// ChapterCard — numero capitolo + titolo "curiosity gap", 3 s.
// mode=full: card a tutto schermo (fondo brand). mode=overlay: card compatta, fondo trasparente.
import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';
import {alpha, makeTheme, Theme} from '../lib/brand';
import {easeIn, ramp, useUnit} from '../lib/anim';
import {useBrandFonts} from '../lib/fonts';
import {fitBalanced} from '../lib/fit';
import {accentGap} from '../lib/type';
import {brandFields, timingFields} from '../lib/schema';
import {BrandField, Signature} from '../components/brand';

export const chapterCardSchema = z.object({
  ...brandFields,
  ...timingFields,
  number: z.number().int().min(0).max(99),
  title: z.string().min(1),
  label: z.string().describe('etichetta sopra il numero (es. Capitolo)'),
  mode: z.enum(['full', 'overlay']),
  background: z.enum(['paper', 'pastel', 'ink']).optional().describe('solo famiglia editorial, mode=full'),
});
export type ChapterCardProps = z.infer<typeof chapterCardSchema>;

const pad2 = (n: number) => String(n).padStart(2, '0');

/** Progressi in/out comuni: tutto vuoto al primo e all'ultimo frame in overlay. */
const usePhase = (outFrames: number) => {
  const frame = useCurrentFrame();
  const {durationInFrames: D} = useVideoConfig();
  const out = ramp(frame, D - 1 - outFrames, outFrames, easeIn);
  return {frame, D, out, at: (from: number, dur = 14) => Math.min(ramp(frame, from, dur), 1 - out)};
};

const Rise: React.FC<{p: number; children: React.ReactNode; style?: React.CSSProperties}> = ({p, children, style}) => (
  <div style={{overflow: 'hidden', paddingBottom: '0.06em', ...style}}>
    <div style={{transform: `translateY(${(1 - p) * 105}%)`}}>{children}</div>
  </div>
);

