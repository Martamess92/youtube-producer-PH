"""Test dei controlli di yt-thumb-qa (thumbnail v2). Niente pytest: assert semplici.

Uso (venv del toolkit; YT_DATA = data dir del plugin o una data dir temporanea di install.sh --data):
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_thumb_qa.py            # tutti
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_thumb_qa.py served      # solo i test col nome che contiene «served»
Tutte le immagini sono sintetiche (nessuna persona reale). Opzionale: YT_QA_PORTRAIT + YT_QA_PORTRAIT_FACE (un ritaglio vero
di chi esegue i test, col suo consenso) per la verifica dei landmark MediaPipe sul grade mono.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"
sys.path.insert(0, str(LIB))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import thumb_qa as tq  # noqa: E402


# ── Aiuti ───────────────────────────────────────────────────────────────────
def canvas(rgb=(128, 128, 128), size=(1280, 720)) -> Image.Image:
    return Image.new("RGB", size, rgb)


def fill_box(im: Image.Image, box, rgb) -> Image.Image:
    W, H = im.size
    x, y, w, h = box
    ImageDraw.Draw(im).rectangle((int(x * W), int(y * H), int((x + w) * W) - 1, int((y + h) * H) - 1), fill=rgb)
    return im


def noise_box(im: Image.Image, box, lo=60, hi=255, seed=1) -> Image.Image:
    W, H = im.size
    x, y, w, h = box
    x0, y0, x1, y1 = int(x * W), int(y * H), int((x + w) * W), int((y + h) * H)
    rng = np.random.default_rng(seed)
    a = np.asarray(im).copy()
    a[y0:y1, x0:x1] = rng.integers(lo, hi, size=(y1 - y0, x1 - x0, 1), dtype=np.uint8)
    return Image.fromarray(a)


def L_of(v: int) -> float:
    return float(tq.srgb_to_L(np.array([[v, v, v]], float))[0])


def face(h, role=None, x=0.6, y=0.1, w=None, **kw) -> dict:
    return {"box": [x, y, w if w is not None else h * 9 / 16, h], "role": role, **kw}


def ids(checks) -> dict:
    return {c["id"]: c for c in checks}


def dashed_rect(d: ImageDraw.ImageDraw, r, color, width=3, on=6, off=3) -> None:
    """Contorno tratteggiato FUORI dal box (come `outline: 3px dashed` dell'overlay debug)."""
    x, y, w, h = r
    x0, y0, x1, y1 = x - width, y - width, x + w + width, y + h + width
    for t in range(int(x0), int(x1), on + off):
        d.rectangle((t, y0, min(t + on, x1) - 1, y0 + width - 1), fill=color)
        d.rectangle((t, y1 - width, min(t + on, x1) - 1, y1 - 1), fill=color)
    for t in range(int(y0), int(y1), on + off):
        d.rectangle((x0, t, x0 + width - 1, min(t + on, y1) - 1), fill=color)
        d.rectangle((x1 - width, t, x1 - 1, min(t + on, y1) - 1), fill=color)


# ── face_size ───────────────────────────────────────────────────────────────
def test_template_kind():
    assert tq.template_kind("generic", "claim") == "claim"
    assert tq.template_kind("generic", "claim", 1) == "claim"
    assert tq.template_kind("ritratto", None) == "claim"
    assert tq.template_kind("acme-ritratto", None) == "claim"            # variante di un brand: stesse soglie
    assert tq.template_kind("scena", None) == "claim"
    assert tq.template_kind("prova", "proof", 0) == "other"
    assert tq.template_kind("prova", "proof", 1) == "claim"
    assert tq.template_kind("generic", "proof", 1) == "other"
    assert tq.template_kind("acme-copertina", "duo") == "duo"
    assert tq.template_kind("duo", None) == "duo"
    assert tq.template_kind("acme-duo", None) == "duo"
    assert tq.template_kind("generic", None) == "other"
    assert tq.base_template("acme-duo") == "duo" and tq.base_template("acme-copertina") == "acme-copertina"


def test_face_size_claim():
    c = tq.check_face_size([face(0.235, "guest")], "claim")
    assert c["level"] == "error" and c["threshold"] == 0.35, c
    assert tq.check_face_size([face(0.36)], "claim")["level"] == "warn"
    assert tq.check_face_size([face(0.42)], "claim")["level"] == "pass"
    # sorgente still: errore sotto il 40 %
    assert tq.check_face_size([face(0.38, still=True)], "claim", still=True)["level"] == "error"
    assert tq.check_face_size([face(0.45)], "claim", still=True)["level"] == "pass"
    # il volto principale è l'ospite, anche se l'host è più grande
    c = tq.check_face_size([face(0.45, "host"), face(0.30, "guest")], "claim")
    assert c["level"] == "error" and abs(c["value"] - 0.30) < 1e-9, c
    # niente volto: errore solo se il template lo richiede
    assert tq.check_face_size([], "claim")["level"] == "skip"
    assert tq.check_face_size([], "claim", require_face=True)["level"] == "error"
    assert tq.check_face_size([face(0.2)], "other")["level"] == "info"


def test_face_size_duo():
    assert tq.check_face_size([face(0.32, "host"), face(0.34, "guest")], "duo")["level"] == "pass"
    c = tq.check_face_size([face(0.25, "guest"), face(0.18, "host")], "duo")
    assert c["level"] == "error" and "ognuno" in c["message"], c
    c = tq.check_face_size([face(0.40, "host"), face(0.33, "guest")], "duo")
    assert c["level"] == "error" and "ospite" in c["message"], c
    assert tq.check_face_size([face(0.40)], "duo")["level"] == "warn"


def test_overrides_and_gate():
    checks = [tq.check_face_size([face(0.30)], "claim"), tq.check_face_surround(5.0)]
    tq.apply_overrides(checks, {"face_floor_reason": "frame largo: ok dell'operatore al G2"})
    by = ids(checks)
    assert by["face_size"]["level"] == "warn" and by["face_size"]["override"], by["face_size"]
    assert by["face_surround"]["level"] == "error"
    tq.apply_overrides(checks, {"qa_overrides": {"face_surround": "test"}})
    assert ids(checks)["face_surround"]["level"] == "warn"
    checks = [tq.check_face_surround(5.0)]
    tq.gate(checks, gated=False)
    assert checks[0]["level"] == "warn" and checks[0]["ungated"]
    checks = [tq.check_face_surround(5.0)]
    tq.gate(checks, gated=True)
    assert checks[0]["level"] == "error"


# ── face_surround ───────────────────────────────────────────────────────────
def test_face_surround():
    box = (0.6, 0.2, 0.13, 0.235)
    im = fill_box(canvas((128, 128, 128)), box, (138, 138, 138))
    v = tq.face_surround_dL(im, box)
    assert abs(v - (L_of(138) - L_of(128))) < 0.6, v
    assert tq.check_face_surround(v)["level"] == "error"
    im = fill_box(canvas((128, 128, 128)), box, (160, 160, 160))
    v = tq.face_surround_dL(im, box)
    assert 10 <= v < 20, v
    assert tq.check_face_surround(v)["level"] == "warn"
    im = fill_box(canvas((25, 25, 25)), box, (205, 170, 150))
    v = tq.face_surround_dL(im, box)
    assert v > 40, v
    assert tq.check_face_surround(v)["level"] == "pass"
    # i box del testo escono dall'intorno: un riquadro bianco a lato non sposta la misura
    im2 = fill_box(fill_box(canvas((25, 25, 25)), box, (205, 170, 150)), (0.45, 0.15, 0.13, 0.3), (255, 255, 255))
    v_text = tq.face_surround_dL(im2, box, [(0.45, 0.15, 0.13, 0.3)])
    assert abs(v_text - v) < 1.0, (v_text, v)
    assert tq.check_face_surround(None)["level"] == "skip"
    # detail: intorno uniforme → stesso valore di R3 (calibrazione invariata)
    d = tq.face_surround_detail(fill_box(canvas((25, 25, 25)), box, (205, 170, 150)), box)
    assert d["method"] == "r3" and abs(d["value"] - v) < 0.05 and not d["straddle"], d
    # intorno a cavallo del volto (duo): sopra un cerchio chiaro, sotto la plate scura, volto grigio medio.
    # R3 (mediana dell'unione) cade sul tono del volto; la mediana per pixel di |ΔL*| vede lo stacco su entrambe le parti.
    im3 = canvas((40, 40, 40))                                            # 40 % delle bande scuro (plate)
    im3 = fill_box(im3, (0.45, 0.10, 0.50, 0.1517), (205, 205, 205))    # 40 % chiaro (cerchio)
    im3 = fill_box(im3, (0.45, 0.2517, 0.50, 0.0611), (128, 128, 128))  # 20 % sul tono del volto (bordo sfumato)
    im3 = fill_box(im3, box, (128, 128, 128))
    d3 = tq.face_surround_detail(im3, box)
    assert d3["straddle"] and d3["method"] == "per_pixel", d3
    assert d3["r3"] < 10 <= d3["value"], d3
    c3 = tq.check_face_surround(d3["value"], d3)
    assert c3["level"] in ("pass", "warn") and "a cavallo" in c3["message"], c3
    # la persona stessa esce dall'intorno: capelli chiari a lato del volto non contano come fondo
    pm = np.zeros((720, 1280))
    pm[int(0.2 * 720):int(0.435 * 720), int(0.48 * 1280):int(0.6 * 1280)] = 1.0
    im4 = fill_box(fill_box(canvas((25, 25, 25)), (0.48, 0.2, 0.12, 0.235), (230, 230, 230)), box, (205, 170, 150))
    d4 = tq.face_surround_detail(im4, box, person=pm)
    assert d4.get("person_excluded") and d4["value"] > 40, d4


# ── served_detail ───────────────────────────────────────────────────────────
def test_served_detail():
    box = (0.6, 0.1, 0.236, 0.42)
    sharp = noise_box(canvas((40, 40, 40)), box, 0, 255)
    v, px = tq.served_detail(tq.served_file(sharp), box)
    assert v > tq.DETAIL_WARN and 165 <= px <= 172, (v, px)
    flat = fill_box(canvas((40, 40, 40)), box, (180, 150, 130))
    v0, _ = tq.served_detail(tq.served_file(flat), box)
    assert v0 < 100, v0                      # solo il bordo del box (il crop è troncato agli interi)
    assert tq.check_served_detail(v0)["level"] == "error"
    assert tq.check_served_detail(650.0)["level"] == "warn"
    assert tq.check_served_detail(569.0)["level"] == "warn"
    assert tq.check_served_detail(568.9)["level"] == "error"
    assert tq.check_served_detail(713.0)["level"] == "pass"
    assert tq.check_served_detail(400.0, main=False)["level"] == "warn"     # volti secondari: mai errore
    assert tq.served_file(sharp).size == (720, 405)
    assert tq.lap_var(np.zeros((2, 2))) == 0.0


# ── silhouette_246 ──────────────────────────────────────────────────────────
def _ellipse_mask(size=(1280, 720), box=(700, 80, 1100, 720)) -> np.ndarray:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse(box, fill=255)
    return np.asarray(m, np.float64) / 255


def test_silhouette():
    mask = _ellipse_mask()
    im = canvas((20, 20, 20))
    im.paste(Image.new("RGB", im.size, (220, 220, 220)), mask=Image.fromarray((mask * 255).astype(np.uint8)))
    v = tq.silhouette_dL(im, mask)
    assert v > 60, v
    assert tq.check_silhouette(v)["level"] == "pass"
    same = canvas((90, 90, 90))
    v2 = tq.silhouette_dL(same, mask)
    assert v2 < 1, v2
    c = tq.check_silhouette(v2, "graphic")
    assert c["level"] == "warn" and "graphic" in c["message"]          # solo avviso, mai errore
    assert tq.check_silhouette(None)["level"] == "skip"
    assert tq.silhouette_dL(im, np.zeros((720, 1280))) is None
    # erosione/dilatazione a croce
    m = np.zeros((7, 7), bool); m[2:5, 2:5] = True
    assert tq._erode(m, 1).sum() == 1 and tq._dilate(m, 1).sum() == 21


def test_person_mask_from_sidecar():
    with tempfile.TemporaryDirectory() as td:
        cut = Path(td) / "cut.png"
        a = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
        ImageDraw.Draw(a).rectangle((100, 100, 299, 599), fill=(200, 150, 120, 255))
        a.save(cut)
        data = {"spec": {"people": [{"path": str(cut)}]}, "metrics": {"heroes": [{"rect": [800, 120, 400, 600], "face": [900, 220, 200, 200]}]}}
        m = tq.person_mask(data)
        assert m is not None and m.shape == (720, 1280)
        area = (m > 0.5).sum()
        assert abs(area - 200 * 500) < 2000, area           # 200×500 px opachi, metà inferiore tagliata dal canvas (720)
        assert m[300, 1000] > 0.5 and m[300, 850] < 0.5
    assert tq.person_mask({"spec": {}, "metrics": {}}) is None


# ── phrase_line_h / keyword_line_h ──────────────────────────────────────────
def test_text_lines_v1_sidecar():
    # template senza parola chiave dichiarata: un solo testo «hook» su 2 righe
    data = {"metrics": {"texts": [{"kind": "badge", "rects": [[124, 61.5, 96.1, 27]]},
                                  {"kind": "hook", "rects": [[64, 176.2, 218.4, 115.4], [61.9, 297.3, 600.8, 176.7]]}]}}
    L = tq.text_lines(data)
    assert L["source"] == "sidecar" and L["keyword_source"] == "estimated"
    assert L["phrase"] == [round(115.4 / 720, 4)] and L["keyword"] == [round(176.7 / 720, 4)], L
    by = ids(tq.check_text_lines(L))
    assert by["phrase_line_h"]["level"] == "pass" and by["keyword_line_h"]["level"] == "pass"


def test_text_lines_v2_sidecar():
    data = {"metrics": {"texts": [{"kind": "phrase", "rects": [[64, 200, 500, 80], [64, 290, 420, 92]]},
                                  {"kind": "keyword", "rects": [[64, 400, 380, 120]]},
                                  {"kind": "credential", "rects": [[64, 600, 300, 30]]}]}}
    L = tq.text_lines(data)
    assert L["keyword_source"] == "kind" and len(L["phrase"]) == 2, L
    by = ids(tq.check_text_lines(L))
    assert by["phrase_line_h"]["level"] == "error" and abs(by["phrase_line_h"]["value"] - 80 / 720) < 1e-3
    assert by["keyword_line_h"]["level"] == "error"                      # 16,7 % < 18 %
    ok = {"metrics": {"texts": [{"kind": "phrase", "rects": [[64, 200, 500, 90]]}, {"kind": "keyword", "rects": [[64, 300, 400, 132]]}]}}
    by = ids(tq.check_text_lines(tq.text_lines(ok)))
    assert by["phrase_line_h"]["level"] == "pass" and by["keyword_line_h"]["level"] == "pass", by
    # parola chiave dichiarata nel testo della frase (keyword_rects): la sua riga esce dalla frase
    kr = {"metrics": {"texts": [{"kind": "hook", "rects": [[64, 200, 500, 90], [64, 300, 600, 140]],
                                 "keyword_rects": [[300, 305, 300, 130]]}]}}
    L = tq.text_lines(kr)
    assert L["keyword_source"] == "field" and L["phrase"] == [0.125] and L["keyword"] == [round(130 / 720, 4)], L
    # righe di glifi del renderer (rows: maiuscole senza accenti): hanno la precedenza sui rects, che contano l'accento
    # («È ANDATA / BENE COSÌ.»: rects 175 px = 24 %, maiuscole 137 px = 19 %)
    acc = {"template": "duo", "metrics": {"texts": [{"kind": "hook", "rects": [[290, 150, 560, 175], [290, 330, 610, 176]],
                                                        "rows": [{"y": 188, "h": 137, "frac": 0.19, "keyword": False},
                                                                 {"y": 369, "h": 139, "frac": 0.193, "keyword": False}]}]}}
    L = tq.text_lines(acc)
    assert max(L["phrase"] + L["keyword"]) < 0.20, L


def test_keyword_one_size_headline_warns():
    # titolo v2 a un solo corpo (parola chiave = span .hl nella riga, alta come le altre): 18 % è l'obiettivo → avviso,
    # come post_render_checks di yt-thumb-render; una parola chiave più grande della frase sotto il 18 % resta errore
    one = {"metrics": {"texts": [{"kind": "hook", "rects": [[44, 173, 670, 104], [44, 285, 666, 104]],
                                  "keyword_rects": [[396, 297, 304, 102]]}]}}
    L = tq.text_lines(one)
    assert L["one_size"] is True, L
    by = ids(tq.check_text_lines(L))
    assert by["keyword_line_h"]["level"] == "warn" and by["phrase_line_h"]["level"] == "pass", by
    big = {"metrics": {"texts": [{"kind": "hook", "rects": [[44, 173, 670, 90], [44, 285, 666, 125]],
                                  "keyword_rects": [[396, 290, 304, 125]]}]}}
    L = tq.text_lines(big)
    assert L["one_size"] is False and ids(tq.check_text_lines(L))["keyword_line_h"]["level"] == "error", L


def test_display_cap_from_portrait_dict():
    # portrait.display_cap di yt-portrait cut è un dict: prima faceva crollare yt-thumb-qa (float(dict))
    assert tq._cap_factor({"mode": "c", "factor": 2.0}) == 2.0 and tq._cap_factor(1.5) == 1.5 and tq._cap_factor(None) is None
    data = {"template": "ritratto", "spec": {"people": [{"role": "guest", "portrait": {"eff_face_px": 170.4,
            "display_cap": {"mode": "c", "factor": 2.0, "max_face_frac": 0.47}}}]},
            "metrics": {"heroes": [{"face": [700, 120, 300, 323]}]}, "checks2": {"heroes": [{"display_cap": 1.5}]}}
    f = tq.faces_from_sidecar(data)
    assert f[0]["display_cap"] == 1.5 and f[0]["eff_face_px"] == 170.4, f      # vince il tetto usato dal render


def test_text_lines_soft_sources():
    L = tq.text_lines(None, manual_boxes=[(0.05, 0.2, 0.4, 0.10), (0.05, 0.35, 0.4, 0.15)])
    by = ids(tq.check_text_lines(L))
    assert L["source"] == "manual" and by["phrase_line_h"]["level"] == "warn", by     # manuale: avviso, non errore
    assert by["keyword_line_h"]["level"] == "warn"
    # stimata e sotto il 18 %: avviso anche dal sidecar
    est = {"metrics": {"texts": [{"kind": "hook", "rects": [[64, 200, 500, 100], [64, 310, 500, 110]]}]}}
    by = ids(tq.check_text_lines(tq.text_lines(est)))
    assert by["keyword_line_h"]["level"] == "warn" and by["phrase_line_h"]["level"] == "pass", by
    assert tq.check_text_lines(tq.text_lines(None))[0]["level"] == "skip"
    assert tq.check_text_lines(tq.text_lines({"metrics": {"texts": [{"kind": "badge", "rects": [[0, 0, 10, 10]]}]}}))[0]["level"] == "skip"


def test_debug_overlay():
    rects = [(64, 176.2, 218.4, 115.4), (61.9, 297.3, 600.8, 176.7), (124, 61.5, 96.1, 27)]
    face_r = (811.2, 136.9, 169.3, 169.3)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x_debug.png"
        im = canvas((150, 80, 60))
        d = ImageDraw.Draw(im)
        for r in rects:
            dashed_rect(d, [round(v) for v in r], (255, 0, 255))
        dashed_rect(d, [round(v) for v in face_r], (0, 255, 255))
        d.text((round(face_r[0]) + 4, round(face_r[1]) + 4), "volto", fill=(0, 255, 255))
        im.save(p)
        ob = tq.overlay_boxes(p)
    hs = sorted(round(b[3] * 720) for b in ob["text"])
    want = sorted(round(r[3]) for r in rects)
    assert len(hs) == 3 and all(abs(a - b) <= 3 for a, b in zip(hs, want)), (hs, want)
    assert len(ob["faces"]) == 1 and abs(ob["faces"][0][3] * 720 - face_r[3]) <= 3, ob["faces"]
    L = tq.text_lines(None, (), ob)
    assert L["source"] == "debug" and L["keyword_source"] == "estimated"
    assert len(L["phrase"]) == 1 and abs(L["phrase"][0] - 115.4 / 720) < 0.006, L    # il badge (< 6 %) è escluso
    by = ids(tq.check_text_lines(L))
    assert by["phrase_line_h"]["level"] == "pass"


# ── avvisi secondari ────────────────────────────────────────────────────────
def test_edges_and_contrast():
    by = ids(tq.check_edges({"edge_dL_dark": 10.6, "edge_dL_light": 85.1}))
    assert by["edge_dL_dark"]["level"] == "warn" and by["edge_dL_light"]["level"] == "pass"     # declassato: mai errore
    assert tq.check_text_contrast(2.5)["level"] == "warn"
    assert tq.check_text_contrast(6.48)["level"] == "pass"
    assert tq.check_text_contrast(None)["level"] == "skip"


def test_display_upscale():
    c = tq.check_display_upscale(169.3, 152.4)
    assert c["level"] == "info" and c["value"] == 1.11, c
    assert tq.check_display_upscale(330, 152.4)["level"] == "warn"            # 2,17× > 2,0×
    assert tq.check_display_upscale(250, 152.4, cap=1.5)["level"] == "warn"   # ripiego (b)
    assert tq.check_display_upscale(None, 152.4)["level"] == "skip"


def test_render_checks():
    assert tq.check_render({}) is None
    assert tq.check_render({"pass": True, "errors": []})["level"] == "pass"
    c = tq.check_render({"pass": False, "errors": ["volto a 2.40× della sorgente > 2.0×"]})
    assert c["level"] == "error" and c["value"] == 1


def test_saliency():
    faces = [face(0.4, x=0.6, y=0.1)]
    text = [(0.05, 0.3, 0.45, 0.2)]
    assert tq.classify_salient((0.62, 0.12, 0.2, 0.3), faces, text) == "face"
    assert tq.classify_salient((0.05, 0.3, 0.4, 0.2), faces, text) == "headline"
    assert tq.classify_salient((0.0, 0.85, 0.1, 0.1), faces, text) == "other"
    assert tq.check_saliency(None, faces, text)["level"] == "info"
    c = tq.check_saliency([{"box": [0.06, 0.3, 0.4, 0.2], "confidence": 0.9}], faces, text)
    assert c["level"] == "info" and c["value"] == "headline", c
    assert tq.check_saliency([], faces, text)["level"] == "info"
    # formato di `thumbvision saliency --boxes face:…;headline:…`: vince `first` (media di salienza nei box)
    sal = {"objects": [{"box": [0.0, 0.85, 0.1, 0.1], "confidence": 1.0}], "first": "headline",
           "boxes": {"face": {"mean": 0.2, "share": 0.1}, "headline": {"mean": 0.5, "share": 0.4}}}
    c = tq.check_saliency(sal, faces, text)
    assert c["value"] == "headline" and "headline 40%" in c["message"], c
    ub = tq.union_box([(0.1, 0.2, 0.2, 0.1), (0.05, 0.4, 0.5, 0.2)])
    assert all(abs(a - b) < 1e-9 for a, b in zip(ub, (0.05, 0.2, 0.5, 0.4))), ub
    assert tq.union_box([]) is None
    cb = tq._clamp_box((-0.1, 0.9, 0.3, 0.3))
    assert all(abs(a - b) < 1e-9 for a, b in zip(cb, (0.0, 0.9, 0.2, 0.1))), cb


def test_saliency_thumbvision():
    """Solo se il thumbvision installato ha il sottocomando `saliency` (thumbnail v2)."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "s.png"
        im = canvas((30, 30, 30))
        fill_box(im, (0.62, 0.15, 0.15, 0.35), (230, 190, 160))
        im.save(p)
        sal = tq.saliency_regions(p, (0.62, 0.15, 0.15, 0.35), (0.05, 0.6, 0.3, 0.1), Path(td) / "h.png")
        if sal is None:
            print("    (saltato: thumbvision senza 'saliency')")
            return
        assert sal["first"] in ("face", "headline") and set(sal["boxes"]) == {"face", "headline"}, sal
        assert sal["first"] == "face", sal
        assert sal["heatmap"] and Path(sal["heatmap"]).exists()


def test_surfaces_json():
    s = tq.load_surfaces()
    assert s.get("_attribution", {}).get("license") == "CC BY 4.0", "attribuzione CC BY 4.0 mancante"
    assert tq.surface_size(s, "sidebar") == (216, 121)
    assert tq.surface_size(s, "search") == (500, 280)
    assert tq.surface_size(s, "home") == (347, 195)
    assert tq.surface_size({}, "sidebar", default=(1, 2)) == (1, 2)
    labels = [t[0] for t in tq.sheet_tiles(s)]
    assert [t[1] for t in tq.sheet_tiles(s)] == [720, 500, 360, 216, 168] and "stress" in labels[-1]


def test_faces_from_sidecar_roles():
    data = {"template": "duo", "spec": {"roles": ["host", "guest"], "people": [{"path": "a.png"}, {"path": "b.png", "portrait": {"eff_face_px": 98}}]},
            "metrics": {"heroes": [{"face": [50.5, 475.3, 129.6, 129.6]}, {"face": [882.9, 244.9, 180, 180]}]}}
    f = tq.faces_from_sidecar(data)
    assert [x["role"] for x in f] == ["host", "guest"] and tq.main_face_index(f) == 1
    assert f[1]["eff_face_px"] == 98 and abs(f[1]["box"][3] - 0.25) < 1e-9
    data["spec"]["people"][0]["role"] = "guest"
    data["spec"]["people"][1]["role"] = "host"
    assert tq.main_face_index(tq.faces_from_sidecar(data)) == 0
    still = {"spec": {"people": [{"portrait": {"source": {"kind": "still"}}}]}, "metrics": {"heroes": [{"face": [0, 0, 100, 300]}]}}
    assert tq.faces_from_sidecar(still)[0]["still"] is True


# ── Stacco dal feed scuro ───────────────────────────────────────────────────
def test_edges_dark_frame_element():
    # sotto 25 senza elemento chiaro: avviso (ritratto su campo scuro 13,5); sotto 25 con un cerchio che tocca il bordo: passa (22,4)
    by = ids(tq.check_edges({"edge_dL_dark": 13.5, "edge_light_run": 0.029, "edge_dL_light": 82.1}))
    assert by["edge_dL_dark"]["level"] == "warn" and by["edge_dL_dark"]["threshold"] == 25.0, by["edge_dL_dark"]
    by = ids(tq.check_edges({"edge_dL_dark": 22.4, "edge_light_run": 0.204, "edge_dL_light": 74.3}))
    assert by["edge_dL_dark"]["level"] == "pass" and "elemento chiaro" in by["edge_dL_dark"]["message"], by
    assert ids(tq.check_edges({"edge_dL_dark": 34.3, "edge_light_run": 0.0}))["edge_dL_dark"]["level"] == "pass"
    assert ids(tq.check_edges({"edge_dL_dark": 21.0}))["edge_dL_dark"]["level"] == "warn"          # metrica vecchia: niente run
    assert ids(tq.check_edges({"edge_dL_light": 16.3}))["edge_dL_light"]["level"] == "warn"        # chiaro: soglia 20 invariata
    assert ids(tq.check_edges({"edge_dL_light": 20.0}))["edge_dL_light"]["level"] == "pass"
    # tratto continuo su un profilo chiuso (anche a cavallo dell'inizio)
    assert tq.longest_circular_run(np.array([1, 1, 0, 0, 1, 1, 1], bool)) == 5
    assert tq.longest_circular_run(np.zeros(5, bool)) == 0 and tq.longest_circular_run(np.ones(4, bool)) == 4
    # misura sulla tile: fondo #141414 e un disco d'accento chiaro che esce dall'angolo in alto a destra
    im = canvas((20, 20, 20))
    ImageDraw.Draw(im).ellipse((900, -300, 1500, 300), fill=(53, 212, 154))
    m = tq.edge_separation(tq.fit_thumb(im, 360, 202))
    assert m["edge_dL_dark"] < 25 and m["edge_light_run"] >= 0.10, m
    assert ids(tq.check_edges(m))["edge_dL_dark"]["level"] == "pass"
    flat = tq.edge_separation(tq.fit_thumb(canvas((20, 20, 20)), 360, 202))
    assert flat["edge_light_run"] == 0 and ids(tq.check_edges(flat))["edge_dL_dark"]["level"] == "warn", flat


# ── Titolo del duo: 3–4 parole, righe ≥ 20 % ────────────────────────────────
def test_hook_words_duo():
    assert tq.check_hook_words("Abbiamo deciso di vendere.", "duo")["level"] == "pass"
    c = tq.check_hook_words("Lo provammo con una lista.", "duo")
    assert c["level"] == "error" and c["value"] == 5 and c["threshold"] == 4, c
    assert tq.check_hook_words("Lo provammo con una lista.", "acme-duo")["level"] == "error"           # variante di un brand
    assert tq.check_hook_words("Lo provammo con una lista.", "ritratto")["level"] == "pass"
    assert tq.check_hook_words("UNA LISTA", "ritratto")["level"] == "error"
    assert tq.check_hook_words("ho chiuso il mio primo SaaS ieri", "ritratto")["level"] == "warn"   # 7 > 6
    assert len(tq.hook_words("L'HO | VENDUTO.")) == 3                                                  # elisione = 2
    assert tq.check_hook_words(None, "duo")["level"] == "skip"


def test_text_lines_duo_20pct():
    one = {"metrics": {"texts": [{"kind": "hook", "rects": [[300, 60, 680, 101], [330, 170, 620, 101]],
                                  "keyword_rects": [[700, 172, 280, 99]]}]}}
    L = tq.text_lines(one)
    by = ids(tq.check_text_lines(L))                         # altri template: 12 % passa, parola chiave a un corpo = avviso
    assert by["phrase_line_h"]["level"] == "pass" and by["keyword_line_h"]["level"] == "warn", by
    by = ids(tq.check_text_lines(L, "duo"))                  # duo: ogni riga ≥ 20 % → errore, anche la parola chiave
    assert by["phrase_line_h"]["level"] == "error" and by["phrase_line_h"]["threshold"] == 0.20, by
    assert by["keyword_line_h"]["level"] == "error" and "duo" in by["keyword_line_h"]["message"], by
    big = {"metrics": {"texts": [{"kind": "hook", "rects": [[300, 60, 680, 160], [330, 230, 620, 160]],
                                  "keyword_rects": [[700, 232, 280, 158]]}]}}
    by = ids(tq.check_text_lines(tq.text_lines(big), "duo"))
    assert by["phrase_line_h"]["level"] == "pass" and by["keyword_line_h"]["level"] == "pass", by
    # il motivo scritto al G2 (hook_size_reason) fa scendere l'errore ad avviso
    checks = tq.check_text_lines(L, "duo")
    tq.apply_overrides(checks, {"hook_size_reason": "nome lungo: ok dell'operatore al G2"})
    assert all(c["level"] == "warn" for c in checks), checks


# ── Livello 2b: grade monocromatico uniforme ────────────────────────────────
INK, PAPER = np.array([21, 23, 28], float) / 255, np.array([244, 241, 234], float) / 255   # brand demo


def mono_curve(rgb01: np.ndarray, contrast: float = 0.35, ev: float = 0.0) -> np.ndarray:
    """Un grade mono qualsiasi (luma Rec.709 → curva a S → rampa inchiostro→carta): il controllo non conosce la curva."""
    y = rgb01 @ np.array([0.2126, 0.7152, 0.0722])
    y = np.clip(y - contrast * np.sin(2 * np.pi * y) / (2 * np.pi), 0, 1)
    y = np.clip(y * 2.0 ** ev, 0, 1)
    return INK + (PAPER - INK) * y[..., None]


def synth_person(seed: int, size=(600, 900)) -> tuple[np.ndarray, list[float]]:
    """Ritaglio RGBA a colori: corpo e capelli a macchie di colore su tutta la scala di luma, volto color pelle (luma che
    si sovrappone al corpo), bordo morbido. Ritorna (rgba uint8, box del volto in px del ritaglio)."""
    w, h = size
    rng = np.random.default_rng(seed)
    blocks = rng.integers(0, 256, (h // 12 + 2, w // 12 + 2, 3)).astype(np.uint8)
    body = np.asarray(Image.fromarray(blocks).resize((w, h), Image.BILINEAR), np.float64)
    fx, fy, fw, fh = w * 0.3, h * 0.12, w * 0.4, h * 0.3
    yy, xx = np.mgrid[0:h, 0:w]
    face = ((xx - (fx + fw / 2)) / (fw / 2)) ** 2 + ((yy - (fy + fh / 2)) / (fh / 2)) ** 2 <= 1
    shade = np.asarray(Image.fromarray(rng.integers(40, 255, (h // 20 + 2, w // 20 + 2)).astype(np.uint8)).resize((w, h), Image.BILINEAR),
                       np.float64) / 255
    skin = np.stack([235 * shade, 180 * shade, 150 * shade], -1)
    rgb = np.where(face[..., None], skin, body)
    sil = ((xx - w / 2) / (w * 0.48)) ** 2 + ((yy - h * 0.62) / (h * 0.62)) ** 2 <= 1
    sil |= ((xx - w / 2) / (w * 0.26)) ** 2 + ((yy - h * 0.27) / (h * 0.24)) ** 2 <= 1
    a = np.asarray(Image.fromarray((sil * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), np.float64)
    return np.dstack([np.clip(rgb, 0, 255), a]).astype(np.uint8), [fx, fy, fw, fh]


def _grade_rgba(rgba: np.ndarray, fn) -> np.ndarray:
    out = rgba.copy()
    out[..., :3] = np.clip(np.round(fn(rgba[..., :3].astype(np.float64) / 255) * 255), 0, 255).astype(np.uint8)
    return out


def write_mono_render(d: Path, name: str, people: list[tuple[np.ndarray, list[float], tuple[float, float]]],
                      graded: list[np.ndarray], grade="mono", plate_rgb=(40, 40, 40), circle=None, accent="accent_2",
                      template="duo", hook="Abbiamo deciso di vendere.", sources=None) -> Path:
    """Render 3840×2160 + sidecar come quelli di yt-thumb-render: ritagli graduati posati 1:1 a (x, y) px del master
    (posizione CSS = /3, arrotondata come Chrome), box del nome sopra la seconda persona."""
    can = Image.new("RGB", (3840, 2160), plate_rgb)
    if circle:
        ImageDraw.Draw(can).ellipse(circle, fill=tuple(int(tq.ACCENT_HEX[accent][i:i + 2], 16) for i in (1, 3, 5)))
    heroes, spec_people = [], []
    for j, ((rgba, fbox, (x, y)), g) in enumerate(zip(people, graded)):
        can.paste(Image.fromarray(g, "RGBA"), (int(round(x)), int(round(y))), Image.fromarray(g, "RGBA"))
        src = d / f"{name}_p{j}.png"
        Image.fromarray(rgba if sources is None else sources[j], "RGBA").save(src)
        heroes.append({"rect": [x / 3, y / 3, rgba.shape[1] / 3, rgba.shape[0] / 3],
                       "face": [(x + fbox[0]) / 3, (y + fbox[1]) / 3, fbox[2] / 3, fbox[3] / 3], "face_frac": fbox[3] / 2160})
        spec_people.append({"path": str(src), "role": "host" if j == 0 else "guest", "name": f"Persona {j + 1}"})
    nx, ny = people[-1][2]
    name_rect = [nx / 3 + 20, ny / 3 + 230, 120, 30]
    ImageDraw.Draw(can).rectangle([v * 3 for v in (name_rect[0], name_rect[1], name_rect[0] + name_rect[2], name_rect[1] + name_rect[3])],
                                  fill=(53, 212, 154))
    p = d / f"{name}.png"
    can.save(p)
    side = {"template": template, "pass": True, "errors": [],
            "spec": {"template": template, "lever": "duo", "grade": grade, "accent": accent, "hook": hook, "people": spec_people},
            "metrics": {"heroes": heroes, "texts": [{"kind": "name", "rects": [name_rect]},
                                                    {"kind": "hook", "rects": [[460, 80, 360, 150], [470, 240, 340, 150]]}]}}
    (d / f"{name}.render.json").write_text(json.dumps(side))
    return p


def _two_people():
    a, fa = synth_person(1)
    b, fb = synth_person(2)
    return [(a, fa, (300.4, 1260.6)), (b, fb, (2700.6, 1200.2))]


def _grade_checks(p: Path) -> dict:
    data = tq.sidecar(p)
    im = tq.fit_thumb(Image.open(p).convert("RGB"), 1280, 720)
    g = tq.analyze_grade(p, data, im, with_landmarks=False)
    return ids(tq.check_grade(g, tq.declared_grade(data))), g


def test_declared_grade():
    assert tq.declared_grade({"spec": {"grade": "mono"}}) == "mono"
    assert tq.declared_grade({"spec": {"grade": {"mode": "mono", "curve_id": "mono-1"}}}) == "mono"
    assert tq.declared_grade({"spec": {}, "v2": {"grade": "mono"}}) == "mono"
    assert tq.declared_grade({"spec": {"guest_style": "mono"}}) == "mono"
    assert tq.declared_grade({"spec": {"grade": "none"}}) == "none"
    # il mono della sola plate (operazione di sfondo) non è il livello 2b
    assert tq.declared_grade({"spec": {"plate": {"grade": "mono"}}, "v2": {"plate": {"grade": "mono"}}}) is None
    # il renderer ha applicato il 2b a un ritaglio: vale come dichiarato
    assert tq.declared_grade({"spec": {}, "metrics": {"heroes": [{}]}, "checks_v2": {"heroes": [{"tone": {"mode": "mono", "level": "2b"}}]}}) == "mono"
    assert tq.check_grade(None, None)[0]["level"] == "skip"
    assert tq.check_grade({"ok": False, "reason": "x"}, "mono")[0]["level"] == "error"
    assert tq.check_grade({"ok": False, "soft": True, "reason": "remotion"}, "mono")[0]["level"] == "warn"


def test_grade_uniform_mono():
    people = _two_people()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ok = write_mono_render(d, "ok", people, [_grade_rgba(r, mono_curve) for r, _, _ in people])
        by, g = _grade_checks(ok)
        assert by["grade_uniform"]["level"] == "pass" and g["res_p95"] < 1.0, (by["grade_uniform"], g["res_p95"])
        assert by["grade_mono"]["level"] == "pass" and by["grade_face"]["level"] == "pass", by
        assert g["luma"] == "rec709" and [p["offset"] for p in g["people"]] == [[300, 1261], [2701, 1200]], g["people"]
        # curve diverse tra le due persone (contrasto 0,35 contro 0,65): non è un grade unico
        diff = write_mono_render(d, "diff", people, [_grade_rgba(people[0][0], mono_curve),
                                                     _grade_rgba(people[1][0], lambda x: mono_curve(x, contrast=0.65))])
        by, g = _grade_checks(diff)
        assert by["grade_uniform"]["level"] == "error" and g["people_gap"][0]["mean"] > tq.GRADE_GAP_ERR, (by["grade_uniform"], g["people_gap"])
        # ritocco locale: volto della seconda persona schiarito del 12 % dopo il grade
        b, fb, _ = people[1]
        gb = _grade_rgba(b, mono_curve)
        x, y, w, h = fb
        gb[int(y):int(y + h), int(x):int(x + w), :3] = np.clip(gb[int(y):int(y + h), int(x):int(x + w), :3] * 1.12, 0, 255).astype(np.uint8)
        dodge = write_mono_render(d, "dodge", people, [_grade_rgba(people[0][0], mono_curve), gb])
        by, g = _grade_checks(dodge)
        faces = [c for c in tq.check_grade(g, "mono") if c["id"] == "grade_face"]
        assert faces[0]["level"] == "pass" and faces[1]["level"] == "error", faces
        assert by["grade_uniform"]["level"] == "error" and g["people"][1]["face_gap"]["mean"] > tq.GRADE_GAP_ERR, g["people"]
        # dichiarato mono ma le persone restano a colori
        color = write_mono_render(d, "color", people, [r for r, _, _ in people])
        by, _ = _grade_checks(color)
        assert by["grade_mono"]["level"] == "error", by["grade_mono"]
        # plate a colori dietro persone mono: avviso
        warm = write_mono_render(d, "warm", people, [_grade_rgba(r, mono_curve) for r, _, _ in people], plate_rgb=(120, 60, 20))
        by, _ = _grade_checks(warm)
        assert by["grade_mono"]["level"] == "warn" and "plate" in by["grade_mono"]["message"], by["grade_mono"]
        # il sidecar punta al ritaglio già graduato: manca il livello 0
        graded = [_grade_rgba(r, mono_curve) for r, _, _ in people]
        miss = write_mono_render(d, "miss", people, graded, sources=graded)
        by, _ = _grade_checks(miss)
        assert by["grade_uniform"]["level"] == "error" and "livello 0" in by["grade_uniform"]["message"], by["grade_uniform"]


def test_skin_de_only_skipped_for_mono():
    over = {"checks_v2": {"heroes": [{"cutout": "a.png", "tone": {"mode": "duo", "skin_de00_mean": 3.1, "skin_de00_p95": 4.0}}]}}
    assert tq.check_skin_de(over, None)["level"] == "error"
    ok = {"checks_v2": {"heroes": [{"cutout": "a.png", "tone": {"mode": "duo", "skin_de00_mean": 2.3, "skin_de00_p95": 3.0}}]}}
    assert tq.check_skin_de(ok, "none")["level"] == "pass"
    assert tq.check_skin_de(over, "mono")["level"] == "skip"
    assert tq.check_skin_de({}, None) is None


def test_circle_contrast():
    # persona mono scura (capelli L* ~25) davanti a un cerchio chiaro (accent_2, L* ~76): stacco forte; l'accento caldo
    # (L* ~61) su una persona grigio medio: no
    rgba, fbox = synth_person(3)
    dark = _grade_rgba(rgba, lambda x: INK + (PAPER - INK) * 0.12 + 0 * x)
    mid = _grade_rgba(rgba, lambda x: np.broadcast_to(np.array([0.55, 0.55, 0.55]), x.shape))
    pos = (2500.0, 1200.0)
    circ = (2400, 600, 3800, 2000)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for name, g, acc, want in (("chiaro", dark, "accent_2", "pass"), ("caldo", mid, "accent", "error")):
            p = write_mono_render(d, name, [(rgba, fbox, pos)], [g], circle=circ, accent=acc, template="ritratto")
            data = tq.sidecar(p)
            im = tq.fit_thumb(Image.open(p).convert("RGB"), 1280, 720)
            c = tq.circle_contrast(im, data, tq.faces_from_sidecar(data))
            chk_ = tq.check_circle(c)
            assert chk_["level"] == want and c["pairs_head"] >= 30, (name, chk_["message"], c)
            assert set(c["alternatives"]) == {"accent", "accent_2", "accent_3"}
        none = write_mono_render(d, "none", [(rgba, fbox, pos)], [dark], template="ritratto")
        data = tq.sidecar(none)
        assert tq.check_circle(tq.circle_contrast(tq.fit_thumb(Image.open(none).convert("RGB"), 1280, 720), data,
                                                  tq.faces_from_sidecar(data)))["level"] == "skip"


def test_grade_landmarks_real():
    """Solo con MediaPipe installato e YT_QA_PORTRAIT = un ritaglio vero (RGBA, livello 0) con il box del volto in
    YT_QA_PORTRAIT_FACE «x,y,w,h» (px del ritaglio). Mono pulito: passa; bocca deformata del 12 %: errore."""
    src, fbox = os.environ.get("YT_QA_PORTRAIT"), os.environ.get("YT_QA_PORTRAIT_FACE")
    if not src or not fbox:
        print("    (saltato: YT_QA_PORTRAIT / YT_QA_PORTRAIT_FACE non impostate)")
        return
    try:
        import expressions as ex
        if not ex.mp_status(check_sha=False)["ok"]:
            print("    (saltato: MediaPipe non installato)")
            return
    except Exception:  # noqa: BLE001
        print("    (saltato: MediaPipe non importabile)")
        return
    rgba = np.asarray(Image.open(src).convert("RGBA"))
    if rgba.shape[0] > 2000:                                     # nel canvas 3840×2160
        k = 2000 / rgba.shape[0]
        rgba = np.asarray(Image.fromarray(rgba).resize((round(rgba.shape[1] * k), 2000), Image.LANCZOS))
    else:
        k = 1.0
    fb = [float(v) * k for v in fbox.split(",")]
    from scipy.ndimage import map_coordinates
    g = _grade_rgba(rgba, mono_curve)
    h, w = g.shape[:2]
    cx, cy, rad = fb[0] + fb[2] / 2, fb[1] + fb[3] * 0.78, fb[2] * 0.22
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    wgt = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * rad ** 2))
    warped = g.copy()
    for c in range(4):
        warped[..., c] = map_coordinates(g[..., c], [yy + 0.12 * fb[3] * 0.25 * wgt, xx - 0.12 * (xx - cx) * wgt * 2.5], order=1, mode="nearest")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        res = {}
        for name, gg in (("clean", g), ("warp", warped)):
            p = write_mono_render(d, name, [(rgba, fb, (2000.0, 100.0))], [gg], template="ritratto")
            data = tq.sidecar(p)
            gr = tq.analyze_grade(p, data, tq.fit_thumb(Image.open(p).convert("RGB"), 1280, 720), with_landmarks=True)
            res[name] = ids(tq.check_landmarks(gr["landmarks"], "mono") + tq.check_grade(gr, "mono"))
    assert res["clean"]["grade_landmarks"]["level"] == "pass" and res["clean"]["grade_face"]["level"] == "pass", res["clean"]
    assert res["warp"]["grade_face"]["level"] == "error", res["warp"]["grade_face"]
    print(f"    landmark: pulito {res['clean']['grade_landmarks']['value']:.3f}, bocca deformata {res['warp']['grade_landmarks']['value']:.3f}")


# ── Comando intero: codice di uscita ────────────────────────────────────────
def _render(dirpath: Path, name: str, face_h: float, sidecar: dict | None, noisy=True) -> Path:
    W, H = 1280, 720
    fw = face_h * H / W
    box = (0.6, 0.08, fw, face_h)
    im = canvas((22, 22, 22))
    im = noise_box(im, box, 120, 255) if noisy else fill_box(im, box, (200, 160, 140))
    d = ImageDraw.Draw(im)
    d.rectangle((64, 200, 564, 290), fill=(244, 241, 234))
    d.rectangle((64, 310, 514, 400), fill=(244, 241, 234))
    d.rectangle((64, 430, 464, 570), fill=(255, 90, 44))
    p = dirpath / f"{name}.png"
    im.save(p)
    if sidecar is not None:
        sc = json.loads(json.dumps(sidecar))
        sc["metrics"]["heroes"] = [{"face": [box[0] * W, box[1] * H, box[2] * W, box[3] * H], "rect": [700, 0, 500, 720],
                                    "face_frac": face_h}]
        (dirpath / f"{name}.render.json").write_text(json.dumps(sc))
    return p


def _run(args: list[str]) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(LIB / "thumb_qa.py"), *args, "--no-vision"], capture_output=True, text=True,
                          env=os.environ.copy(), timeout=300)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"output non JSON (exit {proc.returncode}): {proc.stderr[-800:]}")
    return proc.returncode, out


def test_cli_exit_codes():
    base = {"template": "ritratto", "pass": True, "errors": [],
            "spec": {"template": "ritratto", "lever": "claim", "people": [{"role": "guest"}]},
            "metrics": {"texts": [{"kind": "phrase", "rects": [[64, 200, 500, 90], [64, 310, 450, 90]]},
                                  {"kind": "keyword", "rects": [[64, 430, 400, 140]]}]}}
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        good = _render(t, "good", 0.42, base)
        small = _render(t, "small", 0.235, base)
        loose = _render(t, "loose", 0.235, None)
        code, out = _run([str(good), "--out", str(t / "qa")])
        img = out["outputs"]["images"][0]
        assert code == 0 and out["ok"] and out["all_checks_pass"] and img["pass"], (code, img["errors"])
        by = ids(img["checks"])
        assert by["face_size"]["level"] == "pass" and by["served_detail"]["level"] == "pass", by["served_detail"]
        assert by["face_surround"]["level"] == "pass" and by["phrase_line_h"]["level"] == "pass"
        assert Path(img["sheet"]).exists()
        code, out = _run([str(small), "--out", str(t / "qa")])
        img = out["outputs"]["images"][0]
        assert code == 1 and out["ok"] is True and out["all_checks_pass"] is False, (code, out.get("all_checks_pass"))
        assert ids(img["checks"])["face_size"]["level"] == "error"
        code, _ = _run([str(small), "--out", str(t / "qa"), "--report-only"])
        assert code == 0
        # senza sidecar (audit, competitor): gli errori scendono ad avvisi, uscita 0; --gate always li rende bloccanti
        code, out = _run([str(loose), "--out", str(t / "qa")])
        img = out["outputs"]["images"][0]
        assert code == 0 and img["gated"] is False and not img["errors"], img["errors"]
        code, _ = _run([str(loose), "--out", str(t / "qa"), "--gate", "always", "--text-box", "64,200,500,90"])
        assert code in (0, 1)
        # immagine mancante: ok false, uscita 1
        code, out = _run([str(t / "nope.png"), "--out", str(t / "qa")])
        assert code == 1 and out["ok"] is False


def test_cli_mono_render():
    """Render duo col grade mono: passa con un grade unico; un volto schiarito a mano fa uscire 1 (grade_face)."""
    people = _two_people()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ok = write_mono_render(d, "ok", people, [_grade_rgba(r, mono_curve) for r, _, _ in people])
        code, out = _run([str(ok), "--out", str(d / "qa"), "--no-landmarks"])
        img = out["outputs"]["images"][0]
        by = ids(img["checks"])
        assert by["grade_uniform"]["level"] == "pass" and by["skin_de00"]["level"] == "skip", by
        assert by["grade_landmarks"]["level"] == "skip" and img["metrics"]["face"]["grade"] == "mono", by["grade_landmarks"]
        assert by["hook_words"]["level"] == "pass" and by["phrase_line_h"]["threshold"] == 0.20, by["phrase_line_h"]
        assert all(c["level"] != "error" for c in img["checks"] if c["id"].startswith("grade")), img["errors"]
        b, fb, _ = people[1]
        gb = _grade_rgba(b, mono_curve)
        x, y, w, h = fb
        gb[int(y):int(y + h), int(x):int(x + w), :3] = np.clip(gb[int(y):int(y + h), int(x):int(x + w), :3] * 1.12, 0, 255).astype(np.uint8)
        bad = write_mono_render(d, "bad", people, [_grade_rgba(people[0][0], mono_curve), gb])
        code, out = _run([str(bad), "--out", str(d / "qa"), "--no-landmarks"])
        img = out["outputs"]["images"][0]
        assert code == 1 and any(c["id"] == "grade_face" and c["level"] == "error" for c in img["checks"]), img["errors"]


# ── Palette del brand dal sidecar ───────────────────────────────────────────
def test_palette_from_sidecar():
    # il sidecar di yt-thumb-render porta la palette del brand: il cerchio d'accento si cerca con QUEL colore
    data = {"palette": {"accents": {"blu": "#2f6bff", "verde": "#18b26b"}}}
    assert tq.accent_hex(data, "blu") == "#2f6bff" and tq.accent_hex(data, "#123456") == "#123456"
    assert tq.accent_hex(data, "accent") is None and set(tq.palette_accents(data)) == {"blu", "verde"}
    # senza palette: gli accenti del brand demo del plugin
    assert set(tq.palette_accents({})) == {"accent", "accent_2", "accent_3"} and tq.accent_hex({}, "accent_2") == "#35d49a"


def main() -> int:
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f) and flt in n]
    failed = 0
    t0 = time.time()
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} test passati in {time.time() - t0:.1f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
