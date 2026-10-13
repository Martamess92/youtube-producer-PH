---
# TEMPLATE del profilo canale. Si copia nel primo dei channels_dirs di yt-config
# (default ~/.config/youtube-producer/channels/<slug>.md), MAI dentro il plugin né nella sua repo:
# la cartella del plugin si sovrascrive a ogni aggiornamento e i profili non vanno in git.
# Lo crea /youtube:setup onboard --channel=<slug>; si può anche copiare a mano.
# slug: minuscolo, senza spazi, identico in yt-auth, yt-new, <studio_dir>/work/<slug>/ e <brands_dir>/<slug>/.
# Ogni "[DA COMPILARE]" va riempito con un dato vero di QUESTO canale, oppure lasciato così (l'agente lo chiede).
# Chiavi in inglese (contratto con ytcore.load_channel), valori in italiano. Date tra virgolette.
slug: "[slug]"
kind: own                        # own = canale tuo o del tuo team · personal = canale personale di una persona · client = canale di un cliente
video_kind: other                # tipo di video di default per yt-new: podcast | talking-head | other (--kind lo cambia per un episodio)
name: "[Nome del canale]"
status: "onboarding"             # onboarding | attivo | inattivo
profile_updated: "[AAAA-MM-GG]"
share_lessons: false             # true solo per kind: own E se il canale è in learning_pr_channels: le lezioni possono diventare PR (13-learning-loop §9)

channel:
  handle: "[@handle]"
  url: "[https://www.youtube.com/@handle]"
  id: null                       # lo stampa `yt-auth --channel <slug> --check` dopo l'autorizzazione
  brand_account: "[sì | no | da verificare]"   # se è un Brand Account, all'autorizzazione si sceglie il canale, non l'account personale
  oauth_token: null              # null = <studio_dir>/secrets/token-<slug>.json (default del toolkit), uno per operatore
  oauth_owner: "[chi possiede o gestisce il canale e autorizza l'accesso in sola lettura]"
  reporting_jobs: "da creare il giorno dell'autorizzazione con `yt-reporting-setup --channel <slug>` (backfill di soli 30 giorni); prima `--list`: se esistono già, non rifarli"
  podcast_playlist: "[esiste? solo episodi completi?]"
  ypp: "[sì | no | sconosciuto]"
language: it

graphics_engine: hyperframes     # hyperframes (Apache-2.0, sempre ammesso) | remotion (solo kind own o personal, vedi graphics_licence)
graphics_licence:
  rule: "Remotion è gratuito per singoli e organizzazioni fino a 3 persone (collaboratori inclusi nei termini 5.0); oltre serve una licenza Company. Per i clienti: solo file finiti oppure HyperFrames. Dettagli: docs/yt/vendor/REMOTION_LICENSE_NOTE.md"
  headcount: []                  # chi lavora sul canale (persone, collaboratori), per il conteggio
  status: "da verificare"        # confermato | da verificare: finché non è confermato l'agente usa fallback_engine
  fallback_engine: hyperframes
paid_services: []                # servizi a pagamento solo nella sessione principale, con preventivo e OK per ogni chiamata

engagement:                      # solo kind: client (altrimenti lasciare vuoto)
  scope: "[audit | strategia | montaggio | Shorts | thumbnail | review]"
  start: "[AAAA-MM-GG]"
  end: "[AAAA-MM-GG]"
  non_compete_check: "[nessun altro cliente nello stesso segmento diretto? sì/no, verificato il AAAA-MM-GG]"

audience: "[DA COMPILARE: chi guarda, con dettagli concreti]"
positioning: "[DA COMPILARE: una frase, per chi, cosa promette, perché voi]"
pillars: []                      # [{id, name, share, what}]
formats: {}                      # {engine: {name, length, structure}, experiments: [...], shorts: "...", interview_rules: {key_questions: [], banned_questions: []}}
north_star:
  metric: "[DA COMPILARE: per un canale di business un risultato di business, non le view; per una community: spettatori di ritorno + ore di visione coinvolte]"
  inputs: []
  decision_rules: "confronti a pari età (28 giorni); si decide su trend di almeno 4 video; niente target percentuali universali"

