"""Test del contratto v2 di yt-thumb-render e degli effetti di lib/thumb_fx.py (thumbnail v2). Niente pytest: assert semplici.

Uso (venv del toolkit; YT_DATA = data dir del plugin o una data dir temporanea di install.sh --data):
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_thumb_v2.py            # tutti
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_thumb_v2.py hook       # solo i test col nome che contiene «hook»
I test di render (render_*) girano solo se Playwright è installato (yt-install / /youtube:setup); le persone, il set, la
schermata e il video della sorgente sono SINTETICI (tests/synthetic_people.py), generati in una cartella temporanea:
nessuna persona reale, nessun dato di canale. Il brand è il neutro «demo» del plugin.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import synthetic_people as sp  # noqa: E402
import thumb_fx as fx  # noqa: E402
import thumb_render as tr  # noqa: E402

BRAND_DIR = HERE.parent / "assets" / "brands" / "demo"
TOKENS = json.loads((BRAND_DIR / "tokens.json").read_text())
BIN = HERE.parent / "bin"


# ── colore e LUT ────────────────────────────────────────────────────────────
def test_ciede2000_reference_pairs():
    # Sharma, Wu, Dalal (2005), tabella dei dati di prova
    L1 = np.array([[50, 2.6772, -79.7751], [50, 3.1571, -77.2803], [50, 0, 0], [60.2574, -34.0099, 36.2677],
                   [63.0109, -31.0961, -5.8663], [2.0776, 0.0795, -1.1350]])
    L2 = np.array([[50, 0, -82.7485], [50, 0, -82.7485], [50, -1, 2], [60.4626, -34.1751, 39.4387],
                   [62.8187, -29.7946, -4.0864], [0.9033, -0.0636, -0.5514]])
    exp = [2.0425, 2.8615, 2.3669, 1.2644, 1.2630, 0.9082]
    got = fx.ciede2000(L1, L2)
    assert np.allclose(got, exp, atol=1e-4), got


def test_lut_cube_roundtrip_and_no_saturation_boost():
    ink, paper = fx.brand_colors(TOKENS)
    lut = fx.make_lut(lambda x: fx.brand_look(x, ink, paper), n=17)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.cube"
        fx.write_cube(p, lut, "t")
        back = fx.read_cube(p)
    assert np.allclose(back, lut, atol=1e-5)
    # nessun aumento di saturazione: saturazione CIE s = C*/L* dopo ≤ prima × 1.03 (p95)
    rng = np.random.default_rng(0)
    px = rng.uniform(0.25, 0.75, (2000, 3))
    out = fx.apply_lut(px, lut)
    l0, l1 = fx.rgb_to_lab(px), fx.rgb_to_lab(out)
    s0 = np.hypot(l0[:, 1], l0[:, 2]) / np.maximum(l0[:, 0], 1)
    s1 = np.hypot(l1[:, 1], l1[:, 2]) / np.maximum(l1[:, 0], 1)
    ratio = np.percentile(s1 / np.maximum(s0, 1e-6), 95)
    assert ratio <= 1.03 + 1e-6, ratio
    # più contrasto: le ombre scendono, le luci salgono
    assert fx.luma(fx.apply_lut(np.array([[0.3, 0.3, 0.3]]), lut))[0] < 0.3
    assert fx.luma(fx.apply_lut(np.array([[0.7, 0.7, 0.7]]), lut))[0] > 0.7


def test_brand_lut_files_match_tokens():
    f = BRAND_DIR / fx.LOOK_FILE
    assert f.is_file(), f"manca {f} (python3 lib/thumb_fx.py lut --brand demo)"
    ink, paper = fx.brand_colors(TOKENS)
    assert np.allclose(fx.read_cube(f), fx.make_lut(lambda x: fx.brand_look(x, ink, paper)), atol=2e-6)
    m = BRAND_DIR / fx.MONO_CUBE
    assert m.is_file(), f"manca {m} (python3 lib/thumb_fx.py mono-lut --brand demo)"
    p = fx.mono_params(TOKENS, BRAND_DIR)
    assert p["id"] == "mono-1" and (BRAND_DIR / fx.MONO_FILE).is_file()
    assert np.allclose(fx.read_cube(m), fx.make_lut(lambda x: fx.mono_grade(x, p, ink, paper)), atol=2e-6)


def test_demo_brand_tokens_contract():
    c = TOKENS["colors"]
    assert {"ink", "paper"} <= set(c) and TOKENS["accent"] in c, TOKENS
    names = fx.accent_names(TOKENS)
    assert names == ["accent", "accent_2", "accent_3"] and all(n in c for n in TOKENS["accents_auto"]), names
    for f in TOKENS["fonts"].values():
        assert (HERE.parent / "assets" / "fonts" / f["file"]).is_file(), f
    for rel in TOKENS["logo"].values():
        assert (BRAND_DIR / rel).is_file(), rel
    # testo inchiostro su ogni accento ≥ 4.5:1 (box della parola chiave)
    for n in names:
        assert tr.contrast(c["ink"], c[n]) >= 4.5, (n, tr.contrast(c["ink"], c[n]))
    layout = json.loads((BRAND_DIR / "layout.json").read_text())
    assert layout["canvas"] == {"w": 3840, "h": 2160} and layout["wide"]["w"] == 3840 and "inset" not in layout


def _skin_cutout(path: Path, hole: bool = False) -> list[float]:
    w, h = 400, 520
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([110, 60, 290, 280], fill=(214, 160, 130, 255))             # volto
    d.rectangle([60, 260, 340, 520], fill=(60, 50, 70, 255))               # busto
    rng = np.random.default_rng(1)
    a = np.asarray(im).copy()
    noise = rng.normal(0, 6, a[..., :3].shape)
    a[..., :3] = np.clip(a[..., :3] + noise * (a[..., 3:] > 0), 0, 255)
    if hole:
        a[150:175, 150:185, 3] = 0                                          # «lente» trasparente dentro il volto
    Image.fromarray(a.astype(np.uint8), "RGBA").save(path)
    return [110 / w, 60 / h, 180 / w, 220 / h]


def test_tone_cutout_respects_skin_gate():
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "c.png", Path(td) / "t.png"
        face = _skin_cutout(src)
        for mode in ("look", "duo"):
            r = fx.tone_cutout(src, dst, mode, face, TOKENS)
            assert r["pass"], r
            assert r["skin_de00_mean"] <= 2.5 and r["skin_de00_p95"] <= 5.0, r
            assert 0 < r["strength"] <= 1
            a0 = np.asarray(Image.open(src))[..., 3]
            a1 = np.asarray(Image.open(dst))[..., 3]
            assert np.array_equal(a0, a1), "il tono non deve cambiare l'alpha"
        # forza imposta oltre la soglia → pass False
        r = fx.tone_cutout(src, dst, "duo", face, TOKENS, strength=1.0)
        assert not r["pass"], r


def test_matte_holes_only_enclosed():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c.png"
        face = _skin_cutout(p, hole=True)
        a = np.asarray(Image.open(p).getchannel("A"), np.float64) / 255
        h = fx.matte_holes(a, face)
        assert h["holes"] >= 1 and h["hole_frac"] > tr.HOLE_ERR, h
        p2 = Path(td) / "c2.png"
        face2 = _skin_cutout(p2, hole=False)
        a2 = np.asarray(Image.open(p2).getchannel("A"), np.float64) / 255
        # box del volto allargato che sporge sullo sfondo (profilo): lo sfondo non è un «buco»
        h2 = fx.matte_holes(a2, [face2[0] - 0.1, face2[1], face2[2] + 0.2, face2[3]])
        assert h2["hole_px"] == 0, h2
    # il bordo morbido ESTERNO della sagoma (0.5 ≤ α < 0.9, capelli e guance) non è un buco: contarlo darebbe 1–2,5 %
    # su quasi ogni ritaglio e bloccherebbe ogni guest_style graphic
    a3 = np.zeros((200, 200))
    a3[20:190, 40:160] = 1.0
    a3[20:190, 40:44] = 0.7
    a3[20:24, 40:160] = 0.6
    h3 = fx.matte_holes(a3, [0.25, 0.12, 0.5, 0.5])
    assert h3["hole_px"] == 0, h3


def test_changed_pixels_and_served_detail():
    a = np.zeros((40, 40, 3), np.uint8)
    b = a.copy()
    b[5, 5] = [1, 0, 0]
    b[6, 6] = [9, 0, 0]
    m = np.ones((40, 40), bool)
    r = fx.changed_pixels(a, b, m)
    assert r == {"px": 1600, "changed": 2, "changed_gt1": 1, "max": 9}, r
    # dettaglio al formato servito: un volto a scacchi è nitido, uno piatto no
    im = Image.new("RGB", (1280, 720), (90, 90, 90))
    d = ImageDraw.Draw(im)
    for i in range(0, 300, 6):
        for j in range(0, 300, 6):
            if (i + j) // 6 % 2:
                d.rectangle([500 + i, 200 + j, 503 + i, 203 + j], fill=(240, 240, 240))
    sharp = fx.served_detail(im, [500, 200, 300, 300])
    flat = fx.served_detail(Image.new("RGB", (1280, 720), (90, 90, 90)), [500, 200, 300, 300])
    assert sharp["lap"] > tr.SERVED_WARN and flat["lap"] < 1, (sharp, flat)


def test_face_surround_dL():
    im = np.full((720, 1280, 3), 200, np.uint8)
    im[200:500, 500:780] = 60                               # volto scuro su fondo chiaro
    dl = fx.face_surround_dL(im, [500, 200, 280, 300], [])
    assert dl and dl > 40, dl
    same = np.full((720, 1280, 3), 120, np.uint8)
    assert fx.face_surround_dL(same, [500, 200, 280, 300], []) < 1


# ── contratto del concept, template, brand e default del profilo ────────────
def test_hook_rules():
    ok = lambda h, **kw: tr.validate_hook({"hook": h, "keyword": kw.pop("kw", h.split()[-1]), "payoff_at": 1.0, **kw}, "ritratto")  # noqa: E731
    e, w, i = ok("UNA LISTA", kw="LISTA")
    assert any("2 parole" in x for x in e), e
    e, w, i = ok("UNA LISTA LUNGHISSIMA", kw="LISTA")
    assert any("frammento nominale" in x for x in e), e
    e, w, i = ok("Lo provammo con una lista", kw="lista")
    assert not e, e
    e, w, i = ok("Perché vendere una tazza?", kw="tazza")
    assert not e and "vendere" in [v.lower() for v in i["verbs"]], (e, i)
    e, w, i = ok("Il codice non si riscrive", kw="codice")
    assert not e and "riscrive" in [v.lower() for v in i["verbs"]], (e, i)
    e, w, i = ok("Socio o da sola?", kw="socio")
    assert not e and any("domanda senza verbo" in x for x in w), (e, w)
    e, w, i = ok("$40K ARR in 9 mesi", kw="ARR")
    assert any("number_verified" in x for x in e), e
    e, w, i = ok("$40K ARR in 9 mesi", kw="ARR", number_verified="transcript 12:40")
    assert not e and i["number_unit"], (e, i)
    e, w, i = ok("Ho detto no ai soldi veri oggi", kw="soldi")
    assert not e and any("7 parole" in x for x in w), (e, w)
    e, w, i = tr.validate_hook({"hook": "Lo provammo con una lista", "keyword": "tazza", "payoff_at": 1}, "ritratto")
    assert any("assente dal gancio" in x for x in e), e
    e, w, i = tr.validate_hook({"hook": "L'ho chiuso io", "keyword": "chiuso"}, "ritratto")
    assert not e and i["words"] == 4 and any("timestamp" in x for x in w), (e, w, i)
    # duo (anche nella variante di un brand, <slug>-duo): 3–4 parole, oltre è un errore salvo hook_size_reason
    for t in ("duo", "acme-duo"):
        e, w, i = tr.validate_hook({"hook": "Lo provammo con una lista", "keyword": "lista", "payoff_at": 1}, t)
        assert any("duo: gancio di 5 parole" in x for x in e), (t, e)
    e, w, i = tr.validate_hook({"hook": "Lo provammo con una lista", "keyword": "lista", "payoff_at": 1, "hook_size_reason": "x"}, "duo")
    assert not e and any("motivo dichiarato" in x for x in w), (e, w)


def test_normalize_concept_backward_compatible():
    c = tr.normalize_concept({"id": "A", "hook": "Lo provammo con una lista", "keyword": "lista"})
    assert c["text"] == "Lo provammo con una lista" and c["highlight"] == "lista"
    old = tr.normalize_concept({"id": "B", "text": "UNA LISTA", "highlight": "LISTA", "plate": "p.jpg"})
    assert old["text"] == "UNA LISTA" and old["highlight"] == "LISTA" and old["plate"] == "p.jpg"


def test_prop_request_spec_is_text_only():
    r = tr.prop_request({"id": "A", "accent": "accent_2"}, "una tazza di ceramica", "behind-guest", TOKENS)
    assert r["status"] == "da approvare" and r["budget"]["cap_eur_episode"] == 5 and r["budget"]["cap_eur_month"] == 20
    txt = " ".join(r["constraints"])
    assert "mai persone" in txt and "nessun upload" in txt and TOKENS["colors"]["accent_2"] in txt
    r = tr.prop_request({"id": "A", "accent": "auto"}, None, "plate", TOKENS, {"episode": 2, "month": 8})
    assert r["budget"]["cap_eur_episode"] == 2 and TOKENS["colors"]["accent"] in " ".join(r["constraints"])


def test_v2_colour_pairs():
    pairs, warns = tr.color_pairs("duo", {"accent": "accent"}, TOKENS)
    names = {p["pair"] for p in pairs}
    # «accent» regge l'inchiostro solo a corpo grande (5,8:1 < 7): targhetta del nome su carta
    assert "ink-on-accent" in names and "ink-on-paper" in names and not warns, (pairs, warns)
    pairs, warns = tr.color_pairs("ritratto", {"accent": "accent_2"}, TOKENS)
    assert {p["pair"] for p in pairs} >= {"ink-on-accent_2"} and not warns and tr.plate_box_name(TOKENS, "accent_2") == "accent_2"
    pairs, warns = tr.color_pairs("generic", {}, TOKENS)
    assert pairs and pairs[0]["pair"] == "fg-on-bg" and pairs[0]["allowed"], pairs


def test_template_names_and_brand_override():
    assert tr.base_template("duo") == "duo" and tr.base_template("acme-duo") == "duo"
    assert tr.base_template("acme-copertina") == "acme-copertina" and tr.base_template(None) == ""
    for n in tr.BUILTIN_TEMPLATES:
        assert tr.find_template(n) == tr.TEMPLATES_DIR / f"{n}.html", n
    assert tr.find_template("acme-duo") is None and tr.find_template("sconosciuto") is None and tr.find_template("../x") is None
    assert set(tr.available_templates()) >= set(tr.BUILTIN_TEMPLATES)
    with tempfile.TemporaryDirectory() as td:
        bd = Path(td) / "acme"
        (bd / "templates").mkdir(parents=True)
        (bd / "tokens.json").write_text(json.dumps({"slug": "acme", "colors": {"ink": "#000000", "paper": "#ffffff", "accent": "#ff0000"}}))
        (bd / "templates" / "acme-duo.html").write_text("<!doctype html>")
        (bd / "templates" / "acme-copertina.html").write_text("<!doctype html>")
        orig = tr._external_brand_dirs
        tr._external_brand_dirs = lambda: [bd]
        try:
            assert tr.find_template("duo", "acme") == bd / "templates" / "acme-duo.html"       # variante del brand
            assert tr.find_template("duo", "altro") == tr.TEMPLATES_DIR / "duo.html"           # altri brand: incluso
            assert tr.find_template("ritratto", "acme") == tr.TEMPLATES_DIR / "ritratto.html"  # nessuna variante
            assert tr.find_template("acme-copertina") == bd / "templates" / "acme-copertina.html"
            assert tr.template_brand_dir(bd / "templates" / "acme-duo.html") == bd
            assert "acme-copertina" in tr.available_templates() and "acme-duo" in tr.available_templates()
            assert tr.brand_of("duo", None, bd / "templates" / "acme-duo.html") == "acme"
        finally:
            tr._external_brand_dirs = orig
    assert tr.brand_of("duo", None, tr.TEMPLATES_DIR / "duo.html") == tr.DEFAULT_BRAND == "demo"
    assert tr.brand_of("duo", "acme", None) == "acme"
    # slug del brand con trattini: «caffe-maker-duo» resta un duo (regole v2, default del profilo, QA), come thumb_learn
    import thumb_learn as tl
    import thumb_qa as qa
    for n, base in (("caffe-maker-duo", "duo"), ("caffe-maker-ritratto", "ritratto"), ("caffe-maker-generic", "generic"),
                    ("caffe-maker-copertina", "caffe-maker-copertina")):
        assert tr.base_template(n) == base and qa.base_template(n) == base, (n, tr.base_template(n), qa.base_template(n))
    assert tl.v2_base("caffe-maker-duo") == "duo" and qa.template_kind("caffe-maker-duo", None) == "duo"
    with tempfile.TemporaryDirectory() as td:
        a, b = Path(td) / "caffe", Path(td) / "caffe-maker"
        for bd in (a, b):
            (bd / "templates").mkdir(parents=True)
            (bd / "tokens.json").write_text(json.dumps({"slug": bd.name, "colors": {"ink": "#000000", "paper": "#ffffff"}}))
        (a / "templates" / "caffe-maker-duo.html").write_text("<!doctype html>")   # omonimo in un altro brand
        (b / "templates" / "caffe-maker-duo.html").write_text("<!doctype html>")
        orig = tr._external_brand_dirs
        tr._external_brand_dirs = lambda: [a, b]
        try:
            assert tr.find_template("caffe-maker-duo") == b / "templates" / "caffe-maker-duo.html"   # prefisso più lungo
            assert tr.find_template("duo", "caffe-maker") == b / "templates" / "caffe-maker-duo.html"
        finally:
            tr._external_brand_dirs = orig


def test_client_remotion_guard_and_layout_resolver():
    """Remotion mai per un canale kind: client, anche senza cartella brand (ricade su demo); layout.json con un solo
    risolutore per yt-clips, yt-portrait e yt-thumb-render (brand.slug del profilo, poi la cartella del canale)."""
    import clips
    import portrait
    yc = tr.yc
    with tempfile.TemporaryDirectory() as td:
        ch_dir, br_dir = Path(td) / "channels", Path(td) / "brands"
        ch_dir.mkdir()
        prof = "---\nslug: {s}\nkind: {k}\ngraphics_engine: hyperframes\npaid_services: []\n{b}---\n"
        (ch_dir / "cliente-x.md").write_text(prof.format(s="cliente-x", k="client", b=""))
        (ch_dir / "mio-canale.md").write_text(prof.format(s="mio-canale", k="own", b=""))
        (ch_dir / "acme-pod.md").write_text(prof.format(s="acme-pod", k="own", b="brand:\n  slug: acme\n"))
        (ch_dir / "pod-x.md").write_text(prof.format(s="pod-x", k="own", b=""))
        acme = br_dir / "acme"
        acme.mkdir(parents=True)
        (acme / "tokens.json").write_text(json.dumps({"slug": "acme", "colors": {"ink": "#000000", "paper": "#ffffff"}}))
        inset = {"canvas": {"w": 3840, "h": 2160}, "inset": {"x": 2600, "y": 200, "w": 1000, "h": 1800},
                 "pip": {"x": 100, "y": 1700, "w": 600, "h": 340}}
        (acme / "layout.json").write_text(json.dumps(inset))
        (br_dir / "pod-x").mkdir()                                     # canale senza token: solo il layout misurato
        (br_dir / "pod-x" / "layout.json").write_text(json.dumps(inset))
        yc.CHANNELS_DIRS.insert(0, ch_dir)
        yc.BRANDS_DIRS.insert(0, br_dir)
        try:
            # licenza Remotion: il canale cliente senza brand ricade su demo, ma resta un cliente
            assert tr.brand_of("generic", None, None, {}, "cliente-x") == "demo" and yc.own_brand("demo")
            assert not yc.remotion_allowed("demo", "cliente-x") and yc.remotion_allowed("demo", "mio-canale")
            assert yc.remotion_allowed("demo", None) and not yc.remotion_allowed("acme-sconosciuto", None)
            # (a) brand.slug diverso dallo slug del canale: tutti leggono brands/acme/layout.json
            assert clips.layout_file("acme-pod") == acme / "layout.json" == yc.layout_file("acme-pod")
            assert portrait.is_composite(portrait.brand_layout("acme-pod"))
            assert tr.resolve_roi("inset", tr.brand_of("generic", None, None, {}, "acme-pod"), "acme-pod")
            # (b) canale senza token, layout misurato in <brands_dir>/<canale>/: anche il ritaglio della thumbnail lo trova
            assert tr.brand_of("generic", None, None, {}, "pod-x") == "demo"
            assert tr.resolve_roi("inset", "demo", "pod-x") == "2600,200,1000,1800"
            assert tr.layout_rect("demo", "pip", None, "pod-x") == [100, 1700, 600, 340]
            assert portrait.is_composite(portrait.brand_layout("pod-x"))
            # senza layout misurato: demo generico per yt-clips, nessuna geometria composita per yt-portrait
            assert clips.layout_file("mio-canale") == yc.brand_file("demo", "layout.json")
            assert portrait.brand_layout("mio-canale") is None
            # preset ASS neutro «default»: colori del brand del canale (se ha ink, paper, accent), altrimenti demo
            import captions as cap
            (acme / "tokens.json").write_text(json.dumps({"slug": "acme", "colors": {
                "ink": "#101010", "paper": "#fafafa", "accent": "#2255ee"}}))
            pre = cap.load_preset("default")
            t = cap.preset_tokens(pre, "default", "acme-pod")
            assert cap.preset_brand(pre, "default", "acme-pod") == "acme"
            assert t["colors"]["accent"] == t["colors"]["accent_2"] == t["colors"]["accent_3"] == "#2255ee", t
            assert cap.preset_tokens(pre, "default", "mio-canale") == yc.brand_tokens("demo")
            assert cap.preset_tokens(pre, "default", None) == yc.brand_tokens("demo")
        finally:
            yc.CHANNELS_DIRS.remove(ch_dir)
            yc.BRANDS_DIRS.remove(br_dir)


def test_profile_thumbnail_defaults():
    prof = {"thumbnails": {"default_template": "duo", "grade_default": {"duo": "mono", "others": "natural"}, "accent": "auto",
                           "guest_style_default": "none", "display_cap": "b", "format_label": "IL CAFFÈ DEI MAKER",
                           "host_tag": "con [Nome dell'host]", "show_logo": "symbol", "props_budget": {"per_episode_eur": 3, "per_month_eur": 9},
                           "accents": ["accent_2", "accent_3"], "grade_allowed": ["natural", "mono"], "guest_style_allowed": ["none"]}}
    d = tr.thumb_defaults(prof)
    assert d["accents"] == ["accent_2", "accent_3"] and d["guest_style_allowed"] == ["none"], d
    assert tr._placeholder("[facoltativo: etichetta]") and tr._placeholder("<slug>") and not tr._placeholder("IL CAFFÈ DEI MAKER")
    assert d["default_template"] == "duo" and d["display_cap"] == 1.5 and d["show_logo"] == "symbol", d
    assert "host_tag" not in d and d["props_budget"] == {"episode": 3, "month": 9}, d          # segnaposto ignorato
    assert tr.grade_for("duo", d) == "mono" and tr.grade_for("acme-duo", d) == "mono" and tr.grade_for("ritratto", d) == "natural"
    c = tr.apply_defaults({"id": "A"}, "duo", d)
    assert c["grade"] == "mono" and c["accent"] == "auto" and c["guest_style"] == "none" and c["format_label"] == "IL CAFFÈ DEI MAKER"
    assert tr.apply_defaults({"id": "A", "grade": "natural", "show_logo": False}, "duo", d)["grade"] == "natural"
    assert tr.apply_defaults({"id": "A", "show_logo": False}, "duo", d)["show_logo"] is False                # il concept vince
    assert tr.apply_defaults({"id": "A"}, "generic", d) == {"id": "A"}                                        # solo telaio v2
    # senza profilo: natural, auto, none (i valori del modello di profilo)
    g = tr.apply_defaults({"id": "A"}, "ritratto", tr.thumb_defaults({}))
    assert g == {"id": "A", "grade": "natural", "accent": "auto", "guest_style": "none"}, g
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td) / "canale-esempio" / "2026-03-02-puntata"
        (wd / "thumbs").mkdir(parents=True)
        (wd / "project.json").write_text(json.dumps({"channel": "canale-esempio"}))
        assert tr.channel_of(wd / "thumbs" / "concepts.json") == "canale-esempio"
        assert tr.channel_of(wd / "thumbs" / "concepts.json", {"channel": "altro"}) == "altro"
        assert tr.channel_of(wd / "thumbs" / "concepts.json", {}, "cli") == "cli"


def test_accent_palette_helpers():
    assert tr.accent_names(TOKENS) == ["accent", "accent_2", "accent_3"] and tr.default_accent(TOKENS) == "accent"
    pal = tr.palette_of(TOKENS)
    assert pal["accents"]["accent_2"] == TOKENS["colors"]["accent_2"] and pal["ink"] == TOKENS["colors"]["ink"]
    loose = {"colors": {"bg": "#000", "fg": "#fff", "brand_red": "#e00000"}}
    assert fx.accent_names(loose) == ["brand_red"]
    tones = {"hair_L": 15.0, "face_L": 62.0}
    ac = fx.accent_contrast(tones, TOKENS, TOKENS["accents_auto"])
    assert set(ac["by_accent"]) == {"accent", "accent_2", "accent_3"} and ac["best"] in TOKENS["accents_auto"], ac


# ── render (Playwright + persone sintetiche) ────────────────────────────────
_FIX: dict = {}


def _playwright_ready() -> bool:
    ok, why = tr.yc.npm_project_status(tr.yc.NODE_DIR, tr.yc.NODE_PREFIX)
    if not ok:
        print("   (saltato: Playwright non installato:", why, ")")
    return ok


def fixtures() -> dict:
    """Persone, set, schermata e video sintetici, generati una volta per esecuzione (cartella temporanea)."""
    if _FIX:
        return _FIX
    d = Path(tempfile.mkdtemp(prefix="yt-thumb-v2-"))
    atexit.register(shutil.rmtree, d, True)
    frame = sp.make_set(3840, 2160, seed=7)
    Image.fromarray(frame).save(d / "set.png")
    guest = sp.make_person((2700, 2500), 880, seed=11, skin=(206, 160, 128), hair=(40, 30, 26), shirt=(176, 66, 52), face_top=0.17)
    video = d / "camera.mp4"
    frame, _ = sp.cut_from_frame(frame, guest, (1500, 120), d / "ospite.png", video=str(video), t=0.5)
    Image.fromarray(frame).save(d / "frame.png")
    have_video = Path(tr.yc.FFMPEG).exists()
    if have_video:
        sp.encode_still_video(d / "frame.png", video, tr.yc.FFMPEG)
    sp.write_cut(d / "ospite_duo.png", *sp.make_person((2300, 2000), 712, seed=12, skin=(198, 150, 120), hair=(30, 24, 22),
                                                         shirt=(60, 96, 70), face_top=0.16))
    sp.write_cut(d / "host_duo.png", *sp.make_person((2300, 2000), 660, seed=13, skin=(224, 182, 150), hair=(92, 64, 40),
                                                       shirt=(214, 214, 206), face_top=0.16))
    # host «del campo largo»: volto disegnato grande ma con poca risoluzione effettiva (66 px): il tetto lo rimpicciolisce
    hw, hf = sp.make_person((2300, 2000), 648, seed=16, face_top=0.16)
    sp.write_cut(d / "host_largo.png", hw, hf, eff_face_px=66.0)
    sp.write_cut(d / "ospite_prova.png", *sp.make_person((2000, 1700), 640, seed=14, face_top=0.17))
    sp.make_artifact(d / "schermata.png")
    _FIX.update({"dir": d, "video": have_video})
    return _FIX


def _env(**extra) -> dict:
    env = {**os.environ, **extra}
    return env


def _render(concepts: list, out: Path, *extra, env: dict | None = None) -> tuple[int, dict]:
    data = out / "c.json"
    data.write_text(json.dumps(concepts, ensure_ascii=False))
    p = subprocess.run([str(BIN / "yt-thumb-render"), "--data", str(data), "--out", str(out), *extra], capture_output=True, text=True,
                       env=env or _env())
    try:
        return p.returncode, json.loads(p.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"output non JSON (exit {p.returncode}): {p.stderr[-800:]}")


GUEST = {"role": "guest", "name": "Paolo Bianchi", "title": "Fondatore di Officina Esempio"}


def test_render_v2_ritratto_passes_and_protects_face_pixels():
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "r", "template": "ritratto", "hook": "Lo provammo con una lista", "keyword": "lista", "accent": "accent_2",
             "people": [{"cutout": str(F / "ospite.png"), **GUEST}], "meta_line": "PUNTATA 12 / 2026",
             "format_label": "IL CAFFÈ DEI MAKER", "payoff_at": 750.0, "person_tone": "look", "guest_style": "graphic"}
        code, res = _render([c], out)
        r = res["outputs"]["renders"][0]
        assert r["ok"], r
        assert code == (0 if r["pass"] else 3), (code, r.get("errors"))
        assert r["brand"] == "demo" and r["palette"]["accents"]["accent_2"] == TOKENS["colors"]["accent_2"], r.get("palette")
        cv = r["checks_v2"]
        h = cv["heroes"][0]
        assert h["face_pixels_unchanged"]["changed_gt1"] == 0, h
        assert h["tone"]["pass"] and h["tone"]["skin_de00_mean"] <= 2.5, h
        assert cv["accents"] == ["accent_2"] and cv["credentials"], cv
        assert all(x["frac"] >= tr.HOOK_ROW_MIN for x in cv["hook_rows"]), cv["hook_rows"]
        series = r["metrics"]["series"]
        assert series["template"] == "ritratto" and series["wordmark"]["text"] == TOKENS["wordmark"]["text"], series.get("wordmark")
        assert {u["kind"] for u in series["under"]} >= {"glow", "outline"}, series["under"]
        assert r["pass"], r["errors"]
        side = json.loads(Path(r["png"]).with_suffix(".render.json").read_text())
        assert side["spec"]["grade"] == "natural" and side["spec"]["guest_style"] == "graphic"


def test_render_v2_accented_line_opens_leading():
    # «È PIÙ» sotto «NESSUN SOFTWARE»: in Anton l'accento arriva a 1,10 em sopra la linea di base, l'interlinea è 0.9 →
    # la riga con la maiuscola accentata si apre (≥ 1,12 em tra le linee di base), le altre restano a 0.9
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "acc", "template": "ritratto", "hook": "Nessun software | è più | difendibile.", "keyword": "difendibile",
             "accent": "accent_2", "payoff_at": 2581.8, "people": [{"cutout": str(F / "ospite.png"), **GUEST}]}
        code, res = _render([c], out)
        r = res["outputs"]["renders"][0]
        hook = next(t for t in r["metrics"]["texts"] if t.get("kind") == "hook")
        rows, size = hook["rows"], hook["size"]
        ink = [{"y": q[1], "h": q[3]} for q in hook["rects"]]                    # rects: inchiostro vero, accenti compresi
        assert len(rows) == 3 and len(ink) == 3, (rows, ink)
        base = [x["y"] + x["h"] for x in rows]                                   # righe di glifi: fondo = linea di base
        assert base[1] - base[0] >= 1.12 * size, (rows, size)                    # riga «È PIÙ»: aperta
        assert ink[1]["y"] >= ink[0]["y"] + ink[0]["h"], (ink, size)             # l'accento non entra nella riga sopra
        assert ink[1]["h"] > ink[0]["h"] * 1.15, ink                             # l'inchiostro della riga comprende l'accento
        # rows (altezza di riga dei controlli): le maiuscole senza l'accento, come le altre righe
        assert abs(rows[1]["h"] - rows[0]["h"]) <= 0.04 * rows[0]["h"], rows


def test_render_v2_fragment_hook_fails_with_exit_3():
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "f", "template": "ritratto", "hook": "UNA LISTA", "keyword": "LISTA", "payoff_at": 2.8,
             "people": [{"cutout": str(F / "ospite.png"), **GUEST}]}
        code, res = _render([c], out)
        r = res["outputs"]["renders"][0]
        assert r["ok"] and not r["pass"] and code == 3, (code, r.get("errors"))
        assert any("2 parole" in e for e in r["errors"]), r["errors"]


def test_render_v2_duo_display_cap_blocks_wide_host():
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "d", "template": "duo", "hook": "Vendere una tazza?", "keyword": "tazza", "payoff_at": 742.0,
             "people": [{"cutout": str(F / "host_largo.png"), "role": "host", "name": "Giulia Neri"},
                        {"cutout": str(F / "ospite_duo.png"), **GUEST}]}
        code, res = _render([c], out)
        r = res["outputs"]["renders"][0]
        assert r["ok"] and code == 3, (code, r.get("error"))
        # il template rispetta il tetto al display da solo: l'host (eff 66 px) resta piccolo → il duo fallisce il 30%
        fr = {h["role"]: h["face_frac"] for h in r["checks_v2"]["heroes"]}
        assert fr["host"] < tr.FACE_DUO_MIN and any("duo: volto" in e for e in r["errors"]), (fr, r["errors"])
        for h in r["checks2"]["heroes"]:
            assert h["display_upscale"] <= tr.DISPLAY_CAP + 0.02, h


def test_render_v2_duo_natural_frame():
    """duo con i default del modello di profilo (natural, accent auto): telaio completo, accento scelto per contrasto,
    disco di campo misurato, wordmark e etichetta dell'host dai token e dal concept."""
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "n", "template": "duo", "hook": "L'ho venduta.", "keyword": "venduta", "payoff_at": 120.0,
             "people": [{"cutout": str(F / "host_duo.png"), "role": "host", "name": "Giulia Neri"}, {"cutout": str(F / "ospite_duo.png"), **GUEST}],
             "plate": {"source": "scene", "path": str(F / "set.png")}, "meta_line": "PUNTATA LIVE / 2026", "format_label": "IL CAFFÈ DEI MAKER"}
        code, res = _render([c], out)
        r = res["outputs"]["renders"][0]
        assert r["ok"], r.get("error")
        assert r["checks_v2"]["grade"]["mode"] == "natural" and r["v2"]["accent_choice"]["chosen"] in TOKENS["accents_auto"], r["v2"]
        s = r["metrics"]["series"]
        assert s["host_tag"]["text"] == "con Giulia Neri" and s["layout"]["reached"], s
        assert s["disc"] and r["checks_v2"]["circle"][0]["dL_edge"] is not None, r["checks_v2"].get("circle")
        assert r["checks_v2"]["accents"] == [r["v2"]["accent"]] and all(x["frac"] >= tr.DUO_ROW_MIN for x in r["checks_v2"]["hook_rows"])
        assert not [e for e in r["errors"] if "face_pixels_unchanged" not in e], r["errors"]   # ±1 di Chrome a parte


