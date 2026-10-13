"""Persone, set e video SINTETICI per i test delle thumbnail (nessuna persona reale, nessun dato di canale).

make_set(W, H, seed)                     → fondale RGB di un set inventato (parete, mensole, lampade, rumore)
make_person(size, face_px, seed, …)      → persona stilizzata RGBA (testa, capelli, occhi, bocca, collo, busto) + box del volto
cut_from_frame(frame, person, at, …)     → compone la persona nel frame e scrive il ritaglio 1:1 con i sidecar di yt-portrait cut
                                           (<name>.png, <name>.meta.json con «portrait», <name>.json con sorgente e box del volto)
encode_still_video(png, out, ffmpeg)     → video di 2 s dal frame (per il pop-out del template scena)

Le texture (pelle, capelli, maglia) hanno dettaglio a media frequenza, così il dettaglio del volto nel file servito
(Laplaciano a 720×405) e lo stacco volto–intorno si comportano come su un ritaglio vero.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _blobs(h: int, w: int, cell: float, rng: np.random.Generator, lo: float = -1.0, hi: float = 1.0) -> np.ndarray:
    """Rumore a macchie (celle di ~`cell` px, interpolazione bicubica), valori in [lo, hi]."""
    gh, gw = max(2, int(h / cell) + 2), max(2, int(w / cell) + 2)
    g = rng.uniform(0, 255, (gh, gw)).astype(np.uint8)
    up = np.asarray(Image.fromarray(g).resize((w, h), Image.BICUBIC), np.float64) / 255.0
    return lo + (hi - lo) * up


def make_set(W: int = 3840, H: int = 2160, seed: int = 7, base=(64, 74, 88)) -> np.ndarray:
    """Fondale di un set inventato (uint8 H×W×3): parete con gradiente, due mensole, tre lampade calde, grana."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.zeros((H, W, 3), np.float64)
    grad = 0.75 + 0.35 * (1 - yy / H) * (0.6 + 0.4 * np.cos((xx / W - 0.5) * np.pi))
    for c in range(3):
        img[..., c] = base[c] * grad
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for y0 in (int(H * 0.30), int(H * 0.55)):
        d.rectangle((int(W * 0.05), y0, int(W * 0.95), y0 + int(H * 0.018)), fill=(118, 96, 74))
        x = int(W * 0.07)
        while x < W * 0.93:
            bw = int(rng.integers(30, 90))
            bh = int(rng.integers(int(H * 0.08), int(H * 0.15)))
            col = tuple(int(v) for v in rng.integers(40, 200, 3))
            d.rectangle((x, y0 - bh, x + bw, y0), fill=col)
            x += bw + int(rng.integers(6, 40))
    for cx in (0.18, 0.5, 0.82):
        r = int(H * 0.05)
        d.ellipse((int(W * cx) - r, int(H * 0.08) - r, int(W * cx) + r, int(H * 0.08) + r), fill=(250, 214, 150))
    im = im.filter(ImageFilter.GaussianBlur(2))
    a = np.asarray(im, np.float64)
    a += _blobs(H, W, 40, rng, -10, 10)[..., None]
    a += rng.normal(0, 3, a.shape)
    return np.clip(a, 0, 255).astype(np.uint8)


