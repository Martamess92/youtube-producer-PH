# 03 — Story structures: from raw talk to a story people finish

## How the skills use this file

- `youtube:story` reads it in full: structures (§1–§5), archetypes (§6), interview-to-story method (§7), paper and radio edit (§8–§9), solo script mode (§10), claim ledger (§11).
- `youtube:hook` reads §1–§2 and §6 to pick the cold-open entry point and §11 before putting any number in a hook.
- `youtube:edit` reads §8–§9 (paper edit → `edl.json` labels) and §5.2 (Murch priorities) before G1.
- `youtube:shorts` and `youtube:chapters` read §7.3–§7.4 (beat tags, `standalone`, chapter candidates) instead of re-mining the transcript.
- `youtube:review` reads §12 to map retention dips to beats. Method in English; every deliverable in Italian.

Status: written 2026-10-11 from research F5 §3–§4, §7–§8, F1 K-17/K-18/K-27, SYNTHESIS §2.2 and §7A. Evidence labels: [official] [study] [vendor] [anecdotal]. The leaked MrBeast production document is paraphrased only, never quoted or attached, and counts as [anecdotal] (authenticity reported by former staff, not confirmed by the company).

---

## 0. Ground rules (apply before any structure)

1. **Story serves the packaging promise.** Title and thumbnail are locked (or shortlisted) before the story pass. Every structural choice must deliver what the packaging promised inside the first 30 seconds (see `04-hooks-first-30s.md` §0–§1).
2. **Selects only, never invention.** Every beat in a story deliverable comes from a timestamped line in `analysis/transcript.words.json`. If a slot of a structure cannot be filled from the transcript, the agent flags the gap (pick-up question, host voice-over bridge, or a different structure). It never writes the missing beat as if the guest had said it.
3. **Causation over chronology.** A story is a chain of "ma / quindi / perché", not "e poi" (§1). Chronological order is allowed only in the full episode, and even there each chapter must contain causation.
4. **Ethics are structural.** Never splice words to change meaning, never imply a chronology that did not happen, never upgrade a claim type (an estimate stays an estimate), numbers on screen need guest approval (§11).
5. **Italian output, Italian voice.** The channel profile's `voice` (register, public names exactly as written in `voice.public_names`, never a name listed under `never`), its banned words and its `copy_rules`. Default register when the profile says nothing: "tu", direct, concrete, informal but careful.
6. **Fictional examples.** All examples in this file use invented people ("Sara", "Luca") and illustrative numbers. They are patterns, never facts to reuse.

---

## 1. Causation test: "ma / quindi / perché" (Parker & Stone)