def test_render_v2_duo_mono_2b():
    """duo col grade mono (livello 2b): stessa curva su persone e plate, mappatura esatta, accento scelto per contrasto,
    disco di campo misurato, righe del titolo misurate sulle maiuscole. MediaPipe spento: su volti disegnati i landmark
    non dicono niente (la verifica con un volto vero è in test_thumb_qa.test_grade_landmarks_real)."""
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "m", "template": "duo", "grade": "mono", "accent": "auto", "hook": "È andata bene così.", "payoff_at": 1283.5,
             "people": [{"cutout": str(F / "host_duo.png"), "role": "host", "name": "Giulia Neri"},
                        {"cutout": str(F / "ospite_duo.png"), **GUEST}],
             "plate": {"source": "scene", "path": str(F / "set.png")},
             "show_logo": "wordmark", "meta_line": "PUNTATA LIVE / 2026", "format_label": "IL CAFFÈ DEI MAKER",
             "face_floor_reason": "test", "hook_size_reason": "test"}
        code, res = _render([c], out, env=_env(YT_MP_MODEL=str(Path(td) / "nessun-modello.task")))
        r = res["outputs"]["renders"][0]
        assert r["ok"], r.get("error")
        g = r["checks_v2"]["grade"]
        assert g["mode"] == "mono" and g["level"] == "2b" and g["pass"], (g, r["errors"])
        assert len(set(g["people_signatures"])) == 1 and g["people_signatures"][0] == g["signature"], g
        assert g["plate_signature"] == g["signature"], g
        for h in r["checks_v2"]["heroes"]:
            t = h["tone"]
            assert t["mode"] == "mono" and t["mapping"]["pass"] and t["mapping"]["max_dev_levels"] <= tr.MAP_TOL_LEVELS, t
        assert not any("ΔE00" in e for e in r["errors"]), r["errors"]                  # niente soglia della pelle sul mono
        assert r["v2"]["accent_choice"]["chosen"] in TOKENS["accents_auto"], r["v2"]["accent_choice"]
        assert r["checks_v2"].get("circle") and r["checks_v2"]["circle"][0]["dL_edge"] is not None, r["checks_v2"].get("circle")
        es = r["checks_v2"]["edge_dark"]
        assert {"edge_dL_dark", "edge_light_share", "edge_light_run"} <= set(es) and es["edge_light_run"] <= es["edge_light_share"], es
        # righe del gancio: maiuscole senza accento (È, Ì) → le righe hanno la stessa altezza a meno del 4 %
        hook = next(t for t in r["metrics"]["texts"] if t.get("kind") == "hook")
        hs = [x["h"] for x in hook["rows"]]
        assert max(hs) - min(hs) <= 0.04 * max(hs), hook["rows"]
        im = np.asarray(Image.open(r["png"]).convert("RGB").resize((320, 180)), np.float64)
        # persone e plate grigie: la croma resta solo negli elementi d'accento
        sat = (im.max(-1) - im.min(-1))
        assert float((sat > 40).mean()) < 0.35, float((sat > 40).mean())