def make_person(size: tuple[int, int], face_px: float, seed: int = 1, skin=(214, 166, 136), hair=(46, 36, 32),
                shirt=(52, 70, 104), face_cx: float = 0.5, face_top: float | None = None, bottom_full: bool = True
                ) -> tuple[np.ndarray, list[float]]:
    """Persona stilizzata testa e spalle in un PNG RGBA di `size` (w, h): volto alto `face_px` (box occhi-mento come
    Vision), centrato a `face_cx` della larghezza; con `bottom_full` il busto arriva al bordo basso (bordo dritto da
    portare a filo del canvas). Ritorna (rgba uint8, box del volto [x, y, w, h] in px)."""
    w, h = size
    rng = np.random.default_rng(seed)
    S = 2                                                     # disegno a 2× e riduzione: bordi antialias
    W2, H2 = w * S, h * S
    fh = face_px * S
    fw = fh * 0.78
    fcx = face_cx * W2
    fy = (face_top * H2) if face_top is not None else 0.62 * fh
    fx = fcx - fw / 2
    mask = Image.new("L", (W2, H2), 0)
    md = ImageDraw.Draw(mask)
    # busto (spalle che scendono in curva, niente lati dritti: un bordo dritto sarebbe un taglio) e collo
    sh_y = fy + fh * 1.18
    sh_w = fw * 2.7
    bot = H2 + fh * 2.2 if bottom_full else sh_y + fh * 1.6
    md.ellipse((fcx - sh_w / 2, sh_y, fcx + sh_w / 2, sh_y + 2 * (bot - sh_y)), fill=255)
    if not bottom_full and bot < H2:                          # busto che finisce dentro il PNG (taglio sotto il petto)
        md.rectangle((0, bot, W2, H2), fill=0)
    md.rectangle((fcx - fw * 0.28, fy + fh * 0.75, fcx + fw * 0.28, sh_y + fh * 0.2), fill=255)
    # testa (capelli compresi) e orecchie
    md.ellipse((fx - fw * 0.06, fy - fh * 0.42, fx + fw * 1.06, fy + fh * 1.02), fill=255)
    md.ellipse((fx - fw * 0.12, fy + fh * 0.30, fx + fw * 0.06, fy + fh * 0.60), fill=255)
    md.ellipse((fx + fw * 0.94, fy + fh * 0.30, fx + fw * 1.12, fy + fh * 0.60), fill=255)
    m = np.asarray(mask, np.float64) / 255.0
    yy, xx = np.mgrid[0:H2, 0:W2]
    # aree: pelle (volto, orecchie, collo), capelli (calotta), maglia (busto)
    face_e = ((xx - fcx) / (fw / 2)) ** 2 + ((yy - (fy + fh * 0.5)) / (fh * 0.53)) ** 2 <= 1
    hair_e = (((xx - fcx) / (fw * 0.56)) ** 2 + ((yy - (fy + fh * 0.12)) / (fh * 0.56)) ** 2 <= 1) & (yy < fy + fh * 0.18)
    neck = (np.abs(xx - fcx) <= fw * 0.28) & (yy >= fy + fh * 0.75) & (yy < sh_y + fh * 0.2)
    torso = yy >= sh_y
    rgb = np.zeros((H2, W2, 3), np.float64)
    tex_skin = _blobs(H2, W2, fh / 26, rng, -22, 22)
    tex_fine = _blobs(H2, W2, fh / 60, rng, -20, 20)
    tex_hair = _blobs(H2, W2, fh / 40, rng, -18, 18)
    tex_shirt = _blobs(H2, W2, fh / 18, rng, -16, 16)
    shade = 1.0 - 0.18 * np.clip((xx - fcx) / (fw * 0.8), -1, 1) ** 2
    for c in range(3):
        rgb[..., c] = shirt[c] + tex_shirt
    skin_m = (face_e | neck | (m > 0) & ~torso & ~hair_e) & ~torso
    for c in range(3):
        rgb[..., c] = np.where(skin_m, skin[c] * shade + tex_skin + tex_fine, rgb[..., c])
        rgb[..., c] = np.where(hair_e & (m > 0), hair[c] + tex_hair, rgb[..., c])
    rgb += rng.normal(0, 5, rgb.shape)                        # grana fine: distribuzioni di luma continue, come una foto
    im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), m * 255]).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(im)
    # occhi, sopracciglia, naso, bocca (geometria fissa del volto)
    for side in (-1, 1):
        ex = fcx + side * fw * 0.2
        ey = fy + fh * 0.42
        d.ellipse((ex - fw * 0.075, ey - fh * 0.03, ex + fw * 0.075, ey + fh * 0.03), fill=(245, 242, 236, 255))
        d.ellipse((ex - fw * 0.032, ey - fh * 0.03, ex + fw * 0.032, ey + fh * 0.03), fill=(52, 38, 30, 255))
        d.line((ex - fw * 0.1, ey - fh * 0.09, ex + fw * 0.09, ey - fh * 0.1), fill=(60, 44, 36, 255), width=int(max(2, fh * 0.025)))
    d.line((fcx, fy + fh * 0.48, fcx - fw * 0.04, fy + fh * 0.66), fill=(170, 120, 96, 255), width=int(max(2, fh * 0.015)))
    d.arc((fcx - fw * 0.17, fy + fh * 0.70, fcx + fw * 0.17, fy + fh * 0.86), 15, 165, fill=(150, 72, 66, 255), width=int(max(2, fh * 0.03)))
    im = im.resize((w, h), Image.LANCZOS)
    a = np.asarray(im).copy()
    a[..., 3] = np.where(a[..., 3] < 6, 0, a[..., 3])
    return a, [fx / S, fy / S, fw / S, fh / S]


