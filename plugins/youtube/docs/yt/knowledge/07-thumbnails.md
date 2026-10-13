# 07 — Thumbnails: principles, series frame, sources, guest-pixel policy, QA, pre-test and A/B

> **How the skills use this file**
> 1. `youtube:thumbnail` reads it end to end before step 1 and runs §10–§16 as its procedure; anything not marked "default" or "hypothesis" is a rule.
> 2. `youtube:hook` and `youtube:edit` read §4 (P2) and §5: every concept carries a `payoff_at` that the cold open must pay off inside 0–30 s.
> 3. `youtube:review` reads §15–§16 to log native A/B tests and human pre-tests and to update the scoreboard; `youtube:strategy` reads §4, §6, §7.7 and §16 for the packaging system.
> 4. The critic sub-agent (12-qa-gates.md §8) scores renders with §14; the cold reader (`agents/thumb-cold-reader.md`, §13.3) sees only the tiles. Zero-tolerance items and hard fails override any total.
> 5. `youtube:story --mode=prep` and the recording checklist read §10.6 and hand the crew `docs/yt/templates/brief-camera-stretta.md`.
> 6. Platform numbers carry URL + verification date, statistics carry an evidence label; folklore numbers live in 10-evidence-ledger.md and are never cited. Scores of LLM judges are labelled `[giudizio LLM]`: they are a secondary check, never evidence for a rule.

Verified 2026-10-11 (research F3, V1 §25–28, V3 §4–§8, SYNTHESIS §2.4). **Rewritten 2026-10-12 as v2** from a thumbnail study (tracks R1–R5 and a synthesis with a critical review; reference sets measured and coded, a panel of LLM judges J1–J3 on two rounds of renders; internal logs, not distributed). The numbers quoted from it below are measurements on public reference thumbnails and on test renders, labelled `[misurato]`, `[codificato]` or `[giudizio LLM]`. Where this file and a tool's `--help` disagree, the `--help` wins (design §8) and the gap goes into the G2 brief. Re-verify with 01-platform-facts.md every quarter. Method in English; every text that ends up on a thumbnail, in a brief or in a note is Italian.

---

## 0. Decisions in one screen

### 0.1 House defaults of the v2 frame (every channel; a profile may tighten, never loosen)

