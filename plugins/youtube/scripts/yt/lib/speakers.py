"""yt-speakers — chi parla quando (diarizzazione locale con Senko) e speaker su ogni parola.

Uso:
  yt-speakers WORKDIR                          # diarizza + assegna lo speaker a ogni parola
  yt-speakers WORKDIR --num-speakers 3         # numero di voci noto (es. 2 host + ospite)
  yt-speakers WORKDIR --map S0="Nome Cognome",S1="Paolo Bianchi"   # nomi in project.json
  yt-speakers WORKDIR --force                  # rifà la diarizzazione

Input:  analysis/audio16k.wav (mono 16 kHz) · analysis/transcript.words.json (yt-transcribe)
Output: analysis/speakers.json  [{start, end, speaker}]  (S0 = chi parla di più, poi S1, …)
        transcript.words.json   campo "speaker" su ogni parola (OVERLAP se due voci coprono
                                ciascuna >50% della parola; null se nessun turno vicino),
                                segmenti spezzati ai cambi di speaker, blocco "diarization"
        transcript.srt          rigenerato (i sottotitoli vanno a capo al cambio di speaker)

Senko (CoreML/ANE, pinned 1bcb090) gira nel suo venv (ytcore.SENKO_PY) in un processo separato.
Limiti noti: embedding addestrati su inglese/cinese, nessuna sovrapposizione in uscita (solo la
voce dominante), sotto 20 min clustering spettrale, sopra UMAP+HDBSCAN (con --num-speakers si
forza lo spettrale con numero fisso). Il riepilogo JSON riporta per ogni speaker tempo di parola
e frasi campione: servono per decidere la mappa --map S0=Nome.
"""
from __future__ import annotations

import argparse
import json
import bisect
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import ytcore as yc

SENKO_RUNNER = r"""
import json, sys, time, warnings
warnings.filterwarnings("ignore")
wav, out, k, accurate = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4] == "1"
t0 = time.time()
import senko
d = senko.Diarizer(device="auto", warmup=False, quiet=True)  # warmup = solo benchmark, costa ~60 s
t_init = time.time() - t0
if k > 0:
    d.spectral_cluster.cluster.k = k                  # numero di speaker fissato
    d.umap_hdbscan_cluster = d.spectral_cluster      # anche oltre i 20 min
r = d.diarize(wav, accurate=True if accurate else None, generate_colors=False)
res = {"init_s": round(t_init, 2), "total_s": round(time.time() - t0, 2)}
if r is None:
    res.update(raw=[], merged=[], vad=0)
else:
    res.update(raw=r["raw_segments"], merged=r["merged_segments"], vad=len(r["vad"]),
               timing=r.get("timing_stats", {}), n_raw=r["raw_speakers_detected"],
               n_merged=r["merged_speakers_detected"])
with open(out, "w") as fh:
    json.dump(res, fh)
"""

SENKO_SHA = "1bcb090"


# ── Diarizzazione ───────────────────────────────────────────────────────────
def run_senko(audio: Path, num_speakers: int | None, accurate: bool, logfile: Path) -> dict:
    if not Path(yc.SENKO_PY).exists():
        raise RuntimeError(f"Python di Senko non trovato: {yc.SENKO_PY}")
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yt-senko-") as tmp:
        out = Path(tmp) / "senko.json"
        # -I: niente cwd/site utente sul sys.path del processo Senko
        cmd = [str(yc.SENKO_PY), "-I", "-c", SENKO_RUNNER, str(audio), str(out),
               str(num_speakers or 0), "1" if accurate else "0"]
        yc.log("$ senko", audio.name, f"(num_speakers={num_speakers or 'auto'})")
        t0 = time.time()
        with open(logfile, "w") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0 or not out.exists():
            tail = logfile.read_text(errors="replace")[-2500:]
            raise RuntimeError(f"Senko fallito (exit {proc.returncode}). Log {logfile}:\n{tail}")
        res = yc.read_json(out)
        res["wall_s"] = round(time.time() - t0, 2)
        return res


