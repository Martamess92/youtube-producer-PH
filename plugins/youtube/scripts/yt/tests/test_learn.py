"""Test di yt-learn (lib/learn.py): migrazione, priori, Thompson, lezioni, correzioni → glossario, esiti e scadenze,
proposte (diff validi, regole dure, privacy), propose-pr --dry-run su una repo git temporanea, SessionStart.
Niente pytest: assert semplici, tutto in cartelle temporanee (studio, config, canali, repo).

Canali sintetici nei channels_dirs temporanei: «demo» (proprio, condivisibile: in learning_pr_channels con
share_lessons: true), «esempio» (proprio ma non condiviso), «acme» (cliente), «pers» (personale). Persone di fantasia:
host «Giulia Conti», ospite «Paolo Ferri».

Uso (venv del toolkit; YT_DATA = data dir del plugin o una data dir temporanea di install.sh --data):
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_learn.py            # tutti
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_learn.py thompson   # solo i test col nome che contiene «thompson»
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"
PLUGIN = HERE.parent.parent.parent            # …/plugins/youtube
REPO_SUB = "plugins/youtube"                  # cartella del plugin nella repo (learn.REPO_PLUGIN_SUBDIR)
TMP = Path(tempfile.mkdtemp(prefix="yt-learn-test-"))
STUDIO = TMP / "studio"
CHANNELS = TMP / "channels"
for d in (STUDIO / "data", STUDIO / "work", CHANNELS):
    d.mkdir(parents=True, exist_ok=True)
# isolamento: niente config.yaml dell'operatore, solo canali sintetici, studio temporaneo
os.environ.update({"YT_STUDIO": str(STUDIO), "YT_CONFIG": str(TMP / "config.yaml"),
                   "YT_CHANNELS_DIRS": str(CHANNELS), "YT_VAULT": "", "YT_REPO_PATH": str(TMP / "repo")})
# opt-in del Tier B: solo «demo» è elencato (e il suo profilo dice kind: own e share_lessons: true)
(TMP / "config.yaml").write_text("learning_pr_channels: [demo]\n")
(CHANNELS / "demo.md").write_text("""---
slug: demo
kind: own
share_lessons: true
name: "Il Caffè dei Maker"
channel:
  handle: "@caffedeimaker"
voice:
  public_names:
    hosts: ["Giulia Conti"]
    never: ["Giuly"]
thumbnails:
  default_template: duo
  default_lever: claim
  grade_default: {duo: mono, others: natural}
  guest_style_default: none
consent:
  release_required: true
