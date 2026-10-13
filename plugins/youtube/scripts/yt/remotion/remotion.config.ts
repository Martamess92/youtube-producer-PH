// Config Remotion di YouTube Producer. Il wrapper `yt-remotion` passa comunque tutti i flag
// espliciti (codec, browser, concurrency, public dir): qui solo i default sicuri per lo Studio.
import {Config} from '@remotion/cli/config';

Config.setEntryPoint('./src/index.ts');
Config.setOverwriteOutput(true);
// Niente chiave licenza: Remotion 4.0.534 invia eventi d'uso solo se ne riceve una.
