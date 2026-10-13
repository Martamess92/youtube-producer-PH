"""yt-portrait — ritratti dell'ospite per le thumbnail, dal master composito o da uno still, senza AI generativa.

Sottocomandi (knowledge 07 §10–§11):

  scan WORKDIR   una sola passata VideoToolbox sul master: coppie di frame (n, n+1) ogni --every s, ritagli
                 dell'inset e del posto dell'ospite nel campo largo; layout per campione (sonde di layout.json
                 sul proxy), thumbvision score, mosso (differenza n→n+1 nel volto), scarti, classifica,
                 risoluzione effettiva del volto (test di riduzione) sui migliori, fogli di contatto.
                 → <out>/scan.json + scan_sheet_*.jpg + scan_expr.jpg (risate/bocca aperta, da giudicare a occhio)

  cut WORKDIR --t T[,T…] | --image STILL
                 1. frame esatto a 16 bit (zscale BT.709 limited→full, spline36), ritaglio alla ROI;
                 2. volto con thumbvision (il più grande, o il più vicino a --point);
                 3. matte BiRefNet-portrait (venv rembg, worker portrait_matte.py) su busto + tile della testa,
                    solo le componenti attaccate al volto, PiP escluso; ripiego: Apple Vision (thumbvision
                    cutout, matte accurate, decontam 4, senza choke);
                 4. colore dei bordi: pymatting ML + clamp dello spill caldo (R−B entro quello dell'interno)
                    + clamp dell'alone chiaro (luma della banda morbida entro ±6/255 dall'interno);
                 5. resize premoltiplicato spline36 a 16 bit + nitidezza solo luma (σ 0.7, 0.6) + livelli
                    dell'alpha 0.1–0.95; volto alla misura chiesta, mai oltre --max-upscale (2.0×, 07 §10.1);
                 6. <name>.png (RGBA 8 bit, da disegnare 1:1 nel template a DPR 3), <name>_16.png, <name>.json
                    (volto, scala, risoluzione effettiva, bordi dritti da tenere a filo del canvas),
                    <name>_proof.jpg (confronto volto: sorgente ricampionata | ritaglio, differenza misurata).

  plate WORKDIR --t T   fondale della location senza persone per la plate dei template duo/ritratto (maschera Vision di tutte le persone,
                 PiP, convoluzione normalizzata dei pixel del fondale, 16:9, sfocatura): nessuna AI generativa.

  duo WORKDIR --t T     ospite + host dallo stesso istante del campo largo, testa e spalle, ciascuno col suo tetto;
                 l'host mai più grande dell'ospite.
  selftest       prove unitarie senza media.

Thumbnail v2:
  • tetto al display (T2): `cut --display-cap c` (default) = volto a 1280 px ≤ 2,0× la risoluzione EFFETTIVA del volto
    nel sorgente (b = 1,5×, legacy = il vecchio 2,0× sul box); `--face-frac max` = il volto più grande consentito, che
    rispetta anche il dettaglio al formato servito (Laplaciano del volto nel render ridotto a 720×405: avviso < 713,
    errore < 569, stima validata su ritagli reali). Nel sidecar <png>.meta.json: portrait.display_cap e portrait.served_detail;
    yt-thumb-render li controlla con display_cap_check() e served_face_detail() (oltre il tetto: errore senza override).
  • classi di espressione (T3/T3b, lib/expressions.py): sorriso, risata, intenso, sorpresa, neutro, scettico; geometria
    dei landmark Vision (thumbvision 1.1) e, se installato, MediaPipe Face Landmarker (blendshape); frame a metà parola
    tolti con i tempi delle parole della trascrizione; scan_expr.jpg = una riga per classe con i primi 3.
  • camera stretta: `scan --source FILE --layout full` (nessuna ipotesi su un master composito, offset audio verso il
    master); `cut --src FILE --camera --offset S --roi full`.
  • duo: `scan --layout wide --seat all` = tutti i posti del campo largo, speaker per posto (bocca ↔ trascrizione) e
    momenti duo nello stesso istante (scan_duo.jpg); poi `duo`.

Senza layout composito misurato (layout.json del brand con inset o sonde) `--layout auto` e `--roi auto` usano tutto il
fotogramma: una sola camera, nessuna ipotesi.

Niente denoise temporale (misurato: −7/13% di rumore, −2/5% di dettaglio), niente upscaler AI, niente
modifiche al volto: solo ricampionamento, matte e decontaminazione della banda del bordo.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from scipy import ndimage  # noqa: E402

REMBG_PY = Path(os.environ.get("YT_REMBG_PY", yc.HOME / ".venvs" / "rembg" / "bin" / "python"))
REMBG_HOME = Path(os.environ.get("YT_REMBG_HOME", yc.HOME / ".venvs" / "rembg" / "home"))
WORKER = Path(__file__).resolve().parent / "portrait_matte.py"
ZS = ("zscale=filter=spline36:matrixin=709:transferin=709:primariesin=709:rangein=limited:range=full:"
      "matrix=709:transfer=709:primaries=709")
OUT_H = 2160                    # altezza del canvas della thumbnail (3840×2160)
OUT_W = 3840
MAX_UPSCALE = 2.0               # 07 §10.1, regola precedente: ≤ 2.0× sul box del volto nel sorgente (--display-cap legacy)
EFF_UPSCALE_WARN = 4.0          # proposta x4: ingrandimento sulla risoluzione effettiva (solo segnalato, modo legacy)
# Tetto misurato al display (opzione c; ripiego b): il volto nella thumbnail servita a
# 1280 px di larghezza non supera FACTOR × la sua risoluzione EFFETTIVA nel sorgente (eff_face_px, test di riduzione).
DISPLAY_W = 1280
DISPLAY_CAPS = {"c": 2.0, "b": 1.5}
DEFAULT_DISPLAY_CAP = "c"
FACE_FRAC_MAX = 0.50            # --face-frac max: il più grande consentito dal tetto, ma mai oltre metà altezza
# Dettaglio al formato servito: varianza del Laplaciano sul box del volto nel render ridotto a
# 720×405 (Lanczos). Soglie calibrate sui 66 riferimenti EN: p25 713 (avviso), p10 569 (errore).
SERVED_W = 720
SERVED_WARN, SERVED_ERR = 713.0, 569.0
CROP_PRESETS = {"cu": 1.6, "hs": 2.4, "bust": 3.6}   # altezza sotto il volto, in altezze di volto (cu = primo piano)
PORTRAIT_VERSION = 2
FONT = yc.FONTS / "Inter[opsz,wght].ttf"


# ── I/O a 16 bit (ffmpeg rawvideo) ──────────────────────────────────────────
def probe_stream(p: Path) -> dict:
    out = subprocess.run([yc.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,pix_fmt,r_frame_rate", "-of", "json", str(p)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = (s.get("r_frame_rate") or "30/1").split("/")
    return {"w": int(s["width"]), "h": int(s["height"]), "pix_fmt": s.get("pix_fmt", ""),
            "fps": float(num) / float(den or 1)}


def load16(p: Path, alpha: bool = False) -> np.ndarray:
    """PNG/JPEG (8 o 16 bit) → float64 0–1 (RGB, o RGBA con alpha=True)."""
    s = probe_stream(p)
    pf = "rgba64le" if alpha else "rgb48le"
    raw = subprocess.run([yc.FFMPEG, "-nostdin", "-v", "error", "-i", str(p), "-f", "rawvideo", "-pix_fmt", pf, "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint16).reshape(s["h"], s["w"], 4 if alpha else 3).astype(np.float64) / 65535.0


def save16(a: np.ndarray, p: Path) -> None:
    a = np.clip(a, 0, 1)
    h, w, c = a.shape
    pf = "rgba64le" if c == 4 else "rgb48le"
    subprocess.run([yc.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", pf, "-s", f"{w}x{h}", "-i", "-",
                    "-pix_fmt", "rgba64be" if c == 4 else "rgb48be", str(p)],
                   input=(a * 65535 + 0.5).astype("<u2").tobytes(), check=True)


def to8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def luma(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def font(size: int, weight: int = 600) -> ImageFont.FreeTypeFont:
    try:
        f = ImageFont.truetype(str(FONT), size)
        try:
            f.set_variation_by_axes([max(14, min(32, size)), weight])
        except Exception:  # noqa: BLE001
            pass
        return f
    except OSError:
        return ImageFont.load_default()


# ── Sorgente, layout, ROI ───────────────────────────────────────────────────
def default_channel() -> str | None:
    """Canale quando né il workdir né --channel lo dicono: l'unico profilo <slug>.md dei channels_dirs, se ce n'è
    esattamente uno (i file che iniziano con «_» sono modelli); altrimenti None (nessun layout: tutto il fotogramma)."""
    fn = getattr(yc, "default_channel", None)
    if callable(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001 — si ripiega sulla ricerca locale
            pass
    slugs: set[str] = set()
    for d in getattr(yc, "CHANNELS_DIRS", []) or []:
        try:
            slugs |= {p.stem for p in Path(d).glob("*.md") if not p.name.startswith("_")}
        except OSError:
            continue
    return next(iter(slugs)) if len(slugs) == 1 else None


def brand_layout(channel: str | None) -> dict | None:
    """layout.json misurato per il canale (stesso risolutore di yt-clips e yt-thumb-render: brand.slug del profilo,
    poi la cartella del canale). Il layout generico del brand demo non conta: nessuna geometria composita."""
    if not channel:
        return None
    p = yc.layout_file(channel)
    if p == yc.brand_file(yc.BUILTIN_BRAND, "layout.json"):
        return None
    return yc.read_json(p) if p.exists() else None


def is_composite(layout: dict | None) -> bool:
    """Layout di un master composito misurato (inset dell'ospite o sonde di classificazione): solo allora `auto` cerca
    inset e campo largo; altrimenti una sola camera e tutto il fotogramma."""
    return bool(layout) and bool(rect_of(layout, "inset") or (layout or {}).get("probes"))


def rect_of(layout: dict | None, key: str) -> list[int] | None:
    r = (layout or {}).get(key)
    if isinstance(r, dict) and all(k in r for k in ("x", "y", "w", "h")):
        return [int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])]
    return None


SEATS = {"left": 0, "center": 1, "right": 2}


def roi_rect(name: str, layout: dict | None, W: int, H: int, seat: str = "right") -> list[int]:
    """ROI in px del frame: inset | wide | wide-left|center|right | full | 'x,y,w,h' (px o 0–1)."""
    if re.fullmatch(r"[\d.,\s]+", name or ""):
        v = [float(x) for x in name.split(",")]
        if all(x <= 1 for x in v):
            v = [v[0] * W, v[1] * H, v[2] * W, v[3] * H]
        return [int(round(x)) for x in v]
    if name == "full":
        return [0, 0, W, H]
    if name == "inset":
        r = rect_of(layout, "inset")
        if not r:
            raise RuntimeError("layout.json senza 'inset': passa --roi x,y,w,h")
        return [r[0], r[1], r[2] - 1, r[3] - 1]      # 1 px dentro: niente filo del bordo arrotondato
    if name.startswith("wide"):
        win = rect_of(layout, "wide") or [0, 0, W, H]
        s = name.split("-", 1)[1] if "-" in name else seat
        cxs = ((layout or {}).get("wide") or {}).get("people_cx") or [0.2, 0.48, 0.8]
        i = SEATS.get(s, 2)
        if i >= len(cxs):
            i = len(cxs) - 1
        cx = win[0] + cxs[i] * win[2]
        half = 0.243 * win[2]
        x0, x1 = max(0, int(cx - half)), min(W, int(cx + half))
        y0 = max(0, win[1] - 18)
        return [x0, y0, x1 - x0, min(H, win[1] + win[3]) - y0]
    raise RuntimeError(f"ROI sconosciuta: {name}")


def classify_at(src: Path, t: float, layout: dict | None) -> str:
    """inset | wide | card | other al tempo t (sonde di layout.json, come yt-clips)."""
    if not layout or not layout.get("probes"):
        return "other"
    try:
        import clips  # noqa: WPS433 — classificatore condiviso con yt-clips
        return clips.classify_frame(clips.grab_frame(src, t, clips.SMALL), layout)[0]
    except Exception as e:  # noqa: BLE001
        yc.log(f"[layout] classificazione non riuscita a {t:.2f}s: {e}")
        return "other"


def extract16(src: Path, t: float, out: Path, crop: list[int] | None = None) -> None:
    """Frame esatto (primo frame con pts ≥ t − 5 ms) a 16 bit RGB, BT.709 limited → full con zscale spline36."""
    info = probe_stream(src)
    hw = "p010le" if ("10" in info["pix_fmt"] or "p010" in info["pix_fmt"]) else "nv12"
    tail = ZS + ",format=gbrp16le" + (f",crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}" if crop else "")
    base = [yc.FFMPEG, "-nostdin", "-v", "error", "-y"]
    vt = base + ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld", "-ss", f"{max(0, t - 0.005):.4f}",
                 "-i", str(src), "-frames:v", "1", "-vf", f"hwdownload,format={hw}," + tail, str(out)]
    if subprocess.run(vt, capture_output=True).returncode == 0 and out.exists():
        return
    sw = base + ["-ss", f"{max(0, t - 0.005):.4f}", "-i", str(src), "-frames:v", "1", "-vf", tail, str(out)]
    proc = subprocess.run(sw, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"estrazione del frame a {t:.3f}s fallita: {proc.stderr[-400:]}")


def thumbvision(*args: str) -> object:
    if not yc.SWIFT_BIN.exists():
        raise RuntimeError(f"thumbvision non disponibile ({yc.SWIFT_BIN}): {yc.SETUP_HINT}")
    proc = subprocess.run([str(yc.SWIFT_BIN), *args], capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"thumbvision {args[0]}: output non JSON (exit {proc.returncode}): {proc.stderr[-300:]}")


def faces_px(png: Path) -> list[dict]:
    r = thumbvision("faces", str(png))
    r = r[0] if isinstance(r, list) else r
    W, H = r["w"], r["h"]
    out = []
    for f in r.get("faces") or []:
        b = f["box"]
        out.append({"box": [b[0] * W, b[1] * H, b[2] * W, b[3] * H], **{k: f.get(k) for k in ("yaw", "pitch", "roll", "face_px")}})
    return out


def pick_face(faces: list[dict], W: int, H: int, point: tuple[float, float] | None, seat_band: bool) -> dict:
    if not faces:
        raise RuntimeError("nessun volto trovato nella ROI (prova un altro tempo o --roi)")
    if point:
        return min(faces, key=lambda f: math.hypot(f["box"][0] + f["box"][2] / 2 - point[0], f["box"][1] + f["box"][3] / 2 - point[1]))
    cand = [f for f in faces if not seat_band or 0.2 * W < f["box"][0] + f["box"][2] / 2 < 0.8 * W] or faces
    return max(cand, key=lambda f: f["box"][3])


# ── Colore dei bordi ────────────────────────────────────────────────────────
def interior_colour(F: np.ndarray, a: np.ndarray, r: int) -> tuple[np.ndarray, np.ndarray]:
    inner = (ndimage.minimum_filter(a, size=2 * r + 1) > 0.98).astype(float)
    num = np.stack([ndimage.gaussian_filter(F[..., c] * inner, 1.5 * r) for c in range(3)], -1)
    den = ndimage.gaussian_filter(inner, 1.5 * r)
    return num / (den[..., None] + 1e-4), den


def spill_clamp(F: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Nella banda morbida, (R−B) non oltre quello dell'interno vicino (luminanza conservata): via il colore caldo dello sfondo."""
    est, _ = interior_colour(F, a, 8)
    Y = luma(F)
    excess = np.maximum(0, (F[..., 0] - F[..., 2]) - (est[..., 0] - est[..., 2]))
    w = np.clip((1 - a) * 1.5, 0, 1) * (a > 0.01)
    G = F.copy()
    G[..., 0] -= 0.5 * excess * w
    G[..., 2] += 0.5 * excess * w
    G += (Y - luma(G))[..., None]
    return np.clip(G, 0, 1)


def halo_clamp(F: np.ndarray, a: np.ndarray, delta: float = 6 / 255) -> np.ndarray:
    """Alone chiaro già nel sorgente (sharpening del montaggio): luma della banda entro ±delta dall'interno."""
    est, _ = interior_colour(F, a, 8)
    inner = ndimage.minimum_filter(a, size=17) > 0.98
    den = ndimage.gaussian_filter(inner.astype(float), 12)
    Y, Yin = luma(F), luma(est)
    w = np.clip((1 - a) * 2.0, 0, 1) * (a > 0.01) * (den > 0.02)
    Yt = Y * (1 - w) + np.clip(Y, Yin - delta, Yin + delta) * w
    return np.clip(F + (Yt - Y)[..., None], 0, 1)


def fill_face_holes(alpha: np.ndarray, F: np.ndarray, reg: np.ndarray, fb: list[float]) -> tuple[np.ndarray, np.ndarray, dict]:
    """Buchi del matte nella fascia degli occhi (lente degli occhiali), senza modelli.

    Buco = componente con α < 0.5 racchiusa dalla sagoma (binary_fill_holes), allargata di 2 px nel suo bordo morbido
    (α < 0.9); il bordo morbido esterno della sagoma non è un buco. Si riempie solo se: il baricentro cade nella
    fascia degli occhi del box del volto (x 8–92 %, y 12–70 %), la componente è piccola (≤ 8 % del box) e il colore
    del sorgente nel buco somiglia alla pelle del volto più che allo sfondo appena fuori dalla sagoma (lente davanti
    all'occhio = pelle e occhio veri; lente di profilo contro il muro = sfondo, resta trasparente perché dietro il
    vetro c'è il nuovo fondo). Nei pixel riempiti α = 1 e il colore è quello del sorgente, mai una stima: livello 0."""
    from scipy import ndimage

    solid = alpha >= 0.5
    filled = ndimage.binary_fill_holes(solid)
    core = filled & ~solid
    info = {"components": 0, "px": 0, "skipped": 0}
    lab, k = ndimage.label(core)
    if not k:
        return alpha, F, info
    fx, fy, fw, fh = fb
    H, W = alpha.shape
    x0, y0 = int(max(0, fx)), int(max(0, fy))
    x1, y1 = int(min(W, fx + fw)), int(min(H, fy + fh))
    rgb = reg[..., :3]
    skin_m = np.zeros_like(solid)
    skin_m[y0:y1, x0:x1] = alpha[y0:y1, x0:x1] > 0.98
    ring = ndimage.binary_dilation(filled, iterations=12) & ~ndimage.binary_dilation(filled, iterations=3)   # sfondo vicino
    bx0, by0 = int(max(0, fx - 0.3 * fw)), int(max(0, fy - 0.3 * fh))
    bx1, by1 = int(min(W, fx + 1.3 * fw)), int(min(H, fy + 1.3 * fh))
    bg_m = np.zeros_like(solid)
    bg_m[by0:by1, bx0:bx1] = ring[by0:by1, bx0:bx1]
    skin = np.median(rgb[skin_m], axis=0) if skin_m.any() else None
    bg = np.median(rgb[bg_m], axis=0) if bg_m.any() else None
    cms = ndimage.center_of_mass(core, lab, range(1, k + 1))
    sizes = ndimage.sum(core, lab, range(1, k + 1))
    keep = np.zeros(k + 1, bool)
    for i, ((cy, cx), n) in enumerate(zip(cms, sizes), start=1):
        inside = (fx + 0.08 * fw <= cx <= fx + 0.92 * fw) and (fy + 0.12 * fh <= cy <= fy + 0.70 * fh)
        col = np.median(rgb[lab == i], axis=0)
        looks_skin = skin is None or bg is None or np.linalg.norm(col - skin) < np.linalg.norm(col - bg)
        if inside and n <= 0.08 * fw * fh and looks_skin:
            keep[i] = True
        else:
            info["skipped"] += 1
    m = keep[lab]
    if not m.any():
        return alpha, F, info
    grow = ndimage.binary_dilation(m, iterations=2) & filled & (alpha < 0.9)   # il bordo morbido della lente
    m = m | grow
    a2, F2 = alpha.copy(), F.copy()
    a2[m] = 1.0
    F2[m] = np.clip(rgb[m], 0, 1)
    info.update({"components": int(keep.sum()), "px": int(m.sum())})
    return a2, F2, info


def edge_metrics(F: np.ndarray, a: np.ndarray, fb: list[float] | None) -> dict:
    """fringe_rb: (R−B) della banda 0.1<α<0.9 meno quello dell'interno (×255, >0 = frangia calda);
    rim_luma: luma aggiunta dall'anello esterno 0.02<α<0.5 rispetto all'interno (×255, >0 = alone chiaro).
    Sulla fascia dei capelli/testa se c'è il volto, altrimenti su tutto il bordo."""
    band = np.ones(a.shape, bool)
    if fb:
        fx, fy, fw, fh = fb
        band = np.zeros(a.shape, bool)
        band[int(max(0, fy - 1.0 * fh)):int(max(0, fy + 0.3 * fh)), int(max(0, fx - 0.4 * fw)):int(min(a.shape[1], fx + 1.4 * fw))] = True
    Fin, den = interior_colour(F, a, 8)
    mid = (a > 0.1) & (a < 0.9) & band & (den > 0.02)
    outer = (a > 0.02) & (a < 0.5) & band & (den > 0.02)
    if mid.sum() < 20 or outer.sum() < 20:
        return {"fringe_rb": None, "rim_luma": None, "edge_band_px": int(mid.sum())}
    rb, rbi = F[..., 0] - F[..., 2], Fin[..., 0] - Fin[..., 2]
    return {"fringe_rb": round(float((rb - rbi)[mid].mean() * 255), 2),
            "rim_luma": round(float(luma((F - Fin) * a[..., None])[outer].mean() * 255), 2),
            "edge_band_px": int(mid.sum())}


# ── Ricampionamento ─────────────────────────────────────────────────────────
def zscale_resize(arr: np.ndarray, W2: int, H2: int, tmp: Path, tag: str) -> np.ndarray:
    rgb = arr if arr.ndim == 3 else np.repeat(arr[..., None], 3, 2)
    i, o = tmp / f"_{tag}_in.png", tmp / f"_{tag}_out.png"
    save16(rgb, i)
    subprocess.run([yc.FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(i), "-vf",
                    f"format=gbrp16le,zscale=w={W2}:h={H2}:filter=spline36,format=rgb48le", "-pix_fmt", "rgb48be", str(o)], check=True)
    out = load16(o)
    i.unlink(missing_ok=True)
    o.unlink(missing_ok=True)
    return out if arr.ndim == 3 else out[..., 0]


def luma_usm(rgb: np.ndarray, sigma: float = 0.7, amount: float = 0.6, thresh: float = 1 / 255) -> np.ndarray:
    Y = luma(rgb)
    d = Y - ndimage.gaussian_filter(Y, sigma)
    d = np.where(np.abs(d) > thresh, d, 0.0)
    return np.clip(rgb + (amount * d)[..., None], 0, 1)


def effective_face_px(rgb: np.ndarray, fb: list[float]) -> dict:
    """Risoluzione effettiva del volto: luma del volto (box ×1.3) ridotta di s e riportata su (Lanczos);
    s* = s più piccolo con PSNR ≥ 40 dB → px effettivi = altezza volto × s*."""
    fx, fy, fw, fh = fb
    cx, cy = fx + fw / 2, fy + fh / 2
    x0, x1 = int(max(0, cx - fw * 0.65)), int(min(rgb.shape[1], cx + fw * 0.65))
    y0, y1 = int(max(0, cy - fh * 0.65)), int(min(rgb.shape[0], cy + fh * 0.65))
    g = luma(rgb[y0:y1, x0:x1]).astype(np.float32)
    if g.shape[0] < 24 or g.shape[1] < 24:
        return {"eff_face_px": None}
    F = Image.fromarray(g, "F")
    s_star = 1.0
    for s in (0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95):
        d = F.resize((max(8, round(g.shape[1] * s)), max(8, round(g.shape[0] * s))), Image.LANCZOS)
        u = np.asarray(d.resize((g.shape[1], g.shape[0]), Image.LANCZOS), np.float32)
        mse = float(np.mean((u[6:-6, 6:-6] - g[6:-6, 6:-6]) ** 2))
        if 10 * math.log10(1.0 / max(mse, 1e-12)) >= 40.0:
            s_star = s
            break
    lap = ndimage.laplace(g * 255.0)
    return {"eff_face_px": round(fh * s_star, 1), "eff_ratio": s_star, "face_lapvar": round(float(lap[4:-4, 4:-4].var()), 1)}


# ── Tetto al display e dettaglio servito (thumbnail v2, T2) ────────────────
def display_cap_limits(eff_face_px: float | None, face_px_source: float, mode: str = DEFAULT_DISPLAY_CAP,
                       max_upscale: float = MAX_UPSCALE, at_width: int = DISPLAY_W) -> dict:
    """Limite della misura del volto sul canvas 3840×2160.

    mode c|b (o un numero): volto a `at_width` px di larghezza ≤ factor × eff_face_px, cioè
    face_out_4k ≤ factor × eff × 3840 / at_width. mode legacy: face_out_4k ≤ max_upscale × box del sorgente.
    Senza risoluzione effettiva misurata si ripiega su legacy (più severo per i frame del master)."""
    if mode not in ("legacy",) and eff_face_px:
        factor = DISPLAY_CAPS.get(mode) if mode in DISPLAY_CAPS else float(mode)
        max_out = factor * float(eff_face_px) * OUT_W / at_width
        basis = f"≤ {factor}× la risoluzione effettiva ({eff_face_px:.0f} px) a {at_width} px di larghezza"
        used = mode
    else:
        factor = max_upscale
        max_out = max_upscale * face_px_source
        basis = f"≤ {max_upscale}× il box del volto nel sorgente ({face_px_source:.0f} px)"
        used = "legacy" if mode == "legacy" else "legacy (risoluzione effettiva non misurata)"
    return {"mode": used, "factor": factor, "at_width": at_width, "eff_face_px": eff_face_px,
            "face_px_source": round(face_px_source, 1), "max_face_out_px": round(max_out, 1),
            "max_scale": round(max_out / max(face_px_source, 1e-6), 4), "max_face_frac": round(max_out / OUT_H, 4), "basis": basis}


def lap_var_u8(g: np.ndarray) -> float:
    """Varianza del Laplaciano 4-vicini su grigio 8 bit (stesso calcolo di scripts_critic/served.py)."""
    g = np.asarray(g, np.float64)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def served_status(lapvar: float) -> str:
    return "error" if lapvar < SERVED_ERR else ("warn" if lapvar < SERVED_WARN else "ok")


def served_face_detail(img, face_box_norm: list[float], width: int = SERVED_W) -> dict:
    """Dettaglio del volto nel file che YouTube serve (per yt-thumb-render / yt-thumb-qa): il render intero (PIL Image o
    percorso) ridotto a width×(width·9/16) con Lanczos, box del volto normalizzato (x,y,w,h, origine in alto), grigio
    ITU-R 601 (PIL «L»), varianza del Laplaciano. Avviso < 713, errore < 569 (p25 e p10 dei riferimenti EN)."""
    im = img if isinstance(img, Image.Image) else Image.open(img)
    im = im.convert("RGB")
    h2 = round(width * 9 / 16)
    im = im.resize((width, h2), Image.LANCZOS)
    x, y, w, h = face_box_norm
    c = im.crop((int(x * width), int(y * h2), int((x + w) * width), int((y + h) * h2))).convert("L")
    lv = lap_var_u8(np.asarray(c))
    return {"width": width, "face_px": c.height, "lapvar": round(lv, 1), "status": served_status(lv),
            "warn_below": SERVED_WARN, "error_below": SERVED_ERR}


def predict_served_detail(rgba8: np.ndarray, face_box_px: list[float], width: int = SERVED_W) -> dict:
    """Stima a monte del render: il ritaglio (già alla misura del canvas 3840×2160, disegnato 1:1) su grigio medio,
    ridotto del fattore width/3840 come il render intero, poi lo stesso calcolo di served_face_detail sul box del volto."""
    a = rgba8[..., 3:4].astype(np.float64) / 255.0
    comp = (rgba8[..., :3].astype(np.float64) * a + 128.0 * (1 - a)).clip(0, 255).astype(np.uint8)
    k = width / OUT_W
    im = Image.fromarray(comp).resize((max(1, round(comp.shape[1] * k)), max(1, round(comp.shape[0] * k))), Image.LANCZOS)
    x, y, w, h = [v * k for v in face_box_px]
    c = im.crop((int(x), int(y), int(x + w), int(y + h))).convert("L")
    lv = lap_var_u8(np.asarray(c))
    return {"width": width, "face_px": c.height, "lapvar": round(lv, 1), "status": served_status(lv),
            "warn_below": SERVED_WARN, "error_below": SERVED_ERR,
            "note": "stima sul ritaglio (grigio medio attorno); il controllo vero è sul render: portrait.served_face_detail"}


def served_limited_face_out(rgb: np.ndarray, fb: list[float], lo: float, hi: float, floor: float, tmp: Path,
                            alpha: np.ndarray | None = None, levels: tuple[float, float] = (0.1, 0.95), sharpen: bool = True,
                            iters: int = 7) -> tuple[float, list[dict]]:
    """La misura del volto più grande in [lo, hi] (px a 4K) con dettaglio servito stimato ≥ floor. Stessa catena del
    cut sulla sola zona del volto (resize premoltiplicato spline36 16 bit con il matte, nitidezza luma, livelli
    dell'alpha, grigio medio attorno, riduzione a 720): è la stima che il cut scrive nel sidecar, validata su ritagli reali
    (volto al 23,5 %: 1.216 stimato contro 1.211–1.233 misurati sui render ab1/ab3). Il dettaglio scende quando il
    volto cresce, quindi si cerca per bisezione. Ritorna (face_out, prove)."""
    fx, fy, fw, fh = fb
    x0, y0 = int(max(0, fx - 0.6 * fw)), int(max(0, fy - 0.6 * fh))
    x1, y1 = int(min(rgb.shape[1], fx + 1.6 * fw)), int(min(rgb.shape[0], fy + 1.6 * fh))
    reg, fbr = rgb[y0:y1, x0:x1], [fx - x0, fy - y0, fw, fh]
    a = alpha[y0:y1, x0:x1] if alpha is not None else None
    probes: list[dict] = []

    def served_at(face_out: float) -> float:
        s = face_out / fh
        W2, H2 = max(8, round(reg.shape[1] * s)), max(8, round(reg.shape[0] * s))
        if a is None:
            F2 = zscale_resize(reg, W2, H2, tmp, "srv")
            a3 = np.ones(F2.shape[:2])
        else:
            pre = zscale_resize(reg * a[..., None], W2, H2, tmp, "srv")
            a2 = np.clip(zscale_resize(a, W2, H2, tmp, "srva"), 0, 1)
            F2 = np.clip(np.where(a2[..., None] > 1e-4, pre / np.maximum(a2[..., None], 1e-4), 0), 0, 1)
            a3 = np.clip((a2 - levels[0]) / max(1e-6, levels[1] - levels[0]), 0, 1)
        if sharpen:
            F2 = luma_usm(F2)
        pr = predict_served_detail(to8(np.dstack([F2, a3])), [v * s for v in fbr])
        probes.append({"face_out_px": round(face_out, 1), "face_frac": round(face_out / OUT_H, 4), "lapvar": pr["lapvar"]})
        return pr["lapvar"]

    if served_at(hi) >= floor:
        return hi, probes
    if served_at(lo) < floor:
        return lo, probes
    lo_, hi_ = lo, hi
    for _ in range(iters):
        m = (lo_ + hi_) / 2
        if served_at(m) >= floor:
            lo_ = m
        else:
            hi_ = m
    return lo_, probes


def display_cap_check(portrait: dict | None, draw_scale: float = 1.0, override: str | None = None,
                      legacy_max: float = MAX_UPSCALE, tol: float = 0.02) -> dict:
    """Controllo del tetto per yt-thumb-render (chiave "portrait" del sidecar <png>.meta.json di yt-portrait cut).

    Ritorna {level: ok|warn|error, message, upscale_vs_source, limit_scale, display_upscale, mode}. Con un sidecar v2
    (display_cap) il limite è max_scale del sidecar (tetto al display); senza, il vecchio 2.0× sul box. Oltre il
    limite: error, oppure warn se c'è un motivo scritto (upscale_override del concept, deciso al G2)."""
    p = portrait or {}
    up = float(p.get("scale") or 1.0) * draw_scale
    dc = p.get("display_cap") or {}
    if dc.get("max_scale"):
        limit = float(dc["max_scale"])
        eff = dc.get("eff_face_px")
        face_out = float(p.get("face_out_px") or 0) * draw_scale
        disp = round(face_out * dc.get("at_width", DISPLAY_W) / OUT_W / eff, 3) if eff and face_out else None
        mode = dc.get("mode")
        rule = f"tetto {mode}: {dc.get('basis')}"
    else:
        limit, disp, mode = legacy_max, None, "legacy"
        rule = f"≤ {legacy_max}× il box del volto nel sorgente (07 §10.1)"
    out = {"upscale_vs_source": round(up, 3), "limit_scale": round(limit, 4), "display_upscale": disp, "mode": mode}
    if up <= limit + tol:
        return {**out, "level": "ok", "message": ""}
    msg = f"volto a {up:.2f}× della sorgente, oltre il limite {limit:.2f}× ({rule})"
    if override:
        return {**out, "level": "warn", "message": f"{msg} — motivo dichiarato: {override}"}
    return {**out, "level": "error", "message": f"{msg}: servono still/camera stretta o un volto più piccolo"}


# ── Matting ─────────────────────────────────────────────────────────────────
def matte_available() -> tuple[bool, str]:
    model = REMBG_HOME / "models" / "birefnet-portrait" / "birefnet-portrait.onnx"
    if not REMBG_PY.exists():
        return False, f"venv rembg assente ({REMBG_PY})"
    if not model.exists():
        return False, f"modello birefnet-portrait assente ({model})"
    return True, "birefnet-portrait"


def matte_birefnet(reg: np.ndarray, fb: list[float], exclude: list[list[float]], tmp: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    np.save(tmp / "region.npy", reg.astype(np.float32))
    job = {"region": str(tmp / "region.npy"), "face": fb, "exclude": exclude, "head_tile": True,
           "out_alpha": str(tmp / "alpha.npy"), "out_fg": str(tmp / "fg.npy")}
    (tmp / "job.json").write_text(json.dumps(job))
    env = {k: v for k, v in os.environ.items() if k not in ("U2NET_HOME", "MODEL_CHECKSUM_DISABLED", "PYTHONPATH")}
    env["REMBG_HOME"] = str(REMBG_HOME)
    proc = subprocess.run([str(REMBG_PY), "-I", str(WORKER), str(tmp / "job.json")], capture_output=True, text=True, env=env)
    try:
        res = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        res = {"ok": False, "error": (proc.stderr or proc.stdout)[-500:]}
    if not res.get("ok"):
        raise RuntimeError(f"matte birefnet: {res.get('error')}")
    return np.load(tmp / "alpha.npy").astype(np.float64), np.load(tmp / "fg.npy").astype(np.float64), res


def matte_vision(reg: np.ndarray, fb: list[float], exclude: list[list[float]], tmp: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """Ripiego Apple Vision: matte accurate, decontaminazione 4 px, senza choke (misurato: il choke 2 tagliava 2 px di capelli)."""
    H, W = reg.shape[:2]
    src = tmp / "region8.png"
    Image.fromarray(to8(reg)).save(src)
    out = tmp / "vision.png"
    px, py = (fb[0] + fb[2] / 2) / W, (fb[1] + fb[3] / 2) / H
    args = ["cutout", str(src), "--out", str(out), "--mode", "person", "--matte", "accurate", "--decontam", "4",
            "--point", f"{px:.4f},{py:.4f}"]
    if exclude:
        args += ["--exclude", ";".join(",".join(f"{v / (W if k % 2 == 0 else H):.4f}" for k, v in enumerate(e)) for e in exclude)]
    r = thumbvision(*args)
    if isinstance(r, dict) and r.get("ok") is False:
        raise RuntimeError(f"thumbvision cutout: {r.get('error')}")
    rgba = np.asarray(Image.open(out).convert("RGBA"), np.float64) / 255.0
    if rgba.shape[:2] != (H, W):
        raise RuntimeError("thumbvision cutout: dimensioni diverse dalla regione")
    return rgba[..., 3], rgba[..., :3], {"ok": True, "model": "apple-vision", "coverage": (r or {}).get("coverage")}


# ── cut ─────────────────────────────────────────────────────────────────────
def cut_one(args: argparse.Namespace, workdir: Path | None, src: Path | None, t: float | None, name: str, outdir: Path,
            layout: dict | None, warnings: list[str]) -> dict:
    T: dict[str, float] = {}
    tmp = Path(tempfile.mkdtemp(prefix="yt-portrait-", dir=str(outdir)))
    try:
        t0 = time.time()
        frame = tmp / "frame16.png"
        if args.image:
            img = Path(args.image).expanduser().resolve()
            subprocess.run([yc.FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(img), "-pix_fmt", "rgb48be", str(frame)], check=True)
            W, H = probe_stream(frame)["w"], probe_stream(frame)["h"]
            roi_name = "full" if args.roi in (None, "", "auto") else args.roi
            roi = roi_rect(roi_name, None, W, H)
            source = {"image": str(img), "kind": "still"}
        else:
            info = probe_stream(src)
            W, H = info["w"], info["h"]
            lay = None
            roi_name = args.roi
            if not roi_name or roi_name == "auto":
                lay = classify_at(src, t, layout)
                roi_name = "inset" if lay == "inset" else (f"wide-{args.seat}" if lay == "wide" else "full")
            roi = roi_rect(roi_name, layout, W, H, args.seat)
            kind = "camera" if getattr(args, "camera", False) else "master"
            source = {"video": str(src), "t": t, "layout": lay or roi_name.split("-")[0], "kind": kind}
            if kind == "camera":
                source["offset_s"] = float(args.offset or 0.0)
                source["t_master"] = round(t + float(args.offset or 0.0), 3)
        rx, ry, rw, rh = roi
        if args.image:
            full = load16(frame)
            reg_all = full[ry:ry + rh, rx:rx + rw]
            save16(reg_all, frame)
        else:
            extract16(src, t, frame, crop=roi)
        T["extract"] = time.time() - t0
        full = load16(frame)
        H2, W2 = full.shape[:2]
        point = None
        if args.point:
            px, py = [float(v) for v in args.point.split(",")]
            if px <= 1 and py <= 1:
                px, py = px * W, py * H
            point = (px - rx, py - ry)
        faces = faces_px(frame)
        f = pick_face(faces, W2, H2, point, seat_band=roi_name.startswith("wide"))
        fx, fy, fw, fh = f["box"]
        # regione del busto: inset/still → tutta la larghezza della ROI; campo largo → ±2.4 larghezze di volto
        wide_like = roi_name.startswith("wide") or roi_name == "full" and not args.image
        x0 = int(max(0, fx + fw / 2 - 2.4 * fw)) if wide_like else 0
        x1 = int(min(W2, fx + fw / 2 + 2.4 * fw)) if wide_like else W2
        y0 = int(max(0, fy - 1.5 * fh))
        body = args.body if args.body is not None else CROP_PRESETS[args.preset]
        y1 = int(min(H2, fy + fh + body * fh))
        reg = full[y0:y1, x0:x1]
        fb = [fx - x0, fy - y0, fw, fh]
        exclude = []
        if not args.image and rect_of(layout, "pip") and (roi_name.startswith("wide") or roi_name == "full"):
            px_, py_, pw_, ph_ = rect_of(layout, "pip")
            exclude.append([px_ - 12 - rx - x0, py_ - 12 - ry - y0, pw_ + 24, ph_ + 24])
        eff = effective_face_px(full, [fx, fy, fw, fh])
        cap = display_cap_limits(eff.get("eff_face_px"), fh, args.display_cap, args.max_upscale)
        if cap["mode"].startswith("legacy (") :
            warnings.append(f"{name}: risoluzione effettiva non misurabile: tetto legacy {args.max_upscale}× sul box")
        # misura di uscita
        served_search = None
        if args.face_px:
            face_out = float(args.face_px)
        elif args.upscale:
            face_out = float(args.upscale) * fh
        elif str(args.face_frac) == "max":
            face_out = min(cap["max_face_out_px"], FACE_FRAC_MAX * OUT_H, getattr(args, "face_max_px", None) or math.inf)
            served_search = {"floor": {"error": SERVED_ERR, "warn": SERVED_WARN}.get(args.served_floor)}  # dopo il matte
        else:
            face_out = float(args.face_frac) * OUT_H
        s = face_out / fh
        capped = False
        if face_out > cap["max_face_out_px"] + 0.5:
            if args.over_cap_reason:
                warnings.append(f"{name}: volto {face_out:.0f} px oltre il tetto {cap['max_face_out_px']:.0f} px "
                                f"({cap['basis']}; motivo dichiarato: {args.over_cap_reason})")
            else:
                face_out = cap["max_face_out_px"]
                s = face_out / fh
                capped = True
                warnings.append(f"{name}: volto limitato dal tetto {cap['mode']} ({cap['basis']}): sorgente {fh:.0f} px → "
                                f"{face_out:.0f} px = {face_out / OUT_H:.1%} di 2160; per un volto più grande servono still "
                                "o la camera stretta")
        t0 = time.time()
        backend = args.matte
        ok_bir, why = matte_available()
        if backend in ("auto", "birefnet") and ok_bir:
            try:
                alpha, F, mres = matte_birefnet(reg, fb, exclude, tmp)
                backend = "birefnet-portrait"
            except Exception as e:  # noqa: BLE001
                if args.matte == "birefnet":
                    raise
                warnings.append(f"{name}: BiRefNet non riuscito ({e}); ripiego Apple Vision")
                alpha, F, mres = matte_vision(reg, fb, exclude, tmp)
                backend = "apple-vision"
        else:
            if args.matte == "birefnet":
                raise RuntimeError(f"--matte birefnet non disponibile: {why}")
            if args.matte == "auto":
                warnings.append(f"{name}: {why} → ripiego Apple Vision (bordi dei capelli meno fedeli)")
            alpha, F, mres = matte_vision(reg, fb, exclude, tmp)
            backend = "apple-vision"
        T["matting"] = time.time() - t0
        holes_filled = None
        if not getattr(args, "keep_holes", False):
            alpha, F, holes_filled = fill_face_holes(alpha, F, reg, fb)
            if holes_filled["px"]:
                warnings.append(f"{name}: {holes_filled['px']} px di buchi del matte nella fascia degli occhi riempiti con il "
                                "sorgente (lente degli occhiali; α = 1, pixel reali)")
        t0 = time.time()
        before = edge_metrics(F, alpha, fb)
        F = halo_clamp(spill_clamp(F, alpha), alpha)
        after = edge_metrics(F, alpha, fb)
        T["decontam"] = time.time() - t0
        if served_search and served_search.get("floor"):
            # --face-frac max: il volto più grande entro il tetto con dettaglio servito stimato ≥ soglia (stessa catena del
            # ritaglio finale, matte compreso, sulla sola zona del volto)
            t0 = time.time()
            floor = served_search["floor"]
            lv = tuple(float(v) for v in args.alpha_levels.split(","))
            face_out, probes = served_limited_face_out(F, fb, min(face_out, 0.15 * OUT_H), face_out, floor, tmp, alpha=alpha,
                                                       levels=lv, sharpen=not args.no_sharpen)
            s = face_out / fh
            T["served_search"] = time.time() - t0
            if face_out < cap["max_face_out_px"] - 1:
                warnings.append(f"{name}: --face-frac max limitato dal dettaglio servito (stima ≥ {floor:.0f} a {SERVED_W} px): "
                                f"{face_out / OUT_H:.1%} invece di {cap['max_face_frac']:.1%} del tetto {cap['mode']}")
            served_search.update({"probes": probes, "chosen_face_frac": round(face_out / OUT_H, 4)})
        elif served_search is not None:
            served_search = None
        ys, xs = np.where(alpha > 0.01)
        if not len(xs):
            raise RuntimeError("matte vuoto")
        Hh, Ww = alpha.shape
        touches_region = {"left": bool(xs.min() <= 1), "right": bool(xs.max() >= Ww - 2),
                          "top": bool(ys.min() <= 1), "bottom": bool(ys.max() >= Hh - 2)}
        # quali lati toccano un bordo "vero" della sorgente (ROI/inset/frame) e quali solo la regione del busto
        cause = {"left": "roi" if x0 == 0 else "regione", "right": "roi" if x1 == W2 else "regione",
                 "top": "roi" if y0 == 0 else "regione", "bottom": "roi" if y1 == H2 else "regione"}
        cy0, cy1 = max(0, ys.min() - 8), min(Hh, ys.max() + 9)
        cx0, cx1 = max(0, xs.min() - 8), min(Ww, xs.max() + 9)
        F, alpha, reg_c = F[cy0:cy1, cx0:cx1], alpha[cy0:cy1, cx0:cx1], reg[cy0:cy1, cx0:cx1]
        fbc = [fb[0] - cx0, fb[1] - cy0, fw, fh]
        t0 = time.time()
        Wo, Ho = int(round(F.shape[1] * s)), int(round(F.shape[0] * s))
        pre = zscale_resize(F * alpha[..., None], Wo, Ho, tmp, "rgb")
        a2 = np.clip(zscale_resize(alpha, Wo, Ho, tmp, "a"), 0, 1)
        F2 = np.clip(np.where(a2[..., None] > 1e-4, pre / np.maximum(a2[..., None], 1e-4), 0), 0, 1)
        if not args.no_sharpen:
            F2 = luma_usm(F2)
        lo, hi = [float(v) for v in args.alpha_levels.split(",")]
        a3 = np.clip((a2 - lo) / max(1e-6, hi - lo), 0, 1)
        T["resize_sharpen"] = time.time() - t0
        rgba = np.dstack([F2, a3])
        outdir.mkdir(parents=True, exist_ok=True)
        png, png16, meta_p = outdir / f"{name}.png", outdir / f"{name}_16.png", outdir / f"{name}.json"
        save16(rgba, png16)
        Image.fromarray(to8(rgba), "RGBA").save(png, optimize=True)
        fbo = [round(v * s, 1) for v in fbc]
        # prova di conservazione: volto della sorgente ricampionato (spline36 puro) vs ritaglio, stessa scala
        proof = preservation_proof(reg_c, alpha, fbc, s, F2, a3, tmp, outdir / f"{name}_proof.jpg", name)
        straight = {k: v for k, v in touches_region.items() if v}
        served = predict_served_detail(to8(rgba), fbo)
        eff_px = eff.get("eff_face_px")
        dcap = {**cap, "face_out_px": round(face_out, 1), "face_at_display_px": round(face_out * DISPLAY_W / OUT_W, 1),
                "display_upscale": round(face_out * DISPLAY_W / OUT_W / eff_px, 3) if eff_px else None,
                "served_upscale": round(face_out * SERVED_W / OUT_W / eff_px, 3) if eff_px else None,
                "within_cap": bool(face_out <= cap["max_face_out_px"] + 0.5), "capped": capped,
                "over_cap_reason": args.over_cap_reason if face_out > cap["max_face_out_px"] + 0.5 else None}
        if served["status"] != "ok":
            lim = f"errore < {SERVED_ERR:.0f}" if served["status"] == "error" else f"avviso < {SERVED_WARN:.0f}"
            warnings.append(f"{name}: dettaglio del volto al formato servito ({SERVED_W} px) {served['lapvar']:.0f}, stima "
                            f"({lim}): volto più piccolo, --display-cap b, oppure still o camera stretta")
        meta = {
            "portrait_version": PORTRAIT_VERSION, "tool": "yt-portrait cut", "name": name,
            "source": source, "roi": roi_name, "roi_px": roi, "region_px": [x0 + rx, y0 + ry, x1 - x0, y1 - y0],
            "matte": backend, "matte_info": {k: v for k, v in mres.items() if k != "ok"}, "matte_holes_filled": holes_filled,
            "face_px_source": round(fh, 1), "face_box_source_px": [round(fx + rx, 1), round(fy + ry, 1), round(fw, 1), round(fh, 1)],
            "yaw": f.get("yaw"), "pitch": f.get("pitch"),
            "scale": round(s, 4), "upscale": round(s, 4), "max_upscale": cap["max_scale"], "capped": capped,
            "display_cap": dcap, "served_detail": served, "served_search": served_search, "preset": args.preset if args.body is None else f"body {body}",
            "face_out_px": round(face_out, 1), "face_frac_at_2160": round(face_out / OUT_H, 4),
            "face_box_out_px": fbo, "face_box_norm": [round(fbo[0] / Wo, 5), round(fbo[1] / Ho, 5), round(fbo[2] / Wo, 5), round(fbo[3] / Ho, 5)],
            "out_px": [Wo, Ho], "draw": "1:1 a DPR 3 (larghezza CSS = out_px[0]/3)",
            "eff_face_px": eff.get("eff_face_px"), "eff_ratio": eff.get("eff_ratio"), "face_lapvar_source": eff.get("face_lapvar"),
            "eff_upscale": round(face_out / eff["eff_face_px"], 2) if eff.get("eff_face_px") else None,
            "straight_edges": straight, "straight_edge_cause": {k: cause[k] for k in straight},
            "rule_crop_edges": "07 §11: ogni bordo dritto deve stare a filo del bordo del canvas (o oltre)",
            "edge_before": before, "edge_after": after, "proof": proof,
            "steps": ["extract16 zscale bt709", "thumbvision faces", backend, "pymatting ML" if backend == "birefnet-portrait" else "vision decontam 4",
                      "eye-band holes ← source (α 1)" if (holes_filled or {}).get("px") else "no eye-band holes",
                      "spill clamp", "halo clamp ±6/255", "spline36 16 bit premoltiplicato", "luma USM σ0.7 ×0.6" if not args.no_sharpen else "no sharpen",
                      f"alpha levels {args.alpha_levels}"],
            "timings_s": {k: round(v, 2) for k, v in T.items()},
        }
        if cap["mode"] == "legacy" and meta["eff_upscale"] and meta["eff_upscale"] > EFF_UPSCALE_WARN:
            warnings.append(f"{name}: ingrandimento sulla risoluzione effettiva {meta['eff_upscale']}× (> {EFF_UPSCALE_WARN}×): volto morbido")
        if f.get("yaw") is not None and abs(f["yaw"]) > 35:
            warnings.append(f"{name}: volto di profilo (yaw {f['yaw']:.0f}°): a 168 px non si legge lo sguardo")
        yc.write_json(meta_p, meta)
        # sidecar compatibile con yt-thumb-render (evita il ricalcolo e usa il volto esatto del ritaglio)
        write_render_meta(png, rgba[..., 3], meta)
        if args.keep_frame:
            shutil.copy(frame, outdir / f"{name}_frame16.png")
        return {"name": name, "png": str(png), "png16": str(png16), "json": str(meta_p), "proof": proof.get("jpg"),
                "matte": backend, "upscale": meta["upscale"], "face_out_px": meta["face_out_px"],
                "face_frac": meta["face_frac_at_2160"], "eff_upscale": meta["eff_upscale"], "straight_edges": straight,
                "eff_face_px": eff_px, "display_cap": {k: dcap[k] for k in ("mode", "max_face_frac", "display_upscale", "within_cap")},
                "served_lapvar": served["lapvar"], "served_status": served["status"],
                "fringe_rb": after.get("fringe_rb"), "rim_luma": after.get("rim_luma"), "seconds": round(sum(T.values()), 1)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def preservation_proof(F: np.ndarray, a: np.ndarray, fb: list[float], s: float, F2: np.ndarray, a2: np.ndarray,
                       tmp: Path, out: Path, name: str) -> dict:
    """07 §11: frame originale (F = pixel della sorgente, prima di matte e colore) ricampionato con spline36 puro vs
    ritaglio finale, confrontati solo sui pixel opachi del volto."""
    fx, fy, fw, fh = fb
    x0, x1 = int(max(0, fx - 0.3 * fw)), int(min(F.shape[1], fx + 1.3 * fw))
    y0, y1 = int(max(0, fy - 0.4 * fh)), int(min(F.shape[0], fy + 1.2 * fh))
    ref_src = F[y0:y1, x0:x1] * a[y0:y1, x0:x1, None]
    X0, X1, Y0, Y1 = int(round(x0 * s)), int(round(x1 * s)), int(round(y0 * s)), int(round(y1 * s))
    Wc, Hc = X1 - X0, Y1 - Y0
    if Wc < 16 or Hc < 16:
        return {}
    ref = zscale_resize(ref_src, Wc, Hc, tmp, "proof")
    cut = F2[Y0:Y1, X0:X1] * a2[Y0:Y1, X0:X1, None]
    h, w = min(ref.shape[0], cut.shape[0]), min(ref.shape[1], cut.shape[1])
    ref, cut = ref[:h, :w], cut[:h, :w]
    aa = a2[Y0:Y0 + h, X0:X0 + w]
    face = np.zeros((h, w), bool)
    face[int((fy - y0) * s):int((fy - y0 + fh) * s), int((fx - x0) * s):int((fx - x0 + fw) * s)] = True
    m = face & (aa > 0.99)
    d = np.abs(cut - ref).max(axis=2)[m] * 255 if m.any() else np.array([0.0])
    k = 600 / max(h, 1)
    pair = Image.new("RGB", (int(w * k) * 2 + 12, int(h * k)), (40, 40, 40))
    pair.paste(Image.fromarray(to8(ref)).resize((int(w * k), int(h * k)), Image.LANCZOS), (0, 0))
    pair.paste(Image.fromarray(to8(cut)).resize((int(w * k), int(h * k)), Image.LANCZOS), (int(w * k) + 12, 0))
    dr = ImageDraw.Draw(pair)
    dr.text((8, 8), f"{name}: sorgente spline36 | ritaglio finale · diff media {d.mean():.2f} p99 {np.percentile(d, 99):.1f} livelli",
            fill=(255, 255, 255), font=font(15))
    pair.save(out, quality=90)
    return {"jpg": str(out), "face_diff_mean": round(float(d.mean()), 2), "face_diff_p99": round(float(np.percentile(d, 99)), 2),
            "note": "riferimento = frame originale ricampionato spline36; differenze attese solo dalla nitidezza luma (USM)"}


def write_render_meta(png: Path, alpha: np.ndarray, meta: dict) -> None:
    """<png>.meta.json nel formato di yt-thumb-render.cutout_meta (sagoma a 64 fasce + volto esatto)."""
    a = alpha > 0.5
    h, w = a.shape
    ys, xs = np.where(a)
    bands = 64
    left, right = [], []
    for i in range(bands):
        rows = a[int(i * h / bands): max(int((i + 1) * h / bands), int(i * h / bands) + 1)]
        cols = np.where(rows.any(axis=0))[0]
        left.append(round(float(cols.min()) / w, 4) if len(cols) else -1)
        right.append(round(float(cols.max() + 1) / w, 4) if len(cols) else -1)
    touches = {"left": bool(a[:, :2].any()), "right": bool(a[:, -2:].any()), "top": bool(a[:2].any()), "bottom": bool(a[-2:].any())}
    yc.write_json(png.with_suffix(".meta.json"), {
        "w": w, "h": h, "alpha_box": [round(xs.min() / w, 4), round(ys.min() / h, 4), round((xs.max() - xs.min() + 1) / w, 4),
                                      round((ys.max() - ys.min() + 1) / h, 4)],
        "profile": {"left": left, "right": right}, "touches": touches, "face": meta["face_box_norm"], "face_detected": True,
        "portrait": {k: meta[k] for k in ("scale", "face_out_px", "face_px_source", "eff_face_px", "eff_upscale", "matte",
                                          "straight_edges", "source", "max_upscale", "display_cap", "served_detail")
                     if k in meta}})


def contact_sheet(items: list[dict], out: Path) -> None:
    tiles = []
    for it in items:
        im = Image.open(it["png"]).convert("RGBA")
        k = 520 / im.height
        im = im.resize((max(1, int(im.width * k)), 520), Image.LANCZOS)
        for bg in ((0x15, 0x17, 0x1c), (0xf4, 0xf1, 0xea)):
            t = Image.new("RGB", im.size, bg)
            t.paste(im, mask=im.getchannel("A"))
            d = ImageDraw.Draw(t)
            d.rectangle([0, 0, t.width, 22], fill=(0, 0, 0))
            d.text((4, 3), f"{it['name']} ×{it['upscale']} {it['matte']} edges:{','.join(it['straight_edges']) or '-'}",
                   fill=(255, 255, 255), font=font(13))
            tiles.append(t)
    if not tiles:
        return
    W = sum(t.width for t in tiles) + 8 * (len(tiles) - 1)
    sheet = Image.new("RGB", (W, 520), (40, 40, 40))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 8
    sheet.save(out, quality=88)


def cmd_cut(args: argparse.Namespace) -> None:
    t_start = time.time()
    warnings: list[str] = []
    workdir = yc.resolve_workdir(args.workdir) if args.workdir and args.workdir != "-" else None
    if not workdir and not args.image:
        yc.fail("serve WORKDIR (per il master) oppure --image STILL")
    channel = (yc.load_project(workdir).get("channel") if workdir else None) or args.channel or default_channel()
    layout = None if args.camera else brand_layout(channel)   # camera separata: nessuna geometria del master composito
    if args.camera and not args.src:
        yc.fail("--camera richiede --src FILE (il file della camera stretta)")
    src = None
    if not args.image:
        src = Path(args.src).expanduser() if args.src else yc.source_path(workdir)
        if not src.exists():
            yc.fail(f"sorgente non trovato: {src}")
    if not workdir and not args.out:
        yc.fail("con --image senza WORKDIR serve --out DIR (dove scrivere il ritaglio)")
    outdir = Path(args.out).expanduser().resolve() if args.out else (workdir / "thumbs" / "portrait")
    outdir.mkdir(parents=True, exist_ok=True)
    times = [None] if args.image else [yc.parse_ts(x) for x in str(args.t).split(",") if x.strip()]
    if not times:
        yc.fail("--t: nessun tempo")
    results = []
    for i, t in enumerate(times):
        name = args.name if (args.name and len(times) == 1) else (f"{args.name}_{i + 1:02d}" if args.name else
                                                                  (f"p_{t:09.3f}".replace(".", "_") if t is not None else Path(args.image).stem))
        png = outdir / f"{name}.png"
        if png.exists() and not args.force and (outdir / f"{name}.json").exists():
            prev = yc.read_json(outdir / f"{name}.json")
            results.append({"name": name, "png": str(png), "json": str(outdir / f"{name}.json"), "skipped": True,
                            "upscale": prev.get("upscale"), "matte": prev.get("matte"), "straight_edges": prev.get("straight_edges", {})})
            continue
        yc.log(f"[cut] {name} t={t}")
        results.append(cut_one(args, workdir, src, t, name, outdir, layout, warnings))
    if len(results) > 1 or args.sheet:
        sheet = outdir / (f"{args.name or 'portrait'}_sheet.jpg")
        contact_sheet(results, sheet)
    else:
        sheet = None
    yc.emit(True, outputs={"cutouts": results, "dir": str(outdir), "sheet": str(sheet) if sheet else None},
            warnings=warnings, seconds=round(time.time() - t_start, 1))


# ── scan ────────────────────────────────────────────────────────────────────
def proxy_layout(workdir: Path, src: Path, layout: dict | None, t0: float, t1: float, fps: float = 2.0) -> list[tuple[float, str]]:
    """Layout a 2 campioni/s dal proxy 720p (o dal master se manca), con le sonde di layout.json."""
    if not layout or not layout.get("probes"):
        return []
    import clips  # noqa: WPS433
    proxy = workdir / "analysis" / "proxy.mp4"
    vid = proxy if proxy.exists() else src
    w, h = clips.SMALL
    cmd = [yc.FFMPEG, "-nostdin", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(vid),
           "-vf", f"fps={fps}:round=up,scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    out, k, fb = [], 0, w * h * 3
    while True:
        buf = proc.stdout.read(fb)
        if not buf or len(buf) < fb:
            break
        lab = clips.classify_frame(np.frombuffer(buf, np.uint8).reshape(h, w, 3), layout)[0]
        out.append((round(t0 + k / fps, 3), lab))
        k += 1
    proc.wait()
    return out


def corrupt_spans(workdir: Path) -> list[tuple[float, float]]:
    inv = workdir / "analysis" / "inventory.json"
    if not inv.exists():
        return []
    d = yc.read_json(inv)
    spans = d.get("corrupt_spans") or (d.get("integrity") or {}).get("corrupt_spans") or []
    return [(s["start"] - 2.0, s["end"] + 2.0) for s in spans]


def pct(vals) -> np.ndarray:
    v = np.asarray(vals, float)
    if len(v) < 2:
        return np.ones(len(v))
    return v.argsort().argsort() / (len(v) - 1)


def audio_envelope(path: Path, start: float = 0.0, dur: float | None = None, rate: int = 100) -> np.ndarray:
    """Inviluppo degli attacchi (derivata positiva dell'energia logaritmica) a `rate` Hz, audio mono 8 kHz."""
    sr = 8000
    cmd = [yc.FFMPEG, "-nostdin", "-v", "error", "-ss", f"{max(0.0, start):.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)
    hop = sr // rate
    n = len(x) // hop
    if n < rate:
        return np.zeros(0)
    e = np.log(1e-7 + (x[:n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(1))
    d = np.maximum(0.0, np.diff(e, prepend=e[0]))
    return (d - d.mean()) / (d.std() + 1e-9)


def audio_offset(cam: Path, master_env: np.ndarray, cam_dur: float, rate: int = 100, win: float = 240.0) -> dict:
    """offset tale che tempo master = tempo camera + offset: correlazione incrociata (FFT) degli inviluppi su due finestre
    della camera (a ~10 % e ~55 %). Le due stime devono coincidere entro 0,1 s: altrimenti il master è montato (tagli)
    e un offset unico non vale per tutto l'episodio."""
    est = []
    win = min(win, max(20.0, cam_dur * 0.4))      # file corti: due finestre diverse anche su 2 minuti
    for frac in (0.1, 0.55):
        w0 = max(0.0, min(cam_dur - win, cam_dur * frac))
        ce = audio_envelope(cam, w0, min(win, cam_dur), rate)
        if len(ce) < rate * 10 or len(master_env) < len(ce):
            continue
        n = 1 << int(math.ceil(math.log2(len(master_env) + len(ce))))
        corr = np.fft.irfft(np.fft.rfft(master_env, n) * np.conj(np.fft.rfft(ce, n)), n)[:len(master_env) - len(ce) + 1]
        corr /= len(ce)
        k = int(np.argmax(corr))
        peak = float(corr[k])
        mask = np.ones(len(corr), bool)
        mask[max(0, k - rate):k + rate] = False
        second = float(corr[mask].max()) if mask.any() else 0.0
        est.append({"cam_window_s": [round(w0, 1), round(w0 + len(ce) / rate, 1)], "offset_s": round(k / rate - w0, 2),
                    "peak": round(peak, 3), "peak_ratio": round(peak / max(second, 1e-6), 2)})
    if not est:
        return {"ok": False, "method": "audio", "reason": "audio troppo corto o assente", "windows": est}
    best = max(est, key=lambda e: e["peak_ratio"])
    ok = best["peak_ratio"] >= 1.5 and best["peak"] >= 0.15
    consistent = len(est) < 2 or abs(est[0]["offset_s"] - est[1]["offset_s"]) <= 0.1
    return {"ok": bool(ok), "method": "audio (inviluppi, correlazione FFT)", "offset_s": best["offset_s"], "windows": est,
            "consistent": consistent,
            "reason": "" if ok else "picco di correlazione debole: passa --offset a mano"}


def crop_box_px(r: dict, img_w: int, img_h: int) -> list[float]:
    x, y, w, h = r["face"]["box"]
    return [x * img_w, y * img_h, w * img_w, h * img_h]


def dedupe(rows: list[dict], n: int, gap: float = 3.0) -> list[dict]:
    picked, used = [], []
    for r in rows:
        if any(abs(r["t"] - u) < gap for u in used):
            continue
        picked.append(r)
        used.append(r["t"])
        if len(picked) >= n:
            break
    return picked


def cmd_scan(args: argparse.Namespace) -> None:
    import expressions as ex  # noqa: PLC0415
    t_start = time.time()
    T: dict[str, float] = {}
    warnings: list[str] = []
    workdir = yc.resolve_workdir(args.workdir) if args.workdir not in (None, "-") else None
    project = yc.load_project(workdir) if workdir else {}
    channel = project.get("channel") or default_channel()
    if args.src and args.layout == "full" and not args.source:     # --src FILE --layout full = camera separata
        args.source, args.src = args.src, None
    camera = bool(args.source)
    if camera:
        src = Path(args.source).expanduser().resolve()
    elif args.src:
        src = Path(args.src).expanduser()
    elif workdir:
        src = yc.source_path(workdir)
    else:
        yc.fail("serve WORKDIR (master del progetto) oppure --source FILE (camera stretta)")
    if not src.exists():
        yc.fail(f"sorgente non trovato: {src}")
    mode = args.layout
    if camera and mode == "auto":
        mode = "full"
    if args.seat == "all" and mode not in ("auto", "wide"):
        yc.fail("--seat all vale solo per il campo largo del composito (--layout wide|auto)")
    layout = None if mode == "full" else brand_layout(channel)
    if mode == "auto" and not is_composite(layout):
        mode, layout = "full", None                 # una sola camera: tutto il fotogramma (nessun layout composito misurato)
    info = probe_stream(src)
    W, H, fps = info["w"], info["h"], info["fps"]
    if camera or args.src:
        dur = float(yc.media_duration(src))
    else:
        dur = float(project.get("sources", {}).get(project.get("main_source", "A"), {}).get("duration") or yc.media_duration(src))
    t0 = yc.parse_ts(args.from_) if args.from_ else 0.0
    t1 = min(dur, yc.parse_ts(args.to)) if args.to else dur
    if args.out:
        outdir = Path(args.out).expanduser().resolve()
    elif workdir:
        outdir = workdir / "thumbs" / "portrait" / (f"cam_{src.stem}" if camera else "")
    else:
        yc.fail("senza WORKDIR serve --out")
    # 0. offset camera → master (tempi della trascrizione)
    offset, sync = 0.0, None
    if camera:
        if args.offset is not None:
            offset, sync = float(args.offset), {"ok": True, "method": "manuale (--offset)", "offset_s": float(args.offset)}
        elif args.sync == "auto" and workdir:
            t_a = time.time()
            master = yc.source_path(workdir)
            a16 = workdir / "analysis" / "audio16k.wav"
            menv = audio_envelope(a16 if a16.exists() else master)
            sync = audio_offset(src, menv, dur)
            T["sync"] = time.time() - t_a
            if sync["ok"]:
                offset = sync["offset_s"]
                if not sync["consistent"]:
                    warnings.append(f"offset camera→master diverso tra le due finestre ({[w['offset_s'] for w in sync['windows']]} s): "
                                    "master montato? I tempi della trascrizione valgono solo vicino a quella finestra")
            else:
                warnings.append(f"sincronizzazione audio non riuscita ({sync['reason']}): niente tempi delle parole; usa --offset")
        else:
            sync = {"ok": False, "method": "nessuna", "reason": "--sync none o nessun WORKDIR"}
    raw = outdir / "scan_raw"
    # 1. ritagli da decodificare
    crops: dict[str, dict] = {}
    if mode == "full":
        k = min(1.0, args.scan_height / H) if args.scan_height else 1.0
        ow, oh = int(round(W * k / 2)) * 2, int(round(H * k / 2)) * 2
        crops["full"] = {"rect": [0, 0, W, H], "out": [ow, oh], "layout": "full", "role": "guest", "seat": None}
    else:
        ins = roi_rect("inset", layout, W, H) if layout and rect_of(layout, "inset") else None
        if mode in ("auto", "inset") and ins:
            crops["ins"] = {"rect": [ins[0], ins[1], ins[2], min(ins[3], 1304)], "layout": "inset", "role": "guest", "seat": None}
        if mode in ("auto", "wide"):
            seats = list(SEATS) if args.seat == "all" else [args.seat]
            for st in seats:
                wr = roi_rect(f"wide-{st}", layout, W, H)
                key = "wid" if len(seats) == 1 else f"wid-{st}"
                role = "guest" if (len(seats) == 1 or st == args.guest_seat) else "host"
                crops[key] = {"rect": [wr[0], wr[1], wr[2], min(wr[3], 1304)], "layout": "wide", "role": role, "seat": st}
        for c in crops.values():                       # testa e busto: i 1304 px alti bastano
            c["out"] = list(c["rect"][2:])
    if not crops:
        yc.fail("nessuna ROI da scansionare (layout.json senza inset?)")
    for key in crops:
        (raw / key).mkdir(parents=True, exist_ok=True)
    # 2. layout per campione (solo master composito)
    t_a = time.time()
    labels = proxy_layout(workdir, src, layout, t0, t1) if (workdir and not camera and mode != "full") else []
    lab_at = {round(t * 2) / 2: l for t, l in labels}
    T["layout"] = time.time() - t_a
    yc.log(f"[scan] layout: {len(labels)} campioni in {T['layout']:.0f}s")

    def layout_at(t: float) -> str | None:
        if mode == "full":
            return "full"
        if not labels:
            return "inset" if "ins" in crops else "wide"
        k2 = round(t * 2) / 2
        win = [w for w in (lab_at.get(k2 + d / 2) for d in range(-2, 3)) if w]
        return win[0] if win and len(set(win)) == 1 else None

    # 3. una passata di decodifica: coppie (n, n+1) ogni K frame
    K = max(2, int(round(args.every * fps)))
    keys = list(crops)

    def graph(hw: bool) -> tuple[str, list[str]]:
        head = f"[0:v]select='lt(mod(n\\,{K})\\,2)'"
        if hw:
            head += f",hwdownload,format={'p010le' if '10' in info['pix_fmt'] else 'nv12'}"
        head += ",showinfo=checksum=0"
        fc = head + (f",split={len(keys)}" + "".join(f"[s{i}]" for i in range(len(keys))) if len(keys) > 1 else "[s0]") + ";"
        maps: list[str] = []
        for i, key in enumerate(keys):
            x, y, w, h = crops[key]["rect"]
            ow, oh = crops[key]["out"]
            chain = f"crop={w}:{h}:{x}:{y}" + (f",scale={ow}:{oh}:flags=lanczos" if (ow, oh) != (w, h) else "")
            fc += f"[s{i}]{chain}[c{i}];"
            maps += ["-map", f"[c{i}]", "-fps_mode", "passthrough", "-q:v", "2", str(raw / key / "f_%06d.jpg")]
        return fc.rstrip(";"), maps

    t_a = time.time()
    if not args.reuse_raw or not all(any((raw / key).glob("f_*.jpg")) for key in keys) or not (raw / "pts.json").exists():
        for key in keys:
            for p in (raw / key).glob("f_*.jpg"):
                p.unlink()
        proc = None
        for hw in (True, False):
            fc, maps = graph(hw)
            cmd = [yc.FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "info", "-y"]
            if hw:
                cmd += ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
            cmd += ["-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-copyts", "-i", str(src), "-filter_complex", fc, *maps]
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if proc.returncode == 0:
                break
            yc.log(f"[scan] decodifica {'VideoToolbox' if hw else 'software'} non riuscita" + (": riprovo in software" if hw else ""))
        if proc is None or proc.returncode != 0:
            yc.fail("decodifica del sorgente fallita", stderr=(proc.stderr if proc else "")[-1500:])
        pts = [float(m.group(1)) for m in re.finditer(r"\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.]+)", proc.stderr)]
        yc.write_json(raw / "pts.json", {"pts_time": pts})
    pts = yc.read_json(raw / "pts.json")["pts_time"]
    T["decode"] = time.time() - t_a
    yc.log(f"[scan] {len(pts)} frame decodificati in {T['decode']:.0f}s ({len(keys)} ritagli)")
    # 4. coppie, layout, span corrotti
    bad = corrupt_spans(workdir) if (workdir and not camera and not args.src) else []
    pairs, k = [], 0
    while k < len(pts) - 1:
        if abs(pts[k + 1] - pts[k] - 1 / fps) < 0.006:
            pairs.append((k, k + 1))
            k += 2
        else:
            k += 1
    meta: dict[str, dict] = {}
    todo: dict[str, list[str]] = {key: [] for key in crops}
    for a, b in pairs:
        t = pts[a]
        if any(lo <= t <= hi for lo, hi in bad):
            continue
        lay = layout_at(t)
        for key, c in crops.items():
            if c["layout"] != lay:
                continue
            fa, fb_ = raw / key / f"f_{a + 1:06d}.jpg", raw / key / f"f_{b + 1:06d}.jpg"
            if fa.exists() and fb_.exists():
                todo[key].append(str(fa))
                meta[str(fa)] = {"t": round(t, 3), "layout": key, "next": str(fb_)}
    # 5. thumbvision score (1.1+: geometria dell'espressione)
    t_a = time.time()
    scores: dict[str, dict] = {}
    for key, files in todo.items():
        if not files:
            continue
        cache = raw / f"scores2_{key}.json"
        if args.reuse_raw and cache.exists():
            data = yc.read_json(cache)
            if len(data) == len(files):
                for r in data:
                    scores[r["file"]] = r
                continue
        lst = outdir / f"scan_list_{key}.txt"
        lst.write_text("\n".join(files) + "\n")
        proc = subprocess.run([str(yc.SWIFT_BIN), "score", "--list", str(lst), "--no-aesthetics"], capture_output=True, text=True)
        if proc.returncode != 0:
            yc.fail("thumbvision score fallito", stderr=(proc.stdout + proc.stderr)[-1500:])
        data = json.loads(proc.stdout)
        yc.write_json(cache, data)
        for r in data:
            scores[r["file"]] = r
        lst.unlink(missing_ok=True)
    T["thumbvision"] = time.time() - t_a
    yc.log(f"[scan] thumbvision su {len(scores)} frame in {T['thumbvision']:.0f}s")
    no_geom = sum(1 for r in scores.values() for f in (r.get("faces") or []) if "geom" not in f)
    if scores and no_geom == sum(len(r.get("faces") or []) for r in scores.values()):
        warnings.append(f"thumbvision {yc.SWIFT_BIN} senza geometria dell'espressione (serve 1.1+: rilancia /youtube:setup)")
    # 6. metriche per campione
    point = [float(v) for v in args.point.split(",")] if args.point else None
    recs = []
    for fpath, m in meta.items():
        r = scores.get(fpath)
        if not r:
            continue
        c = crops[m["layout"]]
        cx, cy, cw, ch = c["rect"]
        cand = [f for f in (r.get("faces") or []) if c["layout"] != "wide" or 0.2 < f["box"][0] + f["box"][2] / 2 < 0.8]
        if not cand:
            continue
        if point and c["layout"] == "full":
            px, py = (point[0], point[1]) if all(v <= 1 for v in point) else (point[0] / W, point[1] / H)
            f = min(cand, key=lambda f: math.hypot(f["box"][0] + f["box"][2] / 2 - px, f["box"][1] + f["box"][3] / 2 - py))
        else:
            f = max(cand, key=lambda f: f.get("face_px") or 0)
        x, y, w, h = f["box"]
        ga = np.asarray(Image.open(fpath).convert("L"), np.float32)
        gb = np.asarray(Image.open(m["next"]).convert("L"), np.float32)
        Hh, Ww = ga.shape
        gx0, gx1 = int(max(0, (x - 0.15 * w) * Ww)), int(min(Ww, (x + 1.15 * w) * Ww))
        gy0, gy1 = int(max(0, (y - 0.15 * h) * Hh)), int(min(Hh, (y + 1.15 * h) * Hh))
        pa, pb = ga[gy0:gy1, gx0:gx1], gb[gy0:gy1, gx0:gx1]
        box_src = [round(cx + x * cw, 1), round(cy + y * ch, 1), round(w * cw, 1), round(h * ch, 1)]
        rec = {**m, "file": fpath,
               "face": {**{k2: f.get(k2) for k2 in ("quality", "face_px", "yaw", "pitch", "eye_ratio", "eyes_open", "mouth_open",
                                                    "mouth_ratio", "sharpness", "geom", "box")}, "face_px_src": box_src[3]},
               "face_box_src": box_src, "face_box_4k": box_src,
               "touches_crop": bool(x < 0.01 or y < 0.01 or x + w > 0.99 or y + h > 0.99),
               "motion_mad": round(float(np.abs(pa - pb).mean()), 3) if pa.size else 99.0}
        if camera:
            rec["t_master"] = round(rec["t"] + offset, 3) if sync and sync.get("ok") else None
        recs.append(rec)
    if not recs:
        yc.fail("nessun campione con volto (controlla --layout / --seat / --point)")
    # 7. scarti e punteggio, per gruppo (ospite: inset + suo posto o camera; ogni host a parte)
    stats = {}
    for key in crops:
        S = [r for r in recs if r["layout"] == key]
        if not S:
            continue
        er = np.array([r["face"].get("eye_ratio") or np.nan for r in S], float)
        stats[key] = {"n": len(S), "eye_p80": float(np.nanpercentile(er, 80)) if np.isfinite(er).any() else 1.0,
                      "motion_p40": float(np.percentile([r["motion_mad"] for r in S], 40)),
                      "sharp_p50": float(np.percentile([r["face"].get("sharpness") or 0 for r in S], 50)),
                      "quality_p50": float(np.percentile([r["face"].get("quality") or 0 for r in S], 50)),
                      "mouth_p80": float(np.percentile([r["face"].get("mouth_open") or 0 for r in S], 80))}
    groups: dict[str, list[dict]] = {}
    for r in recs:
        groups.setdefault("guest" if crops[r["layout"]]["role"] == "guest" else r["layout"], []).append(r)
    Pg: dict[str, dict] = {}
    for gname, G in groups.items():
        for r in G:
            r["eyes_n"] = round((r["face"].get("eye_ratio") or 0) / max(1e-6, stats[r["layout"]]["eye_p80"]), 3)
        P = {"q": pct([r["face"].get("quality") or 0 for r in G]), "sh": pct([r["face"].get("sharpness") or 0 for r in G]),
             "mo": 1 - pct([r["motion_mad"] for r in G]), "fp": pct([r["face"]["face_px_src"] or 0 for r in G]),
             "fr": 1 - pct([abs(r["face"].get("yaw") if r["face"].get("yaw") is not None else 90) for r in G]),
             "ey": pct([min(r["eyes_n"], 1.1) for r in G])}
        Pg[gname] = P
        for i, r in enumerate(G):
            st = stats[r["layout"]]
            rej = []
            if r["touches_crop"]:
                rej.append("volto sul bordo")
            if r["eyes_n"] < 0.75:
                rej.append("occhi")
            if r["motion_mad"] > st["motion_p40"] * 1.5:
                rej.append("mosso")
            if (r["face"].get("sharpness") or 0) < st["sharp_p50"] * 0.8:
                rej.append("morbido")
            if (r["face"].get("quality") or 0) < st["quality_p50"]:
                rej.append("qualità")
            r["reject"] = rej
            r["s1"] = round(0.25 * P["q"][i] + 0.20 * P["sh"][i] + 0.15 * P["mo"][i] + 0.15 * P["fr"][i] + 0.10 * P["ey"][i]
                            + 0.15 * P["fp"][i], 4)

    def usable(r: dict) -> bool:          # scarti attuali, tranne «qualità» (come il vecchio foglio delle espressioni)
        return not (set(r["reject"]) - {"qualità"})

    # 8. MediaPipe (facoltativo) sui campioni utilizzabili
    mpst = ex.mp_status() if args.expr != "vision" else {"ok": False, "reason": "--expr vision"}
    if args.expr == "mediapipe" and not mpst["ok"]:
        yc.fail(f"--expr mediapipe: {mpst['reason']}")
    runner = None
    t_a = time.time()
    if mpst["ok"]:
        try:
            runner = ex.MPRunner(Path(mpst["model"]))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"MediaPipe non avviabile ({e}): solo geometria Vision")
    n_mp = 0
    if runner:
        for r in recs:
            if set(r["reject"]) - {"qualità", "occhi"}:
                continue
            img = np.asarray(Image.open(r["file"]).convert("RGB"))
            bs = runner.blendshapes(img, crop_box_px(r, img.shape[1], img.shape[0]))
            r["mps"] = ex.mp_signals(bs)
            if bs:
                r["_bs"] = bs
                n_mp += 1
        # mezzo battito (MediaPipe): eyeBlink alto e anomalo per la persona
        for key in crops:
            S = [r for r in recs if r["layout"] == key and r.get("mps")]
            if len(S) < 20:
                continue
            z = ex.robust_z(np.array([r["mps"]["blink"] for r in S]))
            for r, zz in zip(S, z):
                if r["mps"]["blink"] >= 0.5 and zz >= 2.5:
                    r["reject"].append("palpebre (MP)")
    # occhi stretti da un sorriso vero (AU6) non sono un battito: si tengono se MediaPipe vede il sorriso e non il battito,
    # o (senza MediaPipe) se la bocca sorride per la geometria Vision e gli occhi sono almeno a metà del p80 della persona
    n_squint = 0
    for gname, G in groups.items():
        ex.vision_signals(G)
        for r in G:
            if "occhi" not in r["reject"]:
                continue
            m = r.get("mps")
            smiling = (m["smile"] >= 0.45 and m["blink"] < 0.5) if m else (r["vz"]["smile"] >= 1.0 and r["eyes_n"] >= 0.55)
            if smiling:
                r["reject"] = [x for x in r["reject"] if x != "occhi"]
                r["eyes_squint_smile"] = True
                n_squint += 1
    T["mediapipe"] = time.time() - t_a
    if runner:
        yc.log(f"[scan] MediaPipe su {n_mp} frame in {T['mediapipe']:.0f}s")
    # 9. classi di espressione per gruppo (persona), con chi parla dalla trascrizione
    t_a = time.time()
    words = ex.Words.load(workdir, offset) if (workdir and (not camera or (sync and sync.get("ok")))) else None
    speakers_map = project.get("speakers") or {}
    group_info: dict[str, dict] = {}
    for gname, G in groups.items():
        if gname == "guest" and args.speaker:
            spk = {"speaker": args.speaker, "evidence": "--speaker"}
        else:
            spk = ex.active_speaker(G, words)
        cst = ex.classify(G, words, spk["speaker"])
        group_info[gname] = {"keys": sorted({r["layout"] for r in G}), "n": len(G), "speaker": spk["speaker"],
                             "name": speakers_map.get(spk["speaker"]) if spk["speaker"] else None,
                             "speaker_evidence": spk["evidence"], **cst}
    T["classify"] = time.time() - t_a
    # 10. classifica generale dell'ospite (come prima) + righe per classe
    G = groups.get("guest") or []
    for r in recs:                       # penalità metà parola e scettico anche nella classifica generale (07 §10.2)
        r["s1m"] = round(r["s1"] - ex.PEN_MID * bool(r.get("mid_word")) - ex.PEN_SCEPT * ("scettico" in (r.get("classes") or {})), 4)
    surv = sorted([r for r in G if not r["reject"]], key=lambda r: -r["s1m"])
    top = dedupe(surv, max(args.top * 3, 40))
    allowed = {i for i, r in enumerate(G) if usable(r)}
    class_rows: dict[str, list[dict]] = {}
    class_stats: dict[str, dict] = {}
    for cls in ex.CLASSES:
        ranked = ex.rank_class(G, Pg.get("guest", {}), cls, allowed) if G else []
        rows = []
        for i, sc in ranked:
            rows.append({**G[i], "class_score": sc, "class_fit": G[i]["classes"][cls]})
        picked = dedupe(rows, max(args.class_top * 4, 40))     # candidati: la risoluzione effettiva decide dopo (passo 11)
        moments_frontal = dedupe([x for x in rows if abs(x["face"].get("yaw") if x["face"].get("yaw") is not None else 90) <= 15], 99)
        class_rows[cls] = picked
        class_stats[cls] = {"members": sum(1 for r in G if cls in (r.get("classes") or {})),
                            "usable_not_mid_word": len(rows), "frontal_moments": len(moments_frontal),
                            "found": len(moments_frontal) >= 3}
    # 11. risoluzione effettiva sui candidati mostrati
    t_a = time.time()
    eff_cache: dict[tuple, dict] = {}       # per frame (le righe delle classi sono copie dei campioni)

    def eff_for(r: dict) -> dict:
        if (r["layout"], r["t"]) in eff_cache:
            return eff_cache[(r["layout"], r["t"])]
        c = crops[r["layout"]]
        bx = r["face_box_src"]
        if tuple(c["out"]) == tuple(c["rect"][2:]):
            rgb = np.asarray(Image.open(r["file"]).convert("RGB"), np.float64) / 255.0
            e = effective_face_px(rgb, [bx[0] - c["rect"][0], bx[1] - c["rect"][1], bx[2], bx[3]])
        else:                               # ritaglio ridotto per la scansione: misura sul frame nativo a 16 bit
            mx, my = 0.7 * bx[2], 0.7 * bx[3]
            reg = [int(max(0, bx[0] - mx)), int(max(0, bx[1] - my)), 0, 0]
            reg[2] = int(min(W, bx[0] + bx[2] + mx)) - reg[0]
            reg[3] = int(min(H, bx[1] + bx[3] + my)) - reg[1]
            reg[2] -= reg[2] % 2
            reg[3] -= reg[3] % 2
            with tempfile.TemporaryDirectory(dir=str(outdir)) as td:
                fr = Path(td) / "f.png"
                extract16(src, r["t"], fr, crop=reg)
                e = effective_face_px(load16(fr), [bx[0] - reg[0], bx[1] - reg[1], bx[2], bx[3]])
        eff_cache[(r["layout"], r["t"])] = e
        return e

    def add_eff(r: dict) -> None:
        r.update(eff_for(r))
        bx = r["face_box_src"]
        r["upscale_for"] = {str(ff): round(ff * OUT_H / bx[3], 2) for ff in (0.22, 0.234, 0.249)}
        r["max_face_frac_at_cap"] = round(MAX_UPSCALE * bx[3] / OUT_H, 3)            # legacy 2.0× sul box
        r["eff_upscale_at_cap"] = round(MAX_UPSCALE * bx[3] / r["eff_face_px"], 2) if r.get("eff_face_px") else None
        if r.get("eff_face_px"):
            r["display_cap_face_frac"] = {m: display_cap_limits(r["eff_face_px"], bx[3], m)["max_face_frac"] for m in DISPLAY_CAPS}

    for r in top:
        add_eff(r)
    pe = pct([r.get("eff_face_px") or 0 for r in top])
    for i, r in enumerate(top):
        r["score"] = round(r["s1m"] * 0.75 + 0.25 * pe[i], 4)
    top.sort(key=lambda r: -r["score"])
    top = top[:args.top]
    for i, r in enumerate(top, 1):
        r["rank"] = i
        r["frontal"] = bool(abs(r["face"].get("yaw") if r["face"].get("yaw") is not None else 90) <= 15)
    # righe per classe: come la classifica generale, 75 % punteggio di classe + 25 % risoluzione effettiva. Con il tetto
    # al display la risoluzione effettiva è la misura massima del volto ottenibile: sostituisce l'altezza del box,
    # che premia il campo largo (box più grande, ma già ingrandito in montaggio: effettivo ≈ 97–125 px contro 150–170)
    for cls, rows in class_rows.items():
        for r in rows:
            add_eff(r)
        pe_c = pct([r.get("eff_face_px") or 0 for r in rows])
        for i, r in enumerate(rows):
            r["score"] = round(0.75 * r["class_score"] + 0.25 * pe_c[i], 4)
        rows.sort(key=lambda r: -r["score"])
        del rows[args.class_top:]
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            r["frontal"] = bool(abs(r["face"].get("yaw") if r["face"].get("yaw") is not None else 90) <= 15)
    T["eff"] = time.time() - t_a
    # 12. stabilità n → n+1 (MediaPipe) sui primi di ogni classe
    t_a = time.time()
    stab_rows = []
    if runner:
        for cls, rows in class_rows.items():
            for r in rows[:3]:
                if not r.get("mps"):
                    continue
                img = np.asarray(Image.open(r["next"]).convert("RGB"))
                nxt = ex.mp_signals(runner.blendshapes(img, crop_box_px(r, img.shape[1], img.shape[0])))
                r["mp_stability"] = ex.stability(r["mps"], nxt)
                if r["mp_stability"]:
                    stab_rows.append(r["mp_stability"])
        if not runner.close():
            yc.log("[scan] MediaPipe: chiusura ancora in corso (continua in background)")
    stability = ({k: {"median": round(float(np.median([s[k] for s in stab_rows])), 4),
                      "p90": round(float(np.percentile([s[k] for s in stab_rows], 90)), 4)} for k in stab_rows[0]}
                 if stab_rows else None)
    T["stability"] = time.time() - t_a
    # 13. posti del campo largo (--seat all) e momenti duo (ospite + host nello stesso istante)
    seats_out: dict[str, dict] = {}
    duo: list[dict] = []
    if args.seat == "all":
        for key, c in crops.items():
            if c["layout"] != "wide":
                continue
            S = sorted([r for r in recs if r["layout"] == key and not r["reject"]], key=lambda r: -r["s1"])
            best = dedupe(S, 6)
            for r in best:
                add_eff(r)
            gname = "guest" if c["role"] == "guest" else key
            gi = group_info.get(gname, {})
            seats_out[key] = {"seat": c["seat"], "role": c["role"], "speaker": gi.get("speaker"), "name": gi.get("name"),
                              "speaker_evidence": gi.get("speaker_evidence"), "n": sum(1 for r in recs if r["layout"] == key),
                              "survivors": len(S), "top": best}
        gk = next((k2 for k2, c in crops.items() if c["layout"] == "wide" and c["role"] == "guest"), None)
        by_t = {key: {r["t"]: r for r in recs if r["layout"] == key} for key in crops}
        spk_g = group_info.get("guest", {}).get("speaker")
        cand_duo = []
        for hk, c in crops.items():
            if c["layout"] != "wide" or c["role"] != "host" or not gk:
                continue
            for t, rg in by_t[gk].items():
                rh = by_t[hk].get(t)
                if not rh or not usable(rg) or not usable(rh):
                    continue
                react = bool(set(rh.get("classes") or {}) & {"sorriso", "risata", "sorpresa"})
                g_speaks = bool(words and spk_g and words.speaking(t, spk_g, 0.0))
                sc = (0.5 * rg["s1"] + 0.5 * rh["s1"] + 0.10 * react + 0.05 * g_speaks
                      - 0.15 * bool(rg.get("mid_word")) - 0.10 * bool(rh.get("mid_word")))
                cand_duo.append({"t": t, "score": round(sc, 4), "guest": rg, "host": rh, "host_key": hk,
                                 "host_reacting": react, "guest_speaking": g_speaks})
        cand_duo.sort(key=lambda d: -d["score"])
        for d in dedupe(cand_duo, 12):
            add_eff(d["guest"])
            add_eff(d["host"])
            hs = crops[d["host_key"]]["seat"]
            d["cut"] = (f"yt-portrait duo {workdir or 'WORKDIR'} --t {d['t']} --guest wide-{args.guest_seat} --host wide-{hs} "
                        "--face-frac max")
            duo.append(d)
    # 14. fogli di contatto
    t_a = time.time()
    sheets = []
    for idx in range(0, len(top), 20):
        p = outdir / f"scan_sheet_{idx // 20 + 1}.jpg"
        face_sheet(top[idx:idx + 20], p)
        sheets.append(str(p))
    p = outdir / "scan_expr.jpg"
    if expr_sheet(class_rows, class_stats, p, per_row=min(3, args.class_top)):
        sheets.append(str(p))
    if seats_out:
        p = outdir / "scan_seats.jpg"
        rows_s = {f"{v['seat']} · {v['role']}" + (f" · {v['name']}" if v.get("name") else ""): v["top"][:5] for v in seats_out.values()}
        expr_sheet(rows_s, {}, p, per_row=5, plain=True)
        sheets.append(str(p))
    if duo:
        p = outdir / "scan_duo.jpg"
        duo_sheet(duo[:8], p)
        sheets.append(str(p))
    T["sheets"] = time.time() - t_a
    # 15. copie dei candidati mostrati (il raw si cancella) e JSON
    keep = outdir / "scan_top"
    keep.mkdir(exist_ok=True)
    shown = top + [r for rows in class_rows.values() for r in rows] + [r for v in seats_out.values() for r in v["top"]] \
        + [x for d in duo for x in (d["guest"], d["host"])]
    copied: dict[str, str] = {}
    for r in shown:
        if r["file"] in copied:
            r["file"] = copied[r["file"]]
            continue
        dst = keep / f"{r['layout']}_{r['t']:09.3f}.jpg"
        if Path(r["file"]).resolve() != dst.resolve() and Path(r["file"]).exists():
            shutil.copy(r["file"], dst)
        copied[r["file"]] = str(dst)
        r["file"] = str(dst)
    if not args.keep_raw:
        shutil.rmtree(raw, ignore_errors=True)

    def slim(r: dict, full_mp: bool = False) -> dict:
        out = {k: v for k, v in r.items() if k not in ("next", "_bs")}
        if full_mp and r.get("_bs"):
            out["blendshapes"] = r["_bs"]
        return out

    rejects: dict[str, int] = {}
    for r in recs:
        for x in r["reject"]:
            rejects[x] = rejects.get(x, 0) + 1
    cheek = [r["mps"]["cheek"] for r in G if r.get("mps")]
    not_found = [c for c in ex.NON_SCEPTICAL if not class_stats[c]["found"]]
    found = [c for c in ex.NON_SCEPTICAL if class_stats[c]["found"]]
    T["total"] = time.time() - t_start
    expr_summary = {
        "engine": "vision+mediapipe" if runner else "vision", "mediapipe": mpst, "frames_mediapipe": n_mp,
        "groups": group_info, "classes": class_stats, "found_non_sceptical": found,
        "message": (f"classi non scettiche con ≥ 3 momenti frontali (|yaw| ≤ 15°): {', '.join(found)}"
                    if len(found) >= 2 else "meno di 2 classi non scettiche con ≥ 3 frame frontali: non trovato → servono still"),
        "not_found": {c: "non trovato → servono still (o la camera stretta)" for c in not_found},
        "eyes_reject_lifted_for_smile": n_squint,
        "duchenne": ({"available": bool(np.percentile(cheek, 95) >= 0.05), "cheek_p95": round(float(np.percentile(cheek, 95)), 4),
                      "note": "cheekSquint quasi sempre 0 su questo volto: sorriso ordinato su mouthSmile + mouthUpperUp"
                      if np.percentile(cheek, 95) < 0.05 else ""} if cheek else None),
        "mp_stability_n_n1": stability,
        "weights": {**ex.W_RANK, "pen_mid_word": "escluso dalle righe", "pen_sceptical": ex.PEN_SCEPT},
    }
    summary = {"range": [t0, t1], "every_s": args.every, "frames_decoded": len(pts), "pairs": len(pairs),
               "samples_with_face": len(recs), "by_layout": {key: sum(1 for r in recs if r["layout"] == key) for key in crops},
               "survivors": len(surv), "rejects": rejects, "stats": stats,
               "layout_seconds": {lab: round(sum(1 for _, l in labels if l == lab) / 2, 1) for lab in {l for _, l in labels}},
               "timings_s": {k2: round(v, 1) for k2, v in T.items()},
               "frontal_in_top": sum(1 for r in top if r["frontal"]), "expressions": expr_summary}
    yc.write_json(outdir / "scan.json", {
        "version": 2, "workdir": str(workdir) if workdir else None, "source": str(src), "source_kind": "camera" if camera else "master",
        "layout_mode": mode, "offset_s": offset if camera else 0.0, "sync": sync,
        "crops": crops, "crops_4k": {k2: c["rect"] for k2, c in crops.items()},
        "summary": summary, "top": [slim(r) for r in top],
        "classes": {c: [slim(r, full_mp=True) for r in rows] for c, rows in class_rows.items()},
        "expressive": [slim(r) for c in ("sorriso", "risata", "sorpresa") for r in class_rows.get(c, [])],
        "seats": {k2: {**v, "top": [slim(r) for r in v["top"]]} for k2, v in seats_out.items()},
        "duo": [{**{k2: v for k2, v in d.items() if k2 not in ("guest", "host")}, "guest": slim(d["guest"]), "host": slim(d["host"])}
                for d in duo],
        "note": ("scegliere a occhio dai fogli; poi yt-portrait cut WORKDIR --t <t> --roi inset|wide-<seat> --face-frac max"
                 + (f"; camera: yt-portrait cut WORKDIR --src {src} --camera --offset {offset} --t <t> --roi full" if camera else ""))})

    if args.dump:                         # tutti i campioni, per la calibrazione su frame etichettati (07 §10.4)
        keys_dump = ("t", "t_master", "layout", "s1", "reject", "mid_word", "mid_word_why", "classes", "vz", "mps", "motion_mad",
                     "eyes_n", "face_box_src")
        yc.write_json(outdir / "scan_samples.json", [{**{k2: r.get(k2) for k2 in keys_dump},
                                                      "face": {k2: v for k2, v in r["face"].items() if k2 != "box"}} for r in recs])

    def brief(r: dict) -> dict:
        return {"t": r["t"], "ts": yc.fmt_ts(r["t"], "yt"), "layout": r["layout"], "yaw": r["face"].get("yaw"),
                "eff_face_px": r.get("eff_face_px"), "mid_word": r.get("mid_word"), "fit": r.get("class_fit")}
    yc.emit(True, outputs={"scan": str(outdir / "scan.json"), "sheets": sheets, "top": [
        {k2: r.get(k2) for k2 in ("rank", "t", "layout", "score", "eff_face_px", "display_cap_face_frac", "frontal")}
        | {"yaw": r["face"].get("yaw"), "face_px": r["face"].get("face_px")} for r in top[:10]],
        "classes": {c: [brief(r) for r in rows[:3]] for c, rows in class_rows.items()},
        "duo": [{"t": d["t"], "host": d["host_key"], "score": d["score"], "guest_eff": d["guest"].get("eff_face_px"),
                 "host_eff": d["host"].get("eff_face_px")} for d in duo[:5]]},
        summary=summary, warnings=warnings, seconds=round(time.time() - t_start, 1))


def face_tile(r: dict, label: str = "", size: int = 300, rank: bool = True) -> Image.Image:
    im = Image.open(r["file"]).convert("RGB")
    x, y, w, h = crop_box_px(r, im.width, im.height)
    s = max(w, h) * 2.2
    box = (int(x + w / 2 - s / 2), int(y + h / 2 - s * 0.48), int(x + w / 2 + s / 2), int(y + h / 2 + s * 0.52))
    t = im.crop(box).resize((size, size), Image.LANCZOS)
    d = ImageDraw.Draw(t)
    d.rectangle([0, 0, size, 34], fill=(0, 0, 0))
    f = r["face"]
    head = f"{label}#{r.get('rank', '')} " if rank else label
    d.text((4, 2), f"{head}{r['layout']} t={r['t']:.1f} ({yc.fmt_ts(r['t'], 'yt')})", fill=(255, 255, 255), font=font(12))
    extra = f" fit{r['class_fit']:.2f}" if r.get("class_fit") is not None else ""
    if r.get("mps"):
        extra += f" sm{r['mps']['smile']:.2f}"
    d.text((4, 17), f"fp{f.get('face_px_src') or f.get('face_px') or 0:.0f} eff{r.get('eff_face_px') or 0:.0f} yaw{(f.get('yaw') or 0):+.0f} "
                     f"bocca{(f.get('mouth_open') or 0):.2f}{extra}", fill=(220, 220, 220), font=font(12))
    return t


def face_sheet(rows: list[dict], out: Path, label: str = "") -> None:
    tiles = [face_tile(r, label) for r in rows]
    if not tiles:
        return
    cols = 5
    rows_n = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * 304, rows_n * 304), (30, 30, 30))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 304, (i // cols) * 304))
    sheet.save(out, quality=88)


def expr_sheet(class_rows: dict[str, list[dict]], class_stats: dict, out: Path, per_row: int = 3, plain: bool = False) -> bool:
    """Una riga per classe: etichetta + i primi per_row frame (vuoto = «non trovato → servono still»)."""
    if not any(class_rows.values()):
        return False
    import expressions as ex  # noqa: PLC0415
    lab_w, tile = 260, 300
    rows = list(class_rows.items())
    sheet = Image.new("RGB", (lab_w + per_row * (tile + 4), len(rows) * (tile + 4)), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for ri, (cls, items) in enumerate(rows):
        y = ri * (tile + 4)
        d.rectangle([0, y, lab_w - 6, y + tile], fill=(0x15, 0x17, 0x1c))
        d.text((10, y + 10), cls.upper(), fill=(0xf7, 0x57, 0x00), font=font(26, 800))
        if not plain:
            st = class_stats.get(cls) or {}
            d.text((10, y + 48), ex.CLASS_HELP.get(cls, ""), fill=(0xf4, 0xf1, 0xea), font=font(12))
            d.text((10, y + 72), f"membri {st.get('members', 0)} · utili {st.get('usable_not_mid_word', 0)}", fill=(200, 200, 200), font=font(13))
            d.text((10, y + 92), f"momenti frontali {st.get('frontal_moments', 0)}", fill=(200, 200, 200), font=font(13))
            if not st.get("found") and cls != "scettico":
                d.text((10, y + 120), "non trovato →\nservono still", fill=(0xef, 0xc4, 0x47), font=font(16, 700))
        for ci, r in enumerate(items[:per_row]):
            sheet.paste(face_tile(r, "" if plain else cls[:4] + " ", rank=not plain), (lab_w + ci * (tile + 4), y))
    sheet.save(out, quality=88)
    return True


def duo_sheet(duo: list[dict], out: Path) -> None:
    """Momenti duo: ospite | host nello stesso istante (due tile per riga, due coppie per riga)."""
    tile = 300
    cols = 2
    rows_n = math.ceil(len(duo) / cols)
    sheet = Image.new("RGB", (cols * (2 * tile + 24), rows_n * (tile + 4)), (30, 30, 30))
    for i, dd in enumerate(duo):
        x0, y0 = (i % cols) * (2 * tile + 24), (i // cols) * (tile + 4)
        sheet.paste(face_tile(dd["guest"], f"duo{i + 1} ", rank=False), (x0, y0))
        sheet.paste(face_tile(dd["host"], "", rank=False), (x0 + tile + 4, y0))
    sheet.save(out, quality=88)


# ── plate ───────────────────────────────────────────────────────────────────
def columns_fill(small: np.ndarray, people: np.ndarray, valid: np.ndarray, iters: int = 3, row_sigma: float = 10.0,
                 res_sigma: float = 70.0) -> np.ndarray:
    """Fondale di un muro a pannelli senza le persone (plate --fill columns): modello separabile
    colore(x) × guadagno(y) stimato con mediane robuste sui pixel di fondale (fuori dalla maschera delle persone: i giunti
    verticali scuri restano nel profilo delle colonne), poi il residuo dei pixel validi riempito a bassissima frequenza
    (σ `res_sigma` px a 1/4 di risoluzione: luce e macchie larghe, mai la forma di una persona). Solo pixel del sorgente,
    nessuna AI. `small` H×W×3 (0–255), `people` = maschera dilatata di persone e PiP, `valid` = fondale col colore dominante."""
    H, W = small.shape[:2]
    bg = ~people
    lum = small.mean(-1)
    row = np.ones(H)
    col = np.zeros((W, 3))
    xs, ys = np.arange(W), np.arange(H)
    for _ in range(iters):
        ok = np.zeros(W, bool)
        for x in range(W):
            m = bg[:, x]
            if m.sum() >= 4:
                col[x] = np.median(small[m, x] / row[m, None], axis=0)
                ok[x] = True
        for c in range(3):
            col[:, c] = np.interp(xs, xs[ok], col[ok, c])
        cl = np.maximum(col.mean(-1), 1e-3)
        ratio = lum / cl[None, :]
        rr = np.full(H, np.nan)
        for y in range(H):
            m = valid[y]
            if m.sum() >= 8:
                rr[y] = np.median(ratio[y, m])
        okr = ~np.isnan(rr)
        if okr.sum() >= 2:
            row = np.interp(ys, ys[okr], rr[okr])
            row = ndimage.gaussian_filter1d(row, row_sigma, mode="nearest")
    model = row[:, None, None] * col[None, :, :]
    v = valid.astype(np.float64)
    res = small - model
    num = np.stack([ndimage.gaussian_filter(res[..., c] * v, res_sigma) for c in range(3)], -1)
    den = ndimage.gaussian_filter(v, res_sigma)[..., None]
    return model + num / np.maximum(den, 1e-6) * np.clip(den / 0.05, 0, 1)


def cmd_plate(args: argparse.Namespace) -> None:
    """Fondale della location senza persone (plate dei template), solo elaborazione classica:
    finestra camera del master → maschera di TUTTE le persone (Apple Vision) + PiP + pixel lontani dal colore
    dominante del fondale → stima del fondale per convoluzione normalizzata dei pixel validi → 16:9, sfocatura."""
    t_start = time.time()
    workdir = yc.resolve_workdir(args.workdir)
    project = yc.load_project(workdir)
    layout = brand_layout(project.get("channel") or default_channel())
    src = Path(args.src).expanduser() if args.src else yc.source_path(workdir)
    info = probe_stream(src)
    W, H = info["w"], info["h"]
    t = yc.parse_ts(args.t)
    win = roi_rect(args.roi, layout, W, H) if args.roi != "wide" else (rect_of(layout, "wide") or [0, 0, W, H])
    I = 40
    win = [win[0] + I, win[1] + I, win[2] - 2 * I, win[3] - 2 * I]
    outdir = Path(args.out).expanduser().resolve() if args.out else (workdir / "thumbs" / "plates")
    outdir.mkdir(parents=True, exist_ok=True)
    name = args.name or f"plate_{t:09.3f}".replace(".", "_")
    tmp = Path(tempfile.mkdtemp(prefix="yt-plate-", dir=str(outdir)))
    try:
        fr16 = tmp / "win16.png"
        extract16(src, t, fr16, crop=win)
        rgb = load16(fr16)
        win8 = tmp / "win8.png"
        Image.fromarray(to8(rgb)).save(win8)
        mask_p = tmp / "people.png"
        r = thumbvision("cutout", str(win8), "--out", str(tmp / "cut.png"), "--mode", "person", "--instance", "all",
                        "--mask-out", str(mask_p))
        if isinstance(r, dict) and r.get("ok") is False:
            raise RuntimeError(f"thumbvision: {r.get('error')}")
        hole = np.asarray(Image.open(mask_p).convert("L").resize((rgb.shape[1], rgb.shape[0]))) > 10
        if rect_of(layout, "pip"):
            px, py, pw, ph = rect_of(layout, "pip")
            x0, y0 = px - win[0] - 20, py - win[1] - 20
            hole[max(0, y0):max(0, y0 + ph + 40), max(0, x0):max(0, x0 + pw + 40)] = True
        q = 4
        small = np.asarray(Image.fromarray(to8(rgb)).resize((rgb.shape[1] // q, rgb.shape[0] // q), Image.LANCZOS)).astype(np.float64)
        hs = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255).resize((small.shape[1], small.shape[0]))) > 0
        hs = ndimage.binary_dilation(hs, iterations=10)
        med = np.median(small[~hs], axis=0)
        dist = np.sqrt(((small - med) ** 2).sum(axis=2))
        valid = ndimage.binary_erosion((~hs) & (dist < args.tolerance), iterations=2)
        v = valid.astype(np.float64)

        def nconv(sg: float):
            num = np.stack([ndimage.gaussian_filter(small[..., c] * v, sg) for c in range(3)], -1)
            den = ndimage.gaussian_filter(v, sg)[..., None]
            return num / np.maximum(den, 1e-9), den

        if getattr(args, "fill", "nconv") == "columns":
            out = columns_fill(small, hs, valid)
        else:
            est, den = nconv(args.sigma)
            est2, _ = nconv(150)
            w = np.clip(den / 0.25, 0, 1)
            out = est * w + est2 * (1 - w)
        pim = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
        Wp, Hp = pim.size
        tw = int(Hp * 16 / 9)
        if tw <= Wp:
            pim = pim.crop(((Wp - tw) // 2, 0, (Wp - tw) // 2 + tw, Hp))
        from PIL import ImageFilter
        pim = pim.resize((3840, 2160), Image.BICUBIC).filter(ImageFilter.GaussianBlur(args.blur))
        jpg = outdir / f"{name}.jpg"
        pim.save(jpg, quality=93)
        Image.fromarray((valid * 255).astype(np.uint8)).save(outdir / f"{name}_valid.png")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    share = round(float(valid.mean()), 3)
    warnings = [] if share > 0.25 else [f"solo {share:.0%} di fondale valido: plate poco affidabile, scegli un altro tempo"]
    yc.emit(True, outputs={"plate": str(jpg), "valid_mask": str(outdir / f"{name}_valid.png")},
            summary={"t": t, "window_px": win, "valid_share": share, "median_rgb": [round(float(x)) for x in med]},
            warnings=warnings, seconds=round(time.time() - t_start, 1))



# ── duo ─────────────────────────────────────────────────────────────────────
def cmd_duo(args: argparse.Namespace) -> None:
    """Ospite + host dallo stesso istante del campo largo (07 §10.5: stesso episodio, reazione nella posizione reale),
    testa e spalle, ciascuno col suo tetto; il volto dell'host non supera mai quello dell'ospite (07 §12.4)."""
    t_start = time.time()
    warnings: list[str] = []
    workdir = yc.resolve_workdir(args.workdir)
    project = yc.load_project(workdir)
    layout = brand_layout(project.get("channel") or default_channel())
    src = Path(args.src).expanduser() if args.src else yc.source_path(workdir)
    if not src.exists():
        yc.fail(f"sorgente non trovato: {src}")
    outdir = Path(args.out).expanduser().resolve() if args.out else (workdir / "thumbs" / "portrait")
    outdir.mkdir(parents=True, exist_ok=True)
    t = yc.parse_ts(args.t)
    name = args.name or f"duo_{t:09.3f}".replace(".", "_")
    base = {**vars(args), "image": None, "camera": False, "offset": 0.0, "point": None, "upscale": None, "keep_frame": False}
    ga = argparse.Namespace(**{**base, "roi": args.guest})
    yc.log(f"[duo] {name}: ospite {args.guest} t={t}")
    g = cut_one(ga, workdir, src, t, f"{name}_guest", outdir, layout, warnings)
    hb = {**base, "roi": args.host}
    if str(args.face_frac) == "max":
        hb["face_max_px"] = g["face_out_px"]
    elif args.face_px or args.face_frac:
        want = float(args.face_px) if args.face_px else float(args.face_frac) * OUT_H
        hb.update({"face_px": min(want, g["face_out_px"]), "face_frac": None})
    yc.log(f"[duo] {name}: host {args.host} (volto ≤ {g['face_out_px']:.0f} px)")
    h = cut_one(argparse.Namespace(**hb), workdir, src, t, f"{name}_host", outdir, layout, warnings)
    sheet = outdir / f"{name}_sheet.jpg"
    contact_sheet([g, h], sheet)
    speakers = project.get("speakers") or {}
    res = {"t": t, "ts": yc.fmt_ts(t, "yt"), "guest": g, "host": h,
           "guest_ge_host": bool(g["face_out_px"] >= h["face_out_px"] - 0.5),
           "rule": "07 §10.5: stesso istante dello stesso episodio; 07 §12.4: volto dell'ospite ≥ host",
           "speakers": speakers, "sheet": str(sheet)}
    yc.write_json(outdir / f"{name}.json", res)
    yc.emit(True, outputs={"duo": str(outdir / f"{name}.json"), "sheet": str(sheet),
                           "guest": {k: g.get(k) for k in ("png", "face_frac", "eff_face_px", "display_cap", "served_lapvar", "served_status")},
                           "host": {k: h.get(k) for k in ("png", "face_frac", "eff_face_px", "display_cap", "served_lapvar", "served_status")}},
            warnings=warnings, seconds=round(time.time() - t_start, 1))


# ── autotest ────────────────────────────────────────────────────────────────
def cmd_selftest(args: argparse.Namespace) -> None:
    """Prove unitarie senza media: tetto, controllo per il render, dettaglio servito, offset audio, classi."""
    import wave  # noqa: PLC0415
    import expressions as ex  # noqa: PLC0415
    res: list[tuple[str, bool, str]] = []
    c = display_cap_limits(152.4, 253.9, "c")
    b = display_cap_limits(152.4, 253.9, "b")
    lg = display_cap_limits(152.4, 253.9, "legacy")
    res.append(("tetto c su un volto con eff 152,4 px: 914 px = 42,3 %", abs(c["max_face_out_px"] - 914.4) < 0.1 and abs(c["max_face_frac"] - 0.4233) < 1e-3, str(c["max_face_out_px"])))
    res.append(("tetto b: 686 px = 31,8 %", abs(b["max_face_out_px"] - 685.8) < 0.1, str(b["max_face_out_px"])))
    res.append(("tetto legacy: 2,0× il box = 508 px", abs(lg["max_face_out_px"] - 507.8) < 0.1, str(lg["max_face_out_px"])))
    res.append(("senza risoluzione effettiva → legacy", display_cap_limits(None, 253.9, "c")["mode"].startswith("legacy"), ""))
    res.append(("tetto numerico 1.75", abs(display_cap_limits(100, 200, "1.75")["max_face_out_px"] - 525) < 0.01, ""))
    meta = {"scale": 3.6, "face_out_px": 914.4, "display_cap": {**c}}
    ok = display_cap_check(meta)
    over = display_cap_check({**meta, "scale": 3.9, "face_out_px": 990})
    res.append(("render: entro il tetto → ok", ok["level"] == "ok" and abs(ok["display_upscale"] - 2.0) < 0.01, str(ok)))
    res.append(("render: oltre il tetto → error", over["level"] == "error", over["message"]))
    res.append(("render: oltre con motivo → warn", display_cap_check({**meta, "scale": 3.9}, override="G2 ok")["level"] == "warn", ""))
    res.append(("render: sidecar v1 → 2,0× sul box", display_cap_check({"scale": 2.3})["level"] == "error"
                and display_cap_check({"scale": 1.9})["level"] == "ok", ""))
    res.append(("render: ridisegno 1,1× conta", display_cap_check(meta, draw_scale=1.1)["level"] == "error", ""))
    g = np.zeros((10, 10))
    g[5, 5] = 10
    res.append(("Laplaciano 4-vicini (impulso 10 → varianza 31,25)", abs(lap_var_u8(g) - 31.25) < 1e-9 and lap_var_u8(np.ones((5, 5))) == 0,
                str(lap_var_u8(g))))
    rng = np.random.default_rng(7)
    canvas = np.full((2160, 3840, 3), 128, np.uint8)
    face = (rng.random((800, 600, 3)) * 255).astype(np.uint8)
    canvas[700:1500, 2000:2600] = face
    rgba = np.dstack([face, np.full(face.shape[:2], 255, np.uint8)])
    pr = predict_served_detail(rgba, [0, 0, 600, 800])
    sv = served_face_detail(Image.fromarray(canvas), [2000 / 3840, 700 / 2160, 600 / 3840, 800 / 2160])
    res.append(("stima del dettaglio servito = misura sul render (±10 %)", abs(pr["lapvar"] - sv["lapvar"]) / sv["lapvar"] < 0.10,
                f"stima {pr['lapvar']} render {sv['lapvar']}"))
    res.append(("soglie servito 713/569", served_status(800) == "ok" and served_status(600) == "warn" and served_status(500) == "error", ""))
    with tempfile.TemporaryDirectory() as td:
        sr = 8000
        x = np.zeros(sr * 90, np.float32)
        for k in range(160):                                 # «parlato»: raffiche a tempi casuali
            s0 = int(rng.uniform(0, 89.5) * sr)
            x[s0:s0 + int(0.12 * sr)] += rng.normal(0, 0.3, int(0.12 * sr)).astype(np.float32)[:len(x[s0:s0 + int(0.12 * sr)])]
        def wav(path: Path, data: np.ndarray) -> None:
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes((np.clip(data, -1, 1) * 32000).astype("<i2").tobytes())
        wav(Path(td) / "m.wav", x)
        wav(Path(td) / "c.wav", x[int(12.34 * sr):] + rng.normal(0, 0.01, len(x) - int(12.34 * sr)).astype(np.float32))
        off = audio_offset(Path(td) / "c.wav", audio_envelope(Path(td) / "m.wav"), 90 - 12.34, win=40)
        res.append(("offset audio camera→master (atteso +12,34 s)", bool(off["ok"]) and abs(off["offset_s"] - 12.34) <= 0.02,
                    f"{off.get('offset_s')} picco {[w['peak_ratio'] for w in off['windows']]}"))
    res.append(("--face-frac max/0.4", face_frac_arg("max") == "max" and face_frac_arg("0.4") == 0.4, ""))
    # buchi del matte: lente sull'occhio (colore pelle) riempita col sorgente; lente contro il muro (colore sfondo),
    # spazio braccio–busto e bordo morbido esterno restano com'erano
    al = np.zeros((200, 200))
    al[20:190, 40:160] = 1.0                                   # sagoma; box del volto 50–150 × 30–130
    al[60:72, 70:90] = 0.0                                     # lente sull'occhio
    al[58:60, 68:92] = 0.7                                     # suo bordo morbido
    al[60:70, 120:135] = 0.0                                   # lente «di profilo» che mostra il muro
    al[150:175, 60:75] = 0.0                                   # spazio braccio–busto, sotto il volto
    al[20:190, 40:42] = 0.7                                    # bordo morbido esterno
    srcp = np.full((200, 200, 3), 0.9)                         # muro
    srcp[20:190, 40:160] = 0.3                                 # pelle/vestiti
    srcp[60:72, 70:90] = 0.35                                  # sotto la lente: occhio e pelle veri
    srcp[60:70, 120:135] = 0.88                                # attraverso la lente: il muro
    a2, f2, hi = fill_face_holes(al, np.zeros((200, 200, 3)), srcp, [50, 30, 100, 100])
    res.append(("buchi del matte: lente sull'occhio riempita col sorgente; lente sul muro, braccio–busto e bordo intatti",
                bool(a2[65, 80] == 1.0 and abs(f2[65, 80, 0] - 0.35) < 1e-9 and a2[59, 80] == 1.0 and a2[65, 127] == 0.0
                     and a2[160, 66] == 0.0 and a2[100, 41] == 0.7 and hi["components"] == 1 and hi["skipped"] == 2), str(hi)))
    res += [(f"espressioni: {n}", ok_, why) for n, ok_, why in ex.selftest()]
    failed = [r for r in res if not r[1]]
    for name, ok_, why in res:
        yc.log(f"  {'ok ' if ok_ else 'KO '} {name}" + (f" — {why}" if why and not ok_ else ""))
    out = {"passed": len(res) - len(failed), "failed": len(failed), "tests": [{"name": n, "ok": o, "detail": w} for n, o, w in res]}
    if failed:
        yc.fail(f"selftest: {len(failed)} prove fallite su {len(res)}", **out)
    yc.emit(True, **out)


# ── CLI ─────────────────────────────────────────────────────────────────────
def face_frac_arg(v: str):
    if str(v).lower() == "max":
        return "max"
    f = float(v)
    if not 0 < f <= 1:
        raise argparse.ArgumentTypeError("--face-frac: una frazione 0–1 oppure «max»")
    return f


def display_cap_arg(v: str) -> str:
    if v in DISPLAY_CAPS or v == "legacy":
        return v
    try:
        if float(v) > 0:
            return v
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("--display-cap: c (2.0×), b (1.5×), legacy (2.0× sul box) oppure un fattore")


def add_size_args(c: argparse.ArgumentParser) -> None:
    """Misura del volto, tetto e taglio (comuni a cut e duo)."""
    g = c.add_mutually_exclusive_group()
    g.add_argument("--face-frac", type=face_frac_arg, default=0.25,
                   help="altezza del volto / 2160 (default 0.25), oppure «max» = il più grande consentito dal tetto (≤ 0.5)")
    g.add_argument("--face-px", type=float, help="altezza del volto in px del canvas 3840×2160")
    g.add_argument("--upscale", type=float, help="fattore sul box del volto nel sorgente (limitato dal tetto)")
    c.add_argument("--display-cap", type=display_cap_arg, default=DEFAULT_DISPLAY_CAP,
                   help="tetto: c = volto a 1280 px ≤ 2.0× la risoluzione effettiva (default); b = 1.5×; "
                        "legacy = ≤ --max-upscale sul box del sorgente (regola precedente)")
    c.add_argument("--max-upscale", type=float, default=MAX_UPSCALE, help="solo con --display-cap legacy: cap sul box (2.0)")
    c.add_argument("--over-cap-reason", help="supera il tetto solo con un motivo scritto (va nel brief G2)")
    c.add_argument("--served-floor", choices=["error", "warn", "off"], default="error",
                   help=f"con --face-frac max: dettaglio servito stimato da rispettare (error = ≥ {SERVED_ERR:.0f}, default; "
                        f"warn = ≥ {SERVED_WARN:.0f}; off = solo il tetto)")
    c.add_argument("--preset", choices=list(CROP_PRESETS), default="bust",
                   help="taglio: cu = primo piano (mento + spalle, 1.6 volti sotto), hs = testa e spalle (2.4), bust = busto (3.6, default)")
    c.add_argument("--body", type=float, help="altezza sotto il volto in altezze di volto (sostituisce --preset)")


def main() -> None:
    p = argparse.ArgumentParser(prog="yt-portrait", formatter_class=argparse.RawDescriptionHelpFormatter,
                                description="Ritratti dell'ospite per le thumbnail: scansione dei frame del master e scontorno non generativo.",
                                epilog="""Esempi:
  yt-portrait scan mio-canale/2026-03-02-ospite --out /tmp/p                  # tutto l'episodio (auto: inset + posto destro
                                                                                #  con un layout composito, altrimenti tutto il frame)
  yt-portrait scan W --from 19:00 --to 19:30 --layout wide --seat right
  yt-portrait scan W --layout wide --seat all --every 1                         # posti del campo largo + momenti duo
  yt-portrait scan W --source src/iso/cam_ospite.mov --layout full              # camera stretta (offset audio automatico)
  yt-portrait cut W --t 84.0 --roi full --name ospite_84 --face-frac max       # il volto più grande consentito (tetto c)
  yt-portrait cut W --t 84.0 --roi inset --face-frac max --display-cap b        # ripiego 1,5× (opzione b; inset = layout composito)
  yt-portrait cut W --src cam.mov --camera --offset 12.3 --t 600 --roi full --face-frac 0.45 --preset hs
  yt-portrait duo W --t 1150 --guest wide-right --host wide-center --face-frac max --preset hs
  yt-portrait cut W --t 1150 --roi wide-left --face-frac 0.18 --name host_1150
  yt-portrait cut - --image stills/IMG_0412.jpg --face-frac 0.36 --name still_04   # still di sessione (fonte 1)
  yt-portrait plate W --t 1153 --name set                                        # fondale del set (niente persone)

Uscita di cut: <name>.png (RGBA 8 bit, già alla misura finale: il template lo disegna 1:1), <name>_16.png,
<name>.json (scala, volto, risoluzione effettiva, bordi dritti da mettere a filo del canvas), <name>.meta.json
(per yt-thumb-render: chiave portrait.display_cap = tetto, portrait.served_detail = dettaglio servito stimato),
<name>_proof.jpg (prova di conservazione del volto). Regole: 07 §10–§11. Tetto: volto a
1280 px ≤ 2,0× la risoluzione effettiva (c, default) o 1,5× (b); --face-frac max rispetta anche il dettaglio servito
(stima a 720 px ≥ 569, --served-floor). yt-portrait selftest: prove unitarie senza media.""")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scansione del master (o di una camera stretta) e classifica dei frame per classe di espressione")
    s.add_argument("workdir", help="cartella di lavoro ('-' con --source e --out)")
    s.add_argument("--src", help="master alternativo con lo stesso layout (default: main_source di project.json)")
    s.add_argument("--source", help="file di una camera separata (thumbnail cam, ISO): niente layout composito, default --layout full")
    s.add_argument("--offset", type=float, help="con --source: tempo master = tempo camera + OFFSET (s); senza, --sync auto")
    s.add_argument("--sync", choices=["auto", "none"], default="auto", help="con --source: offset dall'audio (correlazione con il master)")
    s.add_argument("--scan-height", type=int, default=1080, help="con --layout full: altezza dei frame analizzati (default 1080)")
    s.add_argument("--point", help="con --layout full: x,y (0–1 o px) vicino al volto da seguire se ce n'è più di uno")
    s.add_argument("--every", type=float, default=0.5, help="un campione (coppia di frame) ogni N s (default 0.5)")
    s.add_argument("--from", dest="from_", help="inizio (s o hh:mm:ss)")
    s.add_argument("--to", help="fine")
    s.add_argument("--layout", choices=["auto", "inset", "wide", "full"], default="auto",
                   help="auto = inset + campo largo se il brand del canale ha un layout composito misurato (layout.json con inset o "
                        "sonde), altrimenti tutto il frame (con --source: full); full = tutto il frame, nessuna ipotesi")
    s.add_argument("--seat", choices=[*SEATS, "all"], default="right",
                   help="posto dell'ospite nel campo largo (default right); all = tutti i posti + momenti duo")
    s.add_argument("--guest-seat", choices=list(SEATS), default="right", help="con --seat all: il posto dell'ospite (default right)")
    s.add_argument("--speaker", help="speaker della trascrizione per l'ospite (es. S0; default: dedotto dal movimento della bocca)")
    s.add_argument("--expr", choices=["auto", "vision", "mediapipe"], default="auto",
                   help="segnali delle espressioni: auto = MediaPipe se installato, altrimenti geometria Vision")
    s.add_argument("--class-top", type=int, default=6, help="candidati per classe di espressione (default 6; il foglio ne mostra 3)")
    s.add_argument("--top", type=int, default=20, help="candidati nel foglio (default 20)")
    s.add_argument("--out", help="cartella (default WORKDIR/thumbs/portrait)")
    s.add_argument("--keep-raw", action="store_true", help="non cancellare i JPEG grezzi (≈2,7 GB per 53 min)")
    s.add_argument("--reuse-raw", action="store_true", help="riusa i JPEG grezzi già estratti (debug)")
    s.add_argument("--dump", action="store_true", help="scrive anche scan_samples.json con tutti i campioni (calibrazione)")
    c = sub.add_parser("cut", help="scontorno non generativo alla misura finale")
    c.add_argument("workdir", help="cartella di lavoro ('-' con --image)")
    c.add_argument("--t", help="tempo/i sul master (s o hh:mm:ss, separati da virgola)")
    c.add_argument("--image", help="still dell'ospite al posto del master (fonte preferita, 07 §10.1)")
    c.add_argument("--src", help="sorgente video (default: main_source)")
    c.add_argument("--channel", help="canale per layout.json se manca il workdir (default: l'unico profilo dei channels_dirs, "
                                      "se ce n'è uno solo; altrimenti nessun layout)")
    c.add_argument("--roi", default="auto", help="inset | wide | wide-left|center|right | full | x,y,w,h (default auto = layout al tempo t)")
    c.add_argument("--seat", choices=list(SEATS), default="right", help="posto nel campo largo con --roi auto (default right)")
    c.add_argument("--point", help="x,y (px del frame o 0–1) vicino al volto da scontornare")
    add_size_args(c)
    c.add_argument("--camera", action="store_true", help="--src è una camera separata (thumbnail cam, ISO): niente layout composito")
    c.add_argument("--offset", type=float, default=0.0, help="con --camera: tempo master = tempo camera + OFFSET (s)")
    c.add_argument("--matte", choices=["auto", "birefnet", "vision"], default="auto", help="motore del matte (default auto: BiRefNet, ripiego Vision)")
    c.add_argument("--alpha-levels", default="0.1,0.95", help="livelli dell'alpha dopo il resize (0,1 = off)")
    c.add_argument("--no-sharpen", action="store_true", help="niente nitidezza luma dopo il resize")
    c.add_argument("--keep-holes", action="store_true",
                   help="non riempire i buchi del matte nella fascia degli occhi (lente degli occhiali: di default α = 1 e "
                        "pixel del sorgente)")
    c.add_argument("--name", help="nome dei file (con più tempi: <name>_01, _02 …)")
    c.add_argument("--out", help="cartella (default WORKDIR/thumbs/portrait)")
    c.add_argument("--sheet", action="store_true", help="foglio di contatto anche con un solo tempo")
    c.add_argument("--keep-frame", action="store_true", help="tieni anche il frame a 16 bit della ROI")
    c.add_argument("--force", action="store_true", help="rifà anche se esiste")
    d = sub.add_parser("duo", help="ospite + host dallo stesso istante del campo largo, ciascuno col suo tetto")
    d.add_argument("workdir")
    d.add_argument("--t", required=True, help="tempo sul master (da scan --seat all: scan_duo.jpg)")
    d.add_argument("--guest", default="wide-right", help="ROI dell'ospite (default wide-right)")
    d.add_argument("--host", default="wide-center", help="ROI dell'host (default wide-center)")
    d.add_argument("--src", help="sorgente (default: main_source)")
    add_size_args(d)
    d.set_defaults(preset="hs", face_frac="max")
    d.add_argument("--matte", choices=["auto", "birefnet", "vision"], default="auto")
    d.add_argument("--alpha-levels", default="0.1,0.95")
    d.add_argument("--no-sharpen", action="store_true")
    d.add_argument("--keep-holes", action="store_true", help="non riempire i buchi del matte nella fascia degli occhi")
    d.add_argument("--seat", default="right", help=argparse.SUPPRESS)
    d.add_argument("--name", help="prefisso dei file (default duo_<t>)")
    d.add_argument("--out", help="cartella (default WORKDIR/thumbs/portrait)")
    sub.add_parser("selftest", help="prove unitarie (tetto, controllo del render, dettaglio servito, offset audio, classi)")
    pl = sub.add_parser("plate", help="fondale della location senza persone (plate dei template), senza AI")
    pl.add_argument("workdir")
    pl.add_argument("--t", required=True, help="tempo di un'inquadratura larga col fondale ben visibile")
    pl.add_argument("--src", help="sorgente (default: main_source)")
    pl.add_argument("--roi", default="wide", help="wide (finestra camera di layout.json) | x,y,w,h")
    pl.add_argument("--sigma", type=float, default=25, help="raggio della stima (px a 1/4 di risoluzione, default 25)")
    pl.add_argument("--tolerance", type=float, default=60, help="distanza RGB dal colore dominante per i pixel validi (default 60)")
    pl.add_argument("--blur", type=float, default=12, help="sfocatura finale in px a 4K (default 12)")
    pl.add_argument("--fill", choices=["nconv", "columns"], default="nconv",
                    help="riempimento delle zone con persone: nconv = convoluzione normalizzata (default; con --sigma piccolo "
                         "lascia sagome «fantasma»); columns = muro a pannelli: profilo per colonna × guadagno per riga dai pixel "
                         "del fondale (giunti verticali inclusi) + residuo a bassissima frequenza → niente sagome (plate del duo)")
    pl.add_argument("--name", help="nome del file (default plate_<t>)")
    pl.add_argument("--out", help="cartella (default WORKDIR/thumbs/plates)")
    args = p.parse_args()
    if args.cmd == "scan":
        cmd_scan(args)
    elif args.cmd == "duo":
        cmd_duo(args)
    elif args.cmd == "selftest":
        cmd_selftest(args)
    elif args.cmd == "plate":
        cmd_plate(args)
    else:
        if not args.t and not args.image:
            yc.fail("cut: serve --t o --image")
        cmd_cut(args)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc(file=sys.stderr)
        yc.fail(f"{type(exc).__name__}: {exc}")
