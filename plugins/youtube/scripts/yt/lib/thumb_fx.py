"""thumb_fx — effetti e controlli d'immagine delle thumbnail v2 (policy v2 sui pixel delle persone, 07 §11.2).

Tutto locale e deterministico (numpy/scipy/Pillow, niente modelli). Usato da `yt-thumb-render` (lib/thumb_render.py).

Livelli della policy v2 (knowledge/07-thumbnails.md §11):
  1  grafica attorno alla persona, volto intatto: contorno/alone SOTTO il ritaglio, forme dietro, copia scurita/sfocata
     della propria scena (pop-out), bokeh e grade della plate → i pixel opachi del ritaglio non cambiano
     (controllo `face_pixels_unchanged`, fatto da yt-thumb-render confrontando il render con e senza effetti);
  2  tono globale e uniforme su TUTTO il ritaglio (curva, contrasto, LUT «look» del brand; nessun aumento di saturazione) →
     controllo ΔE00 sulla pelle: media ≤ 2.5 e p95 ≤ 5 (la forza si regola da sola per restare sotto la soglia);
  2b grade monocromatico uniforme (opzione del concept `grade: mono`): UNA curva di tono
     (luma Rec.709 → curva monotona → rampa inchiostro→carta del brand, <brand>/mono-curve.json) applicata
     identica a ogni pixel di tutte le persone e della plate; nessun ritocco locale sui volti. La pelle cambia per
     definizione (diventa grigia): il ΔE00 non si applica e lo sostituiscono (a) la coerenza della mappatura
     (`mono_mapping_check`: l'uscita è la stessa funzione dell'ingresso su ogni pixel, scarto dalla curva analitica e
     dispersione per classe di luma in livelli a 8 bit) e (b) i landmark invariati (`landmarks_shift`, MediaPipe 478
     punti, spostamento ÷ distanza tra gli occhi). La plate può in più essere sfocata, scurita (ev prima della curva) e
     vignettata: operazioni di sfondo del livello 1, mai sui pixel delle persone;
  3+ (luce simulata, super-resolution appresa) non in questo modulo; 5 (generativo) vietato.

Funzioni principali:
  brand_look(rgb) / write_cube / read_cube / apply_lut   LUT «look» (curva + contrasto, neri verso l'inchiostro,
                                                      alte luci verso la carta, saturazione invariata)
  tone_cutout(src, dst, mode, face)                   livello 2 sul ritaglio, con ΔE00 sulla pelle e forza auto
  grade_plate(src, dst, mode, …)                      plate: mono (duotono inchiostro→carta), look, bokeh, scurimento
  scene_frame(video, t, roi)                          frame della sorgente (ffmpeg) per il pop-out del template scena
  served_detail / face_surround_dL / silhouette_dL / matte_holes / changed_pixels   controlli sul PNG reso

  mono_params / mono_grade / mono_mapping_check / landmarks_shift / accent_contrast   livello 2b (grade mono)
  edge_separation_dark                                 stacco del bordo della tile dalla pagina scura di YouTube

Rigenerare la LUT del brand:  python3 lib/thumb_fx.py lut --brand demo   (scrive <brand>/look-33.cube)
Rigenerare la LUT mono (.cube per NLE, dalla curva JSON):  python3 lib/thumb_fx.py mono-lut --brand demo   (<brand>/mono-33.cube)
(--brand cerca prima nei brands_dirs dell'operatore, poi in assets/brands del plugin; --dir DIR = cartella esplicita)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SKIN_GATE = (2.5, 5.0)           # ΔE00 pelle: media, p95 (policy v2, livello 2)
LOOK_FILE = "look-33.cube"       # LUT del look del brand (livello 2), facoltativa: senza si calcola dai token
MONO_CUBE = "mono-33.cube"       # LUT della curva mono per gli NLE (il render usa la curva esatta)
LUT_SIZE = 33


# ── Colore ──────────────────────────────────────────────────────────────────
def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float64) / 255.0


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB 0–1 (…,3) → CIELAB D65."""
    lin = srgb_to_linear(np.clip(rgb, 0, 1))
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """ΔE00 (Sharma, Wu, Dalal 2005), vettoriale su (…,3)."""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dh = h2p - h1p
    dh = np.where(C1p * C2p == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(C1p * C2p == 0, hs, np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def s_curve(y: np.ndarray, c: float) -> np.ndarray:
    """Contrasto morbido: 0 e 1 fissi, pendenza 1+c a metà, 1−c agli estremi (c ∈ [0, 0.9])."""
    return np.clip(y - c * np.sin(2 * np.pi * y) / (2 * np.pi), 0, 1)


# ── Look del brand (livello 2) ──────────────────────────────────────────────
def brand_look(rgb: np.ndarray, ink: np.ndarray, paper: np.ndarray, contrast: float = 0.30, desat: float = 0.0,
            toe: float = 0.55, shoulder: float = 0.35) -> np.ndarray:
    """Curva + contrasto sul luma (RGB scalato in proporzione: tinta e rapporto di saturazione invariati), neri verso
    l'inchiostro, alte luci verso la carta. `desat` > 0 solo per il look «duo» (mai un aumento di saturazione)."""
    y = luma(rgb)
    y2 = s_curve(y, contrast)
    k = np.where(y > 1e-4, y2 / np.maximum(y, 1e-4), 1.0)[..., None]
    c = rgb * k
    # dove lo scalamento porta un canale oltre 1, si avvicina al grigio dello stesso luma quanto basta (tinta invariata)
    mx = c.max(-1, keepdims=True)
    yy = y2[..., None]
    t = np.where(mx > 1, (1 - yy) / np.maximum(mx - yy, 1e-6), 1.0)
    out = np.clip(yy + t * (c - yy), 0, 1)
    if desat:
        g = luma(out)[..., None]
        out = g + (out - g) * (1 - desat)
    w_ink = (toe * (1 - y2) ** 6)[..., None]
    w_pap = (shoulder * y2 ** 8)[..., None]
    out = out * (1 - w_ink) + ink * w_ink
    out = out * (1 - w_pap) + paper * w_pap
    return np.clip(out, 0, 1)


def mono(rgb: np.ndarray, ink: np.ndarray, paper: np.ndarray, contrast: float = 0.55, ev: float = -0.9,
         gamma: float = 1.0) -> np.ndarray:
    """Duotono di brand per le plate: luma → contrasto → esposizione → rampa inchiostro→carta."""
    y = luma(rgb)
    y = s_curve(np.clip(y, 0, 1), contrast)
    y = np.clip(y * (2.0 ** ev), 0, 1) ** gamma
    return ink + (paper - ink) * y[..., None]


def make_lut(fn, n: int = LUT_SIZE) -> np.ndarray:
    g = np.linspace(0, 1, n)
    R, G, B = np.meshgrid(g, g, g, indexing="ij")
    return fn(np.stack([R, G, B], -1))                      # [r, g, b, 3]


def write_cube(path: Path, lut: np.ndarray, title: str, comments: list[str] = ()) -> None:
    n = lut.shape[0]
    lines = [f'TITLE "{title}"'] + [f"# {c}" for c in comments] + [f"LUT_3D_SIZE {n}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    for b in range(n):                                     # .cube: il rosso varia più in fretta
        for g in range(n):
            for r in range(n):
                v = lut[r, g, b]
                lines.append(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
    Path(path).write_text("\n".join(lines) + "\n")


def read_cube(path: Path) -> np.ndarray:
    n, vals = None, []
    for line in Path(path).read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("TITLE") or s.startswith("DOMAIN"):
            continue
        if s.startswith("LUT_3D_SIZE"):
            n = int(s.split()[1])
            continue
        vals.append([float(x) for x in s.split()])
    a = np.array(vals, np.float64).reshape(n, n, n, 3)     # [b, g, r, 3]
    return a.transpose(2, 1, 0, 3)                         # → [r, g, b, 3]


def apply_lut(rgb: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """Interpolazione trilineare di una LUT [r,g,b,3] su rgb 0–1."""
    n = lut.shape[0]
    p = np.clip(rgb, 0, 1) * (n - 1)
    i0 = np.minimum(np.floor(p).astype(int), n - 2)
    f = p - i0
    out = np.zeros_like(rgb)
    for dr in (0, 1):
        wr = f[..., 0] if dr else 1 - f[..., 0]
        for dg in (0, 1):
            wg = f[..., 1] if dg else 1 - f[..., 1]
            for db in (0, 1):
                wb = f[..., 2] if db else 1 - f[..., 2]
                out += (wr * wg * wb)[..., None] * lut[i0[..., 0] + dr, i0[..., 1] + dg, i0[..., 2] + db]
    return out


def brand_colors(tokens: dict) -> tuple[np.ndarray, np.ndarray]:
    c = (tokens or {}).get("colors", {})
    return hex_rgb(c.get("ink", "#15171c")), hex_rgb(c.get("paper", "#f4f1ea"))


def brand_lut(tokens: dict, brand_dir: Path | None) -> np.ndarray:
    """LUT «look»: dal file .cube del brand se c'è (deterministico, versionato), altrimenti calcolata dai token."""
    if brand_dir is not None:
        f = Path(brand_dir) / LOOK_FILE
        if f.is_file():
            return read_cube(f)
    ink, paper = brand_colors(tokens)
    return make_lut(lambda x: brand_look(x, ink, paper))


# ── Livello 2b: grade monocromatico uniforme (persone + plate, stessa curva) ──
MONO_FILE = "mono-curve.json"
# Curva di serie «mono-1» (ripresa in <brand>/mono-curve.json, che vince se c'è): luma Rec.709 dei valori
# sRGB → uscita 0–1 sulla rampa inchiostro→carta. Neri profondi, medi con un po' di pendenza (volti), spalla lunga che
# comprime i bianchi (una maglia bianca resta a L* ~80: sotto il titolo carta e sotto un cerchio d'accento chiaro); medi ripidi
# (pendenza ~1,5) perché il dettaglio del volto nel file servito non scenda sotto quello a colori.
MONO_DEFAULT = {"id": "mono-1", "space": "luma709", "ramp": ["ink", "paper"], "keep_sat": 0.0,
                "points": [[0.0, 0.0], [0.10, 0.02], [0.25, 0.10], [0.40, 0.25], [0.55, 0.48], [0.68, 0.67], [0.78, 0.745],
                           [0.88, 0.775], [0.95, 0.785], [1.0, 0.79]]}
MONO_MAP_TOL = 2                 # livelli a 8 bit: scarto massimo dalla curva analitica (arrotondamenti)
LM_SHIFT_WARN, LM_SHIFT_ERR = 0.02, 0.04     # landmark: spostamento medio ÷ distanza tra gli occhi (come yt-thumb-qa)


def mono_params(tokens: dict | None = None, brand_dir: Path | None = None, override: dict | None = None) -> dict:
    """Parametri della curva mono: file del brand (mono-curve.json) → default di serie; `override` (dal concept,
    `grade_curve`) sostituisce i punti per una prova, e cambia l'id (la firma resta tracciabile nel sidecar)."""
    p = dict(MONO_DEFAULT)
    if brand_dir is not None and (Path(brand_dir) / MONO_FILE).is_file():
        try:
            p.update(json.loads((Path(brand_dir) / MONO_FILE).read_text()))
        except Exception:  # noqa: BLE001 — file rotto: si resta sul default, ma si dice
            p["warning"] = f"{MONO_FILE} illeggibile: curva di default"
    if override:
        p.update({k: v for k, v in override.items() if k in ("points", "keep_sat", "id")})
        if "id" not in override:
            p["id"] = p["id"] + "+override"
    pts = np.asarray(p["points"], np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 2 or np.any(np.diff(pts[:, 0]) <= 0) or np.any(np.diff(pts[:, 1]) < 0):
        raise ValueError(f"curva mono non valida (punti crescenti in x e non decrescenti in y): {p['points']}")
    return p


def mono_signature(params: dict, tokens: dict | None = None) -> str:
    """Firma della funzione colore→colore (curva + rampa): uguale su persone e plate = stessa curva."""
    import hashlib
    ink, paper = brand_colors(tokens or {})
    blob = json.dumps({"points": params["points"], "keep_sat": params.get("keep_sat", 0.0), "space": params.get("space"),
                       "ink": [round(float(v), 6) for v in ink], "paper": [round(float(v), 6) for v in paper]}, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def mono_curve(y: np.ndarray, params: dict) -> np.ndarray:
    """Curva monotona (PCHIP: nessun rimbalzo tra i punti) sul luma 0–1."""
    from scipy.interpolate import PchipInterpolator
    pts = np.asarray(params["points"], np.float64)
    return np.clip(PchipInterpolator(pts[:, 0], pts[:, 1])(np.clip(y, 0, 1)), 0, 1)


def mono_grade(rgb: np.ndarray, params: dict, ink: np.ndarray, paper: np.ndarray, pre_ev: float = 0.0) -> np.ndarray:
    """Livello 2b: colore → luma Rec.709 → (esposizione, solo plate) → curva → rampa inchiostro→carta (+ un resto di
    saturazione `keep_sat`, default 0 = mono). Funzione del solo colore del pixel: uguale ovunque."""
    rgb = np.asarray(rgb, np.float64)
    y = luma(rgb)
    if pre_ev:
        y = np.clip(y * 2.0 ** pre_ev, 0, 1)
    yo = mono_curve(y, params)
    out = ink + (paper - ink) * yo[..., None]
    ks = float(params.get("keep_sat") or 0.0)
    if ks:
        out = out + ks * (rgb - y[..., None])
    return np.clip(out, 0, 1)


def mono_mapping_check(src_rgb: np.ndarray, out_rgb: np.ndarray, mask: np.ndarray, params: dict, ink: np.ndarray,
                       paper: np.ndarray, bins: int = 64) -> dict:
    """Coerenza della mappatura sui pixel `mask` (persona opaca): l'uscita è la curva analitica dell'ingresso? Scarto
    massimo e p99.9 in livelli a 8 bit dal valore atteso (stesso colore → stessa uscita: un ritocco locale lo rompe),
    dispersione dell'uscita per classe di luma, e la curva misurata (mediana per classe) da confrontare tra persone."""
    s = np.asarray(src_rgb, np.float64)[mask]
    o = np.asarray(out_rgb, np.float64)[mask]
    if s.max() > 1.5:
        s = s / 255.0
    if o.max() > 1.5:
        o = o / 255.0
    if len(s) == 0:
        return {"ok": False, "reason": "nessun pixel opaco"}
    exp = mono_grade(s, params, ink, paper)
    dev = np.abs(np.round(exp * 255) - np.round(o * 255)).max(-1)
    y_in = luma(s)
    y_out = luma(o) * 255
    idx = np.minimum((y_in * bins).astype(int), bins - 1)
    curve, spread = [], []
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        if n >= 30:
            v = y_out[sel]
            med = float(np.median(v))
            # dispersione attesa entro la classe = pendenza della curva × ampiezza della classe: si misura il residuo
            # dalla curva analitica, non la dispersione grezza
            curve.append([round((b + 0.5) / bins, 4), round(med, 2), n])
            spread.append(float(np.percentile(np.abs(v - luma(exp[sel]) * 255), 99)))
    return {"ok": True, "px": int(len(s)), "max_dev_levels": int(dev.max()), "p999_dev_levels": float(np.percentile(dev, 99.9)),
            "bin_resid_p99_max": round(max(spread), 2) if spread else None, "curve": curve,
            "pass": bool(dev.max() <= MONO_MAP_TOL)}


def curve_gap(curve_a: list, curve_b: list) -> dict | None:
    """Scarto tra due curve misurate (mono_mapping_check.curve) sulle classi comuni, in livelli a 8 bit di luma."""
    da = {c[0]: c[1] for c in curve_a or []}
    gaps = [abs(da[c[0]] - c[1]) for c in curve_b or [] if c[0] in da]
    if not gaps:
        return None
    return {"bins": len(gaps), "max": round(max(gaps), 2), "mean": round(float(np.mean(gaps)), 2)}


def _mp_landmarker():
    """FaceLandmarker di MediaPipe (modello di expressions.mp_model_path) o None se non installato."""
    try:
        import expressions as ex  # noqa: PLC0415
        st = ex.mp_status(check_sha=False)
        if not st["ok"]:
            return None, st.get("reason")
        import absl.logging  # noqa: PLC0415
        absl.logging.set_verbosity(absl.logging.ERROR)
        import os  # noqa: PLC0415
        os.environ.setdefault("GLOG_minloglevel", "2")
        import mediapipe as mp  # noqa: PLC0415
        from mediapipe.tasks import python as mpt  # noqa: PLC0415
        from mediapipe.tasks.python import vision  # noqa: PLC0415
        opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=str(st["model"])),
                                            output_face_blendshapes=True, num_faces=1, running_mode=vision.RunningMode.IMAGE)
        return (mp, vision.FaceLandmarker.create_from_options(opts)), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def landmarks_shift(src_rgba: np.ndarray, out_rgba: np.ndarray, face_px: list[float], grow: float = 2.2) -> dict:
    """Landmark invariati (livello 2b): MediaPipe (478 punti + blendshape) sullo stesso ritaglio del volto del ritaglio
    originale e di quello graduato, appiattiti sullo stesso grigio medio; spostamento ÷ distanza tra gli angoli esterni
    degli occhi (33–263) e differenza massima dei blendshape di espressione. Solo misura: nessun pixel cambia."""
    lm, why = _mp_landmarker()
    if lm is None:
        return {"ok": False, "engine": None, "reason": f"MediaPipe non disponibile: {why}"}
    mp, det = lm
    h, w = src_rgba.shape[:2]
    x, y, fw, fh = face_px
    s = max(fw, fh) * grow
    cx, cy = x + fw / 2, y + fh / 2
    x0, y0, x1, y1 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2)), int(min(w, cx + s / 2)), int(min(h, cy + s / 2))

    def flat(a: np.ndarray) -> np.ndarray:
        c = a[y0:y1, x0:x1].astype(np.float64)
        al = c[..., 3:4] / 255.0
        g = c[..., :3] * al + 128.0 * (1 - al)
        img = np.clip(np.round(g), 0, 255).astype(np.uint8)
        side = max(img.shape[:2])
        if side > 1024:
            from PIL import Image
            k = 1024 / side
            img = np.asarray(Image.fromarray(img).resize((max(1, round(img.shape[1] * k)), max(1, round(img.shape[0] * k))), Image.LANCZOS))
        return np.ascontiguousarray(img)

    res = []
    try:
        for a in (src_rgba, out_rgba):
            img = flat(a)
            r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=img))
            if not r.face_landmarks:
                res.append(None)
                continue
            pts = np.array([[p.x * img.shape[1], p.y * img.shape[0]] for p in r.face_landmarks[0]])
            bs = {b.category_name: float(b.score) for b in r.face_blendshapes[0]} if r.face_blendshapes else {}
            res.append((pts, bs))
    finally:
        try:
            det.close()
        except Exception:  # noqa: BLE001
            pass
    if res[0] is None or res[1] is None:
        return {"ok": False, "engine": "mediapipe", "found": [res[0] is not None, res[1] is not None],
                "reason": "volto non trovato da MediaPipe"}
    (pa, ba), (pb, bs_b) = res
    iod = float(np.linalg.norm(pa[33] - pa[263]))
    d = np.linalg.norm(pa - pb, axis=1) / max(iod, 1e-6)
    keys = ("mouthSmileLeft", "mouthSmileRight", "jawOpen", "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp", "browDownLeft",
            "browDownRight", "mouthPressLeft", "mouthPressRight", "cheekSquintLeft", "cheekSquintRight")
    dbs = {k: abs(ba.get(k, 0) - bs_b.get(k, 0)) for k in keys if k in ba and k in bs_b}
    worst = max(dbs, key=dbs.get) if dbs else None
    mean = float(d.mean())
    return {"ok": True, "engine": "mediapipe", "points": int(len(pa)), "iod_px": round(iod, 1), "mean": round(mean, 4),
            "p95": round(float(np.percentile(d, 95)), 4), "max": round(float(d.max()), 4),
            "bs_worst": worst, "bs_max": round(dbs[worst], 3) if worst else None,
            "level": "error" if mean > LM_SHIFT_ERR else ("warn" if mean > LM_SHIFT_WARN else "pass")}


def person_tones(rgb: np.ndarray, alpha: np.ndarray, face_px: list[float]) -> dict:
    """L* mediano di volto (ellisse interna), capelli (fascia sopra il box del volto) e busto (sotto il mento) di un ritaglio:
    per scegliere l'accento del cerchio sul mono e per misurare la «massa chiara» del busto."""
    h, w = alpha.shape
    x, y, fw, fh = face_px
    L = None
    out = {}
    face, _ = skin_mask(rgb, alpha, face_px)

    def med(m):
        nonlocal L
        if m.sum() < 50:
            return None
        if L is None:
            L = rgb_to_lab(rgb)[..., 0]
        return round(float(np.median(L[m])), 1)
    out["face_L"] = med(face)
    hair = np.zeros_like(face)
    hy0, hy1 = int(max(0, y - 0.30 * fh)), int(max(0, y + 0.08 * fh))
    hair[hy0:hy1, int(max(0, x + 0.1 * fw)):int(min(w, x + 0.9 * fw))] = True
    out["hair_L"] = med(hair & (alpha >= 0.999))
    torso = np.zeros_like(face)
    torso[int(min(h, y + 1.35 * fh)):, :] = True
    tm = torso & (alpha >= 0.999)
    out["torso_L"] = med(tm)
    if tm.sum() >= 50:
        out["torso_L_p90"] = round(float(np.percentile(L[tm], 90)), 1)
    return out


def accent_names(tokens: dict | None) -> list[str]:
    """Nomi dei colori d'accento del brand: tokens.accents, altrimenti tokens.accent, altrimenti ogni colore che non è
    inchiostro, carta o un neutro di servizio."""
    t = tokens or {}
    col = t.get("colors") or {}
    names = [n for n in (t.get("accents") or []) if n in col]
    if not names and t.get("accent") in col:
        names = [t["accent"]]
    if not names:
        names = [n for n in col if n not in ("ink", "paper", "bg", "fg", "muted", "rule", "line", "border", "surface")]
    return names


def accent_contrast(tones: dict, tokens: dict, names=None) -> dict:
    """ΔL* di ogni accento verso capelli e volto della persona davanti al cerchio; `best` = il massimo del minimo.
    `names` = accenti candidati (default: tutti quelli del brand, accent_names)."""
    col = (tokens or {}).get("colors", {})
    names = list(names) if names else accent_names(tokens)
    res = {}
    for n in names:
        if n not in col:
            continue
        La = float(rgb_to_lab(hex_rgb(col[n]))[0])
        res[n] = {"L": round(La, 1), "dL_hair": round(abs(La - tones["hair_L"]), 1) if tones.get("hair_L") is not None else None,
                  "dL_face": round(abs(La - tones["face_L"]), 1) if tones.get("face_L") is not None else None}
    def score(v):
        xs = [t for t in (v["dL_hair"], v["dL_face"]) if t is not None]
        return min(xs) if xs else -1
    best = max(res, key=lambda k: score(res[k])) if res else None
    return {"by_accent": res, "best": best, "rule": "massimo di min(ΔL* capelli, ΔL* volto) sul ritaglio graduato"}


def edge_separation_dark(render, band: int = 6, tile_w: int = 360, page: tuple = (15, 15, 15)) -> dict:
    """Stacco della tile dal feed scuro: render → file servito 720×405 → tile da 360 px; L* medio della cornice di
    `band` px contro la pagina #0f0f0f (stesso metodo di yt-thumb-qa edge_separation) e quota del perimetro «chiara»
    (≥ 40 ΔL* dalla pagina: cerchio, disco carta o maglia che toccano il bordo)."""
    from PIL import Image
    im = render if isinstance(render, Image.Image) else Image.open(render)
    served = im.convert("RGB").resize((720, 405), Image.LANCZOS)
    tile = served.resize((tile_w, round(tile_w * 9 / 16)), Image.LANCZOS)
    a = np.asarray(tile, np.float64) / 255.0
    L = rgb_to_lab(a)[..., 0]
    Lp = float(rgb_to_lab(np.array(page, np.float64) / 255.0)[0])
    m = np.zeros(L.shape, bool)
    m[:band] = m[-band:] = True
    m[:, :band] = m[:, -band:] = True
    d = np.abs(L[m] - Lp)
    prof = np.concatenate([L[:band, :].mean(0), L[:, -band:].mean(1), L[-band:, ::-1].mean(0), L[::-1, :band].mean(1)])
    light = (prof - Lp) >= 40
    # tratto continuo più lungo (profilo chiuso), come yt-thumb-qa edge_separation: un elemento di cornice è UNA massa chiara
    # che tocca il bordo, non tanti pezzetti sparsi (una thumbnail può avere un terzo del bordo chiaro a pezzetti e il tratto
    # più lungo all'1 %)
    run = 0
    if light.all():
        run = len(light)
    elif light.any():
        k = int(np.argmin(light))
        r = np.concatenate([np.roll(light, -k), [False]]).astype(np.int8)
        dd = np.diff(np.concatenate([[0], r]))
        st, en = np.flatnonzero(dd == 1), np.flatnonzero(dd == -1)
        run = int((en - st).max()) if len(st) else 0
    return {"edge_dL_dark": round(float(d.mean()), 1), "edge_light_share": round(float(light.mean()), 3),
            "edge_light_run": round(run / max(1, len(light)), 3)}


# ── Livello 2 sul ritaglio: tono globale con soglia ΔE00 sulla pelle ─────────
def skin_mask(rgb: np.ndarray, alpha: np.ndarray, face_px: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """(volto, pelle): pixel opachi (α ≥ 0.999) nell'ellisse interna del box del volto; pelle = banda di tinta 15–80°."""
    h, w = alpha.shape
    x, y, fw, fh = face_px
    face = np.zeros((h, w), bool)
    skin = np.zeros((h, w), bool)
    x0, y0 = int(max(0, x)), int(max(0, y))                  # solo il box del volto: il resto del ritaglio non serve
    x1, y1 = int(min(w, x + fw + 1)), int(min(h, y + fh + 1))
    if x1 <= x0 or y1 <= y0:
        return face, skin
    yy, xx = np.mgrid[y0:y1, x0:x1]
    cx, cy = x + fw / 2, y + fh / 2
    ell = ((xx - cx) / (0.42 * fw)) ** 2 + ((yy - cy) / (0.48 * fh)) ** 2 <= 1
    f = ell & (alpha[y0:y1, x0:x1] >= 0.999)
    lab = rgb_to_lab(rgb[y0:y1, x0:x1])
    hue = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360
    C = np.hypot(lab[..., 1], lab[..., 2])
    face[y0:y1, x0:x1] = f
    skin[y0:y1, x0:x1] = f & (hue >= 15) & (hue <= 80) & (C >= 6) & (lab[..., 0] >= 20) & (lab[..., 0] <= 95)
    return face, skin


def _de_stats(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    if not len(a):
        return 0.0, 0.0
    d = ciede2000(rgb_to_lab(a), rgb_to_lab(b))
    return float(d.mean()), float(np.percentile(d, 95))


def tone_mono(src: Path, dst: Path, face_norm: list[float], tokens: dict, params: dict, landmarks: bool = True) -> dict:
    """Livello 2b su un ritaglio: la curva mono (mono_grade) su ogni pixel visibile, calcolata sui colori distinti a 8 bit
    (funzione colore→colore: stessa uscita per lo stesso colore ovunque, volto compreso). Alpha e geometria invariate.
    Controlli: mappatura (scarto dalla curva analitica ≤ 2 livelli) e landmark MediaPipe (spostamento medio ≤ 2 %
    della distanza tra gli occhi: avviso; > 4 %: errore). Il ΔE00 della pelle non si applica (la pelle diventa grigia)."""
    from PIL import Image

    im = Image.open(src).convert("RGBA")
    a8 = np.asarray(im, np.uint8)
    ink, paper = brand_colors(tokens)
    vis = a8[..., 3] > 0
    px8 = a8[..., :3][vis].astype(np.uint32)
    codes = (px8[:, 0] << 16) | (px8[:, 1] << 8) | px8[:, 2]
    uniq, inv = np.unique(codes, return_inverse=True)
    ucol = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], -1).astype(np.float64) / 255.0
    umap = mono_grade(ucol, params, ink, paper)
    out8 = a8.copy()
    out8[..., :3][vis] = np.round(umap[inv.ravel()] * 255.0).astype(np.uint8)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out8, "RGBA").save(dst, optimize=False, compress_level=1)
    alpha = a8[..., 3].astype(np.float64) / 255.0
    h, w = alpha.shape
    fpx = [face_norm[0] * w, face_norm[1] * h, face_norm[2] * w, face_norm[3] * h]
    opaque = alpha >= 0.999
    step = max(1, int(np.sqrt(opaque.sum() / 600000)))
    sub = np.zeros_like(opaque)
    sub[::step, ::step] = opaque[::step, ::step]
    mp_ = mono_mapping_check(a8[..., :3], out8[..., :3], sub, params, ink, paper)
    face, _ = skin_mask(a8[..., :3].astype(np.float64) / 255.0, alpha, fpx)
    fmap = mono_mapping_check(a8[..., :3], out8[..., :3], face, params, ink, paper)
    lm = {"ok": False, "reason": "non richiesto"}
    if landmarks:
        lm = landmarks_shift(a8, out8, fpx)
        if lm.get("ok"):
            # soglia del rilevatore: togliere SOLO il colore (grigio = luma, nessuna curva) sposta già i landmark di MediaPipe
            # (con un volto di tre quarti, ~2 % della distanza tra gli occhi). Si misura anche grigio → mono (effetto della
            # sola curva): il livello è «pass» se colore → mono ≤ 2 %, oppure ≤ 4 % con la sola curva ≤ 2 %.
            g8 = a8.copy()
            g8[..., :3] = np.round(luma(a8[..., :3].astype(np.float64) / 255.0)[..., None] * 255).astype(np.uint8)
            lg = landmarks_shift(a8, g8, fpx)
            lc = landmarks_shift(g8, out8, fpx)
            lm["grey_baseline"] = lg.get("mean")
            lm["curve_only"] = lc.get("mean")
            if lm["level"] == "warn" and lc.get("ok") and lc["mean"] <= LM_SHIFT_WARN:
                lm["level"] = "pass"
                lm["note"] = "sopra il 2 % come già il solo grigio (rumore del rilevatore sul colore tolto); la curva da sola ≤ 2 %"
    tones = person_tones(out8[..., :3].astype(np.float64) / 255.0, alpha, fpx)
    ok = bool(mp_.get("pass")) and bool(fmap.get("pass", True)) and (not lm.get("ok") or lm.get("level") != "error")
    return {"mode": "mono", "level": "2b", "curve_id": params.get("id"), "signature": mono_signature(params, tokens),
            "uniform": "una funzione colore→colore (curva mono) applicata a tutti i pixel visibili, volto compreso",
            "mapping": {k: mp_.get(k) for k in ("px", "max_dev_levels", "p999_dev_levels", "bin_resid_p99_max", "pass")},
            "face_mapping": {k: fmap.get(k) for k in ("px", "max_dev_levels", "pass")},
            "curve": mp_.get("curve"), "landmarks": lm, "tones": tones, "pass": ok,
            "src": str(src), "out": str(dst)}


