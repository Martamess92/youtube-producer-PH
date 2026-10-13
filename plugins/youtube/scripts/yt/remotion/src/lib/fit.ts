// Impaginazione del testo display: righe bilanciate + corpo massimo che entra nel box.
// Misura con @remotion/layout-utils (solo dopo il caricamento dei font).
import {measureText} from '@remotion/layout-utils';

export type FitInput = {
  text: string;
  fontFamily: string;
  fontWeight?: number | string;
  letterSpacingEm?: number;
  uppercase?: boolean;
  maxWidth: number;
  maxHeight: number;
  lineHeight: number; // moltiplicatore del corpo
  maxLines: number;
  maxFontSize: number;
  minFontSize?: number;
  extraEmPerLine?: number; // padding orizzontale extra (es. box evidenziato), in em
};

export type FitResult = {fontSize: number; lines: string[]};

const REF = 100;

const widthAt = (s: string, inp: FitInput): number =>
  measureText({
    text: s,
    fontFamily: inp.fontFamily,
    fontWeight: inp.fontWeight ?? 400,
    fontSize: REF,
    letterSpacing: inp.letterSpacingEm ? `${inp.letterSpacingEm}em` : undefined,
    textTransform: inp.uppercase ? 'uppercase' : 'none',
    validateFontIsLoaded: true,
  }).width;

/** Tutte le spezzature di `words` in esattamente `n` righe (parole ≤ 12: brute force ok). */
const partitions = (words: string[], n: number): string[][] => {
  const out: string[][] = [];
  const rec = (start: number, left: number, acc: string[]) => {
    if (left === 1) {
      out.push([...acc, words.slice(start).join(' ')]);
      return;
    }
    for (let i = start + 1; i <= words.length - left + 1; i++) {
      rec(i, left - 1, [...acc, words.slice(start, i).join(' ')]);
    }
  };
  if (n >= 1 && n <= words.length) rec(0, n, []);
  return out;
};

export const fitBalanced = (inp: FitInput): FitResult => {
  const clean = inp.text.trim();
  const explicit = clean.includes('\n');
  // solo spazi normali: il nbsp tiene unite le parole composte
  const words = clean.split(/[ \t\n]+/).filter(Boolean);
  const candidates: string[][] = [];
  if (explicit) {
    candidates.push(clean.split('\n').map((l) => l.trim()).filter(Boolean));
  } else if (words.length > 12) {
    // testo lungo: greedy su larghezza costante (raro per titoli display)
    const per = Math.ceil(words.length / inp.maxLines);
    const lines: string[] = [];
    for (let i = 0; i < words.length; i += per) lines.push(words.slice(i, i + per).join(' '));
    candidates.push(lines);
  } else {
    for (let n = 1; n <= Math.min(inp.maxLines, words.length); n++) candidates.push(...partitions(words, n));
  }
  let best: FitResult = {fontSize: inp.minFontSize ?? 10, lines: candidates[0] ?? [clean]};
  let bestScore = -Infinity;
  for (const lines of candidates) {
    const widths = lines.map((l) => widthAt(l, inp) / REF + (inp.extraEmPerLine ?? 0));
    const maxW = Math.max(...widths);
    const byWidth = inp.maxWidth / maxW;
    const byHeight = inp.maxHeight / (lines.length * inp.lineHeight);
    const size = Math.min(inp.maxFontSize, byWidth, byHeight);
    // Preferisci il corpo più grande; a parità (cap al max) righe più bilanciate e meno righe.
    const balance = Math.min(...widths) / maxW;
    const score = size * 1000 + balance * 10 - lines.length;
    if (score > bestScore) {
      bestScore = score;
      best = {fontSize: Math.max(inp.minFontSize ?? 0, Math.floor(size)), lines};
    }
  }
  return best;
};
