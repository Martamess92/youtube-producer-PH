# Brief troupe — Camera fissa stretta sull'ospite (e sugli host)

> Modello per il team di produzione. Si compila tra [parentesi quadre], si stampa (una pagina) e si manda insieme alla convocazione. Regola di origine: `knowledge/07-thumbnails.md` §10.6 (niente sessione foto: una camera dedicata).

**Episodio**: [slug] · **Data e luogo**: [AAAA-MM-GG, città, location] · **Ospite**: [nome] · **Referente del canale**: [nome, telefono]

**Perché.** Le copertine (thumbnail) di YouTube e Spotify nascono dai frame del video. In un master montato con l'ospite nel riquadro il volto è spesso alto circa 250 px su 2160: ingrandito diventa morbido. Con una camera stretta il volto arriva già grande e nitido. **Non facciamo sessioni foto e non chiediamo pose**: basta questa camera accesa per tutta la registrazione.

## Camere

- **Ospite**: 1 camera fissa dedicata, solo per lui o lei.
- **Host** (se ci sono camere libere): 1 per ogni host, stesse impostazioni. Se ce n'è una sola in più, va sull'ospite.

## Inquadratura

- Orizzontale 16:9, **testa e spalle**. Il volto (dalle sopracciglia al mento) occupa circa il **35–45 % dell'altezza** del quadro.
- **Aria sopra i capelli**: almeno il 10 % del quadro. Testa, orecchie e capelli mai tagliati dal bordo.
- **Spalle e microfono in campo**: il microfono si vede, ma sta di lato o sotto il mento e non copre bocca e viso.
- Camera **accanto all'host che fa le domande**, all'altezza degli occhi: l'ospite guarda quasi in macchina (10–25° di lato).
- Camera ferma per tutta la registrazione: niente zoom, niente reinquadrature.

## Ottica e messa a fuoco

- **85–110 mm equivalenti a circa 2 m.** Con un telefono: teleobiettivo 4× o 5×, mai l'1× da vicino (deforma il viso). Su iPhone l'app Blackmagic Camera (gratuita) blocca otturatore, ISO e bilanciamento.
- Diaframma f/4–5,6 su full frame: occhi, occhiali e orecchie a fuoco.
- Messa a fuoco sul volto (eye-AF continuo) oppure bloccata sulla distanza della sedia.

## Formato

- **4K UHD 3840×2160**, stesso frame rate delle camere principali (25 o 30p).
- **Rec.709 standard (SDR)**: niente LOG, niente HDR.
- Codec alla qualità più alta disponibile (ProRes 422 HQ, oppure HEVC 10 bit ad alto bitrate).
- **Otturatore 1/100 s**, sicuro con la rete elettrica a 50 Hz. 1/200 s solo se una prova di 10 s non mostra bande con le luci del posto. Mai più lento di 1/100.
- **Bilanciamento del bianco ed esposizione bloccati** (niente automatico). ISO il più basso che la luce consente.
- Alimentazione esterna e spazio per almeno [90] minuti.

## Luce

- **Chiave morbida** (softbox 60–90 cm, una finestra o ombra aperta) a 30–45° di lato e poco sopra gli occhi.
- **Schiarita** dal lato opposto, circa uno stop sotto (pannello bianco o riflettore).
- Facoltativa una luce sui capelli da dietro, 1–1,5 stop sotto la chiave. Una gelatina nei colori del canale va bene: è luce vera, non un ritocco.
- **Occhiali**: alza la luce e spostala di lato finché il riflesso esce dalle lenti; controlla al 100 % sul monitor.
- Niente schermi LED o monitor in quadro: fanno bande e dominanti.

## Sfondo e separazione

- Ospite ad **almeno 1,5 m dal fondo**, con il fondo **almeno 1 stop più scuro** del volto.
- **Niente muro colorato** (arancio, rosso) subito dietro la testa: tinge i capelli e sporca lo scontorno.
- Dietro l'ospite niente persone riconoscibili, schermi con dati o loghi di altri.

## Sincronizzazione e consegna

- Ciak o battito di mani all'inizio, insieme alle camere principali. Primo fotogramma: un cartello con slug e data.
- Durante la registrazione un host segna **3–5 «momenti thumbnail»** (minuto e frase).
- Si consegna il **file originale della camera (ISO), non ricompresso**, insieme al master, con questo nome:
  `[AAAA-MM-GG]_[slug]_stretta-[ospite|host1|host2].[mov|mp4]`
- Il file va nella cartella dell'episodio, in `src/iso/`.

## Controllo prima di partire (2 minuti)

- [ ] Prova di 10 s su un host: volto al 35–45 %, aria sopra la testa, microfono visibile e lontano dalla bocca.
- [ ] Nessuna banda a 1/100 s; bianco ed esposizione bloccati; pelle non bruciata (istogramma).
- [ ] Spazio e batteria per tutta la registrazione.
- [ ] Fondo a più di 1,5 m e più scuro del volto; niente muro colorato dietro la testa.

Domande: [referente del canale, telefono].
