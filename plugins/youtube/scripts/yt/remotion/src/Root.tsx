// Composizioni di YouTube Producer. Tutte parametriche: brand, testi, durata e risoluzione
// arrivano dalle props (file JSON passato da `yt-remotion`); i default servono allo Studio.
import React from 'react';
import {CalculateMetadataFunction, Composition, Folder, Still} from 'remotion';
import {ChapterCard, chapterCardSchema, ChapterCardProps} from './compositions/ChapterCard';
import {ColdOpenTitle, coldOpenTitleSchema, ColdOpenTitleProps} from './compositions/ColdOpenTitle';
import {EndPlate, endPlateSchema, EndPlateProps} from './compositions/EndPlate';
import {IntroSting, introStingSchema, IntroStingProps} from './compositions/IntroSting';
import {LowerThird, lowerThirdSchema, LowerThirdProps} from './compositions/LowerThird';
import {ShortCaptions, shortCaptionsSchema, ShortCaptionsProps} from './compositions/ShortCaptions';
import {ThumbnailStill, thumbnailStillSchema} from './compositions/ThumbnailStill';
import {secondsToFrames} from './lib/anim';
import {timedMetadata} from './lib/schema';

const shortMetadata: CalculateMetadataFunction<ShortCaptionsProps> = ({props}) => {
  const fps = props.fps ?? 30;
  return {fps, durationInFrames: secondsToFrames(props.durationInSeconds, fps), width: 1080, height: 1920};
};

// Segnaposto per lo Studio (il render vero calcola tutto da calculateMetadata).
const BASE = {width: 3840, height: 2160, fps: 30} as const;

export const RemotionRoot: React.FC = () => (
  <>
    <Folder name="Overlay">
      <Composition
        id="LowerThird"
        component={LowerThird}
        schema={lowerThirdSchema}
        calculateMetadata={timedMetadata<LowerThirdProps>()}
        defaultProps={{
          brand: 'demo',
          resolution: '4k',
          durationInSeconds: 5,
          name: 'Paolo Bianchi',
          role: 'Fondatore, Officina Esempio',
          position: 'auto',
        }}
        {...BASE}
        durationInFrames={150}
      />
      <Composition
        id="ChapterCard"
        component={ChapterCard}
        schema={chapterCardSchema}
        calculateMetadata={timedMetadata<ChapterCardProps>()}
        defaultProps={{
          brand: 'demo',
          resolution: '4k',
          durationInSeconds: 3,
          number: 3,
          title: 'Perché il primo cliente arrivò per caso',
          label: 'Capitolo',
          mode: 'full',
        }}
        {...BASE}
        durationInFrames={90}
      />
    </Folder>
    <Folder name="Sting">
      <Composition
        id="ColdOpenTitle"
        component={ColdOpenTitle}
        schema={coldOpenTitleSchema}
        calculateMetadata={timedMetadata<ColdOpenTitleProps>()}
        defaultProps={{
          brand: 'demo',
          resolution: '4k',
          durationInSeconds: 2.5,
          hook: 'Il prototipo era pronto in una notte',
          highlight: 'prototipo',
          kicker: 'Il Caffè dei Maker · con Paolo Bianchi',
          background: 'paper',
          exit: false,
        }}
        {...BASE}
        durationInFrames={75}
      />
      <Composition
        id="IntroSting"
        component={IntroSting}
        schema={introStingSchema}
        calculateMetadata={timedMetadata<IntroStingProps>()}
        defaultProps={{brand: 'demo', resolution: '4k', durationInSeconds: 3, subtitle: 'con: Paolo Bianchi', exit: false}}
        {...BASE}
        durationInFrames={90}
      />
      <Composition
        id="EndPlate"
        component={EndPlate}
        schema={endPlateSchema}
        calculateMetadata={timedMetadata<EndPlateProps>()}
        defaultProps={{
          brand: 'demo',
          resolution: '4k',
          durationInSeconds: 20,
          headline: 'Continua a guardare',
          slotLabels: ['Prossimo episodio', 'Ti consigliamo'],
          subscribeLabel: 'Iscriviti',
          showGuides: true,
        }}
        {...BASE}
        durationInFrames={600}
      />
    </Folder>
    <Folder name="Shorts">
      <Composition
        id="ShortCaptions"
        component={ShortCaptions}
        schema={shortCaptionsSchema}
        calculateMetadata={shortMetadata}
        defaultProps={{
          brand: 'demo',
          videoFit: 'cover',
          volume: 1,
          captions: [],
          durationInSeconds: 10,
          combineMs: 800,
          maxWordsPerPage: 4,
          captionY: 0.64,
          captionFont: 'display',
          uppercase: true,
          hookSeconds: 3,
          progressBar: false,
          progressPosition: 'top',
          showSafeZone: false,
        }}
        width={1080}
        height={1920}
        fps={30}
        durationInFrames={300}
      />
    </Folder>
    <Folder name="Thumbnail">
      <Still
        id="ThumbnailStill"
        component={ThumbnailStill}
        schema={thumbnailStillSchema}
        defaultProps={{
          brand: 'demo',
          text: 'Ho cambiato tutto',
          highlight: 'tutto',
          background: 'pastel',
          side: 'right',
          faceHeight: 0.38,
          badge: '', // niente badge di default: un numero episodio finto finirebbe in produzione
          showSafeZones: false,
        }}
        width={1280}
        height={720}
      />
    </Folder>
  </>
);
