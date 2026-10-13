// Elementi di brand riusabili: anello d'accento (motivo della famiglia editorial), marchio editoriale (logo o anello +
// nome), firma testuale dei brand generici, cursore, marchio (logo, firma o nome), fondi (carta con trama, tela morbida
// dalle tinte degli accenti, fondo pieno con griglia). Colori e font sempre dal Theme (token del brand).
import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {alpha, mix, Theme} from '../lib/brand';
import {ramp} from '../lib/anim';

// Archi dell'anello (viewBox 24): alto→destra, →basso, →sinistra, →alto (colori da theme.ring).
const ARCS = [
  'M12 2.5A9.5 9.5 0 0 1 21.5 12',
  'M21.5 12A9.5 9.5 0 0 1 12 21.5',
  'M12 21.5A9.5 9.5 0 0 1 2.5 12',
  'M2.5 12A9.5 9.5 0 0 1 12 2.5',
];

/**
 * Anello in quattro archi (motivo della famiglia editorial, colori da theme.ring). `progress` 0→1 disegna i quattro
 * archi in sequenza oraria; `strokeWidth` in unità del viewBox 24; `inner` = disco carta interno; `initial` = iniziale
 * del brand al centro (simbolo di ripiego quando lo stile non dà un logo).
 */
export const Ring: React.FC<{
  size: number;
  theme: Theme;
  progress?: number;
  strokeWidth?: number;
  initial?: number; // 0..1 opacità/scala dell'iniziale al centro (0 = nascosta)
  inner?: boolean;
  style?: React.CSSProperties;
}> = ({size, theme, progress = 1, strokeWidth = 3, initial = 0, inner = false, style}) => {
  // Box stretto attorno all'anello (raggio 9.5 + mezzo tratto) così `size` = diametro esterno.
  const o = 2.5 - strokeWidth / 2;
  const s = 19 + strokeWidth;
  const letter = (theme.name || theme.slug || '?').trim().charAt(0).toUpperCase();
  return (
    <svg width={size} height={size} viewBox={`${o} ${o} ${s} ${s}`} style={{overflow: 'visible', ...style}}>
      {ARCS.map((d, i) => {
        const p = Math.min(1, Math.max(0, progress * 4 - i));
        return (
          <path
            key={d}
            d={d}
            fill="none"
            stroke={theme.ring[i]}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray="1 1"
            strokeDashoffset={1 - p}
            opacity={p > 0.001 ? 1 : 0}
          />
        );
      })}
      {inner ? <circle cx="12" cy="12" r="8.1" fill={theme.bg} /> : null}
      {initial > 0.001 ? (
        <text
          x="12"
          y="12"
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily={theme.display}
          fontSize={11}
          fill={theme.fg}
          opacity={initial}
          transform={`translate(12 12) scale(${0.85 + 0.15 * initial}) translate(-12 -12)`}
        >
          {letter}
        </text>
      ) : null}
    </svg>
  );
};

/** Marchio della famiglia editorial: il logo dello stile se c'è, altrimenti anello d'accento con l'iniziale. */
export const EditorialMark: React.FC<{theme: Theme; size: number; progress?: number; initial?: number}> = ({theme, size, progress = 1, initial = 1}) => {
  if (theme.look.logo) return <Img src={staticFile(theme.look.logo)} style={{height: size, width: 'auto', display: 'block'}} />;
  return <Ring size={size} theme={theme} progress={progress} initial={initial} inner strokeWidth={3} />;
};

/** Font della firma: mono col motivo terminal, display altrimenti. */
export const sigFont = (theme: Theme): string => (theme.look.motif === 'terminal' ? theme.mono : theme.display);

/**
 * Firma testuale del brand (style.signature) o altro testo nello stesso stile: con `accentPrefix` il primo
 * carattere è nell'accento (l'unico della composizione), il resto nel colore del testo; cursore a blocco opzionale.
 */
export const Signature: React.FC<{
  theme: Theme;
  size: number;
  text?: string | null;
  accentPrefix?: boolean;
  color?: string;
  cursor?: boolean;
  weight?: number;
  style?: React.CSSProperties;
}> = ({theme, size, text, accentPrefix, color, cursor = false, weight = 600, style}) => {
  const t = text ?? theme.look.signature ?? theme.name;
  const pre = (accentPrefix ?? theme.look.accentPrefix) && t.length > 0;
  return (
    <span style={{fontFamily: sigFont(theme), fontWeight: weight, fontSize: size, color: color ?? theme.fg, lineHeight: 1, whiteSpace: 'pre', ...style}}>
      {pre ? <span style={{color: theme.accent}}>{t.slice(0, 1)}</span> : null}
      {pre ? t.slice(1) : t}
      {cursor ? <Cursor theme={theme} /> : null}
    </span>
  );
};