Source: Trey Parker and Matt Stone, NYU writing class 2014 (transcript https://speakola.com/arts/matt-stone-trey-parker-nyu-writing-class-2014). Between two beats the connector must be "but" or "therefore" ("because" added by Stone), never "and then". [anecdotal — craft rule from practitioners, no study]

### 1.1 Italian connector map

| Function | Allowed connectors (IT) | Banned between beats |
|---|---|---|
| Conflict / turn | ma, però, solo che, il problema è che, invece | e poi, dopo, a un certo punto (alone), inoltre |
| Consequence | quindi, per questo, così, allora (causal), di conseguenza | e poi, poi, successivamente |
| Cause / motive | perché, visto che, dato che | e poi |

"A un certo punto" is acceptable only when the next clause states a turn ("a un certo punto il cliente più grande ci chiede l'esclusiva, **ma**…").

### 1.2 How to run the test

1. Write each beat as one Italian sentence (subject + verb + concrete object), max 20 words.
2. Write the connector to the next beat in a separate column.
3. Any row whose only honest connector is "e poi" gets one of three treatments: **cut** it, **merge** it into the previous beat as a detail, or **bridge** it (find the hidden cause: why did this happen, what did it cost).
4. Count: in a narrative cut, at least 70% of connectors should be MA or QUINDI. [anecdotal — house target, tune after 5 episodes]

### 1.3 Worked example (fictional)

Weak chain (event list):
> Sara apre il gestionale **e poi** trova i primi clienti **e poi** assume un developer **e poi** alza i prezzi.

Causal chain:
> Sara apre il gestionale per le sue tre palestre, **ma** le altre palestre del quartiere vogliono usarlo, **quindi** lo vende a 19 € al mese; **solo che** a quel prezzo il supporto le mangia le serate, **quindi** alza i prezzi del triplo, **perché** ha capito che chi paga di più chiede meno.

Every beat now opens a question the next beat answers. This is also the skeleton of the bait chain in §5.1.

---

## 2. ABT premise — "E… Ma… Quindi…" (EMQ)

Source: Randy Olson, *Houston, We Have a Narrative* (University of Chicago Press, 2015). Template: And (set-up, agreement) — But (conflict) — Therefore (consequence). [anecdotal — practitioner framework]

Known gap: ABT has no payoff beat (critique in Times Higher Education review, https://www.timeshighereducation.com/books/review-houston-we-have-a-narrative-randy-olson-university-of-chicago-press). House fix: add a fourth clause **"e oggi…"** with a verified result, or use ABT only for the premise and the story spine/circle for the arc.

### 2.1 Template

> «[Chi] faceva/credeva X **e** Y, **ma** Z, **quindi** W — e oggi [risultato verificato].»

### 2.2 Uses (one sentence feeds four deliverables)

| Use | Where | Rule |
|---|---|---|
| Premise of the episode / video | top of the story note | Written before the paper edit; if it cannot be written, the material has no story yet |
| Title-to-intro bridge | `04` §6 Promise → Proof → Plan | The "ma" clause becomes the gap; the "e oggi" clause becomes the proof |
| First line of the description | handed to the operator (or a packaging skill) in the episode package | Rewritten for publication; never copied with banned words |
| Thumbnail lever | handed to `youtube:thumbnail` | The "e oggi" number or the "ma" conflict is a lever candidate |

### 2.3 Examples (fictional)

- Podcast guest: «Sara gestiva la segreteria di tre palestre **e** teneva gli abbonamenti su un foglio di calcolo, **ma** ogni lunedì perdeva mezza giornata a inseguire i rinnovi, **quindi** ha trasformato quel foglio in un gestionale — e oggi lo pagano 140 palestre.»
- Solo talking head: «Molti maker aprono una lista d'attesa **e** aspettano il giorno del lancio, **ma** così scoprono tardi chi pagherebbe davvero, **quindi** io vendo dal primo giorno a chi mi scrive — e da lì decido cosa costruire»
- Client video (generic SaaS): «Il team rilasciava una funzione al mese **e** nessuno la usava, **ma** nessuno aveva chiesto ai clienti perché, **quindi** abbiamo fatto dieci interviste prima della funzione successiva — e l'adozione è salita al [numero verificato]»

---

## 3. Story spine (Kenn Adams)

Source: Kenn Adams' story spine (late 1980s improv exercise, later taught at Pixar), context in NPR interview https://www.npr.org/transcripts/nx-s1-5750619. [anecdotal — practitioner framework]

### 3.1 Italian scaffold

| # | Slot | Italian frame | Beat tag (§7.3) |
|---|---|---|---|
| 1 | Once upon a time | C'era una volta… | PRIMA |
| 2 | Every day | Ogni giorno… | PRIMA |
| 3 | But one day | Ma un giorno… | INNESCO |
| 4–6 | Because of that (×3) | Per questo… / Per questo… / Per questo… | LOTTA, SVOLTA |
| 7 | Until finally | Finché alla fine… | RISULTATO |
| 8 | And ever since | E da allora… | LEZIONE |

### 3.2 Procedure

1. Fill each slot **only with select IDs** (`[S014]`), then paraphrase the slot in one Italian sentence.
2. Empty slot → write `⚠ GAP` and one of: pick-up question for a 5-minute follow-up call; host voice-over bridge (recorded later, labelled as host speech); or switch to another structure.
3. Slots 4–6 must escalate cost or stakes (crazy-progression idea from the MrBeast document: compress the slow years, reach the conflict early). [anecdotal]
4. The spine paragraph (8 sentences) is the north star of the narrative cut and the source of chapter titles.

### 3.3 Example (fictional)

> C'era una volta una segretaria di palestra che teneva tutto su un foglio di calcolo [S003]. Ogni lunedì ricostruiva a mano gli abbonamenti scaduti [S005]. Ma un giorno il titolare le chiede quanto perdevano in rinnovi dimenticati, e il numero la spaventa [S009]. Per questo costruisce di notte una prima versione [S012]. Per questo le palestre vicine glielo chiedono [S018]. Per questo scopre che a 19 € al mese il supporto la sta schiacciando [S024]. Finché alla fine triplica il prezzo e perde solo due clienti su quaranta [S031]. E da allora ripete a tutti che il prezzo è una scelta di chi vuoi servire [S040].

---

## 4. Story circle (Dan Harmon)

Source: Dan Harmon's 8-step simplification of the hero's journey (Channel 101; original wiki unreachable at research time, secondary summary https://industrialscripts.com/dan-harmons-story-circle/). [anecdotal — practitioner framework]

| Step | Harmon | Italian label | In a founder interview | Beat tag |
|---|---|---|---|---|
| 1 | You | Tu, nella zona di comfort | Job, routine, the "normal" | PRIMA |
| 2 | Need | Il bisogno | The itch, the frustration, the trigger | INNESCO |
| 3 | Go | Vai nell'ignoto | Quits, launches, signs the first client | INNESCO / LOTTA |
| 4 | Search | Cerca, adattati | Attempts, failures, pivots | LOTTA |
| 5 | Find | Trova | The insight or the customer that changes things | SVOLTA |
| 6 | Take | Paga il prezzo | What it cost (money, health, a partner, a product) | LOTTA (late) |
| 7 | Return | Torna | Back to stability with a result | RISULTATO |
| 8 | Change | Cambiato | What they now believe and teach | LEZIONE |

When to prefer the circle over the spine: personal documentary-style videos and narrative cuts where step 6 ("paga il prezzo") exists in the transcript. A circle without step 6 reads as a success brochure; if step 6 is missing, ask for it in the pick-up call or use the spine.

---

## 5. Supporting structures and the structure picker

### 5.1 Ira Glass — anecdote, reflection, bait

Source: Ira Glass on storytelling (video series, ~2009; summaries https://www.tubefilter.com/2008/07/30/storytelling-tips-from-ira-glass/). [anecdotal]

- **Anecdote** = a sequence of actions that feels like it is going somewhere. **Reflection** = the line that says why it matters. Alternate them.
- **Bait** = keep raising questions and answer each one later. Every question raised must be answered inside the video.
- Interview application: cut so an action sequence ends on the guest's one-line reflection ("lì ho capito che…"), then a new question arrives via a host line, a 3–6-word text card, or the next guest line.

### 5.2 Walter Murch — Rule of Six (cut priorities)

Source: Walter Murch, *In the Blink of an Eye* (book); summary https://nofilmschool.com/2016/11/6-rules-good-cutting-according-oscar-winning-editor-walter-murch. Weights as Murch states them: emotion 51%, story 23%, rhythm 10%, eye-trace 7%, 2D plane 5%, 3D space 4%. [anecdotal — editor's weighting, not measured]

Use as a tie-breaker: when two cut points compete, keep the one that preserves emotion, then story, then rhythm. Sacrifice from the bottom of the list (continuity of space and screen direction) first.

### 5.3 Misconception-first exposition (Muller)

Source: Derek Muller's PhD research (University of Sydney, 2008), https://openjournals.library.sydney.edu.au/IISME/article/view/6345. Explanatory videos that first voiced common misconceptions and then addressed them produced roughly double the post-test learning gains of clear expository videos, even though students rated them more confusing. [study]

Application: for explainers (solo talking head, client education videos), state the belief the viewer holds, then break it with proof. This is the evidence behind the "credenza → svolta" step in `04` §6.

### 5.4 Setup → tension → payoff loops (Blackman)

Source: George Blackman, scriptwriter (interview summary https://vidpros.com/insiders/george-blackman-youtube-scriptwriting/). [anecdotal]
Each section sets up a question, builds tension, pays it off, and opens the next setup before closing. Retention reading: dips often sit where a tension was resolved without a new setup (see §12).

### 5.5 Expectations vs reality (Kallaway)

Source: Kallaway long-form script method, third-party transcript https://sozai.app/transcript/write-killer-script-keep-viewers-hooked/. [anecdotal]
Viewers stay when the delivered reality beats the expectation set by the packaging. Exceed the title by one specific extra benefit, never by a bigger claim.

### 5.6 Structure picker

| Deliverable | Primary structure | Secondary | Entry point (§7.6) |
|---|---|---|---|
| Podcast full episode (40–60 min, deliverable A) | Chronological chapters, each with causation (§1) | Ira Glass alternation inside chapters | Cold open from the strongest SVOLTA/RISULTATO (`04` §7) |
| Podcast narrative cut (12–20 min, deliverable B — only after at least 3 episodes have data) | Story spine or story circle | Re-engagements at ~3:00 and ~6:00 | In medias res, result-first or myth-first |
| Podcast Shorts (deliverable C) | One mini-ABT per clip | Loop ending (`04` §8) | Strongest line within 2 s |
| Solo talking-head explainer | Misconception-first + value loop per point (§10) | Setup → tension → payoff | Myth-first or payoff-first |
| Talking-head case study | Story spine of the client/project | Claim ledger strict (§11) | Result-first |
| Client video | ABT premise + point order (§10.3) | Brand rules of the client profile | Per client packaging |

---

## 6. First-time founder archetypes (interview guest arcs)

Synthesised from the structures above and the typical founder-interview format (background → idea → launch → growth → numbers, including failures). [anecdotal] Pick the archetype after the selects pass, never before the interview (it would bias the questions).

| # | Archetype (IT) | Arc | Best entry point | Cold-open candidate | Chapter skeleton (curiosity-gap titles) | Risk |
|---|---|---|---|---|---|---|
| 1 | **Da dipendente a builder** | comfort → frustration → side project → first paying user → quitting (the price) → new identity | In medias res on the quitting day | The resignation scene, cut before "e il giorno dopo…" | «Il lavoro che non voleva lasciare» · «Il primo che ha pagato» · «La sera in cui ha scelto» · «Quanto costa davvero il salto» | Sounds like a motivational cliché; keep the money and the doubt |
| 2 | **Il fallimento che ha insegnato** | starts on the shutdown → what was ignored → the next product built differently | Failure-first | The shutdown number or email | «Il prodotto che ha chiuso» · «I segnali ignorati» · «Cosa ha rifatto da zero» · «Il secondo lancio» | Guest may soften the failure; ask for the concrete loss |
| 3 | **Il cliente che ha cambiato tutto** | stuck → one customer conversation → pivot → traction | The conversation as scene | The customer's sentence, cut before the pivot | «Mesi senza trazione» · «Una telefonata» · «Il pivot» · «I primi trenta clienti» | Customer privacy; anonymise unless consent |
| 4 | **Lo strumento giusto al momento giusto** | manual grind → discovers a tool or AI agent → 10× output → new risk | Before/after | The before/after artifact on screen | «Il lavoro a mano» · «La scoperta» · «Dieci volte più veloce» · «Il nuovo problema» | Becomes a tool ad; on channels with a tool-agnostic copy rule, keep written copy tool-agnostic |
| 5 | **Il numero** | a single number defines the story (MRR, churn, 30 clients) | Result-first: open on the number, earn it | The number + "come?" | «Il numero che conta» · «Da zero a dieci» · «Il mese peggiore» · «Come si legge quel numero» | Number not verified → gate (§11) |
| 6 | **Contro il consiglio di tutti** | everyone said X → did Y → proof → nuance on when X is right | Myth-first | The contrarian line | «Quello che gli dicevano tutti» · «Perché ha fatto il contrario» · «La prova» · «Quando invece hanno ragione loro» | Without the nuance chapter it becomes a hot take |

---

## 7. Interview-to-story method (50-minute multicam interviews)

Three deliverables per recording: **A** full episode (chronological, light retention edit, cold open + chapters), **B** narrative cut (non-linear, only after at least 3 episodes have data), **C** Shorts (self-contained clips). Pipeline position: SYNTHESIS §7A stages 0–6, before gate G1.

### 7.1 Phase 0 — Before recording (design for story)

- Interview guide ordered along the guest arc. Two kinds of questions, Mom Test style (past behaviour, not opinions):
  - **Scene questions**: «Raccontami il giorno in cui…», «Dov'eri quando hai capito che…», «Cosa hai fatto subito dopo?», «Chi c'era nella stanza?»
  - **Number questions**: «Quanto fatturavi il mese prima? E il mese dopo?», «Quanti clienti avevi quando hai alzato i prezzi?», «Quante ore a settimana ci mettevi?»
- Agree before recording which numbers the guest will show on screen (dashboards, Stripe, analytics) and capture that B-roll right after the session.
- Record a **30-second wild line** at the end: «In una frase, cosa diresti a chi parte domani?» — guaranteed LEZIONE beat and Shorts closer.
- Capture checklist (profile `recording.capture_checklist`): keep camera ISOs and per-mic files, the tight fixed camera on the guest (`07` §10.6), and a signed release covering image, voice, clips, thumbnails, ads and AI processing. With `consent.release_required: true` (the template default) no release → no processing; a channel whose owner set it to `false` in writing should still collect one.

### 7.2 Phase 1 — Ingest and transcript (toolkit)

```
yt-new --channel <slug> --slug <guest-slug> --src <master> --kind podcast --glossary "<Guest>,<Company>,<Product>"
yt-ingest <workdir> --proxy               # inventory.json (corrupt_spans, loudness, L/R), audio16k/48k.wav (AAC decoder chosen by the toolkit, `05` §11), proxy.mp4
yt-transcribe <workdir> --engine whisper  # transcript.words.json (glossary + disfluent prompt)
yt-speakers <workdir> --num-speakers 3 --map S0="<Host>",S1="<Co-host>",S2="<Guest>"
yt-pack <workdir> --gap 0.5               # analysis/transcript.packed.txt
```

Spot-check before logging: guest name, company and product spelled right (the glossary is mandatory: in a local test without it a company name came out misspelled, SYNTHESIS N12 [anecdotal, n=1]); three random minutes read against audio; speaker labels plausible.

### 7.3 Phase 2 — Logging: beat tags

The agent reads `transcript.packed.txt` (and word JSON for exact times) and tags every answer.

| Tag | Definition | Typical Italian cues (detection hints, not proof) | Keep | Proof need |
|---|---|---|---|---|
| **PRIMA** | Status quo before the story: job, routine, beliefs | «lavoravo in…», «all'epoca», «ogni giorno», «facevo…» | 1–2 concrete details (place, role, a number), never the CV | Rarely |
| **INNESCO** | The trigger: one event with a time and a place | «un giorno», «a un certo punto», «mi chiama…», «è successo che» | The scene, told as a scene | Sometimes (a message, an email) |
| **LOTTA** | Attempts, obstacles, failures, costs | «non funzionava», «abbiamo provato», «ci abbiamo messo», «il problema era» | The cost (time, money, relationships) | Often (numbers of the bad period) |
| **SVOLTA** | Turning point: decision or insight with its reason | «lì ho capito», «a quel punto abbiamo deciso», «la cosa che ha cambiato tutto» | Decision + reason in the guest's words | Sometimes |
| **RISULTATO** | Measurable outcome | numbers, «fatturiamo», «clienti», «utenti», «MRR», «in X mesi» | The number with its period and qualifiers | **Always** → claim ledger row (§11) |
| **LEZIONE** | Reflection or framework the viewer can reuse | «se tornassi indietro», «il consiglio che darei», «la regola che mi sono dato» | The shortest complete version | No |
| **TANGENTE** | Off-arc material | — | Full episode only, if it entertains | — |

Strength scale (per select):
- **3** — would open the cold open or a chapter; quotable without context; clear emotion or number.
- **2** — carries the story; needs the previous line for context.
- **1** — usable connective tissue; cut first when tightening.

### 7.4 Selects table (fields)

One row per kept span. Times are **source** seconds (float), snapped to word boundaries from `transcript.words.json`. The table is an Italian working document; `youtube:story` defines where it is persisted inside the episode workdir (never in the vault).

| Field | Content | Rule |
|---|---|---|
| `id` | S001, S002… | Stable across revisions |
| `src_in` / `src_out` | source seconds | Start at the first kept word, end after the last; padding is added at render (`05` §3) |
| `speaker` | S0/S1/S2 → name from `project.json` `speakers` | Overlap → note it |
| `beat` | PRIMA · INNESCO · LOTTA · SVOLTA · RISULTATO · LEZIONE · TANGENTE | One tag per row |
| `strength` | 1–3 | Scale above |
| `quote` | verbatim line ≤15 words | Copied from the transcript, never polished |
| `emotion` | tensione · vulnerabilità · ironia · orgoglio · sollievo · rabbia · neutra | One word |
| `standalone` | sì/no + why | "sì" only if it opens on a complete thought, contains a turn, and ends on a line (Shorts seed; full rules in `08-shorts-clip-engine.md`) |
| `needs_proof` | sì/no + what | Any abstract claim or number |
| `proof_asset` | path or «da chiedere» | Consent and source in the rights ledger (§11.3) |
| `claim_ids` | C001… | Mandatory for RISULTATO and for any number |
| `uses` | cold-open · chapter-start · short · thumb · takeaway | Hand-offs to `youtube:hook`, `youtube:chapters`, `youtube:shorts`, `youtube:thumbnail` and the episode package (takeaways for the description) |
| `connector_next` | MA · QUINDI · PERCHÉ | Filled during the paper edit (§8) |
| `notes` | free text | e.g. «risata dopo, tenerla», «audio sporco 2 s» |

Example rows (fictional guest «Sara», illustrative times and numbers):

| id | src_in | src_out | speaker | beat | str | quote | emotion | standalone | needs_proof | claim_ids | uses |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S003 | 212.40 | 241.10 | Sara | PRIMA | 2 | «Avevo un foglio Excel con quattrocento righe e lo odiavo» | ironia | no | no | — | — |
| S009 | 598.05 | 633.80 | Sara | INNESCO | 3 | «Mi ha chiesto quanto perdevamo in rinnovi dimenticati» | tensione | sì | sì (stima della guest) | C002 | cold-open, short |
| S024 | 1402.30 | 1449.90 | Sara | LOTTA | 3 | «A diciannove euro il supporto mi mangiava le serate» | vulnerabilità | sì | no | C005 | short, chapter-start |
| S031 | 1820.15 | 1866.00 | Sara | SVOLTA | 3 | «Ho triplicato il prezzo e ne ho persi due su quaranta» | orgoglio | sì | sì (dashboard) | C007, C008 | cold-open, thumb, short |
| S040 | 2950.60 | 2979.20 | Sara | LEZIONE | 3 | «Il prezzo decide chi vuoi servire, non quanto vali» | neutra | sì | no | — | short, takeaway |
| S017 | 1011.00 | 1090.40 | Giulia (host) | TANGENTE | 1 | «Parentesi: anche noi al nostro meetup…» | ironia | no | no | — | — |

### 7.5 Phase 3 — Spine and premise

- Fill the spine (§3) from select IDs only; flag gaps.
- Write the ABT premise (§2) with an «e oggi» clause from a **verified** claim.
- The premise is the north star for the title shortlist (operator or packaging skill), cold open (`04` §7), chapters (`youtube:chapters`) and the description draft.

### 7.6 Phase 4 — Arc and entry point

Default guest arc: **PRIMA → INNESCO → LOTTA → SVOLTA → RISULTATO → LEZIONE**.

| Entry point | Opens on | Then | Use when | Bookend loop closes with |
|---|---|---|---|---|
| **In medias res** | SVOLTA or the low point of LOTTA | Card «Per capire come ci è arrivata, torniamo a…» or host VO | The turning point is a vivid scene | The SVOLTA replayed in context |
| **Result-first** | RISULTATO with the number on screen | «Come?» drives the video | Verified, surprising number | The LEZIONE that explains the number |
| **Myth-first** | A LEZIONE that contradicts common belief | The story proves it | Archetype 6, explainers | The nuance («quando invece hanno ragione loro») |
| **Linear** | PRIMA | Chronology | Full episode only | — |

### 7.7 Phase 5 — Paper edit → see §8. Phase 6 — Radio edit → see §9. Phase 7 — Picture, graphics, sound → `05-editing-rules.md`. Phase 8 — Cold open and host framing → `04-hooks-first-30s.md` §7 (built last, once the payoff location is known).

### 7.8 Phase 9 — Post-publish loop

At T+48h, D+7 and D+28 (`youtube:review`): Studio Intro (0:30) vs typical band, dips mapped to beats (§12), spikes → Shorts candidates and future topics. Log as a new dated note in the channel's deliverables folder (`deliver/notes/`, or the vault folder the profile names; no in-place rewrites).

---

## 8. Paper edit (text-first assembly)

Practice references: paper edits for documentary (https://reduct.video/blog/paper-edits-for-documentary-filmmakers) and text-based editing (https://blog.frame.io/2023/10/16/premiere-pro-text-based-editing/). [anecdotal]

### 8.1 Format (Italian working document)

```
## Atto 1 — PRIMA → INNESCO                         target output 0:45–3:00
[S003 | 00:03:32.4–00:04:01.1 | Sara | PRIMA | ★2]
«Avevo un foglio Excel con quattrocento righe e lo odiavo…»
  ↳ QUINDI
  VISUAL: B-roll foglio di calcolo (proof_asset: da chiedere)
[CARD 3–6 parole] «Poi arriva una domanda»
[S009 | 00:09:58.0–00:10:33.8 | Sara | INNESCO | ★3]
«Mi ha chiesto quanto perdevamo in rinnovi dimenticati…»
  ↳ MA
  LOOP APERTO L1: «quanto perdevano?» → si chiude in S012
```

### 8.2 Rules

1. **Connector between every two selects** (MA / QUINDI / PERCHÉ). If only «e poi» fits: cut, merge or bridge (§1.2).
2. **Host questions** in the narrative cut: remove most of them and replace with (a) a 3–6-word text card question, (b) a short host voice-over bridge recorded later and labelled as host speech, or (c) nothing, if the guest answer stands alone. In the full episode, keep host questions but trim their preambles.
3. **Alternate** anecdote → reflection → new question (§5.1). Two reflections in a row = cut one.
4. **Open-loop tracker** (below). Never close a loop without another one still open; the bookend loop closes only at the payoff; at most 3 loops open at once. [anecdotal — practitioner heuristic]
5. **Re-engagements** (MrBeast document, paraphrased [anecdotal]): narrative cut → a planned re-engagement at ~3:00 and ~6:00 (the near-failure, the first big customer, the number reveal) plus one at the 40–60% sag point (yaxeen practitioner heuristic [anecdotal]). Full episode → a chapter-opening tease every ~8–12 minutes (F4 application of the same idea).
6. **Point order** (solo and narrative explainers): second-best point first, then the best, then the rest descending (Kallaway [anecdotal]). Never a falling start.
7. **Ethics guardrails**: never splice words to change meaning; never imply a chronology that did not happen (use time cards «Sei mesi dopo»); qualifiers travel with numbers; every on-screen number has a verified ledger row.
8. **Time jumps** are explicit: a card or a host line, never a silent reorder that suggests causality the guest did not state.

Open-loop tracker (Italian deliverable table):

| Loop | Aperto a (output) | Chiuso a (output) | Tipo (domanda / numero / storia / promessa) | Chi lo chiude |
|---|---|---|---|---|
| «Quanto perdevano in rinnovi?» | 0:41 | 2:05 | numero | Sara (S012) |
| «Il prezzo triplicato» (bookend) | 0:12 | 14:30 | promessa | Sara (S031) + LEZIONE (S040) |

### 8.3 From paper edit to `edl.json`

The paper edit is the human-readable twin of `edit/edl.json` (schema in the design doc §8.3). Mapping:

| Paper edit element | `edl.json` |
|---|---|
| Select row | one `segments[]` entry: `src`, `in`, `out` (source seconds, padded per `05` §3), `label` |
| Labels | `cold-open-1…4`, `framing`, `ch01-<slug>`, `ch02-<slug>`…, `reengage-1`, `lezione`, `outro` |
| Text card | `overlays[]` entry (rendered card file under `edit/overlays/`, `at` in output seconds) |
| Host VO bridge | a segment from a pick-up source added to `sources` |
| Punch-in on an emphasis line | `zoom` on that segment (`05` §6) |
| Music change at a section handoff | `music[]` entry |

Chapter boundaries go to `edit/chapters.draft.json` (`"timeline": "output"` once the order is final). G1 approves the EDL summary, not the raw JSON: the brief lists kept/cut minutes, the cold-open choice, every reorder, every time card, and every on-screen number with its claim ID.

---

## 9. Radio edit (does it work as audio?)

Goal: prove the story holds without pictures before any picture work. A podcast that fails as audio will not be rescued by B-roll.

Procedure:
1. **Read-through** (agent, before G1): concatenate the verbatim text of the paper edit in order, with connectors and cards inline, and an estimated duration per section (sum of `src_out − src_in`). Read it as a listener: every section must end with a pull into the next; mark dead spots (two LOTTA beats with the same cost, reflections without action, numbers without stakes).
2. **Section timing check** against the target windows: narrative cut → conflict reached by ~1:00, first value by 1–2 minutes, re-engagements near 3:00 and 6:00; full episode → first story beat by ~1:30 (`04` §7).
3. **Cold open last**: only now pick the 2–4 cold-open lines (`04` §7), because only now is the payoff's position known.
4. **Listen pass** (after G1 approval, on the first proxy assembly `yt-edl-render <workdir> --preset proxy`): The operator, or the agent via waveform views, checks audio joins; picture is ignored. Problems found here are fixed in the EDL before the master render.

Dead-spot fixes, in order of preference: cut → reorder → add a card question → host VO bridge. Never "fix" a dead spot with music or effects.

---

## 10. Solo script mode (talking head on a personal channel, client explainers)

### 10.1 Two-column A/V script (Italian deliverable)

Columns: target time | VIDEO (on screen) | AUDIO (spoken) | TESTO/GRAFICA | NOTA RETENTION. Know which minute mark each row serves (MrBeast document idea, paraphrased [anecdotal]).

Example (personal talking-head channel, fictional numbers):

| ⏱ | VIDEO | AUDIO (parlato) | TESTO / GRAFICA | NOTA RETENTION |
|---|---|---|---|---|
| 0:00 | Primo piano, luce buona, nessun logo | «Ho lanciato senza lista d'attesa, e non tornerei indietro» | «Zero lista d'attesa» (1/3 dall'alto, 3 s) | Conferma il click: stesso oggetto della thumbnail |
| 0:04 | Screen recording della dashboard vendite reale | «Di solito si fa il contrario: prima la lista, poi il lancio» | — | Credenza comune |
| 0:10 | Torna su di me, punch-in 1,15 | «Qui ho invertito l'ordine, e il primo cliente è arrivato il secondo giorno» | «Giorno 2» | Svolta + prova |
| 0:18 | B-roll delle chiamate con i primi clienti (volti oscurati) | «Ti mostro come ho trovato i primi dieci. Il secondo passaggio è quello che quasi tutti saltano» | «2 passaggi» | Piano + loop aperto sul passaggio 2 |
| 3:00 | — | — | — | RE-ENGAGEMENT 1: la funzione che volevo io e che i primi clienti hanno bocciato |
| 6:00 | — | — | — | RE-ENGAGEMENT 2: i numeri di vendita dopo il lancio |

Channel style comes from the profile's `copy_rules` (punctuation on titles and on-screen text, tool and product names, slogans): apply them to every card and title, and ask the owner when a rule and the video's subject collide.

### 10.2 Beat sheet

| # | Beat (1 frase) | Tipo (setup / tensione / payoff / riflessione) | Connettore (MA / QUINDI / PERCHÉ) | Loop aperto | Loop chiuso | Visual | Minuto target |
|---|---|---|---|---|---|---|---|

Rule: a connector cell with «e poi» = cut or rewrite the beat.

### 10.3 Value loop per point (Kallaway, paraphrased [anecdotal])

Each point = **contesto** (explain simply) → **applicazione** (a concrete example from a real project) → **cornice** (why it matters for the whole video). Re-hook between points (line bank in `04` §11). Alternate zoomed-out picture and zoomed-in tactics so pace changes without music tricks.

### 10.4 Outro

Recap in one sentence → show that reality exceeded the title's promise → one CTA tied to a pain point already addressed → next-video tease as a fresh gap during the payoff (never "per concludere"). Plan the ending before the middle and close with a callback to the opening image or line (Ed Lawrence, https://creatorscience.com/podcast/ed-lawrence/ [anecdotal]).

---

## 11. Claim ledger and rights ledger

Pattern from Eric Siu's quality gates (https://github.com/ericosiu/ai-marketing-skills, MIT; F1 K-27), rewritten for our pipeline. The ledger is filled during the selects pass and read by every skill that puts words or numbers on screen or in packaging.

### 11.1 Claim ledger fields

| Field | Content |
|---|---|
| `claim_id` | C001… |
| `verbatim` | exact words with the source time (`src_t`) and speaker |
| `type` | **risultato ottenuto** · **stima** · **previsione** · **obiettivo** · **aneddoto** · **opinione** |
| `value` | number + unit + period + scope, e.g. «4.200 € MRR, settembre 2026, solo Italia» |
| `qualifiers` | words that must travel with the number: «circa», «lordo», «nel mese migliore», «prima delle tasse» |
| `proof` | on-screen asset (path), guest confirmation (date), public source (URL), or none |
| `status` | verified · pending · unverifiable |
| `allowed_uses` | parlato nel montato · testo a schermo · titolo · thumbnail · hook Shorts · descrizione |

### 11.2 Rules

1. **Uses by status**: spoken in the cut → any status (it is the guest's own speech, keep qualifiers); on-screen text, title, thumbnail, Shorts hook overlay → **verified only**; on-screen numbers additionally need the guest's approval (agreed before recording, §7.1).
2. **Never upgrade a type**: an estimate is never shown as a result; a target is never shown as achieved; "previsione" never goes in a title.
3. **Qualifiers survive compression**: when a number moves into a cold open, a Short or a card, its qualifier moves with it, or the number does not move (F1 K-18).
4. **No splicing**: two halves of different sentences never form a new claim.
5. **Flag, don't guess**: unfamiliar names, companies and numbers are flagged for confirmation, never auto-corrected from memory.
6. **Gate link**: any hook containing a number without a verified ledger row is auto-rejected by the Hook Rubric (`04` §3.3).

### 11.3 Rights ledger (assets used in the cut)

| Field | Content |
|---|---|
| `asset` | file path or description (screen recording, logo, screenshot, photo, music, SFX) |
| `owner` | guest · channel owner · client · third party |
| `licence / consent` | release date, licence name (CC0, CC-BY, YouTube Audio Library…), or written OK |
| `permitted_uses` | long-form · Shorts · thumbnail · ads · other platforms |
| `notes` | blur needed (customer names, emails), attribution text |

No row → the asset is not used. Music and SFX licensing rules are in `05-editing-rules.md` §14.

---

## 12. Reading retention against beats (for `youtube:review`)

The retention graph is the only honest editorial feedback. Diagnosis table and metric definitions live in `09-analytics-reading.md`; this section only maps shapes to story causes.

| Graph signal | Likely story cause | Story fix (next edit or next episode) |
|---|---|---|
| Dip right after a payoff | Tension resolved without a new setup (§5.4) | Open the next loop before closing this one |
| Dip at a chapter start | Handoff without a pull; chapter title is a label, not a gap | Host signpost before the switch; rename chapter as a question |
| Steady slide through LOTTA | Repeated costs, no escalation | Merge LOTTA beats; escalate stakes (§3.2 rule 3) |
| Spike at a RISULTATO number | Rewatch-worthy proof (or confusion) | Shorts candidate; move earlier or tease in cold open; if confusion, add a card |
| Top moment late (LEZIONE at the end) | Best material buried | Tease the LEZIONE in the cold open or myth-first entry |
| Drop when the host speaks at length | Host monologue in a guest story | Trim host turns to the question |

Small channels: key moments need videos ≥60 s and ≥100 views, data takes 1–2 days (https://support.google.com/youtube/answer/9314415, verified 2026-10-11) [official]. With small-channel view counts, decide on trends over 4+ episodes, not single graphs.

---

## 13. QA checklist for a story deliverable (before G1)

- [ ] ABT premise written, «e oggi» clause from a verified claim.
- [ ] Spine or circle filled from select IDs; every gap flagged with a fix.
- [ ] Connector column has no «e poi».
- [ ] Every RISULTATO and every on-screen number has a verified claim ID with qualifiers.
- [ ] Loop tracker: ≤3 open at once, bookend closes at the payoff, every question raised is answered.
- [ ] Re-engagements placed (narrative cut ~3:00 / ~6:00 / sag; full episode tease every ~8–12 min).
- [ ] Time jumps and reorders are labelled with cards; no implied chronology.
- [ ] Rights ledger complete for every asset in the paper edit.
- [ ] Voice: Italian, the profile's register, channel banned words absent from cards and VO; public names exactly as in `voice.public_names`.
- [ ] Hand-offs listed: cold-open candidates → `youtube:hook`; chapter candidates → `youtube:chapters`; `standalone: sì` rows → `youtube:shorts`; thumb moments → `youtube:thumbnail`; 3–5 takeaways → the episode package.
Full per-deliverable gates and the critic brief: `12-qa-gates.md`.

---

## 14. Sources

- Parker & Stone, NYU 2014 transcript — https://speakola.com/arts/matt-stone-trey-parker-nyu-writing-class-2014 [anecdotal]
- Randy Olson, *Houston, We Have a Narrative* (2015); review — https://www.timeshighereducation.com/books/review-houston-we-have-a-narrative-randy-olson-university-of-chicago-press [anecdotal]
- Kenn Adams story spine, NPR — https://www.npr.org/transcripts/nx-s1-5750619 [anecdotal]
- Dan Harmon story circle (secondary) — https://industrialscripts.com/dan-harmons-story-circle/ [anecdotal]
- Ira Glass on storytelling (summary) — https://www.tubefilter.com/2008/07/30/storytelling-tips-from-ira-glass/ [anecdotal]
- Walter Murch, *In the Blink of an Eye*; summary — https://nofilmschool.com/2016/11/6-rules-good-cutting-according-oscar-winning-editor-walter-murch [anecdotal]
- Muller, misconceptions in science videos — https://openjournals.library.sydney.edu.au/IISME/article/view/6345 [study]
- George Blackman (interview summary) — https://vidpros.com/insiders/george-blackman-youtube-scriptwriting/ [anecdotal]
- Kallaway long-form script (third-party transcript) — https://sozai.app/transcript/write-killer-script-keep-viewers-hooked/ [anecdotal]
- Ed Lawrence × Creator Science ep. 155 — https://creatorscience.com/podcast/ed-lawrence/ [anecdotal]
- MrBeast production document — context only: https://simonwillison.net/2024/Sep/15/how-to-succeed-in-mrbeast-production/ , https://passionfru.it/?p=81151 (paraphrase only, never quoted) [anecdotal]
- Paper edit / text-based editing — https://reduct.video/blog/paper-edits-for-documentary-filmmakers , https://blog.frame.io/2023/10/16/premiere-pro-text-based-editing/ [anecdotal]
- Eric Siu quality gates and ledgers (MIT) — https://github.com/ericosiu/ai-marketing-skills [anecdotal]
- YouTube Help, key moments for audience retention — https://support.google.com/youtube/answer/9314415 (verified 2026-10-11) [official]
- Research (2026-10-11 archive, not distributed: `../research/README.md`): `F5-story-hook.md` §3–§4, §7–§8; `SYNTHESIS.md` §2.2, §7A, §9.
