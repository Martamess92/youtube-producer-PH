"""Test dell'apprendimento delle thumbnail (lib/thumb_learn.py, yt-thumb-learn). Niente pytest: assert semplici.
Dati sintetici in una cartella temporanea: YT_STUDIO, la configurazione e i channels_dirs vengono SEMPRE spostati su
cartelle temporanee prima di importare il toolkit, così i test non toccano mai lo studio vero (golden set, riferimenti,
database) né i profili dell'operatore. Canali sintetici: «demo» (proprio e condivisibile), «esempio» (proprio, non
condiviso), «tst» e «cliente» (senza profilo).

Uso (venv del toolkit; YT_DATA = data dir del plugin o una data dir temporanea di install.sh --data):
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_thumb_learn.py            # tutti
  $YT_DATA/venv/bin/python plugins/youtube/scripts/yt/tests/test_thumb_learn.py rank       # solo i test col nome che contiene «rank»
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT_TMP = Path(tempfile.mkdtemp(prefix="yt-thumb-learn-test-"))
CHANNELS = ROOT_TMP / "channels"
os.environ.update({"YT_STUDIO": str(ROOT_TMP / "studio"),        # mai lo studio vero
                   "YT_CONFIG": str(ROOT_TMP / "config.yaml"),     # mai il config.yaml dell'operatore
                   "YT_CHANNELS_DIRS": str(CHANNELS), "YT_VAULT": ""})
(ROOT_TMP / "studio" / "data").mkdir(parents=True, exist_ok=True)
CHANNELS.mkdir(parents=True, exist_ok=True)
# Tier B opt-in: «demo» è elencato e il suo profilo dice kind: own e share_lessons: true; «esempio» è proprio ma non
# condiviso (niente share_lessons): le sue lezioni restano locali
(ROOT_TMP / "config.yaml").write_text("learning_pr_channels: [demo]\n")
_THUMBS = ("thumbnails:\n  default_template: duo\n  default_lever: claim\n  grade_default: natural\n"
           "  grade_allowed: [natural, mono]\n  guest_style_default: none\n")
(CHANNELS / "demo.md").write_text("---\nslug: demo\nkind: own\nshare_lessons: true\nname: \"Il Caffè dei Maker\"\n"
                                  + _THUMBS + "---\nProfilo sintetico.\n")
(CHANNELS / "esempio.md").write_text("---\nslug: esempio\nkind: own\nname: \"Canale Esempio\"\n" + _THUMBS
                                     + "---\nProfilo sintetico, non condiviso.\n")

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"
sys.path.insert(0, str(LIB))

from PIL import Image  # noqa: E402

import thumb_learn as tl  # noqa: E402
import ytcore as yc  # noqa: E402

assert str(yc.STUDIO).startswith(str(ROOT_TMP)), "i test devono girare su uno studio temporaneo"


# ── Aiuti ───────────────────────────────────────────────────────────────────
def tmpdir(name: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix=f"{name}-", dir=ROOT_TMP))
    return d


def db(name: str = "yt.db") -> sqlite3.Connection:
    return tl.connect(tmpdir("db") / name)


def png(path: Path, rgb=(90, 90, 90), size=(384, 216), box=None, box_rgb=(240, 240, 240)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, rgb)
    if box:
        from PIL import ImageDraw
        ImageDraw.Draw(im).rectangle(box, fill=box_rgb)
    im.save(path)
    return path


def cutout(path: Path, kind="camera", layout="full") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(im).ellipse((20, 10, 100, 150), fill=(180, 140, 120, 255))
    im.save(path)
    (path.with_suffix(".meta.json")).write_text(json.dumps({"w": 120, "h": 160, "portrait": {"source": {"kind": kind, "layout": layout}}}))
    return path


def sidecar(wd: Path, name: str, *, template="duo", lever="claim", grade="mono", accent="accent", guest=0.42, host=0.33,
            rows=(0.22, 0.23), hook="HO SBAGLIATO L'AGENDA.", expr="intenso", passed=True, kind="camera", layout="full",
            plate="scene", out_dir="renders", people=2) -> Path:
    rd = wd / "thumbs" / out_dir
    p = png(rd / f"{name}.png")
    png(rd / f"{name}.jpg")
    g = cutout(wd / "thumbs" / "portrait" / f"{name}_guest.png", kind, layout)
    h = cutout(wd / "thumbs" / "portrait" / f"{name}_host.png", "camera", "full")
    heroes = [{"role": "guest", "face_frac": guest, "served_720": {"lap": 800.0}, "face_surround_dL": 31.0}]
    spec_people = [{"role": "guest", "name": "Ospite Finto", "title": "Founder", "path": str(g), "source_path": str(g),
                    "portrait": {"source": {"kind": kind, "layout": layout}}}]
    if people == 2:
        heroes.append({"role": "host", "face_frac": host, "served_720": {"lap": 760.0}, "face_surround_dL": 27.0})
        spec_people.append({"role": "host", "name": "Host Finto", "path": str(h), "source_path": str(h),
                            "portrait": {"source": {"kind": "camera", "layout": "full"}}})
    sd = {"id": name.split("_")[0], "name": name, "template": template, "png": str(p), "jpg": str(p.with_suffix(".jpg")),
          "ok": True, "pass": passed, "errors": [] if passed else ["errore finto"], "warnings": ["avviso"],
          "checks_v2": {"heroes": heroes, "hook_rows": [{"frac": r, "keyword": False} for r in rows], "accents": [accent],
                        "grade": {"mode": grade, "pass": True}, "edge_dark": {"edge_dL_dark": 30.0, "edge_light_share": 0.2},
                        "circle": [{"dL_edge": 25.0}], "silhouette_dL_246": 24.0, "hook_plate_contrast": 12.0},
          "v2": {"plate": {"source": plate}, "hook": {"words": len(tl.hook_words(hook))}},
          "metrics": {"series": {"accents": [accent], "grade": grade, "guest_style": "none"}},
          "spec": {"id": name.split("_")[0], "template": template, "lever": lever, "hook": hook, "keyword": hook.split()[-1].strip("."),
                   "expression_class": expr, "guest_style": "none", "grade": grade, "plate": {"source": plate},
                   "circle_behind": "guest", "people": spec_people, "payoff_at": 12.5}}
    side = rd / f"{name}.render.json"
    side.write_text(json.dumps(sd))
    return side


def workdir(channel="tst", slug="ep", date="2026-10-01", concepts=None) -> Path:
    wd = ROOT_TMP / "studio" / "work" / channel / f"{date}-{slug}-{time.time_ns() % 10**8}"
    (wd / "thumbs").mkdir(parents=True, exist_ok=True)
    (wd / "project.json").write_text(json.dumps({"version": 1, "channel": channel, "slug": slug, "date": date}))
    if concepts is not None:
        (wd / "thumbs" / "concepts.json").write_text(json.dumps(concepts))
    return wd


def concept(cid, template="duo", lever="claim", hook="HO SBAGLIATO L'AGENDA.", grade=None, expr="intenso", variants=None, **kw):
    c = {"id": cid, "template": template, "lever": lever, "hook": hook, "keyword": hook.split()[-1].strip(".?"),
         "expression_class": expr, "payoff_at": 10.0, "title_pair": "Titolo finto", "hypothesis": "ipotesi finta", **kw}
    if grade:
        c["grade"] = grade
    if variants:
        c["variants"] = variants
    return c


def g2_job(conn, channel, chosen_tpl, rejected_tpls, reason="mi piace di più", delegated=False):
    """Un lavoro con un render per template; l'operatore sceglie chosen_tpl."""
    tpls = [chosen_tpl] + list(rejected_tpls)
    wd = workdir(channel, concepts=[concept(chr(65 + i), template=t) for i, t in enumerate(tpls)])
    for i, t in enumerate(tpls):
        sidecar(wd, f"{chr(65 + i)}_{t}", template=t, grade="mono" if t == "duo" else "natural",
                people=2 if t == "duo" else 1)
    tl.ingest_workdir(conn, wd, channel, profile=tl.load_profile(channel))
    tl.record_choice(conn, wd, [f"A_{chosen_tpl}"], None, reason, delegated=delegated)
    return wd


