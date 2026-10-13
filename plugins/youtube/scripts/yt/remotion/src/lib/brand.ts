// Brand → Theme. Token e stile arrivano dalle props, iniettati da `yt-remotion`: `tokens` dal tokens.json del
// brand (brand esterno in <brands_dir>/<slug>/ oppure assets/brands/demo del plugin) e `style` da
// <brand>/remotion.json. Il JSON importato qui è solo il default (brand neutro demo) per lo Studio.
// Due famiglie: 'editorial' (carta/inchiostro, token paper+ink, accenti dal brand) e 'generic' (fondo pieno + un accento,
// guidata da `style`).
import demoDefault from '../../../assets/brands/demo/tokens.json';
import {registerMetrics, type Metrics} from './type';

export type BrandTokens = {
  slug?: string;
  name?: string;
  colors?: Record<string, string>;
  accent?: string;
  fonts?: Record<string, {family?: string; file?: string}>;
  [key: string]: unknown;
};

/** Font di un brand esterno: file nella public dir del render (yt-remotion lo collega come brand/…). */
export type FontSpec = {family: string; file: string; weight?: string; metrics?: Partial<Metrics>};

/** Stile delle composizioni generiche (<brand>/remotion.json). Tutto facoltativo. */
export type BrandStyle = {
  fonts?: FontSpec[];
  display?: string; // famiglie (vincono sui token)
  body?: string;
  mono?: string;
  motif?: 'plain' | 'terminal'; // terminal = testo battuto, cursore a blocco, griglia hairline, commenti
  grid?: boolean; // griglia hairline sul fondo
  radius?: number; // raggio card in px @1080p
  signature?: string | null; // firma del brand (badge, intro, end plate, tag del lower third)
  signatureAccentPrefix?: boolean; // primo carattere della firma (e del prefisso numero) nell'accento
  cursor?: boolean; // cursore a blocco dopo firma e testo battuto
  typing?: boolean; // nomi e frasi battuti a macchina
  commentPrefix?: string; // prefisso di ruoli/etichette/kicker (es. '// ')
  lowercaseLabels?: boolean;
  numberPrefix?: string; // prefisso del numero capitolo
  highlight?: 'invert' | 'accent'; // box della parola chiave: negativo fg/bg oppure accento
  logo?: string | null; // immagine del marchio nella public dir (brand/…)
  ring?: 'accent' | 'accents'; // famiglia editorial: anello nell'accento (default) o negli accenti del brand
};

export type Look = {
  motif: 'plain' | 'terminal';
  grid: boolean;
  signature: string | null;
  accentPrefix: boolean;
  cursor: boolean;
  typing: boolean;
  comment: string;
  lowercaseLabels: boolean;
  numberPrefix: string;
  highlight: 'invert' | 'accent';
  logo: string | null;
};

export type Family = 'editorial' | 'generic';

export type Theme = {
  slug: string;
  family: Family;
  name: string;
  bg: string; // campo pieno (paper nella famiglia editorial)
  surface: string; // card
  fg: string; // testo principale
  muted: string; // testo secondario
  line: string; // filetti / hairline
  accent: string; // L'UNICO accento della composizione
  onAccent: string; // testo sopra l'accento
  highlight: string; // box parola chiave (thumbnail)
  onHighlight: string;
  ring: [string, string, string, string]; // archi dell'anello (motivo): l'accento, o gli accenti del brand se `style.ring: "accents"`
  pastel: {t1: string; t2: string; t3: string; t4: string}; // tinte della tela morbida (dagli accenti del brand)
  display: string; // font-family CSS
  body: string;
  mono: string;
  radius: number; // raggio card in px @1080p
  look: Look;
};

const DEFAULTS: Record<string, BrandTokens> = {
  demo: demoDefault as BrandTokens,
};

const fam = (f?: string, fallback = 'sans-serif') => (f ? `'${f}', ${fallback}` : fallback);

/** Stile normalizzato: il motivo terminal accende i suoi default, i flag espliciti vincono. */
export const makeLook = (style?: BrandStyle | null): Look => {
  const s = style ?? {};
  const terminal = s.motif === 'terminal';
  return {
    motif: terminal ? 'terminal' : 'plain',
    grid: s.grid ?? terminal,
    signature: s.signature ?? null,
    accentPrefix: s.signatureAccentPrefix ?? false,
    cursor: s.cursor ?? terminal,
    typing: s.typing ?? terminal,
    comment: s.commentPrefix ?? (terminal ? '// ' : ''),
    lowercaseLabels: s.lowercaseLabels ?? terminal,
    numberPrefix: s.numberPrefix ?? '',
    highlight: s.highlight ?? 'accent',
    logo: s.logo ?? null,
  };
};

