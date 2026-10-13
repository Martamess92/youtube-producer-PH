"""yt-remotion — render dei template brand Remotion (stile guidato dai token del brand attivo; default il brand
neutro demo): overlay alpha, sting, Shorts, thumbnail.

Uso:
  yt-remotion render COMPOSIZIONE --props FILE --out FILE [--codec prores|h264] [--scale N]
                     [--frames a-b] [--concurrency N] [--browser managed|system] [--force]
  yt-remotion still  COMPOSIZIONE --props FILE --out PNG [--scale 3] [--frame N] [--force]
  yt-remotion list

Composizioni: LowerThird, ChapterCard, ColdOpenTitle, IntroSting, EndPlate (video 16:9, 4k|1080p),
ShortCaptions (1080×1920), ThumbnailStill (still 1280×720 → --scale 3 = 3840×2160).

Il file --props è un JSON con le props della composizione. Il wrapper:
  - risolve `brand` (default: demo) e inietta `tokens` dal tokens.json del brand: prima <brands_dir>/<slug>/
    (brand dell'operatore, vedi yt-config), poi assets/brands/<slug>/ del plugin (solo demo). Lo stile segue i
    token del brand ed è guidato da `style` = <brand>/remotion.json (+ eventuale `style` nel file props):
    font del brand (fonts[].file relativo alla cartella del brand: collegati nella public dir come brand/…),
    motivo (plain | terminal), firma, prefissi, griglia, raggio, evidenziazione — vedi remotion/README.md;
  - collega i media locali (videoSrc, cutoutSrc, bgImageSrc: path assoluti o relativi al file
    props) in una public dir temporanea con symlink (niente copie dei file grandi);
  - `captionsFile` (Caption[] Remotion, transcript.words.json, {captions|words: …} o .srt) →
    `captions`, con `captionsOffsetSeconds` per clip tagliate da un sorgente più lungo;
  - ShortCaptions: durata e fps letti dal video se assenti; ThumbnailStill: dimensioni, bbox alpha
    e volto (thumbvision, se presente) dello scontorno.
Codec: .mov → ProRes 4444 con alpha (yuva444p10le, frame PNG) · .mp4 → H.264 (CRF 18, AAC).
Browser: di default chrome-headless-shell gestito da Remotion (scaricato una volta in
node_modules/.remotion della data dir del plugin, ~171 MB); `--browser system` usa Google Chrome di sistema
(più lento). I sorgenti stanno nel plugin (scripts/yt/remotion) e a ogni render vengono sincronizzati nella copia
della data dir dove /youtube:setup ha installato i node_modules (se il package-lock cambia: rilancia /youtube:setup).
Nessuna chiave licenza passata a Remotion → nessun evento d'uso inviato. Licenza: vedi
docs/yt/vendor/REMOTION_LICENSE_NOTE.md del plugin: Remotion è gratuito per singoli e organizzazioni fino a 3
persone, oltre serve una licenza Company; per i clienti solo file finiti oppure HyperFrames (Apache-2.0).
Qui vale per i brand propri: demo, i brand con "own": true nei token, i canali kind: own o personal.
stdout = un solo JSON di riepilogo; log di Remotion su stderr.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore  # noqa: E402

REMOTION_DIR = ytcore.REMOTION_DIR      # progetto eseguibile: copia sincronizzata nella data dir del plugin + node_modules
REMOTION_SRC = ytcore.REMOTION_SRC      # sorgenti nel plugin (scripts/yt/remotion)
REMOTION_BIN = REMOTION_DIR / "node_modules" / ".bin" / "remotion"
ENTRY = "src/index.ts"
FONTS_DIR = REMOTION_SRC / "public" / "fonts"
HEADLESS_DIR = REMOTION_DIR / "node_modules" / ".remotion" / "chrome-headless-shell"
TMP_ROOT = ytcore.CACHE / "remotion"

# kind: video | still · alpha: overlay con trasparenza attesa · default: estensione consigliata
COMPOSITIONS = {
    "LowerThird": {"kind": "video", "alpha": True, "ext": ".mov", "desc": "nome + ruolo, trasparente, 5 s"},
    "ChapterCard": {"kind": "video", "alpha": None, "ext": ".mov", "desc": "numero + titolo capitolo, 3 s (mode full|overlay)"},
    "ColdOpenTitle": {"kind": "video", "alpha": None, "ext": ".mov", "desc": "frase gancio ≤3 s (background transparent = overlay)"},
    "IntroSting": {"kind": "video", "alpha": False, "ext": ".mov", "desc": "sigla ≤3 s"},
    "EndPlate": {"kind": "video", "alpha": False, "ext": ".mov", "desc": "end screen 20 s, 2 slot video + iscrizione"},
    "ShortCaptions": {"kind": "video", "alpha": False, "ext": ".mp4", "desc": "Short 1080×1920 con sottotitoli TikTok-style"},
    "ThumbnailStill": {"kind": "still", "alpha": False, "ext": ".png", "desc": "thumbnail 1280×720 (scale 3 → 4K)"},
}
# Campi di contenuto obbligatori nel file props (gli altri hanno default nella Root)
REQUIRED = {"LowerThird": ("name",), "ChapterCard": ("number", "title"), "ColdOpenTitle": ("hook",),
            "ThumbnailStill": ("text",)}
MEDIA_KEYS = ("videoSrc", "cutoutSrc", "bgImageSrc")
PROGRESS_RE = re.compile(r"^(Rendered|Encoded|Stitched|Bundling|Getting|Downloading|Copying)\b.*\d+")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# ── Utilità ─────────────────────────────────────────────────────────────────
def _resolve_media(value: str, base: Path) -> Path:
    """Path reale del media (segue i symlink: i src/ delle cartelle di lavoro puntano agli originali)."""
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def _newest_mtime(paths) -> float:
    newest = 0.0
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    newest = max(newest, f.stat().st_mtime)
        elif p.exists():
            newest = max(newest, p.stat().st_mtime)
    return newest


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _cleanup(tmp: Path) -> None:
    """Rimuove la cartella temporanea: solo symlink e file nostri, mai i target dei link."""
    if not tmp.exists():
        return
    for root, dirs, files in os.walk(tmp, topdown=False):
        for name in files + dirs:
            p = Path(root) / name
            if p.is_symlink() or p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
    tmp.rmdir()


# ── Sottotitoli ─────────────────────────────────────────────────────────────
def _srt_to_words(text: str) -> list[dict]:
    """SRT a segmenti → parole con tempi distribuiti in proporzione ai caratteri (fallback)."""
    words: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for b in blocks:
        lines = [l for l in b.strip().splitlines() if l.strip()]
        m = next((re.match(r"(\S+)\s*-->\s*(\S+)", l) for l in lines if "-->" in l), None)
        if not m:
            continue
        start, end = ytcore.parse_ts(m.group(1)), ytcore.parse_ts(m.group(2))
        body = " ".join(l for l in lines if "-->" not in l and not l.strip().isdigit())
        toks = body.split()
        total = sum(len(t) + 1 for t in toks) or 1
        t = start
        for tok in toks:
            dur = (end - start) * (len(tok) + 1) / total
            words.append({"w": tok, "start": t, "end": t + dur})
            t += dur
    return words


def load_captions(path: Path, offset: float = 0.0, duration: float | None = None) -> tuple[list[dict], str]:
    """Qualsiasi formato supportato → Caption[] Remotion (text con spazio iniziale tra parole)."""
    if path.suffix.lower() == ".srt":
        words, src = _srt_to_words(path.read_text(encoding="utf-8", errors="replace")), "srt (tempi stimati)"
    else:
        data = ytcore.read_json(path)
        if isinstance(data, dict):
            data = data.get("captions") or data.get("words") or []
        words, src = [], "json"
        for item in data:
            if "startMs" in item:  # già Caption Remotion
                words.append({"w": item["text"], "start": item["startMs"] / 1000, "end": item["endMs"] / 1000,
                              "p": item.get("confidence"), "raw": True})
            else:
                w = item.get("w", item.get("word", item.get("text", "")))
                words.append({"w": w, "start": float(item["start"]), "end": float(item["end"]), "p": item.get("p")})
        src = "caption" if words and words[0].get("raw") else "words"
    caps: list[dict] = []
    for item in words:
        start, end = item["start"] - offset, item["end"] - offset
        if end <= 0 or (duration is not None and start >= duration):
            continue
        start, end = max(0.0, start), min(end, duration) if duration else end
        text = item["w"] if item.get("raw") else str(item["w"]).strip()
        if not text.strip():
            continue
        if not item.get("raw"):
            text = text if not caps else " " + text
        caps.append({"text": text, "startMs": round(start * 1000), "endMs": round(max(end, start + 0.05) * 1000),
                     "timestampMs": round(start * 1000), "confidence": item.get("p")})
    if caps and caps[0]["text"].startswith(" "):
        caps[0]["text"] = caps[0]["text"].lstrip()
    return caps, src


# ── Analisi media ───────────────────────────────────────────────────────────
def _video_meta(path: Path) -> dict:
    info = ytcore.ffprobe(path)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    return {"duration": float(info["format"]["duration"]), "fps": round(fps, 3), "w": v.get("width"), "h": v.get("height"),
            "audio": any(s.get("codec_type") == "audio" for s in info["streams"])}


def _cutout_meta(path: Path, warnings: list) -> dict:
    from PIL import Image

    with Image.open(path) as im:
        size = im.size
        bbox = None
        if im.mode in ("RGBA", "LA") or "transparency" in im.info:
            alpha = im.convert("RGBA").getchannel("A").point(lambda a: 255 if a > 24 else 0)
            bbox = alpha.getbbox()
        else:
            warnings.append(f"{path.name}: PNG senza alpha — non è uno scontorno")
    out = {"cutoutSize": list(size)}
    if bbox:
        w, h = size
        out["cutoutBBox"] = [round(bbox[0] / w, 4), round(bbox[1] / h, 4), round((bbox[2] - bbox[0]) / w, 4), round((bbox[3] - bbox[1]) / h, 4)]
    return out


def _face_box(path: Path, warnings: list) -> list | None:
    """Volto più grande via thumbvision (contratto §8.3: box normalizzati, origine in alto a sinistra)."""
    if not ytcore.SWIFT_BIN.exists():
        warnings.append("thumbvision assente: posizionamento dell'ospite dal bbox (passa faceBox per precisione)")
        return None
    try:
        proc = subprocess.run([str(ytcore.SWIFT_BIN), "score", str(path)], capture_output=True, text=True, timeout=120)
        out = proc.stdout.strip()
        try:
            data = json.loads(out)
        except json.JSONDecodeError:  # una riga JSON per immagine (prototipo)
            data = json.loads(out.splitlines()[0])
        item = data[0] if isinstance(data, list) else data
        boxes = []
        for f in item.get("faces") or []:
            if "box" in f:  # contratto §8.3: origine in alto a sinistra
                boxes.append([float(x) for x in f["box"]])
            elif "bbox" in f:  # Vision grezzo: origine in basso a sinistra
                x, y, w, h = (float(v) for v in f["bbox"])
                boxes.append([x, 1 - y - h, w, h])
        if not boxes:
            warnings.append("thumbvision: nessun volto nello scontorno")
            return None
        best = max(boxes, key=lambda b: b[2] * b[3])
        return [round(v, 4) for v in best]
    except Exception as exc:  # noqa: BLE001 — il volto è un'ottimizzazione, non un requisito
        warnings.append(f"thumbvision fallito ({exc.__class__.__name__}): uso il bbox")
        return None


# ── Preparazione props + public dir ─────────────────────────────────────────
def _brand_style(brand: str, bdir: Path, extra: dict | None, public: Path, inputs: list[Path], warnings: list) -> dict:
    """Stile del brand per le composizioni generiche: <brand>/remotion.json + `style` del file props.
    I file citati (fonts[].file, logo) sono relativi alla cartella del brand: la loro sottocartella viene
    collegata nella public dir temporanea come brand/<sottocartella> (symlink di cartella: il server statico
    di Remotion li segue) e il percorso riscritto per staticFile()."""
    rj = bdir / "remotion.json"
    style = ytcore.read_json(rj) if rj.is_file() else {}
    if rj.is_file():
        inputs.append(rj)
    style = _deep_merge(style if isinstance(style, dict) else {}, extra if isinstance(extra, dict) else {})
    if not style:
        return {}
    linked: dict[str, str] = {}

    def link(rel: str) -> str | None:
        rel = str(rel).lstrip("/")
        src = (bdir / rel).resolve()
        try:
            src.relative_to(bdir.resolve())
        except ValueError:
            warnings.append(f"remotion.json: {rel} fuori dalla cartella del brand, ignorato")
            return None
        if not src.is_file():
            warnings.append(f"remotion.json: file non trovato nella cartella del brand: {rel}")
            return None
        sub = src.parent
        key = str(sub)
        if key not in linked:
            name = f"d{len(linked)}"
            (public / "brand").mkdir(exist_ok=True)
            (public / "brand" / name).symlink_to(sub, target_is_directory=True)
            linked[key] = f"brand/{name}"
            inputs.append(sub)
        return f"{linked[key]}/{src.name}"

    fonts = []
    for f in style.get("fonts") or []:
        if not isinstance(f, dict) or not f.get("family") or not f.get("file"):
            continue
        url = link(f["file"])
        if url:
            fonts.append({**f, "file": url})
    style["fonts"] = fonts
    if style.get("logo"):
        style["logo"] = link(style["logo"])
    return style


def prepare(comp: str, props_file: Path, tmp: Path, warnings: list) -> tuple[dict, list[Path]]:
    props = ytcore.read_json(props_file)
    if not isinstance(props, dict):
        raise ValueError("--props deve contenere un oggetto JSON")
    missing = [k for k in REQUIRED.get(comp, ()) if props.get(k) in (None, "")]
    if missing:
        raise ValueError(f"{comp}: mancano nel file props: {', '.join(missing)}")
    base = props_file.parent
    brand = props.get("brand") or ytcore.BUILTIN_BRAND
    props["brand"] = brand
    bdir = ytcore.brand_dir(brand)
    tokens = ytcore.brand_tokens(brand)
    if not tokens or bdir is None:
        where = ", ".join(str(d / brand) for d in ytcore.BRANDS_DIRS)
        raise FileNotFoundError(f"Token del brand '{brand}' mancanti (cercati: {where}; tokens.json)")
    props["tokens"] = _deep_merge(tokens, props.get("tokens") or {})
    channel = props.get("channel") or ytcore.channel_of_path(props_file)
    if not ytcore.remotion_allowed(brand, channel):
        who = (f"il canale '{channel}' è un cliente" if channel and ytcore.own_brand(brand)
               else f"brand '{brand}' non è un brand proprio")
        warnings.append(f"{who}: con Remotion consegna al cliente solo file finiti, "
                        "per progetti consegnati usa HyperFrames (licenza Remotion, design §11)")

    public = tmp / "public"
    (public / "media").mkdir(parents=True, exist_ok=True)
    (public / "fonts").symlink_to(FONTS_DIR, target_is_directory=True)
    inputs: list[Path] = [props_file, bdir / "tokens.json"]
    style = _brand_style(brand, bdir, props.get("style"), public, inputs, warnings)
    if style:
        props["style"] = style
    else:
        props.pop("style", None)

    for i, key in enumerate(MEDIA_KEYS):
        val = props.get(key)
        if not val or re.match(r"^(https?:|data:)", str(val)):
            continue
        src = _resolve_media(str(val), base)
        if not src.exists():
            raise FileNotFoundError(f"{key}: file non trovato: {src}")
        # Il server statico di Remotion rifiuta i file-symlink (404) ma segue le cartelle-symlink:
        # colleghiamo la cartella del media e referenziamo il file dentro (staticFile codifica il nome).
        (public / "media" / str(i)).symlink_to(src.parent, target_is_directory=True)
        props[key] = f"media/{i}/{src.name}"
        inputs.append(src)
        if key == "videoSrc":
            meta = _video_meta(src)
            start = float(props.get("videoStartSeconds") or 0)
            props.setdefault("durationInSeconds", round(max(0.1, meta["duration"] - start), 3))
            props.setdefault("fps", meta["fps"])
            if meta["w"] and meta["h"] and abs(meta["w"] / meta["h"] - 9 / 16) > 0.02:
                warnings.append(f"videoSrc {meta['w']}×{meta['h']} non è 9:16: verrà ritagliato ({props.get('videoFit', 'cover')})")
        if key == "cutoutSrc":
            for k, v in _cutout_meta(src, warnings).items():
                props.setdefault(k, v)
            if "faceBox" not in props:
                fb = _face_box(src, warnings)
                if fb:
                    props["faceBox"] = fb

    cap_file = props.pop("captionsFile", None)
    if isinstance(props.get("captions"), str):
        cap_file = props.pop("captions")
    if cap_file:
        cpath = _resolve_media(cap_file, base)
        if not cpath.exists():
            raise FileNotFoundError(f"captionsFile non trovato: {cpath}")
        caps, kind = load_captions(cpath, float(props.pop("captionsOffsetSeconds", 0) or 0), props.get("durationInSeconds"))
        props["captions"] = caps
        inputs.append(cpath)
        if kind.startswith("srt"):
            warnings.append("sottotitoli da SRT a segmenti: tempi per parola stimati (usa transcript.words.json)")
        if not caps:
            warnings.append("nessuna parola dei sottotitoli cade nella durata del video (controlla captionsOffsetSeconds)")
    props.pop("captionsOffsetSeconds", None)

    if comp == "ShortCaptions" and "durationInSeconds" not in props:
        caps = props.get("captions") or []
        if not caps:
            raise ValueError("ShortCaptions: servono videoSrc oppure durationInSeconds")
        props["durationInSeconds"] = round(caps[-1]["endMs"] / 1000 + 0.5, 3)
    if comp == "ThumbnailStill":
        words = [w for w in re.split(r"\s+", str(props.get("text", "")).strip()) if w]
        if len(words) > 4:
            warnings.append(f"testo thumbnail di {len(words)} parole (regola: ≤4)")
    return props, inputs


# ── Render ──────────────────────────────────────────────────────────────────
def _browser_args(mode: str) -> tuple[list[str], str]:
    if mode == "system":
        if not Path(ytcore.CHROME).exists():
            raise FileNotFoundError(f"Chrome di sistema non trovato: {ytcore.CHROME}")
        return [f"--browser-executable={ytcore.CHROME}", "--chrome-mode=chrome-for-testing"], "system Chrome (chrome-for-testing mode)"
    version_file = HEADLESS_DIR / "VERSION"
    if not version_file.exists():
        ytcore.log("chrome-headless-shell assente: Remotion lo scarica una volta (~171 MB, ~571 MB su disco)")
        _run_remotion(["browser", "ensure"], [])
    version = version_file.read_text().strip() if version_file.exists() else "?"
    return [], f"chrome-headless-shell {version} (Remotion)"


def _run_remotion(args: list[str], tail: list[str]) -> int:
    """Esegue il binario locale di Remotion; output su stderr con il progresso diradato."""
    env = {**os.environ, **ytcore.node_env(), "DO_NOT_TRACK": "1", "REMOTION_DISABLE_TELEMETRY": "1", "FORCE_COLOR": "0"}
    cmd = [str(REMOTION_BIN), *args]
    ytcore.log("$", " ".join(ytcore._q(a) for a in cmd))
    proc = subprocess.Popen(cmd, cwd=REMOTION_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    last_progress = 0.0
    assert proc.stdout is not None
    for line in proc.stdout:
        line = ANSI_RE.sub("", line.rstrip())
        tail.append(line)
        del tail[:-80]
        if PROGRESS_RE.match(line):
            now = time.monotonic()
            if now - last_progress < 2.0:
                continue
            last_progress = now
        if "PHONE_REGISTRATION_ERROR" in line:
            continue
        ytcore.log(line)
    return proc.wait()


def _alpha_check(path: Path, nb_frames: int, fps: float) -> dict:
    """Decodifica primo, centrale e ultimo frame: alpha presente e overlay vuoto ai bordi (K-23)."""
    from PIL import Image

    out: dict = {}
    tmpdir = TMP_ROOT / f"alpha-{os.getpid()}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        for label, idx in (("first", 0), ("mid", nb_frames // 2), ("last", max(0, nb_frames - 1))):
            png = tmpdir / f"{label}.png"
            ytcore.run([ytcore.FFMPEG, "-v", "error", "-y", "-i", path, "-vf", f"select=eq(n\\,{idx})", "-frames:v", "1",
                        "-pix_fmt", "rgba", png], capture=True)
            with Image.open(png) as im:
                lo, hi = im.getchannel("A").getextrema()
            out[label] = {"frame": idx, "alpha_min": lo, "alpha_max": hi}
            png.unlink()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    out["first_frame_empty"] = out["first"]["alpha_max"] == 0
    out["last_frame_empty"] = out["last"]["alpha_max"] == 0
    out["has_transparency"] = out["mid"]["alpha_min"] < 255
    return out


def probe_output(path: Path) -> dict:
    if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        from PIL import Image

        with Image.open(path) as im:
            return {"width": im.width, "height": im.height, "mode": im.mode, "bytes": path.stat().st_size}
    info = ytcore.ffprobe(path)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {
        "width": v.get("width"), "height": v.get("height"), "codec": v.get("codec_name"), "profile": v.get("profile"),
        "pix_fmt": v.get("pix_fmt"), "fps": round(float(num) / float(den or 1), 3),
        "frames": int(v.get("nb_frames") or 0), "duration": round(float(info["format"].get("duration", 0)), 3),
        "audio": any(s.get("codec_type") == "audio" for s in info["streams"]), "bytes": path.stat().st_size,
    }


def cmd_list() -> None:
    ytcore.emit(True, compositions={k: {kk: vv for kk, vv in v.items() if kk != "alpha"} for k, v in COMPOSITIONS.items()},
                remotion_dir=str(REMOTION_DIR), remotion_src=str(REMOTION_SRC),
                installed=ytcore.npm_project_status(REMOTION_SRC, REMOTION_DIR)[0],
                headless_shell=(HEADLESS_DIR / "VERSION").exists())


def cmd_render(args, still: bool) -> None:
    comp = args.composition
    if comp not in COMPOSITIONS:
        ytcore.fail(f"Composizione sconosciuta: {comp}. Disponibili: {', '.join(COMPOSITIONS)}")
    try:
        ytcore.prepare_remotion()     # sincronizza i sorgenti del plugin nella copia con i node_modules
    except RuntimeError as exc:
        ytcore.fail(str(exc))
    if not REMOTION_BIN.exists():
        ytcore.fail(f"Remotion non installato: manca {REMOTION_BIN} ({ytcore.SETUP_HINT})")
    props_file = Path(args.props).expanduser().resolve()
    if not props_file.exists():
        ytcore.fail(f"File props non trovato: {props_file}")
    out = Path(args.out).expanduser().resolve()
    ext = out.suffix.lower()
    meta = COMPOSITIONS[comp]
    warnings: list[str] = []

    if still:
        if ext not in (".png", ".jpg", ".jpeg"):
            ytcore.fail("still: --out deve essere .png o .jpg")
        codec = "png" if ext == ".png" else "jpeg"
    else:
        if meta["kind"] == "still":
            ytcore.fail(f"{comp} è uno still: usa `yt-remotion still`")
        codec = args.codec or ("prores" if ext == ".mov" else "h264")
        if codec == "prores" and ext not in (".mov", ".mkv"):
            ytcore.fail("ProRes richiede --out .mov")
        if codec == "h264" and ext not in (".mp4", ".mov", ".mkv"):
            ytcore.fail("H.264 richiede --out .mp4 (o .mov)")

    tmp = TMP_ROOT / f"{comp}-{os.getpid()}-{int(time.time() * 1000)}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        try:
            props, inputs = prepare(comp, props_file, tmp, warnings)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            ytcore.fail(str(exc), composition=comp)
        newest_input = _newest_mtime([*inputs, REMOTION_SRC / "src", FONTS_DIR])
        if out.exists() and not args.force and out.stat().st_mtime > newest_input:
            ytcore.emit(True, skipped=True, reason="output più recente degli input (usa --force)", composition=comp,
                        brand=props["brand"], outputs={"file": str(out)}, **probe_output(out), warnings=warnings)
            return
        props_path = tmp / "props.json"
        ytcore.write_json(props_path, props)
        browser_args, browser = _browser_args(args.browser)
        out.parent.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(f"{out.stem}.partial{out.suffix}")
        common = [f"--props={props_path}", f"--public-dir={tmp / 'public'}", "--log=info", *browser_args]
        if still:
            frame = args.frame if args.frame is not None else 0
            cli = ["still", ENTRY, comp, str(partial), *common, f"--scale={args.scale or 1}", f"--frame={frame}",
                   f"--image-format={codec}"]
            if codec == "jpeg":
                cli.append("--jpeg-quality=92")
        else:
            conc = args.concurrency or min(8, os.cpu_count() or 8)
            cli = ["render", ENTRY, comp, str(partial), *common, f"--concurrency={conc}", "--color-space=bt709"]
            if codec == "prores":
                cli += ["--codec=prores", "--prores-profile=4444", "--pixel-format=yuva444p10le", "--image-format=png"]
            else:
                cli += ["--codec=h264", "--crf=18", "--pixel-format=yuv420p", "--image-format=jpeg", "--jpeg-quality=92",
                        "--audio-codec=aac", "--audio-bitrate=192k"]
            if args.scale:
                cli.append(f"--scale={args.scale}")
            if args.frames:
                cli.append(f"--frames={args.frames}")
        t0 = time.monotonic()
        tail: list[str] = []
        rc = _run_remotion(cli, tail)
        elapsed = round(time.monotonic() - t0, 2)
        if rc != 0 or not partial.exists():
            if partial.exists():
                partial.unlink()
            errors = [l for l in tail if re.search(r"error|Error|rror:", l)][-8:] or tail[-15:]
            ytcore.fail(f"Render Remotion fallito (exit {rc})", composition=comp, details=errors, render_seconds=elapsed)
        os.replace(partial, out)
        info = probe_output(out)
        result = {"composition": comp, "brand": props["brand"], "codec": codec, "browser": browser,
                  "render_seconds": elapsed, "outputs": {"file": str(out)}, **info}
        if not still:
            result["concurrency"] = conc
            if info.get("frames"):
                result["render_fps"] = round(info["frames"] / max(elapsed, 0.01), 2)
            if codec == "prores":
                has_alpha = "a" in str(info.get("pix_fmt", "")).replace("yuv", "")
                result["alpha"] = has_alpha
                if not has_alpha:
                    ytcore.fail("ProRes senza canale alpha", **result)
                check = _alpha_check(out, info.get("frames") or 1, info.get("fps") or 30)
                result["alpha_check"] = check
                expects_alpha = meta["alpha"] or props.get("mode") == "overlay" or props.get("background") == "transparent"
                if expects_alpha and not (check["first_frame_empty"] and check["last_frame_empty"]) and not args.frames:
                    warnings.append("overlay: primo/ultimo frame non vuoti (regola K-23)")
                if expects_alpha and not check["has_transparency"]:
                    warnings.append("overlay senza trasparenza nel frame centrale")
            if comp == "ShortCaptions" and props.get("videoSrc") and not info.get("audio"):
                warnings.append("Short senza traccia audio")
        ytcore.emit(True, **result, warnings=warnings)
    finally:
        if not args.keep_tmp:
            _cleanup(tmp)


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-remotion", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="composizioni disponibili")
    for name in ("render", "still"):
        p = sub.add_parser(name, help="render video" if name == "render" else "render di un singolo frame (PNG/JPG)")
        p.add_argument("composition", help="nome composizione (vedi `yt-remotion list`)")
        p.add_argument("--props", required=True, help="JSON con le props (brand, testi, media, …)")
        p.add_argument("--out", required=True, help="file di output (.mov ProRes 4444 alpha · .mp4 H.264 · .png/.jpg)")
        p.add_argument("--scale", type=float, help="fattore di scala (thumbnail: 3 → 3840×2160)")
        p.add_argument("--browser", choices=["managed", "system"], default="managed",
                       help="managed = chrome-headless-shell di Remotion (default), system = Google Chrome")
        p.add_argument("--force", action="store_true", help="rifai anche se l'output è aggiornato")
        p.add_argument("--keep-tmp", action="store_true", help="non cancellare la public dir temporanea (debug)")
        if name == "render":
            p.add_argument("--codec", choices=["prores", "h264"], help="default dall'estensione di --out")
            p.add_argument("--frames", help="intervallo di frame a-b (debug)")
            p.add_argument("--concurrency", type=int, help="tab Chrome in parallelo (default 8 su M5)")
            p.set_defaults(frame=None)
        else:
            p.add_argument("--frame", type=int, help="frame da renderizzare (default 0)")
            p.set_defaults(codec=None, frames=None, concurrency=None)
    args = ap.parse_args()
    if args.cmd == "list":
        cmd_list()
        return
    if args.cmd == "still" and args.scale is None and args.composition == "ThumbnailStill":
        args.scale = 3
    try:
        cmd_render(args, still=args.cmd == "still")
    except RuntimeError as exc:
        ytcore.fail(str(exc))


if __name__ == "__main__":
    main()