/** Marchio dei brand generici: logo (style.logo) se c'è, altrimenti la firma, altrimenti il nome del brand. */
export const BrandMark: React.FC<{theme: Theme; size: number; cursor?: boolean; weight?: number}> = ({theme, size, cursor, weight}) => {
  if (theme.look.logo) return <Img src={staticFile(theme.look.logo)} style={{height: size * 1.2, width: 'auto', display: 'block'}} />;
  return <Signature theme={theme} size={size} cursor={cursor ?? theme.look.cursor} weight={weight} />;
};

/** Cursore a blocco che lampeggia ogni ~0.5 s (frame-driven). */
export const Cursor: React.FC<{theme: Theme; color?: string; solid?: boolean; widthEm?: number}> = ({
  theme,
  color,
  solid = false,
  widthEm = 0.48,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const on = solid || Math.floor(frame / Math.round(fps * 0.5)) % 2 === 0;
  return (
    <span
      style={{
        display: 'inline-block',
        width: `${widthEm}em`,
        height: '0.9em',
        marginLeft: '0.08em',
        transform: 'translateY(0.1em)',
        background: color ?? theme.fg,
        opacity: on ? 1 : 0,
      }}
    />
  );
};

/** Carta con una trama diagonale leggerissima (famiglia editorial). */
export const PaperField: React.FC<{theme: Theme; unit: number; texture?: boolean}> = ({theme, unit, texture = true}) => (
  <AbsoluteFill
    style={{
      backgroundColor: theme.bg,
      backgroundImage: texture
        ? `repeating-linear-gradient(-58deg, transparent 0px, transparent ${26 * unit}px, ${alpha(theme.fg, 0.012)} ${26 * unit}px, ${alpha(theme.fg, 0.012)} ${52 * unit}px)`
        : undefined,
    }}
  />
);

/** Tela morbida: tinte degli accenti del brand mescolate alla carta, più tenue dei colori pieni. */
export const PastelField: React.FC<{theme: Theme; drift?: number}> = ({theme, drift = 0}) => {
  const p = theme.pastel;
  const soft = (c: string, t: number) => mix(c, theme.bg, t);
  const d = drift * 6; // spostamento lento dei centri, in %
  return (
    <AbsoluteFill
      style={{
        backgroundColor: soft(p.t2, 0.45),
        backgroundImage: [
          `radial-gradient(75% 95% at ${-5 + d}% ${10 - d}%, ${soft(p.t1, 0.05)} 0%, ${alpha(soft(p.t1, 0.05), 0)} 100%)`,
          `radial-gradient(60% 70% at ${8 + d}% ${105 - d}%, ${soft(p.t3, 0.62)} 0%, ${alpha(soft(p.t3, 0.62), 0)} 100%)`,
          `radial-gradient(70% 80% at ${105 - d}% ${105 - d}%, ${soft(p.t4, 0.22)} 0%, ${alpha(soft(p.t4, 0.22), 0)} 100%)`,
          `radial-gradient(60% 70% at ${95 - d}% ${0 + d}%, ${soft(p.t2, 0.2)} 0%, ${alpha(soft(p.t2, 0.2), 0)} 100%)`,
        ].join(', '),
      }}
    />
  );
};

/** Fondo pieno dei brand generici, con griglia hairline appena percettibile (style.grid). */
export const GridField: React.FC<{theme: Theme; unit: number; grid?: boolean}> = ({theme, unit, grid = true}) => {
  const ink = theme.family === 'editorial' ? '#ffffff' : theme.fg;
  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        backgroundImage: grid
          ? `linear-gradient(${alpha(ink, 0.028)} 1px, transparent 1px), linear-gradient(90deg, ${alpha(ink, 0.028)} 1px, transparent 1px)`
          : undefined,
        backgroundSize: grid ? `${80 * unit}px ${80 * unit}px` : undefined,
        backgroundPosition: grid ? `${-1 * unit}px ${-1 * unit}px` : undefined,
      }}
    />
  );
};

/** Fondo pieno della famiglia del brand (carta / pastello / fondo generico). */
export const BrandField: React.FC<{theme: Theme; unit: number; variant?: 'paper' | 'pastel' | 'ink' | 'dark'}> = ({
  theme,
  unit,
  variant,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  if (theme.family !== 'editorial') return <GridField theme={theme} unit={unit} grid={theme.look.grid} />;
  if (variant === 'dark') return <GridField theme={theme} unit={unit} />;
  if (variant === 'pastel') return <PastelField theme={theme} drift={ramp(frame, 0, durationInFrames)} />;
  if (variant === 'ink') return <AbsoluteFill style={{backgroundColor: theme.fg}} />;
  return <PaperField theme={theme} unit={unit} />;
};
