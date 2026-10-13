# 04 — Hooks and the first 30 seconds

## How the skills use this file

- `youtube:hook` reads it in full: Hook Lab (§3–§5), Promise → Proof → Plan (§6), podcast cold-open builder (§7), triple alignment (§9).
- `youtube:story` reads §2 (Italian time budget) and §10 (checklists) when it writes a solo A/V script or places re-engagements.
- `youtube:edit` reads §7.4–§7.6 (cold-open mechanics and EDL labels) and §10 as the retention QA pass before the critic.
- `youtube:shorts` reads §8 (first 1–3 s) and the Shorts row of §3.2 weights; selection rules stay in `08-shorts-clip-engine.md`.
- `youtube:review` and `youtube:research` read §0 (what Studio measures), §12 (teardown) and §13 (hook log). Method in English; every hook, card and brief in Italian.

Status: written 2026-10-11 from F5 §0–§10, F4 §3, V1 K5, V3 K3/K4/K8/K9, SYNTHESIS §2.5, §7A. Evidence labels: [official] [study] [vendor] [anecdotal]. The leaked MrBeast production document is paraphrased only, never quoted or attached, and counts as [anecdotal]. Do-not-encode statistics are listed in `10-evidence-ledger.md`; none of them appears here.

---

## 0. What YouTube measures in the opening (and what it does not)

| Fact | Detail | Source |
|---|---|---|
| **Intro = share still watching after the first 30 s** | Studio "key moments" card. YouTube's suggested fixes for a weak intro are only two: make title and thumbnail match the content, and try different styles in the first 30 s | https://support.google.com/youtube/answer/9314415 — verified 2026-10-11 [official] |
| **Benchmark = your own "typical"** | Studio compares a video with the channel's 10 latest videos of similar length; "See more" compares with YouTube videos of similar length | same page — verified 2026-10-11 [official] |
| **Eligibility** | Key moments only for videos ≥60 s with ≥100 views; data takes 1–2 days to process | same page — verified 2026-10-11 [official] |
| **Spikes and dips** | Spikes = more viewers watching, rewatching or sharing a part (interest or confusion); dips = viewers leaving or skipping there | same page — verified 2026-10-11 [official] |
| **Satisfaction beats clicks** | The recommender learned that a click is not a watch; it uses survey-based valued watch time and recommends misleading or clickbaity videos less | https://blog.youtube/inside-youtube/on-youtubes-recommendation-system/ — verified 2026-10-11 (research pass) [official] |
| **Shorts "Stayed to watch"** | Share of times viewers stayed past the initial seconds of a Short; no seconds threshold is published | https://support.google.com/youtube/answer/12220281 — verified 2026-10-11 [official] |
| **API retention is coarse** | `elapsedVideoTimeRatio` returns 100 points: on a 50-min episode the first point already covers ~30 s | https://developers.google.com/youtube/analytics/dimensions — verified 2026-10-11 (research pass) [official] |
| **Hook A/B by cuts is announced** | YouTube announced testing up to 3 video cuts to compare hooks ("coming soon", press TechCrunch 2026-09-23); availability in Italy unknown | SYNTHESIS §2.5, V3 K8 [official, via press] |

Consequences for the agent:
1. **The 0:30 hook number is read from Studio's Intro card** (manually or read-only browser), never inferred from the API curve. The API curve is for shape and comparisons only.
2. **No universal target.** The only benchmark is the channel's typical band. Even the leaked MrBeast document (paraphrased, [anecdotal]) treats the 0:30 drop as something read against the channel's own «typical» band, not against an absolute target; its figures are do-not-encode (`10-evidence-ledger.md` DNE-32). Never promise a % at 30 s.
3. **The hook must pay the click**, not just hold it: an opening that holds by withholding forever and disappoints later hurts satisfaction.
4. **Always deliver 3 cold-open variants** for podcast episodes (§7), so the native 3-cut test can be used the day it is available.
5. **Small-data rule**: with a few hundred views per episode, many episodes barely qualify for key moments. Decide on trends over 4+ episodes.

---

## 1. The five jobs of the opening

| # | Job | Question the viewer silently asks | Failure looks like |
|---|---|---|---|
| J1 | **Confirm the click** | «È quello che mi aspettavo?» | First frame or line from a different world than the thumbnail |
| J2 | **Make the subject clear** | «Di cosa parla, per chi?» | Two sentences of context before the subject appears |
| J3 | **Open a right-sized gap** | «Cosa succede / come ha fatto?» | Gap closed in the same sentence, or a vague "ti svelo tutto" |
| J4 | **Prove the payoff exists** | «Mi posso fidare?» | Claims without a receipt in the lock-in zone (5–10 s after the hook) |
| J5 | **Show the plan** | «Quanto ci vuole, cosa vedrò?» | No sense of direction; or a plan that spoils the payoff |

Format differences:

| Dimension | Long-form (8–25 min) | Shorts (≤60 s typical, 20–45 s common) | Podcast full episode (40–60 min) |
|---|---|---|---|
| Decision window | 0:00–0:30 (Intro card); minute one loses the most viewers (MrBeast doc [anecdotal]) | Initial seconds ("Stayed to watch", no threshold [official]); practitioners say ~1–3 s [anecdotal] | Same 0:30 card; viewers partly pre-qualified by guest and topic |
| Hook job | J1–J5 in ~35 s | Stop the swipe: visual + text + first words in the same second | Prove the episode contains *the* moment; then frame |
| Device | Promise → Proof → Plan (§6) | Visual-first frame, text hook, withheld payoff, loop (§8) | 20–45 s cold-open montage, 2–4 clips cut before resolution (§7) |
| First real value | Within ~1–2 min (Kallaway [anecdotal]) | Within ~4 s (Kallaway [anecdotal]) | First story beat by ~1:30 [anecdotal] |
| Re-hooks | ~3 and ~6 min + every section handoff (MrBeast doc [anecdotal]) | Foreshadowing mid-Short, twist at the end | Chapter-level teases every ~8–12 min, host signposts |
| Ending | Payoff + callback; never signal the end early | Payoff at peak emotion; last line loops to the first | LEZIONE in the guest's words → next-episode tease → one CTA |

