"""yt-collect — inventario e analytics di un canale YouTube → <studio_dir>/data/yt.db

Livelli di accesso (il comando scende da solo di livello e lo dice in "access.messages"):
  Tier 0  nessuna credenziale → yt-dlp: inventario pubblico (titoli, durate, views,
          capitoli, data esatta per i video lunghi). Basso volume, pause, MAI cookie.
  Tier 1  chiave Data API (<studio_dir>/secrets/api_key) → inventario esatto:
          channels → playlist uploads → videos.list a blocchi di 50 (~21 unità/500 video).
  Tier 2  OAuth sola lettura (yt-auth --channel X) → inventario con privati/non in elenco,
          Analytics API (primi 28 giorni a età fissa, lifetime, fonti di traffico,
          Shorts vs long, retention dei video lunghi) e Reporting API (impressioni + CTR
          thumbnail, CSV giornalieri: solo da lì).

--what (default: tutto ciò che il livello permette):
  inventory   canale + video + snapshot views del giorno
  analytics   analytics_28d, analytics_lifetime, traffic_sources, content_type_split   [Tier 2]
  retention   curva retention + tenuta a 0:30 dei video lunghi                         [Tier 2]
  reporting   nuovi report dei job Reporting (reach → reach_daily, basic → basic_daily) [Tier 2]

Esempi:
  yt-collect --channel esempio
  yt-collect --channel esempio --what inventory --tier 0
  yt-collect --channel esempio --url https://www.youtube.com/@CanaleEsempio     (profilo non ancora creato)
  yt-collect --channel esempio --what analytics,retention --since 2026-06-01
  yt-collect --channel @unaltrocanale --what inventory --no-details

Mai scope di scrittura, mai upload. Quota registrata in quota_log (stdout: "quota").
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import gzip
import io
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytauth  # noqa: E402
import ytcore  # noqa: E402
import ytdb  # noqa: E402
from ytcore import log  # noqa: E402

WHAT_ALL = ["inventory", "analytics", "retention", "reporting"]
REPORTS_DIR = ytcore.DATA / "reports"
SHORT_MAX_S = 180  # Shorts fino a 3 minuti (dal 2024-10-15)

# Metriche Analytics API → colonne del DB
CORE_METRICS = [
    ("views", "views"), ("engagedViews", "engaged_views"),
    ("estimatedMinutesWatched", "minutes_watched"), ("averageViewDuration", "avg_view_duration"),
    ("averageViewPercentage", "avg_view_pct"), ("subscribersGained", "subscribers_gained"),
    ("subscribersLost", "subscribers_lost"), ("likes", "likes"), ("comments", "comments"),
    ("shares", "shares"),
]
CONTENT_TYPE_FORMAT = {"SHORTS": "short", "VIDEO_ON_DEMAND": "long", "LIVE_STREAM": "live"}
# Priorità della fonte del formato: una fonte più debole non sovrascrive una più forte
FORMAT_SOURCE_RANK = {"analytics": 5, "media_type": 4, "tab": 3, "aspect": 2, "heuristic": 1, None: 0}
PRECISION_RANK = {"exact": 3, "day": 2, "approx": 1, None: 0}

CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")


# ═══ Errori ═════════════════════════════════════════════════════════════════
class ApiError(RuntimeError):
    pass


class QuotaExceeded(ApiError):
    pass


class AuthError(ApiError):
    pass


class YtdlpError(RuntimeError):
    pass


class YtdlpBlocked(YtdlpError):
    """YouTube ha limitato le richieste (429 / verifica anti-bot): fermarsi, non insistere."""


# ═══ Utilità ════════════════════════════════════════════════════════════════
def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def polite_sleep(lo: float, hi: float) -> None:
    """Pausa casuale tra richieste yt-dlp (YT_SLEEP_SCALE=0 solo nei test)."""
    scale = float(os.environ.get("YT_SLEEP_SCALE", "1"))
    if scale > 0:
        time.sleep(random.uniform(lo, hi) * scale)


def parse_iso_duration(text: str | None) -> float | None:
    """'PT1H2M3S' → 3723.0 · 'P0D' → 0.0."""
    if not text:
        return None
    m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", text)
    if not m:
        return None
    w, d, h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return w * 604800 + d * 86400 + h * 3600 + mi * 60 + s


def parse_since(text: str | None) -> _dt.date | None:
    """'2026-06-01' oppure '30d' (ultimi 30 giorni)."""
    if not text:
        return None
    m = re.fullmatch(r"(\d+)d", text.strip())
    if m:
        return _dt.date.today() - _dt.timedelta(days=int(m.group(1)))
    return _dt.date.fromisoformat(text.strip()[:10])


def date_of(published_at: str | None) -> _dt.date | None:
    if not published_at:
        return None
    try:
        return _dt.date.fromisoformat(published_at[:10])
    except ValueError:
        return None


def ts_to_iso(ts: float | int | None) -> str | None:
    if ts is None:
        return None
    return _dt.datetime.fromtimestamp(float(ts), _dt.timezone.utc).isoformat(timespec="seconds")


def is_fresh(stamp: str | None, hours: float) -> bool:
    if not stamp:
        return False
    try:
        t = _dt.datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return utc_now() - t < _dt.timedelta(hours=hours)


# ── Capitoli dalla descrizione (regole YouTube: primo a 0:00, ≥3, ciascuno ≥10 s) ──
_TS = r"(\d{1,2}:\d{2}(?::\d{2})?)"
_LEAD = re.compile(rf"^\s*[\(\[]?{_TS}[\)\]]?\s*[-–—:|·•.)]*\s*(.*?)\s*$")
_TRAIL = re.compile(rf"^\s*(.*?)\s*[-–—:|·•(\[]*\s*{_TS}[\)\]]?\s*$")


def parse_chapters(description: str | None) -> list[dict]:
    """Elenco [{t, title}] dai timestamp a inizio (o fine) riga della descrizione."""
    out: list[dict] = []
    for line in (description or "").splitlines():
        m = _LEAD.match(line)
        if m:
            t, title = m.group(1), m.group(2)
        else:
            m = _TRAIL.match(line)
            if not m or not m.group(1):
                continue
            title, t = m.group(1), m.group(2)
        out.append({"t": ytcore.parse_ts(t), "title": title.strip(" -–—:|") or ""})
    # tieni solo la sequenza crescente più lunga che parte da 0 (scarta orari sparsi nel testo)
    if out and out[0]["t"] != 0:
        zero = next((i for i, c in enumerate(out) if c["t"] == 0), None)
        out = out[zero:] if zero is not None else out
    seq: list[dict] = []
    for c in out:
        if not seq or c["t"] > seq[-1]["t"]:
            seq.append(c)
    return seq


def chapters_valid(chapters: list[dict], duration: float | None = None) -> bool:
    if len(chapters) < 3 or chapters[0]["t"] != 0:
        return False
    ts = [c["t"] for c in chapters] + ([duration] if duration else [])
    return all(b - a >= 10 for a, b in zip(ts, ts[1:]))


def classify_format(*, duration: float | None, live: bool = False, aspect: float | None = None,
                    media_type: str | None = None) -> tuple[str, str]:
    """(format, format_source). La Data API non ha un flag Shorts: euristica dichiarata."""
    if media_type in ("short", "shorts"):
        return "short", "media_type"
    if media_type in ("livestream", "live"):
        return "live", "media_type"
    if live:
        return "live", "heuristic"
    if duration is not None and 0 < duration <= SHORT_MAX_S:
        if aspect is not None:
            return ("short", "aspect") if aspect <= 1.0 else ("long", "aspect")
        return "short", "heuristic"
    if media_type == "video":
        return "long", "media_type"
    return "long", "heuristic"


def merge_video(existing: dict | None, new: dict) -> dict:
    """Unisce una riga nuova a quella nel DB senza peggiorare precisione di data e formato."""
    if not existing:
        return new
    out = dict(new)
    if PRECISION_RANK.get(new.get("published_precision")) < PRECISION_RANK.get(existing.get("published_precision")):
        out.pop("published_at", None)
        out.pop("published_precision", None)
    if FORMAT_SOURCE_RANK.get(new.get("format_source")) < FORMAT_SOURCE_RANK.get(existing.get("format_source")):
        out.pop("format", None)
        out.pop("format_source", None)
    return out


# ═══ Canale: profilo → riferimento ═════════════════════════════════════════
def parse_channel_ref(text: str) -> dict:
    """@handle · UC… · URL canale (/@x, /channel/UC…, /c/x, /user/x) → {handle|id, url}."""
    t = text.strip()
    if CHANNEL_ID_RE.match(t):
        return {"id": t, "url": f"https://www.youtube.com/channel/{t}"}
    if t.startswith("@"):
        return {"handle": t, "url": f"https://www.youtube.com/{t}"}
    if "youtube.com" in t or "youtu.be" in t:
        u = urlparse(t if "://" in t else "https://" + t)
        parts = [unquote(p) for p in u.path.split("/") if p]
        if parts and parts[0].startswith("@"):
            return {"handle": parts[0], "url": f"https://www.youtube.com/{parts[0]}"}
        if len(parts) >= 2 and parts[0] == "channel" and CHANNEL_ID_RE.match(parts[1]):
            return {"id": parts[1], "url": f"https://www.youtube.com/channel/{parts[1]}"}
        if len(parts) >= 2 and parts[0] in ("c", "user"):
            return {"legacy": parts[1], "url": f"https://www.youtube.com/{parts[0]}/{parts[1]}"}
    raise ValueError(f"Riferimento canale non riconosciuto: {text!r} (usa @handle, UC… o l'URL del canale)")


def resolve_channel(arg: str, url: str | None = None) -> dict:
    """Profilo canale (<slug>.md nei channels_dirs) oppure riferimento diretto."""
    profile = None
    try:
        profile = ytcore.load_channel(arg)
    except FileNotFoundError:
        pass
    except Exception as exc:  # frontmatter rotto: meglio dirlo che ignorarlo
        raise ValueError(f"Profilo canale {arg!r} illeggibile: {exc}") from exc
    slug = arg if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", arg) else None
    ref: dict = {}
    if url:
        ref = parse_channel_ref(url)
    elif profile:
        ch = profile.get("channel")
        cand: list[str] = []
        if isinstance(ch, dict):
            cand += [ch.get("id"), ch.get("handle"), ch.get("url")]
        elif isinstance(ch, str):
            cand.append(ch)
        cand += [profile.get("channel_id"), profile.get("handle"), profile.get("youtube"), profile.get("url")]
        for c in cand:
            if not c or not isinstance(c, str) or "…" in c or "..." in c:
                continue  # segnaposto del template
            try:
                r = parse_channel_ref(c)
            except ValueError:
                continue
            for k, v in r.items():
                ref.setdefault(k, v)
        if not ref:
            raise ValueError(f"Il profilo {arg!r} non ha un canale YouTube valido (campo channel: {{handle, id}}). "
                             "Usa --url https://www.youtube.com/@handle")
    else:
        ref = parse_channel_ref(arg)
    return {
        "slug": slug, "profile_found": profile is not None,
        "language": (profile or {}).get("language") or "it",
        "kind": (profile or {}).get("kind") or "own",
        **ref,
    }


# ═══ Accesso (tier) ═════════════════════════════════════════════════════════
def detect_access(slug: str | None, max_tier: int = 2) -> dict:
    acc: dict[str, Any] = {"tier": 0, "api_key": None, "creds": None, "messages": [],
                           "ytdlp": bool(ytcore.which(ytcore.YTDLP))}
    if not acc["ytdlp"]:
        acc["messages"].append(f"Tier 0 non disponibile: yt-dlp mancante ({ytcore.YTDLP})")
    if max_tier >= 1:
        key = ytauth.api_key()
        if key:
            acc["api_key"] = key
            acc["tier"] = 1
        else:
            acc["messages"].append("Tier 1 non disponibile: manca la chiave Data API "
                                   f"({ytauth.SECRETS / 'api_key'} o YT_API_KEY). Vedi {ytcore.DOCS / 'SETUP-GOOGLE.md'}")
    if max_tier >= 2:
        if not slug:
            acc["messages"].append("Tier 2 non disponibile: serve lo slug del canale (es. --channel esempio) per il token OAuth")
        elif not ytauth.token_path(slug).exists():
            acc["messages"].append(f"Tier 2 non disponibile: esegui yt-auth --channel {slug}")
        else:
            try:
                acc["creds"] = ytauth.load_credentials(slug)
                acc["tier"] = 2
            except SystemExit as exc:
                acc["messages"].append(f"Tier 2 non disponibile: {exc}")
            except Exception as exc:  # RefreshError, token corrotto…
                acc["messages"].append(f"Tier 2 non disponibile: token non rinnovabile ({exc}). "
                                       f"Esegui yt-auth --channel {slug}")
    return acc


def build_service(name: str, version: str, *, creds=None, key: str | None = None):
    """Client Google API (sostituito dai mock nei test)."""
    from googleapiclient.discovery import build

    return build(name, version, credentials=creds, developerKey=None if creds else key, cache_discovery=False)


def download_report(creds, url: str) -> bytes:
    """Scarica un report Reporting API con la sessione OAuth (sostituito dai mock nei test)."""
    from google.auth.transport.requests import AuthorizedSession

    resp = AuthorizedSession(creds).get(url, timeout=180)
    if resp.status_code != 200:
        raise ApiError(f"Download report fallito ({resp.status_code}): {resp.text[:200]}")
    return resp.content


# ═══ Quota ══════════════════════════════════════════════════════════════════
class Meter:
    """Esegue le richieste API contando unità (Data API) e chiamate (Analytics/Reporting)."""

    def __init__(self, conn, channel: str | None, command: str, data_budget: int = 5000):
        self.conn, self.channel, self.command = conn, channel, command
        self.units: Counter = Counter()
        self.calls: Counter = Counter()
        self.data_budget = data_budget
        self.data_used_before = ytdb.quota_used_today(conn, "data") if conn is not None else 0

    def execute(self, request, api: str, method: str, units: int = 1) -> dict:
        if api == "data" and self.data_used_before + self.units["data"] + units > self.data_budget:
            raise QuotaExceeded(f"Budget giornaliero Data API raggiunto ({self.data_budget} unità, "
                                "modificabile con --quota-budget)")
        try:
            resp = request.execute(num_retries=2)
        except Exception as exc:
            self._record(api, method, units)  # anche le chiamate fallite consumano quota
            raise classify_http_error(exc, api, method) from exc
        self._record(api, method, units)
        return resp

    def ytdlp(self, method: str, n: int = 1) -> None:
        self._record("ytdlp", method, n)

    def _record(self, api: str, method: str, units: int) -> None:
        self.units[api] += units
        self.calls[f"{api}:{method}"] += 1
        if self.conn is not None:
            ytdb.log_quota(self.conn, api, method, units, self.channel, self.command)

    def summary(self) -> dict:
        return {
            "data_api_units": self.units["data"],
            "data_api_units_today_total": self.data_used_before + self.units["data"],
            "analytics_queries": self.units["analytics"],
            "reporting_calls": self.units["reporting"],
            "ytdlp_requests": self.units["ytdlp"],
            "calls": dict(self.calls),
        }


def classify_http_error(exc: Exception, api: str, method: str) -> Exception:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:  # pragma: no cover
        HttpError = ()  # type: ignore
    if not isinstance(exc, HttpError):
        return ApiError(f"{api}:{method} fallita: {exc}")
    status = getattr(exc.resp, "status", None)
    reason, message = "", str(exc)
    try:
        body = json.loads(exc.content.decode("utf-8", "replace"))
        err = body.get("error", {})
        message = err.get("message", message)
        reason = (err.get("errors") or [{}])[0].get("reason", "") or err.get("status", "")
    except Exception:
        pass
    text = f"{api}:{method} → HTTP {status} {reason}: {message}"
    if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"):
        return QuotaExceeded(text)
    if status == 401 or reason in ("authError", "insufficientPermissions", "forbidden", "PERMISSION_DENIED",
                                   "UNAUTHENTICATED"):
        return AuthError(text)
    return ApiError(text)


def paginate(meter: Meter, make_request: Callable[[str | None], Any], items_key: str, api: str, method: str,
             limit: int | None = None) -> list[dict]:
    out: list[dict] = []
    token = None
    while True:
        resp = meter.execute(make_request(token), api, method, 1)
        out.extend(resp.get(items_key, []) or [])
        token = resp.get("nextPageToken")
        if not token or (limit and len(out) >= limit):
            return out[:limit] if limit else out


# ═══ Tier 0: yt-dlp (pubblico, basso volume, niente cookie) ═════════════════
# Flag sempre presenti: niente config utente (potrebbe contenere cookie), niente cookie,
# niente componenti remoti, pausa tra le richieste.
YTDLP_SAFE = ["--ignore-config", "--no-cookies", "--no-cookies-from-browser", "--no-remote-components",
              "--sleep-requests", "1"]
YTDLP_FORBIDDEN = ("--cookies", "--cookies-from-browser", "--remote-components", "--username", "--password",
                   "--netrc", "--ap-")


def ytdlp_guard(args: Iterable[str]) -> None:
    for a in args:
        if any(a == f or a.startswith(f + "=") or (f.endswith("-") and a.startswith(f)) for f in YTDLP_FORBIDDEN):
            raise YtdlpError(f"Flag yt-dlp vietato dal guardrail: {a}")


def ytdlp_json(args: list[str], timeout: int = 240) -> dict | None:
    """Esegue yt-dlp -J. None se la scheda richiesta non esiste (es. canale senza Shorts)."""
    ytdlp_guard(args)
    try:
        proc = ytcore.run([ytcore.YTDLP, *YTDLP_SAFE, *args], check=False, capture=True)
    except FileNotFoundError as exc:
        raise YtdlpError(f"yt-dlp non trovato: {exc}") from exc
    err = proc.stderr or ""
    if proc.returncode != 0:
        if re.search(r"does not have an? \w+ tab", err):
            return None
        if re.search(r"HTTP Error 429|Too Many Requests|Sign in to confirm|rate-limit|confirm you.re not a bot", err):
            raise YtdlpBlocked("YouTube sta limitando le richieste (429/verifica anti-bot): riprova più tardi")
        tail = " | ".join(l for l in err.strip().splitlines()[-3:])
        raise YtdlpError(f"yt-dlp fallito ({proc.returncode}): {tail}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise YtdlpError(f"Output yt-dlp non JSON: {exc}") from exc


def ytdlp_tab(base_url: str, tab: str, *, lang: str | None = None, approx_dates: bool = False,
              limit: int | None = None) -> dict | None:
    """Scheda canale piatta (--flat-playlist). Titoli nella lingua `lang` (YouTube traduce i titoli
    nella lingua dell'interfaccia); le date approssimate funzionano solo in inglese."""
    args = ["--flat-playlist", "-J"]
    if approx_dates:
        args += ["--extractor-args", "youtubetab:approximate_date"]
    elif lang and lang != "en":
        args += ["--extractor-args", f"youtube:lang={lang}"]
    if limit:
        args += ["--playlist-end", str(int(limit))]
    return ytdlp_json(args + [f"{base_url.rstrip('/')}/{tab}"])


def ytdlp_video(video_id: str) -> dict:
    """Estrazione completa di un video senza scaricarlo (titolo originale, data esatta, capitoli)."""
    info = ytdlp_json(["--skip-download", "--no-playlist", "-J", f"https://www.youtube.com/watch?v={video_id}"])
    if not info:
        raise YtdlpError(f"Nessun metadato per {video_id}")
    return info


def flat_entries(data: dict | None) -> list[dict]:
    if not data:
        return []
    return [e for e in (data.get("entries") or []) if e and e.get("id") and VIDEO_ID_RE.match(e["id"])]


def ytdlp_detail_row(info: dict) -> dict:
    """Riga `videos` dai metadati completi yt-dlp."""
    desc = info.get("description") or ""
    duration = info.get("duration")
    ch_desc = parse_chapters(desc)
    ch_ytdlp = [{"t": float(c.get("start_time") or 0), "title": c.get("title") or ""} for c in (info.get("chapters") or [])]
    chapters = ch_ytdlp or ch_desc
    source = "description" if len(ch_desc) >= 2 else ("auto" if ch_ytdlp else "none")
    live = info.get("live_status") in ("is_live", "was_live", "post_live", "is_upcoming")
    fmt, fsrc = classify_format(duration=duration, live=live, aspect=info.get("aspect_ratio"),
                                media_type=info.get("media_type"))
    if info.get("timestamp"):
        pub, prec = ts_to_iso(info["timestamp"]), "exact"
    elif info.get("upload_date"):
        u = info["upload_date"]
        pub, prec = f"{u[:4]}-{u[4:6]}-{u[6:8]}", "day"
    else:
        pub, prec = None, None
    avail = info.get("availability")
    return {
        "id": info["id"], "title": info.get("title"), "published_at": pub, "published_precision": prec,
        "duration": duration, "format": fmt, "format_source": fsrc,
        "privacy": avail if avail in ("public", "unlisted", "private") else None,
        "has_chapters": int(bool(chapters)), "chapters_valid": int(chapters_valid(chapters, duration)),
        "chapters_source": source, "chapters_json": chapters,
        "description": desc, "tags_json": info.get("tags") or [], "thumbnail_url": info.get("thumbnail"),
        "aspect_ratio": info.get("aspect_ratio"),
        "views": info.get("view_count"), "likes": info.get("like_count"), "comments": info.get("comment_count"),
        "details_at": utc_now().isoformat(timespec="seconds"),
        "_followers": info.get("channel_follower_count"), "_channel_id": info.get("channel_id"),
    }


def ytdlp_podcast_ids(base_url: str, meter: Meter, lang: str | None) -> set[str] | None:
    """Video nelle playlist designate come podcast (scheda /podcasts). None se non verificabile."""
    try:
        data = ytdlp_tab(base_url, "podcasts", lang=lang)
        meter.ytdlp("tab:podcasts")
    except YtdlpBlocked:
        raise
    except YtdlpError as exc:
        log(f"  scheda podcasts non leggibile: {exc}")
        return None
    if data is None:
        return set()
    ids: set[str] = set()
    for e in (data.get("entries") or [])[:3]:
        pl = e.get("id")
        if not pl or not str(pl).startswith("PL"):
            continue
        polite_sleep(2, 4)
        try:
            items = ytdlp_json(["--flat-playlist", "-J", f"https://www.youtube.com/playlist?list={pl}"])
            meter.ytdlp("playlist:podcast")
        except YtdlpBlocked:
            raise
        except YtdlpError as exc:
            log(f"  playlist podcast {pl} non leggibile: {exc}")
            return None
        ids |= {x["id"] for x in flat_entries(items)}
    return ids


def ytdlp_channel_listing(base_url: str, meter: Meter, *, lang: str | None, limit: int | None = None,
                          tabs: Iterable[tuple[str, str]] = (("videos", "long"), ("shorts", "short"),
                                                             ("streams", "live")),
                          approx_dates: bool = True) -> dict:
    """Schede canale → {meta, rows{id: row}}. Con approx_dates aggiunge una seconda richiesta in
    inglese per le date approssimate quando i titoli sono chiesti in un'altra lingua."""
    meta: dict = {}
    rows: dict[str, dict] = {}
    first = True
    for tab, fmt in tabs:
        if not first:
            polite_sleep(2, 4)
        first = False
        data = ytdlp_tab(base_url, tab, lang=lang, limit=limit, approx_dates=(lang in (None, "en")))
        meter.ytdlp(f"tab:{tab}")
        if data is None:
            log(f"  scheda /{tab}: assente")
            continue
        for k in ("channel_id", "channel", "uploader_id", "channel_url", "description"):
            if data.get(k) and not meta.get(k):
                meta[k] = data[k]
        if data.get("channel_follower_count"):
            meta["channel_follower_count"] = data["channel_follower_count"]
        entries = flat_entries(data)
        log(f"  scheda /{tab}: {len(entries)} video")
        for pos, e in enumerate(entries):
            row = {"id": e["id"], "title": e.get("title"), "duration": e.get("duration"),
                   "views": e.get("view_count"), "format": fmt, "format_source": "tab", "position": pos,
                   "_tab": tab}
            if e.get("timestamp"):
                row.update(published_at=ts_to_iso(e["timestamp"]), published_precision="approx")
            rows.setdefault(e["id"], row)
    if approx_dates and lang not in (None, "en"):
        rows_tabs = sorted({r["_tab"] for r in rows.values()})
        for tab in rows_tabs:
            polite_sleep(2, 4)
            data = ytdlp_tab(base_url, tab, approx_dates=True, limit=limit)
            meter.ytdlp(f"tab:{tab}:dates")
            for e in flat_entries(data):
                if e["id"] in rows and e.get("timestamp"):
                    rows[e["id"]].update(published_at=ts_to_iso(e["timestamp"]), published_precision="approx")
            if data and data.get("channel_follower_count"):
                meta["channel_follower_count"] = data["channel_follower_count"]
    return {"meta": meta, "rows": rows}


# ═══ Tier 1/2: Data API v3 ══════════════════════════════════════════════════
VIDEO_PARTS = "snippet,contentDetails,statistics,status,liveStreamingDetails,player"


def api_channel(yt, meter: Meter, ref: dict, *, mine: bool = False) -> dict:
    part = "snippet,contentDetails,statistics,status"
    if mine:
        req = yt.channels().list(part=part, mine=True)
    elif ref.get("id"):
        req = yt.channels().list(part=part, id=ref["id"])
    elif ref.get("handle"):
        req = yt.channels().list(part=part, forHandle=ref["handle"])
    elif ref.get("legacy"):
        req = yt.channels().list(part=part, forUsername=ref["legacy"])
    else:
        raise ApiError("Canale senza id/handle")
    items = meter.execute(req, "data", "channels.list").get("items") or []
    if not items:
        raise ApiError(f"Canale non trovato via Data API: {ref}")
    return items[0]


def api_upload_ids(yt, meter: Meter, playlist_id: str, limit: int | None = None) -> list[str]:
    def make(token):
        kw = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if token:
            kw["pageToken"] = token
        return yt.playlistItems().list(**kw)
    items = paginate(meter, make, "items", "data", "playlistItems.list", limit=limit)
    return [i["contentDetails"]["videoId"] for i in items if i.get("contentDetails", {}).get("videoId")]


def api_videos(yt, meter: Meter, ids: list[str]) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        # niente maxResults insieme a id (non supportato); maxWidth fa tornare embedWidth/Height
        req = yt.videos().list(part=VIDEO_PARTS, id=",".join(batch), maxWidth=640)
        out.extend(meter.execute(req, "data", "videos.list").get("items") or [])
    return out


def api_video_row(item: dict) -> dict:
    sn, cd, st, ss = (item.get(k, {}) or {} for k in ("snippet", "contentDetails", "statistics", "status"))
    pl = item.get("player") or {}
    duration = parse_iso_duration(cd.get("duration"))
    aspect = None
    if pl.get("embedWidth") and pl.get("embedHeight"):
        try:
            aspect = round(float(pl["embedWidth"]) / float(pl["embedHeight"]), 3)
        except (TypeError, ValueError, ZeroDivisionError):
            aspect = None
    live = bool(item.get("liveStreamingDetails")) or sn.get("liveBroadcastContent") in ("live", "upcoming")
    fmt, fsrc = classify_format(duration=duration, live=live, aspect=aspect)
    desc = sn.get("description") or ""
    chapters = parse_chapters(desc)
    thumbs = sn.get("thumbnails") or {}
    thumb = next((thumbs[k]["url"] for k in ("maxres", "standard", "high", "medium", "default") if k in thumbs), None)

    def _int(v):
        return int(v) if v not in (None, "") else None

    return {
        "id": item["id"], "channel_id": sn.get("channelId"), "title": sn.get("title"),
        "published_at": sn.get("publishedAt"), "published_precision": "exact" if sn.get("publishedAt") else None,
        "duration": duration, "format": fmt, "format_source": fsrc, "privacy": ss.get("privacyStatus"),
        "has_chapters": int(len(chapters) >= 2), "chapters_valid": int(chapters_valid(chapters, duration)),
        "chapters_source": "description" if len(chapters) >= 2 else "none", "chapters_json": chapters,
        "description": desc, "tags_json": sn.get("tags") or [], "thumbnail_url": thumb, "aspect_ratio": aspect,
        "views": _int(st.get("viewCount")), "likes": _int(st.get("likeCount")), "comments": _int(st.get("commentCount")),
    }


def api_podcast_ids(yt, meter: Meter, channel_id: str, mine: bool = False) -> set[str] | None:
    """Video nelle playlist con status.podcastStatus == enabled."""
    try:
        def make(token):
            kw = {"part": "snippet,status", "maxResults": 50}
            kw.update({"mine": True} if mine else {"channelId": channel_id})
            if token:
                kw["pageToken"] = token
            return yt.playlists().list(**kw)
        pls = paginate(meter, make, "items", "data", "playlists.list", limit=200)
        ids: set[str] = set()
        for p in pls:
            if (p.get("status") or {}).get("podcastStatus") == "enabled":
                ids |= set(api_upload_ids(yt, meter, p["id"]))
        return ids
    except QuotaExceeded:
        raise
    except ApiError as exc:
        log(f"  playlist podcast non leggibili: {exc}")
        return None


# ═══ Inventario ═════════════════════════════════════════════════════════════
def existing_videos(conn, channel_id: str | None) -> dict[str, dict]:
    if not channel_id:
        return {}
    return {r["id"]: r for r in ytdb.rows(conn, "SELECT * FROM videos WHERE channel_id=?", (channel_id,))}


def save_inventory(conn, channel: dict, videos: list[dict], *, source: str, tier: int,
                   podcast_ids: set[str] | None, complete: bool = True) -> None:
    now = utc_now().isoformat(timespec="seconds")
    day = ytdb.today_iso()
    with conn:
        if channel.get("slug"):
            conn.execute("UPDATE channels SET slug=NULL WHERE slug=? AND id<>?", (channel["slug"], channel["id"]))
        ytdb.upsert(conn, "channels", {**channel, "source": source, "tier": tier, "updated_at": now,
                                       "inventory_at": now if complete else None}, ["id"])
        old = existing_videos(conn, channel["id"])
        for v in videos:
            row = {k: val for k, val in v.items() if not k.startswith("_")}
            row["channel_id"] = channel["id"]
            if podcast_ids is not None:
                row["is_podcast"] = int(row["id"] in podcast_ids)
            row = merge_video(old.get(row["id"]), row)
            row.update(source=source, last_seen=now, updated_at=now, first_seen=now)
            if row.get("views") is not None:
                row["stats_at"] = now
            ytdb.upsert(conn, "videos", row, ["id"])
            # first_seen resta quello del primo inventario
            if row["id"] in old:
                conn.execute("UPDATE videos SET first_seen=? WHERE id=?", (old[row["id"]]["first_seen"], row["id"]))
            if v.get("views") is not None:
                ytdb.replace(conn, "video_stats_daily", {"video_id": v["id"], "date": day, "views": v.get("views"),
                                                         "likes": v.get("likes"), "comments": v.get("comments"),
                                                         "source": source, "fetched_at": now})


def inventory_ytdlp(conn, meter: Meter, ch: dict, args) -> dict:
    """Tier 0: schede pubbliche + dettagli per video (capitoli, data esatta), basso volume."""
    base = ch.get("url")
    if not base:
        raise YtdlpError("URL canale mancante")
    lang = ch.get("language") or "it"
    log(f"Tier 0 (yt-dlp) su {base} — lingua titoli: {lang}")
    listing = ytdlp_channel_listing(base, meter, lang=lang, approx_dates=False)
    meta, rows = listing["meta"], listing["rows"]
    if not meta.get("channel_id"):
        raise YtdlpError("Canale non trovato o senza video pubblici")
    channel_id = meta["channel_id"]
    old = existing_videos(conn, channel_id)
    warnings: list[str] = []

    podcast_ids = None
    if not args.no_podcasts:
        polite_sleep(2, 4)
        try:
            podcast_ids = ytdlp_podcast_ids(base, meter, lang)
        except YtdlpBlocked as exc:
            warnings.append(f"Playlist podcast non lette: {exc}")

    # Dettagli (capitoli, data esatta, like): prima i video lunghi/live, poi gli Shorts
    followers = meta.get("channel_follower_count")
    if not args.no_details:
        order = sorted(rows.values(), key=lambda r: ({"long": 0, "live": 1, "short": 2}.get(r["format"], 3), r["position"]))
        todo = [r for r in order
                if args.force or not is_fresh((old.get(r["id"]) or {}).get("details_at"), args.details_ttl_days * 24)]
        todo = todo[:args.details_max]
        skipped = len(rows) - len(todo)
        log(f"  dettagli: {len(todo)} video da estrarre ({skipped} già freschi o oltre il limite --details-max)")
        for i, r in enumerate(todo):
            if i:
                polite_sleep(5, 10)
            try:
                info = ytdlp_video(r["id"])
                meter.ytdlp("video")
            except YtdlpBlocked as exc:
                warnings.append(f"Dettagli interrotti dopo {i} video: {exc}")
                break
            except YtdlpError as exc:
                warnings.append(f"Dettagli non letti per {r['id']}: {exc}")
                continue
            det = ytdlp_detail_row(info)
            followers = det.pop("_followers", None) or followers
            det.pop("_channel_id", None)
            # il formato della scheda (/shorts, /streams) vale più dell'euristica
            if FORMAT_SOURCE_RANK[det["format_source"]] < FORMAT_SOURCE_RANK["tab"]:
                det.pop("format"), det.pop("format_source")
            rows[r["id"]].update({k: v for k, v in det.items() if v is not None or k in ("format",)})

    # Date mancanti (né dettagli né DB) → una richiesta in inglese per le date approssimate
    missing_tabs = sorted({r["_tab"] for r in rows.values()
                           if not r.get("published_at") and not (old.get(r["id"]) or {}).get("published_at")})
    for tab in missing_tabs:
        polite_sleep(2, 4)
        try:
            data = ytdlp_tab(base, tab, approx_dates=True)
            meter.ytdlp(f"tab:{tab}:dates")
        except YtdlpError as exc:
            warnings.append(f"Date approssimate non lette per /{tab}: {exc}")
            continue
        for e in flat_entries(data):
            r = rows.get(e["id"])
            if r and not r.get("published_at") and e.get("timestamp"):
                r.update(published_at=ts_to_iso(e["timestamp"]), published_precision="approx")
        followers = followers or (data or {}).get("channel_follower_count")

    handle = meta.get("uploader_id") if str(meta.get("uploader_id", "")).startswith("@") else ch.get("handle")
    channel = {"id": channel_id, "slug": ch.get("slug"), "handle": handle, "title": meta.get("channel"),
               "url": f"https://www.youtube.com/{handle}" if handle else meta.get("channel_url"),
               "kind": ch.get("kind"), "language": lang, "subscribers": followers, "video_count": len(rows)}
    save_inventory(conn, channel, list(rows.values()), source="ytdlp", tier=0, podcast_ids=podcast_ids)
    return {"channel": channel, "source": "ytdlp", "tier": 0, "warnings": warnings,
            "podcast_checked": podcast_ids is not None}


def inventory_api(conn, meter: Meter, ch: dict, acc: dict, args) -> dict:
    """Tier 1 (chiave) o Tier 2 (OAuth: include privati e non in elenco)."""
    use_oauth = acc.get("creds") is not None and args.tier >= 2
    yt = build_service("youtube", "v3", creds=acc["creds"] if use_oauth else None, key=acc.get("api_key"))
    warnings: list[str] = []
    item = api_channel(yt, meter, ch, mine=use_oauth)
    if use_oauth and ch.get("id") and item["id"] != ch["id"]:
        warnings.append(f"Il token OAuth di '{ch.get('slug')}' è del canale {item['id']} "
                        f"({item['snippet'].get('title')}), non di {ch['id']}: uso i dati pubblici")
        use_oauth = False
        item = api_channel(yt, meter, ch)
    sn, cd, st = item.get("snippet", {}), item.get("contentDetails", {}), item.get("statistics", {})
    uploads = (cd.get("relatedPlaylists") or {}).get("uploads")
    ids = api_upload_ids(yt, meter, uploads, limit=args.max_videos) if uploads else []
    items = api_videos(yt, meter, ids)
    rows = [api_video_row(i) for i in items]
    podcast_ids = None if args.no_podcasts else api_podcast_ids(yt, meter, item["id"], mine=use_oauth)
    hidden = None if st.get("hiddenSubscriberCount") else (int(st["subscriberCount"]) if st.get("subscriberCount") else None)
    channel = {"id": item["id"], "slug": ch.get("slug"), "handle": sn.get("customUrl") and (
                   sn["customUrl"] if sn["customUrl"].startswith("@") else "@" + sn["customUrl"]) or ch.get("handle"),
               "title": sn.get("title"), "url": ch.get("url"), "kind": ch.get("kind"),
               "language": ch.get("language"), "subscribers": hidden,
               "video_count": int(st["videoCount"]) if st.get("videoCount") else None,
               "view_count": int(st["viewCount"]) if st.get("viewCount") else None,
               "uploads_playlist": uploads, "published_at": sn.get("publishedAt")}
    source = "oauth" if use_oauth else "api"
    tier = 2 if use_oauth else 1
    save_inventory(conn, channel, rows, source=source, tier=tier, podcast_ids=podcast_ids,
                   complete=args.max_videos is None)
    return {"channel": channel, "source": source, "tier": tier, "warnings": warnings,
            "podcast_checked": podcast_ids is not None}


def known_channel(conn, ch: dict) -> dict | None:
    """Canale già in archivio (per slug, id o handle)."""
    for ref in (ch.get("slug"), ch.get("id"), ch.get("handle")):
        if ref:
            found = ytdb.find_channel(conn, ref)
            if found:
                return found
    return None


def vids_inventory_at(conn, channel_id: str) -> str | None:
    r = conn.execute("SELECT inventory_at FROM channels WHERE id=?", (channel_id,)).fetchone()
    return r[0] if r else None


def inventory_summary(conn, channel_id: str, list_max: int) -> dict:
    vids = ytdb.rows(conn, "SELECT * FROM videos WHERE channel_id=? ORDER BY published_at DESC, position ASC",
                     (channel_id,))
    by_fmt = Counter(v["format"] for v in vids)
    return {
        "videos": len(vids),
        "by_format": dict(by_fmt),
        "with_chapters": sum(1 for v in vids if v["has_chapters"]),
        "chapters_valid": sum(1 for v in vids if v["chapters_valid"]),
        "podcast": sum(1 for v in vids if v["is_podcast"] == 1),
        "privacy": dict(Counter(v["privacy"] or "public?" for v in vids)),
        # in archivio ma non visti nell'ultimo inventario: cancellati, privati o non pubblici a Tier 0
        "not_seen_last_inventory": [v["id"] for v in vids if v["last_seen"] and v["last_seen"] < (
            vids_inventory_at(conn, channel_id) or v["last_seen"])],
        "list": [{"id": v["id"], "title": v["title"], "format": v["format"],
                  "format_source": v["format_source"], "duration": v["duration"],
                  "published_at": v["published_at"], "precision": v["published_precision"],
                  "views": v["views"], "likes": v["likes"], "has_chapters": bool(v["has_chapters"]),
                  "chapters": len(json.loads(v["chapters_json"])) if v["chapters_json"] else 0,
                  "chapters_valid": bool(v["chapters_valid"]), "chapters_source": v["chapters_source"],
                  "is_podcast": v["is_podcast"], "privacy": v["privacy"]}
                 for v in vids[:list_max]],
    }


# ═══ Tier 2: Analytics API ══════════════════════════════════════════════════
def table(resp: dict) -> list[dict]:
    heads = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(heads, r)) for r in resp.get("rows", []) or []]


