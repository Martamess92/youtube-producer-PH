#!/usr/bin/env python3
"""yt-edl-render — render di edit/edl.json → edit/assembled.mov + edit/assembled.timeline.json.

Pipeline (regole video-use adattate a VideoToolbox, vedi design §8.3 e F2 §3.3):
1. tempi quantizzati al frame del timeline (il montato resta entro mezzo frame dalla somma
   dell'EDL); ogni estrazione usa il seek in ingresso (-ss prima di -i: veloce e accurato);
2. video: ogni segmento è spezzato ai bordi degli overlay in pezzi da N frame esatti.
   I pezzi semplici restano tutti in GPU (decodifica VT → scale_vt → encoder VT); quelli con
   punch-in (crop+scale, risoluzione invariata) o overlay alpha (setpts shift, solo il riquadro
   non trasparente) passano dai filtri software;
3. audio: un'unità continua per segmento, N·48000/fps campioni esatti, fade 30 ms solo ai tagli
   veri; video e audio hanno quindi durate identiche a ogni taglio. Decoder AAC dalla policy
   centrale (ytcore.aac_decoder_policy: project.json audio_decoder, di norma il nativo float) con
   aresample async; intermedi audio in float32 (a_*.wav, dialogo, musica, assembled.mov) così i
   picchi > 0 dBFS del master arrivano intatti fino a yt-loudnorm;
4. concat demuxer in copia (nessuna seconda codifica), post audio sull'intero montato:
   bilanciamento L/R (EDL audio.balance) e letti musicali con ducking sidechain;
5. --deliver: deliver/<slug>-master.mp4 (video in copia o ricodificato, AAC 48 kHz 320k,
   +faststart) con il mix normalizzato edit/mix.wav (creato con yt-loudnorm se manca).
6. verifica: durata vs EDL (±100 ms) e sincronia A/V ai tagli (offset frame video e ms audio
   rispetto al sorgente).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402
import loudnorm as ln  # noqa: E402

import numpy as np  # noqa: E402

RENDER_VERSION = 4
SR = 48000
HW_DECODE_CODECS = {"h264", "hevc", "prores", "mpeg4", "mpeg2video", "av1", "vp9"}

# Preset: dimensioni (None = canvas EDL), encoder, pixel format, keep segmenti di default
PRESETS = {
    "master4k": {"height": None, "codec": "hevc", "pix": "p010le", "bits": 10, "keep": False,
                 "desc": "canvas nativo (4K), HEVC VideoToolbox Main10 q:v 70, prio_speed"},
    "1080p": {"height": 1080, "codec": "h264", "pix": "nv12", "bits": 8, "bitrate": "16M", "keep": True,
              "desc": "1920×1080, H.264 VideoToolbox High 16 Mbps"},
    "proxy": {"height": 720, "codec": "h264", "pix": "nv12", "bits": 8, "bitrate": "5M", "keep": True,
              "desc": "1280×720, H.264 VideoToolbox 5 Mbps (anteprima)"},
}


# ── Utilità ─────────────────────────────────────────────────────────────────
def _even(x: float) -> int:
    return max(2, int(round(x / 2.0)) * 2)


def _sha(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _fps_fraction(value) -> Fraction:
    if isinstance(value, str) and "/" in value:
        n, d = value.split("/")
        return Fraction(int(n), int(d))
    f = Fraction(value).limit_denominator(1001)
    return f


def _tc(frames: int, fps: Fraction) -> float:
    return float(Fraction(frames) / fps)


_PROBE_CACHE: dict[str, dict] = {}


def probe_media(path: Path) -> dict:
    """Info essenziali di un media (cache per percorso+mtime)."""
    key = f"{path}:{path.stat().st_mtime_ns}"
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    info = yc.ffprobe(path)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    out = {"path": str(path), "duration": float(info["format"].get("duration") or 0),
           "size": path.stat().st_size, "mtime": path.stat().st_mtime}
    if v:
        # r_frame_rate (nominale) se plausibile e vicino alla media: i file con frame persi
        # (es. master con NAL corrotte) hanno avg_frame_rate tipo 63470/2119
        rate = v.get("avg_frame_rate") if v.get("avg_frame_rate") not in (None, "0/0") else v.get("r_frame_rate")
        try:
            r_nom, r_avg = _fps_fraction(v.get("r_frame_rate")), _fps_fraction(rate)
            if 0 < r_nom <= 120 and abs(float(r_nom - r_avg)) / float(r_nom) < 0.02:
                rate = str(r_nom)
        except (ValueError, ZeroDivisionError, TypeError):
            pass
        out.update(has_video=True, vcodec=v.get("codec_name"), width=int(v["width"]), height=int(v["height"]),
                   fps=str(_fps_fraction(rate)) if rate and rate != "0/0" else None, pix_fmt=v.get("pix_fmt"),
                   vprofile=v.get("profile"), color_transfer=v.get("color_transfer"),
                   nb_frames=int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None,
                   vduration=float(v.get("duration") or out["duration"]))
    else:
        out.update(has_video=False)
    if a:
        out.update(has_audio=True, acodec=a.get("codec_name"), channels=int(a.get("channels") or 0),
                   sample_rate=int(a.get("sample_rate") or 0), aduration=float(a.get("duration") or out["duration"]))
    else:
        out.update(has_audio=False)
    _PROBE_CACHE[key] = out
    return out


# ── EDL ─────────────────────────────────────────────────────────────────────
def _resolve_path(workdir: Path, p: str) -> Path:
    q = Path(p).expanduser()
    return (q if q.is_absolute() else workdir / q)


def load_edl(workdir: Path, edl_path: Path) -> dict:
    """Legge e valida edl.json; risolve i sorgenti (symlink → file reale). Errori in italiano."""
    if not edl_path.exists():
        raise FileNotFoundError(f"EDL non trovato: {edl_path}")
    edl = yc.read_json(edl_path)
    project = yc.load_project(workdir) if (workdir / "project.json").exists() else {}
    proj_sources = {k: v.get("path") for k, v in (project.get("sources") or {}).items()}
    raw_sources = {**proj_sources, **(edl.get("sources") or {})}
    if not edl.get("segments"):
        raise ValueError("EDL senza segmenti")

    sources: dict[str, dict] = {}
    for seg in edl["segments"]:
        key = seg.get("src") or project.get("main_source") or next(iter(raw_sources), None)
        seg["src"] = key
        if key not in raw_sources:
            raise ValueError(f"Segmento {seg.get('id')}: sorgente '{key}' non definito in EDL né in project.json")
        if key not in sources:
            path = _resolve_path(workdir, raw_sources[key])
            if not path.exists():
                raise FileNotFoundError(f"Sorgente {key} non trovato: {path}")
            real = path.resolve()
            info = probe_media(real)
            # decoder AAC dalla policy centrale (decisione di yt-ingest in project.json)
            pol = yc.aac_decoder_policy(workdir, {"path": str(real), "acodec": info.get("acodec")}) \
                if info.get("has_audio") else {"decoder": None, "args": [], "basis": "no-audio"}
            sources[key] = {"key": key, "link": str(path), "real": real, "info": info,
                            "adec": pol["args"], "adec_name": pol["decoder"], "adec_basis": pol["basis"]}

    first = next(iter(sources.values()))["info"]
    fps = _fps_fraction(edl.get("fps") or first.get("fps") or 30)
    canvas = edl.get("canvas") or {"w": first.get("width", 3840), "h": first.get("height", 2160)}
    ids = set()
    for i, seg in enumerate(edl["segments"], 1):
        seg.setdefault("id", f"s{i}")
        if seg["id"] in ids:
            raise ValueError(f"id segmento duplicato: {seg['id']}")
        ids.add(seg["id"])
        for k in ("in", "out"):
            if k not in seg:
                raise ValueError(f"Segmento {seg['id']}: manca '{k}'")
            seg[k] = yc.parse_ts(seg[k])
        if seg["out"] <= seg["in"]:
            raise ValueError(f"Segmento {seg['id']}: out ({seg['out']}) ≤ in ({seg['in']})")
        z = seg.get("zoom")
        if z:
            if float(z.get("scale", 1)) < 1.0:
                raise ValueError(f"Segmento {seg['id']}: zoom.scale < 1 non supportato (solo punch-in)")
            for c in ("cx", "cy"):
                if not 0.0 <= float(z.get(c, 0.5)) <= 1.0:
                    raise ValueError(f"Segmento {seg['id']}: zoom.{c} fuori da 0–1")

    overlays, music = [], []
    for o in edl.get("overlays") or []:
        p = _resolve_path(workdir, o["file"])
        if not p.exists():
            raise FileNotFoundError(f"Overlay non trovato: {p}")
        overlays.append({**o, "path": p.resolve(), "info": probe_media(p.resolve())})
    for m in edl.get("music") or []:
        p = _resolve_path(workdir, m["file"])
        if not p.exists():
            raise FileNotFoundError(f"Musica non trovata: {p}")
        music.append({**m, "path": p.resolve(), "info": probe_media(p.resolve())})
    audio = {"balance": "auto", "loudness": {"I": -14, "TP": -1.5, "LRA": 11}, **(edl.get("audio") or {})}
    return {"raw": edl, "fps": fps, "canvas": {"w": int(canvas["w"]), "h": int(canvas["h"])},
            "sources": sources, "segments": edl["segments"], "overlays": overlays, "music": music, "audio": audio}


def plan_segments(edl: dict) -> list[dict]:
    """Quantizza i segmenti al frame del timeline. I confini di uscita seguono la somma cumulata
    dei tempi EDL (errore ≤ ½ frame su tutta la durata); l'ingresso sorgente è il frame più vicino."""
    fps = edl["fps"]
    fpsf = float(fps)
    plan, cum = [], 0.0
    for i, seg in enumerate(edl["segments"]):
        src = edl["sources"][seg["src"]]
        start_f = round(cum * fpsf)
        cum += seg["out"] - seg["in"]
        end_f = round(cum * fpsf)
        n = end_f - start_f
        if n <= 0:
            raise ValueError(f"Segmento {seg['id']} più corto di un frame")
        in_f = round(seg["in"] * fpsf)
        src_dur = src["info"].get("vduration") or src["info"]["duration"]
        if _tc(in_f + n, fps) > src_dur + 0.5 / fpsf:
            raise ValueError(f"Segmento {seg['id']}: out {_tc(in_f + n, fps):.3f}s oltre la fine del sorgente "
                             f"{seg['src']} ({src_dur:.3f}s)")
        plan.append({
            "idx": i, "id": seg["id"], "label": seg.get("label"), "src": seg["src"],
            "src_path": str(src["real"]), "in_f": in_f, "n": n, "out_start_f": start_f,
            "src_in": round(_tc(in_f, fps), 6), "src_out": round(_tc(in_f + n, fps), 6),
            "out_start": round(_tc(start_f, fps), 6), "out_end": round(_tc(end_f, fps), 6),
            "edl_in": seg["in"], "edl_out": seg["out"],
            "zoom": seg.get("zoom"), "fade_in": float(seg.get("fade_in", 0.03) or 0),
            "fade_out": float(seg.get("fade_out", 0.03) or 0), "gain_db": float(seg.get("gain_db", 0) or 0),
        })
    return plan


