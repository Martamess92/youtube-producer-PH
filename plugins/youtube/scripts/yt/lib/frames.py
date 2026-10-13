"""yt-frames — estrae frame dal sorgente di una cartella di lavoro (decodifica VideoToolbox, seek accurato).

Uso:
  yt-frames WORKDIR --times 75.2,1:02:03.5 [--size full|1080|540] [--format jpg|png]
  yt-frames WORKDIR --every 20 [--from 600 --to 900] [--out DIR] [--contact]
  yt-frames WORKDIR --times 812.4 --size full --format png --out thumbs/frames

Tempi in secondi (75.2) o h:m:s (1:15.2, 00:01:15.200); più tempi separati da virgola o spazio.
--size indica il lato corto: 1080 → 1920×1080 da un 4K 16:9 (mai upscaling). full = nativo.
Nomi dei file: t_<secondi con 3 decimali>.<ext> (es. t_000812.400.jpg), ordinabili.
Default --out: <workdir>/analysis/frames/extract/. Salta i file già presenti e più recenti
del sorgente (--force per rifarli).

Il modulo espone anche le funzioni media condivise con yt-ingest e yt-new:
probe_summary, sw_download_format, extract_at_times, extract_every, contact_sheet, frame_name.
"""
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path

import ytcore
from ytcore import FFMPEG, fail, emit, fmt_ts, log, parse_ts

# Codec che VideoToolbox decodifica in hardware sui Mac Apple Silicon (M3+ anche AV1).
VT_CODECS = {"h264", "hevc", "prores", "mpeg1video", "mpeg2video", "mpeg4", "vp9", "av1"}

# Filtro finale per JPEG: JFIF è BT.601 full range, quindi convertiamo matrice e range
# (senza, i colori di un sorgente BT.709 escono leggermente sfalsati).
JPEG_TAIL = "scale=out_range=full:out_color_matrix=bt601,format=yuv420p"
PNG_TAIL = "format=rgb24"
SIZES = ("full", "1080", "540")


# ── Probe ───────────────────────────────────────────────────────────────────
def parse_rate(rate: str | None) -> float | None:
    """'30000/1001' → 29.97; '0/0' o vuoto → None."""
    if not rate or rate in ("0/0", "N/A"):
        return None
    try:
        value = float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return None
    return value or None


def _bits(pix_fmt: str | None) -> int:
    pf = pix_fmt or ""
    for b in (16, 12, 10):
        if f"p{b}" in pf or f"{b}le" in pf or f"{b}be" in pf:
            return b
    return 8


def probe_summary(path: Path | str) -> dict:
    """ffprobe ridotto all'essenziale: primo stream video e primo audio + formato."""
    raw = ytcore.ffprobe(path)
    fmt = raw.get("format", {})
    streams = raw.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    out: dict = {
        "duration": float(fmt.get("duration") or 0.0),
        "size": int(fmt.get("size") or 0),
        "bit_rate": int(fmt.get("bit_rate") or 0),
        "format": fmt.get("format_name"),
        "start_time": float(fmt.get("start_time") or 0.0),
        "streams": {t: sum(1 for s in streams if s.get("codec_type") == t)
                    for t in ("video", "audio", "subtitle", "data")},
        "video": None,
        "audio": None,
    }
    if video:
        fps = parse_rate(video.get("r_frame_rate"))
        avg = parse_rate(video.get("avg_frame_rate"))
        transfer = video.get("color_transfer")
        out["video"] = {
            "index": video.get("index"),
            "codec": video.get("codec_name"),
            "profile": video.get("profile"),
            "pix_fmt": video.get("pix_fmt"),
            "bits": _bits(video.get("pix_fmt")),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": round(fps, 4) if fps else None,
            "avg_fps": round(avg, 4) if avg else None,
            "vfr": bool(fps and avg and abs(fps - avg) > 0.01),
            "nb_frames": int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else None,
            "duration": float(video.get("duration") or out["duration"]),
            "color_transfer": transfer,
            "color_primaries": video.get("color_primaries"),
            "color_space": video.get("color_space"),
            "hdr": transfer in ("arib-std-b67", "smpte2084"),
            "bit_rate": int(video.get("bit_rate") or 0),
        }
    if audio:
        out["audio"] = {
            "index": audio.get("index"),
            "codec": audio.get("codec_name"),
            "profile": audio.get("profile"),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "channels": int(audio.get("channels") or 0),
            "layout": audio.get("channel_layout"),
            "duration": float(audio.get("duration") or out["duration"]),
            "bit_rate": int(audio.get("bit_rate") or 0),
        }
    return out