---
Profilo sintetico dei test.
""")
(CHANNELS / "demo.glossary.txt").write_text("# Glossario sintetico del canale demo\n# ── P1 nomi del canale\n"
                                            "Il Caffè dei Maker\nGiulia Conti\n# ── P2 strumenti\nTaskora\nNimbly\n")
(CHANNELS / "demo.confusions.json").write_text(json.dumps({"confusions": [
    {"term": "Taskora", "type": "company", "aliases": ["Tascora"], "origin": "a-priori", "evidence": "test"}]}))
(CHANNELS / "esempio.md").write_text("---\nslug: esempio\nkind: own\nname: \"Canale Esempio\"\n---\nProprio, non condiviso.\n")
(CHANNELS / "acme.md").write_text("---\nslug: acme\nkind: client\nname: \"ACME Pasticceria\"\n"
                                  "channel:\n  handle: \"@acmepasticceria\"\n---\nProfilo di prova.\n")
sys.path.insert(0, str(LIB))

import config  # noqa: E402
import glossary as gl  # noqa: E402
import learn as L  # noqa: E402
import ytcore as yc  # noqa: E402
import ytdb  # noqa: E402

TODAY = _dt.date.today()


# ── Aiuti ───────────────────────────────────────────────────────────────────
def fresh_db(name: str) -> sqlite3.Connection:
    return L.connect(TMP / f"{name}.db")


def make_wd(channel: str, name: str, **project) -> Path:
    wd = STUDIO / "work" / channel / name
    for sub in ("thumbs/renders", "thumbs/cold", "thumbs/qa", "edit", "analysis", "deliver"):
        (wd / sub).mkdir(parents=True, exist_ok=True)
    yc.write_json(wd / "project.json", {"channel": channel, "slug": name, "sources": {}, **project})
    return wd


def concept(cid: str, template: str, lever: str, expr: str, accent: str = "accent", hook: str = "IL CODICE NON BASTAVA",
            guest_style: str = "none", grade: str | None = None) -> dict:
    c = {"id": cid, "lever": lever, "template": template, "hook": hook, "keyword": hook.split()[-1], "accent": accent,
         "people": [{"cutout": "x.png", "role": "guest", "name": "Paolo Ferri"},
                    {"cutout": "y.png", "role": "host", "name": "Giulia Conti"}],
         "expression_class": expr, "plate": {"source": "scene"}, "guest_style": guest_style, "payoff_at": 12.0,
         "title_pair": "titolo", "hypothesis": "ipotesi privata"}
    if grade:
        c["grade"] = grade
    return c


def write_thumbs(wd: Path, concepts: list[dict], arms: list[str] | None = None) -> None:
    yc.write_json(wd / "thumbs" / "concepts.json", concepts)
    for c in concepts:
        name = f"{c['id']}_{c['template']}_v1"
        jpg = wd / "thumbs" / "renders" / f"{name}.jpg"
        jpg.write_bytes(b"\xff\xd8\xff fake jpeg " + name.encode())
        yc.write_json(wd / "thumbs" / "renders" / f"{name}.render.json", {
            "id": c["id"], "name": name, "template": c["template"], "ok": True, "errors": [], "warnings": ["w"],
            "jpg": str(jpg), "png": str(jpg.with_suffix(".png")), "spec_hash": "abc",
            "metrics": {"series": {"accent": "accent_2" if c["accent"] == "auto" else c["accent"]}},
            "v2": {"heroes": [{"face_frac": 0.42, "face_surround_dL": 31.0, "served_720": {"lap": 800}}],
                   "hook_rows": [{"frac": 0.21}, {"frac": 0.205}]}})
    yc.write_json(wd / "thumbs" / "cold" / "cold_reads.json", {"reads": [{"id": c["id"], "score": 2} for c in concepts]})
    if arms:
        yc.write_json(wd / "thumbs" / "ab_plan.json", {"arms": [{"arm": chr(65 + i), "render": r} for i, r in enumerate(arms)]})


def add_video(conn, vid: str, pub: _dt.date, snaps: dict[int, int], channel_id: str = "UCtest", fmt: str = "long") -> None:
    now = ytdb.now_iso()
    with conn:
        conn.execute("INSERT OR IGNORE INTO channels(id, slug, kind, updated_at) VALUES (?,?,?,?)",
                     (channel_id, "demo" if channel_id == "UCtest" else channel_id, "own", now))
        conn.execute("INSERT OR REPLACE INTO videos(id, channel_id, title, published_at, format, first_seen, updated_at) "
                     "VALUES (?,?,?,?,?,?,?)", (vid, channel_id, vid, f"{pub.isoformat()}T10:00:00+00:00", fmt, now, now))
        for age, views in snaps.items():
            conn.execute("INSERT OR REPLACE INTO video_stats_daily(video_id, date, views, source, fetched_at) "
                         "VALUES (?,?,?,?,?)", (vid, (pub + _dt.timedelta(days=age)).isoformat(), views, "ytdlp", now))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def ready_lesson(conn, channel: str = "demo", text: str = "Al G2 l'operatore preferisce il duo con l'espressione intensa",
                 skill: str = "thumbnail") -> dict:
    ev = []
    for i in range(3):
        wd = make_wd(channel, f"2026-09-0{i + 1}-lez-{abs(hash(text)) % 1000}-{i}")
        r = L.record_decision(conn, channel=channel, workdir=wd, gate="G2", skill=skill, offered=["A", "B"],
                              chosen=["A"], rejected=["B"], reason=None, text="A", operator="Giulia", delegated=False)
        ev.append(r["event"])
    lv = L.lesson_add(conn, channel=channel, text=text, skill=skill, evidence=ev[:1])
    for e in ev[1:]:
        lv = L.lesson_evidence(conn, lv["id"], [e], contra=False)
    assert lv["state"] == "pronta", lv
    return lv


# ── Test ────────────────────────────────────────────────────────────────────
def test_migration_additive():
    p = TMP / "v1.db"
    raw = sqlite3.connect(p)
    raw.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT)")
    raw.executescript(ytdb.MIGRATIONS[0][2])
    raw.execute("INSERT INTO schema_version VALUES (1, '2026-10-11', 'v1')")
    raw.execute("INSERT INTO hooks(channel, family, text, created_at) VALUES ('demo','E2','V1 x','2026-10-11')")
    raw.commit()
    raw.close()
    conn = ytdb.connect(p)
    assert ytdb.current_version(conn) == ytdb.SCHEMA_VERSION == 2
    assert conn.execute("SELECT COUNT(*) FROM hooks").fetchone()[0] == 1
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    for t in ("learn_jobs", "learn_events", "learn_priors", "learn_lessons", "learn_proposals", "learn_outcomes",
              "learn_publications", "learn_golden", "learn_refs", "learn_thresholds", "learn_due_v"):
        assert t in names, t
    assert ytdb.migrate(conn) == 2      # idempotente


def test_events_append_only():
    conn = fresh_db("events")
    a, new_a = L.add_event(conn, channel="demo", kind="item", ref="r1", data={"v": 1})
    assert new_a and L.add_event(conn, channel="demo", kind="item", ref="r1", data={"v": 1}) == (a, False)
    b, _ = L.add_event(conn, channel="demo", kind="item", ref="r1", data={"v": 2})
    assert [e["id"] for e in L.live_events(conn, "demo", "item")] == [b]
    a2, new2 = L.add_event(conn, channel="demo", kind="item", ref="r1", data={"v": 1})   # torna alla prima versione
    assert new2 and a2 not in (a, b) and [e["data"]["v"] for e in L.live_events(conn, "demo", "item")] == [1]
    L.retract(conn, a2, "prova")
    assert not L.live_events(conn, "demo", "item")
    assert conn.execute("SELECT COUNT(*) FROM learn_events").fetchone()[0] == 3, "niente si cancella"


def test_config_learning_keys():
    y = ("operator: \"Giulia\"\nstudio_dir: \"~/youtube-studio\"\nlearning:\n  min_evidence: 4\n  pr_channels: [demo, altro]\n"
         "learn.auto_pr: true\nlearning_explore_arms: 2\nlearning_above_ratio: nonnumero\n")
    data = config.parse_mini_yaml(y)
    assert data["learning"] == {"min_evidence": 4 if isinstance(data["learning"]["min_evidence"], int) else "4",
                                "pr_channels": ["demo", "altro"]}, data
    s = config.learning_settings(data)
    assert s["min_evidence"] == 4 and s["auto_pr"] is True and s["explore_arms"] == 2
    assert s["pr_channels"] == ["demo", "altro"]
    assert config.learning_settings({})["pr_channels"] == [], "Tier B opt-in: di default nessun canale"
    assert s["above_ratio"] == config.LEARNING_DEFAULTS["above_ratio"]      # valore illeggibile → default
    st = config.settings(data)
    assert st["repo_path"] == Path(os.environ["YT_REPO_PATH"]) and st["learning"]["min_evidence"] == 4
    # il parser minimo continua a rifiutare righe davvero sbagliate
    try:
        config.parse_mini_yaml("  - orfano\n")
        raise AssertionError("atteso ConfigError")
    except config.ConfigError:
        pass


def test_priors_math():
    assert abs(L.beta_quantile(1, 1, 0.1) - 0.1) < 1e-6 and abs(L.beta_quantile(1, 1, 0.9) - 0.9) < 1e-6
    assert abs(L.betainc(2, 3, 0.4) + L.betainc(3, 2, 0.6) - 1) < 1e-9
    assert abs(L.beta_quantile(2, 1, 0.5) - 2 ** -0.5) < 1e-6            # Beta(2,1): F(x) = x²
    assert L.confidence(3, 30, 3) == "bassa"                               # n < 5 → bassa sempre
    assert L.confidence(8, 8, 3) == "media" and L.confidence(20, 40, 12) == "alta"
    assert L.confidence(3, 30, 3, "esiti") == "bassa"
    pt = L.PriorTable({"thumbnail.lever": "claim"})
    dflt = pt.cell("thumbnail.lever", "claim", "scelte")
    assert abs(dflt["alpha"] - 2.4) < 1e-9 and abs(dflt["beta"] - 1.6) < 1e-9   # default: media 0,6, forza 4 (13 §3.2)
    assert pt.cell("thumbnail.lever", "proof", "scelte")["alpha"] == 2.0     # altri: media 0,5, forza 4
    assert L.prior_ab(True) == (dflt["alpha"], dflt["beta"])
    a = {"features": {"thumbnail.lever": "claim", "thumbnail.template": "duo", "thumbnail.grade": "mono"}}
    b = {"features": {"thumbnail.lever": "proof", "thumbnail.template": "duo", "thumbnail.grade": "mono"}}
    c = {"features": {"thumbnail.lever": "duo", "thumbnail.template": "duo", "thumbnail.grade": "mono"}}
    n = L._apply_choice(pt, [a], [b, c], "scelte", 1.0, "v1", 1)
    assert n == 1, "solo la leva varia: template e grade (uguali ovunque) non dicono nulla"
    assert ("thumbnail.template", "duo", "scelte") not in pt.cells
    claim = pt.cells[("thumbnail.lever", "claim", "scelte")]
    assert abs(claim["alpha"] - 3.4) < 1e-9 and abs(claim["beta"] - 1.6) < 1e-9 and len(claim["jobs"]) == 1
    assert pt.cells[("thumbnail.lever", "proof", "scelte")]["beta"] == 3.0
    # un job (peso pieno 1,0) muove la media di al più ~un decimo; con pref_weight 0,5 la metà; l'Elo di al più K
    assert abs(L.beta_mean(3.4, 1.6) - L.beta_mean(2.4, 1.6)) <= 0.1
    # le feature delegate (thumbnail.*) le calcola yt-thumb-learn: compute_priors non le tocca
    pt2 = L.PriorTable({})
    assert L._apply_choice(pt2, [a], [b], "scelte", 1.0, "v1", 1, skip_prefixes=L.DELEGATED_PREFIXES) == 0
    assert not pt2.cells
    assert claim["elo"] - L.ELO_START <= L.ELO_K_MAX + 1e-9
    assert 0 < L.ELO_START - pt.cells[("thumbnail.lever", "proof", "scelte")]["elo"] <= L.ELO_K_MAX
    # esiti: dentro il rumore conta metà, «non leggibile» niente
    assert L.outcome_score("sopra (nel rumore)") == (1.0, 0.5) and L.outcome_score("non leggibile") is None


def test_thompson_exploration_share():
    rng = random.Random(7)
    wins = sum(L.thompson_pick({"a": (2, 1), "b": (1, 1)}, rng) == "a" for _ in range(6000))
    assert abs(wins / 6000 - 2 / 3) < 0.03, wins / 6000               # P(θa > θb) = 2/3
    conn = fresh_db("thompson")
    now = ytdb.now_iso()
    # motore generico (hook, Shorts, capitoli…): le thumbnail passano da yt-thumb-learn (test più sotto)
    rows = [("hook.family", "claim", 40, 6, 20), ("hook.family", "proof", 4, 30, 18),
            ("hook.family", "duo", 1, 1, 0), ("hook.family", "name", 3, 4, 3)]
    with conn:
        for f, v, a, b, n in rows:
            conn.execute("INSERT INTO learn_priors(channel, feature, value, signal, alpha, beta, n_jobs, n_obs, "
                         "updated_at) VALUES ('demo',?,?,'scelte',?,?,?,0,?)", (f, v, a, b, n, now))
    cands = [{"key": k, "features": {"hook.family": k}} for k in ("claim", "proof", "duo", "name")]
    picks: dict[str, int] = {}
    for seed in range(400):
        out = L.suggest(conn, "demo", "hook", cands, k=2, explore=1, seed=seed)
        roles = [c["role"] for c in out["slate"]]
        assert roles == ["sfruttamento", "esplorazione"], roles
        assert out["slate"][0]["key"] == "claim"         # confidenza alta: sfrutta claim
        ex = out["slate"][1]["key"]
        picks[ex] = picks.get(ex, 0) + 1
    assert set(picks) <= {"proof", "duo", "name"} and {"duo", "name"} <= set(picks), picks
    assert picks.get("duo", 0) > 5 * picks.get("proof", 0), picks    # il poco provato batte il perdente certo
    share = sum(1 for seed in range(200) for c in L.suggest(conn, "demo", "hook", cands, k=3, seed=seed)["slate"]
                if c["role"] == "esplorazione") / 200
    assert share == 1.0, share                           # ≥ 1 opzione di esplorazione in ogni proposta (default 1)
    # mai esplorazione su guest_style (pixel dell'ospite): il candidato «graphic» non entra come esplorazione
    gcands = [{"key": "A", "features": {"thumbnail.lever": "claim", "thumbnail.guest_style": "none"}},
              {"key": "G", "features": {"thumbnail.lever": "duo", "thumbnail.guest_style": "graphic"}},
              {"key": "P", "features": {"thumbnail.lever": "proof", "thumbnail.guest_style": "none"}}]
    for seed in range(50):
        out = L.suggest(conn, "demo", "thumbnail", gcands, k=2, explore=1, seed=seed)
        assert all(c["key"] != "G" for c in out["slate"] if c["role"] == "esplorazione"), out["slate"]
    feat = L.suggest(conn, "demo", "hook", seed=1)["features"]
    assert feat["hook.family"]["exploit"] == "claim" and feat["hook.family"]["explore"] != "claim"
    assert "n=20" in feat["hook.family"]["evidence"]
    assert L.suggest(conn, "demo", "thumbnail", seed=1)["features"]["thumbnail.guest_style"]["explore"] is None
    assert not [r for r in L.prior_rows(conn, "demo", "thumbnail") if r["feature"] == "hook.family"]


def test_thumbnail_ingest_decision_publish_golden():
    conn = fresh_db("thumb")
    wd = make_wd("demo", "2026-10-01-paolo")
    cs = [concept("A", "duo", "claim", "intenso"), concept("B", "prova", "proof", "sorriso", accent="accent_3"),
          concept("C", "ritratto", "claim", "sorpresa", accent="auto")]
    write_thumbs(wd, cs)
    r1 = L.ingest(conn, wd, ["thumbnail"])
    assert r1["skills"]["thumbnail"]["concepts"] == 3 and r1["skills"]["thumbnail"]["renders"] == 3
    r2 = L.ingest(conn, wd, ["thumbnail"])
    assert r2["skills"]["thumbnail"]["new"] == 0, "ingest idempotente"
    items = L.items_for(conn, "demo", str(wd), "thumbnail")
    f = items["A_duo_v1"]["data"]["features"]
    assert f["thumbnail.template"] == "duo" and f["thumbnail.grade"] == "mono"      # grade dal profilo demo (duo: mono)
    assert f["thumbnail.face_pct"] == "40-45" and f["thumbnail.rows_pct"] == "20+" and f["thumbnail.people"] == "duo"
    assert items["C_ritratto_v1"]["data"]["features"]["thumbnail.accent"] == "accent_2"   # auto risolto dal render
    assert items["A"]["data"]["metrics"]["cold_read"] == 2
    # il dispatcher registra la risposta verbatim; l'ingest la abbina all'ab_plan scritto dopo G2
    d = L.record_decision(conn, channel="demo", workdir=wd, gate="G2", skill=None, offered=[], chosen=[], rejected=[],
                          reason=None, text="Vai con A, la prova non convince", operator="Giulia", delegated=False)
    assert d["chosen"] == []
    write_thumbs(wd, cs, arms=["A_duo_v1"])
    r3 = L.ingest(conn, wd, ["thumbnail"])
    assert r3["skills"]["thumbnail"]["paired"] == 1
    dec = L.live_events(conn, "demo", "decision", None, str(wd))[-1]["data"]
    assert dec["chosen"] == ["A_duo_v1"] and set(dec["rejected"]) == {"B_prova_v1", "C_ritratto_v1"}
    assert dec["text"] == "Vai con A, la prova non convince"           # il verbatim resta
    L.update_priors(conn, "demo")
    pri = {(r["feature"], r["value"]): r for r in L.prior_rows(conn, "demo", "thumbnail") if r["signal"] == "scelte"}
    assert pri[("thumbnail.template", "duo")]["mean"] > pri[("thumbnail.template", "prova")]["mean"]
    assert pri[("thumbnail.expression", "intenso")]["n_jobs"] == 1
    # una scelta su delega non pesa nelle scelte
    wd2 = make_wd("demo", "2026-10-02-delega")
    write_thumbs(wd2, cs)
    L.ingest(conn, wd2, ["thumbnail"])
    L.record_decision(conn, channel="demo", workdir=wd2, gate="G2", skill="thumbnail", offered=["B_prova_v1", "A_duo_v1"],
                      chosen=["B_prova_v1"], rejected=[], reason=None, text="G2 delegato", operator=None, delegated=True)
    L.update_priors(conn, "demo")
    pri2 = {(r["feature"], r["value"]): r for r in L.prior_rows(conn, "demo", "thumbnail") if r["signal"] == "scelte"}
    assert pri2[("thumbnail.template", "prova")]["alpha"] == pri[("thumbnail.template", "prova")]["alpha"]
    # pubblicazione: braccia da ab_plan, golden set fuori dalla repo
    pub = L.publish(conn, channel="demo", video_id="vidTEST0001", workdir=wd, published_at="2026-10-03")
    assert pub["arms"]["A"]["item"] == "A_duo_v1" and pub["golden"], pub
    g = Path(pub["golden"][0]["path"])
    assert g.is_file() and str(g).startswith(str(STUDIO / "data" / "thumb-golden")) and PLUGIN not in g.parents
    assert (g.parent / "manifest.json").is_file() and (g.parent / "concept.json").is_file(), "golden di yt-thumb-learn"
    assert L.golden_list(conn, "demo")[0]["exists"]
    assert not list((STUDIO / "data" / "thumb-golden" / "demo" / "vidTEST0001").glob("*.png")), "un solo scrittore"
    # esito D+28 con A/B: il braccio vincente > perdenti negli esiti; T+48h non muove niente
    L.publish(conn, channel="demo", video_id="vidTEST0001", workdir=wd,
              arms={"A": "A_duo_v1", "B": "B_prova_v1"}, golden=False)
    L.outcome_manual(conn, channel="demo", video_id="vidTEST0001", checkpoint="t48", verdict="polso")
    L.update_priors(conn, "demo")
    assert not [r for r in L.prior_rows(conn, "demo") if r["signal"] == "esiti" and r["n_jobs"]]
    L.outcome_manual(conn, channel="demo", video_id="vidTEST0001", checkpoint="d28", verdict="non leggibile",
                     ab_winner="B", ab_result="winner")
    L.update_priors(conn, "demo")
    es = {(r["feature"], r["value"]): r for r in L.prior_rows(conn, "demo") if r["signal"] == "esiti"}
    assert es[("thumbnail.template", "prova")]["mean"] > es[("thumbnail.template", "duo")]["mean"]
    rep = L.report(conn, "demo", "thumbnail")
    assert "thumbnail.template" in rep["priors"] and Path(rep["playbook"]).is_file()
    assert rep["playbook_lines"] <= L.PLAYBOOK_MAX_LINES
    text = Path(rep["playbook"]).read_text()
    assert "[appreso: scelte" in text and "Regole dure" in text and "ipotesi privata" not in text
    assert "Proposte per la repo (Tier B): attive" in text and rep["shareable"] is True


def test_g2_decision_pairs_every_skill():
    """Una sola decisione verbatim al G2 copre thumbnail e Shorts: l'ingest ne deriva una per skill."""
    conn = fresh_db("g2")
    wd = make_wd("demo", "2026-10-06-g2")
    (wd / "shorts").mkdir(exist_ok=True)
    write_thumbs(wd, [concept("A", "duo", "claim", "intenso"), concept("B", "prova", "proof", "sorriso")])
    yc.write_json(wd / "shorts" / "scores.json", [{"id": "c01", "in": 0, "out": 40, "why": "segnale: numero · x"},
                                                  {"id": "c02", "in": 50, "out": 70, "why": "segnale: storia · y"}])
    L.ingest(conn, wd, ["thumbnail", "shorts"])
    L.record_decision(conn, channel="demo", workdir=wd, gate="G2", skill=None, offered=[], chosen=[], rejected=[],
                      reason=None, text="Thumbnail A, e solo la clip 1", operator="Giulia", delegated=False)
    write_thumbs(wd, [concept("A", "duo", "claim", "intenso"), concept("B", "prova", "proof", "sorriso")],
                 arms=["A_duo_v1"])
    yc.write_json(wd / "shorts" / "clips.json", {"clips": [{"id": "c01", "approved": True}, {"id": "c02"}]})
    r = L.ingest(conn, wd, ["thumbnail", "shorts"])
    assert r["skills"]["thumbnail"]["paired"] == 1 and r["skills"]["shorts"]["paired"] == 1, r
    assert L.ingest(conn, wd, ["thumbnail", "shorts"])["skills"]["shorts"]["new"] == 0
    st = L.update_priors(conn, "demo")
    assert st["decisions_used"] == 1 and st["decisions_thumbnail"] == 1, st   # thumbnail → yt-thumb-learn
    assert st["thumbnail"]["yt_learn"]["decisions"] >= 1, st
    sig = {(x["feature"], x["value"]): x["mean"] for x in L.prior_rows(conn, "demo") if x["n_jobs"]}
    assert sig[("shorts.signal", "numero")] > sig[("shorts.signal", "storia")]
    assert sig[("thumbnail.template", "duo")] > sig[("thumbnail.template", "prova")]
    assert L.report(conn, "demo", write=False)["counts"]["decision"] == 1, "le derivate non gonfiano il conteggio"