def video(conn, channel, vid, pub: str, snaps: dict[int, int] | None = None, fmt="long"):
    cid = f"UC{channel}"
    conn.execute("INSERT OR IGNORE INTO channels(id, slug, kind, updated_at) VALUES (?,?,?,?)", (cid, channel, "own", "x"))
    conn.execute("INSERT OR REPLACE INTO videos(id, channel_id, title, published_at, format, first_seen, updated_at) "
                 "VALUES (?,?,?,?,?,?,?)", (vid, cid, f"titolo {vid}", pub, fmt, "x", "x"))
    d0 = dt.date.fromisoformat(pub[:10])
    for age, v in (snaps or {}).items():
        conn.execute("INSERT OR REPLACE INTO video_stats_daily(video_id, date, views, source, fetched_at) VALUES (?,?,?,?,?)",
                     (vid, (d0 + dt.timedelta(days=age)).isoformat(), v, "ytdlp", "x"))
    conn.commit()


# ── Caratteristiche ─────────────────────────────────────────────────────────
def test_hook_family_and_buckets():
    assert tl.hook_family("HO PRENOTATO DUE MATRIMONI.") == "ammissione"
    assert tl.hook_family("SOCIA O DA SOLA?") == "domanda"
    assert tl.hook_family("DA ZERO A 210 STUDI") == "numero"
    assert tl.hook_family("IL CODICE NON BASTAVA") == "contro"
    assert tl.hook_family("IL MERCATO TI MENTE", hook_form="contro") == "contro"
    assert tl.hook_family("L'AI SCRIVE IL CODICE") == "affermazione"
    assert len(tl.hook_words("HO SBAGLIATO L'AGENDA.")) == 4          # elisione = 2 parole (come thumb_render)
    assert tl.words_bucket(2) == "<3" and tl.words_bucket(4) == "4" and tl.words_bucket(7) == "6+"
    assert tl.face_bucket(0.42) == "40-45" and tl.face_bucket(34.9) == "30-35" and tl.face_bucket(0.51) == "45+"
    assert tl.rows_bucket(0.202) == "20+" and tl.rows_bucket(0.16) == "15-18" and tl.rows_bucket(0.11) == "<12"
    assert tl.people_value(2) == "duo" and tl.people_value(1) == "solo" and tl.people_value(0) == "nessuno"
    assert tl.face_source_of({"kind": "camera", "layout": "full"}) == "camera-stretta"
    assert tl.face_source_of({"kind": "master", "layout": "inset"}) == "master-inset"
    assert tl.face_source_of({"kind": "still", "image": "x.jpg"}) == "foto"


def test_concept_versions_match_render_names():
    cs = [concept("A", variants=[{"hook": "HO SBAGLIATO L'AGENDA."}, {"hook": "DUE MATRIMONI LO STESSO GIORNO"}]),
          concept("B", template="tst-L1", lever="claim", hook="HO CAMBIATO STRADA")]
    names = [tl.version_name(c.get("id", "X"), c.get("template"), s) for c, s in tl.expand_concepts(cs)]
    assert names == ["A_duo_v1", "A_duo_v2", "B_tst-L1"], names
    fa = tl.concept_features(tl.expand_concepts(cs)[0][0])
    assert fa["grade"] == "natural" and fa["plate"] == "flat" and fa["circle_behind"] == "guest" and fa["guest_style"] == "none"
    # grade: natural di default, mono solo se il profilo (o il concept) lo sceglie
    assert tl.concept_features(cs[0], {"thumbnails": {"grade_default": {"duo": "mono", "others": "natural"}}})["grade"] == "mono"
    assert tl.concept_features(concept("M", grade="mono"))["grade"] == "mono"
    # serie v2 inclusa nel plugin, anche quando un brand la sovrascrive con <slug>-<nome> (07 §8)
    assert tl.v2_base("duo") == "duo" and tl.v2_base("acme-ritratto") == "ritratto"
    assert tl.v2_base("generic") is None and tl.v2_base("tst-L1") is None and tl.v2_base("-duo") is None
    fo = tl.concept_features(concept("O", template="acme-duo"))
    assert fo["hook_font"] == "anton" and fo["circle_behind"] == "guest" and fo["grade"] == "natural"
    fb = tl.concept_features(cs[1])
    assert fb["grade"] is None and fb["guest_style"] is None, fb    # i template v1 non hanno grade né guest_style
    # «contro» come leva (vecchio contratto) → claim + forma del gancio negazione
    fc = tl.concept_features(concept("C", lever="contro", hook="IL MERCATO TI MENTE"))
    assert fc["lever"] == "claim" and fc["hook_family"] == "contro"
    assert fa["hook_font"] == "anton" and fb["hook_font"] is None and fa["people"] == "nessuno"


def test_render_features_from_sidecar():
    wd = workdir()
    side = sidecar(wd, "A_duo_v1", guest=0.421, rows=(0.205, 0.231), accent="accent_2", kind="master", layout="inset")
    f, m = tl.render_features(json.loads(side.read_text()))
    assert f["template"] == "duo" and f["accent"] == "accent_2" and f["grade"] == "mono"
    assert f["face_pct"] == "40-45" and f["rows_pct"] == "20+" and f["face_source"] == "master-inset"
    assert f["people"] == "duo" and f["plate"] == "scene" and f["hook_family"] == "ammissione" and f["hook_words"] == "4"
    assert f["hook_font"] == "anton" and m["n_people"] == 2
    assert m["guest_face_pct"] == 42.1 and m["host_face_pct"] == 33.0 and m["rows_pct_min"] == 20.5
    assert m["served_detail_min"] == 760.0 and m["edge_dL_dark"] == 30.0 and m["pass"] is True and m["errors"] == 0


