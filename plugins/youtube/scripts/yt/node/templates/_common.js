// _common.js — pezzi condivisi del telaio di serie v2 (duo, ritratto, scena, prova), caricato con
// <script src="_common.js">. Usa il runtime TT iniettato da node/render_html.mjs. Tutto ciò che è «brand» arriva dai token
// (TT.tokens = <brand>/tokens.json, default il brand demo del plugin) o dal concept: palette (ink, paper, accenti),
// font (headline condensato, display, body), wordmark (logo + testo), etichette. Nessun colore o testo fisso di un canale.
//
// Token letti (tutti facoltativi, con ripieghi neutri):
//   colors.ink, colors.paper            inchiostro (campo scuro, testo su accento) e carta (titolo, testo su campo scuro)
//   colors.<accento>, accents [nomi]    accenti ammessi (uno solo per composizione); accent = quello di default
//   fonts.headline.family               font del titolo enorme (default Anton: condensato, misure calibrate su Anton)
//   fonts.display.family                font del wordmark e di hook_font: "display"
//   fonts.body.family                   font di ruolo, riga meta, etichette (default Inter)
//   wordmark {text, font: display|body} testo del wordmark (default tokens.name)
//   logo {mark, mark_on_dark}           file del simbolo relativi alla cartella del brand (TT.asset); senza, solo testo
//
// Grana sotto le persone e a media neutra (il fondo resta il token), ritagli di yt-portrait disegnati 1:1, bordi dritti dei
// ritagli a filo del canvas, controlli su dischi e grafica (metrics.series, letti da yt-thumb-render).
window.KIT = (() => {
  const TK = (window.TT && TT.tokens) || {};
  const C = Object.assign({ ink: '#15171c', paper: '#f4f1ea' }, TK.colors || {});
  const NEUTRAL = ['ink', 'paper', 'bg', 'fg', 'muted', 'rule', 'line', 'border', 'surface'];
  let ACCENTS = (Array.isArray(TK.accents) ? TK.accents : []).filter((n) => C[n]);
  if (!ACCENTS.length && TK.accent && C[TK.accent]) ACCENTS = [TK.accent];
  if (!ACCENTS.length) ACCENTS = Object.keys(C).filter((n) => !NEUTRAL.includes(n));
  if (!ACCENTS.length) { C.accent = '#ff5a2c'; ACCENTS = ['accent']; }
  const DEFAULT_ACCENT = ACCENTS.includes(TK.accent) ? TK.accent : ACCENTS[0];
  const F = TK.fonts || {};
  const HEAD = (F.headline && F.headline.family) || 'Anton';
  const DISPLAY = (F.display && F.display.family) || HEAD;
  const BODY = (F.body && F.body.family) || 'Inter';
  const WM = TK.wordmark || {};
  const WM_TEXT = WM.text != null ? String(WM.text) : (TK.name ? String(TK.name) : '');
  const WM_FONT = WM.font === 'body' ? BODY : DISPLAY;
  const LOGO = TK.logo || {};

  const hexRgb = (hex) => { const h = String(hex).replace('#', ''); const v = h.length === 3 ? h.split('').map((x) => x + x).join('') : h;
    return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16)); };
  const rgba = (hex, a) => `rgba(${hexRgb(hex).join(',')},${a})`;
  const esc = (s) => String(s).replace(/[<>&"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
  // tinta HSL (gradi) e saturazione di un colore
  const hueSat = (hex) => {
    const [r, g, b] = hexRgb(hex).map((v) => v / 255);
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn, l = (mx + mn) / 2;
    if (!d) return { h: 0, s: 0, l };
    const s = d / (1 - Math.abs(2 * l - 1));
    let h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return { h: (h * 60 + 360) % 360, s, l };
  };
  // Colore nella famiglia dei toni della pelle (rossi e aranci saturi): mai come disco dietro un volto (la testa si fonde).
  const skinLike = (hex) => { const q = hueSat(hex); return q.s > 0.35 && q.l > 0.25 && q.l < 0.8 && (q.h <= 40 || q.h >= 345); };

  // Grana a media neutra: rumore grigio (luma ~0.5) in overlay → il colore medio del fondo resta il token.
  const NOISE = `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'>` +
    `<feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/>` +
    `<feColorMatrix values='.33 .33 .33 0 0  .33 .33 .33 0 0  .33 .33 .33 0 0  0 0 0 0 1'/></filter>` +
    `<rect width='180' height='180' filter='url(%23n)'/></svg>")`;
  function grain(parent, { opacity = 0.10 } = {}) {
    const g = TT.el('div', 'tt-grain', parent);
    Object.assign(g.style, { position: 'absolute', inset: '0', opacity, mixBlendMode: 'overlay', pointerEvents: 'none',
      backgroundImage: NOISE, zIndex: 2 });   // sotto le persone (z ≥ 10): i pixel della persona restano quelli veri
    return g;
  }

  const R = { template: '', decos: [], heroes: [], logos: [], notes: [] };
  const lum = (hex) => TT.lum(hex);
  const contrast = (a, b) => TT.contrast(a, b);

  async function img(parent, src, cls = 'hero') {
    const i = TT.el('img', cls, parent); i.src = src; await i.decode(); return i;
  }

  // Soggetto. Ritaglio di yt-portrait (hero.portrait): disegnato 1:1 (1 px del PNG = 1 px del 3840×2160) se non
  // si chiede altro; ritaglio a scala di sorgente: upscale (vs master 4K) o faceFrac. Poi: griglia dei px del
  // dispositivo e bordi dritti (hero.touches) portati a filo del canvas (07 §11), al massimo maxShift px.
  function place(i, hero, { upscale, faceFrac, cx, faceTop, bleedBottom = true, maxShift = 0.14, redraw = false } = {}) {
    const T = TT;
    const p = hero.portrait || null;
    const facePxCut = hero.face[3] * (hero.h || i.naturalHeight);
    let faceH, mode;
    if (p && !redraw && !upscale) { faceH = facePxCut / 3; mode = '1:1'; }
    else if (upscale) { faceH = (p ? upscale / p.scale : upscale) * facePxCut / 3; mode = 'upscale'; }
    else { faceH = (faceFrac || 0.25) * T.H; mode = 'face_frac'; }
    const rec = T.placeHero(i, hero, { faceH, cx, faceTop, bleedBottom });
    const t = hero.touches || {};
    let dx = 0, dy = 0;
    const fails = [];
    if (t.right && rec.left + rec.dw < T.W + 1) dx = T.W + 1 - (rec.left + rec.dw);
    if (t.left && rec.left > -1) dx = -1 - rec.left;
    if (t.top && rec.top > -1) dy = -1 - rec.top;
    const ab = hero.alpha_box || [0, 0, 1, 1];
    const bottom = rec.top + (ab[1] + ab[3]) * rec.dh;
    if (t.bottom && bottom < T.H + 1 && !rec.el.style.maskImage) dy = Math.max(dy, T.H + 1 - bottom);
    if (Math.abs(dx) > maxShift * T.W) { fails.push(`bordo dritto ${dx > 0 ? 'destro' : 'sinistro'}: servirebbero ${Math.abs(dx).toFixed(0)} px`); dx = 0; }
    if (Math.abs(dy) > maxShift * T.H) { fails.push(`bordo dritto ${dy > 0 ? 'basso' : 'alto'}: servirebbero ${Math.abs(dy).toFixed(0)} px`); dy = 0; }
    rec.left = Math.round((rec.left + dx) * 3) / 3;
    rec.top = Math.round((rec.top + dy) * 3) / 3;
    rec.el.style.left = rec.left + 'px'; rec.el.style.top = rec.top + 'px';
    const f = hero.face;
    rec.faceRect = { x: rec.left + f[0] * rec.dw, y: rec.top + f[1] * rec.dh, w: f[2] * rec.dw, h: f[3] * rec.dh };
    const drawScale = rec.s * 3;                        // px del dispositivo per px del PNG
    const up = p ? p.scale * drawScale : drawScale;     // vs la sorgente (ritagli non portrait: PNG = px del master)
    rec.upscale = up;
    R.heroes.push({ src: hero.path, mode, draw_scale: +drawScale.toFixed(4), upscale_vs_source: +up.toFixed(3),
      portrait: !!p, touches: t, flush_shift: [+dx.toFixed(1), +dy.toFixed(1)], flush_fail: fails,
      face_frac: +(rec.faceRect.h / T.H).toFixed(4), rect: [rec.left, rec.top, rec.dw, rec.dh].map((v) => +v.toFixed(2)) });
    return rec;
  }

  // Testa: sommità della sagoma (profilo a 64 fasce).
  function headTop(r) {
    const p = r.profile; if (!p || !p.left) return r.faceRect.y - r.faceRect.h * 0.6;
    const i = p.left.findIndex((v) => v >= 0);
    return r.top + (Math.max(0, i) / p.left.length) * r.dh;
  }

  // Gancio accanto al soggetto: prova fasce verticali e tiene quella col corpo più grande.
  function fitBeside(hook, recs, { side = 'right', x0 = 64, yMin = 120, yMax = 610, gap = 40, maxW = 760, min = 60, max = 210,
                                   maxLines = 3, center = 0.5, bands = [240, 300, 360, 430, 490], circles = [] } = {}) {
    const T = TT;
    const availW = (y0, y1) => {
      let lim = side === 'right' ? T.W - 64 : 64;
      for (const r of recs) {
        const s = T.silhouette(r, y0, y1);
        lim = side === 'right' ? Math.min(lim, s.left - gap) : Math.max(lim, s.right + gap);
      }
      for (const c of circles) {
        const dy = (y0 <= c.cy && c.cy <= y1) ? 0 : Math.min(Math.abs(y0 - c.cy), Math.abs(y1 - c.cy));
        if (dy >= c.r) continue;
        const dx = Math.sqrt(c.r * c.r - dy * dy);
        lim = side === 'right' ? Math.min(lim, c.cx - dx - gap) : Math.max(lim, c.cx + dx + gap);
      }
      return side === 'right' ? Math.min(maxW, lim - x0) : Math.min(maxW, T.W - x0 - lim);
    };
    let best = null;
    for (const H of bands) {
      for (let y0 = yMin; y0 + H <= yMax; y0 += 15) {
        const w = Math.max(200, availW(y0, y0 + H));
        const r = T.fit(hook, { maxW: w, maxH: H, min, max, maxLines });
        const h = hook.getBoundingClientRect().height;
        const yc = y0 + (H - h) / 2;
        const score = r.size - Math.abs((yc + h / 2) - T.H * center) * 0.02;
        if (!best || score > best.score) best = { score, w, H, y0, size: r.size };
      }
    }
    T.fit(hook, { maxW: best.w, maxH: best.H, min, max, maxLines });
    const h = hook.getBoundingClientRect().height;
    hook.style.top = (best.y0 + (best.H - h) / 2) + 'px';
    if (side === 'right') hook.style.left = x0 + 'px';
    else { hook.style.left = (T.W - x0 - best.w) + 'px'; hook.style.textAlign = 'right'; }
    return best;
  }

  const inRect = (x, y, r) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;

  // Cerchio (raggio r, spessore sw, centro cx,cy): punti nelle zone vietate, profondità del taglio ai bordi.
  function checkCircle(kind, cx, cy, r, sw, { minClear = 24, minCropFrac = 0.15 } = {}) {
    const T = TT;
    const outer = r + sw / 2, d = 2 * outer;
    let nogo = 0, tr = 0;
    for (let k = 0; k < 720; k++) {
      const a = (k / 720) * 2 * Math.PI;
      for (const rr of [r - sw / 2, r, r + sw / 2]) {
        const x = cx + rr * Math.cos(a), y = cy + rr * Math.sin(a);
        if (x < 0 || y < 0 || x > T.W || y > T.H) continue;
        if (inRect(x, y, T.zones.nogo)) nogo++;
        if (inRect(x, y, T.zones.topRight)) tr++;
      }
    }
    const edges = { top: cy - outer, left: cx - outer, right: T.W - (cx + outer), bottom: T.H - (cy + outer) };
    const bad = [];
    for (const [side, gapPx] of Object.entries(edges)) {
      if (gapPx >= minClear) continue;                    // aria sufficiente
      if (gapPx <= -minCropFrac * d) continue;            // taglio deciso
      bad.push(`${side}: ${gapPx >= 0 ? 'aria ' + gapPx.toFixed(0) + ' px (< ' + minClear + ')' : 'taglio ' + (-gapPx / d * 100).toFixed(0) + '% del diametro (< ' + minCropFrac * 100 + '%)'}`);
    }
    R.decos.push({ kind, shape: 'ring', cx: +cx.toFixed(1), cy: +cy.toFixed(1), r: +r.toFixed(1), stroke: +sw.toFixed(1),
      nogo_points: nogo, top_right_points: tr, edge_gaps: Object.fromEntries(Object.entries(edges).map(([k, v]) => [k, +v.toFixed(1)])), edge_bad: bad });
  }

  // Poligono (freccia, coda di un fumetto…): campionato su griglia, intersezioni con volti e zone vietate.
  function checkPolygon(kind, pts, faces) {
    const T = TT;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const inside = (x, y) => {   // ray casting
      let c = false;
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        const [xi, yi] = pts[i], [xj, yj] = pts[j];
        if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
      }
      return c;
    };
    let face = 0, nogo = 0, tr = 0;
    for (let x = Math.min(...xs); x <= Math.max(...xs); x += 1) {
      for (let y = Math.min(...ys); y <= Math.max(...ys); y += 1) {
        if (!inside(x, y)) continue;
        for (const f of faces) if (inRect(x, y, f)) face++;
        if (inRect(x, y, T.zones.nogo)) nogo++;
        if (inRect(x, y, T.zones.topRight)) tr++;
      }
    }
    R.decos.push({ kind, shape: 'polygon', points: pts.map((p) => p.map((v) => +v.toFixed(1))), face_px: face, nogo_px: nogo, top_right_px: tr });
  }

  function checkRect(kind, r, faces, { faceOk = false } = {}) {
    const T = TT;
    const inter = (a, b) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    R.decos.push({ kind, shape: 'rect', rect: [r.x, r.y, r.w, r.h].map((v) => +v.toFixed(1)), nogo_px: +inter(r, T.zones.nogo).toFixed(0),
      top_right_px: +inter(r, T.zones.topRight).toFixed(0), face_px: faceOk ? 0 : +faces.reduce((s, f) => s + inter(r, f), 0).toFixed(0) });
  }

  // Da chiamare alla fine del builder: aggiunge il rapporto del telaio alle metriche lette da yt-thumb-render (metrics.series).
  function finish(template, extra = {}) {
    R.template = template;
    Object.assign(R, extra);
    const orig = TT.metrics;
    TT.metrics = () => { const m = orig(); m.series = R; return m; };
  }

  // ══ Telaio v2 ═══════════════════════════════════════════════════════════════════════════════════════════════════
  // Comune a duo / ritratto / scena / prova: titolo enorme in un font condensato (Anton di default, solo thumbnail) con
  // il punto finale nel colore d'accento, parola chiave evidenziata, targhetta nome + ruolo, riga meta in maiuscoletto
  // (EVENTO / ANNO), wordmark o simbolo del brand in alto a sinistra (niente numero di episodio di default), etichetta di
  // formato in alto a destra fuori dalla zona hover. Un solo accento per composizione (R.accents).
  // Effetti della policy v2: tutto SOTTO il ritaglio (classe tt-under); il ritaglio non ha filtri che toccano i pixel
  // opachi. yt-thumb-render confronta il render con e senza gli strati tt-under (face_pixels_unchanged).
  R.accents = [];
  R.credentials = [];
  R.under = [];
  function accentName(name, fallback = DEFAULT_ACCENT) { return ACCENTS.includes(name) ? name : fallback; }
  function useAccent(name) { if (name && !R.accents.includes(name)) R.accents.push(name); return C[name] || name; }
  // Box del nome: l'accento se l'inchiostro ci sta sopra con contrasto ≥ 7:1 (anche a corpo piccolo), altrimenti carta.
  function plateBox(accent) { return C[accent] && contrast(C.ink, C[accent]) >= 7 ? accent : 'paper'; }

  // Ritaglio v2: dimensione dal volto voluto, limitata dal tetto al display (≤ cap × risoluzione effettiva del volto
  // misurata a 1280 px; cap da yt-thumb-render, 2.0 o 1.5). Il volto non supera mai il tetto senza un motivo scritto.
  function capFrac(hero, want, spec) {
    const p = hero.portrait || {};
    const cap = (spec && spec.display_cap) || 2.0;
    if (!p.eff_face_px) return { frac: want, capped: false, max: null };
    const max = (p.eff_face_px * cap) / TT.H;                // altezza del volto in px CSS (= px a 1280) / 720
    const over = spec && (spec.upscale_override || spec.face_cap_override);
    if (want > max + 1e-4 && !over) { R.notes.push(`volto limitato dal tetto al display: ${(max * 100).toFixed(1)}% (voluto ${(want * 100).toFixed(0)}%)`); return { frac: max, capped: true, max }; }
    return { frac: want, capped: false, max };
  }

  // Volto che il template userà: con un ritaglio yt-portrait e senza face_frac nel concept vale la misura del ritaglio
  // (disegnato 1:1, nessun secondo ricampionamento), se sta nell'intervallo del template; altrimenti il default.
  function wantFrac(hero, spec, def, [lo, hi] = [0, 1]) {
    if (spec && spec.face_frac) return { frac: spec.face_frac, oneToOne: false };
    if (hero.portrait && hero.face) {
      const f1 = (hero.face[3] * (hero.h || 0)) / (3 * TT.H);
      if (f1 >= lo - 1e-4 && f1 <= hi + 1e-4) return { frac: f1, oneToOne: true };
      return { frac: Math.min(hi, Math.max(lo, f1)), oneToOne: false };
    }
    return { frac: def, oneToOne: false };
  }

  async function person(parent, hero, spec, { faceFrac, cx, faceTop, cls = 'hero', z = 10, maxShift = 0.14, oneToOne = false } = {}) {
    const i = await img(parent, hero.tone_src || hero.src, cls);
    i.style.zIndex = z;
    if (hero.tone_src) i.dataset.rawSrc = hero.src;
    const c = capFrac(hero, faceFrac, spec);
    const rec = place(i, hero, { faceFrac: c.frac, redraw: !(oneToOne && !c.capped), cx, faceTop, maxShift });
    rec.hero = hero; rec.capped = c.capped; rec.maxFrac = c.max;
    R.heroes[R.heroes.length - 1].role = hero.role || null;
    R.heroes[R.heroes.length - 1].cap_max_frac = c.max ? +c.max.toFixed(4) : null;
    return rec;
  }

  // Strati SOTTO il ritaglio: contorno «adesivo» e alone (livello 1, dietro guest_style: graphic). Copia dello stesso PNG
  // con un filtro SVG che tiene solo la sagoma dilatata: i pixel della persona restano quelli del ritaglio sopra.
  let filterSeq = 0;
  function svgDefs() {
    let s = document.getElementById('tt-defs');
    if (!s) {
      s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      s.id = 'tt-defs'; s.setAttribute('width', '0'); s.setAttribute('height', '0');
      Object.assign(s.style, { position: 'absolute', width: 0, height: 0 });
      document.body.appendChild(s);
    }
    return s;
  }
  function underCopy(parent, rec, filterXml, kind, z) {
    const id = `ttf${++filterSeq}`;
    svgDefs().insertAdjacentHTML('beforeend', `<filter id="${id}" x="-20%" y="-20%" width="140%" height="140%" color-interpolation-filters="sRGB">${filterXml}</filter>`);
    const u = TT.el('img', 'tt-under', parent);
    u.src = rec.el.src;
    Object.assign(u.style, { position: 'absolute', left: rec.el.style.left, top: rec.el.style.top, width: rec.el.style.width,
      height: rec.el.style.height, zIndex: z, filter: `url(#${id})`, pointerEvents: 'none' });
    if (rec.el.style.maskImage) u.style.webkitMaskImage = u.style.maskImage = rec.el.style.maskImage;
    R.under.push({ kind, z });
    return u;
  }
  // r in px CSS (≈10 px a 1280 per l'adesivo); colore: carta su campo scuro, inchiostro su campo chiaro.
  function outline(parent, rec, { r = 10, color = C.paper, z } = {}) {
    const zz = z ?? (parseInt(rec.el.style.zIndex || 10, 10) - 1);
    return underCopy(parent, rec, `<feMorphology in="SourceAlpha" operator="dilate" radius="${r}" result="d"/>` +
      `<feGaussianBlur in="d" stdDeviation="0.6" result="s"/><feComponentTransfer in="s" result="a"><feFuncA type="linear" slope="1.6"/></feComponentTransfer>` +
      `<feFlood flood-color="${color}"/><feComposite in2="a" operator="in"/>`, 'outline', zz);
  }
  function glow(parent, rec, { r = 16, blur = 22, color, opacity = 0.85, z } = {}) {
    const zz = z ?? (parseInt(rec.el.style.zIndex || 10, 10) - 2);
    return underCopy(parent, rec, `<feMorphology in="SourceAlpha" operator="dilate" radius="${r}" result="d"/>` +
      `<feGaussianBlur in="d" stdDeviation="${blur}" result="b"/>` +
      `<feFlood flood-color="${color}" flood-opacity="${opacity}"/><feComposite in2="b" operator="in"/>`, 'glow', zz);
  }

  // Disco d'accento dietro una persona: cerca centro e raggio vicino al preferito rispettando le regole di serie
  // (fuori dalle zone hover e timestamp, ≥ 24 px d'aria o taglio ≥ 15% del diametro, lontano dai box da evitare).
  // allowHover (disco «di campo» del duo): il disco può passare sotto le icone hover (massa di fondo); la zona del
  // timestamp resta vietata. contain: rettangoli che devono stare tutti DENTRO il disco (l'etichetta di formato in
  // inchiostro sul cerchio); se nessuna posizione li contiene si riprova senza.
  function solveDisc(rec, { side = 1, k = 1.0, dx = 0.18, dy = -0.12, avoid = [], kMin = 0.72, kMax = 1.15, allowHover = false, contain = [] } = {}) {
    const T = TT, f = rec.faceRect;
    const fcx = f.x + f.w / 2, fcy = f.y + f.h / 2;
    const pref = { cx: fcx + side * dx * f.h, cy: fcy + dy * f.h, r: k * f.h };
    const ok = (cx, cy, r) => {
      const hits = (z, m = 6) => { const nx = Math.max(z.x - m, Math.min(cx, z.x + z.w + m)), ny = Math.max(z.y - m, Math.min(cy, z.y + z.h + m)); return Math.hypot(cx - nx, cy - ny) < r; };
      if ((!allowHover && hits(T.zones.topRight)) || hits(T.zones.nogo)) return false;
      for (const a of avoid) if (hits(a, 10)) return false;
      for (const q of contain) for (const [px, py] of [[q.x - 8, q.y - 6], [q.x + q.w + 8, q.y - 6], [q.x - 8, q.y + q.h + 6], [q.x + q.w + 8, q.y + q.h + 6]])
        if (Math.hypot(px - cx, py - cy) > r) return false;
      const d = 2 * r;
      for (const g of [cy - r, cx - r, T.W - (cx + r), T.H - (cy + r)]) if (g < 24 && g > -0.15 * d) return false;
      return Math.hypot(cx - fcx, cy - fcy) <= 0.75 * r;          // resta «dietro la testa»
    };
    let best = null;
    for (let kk = kMax; kk >= kMin - 1e-6; kk -= 0.03) {
      const r = kk * f.h;
      for (let ox = -0.6; ox <= 0.6; ox += 0.05) for (let oy = -0.6; oy <= 0.8; oy += 0.05) {
        const cx = pref.cx + ox * f.h, cy = pref.cy + oy * f.h;
        if (!ok(cx, cy, r)) continue;
        const cost = Math.hypot(cx - pref.cx, cy - pref.cy) / f.h + Math.abs(kk - k) * 1.5;
        if (!best || cost < best.cost) best = { cx, cy, r, cost };
      }
    }
    if (!best && contain.length) return solveDisc(rec, { side, k, dx, dy, avoid, kMin, kMax, allowHover, contain: [] });
    if (best) best.contained = contain.length > 0;
    return best;
  }
  function disc(parent, { cx, cy, r, color, z = 6, kind = 'disco', field = false }) {
    const d = TT.el('div', 'tt-under tt-disc', parent);
    Object.assign(d.style, { position: 'absolute', left: (cx - r) + 'px', top: (cy - r) + 'px', width: 2 * r + 'px', height: 2 * r + 'px',
      borderRadius: '50%', background: color, zIndex: z });
    checkCircle(kind, cx, cy, r, 0);
    Object.assign(R.decos[R.decos.length - 1], { color, field: !!field, fill: true });
    R.under.push({ kind, z });
    return d;
  }
  // Sposta una persona già posata (multipli di 1/3 di px CSS: il ritaglio resta disegnato 1:1 sulla griglia a DPR 3) e
  // aggiorna rettangolo, volto e rapporto. Solo verso l'esterno per chi ha bordi dritti a filo (restano oltre il canvas).
  function moveRec(rec, dx, dy) {
    dx = Math.round(dx * 3) / 3; dy = Math.round(dy * 3) / 3;
    rec.left += dx; rec.top += dy;
    rec.el.style.left = rec.left + 'px'; rec.el.style.top = rec.top + 'px';
    rec.faceRect = { x: rec.faceRect.x + dx, y: rec.faceRect.y + dy, w: rec.faceRect.w, h: rec.faceRect.h };
    const h = R.heroes.find((q) => q.rect && Math.abs(q.rect[2] - rec.dw) < 0.02 && Math.abs(q.rect[3] - rec.dh) < 0.02 && q.src === (rec.hero && rec.hero.path));
    if (h) { h.rect = [rec.left, rec.top, rec.dw, rec.dh].map((v) => +v.toFixed(2)); h.flush_shift = [+(h.flush_shift[0] + dx).toFixed(1), +(h.flush_shift[1] + dy).toFixed(1)]; }
    return rec;
  }
  // Quota di un rettangolo che cade dentro un disco (griglia 9×5): per scegliere il colore del testo che ci sta sopra.
  function discCover(q, d) {
    if (!d) return 0;
    let n = 0, k = 0;
    for (let i = 0; i < 9; i++) for (let j = 0; j < 5; j++) {
      const x = q.x + (i + 0.5) / 9 * q.w, y = q.y + (j + 0.5) / 5 * q.h;
      k++; if (Math.hypot(x - d.cx, y - d.cy) <= d.r) n++;
    }
    return n / k;
  }

  // Posto libero per un elemento del telaio (simbolo, etichetta): niente sovrapposizioni con le sagome delle persone.
  // Prova da (x, y) spostandosi di `step` lungo `dir` (1 = verso destra, −1 = verso sinistra) fino a `limit`.
  function freeX(recs, { x, y, w, h, dir = 1, step = 12, limit = 520, margin = 10 } = {}) {
    const T = TT;
    const clear = (xx) => recs.every((r) => {
      const sl = T.silhouette(r, y - margin, y + h + margin);
      return xx + w + margin < sl.left || xx - margin > sl.right;
    });
    for (let d = 0; d <= limit; d += step) { const xx = x + dir * d; if (clear(xx)) return { x: xx, moved: d > 0 }; }
    return { x, moved: false, blocked: true };
  }

  // File del simbolo del brand (token logo.mark / logo.mark_on_dark, relativi alla cartella del brand): URL o null.
  function logoSrc(dark) {
    const rel = dark ? (LOGO.mark_on_dark || LOGO.mark_white) : (LOGO.mark || LOGO.mark_on_light);
    if (!rel || !(TT.brand && TT.brand.dir)) return null;
    return TT.asset(rel);
  }
  function scrim(parent, x, y, w, h, a = 0.5) {
    const s = TT.el('div', 'tt-scrim', parent);
    Object.assign(s.style, { position: 'absolute', left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px', zIndex: 3,
      background: `radial-gradient(closest-side, ${rgba(C.ink, a)}, ${rgba(C.ink, 0)})`, pointerEvents: 'none' });
    return s;
  }

  // Wordmark orizzontale: simbolo del brand (se c'è) + testo (tokens.wordmark.text, default tokens.name) nel font display.
  // h = altezza in px CSS; il simbolo è 0,92·h; versione chiara (carta / logo mark_on_dark) solo su fondo scuro.
  // Senza simbolo né testo non disegna niente (nota nel rapporto).
  function wordmark(parent, { x = 40, y = 34, h = 60, dark = true, z = 60, avoid = [], scrim: withScrim = true, text = null, ep = null } = {}) {
    const label = text != null ? String(text) : WM_TEXT;
    const src = logoSrc(dark);
    if (!label && !src && !ep) { R.notes.push('wordmark: il brand non ha né logo né testo (tokens.logo / tokens.wordmark)'); return null; }
    const sym = src ? +(h * 0.92).toFixed(1) : 0;
    const el = TT.el('div', 'tt-logo tt-wordmark', parent);
    Object.assign(el.style, { position: 'absolute', left: x + 'px', top: y + 'px', height: h + 'px', zIndex: z, display: 'flex',
      alignItems: 'center', gap: Math.round(h * 0.22) + 'px', whiteSpace: 'nowrap' });
    el.innerHTML = (src ? `<img class="tt-mark" src="${esc(src)}" style="display:block;width:${sym}px;height:${sym}px">` : '') +
      (label ? `<span class="tt-wm" style="font:400 ${Math.round(h * 0.62)}px/1 '${WM_FONT}';letter-spacing:.01em;color:${dark ? C.paper : C.ink}">${esc(label)}</span>` : '') +
      // numero di episodio (show_episode) anche quando il brand non ha il file del simbolo: resta accanto al wordmark
      (ep ? `<span class="tt-ep" data-role="text" data-kind="badge" style="font:800 ${Math.round(h * 0.55)}px/1 '${BODY}';letter-spacing:.01em;color:${dark ? C.paper : C.ink}">${esc(ep)}</span>` : '');
    let q = el.getBoundingClientRect();
    if (avoid.length) {
      const f = freeX(avoid, { x, y, w: q.width, h, dir: 1, limit: 420 });
      if (f.blocked) R.notes.push('wordmark: nessun punto libero dalle persone in alto (resta sopra una sagoma)');
      x = f.x; el.style.left = x + 'px'; q = el.getBoundingClientRect();
    }
    const w = q.width;
    if (withScrim && dark) scrim(parent, x - h * 0.9, y - h * 0.9, w + h * 1.8, h * 2.8, 0.5);
    R.logos.push({ kind: dark ? 'wordmark-light' : 'wordmark', symbol_css: src ? sym : null, symbol_4k: src ? Math.round(sym * 3) : null,
      at: [x, y], wordmark: true, rect: [x, y, w, h].map((v) => +v.toFixed(1)), width_4k: Math.round(w * 3), text: label || null });
    R.wordmark = { rect: [x, y, w, h].map((v) => +v.toFixed(1)), logo: src ? 'logo' : null, text: label || null };
    return { el, rect: { x, y, w, h } };
  }

  // Larghezza prevista del wordmark di altezza h (simbolo + spazio + testo), prima di disegnarlo: per tenere libero il suo
  // posto mentre si cercano disco e titolo.
  function wordmarkWidth(h, text = null) {
    const label = text != null ? String(text) : WM_TEXT;
    const c = document.createElement('canvas').getContext('2d');
    c.font = `400 ${Math.round(h * 0.62)}px "${WM_FONT}"`;
    const tw = label ? c.measureText(label).width * 1.01 : 0;
    const sym = logoSrc(true) ? h * 0.92 : 0;
    return Math.max(h, sym + (sym && tw ? Math.round(h * 0.22) : 0) + tw);
  }

  // Simbolo del brand in alto a sinistra (con wordmark: true anche il testo accanto). Chiaro solo su fondo scuro, mai su
  // una persona: con `avoid` (ritagli) si sposta a destra fino a un punto libero. Senza file del simbolo: il wordmark.
  function showLogo(parent, { x = 40, y = 34, symbol = 50, dark = true, wordmark: withText = false, scrim: withScrim = true, z = 60, avoid = [], ep = null } = {}) {
    const src = logoSrc(dark);
    if (!src) return wordmark(parent, { x, y, h: Math.round(symbol * 1.1), dark, z, avoid, scrim: withScrim, ep });
    if (avoid.length) {
      const f = freeX(avoid, { x, y, w: withText ? symbol * 4.6 : symbol, h: symbol, dir: 1, limit: 560 });
      if (f.blocked) R.notes.push('simbolo: nessun punto libero dalle persone in alto (resta sopra una sagoma)');
      x = f.x;
    }
    const w = TT.el('div', 'tt-logo', parent);
    Object.assign(w.style, { position: 'absolute', left: x + 'px', top: y + 'px', zIndex: z, display: 'flex', alignItems: 'center', gap: '8px' });
    let html = `<img class="tt-mark" src="${esc(src)}" style="display:block;width:${symbol}px;height:${symbol}px">`;
    if (withText && WM_TEXT) html += `<span class="tt-wm" style="font:400 ${Math.round(symbol * 0.62)}px/1 '${WM_FONT}';letter-spacing:.01em;color:${dark ? C.paper : C.ink}">${esc(WM_TEXT)}</span>`;
    // numero di episodio spento di default (show_episode: true per accenderlo)
    if (ep) html += `<span class="tt-ep" data-role="text" data-kind="badge" style="font:800 30px/1 '${BODY}';letter-spacing:.01em;color:${dark ? C.paper : C.ink};margin-left:6px">${esc(ep)}</span>`;
    w.innerHTML = html;
    if (withScrim && dark) {
      const r = symbol * (withText ? 3.4 : 1.9);
      w.ttScrim = scrim(parent, x + symbol / 2 - r, y + symbol / 2 - r * 0.75, 2 * r, 1.5 * r, 0.55);
    }
    R.logos.push({ kind: dark ? 'symbol-light' : 'symbol', symbol_css: symbol, symbol_4k: Math.round(symbol * 3), at: [x, y], wordmark: !!withText });
    const q = w.getBoundingClientRect();
    return { el: w, rect: { x: q.x, y: q.y, w: q.width, h: q.height } };
  }
  // Logo del telaio secondo show_logo: true | "wordmark" (default) → wordmark; "symbol" → solo il simbolo; false → niente.
  function frameLogo(parent, spec, { x = 40, y = 34, h = 58, symbol = 50, dark = true, avoid = [] } = {}) {
    const mode = spec.show_logo === false ? null : (spec.show_logo === 'symbol' ? 'symbol' : 'wordmark');
    if (!mode) return null;
    if (mode === 'symbol') return showLogo(parent, { x, y: y - 2, symbol, dark, ep: spec.show_episode ? spec.episode : null, avoid });
    return wordmark(parent, { x, y, h: spec.logo_h || h, dark, avoid, text: spec.wordmark_text != null ? spec.wordmark_text : null });
  }

  // Etichetta dell'host: piccola, «con <Nome>» nel font body su una striscia d'inchiostro; non è una targhetta
  // (l'ospite resta l'unico col box d'accento). kind meta: testo terziario, non deve reggere a 168 px.
  function hostTag(parent, p, { x, y, align = 'left', size = 22, z = 56, text = null } = {}) {
    const label = text || (p && p.name ? `con ${p.name}` : null);
    if (!label) return null;
    const e = TT.el('div', 'tt-host-tag', parent, label);
    e.dataset.role = 'text'; e.dataset.kind = 'meta'; e.dataset.sub = 'host';
    Object.assign(e.style, { position: 'absolute', top: y + 'px', zIndex: z, font: `700 ${size}px/1 "${BODY}"`, color: C.paper,
      letterSpacing: '.005em', whiteSpace: 'nowrap', background: rgba(C.ink, 0.86), padding: '.2em .38em .24em' });
    if (align === 'right') { const ww = e.getBoundingClientRect().width; e.style.left = (x - ww) + 'px'; } else e.style.left = x + 'px';
    const q = e.getBoundingClientRect();
    const rect = [q.x, q.y, q.width, q.height].map((v) => +v.toFixed(1));
    R.host_tag = { rect, text: label, name: p && p.name ? p.name : null };
    R.credentials.push({ name: p && p.name ? p.name : null, title: label, role: 'host', box: 'tag', rect });
    return { el: e, rect: { x: q.x, y: q.y, w: q.width, h: q.height } };
  }

  // Testi piccoli del telaio: riga meta e etichetta di formato (maiuscoletto spaziato, body 700). Terziari: non devono
  // reggere a 168 px (kind meta/label: niente avviso di leggibilità), ma restano fuori dalle zone UI.
  // strip: striscia d'inchiostro dietro il testo, quando sotto c'è una persona chiara (riga meta sulla maglia dell'host)
  function smallCaps(parent, text, { x, y, right = null, size = 17, color = C.paper, kind = 'meta', sep = '/', z = 55, sepColor = null, avoid = [], tracking = '.2em', strip = false } = {}) {
    const e = TT.el('div', 'tt-sc', parent);
    e.dataset.role = 'text'; e.dataset.kind = kind;
    Object.assign(e.style, { position: 'absolute', top: y + 'px', font: `700 ${size}px/1 "${BODY}"`, letterSpacing: tracking,
      textTransform: 'uppercase', color, whiteSpace: 'nowrap', zIndex: z, textShadow: '0 1px 2px rgba(0,0,0,.55), 0 0 14px rgba(0,0,0,.45)' });
    if (strip) { Object.assign(e.style, { background: rgba(C.ink, 0.86), padding: '.42em .3em .42em .5em', textShadow: 'none' }); e.dataset.strip = '1';
      (R.strips = R.strips || []).push(String(text).split(/\s*\/\s*/).filter(Boolean).join(' / ')); }
    const parts = String(text).split(/\s*\/\s*/).filter(Boolean);
    e.innerHTML = parts.map((p) => esc(p)).join(` <span style="opacity:.75${sepColor ? ';color:' + sepColor : ''}">${sep}</span> `);
    if (right != null) { const w = e.getBoundingClientRect().width; e.style.left = (right - w) + 'px'; } else e.style.left = x + 'px';
    if (avoid.length) {
      const q = e.getBoundingClientRect();
      const f = freeX(avoid, { x: q.x, y: q.y, w: q.width, h: q.height, dir: right != null ? -1 : 1, limit: 420, margin: 8 });
      if (f.blocked) R.notes.push(`${kind}: sopra una sagoma (nessun punto libero)`);
      else e.style.left = f.x + 'px';
    }
    return e;
  }

  // Targhetta: nome in un box pieno (inchiostro sull'accento se il contrasto regge ≥ 7:1, altrimenti inchiostro su carta)
  // + riga del ruolo sotto, in carta su striscia d'inchiostro.
  function namePlate(parent, p, { x, y, accent = DEFAULT_ACCENT, align = 'left', nameSize = 44, roleSize = 31, z = 56, maxW = 520, strip = true } = {}) {
    if (!p || !p.name) return null;
    const box = plateBox(accent);
    const boxCol = box === 'paper' ? C.paper : useAccent(accent);
    const w = TT.el('div', 'tt-plate', parent);
    Object.assign(w.style, { position: 'absolute', top: y + 'px', zIndex: z, display: 'flex', flexDirection: 'column',
      alignItems: align === 'right' ? 'flex-end' : 'flex-start', gap: '0px', maxWidth: maxW + 'px' });
    const n = TT.el('div', 'tt-name', w, String(p.name).toLocaleUpperCase('it'));
    n.dataset.role = 'text'; n.dataset.kind = 'name';
    Object.assign(n.style, { font: `400 ${nameSize}px/1 "${HEAD}"`, letterSpacing: '.01em', color: C.ink, background: boxCol,
      padding: '.16em .26em .12em', whiteSpace: 'nowrap' });
    let r = null;
    if (p.title) {
      r = TT.el('div', 'tt-role', w, p.title);
      r.dataset.role = 'text'; r.dataset.kind = 'role';
      // striscia d'inchiostro dietro il ruolo: resta leggibile anche sopra una camicia chiara (il fondo sotto non si conosce)
      Object.assign(r.style, { font: `700 ${roleSize}px/1.05 "${BODY}"`, color: C.paper, letterSpacing: '-.005em',
        whiteSpace: 'nowrap', background: strip ? rgba(C.ink, 0.88) : 'none', padding: strip ? '.12em .3em .14em' : '0' });
    }
    // misura e restringi se serve (mai sotto 36 / 26 px)
    for (let k = 0; k < 12 && w.getBoundingClientRect().width > maxW; k++) {
      nameSize = Math.max(36, nameSize - 2); roleSize = Math.max(26, roleSize - 1);
      n.style.fontSize = nameSize + 'px'; if (r) r.style.fontSize = roleSize + 'px';
    }
    if (align === 'right') { const ww = w.getBoundingClientRect().width; w.style.left = (x - ww) + 'px'; } else w.style.left = x + 'px';
    const q = w.getBoundingClientRect();
    R.credentials.push({ name: p.name, title: p.title || null, role: p.role || null, box,
      rect: [q.x, q.y, q.width, q.height].map((v) => +v.toFixed(1)) });
    return { el: w, rect: { x: q.x, y: q.y, w: q.width, h: q.height } };
  }

  // Titolo v2. Font condensato (HEAD, default Anton) maiuscolo, interlinea stretta, punto finale (. ? !) nell'accento;
  // parola chiave: box d'accento con testo inchiostro (keyword_style box), oppure filetto d'accento sotto (bar), o niente.
  // hook_font: "display" = font display del brand. Il punto finale si aggiunge solo se la frase non ne ha.
  function headline(parent, spec, { accent = DEFAULT_ACCENT, color = C.paper, family = null, keywordStyle = 'box', lineHeight = null,
                                   align = 'left', fullStop = true, z = 40 } = {}) {
    const fam = family || (spec.hook_font === 'display' ? DISPLAY : HEAD);
    const anton = fam === 'Anton';
    const h = TT.el('div', 'tt-hook', parent); h.dataset.kind = 'hook'; h.id = 'hook';
    const acc = useAccent(accent);
    let text = String(spec.hook || spec.text || '').trim();
    // interlinea stretta (0.9 su Anton). Le maiuscole accentate (È, À, Ù…) di Anton arrivano a 1,10 em sopra la linea di
    // base contro 0,86 delle maiuscole: con 0.9 l'accento entrerebbe nella riga sopra («È PIÙ» sotto «NESSUN»).
    // Si apre solo la riga che ha la parola accentata (inline-block con padding-top, più sotto), non tutto il blocco.
    const ACC = /[ÀÈÉÌÒÙàèéìòù]/;
    Object.assign(h.style, { position: 'absolute', fontFamily: `"${fam}"`, textTransform: 'uppercase', color, zIndex: z,
      lineHeight: String(lineHeight || (anton ? 0.9 : 0.97)), letterSpacing: anton ? '0' : '-.01em',
      textAlign: align, textWrap: 'balance' });
    const term = /[.?!…]$/.test(text) ? '' : (fullStop && spec.full_stop !== false ? '.' : '');
    TT.hook(h, text + term, keywordStyle === 'none' ? null : spec.highlight);
    // tipografia italiana: le parole di 1–3 lettere (articoli, preposizioni, «HA», «NON») restano attaccate alla parola dopo
    // (spazio non divisibile) → niente «UN» o «IL» da soli a fine riga
    h.normalize();                                            // TT.hook crea un nodo per parola e uno per spazio
    const tw = document.createTreeWalker(h, NodeFilter.SHOW_TEXT);
    const nodes = []; let nd;
    while ((nd = tw.nextNode())) nodes.push(nd);
    nodes.forEach((n, i) => {
      let t = n.textContent.replace(/(?<=^|[\s ])([\p{L}’']{1,3}) (?=\S)/gu, '$1 ');
      if (i < nodes.length - 1 && /(?<=^|[\s ])[\p{L}’']{1,3} $/u.test(t)) t = t.replace(/ $/, ' ');
      n.textContent = t;
    });
    // punteggiatura finale nell'accento (ultimo carattere del testo reso)
    const walker = document.createTreeWalker(h, NodeFilter.SHOW_TEXT);
    let last = null;
    while ((nd = walker.nextNode())) if (nd.textContent.trim()) last = nd;
    if (last && /[.?!…]$/.test(last.textContent)) {
      const t = last.textContent, p = t.slice(-1);
      last.textContent = t.slice(0, -1);
      const s = document.createElement('span'); s.className = 'tt-term'; s.textContent = p;
      s.style.color = keywordStyle === 'box' && last.parentElement.classList.contains('hl') ? C.ink : acc;
      last.parentNode.insertBefore(s, last.nextSibling);
    }
    // la parola corta incollata prima della parola chiave (UNA TAZZA) va a capo con lei anche quando questa è un inline-block
    for (const k of h.querySelectorAll('.hl')) {
      const prev = k.previousSibling;
      const mm = prev && prev.nodeType === 3 ? /(\S+ )$/.exec(prev.textContent) : null;
      if (mm) {
        prev.textContent = prev.textContent.slice(0, -mm[1].length);
        const w = document.createElement('span'); w.style.whiteSpace = 'nowrap'; w.className = 'tt-glue';
        k.parentNode.insertBefore(w, k); w.appendChild(document.createTextNode(mm[1])); w.appendChild(k);
      }
    }
    // parole con maiuscola accentata fuori dal box: inline-block con padding-top → solo la loro riga si apre quanto serve
    // all'accento (Anton: 1,10 em − 0,87 em di riga a interlinea 0.9 + 0,03 di aria ≈ 0,26 em; altri font: 0,14 em)
    const accPad = anton ? '.26em' : '.14em';
    const tw2 = document.createTreeWalker(h, NodeFilter.SHOW_TEXT);
    const tn = [];
    while ((nd = tw2.nextNode())) if (ACC.test(nd.textContent) && !(nd.parentElement && nd.parentElement.closest('.hl'))) tn.push(nd);
    for (const n of tn) {
      // separatore = solo lo spazio normale: «È PIÙ» (parola corta incollata) resta un blocco unico, mai spezzato
      const parts = n.textContent.split(/([^ \t\n\r]*[ÀÈÉÌÒÙàèéìòù][^ \t\n\r]*)/u);
      const frag = document.createDocumentFragment();
      parts.forEach((t, i) => {
        if (!t) return;
        if (i % 2) { const s = document.createElement('span'); s.className = 'tt-acc'; s.textContent = t;
          Object.assign(s.style, { display: 'inline-block', paddingTop: accPad }); frag.appendChild(s); }
        else frag.appendChild(document.createTextNode(t));
      });
      n.parentNode.replaceChild(frag, n);
    }
    for (const k of h.querySelectorAll('.hl')) {
      // parola chiave accentata (PIÙ, È): il box si alza a coprire l'accento
      const kpad = ACC.test(k.textContent) ? (anton ? '.30em' : '.18em') : '.07em';
      if (keywordStyle === 'box') Object.assign(k.style, { background: acc, color: C.ink, padding: `${kpad} .08em .03em`, margin: '.04em -.02em 0',
        display: 'inline-block', lineHeight: anton ? '.96' : '1' });
      else if (ACC.test(k.textContent)) Object.assign(k.style, { display: 'inline-block', paddingTop: accPad });
      else if (keywordStyle === 'bar') Object.assign(k.style, { textDecoration: `underline ${acc}`, textDecorationThickness: '.09em',
        textUnderlineOffset: '.06em', textDecorationSkipInk: 'none' });
    }
    return h;
  }

  // Fascia libera tra due sagome (o tra una sagoma e il margine) per il titolo: prova bande verticali e posizioni,
  // tiene il corpo più grande; il testo non entra mai nel box del volto né nei dischi d'accento.
  function fitBetween(hook, { left = null, right = null, x0 = 48, x1 = 1232, yMin = 70, yMax = 660, gap = 22, min = 60, max = 230,
                            maxLines = 3, center = 0.45, bands = [260, 320, 380, 440, 500, 560], circles = [], boxes = [], align = 'center',
                            preferFewer = 0.93 } = {}) {
    const T = TT;
    // il testo non entra mai nel box del volto (controllo bloccante 07 §12.4), anche dove il box sporge oltre la sagoma
    boxes = [...boxes, ...[left, right].filter(Boolean).map((r) => ({ x: r.faceRect.x - 6, y: r.faceRect.y - 6, w: r.faceRect.w + 12, h: r.faceRect.h + 12 }))];
    const span = (y0, y1) => {
      let a = x0, b = x1;
      if (left) a = Math.max(a, T.silhouette(left, y0, y1).right + gap);
      if (right) b = Math.min(b, T.silhouette(right, y0, y1).left - gap);
      for (const c of circles) {
        const dy = (y0 <= c.cy && c.cy <= y1) ? 0 : Math.min(Math.abs(y0 - c.cy), Math.abs(y1 - c.cy));
        if (dy >= c.r) continue;
        const dx = Math.sqrt(c.r * c.r - dy * dy);
        if (c.cx < (a + b) / 2) a = Math.max(a, c.cx + dx + gap); else b = Math.min(b, c.cx - dx - gap);
      }
      for (const q of boxes) {
        if (q.y + q.h < y0 || q.y > y1) continue;
        if (q.x + q.w / 2 < (a + b) / 2) a = Math.max(a, q.x + q.w + gap); else b = Math.min(b, q.x - gap);
      }
      return [a, b];
    };
    let best = null;
    for (const H of bands) {
      for (let y0 = yMin; y0 + H <= yMax; y0 += 10) {
        const [a, b] = span(y0, y0 + H);
        const w = b - a;
        if (w < 180) continue;
        const r = T.fit(hook, { maxW: w, maxH: H, min, max, maxLines, preferFewer });
        const hh = hook.getBoundingClientRect().height;
        const yc = y0 + (H - hh) / 2 + hh / 2;
        const score = r.size - Math.abs(yc - T.H * center) * 0.03;
        if (!best || score > best.score) best = { score, a, b, w, H, y0, size: r.size };
      }
    }
    if (!best) { R.notes.push('titolo: nessuna fascia libera ≥ 180 px'); return null; }
    T.fit(hook, { maxW: best.w, maxH: best.H, min, max, maxLines, preferFewer });
    const hh = hook.getBoundingClientRect().height;
    hook.style.top = (best.y0 + (best.H - hh) / 2) + 'px';
    hook.style.left = best.a + 'px';
    hook.style.textAlign = align;
    // stringi la larghezza alla riga più larga (allineamento visivo) mantenendo la posizione
    const lr = T.lineRects(hook), widest = Math.max(...lr.map((q) => q.w));
    if (align === 'center') { hook.style.left = (best.a + (best.w - widest) / 2) + 'px'; hook.style.width = Math.ceil(widest + 2) + 'px'; }
    else if (align === 'left') hook.style.width = Math.ceil(widest + 2) + 'px';
    return best;
  }

  // Pop-out (scena): la stessa scena del ritaglio, allineata pixel su pixel sotto di esso (scena = frame della sorgente
  // già graduato/sfocato da yt-thumb-render), più una copia «cover» molto sfocata che riempie il resto del quadro.
  async function popout(parent, rec, scene, { z = 1, backdrop = true } = {}) {
    const T = TT, m = scene.map || {};
    const s = m.scale;                                        // px del ritaglio per px della sorgente
    const k = rec.dw / rec.hero.w;                            // px CSS per px del ritaglio
    const kk = k * s;                                         // px CSS per px della sorgente
    const srcL = m.face_src[0] - m.face_out[0] / s, srcT = m.face_src[1] - m.face_out[1] / s;   // origine del PNG nella sorgente
    const [cx, cy, cw, ch] = scene.crop;                      // ritaglio della scena (px sorgente)
    if (backdrop) {
      const b = TT.el('div', 'tt-under tt-scene-back', parent);
      Object.assign(b.style, { position: 'absolute', inset: '-60px', backgroundImage: `url("${scene.src}")`, backgroundSize: 'cover',
        backgroundPosition: 'center', filter: 'blur(28px)', zIndex: z });
      R.under.push({ kind: 'scene-backdrop', z });
    }
    const i = await img(parent, scene.src, 'tt-under tt-scene');
    Object.assign(i.style, { position: 'absolute', zIndex: z + 1, width: cw * kk + 'px', height: ch * kk + 'px',
      left: (rec.left + (cx - srcL) * kk) + 'px', top: (rec.top + (cy - srcT) * kk) + 'px' });
    R.under.push({ kind: 'scene', z: z + 1 });
    return i;
  }

  // Slot del «prop» (oggetto della storia generato da SOLO TESTO, o foto reale dell'oggetto): PNG con alpha, sotto le
  // persone (classe tt-under), mai sopra un volto. Slot: behind-guest (dietro la spalla, lato opposto al testo), left,
  // right, center-low. Senza file: yt-thumb-render scrive la richiesta in prop_requests.json e il render va avanti senza.
  async function propSlot(parent, prop, rec, { side = 1, z = 5 } = {}) {
    if (!prop || !prop.src) return null;
    const T = TT;
    const i = await img(parent, prop.src, 'tt-under tt-prop');
    const k = prop.scale || 1;
    const h = T.H * 0.62 * k, w = h * i.naturalWidth / i.naturalHeight;
    let x, y;
    if (prop.slot === 'left') { x = 40; y = T.H - h - 20; }
    else if (prop.slot === 'right') { x = T.W - w - 40; y = (T.H - h) / 2; }
    else if (prop.slot === 'center-low') { x = (T.W - w) / 2; y = T.H - h * 0.85; }
    else {                                                   // behind-guest: sporge per ~metà dalla sagoma, verso il centro
      const f = rec.faceRect;
      y = Math.max(-h * 0.1, f.y + f.h * 0.6 - h * 0.35);
      const sl = T.silhouette(rec, y + h * 0.35, y + h * 0.75);
      x = side > 0 ? sl.left - w * 0.55 : sl.right - w * 0.45;
    }
    Object.assign(i.style, { position: 'absolute', left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px', zIndex: z,
      filter: 'drop-shadow(0 18px 30px rgba(0,0,0,.45))' });
    R.under.push({ kind: 'prop', z, slot: prop.slot || 'behind-guest' });
    const nogo = T.zones.nogo, tr = T.zones.topRight;
    const inter = (a) => x < a.x + a.w && a.x < x + w && y < a.y + a.h && a.y < y + h;
    if (inter(nogo) || inter(tr)) R.notes.push('prop: tocca una zona UI (timestamp o hover)');
    return { el: i, rect: { x, y, w, h } };
  }

  const rectOf = (e) => { const q = e.getBoundingClientRect(); return { x: q.x, y: q.y, w: q.width, h: q.height }; };

  // Etichetta di formato sul disco: a cavallo del bordo (nessuna posizione la conteneva) va fuori dal disco, verso
  // sinistra, in carta; tutta dentro il disco diventa inchiostro (come un'etichetta stampata sul cerchio).
  function labelOnDisc(label, dsc) {
    if (!label) return;
    let cov = discCover(rectOf(label), dsc);
    for (let k = 0; k < 120 && cov > 0 && cov < 0.999; k++) { label.style.left = (parseFloat(label.style.left) - 4) + 'px'; cov = discCover(rectOf(label), dsc); }
    if (cov >= 0.999) Object.assign(label.style, { color: C.ink, textShadow: 'none' });
    R.label = { rect: Object.values(rectOf(label)).map((v) => +v.toFixed(1)), on_disc: cov >= 0.999 };
  }

  return { C, rgba, hexRgb, hueSat, skinLike, grain, img, place, headTop, fitBeside, checkCircle, checkPolygon, checkRect, propSlot,
    finish, contrast, lum, report: R, ACCENTS, DEFAULT_ACCENT, HEAD, DISPLAY, BODY, accentName, useAccent, plateBox, capFrac, wantFrac,
    person, outline, glow, solveDisc, disc, freeX, showLogo, wordmark, wordmarkWidth, frameLogo, smallCaps, namePlate, headline, fitBetween, popout,
    discCover, hostTag, moveRec, rectOf, labelOnDisc };
})();