def output_size(edl: dict, preset: str) -> tuple[int, int]:
    cw, ch = edl["canvas"]["w"], edl["canvas"]["h"]
    h = PRESETS[preset]["height"]
    if not h:
        return _even(cw), _even(ch)
    return _even(h * cw / ch), _even(h)


def zoom_crop(z: dict, sw: int, sh: int) -> tuple[int, int, int, int]:
    """Finestra di crop (w, h, x, y) in pixel sorgente per un punch-in, sempre dentro il frame."""
    s = float(z.get("scale", 1.0))
    cw, chh = _even(sw / s), _even(sh / s)
    cw, chh = min(cw, sw - sw % 2), min(chh, sh - sh % 2)
    x = int(round(float(z.get("cx", 0.5)) * sw - cw / 2))
    y = int(round(float(z.get("cy", 0.5)) * sh - chh / 2))
    x = max(0, min(sw - cw, x)) // 2 * 2
    y = max(0, min(sh - chh, y)) // 2 * 2
    return cw, chh, x, y


# ── Segmenti ────────────────────────────────────────────────────────────────
# Video e audio si renderizzano separatamente: i pezzi video si possono spezzare ai bordi degli
# overlay (solo il tratto con overlay passa dai filtri software) senza toccare l'audio, che resta
# un'unità continua per segmento con i fade solo ai tagli veri.
def _venc_args(preset: str, fps: Fraction, quality: int | None, fast: bool, intermediate: str) -> list[str]:
    gop = str(int(round(float(fps) * 2)))
    p = PRESETS[preset]
    if intermediate == "prores":
        return ["-c:v", "prores_videotoolbox", "-profile:v", "hq"]
    if p["codec"] == "hevc":
        return ["-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-q:v", str(quality or 70),
                "-prio_speed", "1" if fast else "0", "-bf", "0", "-g", gop, "-tag:v", "hvc1"]
    args = ["-c:v", "h264_videotoolbox", "-profile:v", "high", "-bf", "0", "-g", gop]
    return args + (["-q:v", str(quality)] if quality else ["-b:v", p["bitrate"]])


def _pix_fmt(preset: str, intermediate: str) -> str:
    return "p210le" if intermediate == "prores" else PRESETS[preset]["pix"]


def _overlay_span(o: dict) -> tuple[float, float]:
    at = float(o.get("at", 0))
    if o.get("until") is not None:
        return at, float(o["until"])
    if o.get("dur") is not None:
        return at, at + float(o["dur"])
    return at, at + float(o["info"].get("vduration") or o["info"]["duration"])


def split_pieces(plan: list[dict], overlays: list[dict], fps: Fraction) -> list[dict]:
    """Pezzi video: ogni segmento EDL spezzato (a frame interi) ai bordi delle finestre overlay."""
    fpsf = float(fps)
    bounds = []
    for o in overlays:
        a, b = _overlay_span(o)
        bounds += [round(a * fpsf), round(b * fpsf)]
    pieces = []
    for p in plan:
        s0, s1 = p["out_start_f"], p["out_start_f"] + p["n"]
        cuts = sorted({s0, s1, *[c for c in bounds if s0 < c < s1]})
        for k, (a, b) in enumerate(zip(cuts, cuts[1:])):
            pieces.append({**p, "piece": k, "in_f": p["in_f"] + (a - s0), "n": b - a, "out_start_f": a,
                           "out_start": round(_tc(a, fps), 6), "out_end": round(_tc(b, fps), 6)})
    return pieces


_BBOX_CACHE: dict[str, list[int] | None] = {}


