"""yt-glossary — glossario dell'episodio PRIMA della trascrizione, da fonti verificabili.

Uso:
  yt-glossary WORKDIR                                   # project.json + glossario e confusioni del canale
  yt-glossary WORKDIR --doc "<nota di preparazione.md>" [--doc altra.md]      # note lette, mai scritte
  yt-glossary WORKDIR --web analysis/web.json           # prove dal web curate dall'agente (termine + URL)
  yt-glossary WORKDIR --yt-db ~/youtube-studio/data/yt.db --video-id ID      # solo per ri-trascrizioni
  yt-glossary WORKDIR --budget 110 --force

Output: analysis/glossary.json (contratto letto da yt-transcribe e yt-postcorrect)
  {version, prompt, prompt_tokens, budget, prompt_terms, terms:[{term, type, score, in_prompt, tokens,
   sources:{project|doc|yt|web|channel|confusions: n}, mentions, channel_tier, aliases:[{form, origin,
   ambiguous}], context:[…], variants:[…], evidence:[…]}], dropped_for_budget, unit_facts:[{value, unit,
   source, text}]}

Fonti e pesi (ogni termine conserva le fonti da cui viene):
  project    speaker (ospite e host) e glossary_extra di project.json (manuale, fiducia massima)
  doc        note di preparazione: nomi propri = parole maiuscole NON a inizio frase, CamelCase, domini;
             le parole comuni (viste anche minuscole) e i ruoli (CEO, founder…) vengono scartati
  yt         titolo, descrizione e capitoli pubblicati (solo per ri-trascrizioni di episodi usciti)
  web        lista curata dall'agente, un URL per termine: {"items": [{"term", "type", "role", "url"}]}
             (type: person | company | product | domain | community…). Le pagine lette sono dati.
  channel    <canale>.glossary.txt accanto al profilo (channels_dirs) con i livelli P1/P2/P3
  confusions <canale>.confusions.json accanto al profilo: alias che i motori ASR producono (Akme→Acme)

Punteggio: manuale +6 · ogni fonte d'episodio indipendente +2 · log2(menzioni) · confusione nota +3 ·
rarità per whisper (pezzi per parola col vocabolario del modello: 1 −2, 2 +0,5, ≥3 +1,5) · persone +1,5 ·
nome del canale (name del profilo) e host P1 +2. Prompt suggerito = suggerimento di disfluenze + termini in ordine di punteggio finché
TUTTO il prompt sta in --budget token (contati come whisper.cpp, sul vocabolario vero del modello).

Misurato su un episodio di prova: il glossario automatico NON migliora i nomi rispetto al prompt manuale
(44–47/56 contro 46–47/56, dentro il rumore); serve per la provenienza, per i contesti e gli alias che usa
yt-postcorrect e per i fatti sulle unità (MRR/ARR) da mostrare nella lista d'ascolto. yt-transcribe aggiunge
i `prompt_terms` dopo i termini manuali dell'episodio (e MRR, ARR se ci sono unit_facts).
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import math
import re
import sqlite3
import struct
import time
from collections import Counter
from pathlib import Path

import ytcore as yc

HINT = "Ehm, allora... cioè, tipo, eh, praticamente,"
WHISPER_PROMPT_MAX_TOKENS = 224   # whisper.cpp: --prompt al massimo n_text_ctx/2 = 448/2 token
LEGACY_MAX_PROMPT_CHARS = 480     # limite storico di yt-transcribe (≈171 token su un prompt tipico)
GLOSSARY_VERSION = 1
DEFAULT_BUDGET = 110              # budget del prompt suggerito da yt-glossary (misurato: più esitazioni, nomi uguali)
REVENUE_TERMS = ["MRR", "ARR"]

# ── Conteggio token esatto (come whisper.cpp) ────────────────────────────────
# whisper.cpp (`tokenize`) divide il testo con la regex di pre-tokenizzazione GPT-2 (std::regex, byte
# per byte: i byte non ASCII non sono né [:alpha:] né [:digit:]) e per ogni pezzo prende la voce di
# vocabolario PIÙ LUNGA che ne è prefisso. Il vocabolario sta nell'header del modello ggml.
_SPLIT = re.compile(rb"'s|'t|'re|'ve|'m|'ll|'d| ?[A-Za-z]+| ?[0-9]+| ?[^\sA-Za-z0-9]+|\s+(?!\S)|\s+")


@functools.lru_cache(maxsize=2)
def _vocab(model: str) -> tuple[frozenset, int]:
    with open(model, "rb") as f:
        magic, = struct.unpack("<I", f.read(4))
        if magic != 0x67676D6C:
            raise ValueError(f"non è un modello whisper ggml: {model}")
        hp = struct.unpack("<11i", f.read(44))
        n_text_ctx = hp[5]
        n_mel, n_fft = struct.unpack("<2i", f.read(8))
        f.seek(n_mel * n_fft * 4, 1)
        n_vocab, = struct.unpack("<i", f.read(4))
        toks = set()
        for _ in range(n_vocab):
            ln, = struct.unpack("<I", f.read(4))
            toks.add(f.read(ln))
    return frozenset(toks), n_text_ctx


def tokenize(text: str, model: Path | str | None = None) -> list[bytes]:
    tok, _ = _vocab(str(model or yc.WHISPER_MODEL))
    out: list[bytes] = []
    for m in _SPLIT.finditer(text.encode("utf-8")):
        word = m.group(0)
        i, n = 0, len(word)
        while i < n:
            j = n
            while j > i and word[i:j] not in tok:
                j -= 1
            if j == i:          # byte sconosciuto: whisper.cpp lo salta
                i += 1
                continue
            out.append(word[i:j])
            i = j
    return out


def count_tokens(text: str, model: Path | str | None = None) -> int:
    """Token del prompt come li conta whisper.cpp; senza modello leggibile, stima ~2,8 caratteri/token."""
    try:
        return len(tokenize(text, model))
    except (OSError, ValueError, struct.error):
        return math.ceil(len(text) / 2.8)


# ── Glossario e confusioni del canale ────────────────────────────────────────
def _learned_path(slug: str, suffix: str) -> Path | None:
    """File appreso da yt-learn (<studio>/data/learned/<slug><suffix>), None se lo slug non è valido."""
    try:
        return yc.learned_file(slug, suffix) if slug else None
    except ValueError:
        return None


def channel_terms(slug: str, extra: Path | str | None = None) -> list[dict]:
    """Voci del glossario canale con il livello (P1/P2/P3…) dalle intestazioni «# ── P1 …».
    Poi le voci apprese da yt-learn (<studio>/data/learned/<slug>.glossary.txt), sempre P3: entrano nel prompt
    solo se l'episodio le nomina (la promozione a P1/P2 passa da una PR sul glossario del plugin, Tier B).
    Le voci di `extra` (glossary.txt nella cartella di lavoro, facoltativo) valgono come episodio."""
    out: list[dict] = []
    seen: set[str] = set()
    for path, default_tier in ((yc.channel_file(slug, ".glossary.txt"), "P1"),
                               (_learned_path(slug, ".glossary.txt"), "P3"),
                               (Path(extra) if extra else None, "episode")):
        if not path or not Path(path).exists():
            continue
        tier = default_tier
        for line in Path(path).read_text().splitlines():
            m = re.match(r"#\s*──\s*(P\d)", line)
            if m and default_tier not in ("episode", "P3"):
                tier = m.group(1)
                continue
            t = line.split("#", 1)[0].strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append({"term": t, "tier": tier})
    return out


def confusions_path(slug: str) -> Path:
    return yc.channel_file(slug, ".confusions.json")


def load_confusions(slug: str, path: Path | str | None = None) -> dict:
    """Confusioni ASR: il file `path` se indicato; altrimenti quelle del canale fuse con le apprese da yt-learn
    (ytcore.channel_confusions: <slug>.confusions.json + <studio>/data/learned/<slug>.confusions.json)."""
    if not path:
        return yc.channel_confusions(slug)
    p = Path(path)
    if not p.exists():
        return {"confusions": []}
    data = yc.read_json(p)
    data.setdefault("confusions", [])
    return data


def channel_hosts(slug: str) -> list[str]:
    """Nomi pubblici degli host dal profilo canale (voice.public_names.hosts)."""
    try:
        ch = yc.load_channel(slug)
    except Exception:
        return []
    hosts = ((ch.get("voice") or {}).get("public_names") or {}).get("hosts") or []
    return [h for h in hosts if isinstance(h, str)]


def glossary_path(workdir: Path) -> Path:
    return workdir / "analysis" / "glossary.json"


def load_glossary_doc(workdir: Path) -> dict | None:
    p = glossary_path(workdir)
    if not p.exists():
        return None
    try:
        return yc.read_json(p)
    except Exception:
        return None


# ── Prompt per whisper (yt-transcribe) ───────────────────────────────────────
def split_extra(extra: str | None) -> list[str]:
    return [t.strip() for t in re.split(r"[,\n;]+", extra or "") if t.strip()]


def ranked_prompt_terms(project: dict, workdir: Path, extra: str | None,
                        glossary_doc: dict | None = None) -> list[dict]:
    """Termini in ordine di priorità, ognuno con la sua origine:
    1. episodio manuale: project.json glossary_extra, poi --prompt-extra;
    2. MRR, ARR se il glossario automatico ha fatti sulle unità (l'episodio parla di ricavi: senza questi
       due acronimi nel prompt gli slot dopo una cifra diventano non-parole);
    3. prompt_terms di analysis/glossary.json (yt-glossary), in ordine di punteggio;
    4. glossario canale: P1, poi P2; P3 e oltre solo se l'episodio li nomina (regola del file del canale)."""
    slug = project.get("channel", "")
    manual = list(project.get("glossary_extra") or []) + split_extra(extra)
    episode_keys = {t.lower() for t in manual}
    auto = list((glossary_doc or {}).get("prompt_terms") or [])
    episode_keys |= {t.lower() for t in auto}
    rows: list[dict] = [{"term": t, "origin": "episode"} for t in manual]
    if glossary_doc and glossary_doc.get("unit_facts"):
        rows += [{"term": t, "origin": "revenue"} for t in REVENUE_TERMS]
    rows += [{"term": t, "origin": "glossary.json"} for t in auto]
    for c in channel_terms(slug, workdir / "glossary.txt"):
        if c["tier"] in ("P1", "P2", "episode") or c["term"].lower() in episode_keys:
            rows.append({"term": c["term"], "origin": f"channel:{c['tier']}"})
    out, seen = [], set()
    for r in rows:
        k = r["term"].lower()
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def build_prompt(project: dict, workdir: Path, extra: str | None, budget: int | None = None,
                 glossary_doc: dict | None = None, model: Path | None = None) -> tuple[str, list[str], list[str], dict]:
    """Prompt = suggerimento di disfluenze + termini in ordine di priorità, riempito in modo greedy.

    budget None → limite storico di 480 caratteri (≈171 token: il prompt lungo, che resta il default);
    budget N → al massimo N token. Sempre ≤ 224 token (oltre, whisper.cpp tronca). Ritorna
    (prompt, termini usati, termini scartati, info)."""
    rows = ranked_prompt_terms(project, workdir, extra, glossary_doc)
    limit = min(budget or WHISPER_PROMPT_MAX_TOKENS, WHISPER_PROMPT_MAX_TOKENS)
    used: list[str] = []
    dropped: list[str] = []
    origins: dict[str, str] = {}
    for r in rows:
        cand = f"{HINT} {', '.join(used + [r['term']])}."
        ok = (budget is not None or len(cand) <= LEGACY_MAX_PROMPT_CHARS) and count_tokens(cand, model) <= limit
        if ok:
            used.append(r["term"])
            origins[r["term"]] = r["origin"]
        else:
            dropped.append(r["term"])
    prompt = f"{HINT} {', '.join(used)}." if used else HINT
    info = {"builder": 2, "budget_tokens": budget, "limit": "tokens" if budget else f"{LEGACY_MAX_PROMPT_CHARS} chars",
            "tokens": count_tokens(prompt, model), "chars": len(prompt),
            "origins": dict(Counter(origins.values())),
            "glossary_json": bool(glossary_doc)}
    return prompt, used, dropped, info


