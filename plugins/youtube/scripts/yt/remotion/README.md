# Remotion — composizioni grafiche di YouTube Producer

Progetto Remotion 4.0.534 (React 19.1.0) con composizioni parametriche guidate dai **token del brand**: colori, font,
accenti e nome arrivano da `tokens.json` (e, facoltativo, da `remotion.json`) del brand scelto con la prop `brand`. Il
plugin include un solo brand, il neutro **`demo`** (`assets/brands/demo/`: carta, inchiostro, tre accenti, Anton + Inter,
wordmark «Il tuo canale»), da sostituire con il brand del tuo canale. Si usa tramite il wrapper `yt-remotion` (nel PATH
del plugin), che inietta token e stile del brand, collega i media e i font del brand in una public dir temporanea e
verifica l'output.

**Licenza.** Remotion è gratuito per le persone singole e per le organizzazioni fino a 3 persone; oltre serve una licenza
aziendale (vedi `docs/yt/vendor/REMOTION_LICENSE_NOTE.md` del plugin). Il toolkit lo usa solo per i brand propri (canale
con profilo `kind: own` o `personal`, o token `"own": true`); per i clienti e per chi non rientra nella licenza gratuita
l'alternativa gratuita è HyperFrames (Apache-2.0).

Installazione: `/youtube:setup` copia questo progetto nella data dir del plugin (`<data>/remotion`, più
`<data>/assets/brands` per l'import dei token di default) ed esegue `npm ci` lì; a ogni render il wrapper risincronizza i
sorgenti, quindi le modifiche a `src/` valgono subito. Se cambia `package-lock.json` serve di nuovo `/youtube:setup`.

```bash
yt-remotion list
yt-remotion render LowerThird --props lt.json --out lower-third.mov        # ProRes 4444 + alpha
yt-remotion render ShortCaptions --props short.json --out short_01.mp4     # H.264 + AAC
yt-remotion still ThumbnailStill --props thumb.json --out thumb.png        # 3840×2160 (scale 3)
yt-remotion still LowerThird --props lt.json --out check.png --frame 75    # QA di un frame
```

Il file props contiene solo ciò che cambia: tutto il resto ha un default in `src/Root.tsx`.
`brand` sceglie i token: prima `<brands_dir>/<slug>/tokens.json` (brand esterni, `yt-config` → `brands_dirs`), poi
`assets/brands/<slug>/tokens.json` del plugin (solo `demo`); `resolution` = `4k` (default) o `1080p`.
I path dei media (`videoSrc`, `cutoutSrc`, `bgImageSrc`, `captionsFile`) possono essere assoluti o relativi al file props.

## Due famiglie, scelte dai token

- **editorial** — token con `colors.paper` e `colors.ink` (come `demo`): campo carta con trama leggera, testo inchiostro,
  titoli nel font display del brand (default Anton) maiuscolo, body Inter, un solo accento (`tokens.accent`) per
  composizione; anello d'accento come motivo (`style.ring: "accents"` lo colora con gli accenti del brand), tela morbida
  `pastel` dalle tinte degli accenti. Marchio: il logo dello stile (`style.logo`) se c'è, altrimenti l'anello con
  l'iniziale del brand.
- **generic** — token con `colors.bg` / `colors.fg`: fondo pieno, un accento, griglia hairline facoltativa, firma testuale;
  si regola con `<brand>/remotion.json` (sotto).

| Composizione | Props principali | Default |
|---|---|---|
| `LowerThird` | `name`*, `role`, `tag` (brand generici: riga nello stile della firma), `position` left/right/auto, `subjectX` (0–1), `maxWidth` (px @1080p, stretta → nome su 2 righe); `align` left/right = alias deprecato | 5 s, trasparente, in basso (title-safe 6%); `position: auto` → lato opposto al soggetto se c'è `subjectX`, altrimenti a sinistra |
| `ChapterCard` | `number`*, `title`*, `label` (Capitolo), `mode` full/overlay, `background` paper/pastel/ink (editorial) | 3 s |
| `ColdOpenTitle` | `hook`*, `highlight` (una parola, box nell'accento), `kicker`, `background` paper/pastel/ink/transparent, `exit` | 2.5 s, taglio secco |
| `IntroSting` | `title` (default: nome del brand), `subtitle` (es. "con: Nome"), `pill`, `exit` | 3 s |
| `EndPlate` | `headline`, `slotLabels` [2], `subscribeLabel`, `showGuides`, `background` (editorial: pastel) | 20 s; slot A x 8.3–48.5 %, slot B x 51.5–91.7 %, y 28.7–68.9 %; cerchio iscrizione x 82.3–91.7 %, y 74.6–91.3 % |
| `ShortCaptions` | `videoSrc` (assente → solo overlay alpha), `captionsFile`, `captionsOffsetSeconds`, `hookText`, `hookSeconds`, `hookY`, `progressBar`, `progressPosition`, `accent` (chiave dei token o hex; default l'accento del brand), `captionFont` display/body, `uppercase`, `maxWordsPerPage` (4), `combineMs` (800), `captionY` (0.64), `videoStartSeconds`, `showSafeZone` | 1080×1920, durata/fps dal video |
| `ThumbnailStill` | `text`* (≤4 parole, `\n` forza l'a capo), `highlight`, `background` pastel/paper/ink/dark/image, `cutoutSrc`, `faceBox`, `side`, `faceHeight` (0.38), `choke`, `badge` (es. EP.08; default: nessuno), `kicker`, `showSafeZones` | 1280×720 → scale 3 |

`*` = obbligatorio (il wrapper si ferma se manca).

`LowerThird`, lato (`resolveLowerThirdSide` in `src/compositions/LowerThird.tsx`): `position: "left"|"right"` vince
sempre; con `position: "auto"` (default) e `subjectX` (centro orizzontale del soggetto principale, 0 = bordo sinistro,
1 = destro: per esempio `x + w/2` del box volto di `thumbvision faces`, che dà già coordinate 0–1) il lower third va
dal lato opposto (`subjectX < 0.5` → destra, altrimenti sinistra); senza `subjectX` vale il vecchio `align` se c'è,
altrimenti sinistra.

```json
{"brand": "demo", "name": "Paolo Bianchi", "role": "Fondatore, Officina Esempio", "subjectX": 0.32}
```

`captionsFile` accetta: `Caption[]` di Remotion, `transcript.words.json` (`words[].w/start/end`), `{captions|words: …}`
oppure `.srt` (tempi per parola stimati: solo fallback).

Regole del brand applicate nel codice: un solo accento per composizione (brand generici: con
`signatureAccentPrefix` l'accento è il primo carattere della firma e nient'altro), testo inchiostro su carta e
sull'accento, primo e ultimo frame vuoti negli overlay, margini title-safe, angoli liberi nelle thumbnail
(basso-destra 230×110, alto-destra 120×80).

## Stile dei brand (`<brand>/remotion.json`)

`yt-remotion` legge `<brands_dir>/<slug>/remotion.json` (facoltativo) e lo passa come prop `style` (un `style` nel file
props vi si sovrappone). La famiglia generic usa tutte le chiavi; la editorial usa `fonts`, `display`, `body`, `mono`,
`radius`, `logo` e `ring`.

| Chiave | Effetto | Default |
|---|---|---|
| `fonts` | `[{family, file, weight, metrics}]`: `file` relativo alla cartella del brand (es. `fonts/X.ttf`), collegato nella public dir; `metrics` = `{asc, desc, cap, descDepth}` in em per i box evidenziati | nessuno (Anton e Inter del plugin sempre caricati) |
| `display`, `body`, `mono` | famiglie (vincono sui token) | dai token, poi Anton (display editorial) e Inter |
| `motif` | `plain` · `terminal` (accende `grid`, `cursor`, `typing`, `commentPrefix: "// "`, `lowercaseLabels`) | `plain` |
| `grid`, `cursor`, `typing`, `lowercaseLabels` | griglia hairline sul fondo, cursore a blocco, testo battuto a macchina, etichette minuscole | dal motivo |
| `signature` | firma testuale (badge della thumbnail, intro, end plate, marchio della cold open) | nessuna (intro: nome del brand) |
| `signatureAccentPrefix` | primo carattere della firma (e del `numberPrefix` dei capitoli) nell'accento | `false` |
| `commentPrefix`, `numberPrefix` | prefisso di ruoli/etichette/kicker; prefisso del numero capitolo | `""` |
| `highlight` | box della parola chiave: `accent` oppure `invert` (fg/bg) | `accent` |
| `radius` | raggio delle card in px @1080p | 6 (editorial 18) |
| `logo` | immagine del marchio (relativa alla cartella del brand) al posto della firma o dell'anello | nessuno |
| `ring` | solo editorial: `accent` (anello nell'accento) o `accents` (archi negli accenti del brand) | `accent` |

```json
{"motif": "terminal", "signature": "/nome", "signatureAccentPrefix": true, "numberPrefix": "/", "highlight": "invert",
 "radius": 2, "fonts": [{"family": "Mono X", "file": "fonts/MonoX-Variable.ttf", "weight": "400 700"}]}
```

Sviluppo: `npm run studio` (anteprima; i media vanno messi in `public/`), `npm run typecheck`.
I font del plugin sono copie OFL di `assets/fonts` in `public/fonts` (Anton, Inter); quelli dei brand esterni stanno
nella cartella del brand e arrivano dalla prop `style.fonts`. Il browser di render è `chrome-headless-shell`
scaricato da Remotion in `node_modules/.remotion` (`node_modules/.bin/remotion browser ensure`, una volta; lo fa anche il wrapper).