def overlay_bbox(path: Path, info: dict) -> list[int] | None:
    """Riquadro (x, y, w, h) dei pixel non trasparenti dell'overlay su tutta la durata.
    Un lower third a canvas intero ha il 95% di pixel trasparenti: compositare solo il riquadro
    rende l'overlay ~10–20× più veloce in 4K. None = nessun canale alpha (overlay intero)."""
    key = f"{path}:{info['mtime']}"
    disk = yc.CACHE / "overlay_bbox.json"
    if not _BBOX_CACHE and disk.exists():
        try:
            _BBOX_CACHE.update(yc.read_json(disk))
        except Exception:  # noqa: BLE001
            pass
    if key in _BBOX_CACHE:
        return _BBOX_CACHE[key]
    pix = info.get("pix_fmt") or ""
    if not any(t in pix for t in ("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")):
        _BBOX_CACHE[key] = None
        return None
    w, h = int(info["width"]), int(info["height"])
    sw, sh = max(1, w // 4), max(1, h // 4)
    cmd = [yc.FFMPEG, "-hide_banner", "-nostdin", "-v", "error", "-i", str(path),
           "-vf", f"alphaextract,scale={sw}:{sh}:flags=area,format=gray", "-f", "rawvideo", "-"]
    acc = np.zeros((sh, sw), dtype=np.uint8)
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        while True:
            buf = proc.stdout.read(sw * sh)
            if len(buf) < sw * sh:
                break
            np.maximum(acc, np.frombuffer(buf, dtype=np.uint8).reshape(sh, sw), out=acc)
    ys, xs = np.nonzero(acc > 1)
    if not len(xs):
        bbox = [0, 0, 2, 2]  # overlay completamente trasparente
    else:
        m = 16  # margine in pixel pieni
        x0, y0 = max(0, xs.min() * 4 - m) // 2 * 2, max(0, ys.min() * 4 - m) // 2 * 2
        x1, y1 = min(w, (xs.max() + 1) * 4 + m), min(h, (ys.max() + 1) * 4 + m)
        bbox = [int(x0), int(y0), _even(x1 - x0), _even(y1 - y0)]
        bbox[2], bbox[3] = min(bbox[2], w - bbox[0]), min(bbox[3], h - bbox[1])
    _BBOX_CACHE[key] = bbox
    try:
        yc.write_json(disk, _BBOX_CACHE)
    except OSError:
        pass
    return bbox


def overlay_windows(pieces: list[dict], overlays: list[dict], fps: Fraction) -> list[list[dict]]:
    """Per ogni pezzo, gli overlay (o le loro porzioni) che cadono nella sua finestra di uscita."""
    res: list[list[dict]] = [[] for _ in pieces]
    for j, o in enumerate(overlays):
        at, end = _overlay_span(o)
        for i, p in enumerate(pieces):
            a, b = max(p["out_start"], at), min(p["out_end"], end)
            if b - a > 0.5 / float(fps):
                res[i].append({"j": j, "path": str(o["path"]), "mtime": o["info"]["mtime"],
                               "skip": round(max(0.0, p["out_start"] - at), 6),
                               "delay": round(max(0.0, at - p["out_start"]), 6),
                               "a": round(a - p["out_start"], 6), "b": round(b - p["out_start"], 6),
                               "x": float(o.get("x", 0)), "y": float(o.get("y", 0)),
                               "w": o["info"].get("width"), "h": o["info"].get("height"),
                               "bbox": overlay_bbox(o["path"], o["info"])})
    return res


def hw_eligible(p: dict, edl: dict, preset: str, ovs: list[dict]) -> bool:
    """Percorso tutto-hardware (decodifica → scale_vt → encoder, frame sempre in GPU): solo senza
    zoom, overlay o bande, con sorgente decodificabile da VideoToolbox."""
    src = edl["sources"][p["src"]]["info"]
    W, H = output_size(edl, preset)
    return (not p.get("zoom") and not ovs and src.get("vcodec") in ("h264", "hevc", "prores")
            and abs(src["width"] / src["height"] - W / H) < 0.01)


def _seek(p: dict, fps: Fraction) -> float:
    # ≤ pts del primo frame (arrotondato per difetto al µs): il frame resta incluso, mai saltato
    return math.floor(_tc(p["in_f"], fps) * 1e6) / 1e6


def video_command(p: dict, edl: dict, preset: str, ovs: list[dict], out_file: Path, *, quality: int | None,
                  fast: bool, intermediate: str, hw: bool = False) -> list[str]:
    """ffmpeg per un pezzo video: N frame esatti a fps costante del timeline.
    `hw`: frame sempre in GPU (scale_vt); altrimenti filtri software (crop, lanczos, overlay)."""
    fps = edl["fps"]
    src = edl["sources"][p["src"]]["info"]
    W, H = output_size(edl, preset)
    n = p["n"]
    dur = _tc(n, fps)
    cmd = [yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "warning"]
    if hw:
        cmd += ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
    elif src.get("vcodec") in HW_DECODE_CODECS:
        cmd += ["-hwaccel", "videotoolbox"]
    cmd += ["-ss", f"{_seek(p, fps):.6f}", "-t", f"{dur + 0.5:.6f}", "-an", "-i", p["src_path"]]
    for o in ovs:
        cmd += ["-ss", f"{o['skip']:.6f}", "-t", f"{o['b'] - o['a'] + 0.5:.6f}", "-i", o["path"]]

    # CFR al timeline (riempie eventuali buchi di decodifica), poi N frame esatti
    sw, sh = src["width"], src["height"]
    v = [f"fps={fps.numerator}/{fps.denominator}:start_time=0", "tpad=stop_mode=clone:stop_duration=1",
         f"trim=end_frame={n}", "setpts=PTS-STARTPTS"]
    if hw:
        if (sw, sh) != (W, H):
            v.append(f"scale_vt=w={W}:h={H}:color_matrix=bt709:color_primaries=bt709:color_transfer=bt709")
    else:
        if p.get("zoom"):
            cw, chh, x, y = zoom_crop(p["zoom"], sw, sh)
            v.append(f"crop={cw}:{chh}:{x}:{y}")
            sw, sh = cw, chh
        if (sw, sh) != (W, H):
            if abs(sw / sh - W / H) < 0.01:
                v.append(f"scale={W}:{H}:flags=lanczos")
            else:  # aspetto diverso: adatta senza deformare (bande)
                v.append(f"scale={W}:{H}:flags=lanczos:force_original_aspect_ratio=decrease")
                v.append(f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
        v.append("setsar=1")
    graph = [f"[0:v]{','.join(v)}[v0]"]
    last = "v0"
    fscale = W / edl["canvas"]["w"]
    ofmt = "yuv420p10" if PRESETS[preset]["bits"] == 10 or intermediate == "prores" else "yuv420"
    for k, o in enumerate(ovs, 1):
        chain = [f"setpts=PTS-STARTPTS+{o['delay']:.6f}/TB"]
        ox, oy, ow, oh = o["x"], o["y"], o.get("w"), o.get("h")
        if o.get("bbox"):  # solo il riquadro non trasparente
            bx, by, bw, bh = o["bbox"]
            chain.append(f"crop={bw}:{bh}:{bx}:{by}")
            ox, oy, ow, oh = ox + bx, oy + by, bw, bh
        if abs(fscale - 1) > 1e-6 and ow:
            chain.append(f"scale={_even(ow * fscale)}:{_even(oh * fscale)}:flags=lanczos")
        graph.append(f"[{k}:v]{','.join(chain)}[ov{k}]")
        graph.append(f"[{last}][ov{k}]overlay=x={int(round(ox * fscale))}:y={int(round(oy * fscale))}"
                     f":eof_action=pass:format={ofmt}:enable='between(t,{o['a']:.4f},{o['b']:.4f})'[v{k}]")
        last = f"v{k}"
    graph.append(f"[{last}]null[vout]" if hw else f"[{last}]format={_pix_fmt(preset, intermediate)}[vout]")
    ts = fps.numerator * (1000 if fps.denominator == 1 else 1)
    cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]",
            *_venc_args(preset, fps, quality, fast, intermediate),
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
            "-video_track_timescale", str(ts), "-f", "mov", str(out_file)]
    return cmd


