"""yt-thumb-qa — foglio QA, controlli v2 e mock della griglia YouTube per thumbnail candidate.

Per ogni immagine:
  - <stem>_qa.png, il foglio (thumbnail v2):
      riga 1, pagina scura #0f0f0f con il badge della durata: 720×405 (il file servito `hq720`, griglia e ricerca
        desktop a 2×), 500 (ricerca, surfaces.json), 360 (`hq720` a 1×), 216 (sidebar vera, surfaces.json) e 168
        (prova di stress: è la misura del file dichiarato, non una tile dipinta). Tutte le tile ≤ 720 derivano dal
        file servito, non dal master: render → 720×405 (Lanczos) → tile;
      riga 2, pagina chiara: 216 e 168 chiare, 360 chiara, scala di grigi (contrasto di valore), sfocata (squint);
      riga 3, la catena del file servito: render → 720×405 → 1180×664 (telefono: 393 px CSS × 3), con i volti nel
        file da 720 e a 1180 px e il pannello dei controlli (volto, dettaglio, stacco, righe, salienza);
  - controlli (JSON `checks`, livelli error / warn / pass / info / skip), soglie della revisione critica dello studio
    thumbnail v2 (07 §12.4, calibrate su 66 thumbnail di podcast di riferimento in inglese):
      face_size        volto principale ≥ 35 % dell'altezza sui template claim (errore; < 40 % avviso; con sorgente
                       still errore < 40 %); duo: ogni volto ≥ 30 % e ospite ≥ host (errore);
      face_surround    ΔL* volto–intorno (metodo R3): errore < 10, avviso < 20; se l'intorno sta a cavallo del volto (≥ 20 % dei
                       pixel più chiari di 10 e ≥ 20 % più scuri, es. cerchio d'accento chiaro + plate scura) mediana per pixel di |ΔL*|;
      phrase_line_h    ogni riga della frase ≥ 12 % dell'altezza; keyword_line_h la parola chiave ≥ 18 % (errore; avviso
                       se il titolo è a un solo corpo, cioè la parola chiave non è più grande della frase, come in
                       yt-thumb-render; senza OCR: rettangoli d'inchiostro del sidecar <stem>.render.json, ripiego
                       sull'overlay debug);
      served_detail    varianza del Laplaciano del volto nel render ridotto a 720×405 (Lanczos): avviso < 713 (p25 EN),
                       errore < 569 (p10 EN);
      silhouette_246   stacco |ΔL*| della sagoma a 246 px: solo avviso < 25 (non calibrato);
      saliency_first   salienza di Apple Vision (thumbvision saliency, se c'è): volto o titolo per primo? (info);
      hook_words       3–6 parole (meno di 3 errore, più di 6 avviso); duo 3–4 parole (più di 4 errore) e ogni riga
                       del titolo ≥ 20 % dell'altezza (07 §7.7);
      edge_dL_dark     stacco del bordo della tile dalla pagina scura #0f0f0f: avviso < 25 ΔL*, salvo un elemento chiaro
                       di cornice (tratto continuo del bordo ≥ 10 % del perimetro a ≥ 40 ΔL* dalla pagina: cerchio
                       d'accento, disco carta); edge_dL_light dalla pagina chiara: avviso < 20;
      circle_contrast  cerchio d'accento dietro una persona ↔ capelli/volto adiacenti: errore < 10 ΔL*, avviso < 20, con
                       il ΔL* che darebbero gli altri accenti del brand (scelta dell'accento sul mono);
      livello 2b       (grade monocromatico uniforme, `grade: mono`) grade_uniform: una sola
                       curva L*(render) = f(luma del ritaglio al livello 0) su tutti i pixel opachi delle persone (residuo
                       p95, scarto tra le curve delle persone e tra volto e resto); grade_face: ogni volto segue la curva
                       comune (niente ritocchi locali né deformazioni); grade_mono: persone e plate senza colore;
                       grade_landmarks: 478 landmark MediaPipe invariati tra livello 0 e render (spostamento medio ÷
                       distanza tra gli occhi); skin_de00 (ΔE00 della pelle del livello 2) saltato SOLO col mono;
      text_contrast_168, display_upscale: avvisi; render_checks: errori del sidecar di yt-thumb-render;
    i controlli bloccano (codice di uscita ≠ 0) solo sui render con sidecar (--gate auto); sulle altre immagini (audit
    dei canali, competitor) gli errori scendono ad avvisi;
  - <stem>_grid.png (con --grid DIR): la candidata in una griglia 3×3 con le thumbnail dei competitor, tema scuro e
    chiaro affiancati, titoli finti (o il titolo vero con --title);
  - <stem>_100.png: ritagli al 100% del master (volti e bordi dritti dei ritagli dentro il canvas, 07 §11);
  - <stem>_qa.json: controlli, esito e metriche dell'immagine (li registra yt-thumb-learn ingest per l'apprendimento);
    con --grid auto la griglia usa i riferimenti di nicchia del canale (<studio>/data/refs/<canale>/grid).
Le metriche non decidono da sole il gusto: l'agente guarda i PNG e compila la rubrica (knowledge 07-thumbnails).
Superfici: data/surfaces.json, Engaged Views, CC BY 4.0 (adattato; vedi docs/yt/vendor/NOTICE.md §10).
"""
from __future__ import annotations

import argparse
import json
import re
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps  # noqa: E402

DARK, LIGHT = (15, 15, 15), (255, 255, 255)
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
FONT_FILE = yc.FONTS / "Inter[opsz,wght].ttf"
SURFACES_FILE = Path(__file__).resolve().parent.parent / "data" / "surfaces.json"

# ── Soglie v2 (07 §12.4; calibrate su 66 thumbnail di podcast di riferimento) ─
FACE_CLAIM_ERR, FACE_CLAIM_WARN = 0.35, 0.40   # 57 riferimenti su 66 passano il 35 %
FACE_STILL_ERR = 0.40                          # sorgente still: niente scuse di risoluzione
FACE_DUO_ERR = 0.30                            # duo: ogni volto
SURROUND_ERR, SURROUND_WARN = 10.0, 20.0       # p10 dei riferimenti 10,1; p25 20,7
PHRASE_LINE_MIN, KEYWORD_LINE_MIN = 0.12, 0.18  # p10 EN della riga più grande 12,8 %
SERVED_W, SERVED_H = 720, 405                  # file più grande servito sul web (hq720)
DETAIL_WARN, DETAIL_ERR = 713.0, 569.0         # p25 / p10 EN del Laplaciano del volto a 720×405
SIL_W, SIL_WARN = 246, 25.0                    # una sola misura: solo avviso
PHONE_W, PHONE_H = 1180, 664                   # 393 px CSS × 3 (feed del telefono)
EDGE_DL_MIN = 20.0                             # ΔL* bordo tile ↔ pagina chiara: avviso (riferimenti tra 16 e 34)
EDGE_DL_DARK_MIN = 25.0                        # ΔL* bordo tile ↔ pagina scura #0f0f0f: avviso sotto 25 (un ritratto su
                                               # campo scuro sta a ~13; con un cerchio d'accento al bordo ~22 ma passa)
EDGE_LIGHT_DL = 40.0                           # un tratto di bordo è «chiaro» se dista ≥ 40 ΔL* dalla pagina scura
EDGE_LIGHT_RUN = 0.10                          # elemento chiaro di cornice: tratto continuo ≥ 10 % del perimetro
                                               # (un cerchio al bordo ~20 %; un ritratto su campo scuro ~3 %)
TEXT_CONTRAST_168_MIN = 3.0
DISPLAY_CAP = 2.0                              # tetto (c): ≤ 2,0× della risoluzione effettiva a 1280 (ripiego b: 1,5×)
DUO_LINE_MIN = 0.20                            # duo: ogni riga del titolo ≥ 20 % (obiettivo 22 %)
DUO_WORDS_MAX = 4                              # duo: 3–4 parole (regola generale 3–6)
HOOK_WORDS_MIN, HOOK_WORDS_MAX = 3, 6

# Livello 2b (opzione `grade: mono`): grade monocromatico uniforme su tutta la foto (persone e plate).
# Soglie calibrate su render simulati con ritagli reali (tests/test_thumb_qa.py, sezione «2b», ora su ritagli sintetici).
GRADE_MONO = {"mono", "monocromatico", "monochrome", "2b"}
GRADE_RES_WARN, GRADE_RES_ERR = 2.5, 5.0       # p95 |ΔL*| dei pixel delle persone dalla curva unica stimata
                                               # (render pulito 0,2–0,3; grana σ 4/255 sopra le persone 3,0)
GRADE_GAP_WARN, GRADE_GAP_ERR = 1.0, 2.0       # scarto medio tra curve: persona ↔ persona, volto ↔ resto (ΔL*); pulito
                                               # ≤ 0,07; contrasto 0,35 vs 0,65 = 2,8; −¼ EV = 7,2; volto +10 % = 3,0
MONO_CHROMA_MAX = 12.0                         # C*ab p95 di persone e plate: il duotono inchiostro→carta sta sotto ~7
SRC_CHROMA_MIN = 8.0                           # C*ab mediano del volto nel livello 0: sotto è già graduato (o una foto
                                               # in bianco e nero): la curva non si può verificare (pelle vera ≥ 15)
FACE_RES_WARN, FACE_RES_ERR = 2.5, 5.0         # p95 |ΔL*| dei pixel del volto dalla curva comune: pulito 0,2–0,4; grana σ 4/255
                                               # 3,1; volto schiarito del 10 % 6,3; bocca deformata del 6 % 9,9
LM_WARN, LM_ERR = 0.02, 0.04                   # spostamento medio dei 478 landmark MediaPipe ÷ distanza tra gli angoli degli
                                               # occhi (come thumb_fx.tone_mono): rumore colore→mono 0,8–2,0 %, bocca
                                               # deformata del 12 % 3,3–4,0 %; tra 2 e 4 % passa se la sola curva
                                               # (grigio → render) resta ≤ 2 %: il resto è il rilevatore sul colore tolto
BS_WARN = 0.35                                 # |Δ| dei blendshape chiave: rumoroso sui volti morbidi (0,26 su un volto pulito
                                               # del campo largo), solo avviso
CIRCLE_ERR, CIRCLE_WARN = 10.0, 20.0           # ΔL* cerchio d'accento ↔ capelli/volto adiacenti (come face_surround)
CIRCLE_MIN_SHARE = 0.015                       # sotto l'1,5 % del canvas non c'è un cerchio


def _demo_accents() -> dict:
    """Accenti del brand neutro del plugin (assets/brands/demo/tokens.json): ripiego quando il sidecar non porta la palette."""
    try:
        t = json.loads((yc.BRANDS / getattr(yc, "BUILTIN_BRAND", "demo") / "tokens.json").read_text())
        c = t.get("colors") or {}
        names = [n for n in (t.get("accents") or [t.get("accent")]) if n in c]
        return {n: c[n] for n in names}
    except Exception:  # noqa: BLE001
        return {"accent": "#ff5a2c", "accent_2": "#35d49a", "accent_3": "#ffcd3c"}


ACCENT_HEX = _demo_accents()                    # nome → hex; il sidecar del render (palette) vince

BUILTIN_TEMPLATES = {"duo", "ritratto", "scena", "prova", "generic"}
CLAIM_TEMPLATES = {"ritratto", "scena", "prova"}
FACE_REQUIRED = {"ritratto", "scena", "duo"}
DUO_TEMPLATES = {"duo"}
CLAIM_LEVERS = {"claim", "name"}
HOOK_KINDS = {"hook", "phrase", "headline", "keyword", "highlight", "hook_keyword"}
PHRASE_KINDS = {"hook", "phrase", "headline"}
KEYWORD_KINDS = {"keyword", "highlight", "hook_keyword"}
LEVELS = ("error", "warn", "pass", "info", "skip")
LEVEL_RGB = {"error": (235, 72, 60), "warn": (242, 182, 40), "pass": (84, 200, 120), "info": (150, 150, 150),
             "skip": (105, 105, 105)}


# ── Superfici (Engaged Views, CC BY 4.0) ─────────────────────────────────────
def load_surfaces(path: Path = SURFACES_FILE) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — il foglio funziona anche senza il file vendorizzato
        return {}


def surface_size(surfaces: dict, name: str, viewport: str = "1280", default: tuple = (0, 0)) -> tuple[int, int]:
    try:
        w, h = surfaces["surfaces"][name]["viewports"][viewport]
        return int(round(w)), int(round(h))
    except (KeyError, TypeError, ValueError):
        return default


# ── Font e disegno ──────────────────────────────────────────────────────────
def font(size: int, weight: int = 500) -> ImageFont.FreeTypeFont:
    try:
        f = ImageFont.truetype(str(FONT_FILE), size)
        try:
            axes = f.get_variation_axes()
            vals = [max(a["minimum"], min(a["maximum"], weight if "eight" in str(a.get("name", "")) else (size if "ptical" in str(a.get("name", "")) else a["default"]))) for a in axes]
            f.set_variation_by_axes(vals)
        except Exception:
            pass
        return f
    except OSError:
        return ImageFont.load_default()


def fit_thumb(im: Image.Image, w: int, h: int) -> Image.Image:
    """Ridimensionamento di qualità (come un browser che scala la miniatura); crop centrale se cambia il formato."""
    if abs(im.width / im.height - w / h) > 0.01:
        tw = min(im.width, round(im.height * w / h))
        th = min(im.height, round(im.width * h / w))
        left, top = (im.width - tw) // 2, (im.height - th) // 2
        im = im.crop((left, top, left + tw, top + th))
    return im.resize((w, h), Image.LANCZOS, reducing_gap=3.0)


def duration_badge(tile: Image.Image, text: str = "52:58") -> Image.Image:
    """Badge della durata in basso a destra, in proporzione alla griglia desktop (48×20 a 347 px)."""
    t = tile.copy()
    s = t.width / 347
    bw, bh, m = int(48 * s), int(20 * s), int(8 * s)
    d = ImageDraw.Draw(t, "RGBA")
    box = (t.width - m - bw, t.height - m - bh, t.width - m, t.height - m)
    d.rounded_rectangle(box, radius=max(2, int(4 * s)), fill=(0, 0, 0, 205))
    f = font(max(7, int(12 * s)), 600)
    tw = d.textlength(text, font=f)
    d.text((box[0] + (bw - tw) / 2, box[1] + bh / 2), text, font=f, fill=(255, 255, 255), anchor="lm")
    return t


def rounded(tile: Image.Image, r: int) -> Image.Image:
    mask = Image.new("L", tile.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), radius=r, fill=255)
    out = Image.new("RGBA", tile.size)
    out.paste(tile.convert("RGBA"), mask=mask)
    return out


def wrap(d: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


# ── Metriche ────────────────────────────────────────────────────────────────
def rel_lum(rgb: np.ndarray) -> np.ndarray:
    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def region_contrast(im: Image.Image, box: tuple[float, float, float, float]) -> dict | None:
    """Contrasto WCAG tra gli estremi robusti di luminanza (p5 vs p95) dentro il box (frazioni 0–1).

    Su una riga di testo gli estremi sono il tratto delle lettere e il fondo immediato (o il riquadro
    evidenziato): misura quanto il gancio si stacca, anche dopo il ridimensionamento a 168 px.
    """
    W, H = im.size
    x, y, w, h = box
    crop = im.crop((int(x * W), int(y * H), max(int(x * W) + 1, int((x + w) * W)), max(int(y * H) + 1, int((y + h) * H))))
    if crop.width < 3 or crop.height < 3:
        return None
    L = rel_lum(np.asarray(crop.convert("RGB"))).ravel()
    lo, hi = float(np.percentile(L, 5)), float(np.percentile(L, 95))
    return {"ratio": round((hi + 0.05) / (lo + 0.05), 2)}


def edge_density(im: Image.Image, thr: float = 48.0) -> tuple[float, np.ndarray]:
    g = np.asarray(im.convert("L"), dtype=np.float64)
    gx = np.zeros_like(g); gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1, :] = g[2:, :] - g[:-2, :]
    mag = np.hypot(gx, gy)
    return float((mag > thr).mean()), mag > thr


def srgb_to_L(rgb: np.ndarray) -> np.ndarray:
    """L* CIELAB (D65) da sRGB 0–255."""
    Y = rel_lum(rgb)
    return np.where(Y > 216 / 24389, 116 * np.cbrt(Y) - 16, Y * 24389 / 27)


PAGE_L = {"dark": float(srgb_to_L(np.array([[15, 15, 15]], float))[0]), "light": 100.0}


