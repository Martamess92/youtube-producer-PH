# 09 Analytics reading — metric definitions, retention diagnosis, small-data rules, outlier formulas, review rituals, A/B and prediction logs

## How the skills use this file
- `youtube:review` (T+48h, weekly, monthly, quarterly) and `youtube:channel-audit` follow it step by step; `youtube:research` uses §6 for outliers; `youtube:hook`, `youtube:edit` and `youtube:shorts` read §4 to turn retention into editing rules.
- Every number in a deliverable comes from `yt-collect` / `yt-outliers` output in `<studio_dir>/data/yt.db`, a Studio read (manual or read-only browser), or a cited source. The model narrates; it never estimates a metric that was not measured.
- Platform definitions and limits are cited from `01-platform-facts.md` by ID; evidence labels follow `10-evidence-ledger.md` §1 (Italian labels in deliverables).
- When data is missing or too thin, the deliverable says so in Italian with the reason and the threshold (§3, §10). An honest "non ancora leggibile" beats a confident guess.
- Outputs: a new dated note per review in the channel's deliverables folder (`deliver/notes/` by default, or the vault folder the profile names when the operator has a vault; agent Passo 4.2), rows in `yt.db`, and at most a few curated lines in the agent's MEMORY.md.
- Outcomes feed the learning loop (§12, `13-learning-loop.md`): `youtube:review` and `youtube:learn` turn the D+7, D+14 and D+28 reads into `esiti` for the channel's priors, under the same small-data rules.

---

## 0. Access tiers and where each number comes from

| Tier | Access | Available | Not available → write in Italian |
|---|---|---|---|
| 0 | yt-dlp only (no keys) | Public inventory, approximate dates, captions, comments (capped) | Everything owner-only |
| 1 | + Data API key | Exact public inventory and stats, comments, batch stats (`01` PF-API-02/04) | Watch time, retention, traffic, CTR |
| 2 | + owner OAuth (Analytics + Reporting, read-only) | Engaged views, watch time, AVD, AVP, retention curves, traffic sources, audience segments, **impressions + CTR (Reporting only)** | A/B results, Intro key moment, typical band, Shorts stayed/swiped → Studio only |

| Metric family | Primary source | Command / table | Studio-only fallback |
|---|---|---|---|
| Inventory, publish dates, durations | Data API | `yt-collect --channel X --what inventory` → `videos` | — |
| Daily public stats (own + peers) | Data API (`videos.batchGetStats`) | `video_stats_daily`, `peer_videos` (30-day purge, `01` PF-POL-01) | — |
| Engaged views, watch time, AVD, AVP, subs | Analytics API | `--what analytics` → `analytics_28d` | Studio Advanced mode |
| Retention curve (100 points) | Analytics API | `--what retention` → `retention` (video, ratio, audience_watch_ratio, relative_retention) | Studio retention card |
| Traffic sources | Analytics API | `traffic_sources` | Studio Reach tab |
| Impressions, impressions CTR | **Reporting API** reach reports | `--what reporting` → `reach_daily` | Studio Reach tab |
| Intro (0:30), key moments, typical band | **Studio only** | manual or read-only browser read, typed into the review note | — |
| A/B test outcome | **Studio only** | logged in `ab_tests` | — |
| Outlier scores | derived | `yt-outliers --channel X [--window 25]` / `yt-outliers --peers FILE` | Studio Research tab (limited test, `01` PF-STUDIO-04) |

Collector cadence: at least weekly; **never more than 25 days between `--what reporting` runs** (historical reports vanish after 30 days, regular after 60, `01` PF-REP-05). Reporting days are Pacific days (`01` PF-REP-06).

## 1. Metric dictionary