/** Normalizza token + stile di qualunque brand in un Theme comune. */
export const makeTheme = (brand: string, tokens?: BrandTokens | null, style?: BrandStyle | null): Theme => {
  const t: BrandTokens = tokens && tokens.colors ? tokens : DEFAULTS[brand] ?? DEFAULTS.demo;
  const c = t.colors ?? {};
  for (const f of style?.fonts ?? []) registerMetrics(f.family, f.metrics);
  // Famiglia stilistica: carta/inchiostro (editorial) oppure generica (fondo pieno + accento).
  const family: Family = c.paper && c.ink ? 'editorial' : 'generic';
  const display = style?.display ?? t.fonts?.display?.family;
  const body = style?.body ?? t.fonts?.body?.family;
  const mono = style?.mono ?? t.fonts?.mono?.family;

  if (family === 'editorial') {
    const NEUTRAL = ['ink', 'paper', 'bg', 'fg', 'muted', 'rule', 'line', 'border', 'surface'];
    const names = ((t.accents as string[] | undefined) ?? []).filter((n) => c[n]);
    const accentKey = (t.accent as string) && c[t.accent as string] ? (t.accent as string) : names[0] ?? Object.keys(c).find((k) => !NEUTRAL.includes(k));
    const accent = (accentKey && c[accentKey]) || '#ff5a2c';
    const acc = names.length ? names.map((n) => c[n]) : [accent];
    const pick = (i: number) => acc[i % acc.length];
    const look = makeLook(style);
    const multi = style?.ring === 'accents';
    return {
      slug: t.slug ?? brand,
      family,
      name: t.name ?? brand,
      bg: c.paper,
      surface: c.paper,
      fg: c.ink,
      muted: c.muted ?? mix(c.ink, c.paper, 0.45),
      line: c.rule ?? mix(c.ink, c.paper, 0.82),
      accent,
      onAccent: c.on_accent ?? c.ink,
      highlight: (typeof t.highlight === 'string' && c[t.highlight]) || accent,
      onHighlight: c.ink,
      // un solo accento per composizione: l'anello è nell'accento; style.ring "accents" lo colora con gli accenti del brand
      ring: multi ? [pick(0), pick(1), pick(2), pick(3)] : [accent, accent, accent, accent],
      pastel: {t1: mix(pick(1), c.paper, 0.35), t2: pick(2), t3: pick(0), t4: pick(1)},
      display: fam(display ?? 'Anton', "'Arial Black', sans-serif"),
      body: fam(body ?? 'Inter', 'Arial, sans-serif'),
      mono: fam(mono ?? body ?? 'Inter', 'monospace'),
      radius: style?.radius ?? 18,
      look,
    };
  }
  const accentKey = (t.accent as string) || 'accent';
  const accent = c[accentKey] ?? c.accent ?? '#2f6bff';
  const bg = c.bg ?? '#111111';
  const look = makeLook(style);
  return {
    slug: t.slug ?? brand,
    family,
    name: t.name ?? brand,
    bg,
    surface: c.surface ?? mix(bg, '#ffffff', 0.04),
    fg: c.fg ?? '#ffffff',
    muted: c.muted ?? '#a3a3a3',
    line: c.border ?? c.line ?? '#2b2b2b',
    accent,
    onAccent: c.on_accent ?? bg,
    highlight: look.highlight === 'invert' ? c.fg ?? '#ffffff' : accent,
    onHighlight: look.highlight === 'invert' ? bg : c.on_accent ?? bg,
    ring: [accent, accent, accent, accent],
    pastel: {t1: accent, t2: accent, t3: accent, t4: accent},
    display: fam(display ?? 'Inter', 'Helvetica, Arial, sans-serif'),
    body: fam(body ?? 'Inter', 'Helvetica, Arial, sans-serif'),
    mono: fam(mono ?? display ?? 'Inter', 'monospace'),
    radius: style?.radius ?? 6,
    look,
  };
};

/** Mescola un colore hex con il bianco/nero o un altro hex (t = 0..1 verso `other`). */
export function mix(hex: string, other: string, t: number): string {
  const p = (h: string) => {
    const s = h.replace('#', '');
    const v = s.length === 3 ? s.split('').map((x) => x + x).join('') : s;
    return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16));
  };
  const a = p(hex);
  const b = p(other);
  const r = a.map((x, i) => Math.round(x + (b[i] - x) * t));
  return `#${r.map((x) => x.toString(16).padStart(2, '0')).join('')}`;
}

export const alpha = (hex: string, a: number): string => {
  const s = hex.replace('#', '');
  const v = s.length === 3 ? s.split('').map((x) => x + x).join('') : s;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
};