def test_render_v2_scena_popout_from_source_video():
    """scena: il frame della sorgente (video sintetico) allineato sotto il ritaglio (pop-out), scurito e sfocato."""
    if not _playwright_ready():
        return
    fx_ = fixtures()
    if not fx_["video"]:
        print("   (saltato: ffmpeg-full non trovato)")
        return
    F = fx_["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "s", "template": "scena", "hook": "Il cliente mi ha salvato", "keyword": "cliente", "payoff_at": 410.0,
             "people": [{"cutout": str(F / "ospite.png"), **GUEST}], "plate": {"source": "scene"}, "format_label": "IL CAFFÈ DEI MAKER"}
        code, res = _render([c], out)
        r = res["outputs"]["renders"][0]
        assert r["ok"], r.get("error")
        assert r["v2"]["scene"] and r["v2"]["scene"]["roi"] == [0, 0, 3840, 2160], r["v2"]
        kinds = {u["kind"] for u in r["metrics"]["series"]["under"]}
        assert {"scene", "scene-backdrop"} <= kinds and r["metrics"]["series"]["field"] == "scene-popout", kinds
        assert r["checks_v2"]["heroes"][0]["face_pixels_unchanged"]["changed_gt1"] == 0
        # accento di default del brand con contrasto < 7:1 → targhetta su carta
        assert r["checks_v2"]["credentials"][0]["box"] == "paper", r["checks_v2"]["credentials"]
        assert r["pass"], r["errors"]


