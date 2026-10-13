"""yt-pack — transcript compatto a frasi, da far leggere all'LLM (story, hook, capitoli, clip).

Uso:
  yt-pack WORKDIR                    # nuova riga su pausa ≥ 0.5 s o cambio di speaker
  yt-pack WORKDIR --gap 0.8          # frasi più lunghe (meno righe, meno token)
  yt-pack WORKDIR --pauses 2         # segnala anche le pause lunghe (≥ 2 s) con una riga "(pausa …)"
  yt-pack WORKDIR --ids              # S0/S1 invece dei nomi di project.json

Input:  analysis/transcript.words.json (yt-transcribe, meglio dopo yt-speakers)
Output: analysis/transcript.packed.txt

Formato (timeline del SORGENTE, tempi hh:mm:ss.s):
  [00:12:03.4–00:12:09.8] Paolo Bianchi: testo della frase…
Intestazione con durata, speaker (quota di parlato) e regole. Le frasi lunghe vengono spezzate
a fine periodo dopo --max-phrase secondi. Gli intercalari restano nel testo (verbatim).
Raggruppamento: group_into_phrases() di video-use (MIT, vendor/video_use/pack_transcripts.py).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ytcore as yc

sys.path.insert(0, str(yc.YT_HOME / "vendor"))
from video_use.pack_transcripts import group_into_phrases  # noqa: E402

SENT_END = (".", "?", "!", "…")
FORCED_BREAK = {"type": "spacing", "start": 0.0, "end": 1e9}  # "spacing" lungo = a capo forzato


def ts(sec: float) -> str:
    """hh:mm:ss.s (decimi arrotondati prima di scomporre, così 59.96 → 00:01:00.0)."""
    t = round(max(0.0, float(sec)), 1)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:04.1f}"


def to_scribe_words(words: list[dict], gap: float, max_phrase: float) -> list[dict]:
    """Parole whisper → forma di video-use; inserisce a capo forzati nelle frasi troppo lunghe."""
    out: list[dict] = []
    phrase_start = None
    prev = None
    for w in words:
        spk = w.get("speaker")
        if prev is not None:
            new_phrase = (w["start"] - prev["end"] >= gap) or (spk is not None and prev.get("speaker") is not None
                                                                and spk != prev.get("speaker"))
            if new_phrase:
                phrase_start = None
            elif phrase_start is not None:
                long_for = prev["end"] - phrase_start
                if (long_for >= max_phrase and prev["w"].endswith(SENT_END)) or \
                        (long_for >= 2 * max_phrase and prev["w"].endswith((",", ";", ":"))):
                    out.append(dict(FORCED_BREAK))
                    phrase_start = None
        if phrase_start is None:
            phrase_start = w["start"]
        out.append({"type": "word", "text": w["w"], "start": w["start"], "end": w["end"], "speaker_id": spk})
        prev = w
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="yt-pack", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--gap", type=float, default=0.5, help="pausa (s) che apre una nuova riga (default 0.5)")
    ap.add_argument("--max-phrase", type=float, default=20.0,
                    help="oltre questi secondi una frase va a capo al primo punto fermo (default 20)")
    ap.add_argument("--pauses", type=float, default=0.0,
                    help="se > 0, aggiunge righe '(pausa N s)' per i silenzi più lunghi di questo valore")
    ap.add_argument("--ids", action="store_true", help="usa S0/S1… anche se project.json ha i nomi")
    ap.add_argument("--force", action="store_true", help="rigenera anche se l'output è aggiornato")
    args = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(args.workdir)
    except FileNotFoundError as e:
        yc.fail(str(e))
    words_json = workdir / "analysis" / "transcript.words.json"
    out = workdir / "analysis" / "transcript.packed.txt"
    if not words_json.exists():
        yc.fail(f"manca {words_json}: esegui prima yt-transcribe")
    params = f"params: gap={args.gap} max_phrase={args.max_phrase} pauses={args.pauses} ids={int(args.ids)}"
    proj_file = workdir / "project.json"
    if out.exists() and not args.force and out.stat().st_mtime >= max(words_json.stat().st_mtime,
                                                                       proj_file.stat().st_mtime):
        if params in out.read_text(errors="replace")[:2000]:
            yc.emit(True, skipped=True, reason="output già aggiornato (usa --force per rifare)",
                    outputs={"packed": str(out)})
            return

    doc = yc.read_json(words_json)
    project = yc.load_project(workdir)
    words = doc.get("words", [])
    names = {} if args.ids else (project.get("speakers") or {})
    warnings: list[str] = []
    if not words:
        warnings.append("transcript senza parole")
    has_spk = any(w.get("speaker") for w in words)
    if not has_spk:
        warnings.append("speaker non assegnati: righe senza nome (esegui yt-speakers)")

    phrases = group_into_phrases(to_scribe_words(words, args.gap, args.max_phrase), args.gap)

    def label(spk) -> str:
        if spk is None:
            return "?"
        return names.get(spk, spk)

    # intestazione
    duration = float(doc.get("duration") or (words[-1]["end"] if words else 0))
    talk: dict[str, float] = {}
    for p in phrases:
        if p.get("speaker_id"):
            talk[p["speaker_id"]] = talk.get(p["speaker_id"], 0.0) + p["end"] - p["start"]
    tot = sum(talk.values()) or 1.0
    spk_line = ", ".join(f"{s} = {names.get(s, 'senza nome')} ({100 * v / tot:.0f}%)"
                         for s, v in sorted(talk.items(), key=lambda kv: -kv[1]))
    src = Path(project.get("sources", {}).get(project.get("main_source") or "", {}).get("path", "")).name
    lines = [
        f"# Transcript compatto — {project.get('title_working') or project.get('slug', workdir.name)}",
        f"# Sorgente: {src or '?'} · durata {ts(duration)} · {len(words)} parole · {len(phrases)} frasi · "
        f"{doc.get('engine', '?')} · timeline: source",
        f"# Speaker: {spk_line or 'non assegnati'}",
        f"# Una riga per frase: nuova riga a ogni pausa ≥ {args.gap:g} s o cambio di speaker; "
        f"tempi [inizio–fine] in hh:mm:ss.s; intercalari conservati.",
        f"# {params}",
        "",
    ]
    n_pause = 0
    prev_end = None
    for p in phrases:
        if args.pauses > 0 and prev_end is not None and p["start"] - prev_end >= args.pauses:
            lines.append(f"[{ts(prev_end)}–{ts(p['start'])}] (pausa {p['start'] - prev_end:.1f} s)")
            n_pause += 1
        who = f"{label(p.get('speaker_id'))}: " if has_spk else ""
        lines.append(f"[{ts(p['start'])}–{ts(p['end'])}] {who}{p['text']}")
        prev_end = p["end"]
    text = "\n".join(lines) + "\n"
    out.write_text(text, encoding="utf-8")

    yc.emit(True, outputs={"packed": str(out)}, phrases=len(phrases), pause_lines=n_pause,
            words=len(words), size_kb=round(len(text.encode()) / 1024, 1), approx_tokens=len(text) // 4,
            speakers={s: names.get(s) for s in talk}, warnings=warnings)


if __name__ == "__main__":
    main()
