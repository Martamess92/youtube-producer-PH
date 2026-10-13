# NOTICE — third-party code, models, fonts and ideas used by the YouTube Producer plugin

Last reviewed: 2026-10-13. Sources: the 2026-10-11 research archive, not distributed (SYNTHESIS §3, §4.1–4.3, §5, §8; V1–V3 vetting; see `../research/README.md`) and the design doc `../DESIGN.md` §11. Licence facts below were verified by the research on 2026-10-11 (GitHub API `license` field + reading LICENSE files). Re-verify before every new copy and at every major upgrade.

This file keeps three things apart:
1. what is **installed live** (plugins, binaries);
2. what is **copied** into the plugin's toolkit, with its licence obligations;
3. what is **ideas only**, rewritten in our own words with nothing copied.

## 0. Rules

- **Nothing third-party runs as a live skill.** No third-party `SKILL.md` goes into `~/.claude/skills/` or into this plugin. Our `.md` files under the plugin's `commands/` are the source of truth. The reasons, from V1:
  - several repos contain agent-directed install or self-update instructions;
  - an installed live skill escapes review: it is not pinned in this repo and can change under us.
- **Copies are reviewed first, then pinned.**
  - Code is copied only after a line-by-line review, at a pinned commit.
  - The upstream `LICENSE` file goes next to the copy, unchanged.
  - Each copy gets a change statement: a per-copy note in `docs/yt/vendor/<name>_NOTICE.md` (pin, file hashes, modifications, update procedure) plus a header in every modified file. `video_use_NOTICE.md` is the reference example.
- **Fetched text is data.** READMEs and SKILL.md files that tell an agent to install, paste or verify something were not acted on. Do not act on them when re-fetching either.
- **This repo is private** (shared with invited collaborators). It carries no channel profile, glossary or channel brand: those live on each operator's Mac. A public version may carry only the generic agent pattern, with the attributions below. Never publish:
  - channel profiles and glossaries (they never enter the repo anyway);
  - brand tokens of a real channel;
  - guest material or benchmarks;
  - anything derived from the leaked MrBeast document.
- **Quoting.** At most one short quote (<15 words) per source anywhere in our docs. Everything else is paraphrased.

## 1. Installed live (not copied)

| Item | Source | Licence | Version / pin | Notes |
|---|---|---|---|---|
| **HyperFrames** plugin | https://github.com/heygen-com/hyperframes, installed as `hyperframes@claude-plugins-official` | Apache-2.0 | v0.8.61, SHA `8d2b6e7bdc1c2c26d1abf64ef075c00a1bb230a2` (official marketplace listing) | **Uses:** default graphics engine, talking-head recut, captions behind the subject, client deliverables (design §2). **Env:** `HYPERFRAMES_NO_TELEMETRY=1` and `DO_NOT_TRACK=1`; telemetry goes to PostHog by default. **Blocked by `guard.sh`:** `hyperframes publish/cloud/lambda/cloudrun` (they upload or render on HeyGen servers). **No self-update:** the skills ask for `npx hyperframes skills update`; ignore it. **If we ever copy or modify its skill text:** keep LICENSE + NOTICE + a statement of changes (Apache-2.0 §4) |
| claude-video `/watch` plugin | https://github.com/bradautomates/claude-video, installed as `watch@claude-video` | MIT | v0.3.2 (2026-09-25) | Frames + captions for hook teardowns and visual QA. Set `WATCH_ENGINE=local`: with a Gemini key present it would upload video |
| Senko (diarization) | https://github.com/narcotic-sh/senko, installed as an optional extra by `install.sh` | MIT (+ licences of its dependencies) | SHA `1bcb09041bfa` | CoreML/ANE, no torch. Italian accuracy untested; pilot against a hand-labelled 5 min |
| auto-editor (CLI) | https://github.com/WyattBlue/auto-editor | Unlicense (code), **paid-key gates in the binary** since July 2026 | v31.7.2 | Analysis, single-source cut lists and NLE export only (see §5) |

## 2. Code copied into the toolkit (`scripts/yt/vendor/` in the plugin)