voice:
  register: "[DA COMPILARE: tu / voi / lei; tono]"
  persona: "[facoltativo: come suona il canale]"
  public_names:
    hosts: []                    # nomi pubblici di chi conduce, come vanno scritti a schermo e nei sottotitoli
    short: []
    never: []                    # soprannomi o grafie da non usare mai in pubblico
  banned: []                     # parole vietate nei testi che scriviamo noi (mai nel parlato dell'ospite)
  banned_match: ""               # es. «senza maiuscole e per radice: soluzion*, innovativ*»
  banned_openers: []
  banned_superlatives: []
  banned_cta: []
  banned_title_patterns: []
  prefer: {}                     # {da_evitare: "da usare"}
  mandatory_when_relevant: []    # termini del canale da usare quando pertinenti
  wpm: null                      # parole al minuto della voce principale: si misura su 3+ trascrizioni (04-hooks-first-30s §2.2)
copy_rules: []                   # regole di copy del canale: punteggiatura di titoli e testi a schermo, nomi di strumenti, maiuscole, slogan

brand:                           # cartella del brand nei brands_dirs (default ~/.config/youtube-producer/brands/<slug>/), MAI nel plugin
  slug: "[slug]"                 # senza una cartella propria il toolkit usa il brand «demo» del plugin
  tokens: "~/.config/youtube-producer/brands/<slug>/tokens.json"   # colori ESATTI dal brand kit o dal CSS, mai a occhio
  fonts: []                      # file in <brand>/fonts/, ognuno con la sua licenza accanto (deve permettere il render locale)
  text_pairs_allowed: []         # coppie testo/fondo ammesse, calcolate con 07-thumbnails §7.1–§7.2
  accent: "[nome del token d'accento]"
  logo: "~/.config/youtube-producer/brands/<slug>/logo/"
  logo_rules: "[facoltativo: colori ammessi, misura minima, spazio di rispetto]"
  layout: "~/.config/youtube-producer/brands/<slug>/layout.json"   # serve per gli Shorts e i ritagli dei master compositi (yt-clips layout --measure)

thumbnails:
  version: 2
  default_lever: claim           # claim | proof | duo | name (07-thumbnails §5)
  default_template: duo          # duo (podcast con ospite e host) | ritratto (canale senza ospiti) | generic (clienti, salvo OK scritto a un template di serie) | scena | prova | <slug>-*.html del brand
  templates:
    duo: "ospite + host dello stesso episodio, titolo di 3–4 parole tra i volti (ogni riga ≥ 20% dell'altezza), cerchio d'accento dietro l'ospite, nome e ruolo dell'ospite, etichetta piccola dell'host"
    ritratto: "solo l'ospite, testa e spalle, volto 40–50% (≥ 35%); per episodi con un solo volto e per la leva nome"
    scena: "pop-out sulla copia scurita e sfocata dello stesso istante, quando il set dice «podcast»"
    prova: "la prova vera (schermata, grafico, oggetto) con l'ospite più piccolo; numero solo se verificato"
    generic: "telaio neutro guidato dai token del brand: claim, prova con artifact, duo o nome con due people"
  engine: html                   # html (default, con i pre-check automatici) | remotion (solo own/personal con graphics_licence confermata)
  format_label: "[facoltativo: etichetta in alto a destra, es. IL PODCAST DEI MAKER]"
  show_logo: wordmark            # wordmark (nome del canale dai token, wordmark.text) | symbol (solo il logo del brand) | false
  host_tag: "con [Nome dell'host]"   # nel duo l'host ha un'etichetta piccola, non un secondo box del nome
  meta_line_rule: "EVENTO / ANNO (CITTÀ / EVENTO / ANNO quando la città aggiunge qualcosa); ogni voce verificata; mai uno sponsor implicito"
  accent: auto                   # auto = tra gli accenti del brand quello con più stacco ΔL* da capelli e volto (07 §7.2)
  accents: []                    # vuoto = tutti gli accenti del brand; altrimenti la lista dei token ammessi
  grade_default: natural         # natural di default; mono (livello 2b, una sola curva su tutta la foto) come opzione
  grade_allowed: [natural, mono]
  guest_style_default: none      # none su ogni template; graphic (contorno/alone + tono globale) solo su richiesta o come braccio di un pre-test
  guest_style_allowed: [none, graphic]
  hook_words_min: 3
  hook_words_max: 6              # oltre 6: avviso; sotto 3 o frammento nominale: errore (07 §5.3)
  hook_words_max_duo: 4          # duo: 3–4 parole in 2 righe
  duo_line_min_pct: 20           # duo: ogni riga del titolo ≥ 20% dell'altezza
  cap_height_min_px: 86          # su canvas CSS 1280×720: ogni riga del gancio ≥ 12% dell'altezza
  keyword_line_min_pct: 18
  face_min_pct_claim: 35         # errore sotto (salvo face_floor_reason al G2); avviso sotto 40; obiettivo 40–50
  display_cap: "c"               # c = volto a 1280 px ≤ 2,0× la risoluzione effettiva della sorgente; b = 1,5× (ripiego)
  served_detail: {warn_below: 713, error_below: 569}   # nitidezza del volto nel file servito 720×405
  source_priority: ["camera fissa stretta sull'ospite (file ISO, 4K)", "ISO delle camere principali", "frame del master (inset preferito) entro il tetto", "foto fornite dall'ospite con permesso scritto"]
  photo_session: false           # niente sessione foto né pose: camera fissa stretta (docs/yt/templates/brief-camera-stretta.md)
  portrait_pipeline: "yt-portrait scan (classi d'espressione; camera stretta con --src <file ISO> --layout full) → cut (BiRefNet-portrait, ripiego Apple Vision; tetto 2,0× della risoluzione effettiva a 1280; disegnato 1:1) → plate della scena"
  owner_ai_edits: false          # true solo per kind: personal, con consenso scritto della persona ritratta e solo sul SUO volto
  ai_generation: "props e sfondi da solo testo, nella sessione principale, con preventivo e OK per ogni chiamata; mai persone, mai testo nell'immagine, nessun upload di girato"
  props_budget: {per_episode_eur: 5, per_month_eur: 20, ledger: "<studio_dir>/data/paid-calls.jsonl"}
  episode_notes: {}              # note per singolo episodio, es. {ep12: "niente numeri nei ganci finché i ricavi non sono confermati a orecchio"}
  ab_test: "A/B nativo di Studio come controllo di sicurezza del pacchetto su un episodio nuovo, a mano dall'operatore (G3); le variabili singole con il pre-test umano (docs/yt/templates/pre-test-protocollo.md)"

