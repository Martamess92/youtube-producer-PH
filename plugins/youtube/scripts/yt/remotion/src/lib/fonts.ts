// Font del brand caricati con FontFace + staticFile: quelli del plugin da public/fonts (copie OFL di
// assets/fonts), quelli di un brand esterno da style.fonts (file collegati da yt-remotion nella public dir
// come brand/…). Il render aspetta i font con delayRender: niente fallback di sistema nei frame.
import {useEffect, useState} from 'react';
import {staticFile, useDelayRender} from 'remotion';
import type {BrandStyle, FontSpec} from './brand';

const BASE_FONTS: FontSpec[] = [
  {family: 'Anton', file: 'fonts/Anton-Regular.ttf', weight: '400'},
  {family: 'Inter', file: 'fonts/Inter-Variable.ttf', weight: '100 900'},
];

const loading = new Map<string, Promise<void>>();

const loadOne = (f: FontSpec): Promise<void> => {
  const key = `${f.family}|${f.file}|${f.weight ?? ''}`;
  let p = loading.get(key);
  if (!p) {
    const face = new FontFace(f.family, `url('${staticFile(f.file)}')`, {weight: f.weight ?? '100 900', display: 'block'});
    p = face.load().then((loaded) => {
      document.fonts.add(loaded);
    });
    loading.set(key, p);
  }
  return p;
};

export const loadBrandFonts = (style?: BrandStyle | null): Promise<void> =>
  Promise.all([...BASE_FONTS, ...(style?.fonts ?? []).filter((f) => f && f.family && f.file)].map(loadOne)).then(
    () => undefined,
  );

/** true quando i font sono pronti; fino ad allora il frame resta in delayRender. */
export const useBrandFonts = (style?: BrandStyle | null): boolean => {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender('Font del brand', {timeoutInMilliseconds: 60000}));
  const [ready, setReady] = useState(false);
  const key = JSON.stringify(style?.fonts ?? []);
  useEffect(() => {
    loadBrandFonts(style)
      .then(() => {
        setReady(true);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cancelRender, continueRender, handle, key]);
  return ready;
};