def normalize_turns(raw: list[dict], gap_merge: float = 0.3) -> tuple[list[dict], dict[str, str]]:
    """SPEAKER_01.. di Senko → S0.. (S0 = più tempo di parola); unisce turni contigui dello stesso speaker."""
    talk: dict[str, float] = {}
    for s in raw:
        talk[s["speaker"]] = talk.get(s["speaker"], 0.0) + s["end"] - s["start"]
    order = sorted(talk, key=lambda k: -talk[k])
    mapping = {old: f"S{i}" for i, old in enumerate(order)}
    turns: list[dict] = []
    for s in sorted(raw, key=lambda x: x["start"]):
        spk = mapping[s["speaker"]]
        a, b = round(float(s["start"]), 3), round(float(s["end"]), 3)
        if b <= a:
            continue
        if turns and turns[-1]["speaker"] == spk and a - turns[-1]["end"] <= gap_merge:
            turns[-1]["end"] = max(turns[-1]["end"], b)
        else:
            turns.append({"start": a, "end": b, "speaker": spk})
    return turns, mapping


# ── Assegnazione parole (usata anche da yt-transcribe) ──────────────────────
def assign_words(words: list[dict], turns: list[dict], overlap_frac: float = 0.5,
                 nearest_max: float = 1.0) -> dict[str, int]:
    """Scrive w['speaker'] = speaker con massima sovrapposizione temporale.

    OVERLAP se almeno due speaker coprono ciascuno > overlap_frac della parola (possibile
    solo con diarizzatori che restituiscono turni sovrapposti). Parola fuori da ogni turno:
    speaker del turno più vicino entro nearest_max secondi, altrimenti None.
    """
    turns = sorted(turns, key=lambda t: t["start"])
    starts = [t["start"] for t in turns]
    max_len = max((t["end"] - t["start"] for t in turns), default=0.0)
    stats: dict[str, int] = {}
    for w in words:
        a, b = float(w["start"]), float(w["end"])
        dur = max(b - a, 1e-3)
        lo = bisect.bisect_left(starts, a - max_len)
        hi = bisect.bisect_right(starts, b)
        cover: dict[str, float] = {}
        for t in turns[lo:hi]:
            ov = min(b, t["end"]) - max(a, t["start"])
            if ov > 0:
                cover[t["speaker"]] = cover.get(t["speaker"], 0.0) + ov
        if cover:
            big = [s for s, ov in cover.items() if ov / dur > overlap_frac]
            spk = "OVERLAP" if len(big) >= 2 else max(cover, key=cover.get)
        else:
            spk, best = None, nearest_max
            mid = (a + b) / 2
            j = bisect.bisect_left(starts, mid)
            for t in turns[max(0, j - 3): j + 3]:
                d = max(t["start"] - mid, mid - t["end"], 0.0)
                if d <= best:
                    spk, best = t["speaker"], d
        w["speaker"] = spk
    refine_changes(words)
    for w in words:
        stats[str(w.get("speaker"))] = stats.get(str(w.get("speaker")), 0) + 1
    return stats


def refine_changes(words: list[dict], max_shift: float = 1.0, min_gap: float = 0.15) -> int:
    """Sposta i cambi di speaker sulla pausa tra parole più vicina.

    I turni di Senko hanno una risoluzione di ~0.6 s (finestre di 1.5 s): un cambio può cadere
    a metà frase ("Ciao a | tutti, grazie"). Se entro ±max_shift c'è una pausa tra parole
    (≥ min_gap, 1.5× quella al cambio attuale; bonus a fine periodo) il cambio si sposta lì.
    """
    moved = 0
    real = lambda s: s not in (None, "OVERLAP")  # noqa: E731
    k = 1
    while k < len(words):
        a, b = words[k - 1].get("speaker"), words[k].get("speaker")
        if not (real(a) and real(b) and a != b):
            k += 1
            continue
        t_change = words[k]["start"]
        lo = k
        while lo - 1 > 0 and words[lo - 1].get("speaker") == a and t_change - words[lo - 1]["start"] <= max_shift:
            lo -= 1
        hi = k
        while hi + 1 < len(words) and words[hi].get("speaker") == b and words[hi + 1]["start"] - t_change <= max_shift:
            hi += 1

        def score(j: int) -> float:
            gap = words[j]["start"] - words[j - 1]["end"]
            return gap + (0.25 if words[j - 1]["w"].endswith((".", "?", "!", "…")) else 0.0)

        best = max(range(max(lo, 1), hi + 1), key=score)
        if best != k and words[best]["start"] - words[best - 1]["end"] >= min_gap and score(best) >= 1.5 * max(score(k), 0.02):
            if best < k:
                for w in words[best:k]:
                    w["speaker"] = b
            else:
                for w in words[k:best]:
                    w["speaker"] = a
            moved += 1
            k = best + 1
        else:
            k += 1
    return moved