| Source | Licence | Pin | What we take | Our changes | Status on 2026-10-11 |
|---|---|---|---|---|---|
| browser-use/video-use — https://github.com/browser-use/video-use | MIT, Copyright (c) 2026 Browser Use | `43cfc566833548093455c9d4a46bd69913b7e552` | `pack_transcripts.py`, `timeline_view.py`, `render.py`, `grade.py` + `LICENSE` (per-file SHA-256 in `vendor/video_use_NOTICE.md`). Its 12 hard editing rules are paraphrased into `knowledge/05-editing-rules.md` | `transcribe*.py` not copied: they call paid ElevenLabs Scribe, replaced by `yt-transcribe` (whisper.cpp). `ffmpeg-full` by absolute path, an `INPUT_ARGS` hook for decoder flags before `-i` (VideoToolbox; the AAC decoder comes from `ytcore.aac_decoder_args`, `knowledge/05` §11), a safe default output dir. Every file carries a header listing its changes. Its SKILL.md is **not** loaded: it asks for `npx --yes` installs | **Copied 2026-10-11** via `gh api` at the pinned SHA, after a full read (no network calls, no installers, no `shell=True`). Details and update procedure: `vendor/video_use_NOTICE.md` |
| louisedesadeleer/clipify — https://github.com/louisedesadeleer/clipify | MIT | not pinned yet | `build_ass.py` caption presets (2–4-word chunks, active-word highlight), ROI motion-energy speaker detector, pan/stack ffmpeg expressions | Adapted to Italian chunking and current Shorts specs | Planned. Pin the SHA at copy time |

## 3. Adapted with attribution (permissive licences; reimplemented in our own files)

Nothing here is copied verbatim unless the row says so. These are methods we re-expressed in the plugin's `commands/*.md`, `docs/yt/knowledge/*` or our own code. Attribution is still given because we adopted their structure.

| Source | Licence | What we adopted | Cautions |
|---|---|---|---|
| ericosiu/ai-marketing-skills (`video-content-engine`, `podcast-ops`) — https://github.com/ericosiu/ai-marketing-skills | MIT | Claim and rights ledgers, portfolio spine, content-atom inventory, quality gates | Strip its telemetry preamble if any text is ever copied |
| TheCraigHewitt/skills (`youtube/*`) — https://github.com/TheCraigHewitt/skills | MIT | 3-step hook, retention-editing pacing, thumbnail glance test | Its unsourced percentages were dropped |
| Jakeschincariol/youtube-agent-skill — https://github.com/Jakeschincariol/youtube-agent-skill | MIT | Weakest-link hook score, dead-air and retake logic, chapter validator | **Reimplemented after review, never installed.** The README tells readers to paste the URL into an agent, and star growth looks inflated |
| yaxeen/storytelling-skills — https://github.com/yaxeen/storytelling-skills | MIT | Open-loop tracker, sag-point re-hook, five-zone retention audit | Markdown only. Never run its `install.sh` |
| mutonby/openshorts — https://github.com/mutonby/openshorts | MIT core; **`cloud/` is proprietary** ("OpenShorts Commercial License") | Window scoring, the 2-second rule, stands-alone rule, trim-by-score (logic only) | Nothing from `cloud/`. Its clip-count floor is tuned for SaaS retention, not viewers |
| Anil-matcha/AI-Youtube-Shorts-Generator — https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator | MIT (LICENSE added 2026-09-10) | 8-signal highlight taxonomy, chunking long sources, >50% overlap dedupe | Commercial upsell in its README; ignored |
| higgsfield-ai/skills (thumbnail) — https://github.com/higgsfield-ai/skills | MIT | Truthful-gap rule, ≥5 concepts before choosing, text-free image generation + HTML text overlay, surgical edit scopes | Never its `curl \| sh` install or paid self-verification |
| vid-io/vidiq-mcp (skills) — https://github.com/vid-io/vidiq-mcp | Apache-2.0 (+ vidIQ trademarks; some content CC-BY-4.0) | Discipline for reading retention graphs (paraphrased) | No vidIQ marks in our docs. If text is ever copied: Apache-2.0 NOTICE + changes, or CC-BY attribution for those parts |
| hassancs91/claude-youtube-editor — https://github.com/hassancs91/claude-youtube-editor | MIT | Element-menu interview, verify-before-show, letter/number versioning of variants, contact sheets | Its upload tool is out of scope (we never upload) |
| iart-ai/lower-thirds-skills, iart-ai/youtube-video-skills — https://github.com/iart-ai/lower-thirds-skills , https://github.com/iart-ai/youtube-video-skills | MIT | Lower-third craft rules, alpha-delivery verification, outro plate respecting end-screen zones | Young repos (1–5 stars): read the code before running anything |
| kirbah/CreatorLens — https://github.com/kirbah/CreatorLens | MIT | Diagnose-first routing over five problem types; the «size vs business» question | Its lens files contain unverified stats: treat them as leads only |
| shkuratovdesigner/yuben-app — https://github.com/shkuratovdesigner/yuben-app | MIT | Trust rule (numbers come from scripts, the LLM only narrates), engagement sanity filter | **Never open it inside the operator's tree:** its CLAUDE.md imports files from outside the repo |
| ur-grue/autopunk-media-skills — https://github.com/ur-grue/autopunk-media-skills | MIT | Agent frontmatter composition; per-skill evals idea | — |
| magnus919/agent-skills (`youtube-thumbnail/evals`) — https://github.com/magnus919/agent-skills/tree/main/youtube-thumbnail | MIT | Eval pattern of `evals/thumbnail.evals.json` (three distinct hypotheses, ties to verifiable footage, no CTR guarantee, no invented person, quote or proof) and the cold-reader brief idea (thumbnail v2, 2026-10-12) | Cases and wording are ours; the attribution line sits in the evals file |