| Metric | Italian term in deliverables | Definition | Source / ID | Caveats | Read it as |
|---|---|---|---|---|---|
| Impressions | Impressioni | Thumbnail shown > 1 s with ≥ 50% visible, on YouTube surfaces | `01` PF-VIEW-06 | Excludes external embeds and end screens | Reach the system granted; first signal of topic/package fit |
| Impressions CTR | CTR delle impressioni | Views from impressions ÷ impressions | `01` PF-VIEW-07, PF-REP-01 | Falls as impressions widen; varies by source; not in Analytics API | Compare within channel, **per traffic source**, with a confidence interval (§3) |
| Views (post 2026-08-24) | Visualizzazioni | Counted from the first frame, incl. hover-autoplay | `01` PF-VIEW-01 | Not comparable across 24–27 Aug 2026 | Never trend raw views across the boundary |
| Engaged views | Visualizzazioni coinvolte | Click/tap to watch or watch past the initial seconds (old definition) | `01` PF-VIEW-02 | — | **Default unit** for all comparisons |
| Watch time | Tempo di visualizzazione (ore) | `estimatedMinutesWatched` ÷ 60 | `01` PF-YTA-01 | Split long-form vs Shorts with `creatorContentType` | Podcast episodes: **engaged watch hours** is the main value metric |
| AVD | Durata media di visualizzazione | Average playback length; excludes looping clips since 2021-12-13 | `01` PF-YTA-01/02 | Dragged down by external traffic | Read per traffic source when it moves |
| AVP | Percentuale media visualizzata | Average % of the video watched | same | Long videos naturally lower | Compare same-length videos only |
| Intro | Spettatori ancora presenti a 0:30 | % still watching after 30 s | `01` PF-RET-01 | Needs ≥ 60 s and ≥ 100 views; 1–2 days processing | **The** hook metric; read vs typical band |
| Typical retention band | Fascia tipica | Your 10 latest videos of similar length | `01` PF-RET-04 | Moving baseline | Above/below typical, never vs an absolute % |
| `audienceWatchRatio` | Rapporto di visione | Times a point was watched ÷ views | `01` PF-YTA-03 | Can exceed 1 | > 1 locally = spike (rewatch or confusion) |
| `relativeRetentionPerformance` | Retention relativa | 0–1 vs similar-length YouTube videos; 0.5 = median | `01` PF-YTA-04 | Coarse on long videos (100 points) | Shape comparison across episodes |
| `startedWatching` / `stoppedWatching` | Ingressi / uscite per segmento | Segment was first / last seen in a playback | `01` PF-YTA-05 | Same 100-point grid | Locate exits and chapter jumps |
| Key moments | Momenti chiave | Intro, top moments, spikes, dips | `01` PF-RET-02 | ≥ 100 views | Studio read; annotate with transcript |
| Stayed to watch (Shorts) | Rimasti a guardare | Share of Shorts-feed shows watched past the opening | `01` PF-SHORTS-09 | No published seconds threshold | Compare Shorts within channel |
| New / returning viewers | Spettatori nuovi / di ritorno | Segment definitions | `01` PF-RET-05 | < 1% regular is normal for new channels | North-star input for community shows (`02` §10) |
| Subscribers gained/lost | Iscritti guadagnati/persi | Per video | `01` PF-YTA-01 | Weak signal (`02` P7) | Secondary |
| Traffic sources | Sorgenti di traffico | `insightTrafficSourceType` | `01` PF-YTA-10 | Detail needs a type filter | §5 |
| Comments per 1,000 engaged views | Commenti ogni 1.000 visualizzazioni coinvolte | derived | `yt.db` | Small n → count, don't ratio, under 20 comments | Participation (Orbit step 3) |
| Shorts → episode bridge | Traffico dagli Short all'episodio | Parent-episode views from RELATED_VIDEO + SHORTS in the 7 days after each Short | derived | **Proxy:** whether the API isolates Related-video link clicks is unverified (`10` OPEN-04) | §5 |
| outlier_x, robust z, VSR | Moltiplicatore outlier, z robusto, VSR | §6 | derived, labelled "metrica derivata" (`01` PF-POL-05) | Not comparable with vidIQ/1of10 scores | §6 |

## 2. Timing: what is readable when

| Checkpoint | Valid reads | Not valid yet | Notes |
|---|---|---|---|
| **T+48h** | Upload hygiene (visibility, playlist, chapters live, end screen, A/B running), first impressions and traffic mix (Studio realtime) | CTR verdicts, retention, outlier status | Analytics lags ~2–3 days `[vendor]`; Intro needs 1–2 days and 100 views |
| **D+7** | Shorts verdicts (engaged views, stayed-to-watch, bridge), early episode race, Intro (if ≥ 100 views), comment harvest | Format decisions | Shorts age gate = 7 days |
| **D+14** | A/B outcome (tests finish within 2 weeks, `01` PF-AB-03) | — | Log the label even if inconclusive |
| **D+28** | Episode verdict: engaged views and engaged watch hours at 28 days, AVP, CTR per source, prediction scoring (§8) | — | **Default comparison age** for long-form |
| **D+90** | "Videos growing your audience", long-tail check (P6) | — | Some videos peak a month+ later (`02` P6) |

Boundaries: compare across **2026-08-24/27** only with engaged views (`01` PF-VIEW-01/04); Shorts across **2025-03-31** only with engaged views (`01` PF-VIEW-05).

