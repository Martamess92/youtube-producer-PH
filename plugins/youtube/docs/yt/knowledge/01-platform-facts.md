# 01 Platform facts — specs, limits and measurement rules of YouTube (and Spotify) as of 2026-10-11

## How the skills use this file
- Every `/youtube:*` skill reads this file before stating a platform number, limit or rule; nothing platform-related is quoted from memory or from third-party skills.
- Cite facts by ID (e.g. `PF-AB-03`) in working notes; in Italian deliverables cite the rule in plain Italian plus the source URL in the "Fonti" block.
- A fact marked **(S)** was verified in the 2026-10-11 research pass (F/V reports); **(R)** was re-fetched from the source page while writing this file on 2026-10-11. Both count as "verified 2026-10-11".
- Anything not in this file, or older than its "Next re-verify" date, must be re-checked on the official page (WebFetch) before it drives a decision, and the result added here.
- Statistics and practitioner numbers are NOT platform facts: they live in `02-strategy-playbook.md` / `09-analytics-reading.md` with evidence labels; banned claims are in `10-evidence-ledger.md`.

**Next re-verify:** 2027-01-11 (quarterly), or immediately after any "Made on YouTube" event, a Help-page change noticed in Studio, or a failed assumption during a job.
**Label vocabulary:** see `10-evidence-ledger.md` §1. Platform facts here are `[official]` unless marked otherwise.

---

## 1. What counts as a view, an impression and an engaged view

| ID | Fact | Value / rule | Source | Verified | How the agent uses it |
|---|---|---|---|---|---|
| PF-VIEW-01 | New view definition (all formats) | From **2026-08-24** a view counts from the **first frame** of playback for Shorts, long-form, podcasts and Live; hover-autoplay on Home and a Short starting in the feed count as views. A thumbnail seen without interaction is an impression, not a view | https://blog.youtube/inside-youtube/engaged-views-youtube-explained/ (post dated 2026-08-19) | 2026-10-11 (R) | Raw `views` before and after 2026-08-24 are **not comparable**. Never chart raw views across the boundary |
| PF-VIEW-02 | Engaged view | The old view definition, renamed: a click/tap to watch, or watching past the initial seconds. Clicks/taps count as both a view and an engaged view. Engaged views are what qualifies for earning (public content) | same | 2026-10-11 (R) | **All period-over-period and episode-vs-episode comparisons use engaged views** (`engagedViews` in Analytics API, `engaged_views` in Reporting) |
| PF-VIEW-03 | Metrics anchored on engaged views | CTR, AVD and retention calculations are unchanged; recommendations and YPP unchanged | same | 2026-10-11 (R) | CTR/AVD/retention series are continuous across the boundary; views are not |
| PF-VIEW-04 | API note of the same change | Data API revision history dates the `viewCount` change to **2026-08-27** (public views counted from playback start, long-form/Live/Shorts) | https://developers.google.com/youtube/v3/revision_history | 2026-10-11 (R) | Treat **24–27 Aug 2026** as one measurement boundary; exclude that week from trend baselines |
| PF-VIEW-05 | Shorts view change (earlier) | Since **2025-03-31** a Shorts view counts every start/replay; the old metric survives as engaged views | https://ppc.land/youtube-changes-how-shorts-views-are-counted-from-march-31/ (secondary report of TeamYouTube) | 2026-10-11 (S) | Shorts before/after 2025-03-31: engaged views only |
| PF-VIEW-06 | Impression | Thumbnail shown > 1 s with ≥ 50% visible on screen. Impressions on external sites and end screens are not counted | https://support.google.com/youtube/answer/9314486 ; https://support.google.com/youtube/answer/7628154 | 2026-10-11 (S) / (R) | Views ÷ impressions ≠ CTR, because views also come from non-impression sources |
| PF-VIEW-07 | Impressions CTR range | Half of all channels and videos sit between **2% and 10%**; videos < 1 week old or < 100 views vary more; Home-heavy videos have lower CTR; channel-page-heavy videos higher | https://support.google.com/youtube/answer/7628154 | 2026-10-11 (R) | Never quote a universal "good CTR". Compare within the channel, per traffic source |
| PF-VIEW-08 | CTR judging rules | Wait for substantial impressions; act only on statistically significant changes; compare long-term with traffic sources in mind; do not test several thumbnails/titles sequentially on one video (traffic-source confound) | same | 2026-10-11 (R) | Sequential manual thumbnail swaps are banned as "tests"; use PF-AB |
| PF-VIEW-09 | Clickbait signal | High CTR + low AVD + lower-than-expected impressions together; such videos are recommended less | same | 2026-10-11 (R) | Packaging diagnosis row in `09-analytics-reading.md` §4 |

## 2. Retention, key moments, audience segments

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-RET-01 | Intro (key moment) | % of viewers still watching after the first **30 s** | https://support.google.com/youtube/answer/9314415 | 2026-10-11 (R) | The single official hook metric. On long episodes read it in Studio (API is too coarse, PF-YTA-07) |
| PF-RET-02 | Top moments / spikes / dips | Top moments: almost nobody dropped. Spikes: rewatched or shared (or confusing). Dips: skipped or left | same | 2026-10-11 (R) | Diagnosis table in `09` §4 |
| PF-RET-03 | Availability | Key moments need a video **≥ 60 s** with **≥ 100 views**; data takes **1–2 days** to process | same | 2026-10-11 (R) | Videos with < 100 views have no key moments: say "dato non disponibile", never estimate |
| PF-RET-04 | Typical retention baseline | Compares with your **10 latest videos of similar length** | same | 2026-10-11 (R) | Always read retention as above/below typical, not vs absolute % |
| PF-RET-05 | Audience segments | New = first watch in period (also private browsing, cleared history, > 1 year); Casual = returned monthly 1–5 of last 12 months; Regular = 6+ months; Returning = casual + regular. Segments do not affect reach or monetization; regular returners are more likely to be shown more videos; < 1% regular is normal for new channels | https://support.google.com/youtube/answer/10246996 | 2026-10-11 (S) | Community-led north stars use returning viewers (`02` §10) |
| PF-RET-06 | Recommendation inputs (official list) | Watch history, search history, subscriptions, likes, dislikes, "Not interested", "Don't recommend channel", satisfaction surveys. Home mainly from watch history; Up Next mainly from current video; Shorts feed personalized | https://support.google.com/youtube/answer/16089387 | 2026-10-11 (S) | Recommender principles in `02` §1 |
| PF-RET-07 | Search ranking factors | Relevance (title, tags, description, video content), engagement (query-specific watch time), quality (expertise, authority, trust) | https://support.google.com/youtube/answer/16090438 | 2026-10-11 (S) | Keyword-first chapter titles and descriptions |

