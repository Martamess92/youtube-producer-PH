"""yt-chapters — capitoli YouTube validati e agganciati ai silenzi.

Legge edit/chapters.draft.json, porta i tempi sul timeline di OUTPUT (se il draft è sul sorgente
e c'è edit/assembled.timeline.json), aggancia ogni confine (tranne il primo) alla pausa o fine
frase più vicina entro ±3 s (pause tra parole del transcript; senza transcript, pause
nell'audio con soglia adattiva), valida le regole YouTube e scrive:

  deliver/chapters.txt   formato descrizione YouTube (0:00 Titolo / 12:34 Titolo / 1:02:03 Titolo)
  deliver/chapters.json  dettaglio: tempi draft → mappati → agganciati, motivo, durata, esito

Regole (support.google.com/youtube/answer/9884579): primo capitolo a 0:00, almeno 3 capitoli,
ognuno ≥10 s, ordine crescente. In più: titoli ≤60 caratteri, su una riga.

Draft accettati:
  [{"t": 0, "title": "…"}, {"t": "5:12.5", "title": "…"}]
  {"timeline": "source|output", "chapters": [ … ]}

Esempi:
  yt-chapters WORKDIR                                   # draft e timeline di default
  yt-chapters WORKDIR --draft edit/chapters.draft.json --timeline none   # master non tagliato
  yt-chapters WORKDIR --draft-timeline source           # il draft (lista) usa tempi del sorgente
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
from pathlib import Path

import captions as cap
import ytcore
from ytcore import log

YT_MIN_CHAPTERS = 3
YT_MIN_LEN = 10.0


def load_draft(path: Path) -> tuple[list[dict], str | None]:
    data = ytcore.read_json(path)
    declared = None
    if isinstance(data, dict):
        declared = data.get("timeline")
        items = data.get("chapters", [])
    else:
        items = data
    out = []
    for k, it in enumerate(items):
        t = it.get("t", it.get("time", it.get("start")))
        if t is None or "title" not in it:
            raise ValueError(f"Capitolo {k + 1} senza 't' o 'title': {it}")
        out.append({"n": k + 1, "draft_t": ytcore.parse_ts(t), "title": str(it["title"])})
    if declared and declared not in ("source", "output"):
        raise ValueError(f"timeline del draft non valido: {declared!r} (source|output)")
    return out, declared


def media_duration(workdir: Path, timeline: list[dict] | None) -> float | None:
    if timeline:
        return max(s["out_end"] for s in timeline)
    try:
        return ytcore.media_duration(ytcore.source_path(workdir))
    except Exception:  # noqa: BLE001
        return None


def word_candidates(words: list[dict]) -> list[dict]:
    """Punti d'inizio frase/turno: pausa ≥0.25 s, o fine frase con pausa ≥0.1 s."""
    cands = []
    for a, b in zip(words, words[1:]):
        gap = b["start"] - a["end"]
        sent = bool(cap.SENT_END.search(a["w"]))
        if gap >= 0.25 or (sent and gap >= 0.1):
            cands.append({"t": b["start"], "gap_start": a["end"], "gap": round(gap, 3), "sentence_end": sent,
                          "speaker_change": a.get("speaker") != b.get("speaker"),
                          "kind": "sentence_gap" if sent else "word_gap"})
    return cands


