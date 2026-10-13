# Contribuire a YouTube Producer

La repo è privata e la usano le persone invitate come collaboratori. Ogni commit su `main` arriva a tutti con il prossimo aggiornamento del plugin (README, «Aggiornare»): per questo su `main` si entra solo con una pull request.

**Non fare mai `git push` su `main`.** Su una repo privata di un account personale i collaboratori hanno sempre il permesso di scrittura, e la protezione del branch richiede un piano GitHub a pagamento: se manca, GitHub non ti ferma. La regola la teniamo noi: lavora sempre su un branch e apri una PR (sotto). Se per sbaglio hai fatto push su `main`, avvisa subito il proprietario della repo.

## Flusso: branch e pull request

1. Clona la repo (servono `gh auth login` e `gh auth setup-git`):
   ```bash
   gh repo clone MikeIdeas2025/youtube-producer ~/youtube-producer && cd ~/youtube-producer
   ```
   È anche il `repo_path` di default delle PR di apprendimento `learn/…`; se la cloni altrove, scrivi il percorso in `repo_path` (README, «Configurazione»).
2. Crea un branch da `main` aggiornato, con un nome che dica cosa fai: `feat/<cosa>`, `fix/<cosa>`, `docs/<cosa>`, `knowledge/<cosa>`. Per esempio `fix/capitoli-oltre-un-ora`.
3. Lavora e prova in locale (sotto). Commit piccoli, messaggi brevi in italiano all'imperativo («Correggi il crop degli Shorts sul campo largo»).
4. Apri la PR verso `main` con `gh pr create`. Nella descrizione: cosa cambia, perché, come l'hai provato (comandi e risultati), cosa cambia per chi usa il plugin (serve rilanciare `/youtube:setup`? cambia un comportamento dell'agente?).
5. Revisione di un'altra persona con accesso alla repo. Si fa merge solo con i test verdi e le domande chiuse. Preferito lo squash merge: un commit per PR su `main`.
6. Dopo il merge, chi vuole la versione nuova lancia `claude plugin marketplace update youtube-producer`, poi `claude plugin update youtube@youtube-producer`, e riavvia Claude Code (README, «Aggiornare»); poi `/youtube:setup` se la PR cambia dipendenze o lockfile.

Non si modifica mai la copia installata in `~/.claude/plugins/`: si sovrascrive al primo aggiornamento e nessun altro vede la modifica.

## Provare in locale

Dalla radice della repo:

```bash
claude plugin validate ./plugins/youtube --strict    # manifest, comandi, agenti, hook
claude plugin validate .                             # il marketplace (se tocchi .claude-plugin/marketplace.json)
claude --plugin-dir ./plugins/youtube                # sessione con il plugin del tuo branch al posto di quello installato
```

L'unico avviso ammesso è «version: No version specified»: è voluto (niente `version` in `plugin.json`, la versione è il commit). Con `--strict` quel solo avviso fa uscire «Validation failed»: va bene così, purché non ci sia nient'altro. Ogni altro avviso o errore si corregge prima della PR.

Nella sessione con `--plugin-dir`:

- `/youtube:setup doctor` deve dare tutti i «must» verdi; se hai cambiato `install.sh`, `pyproject.toml`, `uv.lock` o i `package-lock.json`, prima `bash plugins/youtube/scripts/yt/install.sh` (piano) e poi `--yes`;
- se hai toccato il guard: `bash plugins/youtube/scripts/yt/bin/guard.sh --selftest` deve passare tutto;
- `yt-config` deve stampare i percorsi del tuo checkout;
- prova la skill che hai cambiato su un caso vero e piccolo, fino al gate: `/youtube:producer …` oppure `/youtube:<skill> …`, su un tuo canale di prova.

**Test del toolkit.** I test stanno in `plugins/youtube/scripts/yt/tests/`: sono script con assert semplici (niente pytest) che lavorano in cartelle temporanee, quindi non toccano i tuoi dati. Si lanciano con il Python del venv del plugin:

```bash
PY="$(yt-config --get venv_python)"
for t in plugins/youtube/scripts/yt/tests/test_*.py; do "$PY" "$t" || break; done
"$PY" plugins/youtube/scripts/yt/tests/test_learn.py thompson    # solo i test il cui nome contiene «thompson»
```

Per il kit del pre-test delle thumbnail: `python3 plugins/youtube/docs/yt/templates/pretest-kit/analizza.py selftest`.