class Analytics:
    """reports.query con ripiego automatico se una metrica/dimensione non è supportata."""

    def __init__(self, yta, meter: Meter):
        self.yta, self.meter = yta, meter
        self.engaged_ok = True   # engagedViews accettata dall'API (metrica recente)
        self.ctype_ok = True     # dimensione creatorContentType accettata per singolo video

    def query(self, **params) -> list[dict]:
        params = {k: v for k, v in params.items() if v is not None}
        return table(self.meter.execute(self.yta.reports().query(ids="channel==MINE", **params),
                                        "analytics", "reports.query"))

    def core(self, *, start: str, end: str, filters: str | None = None, dimensions: str | None = None) -> list[dict]:
        """Metriche principali. Se l'API rifiuta engagedViews riprova senza e lo ricorda per la sessione."""
        for eng in ([True, False] if self.engaged_ok else [False]):
            metrics = ",".join(m for m, _ in CORE_METRICS if eng or m != "engagedViews")
            try:
                rows = self.query(startDate=start, endDate=end, metrics=metrics, dimensions=dimensions, filters=filters)
            except (QuotaExceeded, AuthError):
                raise
            except ApiError as exc:
                if not eng or "HTTP 400" not in str(exc):
                    raise
                log(f"  Analytics: engagedViews rifiutata, riprovo senza ({str(exc)[:140]})")
                continue
            if not eng:
                self.engaged_ok = False
            return rows
        raise ApiError("reports.query fallita")  # pragma: no cover

    def content_type(self, *, start: str, end: str, filters: str) -> str | None:
        """creatorContentType del video (SHORTS | VIDEO_ON_DEMAND | LIVE_STREAM): il formato vero."""
        if not self.ctype_ok:
            return None
        try:
            rows = self.query(startDate=start, endDate=end, metrics="views", dimensions="creatorContentType",
                              filters=filters)
        except (QuotaExceeded, AuthError):
            raise
        except ApiError as exc:
            self.ctype_ok = False
            log(f"  Analytics: creatorContentType per video non disponibile ({str(exc)[:140]})")
            return None
        if not rows:
            return None
        return max(rows, key=lambda r: float(r.get("views") or 0)).get("creatorContentType")


