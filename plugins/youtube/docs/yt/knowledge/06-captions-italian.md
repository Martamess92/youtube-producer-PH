# 06 — Italian captions and on-screen text

## How the skills use this file

- `youtube:edit` reads §0–§5 before generating sidecars (`yt-captions <workdir> --format srt,vtt`) and §8 for cards, lower thirds and text hooks.
- `youtube:shorts` reads §3.3, §4, §6 and §7 (burned captions, preset `default` and the presets of the channel's brand, safe zone) before G2 and in the frame QA.
- `youtube:story` and `youtube:edit` read §4 when they build the G1 flag list: fillers are flagged, causal connectors are never cut.
- `youtube:hook`, `youtube:thumbnail` and `youtube:chapters` read §8–§9 for every Italian string they put on screen; §9 is the checklist the agent applies to its own Italian copy (never to verbatim guest quotes).
- The critic and the QA pass use §10. Method in English; every caption, card and QA note in Italian.

Status: written 2026-10-11 from F2 §2.2 and §5, F5 §9.3–§9.4, SYNTHESIS §2.3 and §2.7, the Netflix Italian and General timed-text guides (fetched and verified 2026-10-11), and the implemented toolkit (`scripts/yt/lib/captions.py` in the plugin, the caption presets in `assets/ass/`, Remotion `ShortCaptions`), read on 2026-10-11. **Updated 2026-10-12** (§1, §2.2, §3.1, §3.4, §4.3–§4.5, §5, §10) with the sidecar builder v2 and the transcription pipeline measured in the 2026-10-12 tests (X1 engines/timing, X2 glossary/post-correction, X3 subtitles; one 53-min Italian interview episode — «the test episode» below — against a silver reference; internal logs, not distributed). Where the toolkit and this file disagree, §4.4 and the return notes say so. Evidence labels: [official] [study] [vendor] [anecdotal].

---

## 0. Which text, which file, which engine

| Text | Deliverable | Engine | Rules |
|---|---|---|---|
| Long-form captions (every channel) | Sidecar `deliver/<slug>.it.srt` and `deliver/<slug>.it.vtt`, uploaded by the operator in Studio (G3) | `yt-captions <workdir> --format srt,vtt` (output timeline via `edit/assembled.timeline.json`; `--draft` until every review slot is confirmed by ear, §4.5) | §1–§5, strict |
| Shorts captions, fast path | Burned into `shorts/short_NN.mp4` | ASS via ffmpeg-full libass (`yt-clips render … --style default|<slug>`, or `yt-captions --format ass --style …`) | §3.3, §6, §7 |
| Shorts captions, brand-template path | Burned by Remotion | `yt-captions --format json` → `ShortCaptions` composition (`yt-remotion render ShortCaptions …`) | §6.4, §7 |
| Captions behind the subject; any client deliverable | Burned | HyperFrames `/embedded-captions` (single subject; split multi-shot footage first) | §6.5 |
| Text hooks, cards, lower thirds, chapter cards | Overlays | Remotion compositions (own and personal channels within the licence) or HyperFrames (clients, and the default) | §8 |

Why no burned captions on 50-minute episodes: a sidecar keeps YouTube's caption features (viewer toggle, auto-translation of the uploaded track) and costs no re-encode (F2 §5.1) [anecdotal]. YouTube caption formats: SRT and SBV are plain (no styling or positioning); WebVTT adds positioning and bold/italic/underline (https://support.google.com/youtube/answer/2734698, research pass 2026-10-11) [official]. The agent never uploads captions: the API route (`captions.insert`) needs a write scope the toolkit does not have.

Upload accuracy: an Italian SRT from the corrected word-level transcript beats auto-captions on names and jargon (F6 A11) [anecdotal]. An English sidecar (translation by Claude, same timing rules, ≤42 characters per line) is optional and only on request.

---

## 1. Netflix Italian rules and how we apply them

Source: Netflix *Italian Timed Text Style Guide*, https://partnerhelp.netflixstudios.com/hc/en-us/articles/215349898 — verified 2026-10-11 [official, for Netflix deliveries; adopted here as house standard]. Duration limits from the *General Requirements*, https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617 — verified 2026-10-11.

| Rule | Netflix (Italian) | Sidecar (long-form) | Burned Shorts |
|---|---|---|---|
| Characters per line | max 42 | max 42 | measured in pixels (§6); ~20–22 characters per line |
| Lines per event | max 2; one line unless it does not fit | same | max 2 |
| Line shape | bottom-heavy; avoid 1–2 words on the top line | same | n/a (chunks of 2–4 words) |
| Reading speed (adult) | 17 cps subtitles; 20 cps SDH | target 17 cps, ceiling 20 (same-language captions behave like SDH); the builder plans for both; events above 20 are listed with timecodes, never rewritten; the share above 17 is report-only (§2.3) | n/a (word-synced) |
| Event duration | min 5/6 s, max 7 s | min 1.0 s, never under 0.8 s (20 frames), max 7 s | chunk ≥ ~0.35 s |
| Position | centred, top or bottom | YouTube player decides (SRT) | safe zone (§7) |
| Ellipsis | single character `…` (U+2026); for pauses ≥2 s or abrupt interruptions; no ellipsis when one sentence simply continues across events | same | drop |
| Quotation marks | double quotes, no inner spaces; single quotes inside | same | rarely needed |
| Numbers | 1–10 in words; above 10 in numerals; a number that starts a sentence in words | same (§5) | digits allowed (space) |
| Thousands separator | only from five digits: 12.345 | same | same |
| Time | 24-hour clock with colon, no leading zero for 1–9 (9:15); minutes may be dropped («alle 17») | same | same |
| Currency | spelled out («11 dollari», «12.345 euro»); symbol with a space only under space pressure and above 10 («12.345 €») | same | symbol allowed |
| Italics | titles of works; foreign words not in Treccani or listed neologisms; never proper names; off-screen media voices | SRT: no styling on YouTube → no italics; VTT: italics allowed for foreign words | never |
| «Ok» | «Ok/ok», not «OK/Okay»; «Beh», «Mah» | same | same |
| Acronyms | no periods (MVP, SaaS, B2B) | same | same |
| Dual speaker | hyphen + space («- »), one speaker per line (rule I.7, verified 2026-10-12) | only for rapid exchanges: two one-line turns ≤40 characters, <1 s apart, same segment (3 events on the test episode); a dash at every chained turn is off by default (3 of 43 marks fell on wrong diarization boundaries, X3) | avoid |
| Profanity | never censor; match the original register; a bleeped source → asterisks («ca***») | same | same |
| Repetitions | the same word repeated by the same speaker is translated once (rule I.16) | **default light edit**: hesitations, false starts and the first copy of stutters dropped (115 words on the test episode, 1.9 %); emphatic repeats and discourse markers kept | same |
| Accented capitals | not covered by Netflix | È, À, Ì, Ò, Ù — never E' | same (uppercase preset) |

---

## 2. Timing

### 2.1 Mapping to the edited timeline

Every caption lives on the **output** timeline: `out = word.start − segment.src_in + segment.out_start` (video-use rule, `05` §1 rule 5). `yt-captions` does this from `edit/assembled.timeline.json`; words inside removed ranges are dropped, words straddling a cut are shortened. `--timeline none` keeps source time (only for pre-edit review).

### 2.2 Event timing (as implemented in `yt-captions`, builder v2, 2026-10-12)

Netflix *Timed Text Style Guide: Subtitle Timing Guidelines* (fetched 2026-10-12 in X3) [official, adopted as house standard]. Old builder values in brackets (`--builder v1` reproduces the 2026-10-11 files byte for byte).

| Parameter | Value | Note |
|---|---|---|
| Phrase break | a speaker change, a cut or a pause ≥1.0 s starts a new event; after a weak word, a determiner or between auxiliary and participle only a pause ≥2.5 s does («ho aperto il ‖ … negozio online») | `hard_gap`, `hard_gap_bad` (I1, 2026-10-12: with Parakeet word times the thinking pauses inside a sentence become visible; bad event ends 15 → 2 on the test episode) |
| In-time | first frame of speech; on the cut frame when speech starts ≤0.5 s after a cut | [v1: word start] |
| Out-time | the latest of speech end + 0.5 s, in-time + characters ÷ 17, in-time + 1 s; never past the next event − 2 frames, in-time + 7 s, speech end + 1.5 s or the segment end − 2 frames | [v1: linger 0.3 s] |
| Gaps | either 2 frames (chained) or ≥0.5 s: gaps under 0.5 s are closed to 2 frames | [v1: 0.083 s; 73 "flicker" gaps of 3 frames–0.5 s on the test episode → 3] |
| Min / max duration | 1.0 s target, 0.8 s floor (extend first, then start up to 0.3 s earlier, then merge with a same-speaker neighbour); 7 s max | Netflix allows 5/6 s |
| Reading speed | the split itself is chosen for the time each event will really be on screen (§3.1): cost rises above 17 cps and steeply above 20 | [v1 ignored cps when splitting] |
| Frame snap | every time on a 30 fps frame | — |
| Report | `reports.srt.gate` (blocking items), `over_ceiling_events` (every event >20 cps with timecode), `cps_over_pct` (>17, report only), `readability` | read it in QA (§10) |

### 2.3 Why 17 cps cannot be met word for word (test episode, X3)

- Speakers' own rate: median 17.5 characters per second of speech; the guest 15.0 in continuous stretches, one host 17.9 (63.7 % of his characters are spoken above 17 cps), the other host 14.1 [study, n=1 episode].
- Results on the whole episode (output timeline): events >17 cps 32.9 % (v1 bozza) → 29.6 % (v2 light); events >20 cps 12.8 % → 5.6 %; max 48.8 → 37.9 cps. A speed-only segmentation that ignores grammar reaches 28.3 % / 4.4 %: that is the floor.
- With the new transcript (Parakeet word times, I1): >20 cps 7.0 %, >17 cps 29.7 %, max 31.4 cps — real pauses are now where they are, so slightly less reading time is "borrowed" from silence; the test episode's edit was cut on the old whisper times, which also clips a few words at cuts.
- So the **gate blocks at 20, reports 17**. Do not condense the speech: list the >20 events in the QA report; only the operator can ask for a rewritten (non-verbatim) caption.

---

## 3. Segmentation and line breaking (Italian)

### 3.1 Sidecar algorithm (what `yt-captions` does; the agent checks it) — builder v2, 2026-10-12

1. Speaker turns are repaired in memory (§3.4); words go to the output timeline.
2. Text preparation: light edit (default; `--edit verbatim` keeps everything), orthography and glossary casing (§5), Italian numbers (§5), review slots (§4.5).
3. Units that never split: number + unit/magnitude/currency/%/unit slot, multi-word glossary terms, «un po'», names.
4. Phrases: a new event always starts at a speaker change, a cut or a pause ≥1 s (≥2.5 s when the word before the pause is weak, a determiner or an auxiliary before its participle).
5. Each phrase is partitioned by dynamic programming. Every event: ≤2 lines × 42 characters, ≤7 s of speech, ≥0.8 s on screen. Cost per event: 1.0 + line-layout cost + reading speed (characters × (0.018 per cps above 17 + 0.03 per cps above 20), computed on the time the timing pass will give) + 6 × missing time under 1 s + 0.8 for a fragment under 15 characters + break cost at the event end + 0.4 per sentence end inside the event + 1.5 when a new sentence under 15 characters is left at the end.
6. Break costs (event end / line break), lower is better:

| Where the break falls | Event / line |
|---|---|
| after a sentence end | −1.2 / −0.5 |
| after «;», «:» or a dash | −0.3 / −0.35 |
| after a comma | −0.15 / −0.3 |
| before a connector | −0.1 / −0.2 |
| before a preposition | 0 / −0.1 |
| no punctuation or other cue | +0.6 / +0.3 |
| after an intensifier or subject pronoun | +1.2 / +0.8 |
| after an auxiliary or modal | +1.5 / +0.8 |
| after a determiner or possessive | +2.0 / +1.5 |
| before a tag question («…, no?») | +2.5 / +1.5 |
| between auxiliary + participle/gerund or modal + infinitive | +2.5 / +1.5 |
| after a weak word (article, preposition, conjunction, bare connector, clitic, «non», «che», «se», «come», «quando», «perché», «tramite», «verso», «senza») | +4.0 / +2.5 |

   A pause at the break lowers the event-end cost by 0.4 × the pause (up to 1 s).
7. Line layout: one line if it fits in 42 characters; otherwise the best two-line split = break cost + 0.8 × length difference ÷ 42 + 0.25 if the top line is >4 characters longer + 0.5 if the top line has 1–2 words and the bottom line is more than twice as long.
8. Rapid two-speaker exchanges become one dialogue event (§3.4); then timing (§2.2).

Measured on the test episode vs the v1 builder: well-placed line breaks 60.4 % → 79.8 %, well-placed event ends 85.6 % → 85.3 %, bad event ends 22 → 4, bad line breaks 48 → 3, one-line events 9.7 % → 18.2 %, top-heavy events 107 → 75 [study, n=1]. The break classifier is a word list, not a parser: the agent's read-through (§10) still matters.

### 3.2 Protected groups (never split across lines or events)

| Group | Example (keep together) |
|---|---|
| Article + noun | «il prodotto», «gli utenti» |
| Preposition (simple or articulated) + next word | «della community», «nel 2025» |
| Elided forms | «l'idea», «un'azienda», «dell'app», «c'è» (rejoin if the ASR split them) |
| Clitic + verb | «ci abbiamo», «me l'ha detto» |
| Auxiliary + participle | «abbiamo deciso», «è stato» |
| «non» + verb | «non funzionava» |
| Number + unit or currency | «19 € al mese», «tre volte» |
| First name + surname; title + name | «Giulia Conti», «dott. Bianchi» |
| Fixed terms of art | «build in public», «product market fit», «A/B test» |

Examples:

| Bad | Why | Good |
|---|---|---|
| «Abbiamo deciso di alzare i prezzi del / triplo in una settimana» | top-heavy; splits «del triplo» | «Abbiamo deciso di alzare / i prezzi del triplo in una settimana» |
| «Ho parlato con il / CEO di una startup» | ends on an article | «Ho parlato / con il CEO di una startup» |
| «Fatturiamo 12.345 / euro al mese» | number separated from its unit | «Fatturiamo / 12.345 euro al mese» |
| «Non / ci avevo pensato» | «non» separated from the verb | «Non ci avevo pensato» (one line) |
| «Abbiamo / deciso di chiudere» | auxiliary separated from the participle | «Abbiamo deciso / di chiudere» |

### 3.3 Shorts chunking (burned captions)

- Chunks of 2–4 words (target 3), closed by punctuation, a pause ≥0.3 s, a speaker change or a cut (as implemented in `_chunk_words`).
- Width is **measured in pixels** with the preset font (PIL), not counted: if a chunk does not fit, it is split into two balanced lines, avoiding a weak word at the end of line 1; as a last resort it is scaled down.
- Never show a chunk for less than ~0.35 s: merge it with the next (video-use practice [anecdotal]).
- One active word at a time; the chunk stays on screen while its words are spoken.
- Case: the `default` preset is uppercase; a brand preset follows its brand (`uppercase` / `lowercase` keys, §6.3). Uppercase must keep accents: «È», «PERCHÉ», «CIOÈ» (Python `str.upper()` does).
- Punctuation in chunks: house rule — drop terminal periods and commas inside burned chunks, keep «?» and «!» when they carry intonation. The current ASS builder keeps the transcript's punctuation (see return notes).

### 3.4 Speakers

- A new event at every speaker change (sidecar).
- Two speakers in one event only for rapid exchanges where separate events would last under 1 s: hyphen + space, one speaker per line (Netflix I.7).
- Host backchannels («sì», «esatto», «certo») over a guest's answer are not captioned when they overlap the guest; captioned when they stand alone as an answer.
- **Turn repair before captions** (in memory, never written to the transcript; `--no-speaker-repair` to skip): unlabelled words take the speaker across the weaker boundary; each diarized change moves (−5/+7 words, ±2.5 s) to the strongest text boundary («?» 3.0, «.»/«!» 2.0, «…» 1.5, «;»/«:» 1.0, «,» 0.4, a tag question 0.4, + 1.5 × pause) when it beats the diarized position by ≥1.0; a short greeting or thank-you that names the guest («Benvenuto Paolo.») goes to the last host who spoke (hosts from `voice.public_names.hosts` in the channel profile). Test episode: clear-cut changes exactly right 44/59 → 55/59, misattributed words 29 → 9 [study, labels from text only].

---

## 4. Fillers vs discourse markers: flag, don't cut

### 4.1 Three classes

Italian «segnali discorsivi» have real interactional functions (Bazzanella, *Enciclopedia dell'Italiano*, 2011; Il Post 2026-01-27, https://www.ilpost.it/2026/01/27/parole-riempitive-filler-words-marcatori-del-discorso/) [anecdotal — linguistics references, not corpus statistics]. So the agent treats only pure hesitations as removable.

| Class | Tokens | What it is | Podcast edit (interview) | Solo edit (talking head) | Captions |
|---|---|---|---|---|---|
| **H — hesitation** | ehm, eh (hesitant), ehh, uhm, um, mmm, mh, uh, ah (hesitant) | No meaning | Cut candidate only when isolated and followed by a pause; flag at G1 | Cut candidate, confirmed at G1 | Omit |
| **D — discourse marker** | cioè, tipo, diciamo, praticamente, insomma, niente, vabbè, boh, ecco, beh, comunque, appunto, nel senso, voglio dire, sai, no? (tag) | Reformulation, hedging, turn-taking, summary | **Flag only**; keep unless stacked | Cut candidate when stacked or before a restart; confirm at G1 | Keep when it carries function; omit only stacked repeats |
| **C — connector** | quindi, allora (causal), però, ma, perché, poi, invece, infatti, anzi | The story's "ma / quindi / perché" (`03` §1) | **Never flagged, never cut automatically** | Same | Always keep |

Context rules (the same token can change class):
- «tipo» before a number or as «come/per esempio» = content («tipo cinquanta clienti»); as a quotative («e lui tipo: …») = keep; as a pause filler («tipo… ehm…») = D.
- «niente» as a pronoun = content («non ho fatto niente»); answer-opening «e niente, …» = D.
- «diciamo», «praticamente», «circa» before a number = **qualifier** of a claim: never removed (claim ledger, `03` §11).
- «allora» opening an answer = D (flag only); «allora» meaning "therefore" or "at that time" = C.
- «eh» as an interjection with meaning («eh, lo so») or a tag («bello, eh?») = D, not H.
- «cioè» introducing a reformulation = keep; followed by a pause and a restart = D candidate.

Stacked = two or more H/D tokens within 3 s, or a D token + pause ≥0.4 s + restart. Only stacked or restart cases become cut candidates in the podcast.

### 4.2 Detection signals

1. Token match on the normalised word (lowercase, punctuation stripped), with multi-word patterns («nel senso», «voglio dire», «va be'»).
2. Voiced gaps: an inter-word gap ≥0.25 s not reported as silence by `silencedetect` → probable filler the ASR dropped (`05` §4.2).
3. Restarts: the same 1–3 words repeated within 2 s.

G1 flag list format (Italian, in the brief): `t (sorgente) · parola · classe H/D · contesto ±5 parole · proposta taglia/tieni · motivo`.

### 4.3 Transcription settings that make fillers visible

- Whisper tends to normalise disfluencies away; a disfluent Italian prompt with `--carry-initial-prompt` raises recall but does not guarantee it (OpenAI speech-to-text guide: the prompt can preserve fillers; ~224-token limit — https://developers.openai.com/api/docs/guides/speech-to-text, research pass 2026-10-11) [official].
- Local test on a 2-min guest sample: the disfluent prompt raised detected filler/discourse tokens from 3 to 6 and preserved a false start; without the glossary a company name came out misspelled (SYNTHESIS N12) [anecdotal, n=1].
- So: channel glossary (`<slug>.glossary.txt` next to the profile in `channels_dirs`) + `glossary_extra` in `project.json` + `yt-glossary <workdir> --doc <prep note> --web <web.json>` + `yt-transcribe <workdir>`, every episode. Full pipeline and evidence: `05` §1.1.
- **Prompt length is noise for names, not for hesitations** (2026-10-12, test episode): reordering the same terms moves the error rate by 0.4 pp; long (≈171 tokens), short (≈110) and sentence-style prompts all give 44–47/56 names. The 304→184 hesitation drop between the two production passes was not caused by prompt length. A 110-token prompt found 241 hesitations (4.55/min) against 144 (2.72/min) for the long one, with the same names [study, n=1, one run per prompt]. `yt-transcribe` warns below 3 hesitations/min: if the edit relies on cutting fillers, re-run with `--prompt-budget 110 --force`.

### 4.4 How the toolkit marks them (`flags_version: 2`, fixed 2026-10-11)

`yt-transcribe` writes these flags on the words of `analysis/transcript.words.json` (top-level `"flags_version": 2`; code: `transcribe.py` `classify_words`):

| Flag on the word | What gets it | Class in §4.1 |
|---|---|---|
| `"filler": true`, `"filler_kind": "hesitation"` | ehm, eh, uhm, um, mmm, mh, uh…; «ah»/«oh» only when isolated between two pauses (≥0.12 s each side) | H |
| `"filler": true`, `"filler_kind": "repetition"` | the **first** copy of an immediate repeat of 1–3 words, only when function words are involved («il il», «era, era», «per, per, per», «ho fatto ho fatto»); expressive doubles («piano piano», «no, no») are not flagged | restart (§4.2 signal 3) |
| `"filler": true`, `"filler_kind": "false_start"`, `"false_start": true` | a truncated word («pro-») and, if repeated right after, the function word before it | false start (`05` §5) |
| `"discourse": true` | allora, quindi, cioè, tipo, praticamente, diciamo, insomma, ecco, niente, comunque, vabbè, appunto, magari, boh; «beh/be'» only at sentence start; «nel senso», «voglio dire», «va be'»; the tags «…, no?» and «eh?»; «ah/oh» with meaning | D **plus** «quindi» and «allora», which §4.1 puts in C |
| no flag | everything else, including the other connectors (però, ma, perché, poi, invece…) and the context exceptions below | content or C |

- Context rules in the code: «un tipo di», «quel tipo» = noun; «tipo / diciamo / praticamente» + number = qualifier; «da allora», «fino ad allora» = temporal; «niente» after a negation in the same sentence = pronoun. In all these cases the word gets no flag.
- A word is never both `filler` and `discourse`; «quindi» is always `discourse`, even when repeated.
- `discourse: true` is **not** the same as class D. For the G1 flag list, still classify each `discourse` word by §4.1: «quindi» and causal «allora» are C and are never flagged.
- What removes words: `yt-captions --drop-fillers` and `yt-clips render` (by default) drop only words with `filler: true` or `false_start: true`. **`discourse: true` words are never dropped.** The JSON summaries report `fillers_dropped` and `discourse_kept` (`yt-clips render`: in `renders[].captions`); `yt-captions` also lists the `dropped_words`. `yt-clips render --keep-fillers` keeps hesitations, repetitions and false starts too; use it only when a hesitation carries meaning (comic timing, a quoted «ehm»).
- Old transcripts (no `flags_version`, or the old `filler_kind: "discourse"`): `yt-captions` and `yt-clips render` reclassify them in memory and warn; `yt-transcribe <workdir> --reflag` rewrites the file without re-running ASR and reports the counts and the words that changed; a normal `yt-transcribe` run reflags automatically.
- Whisper drops most hesitations (§4.3): on a 3-min test excerpt the transcript has 0 hesitations, so `--drop-fillers` removes nothing there; on the full episode it found 272 hesitations and 97 repetitions (FX2 test, 2026-10-11).

Rules:
- Sidecars (builder v2, 2026-10-12): the **light edit is the default** (`--edit light`): it applies the «Captions» column of §4.1 and the «stutters collapsed» row of §1 (H omitted, repeats collapsed, D and C kept), moves a sentence-ending mark from a dropped word to the previous word and capitalises the next word when the dropped word opened a sentence. `--edit verbatim` keeps every word (43 «ehm» on screen on the test episode). `--drop-fillers` on srt/vtt is the same as light. The reading-speed gain of the light edit is small (−0.6 pp of events above 17 cps); its value is cleaner text.
- Burned Shorts: the default render (fillers dropped) is right; `--keep-fillers` is no longer a workaround for connectors.
- The EDL never cuts a word just because `filler: true`; only class H tokens and confirmed restarts become cut candidates, and only after G1.

### 4.5 Words that must be confirmed by ear (review slots)

- **Units after a figure** (MRR/ARR and the forms the engines write when the speaker spells M-R-R / A-R-R: «MRAR», «emarar», «Mararro», «e ARR»…) are never resolved by guessing, not even from the prompt: whisper's MRR/ARR choice follows the order of the acronyms in the prompt, not the audio (X2: same audio, «ARR» ×5 or «MRR» ×5 depending on which acronym came later) [study]. `yt-transcribe` marks them `"unit_review": true`; published facts (a revenue figure in a title) are attached as evidence only — a conflict (transcript «ARR» vs a published chapter that says «MRR») is settled by ear.
- Other doubtful words (e.g. «15.000 potenti», where Parakeet hears «utenti») are added by the agent to `analysis/resolutions.json` → `"slots": [{"t", "from", "placeholder", "reason"}]` after reading the listening list (`analysis/transcript.review.json`).
- In the sidecar each open slot is a visible placeholder (`[[MRR/ARR]]`, `[[utenti?]]`). A person who listens (the operator or a host) checks them (source timecodes in the review list; ≈10 per episode) and write the confirmed text in `analysis/resolutions.json` → `"resolved": {"<source start, 2 decimals>": "MRR"}`. Without `--draft`, `yt-captions --format srt,vtt` **refuses to write** while any slot is open (exit 2); `--draft` writes `deliver/<slug>.<lang>.draft.srt/.vtt` for review. ASS/JSON use the resolved text when present and warn otherwise.

---

## 5. Italian orthography and normalisation for captions

| Topic | Rule | Example |
|---|---|---|
| Accents | acute on «perché, poiché, affinché, né, sé»; grave on «è, cioè, caffè»; ASR often writes «perchè» → fix | «Perché l'ha fatto?» |
| Accented capitals | real characters, never apostrophes | «È lì che…», not «E' lì» |
| Apostrophes | «po'» (apostrophe, not accent); «qual è» (no apostrophe); «un'idea» vs «un amico» | «un po' di clienti» |
| Numbers 1–10 | in words | «tre clienti», not «3 clienti» — the builder does NOT convert digits 1–10 automatically (on the test episode the only candidate was «stampa 3.» = «3D»): the agent fixes them in the read-through |
| Numbers >10 | numerals; a number that opens a sentence in words | «40 clienti» · «Quaranta clienti in tre mesi» |
| Thousands | separator only from five digits (automatic: «1.000» → «1000») | «2500», «12.345» |
| Decimals | comma (automatic, except versions after a name: «GPT 3.5», «Apache 2.0») | «2,5 milioni» |
| Number words >10 | numerals when followed within 3 words by a magnitude, currency, K or %, not at sentence start (automatic) | «quindici, venti milioni» → «15, 20 milioni» |
| K and x | as spoken (automatic) | «40K», «20x» (not «20X», «10XR») |
| Percentages | house: numeral + % for readability, also under 11 (Netflix allows breaking number rules for space and reading speed) | «il 5%», «il 30%» |
| Money | «euro» spelled out; «€» only when space-pressed and above 10 | «19 euro al mese» · «12.345 €» |
| Time | 24 h, no leading zero | «alle 9:15», «alle 17» |
| Loanwords | invariable in the plural | «i founder», «le startup», «gli MVP» |
| Brand and names | glossary spelling, exactly (automatic casing from speakers, `glossary_extra`, `analysis/glossary.json` episode terms, channel P1/P2 and a built-in brand list: ChatGPT, OpenAI, GitHub, LinkedIn, Gmail, YouTube…; never for glossary words that are also common words: cloud, cursor, notion, vento…). Names inside the transcript are fixed upstream by `yt-postcorrect` (`05` §1.1) | the channel name as written in P1 of the glossary, guest names from `project.json` |
| Foreign terms | VTT: italics if not in Treccani; SRT and burned: no italics | «build in public» |
| Profanity | faithful, within the profile's register; never invent bleeps | — |
| Content words | never «correct» the speaker's grammar or regional phrasing; fix only ASR errors | — |
| Banned brand words | apply to text **we** write (cards, hooks), never to the guest's own speech | — |

---

## 6. Caption presets and engines

### 6.1 Engines by channel

| Channel | Shorts captions | Long-form | Behind-subject captions |
|---|---|---|---|
| any channel without its own preset | ASS preset `default` (fast) or Remotion `ShortCaptions` (`brand: 'demo'`, own and personal channels only) | sidecar SRT/VTT | HyperFrames `/embedded-captions` |
| own or personal channel with a brand (`<slug>`) | the brand's ASS preset (`<brands_dir>/<slug>/ass/<slug>.json`, `--style <slug>`) or Remotion `ShortCaptions` (`brand: '<slug>'`, styles from its `remotion.json`) | sidecar SRT/VTT | HyperFrames `/embedded-captions` |
| clients | HyperFrames `/embedded-captions` (identity chosen from the client brand) or an ASS preset with the client's tokens | sidecar SRT/VTT | HyperFrames |

Remotion stays on own and personal channels within the licence (`graphics_licence` in the profile; design §11).

### 6.2 Preset `default` (`assets/ass/default.json`)

The built-in preset, coloured with the tokens of the built-in `demo` brand. When the project's channel has a brand whose tokens define `ink`, `paper` and `accent`, `yt-captions` and `yt-clips` use that brand's colours instead (accents it lacks fall back to its `accent`); fonts and geometry stay those of the preset. The file is the truth: read it before quoting a value.

| Element | Value |
|---|---|
| Caption font | Inter ExtraBold, static instance (in `assets/ass/fonts/`), 86 px on a 1080×1920 PlayRes |
| Case | UPPERCASE |
| Colours | `token:paper` text, `token:ink` outline 7 px, ink shadow 3 px (semi-transparent) |
| Active word | the brand accent (`accent`), 108% scale (`--accent accent_2` or `accent_3` picks another accent of the brand) |
| Chunks | 3 words target, 4 max; max ~20 characters per line |
| Position | bottom-centre, MarginV 560, side margins 70 |
| Hook (first 3 s) | Anton 72 px, uppercase, ink text on a paper box (padding 18), top-centre, MarginV 250, up to 3 lines, ≤10 words (`--hook`) |
| Accent discipline | one accent per composition: the hook uses ink on paper, never a second colour |

### 6.3 Presets of a channel's brand (`brands_dirs`)

A channel's brand brings its own preset in `<brands_dir>/<slug>/ass/<slug>.json` (contract in `07` §8); the plugin ships only `default`. The schema is the one of `assets/ass/default.json`. Keys that `default` leaves unused and a brand preset may set:

| Key | Effect |
|---|---|
| `caption.lowercase` / `hook.lowercase` | lowercase text instead of the transcript's case |
| `caption.inactive_alpha` | dims the inactive words of a chunk (ASS alpha, 0 = opaque) |
| `caption.active_color: null` | the active word changes only scale, not colour |
| `hook.prefix`, `hook.prefix_color` | a fixed glyph before the hook, optionally in an accent token |
| `accent_once: true` | the accent appears **once** per composition: on the hook prefix by default, or on one caption word with `--accent-word <parola>` |

`font_file` names a static font in the brand's `fonts/` or `ass/fonts/` (libass needs one file per weight). Colours are `token:<name>` references into the brand's `tokens.json`. Copy rules (punctuation on hooks and cards, tool names) come from the profile's `copy_rules`. Check in the QA frames that the accent appears as often as the brand allows, and that accented letters render in the brand's fonts (§6.6).

### 6.4 Remotion `ShortCaptions` (defaults read from `remotion/src/Root.tsx`, 2026-10-11)

Props: `brand` (`demo` or the slug of the channel's brand), `captions` (from `yt-captions --format json`: `[{text, startMs, endMs, timestampMs, confidence}]`, or `captionsFile`), `combineMs` 800, `maxWordsPerPage` 4, `captionY` 0.64 (centre of the caption block as a fraction of height), `captionFont` `display`, `uppercase` true, `hookSeconds` 3, `progressBar` false, `showSafeZone` false (turn it on for QA renders). Safe box in the component: left 70, right 130, top 260, bottom 1660 px. Brand tokens are injected by `yt-remotion` from the brand's `tokens.json` (the `brands_dirs` first, then the plugin's `assets/brands/`, `07` §8); a brand's `remotion.json` arrives as the `style` prop (fonts, case, accent placement and similar; a `style` object in the props file is merged over it).

### 6.5 HyperFrames `/embedded-captions` (clients, behind-subject look)

35 caption identities; default is a quiet verbatim "rail" plus occasional peak words composited behind the subject with local matting; single-subject talking heads only (split multi-shot footage first); runs locally (F1 §1.1, V1 §1) [anecdotal]. Feed it our corrected word timings (Italian), never its English default model.

### 6.6 ASS anatomy (for checks and manual fixes)

- Colours are `&HAABBGGRR` (alpha first, then blue, green, red; `00` = opaque). Examples (the `demo` tokens): `#f4f1ea` → `&H00EAF1F4`, `#15171c` → `&H001C1715`, `#ff5a2c` → `&H002C5AFF`. The toolkit converts the brand tokens itself.
- Header essentials: `PlayResX: 1080`, `PlayResY: 1920`, `WrapStyle: 2` (no automatic wrap: line breaks are `\N`, decided by the builder), `ScaledBorderAndShadow: yes`, `YCbCr Matrix: TV.709`.
- `BorderStyle: 3` draws an opaque box in the **OutlineColour** with the Outline value as padding: that is how the hooks get their paper or background box (render-tested 2026-10-11 with ffmpeg-full libass) [anecdotal, local render].
- Active word: one `Dialogue` event per word-time inside the chunk, with an inline colour override on the spoken word (`{\1c&H000057F7&}PREZZO{\1c&H00E8F3F7&}`); the karaoke tag `\k` gives a cumulative fill instead (SecondaryColour before, PrimaryColour after its time) and is not used for active-word-only highlight.
- Burn: `ass=<file>.ass:fontsdir=<dir>` in ffmpeg-full; `yt-clips` passes the static fonts directory (`assets/ass/fonts/` for `default`, the brand's `fonts/` for a brand preset). Check family names with `fc-scan --format "%{family[0]} | %{style[0]}\n" <font>`; fonts missing → libass silently falls back to another face.
- Measured on an Apple Silicon Mac (2026-10-11 test render, ffmpeg-full libass) [anecdotal, local render]: with a very wide display face a 33-character uppercase line at 84 px overflowed 1080 px, so hook lines are broken by the builder (≤ ~24 characters per line at 64–76 px); a bold sans uppercase at 88–92 px fits ~20 characters in 900 px (16 «W» fill ~1,050 px). Inter and Anton (preset `default`) and every brand font need the same check on the first render: accented capitals (È) and «×» must render.

Reference presets (clipify `build_ass.py`, MIT [anecdotal]): `opus` Arial Black 100 px, 3-word chunks, yellow active word, outline 8, shadow 3, MarginV 280; `karaoke` 110 px, 4 words, green; `minimal` Helvetica 70 px, 6 words, outline 4. video-use "bold-overlay": ~2-word uppercase chunks, break on punctuation and pauses ≥0.3 s, no cue shorter than 0.35 s, white with a thin black outline. Our presets replace them; MarginV 280 sits inside the bottom UI band of the safe zone (§7) and is not used.

---

## 7. Shorts safe zone (anecdotal — no official YouTube spec)

No official YouTube specification exists (F2 §5.3, SYNTHESIS §1.1); third-party guides roughly agree [anecdotal: https://reap.video/blog/short-form-video-safe-zones , https://blog.eklipse.gg/beginner-guide-2/youtube-shorts-caption-placement-safe-zone.html , https://www.poster.ly/tools/safe-zone-checker].

| Zone on 1080×1920 | Keep clear | Our geometry |
|---|---|---|
| Top ~100–120 px | status bar, search | hook box starts at 250 px (ASS) / safe top 260 px (Remotion) |
| Bottom ~300 px | title, channel, subscribe, sound | captions bottom at 1920 − 560 = 1360 px (ASS); Remotion safe bottom 1660 px, block centred at 64% |
| Right ~50–80 px (practitioners often give more for the button rail) | like / comment / share rail | ASS side margins 70; Remotion right margin 130 |
| Centre box ≈ 900 × 1400 px | all critical text | ASS text width ≤ 940 px; Remotion box 880 × 1400 px |

Checks:
1. **Phone check before standardising** any new preset: open a private test on a phone in the YouTube app (the operator, manual).
2. **Frame QA** (automatic in `yt-clips render`): frames at 1.0 s and at the midpoint in `shorts/qa/`; the agent reads them for text clipping, captions over faces, missing accents, and text under the UI bands.
3. **Faces**: captions must not cover the mouth or eyes; compare the caption block with `thumbvision faces` boxes; if they overlap, regenerate the ASS with `yt-captions <workdir> --format ass --position center …` or change the crop (`yt-clips render … --crop/--face`).
4. The hook text (≤10 words) must stay inside the box and off the face for its 3 seconds.

---

## 8. On-screen text (cards, hooks, lower thirds)

1. **One language per graphic.** Italian by default; English only for proper names and community terms (community, build in public, indie builder, MVP) — never English words scattered for flavour (house rule).
2. **Text hook (long-form)**: about one third down the frame, ≤2 lines, ~3 s on screen (Kallaway [anecdotal]); different words from the spoken line, same idea (`04` §9).
3. **Text hook (Shorts)**: ≤10 words, a concrete specific (number, name, claim) (openshorts rule [anecdotal]); preset hook styles above.
4. **Numbers on screen** come from verified claim-ledger rows (`03` §11) and follow §5.
5. **Lower thirds**: name + one-line credential; sizes and timing in `05` §13. Public names exactly as in the profile's `voice.public_names`, never a name listed under `never`.
6. **Chapter cards**: Italian curiosity-gap titles, 3–7 words, keyword first, the same strings as `deliver/chapters.txt` (rules for chapters: `youtube:chapters`).
7. **Own and personal channels**: the brand's fonts and tokens (`brands_dirs`, `07` §8; or the built-in `demo`), its `text_pairs_allowed`, and the profile's banned words (`voice.banned`) in every text we write.
8. **Copy rules**: the profile's `copy_rules` (punctuation, tool names, case) on cards, hooks and lower thirds.
9. **Clients**: client tokens and voice from the channel profile; HyperFrames as engine.
10. Text sits in title-safe (≥5% from every edge), never over faces, never on screen for less time than it takes to read (≥ ~1 s per 3–4 words, plus 0.5 s) [anecdotal — house default].

---

## 9. Italian copy checklist

Apply to text the agent writes: spoken scripts, hooks, cards, chapter titles, description drafts. **Never** to verbatim guest quotes or captions.

| Problem | Instead of | Write |
|---|---|---|
| Burocratese | «effettuare una verifica», «procedere alla realizzazione», «al fine di», «in data odierna», «risulta essere» | «verificare», «fare», «per», «oggi», «è» |
| Nominalisations | «la realizzazione dell'implementazione», «l'ottimizzazione della conversione» | «implementare», «convertire di più» |
| Calques from English | «fa senso» · «realizzare» (= rendersi conto) · «supportare» (= aiutare) · «applicare per» · «impattare» · «schedulare» · «approcciare un cliente» · «in accordo a» · «assumere» (= presumere) · «eventualmente» (= alla fine) | «ha senso» · «accorgersi, capire» · «aiutare, sostenere» · «candidarsi a» · «incidere su» · «pianificare» · «contattare» · «secondo» · «dare per scontato» · «alla fine» |
| English plurals | «i founders», «le startups» | «i founder», «le startup» |
| Impersonal / passive | «si è deciso di», «viene mostrato» | «abbiamo deciso», «ti mostro» |
| Plural address | «ragazzi», «voi» | «tu» |
| Gerund chains | «andando a vedere, analizzando…» | short main clauses |
| Empty intensifiers | «incredibile», «pazzesco», «imperdibile», «davvero molto» | the concrete fact |
| AI tells | balanced tricolons, «non solo… ma anche», «in un mondo in cui», «scopri come», «immergiamoci» | one concrete sentence |
| Stake word buried | «Trentamila euro è quanto ha fatturato» | «Ha fatturato trentamila euro» |
| Mixed language | «3 days of building» on an Italian card | «3 giorni per costruire» |

---

## 10. Caption QA checklist

Automatic (from the `yt-captions` JSON report, `reports.srt`; any non-zero blocking value is listed in `qa/report.md`):
- [ ] `gate.pass` = true. Blocking: `lines_over_max` (42 characters), `cues_over_2_lines`, `overlaps`, `gaps_under_2f`, `under_floor` (<0.8 s), `over_max_dur` (>7 s), and open review slots (the final build refuses to write: exit 2).
- [ ] `over_ceiling_events` (>20 cps) listed with timecodes in the QA report (35 on the test episode); `cps_over_pct` (>17) reported only.
- [ ] `sidecar.review_open` = 0 for the delivered file (no `.draft` in the name).

Agent read-through (sidecar):
- [ ] Glossary names correct everywhere (guest, company, product, channel name); `analysis/postcorrect.candidates.json` reviewed and `yt-postcorrect` re-run with the decisions.
- [ ] No class C connector missing; no qualifier missing before numbers.
- [ ] Numbers, currency, time per §5; «perché» not «perchè»; «È» not «E'»; digits 1–10 in words where they are counts.
- [ ] Every unit slot resolved by ear (never by the published description alone).
- [ ] Spot-check 3 random minutes against the audio for sync (±0.2 s) and wording.
- [ ] Timeline: captions match the **edited** output (no text from removed ranges).

Burned Shorts (frames from `shorts/qa/`):
- [ ] No clipping at the edges; inside the safe zone; not over the face.
- [ ] Accents render; uppercase keeps them.
- [ ] Hook ≤10 words, visible from frame 0 to ~3 s, one accent colour only (or as the brand preset allows, `accent_once`).
- [ ] Only fillers dropped (§4.4): `fillers_dropped` equals the `filler: true` words in the clip range (the `yt-captions` summary also lists `dropped_words`); «quindi», «allora», «niente», «tipo» still on screen.
- [ ] `units_unconfirmed` = 0 in the ASS/JSON report (or the slot was resolved).

---

## 11. Sources

- Netflix Italian Timed Text Style Guide — https://partnerhelp.netflixstudios.com/hc/en-us/articles/215349898 (verified 2026-10-11) [official]
- Netflix Timed Text Style Guide: General Requirements — https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617 (verified 2026-10-11) [official]
- Netflix Timed Text Style Guide: Subtitle Timing Guidelines and Italian rules I.7, I.16 — fetched 2026-10-12 in the X3 study [official]
- Transcription and subtitle tests 2026-10-12 (one 53-min Italian interview episode, silver reference S0; internal logs, not distributed) — X1 engines/timing, X2 glossary/post-correction, X3 subtitles, I1 implementation and before/after [study, n=1 episode]
- YouTube supported caption files — https://support.google.com/youtube/answer/2734698 (research pass 2026-10-11) [official]
- OpenAI speech-to-text guide (prompting, 224-token limit) — https://developers.openai.com/api/docs/guides/speech-to-text (research pass 2026-10-11) [official]
- Il Post on filler words and discourse markers — https://www.ilpost.it/2026/01/27/parole-riempitive-filler-words-marcatori-del-discorso/ ; Bazzanella, «Segnali discorsivi», *Enciclopedia dell'Italiano* (2011) [anecdotal]
- Shorts safe-zone guides — https://reap.video/blog/short-form-video-safe-zones , https://blog.eklipse.gg/beginner-guide-2/youtube-shorts-caption-placement-safe-zone.html , https://www.poster.ly/tools/safe-zone-checker [anecdotal]
- clipify `build_ass.py` (MIT) — https://github.com/louisedesadeleer/clipify [anecdotal]
- video-use (MIT) — https://github.com/browser-use/video-use/blob/main/SKILL.md [anecdotal]
- HyperFrames (Apache-2.0) — https://github.com/heygen-com/hyperframes [anecdotal]
- Toolkit read 2026-10-11: `scripts/yt/lib/captions.py`, `lib/transcribe.py`, `assets/ass/default.json`, `remotion/src/Root.tsx`, `remotion/src/compositions/ShortCaptions.tsx`
- Research: `F2-editing-toolchain.md` §2.2, §5; `F5-story-hook.md` §9.3–§9.4; `F6-podcast-research-tooling.md` A11; `SYNTHESIS.md` §1.3 (N12), §2.3, §2.7.
