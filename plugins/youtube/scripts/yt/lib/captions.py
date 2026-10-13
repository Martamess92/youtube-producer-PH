"""yt-captions — sottotitoli dal transcript a parole (analysis/transcript.words.json).

Le parole vengono portate sul timeline di OUTPUT con edit/assembled.timeline.json (parole nei
tagli scartate, parole a cavallo di un taglio accorciate), oppure restano sul timeline del
sorgente con --timeline none.

Formati:
  srt, vtt  sidecar per YouTube, costruttore v2 (knowledge 06 §1–§5):
            ≤42 caratteri/riga, ≤2 righe, 1–7 s; divisione a programmazione dinamica che stima i car/s sul
            tempo che ogni evento avrà davvero (obiettivo 17, tetto 20 come SDH Netflix: sopra si elenca, mai
            si riscrive il parlato); mai a capo dopo articolo/preposizione/congiunzione, ausiliare+participio,
            determinante; numero+unità e termini composti mai separati; ingresso sul primo frame del parlato,
            uscita 0,5 s dopo, buchi di 2 frame o ≥0,5 s; «- » solo negli scambi rapidi a due.
            Default --edit light: via esitazioni, false partenze e prime copie delle ripetizioni (mai i segnali
            discorsivi); ortografia («perché», «È», «…», «po'»), maiuscole dei marchi e del glossario, numeri
            all'italiana (12.345, 2,5, 40K, 20x). Turni degli speaker riparati in memoria.
            Unità MRR/ARR dopo una cifra e slot manuali = [[segnaposto]] finché non sono confermati
            all'ascolto in analysis/resolutions.json: senza --draft la consegna è BLOCCATA (exit 2);
            con --draft escono <slug>.<lang>.draft.srt/.vtt. --builder v1 = costruttore precedente.
  ass       karaoke da bruciare negli Shorts (1080×1920): blocchi di 2–4 parole, parola attiva
            evidenziata, preset del canale o del suo brand (<brands_dir>/<slug>/ass/<preset>.json, cercato
            prima), altrimenti il preset neutro 'default' del plugin (assets/ass/default.json); hook facoltativo nei primi 3 s in
            alto. Le unità confermate in analysis/resolutions.json vengono sostituite.
  json      captions per Remotion: [{text, startMs, endMs, timestampMs, confidence}]
            (tipo Caption di @remotion/captions).

Esempi:
  yt-captions WORKDIR --format srt,vtt                 # consegna (bloccata se ci sono unità da confermare)
  yt-captions WORKDIR --format srt,vtt --draft         # bozza con i segnaposto, per la revisione
  yt-captions WORKDIR --format srt --timeline none
  yt-captions WORKDIR --format srt --edit verbatim --builder v2
  yt-captions WORKDIR --format ass --style default --range 812.4,851.2 --hook "Tre errori che rifarei" --drop-fillers
  yt-captions WORKDIR --format json

Le filler (parole con "filler": true o "false_start": true nel transcript: esitazioni, prima copia
delle ripetizioni, false partenze) nei sidecar v2 si tolgono di default (--edit light); in ass/json si
tolgono solo con --drop-fillers (consigliato per gli ASS bruciati). I segnali discorsivi ("discourse": true:
allora, quindi, cioè, tipo…) non si tolgono mai. Transcript con lo schema vecchio dei flag: riclassificati in memoria.

Riepilogo JSON: "words" = parole del perimetro ass/json (solo nell'intervallo con --range, al netto dei filler
tolti con --drop-fillers), "words_in_range", "words_timeline", "fillers_dropped", "dropped_words",
"discourse_kept"; "sidecar" = costruttore, edit, filler tolti, slot da confermare, riparazione speaker;
reports.<srt|vtt>: gate (bloccanti), over_ceiling_events (sopra 20 car/s con timecode), readability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import ytcore
from ytcore import log

ASS_DIR = ytcore.ASSETS / "ass"                 # preset inclusi nel plugin (solo default)
# Istanze statiche dei font (libass non sceglie il peso nei font variabili: vedi make_static_fonts.py).
ASS_FONTS = ASS_DIR / "fonts"
FONTSDIR_FALLBACK = ytcore.FONTS

# ── Regole linguistiche (italiano) ─────────────────────────────────────────
WEAK_WORDS = {
    # richiesti: articoli, preposizioni semplici, congiunzioni
    "il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "di", "a", "da", "in", "con", "su",
    "per", "tra", "fra", "e", "o", "ma", "che",
    # preposizioni articolate e varianti
    "del", "dello", "della", "dei", "degli", "delle", "al", "allo", "alla", "ai", "agli", "alle",
    "dal", "dallo", "dalla", "dai", "dagli", "dalle", "nel", "nello", "nella", "nei", "negli",
    "nelle", "sul", "sullo", "sulla", "sui", "sugli", "sulle", "col", "coi", "ed", "od", "ad",
    "se", "non", "né", "ne", "mi", "ti", "si", "ci", "vi", "ce", "ve", "cui", "come", "quando", "perché",
}
# ausiliari: mai a fine evento ("ho / lanciato"), sconsigliati a fine riga
AUX_WORDS = {"ho", "hai", "ha", "abbiamo", "avete", "hanno", "sono", "sei", "è", "siamo", "siete",
             "era", "erano", "ero", "eravamo", "stato", "stata", "stati", "sarà", "sarebbe", "avevo", "aveva"}
UNITS = {
    "%", "percento", "per cento", "€", "euro", "$", "dollari", "dollaro", "k", "mila", "milioni",
    "milione", "miliardi", "miliardo", "anni", "anno", "mesi", "mese", "giorni", "giorno", "ore",
    "ora", "minuti", "minuto", "secondi", "secondo", "settimane", "settimana", "km", "kg", "gb",
    "mb", "tb", "x", "volte", "persone", "utenti", "clienti", "dipendenti", "progetti", "startup",
}
FILLER_LEXICON = {"ehm", "eh", "ehh", "ehmm", "uhm", "um", "mmm", "mm", "mh", "uh", "ah"}
SENT_END = re.compile(r"[.?!…]+[\"»”’)]*$")
SOFT_PUNCT = re.compile(r"[,;:–—]+[\"»”’)]*$")
NUMERIC = re.compile(r"^[€$]?\d[\d.,]*(%|k|x)?$", re.I)

# Regole del costruttore v1 (precedente): riprodotte identiche con --builder v1.
SRT_RULES_V1 = {"max_line": 42, "max_lines": 2, "max_cps": 17.0, "min_dur": 1.0, "max_dur": 7.0,
                "gap": 0.083, "hard_gap": 1.0, "linger": 0.3, "lead_in": 0.25}
# Regole del costruttore v2 (Netflix Italian + Timed Text/timing guide). Ogni costante è
# una regola del set: target 17 car/s, tetto 20 (SDH), 2 frame o ≥0,5 s tra eventi, permanenza 0,5 s.
SIDECAR_RULES: dict[str, Any] = {
    "max_line": 42, "max_lines": 2, "min_dur": 1.0, "max_dur": 7.0,
    "target_cps": 17.0,      # obiettivo morbido (sottotitoli Netflix, adulti)
    "ceiling_cps": 20.0,     # tetto (SDH Netflix): sopra → elencato nel QA, mai riscritto il parlato
    "fps": 30.0, "gap_frames": 2, "chain_below": 0.5,
    "linger": 0.5, "linger_max": 1.5, "lead_max": 0.3,
    "hard_gap": 1.0,
    "hard_gap_bad": 2.5,     # I1: dopo una parola debole la pausa rompe l'evento solo da 2,5 s (tempi Parakeet)
    "min_dur_floor": 0.8,    # dentro una frase la DP non pianifica eventi più corti (Netflix: 20 frame)
    "shot_snap": 0.5,        # parlato che parte ≤0,5 s dopo un taglio: ingresso sul frame del taglio
    "dash": "- ",            # Netflix Italian I.7: trattino + spazio
    "turn_marks": "dialogue",  # dialogue | chained
    "rapid_exchange": 1.5,
    "w_syntax": 1.0, "w_soft": 0.018, "w_hard": 0.03, "w_event": 1.0,
    "w_internal": 0.4,
}
# Default del controllo (check_cues) e di build_cues = v2; max_cps e gap derivati dalle regole v2.
SRT_RULES = {**SIDECAR_RULES, "max_cps": SIDECAR_RULES["target_cps"],
             "gap": SIDECAR_RULES["gap_frames"] / SIDECAR_RULES["fps"]}


# ── Utilità condivise (usate anche da chapters.py e clips.py) ──────────────
def norm(text: str) -> str:
    return re.sub(r"[^\w%€$']", "", text.lower())


def is_filler(word: dict, lexicon_fallback: bool = True) -> bool:
    """True solo per esitazioni, ripetizioni e false partenze; mai per i segnali discorsivi.

    I segnali discorsivi (allora, quindi, cioè…: "discourse": true, o filler_kind 'discourse'
    nello schema vecchio) non si tolgono mai in automatico. Il lessico serve solo per parole
    senza nessun flag (transcript non prodotti da yt-transcribe)."""
    if word.get("discourse") or word.get("filler_kind") == "discourse":
        return False
    if word.get("filler") or word.get("false_start"):
        return True
    if any(k in word for k in ("filler", "false_start", "discourse")):
        return False
    return lexicon_fallback and norm(word["w"]) in FILLER_LEXICON


def _flags_version() -> int:
    import transcribe  # import pigro: numpy e il resto servono solo per i transcript vecchi
    return transcribe.FLAGS_VERSION


def load_words(workdir: Path, path: str | Path | None = None) -> tuple[list[dict], dict]:
    """Parole pulite e ordinate dal transcript §8.3 (+ metadati: language, engine, segments…).

    Un transcript con lo schema vecchio dei flag (senza 'discourse') viene riclassificato in
    memoria con le stesse regole di yt-transcribe --reflag (il file non viene toccato):
    meta['reflagged'] = True."""
    p = Path(path) if path else workdir / "analysis" / "transcript.words.json"
    if not p.is_absolute():
        p = workdir / p
    if not p.exists():
        raise FileNotFoundError(f"Transcript a parole mancante: {p} (esegui yt-transcribe)")
    data = ytcore.read_json(p)
    words = []
    for w in data.get("words", []):
        text = str(w.get("w", "")).strip()
        if not text:
            continue
        start, end = float(w["start"]), float(w["end"])
        end = max(end, start + 0.04)
        words.append({**w, "w": text, "start": start, "end": end})
    words.sort(key=lambda w: (w["start"], w.get("i", 0)))
    meta = {k: v for k, v in data.items() if k != "words"}
    meta["path"] = str(p)
    if words and data.get("flags_version") != _flags_version():
        import transcribe
        transcribe.classify_words(words)
        meta["reflagged"] = True
    return words, meta


def resolve_timeline(workdir: Path, arg: str | None, warnings: list) -> tuple[list[dict] | None, Path | None]:
    """--timeline: None → edit/assembled.timeline.json se esiste; 'none' → timeline del sorgente."""
    if arg and arg.lower() in ("none", "source", "src"):
        return None, None
    path = Path(arg) if arg else workdir / "edit" / "assembled.timeline.json"
    if not path.is_absolute():
        path = workdir / path
    if not path.exists():
        if arg:
            raise FileNotFoundError(f"Timeline non trovato: {path}")
        warnings.append("edit/assembled.timeline.json assente: uso il timeline del SORGENTE (--timeline none)")
        return None, None
    data = ytcore.read_json(path)
    segs = data["segments"] if isinstance(data, dict) else data
    out = []
    for s in segs:
        o0, o1 = float(s["out_start"]), float(s["out_end"])
        src_in = float(s["src_in"])
        out.append({"id": s.get("id"), "src": s.get("src"), "out_start": o0, "out_end": o1,
                    "src_in": src_in, "src_out": float(s.get("src_out", src_in + (o1 - o0)))})
    out.sort(key=lambda s: s["out_start"])
    return out, path


def main_source_key(workdir: Path) -> str | None:
    try:
        proj = ytcore.load_project(workdir)
    except FileNotFoundError:
        return None
    return proj.get("main_source") or next(iter(proj.get("sources", {}) or {"A": 0}))


def map_words(words: list[dict], timeline: list[dict] | None, src_key: str | None = None,
              stats: dict | None = None) -> list[dict]:
    """Porta le parole dal sorgente al timeline di output.

    Una parola tagliata del tutto sparisce; una parola a cavallo di un taglio viene accorciata e
    tenuta solo se ne resta ≥50% (o ≥0.15 s). Un intervallo del sorgente usato due volte (es. cold
    open) produce la parola due volte, una per ogni uso. Ogni parola mappata porta 'seg' (indice
    del segmento) per sapere dove cadono i tagli.
    """
    stats = stats if stats is not None else {}
    if timeline is None:
        out = [{**w, "seg": 0, "src_start": w["start"]} for w in words]
        stats.update(mapped=len(out), dropped=0, clipped=0)
        return out
    out, clipped, used = [], 0, set()
    for si, seg in enumerate(timeline):
        if src_key and seg.get("src") not in (None, src_key):
            continue  # segmento da un'altra sorgente: il transcript non la copre
        s0, s1 = seg["src_in"], seg["src_out"]
        for w in words:
            if w["end"] <= s0 or w["start"] >= s1:
                continue
            a, b = max(w["start"], s0), min(w["end"], s1)
            dur = w["end"] - w["start"]
            if (b - a) < min(0.5 * dur, 0.15):
                continue
            if a > w["start"] + 1e-6 or b < w["end"] - 1e-6:
                clipped += 1
            used.add(id(w))
            off = seg["out_start"] - s0
            out.append({**w, "start": round(a + off, 3), "end": round(b + off, 3), "seg": si,
                        "src_start": w["start"]})
    out.sort(key=lambda w: w["start"])
    stats.update(mapped=len(out), dropped=sum(1 for w in words if id(w) not in used), clipped=clipped)
    return out


def src_to_out(t: float, timeline: list[dict] | None, src_key: str | None = None) -> tuple[float | None, str]:
    """Tempo del sorgente → output. Se t cade in un taglio → inizio del segmento successivo."""
    if timeline is None:
        return t, "identity"
    best_next = None
    for seg in timeline:
        if src_key and seg.get("src") not in (None, src_key):
            continue
        if seg["src_in"] - 1e-6 <= t < seg["src_out"]:
            return seg["out_start"] + (t - seg["src_in"]), "inside"
        if seg["src_in"] > t and (best_next is None or seg["src_in"] < best_next["src_in"]):
            best_next = seg
    if best_next is not None:
        return best_next["out_start"], "in_cut→next_segment"
    return None, "after_end"


def out_to_src(t: float, timeline: list[dict] | None) -> float | None:
    if timeline is None:
        return t
    for seg in timeline:
        if seg["out_start"] - 1e-6 <= t < seg["out_end"]:
            return seg["src_in"] + (t - seg["out_start"])
    return None


def apply_range(words: list[dict], a: float, b: float, rebase: bool = True) -> list[dict]:
    """Tiene le parole in [a, b] (accorciando quelle ai bordi) e, se rebase, porta a a 0."""
    out = []
    for w in words:
        if w["end"] <= a or w["start"] >= b:
            continue
        s, e = max(w["start"], a), min(w["end"], b)
        if (e - s) < min(0.5 * (w["end"] - w["start"]), 0.15):
            continue
        shift = a if rebase else 0.0
        out.append({**w, "start": round(s - shift, 3), "end": round(e - shift, 3)})
    return out


def parse_range(text: str | None) -> tuple[float, float] | None:
    if not text:
        return None
    parts = [p for p in re.split(r"[,\s]+", text.strip()) if p]
    if len(parts) != 2:
        raise ValueError("--range vuole due tempi: a,b (secondi o hh:mm:ss)")
    a, b = ytcore.parse_ts(parts[0]), ytcore.parse_ts(parts[1])
    if b <= a:
        raise ValueError("--range: la fine deve essere dopo l'inizio")
    return a, b


# ── Idempotenza: output più recente degli input + stessa firma degli argomenti ──
def _stamps_path(workdir: Path) -> Path:
    return workdir / "logs" / "stamps.json"


def signature(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def up_to_date(workdir: Path, outputs: list[Path], inputs: list[Path], sig: str) -> bool:
    if not outputs or not all(p.exists() for p in outputs):
        return False
    newest_in = max((p.stat().st_mtime for p in inputs if p and Path(p).exists()), default=0)
    if min(p.stat().st_mtime for p in outputs) < newest_in:
        return False
    try:
        stamps = ytcore.read_json(_stamps_path(workdir))
    except Exception:
        return False
    return all(stamps.get(str(p)) == sig for p in outputs)


def stamp(workdir: Path, outputs: list[Path], sig: str) -> None:
    path = _stamps_path(workdir)
    try:
        stamps = ytcore.read_json(path)
    except Exception:
        stamps = {}
    for p in outputs:
        stamps[str(p)] = sig
    ytcore.write_json(path, stamps)


# ── Unità indivisibili (numero+unità) ──────────────────────────────────────
def build_units(words: list[dict]) -> list[dict]:
    """Raggruppa parole che non vanno mai separate: '18 progetti', '30 %', '€ 25', 'GPT 3.5'."""
    units: list[dict] = []
    for w in words:
        if units:
            prev = units[-1]
            last = prev["words"][-1]["w"]
            cur = norm(w["w"])
            join = (
                (NUMERIC.match(norm(last) or last) and (cur in UNITS or w["w"] in ("%", "€")))
                or (last in ("€", "$") and NUMERIC.match(cur))
                or (re.fullmatch(r"[A-Z]{2,}", last) and NUMERIC.match(w["w"]))
            ) and not SENT_END.search(last) and not SOFT_PUNCT.search(last)
            if join and w.get("speaker") == prev["words"][-1].get("speaker"):
                prev["words"].append(w)
                prev["text"] = _join_text([x["w"] for x in prev["words"]])
                prev["end"] = w["end"]
                continue
        units.append({"words": [w], "text": w["w"], "start": w["start"], "end": w["end"]})
    return units


def _join_text(tokens: list[str]) -> str:
    return re.sub(r" ([%])", r"\1", " ".join(tokens))


def unit_last_word(unit: dict) -> str:
    return norm(unit["words"][-1]["w"]).strip("'")


def ends_weak(units: list[dict]) -> bool:
    if not units:
        return False
    last = units[-1]["words"][-1]["w"]
    if SENT_END.search(last) or SOFT_PUNCT.search(last):
        return False
    return unit_last_word(units[-1]) in WEAK_WORDS


# ── Divisione in righe ─────────────────────────────────────────────────────
def split_lines(units: list[dict], max_line: int, max_lines: int = 2,
                measure=None) -> list[str] | None:
    """Miglior divisione in ≤max_lines righe; None se non entra. `measure` = larghezza (default len)."""
    measure = measure or (lambda s: len(s))
    tokens = [u["text"] for u in units]
    full = _join_text(tokens)
    if measure(full) <= max_line:
        return [full]
    if max_lines < 2 or len(units) < 2:
        return None
    best, best_score = None, -1e9
    for j in range(1, len(units)):
        l1, l2 = _join_text(tokens[:j]), _join_text(tokens[j:])
        w1, w2 = measure(l1), measure(l2)
        if w1 > max_line:
            break
        if w2 > max_line:
            if max_lines > 2:
                rest = split_lines(units[j:], max_line, max_lines - 1, measure)
                if rest is None:
                    continue
                lines = [l1] + rest
            else:
                continue
        else:
            lines = [l1, l2]
        score = -abs(w1 - w2) / max_line
        last1 = units[j - 1]["words"][-1]["w"]
        if SENT_END.search(last1):
            score += 0.6
        elif SOFT_PUNCT.search(last1):
            score += 0.35
        elif unit_last_word(units[j]) in WEAK_WORDS or norm(units[j]["words"][0]["w"]) in WEAK_WORDS:
            score += 0.15  # a capo prima di preposizione/congiunzione = confine di sintagma
        if ends_weak(units[:j]):
            score -= 3.0
        elif unit_last_word(units[j - 1]) in AUX_WORDS and not SOFT_PUNCT.search(last1):
            score -= 1.0
        if w1 <= w2:
            score += 0.1  # piramide rovesciata (riga sotto più lunga) preferita
        if score > best_score:
            best, best_score = lines, score
    return best


# ── Costruzione eventi SRT/VTT, costruttore v1 (--builder v1) ───────────────
def _phrases(units: list[dict], hard_gap: float) -> list[list[dict]]:
    """Blocchi che un evento non deve mai attraversare: cambio speaker, pausa lunga, taglio."""
    phrases, cur = [], []
    for u in units:
        if cur:
            prev = cur[-1]
            pw, uw = prev["words"][-1], u["words"][0]
            if (u["start"] - prev["end"] >= hard_gap or pw.get("speaker") != uw.get("speaker")
                    or pw.get("seg") != uw.get("seg")):
                phrases.append(cur)
                cur = []
        cur.append(u)
    if cur:
        phrases.append(cur)
    return phrases


def _cue_cost(units: list[dict], lines: list[str], at_phrase_end: bool, r: dict) -> float:
    """Costo di un evento nella partizione ottima (più basso = meglio)."""
    text = " ".join(lines)
    fill = len(text) / (r["max_line"] * r["max_lines"])
    cost = 0.35 + (1.0 - fill) ** 2  # pochi eventi, ma pieni in modo equilibrato
    last = units[-1]["words"][-1]["w"]
    if SENT_END.search(last):
        cost -= 0.4
    elif SOFT_PUNCT.search(last):
        cost -= 0.25
    elif not at_phrase_end:
        cost += 0.25
    if not at_phrase_end and ends_weak(units):
        cost += 3.0
    elif not at_phrase_end and not SOFT_PUNCT.search(last) and not SENT_END.search(last) \
            and unit_last_word(units[-1]) in AUX_WORDS:
        cost += 1.2
    if len(lines) > 1:
        first_last = norm(lines[0].split()[-1]).strip("'")
        if first_last in WEAK_WORDS and not re.search(r"[.,;:?!…]$", lines[0]):
            cost += 1.5
    cost += 0.45 * sum(1 for u in units[:-1] if SENT_END.search(u["words"][-1]["w"]))
    if units[-1]["end"] - units[0]["start"] < r["min_dur"]:
        cost += 0.6
    if len(units) == 1 and not at_phrase_end:
        cost += 0.3
    return cost


def _partition(phrase: list[dict], r: dict) -> list[tuple[list[dict], list[str]]]:
    """Programmazione dinamica: divide una frase in eventi che rispettano righe/durata col costo minimo."""
    n = len(phrase)
    best = [0.0] + [math.inf] * n
    back: list[tuple[int, list[str]] | None] = [None] * (n + 1)
    for i in range(1, n + 1):
        for j in range(i - 1, -1, -1):
            chunk = phrase[j:i]
            if i - j > 1 and chunk[-1]["end"] - chunk[0]["start"] > r["max_dur"]:
                break
            lines = split_lines(chunk, r["max_line"], r["max_lines"])
            if lines is None:
                if i - j == 1:  # unità singola più lunga di una riga: la teniamo comunque
                    lines = [chunk[0]["text"]]
                else:
                    break
            cost = best[j] + _cue_cost(chunk, lines, i == n, r)
            if cost < best[i]:
                best[i], back[i] = cost, (j, lines)
    out, i = [], n
    while i > 0:
        j, lines = back[i]
        out.append((phrase[j:i], lines))
        i = j
    return out[::-1]


def build_cues_v1(words: list[dict], rules: dict | None = None) -> list[dict]:
    """Costruttore precedente (nessuna stima della velocità di lettura nella divisione)."""
    r = {**SRT_RULES_V1, **(rules or {})}
    cues = []
    for phrase in _phrases(build_units(words), r["hard_gap"]):
        for chunk, lines in _partition(phrase, r):
            cues.append({"start": chunk[0]["start"], "end": chunk[-1]["end"], "units": chunk,
                         "speaker": chunk[0]["words"][0].get("speaker"), "lines": lines})
    _merge_short_cues(cues, r)
    _fix_timing(cues, r)
    return cues


def _cue_chars(cue: dict) -> int:
    return len(" ".join(cue["lines"]))


def _merge_short_cues(cues: list[dict], r: dict) -> None:
    """Eventi troppo brevi (es. 'Benvenuto Paolo.' + 'Ciao a tutti, grazie.'): unisce col
    successivo se entra nelle regole; con speaker diversi usa il formato dialogo '- riga'."""
    i = 0
    while i < len(cues) - 1:
        a, b = cues[i], cues[i + 1]
        room = b["start"] - a["start"] - r["gap"]
        if room >= r["min_dur"] or b["end"] - a["start"] > r["max_dur"]:
            i += 1
            continue
        if b["start"] - a["end"] > r["hard_gap"]:
            i += 1
            continue
        if a["speaker"] != b["speaker"]:
            la, lb = " ".join(a["lines"]), " ".join(b["lines"])
            if len(la) + 2 <= r["max_line"] and len(lb) + 2 <= r["max_line"]:
                a.update(end=b["end"], units=a["units"] + b["units"], lines=[f"- {la}", f"- {lb}"], dialogue=True)
                del cues[i + 1]
                continue
        else:
            lines = split_lines(a["units"] + b["units"], r["max_line"], r["max_lines"])
            if lines:
                a.update(end=b["end"], units=a["units"] + b["units"], lines=lines)
                del cues[i + 1]
                continue
        i += 1


def _fix_timing(cues: list[dict], r: dict) -> None:
    """Durata minima, lettura ≤ max_cps (estendendo nelle pause), linger, gap ≥2 frame, ≤ max_dur."""
    for i, c in enumerate(cues):
        nxt_start = cues[i + 1]["start"] if i + 1 < len(cues) else math.inf
        limit = min(nxt_start - r["gap"], c["start"] + r["max_dur"])
        need = max(r["min_dur"], _cue_chars(c) / r["max_cps"])
        target = max(c["end"] + r["linger"], c["start"] + need)
        c["end"] = max(c["end"], min(target, limit))
        # almeno 2 frame tra un evento e il successivo (eventi "incatenati")
        c["end"] = max(min(c["end"], nxt_start - r["gap"]), c["start"] + 0.5)
    for i, c in enumerate(cues):  # se ancora corto, anticipa un poco l'ingresso
        dur = c["end"] - c["start"]
        if dur < r["min_dur"]:
            prev_end = cues[i - 1]["end"] if i else 0.0
            c["start"] = max(prev_end + r["gap"], c["start"] - r["lead_in"], c["end"] - r["min_dur"], 0.0)
    for c in cues:
        c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)


def check_cues(cues: list[dict], r: dict | None = None) -> dict:
    """Rapporto regole (per il JSON di riepilogo e il QA). Vale per eventi v1 e v2.

    Gate (knowledge 06 §2.2, 12 E7): BLOCCANO righe >42 caratteri, più di 2 righe, sovrapposizioni, buchi
    sotto 2 frame, eventi sotto 0,8 s o sopra 7 s; si ELENCANO gli eventi sopra 20 car/s (con timecode);
    la quota sopra 17 car/s è solo riportata."""
    r = {**SRT_RULES, **(r or {})}
    gap = r.get("gap") if r.get("gap") is not None else r["gap_frames"] / r["fps"]
    max_cps = r.get("max_cps") or r.get("target_cps", 17.0)
    ceiling = r.get("ceiling_cps", 20.0)
    floor = r.get("min_dur_floor", 0.8)
    rep = {"cues": len(cues), "lines_over_max": 0, "cues_over_2_lines": 0, "cps_over": 0, "max_cps": 0.0,
           "under_min_dur": 0, "over_max_dur": 0, "weak_line_endings": 0, "overlaps": 0,
           "gaps_under_2f": 0, "cps_over_ceiling": 0, "under_floor": 0}
    over_ceiling = []
    prev_end = -1.0
    for c in cues:
        dur = c["end"] - c["start"]
        cps = _cue_chars(c) / dur if dur > 0 else 99
        rep["max_cps"] = round(max(rep["max_cps"], cps), 1)
        rep["cps_over"] += cps > max_cps + 0.05
        if cps > ceiling + 0.05:
            rep["cps_over_ceiling"] += 1
            over_ceiling.append({"t": round(c["start"], 2), "ts": ytcore.fmt_ts(c["start"], "srt"),
                                 "cps": round(cps, 1), "text": " / ".join(c["lines"])})
        rep["under_min_dur"] += dur < r["min_dur"] - 0.005
        rep["under_floor"] += dur < floor - 0.005
        rep["over_max_dur"] += dur > r["max_dur"] + 0.005
        rep["cues_over_2_lines"] += len(c["lines"]) > r["max_lines"]
        rep["overlaps"] += c["start"] < prev_end - 1e-6
        rep["gaps_under_2f"] += 0 <= c["start"] - prev_end < gap - 0.002
        prev_end = c["end"]
        for line in c["lines"]:
            rep["lines_over_max"] += len(line) > r["max_line"]
            last = norm(line.split()[-1]) if line.split() else ""
            if last.strip("'") in WEAK_WORDS and not re.search(r"[.,;:?!…]$", line):
                rep["weak_line_endings"] += 1
    rep["cps_over_pct"] = round(100 * rep["cps_over"] / max(1, len(cues)), 1)
    rep["cps_over_ceiling_pct"] = round(100 * rep["cps_over_ceiling"] / max(1, len(cues)), 1)
    blocking = {k: rep[k] for k in ("lines_over_max", "cues_over_2_lines", "overlaps", "gaps_under_2f",
                                    "under_floor", "over_max_dur") if rep[k]}
    rep["gate"] = {"pass": not blocking, "blocking": blocking}
    rep["over_ceiling_events"] = over_ceiling[:120]
    return rep


# ══ Costruttore sidecar v2 ═════════════════════════════════════════════════
# Pipeline (build_events):
#   1. prepare     edit leggero facoltativo → ortografia → maiuscole del glossario → numeri all'italiana →
#                  slot da confermare (MRR/ARR e altre parole non confermate diventano [[segnaposto]])
#   2. unità       parole da non separare mai (numero+unità, nomi composti, «un po'»)
#   3. frasi       rotture obbligate: cambio speaker, taglio, pausa ≥ hard_gap
#   4. partizione  programmazione dinamica per frase: costo = numero di eventi + qualità della rottura
#                  (sintassi/punteggiatura/pausa) + impaginazione + velocità di lettura (car/s sul tempo che
#                  l'evento avrà davvero a schermo) + penalità per eventi corti
#   5. dialogo     scambi rapidi tra due speaker → un evento, «- » su ogni riga (Netflix Italian I.7)
#   6. tempi       ingresso sul primo frame del parlato, uscita ≥0,5 s dopo, buchi di 2 frame o ≥0,5 s,
#                  1–7 s, agganciati ai frame, mai oltre un taglio
# Misurato su un episodio di prova: eventi sopra 20 car/s 12,8 % → 5,6 %, a capo ben piazzati 60 % → 80 %,
# buchi "lampeggianti" (3 frame–0,5 s) 73 → 3; la quota sopra 17 car/s scende solo da 32,9 a 29,6 %:
# ospite e conduttore parlavano più veloce di 17 car/s (pavimento senza sintassi: 28,3 %).

WEAK2 = set(WEAK_WORDS) | {"lo", "li", "gli", "ne", "nè", "né", "dell'", "all'", "nell'", "dall'", "sull'", "l'",
                           "un'", "tramite", "verso", "senza", "durante", "contro", "presso", "attraverso",
                           "mediante", "entro", "oppure", "però", "quindi", "cioè", "anche", "poi", "invece",
                           "infatti", "mentre", "dove", "anzi", "ovvero", "ossia", "siccome", "finché", "affinché",
                           "poiché"}
AUX2 = set(AUX_WORDS) | {"avevamo", "avevano", "avete", "abbia", "ho", "è", "sono", "siamo", "stato", "stata",
                         "sto", "stai", "sta", "stiamo", "state", "stanno", "stavo", "stava", "stavamo", "stavano"}
MODALS = {"posso", "puoi", "può", "possiamo", "potete", "possono", "potevo", "potevi", "poteva", "potevamo",
          "potevano", "potrei", "potremmo", "devo", "devi", "deve", "dobbiamo", "dovete", "devono", "dovevo",
          "doveva", "dovevamo", "dovrebbe", "voglio", "vuoi", "vuole", "vogliamo", "volete", "vogliono", "volevo",
          "voleva", "volevamo", "vorrei", "vorremmo", "riesco", "riesci", "riesce", "riusciamo", "so", "sai", "sa",
          "sappiamo", "fare", "faccio", "fa", "facciamo"}
INFINITIVE_RX = re.compile(r"^\w+(are|ere|ire|arsi|ersi|irsi|arlo|erlo|irlo|arla|erla|irla|argli|ergli|irgli)$")
DETERMINERS = {"questo", "questa", "questi", "queste", "quel", "quello", "quella", "quei", "quegli", "quelle", "ogni",
               "qualche", "nessun", "nessuna", "alcun", "alcuna", "alcuni", "alcune", "ciascun", "ciascuna", "mio",
               "mia", "miei", "mie", "tuo", "tua", "tuoi", "tue", "suo", "sua", "suoi", "sue", "nostro", "nostra",
               "nostri", "nostre", "vostro", "vostra", "vostri", "vostre", "certi", "certe", "tale", "tali", "tutto",
               "tutta", "tutti", "tutte", "altro", "altra", "altri", "altre", "stesso", "stessa", "stessi", "stesse"}
MODIFIERS = {"più", "molto", "meno", "tanto", "così", "troppo", "poco", "super", "iper", "ben", "assai"}
SUBJ_PRON = {"io", "tu", "lui", "lei", "noi", "voi", "loro"}
PARTICIPLE_RX = re.compile(r"^(\w+(at|it|ut)[oaie]|\w+(ando|endo)|stato|stata|stati|state|fatto|fatta|fatti|detto|detta|"
                           r"messo|messa|preso|presa|visto|vista|scritto|nato|nata|morto|chiesto|risposto|rimasto|"
                           r"successo|aperto|chiuso|deciso|perso|vinto|speso|scelto|letto|corso|mosso|stretto|"
                           r"diventato|venuto|tenuto|voluto|potuto|dovuto|saputo|avuto|cresciuto|venduto|creato|"
                           r"lanciato)$")
CONNECTORS = {"che", "e", "ed", "ma", "perché", "quindi", "però", "se", "quando", "come", "dove", "mentre", "cioè",
              "o", "oppure", "poi", "infatti", "invece", "anche", "perciò", "allora", "siccome", "finché", "anzi",
              "tipo", "comunque", "ovvero", "sia", "né", "nel", "ossia"}
PREPS = {"di", "a", "da", "in", "con", "su", "per", "tra", "fra", "del", "dello", "della", "dei", "degli", "delle",
         "al", "allo", "alla", "ai", "agli", "alle", "dal", "dallo", "dalla", "dai", "dagli", "dalle", "nel",
         "nello", "nella", "nei", "negli", "nelle", "sul", "sullo", "sulla", "sui", "sugli", "sulle", "col", "coi"}
TAGS = {"no", "eh", "vero", "giusto", "sai", "capito"}

SENT_END2 = re.compile(r"[.?!…][\"»”’)\]]*$")
QUESTION = re.compile(r"[?!][\"»”’)\]]*$")
CLAUSE = re.compile(r"[;:–—][\"»”’)\]]*$")
COMMA = re.compile(r",[\"»”’)\]]*$")
TOK_RX = re.compile(r"^([«\"“(\[]*)(.*?)((?:\.\.\.|[»\"”)\].,;:!?…])*)$")
NUMERIC_RX = re.compile(r"^[€$]?\d[\d.,]*(%|k|x)?$", re.I)
SMALL_NUM = {"due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci"}
NUM_WORDS = {"undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16,
             "diciassette": 17, "diciotto": 18, "diciannove": 19, "venti": 20, "trenta": 30, "quaranta": 40,
             "cinquanta": 50, "sessanta": 60, "settanta": 70, "ottanta": 80, "novanta": 90, "cento": 100}
MAGNITUDE = {"mila", "milioni", "milione", "miliardi", "miliardo", "k", "euro", "dollari", "%", "percento"}
VERSION_CTX = {"gpt", "apache", "versione", "v", "ios", "web", "python", "claude", "llama", "next.js", "node"}
ORTHO = [(re.compile(r"^perchè$", re.I), "perché"), (re.compile(r"^poichè$", re.I), "poiché"),
         (re.compile(r"^affinchè$", re.I), "affinché"), (re.compile(r"^benchè$", re.I), "benché"),
         (re.compile(r"^finchè$", re.I), "finché"), (re.compile(r"^nè$", re.I), "né"),
         (re.compile(r"^E'$"), "È"), (re.compile(r"^pò$", re.I), "po'"), (re.compile(r"^qual'è$", re.I), "qual è")]
# grafie distintive sempre applicate (solo marchi generici; quelli dell'episodio vengono dal glossario)
BRAND_CASING = ["ChatGPT", "OpenAI", "GitHub", "LinkedIn", "Gmail", "YouTube", "WhatsApp", "TikTok", "iPhone",
                "macOS", "iOS", "AppSumo", "Acquire.com", "Zendesk", "Perplexity", "Anthropic", "Microsoft",
                "Facebook", "Instagram", "Excel", "Twitter"]
# termini del glossario che sono anche parole comuni: mai rimessi in maiuscolo (nomi di strumenti che sono parole
# inglesi o italiane d'uso corrente, e parole del parlato tech: «una demo», «la build»); gli altri vengono dal glossario
COMMON_WORDS = {"cloud", "cursor", "linear", "notion", "tally", "bubble", "stripe", "luma", "vento", "x", "mvp", "saas",
                "product", "demo", "build"}
# gruppi da non spezzare mai (minuscolo, sequenze di parole); i termini composti del glossario del canale si aggiungono
GLUE_EXTRA = ["un po'", "open source", "side project", "build in public", "vibe coding", "word of mouth",
              "full time", "product market fit", "go-to-market", "claude code", "gpt 3.5", "apache 2.0",
              "product hunt", "per cento"]
UNIT_PLACEHOLDER = "[[MRR/ARR]]"


def split_tok(t: str) -> tuple[str, str, str]:
    m = TOK_RX.match(t)
    return (m.group(1), m.group(2), m.group(3)) if m else ("", t, "")


def core_l(t: str) -> str:
    return split_tok(t)[1].lower()


# ── 0. Turni degli speaker (in memoria, prima dei sottotitoli) ──────────────
_REAL = (lambda s: s not in (None, "OVERLAP"))  # noqa: E731
_SPK_Q = re.compile(r"\?[\"»”’)]*$")
_SPK_END = re.compile(r"[.!][\"»”’)]*$")
_SPK_ELL = re.compile(r"(…|\.\.\.)[\"»”’)]*$")
_SPK_CLAUSE = re.compile(r"[;:][\"»”’)]*$")
_SPK_TAGS = {"no", "eh", "vero", "giusto", "sai", "capito", "ok", "okay", "ne"}
_GREET = {"benvenuto", "benvenuta", "grazie", "ciao", "bentornato", "bentornata"}


def _boundary_strength(words: list[dict], c: int) -> float:
    """Forza di un cambio di turno messo prima della parola c (punteggiatura + pausa)."""
    if c <= 0 or c >= len(words):
        return 0.0
    prev = words[c - 1]["w"]
    tag = re.sub(r"[^\wàèéìòù]", "", prev.lower()) in _SPK_TAGS and c >= 2 and COMMA.search(words[c - 2]["w"])
    if _SPK_Q.search(prev) and not tag:
        s = 3.0
    elif tag:
        s = 0.4                                    # «…, no?»: domanda-coda dentro la frase dello stesso speaker
    elif _SPK_ELL.search(prev):
        s = 1.5
    elif _SPK_END.search(prev):
        s = 2.0
    elif _SPK_CLAUSE.search(prev):
        s = 1.0
    elif COMMA.search(prev):
        s = 0.4
    else:
        s = 0.0
    return s + 1.5 * min(max(0.0, words[c]["start"] - words[c - 1]["end"]), 1.0)


def _fill_unlabelled(words: list[dict]) -> int:
    n, k, changed = len(words), 0, 0
    while k < n:
        if _REAL(words[k].get("speaker")):
            k += 1
            continue
        j = k
        while j < n and not _REAL(words[j].get("speaker")):
            j += 1
        left = words[k - 1].get("speaker") if k > 0 else None
        right = words[j].get("speaker") if j < n else None
        if left is None and right is None:
            k = j
            continue
        if left is None or right is None or left == right:
            spk = left or right
        else:
            spk = left if _boundary_strength(words, j) >= _boundary_strength(words, k) else right
        for w in words[k:j]:
            w["speaker"] = spk
            changed += 1
        k = j
    return changed


def _snap_turns(words: list[dict], back: int = 5, fwd: int = 7, max_dt: float = 2.5, per_word: float = 0.3,
                margin: float = 1.0) -> int:
    """Sposta ogni cambio di speaker sul confine di testo più forte vicino (−5/+7 parole, ±2,5 s), solo se
    batte la posizione della diarizzazione di almeno `margin`; mai svuotare un turno."""
    changed, k, n = 0, 1, len(words)
    while k < n:
        a, b = words[k - 1].get("speaker"), words[k].get("speaker")
        if not (_REAL(a) and _REAL(b) and a != b):
            k += 1
            continue
        tk = words[k]["start"]
        lo = k
        while lo - 1 >= 1 and k - (lo - 1) <= back and words[lo - 2].get("speaker") == a \
                and tk - words[lo - 1]["start"] <= max_dt:
            lo -= 1
        hi = k
        while hi + 1 < n and (hi + 1) - k <= fwd and words[hi + 1].get("speaker") == b \
                and words[hi + 1]["start"] - tk <= max_dt:
            hi += 1
        s_k = _boundary_strength(words, k)
        best, best_score = k, s_k
        for c in range(lo, hi + 1):
            sc = _boundary_strength(words, c) - per_word * abs(c - k)
            if sc > best_score:
                best, best_score = c, sc
        if best != k and _boundary_strength(words, best) >= s_k + margin:
            spk = b if best < k else a
            for w in words[min(best, k):max(best, k)]:
                w["speaker"] = spk
                changed += 1
            k = max(best, k) + 1
        else:
            k += 1
    return changed


def _vocative_to_host(words: list[dict], guest: str, guest_first: str, hosts: set[str], max_words: int = 4) -> int:
    """«Benvenuto Paolo.» / «Grazie mille, Paolo.» non le dice l'ospite: vanno all'ultimo host che ha parlato."""
    changed, s0, last_host = 0, 0, None
    gf = guest_first.lower()
    bounds = []
    for k, w in enumerate(words):
        if _SPK_END.search(w["w"]) or _SPK_Q.search(w["w"]) or _SPK_ELL.search(w["w"]):
            bounds.append((s0, k + 1))
            s0 = k + 1
    if s0 < len(words):
        bounds.append((s0, len(words)))
    for a, b in bounds:
        sent = words[a:b]
        toks = [re.sub(r"[^\wàèéìòù]", "", w["w"].lower()) for w in sent]
        if {w.get("speaker") for w in sent} == {guest} and len(sent) <= max_words and gf in toks \
                and toks[0] in _GREET and last_host:
            for w in sent:
                w["speaker"] = last_host
                changed += 1
        for w in sent:
            if w.get("speaker") in hosts:
                last_host = w["speaker"]
    return changed


def repair_speakers(words: list[dict], project: dict) -> dict:
    """Ripara i turni in memoria: riempie le parole senza speaker dal lato col confine più debole,
    sposta i cambi sul confine di testo più forte, dà all'host i saluti all'ospite per nome.
    Su un episodio di prova: cambi giusti 44/59 → 55/59, parole attribuite male 29 → 9. Tocca solo 'speaker'."""
    import glossary as gl
    names = project.get("speakers") or {}
    hosts_named = set(gl.channel_hosts(project.get("channel", "")))
    hosts = {k for k, v in names.items() if v in hosts_named}
    guests = [k for k in names if k not in hosts]
    out = {"filled": _fill_unlabelled(words), "snapped": _snap_turns(words), "vocative": 0}
    if len(guests) == 1 and hosts and isinstance(names.get(guests[0]), str):
        out["vocative"] = _vocative_to_host(words, guests[0], names[guests[0]].split()[0], hosts)
    out["words_changed"] = out["filled"] + out["snapped"] + out["vocative"]
    return out


# ── 1. Testo ────────────────────────────────────────────────────────────────
def light_edit(words: list[dict]) -> tuple[list[dict], list[dict]]:
    """Toglie esitazioni, false partenze e prime copie delle ripetizioni (is_filler); mai i segnali discorsivi.
    La punteggiatura di fine frase di una parola tolta passa alla precedente; se la parola tolta apriva
    una frase, la successiva prende la maiuscola."""
    kept: list[dict] = []
    dropped: list[dict] = []
    cap_next = False
    for w in words:
        if is_filler(w):
            dropped.append(w)
            pre, core, post = split_tok(w["w"])
            if kept and post and kept[-1].get("speaker") == w.get("speaker"):
                kp, kc, kpost = split_tok(kept[-1]["w"])
                if SENT_END2.search(post) and not SENT_END2.search(kpost):
                    kept[-1] = {**kept[-1], "w": kp + kc + post.lstrip(",")}
            if core[:1].isupper() and (not kept or SENT_END2.search(kept[-1]["w"])
                                       or kept[-1].get("speaker") != w.get("speaker")):
                cap_next = True
            continue
        if cap_next:
            pre, core, post = split_tok(w["w"])
            if core[:1].islower():
                w = {**w, "w": pre + core[:1].upper() + core[1:] + post}
            cap_next = False
        kept.append(w)
    return kept, dropped


def glossary_maps(terms: list[str]) -> tuple[dict[str, str], list[list[str]]]:
    single, multi = {}, []
    for t in terms:
        t = t.strip()
        if not t:
            continue
        toks = t.split()
        if len(toks) == 1:
            if t.lower() != t and t.lower() not in COMMON_WORDS:
                single[t.lower()] = t
        else:
            multi.append(toks)
    return single, multi


def _after_name(out: list[dict], k: int) -> bool:
    if k == 0:
        return False
    prev = split_tok(out[k - 1]["w"])[1]
    starts_sentence = k == 1 or bool(SENT_END2.search(out[k - 2]["w"]))
    return prev[:1].isupper() and not starts_sentence


def normalize_text(words: list[dict], glossary: list[str], log_: list[dict]) -> list[dict]:
    """Ortografia, maiuscole del glossario, convenzioni italiane dei numeri. Ogni modifica va nel registro."""
    single, multi = glossary_maps(list(BRAND_CASING) + list(glossary))
    out = [dict(w) for w in words]

    def change(k: int, new: str, rule: str) -> None:
        if out[k]["w"] != new:
            log_.append({"t": out[k].get("src_start", out[k]["start"]), "from": out[k]["w"], "to": new, "rule": rule})
            out[k]["w"] = new

    for k, w in enumerate(out):
        pre, core, post = split_tok(w["w"])
        new_post = post.replace("...", "…")
        new_core = core
        for rx, rep in ORTHO:
            if rx.match(core):
                new_core = rep[:1].upper() + rep[1:] if core[:1].isupper() else rep
        if core.lower() in single and core != single[core.lower()]:
            new_core = single[core.lower()]
        if (new_core, new_post) != (core, post):
            change(k, pre + new_core + new_post, "ortho/glossary")
    for k in range(1, len(out)):
        prev = out[k - 1]["w"]
        if re.search(r"[.?!][\"»”’)\]]*$", prev) and not prev.endswith("...") and not prev.endswith("…") \
                and out[k - 1].get("speaker") == out[k].get("speaker"):
            pre, core, post = split_tok(out[k]["w"])
            if core[:1].islower():
                change(k, pre + core[:1].upper() + core[1:] + post, "capital-after-period")
    for toks in multi:
        n = len(toks)
        low = [t.lower() for t in toks]
        for k in range(len(out) - n + 1):
            cores = [split_tok(out[k + j]["w"]) for j in range(n)]
            if [c[1].lower() for c in cores] == low and [c[1] for c in cores] != toks:
                for j in range(n):
                    p, c, q = cores[j]
                    change(k + j, p + toks[j] + q, "glossary-multi")
    for k, w in enumerate(out):
        pre, core, post = split_tok(w["w"])
        prev_core = core_l(out[k - 1]["w"]) if k else ""
        new = core
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", core):               # migliaia: separatore solo da 5 cifre
            digits = core.replace(".", "")
            if len(digits) <= 4:
                new = digits
        elif re.fullmatch(r"\d{5,}", core):
            new = f"{int(core):,}".replace(",", ".")
        elif re.fullmatch(r"\d+\.\d{1,2}", core) and prev_core not in VERSION_CTX and not _after_name(out, k):
            new = core.replace(".", ",")                            # virgola decimale (non nelle versioni: GPT 3.5)
        elif re.fullmatch(r"\d+(?:[.,]\d+)?k", core):
            new = core[:-1] + "K"                                   # 40k → 40K (detto «K»)
        elif re.fullmatch(r"\d+X", core):
            new = core[:-1] + "x"                                   # 20X → 20x
        if new != core:
            change(k, pre + new + post, "number-format")
    for k, w in enumerate(out):                                     # numeri ≥11 in lettere vicino a una grandezza
        pre, core, post = split_tok(w["w"])
        val = NUM_WORDS.get(core.lower())
        if val is None:
            continue
        if k == 0 or SENT_END2.search(out[k - 1]["w"]) or out[k - 1].get("speaker") != w.get("speaker"):
            continue
        ok = False
        for j in range(k + 1, min(len(out), k + 4)):
            cj = core_l(out[j]["w"])
            if cj in MAGNITUDE:
                ok = True
                break
            if not (cj in NUM_WORDS or NUMERIC_RX.match(cj) or cj in ("o", "e")):
                break
        if ok:
            change(k, pre + str(val) + post, "number-words")
    return out


def review_key(w: dict) -> str:
    return f"{w.get('src_start', w['start']):.2f}"


def find_review_slots(words: list[dict], manual: list[dict] | None = None) -> dict[int, dict]:
    """Parole da confermare: unità dopo una cifra (flag unit_review di yt-transcribe, o riconosciute qui per i
    transcript vecchi) e parole elencate a mano in analysis/resolutions.json "slots" ({t, from, placeholder})."""
    import postcorrect as pcm
    targets = {k: {"kind": "unit", "placeholder": UNIT_PLACEHOLDER}
               for k in set(pcm.find_unit_slots(words)) | {k for k, w in enumerate(words) if w.get("unit_review")}}
    for m in manual or []:
        try:
            t, frm = float(m["t"]), str(m["from"])
        except (KeyError, TypeError, ValueError):
            continue
        for k, w in enumerate(words):
            if abs(w.get("src_start", w["start"]) - t) < 0.06 and split_tok(w["w"])[1] == frm:
                targets[k] = {"kind": m.get("kind", "word"), "placeholder": m.get("placeholder") or f"[[{frm}?]]"}
    return targets


def apply_review(words: list[dict], manual: list[dict] | None, resolutions: dict[str, str] | None,
                 log_: list[dict]) -> list[dict]:
    """Le parole non confermate diventano segnaposto (bozza) o il testo risolto dopo l'ascolto. Mai indovinate."""
    resolutions = resolutions or {}
    out = [dict(w) for w in words]
    for k, info in sorted(find_review_slots(out, manual).items()):
        w = out[k]
        pre, core, post = split_tok(w["w"])
        key = review_key(w)
        new_core = resolutions.get(key) or info["placeholder"]
        w["review"] = {"kind": info["kind"], "asr": core, "key": key, "resolved": bool(resolutions.get(key))}
        log_.append({"t": w.get("src_start", w["start"]), "from": w["w"], "to": pre + new_core + post,
                     "rule": f"review-{info['kind']}", "resolved": bool(resolutions.get(key)), "key": key})
        w["w"] = pre + new_core + post
    return out