## 4. Ideas only — no licence, AGPL or leaked (nothing copied, rewritten in our own words)

| Source | Status | Idea we kept (paraphrased) |
|---|---|---|
| 10xcoldleads/multicam-podcast-editor-skill — https://github.com/10xcoldleads/multicam-podcast-editor-skill | No licence | Multicam doctrine (F1 K-14): dialogue audio is the master clock; active-speaker close-up by default, wide shot for crosstalk, laughs and geography resets; reactions only when they add meaning; never cut on every word |
| horvay/multicam-podcast-editor — https://github.com/horvay/multicam-podcast-editor | Rejected as a tool (agent-directed persona file; does not build) | Switching heuristics |
| ChrisTitusTech/titus-ai (`youtube-thumbnail`) — https://github.com/ChrisTitusTech/titus-ai | No licence | «Preserve photographed people»: composite the real pixels, only crop, scale, position and a natural shadow |
| sharbelxyz/nova-youtube-agent — https://github.com/sharbelxyz/nova-youtube-agent | No LICENSE file (frontmatter claims MIT) | Memory files (posted, approved, rejected with reasons) and evidence labels on every recommendation |
| kenneth-liao/ai-launchpad-marketplace — https://github.com/kenneth-liao/ai-launchpad-marketplace | No licence | Separate reviewer agent for thumbnails; outlier-based reference gathering |
| Upload-Post/skill-autoshorts — https://github.com/Upload-Post/skill-autoshorts | MIT claimed only inside SKILL.md, no LICENSE file: treated as unlicensed | Visual QA by reading frames at t=1 s and midpoint; learn loop |
| op7418/Video-Wrapper-Skills — https://github.com/op7418/Video-Wrapper-Skills | No licence; rejected (duplicates HyperFrames) | — |
| remotion-dev/skills — https://github.com/remotion-dev/skills | No licence file | Not copied. Remotion itself is covered in §5 |
| openai/plugins (`plugins/higgsfield`) — https://github.com/openai/plugins | No licence | Confirms the hosted Higgsfield MCP endpoint; the paid-call policy is ours |
| ttfake92-lab/skills (`yyl-video-thumbnail`) — https://github.com/ttfake92-lab/skills/tree/main/skills/yyl-video-thumbnail | No licence | Pop-out over a darkened copy of the subject's own scene: reimplemented from scratch as the `scena` template (`thumb_fx.scene_frame/grade_plate` and the pop-out helper of `_common.js`), nothing copied (thumbnail v2, 2026-10-12) |
| Blueturboguy07/publikclip — https://github.com/Blueturboguy07/publikclip | **AGPL-3.0** | Auditable clip subscores, cross-validated multipliers, CC0-first music policy with a credits file. **No code, no prompt text copied** |
| MrBeast production document (leaked, unofficial) | **Leaked** | Retention and packaging principles, **paraphrase only**. Never quoted, never attached, never in the public repo |

## 5. Engines and tools with special licence terms

