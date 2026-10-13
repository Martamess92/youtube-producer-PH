# Pre-test su Prolific — passi per l'operatore

> Tutto a mano, fuori da Claude: account, pagamenti, caricamenti e pubblicazione li fa l'operatore. L'agente prepara la cartella del test e analizza i CSV. Le etichette dei menu di Prolific, Google Moduli e Netlify sono quelle del 2026-10-12: se l'interfaccia è cambiata, cerca la voce equivalente.

**Cosa serve**: la cartella del test costruita con `build_kit.py` (`site/` o `site-h2h/`), `ipotesi.md` compilata, un account Google, un account Netlify (gratuito) o un altro hosting statico, un account ricercatore Prolific con credito.

## Costo

Prolific vuole il tempo stimato in **minuti interi** [ufficiale, pagina «Study cost»; ricontrolla nel builder]. Il test dura 90–110 s: si dichiarano **2 minuti**.

| Ricompensa per persona | Tariffa sul tempo dichiarato | 100 persone + commissione aziende 42,8 % | Note |
|---|---|---|---|
| **£0,30 (consigliata)** | £9,00/h (la consigliata da Prolific) | £30,00 + £12,84 = **≈ £43** | Reclutamento più rapido |
| £0,23 (minimo ragionevole) | £6,90/h (sopra il minimo di £6/h) | £23,00 + £9,84 = **≈ £33** | Sul tempo reale (~90 s) è ≈ £9/h |

Più IVA se dovuta. La commissione del 33,3 % vale solo per università ed enti non profit. Prezzi da ricontrollare nel riepilogo dei costi dello studio, che compare dopo aver inserito il numero di partecipanti.

## 1. Google Modulo che riceve le risposte (10 minuti)

1. Vai su forms.google.com con l'account Google del canale o del team → **Modulo vuoto**. Titolo interno: `pretest-<study_id>` (i partecipanti non lo vedono).
2. Aggiungi tre domande, **non obbligatorie**, in questo ordine:
   - `record` → tipo **Paragrafo**
   - `pid` → tipo **Risposta breve**
   - `arm` → tipo **Risposta breve**
