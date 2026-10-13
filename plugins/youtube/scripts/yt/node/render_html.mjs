// render_html.mjs — renderer HTML→PNG delle thumbnail (Playwright + Google Chrome di sistema).
//
// Uso:  node render_html.mjs JOBS.json   → stdout: JSON con un risultato per job; log su stderr.
//
// JOBS.json:
// {
//   "viewport": {"w": 1280, "h": 720}, "scale": 3,
//   "fonts": [{"family": "Anton", "file": "/abs/Anton-Regular.ttf", "weight": "400"}],
//   "jobs": [{"id": "A", "template": "/abs/node/templates/ritratto.html", "spec": {...}, "tokens": {...},
//             "out": "/abs/out.png", "debug_out": "/abs/out_debug.png",
//             "fonts": [...] (facoltativo: sostituisce "fonts" per questo job),
//             "brand": "slug", "brand_dir": "/abs/<brands_dir>/<slug>" (facoltativi: brand esterno),
//             "fx_check": true (facoltativo, template v2: dopo il PNG rende i riquadri dei volti con gli strati .tt-under
//                         nascosti → <out>.nofx<i>.png, per il controllo face_pixels_unchanged di yt-thumb-render)}]
// }
// Metriche in più: per il gancio `rows` (righe di glifi, altezza/H misurata sulle maiuscole senza accenti, riga con la parola chiave) e `fonts_ok`
// (famiglie davvero caricate: un font mancante è un errore, non un ripiego silenzioso).
//
// Template di un brand esterno (<brands_dir>/<slug>/templates/*.html): la pagina è un file:// e Chrome gira con
// --allow-file-access-from-files, quindi i percorsi relativi al template (../fonts/…, ../logo/…) funzionano;
// TT.brand = {slug, dir} e TT.asset('logo/x.svg') danno l'URL di un file nella cartella del brand.
//
// Il template registra un builder con TT.ready(async (spec, T) => {...}); il runtime (iniettato qui
// sotto con addInitScript) carica font locali, espone i token come variabili CSS, offre gli helper
// (fit del testo, posizionamento del soggetto sul volto, profilo della sagoma) e misura i controlli
// geometrici: zona del timestamp in basso a destra, testo fuori quadro, testo sul volto, righe, cap height.
// Nessuna rete: Chrome è lanciato con channel 'chrome' (nessun download di browser).
//
// Playwright: questo file resta nel plugin, i node_modules stanno nella data dir del plugin
// (<data>/node, installati da /youtube:setup). yt-thumb-render passa YT_NODE_PREFIX=<data>/node; senza la
// variabile la risoluzione parte da questa cartella (checkout di sviluppo con node/node_modules).
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const requireFrom = createRequire(process.env.YT_NODE_PREFIX
  ? path.join(path.resolve(process.env.YT_NODE_PREFIX), 'package.json')
  : import.meta.url);
const { chromium } = requireFrom('playwright');

const log = (...a) => process.stderr.write(a.join(' ') + '\n');

// Telaio comune dei template (window.KIT, node/templates/_common.js): iniettato in ogni pagina subito dopo il runtime TT,
// così funziona anche per i template copiati nella cartella di un brand (<brands_dir>/<slug>/templates/), che non hanno
// _common.js accanto. Un job può indicarne un altro con "common_js" (percorso assoluto).
const COMMON_JS = fileURLToPath(new URL('./templates/_common.js', import.meta.url));
const commonSource = (p) => { try { return fs.readFileSync(p || COMMON_JS, 'utf8'); } catch (e) { return null; } };