# ── 2. Unità ────────────────────────────────────────────────────────────────
def make_units(words: list[dict], glue: list[list[str]]) -> list[dict]:
    glue_l = [[t.lower() for t in g] for g in glue]
    n = len(words)
    join_next = [False] * n
    cores = [core_l(w["w"]) for w in words]
    for g in glue_l:
        m = len(g)
        for k in range(n - m + 1):
            if cores[k:k + m] == g and all(not SENT_END2.search(words[k + j]["w"]) and not COMMA.search(words[k + j]["w"])
                                           for j in range(m - 1)):
                for j in range(m - 1):
                    join_next[k + j] = True
    import postcorrect as pcm
    for k in range(n - 1):
        a, b = words[k], words[k + 1]
        ca, cb = cores[k], cores[k + 1]
        if SENT_END2.search(a["w"]) or COMMA.search(a["w"]) or CLAUSE.search(a["w"]):
            continue
        b_slot = (b.get("review") or {}).get("kind") == "unit"
        if (NUMERIC_RX.match(ca) or ca in NUM_WORDS or ca in SMALL_NUM or ca in ("mille", "mila")) and (
                cb in UNITS or cb in MAGNITUDE or pcm.UNIT_SLOT_RX.match(cb) or b_slot or cb in ("%",)):
            join_next[k] = True
        if ca in ("€", "$") and NUMERIC_RX.match(cb):
            join_next[k] = True
    units: list[dict] = []
    cur: list[dict] = []
    for k, w in enumerate(words):
        cur.append(w)
        same = k + 1 < n and words[k + 1].get("speaker") == w.get("speaker") and words[k + 1].get("seg") == w.get("seg")
        if not (join_next[k] and same):
            units.append({"words": cur, "text": " ".join(x["w"] for x in cur), "start": cur[0]["start"],
                          "end": cur[-1]["end"], "speaker": cur[0].get("speaker"), "seg": cur[0].get("seg")})
            cur = []
    return units


