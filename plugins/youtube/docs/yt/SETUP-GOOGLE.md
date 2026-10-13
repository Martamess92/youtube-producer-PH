# Setup Google Cloud — analytics in sola lettura

Tempo: circa 15 minuti. È facoltativo: senza, il plugin lavora lo stesso (montaggio, Shorts, thumbnail, capitoli, ricerca pubblica con yt-dlp). Serve per leggere i numeri del tuo canale (retention, sorgenti di traffico, CTR) e i numeri pubblici dei canali concorrenti via API.

Va fatto **il giorno in cui colleghi un canale**: CTR e impressioni arrivano solo dai job della Reporting API, e un job appena creato recupera al massimo 30 giorni di storico. Ogni giorno di ritardo è storico perso.

Niente di quello che segue dà permessi di scrittura: l'agente legge, non pubblica, non cambia titoli o thumbnail.

`<studio_dir>` è lo `studio_dir` di `yt-config` (default `~/youtube-studio`). I comandi `yt-*` sono nel PATH della sessione Claude Code finché il plugin è attivo: lanciali da Claude Code (chiedendolo a Claude, o con `!` davanti), non dal Terminale.

## 0. Un progetto per chi possiede i canali, non uno per persona

Le policy degli sviluppatori YouTube chiedono un solo progetto Google Cloud per ogni "client" che usa le API e vietano di moltiplicare progetti o chiavi per aggirare la quota (`knowledge/11-compliance-safety.md` §4.1). In pratica:

- **Lavori da solo sul tuo canale**: crea il tuo progetto (passi 1–3).
- **Lavorate in più persone sugli stessi canali** (un team, uno studio): un solo progetto per il team. Chi lo amministra passa `client_secret.json` e `api_key` agli altri fuori da ogni repo e da ogni chat condivisa; ognuno li copia in `<studio_dir>/secrets/` (cartella 700, file 600). Gli altri saltano i passi 1–3.
- **Canale di un cliente**: si usa il progetto di chi lavora per il cliente; il cliente autorizza con il suo account (passo 4) e può revocare l'accesso quando vuole.

Il token OAuth (`token-<slug>.json`) invece è personale: ognuno lo crea sul suo Mac con `yt-auth` (passo 4).

## 1. Progetto e API

1. Apri https://console.cloud.google.com e crea un progetto, per esempio **youtube-producer-<nome-team>**.
2. *API e servizi → Libreria*: abilita queste tre API:
   - **YouTube Data API v3**
   - **YouTube Analytics API**
   - **YouTube Reporting API**

## 2. Schermata di consenso OAuth

1. *Google Auth Platform* (o *API e servizi → Schermata consenso OAuth*):
   - Tipo utente: **Esterno**
   - Nome app: per esempio **YouTube Producer**; email di supporto e dello sviluppatore: quella di chi amministra il progetto
2. *Pubblico / Audience* → **Pubblica app** («In produzione»).
   In modalità «Test» i token scadono dopo 7 giorni e l'agente perderebbe l'accesso ogni settimana.
3. Non serve la verifica di Google per un uso interno. Al primo accesso Google mostra «App non verificata» → *Avanzate* → *Vai a <nome app>*. È normale per un'app che non è nello store.

## 3. Credenziali

1. *Credenziali → Crea credenziali → ID client OAuth* → tipo **App desktop** → nome per esempio «youtube-producer-cli».
   Scarica il JSON e salvalo come:
   `<studio_dir>/secrets/client_secret.json`
2. *Credenziali → Crea credenziali → Chiave API* → *Modifica chiave → Restrizioni API* → solo **YouTube Data API v3**. Copia la chiave in un file:
   `<studio_dir>/secrets/api_key` (solo la chiave, una riga)

Non incollare mai client secret o chiave in chat: restano nella cartella `secrets/` (permessi 700, fuori da ogni repo).

## 4. Autorizza il canale e crea i job

Lo slug è quello del profilo del canale (`~/.config/youtube-producer/channels/<slug>.md`).

```bash
yt-auth --channel <slug>
```

Nel browser scegli l'account e poi il canale giusto: se il canale è un Brand Account, Google chiede quale canale usare (scegli il canale, non l'account personale). Lo script stampa il canale autorizzato. Per il canale di un cliente, il comando lo lancia la persona del cliente che gestisce il canale, con il suo account Google (per esempio in una call con condivisione schermo): tu non ricevi e non chiedi password.

```bash
yt-reporting-setup --channel <slug> --list   # prima guarda se i job esistono già
yt-reporting-setup --channel <slug>          # solo se mancano
```

I job Reporting appartengono al canale: se un'altra persona li ha già creati, non crearne altri.

## 5. Verifica

```bash
yt-auth --channel <slug> --check
yt-reporting-setup --channel <slug> --list
yt-doctor --channel <slug>
```

`yt-auth --check` stampa l'id del canale: scrivilo nel profilo (`channel.id`). I primi report arrivano in 24–48 ore dalla creazione dei job; da lì l'agente li scarica con `yt-collect`. Per usare i numeri calcolati (moltiplicatori outlier, confronti con la mediana) chi amministra il progetto deve accettare l'emendamento «derived metrics» delle policy (`knowledge/11-compliance-safety.md` §4.4); fino ad allora l'agente mostra i numeri grezzi.

## Revocare l'accesso

Dal tuo account Google: *Sicurezza → App di terze parti con accesso all'account* → rimuovi l'app. Il file del token in `<studio_dir>/secrets/` si può cancellare a mano.