// ── Runtime iniettato nella pagina ───────────────────────────────────────────
function ttRuntime(cfg) {
  const T = (window.TT = {});
  T.spec = cfg.spec;
  T.tokens = cfg.tokens || {};
  T.brand = cfg.brand || {};
  T.asset = (rel) => (T.brand.dir ? new URL(String(rel).replace(/^\/+/, ''), T.brand.dir).href : String(rel));
  T.W = cfg.vw; T.H = cfg.vh;
  T.zones = {
    nogo: { x: cfg.vw - 230, y: cfg.vh - 110, w: 230, h: 110 },   // badge della durata (misurato sulla griglia desktop)
    topRight: { x: cfg.vw - 120, y: 0, w: 120, h: 80 },         // icone hover desktop
  };
  T._heroes = [];
  T.ready = (fn) => { T._builder = fn; };

  T.el = (tag, cls, parent, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  };

  // Testo del gancio → righe/parole; '|' o '\n' = a capo forzato; parole evidenziate in span.hl.
  T.hook = (el, text, highlight, opts = {}) => {
    el.innerHTML = '';
    el.dataset.role = el.dataset.role || 'text';
    const hl = (Array.isArray(highlight) ? highlight : (highlight ? [highlight] : []))
      .map((h) => String(h).toLocaleUpperCase('it').trim()).filter(Boolean);
    const upper = opts.upper !== false;
    // Apostrofo tipografico (DALL’ITALIA) e righe: '|' o '\n' = a capo forzato.
    const lines = String(text || '').replace(/(\w)'(\w)/g, '$1’$2').split(/\s*(?:\||\n)\s*/);
    // Evidenziazione per frase: si cerca la sequenza di parole, non solo la singola parola.
    lines.forEach((line, li) => {
      const words = line.split(/\s+/).filter(Boolean);
      let i = 0;
      while (i < words.length) {
        let matched = 0;
        for (const h of hl) {
          const hw = h.split(/\s+/);
          const seg = words.slice(i, i + hw.length).map((w) => w.toLocaleUpperCase('it')).join(' ');
          const clean = (s) => s.replace(/[.,!?;:«»"“”]/g, '');
          if (hw.length && clean(seg) === clean(hw.join(' '))) { matched = hw.length; break; }
        }
        const chunk = words.slice(i, i + Math.max(1, matched)).join(' ');
        const shown = upper ? chunk.toLocaleUpperCase('it') : chunk;
        if (!matched && /^(→|->|⟶|=>)$/.test(chunk)) {
          // Freccia disegnata (i font display spesso non hanno il glifo → ripiego incoerente).
          const a = T.el('span', 'arr', el);
          a.innerHTML = '<svg viewBox="0 0 100 64" fill="none" stroke="currentColor" stroke-width="15" stroke-linecap="square" stroke-linejoin="miter"><path d="M6 32H84M58 9L84 32L58 55"/></svg>';
        } else if (matched) { T.el('span', 'hl', el, shown); } else { el.appendChild(document.createTextNode(shown)); }
        i += Math.max(1, matched);
        if (i < words.length) el.appendChild(document.createTextNode(' '));
      }
      if (li < lines.length - 1) el.appendChild(document.createElement('br'));
    });
    return el;
  };

  // Righe effettivamente rese (top distinti dei rettangoli di riga).
  T.lineRects = (el) => {
    const r = document.createRange();
    r.selectNodeContents(el);
    const rects = [...r.getClientRects()].filter((q) => q.width > 1 && q.height > 1);
    const fs = parseFloat(getComputedStyle(el).fontSize) || 16;
    const lines = [];
    for (const q of rects.sort((a, b) => a.top - b.top)) {
      const mid = q.top + q.height / 2;
      const hit = lines.find((L) => Math.abs(L.mid - mid) < fs * 0.35);
      if (hit) {
        hit.x0 = Math.min(hit.x0, q.left); hit.x1 = Math.max(hit.x1, q.right);
        hit.y0 = Math.min(hit.y0, q.top); hit.y1 = Math.max(hit.y1, q.bottom);
      } else lines.push({ mid, x0: q.left, x1: q.right, y0: q.top, y1: q.bottom });
    }
    return lines.map((L) => ({ x: L.x0, y: L.y0, w: L.x1 - L.x0, h: L.y1 - L.y0 }));
  };

  // Rettangoli "d'inchiostro" per riga: glifi reali (metriche canvas, non l'area del font che sborda
  // sopra/sotto) + box visibili con sfondo (parola evidenziata, fascia, cursore). Servono ai controlli.
  // bare: ascendente misurato sulla parola senza segni diacritici (È → E): l'altezza di riga del gancio è quella delle
  // maiuscole, l'accento sopra non la allunga («È ANDATA» misurerebbe il 24 % con le maiuscole al 19 %).
  T.inkRects = (el, { boxes = true, bare = false } = {}) => {
    const rects = [];
    const ctx = document.createElement('canvas').getContext('2d');
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const raw = node.textContent;
      if (!raw.trim()) continue;
      const cs = getComputedStyle(node.parentElement);
      const tt = cs.textTransform;
      const txt = tt === 'uppercase' ? raw.toLocaleUpperCase('it') : tt === 'lowercase' ? raw.toLocaleLowerCase('it') : raw;
      ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
      // per parola: un nodo di testo può andare a capo su più righe (le metriche vanno prese riga per riga)
      const re = /[^\s\u00a0]+/g;
      let mt;
      while ((mt = re.exec(raw))) {
        const word = txt.slice(mt.index, mt.index + mt[0].length);
        const m = ctx.measureText(bare ? word.normalize('NFD').replace(/\p{M}/gu, '') : word);
        const fa = m.fontBoundingBoxAscent, fd = m.fontBoundingBoxDescent;
        const r = document.createRange(); r.setStart(node, mt.index); r.setEnd(node, mt.index + mt[0].length);
        for (const q of r.getClientRects()) {
          if (q.width < 1) continue;
          const k = q.height / ((fa + fd) || q.height);        // area del contenuto → baseline
          const base = q.top + fa * k;
          rects.push({ x: q.left, y: base - m.actualBoundingBoxAscent, w: q.width,
            h: m.actualBoundingBoxAscent + Math.max(0, m.actualBoundingBoxDescent) });
        }
      }
    }
    for (const e of (boxes ? el.querySelectorAll('*') : [])) {
      const bg = getComputedStyle(e).backgroundColor;
      const a = /rgba?\(([^)]+)\)/.exec(bg);
      const alpha = a ? (a[1].split(',')[3] !== undefined ? parseFloat(a[1].split(',')[3]) : 1) : 0;
      if (alpha > 0.05) { const b = e.getBoundingClientRect(); if (b.width > 1) rects.push({ x: b.left, y: b.top, w: b.width, h: b.height }); }
    }
    // unione per riga (sovrapposizione verticale)
    const lines = [];
    for (const q of rects.sort((a, b) => a.y - b.y)) {
      // stessa riga se la sovrapposizione verticale supera metà del rettangolo più basso (gli accenti, É, sporgono
      // nella riga sopra quando l'interlinea è stretta: non sono la stessa riga)
      const hit = lines.find((L) => Math.min(L.y + L.h, q.y + q.h) - Math.max(L.y, q.y) > 0.5 * Math.min(L.h, q.h));
      if (hit) {
        const x0 = Math.min(hit.x, q.x), y0 = Math.min(hit.y, q.y);
        hit.w = Math.max(hit.x + hit.w, q.x + q.w) - x0; hit.h = Math.max(hit.y + hit.h, q.y + q.h) - y0; hit.x = x0; hit.y = y0;
      } else lines.push({ ...q });
    }
    return lines;
  };

  // Font-size massimo (ricerca binaria) che fa stare il testo in maxW×maxH con al più maxLines righe.
  // preferFewer (default 0.85): se con meno righe il corpo resta ≥ 85% del massimo, si preferiscono meno
  // righe (evita parole orfane tipo "IL" da sole e blocchi a scala inutili).
  T.fit = (el, { maxW, maxH, min = 40, max = 220, maxLines = 3, preferFewer = 0.85 }) => {
    el.style.width = maxW + 'px';
    const fits = (s, nLines) => {
      el.style.fontSize = s + 'px';
      if (el.scrollWidth > maxW + 1) return false;
      if (el.getBoundingClientRect().height > maxH + 1) return false;
      return T.lineRects(el).length <= nLines;
    };
    const search = (nLines) => {
      let lo = min, hi = max, best = min;
      while (hi - lo > 0.5) {
        const mid = (lo + hi) / 2;
        if (fits(mid, nLines)) { best = mid; lo = mid; } else hi = mid;
      }
      return best;
    };
    let size = search(maxLines), used = maxLines;
    if (preferFewer && preferFewer < 1) {
      for (let n = 1; n < maxLines; n++) {
        const s = search(n);
        if (s >= size * preferFewer && fits(s, n)) { size = s; used = n; break; }
      }
    }
    const clamped = !fits(size, used);
    el.style.fontSize = size + 'px';
    const lr = T.lineRects(el);
    const widest = Math.max(...lr.map((q) => q.w), 0);
    el.dataset.fit = JSON.stringify({ size, maxW, maxH, maxLines: used, clamped });
    return { size, widest, lines: lr.length };
  };

  // Colore di testo (scuro/chiaro) con più contrasto WCAG su un fondo dato.
  T.lum = (hex) => {
    const h = String(hex).replace('#', ''); const c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  T.contrast = (a, b) => { const [x, y] = [T.lum(a), T.lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  T.textOn = (bg, dark = '#111111', light = '#ffffff') => (T.contrast(dark, bg) >= T.contrast(light, bg) ? dark : light);

  T.capRatio = (family, weight = 400) => {
    const c = document.createElement('canvas').getContext('2d');
    c.font = `${weight} 100px "${family}"`;
    const m = c.measureText('H');
    return (m.actualBoundingBoxAscent || 70) / 100;
  };

  // Soggetto scontornato: scala per altezza volto, centro volto in (cx, faceTop). Il ritaglio deve
  // uscire dal fondo del quadro: se finisce prima, lo si abbassa (il volto scende) e si sfuma il fondo.
  T.placeHero = (img, hero, o) => {
    const nat = { w: hero.w || img.naturalWidth, h: hero.h || img.naturalHeight };
    const face = hero.face || [0.35, 0.08, 0.3, 0.16];
    const s = (o.faceH) / (face[3] * nat.h);
    const dw = nat.w * s, dh = nat.h * s;
    let left = o.cx - (face[0] + face[2] / 2) * nat.w * s;
    let top = o.faceTop - face[1] * nat.h * s;
    // Bordi del ritaglio che toccano il riquadro sorgente (es. inset tagliato): niente lati "tagliati" in vista.
    const ab = hero.alpha_box || [0, 0, 1, 1];
    const bottomOpaque = top + (ab[1] + ab[3]) * dh;
    let fade = false;
    if (o.bleedBottom !== false && bottomOpaque < T.H + 2) {
      const shift = T.H + 2 - bottomOpaque;
      if (shift < T.H * 0.25) top += shift; else fade = true;
    }
    if (hero.touches && hero.touches.bottom === false && bottomOpaque < T.H) fade = true;
    img.style.position = 'absolute';
    img.style.width = dw + 'px'; img.style.height = dh + 'px';
    img.style.left = left + 'px'; img.style.top = top + 'px';
    if (fade || o.fade) {
      const fy = Math.max(0, Math.min(100, ((T.H - top) / dh) * 100));
      img.style.webkitMaskImage = img.style.maskImage = `linear-gradient(to bottom, #000 ${fy - 12}%, transparent ${fy}%)`;
    }
    const faceRect = { x: left + face[0] * dw, y: top + face[1] * dh, w: face[2] * dw, h: face[3] * dh };
    const rec = { el: img, s, left, top, dw, dh, faceRect, profile: hero.profile, alpha_box: ab };
    T._heroes.push(rec);
    return rec;
  };

  // Bordo sinistro/destro della sagoma (px CSS) tra le quote y0..y1, dal profilo pre-calcolato (64 fasce).
  T.silhouette = (rec, y0, y1) => {
    const p = rec.profile;
    if (!p || !p.left) return { left: rec.left, right: rec.left + rec.dw };
    const n = p.left.length;
    let L = Infinity, R = -Infinity;
    for (let i = 0; i < n; i++) {
      const by0 = rec.top + (i / n) * rec.dh, by1 = rec.top + ((i + 1) / n) * rec.dh;
      if (by1 < y0 || by0 > y1 || p.left[i] < 0) continue;
      L = Math.min(L, rec.left + p.left[i] * rec.dw);
      R = Math.max(R, rec.left + p.right[i] * rec.dw);
    }
    return { left: L === Infinity ? T.W : L, right: R === -Infinity ? 0 : R };
  };

  const inter = (a, b) => {
    const x = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
    const y = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    return x * y;
  };

  T.metrics = () => {
    const texts = [...document.querySelectorAll('[data-role="text"]')].filter((e) => e.textContent.trim());
    const out = { texts: [], heroes: [], checks: {}, warnings: [], errors: [] };
    let nogoHit = 0, trHit = 0, outside = 0, faceHit = 0;
    for (const e of texts) {
      const cs = getComputedStyle(e);
      const fsz = parseFloat(cs.fontSize);
      const fam = cs.fontFamily.split(',')[0].replace(/["']/g, '').trim();
      const cap = T.capRatio(fam, cs.fontWeight) * fsz;
      const lines = T.inkRects(e);
      const nLines = T.lineRects(e).length;
      const kind = e.dataset.kind || 'hook';
      const rec = { kind, text: e.textContent, font: fam, weight: cs.fontWeight, size: +fsz.toFixed(1),
        cap_px: +cap.toFixed(1), lines: nLines, rects: lines.map((q) => [q.x, q.y, q.w, q.h].map((v) => +v.toFixed(1))),
        fit: e.dataset.fit ? JSON.parse(e.dataset.fit) : null };
      // font davvero caricato (i font mancanti cadono in silenzio su un ripiego)
      const fams = [fam, ...[...e.querySelectorAll('*')].map((c) => getComputedStyle(c).fontFamily.split(',')[0].replace(/["']/g, '').trim())];
      const loaded = new Set([...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, '')));
      rec.fonts_ok = [...new Set(fams)].every((f) => loaded.has(f) || /^(serif|sans-serif|monospace|system-ui)$/.test(f));
      if (!rec.fonts_ok) out.errors.push(`font non caricato nel testo "${e.textContent.slice(0, 24)}" (${[...new Set(fams)].join(', ')})`);
      // righe del gancio (solo glifi, senza i box di sfondo) come le misura un OCR: altezza / H, riga con la parola chiave
      if (kind === 'hook') {
        // rettangoli dei glifi della parola chiave (letti da yt-thumb-qa: keyword_rects, spazio CSS 1280×720)
        rec.keyword_rects = [...e.querySelectorAll('.hl')].flatMap((h) => T.inkRects(h, { boxes: false }))
          .map((q) => [q.x, q.y, q.w, q.h].map((v) => +v.toFixed(1)));
        const hls = [...e.querySelectorAll('.hl')].flatMap((h) => [...h.getClientRects()]);
        rec.rows = T.inkRects(e, { boxes: false, bare: true }).map((q) => ({ y: +q.y.toFixed(1), h: +q.h.toFixed(1), frac: +(q.h / T.H).toFixed(4),
          keyword: hls.some((r) => { const c = (r.top + r.bottom) / 2; return c >= q.y - 2 && c <= q.y + q.h + 2; }) }));
      }
      out.texts.push(rec);
      for (const q of lines) {
        nogoHit += inter(q, T.zones.nogo); trHit += inter(q, T.zones.topRight);
        if (q.x < -1 || q.y < -1 || q.x + q.w > T.W + 1 || q.y + q.h > T.H + 1) outside++;
        for (const h of T._heroes) faceHit += inter(q, h.faceRect);
      }
      if (kind === 'hook' && cap < 86) out.warnings.push(`cap height gancio ${cap.toFixed(0)} px < 86 px (12% di 720)`);
      if (kind === 'hook' && nLines > 3) out.warnings.push(`gancio su ${nLines} righe (> 3)`);
      if (kind !== 'hook' && kind !== 'meta' && kind !== 'label' && cap < 22) out.warnings.push(`testo "${e.textContent.slice(0, 20)}" troppo piccolo (${cap.toFixed(0)} px cap): illeggibile a 168 px`);
    }
    for (const h of T._heroes) {
      const fr = h.faceRect;
      out.heroes.push({ face: [fr.x, fr.y, fr.w, fr.h].map((v) => +v.toFixed(1)), scale: +h.s.toFixed(4),
        rect: [h.left, h.top, h.dw, h.dh].map((v) => +v.toFixed(1)), face_frac: +(fr.h / T.H).toFixed(3) });
      if (inter(fr, T.zones.nogo) > 0) out.warnings.push('volto nella zona del timestamp (in basso a destra)');
      if (fr.y < 0 || fr.x < 0 || fr.x + fr.w > T.W) out.warnings.push('volto tagliato dal bordo');
    }
    out.checks = { nogo_clear: nogoHit === 0, top_right_clear: trHit === 0, text_inside: outside === 0, face_clear: faceHit === 0 };
    if (nogoHit) out.errors.push('testo nella zona del timestamp (230×110 in basso a destra)');
    if (outside) out.errors.push('testo fuori dal quadro');
    if (trHit) out.warnings.push('testo nella zona hover in alto a destra (120×80)');
    if (faceHit) out.warnings.push('testo sopra un volto');
    return out;
  };

  T._fail = (msg) => { window.__TT_DONE__ = { ok: false, error: String(msg) }; };

  document.addEventListener('DOMContentLoaded', async () => {
    try {
      // Variabili CSS dai token del brand (colors.* → --nome, fonts.display/body → --font-*).
      const root = document.documentElement.style;
      for (const [k, v] of Object.entries((T.tokens.colors) || {})) root.setProperty('--' + k.replace(/_/g, '-'), v);
      const f = T.tokens.fonts || {};
      if (f.display) root.setProperty('--font-display', `"${f.display.family}"`);
      if (f.body) root.setProperty('--font-body', `"${f.body.family}"`);
      if (f.mono) root.setProperty('--font-mono', `"${f.mono.family}"`);
      // Font locali (file://) — Chrome lanciato con --allow-file-access-from-files.
      const css = (cfg.fonts || []).map((ft) =>
        `@font-face{font-family:"${ft.family}";src:url("${ft.url}");font-weight:${ft.weight || '100 900'};font-style:normal;font-display:block}`).join('\n');
      const base = '.arr{display:inline-block;width:.86em;height:.56em;vertical-align:.04em;margin:0 .04em}.arr svg{width:100%;height:100%;display:block}';
      const st = document.createElement('style'); st.textContent = css + '\n' + base; document.head.prepend(st);
      await Promise.all((cfg.fonts || []).map((ft) => document.fonts.load(`${String(ft.weight || '400').split(' ').pop()} 40px "${ft.family}"`)));
      await document.fonts.ready;
      if (!T._builder) throw new Error('il template non ha chiamato TT.ready()');
      const imgs = [...document.images];
      await T._builder(T.spec, T);
      await Promise.all([...document.images].map((i) => (i.complete ? (i.naturalWidth ? null : Promise.reject(new Error('immagine non caricata: ' + i.src))) : i.decode())));
      if (T._after) await T._after();
      window.__TT_DONE__ = { ok: true, metrics: T.metrics() };
    } catch (e) {
      T._fail(e && e.stack ? e.stack : e);
    }
  });
}

// ── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  const jobsPath = process.argv[2];
  if (!jobsPath) { log('uso: node render_html.mjs JOBS.json'); process.exit(64); }
  const cfg = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));
  const vw = cfg.viewport?.w || 1280, vh = cfg.viewport?.h || 720, scale = cfg.scale || 3;
  const withUrl = (list) => (list || []).map((f) => ({ ...f, url: pathToFileURL(f.file).href }));
  const fonts = withUrl(cfg.fonts);
  const t0 = Date.now();
  const browser = await chromium.launch({
    channel: 'chrome', headless: true,
    args: ['--allow-file-access-from-files', '--font-render-hinting=none', '--disable-lcd-text', '--force-color-profile=srgb'],
  });
  const context = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: scale });
  const results = [];
  for (const job of cfg.jobs || []) {
    const t1 = Date.now();
    const page = await context.newPage();
    const consoleErr = [];
    page.on('pageerror', (e) => consoleErr.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') consoleErr.push(m.text()); });
    try {
      const brand = { slug: job.brand || null, dir: job.brand_dir ? pathToFileURL(job.brand_dir).href.replace(/\/?$/, '/') : null };
      await page.addInitScript(ttRuntime, { spec: job.spec, tokens: job.tokens || {}, fonts: job.fonts ? withUrl(job.fonts) : fonts,
        vw, vh, brand });
      const common = commonSource(job.common_js);
      if (common) await page.addInitScript({ content: common });
      await page.goto(pathToFileURL(job.template).href, { waitUntil: 'load' });
      await page.waitForFunction(() => window.__TT_DONE__, null, { timeout: 20000 });
      const done = await page.evaluate(() => window.__TT_DONE__);
      if (!done.ok) throw new Error(done.error);
      fs.mkdirSync(path.dirname(job.out), { recursive: true });
      await page.screenshot({ path: job.out, type: 'png', scale: 'device', animations: 'disabled', caret: 'hide' });
      // face_pixels_unchanged (policy v2, livello 1): gli stessi riquadri dei volti con gli strati .tt-under nascosti
      // (disco, alone, contorno, scena del pop-out). yt-thumb-render li confronta col render sui pixel opachi del volto.
      let fx = null;
      if (job.fx_check) {
        const clips = await page.evaluate(() => TT._heroes.map((h) => {
          const f = h.faceRect, m = 0.12;
          const x0 = Math.max(0, Math.floor(f.x - f.w * m)), y0 = Math.max(0, Math.floor(f.y - f.h * m));
          const x1 = Math.min(TT.W, Math.ceil(f.x + f.w * (1 + m))), y1 = Math.min(TT.H, Math.ceil(f.y + f.h * (1 + m)));
          return { x: x0, y: y0, width: Math.max(1, x1 - x0), height: Math.max(1, y1 - y0) };
        }));
        const nUnder = await page.evaluate(() => { const u = document.querySelectorAll('.tt-under'); u.forEach((e) => { e.dataset.vis = e.style.visibility; e.style.visibility = 'hidden'; }); return u.length; });
        const files = [];
        for (let i = 0; i < clips.length; i++) {
          const f = job.out.replace(/\.png$/, `.nofx${i}.png`);
          await page.screenshot({ path: f, type: 'png', scale: 'device', clip: clips[i], animations: 'disabled', caret: 'hide' });
          files.push(f);
        }
        await page.evaluate(() => document.querySelectorAll('.tt-under').forEach((e) => { e.style.visibility = e.dataset.vis || ''; }));
        fx = { clips, files, under: nUnder };
      }
      if (job.debug_out) {
        await page.evaluate(() => {
          document.documentElement.classList.add('tt-debug');
          const box = (r, color, label) => {
            const d = document.createElement('div');
            Object.assign(d.style, { position: 'absolute', left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px',
              outline: `3px dashed ${color}`, zIndex: 9999, font: '600 14px sans-serif', color, pointerEvents: 'none' });
            d.textContent = label || '';
            document.body.appendChild(d);
          };
          box(TT.zones.nogo, 'red', 'timestamp'); box(TT.zones.topRight, 'orange', 'hover');
          TT._heroes.forEach((h) => box(h.faceRect, 'cyan', 'volto'));
          document.querySelectorAll('[data-role="text"]').forEach((e) => TT.inkRects(e).forEach((q) => box(q, 'magenta')));
        });
        await page.screenshot({ path: job.debug_out, type: 'png', scale: 'css' });
      }
      results.push({ id: job.id, out: job.out, ok: true, ms: Date.now() - t1, metrics: done.metrics, console: consoleErr, fx });
      log(`[render] ${job.id} → ${path.basename(job.out)} (${Date.now() - t1} ms)`);
    } catch (e) {
      results.push({ id: job.id, out: job.out, ok: false, error: String(e.message || e).slice(0, 2000), console: consoleErr });
      log(`[render] ${job.id} ERRORE: ${String(e.message || e).split('\n')[0]}`);
    } finally {
      await page.close();
    }
  }
  await browser.close();
  process.stdout.write(JSON.stringify({ ok: results.every((r) => r.ok), ms: Date.now() - t0, results }, null, 2) + '\n');
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e.stack || e) }) + '\n');
  process.exit(1);
});
