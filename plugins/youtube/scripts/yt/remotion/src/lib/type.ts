// Correzioni tipografiche per i font del brand: box evidenziati centrati sulle maiuscole
// (i font display come Anton hanno un'area di contenuto alta sopra le maiuscole) e spazio per gli accenti
// delle maiuscole italiane (È À Ù…) quando l'interlinea è stretta.
import type React from 'react';

export type Metrics = {asc: number; desc: number; cap: number; descDepth: number};

// Valori in em misurati dai TTF (hhea ascent/descent, altezza della H, discendente reale).
// I brand esterni aggiungono i propri con style.fonts[].metrics (remotion.json → registerMetrics).
const METRICS: Record<string, Metrics> = {
  Anton: {asc: 1.176, desc: 0.329, cap: 0.859, descDepth: 0.122},
  Inter: {asc: 0.969, desc: 0.242, cap: 0.728, descDepth: 0.21},
};

/** Metriche di un font del brand (idempotente: stesso valore a ogni frame). */
export const registerMetrics = (family: string, m?: Partial<Metrics> | null): void => {
  if (!family || !m || METRICS[family]) return;
  const base = METRICS.Inter;
  METRICS[family] = {asc: m.asc ?? base.asc, desc: m.desc ?? base.desc, cap: m.cap ?? base.cap, descDepth: m.descDepth ?? base.descDepth};
};

const metricsFor = (fontFamily: string): Metrics => {
  // la prima famiglia della pila CSS che conosciamo ('Nome', fallback)
  const first = fontFamily.split(',')[0].replace(/['"]/g, '').trim();
  if (METRICS[first]) return METRICS[first];
  const name = Object.keys(METRICS).find((k) => fontFamily.includes(k));
  return name ? METRICS[name] : METRICS.Inter;
};

/**
 * Stile di un box evidenziato (inline-block) con margine visivo `gapEm` uguale sopra le
 * maiuscole e sotto la linea di base (o sotto i discendenti se il testo è minuscolo).
 */
export const markStyle = (fontFamily: string, uppercase: boolean, gapEm = 0.1, padXEm = 0.12): React.CSSProperties => {
  const m = metricsFor(fontFamily);
  const top = uppercase ? m.cap : Math.max(m.cap, 0.75); // ascendenti minuscole ≈ maiuscole
  // line-height interna tale che lo spazio sopra il glifo sia esattamente gapEm
  const L = 2 * (gapEm - m.asc + top) + m.asc + m.desc;
  const baseline = (L - m.asc - m.desc) / 2 + m.asc;
  const bottom = baseline + (uppercase ? 0 : m.descDepth);
  const padBottom = Math.max(0, gapEm - (L - bottom));
  return {
    display: 'inline-block',
    lineHeight: L,
    padding: `0 ${padXEm}em ${padBottom}em`,
    verticalAlign: 'baseline',
  };
};

const ACCENTED_CAPS = /[ÀÁÈÉÌÍÒÓÙÚ]/;

/** Margine sopra una riga MAIUSCOLA con accenti, per non toccare la riga precedente. */
export const accentGap = (line: string, index: number, uppercase: boolean, em = 0.13): number =>
  index > 0 && ACCENTED_CAPS.test(uppercase ? line.toUpperCase() : line) ? em : 0;
