// ThumbnailStill — 1280×720 CSS, renderizzata con --scale 3 → 3840×2160.
// Regole (knowledge/07-thumbnails.md §7.3): margini 64/56, angolo basso-destra 230×110 e alto-destra 120×80 liberi,
// testo ≤4 parole nel font display del brand MAIUSCOLO (cap ≥86 px), UNA parola nel box accento,
// ospite = scontorno reale (nessun ritocco), solo ombra neutra morbida.
import React, {useMemo} from 'react';
import {AbsoluteFill, Img} from 'remotion';
import {z} from 'zod';
import {alpha, makeTheme, Theme} from '../lib/brand';
import {resolveSrc} from '../lib/anim';
import {useBrandFonts} from '../lib/fonts';
import {fitBalanced} from '../lib/fit';
import {accentGap, markStyle} from '../lib/type';
import {brandFields} from '../lib/schema';
import {BrandMark, EditorialMark, GridField, PaperField, PastelField} from '../components/brand';

const box = z.tuple([z.number(), z.number(), z.number(), z.number()]);

export const thumbnailStillSchema = z.object({
  ...brandFields,
  text: z.string().min(1).describe('≤4 parole; "\\n" forza l\'a capo'),
  highlight: z.string().optional().describe('UNA parola nel box accento'),
  background: z.enum(['pastel', 'paper', 'ink', 'dark', 'image']),
  bgImageSrc: z.string().optional().describe('frame reale per background=image (sfocato e scurito)'),
  cutoutSrc: z.string().optional().describe('PNG con alpha (thumbvision cutout)'),
  cutoutSize: z.tuple([z.number(), z.number()]).optional().describe('px naturali del PNG (yt-remotion)'),
  cutoutBBox: box.optional().describe('bbox alpha normalizzato x,y,w,h (yt-remotion)'),
  faceBox: box.optional().describe('volto normalizzato x,y,w,h nel PNG (thumbvision faces)'),
  side: z.enum(['right', 'left']).describe('lato dell\'ospite'),
  faceHeight: z.number().min(0.15).max(0.7).describe('altezza volto / altezza frame'),
  choke: z.number().min(0).max(6).optional().describe('erosione bordo scontorno in px (default 1.2)'),
  badge: z.string().optional().describe('es. EP.08 (editorial: accanto al marchio; brand generici: solo se lo stile non ha firma né logo)'),
  kicker: z.string().optional().describe('riga piccola, es. con Paolo Bianchi'),
  showSafeZones: z.boolean(),
});
export type ThumbnailStillProps = z.infer<typeof thumbnailStillSchema>;

const W = 1280;
const H = 720;
const MX = 64;
const MY = 56;
const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

const Background: React.FC<{props: ThumbnailStillProps; theme: Theme}> = ({props, theme}) => {
  const bg = props.background;
  if (bg === 'image' && props.bgImageSrc) {
    return (
      <AbsoluteFill style={{backgroundColor: '#111'}}>
        <Img src={resolveSrc(props.bgImageSrc)!} style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(14px) brightness(0.55) saturate(1.1)', transform: 'scale(1.08)'}} />
      </AbsoluteFill>
    );
  }
  if (theme.family !== 'editorial' || bg === 'dark') {
    const sx = props.side === 'left' ? 30 : 72;
    const glow = theme.family === 'editorial' ? '#ffffff' : theme.fg;
    return (
      <AbsoluteFill>
        <GridField theme={theme} unit={0.67} grid={theme.family === 'editorial' || theme.look.grid} />
        <AbsoluteFill style={{background: `radial-gradient(48% 70% at ${sx}% 45%, ${alpha(glow, 0.09)} 0%, ${alpha(glow, 0)} 100%)`}} />
      </AbsoluteFill>
    );
  }
  if (bg === 'ink') return <AbsoluteFill style={{backgroundColor: theme.fg}} />;
  if (bg === 'paper') return <PaperField theme={theme} unit={0.67} />;
  return <PastelField theme={theme} />;
};