def metrics_row(r: dict) -> dict:
    out = {}
    for api_name, col in CORE_METRICS:
        if api_name in r and r[api_name] is not None:
            out[col] = r[api_name]
    return out


def sum_rows(rows: list[dict]) -> dict:
    """Somma più righe (es. una per creatorContentType); medie pesate per le views."""
    if len(rows) == 1:
        return metrics_row(rows[0])
    tot: dict = defaultdict(float)
    views = sum(float(r.get("views") or 0) for r in rows)
    for r in rows:
        m = metrics_row(r)
        for k, v in m.items():
            if k in ("avg_view_duration", "avg_view_pct"):
                tot[k] += float(v) * float(r.get("views") or 0)
            else:
                tot[k] += float(v)
    for k in ("avg_view_duration", "avg_view_pct"):
        if k in tot:
            tot[k] = tot[k] / views if views else None
    return {k: (int(v) if k not in ("minutes_watched", "avg_view_duration", "avg_view_pct") and v is not None else v)
            for k, v in tot.items()}


def analytics_videos(conn, channel_id: str, since: _dt.date | None, formats: Iterable[str],
                     max_videos: int | None) -> list[dict]:
    vids = ytdb.rows(conn, "SELECT * FROM videos WHERE channel_id=? AND published_at IS NOT NULL "
                           "AND COALESCE(privacy,'public')<>'private' ORDER BY published_at DESC", (channel_id,))
    out = [v for v in vids if v["format"] in formats and (not since or (date_of(v["published_at"]) or since) >= since)]
    return out[:max_videos] if max_videos else out