# ── Glossario automatico (yt-glossary) ───────────────────────────────────────
ROLE_WORDS = {"ceo", "coo", "cto", "cfo", "co-founder", "cofounder", "founder", "head", "growth", "business",
              "analyst", "series", "senior", "software", "engineer", "partner", "socio", "guest", "host"}
MONTHS = {"gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic", "gennaio",
          "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre", "estate", "inverno", "primavera", "autunno", "oggi", "martedì", "lunedì"}
FUNCTION = {"il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "di", "da", "in", "con", "su", "per", "tra",
            "fra", "e", "o", "ma", "se", "che", "come", "cosa", "chi", "dove", "quando", "quale", "qual", "quanto",
            "perché", "the", "a", "an", "of", "and", "or", "to", "is", "in", "on", "for", "with", "nota", "note",
            "link", "via", "vs", "ok"}
INFRA_DOMAINS = {"github.com", "linkedin.com", "x.com", "twitter.com", "cal.com", "luma.com", "youtube.com",
                 "medium.com", "crunchbase.com", "lu.ma", "www.linkedin.com"}
# vocabolario generico, fissato prima di guardare l'episodio; yt-postcorrect aggiunge al contesto
# "ai_tool" le aziende e i prodotti affidabili dell'episodio
GENERIC_AI = ["AI", "IA", "GPT", "ChatGPT", "OpenAI", "Anthropic", "Gemini", "Copilot", "Cursor", "LLM",
              "modello", "modelli", "agente", "agenti", "agent", "prompt", "chatbot", "Code", "Sonnet", "Opus",
              "Mistral", "Llama", "Perplexity"]