## 3. Small-data rules

1. **No universal targets.** Practitioner bands (Intro ~50–70% at 0:30, AVP ~25–35% for long podcasts, Shorts ~70–80% stayed) are `[anecdotal]` sanity ranges only (`10` HYP-01/02). The benchmark is the channel's own typical band.
2. **Same age or nothing.** Compare videos at the same age (D+7, D+28) from `video_stats_daily` snapshots. If a snapshot is missing, mark the row "età non allineata" and exclude it from verdicts.
3. **Trends need ≥ 4 videos.** One video moves nothing; decide on the median of ≥ 4 comparable videos. Format verdicts need 4–6 instances (`02` §7.4).
4. **Key moments need ≥ 100 views** and the retention report can be withheld on small videos (`01` PF-RET-03, PF-YTA-11). Empty = "non disponibile", never zero.
5. **CTR needs an interval.** Approximate 95% half-width = 1.96 × √(p(1−p)/n), n = impressions. Use the Wilson interval when clicks < 10.

   | CTR \ impressions | 300 | 1,000 | 3,000 | 10,000 |
   |---|---|---|---|---|
   | 3% | ±1.9 pp | ±1.1 pp | ±0.6 pp | ±0.3 pp |
   | 5% | ±2.5 pp | ±1.4 pp | ±0.8 pp | ±0.4 pp |
   | 8% | ±3.1 pp | ±1.7 pp | ±1.0 pp | ±0.5 pp |

   Below ~1,000 impressions, 1–2 pp differences are noise.
6. **Two CTRs differ only if** |p₁ − p₂| > 1.96 × √(p₁(1−p₁)/n₁ + p₂(1−p₂)/n₂) **and** they come from the same traffic source. *Worked example:* episode A 4.0% on 1,200 impressions, episode B 5.5% on 900 → threshold 1.86 pp, observed 1.5 pp → not different. Write: «differenza dentro il rumore statistico».
7. **Traffic mix first.** Before comparing CTR or AVD between videos, compare their traffic mix; Home-heavy videos have lower CTR (`01` PF-VIEW-07), external traffic lowers AVD.
8. **Retention precision.** API position ≈ ratio × duration, uncertain by ± half a point (duration ÷ 200): ±15 s on a 50-min episode. Attach transcript quotes only to the window covering the point before and the point itself (60 s on a 50-min episode). For the first 30 s of long episodes use Studio's Intro, not the API (`01` PF-YTA-07 table).
9. **Inconclusive is data.** A/B "Inconclusive" or "Performed same" is logged as a tie, not discarded (§7).
10. **One change per hypothesis.** If two things changed between videos (title style and guest fame), the comparison is confounded: say so.
11. **External promotion bias.** On a small channel, a guest's social push (LinkedIn, newsletter) can dominate a video's numbers. Report EXT_URL share next to every episode verdict.
12. **Write the decision rule before the data** (experiments in `02` §12.7). A rule invented after seeing the numbers is not a test.

## 4. Retention-graph diagnosis

**Reading procedure (7 steps; vidIQ retention discipline, Apache-2.0, paraphrased):**
1. Read the column headers and units before interpreting (`audienceWatchRatio` vs `relativeRetentionPerformance`).
2. State duration, engaged views and whether key moments exist (≥ 100 views).
3. Compare with the typical band (Studio) or with the last 3–5 same-format videos (API, `relative_retention`).
4. Locate the biggest change: Intro vs typical, then the steepest local drop, then spikes.
5. Map it to the transcript window allowed by the precision rule (§3.8); quote at most one line.
6. Name **the single biggest leak** and **one change** for the next video (or a re-edit if it is a Short/clip still unpublished).
7. State confidence (alta / media / bassa) from sample size and curve sparsity. Preserve what worked.