def test_lessons_lifecycle():
    conn = fresh_db("lessons")
    wds = [make_wd("demo", f"2026-09-1{i}-ep") for i in range(4)]
    ev = [L.record_correction(conn, channel="demo", kind="chapter", before=f"Titolo {i}", after=f"Titolo {i}?",
                              workdir=w)["event"] for i, w in enumerate(wds)]
    lv = L.lesson_add(conn, channel="demo", text="I titoli dei capitoli funzionano meglio come domanda", skill="chapters",
                      evidence=[ev[0]])
    assert lv["state"] == "candidata" and lv["n"] == 1
    lv = L.lesson_evidence(conn, lv["id"], [ev[1]], contra=False)
    assert lv["state"] == "attiva" and lv["n"] == 2
    lv = L.lesson_evidence(conn, lv["id"], [ev[1]], contra=False)
    assert lv["n"] == 2, "lo stesso video non conta due volte"
    lv = L.lesson_evidence(conn, lv["id"], [ev[2]], contra=False)
    assert lv["state"] == "pronta" and lv["stato"] == "pronta per proposta"
    # stessa chiave = stessa lezione
    again = L.lesson_add(conn, channel="demo", text="I titoli dei capitoli funzionano meglio come domanda", skill="chapters",
                         evidence=[ev[3]])
    assert again["id"] == lv["id"] and again["n"] == 4
    # contraddetta due volte di fila → ritirata
    lv2 = L.lesson_add(conn, channel="demo", text="Le pause sopra 1,5 s vanno sempre tenute", skill="edit", evidence=[ev[0]])
    L.lesson_evidence(conn, lv2["id"], [ev[1]], contra=True)
    lv2 = L.lesson_evidence(conn, lv2["id"], [ev[2]], contra=True)
    assert lv2["state"] == "ritirata" and "due volte" in lv2["retired_reason"]
    # ritiro manuale e ritrattazione delle prove
    lv3 = L.lesson_add(conn, channel="demo", text="Il cold open regge meglio sotto i 30 secondi", skill="hook",
                       evidence=[ev[0], ev[1]])
    assert lv3["state"] == "attiva"
    L.retract(conn, ev[1], "correzione ripresa dall'operatore")
    L.refresh_lessons(conn, "demo")
    assert L.lesson_view(L.lesson_get(conn, lv3["id"]))["state"] == "candidata"
    assert L.lesson_retire(conn, lv3["id"], "sbagliata")["state"] == "ritirata"
    assert all(x["id"] != lv3["id"] for x in L.report(conn, "demo")["lessons"]["active"])
    # regole dure, canali clienti, prove di altri canali
    for bad in ("Su questo canale si può saltare la liberatoria se l'ospite è amico",
                "Allenta la soglia del volto al 30% per i duo",
                "Usa un relight generativo sul volto dell'ospite quando la luce è brutta"):
        try:
            L.lesson_add(conn, channel="demo", text=bad, evidence=[ev[0]])
            raise AssertionError(f"lezione accettata: {bad}")
        except L.LearnError as exc:
            assert "regola dura" in str(exc), exc
    try:
        L.lesson_add(conn, channel="acme", text="Il logo va in alto a destra", scope="global")
        raise AssertionError("globale da un cliente")
    except L.LearnError as exc:
        assert "non è un canale proprio" in str(exc)
    try:
        L.lesson_add(conn, channel="acme", text="Il logo va in alto a destra", evidence=[ev[0]])
        raise AssertionError("prova di un altro canale")
    except L.LearnError as exc:
        assert "altro canale" in str(exc)