def media_label(summary: dict) -> str:
    """Etichetta breve: '3840x2160 hevc 10bit 30fps · aac 44100Hz 2ch · 52:58'."""
    parts = []
    v, a = summary.get("video"), summary.get("audio")
    if v:
        parts.append(f"{v['width']}x{v['height']} {v['codec']} {v['bits']}bit {v['fps'] or 0:g}fps")
    if a:
        parts.append(f"{a['codec']} {a['sample_rate']}Hz {a['channels']}ch")
    parts.append(fmt_ts(summary.get("duration", 0), "yt"))
    return " · ".join(parts)


def vt_ok(summary: dict) -> bool:
    v = summary.get("video")
    return bool(v and v.get("codec") in VT_CODECS)


def sw_download_format(pix_fmt: str | None) -> str:
    """Formato software dei frame VideoToolbox dopo hwdownload (dipende da bit e chroma)."""
    pf = pix_fmt or ""
    if _bits(pf) == 8:
        return "nv12"
    if "444" in pf:
        return "p410le"
    if "422" in pf:
        return "p210le"
    return "p010le"


# ── Campionamento ───────────────────────────────────────────────────────────
# Versione del campionatore registrata in frames/index.json: un indice senza (o con
# versione diversa) viene rigenerato.
SAMPLER_VERSION = 2


def fps_sampler(every: float) -> str:
    """Filtro fps che restituisce, per ogni tempo k·N, il frame a quel tempo (o quello subito prima).

    Con il default round=near il filtro emette l'ULTIMO frame di ogni intervallo
    [kN−N/2, kN+N/2): i campioni arriverebbero in ritardo di ~N/2 (10 s con N=20).
    Con round=up l'intervallo diventa (kN−N, kN] e l'ultimo frame è proprio quello a kN.
    """
    rate = Fraction(1 / every).limit_denominator(100000)
    return f"fps=fps={rate.numerator}/{rate.denominator}:round=up"


# ── Nomi e dimensioni ───────────────────────────────────────────────────────
def frame_name(t: float, ext: str = "jpg") -> str:
    return f"t_{max(0.0, t):010.3f}.{ext}"


def target_size(size: str, w: int, h: int) -> tuple[int, int] | None:
    """Dimensioni di uscita per --size (lato corto), None = nativo. Mai upscaling."""
    if size == "full" or not w or not h:
        return None
    short = int(size)
    if min(w, h) <= short:
        return None
    if w >= h:
        return (int(round(w * short / h / 2)) * 2, short)
    return (short, int(round(h * short / w / 2)) * 2)