# ── 3. Qualità delle rotture ────────────────────────────────────────────────
def break_kind(left: dict, right: dict) -> str:
    lw = left["words"][-1]["w"]
    rw = right["words"][0]["w"]
    lc = core_l(lw).strip("'")
    rc = core_l(rw)
    if rc in TAGS and QUESTION.search(rw):
        return "tag"
    if SENT_END2.search(lw):
        return "comma" if lc in TAGS else "sentence"
    if CLAUSE.search(lw):
        return "clause"
    if COMMA.search(lw):
        return "comma"
    if lc in WEAK2 or core_l(lw).endswith("'"):
        return "weak"
    if (lc in AUX2 and PARTICIPLE_RX.match(rc)) or (lc in MODALS and INFINITIVE_RX.match(rc)):
        return "aux+part"
    if lc in DETERMINERS:
        return "det"
    if lc in AUX2 or lc in MODALS:
        return "aux"
    if lc in MODIFIERS or lc in SUBJ_PRON:
        return "mod"
    if rc in CONNECTORS:
        return "connector"
    if rc in PREPS:
        return "prep"
    return "neutral"


EVENT_COST = 1.0
EVENT_BREAK_COST = {"sentence": -1.2, "clause": -0.3, "comma": -0.15, "connector": -0.1, "prep": 0.0,
                    "neutral": 0.6, "mod": 1.2, "aux": 1.5, "det": 2.0, "tag": 2.5, "aux+part": 2.5, "weak": 4.0}