| Topic | Default | Where it lands |
|---|---|---|
| Upscale cap | **Measured at the display**: the face in the 1280×720 output is at most **2.0× its effective source resolution** (option c; ~40–42 % face height from a composited inset frame). Plus a **served-size detail check** (face Laplacian in the render downscaled to 720×405: warning < 713, error < 569). A flag falls back to 1.5× (option b, ~32 %) | §10.1, §12.4 |
| Guest pixels | **Policy ladder**: levels 0–2 allowed (graphics around the person; one global uniform tone curve on the whole cutout, skin ΔE00 mean ≤ 2.5 and p95 ≤ 5); face pixels never change in geometry or identity (automatic check). Outline and glow only with `guest_style: graphic`, **never a default**. Level 3 and above (simulated relight on people, learned super-resolution) are not used; level 5 (generative) is forbidden | §11 |
| Source | **No photo session.** The crew puts a **tight fixed camera** on the guest (ideally one per host too) for the whole recording and keeps the ISO file. The toolkit imports that file as a full-frame portrait source | P5, §10.1, §10.6, `docs/yt/templates/brief-camera-stretta.md` |
| Local analysis and tests | **MediaPipe** (local, Apache-2.0, optional extra `install.sh --with-mediapipe`) for expression search and the landmark check. **Props and backgrounds from text only**: main session, cost preflight, default caps €5 per episode and €20 per month (profile `thumbnails.props_budget`), never faces, never uploaded footage. **Human pre-test** (Prolific or PickFu), run by hand by the operator with the kit in `docs/yt/templates/pre-test-protocollo.md` | §10.2, §15, §17 |
| Style | An **editorial duo** series frame (two people, one huge headline between them, one accent), driven by the channel's brand tokens | §7.7 |
| Host in the duo | The host gets a **small host tag** (`host_tag`, «con <nome dell'host>»), not a second name plate; public names only, as written in the profile | §7.7, §10.5 |
| Monochrome | **Allowed as an option** (`grade: mono`, policy level **2b — uniform monochrome grade**): one desaturation + contrast curve on the whole photo (every person and the plate, the same curve on every pixel), identity and expression intact, no local edits on faces, one accent colour in the graphics only. The skin ΔE00 check does not apply to 2b; it is replaced by the **single-curve check** on all person pixels and **landmarks unchanged** (automatic). Default grade: `natural` | §11.2, §12.4, §13.1 |
| Default frame | **`duo`** (guest + host of the same episode); **`ritratto`** for single-face episodes | §7.7 |
| Meta line | «EVENTO / ANNO»; the city only when it adds something; every item verified | §1.1, §7.7 |

### 0.2 Rules in one screen

| Decision | Rule | Source |
|---|---|---|
| Image source | Real pixels only. Source priority: tight fixed camera ISO → main camera ISO → composited master frame (inset preferred) → guest-supplied photos. `yt-portrait scan` (expression classes) → `yt-portrait cut` (BiRefNet-portrait matte, Apple Vision fallback; non-generative resize drawn 1:1) → series template. No photo session, no generated people | §10; §0.1 |
| Series frame | **One series frame** (§7.7): `duo` (guest + host, **the default**) and `ritratto` (guest alone, single-face episodes) share it; `scena` and `prova` are field modes of the same frame; `generic` is the neutral fallback. A brand may override any of them with `<slug>-<name>.html` (§8). A/B and pre-test variants change one variable inside the frame | §7, P8 |
| Hook | **3–6 words, a complete statement** (subject + verb + stake), or a verified number + unit inside a statement. Noun fragments of ≤2 words are rejected; >6 words is a warning. **`duo`: 3–4 words in 2 lines, every line ≥ 20 % of the height.** Rendered by the template, never by a model | P4, §5.3 |
| Face | Claim templates: face ≥ 35 % of the height (error), target 40–50 %. Cap 2.0× effective at 1280. Served-size detail ≥ 713 (warning) / ≥ 569 (error) | §10.1, §12.4 |
| Guest pixels | Policy ladder 0–5 (§11.2). Levels 0–2 and **2b** allowed; `guest_style: none` is the default, `graphic` enables outline/glow and the tone LUT; `grade: mono` is level 2b (an option); face pixels checked automatically | §11 |
| AI generation | Props and plates from text only, in the main session, with cost preflight and the profile's caps; never people, never text inside the image | §17 |
| Engine | `yt-thumb-render --engine html` (default in `youtube:thumbnail`: the automated pre-checks run only on this path) or `--engine remotion` (Remotion `ThumbnailStill` via `renderStill`: no automated pre-checks; own and personal channels only, with `graphics_licence` confirmed). Clients: `--engine html` only | Design §2, §11 |
| Concepts | 3 concepts = **3 different hypotheses**, not three styles, on ≥ 2 levers; ≥ 8 hooks brainstormed first; each concept is cold-read at 168 px before G1 | §5, §13.3 |
| Gate | Candidate renders + QA before **G2**; final pack (locked masters, JPEG, Spotify, derivatives, test pack) only after G2 | Design §2 |
| Learning | Single variables (expression, source, `guest_style`, headline face): **human pre-test** (§15.2). Native YouTube A/B: a **package safety check**, old package vs new, on the next new episode from release day (§15.1). The operator runs both by hand | §15 |
| Scoreboard | SQLite `ab_tests` (`kind` thumbnail / title / both / pretest) + the agent's MEMORY.md; a pattern counts after ~3 **decisive** tests in the same direction | §16 |

---

## 1. Contract, files and commands

All paths are inside the episode workdir `<studio_dir>/work/<channel>/<YYYY-MM-DD>-<slug>/`.

```
thumbs/concepts.json   thumbs/frames/   thumbs/portrait/   thumbs/cutouts/   thumbs/plates/
thumbs/renders/        thumbs/qa/       thumbs/cold/       thumbs/props/     thumbs/pretest/
```

### 1.1 `thumbs/concepts.json` (v2, backward compatible)

The agent writes it; `yt-thumb-render --data` reads it (a list, one object, or `{"concepts": [...]}`). Example (fictional guest and lines, illustrative only):

```json
[{"id": "A", "lever": "claim", "template": "duo",
  "hook": "IL CODICE NON BASTAVA", "keyword": "CODICE", "accent": "auto",
  "people": [
    {"cutout": "thumbs/portrait/sara_0812.png", "role": "guest", "name": "Sara Riva", "title": "Founder di un SaaS per dentisti"},
    {"cutout": "thumbs/portrait/marco_0815.png", "role": "host", "name": "Marco Bassi"}],
  "host_tag": "con Marco Bassi", "circle_behind": "guest",
  "meta_line": "MAKER MEETUP / 2026", "format_label": "IL PODCAST DEI MAKER", "show_logo": "wordmark",
  "grade": "natural", "guest_style": "none", "plate": {"source": "scene", "path": "thumbs/plates/plate_0815.png"},
  "expression_class": "intenso", "payoff_at": 812.4,
  "title_pair": "Dodici mesi da sola su un SaaS per dentisti: cosa ha portato i primi clienti",
  "hypothesis": "maker che sanno programmare: scoprire cosa è servito oltre al codice"}]
```

| Field | Required | Meaning | Older name still read |
|---|---|---|---|
| `id` | yes | Letter = the bet (hypothesis). Variants of the same bet get a number in the render filename (§12), never a new letter | — |
| `lever` | yes | `claim` · `proof` · `duo` · `name` (§5) | — |
| `template` | yes | A built-in template of `scripts/yt/node/templates/` (`duo`, `ritratto`, `scena`, `prova`, `generic`: list the folder) or a brand's `<slug>-…` (§8) | — |
| `hook` | yes | 3–6 words, a complete statement (§5.3); `\|` forces a line break | `text` |
| `keyword` | yes | The one word set in the accent box; it must appear in `hook` | `highlight` |
| `accent` | yes | the name of an accent token of the brand, or `auto`: **one** accent per composition (§7.2, §7.7). `auto` picks, among the brand's automatic accents (`accents_auto` in `tokens.json`, else `accents`; the profile's `thumbnails.accents` when set), the one with the larger ΔL* from the hair and face of the person in front of the circle, measured on the graded cutout | `accent` |
| `people` | when a face is used | List of `{cutout \| frame, role: guest \| host, name, title}`. `cutout` = a PNG from `yt-portrait cut` (drawn 1:1); `frame` = a frame the toolkit cuts itself. `name` = public name; `title` = the credential line (role, company) | concept-level `cutout` / `frame` (one person) |
| `meta_line` | series frame | Small caps «EVENTO / ANNO», or «CITTÀ / EVENTO / ANNO» when the city adds something. Every item verified (place and date of the recording); fewer items are fine, an unverified item never; never an implied sponsor | — |
| `format_label` | series frame | The show label from the profile (`thumbnails.format_label`, e.g. «IL PODCAST DEI MAKER»), top-right, outside the hover zone | — |
| `show_logo` | series frame | `"wordmark"` (default): the channel name set as text from the brand tokens (`wordmark.text` in the `wordmark.font`), light on the dark plate, top-left, legible at 360 px (`true` means the same); `"symbol"` = the brand's logo mark alone (`logo.mark_on_dark` on dark fields); `false` = none; always **without** an episode number | `episode` / `ep_num` (shown only when set; off by default since v2) |
| `host_tag` | `duo` | The host's small tag, default «con <host name>» (profile `thumbnails.host_tag`): the host is named, without a second name plate | — |
| `circle_behind` | `duo`, `ritratto` | `guest` (default) · `host` · `none`: the accent circle behind that person (§7.7; checked by `circle_contrast`) | — |
| `grade` | default from the profile | `natural` (default) · `mono` (**level 2b**, §11.2: one monochrome curve on every person and on the plate), an option on every template | — |
| `guest_style` | default from the profile | `none` · `graphic` (§11.2); independent of `grade` | — |
| `plate` | default `{"source": "flat"}` | `{source: "scene" \| "flat" \| "prop", path?}`: the episode's own scene (darkened copy, pop-out), the brand field, or a prop from §17 (placeholder until approved) | `plate` as a plain path (= `scene`) |
| `expression_class` | when a face is used | Class from `yt-portrait scan` (§10.2), matched to the lever (§5.5) | — |
| `payoff_at` | yes | Seconds on the **source** timeline where the promise is paid. The cold-open EDL must contain it (P2) | — |
| `title_pair` | yes | The title this thumbnail is designed to sit next to (the locked title or an A/B title candidate) | — |
| `hypothesis` | agent only | One line, written **before** the cold read: who it is for + what it promises. The renderer ignores it; the cold reader never sees it | — |
| `variants` | optional | Alternative hooks of the same bet (both 3–6 words) | `variants` |
| `hook_font` | optional | `"display"` sets the headline in the brand's own display face (`tokens.json` `fonts.display`) instead of the v2 default Anton (§7.7) | — |
| `person_tone` | optional, only with `guest_style: graphic` and `grade: natural` | Level-2 tone on the whole cutout: `none` · `look` (the brand's `look-33.cube`) · `duo`; the strength is capped by the skin bound (§11.2). Ignored with `grade: mono` | — |
| `prop` | with `plate.source: "prop"` | `{prompt, slot, path?}`: the text-only request of §17; without `path` the template draws the local placeholder | — |
| `display_cap` | optional | Per-concept cap factor (2.0 = option c, 1.5 = option b, §10.1) | — |
| `hook_form` | optional | `contro` marks a negation-of-belief hook inside the claim lever (§5.5): the only hook form that may pair with `expression_class: scettico` (the render warns otherwise) | `lever: contro` |
| `upscale_override`, `face_floor_reason`, `detail_reason`, `hook_size_reason` | G2 only | Written reasons to exceed the cap, the face floor, the served-size detail or the line-height floor and the `duo` word count (§12.4), copied into the G2 brief; `yt-thumb-qa` reads the same fields | `upscale_override` |

Other fields the toolkit still reads (`yt-thumb-render --help`): `frame` + `roi` ("x,y,w,h" \| "inset" \| "wide" \| "full"), `point`, `exclude: "pip"`, `artifact` (proof), `bg`, `side`, `face_frac`, `face_cx`, `face_top`, `kicker`, `tokens` (`generic` only). If a needed field is missing, stop and report; do not improvise CSS.

### 1.2 Commands

| Step | Command |
|---|---|
| Rank the guest's frames (whole episode, expression classes) | `yt-portrait scan WORKDIR [--src FILE] [--layout auto\|inset\|wide\|full] [--from --to] [--seat right] [--out DIR]` → `scan.json`, `scan_sheet_*.jpg`, `scan_expr.jpg` (one row per class, v2) |
| Tight-camera ISO (v2) | `yt-portrait scan WORKDIR --src <wd>/src/iso/<file> --layout full --out <wd>/thumbs/portrait/<persona>` |
| Expression signals (v2) | `yt-portrait scan … --expr auto\|vision\|mediapipe` (default `auto`: MediaPipe blendshapes when `install.sh --with-mediapipe` installed them; otherwise the Apple Vision geometry, which needs no install). `scan.json` states which signals it used |
| Cutout at final size | `yt-portrait cut WORKDIR --t T[,T…] [--src FILE] [--roi auto\|inset\|wide-left\|wide-center\|wide-right\|full] [--face-frac F\|--face-px N\|--upscale U] [--display-cap c\|b] [--name N] [--out DIR]`; guest-supplied photos: `yt-portrait cut - --image FILE` |
| Location plate | `yt-portrait plate WORKDIR --t T [--name N]` (people removed by classical fill, no AI) |
| Extract frames | `yt-frames WORKDIR --times t1,t2… [--out DIR] [--size full\|1080\|540]` or `--every N [--from --to]` |
| Score faces | `thumbvision score IMG…` → `[{"file", "faces": [{"box": [x,y,w,h], "quality", "eyes_open", "mouth_open"}], "sharpness", "best_face_quality"}]` (box normalised 0–1, origin top-left) |
| Cutout (Vision, fallback) | `thumbvision cutout IMG --out PNG [--mode person\|subject]` |
| Render | `yt-thumb-render --template T --data FILE --out DIR [--engine html\|remotion] [--debug] [--spotify]` → PNG 3840×2160 + JPEG < 2 MB + `.render.json` sidecar |
| QA sheet + grid mock | `yt-thumb-qa IMAGES… --out DIR [--grid DIR] [--title T] [--channel-name N] [--pos 0–8] [--seed S]` |
| Cold-read tiles | §13.3 (ffmpeg-full, by absolute path) |
| Remotion still (direct) | `yt-remotion still COMPOSITION --props FILE --out FILE [--scale N]` |

For the v2 flags (`--layout full`, `--display-cap c|b`) the `--help` of the installed toolkit is the truth.

Agent-written notes are not CLI outputs: the rubric table goes into `<workdir>/qa/report.md` (section "Thumbnail"), the test plan into the episode-package note (`deliver/notes/`, or the vault folder the profile names; new dated file, `skill: /youtube:thumbnail`, `status: draft`).

**Templates.** Built-in v2 series (`scripts/yt/node/templates/`): `duo`, `ritratto`, `scena`, `prova` (§7.7) and the neutral `generic` (§9); shared code `_common.js`. All text, colours and the wordmark come from the brand tokens and the concept: no channel string is hard-coded. A channel's brand may bring its own templates from the operator's `brands_dirs` (`<brands_dir>/<slug>/templates/<slug>-*.html`, §8), never from the plugin. **A template that is not in the folder is not rendered**: list the folder first and use the closest built-in, saying so in the brief.

---

## 2. Platform facts (official unless marked)

| Fact | Value | Source (verified 2026-10-11) |
|---|---|---|
| Recommended size | 3840×2160 (16:9), min width 640 px; Shorts 2160×3840 | https://support.google.com/youtube/answer/72431 |
| File size | JPG/PNG; ≤2 MB uploading from mobile, ≤50 MB from desktop | same |
| Podcast playlists | 1:1 image (10 MB mobile / 50 MB desktop) — a podcast needs one square show cover | same |
| Vertical videos | A 16:9 custom thumbnail is replaced by an auto 4:5 on Home, Explore, Subscriptions | same |
| Eligibility | Custom thumbnails need a verified account; strikes can remove the privilege | same |
| Custom Shorts thumbnail | Settable only in desktop Studio; mostly unseen in the Shorts feed (Sherman 2023) | same; https://techcrunch.com/2023/08/25/youtube-demystifies-the-shorts-algorithm-views-and-answers-other-creator-questions/ |
| A/B test | Up to 3 titles and/or thumbnails; winner by **watch time share**; few days up to 2 weeks; desktop Studio + advanced features; not for Shorts, scheduled lives, Premieres (until converted), made-for-kids, mature-audience, private. «If your video receives a higher number of views, then the more likely a 'Winner' will be declared» | https://support.google.com/youtube/answer/13861714 (re-read 2026-10-12) |
| A/B downscale trap | If any variant is below 1280×720, all are downscaled to 854×480 | same |
| A/B mechanics | Editing title/thumbnail mid-test stops it; a small control group sees only the default (excluded); outcomes Winner / Performed same / Inconclusive; inconclusive keeps the first-uploaded option | same |
| Impression | Thumbnail shown >1 s with ≥50% visible; embeds and end screens excluded | https://support.google.com/youtube/answer/9314486 |
| CTR range | Half of channels and videos sit at 2–10% [official]; Home exposure lowers CTR; judge only after substantial impressions | https://support.google.com/youtube/answer/7628154 |
| CTR source | Impressions and CTR exist only in the Reporting API reach reports (`channel_reach_basic_a1`, `channel_reach_combined_a1`), never per A/B arm | https://developers.google.com/youtube/reporting/v1/reports/channel_reports |
| Clickbait | Thumbnails that trick users into a video that doesn't deliver violate spam/deceptive practices | https://support.google.com/youtube/answer/2801973 |
| AI disclosure | Generative help to create/improve a thumbnail is production assistance, no disclosure needed; realistic altered video of real people is | https://support.google.com/youtube/answer/14328491 |
| Spotify video podcast | 16:9, ideally 1920×1080; consistent style across the series | https://support.spotify.com/us/creators/article/thumbnails/ |
| Per-language thumbnails | Reported rollout for channels with multi-language audio (2026-03-12); later-stage lever for EN versions | https://www.storyboard18.com/digital/youtube-introduces-translated-thumbnails-to-boost-global-video-discovery-91902.htm |
| Coming (not confirmed for Italy) | Dynamic thumbnails (3 options shown to different segments); Studio auto-swapping underperformers; AI thumbnail suggestions (announced 2026-09-23): any output that alters a face is not used | TechCrunch 2026-09-23, https://techcrunch.com/?p=3167584 |

**Display sizes — measured, not official** (F3 §1.7: built-in browser, logged out, Italian locale, 2026-10-11; the sidebar confirmed by Engaged Views' `surfaces.json`, CC BY 4.0, measured 2026-08-28, https://engagedviews.com/api/surfaces.json):

| Surface | Rendered size (CSS px) | Background |
|---|---|---|
| Desktop search | 500×281 | #0f0f0f dark / #ffffff light |
| Desktop home/channel grid | 347×195 (420×236 on 1600–1920 viewports) | same |
| Desktop watch sidebar (up next) | 216×121 — the smallest common surface | same |
| Mobile web feed | 375–393 wide (full width) | same |
| Duration badge at grid size | ~48×20 px, 8 px from right, bottom-right | rgba(0,0,0,.8) |
| Desktop hover | "watch later / queue" icons top-right; inline preview replaces the thumbnail | — |

"168×94" is the declared size of a file YouTube serves to the sidebar, not the box it paints (Engaged Views' published correction); the QA sheet keeps 168 as a **stress test**.

**Files YouTube actually serves** `[misurato]` (public HTML read logged out on 2026-10-12, study synthesis §10.2; one sample, may vary with account or experiment):

| Surface | Files the page requests | Largest |
|---|---|---|
| Channel grid and search, desktop | `hq720` 360×202 and 720×404 (1× and 2×) | 720×404 |
| Watch-page sidebar | `hqdefault` 168×94, 196×110, 246×138, 336×188 | 336×188 |
| Channel, mobile web (iPhone user agent) | 120×90 … 640×480, plus `hq720` 686×386 | 686×386 |
| iOS/Android apps, TV | not observed | **unknown** |

Consequences: the web never shows our 1280 master directly; detail is judged in the **720×405 file** (§10.1, §12.4). Phones and Retina screens then enlarge that file for every channel alike. Apps and TV are the open risk: until the device split of the channel is known (§15.0), the 2.0× cap (§0.1) stands with the 1.5× fallback ready.

At the 1280×720 design basis these give the no-go zones: **bottom-right 230×110** (badge + margin) and **top-right 120×80** (hover icons, no critical content).

---

## 3. Evidence base (what the data says, with labels)

All studies are correlational; none proves a thumbnail feature causes performance.

| Finding | Label | Source | Use in this file |
|---|---|---|---|
| Faces, brightness, contrast, saturation, background type do **not** separate breakouts from underperformers (faces 84.2% vs 82.2%) | [study] Eden, 507,478 videos / 2,960 thumbnails, Aug 2025–Aug 2026, vendor-run, observational | https://eden.so/blog/what-makes-a-good-youtube-thumbnail/ | Faces are not a default win; value contrast is a legibility check, not a CTR lever |
| 4–6 overlay words: largest gap (30.6% vs 26.5%); no text ~25% more common among underperformers; 7+ leans losing | [study] Eden | same | Hook band 3–6 words (P4); always some text |
| Eye contact 32.4% vs 29.2%; neutral/serious 51.1% vs 47.4%; smiling 21.2% vs 23.4% (leans losing); drawn arrows/circles 41.8% vs 38.1% | [study] Eden | same | Expression and gaze are variables to pre-test, not rules (§5.5) |
| Video length and title length move breakout rate more than any thumbnail feature (26.9% under 5 min vs 41.1% over 40 min) | [study] Eden | same | ~50-min podcast episodes are not handicapped; invest in title + hook |
| Faces in 69% of 500 breakouts, 80% of top 50; high contrast declines with breakout size; ~5% exaggerated expressions; median 5 words when text is used | [vendor] vidIQ, July 2026 (page 403, cross-checked via SEJ) | https://vidiq.com/research/youtube-thumbnail-study/ | Clear, well-lit, genuine faces; no staged shock |
| Face vs no-face similar overall; faces helped **channels above a subscriber threshold** (the threshold is channel size, not face size); Business among the niches where faces help less; multiple faces beat one | [vendor] 1of10, 300k videos, via SEJ 2025-12-22 (re-read 2026-10-12) | https://www.searchenginejournal.com/do-faces-help-youtube-thumbnails-heres-what-the-data-says/563944/ | The duo frame is valid for interview shows; faces are not a guaranteed lever for a channel with few subscribers |
| Reference set of 125 interview-podcast thumbnails (13 channels, 66 English): face height median **48 % EN** / 39 % all (Vision box); head-and-shoulders or tighter 77 % EN; crown cut by the top edge 53 % EN; ≥ 2 faces 59 %; hook median 4 words, 53 % of EN hooks are complete statements, none a 2-word noun fragment; one accented word 82 % EN; small logo 73 %, episode number 8 %; guest name 52 % (Lenny 10/10 with role + company logo); mics or headphones visible 45 % (IT 73 %); outline around people 22/125, all Italian, 0/66 EN | [misurato] (sizes, detail) + [codificato] (one coder) — study R3 | internal study, not distributed (public channel pages listed in §6) | P1, P4, P8, §7.7, §11.2, §12.4 thresholds |
| Renders of an earlier template generation (one podcast, four renders) vs that set: face 23.8 % vs 48 %; hook 2 words vs 4; 0 % credential; 100 % sceptical expression; face–surround ΔL* 6.9 vs 30.9 | [misurato] study R3 §6 | same | The v2 gaps (§10, §12.4) |
| Among covers with a face: neutral 35%, happy 32%, shocked 11% | [vendor] Thumbnail Bench, 11,223 covers (what creators do, not performance) | https://www.netinfluencer.com/?p=53558 | Context only |
| ~1.8 s per title while browsing; complex emotions beat stoic; ≤3 people better | [anecdotal] Netflix ~2016, other platform, secondary coverage | https://about.netflix.com/news/the-power-of-a-picture | Directional support for the 1-second glance test |
| ~50 title/thumbnail concepts per video; test at real size; thumbnail must match the intro; closed mouth won on watch time in ~30 Test & Compare runs (small, unpublished gains) | [anecdotal] MrBeast thumbnail lead, via Social Media Today 2024-03-08 | https://www.socialmediatoday.com/news/youtube-shares-insights-mrbeasts-team-creates-compelling-thumbnail/709817/ | P2, P3, P11; closed mouth = hypothesis |
| Top creators spend ~30% of time on packaging vs ~5% for small ones; "familiar but unexpected"; ~4–5 words | [anecdotal] Paddy Galloway via Colin & Samir | https://www.colinandsamir.com/resources/the-new-rules-of-youtube-from-paddy-galloway | P8, P11 |
| DOAC visualises 20–30 candidate topics as thumbnails and tests them before choosing | [anecdotal] secondhand | https://www.colinandsamir.com/resources/how-diary-of-a-ceo-became-youtubes-1-show | Concept-first workflow |

**Do not encode** (no primary source; listed in 10-evidence-ledger.md): "+154% CTR", "faces +38% CTR", "red = 7% CTR", "curiosity text 5.83%", "73% repeat the title", ">3 elements = −23% CTR", "tool logos in 92% of tech thumbnails", "YouTube recommends 7:1 contrast", "62% decide in under 2 s", "63–70% mobile". If one of these turns up in a brief or a draft, delete it. The same goes for AI "CTR scores" (TubeBuddy, Pikzels, vidIQ analyzer): not validated, never cited.

---

## 4. Principles P1–P13

Check type: **A** = automated (template pre-check or script), **J** = LLM judge or cold reader reading the tiles, **H** = the operator at G2.

| # | Principle | Evidence | How it is enforced | Check |
|---|---|---|---|---|
| P1 | Thumbnail and title are one message and never repeat each other: the thumbnail shows or claims, the title explains | [study] Eden (verbatim repetition rare in both groups); [anecdotal] Appleby | Repetition test (§5.4): no shared content word, numbers included | A + J |
| P2 | The promise is paid in the first 30 s, ideally the cold open shows the thumbnail moment | [anecdotal] Appleby; [official] A/B winner = watch time; spam policy | `payoff_at` must fall inside a cold-open segment in `edl.json`; otherwise the concept is dropped or the cold open changes at G1 | A |
| P3 | One focal point, readable in ~1 s at 216 px wide | [anecdotal] Appleby, Netflix 1.8 s; measured UI sizes | QA sheet glance tiles; cold reader at 168 px (§13.3); rubric items 1–2 | J |
| P4 | **v2.** The hook is **3–6 words and says something on its own**: a complete statement with subject + verb + stake, or a verified number + unit inside a statement. A noun fragment («UNA MAIL», «IL CALENDARIO») is never the hook. Never zero text | [study] Eden 4–6 band and no-text penalty; [vendor] vidIQ median 5; [misurato + codificato] R3: median 4 words, 53 % of EN hooks are statements, none a 2-word fragment | `concepts.json` validation and render pre-check: < 3 words or a fragment = error, > 6 words = warning, > 3 lines = error | A + J |
| P5 | **v2.** Real, well-lit faces with a **genuine expression that matches the claim**. Expressions are **found, never staged**: searched in the footage (tight fixed camera ISO first, then main camera ISO, then master frames; §10.1) by class (§10.2). No photo session (§0.1); never pose a guest for a thumbnail, never edit an expression | [vendor] vidIQ ~5% exaggerated; [study] Eden neutral/eye-contact edge; [anecdotal] Appleby closed mouth; house default (§0.1) | Source priority + expression classes (§10); policy ladder (§11.2) | A + J |
| P6 | Faces depend on niche and channel size; two faces can beat one | [vendor] 1of10 | The series frame is a duo by default (§7.7); single-face vs duo is a pre-test variable | H |
| P7 | Contrast means **value** (luminance) separation, not saturation | [study] Eden/vidIQ; WCAG relative-luminance math | Token whitelist (§7.2; external brands, §8–§9); grayscale tile; face–surround ΔL* (§12.4) | A + J |
| P8 | **v2.** **One familiar series frame, new content.** A channel uses one fixed frame (§7.7): logo, typography, credential, meta line, format label, accent shape and person placement stay put; what changes is the person, the expression, the hook, the accent colour and the field mode. Tests vary **one** variable inside the frame. The older rule "rotate 2–3 layouts" is retired; the "different from the last uploads" check applies to the photo, the expression class and the accent | [codificato] R3: 7 of 13 reference channels keep a near-invariant frame; [anecdotal] Galloway "familiar but unexpected"; Spotify consistency guidance [official] | Template set per channel; the agent compares expression class and accent with the previous upload (MEMORY.md) | A + H |
| P9 | Keep UI zones clear: bottom-right badge, top-right hover icons | measured 2026-10-11 | Geometric pre-check fails the render | A |
| P10 | Exaggerate the framing, never the facts: no invented quotes, numbers or expressions; guest pixels are real pixels within the declared policy level | [official] spam/deceptive policy; titus-ai preserve-people rule (paraphrased) | Claim verbatim or faithful with timestamp; numbers verified with guest/show notes; policy ladder and automatic face checks (§11) | A + J + H |
| P11 | Many concepts, few shipped; the test decides | [anecdotal] Appleby ~50; DOAC | ≥ 8 hooks internally → 3 concepts on 3 hypotheses → cold read → 2 hook candidates each → test | J |
| P12 | Optimise for clicks that stay (watch time), not raw CTR | [official] A/B docs; CTR help (high CTR + low AVD = warning) | Test log records watch-time outcome and the Intro (0:30) of the video | H |
| P13 | Design against the real feed, both themes | design inference from observed DOAC/Lex palettes | Grid mock dark + light (§13.2); rubric item 8 | J |

---

## 5. Levers, hypotheses and hooks

A lever is the reason someone clicks; a **hypothesis** is the bet a concept makes about who clicks and why («maker che sanno programmare: scoprire cosa è servito oltre al codice»). The three concepts must differ in hypothesis, not just in wording or styling: three styles of the same idea count as one concept. When §5.2 forces a repeated lever, the repeat must use a different line, a different expression class and a different hypothesis.

### 5.1 Lever definitions

| Lever (`lever`) | The click comes from | Needs | Fails when | Template (v2) |
|---|---|---|---|---|
| `claim` (default) | A surprising, true first-person statement by the guest or host | A verbatim or faithfully compressed line with timestamp | The line needs context to make sense; it is a cliché ("CREDI IN TE STESSO") | `duo`; `ritratto` without a usable host frame; a brand's claim template (§8); `generic` |
| `proof` | Evidence of work: a real number, a real product UI, a physical object | A verified number or a screenshot the guest authorised | The number is unverified, estimated, or a target dressed as a result | `prova`; `generic` + `artifact` |
| `duo` (tension) | Two people and an open question or disagreement | A real disagreement or reveal in the episode; both cutouts usable | There was no tension; the "VS" is staged | `duo` with the host's real question as hook; a brand's duo template if it has one (§8); `generic` + two `people` |
| `name` | The guest's name is itself the draw | A guest with their own audience (searched, recognised in the niche) | The guest is unknown to cold viewers (most guests of a small show) | `ritratto` with the name in the name plate and a statement as hook |

### 5.2 Lever choice table (per episode)

| Guest recognisability | Verified number or artifact? | Real tension in the talk? | Three concepts to build |
|---|---|---|---|
| none (the usual case) | yes | yes | claim · proof · duo |
| none | yes | no | claim · proof · claim-2 (different line, expression class and hypothesis) |
| none | no | yes | claim · duo · claim-2 |
| niche (known in the channel's niche) | any | any | claim · name · proof-or-duo |
| known (has own audience) | any | any | name · claim · proof-or-duo, and invite as Collaborator (01-platform-facts.md) |

Recognisability is decided with evidence: the guest's own channel/LinkedIn following, search presence, and the operator's call. When unsure, treat as "none". Every concept writes its `hypothesis` before the cold read (§13.3).

### 5.3 Hook writing rules (Italian, on-image) — v2

- **3–6 words**, a **complete statement**: subject + verb + stake («IL CODICE NON BASTAVA», «HO CHIUSO IL MIO PRIMO SAAS»), a past-tense admission, the negation of a belief, a short real question, or a verified number + unit **inside** a statement («DA 0 A 40 STUDI IN UN ANNO»). A bare number + unit of two tokens is a fragment.
- **Rejected**: noun fragments without a verb or a number («UNA MAIL», «UN FOGLIO», «IL CALENDARIO») — an earlier generation of hooks measured in the study had 7 fragments out of 8. Over 6 words: warning, cut it unless the extra word carries the stake.
- Numbers and symbols count as one word each («0 → 30K€» = 3). Every number is verified, with a timestamp; achieved results kept apart from targets.
- **Two hook candidates per concept**, both 3–6 words (e.g. one of 4 and one of 6 words). The old "corta" version of 1–2 words is retired.
- **`duo`: 3–4 words**, still a complete statement, set in **2 lines** (3 only if a word is very long) with **every line ≥ 20 % of the canvas height** (lines around 13 % read as small at feed size on test renders). More than 4 words or a line under 20 % is a render error (`yt-thumb-render`) and a QA error (`yt-thumb-qa` `hook_words`, `phrase_line_h`), overridable only with `hook_size_reason` at G2. When the transcript does not allow a faithful 3–4-word compression, use `ritratto` (3–6 words) instead of a fragment. Before paraphrasing, try the line break: the template glues 1–3-letter words to the next word, so «Abbiamo deciso di vendere.» breaks as «ABBIAMO / DECISO / DI VENDERE.» (4.36 em, 16.6 %); a forced break with `|` that keeps the verb with its preposition, `"Abbiamo | deciso di | vendere."` (widest line 3.51 em), reaches 20.1–20.5 % with the same people once the circle is raised a little (`disc_dy` −0.7, `disc_k` 1.3, `text_gap` 6; measured on a test render) and keeps the hook verbatim.
- One `keyword` per thumbnail, set in the accent box (ink text on the brand's accent, §7.2). The keyword is the word that carries the stake, not an article.
- Concrete nouns and verbs from the transcript vocabulary; the guest must recognise the words as theirs.
- Forbidden: the profile's banned words (`voice.banned`), empty superlatives (incredibile, imperdibile, pazzesco), bait phrases ("NON CI CREDERAI", "GUARDA FINO ALLA FINE"), and whatever the channel's `copy_rules` forbid (tool names, punctuation, formats).
- Public names exactly as in the profile's `voice.public_names` (name plates, host tags, briefs); never a name listed under `never`.
- Episode-specific blocks go in the episode note (e.g. «no numbers in hooks until the revenue figures are confirmed by ear»).

### 5.4 Title-pairing test (P1)

1. Lowercase both strings; split on spaces and punctuation; keep numbers and symbols-with-numbers as tokens.
2. Drop Italian stopwords: articoli (il, lo, la, i, gli, le, un, uno, una, l'), preposizioni semplici e articolate (di, a, da, in, con, su, per, tra, fra, del, della, nel, sul, …), congiunzioni (e, o, ma, che, se), ausiliari (è, ha, ho, sono), "non".
3. Compare stems = first 5 letters of each remaining token (catches studi/studio, costruito/costruire).
4. **Fail** if any stem or number is shared. Override only with a written reason in the G2 brief (e.g. the name-led lever deliberately repeats the guest name in title and thumbnail — then the title must lead with credential, not name). The name plate (`people[].name`, `title`) and the meta line are not part of the hook and are not tested.
5. Judge step: do the two together open **one** gap? Title promises the outcome, thumbnail shows the tension or the proof.

### 5.5 Expression ↔ lever (v2)

Classes as printed by `yt-portrait scan` (v2): `sorriso` (genuine smile), `risata` (open-mouth laugh, teeth), `intenso` (closed mouth, eyes open, no smile: the claim face, also «mentre spiega»), `sorpresa` (brows up, eyes open), `neutro` (no strong signal), `scettico` (pressed or rolled lips, asymmetric grimace). If the installed scan prints other names, its names win and this table maps onto them.

| Lever or hook form | First-choice class | Second choice | Avoid |
|---|---|---|---|
| claim: thesis, admission | `intenso` | `sorriso` | a mid-word grimace (the scan drops those frames from the class rows) |
| claim "contro" (negation of a belief) | `scettico` | `intenso` | `sorriso`, `risata` |
| proof: result or number | `sorriso` (satisfied), `sorpresa` (contained: never staged shock) | `intenso` | — |
| story: failure, risk | `intenso` (worry in the foreground) | `neutro` | `sorriso` |
| duo: question or tension | guest `intenso` while talking; host's genuine reaction (`sorriso`, `risata`, `sorpresa`, or `scettico` when it matches the host's real stance) | `neutro` for a listening host | a staged "VS" |
| name | `intenso` to camera | `sorriso` | — |

Source: [anecdotal] practitioner table (TheCraigHewitt, via study synthesis §3a.2) + [codificato] R3 P7. **No "maximum emotion"**: Eden's smiles lean losing while 47 % of the reference guests smile; the class is a variable for the pre-test, one class at a time (§15.2). `scettico` is selectable only for a "contro" hook.

---

## 6. Archetypes observed and what to borrow

| Archetype | Example | Pattern | Borrow for own channels | Avoid |
|---|---|---|---|---|
| A. Quote-led duo | The Diary Of A CEO | Black field, guest talking off-camera, the host reacting to camera (the same recurring asset, not always chin-on-hand), 3–6-word claim, **red** keyword box, small badge top-left, a «New» tag. Its black field has the lowest tile-edge contrast of the 2026-10-12 sample (ΔL* 11.8) with no visible penalty | Guest speaks, host reacts: the `duo` structure; one keyword box | Copying the black field as a rule |
| B. Credential portrait | Lenny's Podcast | Guest portrait to camera, sentence on paper strips, **name + role + company logo** on 10/10 | The credential (name plate + role line) on every claim | A logo without the guest's permission |
| C. Giant face | 20VC | Face 54 % of the height, crown cut by the top edge, number + unit hooks | Head-and-shoulders, crown allowed out of the top edge | — |
| D. Rigid typographic template | Lex Fridman | Low-key portrait right, monospace text top-left, episode number as a collectible ("#502") | A fixed typographic grid for any series | Expecting the brand alone to pull clicks; the episode number (only 8 % of references use it) |
| E. Name-led duo + badge | The BSMT | Host + guest cutouts with headphones and mics, guest name on a lime brush stroke, show badge centre, cutout outline (Italian register) | Mics as podcast signifiers | Name-led with unknown guests; the outline as a default |
| F. Giant name typography | Gurulandia | Huge two-line name, close-up right, hosts small; grayscale check showed the yellow first name collapsing to the same grey as the white surname | Proof that the grayscale tile catches real failures | Same-luminance text colours |
| G. Editorial duo (the toolkit's own v2 frame) | — (a common editorial pattern, not one channel) | Two people head-and-shoulders with mics in frame; real set photo; one accent; a huge condensed short headline centred between them; a big accent shape behind one person; name in a solid accent box + role line; a small meta line; show logo top-left; small format label top-right | The whole structure, in the brand's tokens: §7.7 | A label inside the top-right hover zone |

Sources: https://www.youtube.com/@TheDiaryOfACEO/videos · https://www.youtube.com/@LennysPodcast/videos · https://www.youtube.com/@20VC/videos · https://www.youtube.com/@lexfridman/videos · https://www.youtube.com/@bsmt_basement/videos · https://www.youtube.com/@gurulandia/videos (observed 2026-10-11 and 2026-10-12, F3 §4 and study R3 §4). Competitor and reference thumbnails are analysed privately, never copied, and deleted on schedule (11-compliance-safety.md §3).

---

## 7. Series templates

The built-in templates take every colour, font and string from the active brand (`tokens.json`) and from the concept: nothing channel-specific is written in them. Without a brand folder for the channel, the toolkit uses the neutral built-in brand **`demo`** (`scripts/yt/assets/brands/demo/`: tokens `ink`, `paper` and three accents `accent`, `accent_2`, `accent_3`; Anton for headlines and Inter for body, both SIL OFL in `assets/fonts/`; the wordmark is text from the tokens, `wordmark.text` = «Il tuo canale»; a generic placeholder mark in `logo/`). A channel's own brand lives in the operator's `brands_dirs` (§8).

### 7.1 Tokens and luminance (computed per brand, WCAG 2.x)

For every brand, before the first render, compute for each colour token: relative luminance, the Rec.601 grey value, and the contrast ratio against YouTube's dark page **#0f0f0f** and light page **#ffffff**. Write the table into the profile's `brand` block (or the G2 brief). Reading rule: a light field (paper and pastel tokens) pops in dark mode and blends in light mode (ratios ≤ ~1.7:1 against white); a dark field (ink) does the opposite. Mock both themes every time (§13.2).

### 7.2 Contrast whitelist (the template enforces it)

| Pair | Rule |
|---|---|
| Hook text on its field | allowed only at **≥ 4.5:1**, and only when the Rec.601 grey values differ by ≥ 60 levels |
| Display text only (cap height ≥ 86 px at the 720 basis) | ≥ 3:1 allowed (e.g. ink on a mid-luminance accent) |
| Highlight box behind display text with cap height ≥ 120 px | 3:1–4.5:1 allowed |
| Light token on light token, or two accents together | **forbidden** for text (they collapse in the grayscale tile) |
| A mid-grey token (metadata colour) | never for the hook; metadata only |

The brand's `text_pairs_allowed` in `tokens.json` is the computed list; the templates refuse any other pair. Additional rules: **one accent colour per composition** besides ink and paper (keyword box, circle, full stop and name box all use that one accent); a light logo only on ink or on a solid dark field; never recolour a logo; an SVG wordmark that loads web fonts must be inlined. Consequence for the name plate: when ink on the accent is display-only, the name sits ink-on-paper and the accent shows in the circle, the keyword box and the full stop.

**Accent on the monochrome grade.** With `grade: mono` the people are grey, so an accent that matched skin tone in colour may now work and vice versa: with `accent: auto` the template chooses, among the brand's accents, the one with the larger luminance contrast with the hair and face of the person in front of the circle, measured on the graded cutout; `yt-thumb-qa` `circle_contrast` prints the ΔL\* every accent would give. Mid-grey hair and skin (L\* 45–65) usually favour the lighter accent; dark hair against a light circle needs ΔL\* ≥ 20 at the hair edge. Still one accent, used in the graphics only, never on the people.

### 7.3 Shared geometry (1280×720 CSS basis, rendered ×3 = 3840×2160)

| Element | Spec |
|---|---|
| Safe margins | 64 px left/right, 56 px top/bottom |
| No-go zones | bottom-right 230×110 (x ≥1050, y ≥610); top-right 120×80 (x ≥1160, y ≤80) — no text, no face |
| Logo | top-left at (64, 56): the **wordmark** (the channel name set from the brand tokens) by default, legible at 360 px; the brand's logo mark with `show_logo: "symbol"` (≥ 140 px at 4K). **No episode number by default** (8 % of references show one; `ep_num` stays available when the operator asks) |
| Hook | Anton (or the brand's display face with `hook_font: "display"`, §7.7), ALL CAPS, line-height 0.9 (a line holding an accented capital — È, À, Ù… — opens by itself: in Anton the accent reaches 1.10 em above the baseline and would touch the line above); measured line height **≥ 12 % of the canvas height for every line** (cap ≥86 px at 720) and **≥ 18 % for the keyword** when it is set larger than the phrase (in the v2 one-size headline the 18 % is a target, reported as a warning); 2–3 words per line; ≤3 lines. **`duo`: every line ≥ 20 %** (target 22–23 %), 3–4 words in 2 lines (§5.3) |
| Keyword | one word, ink text in the accent box, padding 0 .12em, `box-decoration-break: clone` |
| Text on photo | paper fill + ink stroke via `-webkit-text-stroke` with `paint-order: stroke fill` (stroke under the fill, or it eats the letters); measured ≥4.5:1 on the PNG |
| People | real cutouts only, drawn 1:1; soft neutral drop shadow; treatments only within the declared policy level (§11.2) |
| Face vs text | text boxes never intersect any face box (from `thumbvision score`) |
| Crop edges | straight edges flush with the canvas (§11.1) |

Caps note: a channel's `copy_rules` may forbid ALL CAPS in **titles**. Thumbnail hooks are a graphic, not a title; caps stay the template default.

### 7.4 Template set

| Template | Lever | What it is |
|---|---|---|
| `duo` | claim, duo | Guest + host of the same episode, the series frame of §7.7 (**default**) |
| `ritratto` | claim, name | Guest alone, head and shoulders, larger face |
| `scena` | claim on the location | Pop-out over a darkened copy of the same instant |
| `prova` | proof | The real artifact (or a prop placeholder, §17), guest smaller |
| `generic` | claim, proof, duo, name | Neutral frame driven only by tokens and the concept (§9); the fallback for any lever a brand does not cover |

All five run the §12.4 pre-checks. Earlier layout families (a ring behind the head, a wall-graded field, a speech bubble, the first claim/proof/table layouts) are not shipped: P8 replaced the rotation of layouts with one series frame.

### 7.5 Derivatives (after G2)

| Asset | Size | Rule |
|---|---|---|
| YouTube master | 3840×2160 PNG + JPEG <2 MB | From `yt-thumb-render` |
| Spotify episode thumbnail | 1920×1080 | Downscale of the same master |
| Podcast playlist cover | 1:1, one static show cover (not per episode); render at 3000×3000 | Re-verify podcast-app cover specs in 01-platform-facts.md before reuse |
| Vertical (4:5 auto surfaces, Shorts cover) | 1080×1350 / 2160×3840 | Same frame, new viewport; faces in the upper two thirds; text away from the bottom UI |

### 7.6 Brand overrides of the built-in templates

A brand may replace a built-in template with its own file `<brands_dir>/<slug>/templates/<slug>-<name>.html` (e.g. `<slug>-duo.html`); a concept selects it with `"template": "<slug>-duo"`. The override must keep the §7.3 geometry, load its fonts and expose the same data fields, so the §12.4 pre-checks still run. Template-specific rules a brand adds (e.g. a ring that must stay ≥ 24 px from the edge or be cropped by ≥ 15 %, a bubble tail beside the host's mouth, guest face ≥ host face) are enforced by `yt-thumb-render` only when the template declares them; otherwise the agent checks them by eye and says so in the G2 brief.

### 7.7 v2 series frame (default)

**The frame.** An editorial duo: two people from the same episode, one huge headline between them, one accent colour, the brand's wordmark and a small format label. Each element has a fixed rule, so a channel's thumbnails stay recognisable while the person, the expression, the hook and the accent change (P8).

| Element | Rule in the series frame |
|---|---|
| Two people, head-and-shoulders, large, podcast mics visible | Guest + host from the same episode (tight camera ISO first), each face ≥ 30 % (claim: guest ≥ 35 %, target 40–50 %), crown may leave the top edge, mics kept in the cutout (`--mode subject` or BiRefNet with the mic) |
| Real set photo, one accent colour | `grade: natural` by default: people in natural colour (`guest_style: none`), or a partial level-2 grade with `graphic` (skin ΔE00 ≤ 2.5 mean / ≤ 5 p95). **Option `grade: mono`, policy level 2b** (§11.2): one monochrome curve (`mono-curve.json` of the brand, the `demo` one by default: Rec.709 luma → monotone curve → ink-to-paper ramp) on every pixel of both people **and** of the plate; the plate is the episode's own wide shot (`plate.source: "scene"`, `yt-portrait plate`), additionally darkened, blurred and vignetted (background operations), **never a flat grey**. Identity and expression intact, no local edits on faces, one accent in the graphics only |
| Huge condensed headline between the people, with a coloured full stop | **`duo`: 3–4 words in 2 lines, every line ≥ 20 % of the height**, centred between the faces, paper on the dark plate, the keyword in the accent box, the final full stop (or «?») in the accent colour. Display face: Anton by default, or the brand's display face (`hook_font: "display"`) |
| A big accent circle behind one person | An accent circle behind **the guest** (`circle_behind`, default `guest`), cropped by a canvas edge (≥15 % of its diameter) or ≥24 px from it; as a field mass it may pass under the top-right hover icons (nothing is lost there). Measured as **ΔL\* between the circle and the adjacent hair/face ≥ 20** (`circle_contrast`: error < 10, warning < 20), and the face–surround separation still holds (§12.4). With `grade: natural`, an accent of the same luminance as skin never goes behind a face (first generation measured a light accent behind light skin at ΔL\* 1.6) |
| Name in a solid accent box + a role line | `people[].name` (≥ 34 px at 720, face set by the template) ink on the accent box (paper box when ink on the accent is display-only, §7.2), `people[].title` in the body font below it; **the guest only**. The host gets a **small host tag** (`host_tag`, «con <host>»), so a plural hook («abbiamo») is not read as the two people on screen |
| Small-caps meta line (place, date) | `meta_line` in the body font, bold, letter-spaced caps, bottom-left above the safe margin, every item verified; the city only when it adds something |
| Show logo top-left | The **wordmark** (channel name from the brand tokens, light on the dark plate), no episode number |
| Small format label top-right | `format_label` (from the profile) right-aligned to x ≤ 1150 at y 56–80: outside the top-right hover zone |

**Layouts of the frame** (one frame, four modes; the folder of templates is the truth):

| Template | People | Field | When |
|---|---|---|---|
| `duo` (**default**) | guest + host, both large, **the same grade** | the episode's own scene plate, darkened and blurred | every episode with a usable host frame from the same episode (§10.5): claim and duo |
| `ritratto` | guest alone, head-and-shoulders, larger | scene plate or ink | single-face episodes; claim without a usable host frame; name-led. Prefer a **closed-mouth smile** frame (`yt-portrait scan`: class `sorriso` with a low `jawOpen`; if no frontal closed-mouth frame exists the scan says «non trovato» and the brief says so) |
| `scena` | guest (± host) over a darkened copy of the same instant (pop-out) | scene, full width | when the set itself says "podcast" (mics, table, venue) |
| `prova` | guest smaller, looking at or pointing to the proof | the real artifact (screenshot, chart) or a prop placeholder (§17) | proof lever with a verified number |

**Frame rules** (checked by the render, §12.4): one accent; logo, label, meta line and name plate outside the no-go zones; hook between the faces without touching a face box; bottom-right zone free of text and faces (a mic or a shoulder may cross it); `guest_style: none` by default on every mode (outline/glow only on request, §11.2).

**`duo` targets** — what the render and `yt-thumb-qa` check, and what the agent looks for on the sheet:

| Target | Rule | Check |
|---|---|---|
| Real scene plate | From the episode's own wide shot (`yt-portrait plate`), darkened and blurred (mono only with `grade: mono`); no flat grey field | `grade_mono` (plate C\*ab p95 ≤ 12, mono only); visual |
| One grade on both people | Same treatment on every person pixel (level 0, or 2b with the mono curve) | `grade_uniform`, `grade_face`, `grade_landmarks` (mono) |
| Host crop | The host cropped tighter so a light shirt is not the brightest area of the frame (crop, and with mono the curve's long shoulder: pure white lands at L\* ≈ 75, under the paper headline at 96) | render «masse chiare»; visual |
| Accent circle behind the guest | ΔL\* circle ↔ adjacent hair/face ≥ 20; face–surround still ≥ 20 | `circle_contrast`, `face_surround` |
| Headline | 3–4 words, 2 lines, every line ≥ 20 % (target 22–23 %), accent full stop | `hook_words`, `phrase_line_h`, `keyword_line_h` |
| Name plate + host tag | Guest: accent box + role; host: small tag | visual («who is the guest?») |
| Wordmark, label, meta line | Wordmark top-left; format label top-right outside the hover zone; meta line bottom-left; bottom-right timestamp zone clear | render no-go zones |
| Dark-feed separation | Tile edge ΔL\* vs YouTube's dark page #0f0f0f **≥ 25**, or a deliberate light frame element (the circle or a paper disc touching the edge for ≥ 10 % of the perimeter); vs the light page #ffffff ≥ 20 | `edge_dL_dark`, `edge_dL_light` (warnings) |

**Headline face.** v2 sets thumbnail headlines in one condensed SIL-OFL face, **Anton** (`assets/fonts/Anton-Regular.ttf`, OFL text next to it): a wide display face fits only 2–3 words per line at the v2 sizes. A brand may switch to its own display face (`hook_font: "display"`) after the same acceptance test: every hook word readable at 216 and 168 px on light and on dark, Italian accents (À È É Ì Ò Ù) present and legible, ≥ 3 words per line at the 12 % line height, with a 168-px comparison sheet against Anton in the G2 brief. Two faces are never mixed in one headline, and which one wins on clicks is a pre-test variable (§15.2).

---

## 8. Channel brands: `brands_dirs`

The plugin ships one neutral brand, **`demo`** (`scripts/yt/assets/brands/demo/`), the five built-in templates of §7.4 and the caption preset `default`. The brand of a channel (own, personal or client: tokens, logo, fonts, thumbnail templates, caption presets, Remotion styles) lives **outside the plugin**, in the operator's brand folders. It is never copied into the plugin and never committed (`CONTRIBUTING.md`); the folders survive plugin updates because the plugin never touches them.

**Where the toolkit looks.**
- `yt-config` key `brands_dirs`: a list of folders, default `["~/.config/youtube-producer/brands"]`, set in `~/.config/youtube-producer/config.yaml`. `YT_BRANDS_DIRS` (paths separated by «:») overrides it for one session or a test; `yt-config --init --brands-dir DIR` writes it. In the `yt-config` JSON, `brands_dirs` is the effective search list (it ends with the plugin's own folder), `brands_dirs_extra` the operator's folders, `brands` every visible brand with its folder.
- A brand is resolved by its slug: the first `<brands_dir>/<slug>/` that contains a `tokens.json`, in `brands_dirs` order, then the plugin's `scripts/yt/assets/brands/<slug>/` (which holds only `demo`). A folder without `tokens.json` is ignored. The first match wins, so never create an external folder named `demo` unless you mean to replace it. A channel without a brand folder renders with `demo`.
- The brand slug is the channel slug: the same as the profile `<slug>.md` in `channels_dirs`, `yt-auth --channel`, `yt-new --channel` and `<studio_dir>/work/<slug>/`.

**What a brand folder may contain** (all optional except `tokens.json`):

| Path | Content | Used by |
|---|---|---|
| `tokens.json` | Exact colours (HEX), font families and files, the accent and its alternatives, allowed text pairs, the wordmark text. Same shape as `demo/tokens.json`: `colors`, `fonts.display` / `fonts.body` `{family, file}`, `accent`, `text_pairs_allowed` | `yt-thumb-render`, `yt-remotion`, `yt-clips`, `yt-captions` |
| `logo/` | Logo files (SVG or PNG); usage rules go in the profile's `brand` block | templates |
| `fonts/` | Font files, each with its licence next to it (OFL text or the owner's licence). Local rendering must be allowed. libass needs static instances (one file per weight, in `fonts/` or `ass/fonts/`); variable fonts work in HTML and Remotion | HTML templates, ASS burn, Remotion |
| `layout.json` | Frame geometry for crops and ROIs: `canvas {w, h}`, a full-frame `wide` box, optional `inset` / `pip`. Same schema as `demo/layout.json` (written by `yt-clips layout --measure --write` for a composited master) | `yt-clips`, `yt-portrait`, `yt-thumb-render` ROIs |
| `look-33.cube`, `mono-curve.json`, `mono-33.cube` | The level-2 look LUT, the level-2b monochrome curve (§11.2) and its 33-point LUT for an NLE. Without `look-33.cube` the look is computed from the brand's own `ink` and `paper`; without `mono-curve.json` the series curve `mono-1` applies (the same as `demo`). A cube copied from another brand keeps that brand's colours: never copy it, regenerate it with `thumb_fx.py lut` / `mono-lut --brand <slug>` after the tokens change | `yt-thumb-render` |
| `templates/<slug>-*.html` | Thumbnail templates, named with the slug prefix (e.g. `<slug>-duo.html` to override `duo`, §7.6). A concept selects one with `"template": "<slug>-duo"`; `yt-thumb-render` looks in the brand folder of the prefix first, and the folder holding the template tells it which tokens and fonts to load | `yt-thumb-render --engine html` |
| `ass/<name>.json` | Caption presets for burned Shorts captions, same schema as `assets/ass/default.json` (`caption`, `hook`, `accents`, `default_accent`, optional `accent_once`, hook `prefix` / `prefix_color`). Convention: one preset named after the slug, used with `--style <slug>`; `font_file` names a file in the brand's `fonts/` or `ass/fonts/` | `yt-clips render`, `yt-captions --format ass` |
| `remotion.json` | Optional style that `yt-remotion` passes as the `style` prop to the generic compositions (`LowerThird`, `ChapterCard`, `ColdOpenTitle`, `IntroSting`, `EndPlate`, `ShortCaptions`, `ThumbnailStill`): fonts (files relative to the brand folder), logo, motif, signature, prefixes, case, accent placement. A `style` object in the props file is merged over it. Keys: `yt-remotion --help` and `scripts/yt/remotion/README.md`. Without it the compositions use `tokens.json` alone | `yt-remotion` |

**Rules for any brand.**
- Tokens come from the owner's source (brand kit, public CSS, design system), never picked by eye. Compute the contrast whitelist with the §9 procedure and write it into the profile's `brand` block.
- The profile's `brand`, `thumbnails` and `copy_rules` bind. One accent per composition unless the brand says otherwise. The v2 rules on hooks (§5.3), faces (§10.1, §12.4) and guest pixels (§11) apply to every channel.
- Override templates follow the §7.3 geometry (1280×720 CSS basis rendered ×3), keep text out of the no-go zones and load their fonts, so the §12 pre-checks run. Start from a copy of the built-in template you want to change (in the plugin's `scripts/yt/node/templates/`) into `<brands_dir>/<slug>/templates/<slug>-<name>.html`; never save the copy inside the plugin.
- A lever with no template in the brand is not improvised: use the built-in template with the brand's tokens, or `generic`, and say so in the G2 brief.
- Remotion only for own and personal brands (licence in design §11): a channel whose profile says `kind: own` or `personal` with `graphics_licence.status` confirmed, or a brand whose tokens say `"own": true`. `yt-remotion` warns on any other brand; client brands render with `--engine html` or HyperFrames.
- `owner_ai_edits: true` in a personal profile lets the channel owner consent to AI edits of **their own** face only (§17).
- `/youtube:setup onboard` creates the brand folder in the first `brands_dirs` entry. `yt-config --get brands` shows whether the toolkit sees it and which folder wins. Backing up the folder is the operator's job.

## 9. Generic template (`generic`)

- **Tokens**: take exact HEX and font families from the brand kit, CSS `:root` or style guide; if missing, ask. Never infer colours by eye (inferred palettes get rejected). Save them in `<brands_dir>/<slug>/tokens.json` (§8) and record them in the channel profile's brand block (`<slug>.md` in the operator's `channels_dirs`); the concept's `tokens` field or `--tokens` passes them to the template. Without a brand, `generic` renders with `demo`.
- **Whitelist procedure**: compute WCAG ratios for every token pair (same method as §7.1); allow a pair for hook text only at ≥4.5:1; allow 3:1–4.5:1 only as a highlight box behind display text with cap height ≥120 px; reject any hook pair whose Rec.601 grey values differ by <60 levels even if the ratio passes. Write the resulting table into the G2 brief.
- **Engine**: `yt-thumb-render --engine html` (Playwright, Apache-2.0). A client receives PNG/JPEG; if they want the editable template, they receive the HTML file, never a Remotion project (design §11: a client who receives the project counts toward Remotion's headcount).
- **Layouts**: one file, `generic`, driven by the concept: claim (default), proof (add `artifact`), duo/name (add two `people`) — same geometry as §7.3 with the brand's fonts; same no-go zones; same rubric.
- **Consent and approval (clients)**: the client is the data controller for its guests; the operator processes on its behalf (11-compliance-safety.md §6). G2 includes the client's sign-off; the operator forwards it. `guest_style: graphic` on a client's guest needs the client's written OK.

---

## 10. Frame selection

### 10.1 Source priority and the upscale cap (v2)

| Priority | Source | When usable as hero face |
|---|---|---|
| 1 | **Tight fixed camera ISO** on the guest (and one per host when available), 4K, kept by the crew (§10.6) | Always (preferred): the face is 35–45 % of the 4K frame (760–970 px), so a 40–45 % face in the thumbnail is a 0.4–1.0× resize, never an enlargement |
| 2 | Main camera ISO frames (Mode I) | When the face is ≥ half the target face height in pixels |
| 3 | Composited master frames (Mode M) | Within the cap below. Prefer the **inset** over the wide shot: the wide shot is a zoom already upscaled in the edit (effective face ≈ 97 px) while the inset is ≈ 131–152 px effective. `yt-portrait scan` ranks with the effective resolution |
| 4 | Guest-supplied photos (press portraits) | With written permission; same cap; no AI upscaling; declared at G2 (not the episode moment) |

No photo session (§0.1): directed stills are not part of the process.

**Upscale cap (option c, §0.1).** The face height in the **1280×720 output** is at most **2.0× the effective face resolution** of its source (`eff_face_px`, measured by `yt-portrait scan`/`cut`: the face size at which the source's real detail lives). Interpolation only (spline36/Lanczos), plus the logged luma-only unsharp of `yt-portrait`. Example, a test frame from a composited inset: effective 152 px → at most 304 px at 1280 = **42 %** of the height (912 px at 4K); the older 2.0×-on-the-4K-master rule gave 23.5 %. Wide-shot frames (effective ~97 px) reach ~27 % at most: a claim template needs an inset frame or the tight camera.
- In the file YouTube serves on the web (720×405) the same 42 % face is ~1.1× its effective resolution (§2): the cap holds there by construction.
- **Fallback (option b)**: `yt-portrait cut --display-cap b` = 1.5× (≈ 32 % on the same frame; the default `c` = 2.0×, `legacy` = the old 2.0× on the source box) and `yt-thumb-render --display-cap 1.5` (or the concept's `display_cap`). Use it when the operator or the brand judge sees softness at 1280, or when apps + TV carry a large share of the channel's impressions (unknown until §15.0 is done; the threshold is the operator's call).
- `yt-portrait cut` refuses more without `--over-cap-reason`; `yt-thumb-render` fails the render without `upscale_override` (a written reason, G2 only).
- **Served-size detail check** (§12.4): variance of the Laplacian on the face box in the render downscaled to 720×405 (Lanczos), without rescaling the face: warning < **713** (p25 of the 66 English references), error < **569** (p10). On the test episode a 23.5 % face measured 1,211–1,233: sharp per pixel but small; a 32.5 % face cut at 2.8× on the master box measured 271, softer than every reference.
- Generative upscalers (Topaz "Redefine", creativity >1, GAN or diffusion super-resolution, AI face restore) are forbidden on every person (§11.2, level 5). Learned non-generative super-resolution is level 4: not used.
- If no source satisfies the cap at the face floor (§12.4), the G2 brief says so and asks the crew for the tight camera at the next recording; it does not ship a soft face.

### 10.2 Candidate extraction: expression classes (v2)

**Default: `yt-portrait scan WORKDIR`** (on the master), and since v2 `yt-portrait scan WORKDIR --src <tight-cam ISO> --layout full` first when the file exists. One VideoToolbox pass takes frames n and n+1 every 0.5 s, crops the person (inset, wide seat, or the full frame of an ISO), scores with thumbvision, measures motion blur inside the face box, drops corrupt spans (±2 s), rejects (face on the crop edge, eyes < 0.75 of the person's p80, motion > 1.5× p40, sharpness < 0.8× median, quality < median), ranks, keeps the best per 3 s and writes contact sheets. On a 53-min 4K test master: 6,346 pairs, 6,241 with a face, 1,400 survivors, 12 frontal (|yaw| ≤ 15°) in the top 20; 223 s decode + 167 s scoring.

**Expression classes (v2).** Ranking only by "mouth open" collected mid-word frames and missed the one genuine frontal smile of the test episode. The scan now gives every survivor a fit per class, per person and per episode (robust z-scores), and fills one row per class:

| Class (`expression_class`) | Signals: Apple Vision geometry (phase A, no install) | + MediaPipe blendshapes (phase B, after `install.sh --with-mediapipe`) |
|---|---|---|
| `sorriso` | mouth-corner lift ÷ interocular distance, mouth width | `mouthSmileL/R`; Duchenne = smile × `cheekSquintL/R` (AU12 + AU6) |
| `risata` | smile with the mouth open | smile + teeth (`mouthUpperUpL/R`) + `jawOpen` |
| `intenso` | mouth closed, eyes open, no smile, no pressed lips | low `jawOpen`; gaze to camera = 1 − mean of the eight `eyeLook*` |
| `sorpresa` | brow–eye distance up, eyes open | max(`browInnerUp`, `browOuterUpL/R`), eyes open |
| `neutro` | no strong signal | no strong signal |
| `scettico` | pressed lips, asymmetric grimace | `mouthPressL/R`, `mouthRoll*`, asymmetry |

- **Mid-word frames** (the person is pronouncing a word per the transcript timings, with the mouth open and no smile, or high `mouthFunnel`/`mouthPucker`) leave the class rows; a smile while talking stays.
- Signals use the median over n, n+1 and the ±0.5 s neighbours (blendshape jitter on 250-px faces is not documented). Half blinks: `eyeBlinkL/R` with a threshold calibrated per channel (§10.4).
- **Ranking** (initial weights, calibrated on 10 labelled frames, §10.4): `0.20 quality + 0.20 sharpness + 0.10 stillness + 0.15 frontality + 0.10 eyes + 0.10 face height + 0.15 expression fit`, then combined with the effective resolution. Penalties: −0.15 mid-word (high `jawOpen` with low smile, or `mouthFunnel`/`mouthPucker`); −0.10 pressed lips + asymmetric brow unless the hook is "contro".
- `scan_expr.jpg` becomes one row per class with its top 3 frames. When a class has no frontal frame, the scan says «non trovato» instead of padding: the brief then names the class as missing (and the tight camera as the fix).
- MediaPipe Face Landmarker runs locally in the plugin venv (`install.sh --with-mediapipe`, an optional extra): it analyses frames, it never changes pixels and never identifies anyone (11-compliance-safety.md §6.2).
- The manual procedure below stays for single moments (a duo, a reaction) and when `yt-portrait` is unavailable:
  1. **Transcript-driven** (one per concept): for the line at time `t` (source timeline), sample ±2 s at ~5 fps: `yt-frames <workdir> --every 0.2 --from <t−2> --to <t+2> --out <workdir>/thumbs/frames --size full` (if `--every` accepts only integers, pass the 21 timestamps with `--times`).
  2. **Global sweep**: reuse `analysis/frames/` from `yt-ingest`, plus `yt-frames <workdir> --every 2 --from <a> --to <b> --size 1080` on the 2–3 liveliest chapters.
  3. For the duo, extract host and guest separately (different moments of the same episode are allowed, §10.5).

### 10.3 Scoring with `thumbvision` (manual path)

`thumbvision score <workdir>/thumbs/frames/*.jpg > <workdir>/thumbs/frames/scores.json` (agent-side redirect; the CLI prints JSON).

**Hard rejects** (any one drops the frame):

| Check | Threshold (provisional until calibrated) |
|---|---|
| Lever needs a face, none found | `faces == []` |
| Blink | `eyes_open` z-score < −1.0 within this person's frames in this episode, or < 0.25 absolute when fewer than 30 frames exist |
| Mid-word grimace | `mouth_open` in the person's top 20% **and** the claim isn't a laugh/shout moment |
| Soft frame | `sharpness` below the episode's 25th percentile |
| Resolution | the target face would exceed the cap of §10.1 |
| Cropped or occluded | face box touches the inset/window edge, the PiP covers it, or a mic covers >15% of the face (visual check) |

**Rank** the survivors per person (0–1): `rank = 0.35·q + 0.25·s + 0.20·h + 0.20·e`, where `q` = percentile of `quality` within the person, `s` = percentile of face-box height, `h` = percentile of `sharpness`, `e` = expression fit for the concept's class (§5.5): 0, 0.5 or 1. Then a contact sheet of the top 6 per concept, pick 1–2 by eye, write the path into `people[].frame` (or cut it and write `people[].cutout`).

### 10.4 Calibration and hypotheses

- First 3 episodes of a channel (and the first episode with a tight camera): the operator marks 10 frames per episode as good/bad and assigns their class in the G2 brief; the agent sets per-channel cut-offs (`eyes_open`, `mouth_open`, blink and smile thresholds) from those labels and stores them in MEMORY.md ("thumbvision calibration").
- `quality` is relative (Apple faceCaptureQuality is not calibrated across people): never compare it across two different persons.
- Hypotheses to pre-test, never stated as rules: closed vs open mouth ([anecdotal] Appleby); eye contact vs looking at the artifact ([study] Eden eye-contact edge); `intenso` vs `sorriso`.

### 10.5 Truthfulness of composition

- Duo: both people must actually be in the conversation; frames may come from different moments of the **same** episode (the tight cameras of the same recording count); the host's reaction must match the host's real stance in that episode; never pair an expression with a "VS" or question that implies a conflict that didn't happen.
- Duo hooks in the plural («ABBIAMO DECISO DI VENDERE») are read as the two people on screen (first cold reads): name the host with the small host tag (`host_tag`, «con <host>») and make sure the guest's name plate carries the subject; if the plural still reads as «the two of them», rewrite the hook in the first person singular or use `ritratto`.
- Claim: the face shown must belong to the person who said the line; a face from another moment of the same episode is declared in the G2 brief.
- No frame from another episode, no stock person, no generated person, ever. A seasonal host library is not used (§0.1).

### 10.6 Tight fixed camera on the guest (v2)

The source fix is a camera, not a photo session. The crew brief (Italian, one page) is `docs/yt/templates/brief-camera-stretta.md`; `youtube:story --mode=prep` attaches it to the recording checklist, and `docs/yt/templates/messaggio-ospite.md` is the guest's pre-recording note.

| What | Spec | Why |
|---|---|---|
| Framing | head and shoulders with headroom (≥ 10 % air above the hair), shoulders and the mic in frame, face box 35–45 % of the frame height | 40–45 % thumbnail faces without enlargement; no straight crop edge on the head |
| Lens and distance | ~85–110 mm equivalent at ~2 m (phone: 4×/5× telephoto, never the 1× close up) | No perspective distortion; gaze near the lens |
| Recording | 4K UHD 3840×2160, same frame rate as the main cameras (25 or 30p), SDR Rec.709 (no log/HDR), highest-quality codec, the **original ISO file kept** | `yt-portrait` reads SDR BT.709; the ISO is the only file with real detail |
| Shutter | 1/100 s (flicker-safe on 50 Hz mains); 1/200 s only if a 10-s test shows no banding | ~2× less motion blur than the cinematic 1/50–1/60 |
| Light | soft key 30–45° to the side and slightly above the eyes, fill one stop under, optional hair/rim light; background ≥ 1.5 m behind and ≥ 1 stop darker; no coloured wall right behind the head | Real light is photography (level 2bis): separation without touching pixels; no coloured spill on hair |
| Placement | beside the host who asks the questions (guest yaw ≈ 10–25°); one per host when there are cameras to spare | Frontal-ish expressions; host reactions from the same recording |
| Sync | clap or slate at the start; the host marks 3–5 "thumbnail moments" | Fast `scan --from/--to` |

Ingest: the file goes (as a symlink) into `<workdir>/src/iso/`, is listed in `project.json` `sources` with `role: camera`, and is scanned with `yt-portrait scan <wd> --src <file> --layout full`. Its timeline is not the master's: `payoff_at` stays on the master; the cutout sidecar records the ISO time.

---

## 11. Cutouts and the guest-pixel policy

### 11.1 Cutout operations

| Rule | Detail |
|---|---|
| Default | `yt-portrait cut <workdir> --t <s> --roi inset\|wide-left\|wide-center\|wide-right\|full [--src FILE] --name <n>`: exact 16-bit frame (zscale BT.709), face from thumbvision, BiRefNet-portrait matte on the upper body + a head tile at ~1:1, only components touching the face, PiP excluded; foreground colour by pymatting ML, warm-spill clamp (R−B of the edge band ≤ interior) and halo clamp (edge-band luma within ±6/255 of the interior); premultiplied spline36 16-bit resize to the final face size + luma-only unsharp (σ 0.7, 0.6); alpha levels 0.1–0.95. Output is drawn **1:1** by the series templates (no second resample in Chrome). Study x4: face Laplacian 5.4 → 15.1 at the same 538-px face; test finals: 12.3–16.2 → 49–51 at a common 400-px face |
| Vision cutout (fallback, and for separating overlapping people) | `thumbvision cutout <frame> --out … --mode person --matte accurate --decontam 4` — **no `--choke`**: choke 2 pulled the edge 2 px inside the person and shaved hair and ears (x4) |
| Props mode | `--mode subject` keeps mics, headphones, mugs (the v2 frame wants the mic) but can keep desk items; inspect |
| Matte holes | Glasses lenses and gaps inside the face box must be opaque (α ≥ 0.9): a test cutout lost a lens against a coloured wall. Since 2026-10-12 `yt-portrait cut` fills, without a model, every hole (α < 0.5 enclosed by the silhouette, plus its 2-px soft rim) whose centre lies in the eye band of the face box (x 8–92 %, y 12–70 %), is ≤ 8 % of the box and whose **source colour is closer to the face than to the background just outside the silhouette**: α = 1 and the frame's own pixels (glass in front of the eye: level 0). A lens seen against the wall (profile) stays transparent — the new background is what sits behind the glass. `--keep-holes` disables the fill; the sidecar records `matte_holes_filled`. The render check counts only enclosed holes (the soft outer rim of hair and cheeks is not a hole): a hole left in the face box is a warning with `guest_style: none` (the plate shows through) and an error with `graphic` (the outline would show through) |
| Edge QA | View each cutout at 100% on paper and on ink: halo, missing hair, chopped mic or headphones, a second person's shoulder, gradient from a composited canvas left in the matte |
| **Crop edges (hard rule, S1)** | A cutout taken from a crop (a composited inset, a ROI, the frame border, a PiP exclusion) has straight edges wherever the person was cut by that crop: top of the head, a hand, an elbow. Every such edge must sit **flush with the canvas edge** (placed at or beyond it), or the part must be trimmed at a canvas edge, or another frame must be chosen. A straight cut edge visible inside the composition is never acceptable. Found in an early delivery (2026-10-11): hand cut vertically mid-canvas, hair cut flat 10–150 px below the top edge [locale]. **Automatic since 2026-10-12**: the series templates push declared straight edges flush (placement helper in `_common.js`, ≤14% shift); `yt-thumb-render` then finds straight, hard, axis-aligned runs at the extreme of the alpha contour (a run that touches the PNG border, or ends in a sharp corner, or is ≥30% of the face height — the convex apex of a head is flat only for ~2√(2R) px and has no corner), maps them into the canvas and fails the render when one lies inside and shows a colour step > 10 levels across the line on the rendered PNG. Validated on the early renders: catches the cut hand and the flat hair, passes the fixed finals and every later render. Still look at `<stem>_100.png` (yt-thumb-qa) |
| Matte engine | rembg (an optional extra of `install.sh`, installed only with the operator's approval), **only** `birefnet-portrait`, called by `yt-portrait` through `lib/portrait_matte.py`; never the default `bria-rmbg` (commercial licence required), never cloud backends (`withoutbg`, `atlascloud`), never `MODEL_CHECKSUM_DISABLED`, never an automatic download. HyperFrames `remove-background` is not installed (would need new downloads) |
| Fringe QA | `yt-thumb-render` measures on every cutout `fringe_rb` (R−B of the soft band minus the interior, ×255) and `rim_luma`: warning > 12, error > 25. Raw edges score 30–44, Vision decontam 11–14 (the 2026-10-11 finals), yt-portrait 1–7 |
| Preservation proof | `yt-portrait cut` writes `<name>_proof.jpg`: the original frame resampled with plain spline36 next to the final cutout at the same scale, with the mean/p99 difference on opaque face pixels (test frame: 0.21 / 2.5 levels, all from the luma unsharp). Any visible difference inside the face beyond that = hard fail |

### 11.2 Policy ladder v2 (with level 2b)

Applies to every person in a thumbnail (guests, hosts, clients' guests). `guest_style` in `concepts.json` declares the level a concept uses for graphics and colour tone; `grade` declares the monochrome look (level 2b) independently. The channel profile sets the defaults (template default: `guest_style: none` on every template, `grade: natural`, mono as an option).

| Level | What happens to the person's pixels | Examples | Status | Automatic check |
|---|---|---|---|---|
| 0 | Geometry and minimal tone: crop, uniform scale within the cap (§10.1), position, matte (feather ≤ 2 px), colour decontamination of the soft edge band only (α < 1), one global exposure/white-balance match ≤ ⅓ stop on the whole cutout, the logged luma unsharp (σ 0.7 × 0.6), soft neutral drop shadow | today's pipeline | **Allowed** (`none` and `graphic`) | proof sheet; fringe; crop edges; matte holes |
| — | **Background, not the person**: field, accent circle or quarter ring behind, the darkened/desaturated/blurred copy of the episode's own scene (pop-out), bokeh and grade of the plate | `scena`, the §7.7 circle | **Allowed** (`none` and `graphic`): these never touch the person's pixels or silhouette | accent count; face–surround ΔL* |
| 1 | **Graphics hugging the person, face untouched**: outline ("sticker" stroke) and glow **under** the cutout | outline and glow helpers of `_common.js` | **Allowed only with `guest_style: graphic`**; never a default (0 of 66 English references use an outline; 22 of 125 references, all Italian, do) | `face_pixels_unchanged` = 0 (no opaque face pixel differs from level 0); one accent (the glow counts); silhouette ΔL* at 246 px (warning < 25 until calibrated on references) |
| 2 | **One global, uniform tone curve** on the whole cutout: curve, contrast, the brand look LUT (`look-33.cube` in the brand folder, otherwise computed from the brand's tokens: blacks toward ink, highlights toward paper) — **no saturation boost**, no masks, no local edits | brand look | **Allowed only with `guest_style: graphic`**, logged in the sidecar | alpha and geometry identical to level 0 (no pixel moves); skin ΔE00 vs level 0: **mean ≤ 2.5 and p95 ≤ 5**, else error |
| 2b | **Uniform monochrome grade**: one desaturation + contrast curve (`mono-curve.json` in the brand folder, `assets/brands/demo/` by default: Rec.709 luma → monotone curve → ink-to-paper ramp, no colour left) applied **identically to every pixel of every person and of the plate**; the plate may additionally be darkened, blurred and vignetted (background operations). No masks, no local edits on faces, no vignette or grain over the people; alpha and geometry identical to level 0; identity and expression intact; one accent colour, in the graphics only | the editorial duo look | **Allowed** with `grade: mono` (with `guest_style: none` or `graphic`); an option on every template, a default only if the profile says so | **The skin ΔE00 check does not apply** (skin turns grey by definition) and is replaced by: (a) **one curve on all person pixels** — render: every person and the plate carry the same curve signature, the mapping is within 2 8-bit levels of the analytic curve, the measured curves of the people agree; QA (`yt-thumb-qa`, curve-agnostic): the curve L\*(render) = f(luma of the level-0 cutout) fitted on all opaque person pixels together, residual p95 (warning > 2.5, error > 5 ΔL\*), gap between the people's curves and between each face and the rest of its person (warning > 1, error > 2 ΔL\*), every face within p95 2.5 / 5 ΔL\* of the common curve (`grade_face`), people C\*ab p95 ≤ 12 (`grade_mono`; plate over 12 is a warning); (b) **landmarks unchanged** — MediaPipe's 478 landmarks on the level-0 cutout and on the render, mean shift ÷ outer-eye-corner distance: warning > 2 % (passes when the curve alone, grey → render, stays ≤ 2 %: colour removal alone moves the detector by up to ~2 %), error > 4 % (`grade_landmarks`). Calibration on test cutouts: a clean render 0.2 ΔL\* residual and 0.9–1.4 % landmark shift; a +10 % face dodge, a −¼ EV curve on one person, a 6 % mouth warp all fail |
| 2bis | **Real light on the set**: key, fill, hair/rim, a brand-colour gel | crew brief §10.6 | **Allowed**: it is photography, not an edit | — |
| 3 | Simulated light on a person: painted rim on hair/shoulders, dodge & burn, adaptive "subject" presets | Resolve Relight, Adobe adaptive presets | **Not used** (possible later: hosts, or guests with a written OK, after a test) | — (render error if declared) |
| 4 | Learned non-generative super-resolution | Apple VT SR, Pixelmator ML SR | **Not used** (test only, outside the pipeline) | — (render error if declared) |
| 5 | **Generative**: diffusion relight, face restore, GAN/diffusion upscaling, expression/eye/mouth edits, retouching, skin smoothing, teeth/eye whitening, reshaping, face swap, generative fill or outpaint touching the person | IC-Light, CodeFormer, Topaz Redefine, thumbnail generators with "likeness" | **Forbidden**, always | hard fail |

Also forbidden at every level: **mirror flip** (it changes the person's face and the scene's truth), temporal denoise on the face (x4: −7/13 % noise for −2/5 % detail), any treatment of a face whose owner asked not to be stylised.

What the guest is told: the pre-recording note (`docs/yt/templates/messaggio-ospite.md`) says that frames of the video become the cover with cut-out, background and graphics around the figure, and no retouching of the face; when the channel uses the mono look the cover may be in black and white (one uniform grade on the whole photo). A guest who asks for no graphics gets `guest_style: none`; a guest who asks to stay in colour gets `grade: natural`.

---

## 12. Render

1. Write the template data file and run:
   `yt-thumb-render --template auto --data <workdir>/thumbs/concepts.json --out <workdir>/thumbs/renders --engine html --debug`
   (`auto` = each concept's `template`; `--engine remotion` only for own and personal channels within the licence, see §0; clients always `html`.)
2. **Naming**: `<slug>_<id><n>.png` — letters are bets (hypotheses), numbers are dressings (hook candidate, accent, frame). Example: `ep12-sara_A1.png` (claim, hook 1), `ep12-sara_A2.png` (claim, hook 2), `ep12-sara_B1.png` (proof).
3. **Variants per episode**: 3 concepts × 2 hook candidates = 6 renders; up to 12 with one alternative accent, expression class or frame per concept. Never more than 12 before G2.
4. **Pre-checks v2, «§12.4»** (`yt-thumb-render` writes them to the sidecar; the command exits ≠ 0 when any **error** is present — before v2 the exit code only said whether a PNG was produced):

| Check | Error | Warning | Notes |
|---|---|---|---|
| No-go zones | any text, face, logo, label or template graphic in bottom-right 230×110 or top-right 120×80 | non-critical decoration touching a zone | a mic or shoulder may cross bottom-right |
| Hook length and form | < 3 words; a noun fragment without verb or number + unit (heuristic, confirmed by the judge); > 3 lines; **`duo` > 4 words** (override only with `hook_size_reason`) | > 6 words | P4, §5.3; QA `hook_words` |
| Line height | any hook line < 12 % of the canvas height (cap < 86 px at 720); a keyword set larger than the phrase < 18 %; **`duo`: any line < 20 %** (override only with `hook_size_reason` at G2) | keyword < 18 % in a one-size headline (v2 templates: the keyword is an inline box in its line, same body as the phrase); `duo` line < 22 % | measured on the rendered glyph rows (study §10.4: p10 of the largest EN line is 12.8 %); `yt-thumb-render` and `yt-thumb-qa` apply the same rule to the same numbers (`metrics.texts[].rows`). The row height is the capitals' height **without diacritics**: the accent of È, Ì, À sits above the cap and does not make the line bigger (test render: «È ANDATA / BENE COSÌ.» measured 24 % with the accents, 19 % on the capitals) |
| Text vs faces | any text box intersects a face box | — | |
| Colour pairs | a pair outside the whitelist; paper text on a photo < 4.5:1 measured on the PNG | — | §7.2 |
| Crop edges | a straight crop edge visible inside the canvas | — | §11.1 |
| Upscale cap | face > 2.0× effective at 1280 (or > 1.5× with the option-b flag) without `upscale_override` | — | §10.1 |
| Served-size detail | face Laplacian in the render at 720×405 < 569 without `detail_reason` | < 713 | §10.1 |
| Face size, claim templates | largest face < 35 % of the height without `face_floor_reason` (< 40 % when the source is a still photo: no resolution excuse) | < 40 % | `duo`, `ritratto`, `scena`, `prova` with a face, and a brand's claim templates; Vision box height (brows to chin) |
| Faces in a duo | either face < 30 %, or guest face < host face | — | |
| Face–surround ΔL* | < 10 | < 20 | ΔL* between the face and two background bands beside the head, text excluded. Calibrated on references: Lenny and 20VC sit below 20 on 4/10. When the surround straddles the face tone (≥ 20 % of its pixels lighter by ≥ 10 and ≥ 20 % darker by ≥ 10, e.g. a light accent circle above and a dark plate below, with the person's own pixels excluded), the median of the two bands lands on the face tone and says «no separation» although the face separates from both: there the value is the per-pixel median of \|ΔL*\| (`yt-thumb-qa` and `yt-thumb-render` agree; on a test duo: 0.8 → 33). Otherwise R3 is unchanged |
| Accent circle ↔ hair/face | ΔL\* < 10 between the circle and the person pixels next to it in the head zone | < 20 | QA `circle_contrast` (pairs 2–5 px outside / inside the silhouette at 1280, median), with the ΔL\* the other accents would give; render: the disc's `dL_edge` |
| Dark-feed separation | — | tile edge ΔL\* vs #0f0f0f < 25 without a light frame element (a contiguous run of the edge ≥ 40 ΔL\* from the page for ≥ 10 % of the perimeter); vs #ffffff < 20 | QA `edge_dL_dark` / `edge_dL_light` on the 360 tile of the served file. Measured on test renders: a circle on the edge passes (run 20 %); first-generation `ritratto` 13.5 and `scena` 14.1 (warn), `duo` 34.3 (a light shirt on the host) |
| Guest pixels | `face_pixels_unchanged` ≠ 0 at levels 0–1; skin ΔE00 over mean 2.5 / p95 5 at level 2 (**skipped only with `grade: mono`**); level ≥ 3 declared; `guest_style` or `grade` not allowed by the profile | — | §11.2 |
| Level 2b (`grade: mono`) | render: people or plate with a different curve signature, mapping > 2 levels from the curve, measured curves of two people apart > 2 levels, landmarks shifted > 4 %; QA: single-curve residual p95 > 5 or a curve gap > 2 ΔL\* (`grade_uniform`), a face > 5 ΔL\* from the common curve (`grade_face`), people C\*ab p95 > 12 (`grade_mono`), landmarks > 4 % (`grade_landmarks`), level-0 cutout missing from the sidecar | residual > 2.5, gap > 1, face > 2.5; plate C\*ab > 12; landmarks > 2 % with the curve alone > 2 %; MediaPipe missing | §11.2; replaces the skin ΔE00 check for 2b only |
| Matte holes | α < 0.9 inside the face box | — | §11.1 |
| Accent | more than one accent colour (glow, circle, keyword box and full stop count) | — | §7.2 |
| Logo | symbol < 140 px at 4K | — | |
| Fonts | not loaded (`document.fonts.check` / Remotion assertion) | — | fonts fail silently otherwise |
| Silhouette contrast at 246 px | — | < 25 with `guest_style: graphic` | warning until calibrated on references (study §10.4) |
| Fringe | `fringe_rb` > 25 | > 12 | §11.1 |
| Saliency | — | — | **info only**: Apple Vision attention saliency names the element noticed first (face or hook); not validated on thumbnails |

5. Outputs: PNG master 3840×2160 + JPEG <2 MB. Never upload or keep a variant below 1280×720 (A/B downscale trap).

---

## 13. QA sheet, grid mock and cold reader

### 13.1 Legibility sheet (`yt-thumb-qa`)

`yt-thumb-qa <workdir>/thumbs/renders/*.png --out <workdir>/thumbs/qa --grid <dir-of-competitor-thumbs>`

The agent reads (Claude vision) one sheet per render, `<stem>_qa.png`. v2 derives every tile ≤ 720 from the **served file** (render → 720×405 Lanczos → tile), not from the master:

| Row | Tiles | Simulates | What to look for |
|---|---|---|---|
| 1, dark page #0f0f0f with the duration badge | 720×405 (`hq720`, grid and search at 2×) · 500 (search) · 360 (`hq720` at 1×) · **216** (the real sidebar, vendored `surfaces.json`, CC BY 4.0) · 168 (**stress test**: the declared file size, not a painted tile) | desktop surfaces, dark | glance, keyword dominance, badge collisions; the series frame recognisable at 360 |
| 2, light page #ffffff | 216 and 168 light · 360 light · grayscale · blurred | sidebar on white; value contrast (P7); squint | **every hook word readable at 216 on light** (and at 168 as the stress test); text and face separate without colour; one dominant mass |
| 3, served chain | the 720×405 file → 1180×664 (a phone: 393 CSS px × 3), with the faces of both and the check panel (face, detail, separation, lines, saliency) | phone and Retina enlargement of the served file | the face does not turn soft next to its own metrics |

The JSON `checks` (levels error / warn / pass / info / skip) use the §12.4 thresholds: `face_size`, `face_surround`, `phrase_line_h`, `keyword_line_h` (`duo`: 20 % on every line), `hook_words` (3–6; `duo` 3–4), `served_detail`, `silhouette_246` (warning only), `saliency_first` (info), `edge_dL_dark` (warning < 25 unless a light frame element runs ≥ 10 % of the perimeter) / `edge_dL_light` (warning < 20) and `text_contrast_168` (warnings), `circle_contrast`, the level-2b checks `grade_uniform`, `grade_face`, `grade_mono`, `grade_landmarks` (only with `grade: mono`; `--no-landmarks` skips MediaPipe), `skin_de00` (level 2; `skip` with mono), `display_upscale`, `render_checks` (the errors of the render sidecar). On renders with a sidecar the errors make the command exit ≠ 0; on other images (channel audits, competitors) they drop to warnings. It also reports `edge_density_360/168`, `busy_cells_share`, `timestamp_zone_edge_density`, `colorfulness_360` (podcast references ≈ 65) and `<stem>_100.png` (faces and in-canvas crop edges at 100% of the master). `edge_dL_dark` is a **warning, never an error**: DOAC (11.8), MFM (9.1) and Huberman (11.0) sit far below; the house bar is 25 (the judges' top fix on the first renders: dark plates merged with the dark feed), met by a lighter edge or by a deliberate light frame element (`edge_light_run` in the metrics). Check names follow `yt-thumb-qa --help`; a metric missing from an older toolkit is written «non misurato» in `qa/report.md`, never guessed. Metrics flag; the agent decides by looking.

### 13.2 Grid mock

- As implemented (`yt-thumb-qa --grid DIR`): `<stem>_grid.png`, a 3×3 grid of 347×195 tiles with title bars (the real title with `--title`; the neighbours get neutral bars), channel name (`--channel-name`) and duration badge, dark and light themes side by side. `--pos 0–8` places the candidate (default 4, centre; use a random slot via `--seed` to avoid centre bias).
- The candidate sits among 8 thumbnails (fewer are repeated, with a warning; the tool reads only images placed directly in `DIR`) from the same topic search and adjacent Italian podcasts (`https://i.ytimg.com/vi/<id>/mqdefault.jpg`; IDs from the Data API or `yt-research meta`). They stay private, are never published, and are deleted with the workdir research cache within 30 days (11-compliance-safety.md §3).
- Judge prompts (answer in the rubric note): "Which tile do you notice first, dark and light?" · "In one second, what does our video promise?" · "Is ours the most camouflaged tile in either theme?"

### 13.3 Cold reader (v2)

A cheap, read-only sub-agent (`agents/thumb-cold-reader.md`, `subagent_type: "youtube:thumb-cold-reader"`) that has never seen the episode. Per concept, the agent gives it **only two files**: the 168-px tile and the 720-px file (the size YouTube serves). Never `concepts.json`, the title, the transcript, the rubric or other concepts. It answers in one line what the video promises and who it is for, then what it noticed first and what is unclear.

1. Tiles (FF = ffmpeg-full by absolute path, `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`):
   `$FF -v error -y -i <render>.png -vf "scale=168:94:flags=lanczos" <wd>/thumbs/cold/<id>_168.png`
   `$FF -v error -y -i <render>.png -vf "scale=720:405:flags=lanczos" -q:v 3 <wd>/thumbs/cold/<id>_720.jpg`
2. One fresh cold reader per concept (independent reads), in random order.
3. The agent compares the read with the concept's `hypothesis`, written before: **2** = right promise and right audience; **1** = right promise, vague or wrong audience; **0** = wrong promise or "non capisco". Results go to `thumbs/cold/cold_reads.json` and the G2 brief.
4. **Gate**: at least 2 concepts out of 3 score 2. A concept at 0 gets one rewrite (hook or expression class) and one re-read; if it still fails it is dropped or flagged at G2. The cold reader is a `[giudizio LLM]`: it informs, the pre-test and the operator decide.

Where it runs: in Phase 1 on a quick sketch render of each concept (before G1), and again on the finalists before G2 (`commands/thumbnail.md`).

---

## 14. Rubric (LLM-as-judge, then the operator at G2)

Score each item 0–2. **Ship = total ≥15/20, no 0 on items 1, 2, 6, 9 (zero-tolerance), and no hard fail.**

| # | Item | 2 | 1 | 0 |
|---|---|---|---|---|
| 1 ZT | Glance (168 and 246 tiles) | Subject and hook identified in ~1 s at 168, dark and light; cold reader scored 2 | Only at 246, or only one of the two at 168; cold reader 1 | Needs 360+ to understand; cold reader 0 |
| 2 ZT | Hook legibility | Every word readable at 216 and at 168 on light; the keyword is the dominant text mass; hook 3–6 words, a complete statement | All readable at 246 dark, one word marginal at 168 light, or the keyword doesn't dominate | Any word unreadable at 246, or a fragment |
| 3 | Value contrast (grayscale) | Text and face clearly separate from the field; face–surround ΔL* ≥ 20 | One of them partly merges (ΔL* 10–20) | Text or face merges |
| 4 | Squint (blur) | One dominant mass, one focal point | Two competing masses | No focal point |
| 5 | Face quality | Face ≥ 35 % (target 40–50 %), eyes open, expression class fits the lever (§5.5), served-size detail ≥ 713, no mid-word mouth | Acceptable but class off, detail 569–713, or face 30–35 % with a written reason | Blink, grimace, motion blur, over the cap, detail < 569 |
| 6 ZT | Title pairing | No shared stem/number and the pair opens one gap | No shared stem but the pair says the same thing twice | Shared content stem/number (without written override) or contradiction |
| 7 | Brand frame | The channel's series frame recognisable at 360 and in the grid in both themes (the wordmark readable at 360); credential present on claims; one accent; whitelist pairs | Recognisable in one theme only, or credential missing | Off-palette or unrecognisable |
| 8 | Feed pop (grid mock) | Among the first two tiles noticed in both themes | First two in one theme only | Most camouflaged tile in either theme |
| 9 ZT | Truthfulness | Verbatim claim with timestamp, payoff inside the cold open (0–30 s), numbers verified, meta line verified, person pixels within the declared `guest_style` level and `grade` (2b: one curve, landmarks unchanged) | Faithful compression (not verbatim) with timestamp; everything else as for 2 | Anything invented, unverified, paid off after 30 s, or pixels beyond the declared level |
| 10 | Safe zones | Nothing in the two no-go zones; margins respected; no clipping | Non-critical decoration touches a zone | Text or face in a zone, or clipping |

Without a face (text + artifact thumbnails), item 5 scores the artifact's clarity with the same anchors.

**Hard fails** (reject before scoring): forbidden token pair · person pixels beyond the declared level or any level 3–5 operation (§11.2) · text generated by an image model · hook < 3 words or a noun fragment · number not verified · `payoff_at` outside the cold-open segments · render below 1280×720 · a person generated or taken from another episode.

Recommendation at G2: the arm with the highest rubric total goes first (it becomes the default if the test is inconclusive); arms below 15 never enter a test.

---

## 15. Testing: traffic first, pre-test for variables, native A/B as a safety check (v2)

**Why the plan changed** `[inferenza]`: a small show gets a few hundred lifetime views per episode; a two-arm test needs ~1,100 impressions to see a CTR **double** and ~13,500 to see +25 %; Test & Compare decides on watch time share, which is noisier. On such an episode a 14-day native test would almost surely end «Inconclusive».

### 15.0 Know the traffic first

Before any test plan: Reporting API jobs created (`yt-auth`, `yt-reporting-setup --channel <slug>`, `yt-collect`; a new job backfills only 30 days) so `reach_daily` holds impressions, CTR, traffic source and device per video. Until then the operator reads Studio → Analytics → Reach (last 28 days: impressions, CTR, device split) by hand. The device split decides whether the display cap needs the 1.5× fallback (§10.1).

### 15.1 Native A/B: the package safety check

- **One test per new episode**, from release day (when impressions peak): the channel's current package vs the v2 package (or the two best v2 arms), same title. It checks that the new package does not lose; it is not where single variables are learned.
- Rules: 2 arms (3 max); meaningfully different arms; 3840×2160 for every arm; first-uploaded arm = highest rubric total; never edit title or thumbnail during the test; record watch time share **and** the impressions during the test.
- Single-variable tests (source, expression class, `guest_style`, `grade`, headline face, accent) go to the **pre-test** until the channel reaches ~2,000 impressions per arm in 14 days.
- Back-catalogue tests are allowed but on a small channel will mostly end inconclusive: only as a package check (current vs v2), never to learn a variable.

**Pack delivered to the operator** (Italian, in the episode note: `deliver/notes/` or the vault folder of the profile):

```
Test A/B — <titolo bloccato>
Tipo: controllo di sicurezza del pacchetto (attuale contro v2) su episodio nuovo, dal giorno di uscita
Ipotesi: <il telaio v2 non perde sul tempo di visione rispetto a …>
Ordine di caricamento: 1) <slug>_A1.png (rubrica più alta) 2) <slug>_B1.png
Titolo: invariato per tutta la durata
Avvio: <data> · Controllo: <data +14 gg> · Non toccare titolo/thumbnail durante il test
Dopo: segna l'esito (Vincitore / Stesso rendimento / Inconclusivo) e le impressioni del periodo; leggo io il resto
```

### 15.2 Human pre-test: how single variables are learned

- **Panels** (run by hand by the operator outside Claude): Prolific (≈ £32 for 100 Italian residents on a 90-s task, at £9/h + the 42.8 % company fee, VAT if due [ufficiale + secondario]) or PickFu (≈ $70 for 50 answers with one targeting trait, ≈ $140 for 100 [ufficiale]). Prices are re-checked before each run.
- **Task**: the candidate in a feed mock among 8 neighbours at a random slot (exposure as in the feed), then «Quale video apriresti?» and «Cosa promette questo video?»; plus a head-to-head of the two arms as feed cards with the same title. One variable per pre-test; everything else identical.
- **Sample size** [inferenza, binomiale esatto]: 100 answers detect a true 65/35 preference with ~83 % power (decision: ≥ 61/100 for one arm); 50 answers only 70/30 (~78 %, ≥ 33/50); a 60/40 needs ~200 (≥ 115/200). Fewer than the decision count = «pari», logged as such.
- **Consent**: the candidates show the guest's face to strangers before release: the guest's one-line OK first (a release does not cover it by itself). Competitor neighbours in a feed mock are a private stimulus, never a public page (protocol §3).
- It measures **stated preference and comprehension**, not CTR. A pre-test winner goes into the next native safety check.
- Kit, steps and how to log: `docs/yt/templates/pre-test-protocollo.md`.

### 15.3 After a test

Native: record the outcome label, watch-time share per arm if Studio shows it, impressions during the test, the video's Intro (0:30) and the Reporting API CTR for the period (CTR is per video, not per arm). Pre-test: counts per arm, n, the decision rule, the coded «cosa promette» answers. **Inconclusive is a null result, logged like any other.**

---

## 16. Scoreboard and learning

Stored per channel in SQLite `ab_tests` (design §8.4; `kind` = `thumbnail` | `title` | `both` for native tests, `pretest` for panels) and summarised in MEMORY.md (≤ 6 lines per channel).

| Lever | Native tests | Wins | Same | Inconclusive | Losses | Points |
|---|---|---|---|---|---|---|
| claim | | | | | | |
| proof | | | | | | |
| duo | | | | | | |
| name | | | | | | |

| Variable (pre-test) | Tests | Arm A wins | Arm B wins | Pari | Notes |
|---|---|---|---|---|---|
| expression class | | | | | |
| source (tight cam vs master) | | | | | |
| `guest_style` (none vs graphic) | | | | | |
| `grade` (natural vs mono, level 2b) | | | | | |
| headline face (Anton vs brand display face) | | | | | |
| accent / field mode | | | | | |

- Points (native): Winner = 1 to the winning arm's lever; Performed same = 0.5 to each; Inconclusive = 0 (but counted in Tests).
- **A pattern counts as real only after ~3 decisive results in the same direction** (native winners or pre-test results past the decision count); «Inconclusive» and «pari» never count toward the three.
- **Default lever rule**: until 8 native tests exist on a channel, keep the §5.2 table. After ≥ 8, the default becomes the lever leading by ≥ 2 points; re-evaluate every 5 new tests. Never pool channels (own, personal, clients).
- Secondary columns (context, not decisions): CTR from Reporting at D+28, Intro at 0:30 vs the channel's typical, traffic mix (Home-heavy videos naturally show lower CTR).
- Once per channel, generate Ask Studio's own thumbnail suggestion as a baseline concept and include it in one test (only if it does not alter a face).
- Dynamic thumbnails (if they reach Italy): prepare a coherent set of 3 aimed at different segments (name / credential / outcome) inside the series frame.

**From scoreboard to learning (2026-10-13, `13-learning-loop.md` §4.3).** The two tables above are no longer filled by hand: `yt-thumb-learn priors --channel <slug>` computes them from the local records (`<studio_dir>/data/yt.db`, tables `thumb_*`), and the procedure lives in `commands/thumbnail.md`, section «Apprendimento thumbnail». The rules of this section still hold (a pattern needs ~3 decisive results; the default lever moves only after ≥ 8 native tests; never pool channels); learning adds to them:

| What | How it is learned | Signal |
|---|---|---|
| Every concept and render | A record with its features (template, lever, grade, `guest_style`, accent, expression class, hook family and word count, headline face, plate, face source, people, circle) and the render's measured face %, row heights % and QA metrics | — |
| G2 | Pairwise preferences: the chosen render beats each rejected one; the operator's reason verbatim. A delegated G2 has weight 0 | `scelte` (operator) |
| Native A/B, pre-test | Winner > losers (decisive); «Performed same», «Inconclusive», «pari» = tie, never a loss | `esiti` (audience) |
| D+7, D+28 | CTR in the main traffic source vs the channel's previous ≤ 10 same-format videos (only outside the noise, `09` §3); otherwise same-age views (Tier 0, flagged weak). With several arms live, only their shared features learn. T+48h never moves a prior | `esiti` |

- **Model** `[inferenza]`: one Beta per channel, signal, feature and value; the knowledge default (profile `thumbnails` defaults, the §0.2 targets) starts slightly ahead, and the prior weighs a few pseudo-observations, so it moves slowly. Every number shown carries n and a confidence (`13` §3.3); «bassa» means the §5.2 table decides.
- **Concept choice**: `yt-thumb-learn rank` keeps 2 exploit concepts (highest posterior mean) and 1 exploration concept (Thompson draw), never fewer than 2 levers; out-of-policy concepts are excluded, never edited. The evidence goes into the G2 brief with `[appreso: scelte|esiti, n=…, conf. …]`. A prior is not a CTR forecast.
- **Golden set**: every published thumbnail is copied, self-contained (concept, cutouts, plate, sidecar, QA), to `<studio_dir>/data/thumb-golden/<slug>/<video>/<render>/`. `yt-thumb-learn golden check` re-renders them with the current templates and reports pixel and metric drift: a warning to look at before merging a template change, never a block.
- **Niche references**: once a month `yt-thumb-learn refs refresh` replaces `<studio_dir>/data/refs/<slug>/grid/` with ≤ 8 peer thumbnails (≤ 2 per peer channel, the furthest above their own channel's median, ≥ 14 days old); `yt-thumb-qa --grid auto` uses them for §13.2 while they are ≤ 30 days old (`11` §3).
- **Post-mortem** at D+7 and D+28 (`/youtube:review`): `yt-thumb-learn postmortem --video <id>` (published versions and their features, the G2 choice and reason, outcomes with strength and n, the priors this video moved, the next exploration arm).
- **Tier B**: when a lesson has enough evidence, `yt-thumb-learn proposals` writes it as a candidate (only for channels whose lessons may be shared, `13` §9): a stricter face floor, or a row in §16.1. Hard rules never move (`13` §2): `guest_style: graphic` is never proposed as a default, thresholds only tighten. Profile defaults (default template, grade, lever) are never a PR: `yt-thumb-learn proposals` returns them as `profile_changes`, a local suggestion with the exact one-line edit that the operator applies to the profile, for every channel (`13` §1.1).

### 16.1 Learned thumbnail lessons

Rows added only through reviewed learn PRs (`yt-learn propose` → `propose-pr`): rule and counts, never images, hooks, names or reasons. The columns are those of `yt-thumb-learn proposals`.

| Date | Channel | Signal | Feature = value | Jobs | Decisive | Mean (prior) |
|---|---|---|---|---|---|---|

---

## 17. Generative AI policy (thumbnails)

| Use | Status |
|---|---|
| **Props and plates from text only** (an object of the story, a texture, an empty environment) | **Allowed**: main session only, cost preflight, explicit OK per call, caps below; the prompt carries no names and no data of the guest; nothing is uploaded |
| Outpainting or editing a plate of the episode | **Not allowed**: it uploads a frame of the episode, and props are text-only. Headroom comes from the template (crop flush, darkened field) |
| Concept exploration mocks from text (to choose a concept, never shipped) | Same as props, inside the same caps |
| A channel owner's own face (expression, light) on a personal channel | Only with the profile's `owner_ai_edits: true` and the owner's consent per image |
| Any guest, any host, any client's guest | **Never** (§11.2, level 5) |
| Any person in a generated image, even a generic one | **Never** |
| Text inside an image model output | **Never** — typography is template-rendered |
| Uploading footage, frames, cutouts or plates with people to a generator | **Never** |

**Budget (default caps, profile `thumbnails.props_budget`).** At most **€5 per episode** and **€20 per calendar month** per channel, all generative calls included. The main session keeps the ledger `<studio_dir>/data/paid-calls.jsonl` (one JSON line per approved call: `date`, `channel`, `episode`, `tool`, `model`, `units`, `cost_eur`, `approved_by`); the agent reads it to compute the month-to-date total before writing a request, and never writes it.

**The prop-request workflow** (the agent never calls a paid or generative tool):
1. The concept sets `plate: {"source": "prop"}` and `prop: {"prompt": …, "slot": …}` (no `path` yet); the agent writes `thumbs/props/<id>.request.json`:
   ```json
   {"concept": "B", "slot": "prop", "purpose": "l'oggetto della storia accanto all'ospite",
    "prompt": "a single ceramic coffee mug on a dark workbench, studio light, empty background",
    "negative": "no people, no faces, no hands, no text, no letters, no logos, no watermark",
    "palette": ["<ink HEX>", "<paper HEX>", "<accent HEX>"], "aspect": "1:1", "background": "transparent if supported",
    "size_px": 2048, "candidates": 4, "models": ["<modello e costo unitario da preverificare>"],
    "estimate_eur": 0.0, "month_to_date_eur": 0.0, "cap_episode_eur": 5, "cap_month_eur": 20,
    "fallback": "placeholder locale: campo ink con grana + forma d'accento", "output": "thumbs/props/B.png"}
   ```
   The prompt is in English for the model and describes only an object or a place; it never names the guest, the company or the episode.
2. Until the prop exists the template draws the **local placeholder** in the prop slot (an ink field with grain and the accent shape, or the scene plate), so every concept renders and passes QA without paid calls.
3. The agent writes the request block of 11-compliance-safety.md §10 into the G2 brief (estimate, month-to-date, caps). The main session runs `get_cost` (or the provider's price page), asks the operator, generates, appends the ledger line and saves the file at `output`.
4. A request that would exceed a cap is not written; the brief says so and keeps the placeholder.
5. The generated prop is saved at `output` and its path goes into the concept's `prop.path`; it is checked like any asset: no person, no text, one accent, licence of the output recorded in the brief.

Generative help on a thumbnail is production assistance and needs no altered-content disclosure (§2). Higgsfield trains on inputs by default on non-enterprise accounts [ufficiale]: one more reason to send text only.

---

## 18. Worked example (illustrative; guest, numbers and lines are invented)

Episode of «Il Caffè dei Maker»: a founder («Sara R.») who built a SaaS for dental clinics alone. Locked title candidate: «Dodici mesi da sola su un SaaS per dentisti: cosa ha portato i primi clienti». Tight camera on the guest and on the host, Marco.

| Concept | Lever · hypothesis | Hook (candidates) | Keyword | Template · class | Face source | `payoff_at` | Pairing check |
|---|---|---|---|---|---|---|---|
| A | claim · maker che sanno programmare: cosa è servito oltre al codice | «IL CODICE NON BASTAVA» / «SCRIVERE CODICE NON È BASTATO» | CODICE | `duo` · guest `intenso` (talking), Marco `neutro` (listening) | tight cam, guest face 44 % (0.6× resize), Marco 36 % | 812.4 (cold open clip 1) | stems codic, basta vs title — no overlap ✓ |
| B | proof · chi vende a studi professionali: un numero vero di clienti | «DA 0 A 40 STUDI IN UN ANNO» | 40 | `prova` · `sorpresa` | master inset, face 38 % (2.0× effective at 1280), served detail 820 | 1544.0 (cold open clip 2) | "studi" vs "dentisti", "clienti" — no overlap ✓; 40 verified with the guest |
| C | duo · chi è indeciso se cercare un socio | «SOCIA O DA SOLA?» | SOLA | `duo` · Marco `scettico` (his real question) | tight cams, same episode | 2210.5 (cold open clip 3) | "sola" shares a stem with "da sola" in the title ✗ → rewrite the title to «Dodici mesi senza soci su un SaaS per dentisti…» or change C |

Cold reads (168 px only): A «una founder spiega che per vendere il suo SaaS il codice non è bastato · per chi costruisce prodotti» = 2; B «come trovare i primi clienti tra gli studi dentistici» = 2; C «se fare startup da soli o in due» = 1 (audience vague). Gate passed (2 of 3 at 2).

Rubric excerpt (`qa/report.md`): A1 = 17/20 (1:2, 2:2, 3:2, 4:1, 5:2, 6:2, 7:2, 8:1, 9:2, 10:1 — Marco's mic and shoulder sat in the bottom-right zone: allowed, but his face edge touched it; cutout moved 40 px left, re-render = 18/20). B1 = 16/20. C1 blocked by item 6 (zero-tolerance) until the title changes.

Test plan: this is a new episode, so a native **safety check** v1 package vs A1 from release day, title fixed, 14 days. The variable "A1 `intenso` vs A1 `sorriso`" goes to a pre-test with 100 Italian respondents (decision at ≥ 61/100). Results go to `ab_tests` and the scoreboard.

---

## 19. Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Hook unreadable at 216 | > 3 words per line in a wide display face; line height < 12 % | Fewer words per line (2 lines of 2–3), or the condensed Anton (§7.7); never fall back to a 2-word fragment |
| Hook is a fragment («UNA LISTA») | The old "≤ 4 words, prefer the short version" rule | Rewrite as a statement with a verb and a stake (§5.3); the render now fails it |
| Thumbnail disappears in dark grid | Ink or near-black field without a large, light face; `edge_dL_dark` < 25 with no light frame element | Accent circle or paper disc touching the canvas edge (≥ 10 % of the perimeter), a brighter graded scene plate at the edges, bigger face (cap allowing), paper headline mass |
| A light shirt on the host is the brightest mass (first-generation duo) | Wide host crop; natural colour | Crop the host tighter so the shirt is cut by the bottom edge; the mono curve's shoulder puts pure white at L\* ≈ 75, under the paper headline |
| Accent circle merges with the head | Circle of the same luminance as the hair or skin (a skin-toned accent behind light skin in colour; any accent near mid-grey on mono) | `accent: auto` or the accent `circle_contrast` ranks first; circle behind the shoulders; on colour, a lighter accent only with ΔL\* ≥ 20 |
| `grade_uniform` / `grade_face` fail on a mono render | A vignette, grain or light effect drawn over the people; two cutouts graded with different curves; a local dodge on a face | Effects under the people or on the plate only; one curve for the whole photo (2b); never touch a face locally |
| `grade_uniform` error «il ritaglio indicato dal sidecar è già senza colore» | The sidecar points to the graded cutout, not to the level-0 colour cutout | The renderer writes `people[].source_path` (the colour cutout); re-render |
| Duo headline under 20 % | 5–6 words, or 3 lines of long words | 3–4 words in 2 lines (§5.3), people further to the sides; otherwise `ritratto` |
| Thumbnail disappears in light grid | Paper or pastel field | Darkened scene plate or ink field; darker cutout shadow |
| Keyword vanishes in grayscale | A light accent next to paper; an accent next to a grey of similar value | Keyword box with ink text; accent only beside paper on a dark field |
| Face blends into the background (ΔL* < 10) | A wall or circle of skin-tone luminance behind the face | Darken the plate ≥ 25 ΔL* around the head, move the circle behind the shoulders, switch to another brand accent, or `guest_style: graphic` outline (on request) |
| Soft face at 1280 or in the 720 file | Master frame enlarged past the effective cap; wide shot instead of inset | Tight camera ISO; inset frame; the option-b cap (1.5×); smaller face in `prova` |
| Face < 35 % on a claim | Wide-shot source (effective ~97 px) | Inset or tight camera; otherwise `face_floor_reason` at G2, never a soft upscale |
| Only sceptical frames found | Ranking by mouth-open; no tight camera | Expression classes (§10.2), MediaPipe; ask the crew for the tight camera |
| Outline everywhere | `guest_style: graphic` used as a default | `none` is the default; `graphic` only as a requested variant or a pre-test arm |
| Glasses lens missing on the cutout | Matte hole on a coloured wall | v2 lens fill inside the eye contour; render fails on α < 0.9 in the face box |
| Green halo on hair | Gradient canvas leaking into the matte | Re-cut with `--mode person`; fallback matting; never paint the hair |
| Warm/red fringe on hair | Spill from a saturated wall behind the person + Vision decontam + choke | `yt-portrait cut` (BiRefNet + spill/halo clamps); warning at fringe_rb > 12 |
| Hair cut flat or a hand cut vertically inside the canvas | Cutout from a crop placed with the straight edge inside | `yt-thumb-render` fails it; move the cutout flush, trim at a canvas edge, or pick another frame |
| Guest in profile at 168 px (no eye contact) | Frame chosen at the hook moment (wide shot, yaw −45…−60°) | Frontal frames from another moment of the same episode (§10.5) or the tight camera; declare it at G2 |
| Label or logo collides with the hover icons | Format label right-aligned to the canvas edge | Label ends at x ≤ 1150 (§7.7) |
| Concept rejected at G2 as clickbait | Payoff after 30 s or claim compressed beyond the guest's meaning | Re-anchor on a verbatim line inside the cold open |
| Title and thumbnail say the same thing | Same stem/number | Move the outcome to the title, the tension/proof to the thumbnail |
| A/B on an old episode ends «Inconclusive» | Too few impressions | Expected: log it; learn the variable with a pre-test (§15.2) |