const Cutout: React.FC<{props: ThumbnailStillProps}> = ({props}) => {
  const src = resolveSrc(props.cutoutSrc);
  if (!src) return null;
  const [w0, h0] = props.cutoutSize ?? [3840, 2160];
  const right = props.side !== 'left';
  let s: number;
  let cx: number; // centro volto (o soggetto) nel PNG, px
  let cy: number;
  const tx = right ? W * 0.745 : W * 0.255; // dove va il volto sulla tela
  const ty = H * 0.41;
  if (props.faceBox) {
    const [fx, fy, fw, fh] = props.faceBox;
    s = (props.faceHeight * H) / (fh * h0);
    cx = (fx + fw / 2) * w0;
    cy = (fy + fh / 2) * h0;
  } else {
    // Senza volto: il soggetto riempie 1.35× l'altezza, testa a filo del margine alto.
    const [bx, by, bw, bh] = props.cutoutBBox ?? [0, 0, 1, 1];
    s = (1.35 * H) / (bh * h0);
    cx = (bx + bw / 2) * w0;
    cy = by * h0 + (ty - 34) / s;
  }
  const left = tx - cx * s;
  const top = ty - cy * s;
  const choke = props.choke ?? 1.2;
  return (
    <>
      {/* "choke" dell'alpha: erode 1–2 px di bordo per togliere l'alone del fondo originale */}
      <svg width="0" height="0" style={{position: 'absolute'}}>
        <filter id="yt-choke" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feMorphology operator="erode" radius={choke} in="SourceAlpha" result="eroded" />
          <feGaussianBlur in="eroded" stdDeviation={choke * 0.5} result="soft" />
          <feComposite in="SourceGraphic" in2="soft" operator="in" />
        </filter>
      </svg>
      <div style={{position: 'absolute', left, top, width: w0 * s, height: h0 * s, filter: 'drop-shadow(0 10px 26px rgba(0,0,0,0.28))'}}>
        <Img src={src} style={{width: '100%', height: '100%', filter: choke > 0 ? 'url(#yt-choke)' : undefined}} />
      </div>
    </>
  );
};