LINE_BREAK_COST = {"sentence": -0.5, "clause": -0.35, "comma": -0.3, "connector": -0.2, "prep": -0.1,
                   "neutral": 0.3, "mod": 0.8, "aux": 0.8, "det": 1.5, "tag": 1.5, "aux+part": 1.5, "weak": 2.5}
GOOD_BREAKS = {"sentence", "clause", "comma", "connector", "prep"}
BAD_BREAKS = {"weak", "aux+part", "det", "tag"}


def layout(units: list[dict], max_line: int, reserve: int = 0) -> tuple[list[str], float] | None:
    """Miglior impaginazione su 1 o 2 righe. reserve = caratteri liberi sulla riga 1 (per «- »)."""
    texts = [u["text"] for u in units]
    full = " ".join(texts)
    if len(full) <= max_line - reserve:
        return [full], 0.0
    best = None
    for j in range(1, len(units)):
        l1, l2 = " ".join(texts[:j]), " ".join(texts[j:])
        if len(l1) > max_line - reserve:
            break
        if len(l2) > max_line:
            continue
        cost = LINE_BREAK_COST[break_kind(units[j - 1], units[j])] + 0.8 * abs(len(l1) - len(l2)) / max_line
        if len(l1) > len(l2) + 4:
            cost += 0.25                                   # piramide rovesciata preferita
        if len(l1.split()) <= 2 and len(l2) > 2 * len(l1):
            cost += 0.5                                    # evitare 1–2 parole sulla riga in alto
        if best is None or cost < best[1]:
            best = ([l1, l2], cost)
    return best


