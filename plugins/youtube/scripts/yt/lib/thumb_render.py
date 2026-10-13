"""yt-thumb-render — rende i concept di thumbnail da template HTML (o Remotion) a PNG 3840×2160 + JPEG < 2 MB.

Flusso per ogni concept:
  1. asset reali: ritaglio del soggetto (thumbvision cutout, se il concept dà `frame` e non `cutout`),
     box del volto e profilo della sagoma (per non scrivere sopra la persona);
  2. spec → node/render_html.mjs (Playwright + Chrome di sistema, 1280×720 @ DPR 3);
  3. controlli: zona timestamp, testo fuori quadro, cap height, parole, coppie colore ammesse,
     ripetizioni titolo↔thumbnail, testo sopra il soggetto; sul PNG reso: bordi dritti del ritaglio visibili dentro il
     canvas (07 §11, errore), upscale vs sorgente > 2.0× (errore), altezza del volto, frangia calda/alone sul bordo dei
     capelli, grafica del telaio (dischi, forme) nelle zone vietate o sul volto, simbolo del logo sotto il minimo;
     i controlli che 07 §12.4 vuole bloccanti (cap < 86 px, > 4 parole, > 3 righe, testo sul volto, coppia vietata)
     sono errori, non avvisi;
  4. JPEG < 2 MB (Pillow, qualità decrescente); con --spotify anche <nome>_spotify-1920x1080.png.

Template inclusi (node/templates): duo, ritratto, scena, prova (telaio di serie v2, codice comune _common.js) e generic
(campo pieno, token a runtime). Ogni elemento di brand (palette, font, wordmark, simbolo) viene dai token del brand:
--brand / --tokens, altrimenti il brand del canale (profilo, brand.slug o la cartella <brands_dir>/<canale>/), altrimenti il
brand neutro «demo» del plugin. Un brand può sostituire un template incluso con <brands_dir>/<slug>/templates/<slug>-<nome>.html
(es. acme-duo.html vince su duo per il brand acme) o aggiungerne di propri (<slug>-*.html, scelti col nome completo).
Un template esterno può usare file relativi alla sua cartella (../fonts, ../logo: Chrome gira con accesso ai file locali)
e TT.asset('logo/x.svg') → URL del file nella cartella del brand; i font in <brand>/fonts sono caricati come @font-face.

Contratto del concept (thumbs/concepts.json, knowledge/07-thumbnails.md §1.1; `text`/`highlight` restano validi):
  id, lever (claim|proof|duo|name), template, hook (3–6 parole, frase completa: soggetto + verbo, oppure numero + unità
  verificato), keyword, accent (un accento del brand | auto), people [{cutout|frame, role: guest|host, name, title}],
  meta_line («EVENTO / ANNO»), format_label, show_logo (true | "wordmark" | "symbol" | false), guest_style (none|graphic),
  grade (natural | mono), plate {source: scene|flat|prop, path?, grade?, bokeh?, ev?}, prop {prompt, slot, path?},
  expression_class, payoff_at, title_pair, person_tone (none|look|duo), upscale_override / face_floor_reason /
  detail_reason / hook_size_reason (motivi scritti per il G2).
Default dal profilo del canale (blocco `thumbnails`, se c'è; il canale viene da --channel, dal campo `channel` del concept,
dal project.json del workdir di --data o dall'unico profilo dei channels_dirs): default_template, grade_default (stringa o
{template: grade, others: grade}), accent (auto), guest_style_default (none), display_cap (c = 2.0 | b = 1.5 | numero),
format_label, show_logo, host_tag, props_budget. Senza profilo: grade natural, accent auto, guest_style none, tetto 2.0.
mono = livello 2b, grade monocromatico uniforme: la stessa curva (<brand>/mono-curve.json, lib/thumb_fx.py) su ogni pixel di
tutte le persone e della plate (la plate può in più essere sfocata, scurita, vignettata); il ΔE00 della pelle non si
applica e lo sostituiscono la coerenza della mappatura (≤ 2 livelli dalla curva) e i landmark MediaPipe invariati.
`accent: auto` = tra gli accenti del brand (tokens.accents_auto, altrimenti tokens.accents) quello con più stacco ΔL* da
capelli e volto della persona davanti al cerchio, misurato sul ritaglio graduato (duo e ritratto; negli altri template
l'accento di default del brand). duo: titolo di 3–4 parole, ogni riga ≥ 20 % dell'altezza; `circle_behind` = disco
d'accento di campo dietro l'ospite (può passare sotto le icone hover: è una massa di fondo); `host_tag` (default «con
<nome dell'host>»); stacco dal feed scuro misurato (edge_dL_dark ≥ 25 o elemento chiaro di cornice).
Controlli v2 (oltre ai precedenti): tetto al display (volto a 1280 px ≤ 2.0× la sua risoluzione effettiva, --display-cap 1.5
per l'opzione b), dettaglio del volto nel file servito 720×405 (avviso < 713, errore < 569), stacco volto–intorno (errore
< 10, avviso < 20), silhouette a 246 px (avviso < 25 con guest_style graphic), face_pixels_unchanged (0 pixel opachi del
volto cambiati dagli strati sotto il ritaglio), pelle ΔE00 ≤ 2.5 / p95 ≤ 5 dopo il tono (livello 2), buchi del matte nel
volto, un solo accento, credenziale dell'ospite, righe del titolo ≥ 12% (parola chiave ≥ 18%), volto ≥ 35% sui claim
(≥ 30% nel duo).
Codice di uscita: 0 = tutto ok; 3 = render prodotti ma qualche controllo fallito; 1 = render non prodotti.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402

TEMPLATES_DIR = yc.NODE_DIR / "templates"
RENDER_JS = yc.NODE_DIR / "render_html.mjs"
COMMON_JS = TEMPLATES_DIR / "_common.js"
NODE = yc.node_bin() or shutil.which("node") or "/opt/homebrew/bin/node"
JPEG_MAX = 1_950_000            # margine sotto i 2 MB dell'upload da mobile
VIEW_W, VIEW_H, SCALE = 1280, 720, 3
DEFAULT_BRAND = getattr(yc, "BUILTIN_BRAND", "demo")   # brand neutro del plugin (assets/brands/demo)

MAX_UPSCALE = 2.0               # 07 §10.1: interpolazione ≤ 2.0× su qualunque volto (vs il frame sorgente)
FACE_FRAC_MIN, FACE_FRAC_WARN = 0.20, 0.30   # < 20%: volto < 19 px a 168 → errore; < 30%: sotto i podcast di riferimento (mediana 35.5%)
FRINGE_WARN, FRINGE_ERR, RIM_WARN = 12.0, 25.0, 4.0   # bordo grezzo 30–44, decontaminato 2–8 (×255)
SYMBOL_MIN_CSS = 46.7           # simbolo del logo: minimo 140 px a 4K

# ── telaio v2 ──
V2_TEMPLATES = ("duo", "ritratto", "scena", "prova")
V2_CLAIM = ("ritratto", "scena")                # volto principale ≥ 35% (errore), ≥ 40% (obiettivo)
BUILTIN_TEMPLATES = V2_TEMPLATES + ("generic",)
DISPLAY_CAP = 2.0               # tetto (c): volto a 1280 px ≤ 2.0× la risoluzione effettiva; (b) = 1.5 con --display-cap 1.5
DISPLAY_CAPS = {"c": 2.0, "b": 1.5}
FACE_V2_ERR, FACE_V2_WARN, FACE_DUO_MIN = 0.35, 0.40, 0.30
SERVED_WARN, SERVED_ERR = 713.0, 569.0           # Laplaciano del volto nel file 720×405: p25 / p10 dei riferimenti
SURROUND_ERR, SURROUND_WARN = 10.0, 20.0         # stacco volto–intorno ΔL* (podcast di riferimento: p10 10, p25 20)
SILHOUETTE_WARN = 25.0          # silhouette a 246 px con guest_style graphic (solo avviso finché non è calibrata)
HOOK_ROW_MIN, HOOK_KEY_MIN = 0.12, 0.18          # altezza di riga (glifi) / H: frase ≥ 12%, parola chiave ≥ 18%
HOLE_ERR = 0.003                # buchi del matte nell'ellisse del volto: > 0.3% dei pixel → errore
PROP_CAP_EUR = {"episode": 5, "month": 20}       # props/plate da solo testo: tetto di spesa di default (profilo: props_budget)
GRADES = ("mono", "natural")                     # mono = livello 2b (grade monocromatico uniforme su persone e plate)
GRADE_DEFAULT = "natural"                        # senza profilo: pixel veri; mono è un'opzione (concept o profilo)
GUEST_STYLES = ("none", "graphic")
DUO_WORDS_MAX = 4                                # duo: 3–4 parole (titolo enorme)
DUO_ROW_MIN, DUO_ROW_TARGET = 0.20, 0.22         # duo: ogni riga ≥ 20 % (errore, come yt-thumb-qa); obiettivo 22 %
EDGE_DARK_MIN, EDGE_LIGHT_SHARE = 25.0, 0.10     # stacco dal feed scuro: ΔL* ≥ 25 o un tratto chiaro continuo ≥ 10 % del perimetro
MAP_TOL_LEVELS = 2                               # 2b: scarto massimo dalla curva analitica (livelli a 8 bit)
CURVE_GAP_MAX = 2.0                              # 2b: scarto tra le curve misurate di due persone (livelli di luma)

KNOWN_FONTS = {"Inter": "Inter", "Anton": "Anton"}
FONT_EXT = (".ttf", ".otf", ".woff", ".woff2")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")

STOPWORDS_IT = set("""a ad al alla alle allo agli ai anche che chi ci come con cosa da dal dalla dei del della delle
dello di e ed è gli ha hai ho i il in io la le lo l lui ma mi ne nei nel nella noi non o per più poi se si sono su
sul sulla tra tu un una uno vs the and of to la le lo""".split())


# ── Utilità ─────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="yt-thumb-render",
        description="Rende thumbnail 3840×2160 (PNG master + JPEG < 2 MB) da concept JSON con template HTML guidati dai token del brand.",
        epilog="""Template inclusi (telaio di serie v2: titolo condensato + punto d'accento, targhetta nome+ruolo, riga meta, wordmark o
          simbolo del brand, etichetta di formato): duo (due persone, disco d'accento dietro l'ospite),
          ritratto (claim: ospite testa-spalle ~40%), scena (pop-out dalla scena vera dell'ospite), prova (artefatto reale
          autorizzato); generic (campo pieno, token a runtime). Un brand può sostituirli o aggiungerne:
          <brands_dir>/<slug>/templates/<slug>-<nome>.html. Remotion: solo brand propri e solo i template non v2.
Brand: --brand / --tokens, altrimenti quello del canale (--channel, campo channel del concept, project.json del workdir),
altrimenti il brand neutro «demo» del plugin (palette e wordmark segnaposto da sostituire).
Ritagli: meglio quelli di yt-portrait cut (già alla misura finale, disegnati 1:1, bordi dritti dichiarati).

Concept (campi principali; il resto passa al template):
  id, template, hook | text (3–6 parole, '|' = a capo), keyword | highlight (parola nel box),
  people [{cutout | frame (+ roi "x,y,w,h" | "inset" | "wide" | nome del layout del brand, point "x,y", exclude "pip"),
  role guest|host, name, title}] · oppure cutout / frame a livello di concept (una persona) ·
  artifact (schermata reale per prova) · accent, face_frac, face_cx, face_cy, meta_line, format_label, show_logo,
  host_tag (duo), circle_behind (duo), disc (ritratto: paper|accent), grade natural|mono, grade_curve {points} (solo prove),
  guest_style none|graphic, plate {source: scene|flat|prop, path, grade, ev, bokeh}, prop {prompt, slot, path},
  person_tone none|look|duo, display_cap, motivi scritti (upscale_override, face_floor_reason, detail_reason,
  hook_size_reason, hook_override), number_verified, artifact_source (prova), hook_form contro, title_pair,
  variants [{...override}], tokens (solo generic: token a runtime), brand, channel.
  Richieste di prop senza file → <out>/prop_requests.json (nessuna chiamata a pagamento: OK nella sessione principale).
Uscita: 0 = render e controlli ok; 3 = render prodotti con controlli falliti; 1 = render non prodotti.

Esempio:
  yt-thumb-render --data thumbs/concepts.json --out thumbs/renders --debug
  yt-thumb-render --template ritratto --data '{"id":"A","hook":"Ho lasciato tutto","keyword":"tutto","cutout":"p.png"}' --out /tmp/t
""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--template", default="auto",
                   help="template da usare per tutti i concept (default: 'auto' = campo 'template' di ogni concept, poi "
                        "default_template del profilo)")
    p.add_argument("--data", required=True, help="file JSON dei concept (lista, oggetto singolo o {'concepts': [...]}) o JSON inline")
    p.add_argument("--out", required=True, help="cartella di output (PNG, JPEG, cutouts/, render.json)")
    p.add_argument("--engine", choices=["html", "remotion"], default="html", help="motore di render (default html)")
    p.add_argument("--only", help="solo questi id concept, separati da virgola")
    p.add_argument("--channel", help="canale (profilo <slug>.md nei channels_dirs) per brand e default delle thumbnail")
    p.add_argument("--brand", help="slug brand per token, font e logo (default: brand del canale, poi demo)")
    p.add_argument("--tokens", help="file tokens.json esplicito (sovrascrive i token del brand)")
    p.add_argument("--debug", action="store_true", help="salva anche <nome>_debug.png con zone vietate, volti e righe di testo")
    p.add_argument("--force", action="store_true", help="rifà anche se gli output sono più recenti degli input")
    p.add_argument("--spotify", action="store_true", help="scrive anche <nome>_spotify-1920x1080.png (Lanczos dal master)")
    p.add_argument("--max-upscale", type=float, default=MAX_UPSCALE,
                   help="cap dell'upscale dei volti vs la sorgente per i ritagli SENZA risoluzione effettiva (07 §10.1: 2.0)")
    p.add_argument("--display-cap", type=float, default=None,
                   help="volto a 1280 px ≤ N× la sua risoluzione effettiva (eff_face_px di yt-portrait); 2.0 = opzione (c), "
                        "1.5 = ripiego (b). Default: display_cap del profilo, altrimenti 2.0. Un concept può fissarlo con display_cap")
    return p.parse_args()


def load_concepts(data: str) -> tuple[list[dict], Path | None]:
    text = data.strip()
    if text.startswith("{") or text.startswith("["):
        obj, src = json.loads(text), None
    else:
        src = Path(data).expanduser().resolve()
        if not src.exists():
            yc.fail(f"--data: file non trovato: {src}")
        obj = yc.read_json(src)
    if isinstance(obj, dict):
        obj = obj.get("concepts", [obj])
    if not isinstance(obj, list) or not obj:
        yc.fail("--data: nessun concept (serve una lista o un oggetto con 'text')")
    return obj, src


def resolve_path(p: str | None, base: Path | None) -> Path | None:
    if not p:
        return None
    q = Path(str(p)).expanduser()
    if not q.is_absolute() and base is not None:
        q = (base / q)
    return q.resolve()


# ── Canale, profilo e default delle thumbnail ───────────────────────────────
def _placeholder(v) -> bool:
    """Valore non compilato del modello di profilo («[DA COMPILARE]», «con [Nome dell'host]», «<slug>», stringa vuota)."""
    return isinstance(v, str) and (not v.strip() or bool(re.search(r"\[[^\]]*\]|<[^>]*>", v)))