consent:
  release_required: true         # default: senza liberatoria confermata niente passa G1 o G2 (11-compliance-safety §6.4)
  covers: ["image", "voice", "clips", "thumbnails", "ads", "ai_processing", "third_party_processors"]
  owner: "[chi raccoglie e conserva le liberatorie: il titolare del canale, o il cliente]"
  rule: "liberatoria richiesta. Per cambiarla serve una decisione scritta del titolare del canale, con data, riportata qui (release_required: false + motivo); restano comunque le regole su volti, servizi esterni e fedeltà al parlato"
  notes: "[DA COMPILARE]"

confidentiality:
  - "nessun dato, nome o numero di altri canali o clienti in questo profilo, nella cartella di lavoro o nei deliverable"
  - "nessun dato di questo canale riusato altrove senza anonimizzazione"
  - "materiale grezzo solo in locale (<studio_dir>/work/<slug>/), mai caricato su servizi terzi né committato in una repo"

glossary: "<slug>.glossary.txt"   # nella stessa cartella del profilo (formato sotto)
glossary_note: "whisper usa solo gli ultimi ~224 token del prompt: termini dell'episodio (project.json glossary_extra) + righe P1"

vault:                           # facoltativo: solo se l'operatore ha impostato vault_path in config.yaml
  deliverables: null             # cartella del vault (relativa a vault_path) per le note di questo canale; null = <workdir>/deliver/notes/
  context: null                  # facoltativo: cartella di contesto da leggere (sola lettura)

cadence:
  long_form: "[settimanale | bisettimanale | mensile]"
  shorts_per_week: null
  max_gap_days: 30

loudness:
  integrated: -14
  true_peak: -1.5
  lra: 11

recording:
  mode_current: "[M | I]"        # M = post-produzione di un master già montato · I = ISO delle camere + tracce dei microfoni
  video: "[codec, risoluzione, fps, SDR/HDR]"
  layout: "[facoltativo: com'è composto il master (finestra, inset, PiP)]"
  audio: "[tracce, microfoni, difetti noti]"
  sample_master: null            # facoltativo: un master di prova per i test della catena (percorso sul tuo Mac, mai nella repo)
  capture_checklist: "ISO di ogni camera, tracce dei microfoni, camera fissa stretta sull'ospite, 30 s di wild line, liberatoria"

