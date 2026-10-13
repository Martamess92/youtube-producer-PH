"""yt-outliers — quali video hanno fatto molto meglio (o peggio) del solito, a parità di formato.

Fonti:
  --channel X     canale proprio, dal DB (prima: yt-collect --channel X --what inventory)
  --peers FILE    canali di riferimento, uno per riga:  URL | @handle | UC…   [lingua]   # commento
                  metadati via Data API (chiave) oppure yt-dlp (ripiego, basso volume, niente
                  sottotitoli né cookie). Dati di terzi: tenuti al massimo 30 giorni (policy API).

Metodo (metrica DERIVATA, non un numero YouTube):
  outlier_x = views / mediana(views dei --window video PRECEDENTI dello stesso formato)
              (Shorts e long-form separati; live esclusi salvo --include-live)
  log_z     = (ln(1+views) − mediana ln(1+views_base)) / (1.4826 · MAD)   → |z| ≥ 2 = anomalia robusta
  tier      ≥10x breakout · ≥5x forte · ≥2x notevole · ≤0.5x sotto la norma
  età       i video più giovani di 14 gg (long) / 7 gg (Shorts) non ricevono un tier.
            Base "views": views di oggi, NON a pari età (multiplo prudente per i video recenti);
            base "views_28d": views dei primi 28 giorni dall'Analytics API (stessa età, Tier 2);
            --age-adjust stima la crescita con l'età (views ∝ età^b, Theil–Sen) e corregge la base.

Esempi:
  yt-outliers --channel esempio --md ~/youtube-studio/cache/outliers/esempio.md
  yt-outliers --peers ~/youtube-studio/data/peers-esempio.txt --format long --top 20
  yt-outliers --channel esempio --peers peers.txt --window 30 --age-adjust
"""
from __future__ import annotations

import argparse
import datetime as _dt
import math
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as C  # noqa: E402  (fetch Data API / yt-dlp condivisi con yt-collect)
import ytauth  # noqa: E402
import ytcore  # noqa: E402
import ytdb  # noqa: E402
from ytcore import log  # noqa: E402

OUT_DIR = ytcore.CACHE / "outliers"
TIERS = [(10.0, "breakout 10x"), (5.0, "forte 5x"), (2.0, "notevole 2x")]
UNDER = (0.5, "sotto 0.5x")


# ═══ Statistica ═════════════════════════════════════════════════════════════
def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def mad(xs: list[float]) -> float | None:
    m = median(xs)
    return median([abs(x - m) for x in xs]) if xs else None