## 3. Thumbnails

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-THUMB-01 | Video thumbnail size | **3840×2160** recommended, minimum width **640 px**, 16:9 recommended | https://support.google.com/youtube/answer/72431 | 2026-10-11 (R) | Render masters at 3840×2160 (`yt-thumb-render`) |
| PF-THUMB-02 | Shorts thumbnail size | **2160×3840** recommended, minimum height 640 px, 9:16; set only in desktop Studio | same | 2026-10-11 (R) | Shorts packaging effort goes to first frame + hook text (PF-SHORTS-07) |
| PF-THUMB-03 | Formats and file size | JPG or PNG. Mobile upload: **2 MB** (video), **10 MB** (podcast). Desktop: **50 MB** (video, Shorts, podcast) | same | 2026-10-11 (R) | Always export a JPEG < 2 MB fallback next to the PNG master |
| PF-THUMB-04 | Podcast playlist image | **1:1** square; 10 MB mobile / 50 MB desktop; no separate resolution published | same | 2026-10-11 (R) | A podcast show needs one square cover (once) |
| PF-THUMB-05 | Verification | Custom thumbnails require a verified account; strikes can remove the privilege | same | 2026-10-11 (R/S) | `youtube:setup` checklist |
| PF-THUMB-06 | Vertical video + 16:9 custom thumbnail | Replaced by an auto-generated **4:5** on Home, Explore, Subscriptions; the custom one still shows elsewhere | same (F3 §1.1) | 2026-10-11 (S) | Design text to survive a 4:5 centre crop when the upload is vertical |
| PF-THUMB-07 | API `thumbnails.set` | Max file **50 MB** since 2026-09-14 (was 2 MB); `fhd`/`qhd`/`uhd` thumbnail sizes exposed since 2026-09-11; costs 50 units | https://developers.google.com/youtube/v3/revision_history ; https://developers.google.com/youtube/v3/determine_quota_cost | 2026-10-11 (R) | Informational only: the agent **never** calls `thumbnails.set` (no write scopes) |
| PF-THUMB-08 | Per-language thumbnails | Creators with multi-language audio can upload per-language thumbnails (reported 2026-03-12); access gated | https://www.storyboard18.com/digital/youtube-introduces-translated-thumbnails-to-boost-global-video-discovery-91902.htm (secondary) | 2026-10-11 (S) | Later-stage lever for EN versions |
| PF-THUMB-09 | Rendered sizes in the UI | Desktop search **500×281**; desktop home/channel grid **347×195**; watch-page sidebar **216×121**; mobile web feed **375×211**; duration badge ≈ 48×20 px inset 8 px bottom-right; dark theme background **#0f0f0f** | measured with `getBoundingClientRect`, logged out, IT locale (F3 §1.7) `[observed 2026-10-11]` | 2026-10-11 (S) | QA sheet sizes; keep bottom-right ≈ 18%×15% clear. The old "168×94" sidebar size is outdated |
| PF-THUMB-10 | Policy | Thumbnails that trick users into clicking for something the video does not deliver violate spam/deceptive practices | https://support.google.com/youtube/answer/2801973 | 2026-10-11 (S) | Truthfulness gate in `07-thumbnails.md` |
| PF-THUMB-11 | AI in thumbnails | Using generative AI to create/improve a thumbnail is listed as production assistance that does **not** need the altered-content disclosure; disclosure targets realistic altered video (e.g. a real person saying/doing what they did not) | https://support.google.com/youtube/answer/14328491 | 2026-10-11 (S) | Disclosure not required, but house rule still forbids generative edits on guests (design §2.3) |

## 4. A/B testing ("A/B test titles & thumbnails", formerly Test & Compare)

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-AB-01 | What can be tested | Up to **3** variants: title only, thumbnail only, or title + thumbnail together | https://support.google.com/youtube/answer/13861714 | 2026-10-11 (R) | `youtube:thumbnail` always delivers 3 genuinely different concepts |
| PF-AB-02 | Winner metric | **Watch time**, not CTR | same | 2026-10-11 (R) | Design for clicks that stay; payoff inside 0–30 s |
| PF-AB-03 | Duration | A few days up to **2 weeks** | same | 2026-10-11 (R) | Schedule `youtube:review` read at D+14 |
| PF-AB-04 | Where / who | **Desktop Studio only**; **advanced features** required; content must follow Community Guidelines; 18+ videos must be marked or the test won't run | same | 2026-10-11 (R) | The operator launches tests by hand; no API exists to create or read tests (V3 §7) |
| PF-AB-05 | Not eligible | Shorts, scheduled Lives, Premieres (until they end and convert), made-for-kids, mature-audience, private. **Live archives are allowed** | same | 2026-10-11 (R) | A Premiere is testable only after it converts |
| PF-AB-06 | Outcomes | **Winner** (statistically significant) / **Performed same** (you pick) / **Inconclusive** (first uploaded becomes default) | same | 2026-10-11 (R) | Log all three in `ab_tests`; inconclusive is data (`09` §7) |
| PF-AB-07 | Resolution trap | If **any** thumbnail is below 1280×720, **all** are downscaled to 854×480 | same | 2026-10-11 (R) | Never upload a variant below 1280×720 |
| PF-AB-08 | Editing mid-test | Changing title or thumbnail **stops** the test; must be restarted manually | same | 2026-10-11 (R) | G3 checklist: "non toccare titolo/thumbnail durante il test" |
| PF-AB-09 | Mechanics | Small control group sees only the default (excluded from results); impressions split as evenly as possible; a viewer sees the same combination across surfaces; very similar variants run longer; test older videos first is suggested | same (V3 §7) | 2026-10-11 (S) | Variants must differ in lever, not wording |
| PF-AB-10 | Scale | 40M+ experiments run since 2024 (YouTube, self-reported) | https://blog.youtube/news-and-events/made-on-youtube-new-tools-power-creation-journey/ | 2026-10-11 (S) | Context only |

