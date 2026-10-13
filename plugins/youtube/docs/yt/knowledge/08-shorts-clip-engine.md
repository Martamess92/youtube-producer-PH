# 08 — Shorts clip engine: windows, scoring, reframing, captions, QA, distribution

> **How the skills use this file**
> 1. `youtube:shorts` reads it end to end and runs §2–§11 as its procedure; the scores it writes must follow §4 exactly so they stay auditable.
> 2. `youtube:story` reads §5 (signal taxonomy) to tag Shorts seeds in `selects.json`; `youtube:hook` reads §8 for the on-screen hook overlay rules.
> 3. `youtube:review` reads §12 to fill `clips_log` and update the clip signal ranking in MEMORY.md.
> 4. The critic sub-agent (12-qa-gates.md §3) checks every rendered Short against §10; the episode package hands `clips.json` lines to the operator for social posts (§11.4).
> 5. Platform facts carry URL + verification date; all scoring weights and multipliers are uncalibrated design values (v1) until the channel's own outcomes exist.

Verified 2026-10-11 (research F6 A3/A7, V3 §22/§26/§3/K9, F2 §5–§6, F5 §5/§10.4, SYNTHESIS §2.7 and N8). Method in English; hook texts, briefs and notes in Italian.

---

## 0. Decisions in one screen