baseline: {}                     # fotografia del canale all'onboarding: {observed, subscribers, long_form_episodes, shorts, views_per_episode, last_upload}

distribution:
  podcast_playlist: "solo episodi completi, in ordine; niente clip né Shorts"
  shorts: "fuori dalla playlist podcast; link Related video all'episodio"
  collaborations: "ospite invitato come Collaborator se ha un canale"
---

# Template — Profilo di un canale

Questo file è lo stampo del profilo di un canale: lo legge ogni skill `/youtube:*` prima di lavorare su quel canale. Il frontmatter qui sopra è il contratto con il toolkit (`ytcore.load_channel(slug)`); il testo spiega come compilarlo. Ne serve uno per canale, che sia il tuo, quello personale di un collega o quello di un cliente.

Il profilo compilato vive fuori dal plugin, nei `channels_dirs` dell'operatore (default `~/.config/youtube-producer/channels/`). Nel plugin c'è solo questo template: nessun canale di esempio e nessun canale di default. Se nei `channels_dirs` c'è un solo profilo, l'agente usa quello; se ce ne sono di più, chiede su quale canale lavorare.

## Come si crea

1. **Slug.** Scegli lo slug (es. `caffe-maker`). Vale ovunque: `yt-auth --channel`, `yt-new --channel`, `<studio_dir>/work/<slug>/` e la cartella del brand `<brands_dir>/<slug>/`. `/youtube:setup onboard --channel=<slug>` copia il template in `~/.config/youtube-producer/channels/<slug>.md` senza sovrascrivere nulla.
2. **Tipo.** `kind: own` per il tuo canale o quello del tuo team, `personal` per il canale personale di una persona, `client` per un cliente. Il tipo decide il motore grafico ammesso, le regole di isolamento e se le lezioni possono diventare proposte per il plugin (`share_lessons`).
3. **Campi.** Riempi solo con dati veri di questo canale. Quello che non sai resta `[DA COMPILARE]`: l'agente lo mette tra le domande aperte della nota di onboarding.
4. **Brand.** Facoltativo. Se il canale ha un'identità visiva, crea `~/.config/youtube-producer/brands/<slug>/tokens.json` con i colori esatti (dal brand kit o dal CSS, mai a occhio), più logo, font con licenza, `layout.json` e, se vuoi, template e preset dei sottotitoli. Il contratto della cartella è in `knowledge/07-thumbnails.md` §8. Senza cartella propria il toolkit usa il brand neutro `demo` del plugin.
5. **Glossario.** Crea `<slug>.glossary.txt` accanto al profilo (formato sotto) e, quando la trascrizione sbaglia sempre lo stesso nome, `<slug>.confusions.json`.
6. **Accesso dati** (facoltativo, `../SETUP-GOOGLE.md`): chi possiede o gestisce il canale autorizza in sola lettura (`yt-auth --channel <slug>`); il giorno stesso si creano i job Reporting (`yt-reporting-setup --channel <slug>`); si controlla con `yt-doctor --channel <slug>`.
7. **Consenso.** Con `consent.release_required: true` (il default) nessun episodio passa G1 senza la conferma che le liberatorie delle persone in video esistono e coprono gli usi previsti (`knowledge/11-compliance-safety.md` §6.4).

## Glossario: formato

Un file di testo, una voce per riga; tutto quello che segue `#` è un commento, quindi nessuna voce può contenere `#`. Le intestazioni `# ── P1 …`, `# ── P2 …`, `# ── P3 …` danno la priorità alle voci che seguono:

```text
# Glossario del canale <slug>: nomi propri e gergo che la trascrizione sbaglia.
# ── P1 · nome del canale, persone in video, format (sempre nel prompt)
Il Caffè dei Maker
Giulia Conti
# ── P2 · prodotti e gergo ricorrente (se c'è spazio nel prompt)
no-code
side project
# ── P3 · nomi di un solo episodio (entrano solo se l'episodio li nomina)
```