def test_render_v2_prova_needs_source():
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        base = {"template": "prova", "hook": "Ho rifatto tutto da zero", "keyword": "zero", "accent": "accent_3", "payoff_at": 520.0,
                "artifact": str(F / "schermata.png"), "people": [{"cutout": str(F / "ospite_prova.png"), **GUEST}]}
        code, res = _render([{**base, "id": "p1", "artifact_source": "schermata finta del test"}, {**base, "id": "p2"}], out)
        r1, r2 = res["outputs"]["renders"]
        assert r1["ok"] and r1["pass"], r1.get("errors")
        assert r1["metrics"]["series"]["artifact_mode"] == "card" and r1["checks_v2"]["accents"] == ["accent_3"]
        assert not r2["pass"] and any("artifact_source" in e for e in r2["errors"]), r2["errors"]
        assert code == 3


def test_render_generic_and_brand_template_override():
    """generic (campo pieno) e un template di un brand esterno (<slug>-ritratto) che sostituisce quello incluso."""
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bd = td / "brands" / "acme"
        (bd / "templates").mkdir(parents=True)
        tok = json.loads(json.dumps(TOKENS))
        tok.update({"slug": "acme", "name": "Acme Esempio", "wordmark": {"text": "Acme Esempio"}, "logo": {}})
        tok["colors"].update({"accent": "#2f6bff"})
        (bd / "tokens.json").write_text(json.dumps(tok))
        # copia del template incluso nella cartella del brand (come da 07 §8): window.KIT arriva da render_html.mjs
        src = (tr.TEMPLATES_DIR / "ritratto.html").read_text().replace("KIT.finish('ritratto'", "KIT.finish('acme-ritratto'")
        (bd / "templates" / "acme-ritratto.html").write_text(src)
        out = td / "out"
        out.mkdir()
        cs = [{"id": "g", "template": "generic", "text": "Ho cambiato mestiere", "cutout": str(F / "ospite_duo.png"), "face_frac": 0.30},
              {"id": "o", "template": "ritratto", "brand": "acme", "hook": "Ho chiuso il negozio", "keyword": "negozio", "payoff_at": 1.0,
               "show_logo": "symbol", "show_episode": True, "episode": "EP 12",       # brand senza file del simbolo
               "people": [{"cutout": str(F / "ospite.png"), **GUEST}]}]
        code, res = _render(cs, out, env=_env(YT_BRANDS_DIRS=str(td / "brands")))
        g, o = res["outputs"]["renders"]
        assert g["ok"] and g["color_pairs"][0]["pair"] == "fg-on-bg", g
        hook = next(t for t in g["metrics"]["texts"] if t["kind"] == "hook")
        assert hook["font"] == "Anton" and hook["fonts_ok"], hook
        assert o["ok"] and o["brand"] == "acme" and o["metrics"]["series"]["template"] == "acme-ritratto", (o.get("brand"), o.get("error"))
        assert o["metrics"]["series"]["wordmark"]["text"] == "Acme Esempio" and o["palette"]["accents"]["accent"] == "#2f6bff"
        # senza simbolo il logo ricade sul wordmark e il numero di episodio resta (non sparisce in silenzio)
        assert any(t["kind"] == "badge" and "EP 12" in t["text"] for t in o["metrics"]["texts"]), o["metrics"]["texts"]