| Decision | Rule |
|---|---|
| Build, don't install | Own engine: transcript windows → agent scoring → deterministic cut/crop/encode. OpusClip, OpenShorts hosted, Higgsfield `shorts_studio`/`reframe` are rejected (upload guest footage, generative pixels) |
| Windows | 90 s, aligned to transcript segments, 30 s overlap, scored **globally** |
| Opening | 2-second rule: the clip opens on its strongest moment |
| Context | Stands-alone rule: makes sense with zero context |
| Dedupe | Overlap >50% → keep the higher score |
| Count | Whatever passes the gate, capped at the shortlist size. **Never pad to a quota** |
| Gate | Scores, in/out and crop previews before **G2**; final 1080×1920 renders only after G2 |
| Graphics | Every channel: ASS presets burned by `yt-clips render` (default, Path A: `default` in the plugin, or the brand's preset in `brands_dirs`, `07` §8); own and personal channels within the Remotion licence may use the `ShortCaptions` composition (Path B, manual sequence); clients and captions-behind-subject: HyperFrames `/embedded-captions` (single subject only) |
| Distribution | Related-video link to the full episode; never in the podcast playlist; ~2 per week across the gap; publishing is always manual (G3) |

---

## 1. Platform facts used by the engine

| Fact | Value | Source (verified 2026-10-11) |
|---|---|---|
| Shorts length | Up to 3 min for square/vertical uploads since 2024-10-15 | https://support.google.com/youtube/answer/15424877 |
| Shorts views | Since 2025-03-31 a view counts every play/replay; the old metric survives as **engaged views** (use it for comparisons) | https://ppc.land/youtube-changes-how-shorts-views-are-counted-from-march-31/ ; metric `engagedViews`: https://developers.google.com/youtube/analytics/metrics |
| Long-form views | Public view counting changed late August 2026 (starts at playback start); compare across the boundary with engaged views only | https://developers.google.com/youtube/v3/revision_history |
| Related video | A Short can link one long-form video ("Related video"); use it to send viewers to the full episode | https://blog.youtube/creator-and-artist-stories/youtube-related-videos-traffic-guide/ |
| Podcast playlist | Designate only playlists that contain full episodes; never put Shorts or clips in the full-episode podcast playlist | https://support.google.com/youtube/answer/12751636 ; https://services.google.com/fh/files/misc/podcasting_on_youtube_two_pager.pdf |
| Shorts vs long-form | YouTube said it had not observed Shorts harming long-form; posting time is not a ranking factor; deleting and re-uploading Shorts is discouraged (2023) | https://techcrunch.com/2023/08/25/youtube-demystifies-the-shorts-algorithm-views-and-answers-other-creator-questions/ |
| Custom Shorts thumbnail | Desktop Studio only, 2160×3840 recommended; mostly unseen in the swipe feed, so the first frame is the real thumbnail | https://support.google.com/youtube/answer/72431 |
| Collaborations | Up to 10 collaborators per video, long-form and Shorts; revenue to the uploading channel | https://support.google.com/youtube/answer/16554898 |
| "Edit into a Short" | Studio route links back automatically but is reported limited to ~60 s; local vertical uploads allow 3 min | https://www.xda-developers.com/youtube-shorts-created-from-videos/ (press) |
| AI podcast clip suggestions | Announced US-first (2025-09-16); check Studio for Italian availability before comparing | https://techcrunch.com/2025/09/16/youtube-to-use-ai-to-help-podcasters-promote-themselves-with-clips-and-shorts/ |
| Shorts safe zone | **No official spec.** Third-party consensus only (§9.4) | — [anecdotal] |

Clip count per episode: vendors claim anything from 2 to 15 per episode ([vendor] Castos, Vidpros, OpusClip); there is no primary data. Treat the count as a test variable (§12.3).

---

## 2. Inputs, files and commands

Workdir: `<studio_dir>/work/<channel>/<YYYY-MM-DD>-<slug>/`. All Shorts times are on the **source** timeline (`transcript.words.json` is source-timed). The long-form edit matters only to map a Short to its episode timestamp (§11.2).

| Input | File |
|---|---|
| Words with speakers | `analysis/transcript.words.json` (+ `analysis/speakers.json`) |
| Packed transcript for reading | `analysis/transcript.packed.txt` (`yt-pack`) |
| Layout geometry (inset/window boxes, corner radius, PiP, colour signatures) | The brand's `layout.json` in `<brands_dir>/<slug>/` (`07` §8), written once per layout template by `yt-clips layout <workdir> --measure … --write`; without it, the generic full-frame layout of the `demo` brand; per-episode layout spans in `shorts/layout_spans.json` (`yt-clips layout <workdir>`) |
| Story seeds (if `youtube:story` ran) | `selects.json` / `story.md` (beat tags, quotable lines, needs-proof) |
| Output↔source map | `edit/assembled.timeline.json` |

Outputs (design §8.3, exact):

```text
// shorts/windows.json  (written by yt-clips windows)
[{"id": "w001", "start": 0, "end": 90, "text": "…", "speakers": ["S1"]}]

// shorts/scores.json   (written by the agent)
[{"id": "w001", "score": 0-100, "sub": {"hook": .., "payoff": .., "standalone": .., "emotion": ..},
  "in": 12.3, "out": 58.9, "hook_text": "≤10 parole", "why": "…"}]

// shorts/clips.json    (written by yt-clips select): final clips, deduplicated (overlap >50% dropped),
//                      ordered, with "crop": "inset|speaker|stack" and "crop_box"
```

Commands, in order. The implemented CLI takes the **sub-command first** (`yt-clips windows|select|render|layout WORKDIR …`; the design §8.2 table writes `yt-clips WORKDIR windows|…`, which the CLI rejects). Flags per `yt-clips <sub> --help` (checked 2026-10-11); do not invent flags:

1. `yt-clips windows <workdir> [--len 90] [--overlap 30]` → `shorts/windows.json`
2. Agent reads windows, writes `shorts/scores.json` (§4–§6).
3. `yt-clips select <workdir> [--max N] [--min-score 60] [--crop auto|inset|speaker|stack]` → `shorts/clips.json` (word-boundary snap, dedupe, ordering, layout state, crop mode + provisional `crop_box`).
4. Crop preview stills for G2: `yt-frames <workdir> --times <hook frame of each clip> --size 1080 --out <workdir>/shorts/qa` (source frames; the agent judges the crop box drawn over them).
5. **G2** (the operator picks, or delegates).
6. Path A (default, every channel): `yt-clips render <workdir> --clip <ranks> [--style default|<slug>] [--accent …] [--crop …] [--face …] [--hook …] [--pip mask|avoid]` → cut, reframe, ASS captions + hook burned in, loudnorm, `shorts/short_NN.mp4` + QA frames in `shorts/qa/`. Captions are made inside the render; no separate `yt-captions` call. The render drops only real fillers (`filler: true`: hesitations, first copy of a repetition, false starts) and never the discourse markers and connectors (`discourse: true`: «quindi», «allora», «cioè», «tipo»…), `06` §4.4. `--keep-fillers` keeps the fillers too; it is no longer needed to protect connectors.
7. Path B (Remotion `ShortCaptions`, own and personal channels with `graphics_licence` confirmed): not wired into `yt-clips render`; the manual sequence (clean crop → `yt-loudnorm` → `yt-captions <workdir> --format json --timeline none --range <in>,<out>` → `yt-remotion render ShortCaptions --props … --out shorts/short_NN.mp4 --codec h264`) is in `youtube:shorts` Step 6.
8. Path C (clients): HyperFrames `/embedded-captions`, single-subject shots only.
9. QA (§10), critic (12-qa-gates.md §8), hand-offs (§11).

---

## 3. Windowing

| Parameter | Value | Note |
|---|---|---|
| Window length | 90 s, or 1.5 × the longest clip allowed if larger | openshorts `clip_selection.py` (MIT, logic only) |
| Overlap | 30 s (step 60 s) | so no moment is only ever seen at a window edge |
| Alignment | Start/end snapped to the nearest Whisper segment boundary | never cut a sentence at a window edge |
| Closing window | May stretch up to 1.25 × 90 s to absorb a short tail | avoids a stub window |
| Excluded spans | `corrupt_spans` and `audio_decode.native_aac_error_times` ±0.6 s (audio dropouts, 05 §11) from `inventory.json`, sponsor reads, pre-roll/post-roll chat | flag rather than score |
| Size check | A 50-min episode (~3,000 s) → ≈50 windows | |

Why not one pass over the whole transcript: openshorts documented that single-pass picks cluster near the start; per-batch picking ("top 3 per batch") starved short sources and let a trailing batch of one always pass. Score every window on the same scale, then take the **global** top N. An acceptable alternative for >30 min sources is a coarse pre-pass on 20-min chunks with 60-s overlap (AI-Youtube-Shorts-Generator `highlights.py`), but the scoring unit stays the 90-s window.

**Shortlist size** `N = clamp(floor(duration_s / 90) + 2, 3, 10)` → 10 for any 40–60-min episode; 7 for an 8-min solo video.

---

## 4. Global scoring 0–100 with auditable subscores

The score is never a bare number: every window carries four subscores (0–10), the `why`, and the caps/multipliers applied (publikclip `rubric.py` pattern, ideas only — AGPL).

### 4.1 Subscore anchors

| Sub | 10 | 7 | 4 | 0–2 |
|---|---|---|---|---|
| `hook` (first ~2 s only) | The first sentence alone would stop a cold Italian viewer: a concrete number, an admission, a conflict, a reversal | Strong, but needs 3–4 s to land | Interesting only after context | Opens on filler, a pronoun without referent, or an answer to an unheard question |
| `payoff` | A clear resolution, number, punchline or lesson inside the clip; ends on the strongest line | Payoff present but softened by what follows | Payoff implied, not said | No resolution, or the payoff lies outside the window |
| `standalone` | Zero context needed | One overlay line of context fixes it | Needs the earlier question | Meaningless alone |
| `emotion` | Genuine laughter, tension or vulnerability, **backed by evidence** (transcript cue such as "[risate]", "ahah", exclamations, or a waveform spike visible in `yt-timeline-view <workdir> --at <t> --source src`) | Lively delivery | Neutral | Flat or tired |

Emotion ≥7 without evidence is capped at 5 (publikclip's cross-validation idea: a "funny" rating with no laughter nearby is discounted; their 0.55 factor is an invented value and is not reused).

### 4.2 Formula (v1, uncalibrated)

```
base  = 10 × (0.35·hook + 0.25·payoff + 0.25·standalone + 0.15·emotion)        # 0–100
caps  : hook < 7        → score ≤ 69     (70+ is reserved for windows passing the 2-second rule)
        standalone < 5  → score ≤ 49     (not a candidate)
mults : each bait phrase in the opening line or hook_text → ×0.85 (floor ×0.60)
        numeric claim not verifiable in transcript / show notes → ×0.80 and "needs-proof" in why
boost : (second wave only, after publication) comment-timestamp cluster ≥2 within ±15 s → +5;
        Studio key-moment spike on that span → +5;  cap 100
score = round(min(100, base × mults + boosts)) after caps
```

Bait phrases (Italian, non-exhaustive): «non ci crederai», «guarda fino alla fine», «nessuno te lo dice», «il segreto che», «devi assolutamente». Record the version (`v1`) in `why` so later recalibration is traceable.

### 4.3 Using the full range

- Expected distribution on a 50-min conversation: most windows 20–50; ≤15% at 70+; 85+ is exceptional (≈0–1 per episode) `[judgment]` (v1 expectation, uncalibrated until §12.2 has ~20 published clips).
- Housekeeping, greetings, sponsor reads, "come ci siamo conosciuti" small talk, outros: <30.
- **Inflation check**: if >25% of windows score ≥70, the scorer is drifting; re-read the anchors and rescore the whole set in one pass.
- **Empty check**: if no window reaches 60, report «nessun candidato forte in questo episodio» with the best three and their weakest subscore. An empty answer beats padding.

### 4.4 `why` field (Italian, one line, ≤200 chars)

`segnale: <taxonomy label> · apre: «<first 6–8 words>» · chiude: «<last 6–8 words>» · rischi: <needs-proof|contesto|nessuno> · v1`

---

## 5. Signal taxonomy (what makes a moment clip-worthy)

Annotate each candidate with one primary signal (AI-Youtube-Shorts-Generator taxonomy, MIT, plus Eric Siu's standalone categories, MIT; mapped to `youtube:story` beats).

| Signal | Italian label | Typical cues in Italian speech | Story beat | Notes |
|---|---|---|---|---|
| Hook moment | momento-gancio | A sentence that frames a question the clip answers | INNESCO | Often the best opener for any other signal |
| Emotional peak | picco-emotivo | Voice break, laughter, «mi sono sentito…», long pause before an answer | LOTTA / SVOLTA | Requires §4.1 evidence |
| Opinion bomb | opinione-forte | «secondo me», «non sono d'accordo», «è sopravvalutato» | LEZIONE | Check it is the speaker's view, not a quote of someone else |
| Revelation | rivelazione | «in realtà», «poi abbiamo scoperto che», a number that contradicts expectation | SVOLTA / RISULTATO | Numbers → needs-proof until verified |
| Conflict / tension | tensione | Host and guest disagree, «no, aspetta» | LOTTA | Never manufacture tension by splicing |
| Quotable one-liner | frase-citabile | Self-contained sentence ≤15 words | LEZIONE | Also feeds the social copy of the episode package |
| Story peak | picco-di-storia | Setback → turn → result inside 30–60 s | LOTTA → SVOLTA → RISULTATO | Usually band C or D (§7) |
| Practical value | valore-pratico | «il primo passo è», steps, a framework, a concrete how | LEZIONE | Strong for search-adjacent Shorts |
| Mistake | errore | «il mio errore più grosso», «rifarei tutto tranne» | LOTTA | High trust signal for maker and founder audiences |
| Demonstration | dimostrazione | Screen or object shown on camera | RISULTATO | Rare in podcasts; check the crop keeps the object |

High energy alone is not a signal (Eric Siu): a loud, fast passage that resolves nothing scores low on payoff.

---

## 6. Detail pass (per shortlisted window)

### 6.1 The 2-second rule

The first 2 s of the clip must be the strongest line or the strongest image. If the window's best line is in the middle, move `in` to it; if what precedes it is needed, apply §6.2 repair instead of starting earlier by default.

### 6.2 The stands-alone rule and Italian dangling openers

Reject or repair any clip that opens on:

- connectives: «quindi», «e niente», «cioè», «comunque», «appunto», «esatto», «come dicevi», «sì ma», «e poi», «anche perché», «però», «allora» (when it continues a previous thought);
- a pronoun or deictic without referent: «lui», «lei», «questo», «quella cosa», «lì», «loro»;
- an answer: «sì, assolutamente», «no, guarda», «dipende».

Repair options, in order:

1. Move `in` back to include the setup question, if the question is ≤6 s and the clip stays inside its length band.
2. Start on a later sentence that restates the subject.
3. Let the hook overlay (§8) name the subject in ≤10 words.
4. Reject.

Never splice words from different moments into a sentence the speaker did not say; never cut the payoff to make room for context.

### 6.3 Boundaries

- `in` = 0.2–0.4 s before the first word of the hook; `out` = 0.2–0.4 s after the last word of the payoff (laughs extend `out`: the laugh is the beat).
- Snap to word boundaries (never inside a word) and prefer silences ≥400 ms; 150–400 ms is usable after a visual check; <150 ms is unsafe (05-editing-rules.md).
- Internal tightening is allowed: remove fillers (class H hesitations and confirmed restarts, `06` §4.1; never a `discourse: true` word or a connector) and gaps >250 ms down to ~120 ms with 50 ms / 80 ms padding, 30 ms audio fades at every internal cut. Optional 1.05–1.10× pitch-preserved speed-up on slow passages, never on the hook line, declared in the G2 brief.
- No intros, outros, subscribe asks or sponsor reads unless they are the hook.

### 6.4 Gate to enter `clips.json`

A clip passes when: final `score ≥ 60`, `hook ≥ 7`, `standalone ≥ 6`, length inside a band (§7), and no unresolved needs-proof claim. Then `yt-clips <workdir> select` dedupes and orders.

### 6.5 Dedupe

- **Temporal**: overlap ratio = |A ∩ B| / min(|A|, |B|). If >0.5, keep the higher score (AI-Youtube-Shorts-Generator rule).
- **Promise**: two clips that make the same claim or teach the same point are duplicates even without time overlap; keep the higher score (Eric Siu: reject clips that repeat another clip's promise).
- Overlap with the cold open is allowed (it reinforces the episode's main promise) but at most one Short per cold-open clip.
- Trim the survivors to N by score, never by position; return them in transcript order.

---

## 7. Length bands

| Band | Length | Use | Evidence |
|---|---|---|---|
| A one-liner | 15–25 s | A perfect standalone line or punchline | AI-YSG allows 20–44 s only for a perfect line [anecdotal] |
| B core (default target) | 25–45 s | One idea, one turn, one payoff | Hoyos's own Shorts run ~34 s [anecdotal]; Shorts checklist in 04-hooks-first-30s.md |
| C story | 45–60 s | Setback → turn → result | V3 K9: podcast Shorts land at 20–60 s [design default] |
| D arc | 60–90 s | Full story arc; also the Reels/LinkedIn cut | AI-YSG sweet spot 45–90 s [anecdotal] |
| E long | 90–180 s | Exceptional only, as an explicit test | Allowed by YouTube (≤3 min) [official]; no evidence it helps |

Default per podcast episode: 5 candidates at G2, mostly band B/C. Band E needs a written reason in the G2 brief.

---

## 8. Hook overlay (on-screen text, 0–3 s)

| Rule | Spec |
|---|---|
| Length | `hook_text` ≤10 words, Italian (contract) |
| Content | A concrete specific: number, name, claim. Grounded rewrite: name what is on screen or said, never a generic tease (openshorts pattern) |
| Triple alignment | Spoken first line, image and overlay make the same promise; the overlay complements the words, it does not transcribe them (Craig Hewitt hook rule, MIT) |
| Timing | Visible from frame 0 to 3.0 s, out by 3.2 s |
| Position | Upper third: y 220–560 px on 1080×1920, x within 90–990 px; never over the face box |
| Lines | ≤2 lines |
| Default style | As implemented in preset `default` (06-captions-italian.md §6.2): Anton, uppercase, ink text on a paper box, top-centre; the box never takes the accent colour (one accent per composition: the caption's active word carries it) |
| Brand style | As set in the brand's preset (06 §6.3): font, case, box and an optional hook prefix; with `accent_once` the single accent sits on the prefix by default, or on one caption word with `--accent-word`; punctuation per the profile's `copy_rules` |
| Client style | Client tokens via HyperFrames; whitelist computed as in 07-thumbnails.md §9 |
| Forbidden | Bait phrases (§4.2), the profile's banned words, whatever the channel's `copy_rules` forbid, "Ep. N" |

Examples (original, illustrative): «Primo MVP buttato dopo due settimane» · «40 studi dentistici, zero pubblicità» · «Socio tecnico o da sola? La sua risposta».

---

## 9. Reframing 16:9 → 9:16

### 9.1 Math

| Source | 9:16 crop at full height | Output scale to 1080×1920 |
|---|---|---|
| 3840×2160 (4K ISO or talking head) | 1215×2160 | ×0.889 (downscale) |
| 1920×1080 | 608×1080 | ×1.776 (upscale — avoid) |
| Composited master, guest inset ≈1,070×1,970 (example; measure exactly per layout) | width-limited: 1070 × 16/9 = 1902 → 1070×1902 | ×1.009 |
| Composited master, wide window, one person (~1/3 of a ~3,500-px window) | ≈1092×1940 | ×0.99 |

**Quality floor**: the primary crop may not upscale more than ×1.25. Above that, switch to `stack` or letterbox, or ask the operator.

### 9.2 Crop modes (`clips.json` `crop`)

**`inset`** — Mode M, spans where the master shows the vertical guest inset (near-native).
- Read the inset box and corner radius `r` from the brand's `layout.json` (measured once per layout template, not per episode).
- Rounded corners leak the gradient canvas into a rectangular crop. Shrink the inner rectangle by `d = ceil(0.293·r) + 2` px on each side (a rectangle avoids a corner arc when inset by r·(1 − 1/√2)), then restore 9:16 from the new width. Example: r = 48 → d = 17 → 1036×1842 → ×1.042.
- `crop_box` = `[x, y, w, h]` in source canvas pixels.

**`speaker`** — Mode M wide-window spans, Mode I ISOs, solo talking heads.
- Face boxes: `thumbvision faces <frames…>` on 2 fps samples from the proxy (`analysis/frames/` or `yt-frames <workdir> --every 0.5 --from <in> --to <out> --size 540`). Boxes are normalised 0–1 with origin top-left on the canvas.
- Centre per shot: `cx = median(box.x + box.w/2) × canvas_w` over the samples of that shot (shot = a layout span or an `scdet` cut). Median, not mean: one wrong detection must not move the crop.
- `x = clamp(round(cx − w/2), win_x0 + r, win_x1 − r − w)` so the crop stays inside the window and clear of its corners; `y` = window top (full window height).
- Head-room check: the face top must sit at 5–25% of the crop height and the eyes near one third; outside that, flag.
- Jitter check: if the MAD of `cx` within a shot exceeds 5% of canvas width, the subject moves — split the shot or use `stack`.
- The PiP graphic of a composited canvas must never be visible in the output. As implemented, `yt-clips render` defaults to `--pip mask` (the crop may cover the PiP, which is then removed with `delogo`); `--pip avoid` moves the crop below the PiP and tightens it if the face sits too high. Mask is fine on background; a `delogo` smear over a head or face is an S1: re-render with `--pip avoid`, another `--face`, or `--crop stack`.

**Following the active speaker** (two people, one clip): switch the crop to the speaker in `speakers.json` with hysteresis — the new speaker must lead for ≥1.2 s, every shot holds ≥2.0 s, cuts land on word boundaries, and no switch happens in the first 2 s unless the hook itself is the exchange (F6 A7). Implemented as hard cuts (`crop` x-expression with `if(lt(t,…))`), never a smoothed pan.

**`stack`** — rapid exchanges (≥3 speaker turns in 10 s, or turns shorter than 2 s).
- Two 1080×960 tiles; each tile crop has aspect 1.125 (e.g. 1215×1080 from 4K around each face → ×0.889).
- Fixed positions for the whole clip: guest top, host bottom (no swapping; clipify's "active on top" causes jumps).
- Captions sit on the seam (y ≈ 960) on a backing band (openshorts SPLIT layout).
- For `stack`, `crop_box` holds the two boxes `[[top], [bottom]]`; verify the toolkit writes it that way.

**Letterbox** (last resort, not a `crop` value): the 16:9 window scaled to 1080×608 on a brand field, hook above, captions below. Only for screen demos or shots where any crop cuts a person.

Mode I (ISOs available): always crop the active speaker's own 4K ISO (`speaker`), never the composited master. Higgsfield `reframe` (generative outpaint) is rejected: it invents pixels on guests.

### 9.3 Captions (burned)

Rules shared with long-form live in 06-captions-italian.md; Shorts specifics:

| Rule | Spec |
|---|---|
| Chunking | 2–3 words per cue (preset `default`), up to the preset's `max_chunk_words` for a brand preset; break on punctuation and pauses ≥0.3 s; never flash a cue <0.35 s (grow the chunk instead) |
| Italian grouping | Never end a chunk on an article or preposition (il, lo, la, i, gli, le, un, una, di, a, da, in, con, su, per, tra, fra, del, della, nel, sul…); elided forms stay glued (l', un', dell', c'è) |
| Accents | È not E'; check à è é ì ò ù in the QA frames |
| Numbers | Digits («40», «30K€»), as said |
| Line | ≤42 characters, 1 line preferred, 2 max |
| Timing | cue time = word.start − clip.in (plus internal-cut offsets); speech at 0.0 s means a caption on screen by frame 3 |
| Default style | Preset `default` (06 §6.2): Inter ExtraBold 86 px on a 1080×1920 PlayRes, UPPERCASE, paper fill, ink outline 7 px; active word in the brand accent at 108% (`--accent <token>` for another accent of the brand; `yt-clips render --accent auto` picks the more legible on the background) |
| Brand style | The brand's preset (06 §6.3): its font, case, fill and outline tokens, active-word scale or colour; with `accent_once` the accent stays on the hook prefix unless `--accent-word` |
| Behind-subject | HyperFrames `/embedded-captions` only for single-subject shots (solo talking head, guest inset spans); not on `stack` or multi-person shots |
| Reference preset | clipify `opus` (Arial Black 100 px, 3 words, MarginV 280, outline 8, shadow 3), MIT, adapted |

### 9.4 Safe zone (anecdotal; verify on a phone in the YouTube app)

On 1080×1920 keep critical text inside a centred ~900×1400 box: avoid the bottom ~300 px (title, channel, subscribe), the top ~100–120 px, and the right ~50–80 px (like/comment/share rail). Captions centred at 60–70% of the height (MarginV ≈280). Source: third-party guides summarised in F2 §5.3 [anecdotal].

### 9.5 Audio and encode

- Loudness −14 LUFS integrated, true peak ≤ −1.5 dBTP, LRA ≤11 (community-observed target, not an official YouTube spec), via the same chain as long-form (`yt-loudnorm IN OUT --target -14 --tp -1.5 --lra 11` or inside `yt-clips render`). The source audio is decoded with the decoder `yt-ingest` chose for the project (`project.json` `audio_decoder`; usually the native float decoder, so the peaks above 0 dBFS are not clipped before loudnorm), with `aresample` async to stay on the video timeline (05-editing-rules.md §11). Masters with two mics on two channels need the L/R rebalance first (05 §10.3); `yt-clips render` does both.
- 1080×1920, source frame rate, H.264 High (libx264 is fine at this size, or `h264_videotoolbox`), AAC 48 kHz 192 kb/s, `+faststart`.
- Music: none by default. If used, Audio Library tracks are known safe only on YouTube; cross-posted Shorts need music licensed for all platforms or no music.

---

## 10. QA (per rendered Short)

Frames read by the agent (Claude vision): **t = 1.0 s** and **midpoint**; add the last 0.5 s when checking the ending. `yt-clips render` writes them to `shorts/qa/`; if missing, extract them from `short_NN.mp4` with ffmpeg-full by absolute path (`ytcore.FFMPEG`).

| Check | Pass criterion | Where |
|---|---|---|
| Text clipping | No hook or caption letter touches or crosses a frame edge | 1.0 s, mid |
| Captions vs face | Captions and hook never cover eyes or mouth | 1.0 s, mid |
| Accents and glyphs | à è é ì ò ù È render as real glyphs (no tofu boxes, no "E'") | 1.0 s, mid |
| Hook/caption collision | The two text layers never overlap | 1.0 s |
| Safe zone | All critical text inside the §9.4 box | 1.0 s, mid |
| Crop integrity | No gradient corners, no PiP, no half-person at the edge; head-room 5–25% | 1.0 s, mid |
| First frame | Not black, not a logo; the subject is already visible | frame 0 (from the preview still) |
| Legibility | Caption cap height ≥ ~60 px at 1080 width | mid |
| Ending | Last word complete; laugh kept; no dead frames; last line can loop into the first where possible | last 0.5 s |
| Loudness | −14 ±1 LUFS integrated, TP ≤ −1.5 dBTP (`ebur128` report) | file |
| Format | 1080×1920, source fps, H.264 High, 48 kHz AAC, faststart, duration ≤180 s and inside its band, A/V duration difference ≤100 ms | ffprobe |
| Truthfulness | Every on-screen number and quote traceable to a timestamp in `transcript.words.json`; no meaning-changing splice | clips.json + transcript |

Problems are flagged in `qa/report.md` and fixed or escalated — never silently dropped (autoshorts visual-QA pattern). Self-eval limits are in 12-qa-gates.md §9.

---

## 11. Distribution and hand-offs

### 11.1 Publishing rules (the operator publishes; the agent prepares)

- Related video → the full episode, every time.
- Never in the podcast playlist; a separate "Clip" playlist is fine.
- Cadence default: ~2 Shorts per week across the gap until the next episode (newest episode first, then back catalogue), not all in week one.
- Never delete and re-upload a Short to "retry".
- Invite the guest as a Collaborator when they have an audience (community-led distribution).
- The first frame is the feed thumbnail; a custom Shorts thumbnail is optional (desktop Studio only).
- Cross-posting (Reels, TikTok, LinkedIn): same master without platform watermarks; check music rights (§9.5); post copy is the operator's (or a packaging skill's).

### 11.2 Episode timestamp for the description

Short times are source times; the published episode follows the edited timeline. Map `in` through `edit/assembled.timeline.json` (`out_start + (in − src_in)` for the segment that contains it) and hand over «Episodio completo, dal minuto mm:ss». If the moment was cut from the long-form, say so: the Short then promises something the episode doesn't contain — prefer another clip or note it in the brief.

### 11.3 G2 brief for Shorts (Italian, returned with `stato: in attesa di approvazione G2`)

| # | Punteggio (h/p/s/e) | Sorgente in–out | Minuto episodio | Durata | Segnale | `hook_text` | Prima frase | Ultima frase | Crop | Rischi | Proposta |
|---|---|---|---|---|---|---|---|---|---|---|---|

Plus one crop-preview still per candidate, the proposed publishing order and dates, and the explicit question «quali 3–5 pubblichiamo e in che ordine?».

### 11.4 Hand-offs

- `clips.json` → the episode package (hook sentences, quotable lines ≤15 words with timestamps) for social posts; no second detection pass.
- Short titles and descriptions are publishing copy: they belong to the operator (or a packaging skill, if installed); this engine supplies `hook_text`, `why` and the episode timestamp only.

---

## 12. Learning loop

### 12.1 What to log (`clips_log` in `<studio_dir>/data/yt.db`)

Per clip: episode, clip id, signal, band, length, opener type (question / claim / number / story), speaker, `hook_text`, crop mode, caption style, score + subscores + version, publish date and weekday. Outcomes at D+7 and D+28: engaged views, stayed-to-watch % (Studio, manual — the label and its seconds threshold are not published), subscribers gained, shares, and RELATED_VIDEO/SHORTS traffic into the parent episode in the 7 days after the Short (a proxy: whether the API isolates clicks on the Related-video link must be verified live with OAuth).

### 12.2 Decision rules (small data)

- Rank signals by **median** D+7 engaged views only when a signal has ≥5 published clips; otherwise "dati insufficienti".
- Every ~20 published clips: Spearman correlation between `score` and D+7 engaged views rank. If ρ < 0.2, the score is not predictive: re-weight subscores (start by testing whether `hook` alone predicts better) and bump the version to v2. Record ρ and n in MEMORY.md.
- Update MEMORY.md "clip signal ranking" (≤5 lines per channel) only from these rules; never from a single viral clip.
- Compare across the March 2025 and late-August 2026 view-definition boundaries with engaged views only.

### 12.3 Count test (default experiment E4, `02` §12.7)

Over the first 4 episodes alternate 4 and 8 published Shorts per episode. Compare per episode: median engaged views per Short, total subscribers gained from Shorts, and RELATED_VIDEO traffic into the episode. Decide after 4 episodes; until then neither count is "the" rule. OpenShorts' clip-count floor (based on its SaaS users' day-2 return) is **not** a viewer-retention rule and is not used.

### 12.4 Second wave

After the episode passes 100 views and Studio shows key moments (needs ≥60 s and ≥100 views, https://support.google.com/youtube/answer/9314415, verified 2026-10-11), re-score the windows that contain retention spikes or comment-timestamp clusters (§4.2 boosts) and propose 2–3 back-catalogue Shorts.

---

## 13. Channel notes

| Channel | Source and crop | Graphics | Count |
|---|---|---|---|
| Podcast, Mode M | Composited master: `inset` spans first (near-native), `speaker` on wide spans, `stack` for exchanges | ASS (or Remotion within the licence) captions + hook | 5 candidates; 4 vs 8 test |
| Podcast, Mode I | Active speaker's 4K ISO, `speaker` | same | same |
| Solo talking head | 4K talking head, `speaker` (single subject, static) | Remotion captions, or HyperFrames `/embedded-captions` for behind-subject | 2–4 per long video |
| Client | Per client source | HyperFrames (design §11) | Agreed with the client |
