"""ytdb — database SQLite degli analytics di YouTube Producer (<studio_dir>/data/yt.db, default ~/youtube-studio).

Schema (design §8.4) con migrazioni numerate in `schema_version`. Usato da
yt-collect, yt-outliers e dalle skill che leggono i numeri (mai inventati: ogni numero
viene da qui o dall'output di uno script).

Regole dati (YouTube API Developer Policies):
- Dati pubblici di canali NON nostri (peers, peer_videos) → max 30 giorni, poi si
  aggiornano o si cancellano: `purge_peer_data()` (lo chiamano collect e outliers).
- Dati Analytics/Reporting dei canali autorizzati → si tengono, ma l'autorizzazione va
  riverificata ogni 30 giorni (lo fa yt-auth --check / yt-doctor).
- I punteggi outlier sono metriche DERIVATE, non numeri YouTube.

Uso diretto (manutenzione):
  yt-db status          # tabelle, righe, versione schema (yt-db = shim verso questo modulo)
  yt-db purge [--days 30]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore  # noqa: E402

PEER_RETENTION_DAYS = 30

# ── Migrazioni ──────────────────────────────────────────────────────────────
# Ogni voce: (versione, nota, SQL). Mai modificare una migrazione già rilasciata:
# per cambiare lo schema se ne aggiunge una nuova in coda.
MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "schema iniziale (design §8.4)", """
CREATE TABLE IF NOT EXISTS channels (
    id               TEXT PRIMARY KEY,          -- UC…
    slug             TEXT UNIQUE,               -- profilo canale (slug di <slug>.md)
    handle           TEXT,                      -- @handle del canale
    title            TEXT,
    url              TEXT,
    kind             TEXT,                      -- own | client
    language         TEXT,
    subscribers      INTEGER,
    video_count      INTEGER,
    view_count       INTEGER,
    uploads_playlist TEXT,
    published_at     TEXT,
    source           TEXT,                      -- ytdlp | api | oauth
    tier             INTEGER,                   -- livello d'accesso dell'ultimo collect
    inventory_at     TEXT,                      -- ultimo inventario completo
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id                  TEXT PRIMARY KEY,
    channel_id          TEXT NOT NULL,
    title               TEXT,
    published_at        TEXT,                   -- ISO 8601 (UTC se esatto)
    published_precision TEXT,                   -- exact | day | approx
    duration            REAL,                   -- secondi
    format              TEXT,                   -- long | short | live
    format_source       TEXT,                   -- analytics | tab | media_type | heuristic
    is_podcast          INTEGER,                -- 1/0, NULL = ignoto
    privacy             TEXT,                   -- public | unlisted | private (API/OAuth)
    position            INTEGER,                -- indice nella scheda del canale (0 = più recente)
    has_chapters        INTEGER,
    chapters_valid      INTEGER,                -- regole YouTube: primo a 0:00, ≥3, ciascuno ≥10 s
    chapters_source     TEXT,                   -- description | auto | none
    chapters_json       TEXT,                   -- [{"t": 0, "title": "…"}]
    description         TEXT,
    tags_json           TEXT,
    thumbnail_url       TEXT,
    aspect_ratio        REAL,
    views               INTEGER,                -- ultimo snapshot (storico in video_stats_daily)
    likes               INTEGER,
    comments            INTEGER,
    stats_at            TEXT,
    details_at          TEXT,                   -- ultima estrazione completa (capitoli, data esatta)
    source              TEXT,                   -- ytdlp | api | oauth
    first_seen          TEXT NOT NULL,
    last_seen           TEXT,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_videos_channel_pub ON videos(channel_id, published_at);
CREATE INDEX IF NOT EXISTS idx_videos_format ON videos(channel_id, format);

CREATE TABLE IF NOT EXISTS video_stats_daily (
    video_id   TEXT NOT NULL,
    date       TEXT NOT NULL,                   -- YYYY-MM-DD (giorno dello snapshot)
    views      INTEGER,
    likes      INTEGER,
    comments   INTEGER,
    source     TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (video_id, date)
);

-- Metriche Analytics API a età fissa: primi 28 giorni dalla pubblicazione.
CREATE TABLE IF NOT EXISTS analytics_28d (
    video_id           TEXT PRIMARY KEY,
    channel_id         TEXT,
    start_date         TEXT,
    end_date           TEXT,
    complete           INTEGER,                 -- 1 = finestra chiusa (+2 gg di ritardo dati)
    views              INTEGER,
    engaged_views      INTEGER,
    minutes_watched    REAL,
    avg_view_duration  REAL,                    -- secondi
    avg_view_pct       REAL,                    -- 0–100 (come l'API)
    subscribers_gained INTEGER,
    subscribers_lost   INTEGER,
    likes              INTEGER,
    comments           INTEGER,
    shares             INTEGER,
    fetched_at         TEXT NOT NULL
);

-- Metriche Analytics API dalla pubblicazione a oggi (ultimo valore).
CREATE TABLE IF NOT EXISTS analytics_lifetime (
    video_id           TEXT PRIMARY KEY,
    channel_id         TEXT,
    start_date         TEXT,
    end_date           TEXT,
    content_type       TEXT,                    -- creatorContentType: SHORTS | VIDEO_ON_DEMAND | LIVE_STREAM | STORY
    views              INTEGER,
    engaged_views      INTEGER,
    minutes_watched    REAL,
    avg_view_duration  REAL,
    avg_view_pct       REAL,
    subscribers_gained INTEGER,
    subscribers_lost   INTEGER,
    likes              INTEGER,
    comments           INTEGER,
    shares             INTEGER,
    fetched_at         TEXT NOT NULL
);

-- Totali di canale divisi per tipo di contenuto (Shorts vs long-form vs live).
CREATE TABLE IF NOT EXISTS content_type_split (
    channel_id         TEXT NOT NULL,
    period             TEXT NOT NULL,           -- last_28d | lifetime
    start_date         TEXT,
    end_date           TEXT,
    content_type       TEXT NOT NULL,
    views              INTEGER,
    engaged_views      INTEGER,
    minutes_watched    REAL,
    subscribers_gained INTEGER,
    fetched_at         TEXT NOT NULL,
    PRIMARY KEY (channel_id, period, content_type)
);

-- Curva di retention (Analytics API, ~100 punti per video, ultima versione).
CREATE TABLE IF NOT EXISTS retention (
    video_id             TEXT NOT NULL,
    ratio                REAL NOT NULL,         -- elapsedVideoTimeRatio 0–1
    audience_watch_ratio REAL,                  -- può superare 1 (riguardi)
    relative_retention   REAL,                  -- 0–1, 0.5 = mediana dei video di durata simile
    start_date           TEXT,
    end_date             TEXT,
    fetched_at           TEXT NOT NULL,
    PRIMARY KEY (video_id, ratio)
);

CREATE TABLE IF NOT EXISTS retention_summary (
    video_id        TEXT PRIMARY KEY,
    duration        REAL,
    points          INTEGER,
    sec_per_point   REAL,                       -- risoluzione: ~30 s/punto su 50 min
    intro_hold_30s  REAL,                       -- audienceWatchRatio interpolato a 0:30
    mean_awr        REAL,
    fetched_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traffic_sources (
    channel_id      TEXT NOT NULL,
    video_id        TEXT NOT NULL DEFAULT '',   -- '' = totale canale
    period          TEXT NOT NULL,              -- lifetime | last_28d
    start_date      TEXT,
    end_date        TEXT,
    source_type     TEXT NOT NULL,              -- insightTrafficSourceType
    views           INTEGER,
    minutes_watched REAL,
    fetched_at      TEXT NOT NULL,
    PRIMARY KEY (channel_id, video_id, period, source_type)
);

-- Impressioni e CTR delle thumbnail: SOLO dalla Reporting API (channel_reach_*).
CREATE TABLE IF NOT EXISTS reach_daily (
    date           TEXT NOT NULL,               -- YYYY-MM-DD
    channel_id     TEXT,
    video_id       TEXT NOT NULL,
    report_type    TEXT NOT NULL,               -- channel_reach_basic_a1 | channel_reach_combined_a1
    traffic_source TEXT NOT NULL DEFAULT '',
    device_type    TEXT NOT NULL DEFAULT '',
    impressions    INTEGER,
    ctr            REAL,                        -- come nel CSV (video_thumbnail_impressions_ctr), media pesata
    report_id      TEXT,
    loaded_at      TEXT NOT NULL,
    PRIMARY KEY (date, video_id, report_type, traffic_source, device_type)
);
CREATE INDEX IF NOT EXISTS idx_reach_video ON reach_daily(video_id, date);

-- channel_basic_a2 aggregato per giorno e video (views, watch time, iscritti).
CREATE TABLE IF NOT EXISTS basic_daily (
    date               TEXT NOT NULL,
    channel_id         TEXT,
    video_id           TEXT NOT NULL,
    views              INTEGER,
    engaged_views      INTEGER,
    watch_time_minutes REAL,
    likes              INTEGER,
    comments           INTEGER,
    shares             INTEGER,
    subscribers_gained INTEGER,
    subscribers_lost   INTEGER,
    report_id          TEXT,
    loaded_at          TEXT NOT NULL,
    PRIMARY KEY (date, video_id)
);

-- Registro dei file Reporting API già scaricati (idempotenza).
CREATE TABLE IF NOT EXISTS reporting_files (
    report_id   TEXT PRIMARY KEY,
    job_id      TEXT,
    report_type TEXT,
    channel_id  TEXT,
    start_time  TEXT,
    end_time    TEXT,
    create_time TEXT,
    path        TEXT,
    rows        INTEGER,
    loaded_at   TEXT NOT NULL
);

-- Canali di riferimento (peers). Dati pubblici di terzi: purge a 30 giorni.
CREATE TABLE IF NOT EXISTS peers (
    channel_id  TEXT PRIMARY KEY,
    input       TEXT,                           -- riga del file peers (URL/handle)
    handle      TEXT,
    title       TEXT,
    url         TEXT,
    language    TEXT,
    subscribers INTEGER,
    video_count INTEGER,
    source      TEXT,                           -- ytdlp | api
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS peer_videos (
    video_id            TEXT PRIMARY KEY,
    channel_id          TEXT NOT NULL,
    title               TEXT,
    published_at        TEXT,
    published_precision TEXT,
    duration            REAL,
    format              TEXT,
    position            INTEGER,
    views               INTEGER,
    likes               INTEGER,
    comments            INTEGER,
    thumbnail_url       TEXT,
    source              TEXT,
    fetched_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_peer_videos_channel ON peer_videos(channel_id, published_at);
CREATE INDEX IF NOT EXISTS idx_peer_videos_fetched ON peer_videos(fetched_at);

-- Registri scritti dall'agente / dalle skill.
CREATE TABLE IF NOT EXISTS ab_tests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel      TEXT,
    video_id     TEXT,
    kind         TEXT,                          -- thumbnail | title | both
    variants_json TEXT,                         -- [{"id": "A", "file": "…", "title": "…"}]
    started_at   TEXT,
    ended_at     TEXT,
    metric       TEXT,                          -- watch_time_share (Studio Test & Compare)
    winner       TEXT,
    result_json  TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hooks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    channel        TEXT,
    video_id       TEXT,
    workdir        TEXT,
    family         TEXT,                        -- famiglia di hook (Hook Lab)
    text           TEXT,
    score          REAL,                        -- rubrica 0–100
    chosen         INTEGER,
    intro_hold_30s REAL,                        -- risultato (retention_summary)
    notes          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clips_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT,
    workdir         TEXT,
    clip_id         TEXT,
    parent_video_id TEXT,                       -- episodio lungo
    short_video_id  TEXT,                       -- id YouTube dello Short, quando pubblicato
    src_start       REAL,
    src_end         REAL,
    signal_type     TEXT,
    hook_text       TEXT,
    score           REAL,
    approved        INTEGER,
    published_at    TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel      TEXT,
    video_id     TEXT,
    idea         TEXT,
    metric       TEXT,                          -- es. views_28d, outlier_x
    predicted    REAL,                          -- stima 1–10
    rationale    TEXT,
    actual       REAL,                          -- risultato su scala 1–10
    actual_value REAL,                          -- valore grezzo della metrica
    created_at   TEXT NOT NULL,
    resolved_at  TEXT
);

-- Consumo quota API (Data API in unità; Analytics/Reporting in chiamate).
CREATE TABLE IF NOT EXISTS quota_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    api     TEXT NOT NULL,                      -- data | analytics | reporting | ytdlp
    method  TEXT,
    units   INTEGER NOT NULL,
    channel TEXT,
    command TEXT
);
CREATE INDEX IF NOT EXISTS idx_quota_ts ON quota_log(ts);

CREATE TABLE IF NOT EXISTS collect_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    command      TEXT,
    channel      TEXT,
    what         TEXT,
    tier         INTEGER,
    ok           INTEGER,
    summary_json TEXT
);
"""),
    (2, "apprendimento (yt-learn, 13-learning-loop.md): eventi, job, priori, lezioni, proposte, esiti, golden set", """
-- Solo tabelle e viste nuove: nessun dato esistente cambia. Tutto resta in <studio_dir>/data (mai nella repo).
-- Lavori dell'agente (uno per avvio o ripresa), chiusi dal Passo 5.
CREATE TABLE IF NOT EXISTS learn_jobs (
    id            TEXT PRIMARY KEY,           -- <canale>:<cartella del workdir>:<timestamp>
    channel       TEXT NOT NULL,
    workdir       TEXT,
    skills_json   TEXT,
    status        TEXT NOT NULL,              -- aperto | consegnato | parziale | bloccato | in attesa di approvazione G1 …
    gates_json    TEXT,
    operator      TEXT,
    plugin_commit TEXT,
    video_id      TEXT,
    note          TEXT,
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    learned_at    TEXT,                       -- ultimo `yt-learn update` dopo la chiusura
    summary_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_learn_jobs_channel ON learn_jobs(channel, started_at);
CREATE INDEX IF NOT EXISTS idx_learn_jobs_workdir ON learn_jobs(workdir, ended_at);

-- Registro append-only: proposte (item), decisioni, correzioni, esiti, pubblicazioni. Stesso ref + stesso
-- contenuto = nessun evento nuovo (ingest idempotente); contenuto nuovo = nuova versione (superseded_by).
CREATE TABLE IF NOT EXISTS learn_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    channel        TEXT NOT NULL,
    job_id         TEXT,
    workdir        TEXT,
    video_key      TEXT,                      -- video (cartella del workdir o id YouTube): n = video diversi
    skill          TEXT,
    kind           TEXT NOT NULL,             -- item | decision | correction | outcome | publication | qa | refs_refresh
    ref            TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    data_json      TEXT NOT NULL,
    signal         TEXT,                      -- scelte | esiti | NULL
    operator       TEXT,
    source         TEXT,                      -- ingest | cli | dispatcher | agente | pull | manual
    created_at     TEXT NOT NULL,
    superseded_by  INTEGER,
    retracted_at   TEXT,
    retract_reason TEXT,
    UNIQUE(channel, kind, ref, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_learn_events_kind ON learn_events(channel, kind, skill);
CREATE INDEX IF NOT EXISTS idx_learn_events_wd ON learn_events(workdir, kind);
CREATE INDEX IF NOT EXISTS idx_learn_events_job ON learn_events(job_id);

-- Priori per canale (derivati: `yt-learn update` li ricalcola da learn_events). Beta–Bernoulli + Elo.
CREATE TABLE IF NOT EXISTS learn_priors (
    channel       TEXT NOT NULL,
    feature       TEXT NOT NULL,              -- thumbnail.lever, hook.family, shorts.signal, chapters.title_form …
    value         TEXT NOT NULL,
    signal        TEXT NOT NULL,              -- scelte | esiti (mai mescolati)
    alpha         REAL NOT NULL,
    beta          REAL NOT NULL,
    elo           REAL,
    elo_n         INTEGER DEFAULT 0,
    n_jobs        INTEGER NOT NULL DEFAULT 0, -- video/lavori indipendenti
    n_obs         REAL NOT NULL DEFAULT 0,
    wins          REAL DEFAULT 0,
    losses        REAL DEFAULT 0,
    ties          REAL DEFAULT 0,
    is_default    INTEGER DEFAULT 0,          -- valore di default del profilo: prior con media 0,5 + default_bonus
    evidence_json TEXT,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (channel, feature, value, signal)
);

-- Lezioni: candidata → attiva → pronta (per proposta) → proposta; ritirata. Prove = id di learn_events.
CREATE TABLE IF NOT EXISTS learn_lessons (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    scope          TEXT NOT NULL,             -- channel | global (solo da canali propri)
    channel        TEXT NOT NULL,
    skill          TEXT,
    key            TEXT NOT NULL,
    text           TEXT NOT NULL,
    state          TEXT NOT NULL,
    evidence_json  TEXT NOT NULL,
    n_jobs         INTEGER DEFAULT 0,
    n_contra       INTEGER DEFAULT 0,
    decisive       INTEGER DEFAULT 0,
    confidence     REAL,
    signal         TEXT,
    proposal_id    TEXT,
    retired_reason TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE(scope, channel, key)
);

-- Soglie apprese più severe (solo stringere, H8): si applicano sopra quelle del toolkit.
CREATE TABLE IF NOT EXISTS learn_thresholds (
    channel    TEXT NOT NULL,
    name       TEXT NOT NULL,
    direction  TEXT NOT NULL,                 -- min | max
    value      REAL NOT NULL,
    baseline   REAL,                          -- valore del toolkit al momento della registrazione
    level      TEXT,                          -- warn | error
    lesson_id  INTEGER,
    note       TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    retired_at TEXT,
    PRIMARY KEY (channel, name)
);

-- Proposte di miglioramento (Tier B): JSON + markdown in <studio>/data/proposals/.
CREATE TABLE IF NOT EXISTS learn_proposals (
    id              TEXT PRIMARY KEY,         -- AAAA-MM-GG-<slug>
    channel         TEXT NOT NULL,
    scope           TEXT NOT NULL,
    title           TEXT NOT NULL,
    state           TEXT NOT NULL,            -- in_attesa | in_pr | accettata | respinta | ritirata
    targets_json    TEXT NOT NULL,
    lesson_ids_json TEXT,
    evidence_json   TEXT,
    risk            TEXT,
    hard_rule       TEXT,
    json_path       TEXT,
    md_path         TEXT,
    branch          TEXT,
    pr_url          TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Versione pubblicata (dopo G3, dalla parola dell'operatore o dalla review T+48h) e braccia A/B.
CREATE TABLE IF NOT EXISTS learn_publications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel      TEXT NOT NULL,
    video_id     TEXT NOT NULL,
    job_id       TEXT,
    workdir      TEXT,
    kind         TEXT NOT NULL DEFAULT 'long',  -- long | short
    published_at TEXT,
    arms_json    TEXT,                          -- {"A": {"item", "event", "features", "file"}}
    ab_test_id   INTEGER,
    note         TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(channel, video_id)
);

-- Esiti a T+48h (polso), D+7, D+28: Tier 0 (views a pari età) o Tier 1–2 (Analytics, Reporting, A/B).
CREATE TABLE IF NOT EXISTS learn_outcomes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    channel        TEXT NOT NULL,
    video_id       TEXT NOT NULL,
    checkpoint     TEXT NOT NULL,             -- t48 | d7 | d28
    tier           INTEGER,
    source         TEXT NOT NULL,             -- pull | manual
    metric         TEXT,
    value          REAL,
    baseline       REAL,                      -- mediana dei video precedenti dello stesso formato, stessa età
    ratio          REAL,                      -- metrica derivata: calcolata da noi, non è un dato YouTube
    n_baseline     INTEGER,
    verdict        TEXT NOT NULL,             -- sopra | sopra (nel rumore) | in linea | sotto (nel rumore) | sotto | non leggibile | polso
    impressions    INTEGER,
    ctr            REAL,
    avd            REAL,
    avp            REAL,
    intro_hold_30s REAL,
    ab_json        TEXT,
    metrics_json   TEXT,
    event_id       INTEGER,
    reviewed_at    TEXT,                      -- post-mortem fatto in /youtube:review
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE(video_id, checkpoint)
);

-- Golden set delle thumbnail pubblicate (<studio>/data/thumb-golden/, mai nella repo): fixture di regressione.
CREATE TABLE IF NOT EXISTS learn_golden (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    channel       TEXT NOT NULL,
    video_id      TEXT NOT NULL,
    arm           TEXT,
    item_key      TEXT,
    path          TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    features_json TEXT,
    template      TEXT,
    spec_hash     TEXT,
    published_at  TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(channel, sha256)
);

-- Riferimenti di nicchia (thumbnail di terzi per la griglia QA): dati di terzi, al massimo 30 giorni.
CREATE TABLE IF NOT EXISTS learn_refs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel      TEXT NOT NULL,
    ref_video_id TEXT NOT NULL,
    ref_channel  TEXT,
    title        TEXT,
    path         TEXT,
    source       TEXT,
    fetched_at   TEXT NOT NULL,
    UNIQUE(channel, ref_video_id)
);

-- Cosa è dovuto: letture degli esiti (task = pull) e post-mortem (task = review). La legge anche
-- scripts/yt/bin/session-hint.sh con il CLI sqlite3: una sola definizione per Python e shell.
CREATE VIEW IF NOT EXISTS learn_due_v AS
WITH cp(checkpoint, from_d, to_d) AS (VALUES ('t48', 2, 7), ('d7', 9, 60), ('d28', 30, 180)),
pub AS (
    SELECT p.channel, p.video_id, p.job_id, substr(COALESCE(v.published_at, p.published_at), 1, 10) AS pub_day
    FROM learn_publications p LEFT JOIN videos v ON v.id = p.video_id
)
SELECT pub.channel, pub.video_id, pub.job_id, cp.checkpoint, pub.pub_day,
       date(pub.pub_day, '+' || cp.from_d || ' days') AS due_on, 'pull' AS task
FROM pub JOIN cp
WHERE pub.pub_day IS NOT NULL
  AND date('now') >= date(pub.pub_day, '+' || cp.from_d || ' days')
  AND date('now') <  date(pub.pub_day, '+' || cp.to_d || ' days')
  AND NOT EXISTS (SELECT 1 FROM learn_outcomes o WHERE o.video_id = pub.video_id AND o.checkpoint = cp.checkpoint)
UNION ALL
SELECT o.channel, o.video_id, NULL, o.checkpoint, NULL, substr(o.created_at, 1, 10), 'review'
FROM learn_outcomes o
WHERE o.checkpoint IN ('d7', 'd28') AND o.reviewed_at IS NULL AND o.verdict <> 'non leggibile';
"""),
]

SCHEMA_VERSION = MIGRATIONS[-1][0]


# ── Connessione ─────────────────────────────────────────────────────────────
def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def today_iso() -> str:
    return _dt.date.today().isoformat()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Apre (e crea/migra) il database. Righe come sqlite3.Row."""
    path = Path(path) if path else ytcore.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    migrate(conn)
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version ("
                 "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Applica le migrazioni mancanti in ordine. Ritorna la versione finale."""
    version = current_version(conn)
    for num, note, sql in MIGRATIONS:
        if num <= version:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_version(version, applied_at, note) VALUES (?,?,?)",
                          (num, now_iso(), note))
        version = num
    return version


# ── Helper di scrittura ─────────────────────────────────────────────────────
def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def upsert(conn: sqlite3.Connection, table: str, row: dict, key: Sequence[str],
           *, keep_existing_on_null: bool = True) -> None:
    """INSERT … ON CONFLICT(key) DO UPDATE. Con keep_existing_on_null un None non
    cancella un valore già presente (es. Tier 0 non sovrascrive i dati esatti dell'API)."""
    cols = [c for c in row if c in _columns_cached(conn, table)]
    if not cols:
        return
    placeholders = ",".join("?" for _ in cols)
    updates = []
    for c in cols:
        if c in key:
            continue
        updates.append(f"{c}=COALESCE(excluded.{c}, {table}.{c})" if keep_existing_on_null else f"{c}=excluded.{c}")
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    sql += f" ON CONFLICT({','.join(key)}) DO " + (f"UPDATE SET {','.join(updates)}" if updates else "NOTHING")
    conn.execute(sql, [_sqlval(row[c]) for c in cols])


def replace(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols = [c for c in row if c in _columns_cached(conn, table)]
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
    conn.execute(sql, [_sqlval(row[c]) for c in cols])


def insert(conn: sqlite3.Connection, table: str, row: dict) -> int:
    cols = [c for c in row if c in _columns_cached(conn, table)]
    cur = conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                       [_sqlval(row[c]) for c in cols])
    return int(cur.lastrowid)


_COLS_CACHE: dict[tuple[int, str], list[str]] = {}


def _columns_cached(conn: sqlite3.Connection, table: str) -> list[str]:
    k = (id(conn), table)
    if k not in _COLS_CACHE:
        _COLS_CACHE[k] = _columns(conn, table)
    return _COLS_CACHE[k]


def _sqlval(v: Any) -> Any:
    if isinstance(v, (dict, list, tuple)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return int(v)
    return v


def rows(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, tuple(params))]


# ── Quota ───────────────────────────────────────────────────────────────────
def log_quota(conn: sqlite3.Connection, api: str, method: str, units: int,
              channel: str | None = None, command: str | None = None) -> None:
    with conn:
        conn.execute("INSERT INTO quota_log(ts, api, method, units, channel, command) VALUES (?,?,?,?,?,?)",
                     (now_iso(), api, method, int(units), channel, command))


def quota_day_start_utc() -> str:
    """Inizio del giorno-quota della Data API (mezzanotte ora del Pacifico) in UTC ISO."""
    from zoneinfo import ZoneInfo

    pt = ZoneInfo("America/Los_Angeles")
    now_pt = _dt.datetime.now(pt)
    start = now_pt.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")


def quota_used_today(conn: sqlite3.Connection, api: str = "data") -> int:
    row = conn.execute("SELECT COALESCE(SUM(units),0) FROM quota_log WHERE api=? AND ts>=?",
                       (api, quota_day_start_utc())).fetchone()
    return int(row[0])


# ── Policy: purge dati pubblici di terzi ────────────────────────────────────
def purge_peer_data(conn: sqlite3.Connection, days: int = PEER_RETENTION_DAYS) -> dict:
    """Cancella peers e peer_videos non aggiornati da più di `days` giorni
    (YouTube API Developer Policies III.E.4: dati non autorizzati ≤30 giorni)."""
    cutoff = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)).isoformat(timespec="seconds")
    with conn:
        v = conn.execute("DELETE FROM peer_videos WHERE fetched_at < ?", (cutoff,)).rowcount
        p = conn.execute("DELETE FROM peers WHERE fetched_at < ?", (cutoff,)).rowcount
        # video orfani (canale peer già rimosso)
        o = conn.execute("DELETE FROM peer_videos WHERE channel_id NOT IN (SELECT channel_id FROM peers)").rowcount
    return {"peer_videos_deleted": v + o, "peers_deleted": p, "cutoff": cutoff}


# ── Lettura comoda ──────────────────────────────────────────────────────────
def find_channel(conn: sqlite3.Connection, ref: str) -> dict | None:
    """Canale per slug, id UC… o handle (@x)."""
    ref = ref.strip()
    handle = ref if ref.startswith("@") else f"@{ref}"
    r = conn.execute("SELECT * FROM channels WHERE slug=? OR id=? OR lower(handle)=lower(?)",
                     (ref, ref, handle)).fetchone()
    return dict(r) if r else None


def status(conn: sqlite3.Connection) -> dict:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    return {"schema_version": current_version(conn), "tables": counts,
            "data_api_units_today": quota_used_today(conn, "data")}


# Registri che l'agente compila (le altre tabelle le scrivono solo i collector; le learn_* solo yt-learn)
LOG_TABLES = ("ab_tests", "hooks", "clips_log", "predictions")


def add_log(conn: sqlite3.Connection, table: str, row: dict) -> int:
    """Nuova riga in un registro dell'agente (ab_tests, hooks, clips_log, predictions)."""
    if table not in LOG_TABLES:
        raise ValueError(f"Tabella non scrivibile da qui: {table} (ammesse: {', '.join(LOG_TABLES)})")
    with conn:
        return insert(conn, table, {**row, "created_at": row.get("created_at") or now_iso()})


def query_ro(path: Path | str | None, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    """SELECT in sola lettura (connessione mode=ro): per le skill che leggono i numeri."""
    path = Path(path) if path else ytcore.DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"Database assente: {path} (esegui yt-collect)")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, tuple(params))]
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Manutenzione del database yt.db.\n"
                    "  status                 tabelle, righe, versione schema, unità Data API di oggi\n"
                    "  init                   crea/migra lo schema\n"
                    "  purge [--days 30]      cancella i dati peer più vecchi (policy API)\n"
                    "  query \"SELECT …\"       lettura in sola lettura, righe in JSON\n"
                    "  add TABELLA '{json}'   nuova riga in ab_tests | hooks | clips_log | predictions",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["status", "init", "purge", "query", "add"])
    ap.add_argument("args", nargs="*", help="query: SQL · add: tabella e JSON della riga")
    ap.add_argument("--db", help=f"percorso del database (default {ytcore.DB_PATH})")
    ap.add_argument("--days", type=int, default=PEER_RETENTION_DAYS, help="giorni di conservazione dati peer")
    args = ap.parse_args()
    db = str(args.db or ytcore.DB_PATH)
    if args.action == "query":
        if len(args.args) != 1:
            ytcore.fail("Uso: ytdb.py query \"SELECT …\"")
        try:
            res = query_ro(args.db, args.args[0])
        except (sqlite3.Error, FileNotFoundError) as exc:
            ytcore.fail(f"Query fallita: {exc}")
        ytcore.emit(True, outputs={"db": db}, rows=res, count=len(res))
        return
    conn = connect(args.db)
    if args.action == "purge":
        ytcore.emit(True, outputs={"db": db}, purge=purge_peer_data(conn, args.days))
    elif args.action == "add":
        if len(args.args) != 2:
            ytcore.fail("Uso: ytdb.py add TABELLA '{\"campo\": valore}'")
        try:
            rid = add_log(conn, args.args[0], json.loads(args.args[1]))
        except (ValueError, sqlite3.Error) as exc:
            ytcore.fail(str(exc))
        ytcore.emit(True, outputs={"db": db}, table=args.args[0], id=rid)
    else:
        ytcore.emit(True, outputs={"db": db}, **status(conn))


if __name__ == "__main__":
    main()