def test_render_defaults_from_channel_profile():
    """Default dal profilo del canale (blocco thumbnails): template, grade, accenti ammessi, etichetta e logo; il canale
    viene dal project.json del workdir che contiene concepts.json; senza brand del canale si usa il brand demo."""
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "channels").mkdir()
        (td / "channels" / "canale-esempio.md").write_text(
            "---\nslug: canale-esempio\nkind: personal\nname: \"Canale Esempio\"\nthumbnails:\n  default_template: ritratto\n"
            "  grade_default: mono\n  accent: auto\n  accents: [accent_2]\n  format_label: \"IL CAFFÈ DEI MAKER\"\n"
            "  show_logo: symbol\n  host_tag: \"con [Nome dell'host]\"\n  guest_style_allowed: [none]\n---\n\nProfilo di prova.\n")
        wd = td / "work" / "canale-esempio" / "2026-03-02-puntata"
        (wd / "thumbs").mkdir(parents=True)
        (wd / "project.json").write_text(json.dumps({"channel": "canale-esempio"}))
        concepts = [{"id": "p", "hook": "Ho chiuso il primo negozio", "keyword": "negozio", "payoff_at": 1.0, "face_floor_reason": "test",
                     "people": [{"cutout": str(F / "ospite.png"), **GUEST}]},
                    {"id": "x", "hook": "Ho chiuso il primo negozio", "keyword": "negozio", "payoff_at": 1.0, "guest_style": "graphic",
                     "people": [{"cutout": str(F / "ospite.png"), **GUEST}]}]
        data = wd / "thumbs" / "concepts.json"
        data.write_text(json.dumps(concepts, ensure_ascii=False))
        p = subprocess.run([str(BIN / "yt-thumb-render"), "--data", str(data), "--out", str(wd / "thumbs" / "renders")], capture_output=True,
                           text=True, env=_env(YT_CHANNELS_DIRS=str(td / "channels"), YT_MP_MODEL=str(td / "nessun-modello.task")))
        res = json.loads(p.stdout)
        r, x = res["outputs"]["renders"]
        assert r["ok"] and r["template"] == "ritratto" and r["channel"] == "canale-esempio" and r["brand"] == "demo", (r.get("error"), r.get("template"))
        assert r["checks_v2"]["grade"]["mode"] == "mono" and r["checks_v2"]["accents"] == ["accent_2"], (r["checks_v2"]["grade"], r["checks_v2"]["accents"])
        s = r["metrics"]["series"]
        assert s["logos"] and not s["logos"][0]["wordmark"] and "label" in s, s.get("logos")
        assert any(t["kind"] == "label" and "CAFF" in t["text"].upper() for t in r["metrics"]["texts"]), r["metrics"]["texts"]
        assert any("guest_style «graphic» non ammesso" in e for e in x["errors"]), x["errors"]