Tieni P1 corta: whisper considera solo gli ultimi ~224 token del prompt. Non riordinare le righe senza motivo: l'ordine fa parte del prompt e cambiarlo rende «non aggiornati» i transcript esistenti. Le correzioni che fai durante il lavoro finiscono da sole nel glossario appreso del canale (`<studio_dir>/data/learned/<slug>.glossary.txt`), che il toolkit fonde con questo.

`<slug>.confusions.json` raccoglie le grafie sbagliate che i motori di trascrizione producono per un termine del glossario:

```json
{"note": "Confusioni ASR del canale <slug>.", "updated": "AAAA-MM-GG",
 "confusions": [
  {"term": "Ferri", "type": "person", "aliases": ["Ferry"], "origin": "in-sample",
   "evidence": "revisione dell'episodio del AAAA-MM-GG"}]}
```

Un alias che è anche una parola vera si marca `"ambiguous": true`: si corregge solo con la maiuscola a metà frase e con una parola di contesto vicina. Le unità dopo una cifra (MRR/ARR) non si correggono mai in automatico: si ascoltano.

## Regole di isolamento (obbligatorie per i clienti, consigliate per tutti)

1. **Nel profilo entra solo questo canale.** Niente nomi, numeri, fornitori o partner presi da altri profili. Senza un dato di questo canale si scrive `[DA COMPILARE]`.
2. **Prima di nominare una persona** in un deliverable si verifica che il nome sia nel contesto di questo canale; altrimenti «il team» o `[REFERENTE DA COMPILARE]`.
3. **I dati restano separati per canale**: cartella di lavoro `<studio_dir>/work/<slug>/`, token `token-<slug>.json`, righe SQLite con `channel=<slug>`, lezioni apprese per canale. Nessun transcript, frame o numero di un canale nel lavoro di un altro.
4. **I confronti tra canali sono anonimi**: «un podcast B2B con un pubblico simile», mai nomi o numeri riconoscibili.
5. **Memoria dell'agente**: gli appunti di un cliente stanno nella sua sezione (`## cliente:<slug>`); quello che si riusa altrove si scrive in forma anonima.
6. **Niente nella repo del plugin**: né il profilo, né il glossario, né il brand. Le lezioni di un cliente o di un canale personale non diventano mai proposte per il plugin.
7. **Due clienti nello stesso segmento**: niente ricerca condivisa (liste di peer, teardown, Outlier Bank). Ognuno ha la sua.
8. **Dati dei peer**: il dato pubblico di altri canali raccolto via API si rinfresca o si elimina entro 30 giorni (`knowledge/11-compliance-safety.md` §4.3).

## Licenze e motori grafici

- **HyperFrames** (Apache-2.0) è sempre ammesso ed è il default: grafiche, riedizione del talking head, sottotitoli dietro il soggetto. Per i clienti è l'unico motore per i progetti consegnati.
- **Remotion** è ammesso solo per `kind: own` o `personal` e solo se chi lavora sul canale, collaboratori compresi, resta entro 3 persone (`graphics_licence`). Finché `graphics_licence.status` non è «confermato», l'agente usa `fallback_engine`. A un cliente si consegnano solo file finiti, mai un progetto Remotion. Dettagli: `../vendor/REMOTION_LICENSE_NOTE.md`.
- **Servizi a pagamento**: `paid_services: []`. Mai dentro l'agente; solo nella sessione principale, con preventivo e OK per ogni chiamata (`knowledge/11-compliance-safety.md` §10).

## Deliverable e gate

- **Note** (audit, strategia, review, pacchetti episodio): di default in `<studio_dir>/work/<slug>/…/deliver/notes/`, file nuovi `{AAAA-MM-GG} — {Titolo}.md` con `status: draft`, mai sovrascritti. Se l'operatore ha un vault Obsidian (`vault_path` in `config.yaml`) e questo profilo indica `vault.deliverables`, le note vanno lì.
- **Gate**: G1 prima di tagliare, G2 prima dei render finali di Shorts e thumbnail, G3 pubblicazione sempre manuale, fatta dal titolare del canale o da chi indica. L'agente non carica, non pubblica e non cambia nulla sul canale.
- **Fine di un ingaggio (clienti)**: il cliente revoca il token dalle impostazioni del suo account Google; cartelle di lavoro e materiale grezzo si archiviano o si eliminano su decisione dell'operatore e secondo il contratto. L'agente non cancella nulla da solo.
