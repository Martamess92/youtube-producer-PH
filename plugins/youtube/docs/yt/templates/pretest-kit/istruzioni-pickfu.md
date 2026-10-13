# Pre-test su PickFu — passi per l'operatore

> Alternativa a Prolific quando serve una risposta veloce o non c'è tempo per mettere online la pagina. PickFu non ospita pagine esterne: niente feed a tempo, solo le copertine. Tutto a mano: account, pagamento e lancio li fa l'operatore. Etichette dei menu del 2026-10-12: se l'interfaccia è cambiata, cerca la voce equivalente.

**Cosa serve**: la cartella `pickfu/` creata da `build_kit.py` (copertine a 1280×720 con nomi neutri) e `ipotesi.md` compilata. Il file `pickfu/chiave.json` dice quale braccio è ogni opzione: **non si carica**.

## Costo [ufficiale, pagina prezzi di PickFu]

- Circa $1 a risposta con il piano a consumo, minimo $15 a sondaggio; ogni tratto di targeting aumenta il prezzo per risposta.
- **Testa a testa, 50 risposte, Italia, 1 tratto: ≈ $70** (stima della sintesi del 2026-10-12).
- Più di due opzioni (Ranked) costano di più: il prezzo esatto compare nel riepilogo del sondaggio («Survey overview») mentre lo costruisci. Controllalo prima di pagare.

## Quale sondaggio

| Tipo | Opzioni | Cosa dice | Quando |
|---|---|---|---|
| **Head-to-Head** (default) | 2 | Quale delle due apriresti, con un commento | Il budget è ≈ $70: candidata migliore contro il controllo |
| Ranked | 3–8 | Classifica completa; ogni coppia si ricava dalle classifiche individuali | Se il riepilogo mostra un prezzo accettabile per 3 opzioni |
| Click Test / 5 Second Test | 1 immagine | Clic su un'immagine o ricordo dopo 5 s | Non consigliati qui: un sondaggio per braccio (3 volte il costo) |

Non caricare un collage di più copertine come immagine unica senza l'add-on Click Test: PickFu ferma il sondaggio.

## Passi

1. pickfu.com → accedi → crea un nuovo sondaggio.
2. **Audience**: paese **Italy** (le domande vengono tradotte in automatico; le risposte arrivano tradotte in inglese, con l'originale disponibile). **50 risposte**. Al massimo **un tratto**: l'età (18–44 o la fascia più vicina) oppure, se esiste per l'Italia, un interesse vicino al tema del canale. Più tratti allungano molto i tempi sul panel italiano.
3. **Tipo**: Head-to-Head. Carica le due opzioni da `pickfu/` (con la `chiave.json` controlla quale file è quale braccio: di solito la candidata scelta e il controllo).
4. **Domanda** (in italiano, PickFu non la modifica): «Stai scorrendo YouTube e vedi questi due video. Quale apriresti?»
   - Con Ranked: «Stai scorrendo YouTube e vedi questi tre video. Mettili in ordine, da quello che apriresti per primo a quello che apriresti per ultimo.»
5. Controlla il prezzo nel riepilogo → paga → lancia.
6. A fine raccolta:
   - Head-to-Head: annota i voti per opzione e scarica o copia i commenti in `<test>/risultati/pickfu_commenti.txt` (senza nomi o dati dei rispondenti).
   - Ranked: per ogni coppia conta quante persone hanno messo X sopra Y nelle classifiche individuali.
7. Dai i numeri all'agente:
   ```bash
   python3 <kit>/analizza.py pickfu --pair A ab1 --counts <voti A> <voti ab1>
   # Ranked, più coppie (correzione di Holm automatica):
   python3 <kit>/analizza.py pickfu --pair A ab1 --counts 31 19 --pair C ab1 --counts 27 23
   ```
   Con 50 risposte e una sola coppia un braccio vince con **almeno 33 su 50**; sotto è «pari». Con due coppie primarie il primo passo di Holm chiede 34 su 50.
8. L'agente codifica i commenti (temi ricorrenti, citazioni no) e scrive la riga `ab_tests` con `panel: pickfu` (modello in `risultati-template.md`).