def _meta(rgba: np.ndarray, face: list[float], portrait: dict) -> dict:
    """<png>.meta.json nel formato di yt-portrait cut (write_render_meta): sagoma a 64 fasce, bordi, volto esatto."""
    a = rgba[..., 3] > 127
    h, w = a.shape
    ys, xs = np.where(a)
    left, right = [], []
    for i in range(64):
        rows = a[int(i * h / 64): max(int((i + 1) * h / 64), int(i * h / 64) + 1)]
        cols = np.where(rows.any(axis=0))[0]
        left.append(round(float(cols.min()) / w, 4) if len(cols) else -1)
        right.append(round(float(cols.max() + 1) / w, 4) if len(cols) else -1)
    touches = {"left": bool(a[:, :2].any()), "right": bool(a[:, -2:].any()), "top": bool(a[:2].any()), "bottom": bool(a[-2:].any())}
    return {"w": w, "h": h, "alpha_box": [round(xs.min() / w, 4), round(ys.min() / h, 4), round((xs.max() - xs.min() + 1) / w, 4),
                                          round((ys.max() - ys.min() + 1) / h, 4)],
            "profile": {"left": left, "right": right}, "touches": touches,
            "face": [round(face[0] / w, 5), round(face[1] / h, 5), round(face[2] / w, 5), round(face[3] / h, 5)],
            "face_detected": True, "portrait": portrait}


def write_cut(out_png: Path, rgba: np.ndarray, face: list[float], eff_face_px: float | None = None, scale: float = 1.0,
              source: dict | None = None) -> Path:
    """Scrive un ritaglio «come yt-portrait cut»: PNG + <name>.meta.json (chiave portrait) + <name>.json (tool, sorgente)."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(out_png)
    eff = eff_face_px if eff_face_px is not None else face[3] / scale
    portrait = {"scale": scale, "face_out_px": round(face[3], 1), "face_px_source": round(face[3] / scale, 1),
                "eff_face_px": round(eff, 1), "eff_upscale": round(scale * face[3] / scale / max(eff, 1e-6), 3),
                "matte": "sintetico", "straight_edges": {}, "source": source or {"kind": "still"}}
    out_png.with_suffix(".meta.json").write_text(json.dumps(_meta(rgba, face, portrait)))
    return out_png


def cut_from_frame(frame: np.ndarray, person: tuple[np.ndarray, list[float]], at: tuple[int, int], out_png: Path,
                   video: str | None = None, t: float = 0.5, eff_face_px: float | None = None) -> tuple[np.ndarray, Path]:
    """Compone la persona nel frame (in place, ritorna il frame) alla posizione `at` (angolo alto-sinistro, px) e scrive
    il ritaglio 1:1 con i sidecar di yt-portrait cut, compreso <name>.json con sorgente e box del volto (pop-out)."""
    rgba, face = person
    x0, y0 = at
    h, w = rgba.shape[:2]
    H, W = frame.shape[:2]
    # ritaglio: solo la parte della persona dentro il frame (un ritaglio vero non esce dalla sorgente)
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    sub = rgba[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0].copy()
    al = sub[..., 3:4].astype(np.float64) / 255.0
    region = frame[cy0:cy1, cx0:cx1].astype(np.float64)
    frame[cy0:cy1, cx0:cx1] = np.round(region * (1 - al) + sub[..., :3] * al).astype(np.uint8)
    f2 = [face[0] - (cx0 - x0), face[1] - (cy0 - y0), face[2], face[3]]
    src = {"video": video, "t": t, "layout": "full", "kind": "camera"} if video else {"kind": "still"}
    write_cut(out_png, sub, f2, eff_face_px=eff_face_px, source=src)
    side = {"portrait_version": 2, "tool": "yt-portrait cut", "name": Path(out_png).stem, "source": src, "roi": "full",
            "roi_px": [0, 0, W, H], "scale": 1.0, "face_px_source": round(f2[3], 1),
            "face_box_source_px": [round(cx0 + f2[0], 1), round(cy0 + f2[1], 1), round(f2[2], 1), round(f2[3], 1)],
            "face_box_out_px": [round(v, 1) for v in f2]}
    Path(out_png).with_suffix(".json").write_text(json.dumps(side))
    return frame, Path(out_png)


def encode_still_video(png: Path, out: Path, ffmpeg: str, seconds: float = 2.0) -> Path:
    """Video H.264 di `seconds` s da un frame fisso (sorgente finta per il pop-out del template scena)."""
    out = Path(out)
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-loop", "1", "-i", str(png), "-t", str(seconds), "-r", "25",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12", str(out)], check=True)
    return out


def make_artifact(path: Path, w: int = 1600, h: int = 1000, seed: int = 3) -> Path:
    """Schermata finta (grafico a barre su una card chiara), per il template prova."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGB", (w, h), (248, 248, 250))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w, 90), fill=(30, 34, 44))
    for i in range(12):
        bh = int(rng.integers(120, int(h * 0.7)))
        x = 90 + i * (w - 180) // 12
        d.rectangle((x, h - 80 - bh, x + (w - 180) // 12 - 24, h - 80), fill=(70, 120, 220))
    d.line((80, h - 80, w - 80, h - 80), fill=(120, 120, 130), width=4)
    im.save(path)
    return path