export const ThumbnailStill: React.FC<ThumbnailStillProps> = (props) => {
  const ready = useBrandFonts(props.style);
  const theme = makeTheme(props.brand, props.tokens, props.style);
  const ed = theme.family === 'editorial';
  const look = theme.look;
  const terminal = look.motif === 'terminal';
  const right = props.side !== 'left';
  const dark = !ed || props.background === 'ink' || props.background === 'dark' || props.background === 'image';
  const textColor = ed ? (dark ? theme.bg : theme.fg) : theme.fg;
  // Box parola chiave: colore di evidenziazione del brand (highlight, default l'accento); sulla tela morbida l'accento.
  // Brand generici: style.highlight — 'invert' = testo "selezionato" in negativo (l'accento resta alla firma),
  // 'accent' = box nell'accento del brand.
  const hiBg = ed ? (props.background === 'pastel' ? theme.accent : theme.highlight) : theme.highlight;
  const hiFg = ed ? theme.fg : theme.onHighlight;

  // Area testo: metà opposta all'ospite, sotto il badge, fuori dalle zone vietate.
  const area = {
    left: right ? MX : W * 0.47,
    right: right ? W * 0.55 : W - MX,
    top: MY + 64,
    bottom: right ? H - MY : H - 110 - 12,
  };
  const fit = useMemo(
    () =>
      ready
        ? fitBalanced({
            text: props.text,
            fontFamily: ed ? theme.display : theme.body,
            fontWeight: ed ? 400 : 800,
            uppercase: ed,
            letterSpacingEm: ed ? -0.01 : -0.035,
            maxWidth: area.right - area.left,
            maxHeight: area.bottom - area.top - (props.kicker ? 64 : 0),
            lineHeight: ed ? 0.9 : 0.98,
            maxLines: 3,
            maxFontSize: ed ? 168 : 150,
            extraEmPerLine: props.highlight ? 0.24 : 0,
          })
        : {fontSize: 120, lines: [props.text]},
    [ready, props.text, props.highlight, props.kicker, ed, theme.display, theme.body, area.right, area.left, area.bottom, area.top],
  );
  if (!ready) return null;
  const target = props.highlight ? norm(props.highlight) : null;
  let used = false;

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <Background props={props} theme={theme} />
      <Cutout props={props} />
      {/* badge in alto a sinistra */}
      <div style={{position: 'absolute', left: MX, top: MY - 8, display: 'flex', alignItems: 'center', gap: 14}}>
        {ed ? (
          <>
            <EditorialMark theme={theme} size={50} />
            {props.badge ? (
              <div style={{fontFamily: theme.body, fontWeight: 800, fontSize: 30, letterSpacing: '0.02em', color: textColor}}>{props.badge}</div>
            ) : null}
          </>
        ) : look.signature || look.logo ? (
          <BrandMark theme={theme} size={34} weight={600} cursor={false} />
        ) : props.badge ? (
          <div style={{fontFamily: theme.body, fontWeight: 800, fontSize: 30, letterSpacing: '0.02em', color: textColor}}>{props.badge}</div>
        ) : null}
      </div>
      {/* testo */}
      <div
        style={{
          position: 'absolute',
          left: area.left,
          width: area.right - area.left,
          top: area.top,
          bottom: area.bottom === H - MY ? MY : H - area.bottom,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: right ? 'flex-start' : 'flex-end',
          textAlign: right ? 'left' : 'right',
        }}
      >
        {fit.lines.map((line, li) => (
          <div
            key={li}
            style={{
              marginTop: accentGap(line, li, ed) * fit.fontSize,
              fontFamily: ed ? theme.display : theme.body,
              fontWeight: ed ? 400 : 800,
              fontSize: fit.fontSize,
              lineHeight: ed ? 0.9 : 0.98,
              letterSpacing: ed ? '-0.01em' : '-0.035em',
              textTransform: ed ? 'uppercase' : 'none',
              color: textColor,
              whiteSpace: 'nowrap',
              marginBottom: ed ? 0.06 * fit.fontSize : 0.04 * fit.fontSize,
            }}
          >
            {line.split(' ').map((word, wi) => {
              const hi = !used && target !== null && norm(word) === target;
              if (hi) used = true;
              return (
                <React.Fragment key={wi}>
                  {wi > 0 ? ' ' : ''}
                  <span
                    style={
                      hi
                        ? {
                            ...markStyle(ed ? theme.display : theme.body, ed, 0.1, 0.1),
                            background: hiBg,
                            color: hiFg,
                            margin: '0 -0.02em',
                            borderRadius: ed ? 0.07 * fit.fontSize : 2,
                          }
                        : undefined
                    }
                  >
                    {word}
                  </span>
                </React.Fragment>
              );
            })}
          </div>
        ))}
        {props.kicker ? (
          <div
            style={{
              marginTop: 14,
              fontFamily: ed || !terminal ? theme.body : theme.mono,
              fontWeight: ed ? 800 : terminal ? 500 : 700,
              fontSize: 34,
              letterSpacing: ed ? '0.02em' : 0,
              textTransform: ed ? 'uppercase' : 'none',
              color: ed ? textColor : theme.muted,
              whiteSpace: 'nowrap',
            }}
          >
            {ed ? props.kicker : `${look.comment}${props.kicker}`}
          </div>
        ) : null}
      </div>
      {props.showSafeZones ? (
        <AbsoluteFill>
          <div style={{position: 'absolute', left: MX, right: MX, top: MY, bottom: MY, border: '2px dashed rgba(0,160,255,0.9)'}} />
          <div style={{position: 'absolute', right: 0, bottom: 0, width: 230, height: 110, background: 'rgba(255,0,80,0.35)'}} />
          <div style={{position: 'absolute', right: 0, top: 0, width: 120, height: 80, background: 'rgba(255,140,0,0.35)'}} />
          <div style={{position: 'absolute', right: 8, bottom: 8, width: 48, height: 20, background: 'rgba(0,0,0,0.8)', borderRadius: 4}} />
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