def test_render_face_pixels_check_catches_overlay():
    """Controllo negativo: un velo messo SOPRA il volto (strato tt-under a z 30) deve far fallire face_pixels_unchanged."""
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    tpl_dir = tr.TEMPLATES_DIR
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        s = (tpl_dir / "ritratto.html").read_text()
        inj = ("  { const f = rec.faceRect; const v = T.el('div', 'tt-under', frame); Object.assign(v.style, { position: 'absolute', "
               "left: f.x + 'px', top: f.y + 'px', width: f.w + 'px', height: f.h + 'px', background: 'rgba(53,212,154,.2)', zIndex: 30 }); }\n")
        anchor = "  const logo = KIT.frameLogo(frame, spec"
        assert anchor in s
        (td / "ritratto.html").write_text(s.replace(anchor, inj + anchor, 1))
        cut = F / "ospite.png"
        hero = {"src": cut.as_uri(), "path": str(cut), **tr.cutout_meta(cut, cache_dir=td), **GUEST}
        spec = {"hook": "Lo provammo con una lista", "text": "Lo provammo con una lista", "highlight": "lista", "accent": "accent",
                "people": [hero], "hero": hero, "display_cap": 2.0}
        job = {"viewport": {"w": 1280, "h": 720}, "scale": 3, "fonts": tr.font_list({}),
               "jobs": [{"id": "neg", "template": str(td / "ritratto.html"), "spec": spec, "tokens": TOKENS, "out": str(td / "neg.png"),
                         "brand": "demo", "brand_dir": str(BRAND_DIR), "fx_check": True}]}
        (td / "job.json").write_text(json.dumps(job))
        env = {**os.environ, "YT_NODE_PREFIX": str(tr.yc.NODE_PREFIX)}
        p = subprocess.run([tr.NODE, str(tr.RENDER_JS), str(td / "job.json")], capture_output=True, text=True, env=env)
        res = json.loads(p.stdout)["results"][0]
        assert res["ok"], res
        entry = {"errors": [], "warnings": []}
        tr.post_render_v2({"spec": spec, "template": "ritratto", "png": str(td / "neg.png"), "tokens": TOKENS}, entry, res["metrics"], res["fx"])
        cp = entry["checks_v2"]["heroes"][0]["face_pixels_unchanged"]
        assert cp["changed_gt1"] > 1000 and any("face_pixels_unchanged" in e for e in entry["errors"]), cp


