// LowerThird — nome + ruolo, trasparente, 5 s. Primo e ultimo frame vuoti; si muove solo
// in entrata/uscita. Famiglia editorial: card carta, inchiostro, una linguetta nell'accento del brand.
// Brand generici: box pieno con hairline; con lo stile del brand (remotion.json) nome battuto a macchina,
// cursore, tag nello stile della firma (primo carattere nell'accento) e ruolo con prefisso di commento.
import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';
import {alpha, makeTheme, Theme} from '../lib/brand';
import {easeIn, inOut, ramp, useUnit} from '../lib/anim';
import {useBrandFonts} from '../lib/fonts';
import {fitBalanced} from '../lib/fit';
import {brandFields, timingFields} from '../lib/schema';
import {Cursor, Signature} from '../components/brand';

export const lowerThirdSchema = z.object({
  ...brandFields,
  ...timingFields,
  name: z.string().min(1),
  role: z.string(),
  tag: z.string().optional().describe('riga sopra il nome nello stile della firma del brand (brand generici)'),
  position: z
    .enum(['left', 'right', 'auto'])
    .optional()
    .describe("lato: left | right | auto (default): opposto al soggetto se c'è subjectX, altrimenti in basso a sinistra"),
  subjectX: z
    .number()
    .min(0)
    .max(1)
    .optional()
    .describe('centro orizzontale del soggetto principale nel frame (0 = bordo sinistro, 1 = destro); usato da position auto'),
  align: z.enum(['left', 'right']).optional().describe('DEPRECATO, alias di position: vale solo con position auto e senza subjectX'),
  maxWidth: z.number().min(300).max(1700).optional().describe('larghezza max del nome in px @1080p (stretta → nome su 2 righe)'),
});
export type LowerThirdProps = z.infer<typeof lowerThirdSchema>;

export type LowerThirdSide = 'left' | 'right';

/**
 * Lato del lower third. Precedenza: position left/right esplicita → subjectX (position auto:
 * lato opposto al soggetto; soggetto a sinistra del centro → destra) → align (deprecato) → sinistra.
 */
export const resolveLowerThirdSide = ({
  position,
  subjectX,
  align,
}: Pick<LowerThirdProps, 'position' | 'subjectX' | 'align'>): LowerThirdSide => {
  if (position === 'left' || position === 'right') return position;
  if (typeof subjectX === 'number' && Number.isFinite(subjectX)) return subjectX < 0.5 ? 'right' : 'left';
  return align ?? 'left';
};

const Line: React.FC<{p: number; children: React.ReactNode; style?: React.CSSProperties}> = ({p, children, style}) => (
  // Riga mascherata: il testo sale dal basso dentro la propria maschera.
  <div style={{overflow: 'hidden', paddingBottom: '0.08em', marginBottom: '-0.08em', ...style}}>
    <div style={{transform: `translateY(${(1 - p) * 110}%)`, opacity: p > 0 ? 1 : 0}}>{children}</div>
  </div>
);

