# 02 Strategy playbook — discovery, packaging, formats, cadence, community and positioning for own channels, personal channels and clients

## How the skills use this file
- `youtube:strategy` and `youtube:channel-audit` read it in full (§12 is the model every own channel fills in its notes); `youtube:research` reads §5 and §11; `youtube:review` reads §7.4 and §10; `youtube:thumbnail` and `youtube:hook` read §4.
- Method is in English; every deliverable built from it is in Italian, in the channel's voice (the channel profile `<slug>.md`). Italian examples here are original and illustrative: replace every `[segnaposto]` with verified facts.
- Platform numbers come from `01-platform-facts.md` (cite by ID); metric formulas and review rituals from `09-analytics-reading.md`; claims banned or hypothesis-only from `10-evidence-ledger.md`.
- Every recommendation in a deliverable carries an evidence label (`[ufficiale]`, `[ufficiale·indiretto]`, `[studio]`, `[vendor]`, `[aneddotico]`, `[osservato AAAA-MM-GG]`, `[dati canale]`, `[interno]`, `[giudizio]`; English equivalents in this file, mapping in `10` §1) and, when it is an experiment, a decision rule written before the data arrives.
- Ownership: per-video idea scoring and packaging copy (titles, descriptions, social posts) belong to the operator, or to a packaging skill if one is installed on the operator's machine. This file owns the channel-level layer: positioning, pillars, formats, cadence, packaging *system*, KPI tree, community rituals.
- Channel-specific facts (baseline numbers, positioning, pillars, guests) never live in this file: they go in the channel's notes and profile (§12 is the empty model).

---

## 0. Stance