Se la PR tocca trascrizione, montaggio, Shorts o thumbnail, fai girare anche la catena end-to-end (ordine in `plugins/youtube/scripts/yt/README.md`) su un estratto di pochi minuti di un tuo video, tenuto fuori dal checkout, e riporta nella PR i numeri prima e dopo (loudness, errori di trascrizione sui nomi, controlli del QA).

## Regole

- **Niente media.** Video, audio, sottotitoli, trascrizioni, frame, render: mai nella repo, nemmeno «di prova».
- **Niente segreti.** `client_secret.json`, `api_key`, token OAuth, `.env`, chiavi: mai, nemmeno in un commit poi cancellato (resta nella storia). Se succede, avvisa subito: la chiave va revocata e rigenerata.
- **Niente dati di clienti** e niente nomi, numeri o note di lavoro di clienti, neanche negli esempi.
- **Niente profili di canale.** I profili (`<slug>.md`), i glossari e le confusioni dei canali vivono nei `channels_dirs` di chi li usa. In `docs/yt/channels/` c'è e resta solo `_template.md`.
- **Niente brand di canale.** Token, logo, font, template thumbnail (`<slug>-*.html`), preset ASS e stili Remotion di un canale vivono solo nei `brands_dirs` di chi li usa (default `~/.config/youtube-producer/brands/<slug>/`). Nella repo c'è un solo brand, `demo`, neutro; i template incorporati e le composizioni Remotion restano generici e leggono i brand a runtime (`knowledge/07-thumbnails.md` §8).
- **Niente dati di apprendimento.** Playbook, glossari e confusioni appresi, golden set delle thumbnail e riferimenti di nicchia vivono in `<studio_dir>/data/` di chi lavora. Nella repo arrivano solo le regole, con una PR `learn/…` revisionata (sotto).
- **Niente persone vere negli esempi.** Gli esempi usano canali e persone inventati (il podcast «Il Caffè dei Maker», «Giulia», «Paolo», «Sara»…) e numeri dichiarati come illustrativi.
- **Niente percorsi personali.** Mai `/Users/<nome>/…`: nei comandi si usano i nomi nudi (`yt-ingest`), `yt-config --get <chiave>` per i percorsi di runtime, `${CLAUDE_PLUGIN_ROOT}` nei file di agente e comandi, nomi relativi dentro il knowledge pack.
- **Lingua.** Il corpo delle skill e del knowledge pack è in **inglese** (è il metodo, istruzioni per l'agente); la parte «Integrazione» delle skill, i deliverable, i brief dei gate e i messaggi all'utente sono in **italiano**. Non tradurre il metodo, non scrivere deliverable in inglese.
- **Se cambi un comportamento, aggiorna la conoscenza.** Una regola nuova dell'agente o di una skill va anche nel file del knowledge pack che la governa, e nel `DESIGN.md` se tocca un contratto (comandi, schemi JSON, gate, sicurezza, licenze). Un fatto di piattaforma nuovo va in `01-platform-facts.md` con URL e data di verifica; un numero senza fonte non entra (`10-evidence-ledger.md`).
- **Regole dure.** Niente modifiche generative a volti e voci, consenso per profilo, niente servizi a pagamento dentro l'agente, niente upload né pubblicazione, gate G1/G2/G3, OAuth in sola lettura. Una PR che le allenta non passa.
- **Dipendenze**: versioni fissate in `uv.lock`, `package-lock.json` e `install.sh`. Aggiornarle è una PR a sé, con la prova di `/youtube:setup update`.
- **Codice di terzi**: solo dopo averlo letto per intero, a SHA fissato, con licenza e nota in `docs/yt/vendor/` (`NOTICE.md`). Repo senza licenza o AGPL: solo idee, riscritte.

## Le PR di apprendimento (`learn/…`)

L'agente impara da solo in locale (Tier A) e, per i canali che lo permettono, scrive una **proposta di miglioramento** quando una lezione ha abbastanza prove (Tier B, `plugins/youtube/docs/yt/knowledge/13-learning-loop.md` §9). Il Tier B è spento di default: si accende mettendo il canale in `learning_pr_channels` del `config.yaml` e `share_lessons: true` nel suo profilo, che deve avere `kind: own`. Le proposte diventano PR così:

1. `/youtube:producer` mostra le proposte in attesa e chiede **una volta per gruppo** se aprire la PR (salvo `learning_auto_pr: true` nel `config.yaml` di chi lancia). Mai l'agente da solo: il guard gli impedisce `propose-pr`, push e merge.
2. `yt-learn propose-pr` lavora nel clone indicato da `repo_path` (default `~/youtube-producer`): serve pulito (niente modifiche non committate né file nuovi non tracciati). Crea `learn/<AAAA-MM-GG>-<slug>` da `origin/main` aggiornato, applica i cambi, passa il filtro di privacy e `claude plugin validate`, fa commit e push **solo del branch** e apre la PR con `gh`, **in bozza**. Non fa mai push su `main`, non fa merge, non attiva l'auto-merge.
3. La descrizione della PR dice, in italiano, per ogni proposta: file e sezione, il cambio esatto, le prove (quanti lavori o esiti, quale segnale: scelte dell'operatore o esiti del pubblico), gli id locali delle prove, se tocca una regola dura (deve dire «nessuna» o «stringe una soglia») e l'esito del filtro di privacy.

**Cosa controlla chi rivede**:

- **Prove**: il numero di casi regge? Una lezione da 3 lavori dello stesso tipo è un indizio, non una legge: il testo del cambio deve dirlo con la stessa prudenza (`10-evidence-ledger.md`). Niente conclusioni sugli esiti con meno di 4 video.
- **Regole dure**: niente che tocchi volti, consenso, servizi a pagamento, upload, pubblicazione, gate, nomi pubblici, bordi del crop. Una soglia QA può solo stringersi; se la PR la allenta, serve una decisione scritta nella PR.
- **Privacy**: nessuna immagine con persone, nessun file del golden set o dei riferimenti, nessun testo di transcript, nessun nome di ospiti o di canali, nessun dato di clienti o di canali personali, nessun percorso personale.
- **Coerenza**: se cambia una regola di una skill, il file del knowledge pack che la governa deve dire lo stesso (e viceversa).

**Unire o chiudere.** La PR nasce in bozza: prima del merge va segnata pronta (`gh pr ready`). Si unisce con lo squash merge, come le altre PR. Una PR si può correggere sul branch prima del merge o chiudere con un commento che dice perché: al prossimo `/youtube:learn` la proposta risulta respinta e la lezione locale resta, a meno che il motivo non dica che è sbagliata (allora `/youtube:producer togli la lezione …`). Una PR unita per errore si annulla con una PR di revert, mai con un push diretto su `main`.

## Proporre una skill nuova

1. Apri una issue o una PR in bozza con: cosa fa, quando si usa (le frasi con cui la chiederesti), cosa produce, a quale gate si ferma, cosa resta fuori (per non duplicare un'altra skill).
2. Crea `plugins/youtube/commands/<nome>.md` (diventa `/youtube:<nome>`) seguendo la struttura delle altre: frontmatter `description` e `argument-hint` → «Integrazione» in italiano (lingua, parametri, dove salva, agente, confini, quando usarla) → `## Input` con `$ARGUMENTS` → in inglese «Identity and standard», «Inputs to load», procedura, «Gates», «Quality bar», «Output standards» con il formato di ritorno dell'agente, un «Worked example» con dati inventati.
3. Collega la skill all'agente: una riga nella tabella di routing di `plugins/youtube/agents/producer.md` (e in un flusso se fa parte di una pipeline) e un esempio in `commands/producer.md`.
4. Se porta metodo nuovo, mettilo nel knowledge pack (un file esistente o un `14-…` nuovo) e citane le sezioni dalla skill. Aggiungi una sezione «Learning» che dica cosa registra e quali priori legge (`13-learning-loop.md` §4.2).
5. Aggiorna la tabella delle skill in `plugins/youtube/docs/yt/DESIGN.md` §5, `plugins/youtube/docs/yt/README.md` e il `README.md` della repo.
6. Se servono comandi nuovi del toolkit: `lib/<cmd>.py` con stdout = un solo JSON (`ok`, `outputs`, `warnings`), `--help` in italiano, symlink `bin/yt-<cmd>` → `../scripts/yt/bin/_run` nella `bin/` del plugin, riga nel `scripts/yt/README.md`.
7. Prova con `claude --plugin-dir ./plugins/youtube` e `claude plugin validate ./plugins/youtube --strict` (solo l'avviso sulla versione è ammesso), poi apri la PR.
