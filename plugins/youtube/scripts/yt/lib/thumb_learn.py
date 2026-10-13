"""yt-thumb-learn — apprendimento delle thumbnail (knowledge 13-learning-loop §4.3, 07-thumbnails §16).

Tier A (automatico, locale, per canale): ogni concept e ogni render diventano un record con le sue caratteristiche
(template, grade, leva, famiglia e parole del gancio, classe d'espressione, volto %, righe %, accento, guest_style,
plate, fonte del volto, lettura a freddo, metriche QA di render.json e del JSON di yt-thumb-qa); la scelta del G2
diventa preferenze a coppie (scelto > scartato, con il motivo dell'operatore); la versione pubblicata (o i bracci
dell'A/B) si lega al video; gli esiti a D+7 e D+28 (CTR quando c'è la Reporting API, altrimenti visualizzazioni a pari
età, segnalate «deboli») e i vincitori di A/B e pre-test aggiornano i prior per caratteristica. Due segnali mai
mescolati: `scelte` (cosa sceglie l'operatore) ed `esiti` (cosa fa il pubblico). Tutto in <studio>/data, mai nella repo.

Tier B (revisionato, solo canali condivisibili: learning_pr_channels + profilo kind: own e share_lessons: true):
`proposals` elenca le lezioni con abbastanza evidenza come proposte (file di destinazione, cambio esatto, id delle
evidenze); le scrive `yt-learn propose` e la PR la apre il dispatcher. Mai un merge automatico. I default del profilo
(template, grade, leva) non vanno mai in PR: diventano `profile_changes`, suggerimenti locali che l'operatore applica a mano.

Regole fisse che l'apprendimento non tocca (13 §2): policy dei volti (niente generativo, `guest_style: graphic` mai di
default), consenso, nessuna chiamata a pagamento, nessun upload, mai pubblicare, nomi pubblici, regola dei bordi dritti,
soglie QA solo più severe. Il ranking dei concept ordina e annota: non cambia template, grade né controlli.

Uso:
  yt-thumb-learn ingest WORKDIR [--channel SLUG] [--job ID] [--renders DIR …]   concept, render, QA, letture a freddo
  yt-thumb-learn rank --channel SLUG --data thumbs/concepts.json [--keep 3] [--seed N] [--out FILE]
                                                         2 concept da sfruttare + 1 da esplorare (Thompson), con n e confidenza
  yt-thumb-learn choice WORKDIR --chosen V[,V] [--rejected V,…] [--reason "…"] [--delegated] [--operator NOME]
  yt-thumb-learn publish WORKDIR --video ID (--version V | --arm A=V --arm B=V) [--published-at ISO] [--ab-test N]
  yt-thumb-learn outcomes [--channel SLUG] [--video ID] [--due] [--today YYYY-MM-DD]
  yt-thumb-learn update --channel SLUG                  sincronizza A/B e pre-test di ab_tests e ricalcola i prior
  yt-thumb-learn priors --channel SLUG [--signal scelte|esiti]
  yt-thumb-learn postmortem --video ID [--checkpoint d7|d28] [--out FILE] [--no-mark]
  yt-thumb-learn golden list|check [--channel SLUG] [--video ID] [--out DIR]   (check: solo avvisi, uscita 0)
  yt-thumb-learn refs plan|refresh|status|purge --channel SLUG [--max N] [--dry-run]
  yt-thumb-learn due [--channel SLUG] · playbook --channel SLUG · proposals --channel SLUG
  yt-thumb-learn learn WORKDIR [--channel SLUG]          Passo 5 per le thumbnail: ingest + update + riepilogo

Versione di un render = nome del file di yt-thumb-render: <id>_<template>[_vN] (N = indice della variante, da 1).
Stampa un JSON di riepilogo su stdout (contratto dei comandi); i log su stderr.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import functools
import hashlib
import json
import math
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402
import ytdb  # noqa: E402

LIB = Path(__file__).resolve().parent
LEARNED = getattr(yc, "LEARNED", yc.DATA / "learned")
GOLDEN_DIR = yc.DATA / "thumb-golden"
REFS_DIR = yc.DATA / "refs"
PREFIX = "thumbnail."                               # nome delle caratteristiche nei report di yt-learn (--focus thumbnail)

# ── Parametri ───────────────────────────────────────────────────────────────
# I pesi e il prior vengono da ytcore.LEARNING (config.LEARNING_DEFAULTS, chiavi «learning_<nome>» del config.yaml);
# questi sono i ripieghi (toolkit più vecchio) e le chiavi solo-thumbnail.
LEARNING_FALLBACK = {
    "prior_strength": 4.0, "default_bonus": 0.1, "pref_weight": 0.5, "ab_weight": 1.0,
    "outcome_weight_d7": 0.25, "outcome_weight_d28": 0.5, "explore_arms": 1, "min_baseline": 3,
    "above_ratio": 1.25, "below_ratio": 0.8, "min_evidence": 3, "pr_channels": [],
}
THUMB = {
    "keep": 3,                       # concept da proporre (07 §5: tre ipotesi)
    "min_levers": 2,                 # mai meno di 2 leve (07 §5.2)
    "elo_k": 16, "elo_start": 1500,  # 13 §3.2: K ≤ 16 sulla scala da 400
    "checkpoints": {"t48": 2, "d7": 7, "d28": 28},
    "views_tolerance": {"t48": 1, "d7": 1, "d28": 3},   # giorni di scarto ammessi per «pari età» (istantanee Tier 0)
    "baseline_window": 10,           # video precedenti dello stesso formato nella base
    "ctr_min_impressions": 300,      # sotto: CTR «non leggibile» (09 §3: intervallo troppo largo)
    "ctr_min_baseline_impressions": 100,
    "native_tests_for_lever": 8,     # 07 §16: il default della leva cambia solo dopo ≥ 8 test nativi
    "old_days": 365,                 # 13 §3.2: osservazioni più vecchie di 12 mesi contano metà
    "refs_max": 8, "refs_per_channel": 2, "refs_max_age_days": 30, "refs_min_age_days": 14, "refs_peer_max_age_days": 30,
    "golden_px_mean_warn": 3.0,      # livelli medi (0–255) di differenza a 640×360 oltre cui si avvisa
    "golden_px_share_warn": 0.02,    # quota di pixel cambiati di oltre 24 livelli
    "golden_metric_tol": {"guest_face_pct": 2.0, "host_face_pct": 2.0, "rows_pct_min": 1.0, "edge_dL_dark": 5.0,
                          "served_detail_min": 120.0, "face_surround_min": 5.0, "circle_dL_edge": 5.0},
}
STAGES = {"concept": 0, "sketch": 1, "render": 2, "final": 3}
SIGNALS = ("scelte", "esiti")

# Caratteristiche: le prime si conoscono già dal concept (ranking prima del render), le ultime solo dopo il render.
# Stessi nomi e valori di yt-learn (lib/learn.py, prefisso «thumbnail.»), così le due viste parlano la stessa lingua;
# in più: face_source (fonte del volto) e la forma «ammissione» del gancio (07 §5.3).
CONCEPT_FEATURES = ("template", "lever", "grade", "guest_style", "accent", "expression", "hook_family",
                    "hook_words", "hook_font", "plate", "face_source", "people", "circle_behind")
RENDER_ONLY = ("face_pct", "rows_pct")
FEATURES = CONCEPT_FEATURES + RENDER_ONLY
FEATURE_IT = {"template": "template", "lever": "leva", "grade": "grade", "guest_style": "guest_style", "accent": "accento",
              "expression": "classe d'espressione", "hook_family": "forma del gancio", "hook_words": "parole del gancio",
              "hook_font": "carattere del titolo", "plate": "plate", "face_source": "fonte del volto", "people": "persone",
              "circle_behind": "cerchio dietro",
              "face_pct": "volto % (ospite)", "rows_pct": "righe del titolo %"}
V2_TEMPLATES = ("duo", "ritratto", "scena", "prova")   # come thumb_render.V2_TEMPLATES (serie v2 inclusa nel plugin)
HOOK_FAMILIES = ("domanda", "numero", "contro", "ammissione", "affermazione")
ADMISSION_START = {"ho", "abbiamo", "avevo", "avevamo", "sono", "siamo", "ero", "eravamo", "l'ho", "l'abbiamo", "mi", "ci"}
NEGATION_START = {"non", "mai", "niente", "nessuno", "nessuna", "basta", "smetti", "smettila", "stop"}


def v2_base(template: str | None) -> str | None:
    """Template v2 della serie inclusa nel plugin, anche quando un brand lo sovrascrive con <slug>-<nome> (07 §8):
    «duo» e «acme-duo» → «duo»; gli altri (generic, <slug>-L1…) → None."""
    t = str(template or "")
    if t in V2_TEMPLATES:
        return t
    head, sep, tail = t.rpartition("-")
    return tail if sep and head and tail in V2_TEMPLATES else None


def settings() -> dict:
    out = dict(LEARNING_FALLBACK)
    out.update({k: v for k, v in (getattr(yc, "LEARNING", None) or {}).items() if v is not None})
    out.update(THUMB)
    return out


def now_iso() -> str:
    return ytdb.now_iso()


def _today(today: str | _dt.date | None = None) -> _dt.date:
    if isinstance(today, _dt.date):
        return today
    return _dt.date.fromisoformat(today) if today else _dt.date.today()


def _date(s: str | None) -> _dt.date | None:
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


# ── Schema (tabelle thumb_*: create qui, idempotente; indipendenti dalle migrazioni di ytdb) ─────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS thumb_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    channel          TEXT NOT NULL,
    workdir          TEXT NOT NULL DEFAULT '',
    job_id           TEXT,
    concept_id       TEXT NOT NULL,
    version          TEXT NOT NULL,              -- <id>_<template>[_vN] = nome del render
    stage            TEXT NOT NULL,              -- concept | sketch | render | final
    template TEXT, lever TEXT, grade TEXT, guest_style TEXT, accent TEXT, expression_class TEXT,
    hook TEXT, keyword TEXT, hook_words INTEGER, hook_family TEXT,
    face_pct REAL, host_face_pct REAL, rows_pct_min REAL, plate_source TEXT, face_source TEXT, n_people INTEGER,
    payoff_at REAL, cold_score INTEGER, cold_read TEXT,
    render_pass INTEGER, render_errors INTEGER, render_warnings INTEGER,
    qa_pass INTEGER, qa_errors INTEGER, qa_warnings INTEGER,
    features_json TEXT, metrics_json TEXT,
    png TEXT, sha256 TEXT,
    chosen INTEGER, choice_reason TEXT, choice_source TEXT, chosen_at TEXT,
    published INTEGER NOT NULL DEFAULT 0, video_id TEXT, ab_arm TEXT, ab_test_id INTEGER, published_at TEXT,
    golden_dir TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(channel, workdir, version)
);
CREATE INDEX IF NOT EXISTS idx_thumb_records_video ON thumb_records(video_id);
CREATE INDEX IF NOT EXISTS idx_thumb_records_channel ON thumb_records(channel, stage);

-- Preferenze a coppie: g2 (operatore), delegated (agente su delega: peso 0 nelle scelte), ab / pretest (esiti),
-- ab_tie (A/B «stesso rendimento» o «inconcludente»: pareggio, metà a testa).
CREATE TABLE IF NOT EXISTS thumb_prefs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel    TEXT NOT NULL,
    workdir    TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL,
    winner_id  INTEGER NOT NULL,
    loser_id   INTEGER NOT NULL,
    reason     TEXT,                              -- parole dell'operatore, mai dedotte
    operator   TEXT,
    ref        TEXT,                              -- ab_tests.id per ab/pretest
    created_at TEXT NOT NULL,
    UNIQUE(channel, source, winner_id, loser_id)
);

CREATE TABLE IF NOT EXISTS thumb_outcomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT NOT NULL,
    video_id    TEXT NOT NULL,
    checkpoint  TEXT NOT NULL,                    -- t48 | d7 | d28
    metric      TEXT NOT NULL,                    -- ctr | same_age_views
    value       REAL, baseline REAL, ratio REAL,
    n           INTEGER,                          -- video di confronto
    impressions INTEGER,
    label       TEXT NOT NULL,                    -- sopra | sotto | rumore_sopra | rumore_sotto | non_leggibile
    strength    TEXT,                             -- ctr | debole
    weight      REAL NOT NULL DEFAULT 0,          -- peso usato nei prior (0 = solo contesto)
    mixed       INTEGER NOT NULL DEFAULT 0,       -- più bracci pubblicati: conta solo ciò che hanno in comune
    record_ids  TEXT,
    details_json TEXT,
    measured_at TEXT NOT NULL,
    UNIQUE(video_id, checkpoint, metric)
);

CREATE TABLE IF NOT EXISTS thumb_checkpoints (
    channel       TEXT NOT NULL,
    video_id      TEXT NOT NULL,
    checkpoint    TEXT NOT NULL,
    status        TEXT NOT NULL,                  -- done | insufficient
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_attempt  TEXT,
    postmortem_at TEXT,
    PRIMARY KEY (video_id, checkpoint)
);

CREATE TABLE IF NOT EXISTS thumb_priors (
    channel    TEXT NOT NULL,
    signal     TEXT NOT NULL,                     -- scelte | esiti
    feature    TEXT NOT NULL,
    value      TEXT NOT NULL,
    alpha      REAL NOT NULL, beta REAL NOT NULL,
    prior_mean REAL NOT NULL,
    wins REAL NOT NULL DEFAULT 0, losses REAL NOT NULL DEFAULT 0,
    n_jobs     INTEGER NOT NULL DEFAULT 0,
    n_decisive INTEGER NOT NULL DEFAULT 0,
    elo        REAL,
    evidence   TEXT,                              -- id dei record / video che hanno contribuito
    updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, signal, feature, value)
);

CREATE TABLE IF NOT EXISTS thumb_refs_runs (
    channel      TEXT PRIMARY KEY,
    refreshed_at TEXT NOT NULL,
    n            INTEGER,
    dir          TEXT
);

-- Compiti in scadenza (per il suggerimento di SessionStart: sqlite3 -readonly … "SELECT task, COUNT(*) FROM thumb_learn_due GROUP BY task")
DROP VIEW IF EXISTS thumb_learn_due;
CREATE VIEW thumb_learn_due AS
WITH pub AS (
    SELECT channel, video_id, MIN(published_at) AS published_at FROM thumb_records
    WHERE published = 1 AND video_id IS NOT NULL AND published_at IS NOT NULL GROUP BY channel, video_id),
ck(checkpoint, days) AS (VALUES ('t48', 2), ('d7', 7), ('d28', 28))
SELECT pub.channel AS channel, pub.video_id AS video_id, ck.checkpoint AS checkpoint,
       date(pub.published_at, '+' || ck.days || ' days') AS due_date, 'outcome' AS task
FROM pub CROSS JOIN ck
LEFT JOIN thumb_checkpoints c ON c.video_id = pub.video_id AND c.checkpoint = ck.checkpoint
WHERE date(pub.published_at, '+' || ck.days || ' days') <= date('now')
  AND julianday('now') - julianday(pub.published_at) <= ck.days + 60
  AND (c.video_id IS NULL OR (c.status = 'insufficient' AND c.attempts < 3 AND date(c.last_attempt) < date('now')))
UNION ALL
SELECT c.channel, c.video_id, c.checkpoint, date(c.last_attempt), 'postmortem'
FROM thumb_checkpoints c WHERE c.checkpoint IN ('d7', 'd28') AND c.status = 'done' AND c.postmortem_at IS NULL
UNION ALL
SELECT r.channel, NULL, 'refs', date(r.refreshed_at, '+30 days'), 'refs'
FROM thumb_refs_runs r WHERE date(r.refreshed_at, '+30 days') <= date('now');
"""
DUE_SQL = "SELECT task, COUNT(*) AS n FROM thumb_learn_due GROUP BY task"


def ensure_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)


def connect(db: str | Path | None = None) -> sqlite3.Connection:
    conn = ytdb.connect(db)
    ensure_schema(conn)
    return conn


# ── Profilo del canale e default del knowledge (prior) ─────────────────────────────────────────────────────────
def load_profile(channel: str | None) -> dict:
    if not channel:
        return {}
    try:
        return yc.load_channel(channel)
    except Exception:  # noqa: BLE001 — profilo assente o illeggibile: prior neutri
        return {}


def knowledge_defaults(profile: dict | None) -> dict[str, set[str]]:
    """Valori che il knowledge e il profilo raccomandano di default (prior leggermente più alto, 13 §3.2)."""
    th = (profile or {}).get("thumbnails") or {}
    tpl = th.get("default_template")
    d: dict[str, set[str]] = {f: set() for f in FEATURES}
    if tpl:
        d["template"].add(str(tpl))
    if th.get("default_lever"):
        d["lever"].add(str(th["default_lever"]))
    gd = th.get("grade_default")
    if isinstance(gd, dict):
        g = gd.get(tpl) if tpl else None
        d["grade"].add(str(g or gd.get("others") or "natural"))
    elif gd:
        d["grade"].add(str(gd))
    d["guest_style"].add(str(th.get("guest_style_default") or "none"))   # graphic mai di default (H1)
    d["face_pct"].update({"40-45", "45+"})                                # 07 §0.2: obiettivo 40–50 %
    d["face_source"].add("camera-stretta")                                # 07: camera fissa stretta prima fonte
    d["circle_behind"].add("guest")
    if v2_base(tpl):
        d["hook_font"].add("anton")                                       # 07 §7.7: titolo v2 in Anton
    if v2_base(tpl) == "duo":
        d["rows_pct"].add("20+")                                          # duo: ogni riga ≥ 20 %
        d["hook_words"].update({"3", "4"})
        d["people"].add("duo")
        d["plate"].add("scene")
    if th.get("default_lever") == "claim":
        d["expression"].add("intenso")                                    # 07 §5.5: claim → intenso
    return d


def allowed_values(profile: dict | None) -> dict[str, set[str]]:
    """Valori ammessi dal profilo (regole fisse: il ranking esclude un concept fuori regola, non lo «corregge»)."""
    th = (profile or {}).get("thumbnails") or {}
    out: dict[str, set[str]] = {}
    if th.get("guest_style_allowed"):
        out["guest_style"] = {str(v) for v in th["guest_style_allowed"]}
    if th.get("grade_allowed"):
        out["grade"] = {str(v) for v in th["grade_allowed"]}
    if th.get("accents"):
        out["accent"] = {str(v) for v in th["accents"]} | {"auto"}
    return out


