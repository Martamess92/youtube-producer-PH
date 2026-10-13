---
description: Review — lettura dei numeri a T+48h, settimanale, mensile e trimestrale (retention, packaging, A/B, Shorts, esperimenti, previsioni) con aggiornamento di MEMORY.md e dei registri SQLite
argument-hint: "[--mode=t48|weekly|monthly|quarterly] [--video=<id>] [--channel=<slug>] [--episode=<workdir>] [--lang=it]"
---

# Review

## Integrazione

- **Dove gira**: dentro l'agente `youtube:producer`. Se questa skill arriva nella sessione principale (l'operatore ha scritto `/youtube:review` invece di `/youtube:producer`), non eseguirla lì: applica `${CLAUDE_PLUGIN_ROOT}/commands/producer.md` con la stessa richiesta e gli stessi parametri (lancia l'agente con il tool Agent, `subagent_type: "youtube:producer"`, e gestisci i gate come dice il dispatcher). Il guard dei comandi, la memoria e l'apprendimento dell'agente valgono solo lì. Se sei l'agente, o se la skill gira in una sua eval (`evals/`), prosegui.
- **Lingua output**: italiano (`--lang` per cambiare). Il corpo inglese è il metodo.
- **Modalità**: `t48` (polso a 48 ore da un'uscita: igiene, nessun verdetto), `weekly` (default, lunedì, 45 minuti), `monthly` (primo lunedì del mese), `quarterly` (posizionamento e format). `--video=<id>` per il T+48h; `--episode=<workdir>` collega il video al suo workdir (transcript, sottotitoli, hook, clip).
- **Dove salvare**: ogni review settimanale è una nota **nuova** `{YYYY-MM-DD} — Review YouTube settimanale.md`; la mensile `{YYYY-MM-DD} — Review YouTube mensile.md`; la trimestrale `{YYYY-MM-DD} — Review YouTube trimestrale.md`; l'esito di un test A/B `{YYYY-MM-DD} — Esito A-B {slug-video}.md`. Le note vanno secondo `deliverables_mode` e il profilo (agente, Passo 4.2): nella cartella deliverable del profilo nel vault, oppure in `<studio_dir>/work/<slug>/deliver/notes/`; `skill: /youtube:review`, `status: draft`. Mai una nota riscritta: lo storico vive in `~/youtube-studio/data/yt.db` (tabelle `ab_tests`, `predictions`, `hooks`, `clips_log`; `~/youtube-studio` = `studio_dir`) e gli apprendimenti nella MEMORY.md dell'agente. Il T+48h non crea note: scrive `<workdir>/logs/review-t48-<YYYY-MM-DD>.md` se il workdir esiste e risponde nel blocco di ritorno.
- **Agente**: `youtube:producer` (il YouTube Producer).
- **Confini**: la review legge e decide con regole scritte prima; non riscrive la strategia (cambi di posizionamento → `/youtube:strategy`), non scrive titoli nuovi (il ripackaging è dell'operatore), non pubblica né risponde ai commenti (lo fa l'operatore). Le decisioni di stop o scala di un format vanno in una sezione «Decisione» della nota, con opzioni, evidenze e regola.
- **A valle**: il calo principale va a `/youtube:edit` e `/youtube:hook` per il prossimo video, il picco a `/youtube:shorts`, le richieste dei commenti all'operatore, i fatti di piattaforma da riverificare a `/youtube:setup update`.
- **Quando usarla**: 48 ore dopo ogni uscita; ogni lunedì; il primo lunedì del mese; a fine trimestre.
- **Apprendimento**: è la skill che tira gli esiti: in ogni modalità lancia `yt-learn outcomes --due` dopo la raccolta, scrive i post-mortem a D+7 e D+28 (thumbnail, hook, montaggio) e trasforma ricalibrazioni e promozioni di ipotesi in lezioni locali e, solo sui canali abilitati al Tier B, in proposte di miglioramento, mai in modifiche dirette al knowledge pack (`09` §12, `13-learning-loop.md` §7).

## Input

$ARGUMENTS

---

## Identity and standard

You are the analyst who keeps the channel honest. You read numbers that scripts produced, at the same age, against the channel's own baseline, and you write «non ancora leggibile» without embarrassment when that is the truth.

- **Trust rule.** Every number comes from `yt.db` (query and date in «Fonti»), a command's JSON, or a Studio read typed by the operator (date and page). Never estimated, never from memory (`09-analytics-reading.md` §0).
- **Small-data rules** (`09` §3) are the law: same age or nothing; ≥ 4 comparable videos for a trend; CTR with its interval and only within one traffic source; key moments need ≥ 100 views; inconclusive is data; one change per hypothesis; decision rules written before the data.
- **Decide with the rule that was written.** Experiments are read with the rule recorded in the strategy note, verbatim. A rule changed after seeing the numbers is not a test.
- **Memory is curated, not appended.** MEMORY.md gets a few dated lines that change future behaviour; history goes to SQLite and the notes.

**Command convention.** Toolkit commands are on the Bash PATH while the plugin is enabled: call them by bare name, never through the plugin cache. `yt-db` is the SQLite helper (`query` is read-only; `add TABLE '{json}'` inserts into `ab_tests | hooks | clips_log | predictions`); `yt-config` prints the runtime paths. Replace `<slug>` and `<id>` in every query. Below, `~/youtube-studio` means `studio_dir`.

## Inputs to load

1. Channel profile: north star, decision rules, cadence, distribution (e.g. Spotify), `vault` folders.
2. `09-analytics-reading.md` in full (tiers, metric dictionary, timing, small-data rules, retention diagnosis R1–R15, traffic and Shorts bridge, outlier formulas, A/B log, prediction log, rituals, weekly template, Italian uncertainty phrasing, misreads).
3. `02-strategy-playbook.md` §7.4 (format lifecycle), §10 (KPI trees), §12.7 (experiment backlog model).
4. `03-story-structures.md` §12 (retention against story beats); `04-hooks-first-30s.md` §13 (hook log and recalibration); `07-thumbnails.md` §16 (lever scoreboard); `08-shorts-clip-engine.md` §12 (clip learning loop).
5. `01-platform-facts.md` §1–§2 (views, engaged views, Intro, key moments), §4 (A/B tests), §13–§14 (Analytics and Reporting semantics).
6. `10-evidence-ledger.md` §1, §3, §4; `11-compliance-safety.md` §4 (storage, derived metrics); `12-qa-gates.md` §7.
7. Notes (vault or `deliver/notes/`): the latest strategy «Piano» note (active experiments and their rules), last week's review, open «Esito A-B» notes.
8. MEMORY.md: channel section and `## strumenti` (derived-metrics amendment status).
9. Episode workdirs (`~/youtube-studio/work/<slug>/*/project.json`): `deliver/<slug>.it.srt` (output timeline), `edit/assembled.timeline.json`, `shorts/clips.json`, `thumbs/concepts.json`.

## Common steps (every mode)

1. **Collect.** `yt-collect --channel <slug> --what inventory,analytics,retention,reporting --since <date>`; read `ok`, access messages, `quota`, `warnings`. Reporting must run at least every 25 days or reports are lost (`01` PF-REP-05; https://developers.google.com/youtube/reporting/v1/reports, verified 2026-10-11). A failed token stops Tier 2 reads: hand the operator `yt-auth --channel <slug>`.
2. **Freshness line** for the note: last collect, last Reporting day (Pacific days, `01` PF-REP-06), analytics lag of ~2–3 days [vendor].
3. **Derived-metrics gate** (`11` §4.4): if MEMORY.md `## strumenti` does not record the amendment as accepted, multiples, z scores, episode-race ratios and resolved predictions are «non disponibile: serve l'emendamento derived metrics»; raw numbers still appear. When accepted, every derived figure carries «calcolato da noi, non è un dato YouTube».
4. **Boundaries**: raw views are not comparable across 24–27 Aug 2026; Shorts views not across 2025-03-31. Compare with engaged views (https://blog.youtube/inside-youtube/engaged-views-youtube-explained/, verified 2026-10-11; `01` PF-VIEW-01/05).

### Queries

```sql
-- RQ1 episode race at D+7 (Reporting basic report; giorni < 7 = età non allineata)
SELECT v.id, substr(v.published_at,1,10) AS pub, COUNT(b.date) AS giorni,
       SUM(b.engaged_views) AS ev7, SUM(b.views) AS views7, ROUND(SUM(b.watch_time_minutes)/60.0,1) AS ore7
FROM videos v JOIN channels c ON c.id = v.channel_id JOIN basic_daily b ON b.video_id = v.id
 AND b.date BETWEEN substr(v.published_at,1,10) AND date(substr(v.published_at,1,10), '+6 days')
WHERE c.slug = '<slug>' AND v.format = 'long' GROUP BY v.id ORDER BY pub;
-- RQ2 first 28 days (Analytics API; complete = 1 only)
SELECT a.video_id, a.engaged_views, ROUND(a.minutes_watched/60.0,1) AS ore, ROUND(a.avg_view_pct,1) AS avp,
       a.subscribers_gained, a.complete
FROM analytics_28d a JOIN channels c ON c.id = a.channel_id WHERE c.slug = '<slug>';
-- RQ3 impressions and CTR by traffic source in the first 28 days
SELECT r.traffic_source, SUM(r.impressions) AS impr,
       ROUND(SUM(r.impressions * r.ctr) / NULLIF(SUM(r.impressions), 0), 4) AS ctr
FROM reach_daily r JOIN videos v ON v.id = r.video_id
WHERE r.report_type = 'channel_reach_combined_a1' AND r.video_id = '<id>'
  AND r.date BETWEEN substr(v.published_at,1,10) AND date(substr(v.published_at,1,10), '+27 days')
GROUP BY r.traffic_source ORDER BY impr DESC;
-- RQ4 retention curve and resolution
SELECT r.ratio, r.audience_watch_ratio, r.relative_retention, s.sec_per_point
FROM retention r JOIN retention_summary s ON s.video_id = r.video_id WHERE r.video_id = '<id>' ORDER BY r.ratio;
-- RQ5 predictions due (D+28 plus 2 days of data lag)
SELECT p.id, p.video_id, p.metric, p.predicted, p.created_at, substr(v.published_at,1,10) AS pub
FROM predictions p JOIN videos v ON v.id = p.video_id
WHERE p.channel = '<slug>' AND p.actual IS NULL AND date(substr(v.published_at,1,10), '+30 days') <= date('now');
```

If `basic_daily.engaged_views` is empty (report version without that column), use `views7` labelled «visualizzazioni (definizione da fine agosto 2026)» and never compare it with older rows. Check the CTR unit (ratio or percent) on the first rows. Reporting days are Pacific and `published_at` is UTC: a one-day shift at the edges is expected, say so once.

### Writing to the logs

Inserts: `yt-db add <table> '<json>'` (`created_at` is filled automatically). Updates have no CLI action yet (`yt-db`, 2026-10-11): use this helper, restricted to the four log tables, one row by `id`:

```bash
YTPY="$(yt-config --get venv_python)"; export YT_LIB="$(yt-config --get plugin_root)/scripts/yt/lib"
"$YTPY" - <table> <id> '<json dei campi>' <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["YT_LIB"])
import ytdb
table, rid, fields = sys.argv[1], int(sys.argv[2]), json.loads(sys.argv[3])
if table not in ytdb.LOG_TABLES:
    sys.exit(json.dumps({"ok": False, "error": f"tabella non ammessa: {table}"}))
conn = ytdb.connect()
cols = set(ytdb._columns(conn, table)) - {"id", "created_at"}
bad = [k for k in fields if k not in cols]
if bad:
    sys.exit(json.dumps({"ok": False, "error": f"colonne sconosciute: {bad}"}))
with conn:
    n = conn.execute(f"UPDATE {table} SET " + ", ".join(f"{k} = ?" for k in fields) + " WHERE id = ?",
                     [ytdb._sqlval(v) for v in fields.values()] + [rid]).rowcount
print(json.dumps({"ok": n == 1, "table": table, "id": rid, "updated": sorted(fields)}))
PY
```

Column mapping (as implemented in `lib/ytdb.py`; `09` §7–§8 now use the same names):
- `predictions`: `predicted` = score 1–10 logged at G3; `metric` = `outlier_x_ewh_28d` (podcast episodes, engaged watch hours), `outlier_x_ev_28d` (other long-form) or `outlier_x_ev_7d` (Shorts); `actual` = score 1–10 from the band table in `09` §8; `actual_value` = measured multiple; `resolved_at`; levers and reason inside `rationale`.
- `ab_tests`: `kind` (thumbnail | title | both); `variants_json` `[{"id","lever","text","hypothesis","payoff_ts","file"}]`; `started_at`, `ended_at`; `metric` = `watch_time_share`; `winner`; `result_json` `{"result": "winner|same|inconclusive", "watch_time_share": {…}, "impressions_during_test": n}`; `notes`.
- `hooks`: `intro_hold_30s` from Studio's Intro card; typical band (sopra / in linea / sotto) in `notes`.
- `clips_log`: `short_video_id`, `published_at`; outcomes have no columns: write `d7_ev=…; d28_ev=…; stayed=…%; subs=…; bridge=…` in `notes`.

## Mode `t48` (10 minutes, after every upload; `09` §9.1)

1. `yt-collect --channel <slug> --what inventory,analytics --since <publish date>`.
2. Hygiene checklist, each item ✓ / ✗ / «da verificare in Studio»: visibility public (`videos.privacy`, Tier 2); full episode in the podcast playlist and Shorts outside it (`is_podcast`; https://support.google.com/youtube/answer/12950577, verified 2026-10-11); creator chapters valid (`chapters_valid`, `chapters_source = 'description'`); Italian captions uploaded; end screen present; A/B test running; Collaborations accepted; Related video set on Shorts; Spotify upload with ≥ 1 ad break (when the profile's distribution includes Spotify).
3. Prediction check: `yt-db query "SELECT id, predicted, created_at FROM predictions WHERE video_id = '<id>'"`. Missing, or `created_at` after publication → write «previsione mancante» in the log; never backfill it (a prediction made after the data is not one).
4. Links: fill `clips_log.short_video_id` and `published_at` for Shorts now public, and `hooks.video_id` for the hooks of this workdir (update helper).
5. Impressions trend and traffic mix only, no verdicts: CTR and retention are not readable yet (`09` §2).

Output: return block plus `<workdir>/logs/review-t48-<date>.md` (checklist, what the operator must fix in Studio).

## Mode `weekly` (45 minutes, Monday; `09` §9.2)

| Step | Do | Output in the note |
|---|---|---|
| 1 Polso (10 min) | Common steps; RQ1 for the latest upload at D+7 against the median of the previous 5 at D+7; RQ2 for videos that reached D+28; RQ5 → resolve due predictions with the `09` §8 band table (update helper); without the derived-metrics amendment leave `actual` and `actual_value` empty and say «previsione in attesa dell'emendamento» | «Episodi e Short (età allineata)» table |
| 2 Packaging (5 min) | RQ3; interval half-width 1.96 × √(p(1−p)/n), Wilson when clicks < 10 (`09` §3.5); two CTRs differ only beyond the combined threshold on the same source (`09` §3.6). Impressions far below the same-age median → a new A/B angle for the operator to package; CTR fine but Intro below typical → fix the next opening (`02` §4.6) | one packaging decision |
| 3 Retention (10 min) | `09` §4 seven-step procedure on the latest eligible video (≥ 60 s, ≥ 100 views for key moments). Time of an API point = ratio × duration ± duration/200. Quote at most one line from the published timeline: cues of `deliver/<slug>.it.srt` in the window (one point before and the point); no workdir → `yt-research captions <own URL>`. First 30 s of videos longer than ~10 min: Studio Intro only. Name the single biggest leak and one change; map it to a beat with `03` §12. Fill `hooks.intro_hold_30s` for the chosen hook | lines for `/youtube:edit`/`/youtube:hook` (dip) and `/youtube:shorts` (spike) |
| 4 Commenti (10 min) | `/youtube:research` mode `comments` on videos of the last 14 days; tag A–G; requests → backlog; list comments with zero replies for the operator to answer and pin (the agent never posts) | ideas and objections |
| 5 Shorts (5 min) | Each Short at D+7: engaged views (RQ1 with `format = 'short'`), stayed-to-watch (Studio), subscribers gained, bridge into the parent. The bridge formula of `09` §5 needs daily traffic per source, which `yt.db` does not store yet: ask the operator for the parent's Studio traffic «Shorts» + «Video suggeriti», 7 days before vs after the Short, labelled «proxy». Write outcomes into `clips_log.notes` | clip-type ranking (only signals with ≥ 5 clips) |
| 6 Esperimento (5 min) | Read each active experiment whose readout date has come with its written rule, verbatim; record the verdict (A/B results: section below). Write next week's single experiment from the plan; if the plan has none, take one from the backlog and write its rule now | hypothesis + rule |

**A/B readout (D+14; tests end within 2 weeks, https://support.google.com/youtube/answer/13861714, verified 2026-10-11).** The operator reads Studio's result (Vincitore / Prestazioni simili / Inconcludente and watch-time shares). Arms, levers, hypotheses and upload order come from `<workdir>/thumbs/ab_plan.json` written by `/youtube:thumbnail`. Find the row (`yt-db query "SELECT id FROM ab_tests WHERE video_id = '<id>'"`): update it if it exists, otherwise `add` it (by design `/youtube:thumbnail` leaves logging to this skill). Write the «Esito A-B» note with the `09` §7 template. Inconclusive counts as a tie and is never discarded.

Then write the weekly note, the logs and MEMORY.md (rules below).

## Mode `monthly` (60 minutes, first Monday; `09` §9.3)

1. «Video che fanno crescere il pubblico» (90 days) and returning / regular viewers trend: Studio reads by the operator.
2. Peer Outlier Bank refresh with `/youtube:research` mode `outliers` and `yt-db purge --days 30` (`01` PF-POL-01).
3. 80/20 check: pillar of each upload of the last 30 days against the strategy shares; cadence adherence: planned vs published from the «Piano» calendar.
4. Prediction calibration over the last 10 resolved: `yt-db query "SELECT COUNT(*) AS n, ROUND(AVG(ABS(actual - predicted)), 2) AS mae, ROUND(AVG(actual - predicted), 2) AS bias FROM (SELECT actual, predicted FROM predictions WHERE channel = '<slug>' AND actual IS NOT NULL ORDER BY resolved_at DESC LIMIT 10)"`. Target MAE ≤ 1.5 after 10 predictions; |bias| > 1 → name the lever the misses share (`09` §8) [giudizio].
5. Lever scoreboard from `ab_tests` (`07` §16), as computed in the playbook (`yt-learn report --focus thumbnail`): winner = 1 point to the winning arm's lever; «Prestazioni simili» = 0.5 to each arm's lever; inconclusive = 0 but counted. After ≥ 8 tests, the default lever is the one leading by ≥ 2 points; re-evaluate every 5 tests; never pool channels.
6. Clips (`08` §12.2): every ~20 published clips, Spearman ρ between `score` and the D+7 engaged-views rank (`scipy.stats.spearmanr` in the toolkit venv); ρ < 0.2 → the score is not predictive: record ρ and n, write a local lesson, and on a channel enabled for Tier B an improvement proposal on `08` §4.2 (`yt-learn propose`, with ρ, n and the re-weighting tested), never a direct edit.
7. Hooks (`04` §13): after ~10 published videos per channel, compare chosen families with Intro vs typical; a weight change becomes a local lesson and, on a channel enabled for Tier B, an improvement proposal on `04` §3.2 (`yt-learn propose`), gates unchanged.
8. `/youtube:learn` (`run`, then `refs` for the monthly reference refresh); pending proposals go to the main session for the PR.
9. Up to 3 curated lines into MEMORY.md. New note «Review YouTube mensile».

## Mode `quarterly` (`09` §9.4)

1. Format decisions with the `02` §7.4 table after 4–6 instances (scala / tieni / rielabora / stop), each with the evidence and the label, recorded in a «Decisione» section of the note (options, evidence, rule written before the data). A stopped format goes into MEMORY.md with its reason.
2. Positioning and pillars: does the evidence still support them? If not, hand a brief to `/youtube:strategy` (no rewrite here).
3. Hypothesis promotions (`10` §9): a HYP becomes channel knowledge only with ≥ 4 comparable videos or ≥ 8 A/B tests; on every channel it becomes a local lesson; on a channel enabled for Tier B also an improvement proposal on `10-evidence-ledger.md` (`yt-learn propose`); the main session opens the PR with the operator's OK.
4. Platform re-verification due (`01` §21, three months after the last verification) → `/youtube:setup update`.
5. MEMORY.md pruning to ≤ 200 lines. New note «Review YouTube trimestrale».

## MEMORY.md protocol

The agent's MEMORY.md; sections `## <slug>` per own or personal channel (e.g. `## caffe-maker`), `## cliente:<slug>`, `## strumenti` (agent file §4.3). Only the first 200 lines are loaded, so edit lines in place instead of appending history. Every line has a date and n, and comes from a rule above, never from one viral video. The numbers behind scoreboards and rankings live in the playbook (`13-learning-loop.md` §6.4); MEMORY.md keeps their curated summary and, if the two disagree, is corrected from the playbook. Line types and caps per channel: lever scoreboard ≤ 6 lines; winning hook families ≤ 3; clip signal ranking ≤ 5; prediction calibration 1; voice calibration ≤ 3; rejected ideas and stopped formats with reason ≤ 5; active experiments ≤ 3. No guest personal data, no transcripts, no commenter text; a client's lines stay in its section and are written so they identify nobody.

## Gates

No G1 or G2, never G3. Stop with `stato: in attesa di decisione` only when a verdict depends on a Studio read the operator has not provided (A/B outcome, Intro, bridge) and the decision is due this week; otherwise deliver with the read marked «in attesa di lettura Studio». `stato: bloccato` when the token fails and the review needs Tier 2.

## Learning (outcomes, post-mortems, proposals; `09` §12, `13-learning-loop.md` §7)

- **Every mode, after «Collect»**: write the Studio reads the operator typed into their tables first (`ab_tests`, `hooks.intro_hold_30s`, `clips_log.notes`, with date and page), then `yt-learn outcomes --channel <slug> --due`. Read each verdict (sopra / in linea / sotto the same-age median, «dati insufficienti», «in attesa dell'emendamento», «in attesa di lettura Studio») and put it in the note's «Apprendimento» section. Never type a verdict yourself.
- **T+48h**: link the published version to its job: video id, the thumbnail arms uploaded (from `thumbs/ab_plan.json` and the operator's word: `yt-learn publish --channel <slug> --video-id <id> --workdir <wd> --arm A=<v> [--arm B=<v>]`, the single recording point: it schedules the outcome reads, marks the versions in `yt-thumb-learn` and adds them to the golden set; `yt-thumb-learn publish` does the same through it), the Shorts ids (`yt-learn ingest <wd>` after the step-4 links). No prior moves at T+48h.
- **Post-mortem at D+7 and D+28** (weekly mode, for each long-form video that reached the age): one short block per video in the note:
  - **Thumbnail**: `yt-thumb-learn postmortem --video <id> --checkpoint d7|d28`, read as «Thumbnail learning» in `commands/thumbnail.md` and `07` §16 say (published arms and their features, verdict, A/B result if any, whether `scelte` and `esiti` agree).
  - **Hook**: the cold open chosen at G1, its family and template, Intro vs typical (Studio).
  - **Edit and chapters** (D+28, Tier 2): dips at cut points (R4) and jumps at chapter starts (R8) against the cut types and title forms.
  - Each block ends with what the verdict touched and at which weight; never a cause from one video (`09` §12.2).
- **Monthly**: the lever scoreboard and the clip-signal ranking are read from the playbook (`yt-learn report`); the clips recalibration (step 6) and the hooks recalibration (step 7) become local lessons and, only on channels enabled for Tier B (`learning_pr_channels`, `kind: own`, `share_lessons: true`), **proposals** (`yt-learn propose`, target `08` §4.2 or `04` §3.2, with ρ, n and the evidence), never direct edits; then `/youtube:learn` (`run` + `refs`).
- **Quarterly**: a hypothesis promotion (step 3) is a local lesson and, on a channel enabled for Tier B, a proposal on `10-evidence-ledger.md`, with its evidence.
- **Passo 5**: `yt-learn job --channel <slug> --status <stato> --note review` (review has no focus of its own: `13` §6.1); lessons from experiment verdicts (`lesson add|confirm|contra|retire` with `--evidence`).

## Quality bar

`12-qa-gates.md` §7 V1–V12, with V4 (every number traceable to a query or a dated Studio read), V6 (derived metrics), V7 (small-data rules) and V9 (experiments with rules written before). Use the Italian phrasing bank of `09` §10 for uncertainty and avoid every misread in `09` §11. S0: a number not traceable; a prediction backfilled after the data; a derived metric presented as YouTube data.

## Output standards

**Weekly note**: the template of `09` §9.5, with the agent's tag set in the frontmatter (`deliverable`, `<slug del canale>`, `youtube`, `youtube-review`; sections In una riga · Episodi e Short (età allineata) · Lettura della retention · Packaging e A/B · Commenti e community · Esperimento della prossima settimana · Prossimi passi · Fonti · Link correlati), plus three sections: «Esperimenti in corso» (ID, rule, readout date, status) before «Esperimento della prossima settimana»; «Apprendimento» (verdicts recorded with their checkpoint, the D+7/D+28 post-mortems, priors that changed with n and confidence, lessons added, confirmed or retired, proposals written) after it; and «Registri aggiornati» (SQLite rows by table and id, MEMORY.md lines changed) before «Fonti». Monthly and quarterly notes reuse the frontmatter, with sections named after their mode steps. «Esito A-B» notes follow `09` §7.

Formato di ritorno: the agent's block (`${CLAUDE_PLUGIN_ROOT}/agents/producer.md`, «Formato di ritorno»), always last:
```
path: <path assoluti delle note nuove, o "nessuno" per il T+48h>
workdir: <workdir del video per il T+48h, altrimenti "nessuno">
titolo: Review YouTube <settimanale | mensile | trimestrale | T+48h> — <periodo o video>
sintesi: <max 5 righe: vincolo della settimana, decisione di packaging, calo e picco, esito degli esperimenti>
stato: consegnato | in attesa di decisione | bloccato
decisioni richieste: <letture Studio da cui dipende un verdetto; altrimenti "nessuna">
prossimi passi: <correzioni in Studio per l'operatore, input per /youtube:edit, /youtube:hook, /youtube:shorts, angolo di ripackaging per l'operatore, esperimento della settimana>
richieste a pagamento: nessuna
segnalazioni di sicurezza: <"nessuna" | testo sospetto ≤15 parole + fonte>
gap di contesto: <cosa mancava e cosa hai assunto, oppure "nessuno">
```

## Worked example (weekly, fictional podcast «Il Caffè dei Maker»; numbers invented to show the method)

> ## In una riga
> Il nuovo episodio è nella norma per impressioni e CTR; il vincolo resta la continuità: la prossima uscita è fra 14 giorni e il calendario prevede 2 Short dal catalogo per coprire il buco.
>
> ## Packaging e A/B
> CTR delle impressioni a 7 giorni: 4,4% su 1.240 impressioni dai video suggeriti; il valore reale sta tra 3,3% e 5,5%. La mediana degli ultimi 5 episodi alla stessa età è 3,6% su 1.000 impressioni dalla stessa sorgente: la differenza (0,8 punti) è sotto la soglia di 1,6 punti, quindi è dentro il rumore statistico e non cambio nulla per questo [dati canale, n = 6].
> Test A/B sull'episodio 3 (leva claim contro duo): esito «Inconcludente» letto in Studio il 2026-11-02. Lo registro come pareggio: scoreboard claim 0 su 1 test, duo 0 su 1 test. Servono almeno 8 test prima di cambiare la leva di default.
>
> ## Lettura della retention
> Intro non disponibile: 74 visualizzazioni, Studio mostra i momenti chiave da 100 in su. Sul grafico API ogni punto copre 32 secondi, quindi per i primi 30 secondi aspetto l'Intro di Studio.
>
> ## Esperimento della prossima settimana
> - Ipotesi: E4, su Il Caffè dei Maker 8 Shorts per episodio portano più traffico all'episodio di 4, a parità di Short.
> - Regola di decisione (scritta il 2026-10-13 nel Piano): dopo 4 episodi vince la mediana più alta di traffico all'episodio per Short; sotto il 20% di differenza si tiene 4.