def collect_analytics(conn, meter: Meter, acc: dict, channel: dict, args, since) -> dict:
    yta = build_service("youtubeAnalytics", "v2", creds=acc["creds"])
    an = Analytics(yta, meter)
    today = _dt.date.today()
    now = utc_now().isoformat(timespec="seconds")
    cid = channel["id"]
    res = {"videos": 0, "lifetime_updated": 0, "d28_updated": 0, "d28_complete": 0, "traffic_updated": 0,
           "format_fixed": 0, "skipped_fresh": 0, "warnings": []}
    for v in analytics_videos(conn, cid, since, ("long", "short", "live"), args.max_videos):
        res["videos"] += 1
        try:
            _analytics_one(conn, an, v, cid, today, now, args, res)
        except (QuotaExceeded, AuthError):
            raise
        except ApiError as exc:
            res["warnings"].append(f"Analytics non lette per {v['id']}: {exc}")
    _analytics_channel(conn, an, channel, today, now, res)
    res["engaged_views_supported"] = an.engaged_ok
    res["content_type_dimension_supported"] = an.ctype_ok
    return res


def _analytics_one(conn, an: "Analytics", v: dict, cid: str, today: _dt.date, now: str, args, res: dict) -> None:
    """Lifetime (+ tipo di contenuto), primi 28 giorni e fonti di traffico di un video."""
    pub = date_of(v["published_at"])
    vid = v["id"]
    filt = f"video=={vid}"
    # Lifetime + tipo di contenuto
    life = conn.execute("SELECT fetched_at FROM analytics_lifetime WHERE video_id=?", (vid,)).fetchone()
    if args.force or not (life and is_fresh(life[0], args.fresh_hours)):
        rows = an.core(start=pub.isoformat(), end=today.isoformat(), filters=filt)
        ctype = an.content_type(start=pub.isoformat(), end=today.isoformat(), filters=filt)
        with conn:
            ytdb.replace(conn, "analytics_lifetime", {"video_id": vid, "channel_id": cid,
                         "start_date": pub.isoformat(), "end_date": today.isoformat(),
                         "content_type": ctype, **sum_rows(rows), "fetched_at": now})
            fmt = CONTENT_TYPE_FORMAT.get(ctype or "")
            if fmt:
                if fmt != v["format"]:
                    res["format_fixed"] += 1
                conn.execute("UPDATE videos SET format=?, format_source='analytics' WHERE id=?", (fmt, vid))
        res["lifetime_updated"] += 1
    else:
        res["skipped_fresh"] += 1
    # Primi 28 giorni (età fissa): si rifà solo finché la finestra non è chiusa
    d28 = conn.execute("SELECT complete FROM analytics_28d WHERE video_id=?", (vid,)).fetchone()
    if args.force or not (d28 and d28[0] == 1):
        end28 = pub + _dt.timedelta(days=27)
        complete = end28 <= today - _dt.timedelta(days=2)
        rows = an.core(start=pub.isoformat(), end=min(end28, today).isoformat(), filters=filt)
        with conn:
            ytdb.replace(conn, "analytics_28d", {"video_id": vid, "channel_id": cid, "start_date": pub.isoformat(),
                         "end_date": min(end28, today).isoformat(), "complete": int(complete),
                         **sum_rows(rows), "fetched_at": now})
        res["d28_updated"] += 1
        res["d28_complete"] += int(complete)
    # Fonti di traffico lifetime del video
    tr = conn.execute("SELECT MAX(fetched_at) FROM traffic_sources WHERE channel_id=? AND video_id=? "
                      "AND period='lifetime'", (cid, vid)).fetchone()
    if args.force or not (tr and is_fresh(tr[0], args.fresh_hours)):
        rows = an.query(startDate=pub.isoformat(), endDate=today.isoformat(), dimensions="insightTrafficSourceType",
                        metrics="views,estimatedMinutesWatched", filters=filt, sort="-views")
        save_traffic(conn, cid, vid, "lifetime", pub.isoformat(), today.isoformat(), rows, now)
        res["traffic_updated"] += 1