# ── 4. Frasi e partizione ───────────────────────────────────────────────────
def phrases(units: list[dict], hard_gap: float, hard_gap_bad: float | None = None) -> list[list[dict]]:
    """Rotture obbligate: speaker, taglio, pausa ≥ hard_gap. Una pausa dopo una parola debole o tra ausiliare e
    participio («ho aperto il ‖ … negozio online») rompe solo da hard_gap_bad in su: con i tempi Parakeet le pause
    di esitazione a metà frase diventano visibili e romperle lì dà eventi che finiscono su un articolo."""
    out, cur = [], []
    for u in units:
        if cur:
            p = cur[-1]
            gap = u["start"] - p["end"]
            long_pause = gap >= hard_gap and (hard_gap_bad is None or gap >= hard_gap_bad
                                              or break_kind(p, u) not in BAD_BREAKS)
            if u["speaker"] != p["speaker"] or u["seg"] != p["seg"] or long_pause:
                out.append(cur)
                cur = []
        cur.append(u)
    if cur:
        out.append(cur)
    return out


def partition(ph: list[dict], t_next: float, r: dict, reserve_first: int = 0,
              strict: bool = True) -> list[tuple[list[dict], list[str]]]:
    n = len(ph)
    gap = r["gap_frames"] / r["fps"]
    best = [0.0] + [math.inf] * n
    back: list[Any] = [None] * (n + 1)
    for i in range(1, n + 1):
        for j in range(i - 1, -1, -1):
            chunk = ph[j:i]
            if i - j > 1 and chunk[-1]["end"] - chunk[0]["start"] > r["max_dur"]:
                break
            lay = layout(chunk, r["max_line"], reserve_first if j == 0 else 0)
            if lay is None:
                if i - j == 1:
                    lay = ([chunk[0]["text"]], 2.0)
                else:
                    break
            lines, lcost = lay
            chars = len(" ".join(lines))
            w0 = chunk[0]["start"]
            w1 = min((ph[i]["start"] if i < n else t_next) - gap, chunk[-1]["end"] + r["linger_max"])
            w1 = min(w1, w0 + r["max_dur"])
            dur = max(w1 - w0, 0.05)
            if strict and dur < r["min_dur_floor"] and not (j == 0 and i == n):
                continue
            cps = chars / dur
            cost = r["w_event"] * EVENT_COST + r["w_syntax"] * lcost
            cost += chars * (r["w_soft"] * max(0.0, cps - r["target_cps"]) + r["w_hard"] * max(0.0, cps - r["ceiling_cps"]))
            if dur < r["min_dur"]:
                cost += 6.0 * (r["min_dur"] - dur)
            if chars < 15 and not (j == 0 and i == n):
                cost += 0.8 * r["w_syntax"]
            if i < n:
                cost += r["w_syntax"] * (EVENT_BREAK_COST[break_kind(ph[i - 1], ph[i])]
                                         - 0.4 * min(max(0.0, ph[i]["start"] - ph[i - 1]["end"]), 1.0))
            ends = [k for k, u in enumerate(chunk[:-1]) if SENT_END2.search(u["words"][-1]["w"])]
            cost += r["w_syntax"] * r["w_internal"] * len(ends)
            if ends and i < n and len(" ".join(u["text"] for u in chunk[ends[-1] + 1:])) < 15:
                cost += r["w_syntax"] * 1.5                # frase nuova lasciata in coda all'evento
            tot = best[j] + cost
            if tot < best[i]:
                best[i], back[i] = tot, (j, lines)
    if back[n] is None:
        return partition(ph, t_next, r, reserve_first, strict=False)
    out, i = [], n
    while i > 0:
        j, lines = back[i]
        out.append((ph[j:i], lines))
        i = j
    return out[::-1]


def _make_event(units: list[dict], lines: list[str], phrase_id: int) -> dict:
    words = [w for u in units for w in u["words"]]
    return {"units": units, "words": words, "lines": lines, "speaker": units[0]["speaker"], "seg": units[0]["seg"],
            "s0": words[0]["start"], "e0": words[-1]["end"], "phrase": phrase_id, "dialogue": False,
            "turn_mark": False, "seg_end": words[0].get("seg_end"), "seg_start": words[0].get("seg_start")}


# ── 5. Dialogo ──────────────────────────────────────────────────────────────
def _dialogue(events: list[dict], r: dict) -> int:
    n_merged, i, dash = 0, 0, r["dash"]
    while i < len(events) - 1:
        a, b = events[i], events[i + 1]
        ta, tb = " ".join(a["lines"]), " ".join(b["lines"])
        rapid = (b["s0"] - a["s0"] < r["rapid_exchange"]) or (b["e0"] - b["s0"] < 0.8 and len(tb) <= 20)
        if (a["speaker"] != b["speaker"] and not a["dialogue"] and not b["dialogue"] and a["seg"] == b["seg"]
                and len(dash + ta) <= r["max_line"] and len(dash + tb) <= r["max_line"]
                and b["s0"] - a["e0"] < r["hard_gap"] and b["e0"] - a["s0"] <= r["max_dur"] and rapid):
            events[i] = {**a, "units": a["units"] + b["units"], "words": a["words"] + b["words"],
                         "lines": [dash + ta, dash + tb], "e0": b["e0"], "dialogue": True,
                         "speakers": [a["speaker"], b["speaker"]]}
            del events[i + 1]
            n_merged += 1
        i += 1
    return n_merged


# ── 6. Tempi ────────────────────────────────────────────────────────────────
def _fr(t: float, fps: float) -> float:
    return round(t * fps) / fps


def _timing(events: list[dict], r: dict) -> None:
    fps = r["fps"]
    gap = r["gap_frames"] / fps
    for i, e in enumerate(events):
        e["start"] = _fr(e["s0"], fps)
        ss = e.get("seg_start")
        if ss is not None and 0 < e["s0"] - ss <= r["shot_snap"] and (i == 0 or events[i - 1].get("seg") != e.get("seg")):
            e["start"] = _fr(ss, fps)
    for i, e in enumerate(events):
        nxt = events[i + 1]["start"] if i + 1 < len(events) else math.inf
        need = len(" ".join(e["lines"])) / r["target_cps"]
        cap = min(nxt - gap, e["start"] + r["max_dur"], e["e0"] + r["linger_max"])
        if e.get("seg_end") is not None:
            cap = min(cap, e["seg_end"] - gap)
        end = min(max(e["e0"] + r["linger"], e["start"] + need, e["start"] + r["min_dur"]), cap)
        if nxt < math.inf and gap < nxt - end < r["chain_below"] \
                and (e.get("seg_end") is None or nxt <= e["seg_end"] + 1e-6):
            end = nxt - gap
        e["end"] = max(end, e["start"] + 2 / fps)
    for i, e in enumerate(events):
        if e["end"] - e["start"] < r["min_dur"] - 1e-6:
            nxt = events[i + 1]["start"] if i + 1 < len(events) else math.inf
            e["end"] = max(e["end"], min(e["start"] + r["min_dur"], nxt - gap))
        if e["end"] - e["start"] < r["min_dur"] - 1e-6:
            prev_end = events[i - 1]["end"] if i else 0.0
            e["start"] = max(prev_end + gap, e["end"] - r["min_dur"], e["s0"] - r["lead_max"], 0.0)
    for i, e in enumerate(events):
        e["start"], e["end"] = _fr(e["start"], fps), _fr(min(e["end"], e["start"] + r["max_dur"]), fps)
        if i and e["start"] < events[i - 1]["end"] + gap - 1e-6:
            events[i - 1]["end"] = _fr(e["start"] - gap, fps)
    for i in range(len(events) - 1):
        a, b = events[i], events[i + 1]
        g = b["start"] - a["end"]
        same_seg = a.get("seg") == b.get("seg") or a.get("seg_end") is None
        if gap + 0.5 / fps < g < r["chain_below"] and same_seg and b["start"] - gap - a["start"] <= r["max_dur"] + 1e-6:
            a["end"] = _fr(b["start"] - gap, fps)
    # salvaguardia: parole con tempi schiacciati sullo stesso istante (stime senza audio) non devono mai dare
    # eventi a durata nulla o negativa né sovrapposti; gli eventi così corti restano visibili al gate (under_floor)
    one = 2 / fps
    for i, e in enumerate(events):
        if i:
            a = events[i - 1]
            if e["start"] < a["start"] + one + gap - 1e-6:
                e["start"] = _fr(a["start"] + one + gap, fps)
            if a["end"] > e["start"] - gap + 1e-6:
                a["end"] = _fr(e["start"] - gap, fps)
        if e["end"] < e["start"] + one - 1e-6:
            e["end"] = _fr(e["start"] + one, fps)


def _merge_flash(events: list[dict], r: dict) -> int:
    """Dopo i tempi: un evento ancora sotto min_dur_floor (stretto tra un taglio e il parlato) si unisce a un
    vicino dello stesso speaker se il testo sta in 2 × max_line. Il chiamante ricalcola i tempi."""
    n, i = 0, 0
    while i < len(events):
        e = events[i]
        if e["end"] - e["start"] >= r["min_dur_floor"] - 1e-6 or e.get("dialogue"):
            i += 1
            continue
        for j in (i - 1, i + 1):
            if not (0 <= j < len(events)):
                continue
            o = events[j]
            if o["speaker"] != e["speaker"] or o.get("dialogue"):
                continue
            a, b = (o, e) if j < i else (e, o)
            if b["s0"] - a["e0"] >= r["hard_gap"] or b["e0"] - a["s0"] > r["max_dur"]:
                continue
            lay = layout(a["units"] + b["units"], r["max_line"])
            if lay is None:
                continue
            k = min(i, j)
            events[k:k + 2] = [{**a, "units": a["units"] + b["units"], "words": a["words"] + b["words"],
                                "lines": lay[0], "e0": b["e0"], "seg_end": b.get("seg_end"),
                                "crosses_cut": a.get("seg") != b.get("seg")}]
            n += 1
            break
        i += 1
    return n


def _turn_marks(events: list[dict], r: dict) -> int:
    if r["turn_marks"] != "chained":
        return 0
    n = 0
    for i in range(1, len(events)):
        a, b = events[i - 1], events[i]
        if b["dialogue"] or a["speaker"] == b["speaker"]:
            continue
        if b["start"] - a["end"] < r["chain_below"] and len(r["dash"] + b["lines"][0]) <= r["max_line"]:
            b["lines"] = [r["dash"] + b["lines"][0]] + b["lines"][1:]
            b["turn_mark"] = True
            n += 1
    return n


def build_events(words: list[dict], rules: dict | None = None, *, glossary: list[str] | None = None,
                 light: bool = False, manual_review: list[dict] | None = None,
                 resolutions: dict[str, str] | None = None, glue_extra: list[str] | None = None) -> dict:
    """Costruttore sidecar v2. Ritorna {events, log, dropped, review_open, phrases, dialogue_events, …}."""
    r = {**SIDECAR_RULES, **(rules or {})}
    log_: list[dict] = []
    ws = [dict(w) for w in words]
    dropped: list[dict] = []
    if light:
        ws, dropped = light_edit(ws)
    ws = normalize_text(ws, glossary or [], log_)
    ws = apply_review(ws, manual_review or [], resolutions, log_)
    glue = [g.split() for g in (glue_extra or GLUE_EXTRA)] + [t.split() for t in (glossary or []) if " " in t.strip()]
    units = make_units(ws, glue)
    phs = phrases(units, r["hard_gap"], r.get("hard_gap_bad"))
    events: list[dict] = []
    for pi, ph in enumerate(phs):
        t_next = phs[pi + 1][0]["start"] if pi + 1 < len(phs) else math.inf
        new_turn = pi > 0 and phs[pi - 1][-1]["speaker"] != ph[0]["speaker"]
        reserve = len(r["dash"]) if (r["turn_marks"] == "chained" and new_turn) else 0
        for chunk, lines in partition(ph, t_next, r, reserve):
            events.append(_make_event(chunk, lines, pi))
    n_dlg = _dialogue(events, r)
    _timing(events, r)
    n_flash = _merge_flash(events, r)
    if n_flash:
        _timing(events, r)
    n_turn = _turn_marks(events, r)
    review_open = [x for x in log_ if x["rule"].startswith("review") and not x.get("resolved")]
    return {"events": events, "log": log_, "dropped": dropped, "words_out": ws, "phrases": len(phs),
            "dialogue_events": n_dlg, "turn_marks": n_turn, "flash_merges": n_flash, "review_open": review_open,
            "rules": r}


def build_cues(words: list[dict], rules: dict | None = None) -> list[dict]:
    """Sottotitoli SRT/VTT col costruttore v2 (testo verbatim: togliere i filler è compito di chi chiama o di
    build_events(light=True)). Stessa API di sempre: eventi con start, end, lines, speaker, units, words."""
    return build_events(words, rules)["events"]


