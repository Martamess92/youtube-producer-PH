# 05 — Editing rules: cuts, audio, encode, hand-off

## How the skills use this file

- `youtube:edit` reads it in full before G1 and before every render: production rules (§1), passes (§2), cuts (§3–§5), picture (§6–§9), audio (§10–§11), encode (§12), graphics (§13), music (§14), NLE hand-off (§15), self-eval (§16).
- `youtube:shorts` reads §1, §3–§4, §10–§12 for cutting, audio and encode; reframing math and clip selection stay in `08-shorts-clip-engine.md`.
- `youtube:story` and `youtube:hook` read §3 and §9 (what a composited master physically allows) before proposing reorders or cold-open clips.
- `youtube:setup` reads §11–§12 for doctor checks; `youtube:thumbnail` reads §9 for face-size limits of the master.
- The critic sub-agent uses §16 as its checklist (full gate list in `12-qa-gates.md`). Method in English; G1 briefs and QA reports in Italian.

Status: written 2026-10-11 from F1 K-11–K-16/K-22–K-23, F2 §3–§14, V1 K1/K3, V2 §0–§1, SYNTHESIS §1.3 (N8–N11), §2.3, §7A–§7B, design doc §8 and §11. §1.1 (transcription) added 2026-10-12 from the toolkit's transcription tests (X1 engines and timing, X2 glossary and post-correction, I1 before/after; one 53-min Italian interview episode, internal test logs not distributed). Evidence labels: [official] [study] [vendor] [anecdotal]. Local findings from the 2026-10-11 probes of a 4K composited podcast master are marked [anecdotal, local probe] (n=1 file).

---

## 0. Non-negotiables

1. **ffmpeg-full by absolute path** (`ytcore.FFMPEG` = `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`, ffprobe next to it). Bare `ffmpeg` may resolve to the minimal core build without libass/drawtext. Verified on an Apple Silicon Mac 2026-10-11: ffmpeg-full has `ass`, `subtitles`, `loudnorm`, `silencedetect`, `sidechaincompress`, `aac_at`, `h264_videotoolbox`, `hevc_videotoolbox`, `prores_videotoolbox`.
2. **Originals are read-only.** `src/` holds symlinks; nothing is written or deleted there (`guard.sh` blocks `rm` in `*/src/`).
3. **Gates.** G1 before any cut (plain-language strategy + EDL summary), G2 before final renders of Shorts and thumbnails, G3 publishing always manual. The agent never uploads, never sets titles or thumbnails.
4. **Local only.** No paid service inside the agent; guest footage never leaves the Mac by default.
5. **No generative pixels on guests** (no generative upscaling, outpainting or "reframe" on people).
6. **Outputs live in the workdir** `<studio_dir>/work/<channel>/<YYYY-MM-DD>-<slug>/` (`analysis/`, `edit/`, `deliver/`, `shorts/`, `thumbs/`, `qa/`, `logs/`). Notes (vault or `deliver/notes/`) receive only written deliverables, never media; the plugin repo receives neither.
7. **Two timelines.** Times are float seconds; `source` = original file, `output` = edited file; `edit/assembled.timeline.json` maps one to the other.
8. **Idempotent commands.** Every `yt-*` command skips work whose output is newer than its inputs; `--force` redoes it.
9. **Measure, never assume**: loudness, durations, bitrates, layout geometry.

---

## 1. The 12 production rules (video-use, paraphrased)