def silence_candidates(audio: Path, noise_db: float | None, min_dur: float = 0.25,
                       dec_args: list[str] | None = None) -> tuple[list[dict], float]:
    """Fallback senza transcript: pause nell'audio (16 kHz mono, finestre RMS da 20 ms).

    Soglia adattiva di default: rumore di fondo (10° percentile) + 8 dB, perché in un master forte registrato
    in esterno (es. −11 LUFS) le pause possono non scendere mai sotto −35 dB. Candidato = ripresa della voce.
    `dec_args`: decoder dalla policy (ytcore.aac_decoder_args); aresample async tiene il timeline
    del contenitore anche se il decoder scarta un pacchetto.
    """
    import numpy as np

    cmd = [ytcore.FFMPEG, "-v", "error", *(dec_args or []), "-i", str(audio), "-vn",
           "-af", ytcore.AUDIO_ASYNC, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
    log("$", " ".join(cmd))
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    hop = 320  # 20 ms
    n = len(x) // hop
    if n == 0:
        return [], 0.0
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    thr = noise_db if noise_db is not None else float(np.percentile(db, 10) + 8.0)
    quiet = db < thr
    out, k = [], 0
    while k < n:
        if quiet[k]:
            j = k
            while j < n and quiet[j]:
                j += 1
            dur = (j - k) * hop / 16000
            if dur >= min_dur and j < n:
                end = j * hop / 16000
                out.append({"t": round(end, 3), "gap_start": round(k * hop / 16000, 3), "gap": round(dur, 3),
                            "sentence_end": dur >= 0.6, "speaker_change": False, "kind": "silence"})
            k = j
        else:
            k += 1
    return out, round(thr, 1)


def snap(t: float, cands: list[dict], cuts: list[float], window: float) -> tuple[float, dict]:
    """Candidato a costo minimo entro ±window: vicinanza + fine frase + pausa lunga + taglio + cambio speaker."""
    best, best_cost = None, math.inf
    for c in cands:
        d = abs(c["t"] - t)
        if d > window:
            continue
        cost = d / window + (0.0 if c["sentence_end"] else 0.35) - 0.3 * min(c["gap"], 1.5) / 1.5
        cost -= 0.1 if c.get("speaker_change") else 0.0
        if cost < best_cost:
            best, best_cost = c, cost
    for x in cuts:  # un taglio del montaggio è un confine naturale
        d = abs(x - t)
        if d <= window and d / window - 0.2 < best_cost:
            best, best_cost = {"t": x, "gap_start": x, "gap": 0.0, "kind": "cut"}, d / window - 0.2
    if best is None:
        return t, {"kind": "none", "note": f"nessuna pausa entro ±{window:g} s: tempo invariato"}
    return best["t"], best


def yt_second(t: float) -> int:
    """Secondo intero per la descrizione (YouTube tronca): mai dopo l'inizio della prima parola."""
    return max(0, int(math.floor(t + 1e-6)))


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-chapters", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--draft", default="edit/chapters.draft.json", help="draft dei capitoli")
    ap.add_argument("--timeline", default=None,
                    help="edit/assembled.timeline.json (default se esiste) oppure 'none' = timeline del sorgente")
    ap.add_argument("--draft-timeline", default=None, choices=["source", "output"],
                    help="timeline dei tempi del draft se il file non lo dichiara (default: output se c'è un montato)")
    ap.add_argument("--window", type=float, default=3.0, help="ricerca della pausa ±s (default 3)")
    ap.add_argument("--max-title", type=int, default=60, help="lunghezza massima titolo (default 60)")
    ap.add_argument("--audio", default=None, help="audio per le pause se manca il transcript (default edit/mix.wav, analysis/audio16k.wav o il sorgente)")
    ap.add_argument("--silence-db", type=float, default=None,
                    help="soglia fissa delle pause in dBFS (default adattiva: rumore di fondo + 8 dB)")
    ap.add_argument("--no-snap", action="store_true", help="solo validazione, niente aggancio")
    ap.add_argument("--force", action="store_true", help="rifà anche se aggiornato")
    args = ap.parse_args()

    warnings: list[str] = []
    try:
        workdir = ytcore.resolve_workdir(args.workdir)
        draft_path = Path(args.draft)
        draft_path = draft_path if draft_path.is_absolute() else workdir / draft_path
        if not draft_path.exists():
            ytcore.fail(f"Draft dei capitoli mancante: {draft_path}")
        chapters, declared = load_draft(draft_path)
        timeline, tl_path = cap.resolve_timeline(workdir, args.timeline, warnings)
        src_key = cap.main_source_key(workdir)
        draft_tl = declared or args.draft_timeline or ("output" if timeline else "source")
        if timeline is None and draft_tl == "output":
            warnings.append("draft su timeline 'output' ma nessun montato: output = sorgente")

        out_txt, out_json = workdir / "deliver" / "chapters.txt", workdir / "deliver" / "chapters.json"
        words_path = workdir / "analysis" / "transcript.words.json"
        inputs = [draft_path, Path(__file__), Path(cap.__file__)] + ([tl_path] if tl_path else []) + \
                 ([words_path] if words_path.exists() else [])
        sig = cap.signature("chapters", draft_tl, "output" if timeline else "source", args.window, args.max_title,
                            args.audio, args.silence_db, args.no_snap)
        if not args.force and cap.up_to_date(workdir, [out_txt, out_json], inputs, sig):
            data = ytcore.read_json(out_json)
            ytcore.emit(True, outputs={"chapters_txt": str(out_txt), "chapters_json": str(out_json)}, skipped=True,
                        chapters=len(data.get("chapters", [])), warnings=warnings)
            return

        duration = media_duration(workdir, timeline)
        # 1) tempi del draft → timeline di output
        for c in chapters:
            if draft_tl == "source" and timeline is not None:
                t_out, how = cap.src_to_out(c["draft_t"], timeline, src_key)
                if t_out is None:
                    raise ValueError(f"Capitolo {c['n']} ({c['draft_t']:.1f}s sorgente) cade dopo la fine del montato")
                if how != "inside":
                    warnings.append(f"capitolo {c['n']} '{c['title']}': {c['draft_t']:.1f}s è in un taglio → "
                                    f"inizio del segmento successivo ({t_out:.1f}s output)")
                c["mapped_t"] = round(t_out, 3)
            else:
                c["mapped_t"] = c["draft_t"]

        # 2) candidati di aggancio
        cands: list[dict] = []
        source_kind = None
        if words_path.exists():
            words, _ = cap.load_words(workdir)
            cands = word_candidates(cap.map_words(words, timeline, src_key))
            source_kind = "transcript (pause tra parole)"
        else:
            audio = Path(args.audio) if args.audio else None
            if audio is None:
                for cand in ([workdir / "edit" / "mix.wav", workdir / "edit" / "assembled.mov"] if timeline
                             else [workdir / "analysis" / "audio16k.wav"]):
                    if cand.exists():
                        audio = cand
                        break
            if audio is None and timeline is None:
                audio = ytcore.source_path(workdir)
            if audio is not None and not args.no_snap:
                # decoder dalla policy centrale: sorgente → decisione di yt-ingest; wav/mov PCM → nessuno
                dec = ytcore.aac_decoder_args(workdir, {"path": str(audio)})
                cands, thr = silence_candidates(audio, args.silence_db, dec_args=dec)
                source_kind = f"pause audio < {thr:g} dBFS ({'fissa' if args.silence_db is not None else 'adattiva'}) su {audio.name}"
            elif not args.no_snap:
                warnings.append("né transcript né audio: capitoli non agganciati")
        cuts = [s["out_start"] for s in timeline[1:]] if timeline else []

        # 3) aggancio (il primo capitolo va sempre a 0:00)
        for k, c in enumerate(chapters):
            if k == 0:
                if c["mapped_t"] > 0:
                    warnings.append(f"primo capitolo a {c['mapped_t']:.1f}s: portato a 0:00 (regola YouTube)")
                c.update(snapped_t=0.0, how={"kind": "first"})
            elif args.no_snap:
                c.update(snapped_t=c["mapped_t"], how={"kind": "no-snap"})
            else:
                t, how = snap(c["mapped_t"], cands, cuts, args.window)
                c.update(snapped_t=round(t, 3), how=how)
            c["t_yt"] = yt_second(c["snapped_t"])
            c["delta"] = round(c["snapped_t"] - c["mapped_t"], 3)

        # 4) validazione sui secondi interi (quelli che YouTube legge)
        errors: list[str] = []
        if len(chapters) < YT_MIN_CHAPTERS:
            errors.append(f"servono almeno {YT_MIN_CHAPTERS} capitoli (ce ne sono {len(chapters)})")
        seen = set()
        for k, c in enumerate(chapters):
            title = c["title"]
            if not title.strip():
                errors.append(f"capitolo {c['n']}: titolo vuoto")
            if "\n" in title or "\r" in title:
                errors.append(f"capitolo {c['n']}: il titolo va su una riga")
            if len(title.strip()) > args.max_title:
                errors.append(f"capitolo {c['n']}: titolo di {len(title.strip())} caratteri (max {args.max_title})")
            if re.match(r"^\s*\(?\d{1,2}:\d{2}", title):
                errors.append(f"capitolo {c['n']}: il titolo inizia con un orario")
            if title.strip().lower() in seen:
                warnings.append(f"capitolo {c['n']}: titolo ripetuto '{title.strip()}'")
            seen.add(title.strip().lower())
            nxt = chapters[k + 1]["t_yt"] if k + 1 < len(chapters) else duration
            if nxt is not None:
                c["length"] = round(nxt - c["t_yt"], 2)
                if k + 1 < len(chapters) and nxt <= c["t_yt"]:
                    errors.append(f"capitoli {c['n']}→{c['n'] + 1} non in ordine crescente ({c['t_yt']}s → {nxt}s)")
                elif c["length"] < YT_MIN_LEN:
                    errors.append(f"capitolo {c['n']} '{title.strip()}' dura {c['length']:.1f}s (< {YT_MIN_LEN:g}s)")
            if duration is not None and c["t_yt"] >= duration:
                errors.append(f"capitolo {c['n']} oltre la fine del video ({c['t_yt']}s ≥ {duration:.1f}s)")

        valid = not errors
        lines = [f"{ytcore.fmt_ts(c['t_yt'], 'yt')} {c['title'].strip()}" for c in chapters]
        report = {
            "valid": valid, "errors": errors, "timeline": "output" if timeline else "source", "draft_timeline": draft_tl,
            "duration": duration, "snap_source": source_kind, "window": args.window,
            "chapters": [{"n": c["n"], "title": c["title"].strip(), "t": c["t_yt"], "t_precise": c["snapped_t"],
                          "draft_t": c["draft_t"], "mapped_t": c["mapped_t"], "delta": c["delta"],
                          "snapped_to": c["how"].get("kind"), "gap": c["how"].get("gap"),
                          "length": c.get("length"), "yt": lines[k]} for k, c in enumerate(chapters)],
        }
        ytcore.write_json(out_json, report)
        outputs = {"chapters_json": str(out_json)}
        if valid:
            out_txt.parent.mkdir(parents=True, exist_ok=True)
            out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
            outputs["chapters_txt"] = str(out_txt)
            cap.stamp(workdir, [out_txt, out_json], sig)
        elif out_txt.exists():
            warnings.append("deliver/chapters.txt precedente NON aggiornato (draft non valido)")
        adjustments = [{"n": c["n"], "title": c["title"].strip(), "from": round(c["mapped_t"], 2), "to": c["snapped_t"],
                        "yt": ytcore.fmt_ts(c["t_yt"], "yt"), "delta": c["delta"], "snapped_to": c["how"].get("kind")}
                       for c in chapters if abs(c["delta"]) > 0.01 or c["how"].get("kind") in ("first", "none")]
        ytcore.emit(valid, outputs=outputs, chapters=len(chapters), timeline=report["timeline"], text="\n".join(lines),
                    adjustments=adjustments, errors=errors, warnings=warnings)
        if not valid:
            raise SystemExit(1)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        ytcore.fail(str(exc), warnings=warnings)


if __name__ == "__main__":
    main()
