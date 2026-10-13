// ColdOpenTitle — sting ≤3 s con la frase-gancio dell'episodio, grande.
// Famiglia editorial (token paper + ink): anello d'accento che si disegna dietro al testo (font display del brand).
// Brand generici: marchio in alto,
// frase su fondo pieno (battuta parola per parola con cursore se lo stile lo chiede).
// background=transparent → overlay sul video.
import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';
import {alpha, makeTheme, Theme} from '../lib/brand';
import {easeIn, easeOut, ramp, useUnit} from '../lib/anim';
import {useBrandFonts} from '../lib/fonts';
import {fitBalanced} from '../lib/fit';
import {accentGap, markStyle} from '../lib/type';
import {brandFields, timingFields} from '../lib/schema';
import {BrandField, BrandMark, Cursor, Ring} from '../components/brand';

export const coldOpenTitleSchema = z.object({
  ...brandFields,
  ...timingFields,
  hook: z.string().min(1).describe('frase gancio (≤10 parole, verbatim o fedele al transcript)'),
  highlight: z.string().optional().describe('parola da evidenziare (editorial: box nell\'accento; generici: style.highlight)'),
  kicker: z.string().optional().describe('riga piccola (es. EP. 08 · con Nome Cognome)'),
  background: z.enum(['paper', 'pastel', 'ink', 'transparent']),
  exit: z.boolean().describe('animazione di uscita (default: taglio secco)'),
});
export type ColdOpenTitleProps = z.infer<typeof coldOpenTitleSchema>;

const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