def test_ingest_idempotent_with_qa_and_cold():
    conn = db()
    cs = [concept("A", variants=[{"hook": "HO SBAGLIATO L'AGENDA."}, {"hook": "HO PRESO DUE MATRIMONI"}]),
          concept("B", template="ritratto", lever="claim", hook="IL CODICE NON BASTAVA")]
    wd = workdir(concepts=cs)
    sidecar(wd, "A_duo_v1")
    sidecar(wd, "B_ritratto", template="ritratto", grade="natural", people=1, accent="accent")
    sidecar(wd, "A_duo_v1", out_dir="sketch")
    (wd / "thumbs" / "qa").mkdir(parents=True)
    (wd / "thumbs" / "qa" / "A_duo_v1_qa.json").write_text(json.dumps(
        {"file": str(wd / "thumbs/renders/A_duo_v1.png"), "pass": False, "errors": ["face_size"], "warnings": [],
         "checks": [{"id": "face_size", "level": "error", "value": 0.33}], "metrics": {"colorfulness_360": 12.0}}))
    (wd / "thumbs" / "cold").mkdir(parents=True)
    (wd / "thumbs" / "cold" / "cold_reads.json").write_text(json.dumps([{"id": "A", "score": 2, "read": "una fotografa…"},
                                                                       {"id": "B", "score": 1, "read": "un founder…"}]))
    r1 = tl.ingest_workdir(conn, wd)
    n1 = conn.execute("SELECT COUNT(*) FROM thumb_records").fetchone()[0]
    r2 = tl.ingest_workdir(conn, wd)
    n2 = conn.execute("SELECT COUNT(*) FROM thumb_records").fetchone()[0]
    assert r1["channel"] == "tst" and r1["concepts"] == 3 and r1["renders"] == 2 and r1["sketches"] == 1 and r1["qa"] == 1
    assert n1 == n2 == 3, (n1, n2)                                  # A_v1, A_v2, B (lo sketch di A_v1 non duplica)
    a1 = dict(conn.execute("SELECT * FROM thumb_records WHERE version='A_duo_v1'").fetchone())
    assert a1["stage"] == "render" and a1["qa_pass"] == 0 and a1["qa_errors"] == 1 and a1["cold_score"] == 2
    f = json.loads(a1["features_json"])
    assert f["face_pct"] == "40-45" and f["template"] == "duo" and f["accent"] == "accent" and f["expression"] == "intenso"
    assert json.loads(a1["metrics_json"])["qa"]["levels"]["face_size"] == "error"
    a2 = dict(conn.execute("SELECT * FROM thumb_records WHERE version='A_duo_v2'").fetchone())
    assert a2["stage"] == "concept" and a2["hook"] == "HO PRESO DUE MATRIMONI"


# ── Scelte, prior e segnali ─────────────────────────────────────────────────
def test_choice_pairwise_moves_scelte_slowly_and_delegated_has_no_weight():
    conn = db()
    wd = g2_job(conn, "tst", "ritratto", ["duo", "scena"])
    prefs = conn.execute("SELECT source, COUNT(*) FROM thumb_prefs GROUP BY source").fetchall()
    assert dict((r[0], r[1]) for r in prefs) == {"g2": 2}
    pri = tl.compute_priors(conn, "tst", {})
    rit, duo = pri[("scelte", "template", "ritratto")], pri[("scelte", "template", "duo")]
    assert rit["mean"] > 0.5 > duo["mean"] and rit["n_jobs"] == 1 and rit["confidence"] == "bassa"
    assert rit["mean"] - 0.5 < 0.2                                     # una sola scelta muove poco (prior di 4 pseudo-osservazioni)
    assert pri[("esiti", "template", "ritratto")]["mean"] == 0.5    # due segnali mai mescolati
    assert rit["elo"] > 1500 > duo["elo"] and rit["elo"] - 1500 <= 16 * 2
    rec = dict(conn.execute("SELECT chosen, stage, choice_reason FROM thumb_records WHERE version='A_ritratto'").fetchone())
    assert rec == {"chosen": 1, "stage": "final", "choice_reason": "mi piace di più"}
    # delegato: preferenze registrate, nessun peso nelle scelte
    conn2 = db()
    g2_job(conn2, "tst", "ritratto", ["duo"], delegated=True)
    p2 = tl.compute_priors(conn2, "tst", {})
    assert conn2.execute("SELECT COUNT(*) FROM thumb_prefs WHERE source='delegated'").fetchone()[0] == 1
    assert abs(p2[("scelte", "template", "ritratto")]["mean"] - 0.5) < 1e-9 and p2[("scelte", "template", "ritratto")]["n_jobs"] == 0
    # idempotente: la stessa scelta registrata due volte non raddoppia l'evidenza
    tl.record_choice(conn, wd, ["A_ritratto"], None, "mi piace di più")
    assert conn.execute("SELECT COUNT(*) FROM thumb_prefs").fetchone()[0] == 2


def test_one_video_counts_once_per_value():
    """Revisione avversaria (V): 1 render scelto contro 8 scartati dello stesso template = UNA preferenza per valore;
    due cartelle dello stesso episodio (video_key) = un lavoro; D+7 e D+28 dello stesso video non si sommano."""
    conn = db()
    tpls = ["duo"] + ["ritratto"] * 8
    wd = workdir("tst", concepts=[concept(chr(65 + i), template=t) for i, t in enumerate(tpls)])
    for i, t in enumerate(tpls):
        sidecar(wd, f"{chr(65 + i)}_{t}", template=t, grade="mono" if t == "duo" else "natural")
    tl.ingest_workdir(conn, wd, "tst", profile={})
    tl.record_choice(conn, wd, ["A_duo"], None, "questa")
    assert conn.execute("SELECT COUNT(*) FROM thumb_prefs").fetchone()[0] == 8
    pri = tl.compute_priors(conn, "tst", {})
    duo, rit = pri[("scelte", "template", "duo")], pri[("scelte", "template", "ritratto")]
    w = tl.settings()["pref_weight"]
    assert abs(duo["wins"] - w) < 1e-9 and abs(rit["losses"] - w) < 1e-9, (duo["wins"], rit["losses"])
    assert duo["mean"] - 0.5 <= 0.06 and duo["n_jobs"] == 1
    assert duo["elo"] - 1500 <= tl.settings()["elo_k"] + 1e-9
    # un secondo giro dello stesso episodio (stesso video_key) resta un solo lavoro per n
    for d in (wd,):
        pj = json.loads((d / "project.json").read_text())
        (d / "project.json").write_text(json.dumps({**pj, "video_key": "ep-x"}))
    tl.job_key.cache_clear()
    wd2 = workdir("tst", concepts=[concept("A", template="duo"), concept("B", template="scena")])
    pj = json.loads((wd2 / "project.json").read_text())
    (wd2 / "project.json").write_text(json.dumps({**pj, "video_key": "ep-x"}))
    sidecar(wd2, "A_duo", template="duo")
    sidecar(wd2, "B_scena", template="scena", grade="natural")
    tl.ingest_workdir(conn, wd2, "tst", profile={})
    tl.record_choice(conn, wd2, ["A_duo"], None, "ancora questa")
    pri = tl.compute_priors(conn, "tst", {})
    assert pri[("scelte", "template", "duo")]["n_jobs"] == 1, pri[("scelte", "template", "duo")]
    assert abs(pri[("scelte", "template", "duo")]["wins"] - w) < 1e-9
    # D+7 e D+28: vale solo la lettura più matura
    rid = conn.execute("SELECT id FROM thumb_records WHERE version='A_duo' AND workdir=?", (str(wd.resolve()),)).fetchone()[0]
    for ck, wt in (("d7", 0.25), ("d28", 0.5)):
        conn.execute("INSERT INTO thumb_outcomes(channel, video_id, checkpoint, metric, label, strength, weight, mixed, "
                     "record_ids, measured_at) VALUES ('tst','vidONE','" + ck + "','same_age_views','sopra','debole',?,0,?,?)",
                     (wt, json.dumps([rid]), "2026-10-01T00:00:00+00:00"))
    conn.commit()
    es = tl.compute_priors(conn, "tst", {})[("esiti", "template", "duo")]
    assert abs(es["wins"] - 0.5) < 1e-9, es["wins"]