**Shape → cause → how to confirm → fix** (sources: YouTube Help `01` PF-RET-01/02; YouTube "4 metrics" blog https://blog.youtube/creator-and-artist-stories/master-these-4-metrics/ `[official]`; MrBeast memo, paraphrased `[anecdotal]`; yaxeen and youtube-agent-skill heuristics `[anecdotal]`)

| # | Shape | Likely cause | Confirm with | Fix |
|---|---|---|---|---|
| R1 | Intro below typical (steep loss 0:00–0:30) | Click not confirmed: first frame/line ≠ title/thumbnail promise; greeting, logo, sting; poor light/audio at start | Compare thumbnail claim vs first spoken line and first frame ("click triangle"); Studio Intro vs typical | Cold open with the promised moment in 0–10 s; cut greetings and stings; payoff timestamp of the thumbnail inside 0–30 s (`04-hooks-first-30s.md`) |
| R2 | Healthy 0:30, cliff at 1:00–3:00 | Hype never becomes execution; setup too long; promise restated, not delivered | `stoppedWatching` peak in 1–3 min; transcript shows context/small talk | Deliver first value by 1–2 min; compress setup ("crazy progression", paraphrased) |
| R3 | Cliff right after the cold open ends (podcast) | The montage promised, then the show restarted with intro/greetings | Drop sits at cold-open end ± one point | Host Promise→Proof→Plan line straight after the cold open; ≤ 3 s sting or none; first story scene by ~1:30 |
| R4 | Single sharp dip mid-video | Off-topic tangent, sponsor read, confusing explanation, audio/visual problem, repeated context | Transcript window; `yt-timeline-view` at that point | Cut or shorten; re-hook right before; move sponsor later; add a visual |
| R5 | Steady slide, no plateau | No forward tension; disconnected segments; monotone pacing | `relative_retention` below 0.5 across the middle | Open loops; re-engagements at chapter starts every 8–12 min (podcast) or at the 40–60% sag point; chapter titles as promises |
| R6 | Spike (`audienceWatchRatio` > neighbours, possibly > 1) | Rewatch-worthy moment, or confusion (people rewinding) | Transcript + comments with that timestamp | Valuable → Shorts candidate, tease earlier, build a future episode on it. Confusing → on-screen explanation next time |
| R7 | Top moments late in the video | Best material buried | Studio top moments; spikes in the last third | Move or tease earlier; cold open from it |
| R8 | Sawtooth jumps at chapter starts | Viewers navigating via chapters | `startedWatching` peaks at chapter timestamps | Fine for interviews; chapter titles are packaging: make them specific |
| R9 | Early end drop | Ending signalled ("per concludere", goodbyes) | Drop begins at the outro line | Never signal the end; fold the CTA into the payoff; shorten outro; end screen during the payoff |
| R10 | Good retention, low impressions | Package or topic not attracting clicks, or audience too narrow | Reporting impressions vs same-age median | Repackage via A/B; broaden CCN fit (`02` §4.5) |
| R11 | High CTR, low AVD, impressions falling | Clickbait signal (`01` PF-VIEW-09) | Reach + AVD per source | Make the promise match the content |
| R12 | Low overall AVD but Suggested/Browse AVD fine | External/social traffic leaving quickly | AVD by traffic source | Normal; judge on YouTube-native sources |
| R13 | Returning viewers fine, new viewers collapse early (segment toggle in Studio; `subscribedStatus` filter in API) | Insider context, in-jokes, show ritual at the start | Compare subscribed vs unsubscribed curves | Front-load context for strangers; rituals after the hook |
| R14 | Dips aligned with layout switches (composited master: wide ↔ vertical inset) | Hypothesis: inset frames leave most of the 16:9 frame empty on TV/desktop | Overlay layout spans on the curve; AVP by device | Test full-frame long-form (`02` E3) before concluding |
| R15 | Shorts: low stayed-to-watch | First 1–3 s don't stop the scroll; no visual movement; hook text late | First frame + first spoken line | 2-second rule, hook text ≤ 10 words in 0–3 s (`08-shorts-clip-engine.md`) |

Rule: if the Intro is healthy and the slide is flat but reach is low, the problem is packaging, not the edit.

## 5. Traffic sources and the Shorts bridge

| Source (`insightTrafficSourceType`) | Meaning | Expected behaviour | What to do |
|---|---|---|---|
| RELATED_VIDEO | Suggested / Up Next | Biggest source for subscribed channels (`02` P7) | Package as next watch after peers and your previous episode |
| SUBSCRIBER | Home and subscription feeds for subscribers | Low CTR is normal | Don't chase; build returning viewers |
| YT_SEARCH | Search | Slow, compounding; high intent | Keyword-first titles and chapters |
| SHORTS | Swipes in the Shorts feed | Shorts views; also counts into the parent when viewers continue | Bridge metric below |
| EXT_URL / NO_LINK_OTHER | Outside links, apps, messaging | Low AVD normal; dominates small channels at launch | Report share; don't judge retention on it |
| PLAYLIST / YT_CHANNEL | Playlists, channel page | Higher CTR (warm audience) | Series playlists |
| END_SCREEN / NOTIFICATION / HASHTAGS | — | Small | Check end-screen element performance in Studio |

**Shorts → episode bridge** (per Short, D+7): views of the parent episode from RELATED_VIDEO + SHORTS in the 7 days after the Short, minus the parent's median daily views from those sources in the 7 days before. Label it «proxy» until the live API shows whether Related-video link clicks are isolated. Log per Short in `clips_log` with its signal type so clip types can be ranked by median bridge and median engaged views.

## 6. Outlier formulas (implemented by `yt-outliers`; F6 B7, V3 §21)

### 6.1 Same-age views
`V_a(v)` = engaged views (own channels) or public views (peers) of video *v* at age *a* days, from daily snapshots. Defaults: a = 28 for long-form, a = 7 for Shorts. Age gate without snapshots: long-form ≥ 14 days, Shorts ≥ 7 days, flagged «età non allineata».

### 6.2 Within-channel multiple
`outlier_x(v) = V_a(v) / median{ V_a(u) : u ∈ previous N same-format uploads of the channel, u ≠ v }`
- N = 25 by default (`yt-outliers --window 25`); allowed 20–30. Exclude lives and premieres; Shorts and long-form are separate baselines.
- **Minimum baseline: 8 comparable videos.** Below that, output «baseline insufficiente» and switch to the episode race (§6.4) and peer outliers (§6.5).
- Median, not mean: one viral video would inflate the mean.

### 6.3 Robust z on logs
`z(v) = (ln V_a(v) − median(ln V_a)) / (1.4826 × MAD(ln V_a))`, MAD = median absolute deviation. Flag z ≥ 2. The log tames the heavy tail; 1.4826 makes MAD comparable to a standard deviation.

*Worked example (fictional channel, 11 episodes at mixed ages, illustration only):* views 30, 88, 52, 125, 61, 230, 95, 300, 160, 70, 115 → ln = 3.401, 4.477, 3.951, 4.828, 4.111, 5.438, 4.554, 5.704, 5.075, 4.248, 4.745; median ln = 4.554; absolute deviations median (MAD) = 0.443; scale = 1.4826 × 0.443 = 0.657. Episode 8 (300 views, **3.2×** the median of 95) has **z = 1.75**, episode 6 (230 views, 2.4×) z = 1.35. Neither is an outlier by z: with 11 dispersed videos a 3× multiple is within normal spread. This is why a young channel's own baseline cannot produce outlier verdicts yet.

### 6.4 Episode race (small channels)
For each episode, engaged views and engaged watch hours at D1, D7, D28 vs the **median of the previous 5 episodes at the same age**. Report the ratio and the rank (e.g. «3° su 6 a 7 giorni»). Curves are truncated at real age, never padded.

### 6.5 Cross-channel discovery (peers)
- `VSR(v) = views(v) / subscribers(channel)`; niche-normalised `VSR / median VSR of the peer set`. Secondary column only: VSR favours small channels.
- **Engagement sanity filter:** drop videos with < 1.5 likes per 1,000 views as probable paid/ad traffic (author heuristic from yuben-app, `[anecdotal]`) and report how many were dropped.
- Peer rows are purged or refreshed within 30 days (`01` PF-POL-01).

### 6.6 Tiers (tool convention, not a standard)
| outlier_x | Label (IT) | Action |
|---|---|---|
| < 0.5 | sotto la norma | Check packaging and topic; no autopsy unless repeated |
| 0.5–2 | nella norma | Average videos teach little |
| 2–5 | notevole | Code it (`02` §5 schema) |
| 5–10 | forte | Code + teardown of first 60 s |
| ≥ 10 | breakout | Full teardown; consider a series |
A video needs **both** x ≥ 2 and z ≥ 2 to enter the Outlier Bank as an outlier.

### 6.7 Watch-hour outliers for podcasts
For full episodes, compute the same multiple on **engaged watch hours at D+28** (own channels only). A 60-min episode with average views but high watch hours is a strong episode for the recommender (`02` P2); views alone undervalue it.

### 6.8 Presentation
Always show: the formula used, N, age, baseline size, and the label «metrica derivata, non un dato YouTube». Never mix vidIQ/1of10 scores with ours.

## 7. A/B testing log

**Before the test** (in `youtube:thumbnail` / packaging step): 2–3 variants that differ on **one lever family** (claim / proof / duo / name-led for thumbnails; story / credential / question for titles); each variant has a written hypothesis and a payoff timestamp in 0–30 s; all thumbnails ≥ 1280×720 (`01` PF-AB-07). Thumbnail tests first, title tests separately on later episodes, so lever learning is not confounded.

**During:** no edits to title or thumbnail (`01` PF-AB-08). Read at D+14.

**After — fields written to `ab_tests`** (column names as implemented in `lib/ytdb.py`, 2026-10-11): `video_id`, `channel`, `kind` (thumbnail|title|both), `started_at`, `ended_at`, `variants_json` (`[{"id", "lever", "text" (the hook, 3–6 words since thumbnail v2 — `07` §5.3 — or the title), "hypothesis", "payoff_ts", "file"}]`), `metric` = `watch_time_share`, `winner` (variant id or empty), `result_json` (`{"result": "winner|same|inconclusive", "watch_time_share": {…} if Studio shows it, "impressions_during_test": n from Reporting}`), `notes`. Inserts with `ytdb.py add ab_tests '{…}'`; updates with the helper in `youtube:review`.

**Note** (new file, `{YYYY-MM-DD} — Esito A-B [slug].md` in the channel's deliverables folder):
```markdown
---
tags:
  - deliverable
  - [slug del canale]
  - youtube
  - yt-review
  - ab-test
channel: [slug del canale]
skill: /youtube:review
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
# Esito A/B — [titolo episodio]

| Variante | Leva | Testo | Ipotesi | Payoff a |
|---|---|---|---|---|
| A | claim | «[3–6 parole, frase completa]» | [perché dovrebbe trattenere] | 00:00:07 |

**Esito**: [Vincitore / Prestazioni simili / Inconcludente] · **Vincitrice**: [id] · **Periodo**: [date]
**Lettura**: [2–3 righe, con etichette di evidenza]
**Prossima mossa**: [cosa testare dopo]
```

**Lever scoreboard** (computed from `ab_tests` into the channel playbook, `13-learning-loop.md` §6.4; at most a few summary lines in `MEMORY.md`): wins / ties / inconclusive per lever. After **8–10 tests** the default layout is decided by the scoreboard, not by doctrine. Inconclusive results on small channels are common (no public base rate): they still force variety and are logged as ties. Each logged test also becomes a pairwise `esiti` outcome for the thumbnail features of its arms (§12.1).

## 8. Prediction log (Paddy Galloway's 1–10 practice, operationalised)

**When:** before publishing (part of the G3 checklist), for every long-form video and every Short batch.

**Scale** — predicted band of `outlier_x` at D+28 on engaged views (engaged watch hours for podcast episodes); Shorts at D+7:

| Score | outlier_x band | Score | outlier_x band |
|---|---|---|---|
| 1 | < 0.25× | 6 | 1.1–1.5× |
| 2 | 0.25–0.5× | 7 | 1.5–2× |
| 3 | 0.5–0.75× | 8 | 2–3× |
| 4 | 0.75–0.9× | 9 | 3–5× |
| 5 | 0.9–1.1× (channel median) | 10 | ≥ 5× |

If the baseline has < 8 videos, predict against the median of the last 5 at the same age and mark «confidenza bassa».

**Fields in `predictions`** (as implemented in `lib/ytdb.py`): `video_id`, `channel`, `idea`, `metric` (`outlier_x_ewh_28d` podcast episodes, `outlier_x_ev_28d` other long-form, `outlier_x_ev_7d` Shorts), `predicted` (score 1–10), `rationale` (one line: why above/below median, plus levers: packaging lever, format, guest reach), `created_at` (automatic; must precede publication), `actual` (score 1–10, filled at D+28 / D+7), `actual_value` (measured multiple), `resolved_at`. Error = `actual − predicted`, computed in the query.

**Calibration (monthly):** mean absolute error (MAE) and bias (mean signed error) over the last 10 predictions. Practical target `[judgment]`: MAE ≤ 1.5 after 10 predictions; bias outside ±1 means systematic over/under-confidence — write which lever the misses share (e.g. «sopravvalutiamo gli ospiti con molti follower LinkedIn»). New formats get a longer window before their misses count (Paddy).

## 9. Review rituals

### 9.1 T+48h pulse (10 min, after every upload)
1. `yt-collect --channel X --what inventory,analytics --since <publish date>`.
2. Hygiene checks: visibility public, in the right playlist (full episodes only in the podcast playlist, `01` PF-POD-03), chapters live, end screen present, A/B running, Collaborations accepted, Related video set on Shorts.
3. Note impressions trend and traffic mix only. **No verdicts.**

### 9.2 Weekly review (45 min, Monday)
| Step | Time | Do | Output in the note |
|---|---|---|---|
| 1 Pulse | 10 min | `yt-collect --channel X --what inventory,analytics,retention,reporting --since <last Monday −7d>`; latest upload at D+7 vs the last 5 at D+7 (episode race); prediction vs actual if D+28 reached; `yt-learn outcomes --channel X --due` (§12) | Tabella episodi |
| 2 Packaging decision | 5 min | Impressions far below same-age median → new A/B angle; CTR fine but Intro below typical → fix the next opening | Una decisione |
| 3 Retention read | 10 min | §4 procedure on the latest eligible video: annotate 1 dip, 1 spike, 1 top moment with transcript windows | Righe per `youtube:edit` (dip) e `youtube:shorts` (spike) |
| 4 Comments harvest | 10 min | Mom Test tags → idea backlog; reply to unanswered comments; pin the best | Lista idee e obiezioni |
| 5 Shorts check | 5 min | Stayed-to-watch, engaged views D+7, bridge; continue/kill clip styles | Classifica tipi di clip |
| 6 Experiment | 5 min | Write next week's single experiment with its decision rule | Ipotesi + regola |

### 9.3 Monthly (60 min, first Monday)
"Videos growing your audience" (90 days); returning/regular trend; peer Outlier Bank refresh (`yt-outliers --peers FILE`) and 30-day purge; 80/20 mix check; cadence adherence; prediction calibration (§8); lever scoreboard update; `/youtube:learn` run with the monthly reference refresh (`refs`); up to 3 curated lines into `MEMORY.md`.

### 9.4 Quarterly
Positioning and pillars review (`02`); format scale/keep/rework/stop decisions (`02` §7.4), recorded in a dated decision note; re-verify `01-platform-facts.md`.

### 9.5 Weekly note template (Italian; new file each week)
Path: `{YYYY-MM-DD} — Review YouTube settimanale.md` in the channel's deliverables folder (`<studio_dir>/work/<slug>/deliver/notes/` by default, or the vault folder the profile names).

```markdown
---
tags:
  - deliverable
  - [slug del canale]
  - youtube
  - yt-review
channel: [slug del canale]
skill: /youtube:review
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
# Review YouTube settimanale — [settimana dal … al …]

## In una riga
[il vincolo principale di questa settimana e la mossa che ne segue]

## Episodi e Short (età allineata)
| Video | Età | Visualizzazioni coinvolte | Ore di visione | vs mediana ultime 5 | CTR (n impressioni) | Intro vs tipico | Previsione → esito |
|---|---|---|---|---|---|---|---|

## Lettura della retention
- Calo principale: [mm:ss ± precisione] — [causa probabile] — [fonte: Studio / API] — confidenza [alta/media/bassa]
- Picco: [mm:ss] — [candidato Short sì/no]

## Packaging e A/B
[test in corso / esito / prossima leva]

## Commenti e community
[domande, obiezioni, richieste → backlog]

## Esperimento della prossima settimana
- Ipotesi: …
- Regola di decisione (scritta adesso): …

## Prossimi passi
- [ ] …

## Fonti
[comandi eseguiti, date di raccolta, pagine Studio lette]

## Link correlati
[[…]]
```

## 10. Writing uncertainty in Italian (phrasing bank)

| Situation | Write |
|---|---|
| Too few impressions | «Dato non ancora leggibile: [n] impressioni; il CTR reale sta tra [a]% e [b]%.» |
| No key moments | «Studio non mostra i momenti chiave sotto le 100 visualizzazioni: retention non disponibile.» |
| Age mismatch | «Confronto escluso: età non allineata ([x] vs [y] giorni).» |
| Within noise | «Differenza dentro il rumore statistico: non cambio nulla per questo.» |
| Confounded | «Sono cambiati due fattori insieme ([…] e […]): non posso attribuire l'effetto.» |
| Derived metric | «Moltiplicatore outlier: metrica derivata da noi (mediana delle ultime [N] a [a] giorni), non un dato YouTube.» |
| API granularity | «Sul grafico API ogni punto copre [s] secondi: per i primi 30 secondi uso l'Intro di Studio.» |

## 11. Common misreads (never)
- Comparing raw views across 24–27 Aug 2026, or Shorts across 2025-03-31.
- Treating subscriber count or subscriber CTR as the health metric (`02` P7).
- Calling a 1–2 pp CTR change on < 1,000 impressions a result.
- Reading a long episode's hook from the API curve (30 s per point).
- Judging a format on one episode or at T+48h.
- Presenting outlier multiples without N, age and baseline size.
- Concluding "Shorts hurt long-form" from a before/after view count (`10` HYP-07).
- Quoting practitioner benchmarks as YouTube targets.

## 12. Outcomes → learning (`13-learning-loop.md`)

Outcomes are the `esiti` signal of the learning loop: what the audience did with what the operator chose. They update the channel's priors at a reduced weight and never on their own rewrite a default (`13` §3). `youtube:review` pulls them in every mode and `youtube:learn` when run by hand: `yt-learn outcomes --channel <slug> --due`, after a fresh `yt-collect`.

### 12.1 What each checkpoint feeds

| Checkpoint | Tier 0 (yt-dlp, public) | Tier 1–2 (API, Reporting) and Studio reads | Feeds (`esiti`) | Weight (config, as implemented) |
|---|---|---|---|---|
| T+48h | — | hygiene (§9.1) | nothing: it links the published version (video id, thumbnail arms, Shorts ids) to its job | none (`T+48h` never moves a prior) |
| D+7 | public views at 7 days vs the median of the previous same-format uploads at 7 days | Shorts: engaged views, stayed-to-watch (Studio), bridge proxy (§5); long-form: impressions and CTR with their interval (§3.5), Intro vs typical (Studio, ≥ 100 views) | `shorts.signal`, `shorts.band`; `hook.family` (Intro); thumbnail features (early read) | `learning_outcome_weight_d7` (0.25) |
| D+14 | — | A/B readout typed by the operator (§7) | thumbnail features of the arms, pairwise: winner > each loser; «Prestazioni simili» = tie; «Inconcludente» = counted, no move | `learning_ab_weight` (1.0) |
| D+28 | public views at 28 days vs the same-age median | engaged watch hours (podcast episodes) or engaged views (other long-form) vs the same-age median (§6.4, §6.7); AVD and retention by source; CTR per source with its interval | thumbnail features, `hook.*`, `chapters.title_form` (jumps, R8), `edit.cut_type` (dips at cut points, R4) | `learning_outcome_weight_d28` (0.5) |

### 12.2 The verdict

- **Sopra / in linea / sotto**: the video's same-age metric divided by the median of the previous same-format videos at the same age; above `learning_above_ratio` (1.25) is «sopra», below `learning_below_ratio` (0.8) is «sotto», in between «in linea». CTR verdicts use the interval test (§3.6) instead: inside the noise = «in linea».
- **Baseline**: fewer than `learning_min_baseline` (3) comparable videos at the same age → «dati insufficienti», no update. Missing snapshot → «età non allineata», no update (§3.2).
- **Boundaries**: never across 24–27 Aug 2026 for raw views, nor across 2025-03-31 for Shorts (§2); use engaged views or wait.
- **External push** (§3.11): when EXT_URL / NO_LINK_OTHER is more than half of the video's views (Tier 2), the verdict is recorded but it does not move packaging priors (thumbnail, hook): the click did not come from the package. At Tier 0 the traffic mix is unknown: say so next to the verdict.
- **Confounds** (§3.10): a published video changes many things at once (guest, topic, package). Its verdict moves each feature of its package only by the checkpoint weight; a single-variable conclusion comes from a native A/B (package level) or a pre-test (`07` §15.2), never from one upload.
- **Lessons on `esiti`** need ≥ 4 comparable videos (§3.3) and are labelled `[appreso: esiti, n=…, conf. …]`.

### 12.3 Tier 0, API data and the derived-metrics gate

- **Tier 0**: public view counts from yt-dlp snapshots (`source = 'ytdlp'`). The same-age comparison is a local signal labelled «dato pubblico osservato, non API», never mixed with API rows in one median (`11` §4.5). When Tier 1 arrives, the API rows replace them and the verdicts are recomputed.
- **Tier 1–2**: a ratio or verdict computed from API Data is a derived metric (`11` §4.4). Until MEMORY.md `## strumenti` records the amendment as accepted, `yt-learn` stores the raw values, marks the verdicts «in attesa dell'emendamento» and does not update priors from them; learning from the operator's choices continues. After acceptance, every verdict shown carries «calcolato da noi, non è un dato YouTube».
- **Studio reads** typed by the operator (Intro vs typical, A/B result, stayed-to-watch) are recorded with their date and page; Studio's own band («sopra la fascia tipica») is YouTube's comparison, not ours.

### 12.4 Post-mortems

At D+7 and D+28 `youtube:review` writes, per published long-form video, a short post-mortem of the package (thumbnail arms, hook, title lever) and of the edit (dips at cut points, chapter jumps): what the verdict was, which features it touched and at which weight, whether `scelte` and `esiti` agree. The thumbnail post-mortem follows `commands/thumbnail.md` «Thumbnail learning» and `07` §16. Post-mortems never claim a cause from one video: they record, the priors weigh.
