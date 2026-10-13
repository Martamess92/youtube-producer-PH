# Protocollo del pre-test delle thumbnail — Prolific o PickFu

> Modello e procedura. Regole in `knowledge/07-thumbnails.md` §15.2 e §16. L'agente prepara il kit in `<workdir>/thumbs/pretest/<id-test>/` e analizza i risultati; **l'operatore crea lo studio, paga e scarica i risultati a mano**. L'agente non chiama mai il panel né carica file.

## 0. Cosa misura e cosa no

- **Misura** quale di due versioni le persone dichiarano che aprirebbero, e se capiscono la promessa del video.
- **Non misura** il CTR né il tempo di visione. Il braccio vincente entra nel controllo di sicurezza nativo del prossimo episodio nuovo (07 §15.1).
- **Una sola variabile per test**: classe d'espressione, sorgente (camera stretta o master), `guest_style` (`none` o `graphic`), `grade` (`natural` o `mono`), font del titolo (Anton o il font display del brand), accento. Gancio, titolo, persona, posizione nel feed: identici nei due bracci.
- Al traffico di oggi un A/B nativo su una sola variabile finisce quasi sempre «Inconclusivo» (07 §15): per questo le variabili si imparano qui.

## 1. Prima di partire

- [ ] Variabile, ipotesi e regola di decisione scritte **prima** (modello sotto).
- [ ] **OK di una riga dell'ospite** (testo sotto): le copertine con il suo volto arrivano a estranei prima dell'uscita. Senza OK, niente pre-test con il suo volto.
- [ ] Budget e preventivo: Prolific ≈ £32 per 100 risposte (compito di 90 s a £9/h + commissione del 42,8 % per le aziende, IVA se dovuta); PickFu ≈ $70 per 50 risposte con un tratto di targeting, ≈ $140 per 100. Prezzi da ricontrollare sulla pagina del servizio il giorno del test.
- [ ] Decisione dell'operatore sui vicini del feed (§3), scritta nella nota dell'episodio.
- [ ] Stimoli pronti e controllati (§2).

