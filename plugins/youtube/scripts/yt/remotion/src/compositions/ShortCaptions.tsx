// ShortCaptions — Short 1080×1920: video (OffthreadVideo) + sottotitoli stile TikTok a pagine
// (createTikTokStyleCaptions), parola attiva nell'accento del brand, zona sicura, gancio nei
// primi secondi e barra di avanzamento opzionali. Senza videoSrc rende solo l'overlay (alpha).
import React, {useMemo} from 'react';
import {AbsoluteFill, OffthreadVideo, useCurrentFrame, useVideoConfig} from 'remotion';
import {createTikTokStyleCaptions, Caption, TikTokPage} from '@remotion/captions';
import {z} from 'zod';
import {alpha, makeTheme, Theme} from '../lib/brand';
import {easeIn, ramp, resolveSrc} from '../lib/anim';
import {useBrandFonts} from '../lib/fonts';
import {fitBalanced} from '../lib/fit';
import {accentGap, markStyle} from '../lib/type';
import {brandFields} from '../lib/schema';

const captionSchema = z.object({
  text: z.string(),
  startMs: z.number(),
  endMs: z.number(),
  timestampMs: z.number().nullable(),
  confidence: z.number().nullable(),
  pageBreakAfter: z.boolean().optional(),
});

export const shortCaptionsSchema = z.object({
  ...brandFields,
  videoSrc: z.string().optional().describe('media/… nella public dir del render (lo prepara yt-remotion)'),
  videoStartSeconds: z.number().min(0).optional(),
  videoFit: z.enum(['cover', 'contain']),
  volume: z.number().min(0).max(2),
  captions: z.array(captionSchema),
  durationInSeconds: z.number().positive().max(600),
  fps: z.number().positive().max(120).optional(),
  combineMs: z.number().min(0).max(5000).describe('combineTokensWithinMilliseconds'),
  maxWordsPerPage: z.number().int().min(1).max(8),
  captionY: z.number().min(0.3).max(0.85).describe('centro del blocco sottotitoli (frazione di altezza)'),
  captionFont: z.enum(['display', 'body']),
  uppercase: z.boolean(),
  hookText: z.string().optional(),
  hookSeconds: z.number().min(0).max(10),
  hookY: z.number().min(120).max(900).optional().describe('bordo alto della card gancio in px'),
  accent: z.string().optional().describe('colore parola attiva: chiave dei token del brand (es. accent, accent_2) o hex'),
  progressBar: z.boolean(),
  progressPosition: z.enum(['top', 'bottom']),
  showSafeZone: z.boolean().describe('debug: disegna il box sicuro 900×1400'),
});
export type ShortCaptionsProps = z.infer<typeof shortCaptionsSchema>;

// Zona sicura Shorts (aneddotica, F2 §5.3): box centrale ~900×1400, niente nei 300 px bassi,
// nei 120 px alti e nella colonna destra dei pulsanti.
const SAFE = {left: 70, right: 130, top: 260, bottom: 1660};

type Page = {startMs: number; endMs: number; tokens: {text: string; fromMs: number; toMs: number}[]};

