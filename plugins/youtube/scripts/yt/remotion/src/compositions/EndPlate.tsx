// EndPlate — 20 s di schermata finale con 2 slot video 16:9 + area iscrizione, dentro i
// margini di sicurezza. Gli elementi veri si aggiungono in YouTube Studio sopra gli slot
// (regole: ultimi 5–20 s, video ≥25 s, max 4 elementi — support.google.com/youtube/answer/6388789).
// Geometria @1920×1080 (in % del frame): slot A x 8.3–48.5%, slot B x 51.5–91.7%, y 28.7–68.9%;
// cerchio iscrizione Ø 180 px a destra in basso (x 82.3–91.7%, y 74.6–91.3%).
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {z} from 'zod';
import {alpha, makeTheme, Theme} from '../lib/brand';
import {ramp, useUnit} from '../lib/anim';
import {useBrandFonts} from '../lib/fonts';
import {brandFields, timingFields} from '../lib/schema';
import {BrandField, BrandMark, EditorialMark} from '../components/brand';

export const endPlateSchema = z.object({
  ...brandFields,
  ...timingFields,
  headline: z.string(),
  slotLabels: z.array(z.string()).max(2),
  subscribeLabel: z.string(),
  background: z.enum(['paper', 'pastel', 'ink']).optional().describe('solo famiglia editorial (token paper + ink)'),
  showGuides: z.boolean().describe('disegna i segnaposto degli slot (consigliato)'),
});
export type EndPlateProps = z.infer<typeof endPlateSchema>;

// Geometria condivisa (unità 1920×1080)
const M = 160;
const SLOT_W = 772;
const SLOT_H = Math.round((SLOT_W * 9) / 16);
const SLOT_Y = 310;
const GAP = 1600 - 2 * SLOT_W;
const SUB_D = 180;
const SUB_Y = 806;

const PlayGlyph: React.FC<{size: number; color: string}> = ({size, color}) => (
  <svg width={size} height={size} viewBox="0 0 24 24">
    <path d="M8 5.5v13l11-6.5z" fill={color} />
  </svg>
);

const Slot: React.FC<{theme: Theme; u: number; x: number; label?: string; p: number; guides: boolean}> = ({theme, u, x, label, p, guides}) => {
  const ed = theme.family === 'editorial';
  const terminal = theme.look.motif === 'terminal';
  const hair = Math.max(1, Math.round(u));
  return (
    <div style={{position: 'absolute', left: x * u, top: SLOT_Y * u, width: SLOT_W * u, height: SLOT_H * u, opacity: p, transform: `translateY(${(1 - p) * 24 * u}px)`}}>
      {label ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: -50 * u,
            fontFamily: terminal ? theme.mono : theme.body,
            fontWeight: terminal ? 400 : 800,
            fontSize: 24 * u,
            letterSpacing: terminal ? 0 : '0.2em',
            textTransform: terminal || theme.look.lowercaseLabels ? 'none' : 'uppercase',
            color: ed ? theme.fg : theme.muted,
          }}
        >
          {ed ? label : `${theme.look.comment}${theme.look.lowercaseLabels ? label.toLowerCase() : label}`}
        </div>
      ) : null}
      {guides ? (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: (ed ? 22 : theme.radius) * u,
            background: ed ? alpha(theme.bg, 0.5) : theme.surface,
            border: ed ? `${3 * u}px solid ${alpha(theme.fg, 0.12)}` : `${hair}px solid ${theme.line}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <PlayGlyph size={84 * u} color={alpha(theme.fg, ed ? 0.16 : 0.18)} />
        </div>
      ) : null}
    </div>
  );
};

export const EndPlate: React.FC<EndPlateProps> = (props) => {
  const ready = useBrandFonts(props.style);
  const theme = makeTheme(props.brand, props.tokens, props.style);
  const u = useUnit();
  const frame = useCurrentFrame();
  if (!ready) return null;
  const ed = theme.family === 'editorial';
  const terminal = theme.look.motif === 'terminal';
  const hair = Math.max(1, Math.round(u));
  const head = ramp(frame, 2, 16);
  const s1 = ramp(frame, 6, 18);
  const s2 = ramp(frame, 10, 18);
  const sub = ramp(frame, 14, 18);
  const labels = props.slotLabels ?? [];
  return (
    <AbsoluteFill>
      <BrandField theme={theme} unit={u} variant={ed ? props.background ?? 'pastel' : 'dark'} />
      {/* titolo */}
      <div style={{position: 'absolute', left: M * u, top: 104 * u, opacity: head, transform: `translateY(${(1 - head) * 20 * u}px)`}}>
        {ed ? (
          <div style={{fontFamily: theme.display, fontSize: 84 * u, lineHeight: 1, textTransform: 'uppercase', color: theme.fg, letterSpacing: '-0.005em'}}>{props.headline}</div>
        ) : (
          // niente firma qui: l'accento della firma compare una sola volta (in basso)
          <div style={{fontFamily: theme.body, fontWeight: 600, fontSize: 68 * u, letterSpacing: '-0.025em', color: theme.fg}}>{props.headline}</div>
        )}
      </div>
      <Slot theme={theme} u={u} x={M} label={labels[0]} p={s1} guides={props.showGuides} />
      <Slot theme={theme} u={u} x={M + SLOT_W + GAP} label={labels[1]} p={s2} guides={props.showGuides} />
      {/* riga in basso: marchio a sinistra, iscrizione a destra */}
      <div style={{position: 'absolute', left: M * u, top: SUB_Y * u, height: SUB_D * u, display: 'flex', alignItems: 'center', gap: 26 * u, opacity: sub}}>
        {ed ? (
          <>
            <EditorialMark theme={theme} size={96 * u} />
            <div style={{fontFamily: theme.display, fontSize: 58 * u, color: theme.fg, lineHeight: 1}}>{theme.name.toUpperCase()}</div>
          </>
        ) : (
          <BrandMark theme={theme} size={56 * u} weight={600} />
        )}
      </div>
      <div
        style={{
          position: 'absolute',
          right: M * u,
          top: SUB_Y * u,
          height: SUB_D * u,
          display: 'flex',
          alignItems: 'center',
          gap: 30 * u,
          opacity: sub,
          transform: `translateY(${(1 - sub) * 20 * u}px)`,
        }}
      >
        <div
          style={{
            fontFamily: terminal ? theme.mono : theme.body,
            fontWeight: terminal ? 500 : 800,
            fontSize: 30 * u,
            letterSpacing: terminal ? 0 : '0.18em',
            textTransform: terminal ? 'none' : 'uppercase',
            color: theme.fg,
            textAlign: 'right',
          }}
        >
          {props.subscribeLabel}
        </div>
        {props.showGuides ? (
          <div
            style={{
              width: SUB_D * u,
              height: SUB_D * u,
              borderRadius: '50%',
              background: ed ? alpha(theme.bg, 0.5) : theme.surface,
              border: ed ? `${3 * u}px solid ${alpha(theme.fg, 0.12)}` : `${hair}px solid ${theme.line}`,
            }}
          />
        ) : (
          <div style={{width: SUB_D * u, height: SUB_D * u}} />
        )}
      </div>
    </AbsoluteFill>
  );
};