def audio_samples(p: dict, fps: Fraction) -> int:
    return int(round(_tc(p["n"], fps) * SR))


def audio_command(p: dict, edl: dict, out_file: Path) -> list[str]:
    """ffmpeg per l'audio di un segmento: 48 kHz stereo, N·48000/fps campioni esatti, fade ai tagli."""
    fps = edl["fps"]
    src = edl["sources"][p["src"]]["info"]
    dur = _tc(p["n"], fps)
    m = audio_samples(p, fps)
    cmd = [yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "warning"]
    if src.get("has_audio"):
        cmd += ["-ss", f"{_seek(p, fps):.6f}", "-t", f"{dur + 0.5:.6f}"]
        cmd += [*edl["sources"][p["src"]].get("adec", []), "-vn", "-i", p["src_path"]]
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur + 0.5:.6f}", "-i", f"anullsrc=r={SR}:cl=stereo"]
    a = [f"aresample={SR}:async=1:min_hard_comp=0.02:first_pts=0", "aformat=sample_fmts=fltp:channel_layouts=stereo",
         f"atrim=end_sample={m}", f"apad=whole_len={m}", "asetpts=N/SR/TB"]
    if p["gain_db"]:
        a.append(f"volume={p['gain_db']:.2f}dB")
    fi, fo = min(p["fade_in"], dur / 2), min(p["fade_out"], dur / 2)
    if fi > 0:
        a.append(f"afade=t=in:st=0:d={fi:.4f}")
    if fo > 0:
        a.append(f"afade=t=out:st={dur - fo:.6f}:d={fo:.4f}")
    # float32: i picchi > 0 dBFS del master (decoder nativo) restano fino alla normalizzazione
    cmd += ["-af", ",".join(a), "-c:a", "pcm_f32le", "-ar", str(SR), "-ac", "2", "-f", "wav", str(out_file)]
    return cmd


# ── Post audio (bilanciamento + musica) ─────────────────────────────────────
def music_graph(music: list[dict], total: float, dialog_lufs: float | None = None,
                duck_db: float = 13.0) -> tuple[list[str], str, list[dict]]:
    """Ritorna (argomenti input musica, filter graph, note). Ingresso 0 = dialogo.
    Ducking: compressore sidechain (ratio 8) con soglia tarata sulla loudness del dialogo, così
    sul parlato a livello medio il letto scende di ~`duck_db` dB indipendentemente dal livello."""
    args, notes = [], []
    beds = []
    for i, m in enumerate(music):
        at = float(m.get("at", 0))
        if at >= total:
            notes.append({"file": str(m["path"]), "skipped": "inizia dopo la fine del montato"})
            continue
        loop = bool(m.get("loop"))
        fdur = float(m["info"]["duration"])
        end = min(total, float(m["until"]) if m.get("until") is not None else (total if loop else at + fdur))
        length = end - at
        if length <= 0.05:
            continue
        if loop:
            args += ["-stream_loop", "-1"]
        args += ["-i", str(m["path"])]
        k = len(beds) + 1
        fin = min(float(m.get("fade_in", 0.3)), length / 2)
        fout = min(float(m.get("fade_out", 1.0)), length / 2)
        chain = [f"aresample={SR}", "aformat=sample_fmts=fltp:channel_layouts=stereo",
                 f"atrim=end={length:.6f}", "asetpts=N/SR/TB", f"volume={float(m.get('gain_db', -20)):.2f}dB"]
        if fin > 0:
            chain.append(f"afade=t=in:st=0:d={fin:.3f}")
        if fout > 0:
            chain.append(f"afade=t=out:st={length - fout:.6f}:d={fout:.3f}")
        chain += [f"adelay={int(round(at * 1000))}:all=1", "apad"]
        beds.append({"k": k, "duck": m.get("duck", True) is not False, "chain": chain})
        notes.append({"file": str(m["path"]), "at": at, "end": round(end, 3), "gain_db": m.get("gain_db", -20),
                      "duck": m.get("duck", True) is not False, "loop": loop})
    if not beds:
        return [], "", notes
    g = []
    ducked = [b for b in beds if b["duck"]]
    plain = [b for b in beds if not b["duck"]]
    for b in beds:
        g.append(f"[{b['k']}:a]{','.join(b['chain'])}[m{b['k']}]")
    mixins = ["[dlg]"]
    if ducked:
        g.append("[0:a]asplit=2[dlg][key]")
        if len(ducked) > 1:
            g.append("".join(f"[m{b['k']}]" for b in ducked) + f"amix=inputs={len(ducked)}:normalize=0:duration=longest[dbus]")
            dbus = "[dbus]"
        else:
            dbus = f"[m{ducked[0]['k']}]"
        # taratura empirica su parlato da podcast (ratio 8): riduzione ≈ 5 dB + 0.8 × (I_dialogo − soglia)
        ratio = 8.0
        base = dialog_lufs if dialog_lufs is not None and math.isfinite(dialog_lufs) else -20.0
        th_db = base - max(0.0, (duck_db - 5.0) / 0.8)
        th = min(1.0, max(0.000976563, 10 ** (th_db / 20)))
        g.append(f"{dbus}[key]sidechaincompress=threshold={th:.6f}:ratio={ratio:g}:attack=15:release=350:makeup=1[ducked]")
        notes.append({"ducking": {"dialog_lufs": dialog_lufs, "threshold_db": round(th_db, 1), "ratio": ratio,
                                  "target_reduction_db": duck_db}})
        mixins.append("[ducked]")
    else:
        g.append("[0:a]anull[dlg]")
    mixins += [f"[m{b['k']}]" for b in plain]
    m_total = int(round(total * SR))
    g.append("".join(mixins) + f"amix=inputs={len(mixins)}:normalize=0:duration=first,"
             f"atrim=end_sample={m_total},apad=whole_len={m_total}[mix]")
    return args, ";".join(g), notes