def readability(events: list[dict], *, fps: float = 30.0) -> dict:
    """Metriche di leggibilità per qualunque lista di eventi (v1 o v2)."""
    import statistics
    n = len(events)
    if not n:
        return {"events": 0}
    gap2 = 2 / fps
    cps, durs, ends_kind, line_kind = [], [], {}, {}
    one_line = top_heavy = short_top = flicker = placeholders = 0
    for i, e in enumerate(events):
        ws = e.get("words") or [w for u in e.get("units", []) for w in u["words"]]
        text = " ".join(e["lines"])
        dur = e["end"] - e["start"]
        durs.append(dur)
        cps.append(len(text) / dur if dur > 0 else 99)
        one_line += len(e["lines"]) == 1
        if len(e["lines"]) == 2 and not e.get("dialogue"):
            l1, l2 = e["lines"]
            top_heavy += len(l1) > len(l2) + 4
            short_top += len(l1.split()) <= 2 and len(l2) > 2 * len(l1)
            first = l1[2:] if e.get("turn_mark") else l1
            nw1, acc, kidx = len(first.split()), 0, None
            for k2, w in enumerate(ws):
                acc += len(w["w"].split())
                if acc == nw1:
                    kidx = k2
                    break
            if kidx is not None and kidx + 1 < len(ws):
                k = break_kind({"words": [ws[kidx]]}, {"words": [ws[kidx + 1]]})
                line_kind[k] = line_kind.get(k, 0) + 1
        placeholders += text.count("[[")
        if i + 1 < n:
            g = events[i + 1]["start"] - e["end"]
            flicker += gap2 + 0.5 / fps < g < 0.5 - 1e-6
            nw = (events[i + 1].get("words") or [w for u in events[i + 1].get("units", []) for w in u["words"]])[0]
            if ws and ws[-1].get("seg") == nw.get("seg"):
                k = break_kind({"words": [ws[-1]]}, {"words": [nw]})
                ends_kind[k] = ends_kind.get(k, 0) + 1
    nb, nl = sum(ends_kind.values()), sum(line_kind.values())
    pct = (lambda x, d: round(100 * x / d, 1) if d else 0.0)  # noqa: E731
    chars = [len(" ".join(e["lines"])) for e in events]
    return {
        "events": n, "cps_p50": round(sorted(cps)[n // 2], 1), "cps_max": round(max(cps), 1),
        "over17_pct": pct(sum(c > 17.05 for c in cps), n), "over20_pct": pct(sum(c > 20.05 for c in cps), n),
        "over20_chars_pct": pct(sum(ch for ch, c in zip(chars, cps) if c > 20.05), sum(chars)),
        "dur_mean": round(statistics.mean(durs), 2), "under1s": sum(d < 0.995 for d in durs),
        "over7s": sum(d > 7.005 for d in durs), "one_line_pct": pct(one_line, n),
        "top_heavy": top_heavy, "short_top_line": short_top,
        "event_breaks_good_pct": pct(sum(v for k, v in ends_kind.items() if k in GOOD_BREAKS), nb),
        "event_breaks_bad": sum(v for k, v in ends_kind.items() if k in BAD_BREAKS),
        "line_breaks_good_pct": pct(sum(v for k, v in line_kind.items() if k in GOOD_BREAKS), nl),
        "line_breaks_bad": sum(v for k, v in line_kind.items() if k in BAD_BREAKS),
        "flicker_gaps_3f_to_0_5s": flicker, "dialogue_events": sum(bool(e.get("dialogue")) for e in events),
        "placeholders": placeholders,
    }


def caption_glossary(workdir: Path, project: dict) -> list[str]:
    """Grafie per le maiuscole dei sottotitoli: speaker, glossary_extra, termini d'episodio di analysis/glossary.json
    e glossario del canale P1/P2 (i P3 solo se l'episodio li nomina: «Vento» è anche una parola comune)."""
    import glossary as gl
    terms = [v for v in (project.get("speakers") or {}).values() if isinstance(v, str)]
    terms += list(project.get("glossary_extra") or [])
    gdoc = gl.load_glossary_doc(workdir)
    if gdoc:
        terms += [t["term"] for t in gdoc.get("terms", [])
                  if set(t.get("sources", {})) & {"project", "doc", "yt", "web"}]
    episode = {t.lower() for t in terms}
    for c in gl.channel_terms(project.get("channel", "")):
        if c["tier"] in ("P1", "P2") or c["term"].lower() in episode:
            terms.append(c["term"])
    return list(dict.fromkeys(t for t in terms if t and t.strip()))


def load_resolutions(path: Path | None) -> tuple[dict[str, str], list[dict]]:
    """analysis/resolutions.json → ({chiave: testo confermato}, slot manuali). Accetta anche la forma piatta."""
    if not path or not path.exists():
        return {}, []
    data = ytcore.read_json(path)
    if not isinstance(data, dict):
        return {}, []
    res = data.get("resolved") if isinstance(data.get("resolved"), dict) else \
        {k: v for k, v in data.items() if re.fullmatch(r"\d+\.\d\d", k)}
    res = {k: v.strip() for k, v in res.items() if isinstance(v, str) and v.strip()}
    slots = [s for s in data.get("slots", []) if isinstance(s, dict)]
    return res, slots


def resolve_words_inplace(words: list[dict], resolutions: dict[str, str]) -> int:
    """ASS/JSON: sostituisce le unità confermate; ritorna quante unità restano NON confermate nel perimetro."""
    import postcorrect as pcm
    idx = set(pcm.find_unit_slots(words)) | {k for k, w in enumerate(words) if w.get("unit_review")}
    open_ = 0
    for k in idx:
        w = words[k]
        key = review_key(w)
        if resolutions.get(key):
            pre, core, post = split_tok(w["w"])
            words[k] = {**w, "w": pre + resolutions[key] + post}
        else:
            open_ += 1
    return open_


def write_srt(cues: list[dict], path: Path) -> Path:
    blocks = [f"{n}\n{ytcore.fmt_ts(c['start'], 'srt')} --> {ytcore.fmt_ts(c['end'], 'srt')}\n" + "\n".join(c["lines"])
              for n, c in enumerate(cues, 1)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return path


def write_vtt(cues: list[dict], path: Path, lang: str = "it") -> Path:
    blocks = [f"{ytcore.fmt_ts(c['start'], 'vtt')} --> {ytcore.fmt_ts(c['end'], 'vtt')}\n" + "\n".join(c["lines"])
              for c in cues]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"WEBVTT\nKind: captions\nLanguage: {lang}\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")
    return path


# ── JSON per Remotion ──────────────────────────────────────────────────────
def remotion_captions(words: list[dict]) -> list[dict]:
    """Caption di @remotion/captions: testo con lo spazio iniziale (createTikTokStyleCaptions lo usa)."""
    out = []
    for k, w in enumerate(words):
        p = w.get("p")
        out.append({"text": (" " if k else "") + w["w"], "startMs": int(round(w["start"] * 1000)),
                    "endMs": int(round(w["end"] * 1000)), "timestampMs": int(round(w["start"] * 1000)),
                    "confidence": round(float(p), 3) if isinstance(p, (int, float)) else None})
    return out


# ── ASS (karaoke Shorts) ───────────────────────────────────────────────────
def _external_ass_dirs() -> list[Path]:
    """<brands_dir>/<slug>/ass dei brand esterni (ordine di brands_dirs; il plugin escluso)."""
    out: list[Path] = []
    for d in ytcore.BRANDS_DIRS:
        try:
            if d.resolve() == ytcore.BRANDS.resolve():
                continue
            children = sorted(d.iterdir())
        except OSError:
            continue
        out += [c / "ass" for c in children if (c / "ass").is_dir()]
    return out


def preset_path(name: str | None) -> Path | None:
    """File del preset ASS: prima i brand esterni (<brands_dir>/<name>/ass/<name>.json, poi
    <brands_dir>/*/ass/<name>.json), poi assets/ass del plugin. None se non esiste."""
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", str(name)):
        return None
    bd = ytcore.brand_dir(name)
    cands = [bd / "ass" / f"{name}.json"] if bd and ytcore.brand_is_external(name) else []
    cands += [d / f"{name}.json" for d in _external_ass_dirs()]
    cands.append(ASS_DIR / f"{name}.json")
    return next((c for c in cands if c.is_file()), None)


def default_style(channel: str | None) -> str:
    """Preset ASS di default di un canale: <canale>.json se esiste, poi quello del brand del canale
    (brand.slug del profilo), altrimenti il preset neutro del plugin (default)."""
    if channel and preset_path(channel):
        return str(channel)
    brand = ytcore.channel_brand(channel) if channel else None
    if brand and preset_path(brand):
        return brand
    return ytcore.DEFAULT_ASS_PRESET


def preset_brand(preset: dict, style: str, channel: str | None = None) -> str:
    """Brand dei colori del preset: il suo campo «brand». Il preset neutro del plugin (default, brand demo) prende i
    colori del brand del canale quando il canale ne ha uno con ink, paper e accent (shorts.md, percorsi A e C)."""
    brand = str(preset.get("brand") or style)
    if brand == ytcore.BUILTIN_BRAND and channel:
        cb = ytcore.channel_brand(channel)
        cc = (ytcore.brand_tokens(cb) or {}).get("colors") or {}
        if cb != ytcore.BUILTIN_BRAND and all(cc.get(k) for k in ("ink", "paper", "accent")):
            return cb
    return brand


def preset_tokens(preset: dict, style: str, channel: str | None = None) -> dict:
    """Token dei colori per il preset (preset_brand). Con i colori del canale gli accenti che il suo brand non ha
    (accent_2, accent_3 del preset default) ricadono sul suo accento principale, mai sui colori del brand demo."""
    brand = preset_brand(preset, style, channel)
    tokens = ytcore.brand_tokens(brand) or {}
    if brand != str(preset.get("brand") or style):
        colors = dict(tokens.get("colors") or {})
        for spec in (preset.get("accents") or {}).values():
            if isinstance(spec, str) and spec.startswith("token:"):
                colors.setdefault(spec.split(":", 1)[1], colors["accent"])
        tokens = {**tokens, "colors": colors}
    return tokens


def available_presets() -> list[str]:
    names = {p.stem for d in [*_external_ass_dirs(), ASS_DIR] for p in d.glob("*.json")}
    return sorted(names)


def load_preset(name: str) -> dict:
    path = preset_path(name)
    if path is None:
        raise FileNotFoundError(f"Preset ASS '{name}' non trovato (brand esterni in brands_dirs, poi {ASS_DIR}; "
                                f"disponibili: {available_presets()})")
    preset = ytcore.read_json(path)
    preset["_path"] = str(path)
    return preset


def _safe_preset(name: str | None) -> dict | None:
    try:
        return load_preset(name) if name else None
    except (FileNotFoundError, ValueError):
        return None


def preset_font_dirs(preset: dict | None) -> list[Path]:
    """Cartelle dei font del preset: <brand>/ass/fonts e <brand>/fonts del brand esterno, poi assets/ass/fonts
    e assets/fonts del plugin."""
    dirs: list[Path] = []
    if preset and preset.get("_path"):
        pdir = Path(preset["_path"]).parent
        if pdir.resolve() != ASS_DIR.resolve():
            dirs += [pdir / "fonts", pdir.parent / "fonts"]
    if preset and preset.get("brand"):
        bd = ytcore.brand_dir(preset["brand"])
        if bd and ytcore.brand_is_external(preset["brand"]):
            dirs += [bd / "ass" / "fonts", bd / "fonts"]
    out: list[Path] = []
    for d in [*dirs, ASS_FONTS, FONTSDIR_FALLBACK]:
        if d not in out and d.is_dir():
            out.append(d)
    return out


def _color(spec: str | None, tokens: dict, accent: str | None = None) -> str | None:
    """'token:ink' | '#rrggbb' | 'accent' → '#rrggbb'."""
    if spec is None:
        return None
    if spec == "accent":
        return accent
    if spec.startswith("token:"):
        key = spec.split(":", 1)[1]
        val = tokens.get("colors", {}).get(key)
        if not val:
            raise KeyError(f"Colore '{key}' assente nei token del brand")
        return val
    return spec


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    """#rrggbb + alpha (0 = opaco, 255 = trasparente) → &HAABBGGRR."""
    h = hex_rgb.lstrip("#")
    r_hex, g_hex, b_hex = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b_hex}{g_hex}{r_hex}".upper()


def _ass_ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "＼").replace("{", "(").replace("}", ")")


class TextMeasure:
    """Larghezza in pixel PlayRes di una stringa con il font del preset (PIL), per evitare tagli."""

    def __init__(self, font_file: str, size: int, outline: float, scale_x: float = 1.0,
                 dirs: list[Path] | None = None):
        from PIL import ImageFont

        path = next((d / font_file for d in (dirs or [ASS_FONTS, FONTSDIR_FALLBACK]) if (d / font_file).exists()),
                    None)
        if path is None:
            raise FileNotFoundError(f"font {font_file} non trovato in {', '.join(str(d) for d in dirs or [ASS_FONTS])}")
        self.font = ImageFont.truetype(str(path), 200)
        asc, desc = self.font.getmetrics()
        # libass: Fontsize ≈ altezza ascender+descender (compat VSFilter), PIL: em
        self.k = size / (asc + desc)
        self.outline = outline
        self.scale_x = scale_x

    def __call__(self, text: str) -> float:
        return self.font.getlength(text) * self.k * self.scale_x + 2 * self.outline


def _case(text: str, conf: dict) -> str:
    if conf.get("uppercase"):
        return text.upper()
    if conf.get("lowercase"):
        return text.lower()
    return text


def _chunk_words(words: list[dict], conf: dict, measure: TextMeasure, max_w: float) -> list[list[dict]]:
    """Blocchi di 2–4 parole: si chiude su punteggiatura, pausa ≥0.3 s, cambio speaker o taglio."""
    target, max_n = int(conf.get("chunk_words", 3)), int(conf.get("max_chunk_words", 4))
    max_chars = int(conf.get("max_line_chars", 22)) * 2
    chunks, cur = [], []
    for k, w in enumerate(words):
        if cur:
            prev = cur[-1]
            brk = (w["start"] - prev["end"] >= 0.3 or w.get("speaker") != prev.get("speaker")
                   or w.get("seg") != prev.get("seg") or SENT_END.search(prev["w"]) or SOFT_PUNCT.search(prev["w"]))
            text_len = len(" ".join(x["w"] for x in cur + [w]))
            full = len(cur) >= target or text_len > max_chars
            if brk or full:
                # non chiudere su una parola debole: se possibile portala nel blocco successivo
                if not brk and norm(prev["w"]) in WEAK_WORDS and len(cur) > 1:
                    moved = cur.pop()
                    chunks.append(cur)
                    cur = [moved]
                elif not brk and norm(prev["w"]) in WEAK_WORDS and len(cur) < max_n:
                    pass  # blocco da 1 parola debole: allunga
                else:
                    chunks.append(cur)
                    cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    # blocchi lampo (<0.35 s) uniti al vicino se c'è spazio
    merged: list[list[dict]] = []
    for ch in chunks:
        dur = ch[-1]["end"] - ch[0]["start"]
        if merged and dur < 0.35 and len(merged[-1]) + len(ch) <= max_n and \
                ch[0].get("speaker") == merged[-1][-1].get("speaker") and ch[0]["start"] - merged[-1][-1]["end"] < 0.3:
            merged[-1] = merged[-1] + ch
        else:
            merged.append(ch)
    return merged