def test_render_then_qa_end_to_end():
    """Il sidecar di yt-thumb-render basta a yt-thumb-qa: volti, righe, grade e accenti dalla palette del brand."""
    if not _playwright_ready():
        return
    F = fixtures()["dir"]
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        c = {"id": "q", "template": "ritratto", "hook": "Ho chiuso il primo negozio", "keyword": "negozio", "disc": "paper", "payoff_at": 300.0,
             "people": [{"cutout": str(F / "ospite.png"), **GUEST}], "meta_line": "PUNTATA 12 / 2026"}
        code, res = _render([c], out)
        r = res["outputs"]["renders"][0]
        assert r["ok"], r.get("error")
        p = subprocess.run([str(BIN / "yt-thumb-qa"), r["png"], "--out", str(out / "qa"), "--no-vision"], capture_output=True, text=True)
        qa = json.loads(p.stdout)
        img = qa["outputs"]["images"][0]
        by = {x["id"]: x for x in img["checks"]}
        assert img["gated"] and by["face_size"]["level"] in ("pass", "warn") and by["hook_words"]["level"] == "pass", by
        assert by["render_checks"]["level"] == ("pass" if r["pass"] else "error"), by["render_checks"]
        assert Path(img["sheet"]).exists()


# ── runner ──────────────────────────────────────────────────────────────────
def main() -> int:
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f) and flt in n]
    fails = 0
    t0 = time.time()
    for n, f in tests:
        t1 = time.time()
        try:
            f()
            print(f"ok   {n} ({time.time() - t1:.1f} s)")
        except Exception:  # noqa: BLE001
            fails += 1
            print(f"FAIL {n}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails}/{len(tests)} ok in {time.time() - t0:.1f} s")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