TYPE_CONTEXT = {
    "ai_tool": GENERIC_AI,
    "person": ["CEO", "COO", "CTO", "founder", "co-founder", "cofondatore", "fondatore", "socio", "soci",
               "partner", "team", "azienda", "startup"],
}


def strip_markdown(md: str) -> str:
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.S)
    md = re.sub(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]", r"\1", md)
    md = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", md)
    md = re.sub(r"[*_`>#]+", " ", md)
    return md


def find_domains(text: str) -> Counter:
    out: Counter = Counter()
    for m in re.finditer(r"(?:https?://)?(?:www\.)?((?:[a-z0-9][a-z0-9-]*\.)+(?:com|ai|io|so|it|co|me|app|dev|net))\b",
                         text, re.I):
        d = m.group(1).lower()
        if d in INFRA_DOMAINS or d.endswith(("linkedin.com", "github.com", "x.com")):
            continue
        out[d] += 1
    return out


def proper_nouns(text: str) -> tuple[Counter, set[str]]:
    """Sequenze maiuscole non a inizio frase e parole CamelCase → (conteggi, vocabolario minuscolo).
    Una sequenza si interrompe a ogni punteggiatura, slash, trattino o parentesi tra parole e ai numeri."""
    found: Counter = Counter()
    lower_vocab: set[str] = set()
    word_rx = re.compile(r"[A-Za-zÀ-ÿ0-9][\w&'’.\-]*[\w&]|[A-Za-zÀ-ÿ0-9]")
    for line in text.splitlines():
        line = line.strip(" -\t")
        if not line:
            continue
        state = {"start": True, "seq": [], "initial": False}

        def flush() -> None:
            words = [w for w in state["seq"] if not re.fullmatch(r"[A-Z]\.?", w)]
            if words:
                single_plain = len(words) == 1 and not re.search(r"[a-z][A-Z]|[A-Z]{2}", words[0])
                if not (state["initial"] and single_plain):
                    if state["initial"] and len(words) > 1 and words[0].lower() in FUNCTION | MONTHS:
                        words = words[1:]
                    found[" ".join(words)] += 1
            state["seq"], state["initial"] = [], False

        pos = 0
        for m in word_rx.finditer(line):
            gap = line[pos:m.start()]
            pos = m.end()
            t = m.group(0)
            if gap.strip():
                flush()
                if re.search(r"[.!?…:\]\)»”\"]", gap) or re.search(r"(^|\s)[-–—](\s|$)", gap):
                    state["start"] = True
            clean = t.strip("’'.-")
            trailing_stop = t.endswith(".") and not re.fullmatch(r"[A-Z]\.", t) and not re.search(r"\.[a-z]{2,}$", t)
            if not clean:
                continue
            has_digit = bool(re.search(r"\d", clean))
            is_domain = bool(re.search(r"\.[a-z]{2,}$", clean))
            is_cap = bool(re.match(r"[A-Z]", clean))
            camel = bool(re.search(r"[a-z][A-Z]|[A-Z]{2,}[a-z]|[a-z]{2,}[A-Z]{2,}", clean))
            if has_digit and not is_domain:
                flush()
                state["start"] = False
            elif (is_cap or camel) and not is_domain:
                if not state["seq"]:
                    state["initial"] = state["start"]
                state["seq"].append(clean)
                state["start"] = False
            else:
                flush()
                lower_vocab.add(clean.lower())
                state["start"] = False
            if trailing_stop:
                flush()
                state["start"] = True
        flush()
    return found, lower_vocab