# ── Caratteristiche ─────────────────────────────────────────────────────────────────────────────────────────────
def hook_words(text: str | None) -> list[str]:
    """Come thumb_render.hook_words: gli elisi contano due parole («L'AGENDA» = 2)."""
    t = re.sub(r"(\w)['’](\w)", r"\1 \2", str(text or ""))
    return [w for w in re.split(r"[\s|]+", t) if re.search(r"\w", w)]


def hook_family(hook: str | None, hook_form: str | None = None, lever: str | None = None) -> str | None:
    """Forma del gancio (07 §5.3, valori di yt-learn): domanda · numero · contro (negazione di una credenza, anche
    hook_form «contro») · ammissione (passato in prima persona) · affermazione (soggetto + verbo + posta)."""
    h = str(hook or "").replace("|", " ").strip()
    if not h:
        return None
    if str(hook_form or "").lower() in ("contro", "against", "contrarian") or str(lever or "").lower() == "contro":
        return "contro"
    if h.rstrip(" .!»\"").endswith("?"):
        return "domanda"
    if re.search(r"\d", h):
        return "numero"
    ws = [w.lower().strip(".,!?;:«»\"“”…") for w in h.split()]
    if ws and (ws[0] in NEGATION_START or "non" in ws[1:3]):
        return "contro"
    if ws and (ws[0] in ADMISSION_START or ws[0].startswith(("l'ho", "l’ho"))):
        return "ammissione"
    return "affermazione"


def words_bucket(n: int | None) -> str | None:
    if n is None:
        return None
    return "<3" if n < 3 else ("6+" if n >= 6 else str(n))