def channel_of(data_src: Path | None, concept: dict | None = None, override: str | None = None) -> str | None:
    """Canale: --channel, poi il campo `channel` del concept, poi project.json del workdir che contiene il file --data
    (fino a 3 livelli sopra), poi l'unico profilo dei channels_dirs. None = nessun profilo (default generici)."""
    if override:
        return override
    if concept and concept.get("channel"):
        return str(concept["channel"])
    if data_src is not None:
        for d in list(data_src.parents)[:3]:
            pj = d / "project.json"
            if pj.is_file():
                try:
                    ch = yc.read_json(pj).get("channel")
                except Exception:  # noqa: BLE001
                    ch = None
                if ch:
                    return str(ch)
                break
    fn = getattr(yc, "default_channel", None)
    try:
        return fn() if callable(fn) else None
    except Exception:  # noqa: BLE001
        return None


_PROFILES: dict = {}


def channel_profile(channel: str | None) -> dict:
    """Frontmatter del profilo del canale ({} se manca o non si legge: si usano i default generici)."""
    if not channel:
        return {}
    if channel not in _PROFILES:
        try:
            _PROFILES[channel] = yc.load_channel(channel)
        except Exception:  # noqa: BLE001
            _PROFILES[channel] = {}
    return _PROFILES[channel]


def thumb_defaults(profile: dict) -> dict:
    """Default delle thumbnail dal blocco `thumbnails` del profilo, normalizzati (chiavi assenti = default generici)."""
    t = profile.get("thumbnails") if isinstance(profile.get("thumbnails"), dict) else {}
    out: dict = {}
    dt = t.get("default_template")
    if isinstance(dt, str) and not _placeholder(dt):
        out["default_template"] = dt.strip()
    gd = t.get("grade_default", t.get("grade"))
    if isinstance(gd, (str, dict)) and not _placeholder(gd):
        out["grade_default"] = gd
    acc = t.get("accent_default", t.get("accent"))
    if isinstance(acc, str) and not _placeholder(acc):
        out["accent"] = acc.strip()
    gs = t.get("guest_style_default", t.get("guest_style"))
    if isinstance(gs, str) and gs in GUEST_STYLES:
        out["guest_style"] = gs
    dc = t.get("display_cap")
    if isinstance(dc, (int, float)) and dc > 0:
        out["display_cap"] = float(dc)
    elif isinstance(dc, str) and dc.strip().lower() in DISPLAY_CAPS:
        out["display_cap"] = DISPLAY_CAPS[dc.strip().lower()]
    for k in ("format_label", "host_tag"):
        if isinstance(t.get(k), str) and not _placeholder(t[k]):
            out[k] = t[k]
    if t.get("show_logo") in (True, False, "wordmark", "symbol"):
        out["show_logo"] = t["show_logo"]
    for k in ("grade_allowed", "guest_style_allowed", "accents"):
        v = t.get(k)
        if isinstance(v, list) and v and all(isinstance(x, str) and not _placeholder(x) for x in v):
            out[k] = [x.strip() for x in v]
    pb = t.get("props_budget")
    if isinstance(pb, dict):
        out["props_budget"] = {"episode": pb.get("per_episode_eur", PROP_CAP_EUR["episode"]),
                               "month": pb.get("per_month_eur", PROP_CAP_EUR["month"])}
    return out


def grade_for(template: str, defaults: dict) -> str:
    """Grade di default del template: grade_default del profilo (stringa, o {template|others: grade}), altrimenti natural."""
    gd = defaults.get("grade_default")
    if isinstance(gd, dict):
        g = gd.get(base_template(template)) or gd.get(template) or gd.get("others")
    else:
        g = gd
    g = str(g or GRADE_DEFAULT).lower()
    return g if g in GRADES else GRADE_DEFAULT


def apply_defaults(c: dict, template: str, defaults: dict) -> dict:
    """Campi del concept mancanti ← default del profilo (solo per il telaio v2; il concept vince sempre)."""
    if base_template(template) not in V2_TEMPLATES:
        return c
    c = dict(c)
    c.setdefault("grade", grade_for(template, defaults))
    c.setdefault("accent", defaults.get("accent", "auto"))
    c.setdefault("guest_style", defaults.get("guest_style", "none"))
    for k in ("format_label", "show_logo", "host_tag"):
        if k in defaults and k not in c:
            c[k] = defaults[k]
    if "display_cap" in defaults and "display_cap" not in c:
        c["display_cap"] = defaults["display_cap"]
    return c


# ── Template e brand ────────────────────────────────────────────────────────
def _external_brand_dirs() -> list[Path]:
    """Cartelle dei brand esterni (in ordine di brands_dirs; il plugin escluso)."""
    out: list[Path] = []
    for d in yc.BRANDS_DIRS:
        try:
            if d.resolve() == yc.BRANDS.resolve():
                continue
            out += [c for c in sorted(d.iterdir()) if c.is_dir() and (c / "tokens.json").is_file()]
        except OSError:
            continue
    return out


def base_template(name: str | None) -> str:
    """Nome del template incluso che un template fa: «duo» per duo e per <slug>-duo (variante di un brand); altrimenti il
    nome stesso. Decide le regole (v2, claim, duo) e i controlli."""
    n = str(name or "")
    if n in BUILTIN_TEMPLATES:
        return n
    # ultimo segmento: lo slug del brand può contenere trattini («caffe-maker-duo» → «duo»), come thumb_learn.v2_base
    head, sep, tail = n.rpartition("-")
    if sep and head and tail in BUILTIN_TEMPLATES:
        return tail
    return n


def find_template(name: str, brand: str | None = None) -> Path | None:
    """Template HTML. Un nome incluso (duo, ritratto, scena, prova, generic): prima la variante del brand
    <brands_dir>/<brand>/templates/<brand>-<nome>.html, poi node/templates/<nome>.html. Un nome <slug>-…: solo nella cartella
    del brand <slug> (o, se il prefisso non è un brand, negli altri brand esterni). Altri nomi: None (sconosciuto)."""
    if not name or not NAME_RE.fullmatch(name):
        return None
    ext = _external_brand_dirs()
    if name in BUILTIN_TEMPLATES:
        if brand:
            for bd in ext:
                if bd.name == brand and (bd / "templates" / f"{brand}-{name}.html").is_file():
                    return bd / "templates" / f"{brand}-{name}.html"
        p = TEMPLATES_DIR / f"{name}.html"
        return p if p.is_file() else None
    # prima il brand il cui slug è il prefisso del nome (lo slug può contenere trattini), poi gli altri brand esterni
    own = sorted((bd for bd in ext if name.startswith(bd.name + "-")), key=lambda bd: -len(bd.name))
    cands = [bd / "templates" / f"{name}.html" for bd in own]
    cands += [bd / "templates" / f"{name}.html" for bd in ext if bd not in own]
    return next((c for c in cands if c.is_file()), None)


def available_templates() -> list[str]:
    names = {n for n in BUILTIN_TEMPLATES if (TEMPLATES_DIR / f"{n}.html").is_file()}
    for bd in _external_brand_dirs():
        names |= {p.stem for p in (bd / "templates").glob(f"{bd.name}-*.html")}
    return sorted(names)


def template_brand_dir(tpl: Path | None) -> Path | None:
    """Cartella del brand esterno che contiene il template (None per i template del plugin)."""
    if tpl is None:
        return None
    parent = tpl.parent
    return parent.parent if parent.name == "templates" and (parent.parent / "tokens.json").is_file() else None


def brand_of(template: str, override: str | None, tpl: Path | None = None, concept: dict | None = None,
             channel: str | None = None) -> str:
    """Brand dei token: --brand, poi la cartella del template esterno, poi il campo `brand` del concept, poi il brand del
    canale (brand.slug del profilo o la cartella col nome del canale), poi il brand neutro del plugin."""
    if override:
        return override
    bd = template_brand_dir(tpl)
    if bd is not None:
        return bd.name
    if concept and concept.get("brand") and yc.brand_dir(str(concept["brand"])):
        return str(concept["brand"])
    if channel:
        fn = getattr(yc, "channel_brand", None)
        if callable(fn):
            try:
                return fn(channel)
            except Exception:  # noqa: BLE001
                pass
        if yc.brand_dir(channel):
            return channel
    return DEFAULT_BRAND


def load_tokens(brand: str, tokens_file: str | None, concept: dict) -> dict:
    if tokens_file:
        return yc.read_json(Path(tokens_file).expanduser())
    if isinstance(concept.get("tokens"), dict) and concept["tokens"].get("colors"):
        return concept["tokens"]
    return yc.brand_tokens(brand) or yc.brand_tokens(DEFAULT_BRAND)


def accent_names(tokens: dict) -> list[str]:
    """Accenti del brand (tokens.accents, altrimenti tokens.accent, altrimenti i colori non neutri)."""
    import thumb_fx as fx
    return fx.accent_names(tokens)


def default_accent(tokens: dict) -> str | None:
    names = accent_names(tokens)
    acc = tokens.get("accent")
    return acc if acc in names else (names[0] if names else None)


def plate_box_name(tokens: dict, accent: str | None) -> str:
    """Box del nome sotto la targhetta: l'accento se l'inchiostro ci sta sopra con contrasto ≥ 7:1, altrimenti carta
    (stessa regola di KIT.plateBox in node/templates/_common.js)."""
    c = tokens.get("colors", {})
    if accent and c.get(accent) and c.get("ink") and contrast(c["ink"], c[accent]) >= 7:
        return accent
    return "paper"


def palette_of(tokens: dict) -> dict:
    """Palette del brand per il sidecar (yt-thumb-qa: colore degli accenti, inchiostro, carta)."""
    c = tokens.get("colors", {})
    return {"ink": c.get("ink"), "paper": c.get("paper"), "default_accent": default_accent(tokens),
            "accents": {n: c[n] for n in accent_names(tokens) if n in c}}


def font_list(tokens: dict, brand: str | None = None, brand_dir: Path | None = None) -> list[dict]:
    """Font locali: assets/fonts del plugin, poi <brand>/fonts del brand esterno (dichiarati dopo: a parità di
    famiglia vincono). Famiglia dai token se citata, altrimenti dal nome file."""
    by_file = {}
    for f in (tokens.get("fonts") or {}).values():
        if isinstance(f, dict) and f.get("file"):
            by_file[f["file"]] = f.get("family")
    dirs = [yc.FONTS]
    bd = brand_dir or (yc.brand_dir(brand) if brand and brand != "client" and yc.brand_is_external(brand) else None)
    if bd and (bd / "fonts").is_dir():
        dirs.append(bd / "fonts")
    fonts = []
    for d in dirs:
        for path in sorted(d.glob("*")):
            if path.suffix.lower() not in FONT_EXT:
                continue
            stem = re.split(r"[-\[]", path.stem)[0]
            family = by_file.get(path.name) or KNOWN_FONTS.get(stem) or re.sub(r"(?<!^)([A-Z])", r" \1", stem)
            variable = "[" in path.name or "variable" in path.stem.lower()
            fonts.append({"family": family, "file": str(path), "weight": "100 900" if variable else "400"})
    return fonts


def mtime(p: Path | None) -> float:
    try:
        return p.stat().st_mtime if p else 0.0
    except FileNotFoundError:
        return 0.0


def thumbvision(*args: str) -> dict | list:
    if not yc.SWIFT_BIN.exists():
        raise RuntimeError(f"thumbvision non disponibile ({yc.SWIFT_BIN}): {yc.SETUP_HINT}")
    proc = yc.run([yc.SWIFT_BIN, *args], capture=True, check=False)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"thumbvision {args[0]}: output non JSON (exit {proc.returncode}): {proc.stderr[-500:]}")
    if isinstance(out, dict) and out.get("ok") is False:
        raise RuntimeError(f"thumbvision {args[0]}: {out.get('error')}")
    return out


# ── Asset: ritaglio + metadati (volto, sagoma) ──────────────────────────────
def layout_rect(brand: str, name: str, default: list | None, channel: str | None = None) -> list | None:
    """Rettangolo [x,y,w,h] in px dal layout del master (layout.json del brand o del canale, chiavi x/y/w/h; stesso
    risolutore di yt-clips e yt-portrait: ytcore.layout_file)."""
    layout = yc.layout_file(channel, brand)
    if layout.exists():
        r = yc.read_json(layout).get(name)
        if isinstance(r, dict) and all(k in r for k in ("x", "y", "w", "h")):
            return [r["x"], r["y"], r["w"], r["h"]]
        if isinstance(r, (list, tuple)) and len(r) == 4:
            return list(r)
    return default


def resolve_roi(roi, brand: str, channel: str | None = None) -> str | None:
    """ROI del ritaglio: "x,y,w,h" (px o 0–1), lista, "full" (tutto il frame) oppure un nome del layout del brand
    (inset, wide, …: <brand>/layout.json)."""
    if roi in (None, "", False):
        return None
    if isinstance(roi, str) and re.fullmatch(r"[a-z_]+", roi):
        if roi == "full":
            return None
        rect = layout_rect(brand, roi, None, channel)
        if rect is None:
            raise RuntimeError(f"roi '{roi}' non trovata nel layout {yc.layout_file(channel, brand)} (misuralo con "
                               "yt-clips layout --measure, oppure passa \"x,y,w,h\")")
        return ",".join(str(v) for v in rect)
    if isinstance(roi, (list, tuple)):
        return ",".join(str(v) for v in roi)
    return str(roi)


def _rect_px(text: str, W: int, H: int) -> list[float]:
    v = [float(x) for x in str(text).split(",")]
    return [v[0] * W, v[1] * H, v[2] * W, v[3] * H] if all(x <= 1 for x in v) else v


def resolve_exclude(person: dict, frame: Path, brand: str, roi: str | None, warnings: list,
                    channel: str | None = None) -> str | None:
    """Zone da escludere dal ritaglio. 'pip' = riquadro PiP del layout del brand (<brand>/layout.json, chiave pip): di
    default attivo sui frame della misura del canvas del layout quando la ROI (o il frame intero) lo interseca."""
    ex = person.get("exclude")
    pip = layout_rect(brand, "pip", None, channel)
    if ex is None and pip:
        from PIL import Image
        canvas = (yc.read_json(yc.layout_file(channel, brand)).get("canvas") or {})
        with Image.open(frame) as im:
            size = im.size
        if size == (canvas.get("w", 3840), canvas.get("h", 2160)):
            px, py, pw, ph = pip
            rx, ry, rw, rh = _rect_px(roi, *size) if roi else [0, 0, *size]
            if rx < px + pw and px < rx + rw and ry < py + ph and py < ry + rh:
                ex = "pip"
                msg = "PiP del layout escluso dal ritaglio (\"exclude\": [] per disattivare)"
                if msg not in warnings:
                    warnings.append(msg)
    if not ex:
        return None
    rects = ex if isinstance(ex, list) and ex and isinstance(ex[0], (list, str)) else [ex]
    out = []
    for r in rects:
        if r == "pip":
            if not pip:
                raise RuntimeError(f"exclude «pip»: il layout del brand {brand} non ha un riquadro pip")
            x, y, w, h = pip
            r = [x - 10, y - 10, w + 20, h + 14]   # margine: bordo arrotondato/antialias del riquadro
        out.append(",".join(str(v) for v in r) if isinstance(r, (list, tuple)) else str(r))
    return ";".join(out)


