// IntroSting — sigla ≤3 s. Famiglia editorial: card d'intro animata (marchio che si disegna, nome del brand lettera per
// lettera, "con: ospite", pillola nelle tinte degli accenti).
// Brand generici: firma del brand (title → style.signature → nome) su fondo pieno, battuta a macchina con
// cursore se lo stile lo chiede, sottotitolo con il prefisso di commento dello stile.
import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';
import {makeTheme, mix, Theme} from '../lib/brand';
import {easeIn, ramp, useUnit} from '../lib/anim';
import {useBrandFonts} from '../lib/fonts';
import {brandFields, timingFields} from '../lib/schema';
import {BrandField, BrandMark, EditorialMark, Ring, Signature} from '../components/brand';

export const introStingSchema = z.object({
  ...brandFields,
  ...timingFields,
  title: z.string().optional().describe('wordmark (default: nome del brand)'),
  subtitle: z.string().optional().describe('es. con: Paolo Bianchi'),
  pill: z.string().optional().describe('pillola in basso (es. annuncio)'),
  exit: z.boolean(),
});
export type IntroStingProps = z.infer<typeof introStingSchema>;

const EditorialIntro: React.FC<{props: IntroStingProps; theme: Theme; u: number}> = ({props, theme, u}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: D} = useVideoConfig();
  const out = props.exit ? ramp(frame, D - 1 - 8, 8, easeIn) : 0;
  const title = (props.title ?? theme.name).toUpperCase();
  const chars = Array.from(title);
  const ring = ramp(frame, 0, 20);
  const mark = ramp(frame, 9, 14);
  const sub = ramp(frame, 24, 14);
  const pill = ramp(frame, 30, 16);
  const p = theme.pastel;
  return (
    <AbsoluteFill style={{opacity: 1 - out}}>
      <BrandField theme={theme} unit={u} variant="paper" />
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', transform: `translateY(${-30 * u}px)`}}>
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
          {theme.look.logo ? (
            <div style={{opacity: ring}}>
              <EditorialMark theme={theme} size={150 * u} />
            </div>
          ) : (
            <Ring size={150 * u} theme={theme} progress={ring} initial={mark} inner strokeWidth={3} />
          )}
          <div style={{marginTop: 34 * u, display: 'flex', fontFamily: theme.display, fontSize: 236 * u, lineHeight: 0.92, color: theme.fg, letterSpacing: '-0.005em'}}>
            {chars.map((ch, i) => {
              const cp = ramp(frame, 8 + i * 1.3, 12);
              return (
                <span key={i} style={{display: 'inline-block', overflow: 'hidden', paddingBottom: '0.04em'}}>
                  <span style={{display: 'inline-block', transform: `translateY(${(1 - cp) * 100}%)`}}>{ch === ' ' ? ' ' : ch}</span>
                </span>
              );
            })}
          </div>
          {props.subtitle ? (
            <div style={{overflow: 'hidden', marginTop: 18 * u}}>
              <div
                style={{
                  transform: `translateY(${(1 - sub) * 100}%)`,
                  fontFamily: theme.body,
                  fontWeight: 800,
                  fontSize: 44 * u,
                  letterSpacing: '0.03em',
                  textTransform: 'uppercase',
                  color: theme.fg,
                }}
              >
                {props.subtitle}
              </div>
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
      {props.pill ? (
        <div
          style={{
            position: 'absolute',
            left: '50%',
            bottom: 96 * u,
            transform: `translateX(-50%) scaleX(${0.6 + 0.4 * pill})`,
            opacity: pill,
            padding: `${20 * u}px ${42 * u}px`,
            borderRadius: 999,
            background: `linear-gradient(90deg, ${mix(p.t1, theme.bg, 0.2)}, ${mix(p.t2, theme.bg, 0.25)} 40%, ${mix(p.t4, theme.bg, 0.3)} 75%, ${mix(p.t3, theme.bg, 0.6)})`,
            fontFamily: theme.body,
            fontWeight: 800,
            fontSize: 34 * u,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: theme.fg,
            whiteSpace: 'nowrap',
          }}
        >
          {props.pill}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const GenericIntro: React.FC<{props: IntroStingProps; theme: Theme; u: number}> = ({props, theme, u}) => {
  const frame = useCurrentFrame();
  const {durationInFrames: D} = useVideoConfig();
  const look = theme.look;
  const terminal = look.motif === 'terminal';
  const out = props.exit ? ramp(frame, D - 1 - 8, 8, easeIn) : 0;
  const sig = props.title ?? look.signature ?? theme.name;
  // style.typing: firma battuta a macchina; altrimenti sale in un colpo
  const typed = look.typing ? Math.max(0, Math.min(sig.length, Math.floor((frame - 6) / 2.2) + 1)) : sig.length;
  const rise = look.typing ? 1 : ramp(frame, 2, 16);
  const subFrom = look.typing ? 6 + sig.length * 2.2 + 4 : 16;
  const sub = ramp(frame, subFrom, 12);
  return (
    <AbsoluteFill style={{opacity: 1 - out}}>
      <BrandField theme={theme} unit={u} />
      {look.logo && !look.signature && !props.title ? (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: rise}}>
          <BrandMark theme={theme} size={220 * u} />
        </AbsoluteFill>
      ) : (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
          <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-start'}}>
            <div style={{position: 'relative', opacity: rise, transform: `translateY(${(1 - rise) * 30 * u}px)`}}>
              {/* larghezza fissa della firma completa, poi la parte battuta sopra */}
              <Signature theme={theme} size={250 * u} text={sig} weight={600} style={{color: 'transparent', letterSpacing: '-0.03em'}} />
              <div style={{position: 'absolute', left: 0, top: 0}}>
                <Signature theme={theme} size={250 * u} text={sig.slice(0, typed)} weight={600} cursor={look.cursor} style={{letterSpacing: '-0.03em'}} />
              </div>
            </div>
            {props.subtitle ? (
              <div
                style={{
                  marginTop: 34 * u,
                  fontFamily: terminal ? theme.mono : theme.body,
                  fontWeight: terminal ? 400 : 600,
                  fontSize: 40 * u,
                  color: theme.muted,
                  opacity: sub,
                  transform: `translateY(${(1 - sub) * 12 * u}px)`,
                }}
              >
                {look.comment}
                {props.subtitle}
              </div>
            ) : null}
          </div>
        </AbsoluteFill>
      )}
      {props.pill ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 96 * u,
            textAlign: 'center',
            fontFamily: terminal ? theme.mono : theme.body,
            fontWeight: terminal ? 400 : 600,
            fontSize: 28 * u,
            color: theme.muted,
            opacity: ramp(frame, 30, 12),
          }}
        >
          {props.pill}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const IntroSting: React.FC<IntroStingProps> = (props) => {
  const ready = useBrandFonts(props.style);
  const theme = makeTheme(props.brand, props.tokens, props.style);
  const u = useUnit();
  if (!ready) return null;
  return theme.family === 'editorial' ? <EditorialIntro props={props} theme={theme} u={u} /> : <GenericIntro props={props} theme={theme} u={u} />;
};

