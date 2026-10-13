# Questionario del pre-test — testo di ogni schermata

> Il testo è già dentro `feed-test.template.html`: questo file serve per rileggerlo, per tradurlo se un giorno il panel non è italiano e per le domande di PickFu. Se cambi una frase qui, cambiala anche nel modello HTML e ricostruisci con `build_kit.py`.

Tempo stimato: 90–110 secondi. Su Prolific si dichiarano **2 minuti** (vedi `istruzioni-prolific.md`).

## 0. Dispositivo (solo se la finestra è troppo piccola o il dispositivo è touch)

**Serve un computer con una finestra grande**

Questo studio funziona solo su computer, con la finestra del browser di almeno 1000 × 620 pixel.
- Ingrandisci la finestra a tutto schermo, oppure riduci lo zoom della pagina (Ctrl o Cmd e il tasto −), poi premi «Riprova».
- Se stai usando un telefono o un tablet, torna su Prolific e ritira la partecipazione («Return»): non verrai penalizzato.

## 1. Introduzione

**Studio sulle copertine dei video**

Grazie per partecipare. Lo studio dura circa 2 minuti.

Ti mostreremo una pagina di video simile a quella di YouTube e alcune copertine, poi ti faremo poche domande. Non ci sono risposte giuste o sbagliate: ci interessa la tua prima impressione.

Raccogliamo solo le tue risposte, i tempi di risposta, la dimensione della finestra del browser e il tuo ID Prolific. Nessun altro dato personale.

Alcune copertine riguardano video non ancora pubblicati: per favore non fare screenshot e non condividerle.

[Inizia]

## 2. Controllo di attenzione (all'inizio, come chiede Prolific)

**Prima di iniziare**

Per mostrare che leggi con attenzione, in questa domanda seleziona «Verde».
- Rosso · Blu · Verde · Giallo

[Avanti]

Chi sbaglia esce dall'analisi. Su uno studio sotto i 5 minuti Prolific permette di rifiutare anche per un solo errore; il default del kit è **approvare tutti** ed escludere dall'analisi.

## 3. Feed a tempo (solo `site/`, opzione (a))

**La pagina dei video**

Immagina di aprire YouTube e di trovare questi video nella pagina iniziale.

La pagina resterà visibile per **3 secondi**, poi le copertine spariranno. Guardala come faresti di solito, senza studiarla.

[Mostra la pagina] → croce di fissazione 0,8 s → 9 copertine per 3 s → riquadri vuoti

**D1. Quale di questi video apriresti? Clicca il riquadro dove si trovava.**
[Non ricordo / nessuno]

## 4. Promessa e pubblico (sempre)

**Una copertina**

Ora vedrai per **3 secondi** la copertina di uno dei video della pagina. Poi ti faremo due domande.
(senza feed: «la copertina di un video»)

[Mostra la copertina] → la copertina del braccio, 360 px, per 3 s → riquadro vuoto

**D2. Cosa promette questo video? Scrivi una frase.** (testo libero, obbligatorio)

**D3. A chi è rivolto, secondo te? Bastano poche parole.** (testo libero, obbligatorio)

Se manca una risposta: «Rispondi a tutte e due le domande (anche «non so» va bene).»

## 5. Testa a testa (una schermata per coppia)

**D4. Quale dei due video apriresti?**
Clicca una copertina · 1 di 3

Due copertine a 360 px affiancate, con i segnaposto grigi sotto (oppure lo stesso titolo su tutte e due, se `h2h.title` è impostato). Ordine delle coppie e lati a caso per ogni persona.

## 6. Profilo

**Ultime due domande**

**D5. Quanto spesso guardi su YouTube video o podcast su [topic]?** (`topic` nella configurazione; senza, «tecnologia, startup o business»)
- Quasi ogni giorno · Ogni settimana · Qualche volta al mese · Raramente o mai

**D6. Prima di oggi conoscevi il podcast «[show_name]»?**
- Sì · No · Non sono sicuro/a

[Invia le risposte]

Chi risponde «Sì» esce dall'analisi principale (non è pubblico freddo); `analizza.py` riporta l'esito anche includendolo.

## 7. Fine

Grazie! Risposte registrate. Ti stiamo riportando su Prolific… (se non succede nulla: «clicca qui»)

---

## Domande per PickFu

PickFu traduce da solo le domande scritte in inglese; se le scrivi in italiano non le tocca. Le risposte arrivano tradotte in inglese, con il testo originale disponibile («Original text»).

- **Testa a testa (2 opzioni)**: «Stai scorrendo YouTube e vedi questi due video. Quale apriresti?»
- **Classifica (Ranked, 3 opzioni)**: «Stai scorrendo YouTube e vedi questi tre video. Mettili in ordine, da quello che apriresti per primo a quello che apriresti per ultimo.»
- La richiesta del perché la aggiunge PickFu (commento obbligatorio). Non serve una domanda «cosa promette»: si codificano i commenti.