const prepareCaptions = (caps: Caption[]): Caption[] => {
  const withSpaces = caps.some((c, i) => i > 0 && c.text.startsWith(' '));
  return caps
    .filter((c) => c.text.trim() !== '')
    .map((c, i) => {
      let text = c.text.replace(/\s+/g, ' ');
      if (!withSpaces && i > 0) text = ` ${text.trim()}`;
      const sentenceEnd = /[.?!…]["»”)]?$/.test(text.trim());
      return {...c, text, pageBreakAfter: c.pageBreakAfter ?? sentenceEnd};
    });
};

/** Pagine TikTok → massimo N parole per pagina; ogni pagina si spegne poco dopo l'ultima parola. */
const toPages = (pages: TikTokPage[], maxWords: number, holdMs: number): Page[] => {
  const out: Page[] = [];
  pages.forEach((p, pi) => {
    // spazi interni → nbsp, così una parola = un token anche dopo l'impaginazione
    const tokens = p.tokens
      .map((t) => ({text: t.text.trim().replace(/\s+/g, '\u00a0'), fromMs: t.fromMs, toMs: t.toMs}))
      .filter((t) => t.text);
    const nextStart = pi + 1 < pages.length ? pages[pi + 1].startMs : Infinity;
    for (let i = 0; i < tokens.length; i += maxWords) {
      const chunk = tokens.slice(i, i + maxWords);
      const after = i + maxWords < tokens.length ? tokens[i + maxWords].fromMs : nextStart;
      const end = Math.min(after, chunk[chunk.length - 1].toMs + holdMs);
      out.push({startMs: chunk[0].fromMs, endMs: Math.max(end, chunk[0].fromMs + 250), tokens: chunk});
    }
  });
  return out;
};

const HookCard: React.FC<{theme: Theme; text: string; p: number; ready: boolean; top: number}> = ({theme, text, p, ready, top}) => {
  const ed = theme.family === 'editorial';
  const fit = useMemo(
    () =>
      ready
        ? fitBalanced({
            text,
            fontFamily: ed ? theme.display : theme.body,
            fontWeight: ed ? 400 : 700,
            uppercase: ed,
            maxWidth: 800,
            maxHeight: 300,
            lineHeight: ed ? 1.0 : 1.08,
            maxLines: 3,
            maxFontSize: ed ? 70 : 64,
          })
        : {fontSize: 60, lines: [text]},
    [ready, text, ed, theme.display, theme.body],
  );
  return (
    <div style={{position: 'absolute', left: SAFE.left, right: SAFE.right, top, display: 'flex', justifyContent: 'center'}}>
      <div
        style={{
          transform: `translateY(${(1 - p) * -30}px) scale(${0.94 + 0.06 * p})`,
          opacity: p,
          background: ed ? theme.surface : theme.bg,
          border: ed ? 'none' : `2px solid ${theme.line}`,
          borderRadius: ed ? 26 : 2,
          padding: ed ? '24px 34px 26px' : '22px 30px 26px',
          boxShadow: ed ? `0 14px 40px ${alpha(theme.fg, 0.28)}` : 'none',
          textAlign: 'center',
        }}
      >
        {fit.lines.map((l, i) => (
          <div
            key={i}
            style={{
              marginTop: accentGap(l, i, ed) * fit.fontSize,
              fontFamily: ed ? theme.display : theme.body,
              fontWeight: ed ? 400 : 700,
              fontSize: fit.fontSize,
              lineHeight: ed ? 1.0 : 1.08,
              letterSpacing: ed ? '0' : '-0.02em',
              textTransform: ed ? 'uppercase' : 'none',
              color: theme.fg,
              whiteSpace: 'nowrap',
            }}
          >
            {l}
          </div>
        ))}
      </div>
    </div>
  );
};

export const ShortCaptions: React.FC<ShortCaptionsProps> = (props) => {
  const ready = useBrandFonts(props.style);
  const theme = makeTheme(props.brand, props.tokens, props.style);
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width} = useVideoConfig();
  const ed = theme.family === 'editorial';
  const tMs = (frame / fps) * 1000;
  const fontFamily = props.captionFont === 'display' ? theme.display : theme.body;
  const fontWeight = props.captionFont === 'display' && ed ? 400 : 800;
  const upper = props.uppercase;

  const pages = useMemo(() => {
    const caps = prepareCaptions(props.captions as Caption[]);
    if (!caps.length) return [];
    const {pages: tk} = createTikTokStyleCaptions({captions: caps, combineTokensWithinMilliseconds: props.combineMs});
    return toPages(tk, props.maxWordsPerPage, 700);
  }, [props.captions, props.combineMs, props.maxWordsPerPage]);

  // Corpo per pagina: max 2 righe nel box sicuro, corpo massimo costante per coerenza.
  const layouts = useMemo(() => {
    if (!ready) return [];
    return pages.map((pg) =>
      fitBalanced({
        text: pg.tokens.map((t) => t.text).join(' '),
        fontFamily,
        fontWeight,
        uppercase: upper,
        letterSpacingEm: ed ? 0 : -0.01,
        maxWidth: width - SAFE.left - SAFE.right - 40,
        maxHeight: 2 * 1.12 * 104,
        lineHeight: 1.12,
        maxLines: 2,
        maxFontSize: ed ? (props.captionFont === 'display' ? 92 : 100) : 96,
        extraEmPerLine: 0.3,
      }),
    );
  }, [ready, pages, fontFamily, fontWeight, upper, ed, width, props.captionFont]);

  const idx = pages.findIndex((p) => tMs >= p.startMs && tMs < p.endMs);
  const page = idx >= 0 ? pages[idx] : null;
  const layout = idx >= 0 ? layouts[idx] : null;
  const pop = page ? ramp(tMs, page.startMs, 110) : 0;
  const hookP = props.hookText
    ? Math.min(ramp(frame, 2, 8), 1 - ramp(frame, Math.round(props.hookSeconds * fps) - 6, 6, easeIn))
    : 0;
  const videoSrc = resolveSrc(props.videoSrc);
  const stroke = ed ? theme.fg : '#000000';
  const fill = ed ? '#ffffff' : theme.fg;
  // Un display molto nero (es. un condensato pesante): contorno sottile o riempie gli occhielli; i sans 800 reggono di più.
  const strokeEm = props.captionFont === 'display' && ed ? 0.055 : 0.11;
  // Colore della parola attiva: chiave dei token (es. un accento chiaro su un set scuro) o hex.
  const colors = (props.tokens as {colors?: Record<string, string>} | undefined)?.colors ?? {};
  const accent = props.accent ? colors[props.accent] ?? (props.accent.startsWith('#') ? props.accent : theme.accent) : theme.accent;

  // Indice della parola attiva = ultima parola iniziata (resta accesa fino alla successiva).
  let active = -1;
  if (page) page.tokens.forEach((t, i) => (tMs >= t.fromMs ? (active = i) : null));

  let k = 0;
  return (
    <AbsoluteFill style={{backgroundColor: videoSrc ? '#000' : 'transparent'}}>
      {videoSrc ? (
        <OffthreadVideo
          src={videoSrc}
          trimBefore={props.videoStartSeconds ? Math.round(props.videoStartSeconds * fps) : undefined}
          volume={props.volume}
          style={{width: '100%', height: '100%', objectFit: props.videoFit}}
        />
      ) : null}
      {ready && page && layout ? (
        <div
          style={{
            position: 'absolute',
            left: SAFE.left,
            right: SAFE.right,
            top: props.captionY * 1920 - 200,
            height: 400,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            transform: `scale(${0.9 + 0.1 * pop})`,
          }}
        >
          {layout.lines.map((line, li) => (
            <div key={li} style={{whiteSpace: 'nowrap', textAlign: 'center', lineHeight: 1.12}}>
              {line.split(' ').map((w, wi) => {
                const ti = k++;
                const on = ti === active;
                return (
                  <span
                    key={wi}
                    style={{
                      display: 'inline-block',
                      fontFamily,
                      fontWeight,
                      fontSize: layout.fontSize,
                      textTransform: upper ? 'uppercase' : 'none',
                      letterSpacing: ed ? '0' : '-0.01em',
                      ...(ed ? markStyle(fontFamily, upper, 0.1, 0.1) : {padding: '0 0.1em'}),
                      margin: '0 0.08em',
                      borderRadius: 0.16 * layout.fontSize,
                      color: on ? (ed ? theme.onAccent : accent) : fill,
                      background: on && ed ? accent : 'transparent',
                      WebkitTextStroke: on && ed ? '0px transparent' : `${strokeEm * layout.fontSize}px ${stroke}`,
                      paintOrder: 'stroke fill',
                      textShadow: on && ed ? 'none' : `0 ${0.05 * layout.fontSize}px ${0.1 * layout.fontSize}px ${alpha('#000000', 0.45)}`,
                      transform: on ? 'scale(1.06)' : 'none',
                    }}
                  >
                    {w}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      ) : null}
      {props.hookText && hookP > 0 ? <HookCard theme={theme} text={props.hookText} p={hookP} ready={ready} top={props.hookY ?? 200} /> : null}
      {props.progressBar ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            [props.progressPosition === 'bottom' ? 'bottom' : 'top']: 0,
            height: 10,
            background: alpha('#ffffff', 0.22),
          }}
        >
          {/* brand generici: accento già usato dalla parola attiva → barra nel colore del testo (un solo accento) */}
          <div style={{width: `${((frame + 1) / durationInFrames) * 100}%`, height: '100%', background: ed ? accent : theme.fg}} />
        </div>
      ) : null}
      {props.showSafeZone ? (
        <div
          style={{
            position: 'absolute',
            left: SAFE.left,
            right: SAFE.right,
            top: SAFE.top,
            height: SAFE.bottom - SAFE.top,
            border: '4px dashed rgba(255,0,128,0.8)',
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