def edge_separation(tile: Image.Image, band: int = 6) -> dict:
    """L* medio della cornice di `band` px della tile (360 px) e stacco dalla pagina scura (#0f0f0f) e chiara."""
    a = np.asarray(tile.convert("RGB"), np.float64)
    m = np.zeros(a.shape[:2], bool)
    m[:band] = m[-band:] = True
    m[:, :band] = m[:, -band:] = True
    L = srgb_to_L(a[m])
    out = {"edge_L_mean": round(float(L.mean()), 1)}
    for k, pl in PAGE_L.items():
        d = np.abs(L - pl)
        out[f"edge_dL_{k}"] = round(float(d.mean()), 1)
        out[f"edge_dL_{k}_p25"] = round(float(np.percentile(d, 25)), 1)   # il tratto di cornice più mimetizzato
    # elemento chiaro di cornice (cerchio d'accento, disco carta, maglia chiara che tocca il bordo): profilo di L* lungo
    # il perimetro (media sulla profondità della cornice), in senso orario; tratto continuo più lungo ≥ 40 ΔL* dalla
    # pagina scura, come quota del perimetro
    La = srgb_to_L(a)
    prof = np.concatenate([La[:band, :].mean(0), La[:, -band:].mean(1), La[-band:, ::-1].mean(0), La[::-1, :band].mean(1)])
    light = (prof - PAGE_L["dark"]) >= EDGE_LIGHT_DL
    out["edge_light_share"] = round(float(light.mean()), 3)
    out["edge_light_run"] = round(longest_circular_run(light) / max(1, len(light)), 3)
    return out


def longest_circular_run(b: np.ndarray) -> int:
    """Lunghezza del tratto continuo più lungo di True in un profilo chiuso (il perimetro della tile)."""
    b = np.asarray(b, bool)
    if b.all():
        return int(len(b))
    if not b.any():
        return 0
    k = int(np.argmin(b))                      # ruota il profilo perché inizi con un False: niente tratti spezzati
    r = np.concatenate([np.roll(b, -k), [False]]).astype(np.int8)
    d = np.diff(np.concatenate([[0], r]))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    return int((ends - starts).max()) if len(starts) else 0


def colorfulness(tile: Image.Image) -> float:
    """Hasler–Süsstrunk M (0 = grigio; ~66 mediana dei podcast di riferimento)."""
    a = np.asarray(tile.convert("RGB"), np.float64)
    rg = a[..., 0] - a[..., 1]
    yb = 0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]
    return round(float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())), 1)


