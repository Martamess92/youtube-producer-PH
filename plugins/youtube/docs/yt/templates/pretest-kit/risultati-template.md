# Risultati del pre-test — come si analizzano e dove si registrano

> `analizza.py report` scrive da solo `risultati/risultati.md` con questa struttura. Questo modello serve per capire i numeri, per i test fatti su PickFu (conteggi a mano) e per sapere dove registrare l'esito.

## 1. Analisi (la fa l'agente)

```bash
KIT=<plugin>/docs/yt/templates/pretest-kit
T=<cartella-test>
# 1) prima passata: conteggi, test, foglio di codifica alla cieca
python3 $KIT/analizza.py report --config $T/pretest.config.json --csv $T/risultati/risposte.csv --cost "£43"
# 2) codifica: compila la colonna «codice» di risultati/codifica_da_compilare.csv usando solo i codici della
#    configurazione (analysis.promise_codes / audience_codes) e SENZA aprire codifica_chiave.json;
#    salva come risultati/codifica_compilata.csv
# 3) seconda passata con la codifica
python3 $KIT/analizza.py report --config $T/pretest.config.json --csv $T/risultati/risposte.csv \
  --coding $T/risultati/codifica_compilata.csv --cost "£43"
```

Uscite in `risultati/`: `risultati.md` (da leggere), `risultati.json` (tutto), `ab_tests_row.json` (riga per il database), `codifica_da_compilare.csv` e `codifica_chiave.json` (la chiave resta chiusa fino alla fine della codifica).

### Esclusioni (in quest'ordine)