def test_correction_glossary_merge():
    conn = fresh_db("gloss")
    wd = make_wd("demo", "2026-09-20-glidegrid")
    assert "glidegrid" not in {t.casefold() for t in yc.glossary_terms("demo")}
    r = L.record_correction(conn, channel="demo", kind="transcript", before="Glaidgrid", after="GlideGrid", workdir=wd)
    assert r["learned"]["terms"] == 1 and r["learned"]["aliases"] == 1
    L.record_correction(conn, channel="demo", kind="transcript", before="cloud code", after="Claude Code", workdir=wd)
    gfile, cfile = yc.learned_file("demo", ".glossary.txt"), yc.learned_file("demo", ".confusions.json")
    assert gfile.is_file() and cfile.is_file() and STUDIO in gfile.parents and PLUGIN not in gfile.parents
    terms = {c["term"]: c["tier"] for c in gl.channel_terms("demo")}
    assert terms.get("GlideGrid") == "P3" and terms.get("Il Caffè dei Maker") == "P1", "appresi = P3, profilo invariato"
    assert terms.get("Taskora") == "P2"
    conf = gl.load_confusions("demo")
    by = {(c["term"], a) for c in conf["confusions"] for a in c["aliases"]}
    assert ("GlideGrid", "Glaidgrid") in by and ("Taskora", "Tascora") in by, "fusione profilo + appreso"
    amb = {a for c in conf["confusions"] for a in c.get("ambiguous", [])}
    assert "cloud code" in amb and "Glaidgrid" not in amb, "forma minuscola = ambigua (serve contesto)"
    assert len(conf["sources"]) == 2
    # il prompt storico (transcript già fatti) non cambia; il nuovo include P3 solo se l'episodio lo nomina
    assert "GlideGrid" not in yc.glossary_terms("demo") and "GlideGrid" in yc.glossary_terms("demo", learned=True)
    rows = gl.ranked_prompt_terms({"channel": "demo"}, wd, None)
    assert "GlideGrid" not in [x["term"] for x in rows]
    rows = gl.ranked_prompt_terms({"channel": "demo", "glossary_extra": ["GlideGrid"]}, wd, None)
    assert "GlideGrid" in [x["term"] for x in rows]
    g = gl.build_glossary(wd, {"channel": "demo", "glossary_extra": ["GlideGrid"]})
    t = next(x for x in g["terms"] if x["term"] == "GlideGrid")
    assert any(a["form"] == "Glaidgrid" and a["origin"] == "learned" for a in t["aliases"])
    # ritrattare la correzione toglie il termine all'update
    L.retract(conn, r["event"], "sbagliata")
    L.update_channel(conn, "demo")
    assert "GlideGrid" not in gfile.read_text() and ("GlideGrid", "Glaidgrid") not in {
        (c["term"], a) for c in gl.load_confusions("demo")["confusions"] for a in c["aliases"]}


def test_integration_thumb_engine_glossary_context():
    """Integrazione (I): una fonte per i priori thumbnail (yt-thumb-learn), concept → rank, confusioni apprese
    prudenti (ambigue con parole di contesto), tabelle markdown intatte, esito decisivo = decisive_weight lavori."""
    conn = fresh_db("integ")
    wd = make_wd("demo", "2026-10-07-integ")
    cs = [concept("A", "duo", "claim", "intenso"), concept("B", "prova", "proof", "sorriso"),
          concept("C", "ritratto", "claim", "sorpresa", hook="ABBIAMO DECISO DI VENDERE")]
    write_thumbs(wd, cs)
    r = L.ingest(conn, wd, ["thumbnail"])
    assert r["skills"]["thumbnail"]["thumb_learn"]["renders"] == 3, r
    assert conn.execute("SELECT COUNT(*) FROM thumb_records WHERE workdir=?", (str(wd.resolve()),)).fetchone()[0] >= 3
    # concept candidati → yt-thumb-learn rank (2 sfruttamento + 1 esplorazione, ≥ 2 leve)
    out = L.suggest(conn, "demo", "thumbnail", cs, k=3, seed=3)
    assert out["engine"] == "yt-thumb-learn rank" and len(out["slate"]) == 3, out
    assert [c["role"] for c in out["slate"]].count("esplorazione") == 1
    assert len({c["lever"] for c in out["slate"]}) >= 2
    # nessuna riga thumbnail.* in learn_priors: la fonte è una sola
    L.update_priors(conn, "demo")
    assert not conn.execute("SELECT COUNT(*) FROM learn_priors WHERE feature LIKE 'thumbnail.%'").fetchone()[0]
    assert {x["source"] for x in L.prior_rows(conn, "demo", "thumbnail")} == {"yt-thumb-learn"}
    # «ammissione» è una forma del gancio anche per yt-learn
    assert L.hook_family("ABBIAMO DECISO DI VENDERE") == "ammissione"
    # confusioni apprese: «Marco» (parola in vocale) è ambigua e porta le entità viste vicino; «Glaidgrid» no
    yc.write_json(wd / "analysis" / "transcript.words.json", {"words": [
        {"w": w} for w in "ho conosciuto Taskora a una fiera di settore e poi ho scritto a Marco per dire".split()]})
    L.record_correction(conn, channel="demo", kind="transcript", before="Marco", after="Mirko", workdir=wd)
    conf = {(c["term"], c["aliases"][0]): c for c in json.loads(yc.learned_file("demo", ".confusions.json").read_text())["confusions"]}
    mirko = conf[("Mirko", "Marco")]
    assert mirko["ambiguous"] == ["Marco"] and "Taskora" in mirko["context_words"], mirko
    g = gl.build_glossary(wd, {"channel": "demo"})
    t = next(x for x in g["terms"] if x["term"] == "Mirko")
    assert "Taskora" in t["context"] and any(a["form"] == "Marco" and a["ambiguous"] for a in t["aliases"])
    assert L.alias_is_ambiguous("Marco") and not L.alias_is_ambiguous("Glaidgrid")
    # yt-postcorrect: un alias appreso vale solo con il suo contesto vicino; anche di più parole
    import postcorrect as pc
    L.record_correction(conn, channel="demo", kind="transcript", before="Pixel Forge Lab io", after="PixelForgeLab.io",
                        workdir=wd, context="il vecchio progetto, un antenato di Nimbly")
    g = gl.build_glossary(wd, {"channel": "demo"})

    def run(text: str) -> tuple[str, list]:
        doc = {"words": [{"w": w, "start": float(i), "end": i + 0.5} for i, w in enumerate(text.split())]}
        new, rep = pc.correct_doc(doc, g, {"channel": "demo"})
        return " ".join(w["w"] for w in new["words"]), rep
    out, _ = run("ho fatto una proposta a Marco e poi Taskora è cresciuto")
    assert "Mirko" in out, out                                   # Taskora vicino: corretto in automatico
    out, _ = run("ho fatto una proposta a Marco e poi abbiamo cenato insieme")
    assert "Marco" in out and "Mirko" not in out, out            # nessun contesto: resta (SUSPECT)
    out, _ = run("si chiamava Pixel Forge Lab io, un antenato di Nimbly")
    assert "PixelForgeLab.io," in out, out                       # alias di quattro parole → un termine
    out, _ = run("si chiamava Pixel Forge Lab io, un sito qualunque")
    assert "PixelForgeLab.io" not in out, out
    # unità e forme non risolte non diventano mai correzioni apprese (H9)
    for before, after in (("MRAR", "MRR"), ("potenti", "utenti?")):
        try:
            L.record_correction(conn, channel="demo", kind="transcript", before=before, after=after, workdir=wd)
            raise AssertionError("atteso rifiuto")
        except L.LearnError:
            pass
    # una riga aggiunta in coda a una tabella non la spezza
    md = "## 16.1 Lezioni\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## 17. Altro\n"
    new = L.insert_in_section(md, "| 3 | 4 |", "16.1")
    assert "| 1 | 2 |\n| 3 | 4 |\n" in new, new
    # un esito decisivo vale decisive_weight lavori
    st = {**L.settings(), "min_evidence": 3, "decisive_weight": 3}
    one = {"state": "candidata", "channel": "demo", "scope": "channel",
           "evidence_json": json.dumps([{"video": "v1", "kind": "pro", "decisive": True}])}
    assert L.lesson_state(one, st) == "pronta"
    assert L.lesson_state(one, {**st, "decisive_weight": 1}) == "candidata"
    # «pronta» solo dove una PR è possibile: un cliente resta locale anche con un esito decisivo
    assert L.lesson_state({**one, "channel": "acme"}, st) == "candidata"