def test_priors_respect_knowledge_defaults_and_confidence():
    conn = db()
    prof = {"thumbnails": {"default_template": "duo", "default_lever": "claim", "grade_default": {"duo": "mono", "others": "natural"},
                           "guest_style_default": "none"}}
    pri = tl.compute_priors(conn, "tst", prof)
    assert abs(pri[("scelte", "template", "duo")]["prior_mean"] - 0.6) < 1e-9       # default del knowledge: 0,5 + 0,1
    assert abs(pri[("scelte", "grade", "mono")]["prior_mean"] - 0.6) < 1e-9
    assert tl.confidence(3, 0.3) == "bassa" and tl.confidence(6, 0.35) == "media" and tl.confidence(16, 0.18) == "alta"
    assert tl.confidence(20, 0.1, "esiti", comparables=3) == "bassa"                     # esiti: < 4 video confrontabili


# ── Ranking dei concept ─────────────────────────────────────────────────────
def test_rank_two_exploit_one_explore_and_policy():
    conn = db()
    cs = [concept("A", template="duo"), concept("B", template="ritratto"), concept("C", template="scena"),
          concept("D", template="prova", lever="proof", hook="DA ZERO A 210 STUDI")]
    r = tl.rank_concepts(conn, "tst", cs, profile={}, seed=1)
    roles = [s["ruolo"] for s in r["selezionati"]]
    assert roles == ["sfruttamento", "sfruttamento", "esplorazione"], roles
    assert len({s["lever"] for s in r["selezionati"]}) >= 2                  # mai meno di 2 leve
    assert r["nota"] and "default" in r["nota"] and r["segnale"] == "scelte"
    assert all("[appreso: scelte, n=" in s["etichetta"] for s in r["selezionati"])
    # stesso seme → stessa scelta (riproducibile)
    assert [s["id"] for s in tl.rank_concepts(conn, "tst", cs, profile={}, seed=1)["selezionati"]] == [s["id"] for s in r["selezionati"]]
    # 3 lavori in cui l'operatore sceglie ritratto: confidenza bassa → la posteriore lo mostra, ma l'ordine di
    # sfruttamento resta quello del knowledge (13 §3.3, 07 §16)
    for _ in range(3):
        g2_job(conn, "tst", "ritratto", ["duo", "scena"])
    r_low = tl.rank_concepts(conn, "tst", cs, profile={}, seed=1)
    by_id = {s["id"]: s for s in r_low["selezionati"] + r_low["scartati"]}
    assert by_id["B"]["posteriore"]["scelte"] > by_id["A"]["posteriore"]["scelte"]
    assert by_id["B"]["punteggio"]["scelte"] == by_id["A"]["punteggio"]["scelte"], "n=3: l'ordine non cambia"
    # 7 lavori concordi (un video pesa una volta: confidenza «media» solo da qui) → B sale in testa
    for _ in range(4):
        g2_job(conn, "tst", "ritratto", ["duo", "scena"])
    r2 = tl.rank_concepts(conn, "tst", cs, profile={}, seed=1)
    assert r2["selezionati"][0]["id"] == "B", r2["selezionati"]
    assert r2["selezionati"][0]["motivo"] == "media a posteriori più alta"
    ev = [e for e in r2["selezionati"][0]["evidenze"] if e["caratteristica"] == "thumbnail.template"]
    assert ev and ev[0]["n"] == 7 and ev[0]["media"] > 0.6 and ev[0]["confidenza"] == "media", ev
    # fuori regola (profilo che ammette solo guest_style none): escluso, non corretto
    prof = {"thumbnails": {"guest_style_allowed": ["none"]}}
    r3 = tl.rank_concepts(conn, "tst", cs + [concept("E", guest_style="graphic")], profile=prof, seed=2)
    assert [e["id"] for e in r3["esclusi"]] == ["E"] and "E" not in [s["id"] for s in r3["selezionati"]]


def test_rank_min_levers_swaps_in_another_lever():
    conn = db()
    cs = [concept("A", template="duo"), concept("B", template="duo", hook="NON BASTAVA IL CODICE"),
          concept("C", template="duo", hook="HO VENDUTO L'AZIENDA"), concept("D", template="prova", lever="proof",
                                                                                hook="DA ZERO A 210 STUDI")]
    for _ in range(4):                                                           # il duo piace: D (prova) ha la media più bassa
        g2_job(conn, "tst", "duo", ["prova"])
    for seed in range(8):
        r = tl.rank_concepts(conn, "tst", cs, profile={}, seed=seed)
        levers = {s["lever"] for s in r["selezionati"]}
        assert levers == {"claim", "proof"}, (seed, r["selezionati"])


# ── Pubblicazione, golden set, esiti ────────────────────────────────────────
def test_publish_golden_and_tier0_outcome_and_postmortem():
    conn = db()
    wd = g2_job(conn, "tst", "duo", ["ritratto"], reason="volti più grandi")
    for i, pub in enumerate(["2026-07-01", "2026-07-15", "2026-08-01", "2026-08-15"]):
        video(conn, "tst", f"base{i}", pub + "T10:00:00+00:00", {7: 100 + 10 * i, 120: 300})
    video(conn, "tst", "vidNEW", "2026-10-01T10:00:00+00:00", {7: 400})
    out = tl.record_publish(conn, wd, "vidNEW", "A_duo")
    assert out["published_at"].startswith("2026-10-01") and len(out["golden"]) == 1
    g = Path(out["golden"][0])
    assert (g / "thumbnail.png").exists() and (g / "render.json").exists() and (g / "manifest.json").exists()
    gc = json.loads((g / "concept.json").read_text())[0]
    assert gc["id"] == "A" and all(p["cutout"].startswith("assets/") and (g / p["cutout"]).exists() for p in gc["people"])
    assert str(g).startswith(str(tl.GOLDEN_DIR)) and str(tl.GOLDEN_DIR).startswith(str(ROOT_TMP))
    rep = tl.pull_outcomes(conn, "tst", today="2026-10-09")
    ck = {(p["checkpoint"]): p for p in rep["pulled"]}
    assert set(ck) == {"t48", "d7"}, ck                                   # d28 non ancora
    d7 = {r["metric"]: r for r in ck["d7"]["results"]}
    assert d7["same_age_views"]["label"] == "sopra" and d7["same_age_views"]["n"] == 4 and d7["same_age_views"]["value"] == 400
    assert d7["ctr"]["label"] == "non_leggibile"
    row = dict(conn.execute("SELECT weight, strength FROM thumb_outcomes WHERE video_id='vidNEW' AND checkpoint='d7' "
                            "AND metric='same_age_views'").fetchone())
    assert row == {"weight": tl.settings()["outcome_weight_d7"], "strength": "debole"}
    assert conn.execute("SELECT weight FROM thumb_outcomes WHERE checkpoint='t48' AND metric='same_age_views'").fetchone()[0] == 0
    pri = tl.compute_priors(conn, "tst", {})
    assert pri[("esiti", "template", "duo")]["mean"] > 0.5 and pri[("esiti", "template", "duo")]["confidence"] == "bassa"
    # una seconda lettura non duplica (checkpoint fatto)
    rep2 = tl.pull_outcomes(conn, "tst", today="2026-10-10")
    assert not [p for p in rep2["pulled"] if p["checkpoint"] in ("t48", "d7")]
    pm = tl.postmortem(conn, "vidNEW", out=tmpdir("pm") / "pm.md")
    md = pm["markdown"]
    assert pm["checkpoint"] == "d7" and "debole (Tier 0)" in md and "volti più grandi" in md and "calcolati da noi" in md
    assert "B_ritratto" in md and Path(pm["path"]).exists()
    assert conn.execute("SELECT postmortem_at FROM thumb_checkpoints WHERE video_id='vidNEW' AND checkpoint='d7'").fetchone()[0]


