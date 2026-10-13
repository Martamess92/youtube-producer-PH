"""yt-transcribe — trascrizione locale (italiano) con tempi per PAROLA.

Uso:
  yt-transcribe WORKDIR                       # testo whisper.cpp large-v3-turbo (-l it, VAD Silero) + tempi Parakeet
  yt-transcribe WORKDIR --prompt-extra "Lovable, Claude Code"
  yt-transcribe WORKDIR --timing whisper      # tempi dai token whisper (pipeline precedente)
  yt-transcribe WORKDIR --prompt-budget 110   # prompt corto: più esitazioni trovate, nomi uguali
  yt-transcribe WORKDIR --engine parakeet     # A/B con Parakeet TDT v3 anche per il testo (niente prompt)
  yt-transcribe WORKDIR --force               # rifà anche se gli output sono aggiornati
  yt-transcribe WORKDIR --reflag              # riclassifica solo i flag del transcript esistente (niente ASR)

Input:  analysis/audio16k.wav (mono 16 kHz, da yt-ingest); facoltativi analysis/glossary.json (yt-glossary)
        e analysis/corrections.decisions.json (decisioni di yt-postcorrect, riapplicate).
Output: analysis/transcript.words.json  parole {i, w, start, end, p[, filler, filler_kind, false_start,
                                        discourse, fixed_from, postcorrect, unit_review, timing_guess,
                                        speaker]} + flags_version + postprocess_version
                                        + segmenti {i, start, end, text, w0, w1} (timeline source)
        analysis/transcript.srt         sottotitoli sul timeline del SORGENTE (≤2 righe × 42 car.)
        analysis/transcript.review.json lista d'ascolto: slot MRR/ARR, punti in cui whisper e Parakeet non
                                        concordano (prima numeri, nomi e sigle), sospetti di yt-postcorrect
        analysis/resolutions.json       modello da compilare DOPO l'ascolto (mai creato se esiste già)
        analysis/corrections.json       registro delle correzioni dei nomi applicate
Cache:  <studio_dir>/cache/transcripts/<sha256(audio)+engine+modello+prompt>.*  (output grezzi del motore)

Prompt whisper = suggerimento di disfluenze italiane + termini in ordine di priorità (lib/glossary.py):
glossary_extra e --prompt-extra, poi MRR/ARR se analysis/glossary.json ha fatti sulle unità, poi i
prompt_terms di analysis/glossary.json, poi il glossario del canale P1, P2 (P3 solo se l'episodio li nomina);
al massimo 480 caratteri (≈171 token) o --prompt-budget token, mai oltre 224 token; ripetuto in ogni finestra
con --carry-initial-prompt. Misurato su episodi di prova: lunghezza, ordine e stile del prompt non cambiano i
nomi in modo misurabile; contano i nomi dell'episodio, MRR/ARR e i termini del canale.

Tempi (default --timing auto = parakeet se installato): Parakeet TDT v3 gira sullo stesso audio, le parole di
whisper vengono allineate a quelle di Parakeet (finestra ±10 s) e ne prendono inizio e fine; le parole che
Parakeet non sente (quasi sempre «ehm») vanno sull'audio con voce tra le vicine e hanno "timing_guess": true.
Misurato su un episodio di prova: parole a più di 0,5 s dal tempo vero 23,6 % → 2,8 % (contro DTW), ~75 s in più
a episodio.

Post-processing: token → parole (gli spazi iniziali aprono una parola nuova, la punteggiatura
si attacca), tempi rimappati dal timeline compresso del VAD a quello originale, tempi Parakeet, eliminazione
delle allucinazioni (ripetizioni nel silenzio, eco del prompt, frasi tipiche "Sottotitoli a cura
di…"), correzione prudente dei nomi del glossario (es. Akme → Acme), riallineamento dei
bordi parola alle pause reali (±0,4 s), correzione vincolata dei nomi (yt-postcorrect, regole; --no-postcorrect
per saltarla), "unit_review": true sulle unità dopo una cifra (MRR/ARR: mai risolte in automatico),
controllo del tasso di esitazioni (avviso sotto 3/min), flag delle parole (knowledge 06 §4):
  "filler": true      solo esitazioni (ehm, eh, uhm, mmm; ah/oh isolate tra pause), prima copia
                      delle ripetizioni ("il il") e false partenze; filler_kind = hesitation |
                      repetition | false_start (le false partenze hanno anche "false_start": true)
  "discourse": true   segnali discorsivi (allora, quindi, cioè, tipo, praticamente, diciamo, insomma,
                      ecco, niente, comunque, vabbè, appunto, magari, boh; beh a inizio frase;
                      "nel senso", "voglio dire"), con regole di contesto ("un tipo di" = nome,
                      "tipo cinquanta" = qualificatore, "non ho fatto niente" = pronome). Mai tolti
                      in automatico: --drop-fillers e yt-clips render tolgono solo i filler.
Un transcript con lo schema vecchio dei flag viene riclassificato da solo al primo yt-transcribe
(senza rifare l'ASR); --reflag lo fa esplicitamente e riporta conteggi e parole cambiate.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

import ytcore as yc
import glossary as gl

PIPELINE_VERSION = 3          # cambia se cambia il modo di chiamare il motore (invalida la cache)
POSTPROCESS_VERSION = 2       # 2 = tempi Parakeet, post-correzione, slot unità, lista d'ascolto
DISFLUENT_HINT = gl.HINT
MAX_PROMPT_CHARS = gl.LEGACY_MAX_PROMPT_CHARS   # whisper: prompt max n_text_ctx/2 = 224 token
CACHE_DIR = yc.CACHE / "transcripts"
PARAKEET_MODEL_ENV = "YT_PARAKEET_MODEL"
PARAKEET_CHUNK_S = 300.0
PARAKEET_PARSER = "parser2"   # '▁' isolato apre una parola; bordi segmento in frame (×0,08 s)
ALIGN_MAX_DT = 10.0           # finestra dell'allineamento whisper↔Parakeet (2 s non bastavano)
HESITATION_MIN_PER_MIN = 3.0  # sotto questo tasso il prompt ha probabilmente soppresso le esitazioni
DIGITAL_SILENCE_DB = -100.0   # frame a zero digitale (−140 dB): esclusi dal calcolo del fondo

# ── Flag delle parole (FLAGS_VERSION 2, knowledge 06 §4) ────────────────────
# "filler": true SOLO per ciò che si può togliere senza perdere significato:
#   hesitation  esitazioni non lessicali (ehm, eh, uhm, mmm…; ah/oh solo se isolate tra due pause)
#   repetition  balbettio: la PRIMA copia di parole funzionali ripetute ("il il", "che che",
#               "ho fatto ho fatto")
#   false_start parola troncata ("pro-") e l'eventuale parola ripetuta subito dopo; anche "false_start": true
# "discourse": true per i segnali discorsivi che danno struttura (allora, quindi, cioè, tipo…):
#   mai tolti in automatico (yt-captions --drop-fillers e yt-clips render li tengono).
# Una parola non è mai insieme filler e discourse. "quindi" è sempre discourse.
FLAGS_VERSION = 2
HESITATIONS = {"ehm", "eh", "ehh", "uhm", "um", "umh", "uh", "mmm", "mm", "mh", "hmm", "hm", "mmh", "ehmm"}
HESITATION_RE = re.compile(r"^(e+h*m+|e+h+|u+h*m+|u+h+|m{2,}h*|m+h+m*|h+m+)$")
INTERJECTIONS = {"ah", "oh", "ahh", "ohh", "aah", "ooh", "ahah"}       # filler solo se isolate tra pause
DISCOURSE_MARKERS = {"allora", "quindi", "cioè", "cioé", "tipo", "praticamente", "diciamo", "insomma",
                     "ecco", "niente", "comunque", "vabbè", "vabbe", "vabbé", "appunto", "magari", "boh"}
SENTENCE_INITIAL_MARKERS = {"beh", "be", "bè", "bé", "bah"}            # discourse solo a inizio frase
DISCOURSE_PHRASES = {("nel", "senso"), ("voglio", "dire"), ("va", "be"), ("va", "bè"), ("va", "beh"),
                     ("va", "bé")}
DISCOURSE = DISCOURSE_MARKERS | SENTENCE_INITIAL_MARKERS | INTERJECTIONS | {"eh"}
# Ripetizioni: solo parole funzionali (i raddoppi espressivi "piano piano", "caldo caldo",
# "no, no" restano parole vere).
STUTTER_WORDS = {
    "il", "lo", "la", "i", "gli", "le", "l", "un", "uno", "una", "di", "a", "da", "in", "con", "su", "per",
    "tra", "fra", "e", "o", "ma", "che", "se", "non", "mi", "ti", "si", "ci", "vi", "ne", "del", "della",
    "dei", "degli", "delle", "dello", "al", "alla", "ai", "agli", "alle", "allo", "dal", "dalla", "nel",
    "nella", "nei", "nelle", "sul", "sulla", "è", "ho", "ha", "hai", "hanno", "abbiamo", "sono", "era",
    "io", "tu", "lui", "lei", "noi", "voi", "loro", "questo", "questa", "quel", "quella", "quello",
    "come", "cosa", "perché", "quando", "anche", "poi", "più", "c'è", "l'ho", "un'", "ed", "ad",
}
REDUP_OK = {"sì", "si", "no", "via", "ciao", "bravo", "brava", "piano", "così", "dai", "ok", "okay",
            "certo", "bene", "grazie", "esatto", "vero", "pian"}
NUMBER_RE = re.compile(
    r"^(\d[\d.,]*%?|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|"
    r"quindici|sedici|diciassette|diciotto|diciannove|venti|vent\w{1,4}|trenta|trent\w{1,4}|"
    r"quaranta|quarant\w{1,4}|cinquanta|cinquant\w{1,4}|sessanta|sessant\w{1,4}|settanta|settant\w{1,4}|"
    r"ottanta|ottant\w{1,4}|novanta|novant\w{1,4}|cento|\w{2,8}cento|mille|\w{2,8}mila|mezz[oa]|metà)$")
TIPO_NOUN_PREV = {"un", "uno", "il", "lo", "quel", "quello", "questo", "che", "ogni", "stesso", "qualche",
                  "nessun", "nessuno", "altro", "del", "dello", "nel", "al", "dal", "sul", "bel", "strano",
                  "certo", "tal", "quale", "mio", "tuo", "suo", "nostro", "vostro", "primo", "secondo"}
ALLORA_TEMPORAL_PREV = {"da", "ad", "a", "fino", "fin", "di", "sin", "già", "dall"}
NIENTE_CONTENT_PREV = {"non", "per", "di", "da", "nel", "quasi", "proprio", "assolutamente", "mai", "nessuno"}
NIENTE_CONTENT_NEXT = {"di", "da", "più", "altro", "male", "meno", "affatto"}
NEGATIONS = {"non", "mai", "nessuno", "né", "senza"}
PAUSE_S = 0.12              # gap tra parole che conta come pausa (dopo l'allineamento alle pause reali)
TRUNCATED_RE = re.compile(r"[\w'][-–—]+[\"»”)]*$")

# Frasi che whisper inventa nel silenzio (dataset di sottotitoli): sempre scartate.
HARD_HALLUCINATIONS = re.compile(
    r"amara\.org|\bqtss\b|sottotitoli (creati|e revisione|a cura)|sottotitolato da|"
    r"revisione a cura di|grazie per la visione", re.I)
PUNCT_ONLY = re.compile(r"^[\s\.,;:!\?…\-–—\"'«»()\[\]]+$")
SPECIAL_TOKEN = re.compile(r"^\s*(\[_[A-Z]+_?\d*\]|<\|[^|]*\|>)\s*$")
SENT_END = (".", "?", "!", "…")


# ── Utility ─────────────────────────────────────────────────────────────────
def norm(word: str) -> str:
    """Minuscolo senza punteggiatura (mantiene accenti e apostrofi interni)."""
    w = word.lower().strip()
    w = re.sub(r"[^\w']+", "", w)
    return w.strip("'")


def wav_info(path: Path) -> tuple[int, int, int, float]:
    with wave.open(str(path), "rb") as fh:
        rate, ch, width, n = fh.getframerate(), fh.getnchannels(), fh.getsampwidth(), fh.getnframes()
    return rate, ch, width, n / float(rate)


def sha256_audio(path: Path) -> str:
    return yc.sha256_file(path)


class Energy:
    """Energia RMS a 10 ms dell'audio 16 kHz, per riconoscere silenzi e pause reali."""

    HOP = 160  # 10 ms a 16 kHz

    def __init__(self, path: Path):
        with wave.open(str(path), "rb") as fh:
            n = fh.getnframes()
            frames = []
            block = self.HOP * 6000  # ~1 min per blocco, per non caricare tutto in float
            while True:
                raw = fh.readframes(block)
                if not raw:
                    break
                x = np.frombuffer(raw, dtype=np.int16)
                m = len(x) // self.HOP
                if m == 0:
                    break
                x = x[: m * self.HOP].astype(np.float32).reshape(m, self.HOP) / 32768.0
                frames.append(np.sqrt(np.mean(x * x, axis=1)))
        rms = np.concatenate(frames) if frames else np.zeros(1)
        self.db = 20 * np.log10(rms + 1e-7)
        # Silenzio digitale (pacchetti persi, inserti a zero): se è ≥1 % dei frame lo escludo dalle
        # statistiche, altrimenti con ≥10 % il fondo diventa −140 dB, la soglia −86 dB e il rumore della
        # stanza conta come voce (niente pause per lo snap, filtro allucinazioni spento).
        live = self.db > DIGITAL_SILENCE_DB
        self.digital_silence = float(1.0 - live.mean()) if self.db.size else 0.0
        basis = self.db[live] if self.digital_silence >= 0.01 and live.sum() >= 100 else self.db
        self.floor = float(np.percentile(basis, 10))
        speechy = basis[basis > self.floor + 12]
        self.speech = float(np.median(speechy)) if speechy.size else self.floor + 20
        # soglia "voce": a metà strada tra rumore di fondo e voce tipica, almeno +8 dB sul fondo
        self.thr = max(self.floor + 8.0, self.floor + 0.45 * (self.speech - self.floor))
        self.voiced = self.db > self.thr
        self.n = len(self.db)
        log(f"energia: fondo {self.floor:.1f} dBFS, voce {self.speech:.1f} dBFS, soglia {self.thr:.1f} dBFS"
            + (f", silenzio digitale {100 * self.digital_silence:.1f} % (escluso)" if basis is not self.db else ""))

    def voiced_ratio(self, a: float, b: float) -> float:
        i0, i1 = max(0, int(a * 100)), min(self.n, int(b * 100) + 1)
        return float(self.voiced[i0:i1].mean()) if i1 > i0 else 0.0

    def pauses(self, a: float, b: float, min_len: float = 0.15) -> list[tuple[float, float]]:
        """Pause (frame non voce consecutivi ≥ min_len) dentro [a, b]."""
        i0, i1 = max(0, int(a * 100)), min(self.n, int(b * 100) + 1)
        out, i = [], i0
        while i < i1:
            if not self.voiced[i]:
                j = i
                while j < i1 and not self.voiced[j]:
                    j += 1
                if (j - i) / 100 >= min_len:
                    out.append((i / 100, j / 100))
                i = j
            else:
                i += 1
        return out