def width_for(width: int, w: int, h: int) -> tuple[int, int]:
    """Dimensioni per larghezza fissa (pari), mantenendo l'aspetto."""
    width = min(width, w) if w else width
    return (width // 2 * 2, int(round(h * width / w / 2)) * 2 if w else -2)


def _tail(fmt: str) -> str:
    return JPEG_TAIL if fmt == "jpg" else PNG_TAIL


def _quality(fmt: str) -> list[str]:
    return ["-q:v", "2"] if fmt == "jpg" else ["-compression_level", "3"]


def _is_fresh(out: Path, src: Path, dims: tuple[int, int] | None = None) -> bool:
    """Output presente, non vuoto, più recente del sorgente e (se nota) della dimensione giusta."""
    try:
        if not (out.exists() and out.stat().st_size > 0 and out.stat().st_mtime >= src.stat().st_mtime):
            return False
        if dims:
            from PIL import Image

            with Image.open(out) as im:  # legge solo l'header
                return im.size == tuple(dims)
        return True
    except OSError:
        return False


# ── Estrazione ──────────────────────────────────────────────────────────────
def extract_at_times(src: Path, times: list[float], out_dir: Path, *, summary: dict,
                     size: str = "1080", fmt: str = "jpg", hw: bool = True, force: bool = False,
                     jobs: int = 4, width: int | None = None) -> list[dict]:
    """Un ffmpeg per tempo, seek accurato (-ss prima di -i + decodifica fino al frame).

    Con VideoToolbox i frame restano in GPU (scale_vt) e si scarica solo quello scelto;
    se fallisce si ripete lasciando a ffmpeg il download automatico + scaling software.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    v = summary.get("video") or {}
    w, h = v.get("width") or 0, v.get("height") or 0
    dims = width_for(width, w, h) if width else target_size(size, w, h)
    scale = f"scale={dims[0]}:{dims[1]}:flags=lanczos," if dims else ""
    duration = summary.get("duration") or 0.0
    use_hw = hw and vt_ok(summary)
    gpu_chain = (f"scale_vt=w={dims[0]}:h={dims[1]}," if dims else "") + \
        f"hwdownload,format={sw_download_format(v.get('pix_fmt'))},{_tail(fmt)}"

    want = dims or ((w, h) if w and h else None)

    def one(t: float) -> dict:
        out = out_dir / frame_name(t, fmt)
        if not force and _is_fresh(out, src, want):
            return {"t": round(t, 3), "file": str(out), "skipped": True}
        if duration and t > duration:
            return {"t": round(t, 3), "file": None, "error": f"oltre la durata ({duration:.2f}s)"}
        tmp = out.with_name(f".{out.stem}.part.{fmt}")
        attempts = []
        if use_hw:
            attempts.append((["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"], gpu_chain))
            attempts.append((["-hwaccel", "videotoolbox"], scale + _tail(fmt)))
        else:
            attempts.append(([], scale + _tail(fmt)))
        for hwargs, chain in attempts:
            cmd = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *hwargs,
                   "-ss", f"{t:.3f}", "-i", str(src), "-map", "0:v:0", "-frames:v", "1", "-update", "1",
                   "-vf", chain, *_quality(fmt), str(tmp)]
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
                break
        if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
            err = (proc.stderr or "").strip().splitlines()
            return {"t": round(t, 3), "file": None, "error": err[-1] if err else "nessun frame (fine file?)"}
        tmp.replace(out)
        return {"t": round(t, 3), "file": str(out)}

    log(f"· estraggo {len(times)} frame ({'VideoToolbox' if use_hw else 'software'}, "
        f"{'x'.join(map(str, dims)) if dims else 'nativo'}, {fmt}) → {out_dir}")
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(one, times))


def extract_every(src: Path, every: float, out_dir: Path, *, summary: dict, start: float = 0.0,
                  end: float | None = None, size: str = "1080", fmt: str = "jpg", hw: bool = True,
                  force: bool = False, width: int | None = None) -> list[dict]:
    """Un solo passaggio di decodifica con il filtro fps (conviene per intervalli fitti, < 4 s)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = summary.get("duration") or 0.0
    end = min(end, duration) if end else duration
    expected = [start + k * every for k in range(int((end - start) / every + 1e-9) + 1) if start + k * every <= end]
    v = summary.get("video") or {}
    w, h = v.get("width") or 0, v.get("height") or 0
    dims = width_for(width, w, h) if width else target_size(size, w, h)
    want = dims or ((w, h) if w and h else None)
    if not force and expected and all(_is_fresh(out_dir / frame_name(t, fmt), src, want) for t in expected):
        return [{"t": round(t, 3), "file": str(out_dir / frame_name(t, fmt)), "skipped": True} for t in expected]
    use_hw = hw and vt_ok(summary)
    chain = [fps_sampler(every)]
    if use_hw and dims:
        chain += [f"scale_vt=w={dims[0]}:h={dims[1]}", "hwdownload", f"format={sw_download_format(v.get('pix_fmt'))}"]
    elif use_hw:
        chain += ["hwdownload", f"format={sw_download_format(v.get('pix_fmt'))}"]
    elif dims:
        chain += [f"scale={dims[0]}:{dims[1]}:flags=lanczos"]
    chain.append(_tail(fmt))
    tmpdir = Path(tempfile.mkdtemp(prefix=".frames-", dir=out_dir))
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if use_hw:
        cmd += ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
    # Un po' oltre `end`: il filtro fps emette l'ultimo campione solo se vede frame successivi.
    cmd += ["-ss", f"{start:.3f}", "-to", f"{min(end + min(every, 1.0) + 0.1, duration):.3f}", "-i", str(src), "-map", "0:v:0",
            "-vf", ",".join(chain), "-fps_mode", "passthrough", *_quality(fmt),
            "-start_number", "0", str(tmpdir / f"f_%06d.{fmt}")]
    try:
        ytcore.run(cmd, capture=True)
        results = []
        for f in sorted(tmpdir.glob(f"f_*.{fmt}")):
            k = int(f.stem.split("_")[1])
            t = start + k * every
            if t > end + 1e-6:
                continue
            dest = out_dir / frame_name(t, fmt)
            f.replace(dest)
            results.append({"t": round(t, 3), "file": str(dest)})
        return results
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Contact sheet ───────────────────────────────────────────────────────────
def _font(size: int):
    from PIL import ImageFont

    for name in ("Inter[opsz,wght].ttf",):
        p = ytcore.FONTS / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def contact_sheet(frames: list[tuple[float, Path]], out: Path, *, cols: int = 8, tile_w: int = 320,
                  title: str | None = None, max_tiles: int = 160) -> Path:
    """Griglia di miniature con timecode (Pillow). Oltre max_tiles campiona in modo uniforme."""
    from PIL import Image, ImageDraw

    frames = [(t, Path(p)) for t, p in frames if p and Path(p).exists()]
    if not frames:
        raise ValueError("nessun frame per il contact sheet")
    if len(frames) > max_tiles:
        step = len(frames) / max_tiles
        frames = [frames[int(i * step)] for i in range(max_tiles)]
    with Image.open(frames[0][1]) as first:
        tile_h = int(round(tile_w * first.height / first.width))
    cols = max(1, min(cols, len(frames), math.ceil(math.sqrt(len(frames) * 2))))
    rows = (len(frames) + cols - 1) // cols
    gap, label_h = 6, 22
    head = 40 if title else 0
    sheet = Image.new("RGB", (cols * (tile_w + gap) + gap, head + rows * (tile_h + label_h + gap) + gap), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font, font_title = _font(15), _font(20)
    if title:
        draw.text((gap + 4, 10), title, fill=(235, 235, 235), font=font_title)
    for i, (t, path) in enumerate(frames):
        r, c = divmod(i, cols)
        x = gap + c * (tile_w + gap)
        y = head + gap + r * (tile_h + label_h + gap)
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((tile_w, tile_h))
            sheet.paste(im, (x, y))
        draw.text((x + 2, y + tile_h + 2), fmt_ts(t, "yt"), fill=(220, 220, 220), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.part{out.suffix}")
    sheet.save(tmp, quality=85)
    tmp.replace(out)
    return out


# ── CLI ─────────────────────────────────────────────────────────────────────
def _parse_times(items: list[str]) -> list[float]:
    times: list[float] = []
    for item in items:
        for tok in item.replace(";", ",").split(","):
            tok = tok.strip()
            if tok:
                times.append(round(parse_ts(tok), 3))
    return times


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-frames", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <channel>/<dir>)")
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--times", nargs="+", metavar="T", help="tempi sul timeline del sorgente: 75.2,1:02:03 …")
    sel.add_argument("--every", type=float, metavar="N", help="un frame ogni N secondi")
    ap.add_argument("--from", dest="start", default="0", metavar="T", help="inizio intervallo per --every (default 0)")
    ap.add_argument("--to", dest="end", metavar="T", help="fine intervallo per --every (default: fine file)")
    ap.add_argument("--size", choices=SIZES, default="1080", help="lato corto: full (nativo) | 1080 | 540 (default 1080)")
    ap.add_argument("--width", type=int, help="in alternativa a --size: larghezza fissa in pixel")
    ap.add_argument("--format", choices=("jpg", "png"), default="jpg", help="formato immagine (default jpg)")
    ap.add_argument("--out", help="cartella di uscita (default <workdir>/analysis/frames/extract)")
    ap.add_argument("--source", help="chiave del sorgente in project.json (default: main_source)")
    ap.add_argument("--proxy", action="store_true", help="estrae dal proxy 720p (analysis/proxy.mp4): più veloce")
    ap.add_argument("--mode", choices=("auto", "seek", "pass"), default="auto",
                    help="seek = un ffmpeg per frame; pass = una decodifica unica (auto: pass se --every < 4 s)")
    ap.add_argument("--jobs", type=int, default=4, help="estrazioni parallele in modalità seek (default 4)")
    ap.add_argument("--sw", action="store_true", help="decodifica software (senza VideoToolbox)")
    ap.add_argument("--contact", action="store_true", help="crea anche contact.jpg nella cartella di uscita")
    ap.add_argument("--force", action="store_true", help="rigenera anche i frame già presenti")
    args = ap.parse_args()

    try:
        wd = ytcore.resolve_workdir(args.workdir)
        if args.proxy:
            src = wd / "analysis" / "proxy.mp4"
            if not src.exists():
                fail(f"Proxy assente: {src} (esegui yt-ingest)")
        else:
            src = ytcore.source_path(wd, args.source)
        if not src.exists():
            fail(f"Sorgente non trovato: {src}")
        summary = probe_summary(src)
        if not summary.get("video"):
            fail(f"Il sorgente non ha uno stream video: {src}")
        out_dir = Path(args.out).expanduser() if args.out else wd / "analysis" / "frames" / "extract"
        if not out_dir.is_absolute():
            out_dir = wd / out_dir
        hw = not args.sw
        warnings: list[str] = []
        t0 = time.time()
        duration = summary["duration"]

        if args.times:
            times = _parse_times(args.times)
            results = extract_at_times(src, times, out_dir, summary=summary, size=args.size, fmt=args.format,
                                       hw=hw, force=args.force, jobs=args.jobs, width=args.width)
        else:
            if args.every <= 0:
                fail("--every deve essere > 0")
            start = parse_ts(args.start)
            end = parse_ts(args.end) if args.end else duration
            mode = args.mode if args.mode != "auto" else ("pass" if args.every < 4 else "seek")
            if mode == "pass":
                results = extract_every(src, args.every, out_dir, summary=summary, start=start, end=end,
                                        size=args.size, fmt=args.format, hw=hw, force=args.force, width=args.width)
            else:
                n = int((min(end, duration) - start) / args.every + 1e-9) + 1
                times = [round(start + k * args.every, 3) for k in range(n)]
                results = extract_at_times(src, times, out_dir, summary=summary, size=args.size, fmt=args.format,
                                           hw=hw, force=args.force, jobs=args.jobs, width=args.width)

        for r in results:
            if r.get("error"):
                warnings.append(f"{r['t']}s: {r['error']}")
        ok_files = [r for r in results if r.get("file")]
        outputs: dict = {"dir": str(out_dir), "files": ok_files}
        if args.contact and ok_files:
            outputs["contact"] = str(contact_sheet([(r["t"], Path(r["file"])) for r in ok_files],
                                                   out_dir / "contact.jpg", title=f"{wd.name} · {src.name}"))
        emit(bool(ok_files), outputs=outputs, count=len(ok_files),
             skipped=sum(1 for r in results if r.get("skipped")), source=str(src),
             elapsed_s=round(time.time() - t0, 2), warnings=warnings)
        if not ok_files:
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:  # errore leggibile in JSON, dettagli su stderr
        log(f"✗ {exc}")
        fail(str(exc))


if __name__ == "__main__":
    main()