def test_tier0_not_readable_without_same_age_snapshots():
    conn = db()
    wd = g2_job(conn, "tst", "duo", ["ritratto"])
    for i in range(4):
        video(conn, "tst", f"old{i}", f"2026-0{i + 3}-01T10:00:00+00:00", {150: 500})   # solo istantanee a 150+ giorni
    video(conn, "tst", "v2", "2026-10-01T10:00:00+00:00", {7: 90})
    tl.record_publish(conn, wd, "v2", "A_duo", golden=False)
    rep = tl.pull_outcomes(conn, "tst", today="2026-10-08")
    d7 = [p for p in rep["pulled"] if p["checkpoint"] == "d7"][0]
    assert d7["status"] == "insufficient" and all(r["label"] == "non_leggibile" for r in d7["results"])
    assert "confronto" in [r for r in d7["results"] if r["metric"] == "same_age_views"][0]["reason"]
    # mai pari età inventata: nessun peso nei prior
    assert conn.execute("SELECT COUNT(*) FROM thumb_outcomes WHERE weight>0").fetchone()[0] == 0


def test_ctr_outcome_tier2_beats_views():
    conn = db()
    wd = g2_job(conn, "tst", "duo", ["ritratto"])
    pubs = ["2026-07-01", "2026-07-15", "2026-08-01", "2026-08-15"]
    for i, pub in enumerate(pubs):
        video(conn, "tst", f"b{i}", pub + "T10:00:00+00:00", {7: 100})
    video(conn, "tst", "vC", "2026-10-01T10:00:00+00:00", {7: 100})

    def reach(vid, pub, impr, ctr):
        d0 = dt.date.fromisoformat(pub)
        for k in range(7):
            conn.execute("INSERT INTO reach_daily(date, channel_id, video_id, report_type, traffic_source, device_type, impressions, ctr, "
                         "loaded_at) VALUES (?,?,?,?,?,?,?,?,?)", ((d0 + dt.timedelta(days=k)).isoformat(), "UCtst", vid,
                                                                   "channel_reach_basic_a1", "BROWSE", "", impr // 7, ctr, "x"))
    for i, pub in enumerate(pubs):
        reach(f"b{i}", pub, 1400, 0.04)
    reach("vC", "2026-10-01", 2100, 0.08)
    conn.commit()
    tl.record_publish(conn, wd, "vC", "A_duo", golden=False)
    rep = tl.pull_outcomes(conn, "tst", today="2026-10-09")
    d7 = {r["metric"]: r for r in [p for p in rep["pulled"] if p["checkpoint"] == "d7"][0]["results"]}
    assert d7["ctr"]["label"] == "sopra" and d7["ctr"]["n"] == 4 and abs(d7["ctr"]["value"] - 0.08) < 1e-6
    w = dict(conn.execute("SELECT metric, weight FROM thumb_outcomes WHERE video_id='vC' AND checkpoint='d7'").fetchall())
    assert w == {"ctr": tl.settings()["outcome_weight_d7"], "same_age_views": 0.0}, w                   # il CTR è la metrica della thumbnail; le views solo contesto


def test_mixed_arms_only_shared_features_learn():
    conn = db()
    wd = workdir(concepts=[concept("A"), concept("B")])
    sidecar(wd, "A_duo", accent="accent")
    sidecar(wd, "B_duo", accent="accent_2")
    tl.ingest_workdir(conn, wd, profile={})
    for i in range(4):
        video(conn, "tst", f"m{i}", f"2026-0{i + 5}-01T10:00:00+00:00", {7: 100})
    video(conn, "tst", "vAB", "2026-10-01T10:00:00+00:00", {7: 500})
    tl.record_publish(conn, wd, "vAB", {"A": "A_duo", "B": "B_duo"}, golden=False)
    tl.pull_outcomes(conn, "tst", today="2026-10-09")
    pri = tl.compute_priors(conn, "tst", {})
    assert pri[("esiti", "template", "duo")]["mean"] > 0.5             # in comune: impara
    assert pri[("esiti", "accent", "accent")]["mean"] == 0.5 and pri[("esiti", "accent", "accent_2")]["mean"] == 0.5   # diversi: no
    assert conn.execute("SELECT mixed FROM thumb_outcomes WHERE video_id='vAB' AND checkpoint='d7' LIMIT 1").fetchone()[0] == 1


def test_ab_and_pretest_sync_decisive_and_ties():
    conn = db()
    wd = workdir(concepts=[concept("A"), concept("B", template="ritratto")])
    sidecar(wd, "A_duo")
    sidecar(wd, "B_ritratto", template="ritratto", grade="natural", people=1)
    tl.ingest_workdir(conn, wd, profile={})
    tl.record_publish(conn, wd, "vX", {"A": "A_duo", "B": "B_ritratto"}, published_at="2026-10-01T10:00:00+00:00", golden=False)
    variants = json.dumps([{"id": "A", "file": str(wd / "thumbs/renders/A_duo.png")},
                           {"id": "B", "file": str(wd / "thumbs/renders/B_ritratto.png")}])
    conn.execute("INSERT INTO ab_tests(channel, video_id, kind, variants_json, started_at, ended_at, winner, created_at) "
                 "VALUES ('tst','vX','thumbnail',?, '2026-10-01','2026-10-15','B','x')", (variants,))
    conn.execute("INSERT INTO ab_tests(channel, video_id, kind, variants_json, started_at, ended_at, winner, created_at) "
                 "VALUES ('tst','vX','pretest',?, '2026-09-20','2026-09-21','pari','x')", (variants,))
    conn.commit()
    rep = tl.sync_tests(conn, "tst")
    assert rep["decisive"] == 1 and rep["ties"] == 1 and not rep["unmapped"], rep
    src = dict(conn.execute("SELECT source, COUNT(*) FROM thumb_prefs GROUP BY source").fetchall())
    assert src == {"ab": 1, "pretest_tie": 1}, src
    pri = tl.compute_priors(conn, "tst", {})
    rit = pri[("esiti", "template", "ritratto")]
    assert rit["mean"] > 0.5 and rit["n_decisive"] == 1 and pri[("esiti", "template", "duo")]["mean"] < 0.5
    assert pri[("scelte", "template", "ritratto")]["mean"] == 0.5     # un A/B è un esito, mai una scelta
    assert tl.sync_tests(conn, "tst")["prefs_added"] == 0                # idempotente


def test_due_view_lists_outcome_and_postmortem_tasks():
    conn = db()
    wd = g2_job(conn, "tst", "duo", ["ritratto"])
    pub = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat(timespec="seconds")
    tl.record_publish(conn, wd, "vDue", "A_duo", published_at=pub, golden=False)
    tasks = {(r["task"], r["checkpoint"]) for r in tl.due(conn, "tst")}
    assert tasks == {("outcome", "t48"), ("outcome", "d7")}, tasks
    with conn:
        conn.execute("INSERT INTO thumb_checkpoints(channel, video_id, checkpoint, status, attempts, last_attempt) VALUES "
                     "('tst','vDue','d7','done',1,date('now'))")
    tasks = {(r["task"], r["checkpoint"]) for r in tl.due(conn, "tst")}
    assert ("postmortem", "d7") in tasks and ("outcome", "d7") not in tasks
    n = dict(conn.execute(tl.DUE_SQL).fetchall())                       # la query del suggerimento di SessionStart
    assert n.get("outcome") == 1 and n.get("postmortem") == 1


# ── Golden set: regressione visiva (solo avvisi) ────────────────────────────
def test_golden_check_reports_drift_and_never_raises():
    conn = db()
    wd = g2_job(conn, "tst", "duo", ["ritratto"])
    tl.record_publish(conn, wd, "vG", "A_duo", published_at="2026-10-01T10:00:00+00:00")
    gold = tl.golden_entries("tst", "vG")
    assert len(gold) == 1

    def same(cf: Path, od: Path) -> Path:
        g = cf.parent
        p = od / "A_duo.png"
        p.write_bytes((g / "thumbnail.png").read_bytes())
        (od / "A_duo.render.json").write_text((g / "render.json").read_text())
        return p

    def drifted(cf: Path, od: Path) -> Path:
        g = cf.parent
        p = png(od / "A_duo.png", rgb=(90, 90, 90), size=(384, 216), box=(0, 0, 200, 216))
        sd = json.loads((g / "render.json").read_text())
        sd["checks_v2"]["heroes"][0]["face_frac"] = 0.36
        sd["checks_v2"]["accents"] = ["accent_2"]
        (od / "A_duo.render.json").write_text(json.dumps(sd))
        return p

    def broken(cf: Path, od: Path) -> Path:
        raise RuntimeError("Playwright assente")

    r0 = tl.golden_check("tst", "vG", out=tmpdir("g0"), render_fn=same)
    assert r0["checked"] == 1 and not r0["warnings"] and r0["drift"][0]["pixels"]["mean"] == 0
    r1 = tl.golden_check("tst", "vG", out=tmpdir("g1"), render_fn=drifted)
    msgs = " | ".join(r1["warnings"])
    assert "deriva visiva" in msgs and "guest_face_pct" in msgs and "accent" in msgs, msgs
    r2 = tl.golden_check("tst", "vG", out=tmpdir("g2"), render_fn=broken)
    assert r2["checked"] == 0 and "re-render fallito" in r2["warnings"][0]
    assert tl.image_drift(Path(gold[0]["dir"]) / "thumbnail.png", Path(gold[0]["dir"]) / "thumbnail.png")["share_gt24"] == 0


# ── Riferimenti di nicchia ──────────────────────────────────────────────────
def _peers(conn, channel="tst", today=dt.date(2026, 10, 13)):
    tl.peers_file(channel).write_text("# confermati dall'operatore 2026-10-01\n@peerone  it\nhttps://www.youtube.com/@peertwo\n")
    now = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc).isoformat()
    for cid, h in (("UCp1", "@peerone"), ("UCp2", "@peertwo")):
        conn.execute("INSERT INTO peers(channel_id, input, handle, fetched_at) VALUES (?,?,?,?)", (cid, h, h, now))
        for k in range(6):
            views = 1000 * (10 if k == 0 else (5 if k == 1 else (3 if k == 2 else 1)))
            conn.execute("INSERT INTO peer_videos(video_id, channel_id, title, published_at, format, views, fetched_at) "
                         "VALUES (?,?,?,?,?,?,?)", (f"{cid}v{k}", cid, f"t{k}", (today - dt.timedelta(days=20 + k)).isoformat(),
                                                    "long", views, now))
        conn.execute("INSERT INTO peer_videos(video_id, channel_id, title, published_at, format, views, fetched_at) VALUES "
                     "(?,?,?,?,?,?,?)", (f"{cid}new", cid, "nuovo", (today - dt.timedelta(days=3)).isoformat(), "long", 99999, now))
    conn.commit()


def test_refs_plan_refresh_status_and_qa_grid_auto():
    conn = db()
    _peers(conn)
    plan = tl.refs_plan(conn, "tst", max_n=8, today="2026-10-13")
    ids = [i["video_id"] for i in plan["items"]]
    assert len(ids) == 4 and all(i.endswith(("v0", "v1")) for i in ids), ids    # ≤ 2 per canale, i più sopra la mediana
    assert not any(i.endswith("new") for i in ids)                              # < 14 giorni: escluso

    def fake_fetch(vids, raw):
        out = []
        for v in vids:
            out.append(png(raw / v / f"{v}.jpg", rgb=(200, 60, 60)))
            (raw / v / f"{v}.meta.json").write_text("{}")
        return out

    rep = tl.refs_refresh(conn, "tst", max_n=8, fetch=fake_fetch, today="2026-10-13")
    grid = Path(rep["grid"])
    assert rep["copied"] == 4 and len(list(grid.glob("*.jpg"))) == 4 and not (grid.parent / "_raw").exists()
    assert str(grid).startswith(str(ROOT_TMP))
    gdir, msg = tl.refs_grid("tst")
    assert gdir == grid and msg is None
    assert conn.execute("SELECT n FROM thumb_refs_runs WHERE channel='tst'").fetchone()[0] == 4
    if tl._has_table(conn, "learn_refs"):                                       # stesso elenco in yt-learn (purge a 30 gg)
        assert rep.get("yt_learn_refs") == 4, rep.get("warnings")
        assert conn.execute("SELECT COUNT(*) FROM learn_refs WHERE channel='tst'").fetchone()[0] == 4
    # yt-thumb-qa --grid auto: griglia dai riferimenti + <stem>_qa.json
    img = png(tmpdir("qaimg") / "cand.png", rgb=(30, 30, 30), size=(1280, 720), box=(500, 200, 800, 520))
    qa_out = tmpdir("qaout")
    env = {**os.environ, "YT_STUDIO": os.environ["YT_STUDIO"]}
    proc = subprocess.run([sys.executable, str(LIB / "thumb_qa.py"), str(img), "--out", str(qa_out), "--grid", "auto",
                           "--channel", "tst", "--no-vision", "--no-landmarks"], capture_output=True, text=True, env=env)
    res = json.loads(proc.stdout)
    assert res["ok"] and (qa_out / "cand_qa.json").exists() and (qa_out / "cand_grid.png").exists(), (proc.stderr[-800:], res)
    qj = json.loads((qa_out / "cand_qa.json").read_text())
    assert qj["tool"] == "yt-thumb-qa" and "checks" in qj and qj["file"].endswith("cand.png")
    # riferimenti scaduti (> 30 gg): non usati, avviso, nessun errore
    man = grid.parent / "refs.json"
    d = json.loads(man.read_text())
    d["refreshed_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=40)).isoformat()
    man.write_text(json.dumps(d))
    gdir, msg = tl.refs_grid("tst")
    assert gdir is None and "30" in msg
    proc = subprocess.run([sys.executable, str(LIB / "thumb_qa.py"), str(img), "--out", str(tmpdir("qaout2")), "--grid", "auto",
                           "--channel", "tst", "--no-vision", "--no-landmarks"], capture_output=True, text=True, env=env)
    res = json.loads(proc.stdout)
    assert res["ok"] and any("griglia saltata" in w for w in res["warnings"]), res["warnings"]
    assert tl.refs_purge(30)["removed"] == ["tst"] and not grid.exists()


def test_refs_plan_without_peers_says_what_to_do():
    conn = db()
    r = tl.refs_plan(conn, "nopeers")
    assert not r["items"] and "peer" in r["warnings"][0]


# ── Proposte Tier B ─────────────────────────────────────────────────────────
def test_proposals_eligibility_privacy_and_hard_rules():
    conn = db()
    for _ in range(3):                                   # canale demo: l'operatore sceglie ritratto contro duo in 3 lavori
        g2_job(conn, "demo", "ritratto", ["duo", "scena"], reason="Ospite Finto ha un sorriso migliore qui")
    res = tl.proposal_candidates(conn, "demo")
    assert res["eligible"]
    # i default del profilo non vanno mai in PR: suggerimento locale con la sostituzione esatta nel profilo dell'operatore
    assert not [p for p in res["proposals"] if p["kind"] == "profile"]
    prof = [p for p in res["profile_changes"] if p["change"]["yaml_key"] == "thumbnails.default_template"]
    assert prof and {k: prof[0]["change"][k] for k in ("yaml_key", "from", "to")} == \
        {"yaml_key": "thumbnails.default_template", "from": "duo", "to": "ritratto"}
    assert prof[0]["local"] is True and prof[0]["target"] == "demo.md" and prof[0]["evidence"]["n"] == 3
    ch = prof[0]["change"]
    assert ch["replace"] == "default_template: duo" and ch["with"] == "default_template: ritratto", ch   # cambio esatto
    yl = prof[0]["yt_learn"]
    assert yl["lesson_add"][:3] == ["yt-learn", "lesson", "add"] and "propose" not in yl     # solo Tier A
    if tl._has_table(conn, "learn_events"):
        assert yl["evidence_events"] == [] or all(e.startswith("e") for e in yl["evidence_events"])
    blob = json.dumps(res, ensure_ascii=False)
    for secret in ("Ospite Finto", "sorriso migliore", "SBAGLIATO", "/Users/", str(ROOT_TMP)):
        assert secret not in blob, secret                 # niente nomi, motivi, ganci, percorsi (13 §9.2)
    # niente lezioni confuse col template: «grade natural» o «persone solo» vincono solo perché vince ritratto
    assert not [p for p in res["proposals"] + res["profile_changes"]
                if p["id"].split("-")[3] in ("grade", "people", "plate", "rows_pct")], \
        [p["id"] for p in res["proposals"] + res["profile_changes"]]
    # un canale senza profilo e fuori da learning_pr_channels: nessuna proposta, le lezioni restano locali
    conn2 = db()
    for _ in range(3):
        g2_job(conn2, "cliente", "ritratto", ["duo"])
    r2 = tl.proposal_candidates(conn2, "cliente")
    assert not r2["eligible"] and not r2["proposals"] and not r2["profile_changes"] and "locali" in r2["note"]
    # un canale proprio ma non condiviso (niente share_lessons): nessuna PR, ma il suggerimento locale per il profilo sì
    conn3 = db()
    for _ in range(3):
        g2_job(conn3, "esempio", "ritratto", ["duo", "scena"])
    r3 = tl.proposal_candidates(conn3, "esempio")
    assert not r3["eligible"] and not r3["proposals"] and "share_lessons" in r3["note"], r3.get("note")
    assert [p for p in r3["profile_changes"] if p["change"].get("with") == "default_template: ritratto"], r3["profile_changes"]
    # la stessa regola di yt-learn: elencato ma senza consenso nel profilo, oppure consenso senza elenco → locale
    assert tl.channel_shareable("demo") and not tl.channel_shareable("esempio")
    assert not tl.channel_shareable("demo", {"pr_channels": []}) and not tl.channel_shareable("esempio", {"pr_channels": ["esempio"]})


def test_proposals_threshold_only_tightens_and_graphic_refused():
    conn = db()
    for i in range(3):                                   # volti al 35–40 % scartati 3 volte contro volti al 45 %
        wd = workdir("demo", concepts=[concept("A", template="ritratto"), concept("B", template="ritratto")])
        sidecar(wd, "A_ritratto", template="ritratto", grade="natural", guest=0.46, people=1)
        sidecar(wd, "B_ritratto", template="ritratto", grade="natural", guest=0.37, people=1)
        tl.ingest_workdir(conn, wd, "demo")
        tl.record_choice(conn, wd, ["A_ritratto"], ["B_ritratto"], "volto troppo piccolo")
    res = tl.proposal_candidates(conn, "demo")
    th = [p for p in res["proposals"] if p["kind"] == "threshold"]
    assert th and th[0]["change"]["to"] > th[0]["change"]["from"] and "stringe H8" in th[0]["hard_rules"], th
    kn = [p for p in res["proposals"] if p["kind"] == "knowledge"]
    assert kn, [p["id"] for p in res["proposals"]]                         # volto 45+ preferito a parità di template
    doc = (HERE.parent.parent.parent / "docs/yt/knowledge/07-thumbnails.md").read_text()
    assert doc.count(tl.TABLE_HEAD_07) == 1                                  # sostituzione esatta, una sola occorrenza
    new = doc.replace(kn[0]["change"]["replace"], kn[0]["change"]["with"])
    i = new.index(tl.TABLE_HEAD_07)
    assert new[i:].split("\n")[2] == kn[0]["change"]["append_row"]          # la riga entra nella tabella, subito sotto
    assert kn[0]["yt_learn"]["propose"]["replace"] == tl.TABLE_HEAD_07
    ts = th[0]["yt_learn"]["threshold_set"]
    assert ts[:3] == ["yt-learn", "threshold", "set"] and ts[ts.index("--name") + 1] == "face_size" and float(ts[ts.index("--min") + 1]) == 0.40
    l1 = _l1()
    if l1 and tl._has_table(conn, "learn_thresholds"):      # il comando proposto è accettato da yt-learn (più severo: ok)
        r = l1.threshold_set(conn, channel="demo", name="face_size", direction=None, value=0.40, level="error")
        assert r["value"] == 0.40
    # guest_style graphic preferito: mai una proposta di default (H1)
    conn2 = db()
    for i in range(3):
        wd = workdir("demo", concepts=[concept("A", template="ritratto"), concept("B", template="ritratto")])
        sa = sidecar(wd, "A_ritratto", template="ritratto", grade="natural", people=1)
        sd = json.loads(sa.read_text())
        sd["spec"]["guest_style"] = "graphic"
        sa.write_text(json.dumps(sd))
        sidecar(wd, "B_ritratto", template="ritratto", grade="natural", people=1)
        tl.ingest_workdir(conn2, wd, "demo")
        tl.record_choice(conn2, wd, ["A_ritratto"], ["B_ritratto"])
    r2 = tl.proposal_candidates(conn2, "demo")
    assert not [p for p in r2["proposals"] if "guest_style" in p["id"]]
    assert [p for p in r2["refused"] if "H1" in p["reason"]]


def test_learn_workdir_and_playbook_section():
    conn = db()
    wd = g2_job(conn, "tst", "duo", ["ritratto"])
    r = tl.learn_workdir(conn, wd)
    assert r["channel"] == "tst" and r["priors"] > 0 and "### Thumbnail" in r["playbook_section"]
    assert "guest_style graphic mai di default" in r["playbook_section"] and "[appreso: scelte]" in r["playbook_section"]


# ── Integrazione con yt-learn (decisioni, pubblicazioni, verdetti) ─────────
def _l1():
    try:
        import learn
        return learn
    except Exception:  # noqa: BLE001
        return None


def test_sync_from_learn_imports_g2_decision_and_publication():
    l1 = _l1()
    conn = db()
    if not l1 or not tl._has_table(conn, "learn_events"):
        print("    yt-learn assente: test saltato")
        return
    wd = workdir(concepts=[concept("A"), concept("B", template="ritratto")])
    sidecar(wd, "A_duo")
    sidecar(wd, "B_ritratto", template="ritratto", grade="natural", people=1)
    tl.ingest_workdir(conn, wd, profile={})
    # il dispatcher registra la decisione una volta sola, con yt-learn
    l1.record_decision(conn, channel="tst", workdir=wd, gate="G2", skill="thumbnail", offered=["A_duo", "B_ritratto"],
                       chosen=["A_duo"], rejected=[], reason="il duo si legge meglio", text="Va bene A, il duo si legge meglio",
                       operator="Giulia", delegated=False)
    r = tl.sync_from_learn(conn, "tst", wd)
    assert r["available"] and r["decisions"] == 1 and r["prefs_added"] == 1, r
    p = dict(conn.execute("SELECT source, reason, operator FROM thumb_prefs").fetchone())
    assert p == {"source": "g2", "reason": "il duo si legge meglio", "operator": "Giulia"}
    assert tl.sync_from_learn(conn, "tst", wd)["prefs_added"] == 0                     # idempotente
    # delegata: registrata con peso 0
    l1.record_decision(conn, channel="tst", workdir=wd, gate="G2", skill="thumbnail", offered=[], chosen=["B_ritratto"],
                       rejected=["A_duo"], reason=None, text="G2 delegato", operator=None, delegated=True)
    tl.sync_from_learn(conn, "tst", wd)
    assert conn.execute("SELECT COUNT(*) FROM thumb_prefs WHERE source='delegated'").fetchone()[0] == 1
    # pubblicazione registrata con yt-learn (un solo punto): record pubblicato + golden set ricco (concept ri-renderizzabile)
    # scritti subito da yt-thumb-learn; la sync successiva non ha più niente da importare
    pub = l1.publish(conn, channel="tst", video_id="vidL1abc", workdir=wd, arms={"A": "A_duo"},
                     published_at="2026-10-01T10:00:00+00:00")
    assert pub["golden"] and not pub["warnings"], pub
    rec = dict(conn.execute("SELECT published, video_id, ab_arm, golden_dir FROM thumb_records WHERE version='A_duo'").fetchone())
    assert rec["published"] == 1 and rec["video_id"] == "vidL1abc" and rec["ab_arm"] == "A" and Path(rec["golden_dir"]).is_dir()
    assert tl.sync_from_learn(conn, "tst")["publications"] == 0
    # pubblicazione rimasta solo in learn_publications (es. registrata prima dell'integrazione): la sync la importa
    conn.execute("UPDATE thumb_records SET published=0, video_id=NULL WHERE version='A_duo'")
    conn.commit()
    assert tl.sync_from_learn(conn, "tst")["publications"] == 1


def test_outcomes_reuse_yt_learn_verdict():
    l1 = _l1()
    conn = db()
    if not l1 or not tl._has_table(conn, "learn_outcomes"):
        print("    yt-learn assente: test saltato")
        return
    wd = g2_job(conn, "tst", "duo", ["ritratto"])
    video(conn, "tst", "vidV1xx", "2026-10-01T10:00:00+00:00", {7: 50})
    tl.record_publish(conn, wd, "vidV1xx", "A_duo", golden=False)
    now = "2026-10-09T00:00:00+00:00"
    conn.execute("INSERT INTO learn_outcomes(channel, video_id, checkpoint, tier, source, metric, value, baseline, ratio, n_baseline, "
                 "verdict, created_at, updated_at) VALUES ('tst','vidV1xx','d7',0,'pull','views_at_7d',50,100,0.5,4,'sotto',?,?)", (now, now))
    conn.commit()
    rep = tl.pull_outcomes(conn, "tst", today="2026-10-09")
    d7 = {r["metric"]: r for r in [p for p in rep["pulled"] if p["checkpoint"] == "d7"][0]["results"]}
    assert d7["same_age_views"]["label"] == "sotto" and d7["same_age_views"]["n"] == 4      # stesso verdetto di yt-learn
    det = json.loads(conn.execute("SELECT details_json FROM thumb_outcomes WHERE video_id='vidV1xx' AND checkpoint='d7' "
                                  "AND metric='same_age_views'").fetchone()[0])
    assert det["source"] == "yt-learn"
    assert tl.compute_priors(conn, "tst", {})[("esiti", "template", "duo")]["mean"] < 0.5


# ── Ganci additivi in thumb_render ──────────────────────────────────────────
def test_thumb_render_learn_hooks_are_additive_and_safe():
    import thumb_render as tr
    wd = workdir()
    sd = json.loads(sidecar(wd, "A_duo").read_text())
    lf = tr.learn_features(sd)
    assert lf["features"]["template"] == "duo" and lf["metrics"]["guest_face_pct"] == 42.0
    assert "error" in tr.learn_features({"checks_v2": {"heroes": "non una lista"}}) or True   # mai un'eccezione
    out = tmpdir("idx")
    plans = [{"name": "A_duo", "sidecar": str(out / "A_duo.render.json")}]
    tr.write_render_index(out, plans, [{"id": "A", "name": "A_duo", "template": "duo", "ok": True, "pass": True, "features": lf}])
    tr.write_render_index(out, [{"name": "B_prova"}], [{"id": "B", "name": "B_prova", "template": "prova", "ok": True,
                                                            "pass": False, "errors": ["x"]}])
    idx = json.loads((out / "render.json").read_text())["renders"]
    assert set(idx) == {"A_duo", "B_prova"} and idx["A_duo"]["features"]["template"] == "duo"   # --only non cancella


def test_cli_end_to_end_json_contract():
    wd = workdir(concepts=[concept("A"), concept("B", template="ritratto")])
    sidecar(wd, "A_duo")
    sidecar(wd, "B_ritratto", template="ritratto", grade="natural", people=1)
    dbp = tmpdir("cli") / "yt.db"

    def run(*a):
        p = subprocess.run([sys.executable, str(LIB / "thumb_learn.py"), "--db", str(dbp), *a], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)

    code, r = run("ingest", str(wd))
    assert code == 0 and r["ok"] and r["renders"] == 2
    code, r = run("choice", str(wd), "--chosen", "A_duo", "--reason", "più leggibile")
    assert code == 0 and r["prefs_added"] == 1 and r["priors_moved"]
    code, r = run("rank", "--channel", "tst", "--data", str(wd / "thumbs/concepts.json"), "--seed", "3",
                  "--out", str(wd / "thumbs/learn/rank.json"))
    assert code == 0 and len(r["selezionati"]) == 2 and (wd / "thumbs/learn/rank.json").exists()
    code, r = run("choice", str(wd), "--chosen", "Z_inesistente")
    assert code == 1 and not r["ok"] and "sconosciuto" in r["error"]
    code, r = run("priors", "--channel", "tst", "--signal", "scelte")
    assert code == 0 and r["counts"]["scelte_g2"] == 1


def main() -> int:
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f) and flt in n]
    failed = 0
    t0 = time.time()
    for name, fn in tests:
        t1 = time.time()
        try:
            fn()
            print(f"ok    {name} ({time.time() - t1:.1f} s)")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} test passati in {time.time() - t0:.1f} s"
          + (f" (cartella temporanea lasciata per il debug: {ROOT_TMP})" if failed else ""))
    if not failed:
        import shutil
        shutil.rmtree(ROOT_TMP, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