const EditorialLowerThird: React.FC<{props: LowerThirdProps; theme: Theme; u: number; ready: boolean}> = ({props, theme, u, ready}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: D} = useVideoConfig();
  const OUT = 12;
  // Nome su una riga a 62 px; se non entra nel box scende di corpo o va su due righe bilanciate.
  const name = useMemo(() => {
    if (!ready) return {fontSize: 62 * u, lines: [props.name]};
    return fitBalanced({
      text: props.name,
      fontFamily: theme.display,
      uppercase: true,
      letterSpacingEm: 0.01,
      maxWidth: (props.maxWidth ?? 880) * u,
      maxHeight: 2 * 1.04 * 62 * u,
      lineHeight: 1.04,
      maxLines: 2,
      maxFontSize: 62 * u,
      minFontSize: 40 * u,
    });
  }, [ready, props.name, props.maxWidth, theme.display, u]);

  const strip = inOut(frame, D, 1, 10, OUT);
  const card = Math.min(ramp(frame, 4, 16), 1 - ramp(frame, D - 1 - OUT, OUT, easeIn));
  const nameP = Math.min(ramp(frame, 9, 14), 1 - ramp(frame, D - 1 - OUT - 2, 8, easeIn));
  const roleP = Math.min(ramp(frame, 13, 14), 1 - ramp(frame, D - 1 - OUT - 4, 8, easeIn));
  const right = resolveLowerThirdSide(props) === 'right';
  const visible = frame > 0 && frame < D - 1;

  return (
    <AbsoluteFill style={{opacity: visible ? 1 : 0}}>
      <div
        style={{
          position: 'absolute',
          bottom: 118 * u,
          [right ? 'right' : 'left']: 115 * u,
          display: 'flex',
          flexDirection: right ? 'row-reverse' : 'row',
          alignItems: 'stretch',
          filter: `drop-shadow(0 ${10 * u}px ${28 * u}px ${alpha(theme.fg, 0.22 * card)})`,
        }}
      >
        <div
          style={{
            width: 12 * u,
            background: theme.accent,
            borderRadius: right ? `0 ${theme.radius * u}px ${theme.radius * u}px 0` : `${theme.radius * u}px 0 0 ${theme.radius * u}px`,
            transform: `scaleY(${strip})`,
            transformOrigin: 'bottom',
          }}
        />
        <div
          style={{
            background: theme.surface,
            borderRadius: right ? `${theme.radius * u}px 0 0 ${theme.radius * u}px` : `0 ${theme.radius * u}px ${theme.radius * u}px 0`,
            padding: `${26 * u}px ${44 * u}px ${28 * u}px ${32 * u}px`,
            clipPath: right ? `inset(0 0 0 ${(1 - card) * 100}%)` : `inset(0 ${(1 - card) * 100}% 0 0)`,
            textAlign: right ? 'right' : 'left',
          }}
        >
          {name.lines.map((line, i) => (
            <Line key={i} p={nameP}>
              <div
                style={{
                  fontFamily: theme.display,
                  fontSize: name.fontSize,
                  lineHeight: 1.04,
                  letterSpacing: '0.01em',
                  textTransform: 'uppercase',
                  color: theme.fg,
                  whiteSpace: 'nowrap',
                }}
              >
                {line}
              </div>
            </Line>
          ))}
          {props.role ? (
            <Line p={roleP} style={{marginTop: 12 * u}}>
              <div
                style={{
                  fontFamily: theme.body,
                  fontWeight: 700,
                  fontSize: 29 * u,
                  lineHeight: 1.2,
                  color: theme.fg,
                  whiteSpace: 'nowrap',
                }}
              >
                {props.role}
              </div>
            </Line>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const GenericLowerThird: React.FC<{props: LowerThirdProps; theme: Theme; u: number}> = ({props, theme, u}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: D} = useVideoConfig();
  const look = theme.look;
  const OUT = 10;
  const box = Math.min(ramp(frame, 0, 12), 1 - ramp(frame, D - 1 - OUT, OUT, easeIn));
  const typeStart = 10;
  const typeLen = props.name.length;
  const perChar = Math.max(0.6, Math.min(1.2, 22 / Math.max(1, typeLen)));
  // style.typing: il nome si "batte" carattere per carattere; altrimenti sale nella sua maschera
  const typed = look.typing ? Math.max(0, Math.min(typeLen, Math.floor((frame - typeStart) / perChar))) : typeLen;
  const typingDone = typed >= typeLen;
  const nameP = look.typing ? 1 : Math.min(ramp(frame, 8, 14), 1 - ramp(frame, D - 1 - OUT - 2, 8, easeIn));
  const tagP = Math.min(ramp(frame, 5, 10), 1 - ramp(frame, D - 1 - OUT - 4, 8, easeIn));
  const roleFrom = look.typing ? typeStart + typeLen * perChar - 4 : 14;
  const roleP = Math.min(ramp(frame, roleFrom, 12), 1 - ramp(frame, D - 1 - OUT - 4, 8, easeIn));
  const right = resolveLowerThirdSide(props) === 'right';
  const visible = frame > 0 && frame < D - 1;
  const hair = Math.max(1, Math.round(u));
  const terminal = look.motif === 'terminal';
  const showCursor = look.cursor && frame >= typeStart && frame < D - 1 - OUT;

  return (
    <AbsoluteFill style={{opacity: visible ? 1 : 0}}>
      <div
        style={{
          position: 'absolute',
          bottom: 118 * u,
          [right ? 'right' : 'left']: 115 * u,
          background: theme.bg,
          border: `${hair}px solid ${theme.line}`,
          borderRadius: theme.radius * u,
          padding: `${24 * u}px ${36 * u}px ${26 * u}px ${32 * u}px`,
          clipPath: right ? `inset(0 0 0 ${(1 - box) * 100}%)` : `inset(0 ${(1 - box) * 100}% 0 0)`,
          textAlign: right ? 'right' : 'left',
        }}
      >
        {props.tag ? (
          <div style={{opacity: tagP, marginBottom: 14 * u}}>
            <Signature theme={theme} size={26 * u} text={props.tag} weight={500} />
          </div>
        ) : null}
        <Line p={nameP}>
          <div style={{position: 'relative', fontFamily: theme.body, fontWeight: 600, fontSize: 58 * u, lineHeight: 1.08, letterSpacing: '-0.015em', whiteSpace: 'nowrap'}}>
            {/* testo pieno invisibile: fissa la larghezza del box mentre il nome si "batte" */}
            <span style={{color: 'transparent'}}>{props.name}</span>
            <span style={{position: 'absolute', left: right ? undefined : 0, right: right ? 0 : undefined, top: 0, color: theme.fg}}>
              {props.name.slice(0, typed)}
              {showCursor ? <Cursor theme={theme} solid={!typingDone} /> : null}
            </span>
          </div>
        </Line>
        {props.role ? (
          <div
            style={{
              marginTop: 12 * u,
              fontFamily: terminal ? theme.mono : theme.body,
              fontWeight: terminal ? 400 : 500,
              fontSize: 26 * u,
              color: theme.muted,
              opacity: roleP,
              whiteSpace: 'nowrap',
            }}
          >
            {look.comment}
            {props.role}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

export const LowerThird: React.FC<LowerThirdProps> = (props) => {
  const ready = useBrandFonts(props.style);
  const theme = makeTheme(props.brand, props.tokens, props.style);
  const u = useUnit();
  if (!ready) return null;
  return theme.family === 'editorial' ? (
    <EditorialLowerThird props={props} theme={theme} u={u} ready={ready} />
  ) : (
    <GenericLowerThird props={props} theme={theme} u={u} />
  );
};