### Remotion (`scripts/yt/remotion/` in the plugin, Remotion 4.0.534)
- **Licence.** Custom "Remotion License", source-available, not OSI. Sources: https://github.com/remotion-dev/remotion/blob/main/LICENSE.md , https://www.remotion.dev/docs/license/faq , https://www.remotion.dev/docs/terms (verified 2026-10-11).
- **Free for:** individuals; for-profit organisations up to 3 people; non-profits; evaluation.
  - The 4.x LICENSE text says "employees".
  - The 5.0 terms (PR #3750, open on 2026-10-11) count contractors and part-timers too.
  - The FAQ already sums contractor and client headcount when they operate the same project.
- **Above the threshold:** a Company License.
  - Creators: $25 per seat per month.
  - Automators: $0.01 per render, $100/month minimum. Automator keys send per-render telemetry.
  - Enterprise: from $500/month [vendor pricing, read 2026-10-11].
- **Our rule (design §11).**
  - Remotion is used only for the brand templates of own and personal channels (their brands live outside the repo, in `brands_dirs`).
  - Only while the people working on that channel count at most 3 including collaborators, as confirmed by the operator in the channel profile (`graphics_licence.status`); until then the agent renders with HyperFrames.
  - Clients get finished files only (the FAQ says a client receiving only the MP4 is not a Remotion user), or HyperFrames.
  - Re-check at every Remotion major and whenever the team adds people. Note: `REMOTION_LICENSE_NOTE.md`.
- **Data shape.** We may mirror the neutral caption JSON shape of `@remotion/captions` (`text`, `startMs`, `endMs`, `timestampMs`, `confidence`). A field list is not copied code.

### auto-editor
- The code is Unlicense. Since July 2026 the binary gates three things behind a paid licence key:
  - renders above 3200×1800 (silently downscaled without a key);
  - multi-source exports;
  - the `add` effects action.
- **Rule:** use it only for analysis, single-source cut lists and FCPXML/Kdenlive/OTIO export. Final renders are always ffmpeg/VideoToolbox. Licence-key price unverifiable (app.auto-editor.com did not resolve on 2026-10-11).
- **Vendored skill references.** If its 4 `skills/*/SKILL.md` are copied into `docs/yt/vendor/auto-editor/`, add a «licence gates» note at the top of each.
- **Telemetry.** Do not install them via `npx skills add`, which has telemetry.

### ffmpeg-full
- GPL-3.0-or-later (Homebrew keg-only).
- It is used as a tool, called by absolute path. Our outputs are not bound by the GPL, and we do not redistribute the binary.

## 6. Models

| Model | Licence | Where | Attribution |
|---|---|---|---|
| Whisper large-v3-turbo (ggml) | MIT (OpenAI Whisper weights) | downloaded by `install.sh` (path in `yt-doctor`) | — |
| Silero VAD v6.2.0 (ggml) | MIT | downloaded by `install.sh` (path in `yt-doctor`; https://huggingface.co/ggml-org/whisper-vad) | — |
| NVIDIA Parakeet TDT 0.6B v3 (via `parakeet-cli` ggml or parakeet-mlx) | **CC-BY-4.0** (base model); the GGUF repo is tagged MIT but inherits the base licence | optional A/B engine (https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v3) | «Transcription may use NVIDIA Parakeet TDT 0.6B v3, licensed CC BY 4.0, https://creativecommons.org/licenses/by/4.0/». Keep this line in any repo or doc whose pipeline downloads or ships the model (design §11: «attribuire») |
| `u2net_human_seg.onnx` (HyperFrames local matting, ~168 MB) | **Not verified in the research** | downloaded by HyperFrames from rembg's GitHub release | Verify before client work |
| rembg `birefnet-portrait` (fallback cutout, Phase 3 only) | MIT code; BiRefNet weights MIT | optional extra of `install.sh`, only with the operator's OK | **Never** the default `bria-rmbg` (non-commercial) |
| MediaPipe Face Landmarker `face_landmarker.task` (float16/1, 3,758,596 bytes, SHA-256 pinned in `install.sh`) | Apache-2.0 (MediaPipe model card) | optional extra of `install.sh --with-mediapipe` → `<data>/models/mediapipe/`, loaded from disk; expression search in `yt-portrait scan` and the level-2b landmark check (`knowledge/07-thumbnails.md` §11.2) | — |

**Rejected for licence reasons** (do not reintroduce):
- WhisperX: its default Italian alignment model is CC BY-NC.
- CrisperWhisper: non-commercial models.
- upscayl: bundled models are CC-BY-NC-SA.
- videogrep: Anti-Capitalist licence, which excludes an Srl.
- ~~MediaPipe: telemetry with no opt-out.~~ Rejected on 2026-10-11 for undocumented telemetry; **re-admitted on 2026-10-12** as an opt-in extra (`install.sh --with-mediapipe`, `knowledge/11-compliance-safety.md` §9) after a closer reading found no statement either way. Integration check of 2026-10-12: no socket opened by the process in 47 `lsof -i` polls over a 60-frame Face Landmarker run plus 4 s idle (not a packet capture: the open item of `knowledge/11-compliance-safety.md` §9 — a network monitor on the operator's first run — stays open).

## 7. Fonts (`scripts/yt/assets/fonts/` in the plugin)

| Font | Licence | Licence file |
|---|---|---|
| Anton (thumbnail headlines and name plates of the built-in templates, display face of the `demo` brand, caption hooks of the preset `default`) | SIL OFL 1.1 | `OFL-Anton.txt` (google/fonts build, converted to TTF, no glyph changed) |
| Inter (body face of the `demo` brand and of `generic`, caption font of the preset `default` as static instances in `assets/ass/fonts/`, body fallback of the Remotion compositions) | SIL OFL 1.1 | `OFL-Inter.txt` |

Fonts of channel brands (own, personal or client) are not in the plugin: they live in the brand's folder in `brands_dirs` (`fonts/`), each with its own licence file (`knowledge/07-thumbnails.md` §8).

OFL rules:
- Rendering the fonts into videos and images is unrestricted.
- If the font files are redistributed, keep the OFL text with them and never sell them alone.

## 8. Other tools (installed, not redistributed)

| Tool | Licence |
|---|---|
| whisper.cpp 1.9.5 (+ `parakeet-cli`) | MIT |
| yt-dlp | Unlicense. Used for captions and metadata only, low volume, never with cookies: a conscious ToS grey zone (`knowledge/11-compliance-safety.md` §2–§3) |
| Playwright 1.64.0 (drives the installed Chrome) | Apache-2.0 |
| Toolkit Python deps (google-api-python-client, google-auth-oauthlib, numpy, librosa, matplotlib, pillow, requests, PyYAML) | Apache-2.0 / BSD / ISC / MIT mix: see `uv.lock` |
| Optional extra `mediapipe` (mediapipe 1.1.0 + opencv-contrib-python, sounddevice, flatbuffers), installed only with `install.sh --with-mediapipe` | Apache-2.0 / MIT / BSD-3-Clause: see `uv.lock` |

## 9. Obligations checklist when copying anything new

| Licence | What to do |
|---|---|
| MIT | Keep the upstream copyright line and the full licence text next to the copied code |
| Apache-2.0 | Keep LICENSE + upstream NOTICE (if any) + a prominent statement of what we changed |
| Unlicense | No obligation; record the source here anyway |
| CC-BY-4.0 | Attribution with the licence link, and say whether we changed it |
| SIL OFL 1.1 | Keep the OFL text; Reserved Font Names cannot be used for modified versions |
| No licence / AGPL / leaked | Do not copy. Write the idea in our own words and list it in §4 |

After every copy, update the relevant row (pin, date, path) in this file in the same change.

## 10. Data copied (vendored datasets)

| Dataset | Source | Licence | Version / date | Where | Our changes |
|---|---|---|---|---|---|
| YouTube thumbnail surface geometry (Engaged Views) | https://engagedviews.com/api/surfaces.json (provenance: https://engagedviews.com/sources/; MCP Registry `com.engagedviews/youtube-thumbnail-sizes`) | **CC BY 4.0**, https://creativecommons.org/licenses/by/4.0/ | dataset v1.1.1, measured 2026-08-28 (headless Firefox, logged out, viewports 1280/1600/1920); values read 2026-10-12 (thumbnail study, R2 §3.7) | `scripts/yt/data/surfaces.json`, read by `yt-thumb-qa` (216-px sidebar tile, 500-px search tile) | Values transcribed and re-shaped into our own JSON structure (field names are ours; no measurement added or changed). The file carries an `_attribution` block with author, source, licence and this change statement. Only the data is used: the MCP server in the same repo has no licence and is not installed or copied. Re-check against the upstream file before relying on a new value |

Attribution line to keep wherever the data is shown: «YouTube surface geometry: Engaged Views, CC BY 4.0, https://engagedviews.com/api/surfaces.json (adapted)».
