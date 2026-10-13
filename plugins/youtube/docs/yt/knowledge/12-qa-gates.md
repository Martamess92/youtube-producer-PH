# 12 — QA gates: per-deliverable checks, the critic sub-agent, loop limits

> **How the skills use this file**
> 1. Every production skill (`youtube:edit`, `youtube:shorts`, `youtube:thumbnail`, `youtube:hook`, `youtube:chapters`) runs its section here (§2–§6) before presenting work at G1/G2 or delivering it.
> 2. Every note-writing skill (vault or `deliver/notes/`) (`youtube:channel-audit`, `youtube:strategy`, `youtube:research`, `youtube:review`, `youtube:story`) runs §7 before saving.
> 3. The agent spawns the critic with the brief in §8 and merges its ranked output into `<workdir>/qa/report.md` (§10.4).
> 4. §9 caps self-evaluation, critic runs and re-renders; §10 holds the G1/G2 briefs and the G3 checklist the agent hands to the operator.
> 5. Thresholds are owned by the files they cite (05, 06, 04, 07, 08, 11); this file collects them as checks and never relaxes them. A channel may hold a **stricter** learned value for a check (13-learning-loop.md §2.2): the skill applies it on top of this file, never a looser one.
> 6. Every return of the agent runs the learning gate (§11): «Passo 5 — Impara» done, learned items inside the hard rules, recommendations from priors with n and confidence.