def _chunk_lines(chunk: list[dict], conf: dict, measure: TextMeasure, max_w: float) -> tuple[list[list[int]], float]:
    """Indici delle parole per riga (1 o 2 righe) + fattore di scala se una parola da sola non entra."""
    texts = [_case(w["w"], conf) for w in chunk]
    if measure(" ".join(texts)) <= max_w or len(chunk) == 1:
        width = measure(" ".join(texts))
        return [list(range(len(chunk)))], min(1.0, max_w / width) if width > max_w else 1.0
    best, best_score = None, -1e9
    for j in range(1, len(chunk)):
        w1, w2 = measure(" ".join(texts[:j])), measure(" ".join(texts[j:]))
        score = -abs(w1 - w2) / max_w - (3 if norm(chunk[j - 1]["w"]) in WEAK_WORDS else 0)
        score -= 5 * (max(w1, w2) > max_w)
        if score > best_score:
            best, best_score = j, score
    lines = [list(range(best)), list(range(best, len(chunk)))]
    widest = max(measure(" ".join(texts[i] for i in ln)) for ln in lines)
    return lines, min(1.0, max_w / widest)


def hook_lines(hook: str, preset: dict, tokens: dict | None = None, width: int = 1080) -> list[str]:
    """Righe del hook (a capo misurato col font reale, ≤ max_lines)."""
    hk = preset.get("hook", {})
    text = _case(" ".join(hook.split()), hk)
    if hk.get("prefix"):
        text = hk["prefix"] + text  # lo slash occupa spazio nella prima riga
    measure = TextMeasure(hk["font_file"], hk["size"], hk.get("box_padding", 16), dirs=preset_font_dirs(preset))
    units = [{"words": [{"w": t}], "text": t, "start": 0, "end": 0} for t in text.split()]
    lines = split_lines(units, width - 2 * int(hk["margin_lr"]), int(hk.get("max_lines", 3)), measure=measure) or [text]
    if hk.get("prefix") and lines and lines[0].startswith(hk["prefix"]):
        lines[0] = lines[0][len(hk["prefix"]):]
    return lines


def build_ass(words: list[dict], preset: dict, tokens: dict, *, accent: str | None = None,
              hook: str | None = None, duration: float | None = None, position: str = "bottom",
              accent_word: str | None = None, play_res: tuple[int, int] = (1080, 1920),
              hook_margin_v: int | None = None, caption_margin_v: int | None = None) -> tuple[str, dict]:
    """Script ASS completo (stili + eventi). Ritorna (testo, info).
    hook_margin_v / caption_margin_v: posizioni calcolate da yt-clips per non coprire i volti."""
    W, H = play_res
    cap, hk = preset["caption"], preset.get("hook", {})
    accent_name = accent or preset.get("default_accent")
    accents = preset.get("accents", {})
    if accent_name not in accents:
        raise ValueError(f"Accento '{accent_name}' non previsto dal preset {preset['name']} ({list(accents)})")
    accent_hex = _color(accents[accent_name], tokens)
    primary = _color(cap["primary"], tokens)
    outline_c = _color(cap["outline_color"], tokens)
    shadow_c = _color(cap.get("shadow_color") or cap["outline_color"], tokens)
    active_hex = _color(cap.get("active_color"), tokens, accent_hex)
    # accent_uses conta solo per i preset "un accento per composizione" (accent_once); un preset a karaoke lo usa sulla parola attiva
    info: dict[str, Any] = {"preset": preset["name"], "accent": accent_name, "accent_uses": 0, "chunks": 0,
                            "scaled_chunks": 0, "hook_lines": 0}

    align, margin_v = int(cap["alignment"]), int(caption_margin_v if caption_margin_v is not None else cap["margin_v"])
    if position == "center":
        align, margin_v = 5, 0
    info["caption_margin_v"] = margin_v
    margin_lr = int(cap["margin_lr"])
    max_w = W - 2 * margin_lr
    scale_active = int(cap.get("active_scale", 100))
    measure = TextMeasure(cap["font_file"], cap["size"], cap["outline"], scale_active / 100,
                          dirs=preset_font_dirs(preset))

    styles = [
        ("Caption", cap["font"], cap["size"], ass_color(primary), ass_color(active_hex or primary),
         ass_color(outline_c), ass_color(shadow_c, int(cap.get("shadow_alpha", 0))), int(cap.get("bold", 0)),
         1, cap["outline"], cap.get("shadow", 0), align, margin_lr, margin_lr, margin_v),
    ]
    if hook:
        box = _color(hk["box_color"], tokens)
        hook_mv = int(hook_margin_v if hook_margin_v is not None else hk["margin_v"])
        info["hook_margin_v"] = hook_mv
        styles.append(("Hook", hk["font"], hk["size"], ass_color(_color(hk["primary"], tokens)), ass_color(box),
                       ass_color(box), ass_color(box, 255), int(hk.get("bold", 0)), 3, hk.get("box_padding", 16), 0,
                       int(hk["alignment"]), int(hk["margin_lr"]), int(hk["margin_lr"]), hook_mv))

    lines = [
        "[Script Info]", "; Generato da yt-captions (YouTube Producer)", "ScriptType: v4.00+",
        f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
    ]
    for (name, font, size, c1, c2, c3, c4, bold, bstyle, outl, shad, al, ml, mr, mv) in styles:
        lines.append(f"Style: {name},{font},{size},{c1},{c2},{c3},{c4},{bold},0,0,0,100,100,0,0,{bstyle},"
                     f"{outl},{shad},{al},{ml},{mr},{mv},1")
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    inactive_alpha = int(cap.get("inactive_alpha", 0))
    accent_once = preset.get("accent_once", False)
    accent_budget = 1 if accent_once else math.inf
    hook_uses_accent = bool(hook and hk.get("prefix") and hk.get("prefix_color"))
    if accent_once and hook_uses_accent and not accent_word:
        accent_budget = 0  # lo slash del hook consuma l'unico accento
    accent_word_n = norm(accent_word) if accent_word else None

    chunks = _chunk_words(words, cap, measure, max_w)
    info["chunks"] = len(chunks)
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else math.inf
        ch_start = ch[0]["start"]
        ch_end = min(max(ch[-1]["end"] + 0.25, ch_start + 0.5), nxt)
        if nxt - ch[-1]["end"] < 0.6:
            ch_end = nxt  # niente buchi brevi: il blocco resta fino al successivo
        if duration is not None:
            ch_end = min(ch_end, duration)
        if ch_end <= ch_start:
            continue
        line_idx, fit = _chunk_lines(ch, cap, measure, max_w)
        if fit < 1.0:
            info["scaled_chunks"] += 1
        texts = [_ass_escape(_case(w["w"], cap)) for w in ch]
        green_k = None
        if accent_word_n and accent_budget > 0:
            for k, w in enumerate(ch):
                if norm(w["w"]) == accent_word_n:
                    green_k, accent_budget = k, accent_budget - 1
                    info["accent_uses"] += 1
                    break
        for k, w in enumerate(ch):
            t0 = ch_start if k == 0 else w["start"]
            t1 = ch[k + 1]["start"] if k + 1 < len(ch) else ch_end
            if t1 <= t0:
                continue
            parts = []
            for li, ln in enumerate(line_idx):
                seg = []
                for j in ln:
                    tok = texts[j]
                    if j == green_k:
                        tok = "{\\c" + ass_color(_color(accents[accent_name], tokens)) + "}" + tok + "{\\r}"
                    if j == k:
                        sc = round(scale_active * fit)
                        tags = f"\\fscx{sc}\\fscy{sc}" if sc != 100 else ""
                        if active_hex and accent_budget != 0 and not accent_once:
                            tags += "\\c" + ass_color(active_hex)
                        seg.append("{" + tags + "}" + tok + "{\\r}" if tags else tok)
                    elif inactive_alpha:
                        seg.append("{\\1a&H%02X&\\3a&H%02X&}" % (inactive_alpha, inactive_alpha) + tok + "{\\r}")
                    else:
                        seg.append(tok)
                parts.append(" ".join(seg))
            prefix = "{\\fscx%d\\fscy%d}" % (round(fit * 100), round(fit * 100)) if fit < 1.0 else ""
            # \r azzera anche la scala: la riapplico dopo ogni reset
            body = "\\N".join(parts)
            if fit < 1.0:
                body = body.replace("{\\r}", "{\\r\\fscx%d\\fscy%d}" % (round(fit * 100), round(fit * 100)))
            lines.append(f"Dialogue: 1,{_ass_ts(t0)},{_ass_ts(t1)},Caption,,0,0,0,,{prefix}{body}")

    if hook:
        hlines = hook_lines(hook, preset, tokens, W)
        info["hook_lines"] = len(hlines)
        hdur = min(float(hk.get("duration", 3.0)), duration or math.inf)
        text = "\\N".join(_ass_escape(x) for x in hlines)
        if hk.get("prefix"):
            pc = _color(hk.get("prefix_color"), tokens)
            if pc and accent_once and info["accent_uses"] == 0 and not accent_word:
                text = "{\\c" + ass_color(pc) + "}" + _ass_escape(hk["prefix"]) + "{\\r}" + text
                info["accent_uses"] += 1
            else:
                text = _ass_escape(hk["prefix"]) + text
        lines.append(f"Dialogue: 2,{_ass_ts(0)},{_ass_ts(hdur)},Hook,,0,0,0,,{{\\fad(120,220)}}{text}")
    return "\n".join(lines) + "\n", info


def fonts_dir(preset: dict | None = None) -> Path:
    """Cartella font per ffmpeg (subtitles=…:fontsdir=…): istanze statiche se presenti.

    libass legge UNA sola cartella: se il preset viene da un brand esterno con font propri, si prepara in
    <studio>/cache/ass-fonts/<preset>-<hash>/ una copia unita (font del brand + font del plugin)."""
    base = ASS_FONTS if any(ASS_FONTS.glob("*.ttf")) else FONTSDIR_FALLBACK
    dirs = preset_font_dirs(preset)
    extra = [d for d in dirs if d not in (ASS_FONTS, FONTSDIR_FALLBACK)
             and any(f.suffix.lower() in (".ttf", ".otf") for f in d.iterdir())]
    if not extra:
        return base
    import shutil

    key = hashlib.sha1("|".join(str(d) for d in [*extra, base]).encode()).hexdigest()[:8]
    merged = ytcore.CACHE / "ass-fonts" / f"{preset.get('name', 'preset')}-{key}"
    merged.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    for d in [*extra, base]:                 # il brand vince sui nomi uguali
        for f in sorted(d.iterdir()):
            # niente font variabili: libass ne usa solo l'istanza di default (servono le statiche)
            if f.suffix.lower() not in (".ttf", ".otf") or f.name in seen or "[" in f.name or "variable" in f.stem.lower():
                continue
            seen.add(f.name)
            dst = merged / f.name
            if not dst.exists() or dst.stat().st_size != f.stat().st_size or dst.stat().st_mtime < f.stat().st_mtime:
                shutil.copy2(f, dst)
    for f in merged.iterdir():               # via i font spariti dalle sorgenti
        if f.name not in seen:
            f.unlink(missing_ok=True)
    return merged


def make_ass(workdir: Path, rng: tuple[float, float] | None, *, style: str, out: Path, words_path=None,
             timeline_arg: str | None = "none", hook: str | None = None, accent: str | None = None,
             drop_fillers: bool = True, position: str = "bottom", accent_word: str | None = None,
             hook_margin_v: int | None = None, caption_margin_v: int | None = None,
             warnings: list | None = None) -> dict:
    """API per clips.py: ASS del range [a, b] (sul timeline scelto), tempi riportati a 0."""
    warnings = warnings if warnings is not None else []
    words, _ = load_words(workdir, words_path)
    timeline, _ = resolve_timeline(workdir, timeline_arg, warnings)
    words = map_words(words, timeline, main_source_key(workdir))
    duration = None
    if rng:
        words = apply_range(words, rng[0], rng[1], rebase=True)
        duration = rng[1] - rng[0]
    n_scope = len(words)
    if drop_fillers:
        words = [w for w in words if not is_filler(w)]
    # unità MRR/ARR confermate all'ascolto (analysis/resolutions.json): mai bruciare «MRAR» se c'è la risposta
    resolutions, _ = load_resolutions(workdir / "analysis" / "resolutions.json")
    words = [dict(w) for w in words]
    units_open = resolve_words_inplace(words, resolutions)
    if units_open:
        warnings.append(f"{units_open} unità (MRR/ARR) non confermate nella clip: testo dell'ASR "
                        f"(analysis/resolutions.json)")
    preset = load_preset(style)
    pj = Path(workdir) / "project.json"
    tokens = preset_tokens(preset, style, ytcore.load_project(workdir).get("channel") if pj.is_file() else None)
    text, info = build_ass(words, preset, tokens, accent=accent, hook=hook, duration=duration,
                           position=position, accent_word=accent_word, hook_margin_v=hook_margin_v,
                           caption_margin_v=caption_margin_v)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    info.update(words=len(words), path=str(out), fillers_dropped=n_scope - len(words), units_unconfirmed=units_open,
                discourse_kept=sum(1 for w in words if w.get("discourse") or w.get("filler_kind") == "discourse"))
    return info