const EditorialCold: React.FC<{props: ColdOpenTitleProps; theme: Theme; u: number}> = ({props, theme, u}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: D} = useVideoConfig();
  const out = props.exit ? ramp(frame, D - 1 - 8, 8, easeIn) : 0;
  const transparent = props.background === 'transparent';
  const ink = props.background === 'ink';
  const fg = ink ? theme.bg : theme.fg;
  const fit = useMemo(
    () =>
      fitBalanced({
        text: props.hook,
        fontFamily: theme.display,
        uppercase: true,
        letterSpacingEm: -0.01,
        maxWidth: 1500 * u,
        maxHeight: 560 * u,
        lineHeight: 0.95,
        maxLines: 3,
        maxFontSize: 176 * u,
        extraEmPerLine: props.highlight ? 0.3 : 0,
      }),
    [props.hook, props.highlight, theme.display, u],
  );
  const ringP = ramp(frame, 0, 22, easeOut);
  const ringRot = -90 + ramp(frame, 0, D, (t) => t) * 40;
  const target = props.highlight ? norm(props.highlight) : null;
  let wi = 0;
  return (
    <AbsoluteFill style={{opacity: 1 - out}}>
      {transparent ? null : <BrandField theme={theme} unit={u} variant={props.background as 'paper' | 'pastel' | 'ink'} />}
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <div style={{transform: `rotate(${ringRot}deg) scale(${0.92 + 0.08 * ringP})`}}>
          <Ring size={1000 * u} theme={theme} progress={ringP} strokeWidth={1.3} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', transform: `scale(${1 + out * 0.04})`}}>
        <div style={{textAlign: 'center'}}>
          {fit.lines.map((line, li) => (
            <div
              key={li}
              style={{
                whiteSpace: 'nowrap',
                lineHeight: 0.95,
                marginTop: accentGap(line, li, true) * fit.fontSize,
                fontSize: fit.fontSize,
                fontFamily: theme.display,
                textTransform: 'uppercase',
                letterSpacing: '-0.01em',
              }}
            >
              {line.split(' ').map((word, i) => {
                const idx = wi++;
                const p = ramp(frame, 5 + idx * 2.2, 12);
                const hi = target && norm(word) === target;
                const boxed = hi || transparent;
                return (
                  <span
                    key={i}
                    style={{
                      display: 'inline-block',
                      ...(boxed ? markStyle(theme.display, true, 0.1, 0.12) : {}),
                      marginRight: '0.2em',
                      marginLeft: i === 0 ? '0.2em' : 0,
                      transform: `translateY(${(1 - p) * 0.35}em) scale(${0.94 + 0.06 * p})`,
                      opacity: p,
                      color: hi ? theme.onAccent : fg,
                      background: hi ? theme.accent : transparent ? theme.bg : 'transparent',
                      borderRadius: boxed ? 0.08 * fit.fontSize : 0,
                    }}
                  >
                    {word}
                  </span>
                );
              })}
            </div>
          ))}
          {props.kicker ? (
            <div
              style={{
                marginTop: 46 * u,
                fontFamily: theme.body,
                fontWeight: 800,
                fontSize: 30 * u,
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: transparent ? theme.fg : alpha(fg, 0.85),
                opacity: ramp(frame, 16, 12),
                display: 'inline-block',
                background: transparent ? theme.bg : 'transparent',
                padding: transparent ? `${8 * u}px ${18 * u}px` : 0,
                borderRadius: transparent ? 8 * u : 0,
              }}
            >
              {props.kicker}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const GenericCold: React.FC<{props: ColdOpenTitleProps; theme: Theme; u: number}> = ({props, theme, u}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: D} = useVideoConfig();
  const look = theme.look;
  const terminal = look.motif === 'terminal';
  const out = props.exit ? ramp(frame, D - 1 - 8, 8, easeIn) : 0;
  const transparent = props.background === 'transparent';
  const fit = useMemo(
    () =>
      fitBalanced({
        text: props.hook,
        fontFamily: theme.body,
        fontWeight: 700,
        letterSpacingEm: -0.025,
        maxWidth: 1560 * u,
        maxHeight: 520 * u,
        lineHeight: 1.04,
        maxLines: 3,
        maxFontSize: 150 * u,
        extraEmPerLine: look.cursor ? 0.6 : props.highlight ? 0.3 : 0,
      }),
    [props.hook, props.highlight, look.cursor, theme.body, u],
  );
  const words = fit.lines.flatMap((l, li) => l.split(' ').map((w, wi) => ({w, li, first: wi === 0})));
  // style.typing: parole battute una alla volta (cursore sull'ultima); altrimenti salgono in sequenza
  const per = Math.max(1.5, Math.min(3, 26 / Math.max(1, words.length)));
  const shown = look.typing ? Math.floor(Math.max(0, frame - 6) / per) + (frame >= 6 ? 1 : 0) : words.length;
  const done = shown >= words.length;
  const target = props.highlight ? norm(props.highlight) : null;
  let k = 0;
  let used = false;
  return (
    <AbsoluteFill style={{opacity: 1 - out}}>
      {transparent ? null : <BrandField theme={theme} unit={u} />}
      {look.signature || look.logo ? (
        <div style={{position: 'absolute', left: 160 * u, top: 120 * u, opacity: ramp(frame, 0, 8)}}>
          <BrandMark theme={theme} size={34 * u} weight={500} cursor={false} />
        </div>
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: 160 * u,
          right: 160 * u,
          top: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        <div style={{display: 'inline-block', alignSelf: 'flex-start', background: transparent ? theme.bg : 'transparent', padding: transparent ? `${20 * u}px ${32 * u}px` : 0}}>
          {fit.lines.map((line, li) => (
            <div key={li} style={{fontFamily: theme.body, fontWeight: 700, fontSize: fit.fontSize, lineHeight: 1.04, letterSpacing: '-0.025em', color: theme.fg, whiteSpace: 'nowrap'}}>
              {line.split(' ').map((w, i) => {
                const idx = k++;
                const visible = idx < shown;
                const last = idx === Math.min(shown, words.length) - 1;
                const p = look.typing ? (visible ? 1 : 0) : ramp(frame, 5 + idx * 2.2, 12);
                const hi = !used && target !== null && norm(w) === target;
                if (hi) used = true;
                return (
                  <React.Fragment key={i}>
                    {i > 0 ? ' ' : ''}
                    <span
                      style={{
                        display: 'inline-block',
                        opacity: p,
                        transform: look.typing ? undefined : `translateY(${(1 - p) * 0.3}em)`,
                        ...(hi ? {...markStyle(theme.body, false, 0.08, 0.1), background: theme.highlight, color: theme.onHighlight, borderRadius: 2 * u} : {}),
                      }}
                    >
                      {w}
                    </span>
                    {last && look.cursor ? <Cursor theme={theme} solid={!done} /> : null}
                  </React.Fragment>
                );
              })}
            </div>
          ))}
        </div>
        {props.kicker ? (
          <div
            style={{
              marginTop: 40 * u,
              fontFamily: terminal ? theme.mono : theme.body,
              fontWeight: terminal ? 400 : 700,
              fontSize: 30 * u,
              color: theme.muted,
              opacity: ramp(frame, 18, 10),
            }}
          >
            {look.comment}
            {props.kicker}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

export const ColdOpenTitle: React.FC<ColdOpenTitleProps> = (props) => {
  const ready = useBrandFonts(props.style);
  const theme = makeTheme(props.brand, props.tokens, props.style);
  const u = useUnit();
  if (!ready) return null;
  return theme.family === 'editorial' ? <EditorialCold props={props} theme={theme} u={u} /> : <GenericCold props={props} theme={theme} u={u} />;
};