Verified 2026-10-11 (design §2 #8, §8, §12; research SYNTHESIS §6.7/§7, V1 K1 video-use rules, F1 K-15/K-23/K-27, F2 §5/§11). Checks in English; briefs, reports and critic findings in Italian.

---

## 0. Gate map

| Stage | Automated / agent gates | Human gate |
|---|---|---|
| Ingest, transcript, speakers | E0–E2 (§2) | — |
| Story, cold open, EDL | E3 (§2), hook gates (§5), consent check per profile (11-compliance-safety.md §6.4) | **G1** before any cut |
| Long-form render, audio, graphics, captions, encode, NLE file | E4–E9 (§2), critic (§8) | — |
| Chapters | C1–C6 (§6) | (with the delivery) |
| Shorts candidates / thumbnails candidates | S-pre (§3), T-pre (§4) | **G2** before final renders |
| Shorts renders / thumbnail finals | S-post (§3), T-post (§4), critic | — |
| Publication | G3 checklist (§10.3) | **G3** always manual, by the operator |
| Notes (vault or `deliver/notes/`) | V1–V12 (§7), critic for audits and strategy | The operator reviews the draft |
| Every return (gate stops, partial and blocked jobs included) | L1–L10 (§11) | Improvement proposals become a PR only with the operator's OK; humans merge |

All findings and ticks go to `<workdir>/qa/report.md` (design §8.1); cut-point images to `<workdir>/qa/timeline_view/*.png`.

---

## 1. Severity scale

| Sev | Meaning | Examples | Delivery rule |
|---|---|---|---|
| **S0** blocker | Must never ship: legal, rights, truthfulness, safety or platform-policy breach, or a file that doesn't work | Invented or unverifiable quote/number on screen; guest pixels altered; release missing where the profile requires one; anything in 11-compliance-safety.md §0; secrets in a file; master that doesn't decode; wrong channel's brand | Stop. Report. Do not present as deliverable |
| **S1** major | A spec miss or a defect a normal viewer notices | Loudness outside tolerance; true peak above −1.5 dBTP; cut inside a word; audible click; captions >200 ms off; chapters that YouTube would reject; text clipped or under UI; rubric zero-tolerance item at 0; chosen hook below 75; source/output timeline confusion | Fix before delivery; if still failing after the loop limit (§9), escalate with options |
| **S2** minor | Noticed by a careful viewer; doesn't break the experience | Caption line 43–46 chars; one cue at 18–20 cps; lower third 0.5 s late; slightly soft cutout edge; weak chapter wording | Fix if cheap; otherwise list in the brief |
| **S3** nit | Preference or polish | Alternative font size, alternative word | List only |

A finding without evidence (frame path, timestamp, measured value, quoted line) is "non verificato" and can never be ranked above S2.

---

## 2. Long-form edit (`youtube:edit`)

### E0 — Ingest (`yt-ingest`)

- [ ] `analysis/inventory.json` exists; `corrupt_spans` listed with timestamps (they are excluded from cuts or flagged in the G1 brief).
- [ ] AAC decoder decision read (`inventory.json` `audio_decode.decision` + `decision_reason`, `05` §11): `native` expected in most cases (errors that sit next to a corrupt span are ~0.5 s of silence, listened to before use); `aac_at` only with a stated reason (peaks above 0 dBFS clipped flat). No `wav_decoder_mismatch`; `wav_delta_ms` = 0.
- [ ] L/R balance, integrated loudness and true peak reported (composited podcast masters often show a varying L/R imbalance, ~−11 LUFS and peaks >0 dBFS).
- [ ] HDR/log flag known (profile `recording.video`).
- [ ] `yt-doctor` green for the binaries this run needs; ≥60 GB free disk.

### E1 — Transcript (`yt-transcribe`)

- [ ] Every glossary term (guest, company, products from `<slug>.glossary.txt` + `glossary_extra`) appears spelled correctly wherever spoken (the names in P1 first).
- [ ] Three random 1-minute excerpts read for nonsense tokens, language switches and missing passages; copied into the G1 brief for the operator's ear check.
- [ ] Discourse markers flagged, not auto-cut (06-captions-italian.md).

### E2 — Speakers (`yt-speakers`)

- [ ] `speakers` map in `project.json` uses public names (hosts as in the profile's `voice.public_names.hosts`, guest).
- [ ] Overlaps marked; on the first episode of a channel, DER against a hand-labelled 5-min sample recorded in MEMORY.md.

### E3 — EDL before G1

- [ ] Plain-Italian strategy summary (≤10 lines): what goes, what stays, target duration.
- [ ] Every segment `in`/`out` snapped to word boundaries; padding 30–200 ms (50 ms before / 80 ms after as default); silence ≥400 ms preferred, 150–400 ms only with a visual check, <150 ms never.
- [ ] Laughs kept and extended (the laugh is the beat); speaker hand-offs breathe ~400–600 ms.
- [ ] Removed sections listed with reason and seconds saved (pre-roll, re-asked questions, tangents, pauses >0.8 s tightened to ~0.35 s).
- [ ] Cold-open choice from §5 attached; thumbnail `payoff_at` values fall inside it (07-thumbnails.md P2).
- [ ] Claim ledger: every on-screen or cold-open claim verbatim or faithful, qualifiers preserved, results separated from targets/estimates.
- [ ] Consent as the profile requires (11 §6.4): with `release_required: true` (the default) release confirmed and its scope known, otherwise S0, stop; with `false`, the written decision is in `consent.rule`.

### E4 — Assembly render (after G1; `yt-edl-render`)

- [ ] Iterate with `--preset proxy` or `1080p`; `master4k` only after E4–E7 pass on the proxy (§9).
- [ ] Duration of `edit/assembled.mov` = Σ segment durations ±100 ms; `assembled.timeline.json` covers every segment with `out_start`, `out_end`, `src`, `src_in`.
- [ ] `yt-timeline-view <workdir> --at <cut> --window 3 --source edit` for **every** cut (±1.5 s), plus the first and last 2 s: no flash frame, no half-word, no waveform discontinuity, no layout glitch in a composited canvas.
- [ ] A/V duration difference ≤100 ms.

### E5 — Audio (`yt-loudnorm`, measured on the encoded file)

- [ ] Integrated −14 ±0.5 LUFS; true peak ≤ −1.5 dBTP; LRA ≤11 (community-observed YouTube target, not official; −16 LUFS / −1 dBTP only for an audio-only RSS master).
- [ ] L/R within 1 dB after rebalance, or folded to mono.
- [ ] 30 ms fades at every boundary: no clicks at cut points (check waveform in the timeline views).
- [ ] Music ducked under speech (EDL `gain_db` ≈ −20, `duck: true`); music licence covers every target platform (11 §5).

### E6 — Graphics (Remotion for own and personal channels within the licence, HyperFrames otherwise)

- [ ] Guest lower third once, after the hook; name ~50–80 px tall at 1080p equivalent, role about half; inside title-safe ≥5% (template 6%); held still while read.
- [ ] Overlay first and last frames empty; alpha verified by decoding a mid-hold frame (ProRes 4444 `yuva444p10le` or VP9 `yuva420p` with `alpha_mode=1`).
- [ ] Fonts loaded (assertion in the composition); accents render.
- [ ] Chapter cards titled as curiosity gaps, matching `chapters.txt` wording.
- [ ] End screen: last 5–20 s, video ≥25 s, ≤4 elements, brand in the left third and the right two thirds quiet (https://support.google.com/youtube/answer/6388789, verified 2026-10-11).
- [ ] Graphics engine matches the channel (`graphics_engine` in the profile); no Remotion project handed to a client.

### E7 — Sidecar captions (`yt-captions --timeline edit/assembled.timeline.json --format srt|vtt`)

- [ ] Timed on the **output** timeline; cues monotonic and non-overlapping.
- [ ] ≤42 characters per line, ≤2 lines, ≤17 characters per second, cue duration within the 06-captions-italian.md bounds.
- [ ] Glossary spellings, accents (È, not E'), numbers as spoken.
- [ ] Three random cues checked against picture with `yt-timeline-view`.

### E8 — Encode and delivery files

- [ ] ffprobe: resolution as planned (3840×2160 or 1920×1080); fps = source; `hevc` Main10 tagged `hvc1` or `h264` High; BT.709 primaries/transfer; AAC 48 kHz stereo; `+faststart` (moov before mdat); bitrate inside the range calibrated on the first episode.
- [ ] Names: `deliver/<slug>-master.mp4`, `<slug>.it.srt`, `<slug>.it.vtt`, `chapters.txt`, `<slug>.fcpxml`.
- [ ] Final encode by ffmpeg/VideoToolbox, never auto-editor (licence gates downscale 4K silently).

### E9 — NLE hand-off (`yt-export-nle <workdir> --format fcpxml`)

- [ ] Well-formed XML (`xmllint --noout`).
- [ ] Every referenced media path is absolute and exists.
- [ ] Timeline duration = assembled duration ±1 frame; frame rate matches.
- [ ] Opening the file in Final Cut / Resolve / Kdenlive is the operator's check, listed in the delivery note (not claimed by the agent).

---

## 3. Shorts (`youtube:shorts`, rules in 08-shorts-clip-engine.md)

### S-pre — before G2

- [ ] `shorts/scores.json` matches the contract schema; every entry has four subscores, `in`, `out`, `hook_text`, `why` with version tag.
- [ ] Score distribution sane: ≤25% of windows at ≥70; if no window ≥60, the brief says so (no padding).
- [ ] Each candidate: score ≥60, `hook` ≥7, `standalone` ≥6, length inside a band, needs-proof resolved.
- [ ] Opening line free of dangling openers (08 §6.2); no meaning-changing splice.
- [ ] Dedupe applied: temporal overlap >50% and duplicate promises removed.
- [ ] `hook_text` ≤10 words, concrete, aligned with the spoken first line, free of bait phrases and banned words.
- [ ] Crop preview still per candidate: no PiP, no rounded-corner gradient, head-room 5–25%, primary crop upscale ≤×1.25.
- [ ] Episode timestamp mapped through `assembled.timeline.json`; moments cut from the long-form flagged.

### S-post — each `short_NN.mp4`

- [ ] QA frames at 1.0 s and midpoint (plus last 0.5 s) read; the 08 §10 table fully ticked.
- [ ] −14 ±1 LUFS, TP ≤ −1.5 dBTP; 1080×1920; H.264 High; AAC 48 kHz; faststart; ≤180 s.
- [ ] Captions: 2–3-word chunks, no chunk ending on an article/preposition, no cue <0.35 s, accents correct, never over the face.
- [ ] Hook overlay 0–3 s in the safe zone; single accent per composition.

---

## 4. Thumbnails (`youtube:thumbnail`, rules in 07-thumbnails.md)

Thresholds are owned by 07-thumbnails.md (v2: §5.3 hooks, §10.1 cap, §11.2 policy ladder with level 2b, §12.4 pre-checks, §13.3 cold reader, §15 tests; `duo` as the default frame with its 3–4-word headline at ≥ 20 % per line, dark-feed separation, accent-circle contrast).

### T-pre — before G2

- [ ] `thumbs/concepts.json` matches the v2 contract (07 §1.1): 3 concepts on 3 different **hypotheses** and on ≥ 2 levers (07 §5.2); `hook` 3–6 words and a complete statement (a noun fragment or < 3 words is S1; > 6 words is S2; on `duo` > 4 words is S1 without a written `hook_size_reason`); one `keyword` inside the hook; one `accent` (or `auto`); `people` with public `name` and `title` (the duo's host as a small `host_tag`, «con <host>», public name as in the profile); `meta_line` items verified (fewer items are fine); `guest_style` and `grade` allowed by the profile (default `natural`; `mono` = level 2b); `expression_class` set when a face is used; `payoff_at` inside the cold open; `title_pair` set.
- [ ] Title-pairing test passed or overridden in writing (07 §5.4).
- [ ] Cold read done (07 §13.3): one fresh `youtube:thumb-cold-reader` per concept with only the 168-px and 720-px files; ≥ 2 of 3 concepts read correctly (score 2), or the failing concept rewritten once, re-read, then dropped or flagged.
- [ ] Sources: priority respected (tight camera ISO → camera ISO → master inset → guest photos, 07 §10.1); expression class fits the lever (07 §5.5); hard rejects applied; face within the display cap (2.0× effective at 1280, or 1.5× with the option-b flag), interpolation only; if no source reaches the face floor, the brief asks for the tight camera and for a written `face_floor_reason`.
- [ ] Cutouts: only operations of the declared policy level (07 §11.2, including 2b: one monochrome curve on the whole photo, nothing local on faces, no vignette or grain over the people); preservation flicker-compare done; no matte hole in the face box.
- [ ] Render pre-checks passed (07 §12.4), the render exited 0: no-go zones, line heights (every hook line ≥ 12 %, keyword ≥ 18 % when set larger than the phrase; a warning in the one-size v2 headline), ≤ 3 lines, no text over faces, whitelist pairs, crop edges, display cap, served-size detail ≥ 569 (S2 below 713), claim face ≥ 35 % (S2 below 40 %), duo faces ≥ 30 % with guest ≥ host, face–surround ΔL* ≥ 10 (S2 below 20), `face_pixels_unchanged` = 0 at levels 0–1, skin ΔE00 within mean 2.5 / p95 5 at level 2 (skipped **only** with `grade: mono`), level 2b with `grade: mono` (same curve signature on people and plate, mapping ≤ 2 levels, landmarks ≤ 4 %; S1 otherwise), `duo` every hook line ≥ 20 % (S1 below without `hook_size_reason`), accent circle ↔ adjacent hair/face ΔL* ≥ 10 (S2 below 20), one accent, logo ≥ 140 px at 4K (wordmark readable at 360), fonts loaded.
- [ ] QA sheet (dark row, light row with the **216-px** sidebar tile, served chain) and grid mock (dark + light) read; `yt-thumb-qa` checks exit 0 on the candidates, including `hook_words`, `grade_uniform` / `grade_face` / `grade_mono` / `grade_landmarks` on mono renders (S1 on error), `circle_contrast` (S1 below 10, S2 below 20), `edge_dL_dark` (S2: below 25 without a light frame element); metrics missing from the toolkit written «non misurato»; rubric filled for every render; ship rule: ≥ 15/20, no 0 on items 1/2/6/9, no hard fail.
- [ ] ≤ 12 renders before G2.
- [ ] Prop requests (if any): text only, no person, no text in the image, inside the €5/episode and €20/month caps; a local placeholder renders meanwhile (07 §17).

### T-post — after G2

- [ ] Masters 3840×2160 PNG + JPEG <2 MB; no arm below 1280×720.
- [ ] Derivatives: Spotify 1920×1080; 1:1 show cover only if requested; vertical covers if needed.
- [ ] Test plan complete (07 §15): native A/B as a package safety check on a new episode (order: highest rubric first, title locked, hypothesis, start and check dates, impressions recorded); single variables only through a pre-test kit (`docs/yt/templates/pre-test-protocollo.md`: one variable, hypothesis and decision rule written first, guest's one-line OK).
- [ ] Any generative help used came from the main session with the operator's approval, touched no person and stayed inside the props caps (S0 otherwise).

---

## 5. Hooks and cold opens (`youtube:hook`, rubric in 04-hooks-first-30s.md)

### H — Hook Lab (solo videos)

- [ ] 10 hooks across ≥5 families.
- [ ] Each scored with the 04 rubric (criteria C1–C9, verdict = 25 × (0.6·mean + 0.4·min)); the chosen hook scores ≥75 and passes every 04 gate.
- [ ] First line confirms the click (matches title and thumbnail promise); no greeting, channel intro or subscribe ask; Italian time budget from the channel's measured wpm respected.
- [ ] Triple alignment: spoken line, picture and on-screen text make the same promise.
- [ ] Voice: the profile's register, banned words and `copy_rules` on on-screen text.
- [ ] The rubric is a quality floor, not a predictor: the brief never promises performance from a score.

### CO — Podcast cold open

- [ ] 3 alternative variants (ready for YouTube's announced 3-cut hook test).
- [ ] Each: 2–4 clips cut before resolution, 20–45 s total, followed by a ≤3 s sting (or none) and the host's Promise → Proof → Plan line; first story beat by ~1:30.
- [ ] Every clip has source `in`/`out` snapped to words; claims verbatim with qualifiers; no splice that changes meaning.
- [ ] At least the recommended variant contains every `payoff_at` of the thumbnails proposed for the A/B test.
- [ ] Verdict ≥75 on the recommended variant.

---

## 6. Chapters (`youtube:chapters`, `yt-chapters <workdir> --draft edit/chapters.draft.json [--timeline …]`)

| # | Check | Severity if failed |
|---|---|---|
| C1 | First chapter at 0:00; ≥3 chapters; each ≥10 s (https://support.google.com/youtube/answer/9884579, verified 2026-10-11) | S1 (YouTube ignores the chapters) |
| C2 | Timestamps on the **output** timeline (mapped through `assembled.timeline.json`); for retro-fits of published episodes, the published file's duration matches the Data API duration ±1 s before trusting source times | S1 |
| C3 | Strictly ascending, unique, each snapped to a silence within ±1.5 s of the topic change | S1 / S2 |
| C4 | Podcast: 6–12 chapters for a ~50-min episode; the first chapter covers the cold open | S2 |
| C5 | Titles: Italian, keyword-first, ≤45 characters, no ALL CAPS, no "Ep.", no trailing period, no bait, no banned words, true to the segment (read the first 30 s of each chapter's transcript) | S2 (S1 if misleading) |
| C6 | Format `m:ss Titolo` (`h:mm:ss` from 1 h), one per line in `deliver/chapters.txt`, ready to paste into the description | S1 |

---

## 7. Note deliverables (audits, strategy, research, reviews, episode packages, story/script notes)

| # | Check |
|---|---|
| V1 | Path: per `deliverables_mode` — `workdir` (default): `<workdir>/deliver/notes/` (for work without a video, `<studio_dir>/work/<slug>/deliver/notes/`); `vault`: the folder the profile names in `vault.deliverables`; **new** file named `{YYYY-MM-DD} — {Titolo}.md`; never overwrites; never inside the plugin repo |
| V2 | Frontmatter: `tags` (`deliverable`, the channel slug, `youtube`, `yt-<skill>`), `created`, `updated`, `channel`, `skill: /youtube:<skill>`, `status: draft` (agent file §4.2) |
| V3 | H1 `# Titolo — Descrizione` (em dash); Italian throughout; "Link correlati" only to notes actually read (wikilinks when the note lives in a vault) |
| V4 | Every number traceable to script output (`yt.db` table + query date, or tool JSON); every video ID re-verified; no number typed from memory (trust rule) |
| V5 | Every recommendation carries an evidence label from 10-evidence-ledger.md; one taken from a learned prior also carries `[appreso: scelte|esiti, n=…, conf. …]` (13-learning-loop.md §11) |
| V6 | Derived metrics labelled «calcolato da noi, non è un dato YouTube» and allowed only once the derived-metrics amendment is accepted (11 §4.4); competitor comparisons without rivalry framing |
| V7 | Small-data rules: same-age comparisons; no conclusion from <4 videos; no universal % targets; inconclusive results reported as such |
| V8 | Audits: exactly one primary constraint + two secondary, each with evidence |
| V9 | Experiments: hypothesis, metric, duration and decision rule written **before** the experiment |
| V10 | Nothing from the do-not-encode list; no commenter handles; no confidential client data; no leaked-document quotes |
| V11 | Voice: the profile's register, banned words, public names and `copy_rules` |
| V12 | Scope: no idea scoring and no final publishing copy (titles, descriptions, social posts belong to the operator or a packaging skill): hand over inputs instead; every section ends with concrete next steps |

---

## 8. Critic sub-agent

### 8.1 When

- Once per deliverable, before it is presented at G1/G2 or delivered: long-form master, the set of Shorts, the thumbnail set, the cold-open set, chapters, and every audit or strategy note.
- The thumbnail **cold reader** (`agents/thumb-cold-reader.md`, 07 §13.3) is not the critic: it sees only two tiles per concept and says what the video promises. The critic does not receive its scores.
- One confirmation re-check, limited to the issues it raised, after fixes. Never a third run (§9).

### 8.2 How it is spawned and what it gets

Spawned with the Agent tool as a fresh sub-agent with a self-contained brief. It receives:

- the deliverable paths and the QA artifacts (`qa/timeline_view/*.png`, `thumbs/qa/*`, `shorts/qa/*`, ebur128 and ffprobe outputs);
- the spec references: this file's section for the deliverable, plus the owning knowledge file sections (05, 06, 04, 07, 08, 11);
- `project.json` and the channel profile `<slug>.md` (from the operator's `channels_dirs`);
- for notes (vault or `deliver/notes/`): the draft note and the data it cites.

It does **not** receive the agent's reasoning, self-scores or rubric totals (an independent judge must not be anchored by the author's verdict).

Permissions: read-only. It may run probes (ffprobe, `ebur128` through ffmpeg-full by absolute path, `xmllint`) and write QA frames only into `qa/`. No edits to deliverables, no renders, no network, no paid tools, no note or vault writes.

### 8.3 What it checks

1. Every gate of the deliverable's section (§2–§7), ticking or failing each with evidence.
2. 11-compliance-safety.md §0 (any breach = S0).
3. Truthfulness: each on-screen quote and number against `transcript.words.json` timestamps or the cited data.
4. Brand and voice: tokens, whitelist pairs, one-accent rule, banned words, public names.
5. Cross-deliverable consistency: thumbnail `payoff_at` inside the cold open; chapter titles = chapter cards; Short episode timestamps on the output timeline.
6. Scope: publishing copy and idea scoring left to the operator (or a packaging skill), not written as final by the agent.
7. Learned defaults (§11): a choice the brief attributes to a prior carries n, confidence and signal; nothing learned breaks a hard rule or loosens a threshold. The critic gets the brief's «Dall'apprendimento» line, not the priors' internals.

### 8.4 Output format (Italian findings, fixed keys)

```json
{"deliverable": "edit|shorts|thumbnail|hook|chapters|vault",
 "verdict": "ship|fix|block",
 "issues": [{"id": "C01", "sev": "S0|S1|S2|S3",
             "where": "deliver/ep12-sara-master.mp4 @ 00:12:31.4 | thumbs/renders/ep12-sara_A1.png | nota §3",
             "rule": "12-qa-gates §2 E5 | 11-compliance-safety §0 #5 | 07-thumbnails §14 item 9",
             "evidence": "ebur128: I = -12.8 LUFS, TP = -0.6 dBTP",
             "fix": "rifare yt-loudnorm con --target -14 --tp -1.5 sul mix"}],
 "checked": ["E4", "E5", "E6"],
 "not_checked": [{"gate": "E9", "why": "fcpxml non ancora generato"}]}
```

Followed by a markdown table with the same issues, ranked.

**Ranking**: severity first (S0 → S3). Within a severity: (1) issues in the first 30 s, the hook, the thumbnail glance or the first frame of a Short; (2) issues present across the whole piece (audio, captions, brand); (3) issues confined to one moment. Ties: earlier timestamp first.

**Verdict**: any S0 → `block`; any S1 → `fix`; only S2/S3 → `ship` (S2 listed in the brief). List every S0 and S1, the top 10 S2, and summarise S3 in one line.

### 8.5 Brief template (sent by the agent; English prompt, Italian output)

```
You are the independent QA critic for the YouTube Producer. You did not make this work and you have
no stake in it. Read-only: you may run ffprobe, ffmpeg-full ebur128 and xmllint, and extract QA frames
into <workdir>/qa/ only. Do not edit, render, browse the web or call paid tools.

Deliverable: <type> — files: <paths>
Specs to enforce: <plugin_root>/docs/yt/knowledge/12-qa-gates.md §<n>; <owning files and sections>;
11-compliance-safety.md §0. Context: <workdir>/project.json; <absolute path of the channel profile <slug>.md>.
(The agent writes absolute paths here: plugin_root from yt-config, the profile from its channels_dirs.)
QA artifacts: <paths>.

Check every gate in the cited sections. For each issue give severity S0–S3 per 12-qa-gates.md §1,
location, rule reference, measured evidence and a concrete fix. An issue without evidence is
"non verificato" and at most S2. Rank per §8.4. Write findings in Italian. Return only the JSON
object followed by the ranked markdown table.
```

### 8.6 After the critic

The agent fixes S0/S1 (or stops on S0 that need the operator: rights, consent, truth), runs the confirmation re-check on those issue IDs only, and merges both outputs into `qa/report.md`. Disagreeing with the critic is allowed only with evidence written next to the issue; the disagreement goes into the G1/G2 brief for the operator to settle.

---

## 9. Self-evaluation loop limits

| Limit | Value | Source / reason |
|---|---|---|
| Self-eval passes per deliverable | ≤3 (check → fix → re-render/rewrite → re-check) | video-use rule (MIT) |
| Critic runs | 1 + 1 confirmation re-check on raised issues only | Avoid endless loops and judge drift |
| Long-form 4K master encodes | ≤2 per episode (`hevc_videotoolbox` 4K ≈24 min per pass on an M5); iterate on `--preset proxy`/`1080p` | SYNTHESIS N11 benchmarks |
| Short re-renders | ≤2 per clip after G2 | — |
| Thumbnail tweak rounds | ≤2 before G2 (≤12 renders total), ≤1 after G2 | — |
| Same root cause failing twice | Stop patching; diagnose (wrong timeline, bad source, wrong preset) and report | — |
| Long renders | Background Bash with a completion check; the workdir is the resumable state | Design §4 |

Rules:

- Never relax a threshold, edit a rubric or edit this file to make a gate pass. Learning follows the same rule: a learned threshold can only be stricter (13-learning-loop.md §2.2), and a change to this file arrives only through a reviewed PR.
- The agent's own rubric scores are provisional; The operator decides at G1/G2 (or delegates them explicitly, agent Passo 4.1). Truthfulness items are never scored 2 without the timestamp written next to them.
- When a limit is reached with S1 still open, return `stato: bloccato` with the open issues, what was tried, and 2–3 options for the operator (e.g. accept S2-equivalent, provide a new source, change scope).
- Every stop at a gate returns `stato: in attesa di approvazione G1` or `stato: in attesa di approvazione G2` with the brief (§10).

---

## 10. Gate briefs and the QA report

### 10.1 G1 brief (Italian, returned to the main session)

```
## G1 — Approvazione prima del taglio
Episodio: <slug> · Canale: <slug> · Consenso: <liberatoria sì, copre … | non richiesta (decisione scritta nel profilo) | nessun ospite (dichiarato dall'operatore) | no → bloccato>
Strategia (≤10 righe): …
Cold open: consigliato V1 Scala (verdetto 82, 34 s) · V2 Una frase (78, 41 s) · V3 Il numero (75, 27 s) — perché V1
Tagli proposti: | in–out sorgente | motivo | secondi risparmiati |
Durata stimata: 47:30 · Trascrizione: 3 estratti da ascoltare (link ai minuti)
Rischi e segnalazioni: …
Dall'apprendimento: default applicati da priori e lezioni (n, confidenza, segnale), soglie apprese più severe, esplorazione — oppure «nessuno» (§11, 13-learning-loop.md)
Decisioni richieste: 1) cold open  2) tagli  3) …  (oppure «G1 delegato»)
stato: in attesa di approvazione G1
```

### 10.2 G2 brief

```
## G2 — Approvazione prima dei render finali
Thumbnail: | id | leva | ipotesi | gancio | classe | volto % | dettaglio @720 | guest_style / grade | lettura a freddo | rubrica /20 | note | + percorsi dei fogli QA e del mock griglia
Proposta di test: controllo di sicurezza A/B <variante 1 (caricata per prima)> vs <variante 2>, ipotesi, durata · pre-test facoltativo: variabile, n, soglia
Shorts: tabella di 08-shorts-clip-engine §11.3 + still di anteprima del crop
Richieste a pagamento (se servono): blocco di 11-compliance-safety §10
Dall'apprendimento: concept e candidate scelti da priori (n, confidenza, segnale), il braccio di esplorazione e perché, soglie apprese più severe — oppure «nessuno»
Decisioni richieste: quali thumbnail nel test, quali 3–5 Shorts e in che ordine
stato: in attesa di approvazione G2
```

### 10.3 G3 checklist (the operator publishes; the agent never does)

- [ ] Carica `<slug>-master.mp4`; titolo dal set approvato; descrizione con `chapters.txt` incollato.
- [ ] Carica `<slug>.it.srt` come sottotitoli italiani.
- [ ] Test A/B (controllo di sicurezza del pacchetto, su episodio nuovo): thumbnail nell'ordine indicato, titolo invariato fino alla fine del test; a fine test segna esito e impressioni del periodo.
- [ ] Pre-test (se approvato): OK di una riga dell'ospite prima di caricare le copertine su Prolific o PickFu (`docs/yt/templates/pre-test-protocollo.md`).
- [ ] Episodio completo nella playlist podcast; Shorts **mai** in quella playlist.
- [ ] Invita l'ospite come collaboratore (se ha un pubblico).
- [ ] Schermata finale sugli ultimi 5–20 s.
- [ ] Toggle contenuti alterati/sintetici solo se hai usato AI realistica sul tuo volto nel video.
- [ ] Spotify for Creators: versione video con almeno un'interruzione pubblicitaria.
- [ ] Shorts programmati ~2 a settimana, ciascuno con "Video correlato" → episodio completo.
- [ ] Dopo la pubblicazione: mandami l'ID del video per la review a T+48h.

### 10.4 `qa/report.md` structure

```
# QA — <slug> (<YYYY-MM-DD>)
## Sommario            gates superati / falliti, verdetto del critic
## Gate                tabella per sezione (E0–E9, S-pre/S-post, T-pre/T-post, H/CO, C1–C6)
## Critic              JSON + tabella ordinata (prima esecuzione e ricontrollo)
## Compliance          pre-flight di 11-compliance-safety §14
## Segnalazioni di sicurezza   testi sospetti citati (≤15 parole) con fonte
## Note per l'operatore      decisioni aperte, limiti raggiunti, opzioni
```

---

## 11. Learning gate (every return; 13-learning-loop.md)

Checked by the agent before the return block, and by the critic when the deliverable cites a learned prior. Severity per §1.

| # | Check | Severity if failed |
|---|---|---|
| L1 | «Passo 5 — Impara» ran: `yt-learn ingest` and `yt-learn job` for every workdir touched, gate stops, partial and blocked jobs included; or the block says «apprendimento: non registrato — <motivo>» | S2 (the deliverable still ships) |
| L2 | The return block has the `apprendimento:` block with every line filled («nessuna» / «niente» when empty) | S2 |
| L3 | No learned item breaks a hard rule (13 §2): guest-face policy, consent, paid calls, uploads, publication and gates, public names and banned words, crop edges, evidence rules, channel isolation | **S0** |
| L4 | Learned thresholds only tighten: no check moved from error to warning, no value loosened, no check skipped because of a lesson | **S0** if a looser value shipped; S1 if only proposed outside a PR |
| L5 | Every recommendation from a prior carries n, confidence and signal (`[appreso: scelte|esiti, n=…, conf. …]`); «bassa» never changes a default; `esiti` lessons rest on ≥ 4 comparable videos; derived figures keep «calcolato da noi, non è un dato YouTube» and the amendment gate (11 §4.4) | S1 (S0 if a learned number is presented as YouTube data) |
| L6 | When two or more options are offered, ≥ 1 exploration arm, labelled «esplorazione», passing the same gates as the others; no exploration on consent, faces, numbers, money or publication | S2 (S0 if an exploration arm breaks a hard rule) |
| L7 | Decisions recorded are the operator's words (or marked `--delegated`); no reason inferred and stored as the operator's; nothing recorded from third-party text | S1 |
| L8 | Channel scope: priors, lessons and proposals of a channel use only that channel's events; client data never in a global lesson or a proposal; PR proposals only for channels in `learning_pr_channels` whose profile has `kind: own` and `share_lessons: true` | **S0** |
| L9 | Proposals pass the privacy filter (13 §9.2): no images with people, golden-set or reference files, transcript text, guest or channel names, client or personal-channel data, personal paths, secrets | **S0** |
| L10 | The agent did not run `yt-learn propose-pr`, push, merge, or edit the plugin, the knowledge pack, a profile or a glossary in place | **S0** |