def _pct(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x * 100 if x <= 1.0 else x


def face_bucket(frac: Any) -> str | None:
    """Fasce di yt-learn: <30 · 30-35 · 35-40 · 40-45 · 45+ (07: errore < 35, obiettivo 40–50)."""
    p = _pct(frac)
    if p is None:
        return None
    for hi, lab in ((30, "<30"), (35, "30-35"), (40, "35-40"), (45, "40-45")):
        if p < hi:
            return lab
    return "45+"


def rows_bucket(frac: Any) -> str | None:
    """Fasce di yt-learn: <12 · 12-15 · 15-18 · 18-20 · 20+ (riga più bassa del titolo)."""
    p = _pct(frac)
    if p is None:
        return None
    for hi, lab in ((12, "<12"), (15, "12-15"), (18, "15-18"), (20, "18-20")):
        if p < hi:
            return lab
    return "20+"


def people_value(n: int | None) -> str | None:
    """Valori di yt-learn: duo (≥ 2 persone) · solo · nessuno."""
    if n is None:
        return None
    return "duo" if n >= 2 else ("solo" if n == 1 else "nessuno")


def face_source_of(source: dict | None) -> str | None:
    """Fonte del volto dal sidecar di yt-portrait cut (portrait.source: kind still|camera|master, layout)."""
    if not isinstance(source, dict) or not source:
        return None
    kind, lay = str(source.get("kind") or ""), str(source.get("layout") or "")
    if kind == "still" or source.get("image"):
        return "foto"
    if kind == "camera":
        return "camera-stretta" if lay in ("full", "") else f"camera-{lay}"
    if kind == "master":
        return {"inset": "master-inset", "wide": "master-largo", "full": "master-pieno"}.get(lay, f"master-{lay or '?'}")
    return kind or None


def _portrait_source_for(path: Path | None) -> dict | None:
    """portrait.source dal sidecar del ritaglio (<png>.meta.json o <png>.json di yt-portrait cut)."""
    if not path:
        return None
    for side in (path.with_suffix(".meta.json"), path.with_suffix(".json")):
        try:
            d = yc.read_json(side)
        except Exception:  # noqa: BLE001
            continue
        src = (d.get("portrait") or {}).get("source") or (d.get("source") if d.get("tool") == "yt-portrait cut" else None)
        if isinstance(src, dict):
            return src
    return None


def _resolve(p: str | None, base: Path | None) -> Path | None:
    if not p:
        return None
    q = Path(str(p)).expanduser()
    if not q.is_absolute() and base is not None:
        q = base / q
    return q


def _guest(people: list[dict]) -> dict | None:
    return next((p for p in people if (p.get("role") or "") == "guest"), people[0] if people else None)


def default_grade(template: str | None, profile: dict | None = None) -> str:
    """Grade di default: quello del profilo (thumbnails.grade_default, per template o «others»), altrimenti natural
    (thumb_render: mono è un'opzione che il profilo o il concept scelgono, mai un default del plugin)."""
    gd = ((profile or {}).get("thumbnails") or {}).get("grade_default")
    if isinstance(gd, dict):
        g = (gd.get(template) if template else None) or gd.get(v2_base(template) or "") or gd.get("others")
        return str(g or "natural")
    return str(gd) if isinstance(gd, str) and gd else "natural"


def concept_features(c: dict, profile: dict | None = None, base: Path | None = None) -> dict:
    """Caratteristiche note dal concept (prima del render). `base` = cartella di concepts.json (per i ritagli)."""
    th = (profile or {}).get("thumbnails") or {}
    tpl = c.get("template")
    lever = str(c.get("lever") or "") or None
    hook_form = c.get("hook_form")
    if lever == "contro":                    # vecchio contratto: «contro» è una forma del gancio dentro claim
        lever, hook_form = "claim", hook_form or "contro"
    hook = c.get("hook") or c.get("text")
    people = c.get("people") or ([{k: c[k] for k in ("frame", "cutout") if k in c}] if (c.get("frame") or c.get("cutout")) else [])
    plate = c.get("plate")
    v2 = v2_base(tpl) is not None
    plate_source = (plate.get("source") if isinstance(plate, dict) else ("scene" if plate else None)) or ("flat" if v2 else None)
    g = _guest(people)
    fsrc = None
    if g and g.get("cutout"):
        fsrc = face_source_of(_portrait_source_for(_resolve(g["cutout"], base)))
    elif g and g.get("frame"):
        fsrc = "master-frame"
    accent = c.get("accent")
    wn = len(hook_words(hook)) if hook else None
    f = {
        "template": tpl,
        "lever": lever,
        "grade": str(c.get("grade") or default_grade(tpl, profile)).lower() if (v2 or c.get("grade")) else None,
        "guest_style": str(c.get("guest_style") or (th.get("guest_style_default") if v2 else None) or "none") if (v2 or c.get("guest_style")) else None,
        "accent": None if accent in (None, "", "auto") else str(accent),
        "expression": c.get("expression_class"),
        "hook_family": c.get("hook_family") or hook_family(hook, hook_form, c.get("lever")),
        "hook_words": words_bucket(wn),
        "hook_font": c.get("hook_font") or ("anton" if v2 else None),
        "plate": plate_source,
        "face_source": fsrc,
        "people": people_value(len(people)) if tpl else None,
        "circle_behind": (c.get("circle_behind") or ("guest" if v2_base(tpl) in ("duo", "ritratto") else None)),
    }
    return {k: (str(v) if v is not None else None) for k, v in f.items()}


def render_features(sd: dict) -> tuple[dict, dict]:
    """(caratteristiche, metriche) dal sidecar <nome>.render.json di yt-thumb-render (v1 e v2)."""
    spec = sd.get("spec") or {}
    c2 = sd.get("checks_v2") or {}
    v2 = sd.get("v2") or {}
    m = sd.get("metrics") or {}
    bm = m.get("series") or {}                           # metrics.series dei template di serie (_common.js): accento, grade…
    heroes = c2.get("heroes") or (sd.get("checks2") or {}).get("heroes") or []
    people = spec.get("people") or []
    roles = [h.get("role") for h in heroes]
    if not any(roles):                                   # v1: ruoli dalla spec, nello stesso ordine
        roles = [p.get("role") for p in people]
    fr = [(roles[i] if i < len(roles) else None, h.get("face_frac")) for i, h in enumerate(heroes)]
    if not fr and m.get("heroes"):
        fr = [(people[i].get("role") if i < len(people) else None, h.get("face_frac")) for i, h in enumerate(m["heroes"])]
    guest_f = [f for r, f in fr if r == "guest" and f is not None] or [max((f for _, f in fr if f is not None), default=None)]
    host_f = [f for r, f in fr if r == "host" and f is not None]
    rows = [r.get("frac") for r in (c2.get("hook_rows") or []) if r.get("frac") is not None]
    accents = c2.get("accents") or bm.get("accents") or []
    accent = (accents[0] if accents else None) or (v2.get("accent_choice") or {}).get("chosen") or bm.get("accent")
    if accent in (None, "auto"):
        accent = spec.get("accent") if spec.get("accent") not in (None, "auto") else None
    grade = (c2.get("grade") or {}).get("mode") or bm.get("grade") or spec.get("grade")
    plate = v2.get("plate") or {}
    plate_source = plate.get("source") or (spec.get("plate", {}).get("source") if isinstance(spec.get("plate"), dict) else None)
    g = _guest(people)
    fsrc = face_source_of(((g or {}).get("portrait") or {}).get("source")) if g else None
    hook = spec.get("hook") or spec.get("text")
    hw = (v2.get("hook") or {}).get("words")
    if hw is None and hook:
        hw = len(hook_words(hook))
    lever = spec.get("lever")
    hook_form = spec.get("hook_form")
    if lever == "contro":
        lever, hook_form = "claim", hook_form or "contro"
    feats = {
        "template": sd.get("template") or spec.get("template"),
        "lever": lever,
        "grade": grade,
        "guest_style": spec.get("guest_style") or bm.get("guest_style") or ("none" if sd.get("checks_v2") else None),
        "accent": accent,
        "expression": spec.get("expression_class"),
        "hook_family": spec.get("hook_family") or hook_family(hook, hook_form, spec.get("lever")),
        "hook_words": words_bucket(hw),
        "hook_font": spec.get("hook_font") or ("anton" if v2_base(sd.get("template") or spec.get("template")) else None),
        "plate": plate_source,
        "face_source": fsrc,
        "people": people_value(len(people)) if (people or sd.get("template")) else None,
        "circle_behind": spec.get("circle_behind") or ("guest" if v2_base(sd.get("template")) in ("duo", "ritratto") else None),
        "face_pct": face_bucket(guest_f[0]) if guest_f and guest_f[0] is not None else None,
        "rows_pct": rows_bucket(min(rows)) if rows else None,
    }
    lap = [((h.get("served_720") or {}).get("lap")) for h in heroes]
    sur = [h.get("face_surround_dL") for h in heroes]
    circ = [c.get("dL_edge") for c in (c2.get("circle") or []) if c.get("dL_edge") is not None]
    metrics = {
        "guest_face_pct": round(_pct(guest_f[0]), 2) if guest_f and guest_f[0] is not None else None,
        "host_face_pct": round(_pct(max(host_f)), 2) if host_f else None,
        "rows_pct_min": round(_pct(min(rows)), 2) if rows else None,
        "rows_n": len(rows) or None,
        "n_people": len(people) if people else None,
        "hook_words": hw,
        "served_detail_min": min((v for v in lap if v is not None), default=None),
        "face_surround_min": min((v for v in sur if v is not None), default=None),
        "edge_dL_dark": (c2.get("edge_dark") or {}).get("edge_dL_dark"),
        "edge_light_share": (c2.get("edge_dark") or {}).get("edge_light_share"),
        "circle_dL_edge": min(circ) if circ else None,
        "silhouette_dL_246": c2.get("silhouette_dL_246"),
        "hook_plate_contrast": c2.get("hook_plate_contrast"),
        "grade_pass": (c2.get("grade") or {}).get("pass"),
        "pass": sd.get("pass"),
        "errors": len(sd.get("errors") or []),
        "warnings": len(sd.get("warnings") or []),
        "jpg_bytes": sd.get("jpg_bytes"),
    }
    return ({k: (str(v) if v is not None else None) for k, v in feats.items()},
            {k: v for k, v in metrics.items() if v is not None})


def qa_features(entry: dict) -> dict:
    """Riassunto di un'immagine del JSON di yt-thumb-qa (<stem>_qa.json o outputs.images[i])."""
    checks = entry.get("checks") or []
    lv = {c.get("id"): c.get("level") for c in checks if c.get("id")}
    val = {c.get("id"): c.get("value") for c in checks if c.get("id") and isinstance(c.get("value"), (int, float))}
    mt = entry.get("metrics") or {}
    return {"pass": entry.get("pass"), "errors": len(entry.get("errors") or []), "warnings": len(entry.get("warnings") or []),
            "levels": lv, "values": val,
            "colorfulness_360": mt.get("colorfulness_360"), "text_contrast_168_min": mt.get("text_contrast_168_min")}


# ── Record ──────────────────────────────────────────────────────────────────────────────────────────────────────
def version_name(cid: Any, template: Any, suffix: str = "") -> str:
    return f"{cid}_{template}{suffix}"


def expand_concepts(concepts: list[dict]) -> list[tuple[dict, str]]:
    """Come yt-thumb-render: ogni variante eredita il concept; suffisso _vN solo se ci sono varianti."""
    out = []
    for c in concepts:
        variants = c.get("variants") or [None]
        for vi, v in enumerate(variants, 1):
            item = {k: val for k, val in c.items() if k != "variants"}
            suffix = ""
            if v:
                item.update(v)
                suffix = f"_v{vi}"
            out.append((item, suffix))
    return out


def load_concepts_file(path: Path) -> list[dict]:
    obj = yc.read_json(path)
    if isinstance(obj, dict):
        obj = obj.get("concepts", [obj])
    return [c for c in obj if isinstance(c, dict)] if isinstance(obj, list) else []


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _row_of(conn, channel: str, workdir: str, version: str) -> dict | None:
    r = conn.execute("SELECT * FROM thumb_records WHERE channel=? AND workdir=? AND version=?",
                     (channel, workdir, version)).fetchone()
    return dict(r) if r else None


COL_FROM_FEATURE = {"template": "template", "lever": "lever", "grade": "grade", "guest_style": "guest_style", "accent": "accent",
                    "expression_class": "expression", "hook_family": "hook_family", "plate_source": "plate",
                    "face_source": "face_source"}


def upsert_record(conn, *, channel: str, workdir: str, concept_id: str, version: str, stage: str,
                  features: dict | None = None, metrics: dict | None = None, extra: dict | None = None) -> int:
    """Crea o aggiorna il record (chiave canale + workdir + versione). Le caratteristiche misurate sul render
    vincono su quelle del concept; lo stadio non torna mai indietro."""
    prev = _row_of(conn, channel, workdir, version)
    feats = json.loads(prev["features_json"]) if prev and prev.get("features_json") else {}
    for k, v in (features or {}).items():
        if v is not None or k not in feats:
            feats[k] = v
    mets = json.loads(prev["metrics_json"]) if prev and prev.get("metrics_json") else {}
    mets.update(metrics or {})
    st = stage
    if prev and STAGES.get(prev["stage"], 0) > STAGES.get(stage, 0):
        st = prev["stage"]
    row = {"channel": channel, "workdir": workdir, "concept_id": str(concept_id), "version": version, "stage": st,
           "features_json": json.dumps(feats, ensure_ascii=False, sort_keys=True),
           "metrics_json": json.dumps(mets, ensure_ascii=False, sort_keys=True, default=str), "updated_at": now_iso()}
    for col, k in COL_FROM_FEATURE.items():
        row[col] = feats.get(k)
    row.update({k: v for k, v in (extra or {}).items() if v is not None})
    if prev:
        sets = ", ".join(f"{k}=?" for k in row)
        conn.execute(f"UPDATE thumb_records SET {sets} WHERE id=?", [*row.values(), prev["id"]])
        return int(prev["id"])
    row["created_at"] = row["updated_at"]
    cols = ", ".join(row)
    cur = conn.execute(f"INSERT INTO thumb_records ({cols}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    return int(cur.lastrowid)


def channel_of_workdir(wd: Path, channel: str | None = None) -> str:
    if channel:
        return channel
    pj = wd / "project.json"
    if pj.exists():
        try:
            ch = yc.read_json(pj).get("channel")
            if ch:
                return str(ch)
        except Exception:  # noqa: BLE001
            pass
    try:
        rel = wd.resolve().relative_to(yc.WORK.resolve())
        return rel.parts[0]
    except (ValueError, IndexError):
        pass
    raise ValueError(f"canale non determinabile per {wd}: passa --channel")


def _read_cold(wd: Path) -> list[dict]:
    p = wd / "thumbs" / "cold" / "cold_reads.json"
    if not p.exists():
        return []
    try:
        d = yc.read_json(p)
    except Exception:  # noqa: BLE001
        return []
    if isinstance(d, dict):
        d = d.get("reads") or [{"id": k, **(v if isinstance(v, dict) else {"score": v})} for k, v in d.items()]
    return [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []


def _qa_entries(wd: Path, qa_dirs: Iterable[Path]) -> dict[str, dict]:
    """Voci del JSON di yt-thumb-qa (<stem>_qa.json; oppure qa.json con outputs.images), con chiave il percorso del render
    senza estensione (se la voce dice quale file ha controllato) oppure «stem:<nome>» (voci senza file)."""
    out: dict[str, dict] = {}

    def put(e: dict, fallback_stem: str) -> None:
        f = e.get("file")
        if f:
            out[str(Path(f).expanduser().resolve().with_suffix(""))] = e
        else:
            out[f"stem:{fallback_stem}"] = e

    for d in qa_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*_qa.json")):
            try:
                put(yc.read_json(f), f.name[:-len("_qa.json")])
            except Exception:  # noqa: BLE001
                continue
        whole = d / "qa.json"
        if whole.exists():
            try:
                for e in (yc.read_json(whole).get("outputs") or {}).get("images") or []:
                    put(e, Path(e.get("file", "")).stem)
            except Exception:  # noqa: BLE001
                pass
    return out


def ingest_workdir(conn, workdir: str | Path, channel: str | None = None, job_id: str | None = None,
                   render_dirs: Iterable[str | Path] | None = None, profile: dict | None = None) -> dict:
    """Registra concept (thumbs/concepts.json), render (sidecar .render.json), QA (*_qa.json) e letture a freddo.
    Idempotente: rilanciarlo aggiorna gli stessi record."""
    wd = Path(workdir).expanduser().resolve()
    ch = channel_of_workdir(wd, channel)
    profile = load_profile(ch) if profile is None else profile
    thumbs = wd / "thumbs"
    summary = {"channel": ch, "workdir": str(wd), "concepts": 0, "renders": 0, "sketches": 0, "qa": 0, "cold": 0,
               "warnings": []}
    cfile = thumbs / "concepts.json"
    concepts: dict[str, dict] = {}
    with conn:
        if cfile.exists():
            try:
                cl = load_concepts_file(cfile)
            except Exception as e:  # noqa: BLE001
                cl = []
                summary["warnings"].append(f"concepts.json illeggibile: {e}")
            for c, suffix in expand_concepts(cl):
                cid = str(c.get("id", "X"))
                ver = version_name(cid, c.get("template"), suffix)
                concepts[ver] = c
                hook = c.get("hook") or c.get("text")
                upsert_record(conn, channel=ch, workdir=str(wd), concept_id=cid, version=ver, stage="concept",
                              features=concept_features(c, profile, thumbs),
                              extra={"job_id": job_id, "hook": hook, "keyword": c.get("keyword") or c.get("highlight"),
                                     "hook_words": len(hook_words(hook)) if hook else None, "payoff_at": c.get("payoff_at")})
                summary["concepts"] += 1
        dirs = [Path(d).expanduser() for d in render_dirs] if render_dirs else [thumbs / "renders", thumbs / "sketch"]
        qa = _qa_entries(wd, [*sorted(q for q in thumbs.glob("qa*") if q.is_dir()),
                              *[d.parent / "qa" for d in dirs if d.parent != thumbs]])
        for d in dirs:
            if not d.is_dir():
                continue
            stage = "sketch" if d.name.startswith("sketch") else "render"
            for side in sorted(d.glob("*.render.json")):
                try:
                    sd = yc.read_json(side)
                except Exception as e:  # noqa: BLE001
                    summary["warnings"].append(f"{side.name}: sidecar illeggibile ({e})")
                    continue
                ver = sd.get("name") or side.name[:-len(".render.json")]
                feats, mets = render_features(sd)
                # sidecar senza spec (render vecchi o minimi): le caratteristiche note dal concept riempiono i buchi
                base_c = concepts.get(ver) or concepts.get(re.sub(r"_v\d+$", "", ver))
                if base_c:
                    for k, v in concept_features(base_c, profile, thumbs).items():
                        if feats.get(k) is None and v is not None:
                            feats[k] = v
                q = qa.get(str((side.parent / ver).resolve())) or qa.get(f"stem:{ver}")
                if not q and sd.get("png"):          # sidecar copiato altrove: il JSON di QA nomina il PNG originale
                    q = qa.get(str(Path(str(sd["png"])).expanduser().resolve().with_suffix("")))
                extra = {"job_id": job_id, "png": sd.get("png"), "render_pass": sd.get("pass"),
                         "render_errors": len(sd.get("errors") or []), "render_warnings": len(sd.get("warnings") or []),
                         "face_pct": mets.get("guest_face_pct"), "host_face_pct": mets.get("host_face_pct"),
                         "rows_pct_min": mets.get("rows_pct_min"), "n_people": mets.get("n_people"),
                         "hook": (sd.get("spec") or {}).get("hook") or (sd.get("spec") or {}).get("text"),
                         "keyword": (sd.get("spec") or {}).get("keyword"), "hook_words": mets.get("hook_words"),
                         "payoff_at": (sd.get("spec") or {}).get("payoff_at")}
                if q:
                    qf = qa_features(q)
                    mets = {**mets, "qa": qf}
                    extra.update({"qa_pass": qf["pass"], "qa_errors": qf["errors"], "qa_warnings": qf["warnings"]})
                    summary["qa"] += 1
                png = Path(sd["png"]) if sd.get("png") else None
                if png and png.exists() and stage == "render":
                    extra["sha256"] = _sha256(png)
                upsert_record(conn, channel=ch, workdir=str(wd), concept_id=str(sd.get("id") or ver.split("_")[0]),
                              version=ver, stage=stage, features=feats, metrics=mets, extra=extra)
                summary["sketches" if stage == "sketch" else "renders"] += 1
        for rd in _read_cold(wd):
            score = rd.get("score")
            try:
                score = int(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            text = rd.get("read") or rd.get("lettura") or rd.get("text")
            target = rd.get("render") or rd.get("version")
            if target:
                rows = conn.execute("SELECT id FROM thumb_records WHERE channel=? AND workdir=? AND version=?",
                                    (ch, str(wd), str(target))).fetchall()
            else:
                rows = conn.execute("SELECT id FROM thumb_records WHERE channel=? AND workdir=? AND concept_id=?",
                                    (ch, str(wd), str(rd.get("id") or rd.get("concept")))).fetchall()
            for r in rows:
                prev = conn.execute("SELECT features_json FROM thumb_records WHERE id=?", (r[0],)).fetchone()
                feats = json.loads(prev[0] or "{}")
                conn.execute("UPDATE thumb_records SET cold_score=?, cold_read=?, updated_at=? WHERE id=?",
                             (score, text, now_iso(), r[0]))
                feats["cold_score"] = str(score) if score is not None else None
                conn.execute("UPDATE thumb_records SET features_json=? WHERE id=?",
                             (json.dumps(feats, ensure_ascii=False, sort_keys=True), r[0]))
                summary["cold"] += 1
    if not cfile.exists() and not summary["renders"] and not summary["sketches"]:
        summary["warnings"].append("niente da registrare: né thumbs/concepts.json né render con sidecar")
    return summary


# ── Scelte al G2 (preferenze a coppie) ──────────────────────────────────────────────────────────────────────────
def _split(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        items = v
    else:
        items = re.split(r"[,\s]+", str(v))
    return [str(x).strip() for x in items if str(x).strip()]


def resolve_versions(conn, channel: str, workdir: str, refs: Iterable[str], min_stage: str = "render") -> list[int]:
    """Riferimenti → id dei record: nome esatto della versione (anche con .png), oppure id del concept (tutte le sue
    versioni renderizzate)."""
    ids: list[int] = []
    for ref in refs:
        ref = Path(ref).name
        ref = re.sub(r"\.(png|jpe?g|render\.json)$", "", ref)
        r = conn.execute("SELECT id FROM thumb_records WHERE channel=? AND workdir=? AND version=?",
                         (channel, workdir, ref)).fetchone()
        if r:
            ids.append(int(r[0]))
            continue
        rows = conn.execute("SELECT id, stage FROM thumb_records WHERE channel=? AND workdir=? AND concept_id=?",
                            (channel, workdir, ref)).fetchall()
        rows = [x for x in rows if STAGES.get(x["stage"], 0) >= STAGES[min_stage]] or rows
        if not rows:
            raise ValueError(f"versione o concept sconosciuto: {ref} (esegui prima yt-thumb-learn ingest)")
        ids += [int(x["id"]) for x in rows]
    return list(dict.fromkeys(ids))


def add_pref(conn, *, channel: str, workdir: str, source: str, winner: int, loser: int, reason: str | None = None,
             operator: str | None = None, ref: str | None = None) -> bool:
    if winner == loser:
        return False
    cur = conn.execute("INSERT OR IGNORE INTO thumb_prefs(channel, workdir, source, winner_id, loser_id, reason, operator, ref, "
                       "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (channel, workdir, source, winner, loser, reason, operator, ref, now_iso()))
    return cur.rowcount > 0


def _apply_choice(conn, ch: str, wd: Path, win: list[int], lose: list[int], reason: str | None, delegated: bool,
                  operator: str | None) -> int:
    source = "delegated" if delegated else "g2"
    added = 0
    with conn:
        ts = now_iso()
        for w in win:
            conn.execute("UPDATE thumb_records SET chosen=1, stage='final', choice_reason=?, choice_source=?, chosen_at=?, "
                         "updated_at=? WHERE id=?", (reason, source, ts, ts, w))
            for lo in lose:
                added += add_pref(conn, channel=ch, workdir=str(wd), source=source, winner=w, loser=lo, reason=reason,
                                  operator=operator)
        for lo in lose:
            conn.execute("UPDATE thumb_records SET chosen=0, choice_reason=COALESCE(choice_reason, ?), choice_source=?, "
                         "chosen_at=?, updated_at=? WHERE id=? AND (chosen IS NULL OR chosen=0)", (reason, source, ts, ts, lo))
    return added


def record_choice(conn, workdir: str | Path, chosen: Iterable[str], rejected: Iterable[str] | None = None,
                  reason: str | None = None, delegated: bool = False, operator: str | None = None,
                  channel: str | None = None, profile: dict | None = None) -> dict:
    """G2: le versioni scelte battono ognuna delle scartate (default: tutte le altre renderizzate del workdir).
    Il motivo è quello dell'operatore, parola per parola (mai dedotto). Con delega: registrata, peso 0 nelle scelte."""
    wd = Path(workdir).expanduser().resolve()
    ch = channel_of_workdir(wd, channel)
    win = resolve_versions(conn, ch, str(wd), _split(chosen))
    if not win:
        raise ValueError("--chosen vuoto")
    if rejected:
        lose = resolve_versions(conn, ch, str(wd), _split(rejected))
    else:
        rows = conn.execute("SELECT id FROM thumb_records WHERE channel=? AND workdir=? AND stage IN ('render','final')",
                            (ch, str(wd))).fetchall()
        lose = [int(r[0]) for r in rows if int(r[0]) not in win]
    lose = [x for x in lose if x not in win]
    source = "delegated" if delegated else "g2"
    before = {k: v["mean"] for k, v in compute_priors(conn, ch, profile).items() if k[0] == "scelte"}
    added = _apply_choice(conn, ch, wd, win, lose, reason, delegated, operator)
    rebuild_priors(conn, ch, profile)
    after = {k: v["mean"] for k, v in compute_priors(conn, ch, profile).items() if k[0] == "scelte"}
    moved = [{"feature": PREFIX + k[1], "value": k[2], "prima": round(before.get(k, after[k]), 3), "dopo": round(after[k], 3)}
             for k in after if abs(after[k] - before.get(k, after[k])) > 1e-9]
    return {"channel": ch, "workdir": str(wd), "source": source, "chosen": win, "rejected": lose, "prefs_added": added,
            "weight": 0.0 if delegated else settings()["pref_weight"], "priors_moved": moved,
            "note": "scelta delegata: registrata, nessun peso nelle «scelte» (13 §3.1)" if delegated else None}


# ── Integrazione con yt-learn (lib/learn.py): decisioni G2 e pubblicazioni registrate lì ─────────────────────
L1_VERDICT = {"sopra": "sopra", "sopra (nel rumore)": "rumore_sopra", "in linea": "in_linea", "sotto (nel rumore)": "rumore_sotto",
              "sotto": "sotto", "non leggibile": "non_leggibile", "polso": "non_leggibile"}


def _has_table(conn, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (name,)).fetchone())


def _resolve_some(conn, ch: str, wd: str, keys: Iterable[str], warnings: list[str], what: str) -> list[int]:
    out: list[int] = []
    for k in keys:
        try:
            out += resolve_versions(conn, ch, wd, [k])
        except ValueError as e:
            warnings.append(f"{what}: {e}")
    return list(dict.fromkeys(out))


def sync_from_learn(conn, channel: str | None = None, workdir: str | Path | None = None) -> dict:
    """Importa da yt-learn le decisioni del G2 sulle thumbnail (`yt-learn decision --gate G2`, registrate dal
    dispatcher: un solo punto di registrazione) e le pubblicazioni (`yt-learn publish`): preferenze a coppie, versioni
    pubblicate, golden set. Idempotente. Senza le tabelle di yt-learn non fa niente."""
    rep = {"available": _has_table(conn, "learn_events"), "decisions": 0, "prefs_added": 0, "publications": 0, "warnings": []}
    if not rep["available"]:
        return rep
    q = "SELECT * FROM learn_events WHERE kind='decision' AND retracted_at IS NULL AND superseded_by IS NULL"
    params: list = []
    if channel:
        q += " AND channel=?"
        params.append(channel)
    wd_s = str(Path(workdir).expanduser().resolve()) if workdir else None
    for ev in ytdb.rows(conn, q + " ORDER BY id", params):
        try:
            data = json.loads(ev.get("data_json") or "{}")
        except ValueError:
            continue
        skill = data.get("skill") or ev.get("skill")
        if data.get("gate") != "G2" or (skill and skill != "thumbnail") or not data.get("chosen") or not ev.get("workdir"):
            continue
        wd = Path(ev["workdir"]).expanduser().resolve()
        if wd_s and str(wd) != wd_s:
            continue
        ch = ev["channel"]
        win = _resolve_some(conn, ch, str(wd), data["chosen"], rep["warnings"], f"decisione {ev['id']}")
        if not win:
            continue
        lose = _resolve_some(conn, ch, str(wd), data.get("rejected") or [], rep["warnings"], f"decisione {ev['id']}")
        if not lose:
            lose = [int(r[0]) for r in conn.execute("SELECT id FROM thumb_records WHERE channel=? AND workdir=? AND stage IN "
                                                    "('render','final')", (ch, str(wd))).fetchall()]
        lose = [x for x in lose if x not in win]
        rep["prefs_added"] += _apply_choice(conn, ch, wd, win, lose, data.get("reason"), bool(data.get("delegated")),
                                            data.get("operator") or ev.get("operator"))
        rep["decisions"] += 1
    if _has_table(conn, "learn_publications"):
        for pub in ytdb.rows(conn, "SELECT * FROM learn_publications" + (" WHERE channel=?" if channel else ""),
                             (channel,) if channel else ()):
            if not pub.get("workdir") or (wd_s and str(Path(pub["workdir"]).expanduser().resolve()) != wd_s):
                continue
            try:
                arms = json.loads(pub.get("arms_json") or "{}")
            except ValueError:
                arms = {}
            mapping = {str(a): (v.get("item") if isinstance(v, dict) else v) for a, v in (arms or {}).items()}
            mapping = {a: v for a, v in mapping.items() if v}
            if not mapping:
                continue
            have = conn.execute("SELECT COUNT(*) FROM thumb_records WHERE video_id=? AND published=1", (pub["video_id"],)).fetchone()[0]
            if have >= len(mapping):
                continue
            try:
                record_publish(conn, pub["workdir"], pub["video_id"], mapping, pub.get("published_at"), pub.get("ab_test_id"),
                               pub["channel"], golden=True)
                rep["publications"] += 1
            except ValueError as e:
                rep["warnings"].append(f"pubblicazione {pub['video_id']}: {e}")
    if _has_table(conn, "learn_outcomes"):
        rep["manual_ab"] = _sync_manual_ab(conn, channel, rep["warnings"])
    return rep


def _sync_manual_ab(conn, channel: str | None, warnings: list[str]) -> int:
    """A/B letti a mano in Studio e scritti con `yt-learn outcome add --ab-winner …` (learn_outcomes.ab_json senza
    id di ab_tests: quelli con l'id li legge già sync_tests) → preferenze «ab»/«ab_tie» negli esiti. Idempotente."""
    added = 0
    q = "SELECT * FROM learn_outcomes WHERE ab_json IS NOT NULL" + (" AND channel=?" if channel else "")
    for o in ytdb.rows(conn, q, (channel,) if channel else ()):
        try:
            ab = json.loads(o.get("ab_json") or "{}")
        except ValueError:
            continue
        if not isinstance(ab, dict) or ab.get("id") is not None or ab.get("result") not in ("winner", "same", "inconclusive"):
            continue
        arms = {str(r["ab_arm"]): int(r["id"]) for r in conn.execute(
            "SELECT id, ab_arm FROM thumb_records WHERE channel=? AND video_id=? AND published=1 AND ab_arm IS NOT NULL",
            (o["channel"], o["video_id"])).fetchall()}
        if len(arms) < 2:
            continue
        ref = f"manuale:{o['video_id']}"
        with conn:
            if ab["result"] == "winner":
                w = str(ab.get("winner") or "")
                if w not in arms:
                    warnings.append(f"A/B manuale di {o['video_id']}: braccio vincente «{w}» non pubblicato")
                    continue
                for k, rid in arms.items():
                    if k != w:
                        added += add_pref(conn, channel=o["channel"], workdir="", source="ab", winner=arms[w], loser=rid,
                                          ref=ref)
            else:
                ids = sorted(arms.values())
                for i, a in enumerate(ids):
                    for b in ids[i + 1:]:
                        added += add_pref(conn, channel=o["channel"], workdir="", source="ab_tie", winner=a, loser=b,
                                          ref=ref)
    return added


def _l1_outcome(conn, video_id: str, checkpoint: str) -> dict | None:
    """Verdetto a pari età già calcolato da yt-learn (learn_outcomes), per non avere due verdetti diversi."""
    if not _has_table(conn, "learn_outcomes"):
        return None
    r = conn.execute("SELECT * FROM learn_outcomes WHERE video_id=? AND checkpoint=?", (video_id, checkpoint)).fetchone()
    if not r or r["verdict"] in (None, "polso"):
        return None
    r = dict(r)
    return {"metric": "same_age_views", "label": L1_VERDICT.get(r["verdict"], "non_leggibile"), "value": r.get("value"),
            "baseline": r.get("baseline"), "ratio": r.get("ratio"), "n": r.get("n_baseline"),
            "strength": "debole" if not r.get("tier") else "video",
            "details": {"source": "yt-learn", "metric": r.get("metric"), "tier": r.get("tier"), "verdict": r["verdict"],
                        "reason": None if r["verdict"] != "non leggibile" else "yt-learn: non leggibile",
                        "note": "rapporto con la mediana a pari età: calcolato da noi, non è un dato YouTube"}}


# ── Pubblicazione, A/B e golden set ─────────────────────────────────────────────────────────────────────────────
def _video_row(conn, video_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    return dict(r) if r else None


def record_publish(conn, workdir: str | Path, video_id: str, arms: dict[str, str] | list[str] | str,
                   published_at: str | None = None, ab_test_id: int | None = None, channel: str | None = None,
                   golden: bool = True) -> dict:
    """Lega la versione pubblicata (o i bracci dell'A/B) al video e la copia nel golden set (<studio>/data/thumb-golden)."""
    wd = Path(workdir).expanduser().resolve()
    ch = channel_of_workdir(wd, channel)
    if isinstance(arms, str):
        arms = [arms]
    if isinstance(arms, list):
        arms = {(chr(ord("A") + i) if len(arms) > 1 else ""): v for i, v in enumerate(arms)}
    v = _video_row(conn, video_id)
    pub = published_at or (v or {}).get("published_at") or _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    if ab_test_id is None and len(arms) > 1:
        r = conn.execute("SELECT id FROM ab_tests WHERE video_id=? AND kind IN ('thumbnail','both') ORDER BY id DESC LIMIT 1",
                         (video_id,)).fetchone()
        ab_test_id = int(r[0]) if r else None
    out = {"channel": ch, "video_id": video_id, "published_at": pub, "ab_test_id": ab_test_id, "arms": [], "golden": []}
    with conn:
        for arm, ver in arms.items():
            ids = resolve_versions(conn, ch, str(wd), [ver])
            if len(ids) != 1:
                raise ValueError(f"«{ver}» indica {len(ids)} versioni: dai il nome esatto del render (es. A_duo_v2)")
            conn.execute("UPDATE thumb_records SET published=1, video_id=?, ab_arm=?, ab_test_id=?, published_at=?, stage='final', "
                         "updated_at=? WHERE id=?", (video_id, arm or None, ab_test_id, pub, now_iso(), ids[0]))
            out["arms"].append({"arm": arm or None, "version": ver, "record_id": ids[0]})
    if golden:
        for a in out["arms"]:
            rec = dict(conn.execute("SELECT * FROM thumb_records WHERE id=?", (a["record_id"],)).fetchone())
            try:
                gdir = golden_add(conn, rec)
                out["golden"].append(str(gdir))
            except Exception as e:  # noqa: BLE001 — il golden set non blocca mai la registrazione
                out.setdefault("warnings", []).append(f"golden set: {a['version']} non copiato ({e})")
    return out


def _find_sidecar(rec: dict) -> Path | None:
    if rec.get("png"):
        p = Path(rec["png"]).with_suffix(".render.json")
        if p.exists():
            return p
    wd = Path(rec.get("workdir") or "")
    for d in (wd / "thumbs" / "renders", wd / "thumbs" / "final"):
        p = d / f"{rec['version']}.render.json"
        if p.exists():
            return p
    return None


SPEC_DERIVED = {"hero", "people", "artifact", "plate_src", "text", "highlight", "display_cap", "_suffix"}


def _golden_concept(rec: dict, sd: dict, assets: Path) -> dict:
    """Concept autosufficiente per il re-render: concetto originale (variante applicata) con i percorsi degli asset
    copiati in assets/. Ritagli: il PNG di livello 0 (source_path) e i suoi sidecar di yt-portrait."""
    wd = Path(rec.get("workdir") or "")
    base_concept = None
    cfile = wd / "thumbs" / "concepts.json"
    if cfile.exists():
        try:
            for c, suffix in expand_concepts(load_concepts_file(cfile)):
                if version_name(c.get("id", "X"), c.get("template"), suffix) == rec["version"]:
                    base_concept = c
                    break
        except Exception:  # noqa: BLE001
            base_concept = None
    spec = sd.get("spec") or {}
    c = dict(base_concept) if base_concept else {k: v for k, v in spec.items() if k not in SPEC_DERIVED}
    c["id"] = str(rec["concept_id"])
    assets.mkdir(parents=True, exist_ok=True)

    def cp(src: str | Path | None) -> str | None:
        if not src:
            return None
        s = Path(str(src).replace("file://", "")).expanduser()
        if not s.is_absolute():
            s = (wd / "thumbs" / s) if (wd / "thumbs" / s).exists() else (wd / s)
        if not s.exists():
            return None
        dst = assets / s.name
        if not dst.exists():
            shutil.copy2(s, dst)
        for side in (s.with_suffix(".json"), s.with_suffix(".meta.json")):
            if side.exists() and not (assets / side.name).exists():
                shutil.copy2(side, assets / side.name)
        return f"assets/{s.name}"

    people_spec = spec.get("people") or []
    people = []
    for i, p in enumerate(c.get("people") or people_spec):
        sp = people_spec[i] if i < len(people_spec) else {}
        src = sp.get("source_path") or sp.get("path") or p.get("cutout") or p.get("frame")
        q = {k: p.get(k) for k in ("role", "name", "title", "roi", "point") if p.get(k) is not None}
        got = cp(src)
        if got:
            q["cutout"] = got
        people.append(q)
    if people:
        c["people"] = people
    for k in ("frame", "cutout"):
        c.pop(k, None)
    plate = c.get("plate") if base_concept else spec.get("plate")
    if isinstance(plate, dict) and plate.get("path"):
        sp_plate = (spec.get("plate") or {}).get("path") if isinstance(spec.get("plate"), dict) else None
        got = cp(sp_plate or plate.get("path"))
        c["plate"] = {**plate, "path": got} if got else {**{k: v for k, v in plate.items() if k != "path"}, "source": "flat"}
    elif isinstance(plate, str):
        got = cp(plate)
        c["plate"] = got if got else None
    art = spec.get("artifact") or c.get("artifact")
    if art:
        got = cp(art.get("path") if isinstance(art, dict) else art)
        if got:
            c["artifact"] = got
    prop = c.get("prop")
    if isinstance(prop, dict) and prop.get("path"):
        got = cp(prop["path"])
        c["prop"] = {**prop, "path": got} if got else {k: v for k, v in prop.items() if k != "path"}
    return c


def golden_add(conn, rec: dict, root: Path | None = None) -> Path:
    """Copia la thumbnail pubblicata (PNG master, JPEG, sidecar, JSON QA, concept autosufficiente con gli asset)
    in <studio>/data/thumb-golden/<canale>/<video>/<versione>/. Mai nella repo né nel vault."""
    root = root or GOLDEN_DIR
    if not rec.get("video_id"):
        raise ValueError("record non pubblicato (manca video_id)")
    gdir = root / rec["channel"] / rec["video_id"] / rec["version"]
    gdir.mkdir(parents=True, exist_ok=True)
    side = _find_sidecar(rec)
    sd = yc.read_json(side) if side else {}
    files = {}
    png = Path(sd.get("png") or rec.get("png") or "")
    if png.name and png.is_file():
        shutil.copy2(png, gdir / "thumbnail.png")
        files["png"] = "thumbnail.png"
    jpg = Path(sd["jpg"]) if sd.get("jpg") else (png.with_suffix(".jpg") if png.name else None)
    if jpg and jpg.is_file():
        shutil.copy2(jpg, gdir / "thumbnail.jpg")
        files["jpg"] = "thumbnail.jpg"
    if side:
        shutil.copy2(side, gdir / "render.json")
        files["render"] = "render.json"
        qa = side.parent.parent / "qa" / f"{rec['version']}_qa.json"
        if qa.exists():
            shutil.copy2(qa, gdir / "qa.json")
            files["qa"] = "qa.json"
        yc.write_json(gdir / "concept.json", [_golden_concept(rec, sd, gdir / "assets")])
        files["concept"] = "concept.json"
    manifest = {"channel": rec["channel"], "video_id": rec["video_id"], "version": rec["version"], "arm": rec.get("ab_arm"),
                "published_at": rec.get("published_at"), "workdir": rec.get("workdir"), "record_id": rec.get("id"),
                "sha256": _sha256(gdir / "thumbnail.png") if files.get("png") else None, "files": files,
                "features": json.loads(rec.get("features_json") or "{}"), "copied_at": now_iso(),
                "note": "golden set locale: fixture di regressione visiva; mai nella repo, mai nel vault, mai caricato"}
    yc.write_json(gdir / "manifest.json", manifest)
    with conn:
        conn.execute("UPDATE thumb_records SET golden_dir=?, updated_at=? WHERE id=?", (str(gdir), now_iso(), rec["id"]))
    return gdir


def golden_entries(channel: str | None = None, video: str | None = None, root: Path | None = None) -> list[dict]:
    root = root or GOLDEN_DIR
    out = []
    if not root.is_dir():
        return out
    for m in sorted(root.glob("*/*/*/manifest.json")):
        try:
            d = yc.read_json(m)
        except Exception:  # noqa: BLE001
            continue
        if channel and d.get("channel") != channel:
            continue
        if video and d.get("video_id") != video:
            continue
        out.append({**d, "dir": str(m.parent)})
    return out


def image_drift(a: Path, b: Path, size: tuple[int, int] = (640, 360)) -> dict:
    """Deriva in pixel tra due render (ridotti a 640×360): media e p95 di |Δ| (livelli 0–255) e quota di pixel con
    |Δ| > 24."""
    import numpy as np
    from PIL import Image

    A = np.asarray(Image.open(a).convert("RGB").resize(size, Image.LANCZOS), np.float64)
    B = np.asarray(Image.open(b).convert("RGB").resize(size, Image.LANCZOS), np.float64)
    d = np.abs(A - B).max(axis=2)
    return {"mean": round(float(d.mean()), 3), "p95": round(float(np.percentile(d, 95)), 2),
            "share_gt24": round(float((d > 24).mean()), 4)}


def metric_drift(old: dict, new: dict, tol: dict | None = None) -> list[dict]:
    """Differenze tra le metriche di due sidecar (render_features) oltre la tolleranza, più esito e accento."""
    tol = tol or THUMB["golden_metric_tol"]
    of, om = render_features(old)
    nf, nm = render_features(new)
    out = []
    for k, t in tol.items():
        a, b = om.get(k), nm.get(k)
        if a is None and b is None:
            continue
        if a is None or b is None or abs(float(a) - float(b)) > t:
            out.append({"metric": k, "golden": a, "now": b, "tol": t})
    for k in ("pass",):
        if om.get(k) != nm.get(k):
            out.append({"metric": k, "golden": om.get(k), "now": nm.get(k)})
    for k in ("accent", "grade", "face_pct", "rows_pct"):
        if of.get(k) != nf.get(k):
            out.append({"metric": k, "golden": of.get(k), "now": nf.get(k)})
    return out


def _default_render(concept_file: Path, outdir: Path) -> Path | None:
    """yt-thumb-render sul concept del golden set con i template di oggi (stesso interprete del toolkit)."""
    proc = subprocess.run([sys.executable, str(LIB / "thumb_render.py"), "--data", str(concept_file), "--out", str(outdir),
                           "--force"], capture_output=True, text=True)
    try:
        res = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"yt-thumb-render: output non JSON (exit {proc.returncode}): {(proc.stderr or '')[-400:]}")
    rs = (res.get("outputs") or {}).get("renders") or []
    if not rs or not rs[0].get("png") or not Path(rs[0]["png"]).exists():
        raise RuntimeError(res.get("error") or (rs[0].get("error") if rs else "nessun render"))
    return Path(rs[0]["png"])


def golden_check(channel: str | None = None, video: str | None = None, out: Path | None = None,
                 render_fn: Callable[[Path, Path], Path | None] | None = None, root: Path | None = None) -> dict:
    """Regressione visiva: ri-rende i concept del golden set con i template attuali e riporta la deriva (pixel e
    metriche). Solo avvisi: non blocca mai (uscita 0)."""
    cfg = settings()
    render_fn = render_fn or _default_render
    entries = golden_entries(channel, video, root)
    out = Path(out) if out else (root or GOLDEN_DIR) / f"_check-{_dt.date.today().isoformat()}"
    rep = {"entries": len(entries), "checked": 0, "drift": [], "warnings": [], "out": str(out)}
    if not entries:
        rep["warnings"].append("golden set vuoto: nessuna thumbnail pubblicata registrata (yt-thumb-learn publish)")
    for e in entries:
        gdir = Path(e["dir"])
        cf, png = gdir / "concept.json", gdir / "thumbnail.png"
        tag = f"{e.get('channel')}/{e.get('video_id')}/{e.get('version')}"
        if not cf.exists() or not png.exists():
            rep["warnings"].append(f"{tag}: concept o PNG mancanti nel golden set")
            continue
        od = out / e["channel"] / e["video_id"] / e["version"]
        od.mkdir(parents=True, exist_ok=True)
        try:
            new_png = render_fn(cf, od)
        except Exception as ex:  # noqa: BLE001
            rep["warnings"].append(f"{tag}: re-render fallito ({str(ex)[:300]})")
            continue
        if not new_png or not Path(new_png).exists():
            rep["warnings"].append(f"{tag}: re-render senza PNG")
            continue
        px = image_drift(png, Path(new_png))
        old_sd = gdir / "render.json"
        new_sd = Path(new_png).with_suffix(".render.json")
        md = metric_drift(yc.read_json(old_sd), yc.read_json(new_sd)) if old_sd.exists() and new_sd.exists() else []
        item = {"entry": tag, "pixels": px, "metrics": md, "new_png": str(new_png)}
        rep["drift"].append(item)
        rep["checked"] += 1
        if px["mean"] > cfg["golden_px_mean_warn"] or px["share_gt24"] > cfg["golden_px_share_warn"]:
            rep["warnings"].append(f"{tag}: deriva visiva (media {px['mean']} livelli, {px['share_gt24']:.1%} dei pixel > 24): "
                                   "guarda il confronto prima di unire il cambio dei template")
        for d in md:
            rep["warnings"].append(f"{tag}: {d['metric']} {d.get('golden')} → {d.get('now')}")
    if entries:
        yc.write_json(out / "report.json", rep)
    return rep


def sync_tests(conn, channel: str) -> dict:
    """A/B nativi (kind thumbnail|both) e pre-test (kind pretest) di ab_tests → preferenze a coppie negli «esiti».
    Vincitore = id del braccio o nome del file; «stesso rendimento»/«inconclusivo» = pareggio (13 §3.2)."""
    rows = ytdb.rows(conn, "SELECT * FROM ab_tests WHERE channel=? AND kind IN ('thumbnail','both','pretest')", (channel,))
    rep = {"tests": len(rows), "decisive": 0, "ties": 0, "prefs_added": 0, "unmapped": []}
    with conn:
        for t in rows:
            try:
                variants = json.loads(t.get("variants_json") or "[]")
            except ValueError:
                variants = []
            arm_rec: dict[str, int] = {}
            for v in variants if isinstance(variants, list) else []:
                aid = str(v.get("id") or "")
                stem = Path(str(v.get("file") or "")).name
                stem = re.sub(r"\.(png|jpe?g)$", "", stem)
                r = None
                if stem:
                    r = conn.execute("SELECT id FROM thumb_records WHERE channel=? AND version=? ORDER BY "
                                     "(video_id = ?) DESC, id DESC LIMIT 1", (channel, stem, t.get("video_id") or "")).fetchone()
                if not r and t.get("video_id") and aid:
                    r = conn.execute("SELECT id FROM thumb_records WHERE channel=? AND video_id=? AND ab_arm=?",
                                     (channel, t["video_id"], aid)).fetchone()
                if r:
                    arm_rec[aid or stem] = int(r[0])
            if t.get("video_id"):
                for r in conn.execute("SELECT id, ab_arm FROM thumb_records WHERE channel=? AND video_id=? AND ab_arm IS NOT NULL",
                                      (channel, t["video_id"])).fetchall():
                    arm_rec.setdefault(str(r["ab_arm"]), int(r["id"]))
            if len(arm_rec) < 2:
                rep["unmapped"].append(t["id"])
                continue
            win = str(t.get("winner") or "").strip()
            wl = win.lower()
            src = "pretest" if t.get("kind") == "pretest" else "ab"
            if not win or wl in ("inconclusivo", "inconcludente", "inconclusive", "pari", "same", "tie", "stesso rendimento",
                                 "prestazioni simili", "performed same"):
                if t.get("ended_at") or win:
                    ids = list(arm_rec.values())
                    for i, a in enumerate(ids):
                        for b in ids[i + 1:]:
                            rep["prefs_added"] += add_pref(conn, channel=channel, workdir="", source=f"{src}_tie", winner=a,
                                                           loser=b, ref=str(t["id"]))
                    rep["ties"] += 1
                continue
            wkey = win if win in arm_rec else next((k for k in arm_rec if Path(win).stem == k or k.endswith(win)), None)
            if not wkey:
                rep["unmapped"].append(t["id"])
                continue
            rep["decisive"] += 1
            for k, rid in arm_rec.items():
                if k != wkey:
                    rep["prefs_added"] += add_pref(conn, channel=channel, workdir="", source=src, winner=arm_rec[wkey],
                                                   loser=rid, ref=str(t["id"]))
    return rep


# ── Esiti a pari età (D+7, D+28) ────────────────────────────────────────────────────────────────────────────────
def _channel_id(conn, channel: str) -> str | None:
    r = conn.execute("SELECT id FROM channels WHERE slug=? OR id=?", (channel, channel)).fetchone()
    return r[0] if r else None


def views_at_age(conn, video_id: str, published: _dt.date, age: int, tol: int) -> tuple[float | None, str]:
    """Visualizzazioni a `age` giorni dall'uscita: basic_daily (Tier 2, somma dei giorni) oppure le istantanee di
    video_stats_daily (Tier 0: la più vicina entro ±tol giorni, o l'interpolazione tra due che stanno a cavallo)."""
    end = published + _dt.timedelta(days=age)
    rows = conn.execute("SELECT date, views FROM basic_daily WHERE video_id=? AND date>=? AND date<?",
                        (video_id, published.isoformat(), end.isoformat())).fetchall()
    if len(rows) >= max(1, age - 1):
        return float(sum(r[1] or 0 for r in rows)), "basic_daily"
    snaps = [(_date(r[0]), r[1]) for r in conn.execute("SELECT date, views FROM video_stats_daily WHERE video_id=? AND views IS NOT NULL "
                                                       "ORDER BY date", (video_id,)).fetchall()]
    snaps = [((d - published).days, v) for d, v in snaps if d]
    if not snaps:
        return None, "nessuna istantanea"
    exact = [(abs(a - age), v) for a, v in snaps if abs(a - age) <= tol]
    if exact:
        return float(min(exact)[1]), "video_stats_daily"
    before = [(a, v) for a, v in snaps if a < age]
    after = [(a, v) for a, v in snaps if a > age]
    if before and after:
        (a0, v0), (a1, v1) = before[-1], after[0]
        if a1 - a0 <= max(3, 2 * tol + 1):
            return float(v0 + (v1 - v0) * (age - a0) / (a1 - a0)), "video_stats_daily (interpolato)"
    return None, "nessuna istantanea a pari età"


def _baseline_videos(conn, channel_id: str, video: dict, age: int, today: _dt.date, window: int) -> list[dict]:
    pub = _date(video.get("published_at"))
    rows = ytdb.rows(conn, "SELECT id, published_at, format FROM videos WHERE channel_id=? AND id<>? AND published_at IS NOT NULL "
                           "ORDER BY published_at DESC", (channel_id, video["id"]))
    fmt = video.get("format") or "long"
    out = []
    for r in rows:
        d = _date(r["published_at"])
        if not d or (r.get("format") or "long") != fmt or (today - d).days < age:
            continue
        if pub and d >= pub:
            continue                                   # solo i video precedenti (09: «vs mediana ultime N»)
        out.append(r)
        if len(out) >= window:
            break
    return out


def same_age_outcome(conn, channel_id: str, video: dict, checkpoint: str, today: _dt.date, cfg: dict) -> dict:
    age = cfg["checkpoints"][checkpoint]
    tol = cfg["views_tolerance"].get(checkpoint, 1)
    pub = _date(video.get("published_at"))
    res = {"metric": "same_age_views", "strength": "debole", "label": "non_leggibile", "details": {"age": age, "tier": 0}}
    if not pub:
        res["details"]["reason"] = "data di pubblicazione ignota"
        return res
    val, src = views_at_age(conn, video["id"], pub, age, tol)
    res["details"]["source"] = src
    if val is None:
        res["details"]["reason"] = src
        return res
    base = []
    for b in _baseline_videos(conn, channel_id, video, age, today, cfg["baseline_window"]):
        bv, _ = views_at_age(conn, b["id"], _date(b["published_at"]), age, tol)
        if bv is not None:
            base.append(bv)
    res.update({"value": val, "n": len(base)})
    if len(base) < int(cfg["min_baseline"]):
        res["details"]["reason"] = f"solo {len(base)} video di confronto a pari età (servono ≥ {cfg['min_baseline']})"
        return res
    med = statistics.median(base)
    ratio = val / med if med > 0 else None
    res.update({"baseline": med, "ratio": round(ratio, 3) if ratio is not None else None})
    if ratio is None:
        res["details"]["reason"] = "mediana a zero"
        return res
    if ratio >= cfg["above_ratio"]:
        res["label"] = "sopra"
    elif ratio <= cfg["below_ratio"]:
        res["label"] = "sotto"
    else:
        res["label"] = "rumore_sopra" if ratio >= 1 else "rumore_sotto"
    res["details"]["note"] = "rapporto con la mediana a pari età: calcolato da noi, non è un dato YouTube"
    return res


def _reach(conn, video_id: str, start: _dt.date, days: int) -> dict[str, list[float]]:
    """{traffic_source: [impressioni, click]} nei primi `days` giorni (un solo tipo di report: basic, se no combined)."""
    end = (start + _dt.timedelta(days=days)).isoformat()
    for rt in ("channel_reach_basic_a1", "channel_reach_combined_a1"):
        rows = conn.execute("SELECT traffic_source, SUM(impressions), SUM(impressions*COALESCE(ctr,0)) FROM reach_daily "
                            "WHERE video_id=? AND report_type=? AND date>=? AND date<? GROUP BY traffic_source",
                            (video_id, rt, start.isoformat(), end)).fetchall()
        if rows:
            return {str(r[0] or ""): [float(r[1] or 0), float(r[2] or 0)] for r in rows}
    return {}


def ctr_outcome(conn, channel_id: str, video: dict, checkpoint: str, today: _dt.date, cfg: dict) -> dict:
    """CTR delle impressioni (Reporting API) nei primi N giorni, sulla fonte di traffico principale, contro la base
    del canale nella stessa fonte e finestra; differenza solo se fuori dal rumore (09 §3 regola 6)."""
    age = cfg["checkpoints"][checkpoint]
    pub = _date(video.get("published_at"))
    res = {"metric": "ctr", "strength": "ctr", "label": "non_leggibile", "details": {"age": age, "tier": 2}}
    if not pub:
        res["details"]["reason"] = "data di pubblicazione ignota"
        return res
    reach = _reach(conn, video["id"], pub, age)
    if not reach:
        res["details"]["reason"] = "nessuna impressione in reach_daily (Reporting API assente o non ancora caricata)"
        return res
    src, (impr, clicks) = max(reach.items(), key=lambda kv: kv[1][0])
    res.update({"impressions": int(impr), "details": {**res["details"], "traffic_source": src or "tutte",
                                                      "sources": {k: int(v[0]) for k, v in reach.items()}}})
    if impr < cfg["ctr_min_impressions"]:
        res["details"]["reason"] = f"{int(impr)} impressioni (< {cfg['ctr_min_impressions']}): CTR non ancora leggibile"
        return res
    p1 = clicks / impr
    bi = bc = 0.0
    n = 0
    for b in _baseline_videos(conn, channel_id, video, age, today, cfg["baseline_window"]):
        r = _reach(conn, b["id"], _date(b["published_at"]), age).get(src)
        if r and r[0] >= cfg["ctr_min_baseline_impressions"]:
            bi += r[0]
            bc += r[1]
            n += 1
    res.update({"value": round(p1, 5), "n": n})
    if n < int(cfg["min_baseline"]) or bi <= 0:
        res["details"]["reason"] = f"solo {n} video di confronto con impressioni nella stessa fonte (servono ≥ {cfg['min_baseline']})"
        return res
    p0 = bc / bi
    se = math.sqrt(max(p1 * (1 - p1), 1e-9) / impr + max(p0 * (1 - p0), 1e-9) / bi)
    thr = 1.96 * se
    res.update({"baseline": round(p0, 5), "ratio": round(p1 / p0, 3) if p0 > 0 else None})
    res["details"].update({"threshold_pp": round(thr * 100, 2), "baseline_impressions": int(bi)})
    if p1 - p0 > thr:
        res["label"] = "sopra"
    elif p0 - p1 > thr:
        res["label"] = "sotto"
    else:
        res["label"] = "rumore_sopra" if p1 >= p0 else "rumore_sotto"
        res["details"]["note"] = "differenza dentro il rumore statistico"
    return res


def pull_outcomes(conn, channel: str | None = None, video: str | None = None, today: str | _dt.date | None = None,
                  due_only: bool = True, profile: dict | None = None) -> dict:
    """Esiti per ogni video con thumbnail pubblicata, ai checkpoint scaduti (t48 solo igiene: mai nei prior).
    Peso nei prior: CTR se leggibile, altrimenti visualizzazioni a pari età (Tier 0, «debole»); con più bracci
    pubblicati conta solo ciò che hanno in comune (mixed)."""
    cfg = settings()
    td = _today(today)
    synced = sync_from_learn(conn, channel)
    q = "SELECT * FROM thumb_records WHERE published=1 AND video_id IS NOT NULL"
    args: list = []
    if channel:
        q += " AND channel=?"
        args.append(channel)
    if video:
        q += " AND video_id=?"
        args.append(video)
    recs = ytdb.rows(conn, q, args)
    by_video: dict[str, list[dict]] = {}
    for r in recs:
        by_video.setdefault(r["video_id"], []).append(r)
    rep = {"videos": len(by_video), "pulled": [], "skipped": [], "tests": {}, "yt_learn": synced}
    channels = set()
    for vid, rs in by_video.items():
        ch = rs[0]["channel"]
        channels.add(ch)
        cid = _channel_id(conn, ch)
        vrow = _video_row(conn, vid) or {"id": vid, "format": "long"}
        if not vrow.get("published_at"):
            vrow["published_at"] = min((r["published_at"] for r in rs if r.get("published_at")), default=None)
        pub = _date(vrow.get("published_at"))
        if not pub:
            rep["skipped"].append({"video_id": vid, "reason": "data di pubblicazione ignota"})
            continue
        for ck, days in cfg["checkpoints"].items():
            if (td - pub).days < days:
                continue
            prev = conn.execute("SELECT status, attempts, last_attempt FROM thumb_checkpoints WHERE video_id=? AND checkpoint=?",
                                (vid, ck)).fetchone()
            if due_only and prev and (prev["status"] == "done" or prev["attempts"] >= 3
                                      or (_date(prev["last_attempt"]) or td) >= td):
                continue
            mixed = len(rs) > 1
            results = []
            if cid:
                results = [ctr_outcome(conn, cid, vrow, ck, td, cfg),
                           _l1_outcome(conn, vid, ck) or same_age_outcome(conn, cid, vrow, ck, td, cfg)]
            else:
                results = [{"metric": "same_age_views", "strength": "debole", "label": "non_leggibile",
                            "details": {"reason": f"canale {ch} assente dalla tabella channels (yt-collect)"}}]
            w_ck = 0.0 if ck == "t48" else float(cfg.get(f"outcome_weight_{ck}", 0.0))
            used = False
            with conn:
                for res in results:
                    weight = 0.0
                    if not used and res["label"] != "non_leggibile" and w_ck > 0:
                        weight, used = w_ck, True
                    conn.execute(
                        "INSERT INTO thumb_outcomes(channel, video_id, checkpoint, metric, value, baseline, ratio, n, impressions, "
                        "label, strength, weight, mixed, record_ids, details_json, measured_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(video_id, checkpoint, metric) DO UPDATE SET value=excluded.value, baseline=excluded.baseline, "
                        "ratio=excluded.ratio, n=excluded.n, impressions=excluded.impressions, label=excluded.label, "
                        "strength=excluded.strength, weight=excluded.weight, mixed=excluded.mixed, record_ids=excluded.record_ids, "
                        "details_json=excluded.details_json, measured_at=excluded.measured_at",
                        (ch, vid, ck, res["metric"], res.get("value"), res.get("baseline"), res.get("ratio"), res.get("n"),
                         res.get("impressions"), res["label"], res["strength"], weight, int(mixed),
                         json.dumps([r["id"] for r in rs]), json.dumps(res.get("details") or {}, ensure_ascii=False, default=str),
                         now_iso()))
                readable = any(r["label"] != "non_leggibile" for r in results)
                status = "done" if readable or ck == "t48" else "insufficient"
                conn.execute("INSERT INTO thumb_checkpoints(channel, video_id, checkpoint, status, attempts, last_attempt) "
                             "VALUES (?,?,?,?,1,?) ON CONFLICT(video_id, checkpoint) DO UPDATE SET status=excluded.status, "
                             "attempts=thumb_checkpoints.attempts+1, last_attempt=excluded.last_attempt",
                             (ch, vid, ck, status, td.isoformat()))
            rep["pulled"].append({"video_id": vid, "checkpoint": ck, "status": status, "mixed": mixed,
                                  "results": [{k: r.get(k) for k in ("metric", "label", "value", "baseline", "ratio", "n",
                                                                     "impressions", "strength")}
                                              | {"reason": (r.get("details") or {}).get("reason")} for r in results]})
    for ch in channels:
        rep["tests"][ch] = sync_tests(conn, ch)
        rebuild_priors(conn, ch, profile if channel else None)
    return rep


# ── Prior (Beta per caratteristica e valore, due segnali) ───────────────────────────────────────────────────────
LABEL_SCORE = {"sopra": (1.0, 0.0), "sotto": (0.0, 1.0), "rumore_sopra": (0.5, 0.0), "rumore_sotto": (0.0, 0.5), "in_linea": (0.0, 0.0)}


def beta_stats(a: float, b: float) -> dict:
    n = a + b
    mean = a / n
    sd = math.sqrt(a * b / (n * n * (n + 1)))
    lo, hi = max(0.0, mean - 1.2816 * sd), min(1.0, mean + 1.2816 * sd)     # intervallo all'80 % (approssimazione normale)
    return {"mean": mean, "sd": sd, "lo80": lo, "hi80": hi, "width80": hi - lo}


def confidence(n_jobs: int, width80: float, signal: str = "scelte", comparables: int | None = None) -> str:
    """13 §3.3: < 5 job «bassa»; 5–14 e intervallo ≤ 0,4 «media»; ≥ 15 e ≤ 0,2 «alta». Gli esiti restano «bassa»
    con meno di 4 video confrontabili."""
    if signal == "esiti" and comparables is not None and comparables < 4:
        return "bassa"
    if n_jobs >= 15 and width80 <= 0.2:
        return "alta"
    if n_jobs >= 5 and width80 <= 0.4:
        return "media"
    return "bassa"


def _age_factor(created_at: str | None, cfg: dict) -> float:
    d = _date(created_at)
    return 0.5 if d and (_dt.date.today() - d).days > cfg["old_days"] else 1.0


@functools.lru_cache(maxsize=1024)
def job_key(workdir: str | None) -> str:
    """Il «lavoro» che conta per n e per il tetto di peso: il video. Più cartelle sullo stesso episodio (giri di uno
    studio, rifacimenti) condividono «video_key» nel project.json e contano una volta (come yt-learn)."""
    if not workdir:
        return ""
    try:
        vk = (yc.read_json(Path(workdir) / "project.json") or {}).get("video_key")
    except Exception:  # noqa: BLE001 — project.json assente o illeggibile: vale la cartella
        vk = None
    return str(vk) if vk else (Path(str(workdir)).name or str(workdir))


def compute_priors(conn, channel: str, profile: dict | None = None, exclude_video: str | None = None) -> dict:
    """{(segnale, caratteristica, valore): statistiche}. Scelte = preferenze del G2 (delegate: peso 0); esiti = A/B,
    pre-test (decisivi) e verdetti D+7/D+28 sulle caratteristiche del video (con più bracci: solo quelle comuni)."""
    cfg = settings()
    if profile is None:
        profile = load_profile(channel)
    defaults = knowledge_defaults(profile)
    S, bonus = float(cfg["prior_strength"]), float(cfg["default_bonus"])
    recs = {int(r["id"]): r for r in ytdb.rows(conn, "SELECT id, workdir, video_id, features_json FROM thumb_records WHERE channel=?",
                                                (channel,))}
    feats = {i: json.loads(r["features_json"] or "{}") for i, r in recs.items()}
    acc: dict[tuple, dict] = {}

    def slot(sig: str, f: str, v: str) -> dict:
        return acc.setdefault((sig, f, v), {"a": 0.0, "b": 0.0, "jobs": set(), "decisive_jobs": set(), "ev": set(),
                                            "elo": cfg["elo_start"], "clean": set(), "clean_wins": 0.0, "clean_losses": 0.0})

    prefs = ytdb.rows(conn, "SELECT * FROM thumb_prefs WHERE channel=? ORDER BY created_at, id", (channel,))
    # Un lavoro (un video) vale UNA scelta per caratteristica e valore, come in yt-learn (13 §3.2): con 1 render scelto e
    # 8 scartati il valore vincente prende pref_weight una volta, non otto, e ogni valore scartato una volta. Così un
    # solo video non ribalta una media (small-sample guard). Stesso tetto per un A/B: un test = un lavoro.
    side: dict[tuple, float] = {}           # (segnale, caratteristica, valore, lavoro, "a"|"b") → peso
    clean_side: dict[tuple, float] = {}
    elo_pairs: dict[tuple, list] = {}       # (lavoro, caratteristica) → coppie distinte (vincente, perdente), in ordine
    for p in prefs:
        w_rec, l_rec = recs.get(int(p["winner_id"])), recs.get(int(p["loser_id"]))
        if not w_rec or not l_rec:
            continue
        if exclude_video and exclude_video in (w_rec.get("video_id"), l_rec.get("video_id")) and p["source"] not in ("g2", "delegated"):
            continue
        src = p["source"]
        if src in ("g2", "delegated"):
            sig, w = "scelte", (float(cfg["pref_weight"]) if src == "g2" else 0.0)
            job = job_key(p.get("workdir") or w_rec.get("workdir"))
        else:
            sig, w = "esiti", float(cfg["ab_weight"])
            job = f"test:{p.get('ref')}"
        w *= _age_factor(p.get("created_at"), cfg)
        fw, fl = feats.get(int(p["winner_id"]), {}), feats.get(int(p["loser_id"]), {})
        for f in FEATURES:
            vw, vl = fw.get(f), fl.get(f)
            if vw is None or vl is None or vw == vl:
                continue
            sw, sl = slot(sig, f, vw), slot(sig, f, vl)
            tie = src.endswith("_tie")
            if tie:
                for v in (vw, vl):
                    for sd in ("a", "b"):
                        side[(sig, f, v, job, sd)] = max(side.get((sig, f, v, job, sd), 0.0), w / 2)
            else:
                side[(sig, f, vw, job, "a")] = max(side.get((sig, f, vw, job, "a"), 0.0), w)
                side[(sig, f, vl, job, "b")] = max(side.get((sig, f, vl, job, "b"), 0.0), w)
                if sig == "scelte" and w > 0:
                    pairs = elo_pairs.setdefault((job, f), [])
                    if (vw, vl) not in pairs:
                        pairs.append((vw, vl))
                if sig == "esiti":
                    sw["decisive_jobs"].add(job)
                    sl["decisive_jobs"].add(job)
            # confronto «pulito» (per le proposte Tier B): stesso template, salvo che la caratteristica sia template o leva
            clean = f in ("template", "lever") or (fw.get("template") is not None and fw.get("template") == fl.get("template"))
            for s, rid in ((sw, p["winner_id"]), (sl, p["loser_id"])):
                if w > 0:
                    s["jobs"].add(job)
                    if clean:
                        s["clean"].add(job)
                s["ev"].add(int(rid))
            if clean and w > 0 and not tie:
                clean_side[(sig, f, vw, job, "a")] = max(clean_side.get((sig, f, vw, job, "a"), 0.0), w)
                clean_side[(sig, f, vl, job, "b")] = max(clean_side.get((sig, f, vl, job, "b"), 0.0), w)
    for (sig, f, v, _job, sd), w in side.items():
        slot(sig, f, v)["a" if sd == "a" else "b"] += w
    for (sig, f, v, _job, sd), w in clean_side.items():
        slot(sig, f, v)["clean_wins" if sd == "a" else "clean_losses"] += w
    for (job, f), pairs in elo_pairs.items():   # Elo (13 §3.2): al più K per lavoro e caratteristica
        k = cfg["elo_k"] / len(pairs)
        for vw, vl in pairs:
            sw, sl = slot("scelte", f, vw), slot("scelte", f, vl)
            ew = 1 / (1 + 10 ** ((sl["elo"] - sw["elo"]) / 400))
            sw["elo"] += k * (1 - ew)
            sl["elo"] -= k * (1 - ew)
    outs = ytdb.rows(conn, "SELECT * FROM thumb_outcomes WHERE channel=? AND weight>0", (channel,))
    # un video conta una volta: vale la lettura più matura (D+28 sostituisce D+7), come in yt-learn
    latest: dict[str, dict] = {}
    for o in outs:
        rank = {"d28": 2, "d7": 1}.get(o.get("checkpoint"), 0)
        cur = latest.get(o["video_id"])
        if cur is None or rank > {"d28": 2, "d7": 1}.get(cur.get("checkpoint"), 0):
            latest[o["video_id"]] = o
    outs = list(latest.values())
    comparables: dict[tuple, int] = {}
    for o in outs:
        if exclude_video and o["video_id"] == exclude_video:
            continue
        sa, sb = LABEL_SCORE.get(o["label"], (0.0, 0.0))
        if not (sa or sb):
            continue
        ids = [int(x) for x in json.loads(o.get("record_ids") or "[]") if int(x) in feats]
        if not ids:
            continue
        common = {f: feats[ids[0]].get(f) for f in FEATURES}
        for i in ids[1:]:
            common = {f: v for f, v in common.items() if v is not None and feats[i].get(f) == v}
        w = float(o["weight"]) * _age_factor(o.get("measured_at"), cfg)
        for f, v in common.items():
            if v is None:
                continue
            s = slot("esiti", f, v)
            s["a"] += w * sa
            s["b"] += w * sb
            s["jobs"].add(f"video:{o['video_id']}")
            s["ev"].add(o["video_id"])
            comparables[("esiti", f, v)] = max(comparables.get(("esiti", f, v), 0), int(o.get("n") or 0))
    # tutti i valori visti nei record entrano col solo prior (così il ranking conosce anche i valori mai confrontati)
    for fe in feats.values():
        for f in FEATURES:
            v = fe.get(f)
            if v is not None:
                for sig in SIGNALS:
                    slot(sig, f, v)
    for f, vals in defaults.items():
        for v in vals:
            for sig in SIGNALS:
                slot(sig, f, v)
    out = {}
    for (sig, f, v), s in acc.items():
        m0 = 0.5 + (bonus if v in defaults.get(f, set()) else 0.0)
        a, b = S * m0 + s["a"], S * (1 - m0) + s["b"]
        st = beta_stats(a, b)
        nj = len(s["jobs"])
        out[(sig, f, v)] = {**st, "alpha": a, "beta": b, "prior_mean": m0, "wins": s["a"], "losses": s["b"], "n_jobs": nj,
                            "n_decisive": len(s["decisive_jobs"]), "elo": round(s["elo"], 1) if sig == "scelte" else None,
                            "n_clean": len(s["clean"]), "clean_wins": s["clean_wins"], "clean_losses": s["clean_losses"],
                            "evidence": sorted(map(str, s["ev"]))[:50],
                            "confidence": confidence(nj, st["width80"], sig, comparables.get((sig, f, v)) if sig == "esiti" else None)}
    return out


def rebuild_priors(conn, channel: str, profile: dict | None = None) -> int:
    pri = compute_priors(conn, channel, profile)
    ts = now_iso()
    with conn:
        conn.execute("DELETE FROM thumb_priors WHERE channel=?", (channel,))
        conn.executemany("INSERT INTO thumb_priors(channel, signal, feature, value, alpha, beta, prior_mean, wins, losses, n_jobs, "
                         "n_decisive, elo, evidence, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         [(channel, sig, f, v, s["alpha"], s["beta"], s["prior_mean"], s["wins"], s["losses"], s["n_jobs"],
                           s["n_decisive"], s["elo"], json.dumps(s["evidence"]), ts) for (sig, f, v), s in pri.items()])
    return len(pri)


def load_priors(conn, channel: str) -> dict:
    out = {}
    for r in ytdb.rows(conn, "SELECT * FROM thumb_priors WHERE channel=?", (channel,)):
        st = beta_stats(r["alpha"], r["beta"])
        out[(r["signal"], r["feature"], r["value"])] = {**r, **st,
                                                         "confidence": confidence(r["n_jobs"], st["width80"], r["signal"])}
    return out


def _prior_for(pri: dict, sig: str, f: str, v: str, defaults: dict, cfg: dict) -> dict:
    p = pri.get((sig, f, v))
    if p:
        return p
    m0 = 0.5 + (cfg["default_bonus"] if v in defaults.get(f, set()) else 0.0)
    a, b = cfg["prior_strength"] * m0, cfg["prior_strength"] * (1 - m0)
    return {"alpha": a, "beta": b, "prior_mean": m0, "n_jobs": 0, "n_decisive": 0, "elo": None, **beta_stats(a, b),
            "confidence": "bassa"}


# ── Scelta dei concept: 2 da sfruttare + 1 da esplorare (Thompson) ──────────────────────────────────────────────
def _policy_check(f: dict, allowed: dict[str, set[str]]) -> str | None:
    if f.get("guest_style") == "graphic" and "graphic" not in allowed.get("guest_style", {"none", "graphic"}):
        return "guest_style graphic non ammesso dal profilo"
    for k, vals in allowed.items():
        v = f.get(k)
        if v is not None and v not in vals:
            return f"{k} «{v}» fuori dai valori ammessi dal profilo ({', '.join(sorted(vals))})"
    return None


def rank_concepts(conn, channel: str, concepts: list[dict], profile: dict | None = None, seed: int | None = None,
                  keep: int | None = None, explore: int | None = None, min_levers: int | None = None,
                  base: Path | None = None) -> dict:
    """Ordina i concept candidati con i prior del canale. Sfruttamento = media a posteriori più alta (segnale «esiti» se
    ha confidenza almeno media per tutti i candidati, altrimenti «scelte»); esplorazione = estrazione di Thompson tra i
    restanti. Mai meno di `min_levers` leve. Un concept fuori regola (profilo) è escluso, non corretto."""
    cfg = settings()
    profile = load_profile(channel) if profile is None else profile
    defaults = knowledge_defaults(profile)
    allowed = allowed_values(profile)
    pri = compute_priors(conn, channel, profile)
    rng = random.Random(seed)
    keep = int(keep or cfg["keep"])
    explore = max(1, int(cfg["explore_arms"] if explore is None else explore))   # mai senza esplorazione (13 §3.4)
    min_levers = int(min_levers or cfg["min_levers"])
    cands, excluded = [], []
    for c in concepts:
        f = concept_features(c, profile, base)
        why = _policy_check(f, allowed)
        if why:
            excluded.append({"id": c.get("id"), "reason": why})
            continue
        scores, evidence = {}, []
        for sig in SIGNALS:
            ps = [(k, v, _prior_for(pri, sig, k, v, defaults, cfg)) for k, v in f.items() if v is not None and k in CONCEPT_FEATURES]
            if not ps:
                scores[sig] = {"mean": 0.5, "n": 0, "width80": 1.0, "confidence": "bassa"}
                continue
            ns = sorted(p["n_jobs"] for _, _, p in ps)
            n_med = ns[len(ns) // 2]
            w80 = sum(p["width80"] for _, _, p in ps) / len(ps)
            # sfruttamento (13 §3.3, 07 §16): un valore con confidenza «bassa» informa ma non sposta l'ordine, che resta
            # quello del knowledge e del profilo (media del prior); dalla «media» in su conta la media a posteriori.
            # L'esplorazione (Thompson, sotto) usa sempre la posteriore: è lì che i dati nuovi lavorano da subito.
            exploit = [p["mean"] if p["confidence"] in ("media", "alta") else p["prior_mean"] for _, _, p in ps]
            scores[sig] = {"mean": sum(exploit) / len(exploit), "posterior": sum(p["mean"] for _, _, p in ps) / len(ps),
                           "learned": any(p["confidence"] in ("media", "alta") for _, _, p in ps),
                           "n": n_med, "width80": w80,
                           "confidence": confidence(n_med, w80, sig, None if sig == "scelte" else n_med),
                           "draws": [(k, v, p) for k, v, p in ps]}
            for k, v, p in ps:
                if p["n_jobs"] or sig == "scelte":
                    evidence.append({"segnale": sig, "caratteristica": PREFIX + k, "valore": v, "media": round(p["mean"], 3),
                                     "prior": round(p["prior_mean"], 3), "n": p["n_jobs"], "confidenza": p["confidence"],
                                     "elo": p.get("elo")})
        evidence.sort(key=lambda e: (-e["n"], -abs(e["media"] - e["prior"])))
        cands.append({"id": c.get("id"), "lever": f.get("lever"), "template": f.get("template"), "features": f,
                      "scores": scores, "evidence": evidence[:8]})
    sig = "esiti" if cands and all(c["scores"]["esiti"]["confidence"] != "bassa" for c in cands) else "scelte"
    for c in cands:
        c["draw"] = sum(rng.betavariate(p["alpha"], p["beta"]) for _, _, p in c["scores"][sig].get("draws", [])) / max(
            1, len(c["scores"][sig].get("draws", [])))
    by_mean = sorted(cands, key=lambda c: (-c["scores"][sig]["mean"], str(c["id"])))
    n_exploit = max(1, min(keep, len(by_mean)) - explore) if len(by_mean) > 1 else len(by_mean)
    exploit = by_mean[:n_exploit]
    rest = by_mean[n_exploit:]
    explore_pick = sorted(rest, key=lambda c: -c["draw"])[:max(0, min(explore, keep - len(exploit)))]
    if not explore_pick and len(exploit) > 1 and explore > 0:                    # meno candidati di keep: l'ultimo esplora
        explore_pick = [exploit.pop()]
    selected = exploit + explore_pick
    levers = {c["lever"] for c in selected if c["lever"]}
    swapped: set = set()
    if len(levers) < min_levers:
        others = [c for c in by_mean if c not in selected and c["lever"] and c["lever"] not in levers]
        if others:
            out_c = (exploit[-1] if len(exploit) > 1 else (explore_pick[-1] if explore_pick else None))
            if out_c is not None:
                swap_in = others[0]
                swapped.add(str(swap_in["id"]))
                if out_c in exploit:
                    exploit[exploit.index(out_c)] = swap_in
                else:
                    explore_pick[explore_pick.index(out_c)] = swap_in
                selected = exploit + explore_pick
    other_sig = "esiti" if sig == "scelte" else "scelte"
    alt = sorted(cands, key=lambda c: (-c["scores"][other_sig]["mean"], str(c["id"])))[:len(exploit)]
    disagree = bool(any(c["scores"][other_sig]["confidence"] != "bassa" for c in cands)
                    and {c["id"] for c in alt} != {c["id"] for c in exploit})

    def view(c: dict, role: str) -> dict:
        s = c["scores"]
        reason = (("media a posteriori più alta" if s[sig].get("learned") else
                   "ordine del knowledge e del profilo (priori ancora deboli)") if role == "sfruttamento" else
                  f"estrazione di Thompson tra i restanti (n mediano {s[sig]['n']}: poco provato)")
        if str(c["id"]) in swapped:
            reason = f"seconda leva obbligatoria (mai meno di {min_levers} leve, 07 §5.2): entra al posto dell'ultimo sfruttamento"
        return {"id": c["id"], "ruolo": role, "lever": c["lever"], "template": c["template"],
                "punteggio": {k: round(v["mean"], 3) for k, v in s.items()},
                "posteriore": {k: round(v.get("posterior", v["mean"]), 3) for k, v in s.items()},
                "estrazione": round(c["draw"], 3),
                "n": s[sig]["n"], "confidenza": s[sig]["confidence"], "segnale": sig, "motivo": reason,
                "evidenze": c["evidence"],
                "etichetta": f"[appreso: {sig}, n={s[sig]['n']}, conf. {s[sig]['confidence']}]"}

    chosen = [view(c, "sfruttamento") for c in exploit] + [view(c, "esplorazione") for c in explore_pick]
    dropped = [view(c, "scartato") for c in by_mean if c not in selected]
    note = None
    if all(c["scores"][sig]["confidence"] == "bassa" for c in cands):
        note = ("confidenza bassa su tutti i concept: l'ordine di sfruttamento segue i default del knowledge e del profilo "
                "(07 §5.2); i prior sono solo informazione (la «posteriore» è mostrata accanto) e lavorano nell'esplorazione")
    return {"channel": channel, "segnale": sig, "keep": keep, "selezionati": chosen, "scartati": dropped, "esclusi": excluded,
            "disaccordo": disagree, "nota": note, "seed": seed,
            "regole": "il ranking ordina e annota: non cambia template, grade, guest_style né i controlli (13 §2)"}


# ── Report, playbook, post-mortem, proposte ─────────────────────────────────────────────────────────────────────
def priors_report(conn, channel: str, signal: str | None = None, top: int = 40) -> dict:
    pri = compute_priors(conn, channel)
    rows = []
    for (sig, f, v), p in pri.items():
        if signal and sig != signal:
            continue
        rows.append({"segnale": sig, "caratteristica": PREFIX + f, "valore": v, "media": round(p["mean"], 3),
                     "prior": round(p["prior_mean"], 3), "intervallo80": [round(p["lo80"], 3), round(p["hi80"], 3)],
                     "n": p["n_jobs"], "decisivi": p["n_decisive"], "confidenza": p["confidence"], "elo": p.get("elo")})
    rows.sort(key=lambda r: (r["segnale"], -r["n"], -abs(r["media"] - r["prior"])))
    counts = {
        "record": conn.execute("SELECT COUNT(*) FROM thumb_records WHERE channel=?", (channel,)).fetchone()[0],
        "scelte_g2": conn.execute("SELECT COUNT(*) FROM thumb_prefs WHERE channel=? AND source='g2'", (channel,)).fetchone()[0],
        "lavori_g2": conn.execute("SELECT COUNT(DISTINCT workdir) FROM thumb_prefs WHERE channel=? AND source='g2'", (channel,)).fetchone()[0],
        "delegate": conn.execute("SELECT COUNT(*) FROM thumb_prefs WHERE channel=? AND source='delegated'", (channel,)).fetchone()[0],
        "test_decisivi": conn.execute("SELECT COUNT(DISTINCT ref) FROM thumb_prefs WHERE channel=? AND source IN ('ab','pretest')",
                                      (channel,)).fetchone()[0],
        "esiti": conn.execute("SELECT COUNT(*) FROM thumb_outcomes WHERE channel=? AND weight>0", (channel,)).fetchone()[0],
        "pubblicate": conn.execute("SELECT COUNT(DISTINCT video_id) FROM thumb_records WHERE channel=? AND published=1",
                                   (channel,)).fetchone()[0],
    }
    return {"channel": channel, "counts": counts, "priors": rows[:top] if top else rows}


def explore_suggestions(conn, channel: str, n: int = 3) -> list[dict]:
    """Valori ammessi meno provati (scelte): candidati per il braccio esplorativo del prossimo video."""
    pri = compute_priors(conn, channel)
    rows = [{"caratteristica": PREFIX + f, "valore": v, "n": p["n_jobs"], "media": round(p["mean"], 3),
             "default": p["prior_mean"] > 0.5}
            for (sig, f, v), p in pri.items() if sig == "scelte" and f in CONCEPT_FEATURES
            and f not in ("guest_style", "grade", "face_source")]     # volti, grade e girato: mai esplorazione (13 §3.4)
    rows.sort(key=lambda r: (r["n"], r["default"], -r["media"]))     # i meno provati; a parità, non i default (già sfruttati)
    return rows[:n]


def playbook_section(conn, channel: str) -> str:
    """Sezione «Thumbnail» del playbook del canale (italiano; yt-learn playbook la include)."""
    rep = priors_report(conn, channel, top=0)
    c = rep["counts"]
    lines = [f"### Thumbnail (apprendimento locale, {_dt.date.today().isoformat()})", "",
             f"- Evidenza: {c['scelte_g2']} preferenze G2 in {c['lavori_g2']} lavori · {c['delegate']} delegate (peso 0) · "
             f"{c['test_decisivi']} test decisivi (A/B, pre-test) · {c['esiti']} esiti D+7/D+28 · {c['pubblicate']} video pubblicati."]
    for sig in SIGNALS:
        rows = [r for r in rep["priors"] if r["segnale"] == sig and r["n"] > 0]
        rows.sort(key=lambda r: (-(r["media"] - r["prior"]) * min(r["n"], 15)))
        if not rows:
            lines.append(f"- {sig.capitalize()}: nessuna evidenza ancora: valgono i default del knowledge (07 §5.2, profilo).")
            continue
        top = [f"{r['caratteristica'][len(PREFIX):]} = {r['valore']} {r['media']:.2f} (n={r['n']}, conf. {r['confidenza']})"
               for r in rows[:4]]
        low = [f"{r['caratteristica'][len(PREFIX):]} = {r['valore']} {r['media']:.2f} (n={r['n']})"
               for r in sorted(rows, key=lambda r: r["media"] - r["prior"])[:2] if r["media"] < r["prior"]]
        lines.append(f"- {sig.capitalize()}, più forti: " + "; ".join(top) + f" [appreso: {sig}]")
        if low:
            lines.append(f"- {sig.capitalize()}, più deboli: " + "; ".join(low))
    ex = explore_suggestions(conn, channel)
    if ex:
        lines.append("- Da esplorare (braccio esplorativo): " + "; ".join(f"{e['caratteristica'][len(PREFIX):]} = {e['valore']} (n={e['n']})"
                                                                         for e in ex))
    lines.append("- Fisso, mai appreso: volti solo pixel veri entro la scala 07 §11.2, guest_style graphic mai di default, "
                 "bordi dritti a filo, soglie QA solo più severe, nessuna chiamata a pagamento, mai pubblicare.")
    return "\n".join(lines) + "\n"


def due(conn, channel: str | None = None) -> list[dict]:
    q = "SELECT * FROM thumb_learn_due"
    rows = ytdb.rows(conn, q + (" WHERE channel=?" if channel else ""), (channel,) if channel else ())
    return rows


def postmortem(conn, video_id: str, checkpoint: str | None = None, out: Path | None = None, mark: bool = True) -> dict:
    """Post-mortem della thumbnail a D+7 / D+28 per /youtube:review: versioni pubblicate con le caratteristiche e le metriche
    QA, scelta al G2, esiti con forza e n, A/B, prior mossi da questo video (prima/dopo), cosa esplorare dopo."""
    recs = ytdb.rows(conn, "SELECT * FROM thumb_records WHERE video_id=? AND published=1 ORDER BY ab_arm, id", (video_id,))
    if not recs:
        raise ValueError(f"nessuna thumbnail pubblicata registrata per {video_id} (yt-thumb-learn publish)")
    ch = recs[0]["channel"]
    outs = ytdb.rows(conn, "SELECT * FROM thumb_outcomes WHERE video_id=? ORDER BY checkpoint, metric", (video_id,))
    if checkpoint is None:
        done = [o["checkpoint"] for o in outs if o["checkpoint"] in ("d7", "d28")]
        checkpoint = "d28" if "d28" in done else ("d7" if "d7" in done else None)
    before = compute_priors(conn, ch, exclude_video=video_id)
    after = compute_priors(conn, ch)
    moved = []
    for k, a in after.items():
        b = before.get(k)
        if b and abs(a["mean"] - b["mean"]) > 0.005 and k[0] == "esiti":
            moved.append({"caratteristica": PREFIX + k[1], "valore": k[2], "prima": round(b["mean"], 3), "dopo": round(a["mean"], 3),
                          "n": a["n_jobs"], "confidenza": a["confidence"]})
    moved.sort(key=lambda m: -abs(m["dopo"] - m["prima"]))
    wd = recs[0].get("workdir") or ""
    others = ytdb.rows(conn, "SELECT version, chosen, choice_reason, choice_source FROM thumb_records WHERE channel=? AND workdir=? "
                             "AND stage IN ('render','final') AND (published=0 OR published IS NULL)", (ch, wd)) if wd else []
    tests = ytdb.rows(conn, "SELECT id, kind, winner, started_at, ended_at, result_json FROM ab_tests WHERE video_id=?", (video_id,))
    L = [f"## Post-mortem thumbnail — {video_id} ({checkpoint or 'nessun checkpoint letto'})", ""]
    L.append("| braccio | versione | template | leva | grade | accento | classe | gancio (forma, parole) | volto % | righe % | "
             "lettura a freddo | render / QA |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in recs:
        f = json.loads(r["features_json"] or "{}")
        L.append(f"| {r.get('ab_arm') or '—'} | {r['version']} | {f.get('template') or '—'} | {f.get('lever') or '—'} | "
                 f"{f.get('grade') or '—'} | {f.get('accent') or '—'} | {f.get('expression') or '—'} | "
                 f"{f.get('hook_family') or '—'}, {r.get('hook_words') or '—'} | {r.get('face_pct') or '—'} | "
                 f"{r.get('rows_pct_min') or '—'} | {r.get('cold_score') if r.get('cold_score') is not None else '—'} | "
                 f"{'ok' if r.get('render_pass') else ('errori' if r.get('render_pass') is not None else '—')} / "
                 f"{'ok' if r.get('qa_pass') else ('errori' if r.get('qa_pass') is not None else '—')} |")
    L.append("")
    reason = next((r.get("choice_reason") for r in recs if r.get("choice_reason")), None)
    src = next((r.get("choice_source") for r in recs if r.get("choice_source")), None)
    if others or reason:
        L.append(f"Scelta al G2 ({'delegata' if src == 'delegated' else 'operatore'}): pubblicata contro "
                 f"{', '.join(o['version'] for o in others) or '—'}; motivo: «{reason or 'nessuno dato'}».")
        L.append("")
    if outs:
        L.append("| checkpoint | metrica | valore | base del canale | rapporto | n confronti | impressioni | forza | esito | peso |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for o in outs:
            val = (f"{o['value'] * 100:.2f} %" if o["metric"] == "ctr" and o.get("value") is not None else o.get("value"))
            base = (f"{o['baseline'] * 100:.2f} %" if o["metric"] == "ctr" and o.get("baseline") is not None else o.get("baseline"))
            det = json.loads(o.get("details_json") or "{}")
            lab = o["label"] + (f" ({det.get('reason')})" if o["label"] == "non_leggibile" and det.get("reason") else "")
            L.append(f"| {o['checkpoint']} | {o['metric']} | {val if val is not None else '—'} | {base if base is not None else '—'} | "
                     f"{o.get('ratio') or '—'} | {o.get('n') if o.get('n') is not None else '—'} | {o.get('impressions') or '—'} | "
                     f"{'debole (Tier 0)' if o.get('strength') == 'debole' else o.get('strength')} | {lab} | {o['weight']} |")
        L.append("")
        L.append("Rapporti e confronti: calcolati da noi, non sono dati YouTube. CTR per video, non per braccio (07 §15.3); "
                 "con più bracci pubblicati l'esito pesa solo sulle caratteristiche comuni.")
    else:
        L.append("Esiti: nessuno letto (yt-thumb-learn outcomes, dopo yt-collect).")
    L.append("")
    for t in tests:
        L.append(f"Test {t['kind']} #{t['id']}: esito «{t.get('winner') or 'in corso / non registrato'}» "
                 f"({t.get('started_at') or '?'} → {t.get('ended_at') or '?'}).")
    if moved:
        L.append("")
        L.append("Prior mossi da questo video (esiti): " + "; ".join(
            f"{m['caratteristica'][len(PREFIX):]} = {m['valore']} {m['prima']:.2f} → {m['dopo']:.2f} (n={m['n']}, conf. {m['confidenza']})"
            for m in moved[:6]))
    ex = explore_suggestions(conn, ch)
    if ex:
        L.append("")
        L.append("Prossimo braccio esplorativo suggerito: " + "; ".join(f"{e['caratteristica'][len(PREFIX):]} = {e['valore']} (n={e['n']})"
                                                                     for e in ex))
    md = "\n".join(L) + "\n"
    path = None
    if out:
        path = Path(out)
    elif wd and Path(wd).is_dir():
        path = Path(wd) / "logs" / f"thumb-postmortem-{checkpoint or 'nd'}-{video_id}.md"
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md)
    if mark and checkpoint:
        with conn:
            conn.execute("UPDATE thumb_checkpoints SET postmortem_at=? WHERE video_id=? AND checkpoint=?", (now_iso(), video_id, checkpoint))
    return {"channel": ch, "video_id": video_id, "checkpoint": checkpoint, "markdown": md, "path": str(path) if path else None,
            "priors_moved": moved, "outcomes": len(outs)}


# Destinazioni delle proposte Tier B (percorsi relativi alla radice della repo). I default del profilo (template, grade,
# leva) non sono una destinazione: il profilo vive nei channels_dirs dell'operatore, mai nella repo, e una lezione su quei
# default diventa un suggerimento locale (profile_changes) che l'operatore applica a mano.
PROFILE_KEYS = {"template": "thumbnails.default_template", "grade": "thumbnails.grade_default", "lever": "thumbnails.default_lever"}
REPO_PLUGIN_SUBDIR = "plugins/youtube"                 # come learn.REPO_PLUGIN_SUBDIR
KNOWLEDGE_07 = f"{REPO_PLUGIN_SUBDIR}/docs/yt/knowledge/07-thumbnails.md"
ANCHOR_07 = "16.1 Learned thumbnail lessons"           # sezione di 07 con la tabella delle lezioni apprese
# Intestazione esatta della tabella di 07 §16.1: la proposta la sostituisce con intestazione + riga nuova (yt-learn propose
# --replace/--with), così la riga entra nella tabella (un'aggiunta in fondo alla sezione lascerebbe una riga vuota).
TABLE_HEAD_07 = ("| Date | Channel | Signal | Feature = value | Jobs | Decisive | Mean (prior) |\n"
                 "|---|---|---|---|---|---|---|")
THRESHOLDS = {   # caratteristica, valore che perde → soglia da stringere (solo più severa, H8)
    ("face_pct", "35-40"): {"files": [f"{REPO_PLUGIN_SUBDIR}/scripts/yt/lib/thumb_render.py",
                                      f"{REPO_PLUGIN_SUBDIR}/scripts/yt/lib/thumb_qa.py"],
                            "constants": ["FACE_V2_ERR", "FACE_CLAIM_ERR"], "from": 0.35, "to": 0.40, "l1_name": "face_size"},
}


def channel_shareable(channel: str, cfg: dict | None = None) -> bool:
    """Le lezioni del canale possono diventare una PR (13 §1.2, §9.2): il canale è in learning_pr_channels (default:
    nessuno) E il suo profilo dice `kind: own` e `share_lessons: true` (ytcore.shareable_channels, ricontrollato qui sul
    profilo: fallisce chiuso). Clienti, canali personali e canali propri non condivisi restano locali."""
    cfg = cfg or settings()
    configured = cfg.get("pr_channels") or []
    if isinstance(configured, str):
        configured = [x.strip() for x in configured.split(",") if x.strip()]
    if channel not in configured:
        return False
    try:
        listed = channel in (yc.shareable_channels(configured) if hasattr(yc, "shareable_channels") else [])
    except Exception:  # noqa: BLE001
        listed = False
    prof = load_profile(channel)
    return bool(listed) and prof.get("kind") == "own" and prof.get("share_lessons") is True


def _l1_evidence(conn, channel: str, evidence: Iterable[str]) -> list[str]:
    """Id degli eventi di yt-learn (e<n>) che corrispondono alle evidenze (record di render → item, video → esito e
    pubblicazione): così `yt-learn lesson add --evidence` punta agli stessi fatti."""
    if not _has_table(conn, "learn_events"):
        return []
    refs: list[str] = []
    for e in evidence:
        if str(e).isdigit():
            r = conn.execute("SELECT workdir, version FROM thumb_records WHERE id=? AND channel=?", (int(e), channel)).fetchone()
            if r and r["workdir"]:
                refs.append(f"thumbnail:render:{Path(r['workdir']).name}:{r['version']}")
        else:
            refs += [f"publication:{e}", f"outcome:{e}:d7", f"outcome:{e}:d28"]
    out = []
    for ref in refs:
        for r in conn.execute("SELECT id FROM learn_events WHERE channel=? AND ref=? AND retracted_at IS NULL AND superseded_by IS NULL",
                              (channel, ref)).fetchall():
            out.append(f"e{r[0]}")
    return list(dict.fromkeys(out))[:30]


def _profile_change(channel: str, key: str, cur: Any, new: str) -> dict | None:
    """Sostituzione esatta nel profilo del canale (una riga, nel file dei channels_dirs dell'operatore):
    {"replace": vecchio testo, "with": nuovo testo}."""
    try:
        path = yc.channel_file(channel, ".md")
        text = path.read_text()
    except Exception:  # noqa: BLE001
        return None
    leaf = key.split(".")[1] if key.count(".") >= 1 else key
    if key.startswith("thumbnails.grade_default.") and isinstance(cur, str):
        tpl = key.split(".")[2]
        m = re.search(rf"^\s*grade_default:\s*\{{[^}}\n]*\b{re.escape(tpl)}:\s*{re.escape(cur)}\b", text, re.M)
        if m:
            old = m.group(0).strip()
            return {"replace": old, "with": re.sub(rf"\b{re.escape(tpl)}:\s*{re.escape(cur)}\b", f"{tpl}: {new}", old)}
        return None
    m = re.search(rf"^\s*{re.escape(leaf)}:\s*([^\s#]+)", text, re.M)
    if m and m.group(1) == str(cur):
        old = m.group(0).strip()
        return {"replace": old, "with": old[: old.rfind(m.group(1))] + new}
    return None


def proposal_candidates(conn, channel: str, profile: dict | None = None) -> dict:
    """Lezioni thumbnail con abbastanza evidenza (13 §1.2): ≥ min_evidence lavori concordi, oppure un esito decisivo
    (A/B o pre-test) senza esiti contrari.
    - `proposals` (Tier B, PR): solo per i canali condivisibili (channel_shareable); righe della tabella di 07 §16.1 e
      soglie più severe. Portano regola e conteggi: niente immagini, ganci, nomi, motivi dell'operatore o percorsi.
    - `profile_changes` (locale, ogni canale): i default del profilo (template, grade, leva) che l'evidenza sposta, con
      la sostituzione esatta da fare a mano nel profilo dell'operatore. Mai una PR: il profilo non è nella repo."""
    cfg = settings()
    profile = load_profile(channel) if profile is None else profile
    eligible = channel_shareable(channel, cfg)
    res = {"channel": channel, "proposals": [], "refused": [], "profile_changes": [], "eligible": eligible}
    if not eligible:
        res["note"] = (f"canale {channel} non condivisibile (servono learning_pr_channels e, nel profilo, kind: own e "
                       "share_lessons: true): le lezioni restano locali (Tier A), nessuna PR (13 §9.2)")
    th = (profile or {}).get("thumbnails") or {}
    pri = compute_priors(conn, channel, profile)
    native_tests = conn.execute("SELECT COUNT(*) FROM ab_tests WHERE channel=? AND kind IN ('thumbnail','both') AND winner IS NOT NULL",
                                (channel,)).fetchone()[0]
    for (sig, f, v), p in pri.items():
        lead = p["mean"] - p["prior_mean"]
        # solo confronti «puliti» (stesso template): un valore che vince perché vince il suo template non è una lezione
        nc, cw, cl = p.get("n_clean", 0), p.get("clean_wins", 0.0), p.get("clean_losses", 0.0)
        consistent = nc >= int(cfg["min_evidence"]) and cl <= 0.25 * max(cw, 1e-9) and cw > 0
        decisive = (sig == "esiti" and p["n_decisive"] >= 1 and p["losses"] == 0 and p["wins"] > 0
                    and (f in ("template", "lever") or nc >= 1))
        losing = nc >= int(cfg["min_evidence"]) and cw <= 0.25 * max(cl, 1e-9) and cl > 0
        if not ((consistent or decisive) and lead >= 0.1) and not (losing and (f, v) in THRESHOLDS):
            continue
        ev = {"segnale": sig, "n": p["n_jobs"], "n_puliti": nc, "decisivi": p["n_decisive"], "media": round(p["mean"], 3),
              "prior": round(p["prior_mean"], 3), "id": p["evidence"][:20]}
        pid = f"thumb-{channel}-{sig}-{f}-{yc.slugify(v)}"
        base = {"id": pid, "slug": f"thumb-{f}-{yc.slugify(v)}", "channel": channel, "scope": "channel", "signal": sig,
                "evidence": ev, "source": "thumb_learn", "privacy": "ok: solo regola e conteggi"}
        if f in PROFILE_KEYS:            # default del profilo: suggerimento locale, su ogni canale (mai una PR)
            if not profile:              # canale senza profilo: niente da suggerire
                continue
            key = PROFILE_KEYS[f]
            cur = th.get(key.split(".", 1)[1])
            if f == "grade" and isinstance(cur, dict):
                tpl = th.get("default_template")
                key, cur = f"{key}.{tpl}", cur.get(tpl)
            if f == "lever" and native_tests < cfg["native_tests_for_lever"]:
                res["refused"].append({**base, "kind": "profile", "reason": f"07 §16: il default della leva cambia solo dopo ≥ "
                                       f"{cfg['native_tests_for_lever']} test nativi (ora {native_tests}): va nello scoreboard"})
            elif str(cur) != v:
                reason = (f"{FEATURE_IT[f]} {v} preferito in {max(nc, p['n_decisive'])} lavori (media {p['mean']:.2f} contro il "
                          f"prior {p['prior_mean']:.2f}) [appreso: {sig}, n={p['n_jobs']}]")
                exact = _profile_change(channel, key, cur, v)
                res["profile_changes"].append({**base, "kind": "profile", "local": True, "target": f"{channel}.md",
                                               "where": "channels_dirs dell'operatore (yt-config): mai nella repo",
                                               "change": {"yaml_key": key, "from": cur, "to": v, **(exact or {})},
                                               "hard_rules": "nessuna", "reason": reason,
                                               "how": "l'operatore lo applica a mano nel suo profilo, se è d'accordo",
                                               "yt_learn": _yt_learn_block(conn, channel, sig, p, f, v, reason, None)})
            continue
        if not eligible:
            continue
        if losing and (f, v) in THRESHOLDS:
            t = THRESHOLDS[(f, v)]
            reason = f"{FEATURE_IT[f]} {v}: perde in {nc} lavori a parità di template [appreso: {sig}, n={nc}]"
            res["proposals"].append({**base, "kind": "threshold", "target": t["files"],
                                     "change": {"constants": t["constants"], "from": t["from"], "to": t["to"]},
                                     "hard_rules": "stringe H8 (soglia più severa)", "reason": reason,
                                     "yt_learn": _yt_learn_block(conn, channel, sig, p, f, v, reason, {"target": t["files"][0]},
                                                                 threshold={"name": t["l1_name"], "min": t["to"]})})
            continue
        if f == "guest_style":
            res["refused"].append({**base, "reason": "H1: guest_style graphic mai di default; resta una variabile da pre-test"})
            continue
        row = (f"| {date_str()} | {channel} | {sig} | `{f}` = `{v}` | {nc} | {p['n_decisive']} | "
               f"{p['mean']:.2f} (prior {p['prior_mean']:.2f}) |")
        reason = (f"{FEATURE_IT.get(f, f)} {v}: evidenza concorde a parità di template (n={nc}, decisivi {p['n_decisive']}) "
                  f"[appreso: {sig}]")
        res["proposals"].append({**base, "kind": "knowledge", "target": KNOWLEDGE_07,
                                 "change": {"section": ANCHOR_07, "append_row": row, "replace": TABLE_HEAD_07,
                                            "with": TABLE_HEAD_07 + "\n" + row},
                                 "hard_rules": "nessuna", "reason": reason,
                                 "yt_learn": _yt_learn_block(conn, channel, sig, p, f, v, reason,
                                                             {"target": KNOWLEDGE_07, "replace": TABLE_HEAD_07,
                                                              "with": TABLE_HEAD_07 + "\n" + row})})
    return res


def _yt_learn_block(conn, channel: str, sig: str, p: dict, f: str, v: str, reason: str, propose: dict | None,
                    threshold: dict | None = None) -> dict:
    """Comandi pronti per registrare la lezione e la proposta con yt-learn (13 §6.1 passi 5 e 7). propose=None: solo la
    lezione (Tier A), per un suggerimento locale che non diventa mai una PR."""
    ev = _l1_evidence(conn, channel, p["evidence"])
    cmd = ["yt-learn", "lesson", "add", "--channel", channel, "--skill", "thumbnail", "--signal", sig, "--text", reason]
    if ev:
        cmd += ["--evidence", ",".join(ev)]
    if sig == "esiti" and p.get("n_decisive"):
        cmd.append("--decisive")
    out: dict[str, Any] = {"lesson_add": cmd, "evidence_events": ev}
    if propose is not None:
        out["propose"] = {"title": f"Thumbnail {channel}: {FEATURE_IT.get(f, f)} {v}", **propose}
    if threshold:          # Tier A subito, sul solo canale: soglia più severa (13 §2.2), poi la PR per tutti
        out["threshold_set"] = ["yt-learn", "threshold", "set", "--channel", channel, "--name", threshold["name"],
                                "--min", str(threshold["min"]), "--level", "error"]
    return out


def date_str() -> str:
    return _dt.date.today().isoformat()


# ── Riferimenti di nicchia (aggiornamento mensile, ≤ 30 giorni) ─────────────────────────────────────────────────
def peers_file(channel: str) -> Path:
    return yc.DATA / f"peers-{channel}.txt"


def read_peers(path: Path) -> list[str]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.split()[0])
    return out


def _peer_channel_ids(conn, refs: list[str]) -> list[str]:
    ids = []
    for ref in refs:
        handle = ref if ref.startswith("@") else ("@" + ref.rstrip("/").split("/@")[-1] if "/@" in ref else None)
        r = conn.execute("SELECT channel_id FROM peers WHERE channel_id=? OR input=? OR lower(handle)=lower(?) OR url=?",
                         (ref, ref, handle or "", ref)).fetchone()
        if r:
            ids.append(r[0])
    return list(dict.fromkeys(ids))


def refs_plan(conn, channel: str, max_n: int | None = None, today: str | _dt.date | None = None) -> dict:
    """Video dei peer da cui prendere le thumbnail di riferimento: i più sopra la mediana del proprio canale (formato
    long, ≥ 14 giorni, dati peer ≤ 30 giorni), al massimo 2 per canale. Il rapporto è una metrica derivata, solo per
    scegliere i riferimenti."""
    cfg = settings()
    td = _today(today)
    max_n = int(max_n or cfg["refs_max"])
    pf = peers_file(channel)
    rep = {"channel": channel, "peers_file": str(pf), "items": [], "warnings": []}
    refs = read_peers(pf)
    if not refs:
        rep["warnings"].append(f"file dei peer assente o vuoto ({pf}): conferma la lista con /youtube:research (modo outliers)")
        return rep
    ids = _peer_channel_ids(conn, refs)
    if not ids:
        rep["warnings"].append("nessun peer nel database: esegui yt-outliers --peers <file> (/youtube:research, modo outliers)")
        return rep
    cutoff = (_dt.datetime.combine(td, _dt.time()) - _dt.timedelta(days=cfg["refs_peer_max_age_days"])).isoformat()
    cands = []
    for cid in ids:
        vids = ytdb.rows(conn, "SELECT video_id, channel_id, title, published_at, views, format FROM peer_videos WHERE channel_id=? "
                               "AND fetched_at>=? AND views IS NOT NULL", (cid, cutoff))
        longs = [v for v in vids if (v.get("format") or "long") == "long"]
        if len(longs) < 3:
            continue
        med = statistics.median(v["views"] for v in longs) or 1
        for v in longs:
            d = _date(v.get("published_at"))
            if d and (td - d).days < cfg["refs_min_age_days"]:
                continue
            cands.append({**v, "ratio": round(v["views"] / med, 2)})
    cands.sort(key=lambda v: -v["ratio"])
    per: dict[str, int] = {}
    for v in cands:
        if per.get(v["channel_id"], 0) >= cfg["refs_per_channel"]:
            continue
        per[v["channel_id"]] = per.get(v["channel_id"], 0) + 1
        rep["items"].append({"video_id": v["video_id"], "peer_channel": v["channel_id"], "title": v.get("title"),
                             "ratio": v["ratio"]})
        if len(rep["items"]) >= max_n:
            break
    if not rep["items"]:
        rep["warnings"].append("nessun video dei peer utilizzabile (dati più vecchi di 30 giorni o troppo pochi video)")
    return rep


def _default_fetch(ids: list[str], raw: Path) -> list[Path]:
    """yt-research meta --thumb (yt-dlp con i guardrail del toolkit: niente cookie, pause, ≤ 20 URL)."""
    proc = subprocess.run([sys.executable, str(LIB / "research.py"), "meta", *ids[:20], "--thumb", "--out", str(raw)],
                          capture_output=True, text=True)
    if proc.returncode not in (0, 3):
        yc.log((proc.stderr or "")[-800:])
    return sorted(raw.glob("*/*.jpg"))


def refs_dir(channel: str) -> Path:
    return REFS_DIR / channel


def refs_refresh(conn, channel: str, max_n: int | None = None, dry_run: bool = False,
                 fetch: Callable[[list[str], Path], list[Path]] | None = None, today: str | _dt.date | None = None) -> dict:
    """Aggiornamento mensile: sostituisce <studio>/data/refs/<canale>/grid/ con le thumbnail dei video del piano.
    I metadati grezzi di yt-research si cancellano subito; restano le immagini e un manifest minimo (≤ 30 giorni)."""
    plan = refs_plan(conn, channel, max_n, today)
    rep = {**plan, "dry_run": dry_run, "copied": 0}
    if dry_run or not plan["items"]:
        return rep
    base = refs_dir(channel)
    grid = base / "grid"
    raw = base / "_raw"
    shutil.rmtree(raw, ignore_errors=True)
    raw.mkdir(parents=True, exist_ok=True)
    got = (fetch or _default_fetch)([i["video_id"] for i in plan["items"]], raw)
    shutil.rmtree(grid, ignore_errors=True)
    grid.mkdir(parents=True, exist_ok=True)
    have = {p.stem: p for p in got}
    items = []
    for it in plan["items"]:
        p = have.get(it["video_id"])
        if p and p.exists():
            shutil.copy2(p, grid / f"{it['video_id']}.jpg")
            items.append(it)
    shutil.rmtree(raw, ignore_errors=True)
    if items and _has_table(conn, "learn_refs"):
        try:                                            # stesso elenco in yt-learn (learn_refs: rinfresco dovuto e purge a 30 gg)
            import learn as _l1
            _l1.refs_purge(conn, channel, everything=True)
            _l1.refs_add(conn, channel, [str(grid / f"{it['video_id']}.jpg") for it in items], source="yt-thumb-learn refs refresh")
            rep["yt_learn_refs"] = len(items)
        except Exception as e:  # noqa: BLE001 — yt-learn assente o diverso: i riferimenti restano comunque qui
            rep["warnings"].append(f"riferimenti non registrati in yt-learn ({type(e).__name__}: {e})")
    ts = now_iso()
    yc.write_json(base / "refs.json", {"channel": channel, "refreshed_at": ts, "items": items,
                                       "note": "thumbnail di terzi: uso privato per la griglia QA, cancellate entro 30 giorni (11 §3)"})
    with conn:
        conn.execute("INSERT INTO thumb_refs_runs(channel, refreshed_at, n, dir) VALUES (?,?,?,?) ON CONFLICT(channel) DO UPDATE SET "
                     "refreshed_at=excluded.refreshed_at, n=excluded.n, dir=excluded.dir", (channel, ts, len(items), str(grid)))
    rep.update({"copied": len(items), "grid": str(grid)})
    if len(items) < len(plan["items"]):
        rep["warnings"].append(f"scaricate {len(items)} thumbnail su {len(plan['items'])}")
    return rep


def refs_status(channel: str) -> dict:
    base = refs_dir(channel)
    man = base / "refs.json"
    if not man.exists():
        return {"channel": channel, "exists": False}
    d = yc.read_json(man)
    ts = _dt.datetime.fromisoformat(d["refreshed_at"])
    age = (_dt.datetime.now(_dt.timezone.utc) - ts).days
    n = len(list((base / "grid").glob("*.jpg"))) if (base / "grid").is_dir() else 0
    return {"channel": channel, "exists": True, "refreshed_at": d["refreshed_at"], "age_days": age, "n": n,
            "stale": age > THUMB["refs_max_age_days"], "grid": str(base / "grid")}


def refs_grid(channel: str | None) -> tuple[Path | None, str | None]:
    """Cartella dei riferimenti per yt-thumb-qa --grid auto: (cartella, avviso). Scaduti (> 30 gg) = non usati."""
    if not channel:
        return None, "--grid auto: canale non determinabile (passa --channel)"
    st = refs_status(channel)
    if not st.get("exists") or not st.get("n"):
        return None, f"--grid auto: nessun riferimento di nicchia per {channel} (yt-thumb-learn refs refresh --channel {channel})"
    if st["stale"]:
        return None, (f"--grid auto: riferimenti di {channel} vecchi di {st['age_days']} giorni (> 30): non usati; "
                      f"rinnova con yt-thumb-learn refs refresh o cancellali con refs purge")
    return Path(st["grid"]), None


def refs_purge(days: int = 30) -> dict:
    removed = []
    if REFS_DIR.is_dir():
        for base in REFS_DIR.iterdir():
            st = refs_status(base.name) if base.is_dir() else {}
            if base.is_dir() and (not st.get("exists") or st.get("age_days", 0) > days):
                shutil.rmtree(base, ignore_errors=True)
                removed.append(base.name)
    return {"removed": removed}


# ── Passo 5 per le thumbnail ───────────────────────────────────────────────────────────────────────────────────
def learn_workdir(conn, workdir: str | Path, channel: str | None = None, job_id: str | None = None) -> dict:
    wd = Path(workdir).expanduser().resolve()
    ch = channel_of_workdir(wd, channel)
    profile = load_profile(ch)
    ing = ingest_workdir(conn, wd, ch, job_id, profile=profile)
    synced = sync_from_learn(conn, ch, wd)
    tests = sync_tests(conn, ch)
    n = rebuild_priors(conn, ch, profile)
    props = proposal_candidates(conn, ch, profile)
    return {"channel": ch, "ingest": ing, "yt_learn": synced, "tests": tests, "priors": n, "proposals": props["proposals"],
            "refused": props["refused"], "profile_changes": props["profile_changes"], "due": due(conn, ch),
            "playbook_section": playbook_section(conn, ch)}


# ── CLI ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _arms(values: list[str] | None) -> dict[str, str]:
    out = {}
    for v in values or []:
        if "=" not in v:
            raise ValueError(f"--arm «{v}»: usa BRACCIO=VERSIONE (es. A=A_duo_v2)")
        k, ver = v.split("=", 1)
        out[k.strip()] = ver.strip()
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="yt-thumb-learn", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Dettagli: knowledge 13-learning-loop §4.3, 07-thumbnails §16; skill /youtube:thumbnail, "
                                        "sezione «Apprendimento thumbnail».")
    ap.add_argument("--db", help=f"database (default {yc.DB_PATH})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest", help="registra concept, render, QA e letture a freddo del workdir")
    p.add_argument("workdir")
    p.add_argument("--channel")
    p.add_argument("--job")
    p.add_argument("--renders", action="append", help="cartella di render (ripetibile; default thumbs/renders e thumbs/sketch)")
    p = sub.add_parser("learn", help="Passo 5 per le thumbnail: ingest + test + prior + proposte + playbook")
    p.add_argument("workdir")
    p.add_argument("--channel")
    p.add_argument("--job")
    p = sub.add_parser("rank", help="ordina i concept: sfruttamento + 1 esplorazione (Thompson), con n e confidenza")
    p.add_argument("--channel", required=True)
    p.add_argument("--data", required=True, help="concepts.json (lista, oggetto o {'concepts': [...]})")
    p.add_argument("--keep", type=int)
    p.add_argument("--explore", type=int)
    p.add_argument("--seed", type=int)
    p.add_argument("--out", help="scrive il risultato anche qui (es. thumbs/learn/rank.json)")
    p = sub.add_parser("choice", help="G2: scelte > scartate (preferenze a coppie) col motivo dell'operatore")
    p.add_argument("workdir")
    p.add_argument("--chosen", required=True, help="versioni scelte (nomi dei render) o id dei concept, separati da virgola")
    p.add_argument("--rejected", help="scartate (default: tutte le altre renderizzate)")
    p.add_argument("--reason", help="motivo dell'operatore, parola per parola (mai dedotto)")
    p.add_argument("--delegated", action="store_true", help="G2 delegato: registrato, peso 0 nelle scelte")
    p.add_argument("--operator")
    p.add_argument("--channel")
    p = sub.add_parser("publish", help="lega la versione pubblicata (o i bracci A/B) al video e la copia nel golden set")
    p.add_argument("workdir")
    p.add_argument("--video", required=True)
    p.add_argument("--version", help="versione pubblicata (nome del render)")
    p.add_argument("--arm", action="append", help="BRACCIO=VERSIONE per un A/B (ripetibile)")
    p.add_argument("--published-at")
    p.add_argument("--ab-test", type=int)
    p.add_argument("--no-golden", action="store_true")
    p.add_argument("--channel")
    p = sub.add_parser("outcomes", help="esiti ai checkpoint scaduti (t48 igiene, d7, d28) e ricalcolo dei prior")
    p.add_argument("--channel")
    p.add_argument("--video")
    p.add_argument("--due", action="store_true", help="solo i checkpoint in scadenza (default)")
    p.add_argument("--all", action="store_true", help="rilegge anche i checkpoint già fatti")
    p.add_argument("--today")
    p = sub.add_parser("update", help="sincronizza A/B e pre-test (ab_tests) e ricalcola i prior")
    p.add_argument("--channel", required=True)
    p = sub.add_parser("priors", help="prior per caratteristica (media, intervallo 80 %%, n, confidenza)")
    p.add_argument("--channel", required=True)
    p.add_argument("--signal", choices=SIGNALS)
    p.add_argument("--top", type=int, default=60)
    p = sub.add_parser("postmortem", help="post-mortem D+7/D+28 della thumbnail (per /youtube:review)")
    p.add_argument("--video", required=True)
    p.add_argument("--checkpoint", choices=["d7", "d28"])
    p.add_argument("--out")
    p.add_argument("--no-mark", action="store_true")
    p = sub.add_parser("golden", help="golden set: list | check (regressione visiva, solo avvisi)")
    p.add_argument("action", choices=["list", "check"])
    p.add_argument("--channel")
    p.add_argument("--video")
    p.add_argument("--out")
    p = sub.add_parser("refs", help="riferimenti di nicchia: plan | refresh | status | purge")
    p.add_argument("action", choices=["plan", "refresh", "status", "purge"])
    p.add_argument("--channel")
    p.add_argument("--max", type=int)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("due", help="compiti in scadenza (esiti, post-mortem, riferimenti)")
    p.add_argument("--channel")
    p = sub.add_parser("playbook", help="sezione «Thumbnail» del playbook del canale")
    p.add_argument("--channel", required=True)
    p = sub.add_parser("proposals", help="proposte Tier B dalle lezioni thumbnail e suggerimenti locali per il profilo "
                                         "(non scrive nulla: le proposte le registra yt-learn propose)")
    p.add_argument("--channel", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "golden" and args.action == "list":
        es = golden_entries(args.channel, args.video)
        yc.emit(True, entries=es, count=len(es), dir=str(GOLDEN_DIR))
        return
    if args.cmd == "golden":
        rep = golden_check(args.channel, args.video, Path(args.out).expanduser() if args.out else None)
        yc.emit(True, **rep)
        return
    if args.cmd == "refs" and args.action == "status":
        if not args.channel:
            yc.fail("refs status: serve --channel")
        yc.emit(True, **refs_status(args.channel))
        return
    if args.cmd == "refs" and args.action == "purge":
        yc.emit(True, **refs_purge(THUMB["refs_max_age_days"]))
        return
    conn = connect(args.db)
    try:
        if args.cmd == "ingest":
            ch = channel_of_workdir(Path(args.workdir).expanduser().resolve(), args.channel)
            rep = ingest_workdir(conn, args.workdir, ch, args.job, args.renders)
            rep["yt_learn"] = sync_from_learn(conn, ch, args.workdir)
            rebuild_priors(conn, ch)
            yc.emit(True, **rep)
        elif args.cmd == "learn":
            yc.emit(True, **learn_workdir(conn, args.workdir, args.channel, args.job))
        elif args.cmd == "rank":
            src = Path(args.data).expanduser().resolve()
            res = rank_concepts(conn, args.channel, load_concepts_file(src), seed=args.seed, keep=args.keep,
                                explore=args.explore, base=src.parent)
            if args.out:
                yc.write_json(Path(args.out).expanduser(), res)
            yc.emit(True, **res)
        elif args.cmd == "choice":
            yc.emit(True, **record_choice(conn, args.workdir, _split(args.chosen), _split(args.rejected) or None, args.reason,
                                          args.delegated, args.operator, args.channel))
        elif args.cmd == "publish":
            arms: Any = _arms(args.arm) if args.arm else args.version
            if not arms:
                yc.fail("publish: serve --version oppure --arm A=… --arm B=…")
            if _has_table(conn, "learn_publications"):
                # un solo punto di registrazione: yt-learn publish (pubblicazione + esiti dovuti + questo motore + golden)
                import learn as _l1
                wd = Path(args.workdir).expanduser().resolve()
                try:
                    rep = _l1.publish(conn, channel=channel_of_workdir(wd, args.channel), video_id=args.video, workdir=wd,
                                      arms=arms if isinstance(arms, dict) else {"A": arms}, published_at=args.published_at,
                                      ab_test=args.ab_test, golden=not args.no_golden)
                except _l1.LearnError as e:
                    yc.fail(str(e))
                yc.emit(True, **rep, via="yt-learn publish")
            else:
                yc.emit(True, **record_publish(conn, args.workdir, args.video, arms, args.published_at, args.ab_test,
                                               args.channel, golden=not args.no_golden))
        elif args.cmd == "outcomes":
            yc.emit(True, **pull_outcomes(conn, args.channel, args.video, args.today, due_only=not args.all))
        elif args.cmd == "update":
            t = sync_tests(conn, args.channel)
            yc.emit(True, channel=args.channel, tests=t, priors=rebuild_priors(conn, args.channel))
        elif args.cmd == "priors":
            yc.emit(True, **priors_report(conn, args.channel, args.signal, args.top))
        elif args.cmd == "postmortem":
            yc.emit(True, **postmortem(conn, args.video, args.checkpoint, Path(args.out).expanduser() if args.out else None,
                                       mark=not args.no_mark))
        elif args.cmd == "refs":
            if not args.channel:
                yc.fail(f"refs {args.action}: serve --channel")
            if args.action == "plan":
                yc.emit(True, **refs_plan(conn, args.channel, args.max))
            else:
                yc.emit(True, **refs_refresh(conn, args.channel, args.max, args.dry_run))
        elif args.cmd == "due":
            rows = due(conn, args.channel)
            yc.emit(True, due=rows, count=len(rows), sql=DUE_SQL)
        elif args.cmd == "playbook":
            yc.emit(True, channel=args.channel, markdown=playbook_section(conn, args.channel))
        elif args.cmd == "proposals":
            yc.emit(True, **proposal_candidates(conn, args.channel))
    except (ValueError, FileNotFoundError, sqlite3.Error) as exc:
        yc.fail(str(exc))
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — errori inattesi → JSON leggibile
        import traceback
        traceback.print_exc(file=sys.stderr)
        yc.fail(f"{type(exc).__name__}: {exc}")