def split_terms(found: Counter, lower_vocab: set[str]) -> Counter:
    out: Counter = Counter()
    for term, n in found.items():
        words = term.split()
        lw = [w.lower().strip("'’") for w in words]
        if all(w in ROLE_WORDS | MONTHS | FUNCTION for w in lw):
            continue
        if re.fullmatch(r"[\d.,%$€k+-]+", term.lower()):
            continue
        if len(words) == 1:
            w = words[0]
            if lw[0] in lower_vocab and not re.search(r"[a-z][A-Z]", w):
                continue
            if lw[0] in FUNCTION | MONTHS | ROLE_WORDS or len(w) < 3:
                continue
        if len(words) > 4 or (len(words) > 1 and all(w.isupper() for w in words)):
            continue
        out[term] += n
    return out


def term_key(term: str) -> str:
    return re.sub(r"[^a-z0-9]", "", term.lower())


def from_ytdb(db: Path, vid: str) -> str:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("select title, description, chapters_json from videos where id=?", (vid,)).fetchone()
    finally:
        con.close()
    if not row:
        return ""
    title, desc, chap = row
    chapters = " . ".join(c.get("title", "") for c in json.loads(chap or "[]"))
    return f"{title or ''} .\n{desc or ''}\n{chapters}"


def channel_name(slug: str) -> str:
    """Nome del canale dal profilo (`name`), "" se manca o è ancora un segnaposto «[…]»."""
    try:
        name = yc.load_channel(slug).get("name") if slug else None
    except Exception:
        return ""
    return name.strip() if isinstance(name, str) and name.strip() and not name.strip().startswith("[") else ""