## 5. Titles, descriptions, tags, hashtags, translated metadata

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-META-01 | Tags | Minimal role in discovery; mainly useful for commonly misspelled terms | https://support.google.com/youtube/answer/146402 | 2026-10-11 (S) | Don't spend time on tags; add misspellings of guest/company names only |
| PF-META-02 | Hashtags | Up to **3** hashtags from the description appear above the title; with **> 60** hashtags YouTube ignores all; misleading/excessive tagging can lead to removal | https://support.google.com/youtube/answer/6390658 | 2026-10-11 (S) | Hashtag copy is the operator's (or a packaging skill's, if one is installed); the agent only checks limits |
| PF-META-03 | Translated title/description | Available to all creators; YouTube search uses translated metadata for viewers searching in that language | https://support.google.com/youtube/answer/13338784 | 2026-10-11 (S) | Free reach experiment: EN title+description on Italian episodes |
| PF-META-04 | Title guidance (official creators site) | Keywords early; avoid excessive caps/emoji; choose searchable vs curiosity depending on how viewers find you | https://www.youtube.com/creators/how-things-work/content-creation-strategy/ | 2026-10-11 (S) | Packaging rules `02` §4 |

## 6. Chapters and end screens

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-CHAP-01 | Manual chapter rules | First timestamp **00:00**; at least **3** timestamps; **ascending**; each chapter **≥ 10 s**; written in the description | https://support.google.com/youtube/answer/9884579 | 2026-10-11 (R) | `yt-chapters` validates deterministically |
| PF-CHAP-02 | Automatic chapters | "Allow automatic chapters" is on by default; manual chapters override automatic ones | same | 2026-10-11 (R) | Always ship manual chapters on long episodes |
| PF-CHAP-03 | Unavailable when | Channel has active strikes; content may be inappropriate for some viewers; some channels need advanced features | same | 2026-10-11 (R) | If chapters don't appear, check these before re-uploading anything |
| PF-CHAP-04 | Format above 60 min | Use `h:mm:ss` once the video exceeds 60 min (validator rule, F6 A9) | F6 A9 | 2026-10-11 (S) | Long podcast episodes often cross 60 min |
| PF-END-01 | End screen rules | Video **≥ 25 s**; elements only in the **last 5–20 s**; up to **4** elements on 16:9 | https://support.google.com/youtube/answer/6388789 | 2026-10-11 (R) | Edit holds a quiet 20 s end plate |
| PF-END-02 | Element types | Video/playlist; Subscribe; Channel; Link to external site (**requires YPP**) | same | 2026-10-11 (R) | Channels outside YPP: no external-link element |
| PF-END-03 | Not shown | Mobile web (except iPad), YouTube Music and Kids apps, 360 videos; viewers can hide them; never on made-for-kids | same | 2026-10-11 (R) | Never rely on end screens alone for the next-episode bridge: say it in the audio too |

## 7. Shorts

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-SHORTS-01 | Max length | Up to **3 min** for square or vertical uploads on/after **2024-10-15** (standard channels) | https://support.google.com/youtube/answer/15424877 | 2026-10-11 (R) | Clip length bands in `08-shorts-clip-engine.md` |
| PF-SHORTS-02 | What is a Short | Square or vertical aspect ratio; 16:9 is long-form | same | 2026-10-11 (R) | 1080×1920 delivery |
| PF-SHORTS-03 | Claimed music over 1 min | A Short > 1 min with an active Content ID claim is **blocked globally** until resolved (no penalty) | same | 2026-10-11 (R) | Never put third-party music in Shorts > 60 s |
| PF-SHORTS-04 | Audio Library in Shorts | Most Audio Library songs usable up to 90 s of a 3-min Short (some 60/30 s); royalty-free Audio Library music is not claimed | same; https://support.google.com/youtube/answer/3376882 | 2026-10-11 (R) | Audio Library is YouTube-only safe: no off-platform guidance (Spotify, LinkedIn) |
| PF-SHORTS-05 | Related video link | Each Short can link to a long-form video, live or Short (Studio → Content → Short → Related video). Official guidance: Short must stand alone; last ~5 s verbal + visual CTA; the long-form must open with exactly what the Short promised within **5–10 s** | https://blog.youtube/creator-and-artist-stories/youtube-related-videos-traffic-guide/ (2026-07-14) | 2026-10-11 (S) | Every podcast Short links to its episode |
| PF-SHORTS-06 | Separate systems | Shorts and long-form use separate recommendation systems; YouTube reports no evidence that Shorts hurt long-form | https://blog.youtube/creator-and-artist-stories/debunking-common-myths-about-youtube-shorts/ (2025-05-06) | 2026-10-11 (S) | Measure anyway (`10` HYP-07) |
| PF-SHORTS-07 | Custom Shorts thumbnails | Mostly unseen in the feed (Todd Sherman, 2023) | https://techcrunch.com/2023/08/25/youtube-demystifies-the-shorts-algorithm-views-and-answers-other-creator-questions/ `[official·secondary]` | 2026-10-11 (S) | First frame + text hook carry the packaging |
| PF-SHORTS-08 | Edit into a Short | Studio/mobile timeline editor on own long-form; links back automatically; reported limit ~60 s via this route | https://www.xda-developers.com/youtube-shorts-created-from-videos/ (secondary) | 2026-10-11 (S) | Our engine uploads local vertical files instead (up to 3 min) |
| PF-SHORTS-09 | Shorts metric | Studio "Stayed to watch vs Swiped away" (formerly viewed vs swiped away): share of feed shows watched past the opening; YouTube publishes no seconds threshold | https://support.google.com/youtube/answer/12220281 | 2026-10-11 (S) | Compare Shorts within channel only |
| PF-SHORTS-10 | AI podcast clip suggestions | Announced 2025-09-16 for **US** video podcasters first | https://techcrunch.com/2025/09/16/youtube-to-use-ai-to-help-podcasters-promote-themselves-with-clips-and-shorts/ | 2026-10-11 (S) | Assume unavailable in Italy until seen in Studio |