def test_outcomes_tier0_and_due():
    conn = fresh_db("due")
    assert L.views_at_age([(5, 100), (9, 180)], 7, 2) == (140.0, "interpolato")
    assert L.views_at_age([(9, 180)], 7, 2)[0] == 180.0
    assert L.views_at_age([(1, 10), (20, 400)], 7, 2) == (None, "età non allineata")   # mai a cavallo di 19 giorni
    base_day = TODAY - _dt.timedelta(days=200)
    for i, views in enumerate((100, 120, 140, 90)):
        add_video(conn, f"prev{i:07d}", base_day + _dt.timedelta(days=14 * i), {6: views - 10, 8: views + 10})
    pub = TODAY - _dt.timedelta(days=10)
    add_video(conn, "newvid00001", pub, {7: 300})
    res = L.compute_outcome(conn, "newvid00001", "d7")
    assert res["tier"] == 0 and res["n_baseline"] == 4 and res["baseline"] == 110.0, res
    assert res["verdict"] == "sopra" and res["derived_note"]
    # scadenze: pubblicato 10 giorni fa → D+7 dovuto (dal giorno 9), T+48h fuori finestra, D+28 non ancora
    L.publish(conn, channel="demo", video_id="newvid00001", golden=False)
    due = L.due_items(conn, "demo")
    assert [(r["video_id"], r["checkpoint"]) for r in due["outcome_pulls"]] == [("newvid00001", "d7")], due
    pulled = L.pull_outcomes(conn, "demo")
    assert len(pulled) == 1 and pulled[0]["verdict"] == "sopra"
    due = L.due_items(conn, "demo")
    assert not due["outcome_pulls"] and [r["checkpoint"] for r in due["reviews"]] == ["d7"]
    with conn:
        conn.execute("UPDATE learn_outcomes SET reviewed_at=? WHERE video_id='newvid00001'", (ytdb.now_iso(),))
    assert not L.due_items(conn, "demo")["reviews"]
    # pochi confronti → non leggibile
    add_video(conn, "lonely00001", TODAY - _dt.timedelta(days=10), {7: 50}, channel_id="UCaltro", fmt="long")
    assert L.compute_outcome(conn, "lonely00001", "d7")["verdict"] == "non leggibile"


def test_session_hint():
    hint = PLUGIN / "scripts" / "yt" / "bin" / "session-hint.sh"
    env = {**os.environ, "YT_DATA": str(TMP / "nodata-dev")}
    (TMP / "nodata-dev").mkdir(exist_ok=True)
    (TMP / "nodata-dev" / ".setup-ok").write_text("fingerprint=x\n")
    os.utime(TMP / "nodata-dev" / ".setup-ok", None)

    def run(studio: Path) -> tuple[str, float]:
        t0 = time.time()
        p = subprocess.run(["/bin/bash", str(hint)], env={**env, "YT_STUDIO": str(studio)}, capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        dt = time.time() - t0
        if not p.stdout.strip():
            return "", dt
        # un solo oggetto JSON: systemMessage per l'operatore (lo stdout semplice di SessionStart lo vede solo Claude),
        # additionalContext con le stesse righe per Claude
        out = json.loads(p.stdout)
        ctx = out["hookSpecificOutput"]
        assert ctx["hookEventName"] == "SessionStart" and ctx["additionalContext"] == out["systemMessage"], out
        return out["systemMessage"], dt

    def learning_lines(out: str) -> list[str]:
        return [ln for ln in out.splitlines() if "apprendimento" in ln]

    out, _ = run(TMP / "studio-vuoto")                 # database assente → muto
    assert not learning_lines(out), out
    s2 = TMP / "studio-hint"
    (s2 / "data").mkdir(parents=True, exist_ok=True)
    conn = L.connect(s2 / "data" / "yt.db")
    out, _ = run(s2)                                    # niente di dovuto → muto
    assert not learning_lines(out), out
    add_video(conn, "hintvid0001", TODAY - _dt.timedelta(days=10), {7: 10})
    L.publish(conn, channel="demo", video_id="hintvid0001", golden=False)
    with conn:
        conn.execute("INSERT INTO learn_proposals(id, channel, scope, title, state, targets_json, created_at, updated_at) "
                     "VALUES ('p1','demo','channel','t','in_attesa','[]','x','x')")
    conn.close()
    out, dt = run(s2)
    lines = learning_lines(out)
    assert len(lines) == 2, out
    assert "1 esito da leggere (demo)" in lines[0] and "/youtube:review" in lines[0], lines
    assert "1 proposta di miglioramento in attesa" in lines[1] and "/youtube:learn" in lines[1], lines
    assert dt < 1.0, dt
    # con la vista di yt-thumb-learn: stesso video e checkpoint contati una volta, gli altri si sommano
    conn = sqlite3.connect(s2 / "data" / "yt.db")
    conn.executescript("""CREATE VIEW thumb_learn_due AS
        SELECT 'demo' AS channel, 'hintvid0001' AS video_id, 'd7' AS checkpoint, '2026-01-01' AS due_date, 'outcome' AS task
        UNION ALL SELECT 'acme', 'othervid001', 'd28', '2026-01-01', 'outcome'
        UNION ALL SELECT 'demo', 'othervid002', 'd7', '2026-01-01', 'postmortem'
        UNION ALL SELECT 'demo', NULL, 'refs', '2026-01-01', 'refs';""")
    conn.close()
    out, dt = run(s2)
    lines = learning_lines(out)
    assert "2 esiti da leggere e 1 post-mortem da fare (acme, demo)" in lines[0], lines
    assert "riferimenti di nicchia da rinfrescare" in lines[1], lines
    assert dt < 1.0, dt
    # con la riga del setup (dipendenze cambiate) l'apprendimento si stringe in una riga: mai più di due righe in tutto
    os.utime(TMP / "nodata-dev" / ".setup-ok", (0, 0))
    out, dt = run(s2)
    all_lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(all_lines) == 2 and "/youtube:setup" in all_lines[0], out
    assert "/youtube:review" in all_lines[1] and "proposta di miglioramento in attesa" in all_lines[1], out
    assert dt < 1.0, dt
    # senza il marcatore del setup: solo la riga del setup, niente apprendimento
    (TMP / "nodata-dev" / ".setup-ok").rename(TMP / "nodata-dev" / ".setup-ok.bak")
    try:
        out, _ = run(s2)
        assert out.count("\n") == 0 and "/youtube:setup" in out and "apprendimento" not in out, out
    finally:
        (TMP / "nodata-dev" / ".setup-ok.bak").rename(TMP / "nodata-dev" / ".setup-ok")
    os.utime(TMP / "nodata-dev" / ".setup-ok", None)


def _prep_repo(target_rel: str) -> tuple[Path, Path]:
    base = Path(tempfile.mkdtemp(prefix="git-", dir=TMP))
    origin, repo = base / "origin.git", base / "repo"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    for rel in (".claude-plugin/plugin.json", target_rel):
        dst = repo / REPO_SUB / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PLUGIN / rel, dst)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    return repo, origin