def render(terms: list[str], style: str, guest: str = "", channel: str = "") -> str:
    if not terms:
        return HINT
    if style == "sentence":
        rest = [t for t in terms if t not in (guest, channel)]
        where = f" {channel}:" if channel else ""
        head = f"{HINT}{where} oggi parliamo con {guest} di " if guest else f"{HINT} parliamo di "
        return head + ", ".join(rest) + "."
    return f"{HINT} {', '.join(terms)}."


def build_glossary(workdir: Path, project: dict, docs: list[str] | None = None, web: str | None = None,
                   yt_db: str | None = None, video_id: str | None = None, confusions: str | None = None,
                   budget: int = DEFAULT_BUDGET, style: str = "list") -> dict:
    """Glossario dell'episodio con provenienza, punteggi, alias, contesti e fatti sulle unità."""
    slug = project.get("channel", "")
    terms: dict[str, dict] = {}
    web_items = yc.read_json(Path(web).expanduser())["items"] if web else []

    def add(term: str, src: str, n: int = 1, ttype: str | None = None, extra: dict | None = None) -> None:
        term = term.strip()
        k = term_key(term)
        if not term or not k:
            return
        e = terms.setdefault(k, {"term": term, "variants": Counter(), "sources": {}, "mentions": 0,
                                 "type": None, "evidence": []})
        e["variants"][term] += n
        e["sources"][src] = e["sources"].get(src, 0) + n
        if src != "channel":
            e["mentions"] += n
        if ttype and not e["type"]:
            e["type"] = ttype
        if extra:
            e["evidence"].append(extra)

    speakers = project.get("speakers") or {}
    hosts = set(channel_hosts(slug))
    cname = channel_name(slug)
    for sid, name in speakers.items():
        if isinstance(name, str) and name.strip():
            add(name, "project", 3, "person:host" if name in hosts else "person:guest")
    for t in project.get("glossary_extra") or []:
        add(t, "project", 3)

    doc_texts = []
    for p in docs or []:
        txt = strip_markdown(Path(p).expanduser().read_text())
        doc_texts.append(txt)
        found, lv = proper_nouns(txt)
        for t, n in split_terms(found, lv).items():
            add(t, "doc", n)
        for d, n in find_domains(txt).items():
            add(d, "doc", n, "domain")

    yt_text = ""
    if yt_db and video_id:
        yt_text = from_ytdb(Path(yt_db).expanduser(), video_id)
        found, lv = proper_nouns(yt_text)
        for t, n in split_terms(found, lv).items():
            add(t, "yt", n)
        for d, n in find_domains(yt_text).items():
            add(d, "yt", n, "domain")

    # fatti sulle unità ("$40K ARR", "10K MRR"): solo prove per gli slot da ascoltare, mai correzioni
    unit_facts = []
    for label, txt in [("doc", t) for t in doc_texts] + ([("yt", yt_text)] if yt_text else []):
        for m in re.finditer(r"\$?(\d+(?:[.,]\d+)?)\s*([kKmM])?\s*(MRR|ARR)\b", txt):
            a, b = max(0, m.start() - 60), min(len(txt), m.end() + 40)
            unit_facts.append({"value": (m.group(1).replace(",", ".") + (m.group(2) or "").lower()),
                               "unit": m.group(3), "source": label, "text": " ".join(txt[a:b].split())})

    for it in web_items:
        add(it["term"], "web", 1, it.get("type"), {"url": it.get("url", ""), "role": it.get("role", "")})

    for c in channel_terms(slug):
        add(c["term"], "channel", 1, None, {"tier": c["tier"]})
        terms[term_key(c["term"])].setdefault("tier", c["tier"])

    conf = load_confusions(slug, confusions)
    for c in conf.get("confusions", []):
        k = term_key(c["term"])
        if k not in terms:
            add(c["term"], "confusions", 0)
        e = terms[k]
        for a in c.get("aliases", []):
            e.setdefault("aliases", []).append({"form": a, "origin": c.get("origin", "a-priori"),
                                                "ambiguous": a in (c.get("ambiguous") or []),
                                                "evidence": c.get("evidence", "")})
        if c.get("context"):
            e["context_type"] = c["context"]
        if c.get("context_words"):          # confusioni apprese (yt-learn): entità viste vicino alle correzioni
            e.setdefault("context_extra", [])
            e["context_extra"] += [w for w in c["context_words"] if isinstance(w, str) and w not in e["context_extra"]]
        if c.get("type") and not e["type"]:
            e["type"] = c["type"]

    # "Acme AI" e "Acme": una voce sola (le due grafie restano varianti)
    for k in list(terms):
        e = terms[k]
        m = re.fullmatch(r"(.+?)(ai)", k)
        if m and m.group(1) in terms and len(m.group(1)) >= 4:
            base = terms[m.group(1)]
            base["variants"].update(e["variants"])
            for s, n in e["sources"].items():
                base["sources"][s] = base["sources"].get(s, 0) + n
            base["mentions"] += e["mentions"]
            base.setdefault("merged", []).append(e["term"])
            del terms[k]

    manual_set = set(project.get("glossary_extra") or []) | {v for v in speakers.values() if isinstance(v, str)}
    for e in terms.values():
        manual = [v for v in e["variants"] if v in manual_set]
        webv = [x for x in web_items if term_key(x["term"]) == term_key(e["term"])]
        if manual:
            e["term"] = manual[0]
        elif webv:
            e["term"] = webv[0]["term"]
        else:
            e["term"] = e["variants"].most_common(1)[0][0]

    paragraphs = [p for t in doc_texts + [yt_text] for p in re.split(r"\n\s*\n", t) if p.strip()]
    generic = {"arr", "mrr", "saas", "microsaas", "mvp", "ai", "italia", "roma", "linkedin", "twitter", "github"}
    episode_keys = {k for k, e in terms.items()
                    if k not in generic and (e["sources"].get("project")
                                             or len(set(e["sources"]) & {"doc", "yt", "web"}) >= 2)}
    for k, e in terms.items():
        ctx: Counter = Counter()
        pat = re.compile(rf"(?<!\w){re.escape(e['term'])}(?!\w)", re.I)
        for p in paragraphs:
            if pat.search(p):
                for k2 in episode_keys:
                    if k2 != k and re.search(rf"(?<!\w){re.escape(terms[k2]['term'])}(?!\w)", p, re.I):
                        ctx[terms[k2]["term"]] += 1
        ttype = e.get("context_type") or ("person" if (e["type"] or "").startswith("person") else None)
        e["context"] = [t for t, _ in ctx.most_common(25)] + TYPE_CONTEXT.get(ttype or "", [])
        e["context"] += [w for w in e.get("context_extra") or [] if w not in e["context"]]

    rows = []
    for k, e in terms.items():
        src = e["sources"]
        episode_srcs = [s for s in ("project", "doc", "yt", "web") if src.get(s)]
        toks = count_tokens(" " + e["term"])
        ppw = toks / max(1, len(e["term"].split()))
        s = 0.0
        s += 6 if src.get("project") else 0
        s += 2 * len([x for x in episode_srcs if x != "project"])
        s += math.log2(1 + e["mentions"]) if e["mentions"] else 0
        s += 3 if any(a["origin"] == "a-priori" for a in e.get("aliases", [])) else 0
        s += -2 if ppw <= 1 else (0.5 if ppw < 3 else 1.5)
        s += 1.5 if (e["type"] or "").startswith("person") else 0
        tier = e.get("tier")
        brand = tier == "P1" and ((cname and k == term_key(cname)) or e["term"] in speakers.values())
        s += 2 if brand else 0
        rows.append({"term": e["term"], "type": e["type"], "score": round(s, 2), "tokens": toks,
                     "eligible_for_prompt": bool(episode_srcs) or brand, "sources": src,
                     "mentions": e["mentions"], "channel_tier": tier, "aliases": e.get("aliases", []),
                     "context": e["context"],
                     "variants": [v for v in e["variants"] if v != e["term"]] + e.get("merged", []),
                     "evidence": e["evidence"]})
    rows.sort(key=lambda r: (-r["score"], r["term"]))

    guest = next((v for v in speakers.values() if isinstance(v, str) and v not in hosts), "")
    chosen: list[str] = []
    dropped: list[dict] = []
    for r in rows:
        if not r["eligible_for_prompt"]:
            continue
        words = set(r["term"].lower().split())
        if any(words < set(c.lower().split()) for c in chosen):
            continue
        n = count_tokens(render(chosen + [r["term"]], style, guest, cname))
        if n <= budget:
            chosen.append(r["term"])
        else:
            dropped.append({"term": r["term"], "score": r["score"], "reason": f"budget ({n} > {budget})"})
    for r in rows:
        r["in_prompt"] = r["term"] in chosen
    prompt = render(chosen, style, guest, cname)
    return {"version": GLOSSARY_VERSION, "workdir": str(workdir), "style": style, "budget": budget,
            "prompt": prompt, "prompt_tokens": count_tokens(prompt), "prompt_chars": len(prompt),
            "prompt_terms": chosen, "hint": HINT,
            "sources_used": {"doc": [str(p) for p in docs or []],
                             "yt": f"{yt_db}#{video_id}" if yt_db and video_id else None,
                             "web": web, "confusions": str(confusions) if confusions else
                             (", ".join(conf.get("sources") or []) or str(confusions_path(slug))),
                             "channel": str(yc.channel_file(slug, ".glossary.txt"))},
            "terms": rows, "dropped_for_budget": dropped, "unit_facts": unit_facts}


