# video-use — NOTICE (codice vendorizzato)

**Upstream**: https://github.com/browser-use/video-use
**Commit fissato**: `43cfc566833548093455c9d4a46bd69913b7e552`
**Licenza**: MIT — Copyright (c) 2026 Browser Use (testo integrale in `scripts/yt/vendor/video_use/LICENSE` del plugin)
**Scaricato**: 2026-10-11 con `gh api repos/browser-use/video-use/contents/<PATH>?ref=<SHA>` (base64 decodificato), nessun `git clone`, nessun installer.
**Destinazione**: `scripts/yt/vendor/video_use/` del plugin (percorsi stabili, importati dai comandi `lib/`)

## File vendorizzati

| File | SHA-256 del file upstream (prima delle patch) | Usato da |
|---|---|---|
| `helpers/pack_transcripts.py` → `pack_transcripts.py` | `f9e419def5f0a014d5e1fd16fdad801013ae068854c1d474c3492297e2304f4b` | `yt-pack` (`group_into_phrases`) |
| `helpers/timeline_view.py` → `timeline_view.py` | `69aee88e4204f86127740cca9de6a6eaa75a558df1bb07745dd62f69a3c2e9cf` | `yt-timeline-view` (`find_silences`, `load_font`, palette) |
| `helpers/render.py` → `render.py` | `6bbde45ad5929c7c94fa068996f81e0c44b55a9c9dedcf716fc24c071a5c8dd7` | `yt-edl-render` (builder T3) |
| `helpers/grade.py` → `grade.py` | `f5df58e81f31c95a621ffba5973fd866f6662fc481a36ebd37a2e68eb81220c2` | importato da `render.py` (preset e auto-grade) |
| `LICENSE` | `5afa3d97bf1e6f998d587fa101e3fe0d0c416840b7fe77bcd6ae97690a334631` | — |

**Non vendorizzati di proposito**: `helpers/transcribe.py` e `helpers/transcribe_batch.py`, che chiamano l'API ElevenLabs Scribe (a pagamento, cloud). Al loro posto c'è `yt-transcribe` (whisper.cpp locale), che produce parole con lo stesso significato (`start`/`end` in secondi, testo, speaker).

## Revisione di sicurezza (2026-10-11)

I quattro file sono stati letti per intero prima della copia. Risultato:
- nessuna chiamata di rete (`requests`, `urllib`, `socket`, `http`): assenti;
- nessun installer, `npx`, `pip`, `curl | sh`: assenti;
- nessun `shell=True`, `eval`, `exec`, `os.system`: assenti;
- unici processi esterni: `ffmpeg` / `ffprobe` locali con argomenti in lista.

## Modifiche locali

Ogni file porta in testa un commento con origine, SHA, licenza e l'elenco delle modifiche. In sintesi:

1. **Tutti i file tranne `pack_transcripts.py`**: `"ffmpeg"` / `"ffprobe"` (cercati nel `PATH`) sostituiti dalle costanti `FFMPEG` / `FFPROBE` = ffmpeg-full per percorso assoluto (`/opt/homebrew/opt/ffmpeg-full/bin/…`, sovrascrivibili con `YT_FFMPEG` / `YT_FFPROBE`, gli stessi env di `ytcore`). Il `ffmpeg` minimale di Homebrew non ha libass/zscale.
2. **Hook `INPUT_ARGS`** (lista, vuota di default = comportamento upstream), inserito prima del `-i` della sorgente in:
   - `render.extract_segment()`,
   - `grade._sample_frame_stats()`,
   - `timeline_view.extract_frames()` e `timeline_view.compute_envelope()`.
   Chi importa può impostare ad esempio `render.INPUT_ARGS = ["-hwaccel", "videotoolbox", *ytcore.aac_decoder_args(workdir)]` per decodificare in hardware l'HEVC Main10 4K e l'AAC con il decoder deciso dalla policy del toolkit (di solito il nativo float, `aac_at` solo se `yt-ingest` lo sceglie: `knowledge/05-editing-rules.md` §11). I commenti nei file copiati mostrano ancora l'esempio storico con `"-c:a", "aac_at"`: non sono stati toccati per non cambiare gli SHA-256 registrati qui; vale questa nota (aggiornata 2026-10-11).
3. **`render.py`**: l'import di `grade` funziona sia come package (`from video_use import render` → `from .grade`) sia come modulo top-level (`sys.path` sulla cartella → `from grade`).
4. **`timeline_view.py`**: la cartella di output di default della CLI è `./timeline_view/` (cwd) invece di `<cartella del video>/edit/verify/`, così la CLI non scrive mai accanto a un originale (es. `~/Downloads`).
5. **`pack_transcripts.py`**: nessuna modifica al codice (solo intestazione).

Non modificati di proposito: encoder e scala di `render.py` (libx264 1080p upstream), stile sottotitoli, loudnorm. Il preset di consegna (VideoToolbox, 4K) appartiene al chiamante (`yt-edl-render`).

## Come aggiornare

1. Scegliere il nuovo commit upstream e leggerne il diff per intero (codice di terzi = non fidato).
2. Riscaricare con `gh api` allo SHA nuovo, ricalcolare gli SHA-256 qui sopra.
3. Riapplicare le modifiche 1–4 e aggiornare intestazioni e questa nota.
4. Rieseguire i test di `yt-pack`, `yt-timeline-view` e `yt-edl-render`.

## Attribuzione

Pattern e codice dei moduli sopra: **video-use** di Browser Use (MIT). Le 12 regole di produzione di video-use (SKILL.md) sono riprese, parafrasate, nel knowledge pack (`05-editing-rules`).