Open loops: write them as **interrupted tasks with a visible finish line** («tra poco vediamo il numero esatto») and as right-sized information gaps (Loewenstein 1994, *Psychological Bulletin* 116(1): curiosity needs some prior knowledge and a gap that looks closable [study]). Do not claim that "the brain can't stand open loops": a 2025 meta-analysis found no reliable memory advantage for unfinished tasks, only a robust tendency to resume them (Ghibellini & Meier, https://doi.org/10.1057/s41599-025-05000-w [study]).

---

## 2. Italian speech time budget

### 2.1 Why English rules don't transfer

Pellegrino, Coupé & Marsico (2011), *Language* 87(3): Italian is spoken at ~6.99 syllables/s but carries less information per syllable (density 0.72 vs English 0.91), so its information rate is lower (0.96 vs 1.08, Vietnamese = 1) (https://www.cambridge.org/core/journals/language/article/abs/crosslanguage-perspective-on-speech-information-rate/73064B3F77E7CE81C42CAB29B4393F80) [study].
Practical reading: the same message takes about **12% more time** in Italian (1.08 / 0.96 ≈ 1.125). An English rule like "the hook fits in 10 s" becomes ~11–11.5 s, and English word-count bands (150 wpm, "9–24 words") are not valid for Italian. **Measure the speaker; never assume.**

### 2.2 Measure each speaker's rate (once per speaker, refresh quarterly)

Input: `analysis/transcript.words.json` from at least 3 real recordings, ≥5 minutes of speech per speaker.

1. Keep the words of one speaker (`speaker == "S1"`, mapped to a name in `project.json`).
2. Split into phrases at gaps ≥0.5 s (same gap as `yt-pack --gap 0.5`) and at speaker changes.
3. Drop phrases under 5 words.
4. Phrase rate = `60 × words / (last.end − first.start)` → take the **median** across phrases (report the IQR too).
5. Store the median as `voice.wpm` in the channel profile (`<slug>.md` in the operator's `channels_dirs`) for the main voice, and per-speaker values in the agent memory (`MEMORY.md`, "voice calibration").

```python
import json, statistics, sys
wd, spk = sys.argv[1], sys.argv[2]                      # workdir, e.g. "S1"
words = json.load(open(f"{wd}/analysis/transcript.words.json"))["words"]
phrases, cur = [], []
for w in words:
    if w.get("speaker") != spk:                         # another speaker = phrase break
        if cur: phrases.append(cur); cur = []
        continue
    if cur and w["start"] - cur[-1]["end"] >= 0.5:      # pause = phrase break
        phrases.append(cur); cur = []
    cur.append(w)
if cur: phrases.append(cur)
rates = [60 * len(p) / (p[-1]["end"] - p[0]["start"])
         for p in phrases if len(p) >= 5 and p[-1]["end"] > p[0]["start"]]
q1, med, q3 = statistics.quantiles(rates, n=4)
print(f"wpm median={med:.0f} IQR={q1:.0f}-{q3:.0f} phrases={len(rates)}")
```

Until a measured value exists, time drafts with §2.4 and add 15% safety. Replace with the measured value after the first transcript.

### 2.3 Word budget per window

`budget_words = floor(wpm × seconds / 60 × 0.9)` — the 0.9 leaves room for emphasis pauses after the stake word.

| Window | at 150 wpm | at 170 wpm | at 190 wpm |
|---|---|---|---|
| Shorts first line (3 s) | 6 | 7 | 8 |
| Long-form hook (0–5 s) | 11 | 12 | 14 |
| Hook + lock-in (0–10 s) | 22 | 25 | 28 |
| Full intro (0–30 s) | 67 | 76 | 85 |

The three wpm columns are illustrative speeds to show the math, not measurements of anyone. Use the speaker's measured `voice.wpm`.

### 2.4 Time a draft before recording (local, free)

macOS ships Italian voices (`say -v '?' | grep it_IT` → Alice, Eddy, Flo, …). `-r` is the rate in words per minute.

```bash
mkdir -p <workdir>/qa/hook_tts
say -v Alice -r <voice.wpm> -o <workdir>/qa/hook_tts/h03.aiff "Testo dell'hook"
/opt/homebrew/opt/ffmpeg-full/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 <workdir>/qa/hook_tts/h03.aiff
```

TTS reads flat, without emphasis pauses: if the TTS duration exceeds 90% of the window, cut words. For real speakers, a phone voice memo of the speaker reading the line beats TTS.

### 2.5 Italian rhythm rules for the first seconds [anecdotal — practitioner craft]

1. **Stake word at the end of the sentence**, where Italian stress falls: «Ha chiuso il primo anno con **trentamila euro**», not «Trentamila euro è quanto ha fatturato…».
2. **Short words, active verbs, "tu".** No nominalisations («la realizzazione dell'implementazione»), no impersonal «si», no passive. Speak to one viewer, never «ragazzi» or «voi tutti».
3. **One idea per sentence** in the first 5 s; staccato first, longer sentences after the lock-in.
4. **Contrast connectors** for the scroll-stop turn: «Ma», «Però», «Solo che», «Il problema?», «E qui si complica».
5. **Snapback openers**, sparingly (they wear out): «In realtà…», «Il punto non è X. È Y», «Non è quello che sembra».
6. **Numbers**: say them the way people say them («quasi tremila», «un cliente su venti»), keep the qualifier («circa», «lordi») if the claim ledger has one (`03` §11).
7. **English terms**: only community terms of art in the channel's mandatory list (`voice.mandatory_when_relevant`, e.g. build in public, MVP); otherwise Italian.
8. **Register follows the profile**: a brand channel is usually more careful than a host's personal channel; the profile's banned words never appear in brand copy.

---

## 3. Hook rubric C1–C9

Synthesised from YouTube Help (click confirmation), Kallaway (subject, stakes, speed, clarity, curiosity, triple alignment, lock-in proof — third-party transcripts), Jenny Hoyos (readability, withheld payoff), Ed Lawrence (why it matters to this viewer), and the weakest-link scoring idea of `youtube-agent-skill` (`hookscore.py`, MIT, reimplemented) [anecdotal].

### 3.1 Criteria and anchors (score each 0–4)

| # | Criterion | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|---|
| C1 | **Click confirmation** — first line/frame vs title + thumbnail | Ignores or contradicts the packaging | Same topic, different promise; or confirms after ~10 s | Confirms, but after ~5 s or only in words | Confirms within 5 s in words and picture, with a different object/number than the thumbnail | First line and first frame deliver the packaging's promise with the same number, object or question |
| C2 | **Clarity** — one listen, one reading | Can't tell what the video is about | Subject clear only after 2+ sentences or behind jargon | Topic clear but needs a second sentence | Subject + outcome in one sentence, one ambiguity (pronoun, jargon) | Subject + outcome obvious in ≤1 sentence, no wordplay, one reading |
| C3 | **Curiosity gap** — right-sized, closable | No gap, or closed in the same sentence | Gap too vague («cambierà tutto») or answer obvious | Generic gap («ti svelo tutto») | Specific gap, answer partly guessable | Specific question the viewer now needs answered and believes this video will answer |
| C4 | **Stakes** — gain/avoid for the viewer, or risk for the character | No reason to care | Vague stakes for the speaker only | Implied benefit | Explicit cost/benefit for a generic viewer | Explicit cost/benefit for *this* viewer, or vivid character stakes with a consequence |
| C5 | **Specificity** — numbers, names, dates, concrete nouns | Vague adjectives («incredibile», «pazzesco») | One concrete noun | One concrete element (number or name or timeframe) | Two concrete elements | Verified number/name/timeframe that is surprising |
| C6 | **Speed-to-value** — word economy vs §2 budget; time to first proof | Over budget, slow build (greeting, context first) | Over budget by ≤20% | Fits budget; first proof later than ~20 s | Fits budget; proof within 10–20 s | Fits budget; first receipt inside the lock-in zone (~5–10 s after the hook) |
| C7 | **Proof / credibility** — trust anchor | Unsupported claim | Proof promised later, no hint of it | Credential stated | Proof told concretely (number + source), not shown | Shown on screen (dashboard, artifact, result) |
| C8 | **Triple alignment** — spoken ↔ on-screen text ↔ visual | Three different messages | Text or visual contradicts the spoken line | Two of three aligned | All three aligned but text repeats the spoken words verbatim, or visual is generic | All three reinforce one idea; text ≠ spoken verbatim |
| C9 | **Voice & brand fit** — register, naturalness, banned words | Banned word, or sounds translated | Wrong register for the channel, calques | Correct but generic | Natural, one stiff phrase | Sounds like the speaker; natural Italian rhythm; stake word at the end |

### 3.2 Verdict formula and weights

```
mean_w  = Σ(w_i × C_i) / Σ w_i          (weighted mean of C1..C9)
min_C   = min(C1..C9)                   (unweighted)
verdict = round(25 × (0.6 × mean_w + 0.4 × min_C))     # 0–100
```

The 40% weight on the minimum encodes "a hook leaks at its weakest property".

| Format | Weights (others = 1) | Σw |
|---|---|---|
| Long-form solo, podcast cold open, narrative cut | C1 ×2, C3 ×2 | 11 |
| Shorts | C6 ×2, C8 ×2 | 11 |

| Band | Verdict | Action |
|---|---|---|
| **STRONG** | ≥75 | Record / cut it |
| **WORKABLE** | 55–74 | Fix the weakest criterion first; name it in the brief |
| **WEAK** | <55 | Rewrite with a different template family (§5) |

### 3.3 Kill gates (auto-reject regardless of score)

| Gate | Condition |
|---|---|
| X1 | C1 = 0 (packaging not confirmed) |
| X2 | C2 = 0 (subject unclear) |
| X3 | A number in the hook's on-screen text or in the host's voice without a **verified** claim-ledger row; a guest's own spoken number in a cold-open clip needs a ledger row and its qualifier inside the clip (`03` §11) |
| X4 | Promise the video does not keep: no payoff timestamp in the final cut for what the hook opens; a "receipt" hook without a real artifact |
| X5 | Guest misrepresentation: spliced words, dropped qualifier, implied chronology |
| X6 | Channel hard rule broken: a banned word of the profile (`voice.banned`, `banned_cta`), a name listed in `voice.public_names.never`, or whatever the profile's `copy_rules` forbid in written hook text (spoken mentions inside content follow the profile too) |
| X7 | Shorts only: frame 0 is black, a logo or a title card |

### 3.4 Worked scoring (long-form weights)

Hook H3 (template A1, solo talking-head channel): C1 4 · C2 3 · C3 4 · C4 3 · C5 4 · C6 3 · C7 2 · C8 3 · C9 4.
- Σ(w×C) = 2×4 + 3 + 2×4 + 3 + 4 + 3 + 2 + 3 + 4 = 38 → mean_w = 38/11 = 3.45; min_C = 2.
- verdict = round(25 × (0.6×3.45 + 0.4×2)) = round(25 × 2.87) = **72 WORKABLE** → weakest: C7 (proof only told).
- Fix: open on the real dashboard (C7 → 4). Σ = 40 → mean_w 3.64; min_C = 3 → round(25 × (2.18 + 1.2)) = **85 STRONG**.

Hook H7 (template D1): C1 2 · C2 4 · C3 1 · C4 2 · C5 1 · C6 4 · C7 0 · C8 2 · C9 3.
- Σ = 4 + 4 + 2 + 2 + 1 + 4 + 0 + 2 + 3 = 22 → mean_w 2.0; min_C = 0 → round(25 × 1.2) = **30 WEAK** → rewrite with another family (no gate fired, but the zero on proof sinks it).

### 3.5 Calibration and honesty

- The rubric is a **quality floor, not a predictor**. The author of `hookscore.py` reports that his heuristic separates bad hooks from real ones but barely separates a creator's hits from misses [anecdotal].
- After ~10 published videos per channel, correlate each criterion with the Studio Intro (0:30) vs typical band (long-form) and Stayed to watch (Shorts); adjust weights in this file with a dated note. Until then, weights stay as above.

---

## 4. Hook Lab procedure (`youtube:hook`)

Inputs: locked or shortlisted packaging (title from the operator or a packaging skill, thumbnail concept from `youtube:thumbnail`), claim ledger, selects or script (`03`), channel profile (voice, banned words, `voice.wpm`), format (long-form / Shorts / podcast).

1. **Asset inventory first.** List what the footage really has: a verified number? a scene with a time and place? an artifact on screen? a confession? a contrarian lesson? exclusive access? Each template in §5 lists what it needs; never force a template the footage can't support.
2. **Write 10 hooks across ≥5 families** (§5, families A–G), at most 2 per family. Never 10 variants of one sentence.
3. **Gates** (§3.3): kill any hook that fires X1–X7.
4. **Score** the survivors (§3.1–§3.2) with the format's weights; keep the top 2.
5. **Time check** (§2.3–§2.4): cut words until each finalist fits the window.
6. **Triple alignment** (§9) for the 2 finalists: spoken line + on-screen text (different words, same idea) + first frame + what the lock-in zone (5–10 s) shows as proof.
7. **Decide, don't list**: recommend one, say why it beats the runner-up in one or two sentences, name the runner-up's weakest criterion.
8. **Podcast episodes**: also build the 3 cold-open variants (§7).
9. **Log** each produced hook in the `hooks` table (§13).

Italian deliverable skeleton (the skill defines the full note):

```markdown
| # | Famiglia | Template | Hook (parlato) | Testo a schermo | Primo frame | Durata stimata | C1–C9 | Verdetto |
|---|---|---|---|---|---|---|---|---|

**Raccomandazione:** H3, perché… Il secondo classificato (H5) perde su C7: …
**Zona di aggancio (5–10 s):** cosa si vede come prova, a che secondo.
```

---

## 5. Cold-open and hook template library (20 templates, 7 families)

Rules for the library:
- Examples are **original, fictional and illustrative**: invented people, illustrative numbers. Every number in a real hook comes from a verified claim-ledger row.
- Pick the template from the footage's real asset. A receipt hook without a receipt is a lie (X4).
- After the hook, the lock-in zone (5–10 s) must deliver proof + plan (long-form) or the host framing (podcast, §7).
- Rotate families across uploads so hooks don't become a recognisable tic. Log the family (§13).
- Spoken script lines use normal punctuation; on-screen text derived from them follows the channel's style (the profile's `copy_rules`).

### Family A — PROVA (show the result or the artifact)

**A1. Il risultato prima (payoff-first)**
- Mechanism: the end state in frame 0, then the question «come?». Use when the result is visual or numeric and verified.
- Needs: artifact or chart + verified claim.
- Example (solo talking head): *[Schermo: grafico iscritti, piatto per mesi poi quasi verticale]* «Per cinque mesi questa linea non si muove. Poi in tre settimane sale più che in tutto l'anno prima. Il prodotto era lo stesso: è cambiato chi ne parlava»
- Failure mode: result shown, «come» never promised → no gap (C3 low).
- Lineage: YouTube Creator Playbook (show the finished result early), Kallaway (proof), MrBeast document (meet the expectation).

**A2. La prova sul tavolo (visual receipt)**
- Mechanism: show the artifact first, explain second.
- Needs: a real artifact, anonymised where needed, with consent.
- Example (solo talking head): *[Schermo: email di disdetta, nomi oscurati]* «Questa è la mail con cui un cliente mi ha lasciato. Sono quattro righe, e nella terza c'è l'errore che ho fatto per due anni senza accorgermene»
- Failure mode: no artifact on screen → X4.
- Lineage: `youtube-agent-skill` "The Receipt" (idea); Kallaway lock-in proof.

**A3. Prima e dopo (before/after)**
- Mechanism: two states, one cut, the middle withheld.
- Example (podcast): «Marzo: un foglio di calcolo e nessun cliente. Settembre: diciotto aziende che pagano ogni mese. Tra le due date non ha aggiunto funzioni. Ne ha tolta una»
- Failure mode: the middle step is obvious → the gap closes by itself.
- Lineage: `youtube-agent-skill` "Before and After"; Kallaway contrast.

**A4. Il numero misterioso (mystery number)**
- Mechanism: a bare number with a known anchor, then the gap.
- Example (podcast): «Undici. Sono le telefonate che ha fatto prima di scrivere una riga di codice. Alla dodicesima ha capito che stava costruendo la cosa sbagliata»
- Failure mode: number without an anchor («Quarantasette.») → noise, not curiosity.
- Lineage: `youtube-agent-skill` "The Statistic"; Loewenstein (the gap needs prior knowledge) [study].

### Family B — TENSIONE (stakes, time, cost)

**B1. Nel mezzo dell'azione (in medias res)**
- Mechanism: start at peak tension, explain later.
- Example (podcast): «Mancano quaranta minuti alla demo, il pagamento di prova non passa e il cliente è già collegato. Da quella sera ha cambiato il modo in cui costruisce ogni MVP»
- Failure mode: action with no consequence for the viewer → C4 low.
- Lineage: YouTube blog 2014 (cold open: jump straight into the action); story circle "Vai".

**B2. La posta in gioco (stakes upfront)**
- Mechanism: name what is at risk, with a deadline.
- Example (podcast): «Si era data sei mesi: se a giugno il progetto non pagava l'affitto, tornava a fare la consulente. Giugno è arrivato, e il conto in banca diceva una cosa precisa»
- Failure mode: stakes invented for drama → X4/X5.
- Lineage: Kallaway stakes; Hoyos personal stake.

**B3. La promessa a tempo (the clock — must be true)**
- Mechanism: a bounded payoff with a time.
- Example (solo talking head): «In otto minuti ti mostro la griglia che uso per dire sì o no a un MVP. La settimana scorsa mi ha fatto bocciare un progetto che mi piaceva molto»
- Failure mode: the section runs longer than promised → satisfaction penalty.
- Lineage: `youtube-agent-skill` "The Clock"; Kallaway "time".

**B4. La confessione (confession)**
- Mechanism: vulnerability as stakes; the viewer avoids the same cost.
- Example (solo talking head): «Ho chiesto a quaranta persone se avrebbero pagato. Trentacinque mi hanno detto di sì. Hanno pagato in due. Il problema non erano loro, erano le mie domande»
- Failure mode: humble-brag disguised as confession → C9 and trust drop.
- Lineage: Ed Lawrence (personal struggle that mirrors the viewer's); story circle "Paga il prezzo".

### Family C — CREDENZA (a belief to break)

**C1. Contro il consiglio di tutti (contrarian claim)**
- Mechanism: context the viewer recognises → turn («ma») → unexpected angle that stays on topic.
- Example (solo talking head): «Ti hanno insegnato che prima serve una lista d'attesa e poi il lancio. Io l'ho saltata, e il primo cliente pagante è arrivato il secondo giorno»
- Failure mode: contrarian without proof → hot take (C7 low).
- Lineage: Kallaway curiosity loop (context lean → interjection → snapback) and long-form intro formula [anecdotal].

**C2. L'errore che fai anche tu (myth-first)**
- Mechanism: voice the viewer's misconception, then break it.
- Example (solo talking head): «Se per trovare il prezzo giusto chiedi ai clienti quanto pagherebbero, stai facendo quello che facevo anch'io. È la domanda che ti dà la risposta più lontana dalla realtà»
- Failure mode: strawman belief nobody holds → C2/C3 low.
- Lineage: Muller misconception research (dialogue videos voicing misconceptions roughly doubled learning gains) [study]; Kallaway "common belief".

**C3. Due strade (versus)**
- Mechanism: two comparable paths, one outcome withheld.
- Example (podcast): «Due founder, la stessa idea, lo stesso mese. Una costruisce in silenzio per sei mesi, l'altra vende una versione grezza dopo dieci giorni. Oggi solo una delle due fattura, e la differenza non sta nel codice»
- Failure mode: the winner is guessable → add the twist («e non è quella che ha venduto prima» only if true).
- Lineage: versus framings (Paddy Galloway, F4 §3.1) [anecdotal]; Kallaway contrast.

### Family D — DOMANDA (the viewer's question or identity)

**D1. La domanda che ti fai (searcher's question)**
- Mechanism: ask exactly what the viewer would type or wonder.
- Example (podcast): «Quanto costa davvero portare un MVP fino al primo cliente pagante? Non il preventivo: tutto quello che esce dal conto tra il primo schizzo e la prima fattura. Lo ricostruiamo voce per voce»
- Failure mode: question answered in the next line → no gap.
- Lineage: YouTube blog 2014 (start with a question); search intent.

**D2. Se sei questa persona (direct address)**
- Mechanism: name the exact viewer in the first words.
- Example (podcast): «Se di giorno lavori per qualcun altro e di sera costruisci una cosa tua, questa puntata è per te. Lui l'ha fatto per due anni, fino alla sera in cui ha dovuto scegliere»
- Failure mode: audience too broad («se ti interessa il business») → C4 low.
- Lineage: `youtube-agent-skill` "Direct Address"; Kallaway (subject = you).

**D3. Il dettaglio fuori posto (odd detail)**
- Mechanism: one concrete anomaly in a familiar context triggers «perché?».
- Example (podcast): «Sul monitor di questa founder c'è un post-it: "non rispondere entro un'ora". Quel foglietto le ha restituito un giorno a settimana, e ha cambiato il modo in cui vende»
- Failure mode: the anomaly is decorative and never explained → X4.
- Lineage: Ira Glass bait; Loewenstein information gap [study].

### Family E — VOCE (the guest's voice; podcast cold opens)

**E1. La frase dell'ospite (guest-quote teaser)**
- Mechanism: one strong line, cut before it resolves, then title or framing.
- Example (podcast): *[Ospite, primo piano]* «Quando il nostro cliente più grande ci ha chiesto l'esclusiva, abbiamo fatto una cosa che non rifarei…» *[TAGLIO secco · 0,3 s di silenzio · inquadratura conduttore]*
- Failure mode: line that needs context to be understood → C2 low.
- Lineage: Diary of a CEO-style cold opens (third-party analyses only) [anecdotal].

**E2. Tre risposte in salita (escalating montage)**
- Mechanism: 3 clips with rising stakes, the last cut mid-sentence.
- Example (podcast): Clip 1 «Il primo mese abbiamo incassato novanta euro.» · Clip 2 «Il quarto mese un'azienda ci ha proposto un contratto annuale.» · Clip 3 «E noi abbiamo detto di no, perché…» *[TAGLIO]*
- Failure mode: flat escalation (three clips at the same stake level).
- Lineage: DOAC analyses [anecdotal]; Ira Glass bait.

**E3. La domanda sospesa (host question + reaction)**
- Mechanism: the host's sharpest question, the guest's silent reaction, cut before the answer.
- Needs: the answer exists later in the cut; a usable reaction shot (Mode M: wide state or PiP; Mode I: guest ISO).
- Example (podcast): *[Host]* «Quindi avete chiuso il prodotto che vi pagava gli stipendi?» *[Ospite: due secondi di silenzio, sorride]* *[TAGLIO]*
- Failure mode: reaction that reads as embarrassment the guest would not approve → X5.
- Lineage: Ira Glass bait; podcast reaction cuts (third-party analyses) [anecdotal].

### Family F — ACCESSO (what only this channel can show)

**F1. Ti porto dentro (behind the scenes)**
- Mechanism: insider access as the hook — for a founder show the "wow factor" is often transparency (real dashboards, real decisions).
- Needs: written consent of whoever owns the material.
- Example (podcast): «Questa è la lavagna della settimana in cui abbiamo deciso cosa togliere dall'MVP di un cliente. Di solito non si fa vedere. Oggi te la leggo tutta, compresi gli errori»
- Failure mode: access promised, then generic footage → X4.
- Lineage: MrBeast document "wow factor" (what only you can do) [anecdotal].

**F2. L'esperimento (I tried it)**
- Mechanism: first-person test with a real cost and a counted result.
- Example (solo talking head): «Per trenta giorni ho risposto a ogni commento entro un'ora e ho segnato tutto in un foglio. La colonna che non mi aspettavo è quella dei clienti»
- Failure mode: experiment not actually run as described → X4.
- Lineage: `youtube-agent-skill` "I Tried It"; challenge formats.

### Family G — LOOP (Shorts)

**G1. Il cerchio (loop opener)**
- Mechanism: the first line continues or answers the last line, inviting a rewatch. Write the last line first.
- Example (podcast Short): prima riga «…ed è per questo che il secondo cliente ha pagato il doppio del primo.» · ultima riga «E il primo? Il primo l'ho trovato con una sola domanda, fatta al momento giusto…» → riparte dall'inizio
- Failure mode: loop that needs the long-form to make sense → fails the stands-alone rule (`08`).
- Lineage: Jenny Hoyos (write hook and last line first, rewatches) [anecdotal]; Shorts loop point.

---

## 6. Promise → Proof → Plan (long-form intro scaffold)

Synthesises Kallaway's intro formula (context → common belief → contrarian → proof + plan), Ed Lawrence's three intro jobs (undo the title's provocation, set up the value, say why it matters to this viewer) and YouTube's own advice (match the packaging) [anecdotal + official].

| Step | Window | Job | Rule |
|---|---|---|---|
| 1. Conferma del click | 0–5 s | Restate the title's promise in different words, ideally showing it | Never read the title aloud verbatim |
| 2. Credenza comune | 5–10 s | What the viewer currently believes | Real belief, not a strawman |
| 3. Svolta | 10–15 s | Why that belief is incomplete or wrong | Contrast connector («ma», «solo che») |
| 4. Prova | 15–25 s | One concrete receipt: number, screen, result, credential | Verified ledger row; show it if possible |
| 5. Piano | 25–35 s | What comes, in order, with one open loop on the most interesting step | Plan mirrors the chapters; exceed the title by one extra benefit |

Rules: total ≤ the 0–30/35 s word budget (§2.3); no «in questo video vedremo»; no subscribe ask; no logo pause; the loop planted in step 5 is the bookend that closes at the payoff.

Example (solo talking head, illustrative):
> «Puoi lanciare un prodotto senza lista d'attesa? Certo. Molti la trattano come il passaggio obbligato prima del lancio. Io l'ho saltata due volte: si vende dal primo giorno a chi scrive. Te lo mostro su tutti e due i lanci, con le dashboard vere, e nel secondo quella scelta mi è costata un mese di lavoro»

Mapping: conferma (the title's question) → credenza (passaggio obbligato) → svolta (saltata due volte) → prova (lanci reali, dashboard a schermo) → piano (due lanci + loop sul secondo).

Example (podcast host framing after a cold open, the host speaking, fictional guest):
> «Sara ha trasformato un foglio di calcolo in un gestionale che oggi pagano centoquaranta palestre. In questa puntata ti racconta come ha trovato le prime dieci senza spendere in pubblicità, perché a un certo punto ha triplicato i prezzi, e la settimana in cui ha quasi venduto tutto. Partiamo dal foglio di calcolo»

Mapping: prova (the number, verified) → promessa + piano (three chapters in order, the last as open loop) → handoff into the first story beat.

---

## 7. Podcast cold-open builder (full interview episodes)

### 7.1 Spec

| Element | Spec | Source |
|---|---|---|
| Total cold open | 20–45 s; default target 25–35 s | F5 §5, §8 [anecdotal] |
| Clips | 2–4, each **cut before its resolution**; the last one is the strongest | DOAC-style analyses [anecdotal] |
| Between clips | Hard cut; optional ≤0.3 s of silence or room tone | house default |
| Brand sting | ≤3 s or none; default **none** until tested on the channel. Branding only if it is itself entertaining and tells new viewers what show this is | YouTube blog 2014 tip "brand with a bang" [official]; F5 [anecdotal] |
| Host framing | Right after the cold open, ~0:30–1:15, 3–4 sentences of Promise → Proof → Plan (§6), guest credential said once | F5 §8 [anecdotal] |
| First story beat | A PRIMA/INNESCO scene by ~1:30 — not small talk | F5 §8 [anecdotal] |
| Forbidden before the first story beat | Greetings, «benvenuti», sponsor, subscribe ask, «prima di iniziare» | F5 §9.3 |
| Guest lower third | Once, during or after the framing (not in the cold open), ~6–8 s | vidpros [vendor] |

### 7.2 Candidate mining (from the selects table, `03` §7.4)

1. Filter selects with `uses` containing `cold-open`, `strength` = 3, beats SVOLTA, low-point LOTTA, RISULTATO, INNESCO.
2. For each candidate, find its **resolution word**: the word where the answer lands (the number, the decision, the outcome noun).
3. Candidate clip = from the first word of the strongest complete clause up to the end of the word **before** the resolution. Ideal last words: suspended syntax («…una cosa che», «…e lì abbiamo», «perché…») or rising intonation.
4. Clip length 4–12 s each.
5. Reject: clips whose payoff is not in the final cut (X4); clips that need earlier context to name the subject (C2); numbers without a ledger row or with the qualifier cut away (X3); host-only clips except template E3.
6. Record each clip's **payoff timestamp** in the output timeline («la clip 2 si risolve a 23:14»): it goes in the G1 brief.

### 7.3 Three variants (always delivered)

| Variant | Template | Build | Use when |
|---|---|---|---|
| **V1 Scala** | E2 escalating montage | 3 clips: small stake → cost → SVOLTA cut before resolution | The arc has clear escalation |
| **V2 Una frase** | E1 or E3 | 1–2 clips: the single strongest guest line (or host question + reaction), cut before resolution | One line dominates the episode |
| **V3 Il numero** | A1/A4 + E2 | RISULTATO clip with the verified number (+ 3–6-word card) → LOTTA clip → SVOLTA cut | The episode's story is a number (archetype 5) |

Score each with the rubric (long-form weights, §3.2) and present all three with the rationale; the operator picks at G1.

### 7.4 Cut mechanics

- **Picture (Mode M, composited master)**: prefer the guest inset state for emotional lines and the wide state for laughter or exchanges; avoid a layout switch inside a clip. Layout facts: `05-editing-rules.md` §9.
- **Audio**: each clip keeps the standard 30 ms fades (technical only); the cut before resolution is otherwise a hard stop. Optional low music bed from frame 0 (`music` entry, `gain_db` −20, `duck: true`) that stops on the last cut; then 0.3–0.5 s of silence before the framing. [anecdotal — house defaults, tune by ear]
- **Text**: at most one 3–6-word card in the cold open (e.g. «Da 19 € a 57 € al mese»), consistent with the thumbnail's world, never repeating the title verbatim. Number cards need verified claims.
- **Sting** (if used): the `IntroSting` Remotion composition (`yt-remotion render IntroSting --props <file> --out edit/overlays/sting.mov --codec prores`) placed in `overlays[]` at the start of the framing segment; logo hit within 1–2 s, total ≤3 s (iart-ai intro craft [anecdotal]). A text card in the cold open uses `ColdOpenTitle`.
- **Pick-up**: if the master has no usable host framing, the agent writes a 20–30 s framing script for the host to record (on camera in the same setup, or as VO over B-roll). It is labelled as a pick-up source in `edl.json`.

### 7.5 EDL output (labels the edit skill expects)

Fictional example, V1 Scala (source seconds):

```json
"segments": [
  {"id": "co1", "src": "A", "in": 1402.30, "out": 1409.85, "label": "cold-open-1", "fade_in": 0.03, "fade_out": 0.03, "zoom": null},
  {"id": "co2", "src": "A", "in": 1835.10, "out": 1843.40, "label": "cold-open-2", "fade_in": 0.03, "fade_out": 0.03, "zoom": null},
  {"id": "co3", "src": "A", "in": 1820.15, "out": 1829.60, "label": "cold-open-3", "fade_in": 0.03, "fade_out": 0.03, "zoom": null},
  {"id": "fr1", "src": "P", "in": 3.20, "out": 31.70, "label": "framing", "fade_in": 0.03, "fade_out": 0.03, "zoom": null},
  {"id": "c01", "src": "A", "in": 212.40, "out": 641.00, "label": "ch01-foglio-di-calcolo", "fade_in": 0.03, "fade_out": 0.03, "zoom": null}
]
```

(`P` = pick-up recording added to `sources`.) Variants V2 and V3 are delivered as alternative segment lists in the G1 brief; only the chosen one goes into `edit/edl.json`.

### 7.6 The first 90 seconds of a podcast episode (target layout)

| Output time | Content |
|---|---|
| 0:00–0:30 | Cold open (V1/V2/V3) |
| 0:30–0:31 | Silence / sting overlay (optional) |
| 0:31–1:00 | Host framing: Promise → Proof → Plan; guest lower third |
| 1:00–1:30 | First story scene (PRIMA or INNESCO), chapter 1 starts |

### 7.7 Cold-open QA (before G1)

- [ ] 3 variants, each 20–45 s, each scored; chosen one ≥75 (STRONG).
- [ ] Every clip is cut before resolution and its payoff timestamp exists in the cut.
- [ ] No greeting, no channel intro, no subscribe ask before the first story beat (≤ ~1:30).
- [ ] Card text matches the thumbnail's world (C1) and passes X3.
- [ ] Qualifiers intact; no splicing (X5).
- [ ] Guest credential appears once, in the framing.

---

## 8. Shorts: the first 1–3 seconds

Selection, windowing, scoring and dedupe are in `08-shorts-clip-engine.md`. This section covers only the opening.

1. **Frame 0 moves.** A face mid-gesture or a recognisable visual; never a black frame, logo or title card (X7). Trim to the first frame with motion.
2. **Text hook from frame 0 to ~3 s**: ≤10 words, Italian, a concrete specific (number, name, claim) (openshorts rule via V3 K9 [anecdotal]); placed in the upper part of the safe zone (`06-captions-italian.md` §7).
3. **The spoken first line completes subject + stakes by ~3 s.** YouTube measures whether viewers stay past the initial seconds (official, no threshold); practitioners treat the first 1–3 s as the decision [anecdotal].
4. **Two-second rule**: start on the strongest line, not on the host's question (openshorts [anecdotal]).
5. **New first line**: allowed only if it is the guest's own words from the same answer, moved in front with a visible cut, without changing meaning (X5). Record it as `hook_text` in `shorts/scores.json`.
6. **No host intro**, no «ciao», no «in questa puntata».
7. **Withhold the payoff to the end**; a foreshadowing line mid-clip; end on the peak emotion; last line loops to the first when possible (G1). Write the hook and the last line first (Hoyos [anecdotal]).
8. **Captions burned from frame 0** (`06`); simple words (Hoyos reports Shorts readability around a 5th-grade level [anecdotal]).
9. **Triple alignment in the first second**: spoken line, text hook and visual say one idea (§9.2).
10. **Length**: default 20–60 s for podcast clips (V3 K9 [anecdotal]); Shorts can run up to 3 minutes (https://support.google.com/youtube/answer/15424877, verified 2026-10-11 research pass [official]) — length is a test variable.
11. Score with Shorts weights (C6 ×2, C8 ×2).

Worked example (podcast Short, fictional guest):
- Frame 0: guest inset, hand mid-gesture. Text hook (≤10 words): «Prezzi ×3. Quanti clienti ha perso?»
- 0:00–0:03 spoken: «Quando ho triplicato il prezzo, mi aspettavo di perdere metà dei clienti.»
- 0:03–0:25: the fear, the email to customers, one reaction (foreshadow: «e la prima risposta che arriva è di quello che pagava di più»).
- Last 2 s: «Ne ho persi due.» → cut on the smile; no «iscriviti» tail.

---

## 9. Triple alignment

### 9.1 Packaging triangle: title — thumbnail — first line/frame

| Rule | Check | Source |
|---|---|---|
| Thumbnail shows, title tells | They create one gap together; they never say the same thing | packaging practice (`07` P1) |
| No repeated content words between title and thumbnail text | Compare lemmas; articles/prepositions don't count | SYNTHESIS §7A stage 5 |
| First frame belongs to the thumbnail's world | Same person, place or object visible in 0–2 s | F5 checklist; MrBeast doc (meet the expectation) [anecdotal] |
| First spoken line confirms the promise | Same number, object or question as the packaging (C1 = 4) | YouTube Help (match title/thumbnail to content) [official] |
| Thumbnail claim confirmed in 0–30 s; full payoff exists in the cut | `payoff_at` in `thumbs/concepts.json` points to a real moment of the cut | SYNTHESIS §7A; X4 |
| A/B variants must not over-promise | Test & Compare picks the winner on watch time, not CTR | https://support.google.com/youtube/answer/13861714 — verified 2026-10-11 (research pass) [official] |
| Short → long-form bridge | The long-form opens with exactly what the Short promised within 5–10 s | https://blog.youtube/creator-and-artist-stories/youtube-related-videos-traffic-guide/ — verified 2026-10-11 (research pass) [official] |

### 9.2 Inside the hook: spoken — on-screen text — visual

- Same idea, different words: the text hook is never the spoken line verbatim.
- Text hook placement for long-form: about one third down the frame, ≤2 lines, ~3 s on screen (Kallaway [anecdotal]). Shorts: safe zone in `06` §7.
- Visual hook families (Kallaway [anecdotal]): text/graphic overlay, pattern interrupt, subject motion, visual effect, visual selection (an inherently interesting shot). Pick one per hook.

### 9.3 Worked check (fictional)

| Element | Podcast episode (Sara) | Solo talking-head video |
|---|---|---|
| Title | «Ha triplicato i prezzi e ha perso solo due clienti \| Sara Ferri» | «Ho lanciato senza lista d'attesa» |
| Thumbnail text | «×3» + Sara with the dashboard | «GIORNO 2» + the presenter pointing at the sales dashboard |
| First frame | Sara inset, mid-sentence, dashboard PiP | The real sales dashboard on screen |
| First line | «Quando ho triplicato il prezzo, mi aspettavo di perdere metà dei clienti» | «Ho lanciato senza lista d'attesa, e non tornerei indietro» |
| Repeated content words title ↔ thumbnail | none ✔ | none ✔ |
| Verdict | C1 = 4, C8 = 4 | C1 = 4, C8 = 3 (text close to the title idea; rewrite to «primo cliente: giorno 2») |

Note: the channel's title format (e.g. arc | guest name) and character limits come from the profile's `copy_rules`; this table only checks alignment.

---

## 10. Timestamped retention checklists

Practitioner windows; none is a YouTube rule except the 0:30 Intro definition. Derive the real cadence from the channel's own dips (`09-analytics-reading.md`). [anecdotal unless marked]

### 10.1 Long-form (8–25 min): solo talking-head videos, podcast narrative cuts

| Window | Must be true | How | Fail signal in Studio | Source |
|---|---|---|---|---|
| **0–5 s** | First frame = packaging world; good light and audio from frame 0; no logo, no greeting; first line confirms the title; text hook on screen (≤2 lines, ~3 s); a visual change within 5 s | Templates A1, B1, A2; punch-in or cut | Intro below typical band | YouTube Help [official]; MrBeast doc (lighting and expectations at the start) [anecdotal]; Kallaway |
| **5–30 s** | Lock-in: proof + plan; one bookend loop planted; subject and stakes unambiguous; no subscribe ask, no sponsor; within the Italian budget (§2) | Promise → Proof → Plan (§6); loop tracker (`03` §8.2) | Intro below typical band | Kallaway lock-in; YouTube Help [official] |
| **30–60 s** | Start *showing* (execution), not describing; first value delivered or visibly underway; credential lower third if needed | Crazy progression (compress setup); B-roll | Steeper-than-typical drop 0:30–1:00 | MrBeast doc minutes 1–3 [anecdotal]; Kallaway (value within 1–2 min) |
| **1–3 min** | Hype has become execution; second-best point first, then the best | Point order (`03` §8.2 rule 6) | Cliff 1:00–3:00 | MrBeast doc; Kallaway |
| **~2–3 min dip** | A named re-engagement at a timestamp: new loop, raised stakes, surprising fact, or a spectacle that fits the story | Re-hook lines (§11); visual pattern interrupt | Dip around 2–3 min | MrBeast doc 3-min re-engagement [anecdotal] |
| **Section handoffs** | Close one loop only after opening the next; connector MA/QUINDI/PERCHÉ; chapter titled as a gap; zoom-out or music change marks the shift | Beat sheet, chapter cards | Dips at chapter starts | Parker & Stone; Blackman; yaxeen [anecdotal] |
| **~6 min / 40–60% sag** | Second re-engagement: a bigger reveal that needs some explanation; restate the core promise with fresh urgency | Number reveal, low point, twist | Steady slide mid-video | MrBeast doc 6-min; yaxeen sag point [anecdotal] |
| **Back half** | Longer explanations allowed, but no flat stretch over ~2–3 min without a new question; no «per concludere» | Callbacks to earlier loops | Early end drop | MrBeast doc back half [anecdotal] |
| **Last 10% / outro** | Bookend loop closes explicitly; callback to the opening; one CTA tied to the value just given; next-video tease as a fresh gap during the payoff; end screen in the last 5–20 s | Native CTA; end-screen plate | Drop before the payoff | Ed Lawrence; Kallaway; end screens https://support.google.com/youtube/answer/6388789 (verified 2026-10-11 research pass) [official] |

### 10.2 Shorts (20–45 s)

| Window | Must be true |
|---|---|
| 0–1 s | Visual hook already moving; text hook visible; no black frame or logo (X7) |
| 1–3 s | Spoken first line completes subject + stakes |
| 3–15 s | One turn (ma / quindi); payoff withheld; a foreshadowing line |
| 15–40 s | Escalation; plain words; captions ≤2 lines inside the safe zone (`06`) |
| Last 2 s | Payoff at peak emotion; last line loops into the first; no «iscriviti» tail that kills the loop; dead frames trimmed |

### 10.3 Podcast full episode (40–60 min)

| Window | Must be true |
|---|---|
| 0:00–0:45 | Cold open: 2–4 clips cut before resolution (§7); no greetings |
| ~0:30–1:15 | ≤3 s sting or none; host Promise → Proof → Plan; guest credential once |
| 1:15–3:00 | First story scene (PRIMA/INNESCO), not small talk |
| Every chapter (5–10 min) | Curiosity-gap chapter title; host signpost before the switch; at least one number or proof on screen per chapter |
| Every ~8–12 min | A chapter-opening tease of something coming later («tra il minuto 20 e il 25 racconta come ha trovato i primi trenta clienti» — said by the host in natural words) |
| ~Midpoint | Tease of the most valuable segment if it comes late; restate the episode's main question |
| Last 90 s | LEZIONE in the guest's words → next-episode tease → one CTA (never one of the profile's `banned_cta`) |

---

## 11. Re-hook line bank and outro rules

Original Italian lines, to adapt (never paste the same line in consecutive videos). Lines in the host's voice use the public names of the profile when names are needed.

Section handoffs and dips:
- «Fin qui sembra una storia lineare. Non lo è.»
- «Questo è il lato facile. Il difficile arriva il mese dopo.»
- «Tieni a mente questa frase: tra poco torna.»
- «Il secondo passaggio è quello che gli è costato di più.»
- «Sembra un dettaglio. È il motivo per cui oggi fattura.»
- «Ti ho promesso un numero: ci siamo quasi.»
- «Prima di arrivarci, devi vedere cosa è successo dopo il lancio.»
- «Ok, ma in pratica come si fa? Te lo faccio vedere.»
- «Fermati un attimo su questo numero.»
- «Ma c'è un problema.»
- Host signpost (podcast): «Tra poco ci racconta il giorno in cui ha quasi chiuso. Prima però torniamo a quando…»

Outro rules:
1. **Never signal the end** before the payoff. Banned until the last ~15 s: «per concludere», «prima di salutarci», «siamo arrivati alla fine», «ultima cosa e poi vi lascio», «grazie per essere stati con noi».
2. **Callback** to the opening image or line («Ricordi il foglio di calcolo dell'inizio? Eccolo oggi»).
3. **One CTA**, tied to the value just given, specific and not pushy (never one of the profile's `banned_cta`).
4. **Next-video tease as a fresh gap**, inside the payoff, not after it («Nella prossima puntata c'è chi ha fatto l'esatto contrario, e gli è andata bene lo stesso»).
5. **End screen** in the last 5–20 s (video ≥25 s, ≤4 elements) [official, URL in §10.1]; the plate layout is in `05` §13.

---

## 12. Teardown of reference openings (`youtube:research --mode=teardown`)

Purpose: build evidence on Italian podcast and creator openings (no written analyses exist; SYNTHESIS §1.1).

1. Captions first, low volume: `yt-research captions <URL…> --out <dir>` (guardrails: no cookies, sleeps; policy in `11-compliance-safety.md`).
2. Frames of 0:00–0:30 (or 0:00–1:00) with the `/watch` plugin, local engine.
3. Code each opening in a table: family (§5), seconds to click confirmation, seconds to first proof, words in the first 5 s, speaker wpm, cuts in the first 30 s (ffmpeg `scdet` on a proxy), sting length, greeting yes/no.
4. Store as a research note; compare with the channel's own hook log (§13). Patterns need ≥5 examples before they become advice.

---

## 13. Hook log and calibration

Every produced hook (used or not) is logged in the `hooks` table of `<studio_dir>/data/yt.db` (design doc §8.4). Columns as implemented (2026-10-11): `channel`, `video_id`, `workdir`, `family`, `text`, `score` (verdict 0–100), `chosen`, `intro_hold_30s` (filled after publish from Studio's Intro card), `notes`, `created_at`. Put what has no column of its own in `notes` as compact text: template ID, format, C1–C9 (e.g. `A1 · long · C=4,3,4,3,4,3,2,3,4`), typical band (sopra / in linea / sotto), Stayed to watch for Shorts. The winning family per channel also goes into the agent's `MEMORY.md` ("winning hook families").

Recalibration: after ~10 published videos per channel, compare chosen hooks' families and criteria with intro vs typical; adjust §3.2 weights with a dated note; keep the gates unchanged.

---

## 14. Anti-patterns

- **Throat-clearing** (Italian): «Ciao a tutti e bentornati sul canale», «Benvenuti a un nuovo episodio di…», «Prima di iniziare…», «Allora, oggi parliamo di…», «Non dimenticate di iscrivervi», «Come vi avevo promesso…», «In questo video vedremo…», «Senza perdere altro tempo…».
- **Empty superlatives**: «ospite d'eccezione», «episodio pazzesco», «incredibile», «imperdibile».
- **Plural address** («ragazzi», «voi») instead of «tu».
- **Reading the title aloud** as the first line (C8 ≤ 3, wasted seconds).
- **Receipt without a receipt**, clock not respected, stakes invented (X4).
- **Same family every week** → recognisable tic; rotate (§5).
- **Hyper-cut editing on reflective interviews**: MrBeast publicly said in 2024 that slowing his edits helped, and the Washington Post framed it as a possible end of "retention editing" with cuts every ~1.3–1.5 s (https://www.washingtonpost.com/technology/2024/03/30/video-editing-mrbeast-retention/) [anecdotal]. For interview podcasts: remove dead air and throat-clearing, don't impose TikTok cadence.
- **Universal % promises** ("terrai il 70% a 30 secondi"): forbidden; see `10-evidence-ledger.md`.

---

## 15. Sources

Official (all verified 2026-10-11; "research pass" = verified by the research agents that day):
- Key moments for audience retention — https://support.google.com/youtube/answer/9314415
- Content performance / Stayed to watch — https://support.google.com/youtube/answer/12220281
- Recommendation system and satisfaction — https://blog.youtube/inside-youtube/on-youtubes-recommendation-system/ (research pass)
- Creator Playbook, first 15 seconds — https://blog.youtube/creator-and-artist-stories/youtube-creator-playbook-tips-first-15/ (research pass)
- Four tips to hook viewers (2014) — https://blog.youtube/creator-and-artist-stories/four-tips-to-hook-your-viewers-on/ (research pass)
- Test & Compare (A/B) — https://support.google.com/youtube/answer/13861714 (research pass)
- Related-video traffic guide (Shorts → long-form) — https://blog.youtube/creator-and-artist-stories/youtube-related-videos-traffic-guide/ (research pass)
- End screens — https://support.google.com/youtube/answer/6388789 (research pass)
- Shorts length — https://support.google.com/youtube/answer/15424877 (research pass)
- Analytics dimensions (`elapsedVideoTimeRatio`) — https://developers.google.com/youtube/analytics/dimensions (research pass)

Studies:
- Pellegrino, Coupé & Marsico 2011 — https://www.cambridge.org/core/journals/language/article/abs/crosslanguage-perspective-on-speech-information-rate/73064B3F77E7CE81C42CAB29B4393F80
- Loewenstein 1994, *Psychological Bulletin* 116(1) (secondary access https://www.pbs.org/wgbh/nova/article/how-to-stimulate-curiosity/)
- Ghibellini & Meier 2025 — https://doi.org/10.1057/s41599-025-05000-w
- Muller (misconceptions) — https://openjournals.library.sydney.edu.au/IISME/article/view/6345

Practitioner [anecdotal] / vendor:
- Kallaway (third-party transcripts) — https://sozai.app/transcript/psychology-killer-hooks/ , https://sozai.app/transcript/only-6-words-hook-viewer/ , https://sozai.app/transcript/write-killer-script-keep-viewers-hooked/ , https://youtubesummary.com/summary/LmXpbP7dD48
- Jenny Hoyos × Creator Science — https://www.youtube.com/watch?v=As7abwNhG7Y
- Ed Lawrence × Creator Science ep. 155 — https://creatorscience.com/podcast/ed-lawrence/
- MrBeast production document — context only: https://simonwillison.net/2024/Sep/15/how-to-succeed-in-mrbeast-production/ , https://passionfru.it/?p=81151 (paraphrase only)
- DOAC cold-open analyses (third-party) — https://joyspace.ai/diary-of-ceo-formula-trailerize-podcast
- `youtube-agent-skill` (MIT, reviewed, ideas reimplemented) — https://github.com/Jakeschincariol/youtube-agent-skill
- yaxeen storytelling skills (MIT) — https://github.com/yaxeen/storytelling-skills
- openshorts clip rules (MIT core) — https://github.com/mutonby/openshorts
- vidpros podcast guide [vendor] — https://vidpros.com/podcast-on-youtube/
- Washington Post 2024 on slower edits — https://www.washingtonpost.com/technology/2024/03/30/video-editing-mrbeast-retention/
- Research (2026-10-11 archive, not distributed: `../research/README.md`): `F5-story-hook.md` §0–§10; `F4-strategy.md` §3, §5; `V1-vetting.md` K5; `V3-vetting.md` K3–K9; `SYNTHESIS.md` §2.5, §7A.
