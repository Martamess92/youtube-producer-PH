#!/usr/bin/env python3
"""Costruisce il kit di pre-test delle thumbnail da una configurazione JSON.

Uso:
    python3 build_kit.py --config <cartella-test>/pretest.config.json [--out <cartella-test>]

Scrive, dentro --out (default: la cartella della configurazione):
    site/index.html       pagina autonoma con il feed a tempo (opzione (a): vicini veri)
    site/robots.txt
    site-h2h/index.html   stessa pagina senza feed né immagini di terzi (opzione (b))
    site-h2h/robots.txt
    pickfu/opzione-N.jpg  le copertine a 1280×720 per PickFu, con nomi neutri
    pickfu/chiave.json    quale braccio è ogni opzione (NON va caricato su PickFu)
    build.json            riepilogo: id di build, braccia, vicini, dimensioni

Nessuna rete, nessun caricamento: tutto resta in locale. Le immagini vengono ridotte a
720×405 (la misura servita da YouTube) e incorporate come data URI. Serve Pillow; in
mancanza, su macOS si usa `sips`.

Il modello HTML è `feed-test.template.html`, nella stessa cartella di questo script.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT_VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "feed-test.template.html"
PLACEHOLDER = "/*__KIT__*/null"
ROBOTS = "User-agent: *\nDisallow: /\n"

DEFAULTS = {
    "feed": {"enabled": True, "exposure_ms": 3000, "fixation_ms": 800, "tile_max_px": 360,
             "tile_min_px": 220, "themes": ["dark", "light"]},
    "promise": {"exposure_ms": 3000, "tile_px": 360},
    "h2h": {"tile_px": 360, "title": None},
    "image": {"width": 720, "height": 405, "quality": 82},
    "min_viewport": {"w": 1000, "h": 620},
    "sink": {"type": "google_form", "form_action": "", "fields": {"record": "", "pid": "", "arm": ""}},
    "prolific": {"completion_url": ""},
}


class KitError(Exception):
    pass


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def resolve(p: str, root: Path) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else (root / path)


def load_config(path: Path) -> dict:
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise KitError(f"configurazione illeggibile: {path}: {e}") from e
    for k, v in DEFAULTS.items():
        cfg[k] = merge(v, cfg.get(k) or {}) if isinstance(v, dict) else cfg.get(k, v)
    validate(cfg, path.parent)
    return cfg


def validate(cfg: dict, root: Path) -> None:
    errs = []
    sid = cfg.get("study_id", "")
    if not sid or not all(c.isalnum() or c in "-_." for c in sid):
        errs.append("study_id mancante o con caratteri non ammessi (solo lettere, cifre, - _ .)")
    arms = cfg.get("arms") or []
    ids = [a.get("id") for a in arms]
    if len(arms) < 2:
        errs.append("servono almeno 2 braccia in arms")
    if len(set(ids)) != len(ids) or not all(ids):
        errs.append("gli id delle braccia devono essere unici e non vuoti")
    if sum(1 for a in arms if a.get("role") == "control") != 1:
        errs.append("serve esattamente un braccio con role \"control\"")
    for a in arms:
        if not a.get("file") or not resolve(a["file"], root).is_file():
            errs.append(f"braccio {a.get('id')}: file assente {a.get('file')}")
    pairs = cfg.get("pairs") or []
    if not pairs:
        errs.append("pairs vuoto: serve almeno una coppia per il testa a testa")
    seen = set()
    for p in pairs:
        if len(p) != 2 or p[0] == p[1] or p[0] not in ids or p[1] not in ids:
            errs.append(f"coppia non valida: {p}")
        key = frozenset(p)
        if key in seen:
            errs.append(f"coppia ripetuta: {p}")
        seen.add(key)
    for p in cfg.get("primary_pairs") or []:
        if frozenset(p) not in seen:
            errs.append(f"primary_pairs: la coppia {p} non è in pairs")
    neigh = cfg.get("neighbours") or []
    if cfg["feed"].get("enabled"):
        if len(neigh) != 8:
            errs.append(f"il feed vuole esattamente 8 vicini (ne hai {len(neigh)})")
        nids = [n.get("id") for n in neigh]
        if len(set(nids)) != len(nids) or set(nids) & set(ids):
            errs.append("gli id dei vicini devono essere unici e diversi da quelli delle braccia")
        for n in neigh:
            if not n.get("file") or not resolve(n["file"], root).is_file():
                errs.append(f"vicino {n.get('id')}: file assente {n.get('file')}")
    url = cfg["prolific"].get("completion_url") or ""
    if url and not url.startswith("https://app.prolific.com/"):
        errs.append("prolific.completion_url deve iniziare con https://app.prolific.com/")
    if errs:
        raise KitError("configurazione non valida:\n  - " + "\n  - ".join(errs))


def to_jpeg(src: Path, w: int, h: int, quality: int) -> bytes:
    """Ritaglio centrale a 16:9 e riduzione a w×h, sRGB, JPEG."""
    try:
        from PIL import Image, ImageOps  # type: ignore
    except ImportError:
        return to_jpeg_sips(src, w, h, quality)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB",):
            bg = Image.new("RGB", im.size, (0, 0, 0))
            rgba = im.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        im = ImageOps.fit(im, (w, h), method=Image.LANCZOS, centering=(0.5, 0.5))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        return buf.getvalue()


def to_jpeg_sips(src: Path, w: int, h: int, quality: int) -> bytes:
    if not shutil.which("sips"):
        raise KitError("serve Pillow (pip install pillow) oppure sips (macOS)")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.jpg"
        cmd = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality),
               "-z", str(h), str(w), str(src), "--out", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise KitError(f"sips non è riuscito su {src}: {r.stderr.strip()}")
        return out.read_bytes()


def data_uri(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def page(template: str, kit: dict) -> str:
    if PLACEHOLDER not in template:
        raise KitError("segnaposto KIT assente nel modello HTML")
    payload = json.dumps(kit, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, payload, 1)


def build(cfg_path: Path, out: Path) -> dict:
    cfg = load_config(cfg_path)
    root = cfg_path.parent
    template = TEMPLATE.read_text(encoding="utf-8")
    im = cfg["image"]
    images, digest = {}, hashlib.sha256(template.encode("utf-8"))
    for a in cfg["arms"]:
        b = to_jpeg(resolve(a["file"], root), im["width"], im["height"], im["quality"])
        images[a["id"]] = data_uri(b)
        digest.update(a["id"].encode() + b)
    neigh_images = {}
    if cfg["feed"].get("enabled"):
        for n in cfg["neighbours"]:
            b = to_jpeg(resolve(n["file"], root), im["width"], im["height"], im["quality"])
            neigh_images[n["id"]] = data_uri(b)
            digest.update(n["id"].encode() + b)
    digest.update(json.dumps({k: cfg[k] for k in ("feed", "promise", "h2h", "pairs")}, sort_keys=True).encode())
    build_id = digest.hexdigest()[:12]

    base = {
        "kit_version": KIT_VERSION, "study_id": cfg["study_id"], "build_id": build_id,
        "show_name": cfg.get("show_name", ""), "topic": cfg.get("topic", ""),
        "arms": [{"id": a["id"]} for a in cfg["arms"]],   # niente etichette né percorsi nella pagina
        "pairs": cfg["pairs"],
        "promise": cfg["promise"], "h2h": cfg["h2h"], "min_viewport": cfg["min_viewport"],
        "sink": cfg["sink"], "prolific": cfg["prolific"],
    }
    outputs = {}
    variants = [("site", True), ("site-h2h", False)] if cfg["feed"].get("enabled") else [("site-h2h", False)]
    for folder, with_feed in variants:
        kit = dict(base)
        kit["feed"] = dict(cfg["feed"], enabled=with_feed)
        kit["neighbours"] = [{"id": n["id"]} for n in cfg["neighbours"]] if with_feed else []
        kit["images"] = dict(images, **(neigh_images if with_feed else {}))
        d = out / folder
        d.mkdir(parents=True, exist_ok=True)
        html = page(template, kit)
        (d / "index.html").write_text(html, encoding="utf-8")
        (d / "robots.txt").write_text(ROBOTS, encoding="utf-8")
        outputs[folder] = {"path": str(d / "index.html"), "bytes": len(html.encode("utf-8"))}

    # PickFu: copertine a 1280×720, nomi neutri, chiave a parte
    pf = out / "pickfu"
    pf.mkdir(parents=True, exist_ok=True)
    key = {}
    for i, a in enumerate(cfg["arms"], start=1):
        b = to_jpeg(resolve(a["file"], root), 1280, 720, 88)
        name = f"opzione-{i}.jpg"
        (pf / name).write_bytes(b)
        key[name] = {"arm": a["id"], "role": a.get("role", ""), "label": a.get("label", "")}
    (pf / "chiave.json").write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "kit_version": KIT_VERSION, "study_id": cfg["study_id"], "build_id": build_id,
        "arms": [{k: a.get(k) for k in ("id", "role", "label", "file")} for a in cfg["arms"]],
        "pairs": cfg["pairs"], "primary_pairs": cfg.get("primary_pairs") or [],
        "neighbours": [{k: n.get(k) for k in ("id", "label", "file")} for n in cfg.get("neighbours") or []],
        "sink_configured": bool(cfg["sink"].get("form_action")) and bool(cfg["sink"]["fields"].get("record")),
        "completion_url_configured": bool(cfg["prolific"].get("completion_url")),
        "outputs": outputs, "pickfu": key,
    }
    (out / "build.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="pretest.config.json del test")
    ap.add_argument("--out", help="cartella di uscita (default: quella della configurazione)")
    args = ap.parse_args(argv)
    cfg_path = Path(args.config).expanduser().resolve()
    out = Path(args.out).expanduser().resolve() if args.out else cfg_path.parent
    try:
        s = build(cfg_path, out)
    except KitError as e:
        print(f"[pretest-kit] errore: {e}", file=sys.stderr)
        return 2
    for name, o in s["outputs"].items():
        print(f"[pretest-kit] {name}/index.html  {o['bytes'] / 1e6:.2f} MB")
    print(f"[pretest-kit] build {s['build_id']} · braccia {', '.join(a['id'] for a in s['arms'])} · "
          f"raccolta dati {'configurata' if s['sink_configured'] else 'NON configurata (anteprima)'} · "
          f"link di completamento Prolific {'presente' if s['completion_url_configured'] else 'assente'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