# ── Verifica sincronia ──────────────────────────────────────────────────────
def _gray_frames(path: str, t: float, count: int, vf_pre: str = "", w: int = 192, h: int = 108) -> np.ndarray:
    vf = f"{vf_pre}scale={w}:{h}:flags=area,format=gray"
    cmd = [yc.FFMPEG, "-hide_banner", "-nostdin", "-v", "error", "-hwaccel", "videotoolbox",
           "-ss", f"{max(0.0, t):.6f}", "-i", path, "-frames:v", str(count), "-vf", vf, "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    k = len(out) // (w * h)
    return np.frombuffer(out[: k * w * h], dtype=np.uint8).reshape(k, h, w).astype(np.float32)


def _pcm(path: str, t: float, dur: float, sr: int = 16000, dec_args: list[str] | None = None) -> np.ndarray:
    """Audio mono float decodificato da `path` (dec_args: decoder dalla policy, [] = nativo)."""
    cmd = [yc.FFMPEG, "-hide_banner", "-nostdin", "-v", "error", "-ss", f"{max(0.0, t):.6f}", "-t", f"{dur:.6f}"]
    cmd += [*(dec_args or []), "-i", path, "-vn", "-af", ln.ASYNC, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32).astype(np.float64)


def verify_sync(out_file: Path, plan: list[dict], edl: dict, max_segments: int = 40) -> dict:
    """Confronta il montato con il sorgente vicino all'inizio e alla fine di ogni segmento:
    offset video in frame (sequenze di 12 frame in scala di grigi, ricerca ±4) e offset audio in ms
    (cross-correlazione 1 s a 16 kHz). Positivo = il contenuto arriva in ritardo nel montato."""
    fps = edl["fps"]
    fpsf = float(fps)
    t0 = time.time()
    sel = plan if len(plan) <= max_segments else [plan[int(i)] for i in np.linspace(0, len(plan) - 1, max_segments)]
    K, L = 12, 4
    rows = []
    for p in sel:
        src = edl["sources"][p["src"]]["info"]
        vf_pre = ""
        if p.get("zoom"):
            cw, chh, x, y = zoom_crop(p["zoom"], src["width"], src["height"])
            vf_pre = f"crop={cw}:{chh}:{x}:{y},"
        points = [min(12, p["n"] // 3)]
        if p["n"] > 3 * fpsf:
            points.append(p["n"] - int(fpsf) - K)
        for d in points:
            if d < 0 or p["n"] < K + 2:
                continue
            row = {"id": p["id"], "at_out": round(_tc(p["out_start_f"] + d, fps), 3)}
            try:
                s_frames = _gray_frames(p["src_path"], _tc(p["in_f"] + d, fps) - 0.25 / fpsf, K, vf_pre)
                o_frames = _gray_frames(str(out_file), _tc(p["out_start_f"] + d - L, fps) - 0.25 / fpsf, K + 2 * L)
                costs = {}
                for lag in range(-L, L + 1):
                    seg = o_frames[L + lag: L + lag + len(s_frames)]
                    if len(seg) == len(s_frames) and len(seg):
                        costs[lag] = float(np.abs(seg - s_frames).mean())
                best = min(costs, key=costs.get)
                others = sorted(v for k2, v in costs.items() if k2 != best)
                row.update(video_lag_frames=best, video_cost=round(costs[best], 3),
                           video_confidence=round((others[0] - costs[best]) / (costs[best] + 1e-6), 3) if others else None)
            except Exception as exc:  # noqa: BLE001
                row["video_error"] = str(exc)[:200]
            try:
                sr = 16000
                pad = 0.6   # ricerca ±600 ms: scopre anche buchi/slittamenti grossi
                t_out = _tc(p["out_start_f"] + d, fps) + 0.05
                t_src = _tc(p["in_f"] + d, fps) + 0.05
                win = min(1.0, (p["n"] - d) / fpsf - 0.1)
                if win > 0.3:
                    o = _pcm(str(out_file), t_out, win, sr)
                    s0 = max(0.0, t_src - pad)
                    lead = int(round((t_src - s0) * sr))          # campioni di anticipo del sorgente
                    s = _pcm(p["src_path"], s0, (t_src - s0) + win + pad, sr,
                             dec_args=edl["sources"][p["src"]].get("adec"))
                    n = 1 << int(math.ceil(math.log2(len(s) + len(o))))
                    c = np.fft.irfft(np.fft.rfft(s, n) * np.conj(np.fft.rfft(o, n)), n)
                    # c[k] = Σ s[i+k]·o[i]: in sincronia il picco cade a k = lead
                    cc = c[: lead + int(pad * sr) + 1]
                    k = int(np.argmax(cc))
                    lag_ms = (lead - k) / sr * 1000          # >0: l'audio del montato è in ritardo
                    seg = s[k: k + len(o)]
                    nc = float(cc[k] / (math.sqrt(float((o * o).sum()) * float((seg * seg).sum())) + 1e-12))
                    row.update(audio_lag_ms=round(lag_ms, 2), audio_corr=round(nc, 3))
            except Exception as exc:  # noqa: BLE001
                row["audio_error"] = str(exc)[:200]
            rows.append(row)
    v_ok = [r for r in rows if "video_lag_frames" in r and (r.get("video_confidence") or 0) >= 0.05]
    a_ok = [r for r in rows if "audio_lag_ms" in r and (r.get("audio_corr") or 0) >= 0.3]
    bad_v = [r for r in v_ok if r["video_lag_frames"] != 0]
    bad_a = [r for r in a_ok if abs(r["audio_lag_ms"]) > 5.0]
    if len(rows) and len(a_ok) < len(rows) / 2:
        bad_a = bad_a or [{"note": "audio poco correlato al sorgente nella maggior parte dei punti"}]
    return {"checked_points": len(rows), "video_confident": len(v_ok), "audio_confident": len(a_ok),
            "video_offsets": sorted({r["video_lag_frames"] for r in v_ok}),
            "audio_max_abs_ms": round(max((abs(r["audio_lag_ms"]) for r in a_ok), default=0.0), 2),
            "in_sync": not bad_v and not bad_a, "points": rows, "elapsed_s": round(time.time() - t0, 1)}


# ── Consegna ────────────────────────────────────────────────────────────────
def deliver(workdir: Path, assembled: Path, edl: dict, preset: str, codec: str, force: bool,
            logfile: Path) -> dict:
    project = yc.load_project(workdir) if (workdir / "project.json").exists() else {}
    slug = project.get("slug") or workdir.name
    name = f"{slug}-proxy.mp4" if preset == "proxy" else f"{slug}-master.mp4"
    out = workdir / "deliver" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    mix = workdir / "edit" / "mix.wav"
    warnings: list[str] = []
    t0 = time.time()
    loud = edl["audio"].get("loudness") or {}
    target = float(loud.get("I", -14)); tp = float(loud.get("TP", -1.5)); lra = float(loud.get("LRA", 11))

    mix_report = None
    if not mix.exists() or mix.stat().st_mtime < assembled.stat().st_mtime:
        if mix.exists():
            warnings.append("edit/mix.wav più vecchio del montato: rigenerato")
        yc.log("▶ mix normalizzato mancante → yt-loudnorm (bilanciamento già applicato nel render)")
        mix_report = ln.normalize(assembled, mix, target=target, tp=tp, lra=lra, balance="none",
                                  chain=str(edl["audio"].get("chain", "none")), force=True)
    else:
        rp = mix.with_suffix(".loudnorm.json")
        mix_report = yc.read_json(rp) if rp.exists() else None
        yc.log(f"✓ uso il mix esistente {mix}")

    # già consegnato e aggiornato? (stesso video, stesso mix, stessa modalità)
    stamp = out.with_name(f".{out.name}.json")
    sig = {"assembled": [str(assembled), assembled.stat().st_mtime], "mix": [str(mix), mix.stat().st_mtime],
           "codec": codec}
    if not force and out.exists() and stamp.exists():
        try:
            old = yc.read_json(stamp)
            if old.get("sig") == sig:
                yc.log(f"✓ {out.name} già aggiornato (usa --force per rifare)")
                return {**old["result"], "skipped": True, "warnings": warnings}
        except Exception:  # noqa: BLE001
            pass

    vinfo = probe_media(assembled)
    minfo = ln.probe_audio(mix)
    if abs(minfo["duration"] - vinfo["vduration"]) > 0.05:
        warnings.append(f"mix.wav ({minfo['duration']:.3f}s) e video ({vinfo['vduration']:.3f}s) differiscono: "
                        "audio tagliato/riempito alla durata video")

    vcodec = vinfo["vcodec"]
    if codec == "copy" and vcodec not in ("h264", "hevc"):
        codec = "hevc"  # ProRes non va consegnato: ricodifica HEVC
    if codec == "copy":
        venc = ["-c:v", "copy"] + (["-tag:v", "hvc1"] if vcodec == "hevc" else [])
    elif codec == "hevc":
        venc = ["-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-q:v", "70", "-tag:v", "hvc1",
                "-pix_fmt", "p010le"]
    else:  # h264 (YouTube: High, 2 B-frame, GOP mezzo fps)
        br = "40M" if vinfo["height"] > 1440 else "16M"
        venc = ["-c:v", "h264_videotoolbox", "-profile:v", "high", "-b:v", br, "-g",
                str(int(round(float(edl["fps"]) / 2))), "-pix_fmt", "nv12"]
    m = int(round(vinfo["vduration"] * SR))
    tmp = out.with_name(f".{out.stem}.tmp.mp4")
    cmd = [yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "warning"]
    if codec != "copy":
        cmd += ["-hwaccel", "videotoolbox"]
    cmd += ["-i", str(assembled), "-i", str(mix), "-map", "0:v:0", "-map", "1:a:0", *venc,
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-af", f"atrim=end_sample={m},apad=whole_len={m}",
            "-c:a", "aac_at", "-aac_at_mode", "cbr", "-b:a", "320k", "-ar", str(SR), "-ac", "2",
            "-movflags", "+faststart", "-metadata", f"title={project.get('title_working') or slug}",
            str(tmp)]
    yc.run(cmd, logfile=logfile)
    os.replace(tmp, out)
    t_mux = time.time() - t0

    # verifica consegna
    info = yc.ffprobe(out)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    as_ = next(s for s in info["streams"] if s["codec_type"] == "audio")
    meas = ln.measure_ebur128(out, ln.probe_audio(out))
    if meas["I"] is not None and abs(meas["I"] - target) > 0.5:
        warnings.append(f"Loudness consegna {meas['I']} LUFS fuori da {target}±0.5")
    if meas["TP"] is not None and meas["TP"] > tp + 0.5:
        warnings.append(f"True peak consegna {meas['TP']} dBTP sopra {tp} (+0.5 tolleranza encoder AAC)")
    with open(out, "rb") as fh:
        head = fh.read(4096)
    faststart = head.find(b"moov") != -1 and (head.find(b"mdat") == -1 or head.find(b"moov") < head.find(b"mdat"))
    result = {"file": str(out), "size_mb": round(out.stat().st_size / 1e6, 1), "elapsed_s": round(t_mux, 1),
            "video": {"codec": vs["codec_name"], "tag": vs.get("codec_tag_string"), "profile": vs.get("profile"),
                      "w": vs["width"], "h": vs["height"], "fps": vs.get("avg_frame_rate"),
                      "duration": float(vs.get("duration") or 0), "bitrate_mbps": round(int(vs.get("bit_rate", 0)) / 1e6, 1)},
            "audio": {"codec": as_["codec_name"], "sample_rate": int(as_["sample_rate"]), "channels": as_["channels"],
                      "bitrate_kbps": round(int(as_.get("bit_rate", 0)) / 1e3), "duration": float(as_.get("duration") or 0)},
            "loudness": meas, "faststart": faststart, "video_mode": codec,
            "mix": str(mix), "mix_balance": (mix_report or {}).get("balance", {}).get("decision"),
            "mix_loudness": (mix_report or {}).get("after")}
    yc.write_json(stamp, {"sig": sig, "result": result})
    return {**result, "skipped": False, "warnings": warnings}


# ── Render ──────────────────────────────────────────────────────────────────
def _stream(info: dict, kind: str) -> dict:
    return next(s for s in info["streams"] if s["codec_type"] == kind)


def render(workdir: Path, edl_path: Path, preset: str, out: Path, *, force: bool, jobs: int, quality: int | None,
           fast: bool, intermediate: str, keep_segments: bool | None, verify: bool, verify_max: int,
           sw_only: bool = False) -> dict:
    t_start = time.time()
    edl = load_edl(workdir, edl_path)
    plan = plan_segments(edl)
    fps = edl["fps"]
    W, H = output_size(edl, preset)
    timeline_path = out.with_name(out.stem + ".timeline.json")
    logfile = workdir / "logs" / "edl_render.log"
    warnings: list[str] = []
    for s in edl["sources"].values():
        i = s["info"]
        if i.get("fps") and _fps_fraction(i["fps"]) != fps:
            warnings.append(f"Sorgente {s['key']} a {i['fps']} fps ≠ timeline {fps}: conversione con filtro fps")
        if i.get("color_transfer") in ("arib-std-b67", "smpte2084"):
            warnings.append(f"Sorgente {s['key']} HDR ({i['color_transfer']}): nessun tone-mapping applicato")

    pieces = split_pieces(plan, edl["overlays"], fps)
    ovw = overlay_windows(pieces, edl["overlays"], fps)
    total_f = plan[-1]["out_start_f"] + plan[-1]["n"]
    total = _tc(total_f, fps)
    render_key = _sha({"v": RENDER_VERSION, "preset": preset, "q": quality, "fast": fast, "im": intermediate,
                       "sw": sw_only, "plan": plan, "ov": ovw, "audio": edl["audio"],
                       "music": [(str(m["path"]), m["info"]["mtime"], {k: v for k, v in m.items() if k not in ("path", "info")})
                                 for m in edl["music"]],
                       "src": {k: (str(s["real"]), s["info"]["size"], s["info"]["mtime"]) for k, s in edl["sources"].items()},
                       "adec": {k: s.get("adec_name") for k, s in edl["sources"].items()}, "afmt": "f32"})

    if not force and out.exists() and timeline_path.exists():
        try:
            old = yc.read_json(timeline_path)
            if old.get("render_key") == render_key and out.stat().st_mtime >= edl_path.stat().st_mtime:
                yc.log(f"✓ {out.name} già aggiornato per questo EDL/preset (usa --force per rifare)")
                return {"skipped": True, "timeline": old, "out": out, "timeline_path": timeline_path, "warnings": warnings}
        except Exception:  # noqa: BLE001
            pass

    segdir = workdir / "edit" / ".render" / preset
    segdir.mkdir(parents=True, exist_ok=True)
    venc = _venc_args(preset, fps, quality, fast, intermediate)
    vjobs, ajobs = [], []
    for i, p in enumerate(pieces):
        hw = (not sw_only) and hw_eligible(p, edl, preset, ovw[i])
        key = _sha({"v": RENDER_VERSION, "p": {k: p[k] for k in ("src_path", "in_f", "n", "zoom")},
                    "src": edl["sources"][p["src"]]["info"]["mtime"], "ovs": ovw[i], "venc": venc, "W": W, "H": H,
                    "fps": str(fps), "canvas": edl["canvas"], "hw": hw})
        vjobs.append({"p": p, "ovs": ovw[i], "hw": hw, "file": segdir / f"v_{p['idx'] + 1:04d}_{p['piece']:02d}_{key[:10]}.mov"})
    for p in plan:
        key = _sha({"v": RENDER_VERSION, "p": {k: p[k] for k in ("src_path", "in_f", "n", "fade_in", "fade_out", "gain_db")},
                    "src": edl["sources"][p["src"]]["info"]["mtime"], "fps": str(fps),
                    "adec": edl["sources"][p["src"]].get("adec_name"), "afmt": "f32"})
        ajobs.append({"p": p, "file": segdir / f"a_{p['idx'] + 1:04d}_{key[:10]}.wav"})

    vtodo = [j for j in vjobs if force or not j["file"].exists()]
    atodo = [j for j in ajobs if force or not j["file"].exists()]
    yc.log(f"▶ {len(plan)} segmenti ({len(pieces)} pezzi video) · {total:.2f}s · preset {preset} {W}×{H} · "
           f"da renderizzare {len(vtodo)} video + {len(atodo)} audio · jobs {jobs}")

    # 1a. audio per segmento (veloce, in parallelo)
    t_a = time.time()

    def awork(j):
        tmp = j["file"].with_name(f".{j['file'].stem}.tmp.wav")
        yc.run(audio_command(j["p"], edl, tmp), logfile=logfile)
        os.replace(tmp, j["file"])

    with ThreadPoolExecutor(max_workers=4) as ex:
        for fut in as_completed([ex.submit(awork, j) for j in atodo]):
            fut.result()
    t_audio = time.time() - t_a

    # 1b. pezzi video (riusa quelli già pronti con la stessa chiave)
    seg_times: dict[str, dict] = {}
    t_v = time.time()

    def vwork(j):
        p, ovs, f, hw = j["p"], j["ovs"], j["file"], j["hw"]
        tmp = f.with_name(f".{f.stem}.tmp.mov")
        t = time.time()
        kw = dict(quality=quality, fast=fast, intermediate=intermediate)
        try:
            yc.run(video_command(p, edl, preset, ovs, tmp, hw=hw, **kw), logfile=logfile)
        except RuntimeError:
            if not hw:
                raise
            yc.log(f"  ! {p['id']}: percorso hardware fallito, ripiego sui filtri software")
            hw = False
            yc.run(video_command(p, edl, preset, ovs, tmp, hw=False, **kw), logfile=logfile)
        os.replace(tmp, f)
        return j, time.time() - t, hw

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = [ex.submit(vwork, j) for j in vtodo]
        for k, fut in enumerate(as_completed(futs), 1):
            j, el, hw = fut.result()
            p = j["p"]
            dur = _tc(p["n"], fps)
            name = f"{p['id']}" + (f".{p['piece']}" if any(q["p"]["idx"] == p["idx"] and q["p"]["piece"] for q in vjobs) else "")
            seg_times[name] = {"seconds": round(dur, 3), "elapsed_s": round(el, 2), "speed_x": round(dur / el, 2),
                               "path": "hw" if hw else "sw", "overlay": bool(j["ovs"]), "zoom": bool(p.get("zoom"))}
            yc.log(f"  [{k}/{len(vtodo)}] {name} {yc.fmt_ts(_tc(p['in_f'], fps))} +{dur:.2f}s"
                   f"{' zoom' if p.get('zoom') else ''}{' overlay' if j['ovs'] else ''} ({'hw' if hw else 'sw'}) "
                   f"in {el:.1f}s = {dur / el:.2f}× RT")
    t_video = time.time() - t_v

    # controllo: ogni pezzo ha esattamente i frame/campioni attesi
    for j in vjobs:
        nf = int(_stream(yc.ffprobe(j["file"]), "video").get("nb_frames") or 0)
        if nf != j["p"]["n"]:
            raise RuntimeError(f"Pezzo video {j['file'].name}: {nf} frame, attesi {j['p']['n']}")
    for j in ajobs:
        ns = int(_stream(yc.ffprobe(j["file"]), "audio").get("duration_ts") or 0)
        if ns != audio_samples(j["p"], fps):
            raise RuntimeError(f"Audio {j['file'].name}: {ns} campioni, attesi {audio_samples(j['p'], fps)}")

    # 2. concat video in copia + audio continuo (bilanciamento, musica) → mux
    t_cat = time.time()
    vlist, alist = segdir / "video.txt", segdir / "audio.txt"
    vlist.write_text("".join(f"file '{j['file'].name}'\nduration {_tc(j['p']['n'], fps):.6f}\n" for j in vjobs))
    alist.write_text("".join(f"file '{j['file'].name}'\n" for j in ajobs))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_name(f".{out.stem}.tmp.mov")
    balance_mode = str(edl["audio"].get("balance") or "none")
    balance_report, music_notes = None, []
    with tempfile.TemporaryDirectory(prefix=".post-", dir=segdir) as td:
        tdp = Path(td)
        cur = tdp / "dialog.wav"
        yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(alist), "-c:a", "copy", str(cur)], logfile=logfile)
        if balance_mode != "none":
            bal = tdp / "dialog_bal.wav"
            balance_report = ln.render_balanced(cur, bal, balance_mode, tdp)
            balance_report = {k: v for k, v in balance_report.items() if not k.startswith("_")}
            yc.log(f"  bilanciamento: {balance_report.get('decision')} — {balance_report.get('reason', '')}")
            if balance_report.get("decision") != "keep":
                cur = bal
        dlg_lufs = ln.measure_ebur128(cur)["I"] if edl["music"] else None
        margs, mgraph, music_notes = music_graph(edl["music"], total, dlg_lufs, float(edl["audio"].get("duck_db", 13)))
        if mgraph:
            mixed = tdp / "mix_pre.wav"
            yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(cur), *margs,
                    "-filter_complex", mgraph, "-map", "[mix]", "-c:a", "pcm_f32le", "-ar", str(SR), str(mixed)],
                   logfile=logfile)
            cur = mixed
        yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                "-i", str(vlist), "-i", str(cur), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-c:a", "pcm_f32le", "-f", "mov", str(tmp_out)], logfile=logfile)
    os.replace(tmp_out, out)
    t_concat = time.time() - t_cat

    # 3. controlli: durata vs EDL
    pi = yc.ffprobe(out)
    vs, as_ = _stream(pi, "video"), _stream(pi, "audio")
    v_dur = float(vs.get("duration") or 0)
    a_dur = float(as_.get("duration") or 0)
    edl_sum_raw = sum(s["out"] - s["in"] for s in edl["segments"])
    duration = {"video": round(v_dur, 4), "audio": round(a_dur, 4), "container": round(float(pi["format"]["duration"]), 4),
                "frames": int(vs.get("nb_frames") or 0), "expected_frames": total_f,
                "edl_sum": round(edl_sum_raw, 4), "edl_sum_frames": round(total, 4),
                "delta_vs_edl_ms": round((v_dur - edl_sum_raw) * 1000, 1),
                "delta_av_ms": round((a_dur - v_dur) * 1000, 2)}
    duration["ok"] = abs(duration["delta_vs_edl_ms"]) <= 100 and abs(duration["delta_av_ms"]) <= 25 \
        and duration["frames"] == total_f
    if not duration["ok"]:
        warnings.append(f"Durata fuori tolleranza: {duration}")

    timeline = {
        "version": 1, "render_key": render_key, "edl": str(edl_path), "fps": f"{fps.numerator}/{fps.denominator}",
        "preset": preset, "size": {"w": W, "h": H}, "duration": round(total, 6), "file": str(out),
        "segments": [{"id": p["id"], "label": p["label"], "src": p["src"], "src_path": p["src_path"],
                      "src_in": p["src_in"], "src_out": p["src_out"], "out_start": p["out_start"],
                      "out_end": p["out_end"], "frames": p["n"], "zoom": p["zoom"]} for p in plan],
        "overlays": [{"file": str(o["path"]), "at": o.get("at"), "until": round(_overlay_span(o)[1], 3),
                      "x": o.get("x", 0), "y": o.get("y", 0)} for o in edl["overlays"]],
        "music": music_notes, "balance": balance_report,
        "audio_decoders": {k: {"decoder": s.get("adec_name"), "basis": s.get("adec_basis")}
                           for k, s in edl["sources"].items()},
        "render": {"duration_check": duration, "segment_times": seg_times,
                   "timings": {"audio_s": round(t_audio, 1), "video_s": round(t_video, 1),
                               "concat_post_s": round(t_concat, 1)},
                   "pieces": len(pieces), "created": time.strftime("%Y-%m-%dT%H:%M:%S")},
    }

    # 4. sincronia A/V ai tagli
    if verify:
        yc.log("▶ verifica sincronia A/V ai tagli…")
        sync = verify_sync(out, plan, edl, verify_max)
        timeline["render"]["sync"] = sync
        if not sync["in_sync"]:
            warnings.append(f"Possibile desincronizzazione: video {sync['video_offsets']} frame, "
                            f"audio max {sync['audio_max_abs_ms']} ms (dettagli in timeline.render.sync)")
    work_s = t_audio + t_video + t_concat
    timeline["render"]["timings"]["total_s"] = round(time.time() - t_start, 1)
    timeline["render"]["speed_x"] = round(total / max(1e-6, work_s), 2)
    yc.write_json(timeline_path, timeline)

    # pulizia: si tengono i pezzi per i preset leggeri (cache per i re-render), mai quelli vecchi
    keep = PRESETS[preset]["keep"] if keep_segments is None else keep_segments
    used = {j["file"].name for j in vjobs} | {j["file"].name for j in ajobs}
    for f in [*segdir.glob("v_*.mov"), *segdir.glob("a_*.wav"), *segdir.glob("seg_*.mov")]:
        if not keep or f.name not in used:
            f.unlink(missing_ok=True)
    if not keep:
        vlist.unlink(missing_ok=True)
        alist.unlink(missing_ok=True)
    return {"skipped": False, "timeline": timeline, "out": out, "timeline_path": timeline_path, "warnings": warnings}