## 8. Podcasts on YouTube

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-POD-01 | Structure | A podcast show = a playlist designated as podcast; each episode = a video | https://support.google.com/youtube/answer/12950577 | 2026-10-11 (R) | The show's "Podcast" playlist |
| PF-POD-02 | One per show | One public podcast per show; don't split seasons into separate podcasts | same | 2026-10-11 (R) | — |
| PF-POD-03 | Content | **Only full-length episodes**; no clips, no other shows, no other channels' uploads; all seasons in the order they should be consumed | same; https://support.google.com/youtube/answer/12751636 | 2026-10-11 (R/S) | Shorts, clips, trailers stay OUT of the podcast playlist |
| PF-POD-04 | Naming | Podcast title = show name, no extra words (not even "podcast" unless part of the name); detailed description; episode title = episode name (+ optional show name) | https://support.google.com/youtube/answer/12950577 | 2026-10-11 (R) | Episode title leads with the promise (`02` §4) |
| PF-POD-05 | New episodes feed | Always add the newest full episode to the podcast playlist, otherwise followers miss it in YouTube Music "new episodes" | https://services.google.com/fh/files/misc/podcasting_on_youtube_two_pager.pdf | 2026-10-11 (S) | G3 publish checklist |
| PF-POD-06 | Channel split rule | Keep the podcast with the main channel if audiences overlap; separate outlet if they don't | same | 2026-10-11 (S) | A show and a host's personal channel = separate channels when the value propositions differ |
| PF-POD-07 | RSS ingestion | For audio-first shows, select countries, static show-art video, appears only on YouTube + YouTube Music | https://support.google.com/youtube/answer/13525207 | 2026-10-11 (S) | Not for video podcasts (they have real video) |
| PF-POD-08 | Official podcast best practices | Unique 16:9 thumbnail per episode, expressive faces, 3–5 bold words, consistent fonts/colours/logo placement; avoid "Show Ep. 54 – Name" titles; **chapters for episodes > 20 min**; blog-style keyword descriptions; cut ~60 s moments into Shorts; Posts between episodes; reply to comments in the first hours, pin standouts; **Premieres** with countdown + chat | https://blog.youtube/creator-and-artist-stories/the-definitive-guide-to-creating-engaging-podcast-content/ (2025-10-08) | 2026-10-11 (S) | Per-episode baseline checklist (`02` §9) |
| PF-POD-09 | Scale (self-reported) | 1B+ monthly podcast viewers (Jan 2025); 700M+ hours of podcasts on living-room TVs in Oct 2025 vs 400M a year earlier | https://blog.youtube/news-and-events/1-billion-monthly-podcast-users/ ; https://blog.youtube/news-and-events/podcasts-living-room-in-2025/ | 2026-10-11 (S) | `[official]` but unaudited; context, never a forecast |