def _analytics_channel(conn, an: "Analytics", channel: dict, today: _dt.date, now: str, res: dict) -> None:
    """Totali di canale: Shorts vs long vs live e fonti di traffico degli ultimi 28 giorni."""
    cid = channel["id"]
    start_l28 = (today - _dt.timedelta(days=30)).isoformat()
    end_l28 = (today - _dt.timedelta(days=3)).isoformat()  # ritardo dati ~2-3 giorni
    ch_start = (date_of(channel.get("published_at")) or date_of(
        conn.execute("SELECT MIN(published_at) FROM videos WHERE channel_id=?", (cid,)).fetchone()[0])
        or _dt.date(2005, 2, 14)).isoformat()
    split = {}
    for period, start, end in (("last_28d", start_l28, end_l28), ("lifetime", ch_start, today.isoformat())):
        try:
            metrics = "views,estimatedMinutesWatched,subscribersGained" + (",engagedViews" if an.engaged_ok else "")
            rows = an.query(startDate=start, endDate=end, dimensions="creatorContentType", metrics=metrics)
        except (QuotaExceeded, AuthError):
            raise
        except ApiError as exc:
            res["warnings"].append(f"Divisione per tipo di contenuto ({period}) non disponibile: {exc}")
            continue
        with conn:
            conn.execute("DELETE FROM content_type_split WHERE channel_id=? AND period=?", (cid, period))
            for r in rows:
                ytdb.replace(conn, "content_type_split", {
                    "channel_id": cid, "period": period, "start_date": start, "end_date": end,
                    "content_type": r.get("creatorContentType"), "views": r.get("views"),
                    "engaged_views": r.get("engagedViews"), "minutes_watched": r.get("estimatedMinutesWatched"),
                    "subscribers_gained": r.get("subscribersGained"), "fetched_at": now})
        split[period] = {r.get("creatorContentType"): r.get("views") for r in rows}
    try:
        rows = an.query(startDate=start_l28, endDate=end_l28, dimensions="insightTrafficSourceType",
                        metrics="views,estimatedMinutesWatched", sort="-views")
        save_traffic(conn, cid, "", "last_28d", start_l28, end_l28, rows, now)
    except (QuotaExceeded, AuthError):
        raise
    except ApiError as exc:
        res["warnings"].append(f"Fonti di traffico del canale non disponibili: {exc}")
    res["content_type_views"] = split