def cutout_meta(path: Path, force: bool = False, cache_dir: Path | None = None) -> dict:
    """Metadati del ritaglio: dimensioni, box alpha, profilo 64 fasce, volto.

    Il sidecar <png>.meta.json di `yt-portrait cut` (chiave "portrait": scala sulla sorgente, volto esatto, bordi
    dritti) è autorevole: si legge sempre, anche con --force e a prescindere dall'mtime (una copia può invertirlo),
    purché le misure coincidano col PNG, e non si riscrive mai. (Se con --force venisse sovrascritto senza "portrait",
    il ritaglio sarebbe ridisegnato a 1,08–1,21× e il cap 2,0× misurato sul ritaglio invece che sulla sorgente:
    2,16–2,42× reali passerebbero il controllo.)
    Altri ritagli: cache accanto al PNG solo se il PNG sta dentro cache_dir (cartella di uscita del render), altrimenti
    in <cache_dir>/.cutout_meta/: mai scritture nelle cartelle di lavoro da cui si leggono i ritagli."""
    import tempfile
    from PIL import Image
    import numpy as np

    side = path.with_suffix(".meta.json")
    portrait_side = False
    if side.exists():
        try:
            prev = yc.read_json(side)
        except Exception:  # noqa: BLE001 — sidecar illeggibile: si ricalcola nella cache
            prev = {}
        if prev.get("portrait"):
            portrait_side = True
            with Image.open(path) as im0:
                size = im0.size
            if (prev.get("w"), prev.get("h")) == size:
                return prev
            yc.log(f"[cutout] {side.name}: sidecar di yt-portrait per {prev.get('w')}×{prev.get('h')} ma il PNG è "
                   f"{size[0]}×{size[1]}: ignorato (rifai yt-portrait cut)")
        elif prev and not force and mtime(side) >= mtime(path):
            return prev
    cache = side
    outside = False
    if cache_dir is not None:
        try:
            path.resolve().relative_to(Path(cache_dir).resolve())
        except ValueError:
            outside = True
    if outside or portrait_side:
        base = Path(cache_dir) if cache_dir is not None else path.parent
        key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:10]
        cache = base / ".cutout_meta" / f"{path.stem}-{key}.meta.json"
        if cache.exists() and not force and mtime(cache) >= mtime(path):
            return yc.read_json(cache)
    im = Image.open(path)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    a = np.asarray(im.getchannel("A")) > 127
    h, w = a.shape
    ys, xs = np.where(a)
    if len(xs) == 0:
        raise RuntimeError(f"ritaglio vuoto (alpha tutto trasparente): {path}")
    alpha_box = [xs.min() / w, ys.min() / h, (xs.max() - xs.min() + 1) / w, (ys.max() - ys.min() + 1) / h]
    bands = 64
    left, right = [], []
    for i in range(bands):
        rows = a[int(i * h / bands): max(int((i + 1) * h / bands), int(i * h / bands) + 1)]
        cols = np.where(rows.any(axis=0))[0]
        left.append(round(float(cols.min()) / w, 4) if len(cols) else -1)
        right.append(round(float(cols.max() + 1) / w, 4) if len(cols) else -1)
    touches = {"left": bool(a[:, :2].any()), "right": bool(a[:, -2:].any()),
               "top": bool(a[:2].any()), "bottom": bool(a[-2:].any())}
    # Volto: thumbvision su una versione appiattita su grigio medio (alpha → sfondo neutro).
    flat = Image.new("RGB", im.size, (128, 128, 128))
    flat.paste(im, mask=im.getchannel("A"))
    face = None
    with tempfile.TemporaryDirectory(prefix="yt-cutout-") as td:   # mai file temporanei accanto al ritaglio
        tmp = Path(td) / f"{path.stem}.flat.jpg"
        flat.save(tmp, quality=92)
        res = thumbvision("faces", str(tmp))
        faces = res[0].get("faces", []) if res else []
        if faces:
            face = max(faces, key=lambda f: f["box"][2] * f["box"][3])["box"]
    meta = {"w": w, "h": h, "alpha_box": [round(v, 4) for v in alpha_box], "profile": {"left": left, "right": right},
            "touches": touches, "face": face, "face_detected": face is not None}
    if face is None:
        # Ripiego: testa ≈ parte alta della sagoma, centrata.
        ab = alpha_box
        meta["face"] = [ab[0] + ab[2] * 0.35, ab[1] + 0.02, ab[2] * 0.3, min(0.18, ab[3] * 0.15)]
    cache.parent.mkdir(parents=True, exist_ok=True)
    yc.write_json(cache, meta)
    return meta


def ensure_person(person: dict, base: Path | None, outdir: Path, brand: str, force: bool, warnings: list,
                  channel: str | None = None) -> dict:
    """Ritaglio (esistente o generato) + metadati → oggetto 'hero' per la spec del template."""
    cut = resolve_path(person.get("cutout"), base)
    if cut is None:
        frame = resolve_path(person.get("frame"), base)
        if frame is None or not frame.exists():
            raise RuntimeError(f"serve 'cutout' oppure 'frame' esistente (frame={person.get('frame')})")
        roi = resolve_roi(person.get("roi"), brand, channel)
        exclude = resolve_exclude(person, frame, brand, roi, warnings, channel)
        key = hashlib.sha1(json.dumps([str(frame), roi, person.get("point"), person.get("mode"),
                                       person.get("instance"), exclude]).encode()).hexdigest()[:8]
        cut = outdir / "cutouts" / f"{frame.stem}_{key}.png"
        if force or mtime(cut) < mtime(frame):
            args = ["cutout", str(frame), "--out", str(cut), "--mode", person.get("mode", "person"), "--trim", "--pad", "8"]
            if roi:
                args += ["--roi", roi]
            if exclude:
                args += ["--exclude", exclude]
            if person.get("point"):
                args += ["--point", str(person["point"]) if not isinstance(person["point"], list) else ",".join(map(str, person["point"]))]
            if person.get("instance"):
                args += ["--instance", str(person["instance"])]
            res = thumbvision(*args)
            yc.log(f"[cutout] {cut.name}: copertura {res.get('coverage')}, bordo {res.get('edge_softness_px')} px")
    if not cut.exists():
        raise RuntimeError(f"ritaglio non trovato: {cut}")
    meta = cutout_meta(cut, force=force, cache_dir=outdir)
    if not meta.get("face_detected"):
        warnings.append(f"volto non rilevato nel ritaglio {cut.name}: posizione stimata")
    if person.get("face"):
        meta = {**meta, "face": person["face"]}
    return {"src": cut.as_uri(), "path": str(cut), **meta}


def ensure_image(p: str | None, base: Path | None) -> dict | None:
    if not p:
        return None
    from PIL import Image
    path = resolve_path(p, base)
    if not path or not path.exists():
        raise RuntimeError(f"immagine non trovata: {p}")
    with Image.open(path) as im:
        w, h = im.size
    return {"src": path.as_uri(), "path": str(path), "w": w, "h": h}


# ── Controlli testuali e di colore ──────────────────────────────────────────
def words_of(text: str) -> list[str]:
    return [w for w in re.split(r"[\s|]+", text or "") if re.search(r"\w", w)]


def default_highlight(concept: dict, template: str):
    if "highlight" in concept:
        return concept["highlight"]
    text = concept.get("text", "")
    if "→" in text:
        return text.split("→")[-1].strip().split("|")[0].strip() or None
    if base_template(template) == "generic":
        ws = words_of(text)
        return ws[-1] if ws else None
    return None