## 9. Community and distribution features

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-COLLAB-01 | Collaborations limit | Up to **10** collaborators per video (resolves the older "5" on the launch post/creators page) | https://support.google.com/youtube/answer/16554898 | 2026-10-11 (R) | Invite every guest with a channel |
| PF-COLLAB-02 | Eligible formats | Long-form and Shorts; archived lives yes; active lives no | same | 2026-10-11 (R) | Episode + 1–2 Shorts per guest |
| PF-COLLAB-03 | Revenue / reach | The posting channel receives the earned revenue (no split); YouTube aims to recommend to all collaborators' audiences; effects may not show at first | same | 2026-10-11 (R) | Post on the show's channel, invite the guest (and a host's personal channel where relevant) |
| PF-HYPE-01 | Hype eligibility | YPP channels with **500–500,000** subscribers; **Italy eligible**; access lost above the range or on leaving YPP | https://support.google.com/youtube/answer/15509925 | 2026-10-11 (R) | Not available to a channel until it joins YPP |
| PF-HYPE-02 | Hype window | Viewers can hype for the **first 7 days** after publish; "Hyped" badge 7 days; weekly country leaderboard ranked by hype from that country's viewers; free hypes limited (number not published) | same | 2026-10-11 (R) | Launch-week ritual once eligible (`02` §9) |
| PF-HYPE-03 | Hype exclusions | Shorts; unlisted/private; made-for-kids; age-restricted; misleading/clickbait; copyright-claimed; YouTube Giving fundraisers; lives/premieres while live (eligible after they end) | same | 2026-10-11 (R) | — |
| PF-POSTS-01 | Posts (ex Community tab) | Polls, quizzes, images, GIFs, text, video; shown on channel, Home and Subscriptions; image posts can appear in the Shorts feed; scheduled and expiring posts | https://support.google.com/youtube/answer/9409631 | 2026-10-11 (S) | Guest-question collection, polls |
| PF-COMM-01 | Communities | Fan-started discussion spaces on a channel; rolled out to eligible creators from 2025-06-17; moderation incl. "Hold all" | https://ppc.land/youtube-expands-communities-feature-to-all-eligible-creators/ (secondary); https://www.youtube.com/creators/grow/engage-your-community/ | 2026-10-11 (S) | Check eligibility in Studio before planning rituals on it |
| PF-LIVE-01 | Dual stream | Live Control Room can stream 16:9 and 9:16 simultaneously; vertical lives appear in the Shorts feed | https://blog.youtube/creator-and-artist-stories/youtube-related-videos-traffic-guide/ | 2026-10-11 (S) | Live events (e.g. a demo day) |
| PF-UPLOAD-01 | Re-upload rule | Don't delete and re-upload underperformers (can look like spam); make a new improved version. Untick "notify subscribers" only for bulk uploads (e.g. back-catalogue) | https://blog.youtube/culture-and-trends/renes-top-five-on-youtube-april-18-2024-edition/ | 2026-10-11 (S) | Never re-upload old episodes; fix packaging instead |

## 10. Multilingual: auto-dubbing, multi-language audio, captions

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-DUB-01 | Auto-dubbing default | Enabled **by default for eligible creators**; can be turned on/off any time. The Help page does not state a YPP requirement | https://support.google.com/youtube/answer/15569972 | 2026-10-11 (R) | Italian episodes of small channels were observed with the "Doppiaggio automatico" badge `[observed 2026-10-11]`: check it in Studio |
| PF-DUB-02 | Italian pairs | Italian original → **English only**; English original → Italian. Both with expressive speech (not always applied) | same | 2026-10-11 (R) | IT→EN reach upside; EN channels also reach Italian viewers dubbed |
| PF-DUB-03 | Limits | Videos **> 120 min** ineligible; review via "Publish manually" (Studio app setting); preview/publish/delete dubs on desktop Studio; lip sync is an experimental early-access option | same | 2026-10-11 (R) | Recommend "Publish manually" so dubs are checked for guest names |
| PF-DUB-04 | Multi-language audio | Upload own dub tracks (and per-language thumbnails on long-form); gradual access, subset of creators with advanced features | https://support.google.com/youtube/answer/13338784 | 2026-10-11 (S) | Later-stage |
| PF-CAP-01 | Caption formats | Basic: **SRT** (plain UTF-8, no style), SBV/SUB, MPsub, LRC, CAP. Advanced: SAMI/RealText (simple markup, no positioning), **WebVTT** (positioning; bold/italic/underline only), TTML/DFXP (styling + positioning, partial), iTT. Broadcast: SCC, EBU-STL and others | https://support.google.com/youtube/answer/2734698 | 2026-10-11 (R) | Deliver `<slug>.it.srt` (UTF-8) + `<slug>.it.vtt` |
| PF-CAP-02 | Caption upload via API | `captions.insert` costs 400 units and needs `youtube.force-ssl` (write scope) | https://developers.google.com/youtube/v3/determine_quota_cost | 2026-10-11 (R) | **Never** via API (no write scopes): the operator uploads in Studio |

## 11. Monetization eligibility (context for Hype, end-screen links, Memberships)

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-YPP-01 | Full YPP | **1,000 subscribers** + either **4,000 public long-form watch hours (12 months)** or **10M public Shorts views (90 days)**. Shorts-feed hours don't count toward 4,000; unlisted/private/deleted don't count | https://support.google.com/youtube/answer/72851 | 2026-10-11 (R) | A small channel far from YPP: don't plan around YPP features |
| PF-YPP-02 | Inactivity | Monetization may be turned off after **6 months or more** without uploads or Posts | same | 2026-10-11 (R) | Once in YPP: never let a channel go 6 months dark |
| PF-YPP-03 | Terms update | Updated YPP terms effective **2027-02-01**; accept in Studio by **2027-01-31** to keep full monetization | same | 2026-10-11 (R) | Reminder for monetized client channels |
| PF-YPP-04 | Lower 500-sub tier | **Not on the official page** (only secondary sources) | same | 2026-10-11 (R) | Do not state its thresholds (`10` DNE-21) |

## 12. YouTube Data API v3 (public data, API key)

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-API-01 | Default quota | **10,000 units/day** shared by all methods except the separate buckets; reset at **midnight Pacific** | https://developers.google.com/youtube/v3/determine_quota_cost (page updated 2026-10-08) | 2026-10-11 (R) | `yt-collect` budgets per run |
| PF-API-02 | Separate buckets | `search.list`: **100 calls/day**, 1 unit/call (since 2026-06-01). `videos.insert`: 100 calls/day. `videos.batchGetStats` (since 2026-06-03): 1 unit/call in **its own** bucket, default **10,000/day** | same; https://developers.google.com/youtube/v3/revision_history | 2026-10-11 (R) | Never inventory channels via search |
| PF-API-03 | Unit costs | `videos.list`, `channels.list`, `playlistItems.list`, `commentThreads.list` = **1**; `captions.list` = 50; `captions.insert` = 400; `thumbnails.set`, `videos.update` = 50; `captions.download` = 200 (own videos only, F6 B3) | same | 2026-10-11 (R; captions.download S) | Cost recipes below |
| PF-API-04 | Inventory recipe | `channels.list` → uploads playlist ID (`UU` + channel ID without `UC`) → `playlistItems.list` (50/page) → `videos.list` (50 IDs/call). A 500-video channel ≈ **21 units** | F6 B3; V3 §13 | 2026-10-11 (S) | `yt-collect --what inventory` |
| PF-API-05 | batchGetStats | 1 unit; no auth for public videos (auth needed for non-public); per-ID failures reported in `summary.failedVideoIds`. Max IDs/call not stated on the method page (F6 reported 50 from the revision note) | https://developers.google.com/youtube/v3/docs/videos/batchGetStats | 2026-10-11 (R) | Batch ≤ 50 IDs until confirmed otherwise |
| PF-API-06 | Stale numbers to ignore | Upload cost dropped ~1,600 → ~100 units on **2025-12-04** (page summaries may still say 1,600); third-party READMEs quoting "search = 100 units" are pre-June-2026 | revision history | 2026-10-11 (R) | — |
| PF-API-07 | No Shorts flag | Data API has no Shorts field; use yt-dlp `/shorts` tab membership or heuristic (≤ 180 s and vertical), labelled heuristic | F6 B3 | 2026-10-11 (S) | `videos.format` column |

## 13. YouTube Analytics API (owner OAuth, targeted queries)

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-YTA-01 | Core metrics | `views`, `engagedViews`, `estimatedMinutesWatched`, `averageViewDuration`, `averageViewPercentage`, `subscribersGained/Lost`, `likes`, `comments`, `shares` | https://developers.google.com/youtube/analytics/metrics | 2026-10-11 (R) | `analytics_28d` table |
| PF-YTA-02 | AVD/AVP exclusion | Since **2021-12-13** both exclude looping-clips traffic | same | 2026-10-11 (R) | — |
| PF-YTA-03 | `audienceWatchRatio` | Times a point was watched ÷ total views; **can exceed 1** (rewatches) | same | 2026-10-11 (R) | Values > 1 = spike, not an error |
| PF-YTA-04 | `relativeRetentionPerformance` | 0–1 vs YouTube videos of similar length; **0.5 = median**; 0 worse than all, 1 better than all | same | 2026-10-11 (R) | Shape comparison across episodes |
| PF-YTA-05 | Segment metrics | `startedWatching` (segment was first seen), `stoppedWatching` (last seen), `totalSegmentImpressions` (segment views incl. repeats) | same | 2026-10-11 (R) | Locate exits precisely |
| PF-YTA-06 | **No impressions/CTR** | The Analytics API has no thumbnail impressions or impressions CTR (only ad/annotation/card metrics) | same | 2026-10-11 (R) | CTR comes only from Reporting (PF-REP) or Studio |
| PF-YTA-07 | Retention granularity | `elapsedVideoTimeRatio` returns exactly **100 equally spaced points** (0.01–1.0) per video | https://developers.google.com/youtube/analytics/dimensions | 2026-10-11 (R) | See table below; on long episodes the API cannot see the hook |
| PF-YTA-08 | Retention query constraints | Requires a single `video==ID` filter; filterable by `audienceType` (ORGANIC, AD_INSTREAM, AD_INDISPLAY), `subscribedStatus`, `youtubeProduct` | same; F6 B4 | 2026-10-11 (R/S) | Subscribed vs not-subscribed curves |
| PF-YTA-09 | Content type split | `creatorContentType`: LIVE_STREAM, SHORTS, STORY, VIDEO_ON_DEMAND, UNSPECIFIED; data from 2019-01-01 | same | 2026-10-11 (R) | Separate Shorts from long-form in totals |
| PF-YTA-10 | Traffic sources | `insightTrafficSourceType` (22 values) incl. YT_SEARCH, RELATED_VIDEO (suggested), SUBSCRIBER (home + subscription feeds), SHORTS, PLAYLIST, YT_CHANNEL, EXT_URL, NOTIFICATION, END_SCREEN, HASHTAGS, NO_LINK_OTHER, YT_OTHER_PAGE. Detail needs a type filter, max 25 rows; queries error if videos × days > 50,000 | same; F6 B4 | 2026-10-11 (R/S) | `traffic_sources` table |
| PF-YTA-11 | Small-channel withholding | The retention report is withheld below a watch-time threshold on small videos `[vendor]` (yt-analytics-mcp README, not an official doc) | https://github.com/conorbronsdon/yt-analytics-mcp | 2026-10-11 (S) | Empty curve ≠ zero retention |
| PF-YTA-12 | Latency | Analytics data lags ~2–3 days `[vendor]`; retention data 1–2 days to process `[official]` (PF-RET-03) | vidIQ retention skill; Help 9314415 | 2026-10-11 (S) | T+48h pulse is a sanity check, not a verdict |

**API retention resolution (PF-YTA-07 applied: seconds per point = duration ÷ 100)**

| Video length | Seconds per API point | Can the API see the 0:30 hook? |
|---|---|---|
| 60 s Short | 0.6 s | yes |
| 10 min | 6 s | roughly (5 points) |
| 20 min | 12 s | barely (2–3 points) |
| 50 min (podcast episode) | 30 s | **no**: point 1 already spans 0:00–0:30 |
| 64 min | 38.6 s | no |

## 14. YouTube Reporting API (bulk daily CSVs; the only API source of CTR)

| ID | Fact | Value / rule | Source | Verified | Use |
|---|---|---|---|---|---|
| PF-REP-01 | Reach reports | `channel_reach_basic_a1` (dims date, channel_id, video_id) and `channel_reach_combined_a1` (+ traffic_source_type, traffic_source_detail, operating_system, device_type); metrics `video_thumbnail_impressions`, `video_thumbnail_impressions_ctr` | https://developers.google.com/youtube/reporting/v1/reports/channel_reports | 2026-10-11 (R) | `reach_daily` table |
| PF-REP-02 | Basic activity report | Current ID is **`channel_basic_a3`** (dims incl. `subscribed_status`, `country_code`; metrics incl. `engaged_views`, `views`, `watch_time_minutes`, `average_view_duration_seconds`, `average_view_duration_percentage`, `subscribers_gained/lost`) | same | 2026-10-11 (R) | Confirm with `reportTypes.list` in `yt-reporting-setup` |
| PF-REP-03 | Backfill | A new job generates reports for the **30 days before** job creation; days older than that are never available | https://developers.google.com/youtube/reporting/v1/reports | 2026-10-11 (R) | **Create jobs on day 1** (`yt-reporting-setup --channel X`) |
| PF-REP-04 | First availability | Retrieve within **48 h** of job creation; each daily report ready ~2 days after the day it covers; historical data "within a couple of days" | same | 2026-10-11 (R) | — |
| PF-REP-05 | Retention of reports | Regular reports downloadable **60 days**; historical (backfill) reports **30 days** | same | 2026-10-11 (R) | Collector must run at least every **25 days** (safety margin); weekly by default |
| PF-REP-06 | Time zone | Each daily report covers 00:00–23:59 **PST (UTC−8)** | same | 2026-10-11 (R) | Dates in `reach_daily` are Pacific days, not Italian days |
| PF-REP-07 | Backfill replaces data | A backfill report has a new ID but the same start/end time: replace stored rows; if two reports share start/end, keep the newer `createTime`; track `createTime` and pass `createdAfter` | same | 2026-10-11 (R) | Upsert logic in `yt-collect --what reporting` |
| PF-OAUTH-01 | Testing-mode tokens | External apps in **Testing** status get refresh tokens that expire after **7 days** | https://developers.google.com/identity/protocols/oauth2 | 2026-10-11 (S) | Consent screen "In production" (`yt-auth`) |
| PF-OAUTH-02 | Scopes used | `yt-analytics.readonly` + `youtube.readonly` only. Never `youtube`, `youtube.upload`, `youtube.force-ssl` | design doc §2 decision 9; https://developers.google.com/youtube/analytics | 2026-10-11 (S) | Read-only by construction |

## 15. Developer policies that bind the collector

| ID | Rule | Source | Verified | Consequence |
|---|---|---|---|---|
| PF-POL-01 | Non-authorized API data (other channels' public stats) may be stored **≤ 30 days**, then deleted or refreshed (III.E.4) | https://developers.google.com/youtube/terms/developer-policies | 2026-10-11 (S) | `peer_videos` purge at 30 days |
| PF-POL-02 | Own Analytics/Reporting data may be kept as long as needed if authorization is re-checked every 30 days | same | 2026-10-11 (S) | Own history kept in `yt.db` indefinitely |
| PF-POL-03 | No scraping, and no scraped YouTube data, inside an API client (III.E.6, III.I.14) | same | 2026-10-11 (S) | yt-dlp research path stays logically separate from API tables |
| PF-POL-04 | One project per client; no masking usage; no key rotation (III.D.1) | same | 2026-10-11 (S) | One Google Cloud project per channel owner or team; ask for a quota extension if ever needed |
| PF-POL-05 | Don't present derived metrics as YouTube's numbers (III.E.4.h) | same | 2026-10-11 (S) | Outlier scores are labelled "metrica derivata" |

## 16. Upload and delivery specs

**YouTube recommended upload encoding** — https://support.google.com/youtube/answer/1722171 — verified 2026-10-11 (R)

| Item | Recommendation |
|---|---|
| Container | MP4, no edit lists, moov atom at the front (`-movflags +faststart`) |
| Audio | AAC-LC (or Opus, Eclipsa), stereo or stereo + 5.1, **48 kHz**; 128 kbps mono / **384 kbps stereo** / 512 kbps 5.1 |
| Video | H.264, progressive, High profile, CABAC, 4:2:0, 2 consecutive B-frames, **closed GOP = half the frame rate**, VBR |
| Frame rate | Same as recorded (24/25/30/48/50/60); deinterlace first |
| SDR bitrate 24–30 fps | 2160p **35–45 Mbps** · 1440p 16 · 1080p 8 |
| SDR bitrate 48–60 fps | 2160p 53–68 Mbps · 1440p 24 · 1080p 12 |
| Colour (SDR) | BT.709 primaries, transfer and matrix; YouTube converts BT.2020 to 8-bit BT.709 and full range to limited |
| Accepted codecs | HEVC, ProRes, DNxHR and others are accepted (F2 §11.4); H.264 is the recommended one |

**Spotify video podcast specs** — https://support.spotify.com/us/creators/article/video-specs/ — verified 2026-10-11 (R)

| Item | Recommendation |
|---|---|
| File / duration | < 10 GB recommended (60 GB max); < 4 h recommended (12 h max) |
| Container / tracks | MP4 (MOV accepted); exactly one video + one audio track of equal duration; no edit lists |
| Video | H.264 or HEVC; 1080p or higher; 16:9; **25 Mbit/s CBR (1080p) or 35 Mbit/s CBR (4K)**; 24/25/30/50/60 fps progressive; keyframe ~1/s (≤ 60 s required); first frame within 50 ms of t=0 |
| Colour | Rec.709 SDR recommended (Rec.2020/HDR converted); 8- or 10-bit |
| Audio | AAC-LC, PCM or FLAC; ≥ 128 kbps; stereo (mono upmixed, 5.1 downmixed) |
| Thumbnail | 16:9, ideally 1920×1080 (https://support.spotify.com/us/creators/article/thumbnails/, verified 2026-10-11 (S)) |

## 17. Loudness (official vs community)

| ID | Platform | Target | Status | Source | Verified |
|---|---|---|---|---|---|
| PF-LOUD-01 | YouTube | **No published LUFS target.** Community measurements: YouTube turns louder uploads down toward about **−14 LUFS** and does not boost quieter ones; "Stats for nerds → content loudness" shows the offset | `[anecdotal]` (community-observed) | https://youlean.co/?p=30813 ; productionadvice.co.uk "stats for nerds" (F2 §4.1) | 2026-10-11 (S) |
| PF-LOUD-02 | Apple Podcasts (RSS audio) | **−16 LKFS ±1 dB**, true peak ≤ **−1 dBFS**, measured per **ITU-R BS.1770-5**; apply loudness before encoding | `[official]` | https://podcasters.apple.com/support/893-audio-requirements | 2026-10-11 (R) |
| PF-LOUD-03 | Spotify video podcasts | No official LUFS figure found | — | https://support.spotify.com/us/creators/article/video-specs/ | 2026-10-11 (R) |
| PF-LOUD-04 | **House targets** (decision, not a platform fact) | Video masters (YouTube, Spotify video): **−14 LUFS integrated, TP ≤ −1.5 dBTP, LRA ≤ 11 LU**, tolerance ±0.5 LU. Audio-only RSS master: −16 LUFS, TP ≤ −1 dBTP | house rule | SYNTHESIS §1.2; `05-editing-rules.md` | 2026-10-11 |

## 18. Spotify Partner Program (for shows that also publish there)

| ID | Fact | Value / rule | Source | Verified |
|---|---|---|---|---|
| PF-SPP-01 | Italy | Eligible from **2026-10-20** (with Spain, Poland, Malta, Andorra, San Marino and others); the newsroom lists 37 new markets | https://support.spotify.com/ie/creators/article/spotify-partner-program/ ; https://newsroom.spotify.com/?p=42323 | 2026-10-11 (R) |
| PF-SPP-02 | Thresholds | Legal address in an eligible market; **≥ 3 episodes**; **≥ 2,000 consumption hours** and **≥ 1,000 audience** on Spotify, both in the last 30 days; hosted on Spotify for Creators | same | 2026-10-11 (R) |
| PF-SPP-03 | Video ad break | Video episodes need **≥ 1 ad break** to earn Premium video revenue; ad revenue also needs ≥ 1 ad break | same | 2026-10-11 (R) |
| PF-SPP-04 | Payout basics | 50% of Spotify-monetized ad revenue; Premium video revenue by proprietary formula; a stream counts at ≥ 60 s; stay active: publish an episode and earn ≥ $10 in any 6-month period | same | 2026-10-11 (R) |

## 19. Studio tools and announced features (availability in Italy unconfirmed unless stated)

| ID | Feature | Status | Source | Verified | Agent stance |
|---|---|---|---|---|---|
| PF-STUDIO-01 | Draft feedback (AI review of private/unlisted drafts: pacing, structure, storytelling) | Announced 2026-09-23 | https://blog.youtube/news-and-events/made-on-youtube-new-tools-power-creation-journey/ ; https://techcrunch.com/?p=3167584 | 2026-10-11 (S) | Optional pre-publish second opinion; check availability in Studio |
| PF-STUDIO-02 | Dynamic thumbnails (up to 3, shown to different audience segments) | Announced 2026-09-23; who generates the options is reported inconsistently | same | 2026-10-11 (S) | Prepare a coherent set of 3 (returning-viewer / new-viewer / outcome framing) |
| PF-STUDIO-03 | A/B test of up to 3 video cuts (hook test) | "Coming soon"; a secondary source says select creators in 2027 | same | 2026-10-11 (S) | `youtube:hook` always delivers 3 cold opens |
| PF-STUDIO-04 | Research & Insights destinations (outlier multipliers, "watched by my viewers") | Limited test with a small number of users (2026-08-05) | https://www.tubefilter.com/2026/08/05/youtube-research-tab-outlier-multipliers-viewer-comparison-data/ | 2026-10-11 (S) | Store our outliers in the same unit (multiple vs channel norm) |
| PF-STUDIO-05 | Ask Studio | Desktop + mobile apps; comment summaries, analytics explanations, script feedback; not for < 18, made-for-kids; conversations kept 30 days and may be human-reviewed; can review draft/private/unlisted | https://support.google.com/youtube/answer/16291691 | 2026-10-11 (S) | Never paste guest-confidential material into it |
| PF-STUDIO-06 | Inspiration tab | English-only; deprecated from Aug 2026 in favour of Ask Studio | https://support.google.com/youtube/answer/15575509 | 2026-10-11 (S) | Don't build on it |
| PF-STUDIO-07 | Studio Research tab (search insights) | Last-28-day searches, volume labels, "content gap" labels; browser-only, no API | https://support.google.com/youtube/answer/11962757 (via Search Engine Land) | 2026-10-11 (S) | Read-only via Claude in Chrome when the operator is logged in |

## 20. Italian regulatory threshold worth knowing

| ID | Fact | Source | Verified | Use |
|---|---|---|---|---|
| PF-IT-01 | AGCOM "influencer rilevanti": registration above **500K followers** or **1M average monthly views** on a platform; code of conduct; fines up to €600K | https://www.agcom.it/sites/default/files/media/allegato/2026/Allegato%20A%20-%20Quadro%20normativo%20e%20profili%20procedurali%20-%20Influencer.pdf | 2026-10-11 (S) | Not relevant to small channels; re-check for larger channels and client channels near the threshold |

---

## 21. Re-verification protocol

1. Quarterly (next: **2027-01-11**) re-fetch every **(R)** row's source URL with WebFetch and diff the values. Re-fetch **(S)** rows that a skill relied on in the last quarter.
2. When a value changed: update the row, set the new verified date, and add a line to the changelog below. If the change breaks a skill rule (e.g. a new A/B limit), flag it in the next `youtube:review` monthly note.
3. When a page 404s or contradicts a secondary source: keep the last verified value, mark it `(stale?)`, and add an open item to `10-evidence-ledger.md` §7.
4. Never "upgrade" a secondary-sourced row to official without fetching the official page.

## 22. Changelog

| Date | Change |
|---|---|
| 2026-10-11 | File created from F1/F3/F4/F6/V1/V3/SYNTHESIS; 25 source pages re-fetched (R). Resolved: Collaborations = 10; reach + basic report IDs (`channel_basic_a3`); auto-dub page no longer mentions YPP; batchGetStats max IDs not stated on method page |