Altro studio o anteprima · ID che inizia con `TEST` (prove interne) · stesso ID Prolific già visto (si tiene la prima risposta) · controllo di attenzione sbagliato · tempo totale sotto `min_total_s` (25 s) · risposte incomplete · chi conosceva già il podcast (con `exclude_knows_show`; l'esito con loro incluso è riportato come sensibilità). Solo per il feed e per la promessa: esposizione con la scheda nascosta o fuori da 2,5–3,7 s.

### Testa a testa: la decisione

Test binomiale esatto a due code contro 50/50, α = 0,05. Le coppie primarie (ogni candidata contro il controllo) si correggono con Holm: la coppia con il p più piccolo deve stare sotto 0,025, l'altra sotto 0,05. Sotto la soglia l'esito è **«pari»**.

| Risposte valide | Vince con almeno (α 0,05) | Primo passo di Holm (2 coppie) | Potenza se la preferenza vera è 65/35 | 70/30 |
|---|---|---|---|---|
| 50 | 33 | 34 | 51 % | 78 % |
| 60 | 39 | 40 | 56 % | 84 % |
| 80 | 50 | 51 | 72 % | 94 % |
| 90 | 55 | 57 | 81 % | 97 % |
| **100** | **61** | **62** | **83 %** | **98 %** |
| 200 | 115 | 117 | 99 % | 100 % |

Per un altro n: `python3 $KIT/analizza.py soglie 96` oppure `binom 58 96`.

Controlli di qualità: la quota di scelte a sinistra deve stare vicina al 50 % (altrimenti la scelta segue il lato, non la copertina); più build nello stesso studio = stimoli cambiati durante la raccolta (avviso nel report).

### Feed a tempo: descrittivo

Per braccio: quante persone scelgono la nostra copertina tra 9 (caso = 1 su 9 = 11 %), con intervallo di Wilson al 95 %, p a una coda contro il caso e Fisher esatto contro il controllo. Con ~33 persone per braccio si vede solo un salto grande (dall'11 % a circa il 30 %, potenza ~80 %). Si riporta anche per tema (scuro, chiaro).

### Cosa promette e a chi è rivolto: codifica alla cieca

Ogni risposta riceve un codice della configurazione senza sapere il braccio (le righe sono mescolate e anonime). Lo script traduce i codici in giusta / parziale / sbagliata con le regole per braccio. Esempio (inventato) per un concept «Il codice non bastava»:

| Codice | Promessa |
|---|---|
| T2 | per vendere un prodotto non basta saper programmare (serve altro oltre al codice) |
| T1 | il codice o la programmazione, senza l'idea di vendere |
| V2 | perché o come una founder ha deciso di vendere la sua azienda (exit) |
| V1 | vendere o una decisione, senza dire cosa |
| S | storia generica di startup, founder o business |
| X | altro, non so, vuoto |

Pubblico: F (founder, startupper, chi crea prodotti digitali, maker) = giusto; P (tech o business generico) = parziale; X = sbagliato.

## 2. Modello dei risultati (per una nota o per PickFu)

```
Pre-test [id-test] · [Prolific | PickFu] · [AAAA-MM-GG → AAAA-MM-GG] · costo [£… | $…]
Variabile: [...] · Vicini: [(a) feed | (b) solo testa a testa] · OK ospite: [data]
Risposte: [n] ricevute · [n] valide · escluse: attenzione [n], troppo veloci [n], duplicati [n], conoscevano il podcast [n]

Testa a testa (α 0,05, Holm sulle primarie):
  [A] vs [ab1]: [k]–[k] su [n] · soglia [61/100] · p [..] · p Holm [..] → [vince A | pari]
  [C] vs [ab1]: [k]–[k] su [n] · soglia [..] · p [..] · p Holm [..] → [...]
  [A] vs [C] (secondaria): [k]–[k] · p [..] → [...]
Feed (3 s, 9 copertine, caso 11 %): ab1 [..] % · A [..] % · C [..] %   (descrittivo)
Promessa giusta: ab1 [..] % · A [..] % · C [..] % · Pubblico giusto: ab1 [..] % · A [..] % · C [..] %
Temi ricorrenti nei perché / nelle promesse: [...]   (senza citare i partecipanti)
Decisione: [quale braccio entra nel prossimo controllo di sicurezza nativo]
```

## 3. Dove si registra

1. **Database** (`yt.db`, tabella `ab_tests`, `kind = "pretest"`): `yt-db add ab_tests "$(cat <cartella-test>/risultati/ab_tests_row.json)"`. Per PickFu, scrivi la riga a mano con gli stessi campi:
   ```
   yt-db add ab_tests '{"channel":"<slug>","video_id":"<id o vuoto>","kind":"pretest",
    "variants_json":[{"id":"A","file":"…","template":"ritratto","lever":"claim","text":"…"},
                     {"id":"ab1","file":"…","template":"duo","lever":"claim","text":"…"}],
    "started_at":"AAAA-MM-GG","ended_at":"AAAA-MM-GG","metric":"stated_preference","winner":"<A | vuoto se pari>",
    "result_json":{"panel":"pickfu","n":50,"n_valid":50,"testa_a_testa":{"A|ab1":{"voti":{"A":33,"ab1":17},"soglia":33,"esito":"vince A"}},
                   "costo":"$70","vicini":"b","ok_ospite":"<data>"},
    "notes":"pre-test <id-test>: <variabile>; ipotesi in <cartella-test>/ipotesi.md"}'
   ```
   Controllo: `yt-db query "SELECT id, kind, winner, started_at FROM ab_tests WHERE kind='pretest' ORDER BY id DESC LIMIT 3"`.
2. **MEMORY.md** dell'agente (`youtube:producer`), sezione `## <slug>`, scoreboard delle thumbnail (≤ 6 righe per canale, 07 §16), una riga: `pretest AAAA-MM-GG · <variabile> · <vince X (k/n) | pari> · n <valide> · <panel>`.
3. **Scoreboard delle variabili** (07 §16): +1 alla colonna del braccio che vince; «pari» va in «Pari» e non conta tra i ~3 risultati nella stessa direzione.
4. **Nota dell'episodio**: ipotesi, esito, cosa entra nel prossimo controllo di sicurezza nativo.
5. **Pulizia**: CSV e commenti restano in `<cartella-test>/risultati/`, mai in un vault né nella repo; sito e Google Modulo cancellati entro 30 giorni (`istruzioni-prolific.md` §6).
