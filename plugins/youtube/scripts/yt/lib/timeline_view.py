"""yt-timeline-view — PNG di controllo: filmstrip + forma d'onda + parole intorno a un istante.

Uso:
  yt-timeline-view WORKDIR --at 62.3                       # sorgente, finestra 3 s (T ± 1.5 s)
  yt-timeline-view WORKDIR --at 1:02.3,5:40,12:03 --window 4
  yt-timeline-view WORKDIR --find "Acme" --max 3        # centra la vista sulle occorrenze di una parola
  yt-timeline-view WORKDIR --at 38.8 --source edit         # montato: edit/assembled.mov, tagli marcati

Il "drill-down visivo" di video-use (MIT, vendor/video_use/timeline_view.py) adattato al toolkit:
decodifica VideoToolbox (4K HEVC Main10), audio dal WAV di analisi o con AudioToolbox,
parole del transcript (colore per speaker, intercalari evidenziati), pause ≥ 400 ms ombreggiate,
linea su T e, sul montato, i punti di taglio presi da edit/assembled.timeline.json.

Output: qa/timeline_view/<T>.png (sorgente) o <T>.edit.png (montato), T = secondi con 2 decimali.
Il JSON di riepilogo riporta anche le parole nella finestra, così si legge il testo senza aprire il PNG.
Usalo nei punti di decisione (tagli, pause ambigue, verifica dei tempi parola), non in scansione.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import ytcore as yc

sys.path.insert(0, str(yc.YT_HOME / "vendor"))
from video_use import timeline_view as vu  # noqa: E402  (helper vendorizzati: font, silenzi, palette)

SPEAKER_COLORS = {"S0": (110, 170, 255), "S1": (120, 220, 140), "S2": (255, 140, 200), "S3": (240, 210, 90),
                  "S4": (170, 140, 255), "OVERLAP": (255, 90, 90), None: (150, 150, 160)}
FILLER_COLOR = (255, 170, 60)
CUT_COLOR = (255, 80, 80)
T_COLOR = (255, 230, 80)


# ── Sorgenti ────────────────────────────────────────────────────────────────
def probe_av(path: Path) -> tuple[float, str | None, str | None]:
    info = yc.ffprobe(path)
    dur = float(info.get("format", {}).get("duration") or 0)
    vcodec = next((s.get("codec_name") for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    acodec = next((s.get("codec_name") for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    return dur, vcodec, acodec


def extract_frames(video: Path, times: list[float], dest: Path, width: int) -> list[Path]:
    """Un frame per istante (seek veloce + decodifica VideoToolbox), in parallelo."""
    dest.mkdir(parents=True, exist_ok=True)

    def one(k_t):
        k, t = k_t
        out = dest / f"f_{k:03d}.jpg"
        cmd = [yc.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-hwaccel", "videotoolbox",
               "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-an",
               "-vf", f"scale={width}:-2", "-q:v", "3", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            # ripiego software (es. codec non supportato da VideoToolbox)
            cmd.remove("-hwaccel")
            cmd.remove("videotoolbox")
            subprocess.run(cmd, capture_output=True, text=True)
        return out

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(one, enumerate(times)))


def envelope_from_wav(wav: Path, a: float, b: float, samples: int) -> np.ndarray:
    with wave.open(str(wav), "rb") as fh:
        rate, ch, width = fh.getframerate(), fh.getnchannels(), fh.getsampwidth()
        fh.setpos(min(fh.getnframes(), max(0, int(a * rate))))
        raw = fh.readframes(max(0, int((b - a) * rate)))
    if width != 2 or not raw:
        return np.zeros(samples)
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    return rms_envelope(pcm, samples)


def rms_envelope(pcm: np.ndarray, samples: int, rate: int = 16000) -> np.ndarray:
    """Inviluppo RMS su finestre di 20 ms centrate su ogni pixel, in dB normalizzati alla finestra.

    La scala parte ~3 dB sopra il rumore di fondo della finestra (5° percentile): pause e attacchi
    delle parole si leggono anche con il brusio di sala, i picchi non schiacciano il resto.
    """
    if pcm.size == 0:
        return np.zeros(samples)
    cs = np.concatenate([[0.0], np.cumsum(pcm.astype(np.float64) ** 2)])
    h = max(1, int(0.010 * rate))
    centers = np.linspace(0, pcm.size - 1, samples).astype(int)
    lo, hi = np.clip(centers - h, 0, pcm.size), np.clip(centers + h, 0, pcm.size)
    env = np.sqrt((cs[hi] - cs[lo]) / np.maximum(hi - lo, 1))
    db = 20 * np.log10(env + 1e-7)
    top = float(db.max())
    floor = max(float(np.percentile(db, 5)) + 3.0, top - 45.0)
    return np.clip((db - floor) / max(1e-3, top - floor), 0, 1)


def envelope_from_media(path: Path, a: float, b: float, samples: int, acodec: str | None,
                        workdir: Path | None = None) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="yt-tv-") as tmp:
        wav = Path(tmp) / "a.wav"
        # decoder AAC dalla policy centrale (decisione di yt-ingest); async = timeline del contenitore
        dec = yc.aac_decoder_args(workdir, {"path": str(path), "codec": acodec})
        cmd = [yc.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *dec, "-ss", f"{a:.3f}",
               "-i", str(path), "-t", f"{b - a:.3f}", "-vn", "-af", yc.AUDIO_ASYNC, "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", str(wav)]
        if subprocess.run(cmd, capture_output=True).returncode != 0 or not wav.exists():
            return np.zeros(samples)
        return envelope_from_wav(wav, 0, b - a, samples)


# ── Parole e tagli ──────────────────────────────────────────────────────────
def load_words(workdir: Path) -> tuple[list[dict], dict]:
    p = workdir / "analysis" / "transcript.words.json"
    if not p.exists():
        return [], {}
    doc = yc.read_json(p)
    return doc.get("words", []), doc.get("speaker_names") or {}


def load_edit_map(workdir: Path) -> list[dict]:
    p = workdir / "edit" / "assembled.timeline.json"
    if not p.exists():
        return []
    return yc.read_json(p).get("segments", [])


def words_to_output(words: list[dict], segs: list[dict]) -> list[dict]:
    """Parole del sorgente → timeline del montato (out = start − src_in + out_start).

    Le parole tagliate a metà da un segmento restano, ritagliate, con "clipped": true
    (disegnate in rosso): è il segnale di un taglio dentro una parola.
    """
    out = []
    for s in segs:
        src_in = float(s.get("src_in", 0))
        dur = float(s["out_end"]) - float(s["out_start"])
        src_out = src_in + dur
        shift = float(s["out_start"]) - src_in
        for w in words:
            if w["end"] <= src_in + 0.01 or w["start"] >= src_out - 0.01:
                continue
            a, b = max(w["start"], src_in), min(w["end"], src_out)
            rec = {**w, "start": a + shift, "end": b + shift}
            if a > w["start"] + 0.02 or b < w["end"] - 0.02:
                rec["clipped"] = True
            out.append(rec)
    return sorted(out, key=lambda w: w["start"])


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9&']+", " ", t).strip()


def find_occurrences(words: list[dict], query: str, limit: int) -> list[tuple[float, str]]:
    q = fold(query).split()
    hits = []
    if not q:
        return hits
    folded = [fold(w["w"]) for w in words]
    for i in range(len(words) - len(q) + 1):
        if all(q[k] in folded[i + k] for k in range(len(q))):
            a, b = words[i]["start"], words[i + len(q) - 1]["end"]
            hits.append(((a + b) / 2, " ".join(w["w"] for w in words[i:i + len(q)])))
            if len(hits) >= limit:
                break
    return hits


# ── Disegno ─────────────────────────────────────────────────────────────────
def render(video: Path, label: str, t: float, a: float, b: float, n_frames: int, words: list[dict],
           names: dict, cuts: list[tuple[float, str]], env: np.ndarray, out: Path) -> None:
    W = 1920
    margin = 50
    gap = 6
    per_row = min(n_frames, 5)
    rows = (n_frames + per_row - 1) // per_row
    fw = (W - 2 * margin - (per_row - 1) * gap) // per_row
    times = [a + (b - a) * (k / (n_frames - 1) if n_frames > 1 else 0.5) for k in range(n_frames)]
    with tempfile.TemporaryDirectory(prefix="yt-tv-") as tmp:
        paths = extract_frames(video, times, Path(tmp), fw)
        frames = []
        for pth in paths:
            try:
                frames.append(Image.open(pth).convert("RGB"))
            except Exception:
                frames.append(Image.new("RGB", (fw, int(fw * 9 / 16)), (40, 40, 40)))
    fh = max(im.height for im in frames)

    header_h = 60
    strip_y = header_h
    strip_h = rows * (fh + gap)
    words_y = strip_y + strip_h + 20
    words_h = 64
    wave_y = words_y + words_h + 6
    wave_h = 200
    ruler_y = wave_y + wave_h + 4
    H = ruler_y + 70

    canvas = Image.new("RGB", (W, H), vu.BG)
    draw = ImageDraw.Draw(canvas, "RGBA")
    f_head, f_lab, f_small = vu.load_font(24), vu.load_font(15), vu.load_font(13)

    draw.text((margin, 16), f"{label}   T = {yc.fmt_ts(t)} ({t:.2f}s)   finestra {a:.2f}–{b:.2f}s "
              f"({b - a:.1f}s, {n_frames} frame)", fill=vu.FG, font=f_head)

    # filmstrip (frame più vicino a T bordato)
    k_t = int(np.argmin([abs(x - t) for x in times]))
    for k, im in enumerate(frames):
        r, c = divmod(k, per_row)
        x, y = margin + c * (fw + gap), strip_y + r * (fh + gap)
        canvas.paste(im, (x, y))
        draw.rectangle((x, y + im.height - 22, x + 92, y + im.height), fill=(0, 0, 0, 170))
        draw.text((x + 5, y + im.height - 20), f"{times[k]:.2f}s", fill=vu.FG, font=f_small)
        if k == k_t:
            draw.rectangle((x - 2, y - 2, x + im.width + 1, y + im.height + 1), outline=T_COLOR, width=3)

    x0, x1 = margin, W - margin

    def tx(v: float) -> float:
        return x0 + (v - a) / max(1e-6, b - a) * (x1 - x0)

    # parole: barra inizio→fine colorata per speaker, testo su due righe alternate
    in_win = [w for w in words if w["end"] > a and w["start"] < b]
    for k, w in enumerate(in_win):
        xa, xb = max(x0, tx(w["start"])), min(x1, tx(w["end"]))
        color = CUT_COLOR if w.get("clipped") else FILLER_COLOR if w.get("filler") \
            else SPEAKER_COLORS.get(w.get("speaker"), SPEAKER_COLORS[None])
        row = k % 2
        yb = words_y + 22 + row * 30
        draw.rectangle((xa, yb, max(xa + 2, xb), yb + 6), fill=(*color, 230))
        draw.line((xa, yb, xa, wave_y + wave_h), fill=(*color, 70), width=1)
        draw.text((xa + 1, yb - 19), w["w"], fill=color, font=f_lab)

    # forma d'onda con pause (≥ 400 ms tra parole) ombreggiate
    draw.rectangle((x0, wave_y, x1, wave_y + wave_h), fill=(28, 28, 34))
    for p0, p1 in (vu.find_silences(in_win, a, b, threshold=0.4) if in_win else []):
        draw.rectangle((tx(p0), wave_y, tx(p1), wave_y + wave_h), fill=vu.SILENCE)
    mid = wave_y + wave_h / 2
    amp = wave_h / 2 - 6
    xs = np.linspace(x0, x1, len(env))
    top = [(float(xx), float(mid - v * amp)) for xx, v in zip(xs, env)]
    bot = [(float(xx), float(mid + v * amp)) for xx, v in zip(xs, env)]
    if top:
        draw.polygon(top + bot[::-1], fill=(*vu.WAVE, 90))
        draw.line(top, fill=vu.WAVE, width=1)
        draw.line(bot, fill=vu.WAVE, width=1)

    # tagli del montato e linea su T
    for ct, cid in cuts:
        if a <= ct <= b:
            xc = tx(ct)
            for yy in range(int(words_y), int(wave_y + wave_h), 10):
                draw.line((xc, yy, xc, yy + 5), fill=CUT_COLOR, width=2)
            draw.text((xc + 4, wave_y + wave_h - 18), f"taglio {cid}", fill=CUT_COLOR, font=f_small)
    xt = tx(t)
    draw.line((xt, words_y, xt, wave_y + wave_h), fill=T_COLOR, width=2)

    # righello
    span = b - a
    step = 0.25 if span <= 3.5 else 0.5 if span <= 8 else 1.0 if span <= 16 else 5.0
    v = np.ceil(a / step) * step
    while v <= b + 1e-6:
        xv = tx(v)
        major = abs(v / (step * 2) - round(v / (step * 2))) < 1e-6
        draw.line((xv, ruler_y, xv, ruler_y + (10 if major else 5)), fill=vu.DIM, width=1)
        if major or step >= 1.0:
            draw.text((xv - 22, ruler_y + 12), f"{v:.2f}s", fill=vu.DIM, font=f_small)
        v += step

    spk = sorted({w.get("speaker") for w in in_win if w.get("speaker")})
    legend = "barre = parole (colore per speaker"
    if spk:
        legend += ": " + ", ".join(f"{s}={names[s]}" if names.get(s) else s for s in spk)
    legend += ") · arancio = intercalari · azzurro = pause ≥400 ms · giallo = T"
    if cuts:
        legend += " · rosso tratteggiato = tagli · parola rossa = tagliata a metà"
    draw.text((margin, ruler_y + 40), legend, fill=vu.DIM, font=f_small)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "PNG", optimize=True)


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        prog="yt-timeline-view", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--at", default=None, help="istante/i: 62.3 · 1:02.3 · 00:01:02,300 (più valori separati da virgola)")
    ap.add_argument("--find", default=None, help="centra la vista sulle occorrenze di questa parola/frase")
    ap.add_argument("--max", type=int, default=3, help="massimo di occorrenze con --find (default 3)")
    ap.add_argument("--window", type=float, default=3.0, help="ampiezza TOTALE della finestra in s (default 3 → T±1.5)")
    ap.add_argument("--source", choices=["src", "edit"], default="src",
                    help="src = sorgente principale (timeline source) · edit = edit/assembled.mov (timeline output)")
    ap.add_argument("--frames", type=int, default=10, help="frame nella filmstrip (default 10, 5 per riga)")
    ap.add_argument("--out", default=None, help="PNG di output (solo con un singolo istante)")
    ap.add_argument("--force", action="store_true", help="rigenera anche se il PNG esiste ed è aggiornato")
    args = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(args.workdir)
    except FileNotFoundError as e:
        yc.fail(str(e))
    if not args.at and not args.find:
        yc.fail("serve --at T oppure --find TESTO")
    if args.window <= 0.2:
        yc.fail("--window deve essere > 0.2 s")

    words, names = load_words(workdir)
    warnings: list[str] = []
    cuts: list[tuple[float, str]] = []
    if args.source == "src":
        video = yc.source_path(workdir)
        label = f"{workdir.name} · sorgente {video.name}"
    else:
        video = workdir / "edit" / "assembled.mov"
        label = f"{workdir.name} · montato {video.name}"
        segs = load_edit_map(workdir)
        if segs:
            words = words_to_output(words, segs)
            cuts = [(float(s["out_start"]), str(s.get("id", k))) for k, s in enumerate(segs) if k > 0]
        else:
            warnings.append("edit/assembled.timeline.json assente: niente parole né tagli sul montato")
            words = []
    if not video.exists():
        yc.fail(f"video non trovato: {video}")
    if not words:
        warnings.append("nessuna parola disponibile (manca transcript.words.json?)")

    dur, vcodec, acodec = probe_av(video)
    targets: list[tuple[float, str | None]] = []
    if args.at:
        at = args.at.strip()
        # un solo tempo in stile SRT (00:01:02,300) oppure una lista separata da virgole/punto e virgola
        parts = [at] if re.fullmatch(r"\d+:\d{2}:\d{2},\d{1,3}", at) else re.split(r"[;,]", at)
        for part in (p.strip() for p in parts):
            if part:
                try:
                    targets.append((yc.parse_ts(part), None))
                except ValueError:
                    yc.fail(f"tempo non valido: {part}")
    if args.find:
        hits = find_occurrences(words, args.find, args.max)
        if not hits:
            warnings.append(f"'{args.find}' non trovato nel transcript")
        targets += [(h[0], h[1]) for h in hits]
    if not targets:
        yc.fail("nessun istante da visualizzare", warnings=warnings)
    if args.out and len(targets) > 1:
        yc.fail("--out vale solo per un singolo istante")

    wav16 = yc.analysis_audio(workdir, "16k")
    words_mtime = (workdir / "analysis" / "transcript.words.json").stat().st_mtime \
        if (workdir / "analysis" / "transcript.words.json").exists() else 0
    results = []
    for t, matched in targets:
        half = args.window / 2
        a = max(0.0, t - half)
        b = min(dur - 0.05, t + half) if dur else t + half
        if b - a < 0.2:
            warnings.append(f"T={t:.2f} fuori dalla durata ({dur:.2f}s): saltato")
            continue
        suffix = "" if args.source == "src" else ".edit"
        out = Path(args.out).expanduser() if args.out else workdir / "qa" / "timeline_view" / f"{t:08.2f}{suffix}.png"
        in_win = [w for w in words if w["end"] > a and w["start"] < b]
        rec = {"at": round(t, 3), "png": str(out), "window": [round(a, 3), round(b, 3)],
               "words": [{"w": w["w"], "start": round(w["start"], 2), "end": round(w["end"], 2),
                          **({"speaker": w["speaker"]} if w.get("speaker") else {}),
                          **({"clipped": True} if w.get("clipped") else {})} for w in in_win]}
        if matched:
            rec["match"] = matched
        fresh = out.exists() and out.stat().st_mtime >= max(words_mtime, video.stat().st_mtime)
        if fresh and not args.force:
            rec["skipped"] = True
            results.append(rec)
            continue
        samples = 1820
        if args.source == "src" and wav16.exists():
            env = envelope_from_wav(wav16, a, b, samples)
        else:
            env = envelope_from_media(video, a, b, samples, acodec, workdir)
        render(video, label, t, a, b, max(1, args.frames), words, names, cuts, env, out)
        yc.log(f"salvato {out}")
        results.append(rec)

    yc.emit(True, outputs={"png": [r["png"] for r in results]}, views=results,
            source=args.source, video=str(video), warnings=warnings)


if __name__ == "__main__":
    main()