def log(*parts) -> None:
    yc.log(*parts)


# ── Prompt e chiave di cache ────────────────────────────────────────────────
def build_prompt(project: dict, workdir: Path, extra: str | None, budget: int | None = None,
                 glossary_doc: dict | None = None) -> tuple[str, list[str], list[str], dict]:
    """Prompt a priorità (lib/glossary.py). Ritorna (prompt, termini usati, termini scartati, info)."""
    return gl.build_prompt(project, workdir, extra, budget=budget, glossary_doc=glossary_doc)


def build_prompt_legacy(project: dict, workdir: Path, extra: str | None) -> tuple[str, list[str], list[str]]:
    """Costruttore della pipeline precedente (pipeline 3, solo caratteri, canale in ordine di file): serve solo a
    riconoscere come aggiornati i transcript fatti allora. Ritorna (prompt, usati, scartati)."""
    episode = list(project.get("glossary_extra") or [])
    if extra:
        episode += [t.strip() for t in re.split(r"[,\n;]+", extra) if t.strip()]
    channel = yc.glossary_terms(project.get("channel", ""), workdir / "glossary.txt")
    terms, seen = [], set()
    for t in episode + channel:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            terms.append(t)
    used, dropped = [], []
    for t in terms:
        candidate = f"{DISFLUENT_HINT} {', '.join(used + [t])}."
        (used if len(candidate) <= MAX_PROMPT_CHARS else dropped).append(t)
    prompt = f"{DISFLUENT_HINT} {', '.join(used)}." if used else DISFLUENT_HINT
    return prompt, used, dropped


def cache_key(audio_sha: str, engine: str, model: Path, prompt: str, lang: str) -> str:
    size = model.stat().st_size if model.exists() else 0
    blob = json.dumps([PIPELINE_VERSION, audio_sha, engine, model.name, size, prompt, lang])
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


# ── Esecuzione con heartbeat ────────────────────────────────────────────────
def run_logged(cmd: list, logfile: Path, label: str, total_s: float | None = None) -> float:
    """Lancia il motore con stdout+stderr nel log; ogni 20 s stampa l'avanzamento su stderr."""
    logfile.parent.mkdir(parents=True, exist_ok=True)
    log("$", " ".join(yc._q(str(c)) for c in cmd))
    t0 = time.time()
    with open(logfile, "w") as fh:
        proc = subprocess.Popen([str(c) for c in cmd], stdout=fh, stderr=subprocess.STDOUT, text=True)
        last = t0
        while proc.poll() is None:
            time.sleep(1.0)
            if time.time() - last >= 20:
                last = time.time()
                log(f"  {label}: {int(last - t0)} s … {progress_hint(logfile, total_s)}")
    elapsed = time.time() - t0
    if proc.returncode != 0:
        tail = logfile.read_text(errors="replace")[-2500:]
        raise RuntimeError(f"{label} fallito (exit {proc.returncode}). Coda del log {logfile}:\n{tail}")
    return elapsed


def progress_hint(logfile: Path, total_s: float | None) -> str:
    try:
        with open(logfile, "rb") as fh:
            fh.seek(max(0, logfile.stat().st_size - 6000))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    m = re.findall(r"progress =\s*(\d+)%", tail)
    if m:
        return f"{m[-1]}%"
    m = re.findall(r"\[(\d\d):(\d\d):(\d\d)\.\d+ -->", tail)
    if m and total_s:
        h, mi, s = map(int, m[-1])
        return f"{yc.fmt_ts(h * 3600 + mi * 60 + s, 'yt')} / {yc.fmt_ts(total_s, 'yt')}"
    return ""


# ── whisper.cpp ─────────────────────────────────────────────────────────────
def whisper_version() -> str:
    real = os.path.realpath(yc.WHISPER_CLI)
    m = re.search(r"/whisper\.cpp/([\d.]+)/", real)
    return m.group(1) if m else "?"


