---
description: Thumbnail — 3 concept su 3 ipotesi, lettore a freddo a 168 px, volti veri dalla camera stretta o dal master (yt-portrait, classi d'espressione), telaio di serie (duo, ritratto, scena, prova, generic) con i token del brand, QA v2, rubrica, gate G2, pre-test umano e A/B di sicurezza (props AI solo da testo, nella sessione principale)
argument-hint: "[richiesta] [--channel=<slug>] [--episode=<workdir>] [--title=\"titolo bloccato o candidati\"] [--tight=<file ISO della camera stretta>] [--photos=<cartella foto fornite dall'ospite>] [--engine=html|remotion] [--resume=G2] [--lang=it]"
---

# Thumbnail

## Integrazione

- **Dove gira**: dentro l'agente `youtube:producer`. Se questa skill arriva nella sessione principale (l'operatore ha scritto `/youtube:thumbnail` invece di `/youtube:producer`), non eseguirla lì: applica `${CLAUDE_PLUGIN_ROOT}/commands/producer.md` con la stessa richiesta e gli stessi parametri (lancia l'agente con il tool Agent, `subagent_type: "youtube:producer"`, e gestisci i gate come dice il dispatcher). Il guard dei comandi, la memoria e l'apprendimento dell'agente valgono solo lì. Se sei l'agente, o se la skill gira in una sua eval (`evals/`), prosegui.
- **Lingua output**: italiano di default (`--lang` per cambiare). Il testo sulla thumbnail, il brief G2, la rubrica, le richieste di props e il piano dei test sono in italiano.
- **Parametri**:
  - `--channel` carica il profilo `<slug>.md` (nei `channels_dirs` di `yt-config`); `--episode=<workdir>` indica la cartella dell'episodio;
  - `--title` passa il titolo bloccato o i candidati: serve per il test di abbinamento;
  - `--tight=<file>` indica il file ISO della camera fissa stretta sull'ospite (fonte preferita, `07` §10.6); senza, la skill cerca in `<workdir>/src/iso/`;
  - `--photos=<cartella>` indica foto fornite dall'ospite (ultima fonte, con permesso scritto);
  - `--engine=html` è il default (template con controlli automatici); `remotion` usa `ThumbnailStill`, solo per i canali propri o personali con stili Remotion nel brand e licenza confermata nel profilo;
  - `--resume=G2` riprende dopo la scelta dell'operatore (o una delega esplicita del G2).
- **Workdir**: scrive `thumbs/concepts.json`, `thumbs/portrait/`, `thumbs/frames/`, `thumbs/cutouts/`, `thumbs/plates/`, `thumbs/renders/`, `thumbs/qa/`, `thumbs/cold/` (letture a freddo), `thumbs/props/` (richieste di props), `thumbs/pretest/` (kit del pre-test) e `thumbs/ab_plan.json`. La rubrica va in `qa/report.md`, sezione «Thumbnail».
- **Nota**: crea una nuova nota datata `{YYYY-MM-DD} — Thumbnail e piano dei test {episodio}.md` con `skill: /youtube:thumbnail` e `status: draft`, secondo `deliverables_mode` e il profilo (agente, Passo 4.2): nella cartella deliverable del profilo nel vault, oppure in `<workdir>/deliver/notes/`.
- **Agente**: `youtube:producer`. I concept nascono prima di G1, così il cold open paga la promessa della thumbnail. I render arrivano dopo, con G2. Il lettore a freddo è il sub-agente `youtube:thumb-cold-reader`.
- **Confini**:
  - idee e copy del packaging (titoli, angolo) sono dell'operatore o della sua skill di packaging, se ne ha una (questa skill ne legge la nota);
  - il titolo di pubblicazione è dell'operatore;
  - impostare la thumbnail, lanciare il test A/B su YouTube e lanciare un pre-test su Prolific o PickFu lo fa solo l'operatore.
- **AI generativa**: mai dentro l'agente. Props e sfondi **da solo testo**, solo se il profilo li ammette (`thumbnails.ai_generation`): l'agente scrive la richiesta, la sessione principale fa il preventivo e chiede l'OK per ogni chiamata, entro i tetti del profilo (`thumbnails.props_budget`). Mai persone, mai volti, mai testo nell'immagine, mai upload di girato.
- **Quando usarla**: per ogni episodio o video lungo prima di G1 (concept) e dopo il montaggio (render e test). Anche per i controlli di sicurezza A/B sul catalogo già pubblicato.
- **Apprendimento** (attenzione massima, `13-learning-loop.md` §4.3): al Passo 0 legge `yt-learn report --focus thumbnail` e il playbook del canale; ogni concept e ogni render vengono registrati con le loro feature, la scelta del G2 diventa una serie di preferenze a coppie con i motivi dell'operatore, la versione pubblicata entra nel golden set locale e gli esiti a D+7 e D+28 aggiornano i priori. I passi sono nella sezione «Thumbnail learning» in fondo a questo file.

## Input

$ARGUMENTS

---

## Identity and standard

You design the click that stays. Three concepts on three different hypotheses, built from real pixels, rendered in the channel's series frame, checked at the sizes the feed really shows and in the file YouTube really serves. Then a test plan that fits the channel's traffic: a human pre-test for single variables, a native A/B as a safety check. Faces, colours and word counts are hypotheses, not laws: the large studies are correlational and mixed (`07-thumbnails.md` §3).

Rules that override everything below:

- **Real pixels only on people, within the policy ladder** (`07` §11.2). Level 0 always (crop, scale within the cap, matte, edge decontamination, ≤ ⅓ stop global exposure/white balance, the logged luma unsharp, soft neutral shadow). Levels 1–2 (outline/glow **under** the cutout; one global uniform tone LUT on the whole cutout, no saturation boost, skin ΔE00 mean ≤ 2.5 and p95 ≤ 5) only with `guest_style: graphic`, which is **never the default**. Level **2b**: with `grade: mono` one uniform monochrome curve on the whole photo, every person and the plate alike, nothing local on faces, identity and expression intact; the skin ΔE00 bound does not apply to 2b alone, the single-curve and landmark checks replace it. The default is `grade: natural` on every template; `mono` only where the profile allows it (`thumbnails.grade_allowed`, `grade_default`). Backgrounds (plate grade, bokeh, pop-out, the accent circle) are free: they are not the person's pixels. Level 3+ is not available; level 5 (generative: relight, restore, AI upscale, expression or skin edits, face swap, mirror flip) is forbidden (`11-compliance-safety.md` §0 #5).
- **Expressions are found, never staged**: tight camera ISO first, then master frames, ranked by expression class (`07` P5, §10.2). No posed photo session: the fix for small or soft faces is the tight fixed camera at the next recording (`07` §10.6).
- **The hook is 3–6 words and says something on its own** (`07` P4, §5.3; profile `hook_words_min`, `hook_words_max`). A noun fragment is never the hook. On `duo`: **3–4 words in 2 lines** (profile `hook_words_max_duo`, default 4), **every line ≥ 20 % of the height** (`duo_line_min_pct`, default 20).
- **Typography is rendered by the template, never by a model** (`07` §0).
- **The promise is paid inside the first 30 s**: each concept's `payoff_at` must fall inside the cold open (P2).
- **Title and thumbnail never repeat each other** (P1, title-pairing test `07` §5.4).
- **Platform facts** [official]:
  - Recommended size 3840×2160 (min width 640), ≤2 MB from mobile, ≤50 MB from desktop; podcast playlists need a 1:1 image (https://support.google.com/youtube/answer/72431, verified 2026-10-11).
  - A/B tests take up to 3 titles and/or thumbnails, pick the winner by **watch time share**, and run up to 2 weeks in desktop Studio with advanced features. If any variant is below 1280×720, all are downscaled to 854×480 (https://support.google.com/youtube/answer/13861714, verified 2026-10-11).
  - Thumbnails that trick viewers break the spam and deceptive-practices policy (https://support.google.com/youtube/answer/2801973, verified 2026-10-11).
- **Do not cite** «+154% CTR», «faces +38%», «red = 7% CTR», «7:1 contrast» or any other number in `10-evidence-ledger.md` §3, and never an AI «CTR score». Never promise a CTR or watch-time gain: a render, a rubric total, a cold read and a pre-test are not a forecast.

## Inputs to load

1. **Channel profile**:
   - `thumbnails`: `default_lever`, `series_frame`, `default_template`, `templates`, `format_label`, `meta_line_rule`, `show_logo`, `episode_badge`, `host_tag`, `accents`, `accent_rule`, `grade_default`, `grade_allowed`, `grade_rule`, `guest_style_default`, `guest_style_allowed`, `hook_words_min`, `hook_words_max`, `hook_words_max_duo`, `duo_line_min_pct`, `cap_height_min_px`, `keyword_line_min_pct`, `dark_feed`, `face_min_pct_claim`, `display_cap`, `served_detail`, `source_priority`, `master_face_px`, `owner_ai_edits`, `ai_generation`, `props_budget`, `episode_notes` (episode-specific blocks, e.g. an episode whose numbers are not confirmed yet: no numbers in hooks). A key missing from the profile takes the default of `07` (and of `_template.md`); say which defaults you used in the brief;
   - `brand`: tokens, fonts, `text_pairs_allowed` and forbidden pairs, `one_accent_rule`, logo rules;
   - `voice`: banned words, public names and their forbidden forms, the channel's `copy_rules` if any;
   - `consent`.
2. **Knowledge**:
   - `07-thumbnails.md`, in full: §5 levers and hooks, §7.7 the series frame, §8 brand folders and template overrides, §10–§16 the procedure, §17 the AI policy and the prop workflow, §19 the failure modes.
   - `04-hooks-first-30s.md` §9 (triple alignment).
   - `03-story-structures.md` §11 (claims).
   - `05-editing-rules.md` §9 (face size in a composited master).
   - `06-captions-italian.md` §8–§9.
   - `11-compliance-safety.md` §6 (portrait law, hosts too), §10 (paid-call request format and the props budget).
   - `12-qa-gates.md` §4 and §8.
   - Templates for the operator: `docs/yt/templates/brief-camera-stretta.md`, `messaggio-ospite.md`, `pre-test-protocollo.md`.
3. **Agent memory** (MEMORY.md):
   - lever scoreboard and pre-test log per channel;
   - thumbvision calibration (eyes, mouth, blink, smile cut-offs);
   - the expression class and the accent of the channel's last upload (P8: the frame stays, these change).
4. **Data**: past tests with `yt-db query "SELECT kind, variants_json, winner, result_json FROM ab_tests WHERE channel='<slug>'"` (native tests and `kind = 'pretest'`); impressions and device split from `reach_daily` if the Reporting jobs exist (`07` §15.0); the props ledger `<studio_dir>/data/paid-calls.jsonl` (read only) for the month-to-date spend.
5. **Workdir**:
   - `edit/selects.json` (rows with `thumb` in `uses`, claims and their status);
   - `edit/cold_open.json` or `edit/edl.json` (cold-open segments);
   - `src/iso/` (tight camera and camera ISO files), `analysis/frames/`, `analysis/transcript.words.json`;
   - the brand's `layout.json`: the channel's brand folder `<brands_dir>/<slug>/` (`yt-config --get brands` prints each visible brand and its folder, `07` §8), or the built-in `demo` brand in `${CLAUDE_PLUGIN_ROOT}/scripts/yt/assets/brands/demo/` when the channel has none (declared);
   - the packaging note (the operator's, or his packaging skill's), if it exists; otherwise the titles the operator gave.

Toolkit commands (`thumbvision` included) are on the Bash PATH while the plugin is enabled: call them by bare name, never through the plugin cache. Where a v2 flag in this file and the tool's `--help` disagree, the `--help` wins: use it and write the gap in the brief.

**Templates, as implemented.** List `${CLAUDE_PLUGIN_ROOT}/scripts/yt/node/templates/` (the built-ins `duo`, `ritratto`, `scena`, `prova`, `generic` and the shared helper `_common.js`) and `<brands_dir>/<slug>/templates/` before choosing: a template that is not there is not rendered. When the brand folder has its own `<slug>-<nome>.html` for a role (e.g. `<slug>-duo.html`), use it in place of the built-in by writing `"template": "<slug>-duo"` in the concept (`07` §7.6, §8); it keeps the same geometry and pre-checks. Every built-in takes text, colours, fonts, wordmark and labels from the brand's `tokens.json` and the concept, never from the template. Map them like this:

| Lever | Series frame (`07` §7.7): own and personal channels, and clients that use it | Client on the generic layout |
|---|---|---|
| `claim` (default) | `duo` (guest + host of the same episode: the default frame, profile `default_template`) · `ritratto` (single-face episodes, or when no host frame works; closed-mouth smile frame preferred) · `scena` (pop-out on the real set) | `generic` |
| `proof` | `prova` | `generic` + `artifact` |
| `duo` | `duo` with the host's real question as hook | `generic` + two `people` |
| `name` | `ritratto` with the name plate | `generic` |

A channel with only one person on camera (solo talking head) has no host frame: `ritratto`, `scena` and `prova` are its family and the `duo` lever does not apply. A client uses `generic` with its tokens unless its profile sets `default_template` to a series template; either way the tokens come from the client's kit (`--tokens <brands_dir>/<slug>/tokens.json`), never the `demo` ones in a delivered thumbnail.

**Engine.** Default to `--engine html` for every channel.
- The HTML path runs the automated pre-checks of `07` §12.4 (v2): no-go zones, hook length and form (`duo`: the profile's 3–4 words), line heights (every hook line ≥ 12 % of the height, keyword ≥ 18 % when set larger than the phrase — a warning in the one-size v2 headline; `duo`: every line ≥ the profile's `duo_line_min_pct`), text over faces, colour pairs, straight crop edges, the display cap, the served-size detail, face size and duo order, face–surround ΔL*, guest-pixel checks for the declared `guest_style` and `grade` (2b: one curve signature on people and plate, mapping within 2 levels, landmarks), the accent circle's contrast, matte holes, one accent, logo size, fonts; warnings for fringe, faces < 40 %, silhouette at 246 px, dark-feed separation; saliency as info. A render with an error exits ≠ 0. With `--debug` it saves a zones overlay.
- `--engine remotion` renders the Remotion `ThumbnailStill` still and returns **no automated checks**. Use it only for a claim concept on an own or personal channel whose brand has `remotion.json` styles (`07` §8) and whose profile records the Remotion licence as confirmed (`graphics_licence.status`), when the operator wants that look; then check the geometry by eye on the QA sheet.
- Say which engine you used in the brief.

## Procedure

### Phase 1 — Concepts (before G1, so the cold open can pay them)

1. **Preconditions.**
   - Locked title or 2–3 title candidates (`--title` or the packaging note). Without them the pairing test can't run: ask.
   - Consent as the profile requires (agent Passo 4.1). With `release_required: true` (the default) the release must cover thumbnails: release unknown → `stato: in attesa di decisione` with the question «Liberatoria firmata? Cosa copre?»; release confirmed absent or not covering this use → `stato: bloccato`. With `release_required: false` (the operator's written decision in the profile) there is no release check for the guest. On a duo concept, every host shown is asked for their OK too (`11` §6.3). A video with no guests (the operator says «nessun ospite»): no release question, `11` §6.4 «No guests».
   - Episode blocks in the profile (`thumbnails.episode_notes`): e.g. an episode whose revenue numbers are still unconfirmed has no numbers in hooks and no `prova` concept until they are.
2. **Lever choice** (`07` §5.2). Decide guest recognisability from evidence (own channel or LinkedIn following, search presence, the operator's call; when unsure, «none»), then pick from this table:

| Guest | Verified number or artifact? | Real tension? | Three concepts |
|---|---|---|---|
| unknown (the usual case on a small channel) | yes | yes | claim · proof · duo |
| unknown | yes | no | claim · proof · claim-2 (different line, expression class and hypothesis) |
| unknown | no | yes | claim · duo · claim-2 |
| niche | any | any | claim · name · proof-or-duo |
| known | any | any | name · claim · proof-or-duo (+ invite as Collaborator) |

   - Never fewer than 2 levers. On a solo channel (no host frame) replace `duo` with `claim-2`.
   - After ≥ 8 native tests on a channel, the default lever is the one leading the scoreboard by ≥ 2 points (`07` §16). Never pool channels.
3. **Start from the packaging concepts.** If the packaging note (the operator's, or his packaging skill's) has thumbnail concepts, map each one to a lever, a hypothesis and a template first and keep its idea; generate new concepts only for a lever none of them covers. You never write titles here (P1 tests against the operator's titles).
4. **Three hypotheses, not three styles.** Write one `hypothesis` per concept (who it is for + what it promises, one line) before anything visual. Two concepts whose hypotheses say the same thing are one concept: replace one.
5. **Brainstorm ≥ 8 on-image hooks internally** (P11), from the transcript vocabulary, anchored to timestamps (`07` §5.3):
   - **3–6 words, a complete statement**: subject + verb + stake, a past-tense admission, the negation of a belief, a short real question, or a verified number + unit inside a statement. Noun fragments are rejected; over 6 words is a warning. **`duo`: 3–4 words** (the headline must fit 2 lines at ≥ the profile's `duo_line_min_pct` of the height); when no faithful 3–4-word compression exists, the concept goes to `ritratto`.
   - **Two hook candidates per concept**, both 3–6 words. One `keyword` that carries the stake.
   - Forbidden: the profile's banned words and forbidden name forms, empty superlatives, bait, unverified numbers, whatever the channel's `copy_rules` forbid.
6. **Expression class per concept** (`07` §5.5): the class that fits the lever (claim → `intenso`; «contro» → `scettico`; result/number → `sorriso` or `sorpresa`; story → `intenso`; duo → the host's genuine reaction). Never «the most emotional frame».
7. **Title-pairing test** (`07` §5.4).
   - Lowercase both strings, drop the Italian stopwords, compare 5-letter stems and numbers. Any shared stem fails; override only with a written reason (name-led). The name plate and the meta line are not tested.
   - Judge step: do title and thumbnail open **one** gap together?
8. **Truth anchor per concept.**
   - The line is verbatim, or a faithful compression, with a timestamp.
   - Any number has a `verified` claim.
   - The face belongs to whoever said the line; a host's reaction matches the host's real stance.
   - The meta line (event / year, the city only when it adds something; profile `meta_line_rule`) is verified item by item (`07` §7.7); fewer items are fine, an unverified item never.
   - A duo was really in the conversation and the tension really happened (`07` §10.5).
9. **`payoff_at`** (source seconds): where the promise is paid. Before G1, hand these times to `/youtube:hook` so the recommended cold open contains them. After G1, a concept whose `payoff_at` falls outside the cold-open segments of `edl.json` is dropped, or flagged for the operator if it was the strongest.
10. **Novelty inside the frame (P8).** The series frame stays. Do not repeat the previous upload's expression class **and** accent together (MEMORY.md, or the previous workdir's `thumbs/concepts.json`).
11. Write `thumbs/concepts.json` (Output standards). Props: a concept that needs an object of the story gets `plate: {"source": "prop"}` and a request (section «Props da testo»); it renders with the local placeholder meanwhile.
12. **Sketch and cold read** (`07` §13.3).
    - Sketch each concept: render it with the best frame available now (run the Phase 2 scans first if they have not run: the tight camera scan if the file exists, else the master scan's top frame of the right class) into `thumbs/sketch/` with `yt-thumb-render … --out <wd>/thumbs/sketch`. Sketches are never shipped and never go to G2.
    - Make the two tiles per concept: `FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`; `$FF -v error -y -i <sketch>.png -vf "scale=168:94:flags=lanczos" <wd>/thumbs/cold/<id>_168.png`; `$FF -v error -y -i <sketch>.png -vf "scale=720:405:flags=lanczos" -q:v 3 <wd>/thumbs/cold/<id>_720.jpg`.
    - Spawn **one fresh** `youtube:thumb-cold-reader` per concept (Agent tool, `subagent_type: "youtube:thumb-cold-reader"`), in random order, with this brief and nothing else: «Leggi a freddo questa thumbnail. File: <percorso assoluto di <id>_168.png>, <percorso assoluto di <id>_720.jpg>.» Never pass `concepts.json`, the title, the hypothesis, the transcript or another concept.
    - Score each read against the concept's `hypothesis`: 2 = right promise and right audience; 1 = right promise, vague audience; 0 = wrong promise or not understood. Save the reads and scores in `thumbs/cold/cold_reads.json`.
    - **Gate**: at least 2 of 3 concepts score 2. A concept at 0 gets one rewrite (hook or class) and one fresh re-read; if it still fails, drop it or flag it for the operator. The cold reader is a `[giudizio LLM]`: it informs, it does not decide.

### Phase 2 — Sources, frames and cutouts

**Source priority** (`07` §10.1; profile `source_priority`):
1. the **tight fixed camera ISO** on the guest (and on each host, when there is one): `--tight` or `<workdir>/src/iso/`;
2. main camera ISO frames;
3. composited master frames (inset preferred over the wide shot, when the layout has one);
4. guest-supplied photos with written permission (`--photos`; declared at G2: not the episode moment).

There is no posed photo session. If there is no tight camera and the master cannot reach the face floor within the cap, say so in the brief and ask the operator to send the crew brief (`docs/yt/templates/brief-camera-stretta.md`) and the guest message (`docs/yt/templates/messaggio-ospite.md`) before the next recording.

**Default since v2 — `yt-portrait` (`07` §10.2, §11):**

```
yt-portrait scan <wd> --src <wd>/src/iso/<file> --layout full --out <wd>/thumbs/portrait/ospite   # camera stretta: prima fonte
yt-portrait scan <wd> --src <wd>/src/iso/<file-host> --layout full --out <wd>/thumbs/portrait/host
yt-portrait scan <wd>                                    # master: alcuni minuti per un'ora di girato; scan.json + scan_sheet_*.jpg + scan_expr.jpg (una riga per classe)
yt-portrait cut <wd> --src <wd>/src/iso/<file> --roi full --t <s ISO> --name ospite_<t>    # camera stretta: riduzione, mai ingrandimento
yt-portrait cut <wd> --t <s> --roi inset --name ospite_<t>        # master con inset: volto al massimo consentito dal tetto (2.0× effettivo a 1280)
yt-portrait cut <wd> --t <s> --roi inset --display-cap b --name ospite_<t>_b   # ripiego 1.5× (opzione b)
yt-portrait cut - --image <foto> --name ospite_foto      # foto fornite dall'ospite (permesso scritto)
yt-portrait plate <wd> --t <s> --name scena              # plate della scena reale (duo, scena)
```

- `--expr auto` (default) uses the MediaPipe blendshapes when the extra is installed (`install.sh --with-mediapipe`) and the Apple Vision geometry otherwise; `--expr vision|mediapipe` forces one. `scan.json` says which. Installing it is the operator's call in the main session (`/youtube:setup`), never yours.
- `--roi inset` needs an `inset` box in the brand's `layout.json` (a composited master); on a full-frame source use `--roi full`.
- Read the class rows of `scan_expr.jpg` and the contact sheets by eye (eye contact or a believable gaze, no mid-word mouth, no motion), then cut 1–3 candidates per concept in the class the concept needs. If the scan says «non trovato» for that class, change the concept's class (and its hook if needed), or declare the gap.
- Each cut writes `<n>.png` (already at the final size: the series templates draw it 1:1), `<n>.json` (scale, effective resolution, the display cap used, straight edges, fringe before/after, source and ISO time) and `<n>_proof.jpg` (preservation proof). A face from another moment of the same episode is allowed for a claim (`07` §10.5: same person) but must be declared in the G2 brief.
- The tight-camera timeline is not the master's: `payoff_at` stays on the master timeline; the cutout sidecar records the ISO time.
- The manual steps remain for single moments and when `yt-portrait` is unavailable:
  1. **Candidate frames** around each concept's line at time `t`: `yt-frames <wd> --every 0.2 --from <t−2> --to <t+2> --size full --format png --out <wd>/thumbs/frames/<id>` (for the global sweep, reuse `analysis/frames/` and add `yt-frames <wd> --every 2 --from <a> --to <b> --size 1080` on the 2–3 liveliest chapters; for a duo, extract host and guest separately).
  2. **Score**: `thumbvision score <wd>/thumbs/frames/<id>/*.png > <wd>/thumbs/frames/<id>/scores.json` (on a composited master with an inset, add `--roi x,y,w,h` from the brand's `layout.json`, normalised 0–1).
  3. **Hard rejects** (`07` §10.3): no face when the lever needs one; `eyes_open` z < −1.0 within the person (or < 0.25 absolute with fewer than 30 frames); `mouth_open` in the person's top 20% on a non-laughing claim; `sharpness` below the episode's 25th percentile; a target face over the cap; face touching the window edge, covered by a picture-in-picture, or with a mic over > 15% of it.
  4. **Rank** per person: `rank = 0.35·q + 0.25·s + 0.20·h + 0.20·e` (within-person percentiles of quality, face height and sharpness; e = fit to the concept's class: 0, 0.5 or 1). Never compare `quality` across two people.
  5. **Cutout**: prefer `yt-portrait cut - --image <frame>`; fallback `thumbvision cutout <frame> --out <wd>/thumbs/cutouts/<id>.png --mode person` (`--mode subject` keeps the mic). Edge QA at 100% on paper and on ink.
- **Crop edges**: wherever the crop (inset, ROI, frame border) cut the person (top of the head, a hand), that straight edge must end flush with the canvas edge, or be trimmed at a canvas edge, or you pick another frame. A straight edge visible inside the composition is an S1 (`07` §11.1). Check it on the final render at full resolution.
- **First 3 episodes of a channel, and the first episode with a tight camera**: ask the operator to mark 10 frames good or bad and assign their class in the G2 brief; store per-channel cut-offs in MEMORY.md (`07` §10.4).

### Phase 3 — Render and QA (before G2)

1. **Render**: `yt-thumb-render --template auto --data <wd>/thumbs/concepts.json --out <wd>/thumbs/renders --engine html --debug --spotify`.
   - `auto` takes each concept's `template` (a built-in name, or a brand override `<slug>-<nome>`). `variants` render the hook candidates as `<id>_<template>_v1/_v2`.
   - Outputs: PNG 3840×2160, JPEG < 2 MB, `render.json` and a `.render.json` sidecar per render.
   - At most 12 renders before G2: 3 concepts × 2 hook candidates, plus at most one alternative accent, class or frame per concept.
2. **Read the sidecar per render**: `pass`, `errors`, `warnings` and the v2 checks (`07` §12.4). An error means fix the data and re-render; never relax a check, never pass an override the operator has not given (`upscale_override`, `face_floor_reason`, `detail_reason`, `hook_size_reason` are written reasons approved at G2). Remotion renders report no checks: inspect the geometry by eye instead.
3. **QA sheet and grid mock**: `yt-thumb-qa <wd>/thumbs/renders/*.png --out <wd>/thumbs/qa --grid <wd>/thumbs/grid --title "<titolo bloccato>" --channel-name "<nome canale>" --pos <0–8, not 4> --seed <n>`.
   - Exit codes: `yt-thumb-render` 0 = renders and checks ok, 3 = renders produced with failed checks, 1 = no render; `yt-thumb-qa` 1 with `all_checks_pass: false` = a blocking check failed on a render with a sidecar (the thumbnail failed QA, the tool did not break), 1 with `ok: false` = an image could not be read.
   - Read `<stem>_qa.png` (`07` §13.1): row 1 dark (720, 500, 360, 216, 168), row 2 light (216, 168, 360, grayscale, blurred), row 3 the served chain (720 → 1180) with the check panel; and the JSON `checks` (`face_size`, `face_surround`, `phrase_line_h`, `keyword_line_h`, `hook_words`, `served_detail`, `silhouette_246`, `saliency_first`, `edge_dL_dark` / `edge_dL_light`, `circle_contrast`, `text_contrast_168`, `skin_de00`, and on `grade: mono` renders `grade_uniform`, `grade_face`, `grade_mono`, `grade_landmarks`, then `render_checks`). A missing metric is «non misurato», never guessed. On a mono render an error in a `grade_*` check is an S1: never ship it, fix the render (one curve, nothing over the faces).
   - Grid references come from `yt-research meta <URL…> --thumb --out <wd>/thumbs/grid_refs`: 8 videos of competitor or adjacent channels in the same language, ≤ 20 per call (or `--grid auto` with the monthly references, «Thumbnail learning» below). `yt-thumb-qa` reads only images placed directly in `--grid DIR`: `cp <wd>/thumbs/grid_refs/*/*.jpg <wd>/thumbs/grid/`.
   - Competitor images stay private and are deleted with the research cache within 30 days (`11` §3).
4. **If `yt-thumb-qa` returns `ok: false`**, build the tiles yourself and note the toolkit gap in `qa/report.md`:

```
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg; Q=<wd>/thumbs/qa; R=<render>.png; N=$(basename "$R" .png)
$FF -v error -y -i "$R" -vf "scale=720:405:flags=lanczos" -q:v 3 "$Q/${N}_720.jpg"          # il file servito: tutte le tile partono da qui
for W in 500 360; do $FF -v error -y -i "$Q/${N}_720.jpg" -vf "scale=$W:-2:flags=lanczos,pad=iw+32:ih+32:16:16:color=0x0f0f0f" "$Q/${N}_${W}_dark.png"; done
for W in 216 168; do $FF -v error -y -i "$Q/${N}_720.jpg" -vf "scale=$W:-2:flags=lanczos,pad=iw+32:ih+32:16:16:color=0xffffff" "$Q/${N}_${W}_light.png"; done
$FF -v error -y -i "$Q/${N}_720.jpg" -vf "scale=360:-2,format=gray" "$Q/${N}_360_gray.png"
$FF -v error -y -i "$Q/${N}_720.jpg" -vf "scale=360:-2,gblur=sigma=3" "$Q/${N}_360_blur.png"
```

5. **Read every tile.**
   - The real smallest surface is the watch-page sidebar, ~216 px wide on white: **every hook word readable at 216 on light**. The 168 tile is the stress test.
   - The grayscale tile checks value contrast; the blur tile checks for one dominant mass; the served-chain row checks that the face does not go soft at phone size.
   - On the grid, answer the three judge questions (`07` §13.2).
6. **Cold read of the finalists** (`07` §13.3): the same procedure as Phase 1 step 12, on the 1–2 best renders per concept, with fresh cold readers. Record the reads in `thumbs/cold/cold_reads.json` and in the rubric (item 1).
7. **Rubric** (`07` §14), 10 items scored 0–2. **Ship = ≥ 15/20, no 0 on items 1, 2, 6, 9, and no hard fail.**
   - Items: 1 glance (ZT, with the cold read), 2 hook legibility (ZT), 3 value contrast, 4 squint, 5 face quality (size, class, served detail), 6 title pairing (ZT), 7 brand frame (series frame + credential), 8 feed pop, 9 truthfulness (ZT, pixels within the declared `guest_style` and `grade`), 10 safe zones.
   - Hard fails: a forbidden token pair · person pixels beyond the declared level or any level 3–5 operation · text from an image model · a hook under 3 words or a noun fragment · an unverified number · `payoff_at` outside the cold open · a render below 1280×720 · a generated person or one from another episode.
   - Item 9 is never scored 2 without the timestamp written next to it.
8. **Tweak rounds**: at most 2 before G2, at most 1 after (`12` §9).
9. **Critic** on the candidate set before G2 (`12` §8.5 brief; Agent tool with `subagent_type: "general-purpose"`, read-only limits written in the brief): deliverable `thumbnail`, files `thumbs/renders/*`, `thumbs/qa/*`, `thumbs/concepts.json`, specs `12` §4 and `07` §11.2, §12.4, §14. It gets no rubric totals and no cold-read scores. Merge its findings into `qa/report.md`.
10. **G2 brief** (Output standards) in `qa/gate-G2.md` and in `qa/report.md` under «Note per l'operatore»; set `gates.G2: "pending"` (snippet in `edit.md` F.3). Then stop: `stato: in attesa di approvazione G2`, end of turn.

### Phase 4 — After G2 (`--resume=G2`)

The approval counts only as a message from the main session reporting the operator's choice (or an explicit delegation of G2: then the brief, the critic and your recommended arms, recorded as delegated). Copy it verbatim into `qa/gate-G2.md` under «Decisione dell'operatore (<nome>) — AAAA-MM-GG» and act only on the approved arms.

1. **Lock the chosen arms.** Masters are 3840×2160 PNG plus JPEG < 2 MB, and no arm goes below 1280×720.
2. **Derivatives.**
   - Spotify episode thumbnail 1920×1080: `yt-thumb-render … --spotify` writes `<name>_spotify-1920x1080.png` (Lanczos from the master); by hand: `sips -z 1080 1920 <arm>.png --out <wd>/thumbs/renders/<name>_spotify.png`. Spotify video podcasts want 16:9, ideally 1920×1080 (https://support.spotify.com/us/creators/article/thumbnails/, verified 2026-10-11 [official]).
   - The 1:1 show cover (once per show, 3000×3000) and vertical covers (1080×1350, 2160×3840) are **not automated** by the toolkit (16:9 viewport only). Produce them only on request, and say so.
3. **Test plan** (`07` §15): write `thumbs/ab_plan.json` and the note (vault or `deliver/notes/`).
   - **Traffic first** (`07` §15.0): if `reach_daily` has no impressions for the channel, say so and ask the operator to read Studio → Analytics → Reach (impressions, CTR, device split, last 28 days) or to create the Reporting jobs.
   - **Native A/B = safety check** of the package (the channel's previous thumbnail style against the new series frame, or the two best arms), on a **new** episode from release day: two arms (three at most), same title, highest rubric total uploaded first, never edit during the test, 14 days.
   - **Single variables → pre-test** (`07` §15.2): if the operator wants to learn a variable (class, source, `guest_style`, `grade`, headline face, accent), prepare the kit in `thumbs/pretest/<id-test>/` following `docs/yt/templates/pre-test-protocollo.md` (stimuli, hypothesis, decision rule ≥ 61/100, the guest's one-line OK, the decision on feed neighbours). The operator runs it by hand on Prolific or PickFu.
   - Back-catalogue tests only as package checks; on a small channel they will mostly end «Inconclusivo».
4. **Logging.** `/youtube:review` logs native outcomes in `ab_tests` after the test; you log pre-test results when the operator brings the CSVs (`kind: "pretest"`, protocol §8). The plan here records the hypothesis and the arms. The operator runs every test by hand (G3).

## Props da testo and other generative requests

The agent never calls a paid or generative tool. A prop or a plate from text is requested like this (`07` §17), and only when the profile allows it (`thumbnails.ai_generation`):

1. Read the month-to-date spend in `<studio_dir>/data/paid-calls.jsonl` (read only; missing file = €0). If the request would pass the profile's caps (`thumbnails.props_budget`: per episode and per month), do not write it: keep the placeholder and say so in the brief. Without `props_budget` in the profile, the caps are a decision for the operator: put the estimate in `decisioni richieste` and write nothing above what he approves.
2. Write `thumbs/props/<id>.request.json` (schema in `07` §17): slot, purpose, an English prompt that describes **only an object or a place** (no names, no company, no episode, no person, no hands, no text, no logos), the negative list, the palette from `tokens.json`, aspect, size, number of candidates, estimate, month-to-date, the caps, the local fallback and the output path.
3. Set the concept's `plate: {"source": "prop"}` and `prop: {"prompt": …, "slot": …}` without `path`: the template draws the local placeholder in the prop slot, so QA runs now. When the main session has generated the file, its path goes into `prop.path` and the concept is re-rendered.
4. Put this block in the G2 brief and in the return block (`11` §10):

```
Richiesta servizio a pagamento (da eseguire nella sessione principale)
Cosa: prop da solo testo per il concept B — thumbs/props/B.request.json (nessuna persona, nessun testo)
Perché il locale non basta: <evidenza: manca una prova reale; il segnaposto regge ma è generico>
Dati che escono dal Mac: solo il prompt testuale (nessun frame, nessun nome)  ·  Coperto dal consenso: non serve
Costo: <stima per candidato × candidati, da verificare con get_cost>  ·  Speso nel mese: <€ …> su <tetto mensile del profilo> · Episodio: <€ …> su <tetto per episodio>
Alternativa locale: segnaposto (campo inchiostro con grana + forma d'accento) o plate della scena
```

| Use | Status |
|---|---|
| Props and plates from text only (objects, textures, empty places) | Only if the profile allows it: main session, cost preflight, per-call OK, within the profile's caps, ledger kept by the main session |
| Concept mock-ups from text, never shipped | Same (inside the same caps) |
| Outpainting or editing a plate or a frame of the episode | **Never**: it uploads footage; props are text-only |
| The owner's own face (expression, light) on a personal channel | Only with the profile's `owner_ai_edits: true` and the owner's consent for that image |
| Any guest, any host of a channel with more people, any client's guest, any third person | **Never** |
| Text inside a model's output | **Never**: the template renders it |
| Uploading footage, frames, cutouts or plates with people | **Never** |

Generative help on a thumbnail is production assistance and needs no altered-content disclosure (https://support.google.com/youtube/answer/14328491, verified 2026-10-11 [official]).

## Gates

- **G2 (always, unless delegated).** Concepts, cold reads, candidate renders, QA sheets, rubric, prop requests and the test proposal go to the operator before any final pack. For clients, the client's sign-off arrives through the operator.
- **Stop with `stato: bloccato`** when:
  - the release (where the profile requires one) or a host's OK is confirmed absent (unknown → `stato: in attesa di decisione`);
  - no source reaches the face floor within the cap (ask for the tight camera at the next recording, and the operator's `face_floor_reason` for this one);
  - every concept needs an unverified number;
  - pairing fails for every title candidate;
  - fewer than 2 concepts pass the cold read after one rewrite.
- **Never** set a thumbnail, start a test, run a panel, install a package or touch YouTube.

## Learning (Passo 5, `13-learning-loop.md` §4.3)

Thumbnails get the most attention in the learning loop. The shared rules are in `13` §0–§3 (two signals, small-sample guard, Thompson exploration: 2 exploit concepts + 1 explore concept, hard rules H1–H12, thresholds that only tighten) and §12 (privacy: the golden set and the references never leave `<studio_dir>/data/`). The thumbnail-specific procedure (what is logged per concept and per render, the pairwise G2 preferences, the published versions and A/B arms, the golden set, the monthly references, the D+7/D+28 post-mortem, how Phase 1 uses the priors and shows the evidence at G2) is the section «Thumbnail learning» at the end of this file. Every recommendation taken from a prior is written in the G2 brief with `[appreso: scelte|esiti, n=…, conf. …]`; the exploration concept is labelled «esplorazione» and passes every check of Phase 3 like the others.

## Quality bar

`12-qa-gates.md` §4 T-pre and T-post, all ticked; `07` §14 rubric; `07` §19 failure modes checked; `11` §14 pre-flight («Before G2» row); severity per `12` §1.

## Output standards

### `thumbs/concepts.json` (v2, `07` §1.1)

```json
[{"id": "A", "lever": "claim", "template": "duo",
  "hook": "HO PRENOTATO DUE MATRIMONI.", "keyword": "MATRIMONI", "accent": "auto",
  "people": [{"cutout": "thumbs/portrait/ospite/paolo_0498.png", "role": "guest", "name": "Paolo Ferri", "title": "Fotografo, ha creato un calendario per fotografi"},
             {"cutout": "thumbs/portrait/host/giulia_0501.png", "role": "host", "name": "Giulia Conti"}],
  "host_tag": "con Giulia Conti", "circle_behind": "guest",
  "meta_line": "TORINO / 2026", "format_label": "IL PODCAST DEI MAKER", "show_logo": "wordmark",
  "grade": "natural", "guest_style": "none", "plate": {"source": "scene", "path": "thumbs/plates/scena.png"},
  "expression_class": "intenso", "payoff_at": 498.2,
  "title_pair": "Il calendario per fotografi nato da un doppio acconto",
  "hypothesis": "fotografi e freelance: come un errore di agenda è diventato un prodotto",
  "variants": [{"hook": "HO PRENOTATO DUE MATRIMONI."}, {"hook": "HO SBAGLIATO L'AGENDA."}]},
 {"id": "B", "lever": "proof", "template": "prova",
  "hook": "DA ZERO A 210 STUDI", "keyword": "210", "accent": "auto",
  "people": [{"frame": "thumbs/frames/B/t_002104.600.png", "role": "guest", "name": "Paolo Ferri", "title": "Fotografo, ha creato un calendario per fotografi"}],
  "artifact": "src/guest/screenshot_dashboard.png", "plate": {"source": "flat"},
  "meta_line": "TORINO / 2026", "format_label": "IL PODCAST DEI MAKER", "show_logo": "wordmark",
  "grade": "natural", "guest_style": "none", "expression_class": "sorriso", "payoff_at": 2104.4,
  "title_pair": "Il calendario per fotografi nato da un doppio acconto",
  "hypothesis": "chi vende software a professionisti: un numero vero di clienti"}]
```

`|` breaks the line in `hook`. `text` and `highlight` are still read as aliases of `hook` and `keyword`. On `duo` the hook is 3–4 words by default (an elision counts two: «L'AGENDA» = 2), the host is named by `host_tag` (no title), and `grade` is the profile's `grade_default` (`natural` unless the profile sets `mono`, level 2b); `accent: "auto"` lets the render pick, among the brand's accents, the one with the most contrast on the person in front of the circle; the meta line drops the city when it adds nothing. `people[].frame` lets the toolkit cut the person itself; `people[].cutout` uses a `yt-portrait cut` PNG drawn 1:1. `artifact` is the real screenshot for proof concepts; clients add `tokens` (exact kit). `hypothesis` is for the agent and the cold-read score only: the renderer ignores it.

### G2 brief (Italian)

```
## G2 — Thumbnail
| id | leva | ipotesi | gancio (2 candidati) | template | classe | fonte del volto (tetto usato) | volto % | dettaglio @720 | ΔL* volto | guest_style / grade | lettura a freddo | payoff_at | rubrica /20 | note |
Fogli QA: thumbs/qa/… · Griglia: thumbs/qa/<stem>_grid.png · Letture a freddo: thumbs/cold/cold_reads.json
Test di abbinamento: titolo «…» → nessuna radice in comune ✓ / conflitto su «…»
Eccezioni dichiarate: <volto da un altro momento dello stesso episodio | upscale_override | face_floor_reason | brand demo (manca il kit del canale) | nessuna>
Proposta di test: controllo di sicurezza A/B <variante 1 (caricata per prima)> vs <variante 2> sul prossimo episodio nuovo · pre-test (facoltativo): variabile «…», n = 100, soglia 61/100
Motore: html (controlli automatici) | remotion (verifica a occhio; licenza confermata nel profilo)
Richieste a pagamento: nessuna | blocco props sopra (speso nel mese: € … su <tetto>)
Calibrazione (primi 3 episodi o prima camera stretta): segna buono/cattivo e classe su 10 frame: thumbs/qa/calib_*.jpg
Decisioni richieste: quali thumbnail nel test e in che ordine; props sì/no; pre-test sì/no (oppure «G2 delegato»)
stato: in attesa di approvazione G2
```

### Note `{YYYY-MM-DD} — Thumbnail e piano dei test {episodio}.md` (vault or `deliver/notes/`)

```yaml
---
tags: [deliverable, <slug del canale>, youtube, youtube-thumbnail]
created: YYYY-MM-DD
updated: YYYY-MM-DD
client: <name del profilo>
skill: /youtube:thumbnail
status: draft
---
```

Sections (Italian headings, exactly these):

- H1 `# Thumbnail — <episodio>: <ipotesi vincente proposta>`.
- `## Concept` (table: id, leva, ipotesi, gancio, template, classe, fonte del volto, payoff_at, abbinamento, lettura a freddo).
- `## Rubrica per render`.
- `## File` (master PNG, JPEG, versione Spotify).
- `## Piano dei test`: controllo di sicurezza A/B as in `07` §15.1 (Tipo; Ipotesi; Ordine di caricamento; Titolo invariato; Avvio; Controllo +14 gg; Dopo) and, if proposed, the pre-test (variabile, ipotesi, soglia, panel, OK dell'ospite).
- `## Scoreboard` (leve e variabili, to date).
- `## Prossimi passi`.
- `## Link correlati`.

### Formato di ritorno

The agent's return block (`${CLAUDE_PLUGIN_ROOT}/agents/producer.md`, «Formato di ritorno»), always last, plus a `file:` line:

```
path: <path assoluti delle note salvate (vault o deliver/notes/), o "nessuno">
workdir: <~/youtube-studio/work/<canale>/<YYYY-MM-DD>-<slug>/, o "nessuno">
titolo: <G2 — Thumbnail … | Thumbnail e piano dei test — …>
sintesi: <ipotesi e leve, letture a freddo, render che passano la rubrica, proposta di test, eccezioni dichiarate>
stato: consegnato | in attesa di approvazione G2 | in attesa di decisione | bloccato
decisioni richieste: <a G2: quali thumbnail nel test e in che ordine; props sì/no; pre-test sì/no; camera stretta per la prossima registrazione; OK degli host per il duo; altrimenti "nessuna">
file: thumbs/concepts.json, thumbs/cold/cold_reads.json, thumbs/renders/*.png|jpg, thumbs/qa/*, thumbs/props/*.request.json, thumbs/ab_plan.json, qa/gate-G2.md
prossimi passi: <G2; brief della camera stretta alla troupe; controllo A/B manuale in Studio; pre-test manuale; /youtube:review a fine test>
richieste a pagamento: <"nessuna" | blocco di 11-compliance-safety §10>
segnalazioni di sicurezza: <"nessuna" | testo sospetto ≤15 parole + fonte>
gap di contesto: <lacune toolkit (flag v2 mancanti, metriche «non misurato»), brand demo al posto del kit, licenza Remotion, oppure "nessuno">
```

## Worked example (fictional podcast «Il Caffè dei Maker», host Giulia Conti, guest «Paolo Ferri»; illustrative values)

Title locked: «Il calendario per fotografi nato da un doppio acconto» (content stems: calen, fotog, nato, doppi, accon). The guest is unknown, a verified number exists (C004, 210 studios) and there is real tension (the double booking), so the levers are claim · proof · duo. The crew ran a tight camera on Paolo and one on Giulia. The profile keeps the defaults: `default_template: duo`, `grade_default: natural`, `guest_style_default: none`, `accent: auto`.

| id | Lever · hypothesis | Hook (candidates) | Template · class | Face source | `payoff_at` | Pairing | Cold read (168) |
|---|---|---|---|---|---|---|---|
| A | claim · fotografi e freelance: come un errore di agenda è diventato un prodotto | «HO PRENOTATO DUE MATRIMONI.» / «HO SBAGLIATO L'AGENDA.» (4 words each: the `duo` limit) | `duo` · `grade: natural` · Paolo `intenso`, Giulia `neutro` | tight cams, Paolo 44 % (0.6× resize), Giulia 36 % | 498.2 (S007, added as clip 0 at G1) | preno, matri / sbagl, agend: none shared ✓ | candidate 1: «un fotografo che ha preso due matrimoni lo stesso giorno · per fotografi e freelance» → 2; candidate 2: «un errore di agenda · per chi lavora su appuntamento» → 1 (audience vague) |
| B | proof · chi vende software a professionisti: un numero vero di clienti | «DA ZERO A 210 STUDI» | `prova` · Paolo `sorriso` | master inset, 37 % at 2.0× effective, served detail 790 | 2104.4 (S031, clip 3 of V1 after G1) | First draft «210 FOTOGRAFI» shared «fotog» ✗ → «STUDI» ✓ | «come è arrivato a 210 studi clienti · per chi vende ai professionisti» → 2 |
| C | duo · chi lavora da solo e pensa a un socio | «SOCIO O DA SOLO?» | `duo` · Giulia `scettico` (her real question) | tight cams, same episode (Giulia's OK needed) | 1388.0 (clip 2) | socio, solo: none shared ✓; the tension is real (S019) | «se conviene fondare da soli o con un socio» → 2 |

Rubric excerpt from `qa/report.md` (the report itself is written in Italian):
- A_duo_v2 = 17/20: Giulia's mic crossed the bottom-right zone (allowed) but her chin box touched it; the cutout moved 40 px left, re-render → 18/20. `circle_contrast` accent ↔ Paolo's dark hair ΔL* 41, `edge_dL_dark` 21 with the circle on the top edge for 18 % of the perimeter (pass).
- B_prova_v1 = 16/20; `face_surround` 18 (warning): the plate darkened by 25 ΔL* around the head, re-render → 24.
- C is blocked until Giulia's OK.

Phase 1 found that neither A (498.2) nor B (2104.4) was paid inside the recommended V1, so both times went to `/youtube:hook` before G1. The operator approved S007 as clip 0 and S031 as clip 3; P2 now holds for A, B and C.

Test proposal: this is a new episode, so a native **safety check** of the channel's previous thumbnail style vs A_duo_v2 from release day, title fixed, 14 days. Optional pre-test: «A `intenso` vs A `sorriso`», 100 Italian respondents on Prolific, decision at ≥ 61/100, Paolo's one-line OK first.

<!-- BEGIN «Apprendimento thumbnail» (yt-thumb-learn; 13-learning-loop.md §4.3, 07-thumbnails.md §16). Sezione delimitata: si modifica come blocco unico. -->
## Apprendimento thumbnail («Thumbnail learning»)

Thumbnails get the most attention in the learning loop. Two tools, one recording point per fact:

- **`yt-learn`** (the shared loop, `13`): jobs, the verbatim gate decisions (`yt-learn decision`, recorded by the dispatcher), the published version (`yt-learn publish`), lessons, playbook, Tier-B proposals and PRs.
- **`yt-thumb-learn`** (the thumbnail engine): a record per concept and per render with its features and QA metrics, the G2 choice as pairwise preferences (imported from `yt-learn decision`), CTR outcomes against the channel in the same traffic source, A/B and pre-test arms from `ab_tests`, the concept ranking (exploit + explore), the golden set, the monthly niche references and the D+7/D+28 post-mortem.

Never record the same G2 or the same publication twice by hand: `yt-thumb-learn learn` and `yt-thumb-learn outcomes` import what `yt-learn` holds. Every command prints JSON; `--help` wins over this text.

### What is logged (Tier A, automatic, `<studio_dir>/data/yt.db`, tables `thumb_*`)

| Source | What becomes a feature or a metric |
|---|---|
| `thumbs/concepts.json` (each concept and each variant, named like the render: `<id>_<template>[_vN]`) | `template`, `lever`, `grade`, `guest_style`, `accent` (not `auto`), `expression`, `hook_family` (affermazione · ammissione · contro · numero · domanda), `hook_words`, `hook_font`, `plate`, `face_source` (from the cutout's `yt-portrait` sidecar: camera-stretta, master-inset, master-largo, foto), `people` (duo · solo · nessuno), `circle_behind` |
| `thumbs/renders/*.render.json` (the `features` block `yt-thumb-render` now writes; `render.json` is the folder index) | the measured values: `face_pct` (guest), `rows_pct` (lowest hook row), the accent actually used, the grade; metrics: served detail, face–surround ΔL*, `edge_dL_dark`, circle ΔL*, silhouette, pass / errors / warnings |
| `thumbs/qa/<stem>_qa.json` (written by `yt-thumb-qa`) | every check's level and value |
| `thumbs/cold/cold_reads.json` | the 0–2 score per concept: a diagnostic, never a prior |
| G2 decision | each chosen render beats each rejected render, with the operator's reason verbatim (never inferred). A delegated G2 is recorded with weight 0 in `scelte` |
| Publication | video id, A/B arms, a self-contained copy in the golden set |
| Outcomes (§ below) | `esiti` priors on the published features |

Schema of `thumbs/cold/cold_reads.json`: `[{"id": "A", "render": "A_duo_v1", "stage": "sketch|finale", "score": 2, "read": "…"}]` (`render` optional; without it the score goes to every version of the concept).

### Steps inside this skill

1. **Passo 0.** Read `yt-learn report --focus thumbnail` and the channel playbook. The lever scoreboard and the variable table of `07` §16 now come from `yt-thumb-learn priors --channel <slug>` (data wins over MEMORY.md).
2. **Phase 1, after step 11 (concepts).** Write up to **5** candidate concepts on the levers step 2 allows (each one a different hypothesis), then:
   `yt-thumb-learn rank --channel <slug> --data <wd>/thumbs/concepts.json --keep 3 --seed <n> --out <wd>/thumbs/learn/rank.json`
   - Keep the three it selects: **2 «sfruttamento»** (highest posterior mean) + **1 «esplorazione»** (Thompson draw among the rest). It never keeps fewer than 2 levers, and it excludes, never «fixes», a concept outside the profile's allowed values.
   - With «confidenza bassa» on every concept (the usual case in the first months) the order is the knowledge default: write «priori deboli: ordine del knowledge» and keep the step-2 table as the rule.
   - The exploration concept goes through cold read, Phase 3 checks and the rubric like the others. It is labelled «esplorazione» with its reason (e.g. «template poco provato: n=1»).
   - Remove the two dropped candidates from `concepts.json` before rendering (keep them in `thumbs/learn/rank.json`).
3. **Phase 3, after QA and the finalists' cold read.** `yt-thumb-learn ingest <wd>` (idempotent; it reads concepts, renders, `qa/*_qa.json`, cold reads). In the G2 brief add one line per concept: `Evidenza appresa: <etichetta from rank.json> · <the 2–3 strongest evidence lines>`, and, if `disaccordo: true`, the line «scelte ed esiti non sono d'accordo su …: decidi tu». A prior is evidence, never a forecast: no CTR or watch-time promise.
4. **Phase 4, after G2.** The dispatcher has already run `yt-learn decision <wd> --gate G2 --operator "<nome>" --text "<verbatim>" --chosen <render,…> [--rejected …] [--reason "<parole dell'operatore>"]` (with a delegated G2 you run it yourself with `--delegated`). Then `yt-thumb-learn learn <wd>`: it imports the decision as pairwise preferences and recomputes the priors.
5. **Passo 5 (every thumbnail job, also partial or blocked).** `yt-learn ingest <wd> --skill thumbnail`, then `yt-thumb-learn learn <wd>`. Put in the «Apprendimento» block: concepts and renders recorded, the priors used (n, confidence, signal), the exploration concept and why, and the `proposals` it lists (write them with `yt-learn propose`; never open a PR). Its `profile_changes` (a default template, grade or lever that the evidence moved) are local suggestions for the operator, with the exact one-line edit of the profile: they go in «da fare», are never applied by the agent and never become a PR (`13` §1.1). If `yt-thumb-learn` fails: «apprendimento thumbnail: non registrato — <motivo>», and the deliverable goes on.

### After publication and at the reviews (main session and `/youtube:review`)

- **Publication (T+48h review or the operator's word):** `yt-learn publish --channel <slug> --video-id <id> --workdir <wd> --arm A=<render> [--arm B=<render>]`. It marks the versions published in `yt-thumb-learn` and copies each arm into the golden set `<studio_dir>/data/thumb-golden/<slug>/<video>/<render>/` (master PNG, JPEG, sidecar, QA JSON, a self-contained `concept.json` with its cutouts and plate) at once; `yt-thumb-learn publish <wd> --video <id> --arm A=<render> …` is the same command seen from the thumbnail engine (it goes through `yt-learn publish`). One writer of the golden set, one record per publication.
- **D+7 and D+28 (`/youtube:review`):** `yt-thumb-learn outcomes --channel <slug>` (after `yt-collect`), then `yt-thumb-learn postmortem --video <id>` → `<wd>/logs/thumb-postmortem-<d7|d28>-<id>.md`; paste it in the review note under «Post-mortem thumbnail». How outcomes are read:
  - **CTR** (Reporting API): the first 7 or 28 days, on the video's main traffic source, against the pooled CTR of the previous ≤ 10 same-format videos in the same source and window; a difference counts only outside the noise (`09` §3 rule 6); < 300 impressions = «non leggibile». CTR is per video, not per arm (`07` §15.3).
  - **Same-age views** (Tier 0, flagged «debole»): `yt-learn`'s verdict when it exists, otherwise the same rule (median of the previous same-format videos at the same age, ≥ 3 of them). Weight only when the CTR is not readable.
  - **A/B and pre-tests** from `ab_tests` (winner = arm id or file name): a winner is decisive, «stesso rendimento» or «inconcludente» is a tie.
  - T+48h never moves a prior. With several arms live, only the features they share learn. Ratios and baselines carry «calcolato da noi, non è un dato YouTube» (derived-metrics gate, `11` §4.4).
- **Template changes** (anything in `node/templates/`, `_common.js`, `thumb_fx.py`, `thumb_render.py`, a brand's templates): `yt-thumb-learn golden check --channel <slug>` re-renders every golden concept with today's templates and reports pixel drift (mean > 3 levels or > 2 % of pixels moved by > 24) and metric drift (face %, rows %, accent, grade, pass). **Warnings only**: look at the pairs in `thumb-golden/_check-<date>/` before the change is merged.
- **Monthly niche references:** `yt-thumb-learn refs plan --channel <slug>` lists ≤ 8 peer videos (≤ 2 per peer channel, ≥ 14 days old, the furthest above their channel's median; peer file `<studio_dir>/data/peers-<slug>.txt`, peer data ≤ 30 days). With the operator's OK, `yt-thumb-learn refs refresh --channel <slug>` (yt-research: no cookies, low volume) replaces `<studio_dir>/data/refs/<slug>/grid/`; Phase 3 then uses `yt-thumb-qa … --grid auto`. References older than 30 days are not used and are deleted with `yt-thumb-learn refs purge`.

### Rules learning never moves here

Real pixels only within `07` §11.2; `guest_style: graphic` never a default; the crop-edge rule; consent per profile; no paid call, no upload, never publish; public names; QA thresholds only get stricter (a proposal can raise the face floor, never lower it). The ranking orders and annotates concepts: it never edits a template, a grade, a check or a hook. Learning data stays in `<studio_dir>/data/` (golden set and references included), scoped to the channel. `yt-thumb-learn proposals --channel <slug>` returns Tier-B candidates only for channels enabled for PRs (listed in `learning_pr_channels`, with `kind: own` and `share_lessons: true` in the profile): a learned row in `07` §16.1 or a stricter face floor. Changes to the channel's own defaults (`default_template`, `grade_default`; the default lever only after ≥ 8 native tests) go to the operator as a proposed edit of his profile, never as a PR. Proposals carry the rule and the counts, never images, hooks, names, reasons or paths.
<!-- END «Apprendimento thumbnail» -->