# ── CLI ────────────────────────────────────────────────────────────────────
def _file_sig(paths: list[Path]) -> str:
    h = hashlib.sha1()
    for p in paths:
        h.update(str(p).encode())
        if p and p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-captions", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--format", default="srt", help="srt | vtt | ass | json (anche più formati: srt,vtt)")
    ap.add_argument("--timeline", default=None,
                    help="timeline di output (default edit/assembled.timeline.json se esiste) oppure 'none' = sorgente")
    ap.add_argument("--range", default=None, help="a,b: solo questo intervallo (sul timeline scelto); tempi riportati a 0")
    ap.add_argument("--no-rebase", action="store_true", help="con --range mantiene i tempi assoluti")
    ap.add_argument("--words", default=None, help="transcript alternativo (default analysis/transcript.words.json)")
    ap.add_argument("--style", default=None, help="preset ASS (default: quello del canale o del suo brand, altrimenti 'default')")
    ap.add_argument("--accent", default=None, help="ASS: accento del preset (nomi in «accents» del preset; default: default_accent)")
    ap.add_argument("--accent-word", default=None,
                    help="ASS, preset con accent_once: l'unico accento va su questa parola invece che sul prefisso del hook")
    ap.add_argument("--hook", default=None, help="ASS: testo hook (≤10 parole) nei primi 3 s, in alto")
    ap.add_argument("--position", default="bottom", choices=["bottom", "center"], help="ASS: posizione sottotitoli")
    ap.add_argument("--drop-fillers", action="store_true",
                    help="toglie esitazioni (ehm, eh…), ripetizioni e false partenze; mai i segnali discorsivi "
                         "(quindi, allora, cioè…). Per srt/vtt v2 equivale a --edit light (già il default)")
    ap.add_argument("--builder", choices=["v2", "v1"], default="v2",
                    help="srt/vtt: v2 = costruttore attuale (default); v1 = quello precedente, identico byte per byte")
    ap.add_argument("--edit", choices=["light", "verbatim"], default="light",
                    help="srt/vtt v2: light = senza esitazioni, false partenze e prime copie delle ripetizioni "
                         "(Netflix I.16; default); verbatim = tutto")
    ap.add_argument("--cps-target", type=float, default=None,
                    help=f"srt/vtt v2: obiettivo car/s (default {SIDECAR_RULES['target_cps']:g}; tetto "
                         f"{SIDECAR_RULES['ceiling_cps']:g})")
    ap.add_argument("--turn-marks", choices=["dialogue", "chained"], default="dialogue",
                    help="srt/vtt v2: «- » solo negli scambi rapidi a due (default) o a ogni cambio incatenato")
    ap.add_argument("--resolutions", default=None,
                    help="testi confermati all'ascolto (default analysis/resolutions.json)")
    ap.add_argument("--draft", action="store_true",
                    help="srt/vtt: scrive comunque una bozza <slug>.<lang>.draft.srt/.vtt se ci sono parole da "
                         "confermare (senza: consegna bloccata, exit 2)")
    ap.add_argument("--no-speaker-repair", action="store_true",
                    help="srt/vtt v2: non riparare i cambi di speaker in memoria")
    ap.add_argument("--lang", default=None, help="lingua nel nome file (default: language del transcript)")
    ap.add_argument("--out", default=None, help="file di output (solo con un formato)")
    ap.add_argument("--force", action="store_true", help="rigenera anche se aggiornato")
    args = ap.parse_args()

    warnings: list[str] = []
    try:
        workdir = ytcore.resolve_workdir(args.workdir)
        project = ytcore.load_project(workdir)
        formats = [f.strip().lower() for f in args.format.split(",") if f.strip()]
        bad = [f for f in formats if f not in ("srt", "vtt", "ass", "json")]
        if bad:
            ytcore.fail(f"Formato non supportato: {bad} (srt|vtt|ass|json)")
        if args.out and len(formats) > 1:
            ytcore.fail("--out vale solo con un formato")
        rng = parse_range(args.range)
        if args.hook and len(args.hook.split()) > 10:
            ytcore.fail(f"Hook di {len(args.hook.split())} parole: massimo 10")

        words_all, meta = load_words(workdir, args.words)
        timeline, tl_path = resolve_timeline(workdir, args.timeline, warnings)
        src_key = main_source_key(workdir)
        stats: dict = {}
        words = map_words(words_all, timeline, src_key, stats)
        lang = args.lang or meta.get("language") or "it"
        slug = project.get("slug") or workdir.name
        style = args.style or default_style(project.get("channel"))
        tl_name = "output" if timeline is not None else "source"
        res_path = Path(args.resolutions).expanduser() if args.resolutions else workdir / "analysis" / "resolutions.json"
        if args.resolutions and not res_path.exists():
            ytcore.fail(f"file delle risoluzioni mancante: {res_path}")
        resolutions, manual_slots = load_resolutions(res_path)

        inputs = [Path(meta["path"]), Path(__file__)] + ([tl_path] if tl_path else [])
        if meta.get("reflagged"):
            inputs.append(Path(__file__).with_name("transcribe.py"))
            warnings.append("transcript con lo schema vecchio dei flag: riclassificato in memoria "
                            "(yt-transcribe WORKDIR --reflag per aggiornare il file)")
        # parole nel perimetro dell'output: prima l'intervallo, poi (se richiesto) via i filler
        scope = apply_range(words, rng[0], rng[1], rebase=not args.no_rebase) if rng else words
        ws = [w for w in scope if not (args.drop_fillers and is_filler(w))]
        dropped_words = [w["w"] for w in scope if args.drop_fillers and is_filler(w)]
        discourse_kept = [w["w"] for w in ws if w.get("discourse") or w.get("filler_kind") == "discourse"]

        # ── sidecar srt/vtt col costruttore v2: costruito una volta per entrambi i formati ──
        side = None
        side_info: dict[str, Any] = {}
        side_formats = [f for f in formats if f in ("srt", "vtt")]
        if side_formats and args.builder == "v2":
            sw_all = [dict(w) for w in words_all]
            spk_rep = {"words_changed": 0}
            if not args.no_speaker_repair and any(w.get("speaker") for w in sw_all):
                spk_rep = repair_speakers(sw_all, project)
            sw = map_words(sw_all, timeline, src_key)
            if timeline is not None:
                for w in sw:
                    w["seg_start"], w["seg_end"] = timeline[w["seg"]]["out_start"], timeline[w["seg"]]["out_end"]
            if rng:
                sw = apply_range(sw, rng[0], rng[1], rebase=not args.no_rebase)
            rules = {"turn_marks": args.turn_marks}
            if args.cps_target:
                rules["target_cps"] = args.cps_target
            light = args.edit == "light" or args.drop_fillers
            gloss = caption_glossary(workdir, project)
            side = build_events(sw, rules, glossary=gloss, light=light, manual_review=manual_slots,
                                resolutions=resolutions)
            side_info = {"builder": "v2", "edit": "light" if light else "verbatim",
                         "fillers_dropped": len(side["dropped"]), "speaker_repair": spk_rep,
                         "normalized": sum(1 for x in side["log"] if not x["rule"].startswith("review")),
                         "review_slots": sum(1 for x in side["log"] if x["rule"].startswith("review")),
                         "review_open": len(side["review_open"]), "dialogue_events": side["dialogue_events"]}
            if side["review_open"] and not args.draft:
                open_rows = {}
                for x in side["review_open"]:
                    open_rows.setdefault(x["key"], {"key": x["key"], "t_source": round(x["t"], 2),
                                                    "ts_source": ytcore.fmt_ts(x["t"]), "asr": x["from"],
                                                    "placeholder": x["to"], "kind": x["rule"]})
                ytcore.fail(f"{len(open_rows)} parole da confermare all'ascolto (MRR/ARR o slot manuali): consegna dei "
                            f"sottotitoli bloccata. Ascolta (analysis/transcript.review.json), scrivi il testo in "
                            f"{res_path.name} → \"resolved\", oppure usa --draft per la bozza",
                            code=2, review_open=list(open_rows.values()), resolutions=str(res_path),
                            warnings=warnings)
            inputs += [res_path, workdir / "project.json", workdir / "analysis" / "glossary.json",
                       ytcore.channel_file(project.get('channel', ''), ".glossary.txt")]

        outputs: dict[str, Any] = {}
        reports: dict[str, Any] = {}
        tag = f"_{rng[0]:.2f}-{rng[1]:.2f}" if rng else ""
        draft_tag = ".draft" if (side and side["review_open"]) else ""
        for fmt in formats:
            if args.out:
                out = Path(args.out).expanduser()
                out = out if out.is_absolute() else Path.cwd() / out
            elif fmt in ("srt", "vtt"):
                out = (workdir / "shorts" / f"captions{tag}.{lang}{draft_tag}.{fmt}") if rng else \
                    workdir / "deliver" / f"{slug}.{lang}{draft_tag}.{fmt}"
            elif fmt == "ass":
                out = (workdir / "shorts" / f"captions{tag}.{style}.ass") if rng else workdir / "edit" / f"captions.{style}.ass"
            else:
                out = (workdir / "shorts" / f"captions{tag}.json") if rng else workdir / "edit" / "captions.json"
            if fmt in ("srt", "vtt") and args.builder == "v2":
                sig = signature(fmt, tl_name, rng, args.no_rebase, "v2", side_info.get("edit"), args.cps_target,
                                args.turn_marks, args.no_speaker_repair, lang, bool(draft_tag),
                                _file_sig([res_path]), signature(caption_glossary(workdir, project)))
            else:
                sig = signature(fmt, tl_name, rng, args.no_rebase, args.drop_fillers, style, args.accent,
                                args.accent_word, args.hook, args.position, lang,
                                *(["v1"] if fmt in ("srt", "vtt") else []),
                                *([_file_sig([res_path])] if fmt in ("ass", "json") and resolutions else []))
            extra_in = [preset_path(style) or ASS_DIR / f"{style}.json"] if fmt == "ass" else []
            if not args.force and up_to_date(workdir, [out], inputs + extra_in, sig):
                log(f"[{fmt}] aggiornato, salto: {out}")
                outputs[fmt] = str(out)
                reports[fmt] = "skipped (up to date)"
                continue

            if not ws and fmt not in ("srt", "vtt"):
                warnings.append(f"[{fmt}] nessuna parola nell'intervallo richiesto")
            if fmt in ("srt", "vtt") and args.builder == "v2":
                events = side["events"]
                if not events:
                    warnings.append(f"[{fmt}] nessuna parola nell'intervallo richiesto")
                (write_srt if fmt == "srt" else write_vtt)(events, out, *([lang] if fmt == "vtt" else []))
                rep = check_cues(events, {**SRT_RULES, **side["rules"],
                                          "max_cps": side["rules"]["target_cps"]})
                rep["readability"] = readability(events)
                rep.update(side_info)
                if side["review_open"]:
                    rep["draft"] = True
                    seen_keys: dict[str, dict] = {}
                    for x in side["review_open"]:
                        seen_keys.setdefault(x["key"], {"key": x["key"], "ts_source": ytcore.fmt_ts(x["t"]),
                                                        "asr": x["from"], "placeholder": x["to"]})
                    rep["review_open_list"] = list(seen_keys.values())[:60]
                if fmt == "vtt" and isinstance(reports.get("srt"), dict):   # stessi eventi: niente liste doppie
                    rep.pop("over_ceiling_events", None)
                    rep.pop("review_open_list", None)
                    rep["lists"] = "uguali a reports.srt"
                reports[fmt] = rep
                if rep["cps_over_ceiling"]:
                    warnings.append(f"[{fmt}] {rep['cps_over_ceiling']} eventi sopra {SIDECAR_RULES['ceiling_cps']:g} "
                                    f"car/s (parlato veloce, mai riscritto): elencati in reports.{fmt}.over_ceiling_events")
                if not rep["gate"]["pass"]:
                    warnings.append(f"[{fmt}] gate dei sottotitoli NON superato: {rep['gate']['blocking']}")
                if side["review_open"]:
                    warnings.append(f"[{fmt}] BOZZA: {len({x['key'] for x in side['review_open']})} parole da confermare "
                                    f"all'ascolto (segnaposto [[…]] nel testo); non consegnare")
            elif fmt in ("srt", "vtt"):
                if not ws:
                    warnings.append(f"[{fmt}] nessuna parola nell'intervallo richiesto")
                cues = build_cues_v1(ws)
                (write_srt if fmt == "srt" else write_vtt)(cues, out, *([lang] if fmt == "vtt" else []))
                reports[fmt] = check_cues(cues, SRT_RULES_V1)
                if reports[fmt]["cps_over"]:
                    warnings.append(f"[{fmt}] {reports[fmt]['cps_over']} eventi sopra 17 car/s (parlato veloce, "
                                    f"testo verbatim: max {reports[fmt]['max_cps']})")
            elif fmt == "json":
                wj = [dict(w) for w in ws]
                n_open = resolve_words_inplace(wj, resolutions)
                ytcore.write_json(out, remotion_captions(wj))
                reports[fmt] = {"captions": len(wj), "units_unconfirmed": n_open}
                if n_open:
                    warnings.append(f"[{fmt}] {n_open} unità (MRR/ARR) non confermate nel perimetro: testo dell'ASR")
            else:
                wa = [dict(w) for w in ws]
                n_open = resolve_words_inplace(wa, resolutions)
                preset = load_preset(style)
                tokens = preset_tokens(preset, style, project.get("channel"))
                dur = (rng[1] - rng[0]) if rng and not args.no_rebase else None
                text, info = build_ass(wa, preset, tokens, accent=args.accent, hook=args.hook, duration=dur,
                                       position=args.position, accent_word=args.accent_word)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text, encoding="utf-8")
                info["fontsdir"] = str(fonts_dir(preset))
                info["units_unconfirmed"] = n_open
                reports[fmt] = info
                if n_open:
                    warnings.append(f"[{fmt}] {n_open} unità (MRR/ARR) non confermate nel perimetro: testo dell'ASR")
            stamp(workdir, [out], sig)
            outputs[fmt] = str(out)
            log(f"[{fmt}] → {out}")

        if stats.get("dropped"):
            log(f"{stats['dropped']} parole cadono nei tagli, {stats.get('clipped', 0)} accorciate")
        # words = parole scritte negli output (solo quelle nell'intervallo con --range, senza i
        # filler tolti); words_timeline = tutte le parole portate sul timeline scelto
        ytcore.emit(True, outputs=outputs, timeline=tl_name, words=len(ws),
                    words_in_range=len(scope) if rng else None, words_timeline=len(words),
                    fillers_dropped=len(dropped_words), dropped_words=dropped_words[:50],
                    discourse_kept=len(discourse_kept), sidecar=side_info or None,
                    mapping=stats, range=list(rng) if rng else None, reports=reports, warnings=warnings,
                    burn_hint=(f"subtitles=<file.ass>:fontsdir={fonts_dir(_safe_preset(style))}"
                               if "ass" in formats else None))
    except (FileNotFoundError, ValueError, KeyError) as exc:
        ytcore.fail(str(exc), warnings=warnings)


if __name__ == "__main__":
    main()