def theil_sen(points: list[tuple[float, float]]) -> float | None:
    """Pendenza robusta (mediana delle pendenze a coppie)."""
    slopes = [(y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(points) for (x2, y2) in points[i + 1:]
              if x2 != x1]
    return median(slopes)


def tier_of(x: float | None) -> str:
    if x is None:
        return ""
    for thr, name in TIERS:
        if x >= thr:
            return name
    return UNDER[1] if x <= UNDER[0] else ""


def age_days(published_at: str | None, today: _dt.date) -> int | None:
    d = C.date_of(published_at)
    return (today - d).days if d else None


# ═══ Punteggio ══════════════════════════════════════════════════════════════
def chrono(videos: list[dict]) -> list[dict]:
    """Dal più vecchio al più recente. Le date approssimate hanno pareggi: decide la posizione
    nella scheda del canale (indice più alto = più vecchio)."""
    if all(v.get("published_at") for v in videos):
        return sorted(videos, key=lambda v: (v["published_at"][:19], -(v.get("position") or 0)))
    return sorted(videos, key=lambda v: -(v.get("position") if v.get("position") is not None else 10**6))


def growth_exponent(group: list[dict], value_key: str, min_age: int, today: _dt.date) -> float | None:
    pts = []
    for v in group:
        a = age_days(v.get("published_at"), today)
        val = v.get(value_key)
        if a and a >= min_age and val and val > 0:
            pts.append((math.log(a), math.log(val)))
    if len(pts) < 6:
        return None
    b = theil_sen(pts)
    return None if b is None else max(0.0, min(1.0, b))


def score_group(group: list[dict], *, value_key: str, window: int, min_baseline: int, min_age: int,
                age_adjust: bool, today: _dt.date) -> tuple[list[dict], dict]:
    """Punteggi per un canale e un formato. Ritorna (righe, meta)."""
    group = chrono([v for v in group if v.get(value_key) is not None])
    b = growth_exponent(group, value_key, min_age, today) if age_adjust and value_key == "views" else None
    out = []
    for i, v in enumerate(group):
        val = float(v[value_key])
        prev = group[max(0, i - window):i]
        kind = "precedenti"
        if len(prev) < min_baseline:
            others = sorted(((abs(j - i), j, g) for j, g in enumerate(group) if j != i), key=lambda t: t[:2])
            prev = [g for _, _, g in others[:window]]
            kind = "vicini (pochi video precedenti)"
        base_vals = [float(g[value_key]) for g in prev]
        row = {
            "channel_id": v.get("channel_id"), "channel": v.get("channel_title"), "video_id": v["id"],
            "title": v.get("title"), "format": v.get("format"), "published_at": v.get("published_at"),
            "precision": v.get("published_precision"), "age_days": age_days(v.get("published_at"), today),
            "value": int(val), "basis": value_key, "views": v.get("views"),
            "baseline_n": len(base_vals), "baseline_kind": kind, "baseline_median": None,
            "outlier_x": None, "outlier_x_age_adj": None, "log_z": None, "tier": "", "flags": [],
            "vsr": None, "likes_per_1k": None, "url": f"https://www.youtube.com/watch?v={v['id']}",
        }
        if len(base_vals) < 3:
            row["flags"].append("campione insufficiente")
            out.append(row)
            continue
        med = median(base_vals)
        row["baseline_median"] = med
        row["outlier_x"] = round(val / med, 2) if med else None
        logs = [math.log1p(x) for x in base_vals]
        m_log, d_log = median(logs), mad(logs)
        if d_log:
            row["log_z"] = round((math.log1p(val) - m_log) / (1.4826 * d_log), 2)
        ages = [age_days(g.get("published_at"), today) for g in prev]
        ages = [a for a in ages if a]
        if row["age_days"] and ages:
            row["age_ratio"] = round(row["age_days"] / median(ages), 2)
        if b is not None and row["age_days"]:
            adj = [float(g[value_key]) * (row["age_days"] / a) ** b
                   for g in prev if (a := age_days(g.get("published_at"), today))]
            if len(adj) >= 3 and median(adj):
                row["outlier_x_age_adj"] = round(val / median(adj), 2)
        x_for_tier = row["outlier_x_age_adj"] if row["outlier_x_age_adj"] is not None else row["outlier_x"]
        if value_key == "views" and row["age_days"] is not None and row["age_days"] < min_age:
            row["flags"].append(f"recente (<{min_age} gg): niente tier")
        elif value_key == "views" and row["age_days"] is None:
            # senza data (Shorts via yt-dlp) un video giovane sembrerebbe "sotto": solo i tier positivi
            tier = tier_of(x_for_tier)
            row["tier"] = "" if tier == UNDER[1] else tier
            row["flags"].append("data ignota: niente tier 'sotto'")
        else:
            row["tier"] = tier_of(x_for_tier)
        if row["log_z"] is not None and row["log_z"] >= 2:
            row["flags"].append("z≥2")
        if v.get("subscribers"):
            row["vsr"] = round((v.get("views") or 0) / v["subscribers"], 3)
        if v.get("likes") is not None and v.get("views"):
            row["likes_per_1k"] = round(1000 * v["likes"] / v["views"], 1)
            if v["views"] >= 1000 and row["likes_per_1k"] < 1.5:
                row["flags"].append("engagement basso (<1.5 like/1000 views)")
        out.append(row)
    meta = {"videos": len(group), "median": median([float(v[value_key]) for v in group]) if group else None,
            "growth_exponent_b": b}
    return out, meta


def score_channel(videos: list[dict], *, args, today: _dt.date, basis: str) -> tuple[list[dict], list[dict]]:
    formats = ["long", "short"] + (["live"] if args.include_live else [])
    if args.format != "all":
        formats = [args.format]
    rows, metas = [], []
    for fmt in formats:
        group = [v for v in videos if v.get("format") == fmt]
        if not group:
            continue
        min_age = args.min_age_short if fmt == "short" else args.min_age_long
        r, m = score_group(group, value_key=basis, window=args.window, min_baseline=args.min_baseline,
                           min_age=min_age, age_adjust=args.age_adjust, today=today)
        m.update(format=fmt, basis=basis, excluded_no_value=len(group) - m["videos"],
                 tiers={t: sum(1 for x in r if x["tier"] == t) for _, t in TIERS + [UNDER]})
        if m["videos"] < 10:
            m["caveat"] = f"canale piccolo: {m['videos']} video {fmt}, baseline instabile (servono ≥10)"
        rows += r
        metas.append(m)
    return rows, metas


# ═══ Dati: canale proprio ═══════════════════════════════════════════════════
def own_videos(conn, ref: str, basis_arg: str) -> tuple[dict, list[dict], str, str]:
    ch = ytdb.find_channel(conn, ref)
    if not ch:
        try:
            r = C.resolve_channel(ref)
            ch = ytdb.find_channel(conn, r.get("id") or r.get("handle") or ref)
        except ValueError:
            ch = None
    if not ch:
        raise LookupError(f"Canale '{ref}' non in archivio: esegui prima yt-collect --channel {ref} --what inventory")
    vids = ytdb.rows(conn, """SELECT v.*, a.views AS views_28d, a.complete AS d28_complete
                              FROM videos v LEFT JOIN analytics_28d a ON a.video_id = v.id
                              WHERE v.channel_id=? AND COALESCE(v.privacy,'public')='public'""", (ch["id"],))
    for v in vids:
        v["channel_title"] = ch["title"]
        v["subscribers"] = ch["subscribers"]
        if not v.get("d28_complete"):
            v["views_28d"] = None
    basis = basis_arg
    if basis_arg == "auto":
        with28 = sum(1 for v in vids if v["views_28d"] is not None)
        basis = "views_28d" if vids and with28 >= max(5, 0.6 * len(vids)) else "views"
    note = age_note(basis)
    return ch, vids, basis, note


def age_note(basis: str, age_adjust: bool = False) -> str:
    if basis == "views_28d":
        return ("Stessa età: views nei primi 28 giorni dalla pubblicazione (Analytics API, Tier 2). "
                "I video senza finestra di 28 giorni chiusa sono esclusi.")
    note = ("Views di oggi, non a pari età: i video precedenti hanno avuto più tempo per accumulare views, "
            "quindi per i video recenti il multiplo è prudente (sottostimato). Per un confronto a età fissa servono "
            "gli snapshot giornalieri (video_stats_daily, si accumulano a ogni yt-collect) o Tier 2 (analytics_28d).")
    if age_adjust:
        note += " Con --age-adjust la base è riscalata con views ∝ età^b (b stimato sul canale, Theil–Sen)."
    return note


# ═══ Dati: peers ════════════════════════════════════════════════════════════
def read_peers_file(path: Path) -> list[tuple[str, str | None]]:
    out = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        lang = parts[1] if len(parts) > 1 and re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", parts[1]) else None
        out.append((parts[0], lang))
    return out


def peer_fresh(conn, ref: str, max_age_days: float) -> dict | None:
    r = conn.execute("SELECT * FROM peers WHERE input=?", (ref,)).fetchone()
    if r and C.is_fresh(r["fetched_at"], max_age_days * 24):
        return dict(r)
    return None


def save_peer(conn, channel: dict, rows: list[dict], source: str) -> None:
    now = C.utc_now().isoformat(timespec="seconds")
    with conn:
        conn.execute("DELETE FROM peer_videos WHERE channel_id=?", (channel["channel_id"],))
        ytdb.replace(conn, "peers", {**channel, "source": source, "fetched_at": now})
        for v in rows:
            ytdb.replace(conn, "peer_videos", {
                "video_id": v["id"], "channel_id": channel["channel_id"], "title": v.get("title"),
                "published_at": v.get("published_at"), "published_precision": v.get("published_precision"),
                "duration": v.get("duration"), "format": v.get("format"), "position": v.get("position"),
                "views": v.get("views"), "likes": v.get("likes"), "comments": v.get("comments"),
                "thumbnail_url": v.get("thumbnail_url"), "source": source, "fetched_at": now})


def fetch_peer_api(conn, meter, yt, ref_text: str, lang: str | None, per_channel: int) -> dict:
    ref = C.parse_channel_ref(ref_text)
    item = C.api_channel(yt, meter, ref)
    sn, cd, st = item.get("snippet", {}), item.get("contentDetails", {}), item.get("statistics", {})
    uploads = (cd.get("relatedPlaylists") or {}).get("uploads")
    ids = C.api_upload_ids(yt, meter, uploads, limit=per_channel) if uploads else []
    rows = [C.api_video_row(i) for i in C.api_videos(yt, meter, ids)]
    for pos, r in enumerate(sorted(rows, key=lambda r: r.get("published_at") or "", reverse=True)):
        r["position"] = pos
    channel = {"channel_id": item["id"], "input": ref_text, "handle": sn.get("customUrl"), "title": sn.get("title"),
               "url": ref.get("url"), "language": lang,
               "subscribers": None if st.get("hiddenSubscriberCount") else
               (int(st["subscriberCount"]) if st.get("subscriberCount") else None),
               "video_count": int(st["videoCount"]) if st.get("videoCount") else None}
    save_peer(conn, channel, rows, "api")
    return {**channel, "source": "api"}


def fetch_peer_ytdlp(conn, meter, ref_text: str, lang: str | None, per_channel: int) -> dict:
    ref = C.parse_channel_ref(ref_text)
    listing = C.ytdlp_channel_listing(ref["url"], meter, lang=lang or "it", limit=per_channel,
                                      tabs=(("videos", "long"), ("shorts", "short")), approx_dates=True)
    meta, rows = listing["meta"], listing["rows"]
    if not meta.get("channel_id"):
        raise C.YtdlpError(f"Canale non trovato: {ref_text}")
    handle = meta.get("uploader_id") if str(meta.get("uploader_id", "")).startswith("@") else ref.get("handle")
    channel = {"channel_id": meta["channel_id"], "input": ref_text, "handle": handle, "title": meta.get("channel"),
               "url": ref["url"], "language": lang, "subscribers": meta.get("channel_follower_count"),
               "video_count": len(rows)}
    save_peer(conn, channel, list(rows.values()), "ytdlp")
    return {**channel, "source": "ytdlp"}


def peer_videos(conn, channel_id: str) -> list[dict]:
    p = conn.execute("SELECT * FROM peers WHERE channel_id=?", (channel_id,)).fetchone()
    vids = ytdb.rows(conn, "SELECT video_id AS id, * FROM peer_videos WHERE channel_id=?", (channel_id,))
    for v in vids:
        v["channel_title"] = p["title"] if p else None
        v["subscribers"] = p["subscribers"] if p else None
    return vids


# ═══ Output ═════════════════════════════════════════════════════════════════
def _md_cell(text: Any) -> str:
    return str(text if text is not None else "—").replace("|", "\\|").replace("\n", " ")


def _fmt_x(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}x"


def render_md(title: str, sections: list[dict], method: dict) -> str:
    lines = [f"# Outlier — {title} — {ytdb.today_iso()}", "",
             f"**Metodo**: {method['formula']}. {method['z']}. Tier: {method['tiers']}. "
             f"_Metrica derivata, non un dato YouTube._", ""]
    for sec in sections:
        lines += [f"## {sec['heading']}", ""]
        if sec.get("note"):
            lines += [f"> {sec['note']}", ""]
        for m in sec["metas"]:
            extra = f" · b={m['growth_exponent_b']:.2f}" if m.get("growth_exponent_b") is not None else ""
            cav = f" · ⚠ {m['caveat']}" if m.get("caveat") else ""
            med = f"{m['median']:.0f}" if m.get("median") is not None else "—"
            lines.append(f"- **{m['format']}**: {m['videos']} video, mediana {med} ({m['basis']}){extra}{cav}")
        lines += ["", "| # | Video | Formato | Pubblicato | Età (gg) | Valore | Base (n · mediana) | x | x età | z | Tier | Note |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(sec["rows"], 1):
            pub = (r.get("published_at") or "")[:10] + ("~" if r.get("precision") == "approx" else "")
            base = f"{r['baseline_n']} · {r['baseline_median']:.0f}" if r.get("baseline_median") is not None else f"{r['baseline_n']} · —"
            if r.get("baseline_kind", "").startswith("vicini"):
                base += " (vicini)"
            link = f"[{_md_cell(r['title'])}]({r['url']})"  # titolo già con | protetti
            cells = [_md_cell(c) for c in [i]] + [link] + [_md_cell(c) for c in [
                r["format"], pub or "—", r.get("age_days"), r["value"], base, _fmt_x(r["outlier_x"]),
                _fmt_x(r.get("outlier_x_age_adj")), r["log_z"] if r["log_z"] is not None else "—",
                r["tier"] or "—", "; ".join(r["flags"]) or ""]]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["~ = data approssimata (yt-dlp). Base = video precedenti dello stesso formato; "
              "(vicini) = canale con meno video precedenti del minimo, base presa dai video più vicini.", ""]
    return "\n".join(lines)


def sort_rows(rows: list[dict]) -> list[dict]:
    def key(r):
        x = r["outlier_x_age_adj"] if r.get("outlier_x_age_adj") is not None else r["outlier_x"]
        return (x is None, -(x or 0))
    return sorted(rows, key=key)


# ═══ Main ═══════════════════════════════════════════════════════════════════
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="yt-outliers", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", help="canale proprio dal DB: slug del profilo, @handle o UC…")
    ap.add_argument("--peers", help="file con i canali di riferimento (uno per riga, lingua opzionale)")
    ap.add_argument("--window", type=int, default=25, help="video precedenti nella base (default 25; consigliato 20–30)")
    ap.add_argument("--min-baseline", type=int, default=5,
                    help="minimo di video precedenti; sotto si usano i video più vicini (default 5)")
    ap.add_argument("--format", choices=["all", "long", "short", "live"], default="all", help="formato (default all)")
    ap.add_argument("--include-live", action="store_true", help="calcola anche i live (esclusi di default)")
    ap.add_argument("--basis", choices=["auto", "views", "views_28d"], default="auto",
                    help="auto = views_28d se Tier 2 copre ≥60%% dei video, altrimenti views di oggi")
    ap.add_argument("--age-adjust", action="store_true", help="correggi la base per l'età (views ∝ età^b)")
    ap.add_argument("--min-age-long", type=int, default=14, help="età minima per il tier, long-form (gg)")
    ap.add_argument("--min-age-short", type=int, default=7, help="età minima per il tier, Shorts (gg)")
    ap.add_argument("--per-channel", type=int, default=50, help="peers: ultimi N video per scheda (default 50)")
    ap.add_argument("--max-peers", type=int, default=40, help="peers: massimo canali per esecuzione")
    ap.add_argument("--peer-max-age-days", type=float, default=7, help="peers: riusa dati più recenti di N giorni")
    ap.add_argument("--refresh", action="store_true", help="peers: riscarica anche se i dati sono freschi")
    ap.add_argument("--tier", type=int, choices=[0, 1], default=1, help="peers: 0 forza yt-dlp anche con la chiave API")
    ap.add_argument("--top", type=int, default=30, help="righe nel JSON su stdout (il file --json le ha tutte)")
    ap.add_argument("--md", help="scrivi la tabella markdown in questo file")
    ap.add_argument("--json", help=f"risultato completo (default {OUT_DIR}/<nome>-<data>.json)")
    ap.add_argument("--quota-budget", type=int, default=5000, help="tetto unità Data API al giorno")
    ap.add_argument("--db", help=f"database (default {ytcore.DB_PATH})")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not args.channel and not args.peers:
        ytcore.fail("Serve --channel e/o --peers")
    t0 = time.time()
    today = _dt.date.today()
    conn = ytdb.connect(args.db)
    purge = ytdb.purge_peer_data(conn)
    warnings: list[str] = []
    sections: list[dict] = []
    all_rows: list[dict] = []
    meter = C.Meter(conn, args.channel or "peers", "yt-outliers", args.quota_budget)

    if args.channel:
        try:
            ch, vids, basis, note = own_videos(conn, args.channel, args.basis)
        except LookupError as exc:
            ytcore.fail(str(exc))
        rows, metas = score_channel(vids, args=args, today=today, basis=basis)
        note = age_note(basis, args.age_adjust)
        src = ch.get("source")
        if src == "ytdlp":
            note += " Inventario Tier 0 (yt-dlp): views pubbliche al momento della raccolta."
        sections.append({"heading": f"{ch['title']} ({ch.get('handle') or ch['id']}) — canale proprio",
                         "note": note, "metas": metas, "rows": sort_rows(rows), "channel_id": ch["id"],
                         "inventory_at": ch.get("inventory_at"), "source": src})
        all_rows += rows

    if args.peers:
        path = Path(args.peers).expanduser()
        if not path.exists():
            ytcore.fail(f"File peers non trovato: {path}")
        lines = read_peers_file(path)
        if len(lines) > args.max_peers:
            warnings.append(f"{len(lines)} peers nel file: elaboro i primi {args.max_peers} (--max-peers)")
            lines = lines[:args.max_peers]
        key = ytauth.api_key() if args.tier >= 1 else None
        yt = C.build_service("youtube", "v3", key=key) if key else None
        if not key:
            warnings.append("Peers via yt-dlp (Tier 0: niente chiave Data API o --tier 0): basso volume, date approssimate")
        fetched_any = False
        for ref_text, lang in lines:
            fresh = None if args.refresh else peer_fresh(conn, ref_text, args.peer_max_age_days)
            try:
                if fresh:
                    channel = fresh
                    log(f"peer {ref_text}: dati del {fresh['fetched_at'][:10]} (freschi)")
                else:
                    if fetched_any and not yt:
                        C.polite_sleep(5, 10)
                    fetched_any = True
                    log(f"peer {ref_text}: scarico ({'Data API' if yt else 'yt-dlp'})")
                    channel = fetch_peer_api(conn, meter, yt, ref_text, lang, args.per_channel) if yt else \
                        fetch_peer_ytdlp(conn, meter, ref_text, lang, args.per_channel)
            except C.YtdlpBlocked as exc:
                warnings.append(f"Interrotto su {ref_text}: {exc}")
                break
            except C.QuotaExceeded as exc:
                warnings.append(f"Quota Data API: {exc}")
                break
            except (C.ApiError, C.YtdlpError, ValueError) as exc:
                warnings.append(f"Peer {ref_text} saltato: {exc}")
                continue
            vids = peer_videos(conn, channel["channel_id"])
            rows, metas = score_channel(vids, args=args, today=today, basis="views")
            sections.append({"heading": f"{channel.get('title')} ({channel.get('handle') or channel['channel_id']}) — peer",
                             "note": age_note("views", args.age_adjust) + (
                                 " Date approssimate (yt-dlp)." if channel.get("source") == "ytdlp" else ""),
                             "metas": metas, "rows": sort_rows(rows), "channel_id": channel["channel_id"],
                             "source": channel.get("source"), "subscribers": channel.get("subscribers")})
            all_rows += rows

    method = {
        "formula": f"outlier_x = views ÷ mediana delle views dei {args.window} video precedenti dello stesso formato "
                   f"(minimo {args.min_baseline}, altrimenti i più vicini)",
        "z": "log_z = (ln(1+v) − mediana ln(1+base)) / (1.4826·MAD), anomalia robusta se ≥ 2",
        "tiers": "≥10x breakout · ≥5x forte · ≥2x notevole · ≤0.5x sotto",
        "age_gate_days": {"long": args.min_age_long, "short": args.min_age_short},
        "derived_metric": True,
    }
    name = ytcore.slugify("-".join(filter(None, [args.channel, Path(args.peers).stem if args.peers else None])))
    json_path = Path(args.json).expanduser() if args.json else OUT_DIR / f"{name}-{today.isoformat()}.json"
    ytcore.write_json(json_path, {"generated": C.utc_now().isoformat(timespec="seconds"), "method": method,
                                  "sections": sections})
    outputs = {"json": str(json_path)}
    if args.md:
        md_path = Path(args.md).expanduser()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_md(name, sections, method))
        outputs["md"] = str(md_path)

    top = sort_rows(all_rows)[:args.top]
    ytcore.emit(True, outputs=outputs, method=method,
                channels=[{"heading": s["heading"], "channel_id": s["channel_id"], "source": s.get("source"),
                           "formats": s["metas"], "note": s["note"]} for s in sections],
                top=[{k: r[k] for k in ("channel", "video_id", "title", "format", "published_at", "age_days", "value",
                                        "basis", "baseline_n", "baseline_median", "outlier_x", "outlier_x_age_adj",
                                        "log_z", "tier", "flags", "vsr")} for r in top],
                quota=meter.summary(), purge=purge, warnings=warnings, elapsed_s=round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