def split_segments(words: list[dict], segments: list[dict] | None = None) -> list[dict]:
    """Ricostruisce i segmenti spezzandoli ai cambi di speaker (None/OVERLAP non spezzano)."""
    if not words:
        return []
    bounds = [(s["w0"], s["w1"]) for s in segments] if segments else [(0, len(words))]
    out: list[dict] = []

    def flush(ws: list[dict], spk: str | None) -> None:
        if ws:
            out.append({"i": len(out), "start": ws[0]["start"], "end": ws[-1]["end"],
                        "text": " ".join(x["w"] for x in ws), "speaker": spk,
                        "w0": ws[0]["i"], "w1": ws[-1]["i"] + 1})

    for w0, w1 in bounds:
        run: list[dict] = []
        spk = None
        for w in words[w0:w1]:
            s = w.get("speaker")
            if s in (None, "OVERLAP") or s == spk or spk is None:
                if spk is None and s not in (None, "OVERLAP"):
                    spk = s
                run.append(w)
                continue
            flush(run, spk)
            run, spk = [w], s
        flush(run, spk)
    return out


def speaker_summary(words: list[dict], segments: list[dict], turns: list[dict], names: dict) -> dict:
    talk: dict[str, float] = {}
    for t in turns:
        talk[t["speaker"]] = talk.get(t["speaker"], 0.0) + t["end"] - t["start"]
    total = sum(talk.values()) or 1.0
    out = {}
    for spk in sorted(talk, key=lambda s: int(s[1:]) if s[1:].isdigit() else 99):
        segs = [s for s in segments if s.get("speaker") == spk and len(s["text"]) > 25]
        samples = [f"[{yc.fmt_ts(s['start'], 'yt')}] {s['text'][:110]}" for s in segs[:3]]
        if len(segs) > 6:
            s = segs[len(segs) // 2]
            samples.append(f"[{yc.fmt_ts(s['start'], 'yt')}] {s['text'][:110]}")
        out[spk] = {"name": names.get(spk), "talk_s": round(talk[spk], 1),
                    "share": round(talk[spk] / total, 3),
                    "words": sum(1 for w in words if w.get("speaker") == spk), "samples": samples}
    return out


def parse_map(text: str | None) -> dict[str, str]:
    out = {}
    if not text:
        return out
    for part in text.split(","):
        if "=" not in part:
            raise ValueError(f"--map: atteso S0=Nome, trovato '{part}'")
        k, v = part.split("=", 1)
        k, v = k.strip().upper(), v.strip().strip('"').strip("'")
        if not k.startswith("S") or not k[1:].isdigit() or not v:
            raise ValueError(f"--map: chiave non valida '{k}' (usa S0, S1, …)")
        out[k] = v
    return out


def check_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as fh:
        ok = fh.getframerate() == 16000 and fh.getnchannels() == 1 and fh.getsampwidth() == 2
    if not ok:
        raise ValueError(f"{path.name} deve essere WAV mono 16 kHz 16 bit (rifai yt-ingest)")


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        prog="yt-speakers", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--num-speakers", type=int, default=None, help="numero di voci se noto (default: automatico)")
    ap.add_argument("--map", default=None, help='nomi degli speaker: S0="Nome Cognome",S1=…  (salvati in project.json)')
    ap.add_argument("--accurate", action="store_true", help="finestre più fitte per gli embedding (più lento)")
    ap.add_argument("--force", action="store_true", help="rifà la diarizzazione anche se speakers.json è aggiornato")
    args = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(args.workdir)
        names_new = parse_map(args.map)
    except (FileNotFoundError, ValueError) as e:
        yc.fail(str(e))
    analysis = workdir / "analysis"
    audio = yc.analysis_audio(workdir, "16k")
    words_json = analysis / "transcript.words.json"
    spk_json = analysis / "speakers.json"
    warnings: list[str] = []

    project = yc.load_project(workdir)
    if names_new:
        project = yc.update_project(workdir, speakers=names_new)
    names = project.get("speakers") or {}

    if not audio.exists():
        yc.fail(f"manca {audio}: esegui prima yt-ingest")
    try:
        check_wav(audio)
    except ValueError as e:
        yc.fail(str(e))

    diar_info = None
    meta_json = workdir / "logs" / "speakers.meta.json"   # metadati Senko (speakers.json resta una lista)
    fresh = spk_json.exists() and spk_json.stat().st_mtime >= audio.stat().st_mtime
    num_req = args.num_speakers
    if fresh and not args.force:
        try:
            prev = yc.read_json(meta_json) if meta_json.exists() else {}
        except Exception:
            prev = {}
        if num_req and prev.get("num_speakers_requested") != num_req:
            fresh = False
    t0 = time.time()
    if fresh and not args.force:
        turns = yc.read_json(spk_json)
        yc.log(f"speakers.json aggiornato ({len(turns)} turni): salto la diarizzazione")
        try:
            diar_info = yc.read_json(meta_json) if meta_json.exists() else None
        except Exception:
            diar_info = None
    else:
        try:
            res = run_senko(audio, num_req, args.accurate, workdir / "logs" / "speakers.senko.log")
        except RuntimeError as e:
            yc.fail(str(e))
        turns, mapping = normalize_turns(res.get("raw") or [])
        merged, _ = normalize_turns(res.get("merged") or [])
        if not turns:
            warnings.append("Senko non ha trovato voce nell'audio")
        yc.write_json(spk_json, turns)
        diar_info = {"engine": f"senko {SENKO_SHA} (CoreML)", "num_speakers_requested": num_req,
                     "speakers_detected": len({t['speaker'] for t in turns}),
                     "turns": len(turns), "turns_merged": len(merged),
                     "senko_seconds": res.get("total_s"), "senko_init_seconds": res.get("init_s"),
                     "diarize_seconds": (res.get("timing") or {}).get("total_time"), "wall_seconds": res.get("wall_s"),
                     "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        yc.write_json(meta_json, diar_info)
        yc.log(f"Senko: {diar_info['speakers_detected']} speaker, {len(turns)} turni in {res.get('total_s')} s")

    outputs = {"speakers": str(spk_json)}
    summary = {}
    stats = {}
    if words_json.exists():
        doc = yc.read_json(words_json)
        before = json.dumps(doc, sort_keys=True, ensure_ascii=False, default=str)
        words = doc.get("words", [])
        stats = assign_words(words, turns)
        # base = segmentazione originale dell'ASR (asr_segments), così rilanci ripetuti non frammentano
        base = [{"w0": a, "w1": b} for a, b in doc.get("asr_segments") or []] or doc.get("segments")
        doc["segments"] = split_segments(words, base)
        if diar_info:
            doc["diarization"] = diar_info
        doc["speaker_names"] = names
        # riscrive solo se qualcosa è cambiato: un rilancio a vuoto non deve rendere "vecchi" tutti gli
        # output a valle (pack, captions, chapters, clips…), che si basano sulla data dei file
        unchanged = json.dumps(doc, sort_keys=True, ensure_ascii=False, default=str) == before
        if unchanged:
            yc.log("transcript.words.json già aggiornato: non lo riscrivo")
        else:
            yc.write_json(words_json, doc)
        outputs["words"] = str(words_json)
        try:  # sottotitoli sorgente: a capo anche al cambio di speaker
            from transcribe import build_srt
            srt_path = analysis / "transcript.srt"
            srt_text = build_srt(words)
            if not (srt_path.exists() and srt_path.read_text() == srt_text):
                srt_path.write_text(srt_text)
            outputs["srt"] = str(srt_path)
        except Exception as e:
            warnings.append(f"transcript.srt non rigenerato: {e}")
        summary = speaker_summary(words, doc["segments"], turns, names)
        unassigned = stats.get("None", 0)
        if words and unassigned / len(words) > 0.05:
            warnings.append(f"{unassigned} parole senza speaker (fuori dai turni di Senko)")
    else:
        warnings.append("transcript.words.json assente: scritto solo speakers.json (esegui yt-transcribe, poi rilancia)")
        summary = speaker_summary([], [], turns, names)

    if names and not set(summary) <= set(names):
        missing = sorted(set(summary) - set(names))
        warnings.append(f"speaker senza nome: {', '.join(missing)} (usa --map)")
    n_spk = len(summary)
    if n_spk > 4:
        warnings.append(f"{n_spk} speaker rilevati: troppi per un podcast? prova --num-speakers N")
    yc.emit(True, outputs=outputs, speakers=summary, words_by_speaker=stats,
            diarization=diar_info, names=names, seconds=round(time.time() - t0, 1), warnings=warnings)


if __name__ == "__main__":
    main()