# ── CLI ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        prog="yt-edl-render",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Renderizza edit/edl.json in edit/assembled.mov (+ assembled.timeline.json, mappa "
                    "uscita↔sorgente per sottotitoli, capitoli e clip). Opzionale: consegna MP4.",
        epilog="""Preset:
  master4k  canvas nativo (4K) HEVC VideoToolbox Main10 q:v 70 (+prio_speed): ~2.5–3.5× tempo reale
  1080p     1920×1080 H.264 VideoToolbox 16 Mbps: ~4–5× tempo reale
  proxy     1280×720 H.264 VideoToolbox 5 Mbps: anteprima veloce

EDL (design §8.3): segmenti {id, src, in, out, label, fade_in, fade_out, zoom{scale,cx,cy}, gain_db},
overlays {file, at, x, y, [dur|until]} (tempi sul montato, ProRes 4444 alpha), music {file, at,
gain_db, duck, [until, loop, fade_in, fade_out]}, audio {balance, loudness{I,TP,LRA}, chain}.

Esempi:
  yt-edl-render esempio/2026-10-13-ospite-paolo --preset proxy           # anteprima
  yt-edl-render esempio/2026-10-13-ospite-paolo --preset master4k --deliver
  yt-edl-render WORKDIR --deliver --deliver-codec h264          # MP4 H.264 per YouTube

Consegna (--deliver): deliver/<slug>-master.mp4 (proxy: <slug>-proxy.mp4), +faststart, AAC 48 kHz
320k dal mix normalizzato edit/mix.wav (se manca o è vecchio viene creato con yt-loudnorm ai valori
EDL audio.loudness). Il video è copiato dall'intermedio (HEVC hvc1/H.264) salvo --deliver-codec.
Segmenti intermedi in edit/.render/<preset>/ (tenuti come cache per 1080p/proxy).""")
    ap.add_argument("workdir", metavar="WORKDIR", help="cartella di lavoro (path o <channel>/<dir>)")
    ap.add_argument("--edl", default="edit/edl.json", help="EDL (default edit/edl.json)")
    ap.add_argument("--preset", choices=list(PRESETS), default="master4k", help="preset di uscita (default master4k)")
    ap.add_argument("--out", help="file montato (default edit/assembled.mov)")
    ap.add_argument("--quality", type=int, help="q:v VideoToolbox (1–100; master4k default 70; 1080p/proxy usano bitrate)")
    ap.add_argument("--no-fast", action="store_true", help="master4k senza prio_speed (≈35%% più lento, qualità quasi uguale)")
    ap.add_argument("--intermediate", choices=("auto", "prores"), default="auto",
                    help="prores = ProRes 422 HQ VideoToolbox (≈750 Mbps in 4K: solo per brani brevi)")
    ap.add_argument("--sw-scale", action="store_true",
                    help="niente percorso tutto-GPU: filtri software (scaler lanczos) anche sui segmenti semplici")
    ap.add_argument("--jobs", type=int, help="segmenti in parallelo (default 1 per master4k: l'encoder HEVC è unico; 2 altrimenti)")
    ap.add_argument("--keep-segments", dest="keep", action="store_true", default=None, help="tieni i segmenti intermedi")
    ap.add_argument("--no-keep-segments", dest="keep", action="store_false", help="cancella i segmenti intermedi")
    ap.add_argument("--no-verify", action="store_true", help="salta la verifica di sincronia A/V ai tagli")
    ap.add_argument("--verify-max", type=int, default=40, help="segmenti massimi da verificare (default 40)")
    ap.add_argument("--deliver", action="store_true", help="crea anche deliver/<slug>-master.mp4")
    ap.add_argument("--deliver-codec", choices=("copy", "hevc", "h264"), default="copy",
                    help="video della consegna: copia dell'intermedio (default), HEVC o H.264 VideoToolbox")
    ap.add_argument("--force", action="store_true", help="rifà tutto anche se aggiornato")
    a = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(a.workdir)
        edl_path = (workdir / a.edl) if not Path(a.edl).is_absolute() else Path(a.edl)
        out = Path(a.out).expanduser() if a.out else workdir / "edit" / "assembled.mov"
        if not out.is_absolute():
            out = workdir / out
        jobs = a.jobs or (1 if a.preset == "master4k" else 2)
        res = render(workdir, edl_path, a.preset, out, force=a.force, jobs=jobs, quality=a.quality,
                     fast=not a.no_fast, intermediate=a.intermediate, keep_segments=a.keep,
                     verify=not a.no_verify, verify_max=a.verify_max, sw_only=a.sw_scale)
        tl = res["timeline"]
        outputs = {"assembled": str(res["out"]), "timeline": str(res["timeline_path"])}
        warnings = list(res["warnings"])
        delivered = None
        if a.deliver:
            edl = load_edl(workdir, edl_path)
            delivered = deliver(workdir, res["out"], edl, a.preset, a.deliver_codec, a.force,
                                workdir / "logs" / "edl_render.log")
            outputs["deliver"] = delivered["file"]
            outputs["mix"] = delivered["mix"]
            warnings += delivered.pop("warnings")
        # stato del progetto (design §8.1): edit dopo il montato, delivered dopo la consegna; mai indietro.
        # Solo per il montato di default (un --out/--edl alternativo è una prova, non il montaggio)
        if out == workdir / "edit" / "assembled.mov":
            _advance_status(workdir, "delivered" if delivered else "edit")
        r = tl.get("render", {})
        yc.emit(True, outputs=outputs, skipped=res["skipped"], preset=tl.get("preset"),
                segments=len(tl["segments"]), duration=tl["duration"],
                duration_check=r.get("duration_check"), speed_x=r.get("speed_x"), timings=r.get("timings"),
                segment_times=r.get("segment_times"),
                sync={k: v for k, v in (r.get("sync") or {}).items() if k != "points"} or None,
                balance=(tl.get("balance") or {}).get("decision"), deliver=delivered, warnings=warnings)
    except Exception as exc:  # noqa: BLE001
        yc.fail(str(exc))


STATUS_ORDER = ["new", "ingested", "transcribed", "story", "edit", "delivered"]


def _advance_status(workdir: Path, target: str) -> None:
    try:
        status = yc.load_project(workdir).get("status") or "new"
        if status not in STATUS_ORDER or STATUS_ORDER.index(status) < STATUS_ORDER.index(target):
            yc.update_project(workdir, status=target)
    except (OSError, ValueError) as exc:
        yc.log(f"stato del progetto non aggiornato: {exc}")


if __name__ == "__main__":
    main()