3. **Impostazioni** → **Risposte**: «Raccogli indirizzi email» = **Non raccogliere**; «Limita a 1 risposta» = **disattivato** (altrimenti chiede l'accesso a Google). Nessuna domanda obbligatoria.
4. Scheda **Risposte** → **Collega a Fogli** → nuovo foglio. Lì arriveranno le risposte.
5. Menu ⋮ in alto → **Ottieni link precompilato** → scrivi `x` in tutte e tre le domande → **Ottieni link** → **Copia link**. Il link è come:
   `https://docs.google.com/forms/d/e/<ID_MODULO>/viewform?usp=pp_url&entry.111111111=x&entry.222222222=x&entry.333333333=x`
6. Nella `pretest.config.json` del test:
   ```json
   "sink": {"type": "google_form",
            "form_action": "https://docs.google.com/forms/d/e/<ID_MODULO>/formResponse",
            "fields": {"record": "entry.111111111", "pid": "entry.222222222", "arm": "entry.333333333"}}
   ```
   (`viewform` diventa `formResponse`; i tre `entry.` nell'ordine delle domande.)

## 2. Studio su Prolific in bozza, per avere il link di completamento

1. app.prolific.com → **New study** (o «Create study»).
2. **Study details**
   - Titolo pubblico: `Copertine di video: quale apriresti? (2 minuti)`
   - Descrizione: `Vedrai per pochi secondi una pagina di video simile a YouTube e alcune copertine, poi risponderai a poche domande sulla tua prima impressione. Serve un computer (non telefono o tablet). Alcune immagini riguardano video non ancora pubblicati: ti chiediamo di non fare screenshot né di condividerle.`
   - Dispositivi: solo **Desktop** (l'impostazione è informativa: il blocco vero lo fa la pagina). Nessun requisito di audio, camera o download.
3. **Data collection**: «External study link» (o equivalente). Spunta **I'll use URL parameters**: Prolific aggiunge `PROLIFIC_PID`, `STUDY_ID` e `SESSION_ID`. Per ora lascia l'URL provvisorio; lo completi al passo 4.
4. **Completion paths / completion codes**: scegli **Redirect URL** e copia il **Completion URL** generato (`https://app.prolific.com/submissions/complete?cc=…`). Mettilo nella configurazione: `"prolific": {"completion_url": "<quello copiato>"}`.
5. Salva come bozza.

## 3. Costruisci e metti online la pagina

1. Ricostruisci: `python3 <kit>/build_kit.py --config <test>/pretest.config.json`. Deve dire «raccolta dati configurata · link di completamento Prolific presente».
2. Scegli la cartella: `site/` se in `ipotesi.md` c'è la decisione scritta per l'opzione (a) (feed con i vicini veri); altrimenti `site-h2h/`.
3. Hosting, per esempio Netlify (gratuito):
   - app.netlify.com → **Add new site** (o «Add new project») → **Deploy manually** → trascina la cartella `site/` (o `site-h2h/`).
   - **Site configuration** → **Change site name**: un nome non indovinabile, per esempio `pt-` seguito da 8 caratteri a caso. L'indirizzo diventa `https://<nome>.netlify.app/`.
   - Non collegare domini, non condividere il link fuori da Prolific.
4. Torna allo studio su Prolific, **Data collection**, e incolla l'URL della pagina: `https://<nome>.netlify.app/` seguito dai parametri che Prolific aggiunge (`?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}`).

## 4. Prove prima del lancio (obbligatorie)

1. Apri `https://<nome>.netlify.app/?debug=1`: fascia rossa «ANTEPRIMA», nessun invio. Fai il percorso in tema scuro e chiaro (`&theme=dark`, `&theme=light`).
2. Due prove vere: `https://<nome>.netlify.app/?PROLIFIC_PID=TEST1` e `?PROLIFIC_PID=TEST2` (con un altro browser o una finestra in incognito: la pagina ricorda chi ha già finito). Alla fine la pagina ti porta su Prolific: è normale.
3. Nel foglio Google devono comparire **due righe** con il JSON nella colonna `record`. Se non arrivano: controlla `form_action` (`formResponse`, non `viewform`), gli `entry.` e che il modulo non chieda l'accesso.
4. Su Prolific usa **Preview** per vedere lo studio come un partecipante.
5. Le righe `TEST…` possono restare: `analizza.py` le esclude da sola.

## 5. Pubblico e lancio

1. **Audience** → **Prescreeners** (filtri):
   - **Current Country of Residence**: Italy.
   - **Age**: 18–45.
   - **Fluent languages**: Italian (oppure **First language**: Italian, più stretto).
   - Interesse per il tema del canale: Prolific non ha sempre un filtro diretto. Se nel builder trovi un filtro vicino (per esempio settore di lavoro o un interesse), puoi aggiungerne **uno**; ogni filtro riduce il pool italiano e allunga i tempi. Senza filtro, la domanda D5 del test permette di guardare a parte chi guarda spesso video su quel tema (`topic`).
   - Per un secondo test sullo stesso tema: **Exclude participants from previous studies** → scegli questo studio.
2. **Places**: 100. **Estimated completion time**: 2 minuti. **Reward**: £0,30 (o £0,23, vedi Costo). Controlla il riepilogo dei costi.
3. Ricontrolla `ipotesi.md` (scritta e datata prima del lancio) → **Publish**.

## 6. Durante e dopo

1. Segui l'avanzamento su Prolific. Chi chiede aiuto per «finestra troppo piccola» va invitato a ritirarsi senza penalità.
2. **Approvazioni**: approva tutti (default). La policy di Prolific permetterebbe di rifiutare chi sbaglia il controllo di attenzione in uno studio sotto i 5 minuti, ma il kit lo esclude comunque dall'analisi.
3. Nel foglio Google: **File** → **Scarica** → **Valori separati da virgola (.csv)** → salva come `<test>/risultati/risposte.csv`.
4. Dai il CSV all'agente: `analizza.py report …` (vedi `risultati-template.md`).
5. **Pulizia, entro 30 giorni e comunque a fine analisi**: Netlify → **Site configuration** → **Delete this site** (o «Delete project»); svuota le risposte del Google Modulo e cancella il foglio; i CSV restano solo nella cartella dell'episodio.
6. Registra il costo reale (dal riepilogo di Prolific) per `--cost`.
