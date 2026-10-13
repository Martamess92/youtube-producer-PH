#!/usr/bin/env python3
"""yt-export-nle — timeline per il montaggio umano (FCPXML 1.10/1.11 + CMX3600 EDL) da edit/edl.json.

I clip puntano ai file ORIGINALI (URL file:// assoluti, symlink risolti), con gli stessi frame
del render (`edl_render.plan_segments`): ciò che si apre nell'NLE coincide con assembled.mov.
FCPXML: spine di asset-clip (tempi razionali N/fps), punch-in come adjust-transform, overlay come
clip collegati (lane 1), musica come clip audio collegati (lane -1, ruolo music, volume),
capitoli (deliver/chapters.json di yt-chapters, altrimenti edit/chapters.draft.json) come marker. EDL CMX3600: un evento per segmento (A/V),
commenti con nome clip e percorso, fallback universale.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402
import edl_render as er  # noqa: E402

STANDARD_FORMATS = {(3840, 2160): "2160p", (1920, 1080): "1080p", (1280, 720): "720p"}


# ── Tempo razionale ─────────────────────────────────────────────────────────
def rt(frames: int, fps: Fraction) -> str:
    """frame → tempo FCPXML razionale: 30 fps → 'N/30s', 29.97 → 'N·1001/30000s', 0 → '0s'."""
    if frames == 0:
        return "0s"
    return f"{frames * fps.denominator}/{fps.numerator}s"


def parse_rt(text: str) -> Fraction:
    t = text.rstrip("s")
    if "/" in t:
        n, d = t.split("/")
        return Fraction(int(n), int(d))
    return Fraction(t)


def timecode(frames: int, fps: Fraction) -> str:
    """Timecode non-drop HH:MM:SS:FF (base = fps arrotondato)."""
    base = int(round(float(fps)))
    ff = frames % base
    s = frames // base
    return f"{s // 3600:02d}:{(s // 60) % 60:02d}:{s % 60:02d}:{ff:02d}"


def parse_tc(tc: str, fps: Fraction) -> int:
    base = int(round(float(fps)))
    h, m, s, f = (int(x) for x in re.split(r"[:;]", tc))
    return ((h * 60 + m) * 60 + s) * base + f


# ── Capitoli ────────────────────────────────────────────────────────────────
def load_chapters(workdir: Path, plan: list[dict], fps: Fraction, main_src: str | None) -> tuple[list[dict], list[str]]:
    """Capitoli → [{frame, title}] sul timeline di uscita.

    Preferisce deliver/chapters.json di yt-chapters (validato e agganciato alle pause, timeline
    di output) se è valido e più recente del draft: così marker FCPXML e chapters.txt coincidono.
    Altrimenti usa edit/chapters.draft.json (mappato da source se serve)."""
    path = workdir / "edit" / "chapters.draft.json"
    final = workdir / "deliver" / "chapters.json"
    warnings: list[str] = []
    total = plan[-1]["out_start_f"] + plan[-1]["n"]
    if final.exists() and (not path.exists() or final.stat().st_mtime >= path.stat().st_mtime):
        try:
            data = yc.read_json(final)
        except (OSError, ValueError):
            data = {}
        if data.get("valid") and data.get("timeline") == "output" and data.get("chapters"):
            out = [{"frame": int(round(float(c.get("t_precise", c.get("t", 0))) * float(fps))),
                    "title": str(c.get("title", "")).strip() or "Capitolo"} for c in data["chapters"]]
            out = [c for c in out if 0 <= c["frame"] < total]
            return sorted(out, key=lambda c: c["frame"]), warnings
    if not path.exists():
        return [], warnings
    data = yc.read_json(path)
    timeline = "output"
    items = data
    if isinstance(data, dict):
        timeline = data.get("timeline", "output")
        items = data.get("chapters") or data.get("items") or []
    out = []
    for ch in items:
        t = yc.parse_ts(ch.get("t", ch.get("time", 0)))
        tl = ch.get("timeline", timeline)
        title = str(ch.get("title", "")).strip() or "Capitolo"
        if tl == "source":
            seg = next((p for p in plan if (main_src is None or p["src"] == main_src)
                        and p["src_in"] <= t < p["src_out"]), None)
            if not seg:
                warnings.append(f"Capitolo '{title}' a {t:.2f}s (source) fuori dai segmenti tenuti: ignorato")
                continue
            t = seg["out_start"] + (t - seg["src_in"])
        out.append({"frame": int(round(t * float(fps))), "title": title})
    total = plan[-1]["out_start_f"] + plan[-1]["n"]
    out = [c for c in out if 0 <= c["frame"] < total]
    return sorted(out, key=lambda c: c["frame"]), warnings


def _seg_at(plan: list[dict], frame: int) -> dict:
    for p in plan:
        if p["out_start_f"] <= frame < p["out_start_f"] + p["n"]:
            return p
    return plan[-1]


# ── FCPXML ──────────────────────────────────────────────────────────────────
def _format_el(res: ET.Element, fid: str, w: int, h: int, fps: Fraction) -> ET.Element:
    attrs = {"id": fid, "frameDuration": rt(1, fps), "width": str(w), "height": str(h),
             "colorSpace": "1-1-1 (Rec. 709)"}
    std = STANDARD_FORMATS.get((w, h))
    rate = {Fraction(30): "30", Fraction(25): "25", Fraction(24): "24", Fraction(60): "60", Fraction(50): "50",
            Fraction(30000, 1001): "2997", Fraction(24000, 1001): "2398", Fraction(60000, 1001): "5994"}.get(fps)
    if std and rate:
        attrs = {"id": fid, "name": f"FFVideoFormat{std}{rate}", **{k: v for k, v in attrs.items() if k != "id"}}
    return ET.SubElement(res, "format", attrs)


def build_fcpxml(workdir: Path, edl: dict, plan: list[dict], chapters: list[dict], *, version: str,
                 project_name: str, event_name: str, chapter_markers: bool) -> tuple[ET.Element, dict]:
    fps = edl["fps"]
    W, H = edl["canvas"]["w"], edl["canvas"]["h"]
    root = ET.Element("fcpxml", {"version": version})
    res = ET.SubElement(root, "resources")
    ids = iter(f"r{i}" for i in range(1, 10_000))
    seq_fmt = next(ids)
    _format_el(res, seq_fmt, W, H, fps)
    formats = {(W, H, fps): seq_fmt}

    def fmt_for(info: dict) -> str:
        key = (int(info["width"]), int(info["height"]), er._fps_fraction(info.get("fps") or fps))
        if key not in formats:
            formats[key] = next(ids)
            _format_el(res, formats[key], key[0], key[1], key[2])
        return formats[key]

    def asset(path: Path, info: dict, name: str) -> str:
        aid = next(ids)
        dur_f = int(round(info["duration"] * float(fps)))
        attrs = {"id": aid, "name": name, "start": "0s", "duration": rt(max(1, dur_f), fps)}
        if info.get("has_video"):
            attrs.update(hasVideo="1", format=fmt_for(info), videoSources="1")
        if info.get("has_audio"):
            attrs.update(hasAudio="1", audioSources="1", audioChannels=str(info.get("channels") or 2),
                         audioRate=str(info.get("sample_rate") or 48000))
        el = ET.SubElement(res, "asset", attrs)
        ET.SubElement(el, "media-rep", {"kind": "original-media", "src": Path(path).resolve().as_uri()})
        return aid

    src_assets = {k: asset(s["real"], s["info"], Path(s["real"]).stem) for k, s in edl["sources"].items()}
    ov_assets = [asset(o["path"], o["info"], Path(o["path"]).stem) for o in edl["overlays"]]
    mu_assets = [asset(m["path"], m["info"], Path(m["path"]).stem) for m in edl["music"]]

    lib = ET.SubElement(root, "library")
    ev = ET.SubElement(lib, "event", {"name": event_name})
    pr = ET.SubElement(ev, "project", {"name": project_name})
    total = plan[-1]["out_start_f"] + plan[-1]["n"]
    seq = ET.SubElement(pr, "sequence", {"format": seq_fmt, "duration": rt(total, fps), "tcStart": "0s",
                                         "tcFormat": "NDF", "audioLayout": "stereo", "audioRate": "48k"})
    spine = ET.SubElement(seq, "spine")

    clips: dict[int, ET.Element] = {}
    for p in plan:
        name = f"{p['id']} {p['label']}" if p.get("label") else p["id"]
        el = ET.SubElement(spine, "asset-clip", {
            "ref": src_assets[p["src"]], "offset": rt(p["out_start_f"], fps), "name": name,
            "start": rt(p["in_f"], fps), "duration": rt(p["n"], fps), "tcFormat": "NDF",
            "audioRole": "dialogue"})
        if p.get("zoom"):
            # punch-in come trasformazione: scala + spostamento perché il centro del crop vada al centro
            # (posizione FCPXML in % dell'altezza fotogramma, asse y verso l'alto)
            info = edl["sources"][p["src"]]["info"]
            sw, sh = info["width"], info["height"]
            cw, chh, x, y = er.zoom_crop(p["zoom"], sw, sh)
            s = sw / cw
            ccx, ccy = x + cw / 2, y + chh / 2
            px = (sw / 2 - ccx) * s / sh * 100
            py = (ccy - sh / 2) * s / sh * 100
            ET.SubElement(el, "adjust-transform", {"position": f"{px:.4f} {py:.4f}", "scale": f"{s:.4f} {s:.4f}"})
        if p.get("gain_db"):
            ET.SubElement(el, "adjust-volume", {"amount": f"{p['gain_db']:+.1f}dB"})
        clips[p["idx"]] = el

    fpsf = float(fps)

    def anchor(frame: int) -> tuple[ET.Element, int]:
        p = _seg_at(plan, frame)
        return clips[p["idx"]], p["in_f"] + (frame - p["out_start_f"])  # tempo locale del clip padre

    for o, aid in zip(edl["overlays"], ov_assets):
        a, b = er._overlay_span(o)
        fa, fb = int(round(a * fpsf)), int(round(b * fpsf))
        if fb <= fa or fa >= total:
            continue
        parent, local = anchor(fa)
        ET.SubElement(parent, "asset-clip", {"ref": aid, "lane": "1", "offset": rt(local, fps),
                                             "name": Path(o["path"]).stem, "start": "0s",
                                             "duration": rt(min(fb, total) - fa, fps), "tcFormat": "NDF"})
    for m, aid in zip(edl["music"], mu_assets):
        at = float(m.get("at", 0))
        fa = int(round(at * fpsf))
        if fa >= total:
            continue
        fdur = int(round(float(m["info"]["duration"]) * fpsf))
        end = int(round(float(m["until"]) * fpsf)) if m.get("until") is not None else fa + fdur
        end = min(end, fa + fdur, total)
        if end <= fa:
            continue
        parent, local = anchor(fa)
        mc = ET.SubElement(parent, "asset-clip", {"ref": aid, "lane": "-1", "offset": rt(local, fps),
                                                  "name": Path(m["path"]).stem, "start": "0s",
                                                  "duration": rt(end - fa, fps), "audioRole": "music"})
        ET.SubElement(mc, "adjust-volume", {"amount": f"{float(m.get('gain_db', -20)):+.1f}dB"})
    for ch in chapters:
        parent, local = anchor(ch["frame"])
        tag = "chapter-marker" if chapter_markers else "marker"
        attrs = {"start": rt(local, fps), "duration": rt(1, fps), "value": ch["title"]}
        if chapter_markers:
            attrs["posterOffset"] = "0s"
        ET.SubElement(parent, tag, attrs)
    return root, {"assets": len(src_assets) + len(ov_assets) + len(mu_assets), "clips": len(plan),
                  "overlays": len(ov_assets), "music": len(mu_assets), "markers": len(chapters)}


def write_fcpxml(root: ET.Element, out: Path) -> None:
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    tmp = out.with_name(f".{out.name}.tmp")
    tmp.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n\n' + body + "\n", encoding="utf-8")
    tmp.replace(out)


def validate_fcpxml(path: Path, fps: Fraction) -> dict:
    """Ben formato (parser Python + xmllint se c'è) + controlli semantici del timeline."""
    errors: list[str] = []
    tree = ET.parse(path)  # solleva se malformato
    root = tree.getroot()
    lint = None
    xmllint = shutil.which("xmllint")
    if xmllint:
        proc = yc.run([xmllint, "--noout", str(path)], check=False, capture=True)
        lint = "ok" if proc.returncode == 0 else proc.stderr.strip()[:500]
        if proc.returncode != 0:
            errors.append(f"xmllint: {lint}")
    ids = {el.get("id") for el in root.iter() if el.get("id")}
    for el in root.iter():
        if el.get("ref") and el.get("ref") not in ids:
            errors.append(f"ref inesistente: {el.get('ref')}")
        if el.get("format") and el.tag != "sequence" and el.get("format") not in ids:
            errors.append(f"format inesistente: {el.get('format')}")
    fd = Fraction(1) / fps
    for el in root.iter():
        for attr in ("offset", "start", "duration"):
            v = el.get(attr)
            if v is None or el.tag in ("asset",):
                continue
            q = parse_rt(v) / fd
            if q.denominator != 1:
                errors.append(f"{el.tag}@{attr}={v} non allineato al frame")
    seq = root.find(".//sequence")
    spine = seq.find("spine")
    cur = Fraction(0)
    for clip in spine:
        if parse_rt(clip.get("offset")) != cur:
            errors.append(f"spine non contiguo a {clip.get('name')}: offset {clip.get('offset')} ≠ {cur}")
        cur += parse_rt(clip.get("duration"))
    if cur != parse_rt(seq.get("duration")):
        errors.append(f"somma durate spine {cur} ≠ durata sequenza {seq.get('duration')}")
    assets = {a.get("id"): a for a in root.iter("asset")}
    for clip in spine:
        a = assets.get(clip.get("ref"))
        if a is not None and parse_rt(clip.get("start")) + parse_rt(clip.get("duration")) > parse_rt(a.get("duration")):
            errors.append(f"{clip.get('name')}: oltre la fine dell'asset")
    for a in assets.values():
        rep = a.find("media-rep")
        src = rep.get("src") if rep is not None else None
        if not src or not src.startswith("file:///"):
            errors.append(f"asset {a.get('name')}: media-rep senza URL file:// assoluto")
    return {"well_formed": True, "xmllint": lint, "errors": errors, "ok": not errors,
            "spine_clips": len(spine), "duration": seq.get("duration")}


# ── CMX3600 ─────────────────────────────────────────────────────────────────
def _reel(path: str) -> str:
    stem = re.sub(r"[^A-Z0-9_]", "_", Path(path).stem.upper())
    return (stem or "AX")[:8]


def build_cmx(edl: dict, plan: list[dict], title: str, tc_start: int) -> str:
    fps = edl["fps"]
    lines = [f"TITLE: {title[:70]}", "FCM: NON-DROP FRAME", ""]
    for k, p in enumerate(plan, 1):
        reel = _reel(p["src_path"])
        s_in, s_out = p["in_f"], p["in_f"] + p["n"]
        r_in, r_out = tc_start + p["out_start_f"], tc_start + p["out_start_f"] + p["n"]
        lines.append(f"{k:03d}  {reel:<8} AA/V  C        {timecode(s_in, fps)} {timecode(s_out, fps)} "
                     f"{timecode(r_in, fps)} {timecode(r_out, fps)}")
        lines.append(f"* FROM CLIP NAME: {Path(p['src_path']).name}")
        lines.append(f"* SOURCE FILE: {p['src_path']}")
        if p.get("label") or p["id"]:
            lines.append(f"* COMMENT: {p['id']} {p.get('label') or ''}".rstrip())
        if p.get("zoom"):
            z = p["zoom"]
            lines.append(f"* EFFECT: PUNCH-IN {float(z.get('scale', 1)):.2f}x CX {float(z.get('cx', .5)):.2f} "
                         f"CY {float(z.get('cy', .5)):.2f}")
        lines.append("")
    return "\n".join(lines)


def validate_cmx(text: str, plan: list[dict], fps: Fraction, tc_start: int) -> dict:
    ev = re.compile(r"^(\d{3})\s+(\S+)\s+(\S+)\s+C\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$")
    events = [m.groups() for line in text.splitlines() if (m := ev.match(line))]
    errors = []
    if len(events) != len(plan):
        errors.append(f"{len(events)} eventi ≠ {len(plan)} segmenti")
    prev_out = tc_start
    for e, p in zip(events, plan):
        si, so, ri, ro = (parse_tc(x, fps) for x in e[3:])
        if so - si != ro - ri or so - si != p["n"]:
            errors.append(f"evento {e[0]}: durate incoerenti")
        if ri != prev_out:
            errors.append(f"evento {e[0]}: record non contiguo")
        prev_out = ro
    return {"events": len(events), "errors": errors, "ok": not errors}


# ── CLI ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        prog="yt-export-nle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Esporta il montaggio di edit/edl.json come timeline per NLE: deliver/<slug>.fcpxml "
                    "(FCPXML 1.10) e deliver/<slug>.edl (CMX3600). I clip puntano ai file originali.",
        epilog="""Come aprirli:
  Final Cut Pro      File > Import > XML… → deliver/<slug>.fcpxml (crea evento + progetto)
  DaVinci Resolve    File > Import > Timeline… (anche nella versione gratuita) → .fcpxml o .edl;
                     con l'EDL scegli i clip dal media pool o "Automatically import source clips"
  Kdenlive           importa la timeline via OpenTimelineIO (FCPXML) o l'EDL CMX3600 dal menu
                     File > Import; se il sorgente non viene trovato, ricollega il file indicato
                     nei commenti "* SOURCE FILE".
Contenuto: un asset-clip per segmento (stessi frame di yt-edl-render, tempi razionali N/fps),
punch-in come adjust-transform, overlay (lane 1) e musica (lane -1, ruolo music, volume),
capitoli (deliver/chapters.json di yt-chapters, altrimenti edit/chapters.draft.json) come marker. L'EDL CMX3600 porta solo i tagli (A/V) con nome
e percorso del clip nei commenti: è il ripiego universale.

Esempi:
  yt-export-nle esempio/2026-10-13-ospite-paolo
  yt-export-nle WORKDIR --format fcpxml --chapter-markers
  yt-export-nle WORKDIR --fcpxml-version 1.11 --tc-start 01:00:00:00""")
    ap.add_argument("workdir", metavar="WORKDIR", help="cartella di lavoro (path o <channel>/<dir>)")
    ap.add_argument("--edl", default="edit/edl.json", help="EDL (default edit/edl.json)")
    ap.add_argument("--format", default="fcpxml,edl",
                    help="formati separati da virgola: fcpxml, edl (default entrambi; 'all' = entrambi)")
    ap.add_argument("--fcpxml-version", choices=("1.10", "1.11"), default="1.10", help="versione FCPXML (default 1.10)")
    ap.add_argument("--chapter-markers", action="store_true",
                    help="capitoli come <chapter-marker> (Final Cut) invece di <marker> (più portabile)")
    ap.add_argument("--tc-start", default="00:00:00:00", help="timecode di partenza del record EDL (default 00:00:00:00)")
    ap.add_argument("--name", help="nome del progetto (default <slug>)")
    ap.add_argument("--force", action="store_true", help="riscrive anche se aggiornato")
    a = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(a.workdir)
        edl_path = Path(a.edl) if Path(a.edl).is_absolute() else workdir / a.edl
        project = yc.load_project(workdir)
        slug = project.get("slug") or workdir.name
        formats = {"fcpxml", "edl"} if a.format == "all" else {f.strip() for f in a.format.split(",") if f.strip()}
        if not formats <= {"fcpxml", "edl"}:
            raise ValueError(f"Formato sconosciuto: {formats - {'fcpxml', 'edl'}}")
        deliver = workdir / "deliver"
        deliver.mkdir(parents=True, exist_ok=True)
        outs = {"fcpxml": deliver / f"{slug}.fcpxml", "edl": deliver / f"{slug}.edl"}
        inputs = [edl_path, workdir / "project.json", workdir / "edit" / "chapters.draft.json",
                  workdir / "deliver" / "chapters.json"]
        newest = max(p.stat().st_mtime for p in inputs if p.exists())
        if not a.force and all(outs[f].exists() and outs[f].stat().st_mtime >= newest for f in formats):
            yc.log("✓ export già aggiornato (usa --force per rifare)")
            yc.emit(True, skipped=True, outputs={f: str(outs[f]) for f in formats}, warnings=[])
            return

        edl = er.load_edl(workdir, edl_path)
        plan = er.plan_segments(edl)
        fps = edl["fps"]
        chapters, warnings = load_chapters(workdir, plan, fps, project.get("main_source"))
        result: dict = {"segments": len(plan), "fps": f"{fps.numerator}/{fps.denominator}",
                        "duration": round(er._tc(plan[-1]["out_start_f"] + plan[-1]["n"], fps), 3),
                        "chapters": len(chapters)}
        outputs = {}
        if "fcpxml" in formats:
            root, stats = build_fcpxml(workdir, edl, plan, chapters, version=a.fcpxml_version,
                                       project_name=a.name or slug,
                                       event_name=project.get("title_working") or slug,
                                       chapter_markers=a.chapter_markers)
            write_fcpxml(root, outs["fcpxml"])
            val = validate_fcpxml(outs["fcpxml"], fps)
            result["fcpxml"] = {**stats, "version": a.fcpxml_version, "validation": val}
            outputs["fcpxml"] = str(outs["fcpxml"])
            if not val["ok"]:
                warnings += val["errors"]
        if "edl" in formats:
            tc0 = parse_tc(a.tc_start, fps)
            text = build_cmx(edl, plan, a.name or slug, tc0)
            tmp = outs["edl"].with_name(f".{outs['edl'].name}.tmp")
            tmp.write_text(text, encoding="ascii", errors="replace")
            tmp.replace(outs["edl"])
            val = validate_cmx(outs["edl"].read_text(), plan, fps, tc0)
            result["edl"] = {"events": val["events"], "validation": val}
            outputs["edl"] = str(outs["edl"])
            if not val["ok"]:
                warnings += val["errors"]
        if "edl" in formats and (edl["overlays"] or edl["music"]):
            warnings.append("EDL CMX3600: overlay e musica non inclusi (solo nel FCPXML)")
        ok = all(result[f]["validation"]["ok"] for f in formats)
        yc.emit(ok, outputs=outputs, **result, warnings=warnings)
    except Exception as exc:  # noqa: BLE001
        yc.fail(str(exc))


if __name__ == "__main__":
    main()