def run_whisper(audio: Path, model: Path, prompt: str, lang: str, threads: int,
                workdir: Path, key: str, duration: float) -> tuple[Path, Path, dict]:
    """Esegue whisper-cli e salva in cache JSON completo (-ojf) + segmenti VAD dal log."""
    if not yc.which(yc.WHISPER_CLI):
        raise RuntimeError(f"whisper-cli non trovato: {yc.WHISPER_CLI}")
    if not yc.VAD_MODEL.exists():
        raise RuntimeError(f"modello VAD mancante: {yc.VAD_MODEL}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    logfile = workdir / "logs" / "transcribe.whisper.log"
    with tempfile.TemporaryDirectory(dir=CACHE_DIR, prefix=".tmp-") as tmp:
        base = Path(tmp) / "out"
        cmd = [yc.WHISPER_CLI, "-m", model, "-f", audio, "-l", lang, "-t", threads,
               "--vad", "-vm", yc.VAD_MODEL,
               "--prompt", prompt, "--carry-initial-prompt",
               "-ojf", "-pp", "-of", base]
        elapsed = run_logged(cmd, logfile, "whisper", duration)
        out = base.with_suffix(".json")
        if not out.exists():
            raise RuntimeError(f"whisper-cli non ha prodotto {out.name} (vedi {logfile})")
        vad = parse_vad_segments(logfile.read_text(errors="replace"))
        raw_dst = CACHE_DIR / f"{key}.whisper.json"
        os.replace(out, raw_dst)
    meta = {"engine": "whisper", "engine_version": whisper_version(), "model": model.name,
            "elapsed_s": round(elapsed, 1), "vad_segments": vad, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    meta_dst = CACHE_DIR / f"{key}.meta.json"
    yc.write_json(meta_dst, meta)
    return raw_dst, meta_dst, meta


def parse_vad_segments(text: str) -> list[list[float]]:
    """Righe 'vad_segment_info' del log di whisper.cpp → [[orig_start, orig_end, vad_start, vad_end]]."""
    rx = re.compile(r"vad_segment_info: orig_start: ([\d.]+), orig_end: ([\d.]+), "
                    r"vad_start: ([\d.]+), vad_end: ([\d.]+)")
    return [[float(x) for x in m.groups()] for m in rx.finditer(text)]


def vad_mapper(vad: list[list[float]]):
    """Funzione tempo-processato → tempo-originale.

    whisper.cpp con --vad concatena i tratti di voce (+0.1 s di sovrapposizione e 0.1 s di
    silenzio tra un tratto e l'altro) e rimappa solo i tempi dei SEGMENTI: i token restano
    sul timeline compresso. Ricostruiamo la stessa tabella (src/whisper.cpp v1.9.5,
    whisper_vad) tenendo lineare anche la coda di sovrapposizione, che è audio reale.
    """
    if not vad:
        return lambda t: t
    pts: list[tuple[float, float]] = []
    for i, (os_, oe, vs, ve) in enumerate(vad):
        pts += [(vs, os_), (ve, oe)]
        if i + 1 < len(vad):
            ov = max(0.0, min(0.2, vad[i + 1][2] - ve - 0.10))
            pts.append((ve + ov, oe + ov))
    pts.sort()
    P = np.array([p[0] for p in pts])
    O = np.maximum.accumulate(np.array([p[1] for p in pts]))  # monotono anche con tratti sovrapposti
    keep = np.concatenate([[True], np.diff(P) > 0])
    P, O = P[keep], O[keep]
    return lambda t: float(np.interp(t, P, O))


def tokens_need_mapping(data: dict, vad: list[list[float]]) -> bool:
    """True se i token sono sul timeline compresso dal VAD (whisper.cpp 1.9.5).

    Salvaguardia per versioni future che rimappassero anche i token: se l'inizio di ogni
    segmento (già rimappato) coincide col primo token mentre il VAD sposta i tempi di
    oltre 1 s, i token sono già originali e non vanno rimappati una seconda volta.
    """
    if not vad:
        return False
    shift = max(os_ - vs for os_, _, vs, _ in vad)
    if shift < 1.0:
        return True  # spostamento trascurabile: rimappare è comunque innocuo
    diffs = []
    for seg in data.get("transcription", []):
        toks = [t for t in seg.get("tokens", []) if t.get("text") and not SPECIAL_TOKEN.match(t["text"])]
        if toks:
            diffs.append(abs(seg["offsets"]["from"] - toks[0]["offsets"]["from"]) / 1000.0)
    return not diffs or float(np.median(diffs)) > 0.3


def read_whisper_json(path: Path) -> dict:
    # i token possono spezzare un carattere UTF-8 a metà: surrogateescape conserva i byte
    raw = path.read_bytes().decode("utf-8", errors="surrogateescape")
    return json.loads(raw)


def join_tokens(texts: list[str]) -> str:
    s = "".join(texts)
    return s.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def whisper_to_words(data: dict, tmap) -> list[dict]:
    """Token whisper → segmenti con parole (tempi già sul timeline originale)."""
    segs = []
    for si, seg in enumerate(data.get("transcription", [])):
        words: list[dict] = []
        cur: dict | None = None
        for tok in seg.get("tokens", []):
            text = tok.get("text", "")
            if not text or SPECIAL_TOKEN.match(text):
                continue
            t0 = tok["offsets"]["from"] / 1000.0
            t1 = tok["offsets"]["to"] / 1000.0
            p = float(tok.get("p", 0.0))
            plain = join_tokens([text])
            is_punct = bool(PUNCT_ONLY.match(plain))
            if cur is not None and (is_punct or not text.startswith(" ")):
                cur["toks"].append(text)
                if not is_punct:
                    cur["t1"] = t1
                    cur["ps"].append(p)
                continue
            if is_punct:  # punteggiatura a inizio segmento: la ignoriamo
                continue
            cur = {"toks": [text], "t0": t0, "t1": t1, "ps": [p]}
            words.append(cur)
        out = []
        for w in words:
            text = join_tokens(w["toks"]).strip()
            if not text or PUNCT_ONLY.match(text):
                continue
            start, end = tmap(w["t0"]), tmap(w["t1"])
            out.append({"w": text, "start": start, "end": max(end, start + 0.02),
                        "p": float(np.mean(w["ps"])) if w["ps"] else 0.0})
        if out:
            segs.append({"src_i": si, "words": out})
    return segs


# ── Parakeet (whisper.cpp parakeet-cli) ─────────────────────────────────────
def parakeet_model(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    if os.environ.get(PARAKEET_MODEL_ENV):
        return Path(os.environ[PARAKEET_MODEL_ENV]).expanduser()
    found = sorted((yc.HOME / ".whisper-models").glob("ggml-parakeet-tdt-0.6b-v3*.bin"))
    return found[0] if found else yc.HOME / ".whisper-models" / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"


SEG_RX = re.compile(r'^Segment \d+: \[(\d+) -> (\d+)\] "(.*)"\s*$')
TOK_RX = re.compile(r'^\s*\[\s*\d+\] id=\s*\d+ .*?p=([\d.]+) .*?t0=\s*(\d+) t1=\s*(\d+) '
                    r'word_start=(true|false) "(.*)"\s*$')


PARAKEET_FRAME_S = 0.08      # i bordi "Segment [a -> b]" di -ps sono frame dell'encoder (×0,08 s)


def parse_parakeet(text: str, offset: float) -> tuple[list[dict], bool]:
    """Output -ps di parakeet-cli (stderr) → segmenti con parole. Tempi dei token in centesimi.

    Due correzioni del parser: un token '▁' isolato (word_start=true, vuoto senza '▁') apre
    comunque una parola nuova (prima le cifre si attaccavano: «nel2019», «faceva1,2K»; numeri giusti
    4/29 → 29/29); i bordi dei segmenti sono frame dell'encoder, non centesimi.
    Ritorna (segmenti, approx): se mancano le righe dei token, le parole sono distribuite
    in modo uniforme sul segmento e marcate approx.
    """
    segs: list[dict] = []
    approx = False
    cur = None
    for line in text.splitlines():
        m = SEG_RX.match(line)
        if m:
            cur = {"t0": int(m.group(1)) * PARAKEET_FRAME_S + offset, "t1": int(m.group(2)) * PARAKEET_FRAME_S + offset,
                   "text": m.group(3), "toks": []}
            segs.append(cur)
            continue
        m = TOK_RX.match(line)
        if m and cur is not None:
            cur["toks"].append((float(m.group(1)), int(m.group(2)) / 100 + offset,
                                int(m.group(3)) / 100 + offset, m.group(4) == "true", m.group(5)))
    out = []
    for si, s in enumerate(segs):
        words: list[dict] = []
        if s["toks"]:
            cw = None
            pending_start = False
            for p, t0, t1, start, tok in s["toks"]:
                piece = tok.replace("▁", "")
                if not piece:
                    pending_start = pending_start or start
                    continue
                is_punct = bool(PUNCT_ONLY.match(piece))
                if cw is None or ((start or pending_start) and not is_punct):
                    cw = {"w": piece, "start": t0, "end": max(t1, t0 + 0.02), "ps": [p]}
                    words.append(cw)
                else:
                    cw["w"] += piece
                    if not is_punct:
                        cw["end"] = max(t1, cw["start"] + 0.02)
                        cw["ps"].append(p)
                pending_start = False
            for w in words:
                w["p"] = float(np.mean(w.pop("ps")))
        else:
            approx = True
            toks = s["text"].split()
            if not toks:
                continue
            step = (s["t1"] - s["t0"]) / len(toks)
            words = [{"w": t, "start": s["t0"] + k * step, "end": s["t0"] + (k + 1) * step,
                      "p": 0.0, "approx": True} for k, t in enumerate(toks)]
        if words:
            out.append({"src_i": si, "words": words})
    return out, approx


def quiet_cut_points(energy: Energy, duration: float, chunk: float) -> list[float]:
    """Punti di taglio ~ogni `chunk` s nel frame più silenzioso entro ±15 s."""
    cuts = [0.0]
    t = chunk
    while t < duration - 30:
        i0, i1 = int((t - 15) * 100), int((t + 15) * 100)
        seg = energy.db[i0:i1]
        cuts.append((i0 + int(np.argmin(seg))) / 100 if seg.size else t)
        t = cuts[-1] + chunk
    cuts.append(duration)
    return cuts


def run_parakeet(audio: Path, model: Path, threads: int, workdir: Path, key: str,
                 duration: float, energy: Energy) -> tuple[Path, Path, dict]:
    import soundfile as sf

    if not yc.which(yc.PARAKEET_CLI):
        raise RuntimeError(f"parakeet-cli non trovato: {yc.PARAKEET_CLI}")
    if not model.exists():
        raise RuntimeError(
            f"modello Parakeet mancante: {model}. Scaricalo (≈669 MB, CC-BY-4.0) dopo l'OK dell'operatore: "
            f"hf download ggml-org/parakeet-GGUF ggml-parakeet-tdt-0.6b-v3-q8_0.bin --local-dir ~/.whisper-models "
            f"(oppure imposta {PARAKEET_MODEL_ENV})")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cuts = quiet_cut_points(energy, duration, PARAKEET_CHUNK_S)
    all_segs: list[dict] = []
    approx_any = False
    elapsed = 0.0
    data, rate = sf.read(str(audio), dtype="int16")
    with tempfile.TemporaryDirectory(dir=CACHE_DIR, prefix=".tmp-") as tmp:
        for k in range(len(cuts) - 1):
            a, b = cuts[k], cuts[k + 1]
            chunk_wav = Path(tmp) / f"chunk{k:03d}.wav"
            sf.write(str(chunk_wav), data[int(a * rate): int(b * rate)], rate, subtype="PCM_16")
            logfile = workdir / "logs" / f"transcribe.parakeet.{k:03d}.log"
            elapsed += run_logged([yc.PARAKEET_CLI, "-m", model, "-f", chunk_wav, "-t", threads, "-ps"],
                                  logfile, f"parakeet {k + 1}/{len(cuts) - 1}")
            segs, approx = parse_parakeet(logfile.read_text(errors="replace"), a)
            approx_any |= approx
            all_segs += segs
    raw_dst = CACHE_DIR / f"{key}.parakeet.json"
    yc.write_json(raw_dst, {"segments": all_segs})
    meta = {"engine": "parakeet", "engine_version": whisper_version(), "model": model.name,
            "elapsed_s": round(elapsed, 1), "approx": approx_any, "chunks": len(cuts) - 1,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    meta_dst = CACHE_DIR / f"{key}.meta.json"
    yc.write_json(meta_dst, meta)
    return raw_dst, meta_dst, meta


def parakeet_words(raw_path: Path) -> list[dict]:
    """Parole Parakeet piatte e ordinate dal JSON in cache."""
    segs = yc.read_json(raw_path)["segments"]
    ws = [dict(w) for s in segs for w in s["words"] if not w.get("approx")]
    ws.sort(key=lambda w: w["start"])
    return ws


# ── Tempi Parakeet sul testo whisper ────────────────────────────────────────
# Le parole whisper hanno un anticipo sistematico (mediana −145…−275 ms) e il 23,6 % sbaglia di oltre 0,5 s
# anche col VAD spento; Parakeet TDT ha tempi a frame (80 ms) e sbaglia l'1,1 % (contro DTW). Il testo resta
# di whisper (nomi e unità migliori col prompt), i tempi vengono da Parakeet dove le due parole si allineano.
_ALIGN_STRIP = ".,;:!?\"«»“”()[]{}*'`…"
_ALIGN_NUM = {"zero": 0, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8,
              "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14, "quindici": 15,
              "sedici": 16, "diciassette": 17, "diciotto": 18, "diciannove": 19, "venti": 20, "trenta": 30,
              "quaranta": 40, "cinquanta": 50, "sessanta": 60, "settanta": 70, "ottanta": 80, "novanta": 90,
              "cento": 100, "mille": 1000}


def _num_norm(t: str) -> str:
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        return t.replace(".", "")
    m = re.fullmatch(r"(\d+)[.,](\d+)([kx]?)", t)
    if m:
        return f"{m.group(1)},{m.group(2)}{m.group(3)}"
    if t in _ALIGN_NUM:
        return str(_ALIGN_NUM[t])
    m = re.fullmatch(r"(\w+?)mila", t)
    if m and m.group(1) in _ALIGN_NUM:
        return str(_ALIGN_NUM[m.group(1)] * 1000)
    return t


def align_norm(word: str) -> str:
    """Forma confrontabile di una parola (minuscole, niente punteggiatura, numeri per valore)."""
    w = unicodedata.normalize("NFC", word).replace("’", "'").replace("‘", "'").casefold().replace("…", " ")
    w = re.sub(r"(?<=\w)[-–—](?=\w)", " ", w).replace("/", " slash ")
    out = []
    for t in w.split():
        t = t.strip(_ALIGN_STRIP)
        if t and not re.fullmatch(r"[-–—]+", t):
            out.append(_num_norm(t))
    return "".join(out)


def is_hesitation_token(word: str) -> bool:
    t = word.casefold().strip(_ALIGN_STRIP)
    return t in HESITATIONS or bool(HESITATION_RE.match(t))


def _dp_align(ref: list[dict], hyp: list[dict], max_dt: float) -> list[tuple]:
    """Levenshtein con vincolo di tempo (|Δt| ≤ max_dt), costo primario = numero di modifiche; a parità,
    somiglianza dei caratteri e distanza nel tempo. merge2 = due parole di ref in una di hyp, split2 = il
    contrario («vibe coding» = «vibecoding»). Stessa logica del valutatore usato per misurare la trascrizione."""
    n, m = len(ref), len(hyp)
    W = 10 ** 6
    D = np.full((n + 1, m + 1), np.inf)
    B = np.zeros((n + 1, m + 1), dtype=np.int8)
    D[0, 0] = 0
    for i in range(1, n + 1):
        D[i, 0], B[i, 0] = D[i - 1, 0] + W, 2
    for j in range(1, m + 1):
        D[0, j], B[0, j] = D[0, j - 1] + W, 3
    for i in range(1, n + 1):
        ri = ref[i - 1]
        for j in range(1, m + 1):
            hj = hyp[j - 1]
            dt = abs(ri["t"] - hj["t"])
            best, how = D[i - 1, j] + W, 2
            c = D[i, j - 1] + W
            if c < best:
                best, how = c, 3
            if dt <= max_dt:
                if ri["n"] == hj["n"]:
                    c = D[i - 1, j - 1] + min(dt, 10)
                else:
                    c = D[i - 1, j - 1] + W + (1 - difflib.SequenceMatcher(None, ri["n"], hj["n"]).ratio()) * 100 \
                        + min(dt, 10)
                if c < best:
                    best, how = c, 1
                if i >= 2 and ref[i - 2]["n"] + ri["n"] == hj["n"] and not re.search(r"\d", hj["n"]):
                    c = D[i - 2, j - 1] + min(dt, 10)
                    if c < best:
                        best, how = c, 4
                if j >= 2 and hyp[j - 2]["n"] + hj["n"] == ri["n"] and not re.search(r"\d", ri["n"]):
                    c = D[i - 1, j - 2] + min(dt, 10)
                    if c < best:
                        best, how = c, 5
            D[i, j], B[i, j] = best, how
    ops: list[tuple] = []
    i, j = n, m
    while i > 0 or j > 0:
        how = B[i, j]
        if how == 1:
            ops.append(("match" if ref[i - 1]["n"] == hyp[j - 1]["n"] else "sub", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif how == 2:
            ops.append(("del", i - 1, None))
            i -= 1
        elif how == 3:
            ops.append(("ins", None, j - 1))
            j -= 1
        elif how == 4:
            ops += [("merge2", i - 1, j - 1), ("merge2", i - 2, j - 1)]
            i, j = i - 2, j - 1
        elif how == 5:
            ops += [("split2", i - 1, j - 1), ("split2", i - 1, j - 2)]
            i, j = i - 1, j - 2
        else:
            raise RuntimeError("allineamento: backtrack fallito")
    return ops[::-1]


def align_words(A: list[dict], B: list[dict], max_dt: float = ALIGN_MAX_DT) -> list[tuple]:
    """Allineamento parola-parola A→B: ancore difflib (blocchi ≥3 parole, |Δt| ≤ max_dt) + DP esatta nei buchi.
    Ritorna [(op, i, j)] con op in match|sub|del|ins|merge2|split2."""
    sa = [{"n": align_norm(w["w"]) or "∅", "t": w["start"]} for w in A]
    sb = [{"n": align_norm(w["w"]) or "∅", "t": w["start"]} for w in B]
    sm = difflib.SequenceMatcher(None, [x["n"] for x in sa], [x["n"] for x in sb], autojunk=False)
    anchors: list[tuple[int, int]] = []
    for blk in sm.get_matching_blocks():
        if blk.size >= 3:
            for k in range(blk.size):
                i, j = blk.a + k, blk.b + k
                if abs(sa[i]["t"] - sb[j]["t"]) <= max_dt and (not anchors or (i > anchors[-1][0] and j > anchors[-1][1])):
                    anchors.append((i, j))
    ops: list[tuple] = []
    pi, pj = 0, 0
    for i, j in anchors + [(len(sa), len(sb))]:
        if i > pi or j > pj:
            sub = _dp_align(sa[pi:i], sb[pj:j], max_dt)
            ops += [(op, None if a is None else a + pi, None if b is None else b + pj) for op, a, b in sub]
        if i < len(sa):
            ops.append(("match", i, j))
        pi, pj = i + 1, j + 1
    return ops


def _voiced_runs(energy: Energy, a: float, b: float, min_len: float = 0.06) -> list[tuple[float, float]]:
    i0, i1 = max(0, int(round(a * 100))), min(energy.n, int(round(b * 100)))
    out, k = [], i0
    while k < i1:
        if energy.voiced[k]:
            k2 = k
            while k2 < i1 and energy.voiced[k2]:
                k2 += 1
            if (k2 - k) / 100 >= min_len:
                out.append((k / 100, k2 / 100))
            k = k2
        else:
            k += 1
    return out


def _place_in_voiced_gaps(new: list[dict], anchored: list[bool], energy: Energy) -> int:
    """Le parole senza corrispondente Parakeet (quasi sempre «ehm»/«eh») stanno nel buco tra le vicine con
    tempi Parakeet: le metto sull'audio con voce dentro quel buco (una parola → il tratto di voce più
    lungo; più parole → tutto il tratto, in proporzione ai caratteri). Niente voce → resta l'interpolazione."""
    placed, k, n = 0, 0, len(new)
    while k < n:
        if anchored[k]:
            k += 1
            continue
        k2 = k
        while k2 < n and not anchored[k2]:
            k2 += 1
        g0 = new[k - 1]["end"] if k > 0 else new[k]["start"] - 1.0
        g1 = new[k2]["start"] if k2 < n else new[k2 - 1]["end"] + 1.0
        vr = _voiced_runs(energy, g0, g1) if g1 - g0 >= 0.06 else []
        if vr:
            group = list(range(k, k2))
            if len(group) == 1:
                mid = (new[k]["start"] + new[k]["end"]) / 2
                a, b = max(vr, key=lambda r: (round(r[1] - r[0], 2), -abs((r[0] + r[1]) / 2 - mid)))
                new[k]["start"], new[k]["end"] = a, b
            else:
                a, b = vr[0][0], vr[-1][1]
                tot = sum(max(1, len(new[j]["w"])) for j in group)
                t = a
                for j in group:
                    d = (b - a) * max(1, len(new[j]["w"])) / tot
                    new[j]["start"], new[j]["end"] = t, t + d
                    t += d
            placed += len(group)
        k = k2
    return placed


def _mark_duplicates_without_audio(new: list[dict], anchored: list[bool], min_run: int = 6,
                                   max_s_per_word: float = 0.05, lookback: int = 80) -> int:
    """Una sequenza di ≥6 parole whisper senza corrispondente Parakeet, che nel buco tra le vicine avrebbe meno
    di 50 ms a parola e ripete di fila (blocco contiguo ≥80 %) le parole appena dette, è un doppione del
    passaggio tra due finestre
    di whisper: fisicamente non c'è audio per dirla una seconda volta. La marco "dup_no_audio" (va scartata
    come allucinazione). Visto su un episodio di prova con il prompt del glossario automatico: 38 parole di fila."""
    n, k, marked = len(new), 0, 0
    while k < n:
        if anchored[k]:
            k += 1
            continue
        k2 = k
        while k2 < n and not anchored[k2]:
            k2 += 1
        run = k2 - k
        if run >= min_run:
            g0 = new[k - 1]["end"] if k > 0 else new[k]["start"]
            g1 = new[k2]["start"] if k2 < n else new[k2 - 1]["end"]
            if (g1 - g0) / run < max_s_per_word:
                seq = [align_norm(w["w"]) for w in new[k:k2]]
                prev = [align_norm(w["w"]) for w in new[max(0, k - lookback):k]]
                sm = difflib.SequenceMatcher(None, seq, prev, autojunk=False)
                if sm.find_longest_match(0, len(seq), 0, len(prev)).size >= 0.8 * run:
                    for j in range(k, k2):
                        new[j]["dup_no_audio"] = True
                    marked += run
        k = k2
    return marked


def retime_with_parakeet(W: list[dict], P: list[dict], energy: Energy,
                         max_dt: float = ALIGN_MAX_DT) -> tuple[list[dict], dict, list[tuple]]:
    """Parole whisper W con i tempi delle parole Parakeet P allineate; le altre interpolate tra le vicine
    e poi messe sulla voce (timing_guess). Ritorna (parole nuove, statistiche, operazioni)."""
    ops = align_words(W, P, max_dt)
    m: dict[int, list[int]] = {}
    for op, i, j in ops:
        if i is not None and j is not None and op in ("match", "sub", "merge2", "split2"):
            m.setdefault(i, [])
            if j not in m[i]:
                m[i].append(j)
    inv: dict[int, list[int]] = {}
    for i, js in m.items():
        for j in js:
            inv.setdefault(j, []).append(i)
    new = [dict(w) for w in W]
    anchored = [False] * len(W)
    for i, js in m.items():
        js = sorted(js)
        if len(js) == 1 and len(inv[js[0]]) > 1:          # merge2: la parola Parakeet si divide per caratteri
            group = sorted(inv[js[0]])
            p = P[js[0]]
            tot = sum(max(1, len(W[k]["w"])) for k in group)
            t = p["start"]
            for k in group:
                d = (p["end"] - p["start"]) * max(1, len(W[k]["w"])) / tot
                if k == i:
                    new[i]["start"], new[i]["end"] = t, t + d
                t += d
        else:
            new[i]["start"], new[i]["end"] = P[js[0]]["start"], P[js[-1]]["end"]
        anchored[i] = True
    idx = [k for k in range(len(W)) if anchored[k]]
    n_interp = 0
    import bisect
    for k in range(len(W)):
        if anchored[k]:
            continue
        n_interp += 1
        pos = bisect.bisect_left(idx, k)
        prev = idx[pos - 1] if pos > 0 else None
        nxt = idx[pos] if pos < len(idx) else None
        if prev is not None and nxt is not None:
            o0, o1 = W[prev]["end"], W[nxt]["start"]
            n0, n1 = new[prev]["end"], new[nxt]["start"]
            if o1 - o0 > 1e-3 and n1 > n0:
                f = (lambda t, o0=o0, o1=o1, n0=n0, n1=n1: n0 + (t - o0) * (n1 - n0) / (o1 - o0))
                new[k]["start"], new[k]["end"] = f(W[k]["start"]), f(W[k]["end"])
            else:
                new[k]["start"] = new[k]["end"] = n0
        elif prev is not None:
            off = new[prev]["end"] - W[prev]["end"]
            new[k]["start"], new[k]["end"] = W[k]["start"] + off, W[k]["end"] + off
        elif nxt is not None:
            off = new[nxt]["start"] - W[nxt]["start"]
            new[k]["start"], new[k]["end"] = W[k]["start"] + off, W[k]["end"] + off
        new[k]["end"] = max(new[k]["end"], new[k]["start"] + 0.02)
        new[k]["timing_guess"] = True
    placed = _place_in_voiced_gaps(new, anchored, energy)
    n_dup = _mark_duplicates_without_audio(new, anchored)
    stats = {"words": len(W), "parakeet_words": len(P), "anchored": sum(anchored), "duplicates_no_audio": n_dup,
             "anchored_pct": round(100 * sum(anchored) / max(1, len(W)), 1), "interpolated": n_interp,
             "voiced_placed": placed, "max_dt": max_dt,
             "ops": {o: sum(1 for x in ops if x[0] == o) for o in ("match", "sub", "del", "ins", "merge2", "split2")}}
    return new, stats, ops


def regroup(segs: list[dict], new_words: list[dict]) -> list[dict]:
    """Rimette le parole ritemporizzate nei segmenti d'origine (inizi monotoni dentro il segmento)."""
    out, k = [], 0
    for s in segs:
        n = len(s["words"])
        ws = new_words[k:k + n]
        k += n
        for a, b in zip(ws, ws[1:]):
            if b["start"] < a["start"]:
                b["start"] = a["start"]
            b["end"] = max(b["end"], b["start"] + 0.02)
        out.append({**{kk: vv for kk, vv in s.items() if kk != "words"}, "words": ws})
    return out


# ── Lista d'ascolto (whisper ↔ Parakeet) ─────────────────────────────────────
_REVIEW_FUNC = {"e", "è", "ed", "i", "il", "lo", "la", "le", "gli", "l", "un", "una", "uno", "di", "da", "a", "ad",
                "in", "su", "con", "per", "tra", "fra", "che", "ma", "o", "se", "non", "ne", "ci", "si", "mi", "ti",
                "vi", "del", "della", "dei", "al", "alla", "ai", "dal", "dalla", "nel", "nella", "sul", "sulla",
                "sui", "era", "ho", "ha", "hai", "hanno", "sono", "sei", "c'è", "l'ho", "anche", "poi", "più",
                "come", "cosa", "quello", "questo", "quella", "questa"}
_REVIEW_DISC = {"quindi", "cioè", "sì", "si", "no", "ok", "okay", "beh", "insomma", "diciamo", "tipo", "allora",
                "ecco", "niente", "comunque", "praticamente", "appunto", "magari", "boh", "dire", "giusto",
                "esatto", "vabbè", "dai"}


def _rcore(w: str) -> str:
    return re.sub(r"[^\w']", "", w.lower())


def _rcontent(w: str) -> bool:
    c = _rcore(w)
    return len(c.replace("'", "")) >= 4 and c not in _REVIEW_FUNC and c not in _REVIEW_DISC


def _rspecial(w: str, prev: str | None) -> bool:
    raw = w.strip(".,;:!?…\"«»")
    if re.search(r"\d", raw):
        return True
    if len(raw) >= 2 and raw.isupper():
        return True
    sentence_start = prev is None or prev.rstrip("\"»”)'").endswith(SENT_END)
    return bool(raw[:1].isupper() and not sentence_start)


def _rsame_lemma(a: str, b: str) -> bool:
    a, b = _rcore(a), _rcore(b)
    strip = (lambda s: re.sub(r"^(l|un|all|dell|nell|sull|dall|d|c)'", "", s))
    a, b = strip(a), strip(b)
    return a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 1)


def disagreement_spans(W: list[dict], P: list[dict], ops: list[tuple], times: list[dict]) -> list[dict]:
    """Punti in cui whisper e Parakeet non concordano e conviene ascoltare (review_flags):
    sostituzioni con cifre, sigle o nomi a metà frase (priorità), o tra parole di contenuto diverse;
    parole di contenuto sentite da un solo motore. Voci entro 1,5 s si uniscono; ascolto [t0−1, t1+1,5]."""
    items = []
    for op, i, j in ops:
        if op == "sub":
            a, b = W[i]["w"], P[j]["w"]
            if is_hesitation_token(a) or is_hesitation_token(b):
                continue
            prev = W[i - 1]["w"] if i > 0 else None
            nxt = W[i + 1]["w"] if i + 1 < len(W) else ""
            # priorità: cifre, sigle, nomi a metà frase, o la parola subito dopo/prima di una cifra
            # («15.000 potenti» ~ «utenti»: ciò che il numero conta è un fatto da verificare)
            prio = _rspecial(a, prev) or _rspecial(b, None) or bool(re.search(r"\d", (prev or "") + nxt))
            keep = (not _rsame_lemma(a, b) or bool(re.search(r"\d", a + b))) if prio else \
                (_rcontent(a) and _rcontent(b) and not _rsame_lemma(a, b))
            if keep:
                items.append({"t": round(times[i]["start"], 2), "type": "sub", "whisper": a, "parakeet": b,
                              "priority": prio})
        elif op == "del":
            a = W[i]["w"]
            if not is_hesitation_token(a) and _rcontent(a):
                items.append({"t": round(times[i]["start"], 2), "type": "whisper_only", "whisper": a,
                              "priority": _rspecial(a, W[i - 1]["w"] if i > 0 else None)})
        elif op == "ins":
            b = P[j]["w"]
            if not is_hesitation_token(b) and _rcontent(b):
                items.append({"t": round(P[j]["start"], 2), "type": "parakeet_only", "parakeet": b,
                              "priority": _rspecial(b, None)})
    items.sort(key=lambda x: x["t"])
    spans: list[dict] = []
    for it in items:
        if spans and it["t"] - spans[-1]["t1"] <= 1.5:
            spans[-1]["t1"] = it["t"]
            spans[-1]["items"].append(it)
        else:
            spans.append({"t0": it["t"], "t1": it["t"], "items": [it]})
    for s in spans:
        s["priority"] = any(x["priority"] for x in s["items"])
        s["hallucination_candidate"] = sum(1 for x in s["items"] if x["type"] == "whisper_only") >= 3
        s["listen"] = [round(max(0.0, s["t0"] - 1.0), 2), round(s["t1"] + 1.5, 2)]
    return spans


# ── Post-processing ─────────────────────────────────────────────────────────
def collapse_loops(words: list[dict], min_rep: int = 5, keep: int = 2) -> tuple[list[dict], int]:
    """Riduce i loop tipici di whisper (stesso n-gramma ripetuto ≥ min_rep volte di fila)."""
    removed = 0
    for n in range(1, 7):
        i = 0
        out: list[dict] = []
        while i < len(words):
            gram = [norm(w["w"]) for w in words[i:i + n]]
            if len(gram) < n:
                out += words[i:]
                break
            reps = 1
            while [norm(w["w"]) for w in words[i + reps * n: i + (reps + 1) * n]] == gram:
                reps += 1
            if reps >= min_rep:
                out += words[i: i + keep * n]
                removed += (reps - keep) * n
                i += reps * n
            else:
                out.append(words[i])
                i += 1
        words = out
    return words, removed


def filter_hallucinations(segs: list[dict], energy: Energy, prompt: str) -> tuple[list[dict], list[dict]]:
    prompt_n = " ".join(norm(t) for t in prompt.split() if norm(t))
    kept, dropped = [], []
    recent: list[str] = []
    for s in segs:
        words, loops = collapse_loops(s["words"])
        if loops:
            dropped.append({"start": round(words[0]["start"], 2), "reason": "loop", "words_removed": loops})
        s["words"] = words
        text = " ".join(w["w"] for w in words)
        text_n = " ".join(norm(w["w"]) for w in words if norm(w["w"]))
        start, end = words[0]["start"], words[-1]["end"]
        voiced = energy.voiced_ratio(start, end)
        mean_p = float(np.mean([w["p"] for w in words]))
        reason = None
        if HARD_HALLUCINATIONS.search(text):
            reason = "frase-tipica"
        elif text_n and f" {text_n} " in f" {prompt_n} " and \
                (len(words) >= 3 or (len(words) >= 2 and voiced < 0.1)):
            reason = "eco-del-prompt"
        elif text_n and text_n in recent and voiced < 0.25:
            reason = "ripetizione-nel-silenzio"
        elif voiced < 0.08 and mean_p < 0.4:
            reason = "silenzio-bassa-confidenza"
        if reason:
            dropped.append({"start": round(start, 2), "end": round(end, 2), "text": text[:120],
                            "reason": reason, "voiced": round(voiced, 2)})
            continue
        # duplicati a cavallo di due finestre: stesse parole iniziali sovrapposte nel tempo
        if kept:
            prev = kept[-1]["words"]
            for k in range(min(len(prev), len(words), 8), 2, -1):
                if [norm(w["w"]) for w in prev[-k:]] == [norm(w["w"]) for w in words[:k]] \
                        and words[0]["start"] < prev[-1]["end"] - 0.1:
                    dropped.append({"start": round(words[0]["start"], 2), "reason": "duplicato-confine",
                                    "text": " ".join(w["w"] for w in words[:k])})
                    words = words[k:]
                    break
            if not words:
                continue
            s["words"] = words
        kept.append(s)
        recent = (recent + [text_n])[-3:]
    return kept, dropped


PHON_RULES = [("ch", "k"), ("ck", "k"), ("ph", "f"), ("gh", "g"), ("gn", "n"), ("qu", "kv"),
              ("c", "k"), ("q", "k"), ("x", "ks"), ("y", "i"), ("w", "v"), ("j", "i"), ("h", "")]


def phon(word: str) -> str:
    w = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    w = re.sub(r"[^a-z]", "", w)
    for a, b in PHON_RULES:
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def _glossary_keys(terms: list[str], surname_only: bool) -> dict[str, str]:
    """Parole-chiave del glossario: termini di una parola (≥4 lettere, es. marchi) e, dei
    termini composti (nomi di persona), solo l'ultima parola se ≥6 lettere (es. 'Bianchi'):
    i nomi di battesimo ('Paolo', 'Giulio') e i cognomi corti ('Neri') cambierebbero
    persone diverse ('Paola', 'Giulia', 'Nero')."""
    keys: dict[str, str] = {}
    for t in terms:
        parts = [re.sub(r"[^\w&]", "", p) for p in t.strip().split()]
        parts = [p for p in parts if p]
        if not parts:
            continue
        cands = parts if len(parts) == 1 else ([parts[-1]] if surname_only else parts)
        for core in cands:
            minlen = 4 if len(parts) == 1 else 6
            if len(core) >= minlen and core[0].isupper() and core.isalpha():
                keys.setdefault(core.lower(), core)
    return keys


def glossary_fix(words: list[dict], apply_terms: list[str], suspect_terms: list[str],
                 threshold: float = 0.8, suspect_threshold: float = 0.72) -> tuple[list[dict], list[dict]]:
    """Corregge nomi propri simili ai termini dell'EPISODIO (prudente: solo parole maiuscole,
    stessa iniziale fonetica, similarità fonetica ≥ threshold). La parola corretta conserva
    l'originale in `fixed_from`. Le somiglianze col glossario del CANALE non vengono applicate:
    finiscono in `suspects` per la revisione."""
    apply_keys = _glossary_keys(apply_terms, surname_only=True)
    sus_keys = {k: v for k, v in _glossary_keys(suspect_terms, surname_only=False).items() if k not in apply_keys}
    known = set(apply_keys) | {k.lower() for t in apply_terms + suspect_terms for k in re.findall(r"\w+", t)}
    fixes: list[dict] = []
    suspects: list[dict] = []
    ph_apply = {k: phon(v) for k, v in apply_keys.items()}
    ph_sus = {k: phon(v) for k, v in sus_keys.items()}

    def best_of(pc: str, table: dict[str, str]) -> tuple[str | None, float]:
        best, score = None, 0.0
        for k, pk in table.items():
            if not pk or pc[:1] != pk[:1]:
                continue
            r = difflib.SequenceMatcher(None, pc, pk).ratio()
            if r > score:
                best, score = k, r
        return best, score

    for k, w in enumerate(words):
        m = re.match(r"^([«\"'(]*)([\w']+)([^\w']*)$", w["w"])
        if not m:
            continue
        lead, core, trail = m.groups()
        if not core[:1].isupper() or core.lower() in known or len(core) < 4:
            continue
        # maiuscola solo perché a inizio frase: niente sospetti (es. "Allora," ≠ "Allori")
        sentence_start = k == 0 or words[k - 1]["w"].endswith(SENT_END)
        pc = phon(core)
        best, score = best_of(pc, ph_apply)
        if best and score >= threshold:
            new = lead + apply_keys[best] + trail
            fixes.append({"start": round(w["start"], 2), "from": w["w"], "to": new, "score": round(score, 2)})
            w["fixed_from"] = w["w"]
            w["w"] = new
            continue
        if sentence_start or norm(core) in DISCOURSE:
            continue
        best, score = best_of(pc, ph_sus)
        if best and score >= suspect_threshold:
            suspects.append({"start": round(w["start"], 2), "word": w["w"], "maybe": sus_keys[best],
                             "score": round(score, 2)})
    return fixes, suspects


def snap_to_pauses(words: list[dict], energy: Energy) -> int:
    """Allinea i bordi tra parole consecutive alla pausa reale più vicina (se c'è).

    I tempi dei token whisper derivano da un'euristica e a inizio segmento sono compressi.
    Dove l'audio mostra una pausa vera (≥150 ms) vicino al confine previsto, fine parola e
    inizio della successiva vengono spostati sui bordi della pausa: sono i punti di taglio
    che contano per il montaggio. Nel parlato continuo i tempi restano quelli del modello.
    """
    moved = 0
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        lo = max(a["start"] + 0.05, a["end"] - 0.4)
        hi = min(b["end"] - 0.05, b["start"] + 0.4)
        if hi <= lo:
            continue
        # se il modello vede parlato continuo serve una pausa più lunga (le occlusive doppie
        # come in "tutti" possono durare ~150 ms senza essere una pausa)
        min_len = 0.15 if b["start"] - a["end"] >= 0.12 else 0.22
        ps = energy.pauses(lo, hi, min_len)
        if not ps:
            continue
        # fine di A = inizio della PRIMA pausa; inizio di B = fine dell'ULTIMA pausa:
        # respiri e rumori tra due pause non vengono attribuiti a nessuna parola
        new_end = max(a["start"] + 0.04, ps[0][0] + 0.02)
        new_start = min(b["end"] - 0.04, ps[-1][1] - 0.02)
        if new_start <= new_end:
            continue
        if abs(new_end - a["end"]) > 0.02 or abs(new_start - b["start"]) > 0.02:
            moved += 1
        a["end"], b["start"] = new_end, new_start
    return moved


FLAG_KEYS = ("filler", "filler_kind", "discourse", "false_start")


def word_class(w: dict) -> str:
    """Etichetta leggibile della classe di una parola (anche per lo schema vecchio)."""
    if w.get("false_start"):
        return "false_start"
    if w.get("filler"):
        return f"filler:{w.get('filler_kind') or '?'}"
    if w.get("discourse"):
        return "discourse"
    return "-"


def flag_counts(words: list[dict]) -> dict:
    """Conteggi per il riepilogo JSON. Nello schema vecchio (v1) i segnali discorsivi erano
    filler con filler_kind 'discourse': li contiamo in entrambe le voci, come stavano."""
    from collections import Counter

    kinds = Counter(w.get("filler_kind") or "?" for w in words if w.get("filler"))
    return {"fillers": sum(1 for w in words if w.get("filler")),
            "filler_kinds": dict(sorted(kinds.items())),
            "discourse": sum(1 for w in words if w.get("discourse") or
                             (w.get("filler") and w.get("filler_kind") == "discourse")),
            "false_starts": sum(1 for w in words if w.get("false_start"))}


def _gap_before(words: list[dict], i: int) -> float:
    return 99.0 if i == 0 else words[i]["start"] - words[i - 1]["end"]


def _gap_after(words: list[dict], i: int) -> float:
    return 99.0 if i + 1 >= len(words) else words[i + 1]["start"] - words[i]["end"]


def _same_speaker(a: dict, b: dict) -> bool:
    return a.get("speaker") == b.get("speaker")


def _sentence_initial(words: list[dict], i: int) -> bool:
    if i == 0:
        return True
    prev = words[i - 1]
    return prev["w"].rstrip("\"»”)'").endswith(SENT_END + (":",)) or not _same_speaker(prev, words[i]) \
        or _gap_before(words, i) >= 0.5


def _discourse_in_context(words: list[dict], i: int, n: str) -> bool:
    """True se il marcatore n alla posizione i è un segnale discorsivo (regole economiche, 06 §4.1)."""
    raw = words[i]["w"]
    prev = norm(words[i - 1]["w"]) if i > 0 else ""
    prev_raw = words[i - 1]["w"] if i > 0 else ""
    nxt = norm(words[i + 1]["w"]) if i + 1 < len(words) else ""
    prev_punct = bool(re.search(r"[,;:.?!…]$", prev_raw.rstrip("\"»”)'")))
    own_punct = bool(re.search(r"[,;:.?!…]", raw))
    if n == "quindi":
        return True
    if n == "tipo":
        if nxt in ("di", "da") or nxt.startswith("d'"):
            return False                                    # "un tipo di", "che tipo di"
        if prev in TIPO_NOUN_PREV and not prev_punct and not own_punct:
            return False                                    # "un tipo", "quel tipo" (nome)
        if NUMBER_RE.match(nxt) and not own_punct:
            return False                                    # "tipo cinquanta clienti": qualificatore
        return True
    if n in ("diciamo", "praticamente"):
        return not (NUMBER_RE.match(nxt) and not own_punct)  # qualificatore di un numero: contenuto
    if n == "allora":
        return prev not in ALLORA_TEMPORAL_PREV or prev_punct  # "da allora", "fino ad allora"
    if n == "niente":
        if prev in NIENTE_CONTENT_PREV or nxt in NIENTE_CONTENT_NEXT:
            return False
        back = []
        for k in range(i - 1, max(-1, i - 6), -1):          # negazione nella stessa frase
            if words[k]["w"].rstrip("\"»”)'").endswith(SENT_END):
                break
            back.append(norm(words[k]["w"]))
        if any(b in NEGATIONS for b in back):
            return False
        return _sentence_initial(words, i) or own_punct or (prev == "e" and _sentence_initial(words, i - 1))
    return True


def classify_words(words: list[dict]) -> dict:
    """Riclassifica in place filler / discourse / false_start (FLAGS_VERSION 2). Ritorna i conteggi.

    Lavora sulle parole finali (tempi sul timeline del sorgente, speaker se già assegnati):
    è la stessa funzione usata da --reflag e, in memoria, da yt-captions sui transcript vecchi.
    """
    for w in words:
        for k in FLAG_KEYS:
            w.pop(k, None)
    norms = [norm(w["w"]) for w in words]

    def flag_filler(k: int, kind: str) -> None:
        words[k]["filler"] = True
        words[k]["filler_kind"] = kind
        words[k].pop("discourse", None)
        if kind == "false_start":
            words[k]["false_start"] = True

    # 1. parole singole
    for i, w in enumerate(words):
        n = norms[i]
        n_plain = n.replace("'", "")
        raw = w["w"]
        if not n:
            continue
        if n_plain in HESITATIONS or HESITATION_RE.match(n_plain):
            if n_plain == "eh" and re.search(r"[?!]", raw):
                w["discourse"] = True                       # "bello, eh?" (tag) / "eh!" interiezione
            else:
                flag_filler(i, "hesitation")
            continue
        if n_plain in INTERJECTIONS:
            standalone = _gap_before(words, i) >= PAUSE_S and _gap_after(words, i) >= PAUSE_S
            if standalone and not re.search(r"[?!]", raw):
                flag_filler(i, "hesitation")
            else:
                w["discourse"] = True                       # "ah, ok": interiezione con significato
            continue
        if n in DISCOURSE_MARKERS:
            if _discourse_in_context(words, i, n):
                w["discourse"] = True
            continue
        if n in SENTENCE_INITIAL_MARKERS:
            if _sentence_initial(words, i):
                w["discourse"] = True
            continue
        if n == "no" and raw.rstrip("\"»”)'").endswith("?") and not _sentence_initial(words, i):
            w["discourse"] = True                           # tag "…, no?"
    # 2. locuzioni ("nel senso", "voglio dire", "va be'")
    for i in range(len(words) - 1):
        if (norms[i], norms[i + 1]) in DISCOURSE_PHRASES and _same_speaker(words[i], words[i + 1]) \
                and not words[i]["w"].endswith((",", ".", "?", "!", "…")):
            for k in (i, i + 1):
                if not words[k].get("filler"):
                    words[k]["discourse"] = True
    # 3. parole troncate ("pro-") = false partenza; "il pro- il progetto" → anche il primo "il"
    for i, w in enumerate(words):
        if i + 1 < len(words) and TRUNCATED_RE.search(w["w"]) and not w.get("filler") \
                and words[i + 1]["start"] - w["end"] < 1.5 and _same_speaker(w, words[i + 1]):
            flag_filler(i, "false_start")
            if i > 0 and i + 1 < len(words) and norms[i - 1] == norms[i + 1] and norms[i - 1] in STUTTER_WORDS \
                    and not words[i - 1].get("discourse"):
                flag_filler(i - 1, "false_start")
    # 4. ripetizioni immediate di 3, 2, 1 parole: si toglie la prima copia
    for n in (3, 2, 1):
        i = 0
        while i + 2 * n <= len(words):
            a, b = words[i:i + n], words[i + n:i + 2 * n]
            ga, gb = norms[i:i + n], norms[i + n:i + 2 * n]
            ok = ga == gb and all(ga) \
                and all(_same_speaker(words[i], x) for x in a + b) \
                and not any(x.get("filler") or x.get("discourse") for x in a) \
                and not a[-1]["w"].rstrip("\"»”)'").endswith(SENT_END) \
                and b[0]["start"] - a[0]["start"] <= (1.2 if n == 1 else 2.5) \
                and not all(g in REDUP_OK for g in ga)
            if ok and n == 1:
                ok = ga[0] in STUTTER_WORDS
            if ok and n > 1:
                ok = any(g in STUTTER_WORDS for g in ga)    # "ho fatto ho fatto", non "molto bello molto bello"
            if ok:
                for k in range(i, i + n):
                    flag_filler(k, "repetition")
                i += n
            else:
                i += 1
    return flag_counts(words)


def reflag_doc(doc: dict) -> dict:
    """Riclassifica un transcript.words.json già caricato. Ritorna before/after/changed."""
    words = doc.get("words", [])
    before_cls = [word_class(w) for w in words]
    before = flag_counts(words)
    after = classify_words(words)
    changed = []
    for w, old in zip(words, before_cls):
        new = word_class(w)
        if new != old:
            changed.append({"i": w.get("i"), "w": w["w"], "start": w["start"], "from": old, "to": new})
    pp = doc.setdefault("postprocess", {})
    pp.update(fillers=after["fillers"], discourse=after["discourse"], false_starts=after["false_starts"],
              filler_kinds=after["filler_kinds"])
    return {"before": before, "after": after, "changed": changed,
            "version_before": doc.get("flags_version", 1)}


def finalize(segs: list[dict], duration: float) -> tuple[list[dict], list[dict]]:
    words: list[dict] = []
    segments: list[dict] = []
    last_start = 0.0
    for s in segs:
        w0 = len(words)
        for w in s["words"]:
            st = min(max(w["start"], last_start, 0.0), duration)
            en = min(max(w["end"], st + 0.02), duration)
            rec = {"i": len(words), "w": w["w"], "start": round(st, 3), "end": round(en, 3),
                   "p": round(float(w.get("p", 0.0)), 3)}
            for k in ("approx", "fixed_from", "timing_guess"):
                if w.get(k):
                    rec[k] = w[k]
            words.append(rec)
            last_start = st
        if len(words) > w0:
            ws = words[w0:]
            segments.append({"i": len(segments), "start": ws[0]["start"], "end": ws[-1]["end"],
                             "text": " ".join(x["w"] for x in ws), "w0": w0, "w1": len(words)})
    # nessuna sovrapposizione tra parole consecutive (utile per tagli e sottotitoli)
    for a, b in zip(words, words[1:]):
        if a["end"] > b["start"] and b["start"] > a["start"]:
            a["end"] = b["start"]
    return words, segments


# ── SRT sul timeline del sorgente ───────────────────────────────────────────
NO_BREAK_AFTER = {"il", "lo", "la", "i", "gli", "le", "l'", "un", "uno", "una", "un'", "di", "a", "da",
                  "in", "con", "su", "per", "tra", "fra", "e", "o", "che", "del", "della", "dei", "degli",
                  "delle", "al", "alla", "ai", "agli", "alle", "dal", "dalla", "nel", "nella", "nei",
                  "sul", "sulla", "non", "mi", "ti", "si", "ci", "vi", "ne", "ma", "se", "come"}


def wrap_two_lines(text: str, width: int = 42) -> str:
    if len(text) <= width:
        return text
    toks = text.split()
    best, best_cost = None, 1e9
    for k in range(1, len(toks)):
        l1, l2 = " ".join(toks[:k]), " ".join(toks[k:])
        if len(l1) > width or len(l2) > width:
            continue
        cost = abs(len(l1) - len(l2)) + (25 if norm(toks[k - 1]) in NO_BREAK_AFTER else 0) \
            - (10 if toks[k - 1].endswith((",", ".", "?", "!", ":", ";")) else 0)
        if cost < best_cost:
            best, best_cost = (l1, l2), cost
    return "\n".join(best) if best else text


def fits_two_lines(text: str, width: int = 42) -> bool:
    if len(text) <= width:
        return True
    toks = text.split()
    return any(len(" ".join(toks[:k])) <= width and len(" ".join(toks[k:])) <= width for k in range(1, len(toks)))


def build_srt(words: list[dict], width: int = 42, max_dur: float = 6.0, gap_break: float = 0.6) -> str:
    """SRT leggibile sul timeline sorgente: ≤2 righe × width, ≤ max_dur s, a capo su pause,
    fine frase, virgola a metà cue e cambio di speaker."""
    cues: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur:
            cur_text = " ".join(x["w"] for x in cur)
            gap = w["start"] - cur[-1]["end"]
            spk_change = w.get("speaker") and cur[-1].get("speaker") and w["speaker"] != cur[-1]["speaker"]
            if not fits_two_lines(f"{cur_text} {w['w']}", width) or w["end"] - cur[0]["start"] > max_dur \
                    or gap >= gap_break or spk_change \
                    or (cur[-1]["w"].endswith(SENT_END) and len(cur_text) >= 20) \
                    or (cur[-1]["w"].endswith((",", ";", ":")) and len(cur_text) >= width):
                cues.append(cur)
                cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    out = []
    for k, c in enumerate(cues):
        a = c[0]["start"]
        b = c[-1]["end"]
        nxt = cues[k + 1][0]["start"] if k + 1 < len(cues) else b + 1.0
        b = min(max(b, a + 0.8), nxt - 0.04) if nxt - 0.04 > a else b  # minimo leggibile, mai sovrapposti
        out.append(f"{k + 1}\n{yc.fmt_ts(a, 'srt')} --> {yc.fmt_ts(b, 'srt')}\n"
                   f"{wrap_two_lines(' '.join(x['w'] for x in c))}\n")
    return "\n".join(out)


# ── Main ────────────────────────────────────────────────────────────────────
def outputs_fresh(words_json: Path, srt: Path, audio: Path, engine: str, prompt: str,
                  legacy_prompt: str | None = None, timing_mode: str | None = None,
                  timing_explicit: bool = False) -> tuple[bool, dict]:
    """True se il transcript esistente corrisponde a motore, prompt e tempi richiesti.

    Transcript della pipeline precedente (senza postprocess_version): restano validi se
    il prompt di allora coincide (niente ritrascrizione automatica: i tempi Parakeet e la post-correzione si
    ottengono con --force, oppure con --timing parakeet esplicito). Ritorna (fresco, dettagli)."""
    if not (words_json.exists() and srt.exists()):
        return False, {}
    if words_json.stat().st_mtime < audio.stat().st_mtime:
        return False, {}
    try:
        old = yc.read_json(words_json)
    except Exception:
        return False, {}
    if old.get("engine_id") != engine or old.get("pipeline_version") != PIPELINE_VERSION:
        return False, {}
    if (old.get("postprocess_version") or 1) >= 2:
        same_timing = timing_mode is None or old.get("timing_mode") == timing_mode or \
            (not timing_explicit and old.get("timing_mode") == "parakeet")
        return old.get("prompt") == prompt and same_timing, {}
    if timing_explicit and timing_mode not in (None, "whisper"):
        return False, {}
    fresh = old.get("prompt") in {prompt, legacy_prompt}
    return fresh, ({"upgrade_available": "transcript della pipeline precedente (tempi whisper, niente "
                                          "post-correzione): --force per tempi Parakeet, correzione dei nomi e "
                                          "lista d'ascolto"} if fresh else {})


REFLAG_LIST_MAX = 200  # parole cambiate elencate nel JSON (il totale è sempre in changed_total)


def reflag_file(words_json: Path) -> dict:
    """Riclassifica analysis/transcript.words.json senza rifare l'ASR. Scrive solo se cambia qualcosa."""
    from collections import Counter

    doc = yc.read_json(words_json)
    res = reflag_doc(doc)
    version_changed = doc.get("flags_version") != FLAGS_VERSION
    written = bool(res["changed"]) or version_changed
    if written:
        doc["flags_version"] = FLAGS_VERSION
        doc.setdefault("postprocess", {})["reflagged"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        yc.write_json(words_json, doc)
    by_word = Counter(f"{norm(c['w'])}: {c['from']} → {c['to']}" for c in res["changed"])
    return {"flags_version": FLAGS_VERSION, "flags_version_before": res["version_before"], "written": written,
            "before": res["before"], "after": res["after"], "changed_total": len(res["changed"]),
            "changed_by_word": dict(by_word.most_common()),
            "changed": res["changed"][:REFLAG_LIST_MAX]}


def write_review(path: Path, words: list[dict], spans: list[dict], slots: list[int], pc_report: dict | None,
                 meta: dict) -> dict:
    """analysis/transcript.review.json: cosa ascoltare prima di consegnare (in ordine di priorità)."""
    import postcorrect as pcm

    def ctx(i0: int, i1: int, n: int = 8) -> str:
        a, b = max(0, i0 - n), min(len(words), i1 + n)
        return " ".join(words[k]["w"] if not (i0 <= k < i1) else f"[[{words[k]['w']}]]" for k in range(a, b))

    flags = {round(f["start"], 2): f for f in (pc_report or {}).get("flags", [])}
    unit_rows = []
    for k in slots:
        w = words[k]
        f = flags.get(round(w["start"], 2), {})
        unit_rows.append({"key": f"{w['start']:.2f}", "t": round(w["start"], 2), "ts": yc.fmt_ts(w["start"]),
                          "asr": w["w"], "figure": pcm.unit_figure(words, k), "speaker": w.get("speaker"),
                          "context": ctx(k, k + 1), "facts": f.get("facts", [])})
    starts = [w["start"] for w in words]
    import bisect
    span_rows = []
    for s in spans:
        a, b = s["listen"]
        i0, i1 = bisect.bisect_left(starts, a), bisect.bisect_right(starts, b)
        span_rows.append({**s, "ts": yc.fmt_ts(s["t0"]), "text": " ".join(w["w"] for w in words[i0:i1])})
    prio = [s for s in span_rows if s["priority"]]
    listen = sum(s["listen"][1] - s["listen"][0] for s in span_rows)
    listen_p = sum(s["listen"][1] - s["listen"][0] for s in prio)
    summary = {"unit_slots": len(unit_rows), "spans": len(span_rows), "priority_spans": len(prio),
               "listen_min": round(listen / 60, 1), "priority_listen_min": round(listen_p / 60, 1),
               "hallucination_candidates": sum(1 for s in span_rows if s["hallucination_candidate"]),
               "postcorrect_suspects": len((pc_report or {}).get("suspects", []))}
    yc.write_json(path, {
        "version": 1, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), **meta,
        "about": ("Lista d'ascolto di yt-transcribe. 1) unit_slots: unità dopo una cifra (MRR/ARR), mai risolte in "
                  "automatico: ascoltare e scrivere il testo confermato in analysis/resolutions.json (chiave = "
                  "'key'); 2) spans con priority=true: numeri, nomi e sigle su cui whisper e Parakeet non "
                  "concordano; 3) postcorrect_suspects: nomi che yt-postcorrect non ha corretto da solo. "
                  "Timeline del SORGENTE."),
        "summary": summary, "unit_slots": unit_rows, "spans": span_rows,
        "postcorrect_suspects": (pc_report or {}).get("suspects", [])})
    return summary


def update_resolutions_template(path: Path, keys: list[str]) -> int:
    """Aggiunge a analysis/resolutions.json le chiavi degli slot nuovi (valore vuoto); non tocca il resto."""
    try:
        data = yc.read_json(path) if path.exists() else {}
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    data.setdefault("about", "Compilare SOLO dopo l'ascolto (clip/istanti in analysis/transcript.review.json): "
                             "\"resolved\" = {chiave: testo confermato, es. \"MRR\"}; vuoto = da ascoltare, la "
                             "consegna dei sottotitoli resta bloccata. \"slots\" = altre parole da confermare "
                             "[{t, from, placeholder, reason}]. Mai compilare a intuito.")
    flat = "resolved" not in data and any(re.fullmatch(r"\d+\.\d\d", k) for k in data)
    target = data if flat else data.setdefault("resolved", {})
    data.setdefault("slots", [])
    added = 0
    for k in keys:
        if k not in target:
            target[k] = ""
            added += 1
    if added or not path.exists():
        yc.write_json(path, data)
    return added


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="yt-transcribe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--engine", choices=["whisper", "parakeet"], default="whisper",
                    help="motore del TESTO (default whisper; parakeet = A/B senza prompt)")
    ap.add_argument("--timing", choices=["auto", "parakeet", "whisper"], default="auto",
                    help="tempi delle parole: parakeet (allineati sul testo whisper), whisper (token), "
                         "auto = parakeet se installato (default)")
    ap.add_argument("--prompt-extra", default=None, help="termini aggiuntivi per il glossario, separati da virgola")
    ap.add_argument("--prompt-budget", type=int, default=None,
                    help="token massimi del prompt (default: 480 caratteri ≈171 token; 110 = prompt corto, "
                         "più esitazioni trovate)")
    ap.add_argument("--glossary-prompt", action=argparse.BooleanOptionalAction, default=True,
                    help="usa i prompt_terms di analysis/glossary.json nel prompt (--no-glossary-prompt: il glossario "
                         "serve solo alla post-correzione)")
    ap.add_argument("--lang", default="it", help="lingua parlata (default it)")
    ap.add_argument("--threads", type=int, default=8, help="thread CPU (default 8; la GPU Metal è sempre attiva)")
    ap.add_argument("--model", default=None, help="modello alternativo (ggml whisper o parakeet, secondo --engine)")
    ap.add_argument("--no-cache", action="store_true", help="ignora la cache e ritrascrive")
    ap.add_argument("--no-glossary-fix", action="store_true", help="non correggere i nomi simili al glossario")
    ap.add_argument("--no-postcorrect", action="store_true",
                    help="niente correzione vincolata dei nomi (yt-postcorrect, regole + decisioni)")
    ap.add_argument("--postcorrect-window", type=int, default=60, help="contesto della post-correzione (parole per lato)")
    ap.add_argument("--no-snap", action="store_true", help="non allineare i bordi parola alle pause reali")
    ap.add_argument("--force", action="store_true", help="rifà anche se gli output sono aggiornati")
    ap.add_argument("--reflag", action="store_true",
                    help="riclassifica filler/discourse/false_start del transcript esistente senza rifare l'ASR")
    args = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(args.workdir)
    except FileNotFoundError as e:
        yc.fail(str(e))
    if args.reflag:
        words_json = workdir / "analysis" / "transcript.words.json"
        if not words_json.exists():
            yc.fail(f"manca {words_json}: esegui prima yt-transcribe", workdir=str(workdir))
        try:
            res = reflag_file(words_json)
        except (ValueError, KeyError, TypeError) as e:
            yc.fail(f"{words_json.name} illeggibile: {e}", workdir=str(workdir))
        yc.emit(True, reflag=True, outputs={"words": str(words_json)}, **res,
                fillers=res["after"]["fillers"], discourse=res["after"]["discourse"],
                false_starts=res["after"]["false_starts"], warnings=[])
        return
    project = yc.load_project(workdir)
    audio = yc.analysis_audio(workdir, "16k")
    if not audio.exists():
        yc.fail(f"manca {audio}: esegui prima yt-ingest", workdir=str(workdir))
    rate, ch, width, duration = wav_info(audio)
    if rate != 16000 or ch != 1 or width != 2:
        yc.fail(f"{audio.name} deve essere WAV mono 16 kHz 16 bit (trovato {rate} Hz, {ch} canali, {8 * width} bit)")
    if args.prompt_budget is not None and not (20 <= args.prompt_budget <= gl.WHISPER_PROMPT_MAX_TOKENS):
        yc.fail(f"--prompt-budget {args.prompt_budget}: fra 20 e {gl.WHISPER_PROMPT_MAX_TOKENS} token")

    analysis = workdir / "analysis"
    words_json = analysis / "transcript.words.json"
    srt_path = analysis / "transcript.srt"
    review_path = analysis / "transcript.review.json"
    warnings: list[str] = []
    gdoc = gl.load_glossary_doc(workdir)

    prompt, used_terms, dropped_terms, prompt_info = build_prompt(project, workdir, args.prompt_extra,
                                                                  args.prompt_budget,
                                                                  gdoc if args.glossary_prompt else None)
    legacy_prompt = build_prompt_legacy(project, workdir, args.prompt_extra)[0]
    if args.engine == "whisper":
        model = Path(args.model).expanduser() if args.model else yc.WHISPER_MODEL
        episode_terms = {t.lower() for t in (project.get("glossary_extra") or [])}
        lost = [t for t in dropped_terms if t.lower() in episode_terms]
        if lost:
            warnings.append(f"prompt troppo lungo: esclusi termini dell'EPISODIO ({', '.join(lost)}); "
                            f"accorcia glossary_extra")
        elif dropped_terms:
            log(f"prompt: {len(dropped_terms)} termini esclusi per lunghezza "
                f"(restano disponibili per la correzione dei nomi)")
        engine_label = f"whisper.cpp {model.stem.replace('ggml-', '')}"
    else:
        model = parakeet_model(args.model)
        # Parakeet non usa prompt: il glossario serve solo alla correzione dei nomi
        engine_label = f"parakeet.cpp {model.stem.replace('ggml-', '')}"
    if not model.exists() and args.engine == "whisper":
        yc.fail(f"modello whisper mancante: {model}")
    engine_id = f"{args.engine}:{model.name}"

    # tempi: Parakeet allineato sul testo whisper (default se installato)
    pk_model = parakeet_model(None) if args.engine == "whisper" else model
    pk_ok = bool(yc.which(yc.PARAKEET_CLI)) and pk_model.exists()
    if args.engine == "parakeet":
        timing_mode = "parakeet-token"
    elif args.timing == "whisper":
        timing_mode = "whisper"
    elif pk_ok:
        timing_mode = "parakeet"
    elif args.timing == "parakeet":
        yc.fail(f"--timing parakeet: manca parakeet-cli ({yc.PARAKEET_CLI}) o il modello ({pk_model})")
    else:
        timing_mode = "whisper"
        warnings.append("Parakeet non disponibile: tempi dai token whisper (su un episodio di prova il 23,6 % delle parole sbaglia "
                        "di oltre 0,5 s); installare il modello per i tempi allineati")

    fresh, fresh_info = (False, {}) if args.force else outputs_fresh(
        words_json, srt_path, audio, engine_id, prompt, legacy_prompt,
        timing_mode if args.engine == "whisper" else None, args.timing != "auto")
    if fresh:
        old = yc.read_json(words_json)
        extra: dict = dict(fresh_info)
        if old.get("flags_version") != FLAGS_VERSION:
            # transcript in cache con lo schema vecchio dei flag (senza 'discourse'): riclassifico e basta
            res = reflag_file(words_json)
            extra.update({"reflagged": True, "changed_total": res["changed_total"],
                          "changed_by_word": res["changed_by_word"], "flags_before": res["before"]})
            warnings.append(f"flag riclassificati (schema {res['flags_version_before']} → {FLAGS_VERSION}): "
                            f"{res['changed_total']} parole cambiate")
            old = yc.read_json(words_json)
        counts = flag_counts(old.get("words", []))
        if fresh_info.get("upgrade_available"):
            warnings.append(fresh_info["upgrade_available"])
        yc.emit(True, skipped=True, reason="output già aggiornati (usa --force per rifare)",
                outputs={"words": str(words_json), "srt": str(srt_path),
                         "review": str(review_path) if review_path.exists() else None},
                words=len(old.get("words", [])), duration=old.get("duration"),
                timing=old.get("timing"), postprocess_version=old.get("postprocess_version", 1),
                fillers=counts["fillers"], discourse=counts["discourse"], false_starts=counts["false_starts"],
                filler_kinds=counts["filler_kinds"], **extra, warnings=warnings)
        return

    log(f"audio: {audio} ({yc.fmt_ts(duration)}), motore {engine_label}, tempi {timing_mode}")
    log(f"prompt ({prompt_info['tokens']} token): {prompt}")
    audio_sha = sha256_audio(audio)
    salt = prompt if args.engine == "whisper" else PARAKEET_PARSER
    key = cache_key(audio_sha, args.engine, model, salt, args.lang)
    energy = Energy(audio)

    raw_path = CACHE_DIR / f"{key}.{args.engine}.json"
    meta_path = CACHE_DIR / f"{key}.meta.json"
    from_cache = raw_path.exists() and meta_path.exists() and not args.no_cache
    t_start = time.time()
    try:
        if from_cache:
            log(f"cache: {raw_path.name}")
            meta = yc.read_json(meta_path)
        elif args.engine == "whisper":
            raw_path, meta_path, meta = run_whisper(audio, model, prompt, args.lang, args.threads,
                                                     workdir, key, duration)
        else:
            raw_path, meta_path, meta = run_parakeet(audio, model, args.threads, workdir, key, duration, energy)
    except RuntimeError as e:
        yc.fail(str(e), workdir=str(workdir))
    engine_s = time.time() - t_start

    # token → parole (timeline originale)
    retime_stats: dict | None = None
    spans: list[dict] = []
    pk_meta: dict = {}
    dup_drops: list[dict] = []
    if args.engine == "whisper":
        data = read_whisper_json(raw_path)
        vad = meta.get("vad_segments") or []
        if vad and not tokens_need_mapping(data, vad):
            warnings.append("token whisper già sul timeline originale (versione diversa da 1.9.5?): niente rimappatura VAD")
            vad = []
        tmap = vad_mapper(vad)
        segs = whisper_to_words(data, tmap)
        timing = "token"
        if not meta.get("vad_segments"):
            warnings.append("nessun segmento VAD nel log: tempi non rimappati (VAD spento o audio muto?)")
        if timing_mode == "parakeet":
            pk_key = cache_key(audio_sha, "parakeet", pk_model, PARAKEET_PARSER, args.lang)
            pk_raw, pk_meta_path = CACHE_DIR / f"{pk_key}.parakeet.json", CACHE_DIR / f"{pk_key}.meta.json"
            try:
                if pk_raw.exists() and pk_meta_path.exists() and not args.no_cache:
                    log(f"cache Parakeet: {pk_raw.name}")
                    pk_meta = yc.read_json(pk_meta_path)
                else:
                    pk_raw, pk_meta_path, pk_meta = run_parakeet(audio, pk_model, args.threads, workdir, pk_key,
                                                                 duration, energy)
                P = parakeet_words(pk_raw)
            except RuntimeError as e:
                if args.timing == "parakeet":
                    yc.fail(str(e), workdir=str(workdir))
                warnings.append(f"Parakeet fallito, tempi whisper: {str(e)[:300]}")
                P = []
                timing_mode = "whisper"
            if P:
                W = [w for s in segs for w in s["words"]]
                newW, retime_stats, ops = retime_with_parakeet(W, P, energy)
                spans = disagreement_spans(W, P, ops, newW)
                segs = regroup(segs, newW)
                timing = "parakeet-aligned"
                for sg in segs:
                    dups = [w for w in sg["words"] if w.get("dup_no_audio")]
                    if dups:
                        dup_drops.append({"start": round(dups[0]["start"], 2), "reason": "doppione-senza-audio",
                                          "words_removed": len(dups),
                                          "text": " ".join(w["w"] for w in dups)[:120]})
                        sg["words"] = [w for w in sg["words"] if not w.get("dup_no_audio")]
                segs = [sg for sg in segs if sg["words"]]
                log(f"tempi Parakeet: {retime_stats['anchored_pct']} % delle parole allineate, "
                    f"{retime_stats['interpolated']} stimate ({retime_stats['voiced_placed']} sulla voce)")
            elif timing_mode == "parakeet":
                warnings.append("Parakeet senza parole: tempi whisper")
                timing_mode = "whisper"
    else:
        segs = yc.read_json(raw_path)["segments"]
        timing = "approx" if meta.get("approx") else "parakeet-token"
        if meta.get("approx"):
            warnings.append("Parakeet senza tempi dei token: parole distribuite in modo uniforme (approx)")

    n_raw = sum(len(s["words"]) for s in segs)
    segs, dropped = filter_hallucinations(segs, energy, prompt if args.engine == "whisper" else "")
    dropped = dup_drops + dropped
    flat = [w for s in segs for w in s["words"]]
    episode_glossary = list(project.get("glossary_extra") or []) + gl.split_extra(args.prompt_extra)
    fixes, suspects = ([], []) if args.no_glossary_fix else \
        glossary_fix(flat, episode_glossary, used_terms + dropped_terms)
    moved = 0 if (args.no_snap or timing == "approx") else snap_to_pauses(flat, energy)
    words, segments = finalize(segs, duration)
    asr_segments = [[s["w0"], s["w1"]] for s in segments]
    for f in fixes:  # indici finali delle parole corrette
        f["i"] = next((w["i"] for w in words if w.get("fixed_from") == f["from"]
                       and abs(w["start"] - f["start"]) < 1.0), None)

    # speaker già noti (yt-speakers eseguito prima di una ritrascrizione): li riassegniamo
    spk_note = None
    carry: dict = {}
    spk_json = analysis / "speakers.json"
    if spk_json.exists() and spk_json.stat().st_mtime >= audio.stat().st_mtime:
        try:
            import speakers as spk_mod
            turns = yc.read_json(spk_json)
            spk_mod.assign_words(words, turns)
            segments = spk_mod.split_segments(words, segments)
            spk_note = "speaker riassegnati da analysis/speakers.json"
            meta_spk = workdir / "logs" / "speakers.meta.json"
            if meta_spk.exists():
                carry["diarization"] = yc.read_json(meta_spk)
            if project.get("speakers"):
                carry["speaker_names"] = project["speakers"]
        except Exception as e:  # non bloccante
            warnings.append(f"speaker non riassegnati: {e}")

    # flag filler / discourse / false_start sulle parole finali (dopo gli speaker: le ripetizioni
    # contano solo dentro lo stesso turno)
    classify_words(words)

    # correzione vincolata dei nomi (regole + decisioni già prese), poi slot delle unità
    import postcorrect as pcm
    pc_report: dict | None = None
    if not args.no_postcorrect:
        try:
            extra_terms = gl.split_extra(args.prompt_extra)
            gdoc_pc = pcm.default_glossary(workdir, project, extra_terms)
            dec = analysis / "corrections.decisions.json"
            new, pc_report = pcm.correct_doc({"words": words, "segments": segments, "asr_segments": asr_segments},
                                             gdoc_pc, pcm.with_extra(project, extra_terms), args.postcorrect_window,
                                             dec if dec.exists() else None)
            words, segments, asr_segments = new["words"], new["segments"], new["asr_segments"]
            pcm.write_candidates(analysis / "postcorrect.candidates.json", pc_report, words_json)
        except Exception as e:  # non bloccante: il transcript resta quello di whisper
            warnings.append(f"post-correzione saltata: {e}")
            pc_report = None
    slots = pcm.find_unit_slots(words)
    for k in slots:
        words[k]["unit_review"] = True
    counts = flag_counts(words)
    n_fill = counts["fillers"]
    hes = counts["filler_kinds"].get("hesitation", 0)
    hes_rate = round(hes / (duration / 60), 2) if duration else 0.0

    doc = {
        "version": 1,
        "language": args.lang,
        "engine": engine_label,
        "engine_id": engine_id,
        "engine_version": meta.get("engine_version"),
        "pipeline_version": PIPELINE_VERSION,
        "postprocess_version": POSTPROCESS_VERSION,
        "flags_version": FLAGS_VERSION,
        "prompt": prompt,
        "prompt_extra": gl.split_extra(args.prompt_extra),
        "prompt_info": prompt_info,
        "glossary": used_terms,
        "timing": timing,
        "timing_mode": timing_mode,
        "duration": round(duration, 3),
        "audio_sha256": audio_sha,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "postprocess": {
            "words_raw": n_raw, "dropped": dropped, "glossary_fixes": fixes, "glossary_suspects": suspects,
            "snapped_boundaries": moved, "fillers": n_fill, "discourse": counts["discourse"],
            "false_starts": counts["false_starts"], "filler_kinds": counts["filler_kinds"],
            "vad_segments": len(meta.get("vad_segments") or []),
            "retime": retime_stats,
            "postcorrect": None if pc_report is None else {
                "version": pc_report["version"], "applied": pc_report["applied"],
                "applied_by_rule": pc_report["applied_by_rule"], "suspects": len(pc_report["suspects"]),
                "flags": len(pc_report["flags"]), "window": pc_report["window"],
                "decisions_accepted": pc_report["decisions_accepted"],
                "decisions_rejected": pc_report["decisions_rejected"]},
            "unit_slots": len(slots),
            "hesitations_per_min": hes_rate,
            "energy": {"floor_db": round(energy.floor, 1), "threshold_db": round(energy.thr, 1),
                       "digital_silence_pct": round(100 * energy.digital_silence, 2)},
        },
        "review": str(review_path),
        "words": words,
        "segments": segments,
        "asr_segments": asr_segments,   # [w0, w1) dei segmenti originali dell'ASR (base per yt-speakers)
        **carry,
    }
    yc.write_json(words_json, doc)
    srt_path.write_text(build_srt(words))
    if pc_report and pc_report["applied"]:
        pcm.append_log(analysis / "corrections.json", pc_report, "transcribe-rules", words_json)
    review = write_review(review_path, words, spans, slots, pc_report,
                          {"timing": timing, "engine": engine_label, "transcript": str(words_json)})
    added_keys = update_resolutions_template(analysis / "resolutions.json",
                                             [f"{words[k]['start']:.2f}" for k in slots]) if slots else 0

    if project.get("status") in (None, "new", "ingested"):
        yc.update_project(workdir, status="transcribed")

    engine_total = (meta.get("elapsed_s") or engine_s) + (pk_meta.get("elapsed_s") or 0.0)
    rtf = engine_total / duration if duration else None
    if dropped:
        warnings.append(f"{len(dropped)} segmenti/ripetizioni scartati come allucinazioni (vedi postprocess.dropped)")
    if fixes:
        from collections import Counter
        agg = Counter((norm(f["from"]), norm(f["to"])) for f in fixes)
        warnings.append("correzioni glossario (verifica): " +
                        ", ".join(f"{a}→{b} ×{n}" for (a, b), n in agg.most_common(8)))
    if suspects:
        warnings.append(f"{len(suspects)} parole simili al glossario del canale NON corrette (postprocess.glossary_suspects)")
    if pc_report and pc_report["suspects"]:
        warnings.append(f"{len(pc_report['suspects'])} nomi sospetti da rivedere (analysis/postcorrect.candidates.json, "
                        f"poi analysis/corrections.decisions.json e yt-postcorrect)")
    if slots:
        warnings.append(f"{len(slots)} unità dopo una cifra (MRR/ARR) da ascoltare: mai risolte in automatico "
                        f"(transcript.review.json → analysis/resolutions.json)")
    if args.engine == "whisper" and duration >= 300 and hes_rate < HESITATION_MIN_PER_MIN:
        warnings.append(f"esitazioni {hes_rate}/min (< {HESITATION_MIN_PER_MIN:g}): il prompt può averle soppresse "
                        f"(su un episodio di prova --prompt-budget 110 le ha quasi raddoppiate); per tagliare i filler "
                        f"valuta yt-transcribe --prompt-budget 110 --force")
    yc.emit(True,
            outputs={"words": str(words_json), "srt": str(srt_path), "review": str(review_path),
                     "candidates": str(analysis / "postcorrect.candidates.json") if pc_report else None,
                     "resolutions": str(analysis / "resolutions.json") if slots else None},
            engine=engine_label, timing=timing, from_cache=from_cache,
            duration=round(duration, 1), words=len(words), segments=len(segments),
            fillers=n_fill, discourse=counts["discourse"], false_starts=counts["false_starts"],
            filler_kinds=counts["filler_kinds"], hesitations_per_min=hes_rate,
            engine_seconds=round(engine_total, 1), whisper_seconds=meta.get("elapsed_s"),
            parakeet_seconds=pk_meta.get("elapsed_s"),
            seconds_per_audio_minute=round(rtf * 60, 2) if rtf else None,
            wall_seconds=round(time.time() - t_start, 1),
            prompt_tokens=prompt_info["tokens"],
            retime=None if not retime_stats else {k: retime_stats[k] for k in
                                                  ("anchored_pct", "interpolated", "voiced_placed")},
            glossary_fixes=len(fixes), glossary_suspects=len(suspects), dropped=len(dropped), snapped=moved,
            postcorrect=None if not pc_report else {"applied": pc_report["applied"],
                                                    "applied_by_rule": pc_report["applied_by_rule"],
                                                    "suspects": len(pc_report["suspects"]),
                                                    "flags": len(pc_report["flags"])},
            unit_slots=len(slots), resolutions_keys_added=added_keys, review=review,
            speakers=spk_note, cache=str(raw_path), warnings=warnings)


if __name__ == "__main__":
    main()
