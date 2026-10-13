"""yt-clips — motore Shorts: finestre da valutare, selezione, render 9:16 con sottotitoli.

Sottocomandi:
  windows WORKDIR [--len 90] [--overlap 30]
      shorts/windows.json: finestre di ~90 s con 30 s di sovrapposizione, allineate ai confini di
      frase del transcript (timeline del sorgente), con testo, righe con tempo e speaker. L'agente
      le valuta e scrive shorts/scores.json.
  select WORKDIR [--scores shorts/scores.json] [--max 8] [--min-score 0] [--crop auto|inset|speaker|stack]
      valida i punteggi, aggancia in/out ai confini di parola, scarta i doppioni (sovrapposizione
      >50% → resta il punteggio più alto), ordina, taglia a --max (mai riempire per quota), rileva il
      layout del master composito se il brand ne ha uno misurato (inset/wide/card, cambi a ±1 frame) e i
      cartelli di titolo bruciati nel master → shorts/clips.json. Senza layout misurato: una camera a
      tutto quadro (layout generico del brand neutro demo), crop speaker sul volto.
  render WORKDIR (--clip N | --all) [--style PRESET] [--crop …] [--face largest|left|right|center|speaker]
      taglia [in,out] dal sorgente (decodifica VideoToolbox), reframe 1080×1920 (inset = finestra
      verticale del master composito, se misurata; speaker = crop 9:16 sul volto via thumbvision, altrimenti posizioni di
      layout.json; stack = due crop impilati; la grafica PiP finita nel crop si toglie con delogo,
      --pip avoid per scendere sotto), sottotitoli ASS bruciati + hook nei primi 3 s posizionati
      fuori dai volti, accento scelto per contrasto (se il preset ne ha più di uno), loudnorm −14 LUFS (due
      passaggi, bilanciamento L/R automatico), H.264 high 1080×1920 30 fps → shorts/short_NN.mp4
      (+ short_NN.<stile>.mp4 se lo stile non è quello di serie del canale) e frame QA a 1 s e a metà in shorts/qa/.
  layout WORKDIR [--from A --to B --every 1]
      rileva i tratti di layout del sorgente → shorts/layout_spans.json.
  layout WORKDIR --measure --inset-at T --wide-at T [--card-at T]
      MISURA la geometria del layout (finestra inset, finestra wide, PiP, raggi degli angoli,
      firme di colore) dai frame 4K → layout.json del brand del canale nei brands_dirs dell'operatore
      (<brands_dir>/<brand o canale>/layout.json; mai nel plugin).

Esempi:
  yt-clips windows esempio/2026-10-13-ospite-paolo
  yt-clips select  esempio/2026-10-13-ospite-paolo --max 6
  yt-clips render  esempio/2026-10-13-ospite-paolo --clip 1 --style default
  (PRESET = default, il preset neutro del plugin, o un preset ASS di un brand: <brands_dir>/<slug>/ass/<preset>.json)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

import captions as cap
import ytcore
from ytcore import log

OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30
SMALL = (480, 270)  # risoluzione di campionamento per la classificazione del layout
EDGE_THR = 60       # salto RGB (somma dei 3 canali) tra pixel vicini che segna un bordo (ringing < 60)


# ── Layout: geometria del master (misurata per brand, generica nel brand demo) ──
def _home_tilde(p) -> str:
    """Percorso con ~ al posto della HOME: un layout.json non contiene mai /Users/<nome>/."""
    s, h = str(p), str(ytcore.HOME)
    return "~" + s[len(h):] if s == h or s.startswith(h + "/") else s


def layout_file(channel: str | None) -> Path:
    """layout.json usato per il canale: quello del suo brand (brand.slug del profilo), poi quello misurato per il
    canale (<brands_dir>/<canale>/layout.json), altrimenti il layout generico del brand neutro demo (una camera a
    tutto quadro, senza inset né PiP). Stesso risolutore di yt-portrait e yt-thumb-render (ytcore.layout_file)."""
    return ytcore.layout_file(channel)


def layout_write_path(channel: str) -> Path:
    """Dove scrive `layout --measure --write`: la cartella del brand del canale nei brands_dirs dell'operatore
    (o <primo brands_dir>/<canale>/ se il canale usa il brand demo). Mai il plugin."""
    brand = ytcore.channel_brand(channel)
    dest = ytcore.brand_file(brand if brand != ytcore.BUILTIN_BRAND else channel, "layout.json")
    try:
        inside_plugin = ytcore.BRANDS.resolve() in dest.resolve().parents
    except OSError:
        inside_plugin = True
    if inside_plugin:
        raise ValueError(f"il layout misurato andrebbe nel plugin ({dest}): configura brands_dirs "
                         "(yt-config --init) e rilancia, oppure usa --measure senza --write")
    return dest


def load_layout(channel: str | None) -> dict | None:
    p = layout_file(channel)
    return ytcore.read_json(p) if p.exists() else None


def has_probes(layout: dict | None) -> bool:
    """Il layout ha le sonde per classificare i tratti (inset/wide/card): solo i layout misurati."""
    return bool(layout and isinstance(layout.get("probes"), dict) and layout["probes"].get("boxes"))


def _probe_video(src: Path) -> dict:
    info = ytcore.ffprobe(src)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    return {"w": int(v["width"]), "h": int(v["height"]), "codec": v.get("codec_name"),
            "duration": float(info["format"]["duration"]), "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def _decode_args(src: Path) -> list[str]:
    """VideoToolbox per HEVC/H.264 (4K Main10 incluso); altrimenti decoder software."""
    return ["-hwaccel", "videotoolbox"]


def grab_frame(src: Path, t: float, size: tuple[int, int] | None = None) -> np.ndarray:
    """Un frame RGB (risoluzione piena o `size`) come array numpy uint8."""
    if size:
        w, h = size
    else:
        info = _probe_video(src)
        w, h = info["w"], info["h"]
    vf = f"scale={w}:{h}:flags=area" if size else "null"
    cmd = [ytcore.FFMPEG, "-v", "error", *_decode_args(src), "-ss", f"{t:.3f}", "-i", str(src),
           "-frames:v", "1", "-vf", vf, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    if len(raw) < w * h * 3:
        raise RuntimeError(f"Frame a {t:.2f}s non decodificato da {src}")
    return np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3)


def sample_frames(src: Path, t0: float, t1: float, step: float, size=SMALL) -> list[tuple[float, np.ndarray]]:
    """Frame piccoli in [t0, t1) con una sola decodifica (pipe rawvideo).

    Veloce: solo i keyframe (-skip_frame nokey, ~40× realtime sul master 4K con GOP ~1 s), tempi
    letti da showinfo. Se i keyframe sono troppo radi rispetto a `step` (es. proxy con GOP lungo)
    decodifica tutto e prende un frame ogni `step` s.
    """
    w, h = size
    dur = max(step, t1 - t0)
    frame_bytes = w * h * 3

    def _run(keyframes: bool) -> list[tuple[float, np.ndarray]]:
        vf = ("showinfo," if keyframes else f"fps=1/{step}:start_time=0,showinfo,") + f"scale={w}:{h}:flags=area"
        cmd = [ytcore.FFMPEG, "-hide_banner", "-nostats", "-v", "info", *(["-skip_frame", "nokey"] if keyframes else []),
               *_decode_args(src), "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-vf", vf,
               "-fps_mode", "passthrough", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Campionamento frame fallito: {proc.stderr.decode(errors='replace')[-500:]}")
        times = [float(m) for m in re.findall(rb"showinfo.*?pts_time:\s*(-?[\d.]+)", proc.stderr)]
        n = min(len(proc.stdout) // frame_bytes, len(times))
        frames = np.frombuffer(proc.stdout[: n * frame_bytes], np.uint8).reshape(n, h, w, 3)
        return [(round(t0 + times[k], 3), frames[k]) for k in range(n) if times[k] >= -1e-3]

    out = _run(keyframes=True)
    if len(out) >= 2 and (out[-1][0] - out[0][0]) / (len(out) - 1) <= 1.25 * step:
        kept, last = [], -math.inf
        for t, f in out:  # dirada se i keyframe sono più fitti di step
            if t - last >= 0.9 * step:
                kept.append((t, f))
                last = t
        return kept
    return _run(keyframes=False)


def _mode(values: list[int]) -> int:
    vals = np.asarray(values, int)
    return int(np.bincount(vals - vals.min()).argmax() + vals.min())


def measure_window(a: np.ndarray) -> dict:
    """Bbox della finestra video con angoli arrotondati sul fondo sfumato (pixel del canvas).

    Il gradiente pastello è liscio (salti tra pixel vicini < 5): scorrendo dall'esterno verso il
    centro, il primo salto > EDGE_THR è il bordo della finestra. Mode su molte righe/colonne.
    """
    img = a.astype(np.int32)
    H, W, _ = img.shape
    dh = np.abs(np.diff(img, axis=1)).sum(axis=2)
    dv = np.abs(np.diff(img, axis=0)).sum(axis=2)
    lefts, rights = [], []
    for y in range(int(H * 0.35), int(H * 0.65), 5):
        idx = np.where(dh[y, 2: W - 8] > EDGE_THR)[0] + 2
        if len(idx):
            lefts.append(idx[0] + 1)
            rights.append(idx[-1])
    if not lefts:
        raise ValueError("Nessun bordo verticale trovato: il frame non mostra una finestra sul gradiente")
    x0, x1 = _mode(lefts), _mode(rights)
    tops, bots = [], []
    for x in range(x0 + (x1 - x0) // 4, x1 - (x1 - x0) // 4, 5):
        idx = np.where(dv[2: H - 4, x] > EDGE_THR)[0] + 2
        if len(idx):
            tops.append(idx[0] + 1)
            bots.append(idx[-1])
    y0, y1 = _mode(tops), _mode(bots)
    # raggio: righe dall'alto prima che il bordo sinistro arrivi a x0
    r = 0
    for k in range(0, min(400, y1 - y0)):
        idx = np.where(dh[y0 + k, 2: W - 8] > EDGE_THR)[0] + 2
        if len(idx) and idx[0] + 1 <= x0 + 1:
            r = k
            break
    return {"x": int(x0), "y": int(y0), "w": int(x1 - x0 + 1), "h": int(y1 - y0 + 1), "r": int(r)}


def measure_pip(a: np.ndarray, x_from: int) -> dict | None:
    """Riquadro PiP (grafica in alto a destra) cercato a destra di x_from nella fascia alta."""
    img = a.astype(np.int32)
    H, W, _ = img.shape
    region = img[: int(H * 0.4), x_from: W - 8]
    dh = np.abs(np.diff(region, axis=1)).sum(axis=2) > EDGE_THR
    dv = np.abs(np.diff(region, axis=0)).sum(axis=2) > EDGE_THR
    rows = np.where(dh.sum(axis=1) > 3)[0]
    cols = np.where(dv.sum(axis=0) > 3)[0]
    if not len(rows) or not len(cols):
        return None
    y0, y1 = int(rows.min()), int(rows.max())
    # bordo sinistro/destro: mode dei primi/ultimi salti nelle righe interne
    lefts, rights = [], []
    for y in range(y0 + (y1 - y0) // 4, y1 - (y1 - y0) // 4, 3):
        idx = np.where(dh[y])[0]
        if len(idx):
            lefts.append(idx[0] + 1)
            rights.append(idx[-1])
    x0, x1 = _mode(lefts) + x_from, _mode(rights) + x_from
    tops, bots = [], []
    for x in range(x0 - x_from + (x1 - x0) // 4, x1 - x_from - (x1 - x0) // 4, 3):
        idx = np.where(dv[:, x])[0]
        if len(idx):
            tops.append(idx[0] + 1)
            bots.append(idx[-1])
    return {"x": int(x0), "y": int(_mode(tops)), "w": int(x1 - x0 + 1), "h": int(_mode(bots) - _mode(tops) + 1)}


# Zone sonda (coordinate normalizzate del canvas) per classificare il layout: dentro la finestra
# wide ma fuori dall'inset e sotto il PiP. Inset → gradiente; wide → video; card → carta.
PROBES = {"L": [0.06, 0.25, 0.30, 0.85], "R": [0.70, 0.25, 0.92, 0.85]}
GRID = (6, 4)


def patch_signature(small: np.ndarray, box: list[float]) -> dict:
    h, w, _ = small.shape
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    p = small[y0:y1, x0:x1].astype(np.float32)
    gx, gy = GRID
    cells = []
    for j in range(gy):
        for i in range(gx):
            c = p[j * p.shape[0] // gy:(j + 1) * p.shape[0] // gy, i * p.shape[1] // gx:(i + 1) * p.shape[1] // gx]
            cells.append([round(float(v), 1) for v in c.reshape(-1, 3).mean(axis=0)])
    luma = p @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    texture = float(np.abs(np.diff(luma, axis=1)).mean() + np.abs(np.diff(luma, axis=0)).mean())
    return {"cells": cells, "texture": round(texture, 2)}


def _sig_distance(sig: dict, ref: dict) -> float:
    a, b = np.asarray(sig["cells"]), np.asarray(ref["cells"])
    return float(np.abs(a - b).mean())


def classify_frame(small: np.ndarray, layout: dict) -> tuple[str, dict]:
    """'inset' | 'wide' | 'card' | 'other' con le distanze usate (per il debug)."""
    sigs = {k: patch_signature(small, box) for k, box in layout["probes"]["boxes"].items()}
    refs, thr = layout["probes"], layout["probes"]["thresholds"]
    d_inset = {k: _sig_distance(sigs[k], refs["inset"][k]) for k in sigs}
    d_card = {k: _sig_distance(sigs[k], refs["card"][k]) for k in sigs} if refs.get("card") else {}
    m = {"d_inset": {k: round(v, 1) for k, v in d_inset.items()},
         "d_card": {k: round(v, 1) for k, v in d_card.items()},
         "texture": {k: s["texture"] for k, s in sigs.items()}}
    near_inset = [d < thr["inset_max_dist"] for d in d_inset.values()]
    if all(near_inset):
        return "inset", m
    if d_card and d_card["R"] < thr["card_max_dist"] and sigs["R"]["texture"] < thr["card_max_texture"]:
        return "card", m
    if any(near_inset):
        return "other", m  # metà gradiente e metà video: template diverso o transizione
    return "wide", m


def title_overlay(small: np.ndarray) -> bool:
    """Cartello di titolo bruciato nel master (box bianco pieno con testo nero al centro, es.
    'CHI È PAOLO?', ~1 s): righe con una corsa di bianco puro ≥45% della larghezza utile."""
    h, w, _ = small.shape
    band = small[int(h * 0.30):int(h * 0.70), int(w * 0.10):int(w * 0.90)]
    white = band.min(axis=2) >= 240
    padded = np.pad(white, ((0, 0), (1, 1)), constant_values=False).astype(np.int8)
    runs = []
    for row in padded:
        edges = np.flatnonzero(np.diff(row))
        runs.append(int((edges[1::2] - edges[0::2]).max()) if len(edges) >= 2 else 0)
    runs = np.asarray(runs) / white.shape[1]
    return bool((runs >= 0.3).mean() >= 0.10 and runs.max() >= 0.45)


def overlay_spans(src: Path, t0: float, t1: float, step: float = 0.4) -> list[dict]:
    """Intervalli in cui il master mostra un cartello di titolo al centro (da evitare nei crop wide)."""
    hits = [t for t, f in sample_frames(src, t0, t1, step) if title_overlay(f)]
    spans: list[dict] = []
    for t in hits:
        if spans and t - spans[-1]["end"] <= step * 1.5:
            spans[-1]["end"] = round(t + step / 2, 3)
        else:
            spans.append({"start": round(max(t0, t - step / 2), 3), "end": round(min(t1, t + step / 2), 3)})
    return spans


def detect_spans(src: Path, t0: float, t1: float, layout: dict, step: float = 1.0,
                 refine: bool = True, fps: float = 30.0) -> tuple[list[dict], list[dict]]:
    """Tratti di layout uniformi in [t0, t1]: campioni ogni ~step s ('other' assorbito dai vicini),
    poi ogni cambio viene raffinato a ±1 frame con una bisezione su frame singoli."""
    samples = [{"t": t, "layout": classify_frame(f, layout)[0]} for t, f in sample_frames(src, t0, t1, step)]
    if not samples:
        return [{"start": t0, "end": t1, "layout": "unknown"}], []
    labels = [s["layout"] for s in samples]
    for k, lab in enumerate(labels):  # 'other' isolato (dissolvenze) → layout del vicino
        if lab == "other":
            prev = next((labels[j] for j in range(k - 1, -1, -1) if labels[j] != "other"), None)
            nxt = next((labels[j] for j in range(k + 1, len(labels)) if labels[j] != "other"), None)
            labels[k] = prev or nxt or "other"
    spans: list[dict] = []
    for k, (s, lab) in enumerate(zip(samples, labels)):
        if spans and spans[-1]["layout"] == lab:
            continue
        if spans:
            ta, tb = samples[k - 1]["t"], s["t"]
            cut = _bisect_switch(src, ta, tb, spans[-1]["layout"], lab, layout, fps) if refine else (ta + tb) / 2
            spans[-1]["end"] = cut
            spans.append({"start": cut, "end": t1, "layout": lab})
        else:
            spans.append({"start": t0, "end": t1, "layout": lab})
    spans[-1]["end"] = t1
    # tratti brevissimi (<1 s) fusi col precedente: non vale un cambio di inquadratura
    merged: list[dict] = []
    for sp in spans:
        if merged and sp["end"] - sp["start"] < 1.0:
            merged[-1]["end"] = sp["end"]
        elif merged and merged[-1]["layout"] == sp["layout"]:
            merged[-1]["end"] = sp["end"]
        else:
            merged.append(sp)
    if len(merged) > 1 and merged[0]["end"] - merged[0]["start"] < 1.0:
        merged[1]["start"] = merged[0]["start"]
        merged.pop(0)
    return [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()} for s in merged], samples


def _bisect_switch(src: Path, ta: float, tb: float, lab_a: str, lab_b: str, layout: dict, fps: float) -> float:
    """Primo frame con il nuovo layout tra ta (lab_a) e tb (lab_b), a ±1 frame."""
    lo, hi = ta, tb
    for _ in range(8):
        if hi - lo <= 1.0 / fps:
            break
        mid = (lo + hi) / 2
        try:
            lab = classify_frame(grab_frame(src, mid, SMALL), layout)[0]
        except Exception:  # noqa: BLE001 — frame corrotto: ci si accontenta del punto medio
            break
        if lab == lab_b:
            hi = mid
        elif lab == lab_a:
            lo = mid
        else:
            break
    return round(math.ceil(hi * fps - 1e-6) / fps, 3)


def _consensus(boxes: list[dict]) -> dict:
    """Mode campo per campo su più frame (un frame con ringing o un bordo poco contrastato non sposta il risultato)."""
    return {k: _mode([b[k] for b in boxes]) for k in boxes[0]}


def measure_layout(src: Path, t_inset: list[float], t_wide: list[float], t_card: float | None, channel: str) -> dict:
    """Misura la geometria del template su frame a piena risoluzione e le firme colore delle sonde."""
    info = _probe_video(src)
    fis, fws = [grab_frame(src, t) for t in t_inset], [grab_frame(src, t) for t in t_wide]
    insets, wides = [measure_window(f) for f in fis], [measure_window(f) for f in fws]
    inset, wide = _consensus(insets), _consensus(wides)
    pips = [p for p in (measure_pip(f, inset["x"] + inset["w"] + 40) for f in fis) if p]
    pip = _consensus(pips) if pips else None
    fi, fw = fis[0], fws[0]
    small = {k: np.asarray(_resize(f, SMALL)) for k, f in (("inset", fi), ("wide", fw))}
    probes = {"boxes": PROBES, "grid": list(GRID),
              "inset": {k: patch_signature(small["inset"], b) for k, b in PROBES.items()},
              "wide_example": {k: patch_signature(small["wide"], b)["texture"] for k, b in PROBES.items()}}
    card_tex = 3.0
    if t_card is not None:
        fc = grab_frame(src, t_card)
        probes["card"] = {k: patch_signature(np.asarray(_resize(fc, SMALL)), b) for k, b in PROBES.items()}
        card_tex = max(card_tex, probes["card"]["R"]["texture"] * 2 + 2)
    # soglie: metà della distanza tra inset e wide sulle sonde (minimo 8)
    d_iw = min(_sig_distance(patch_signature(small["wide"], b), probes["inset"][k]) for k, b in PROBES.items())
    probes["thresholds"] = {"inset_max_dist": round(max(8.0, min(20.0, d_iw / 2)), 1), "card_max_dist": 12.0,
                            "card_max_texture": round(card_tex, 1)}
    W, H = info["w"], info["h"]
    people = _measure_people(src, t_wide, wide, W, H)

    def norm_box(b):
        return {**b, "nx": round(b["x"] / W, 5), "ny": round(b["y"] / H, 5), "nw": round(b["w"] / W, 5), "nh": round(b["h"] / H, 5)}

    return {
        "version": 1, "brand": channel, "template": "podcast-composite",
        "canvas": {"w": W, "h": H},
        "measured": {"source": _home_tilde(src), "inset_at": t_inset, "wide_at": t_wide, "card_at": t_card,
                     "date": ytcore.today(),
                     "method": f"edge scan (Δ RGB > {EDGE_THR}) dal gradiente verso l'interno, mode su righe/colonne e tra frame",
                     "per_frame": {"inset": insets, "wide": wides, "pip": pips}},
        "inset": norm_box(inset),
        "wide": {**norm_box(wide), **people,
                 "people_note": "centri dei volti (frazioni della finestra wide, da sinistra) usati se thumbvision manca"},
        "pip": norm_box(pip) if pip else None,
        "probes": probes,
    }


def _measure_people(src: Path, times: list[float], wide: dict, W: int, H: int) -> dict:
    """Posizioni tipiche dei volti nella finestra wide (thumbvision sui frame di misura); default 0.2/0.48/0.8."""
    default = {"people_cx": [0.2, 0.48, 0.8], "people_cy": 0.28, "people_source": "default"}
    tv = ytcore.SWIFT_BIN
    if not tv.exists():
        return default
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for k, t in enumerate(times):
            p = Path(tmp) / f"w{k}.jpg"
            subprocess.run([ytcore.FFMPEG, "-v", "error", "-y", *_decode_args(src), "-ss", f"{t:.3f}", "-i", str(src),
                            "-frames:v", "1", "-vf", "scale=1920:-2", "-q:v", "3", "-update", "1", str(p)], check=True)
            files.append(str(p))
        try:
            data = json.loads(subprocess.run([str(tv), "faces", *files], capture_output=True, text=True, check=True).stdout)
        except Exception:  # noqa: BLE001
            return default
    rows = []
    for e in data:
        pts = []
        for f in e.get("faces") or []:
            x, y, w, h = f["box"]
            cx, cy = ((x + w / 2) * W - wide["x"]) / wide["w"], ((y + h / 2) * H - wide["y"]) / wide["h"]
            if 0 < cx < 1 and 0 < cy < 1:
                pts.append((cx, cy))
        rows.append(sorted(pts))
    n = _mode([len(r) for r in rows]) if rows else 0
    good = [r for r in rows if len(r) == n]
    if not n or not good:
        return default
    cx = [round(float(np.median([r[i][0] for r in good])), 3) for i in range(n)]
    cy = round(float(np.median([p[1] for r in good for p in r])), 3)
    return {"people_cx": cx, "people_cy": cy, "people_source": f"thumbvision faces su {len(good)} frame"}


def _resize(a: np.ndarray, size: tuple[int, int]):
    from PIL import Image

    return Image.fromarray(a).resize(size, Image.BOX)


def scale_layout(layout: dict, w: int, h: int) -> dict:
    """Geometria del layout riportata alla risoluzione del sorgente (es. proxy 720p)."""
    cw, ch = layout["canvas"]["w"], layout["canvas"]["h"]
    if (cw, ch) == (w, h):
        return layout
    sx, sy = w / cw, h / ch
    out = json.loads(json.dumps(layout))
    for key in ("inset", "wide", "pip"):
        b = out.get(key)
        if b:
            b["x"], b["w"] = round(b["x"] * sx), round(b["w"] * sx)
            b["y"], b["h"] = round(b["y"] * sy), round(b["h"] * sy)
            if "r" in b:
                b["r"] = round(b["r"] * sx)
    out["canvas"] = {"w": w, "h": h}
    return out


# ── Finestre (windows) ─────────────────────────────────────────────────────
def sentences(words: list[dict], max_len: float = 25.0) -> list[dict]:
    """Frasi dal transcript a parole: punteggiatura finale, cambio speaker o pausa ≥0.7 s.
    Frasi più lunghe di max_len si spezzano sulla pausa (o virgola) più ampia."""
    out, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        if nxt is None or cap.SENT_END.search(w["w"]) or nxt.get("speaker") != w.get("speaker") or nxt["start"] - w["end"] >= 0.7:
            out.extend(_split_long(cur, max_len))
            cur = []
    return [{"start": round(s[0]["start"], 3), "end": round(s[-1]["end"], 3), "speaker": s[0].get("speaker"),
             "text": " ".join(w["w"] for w in s), "n": len(s)} for s in out]


def _split_long(ws: list[dict], max_len: float) -> list[list[dict]]:
    if ws[-1]["end"] - ws[0]["start"] <= max_len or len(ws) < 4:
        return [ws]
    best, best_k = -1.0, None
    for k in range(1, len(ws)):
        gap = ws[k]["start"] - ws[k - 1]["end"] + (0.3 if cap.SOFT_PUNCT.search(ws[k - 1]["w"]) else 0)
        balance = min(ws[k - 1]["end"] - ws[0]["start"], ws[-1]["end"] - ws[k]["start"])
        score = gap + 0.01 * balance
        if score > best:
            best, best_k = score, k
    return _split_long(ws[:best_k], max_len) + _split_long(ws[best_k:], max_len)


def build_windows(sents: list[dict], length: float = 90.0, overlap: float = 30.0, names: dict | None = None) -> list[dict]:
    if not sents:
        return []
    windows, i, n = [], 0, len(sents)
    while i < n:
        start = sents[i]["start"]
        j = i
        while j < n - 1 and sents[j]["end"] - start < length:
            j += 1
        # se la frase che supera `length` sfora molto, meglio fermarsi alla frase prima (≥0.75×)
        if j > i and sents[j]["end"] - start > length and sents[j - 1]["end"] - start >= 0.75 * length \
                and abs(sents[j - 1]["end"] - start - length) < abs(sents[j]["end"] - start - length):
            j -= 1
        # ultima finestra: se resta una coda corta, allunga fino a 1.25× invece di lasciarla sola
        if j < n - 1 and sents[-1]["end"] - start <= 1.25 * length:
            j = n - 1
        end = sents[j]["end"]
        part = sents[i:j + 1]
        speakers = list(dict.fromkeys(s["speaker"] for s in part if s.get("speaker")))
        windows.append({
            "id": f"w{len(windows) + 1:03d}", "start": start, "end": end, "duration": round(end - start, 2),
            "text": " ".join(s["text"] for s in part), "speakers": speakers,
            "speaker_names": {s: names.get(s) for s in speakers} if names else {},
            "lines": [{"t": s["start"], "end": s["end"], "speaker": s.get("speaker"), "text": s["text"]} for s in part],
        })
        if j >= n - 1:
            break
        nxt = next((k for k in range(i + 1, n) if sents[k]["start"] >= end - overlap), j + 1)
        i = max(nxt, i + 1)
    return windows


# ── Selezione ──────────────────────────────────────────────────────────────
def snap_in_out(t_in: float, t_out: float, words: list[dict]) -> tuple[float, float]:
    """In/out sui confini di parola (mai dentro una parola) con padding 50 ms / 80 ms."""
    inside = [w for w in words if w["end"] > t_in - 0.25 and w["start"] < t_out + 0.25]
    if not inside:
        return t_in, t_out
    # una parola a cavallo del punto richiesto entra solo se il range ne copre almeno metà
    first = next((w for w in inside if (w["end"] - max(t_in, w["start"])) >= 0.5 * (w["end"] - w["start"])), inside[0])
    last = next((w for w in reversed(inside) if (min(t_out, w["end"]) - w["start"]) >= 0.5 * (w["end"] - w["start"])), inside[-1])
    prev = [w for w in words if w["end"] <= first["start"]]
    nxt = [w for w in words if w["start"] >= last["end"]]
    a = max(first["start"] - 0.05, (prev[-1]["end"] + 0.02) if prev else 0.0)
    b = min(last["end"] + 0.08, (nxt[0]["start"] - 0.02) if nxt else last["end"] + 0.08)
    return round(min(a, first["start"]), 3), round(max(b, last["end"]), 3)


def overlap_ratio(a: dict, b: dict) -> float:
    inter = max(0.0, min(a["out"], b["out"]) - max(a["in"], b["in"]))
    return inter / max(1e-6, min(a["out"] - a["in"], b["out"] - b["in"]))


def validate_scores(scores: Any, windows: dict[str, dict]) -> tuple[list[dict], list[dict], list[str]]:
    ok, rejected, warns = [], [], []
    if not isinstance(scores, list):
        raise ValueError("scores.json deve essere una lista di oggetti")
    for k, s in enumerate(scores):
        why = []
        sid = s.get("id") if isinstance(s, dict) else None
        if not isinstance(s, dict):
            rejected.append({"index": k, "reasons": ["non è un oggetto"]})
            continue
        if sid not in windows:
            why.append(f"id '{sid}' non presente in windows.json")
        try:
            score = float(s.get("score"))
            if not 0 <= score <= 100:
                why.append(f"score {score} fuori da 0–100")
        except (TypeError, ValueError):
            why.append("score mancante o non numerico")
            score = -1
        try:
            t_in, t_out = ytcore.parse_ts(s["in"]), ytcore.parse_ts(s["out"])
            dur = t_out - t_in
            if dur <= 0:
                why.append("out ≤ in")
            elif dur < 5:
                why.append(f"durata {dur:.1f} s < 5 s")
            elif dur > 180:
                why.append(f"durata {dur:.1f} s > 180 s (limite Shorts)")
            elif dur > 60:
                warns.append(f"{sid}: {dur:.0f} s, oltre il punto dolce 15–60 s")
        except (KeyError, TypeError, ValueError):
            why.append("in/out mancanti o non validi")
            t_in = t_out = 0.0
        hook = (s.get("hook_text") or "").strip()
        if hook and len(hook.split()) > 10:
            why.append(f"hook_text di {len(hook.split())} parole (max 10)")
        if sid in windows and not why:
            w = windows[sid]
            if t_in < w["start"] - 2 or t_out > w["end"] + 2:
                warns.append(f"{sid}: in/out ({t_in:.1f}–{t_out:.1f}) escono dalla finestra ({w['start']:.1f}–{w['end']:.1f})")
        if why:
            rejected.append({"id": sid, "reasons": why})
        else:
            ok.append({**s, "score": score, "in": t_in, "out": t_out, "hook_text": hook or None})
    return ok, rejected, warns


def dedupe(cands: list[dict], max_overlap: float = 0.5) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for c in sorted(cands, key=lambda c: -c["score"]):
        clash = next((k for k in kept if overlap_ratio(c, k) > max_overlap), None)
        if clash:
            dropped.append({"id": c["id"], "score": c["score"], "in": c["in"], "out": c["out"],
                            "reason": f"sovrapposto {overlap_ratio(c, clash):.0%} (>{max_overlap:.0%}) a {clash['id']} "
                                      f"{clash['in']:.1f}–{clash['out']:.1f} (score {clash['score']:.0f})"})
        else:
            kept.append(c)
    return kept, dropped


# ── Crop 9:16 ──────────────────────────────────────────────────────────────
def _even(v: float) -> int:
    return int(round(v / 2) * 2)


def crop_inset(L: dict) -> list[int]:
    """Finestra verticale senza angoli arrotondati né antialias, portata a 9:16 esatto."""
    b = L["inset"]
    x, y, w, h = b["x"] + 3, b["y"] + b["r"], b["w"] - 6, b["h"] - 2 * b["r"]
    if w / h > 9 / 16:
        nw = h * 9 / 16
        x, w = x + (w - nw) / 2, nw
    else:
        nh = w * 16 / 9
        y, h = y + (h - nh) / 2, nh
    return [_even(x), _even(y), _even(w), _even(h)]


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi) if hi >= lo else lo


def default_face(L: dict, idx: int | None = None) -> dict:
    """Volto 'tipico' dalle posizioni misurate in layout.json (frazioni del canvas)."""
    wb, (W, H) = L["wide"], (L["canvas"]["w"], L["canvas"]["h"])
    cxs = wb.get("people_cx") or [0.2, 0.48, 0.8]
    i = len(cxs) // 2 if idx is None else idx
    return {"cx": (wb["x"] + wb["w"] * cxs[i]) / W, "cy": (wb["y"] + wb["h"] * wb.get("people_cy", 0.28)) / H,
            "w": 0.07, "h": 0.12, "source": "layout.json (fallback)"}


def crop_speaker(L: dict, face: dict | None, aspect: float = 9 / 16, face_pos: float = 0.32,
                 base_frac: float = 1.0, min_frac: float = 0.6, pip_mode: str = "mask") -> list[int]:
    """Crop `aspect` nella finestra wide sul volto: volto a ~1/3 dall'alto, dentro gli angoli arrotondati.

    pip_mode 'mask': il crop può coprire la grafica PiP, che poi viene tolta con delogo (vedi
    pip_mask) — l'ospite a destra sta proprio sotto il PiP e altrimenti perderebbe la testa.
    pip_mode 'avoid': il crop scende sotto il PiP e, se il volto resta troppo in alto, si stringe
    (zoom fino a 1/min_frac) per lasciare aria sopra la testa.
    """
    wb, pip, (W, H) = L["wide"], L.get("pip"), (L["canvas"]["w"], L["canvas"]["h"])
    face = face or default_face(L)
    m, r = 4, wb["r"]
    ax0, ay0, ax1, ay1 = wb["x"] + m, wb["y"] + m, wb["x"] + wb["w"] - m, wb["y"] + wb["h"] - m
    area_h = ay1 - ay0
    fx, fy = face["cx"] * W, face["cy"] * H
    top = ay0
    x = y = w = h = 0.0
    for _ in range(3):
        avail = ay1 - top
        h = min(avail, area_h * base_frac)
        if fy - top < face_pos * h:  # volto troppo in alto: zoom per dargli aria sopra
            h = _clamp((fy - top) / face_pos, area_h * min_frac, h)
        w = h * aspect
        xa0, xa1 = (ax0 + r, ax1 - r) if h > area_h - 2 * r else (ax0, ax1)
        x = _clamp(fx - w / 2, xa0, xa1 - w)
        y = _clamp(fy - face_pos * h, top, ay1 - h)
        if pip_mode == "avoid" and pip and x < pip["x"] + pip["w"] and x + w > pip["x"] and y < pip["y"] + pip["h"]:
            top = pip["y"] + pip["h"] + 8  # il crop toccava la grafica PiP: scendo sotto
            continue
        break
    return [_even(x), _even(y), _even(w), _even(h)]


def pip_mask(L: dict, boxes: list[list[int]]) -> list[int] | None:
    """Rettangolo per delogo (pixel del sorgente) se un crop include la grafica PiP; None altrimenti.
    Il bordo campionato da delogo resta dentro la finestra (muro), non sul gradiente."""
    pip = L.get("pip")
    if not pip:
        return None
    for x, y, w, h in boxes:
        if x < pip["x"] + pip["w"] and x + w > pip["x"] and y < pip["y"] + pip["h"] and y + h > pip["y"]:
            W, H = L["canvas"]["w"], L["canvas"]["h"]
            rx, ry = max(2, pip["x"] - 4), max(2, pip["y"])
            return [rx, ry, min(pip["w"] + 8, W - rx - 2), min(pip["h"] + 4, H - ry - 2)]
    return None


def faces_for_span(src: Path, a: float, b: float, workdir: Path, tag: str, warnings: list) -> list[list[dict]]:
    """Volti (box normalizzati) su 3 frame del tratto via bin/thumbvision faces; [] se assente."""
    tv = ytcore.SWIFT_BIN
    if not (tv.exists() and tv.stat().st_mode & 0o111):
        if "thumbvision non disponibile" not in " ".join(warnings):
            warnings.append("thumbvision non disponibile: crop speaker su posizioni fisse di layout.json")
        return []
    out_dir = workdir / "shorts" / "qa" / "faces"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for k, f in enumerate((0.2, 0.5, 0.8)):
        t = a + (b - a) * f
        p = out_dir / f"{tag}_{k}.jpg"
        ytcore.run([ytcore.FFMPEG, "-v", "error", "-y", *_decode_args(src), "-ss", f"{t:.3f}", "-i", src,
                    "-frames:v", "1", "-vf", "scale=1920:-2", "-q:v", "3", "-update", "1", p], capture=True)
        files.append(p)
    try:
        proc = ytcore.run([tv, "faces", *files], capture=True)
        data = json.loads(proc.stdout)
    except Exception as exc:  # noqa: BLE001 — thumbvision è di un altro builder: degradare, non fallire
        warnings.append(f"thumbvision faces fallito ({exc.__class__.__name__}): posizioni fisse")
        return []
    entries = data if isinstance(data, list) else data.get("results", [])
    return [[f for f in (e.get("faces") or []) if f.get("box")] for e in entries]


def pick_face(faces_per_frame: list[list[dict]], L: dict, rule: str = "largest", region: str = "wide") -> dict | None:
    """Volto scelto (centro e dimensioni in frazioni del canvas), mediana sui frame.
    Solo volti dentro la finestra `region` e fuori dalla grafica PiP."""
    rb, (W, H), pip = L[region], (L["canvas"]["w"], L["canvas"]["h"]), L.get("pip")
    rows = []
    for faces in faces_per_frame:
        cands = []
        for f in faces:
            x, y, w, h = f["box"]
            cx, cy = x + w / 2, y + h / 2
            if not (rb["x"] <= cx * W <= rb["x"] + rb["w"] and rb["y"] <= cy * H <= rb["y"] + rb["h"]):
                continue
            if pip and pip["x"] <= cx * W <= pip["x"] + pip["w"] and cy * H <= pip["y"] + pip["h"]:
                continue  # volti stampati nella grafica PiP
            cands.append((cx, cy, w, h))
        if not cands:
            continue
        key = {"left": lambda c: c[0], "right": lambda c: -c[0], "center": lambda c: abs(c[0] - 0.5)}.get(rule)
        rows.append(min(cands, key=key) if key else max(cands, key=lambda c: c[2] * c[3]))
    if not rows:
        return None
    med = [float(np.median([r[i] for r in rows])) for i in range(4)]
    return {"cx": med[0], "cy": med[1], "w": med[2], "h": med[3], "source": f"thumbvision ({len(rows)} frame)"}


def stack_faces(faces_per_frame: list[list[dict]], L: dict) -> list[dict]:
    """Due volti per lo split impilato: il più a sinistra e il più a destra (o posizioni fisse)."""
    left, right = pick_face(faces_per_frame, L, "left"), pick_face(faces_per_frame, L, "right")
    if left and right and abs(left["cx"] - right["cx"]) > 0.1:
        return [left, right]
    n = len(L["wide"].get("people_cx") or [0, 0, 0])
    return [default_face(L, 0), default_face(L, n - 1)]


def face_in_output(face: dict | None, crop_box: list[int], L: dict, out_h: int = OUT_H, y_offset: int = 0) -> list[int] | None:
    """Box del volto [x, y, w, h] in pixel del Short (1080×1920) dato il crop."""
    if not face:
        return None
    W, H = L["canvas"]["w"], L["canvas"]["h"]
    x, y, w, h = crop_box
    s = out_h / h
    fx0, fy0 = (face["cx"] - face["w"] / 2) * W, (face["cy"] - face["h"] / 2) * H
    # +35% sopra il box Vision per capelli/fronte
    extra = face["h"] * H * 0.35
    return [round((fx0 - x) * s), round((fy0 - extra - y) * s) + y_offset, round(face["w"] * W * s),
            round((face["h"] * H + extra) * s)]


def speaker_turns(words: list[dict], a: float, b: float, min_turn: float = 2.0) -> list[dict]:
    """Turni di parola in [a, b] (speaker dal transcript); turni < min_turn assorbiti dal precedente."""
    turns: list[dict] = []
    for w in words:
        if not (a <= w["start"] < b) or not w.get("speaker"):
            continue
        if turns and turns[-1]["speaker"] == w["speaker"]:
            turns[-1]["end"] = w["end"]
        else:
            turns.append({"speaker": w["speaker"], "start": w["start"], "end": w["end"]})
    merged: list[dict] = []
    for t in turns:
        if merged and (t["end"] - t["start"] < min_turn or merged[-1]["speaker"] == t["speaker"]):
            merged[-1]["end"] = t["end"]
        else:
            merged.append(t)
    if not merged:
        return [{"speaker": None, "start": a, "end": b}]
    for x, y in zip(merged, merged[1:]):  # confine a metà della pausa tra i turni
        x["end"] = y["start"] = round((x["end"] + y["start"]) / 2, 3)
    merged[0]["start"], merged[-1]["end"] = a, b
    return merged


def plan_crops(clip: dict, L: dict, src: Path, workdir: Path, mode: str, face_rule: str, warnings: list,
               pip_mode: str = "mask") -> list[dict]:
    """Crop per ogni tratto di layout della clip (auto: inset→inset, wide→speaker) + volti nel Short.

    Con --face speaker e project.json "speaker_positions" (es. {"S0": "left", "S1": "right"}) i tratti
    wide vengono divisi per turno di parola e il crop segue chi parla."""
    out = []
    spans = clip.get("layout_spans") or [{"start": clip["in"], "end": clip["out"], "layout": clip.get("layout", "wide")}]
    positions = ytcore.load_project(workdir).get("speaker_positions") or {}
    if face_rule == "speaker":
        if not positions:
            warnings.append("--face speaker senza 'speaker_positions' in project.json: uso il volto più grande")
            face_rule = "largest"
        else:
            words, _ = cap.load_words(workdir)
            split = []
            for sp in spans:
                if sp["layout"] != "wide" or mode not in ("auto", "speaker"):
                    split.append(sp)
                    continue
                for t in speaker_turns(words, sp["start"], sp["end"]):
                    split.append({**sp, "start": t["start"], "end": t["end"], "speaker": t["speaker"]})
            spans = split
    for k, sp in enumerate(spans):
        lay = sp["layout"]
        m = mode if mode != "auto" else ("speaker" if lay == "wide" else "inset")
        if m == "inset" and lay == "wide":
            warnings.append(f"{clip['id']}: crop 'inset' richiesto su un tratto wide ({sp['start']:.1f}s): uso speaker")
            m = "speaker"
        if lay == "card":
            warnings.append(f"{clip['id']}: il tratto {sp['start']:.1f}–{sp['end']:.1f}s è la title card: crop centrale")
        if lay in ("inset", "card"):
            m = "inset"
        if m == "inset" and not L.get("inset"):
            warnings.append(f"{clip['id']}: il layout non ha una finestra inset (non misurato): uso il crop speaker")
            m = "speaker"
        entry = {"start": sp["start"], "end": sp["end"], "layout": lay, "crop": m}
        faces = faces_for_span(src, sp["start"], sp["end"], workdir, f"{clip['id']}_{k}", warnings) if lay != "card" else []
        if m == "inset":
            entry["crop_box"] = crop_inset(L)
            face = pick_face(faces, L, "largest", region="inset")
            entry["face"] = face
            entry["faces_out"] = [b for b in [face_in_output(face, entry["crop_box"], L)] if b]
        elif m == "stack":
            f1, f2 = stack_faces(faces, L)
            half = OUT_H // 2
            # i crop dello split sono già stretti: stanno sotto il PiP senza delogo (niente aloni)
            boxes = [crop_speaker(L, f, aspect=OUT_W / half, face_pos=0.4, base_frac=0.62, min_frac=0.4, pip_mode="avoid")
                     for f in (f1, f2)]
            entry["crop_box"], entry["faces"] = boxes, [f1, f2]
            entry["faces_out"] = [b for b in [face_in_output(f1, boxes[0], L, half), face_in_output(f2, boxes[1], L, half, half)] if b]
            entry["delogo"] = pip_mask(L, boxes)
        else:
            rule = positions.get(sp.get("speaker"), "largest") if face_rule == "speaker" else face_rule
            face = pick_face(faces, L, rule) or default_face(L)
            entry["speaker"], entry["face_rule"] = sp.get("speaker"), rule
            entry["crop_box"] = crop_speaker(L, face, pip_mode=pip_mode)
            entry["face"] = face
            entry["faces_out"] = [face_in_output(face, entry["crop_box"], L)]
            entry["delogo"] = pip_mask(L, [entry["crop_box"]])
        out.append(entry)
    return out


def place_text(crops: list[dict], style: str, hook: str | None, position: str, warnings: list, clip_id: str,
               channel: str | None = None) -> dict:
    """Margini di hook e sottotitoli che non coprono i volti (pixel del Short).

    Hook: nei primi 3 s, in alto; se coprirebbe il volto va sopra (se c'è spazio) o sotto il volto.
    Sottotitoli: fascia in basso (default ~70% dell'altezza); se il volto scende fin lì si abbassano
    fino al limite dell'interfaccia Shorts (≥380 px dal fondo)."""
    preset = cap.load_preset(style)
    cc, hk = preset["caption"], preset.get("hook", {})
    out: dict[str, Any] = {}
    if crops and all(c["crop"] == "stack" for c in crops):
        # split impilato: sottotitoli in fondo alla metà alta (sul busto di chi sta sopra), mai sulla
        # testa di chi sta sotto la giuntura
        out["caption_margin_v"] = OUT_H // 2 + 24
    elif position == "bottom":
        cap_h = 2 * cc["size"] * 1.15
        mv = int(cc["margin_v"])
        face_bottom = max((b[1] + b[3] for c in crops for b in c.get("faces_out") or []), default=None)
        if face_bottom is not None and OUT_H - mv - cap_h < face_bottom + 30:
            mv_new = int(OUT_H - (face_bottom + 30) - cap_h)
            out["caption_margin_v"] = max(380, mv_new)
            if mv_new < 380:
                warnings.append(f"{clip_id}: il volto scende fino a y={face_bottom}: sottotitoli possono toccarlo")
    if hook:
        first = next((c for c in crops if c["start"] <= crops[0]["start"] + 0.01), crops[0])
        boxes = first.get("faces_out") or []
        lines = cap.hook_lines(hook, preset, cap.preset_tokens(preset, style, channel))
        hh = len(lines) * hk["size"] * 1.2 + 2 * hk.get("box_padding", 16)
        mv = int(hk["margin_v"])
        safe_top = 150

        def clash(top: float) -> dict | None:
            return next((b for b in boxes if top < b[1] + b[3] + 25 and top + hh > b[1] - 25), None)

        b = clash(mv)
        if b:
            above = b[1] - 30 - hh
            below = b[1] + b[3] + 40
            cap_top = OUT_H - out.get("caption_margin_v", cc["margin_v"]) - 2 * cc["size"] * 1.15
            if above >= safe_top:
                out["hook_margin_v"] = int(above)
            elif below + hh < cap_top - 30:
                out["hook_margin_v"] = int(below)
            else:
                warnings.append(f"{clip_id}: l'hook copre in parte il volto (nessuno spazio libero)")
        out["hook_lines"] = len(lines)
    return out


# ── Audio ──────────────────────────────────────────────────────────────────
def _audio_in(src: Path, t_in: float, dur: float, dec_args: list[str] | None = None) -> list[str]:
    # decoder AAC dalla policy centrale (ytcore.aac_decoder_args): di norma il nativo (float, niente clipping)
    return ["-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}", *(dec_args or []), "-i", str(src)]


def clip_audio(src: Path, t_in: float, dur: float, tmpdir: Path,
               workdir: Path | None = None) -> tuple[Path, dict]:
    """Audio della clip con la stessa catena del montato (loudnorm.normalize di yt-loudnorm).

    Bilanciamento L/R automatico: in molti master da podcast L e R sono due microfoni diversi (es. microfono a
    mano dell'host, lavalier dell'ospite, con 1–2 ms di rientro), quindi una somma con guadagno farebbe filtro a pettine;
    decide_balance sceglie automix/mono/keep. Poi −14 LUFS / −1.5 dBTP, lineare quando possibile, WAV 48 kHz.
    """
    import loudnorm as ln

    raw = tmpdir / "clip_raw.wav"
    dec = ytcore.aac_decoder_args(workdir, {"path": str(src)})
    ytcore.run([ytcore.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", *_audio_in(src, t_in, dur, dec),
                "-vn", "-af", ln.ASYNC, "-c:a", "pcm_f32le", str(raw)])
    mixed = tmpdir / "clip_mix.wav"
    rep = ln.normalize(raw, mixed, target=-14.0, tp=-1.5, lra=11.0, balance="auto", force=True)
    b = rep.get("balance") or {}
    info = {k: b[k] for k in ("decision", "reason", "diff_db", "diff_active_db", "gains_db") if k in b}
    info["mode"] = b.get("decision")
    info["normalization"] = (rep.get("pass2") or {}).get("normalization_type")
    return mixed, info


def measure_output_loudness(path: Path) -> dict:
    proc = subprocess.run([ytcore.FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-vn",
                           "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    tail = proc.stderr[proc.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s*(-?[\d.]+) LUFS", tail)
    tp = re.search(r"Peak:\s*(-?[\d.]+) dBFS", tail)
    return {"I": float(i.group(1)) if i else None, "TP": float(tp.group(1)) if tp else None}


# ── Render ─────────────────────────────────────────────────────────────────
def _filter_path(p: Path) -> str:
    """Percorso dentro un filtergraph ffmpeg (escape di : , ' \\)."""
    return str(p).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def build_video_graph(crops: list[dict], t_in: float, ass: Path | None, preset: dict | None = None) -> str:
    """Un ramo per tratto (trim → crop → scale 1080×1920, o due crop impilati), concat, poi ASS."""
    n = len(crops)
    parts = [f"[0:v]split={n}" + "".join(f"[s{k}]" for k in range(n)) if n > 1 else "[0:v]null[s0]"]
    for k, c in enumerate(crops):
        a, b = c["start"] - t_in, c["end"] - t_in
        trim = f"trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS," if n > 1 else ""
        if c.get("delogo"):
            dx, dy, dw, dh = c["delogo"]
            trim += f"delogo=x={dx}:y={dy}:w={dw}:h={dh},"  # toglie la grafica PiP finita nel crop
        if c["crop"] == "stack":
            (x1, y1, w1, h1), (x2, y2, w2, h2) = c["crop_box"]
            parts.append(f"[s{k}]{trim}split=2[t{k}][b{k}]")
            parts.append(f"[t{k}]crop={w1}:{h1}:{x1}:{y1},scale={OUT_W}:{OUT_H // 2}:flags=lanczos,setsar=1[tt{k}]")
            parts.append(f"[b{k}]crop={w2}:{h2}:{x2}:{y2},scale={OUT_W}:{OUT_H // 2}:flags=lanczos,setsar=1[bt{k}]")
            parts.append(f"[tt{k}][bt{k}]vstack=inputs=2,format=yuv420p[c{k}]")
        else:
            x, y, w, h = c["crop_box"]
            parts.append(f"[s{k}]{trim}crop={w}:{h}:{x}:{y},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1,format=yuv420p[c{k}]")
    chain = "".join(f"[c{k}]" for k in range(n)) + (f"concat=n={n}:v=1:a=0," if n > 1 else "null,")
    chain += f"fps={OUT_FPS}"
    if ass:
        chain += f",subtitles=filename='{_filter_path(ass)}':fontsdir='{_filter_path(cap.fonts_dir(preset))}'"
    chain += ",format=yuv420p[v]"
    parts.append(chain)
    return ";".join(parts)


def render_clip(workdir: Path, clip: dict, *, style: str, accent: str | None, crop_mode: str, face_rule: str,
                hook: bool, drop_fillers: bool, crf: int, force: bool, out_name: str, warnings: list,
                pip_mode: str = "mask") -> dict:
    project = ytcore.load_project(workdir)
    src = ytcore.source_path(workdir)
    info = _probe_video(src)
    L = load_layout(project.get("channel"))
    if L is None:
        raise FileNotFoundError(f"layout.json mancante per il canale {project.get('channel')} (nemmeno quello del "
                                f"brand {ytcore.BUILTIN_BRAND}): esegui 'yt-clips layout --measure … --write'")
    L = scale_layout(L, info["w"], info["h"])
    t_in, t_out = float(clip["in"]), float(clip["out"])
    dur = t_out - t_in
    shorts = workdir / "shorts"
    out = shorts / f"{out_name}.mp4"
    ass = shorts / f"{out_name}.ass"
    adec = ytcore.aac_decoder_policy(workdir, {"path": str(src)})["decoder"]
    # il decoder entra nella firma solo se non è quello storico (aac_at): le clip già fatte con aac_at
    # restano valide finché la decisione non cambia
    sig = cap.signature(clip["in"], clip["out"], clip.get("hook_text") if hook else None, style, accent, crop_mode,
                        face_rule, drop_fillers, crf, clip.get("layout_spans"), pip_mode,
                        *([f"adec:{adec}"] if adec != "aac_at" else []))
    inputs = [src, workdir / "analysis" / "transcript.words.json", workdir / "shorts" / "clips.json", Path(__file__),
              Path(cap.__file__), cap.preset_path(style) or cap.ASS_DIR / f"{style}.json",
              layout_file(project.get("channel")),
              ytcore.brand_file(cap.preset_brand(cap.load_preset(style), style, project.get("channel")), "tokens.json")]
    if not force and cap.up_to_date(workdir, [out], inputs, sig):
        log(f"{out.name}: aggiornato, salto")
        return {"id": clip["id"], "out": str(out), "skipped": True}

    crops = plan_crops(clip, L, src, workdir, crop_mode, face_rule, warnings, pip_mode)
    position = "bottom"
    accent_pick = None
    if accent in (None, "auto"):
        accent, accent_pick = pick_accent(src, crops, style, position, project.get("channel"))
    hook_text = clip.get("hook_text") if hook else None
    placement = place_text(crops, style, hook_text, position, warnings, clip["id"], project.get("channel"))
    ass_info = cap.make_ass(workdir, (t_in, t_out), style=style, out=ass, timeline_arg="none",
                            hook=hook_text, accent=accent, drop_fillers=drop_fillers, position=position,
                            hook_margin_v=placement.get("hook_margin_v"),
                            caption_margin_v=placement.get("caption_margin_v"), warnings=warnings)

    graph = build_video_graph(crops, t_in, ass, cap.load_preset(style)) + ";[1:a]aresample=48000[a]"
    tmp = out.with_suffix(".part.mp4")
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix=".audio-", dir=shorts) as td:
        mix, bal = clip_audio(src, t_in, dur, Path(td), workdir=workdir)
        cmd = [ytcore.FFMPEG, "-hide_banner", "-y", *_decode_args(src), "-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}",
               "-i", src, "-i", mix, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
               "-r", str(OUT_FPS), "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{dur:.3f}", tmp]
        ytcore.run(cmd, logfile=workdir / "logs" / "clips_render.log")
    tmp.replace(out)
    elapsed = round(time.time() - t0, 1)
    loud = measure_output_loudness(out)
    qa = qa_frames(out, shorts / "qa", out_name, dur)
    cap.stamp(workdir, [out], sig)
    probe = ytcore.ffprobe(out)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    return {"id": clip["id"], "out": str(out), "ass": str(ass), "duration": round(float(probe["format"]["duration"]), 2),
            "video": f"{v['width']}x{v['height']} {v.get('codec_name')} {v.get('profile')} {v.get('r_frame_rate')}",
            "crops": crops, "placement": placement, "audio_balance": bal, "audio_decoder": adec, "loudness_out": loud, "captions": ass_info,
            "accent_pick": accent_pick,
            "qa_frames": qa,
            "render_seconds": elapsed}


def _rel_lum(rgb) -> float:
    c = [v / 255 for v in rgb]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast_ratio(a, b) -> float:
    la, lb = sorted((_rel_lum(a), _rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def pick_accent(src: Path, crops: list[dict], style: str, position: str,
                channel: str | None = None) -> tuple[str | None, dict | None]:
    """Con più accenti nel preset sceglie quello più leggibile sullo sfondo della fascia sottotitoli (es. su un
    muro saturo vince l'accento che ci contrasta di più). Un solo accento per composizione."""
    preset = cap.load_preset(style)
    accents = preset.get("accents", {})
    if len(accents) < 2:
        return None, None
    tokens = cap.preset_tokens(preset, style, channel)
    main = max(crops, key=lambda c: c["end"] - c["start"])
    box = main["crop_box"][0] if main["crop"] == "stack" else main["crop_box"]
    x, y, w, h = box
    frame = grab_frame(src, (main["start"] + main["end"]) / 2)
    band = (0.40, 0.60) if position == "center" else (0.58, 0.76)
    region = frame[int(y + h * band[0]):int(y + h * band[1]), int(x):int(x + w)]
    bg = [float(v) for v in region.reshape(-1, 3).mean(axis=0)]
    scores = {}
    for name, spec in accents.items():
        hexv = cap._color(spec, tokens).lstrip("#")
        scores[name] = round(contrast_ratio([int(hexv[i:i + 2], 16) for i in (0, 2, 4)], bg), 2)
    best = max(scores, key=scores.get)
    return best, {"background_rgb": [round(v) for v in bg], "contrast": scores, "chosen": best}


def qa_frames(video: Path, qa_dir: Path, name: str, dur: float) -> list[str]:
    qa_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for label, t in (("t01.0", 1.0), ("mid", dur / 2)):
        p = qa_dir / f"{name}_{label}.jpg"
        ytcore.run([ytcore.FFMPEG, "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                    "-q:v", "3", "-update", "1", p], capture=True)
        out.append(str(p))
    return out


# ── Sottocomandi ───────────────────────────────────────────────────────────
def cmd_windows(args, workdir: Path, warnings: list) -> None:
    words, meta = cap.load_words(workdir, args.words)
    out = workdir / "shorts" / "windows.json"
    sig = cap.signature("windows", args.len, args.overlap)
    if not args.force and cap.up_to_date(workdir, [out], [Path(meta["path"]), Path(__file__)], sig):
        ytcore.emit(True, outputs={"windows": str(out)}, skipped=True, windows=len(ytcore.read_json(out)), warnings=warnings)
        return
    names = ytcore.load_project(workdir).get("speakers") or {}
    if not any(w.get("speaker") for w in words):
        warnings.append("transcript senza speaker (yt-speakers non eseguito): 'speakers' vuoto")
    sents = sentences(words)
    wins = build_windows(sents, args.len, args.overlap, names)
    ytcore.write_json(out, wins)
    cap.stamp(workdir, [out], sig)
    durs = [w["duration"] for w in wins]
    ytcore.emit(True, outputs={"windows": str(out)}, windows=len(wins), sentences=len(sents),
                duration_range=[min(durs), max(durs)] if durs else None,
                next_step="L'agente valuta OGNI finestra 0–100 e scrive shorts/scores.json, poi 'yt-clips select'",
                warnings=warnings)


def cmd_select(args, workdir: Path, warnings: list) -> None:
    project = ytcore.load_project(workdir)
    wpath = workdir / "shorts" / "windows.json"
    spath = Path(args.scores) if args.scores else workdir / "shorts" / "scores.json"
    spath = spath if spath.is_absolute() else workdir / spath
    if not wpath.exists():
        ytcore.fail("shorts/windows.json mancante: esegui prima 'yt-clips windows'")
    if not spath.exists():
        ytcore.fail(f"Punteggi mancanti: {spath} (li scrive l'agente)")
    out = workdir / "shorts" / "clips.json"
    sig = cap.signature("select", args.max, args.min_score, args.crop, args.no_layout)
    if not args.force and cap.up_to_date(workdir, [out], [wpath, spath, Path(__file__)], sig):
        ytcore.emit(True, outputs={"clips": str(out)}, skipped=True, clips=len(ytcore.read_json(out)["clips"]), warnings=warnings)
        return
    windows = {w["id"]: w for w in ytcore.read_json(wpath)}
    valid, rejected, warns = validate_scores(ytcore.read_json(spath), windows)
    warnings += warns
    if not valid:
        ytcore.fail("Nessun punteggio valido in scores.json", rejected=rejected, warnings=warnings)
    words, _ = cap.load_words(workdir)
    for c in valid:
        c["in_requested"], c["out_requested"] = c["in"], c["out"]
        c["in"], c["out"] = snap_in_out(c["in"], c["out"], words)
    below = [c for c in valid if c["score"] < args.min_score]
    cands = [c for c in valid if c["score"] >= args.min_score]
    kept, dropped = dedupe(cands)
    capped = kept[args.max:] if args.max else []
    kept = kept[: args.max] if args.max else kept

    src = ytcore.source_path(workdir)
    layout = load_layout(project.get("channel"))
    if layout is None and not args.no_layout:
        warnings.append(f"layout.json assente per '{project.get('channel')}': layout non rilevato (crop speaker)")
    elif layout is not None and not has_probes(layout) and not args.no_layout:
        log(f"layout {layout.get('template') or 'generico'} senza sonde: una sola inquadratura (wide), crop speaker")
    proxy = workdir / "analysis" / "proxy.mp4"
    scan_src = proxy if proxy.exists() else src

    clips = []
    for rank, c in enumerate(kept, 1):
        clip = {"id": f"short_{rank:02d}", "rank": rank, "window": c["id"], "score": c["score"], "sub": c.get("sub"),
                "in": c["in"], "out": c["out"], "duration": round(c["out"] - c["in"], 2),
                "in_requested": c["in_requested"], "out_requested": c["out_requested"],
                "hook_text": c.get("hook_text"), "why": c.get("why"),
                "text": " ".join(w["w"] for w in words if c["in"] <= w["start"] < c["out"])}
        if has_probes(layout) and not args.no_layout:
            spans, _ = detect_spans(scan_src, c["in"], c["out"], layout, step=1.0)
            clip["layout_spans"] = spans
            kinds = {s["layout"] for s in spans}
            clip["layout"] = kinds.pop() if len(kinds) == 1 else "mixed"
        else:
            clip["layout"] = "wide" if layout and not args.no_layout else "unknown"
            clip["layout_spans"] = [{"start": c["in"], "end": c["out"], "layout": "wide"}]
        if not args.no_layout:
            clip["title_overlays"] = overlay_spans(scan_src, c["in"], c["out"])
            for ov in clip["title_overlays"]:
                warnings.append(f"{clip['id']}: cartello di titolo del master a {ov['start']:.1f}–{ov['end']:.1f}s "
                                f"(sorgente): nei crop wide resta tagliato, valuta di spostare in/out")
        main = max(clip["layout_spans"], key=lambda s: s["end"] - s["start"])
        mode = args.crop if args.crop != "auto" else ("speaker" if main["layout"] == "wide" else "inset")
        clip["crop"] = mode
        clip["crop_request"] = args.crop  # render: auto = crop per tratto (inset→inset, wide→speaker)
        if layout:
            L = scale_layout(layout, *(lambda i: (i["w"], i["h"]))(_probe_video(src)))
            if mode == "inset" and not L.get("inset"):
                mode = clip["crop"] = "speaker"
            clip["crop_box"] = crop_inset(L) if mode == "inset" else (crop_speaker(L, None) if mode == "speaker" else None)
            clip["crop_box_note"] = "provvisorio: render ricalcola sui volti (thumbvision) per i tratti wide"
        clips.append(clip)
        log(f"{clip['id']}: {c['id']} score {c['score']:.0f}  {c['in']:.2f}–{c['out']:.2f}  layout {clip['layout']}")
    data = {"version": 1, "source_timeline": "source", "generated": ytcore.today(), "max": args.max,
            "min_score": args.min_score, "clips": clips, "rejected": rejected,
            "dropped_overlap": dropped, "dropped_cap": [{"id": c["id"], "score": c["score"]} for c in capped],
            "below_min_score": [{"id": c["id"], "score": c["score"]} for c in below]}
    ytcore.write_json(out, data)
    cap.stamp(workdir, [out], sig)
    ytcore.emit(True, outputs={"clips": str(out)}, clips=len(clips), rejected=len(rejected), dropped_overlap=len(dropped),
                dropped_cap=len(capped), below_70=[c["id"] for c in clips if c["score"] < 70],
                layouts={c["id"]: c["layout"] for c in clips}, warnings=warnings)


def cmd_render(args, workdir: Path, warnings: list) -> None:
    project = ytcore.load_project(workdir)
    cpath = workdir / "shorts" / "clips.json"
    if not cpath.exists():
        ytcore.fail("shorts/clips.json mancante: esegui 'yt-clips select'")
    clips = ytcore.read_json(cpath)["clips"]
    if args.all:
        chosen = clips
    elif args.clip:
        chosen = []
        for token in str(args.clip).split(","):
            token = token.strip()
            want = f"short_{int(token):02d}" if token.isdigit() else token
            c = next((c for c in clips if c["id"] == want), None)
            if c is None:
                ytcore.fail(f"Clip '{token}' non trovata in clips.json ({[c['id'] for c in clips]})")
            chosen.append(c)
    else:
        ytcore.fail("Indica --clip N (o più: 1,3) oppure --all")
    channel = project.get("channel")
    channel_style = cap.default_style(channel)          # stile di serie del canale: short_NN.mp4 senza suffisso
    style = args.style or channel_style
    if args.hook is not None:
        if len(chosen) != 1:
            ytcore.fail("--hook vale per una sola clip")
        if len(args.hook.split()) > 10:
            ytcore.fail(f"--hook di {len(args.hook.split())} parole: massimo 10")
        chosen = [{**chosen[0], "hook_text": args.hook.strip() or None}]
    results = []
    for c in chosen:
        name = c["id"] if style == channel_style else f"{c['id']}.{style}"
        log(f"── render {name} ({c['in']:.2f}–{c['out']:.2f}, {c['out'] - c['in']:.1f} s, stile {style})")
        results.append(render_clip(workdir, c, style=style, accent=args.accent,
                                   crop_mode=args.crop or c.get("crop_request") or "auto",
                                   face_rule=args.face, hook=not args.no_hook, drop_fillers=not args.keep_fillers,
                                   crf=args.crf, force=args.force, out_name=name, warnings=warnings,
                                   pip_mode=args.pip))
    for r in results:
        lo = r.get("loudness_out") or {}
        if lo.get("I") is not None and abs(lo["I"] + 14) > 1.0:
            warnings.append(f"{r['id']}: loudness {lo['I']} LUFS (atteso −14 ±1)")
    ytcore.emit(True, outputs={r["id"]: r["out"] for r in results}, renders=results,
                next_step="Leggi i frame QA (1 s e metà): testo non tagliato, accenti, sottotitoli non sul volto",
                warnings=warnings)


def cmd_layout(args, workdir: Path, warnings: list) -> None:
    project = ytcore.load_project(workdir)
    channel = args.channel or project.get("channel")
    src = ytcore.source_path(workdir)
    if args.measure:
        if args.inset_at is None or args.wide_at is None:
            ytcore.fail("--measure vuole --inset-at T e --wide-at T (tempi con layout inset e wide)")
        times = lambda v: [ytcore.parse_ts(x) for x in str(v).split(",") if x.strip()]  # noqa: E731
        L = measure_layout(src, times(args.inset_at), times(args.wide_at),
                           ytcore.parse_ts(args.card_at) if args.card_at else None, channel)
        try:
            dest = layout_write_path(channel) if args.write else workdir / "shorts" / "layout.measured.json"
        except ValueError as exc:
            ytcore.fail(str(exc))
        ytcore.write_json(dest, L)
        # verifica: i frame di misura devono classificarsi come attesi
        check = {}
        for kind, t in (("inset", args.inset_at), ("wide", args.wide_at), ("card", args.card_at)):
            if t is not None:
                small = grab_frame(src, times(t)[0], SMALL)
                check[kind] = classify_frame(small, L)
        ytcore.emit(True, outputs={"layout": str(dest)}, inset=L["inset"], wide=L["wide"], pip=L["pip"],
                    thresholds=L["probes"]["thresholds"], self_check={k: v[0] for k, v in check.items()},
                    self_check_metrics={k: v[1] for k, v in check.items()}, warnings=warnings)
        return
    L = load_layout(channel)
    if L is None:
        ytcore.fail(f"layout.json mancante per {channel}: esegui con --measure")
    if not has_probes(L):
        ytcore.fail(f"il layout {layout_file(channel)} non è misurato (niente sonde: una sola inquadratura). Per un "
                    "master composito misuralo con --measure --inset-at T --wide-at T --write")
    info = _probe_video(src)
    proxy = workdir / "analysis" / "proxy.mp4"
    scan_src = proxy if proxy.exists() and not args.no_proxy else src
    t0 = ytcore.parse_ts(args.start) if args.start else 0.0
    t1 = ytcore.parse_ts(args.end) if args.end else info["duration"]
    spans, samples = detect_spans(scan_src, t0, t1, L, step=args.every)
    out = workdir / "shorts" / "layout_spans.json"
    ytcore.write_json(out, {"source": str(scan_src), "from": t0, "to": t1, "every": args.every, "spans": spans})
    totals: dict[str, float] = {}
    for s in spans:
        totals[s["layout"]] = round(totals.get(s["layout"], 0) + s["end"] - s["start"], 1)
    ytcore.emit(True, outputs={"layout_spans": str(out)}, spans=len(spans), seconds_by_layout=totals,
                samples=len(samples), warnings=warnings)


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-clips", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("windows", help="finestre ~90 s (30 s di sovrapposizione) → shorts/windows.json")
    p.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    p.add_argument("--len", type=float, default=90.0, help="durata obiettivo della finestra (s)")
    p.add_argument("--overlap", type=float, default=30.0, help="sovrapposizione tra finestre (s)")
    p.add_argument("--words", default=None, help="transcript alternativo")
    p.add_argument("--force", action="store_true", help="rifà anche se aggiornato")

    p = sub.add_parser("select", help="valida scores.json, dedup, ordina → shorts/clips.json")
    p.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    p.add_argument("--scores", default=None, help="default shorts/scores.json")
    p.add_argument("--max", type=int, default=8, help="massimo clip (0 = nessun limite); mai riempire per quota")
    p.add_argument("--min-score", type=float, default=0.0, help="scarta sotto questo punteggio")
    p.add_argument("--crop", default="auto", choices=["auto", "inset", "speaker", "stack"])
    p.add_argument("--no-layout", action="store_true", help="non campionare i frame per il layout")
    p.add_argument("--force", action="store_true", help="rifà anche se aggiornato")

    p = sub.add_parser("render", help="render 1080×1920 con sottotitoli → shorts/short_NN.mp4")
    p.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    p.add_argument("--clip", default=None, help="N (rank), 'short_03' o lista '1,3'")
    p.add_argument("--all", action="store_true", help="tutte le clip di clips.json")
    p.add_argument("--style", default=None, help="preset ASS (default: quello del canale o del suo brand, altrimenti 'default')")
    p.add_argument("--accent", default="auto", help="accento del preset (nomi in «accents»); auto = il più leggibile sullo sfondo")
    p.add_argument("--crop", default=None, choices=["auto", "inset", "speaker", "stack"], help="forza il crop (default auto)")
    p.add_argument("--face", default="largest", choices=["largest", "left", "right", "center", "speaker"],
                   help="volto per il crop speaker; 'speaker' segue chi parla (serve speaker_positions in project.json)")
    p.add_argument("--no-hook", action="store_true", help="niente hook nei primi 3 s")
    p.add_argument("--hook", default=None, help="sostituisce hook_text di clips.json (una sola clip, ≤10 parole)")
    p.add_argument("--keep-fillers", action="store_true", help="tiene ehm/eh nei sottotitoli bruciati")
    p.add_argument("--crf", type=int, default=18, help="qualità libx264 (default 18)")
    p.add_argument("--pip", default="mask", choices=["mask", "avoid"],
                   help="grafica PiP nel crop wide: mask = la toglie (delogo), avoid = crop sotto il PiP (più zoom)")
    p.add_argument("--force", action="store_true", help="rifà anche se aggiornato")

    p = sub.add_parser("layout", help="rileva i tratti di layout, o --measure la geometria del template")
    p.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    p.add_argument("--measure", action="store_true", help="misura la geometria (serve --inset-at e --wide-at)")
    p.add_argument("--inset-at", default=None, help="tempi (anche più, separati da virgola) con layout inset")
    p.add_argument("--wide-at", default=None, help="tempi con layout wide (3 persone)")
    p.add_argument("--card-at", default=None, help="un tempo con la title card (facoltativo)")
    p.add_argument("--write", action="store_true", help="con --measure scrive il layout.json del brand del canale (nei brands_dirs, mai nel plugin)")
    p.add_argument("--channel", default=None)
    p.add_argument("--from", dest="start", default=None)
    p.add_argument("--to", dest="end", default=None)
    p.add_argument("--every", type=float, default=1.0, help="passo di campionamento (s)")
    p.add_argument("--no-proxy", action="store_true", help="usa il sorgente anche se c'è analysis/proxy.mp4")

    args = ap.parse_args()
    warnings: list[str] = []
    try:
        workdir = ytcore.resolve_workdir(args.workdir)
        {"windows": cmd_windows, "select": cmd_select, "render": cmd_render, "layout": cmd_layout}[args.cmd](args, workdir, warnings)
    except (FileNotFoundError, ValueError, RuntimeError, KeyError) as exc:
        ytcore.fail(str(exc), warnings=warnings)


if __name__ == "__main__":
    main()