def save_traffic(conn, cid: str, vid: str, period: str, start: str, end: str, rows: list[dict], now: str) -> None:
    with conn:
        conn.execute("DELETE FROM traffic_sources WHERE channel_id=? AND video_id=? AND period=?", (cid, vid, period))
        for r in rows:
            ytdb.replace(conn, "traffic_sources", {
                "channel_id": cid, "video_id": vid, "period": period, "start_date": start, "end_date": end,
                "source_type": r.get("insightTrafficSourceType"), "views": r.get("views"),
                "minutes_watched": r.get("estimatedMinutesWatched"), "fetched_at": now})


def interp(xs: list[float], ys: list[float], x: float) -> float | None:
    if not xs:
        return None
    if x <= xs[0]:
        return ys[0]
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * ((x - x0) / (x1 - x0) if x1 > x0 else 0)
    return ys[-1]


def collect_retention(conn, meter: Meter, acc: dict, channel: dict, args, since) -> dict:
    yta = build_service("youtubeAnalytics", "v2", creds=acc["creds"])
    an = Analytics(yta, meter)
    today = _dt.date.today().isoformat()
    now = utc_now().isoformat(timespec="seconds")
    res: dict[str, Any] = {"videos": 0, "curves": 0, "unavailable": [], "skipped_fresh": 0, "intro_hold_30s": {},
                           "warnings": []}
    for v in analytics_videos(conn, channel["id"], since, ("long",), args.max_videos):
        if not v["duration"] or v["duration"] < 60:
            continue
        res["videos"] += 1
        old = conn.execute("SELECT fetched_at FROM retention_summary WHERE video_id=?", (v["id"],)).fetchone()
        if not args.force and old and is_fresh(old[0], args.retention_fresh_hours):
            res["skipped_fresh"] += 1
            continue
        params = dict(startDate=v["published_at"][:10], endDate=today, dimensions="elapsedVideoTimeRatio",
                      filters=f"video=={v['id']}", sort="elapsedVideoTimeRatio")
        try:
            try:
                rows = an.query(metrics="audienceWatchRatio,relativeRetentionPerformance", **params)
            except (QuotaExceeded, AuthError):
                raise
            except ApiError:
                rows = an.query(metrics="audienceWatchRatio", **params)
        except (QuotaExceeded, AuthError):
            raise
        except ApiError as exc:
            res["warnings"].append(f"Retention non letta per {v['id']}: {exc}")
            continue
        if not rows:
            res["unavailable"].append(v["id"])
            log(f"  retention non disponibile per {v['id']} (sotto la soglia di watch time o troppo recente)")
            continue
        xs = [float(r["elapsedVideoTimeRatio"]) for r in rows]
        ys = [float(r["audienceWatchRatio"]) for r in rows]
        hold = interp(xs, ys, min(1.0, 30.0 / v["duration"]))
        with conn:
            conn.execute("DELETE FROM retention WHERE video_id=?", (v["id"],))
            for r in rows:
                ytdb.replace(conn, "retention", {"video_id": v["id"], "ratio": r["elapsedVideoTimeRatio"],
                             "audience_watch_ratio": r.get("audienceWatchRatio"),
                             "relative_retention": r.get("relativeRetentionPerformance"),
                             "start_date": params["startDate"], "end_date": today, "fetched_at": now})
            ytdb.replace(conn, "retention_summary", {"video_id": v["id"], "duration": v["duration"],
                         "points": len(rows), "sec_per_point": round(v["duration"] / max(1, len(rows)), 1),
                         "intro_hold_30s": hold, "mean_awr": sum(ys) / len(ys), "fetched_at": now})
        res["curves"] += 1
        res["intro_hold_30s"][v["id"]] = round(hold, 3) if hold is not None else None
    if res["unavailable"]:
        res["note"] = ("YouTube nasconde la retention sotto una soglia di watch time: normale per video piccoli o "
                       "recenti. La tenuta a 0:30 dalla curva API ha risoluzione ~durata/100 (≈30 s su 50 min): "
                       "per il valore preciso usa il momento chiave 'Intro' in Studio.")
    return res


