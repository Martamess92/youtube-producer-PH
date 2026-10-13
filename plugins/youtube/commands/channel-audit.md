---
description: "Channel Audit — audit diagnose-first di un canale YouTube: livello di accesso, fotografia, tabella a età fissa, inventario packaging, anomalie e un solo vincolo primario"
argument-hint: "[richiesta] [--channel=<slug>] [--tier=0|1|2] [--peers=<file>] [--lang=it]"
---

# Channel Audit

## Integrazione

- **Dove gira**: dentro l'agente `youtube:producer`. Se questa skill arriva nella sessione principale (l'operatore ha scritto `/youtube:channel-audit` invece di `/youtube:producer`), non eseguirla lì: applica `${CLAUDE_PLUGIN_ROOT}/commands/producer.md` con la stessa richiesta e gli stessi parametri (lancia l'agente con il tool Agent, `subagent_type: "youtube:producer"`, e gestisci i gate come dice il dispatcher). Il guard dei comandi, la memoria e l'apprendimento dell'agente valgono solo lì. Se sei l'agente, o se la skill gira in una sua eval (`evals/`), prosegui.
- **Lingua output**: italiano (`--lang` per cambiare). Il corpo inglese è il metodo.
- **Parametri**: `--channel=<slug>` carica il profilo `<slug>.md` (nei `channels_dirs` di `yt-config`). `--tier` forza un livello di accesso più basso (utile per un confronto pubblico). `--peers` indica il file dei canali di riferimento (default `~/youtube-studio/data/peers-<slug>.txt`; `~/youtube-studio` = `studio_dir`).
- **Dove salvare**: una nota nuova `{YYYY-MM-DD} — Audit canale YouTube.md`, con `skill: /youtube:channel-audit` e `status: draft`, secondo `deliverables_mode` e il profilo (agente, Passo 4.2): nella cartella deliverable del profilo nel vault, oppure in `<studio_dir>/work/<slug>/deliver/notes/`. Numeri in `~/youtube-studio/data/yt.db`; file di lavoro (thumbnail scaricate, fogli QA, tabelle outlier) in `~/youtube-studio/cache/audit/<slug>-<YYYY-MM-DD>/`. Mai un audit sovrascritto: ogni audit è un file nuovo, confrontato con il precedente.
- **Agente**: `youtube:producer` (il YouTube Producer).
- **Confini**: l'audit diagnostica e si ferma a un vincolo primario più due secondari; posizionamento, format e calendario li scrive `/youtube:strategy`. Valutare idee e scrivere titoli resta all'operatore (o alla sua skill di packaging). Se il vincolo vero non è YouTube ma il business (offerta, prezzo, funnel), dillo nella nota e nel ritorno invece di forzare una diagnosi di canale.
- **Skill correlate**: usa le procedure di `/youtube:research` (outlier, commenti) senza riscriverle; dopo l'audit vengono `/youtube:strategy` e i quick win (`/youtube:chapters`, ripackaging con `/youtube:thumbnail` e i titoli dell'operatore). Accessi mancanti → `/youtube:setup`.
- **Quando usarla**: primo lavoro su un canale (dopo l'onboarding), quando un canale «non cresce», prima di una strategia, ogni trimestre come confronto.
- **Apprendimento**: al Passo 0 legge `yt-learn report` (tutti i focus) e il playbook come evidenza del canale; al Passo 5 registra il vincolo primario scelto. I disaccordi tra scelte dell'operatore ed esiti del pubblico sono un input della diagnosi (`13-learning-loop.md` §3.1).

## Input

$ARGUMENTS

---

## Identity and standard

You are the diagnostician. You read the channel the way a doctor reads a chart: measurements first, then one diagnosis you can defend, then a referral. The standard:

- **Diagnose before prescribing** (`02-strategy-playbook.md` §0). The output is one primary constraint and two secondary, each with evidence and a confidence level. Never a list of twenty tips.
- **Trust rule.** Every number comes from a command's JSON, a `yt.db` query (with the query date), a Studio read typed by the operator (with the date) or a cited source. The model narrates; it never estimates a metric (`09` §0). Video IDs are re-checked against `videos` before they appear.
- **Tier honesty.** What the current access tier cannot see is written «non disponibile: serve livello 2», never inferred from a proxy without saying so.
- **Small data is not a verdict.** Same age or nothing; trends need ≥ 4 videos; CTR needs an interval; inconclusive stays inconclusive (`09` §3).

**Command convention.** Toolkit commands are on the Bash PATH while the plugin is enabled: call them by bare name, never through the plugin cache. `yt-db` is the SQLite helper; `yt-db query "SELECT …"` is read-only; `yt-config` prints the runtime paths. Replace `<slug>` in every query. Below, `~/youtube-studio` means `studio_dir`.

## Inputs to load

1. Channel profile `<slug>.md` (agent Passo 0.1): `kind`, north star, pillars, cadence (`max_gap_days`), baseline block, open decisions.
2. `02-strategy-playbook.md` in full: §0 stance and routing, §1 discovery principles, §3 cold-start doctrine, §4.6 packaging diagnostics, §5 outlier method, §11 Italian benchmarks, §12 (the baseline and positioning model a channel fills), §13 (personal channels) and §14 (clients).
3. `09-analytics-reading.md` §0 (tiers), §1 (metric dictionary), §2 (timing), §3 (small-data rules), §4 (retention diagnosis R1–R15), §5 (traffic sources), §6 (outlier formulas), §10 (Italian uncertainty phrasing), §11 (misreads).
4. `01-platform-facts.md` §1–§2 (views, impressions, retention), §6 (chapters, end screens), §8–§9 (podcasts, Collaborations), §12–§15 (APIs and policies).
5. `10-evidence-ledger.md` §1 (labels), §3 (do-not-encode), §4 (hypotheses), §7 (open items this skill can answer: visibility, retention withholding).
6. `11-compliance-safety.md` §2–§4 (ToS, yt-dlp, API storage and derived metrics).
7. `12-qa-gates.md` §7 (V1–V12) and §8 (critic).
8. MEMORY.md: the channel section (`## <slug>`, or `## cliente:<slug>`) and `## strumenti` (amendment status).
9. Notes (vault or `deliver/notes/`): the previous audit and the latest weekly review of the channel; the profile's `vault.context` folder (read-only) when a vault is in use.

## Procedure

### Step 0 — Access tier

1. `yt-doctor --channel <slug> --json`; `yt-auth --channel <slug> --check` (Tier 2 if it returns the profile's `channel.id`; while the profile's `id` is still `null`, match the returned `customUrl` and title against `channel.handle` and ask `/youtube:setup` to record the id); `test -f "$(yt-config --get studio_dir)/secrets/api_key"` (Tier 1).
2. Write the tier statement first. What each tier can and cannot show is `09` §0; in the note, list the analyses marked unavailable.
3. Channel without a profile (prospect or unknown): run `/youtube:setup` onboard steps 2–3 to create a minimal profile with `status: "prospect"` in the `channels_dirs` (never inside the plugin), then audit at Tier 0/1 only. No Tier 2 without the owner's authorisation.
4. Derived-metrics gate (`11` §4.4): if MEMORY.md `## strumenti` does not record the amendment as accepted, outlier multiples, z scores and «Intro vs tipico» ratios are written «non disponibile: serve l'emendamento derived metrics»; raw numbers are still shown.

### Step 1 — Data pull

1. `yt-collect --channel <slug> --what inventory,analytics,retention,reporting` at Tier 2; `--what inventory` at Tier 0/1. Read `access`, `quota` and `warnings` in the JSON. A failed token stops Tier 2 work (authorization re-check rule, `11` §4.3).
2. Run the queries below and keep their outputs (date, row count) for the «Fonti» block.

```sql
-- Q1 inventory and hygiene
SELECT v.id, v.title, substr(v.published_at,1,10) AS pub, v.published_precision AS prec, v.format,
       ROUND(v.duration/60.0,1) AS min, v.privacy, v.is_podcast, v.has_chapters, v.chapters_valid,
       v.chapters_source, v.views, v.source
FROM videos v JOIN channels c ON c.id = v.channel_id WHERE c.slug = '<slug>' ORDER BY v.published_at;
-- Q2 gaps between long-form uploads (days)
SELECT pub, julianday(pub) - julianday(LAG(pub) OVER (ORDER BY pub)) AS gap_days
FROM (SELECT substr(v.published_at,1,10) AS pub FROM videos v JOIN channels c ON c.id = v.channel_id
      WHERE c.slug = '<slug>' AND v.format = 'long');
-- Q3 fixed age: first 28 days (Tier 2; complete = 1 only)
SELECT v.id, substr(v.published_at,1,10) AS pub, a.engaged_views AS ev28,
       ROUND(a.minutes_watched/60.0,1) AS hours28, ROUND(a.avg_view_pct,1) AS avp, a.complete
FROM videos v JOIN channels c ON c.id = v.channel_id JOIN analytics_28d a ON a.video_id = v.id
WHERE c.slug = '<slug>' AND v.format = 'long' ORDER BY v.published_at;
-- Q4 impressions and CTR in the first 28 days (Reporting only)
SELECT r.video_id, SUM(r.impressions) AS impr,
       ROUND(SUM(r.impressions * r.ctr) / NULLIF(SUM(r.impressions), 0), 4) AS ctr
FROM reach_daily r JOIN videos v ON v.id = r.video_id
WHERE r.report_type = 'channel_reach_basic_a1'
  AND r.date BETWEEN substr(v.published_at,1,10) AND date(substr(v.published_at,1,10), '+27 days')
GROUP BY r.video_id;
-- Q5 traffic mix per video (lifetime)
SELECT t.video_id, t.source_type, t.views,
       ROUND(100.0 * t.views / SUM(t.views) OVER (PARTITION BY t.video_id), 1) AS pct
FROM traffic_sources t JOIN videos v ON v.id = t.video_id JOIN channels c ON c.id = v.channel_id
WHERE c.slug = '<slug>' AND t.period = 'lifetime' AND t.video_id <> '' ORDER BY t.video_id, t.views DESC;
-- Q6 API retention resolution
SELECT video_id, ROUND(duration) AS dur_s, ROUND(sec_per_point,1) AS s_per_pt, intro_hold_30s
FROM retention_summary;
```

Reading rules for these queries:
- Q4: check the CTR unit on the first rows (ratio 0–1 or percent) before writing it. Reach data exists only from 30 days before the Reporting job was created (`01` PF-REP-03): older videos get «CTR non disponibile: prima della finestra dei report».
- Q6: use `intro_hold_30s` only where `s_per_pt ≤ 6` (videos up to ~10 min). On longer videos the first API point already spans the hook: use Studio's Intro (`01` PF-YTA-07; https://developers.google.com/youtube/analytics/dimensions, verified 2026-10-11).
- Q1: `chapters_source = 'auto'` means YouTube generated them; the creator hygiene check needs `description`.
- Raw `views` are not comparable across 24–27 Aug 2026; compare with engaged views (`01` PF-VIEW-01, https://blog.youtube/inside-youtube/engaged-views-youtube-explained/, verified 2026-10-11).

3. **Studio reads** (only the operator or the main session can do them; the agent has no browser). List them precisely in `decisioni richieste` or `prossimi passi`: per long-form video with ≥ 100 views, Intro % at 0:30 and its position against the typical band; visibility of each video (Tier < 2); podcast playlist designation and contents; end screens yes/no; «Video che fanno crescere il pubblico» (90 days); new / casual / regular viewers; device split (TV share); advanced features and YPP status. Key moments need ≥ 60 s and ≥ 100 views (https://support.google.com/youtube/answer/9314415, verified 2026-10-11). If the reads are missing, finish the audit and mark the cells «in attesa di lettura Studio».

### Step 2 — Snapshot and anomalies

| Check | Source | Rule (verified 2026-10-11) | Anomaly if |
|---|---|---|---|
| Visibility | Q1 `privacy` (Tier 2) or Studio | unlisted videos are left out of search, related videos, recommendations, subscriber feeds and the channel's Videos tab, but they can still appear in a public playlist (https://support.google.com/youtube/answer/157177) | a video meant to be public is not; an episode visible in the Podcast tab but missing from the Videos tab is the typical trace of an unlisted video inside a public playlist |
| Podcast playlist | collector podcast check, Studio | only full episodes, in order (https://support.google.com/youtube/answer/12950577) | clips/Shorts inside it, or an episode missing |
| Chapters | Q1 | first at 00:00, ≥ 3, each ≥ 10 s (https://support.google.com/youtube/answer/9884579); recommended for podcasts > 20 min (`01` PF-POD-08) | episode > 20 min without valid creator chapters |
| Cadence | Q2 | profile `cadence.max_gap_days`; `02` §8 | any gap above it in the last 180 days; last upload older than it |
| Formats | Q1 `format` | Shorts are separate systems (`01` PF-SHORTS-06) | no Shorts at all; Shorts without a parent link (Studio) |
| End screens | Studio | last 5–20 s, video ≥ 25 s (https://support.google.com/youtube/answer/6388789) | missing on long-form |
| Collaborations | Studio | up to 10 collaborators (https://support.google.com/youtube/answer/16554898) | guests with channels never invited |
| Title hygiene | Q1 titles | no «Ep. N – Nome», keyword early (`01` PF-POD-08, PF-META-04) | episode numbers first, ALL CAPS, generic question |
| Thumbnails | Step 4 sheet | legible at 168–246 px wide | text unreadable at small sizes, repeats the title |
| Inactivity | Q2 | YPP may switch off monetisation after 6 months without uploads or Posts (https://support.google.com/youtube/answer/72851) | YPP channel near 6 months dark |

### Step 3 — Fixed-age performance table

One row per long-form video (Shorts in a separate table at D+7). Columns: video · published · minutes · age · engaged views 28 d · hours 28 d · × median (N, age) · z · CTR 28 d (impressions, ± interval) · Intro vs typical (Studio) · AVP · top source (share) · EXT_URL share.

1. Outliers: `yt-outliers --channel <slug> --window 25 --min-baseline 8 --format long --md ~/youtube-studio/cache/audit/<slug>-<date>/outliers.md`. With Tier 2 the script uses 28-day views when they cover ≥ 60% of videos (`--basis auto`), else today's views (not same-age).
2. The script falls back to the nearest videos when fewer than `--min-baseline` earlier videos exist. The audit does not: below 8 comparable earlier videos, the row says «baseline insufficiente» and the table switches to the episode race (`09` §6.4: each episode vs the median of the previous 5 at the same age). A video enters the Outlier Bank only with x ≥ 2 **and** z ≥ 2 (`09` §6.6).
3. CTR interval: half-width ≈ 1.96 × √(p(1−p)/n), n = impressions; below ~1,000 impressions, 1–2 pp differences are noise (`09` §3.5). Compare CTR only within the same traffic source and after comparing traffic mix (`09` §3.7).
4. Report EXT_URL share next to every verdict: on small channels guest promotion can dominate a video's numbers (`09` §3.11).
5. Tier 0/1: one column of public views today, labelled «età non allineata», and no verdict column.

### Step 4 — Packaging inventory

1. Download own thumbnails into `~/youtube-studio/cache/audit/<slug>-<date>/thumbs/` with `curl -s -o <id>.jpg https://i.ytimg.com/vi/<id>/maxresdefault.jpg` (fallback `hqdefault.jpg`), one per second.
2. `yt-thumb-qa ~/youtube-studio/cache/audit/<slug>-<date>/thumbs/*.jpg --out ~/youtube-studio/cache/audit/<slug>-<date>/qa`; add `--grid <dir of peer thumbnails>` when peer thumbnails were fetched in `/youtube:research`. Look at the PNGs; the metrics alone decide nothing.
3. Code each video with the schema of `02` §5 step 4 (`title_pattern`, `thumb_pattern`, `promise`, `length_band`, `guest_fame`). For the top 2 and bottom 2 videos by the Step 3 measure, check promise–content match: the thumbnail claim and title promise against the first 60 s of our own transcript (local workdir, or `yt-research captions <own URL>` at low volume). Flag title–thumbnail word repetition (`07-thumbnails.md` P1; `10` DNE-05).
4. A pattern difference between top and bottom videos is a hypothesis unless it holds on ≥ 4 videos; write it as «ipotesi da testare» with the experiment it implies.

### Step 5 — Outlier Bank (peers)

Apply `/youtube:research` mode `outliers` (peer part) when the peer file exists and the operator confirmed it. Otherwise propose 20–40 peers (`02` §5 step 1) in `decisioni richieste` and mark the section «in attesa di conferma dei peer». Never block the audit on this step.

### Step 6 — Audience

Studio segment reads (Step 1.3); comments via `/youtube:research` mode `comments` on the top 5 videos by engaged views. Under 20 comments in total: quote patterns qualitatively, no ratios (`09` §1).

### Step 7 — Diagnosis: one primary constraint, two secondary

Score each candidate constraint, then pick with the rule below the table.

| Constraint (IT label) | Route (`02` §0) | Signals (need ≥ 2) | Minimum tier |
|---|---|---|---|
| Igiene e visibilità | retrospective audit | intended-public video not public; full episodes missing from the podcast playlist; no valid chapters on episodes > 20 min; no end screens | 0 (+ Studio) |
| Continuità | retrospective audit | gap above `max_gap_days`; < 2 long-form uploads in the last 60 days; no Shorts bridging the gap | 0 |
| Tema e packaging | packaging | first-28-day impressions < 0.5× the median of the last 5 same-format videos; CTR below the channel median beyond the interval on the same source; bottom videos share a title pattern (generic question, no number, no protagonist) | 2 (1 for weak title evidence) |
| Distribuzione | packaging | no Shorts; guests with channels never invited as Collaborators; EXT_URL > 50% of views on most videos while YouTube-native sources stay flat | 0–2 |
| Apertura | hook / retention | Intro below typical on ≥ 3 of the last 5 eligible videos; R1 or R3 shapes (`09` §4) | 2 + Studio |
| Tenuta | hook / retention | `relative_retention` < 0.5 through the middle on ≥ 3 of 5; R4 or R5 shapes | 2 |
| Format | format pivot | same-format median < 0.5× peers' comparable format over ≥ 4–6 instances; the format fails the 52-week test (`02` §7.3) | 1–2 |
| Nicchia | niche doubt | uploads spread over ≥ 4 unrelated topics; new viewers who arrive never return; comments from outside the target audience | 1–2 |

**Selection rule.** Walk the viewer chain upstream to downstream: exist and be visible → keep publishing → be shown and clicked → be found beyond the channel → hold the first 30 s → hold the middle → format → niche. The primary constraint is the **first** one in that order with confidence ≥ media. Exception: a downstream constraint with confidence alta beats an upstream one with confidence bassa; say why in one line. The next two by the same order are the secondary constraints.

**Confidence.** Alta: Tier 2 data, ≥ 4 comparable videos, effect outside the interval. Media: Tier 1 data or Studio reads on 3 videos, or consistent qualitative evidence across sources. Bassa: Tier 0, fewer than 3 videos, or confounded (two things changed at once, `09` §3.10).

Each constraint is written as: claim → evidence (numbers with labels, n, age) → confidence → what would change the verdict → referral.

### Step 8 — Quick wins and referrals

Up to 5 quick wins, each ≤ 1 h of the operator's time, reversible, tied to the primary constraint (e.g. chapters retro-fit via `/youtube:chapters`; repackaging an old video through an A/B test, never delete and re-upload: `01` PF-UPLOAD-01). Then the referrals: `/youtube:strategy` for positioning, formats, calendar and the KPI tree; `/youtube:setup` for missing access; the operator for repackaging copy (titles). For clients, write in a confident, operational tone and never question contractual goals in the note; strategic doubts go to the operator in the return block.

### Step 9 — QA, save, memory

1. Self-check `12-qa-gates.md` §7 V1–V12, with V8 (exactly one primary and two secondary) and V6 (derived metrics labelled «calcolato da noi, non è un dato YouTube» or unavailable).
2. Spawn the critic (`12` §8.5 brief, deliverable `vault`) on the draft and the query outputs; fix S0/S1; one confirmation re-check only.
3. Save the note. MEMORY.md, channel section: one dated line «audit <data>: vincolo primario <X> (confidenza <Y>)». Delete third-party files in the audit cache (peer thumbnails, captions) once the note is saved; own-channel files may stay up to 30 days (`11` §1).

## Gates

No G1 or G2: the audit cuts and renders nothing, and G3 is never the agent's. It returns `stato: in attesa di decisione` only when it cannot produce a defensible diagnosis without the operator (peer list to confirm, Studio reads that decide between two primary constraints, ambiguous channel). Otherwise it delivers with the open reads listed. `stato: bloccato` for a token on the wrong channel or a client without authorisation to read its data.

## Learning (Passo 5, `13-learning-loop.md` §4.2)

- **Reads at Passo 0**: `yt-learn report --channel <slug>` and the playbook. A persistent disagreement between `scelte` and `esiti` (e.g. the operator keeps choosing a lever that stays below the same-age median) is a candidate packaging constraint, labelled with its n and confidence; below 4 comparable videos it goes under «Cosa non sappiamo ancora».
- **Logs**: `yt-learn job`; the primary constraint and the two secondary ones as a decision, so the next audit can compare.
- **Typical proposals**: none directly; the audit hands evidence to `/youtube:strategy` and `/youtube:review`.

## Quality bar

`12-qa-gates.md` §7 (V1–V12) and §8 (critic, mandatory for audits). S0 for this skill: a number not traceable to a query, command or dated Studio read; a derived metric presented as YouTube data; another client's data in the note; commenter handles stored.

## Output standards

Note (Italian, new file, vault or `deliver/notes/` per `deliverables_mode` and the profile):
```markdown
---
tags:
  - deliverable
  - <slug del canale>
  - youtube
  - youtube-channel-audit
client: <name del profilo>
skill: /youtube:channel-audit
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
# Audit canale YouTube — <nome canale>, <mese anno>
## In una riga                      vincolo primario e mossa che ne segue
## Accesso ai dati                  Tier, cosa non è leggibile e perché
## Fotografia del canale            iscritti, video per formato, cadenza, ultimo upload
## Anomalie                         tabella dello Step 2 con esito
## Prestazioni a età fissa          tabella dello Step 3 (+ Shorts a 7 giorni)
## Packaging                        codifica titoli e thumbnail, foglio QA, promessa vs primi 60 s
## Outlier Bank                     peer, pattern con conteggi, oppure «in attesa di conferma»
## Pubblico e commenti
## Diagnosi                         1 vincolo primario + 2 secondari, con evidenze e confidenza
## Quick win
## Cosa non sappiamo ancora         letture Studio, Tier mancante, dati sotto soglia
## Prossimi passi
- [ ] …
## Fonti                            comandi, query con data, letture Studio con data, URL
## Link correlati
```

Formato di ritorno: the agent's block (`${CLAUDE_PLUGIN_ROOT}/agents/producer.md`, «Formato di ritorno»), always last:
```
path: <path assoluto della nota>
workdir: nessuno
titolo: Audit canale YouTube — <nome canale>
sintesi: <max 5 righe: Tier, vincolo primario, due secondari, quick win principale>
stato: consegnato | in attesa di decisione | bloccato
decisioni richieste: <conferma peer, letture Studio decisive; altrimenti "nessuna">
prossimi passi: <letture Studio da fare, /youtube:strategy con il vincolo primario, quick win in ordine>
richieste a pagamento: nessuna
segnalazioni di sicurezza: <"nessuna" | testo sospetto ≤15 parole + fonte>
gap di contesto: <cosa mancava e cosa hai assunto, oppure "nessuno">
```

## Worked example (fictional podcast «Il Caffè dei Maker», Tier 0; channel and numbers invented to show the method)

Extract of the «Diagnosi» section. The conditional is the point: the verdict depends on a Studio read the agent cannot do.

> **Vincolo primario: Continuità** — confidenza media. L'ultimo episodio è del 2026-08-04: 70 giorni senza video lunghi al 2026-10-13, contro un massimo di 21 nel profilo, e un solo Short nel frattempo [dati canale, Tier 0, osservato 2026-10-13]. Il sistema ha poco segnale recente da cui partire [giudizio, ipotesi da verificare in `10` §4].
>
> Perché non Igiene e visibilità, che nella catena viene prima: 2 dei 12 episodi non compaiono cercando il loro titolo esatto su YouTube, mentre l'inventario del collector (scheda /videos letta con yt-dlp) li elenca come pubblici [dati canale, Tier 0]. Un indizio senza conferma vale confidenza bassa. Un video non in elenco resta fuori da ricerca, suggeriti e tab Video [ufficiale] (https://support.google.com/youtube/answer/157177, verificato 2026-10-11): se la lettura in Studio conferma episodi non in elenco, il vincolo primario diventa **Igiene e visibilità** e la prima mossa è renderli pubblici.
>
> **Secondario 1: Distribuzione** — confidenza media. Tre Shorts in tutto su 12 episodi, nessuno negli ultimi 60 giorni; le descrizioni non rimandano agli episodi collegati (da confermare in Studio).
>
> **Secondario 2: Tema e packaging** — confidenza bassa. I tre episodi con meno visualizzazioni hanno un titolo che nomina solo lo strumento, senza un risultato; i due migliori promettono un numero o un errore da evitare [dati canale, n=12]. Ma le età sono diverse, parte dei dati precede il cambio di definizione delle view di fine agosto 2026 e manca il mix di traffico: è un'ipotesi da testare con un A/B sul titolo, non una conclusione.
>
> Moltiplicatori outlier: baseline insufficiente (12 episodi a età diverse, servono almeno 8 precedenti comparabili alla stessa età).