def tone_cutout(src: Path, dst: Path, mode: str, face_norm: list[float], tokens: dict, brand_dir: Path | None = None,
                strength: float | None = None, gate: tuple[float, float] = SKIN_GATE, margin: float = 0.92,
                mono: dict | None = None) -> dict:
    """Livello 2: applica il look (`look` | `duo`) a tutto il ritaglio, con la stessa forza ovunque (uniforme), e misura
    il ΔE00 sulla pelle del volto (α = 1). Senza `strength` la forza è la massima che resta sotto `gate`×`margin`.
    I pixel del ritaglio passano solo per una LUT 3D (funzione colore→colore): nessuna operazione locale, nessuna
    modifica di geometria. L'alpha non cambia. `mode` "mono" = livello 2b (tone_mono, parametri `mono`)."""
    from PIL import Image

    if mode == "mono":
        return tone_mono(src, dst, face_norm, tokens, mono or mono_params(tokens, brand_dir))
    im = Image.open(src).convert("RGBA")
    a8 = np.asarray(im, np.uint8)
    rgb = a8[..., :3].astype(np.float64) / 255.0
    alpha = a8[..., 3].astype(np.float64) / 255.0
    h, w = alpha.shape
    fpx = [face_norm[0] * w, face_norm[1] * h, face_norm[2] * w, face_norm[3] * h]
    face, skin = skin_mask(rgb, alpha, fpx)
    sel = skin if skin.sum() >= 400 else face
    ink, paper = brand_colors(tokens)
    if mode == "duo":
        lut = make_lut(lambda x: brand_look(x, ink, paper, contrast=0.42, desat=0.62, toe=0.6, shoulder=0.3))
    elif mode == "look":
        lut = brand_lut(tokens, brand_dir)
    else:
        raise ValueError(f"tone mode sconosciuto: {mode}")
    px = rgb[sel]
    px = px[::max(1, len(px) // 250000)]                     # misura finale: fino a 250k pixel di pelle (passo regolare)
    full = apply_lut(px, lut)
    step = max(1, len(px) // 30000)                         # ricerca della forza: campione di ~30k pixel
    pxs, fulls = px[::step], full[::step]

    def stats(s, all_px=False):
        if all_px:
            return _de_stats(px, px + s * (full - px))
        return _de_stats(pxs, pxs + s * (fulls - pxs))

    auto = strength is None
    if auto:
        lo, hi = 0.0, 1.0
        m, p = stats(1.0)
        if m <= gate[0] * margin and p <= gate[1] * margin:
            lo = 1.0
        else:
            for _ in range(14):
                mid = (lo + hi) / 2
                m, p = stats(mid)
                if m <= gate[0] * margin and p <= gate[1] * margin:
                    lo = mid
                else:
                    hi = mid
        strength = round(lo, 3)
    m, p = stats(strength, all_px=True)
    while (m > gate[0] or p > gate[1]) and strength > 0 and auto:   # il campione può sottostimare di poco: ricontrolla
        strength = round(max(0.0, strength - 0.02), 3)
        m, p = stats(strength, all_px=True)
    # applicazione: la LUT è una funzione colore→colore, quindi basta calcolarla sui colori distinti (8 bit) dei pixel visibili
    vis = a8[..., 3] > 0
    px8 = a8[..., :3][vis].astype(np.uint32)
    codes = (px8[:, 0] << 16) | (px8[:, 1] << 8) | px8[:, 2]
    uniq, inv = np.unique(codes, return_inverse=True)
    ucol = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], -1).astype(np.float64) / 255.0
    umap = np.clip(ucol + strength * (apply_lut(ucol, lut) - ucol), 0, 1)
    out8 = a8.copy()
    out8[..., :3][vis] = np.round(umap[inv.ravel()] * 255.0).astype(np.uint8)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out8, "RGBA").save(dst, optimize=False, compress_level=1)
    fstep = max(1, int(face.sum()) // 250000)
    fm, fp = _de_stats(rgb[face][::fstep], out8[..., :3][face][::fstep].astype(np.float64) / 255.0)
    return {"mode": mode, "strength": strength, "skin_px": int(sel.sum()), "skin_px_measured": int(len(px)), "skin_is_band": bool(skin.sum() >= 400),
            "skin_de00_mean": round(m, 2), "skin_de00_p95": round(p, 2), "face_de00_mean": round(fm, 2), "face_de00_p95": round(fp, 2),
            "gate": {"mean": gate[0], "p95": gate[1]}, "pass": bool(m <= gate[0] + 1e-6 and p <= gate[1] + 1e-6),
            "src": str(src), "out": str(dst), "uniform": "LUT 3D applicata a tutti i pixel con la stessa forza"}


# ── Plate ───────────────────────────────────────────────────────────────────
def disc_blur(rgb: np.ndarray, radius: float) -> np.ndarray:
    """Bokeh semplice: convoluzione con un disco (FFT), a metà risoluzione se il raggio è grande."""
    from scipy.signal import fftconvolve
    from PIL import Image

    if radius < 0.8:
        return rgb
    h, w = rgb.shape[:2]
    k = 2 if radius >= 6 else 1
    work = rgb
    if k > 1:
        work = np.asarray(Image.fromarray((rgb * 255).astype(np.uint8)).resize((w // k, h // k), Image.LANCZOS), np.float64) / 255
    r = radius / k
    n = int(np.ceil(r))
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    disc = np.clip(r + 0.5 - np.hypot(xx, yy), 0, 1)
    disc /= disc.sum()
    pad = n + 1
    p = np.pad(work, ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    out = np.stack([fftconvolve(p[..., c], disc, mode="same") for c in range(3)], -1)[pad:-pad, pad:-pad]
    out = np.clip(out, 0, 1)
    if k > 1:
        out = np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize((w, h), Image.LANCZOS), np.float64) / 255
    return out


def grade_plate(src: Path, dst: Path, mode: str, tokens: dict, brand_dir: Path | None = None, bokeh: float = 0.0,
                ev: float = 0.0, contrast: float | None = None, max_w: int = 3840, crop: list[float] | None = None,
                vignette: float = 0.0, mono_p: dict | None = None, flip: bool = False) -> dict:
    """Plate (livello 1, nessun pixel di persona): `mono` (duotono inchiostro→carta, alto contrasto), `mono-2b` (la STESSA
    curva mono delle persone, livello 2b: esposizione `ev` prima della curva), `look`, `none`; prima il bokeh (raggio in
    px della plate), dopo la vignetta verso l'inchiostro. `crop` = [x,y,w,h] in px della sorgente; `flip` = specchio
    orizzontale (un muro senza scritte: per spostare un giunto da dietro il titolo)."""
    from PIL import Image

    im = Image.open(src).convert("RGB")
    if crop:
        x, y, w, h = [int(round(v)) for v in crop]
        im = im.crop((x, y, x + w, y + h))
    if bokeh >= 4:
        # plate sfocata: metà risoluzione basta (Chrome la ingrandisce, il bokeh non ha dettaglio da perdere)
        max_w = min(max_w, 1920)
        bokeh = bokeh * min(1.0, max_w / im.width)
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    rgb = np.asarray(im, np.float32) / 255.0
    ink, paper = brand_colors(tokens)
    sig = None
    if bokeh:
        rgb = disc_blur(rgb, bokeh)
    if mode == "mono-2b":
        mp_ = mono_p or mono_params(tokens, brand_dir)
        rgb = mono_grade(rgb, mp_, ink, paper, pre_ev=ev)
        sig = mono_signature(mp_, tokens)
    elif mode == "mono":
        rgb = mono(rgb, ink, paper, contrast=0.55 if contrast is None else contrast, ev=ev)
    elif mode == "look":
        rgb = apply_lut(rgb, brand_lut(tokens, brand_dir))
        if ev:
            rgb = np.clip(rgb * 2.0 ** ev, 0, 1)
    elif mode in ("none", None):
        if ev:
            rgb = np.clip(rgb * 2.0 ** ev, 0, 1)
    else:
        raise ValueError(f"grade della plate sconosciuto: {mode}")
    if vignette:
        h, w = rgb.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
        v = (np.clip((d - 0.35) / 0.65, 0, 1) ** 1.6 * vignette)[..., None]
        rgb = rgb * (1 - v) + ink * v
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out = Image.fromarray(np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8), "RGB")
    if dst.suffix.lower() in (".jpg", ".jpeg"):
        out.save(dst, quality=94, subsampling=0)
    else:
        out.save(dst)
    return {"src": str(src), "out": str(dst), "mode": mode, "bokeh_px": bokeh, "ev": ev, "vignette": vignette,
            "size": [out.width, out.height], "crop": crop, "flip": flip, "signature": sig}


def scene_frame(video: str, t: float, dst: Path, ffmpeg: str = "ffmpeg") -> Path:
    """Frame della sorgente al tempo t (ricerca veloce + esatta), sRGB 8 bit. Per il pop-out del template scena."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-v", "error", "-y", "-ss", f"{max(0.0, t - 1.0):.3f}", "-i", str(video), "-ss", "1.0" if t >= 1.0 else f"{t:.3f}",
           "-frames:v", "1", "-vf", "scale=in_range=tv:out_range=pc:in_color_matrix=bt709,format=rgb24", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dst.exists():
        raise RuntimeError(f"ffmpeg: frame a {t}s non estratto: {proc.stderr[-400:]}")
    return dst


# ── Controlli sul PNG reso ──────────────────────────────────────────────────
def lap_var(g: np.ndarray) -> float:
    g = g.astype(np.float64)
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def served_detail(render, face_css: list[float], css_w: int = 1280, css_h: int = 720, served_w: int = 720) -> dict:
    """Dettaglio del volto nel file che YouTube serve (720×405, Lanczos): varianza del Laplaciano sul box del volto
    (soglie calibrate su 66 thumbnail di podcast di riferimento: mediana 1.046, p25 713, p10 569)."""
    from PIL import Image

    im = render if isinstance(render, Image.Image) else Image.open(render)
    H2 = round(served_w * 9 / 16)
    small = im.convert("RGB").resize((served_w, H2), Image.LANCZOS)
    x, y, w, h = face_css
    k = served_w / css_w
    box = (int(max(0, x * k)), int(max(0, y * k)), int(min(served_w, (x + w) * k)), int(min(H2, (y + h) * k)))
    c = small.crop(box).convert("L")
    return {"served_w": served_w, "face_px": c.height, "lap": round(lap_var(np.asarray(c)), 1)}


def face_surround_dL(render_rgb: np.ndarray, face_css: list[float], text_rects: list, css_w: int = 1280, css_h: int = 720,
                     person: np.ndarray | None = None) -> float | None:
    """Stacco volto–intorno (ΔL*), metodo R3: render a 320×180, media L* del volto (centro del box)
    contro la mediana di due bande ai lati della testa all'altezza del volto, senza le righe di testo."""
    from PIL import Image

    im = np.asarray(Image.fromarray(render_rgb).resize((320, 180), Image.BILINEAR), np.float64)
    L = rgb_to_lab(im / 255.0)
    x, y, w, h = face_css[0] / css_w, face_css[1] / css_h, face_css[2] / css_w, face_css[3] / css_h
    face = L[int((y + h * .15) * 180):int((y + h * .9) * 180), int((x + w * .2) * 320):int((x + w * .8) * 320)].reshape(-1, 3)
    if not len(face):
        return None
    y0, y1 = int(max(0, y - h * 0.3) * 180), int(min(1, y + h) * 180)
    xl0, xl1 = int(max(0, x - w * 0.9) * 320), int(max(0, x - w * 0.15) * 320)
    xr0, xr1 = int(min(1, x + w * 1.15) * 320), int(min(1, x + w * 1.9) * 320)
    sides = []
    for (a0, a1) in ((xl0, xl1), (xr0, xr1)):
        m = np.zeros((180, 320), bool)
        m[y0:y1, a0:a1] = True
        for (bx, by, bw, bh) in text_rects or []:
            m[int(by / css_h * 180):int((by + bh) / css_h * 180) + 1, int(bx / css_w * 320):int((bx + bw) / css_w * 320) + 1] = False
        if person is not None and (m & ~person).sum() >= 10:
            m &= ~person                                      # l'intorno è il fondo, non i capelli/l'orecchio della persona stessa
        if m.sum() >= 10:
            # per pixel: quanta parte dell'intorno si discosta dal tono del volto (mediana di |ΔL*|), non |mediana − volto|:
            # una banda metà cerchio chiaro e metà fondo scuro ha la mediana sul tono del volto ma stacca su entrambe le metà
            sides.append(float(np.median(np.abs(L[m][:, 0] - face.mean(0)[0]))))
    if not sides:
        return None
    # Media dello stacco lato per lato, ogni lato = mediana per pixel di |L* − L* del volto| (con `person` = maschera delle
    # persone a 320×180, i loro pixel escono dalle bande se ne resta abbastanza). Il metodo R3 (|mediana delle due bande −
    # volto|) con un lato scuro (plate) e uno chiaro (cerchio d'accento) cade sul tono del volto: un volto a L* 55 tra un
    # cerchio a L* 82 e una plate a L* ~20 darebbe ΔL* < 1 pur staccando da entrambi.
    return round(float(np.mean(sides)), 1)


def face_surround_sides(render_rgb: np.ndarray, face_css: list[float], text_rects: list, css_w: int = 1280, css_h: int = 720,
                        person: np.ndarray | None = None) -> dict | None:
    """Stacco volto–intorno lato per lato (sinistra, destra) e col metodo R3 (mediana delle due bande insieme), per il sidecar."""
    from PIL import Image
    im = np.asarray(Image.fromarray(render_rgb).resize((320, 180), Image.BILINEAR), np.float64)
    L = rgb_to_lab(im / 255.0)[..., 0]
    x, y, w, h = face_css[0] / css_w, face_css[1] / css_h, face_css[2] / css_w, face_css[3] / css_h
    fL = L[int((y + h * .15) * 180):int((y + h * .9) * 180), int((x + w * .2) * 320):int((x + w * .8) * 320)]
    if not fL.size:
        return None
    y0, y1 = int(max(0, y - h * 0.3) * 180), int(min(1, y + h) * 180)
    bands = {"left": (int(max(0, x - w * 0.9) * 320), int(max(0, x - w * 0.15) * 320)),
             "right": (int(min(1, x + w * 1.15) * 320), int(min(1, x + w * 1.9) * 320))}
    out, union = {"face_L": round(float(fL.mean()), 1)}, np.zeros((180, 320), bool)
    for k, (a0, a1) in bands.items():
        m = np.zeros((180, 320), bool)
        m[y0:y1, a0:a1] = True
        for (bx, by, bw, bh) in text_rects or []:
            m[int(by / css_h * 180):int((by + bh) / css_h * 180) + 1, int(bx / css_w * 320):int((bx + bw) / css_w * 320) + 1] = False
        union |= m
        if person is not None and (m & ~person).sum() >= 10:
            m &= ~person
        if m.sum() >= 10:
            out[f"{k}_L"] = round(float(np.median(L[m])), 1)
            out[f"{k}_dL"] = round(float(np.median(np.abs(L[m] - out["face_L"]))), 1)
    if union.sum() >= 20:
        out["r3_union_dL"] = round(abs(out["face_L"] - float(np.median(L[union]))), 1)
    return out


def hero_alpha_on_canvas(cut_alpha: np.ndarray, rect_css: list[float], W: int, H: int, css_w: int = 1280) -> np.ndarray:
    """Alpha del ritaglio ricampionato sulla griglia W×H del canvas (rect in px CSS)."""
    from PIL import Image

    k = W / css_w
    L, T, Wd, Hd = [v * k for v in rect_css]
    out = np.zeros((H, W), np.float64)
    tw, th = max(1, int(round(Wd))), max(1, int(round(Hd)))
    a = np.asarray(Image.fromarray((cut_alpha * 255).astype(np.uint8)).resize((tw, th), Image.BILINEAR), np.float64) / 255
    x0, y0 = int(round(L)), int(round(T))
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    dx1, dy1 = min(W, x0 + tw), min(H, y0 + th)
    if dx1 > dx0 and dy1 > dy0:
        out[dy0:dy1, dx0:dx1] = a[sy0:sy0 + (dy1 - dy0), sx0:sx0 + (dx1 - dx0)]
    return out


def silhouette_dL(render_rgb: np.ndarray, alphas: list[tuple[np.ndarray, list[float]]], tile_w: int = 246) -> float | None:
    """Stacco della sagoma alla tile da `tile_w` px (stesso metodo di yt-thumb-qa silhouette_dL): |ΔL*| medio tra ogni pixel appena fuori dalla
    sagoma e la media dei pixel appena dentro (finestra 5×5), esclusi i bordi del canvas."""
    from PIL import Image
    from scipy import ndimage

    H = round(tile_w * 9 / 16)
    small = np.asarray(Image.fromarray(render_rgb).resize((tile_w, H), Image.LANCZOS), np.float64) / 255
    L = rgb_to_lab(small)[..., 0]
    m = np.zeros((H, tile_w), bool)
    for a, rect in alphas:
        m |= hero_alpha_on_canvas(a, rect, tile_w, H) > 0.5
    if m.sum() < 20:
        return None
    inner = m & ~ndimage.binary_erosion(m, iterations=1)
    outer = ndimage.binary_dilation(m, iterations=1) & ~m
    outer[:2, :] = outer[-2:, :] = outer[:, :2] = outer[:, -2:] = False
    num = ndimage.uniform_filter(L * inner, 5)
    den = ndimage.uniform_filter(inner.astype(float), 5)
    ok = outer & (den > 1e-3)
    if ok.sum() < 10:
        return None
    return round(float(np.abs(L[ok] - num[ok] / den[ok]).mean()), 1)


def _canvas_L(render_rgb: np.ndarray, W: int = 1280, H: int = 720) -> np.ndarray:
    from PIL import Image
    im = np.asarray(Image.fromarray(render_rgb).resize((W, H), Image.LANCZOS), np.float64) / 255.0
    return rgb_to_lab(im)[..., 0]


def _people_alpha(heroes: list[dict], mh: list[dict], W: int = 1280, H: int = 720) -> list[np.ndarray]:
    from PIL import Image
    out = []
    for i, h in enumerate(heroes):
        if i >= len(mh):
            break
        a = np.asarray(Image.open(h["path"]).getchannel("A"), np.float64) / 255.0
        out.append(hero_alpha_on_canvas(a, mh[i]["rect"], W, H))
    return out


def disc_contrast(render_rgb: np.ndarray, deco: dict, heroes: list[dict], mh: list[dict], tokens: dict) -> dict:
    """Cerchio d'accento dietro una persona, misurato sul render (1280×720): ΔL* tra il cerchio appena fuori dalla sagoma
    (2–5 px) e la persona appena dentro (2–5 px) nella zona della testa (capelli/volto adiacenti), e ΔL* volto ↔ cerchio."""
    from scipy import ndimage
    L = _canvas_L(render_rgb)
    H, W = L.shape
    yy, xx = np.mgrid[0:H, 0:W]
    disc = np.hypot(xx - deco["cx"], yy - deco["cy"]) <= deco["r"] - 1
    alphas = _people_alpha(heroes, mh)
    res = {"kind": deco.get("kind"), "share": round(float(disc.mean()), 3)}
    best = None
    for i, A in enumerate(alphas):
        P = A > 0.5
        f = mh[i]["face"]
        head = np.zeros_like(P)
        head[int(max(0, f[1] - 0.9 * f[3])):int(min(H, f[1] + 1.15 * f[3])), int(max(0, f[0] - 0.6 * f[2])):int(min(W, f[0] + 1.6 * f[2]))] = True
        outer = ndimage.binary_dilation(P, iterations=5) & ~ndimage.binary_dilation(P, iterations=2) & disc & head
        if outer.sum() < 30:
            continue
        inner = ndimage.binary_erosion(P, iterations=2) & ~ndimage.binary_erosion(P, iterations=5) & head & ndimage.binary_dilation(outer, iterations=6)
        if inner.sum() < 30:
            continue
        fc = L[int(f[1] + 0.2 * f[3]):int(f[1] + 0.85 * f[3]), int(f[0] + 0.2 * f[2]):int(f[0] + 0.8 * f[2])]
        far = disc & ~ndimage.binary_dilation(P, iterations=30)          # colore del disco lontano dall'ombra portata
        r = {"person": Path(heroes[i]["path"]).name, "pairs": int(outer.sum()), "disc_L_edge": round(float(np.median(L[outer])), 1),
             "disc_L": round(float(np.median(L[far])), 1) if far.sum() > 50 else None,
             "edge_L": round(float(np.median(L[inner])), 1), "face_L": round(float(np.median(fc)), 1) if fc.size else None}
        # stacco al bordo: cerchio appena fuori (con l'ombra portata della persona, come si vede) ↔ persona appena dentro
        r["dL_edge"] = round(abs(r["disc_L_edge"] - r["edge_L"]), 1)
        dl = r["disc_L"] if r["disc_L"] is not None else r["disc_L_edge"]
        r["dL_face"] = round(abs(dl - r["face_L"]), 1) if r["face_L"] is not None else None
        if best is None or r["pairs"] > best["pairs"]:
            best = r
    if best:
        res.update(best)
    return res


def bright_masses(render_rgb: np.ndarray, heroes: list[dict], mh: list[dict], metrics: dict, discs: list[dict], tokens: dict) -> dict:
    """Masse chiare del render (1280×720): L* mediano e p90 del busto visibile di ogni persona (sotto il mento, fuori dai
    testi) e quota del canvas; riferimento = il cerchio d'accento se c'è, altrimenti il titolo (carta)."""
    L = _canvas_L(render_rgb)
    H, W = L.shape
    alphas = _people_alpha(heroes, mh)
    text = np.zeros((H, W), bool)
    for t in metrics.get("texts", []):
        for (x, y, w, h) in t.get("rects", []):
            text[int(max(0, y)):int(min(H, y + h + 1)), int(max(0, x)):int(min(W, x + w + 1))] = True
    col = (tokens or {}).get("colors", {})
    out = {"people": []}
    acc_hex = next((d.get("color") for d in discs if d.get("color")), None)
    if acc_hex:
        out["ref"], out["ref_L"] = "il cerchio d'accento", round(float(rgb_to_lab(hex_rgb(acc_hex))[0]), 1)
    else:
        out["ref"], out["ref_L"] = "il titolo (carta)", round(float(rgb_to_lab(hex_rgb(col.get("paper", "#f4f1ea")))[0]), 1)
    for i, A in enumerate(alphas):
        f = mh[i]["face"]
        m = (A > 0.95) & ~text
        m[:int(min(H, f[1] + 1.35 * f[3])), :] = False
        if m.sum() < 200:
            continue
        out["people"].append({"cutout": Path(heroes[i]["path"]).name, "role": heroes[i].get("role"), "torso_share": round(float(m.mean()), 3),
                              "torso_L": round(float(np.median(L[m])), 1), "torso_L_p90": round(float(np.percentile(L[m], 90)), 1)})
    return out


def matte_holes(cut_alpha: np.ndarray, face_norm: list[float]) -> dict:
    """Buchi del matte nel volto: pixel con α < 0.5 RACCHIUSI dalla sagoma (buchi topologici, non lo sfondo
    davanti a un profilo) più il loro bordo morbido, dentro il box del volto allargato del 10%. Un buco mostra lo sfondo,
    o l'alone/contorno, attraverso il volto: es. la lente degli occhiali."""
    from scipy import ndimage

    h, w = cut_alpha.shape
    x, y, fw, fh = face_norm[0] * w, face_norm[1] * h, face_norm[2] * w, face_norm[3] * h
    x0, y0 = int(max(0, x - 0.1 * fw)), int(max(0, y - 0.1 * fh))
    x1, y1 = int(min(w, x + 1.1 * fw)), int(min(h, y + 1.1 * fh))
    solid = cut_alpha >= 0.5
    filled = ndimage.binary_fill_holes(solid)
    # buco = α < 0.5 racchiuso dalla sagoma, più il suo bordo morbido (2 px, α < 0.9). Il bordo morbido ESTERNO della
    # sagoma (0.5 ≤ α < 0.9 lungo capelli e guance) non è un buco: contarlo darebbe 1–2,5 % su quasi ogni ritaglio.
    core = filled & ~solid
    grow = ndimage.binary_dilation(core, iterations=2) & filled & (cut_alpha < 0.9) if core.any() else core
    sub = (core | grow)[y0:y1, x0:x1]
    face = filled[y0:y1, x0:x1]
    n = int(face.sum())
    holes = int(sub.sum())
    lab, k = ndimage.label(sub)
    big = int(max(np.bincount(lab.ravel())[1:], default=0)) if k else 0
    return {"face_px": n, "hole_px": holes, "hole_frac": round(holes / max(1, n), 5), "largest_hole_px": big, "holes": int(k)}


def changed_pixels(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> dict:
    """Pixel diversi (qualunque canale) tra due render sulla maschera."""
    d = np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).max(-1)
    dm = d[mask]
    return {"px": int(mask.sum()), "changed": int((dm > 0).sum()), "changed_gt1": int((dm > 1).sum()), "max": int(dm.max()) if dm.size else 0}


# ── CLI: rigenera le LUT del brand ──────────────────────────────────────────
def _brand_dir_cli(argv: list[str]) -> Path:
    """Cartella del brand per la CLI: --dir DIR esplicita, altrimenti --brand SLUG (default demo) cercato nei brands_dirs
    dell'operatore e poi in assets/brands del plugin (lib/config.py, solo stdlib)."""
    if "--dir" in argv:
        return Path(argv[argv.index("--dir") + 1]).expanduser().resolve()
    brand = argv[argv.index("--brand") + 1] if "--brand" in argv else "demo"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import config as _config  # noqa: PLC0415
        bd = _config.brand_dir(brand, _config.settings())
        if bd:
            return Path(bd)
    except Exception:  # noqa: BLE001 — configurazione assente o illeggibile: si resta sul plugin
        pass
    return Path(__file__).resolve().parent.parent / "assets" / "brands" / brand


def _main(argv: list[str]) -> int:
    if len(argv) >= 1 and argv[0] in ("lut", "mono-lut"):
        bdir = _brand_dir_cli(argv)
        if not (bdir / "tokens.json").is_file():
            print(f"tokens.json non trovato in {bdir}", file=sys.stderr)
            return 2
        tokens = json.loads((bdir / "tokens.json").read_text())
        brand = tokens.get("slug") or bdir.name
        ink, paper = brand_colors(tokens)
        if argv[0] == "lut":
            lut = make_lut(lambda x: brand_look(x, ink, paper))
            out = bdir / LOOK_FILE
            write_cube(out, lut, f"{brand}-look", [
                f"Generata da lib/thumb_fx.py (python3 lib/thumb_fx.py lut --brand {brand}) a partire da tokens.json.",
                "Curva + contrasto sul luma (s-curve c=0.30), neri verso l'inchiostro, alte luci verso la carta.",
                "Nessun aumento di saturazione. Sui ritagli delle persone: livello 2 della policy v2,",
                "forza regolata da yt-thumb-render per restare sotto ΔE00 pelle media 2.5 / p95 5."])
            print(json.dumps({"ok": True, "lut": str(out), "size": LUT_SIZE}))
            return 0
        p = mono_params(tokens, bdir)
        lut = make_lut(lambda x: mono_grade(x, p, ink, paper))
        out = bdir / MONO_CUBE
        write_cube(out, lut, f"{brand}-mono ({p['id']})", [
            f"Generata da lib/thumb_fx.py (python3 lib/thumb_fx.py mono-lut --brand {brand}) da {MONO_FILE} + tokens.json.",
            "Livello 2b: luma Rec.709 → curva monotona (PCHIP) → rampa inchiostro→carta. La stessa su persone e plate.",
            f"Firma della funzione: {mono_signature(p, tokens)}. Il render usa la curva esatta (non questa LUT a 33 punti)."])
        print(json.dumps({"ok": True, "lut": str(out), "size": LUT_SIZE, "curve": p["id"], "signature": mono_signature(p, tokens)}))
        return 0
    print("uso: thumb_fx.py lut [--brand SLUG | --dir DIR] | mono-lut [--brand SLUG | --dir DIR]   (default --brand demo)",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