# ═══ Tier 2: Reporting API (impressioni + CTR) ══════════════════════════════
REACH_TYPES = ("channel_reach_basic_a1", "channel_reach_combined_a1")
BASIC_TYPES = ("channel_basic_a2", "channel_basic_a3")


def _num(v: str | None) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _iso_day(d: str) -> str:
    d = d.strip()
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d) else d[:10]


def load_report(conn, report_type: str, text: str, report_id: str, channel_id: str | None) -> int:
    """Carica un CSV Reporting API nel DB. Ritorna le righe lette."""
    reader = list(csv.DictReader(io.StringIO(text)))
    now = utc_now().isoformat(timespec="seconds")
    if report_type in REACH_TYPES:
        agg: dict[tuple, dict] = {}
        for r in reader:
            key = (_iso_day(r.get("date", "")), r.get("video_id") or "", r.get("traffic_source_type") or "",
                   r.get("device_type") or "")
            a = agg.setdefault(key, {"impr": 0.0, "clicks": 0.0, "ch": r.get("channel_id")})
            impr = _num(r.get("video_thumbnail_impressions"))
            a["impr"] += impr
            a["clicks"] += impr * _num(r.get("video_thumbnail_impressions_ctr"))
        dates = sorted({k[0] for k in agg})
        with conn:
            for d in dates:
                conn.execute("DELETE FROM reach_daily WHERE date=? AND report_type=?", (d, report_type))
            for (d, vid, ts, dev), a in agg.items():
                ytdb.replace(conn, "reach_daily", {
                    "date": d, "channel_id": a["ch"] or channel_id, "video_id": vid, "report_type": report_type,
                    "traffic_source": ts, "device_type": dev, "impressions": int(a["impr"]),
                    "ctr": (a["clicks"] / a["impr"]) if a["impr"] else None, "report_id": report_id, "loaded_at": now})
    elif report_type in BASIC_TYPES:
        cols = {"views": "views", "engaged_views": "engaged_views", "watch_time_minutes": "watch_time_minutes",
                "likes": "likes", "comments": "comments", "shares": "shares",
                "subscribers_gained": "subscribers_gained", "subscribers_lost": "subscribers_lost"}
        agg2: dict[tuple, dict] = {}
        for r in reader:
            key = (_iso_day(r.get("date", "")), r.get("video_id") or "")
            a = agg2.setdefault(key, {"ch": r.get("channel_id"), **{c: None for c in cols}})
            for src, dst in cols.items():
                if src in r and r[src] not in (None, ""):
                    a[dst] = (a[dst] or 0) + _num(r[src])
        with conn:
            for d in sorted({k[0] for k in agg2}):
                conn.execute("DELETE FROM basic_daily WHERE date=?", (d,))
            for (d, vid), a in agg2.items():
                ytdb.replace(conn, "basic_daily", {
                    "date": d, "channel_id": a.pop("ch") or channel_id, "video_id": vid,
                    **{k: (int(v) if v is not None and k != "watch_time_minutes" else v) for k, v in a.items()},
                    "report_id": report_id, "loaded_at": now})
    return len(reader)


def collect_reporting(conn, meter: Meter, acc: dict, channel: dict, args, since) -> dict:
    rep = build_service("youtubereporting", "v1", creds=acc["creds"])
    res: dict[str, Any] = {"jobs": 0, "reports_new": 0, "reports_known": 0, "rows": 0, "by_type": {}, "warnings": []}

    def make_jobs(token):
        return rep.jobs().list(**({"pageToken": token} if token else {}))
    jobs = paginate(meter, make_jobs, "jobs", "reporting", "jobs.list")
    res["jobs"] = len(jobs)
    if not jobs:
        res["warnings"].append(f"Nessun job Reporting: esegui yt-reporting-setup --channel {channel.get('slug') or '<slug>'} "
                               "(CTR e impressioni esistono solo lì; i primi report arrivano dopo 24–48 h)")
        return res
    wanted = set(args.report_types.split(",")) if args.report_types else None
    known = {r[0] for r in conn.execute("SELECT report_id FROM reporting_files")}
    since_rfc = f"{since.isoformat()}T00:00:00Z" if since else None
    downloads = 0
    for job in jobs:
        rtype = job.get("reportTypeId")
        if wanted and rtype not in wanted:
            continue

        def make_reports(token, job_id=job["id"]):
            kw: dict[str, Any] = {"jobId": job_id}
            if since_rfc:
                kw["startTimeAtOrAfter"] = since_rfc
            if token:
                kw["pageToken"] = token
            return rep.jobs().reports().list(**kw)
        reports = paginate(meter, make_reports, "reports", "reporting", "jobs.reports.list")
        reports.sort(key=lambda r: (r.get("startTime", ""), r.get("createTime", "")))
        stats = res["by_type"].setdefault(rtype, {"available": len(reports), "new": 0, "rows": 0})
        for r in reports:
            if r["id"] in known and not args.force:
                res["reports_known"] += 1
                continue
            if downloads >= args.max_reports:
                res["warnings"].append(f"Limite --max-reports {args.max_reports} raggiunto: rilancia per il resto")
                break
            raw = download_report(acc["creds"], r["downloadUrl"])
            meter._record("reporting", "media.download", 1)
            downloads += 1
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8-sig", "replace")
            day = (r.get("startTime") or "")[:10] or "nodate"
            path = REPORTS_DIR / (channel.get("slug") or channel["id"]) / rtype / f"{day}_{r['id']}.csv.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(text.encode("utf-8")))
            n = load_report(conn, rtype, text, r["id"], channel["id"])
            with conn:
                ytdb.replace(conn, "reporting_files", {
                    "report_id": r["id"], "job_id": job["id"], "report_type": rtype, "channel_id": channel["id"],
                    "start_time": r.get("startTime"), "end_time": r.get("endTime"),
                    "create_time": r.get("createTime"), "path": str(path), "rows": n,
                    "loaded_at": utc_now().isoformat(timespec="seconds")})
            known.add(r["id"])
            res["reports_new"] += 1
            res["rows"] += n
            stats["new"] += 1
            stats["rows"] += n
    loaded_types = set(res["by_type"]) & (set(REACH_TYPES) | set(BASIC_TYPES))
    res["loaded_into"] = sorted({"reach_daily" if t in REACH_TYPES else "basic_daily" for t in loaded_types})
    res["raw_dir"] = str(REPORTS_DIR / (channel.get("slug") or channel["id"]))
    return res