def test_propose_diff_validity_and_guards():
    conn = fresh_db("propose")
    L._KIND_MEMO.clear()
    lv = ready_lesson(conn)
    target = "docs/yt/knowledge/07-thumbnails.md"
    orig = (PLUGIN / target).read_text()
    block = "- Appreso sul canale demo: al G2 il duo con espressione intensa è stato scelto 3 volte su 3 [appreso: scelte, n=3]."
    p = L.propose(conn, title="Duo intenso come primo concept", lesson_ids=[lv["id"]], target=target, append=block,
                  anchor="16. Scoreboard and learning", rationale="Tre G2 coerenti sul canale demo.")
    data = json.loads(Path(p["json"]).read_text())
    diff = data["changes"][0]["diff"]
    new = L.apply_unified_diff(orig, diff)
    assert block in new and new.index(block) > orig.index("## 16. Scoreboard and learning")
    assert new.index(block) < orig.index("## 17. Generative AI policy") + len(block) + 2
    assert CO_AUTHOR_OK(data["commit_message"]) and Path(p["md"]).read_text().startswith("# Proposta")
    assert L.lesson_view(L.lesson_get(conn, lv["id"]))["state"] == "proposta"
    # git apply --check sulla stessa base
    repo, _ = _prep_repo(target)
    pf = TMP / "x.patch"
    pf.write_text(diff)
    subprocess.run(["git", "-C", str(repo), "apply", "--check", f"--directory={REPO_SUB}", str(pf)], check=True)
    # diff esplicito: normalizzato e verificato
    lv2 = ready_lesson(conn, text="Nel brief G2 mostra sempre n e confidenza accanto al concept consigliato")
    alt = orig.replace("## 16. Scoreboard and learning\n", "## 16. Scoreboard and learning\n\nRiga nuova.\n", 1)
    p2 = L.propose(conn, title="Riga nuova", lesson_ids=[lv2["id"]], target=REPO_SUB + "/" + target,
                   diff=L.make_diff(target, orig, alt))
    assert p2["target"] == target and p2["kind"] == "diff"
    stale = L.make_diff(target, orig.replace("## 16.", "## 16bis.", 1), alt)
    try:
        L.apply_unified_diff(orig, stale)
        raise AssertionError("diff non applicabile accettato")
    except L.LearnError:
        pass
    # regole dure: sezione protetta, file vietato, chiavi del profilo
    lv3 = ready_lesson(conn, text="Nei ritagli dei duo il bordo va controllato a mano")
    for kw in ({"target": target, "append": "- x", "anchor": "11.2 Policy ladder"},
               {"target": "docs/yt/knowledge/11-compliance-safety.md", "append": "- x"},
               {"target": "scripts/yt/bin/guard.sh", "append": "# x"},
               {"target": "docs/yt/channels/_template.md", "replace_old": "release_required: true",
                "replace_new": "release_required: false"},
               {"target": "docs/yt/channels/demo.md", "append": "- x"}):
        try:
            L.propose(conn, title="Prova vietata", lesson_ids=[lv3["id"]], **kw)
            raise AssertionError(f"proposta vietata accettata: {kw}")
        except L.LearnError as exc:
            assert "regole dure" in str(exc) or "vietata" in str(exc) or "protette" in str(exc), exc
    # privacy: percorso assoluto, cliente, ospite non nel glossario
    for bad in ("- vedi /Users/operatore/youtube-studio/work/demo/x.png", "- come per ACME Pasticceria",
                "- come nella thumbnail di Paolo Ferri"):
        if "Paolo" in bad:   # serve un ospite registrato da un ingest
            wd = make_wd("demo", "2026-09-30-ospite")
            write_thumbs(wd, [concept("A", "duo", "claim", "intenso")])
            L.ingest(conn, wd, ["thumbnail"])
        try:
            L.propose(conn, title="Privacy", lesson_ids=[lv3["id"]], target=target, append=bad,
                      anchor="16. Scoreboard and learning")
            raise AssertionError(f"privacy non rilevata: {bad}")
        except L.LearnError as exc:
            assert "privacy" in str(exc), exc
    # lezioni non pronte, o di un cliente
    young = L.lesson_add(conn, channel="demo", text="Una sola osservazione non basta", evidence=[])
    try:
        L.propose(conn, title="x", lesson_ids=[young["id"]], target=target, append="- x")
        raise AssertionError("lezione non pronta accettata")
    except L.LearnError as exc:
        assert "pronta" in str(exc)
    wdc = [make_wd("acme", f"2026-09-0{i}-c") for i in range(3)]
    evc = [L.record_correction(conn, channel="acme", kind="copy", before="a", after="b", workdir=w)["event"] for w in wdc]
    lc = L.lesson_add(conn, channel="acme", text="Il copy del cliente evita i superlativi", evidence=evc[:1])
    for e in evc[1:]:
        lc = L.lesson_evidence(conn, lc["id"], [e], contra=False)
    try:
        L.propose(conn, title="cliente", lesson_ids=[lc["id"]], target=target, append="- x")
        raise AssertionError("lezione di un cliente in PR")
    except L.LearnError as exc:
        assert "restano locali" in str(exc)


def CO_AUTHOR_OK(msg: str) -> bool:
    return msg.rstrip().endswith(L.CO_AUTHOR)