**Modello di ipotesi** (va nella nota dell'episodio e in `thumbs/pretest/<id-test>/ipotesi.md`):

```
Variabile: <classe d'espressione | sorgente | guest_style | grade | font del titolo | accento>
Braccio A: <file, valore della variabile> · Braccio B: <file, valore> · tutto il resto identico
Ipotesi: «Con <B> invece di <A> più persone dichiarano che aprirebbero il video»
Panel: <Prolific | PickFu> · n = 100 · Italia · 25–44 anni
Decisione: vince il braccio con almeno 61 risposte su 100 nel testa a testa; sotto = «pari»
Data: <AAAA-MM-GG> · Costo previsto: <…> · OK dell'ospite: <data>
```

**OK dell'ospite, sempre** (la liberatoria da sola non copre il pre-test). WhatsApp o email, e la risposta va nella nota dell'episodio:

> «Ciao [Nome], per scegliere la copertina della puntata vorremmo mostrare due versioni a un panel di circa 100 persone in Italia, tramite [Prolific/PickFu], prima dell'uscita. Vedono solo le due copertine, con nome e ruolo come saranno pubblicate. Per te va bene?»

## 2. Stimoli (li prepara l'agente)

Cartella `thumbs/pretest/<id-test>/`. `FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`.

1. **I due bracci alla misura servita** (720×405, come li serve YouTube):
   `$FF -v error -y -i <render A>.png -vf "scale=720:405:flags=lanczos" -q:v 3 A_720.jpg` (e lo stesso per B).
2. **Testa a testa**: un'immagine con A a sinistra e B a destra e una con B a sinistra e A a destra (`AB.jpg`, `BA.jpg`), sfondo scuro #0f0f0f:
   `$FF -v error -y -i A_720.jpg -i B_720.jpg -filter_complex "[0][1]hstack,pad=iw+48:ih+48:24:24:color=0x0f0f0f" AB.jpg`
3. **Feed** (solo con l'opzione (a) del §3): la candidata tra 8 vicini, stessa posizione e stessi vicini nei due bracci, **senza `--title`** (altrimenti solo la nostra tile ha un titolo e si riconosce):
   `yt-thumb-qa <render A>.png --out thumbs/pretest/<id-test>/A --grid <wd>/thumbs/grid --pos <n> --seed <s>` (poi B con gli stessi `--pos` e `--seed`), con `n` diverso da 4 (il centro).
   La griglia ha il tema scuro a sinistra e il chiaro a destra; si tiene la metà scura:
   `$FF -v error -y -i A/<stem>_grid.png -vf "crop=iw/2:ih:0:0" A_feed.png`
4. **Controllo**: le due immagini del feed differiscono solo nella nostra tile; nessun testo nelle immagini dice che è un test; nessun dato dell'ospite oltre a quelli della copertina.

## 3. Vicini nel feed: decide l'operatore

Gli 8 vicini sono thumbnail di altri canali. I nostri mock della griglia sono privati (`knowledge/11-compliance-safety.md` §3); mostrarli a un panel a pagamento è uno stimolo di ricerca privato, non una pubblicazione, ma resta una copia mostrata a ~100 estranei: zona grigia [giudizio, non è parere legale].

- **(a) Feed con i vicini veri** della stessa ricerca (il più realistico): solo dentro lo studio privato, mai su una pagina pubblica, cancellati con la cache di ricerca dell'episodio entro 30 giorni.
- **(b) Senza vicini**: solo il testa a testa (§4, compito 2). Nessuna immagine di terzi.

**Default senza decisione scritta: (b).**

## 4. Il compito (circa 90 secondi)

**Filtri del panel**: residenza in Italia, italiano fluente o madrelingua, 25–44 anni. Facoltativo, se il servizio lo offre: un tratto vicino al pubblico del canale, per esempio lavoro o interesse nella tecnologia (ogni tratto in più costa).

**Compito 1 — Feed** (solo con l'opzione (a)): ogni partecipante vede **un solo** feed (A o B, metà e metà), come se scorresse YouTube.
- D1 «Quale video apriresti per primo? Indica la posizione da 1 a 9, da sinistra a destra e dall'alto in basso.»
- D2 (solo la nostra tile, 360 px) «In una frase: cosa promette questo video?»
- D3 «Per chi pensi che sia questo video?»

**Compito 2 — Testa a testa** (sempre): i due bracci affiancati, con lo stesso titolo scritto sotto la domanda; metà dei partecipanti vede `AB.jpg`, metà `BA.jpg`.
- D4 «Quale dei due video apriresti?»
- D5 «Perché? Una frase.»

**Controllo di attenzione**: una domanda del tipo «Per questa domanda scegli "Giallo"». Chi la sbaglia esce dall'analisi; escono anche le risposte vuote o fatte troppo in fretta (sotto i 20 s in tutto).

## 5. Quante risposte e come si decide

Testa a testa, test binomiale esatto a due code, α = 0,05 [inferenza]:

| Risposte valide | Preferenza vera che si riesce a vedere | Potenza | Un braccio vince se ha almeno |
|---|---|---|---|
| 50 | 70/30 | ~78 % | 33 su 50 |
| **100 (default)** | **65/35** | **~83 %** | **61 su 100** |
| 200 | 60/40 | ~79 % | 115 su 200 |

- Sotto la soglia l'esito è **«pari»**: si registra come tale e non conta tra i «~3 risultati nella stessa direzione» (07 §16).
- Feed (compito 1, gruppi separati): con 100 persone per braccio si vede solo una differenza grande nella quota di chi sceglie la nostra tile, per esempio dall'11 % (1 su 9, il caso) al 28 % (potenza ~86 %). Differenze più piccole si riportano come descrittive.
- «Cosa promette»: l'agente codifica ogni risposta come giusta, parziale o sbagliata rispetto all'ipotesi del concept, **senza sapere da quale braccio viene** (prima toglie le etichette dei bracci). Si riporta la quota di «giusta» per braccio.

## 6. Passi su Prolific (l'operatore, a mano)

1. Prepara **due moduli** con un servizio che mostra immagini (per esempio Google Moduli): modulo 1 = feed A + `AB.jpg`, modulo 2 = feed B + `BA.jpg`. Domande D1–D5 e controllo di attenzione come al §4. In fondo, il codice di completamento di Prolific.
2. Crea **due studi** su Prolific, uno per modulo, con gli stessi filtri (§4) e 50 partecipanti ciascuno; nel secondo escludi chi ha partecipato al primo.
3. Ricompensa: almeno la tariffa oraria consigliata da Prolific per un compito di 90 secondi. Controlla il totale con la commissione prima di pubblicare.
4. Pubblica. A fine raccolta scarica i CSV di entrambi gli studi in `thumbs/pretest/<id-test>/results/`.
5. Gestisci le approvazioni secondo le regole di Prolific; i fallimenti del controllo di attenzione escono comunque dall'analisi.

## 7. Passi su PickFu (l'operatore, a mano)

1. Nuovo sondaggio a due opzioni (testa a testa) con `A_720.jpg` e `B_720.jpg`, oppure con i due feed se vale l'opzione (a).
2. Domanda: «Quale di questi due video apriresti?», con il titolo del video nel testo della domanda.
3. Pubblico: Italia, 100 risposte (o 50 se il budget non basta: allora la soglia è 33 su 50), al massimo un tratto di targeting.
4. Chiedi il perché della scelta (la risposta scritta serve alla codifica di «cosa promette»).
5. Controlla il prezzo mostrato prima di pagare; paga.
6. A fine raccolta scarica conteggi e commenti in `thumbs/pretest/<id-test>/results/`.

## 8. Analisi e registrazione (le fa l'agente)

1. Conteggi per braccio, esclusioni con il motivo, decisione con la soglia del §5, quota di «cosa promette» giusta per braccio, temi ricorrenti nei «perché» (senza citare i partecipanti).
2. Riga in `ab_tests` (gli oggetti annidati vengono serializzati da `yt-db`):

```
yt-db add ab_tests '{"channel":"<slug>","video_id":"<id del video, o vuoto se non ancora pubblicato>","kind":"pretest",
 "variants_json":[{"id":"A","file":"thumbs/renders/<slug>_A1.png","variable":"expression_class","value":"intenso"},
                  {"id":"B","file":"thumbs/renders/<slug>_A2.png","variable":"expression_class","value":"sorriso"}],
 "started_at":"<AAAA-MM-GG>","ended_at":"<AAAA-MM-GG>","metric":"stated_preference","winner":"<A|B|vuoto se pari>",
 "result_json":{"panel":"prolific|pickfu","n":100,"n_valid":96,"testa_a_testa":{"A":61,"B":35},"soglia":"61/100",
                "esito":"vince A|pari","feed_quota":{"A":0.18,"B":0.27},"promessa_giusta":{"A":0.62,"B":0.71},
                "costo":"£32","vicini":"a|b","ok_ospite":"<data>"},
 "notes":"pre-test <id-test>: variabile classe d'espressione; ipotesi in thumbs/pretest/<id-test>/ipotesi.md"}'
```

3. **MEMORY.md** dell'agente, nello scoreboard delle thumbnail del canale, una riga: «pretest AAAA-MM-GG · variabile · esito · n».
4. Nella nota dell'episodio: ipotesi, esito, cosa entra nel prossimo controllo di sicurezza nativo.

## 9. Dati e pulizia

- I CSV dei panel contengono ID pseudonimi dei partecipanti: restano nella cartella dell'episodio, mai in un vault né nella repo; nelle note vanno solo i risultati aggregati.
- I feed con le thumbnail di altri canali si cancellano con la cache di ricerca entro 30 giorni (`11-compliance-safety.md` §3).
- I costi del panel sono spese dell'operatore fuori da Claude: si registrano in `result_json`, non nel registro delle chiamate a pagamento (`07` §17).