# ═══ Main ═══════════════════════════════════════════════════════════════════
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="yt-collect", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", required=True,
                    help="slug del profilo canale oppure @handle / UC… / URL")
    ap.add_argument("--url", help="URL o @handle del canale (sovrascrive il profilo; utile se il profilo manca)")
    ap.add_argument("--what", default=",".join(WHAT_ALL),
                    help="inventory,analytics,retention,reporting (default: tutti; quelli Tier 2 si saltano se manca OAuth)")
    ap.add_argument("--since", help="solo video pubblicati / report dal giorno D (YYYY-MM-DD o '30d')")
    ap.add_argument("--tier", type=int, choices=[0, 1, 2], default=2,
                    help="livello massimo da usare (es. --tier 0 forza yt-dlp)")
    ap.add_argument("--max-videos", type=int, help="limita i video considerati (i più recenti)")
    ap.add_argument("--no-details", action="store_true", help="Tier 0: niente estrazione per video (niente capitoli/date esatte)")
    ap.add_argument("--details-max", type=int, default=30, help="Tier 0: max video da estrarre per esecuzione (default 30)")
    ap.add_argument("--inventory-fresh-hours", type=float, default=6,
                    help="non rifare l'inventario se più recente di N ore allo stesso livello (default 6)")
    ap.add_argument("--details-ttl-days", type=float, default=7, help="Tier 0: non riestrarre dettagli più recenti di N giorni")
    ap.add_argument("--no-podcasts", action="store_true", help="non verificare le playlist podcast")
    ap.add_argument("--fresh-hours", type=float, default=20, help="Tier 2: non rifare lifetime/traffico più recenti di N ore")
    ap.add_argument("--retention-fresh-hours", type=float, default=72, help="Tier 2: non rifare curve più recenti di N ore")
    ap.add_argument("--report-types", help="Reporting: solo questi tipi (separati da virgola)")
    ap.add_argument("--max-reports", type=int, default=200, help="Reporting: max file scaricati per esecuzione")
    ap.add_argument("--quota-budget", type=int, default=5000, help="tetto di unità Data API al giorno (default 5000 su 10000)")
    ap.add_argument("--list-max", type=int, default=60, help="video elencati nel JSON di riepilogo")
    ap.add_argument("--db", help=f"database (default {ytcore.DB_PATH})")
    ap.add_argument("--force", action="store_true", help="ignora le soglie di freschezza")
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    t0 = time.time()
    what = [w.strip() for w in args.what.split(",") if w.strip()]
    bad = [w for w in what if w not in WHAT_ALL]
    if bad:
        ytcore.fail(f"--what non valido: {bad} (ammessi: {WHAT_ALL})")
    try:
        since = parse_since(args.since)
    except ValueError:
        ytcore.fail(f"--since non valido: {args.since} (usa YYYY-MM-DD o 30d)")
    try:
        ch = resolve_channel(args.channel, args.url)
    except ValueError as exc:
        ytcore.fail(str(exc))

    conn = ytdb.connect(args.db)
    purge = ytdb.purge_peer_data(conn)
    warnings: list[str] = []
    if not ch["profile_found"]:
        warnings.append(f"Profilo canale '{args.channel}' non trovato in {', '.join(str(d) for d in ytcore.CHANNELS_DIRS)}: uso il riferimento diretto")
    acc = detect_access(ch.get("slug"), args.tier)
    meter = Meter(conn, ch.get("slug") or args.channel, "yt-collect", args.quota_budget)
    run_id = ytdb.insert(conn, "collect_runs", {"started_at": utc_now().isoformat(timespec="seconds"),
                                                "command": "yt-collect", "channel": args.channel,
                                                "what": ",".join(what), "tier": acc["tier"]})
    conn.commit()
    outputs: dict[str, Any] = {"db": str(args.db or ytcore.DB_PATH)}
    tiers_used: dict[str, int] = {}
    channel: dict | None = None
    ok = True
    error = None

    try:
        # ── Inventario ───────────────────────────────────────────────────
        known = known_channel(conn, ch)
        if "inventory" in what and known and not args.force and \
                is_fresh(known.get("inventory_at"), args.inventory_fresh_hours) and (known.get("tier") or 0) >= min(acc["tier"], 2):
            # inventario recente con lo stesso livello d'accesso: niente nuove richieste
            channel = known
            tiers_used["inventory"] = known.get("tier") or 0
            outputs["inventory"] = {"source": known.get("source"), "tier": known.get("tier"), "cached": True,
                                    "note": f"Inventario del {known['inventory_at']} (< {args.inventory_fresh_hours:g} h): "
                                            "nessuna richiesta, usa --force per rifarlo",
                                    **inventory_summary(conn, known["id"], args.list_max)}
        elif "inventory" in what:
            inv = None
            if acc["tier"] >= 1:
                try:
                    inv = inventory_api(conn, meter, ch, acc, args)
                except (ApiError, QuotaExceeded, AuthError) as exc:
                    warnings.append(f"Inventario via API fallito ({exc}): ripiego su Tier 0 (yt-dlp)")
            if inv is None:
                if not acc["ytdlp"]:
                    raise YtdlpError("Nessun livello d'accesso disponibile per l'inventario")
                inv = inventory_ytdlp(conn, meter, ch, args)
            warnings += inv.pop("warnings", [])
            channel = inv["channel"]
            tiers_used["inventory"] = inv["tier"]
            outputs["inventory"] = {"source": inv["source"], "tier": inv["tier"],
                                    "podcast_checked": inv["podcast_checked"],
                                    **inventory_summary(conn, channel["id"], args.list_max)}
            if inv["source"] == "ytdlp":
                outputs["inventory"]["note"] = ("Tier 0: dati pubblici via yt-dlp (zona grigia ToS, basso volume). "
                                                "Formato dalle schede del canale; date esatte solo per i video con dettagli.")
            elif inv["source"] == "api":
                outputs["inventory"]["note"] = ("Shorts riconosciuti con euristica (≤180 s e verticale): la Data API "
                                                "non ha un flag Shorts. Con OAuth il formato viene da creatorContentType.")
        if channel is None:
            if not known:
                raise ApiError("Canale non ancora in archivio: esegui prima --what inventory")
            channel = known

        # ── Tier 2 ───────────────────────────────────────────────────────
        tier2_steps = [w for w in what if w in ("analytics", "retention", "reporting")]
        if tier2_steps and acc["tier"] < 2:
            msg = next((m for m in acc["messages"] if m.startswith("Tier 2")),
                       "Tier 2 non disponibile: esegui yt-auth --channel " + (ch.get("slug") or "<slug>"))
            warnings.append(f"{msg} — saltati: {', '.join(tier2_steps)}")
            for s in tier2_steps:
                outputs[s] = {"skipped": True, "reason": msg}
        elif tier2_steps:
            steps = {"analytics": collect_analytics, "retention": collect_retention, "reporting": collect_reporting}
            for s in tier2_steps:
                try:
                    r = steps[s](conn, meter, acc, channel, args, since)
                    warnings += r.pop("warnings", [])
                    outputs[s] = r
                    tiers_used[s] = 2
                except QuotaExceeded as exc:
                    warnings.append(f"{s}: quota esaurita ({exc}); interrompo")
                    outputs[s] = {"error": str(exc)}
                    break
                except AuthError as exc:
                    warnings.append(f"{s}: autorizzazione rifiutata ({exc}). Ripeti yt-auth --channel {ch.get('slug')}")
                    outputs[s] = {"error": str(exc)}
                    break
                except ApiError as exc:
                    warnings.append(f"{s}: {exc}")
                    outputs[s] = {"error": str(exc)}
    except (YtdlpError, ApiError) as exc:
        ok, error = False, str(exc)

    summary = {
        "channel": {k: (channel or {}).get(k) for k in ("id", "slug", "handle", "title", "subscribers", "url")},
        "access": {"max_tier": acc["tier"], "used": tiers_used, "messages": acc["messages"]},
        "outputs": outputs, "quota": meter.summary(), "purge": purge,
        "warnings": warnings, "elapsed_s": round(time.time() - t0, 1),
    }
    with conn:
        conn.execute("UPDATE collect_runs SET finished_at=?, ok=?, summary_json=? WHERE id=?",
                     (utc_now().isoformat(timespec="seconds"), int(ok),
                      json.dumps({k: v for k, v in summary.items() if k != "outputs"}, default=str), run_id))
    log(f"Quota: {meter.summary()['data_api_units']} unità Data API, {meter.units['analytics']} query Analytics, "
        f"{meter.units['reporting']} chiamate Reporting, {meter.units['ytdlp']} richieste yt-dlp")
    if ok:
        ytcore.emit(True, **summary)
    else:
        ytcore.emit(False, error=error, **summary)
        sys.exit(1)


if __name__ == "__main__":
    main()