const EditorialFull: React.FC<{props: ChapterCardProps; theme: Theme; u: number}> = ({props, theme, u}) => {
  const {at} = usePhase(9);
  const fit = useMemo(
    () =>
      fitBalanced({
        text: props.title,
        fontFamily: theme.display,
        uppercase: true,
        letterSpacingEm: -0.005,
        maxWidth: 1080 * u,
        maxHeight: 520 * u,
        lineHeight: 0.98,
        maxLines: 4,
        maxFontSize: 124 * u,
      }),
    [props.title, theme.display, u],
  );
  const ink = props.background === 'ink';
  const fg = ink ? theme.bg : theme.fg;
  return (
    <AbsoluteFill>
      <BrandField theme={theme} unit={u} variant={props.background ?? 'paper'} />
      <AbsoluteFill>
        <div style={{position: 'absolute', left: 160 * u, right: 160 * u, top: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 64 * u}}>
          <div style={{flex: '0 0 auto'}}>
            <Rise p={at(2, 14)}>
              <div style={{fontFamily: theme.body, fontWeight: 800, fontSize: 30 * u, letterSpacing: '0.22em', textTransform: 'uppercase', color: fg, marginBottom: 6 * u}}>
                {props.label}
              </div>
            </Rise>
            <Rise p={at(0, 16)}>
              <div style={{fontFamily: theme.display, fontSize: 300 * u, lineHeight: 0.9, color: theme.accent, letterSpacing: '-0.02em'}}>{pad2(props.number)}</div>
            </Rise>
          </div>
          <div
            style={{
              alignSelf: 'center',
              width: 4 * u,
              height: 420 * u,
              borderRadius: 2 * u,
              background: alpha(fg, 0.85),
              transform: `scaleY(${at(4, 16)})`,
              transformOrigin: 'top',
            }}
          />
          <div style={{flex: '0 1 auto'}}>
            {fit.lines.map((line, i) => (
              <Rise key={i} p={at(6 + i * 3, 15)} style={{marginTop: accentGap(line, i, true) * fit.fontSize}}>
                <div style={{fontFamily: theme.display, fontSize: fit.fontSize, lineHeight: 0.98, textTransform: 'uppercase', color: fg, whiteSpace: 'nowrap', letterSpacing: '-0.005em'}}>
                  {line}
                </div>
              </Rise>
            ))}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const EditorialOverlay: React.FC<{props: ChapterCardProps; theme: Theme; u: number}> = ({props, theme, u}) => {
  const {frame, D, at} = usePhase(10);
  const card = at(2, 16);
  const fit = useMemo(
    () =>
      fitBalanced({
        text: props.title,
        fontFamily: theme.display,
        uppercase: true,
        maxWidth: 940 * u,
        maxHeight: 140 * u,
        lineHeight: 1.0,
        maxLines: 2,
        maxFontSize: 60 * u,
      }),
    [props.title, theme.display, u],
  );
  return (
    <AbsoluteFill style={{opacity: frame > 0 && frame < D - 1 ? 1 : 0}}>
      <div
        style={{
          position: 'absolute',
          left: 115 * u,
          bottom: 118 * u,
          display: 'flex',
          alignItems: 'stretch',
          clipPath: `inset(0 ${(1 - card) * 100}% 0 0 round ${theme.radius * u}px)`,
          filter: `drop-shadow(0 ${10 * u}px ${28 * u}px ${alpha(theme.fg, 0.22 * card)})`,
        }}
      >
        <div
          style={{
            background: theme.accent,
            color: theme.onAccent,
            fontFamily: theme.display,
            fontSize: 84 * u,
            lineHeight: 1,
            padding: `0 ${30 * u}px`,
            display: 'flex',
            alignItems: 'center',
            borderRadius: `${theme.radius * u}px 0 0 ${theme.radius * u}px`,
          }}
        >
          {pad2(props.number)}
        </div>
        <div style={{background: theme.surface, padding: `${24 * u}px ${44 * u}px ${26 * u}px ${34 * u}px`, borderRadius: `0 ${theme.radius * u}px ${theme.radius * u}px 0`}}>
          <Rise p={at(8, 12)}>
            <div style={{fontFamily: theme.body, fontWeight: 800, fontSize: 24 * u, letterSpacing: '0.2em', textTransform: 'uppercase', color: theme.muted, marginBottom: 8 * u}}>
              {props.label}
            </div>
          </Rise>
          {fit.lines.map((line, i) => (
            <Rise key={i} p={at(10 + i * 3, 14)} style={{marginTop: accentGap(line, i, true) * fit.fontSize}}>
              <div style={{fontFamily: theme.display, fontSize: fit.fontSize, lineHeight: 1.02, textTransform: 'uppercase', color: theme.fg, whiteSpace: 'nowrap'}}>{line}</div>
            </Rise>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const GenericCard: React.FC<{props: ChapterCardProps; theme: Theme; u: number; overlay: boolean}> = ({props, theme, u, overlay}) => {
  const {frame, D, at} = usePhase(overlay ? 10 : 8);
  const look = theme.look;
  const terminal = look.motif === 'terminal';
  const hair = Math.max(1, Math.round(u));
  const fit = useMemo(
    () =>
      fitBalanced({
        text: props.title,
        fontFamily: theme.body,
        fontWeight: 600,
        letterSpacingEm: -0.02,
        maxWidth: (overlay ? 980 : 1500) * u,
        maxHeight: (overlay ? 140 : 360) * u,
        lineHeight: 1.08,
        maxLines: overlay ? 2 : 3,
        maxFontSize: (overlay ? 54 : 104) * u,
      }),
    [props.title, theme.body, u, overlay],
  );
  // numero: con un prefisso (style.numberPrefix) il prefisso porta l'accento, altrimenti il numero intero
  const num = `${look.numberPrefix}${pad2(props.number)}`;
  const label = look.lowercaseLabels ? props.label.toLowerCase() : props.label;
  const content = (
    <>
      <div
        style={{
          opacity: at(0, 10),
          marginBottom: (overlay ? 10 : 18) * u,
          fontFamily: terminal ? theme.mono : theme.body,
          fontWeight: terminal ? 400 : 700,
          fontSize: (overlay ? 24 : 30) * u,
          letterSpacing: terminal ? 0 : '0.18em',
          textTransform: terminal || look.lowercaseLabels ? 'none' : 'uppercase',
          color: theme.muted,
        }}
      >
        {look.comment}
        {label}
      </div>
      <div style={{opacity: at(2, 10)}}>
        <Signature
          theme={theme}
          size={(overlay ? 64 : 190) * u}
          text={num}
          accentPrefix={look.numberPrefix.length > 0}
          color={look.numberPrefix ? theme.fg : theme.accent}
          weight={600}
          style={{letterSpacing: '-0.02em'}}
        />
      </div>
      <div
        style={{
          height: hair,
          background: theme.line,
          margin: `${(overlay ? 18 : 40) * u}px 0 ${(overlay ? 18 : 40) * u}px`,
          transform: `scaleX(${at(4, 18)})`,
          transformOrigin: 'left',
        }}
      />
      {fit.lines.map((line, i) => (
        <Rise key={i} p={at(8 + i * 3, 14)}>
          <div style={{fontFamily: theme.body, fontWeight: 600, fontSize: fit.fontSize, lineHeight: 1.08, letterSpacing: '-0.02em', color: theme.fg, whiteSpace: 'nowrap'}}>
            {line}
          </div>
        </Rise>
      ))}
    </>
  );
  if (overlay) {
    const box = at(0, 12);
    return (
      <AbsoluteFill style={{opacity: frame > 0 && frame < D - 1 ? 1 : 0}}>
        <div
          style={{
            position: 'absolute',
            left: 115 * u,
            bottom: 118 * u,
            background: theme.bg,
            border: `${hair}px solid ${theme.line}`,
            borderRadius: theme.radius * u,
            padding: `${24 * u}px ${40 * u}px ${28 * u}px ${32 * u}px`,
            clipPath: `inset(0 ${(1 - box) * 100}% 0 0)`,
          }}
        >
          {content}
        </div>
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill>
      <BrandField theme={theme} unit={u} />
      <div style={{position: 'absolute', left: 160 * u, right: 160 * u, top: 0, bottom: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
        {content}
      </div>
    </AbsoluteFill>
  );
};

export const ChapterCard: React.FC<ChapterCardProps> = (props) => {
  const ready = useBrandFonts(props.style);
  const theme = makeTheme(props.brand, props.tokens, props.style);
  const u = useUnit();
  if (!ready) return null;
  const overlay = props.mode === 'overlay';
  if (theme.family !== 'editorial') return <GenericCard props={props} theme={theme} u={u} overlay={overlay} />;
  return overlay ? <EditorialOverlay props={props} theme={theme} u={u} /> : <EditorialFull props={props} theme={theme} u={u} />;
};