def test_propose_pr_dry_run():
    conn = fresh_db("pr")
    L._KIND_MEMO.clear()
    lv = ready_lesson(conn, text="Al G2 il concept con la prova vera vince sui duo generici")
    target = "docs/yt/knowledge/07-thumbnails.md"
    p = L.propose(conn, title="Prova vera prima dei duo generici", lesson_ids=[lv["id"]], target=target,
                  append="- Appreso: la prova vera batte i duo generici al G2 [appreso: scelte, n=3].",
                  anchor="16. Scoreboard and learning")
    repo, origin = _prep_repo(target)
    head = git(repo, "rev-parse", "HEAD")
    res = L.propose_pr(conn, repo=repo, dry_run=True, validate=False)
    plan = res["results"][0]
    assert plan["apply_check"] == "ok" and plan["branch"] == f"learn/{p['id']}" and plan["branch"].startswith("learn/")
    assert any("gh pr create --draft" in c for c in plan["would_run"])
    assert git(repo, "rev-parse", "HEAD") == head and not git(repo, "status", "--porcelain").strip()
    assert not git(repo, "branch", "--list", "learn/*").strip(), "dry-run non crea branch"
    assert L.proposals_list(conn)[0]["state"] == "in_attesa"
    # clone sporco → rifiuto
    (repo / "sporco.txt").write_text("x")
    try:
        L.propose_pr(conn, repo=repo, dry_run=True, validate=False)
        raise AssertionError("clone sporco accettato")
    except L.LearnError as exc:
        assert "non committate" in str(exc)
    (repo / "sporco.txt").unlink()
    # giro vero senza gh: push del solo branch learn/… sull'origin locale, main intatto
    main_before = git(origin, "rev-parse", "main")
    res = L.propose_pr(conn, repo=repo, no_pr=True, validate=False)
    assert res["results"][0]["commit"]
    heads = git(origin, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    assert f"learn/{p['id']}" in heads and git(origin, "rev-parse", "main") == main_before
    msg = git(origin, "log", "-1", "--format=%B", f"learn/{p['id']}")
    assert L.CO_AUTHOR in msg
    show = git(origin, "show", f"learn/{p['id']}:{REPO_SUB}/{target}")
    assert "la prova vera batte i duo generici" in show
    assert L.proposals_list(conn, "in_pr")[0]["id"] == p["id"]
    assert not git(repo, "worktree", "list").count("\n") > 1, "worktree temporaneo rimosso"
    assert L.propose_pr(conn, repo=repo, dry_run=True, validate=False)["results"] == []
    # origin/main è andato avanti sullo stesso file: una proposta «append» si riapplica sul file nuovo
    lv2 = ready_lesson(conn, text="Nel brief G2 il concept di esplorazione va dichiarato con il suo n")
    p2 = L.propose(conn, title="Esplorazione dichiarata al G2", lesson_ids=[lv2["id"]], target=target,
                   append="- Appreso: l'esplorazione va dichiarata con n al G2 [appreso: scelte, n=3].",
                   anchor="16. Scoreboard and learning")
    f = repo / REPO_SUB / target
    f.write_text(f.read_text().replace("## 16. Scoreboard and learning\n", "## 16. Scoreboard and learning\n\nRiga upstream.\n", 1))
    git(repo, "commit", "-qam", "upstream")
    git(repo, "push", "-q", "origin", "main")
    plan = L.propose_pr(conn, repo=repo, dry_run=True, validate=False)["results"][0]
    assert plan["id"] == p2["id"] and plan["rebased"] == [target] and plan["apply_check"] == "ok", plan
    # una proposta respinta riporta la lezione ad «attiva» (resta Tier A)
    L.set_proposal_state(conn, p2["id"], "respinta")
    assert L.lesson_view(L.lesson_get(conn, lv2["id"]))["state"] == "attiva"


def test_thresholds_tighten_only():
    conn = fresh_db("thr")
    t = L.threshold_set(conn, channel="demo", name="face_size", direction="min", value=0.40, level="error")
    assert t["value"] == 0.40 and t["baseline"] == 0.35
    for v in (0.30, 0.38):
        try:
            L.threshold_set(conn, channel="demo", name="face_size", direction="min", value=v)
            raise AssertionError(f"allentata a {v}")
        except L.LearnError as exc:
            assert "PR" in str(exc)
    try:
        L.threshold_set(conn, channel="demo", name="face_size", direction="min", value=0.41, level="warn")
        raise AssertionError("errore → warning accettato")
    except L.LearnError:
        pass
    assert L.threshold_set(conn, channel="demo", name="display_upscale", direction="max", value=1.5)["value"] == 1.5
    data = json.loads(yc.learned_file("demo", ".thresholds.json").read_text())
    assert {x["name"] for x in data["thresholds"]} == {"face_size", "display_upscale"}


def test_cli_smoke():
    """Il comando vero (bin/yt-learn → _run → venv) con lo studio temporaneo."""
    exe = PLUGIN / "bin" / "yt-learn"
    if not os.environ.get("YT_DATA"):
        print("    (salto: YT_DATA non impostata)")
        return
    env = {**os.environ, "YT_STUDIO": str(TMP / "studio-cli")}
    wd = make_wd("demo", "2026-10-05-cli")

    def cli(*args: str) -> dict:
        p = subprocess.run([str(exe), *args], env=env, capture_output=True, text=True)
        out = json.loads(p.stdout)
        assert out["ok"], (args, out, p.stderr[-500:])
        return out
    # la cartella di lavoro sta nello studio dei test: il percorso assoluto vale ovunque
    cli("ingest", str(wd), "--skill", "all")
    cli("job", "start", "--channel", "demo", "--skill", "strategy,review")
    cli("correction", "--channel", "demo", "--kind", "transcript", "--from", "Nimbli", "--to", "Nimbly")
    out = cli("job", str(wd), "--skill", "thumbnail", "--status", "in attesa di approvazione G2")
    assert out["job"]["status"].startswith("in attesa") and Path(out["playbook"]).is_file()
    rep = cli("report", "--channel", "demo", "--focus", "thumbnails")
    assert rep["focus"] == "thumbnail" and rep["playbook_lines"] <= 150
    assert cli("due")["proposals_pending"] == 0


def test_review_hard_rules_and_thresholds():
    """Revisione avversaria (V): parafrasi delle regole dure, soglie che non si allentano per vie traverse."""
    bad = ["Il consenso non è necessario per questo canale", "La release non serve per questo canale", "Skip consent on demo",
           "Usa Higgsfield per migliorare il volto dell'ospite", "Cambia l'espressione dell'ospite per renderla sorpresa",
           "guest_style graphic come scelta predefinita", "Carica la thumbnail su YouTube appena pronta",
           "Il G2 si può saltare per le thumbnail del canale", "Delega automaticamente il G2",
           "La soglia del volto si può abbassare a 0.30", "face_size minimo 0.30 va bene",
           "Errore QA declassato a warning per il canale demo", "Ignora gli errori della QA quando il render è urgente",
           "Nel titolo chiama l'host Giuly, è più simpatico"]          # H6: nome che il profilo vieta (public_names.never)
    good = ["Mostra le thumbnail ai due host nello stesso ordine del brief", "Crea i concept direttamente dai selects",
            "Se il controllo hook_words fallisce, togli una parola dal gancio", "Il master per YouTube va esportato in HEVC 4K",
            "Mai upscale generativo sul volto: solo upscale non generativo con gate QA",
            "Soglia del volto più severa: face_size minimo 0.40 sui duo",
            "Grade mono (livello 2b) ammesso su duo: stessa curva su persone e plate",
            "- vedi /Users/operatore/youtube-studio/work/demo/x.png",
            "Mai «Giuly» nei titoli: sempre Giulia Conti, come dice il profilo"]
    assert [t for t in bad if not L.hard_rule_hit(t)] == []
    assert L.hard_rule_hit("Nel titolo chiama l'host Giuly, è più simpatico") == "H6"
    assert [t for t in good if L.hard_rule_hit(t)] == []
    conn = fresh_db("v-thr")
    for kw in ({"value": 0.30, "baseline": 0.25},):                          # --baseline più permissivo del toolkit
        try:
            L.threshold_set(conn, channel="demo", name="face_size", direction="min", **kw)
            raise AssertionError("allentamento via --baseline accettato")
        except L.LearnError as exc:
            assert "toolkit" in str(exc)
    L.threshold_set(conn, channel="demo", name="face_size", direction="min", value=0.40)
    try:                                                                       # cambio di direzione = limite perso
        L.threshold_set(conn, channel="demo", name="face_size", direction="max", value=0.30, baseline=1.0)
        raise AssertionError("cambio di direzione accettato")
    except L.LearnError as exc:
        assert "direzione" in str(exc) or "limite" in str(exc)
    s = config.learning_settings({"learning_explore_arms": 0, "learning_min_evidence": 0, "learning_prior_strength": 0.1,
                                  "learning_elo_k": 400, "learning_pref_weight": 9})
    assert (s["explore_arms"], s["min_evidence"], s["prior_strength"], s["elo_k"], s["pref_weight"]) == (1, 2, 2.0, 16.0, 1.0)


def test_review_proposals_targets_privacy_rollback():
    """Revisione avversaria (V): destinazioni del sistema di apprendimento, privacy della decisione dell'operatore,
    canali non condivisibili, ritiro di una lezione con proposta in attesa, JSON manomesso, due operatori."""
    conn = fresh_db("v-prop")
    L._KIND_MEMO.clear()
    target = "docs/yt/knowledge/07-thumbnails.md"
    lv = ready_lesson(conn, text="Al G2 meglio tre concept con leve diverse")
    for bad_target in ("scripts/yt/lib/thumb_learn.py", "commands/learn.md", "docs/yt/knowledge/13-learning-loop.md",
                       "scripts/yt/lib/ytcore.py", "scripts/yt/lib/postcorrect.py"):
        try:
            L.propose(conn, title="x", lesson_ids=[lv["id"]], target=bad_target, append="# x")
            raise AssertionError(f"destinazione accettata: {bad_target}")
        except L.LearnError as exc:
            assert "vietata" in str(exc) or "perimetro" in str(exc), exc
    try:
        L.propose(conn, title="Tre leve", lesson_ids=[lv["id"]], target=target, append="- tre leve",
                  anchor="16. Scoreboard and learning",
                  operator_decision="ok, vedi /Users/operatore/youtube-studio/work/demo/x — scrivimi a operatore@example.com")
        raise AssertionError("privacy della decisione dell'operatore non controllata")
    except L.LearnError as exc:
        assert "privacy" in str(exc)
    # un cliente in learning_pr_channels resta locale: lezione al massimo «attiva», niente proposta
    old = dict(yc.LEARNING or {})
    yc.LEARNING = {**old, "pr_channels": ["demo", "acme", "pers"]}
    try:
        wdc = [make_wd("acme", f"2026-08-0{i}-c") for i in range(3)]
        evc = [L.record_correction(conn, channel="acme", kind="copy", before="a", after="b", workdir=w)["event"] for w in wdc]
        lc = L.lesson_add(conn, channel="acme", text="Il copy evita i superlativi", evidence=evc[:1])
        for e in evc[1:]:
            lc = L.lesson_evidence(conn, lc["id"], [e], contra=False)
        assert lc["state"] == "attiva", lc
        assert "acme" not in L.pr_channels()
        # una lezione GLOBALE di un canale personale resta locale, anche se il profilo dice share_lessons: true
        (CHANNELS / "pers.md").write_text("---\nslug: pers\nkind: personal\nshare_lessons: true\n"
                                          "name: \"Canale Personale\"\n---\nProva.\n")
        L._KIND_MEMO.clear()
        L._profile.cache_clear()
        wdp = [make_wd("pers", f"2026-08-1{i}-p") for i in range(3)]
        evp = [L.record_correction(conn, channel="pers", kind="copy", before="a", after="b", workdir=w)["event"] for w in wdp]
        lp = L.lesson_add(conn, channel="pers", text="Il gancio a domanda regge meglio", scope="global", evidence=evp[:1])
        for e in evp[1:]:
            lp = L.lesson_evidence(conn, lp["id"], [e], contra=False)
        assert lp["state"] == "attiva" and lp["scope"] == "global", lp
        assert L.pr_channels() == {"demo"}, L.pr_channels()
        try:
            L.propose(conn, title="x", lesson_ids=[lp["id"]], target=target, append="- x", anchor="16. Scoreboard and learning")
            raise AssertionError("lezione globale di un canale personale in PR")
        except L.LearnError as exc:
            assert "restano locali" in str(exc), exc
    finally:
        yc.LEARNING = old
    # ritiro: la proposta in attesa viene ritirata e propose-pr non la porta in PR
    p = L.propose(conn, title="Tre leve", lesson_ids=[lv["id"]], target=target, append="- tre leve",
                  anchor="16. Scoreboard and learning")
    out = L.lesson_retire(conn, lv["id"], "sbagliata")
    assert [w["id"] for w in out["proposals_withdrawn"]] == [p["id"]]
    assert L.proposals_list(conn, None)[-1]["state"] == "ritirata"
    repo, origin = _prep_repo(target)
    assert L.propose_pr(conn, repo=repo, dry_run=True, validate=False)["results"] == []
    # tutte le prove ritrattate → lezione ritirata (niente residui)
    lv2 = ready_lesson(conn, text="Nel brief G2 il concept consigliato va per primo")
    for e in L.lesson_view(L.lesson_get(conn, lv2["id"]))["evidence"]:
        L.retract(conn, int(e[1:]), "prova")
    L.refresh_lessons(conn, "demo")
    assert L.lesson_get(conn, lv2["id"])["state"] == "ritirata"
    # JSON manomesso: branch verso main e intestazioni del diff su un altro file
    lv3 = ready_lesson(conn, text="Nel brief G2 la leva del concept va scritta per esteso")
    p3 = L.propose(conn, title="Leva per esteso", lesson_ids=[lv3["id"]], target=target, append="- leva per esteso",
                   anchor="16. Scoreboard and learning")
    j = json.loads(Path(p3["json"]).read_text())
    j["branch"] = "learn/x:refs/heads/main"
    Path(p3["json"]).write_text(json.dumps(j))
    try:
        L.propose_pr(conn, repo=repo, ids=[p3["id"]], dry_run=True, validate=False)
        raise AssertionError("branch manomesso accettato")
    except L.LearnError as exc:
        assert "branch non ammesso" in str(exc)
    j["branch"] = f"learn/{p3['id']}"
    j["changes"][0]["diff"] = j["changes"][0]["diff"].replace(f"a/{target}", "a/hooks/hooks.json").replace(
        f"b/{target}", "b/hooks/hooks.json")
    Path(p3["json"]).write_text(json.dumps(j))
    plan = L.propose_pr(conn, repo=repo, ids=[p3["id"]], dry_run=True, validate=False)["results"][0]
    assert plan["files"] == [f"{REPO_SUB}/{target}"] and plan["apply_check"] == "ok", plan
    # due operatori, stesso titolo lo stesso giorno: il secondo prende il suffisso libero, main intatto
    repo2 = repo.parent / "repo-secondo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo2)], check=True)
    git(repo2, "config", "user.email", "d@example.invalid")
    git(repo2, "config", "user.name", "D")
    c1, c2 = fresh_db("v-op1"), fresh_db("v-op2")
    l1, l2 = ready_lesson(c1, text="Duo prima di tutto"), ready_lesson(c2, text="Duo prima di tutto")
    q1 = L.propose(c1, title="Duo primo", lesson_ids=[l1["id"]], target=target, append="- duo (op1)",
                   anchor="16. Scoreboard and learning")
    q2 = L.propose(c2, title="Duo primo", lesson_ids=[l2["id"]], target=target, append="- duo (op2)",
                   anchor="16. Scoreboard and learning")
    assert q1["id"] == q2["id"]
    main_before = git(origin, "rev-parse", "main")
    b1 = L.propose_pr(c1, repo=repo, ids=[q1["id"]], no_pr=True, validate=False)["results"][0]["branch"]
    b2 = L.propose_pr(c2, repo=repo2, no_pr=True, validate=False)["results"][0]["branch"]
    assert b1 == f"learn/{q1['id']}" and b2 == f"{b1}-2", (b1, b2)
    assert git(origin, "rev-parse", "main") == main_before


def test_tier_b_opt_in_rule():
    """Tier B opt-in (13 §1.2): un canale è condivisibile solo se è in learning_pr_channels E il profilo dice kind: own
    E share_lessons: true (booleano). Nei due sensi: elencato senza consenso nel profilo → locale; consenso nel profilo
    senza elenco → locale. yt-learn e yt-thumb-learn applicano la stessa regola."""
    import thumb_learn as TL
    conn = fresh_db("optin")
    old = dict(yc.LEARNING or {})
    (CHANNELS / "stringa.md").write_text("---\nslug: stringa\nkind: own\nshare_lessons: \"true\"\n---\nValore non booleano.\n")
    L._KIND_MEMO.clear()
    L._profile.cache_clear()
    try:
        # elencati tutti: conta solo demo (own + share_lessons: true); esempio è own senza consenso, acme è un cliente,
        # stringa ha share_lessons come stringa
        yc.LEARNING = {**old, "pr_channels": ["demo", "esempio", "acme", "stringa", "fantasma"]}
        assert L.pr_channels() == {"demo"}, L.pr_channels()
        assert set(yc.shareable_channels(["demo", "esempio", "acme", "stringa"])) == {"demo"}
        assert TL.channel_shareable("demo") and not TL.channel_shareable("esempio") and not TL.channel_shareable("acme")
        # consenso nel profilo ma lista vuota (il default): nessun canale condivisibile
        yc.LEARNING = {**old, "pr_channels": []}
        assert L.pr_channels() == set() and not TL.channel_shareable("demo")
        st = L.settings()
        one = {"state": "candidata", "channel": "demo", "scope": "channel",
               "evidence_json": json.dumps([{"video": f"v{i}", "kind": "pro"} for i in range(3)])}
        assert L.lesson_state(one, st) == "attiva", "senza elenco la lezione non diventa «pronta»"
        # elencato e con consenso: «pronta»; esempio (proprio, non condiviso) resta «attiva» anche con 3 lavori
        yc.LEARNING = {**old, "pr_channels": ["demo", "esempio"]}
        st = L.settings()
        assert L.lesson_state(one, st) == "pronta"
        assert L.lesson_state({**one, "channel": "esempio"}, st) == "attiva"
        wde = [make_wd("esempio", f"2026-07-0{i}-e") for i in range(3)]
        eve = [L.record_correction(conn, channel="esempio", kind="chapter", before=f"T{i}", after=f"T{i}?",
                                   workdir=w)["event"] for i, w in enumerate(wde)]
        le = L.lesson_add(conn, channel="esempio", text="I titoli dei capitoli come domanda", skill="chapters", evidence=eve[:1])
        for e in eve[1:]:
            le = L.lesson_evidence(conn, le["id"], [e], contra=False)
        assert le["state"] == "attiva", le
        assert L.report(conn, "esempio", write=False)["shareable"] is False
        pb, _ = L.write_playbook(conn, "esempio")
        assert "Proposte per la repo (Tier B): spente" in pb.read_text()
        try:
            L.propose(conn, title="x", lesson_ids=[le["id"]], target="docs/yt/knowledge/07-thumbnails.md", append="- x")
            raise AssertionError("lezione di un canale non condiviso in PR")
        except L.LearnError as exc:
            assert "share_lessons" in str(exc), exc
        # i nomi dei canali non condivisi restano nel filtro di privacy; demo (condiviso) no
        names, _, _ = L._privacy_terms(conn)
        assert "esempio" in names and "Canale Esempio" in names and "demo" not in names, names
    finally:
        yc.LEARNING = old
        (CHANNELS / "stringa.md").unlink(missing_ok=True)
        L._KIND_MEMO.clear()
        L._profile.cache_clear()


def test_templates_and_accents_from_brand():
    """Template e accenti generici: i template inclusi nel plugin (duo, ritratto, scena, prova, generic) e quelli del
    brand del canale (<slug>-*.html nei brands_dirs) che li sovrascrivono; gli accenti dai token del brand."""
    tdir = TMP / "node-templates"
    (tdir / "templates").mkdir(parents=True, exist_ok=True)
    for name in ("duo", "ritratto", "scena", "prova", "generic", "_common"):
        (tdir / "templates" / f"{name}.html").write_text("<html></html>")
    brands = TMP / "brands"
    (brands / "demo" / "templates").mkdir(parents=True, exist_ok=True)
    (brands / "demo" / "tokens.json").write_text(json.dumps({"slug": "demo", "accents": ["corallo", "menta"]}))
    (brands / "demo" / "templates" / "demo-duo.html").write_text("<html></html>")
    (brands / "demo" / "templates" / "demo-L1.html").write_text("<html></html>")
    old_node, old_dirs, old_set = yc.NODE_DIR, yc.BRANDS_DIRS, dict(yc._SETTINGS)
    yc.NODE_DIR = tdir
    yc.BRANDS_DIRS = [brands, *old_dirs]
    yc._SETTINGS["brands_dirs"] = yc.BRANDS_DIRS
    L._profile.cache_clear()
    try:
        tpls = L.allowed_templates("demo")
        assert tpls == ["demo-L1", "demo-duo", "ritratto", "scena", "prova", "generic"], tpls   # demo-duo sostituisce duo
        assert L.allowed_templates("acme") == ["duo", "ritratto", "scena", "prova", "generic"]
        assert L.brand_accents("demo") == ["corallo", "menta"]
        assert "corallo" in L.allowed_values(fresh_db("tpl"), "demo", "thumbnail.accent")
    finally:
        yc.NODE_DIR, yc.BRANDS_DIRS = old_node, old_dirs
        yc._SETTINGS.clear()
        yc._SETTINGS.update(old_set)
        L._profile.cache_clear()


def test_review_guest_style_never_learned_default():
    """H1: anche con l'operatore che sceglie sempre «graphic», lo sfruttamento di guest_style resta il default."""
    conn = fresh_db("v-gs")
    rows = [{"channel": "demo", "feature": "thumbnail.guest_style", "value": v, "signal": "scelte", "alpha": a, "beta": b,
             "elo": 1500, "elo_n": 1, "n_jobs": 10, "n_obs": 10, "wins": 0, "losses": 0, "ties": 0, "is_default": int(v == "none"),
             "mean": round(a / (a + b), 3), "ci80": [0, 1], "conf": "media", "source": "test"}
            for v, a, b in (("graphic", 12, 2), ("none", 2.4, 11.6))]
    orig = L.thumb_prior_rows
    L.thumb_prior_rows = lambda c, ch, feature=None: [r for r in rows if not feature or r["feature"] == feature]
    try:
        e = L.suggest(conn, "demo", "thumbnail", seed=1)["features"]["thumbnail.guest_style"]
    finally:
        L.thumb_prior_rows = orig
    assert e["exploit"] == "none" and e["explore"] is None and "graphic" in e["note"], e


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]


def main() -> int:
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    failed = 0
    for t in TESTS:
        if flt and flt not in t.__name__:
            continue
        t0 = time.time()
        try:
            t()
            print(f"ok    {t.__name__} ({time.time() - t0:.2f} s)")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"{'tutti ok' if not failed else f'{failed} falliti'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