def _inputs_signature(args: argparse.Namespace, project_path: Path, slug: str) -> str:
    h = hashlib.sha256()
    h.update(json.dumps([GLOSSARY_VERSION, args.budget, args.style, args.video_id, args.yt_db,
                         sorted(args.doc or [])], sort_keys=True).encode())
    paths = [project_path, yc.channel_file(slug, ".glossary.txt"),
             Path(args.confusions).expanduser() if args.confusions else confusions_path(slug)]
    paths += [p for p in (_learned_path(slug, ".glossary.txt"),
                          None if args.confusions else _learned_path(slug, ".confusions.json")) if p]
    paths += [Path(p).expanduser() for p in args.doc or []]
    if args.web:
        paths.append(Path(args.web).expanduser())
    for p in paths:
        h.update(str(p).encode())
        if p.exists():
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()[:20]


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-glossary", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--doc", action="append", help="nota di preparazione (markdown, sola lettura); ripetibile")
    ap.add_argument("--web", default=None, help="JSON curato dall'agente: {items:[{term, type, role, url}]}")
    ap.add_argument("--yt-db", default=None, help="yt.db per titolo/descrizione/capitoli pubblicati (con --video-id)")
    ap.add_argument("--video-id", default=None, help="id del video pubblicato (solo ri-trascrizioni)")
    ap.add_argument("--confusions", default=None,
                    help="file delle confusioni ASR (default <canale>.confusions.json accanto al profilo)")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                    help=f"token del prompt suggerito (default {DEFAULT_BUDGET}; massimo {WHISPER_PROMPT_MAX_TOKENS})")
    ap.add_argument("--style", choices=["list", "sentence"], default="list", help="forma del prompt suggerito")
    ap.add_argument("--out", default=None, help="file di output (default analysis/glossary.json)")
    ap.add_argument("--force", action="store_true", help="rifà anche se l'output è aggiornato")
    args = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(args.workdir)
        project = yc.load_project(workdir)
    except FileNotFoundError as e:
        yc.fail(str(e))
    if args.budget > WHISPER_PROMPT_MAX_TOKENS:
        yc.fail(f"--budget {args.budget}: whisper.cpp tiene al massimo {WHISPER_PROMPT_MAX_TOKENS} token di prompt")
    for p in (args.doc or []) + ([args.web] if args.web else []):
        if not Path(p).expanduser().exists():
            yc.fail(f"file mancante: {p}")
    if bool(args.yt_db) != bool(args.video_id):
        yc.fail("--yt-db e --video-id vanno insieme")
    out = Path(args.out).expanduser() if args.out else glossary_path(workdir)
    slug = project.get("channel", "")
    sig = _inputs_signature(args, workdir / "project.json", slug)
    if out.exists() and not args.force:
        try:
            old = yc.read_json(out)
        except Exception:
            old = {}
        if old.get("inputs_signature") == sig:
            yc.emit(True, skipped=True, reason="glossario già aggiornato (usa --force per rifare)",
                    outputs={"glossary": str(out)}, prompt=old.get("prompt"), prompt_tokens=old.get("prompt_tokens"),
                    terms=len(old.get("terms", [])), warnings=[])
            return
    try:
        g = build_glossary(workdir, project, args.doc, args.web, args.yt_db, args.video_id, args.confusions,
                           args.budget, args.style)
    except (OSError, ValueError, KeyError, sqlite3.Error) as e:
        yc.fail(f"glossario non costruito: {e}", workdir=str(workdir))
    g["inputs_signature"] = sig
    g["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    yc.write_json(out, g)
    warnings = []
    if not args.doc and not args.web:
        warnings.append("nessuna nota (--doc) né prova web (--web): glossario solo da project.json e canale")
    yc.emit(True, outputs={"glossary": str(out)}, prompt=g["prompt"], prompt_tokens=g["prompt_tokens"],
            prompt_terms=g["prompt_terms"], terms=len(g["terms"]), unit_facts=len(g["unit_facts"]),
            top=[f"{r['term']} ({r['score']})" for r in g["terms"][:25]], warnings=warnings)


if __name__ == "__main__":
    main()