Source: browser-use/video-use `SKILL.md`, MIT, pinned at `43cfc566` (https://github.com/browser-use/video-use/blob/main/SKILL.md); vendored helpers keep the LICENSE, attribution in `vendor/NOTICE.md` (docs/yt). Rewritten in our words for our toolkit. [anecdotal — practitioner engineering rules]

| # | Rule | Why | Where it lives in our toolkit |
|---|---|---|---|
| 1 | Burn subtitles last, after every overlay | Overlays drawn later would cover them | Final filter of `yt-edl-render` / Shorts render |
| 2 | Render each kept range as its own segment, then join with a lossless concat (`-c copy`) | No double encoding; a fix re-renders one segment | `yt-edl-render` |
| 3 | 30 ms audio fade-in and fade-out at every segment boundary | Removes clicks at cuts | `fade_in`/`fade_out` = 0.03 in `edl.json` |
| 4 | Shift every overlay with `setpts=PTS-STARTPTS+T/TB` | Frame 0 of the animation lands exactly at its window start | Overlay compositing (`overlays[].at`) |
| 5 | Master captions in output time: `out = word.start − segment.src_in + segment.out_start` | Captions stay in sync after reorders | `yt-captions` via `edit/assembled.timeline.json` |
| 6 | Never cut inside a word; snap every edge to a word boundary | Clipped syllables are the most audible edit error | EDL builder |
| 7 | Pad edges inside a 30–200 ms window (reference: 50 ms before the first kept word, 80 ms after the last) | ASR word times drift ~50–100 ms (with the Parakeet timing of §1.1; raw whisper token times were off by >0.5 s on 23.6 % of words) | EDL builder (§3.2) |
| 8 | Edit only from word-level verbatim ASR, never from phrase-level SRT or filler-normalised text | Cut points need word timing; normalised text hides fillers | `yt-transcribe` (word JSON, disfluent prompt) |
| 9 | Cache transcripts per source hash | Re-transcribing costs minutes and changes word IDs | `<studio_dir>/cache/transcripts/` |
| 10 | Build independent animations in parallel sub-agents | Graphics are the slow part | Remotion / HyperFrames renders (§13) |
| 11 | Get plain-language approval of the strategy before cutting | The human owns editorial intent | Gate G1 |
| 12 | Write every output inside the episode workdir, never inside skill or toolkit folders | Reproducibility; no pollution of versioned code | All commands |

Craft values from the same source: speaker hand-offs breathe at ~400–600 ms; extend past laughs ("the laugh is the beat"); self-evaluate the rendered file at every cut (±1.5 s), first and last 2 s, max 3 passes; measure loudness with `ebur128`; a critic sub-agent reviews anything publishable (§16). [anecdotal]

### 1.1 Transcription: text, timing, names, units (as implemented 2026-10-12)

Measured on one episode (53 min, Italian, 3 speakers) against a silver reference (S0) (4 slices, 1,384 certain tokens, 56 entity occurrences; one error = 0.07 pp; differences under ~0.5 pp WER are noise) [study, n=1].

| Step | What the toolkit does | Evidence |
|---|---|---|
| Glossary | `yt-glossary`: terms with provenance from `project.json`, the prep note, web pages the agent read (`web.json` with type and URL), the channel glossary (P1/P2/P3) and `<channel>.confusions.json` → `analysis/glossary.json` | Episode names in the prompt matter (no prompt: 39/56 names; with: 44–47/56); ranking, length and style do not (X2) |
| Prompt | hint + `glossary_extra`/`--prompt-extra` + MRR, ARR (when the prep mentions revenue) + `glossary.json` terms + channel P1/P2; ≤480 characters (≈171 tokens) or `--prompt-budget N` | Without MRR/ARR in the prompt every unit slot becomes a non-word («Mararro», «emarar»); without channel terms whole-episode spellings break («Bluestrapped» for bootstrapped, «StiJobs» for Steve Jobs) (X1). A 110-token prompt finds more hesitations (241 vs 144) with the same names (X2) |
| Text | whisper.cpp large-v3-turbo, `-l it`, Silero VAD defaults | VAD off / thresholds / padding: no measurable gain; Parakeet as text engine: fewer names (37/56) and no MRR/ARR; ROVER: +0.1 pp at most and broke «20x»; DTW: +31 % runtime, worse word ends (X1) |
| **Word times** | **Parakeet TDT v3 on the same audio; whisper words aligned to Parakeet words (±10 s) take their start/end; unmatched words (mostly «ehm») go on voiced audio between their neighbours (`timing_guess: true`); a ≥6-word whisper repeat with no audio left for it is dropped (`doppione-senza-audio`)**; then the ±0.4 s pause snapping | Words off by >0.5 s against DTW: 23.6 % → 2.8 % (>1 s: 7.0 % → 0.6 %); pause-initial word starts within 100 ms: 76 % → 90 %; word starts in silence: 11.2 % → 6.1 %; runtime +≈70 s per episode (I1, matches X1) |
| Names | `glossary_fix` (episode terms, phonetic) + **constrained post-correction** (`yt-postcorrect` rules: aliases from the confusions file, casing of distinctive spellings, joined/split forms, elisions, phonetic neighbours only when capitalised mid-sentence with a context word within ±60 words) | 0 false corrections in 48 runs (X2). Names 46/56 → 49/56 with the rules alone, 52/56 after the agent's review (I1, production inputs); 41/56 → 54/56 on a first pass with `yt-glossary` (I1) |
| Review | `analysis/postcorrect.candidates.json` → agent's `analysis/corrections.decisions.json` (accept/reject with evidence; rejecting undoes an AUTO edit) → `yt-postcorrect`; every edit in `analysis/corrections.json`, words keep `fixed_from` | No prompt fixes «Cloud» for Claude or a common first name written instead of a rarer spelling of the same name (they appear with every prompt, even prompts containing the right name) (X1, X2) |
| Units | every MRR/ARR (or mangled form) ≤3 words after a figure gets `unit_review: true` and goes to the listening list; never resolved automatically | Whisper's MRR/ARR choice follows the order of the acronyms in the prompt, not the audio (X2) |
| Listening list | `analysis/transcript.review.json`: unit slots + spans where whisper and Parakeet disagree; `priority` = numbers, acronyms, mid-sentence names and the word next to a figure (≈4 min per episode; all spans ≈10 min) | Catches «2020»/«2024», «Vento»/«evento», «potenti»/«utenti» (X1) |
| Hesitation check | warning below 3 hesitations per minute | 2.7/min with the long prompt vs 4.6/min with the glossary prompt on the test episode (I1) |
| Robustness | the energy floor ignores digital silence when it is ≥1 % of the audio | With ≥10 % digital silence the old floor fell to −140 dB and room tone counted as speech (X1 stress test) |

Practical consequences for the edit:
- Cut points (§3.2) can trust word boundaries at pauses; inside continuous speech the 50/80 ms padding still applies.
- A word with `"timing_guess": true` has an estimated time (no Parakeet counterpart): look at it in `yt-timeline-view` before cutting on it.
- Hesitations Parakeet does not hear are placed on the voiced audio of the gap, so `filler` words now sit on the «ehm» itself in ~89 % of cases (was 68 %) (X1).
- Re-transcribing (`yt-transcribe --force`) keeps the agent's name decisions (re-applied by id); old transcripts (pipeline of 2026-10-11) stay valid and are not re-run unless `--force` or `--timing parakeet` is given.

---

## 2. Edit pass order (talking head and interview)

| # | Pass | What happens | Tools | Gate |
|---|---|---|---|---|
| 1 | Technical | Probe, decode errors, loudness, L/R balance, layout spans; dead air candidates | `yt-ingest`, `yt-transcribe`, `yt-speakers`, `yt-pack` | — |
| 2 | Content | Remove repeats, tangents, re-asked questions, pre-roll and after-talk; keep causation (`03` §1) | Packed transcript, selects | — |
| 3 | Structure | Reorder (narrative cut only), chapters, cold open built last (`04` §7) | Paper edit (`03` §8) | **G1** |
| 4 | Picture | Shot choice (Mode I), punch-ins (solo), B-roll, screen recordings | `edl.json` `zoom`, `overlays` | — |
| 5 | Text and graphics | Text hook, lower thirds, number callouts, chapter cards, end plate | `yt-remotion` / HyperFrames | — |
| 6 | Sound | Balance, voice chain, music beds and ducking, SFX, loudness | `yt-loudnorm`, ffmpeg filters | — |
| 7 | Retention QA | `04` §10 checklists; first 30 s watched on a phone with sound off (does the text carry the hook?) and with sound on; self-eval + critic | `yt-timeline-view`, critic | — |

---

## 3. Cut-point heuristics

### 3.1 Gap classes (silence between kept words)

| Gap | Class | Use |
|---|---|---|
| ≥400 ms | Clean | Cut freely |
| 150–400 ms | Usable | Cut after checking the waveform view at that point |
| <150 ms | Unsafe | Mid-phrase; do not cut unless a picture change covers it and the audio join is verified |

Source: video-use cut-point practice (F1 K-12). [anecdotal]

### 3.2 Padding and snapping

- `in = first_kept_word.start − 0.05`, `out = last_kept_word.end + 0.08` (seconds).
- Clamp the padding inside the gap: if the gap to the neighbouring word is shorter than the padding, split the gap at its midpoint.
- Never pad into a neighbouring word, a breath intake that starts a new phrase, or a laugh you are cutting away.
- Prefer cut edges at the bottom of the waveform envelope (lowest energy) within the allowed window.

### 3.3 Speaker hand-offs, laughs, reflective pauses

- **Hand-offs**: keep ~400–600 ms of air between speakers; never tighten below ~300 ms in conversation (it sounds like interruption). [anecdotal]
- **Laughs**: extend the out-point past the laugh until it decays; when the host laughs at the guest's punchline, the laugh stays (it is the reaction beat). [anecdotal]
- **Big lines**: after a LEZIONE line, an admission or a number reveal, keep up to ~1.0 s of silence before the next line. Silence is a tool after a big line. [anecdotal]

### 3.4 Priorities when two cut points compete

Murch's Rule of Six (`03` §5.2): emotion > story > rhythm > eye-trace > 2D plane > 3D space. Sacrifice continuity before emotion. [anecdotal]

### 3.5 Split edits (J- and L-cuts)

- **L-cut**: the previous audio continues over the new picture (end of an answer over a reaction shot or B-roll). **J-cut**: the next speaker's audio starts before their picture (multicam: picture follows 4–8 frames after the first word). Sources: https://en.wikipedia.org/wiki/J_cut ; https://vimeo.com/blog/post/j-cuts-l-cuts [anecdotal].
- **Mode M (composited master)**: audio and picture are baked together, so split edits are not possible inside the master; B-roll overlays give the L-cut feel (audio continues under the insert).
- **Mode I**: split edits are needed for multicam. The current `edl.json` schema has no per-segment audio offset; until it gains one, split edits are expressed by overlaying camera picture over a continuous master-audio track (camera EDL, §8.3) or finished in the NLE (§15).

### 3.6 Never cut automatically

- Causal connectors («quindi», «però», «perché», «allora» when causal): they are the story's "ma/quindi" (`06` §4).
- Qualifiers attached to numbers («circa», «lordo», «nel mese migliore»).
- A guest's self-correction: keep the corrected version, never build a sentence the guest did not say.
- The last word before a laugh.

---

## 4. Adaptive silence detection and pause tightening

### 4.1 Adaptive threshold (no fixed −35 dB guess)

Recipe from remotion-dev's silence-detection reference (plain ffmpeg, no Remotion needed) [anecdotal]:

```bash
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
# pass 1: measure, read "input_thresh" from the JSON block on stderr
$FF -hide_banner -i analysis/audio48k.wav -af loudnorm=print_format=json -f null - 2> logs/ln_measure.txt
# pass 2: detect silences relative to the program's own gate
$FF -hide_banner -i analysis/audio48k.wav -af silencedetect=noise=${THRESH}dB:d=0.5 -f null - 2>&1 | grep -E "silence_(start|end)"
```

Merge silences separated by less than 0.2 s when they sit at the head or tail of a take.

### 4.2 Voiced gaps (fillers the ASR dropped)

Whisper tends to normalise disfluencies away. An inter-word gap ≥0.25 s that `silencedetect` does **not** report as silence is probably an unrecognised filler, a breath or a false start → mark as a candidate and look at it in `yt-timeline-view` before cutting. [anecdotal — F2 §2.2] With the Parakeet word times (§1.1) these gaps are where they really are: the old whisper times smeared them (median −145…−275 ms early bias), so gap lists made before 2026-10-12 are unreliable.

### 4.3 Parameters by format

| Parameter | Podcast (interview) | Solo talking head | Shorts |
|---|---|---|---|
| Pause tightening | gaps >0.8 s → ~0.35 s | gaps >0.25 s → 0.10–0.20 s | gaps >0.25 s → 0.10–0.15 s |
| Edge padding | 50 / 80 ms | 50 / 80 ms (up to 120 ms after the last word if breath sounds chopped) | 50 / 80 ms |
| Fillers (`06` §4) | flag only; keep unless stacked | cut candidates, confirmed at G1 | cut |
| Speaker hand-offs | 400–600 ms | — | 300–400 ms |
| Laughs and reactions | keep | keep | keep the start, trim the tail |
| Baseline tool | transcript-driven EDL | `auto-editor <take> --edit audio:-30dB --margin 0.08s,0.12s --smooth 0.2s,0.1s --preview` then `--export v3` | transcript-driven EDL |

Values are house defaults distilled from F2 §15 and SYNTHESIS §7A–§7B [anecdotal]; tune on the first real episode and store the result in the agent's `MEMORY.md`.

Gap trimming rule: when shortening a gap, remove its **middle**, so both sides keep their natural breath and decay. [anecdotal]

Speed: an optional 1.05–1.1× on slow passages (pitch-preserving `atempo`) is allowed only on a channel owner's own solo Shorts; never on guests, never above 1.1×. `atempo` accepts 0.5–2.0 per instance. [anecdotal]

---

## 5. Retakes and false starts

### 5.1 Detection signals

- The same first 3–5 words opening two phrases within ~20 s (repeated n-gram).
- Italian restart markers: «no, aspetta», «rifaccio», «ricomincio», «da capo», «scusa», «dicevo», «rifacciamo», «taglia».
- An abandoned clause (phrase ends on an article, preposition or auxiliary) followed by a pause ≥0.4 s and a restart.
- A clap or slate spike in the waveform at the start of a take.

### 5.2 Selection rules

- **Solo talking head**: pick the best take per beat; default to the **last complete** take; prefer complete sentence, no stumble, matching energy. If two takes are close, put both in the G1 brief and let the operator pick. Never splice halves of two takes unless the join sits in a ≥150 ms gap and a punch-in change covers the visual jump.
- **Podcast**: inside an answer, remove a false start only when the restart repeats the same content («abbiamo— abbiamo deciso» → keep the second). If the restart changes meaning (self-correction), keep the final version only.
- Every retake removal appears in the EDL notes (§17) with the reason «retake».

---

## 6. Punch-ins (digital zooms)

| Source → delivery | Max scale without upscaling | House cap |
|---|---|---|
| 4K → 1080p | 2.0 | 1.3 |
| 4K → 1440p | 1.5 | 1.3 |
| 4K → 4K | none (any zoom upscales) | 1.15 |
| 1080p → 1080p | none | 1.10 |

Rules (practitioner [anecdotal]):
1. **Solo jump cuts**: alternate framing on consecutive segments of the same shot (1.0 ↔ 1.12–1.2); never the same framing across a jump cut.
2. **Emphasis**: 2–4 punch-ins per minute at important lines (Craig Hewitt skill heuristic); zoom back out at topic transitions.
3. **Slow push-in** (1.00 → 1.06 over a key statement) for reflective moments; per-frame scaling renders slower.
4. **Centre on the face, not the frame**: set `cx`/`cy` from the median face centre of the segment (`thumbvision faces` on a few frames); `cy` ≈ 0.4 keeps the face slightly above centre.
5. **Mode M (composited master): no punch-ins on the canvas.** Scaling the canvas scales the background, the rounded window and the PiP; it reads as an error, not emphasis. Punch-ins inside the window become possible only when the layout is rebuilt from ISOs (Mode I, §9.5).

EDL field (design doc §8.3): `"zoom": {"scale": 1.15, "cx": 0.5, "cy": 0.4}`. `cx`/`cy` are the **centre of the crop** in normalised frame coordinates (0.5 = frame centre); `scale` < 1 is rejected (punch-in only). Equivalent filter, as `yt-edl-render` computes it:

```
crop=iw/S:ih/S:CX*iw-iw/(2*S):CY*ih-ih/(2*S),scale=W:H:flags=lanczos
```

So `cy` 0.4 puts the crop centre at 40% of the frame height; take it from the median face centre (`thumbvision faces`), then make sure the crop stays inside the frame.

---

## 7. B-roll and screen inserts

1. **Every abstract claim and every RISULTATO gets visual proof**: the chart, the dashboard, the product screen (claim ledger `03` §11). [anecdotal]
2. **When a company, product or person is named, show it** if rights allow (practitioner pattern [vendor]: vidpros).
3. **No stock footage as evidence.** Illustrative B-roll only if obviously illustrative; never generic "people typing" presented as the guest's company.
4. **Readability**: hold a screen ≥3 s plus ~1 s per line of text the viewer must read; box or zoom the relevant area. [anecdotal — house default]
5. **Audio keeps running** under B-roll; never cover the speaker's face at an emotional peak or a punchline (emotion first, §3.4).
6. **Privacy and consent**: blur customer names, emails and third-party revenue; the guest approves every on-screen number; each asset has a rights-ledger row (`03` §11.3).
7. **Screen recordings**: native resolution, project frame rate, steady cursor; for web products a Playwright recording is fine (SYNTHESIS §7B).
8. **Mode M**: a full-canvas insert replaces the brand frame; keep each insert ≤8 s and return to the layout (house default). Window-box inserts wait for a rebuilt layout (Mode I).
9. **Placement**: `overlays[]` entries (`file`, `at` in output seconds), shifted per rule 4 of §1.
10. **Cadence**: practitioner ranges disagree (a visual change every 15–30 s, 20–40 s or 30–90 s); none is evidence. Derive the cadence from the channel's own dips (`09-analytics-reading.md`). [anecdotal]

---

## 8. Multicam doctrine (Mode I)

Mode I needs camera ISOs + per-mic files (profile `recording.capture_checklist`). Without them the switch is baked into the master and this section is reference. Sources: multicam doctrine paraphrased from 10xcoldleads/multicam-podcast-editor-skill (no licence: ideas only) and F2 §7.2 [anecdotal].

### 8.1 Sync

- The studio/dialogue audio is the master clock.
- Sync each camera by cross-correlating its scratch-audio envelope (mono 16 kHz) with the master; verify at two known speech windows.
- Drift: compare offsets at the start and the end; more than 1 frame of difference → resample (`setpts`/`atempo`) or re-sync per chapter.
- Conform VFR to CFR first; all cameras at the same fps. Watch for a reversed offset sign.

### 8.2 Speaker timeline

Per-mic RMS in 50 ms windows, gate around −45 dBFS, hysteresis (min speech 250 ms, min silence 300 ms), loudest track wins by ≥6 dB to reject bleed. Thresholds are tuning starting points, not constants. Words in overlap regions get `speaker = OVERLAP` (drives the wide shot).

### 8.3 Shot rules

| Situation | Shot |
|---|---|
| Default | Active speaker's close-up |
| New speaker | Switch only after they have spoken ≥1.0–1.5 s (ignore «sì», «esatto», laughs) |
| Picture timing | Cut picture 4–8 frames before the new speaker's first word (J-cut); never inside a word |
| Minimum shot | ~2.5–3 s |
| Long monologue | Max ~20–30 s on one shot → insert a 2–4 s listener reaction or the wide |
| Crosstalk, turns <2 s, group laughter | Wide / two-shot |
| Reaction shots | Only when they add meaning (surprise, disagreement, a laugh) |
| Cold open and first 30 s | Tighter, more frequent switching |
| Geography reset after a long close-up stretch | Wide for 2–4 s |

Emit a camera EDL (`[{cam, start, end, reason}]`), render with the master audio (camera scratch muted, so no per-segment audio fades where audio is continuous), or export for human review (§15).

### 8.4 QC

No shot under the minimum; every switch on a word boundary; A/V sync checked on the **encoded** output at one host moment and one guest moment.

---

## 9. Composited masters: Mode M vs Mode I

Many video podcasts arrive as a **composited master**: a branded canvas (a background, a video window with rounded corners, a picture-in-picture) where the production team has already switched between a wide shot and a single-person inset. The agent then works in **Mode M** (post-production of that master). With the camera ISOs and per-mic files it works in **Mode I** (rebuild from the sources). The channel profile records which mode applies (`recording.mode_current`).

### 9.1 What to measure on a new master (once per layout template)

| Property | How | Why it matters |
|---|---|---|
| Video | `yt-ingest` → `analysis/inventory.json` (codec, size, fps, transfer, bitrate, duration) | Encode presets, HDR/SDR handling (§12.4) |
| Canvas and window states | `yt-clips layout <workdir> --measure --inset-at T --wide-at T [--card-at T] --write` → the brand's `layout.json` | Overlay positions, Shorts crops, thumbnail ROIs |
| PiP | same | Must never appear in a Short (`08` §9.2) |
| Faces | `thumbvision faces` on a few frames | In a 4K composite, faces are often ~250 px tall: thumbnails then need the tight camera (`07` §10.1) |
| Audio | `yt-ingest` balance profile and loudness | Mixed tracks often carry two mics on two channels with a varying imbalance, over-compression and sample peaks above 0 dBFS (§10.3, §11) |
| Decode errors | `yt-ingest` integrity pass (`corrupt_spans`, `audio_decode`) | Decoder choice (§11) and spans to avoid in cuts and Shorts |

Observed on the probe master behind the rules below [anecdotal, local probe, n=1]: 3840×2160 HEVC Main 10, SDR BT.709, 30 fps; a coloured canvas with a rounded window alternating **W** (a wide multi-person shot) and **I** (a vertical guest inset filling about half the canvas width); a small wide-shot PiP in a corner; faces ~250 px tall; one stereo AAC track with two mics on two channels and an imbalance that varied from ≈ −11.5 dB to ≈ −4 dB along the episode; about −11 LUFS, LRA ~2 LU, peaks above 0 dBFS; one short corrupt video span with AAC decoder errors next to it. Measure every new master: none of these numbers is a default.

### 9.2 What each mode allows

| Operation | Mode M (post-process the composited master) | Mode I (camera ISOs + mic tracks) |
|---|---|---|
| Content cuts | Cut the master; prefer cut points at native layout switches (W ↔ I); inside one state a jump cut is visible and is accepted for conversation | Cut on the master audio timeline; camera chosen per §8 |
| Punch-ins | Not on the canvas (§6 rule 5) | Inside the window, via the layout composition |
| Camera choice | None (baked) | Multicam doctrine §8 |
| Split edits | Only via overlays (§3.5) | Yes |
| B-roll | Full-canvas, ≤8 s | Inside the window or full-canvas |
| Lower thirds, cards | Overlaid in the canvas area, never over faces; positions from the measured layout file (§9.3) | Part of the layout composition |
| Audio | One mixed track: decode with the decoder chosen by `yt-ingest` (§11) → balance fix → no extra compression → loudnorm (§10) | Per-mic chain (§10.2) then mix |
| Diarization | Senko on the mixed track (`yt-speakers`) | Per-mic RMS (§8.2) |
| Shorts | Crop state I near-natively; per-speaker 9:16 crops of state W; see `08` | Crop the ISO (1215×2160 strip from 4K) |
| Thumbnails | Faces often too small: tight camera, ISOs, or the display cap with a QA gate (`07-thumbnails.md` §10.1) | 4K ISO frames |

### 9.3 Layout files

- **Geometry per brand template**: `yt-clips layout <workdir> --measure --inset-at T --wide-at T [--card-at T] --write` measures the inset window, wide window, PiP, corner radii and colour signatures from 4K frames and writes `layout.json` into the channel's brand folder (`<brands_dir>/<slug>/`, `07` §8). Re-measure whenever the production template changes.
- **Spans per episode**: `yt-clips layout <workdir>` detects which state (inset / wide / card) each stretch of the source is in → `shorts/layout_spans.json`.
- Overlays and Shorts crops read positions from the measured files, never from approximate numbers.

### 9.4 Open hypothesis, not a rule

In an inset state most of the 16:9 frame can be background (about 70% on the probe master). Whether this hurts TV/desktop viewers is untested: compare full-frame 16:9 vs inset for long-form (`02` §12.7, E3) before changing the layout. Keep the inset for Shorts.

### 9.5 Rebuilding the layout (Mode I)

With ISOs, the channel's layout becomes a brand composition: in Remotion for own and personal channels within the licence (design §11; `graphics_licence` in the profile), otherwise in HyperFrames (Apache-2.0).

---

## 10. Audio chain and loudness

### 10.1 Targets

| Deliverable | Integrated | True peak | LRA | Label |
|---|---|---|---|---|
| YouTube long-form master | −14 LUFS (±0.5) | ≤ −1.5 dBTP | ≤ 11 LU | [anecdotal] — community-observed normalisation reference; YouTube publishes no figure (F2 §4.1, sources productionadvice, MeterPlugs, Youlean) |
| Spotify video master | same as YouTube | ≤ −1.5 dBTP | ≤ 11 LU | [anecdotal] — no official Spotify LUFS figure found |
| Shorts | −14 LUFS | ≤ −1.5 dBTP | — | [anecdotal] |
| Audio-only RSS master (Apple Podcasts) | −16 LKFS ±1 dB | ≤ −1 dBFS true peak | — | [official] https://podcasters.apple.com/support/893-audio-requirements — verified 2026-10-11 (ITU-R BS.1770-5) |

The design doc success criterion uses −14 ±0.5 LUFS for the test render.

### 10.2 Chain, in order

| Step | What | Filter / command (ffmpeg-full) | Composited master (Mode M) | Raw mics (Mode I, solo talking head) |
|---|---|---|---|---|
| 0 | Decode (AAC decoder policy) | decoder from `project.json` `audio_decoder` (§11): native = no flag, `aac_at` = `-c:a aac_at` before `-i`; always `-af aresample=async=1:min_hard_comp=0.02:first_pts=0`; float (`pcm_f32le`) intermediates | always (usually native) | n/a (WAV/PCM) |
| 1 | Balance | `yt-loudnorm … --balance auto|mono|none` (§10.3) | `auto` or `mono` (expect a varying 4–12 dB imbalance; read the report's decision) | `none` |
| 2 | High-pass | `highpass=f=80` | yes | yes |
| 3 | Denoise (only if noisy) | `afftdn=nf=-25` (steady hiss) or `arnndn=m=<bd.rnnn>:mix=0.85` (non-stationary) | no — the problem is over-compression, not noise | only if measured noise |
| 4 | De-ess (only if audible) | `deesser=i=0.4:m=0.5:f=0.5` | rarely | if sibilant |
| 5 | Compression | `yt-loudnorm --chain gentle` (= highpass 80 Hz + 2:1 compression around −18 dBFS); heavier manual starting point for raw mics: `acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=2` | **skip** when the master is already compressed (`--chain none`, the default; e.g. LRA ~2 LU) | yes, light |
| 6 | Segment fades | 30 ms in/out at each boundary (§1 rule 3) | yes | yes |
| 7 | Music ducking | `sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350:makeup=1` on the bed keyed by voice; bed pre-gain ~0.35 | if music | if music |
| 8 | Two-pass loudnorm | `yt-loudnorm IN OUT --target -14 --tp -1.5 --lra 11` | yes | yes |
| 9 | QC | `ebur128=peak=true` on the **encoded** file | yes | yes |

Values are starting points from F2 §4 [anecdotal]; tune by ear on phone and laptop speakers. Ducking target: bed about 12–15 dB under its music-only level while speech is present; fade the bed out before a stinger or the end plate instead of letting it tail under the CTA.

Two-pass loudnorm (what `yt-loudnorm` wraps):

```bash
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
$FF -hide_banner -i edit/mix.raw.wav -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null - 2> logs/ln1.txt
# parse input_i, input_tp, input_lra, input_thresh, target_offset
$FF -hide_banner -i edit/mix.raw.wav -af "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=$I:measured_TP=$TP:measured_LRA=$LRA:measured_thresh=$TH:offset=$OFF:linear=true:print_format=summary" -ar 48000 -c:a pcm_s24le edit/mix.wav
# (illustration of what the tool wraps; in practice: yt-loudnorm edit/assembled.mov edit/mix.wav --target -14 --tp -1.5 --lra 11)
```

ffmpeg facts (https://ffmpeg.org/ffmpeg-filters.html, research pass 2026-10-11) [official]: `loudnorm` defaults are I −24 / LRA 7 / TP −2; linear mode needs all measured values, otherwise it falls back to dynamic mode; dynamic mode upsamples to 192 kHz, so always set `-ar 48000`. If pass 2 reports a fallback to dynamic (source LRA above target), raise LRA or compress upstream.

### 10.3 Balance decision (`yt-loudnorm --balance auto`, as implemented)

`yt-loudnorm` analyses the two channels (active-speech level difference, energy-weighted L↔R cross-correlation and lag, per-block dominance) and explains its choice in the report (`<OUT>.loudnorm.json`). Read the decision; never assume it.

| Measured situation | Decision |
|---|---|
| One channel silent or nearly (< −60 dB, or > 30 dB apart) | Mono from the active channel |
| Same signal: correlation ≥0.95, lag ~0, difference >3 dB | Mono from the louder channel (summing would only add a quieter copy) |
| Two mics on two channels: each dominates by >6 dB in ≥5% of the speech, with mutual bleed | **Automix** mono with gain sharing (Dugan-style) and aligned mic levels; output dual-mono. Keeping only the louder channel would lose a speaker; a plain sum creates comb filtering |
| Different signals, difference >3 dB, no two-mic pattern | Pan rebalance, stereo kept (`--balance mono` sums to mono instead) |
| Difference ≤3 dB | No change (`mono` → average) |

For spoken podcasts `--balance mono` is the recommended choice (identical speech in both ears). Explicit overrides: `automix`, `left`, `right`, `average`, `rebalance`. Thresholds are the tool's defaults [anecdotal]; the QA report quotes the measured values and the decision.

### 10.4 Audio QC tolerances

- Integrated −14 ±0.5 LU; true peak ≤ −1.5 dBTP; LRA ≤ 11 LU.
- Audio and video durations within 100 ms (practitioner gate, F1 K-15 [anecdotal]).
- No click at any cut (§16), no truncated laugh, music bed silent under the most important line.
- After upload (the operator, manual): Studio "Stats for nerds" content loudness; a positive value means YouTube turns the video down by that amount [anecdotal].

---

## 11. AAC decoder policy — decoding is not encoding

**Changed 2026-10-11.** The old rule «always decode masters with `-c:a aac_at`» is withdrawn. The toolkit has one decision point, `ytcore.aac_decoder_policy` / `ytcore.aac_decoder_args`, and every command (`yt-ingest`, `yt-edl-render`, `yt-loudnorm`, `yt-clips`, `yt-chapters`, `yt-timeline-view`) uses it.

**Why the rule changed** [anecdotal, local probe, n=1 master, FX1 + V tests 2026-10-11]:
- `aac_at` (AudioToolbox) always decodes to **s16**, so a master's peaks above 0 dBFS are clipped flat. On the probe master the native decoder kept thousands of samples above full scale (peak ≈ +0.6 dBFS on a 3-min excerpt) that `aac_at` flattened at 0.000 dBFS.
- FFmpeg's native `aac` decoder decodes to **float** (no clipping). On the probe master its only errors (a burst of «channel element duplicate») sat about 1 s after a corrupt video span. There it drops the bad packets; with `aresample` async the hole becomes silence and the timeline stays the container's (full master: WAV duration = container, Δ 0 ms).
- At such a point the audio is lost in the master whichever decoder you use: both gave ~0.5 s of digital silence in the middle of speech. After the bad packets `aac_at` ran one AAC frame (−23.2 ms) early; the native decode matched a fresh decode started after the error (0.000 ms).

**Decision rule (`yt-ingest`, `ytcore.decide_aac_decoder`)**: the audio pass runs with the native decoder and records the time of every error; a second pass counts `aac_at` errors. After the video integrity pass:
- **native** if the native decoder has no errors, or if all its errors fall within ±3 s of a `corrupt_spans` entry (the probe master: native, verified on the full master 2026-10-11);
- **`aac_at`** otherwise, or when there are native errors and the integrity pass was skipped (`--no-integrity`).

The decision and its reason go to `analysis/inventory.json` `audio_decode` (`decision`, `decision_reason`, `native_aac_error_times`, `aac_at_errors`, peaks, `wav_delta_ms`) and to `project.json` (`audio_decoder`, `audio_decoder_reason`, `audio_decoder_by_source`).

**Policy for any later decode (`ytcore.aac_decoder_policy`, in order)**:
1. Non-AAC audio → native (`aac_at` only decodes AAC).
2. `YT_AAC_DECODER=native|aac_at` forces a decoder (`auto` or unset = no override).
3. A project's own source → the decision in `project.json` (or derived from `inventory.json`).
4. Any other file inside a workdir but outside `src/` (proxy, `assembled.mov`, deliverables, Shorts) → native: the toolkit encoded it.
5. Any other AAC file → a one-time native test decode (cached in `<studio_dir>/cache/aac-decoder/`): native if it has no errors, otherwise `aac_at`. On a 53-min master this is a full decode; ingest the file first.

**Rules for the agent**:
- Never hard-code `-c:a aac_at`. In a manual ffmpeg call, ask the policy for the decoder and add the async filter and a float intermediate:

```bash
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
YTPY="$(yt-config --get venv_python)"; YT_LIB="$(yt-config --get plugin_root)/scripts/yt/lib"
DEC=$("$YTPY" -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import ytcore; print(ytcore.aac_decoder_policy(sys.argv[2])["decoder"])' "$YT_LIB" <wd>)
if [ "$DEC" = aac_at ]; then A=(-c:a aac_at); else A=(); fi
$FF -hide_banner "${A[@]}" -i <wd>/src/<master> -vn -af "aresample=async=1:min_hard_comp=0.02:first_pts=0" \
  -ac 2 -ar 48000 -c:a pcm_f32le <out>.wav
```

- Kept ranges that cross `audio_decode.native_aac_error_times` (±0.6 s) may contain ~0.5 s of silence: treat them like a corrupt span in the G1 brief and listen to them.
- If an older workdir has WAVs made with the other decoder, `yt-ingest` sets `wav_decoder_mismatch: true` and does not overwrite them when a transcript exists: run `yt-ingest <wd> --force`, then `yt-transcribe` and `yt-speakers` (the audio hash changes, so whisper runs again).
- Audio intermediates are float32 (`analysis/audio48k.wav`, `edit/.render` segments, the audio of `edit/assembled.mov` as `pcm_f32le`), so the peaks above 0 dBFS survive until `yt-loudnorm`. `edit/mix.wav` (after loudnorm) stays 24-bit.
- `yt-doctor` still checks that the `aac_at` decoder exists: it is the fallback.

**Encoding is a separate matter (unchanged)**: the delivery `deliver/<slug>-master.mp4` and `yt-loudnorm … .m4a` use the `aac_at` **encoder**, AAC-LC CBR 320k, 48 kHz (§12.1); Shorts (192k) and the proxy (128k) use the native `aac` encoder. Both encoders are in ffmpeg-full on Apple Silicon (checked 2026-10-11).

---

## 12. VideoToolbox encoding

### 12.1 Presets (`yt-edl-render --preset`)

| Preset | Use | Video (as implemented in `yt-edl-render`, 2026-10-11) | Audio | Measured speed (M5, 4K HEVC source) |
|---|---|---|---|---|
| `master4k` | Long-form master | Native canvas, `hevc_videotoolbox -profile:v main10`, 10-bit, `-q:v 70` default (calibrate 65–72, §12.4), `-tag:v hvc1` | `--deliver`: AAC-LC 320 kbps CBR via the `aac_at` encoder (its stereo maximum), 48 kHz, from `edit/mix.wav`. YouTube recommends 384 kbps stereo (§12.3) [official]; for speech the gap is not audible [judgment] | 2.2× realtime at q 65 → ~24 min for 53 min |
| `1080p` | Review copies, 1080p deliveries | 1920×1080, `h264_videotoolbox` High, 16 Mbps | AAC 192–384 kbps | 6.3× realtime → ~8.5 min |
| `proxy` | Analysis and listen checks | 1280×720, `h264_videotoolbox`, 5 Mbps | AAC | fast |
| H.264 4K (manual alternative) | When an H.264 master is required | `h264_videotoolbox` at 35–45 Mbps (8-bit only) | AAC-LC 384 kbps | not benchmarked at 4K |
| Shorts (`yt-clips render`) | 1080×1920 | `libx264 --crf 18` default (short clips only) or `h264_videotoolbox` | AAC 192 kbps, 48 kHz | — |

Benchmarks: SYNTHESIS §10.1, local 2026-10-11 [anecdotal, local probe]: VT 4K HEVC decode 7.4× RT; `libx264 -preset slow -crf 18` at 4K 0.42× RT (~2 h 6 min per episode) → **never libx264 for full 4K episodes**.

### 12.2 Commands (what the render helpers do)

```bash
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
# one kept range → intermediate segment (VT decode, VT encode); "${A[@]}" = AAC decoder from the policy (§11):
# empty when the policy says native (float), (-c:a aac_at) only if yt-ingest chose it. The helper renders the audio
# of each segment as a separate float WAV (exact N·48000/fps samples) and joins it at the concat.
$FF -hide_banner -y -hwaccel videotoolbox -ss $IN -to $OUT "${A[@]}" -i src/master.mp4 \
  -vf "$CROP_OR_ZOOM_CHAIN" \
  -af "aresample=48000:async=1:min_hard_comp=0.02:first_pts=0,afade=t=in:st=0:d=0.03,afade=t=out:st=$((DUR-0.03)):d=0.03" \
  -c:v hevc_videotoolbox -profile:v main10 -pix_fmt p010le -q:v 65 -tag:v hvc1 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  -c:a pcm_f32le -ar 48000 edit/seg_0001.mov
# lossless join (identical codec params, fps, size, pix_fmt)
printf "file '%s'\n" edit/seg_*.mov > edit/concat.txt
$FF -f concat -safe 0 -i edit/concat.txt -c copy edit/assembled.mov
# final mux with the normalised mix (video stream copied: colour tags were set at encode time);
# here aac_at is the ENCODER (CBR 320k), not the decoder
$FF -i edit/assembled.mov -i edit/mix.wav -map 0:v -map 1:a -c:v copy \
  -c:a aac_at -aac_at_mode cbr -b:a 320k -ar 48000 -movflags +faststart deliver/<slug>-master.mp4
# (what `yt-edl-render <wd> --preset master4k --deliver` does)
```

(`$((DUR-0.03))` stands for the computed value; the helper writes the number. Verify the tags on the delivered file with `ffprobe -show_entries stream=color_primaries,color_transfer,color_space`.)

### 12.3 YouTube's recommended upload settings

Source: https://support.google.com/youtube/answer/1722171 — verified 2026-10-11 [official].
- Container MP4, no edit lists, moov atom at the front (fast start).
- Audio AAC-LC, Opus or Eclipsa Audio, 48 kHz; 128 kbps mono, 384 kbps stereo.
- Video H.264 High Profile, two consecutive B-frames, closed GOP of half the frame rate.
- SDR bitrates: 2160p 35–45 Mbps (24/25/30 fps) or 53–68 Mbps (48/50/60); 1440p 16 / 24; 1080p 8 / 12.
- SDR colour: BT.709 primaries, transfer and matrix.
- HEVC, ProRes and other codecs are accepted uploads (supported formats page, research pass 2026-10-11), so a 4K HEVC 10-bit master is valid even though H.264 is the recommendation.

### 12.4 Rules

1. `-q:v` constant quality works only on Apple Silicon; `-crf` is ignored by VideoToolbox; if both `-q:v` and `-b:v` are set, `-q:v` wins silently (third-party notes, F2 §11.3) [anecdotal].
2. **Calibrate `-q:v` once per machine**: encode a 60 s 4K sample at q 60/65/70/72, read the bitrate with ffprobe, pick the lowest q whose bitrate is ≥35 Mbps for a 4K30 SDR master (YouTube's recommended band as the floor). Store the value in the agent's `MEMORY.md` (tool versions block).
3. Always `-tag:v hvc1` for HEVC in MP4/MOV (QuickTime/Apple compatibility).
4. All segments share fps, size and pixel format, or the copy-concat breaks.
5. Tag BT.709 on SDR outputs. HLG sources (`color_transfer=arib-std-b67`) need tone-mapping with `zscale` before an SDR master; check `inventory.json` before the first render.
6. Analyse on proxies, render from originals with the same timestamps.
7. Disk and time: intermediates take 15–25 GB per pass; `yt-doctor` requires ≥60 GB free; long renders run in the background with a completion check; intermediates are cleaned after delivery (never `src/`).

---

## 13. Graphics compositing

- **Engine by channel** (design doc §2, channel profile `graphics_engine`): **Remotion** for own and personal channels within the licence (`graphics_licence` confirmed), rendered with `yt-remotion render <COMPOSITION> --props <file> --out <file.mov> --codec prores` (`.mov` = ProRes 4444 with alpha). Compositions registered today (`yt-remotion list`): `LowerThird`, `ChapterCard`, `ColdOpenTitle`, `IntroSting`, `EndPlate` (16:9), `ShortCaptions` (1080×1920), `ThumbnailStill` (still, `--scale 3` → 3840×2160). **HyperFrames** for talking-head recut, captions behind the subject, and every client deliverable (licence: design doc §11 and `vendor/REMOTION_LICENSE_NOTE.md`).
- **Alpha delivery**: ProRes 4444 (`yuva444p10le`) or VP9 WebM (`yuva420p`, alpha mode on); verify the alpha by decoding one frame before compositing (iart-ai practice [anecdotal]).
- **Order**: base video → B-roll → graphics overlays → captions last (§1 rule 1).
- **Lower thirds** (iart-ai lower-third craft [anecdotal]): inside title-safe (≥5% from every edge; their template uses 6%); name ~50–80 px tall at 1080p (×2 at 4K), role about half; text on its own backing; still while read, motion only in build-in and build-out; first and last frames empty; auto-fit long names; lining numerals; ~8 s default. Guest lower third once, after the hook, ~6–8 s (vidpros [vendor]).
- **Chapter cards**: Italian curiosity-gap titles («Il cliente che ha cambiato tutto», never «Parte 2»), 2–3 s, consistent with `deliver/chapters.txt`.
- **Intro sting**: ≤3 s, logo hit within 1–2 s, the loudest transient of the audio on the impact frame (iart-ai [anecdotal]); default none until tested (`04` §7.1).
- **End plate**: end screens use the last 5–20 s of a video ≥25 s with up to 4 elements (https://support.google.com/youtube/answer/6388789, research pass 2026-10-11 [official]); brand in the left third, the right two-thirds left free for elements (iart-ai [anecdotal]).
- **Brand tokens**: the channel's brand folder in the operator's `brands_dirs` (`<brands_dir>/<slug>/tokens.json`, `07` §8), or the neutral built-in brand `demo` (`scripts/yt/assets/brands/demo/`: `ink`, `paper` and three accents `accent`, `accent_2`, `accent_3`; Anton for headlines, Inter for body). Text pairs come from the brand's `text_pairs_allowed` and the profile's `brand` block; copy from `copy_rules`. Never pick colours by eye.
- **Fonts fail silently** in HTML-based renders: assert that fonts are loaded before rendering (video-use practice [anecdotal]).
- **Language**: one language per graphic; English only for proper names and community terms (house rule).

---

## 14. Music and SFX licensing

| Source | YouTube | Spotify and other platforms | Conditions | Label |
|---|---|---|---|---|
| YouTube Audio Library | Yes; downloads are not claimed through Content ID; monetisable for YPP channels | No guidance from YouTube for off-platform use → treat as **YouTube-only** | Creative Commons tracks must be credited in the description (copy the text from the library); filter "Attribution not required" to avoid it | [official] https://support.google.com/youtube/answer/3376882 — verified 2026-10-11 |
| CC0 (e.g. Freesound SFX, Jamendo CC0) | Yes | Yes | Keep the source URL in the rights ledger | [anecdotal] (licence policy idea from publikclip) |
| CC-BY | Yes, with credit | Yes, with credit | Credit text in the description; rights ledger row | [anecdotal] |
| CC-BY-NC, CC-BY-ND, "royalty-free" without a written licence | **Never** (a business channel is commercial use; ND forbids edits) | Never | — | — |
| ElevenLabs music / SFX | Paid: main session only, after explicit approval and a cost check; never inside the agent | — | Design doc §2 decision 6 | — |

Rules [anecdotal unless marked]:
1. Spotify video episodes need music whose licence explicitly covers all platforms; when unsure, cut the music from the Spotify version.
2. **Cut the music under the most important line** so it lands.
3. Bed ~12–15 dB under speech (§10.2); fade before the end plate.
4. **Music taste is the operator's call**: offer two contrasting options, never decide alone (video-use practice).
5. **SFX discipline**: tie every effect to a visible event; few effects in talk formats; start the SFX file so its transient hits the contact frame.
6. Every track and effect gets a rights-ledger row (`03` §11.3) before it enters `edl.json` `music[]`.

---

## 15. NLE hand-off (FCPXML)

Command: `yt-export-nle <workdir> --format fcpxml` → `deliver/<slug>.fcpxml` (FCPXML 1.10, `--fcpxml-version 1.11` optional), built from `edit/edl.json`. Without `--format` (or with `--format fcpxml,edl`) it also writes `deliver/<slug>.edl`, a CMX3600 cut list (cuts only, clip name and path in `* SOURCE FILE` comments): the universal fallback. As implemented (`--help`, 2026-10-11) the FCPXML carries one `asset-clip` per segment (same frames as `yt-edl-render`, rational times N/fps), punch-ins as `adjust-transform`, overlays on lane 1, music on lane −1 (role music, volume), and the chapters of `edit/chapters.draft.json` as `<marker>` (or `<chapter-marker>` with `--chapter-markers`, Final Cut only). It does not use auto-editor.

What the package should carry (verify against the actual export on the first episode):
- The cut list on the **original source media** (absolute paths; `src/` symlinks resolved), in output order.
- Overlays and cards as clips referencing `edit/overlays/*` (alpha ProRes).
- The finished mix `edit/mix.wav` is not referenced by the export: if the operator wants to finish picture without redoing sound, hand it over next to the FCPXML and say so in the delivery note.
- Captions and chapters as separate files in `deliver/` (`<slug>.it.srt`, `<slug>.it.vtt`, `chapters.txt`), imported manually.
- Zooms and loudness may not travel as editable effects; the QA report states what did not translate.

Acceptance test (design doc §12: "FCPXML che si apre"): open it in at least one NLE; duration equals `edit/assembled.timeline.json` within one frame; spot-check three cuts; media relinks without prompts. Moving the originals (e.g. out of `~/Downloads`) breaks relinking.

Targets:
- **Final Cut Pro**: native FCPXML.
- **DaVinci Resolve (free)**: timeline import via the File/Media Pool import menus works for a human according to third-party sources; external and (since 21.1) in-app Python scripting are Studio-only (third-party: davinci-resolve-mcp maintainers) [anecdotal] — the operator tests manually.
- **Kdenlive** (vetted, GPL-3.0, `brew install --cask kdenlive`): import through OpenTimelineIO (FCPXML) or the CMX3600 `.edl` from `yt-export-nle`; auto-editor's single-source `--export kdenlive` is a fallback. Do not assume it opens FCPXML.

auto-editor licence gates (V2 §0.1, code read 2026-10-11) [anecdotal]: renders above 3200×1800 are downscaled without a key (31.7.2: a 3840×2160 render becomes 2880×1620); multi-source renders are capped at 720×576; multi-source timeline exports and the `add` action need a paid key. **Use auto-editor only for analysis (`--preview`, `levels`), single-source cut lists and single-source exports; never for final renders.**

---

## 16. Self-eval loop at every cut

Run after every render of `edit/assembled.mov` (and every Short). Max **3 passes**; then the critic; only then the operator sees it.

### 16.1 Procedure

1. List every cut boundary from `edit/assembled.timeline.json` (each `out_start` > 0).
2. For each boundary T: `yt-timeline-view <workdir> --at T --window 3 --source edit` → `qa/timeline_view/<T>.edit.png` (filmstrip + waveform + word labels, ±1.5 s; source-timeline views are `<T>.png`). Several boundaries in one call: `--at 38.8,95.2,141.0`. Read every image.
3. Global views: `--at 1` and `--at <duration−1>` (first and last 2 s); the midpoint of every segment longer than 60 s.
4. Measure: `ebur128=peak=true` on the encoded file; ffprobe duration vs the EDL sum (±100 ms); A/V sync at one host and one guest moment (word timestamp vs mouth movement on extracted frames, `yt-frames --times`).
5. Fix in `edl.json` → re-render only the affected segments (idempotent commands) → repeat from step 2 for those boundaries.

### 16.2 Per-cut checklist

- [ ] No clipped syllable (waveform shows no truncated energy; first/last words complete in the transcript).
- [ ] No click (fades present; no DC jump in the waveform).
- [ ] No flash frame (no shot shorter than 3 frames at the boundary).
- [ ] Pause length within the format target (§4.3); hand-off air 400–600 ms.
- [ ] Laugh not truncated.
- [ ] Mode M: no layout jump mid-word; layout state change lands on a word boundary.
- [ ] Overlays and captions don't straddle the cut unintentionally; captions not over faces (Shorts).
- [ ] The connector logic still holds (no orphan «quindi» after a removed cause).

### 16.3 Critic sub-agent brief

Inputs: path of the render, `edit/edl.json`, `edit/assembled.timeline.json`, `project.json`, `qa/timeline_view/*.png`, loudness report. Task: list problems ranked by severity (blocker / major / minor) with output timecodes and a proposed EDL fix; check the `04` §10 checklist for the format; check every on-screen number against the claim ledger. The critic never edits files. Output appended to `qa/report.md` (Italian).

### 16.4 Stop rule

After 3 passes, stop even if minor issues remain; list them in `qa/report.md` under «Problemi aperti» with timecodes, so the operator can decide or finish in the NLE (§15).

---

## 17. Edit notes table (Italian) → `edl.json`

The G1 brief and the QA report use this table; each row maps to the JSON.

```markdown
| TC in (sorgente) | TC out (sorgente) | Azione | Motivo | Beat | Note |
|---|---|---|---|---|---|
| 00:12:04.20 | 00:13:40.00 | CUT | domanda ripetuta | TANGENTE | — |
| 00:23:20.15 | 00:23:29.60 | MOVE → cold-open-3 | svolta, tagliata prima della risposta | SVOLTA | si risolve a 23:31 |
```

| Azione | `edl.json` |
|---|---|
| KEEP | a `segments[]` entry |
| CUT | absence of a segment for that range |
| MOVE | segment order (labels `cold-open-N`, `framing`, `chNN-…`) |
| PUNCH | `zoom` on the segment |
| BROLL / TEXT | `overlays[]` entry |
| MUSIC / SFX | `music[]` entry (`gain_db`, `duck`) |
| JCUT / LCUT | Mode M: overlay technique (§3.5); Mode I: camera EDL or NLE |
| TIGHTEN | split the segment around the removed middle of the gap (§4.3) |

---

## 18. Sources

- video-use SKILL.md (MIT, pinned 43cfc566) — https://github.com/browser-use/video-use/blob/main/SKILL.md [anecdotal]
- remotion-dev silence-detection reference — https://github.com/remotion-dev/skills/blob/main/skills/remotion-markup/silence-detection.md [anecdotal]
- multicam doctrine (no licence, ideas only) — https://github.com/10xcoldleads/multicam-podcast-editor-skill [anecdotal]
- clipify (MIT) — https://github.com/louisedesadeleer/clipify [anecdotal]
- iart-ai lower thirds and intro/outro skills (MIT) — https://github.com/iart-ai/lower-thirds-skills , https://github.com/iart-ai/youtube-video-skills [anecdotal]
- auto-editor (Unlicense + paid gates) — https://github.com/WyattBlue/auto-editor [anecdotal]
- FFmpeg filters documentation — https://ffmpeg.org/ffmpeg-filters.html (research pass 2026-10-11) [official]
- YouTube recommended upload encoding settings — https://support.google.com/youtube/answer/1722171 (verified 2026-10-11) [official]
- YouTube Audio Library — https://support.google.com/youtube/answer/3376882 (verified 2026-10-11) [official]
- YouTube end screens — https://support.google.com/youtube/answer/6388789 (research pass 2026-10-11) [official]
- Apple Podcasts audio requirements — https://podcasters.apple.com/support/893-audio-requirements (verified 2026-10-11) [official]
- Spotify video specs — https://support.spotify.com/us/podcasters/article/video-specs/ (research pass 2026-10-11) [official]
- Loudness observation — https://productionadvice.co.uk/stats-for-nerds/ , https://www.meterplugs.com/blog/2019/09/18/youtube-changes-loudness-reference-to-14-lufs.html , https://youlean.co/?p=30813 [anecdotal]
- VideoToolbox `-q:v` notes — https://slhck.info/video/2017/02/24/vbr-settings.html , https://yre.jp/en/post/m1mac_h265/ [anecdotal]
- J/L cuts — https://en.wikipedia.org/wiki/J_cut , https://vimeo.com/blog/post/j-cuts-l-cuts [anecdotal]
- Research (2026-10-11 archive, not distributed: `../research/README.md`): `F2-editing-toolchain.md` §3–§15; `F1-agent-layer.md` K-11–K-16, K-22–K-23; `V1-vetting.md` K1, K3; `V2-vetting.md` §0–§1; `SYNTHESIS.md` §1.3, §2.3, §7A–§7B, §10.1; design doc `DESIGN.md` (docs/yt) §8, §11.