1. **Diagnose before prescribing.** No positioning or calendar without a `youtube:channel-audit` (or an explicit "audit skipped, assumptions listed" block). Route the diagnosis into one of five problems (CreatorLens pattern, MIT, V1 §31): retrospective audit, hook/retention, packaging, format pivot, niche doubt. Name **one primary constraint** and at most two secondary.
2. **Ask once: size or business?** "Maximum audience" vs "a smaller audience that supports a business". For a show attached to a community, events or sponsors, and for a personal expert channel (inbound for its owner's business), the answer is business/community: optimise for returning viewers and qualified actions, not raw reach.
3. **Viewer, not algorithm.** Every format and package is designed for a named viewer and for what they watched just before (§1, P3/P7).
4. **Numbers from scripts, prose from the model** (trust rule, yuben-app, V3 K10). If a number is not in `yt.db`, a Studio read, or a cited source, it does not appear.
5. **Sustainable beats ambitious.** A format that dies in week 9 is worse than a smaller one that runs 52 weeks (§7.3).
6. **One experiment at a time per variable family**, with the decision rule written up front (§12.7).

## 1. How discovery works: principles the strategy relies on

| # | Principle | Evidence | Label | Strategic implication |
|---|---|---|---|---|
| P1 | Recommendations are **pulled per viewer** at session start; rankings differ from viewer to viewer; notifications are the push exception | Beaupré (YouTube), Creator Insider 2026-09-01, via https://ppc.land/subscribers-skip-90-of-uploads-in-their-feed-youtube-director-says/ | `[official·secondary]` | There is no global score to "beat". Design for a specific viewer and their previous watch |
| P2 | Ranking objective ≈ **expected watch time per impression**; pure CTR ranking was dropped because it promoted clickbait | Covington, Adams, Sargin, RecSys 2016 https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/ | `[study]` (Google Research) | Packaging is judged by the watch time it produces. Test & Compare uses watch time for the same reason (`01` PF-AB-02) |
| P3 | Watch time is weighted by predicted **satisfaction** ("valued watch time": survey ratings, likes, dislikes, dismissals; weights personalised) | Goodrow, https://blog.youtube/inside-youtube/on-youtubes-recommendation-system/ (2021); Zhao et al. RecSys 2019 multitask ranker https://research.google/pubs/recommending-what-video-to-watch-next-a-multitask-ranking-system/ | `[official]` / `[study]` | A hook that holds by withholding and then disappoints is punished twice. Pay the click |
| P4 | The strongest features describe the **viewer's history with the channel and topic** (how many of your videos they watched, how recently they watched this topic) | Covington 2016 §4.1 | `[study]` | Topic and format consistency compound. Returning viewers get more of your videos (`01` PF-RET-05) |
| P5 | An impression that is not clicked demotes the video for that viewer on the next load; but engagement sometimes comes after many repeated exposures | Covington 2016; Beaupré 2026 (capping experiment, no data published) | `[study]` / `[anecdotal]` | Low CTR on an old video is fixable by repackaging, not by re-uploading (`01` PF-UPLOAD-01) |
| P6 | Freshness is modelled, but decisions are not launch-only: some videos peak on day one, others a month or more later | Covington 2016 ("example age"); Beaupré 2026 | `[study]` / `[official·secondary]` | Never kill a video or format on T+48h data. Judge at D+28 (`09` §2) |
| P7 | No subscriber-first gate: early exposure reaches non-subscribers in the first hour; subscribers and non-subscribers are learned separately; low subscriber CTR in Browse is normal; **Suggested is the biggest source of views for subscribed channels** | Beaupré 2026 via PPC Land | `[official·secondary]` | Don't over-index on subscriber count. Package each episode as the natural next watch after adjacent videos |
| P8 | **Cold start**: with no viewer history the system matches topic to likely audiences; if nobody bites, impressions stop | Beaupré 2026 | `[official·secondary]` | Small channels must make the topic legible (§3) |
| P9 | Signals weigh differently by surface and person (time spent may matter more on TV, likes/dislikes on phones); TV viewers get longer videos | Beaupré 2026; podcasts on TV `01` PF-POD-09 | `[official·secondary]` | Full podcast episodes are TV inventory: thumbnails must read at 10 feet, openings must survive "hover" viewing |
| P10 | Shorts and long-form are **separate recommendation systems** | `01` PF-SHORTS-06 | `[official]` | Shorts are probes and bridges, not a growth hack for long-form; measure the bridge (§9, `09` §5) |
| P11 | Separate channels make sense only when **value propositions or audiences differ** | Beaupré 2026; Google podcast two-pager `01` PF-POD-06 | `[official]` | A show and its hosts' personal channels stay separate; cross-pollinate with Collaborations |

## 2. Surfaces and how to package for each

| Surface | What drives it | Packaging move |
|---|---|---|
| Browse / Home | Personalised mainly by watch history; CTR naturally lower (broad placement) | Must beat everything else the viewer likes: one clear promise, curiosity + clarity, recognisable series look for returning viewers |
| Suggested / Up Next | Mainly the video being watched now | Make it the obvious next watch after peer episodes and your own previous episode: same topic vocabulary, series playlists, end screen to the next in-series |
| Search | Relevance (title, description, transcript, tags), query-specific watch time, quality | Keyword early in title; keyword-first chapters; detailed description (`01` PF-RET-07). Choose searchable vs curiosity title per video |
| Shorts feed | Separate system; stayed vs swiped | First frame + spoken first line + text hook; Related-video link to the episode (`01` PF-SHORTS-05) |
| Subscriptions / notifications | Push to opted-in viewers | Skipping is normal; build returning viewers instead of chasing subs |
| TV / living room | Longer videos; podcasts growing on TV | Full episodes, 10-foot thumbnails, no reliance on small on-screen text for meaning |

## 3. Cold-start doctrine (channels under ~1,000 subscribers)

| Symptom (from `09`) | Move | Why |
|---|---|---|
| Impressions stop within days of upload | Make the topic legible: the niche's own vocabulary (for a maker show: builder, SaaS, side project) in title, first description lines, chapters and spoken intro | P8: the system must match topic to an audience |
| Most views from EXT_URL / NO_LINK_OTHER | Bring **qualified** external viewers (guest's LinkedIn, newsletter, community) whose watch behaviour teaches the system who the audience is; never buy views | Quality external watchers seed the audience model; low-retention external traffic is normal (`09` §4) |
| First 10–15 episodes with no search traffic | Pick topics with search demand (Studio Research tab, autocomplete, peer outliers) for a share of the slate | Search is often the first discovery source for fresh videos (older Beaupré guidance, SEJ) `[official·secondary]` |
| No Shorts | Publish Shorts as cheap topic probes, each linked to its episode | P10; Shorts test topics without production cost |
| Guest has a channel | Co-post via Collaborations (`01` PF-COLLAB-01) | Shown to the guest's audience too |
| Long publishing gap | Resume with back-catalogue Shorts + chapters retro-fit while the next episodes are produced | Recent signal matters (P6) |

## 4. Packaging-first system

### 4.1 Order of operations (per video; owners in brackets)

1. **Premise test** [`youtube:strategy` → operator or packaging skill]: one sentence, viewer-centred, specific tension or outcome. Template: *"Come [protagonista] è passato da [A] a [B] senza [C]"*.
2. **20–40 title candidates** across angles [operator or packaging skill; 20–40 for flagship episodes, not the usual 8–10]: transformation, number/result, versus, three-tier comparison, contrarian, mistake/regret, insider-Italia, question with stakes, list of N.
3. **3 thumbnail concepts on 3 different levers** that complement, never repeat, the title [`youtube:thumbnail`; `07-thumbnails.md`].
4. **Kill rule:** if you cannot write a title + thumbnail you would click, do not record or cut the episode that way; pick another angle from the same conversation.
5. **Pick the 3 most different pairs** for A/B (`01` PF-AB-01). Different lever, not different wording.
6. **First 30 seconds confirm the click** [`youtube:hook`; `04-hooks-first-30s.md`]: each concept carries a payoff timestamp that lands in 0–30 s.
7. **Predict** the outcome on the 1–10 scale before publishing and log it (`09` §8).
8. After the test: log the result in `ab_tests` and the lever scoreboard (`09` §7).

### 4.2 Title rules

| Rule | Source | Label |
|---|---|---|
| Keyword early; no excessive caps/emoji; searchable vs curiosity chosen per traffic source | `01` PF-META-04 | `[official]` |
| Lead with value + keyword; never "Show Ep. 54 – Nome" | `01` PF-POD-08 | `[official]` |
| Guest **name only if recognisable**; otherwise descriptor/credential/transformation | Paddy Galloway, https://www.colinandsamir.com/resources/the-new-rules-of-youtube-from-paddy-galloway | `[anecdotal]` (practitioner) |
| One promise per title; credentials over names; numbers frequent among high performers | Grow The Show ep. 240 (5,463 titles, method undisclosed) | `[anecdotal]` → hypothesis `10` HYP-03 |
| A common interview-podcast house format: strong part in the first 60 characters, ≤ 100 total, guest name after `|`, no ALL CAPS, ≥ 1 concrete number, no "Ep. N". Each channel writes its own in the profile's `copy_rules` | channel profile | house rule |
| Series signature at the end (e.g. `| Il Caffè dei Maker`) is allowed; the front carries the promise | F4 §4.2 | `[judgment]` |

### 4.3 Title formula bank — interview podcast (Italian, original, illustrative)

This bank (§4.3), and the per-channel banks of §4.4, are **constraints and seeds for the packaging system** that `youtube:strategy` writes. Per-video titles are produced by the operator (or by a packaging skill, if one is installed), who receives the bank as input; no `/youtube:` skill ships a title from it. Every example below is invented: replace each `[segnaposto]` with verified facts.

| Formula | Example (replace segnaposto with verified facts) | Use when | Evidence |
|---|---|---|---|
| Trasformazione A→B in tempo | `Da [ruolo di partenza] a [risultato verificato] in [periodo] \| [Ospite]` | Guest has a clean before/after with numbers | Transformation and constraint framings recur among Italian founder-story outliers (§11) `[observed 2026-10-11]`; test on the channel (E1, §12.7) |
| Vincolo + risultato | `[Numero] clienti senza budget: come è nato [prodotto] \| [Ospite]` | The constraint is the surprise | `[judgment]`, to test |
| Errore / rimpianto | `Ho buttato [N] mesi su una feature che nessuno usava \| [Ospite]` | Guest tells a real failure with a lesson | `[anecdotal]` (negative framing, Grow The Show) |
| Tre livelli (Paddy) | `SaaS da 100€, 1.000€ e 10.000€ al mese: cosa cambia davvero` | Panel or solo numbers episode | `[anecdotal]` (practitioner) |
| Insider Italia | `Aprire una SRL per un SaaS: quanto costa davvero` | Playbook, search-driven | search demand to be checked `[judgment]` |
| Versus | `Bootstrap o investitori? Due founder, due strade, numeri veri` | Two guests or host vs guest disagree | Gurulandia versus outlier `[observed 2026-10-11]` |
| Domanda con posta in gioco | Weak alone: `Una newsletter può diventare un lavoro?`. Repair with a number: `[N] iscritti a una newsletter di [nicchia]: quanto rende davvero \| [Ospite]` | Only with a number or a named stake | generic questions tend to under-perform `[judgment]`; verify on the channel |

### 4.4 Title formula bank — other channels

Each channel keeps its own formula bank in its notes or profile, outside the plugin. The rules of §4.2 and the profile's `voice` and `copy_rules` apply; every `[N]` comes from the channel owner's records, never estimated; clients stay anonymous unless they signed off.

### 4.5 CCN fit check (Core / Casual / New)

For each idea, score 0–2 on whether it serves **Core** (the channel's returning audience), **Casual** (adjacent builders who watch occasionally) and **New** (someone who never heard of the channel). Ship ideas scoring ≥ 4/6 with no 0 on New for flagship slots; experiments may score 0 on Core. Source: third-party synthesis of Paddy's videos (CreatorLens), `[anecdotal]`, verify against the linked videos before quoting.

### 4.6 Packaging diagnostics (official logic; reading rules in `09` §4)

- High CTR + low AVD + falling impressions → promise does not match content (`01` PF-VIEW-09).
- CTR fine, Intro below typical → the opening, not the package, is broken: fix the next video's first 30 s.
- Low impressions in the first days → topic or package not matched to an audience: change angle (new A/B set), not words. Ed Lawrence reads impressions before CTR in the first hours `[anecdotal]` (https://creatorscience.com/podcast/ed-lawrence/).
- Old video underperforming → repackage (Paddy's and Ed Lawrence's practice; a single word change can revive it `[anecdotal]`), never delete and re-upload.

## 5. Outlier method (strategy use; formulas in `09` §6)

**Outlier Bank procedure** (F4 §3.6, F6 B7–B9):
1. **Peer set, 20–40 channels**, confirmed by the operator: direct Italian peers, adjacent Italian niches, 3–5 global analogs. For the example niche of §11 (Italian founder and tech interviews), its channels are a starting point to propose (BSMT, Gurulandia, Marcello Ascani, Montemagno, Prima o Poi, Raffaele Gaito, Datapizza, Startup Geeks, Starter Story), plus peers found by `youtube:research` mode `competitors`. Other niches build their own list the same way.
2. **Inventory** last 50 long-form uploads per peer (`yt-collect`/Data API; ~21 units per 500 videos, `01` PF-API-04). Peer rows are purged or refreshed within 30 days (`01` PF-POL-01).
3. **Score** with `yt-outliers --peers FILE` (median at same age, robust log-z, VSR secondary). Keep ≥ 3× and z ≥ 2.
4. **Code each outlier** with this schema (one row per video): `topic`, `format`, `title_pattern` (transformation / number / versus / tiers / question / name-first / credential-first / negative / list), `thumb_pattern` (faces count, words count, emotion, number present, brand frame), `promise`, `length_band`, `guest_fame` (known / niche / unknown), `hook_type` (from first-60-s captions via `yt-research captions`).
5. **Contrast with non-outliers** from the same channels: a pattern counts only if it appears in **≥ 3 outliers across ≥ 2 channels** and is **at least twice as frequent** among outliers as among the channel's median videos. Below that it is an anecdote.
6. **Write hypotheses** in the form *"Sul canale, [pattern] batte [alternativa] su visualizzazioni coinvolte a 28 giorni"* and turn the top 2 into experiments (§12.7).
7. **Generate variants** for the channel and hand them to the operator (or a packaging skill) for copy; log predicted 1–10 (`09` §8).

Outlier formulas differ between tools (vidIQ uses channel average, 1of10 shows ≥ 10× channel average, VSR uses subscribers); their scores are not comparable with ours `[vendor]`.

## 6. Strategist frameworks digest (paraphrased; how to apply)

| Source | Core ideas (paraphrase) | Label | Apply to own channels |
|---|---|---|---|
| **Paddy Galloway** (Colin & Samir write-up; edited transcript https://thetranscriptdesk.substack.com/p/the-new-rules-of-youtube-2025-edited) | No click, no watch: top creators spend far more time on ideation/packaging than small ones; write dozens of title/thumbnail variants; exaggerate the framing then pull back to what is honest; curiosity devices (superlatives, versus, three tiers, "familiar but unexpected"); borrow formats from adjacent niches; study outliers, most growth comes from one idea turned into a repeatable format; names only if famous; ~80% of uploads for the core audience, ~20% experiments; predict each video 1–10 vs baseline; confirm the click immediately and re-hook ~30 s in | `[anecdotal]` (practitioner) | Packaging time budget per episode ≥ 2 h; descriptor-first titles; 80/20 slate; prediction log |
| **MrBeast production memo** (leaked 2024; authenticity likely but unconfirmed). **Paraphrase only: never quote it, never attach or link the PDF in deliverables** | Production must know title and thumbnail before working; the first minute loses the most viewers; move from hype to execution in minutes 1–3 with compressed progression; plan re-engagements around minute 3 and 6; the back half tolerates explanation; never signal the end; CTR, AVD, AVP are the trackable trio | `[anecdotal]` (leaked) | 50-min episode: cold open with the strongest promise-fulfilling moment; chapter-opening teasers every 8–12 min; explanatory material in the back half; end on the payoff, not on goodbyes |
| **Ed Lawrence** (Film Booth, Creator Science ep. 155) | No script or shoot before title + thumbnail; poll packaging styles with the community; revive weak videos with a new thumbnail; assume your idea is boring and attach it to a result viewers want; impressions before CTR as the early signal | `[anecdotal]` | A show with a community can poll 3 thumbnail styles in its chat before the A/B (cheap pre-test) |
| **Colin & Samir** (Creator Science ep. 263) | A repeatable format is the path to consistency: could you make it weekly for 52 weeks? One steady "engine" show plus experiments; long-form builds relevance through time spent; don't tie income to AdSense; expect years, not months | `[anecdotal]` | 52-week test (§7.3); engine + experiments portfolio; revenue not tied to AdSense alone (sponsors, products, services) |
| **Jay Clouse** (Creator Science) | Expert-led creator business: packaging is the gateway; owned channels (newsletter) reduce platform dependence | `[anecdotal]` | Closest analog for a personal expert channel: YouTube feeds an owned newsletter and a booking link |
| **The Diary Of A CEO** (Colin & Samir case study; secondhand analyses) | Packaging run as a function (a dedicated packaging lead); candidate topics visualised as thumbnails and tested to learn interest before shaping the episode | `[anecdotal]` | Before recording, sketch 3 thumbnail claims per guest and ask which the community would click |
| **CreatorLens** (MIT, Paddy/Ed/Kallaway lenses) | Diagnose-first routing into 5 problems; pull only the data each problem needs | `[anecdotal]` | Used in `youtube:channel-audit` routing (§0) |

## 7. Formats and series bible

### 7.1 Portfolio rule
- **One engine format** on a steady schedule carries ~80% of uploads; **one experiment slot** (~20%) rotates new formats `[judgment]` (house portfolio rule; the split is a starting point, not a measured optimum). Never two experiments in the same weeks: you will not know which one moved the numbers.
- Each format has its own playlist, its own thumbnail frame variant and a series tag.

### 7.2 Format card (deliverable template, Italian)

```markdown
## Format: [nome]
- **Premessa in una frase**: [chi, cosa succede, perché guardarlo]
- **Spettatore**: [Core / Casual / New] — [descrizione concreta]
- **Promessa**: [cosa porta a casa chi guarda]
- **Durata**: [min–max] · **Cadenza**: [settimanale / bisettimanale / mensile]
- **Struttura**: cold open [s] → promessa → capitoli [n, ogni ~min] → re-engagement a [min] → payoff → ponte al prossimo episodio
- **Segmenti ricorrenti**: [es. la domanda della community, l'errore della settimana]
- **Costo di produzione**: [ore registrazione + ore montaggio + ore packaging] per puntata
- **Test delle 52 settimane**: [punteggio /12, criterio più debole]
- **Metrica di successo**: [es. ore di visione coinvolte a 28 gg ≥ mediana canale]
- **Regola di stop**: [es. dopo 6 puntate, se < 0,5× mediana e nessun segnale qualitativo → rework o stop]
- **Finestra di valutazione**: [n puntate] · **Prossima revisione**: [data]
```

### 7.3 The 52-week test (rubric)

Score each criterion 0–2. **Pass = ≥ 9/12 with no 0 on Capacity or Supply.**

| Criterion | 0 | 1 | 2 |
|---|---|---|---|
| Capacity | hours/instance × cadence > available hours | 70–100% of available hours | ≤ 70% of available hours |
| Supply | < 6 ideas/guests in backlog, no sourcing channel | 6–11 or one fragile channel | ≥ 12 + a repeatable sourcing channel (community, events) |
| Dependency | dies if one person is missing | survives with effort | runs with either host |
| Production risk | needs a specific place/tool/person each time | occasional dependency | repeatable kit |
| Motivation | hosts would stop after 3 flat months | unsure | hosts would make it for 6 months with flat numbers |
| Premise stability | premise changes every episode | mostly stable | one sentence true for all 52 episodes |

**Worked example (fictional) — «Il Caffè dei Maker», biweekly interview**: capacity 1 (recording 1.5 h + agent pipeline ~1.5 h machine + ~1 h human gates + packaging 2 h; tight with two hosts who also run meetups); supply 2 (a maker community + meetups as sourcing channel); dependency 1; production risk 1 (location and composite layout); motivation 2; premise 2 → **9/12, pass**. Weakest: capacity → protect it by batching two recordings per session.

### 7.4 Format lifecycle decisions

Evaluate after **4–6 instances** (experiments: 6; Paddy gives new formats longer windows) on **engaged watch hours at D+28** for full episodes and **engaged views at D+7** for Shorts, against the channel median of the same format family (formulas in `09` §6).

| Result after window | Qualitative signal (comments, DMs, guests asking, community talk) | Decision |
|---|---|---|
| Median ≥ 1.5× channel median | any | **Scale**: give it the engine slot or a second slot |
| 0.75–1.5× | positive | **Keep**, iterate packaging |
| 0.75–1.5× | none | **Keep one more window** with a packaging change |
| 0.5–0.75× | positive | **Rework** the premise or packaging, then one more window |
| < 0.5× | none | **Stop** and log the reason in `MEMORY.md` (rejected ideas with reasons) |

Before the channel has ≥ 8 long-form videos at D+28, use peer outliers and the episode race (`09` §6.4) instead of channel medians, and label the decision `[judgment]`.

### 7.5 Series mechanics
- Series tag at the end of the title; same thumbnail frame family; dedicated playlist; end screen and spoken bridge to the next instance of the same series.
- Chapters for every episode > 20 min (`01` PF-POD-08), keyword-first titles (`youtube:chapters`).
- Spoken bridge in the last 30 s: name the next episode's promise, not "iscriviti".

## 8. Cadence

| Hours available per week (all people) | Long-form | Shorts | Notes |
|---|---|---|---|
| < 4 | 1 per month | 1 per week from back catalogue | Better a fixed monthly day than irregular bursts |
| 4–8 | 1 every 2 weeks | 2 per week | Common default for a two-host interview show |
| 8–15 | 1 per week | 2–3 per week | Only if the 52-week test passes at weekly |
| > 15 | 1–2 per week + 1 experiment per month | 3–5 per week | Rarely sustainable for a small team |

Rules:
- **Consistent release day and time** (e.g. every other Thursday 18:00 CET). The day is part of the promise to returning viewers.
- **No multi-month gaps.** A long gap leaves the system with little recent signal (HYP-20). Once in YPP, 6 months without uploads or Posts can switch off monetization (`01` PF-YPP-02).
- **Spread Shorts across the gap** to the next episode (≈ 2/week) instead of dumping them in week one (F6 A5).
- **Back-catalogue mining:** every old episode yields 2–4 Shorts and chapters retro-fit; untick "notify subscribers" only for bulk back-uploads (`01` PF-UPLOAD-01).
- Publishing time is not a ranking factor for Shorts (Sherman 2023, `[official·secondary]`); for long-form choose the time the core community is free (evening), then keep it.

## 9. Community-led growth on YouTube

### 9.1 Orbit / Commitment Curve mapped to YouTube features

| Step (Orbit / Commitment) | YouTube feature (`01` IDs) | Ritual | Metric to watch (`09`) |
|---|---|---|---|
| Observer → first watch | Shorts + Related video (PF-SHORTS-05); search-friendly episodes | 3–5 Shorts per episode, each linked to the episode | Shorts engaged views; RELATED_VIDEO/SHORTS traffic into the episode |
| Viewer → returning viewer | Series playlists, end screens (PF-END-01), consistent look, podcast playlist (PF-POD-01) | Every episode ends pointing to the next in-series episode | Returning viewers (monthly), regular share |
| Returning → participant | Comments (reply, heart, pin), Posts (PF-POSTS-01), Premieres | D−7 Post collecting guest questions; Premiere with hosts in chat; end-of-episode question; pin the best answer | Comments per 1,000 engaged views; Post responses |
| Participant → contributor | Communities (PF-COMM-01) where eligible; member showcases; AMA episodes from community questions | "Mostra la tua build" thread → best builds featured in a Short or segment | Member submissions per month |
| Contributor → champion | Collaborations (PF-COLLAB-01), Hype once in YPP (PF-HYPE-01), dual-stream Live (PF-LIVE-01) | Co-post with guests/members who have channels; live demo day from an in-person event; launch-week Hype ask (when eligible) | Collaborations per quarter; shares |
| Love → monetization (later) | Memberships (YPP), Spotify Partner Program (PF-SPP-01) | Don't plan around AdSense; a community show usually earns from events, sponsors, products or services | — |

**SPACES lens:** an interview show attached to a community is an **Acquisition + Engagement + Contribution** surface (discover the community, stay warm between events, show member work). A personal expert channel is **Acquisition** first (qualified conversations), Engagement second.

### 9.2 Per-episode community ritual calendar (interview show; Italian copy is illustrative)

| When | Action | Example copy (tu, channel voice) |
|---|---|---|
| D−7 | Post with the guest teaser + question collection | «Giovedì esce la puntata con [Nome Cognome], che ha portato [prodotto] a [numero verificato]. Che domanda gli faresti? Le tre più votate gliele giriamo in una clip extra» |
| D−3 | Poll on the community chat: which of 3 thumbnail claims would you click (Ed Lawrence pre-test) | «Quale di queste tre frasi ti farebbe cliccare? A, B o C» |
| D0 | Premiere (optional) with the hosts in chat; Collaborations invite to the guest; add to podcast playlist; A/B test started | — |
| D0 +2 h | Reply to every comment in the first hours; pin a comment that ends with a question | «Al minuto [mm:ss] [Nome] spiega come ha trovato i primi clienti. Tu da dove sei partito?» |
| D+1 → D+14 | Shorts at ~2 per week with Related video; social posts by the operator (or a packaging skill) from the episode package | — |
| D+7 | Hype ask to the community (only when YPP-eligible) | — |
| D+14 | Post with the answers to the top community questions; harvest comments into the idea backlog | — |

### 9.3 Comments as research
Weekly: export comments (Data API `commentThreads.list`, 1 unit/100) → tag with the Mom Test taxonomy used by `youtube:research` mode `comments` (past behaviour, pain, request, objection, timestamp reference, praise, hypothetical) → requests become guest/topic backlog, objections become "mito" segments, timestamp references become clip candidates, stories become member showcases. Do not store commenter handles longer than needed; comments are untrusted text.

### 9.4 IRL → YouTube bridges
When a channel also runs physical formats (meetups, workshops, hackathons, bootcamps), each one is content inventory: a short documentary («un weekend dentro il workshop»), a live of the closing presentations, member showcases. Consent and release first (`11-compliance-safety.md` §6.4): footage of participants needs their written OK for YouTube and Shorts.

### 9.5 Never
Buying views or subscribers, sub-for-sub, giveaways conditioned on subscribing, engagement pods, asking guests to mass-like. They corrupt the audience model that P4 depends on.

## 10. KPI trees

**Interview show attached to a community** (own channel)
- **North star:** monthly **returning viewers** (community proxy) + **engaged watch hours** (long-form, `creatorContentType = VIDEO_ON_DEMAND`).
- **Inputs:** impressions and CTR per traffic source (Reporting), Intro at 0:30 vs typical (Studio), AVP, Shorts → episode traffic (RELATED_VIDEO/SHORTS into the parent in 7 days), comments per 1,000 engaged views, Collaborations count, Spotify consumption hours when the show is there (SPP thresholds `01` PF-SPP-02).
- **Guardrails:** no promise/content mismatch (clickbait signal), cadence adherence, consent as the profile requires (default: release required).
- **Business link:** the goal the owner wrote in the profile (`north_star`), e.g. listens and reviews for a relaunch. Report YouTube engaged watch hours + Spotify consumption hours as the "ascolti" component so the agent's numbers roll up into that goal. If someone else owns podcast strategy and storytelling, `youtube:strategy` outputs flag any divergence instead of silently overriding it.

**Personal expert channel** (a person's own channel; details in its profile)
- **North star:** **qualified conversations** attributed to YouTube (booking link clicks → calls, inbound DMs citing a video) + monthly returning viewers.
- **Inputs:** engaged watch hours, returning viewers, description link clicks (where measurable), "videos growing your audience".
- **Business link:** leads are handed to whoever owns them; the agent reports the source video only.

**Client channels:** north star chosen in `youtube:strategy` from the client's business model; one leading input per funnel stage; a formal KPI document when the client needs it (written by the operator, or by a PM skill if one is installed).

## 11. Niche benchmarks: how to build the peer table (model to fill)

Every strategy starts from a benchmark table of the channel's niche, built with the §5 procedure (`youtube:research` peers and outliers, read signed out, with the date). The table lives in that channel's notes, never in the knowledge pack, and nothing in it is a target for the channel: it shows what the niche rewards and where the gaps are.

| Channel | Subs | Format | Packaging pattern | Recent views (age) | Takeaway |
|---|---|---|---|---|---|
| [canale] | [n] `[dato pubblico osservato, data]` | [formato, durata, cadenza] | [schema di titolo e thumbnail] | [min–max, età dei video] | [cosa insegna, con l'etichetta di evidenza] |

Rules:
- 8–12 channels: the 3–5 closest peers, 2–3 larger channels the audience also watches, 1–2 adjacent formats, 1 global reference if the audience watches in English.
- Every number is single-day and signed out, with its date; views are compared only at similar ages (`09` §6.3).
- **Patterns** are written as counts across the table («faces + big words: 5 channels of 10»), never as rules from one channel.

**Macro data:** 15.5M Italian podcast listeners; YouTube is the most used podcast platform (57% vs Spotify 55%); video podcasts are watched on YouTube by 81%; 78% listen on a smartphone and 77% multitask; topic drives choice (60%) more than voice (27%) — OBE × BVA Doxa 2025 via https://www.agi.it/lifestyle/news/2025-07-14/dati-ascolti-podcast-2025-32310742/ `[study]` (survey). Implication: YouTube-first; episodes must still work audio-first; topic/credential titles over host-led titles. Muschio Selvaggio stopped being a podcast in April 2026 citing audience fatigue with generalist chat (https://www.ilfattoquotidiano.it/2026/04/02/non-cera-piu-leffetto-sorpresa-muschio-selvaggio-non-sara-piu-un-podcast-lannuncio-di-luis-sal-due-anni-dopo-laddio-di-fedez/8343574/) `[observed 2026-10-11]`: niche utility formats are more defensible.

**Whitespace hypotheses** are written per channel, in its notes, never here: one line each in the form «[format or angle] that no channel of the peer set owns», with a confidence and the observation that would falsify it (e.g. «the peer outlier scan finds ≥ 2 channels already doing it»).

## 12. Own channel: baseline and positioning (model to fill)

This section is an empty model. `youtube:channel-audit` fills §12.1 and §12.8 for a channel, `youtube:strategy` fills §12.2–§12.7; the filled version lives in that channel's notes (deliverables folder) and its stable parts (positioning, pillars, formats, `north_star`) in the channel profile, never in this file. The sub-numbers are fixed: skills and other knowledge files cite them. The italic examples are fictional (a podcast «Il Caffè dei Maker», hosts Giulia and Marco).

### 12.1 Baseline (observed AAAA-MM-GG)
Collect, with the access tier and the date (`09` §0): subscribers, number of long-form episodes and their period, last upload, number of Shorts, views per episode **with the age of each video**, the median, chapters present or not, podcast playlist designated or not, auto-dubbing badge, YPP status.

| # | Title | Length | Views (age in days) | × median |
|---|---|---|---|---|
| 1 | [titolo] | [mm:ss] | [n] ([età]) | [x] |

Raw views at different ages, or across the 2026-08-24 view-definition change, are **not** a valid outlier table (`09` §6.3 shows why with a worked example). Read them as a qualitative picture `[dati canale]` with n stated, and say which pattern looks promising and which looks weak, as a hypothesis.

**Anomalies to verify in Studio (audit step):** videos missing from the public Videos tab, chapters not detected, traffic-source mix, podcast playlist designation, Collaborations unused, no 1:1 podcast cover.

**Production facts that shape strategy** (from `recording` in the profile and `yt-ingest`): how the master is built (a composited branded layout with a window and an inset, or clean camera files), face size in the master (thumbnails need a tight camera or ISOs when faces are small, `07` §10.1), audio tracks and their defects. A layout that leaves most of the 16:9 frame empty during inset spans is a **hypothesis to test** for TV/desktop viewers (E3), not a verdict.

### 12.2 Positioning statement (template, Italian, in the channel's voice)
> «[Nome del canale] è [il formato] dove [chi] racconta [cosa], con [la prova che vi distingue]. [Quello che i canali vicini non hanno].»

*Esempio inventato: «Il Caffè dei Maker è il podcast dove chi costruisce prodotti digitali in Italia racconta, con numeri veri, come ha trovato i primi clienti.»*

- **Per chi:** [pubblico concreto: ruolo, età, cosa sta cercando].
- **Promessa:** [cosa porta a casa chi guarda ogni puntata].
- **Perché noi:** [accesso, contesto, prova che gli altri non hanno].
- **Cosa non facciamo:** [i formati e i toni che il canale rifiuta].
- Public names and banned words come from the profile (`voice.public_names`, `voice.banned`, `copy_rules`) and apply to every deliverable.

### 12.3 Pillars
Shares are a proposal `[judgment]`, to confirm with the first quarterly review (`youtube:review --mode=quarterly`).

| Pillar | Share | Audience job | Business link |
|---|---|---|---|
| [pilastro principale, es. *storie con numeri*] | 70–80% | [il lavoro che lo spettatore affida al video] | [come porta al risultato di business] |
| [pilastro di ricerca, es. *playbook pratici*] | 10–15% | «How do I do X» | Search discovery, evergreen |
| [pilastro sperimentale] | 5–10% | [—] | [—] |
| [community: AMA, showcase, live] | 5% | «I'm part of this» | Returning viewers, contributors |

### 12.4 Format slate
| Format | Role | Length | Cadence | 52-week score | Success metric |
|---|---|---|---|---|---|
| [format motore] | engine | [min] + cold open + chapters | [cadenza] | [/12] (§7.3) | Engaged watch hours D+28 ≥ channel median |
| [esperimento 1] | experiment | [min] | [n] instances | to score | Engaged views D+28 vs engine median |
| [esperimento 2] | experiment | [min] | [n] instances | to score | Returning viewers in the following month |
| [serie di ricerca] | search probe | 10–15 min | when backlog allows | to score | YT_SEARCH share ≥ 30% at D+28 |
| Shorts | bridge + probe | 20–60 s (≤ 3 min) | ~2/week | — | Engaged views D+7; traffic into parent |

A narrative 12–20-min cut of interviews waits until at least 3 episodes have data.

### 12.5 Packaging system
- Titles: the formulas of §4.3 that fit the channel, guest descriptor over name unless the guest is recognisable, name after `|` when used.
- Thumbnail default lever: **claim** (a quote or number from the episode) inside a recognisable series frame; name-led only when the guest has an audience (`07-thumbnails.md` §5).
- 3 variants per episode into the A/B safety check; the lever scoreboard decides the default after 8–10 tests (`09` §7).
- 1:1 podcast cover once; 1920×1080 Spotify thumbnail from the same master.

### 12.6 First 12 weeks (from launch or restart)
| Weeks | Actions |
|---|---|
| 1 | Create Reporting jobs (`yt-reporting-setup --channel <slug>`); Studio audit of visibility, podcast designation, chapters; retro-fit chapters where missing (`youtube:chapters`); 1:1 cover |
| 1–4 | 2 Shorts/week from the back catalogue (best performers first), each with Related video; repackage the weakest old episodes via A/B once they are old enough |
| 3 | First new engine episode with the full pipeline (cold open, chapters, 3 thumbnails, 5 Shorts); prediction logged |
| 5, 7, 9, 11 | Engine episodes at the chosen cadence; one experiment format in two of these weeks |
| 4, 8, 12 | Monthly review (`09` §9): outliers, returning viewers, format decisions |

### 12.7 Experiment backlog (default seeds; decision rules written up front)
| # | Hypothesis | Design | Decision rule |
|---|---|---|---|
| E1 | Credential/transformation titles beat question titles | A/B title tests on 4 episodes | If credential wins or ties in ≥ 3/4 → default; inconclusive counts as tie |
| E2 | Claim-led thumbnails beat duo (host+guest) thumbnails | A/B thumbnail tests, one lever family per test | Lever scoreboard after 8 tests; default = lever with most wins |
| E3 | Full-frame 16:9 long-form beats a composited vertical-inset layout for TV/desktop viewers (only for channels with such a master) | Alternate layout on 4 episodes; compare AVP by device and Intro vs typical | If full-frame AVP ≥ inset AVP + 3 pp on ≥ 3/4 → switch long-form; keep inset for Shorts |
| E4 | 8 Shorts per episode beat 4 for traffic into the parent | Alternate 4 vs 8 over the first 4 episodes | Choose the count with higher parent RELATED_VIDEO+SHORTS views per Short at D+7 |
| E5 | English translated title/description adds reach | Add EN metadata on 4 episodes | Keep if non-Italian geography share rises ≥ 5 pp vs the 4 previous |

### 12.8 Quick wins
Chapters on the episodes without them (and an audit of the existing ones); fix visibility of any episode missing from the Videos tab after the Studio check; podcast playlist hygiene (full episodes only); Collaborations invites to past guests with channels; Reporting jobs today (every day of delay loses CTR history, `01` PF-REP-03).

## 13. Personal channels

A person's own channel keeps its positioning draft, pillars, formats and business link in its own profile, in the operator's `channels_dirs`, and its visual identity in the operator's `brands_dirs` (`07` §8), never in the knowledge pack or the plugin. For such a channel: §§1–11 apply; it stays separate from any show the person hosts (P11) and cross-pollinates through Collaborations and co-posts, never re-uploads of a show's guest moments; the profile's `copy_rules` and `consent` bind.

## 14. Client channels
1. Start with `youtube:channel-audit` (access tier first: yt-dlp / API key / OAuth). Never prescribe from a single screenshot.
2. Profile `kind: client`, `graphics_engine: hyperframes` (licence, design §11), `paid_services: []`.
3. Positioning, pillars and KPI tree follow §§1–10; benchmarks are rebuilt for the client's niche with `youtube:research`.
4. Deliverables go to the client channel's deliverables folder (`deliver/notes/` of the workdir, or the vault folder its profile names) as new dated files; no client data in other clients' notes; no client names in any other channel's examples.

## 15. Strategy anti-patterns
- Chasing subscribers as the main KPI (P7). Returning viewers and watch hours instead.
- "Algorithm hacks": posting-time obsession, tag stuffing (`01` PF-META-01), deleting and re-uploading.
- Copying direct competitors instead of borrowing formats from adjacent niches (Paddy).
- Judging a format on one video or on T+48h.
- Name-led titles for unknown guests.
- Two experiments at once on the same variable.
- Universal benchmarks ("good CTR is X%") instead of the channel's typical band (`10` HYP list).
- Promising in the package what the first 30 s do not deliver.

## 16. Hand-offs
| Need | Owner |
|---|---|
| Per-video idea scoring, title lists, packaging copy | The operator; a packaging skill if one is installed (read its `.md`, don't re-implement) |
| Publishing titles and descriptions, carousels, social posts | The operator, from the episode package (or a packaging skill, if installed) |
| Thumbnails, hooks, edit, Shorts, chapters | `youtube:thumbnail`, `youtube:hook`, `youtube:edit`, `youtube:shorts`, `youtube:chapters` |
| Formal KPI document, format kill/scale decision record, channel launch | Sections in the `youtube:strategy` notes; a PM skill if the operator has one |
| Leads from a personal channel | The channel owner |