def rel_lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted([rel_lum(a), rel_lum(b)], reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def color_pairs(template: str, spec: dict, tokens: dict) -> tuple[list[dict], list[str]]:
    """Coppie testo/fondo effettive del template, con contrasto WCAG e whitelist del brand (text_pairs_allowed)."""
    c = tokens.get("colors", {})
    pairs, warns = [], []
    bt = base_template(template)
    if bt in V2_TEMPLATES and c:
        allowed = set(tokens.get("text_pairs_allowed", []))
        names = accent_names(tokens)
        acc = spec.get("accent") if spec.get("accent") in names else default_accent(tokens)
        pairs.append({"role": "testo", "pair": "paper-on-plate", "contrast": None, "allowed": None,
                      "note": "titolo carta sul fondo scuro: contrasto misurato sul PNG dopo il render"})
        combos = [("ink", acc, "parola chiave (box)"), ("ink", plate_box_name(tokens, acc), "targhetta del nome")]
        for fg, bgc, role in combos:
            if not bgc or fg not in c or bgc not in c:
                continue
            name = f"{fg}-on-{bgc}"
            ok = name in allowed or not allowed
            pairs.append({"role": role, "pair": name, "contrast": contrast(c[fg], c[bgc]), "allowed": ok})
            if not ok:
                warns.append(f"coppia colore non ammessa dal brand: {name}")
        return pairs, warns
    if bt == "generic":
        cc = (spec.get("tokens") or tokens or {}).get("colors", {})
        fg, bg = cc.get("fg") or cc.get("ink", "#15171c"), cc.get("bg") or cc.get("paper", "#f4f1ea")
        r = contrast(fg, bg)
        pairs.append({"role": "testo", "pair": "fg-on-bg", "contrast": r, "allowed": r >= 4.5})
        if r < 4.5:
            warns.append(f"contrasto testo/fondo {r}:1 < 4.5:1")
    elif (c.get("fg") or c.get("ink")) and (c.get("bg") or c.get("paper")):
        # template proprio di un brand esterno: coppia testo/fondo dai token fg/bg (o ink/paper)
        fg, bg = c.get("fg") or c.get("ink"), c.get("bg") or c.get("paper")
        r = contrast(fg, bg)
        pairs.append({"role": "testo", "pair": "fg-on-bg", "contrast": r, "allowed": r >= 4.5})
        if r < 4.5:
            warns.append(f"contrasto testo/fondo {r}:1 < 4.5:1")
    return pairs, warns


def title_overlap(text: str, title: str | None) -> list[str]:
    if not title:
        return []
    norm = lambda s: {w.lower().strip(".,!?«»\"'’:;") for w in re.split(r"[\s|→]+", s)}  # noqa: E731
    a = {w for w in norm(text) if w and w not in STOPWORDS_IT and len(w) > 2}
    b = {w for w in norm(title) if w and w not in STOPWORDS_IT and len(w) > 2}
    return sorted(a & b)


# ── v2: contratto del concept, gancio, preparazione di tono/plate/scena/prop ─────────────────────────────────
VERB_WORDS = set("""è e’ era erano eri ero sono sei siamo siete sarà sarò saranno fu fui furono stato stata stati state essere
ho hai ha abbiamo avete hanno avevo aveva avevamo avevano ebbi ebbe ebbero avrò avrà avere fa fai faccio facciamo fanno fece feci
fecero fatto fatta fare dice dico dici diciamo dicono disse dissi detto dire va vai vado andiamo vanno andò andato andata andare
può posso puoi possiamo possono potevo poteva potuto deve devo devi dobbiamo devono doveva dovuto vuole voglio vuoi vogliamo
vogliono voleva voluto serve servono servì basta bastano bastò manca mancano mancò sa so sai sanno seppe saputo sta sto stai stanno
stava stette dà do dai danno diede dato vede vedo vedi vedono vide visto viene vengo vieni vengono venne venuto tiene tengo tengono
tenne esce esco escono uscì resta resto restano restò sembra sembrava costa costano costò vale valgono valeva""".split())
VERB_STEMS = ("scopr", "vend", "lasci", "chiud", "apr", "compr", "lanc", "costru", "perd", "vinc", "pag", "guadagn", "lavor",
              "cresc", "scal", "trov", "cerc", "sbagli", "cambi", "inizi", "smett", "rifiut", "licenzi", "assum", "fall", "us", "cre",
              "pens", "cred", "dic", "facc", "scriv", "riscriv", "rinunc", "punt", "mollat", "molli", "moll", "sced", "scegl", "rischi", "fattur", "raccogl",
              "investi", "assunt", "valid", "rifar", "impar", "insegn", "spieg", "prov", "rid", "odi", "am", "port", "tiene", "capi")
NOT_VERBS = set("""perché poiché affinché benché più già giù così però città qualità libertà novità caffè tè sé né ciò università
società velocità realtà verità età metà attività opportunità comunità identità mercato stato dato risultato privato mandato sito
credito partito invito minuto contenuto tributo istituto prodotto progetto soggetto oggetto oggetti prodotti progetti""".split())
NUMBER_UNITS = set("""k m mila milioni miliardi euro dollari € $ % mrr arr mau dau utenti clienti iscritti persone mesi mese anni anno
giorni giorno ore ora minuti settimane settimana volte progetti startup founder dipendenti download vendite ordini x""".split())


def hook_words(text: str) -> list[str]:
    """Parole del gancio per il conteggio v2: gli elisi contano come due parole (L'HO = lo ho)."""
    t = re.sub(r"(\w)['’](\w)", r"\1 \2", str(text or ""))
    return [w for w in re.split(r"[\s|]+", t) if re.search(r"\w", w)]


def _is_verb(w: str) -> bool:
    x = w.lower().strip(".,!?;:«»\"“”…")
    if not x or x in NOT_VERBS:
        return False
    if x in VERB_WORDS:
        return True
    if re.search(r"(are|ere|ire|arlo|erlo|irlo|arla|erla|irla|arli|erli|irli|arne|erne|irne|arsi|ersi|irsi)$", x) and len(x) > 4:
        return True                                                      # infiniti (anche con clitici)
    if re.search(r"(ando|endo|avo|ava|avano|evo|eva|evano|ivo|iva|ivano|iamo|isco|isce|iscono|erò|erà|eranno|irò|irà|iranno|arò|arà|ò|ì)$", x) and len(x) > 3:
        return True                                                      # gerundio, imperfetto, futuro, passato remoto, -isco
    if re.search(r"(ato|ata|ati|ate|uto|uta|uti|ute|ito|ita|iti)$", x) and len(x) > 4:
        return True                                                      # participi (euristica: alcuni nomi passano)
    return any(x.startswith(s) and len(x) - len(s) <= 5 and re.search(r"[oaie]$|ono$|ano$", x) for s in VERB_STEMS)


def validate_hook(c: dict, template: str) -> tuple[list[str], list[str], dict]:
    """Regole v2 del gancio (07 §5.3, §12.4): 3–6 parole (meno di 3 = errore, più di 6 = avviso); frase completa
    (almeno un verbo, oppure numero + unità; i frammenti nominali di 2+ parole sono rifiutati); parola chiave presente nel
    gancio; numeri solo con `number_verified` (fonte o timestamp); timestamp del momento (`payoff_at`/`claim_ts`)."""
    text = str(c.get("hook") or c.get("text") or "")
    errs, warns = [], []
    ws = hook_words(text)
    info = {"words": len(ws), "verbs": [w for w in ws if _is_verb(w)]}
    has_num = any(re.search(r"\d", w) for w in ws)
    num_unit = False
    for i, w in enumerate(ws):
        if re.search(r"\d", w):
            unit_attached = re.search(r"\d\s*([km%€$x]|mrr|arr)$", w.lower()) or re.match(r"^[€$]", w)
            nxt = ws[i + 1].lower().strip(".,!?") if i + 1 < len(ws) else ""
            if unit_attached or nxt in NUMBER_UNITS:
                num_unit = True
    info["number_unit"] = num_unit
    question = text.strip().endswith("?")
    override = c.get("hook_override")
    if len(ws) < 3:
        errs.append(f"gancio di {len(ws)} parole: servono 3–6 parole che si capiscano da sole (un frammento come «UNA LISTA» non dice niente)")
    elif base_template(template) == "duo" and len(ws) > DUO_WORDS_MAX:
        msg = (f"duo: gancio di {len(ws)} parole (> {DUO_WORDS_MAX}): il titolo del duo è di 3–4 parole, ogni riga ≥ "
               f"{DUO_ROW_MIN:.0%} dell'altezza → comprimi la frase o usa ritratto")
        (warns if c.get("hook_size_reason") else errs).append(msg + (f" — motivo dichiarato: {c['hook_size_reason']}"
                                                                     if c.get("hook_size_reason") else ""))
    elif len(ws) > 6:
        warns.append(f"gancio di {len(ws)} parole (> 6): accorcia se puoi")
    if not info["verbs"] and not num_unit and len(ws) >= 2:
        msg = f"gancio «{text}» senza verbo né numero + unità: è un frammento nominale, serve una frase (soggetto + verbo + posta)"
        if question:
            warns.append(msg.replace("è un frammento nominale", "domanda senza verbo") + ": verifica che si capisca da sola")
        elif override:
            warns.append(msg + f" — motivo dichiarato: {override}")
        else:
            errs.append(msg)
    if has_num and not c.get("number_verified"):
        errs.append("numero nel gancio senza `number_verified` (fonte o timestamp): niente numeri non confermati in thumbnail")
    kw = c.get("keyword") or c.get("highlight")
    if kw:
        norm = lambda s: re.sub(r"[^\w\s]", "", s.lower())  # noqa: E731
        if norm(str(kw)) not in norm(text):
            errs.append(f"parola chiave «{kw}» assente dal gancio")
    else:
        warns.append("nessuna parola chiave (keyword): il titolo resta senza evidenziazione")
    ec = str(c.get("expression_class") or "").lower()
    # «contro» è una forma del gancio dentro la leva claim (07 §5.5: lever resta claim|proof|duo|name): basta hook_form
    contro = {str(c.get("lever") or "").lower(), str(c.get("hook_form") or "").lower()} & {"contro", "against", "contrarian"}
    if ec.startswith("scett") and not contro:
        warns.append("espressione «scettico» senza un gancio «contro» (hook_form: contro; 07 §5.5): scegli una classe adatta alla leva")
    if not (c.get("payoff_at") is not None or c.get("claim_ts")):
        warns.append("gancio senza timestamp (payoff_at / claim_ts): ogni frase va presa dal transcript e verificata")
    return errs, warns, info


def normalize_concept(c: dict) -> dict:
    """Contratto v2 → campi letti dai template, senza perdere i vecchi: hook→text, keyword→highlight, plate dict."""
    c = dict(c)
    if c.get("hook") and not c.get("text"):
        c["text"] = c["hook"]
    if c.get("keyword") and "highlight" not in c:
        c["highlight"] = c["keyword"]
    return c


def _cache_name(*parts) -> str:
    return hashlib.sha1(json.dumps([str(p) for p in parts]).encode()).hexdigest()[:10]


def portrait_sidecar(cut_path: str) -> dict:
    """Sidecar completo di `yt-portrait cut` (<nome>.json accanto al PNG): sorgente, ROI, box del volto in sorgente e in uscita."""
    p = Path(cut_path).with_suffix(".json")
    try:
        d = yc.read_json(p)
        return d if d.get("tool") == "yt-portrait cut" else {}
    except Exception:  # noqa: BLE001
        return {}


def prepare_v2(c: dict, spec: dict, template: str, tokens: dict, brand: str, outdir: Path, base: Path | None,
               warns: list, force: bool, budget: dict | None = None) -> dict:
    """Preparazione dei template v2 prima del render (tutto locale, file in <out>/fx/):
      - grade: natural (pixel veri; tono del ritaglio di livello 2 solo con person_tone, ΔE00 sulla pelle) oppure mono
        (livello 2b: la stessa curva su persone e plate);
      - plate: scena graduata (duotono inchiostro→carta o curva mono, scurita e sfocata), piatta, oppure prop da testo;
      - scena del pop-out (scena): frame della sorgente del ritaglio dell'ospite, allineato;
      - accento auto: tra gli accenti del brand, quello con più stacco dalla persona davanti al cerchio;
      - richieste di prop: mai chiamate a pagamento qui, solo la specifica in prop_requests.json."""
    import numpy as np
    import thumb_fx as fx

    fxdir = outdir / "fx"
    bdir = yc.brand_dir(brand) if brand and brand != "client" else None
    bt = base_template(template)
    rep: dict = {"tone": [], "plate": None, "scene": None, "prop_requests": []}
    # grade della composizione: mono = livello 2b su persone E plate con la stessa curva; natural = pixel veri delle persone
    grade = str(c.get("grade") or GRADE_DEFAULT).lower()
    if grade not in GRADES:
        warns.append(f"grade «{grade}» sconosciuto (mono | natural): uso natural")
        grade = "natural"
    spec["grade"] = grade
    rep["grade"] = {"mode": grade}
    mono_p = None
    if grade == "mono":
        mono_p = fx.mono_params(tokens, bdir, c.get("grade_curve") if isinstance(c.get("grade_curve"), dict) else None)
        sig = fx.mono_signature(mono_p, tokens)
        rep["grade"].update({"level": "2b", "curve_id": mono_p["id"], "signature": sig,
                             "file": str(Path(bdir) / fx.MONO_FILE) if bdir and (Path(bdir) / fx.MONO_FILE).is_file() else None})
        if c.get("person_tone") not in (None, "mono"):
            warns.append(f"grade mono: person_tone «{c.get('person_tone')}» ignorato (la stessa curva mono va su tutte le persone)")
        tone = "mono"
    else:
        tone = c.get("person_tone") or "none"
        if tone not in ("none", "look", "duo"):
            warns.append(f"person_tone «{tone}» sconosciuto (none | look | duo): nessun tono")
            tone = "none"
        elif tone != "none" and str(c.get("guest_style") or "none") == "none":
            warns.append(f"person_tone «{tone}» con guest_style none: il tono di livello 2 è previsto con guest_style graphic (07 §11.2)")
    curve_tag = json.dumps(mono_p, sort_keys=True) if mono_p else ""
    for h in spec.get("people") or []:
        h["source_path"] = h["path"]                    # livello 0 (a colori): yt-thumb-qa ci confronta il render
        if tone in (None, "none") or not h.get("face"):
            continue
        dst = fxdir / f"{Path(h['path']).stem}_{tone}_{_cache_name(h['path'], mtime(Path(h['path'])), tone, json.dumps(tokens.get('colors', {}), sort_keys=True), curve_tag)}.png"
        side = dst.with_suffix(".tone.json")
        if dst.exists() and side.exists() and not force:
            r = yc.read_json(side)
        else:
            r = fx.tone_cutout(Path(h["path"]), dst, tone, h["face"], tokens, bdir, mono=mono_p)
            yc.write_json(side, r)
        h["tone_src"] = dst.as_uri()
        h["tone_path"] = str(dst)
        keys = ("mode", "level", "curve_id", "signature", "mapping", "face_mapping", "landmarks", "tones", "pass") if tone == "mono" else \
            ("mode", "strength", "skin_de00_mean", "skin_de00_p95", "face_de00_mean", "face_de00_p95", "pass", "skin_px")
        h["tone"] = {k: r.get(k) for k in keys}
        if tone == "mono":
            h["_curve"] = r.get("curve")
        rep["tone"].append({"cutout": Path(h["path"]).name, "role": h.get("role"), **h["tone"]})
    if grade == "mono":
        # stessa curva su tutte le persone: firma uguale + curve misurate sovrapposte (classi di luma comuni)
        ppl = [h for h in spec.get("people") or [] if h.get("tone")]
        sigs = sorted({h["tone"].get("signature") for h in ppl})
        gaps = []
        for i in range(len(ppl)):
            for j in range(i + 1, len(ppl)):
                gp = fx.curve_gap(ppl[i].get("_curve"), ppl[j].get("_curve"))
                if gp:
                    gaps.append({"pair": [Path(ppl[i]["path"]).name, Path(ppl[j]["path"]).name], **gp})
        rep["grade"].update({"people_signatures": sigs, "people_curve_gap": gaps})
        for h in ppl:
            h.pop("_curve", None)
    # accento automatico: quello con più stacco da capelli e volto della persona davanti al cerchio (sul ritaglio graduato)
    acc_in = str(c.get("accent") or "").strip()
    names = accent_names(tokens)
    allowed = [n for n in (spec.pop("_accents_allowed", None) or []) if n in names]
    if allowed:                                       # accenti ammessi dal profilo del canale (blocco thumbnails.accents)
        names = allowed
    if acc_in and acc_in != "auto" and acc_in not in names:
        fallback = default_accent(tokens) if default_accent(tokens) in names else names[0]
        warns.append(f"accento «{acc_in}» non è tra quelli ammessi (brand {brand}: {', '.join(names)}): uso {fallback}")
        spec["accent"] = fallback
    target = None
    if bt in ("duo", "ritratto"):
        people = spec.get("people") or []
        cb = str(c.get("circle_behind") or "guest")
        if people:
            target = next((h for h in people if h.get("role") == (cb if cb in ("guest", "host") else "guest")), people[0])
    if target is not None and target.get("face"):
        from PIL import Image
        src_img = Path(target.get("tone_path") or target["path"])
        try:
            a = np.asarray(Image.open(src_img).convert("RGBA"), np.float64) / 255.0
            hh, ww = a.shape[:2]
            f = target["face"]
            tones = fx.person_tones(a[..., :3], a[..., 3], [f[0] * ww, f[1] * hh, f[2] * ww, f[3] * hh])
            auto_names = [n for n in (tokens.get("accents_auto") or []) if n in names] or names
            ac = fx.accent_contrast(tones, tokens, auto_names if acc_in == "auto" else names)
            rep["accent_choice"] = {"person": Path(target["path"]).name, "tones": tones, **ac}
            if acc_in == "auto" and ac.get("best"):
                spec["accent"] = ac["best"]
                rep["accent_choice"]["chosen"] = ac["best"]
        except Exception as e:  # noqa: BLE001
            warns.append(f"accento: misura di contrasto non riuscita ({e})")
    if spec.get("accent") in (None, "", "auto"):
        spec["accent"] = default_accent(tokens) if default_accent(tokens) in names else names[0]
    rep["accent"] = spec["accent"]
    # plate
    pl = c.get("plate")
    pl = pl if isinstance(pl, dict) else ({"source": "scene", "path": pl} if isinstance(pl, str) else {})
    src = pl.get("source") or ("scene" if pl.get("path") else ("scene" if bt == "scena" else "flat"))
    # plate (livello 1, nessun pixel di persona): duotono inchiostro→carta del brand (mono) o look del brand, scurita e sfocata
    defaults = {"duo": {"grade": "mono", "ev": -2.3, "bokeh": 8, "vignette": 0.6},
                "ritratto": {"grade": "mono", "ev": -1.6, "bokeh": 18, "vignette": 0.5},
                "scena": {"grade": "look", "ev": -1.6, "bokeh": 7, "vignette": 0.0},
                "prova": {"grade": "mono", "ev": -1.5, "bokeh": 14, "vignette": 0.5}}[bt]
    if grade == "mono":
        # 2b: la plate passa per la STESSA curva delle persone (esposizione prima della curva, bokeh e vignetta di sfondo)
        defaults = {**defaults, "grade": "mono-2b", "ev": {"duo": -1.7, "ritratto": -1.5}.get(bt, -1.4),
                    "bokeh": {"duo": 6}.get(bt, defaults["bokeh"]), "vignette": {"duo": 0.7}.get(bt, defaults["vignette"])}
    g = {**defaults, **{k: pl[k] for k in ("grade", "ev", "bokeh", "vignette", "contrast", "flip") if k in pl}}
    if grade == "mono" and g["grade"] != "mono-2b":
        warns.append(f"grade mono: plate.grade «{g['grade']}» sostituito da mono-2b (stessa curva di persone e plate)")
        g["grade"] = "mono-2b"
    if src == "prop":
        prompt = pl.get("prompt") or (c.get("prop") or {}).get("prompt")
        if pl.get("path") and resolve_path(pl["path"], base) and resolve_path(pl["path"], base).exists():
            src_img = resolve_path(pl["path"], base)
        else:
            rep["prop_requests"].append(prop_request({**c, "accent": spec.get("accent")}, prompt, "plate", tokens, budget))
            warns.append("plate «prop» senza file: richiesta scritta in prop_requests.json (preventivo e OK esplicito nella sessione "
                         f"principale); ripiego locale: {pl.get('fallback', 'flat')}")
            src = pl.get("fallback", "flat")
            src_img = resolve_path(pl.get("fallback_path"), base) if pl.get("fallback_path") else None
            if src == "scene" and not src_img:
                src = "flat"
    elif src == "scene":
        src_img = resolve_path(pl.get("path"), base) if pl.get("path") else None
    else:
        src_img = None
    if bt == "scena" and src == "scene" and not pl.get("path"):
        # pop-out: la scena è il frame della sorgente del ritaglio dell'ospite, allineato al ritaglio
        guest = next((h for h in spec.get("people") or [] if h.get("role") == "guest"), (spec.get("people") or [None])[0])
        side = portrait_sidecar(guest["path"]) if guest else {}
        so = side.get("source") or {}
        if not (so.get("video") and so.get("t") is not None and side.get("face_box_source_px") and side.get("face_box_out_px")):
            warns.append("scena: il ritaglio non ha il sidecar di yt-portrait con sorgente e box del volto: niente pop-out, plate piatta")
            src = "flat"
        else:
            frame = fxdir / f"scene_{_cache_name(so['video'], so['t'])}.png"
            if not frame.exists() or force:
                fx.scene_frame(so["video"], float(so["t"]), frame, yc.FFMPEG)
            if side.get("roi_px"):
                roi = side["roi_px"]
            else:                                            # camera separata o frame intero: tutto il fotogramma
                from PIL import Image
                with Image.open(frame) as _im:
                    roi = [0, 0, _im.width, _im.height]
            out = fxdir / f"scene_{_cache_name(so['video'], so['t'], roi, json.dumps(g, sort_keys=True), curve_tag)}.jpg"
            if not out.exists() or force:
                fx.grade_plate(frame, out, g["grade"], tokens, bdir, bokeh=g["bokeh"], ev=g["ev"], crop=roi,
                               contrast=g.get("contrast"), vignette=g.get("vignette", 0.0), mono_p=mono_p)
            spec["scene"] = {"src": out.as_uri(), "crop": roi,
                             "map": {"scale": side["scale"], "face_src": side["face_box_source_px"][:2], "face_out": side["face_box_out_px"][:2]}}
            rep["scene"] = {"frame_t": so["t"], "roi": roi, **g}
            src_img = None
    if src == "scene" and src_img is not None:
        if not src_img.exists():
            raise RuntimeError(f"plate non trovata: {src_img}")
        out = fxdir / f"plate_{src_img.stem}_{_cache_name(src_img, mtime(src_img), json.dumps(g, sort_keys=True), template, curve_tag)}.jpg"
        if not out.exists() or force:
            fx.grade_plate(src_img, out, g["grade"], tokens, bdir, bokeh=g["bokeh"], ev=g["ev"], contrast=g.get("contrast"),
                           vignette=g.get("vignette", 0.0), mono_p=mono_p, flip=bool(g.get("flip")))
        spec["plate_src"] = out.as_uri()
        rep["plate"] = {"source": "scene" if pl.get("source") != "prop" else "prop", "path": str(src_img), **g,
                        "signature": fx.mono_signature(mono_p, tokens) if g["grade"] == "mono-2b" and mono_p else None}
    elif src == "flat":
        spec.pop("plate_src", None)
        rep["plate"] = rep["plate"] or {"source": "flat"}
    # oggetto «prop» in uno slot del template (sotto le persone)
    prop = c.get("prop")
    if isinstance(prop, dict):
        pp = resolve_path(prop.get("path"), base) if prop.get("path") else None
        if pp and pp.exists():
            spec["prop_obj"] = {"src": pp.as_uri(), "slot": prop.get("slot", "behind-guest"), "scale": prop.get("scale", 1.0)}
        else:
            rep["prop_requests"].append(prop_request({**c, "accent": spec.get("accent")}, prop.get("prompt"),
                                                     prop.get("slot", "behind-guest"), tokens, budget))
            warns.append(f"prop «{prop.get('slot', 'behind-guest')}» senza file: richiesta in prop_requests.json; render senza prop")
    spec["display_cap"] = c.get("display_cap") or spec.get("display_cap")
    return rep


def prop_request(c: dict, prompt: str | None, slot: str, tokens: dict, budget: dict | None = None) -> dict:
    """Specifica di una richiesta di prop/plate da SOLO TESTO. Non chiama niente: la chiamata la fa la sessione principale,
    dopo il preventivo dei crediti e l'OK esplicito dell'operatore (e del cliente, per un canale cliente)."""
    col = tokens.get("colors", {})
    acc = c.get("accent") if c.get("accent") in col else default_accent(tokens)
    cap = budget or PROP_CAP_EUR
    return {"concept": c.get("id"), "slot": slot, "status": "da approvare",
            "prompt": prompt or "(manca: descrivi l'oggetto della storia, senza persone)",
            "constraints": ["mai persone, volti, mani o parti del corpo", "mai testo, lettere, numeri o loghi nell'immagine",
                            "solo prompt testuale: nessun upload di frame, plate, ritagli o nomi dell'ospite",
                            f"palette bloccata: ink {col.get('ink')}, paper {col.get('paper')}, un solo accento {col.get(acc, acc)}",
                            "fondo trasparente per gli oggetti; 16:9 a tutto campo per le plate; ≥ 2048 px sul lato lungo"],
            "budget": {"cap_eur_episode": cap["episode"], "cap_eur_month": cap["month"],
                       "preflight": "preventivo dei crediti prima di ogni chiamata, poi OK esplicito nella sessione principale"},
            "suggested": ["un generatore di immagini da solo testo con palette bloccabile, scelto dall'operatore"],
            "deliver_to": f"plate.path / prop.path del concept {c.get('id')} (file locale), poi rilancia yt-thumb-render"}


def text_over_subject(metrics: dict, heroes: list[dict]) -> float:
    """Frazione dell'area del testo che cade su pixel opachi del soggetto (dai rettangoli misurati in pagina)."""
    from PIL import Image
    import numpy as np

    total, over = 0.0, 0.0
    alphas = []
    for h, m in zip(heroes, metrics.get("heroes", [])):
        im = Image.open(h["path"]).getchannel("A")
        alphas.append((np.asarray(im) > 127, m["rect"]))
    for t in metrics.get("texts", []):
        for (x, y, w, hh) in t["rects"]:
            area = max(w * hh, 1)
            total += area
            for a, (L, T, W, H) in alphas:
                ah, aw = a.shape
                # campionamento a griglia del rettangolo di testo nelle coordinate del ritaglio
                xs = np.linspace(x, x + w, 24)
                ys = np.linspace(y, y + hh, 12)
                gx = ((xs - L) / W * aw).astype(int)
                gy = ((ys - T) / H * ah).astype(int)
                mx = (gx >= 0) & (gx < aw)
                my = (gy >= 0) & (gy < ah)
                if not mx.any() or not my.any():
                    continue
                sub = a[np.ix_(gy[my], gx[mx])]
                over += area * sub.sum() / (len(xs) * len(ys))
    return round(over / total, 4) if total else 0.0


# ── Controlli sul PNG reso (crop dritti, upscale, volto, bordi, grafica del telaio) ──────────────────────
def _runs(mask) -> list[tuple[int, int]]:
    import numpy as np
    m = np.concatenate([[False], np.asarray(mask, bool), [False]]).astype(np.int8)
    d = np.flatnonzero(np.diff(m))
    return list(zip(d[0::2], d[1::2]))


def straight_alpha_edges(alpha, minrun: int | None = None, face_px: float | None = None) -> list[dict]:
    """Tratti dritti e netti del contorno dell'alpha (dove un crop ha tagliato la persona), su ogni lato.

    Per ogni colonna (lati alto/basso) o riga (sinistra/destra) prende il primo pixel opaco dal lato; un crop lascia
    un plateau: colonne consecutive col bordo alla stessa quota (entro 2 px) e un salto netto (α < 0.25 a 3 px
    fuori, o persona che tocca il bordo del PNG) e all'estremo del contorno su quel lato (un crop è un rettangolo che
    contiene la persona: i tratti dritti naturali, spalle e fianchi della giacca, stanno all'interno). Vale anche per ritagli con margine trasparente (thumbvision --pad), dove l'alpha non tocca il bordo del PNG."""
    import numpy as np

    A = np.asarray(alpha, np.float64)
    if A.max() > 1.5:
        A = A / 255.0
    h, w = A.shape
    # L'apice convesso della testa è «piatto» entro ±1 px per ~2·√(2R) px (≈ 50 px con un volto di 500 px) ma senza
    # angoli: un tratto corto conta solo se tocca il bordo del PNG o ha un angolo netto a un capo; senza angoli serve
    # ≥ 30% dell'altezza del volto (un taglio anche di soli 10 px nei capelli dura ≥ 150 px).
    shortrun = minrun or max(16, int(0.012 * max(w, h)))
    longrun = max(shortrun, int(0.30 * face_px)) if face_px else max(shortrun, int(0.04 * max(w, h)))
    out = []
    for side in ("top", "bottom", "left", "right"):
        M = {"top": A, "bottom": A[::-1], "left": A.T, "right": A.T[::-1]}[side]      # righe = profondità dal lato
        op = M > 0.5
        has = op.any(axis=0)
        idx = np.where(has, op.argmax(axis=0), -1)
        cols = np.arange(M.shape[1])
        # netto = transizione entro 3 px (α < 0.25 tre px fuori), oppure persona che arriva al bordo del PNG (α > 0.2 sul bordo)
        prev3 = np.where(idx >= 3, M[np.clip(idx - 3, 0, None), cols], 0.0)
        hard = has & (((idx <= 2) & (M[0] > 0.2)) | ((idx >= 3) & (prev3 < 0.25)))
        # un crop è il rettangolo che contiene la persona: il tratto sta all'estremo del contorno su quel lato
        extreme = int(idx[has].min()) if has.any() else 0
        hard &= idx <= extreme + 4
        k = 0
        n = len(idx)
        while k < n:
            if not hard[k]:
                k += 1
                continue
            j = k
            lo = hi = idx[k]
            while j + 1 < n and hard[j + 1] and max(hi, idx[j + 1]) - min(lo, idx[j + 1]) <= 2:
                j += 1
                lo, hi = min(lo, idx[j]), max(hi, idx[j])
            L = j - k + 1
            # crop se: tocca il bordo del PNG (ritaglio senza margine), oppure ha un angolo netto a un capo (il contorno
            # salta di ≥ 4 px entro 3 px oltre il tratto: lì il crop ha tagliato il fianco della testa/mano), oppure è lungo
            touch = bool(idx[k] <= 2 and M[0, k] > 0.2)
            corner = False
            for e0, step in ((k, -1), (j, 1)):
                q = e0 + 3 * step
                if 0 <= q < n:
                    corner |= bool(not has[q] or idx[q] - idx[e0] >= 4)
                else:
                    corner = True          # il tratto arriva al bordo del PNG sull'altro asse
            if L >= shortrun and (touch or corner or L >= longrun):
                depth = float(np.median(idx[k:j + 1]))
                pos = {"top": depth, "bottom": h - depth, "left": depth, "right": w - depth}[side]
                out.append({"side": side, "pos": pos, "span": [int(k), int(j + 1)]})   # indici nelle coordinate originali
            k = j + 1
    return out


def crop_edge_check(hero: dict, rect_css: list, render, scale: int = SCALE) -> list[dict]:
    """Bordi dritti del ritaglio mappati nel canvas. Un bordo che cade dentro il canvas (> 3 px dal bordo) ed è visibile
    nel PNG reso (salto di colore tra i due lati della linea > 10 livelli) è un errore S1 (07 §11). Template-agnostico:
    un bordo coperto da altri elementi o sfumato da una maschera non ha salto e passa."""
    from PIL import Image
    import numpy as np

    im = Image.open(hero["path"]).convert("RGBA")
    A = np.asarray(im.getchannel("A"), np.float64) / 255.0
    h, w = A.shape
    L, T, Wd, Hd = [float(v) for v in rect_css]
    RH, RW = render.shape[:2]
    sx, sy = Wd * scale / w, Hd * scale / h
    out = []
    f = hero.get("face")
    for e in straight_alpha_edges(A, face_px=(f[3] * h) if f else None):
        side = e["side"]
        a0, a1 = e["span"]
        if side in ("left", "right"):
            line = L * scale + e["pos"] * sx
            s0, s1 = T * scale + a0 * sy, T * scale + a1 * sy
            lim, other = RW, RH
        else:
            line = T * scale + e["pos"] * sy
            s0, s1 = L * scale + a0 * sx, L * scale + a1 * sx
            lim, other = RH, RW
        seg = {"side": side, "line_css": round(line / scale, 1), "span_css": [round(s0 / scale, 1), round(s1 / scale, 1)]}
        c0, c1 = int(max(0, s0)), int(min(other, s1))
        if line <= 3 or line >= lim - 3 or c1 - c0 < 8:
            seg.update({"inside": False, "visible_px": 0})
            out.append(seg)
            continue
        inner = int(round(line + (6 if side in ("left", "top") else -6)))
        outer = int(round(line + (-6 if side in ("left", "top") else 6)))
        inner, outer = min(max(inner, 0), lim - 1), min(max(outer, 0), lim - 1)
        idx = np.arange(c0, c1, 2)
        if side in ("left", "right"):
            pa, pb = render[idx, inner, :3].astype(float), render[idx, outer, :3].astype(float)
        else:
            pa, pb = render[inner, idx, :3].astype(float), render[outer, idx, :3].astype(float)
        diff = np.abs(pa - pb).mean(axis=1)
        seg.update({"inside": True, "visible_px": int((diff > 10).sum() * 2), "mean_step": round(float(diff.mean()), 1)})
        out.append(seg)
    return out


_EDGE_CACHE: dict = {}


def cutout_edge_quality(hero: dict) -> dict:
    """Frangia calda (fringe_rb) e alone chiaro (rim_luma) sul bordo testa/capelli del ritaglio (metriche di qualità del matte,
    ×255 rispetto al colore dell'interno vicino). Cache solo in memoria: niente scritture accanto al ritaglio, che può
    stare in una cartella di lavoro da non toccare."""
    key = (hero["path"], mtime(Path(hero["path"])))
    if key in _EDGE_CACHE:
        return _EDGE_CACHE[key]
    from PIL import Image
    import numpy as np
    from portrait import edge_metrics

    im = Image.open(hero["path"]).convert("RGBA")
    a = np.asarray(im, np.float64) / 255.0
    w, h = im.size
    f = hero.get("face")
    fb = [f[0] * w, f[1] * h, f[2] * w, f[3] * h] if f else None
    e = edge_metrics(a[..., :3], a[..., 3], fb)
    _EDGE_CACHE[key] = e
    return e


def plate_text_contrast(render, rects: list, text_hex: str, scale: int = SCALE) -> float | None:
    """Contrasto WCAG tra il colore del testo e la mediana del fondo attorno alle righe (anello di 24 px CSS)."""
    import numpy as np

    if not rects:
        return None
    H, W = render.shape[:2]
    mask = np.zeros((H, W), bool)
    inner = np.zeros((H, W), bool)
    for (x, y, w, h) in rects:
        X0, Y0, X1, Y1 = [int(v * scale) for v in (x, y, x + w, y + h)]
        mask[max(0, Y0 - 72):min(H, Y1 + 72), max(0, X0 - 72):min(W, X1 + 72)] = True
        inner[max(0, Y0):min(H, Y1), max(0, X0):min(W, X1)] = True
    ring = mask & ~inner
    if ring.sum() < 100:
        return None
    med = np.median(render[ring][:, :3], axis=0)
    return contrast(text_hex, "#%02x%02x%02x" % tuple(int(v) for v in med))


PROMOTE = (("cap height gancio", "07 §12.4"), ("gancio su ", "07 §12.4"), ("testo sopra un volto", "07 §12.4"),
           ("gancio di ", "07 §12.4"), ("coppia colore non ammessa", "07 §7.2"))


def post_render_checks(plan: dict, entry: dict, metrics: dict, max_upscale: float, display_cap: float = DISPLAY_CAP) -> None:
    """Controlli sul PNG reso; scrive entry['checks2'], sposta in errors ciò che 07 §11/§12.4 vuole bloccante."""
    import numpy as np
    from PIL import Image

    spec, template = plan["spec"], plan["template"]
    errors, warns = entry["errors"], entry["warnings"]
    # 1. avvisi che 07 §12.4 vuole bloccanti → errori
    keep = []
    for w in warns:
        rule = next((r for pre, r in PROMOTE if w.startswith(pre)), None)
        if rule and not (w.startswith("coppia colore") and "plate" in w):
            errors.append(f"{w} [{rule}: blocca il render]")
        else:
            keep.append(w)
    entry["warnings"] = warns = keep
    heroes = spec.get("people") or []
    mh = metrics.get("heroes") or []
    sr = metrics.get("series") or {}
    srh = sr.get("heroes") or []
    render = np.asarray(Image.open(plan["png"]).convert("RGB"))
    out: dict = {"heroes": []}
    face_fracs = []
    for i, hero in enumerate(heroes):
        if i >= len(mh):
            break
        rect = mh[i]["rect"]
        info = {"cutout": Path(hero["path"]).name, "face_frac": mh[i].get("face_frac")}
        face_fracs.append(mh[i].get("face_frac") or 0)
        # bordi dritti visibili
        edges = crop_edge_check(hero, rect, render)
        info["crop_edges"] = edges
        for e in edges:
            if e.get("inside") and e.get("visible_px", 0) >= 24:
                errors.append(f"bordo dritto del ritaglio {info['cutout']} visibile dentro il canvas: lato {e['side']} a "
                              f"{e['line_css']} px CSS, {e['visible_px'] / SCALE:.0f} px CSS di lunghezza (07 §11: va a filo del bordo "
                              "del canvas, rifilato su un bordo o cambiato frame)")
            elif e.get("inside") and e.get("visible_px", 0) > 0:
                warns.append(f"bordo dritto del ritaglio {info['cutout']} dentro il canvas (lato {e['side']}, {e['visible_px'] / SCALE:.0f} px CSS): "
                             "controlla al 100%")
        # upscale: con la risoluzione effettiva del volto (ritagli yt-portrait) il tetto si misura al
        # display: volto a 1280 px ≤ display_cap × eff_face_px; senza (ritagli generici) resta ≤ max_upscale vs la sorgente.
        p = hero.get("portrait") or {}
        draw = rect[2] * SCALE / max(1, hero["w"])
        up = (p.get("scale") or 1.0) * draw
        face_css = mh[i]["face"][3]
        eff = p.get("eff_face_px")
        disp = round(face_css / eff, 3) if eff else None
        info.update({"draw_scale": round(draw, 4), "upscale_vs_source": round(up, 3), "portrait": bool(p),
                     "eff_upscale": round(p["eff_upscale"] * draw, 2) if p.get("eff_upscale") else None,
                     "face_px_1280": round(face_css, 1), "eff_face_px": eff, "display_upscale": disp, "display_cap": display_cap})
        if eff:
            if disp > display_cap + 0.02:
                if spec.get("upscale_override"):
                    warns.append(f"volto a {disp:.2f}× la sua risoluzione effettiva a 1280 px (tetto {display_cap}×) — motivo "
                                 f"dichiarato: {spec['upscale_override']}")
                else:
                    errors.append(f"volto di {info['cutout']} a {disp:.2f}× la sua risoluzione effettiva ({eff:.0f} px) a 1280 px > "
                                  f"{display_cap}× (07 §10.1): servono still, la camera stretta o un volto più piccolo")
        elif up > max_upscale + 0.02:
            if spec.get("upscale_override"):
                warns.append(f"volto a {up:.2f}× della sorgente (oltre {max_upscale}×) — motivo dichiarato: {spec['upscale_override']}")
            else:
                errors.append(f"volto a {up:.2f}× della sorgente > {max_upscale}× (07 §10.1): servono still o un volto più piccolo")
        if p and abs(draw - 1) > 0.01:
            warns.append(f"ritaglio yt-portrait ridisegnato a {draw:.2f}× (doppio ricampionamento): rifai il cut alla misura giusta")
        # bordo dei capelli
        try:
            edge = cutout_edge_quality(hero)
        except Exception as ex:  # noqa: BLE001
            edge = {"error": str(ex)}
        info["edge"] = edge
        fr, rim = edge.get("fringe_rb"), edge.get("rim_luma")
        if fr is not None and fr > FRINGE_ERR:
            errors.append(f"frangia calda sul bordo dei capelli di {info['cutout']}: {fr} (> {FRINGE_ERR}): rifai lo scontorno con yt-portrait cut")
        elif fr is not None and fr > FRINGE_WARN:
            warns.append(f"frangia calda sul bordo dei capelli di {info['cutout']}: {fr} (> {FRINGE_WARN}; decontaminato: 2–8)")
        if rim is not None and rim > RIM_WARN:
            warns.append(f"alone chiaro sul bordo di {info['cutout']}: {rim} (> {RIM_WARN})")
        if i < len(srh) and srh[i].get("flush_fail"):
            errors.append(f"{info['cutout']}: bordi dritti non portabili a filo ({'; '.join(srh[i]['flush_fail'])})")
        out["heroes"].append(info)
    # 2. altezza del volto (il più grande sul canvas; nel duo l'ospite deve dominare). I template v2 hanno soglie proprie
    #    (post_render_v2).
    if face_fracs and base_template(template) not in V2_TEMPLATES:
        big = max(face_fracs)
        out["face_frac_max"] = big
        if big < FACE_FRAC_MIN:
            errors.append(f"volto più grande al {big:.0%} dell'altezza (< {FACE_FRAC_MIN:.0%}: meno di 19 px a 168 px)")
        elif big < FACE_FRAC_WARN and not spec.get("artifact"):
            warns.append(f"volto al {big:.0%} dell'altezza (< {FACE_FRAC_WARN:.0%}; mediana dei podcast di riferimento 35.5%): "
                         "con il master il cap 2.0× non permette di più → still dell'ospite")
        dom = sr.get("dominance")
        if dom and dom["guest_face_frac"] + 1e-3 < dom["host_face_frac"]:
            errors.append(f"duo: l'ospite ({dom['guest_face_frac']:.0%}) ha il volto più piccolo dell'host ({dom['host_face_frac']:.0%})")
    # 3. grafica del telaio (dischi, forme, box)
    for d in sr.get("decos") or []:
        k = d.get("kind")
        if d.get("nogo_points") or d.get("nogo_px"):
            errors.append(f"{k} nella zona del timestamp (230×110 in basso a destra)")
        if (d.get("top_right_points") or d.get("top_right_px")) and not d.get("field"):
            # il disco «di campo» del duo (massa di fondo sotto le persone) può passare sotto
            # le icone hover: lì non si perde niente; gli elementi grafici (anelli, code, box) no
            errors.append(f"{k} nella zona hover in alto a destra (120×80)")
        if d.get("edge_bad"):
            errors.append(f"{k} che sfiora il bordo del canvas ({'; '.join(d['edge_bad'])}): ≥ 24 px d'aria o taglio ≥ 15% del diametro")
        if d.get("face_px"):
            errors.append(f"{k} sopra un volto ({d['face_px']} px CSS²)")
    for lg in sr.get("logos") or []:
        if lg.get("symbol_css") and lg["symbol_css"] < SYMBOL_MIN_CSS:
            errors.append(f"simbolo del logo a {lg['symbol_4k']} px a 4K (< 140 px, regola del logo)")
    for n in sr.get("notes") or []:
        if "< 2%" in n:
            warns.append(n)
    out["series"] = {k: sr.get(k) for k in ("template", "field", "accent", "dominance", "notes") if sr.get(k) is not None}
    entry["checks2"] = out


def post_render_v2(plan: dict, entry: dict, metrics: dict, fxres: dict | None) -> None:
    """Controlli dei template v2 (07 §12.4). Scrive entry['checks_v2']."""
    import numpy as np
    from PIL import Image
    import thumb_fx as fx

    spec, template = plan["spec"], base_template(plan["template"])
    errors, warns = entry["errors"], entry["warnings"]
    out: dict = {"heroes": []}
    heroes = spec.get("people") or []
    mh = metrics.get("heroes") or []
    sr = metrics.get("series") or {}
    im = Image.open(plan["png"]).convert("RGB")
    render = np.asarray(im)
    text_rects = [r for t in metrics.get("texts", []) for r in t.get("rects", [])]
    gs = spec.get("guest_style") or "none"
    fracs = []
    # maschera delle persone a 320×180 (stacco volto–intorno: le bande misurano il fondo, non la persona)
    try:
        pmask320 = np.zeros((180, 320), bool)
        for i, h in enumerate(heroes):
            if i < len(mh):
                aa = np.asarray(Image.open(h["path"]).getchannel("A"), np.float64) / 255.0
                pmask320 |= fx.hero_alpha_on_canvas(aa, [v / 4.0 for v in mh[i]["rect"]], 320, 180, css_w=320) > 0.5
    except Exception:  # noqa: BLE001
        pmask320 = None
    for i, hero in enumerate(heroes):
        if i >= len(mh):
            break
        face = mh[i]["face"]
        name = Path(hero["path"]).name
        role = hero.get("role") or ("guest" if i == 0 else None)
        info = {"cutout": name, "role": role, "face_frac": mh[i]["face_frac"]}
        fracs.append((role, mh[i]["face_frac"], name))
        # dettaglio nel file servito (07 §10.1)
        sd = fx.served_detail(im, face)
        info["served_720"] = sd
        if sd["lap"] < SERVED_ERR:
            msg = (f"volto di {name} morbido nel file servito 720×405: Laplaciano {sd['lap']:.0f} < {SERVED_ERR:.0f} (p10 dei riferimenti EN)")
            if spec.get("detail_reason"):
                warns.append(msg + f" — motivo dichiarato: {spec['detail_reason']}")
            else:
                errors.append(msg + ": volto più piccolo, sorgente migliore (still / camera stretta) o motivo scritto (detail_reason)")
        elif sd["lap"] < SERVED_WARN:
            warns.append(f"volto di {name} sotto il p25 dei riferimenti nel file servito 720×405 (Laplaciano {sd['lap']:.0f} < {SERVED_WARN:.0f})")
        # stacco volto–intorno
        dl = fx.face_surround_dL(render, face, text_rects, person=pmask320)
        info["face_surround_dL"] = dl
        sides = fx.face_surround_sides(render, face, text_rects, person=pmask320)
        info["face_surround_sides"] = sides
        for k in ("left", "right"):
            v = (sides or {}).get(f"{k}_dL")
            if v is not None and dl is not None and dl >= SURROUND_ERR and v < SURROUND_ERR:
                warns.append(f"stacco volto–intorno di {name}: sul lato {'sinistro' if k == 'left' else 'destro'} solo ΔL* {v} (< {SURROUND_ERR:.0f})")
        if dl is not None and dl < SURROUND_ERR:
            errors.append(f"volto di {name} senza stacco dall'intorno: ΔL* {dl} < {SURROUND_ERR:.0f} (fondo del tono della pelle)")
        elif dl is not None and dl < SURROUND_WARN:
            warns.append(f"stacco volto–intorno di {name} basso: ΔL* {dl} < {SURROUND_WARN:.0f}")
        # buchi del matte nel volto
        a = np.asarray(Image.open(hero["path"]).getchannel("A"), np.float64) / 255.0
        holes = fx.matte_holes(a, hero["face"])
        info["matte_holes"] = holes
        if holes["hole_frac"] > HOLE_ERR:
            msg = (f"buchi del matte nel volto di {name}: {holes['hole_frac']:.2%} dei pixel con α < 0.9 (lente degli occhiali?)")
            (errors if gs != "none" else warns).append(msg + (": con guest_style graphic il contorno si vedrebbe attraverso — "
                                                             "rifai il cut" if gs != "none" else ": si vede la plate attraverso"))
        # tono (livello 2): ΔE00 sulla pelle
        if hero.get("tone"):
            t = hero["tone"]
            info["tone"] = t
            if t.get("mode") == "mono":
                # livello 2b: niente ΔE00 (la pelle diventa grigia per scelta); stessa funzione su ogni pixel + landmark
                mp_ = t.get("mapping") or {}
                if not mp_.get("pass") or not (t.get("face_mapping") or {}).get("pass", True):
                    errors.append(f"grade mono su {name}: la mappatura non è la curva unica (scarto massimo {mp_.get('max_dev_levels')} "
                                  f"livelli > {MAP_TOL_LEVELS}): un ritocco locale o una curva diversa (livello 2b)")
                lm = t.get("landmarks") or {}
                if lm.get("ok"):
                    msg = (f"grade mono su {name}: landmark MediaPipe spostati in media del {lm['mean']:.1%} della distanza tra gli "
                           f"occhi (solo grigio {lm.get('grey_baseline')}, sola curva {lm.get('curve_only')})")
                    if lm.get("level") == "error":
                        errors.append(msg + " (> 4 %): la geometria del volto non è invariata")
                    elif lm.get("level") == "warn":
                        warns.append(msg + " (> 2 %)")
                else:
                    warns.append(f"grade mono su {name}: landmark non verificati ({lm.get('reason', 'MediaPipe assente')})")
            elif not t.get("pass"):
                errors.append(f"tono {t['mode']} su {name}: pelle ΔE00 {t['skin_de00_mean']} / p95 {t['skin_de00_p95']} oltre la soglia "
                              f"(≤ 2.5 / ≤ 5, policy v2 livello 2)")
        # face_pixels_unchanged: render vs render senza gli strati sotto il ritaglio, sui pixel opachi del volto
        if fxres and i < len(fxres.get("files") or []):
            clip = fxres["clips"][i]
            nofx = np.asarray(Image.open(fxres["files"][i]).convert("RGB"))
            X0, Y0 = int(round(clip["x"] * SCALE)), int(round(clip["y"] * SCALE))
            main = render[Y0:Y0 + nofx.shape[0], X0:X0 + nofx.shape[1]]
            hh, ww = min(main.shape[0], nofx.shape[0]), min(main.shape[1], nofx.shape[1])
            A = fx.hero_alpha_on_canvas(a, mh[i]["rect"], render.shape[1], render.shape[0])
            from scipy import ndimage
            opaque = ndimage.binary_erosion(A >= 0.999, iterations=3)
            fm = np.zeros_like(opaque)
            fx0, fy0, fw, fh = [v * SCALE for v in face]
            fm[int(fy0):int(fy0 + fh), int(fx0):int(fx0 + fw)] = True
            mask = (opaque & fm)[Y0:Y0 + hh, X0:X0 + ww]
            cp = fx.changed_pixels(main[:hh, :ww], nofx[:hh, :ww], mask)
            info["face_pixels_unchanged"] = cp
            # ±1 livello sullo 0,1% dei pixel = arrotondamento del compositing di Chrome («1 level, float rounding»)
            if cp["changed_gt1"] or cp["changed"] > 0.001 * max(1, cp["px"]):
                errors.append(f"face_pixels_unchanged: {cp['changed']} pixel opachi del volto di {name} cambiano con gli strati grafici "
                              f"(max {cp['max']} livelli): un effetto sta SOPRA la persona (policy v2: solo sotto)")
        out["heroes"].append(info)
    # silhouette a 246 px
    try:
        alphas = [(np.asarray(Image.open(h["path"]).getchannel("A"), np.float64) / 255.0, mh[i]["rect"]) for i, h in enumerate(heroes) if i < len(mh)]
        sil = fx.silhouette_dL(render, alphas)
    except Exception as e:  # noqa: BLE001
        sil = None
        warns.append(f"silhouette non misurata: {e}")
    out["silhouette_dL_246"] = sil
    if sil is not None and gs != "none" and sil < SILHOUETTE_WARN:
        warns.append(f"silhouette a 246 px: ΔL* {sil} < {SILHOUETTE_WARN:.0f} con guest_style {gs} (soglia non ancora calibrata)")
    # volti: claim ≥ 35% (obiettivo 40%); duo: ciascuno ≥ 30%, ospite ≥ host
    if fracs:
        guest = [f for r, f, n in fracs if r == "guest"] or [max(f for _, f, _ in fracs)]
        if template in V2_CLAIM:
            g = max(guest)
            if g < FACE_V2_ERR:
                msg = f"volto dell'ospite al {g:.0%} dell'altezza (< {FACE_V2_ERR:.0%}, template claim v2)"
                if spec.get("face_floor_reason"):
                    warns.append(msg + f" — motivo dichiarato: {spec['face_floor_reason']}")
                else:
                    errors.append(msg + ": sorgente con più risoluzione (still, camera stretta) o motivo scritto (face_floor_reason)")
            elif g < FACE_V2_WARN:
                warns.append(f"volto dell'ospite al {g:.0%} (obiettivo ≥ {FACE_V2_WARN:.0%})")
        if template == "duo":
            for r, f, n in fracs:
                if f < FACE_DUO_MIN:
                    msg = f"duo: volto di {n} ({r or '?'}) al {f:.0%} (< {FACE_DUO_MIN:.0%})"
                    (warns if spec.get("face_floor_reason") else errors).append(
                        msg + (f" — motivo dichiarato: {spec['face_floor_reason']}" if spec.get("face_floor_reason") else
                               ": la sorgente non regge un volto più grande (tetto al display) → camera stretta per host e ospite"))
            dom = sr.get("dominance")
            if dom and dom["guest_face_frac"] + 1e-3 < dom["host_face_frac"]:
                errors.append(f"duo: l'ospite ({dom['guest_face_frac']:.0%}) ha il volto più piccolo dell'host ({dom['host_face_frac']:.0%})")
    # un solo accento; credenziale; logo
    acc = sr.get("accents") or []
    out["accents"] = acc
    if len(acc) > 1:
        errors.append(f"più di un accento nella composizione: {', '.join(acc)} (07 §7.2)")
    pal = accent_names(plan["tokens"])
    if any(a not in pal for a in acc):
        errors.append(f"accento fuori palette: {acc} (accenti del brand: {', '.join(pal)})")
    creds = sr.get("credentials") or []
    out["credentials"] = creds
    guest_named = any(h.get("role") == "guest" and h.get("name") for h in heroes)
    if template in ("duo",) + V2_CLAIM and not creds:
        errors.append("credenziale assente: nome (e ruolo) dell'ospite in people[].name/title (rubrica 07 §14 voce 7)")
    elif template == "prova" and not creds and guest_named:
        warns.append("prova: nome dell'ospite non mostrato")
    # righe del titolo (glifi): frase ≥ 12%, parola chiave ≥ 18%
    rows = [r for t in metrics.get("texts", []) if t.get("kind") == "hook" for r in (t.get("rows") or [])]
    out["hook_rows"] = rows
    two_reg = len({t.get("font") for t in metrics.get("texts", []) if t.get("kind") == "hook"}) > 1 or spec.get("hook_style") == "two"
    for r in rows:
        lim = HOOK_KEY_MIN if r["keyword"] else HOOK_ROW_MIN
        if template == "duo":
            # duo: ogni riga ≥ 20 % dell'altezza, obiettivo il 22 %
            if r["frac"] + 1e-4 < DUO_ROW_MIN:
                msg = f"duo: riga del titolo alta {r['frac']:.1%} < {DUO_ROW_MIN:.0%} (obiettivo {DUO_ROW_TARGET:.0%})"
                if spec.get("hook_size_reason"):
                    warns.append(msg + f" — motivo dichiarato: {spec['hook_size_reason']}")
                else:
                    errors.append(msg + ": 3–4 parole in 2–3 righe corte, persone più ai lati")
            elif r["frac"] + 1e-4 < DUO_ROW_TARGET:
                warns.append(f"duo: riga del titolo alta {r['frac']:.1%} (obiettivo ≥ {DUO_ROW_TARGET:.0%})")
            continue
        if r["keyword"] and not two_reg and r["frac"] + 1e-4 >= HOOK_ROW_MIN and r["frac"] + 1e-4 < HOOK_KEY_MIN:
            # titolo uniforme (la parola chiave ha lo stesso corpo della frase): il 18% è l'obiettivo, non un blocco
            warns.append(f"riga della parola chiave alta {r['frac']:.1%} (< {HOOK_KEY_MIN:.0%}, obiettivo per un titolo a un solo corpo)")
            continue
        if r["frac"] + 1e-4 < lim:
            msg = (f"riga del titolo alta {r['frac']:.1%} dell'altezza < {lim:.0%}{' (riga della parola chiave)' if r['keyword'] else ''}")
            if spec.get("hook_size_reason"):
                warns.append(msg + f" — motivo dichiarato: {spec['hook_size_reason']}")
            else:
                errors.append(msg + ": accorcia il gancio o allarga la fascia del testo")
    # titolo carta sul fondo: contrasto WCAG misurato attorno alle righe
    hrects = [r for t in metrics.get("texts", []) if t.get("kind") == "hook" for r in t.get("rects", [])]
    cr = plate_text_contrast(render, hrects, plan["tokens"].get("colors", {}).get("paper", "#f4f1ea"))
    out["hook_plate_contrast"] = cr
    for pr in entry.get("color_pairs") or []:
        if pr.get("pair") == "paper-on-plate":
            pr.update({"contrast": cr, "allowed": bool(cr and cr >= 4.5)})
    if cr is not None and cr < 4.5:
        errors.append(f"titolo carta sul fondo a {cr}:1 (< 4.5:1): scurisci la plate (ev) o cambia fondo")
    # simbolo ed etichetta di formato mai sopra una persona (logo: fondo scuro pieno, mai su un'immagine «affollata»)
    try:
        cover = np.zeros((720, 1280), np.float64)
        for i, h in enumerate(heroes):
            if i < len(mh):
                a = np.asarray(Image.open(h["path"]).getchannel("A"), np.float64) / 255.0
                cover = np.maximum(cover, fx.hero_alpha_on_canvas(a, mh[i]["rect"], 1280, 720))
        over = []
        for lg in sr.get("logos") or []:
            x, y = lg.get("at", [0, 0])
            s_ = lg.get("symbol_css") or 50
            w_ = s_ * (4.6 if lg.get("wordmark") else 1.0)
            if lg.get("rect"):                                  # wordmark: rettangolo misurato in pagina
                x, y, w_, s_ = lg["rect"]
            sub = cover[int(max(0, y)):int(y + s_), int(max(0, x)):int(x + w_)]
            frac = float((sub > 0.5).mean()) if sub.size else 0.0
            over.append(round(frac, 3))
            if frac > 0.02:
                errors.append(f"logo del brand sopra una persona ({frac:.0%} dell'area): spostalo o usa una pillola d'inchiostro")
        cols = plan["tokens"].get("colors", {})
        paper = cols.get("paper", "#f4f1ea")
        for t in metrics.get("texts", []):
            if t.get("kind") in ("label", "meta") and t.get("rects"):
                if (sr.get("host_tag") or {}).get("text") and t.get("text", "").strip() == sr["host_tag"]["text"]:
                    continue                                    # etichetta dell'host: carta sulla sua striscia d'inchiostro
                if t.get("text", "") in (sr.get("strips") or []):
                    continue                                    # testo su striscia d'inchiostro (riga meta sopra la maglia chiara)
                on_disc = t.get("kind") == "label" and (sr.get("label") or {}).get("on_disc")
                crt = plate_text_contrast(render, t["rects"], cols.get("ink", "#15171c") if on_disc else paper)
                if crt is not None and crt < 4.5:
                    warns.append(f"testo «{t['text'][:24]}» ({t['kind']}) a {crt}:1 sul fondo (< 4.5:1): spostalo su un fondo scuro")
        out["logo_over_person"] = over
    except Exception as e:  # noqa: BLE001
        warns.append(f"controllo simbolo/etichetta non eseguito: {e}")
    # prova: l'artefatto deve essere reale e autorizzato (provenienza scritta)
    if template == "prova" and not spec.get("artifact_source"):
        errors.append("prova: artefatto senza «artifact_source» (chi l'ha fornito/autorizzato, quando): solo prove reali, "
                      "autorizzate dall'ospite, senza dati di clienti")
    # testo nella zona hover: nei template v2 è un errore
    for w in list(warns):
        if w.startswith("testo nella zona hover"):
            warns.remove(w)
            errors.append(w + " [v2: blocca il render]")
    v2rep = plan.get("v2") or {}
    # ── grade (2b), cerchio d'accento, stacco dal feed scuro, masse chiare ──
    grade = (v2rep.get("grade") or {}).get("mode") or spec.get("grade") or "natural"
    gout: dict = {"mode": grade}
    if grade == "mono":
        g = v2rep.get("grade") or {}
        psig = (v2rep.get("plate") or {}).get("signature")
        sigs = list(g.get("people_signatures") or [])
        gout.update({"level": "2b", "curve_id": g.get("curve_id"), "signature": g.get("signature"), "people_signatures": sigs,
                     "plate_signature": psig, "people_curve_gap": g.get("people_curve_gap")})
        if len(sigs) > 1 or (sigs and sigs[0] != g.get("signature")):
            errors.append(f"grade mono: curve diverse tra le persone ({', '.join(map(str, sigs))}): una sola curva per tutta la foto (2b)")
        if (v2rep.get("plate") or {}).get("source") not in (None, "flat") and psig and psig != g.get("signature"):
            errors.append("grade mono: la plate non usa la stessa curva delle persone (2b)")
        for gp in g.get("people_curve_gap") or []:
            if gp.get("max", 0) > CURVE_GAP_MAX:
                errors.append(f"grade mono: curve misurate diverse tra {gp['pair'][0]} e {gp['pair'][1]} (scarto {gp['max']} livelli "
                              f"> {CURVE_GAP_MAX}): non è la stessa curva")
        gout["pass"] = not any(e.startswith("grade mono") for e in errors)
    out["grade"] = gout
    # cerchio d'accento (disco di campo): ΔL* verso capelli/volto adiacenti e verso il volto, misurati sul render
    discs = [d for d in (sr.get("decos") or []) if str(d.get("kind", "")).startswith("disco")]
    if discs:
        try:
            out["circle"] = [fx.disc_contrast(render, d, heroes, mh, plan["tokens"]) for d in discs]
            for cc in out["circle"]:
                v = cc.get("dL_edge")
                if v is not None and v < SURROUND_ERR:
                    errors.append(f"cerchio d'accento: stacco dai capelli/volto adiacenti ΔL* {v} < {SURROUND_ERR:.0f} (la testa si fonde)")
                elif v is not None and v < SURROUND_WARN:
                    warns.append(f"cerchio d'accento: stacco dai capelli/volto adiacenti ΔL* {v} < {SURROUND_WARN:.0f}")
        except Exception as e:  # noqa: BLE001
            warns.append(f"cerchio d'accento non misurato: {e}")
    # stacco dal feed scuro di YouTube (#0f0f0f): ΔL* della cornice della tile ≥ 25, o un elemento chiaro di cornice
    try:
        es = fx.edge_separation_dark(im)
        out["edge_dark"] = es
        if es["edge_dL_dark"] < EDGE_DARK_MIN and es.get("edge_light_run", es["edge_light_share"]) < EDGE_LIGHT_SHARE:
            warns.append(f"bordo della tile a ΔL* {es['edge_dL_dark']} dal feed scuro (< {EDGE_DARK_MIN:.0f}) e il tratto chiaro "
                         f"continuo più lungo è il {es.get('edge_light_run', 0):.0%} del perimetro (< {EDGE_LIGHT_SHARE:.0%}; chiaro in "
                         f"tutto il {es['edge_light_share']:.0%}): si mimetizza nel feed scuro")
    except Exception as e:  # noqa: BLE001
        warns.append(f"stacco dal feed scuro non misurato: {e}")
    # masse chiare: il busto di una persona (maglia bianca) non deve essere la cosa più chiara dopo titolo e cerchio
    try:
        masses = fx.bright_masses(render, heroes, mh, metrics, discs, plan["tokens"])
        out["bright_masses"] = masses
        for pm in masses.get("people") or []:
            if pm.get("torso_L_p90") is not None and masses.get("ref_L") is not None and pm["torso_L_p90"] > masses["ref_L"] + 1:
                warns.append(f"busto di {pm['cutout']} (L* p90 {pm['torso_L_p90']}) più chiaro di {masses['ref']} (L* {masses['ref_L']}): "
                             "la maglia richiama l'occhio → grade con più spalla o taglio più stretto")
    except Exception as e:  # noqa: BLE001
        warns.append(f"masse chiare non misurate: {e}")
    entry["checks_v2"] = out
    entry["v2"] = plan.get("v2")


# ── Apprendimento: record delle caratteristiche (yt-thumb-learn; solo additivo, mai bloccante) ──────────────
def learn_features(sidecar: dict) -> dict | None:
    """Caratteristiche e metriche del render per l'apprendimento (lib/thumb_learn.py, render_features): template, leva,
    grade, accento usato, classe, forma e parole del gancio, volto %, righe %, plate, fonte del volto, metriche QA."""
    try:
        import thumb_learn
        feats, mets = thumb_learn.render_features(sidecar)
        return {"features": feats, "metrics": mets}
    except Exception as e:  # noqa: BLE001 — l'apprendimento non blocca mai un render
        return {"error": f"{type(e).__name__}: {e}"}


def write_render_index(outdir: Path, plans: list[dict], renders: list[dict]) -> Path | None:
    """<out>/render.json: indice dei render della cartella (fuso con quello esistente: un --only non cancella gli altri),
    con sidecar, esito e caratteristiche per l'apprendimento."""
    try:
        idx_path = outdir / "render.json"
        idx = yc.read_json(idx_path) if idx_path.exists() else {}
        items = idx.get("renders") if isinstance(idx.get("renders"), dict) else {}
        sidecars = {p.get("name"): p.get("sidecar") for p in plans if p.get("name")}
        for r in renders:
            name = r.get("name")
            if not name:
                continue
            items[name] = {"id": r.get("id"), "template": r.get("template"), "png": r.get("png"), "jpg": r.get("jpg"),
                           "sidecar": sidecars.get(name), "ok": r.get("ok"), "pass": r.get("pass"),
                           "errors": len(r.get("errors") or []), "warnings": len(r.get("warnings") or []),
                           "features": (r.get("features") or {}).get("features") if isinstance(r.get("features"), dict) else None}
        yc.write_json(idx_path, {"tool": "yt-thumb-render", "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "renders": items})
        return idx_path
    except Exception as e:  # noqa: BLE001
        yc.log(f"[render.json] indice non scritto: {e}")
        return None


# ── Remotion (ThumbnailStill) ───────────────────────────────────────────────
def remotion_props(spec: dict, template: str, brand: str, debug: bool) -> dict:
    """Spec del concept → props di ThumbnailStill (remotion/src/compositions/ThumbnailStill.tsx)."""
    bgmap = {"gradient": "pastel", "pastel": "pastel", "paper": "paper", "ink": "ink", "dark": "dark", "image": "image"}
    default_bg = "paper" if (yc.brand_tokens(brand).get("colors") or {}).get("paper") else "dark"
    props = {"brand": brand, "text": str(spec.get("text", "")).replace("|", "\n"),
             "background": bgmap.get(spec.get("bg") or default_bg, default_bg),
             "side": spec.get("side") or "right", "faceHeight": float(spec.get("face_frac") or 0.30),
             "showSafeZones": bool(debug)}
    if spec.get("highlight"):
        props["highlight"] = spec["highlight"] if isinstance(spec["highlight"], str) else spec["highlight"][0]
    hero = spec.get("hero") or {}
    if hero.get("path"):
        props.update({"cutoutSrc": hero["path"], "cutoutSize": [hero["w"], hero["h"]],
                      "cutoutBBox": hero.get("alpha_box"), "faceBox": hero.get("face")})
    if spec.get("episode"):
        props["badge"] = spec["episode"]
    if spec.get("kicker"):
        props["kicker"] = spec["kicker"]
    return props


# ── JPEG ────────────────────────────────────────────────────────────────────
def to_jpeg(png: Path, jpg: Path) -> dict:
    from PIL import Image

    im = Image.open(png).convert("RGB")
    for q, sub in ((92, 0), (90, 0), (88, 2), (85, 2), (82, 2), (78, 2), (74, 2), (70, 2), (65, 2)):
        im.save(jpg, "JPEG", quality=q, subsampling=sub, optimize=True, progressive=True)
        size = jpg.stat().st_size
        if size <= JPEG_MAX:
            return {"jpg": str(jpg), "jpg_bytes": size, "jpg_quality": q, "subsampling": "4:4:4" if sub == 0 else "4:2:0"}
    return {"jpg": str(jpg), "jpg_bytes": jpg.stat().st_size, "jpg_quality": 65, "warning": "JPEG ancora > 2 MB"}


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    t0 = time.time()
    outdir = Path(args.out).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    concepts, data_src = load_concepts(args.data)
    base = data_src.parent if data_src else Path.cwd()
    only = set(args.only.split(",")) if args.only else None

    # Espansione varianti: ogni variante eredita il concept e sovrascrive i campi.
    items = []
    for c in concepts:
        if only and str(c.get("id")) not in only:
            continue
        variants = c.get("variants") or [None]
        for vi, v in enumerate(variants, 1):
            item = {k: val for k, val in c.items() if k != "variants"}
            if v:
                item.update(v)
                item["_suffix"] = f"_v{vi}"
            items.append(normalize_concept(item))
    if not items:
        yc.fail("nessun concept da rendere (controlla --only)")

    global_warn: list[str] = []
    prop_requests: list[dict] = []
    jobs, plans = [], []
    for c in items:
        cid = str(c.get("id", "X"))
        channel = channel_of(data_src, c, args.channel)
        defaults = thumb_defaults(channel_profile(channel))
        template = (c.get("template") if args.template == "auto" else args.template) or defaults.get("default_template")
        if not template:
            yc.fail(f"concept {cid}: manca 'template' (o passa --template, o default_template nel profilo del canale)")
        brand = brand_of(template, args.brand, None, c, channel)
        tpl = find_template(template, brand)
        if args.engine == "html" and tpl is None:
            yc.fail(f"template sconosciuto: {template} (disponibili: {', '.join(available_templates())})")
        v2 = base_template(template) in V2_TEMPLATES
        if args.engine == "remotion" and v2:
            yc.fail(f"{template}: i template v2 esistono solo per il motore html (controlli v2, effetti sotto il ritaglio): "
                    "usa --engine html")
        tpl = tpl or TEMPLATES_DIR / f"{template}.html"
        brand = brand_of(template, args.brand, tpl, c, channel)
        tokens = load_tokens(brand, args.tokens, c)
        c = apply_defaults(c, template, defaults)
        warns: list[str] = []
        name = f"{cid}_{template}{c.get('_suffix', '')}"
        png, jpg = outdir / f"{name}.png", outdir / f"{name}.jpg"
        pre_errors: list[str] = []
        try:
            people_src = c.get("people") or ([{k: c[k] for k in ("frame", "cutout", "roi", "point", "mode", "instance", "face", "exclude") if k in c}]
                                             if (c.get("frame") or c.get("cutout")) else [])
            people = []
            for p in people_src:
                h = ensure_person(p, base, outdir, brand, args.force, warns, channel)
                h.update({k: p[k] for k in ("role", "name", "title") if p.get(k)})
                people.append(h)
            if v2 and people and not any(h.get("role") == "guest" for h in people):
                warns.append("nessuna persona con role «guest»: la prima è trattata come ospite")
                people[0]["role"] = people[0].get("role") or "guest"
            artifact = ensure_image(c.get("artifact"), base)
            plate = (ensure_image(c.get("plate"), base) if isinstance(c.get("plate"), str) and c.get("plate")
                     and not str(c.get("plate")).startswith("file:") and not v2 else None)
        except Exception as e:  # asset mancanti: il concept fallisce, gli altri proseguono
            plans.append({"id": cid, "name": name, "template": template, "ok": False, "error": str(e)})
            continue
        spec = {k: v for k, v in c.items() if not k.startswith("_") and k not in ("people", "artifact", "frame", "cutout")}
        spec["highlight"] = default_highlight(c, template)
        spec["hero"] = people[0] if people else None
        spec["people"] = people
        spec["artifact"] = artifact
        if plate:
            spec["plate_src"] = plate["src"]
        v2rep = None
        if v2:
            herr, hw, hinfo = validate_hook(c, template)
            pre_errors += herr
            warns += hw
            nwords = hinfo["words"]
            spec["display_cap"] = c.get("display_cap") or args.display_cap or defaults.get("display_cap") or DISPLAY_CAP
            if str(c.get("guest_style") or "none") not in GUEST_STYLES:
                warns.append(f"guest_style «{c.get('guest_style')}» sconosciuto (none | graphic): uso none")
                spec["guest_style"] = "none"
            # valori ammessi dal profilo del canale (07 §12.4: grade o guest_style non ammessi bloccano il render)
            for key, allowed in (("grade", defaults.get("grade_allowed")), ("guest_style", defaults.get("guest_style_allowed"))):
                if allowed and str(c.get(key)) not in allowed:
                    pre_errors.append(f"{key} «{c.get(key)}» non ammesso dal profilo del canale {channel} ({', '.join(allowed)})")
            if defaults.get("accents"):
                spec["_accents_allowed"] = defaults["accents"]
            try:
                v2rep = prepare_v2(c, spec, template, tokens, brand, outdir, base, warns, args.force, defaults.get("props_budget"))
            except Exception as e:  # noqa: BLE001
                plans.append({"id": cid, "name": name, "template": template, "ok": False, "error": f"preparazione v2: {e}"})
                continue
            v2rep["hook"] = hinfo
            v2rep["brand"] = brand
            v2rep["channel"] = channel
            for rq in v2rep.get("prop_requests") or []:
                prop_requests.append({**rq, "render": name})
        else:
            nwords = len(words_of(c.get("text", "")))
            if nwords > 4:
                warns.append(f"gancio di {nwords} parole (regola: ≤ 4)")
        if nwords == 0:
            warns.append("gancio vuoto")
        rep = title_overlap(c.get("text", ""), c.get("title_pair"))
        if rep:
            warns.append(f"parole ripetute tra thumbnail e titolo: {', '.join(rep)} (P1)")
        pairs, pw = color_pairs(template, {**c, "accent": spec.get("accent", c.get("accent"))} if v2 else c, tokens)   # accent: auto → scelto
        warns += pw
        # Idempotenza: salta se PNG+JPEG esistono, sono più recenti degli input e la spec è identica.
        spec_hash = hashlib.sha1(json.dumps([spec, tokens, template, args.engine], sort_keys=True, default=str).encode()).hexdigest()
        sidecar = outdir / f"{name}.render.json"
        inputs = [tpl, tpl.parent.parent / "tokens.json" if template_brand_dir(tpl) else None, RENDER_JS, data_src, Path(__file__)] \
            + [Path(p["path"]) for p in people] + ([Path(artifact["path"])] if artifact else []) \
            + ([Path(plate["path"])] if plate else []) + [COMMON_JS] \
            + ([Path(__file__).with_name("thumb_fx.py")] if v2 else [])
        fresh = (not args.force and png.exists() and jpg.exists() and sidecar.exists()
                 and yc.read_json(sidecar).get("spec_hash") == spec_hash
                 and mtime(png) >= max(mtime(p) for p in inputs if p))
        plan = {"id": cid, "name": name, "template": template, "brand": brand, "channel": channel, "png": str(png), "jpg": str(jpg),
                "spec": spec, "tokens": tokens, "warnings": warns, "color_pairs": pairs, "spec_hash": spec_hash,
                "sidecar": str(sidecar), "skipped": fresh, "words": nwords, "v2": v2rep, "pre_errors": pre_errors}
        plans.append(plan)
        if not fresh:
            bdir = template_brand_dir(tpl) or yc.brand_dir(brand)
            job = {"id": name, "template": str(tpl), "spec": spec, "tokens": tokens, "out": str(png),
                   "fonts": font_list(tokens, brand, template_brand_dir(tpl)), "brand": brand, "channel": channel,
                   "brand_dir": str(bdir) if bdir else None, "fx_check": v2}
            if args.debug:
                job["debug_out"] = str(outdir / f"{name}_debug.png")
            jobs.append(job)

    results_by_name: dict[str, dict] = {}
    if jobs and args.engine == "html":
        fonts = font_list({})
        jobfile = outdir / ".render_jobs.json"
        yc.write_json(jobfile, {"viewport": {"w": VIEW_W, "h": VIEW_H}, "scale": SCALE, "fonts": fonts, "jobs": jobs})
        ready, why = yc.npm_project_status(yc.NODE_DIR, yc.NODE_PREFIX)
        if not ready:
            yc.fail(f"Playwright non installato: {why}")
        # render_html.mjs resta nel plugin; Playwright si risolve dai node_modules della data dir (YT_NODE_PREFIX)
        proc = yc.run([NODE, RENDER_JS, jobfile], capture=True, check=False, cwd=yc.NODE_DIR,
                      env=yc.node_env({"YT_NODE_PREFIX": str(yc.NODE_PREFIX)}))
        for line in (proc.stderr or "").splitlines():
            yc.log(line)
        try:
            res = json.loads(proc.stdout)
        except json.JSONDecodeError:
            yc.fail(f"render_html.mjs: output non JSON (exit {proc.returncode})", stderr=proc.stderr[-2000:])
        if res.get("error"):
            yc.fail(f"render_html.mjs: {res['error'][:1500]}")
        for r in res.get("results", []):
            results_by_name[r["id"]] = r
        jobfile.unlink(missing_ok=True)
    elif jobs and args.engine == "remotion":
        remotion = next((b / "yt-remotion" for b in ([yc.PLUGIN_ROOT / "bin"] if yc.PLUGIN_ROOT else []) + [yc.YT_HOME / "bin"]
                         if (b / "yt-remotion").exists()), None)
        if remotion is None:
            yc.fail("engine remotion non disponibile: manca bin/yt-remotion (usa --engine html)")
        for job in jobs:
            brand = job.get("brand") or brand_of(Path(job["template"]).stem, args.brand)
            if not yc.remotion_allowed(brand, job.get("channel")):
                yc.fail("engine remotion solo per i brand propri (canale con kind: own o personal, o token \"own\": true; "
                        "licenza Remotion, design §11): per i clienti usa --engine html")
            props = outdir / "props" / f"{job['id']}.json"
            yc.write_json(props, remotion_props(job["spec"], Path(job["template"]).stem, brand, args.debug))
            proc = yc.run([remotion, "still", "ThumbnailStill", "--props", props, "--out", job["out"], "--scale", str(SCALE)]
                          + (["--force"] if args.force else []), capture=True, check=False)
            try:
                rj = json.loads(proc.stdout)
            except json.JSONDecodeError:
                rj = {"ok": False, "error": (proc.stderr or "")[-800:]}
            # il motore remotion non restituisce le metriche di layout: niente controlli geometrici né box
            # del testo per yt-thumb-qa → lo diciamo, e riportiamo gli avvisi di yt-remotion
            rwarn = [f"remotion: {w}" for w in (rj.get("warnings") or [])]
            rwarn.append("motore remotion: controlli geometrici (zona timestamp, testo sul volto) non eseguiti; "
                         "yt-thumb-qa richiede --text-box per misurare il contrasto del gancio")
            results_by_name[job["id"]] = {"ok": bool(rj.get("ok")) and Path(job["out"]).exists(), "error": rj.get("error"),
                                          "metrics": {"warnings": rwarn}, "engine_out": rj}

    renders, all_pass = [], True
    for plan in plans:
        if plan.get("ok") is False:
            renders.append({k: plan[k] for k in ("id", "name", "template", "ok", "error")})
            all_pass = False
            continue
        entry = {k: plan[k] for k in ("id", "name", "template", "png", "jpg", "warnings", "color_pairs", "words", "skipped")}
        entry.update({"brand": plan.get("brand"), "channel": plan.get("channel"), "palette": palette_of(plan["tokens"])})
        if plan["skipped"]:
            prev = yc.read_json(plan["sidecar"])
            entry.update({k: prev.get(k) for k in ("checks", "checks2", "checks_v2", "v2", "errors", "metrics", "jpg_bytes", "jpg_quality",
                                                   "text_over_subject", "spotify_png", "features")})
            entry["warnings"] = prev.get("warnings", entry["warnings"])
            entry["ok"] = True
            entry["pass"] = not entry.get("errors")
        else:
            r = results_by_name.get(plan["name"], {"ok": False, "error": "nessun risultato dal renderer"})
            entry["ok"] = bool(r.get("ok"))
            if not entry["ok"]:
                entry["error"] = r.get("error")
                all_pass = False
                renders.append(entry)
                continue
            m = r.get("metrics") or {}
            entry["checks"] = m.get("checks", {})
            entry["errors"] = plan.get("pre_errors", []) + m.get("errors", [])
            entry["warnings"] = plan["warnings"] + m.get("warnings", [])
            entry["metrics"] = {"texts": m.get("texts", []), "heroes": m.get("heroes", [])}
            heroes = plan["spec"].get("people") or []
            if heroes and m.get("heroes"):
                # v2: targhetta e riga meta stanno sul busto per scelta; conta solo il titolo
                tos = text_over_subject({**m, "texts": [t for t in m.get("texts", []) if t.get("kind") == "hook"]}
                                        if base_template(plan["template"]) in V2_TEMPLATES else m, heroes)
                entry["text_over_subject"] = tos
                if tos > 0.04:
                    entry["warnings"].append(f"{tos:.0%} del testo sta sopra il soggetto")
            if r.get("console"):
                entry["warnings"] += [f"console: {c[:200]}" for c in r["console"]]
            if args.engine == "html":
                post_render_checks(plan, entry, m, args.max_upscale,
                                   plan["spec"].get("display_cap") or args.display_cap or DISPLAY_CAP)
                if base_template(plan["template"]) in V2_TEMPLATES:
                    post_render_v2(plan, entry, m, r.get("fx"))
                    for f in (r.get("fx") or {}).get("files") or []:
                        Path(f).unlink(missing_ok=True)
                entry["metrics"]["series"] = m.get("series")
            entry.update(to_jpeg(Path(plan["png"]), Path(plan["jpg"])))
            if args.spotify:
                sp = Path(plan["png"]).with_name(plan["name"] + "_spotify-1920x1080.png")
                from PIL import Image
                Image.open(plan["png"]).convert("RGB").resize((1920, 1080), Image.LANCZOS).save(sp, optimize=True)
                entry["spotify_png"] = str(sp)
            if args.debug:
                entry["debug_png"] = str(Path(plan["png"]).with_name(plan["name"] + "_debug.png"))
            entry["pass"] = not entry["errors"]
            entry["features"] = learn_features({**entry, "spec": plan["spec"]})   # apprendimento (yt-thumb-learn), additivo
            yc.write_json(plan["sidecar"], {**entry, "spec_hash": plan["spec_hash"], "spec": plan["spec"]})
        if not entry.get("pass", False):
            all_pass = False
        renders.append(entry)

    ok = all(r.get("ok") for r in renders)
    # avvisi dei singoli render anche nel riepilogo (contratto §8: warnings di primo livello)
    for r in renders:
        for w in r.get("warnings") or []:
            msg = f"{r.get('name', r.get('id'))}: {w}"
            if msg not in global_warn:
                global_warn.append(msg)
    outputs = {"renders": renders, "dir": str(outdir)}
    index = write_render_index(outdir, plans, renders)
    if index:
        outputs["index"] = str(index)
    if prop_requests:
        pr = outdir / "prop_requests.json"
        yc.write_json(pr, {"note": "Richieste di prop/plate da SOLO TESTO. Nessuna chiamata fatta: preventivo crediti e OK "
                                   "esplicito nella sessione principale; tetto di spesa del profilo (default €5 a episodio, €20 al "
                                   "mese); mai volti, mai upload.",
                           "requests": prop_requests})
        outputs["prop_requests"] = str(pr)
    yc.emit(ok, engine=args.engine, outputs=outputs, all_checks_pass=all_pass,
            warnings=global_warn, seconds=round(time.time() - t0, 2))
    # 0 = render prodotti e controlli passati; 3 = render prodotti ma controlli falliti (07 §12.4); 1 = render mancanti
    sys.exit(0 if ok and all_pass else (3 if ok else 1))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # errori inattesi → JSON leggibile, non traceback su stdout
        import traceback
        traceback.print_exc(file=sys.stderr)
        yc.fail(f"{type(exc).__name__}: {exc}")
