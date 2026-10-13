// Schemi zod delle props (validati da Remotion prima del render) e calculateMetadata comuni.
import {z} from 'zod';
import type {CalculateMetadataFunction} from 'remotion';
import {RESOLUTIONS, secondsToFrames} from './anim';

export const brandFields = {
  brand: z.string().describe('slug del brand: demo (brand neutro del plugin) oppure un brand esterno in brands_dirs'),
  tokens: z.any().optional().describe('token del brand (iniettati da yt-remotion)'),
  style: z.any().optional().describe('stile delle composizioni generiche (<brand>/remotion.json, iniettato da yt-remotion)'),
};

export const timingFields = {
  resolution: z.enum(['4k', '1080p']).describe('4k = 3840×2160, 1080p = 1920×1080'),
  durationInSeconds: z.number().positive().max(600),
  fps: z.number().positive().max(120).optional(),
};

type Timed = {resolution?: '4k' | '1080p'; durationInSeconds: number; fps?: number};

/** Durata, fps e dimensioni dalle props (le composizioni sono tutte parametriche). */
export const timedMetadata =
  <T extends Record<string, unknown> & Timed>(): CalculateMetadataFunction<T> =>
  ({props}) => {
    const fps = props.fps ?? 30;
    const dims = RESOLUTIONS[props.resolution ?? '4k'];
    return {fps, durationInFrames: secondsToFrames(props.durationInSeconds, fps), ...dims};
  };
