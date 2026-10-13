// Helper di animazione e unità. Tutto deterministico (solo funzione del frame).
import {Easing, interpolate, staticFile, useVideoConfig} from 'remotion';

export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);
export const easeIn = Easing.bezier(0.7, 0, 0.84, 0);

/** 0→1 tra `from` e `from+dur` (clamp). */
export const ramp = (frame: number, from: number, dur: number, easing = easeOut): number =>
  interpolate(frame, [from, from + Math.max(1, dur)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  });

/** Entrata + uscita: 0 al primo frame, 1 nel mantenimento, 0 all'ultimo frame. */
export const inOut = (frame: number, total: number, inFrom: number, inDur: number, outDur: number): number => {
  const enter = ramp(frame, inFrom, inDur);
  const exit = outDur > 0 ? ramp(frame, total - 1 - outDur, outDur, easeIn) : 0;
  return Math.min(enter, 1 - exit);
};

/** Unità di layout: 1 = 1 px su una tela 1920×1080 (o 1080×1920 in verticale). */
export const useUnit = (): number => {
  const {width, height} = useVideoConfig();
  return width >= height ? width / 1920 : width / 1080;
};

/** Sorgenti media: relative → staticFile (public dir del render), URL → invariati. */
export const resolveSrc = (src?: string | null): string | null => {
  if (!src) return null;
  if (/^(https?:|data:|blob:)/.test(src)) return src;
  return staticFile(src.replace(/^\/+/, ''));
};

export const RESOLUTIONS = {
  '4k': {width: 3840, height: 2160},
  '1080p': {width: 1920, height: 1080},
} as const;

export const secondsToFrames = (s: number, fps: number) => Math.max(1, Math.round(s * fps));
