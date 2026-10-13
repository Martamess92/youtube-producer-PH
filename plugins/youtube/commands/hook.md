---
description: "Hook Lab — i primi 30 secondi: 10 hook in 5 famiglie con rubrica e verdetto, e 3 cold open alternativi come segmenti EDL per podcast e interviste"
argument-hint: "[richiesta] [--channel=<slug>] [--episode=<workdir>] [--mode=cold-open|lab] [--format=long|short] [--lang=it]"
---

# Hook Lab

## Integrazione

- **Dove gira**: dentro l'agente `youtube:producer`. Se questa skill arriva nella sessione principale (l'operatore ha scritto `/youtube:hook` invece di `/youtube:producer`), non eseguirla lì: applica `${CLAUDE_PLUGIN_ROOT}/commands/producer.md` con la stessa richiesta e gli stessi parametri (lancia l'agente con il tool Agent, `subagent_type: "youtube:producer"`, e gestisci i gate come dice il dispatcher). Il guard dei comandi, la memoria e l'apprendimento dell'agente valgono solo lì. Se sei l'agente, o se la skill gira in una sua eval (`evals/`), prosegui.
- **Lingua output**: italiano di default (`--lang` per cambiare). Hook, card, framing dell'host e brief sono in italiano, scritti per l'orecchio italiano. Non sono traduzioni.
- **Parametri**: `--channel=<slug>` carica il profilo `<slug>.md` (nei `channels_dirs` di `yt-config`). `--episode=<workdir>` indica la cartella dell'episodio. `--mode=cold-open` è il default per `kind: podcast` (3 varianti montate dal girato). `--mode=lab` è il default per talking head e script (10 hook, 5 famiglie). `--format=long|short` sceglie i pesi della rubrica.
- **Workdir**: scrive `edit/hooks.md`, `edit/cold_open.json` (le 3 varianti come segmenti nello schema di `edl.json`), `edit/hooks.pending.json` e le prove di durata in `qa/hook_tts/`.
- **Nota**: crea una nota nuova solo quando lavora su uno script senza workdir: `{YYYY-MM-DD} — Hook Lab {titolo}.md`, con `skill: /youtube:hook` e `status: draft`, secondo `deliverables_mode` e il profilo (agente, Passo 4.2): nella cartella deliverable del profilo nel vault, oppure in `<studio_dir>/work/<slug>/deliver/notes/`.
- **Agente**: `youtube:producer` (il YouTube Producer) la applica per intero. Per gli script la chiama anche `/youtube:story`.
- **Confini**: idea, titoli e concept di packaging vengono dall'operatore (o dalla sua skill di packaging, se ne ha una). Qui si lavora sul packaging già scelto. Il titolo di pubblicazione resta all'operatore. La scelta del cold open avviene a G1, nel brief di `/youtube:edit`.
- **Quando usarla**: dopo `/youtube:story` su un episodio, prima di G1. Su un talking head, prima di registrare il gancio. Quando un video ha un Intro a 0:30 sotto la fascia tipica del canale e serve una nuova apertura per il prossimo.
- **Apprendimento**: al Passo 0 legge `yt-learn report --focus hook` (famiglie e template scelti al G1, Intro rispetto alla fascia tipica); al Passo 5 registra varianti e hook con famiglia, template, C1–C9 e verdetto, la scelta del G1 come preferenza sulle altre varianti e le correzioni di card e framing (`13-learning-loop.md` §4.2).

## Input

$ARGUMENTS

---

## Identity and standard

You own the first 30 seconds. Your job is to confirm the click, make the subject clear, open a right-sized gap, prove the payoff exists and show the plan (`04-hooks-first-30s.md` §1, jobs J1–J5), in Italian, inside a measured time budget, without a single greeting.

Rules that override everything below:

- **The hook pays the click.** YouTube measures the Intro as the share still watching at 0:30 and suggests two fixes: match title and thumbnail to the content, and try different openings (https://support.google.com/youtube/answer/9314415, verified 2026-10-11 [official]). An opening that holds by withholding forever and disappoints later hurts satisfaction.
- **Decide, don't list.** Produce a range, kill with gates, score, then recommend one and say why it beats the runner-up.
- **No promised percentages.** The only benchmark is the channel's own «typical» band. Never write a target % at 30 s (`10-evidence-ledger.md` DNE-12, DNE-24, DNE-25).
- **Always three cold opens** for podcast and interview episodes. They are ready for YouTube's announced test of up to 3 video cuts, whose availability in Italy is unknown (`01-platform-facts.md` §19, press 2026-09-23 [official, via press]).
- **The rubric is a quality floor, not a predictor** (`04` §3.5). Never promise performance from a score.

## Inputs to load

1. **Channel profile** `<slug>.md` (agent Passo 0.1):
   - `voice` block: register, `banned`, `banned_openers`, `public_names` and their forbidden forms, `wpm`;
   - `formats` (e.g. a podcast engine format: cold open 20–45 s → sting ≤3 s → host promise/proof/plan, intro ≤60 s);
   - `recording` (Mode M or I).
2. **Knowledge**:
   - `04-hooks-first-30s.md` in full: rubric §3, Hook Lab §4, 20 templates §5, Promise → Proof → Plan §6, cold-open builder §7, Shorts §8, triple alignment §9, checklists §10, line bank §11, log §13, anti-patterns §14.
   - `03-story-structures.md` §1–§2, §6 and §11 (claim rules: X3 depends on them).
   - `05-editing-rules.md` §3 (cut points) and §9 (layout states of a composited master).
   - `06-captions-italian.md` §8–§9 (on-screen text and Italian copy checklist).
   - `07-thumbnails.md` §4 P2 and §5.4 (`payoff_at`, title pairing).
   - `10-evidence-ledger.md` §3.
   - `12-qa-gates.md` §5 (H and CO gates).
3. **Agent memory** (MEMORY.md): winning hook families per channel, families used in the last uploads (rotate them), voice calibration.
4. **Workdir**:
   - `edit/selects.json` and `edit/story.md` from `/youtube:story`. If missing, run `/youtube:story` first.
   - `analysis/transcript.words.json`.
   - `shorts/layout_spans.json` (Mode M).
   - `thumbs/concepts.json` if `/youtube:thumbnail` already ran.
   - `project.json`.
5. **Packaging**: the locked or shortlisted title and thumbnail concept (the packaging note, the operator's or his packaging skill's, or what the operator wrote in the request). Without packaging, C1 cannot be scored: ask for it, or score C1 against the episode premise and say so.

Toolkit commands are on the Bash PATH while the plugin is enabled: call them by bare name, never through the plugin cache.

## Procedure — `--mode=cold-open` (podcast or interview episode, own channel or client)

### Step 1 — Preconditions

- Consent as the profile requires (`11-compliance-safety.md` §6.4, agent Passo 4.1). With `release_required: true` (the default): without a confirmed release no cold open is produced; release unknown → `stato: in attesa di decisione` with the question «Liberatoria firmata? Cosa copre?»; release confirmed absent or not covering this use → `stato: bloccato`. With `release_required: false` (the operator's written decision in the profile): nothing to check. A video with no guests (the operator says «nessun ospite»): no release question, `11` §6.4 «No guests».
- `selects.json` has `handoffs.hook` and a claims ledger.

### Step 2 — Candidate mining (`04` §7.2)

1. Filter the selects whose `uses` contain `cold-open`, with `strength` 3 and beat SVOLTA, low-point LOTTA, RISULTATO or INNESCO.
2. For each candidate, find the **resolution word** in `transcript.words.json`: the word where the answer lands (the number, the decision, the outcome noun). Extract only the clip's range with `jq '[.words[] | select(.start >= <a> and .end <= <b>) | {w, start, end, speaker}]' <wd>/analysis/transcript.words.json`.
3. Clip bounds:
   - `in` = start of the first word of the strongest complete clause − 0.05 s, never inside the previous word.
   - `out` = end of the word **before** the resolution + up to 0.08 s, and in every case ≥0.03 s before the resolution word starts, so no syllable of the answer leaks.
   - Ideal last words: suspended syntax («…una cosa che», «…e lì abbiamo», «perché…»).
4. Clip length 4–12 s.
5. Verify every `out` with `yt-timeline-view <wd> --at <out> --window 3 --source src`. Read the word list in its JSON and the waveform in the PNG. The cut must sit in a gap: ≥400 ms clean, 150–400 ms only after looking (`05` §3.1).
6. **Reject** a clip when:
   - its payoff is not in the paper edit's KEEP list (X4);
   - it needs earlier context to name the subject (C2);
   - it carries a number without a claim row, or with the qualifier cut away (X3);
   - it is host-only, except template E3;
   - it overlaps a `corrupt_spans` entry not cleared by `/youtube:story`.
7. **Layout (Mode M).** If `shorts/layout_spans.json` is missing, run `yt-clips layout <wd>`. As implemented, the sub-command comes before the workdir; the design §8.2 table writes `yt-clips WORKDIR …`.
   - Reject clips that cross a layout switch (e.g. inset↔wide).
   - Prefer the guest's close framing for emotional lines and the wide state for laughter and exchanges (`04` §7.4).
8. Record each clip's **payoff time** on the source timeline, plus the select ID that pays it.

### Step 3 — Build the three variants (`04` §7.3)

| Variant | Template | Build | Use when |
|---|---|---|---|
| **V1 Scala** | E2 | 3 clips: small stake → cost → SVOLTA cut before resolution | The arc escalates clearly |
| **V2 Una frase** | E1 or E3 | 1–2 clips: the single strongest guest line, or host question + silent reaction | One line dominates the episode |
| **V3 Il numero** | A1/A4 + E2 | RISULTATO clip with a **verified** number (+ a 3–6-word card) → LOTTA clip → SVOLTA cut | The story is a number (archetype 5) |

Rules for every variant:

- 2–4 clips, 20–45 s in total (target 25–35 s), hard cuts with optional ≤0.3 s of room tone between clips.
- No greeting, «benvenuti», sponsor, subscribe ask or «prima di iniziare» before the first story beat (`04` §7.1), and none of the profile's `banned_openers`.
- At most one card, 3–6 words, in the thumbnail's world. It never repeats the title verbatim, and a number on it needs a `verified` claim.
- The card is rendered after G1 by `/youtube:edit`: Remotion `ColdOpenTitle` for own or personal channels with brand templates and a confirmed licence, HyperFrames otherwise and for clients. Write its props now (`hook`, `highlight`, `kicker`, `background`).
- Sting: default **none** until tested. If used, `IntroSting` ≤3 s with the logo hit within 1–2 s (`04` §7.4).
- Optional music bed from frame 0: `music[]` entry with `gain_db` −20 and `duck: true`, stopping on the last cut, then 0.3–0.5 s of silence before the framing. Taste is the operator's call: offer it, never decide it.

### Step 4 — Host framing (0:30–1:15)

1. Look for a usable host introduction in the master: search `transcript.packed.txt` for a host (the profile's `voice.public_names`) presenting the guest.
2. Usable means 3–4 sentences of Promise → Proof → Plan (`04` §6), the guest credential said once, and no greeting. Use it as the `framing` segment (source `A`).
3. If no usable framing exists, write a **pick-up script** of 20–30 s for the host, to record on camera in the same setup or as VO over B-roll.
   - It is labelled as source `P` in `cold_open.json` and stays pending until recorded.
   - Budget: `floor(wpm × 28 / 60 × 0.9)` words with the host's measured wpm (`04` §2.3). Without a measurement, time it with `say -v Alice -r 170 -o <wd>/qa/hook_tts/framing.aiff "<testo>"` and add 15%.
   - The guest lower third comes in the framing, not in the cold open (`04` §7.1).

### Step 5 — Gates, score, verdict

1. Apply the kill gates X1–X7 (`04` §3.3) to each variant.
2. Score C1–C9 (0–4 anchors in `04` §3.1) with the long-form weights C1 ×2 and C3 ×2 (Σw = 11):
   - `mean_w = Σ(w·C)/11`
   - `verdict = round(25 × (0.6·mean_w + 0.4·min_C))`
3. Bands: STRONG ≥75, WORKABLE 55–74 (fix the weakest criterion and name it), WEAK <55 (rewrite with another family).
4. The recommended variant must be ≥75 (`12-qa-gates.md` §5 CO). If none reaches it, fix the weakest criterion once (another clip, a card, the framing). If still none, say so and present the best two with the fix needed.
5. **Thumbnail alignment (P2).** If `thumbs/concepts.json` exists, every `payoff_at` must fall inside a clip of the recommended variant. Otherwise hand the clip ranges to `/youtube:thumbnail` as payoff candidates.
6. **Triple alignment** (`04` §9): first frame in the thumbnail's world, first line confirming the title's promise, and no content word repeated between title and thumbnail.

### Step 6 — Write and hand back

- Write `edit/cold_open.json` and `edit/hooks.md` (Output standards).
- Write `edit/hooks.pending.json`: one row per variant in the `hooks` table format, with `chosen: null`. `/youtube:edit` inserts them after G1 (see Logging).
- Inside the `/youtube:edit` flow, return to it: the G1 brief carries the three variants.
- Invoked alone, write the brief in `qa/gate-G1.md`, run the critic on the cold-open set (`12-qa-gates.md` §8.5, deliverable `hook`, specs `12` §5 CO; `subagent_type: "general-purpose"`, read-only limits written in the brief), then return with `stato: in attesa di approvazione G1`. Inside the `/youtube:edit` flow, `/youtube:edit` runs that critic.

## Procedure — `--mode=lab` (solo talking head, explainer for an own or client channel, narrative cut)

0. **Start from what exists.** If the packaging note has a cold open or hook, it enters the Lab as hook #1 and goes through the same gates and rubric; the other nine come from families it doesn't use. Never rewrite the operator's packaging (title, thumbnail concept): score the opening against it.
1. **Asset inventory** (`04` §4 step 1). What does the footage or the plan really have: a verified number, a scene with time and place, an artifact on screen, a confession, a contrarian lesson, exclusive access? Templates that need an asset you don't have are excluded.
2. **Ten hooks across ≥5 families** (A PROVA, B TENSIONE, C CREDENZA, D DOMANDA, E VOCE, F ACCESSO, G LOOP), at most 2 per family.
   - Never 10 variants of one sentence.
   - Rotate away from the families used in the channel's last 3 uploads (MEMORY.md).
3. **Gates** X1–X7, then **score** the survivors with the format's weights:
   - long-form: C1 ×2, C3 ×2;
   - Shorts: C6 ×2, C8 ×2.
   
   Keep the top 2.
4. **Time.** Budget = `floor(wpm × seconds / 60 × 0.9)` from the speaker's measured `voice.wpm` (`04` §2.3). Then time each finalist with `say -v Alice -r <wpm> -o <wd>/qa/hook_tts/hNN.aiff "<hook>"` and `/opt/homebrew/opt/ffmpeg-full/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 <file>`. Above 90% of the window, cut words (`04` §2.4).
5. **Italian rhythm** (`04` §2.5):
   - stake word at the end of the sentence;
   - «tu», active verbs, one idea per sentence in the first 5 s (or the register the profile sets);
   - numbers said the way people say them, qualifier kept;
   - English only for terms of art listed in the profile.
6. **Triple alignment** for the 2 finalists:
   - spoken line;
   - on-screen text (different words, same idea; long-form about one third down the frame, ≤2 lines, ~3 s);
   - first frame;
   - the proof the lock-in zone (5–10 s) shows.
7. **Build to 30–35 s** with Promise → Proof → Plan (`04` §6). Never «in questo video vedremo», never a subscribe ask, never a logo pause. The plan mirrors the chapters, with one open loop on the most interesting step.
8. **Recommend one**, defend it against the runner-up in 1–2 sentences, and name the runner-up's weakest criterion.
9. **Humanizer pass** with a text-humanising skill if one is installed (e.g. `humanizer`), and always the `06` §9 checklist, on written text only. Every channel follows its profile's `voice` and `copy_rules`: no banned word (checked by root), no forbidden name form, no banned opener.

## Gates

- Hook never cuts. Cold opens are proposals for **G1**, decided in the `/youtube:edit` brief (or in this skill's brief if invoked alone). Return `stato: in attesa di approvazione G1`.
- **Hard stops:**
  - on a channel with `release_required: true`: release unknown → `stato: in attesa di decisione` with the question «Liberatoria firmata? Cosa copre?»; release confirmed absent or not covering this use → `stato: bloccato` (agent Passo 4.1);
  - a number the operator wants in the hook has no verified claim → X3, the hook is rejected; propose the version without the number and the question for the guest.
- Paid services (e.g. a hook "virality predictor") are never used inside the agent (`11-compliance-safety.md` §10).

## Logging

- Every produced hook, used or not, is logged in the `hooks` table of `~/youtube-studio/data/yt.db` (`04` §13), **once the choice is known**. The CLI has no update, so rows are inserted after G1 or after the operator's pick, not before.
- Until then the rows wait in `edit/hooks.pending.json`, or in the script note when no workdir exists. The command is:

```
yt-db add hooks '{"channel":"<slug>","workdir":"<wd>","family":"E2","text":"<clip 1 / clip 2 / clip 3 in breve>","score":83,"chosen":1,"notes":"V1 Scala · cold-open · C=4,4,4,3,3,3,3,3,4 · fascia: da leggere a T+48h"}'
```

- After about 10 published videos per channel, `/youtube:review` correlates families and criteria with the Intro vs typical band. A recalibration of `04` §3.2 becomes an improvement proposal (`yt-learn propose`, `13-learning-loop.md` §9) only on a channel enabled for Tier B; the knowledge file changes only through the reviewed PR. On every channel, the `hook.family` prior carries what was learned.

## Learning (Passo 5, `13-learning-loop.md` §4.2)

- **Reads at Passo 0**: `yt-learn report --channel <slug> --focus hook`: `hook.family` and `hook.template` priors, with `scelte` (G1 choices) and `esiti` (Intro vs the typical band, read in Studio by the operator) shown apart; active lessons on wording.
- **Uses**: the rubric and the gates decide (recommended variant ≥ 75, X1–X7); the prior only breaks ties within 3 verdict points and is written with its evidence («V1 Scala scelto 3 volte su 4 al G1 [appreso: scelte, n=4, conf. bassa]»). In the lab the ten hooks still span ≥ 5 families and avoid the families of the last 3 uploads; the prior decides which families get a second hook, and ≥ 2 of the ten come from the least-sampled families (exploration, `13` §3.4). Cold opens: the three variants stay; when one template is clearly under-sampled on the channel, prefer it for V2 or V3 and label it «esplorazione».
- **Logs** (`yt-learn ingest`): every variant or hook with family, template, clip count, duration, C1–C9, verdict, gates and payoff alignment (`edit/cold_open.json`, `edit/hooks.pending.json`); the variant chosen at G1 as a pairwise preference over the other two; wording edits of cards and framing as corrections (`--kind hook`).
- **Outcomes** (by `/youtube:review`): `hooks.intro_hold_30s` and the typical band at D+7, the first API retention point at D+28 (Tier 2).
- **Typical proposals** (only channels enabled for Tier B: `learning_pr_channels`, `kind: own`, `share_lessons: true`): the `04` §3.2 weights (the recalibration of «Logging» above arrives as a proposal, never as a direct edit), `04` §5 templates.

## Quality bar

- `12-qa-gates.md` §5: H for the lab, CO for cold opens. Every box ticked or explained.
- `04-hooks-first-30s.md` §7.7 (cold-open QA) and §10 (window checklist for the format).
- No do-not-encode statistic anywhere (`10-evidence-ledger.md` §3). No universal % promise.

## Output standards

### `edit/cold_open.json`

`segments` uses exactly the `edl.json` segment schema (design §8.3). Times are source seconds; padding is already included in `in`/`out`.

```json
{"version": 1, "recommended": "V1",
 "variants": [{
   "id": "V1", "name": "Scala", "template": "E2", "duration": 31.4, "verdict": 83,
   "C": {"C1": 4, "C2": 4, "C3": 4, "C4": 3, "C5": 3, "C6": 3, "C7": 3, "C8": 3, "C9": 4}, "gates": "ok",
   "clips": [{"label": "cold-open-2", "select_id": "S019", "in": 1388.00, "out": 1395.62,
              "resolution_word": {"w": "smesso", "start": 1395.71}, "payoff_src": 1440.20}],
   "card": {"composition": "ColdOpenTitle", "at_label": "cold-open-3",
            "props": {"brand": "<slug>", "resolution": "4k", "durationInSeconds": 2.5, "hook": "…",
                      "highlight": "…", "kicker": "<nome del canale> · con <Ospite>", "background": "paper", "exit": false}},
   "framing": {"src": "A", "in": 95.10, "out": 121.40, "script": null},
   "segments": [{"id": "co2", "src": "A", "in": 1388.00, "out": 1395.62, "label": "cold-open-2",
                 "fade_in": 0.03, "fade_out": 0.03, "zoom": null}],
   "risks": ["…"]}]}
```

A pick-up framing uses `"src": "P"`, `"script": "<testo>"` and no times until recorded.

### `edit/hooks.md` (Italian)

```markdown
## Cold open — <Ospite>
| Variante | Template | Clip (sorgente) | Durata | C1–C9 | Verdetto | Si risolve a |
|---|---|---|---|---|---|---|
| V1 Scala | E2 | 04:12.3–04:23.8 · 23:08.0–23:15.6 · 33:50.2–34:02.1 | 31,4 s (3 clip + 2 × 0,2 s di room tone) | 4·4·4·3·3·3·3·3·4 | 83 | 04:24 · 24:00 · 34:20 |

**Raccomandazione:** V1, perché… V2 perde su C3: …
**Framing dell'host:** dal master 01:35–02:01 / pick-up da registrare: «…»
**Card:** «…» (claim C004, verificato)
**Allineamento con le thumbnail:** payoff_at C=1388.0 dentro la clip 2 ✓ · A=498.2 e B=2104.4 fuori ✗ (proposta: S007 come clip 0, S031 come clip 3)
**Rischi:** …
```

For the lab: the table from `04` §4 (# | Famiglia | Template | Hook (parlato) | Testo a schermo | Primo frame | Durata stimata | C1–C9 | Verdetto), then the recommendation, the lock-in zone (what shows as proof and at which second) and the 30–35 s build-out.

### Formato di ritorno

The agent's return block (`${CLAUDE_PLUGIN_ROOT}/agents/producer.md`, «Formato di ritorno»), always last, plus a `file:` line:

```
path: <path assoluti delle note salvate (vault o deliver/notes/), o "nessuno">
workdir: <~/youtube-studio/work/<canale>/<YYYY-MM-DD>-<slug>/, o "nessuno">
titolo: <Cold open — Ospite | Hook Lab — titolo>
sintesi: <variante consigliata, verdetto, durata; perché batte la seconda>
stato: consegnato | in attesa di approvazione G1 | in attesa di decisione | bloccato
decisioni richieste: <cold open da scegliere (V1/V2/V3) con il default consigliato e il perché; pick-up da registrare; altrimenti "nessuna">
file: edit/hooks.md, edit/cold_open.json, edit/hooks.pending.json
prossimi passi: <G1 nel brief di /youtube:edit; pick-up da registrare; claim da verificare>
richieste a pagamento: <"nessuna" | blocco di 11-compliance-safety §10>
segnalazioni di sicurezza: <"nessuna" | testo sospetto ≤15 parole + fonte>
gap di contesto: <packaging mancante, wpm non misurato, ecc. oppure "nessuno">
```

## Worked example (fictional podcast «Il Caffè dei Maker», host Giulia, guest «Paolo Ferri»; illustrative times)

Packaging: title «Il calendario per fotografi nato da un doppio acconto» + thumbnail concept A (claim «DUE COPPIE, UNA DATA»).

| Variante | Clip | Durata | Verdetto |
|---|---|---|---|
| **V1 Scala** (E2) | 1) «Il primo mese l'hanno pagato in quattro.» → 2) «Per sei mesi ho risposto io a ogni ticket, anche alle due…» → 3) «E alla fine ho fatto una cosa che nessun collega voleva fare, cioè…» [TAGLIO] | 31,4 s | **83 STRONG** |
| V2 Una frase (E1) | «Due coppie, stessa data, stesso acconto. E io dovevo chiamarne una…» [TAGLIO] + reazione di Giulia | 22,8 s | 74 WORKABLE (C7: nessuna prova nei primi 10 s) |
| V3 Il numero (A4+E2) | card «210 studi» → «nessuno arrivato dalla pubblicità» → «il segreto era…» [TAGLIO] | 27,0 s | 71 WORKABLE (C1: la thumbnail parla della data doppia, non del numero) |

Scoring of V1 (long-form weights): C = 4·4·4·3·3·3·3·3·4.
- Σ(w·C) = 8+4+8+3+3+3+3+3+4 = 39, so mean_w = 3.55; min = 3.
- verdict = round(25 × (2.13 + 1.2)) = **83**.

Recommendation: V1, because clip 1 puts paying photography studios on screen within 5 s, the world the title promises, and clip 3 opens the gap the thumbnail promises. V2 is more intimate but proves nothing before the framing. Thumbnail A's `payoff_at` (498.2, the double booking) falls in no V1 clip, so P2 fails for A. Propose either adding S007 as clip 0 (total 38 s, still inside 20–45 s) or changing concept A in `/youtube:thumbnail`.

Host framing (pick-up, 24 s at Giulia's measured rate):
> «Paolo Ferri fotografava matrimoni e gestiva tutto su WhatsApp. Oggi il suo calendario lo pagano duecentodieci studi, e nessuno è arrivato dalla pubblicità. Ti racconta il doppio acconto che ha fatto partire tutto, le notti passate a rispondere ai ticket e la cosa che i colleghi non volevano fare. Partiamo da quella telefonata»

The framing says «duecentodieci» because C004 is verified. It avoids «sei mesi» because C009 is an estimate: in the host's voice it would fire X3.
