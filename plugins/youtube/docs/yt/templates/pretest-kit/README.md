# Kit del pre-test delle thumbnail — Prolific o PickFu

> Strumenti per fare vedere le copertine candidate a persone vere prima dell'uscita e leggere i risultati. Regole in `knowledge/07-thumbnails.md` §15.2 e §16, procedura generale in `../pre-test-protocollo.md`. **L'agente prepara il kit e analizza i CSV; l'operatore crea gli account, carica la pagina, crea lo studio, paga e scarica i risultati, a mano.** L'agente non si iscrive, non pubblica e non invia niente.

## Cosa c'è qui

| File | A cosa serve |
|---|---|
| `feed-test.template.html` | Il modello della pagina del test: feed tipo YouTube con 9 copertine, esposizione di 3 secondi, domande. Non si apre così: lo compila `build_kit.py` |
| `build_kit.py` | Costruisce la pagina autonoma (immagini incorporate) e le immagini per PickFu da una configurazione |
| `pretest.config.example.json` | Configurazione di esempio: braccia, coppie, vicini del feed, raccolta dati, chiavi di codifica |
| `questionario.md` | Il testo di ogni schermata e di ogni domanda, in italiano, più le domande per PickFu |
| `istruzioni-prolific.md` | Passi esatti: Google Modulo per raccogliere le risposte, hosting della pagina, studio su Prolific, prova, lancio, download |
| `istruzioni-pickfu.md` | Passi esatti per il sondaggio su PickFu (testa a testa o classifica) |
| `ipotesi-template.md` | La pre-registrazione: variabile, braccia, regola di decisione, scritta **prima** del lancio |
| `risultati-template.md` | Il modello dei risultati, come si analizzano e dove si registrano (`ab_tests`, MEMORY.md dell'agente) |
| `analizza.py` | L'analisi (solo libreria standard): esclusioni, test binomiale esatto, Holm, feed, foglio di codifica alla cieca, riga per `yt-db` |

Nella repo non c'è nessuna immagine di ospiti né di altri canali: le copertine e i vicini restano nella cartella dell'episodio o dello studio.

## Come funziona il test (circa 2 minuti)

1. **Controllo del dispositivo**: serve un computer con la finestra di almeno 1000 × 620 px. Su telefono o tablet la pagina chiede di ritirarsi da Prolific senza penalità (le impostazioni sul dispositivo di Prolific sono solo informative).
2. **Controllo di attenzione** all'inizio («seleziona Verde»), come chiede la policy di Prolific.
3. **Feed a tempo**: la copertina del braccio assegnato in una posizione casuale tra 8 copertine vere di altri canali, tema scuro o chiaro a caso, 3 secondi, poi le copertine spariscono. Domanda: «Quale di questi video apriresti?» (clic sul riquadro, oppure «Non ricordo / nessuno»).
4. **Una copertina per 3 secondi** (la stessa del braccio), poi «Cosa promette questo video?» e «A chi è rivolto, secondo te?», a testo libero.
5. **Testa a testa**: ogni coppia della configurazione, ordine e lati a caso: «Quale dei due video apriresti?».
6. **Profilo**: quanto spesso guarda video sul tema del canale (`topic` nella configurazione); se conosceva già il podcast.
7. Invio delle risposte a un Google Modulo e ritorno automatico su Prolific.

Ogni partecipante vede un solo braccio nel feed (gruppi separati) e tutte le coppie nel testa a testa (stesse persone). L'esposizione al braccio del feed è bilanciata tra le braccia, quindi non favorisce nessuna coppia.

**Cosa decide**: il testa a testa (test binomiale esatto, soglia 61/100). **Cosa descrive**: la quota di chi sceglie la nostra copertina nel feed (contro il caso, 1 su 9) e la quota di risposte giuste a «cosa promette» e «a chi è rivolto». Misura una preferenza dichiarata e la comprensione, non il CTR.

## Uso in breve

```bash
KIT=<plugin>/docs/yt/templates/pretest-kit
T=<workdir>/thumbs/pretest/<id-test>          # oppure la cartella dello studio
mkdir -p "$T" && cp "$KIT/pretest.config.example.json" "$T/pretest.config.json"
cp "$KIT/ipotesi-template.md" "$T/ipotesi.md"  # compilare prima del lancio
# modifica pretest.config.json: braccia, coppie, vicini, chiavi di codifica
python3 "$KIT/build_kit.py" --config "$T/pretest.config.json"
open "$T/site/index.html"                      # anteprima locale: nessun invio, record finale visibile
```

Poi `istruzioni-prolific.md` (Google Modulo → `sink` nella configurazione, link di completamento → `prolific.completion_url`, di nuovo `build_kit.py`, hosting) oppure `istruzioni-pickfu.md` (solo le immagini in `pickfu/`).

Uscite di `build_kit.py`:
- `site/index.html`: test con il feed e i vicini veri (opzione (a) del protocollo §3);
- `site-h2h/index.html`: stesso test senza feed e senza immagini di terzi (opzione (b), il default se manca la decisione scritta);
- `pickfu/opzione-N.jpg` a 1280×720 con nomi neutri, e `pickfu/chiave.json` (quale braccio è ogni opzione: **non** va caricato);
- `build.json`: riepilogo della build (id, braccia, vicini, raccolta dati configurata o no).

Parametri dell'URL utili per le prove: `?debug=1` (anteprima anche con la raccolta configurata: niente invio, record finale e download del JSON), `&arm=A`, `&theme=light`, `&slot=0…8` (solo con `debug=1`). Finché `sink` è vuoto, la pagina mostra sempre la fascia rossa «ANTEPRIMA» e non invia niente: non si può lanciare per sbaglio senza raccolta dati.

Analisi: `risultati-template.md`. In breve:

```bash
python3 "$KIT/analizza.py" report --config "$T/pretest.config.json" --csv "$T/risultati/risposte.csv" --cost "£43"
# compila risultati/codifica_da_compilare.csv alla cieca, poi:
python3 "$KIT/analizza.py" report --config "$T/pretest.config.json" --csv "$T/risultati/risposte.csv" \
  --coding "$T/risultati/codifica_compilata.csv" --cost "£43"
yt-db add ab_tests "$(cat "$T/risultati/ab_tests_row.json")"
```

## Privacy, consenso, terzi

- **Volti prima dell'uscita.** Le copertine candidate mostrano il volto dell'ospite (e degli host) a persone estranee prima della pubblicazione. **Serve sempre l'OK di una riga dell'ospite** (testo in `../pre-test-protocollo.md` §1). La pagina chiede ai partecipanti di non fare screenshot e di non condividere le immagini; resta comunque una copia vista da circa 100 estranei.
- **Copertine di altri canali.** I vicini del feed sono thumbnail di terzi: uno stimolo di ricerca privato, mai una pagina pubblica. Si usano solo se l'operatore lo decide per iscritto nella `ipotesi.md` (opzione (a), `11-compliance-safety.md` §3); altrimenti si usa `site-h2h/`. La pagina ha `noindex` e un `robots.txt` che blocca tutto; l'indirizzo non va pubblicato da nessuna parte; il sito si cancella a fine raccolta e comunque entro 30 giorni.
- **Dati dei partecipanti.** La pagina raccoglie: risposte, tempi, dimensione della finestra, lingua e fuso del browser, ID Prolific (pseudonimo). Nessun nome, email o IP. I CSV restano nella cartella dell'episodio: mai nel vault né nella repo; nelle note vanno solo i risultati aggregati. Il Google Modulo e il suo foglio si svuotano dopo il download.
- **Costi.** Spese dell'operatore fuori da Claude: si registrano nel `result_json` della riga `ab_tests`, non nel registro delle chiamate a pagamento (`07` §17).

## Limiti noti

- Il feed mostra solo copertine e segnaposto grigi al posto di titoli e canali (come il protocollo §2: se solo la nostra tile avesse un titolo si riconoscerebbe). Si può aggiungere lo stesso titolo alle due copertine del testa a testa con `h2h.title`.
- Con ~33 persone per braccio il feed vede solo differenze grandi (per esempio dall'11 % al 30 %): è descrittivo.
- Il panel di Prolific pende verso studenti e ricercatori; quello di PickFu Italia è più piccolo di quello USA (tempi più lunghi con più filtri).
- Un pacchetto contro un altro (telaio, volto e gancio insieme) dice quale pacchetto preferire, non quale elemento conta. Per le variabili singole: un braccio contro l'altro, tutto il resto identico.
