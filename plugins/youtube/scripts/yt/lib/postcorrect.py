"""yt-postcorrect — correzione vincolata dei NOMI nel transcript, contro il glossario (precisione prima di tutto).

Uso:
  yt-postcorrect WORKDIR                          # regole deterministiche (+ decisioni già prese, se ci sono)
  yt-postcorrect WORKDIR --dry-run                # cosa cambierebbe e perché: niente scritto nel transcript
  yt-postcorrect WORKDIR --decisions analysis/corrections.decisions.json   # applica le decisioni dell'agente
  yt-postcorrect WORKDIR --words FILE --out FILE  # su un altro file (studi, copie)

Tocca SOLO parole candidate a un'entità del glossario (alias della lista confusioni, maiuscole di una grafia
distintiva, forma unita/spezzata di un termine composto noto, articolo eliso, vicino fonetico) e MAI numeri
o l'unità dopo una cifra: gli slot MRR/ARR vengono solo segnalati (FLAG) con i fatti pubblicati come prova,
mai riscritti. I tempi restano quelli della parola; si spezza o si unisce solo per termini composti noti.

Decisioni (modalità regole, default):
  AUTO     applicata: maiuscole di una grafia distintiva (Github→GitHub, chatGPT→ChatGPT); forma composta nota
           (vibecoding→vibe coding, chat GPT→ChatGPT); articolo eliso (l'Ivetrack→Livetrack); alias non ambiguo
           (Akme→Acme, Robotix→Robotics); alias ambiguo o vicino fonetico esatto (Cloud→Claude, Erica→Erika)
           SOLO se la parola è maiuscola a metà frase, nessuna parola vicina la blocca ("versione cloud",
           "nel cloud", "Erica Rossi") e una parola di contesto dell'entità sta entro ±--window parole;
           alias d'episodio da project.json "entity_aliases" ({"Erica": "Erika"}): solo forma identica,
           maiuscole comprese; alias APPRESI da yt-learn (<studio>/data/learned/<canale>.confusions.json, origin
           «learned», anche di più parole: «Data Pilot io»→DataPilot.io) solo se un'entità del loro contesto
           appreso è entro ±2×--window parole (e, se ambigui, con le stesse prove degli alias ambigui)
  SUSPECT  riportata, non applicata (tutto il resto, incluse le forme minuscole che sono anche parole comuni)
  FLAG     mai applicata: unità dopo una cifra (MRAR, emarar, «e ARR»…)

Revisione (agente): leggere analysis/postcorrect.candidates.json (ogni candidato con contesto ±14 parole),
scrivere analysis/corrections.decisions.json = {"decisions": [{"id", "accept": true|false, "evidence"}]} e
rilanciare yt-postcorrect: le decisioni prevalgono sulle regole (un AUTO rifiutato non si applica, un SUSPECT
accettato sì); yt-transcribe le riapplica da solo a ogni nuova trascrizione (gli id sono "inizio:forma").
Ogni modifica tiene "fixed_from" e "postcorrect": {id, rule, entity} sulla parola ed entra nel registro
analysis/corrections.json. Misurato su un episodio di prova: 0 correzioni sbagliate su 48 esecuzioni; sul
transcript di produzione nomi giusti 46→52/56 con le sole regole, 56/56 dopo la revisione.

Glossario: analysis/glossary.json (yt-glossary) se c'è, altrimenti project.json + glossario e confusioni del
canale (<canale>.glossary.txt e .confusions.json accanto al profilo), costruiti in memoria.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import ytcore as yc
import glossary as gl

POSTCORRECT_VERSION = 1
GENERIC_AI = {"ai", "ia", "gpt", "chatgpt", "openai", "anthropic", "gemini", "copilot", "cursor", "llm", "llms",
              "modello", "modelli", "agente", "agenti", "agent", "agents", "prompt", "chatbot", "code", "sonnet",
              "opus", "mistral", "llama", "perplexity"}
PERSON_CTX = {"ceo", "coo", "cto", "founder", "co-founder", "cofondatore", "fondatore", "socio", "soci", "partner",
              "team", "azienda", "startup"}
# parola minuscola subito prima / dopo un alias ambiguo che indica l'uso come nome comune
BLOCK_PREV = {"il", "lo", "nel", "sul", "dal", "del", "al", "in", "un", "una", "versione", "versioni", "piattaforma",
              "piattaforme", "servizio", "servizi", "provider", "tool", "open", "private", "public", "hybrid",
              "google", "oracle", "ibm", "alibaba", "salesforce", "adobe", "sound", "nextcloud", "icloud"}
BLOCK_NEXT = {"computing", "storage", "native", "provider", "providers", "server", "hosting", "service", "services",
              "privato", "pubblico", "ibrido", "based", "run", "functions", "console", "platform", "drive"}
HESITATION_RE = re.compile(r"^(e+h*m+|e+h+|u+h*m+|u+h+|m{2,}h*|m+h+m*|h+m+)$", re.I)
NUMBER_WORD_RE = re.compile(
    r"^(\d[\d.,]*[kKmMxX%]?|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici|tredici|quattordici|"
    r"quindici|sedici|diciassette|diciotto|diciannove|venti|trenta|quaranta|cinquanta|sessanta|settanta|ottanta|"
    r"novanta|cento|\w+cento|mille|\w+mila|k)$", re.I)
# Unità dopo una cifra: le grafie che i motori producono quando il parlante sillaba M-R-R / A-R-R
# (MRAR, emarar, Mararro, EMAR…). Volutamente stretta: «marzo», «mare», «raro» NON corrispondono.
UNIT_SLOT_RX = re.compile(
    r"^(?:mrr|arr|mrar|marr|mrarr|m?r?ar+|e-?m+a?r+a?r+\w*|marar+\w*|mararr?\w*|emar\w*|e?m+r+|a+r+r+|arar+\w*)$", re.I)
SENT_END = (".", "?", "!", "…")
LEAD_RX = re.compile(r"^([«\"'“(\[]*)(.*?)([.,;:!?…»\"”)\]]*)$")


# ── testo ────────────────────────────────────────────────────────────────────
def split_punct(w: str) -> tuple[str, str, str]:
    m = LEAD_RX.match(w)
    return (m.group(1), m.group(2), m.group(3)) if m else ("", w, "")


def lower_key(s: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", s).lower())


PHON_RULES = [("ch", "k"), ("ck", "k"), ("ph", "f"), ("gh", "g"), ("gn", "n"), ("qu", "kv"), ("c", "k"),
              ("q", "k"), ("x", "ks"), ("y", "i"), ("w", "v"), ("j", "i"), ("h", "")]


def phon(word: str) -> str:
    """Stessa chiave di transcribe.phon, così i vicini coincidono con glossary_fix di yt-transcribe."""
    w = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    w = re.sub(r"[^a-z]", "", w)
    for a, b in PHON_RULES:
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def is_numeric(core: str) -> bool:
    return bool(re.search(r"\d", core)) or bool(NUMBER_WORD_RE.match(core))


def distinctive_case(term: str) -> bool:
    """La grafia porta informazione oltre la maiuscola iniziale: GitHub, ChatGPT, MRR, Acquire.com, vibe coding."""
    return bool(re.search(r"[a-z][A-Z]|[A-Z]{2}|\d|\.", term)) or term.islower()


def _is_filler(w: dict) -> bool:
    return bool(w.get("filler") or w.get("false_start")) or bool(HESITATION_RE.match(split_punct(w["w"])[1]))


def find_unit_slots(words: list[dict], back: int = 3) -> list[int]:
    """Indici delle parole-unità (MRR/ARR o grafie storpiate) entro `back` parole dopo una cifra
    (esitazioni e ripetizioni saltate). Sono sempre da ascoltare: mai risolte in automatico."""
    slots = []
    for k, w in enumerate(words):
        core = split_punct(w["w"])[1].replace("'", "")
        if not core or not UNIT_SLOT_RX.match(core):
            continue
        n = 0
        for j in range(k - 1, max(-1, k - 8), -1):
            if _is_filler(words[j]):
                continue
            cj = split_punct(words[j]["w"])[1]
            if is_numeric(cj):
                slots.append(k)
                break
            n += 1
            if n >= back or (j < k - 1 and split_punct(words[j]["w"])[2][-1:] in (".", "?", "!")):
                break
    return slots


def unit_figure(words: list[dict], k: int) -> str | None:
    for j in range(k - 1, max(-1, k - 8), -1):
        cj = split_punct(words[j]["w"])[1]
        if is_numeric(cj) and cj.lower() != "k":
            return cj
    return None


# ── glossario → entità ───────────────────────────────────────────────────────
class Entity:
    def __init__(self, term: str, etype: str | None, trusted: bool, context: list[str], source: str):
        self.term = term
        self.words = term.split()
        self.key = lower_key(term)
        self.type = etype or ""
        self.trusted = trusted
        self.context = {c.lower() for c in context}
        self.aliases: list[dict] = []
        self.source = source
        self.tier: str | None = None
        self.domain = bool(re.search(r"\.[a-z]{2,}$", term))

    @property
    def structural_ok(self) -> bool:
        """Le regole senza perdita (maiuscole, unione, divisione, elisione) valgono anche per i termini P1 del canale."""
        return self.trusted or self.tier == "P1"

    def __repr__(self) -> str:
        return f"Entity({self.term})"


def load_entities(glossary_doc: dict, project: dict | None = None, origin: str = "all") -> tuple[list[Entity], list[dict], str]:
    ents: dict[str, Entity] = {}
    unit_facts = list(glossary_doc.get("unit_facts", []))
    for t in glossary_doc.get("terms", []):
        src = t.get("sources", {})
        trusted = bool(set(src) & {"project", "doc", "yt", "web", "confusions"})
        k = lower_key(t["term"])
        e = ents.get(k)
        if e is None:
            e = ents[k] = Entity(t["term"], t.get("type"), trusted, t.get("context", []), "glossary")
        else:
            e.trusted = e.trusted or trusted
            e.context |= {c.lower() for c in t.get("context", [])}
        e.tier = e.tier or t.get("channel_tier")
        for a in t.get("aliases", []):
            if origin == "all" or a.get("origin") == origin:
                e.aliases.append(a)
    # alias d'episodio scritti dall'agente/dall'operatore in project.json: {"Erica": "Erika"}
    for form, term in ((project or {}).get("entity_aliases") or {}).items():
        if not (isinstance(form, str) and isinstance(term, str) and form.strip() and term.strip()):
            continue
        k = lower_key(term)
        e = ents.get(k)
        if e is None:
            e = ents[k] = Entity(term, None, True, [], "project.entity_aliases")
        e.trusted = True
        e.aliases.append({"form": form, "origin": "episode", "ambiguous": False, "case_sensitive": True,
                          "evidence": "project.json entity_aliases"})
    # il nome di battesimo eredita tipo e contesto della persona ("Paolo" ← "Paolo Bianchi")
    for e in list(ents.values()):
        if e.type.startswith("person") and len(e.words) >= 2:
            first = ents.get(lower_key(e.words[0]))
            if first is not None:
                first.type = first.type or "person"
                first.context |= e.context
    tech = {x.term.lower() for x in ents.values() if x.trusted and re.match(r"(company|product)", x.type or "")}
    for e in ents.values():
        if e.context & GENERIC_AI or e.term.lower() in {"claude", "chatgpt", "gpt", "gemini", "copilot"}:
            e.context |= GENERIC_AI | tech
        if e.type.startswith("person"):
            e.context |= PERSON_CTX
    return list(ents.values()), unit_facts, UNIT_SLOT_RX.pattern


def with_extra(project: dict, extra_terms: list[str] | None) -> dict:
    """project.json con i termini di --prompt-extra aggiunti a glossary_extra (contano come termini dell'episodio)."""
    extra = [t for t in (extra_terms or []) if t and t.lower() not in {x.lower() for x in project.get("glossary_extra") or []}]
    return {**project, "glossary_extra": list(project.get("glossary_extra") or []) + extra} if extra else project


def default_glossary(workdir: Path, project: dict, extra_terms: list[str] | None = None) -> dict:
    """analysis/glossary.json se c'è; altrimenti lo stesso glossario costruito in memoria (senza note né web),
    con i termini --prompt-extra della trascrizione."""
    doc = gl.load_glossary_doc(workdir)
    if doc is not None:
        if extra_terms:                       # i termini manuali dati a yt-transcribe valgono anche qui
            have = {lower_key(t["term"]) for t in doc.get("terms", [])}
            add = [{"term": t, "type": None, "sources": {"project": 1}, "context": [], "aliases": []}
                   for t in extra_terms if lower_key(t) not in have]
            if add:
                doc = {**doc, "terms": list(doc.get("terms", [])) + add}
        return doc
    return gl.build_glossary(workdir, with_extra(project, extra_terms))


# ── candidati ────────────────────────────────────────────────────────────────
def context_hits(words: list[dict], i: int, span: int, ent: Entity, window: int) -> list[str]:
    lo, hi = max(0, i - window), min(len(words), i + span + window)
    toks = [lower_key(w["w"]) for k, w in enumerate(words[lo:hi], start=lo) if not (i <= k < i + span)]
    text = " " + " ".join(toks) + " "
    hits = []
    for c in ent.context:
        ck = " ".join(lower_key(x) for x in c.split())
        if ck and ck != ent.key and f" {ck} " in text:
            hits.append(c)
    return sorted(hits)


def sentence_initial(words: list[dict], i: int) -> bool:
    return i == 0 or words[i - 1]["w"].rstrip("»\"”)").endswith(SENT_END)


def cand_id(words: list[dict], i: int, span: int) -> str:
    frm = " ".join(w["w"] for w in words[i:i + span])
    return f"{words[i]['start']:.2f}:{lower_key(frm)}"


def find_candidates(words: list[dict], ents: list[Entity], unit_facts: list[dict], window: int = 60,
                    phon_auto: float = 0.95, phon_suspect: float = 0.8) -> list[dict]:
    lower_seen = Counter(split_punct(w["w"])[1] for w in words if split_punct(w["w"])[1].islower())
    by_key = {e.key: e for e in ents}
    alias_map: dict[str, list[tuple[Entity, dict]]] = {}
    multi_alias: list[tuple[list[str], Entity, dict]] = []      # alias di più parole (appresi): sequenza esatta
    for e in ents:
        for a in e.aliases:
            toks = [lower_key(x) for x in str(a["form"]).split()]
            if len(toks) >= 2 and all(toks):
                multi_alias.append((toks, e, a))
            else:
                alias_map.setdefault(lower_key(a["form"]), []).append((e, a))
    multi_alias.sort(key=lambda t: -len(t[0]))
    multi = [e for e in ents if len(e.words) >= 2]
    mp_keys = {e.key: phon("".join(e.words)) for e in multi}
    single_phon = []
    for e in ents:
        if len(e.words) == 1 and len(e.key) >= 4 and e.key.isalpha():
            single_phon.append((e, phon(e.term)))
        elif e.type.startswith("person") and len(e.words) >= 2 and len(e.words[-1]) >= 6:
            single_phon.append((Entity(e.words[-1], e.type, e.trusted, list(e.context), e.source), phon(e.words[-1])))
    unit_idx = set(find_unit_slots(words))
    cands: list[dict] = []
    used: set[int] = set()

    def add(i: int, span: int, to: str, kind: str, ent: Entity | None, **kw) -> None:
        if any(k in used for k in range(i, i + span)):
            return
        frm = " ".join(w["w"] for w in words[i:i + span])
        cands.append({"id": cand_id(words, i, span), "i": i, "span": span,
                      "start": round(words[i]["start"], 2), "end": round(words[i + span - 1]["end"], 2),
                      "from": frm, "to": to, "kind": kind, "entity": ent.term if ent else None,
                      "speaker": words[i].get("speaker"), **kw})
        for k in range(i, i + span):
            used.add(k)

    for i, w in enumerate(words):
        if i in used:
            continue
        lead, core, trail = split_punct(w["w"])
        if not core or HESITATION_RE.match(core):
            continue
        # ── guardia: numeri e unità dopo una cifra ──
        if i in unit_idx:
            num = unit_figure(words, i) or "?"
            nv = re.sub(r"[^\d.,kK]", "", num).replace(",", ".").lower()
            facts = [f for f in unit_facts if f["value"].lower().rstrip("0").rstrip(".") == nv.rstrip("0").rstrip(".")
                     or f["value"].lower() == nv]
            add(i, 1, "MRR|ARR?", "unit-slot", None, decision="FLAG",
                reason=f"unità dopo la cifra «{num}»: mai riscritta; ascoltare e scegliere MRR o ARR",
                facts=facts[:4])
            continue
        if is_numeric(core) and not re.search(r"\.[a-z]{2,}$", core):
            continue
        # ── forme composte (unione di 2-3 parole / maiuscole di un termine composto) ──
        done = False
        for e in multi:
            n = len(e.words)
            if i + n > len(words):
                continue
            seq = words[i:i + n]
            cores = [split_punct(x["w"])[1] for x in seq]
            if any(split_punct(x["w"])[2] for x in seq[:-1]):
                continue
            if [c.lower() for c in cores] == [x.lower() for x in e.words] and cores != e.words:
                to = split_punct(seq[0]["w"])[0] + e.term + split_punct(seq[-1]["w"])[2]
                add(i, n, to, "case-multi", e, decision="AUTO" if e.structural_ok else "SUSPECT",
                    reason="maiuscole di un termine composto noto")
                done = True
                break
        if done:
            continue
        for toks, e2, a in multi_alias:
            n = len(toks)
            seq = words[i:i + n]
            if len(seq) < n or any(k in unit_idx for k in range(i, i + n)):
                continue
            parts = [split_punct(x["w"]) for x in seq]
            if any(p[2] for p in parts[:-1]) or [lower_key(p[1]) for p in parts] != toks:
                continue
            ok, why, hits = judge_alias(words, i, e2, a, window, n)
            add(i, n, parts[0][0] + e2.term + parts[-1][2], "alias", e2, decision="AUTO" if ok else "SUSPECT",
                reason=why, origin=a.get("origin"), context_hits=hits)
            done = True
            break
        if done:
            continue
        if i + 1 < len(words) and not trail and (i + 1) not in unit_idx:
            nxt_lead, nxt_core, nxt_trail = split_punct(words[i + 1]["w"])
            e = by_key.get(lower_key(core + nxt_core))
            if e is not None and len(e.words) == 1 and not is_numeric(nxt_core):
                add(i, 2, lead + e.term + nxt_trail, "merge", e, decision="AUTO" if e.structural_ok else "SUSPECT",
                    reason=f"due parole compongono il termine noto {e.term}")
                continue
        if not trail:
            hit = multi_phonetic(words, i, multi, mp_keys)
            if hit:
                n, r, e = hit
                seq = words[i:i + n]
                to = split_punct(seq[0]["w"])[0] + e.term + split_punct(seq[-1]["w"])[2]
                add(i, n, to, "phonetic-multi", e, decision="SUSPECT", score=round(r, 2),
                    reason=f"{n} parole suonano come «{e.term}» (fonetica {r:.2f}); mai in automatico")
                continue
        k = lower_key(core)
        e = by_key.get(k)
        if e is not None and len(e.words) >= 2 and core.replace("-", " ") != e.term:
            add(i, 1, lead + e.term + trail, "split", e, decision="AUTO" if e.structural_ok else "SUSPECT",
                reason="forma unita di un termine composto noto")
            continue
        if e is not None and len(e.words) == 1 and core != e.term:
            if e.domain or (e.term.islower() and core.lower() == e.term and sentence_initial(words, i)):
                continue                                   # termine minuscolo con la maiuscola d'inizio frase: giusto
            clash = core.islower() and not distinctive_case(e.term)
            add(i, 1, lead + e.term + trail, "case", e,
                decision="AUTO" if (e.structural_ok and not clash) else "SUSPECT",
                reason="la forma minuscola può essere una parola comune (vento/Vento): tenuta" if clash
                else "maiuscole di un termine noto")
            continue
        if e is not None:
            continue
        m = re.match(r"^([lL])['’](\w+)$", core)
        if m:
            e2 = by_key.get(lower_key(m.group(1) + m.group(2)))
            if e2 is not None:
                add(i, 1, lead + e2.term + trail, "elision", e2, decision="AUTO" if e2.structural_ok else "SUSPECT",
                    reason="articolo + parola compongono il termine noto")
                continue
        if k in alias_map:
            hits_alias = [(e2, a) for e2, a in alias_map[k] if not a.get("case_sensitive") or core == a["form"]]
            if hits_alias:
                e2, a = hits_alias[0]
                ok, why, hits = judge_alias(words, i, e2, a, window)
                add(i, 1, lead + e2.term + trail, "alias", e2, decision="AUTO" if ok else "SUSPECT",
                    reason=why, origin=a.get("origin"), context_hits=hits)
                continue
        if "." in core:
            best = max(((difflib.SequenceMatcher(None, core.lower(), x.term.lower()).ratio(), x) for x in ents
                        if "." in x.term), default=(0, None), key=lambda t: t[0])
            if best[1] is not None and best[0] >= 0.9 and core.lower() != best[1].term.lower():
                add(i, 1, lead + best[1].term + trail, "domain", best[1],
                    decision="AUTO" if best[1].trusted else "SUSPECT",
                    reason=f"vicino per distanza di modifica di un dominio verificato (rapporto {best[0]:.2f})")
            continue
        if len(core) < 4 or not core[:1].isupper() or not core.replace("'", "").isalpha():
            continue
        pc = phon(core)
        scored = []
        for e2, pk in single_phon:
            if not pk or pc[:1] != pk[:1] or lower_key(core) == e2.key:
                continue
            if e2.key.startswith(k) and len(k) < len(e2.key):
                continue                                   # forma breve detta (Taskora ⊂ TaskoraAI): non è un errore
            r = difflib.SequenceMatcher(None, pc, pk).ratio()
            if r >= phon_suspect:
                scored.append((r, e2))
        if not scored:
            continue
        scored.sort(key=lambda t: -t[0])
        r, e2 = scored[0]
        rivals = [x.term for rr, x in scored[1:] if rr >= r - 0.05 and x.key != e2.key]
        initial = sentence_initial(words, i)
        known_word = lower_seen.get(core.lower(), 0) > 0
        if r >= phon_auto and e2.trusted and not rivals and not initial:
            ok, why, hits = judge_ambiguous(words, i, e2, window)
            why = f"fonetica {r:.2f}; " + why
        else:
            ok, hits = False, []
            why = (f"fonetica {r:.2f}" + ("; rivali " + ", ".join(rivals) if rivals else "") +
                   ("; inizio frase" if initial else "") + ("; termine solo del canale" if not e2.trusted else "")
                   + ("" if r >= phon_auto else f"; sotto la soglia automatica {phon_auto}"))
        if known_word:
            why += "; la parola compare anche minuscola (parola comune)"
        add(i, 1, lead + e2.term + trail, "phonetic", e2, decision="AUTO" if ok else "SUSPECT", reason=why,
            score=round(r, 2), context_hits=hits)
    return cands


def multi_phonetic(words: list[dict], i: int, multi: list[Entity], mp_keys: dict[str, str],
                   thr: float = 0.86) -> tuple[int, float, Entity] | None:
    best = None
    for e in multi:
        n = len(e.words)
        if n > 3 or i + n > len(words) or len(mp_keys[e.key]) < 8:
            continue
        seq = words[i:i + n]
        cores = [split_punct(x["w"])[1] for x in seq]
        if any(split_punct(x["w"])[2] for x in seq[:-1]) or any(is_numeric(c) for c in cores):
            continue
        if [c.lower() for c in cores] == [x.lower() for x in e.words]:
            continue
        if not any(c.lower() == x.lower() for c, x in zip(cores, e.words)) and n == 2:
            continue
        if any(c.lower() != x.lower() and difflib.SequenceMatcher(None, phon(c), phon(x)).ratio() < 0.66
               for c, x in zip(cores, e.words)):
            continue
        pc = phon("".join(cores))
        pk = mp_keys[e.key]
        if not pc or pc[:1] != pk[:1]:
            continue
        r = difflib.SequenceMatcher(None, pc, pk).ratio()
        if r >= thr and (best is None or r > best[1]):
            best = (n, r, e)
    return best


def judge_alias(words: list[dict], i: int, ent: Entity, a: dict, window: int, span: int = 1) -> tuple[bool, str, list[str]]:
    """Alias della lista confusioni. Gli alias APPRESI (yt-learn, origin «learned») valgono per l'episodio solo se una
    delle entità viste vicino alle correzioni passate (contesto appreso) è entro ±window parole: è la prova che il
    termine c'entra anche qui. Ambigui o no, senza contesto restano SUSPECT."""
    amb = bool(a.get("ambiguous"))
    if a.get("origin") == "learned" and not ent.trusted:
        # il contesto appreso è fatto di entità specifiche (non di parole generiche): finestra doppia
        lw = window * 2
        hits = context_hits(words, i, span, ent, lw)
        if not hits:
            return False, (f"alias appreso: nessuna entità del suo contesto entro ±{lw} parole, il termine potrebbe "
                           "non c'entrare"), []
        if not amb:
            return True, f"alias appreso + contesto ({', '.join(hits[:4])})", hits
        ok, why, h = judge_ambiguous(words, i, ent, lw, assume_trusted=True, span=span)
        return ok, ("alias appreso; " + why), h
    return judge_ambiguous(words, i, ent, window, span=span) if amb else (ent.trusted, "alias non ambiguo", [])


def judge_ambiguous(words: list[dict], i: int, ent: Entity, window: int, assume_trusted: bool = False,
                    span: int = 1) -> tuple[bool, str, list[str]]:
    """Una forma ambigua (parola vera / nome comune) si corregge solo con prove positive."""
    lead, core, trail = split_punct(words[i]["w"])
    if not ent.trusted and not assume_trusted:
        return False, "termine solo del canale", []
    if not core[:1].isupper():
        return False, "minuscola: probabile nome comune", []
    if sentence_initial(words, i):
        return False, "maiuscola di inizio frase: nessun segnale di nome proprio", []
    prev = split_punct(words[i - 1]["w"])[1].lower() if i > 0 else ""
    j = i + span
    nxt_lead, nxt_core, _ = split_punct(words[j]["w"]) if j < len(words) else ("", "", "")
    trail = split_punct(words[j - 1]["w"])[2]
    if prev in BLOCK_PREV:
        return False, f"bloccata dalla parola precedente «{prev}»", []
    if nxt_core.lower() in BLOCK_NEXT:
        return False, f"bloccata dalla parola successiva «{nxt_core}»", []
    if ent.type.startswith("person") and nxt_core[:1].isupper() and not trail \
            and lower_key(nxt_core) not in {lower_key(x) for x in ent.words}:
        return False, f"seguita da un altro cognome «{nxt_core}»", []
    hits = context_hits(words, i, span, ent, window)
    if not hits:
        return False, f"nessuna parola di contesto di {ent.term} entro ±{window} parole", []
    return True, f"maiuscola a metà frase + contesto ({', '.join(hits[:4])})", hits


# ── applicazione ─────────────────────────────────────────────────────────────
def apply(doc: dict, cands: list[dict], accept: set[str]) -> tuple[dict, list[dict]]:
    words = doc["words"]
    by_i = {c["i"]: c for c in cands if c["id"] in accept and c["kind"] != "unit-slot"}
    out: list[dict] = []
    old2new: dict[int, int] = {}
    old_end: dict[int, int] = {}
    applied = []
    i = 0
    while i < len(words):
        c = by_i.get(i)
        if c is None:
            old2new[i] = len(out)
            out.append(dict(words[i]))
            old_end[i] = len(out)
            i += 1
            continue
        span = c["span"]
        seq = words[i:i + span]
        tag = {"id": c["id"], "rule": c["kind"], "entity": c["entity"], "from": c["from"]}
        new_words = c["to"].split()
        for k in range(span):
            old2new[i + k] = len(out)
        if len(new_words) == span:
            for w, nw in zip(seq, new_words):
                r = dict(w)
                if r["w"] != nw:
                    r["fixed_from"] = w.get("fixed_from", w["w"])
                    r["w"] = nw
                    r["postcorrect"] = tag
                out.append(r)
        elif span == 1:                                     # divisione: tempi in proporzione ai caratteri
            w = seq[0]
            total = sum(len(x) for x in new_words)
            t, dur = w["start"], w["end"] - w["start"]
            for k, nw in enumerate(new_words):
                r = {kk: vv for kk, vv in w.items() if kk not in ("w", "start", "end", "i")}
                r.update({"w": nw, "start": round(t, 3)})
                t = t + dur * len(nw) / total
                r["end"] = round(w["end"] if k == len(new_words) - 1 else t, 3)
                r["fixed_from"] = w["w"]
                r["split_from"] = w["w"]
                r["postcorrect"] = tag
                out.append(r)
        else:                                               # unione: dal primo all'ultimo
            r = dict(seq[0])
            r.update({"w": c["to"], "end": seq[-1]["end"], "fixed_from": " ".join(x["w"] for x in seq),
                      "merged_from": [x["w"] for x in seq], "postcorrect": tag})
            out.append(r)
        for k in range(span):
            old_end[i + k] = len(out)
        applied.append(c)
        i += span
    if words and "i" in words[0]:
        for k, w in enumerate(out):
            w["i"] = k
    new = dict(doc)
    new["words"] = out
    n_new = len(out)
    if isinstance(doc.get("segments"), list):
        segs = []
        for s in doc["segments"]:
            s2 = dict(s)
            if "w0" in s and "w1" in s:
                s2["w0"] = old2new.get(s["w0"], n_new)
                s2["w1"] = old_end.get(s["w1"] - 1, n_new) if s["w1"] > s["w0"] else s2["w0"]
                s2["text"] = " ".join(x["w"] for x in out[s2["w0"]:s2["w1"]])
            segs.append(s2)
        new["segments"] = segs
    if isinstance(doc.get("asr_segments"), list):
        new["asr_segments"] = [[old2new.get(a, n_new), old_end.get(b - 1, n_new)] for a, b in doc["asr_segments"]]
    return new, applied


def ctx(words: list[dict], c: dict, n: int = 14) -> str:
    a, b = max(0, c["i"] - n), min(len(words), c["i"] + c["span"] + n)
    left = " ".join(w["w"] for w in words[a:c["i"]])
    mid = " ".join(w["w"] for w in words[c["i"]:c["i"] + c["span"]])
    right = " ".join(w["w"] for w in words[c["i"] + c["span"]:b])
    return f"{left} [[{mid}]] {right}"


def read_decisions(path: Path | None) -> tuple[set[str], set[str]]:
    if not path or not Path(path).exists():
        return set(), set()
    data = yc.read_json(path)
    dec = data.get("decisions", []) if isinstance(data, dict) else data
    acc = {d["id"] for d in dec if isinstance(d, dict) and d.get("id") and d.get("accept") is True}
    rej = {d["id"] for d in dec if isinstance(d, dict) and d.get("id") and d.get("accept") is False}
    return acc, rej


def correct_doc(doc: dict, glossary_doc: dict, project: dict | None = None, window: int = 60,
                decisions: Path | None = None, origin: str = "all", phon_auto: float = 0.95,
                phon_suspect: float = 0.8) -> tuple[dict, dict]:
    """Regole (+ decisioni) su un transcript in memoria. Ritorna (nuovo doc, rapporto)."""
    acc, rej = read_decisions(decisions)
    # correzioni già nel transcript: un rifiuto dell'agente le annulla (solo sostituzioni 1→1)
    words = [dict(w) for w in doc["words"]]
    already: dict[str, list[int]] = {}
    for idx, w in enumerate(words):
        if isinstance(w.get("postcorrect"), dict) and w["postcorrect"].get("id"):
            already.setdefault(w["postcorrect"]["id"], []).append(idx)
    reverted, not_revertible = [], []
    for rid in sorted(rej & set(already)):
        idxs = already[rid]
        if any(words[i].get("split_from") or words[i].get("merged_from") for i in idxs):
            not_revertible.append(rid)
            continue
        for i in idxs:
            w = words[i]
            orig = w["postcorrect"].get("from") or w.get("fixed_from")
            if orig:
                reverted.append({"id": rid, "t": round(w["start"], 2), "from": w["w"], "to": orig})
                w["w"] = orig
                w.pop("postcorrect", None)
                if w.get("fixed_from") == orig:
                    w.pop("fixed_from", None)
    doc = {**doc, "words": words}
    ents, facts, _ = load_entities(glossary_doc, project, origin)
    cands = find_candidates(words, ents, facts, window, phon_auto, phon_suspect)
    for c in cands:
        c["context"] = ctx(words, c)
    known = {c["id"] for c in cands}
    applied_before = {i for i in already if i not in {r["id"] for r in reverted}}
    accept = ({c["id"] for c in cands if c["decision"] == "AUTO"} | (acc & known)) - rej
    new, applied = apply(doc, cands, accept)
    for c in applied:
        c["source"] = "decisions" if c["id"] in acc else "rules"
    report = {
        "version": POSTCORRECT_VERSION, "window": window, "origin": origin,
        "candidates": len(cands), "by_decision": dict(Counter(c["decision"] for c in cands)),
        "by_kind": dict(Counter(c["kind"] for c in cands)), "applied": len(applied),
        "applied_by_rule": dict(Counter(f"{c['kind']}:{lower_key(c['from'])}→{c['to'].strip('.,;:!?')}" for c in applied)),
        "decisions_file": str(decisions) if decisions and Path(decisions).exists() else None,
        "decisions_accepted": len(acc & known), "decisions_rejected": len(rej & known),
        "decisions_unknown_ids": sorted((acc | rej) - known - applied_before - {r["id"] for r in reverted})[:20],
        "already_applied": len(applied_before), "reverted": reverted, "not_revertible": not_revertible,
        "flags": [{"id": c["id"], "start": c["start"], "from": c["from"], "reason": c["reason"],
                   "facts": c.get("facts", []), "context": c["context"]} for c in cands if c["decision"] == "FLAG"],
        "suspects": [{"id": c["id"], "start": c["start"], "from": c["from"], "maybe": c["to"], "kind": c["kind"],
                      "reason": c["reason"], "context": c["context"]} for c in cands
                     if c["decision"] == "SUSPECT" and c["id"] not in accept],
        "applied_list": [{"id": c["id"], "t": c["start"], "from": c["from"], "to": c["to"], "rule": c["kind"],
                          "entity": c["entity"], "source": c["source"], "reason": c["reason"]} for c in applied],
        "candidates_list": cands,
    }
    return new, report


def append_log(log_path: Path, report: dict, mode: str, transcript: Path) -> None:
    """Registro delle correzioni (analysis/corrections.json): una voce per modifica applicata."""
    try:
        data = yc.read_json(log_path) if log_path.exists() else {}
    except Exception:
        data = {}
    data.setdefault("version", 1)
    data.setdefault("about", "Registro di yt-postcorrect: ogni parola corretta (regole o decisioni dell'agente). "
                             "Le parole conservano 'fixed_from' nel transcript; gli slot MRR/ARR non sono mai qui.")
    entries = data.setdefault("entries", [])
    seen = {(e.get("id"), e.get("to")) for e in entries}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for a in report["applied_list"]:
        if (a["id"], a["to"]) in seen:
            continue
        entries.append({**a, "mode": mode, "transcript": str(transcript), "at": now})
    for r in report.get("reverted", []):
        entries.append({**r, "rule": "revert", "source": "decisions", "mode": mode, "transcript": str(transcript),
                        "at": now, "reason": "rifiutata nella revisione (corrections.decisions.json)"})
    yc.write_json(log_path, data)


def write_candidates(path: Path, report: dict, source: Path) -> None:
    yc.write_json(path, {
        "source_words": str(source), "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "instructions": ("Per ogni candidato SUSPECT decidi accept true/false con una riga di prova (contesto, fonti, "
                         "glossario). Gli unit-slot non si accettano mai: si risolvono solo ascoltando "
                         "(analysis/resolutions.json). Scrivi analysis/corrections.decisions.json = "
                         "{\"decisions\": [{\"id\", \"accept\", \"evidence\"}]} e rilancia yt-postcorrect."),
        "candidates": [{k: c.get(k) for k in ("id", "start", "from", "to", "kind", "entity", "decision", "reason",
                                               "context", "speaker", "facts", "origin")}
                       for c in report["candidates_list"]]})


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-postcorrect", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <canale>/<cartella>)")
    ap.add_argument("--words", default=None, help="transcript da correggere (default analysis/transcript.words.json)")
    ap.add_argument("--out", default=None, help="dove scrivere il transcript corretto (default: sul posto)")
    ap.add_argument("--glossary", default=None, help="glossario JSON (default analysis/glossary.json o in memoria)")
    ap.add_argument("--decisions", default=None,
                    help="decisioni dell'agente (default analysis/corrections.decisions.json se esiste)")
    ap.add_argument("--window", type=int, default=60, help="parole di contesto per lato (default 60)")
    ap.add_argument("--origin", choices=["a-priori", "all"], default="all",
                    help="quali alias della lista confusioni usare (default all)")
    ap.add_argument("--phon-auto", type=float, default=0.95, help="somiglianza fonetica per la correzione automatica")
    ap.add_argument("--phon-suspect", type=float, default=0.8, help="somiglianza fonetica per un sospetto")
    ap.add_argument("--dry-run", action="store_true", help="non scrive il transcript (solo candidati e rapporto)")
    args = ap.parse_args()

    try:
        workdir = yc.resolve_workdir(args.workdir)
        project = yc.load_project(workdir)
    except FileNotFoundError as e:
        yc.fail(str(e))
    analysis = workdir / "analysis"
    src = Path(args.words).expanduser() if args.words else analysis / "transcript.words.json"
    if not src.exists():
        yc.fail(f"manca {src}: esegui prima yt-transcribe", workdir=str(workdir))
    out = Path(args.out).expanduser() if args.out else src
    try:
        doc = yc.read_json(src)
        if isinstance(doc, list):
            doc = {"words": doc}
        gdoc = yc.read_json(Path(args.glossary).expanduser()) if args.glossary else \
            default_glossary(workdir, project, doc.get("prompt_extra"))
    except (OSError, ValueError, KeyError) as e:
        yc.fail(f"input illeggibile: {e}", workdir=str(workdir))
    dec = Path(args.decisions).expanduser() if args.decisions else analysis / "corrections.decisions.json"
    if args.decisions and not dec.exists():
        yc.fail(f"file delle decisioni mancante: {dec}")
    new, rep = correct_doc(doc, gdoc, with_extra(project, doc.get("prompt_extra")), args.window,
                           dec if dec.exists() else None, args.origin, args.phon_auto, args.phon_suspect)
    cand_path = analysis / "postcorrect.candidates.json" if not args.out else out.with_suffix(".candidates.json")
    write_candidates(cand_path, rep, src)
    warnings = []
    if rep["not_revertible"]:
        warnings.append(f"rifiuti non annullabili in automatico (parole divise/unite): {rep['not_revertible']}; "
                        f"rifai yt-transcribe --force (le decisioni vengono riapplicate)")
    if rep["decisions_unknown_ids"]:
        warnings.append(f"{len(rep['decisions_unknown_ids'])} id delle decisioni non trovati tra i candidati "
                        f"(transcript rifatto? id = inizio:forma): {rep['decisions_unknown_ids'][:5]}")
    written = False
    if not args.dry_run and (rep["applied"] or rep["reverted"] or out != src):
        pc = new.setdefault("postprocess", {}).setdefault("postcorrect", {})
        pc.update({"version": POSTCORRECT_VERSION, "applied": pc.get("applied", 0) + rep["applied"],
                   "last_run": time.strftime("%Y-%m-%dT%H:%M:%S"), "window": args.window,
                   "suspects": len(rep["suspects"]), "flags": len(rep["flags"])})
        yc.write_json(out, new)
        written = True
        if out == src and src.name == "transcript.words.json":
            try:
                import transcribe
                (analysis / "transcript.srt").write_text(transcribe.build_srt(new["words"]))
            except Exception as e:  # non bloccante
                warnings.append(f"transcript.srt non rigenerato: {e}")
        if rep["applied"] or rep["reverted"]:
            append_log(analysis / "corrections.json" if not args.out else out.with_suffix(".corrections.json"),
                       rep, "decisions" if rep["decisions_accepted"] else "rules", out)
    if rep["flags"]:
        warnings.append(f"{len(rep['flags'])} unità dopo una cifra da ascoltare (MRR/ARR): mai corrette in automatico")
    if rep["suspects"]:
        warnings.append(f"{len(rep['suspects'])} sospetti da rivedere in {cand_path.name}")
    yc.emit(True, outputs={"words": str(out) if written else None, "candidates": str(cand_path)},
            written=written, dry_run=args.dry_run, candidates=rep["candidates"], by_decision=rep["by_decision"],
            applied=rep["applied"], applied_by_rule=rep["applied_by_rule"],
            decisions_accepted=rep["decisions_accepted"], decisions_rejected=rep["decisions_rejected"],
            already_applied=rep["already_applied"], reverted=rep["reverted"],
            suspects=[{k: s[k] for k in ("id", "start", "from", "maybe", "reason")} for s in rep["suspects"][:40]],
            flags=[{k: f[k] for k in ("id", "start", "from", "reason")} for f in rep["flags"]],
            warnings=warnings)


if __name__ == "__main__":
    main()