def metrics_for(im: Image.Image, text_boxes: list) -> dict:
    m: dict = {}
    small360 = fit_thumb(im, 360, 202)
    small168 = fit_thumb(im, 168, 94)
    ed360, e360 = edge_density(small360)
    m["edge_density_360"] = round(ed360, 4)
    m["edge_density_168"] = round(edge_density(small168)[0], 4)
    # Concentrazione: quota di celle (4×4) con densità sopra la media → più bassa = un punto focale.
    h, w = e360.shape
    cells = [e360[i * h // 4:(i + 1) * h // 4, j * w // 4:(j + 1) * w // 4].mean() for i in range(4) for j in range(4)]
    m["busy_cells_share"] = round(float(np.mean(np.array(cells) > np.mean(cells))), 3)
    # Zona del timestamp (230×110 su 1280×720): quanto è "occupata".
    m["timestamp_zone_edge_density"] = round(float(e360[int(h * (1 - 110 / 720)):, int(w * (1 - 230 / 1280)):].mean()), 4)
    g = np.asarray(small360.convert("L"), dtype=np.float64)
    m["luma_mean"] = round(float(g.mean()), 1)
    m["luma_rms_contrast"] = round(float(g.std()), 1)
    m.update(edge_separation(small360))
    m["colorfulness_360"] = colorfulness(small360)
    if text_boxes:
        res = []
        for b in text_boxes:
            full = region_contrast(im, b)
            small = region_contrast(small168, b)
            res.append({"box": [round(v, 4) for v in b], "contrast": full and full["ratio"],
                        "contrast_168": small and small["ratio"]})
        m["text"] = res
        m["text_contrast_min"] = min((r["contrast"] or 0) for r in res)
        m["text_contrast_168_min"] = min((r["contrast_168"] or 0) for r in res)
    return m


def lap_var(g: np.ndarray) -> float:
    """Varianza del Laplaciano a 4 vicini (stessa formula di thumb_fx.lap_var)."""
    g = g.astype(np.float64)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def face_surround_dL(im: Image.Image, box, text_boxes=()) -> float | None:
    """ΔL* tra il volto e l'intorno (metodo R3, scripts_R3/sep.py): immagine a 320×180; volto = parte centrale del box
    (20–80 % in larghezza, 15–90 % in altezza), media di L*; intorno = due fasce ai lati della testa (da 0,15 a 0,9
    larghezze di volto fuori dal box, dall'altezza della fronte − 0,3 al mento), meno i box del testo; mediana di L*."""
    W, H = 320, 180
    a = np.asarray(im.convert("RGB").resize((W, H), Image.BILINEAR), np.float64)
    L = srgb_to_L(a)
    x, y, w, h = box
    face = L[int((y + h * .15) * H):int((y + h * .9) * H), int((x + w * .2) * W):int((x + w * .8) * W)]
    if face.size == 0:
        return None
    mask = np.zeros((H, W), bool)
    y0, y1 = int(max(0, y - h * 0.3) * H), int(min(1, y + h) * H)
    xl0, xl1 = int(max(0, x - w * 0.9) * W), int(max(0, x - w * 0.15) * W)
    xr0, xr1 = int(min(1, x + w * 1.15) * W), int(min(1, x + w * 1.9) * W)
    mask[y0:y1, xl0:xl1] = True
    mask[y0:y1, xr0:xr1] = True
    for (bx, by, bw, bh) in text_boxes or ():
        mask[max(0, int(by * H)):max(0, int((by + bh) * H) + 1), max(0, int(bx * W)):max(0, int((bx + bw) * W) + 1)] = False
    if mask.sum() < 20:
        return None
    return round(abs(float(face.mean()) - float(np.median(L[mask]))), 1)


STRADDLE_DL, STRADDLE_SHARE = 10.0, 0.20       # intorno «a cavallo» del volto: ≥ 20 % dei pixel più chiari di 10 E ≥ 20 % più scuri


def face_surround_detail(im: Image.Image, box, text_boxes=(), person: np.ndarray | None = None) -> dict | None:
    """Stacco volto–intorno con il metodo R3 (`face_surround_dL`, il valore di riferimento) e, quando l'intorno sta «a cavallo»
    del tono del volto, la mediana per pixel di |ΔL*|.

    Il metodo R3 confronta il volto con la MEDIANA delle due bande insieme: se una parte dell'intorno è molto più chiara
    (cerchio d'accento chiaro, L* ≈ 82) e un'altra molto più scura (plate, L* ≈ 20), la mediana cade sul tono del volto
    (L* ≈ 55) e il volto risulta «senza stacco» anche se stacca da entrambi (un duo con cerchio chiaro e plate scura: R3 < 1). In quel caso — almeno il 20 % dei pixel dell'intorno più chiari del volto di ≥ 10 e almeno
    il 20 % più scuri di ≥ 10 — il valore è la mediana per pixel di |L* − L* del volto| (come `thumb_fx.face_surround_dL`
    di yt-thumb-render). Negli altri casi resta R3: stessa calibrazione e stessi numeri di prima.
    `person` = maschera delle persone (1280×720, 0–1, da `person_mask`): i pixel delle persone escono dall'intorno se ne
    restano almeno 20 (le bande non devono misurare i capelli o l'orecchio della persona stessa)."""
    W, H = 320, 180
    a = np.asarray(im.convert("RGB").resize((W, H), Image.BILINEAR), np.float64)
    L = srgb_to_L(a)
    x, y, w, h = box
    face = L[int((y + h * .15) * H):int((y + h * .9) * H), int((x + w * .2) * W):int((x + w * .8) * W)]
    if face.size == 0:
        return None
    mask = np.zeros((H, W), bool)
    y0, y1 = int(max(0, y - h * 0.3) * H), int(min(1, y + h) * H)
    xl0, xl1 = int(max(0, x - w * 0.9) * W), int(max(0, x - w * 0.15) * W)
    xr0, xr1 = int(min(1, x + w * 1.15) * W), int(min(1, x + w * 1.9) * W)
    mask[y0:y1, xl0:xl1] = True
    mask[y0:y1, xr0:xr1] = True
    for (bx, by, bw, bh) in text_boxes or ():
        mask[max(0, int(by * H)):max(0, int((by + bh) * H) + 1), max(0, int(bx * W)):max(0, int((bx + bw) * W) + 1)] = False
    if mask.sum() < 20:
        return None
    fL = float(face.mean())
    r3 = round(abs(fL - float(np.median(L[mask]))), 1)
    out = {"face_L": round(fL, 1), "r3": r3, "value": r3, "method": "r3", "straddle": False}
    m = mask
    if person is not None:
        p = np.asarray(Image.fromarray((np.clip(person, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR),
                       np.float64) / 255 > 0.5
        if (mask & ~p).sum() >= 20:
            m = mask & ~p
            out["person_excluded"] = int((mask & p).sum())
    d = L[m] - fL
    hi, lo = float((d >= STRADDLE_DL).mean()), float((d <= -STRADDLE_DL).mean())
    out.update({"brighter_share": round(hi, 3), "darker_share": round(lo, 3), "surround_L_p10_p90":
                [round(float(np.percentile(L[m], 10)), 1), round(float(np.percentile(L[m], 90)), 1)]})
    if hi >= STRADDLE_SHARE and lo >= STRADDLE_SHARE:
        out.update({"straddle": True, "method": "per_pixel", "value": round(float(np.median(np.abs(d))), 1)})
    return out


def served_file(im1280: Image.Image) -> Image.Image:
    """Il file che YouTube serve sul web (hq720): render → 720×405, Lanczos (calibrazione della revisione critica)."""
    return im1280.convert("RGB").resize((SERVED_W, SERVED_H), Image.LANCZOS)


def served_detail(served: Image.Image, box) -> tuple[float | None, int]:
    """Varianza del Laplaciano sul box del volto nel file servito (senza riportare il volto a una misura comune)."""
    W2, H2 = served.size
    x, y, w, h = box
    c = served.crop((max(0, int(x * W2)), max(0, int(y * H2)), min(W2, int((x + w) * W2)), min(H2, int((y + h) * H2)))).convert("L")
    if c.width < 3 or c.height < 3:
        return None, c.height
    return round(lap_var(np.asarray(c)), 1), c.height


def _erode(m: np.ndarray, it: int = 1) -> np.ndarray:
    for _ in range(it):   # croce 3×3, bordo = vuoto (come scipy.ndimage.binary_erosion)
        p = np.pad(m, 1, constant_values=False)
        m = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m


def _dilate(m: np.ndarray, it: int = 1) -> np.ndarray:
    for _ in range(it):
        p = np.pad(m, 1, constant_values=False)
        m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return m


def silhouette_dL(im1280: Image.Image, mask: np.ndarray, width: int = SIL_W) -> float | None:
    """Stacco della sagoma alla misura di display: fascia di 2 px dentro e 2 px fuori dalla sagoma
    alla larghezza `width`; per ogni pixel esterno il pixel interno più vicino; media di |ΔL*|."""
    h = round(width * 9 / 16)
    m8 = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8)).resize((width, h), Image.LANCZOS)
    m = np.asarray(m8, np.float64) / 255 > 0.5
    inner = m & ~_erode(m, 2)
    outer = _dilate(m, 2) & ~m
    if inner.sum() < 5 or outer.sum() < 5:
        return None
    L = srgb_to_L(np.asarray(im1280.convert("RGB").resize((width, h), Image.LANCZOS), np.float64))
    iy, ix = np.nonzero(inner)
    oy, ox = np.nonzero(outer)
    near = np.empty(len(oy), int)
    for s in range(0, len(oy), 512):
        d = (oy[s:s + 512, None] - iy[None]) ** 2 + (ox[s:s + 512, None] - ix[None]) ** 2
        near[s:s + 512] = d.argmin(1)
    return round(float(np.abs(L[oy, ox] - L[iy[near], ix[near]]).mean()), 1)


def person_mask(data: dict, size: tuple[int, int] = (1280, 720)) -> np.ndarray | None:
    """Maschera delle persone nel canvas 1280×720: alpha dei ritagli (spec.people[i].path) posati nei rettangoli
    misurati dal renderer (metrics.heroes[i].rect, px CSS). Oppure metrics.person_mask (PNG) se il renderer la scrive."""
    met = data.get("metrics") or {}
    pm = met.get("person_mask")
    if pm and Path(pm).exists():
        a = Image.open(pm)
        a = a.getchannel("A") if a.mode in ("RGBA", "LA") else a.convert("L")
        return np.asarray(a.resize(size, Image.LANCZOS), np.float64) / 255
    people = ((data.get("spec") or {}).get("people")) or []
    heroes = met.get("heroes") or []
    if not people or not heroes:
        return None
    canvas = np.zeros((size[1], size[0]), np.float64)
    kx, ky = size[0] / 1280, size[1] / 720
    used = 0
    for p, hm in zip(people, heroes):
        path = (p or {}).get("path")
        rect = hm.get("rect")
        if not path or not rect or not Path(path).exists():
            continue
        L, T, W, H = rect
        w, h = max(1, int(round(W * kx))), max(1, int(round(H * ky)))
        im = Image.open(path)
        a = im.getchannel("A") if im.mode in ("RGBA", "LA") else im.convert("RGBA").getchannel("A")
        layer = Image.new("L", size, 0)
        layer.paste(a.resize((w, h), Image.LANCZOS), (int(round(L * kx)), int(round(T * ky))))
        canvas = np.maximum(canvas, np.asarray(layer, np.float64) / 255)
        used += 1
    return canvas if used else None


# ── Livello 2b: grade monocromatico uniforme (07 §11.2) ──────────────────────
def rgb_to_lab(rgb01: np.ndarray) -> np.ndarray:
    """sRGB 0–1 (…,3) → CIELAB D65 (stessa formula di thumb_fx.rgb_to_lab)."""
    c = np.clip(rgb01, 0, 1)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def hex_lab(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return rgb_to_lab(np.array([[int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]]))[0]


def declared_grade(data: dict) -> str | None:
    """Grade dichiarato del concept: `spec.grade` ("mono" | "none" | {mode: …}), oppure v2.grade / checks_v2.grade del
    sidecar; `guest_style: "mono"` è letto come sinonimo. Il grade della sola plate (`plate.grade`) non conta: lì il
    mono è un'operazione di sfondo, non il livello 2b."""
    spec = data.get("spec") or {}
    for g in (spec.get("grade"), (data.get("v2") or {}).get("grade"), (data.get("checks_v2") or {}).get("grade")):
        if isinstance(g, dict):
            g = g.get("mode") or g.get("kind")
        if isinstance(g, str) and g.strip():
            g = g.strip().lower()
            return "mono" if g in GRADE_MONO else g
    if str(spec.get("guest_style") or "").strip().lower() in GRADE_MONO:
        return "mono"
    heroes = (data.get("metrics") or {}).get("heroes") or []
    if any(str((t or {}).get("mode")).lower() in GRADE_MONO or str((t or {}).get("level")) == "2b"
           for t in _tone_records(data, max(len(heroes), len((data.get("checks_v2") or {}).get("heroes") or [])))):
        return "mono"                                  # il renderer ha applicato il 2b anche se il concept non lo dice
    return None


def level0_path(person: dict, tone: dict | None = None) -> str | None:
    """Il ritaglio al livello 0 (prima del grade): `source_path` della persona se il renderer lo scrive, poi il `src`
    del record del tono (thumb_fx.tone_mono / tone_cutout), infine `path`."""
    cands = [(person or {}).get(k) for k in ("source_path", "path_level0", "level0_path", "orig_path")]
    cands.append((tone or {}).get("src"))
    cands.append((person or {}).get("path"))
    for v in cands:
        if v and Path(v).exists():
            return str(v)
    return None


def _tone_records(data: dict, n: int) -> list[dict | None]:
    """Record del tono per persona: checks_v2.heroes[i].tone, altrimenti v2.tone[i]."""
    out: list[dict | None] = [None] * n
    for src in (((data.get("checks_v2") or {}).get("heroes") or []), [{"tone": t} for t in ((data.get("v2") or {}).get("tone") or [])]):
        for i, h in enumerate(src[:n]):
            t = (h or {}).get("tone")
            if out[i] is None and isinstance(t, dict):
                out[i] = t
    return out


def luma_variants(rgb01: np.ndarray) -> dict[str, np.ndarray]:
    """Le conversioni in grigio più comuni (il grade può usarne una qualsiasi: la curva si stima su ognuna)."""
    return {"rec709": rgb01 @ np.array([0.2126, 0.7152, 0.0722]),
            "rec601": rgb01 @ np.array([0.299, 0.587, 0.114]),
            "lstar": rgb_to_lab(rgb01)[..., 0] / 100.0}


def fit_tone_curve(x: np.ndarray, y: np.ndarray, bins: int = 96, min_px: int = 30) -> dict:
    """Curva di tono y = f(x) stimata come mediana per classe di x (0–1), interpolata linearmente tra i centri."""
    x = np.clip(np.asarray(x, np.float64), 0, 1)
    y = np.asarray(y, np.float64)
    idx = np.minimum((x * bins).astype(int), bins - 1)
    order = np.argsort(idx, kind="stable")
    cnt = np.bincount(idx, minlength=bins)
    med = np.full(bins, np.nan)
    for b, chunk in enumerate(np.split(y[order], np.cumsum(cnt)[:-1])):
        if len(chunk) >= min_px:
            med[b] = np.median(chunk)
    centers = (np.arange(bins) + 0.5) / bins
    ok = ~np.isnan(med)
    if ok.sum() < 2:
        return {"ok": False, "centers": centers, "med": med, "cnt": cnt, "idx": idx, "pred": np.full_like(y, np.nan)}
    pred = np.interp(x, centers[ok], med[ok])
    return {"ok": True, "centers": centers, "med": med, "cnt": cnt, "idx": idx, "pred": pred}


def curve_gap(res: np.ndarray, idx: np.ndarray, a: np.ndarray, b: np.ndarray, bins: int = 96, min_px: int = 80) -> dict | None:
    """Scarto tra le curve di due gruppi di pixel (stessa persona o due persone): per ogni classe di x con ≥ min_px pixel
    in entrambi, differenza tra le mediane dei residui con segno dalla curva comune; media pesata e p90 tra le classi.
    Un ritocco locale (volto schiarito) o una curva diversa per una persona spostano un gruppo rispetto all'altro."""
    gaps, w = [], []
    for k in range(bins):
        ia, ib = a & (idx == k), b & (idx == k)
        na, nb = int(ia.sum()), int(ib.sum())
        if na >= min_px and nb >= min_px:
            gaps.append(abs(float(np.median(res[ia])) - float(np.median(res[ib]))))
            w.append(min(na, nb))
    if not gaps:
        return None
    g, w = np.array(gaps), np.array(w, np.float64)
    return {"mean": round(float((g * w).sum() / w.sum()), 2), "p90": round(float(np.percentile(g, 90)), 2), "bins": len(g)}


def _rect_mask(shape: tuple[int, int], rects, k: float, grow: int = 0) -> np.ndarray:
    H, W = shape
    m = np.zeros((H, W), bool)
    for r in rects or ():
        try:
            x, y, w, h = [float(v) * k for v in r]
        except (TypeError, ValueError):
            continue
        m[max(0, int(y) - grow):max(0, int(y + h) + 1 + grow), max(0, int(x) - grow):max(0, int(x + w) + 1 + grow)] = True
    return m


def _overlay_rects(data: dict) -> list:
    """Rettangoli (CSS 1280×720) di tutto ciò che il template disegna SOPRA le persone: testi (anche box del nome e
    della parola chiave), logo o wordmark, etichetta del conduttore. Escono dal confronto dei pixel."""
    met = data.get("metrics") or {}
    rects = [r for t in met.get("texts") or [] for r in (t.get("rects") or []) if isinstance(r, (list, tuple)) and len(r) == 4]
    sr = met.get("series") or {}
    for key in ("logo", "logos", "logo_rect", "wordmark", "wordmark_rect", "host_tag", "host_tag_rect", "overlays"):
        v = sr.get(key) if key in sr else met.get(key)
        if isinstance(v, dict):
            v = v.get("rect")
        if isinstance(v, (list, tuple)) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v):
            rects.append(v)
        elif isinstance(v, (list, tuple)):
            for r in v:
                r = r.get("rect") if isinstance(r, dict) else r
                if isinstance(r, (list, tuple)) and len(r) == 4 and all(isinstance(x, (int, float)) for x in r):
                    rects.append(r)
    for c in ((data.get("checks_v2") or {}).get("credentials") or []):
        if isinstance(c.get("rect"), (list, tuple)) and len(c["rect"]) == 4:
            rects.append(c["rect"])
    return rects


def person_layers(data: dict, size: tuple[int, int]) -> list[dict]:
    """Ritagli al livello 0 posati come nel render (rect di metrics.heroes in CSS × size/1280): RGBA, origine frazionaria,
    box del volto. Il template disegna i ritagli 1:1 a 3840; se la misura non torna, il ritaglio viene ridimensionato."""
    spec = data.get("spec") or {}
    people = spec.get("people") or []
    heroes = (data.get("metrics") or {}).get("heroes") or []
    W, H = size
    k = W / 1280
    roles = _people_roles(spec, len(heroes), data.get("template"))
    tones = _tone_records(data, len(heroes))
    out = []
    for i, hm in enumerate(heroes):
        p = (people[i] if i < len(people) else {}) or {}
        path = level0_path(p, tones[i])
        rect = hm.get("rect")
        if not path or not rect or len(rect) != 4:
            continue
        im = Image.open(path).convert("RGBA")
        tw, th = rect[2] * k, rect[3] * k
        resized = abs(im.width - tw) > max(2.0, 0.01 * tw) or abs(im.height - th) > max(2.0, 0.01 * th)
        if resized:
            im = im.resize((max(1, round(tw)), max(1, round(th))), Image.LANCZOS)
        f = hm.get("face")
        out.append({"i": i, "rgba": np.asarray(im), "x": rect[0] * k, "y": rect[1] * k, "role": roles[i] if i < len(roles) else None,
                    "name": p.get("name"), "path": path, "resized": bool(resized),
                    "face": [v * k for v in f] if f and len(f) == 4 else None})
    return out


def _window(ox: int, oy: int, w: int, h: int, W: int, H: int):
    x0, y0, x1, y1 = max(0, ox), max(0, oy), min(W, ox + w), min(H, oy + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return (y0, y1, x0, x1), (y0 - oy, y1 - oy, x0 - ox, x1 - ox)


def grade_samples(master: np.ndarray, layers: list[dict], exclude: np.ndarray, max_px: int = 400_000) -> list[dict]:
    """Coppie (colore del livello 0, colore nel render) sui pixel interni e opachi di ogni persona, con l'allineamento
    intero migliore attorno all'origine frazionaria (Chrome arrotonda la posizione al pixel del dispositivo)."""
    H, W = master.shape[:2]
    # pixel coperti da due persone: fuori (non si sa chi sta sopra)
    cover = np.zeros((H, W), np.uint8)
    for ly in layers:
        a = ly["rgba"][..., 3] > 5
        win = _window(int(round(ly["x"])), int(round(ly["y"])), a.shape[1], a.shape[0], W, H)
        if win:
            (y0, y1, x0, x1), (sy0, sy1, sx0, sx1) = win
            cover[y0:y1, x0:x1] += a[sy0:sy1, sx0:sx1]
    overlap = cover > 1
    out = []
    for ly in layers:
        rgba = ly["rgba"]
        src = rgba[..., :3].astype(np.float64) / 255.0
        inner = _erode(rgba[..., 3] >= 252, 3)
        best = None
        cands = {(int(np.floor(ly["x"])) + dx, int(np.floor(ly["y"])) + dy) for dx in (0, 1) for dy in (0, 1)}
        cands.add((int(round(ly["x"])), int(round(ly["y"]))))
        for ox, oy in sorted(cands):
            win = _window(ox, oy, rgba.shape[1], rgba.shape[0], W, H)
            if not win:
                continue
            (y0, y1, x0, x1), (sy0, sy1, sx0, sx1) = win
            m = inner[sy0:sy1, sx0:sx1] & ~exclude[y0:y1, x0:x1] & ~overlap[y0:y1, x0:x1]
            n = int(m.sum())
            if n < 500:
                continue
            step = max(1, int(np.sqrt(n / max_px)))
            mm = np.zeros_like(m)
            mm[::step, ::step] = m[::step, ::step]
            s = src[sy0:sy1, sx0:sx1][mm]
            r = master[y0:y1, x0:x1][mm].astype(np.float64) / 255.0
            ys = s @ np.array([0.2126, 0.7152, 0.0722])
            yr = r @ np.array([0.2126, 0.7152, 0.0722])
            q = ys[::max(1, len(ys) // 20000)], yr[::max(1, len(yr) // 20000)]
            c = float(np.corrcoef(q[0], q[1])[0, 1]) if len(q[0]) > 10 and q[0].std() > 0 and q[1].std() > 0 else -1.0
            if best is None or c > best["corr"]:
                yy, xx = np.nonzero(mm)
                X, Y = xx + x0, yy + y0                        # coordinate nel canvas
                fb = ly.get("face")
                if fb:
                    in_face = (X >= fb[0]) & (X < fb[0] + fb[2]) & (Y >= fb[1]) & (Y < fb[1] + fb[3])
                else:
                    in_face = np.zeros(len(yy), bool)
                best = {"corr": c, "offset": [ox, oy], "src": s, "ren": r, "face": in_face, "n_interior": n, "step": step}
        if best is None:
            continue
        best.update({"i": ly["i"], "role": ly.get("role"), "name": ly.get("name"), "resized": ly.get("resized")})
        out.append(best)
    return out


def grade_consistency(samples: list[dict]) -> dict:
    """Stessa curva di tono su tutti i pixel delle persone? Stima della curva unica L*(render) = f(luma del livello 0)
    sui pixel di tutte le persone insieme (la conversione in grigio che la spiega meglio), poi: residuo |ΔL*| (p50, p95),
    scarto tra le curve delle persone e tra volto e resto di ogni persona (ritocchi locali), croma del render (mono?),
    monotonia della curva, croma della sorgente (il livello 0 deve essere a colori)."""
    if not samples:
        return {"ok": False, "reason": "nessun pixel di persona confrontabile"}
    src = np.concatenate([s["src"] for s in samples])
    ren = np.concatenate([s["ren"] for s in samples])
    who = np.concatenate([np.full(len(s["src"]), j) for j, s in enumerate(samples)])
    face = np.concatenate([s["face"] for s in samples])
    lab_r = rgb_to_lab(ren)
    Lr = lab_r[..., 0]
    lab_s = rgb_to_lab(src)
    cs = np.hypot(lab_s[..., 1], lab_s[..., 2])
    src_chroma = float(np.median(cs[face])) if face.sum() >= 500 else float(np.median(cs))
    best = None
    for name, x in luma_variants(src).items():
        fit = fit_tone_curve(x, Lr)
        if not fit["ok"]:
            continue
        res = Lr - fit["pred"]
        p95 = float(np.percentile(np.abs(res), 95))
        if best is None or p95 < best["p95"]:
            best = {"luma": name, "fit": fit, "res": res, "p95": p95}
    if best is None:
        return {"ok": False, "reason": "curva non stimabile (pochi pixel)"}
    res, fit = best["res"], best["fit"]
    out = {"ok": True, "luma": best["luma"], "px": int(len(res)),
           "res_p50": round(float(np.percentile(np.abs(res), 50)), 2), "res_p95": round(best["p95"], 2),
           "chroma_p95": round(float(np.percentile(np.hypot(lab_r[..., 1], lab_r[..., 2]), 95)), 1),
           "src_face_chroma": round(src_chroma, 1), "people": []}
    med = fit["med"][~np.isnan(fit["med"])]
    cnt = fit["cnt"][~np.isnan(fit["med"])]
    drops = [float(med[j] - med[j + 1]) for j in range(len(med) - 1) if cnt[j] >= 200 and cnt[j + 1] >= 200 and med[j] - med[j + 1] > 2.0]
    out["monotonic"] = not drops
    out["max_drop"] = round(max(drops), 2) if drops else 0.0
    gaps = []
    for j, s in enumerate(samples):
        mine = who == j
        info = {"role": s.get("role"), "name": s.get("name"), "offset": s["offset"], "corr": round(s["corr"], 4), "px": int(mine.sum()),
                "res_p95": round(float(np.percentile(np.abs(res[mine]), 95)), 2), "resized": s.get("resized")}
        mf = mine & face
        info["face_px"] = int(mf.sum())
        info["face_res_p95"] = round(float(np.percentile(np.abs(res[mf]), 95)), 2) if mf.sum() >= 200 else None
        fg = curve_gap(res, fit["idx"], mine & face, mine & ~face)
        info["face_gap"] = fg
        out["people"].append(info)
    for j in range(len(samples)):
        for k in range(j + 1, len(samples)):
            g = curve_gap(res, fit["idx"], who == j, who == k)
            if g:
                gaps.append({"pair": [j, k], **g})
    out["people_gap"] = gaps
    return out


def palette_accents(data: dict | None) -> dict:
    """Accenti (nome → hex) del brand del render: palette del sidecar di yt-thumb-render, altrimenti il brand demo."""
    pal = ((data or {}).get("palette") or {}).get("accents")
    return dict(pal) if isinstance(pal, dict) and pal else dict(ACCENT_HEX)


def accent_hex(data: dict | None, accent: str | None) -> str | None:
    """Colore dell'accento: nome nella palette del brand (sidecar), oppure un hex esplicito."""
    if isinstance(accent, str) and accent.startswith("#"):
        return accent
    return palette_accents(data).get(str(accent or ""))


def plate_chroma(im1280: Image.Image, data: dict, accent: str | None) -> dict | None:
    """Croma della plate (tutto ciò che non è persona, testo o colore d'accento) nel canvas 1280×720: il mono del 2b vale
    anche per il fondo (la plate può in più essere scurita, sfocata, vignettata: operazioni di sfondo)."""
    mask = person_mask(data)
    a = np.asarray(im1280.convert("RGB"), np.float64) / 255.0
    lab = rgb_to_lab(a)
    keep = np.ones(a.shape[:2], bool)
    if mask is not None:
        keep &= ~_dilate(mask > 0.02, 6)
    keep &= ~_rect_mask(a.shape[:2], _overlay_rects(data), 1.0, grow=8)
    acc = accent_hex(data, accent)
    if acc:
        keep &= np.linalg.norm(lab - hex_lab(acc), axis=-1) >= 25
    if keep.sum() < 2000:
        return None
    C = np.hypot(lab[..., 1], lab[..., 2])[keep]
    return {"chroma_p95": round(float(np.percentile(C, 95)), 1), "px": int(keep.sum())}


# ── Landmark (livello 2b: geometria ed espressione invariate) ───────────────
KEY_BLENDSHAPES = ("mouthSmileLeft", "mouthSmileRight", "jawOpen", "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp",
                   "browDownLeft", "browDownRight", "mouthPressLeft", "mouthPressRight", "cheekSquintLeft", "cheekSquintRight",
                   "mouthFunnel", "mouthPucker")


def _face_crop_box(face, W: int, H: int, grow: float = 2.2) -> tuple[int, int, int, int]:
    x, y, w, h = face
    s = max(w, h) * grow
    cx, cy = x + w / 2, y + h / 2
    return int(max(0, cx - s / 2)), int(max(0, cy - s / 2)), int(min(W, cx + s / 2)), int(min(H, cy + s / 2))


def mediapipe_faces(crops: list[np.ndarray]) -> list[dict | None] | None:
    """478 landmark + blendshape di MediaPipe Face Landmarker (locale, `install.sh --with-mediapipe`) per ogni ritaglio
    RGB uint8; None se MediaPipe non è installato. Solo analisi: nessun pixel cambia, nessuna identificazione."""
    try:
        import expressions as ex  # noqa: PLC0415
        st = ex.mp_status(check_sha=False)
        if not st["ok"]:
            return None
        runner = ex.MPRunner(Path(st["model"]))
    except Exception:  # noqa: BLE001
        return None
    out = []
    try:
        for c in crops:
            if c is None or c.shape[0] < 32 or c.shape[1] < 32:
                out.append(None)
                continue
            res = runner.lm.detect(runner.mp.Image(image_format=runner.mp.ImageFormat.SRGB, data=np.ascontiguousarray(c[..., :3])))
            if not res.face_landmarks:
                out.append(None)
                continue
            pts = np.array([[p.x * c.shape[1], p.y * c.shape[0]] for p in res.face_landmarks[0]])
            bs = {b.category_name: float(b.score) for b in res.face_blendshapes[0]} if res.face_blendshapes else {}
            out.append({"pts": pts, "bs": bs})
    finally:
        runner.close()
    return out


def compare_landmarks(a: dict | None, b: dict | None) -> dict | None:
    """Spostamento dei landmark tra il livello 0 e il render (÷ distanza tra gli angoli esterni degli occhi, 33–263) e
    differenza dei blendshape chiave."""
    if not a or not b or len(a["pts"]) != len(b["pts"]):
        return None
    iod = float(np.linalg.norm(a["pts"][33] - a["pts"][263])) if len(a["pts"]) > 263 else 0.0
    if iod < 5:
        return None
    d = np.linalg.norm(a["pts"] - b["pts"], axis=1) / iod
    keys = [k for k in KEY_BLENDSHAPES if k in a["bs"] and k in b["bs"]]
    dbs = {k: round(abs(a["bs"][k] - b["bs"][k]), 3) for k in keys}
    worst = max(dbs, key=dbs.get) if dbs else None
    return {"mean": round(float(d.mean()), 4), "p95": round(float(np.percentile(d, 95)), 4), "iod_px": round(iod, 1),
            "bs_max": dbs.get(worst) if worst else None, "bs_worst": worst}


def landmarks_check_data(master: np.ndarray, layers: list[dict], samples: list[dict]) -> list[dict] | None:
    """Per ogni persona con un volto: lo stesso ritaglio del canvas dal render e dal livello 0 posato sopra il render
    (stesso fondo, stessa posizione: cambia solo il tono della persona); MediaPipe su entrambi."""
    H, W = master.shape[:2]
    crops, meta = [], []
    for ly in layers:
        s = next((s for s in samples if s["i"] == ly["i"]), None)
        if not ly.get("face") or s is None:
            continue
        ox, oy = s["offset"]
        x0, y0, x1, y1 = _face_crop_box(ly["face"], W, H)
        if x1 - x0 < 40 or y1 - y0 < 40:
            continue
        ren = master[y0:y1, x0:x1].copy()
        lv0 = ren.astype(np.float64)
        rgba = ly["rgba"]
        sy0, sx0 = y0 - oy, x0 - ox
        ys0, xs0 = max(0, sy0), max(0, sx0)
        ys1, xs1 = min(rgba.shape[0], sy0 + (y1 - y0)), min(rgba.shape[1], sx0 + (x1 - x0))
        if ys1 > ys0 and xs1 > xs0:
            part = rgba[ys0:ys1, xs0:xs1].astype(np.float64)
            al = part[..., 3:4] / 255.0
            ty, tx = ys0 - sy0, xs0 - sx0
            reg = lv0[ty:ty + part.shape[0], tx:tx + part.shape[1]]
            lv0[ty:ty + part.shape[0], tx:tx + part.shape[1]] = part[..., :3] * al + reg * (1 - al)
        grey = np.round(lv0 @ np.array([0.2126, 0.7152, 0.0722]))[..., None].repeat(3, -1)   # solo il colore tolto
        lv0 = np.clip(np.round(lv0), 0, 255).astype(np.uint8)
        grey = np.clip(grey, 0, 255).astype(np.uint8)
        side = max(ren.shape[:2])
        if side > 1024:                                   # stessa riduzione per i tre ritagli (velocità del landmarker)
            k = 1024 / side
            size = (max(1, round(ren.shape[1] * k)), max(1, round(ren.shape[0] * k)))
            ren, lv0, grey = (np.asarray(Image.fromarray(x).resize(size, Image.LANCZOS)) for x in (ren, lv0, grey))
        crops += [lv0, grey, ren]
        meta.append({"i": ly["i"], "role": ly.get("role"), "name": ly.get("name")})
    if not meta:
        return []
    faces = mediapipe_faces(crops)
    if faces is None:
        return None
    out = []
    for j, m in enumerate(meta):
        a, gr, b = faces[3 * j], faces[3 * j + 1], faces[3 * j + 2]
        cmp_ = compare_landmarks(a, b)                     # livello 0 a colori → render
        if cmp_:
            cg = compare_landmarks(gr, b)                  # grigio → render: l'effetto della sola curva
            cb = compare_landmarks(a, gr)                  # colore → grigio: il rumore del rilevatore
            cmp_["curve_only"] = cg["mean"] if cg else None
            cmp_["grey_baseline"] = cb["mean"] if cb else None
        m.update({"engine": "mediapipe", "found": [a is not None, b is not None], "cmp": cmp_})
        out.append(m)
    return out


def analyze_grade(src: Path, data: dict, im1280: Image.Image, with_landmarks: bool = True) -> dict:
    """Analisi completa del livello 2b su un render con sidecar: curva unica sulle persone, plate mono, landmark."""
    master_im = Image.open(src).convert("RGB")
    master = np.asarray(master_im, np.uint8)
    H, W = master.shape[:2]
    if not (data.get("metrics") or {}).get("heroes"):
        return {"ok": False, "soft": True, "reason": "il sidecar non ha la geometria dei ritagli (metrics.heroes: motore remotion o "
                "sidecar vecchio): verifica il grade a occhio sul foglio e nei ritagli al 100 %"}
    layers = person_layers(data, (W, H))
    if not layers:
        return {"ok": False, "reason": "ritagli del livello 0 non trovati (spec.people[].source_path o path nel sidecar)"}
    excl = _rect_mask((H, W), _overlay_rects(data), W / 1280, grow=int(round(12 * W / 3840)) + 2)
    samples = grade_samples(master, layers, excl)
    res = grade_consistency(samples)
    res["plate"] = plate_chroma(im1280, data, (data.get("spec") or {}).get("accent"))
    if with_landmarks and res.get("ok"):
        res["landmarks"] = landmarks_check_data(master, layers, samples)
    return res


# ── Cerchio d'accento dietro una persona ────────────────────────────────────
def circle_contrast(im1280: Image.Image, data: dict, faces: list[dict], accent: str | None = None) -> dict | None:
    """ΔL* tra il cerchio d'accento e i capelli/il volto adiacenti: coppie (2–5 px fuori dalla sagoma, sul cerchio) ↔
    (pixel interno più vicino, 2–5 px dentro), nella zona della testa di ogni volto. None se non c'è un cerchio."""
    spec = data.get("spec") or {}
    accent = accent or spec.get("accent")
    hexv = accent_hex(data, accent)
    mask = person_mask(data)
    if not hexv or mask is None:
        return None
    a = np.asarray(im1280.convert("RGB").resize((1280, 720), Image.LANCZOS), np.float64) / 255.0
    lab = rgb_to_lab(a)
    acc = np.linalg.norm(lab - hex_lab(hexv), axis=-1) < 18
    acc &= ~_rect_mask(acc.shape, _overlay_rects(data), 1.0, grow=10)
    share = float(acc.mean())
    if share < CIRCLE_MIN_SHARE:
        return None
    P = mask > 0.5
    outer = _dilate(P, 5) & ~_dilate(P, 2) & acc
    inner = _erode(P, 2) & ~_erode(P, 5)
    head = np.zeros_like(P)
    for f in faces or ():
        x, y, w, h = f["box"]
        head[max(0, int((y - 0.9 * h) * 720)):int(min(1, y + 1.15 * h) * 720),
             max(0, int((x - 0.6 * w) * 1280)):int(min(1, x + 1.6 * w) * 1280)] = True
    L = lab[..., 0]
    res = {"accent": accent, "circle_share": round(share, 3)}
    iy, ix = np.nonzero(inner)
    if len(iy) < 5:
        return res
    for label, sel in (("head", outer & head), ("all", outer)):
        oy, ox = np.nonzero(sel)
        if len(oy) < 30:
            res[f"pairs_{label}"] = int(len(oy))
            continue
        near = np.empty(len(oy), int)
        for s in range(0, len(oy), 256):
            d = (oy[s:s + 256, None] - iy[None]) ** 2 + (ox[s:s + 256, None] - ix[None]) ** 2
            near[s:s + 256] = d.argmin(1)
        Lin = L[iy[near], ix[near]]
        res[f"pairs_{label}"] = int(len(oy))
        res[f"dL_{label}"] = round(float(np.median(np.abs(L[oy, ox] - Lin))), 1)
        res[f"person_L_{label}"] = round(float(np.median(Lin)), 1)
    pl = res.get("person_L_head", res.get("person_L_all"))
    if pl is not None:
        res["alternatives"] = {k: round(abs(float(hex_lab(v)[0]) - pl), 1) for k, v in palette_accents(data).items()}
    return res


def parse_box(text: str) -> tuple[float, float, float, float]:
    v = [float(x) for x in text.split(",")]
    if len(v) != 4:
        raise ValueError("--text-box vuole x,y,w,h")
    if any(x > 1 for x in v):  # pixel nello spazio 1280×720
        v = [v[0] / 1280, v[1] / 720, v[2] / 1280, v[3] / 720]
    return tuple(v)  # type: ignore[return-value]


def _norm_rect(r) -> tuple[float, float, float, float] | None:
    try:
        x, y, w, h = [float(v) for v in r]
    except (TypeError, ValueError):
        return None
    return (max(0.0, x) / 1280, max(0.0, y) / 720, min(w, 1280 - x) / 1280, min(h, 720 - y) / 720)


def boxes_from_sidecar(img: Path, data: dict | None = None, kinds: set | None = HOOK_KINDS) -> list:
    """Rettangoli delle righe del gancio (frase + parola chiave) dal sidecar di yt-thumb-render (spazio CSS 1280×720).
    kinds=None → tutti i testi (badge, credenziale, meta compresi)."""
    if data is None:
        data = sidecar(img)
    out = []
    for t in (data.get("metrics") or {}).get("texts", []):
        if kinds is not None and (t.get("kind") or "hook") not in kinds:
            continue
        for r in t.get("rects", []):
            b = _norm_rect(r)
            if b and b[2] > 0 and b[3] > 0:
                out.append(b)
    return out


def sidecar(img: Path) -> dict:
    side = img.with_name(img.stem + ".render.json")
    try:
        return yc.read_json(side) if side.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


# ── Overlay debug (ripiego senza sidecar) ───────────────────────────────────
def _vertical_segments(mask: np.ndarray, gap: int = 12, min_len: int = 20) -> list[tuple[float, int, int]]:
    """Tratti verticali di un contorno tratteggiato: per colonna, run di pixel con buchi ≤ gap chiusi; colonne vicine
    con la stessa run diventano un tratto (x medio, y0, y1)."""
    H, W = mask.shape
    runs_by_col: dict[int, list[tuple[int, int]]] = {}
    for x in np.flatnonzero(mask.any(axis=0)):
        ys = np.flatnonzero(mask[:, x])
        runs, s, p = [], ys[0], ys[0]
        for y in ys[1:]:
            if y - p > gap + 1:
                runs.append((s, p + 1)); s = y
            p = y
        runs.append((s, p + 1))
        runs_by_col[int(x)] = [r for r in runs if r[1] - r[0] >= min_len]
    segs: list[dict] = []
    for x in sorted(runs_by_col):
        for (a, b) in runs_by_col[x]:
            hit = next((s for s in segs if s["x1"] >= x - 1 and abs(s["y0"] - a) <= 3 and abs(s["y1"] - b) <= 3), None)
            if hit:
                hit["x1"] = x
                hit["y0"], hit["y1"] = min(hit["y0"], a), max(hit["y1"], b)
            else:
                segs.append({"x0": x, "x1": x, "y0": a, "y1": b})
    return [((s["x0"] + s["x1"]) / 2, s["y0"], s["y1"]) for s in segs]


def rects_from_overlay(mask: np.ndarray, outline: int = 3) -> list[tuple[float, float, float, float]]:
    """Rettangoli (px dell'immagine) disegnati con un contorno tratteggiato di `outline` px fuori dal box (overlay
    debug di render_html.mjs). Tratti verticali con la stessa estensione = lati dello stesso box; un tratto che copre
    due box sovrapposti in colonna (bordi sinistri allineati) viene scartato."""
    segs = _vertical_segments(mask)
    spans = [(y0, y1) for _, y0, y1 in segs]
    keep = []
    for i, (x, y0, y1) in enumerate(segs):
        inside = [j for j, (a, b) in enumerate(spans) if j != i and a >= y0 - 3 and b <= y1 + 3 and (b - a) < (y1 - y0) - 6]
        if len(inside) >= 2:
            continue                                   # unione di due lati sinistri allineati
        keep.append((x, y0, y1))
    groups: list[dict] = []
    for x, y0, y1 in keep:
        g = next((g for g in groups if abs(g["y0"] - y0) <= 3 and abs(g["y1"] - y1) <= 3), None)
        if g:
            g["xs"].append(x)
        else:
            groups.append({"y0": y0, "y1": y1, "xs": [x]})
    out = []
    for g in groups:
        x0, x1 = min(g["xs"]), max(g["xs"])
        out.append((x0 + 1, g["y0"] + outline, max(0.0, x1 - x0 - 2), max(0.0, g["y1"] - g["y0"] - 2 * outline)))
    return sorted(out, key=lambda r: (r[1], r[0]))


def overlay_boxes(debug_png: Path) -> dict:
    """Box del testo (magenta) e dei volti (ciano) dall'overlay <stem>_debug.png (1280×720, scala CSS)."""
    im = Image.open(debug_png).convert("RGB")
    k = 1280 / im.width
    a = np.asarray(im).astype(np.int16)
    mag = (a[..., 0] > 180) & (a[..., 1] < 90) & (a[..., 2] > 180)
    cya = (a[..., 0] < 90) & (a[..., 1] > 180) & (a[..., 2] > 180)
    to_norm = lambda r: (r[0] * k / 1280, r[1] * k / 720, r[2] * k / 1280, r[3] * k / 720)  # noqa: E731
    return {"text": [to_norm(r) for r in rects_from_overlay(mag)], "faces": [to_norm(r) for r in rects_from_overlay(cya)]}


# ── Righe del testo (senza OCR) ─────────────────────────────────────────────
def text_lines(data: dict | None, manual_boxes=(), debug: dict | None = None) -> dict:
    """Altezze delle righe (frazione dell'altezza del canvas) per frase e parola chiave.

    Sidecar di yt-thumb-render: i testi con kind phrase/hook/headline sono la frase, keyword/highlight la parola
    chiave; un testo della frase può dichiarare keyword_rects. Senza parola chiave dichiarata (template v1: tutto il
    gancio in un elemento) la parola chiave è stimata come la riga più alta. Ripieghi: --text-box, overlay debug."""
    phrase: list[float] = []
    keyword: list[float] = []
    ksrc = None
    texts = ((data or {}).get("metrics") or {}).get("texts") or []
    if texts:
        src = "sidecar"
        for t in texts:
            kind = t.get("kind") or "hook"
            rects = [r for r in (t.get("rects") or []) if isinstance(r, (list, tuple)) and len(r) == 4 and r[3] > 0]
            if kind in KEYWORD_KINDS:
                keyword += [r[3] / 720 for r in rects]
                ksrc = "kind"
            elif kind in PHRASE_KINDS:
                rows = [r for r in (t.get("rows") or []) if isinstance(r, dict) and (r.get("h") or 0) > 0]
                if rows:
                    # righe di glifi del renderer (metrics.texts[].rows): altezza delle maiuscole senza i
                    # segni diacritici (È, Ì) e senza i box di sfondo, la stessa misura dei controlli di yt-thumb-render.
                    # I `rects` contano l'accento: «È ANDATA / BENE COSÌ.» misurerebbe il 24 % con le maiuscole al 19 %.
                    kw_rows = [r["h"] / 720 for r in rows if r.get("keyword")]
                    if kw_rows:
                        keyword += kw_rows
                        ksrc = ksrc or "field"
                    phrase += [r["h"] / 720 for r in rows if not r.get("keyword")]
                    continue
                kr = [r for r in (t.get("keyword_rects") or t.get("highlight_rects") or []) if len(r) == 4 and r[3] > 0]
                if kr:
                    keyword += [r[3] / 720 for r in kr]
                    ksrc = ksrc or "field"
                    rects = [r for r in rects if not any(k[1] <= r[1] + r[3] / 2 <= k[1] + k[3] for k in kr)]
                phrase += [r[3] / 720 for r in rects]
    elif manual_boxes:
        src = "manual"
        phrase = [b[3] for b in manual_boxes]
    elif debug and debug.get("text"):
        src = "debug"
        phrase = [b[3] for b in debug["text"] if b[3] >= 0.06]    # < 6 %: badge, credenziale, meta
    else:
        return {"phrase": [], "keyword": [], "keyword_source": None, "source": None}
    if ksrc is None and phrase:
        i = int(np.argmax(phrase))
        keyword = [phrase.pop(i)]
        ksrc = "estimated"
    # titolo a un solo corpo (v2: la parola chiave è uno span .hl nella stessa riga, alta come le altre): il 18 % della
    # parola chiave è l'obiettivo, non un blocco — come in yt-thumb-render (post_render_checks). Solo con la parola
    # chiave dichiarata dal sidecar (keyword_rects), mai sulla stima.
    one_size = bool(ksrc == "field" and keyword and phrase and max(keyword) <= max(phrase) * 1.10)
    return {"phrase": [round(v, 4) for v in phrase], "keyword": [round(v, 4) for v in keyword],
            "keyword_source": ksrc, "source": src, "one_size": one_size}


# ── Controlli (funzioni pure: tests/test_thumb_qa.py) ───────────────────────
def chk(cid: str, level: str, message: str, value=None, threshold=None, **extra) -> dict:
    assert level in LEVELS, level
    out = {"id": cid, "level": level, "value": value, "threshold": threshold, "message": message}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def base_template(template: str | None) -> str:
    """Template incluso di riferimento: «duo» per duo e per <slug>-duo (variante di un brand), come yt-thumb-render."""
    t = str(template or "").strip()
    if t in BUILTIN_TEMPLATES:
        return t
    head, sep, tail = t.rpartition("-")          # lo slug del brand può contenere trattini («caffe-maker-duo»)
    if sep and head and tail in BUILTIN_TEMPLATES:
        return tail
    return t


def template_kind(template: str | None, lever: str | None, n_faces: int = 0) -> str:
    """claim | duo | other: decide quali soglie del volto valgono."""
    t, lv = base_template(template), (lever or "").strip().lower()
    if lv == "duo" or t in DUO_TEMPLATES:
        return "duo"
    if lv in CLAIM_LEVERS or t in (CLAIM_TEMPLATES - {"prova"}) or (t == "prova" and n_faces):
        return "claim"
    return "other"


def main_face_index(faces: list[dict]) -> int | None:
    """Volto principale: il più grande tra gli ospiti, altrimenti il più grande."""
    if not faces:
        return None
    guests = [i for i, f in enumerate(faces) if f.get("role") == "guest"]
    pool = guests or list(range(len(faces)))
    return max(pool, key=lambda i: faces[i]["box"][3])


def check_face_size(faces: list[dict], kind: str, still: bool = False, require_face: bool = False) -> dict:
    """faces: [{"box": [x,y,w,h] 0–1, "role": guest|host|None}]."""
    if not faces:
        if require_face:
            return chk("face_size", "error", "nessun volto nel render di un template che lo richiede")
        return chk("face_size", "skip", "nessun volto")
    mi = main_face_index(faces)
    v = round(faces[mi]["box"][3], 4)
    if kind == "claim":
        err = FACE_STILL_ERR if still else FACE_CLAIM_ERR
        src = " (sorgente still)" if still else ""
        if v < err:
            return chk("face_size", "error", f"volto principale al {v:.1%} dell'altezza (< {err:.0%} sui template claim{src}): "
                       "tetto al display o still/thumbnail cam", v, err)
        if v < FACE_CLAIM_WARN:
            return chk("face_size", "warn", f"volto principale al {v:.1%} (obiettivo ≥ {FACE_CLAIM_WARN:.0%})", v, FACE_CLAIM_WARN)
        return chk("face_size", "pass", f"volto principale al {v:.1%}", v, err)
    if kind == "duo":
        top = sorted(range(len(faces)), key=lambda i: -faces[i]["box"][3])[:2]
        if len(top) < 2:
            return chk("face_size", "warn", f"duo con un solo volto ({v:.1%})", v, FACE_DUO_ERR)
        small = [faces[i]["box"][3] for i in top if faces[i]["box"][3] < FACE_DUO_ERR]
        g = [faces[i]["box"][3] for i in top if faces[i].get("role") == "guest"]
        h = [faces[i]["box"][3] for i in top if faces[i].get("role") == "host"]
        vals = [round(faces[i]["box"][3], 4) for i in top]
        if small:
            return chk("face_size", "error", f"duo: volti al {', '.join(f'{x:.1%}' for x in vals)} (ognuno ≥ {FACE_DUO_ERR:.0%})",
                       vals, FACE_DUO_ERR)
        if g and h and max(g) + 1e-3 < max(h):
            return chk("face_size", "error", f"duo: l'ospite ({max(g):.1%}) ha il volto più piccolo dell'host ({max(h):.1%})",
                       vals, "ospite ≥ host")
        return chk("face_size", "pass", f"duo: volti al {', '.join(f'{x:.1%}' for x in vals)}", vals, FACE_DUO_ERR)
    return chk("face_size", "info", f"volto principale al {v:.1%} (template non claim/duo: nessuna soglia)", v)


def check_face_surround(v: float | None, detail: dict | None = None) -> dict:
    if v is None:
        return chk("face_surround", "skip", "stacco volto–intorno non misurabile (volto mancante o intorno coperto)")
    how = ""
    if detail and detail.get("straddle"):
        how = (f" [intorno a cavallo del volto: {detail['brighter_share']:.0%} più chiaro, {detail['darker_share']:.0%} più scuro → "
               f"mediana per pixel di |ΔL*|; R3 {detail['r3']}]")
    if v < SURROUND_ERR:
        return chk("face_surround", "error", f"stacco volto–intorno ΔL* {v} (< {SURROUND_ERR:.0f}): il volto si confonde col fondo "
                   "(scurisci o raffredda il fondo attorno alla testa)" + how, v, SURROUND_ERR)
    if v < SURROUND_WARN:
        return chk("face_surround", "warn", f"stacco volto–intorno ΔL* {v} (< {SURROUND_WARN:.0f})" + how, v, SURROUND_WARN)
    return chk("face_surround", "pass", f"stacco volto–intorno ΔL* {v}" + how, v, SURROUND_ERR)


def check_served_detail(v: float | None, face_px: int | None = None, main: bool = True) -> dict:
    cid = "served_detail" if main else "served_detail_other"
    px = f", volto di {face_px} px" if face_px else ""
    if v is None:
        return chk(cid, "skip", "dettaglio al formato servito non misurabile")
    if v < DETAIL_ERR:
        lvl = "error" if main else "warn"
        return chk(cid, lvl, f"dettaglio del volto nel file da 720×405 {v:.0f}{px} (< {DETAIL_ERR:.0f}, p10 EN): troppo morbido "
                   "al formato servito → volto più piccolo o sorgente migliore (still, thumbnail cam)", v, DETAIL_ERR)
    if v < DETAIL_WARN:
        return chk(cid, "warn", f"dettaglio del volto nel file da 720×405 {v:.0f}{px} (< {DETAIL_WARN:.0f}, p25 EN)", v, DETAIL_WARN)
    return chk(cid, "pass", f"dettaglio del volto nel file da 720×405 {v:.0f}{px}", v, DETAIL_ERR)


def check_silhouette(v: float | None, guest_style: str | None = None) -> dict:
    gs = f" (guest_style: {guest_style})" if guest_style else ""
    if v is None:
        return chk("silhouette_246", "skip", "stacco della sagoma non misurato (serve il sidecar con i ritagli)")
    if v < SIL_WARN:
        return chk("silhouette_246", "warn", f"stacco della sagoma a {SIL_W} px |ΔL*| {v} (< {SIL_WARN:.0f}, soglia non calibrata){gs}",
                   v, SIL_WARN)
    return chk("silhouette_246", "pass", f"stacco della sagoma a {SIL_W} px |ΔL*| {v}{gs}", v, SIL_WARN)


def line_minimums(template: str | None) -> tuple[float, float, str]:
    """(minimo di ogni riga della frase, minimo della parola chiave, nota): il duo vuole ogni riga ≥ 20 % (07 §7.7,
    obiettivo 22 %); gli altri template 12 % e 18 %."""
    if base_template(template) == "duo":
        return DUO_LINE_MIN, DUO_LINE_MIN, "duo: ogni riga ≥ 20 %"
    return PHRASE_LINE_MIN, KEYWORD_LINE_MIN, ""


def check_text_lines(lines: dict, template: str | None = None) -> list[dict]:
    src, ksrc = lines.get("source"), lines.get("keyword_source")
    if not src:
        return [chk("phrase_line_h", "skip", "righe del testo non misurate (niente sidecar, --text-box o overlay debug)")]
    out = []
    soft = src in ("debug", "manual")                    # classificazione incerta: avviso, non errore
    pmin, kmin, tnote = line_minimums(template)
    duo = base_template(template) == "duo"
    tsuf = f"; {tnote}" if tnote else ""
    ph = lines.get("phrase") or []
    if not ph and not lines.get("keyword"):
        return [chk("phrase_line_h", "skip", f"nessuna riga del gancio (fonte: {src})")]
    if ph:
        v = min(ph)
        if v < pmin:
            out.append(chk("phrase_line_h", "warn" if soft else "error",
                           f"riga della frase alta {v:.1%} dell'altezza (< {pmin:.0%}; fonte: {src}{tsuf})", v, pmin))
        else:
            out.append(chk("phrase_line_h", "pass", f"righe della frase ≥ {v:.1%} (fonte: {src}{tsuf})", v, pmin))
    kw = lines.get("keyword") or []
    if kw:
        v = max(kw)
        est = ksrc == "estimated"
        note = "stimata: la riga più alta" if est else f"fonte: {src}"
        one = bool(lines.get("one_size"))
        if one and not duo:
            note += "; titolo a un solo corpo: il 18 % è l'obiettivo, non un blocco"
        if v < kmin:
            soft_kw = soft or est or (one and not duo and v >= PHRASE_LINE_MIN)
            out.append(chk("keyword_line_h", "warn" if soft_kw else "error",
                           f"parola chiave alta {v:.1%} (< {kmin:.0%}; {note}{tsuf})", v, kmin))
        else:
            out.append(chk("keyword_line_h", "pass", f"parola chiave alta {v:.1%} ({note}{tsuf})", v, kmin))
    return out


def hook_words(text: str) -> list[str]:
    """Parole del gancio contate come yt-thumb-render (gli elisi contano due: L'HO = lo ho; «|» va a capo)."""
    t = re.sub(r"(\w)['’](\w)", r"\1 \2", str(text or ""))
    return [w for w in re.split(r"[\s|]+", t) if re.search(r"\w", w)]


def check_hook_words(hook: str | None, template: str | None) -> dict:
    """3–6 parole per tutti (meno di 3 errore, più di 6 avviso); duo 3–4 parole (più di 4 errore: il titolo deve stare in
    2 righe al 20 % dell'altezza)."""
    if not hook:
        return chk("hook_words", "skip", "gancio non presente nel sidecar")
    n = len(hook_words(hook))
    if n < HOOK_WORDS_MIN:
        return chk("hook_words", "error", f"gancio di {n} parole (< {HOOK_WORDS_MIN}): un frammento non dice niente", n, HOOK_WORDS_MIN)
    if base_template(template) == "duo" and n > DUO_WORDS_MAX:
        return chk("hook_words", "error", f"duo: gancio di {n} parole (> {DUO_WORDS_MAX}): servono 3–4 parole in 2 righe "
                   "al 20 % dell'altezza (07 §7.7); comprimi la frase o usa ritratto", n, DUO_WORDS_MAX)
    if n > HOOK_WORDS_MAX:
        return chk("hook_words", "warn", f"gancio di {n} parole (> {HOOK_WORDS_MAX})", n, HOOK_WORDS_MAX)
    lim = DUO_WORDS_MAX if base_template(template) == "duo" else HOOK_WORDS_MAX
    return chk("hook_words", "pass", f"gancio di {n} parole", n, lim)


def check_edges(m: dict) -> list[dict]:
    """Stacco dal feed. Scuro (#0f0f0f): avviso sotto 25 ΔL*, salvo un elemento chiaro di cornice (tratto continuo del
    bordo ≥ 10 % del perimetro, ≥ 40 ΔL* dalla pagina: cerchio d'accento o disco carta che toccano il bordo).
    Chiaro (#ffffff): avviso sotto 20."""
    out = []
    v = m.get("edge_dL_dark")
    if v is not None:
        run = m.get("edge_light_run")
        frame = run is not None and run >= EDGE_LIGHT_RUN
        if v >= EDGE_DL_DARK_MIN:
            out.append(chk("edge_dL_dark", "pass", f"bordo della tile a ΔL* {v} dalla pagina scura", v, EDGE_DL_DARK_MIN,
                           light_run=run))
        elif frame:
            out.append(chk("edge_dL_dark", "pass", f"bordo della tile a ΔL* {v} dalla pagina scura (< {EDGE_DL_DARK_MIN:.0f}), "
                           f"ma un elemento chiaro tocca il bordo per il {run:.0%} del perimetro (≥ {EDGE_LIGHT_RUN:.0%}): "
                           "stacco affidato all'elemento di cornice", v, EDGE_DL_DARK_MIN, light_run=run))
        else:
            rs = f"; elemento chiaro di cornice {run:.0%} del perimetro (< {EDGE_LIGHT_RUN:.0%})" if run is not None else ""
            out.append(chk("edge_dL_dark", "warn", f"bordo della tile a ΔL* {v} dalla pagina scura (< {EDGE_DL_DARK_MIN:.0f}){rs}: "
                           "si mimetizza nel feed scuro → plate più chiara al bordo, oppure un cerchio d'accento o un disco carta "
                           "che tocchi il bordo (07 §7.7)", v, EDGE_DL_DARK_MIN, light_run=run))
    v = m.get("edge_dL_light")
    if v is not None:
        if v < EDGE_DL_MIN:
            out.append(chk("edge_dL_light", "warn", f"bordo della tile a ΔL* {v} dalla pagina chiara (< {EDGE_DL_MIN:.0f}): "
                           "può mimetizzarsi nel feed chiaro", v, EDGE_DL_MIN))
        else:
            out.append(chk("edge_dL_light", "pass", f"bordo della tile a ΔL* {v} dalla pagina chiara", v, EDGE_DL_MIN))
    return out


def check_grade(g: dict | None, declared: str | None) -> list[dict]:
    """Livello 2b (07 §11.2): con `grade: mono` la stessa curva su tutti i pixel delle persone (residuo e scarti tra
    curve), persone e plate monocromatiche, sorgente a colori (livello 0 vero); senza mono: skip."""
    if declared != "mono":
        return [chk("grade_uniform", "skip", f"grade {declared or 'none'}: nessun grade monocromatico dichiarato (livello 2b)")]
    if not g or not g.get("ok"):
        return [chk("grade_uniform", "warn" if (g or {}).get("soft") else "error",
                    f"grade mono dichiarato ma non verificabile: {(g or {}).get('reason', 'nessun dato')}")]
    out = []
    if g["src_face_chroma"] < SRC_CHROMA_MIN:
        return [chk("grade_uniform", "error", f"il ritaglio indicato dal sidecar è già senza colore (C*ab mediano del volto "
                    f"{g['src_face_chroma']} < {SRC_CHROMA_MIN:.0f}): serve il livello 0 a colori (spec.people[].source_path) per "
                    "verificare la curva", g["src_face_chroma"], SRC_CHROMA_MIN)]
    gaps = [x for x in g.get("people_gap") or []]
    pg = max((x["mean"] for x in gaps), default=None)
    fg = max(((p.get("face_gap") or {}).get("mean", 0.0) for p in g["people"]), default=None)
    worst_gap = max(v for v in (pg, fg, 0.0) if v is not None)
    r = g["res_p95"]
    parts = [f"curva unica su {len(g['people'])} persone ({g['px']} px, grigio {g['luma']}): residuo p50 {g['res_p50']} / p95 {r} ΔL*"]
    if pg is not None:
        parts.append(f"scarto tra persone {pg}")
    if fg is not None:
        parts.append(f"scarto volto ↔ resto {fg}")
    msg = "; ".join(parts)
    if r > GRADE_RES_ERR or worst_gap > GRADE_GAP_ERR:
        lvl = "error"
    elif r > GRADE_RES_WARN or worst_gap > GRADE_GAP_WARN:
        lvl = "warn"
    else:
        lvl = "pass"
    hint = {"error": ": non è una curva globale uguale per tutti (ritocco locale, curve diverse tra le persone o grana sopra "
                     "le persone) → stesso grade su tutto, nessun ritocco locale sul volto",
            "warn": f" (avviso oltre {GRADE_RES_WARN} / {GRADE_GAP_WARN})", "pass": ""}[lvl]
    out.append(chk("grade_uniform", lvl, msg + hint, {"res_p95": r, "people_gap": pg, "face_gap": fg},
                   {"res_p95": GRADE_RES_ERR, "gap": GRADE_GAP_ERR}, people=g["people"]))
    c = g["chroma_p95"]
    if c > MONO_CHROMA_MAX:
        out.append(chk("grade_mono", "error", f"persone non monocromatiche: C*ab p95 {c} (> {MONO_CHROMA_MAX:.0f}): il 2b è un grade "
                       "senza colore su tutta la foto", c, MONO_CHROMA_MAX))
    else:
        pl = (g.get("plate") or {}).get("chroma_p95")
        if pl is not None and pl > MONO_CHROMA_MAX:
            out.append(chk("grade_mono", "warn", f"persone mono (C*ab p95 {c}) ma la plate ha colore: C*ab p95 {pl} (> {MONO_CHROMA_MAX:.0f}; "
                           "accento escluso): stesso grade su persone e plate", pl, MONO_CHROMA_MAX))
        else:
            out.append(chk("grade_mono", "pass", f"persone e plate monocromatiche (C*ab p95 {c}" + (f" / plate {pl})" if pl is not None else ")"),
                           c, MONO_CHROMA_MAX))
    for p in g.get("people") or []:
        who = p.get("name") or p.get("role") or "persona"
        v = p.get("face_res_p95")
        if v is None:
            continue
        soft = bool(p.get("resized"))                  # ritaglio non disegnato 1:1: il ricampionamento aggiunge rumore
        note = " (ritaglio non disegnato 1:1: solo avviso)" if soft else ""
        msg = f"{who}: volto a p95 {v} ΔL* dalla curva comune ({p['face_px']} px){note}"
        if v > FACE_RES_ERR:
            out.append(chk("grade_face", "warn" if soft else "error", msg + f" (> {FACE_RES_ERR}): il volto non segue la curva "
                           "globale (ritocco locale, deformazione o un effetto sopra il volto)", v, FACE_RES_ERR))
        elif v > FACE_RES_WARN:
            out.append(chk("grade_face", "warn", msg + f" (> {FACE_RES_WARN}: grana o un effetto sopra il volto?)", v, FACE_RES_WARN))
        else:
            out.append(chk("grade_face", "pass", msg, v, FACE_RES_ERR))
    if not g.get("monotonic", True):
        out.append(chk("grade_curve_monotonic", "warn", f"la curva stimata scende di {g['max_drop']} L* in un tratto: un grade "
                       "di tono è monotono (curve miste?)", g["max_drop"], 2.0))
    return out


def check_landmarks(lm: list[dict] | None, declared: str | None) -> list[dict]:
    """Livello 2b: landmark e espressione invariati tra livello 0 e render (MediaPipe, 478 punti)."""
    if declared != "mono":
        return []
    if lm is None:
        return [chk("grade_landmarks", "warn", "landmark non verificati: MediaPipe non installato (install.sh --with-mediapipe); "
                    "guarda il volto a 100 % in <stem>_100.png")]
    if not lm:
        return [chk("grade_landmarks", "skip", "nessun volto da confrontare (box del volto mancante nel sidecar)")]
    out = []
    for f in lm:
        who = f.get("name") or f.get("role") or f"persona {f['i'] + 1}"
        c = f.get("cmp")
        if not c:
            found = f.get("found") or [False, False]
            lvl = "error" if found[0] and not found[1] else "warn"
            out.append(chk("grade_landmarks", lvl, f"{who}: volto {'non trovato nel render' if found[0] else 'non trovato nel livello 0'} "
                           "da MediaPipe: impossibile confrontare i landmark"))
            continue
        v = c["mean"]
        co = c.get("curve_only")
        bs = f" · blendshape {c['bs_worst']} Δ {c['bs_max']}" if c.get("bs_worst") else ""
        base = f"; solo grigio {c['grey_baseline']:.1%}, sola curva {co:.1%}" if co is not None and c.get("grey_baseline") is not None else ""
        msg = f"{who}: landmark spostati in media del {v:.1%} della distanza tra gli occhi (p95 {c['p95']:.1%}{base}){bs}"
        if v > LM_ERR:
            out.append(chk("grade_landmarks", "error", msg + f" (> {LM_ERR:.0%}): la geometria del volto è cambiata", v, LM_ERR, cmp=c))
        elif v > LM_WARN and not (co is not None and co <= LM_WARN):
            out.append(chk("grade_landmarks", "warn", msg + f" (> {LM_WARN:.0%}, anche con la sola curva)", v, LM_WARN, cmp=c))
        elif (c.get("bs_max") or 0) > BS_WARN:
            out.append(chk("grade_landmarks", "warn", msg + f" (blendshape Δ > {BS_WARN}: guarda l'espressione a 100 %)", v, LM_WARN, cmp=c))
        else:
            note = " (sopra il 2 % come il solo grigio: rumore del rilevatore; la sola curva ≤ 2 %)" if v > LM_WARN else ""
            out.append(chk("grade_landmarks", "pass", msg + note, v, LM_ERR, cmp=c))
    return out


def check_skin_de(data: dict, declared: str | None) -> dict | None:
    """ΔE00 della pelle (livello 2, `person_tone` con guest_style graphic): ripetuto dal sidecar del render. Saltato
    SOLO con il grade mono (2b), dove è sostituito da grade_uniform + grade_landmarks."""
    heroes = (data.get("checks_v2") or {}).get("heroes") or []
    tones = [(h.get("cutout") or f"persona {i + 1}", h.get("tone")) for i, h in enumerate(heroes) if isinstance(h.get("tone"), dict)]
    if declared == "mono":
        return chk("skin_de00", "skip", "ΔE00 della pelle non applicabile al grade monocromatico (livello 2b): valgono "
                   "grade_uniform e grade_landmarks")
    if not tones:
        return None
    bad = [f"{n}: media {t.get('skin_de00_mean')} / p95 {t.get('skin_de00_p95')}" for n, t in tones
           if (t.get("skin_de00_mean") or 0) > 2.5 + 1e-6 or (t.get("skin_de00_p95") or 0) > 5.0 + 1e-6]
    if bad:
        return chk("skin_de00", "error", "ΔE00 della pelle oltre media 2.5 / p95 5 (livello 2): " + "; ".join(bad), len(bad), 0)
    return chk("skin_de00", "pass", "ΔE00 della pelle entro media 2.5 / p95 5: " +
               ", ".join(f"{n} {t.get('skin_de00_mean')}/{t.get('skin_de00_p95')}" for n, t in tones), 0, 0)


def check_circle(c: dict | None) -> dict:
    """Cerchio d'accento dietro una persona: ΔL* verso i capelli/il volto adiacenti (errore < 10, avviso < 20)."""
    if c is None:
        return chk("circle_contrast", "skip", "nessun cerchio d'accento (o niente sidecar con i ritagli)")
    alt = c.get("alternatives") or {}
    alt_s = (" · alternative: " + ", ".join(f"{k} {v}" for k, v in sorted(alt.items(), key=lambda kv: -kv[1]))) if alt else ""
    if c.get("dL_head") is None:
        v = c.get("dL_all")
        if v is None:
            return chk("circle_contrast", "info", f"cerchio d'accento ({c.get('accent')}, {c['circle_share']:.0%} del canvas) non "
                       "adiacente a una persona", None)
        return chk("circle_contrast", "info", f"cerchio d'accento non adiacente a una testa; ΔL* verso la persona {v}{alt_s}", v,
                   CIRCLE_WARN, circle=c)
    v = c["dL_head"]
    msg = (f"cerchio {c.get('accent')} ↔ capelli/volto adiacenti ΔL* {v} (persona L* {c.get('person_L_head')}; "
           f"{c.get('pairs_head')} coppie){alt_s}")
    if v < CIRCLE_ERR:
        return chk("circle_contrast", "error", msg + f" (< {CIRCLE_ERR:.0f}): la testa si fonde col cerchio → l'altro accento, "
                   "o il cerchio dietro le spalle", v, CIRCLE_ERR, circle=c)
    if v < CIRCLE_WARN:
        return chk("circle_contrast", "warn", msg + f" (< {CIRCLE_WARN:.0f})", v, CIRCLE_WARN, circle=c)
    return chk("circle_contrast", "pass", msg, v, CIRCLE_ERR, circle=c)


def check_text_contrast(v: float | None) -> dict:
    if v is None:
        return chk("text_contrast_168", "skip", "contrasto del gancio non misurato (nessun box del testo)")
    if v < TEXT_CONTRAST_168_MIN:
        return chk("text_contrast_168", "warn", f"contrasto testo/fondo a 168 px {v}:1 (< 3:1)", v, TEXT_CONTRAST_168_MIN)
    return chk("text_contrast_168", "pass", f"contrasto testo/fondo a 168 px {v}:1", v, TEXT_CONTRAST_168_MIN)


def check_display_upscale(face_px_1280: float | None, eff_face_px: float | None, cap: float = DISPLAY_CAP) -> dict:
    if not face_px_1280 or not eff_face_px:
        return chk("display_upscale", "skip", "ingrandimento al display non misurato (manca eff_face_px nel sidecar del ritratto)")
    v = round(face_px_1280 / eff_face_px, 2)
    msg = f"volto a 1280 px = {face_px_1280:.0f} px su {eff_face_px:.0f} px effettivi = {v}× (tetto {cap}×)"
    if v > cap + 0.02:
        return chk("display_upscale", "warn", msg + ": oltre il tetto al display (07 §10.1)", v, cap)
    return chk("display_upscale", "info", msg, v, cap)


def check_render(data: dict) -> dict | None:
    if not data:
        return None
    errs = data.get("errors") or []
    if errs or data.get("pass") is False:
        return chk("render_checks", "error", f"yt-thumb-render: {len(errs)} errori bloccanti ({'; '.join(map(str, errs))[:300]})",
                   len(errs), 0)
    return chk("render_checks", "pass", "yt-thumb-render: nessun errore", 0, 0)


def classify_salient(sbox, faces: list[dict], text_boxes) -> str:
    """Cosa copre la regione saliente: 'face' | 'headline' | 'other' (quota dell'area coperta, ≥ 25 %)."""
    x, y, w, h = sbox
    area = max(w * h, 1e-9)

    def cover(b):
        bx, by, bw, bh = b
        ix = max(0.0, min(x + w, bx + bw) - max(x, bx))
        iy = max(0.0, min(y + h, by + bh) - max(y, by))
        return ix * iy / area

    fc = max((cover(f["box"]) for f in faces), default=0.0)
    tc = min(1.0, sum(cover(b) for b in text_boxes or ()))
    if max(fc, tc) < 0.25:
        return "other"
    return "face" if fc >= tc else "headline"


def union_box(boxes) -> tuple[float, float, float, float] | None:
    boxes = [b for b in boxes or () if b and b[2] > 0 and b[3] > 0]
    if not boxes:
        return None
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _clamp_box(b) -> tuple[float, float, float, float]:
    x0, y0 = min(max(b[0], 0.0), 1.0), min(max(b[1], 0.0), 1.0)
    x1, y1 = min(max(b[0] + b[2], 0.0), 1.0), min(max(b[1] + b[3], 0.0), 1.0)
    return (x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0))


def saliency_regions(png: Path, face_box=None, headline_box=None, heatmap: Path | None = None,
                     timeout: float = 60) -> dict | None:
    """`thumbvision saliency IMG --boxes face:…;headline:…` (Apple Vision, attention-based): oggetti salienti
    [{box 0–1 alto-sinistra, confidence}], quota e media di salienza nei box nominati, `first` = box con la media più
    alta. None se il binario non ha il sottocomando (thumbvision prima di thumbnail v2)."""
    if not yc.SWIFT_BIN.exists():
        return None
    cmd = [str(yc.SWIFT_BIN), "saliency", str(png)]
    named = [(n, _clamp_box(b)) for n, b in (("face", face_box), ("headline", headline_box)) if b]
    named = [(n, b) for n, b in named if b[2] > 0.005 and b[3] > 0.005]
    if named:
        cmd += ["--boxes", ";".join(f"{n}:" + ",".join(f"{v:.4f}" for v in b) for n, b in named)]
    if heatmap is not None:
        cmd += ["--out", str(heatmap), "--overlay"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = json.loads(proc.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    if isinstance(out, list):
        out = out[0] if out else {}
    if not isinstance(out, dict) or out.get("ok") is False or out.get("error"):
        return None
    regs = next((out[k] for k in ("objects", "salient_objects", "salient", "regions") if isinstance(out.get(k), list)), [])
    clean = [r for r in regs if isinstance(r, dict) and isinstance(r.get("box"), (list, tuple)) and len(r["box"]) == 4]
    return {"objects": sorted(clean, key=lambda r: -(r.get("confidence") or 0)), "first": out.get("first"),
            "boxes": out.get("boxes"), "peak": out.get("peak"), "heatmap": out.get("heatmap")}


def check_saliency(sal: dict | list | None, faces: list[dict], text_boxes) -> dict:
    """Info: cosa si nota per primo. Con i box nominati vince la media di salienza (thumbvision `first`); senza, la
    regione saliente più sicura classificata per copertura."""
    if sal is None:
        return chk("saliency_first", "info", "salienza non disponibile (thumbvision senza il sottocomando 'saliency')")
    if isinstance(sal, list):
        sal = {"objects": sal}
    regions = sal.get("objects") or []
    first = sal.get("first")
    how = "media di salienza nei box"
    if first not in ("face", "headline"):
        if not regions:
            return chk("saliency_first", "info", "salienza: nessuna regione saliente")
        first, how = classify_salient(regions[0]["box"], faces, text_boxes), "regione principale"
    label = {"face": "il volto", "headline": "il titolo", "other": "un'altra zona"}[first]
    shares = sal.get("boxes") or {}
    extra = ", ".join(f"{k} {v.get('share', 0):.0%}" for k, v in shares.items() if isinstance(v, dict))
    return chk("saliency_first", "info", f"si nota per primo: {label} ({how}{'; quota di salienza ' + extra if extra else ''})",
               first, regions=[{"box": [round(v, 4) for v in r["box"]], "confidence": r.get("confidence")} for r in regions[:3]] or None,
               boxes=shares or None, heatmap=sal.get("heatmap"))


def apply_overrides(checks: list[dict], spec: dict) -> None:
    """Motivi scritti al G2 (spec.qa_overrides {id: motivo}, spec.face_floor_reason): l'errore scende ad avviso."""
    ov = dict(spec.get("qa_overrides") or {}) if isinstance(spec.get("qa_overrides"), dict) else {}
    if spec.get("face_floor_reason"):
        ov.setdefault("face_size", spec["face_floor_reason"])
    if spec.get("hook_size_reason"):                    # stesso motivo G2 che yt-thumb-render accetta per le righe
        ov.setdefault("phrase_line_h", spec["hook_size_reason"])
        ov.setdefault("keyword_line_h", spec["hook_size_reason"])
    if spec.get("detail_reason"):
        ov.setdefault("served_detail", spec["detail_reason"])
    for c in checks:
        reason = ov.get(c["id"])
        if reason and c["level"] == "error":
            c["level"] = "warn"
            c["override"] = str(reason)
            c["message"] += f" — motivo dichiarato: {reason}"


def gate(checks: list[dict], gated: bool) -> None:
    if gated:
        return
    for c in checks:
        if c["level"] == "error":
            c["level"] = "warn"
            c["ungated"] = True


# ── Facce e contesto dal sidecar ────────────────────────────────────────────
def _people_roles(spec: dict, n: int, template: str | None) -> list[str | None]:
    people = spec.get("people") or []
    roles = [((people[i] or {}).get("role") if i < len(people) else None) for i in range(n)]
    if not any(roles) and isinstance(spec.get("roles"), list):
        roles = (spec["roles"] + [None] * n)[:n]
    if not any(roles) and n == 1:
        roles = ["guest"]
    return roles


def faces_from_sidecar(data: dict) -> list[dict]:
    spec = data.get("spec") or {}
    heroes = (data.get("metrics") or {}).get("heroes") or []
    roles = _people_roles(spec, len(heroes), data.get("template"))
    people = spec.get("people") or []
    rendered = (data.get("checks2") or {}).get("heroes") or []   # tetto usato davvero dal render (--display-cap o concept)
    out = []
    for i, h in enumerate(heroes):
        f = h.get("face")
        if not f or len(f) != 4:
            continue
        p = (people[i] if i < len(people) else {}) or {}
        portrait = p.get("portrait") or {}
        src = portrait.get("source") or {}
        still = (src.get("kind") == "still") or bool(src.get("image")) or p.get("source_kind") == "still"
        out.append({"box": [f[0] / 1280, f[1] / 720, f[2] / 1280, f[3] / 720], "role": roles[i] if i < len(roles) else None,
                    "face_px_1280": f[3], "eff_face_px": portrait.get("eff_face_px"), "still": still,
                    "display_cap": _cap_factor((rendered[i] if i < len(rendered) else {}).get("display_cap"))
                    or _cap_factor(portrait.get("display_cap")), "name": p.get("name")})
    return out


def _cap_factor(cap) -> float | None:
    """portrait.display_cap di yt-portrait cut è un dict ({mode, factor, …}); i sidecar vecchi o manuali possono avere
    un numero. Ritorna il fattore (2.0 = opzione c, 1.5 = b) o None."""
    if isinstance(cap, dict):
        cap = cap.get("factor")
    try:
        return float(cap) if cap not in (None, "") else None
    except (TypeError, ValueError):
        return None


def faces_from_vision(im1280: Image.Image) -> list[dict] | None:
    if not yc.SWIFT_BIN.exists():
        return None
    with tempfile.TemporaryDirectory(prefix="yt-qa-") as td:
        tmp = Path(td) / "tile.jpg"
        im1280.convert("RGB").save(tmp, quality=92)
        try:
            proc = subprocess.run([str(yc.SWIFT_BIN), "faces", str(tmp)], capture_output=True, text=True, timeout=60)
            res = json.loads(proc.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None
    faces = (res[0].get("faces") if isinstance(res, list) and res else None) or []
    return [{"box": f["box"], "role": None, "face_px_1280": f["box"][3] * 720} for f in faces if f.get("box") and f["box"][3] >= 0.05]


def run_checks(im1280: Image.Image, src: Path, data: dict, manual_boxes: list, *, gated: bool, use_vision: bool = True,
               display_cap: float | None = None, heatmap: Path | None = None, landmarks: bool = True) -> tuple[list[dict], dict]:
    """Tutti i controlli v2 per un'immagine. Ritorna (checks, pannello del volto per il foglio e il JSON)."""
    spec = data.get("spec") or {}
    template = data.get("template") or spec.get("template")
    debug_png = src.with_name(src.stem + "_debug.png")
    debug = None
    faces: list[dict] = []
    face_src = None
    if data:
        faces = faces_from_sidecar(data)
        face_src = "sidecar" if faces else None
    if not faces and debug_png.exists():
        try:
            debug = overlay_boxes(debug_png)
            faces = [{"box": list(b), "role": None, "face_px_1280": b[3] * 720} for b in debug["faces"]]
            face_src = "debug" if faces else None
        except Exception:  # noqa: BLE001
            debug = None
    if not faces and use_vision and not data:
        faces = faces_from_vision(im1280) or []
        face_src = "vision" if faces else None
    text_all = boxes_from_sidecar(src, data, kinds=None) if data else []
    if not text_all:
        text_all = list(manual_boxes) or ((debug or {}).get("text") or [])
    hook_boxes = boxes_from_sidecar(src, data) if data else []
    kind = template_kind(template, spec.get("lever"), len(faces))
    mi = main_face_index(faces)
    checks: list[dict] = []
    # 1. volto
    still = bool(faces and mi is not None and faces[mi].get("still"))
    checks.append(check_face_size(faces, kind, still=still, require_face=bool(data) and template in FACE_REQUIRED))
    served = served_file(im1280)
    panel: dict = {"faces": [], "main": mi, "kind": kind, "face_source": face_src, "template": template}
    mask = person_mask(data) if data else None
    for i, f in enumerate(faces):
        det, px = served_detail(served, f["box"])
        sur = face_surround_detail(im1280, f["box"], text_all, person=mask)
        info = {"box": [round(v, 4) for v in f["box"]], "role": f.get("role"), "face_frac": round(f["box"][3], 4),
                "served_px": px, "served_detail": det, "surround_dL": sur and sur["value"], "surround": sur}
        if f.get("eff_face_px"):
            info["display_upscale"] = round(f["face_px_1280"] / f["eff_face_px"], 2)
        panel["faces"].append(info)
    if mi is not None:
        m = panel["faces"][mi]
        checks.append(check_face_surround(m["surround_dL"], m.get("surround")))
        checks.append(check_served_detail(m["served_detail"], m["served_px"], main=True))
        for i, f in enumerate(panel["faces"]):
            if i != mi and f["face_frac"] >= 0.10:
                c = check_served_detail(f["served_detail"], f["served_px"], main=False)
                if c["level"] in ("warn", "error"):
                    c["message"] = f"volto {i + 1}: " + c["message"]
                    checks.append(c)
        cap = display_cap or faces[mi].get("display_cap") or DISPLAY_CAP
        checks.append(check_display_upscale(faces[mi].get("face_px_1280"), faces[mi].get("eff_face_px"), float(cap)))
    else:
        checks.append(check_face_surround(None))
        checks.append(check_served_detail(None))
    # 2. sagoma (maschera delle persone calcolata sopra)
    sil = silhouette_dL(im1280, mask) if mask is not None else None
    panel["silhouette_dL_246"] = sil
    checks.append(check_silhouette(sil, spec.get("guest_style")))
    # 3. righe del testo (sidecar → --text-box → overlay debug)
    has_texts = bool((data.get("metrics") or {}).get("texts"))
    if not has_texts and not manual_boxes and debug is None and debug_png.exists():
        try:
            debug = overlay_boxes(debug_png)
        except Exception:  # noqa: BLE001
            debug = None
    lines = text_lines(data if has_texts else None, manual_boxes, debug)
    panel["text_lines"] = lines
    checks += check_text_lines(lines, template)
    if data:
        checks.append(check_hook_words(spec.get("hook") or spec.get("text"), template))
    # 3b. livello 2b (grade monocromatico uniforme), ΔE00 della pelle (livello 2), cerchio d'accento
    if data:
        declared = declared_grade(data)
        panel["grade"] = declared or "none"
        g = None
        if declared == "mono":
            try:
                g = analyze_grade(src, data, im1280, with_landmarks=landmarks)
            except Exception as e:  # noqa: BLE001 — il controllo fallisce in modo leggibile, non il comando
                g = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
            panel["grade_analysis"] = {k: v for k, v in (g or {}).items() if k not in ("landmarks",)}
        checks += check_grade(g, declared)
        if declared == "mono":
            if not landmarks:
                checks.append(chk("grade_landmarks", "skip", "landmark non controllati (--no-landmarks)"))
            elif g and g.get("ok"):
                checks += check_landmarks(g.get("landmarks"), declared)
        sk = check_skin_de(data, declared)
        if sk:
            checks.append(sk)
        try:
            circ = circle_contrast(im1280, data, faces)
        except Exception:  # noqa: BLE001
            circ = None
        panel["circle"] = circ
        checks.append(check_circle(circ))
    # 4. salienza (info)
    head = union_box(hook_boxes or text_all)
    sal = saliency_regions(src, faces[mi]["box"] if mi is not None else None, head, heatmap) if use_vision else None
    checks.append(check_saliency(sal, faces, hook_boxes or text_all))
    panel["saliency"] = checks[-1].get("value")
    if sal and sal.get("heatmap"):
        panel["saliency_heatmap"] = sal["heatmap"]
    # 5. sidecar del render
    rc = check_render(data)
    if rc:
        checks.append(rc)
    apply_overrides(checks, spec)
    gate(checks, gated)
    return checks, panel


# ── Ritagli al 100 % ────────────────────────────────────────────────────────
def crops_100(src: Path, data: dict, out: Path) -> dict | None:
    """Ritagli al 100% del master (nessun ricampionamento): volto di ogni persona (box ×2.2) e bordi dritti dei
    ritagli che cadono dentro il canvas. Le coordinate vengono dal sidecar (spazio CSS 1280×720 → ×3)."""
    heroes = ((data.get("metrics") or {}).get("heroes")) or []
    edges = []
    for h in ((data.get("checks2") or {}).get("heroes")) or []:
        edges += [e for e in h.get("crop_edges", []) if e.get("inside")]
    if not heroes:
        return None
    im = Image.open(src).convert("RGB")
    k = im.width / 1280
    tiles = []
    for i, h in enumerate(heroes):
        x, y, w, hh = h["face"]
        cx, cy, s = (x + w / 2) * k, (y + hh / 2) * k, max(w, hh) * 2.2 * k
        box = [int(max(0, cx - s / 2)), int(max(0, cy - s * 0.55)), int(min(im.width, cx + s / 2)), int(min(im.height, cy + s * 0.45))]
        tiles.append((f"volto {i + 1} al 100%", im.crop(box)))
    for e in edges[:4]:
        a, b = e["span_css"]
        if e["side"] in ("left", "right"):
            x = e["line_css"] * k
            box = [int(max(0, x - 120)), int(max(0, a * k)), int(min(im.width, x + 120)), int(min(im.height, max(a * k + 10, min(b * k, a * k + 480))))]
        else:
            y = e["line_css"] * k
            box = [int(max(0, a * k)), int(max(0, y - 120)), int(min(im.width, max(a * k + 10, min(b * k, a * k + 480)))), int(min(im.height, y + 120))]
        tiles.append((f"bordo dritto {e['side']} ({e.get('visible_px', 0)} px visibili)", im.crop(box)))
    H = max(t.height for _, t in tiles) + 40
    W = sum(t.width for _, t in tiles) + 20 * (len(tiles) + 1)
    sheet = Image.new("RGB", (W, H + 20), DARK)
    d = ImageDraw.Draw(sheet)
    x = 20
    for label, t in tiles:
        sheet.paste(t, (x, 40))
        d.text((x, 10), label, font=font(20, 600), fill=(230, 230, 230))
        x += t.width + 20
    sheet.save(out, optimize=True)
    return {"crops_100": str(out), "tiles": len(tiles)}


# ── Foglio QA ───────────────────────────────────────────────────────────────
def sheet_tiles(surfaces: dict) -> list[tuple[str, int, int]]:
    sw, sh = surface_size(surfaces, "search", default=(500, 281))
    bw, bh = surface_size(surfaces, "sidebar", default=(216, 121))
    return [(f"{SERVED_W}×{SERVED_H} · file servito hq720 (griglia/ricerca desktop a 2×)", SERVED_W, SERVED_H),
            (f"{sw}×{sh} · ricerca (surfaces.json)", sw, sh),
            ("360×202 · hq720 a 1×", 360, 202),
            (f"{bw}×{bh} · sidebar reale (surfaces.json)", bw, bh),
            ("168×94 · stress test", 168, 94)]


def _face_crop(img: Image.Image, box, scale: float = 1.3, cap: int = 280) -> tuple[Image.Image, int]:
    W, H = img.size
    x, y, w, h = box
    cx, cy, s = (x + w / 2) * W, (y + h / 2) * H, max(w * W, h * H) * scale
    c = img.crop((int(max(0, cx - s / 2)), int(max(0, cy - s / 2)), int(min(W, cx + s / 2)), int(min(H, cy + s / 2))))
    face_px = int(round(h * H))
    if c.height > cap:
        c = c.resize((max(1, int(c.width * cap / c.height)), cap), Image.LANCZOS)
    return c, face_px


def legibility_sheet(im: Image.Image, title: str, out: Path, checks: list[dict] | None = None, panel: dict | None = None,
                     surfaces: dict | None = None) -> None:
    checks, panel, surfaces = checks or [], panel or {}, surfaces or {}
    pad, gap, lab = 32, 28, 34
    served = served_file(im)
    phone = served.resize((PHONE_W, PHONE_H), Image.BICUBIC)
    tiles = sheet_tiles(surfaces)
    row1_w = sum(w for _, w, _ in tiles) + gap * (len(tiles) - 1)
    bw, bh = surface_size(surfaces, "sidebar", default=(216, 121))
    row2 = [(f"{bw} chiaro", bw, bh, "plain"), ("168 chiaro (stress)", 168, 94, "plain"), ("360 chiaro", 360, 202, "plain"),
            ("360 grigi", 360, 202, "gray"), ("168 grigi", 168, 94, "gray"), ("360 sfocata", 360, 202, "blur"),
            ("168 sfocata", 168, 94, "blur")]
    W = max(row1_w, PHONE_W + gap + 868) + 2 * pad
    right_w = W - 2 * pad - PHONE_W - gap
    # pannello: altezza dei controlli (testo a capo)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    fchk = font(19, 500)
    chk_lines = []
    for c in checks:
        for j, line in enumerate(wrap(probe, f"{c['level'].upper()} · {c['message']}", fchk, right_w - 30)):
            chk_lines.append((c["level"], line, j == 0))
    faces = panel.get("faces") or []
    mi = panel.get("main")
    crops = []
    if mi is not None and faces:
        fb = faces[mi]["box"]
        for name, img in (("file 720", served), ("telefono 1180", phone)):
            c, fpx = _face_crop(img, fb)
            crops.append((f"{name}: volto {fpx} px" + (" (mostrato ridotto)" if c.height >= 280 else ""), c))
    hm = panel.get("saliency_heatmap")
    if hm and Path(hm).exists():
        try:
            h_img = Image.open(hm).convert("RGB")
            h_img = h_img.resize((356, max(1, round(356 * h_img.height / h_img.width))), Image.LANCZOS)
            first = {"face": "il volto", "headline": "il titolo", "other": "altro"}.get(panel.get("saliency") or "", "?")
            crops.append((f"salienza (Apple Vision): prima {first}", h_img))
        except Exception:  # noqa: BLE001
            pass
    crops_h = (max(c.height for _, c in crops) + 34) if crops else 0
    face_line = ""
    if mi is not None and faces:
        fm = faces[mi]
        bits = [f"volto {fm['face_frac']:.1%}", f"dettaglio@720 {fm['served_detail']:.0f}" if fm.get("served_detail") is not None else None,
                f"ΔL* volto–intorno {fm['surround_dL']}" if fm.get("surround_dL") is not None else None,
                f"sagoma@246 {panel['silhouette_dL_246']}" if panel.get("silhouette_dL_246") is not None else None,
                f"{fm['display_upscale']}× effettivo a 1280" if fm.get("display_upscale") else None]
        face_line = " · ".join(b for b in bits if b)
    right_h = (60 if face_line else 0) + crops_h + 20 + 28 * len(chk_lines) + 40
    row3_h = max(PHONE_H, right_h) + lab
    head_h = 50 + 40
    H = pad + head_h + (SERVED_H + lab) + gap + (202 + lab) + gap + row3_h + pad
    sheet = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(sheet)
    d.text((pad, pad), title, font=font(30, 700), fill=(240, 240, 240))
    d.text((W - pad, pad + 4), "tile dal file servito 720×405 · surfaces: Engaged Views, CC BY 4.0 (adattato)",
           font=font(20, 500), fill=(160, 160, 160), anchor="ra")
    errs = [c for c in checks if c["level"] == "error"]
    warns = [c for c in checks if c["level"] == "warn"]
    if errs:
        summary, col = f"NON PASSA · {len(errs)} errori, {len(warns)} avvisi: " + " · ".join(c["id"] for c in errs), LEVEL_RGB["error"]
    else:
        summary, col = f"passa i controlli bloccanti · {len(warns)} avvisi" + (": " + " · ".join(c["id"] for c in warns) if warns else ""), LEVEL_RGB["pass"]
    d.text((pad, pad + 46), summary, font=font(24, 700), fill=col)
    # Riga 1: tile su fondo scuro, allineate in basso
    x, base = pad, pad + head_h + lab + SERVED_H
    for label, w, h in tiles:
        t = duration_badge(served if (w, h) == (SERVED_W, SERVED_H) else fit_thumb(served, w, h))
        r = rounded(t, max(4, int(12 * w / 347)))
        sheet.paste(r, (x, base - h), r)
        lab_lines = wrap(d, label, font(18, 600), max(w, 150))
        for li, line in enumerate(reversed(lab_lines)):
            d.text((x, base - h - 8 - li * 22), line, font=font(18, 600), fill=(200, 200, 200), anchor="ld")
        x += w + gap
    # Riga 2: chiaro / grigi / sfocata
    y2 = base + gap
    sheet.paste(Image.new("RGB", (W, 202 + lab + gap), LIGHT), (0, y2 - gap // 2))
    x = pad
    for label, w, h, kind in row2:
        t = fit_thumb(served, w, h)
        if kind == "gray":
            t = ImageOps.grayscale(t).convert("RGB")
        elif kind == "blur":
            t = t.filter(ImageFilter.GaussianBlur(radius=1.6 * w / 360))
        t = duration_badge(t)
        r = rounded(t, max(4, int(12 * w / 347)))
        sheet.paste(r, (x, y2 + lab + (202 - h)), r)
        d.text((x, y2 + lab - 6), label, font=font(18, 600), fill=(60, 60, 60), anchor="ld")
        x += w + gap + 16
    # Riga 3: catena del file servito + pannello
    y3 = y2 + 202 + lab + gap + gap // 2
    d.text((pad, y3 + lab - 8), f"catena servita: render → {SERVED_W}×{SERVED_H} (Lanczos) → {PHONE_W}×{PHONE_H} (telefono, bicubica)",
           font=font(20, 600), fill=(200, 200, 200), anchor="ld")
    pr = rounded(duration_badge(phone), 24)
    sheet.paste(pr, (pad, y3 + lab), pr)
    rx, ry = pad + PHONE_W + gap, y3 + lab
    if face_line:
        fl = wrap(d, face_line, font(20, 700), right_w)[:2]
        for li, line in enumerate(fl):
            d.text((rx, ry + li * 24), line, font=font(20, 700), fill=(240, 240, 240))
        ry += 24 * len(fl) + 12
    if crops:
        cx = rx
        f18 = font(18, 600)
        for label, c in crops:
            if cx + c.width > W - pad:
                break
            sheet.paste(c, (cx, ry + 28))
            d.text((cx, ry + 20), label, font=f18, fill=(200, 200, 200), anchor="ld")
            cx += max(c.width, int(d.textlength(label, font=f18))) + 28
        ry += crops_h
    yy = ry + 10
    for level, line, first in chk_lines:
        if first:
            d.ellipse((rx, yy + 6, rx + 14, yy + 20), fill=LEVEL_RGB[level])
        d.text((rx + 26, yy), line, font=fchk, fill=(225, 225, 225) if level in ("error", "warn") else (170, 170, 170))
        yy += 28
    sheet.save(out, optimize=True)


# ── Mock della griglia ──────────────────────────────────────────────────────
def grid_mock(cand: Image.Image, comps: list[Path], out: Path, title: str | None, pos: int, seed: int,
              channel: str = "Il tuo canale") -> dict:
    S = 2                                   # disegno a 2× per testi nitidi
    tw, th, gx, gy = 347 * S, 195 * S, 16 * S, 40 * S
    meta_h = 92 * S
    cols, rows = 3, 3
    rng = random.Random(seed)
    pool = list(comps)
    rng.shuffle(pool)
    while len(pool) < cols * rows - 1:
        pool += pool[: cols * rows - 1 - len(pool)] or []
        if not pool:
            break
    pool = pool[: cols * rows - 1]
    tiles: list[tuple[Image.Image, bool]] = []
    for p in pool:
        try:
            tiles.append((Image.open(p).convert("RGB"), False))
        except Exception:
            continue
    tiles.insert(min(pos, len(tiles)), (cand, True))
    badges = [rng.choice(["48:12", "1:02:45", "37:09", "52:58", "1:21:30"]) for _ in tiles]
    panels = []
    for theme in ("dark", "light"):
        bg = DARK if theme == "dark" else LIGHT
        fg = (241, 241, 241) if theme == "dark" else (15, 15, 15)
        sub = (170, 170, 170) if theme == "dark" else (96, 96, 96)
        bar = (63, 63, 63) if theme == "dark" else (229, 229, 229)
        W = 24 * S * 2 + cols * tw + (cols - 1) * gx
        H = 24 * S * 2 + rows * (th + meta_h) + (rows - 1) * gy // 2
        panel = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(panel)
        for i, (img, is_cand) in enumerate(tiles[: cols * rows]):
            r, c = divmod(i, cols)
            x = 24 * S + c * (tw + gx)
            y = 24 * S + r * (th + meta_h + gy // 2)
            t = rounded(duration_badge(fit_thumb(img, tw, th), badges[i]), 12 * S)
            panel.paste(t, (x, y), t)
            # avatar + titolo (2 righe) + canale/visualizzazioni
            ay = y + th + 12 * S
            d.ellipse((x, ay, x + 36 * S, ay + 36 * S), fill=bar)
            tx = x + 48 * S
            if is_cand and title:
                f = font(16 * S, 600)
                lines = wrap(d, title, f, tw - 48 * S)[:2]
                for li, line in enumerate(lines):
                    d.text((tx, ay + li * 22 * S), line, font=f, fill=fg)
                d.text((tx, ay + 48 * S), f"{channel} · 1,2K visualizzazioni · 2 giorni fa", font=font(13 * S, 500), fill=sub)
            else:
                lw1 = rng.randint(int(tw * 0.55), tw - 56 * S)
                lw2 = rng.randint(int(tw * 0.25), int(tw * 0.6))
                d.rounded_rectangle((tx, ay + 2 * S, tx + lw1, ay + 16 * S), radius=4 * S, fill=bar)
                d.rounded_rectangle((tx, ay + 24 * S, tx + lw2, ay + 38 * S), radius=4 * S, fill=bar)
                d.rounded_rectangle((tx, ay + 50 * S, tx + int(tw * 0.35), ay + 60 * S), radius=4 * S, fill=bar)
        panels.append(panel)
    W = sum(p.width for p in panels)
    grid = Image.new("RGB", (W, max(p.height for p in panels)), DARK)
    x = 0
    for p in panels:
        grid.paste(p, (x, 0)); x += p.width
    grid.save(out, optimize=True)
    return {"grid": str(out), "position": pos, "competitors": len(pool)}


# ── Main ────────────────────────────────────────────────────────────────────
# ── Apprendimento (yt-thumb-learn): JSON per immagine e riferimenti di nicchia; solo additivo ─────────────────
def write_entry_json(path: Path, entry: dict) -> None:
    """<stem>_qa.json accanto al foglio: controlli, esito e metriche dell'immagine. Lo leggono yt-thumb-learn ingest
    (campi in cima) e yt-learn ingest (lista «images», come il JSON su stdout)."""
    try:
        yc.write_json(path, {"tool": "yt-thumb-qa", **entry, "images": [entry]})
    except Exception as e:  # noqa: BLE001 — mai bloccante
        yc.log(f"[qa] {path.name} non scritto: {e}")


def grid_auto(channel: str | None, images: list[str], warnings: list[str]) -> str | None:
    """--grid auto → <studio>/data/refs/<canale>/grid (aggiornamento mensile di yt-thumb-learn refs refresh).
    Canale da --channel o dal project.json del workdir delle immagini; riferimenti scaduti o assenti = niente griglia."""
    try:
        import thumb_learn as tl
    except Exception as e:  # noqa: BLE001
        warnings.append(f"--grid auto non disponibile ({e}): passa una cartella")
        return None
    if not channel:
        for raw in images:
            for parent in Path(raw).expanduser().resolve().parents:
                if (parent / "project.json").exists():
                    try:
                        channel = tl.channel_of_workdir(parent)
                    except ValueError:
                        channel = None
                    break
            if channel:
                break
    gdir, msg = tl.refs_grid(channel)
    if msg:
        warnings.append(msg + ": griglia saltata")
    return str(gdir) if gdir else None


def main() -> None:
    p = argparse.ArgumentParser(
        prog="yt-thumb-qa",
        description="Foglio QA (tile 720/500/360/216/168 dal file servito, chiaro, grigi, sfocata, catena del telefono), "
                    "controlli v2 bloccanti e mock della griglia YouTube per thumbnail.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Controlli (JSON images[].checks; livelli error/warn/pass/info/skip; soglie: knowledge/07-thumbnails.md §12.4):
  face_size          claim: volto principale ≥ 35 % (errore; < 40 % avviso; still: errore < 40 %); duo: ogni volto ≥ 30 %,
                     ospite ≥ host. Template claim: ritratto, scena, prova con volto (anche <slug>-ritratto…) o lever claim
  face_surround      ΔL* volto–intorno: errore < 10, avviso < 20 (R3; intorno a cavallo del volto: mediana per pixel di |ΔL*|)
  phrase_line_h      ogni riga della frase ≥ 12 % dell'altezza; keyword_line_h parola chiave ≥ 18 % (dal sidecar .render.json:
                     kind phrase|hook = frase, keyword|highlight = parola chiave; senza kind la parola chiave è la riga più alta,
                     e un esito negativo resta avviso; titolo a un solo corpo: il 18 % è un avviso)
  served_detail      Laplaciano del volto nel render ridotto a 720×405: avviso < 713, errore < 569
  silhouette_246     |ΔL*| della sagoma a 246 px: avviso < 25 · saliency_first: info · display_upscale: avviso oltre il tetto
  hook_words         3–6 parole (duo 3–4; e nel duo ogni riga ≥ 20 %, motivo G2: hook_size_reason)
  edge_dL_dark       ΔL* bordo ↔ pagina #0f0f0f: avviso < 25 salvo un elemento chiaro di cornice (≥ 10 % del perimetro);
                     edge_dL_light ↔ #ffffff: avviso < 20
  circle_contrast    cerchio d'accento ↔ capelli/volto adiacenti: errore < 10, avviso < 20 (+ ΔL* degli altri accenti)
  livello 2b (grade: mono): grade_uniform (curva unica sulle persone: residuo p95 avviso > 2.5 / errore > 5; scarto tra
                     curve avviso > 1 / errore > 2 ΔL*), grade_face (volto dalla curva comune: avviso > 2.5 / errore > 5),
                     grade_mono (C*ab p95 ≤ 12 su persone; plate: avviso), grade_landmarks (MediaPipe: avviso > 2 % salvo
                     sola curva ≤ 2 %, errore > 4 % della distanza tra gli occhi); skin_de00 saltato solo col mono
  text_contrast_168: avviso · render_checks: errori del sidecar di yt-thumb-render
Bloccano solo i render con sidecar (--gate auto); codice di uscita 1 se un controllo bloccante fallisce (--report-only: 0).
ok: false solo se un'immagine non si legge. Metriche: text_contrast_168_min (WCAG p95/p5 nelle righe del gancio a 168 px),
edge_dL_dark/light (ΔL* della cornice della tile dalla pagina), colorfulness_360, edge_density_360/168, busy_cells_share,
timestamp_zone_edge_density. Superfici 216/500: data/surfaces.json (Engaged Views, CC BY 4.0, adattato).

Esempio:
  yt-thumb-qa thumbs/renders/*.png --out thumbs/qa --grid thumbs/competitors --title "Ho chiuso il primo negozio"
""")
    p.add_argument("images", nargs="+", help="thumbnail da controllare (PNG/JPEG; meglio il master 3840×2160 col sidecar .render.json)")
    p.add_argument("--out", required=True, help="cartella di output dei fogli QA")
    p.add_argument("--grid", help="cartella con le thumbnail dei competitor (≥ 8 consigliate) per il mock 3×3; «auto» = i "
                                  "riferimenti di nicchia del canale (<studio>/data/refs/<canale>/grid, yt-thumb-learn refs "
                                  "refresh; non usati se più vecchi di 30 giorni)")
    p.add_argument("--channel", help="canale per --grid auto (default: dal project.json del workdir delle immagini)")
    p.add_argument("--title", help="titolo da mostrare sotto la candidata nel mock (default: barre finte)")
    p.add_argument("--text-box", action="append", default=[],
                   help="box del testo x,y,w,h (0–1 o px su 1280×720), ripetibile; default: dal sidecar .render.json")
    p.add_argument("--channel-name", default="Il tuo canale", help="nome canale sotto il titolo nel mock")
    p.add_argument("--pos", type=int, default=4, help="posizione della candidata nella griglia 0–8 (default 4 = centro)")
    p.add_argument("--seed", type=int, default=7, help="seme per l'ordine dei competitor")
    p.add_argument("--gate", choices=["auto", "always", "never"], default="auto",
                   help="quando i controlli bloccano: auto = solo render con sidecar (default), always, never")
    p.add_argument("--report-only", action="store_true", help="codice di uscita 0 anche con controlli bloccanti falliti")
    p.add_argument("--display-cap", type=float, help="tetto dell'ingrandimento al display (default 2.0; ripiego b: 1.5)")
    p.add_argument("--no-vision", action="store_true", help="niente thumbvision (volti senza sidecar, salienza)")
    p.add_argument("--no-landmarks", action="store_true",
                   help="niente MediaPipe sui render col grade mono (livello 2b): grade_landmarks resta «skip»")
    p.add_argument("--force", action="store_true", help="rifà anche se gli output sono più recenti")
    args = p.parse_args()

    t0 = time.time()
    outdir = Path(args.out).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    surfaces = load_surfaces()
    comps: list[Path] = []
    warnings: list[str] = []
    if not surfaces:
        warnings.append(f"superfici non trovate ({SURFACES_FILE}): tile 216/500 con i valori di ripiego")
    if args.grid == "auto":
        args.grid = grid_auto(args.channel, args.images, warnings)
    if args.grid:
        gdir = Path(args.grid).expanduser()
        if not gdir.is_dir():
            yc.fail(f"--grid: cartella non trovata: {gdir}")
        comps = sorted(q for q in gdir.iterdir() if q.suffix.lower() in IMG_EXT)
        if not comps:
            yc.fail(f"--grid: nessuna immagine in {gdir}")
        if len(comps) < 8:
            warnings.append(f"solo {len(comps)} competitor: la griglia li ripete")
    try:
        manual_boxes = [parse_box(b) for b in args.text_box]
    except ValueError as e:
        yc.fail(str(e))

    results, ok, all_pass = [], True, True
    # nomi dei fogli univoci: due input con lo stesso nome (es. renders/ e renders_remotion/) non si
    # sovrascrivono a vicenda → <cartella>-<nome>_qa.png
    srcs = [Path(raw).expanduser().resolve() for raw in args.images]
    # «renders/*.png» prende anche gli overlay di --debug e i derivati Spotify di --spotify: non sono thumbnail da
    # controllare (l'overlay ha i box disegnati sopra; il derivato è un ricampionamento del master, senza sidecar)
    derived = [q for q in srcs if q.name.endswith("_debug.png") or re.search(r"_spotify-\d+x\d+\.(png|jpe?g)$", q.name)]
    if derived and len(derived) < len(srcs):
        srcs = [q for q in srcs if q not in derived]
        warnings.append(f"saltati {len(derived)} overlay/derivati (_debug, _spotify-…): si controllano i master")
    stem_count: dict[str, int] = {}
    for s_ in srcs:
        stem_count[s_.stem] = stem_count.get(s_.stem, 0) + 1
    for src in srcs:
        stem = src.stem if stem_count[src.stem] == 1 else f"{src.parent.name}-{src.stem}"
        entry: dict = {"file": str(src)}
        if not src.exists():
            entry["error"] = "file non trovato"; ok = False; results.append(entry); continue
        try:
            im = Image.open(src).convert("RGB")
        except Exception as e:
            entry["error"] = f"immagine non leggibile: {e}"; ok = False; results.append(entry); continue
        entry["size"] = list(im.size)
        if abs(im.width / im.height - 16 / 9) > 0.02:
            warnings.append(f"{src.name}: proporzioni {im.width}×{im.height} non 16:9")
        if im.width < 1280:
            warnings.append(f"{src.name}: sotto 1280×720 → nei test A/B tutte le varianti scendono a 854×480")
        im = fit_thumb(im, 1280, 720)   # base di lavoro: tutte le misure derivano da qui (più veloce)
        data = sidecar(src)
        boxes = manual_boxes or boxes_from_sidecar(src, data)
        entry["text_box_source"] = "manuale" if manual_boxes else ("sidecar" if boxes else "nessuno")
        entry["metrics"] = metrics_for(im, boxes)
        gated = args.gate == "always" or (args.gate == "auto" and bool(data))
        checks, panel = run_checks(im, src, data, manual_boxes, gated=gated, use_vision=not args.no_vision,
                                   display_cap=args.display_cap, heatmap=outdir / f"{stem}_saliency.png",
                                   landmarks=not args.no_landmarks)
        checks += check_edges(entry["metrics"])
        checks.append(check_text_contrast(entry["metrics"].get("text_contrast_168_min") if boxes else None))
        gate(checks, gated)
        entry["checks"] = checks
        entry["gated"] = gated
        entry["errors"] = [c["message"] for c in checks if c["level"] == "error"]
        entry["warnings"] = [c["message"] for c in checks if c["level"] == "warn"]
        entry["pass"] = not entry["errors"]
        entry["metrics"]["face"] = panel
        if gated and not entry["pass"]:
            all_pass = False
        if not boxes and not panel.get("text_lines", {}).get("source"):
            warnings.append(f"{src.name}: nessun box del testo (sidecar senza metriche, es. motore remotion) → "
                            "contrasto e righe del gancio non misurati: passa --text-box x,y,w,h")
        for c in checks:
            if c["level"] in ("error", "warn"):
                warnings.append(f"{src.name}: {'ERRORE ' if c['level'] == 'error' else ''}{c['id']}: {c['message']}")
        sheet = outdir / f"{stem}_qa.png"
        legibility_sheet(im, src.name, sheet, checks, panel, surfaces)   # sempre: dipende dai controlli
        entry["sheet"] = str(sheet)
        c2 = data.get("checks2") or {}
        if c2:
            entry["render_checks"] = {"pass": data.get("pass"), "errors": data.get("errors"), "face_frac_max": c2.get("face_frac_max"),
                                      "heroes": [{k: h.get(k) for k in ("cutout", "face_frac", "upscale_vs_source", "eff_upscale", "edge")}
                                                 | {"crop_edges_inside": [e for e in h.get("crop_edges", []) if e.get("inside")]}
                                                 for h in c2.get("heroes", [])]}
        c100 = outdir / f"{stem}_100.png"
        if data and (args.force or not c100.exists() or c100.stat().st_mtime < src.stat().st_mtime):
            r100 = crops_100(src, data, c100)
            if r100:
                entry.update(r100)
        elif c100.exists():
            entry["crops_100"] = str(c100)
        if comps:
            grid = outdir / f"{stem}_grid.png"
            if args.force or not grid.exists() or grid.stat().st_mtime < src.stat().st_mtime:
                entry.update(grid_mock(im, comps, grid, args.title, args.pos, args.seed, args.channel_name))
            else:
                entry["grid"] = str(grid)
        results.append(entry)
        write_entry_json(outdir / f"{stem}_qa.json", entry)
        n_err = len(entry["errors"])
        yc.log(f"[qa] {src.name}: {'NON PASSA (' + str(n_err) + ' errori)' if n_err else 'passa'}"
               f"{'' if gated else ' (non bloccante)'}, {len(entry['warnings'])} avvisi")

    yc.emit(ok, outputs={"images": results, "dir": str(outdir)}, all_checks_pass=all_pass, warnings=warnings,
            seconds=round(time.time() - t0, 2))
    sys.exit(0 if ok and (all_pass or args.report_only) else 1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        yc.fail(f"{type(exc).__name__}: {exc}")
