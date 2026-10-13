#!/usr/bin/env python3
"""Analisi del pre-test delle thumbnail (solo libreria standard).

Sottocomandi:
  report    legge le risposte (CSV del Google Sheet e/o JSON di anteprima), applica le esclusioni,
            fa i test e scrive risultati.md, risultati.json, ab_tests_row.json e il foglio di
            codifica alla cieca di «cosa promette» / «a chi è rivolto».
  binom K N         test binomiale esatto a due code contro 50/50 (testa a testa, PickFu).
  soglie [N ...]    quante risposte servono a un braccio per vincere, per ogni N.
  pickfu    testa a testa o coppie ricavate da un sondaggio Ranked di PickFu (conteggi a mano).
  selftest  dati simulati: controlla soglie, Holm, esclusioni e codifica.

Esempi:
  python3 analizza.py report --config pretest.config.json --csv risultati/risposte.csv --out risultati/
  python3 analizza.py report --config pretest.config.json --csv risultati/risposte.csv \
      --coding risultati/codifica_compilata.csv --cost "£43" --out risultati/
  python3 analizza.py binom 61 100
  python3 analizza.py pickfu --pair A ab1 --counts 33 17
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

csv.field_size_limit(10_000_000)

# ---------------------------------------------------------------- statistica


def binom_pmf(n: int, k: int, p: float) -> float:
    return math.comb(n, k) * p ** k * (1 - p) ** (n - k)


def binom_two_sided(k: int, n: int, p: float = 0.5) -> float:
    """p-value esatto a due code (somma delle probabilità ≤ quella osservata)."""
    if n == 0:
        return 1.0
    pk = binom_pmf(n, k, p)
    tot = sum(binom_pmf(n, i, p) for i in range(n + 1) if binom_pmf(n, i, p) <= pk * (1 + 1e-7))
    return min(1.0, tot)


def binom_upper(k: int, n: int, p: float) -> float:
    """P(X ≥ k): una coda, per «la nostra tile è scelta più del caso»."""
    return min(1.0, sum(binom_pmf(n, i, p) for i in range(k, n + 1)))


def win_threshold(n: int, alpha: float = 0.05) -> int | None:
    """Minimo k (> n/2) con p a due code ≤ alpha."""
    for k in range(n // 2 + 1, n + 1):
        if k > n - k and binom_two_sided(k, n) <= alpha:
            return k
    return None


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Fisher esatto 2×2 [[a, b], [c, d]], due code."""
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d

    def p(x: int) -> float:
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)

    lo, hi = max(0, c1 - r2), min(r1, c1)
    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 * (1 + 1e-7)))


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """p-value corretti con Holm–Bonferroni (monotoni)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (key, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[key] = run
    return out


# ---------------------------------------------------------------- lettura


def parse_records_from_csv(path: Path) -> list[dict]:
    recs = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            for cell in row:
                cell = cell.strip()
                if cell.startswith("{") and '"study_id"' in cell:
                    try:
                        recs.append(json.loads(cell))
                    except json.JSONDecodeError:
                        pass
                    break
    return recs


def parse_records_from_json(path: Path) -> list[dict]:
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return []
    try:
        data = json.loads(txt)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in txt.splitlines() if line.strip().startswith("{")]


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    a = cfg.setdefault("analysis", {})
    a.setdefault("alpha", 0.05)
    a.setdefault("primary_correction", "holm")
    a.setdefault("min_total_s", 25)
    a.setdefault("exclude_knows_show", True)
    a.setdefault("chance", 1 / 9)
    a.setdefault("exposure_window_ms", [2500, 3700])
    return cfg


# ---------------------------------------------------------------- esclusioni


def apply_exclusions(recs: list[dict], cfg: dict, include_knows: bool | None = None) -> tuple[list[dict], Counter, list[str]]:
    a = cfg["analysis"]
    excl_knows = a["exclude_knows_show"] if include_knows is None else not include_knows
    arm_ids = {x["id"] for x in cfg["arms"]}
    warnings: list[str] = []
    builds = Counter(r.get("build") for r in recs if r.get("study_id") == cfg["study_id"])
    if len(builds) > 1:
        warnings.append(f"più build nello stesso studio: {dict(builds)} (stimoli cambiati durante la raccolta?)")
    reasons: Counter = Counter()
    seen: set[str] = set()
    valid: list[dict] = []
    for r in sorted(recs, key=lambda r: r.get("t_end") or ""):
        if r.get("study_id") != cfg["study_id"]:
            reasons["altro studio"] += 1
            continue
        if r.get("preview"):
            reasons["anteprima"] += 1
            continue
        pid = r.get("pid") or ""
        if any(pid.upper().startswith(x.upper()) for x in a.get("test_pid_prefixes", ["TEST"])):
            reasons["prova interna (ID che inizia con TEST)"] += 1
            continue
        if pid:
            if pid in seen:
                reasons["duplicato (stesso ID Prolific)"] += 1
                continue
            seen.add(pid)
        if r.get("arm") not in arm_ids:
            reasons["braccio sconosciuto"] += 1
            continue
        if not (r.get("imc") or {}).get("pass"):
            reasons["controllo di attenzione sbagliato"] += 1
            continue
        if (r.get("total_ms") or 0) < a["min_total_s"] * 1000:
            reasons[f"troppo veloce (< {a['min_total_s']} s in tutto)"] += 1
            continue
        if not r.get("h2h") or not r.get("promise") or not r.get("profile"):
            reasons["incompleto"] += 1
            continue
        if excl_knows and (r.get("profile") or {}).get("knows_show") == "si":
            reasons["conosceva già il podcast"] += 1
            continue
        valid.append(r)
    no_pid = sum(1 for r in valid if not r.get("pid"))
    if no_pid:
        warnings.append(f"{no_pid} risposte valide senza ID Prolific (prove interne? link aperto fuori da Prolific?)")
    return valid, reasons, warnings


def exposure_ok(block: dict | None, cfg: dict) -> bool:
    if not block:
        return False
    lo, hi = cfg["analysis"]["exposure_window_ms"]
    e = block.get("exposure_ms")
    return (not block.get("hidden_during_exposure")) and e is not None and lo <= e <= hi


# ---------------------------------------------------------------- analisi


def analyse_h2h(valid: list[dict], cfg: dict) -> dict:
    alpha = cfg["analysis"]["alpha"]
    pairs = ["|".join(p) for p in cfg["pairs"]]
    primary = {"|".join(p) for p in (cfg.get("primary_pairs") or [])}
    out: dict = {}
    for key in pairs:
        x, y = key.split("|")
        votes = Counter()
        left = 0
        for r in valid:
            for h in r.get("h2h") or []:
                if set(h.get("pair", "").split("|")) == {x, y} and h.get("choice") in (x, y):
                    votes[h["choice"]] += 1
                    left += h["choice"] == h.get("left")
        n = votes[x] + votes[y]
        top = x if votes[x] >= votes[y] else y
        out[key] = {"a": x, "b": y, "votes": {x: votes[x], y: votes[y]}, "n": n,
                    "p": binom_two_sided(max(votes[x], votes[y]), n) if n else 1.0,
                    "share_top": (max(votes[x], votes[y]) / n) if n else None, "top": top,
                    "left_share": (left / n) if n else None, "primary": key in primary,
                    "soglia": win_threshold(n, alpha) if n else None}
    prim = {k: v["p"] for k, v in out.items() if v["primary"]}
    adj = holm(prim) if cfg["analysis"]["primary_correction"] == "holm" else prim
    m = len(prim)
    for k, v in out.items():
        v["p_adj"] = adj.get(k, v["p"])
        if v["primary"] and m > 1:
            v["soglia_holm_primo_passo"] = win_threshold(v["n"], alpha / m) if v["n"] else None
        tie = v["votes"][v["a"]] == v["votes"][v["b"]]
        v["esito"] = f"vince {v['top']}" if (v["n"] and not tie and v["p_adj"] <= alpha) else "pari"
    return out


def analyse_feed(valid: list[dict], cfg: dict) -> dict | None:
    if not any(r.get("feed_on") for r in valid):
        return None
    chance = cfg["analysis"]["chance"]
    control = next(x["id"] for x in cfg["arms"] if x.get("role") == "control")
    per: dict = {}
    excluded = Counter()
    by_theme: dict = defaultdict(lambda: [0, 0])
    slots = Counter()
    for r in valid:
        f = r.get("feed")
        if not r.get("feed_on"):
            continue
        if not exposure_ok(f, cfg):
            excluded["esposizione non valida (scheda nascosta o tempi fuori finestra)"] += 1
            continue
        arm = r["arm"]
        d = per.setdefault(arm, {"n": 0, "k": 0, "none": 0})
        d["n"] += 1
        d["k"] += bool(f.get("chose_candidate"))
        d["none"] += f.get("choice_slot") is None
        by_theme[(arm, r.get("theme"))][0] += 1
        by_theme[(arm, r.get("theme"))][1] += bool(f.get("chose_candidate"))
        slots[f.get("slot")] += 1
    for arm, d in per.items():
        d["share"] = d["k"] / d["n"] if d["n"] else None
        d["ci95"] = wilson(d["k"], d["n"])
        d["p_vs_caso"] = binom_upper(d["k"], d["n"], chance) if d["n"] else 1.0
        if arm != control and control in per:
            c = per[control]
            d["p_vs_controllo"] = fisher_two_sided(d["k"], d["n"] - d["k"], c["k"], c["n"] - c["k"])
    return {"per_arm": per, "excluded": dict(excluded), "chance": chance, "control": control,
            "by_theme": {f"{a}/{t}": {"n": v[0], "k": v[1]} for (a, t), v in by_theme.items()},
            "slots": {str(k): v for k, v in sorted(slots.items(), key=lambda kv: (kv[0] is None, kv[0]))}}


def coding_sheet(valid: list[dict], cfg: dict, out_dir: Path, seed: int = 7) -> tuple[Path, Path]:
    rows, key = [], {}
    rng = random.Random(seed)
    for r in valid:
        p = r.get("promise") or {}
        rid = hashlib.sha256((r.get("pid") or r.get("t_end") or str(id(r))).encode()).hexdigest()[:10]
        for tipo, txt in (("promessa", p.get("promise", "")), ("pubblico", p.get("audience", ""))):
            rows.append({"tipo": tipo, "testo": " ".join(str(txt).split()), "_rid": rid, "_arm": r["arm"],
                         "_ok": exposure_ok(p, cfg)})
    rng.shuffle(rows)
    sheet = out_dir / "codifica_da_compilare.csv"
    keyf = out_dir / "codifica_chiave.json"
    with sheet.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["riga", "tipo", "testo", "codice"])
        for i, row in enumerate(rows, start=1):
            w.writerow([i, row["tipo"], row["testo"], ""])
            key[str(i)] = {"rid": row["_rid"], "arm": row["_arm"], "tipo": row["tipo"], "esposizione_valida": row["_ok"]}
    keyf.write_text(json.dumps(key, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return sheet, keyf


def analyse_coding(coded: Path, keyf: Path, cfg: dict) -> dict:
    key = json.loads(keyf.read_text(encoding="utf-8"))
    pk = cfg["analysis"].get("promise_codes") or {}
    ak = cfg["analysis"].get("audience_codes") or {}
    res: dict = defaultdict(lambda: {"promessa": Counter(), "pubblico": Counter()})
    unknown = Counter()
    with coded.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = key.get(str(row.get("riga", "")).strip())
            code = (row.get("codice") or "").strip().upper()
            if not k or not code or not k.get("esposizione_valida", True):
                continue
            arm, tipo = k["arm"], k["tipo"]
            rules = (pk.get("per_arm", {}).get(arm) if tipo == "promessa" else ak.get("rules")) or {}
            if code not in {c.upper() for c in ((pk if tipo == "promessa" else ak).get("codes") or {})}:
                unknown[code] += 1
            label = ("giusta" if code in [c.upper() for c in rules.get("giusta", [])] else
                     "parziale" if code in [c.upper() for c in rules.get("parziale", [])] else "sbagliata")
            res[arm][tipo][label] += 1
    out = {}
    for arm, d in res.items():
        out[arm] = {}
        for tipo, c in d.items():
            n = sum(c.values())
            out[arm][tipo] = {"n": n, **dict(c), "quota_giusta": (c["giusta"] / n) if n else None,
                              "ci95_giusta": wilson(c["giusta"], n)}
    if unknown:
        out["_codici_sconosciuti"] = dict(unknown)
    return out


# ---------------------------------------------------------------- uscite


def pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.0f} %"


def fmt_p(p: float | None) -> str:
    return "–" if p is None else (f"{p:.3f}" if p >= 0.001 else "< 0,001").replace(".", ",")


def write_outputs(cfg: dict, valid: list[dict], reasons: Counter, warnings: list[str], h2h: dict,
                  feed: dict | None, coding: dict | None, sens: dict, total: int, out_dir: Path,
                  cost: str, panel: str) -> dict:
    labels = {a["id"]: a.get("label", a["id"]) for a in cfg["arms"]}
    alpha = cfg["analysis"]["alpha"]
    L = [f"# Risultati del pre-test — {cfg['study_id']}", "",
         f"Generato da `analizza.py` il {date.today().isoformat()} · panel: {panel} · costo: {cost or 'da compilare'}", "",
         "## Campione", "",
         f"- Risposte ricevute: **{total}** · valide: **{len(valid)}**"]
    for k, v in reasons.most_common():
        L.append(f"- Escluse — {k}: {v}")
    arms_n = Counter(r["arm"] for r in valid)
    L.append("- Valide per braccio: " + ", ".join(f"{a} {arms_n.get(a, 0)}" for a in labels))
    themes = Counter(r.get("theme") for r in valid)
    L.append("- Tema: " + ", ".join(f"{t} {n}" for t, n in themes.items()))
    for w in warnings:
        L.append(f"- Attenzione: {w}")
    L += ["", "## Testa a testa (decisione)", "",
          f"Test binomiale esatto a due code contro 50/50, α = {str(alpha).replace('.', ',')}. "
          "Coppie primarie corrette con Holm. Sotto la soglia l'esito è «pari».", "",
          "| Coppia | Voti | n | Quota del primo | Soglia (α) | p | p corretto | Esito | Quota a sinistra |",
          "|---|---|---|---|---|---|---|---|---|"]
    for key, v in h2h.items():
        tag = " (primaria)" if v["primary"] else " (secondaria)"
        votes = f"{v['a']} {v['votes'][v['a']]} · {v['b']} {v['votes'][v['b']]}"
        soglia = f"{v['soglia']}/{v['n']}" if v["soglia"] else "–"
        if v.get("soglia_holm_primo_passo"):
            soglia += f" (primo passo Holm: {v['soglia_holm_primo_passo']})"
        L.append(f"| {v['a']} vs {v['b']}{tag} | {votes} | {v['n']} | {pct(v['share_top'])} {v['top']} | {soglia} | "
                 f"{fmt_p(v['p'])} | {fmt_p(v['p_adj'])} | **{v['esito']}** | {pct(v['left_share'])} |")
    L += ["", "Quota a sinistra lontana dal 50 % = preferenza per il lato, non per la copertina: controlla la randomizzazione.", ""]
    if sens:
        L += ["Sensibilità (includendo chi conosceva già il podcast): " +
              "; ".join(f"{k.replace('|', ' vs ')} {v['esito']} ({v['votes'][v['a']]}–{v['votes'][v['b']]})" for k, v in sens.items()), ""]
    if feed:
        L += ["## Feed a tempo (descrittivo)", "",
              f"Quota di chi sceglie la nostra copertina tra 9 dopo 3 s. Caso = {pct(feed['chance'])}. "
              "Gruppi separati per braccio: con ~30 persone per braccio si vedono solo differenze grandi.", "",
              "| Braccio | n | Sceglie la nostra | Quota (IC 95 %) | p contro il caso | p contro il controllo | «Non ricordo» |",
              "|---|---|---|---|---|---|---|"]
        for arm in labels:
            d = feed["per_arm"].get(arm)
            if not d:
                continue
            ci = f"{pct(d['share'])} ({pct(d['ci95'][0])}–{pct(d['ci95'][1])})"
            L.append(f"| {labels[arm]} | {d['n']} | {d['k']} | {ci} | {fmt_p(d['p_vs_caso'])} | "
                     f"{fmt_p(d.get('p_vs_controllo')) if arm != feed['control'] else '—'} | {d['none']} |")
        for k, v in feed["excluded"].items():
            L.append(f"\nEscluse dal feed — {k}: {v}")
        L.append("\nPer tema: " + ", ".join(f"{k} {v['k']}/{v['n']}" for k, v in sorted(feed["by_theme"].items())))
        L.append("")
    L += ["## Cosa promette e a chi è rivolto (codifica alla cieca)", ""]
    if coding:
        L += ["| Braccio | Promessa giusta | parziale | sbagliata | Pubblico giusto | parziale | sbagliato |", "|---|---|---|---|---|---|---|"]
        for arm in labels:
            c = coding.get(arm)
            if not c:
                continue
            p, a = c.get("promessa", {}), c.get("pubblico", {})
            L.append(f"| {labels[arm]} | {p.get('giusta', 0)}/{p.get('n', 0)} ({pct(p.get('quota_giusta'))}) | {p.get('parziale', 0)} | "
                     f"{p.get('sbagliata', 0)} | {a.get('giusta', 0)}/{a.get('n', 0)} ({pct(a.get('quota_giusta'))}) | {a.get('parziale', 0)} | {a.get('sbagliata', 0)} |")
        if coding.get("_codici_sconosciuti"):
            L.append(f"\nCodici non previsti nella configurazione: {coding['_codici_sconosciuti']}")
    else:
        L.append("Da fare: compila `codifica_da_compilare.csv` (colonna `codice`) senza aprire `codifica_chiave.json`, "
                 "poi rilancia `report` con `--coding`.")
    L += ["", "## Lettura", "",
          "- Misura una preferenza dichiarata e la comprensione, non il CTR.",
          "- Un esito «vince» conta tra i ~3 risultati nella stessa direzione (07 §16); «pari» no.",
          "- Il braccio che vince entra nel prossimo controllo di sicurezza nativo (07 §15.1).", ""]
    (out_dir / "risultati.md").write_text("\n".join(L), encoding="utf-8")

    # riga per yt-db add ab_tests
    log = cfg.get("log") or {}
    prim = [v for v in h2h.values() if v["primary"]]
    winners = sorted({v["top"] for v in prim if v["esito"].startswith("vince")})
    winner = ""
    if len(winners) == 1:
        winner = winners[0]
    elif len(winners) > 1:
        sec = [v for v in h2h.values() if not v["primary"] and set([v["a"], v["b"]]) <= set(winners)]
        winner = sec[0]["top"] if sec and sec[0]["esito"].startswith("vince") else "/".join(winners)
    dates = sorted(r.get("t_end", "")[:10] for r in valid if r.get("t_end"))
    row = {
        "channel": log.get("channel", ""), "video_id": log.get("video_id", ""), "kind": "pretest",
        "variants_json": [{"id": a["id"], "role": a.get("role"), "file": a.get("file"), "template": a.get("template"),
                           "lever": a.get("lever"), "text": a.get("text"), "label": a.get("label")} for a in cfg["arms"]],
        "started_at": dates[0] if dates else "", "ended_at": dates[-1] if dates else "",
        "metric": "stated_preference", "winner": winner,
        "result_json": {
            "panel": panel, "study_id": cfg["study_id"], "variable": log.get("variable", ""),
            "n": sum(reasons.values()) + len(valid), "n_valid": len(valid), "exclusions": dict(reasons),
            "testa_a_testa": {k: {"voti": v["votes"], "n": v["n"], "p": round(v["p"], 4), "p_holm": round(v["p_adj"], 4),
                                  "soglia": v["soglia"], "esito": v["esito"], "primaria": v["primary"]} for k, v in h2h.items()},
            "feed_quota": {a: round(d["share"], 3) for a, d in (feed or {}).get("per_arm", {}).items() if d["share"] is not None} or None,
            "promessa_giusta": {a: round(c["promessa"]["quota_giusta"], 3) for a, c in (coding or {}).items()
                                if not a.startswith("_") and c.get("promessa", {}).get("quota_giusta") is not None} or None,
            "costo": cost, "vicini": log.get("neighbours_option", "a" if feed else "b"),
            "ok_ospite": log.get("guest_ok", "non indicato"),
        },
        "notes": f"pre-test {cfg['study_id']}: {log.get('variable', '')}; ipotesi in ipotesi.md; dettaglio in risultati.md",
    }
    (out_dir / "ab_tests_row.json").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    full = {"h2h": h2h, "feed": feed, "coding": coding, "exclusions": dict(reasons), "warnings": warnings,
            "n_total": total, "n_valid": len(valid)}
    (out_dir / "risultati.json").write_text(json.dumps(full, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return row


# ---------------------------------------------------------------- comandi


def cmd_report(args: argparse.Namespace) -> int:
    cfg = load_config(Path(args.config))
    out_dir = Path(args.out or Path(args.config).parent / "risultati")
    out_dir.mkdir(parents=True, exist_ok=True)
    recs: list[dict] = []
    for p in args.csv or []:
        recs += parse_records_from_csv(Path(p))
    for p in args.json or []:
        recs += parse_records_from_json(Path(p))
    if not recs:
        print("[analizza] nessun record trovato nei file indicati", file=sys.stderr)
        return 2
    valid, reasons, warnings = apply_exclusions(recs, cfg)
    h2h = analyse_h2h(valid, cfg)
    feed = analyse_feed(valid, cfg)
    sens = {}
    if cfg["analysis"]["exclude_knows_show"]:
        v2, _, _ = apply_exclusions(recs, cfg, include_knows=True)
        if len(v2) != len(valid):
            sens = analyse_h2h(v2, cfg)
    keyf = out_dir / "codifica_chiave.json"
    if not keyf.exists() or args.new_coding_sheet:
        sheet, keyf = coding_sheet(valid, cfg, out_dir)
        print(f"[analizza] foglio di codifica: {sheet}")
    coding = analyse_coding(Path(args.coding), keyf, cfg) if args.coding else None
    row = write_outputs(cfg, valid, reasons, warnings, h2h, feed, coding, sens, len(recs), out_dir,
                        args.cost or "", args.panel or (cfg.get("log") or {}).get("panel", "prolific"))
    print(f"[analizza] risposte {len(recs)} · valide {len(valid)} · " +
          " · ".join(f"{k.replace('|', ' vs ')}: {v['esito']} ({v['votes'][v['a']]}–{v['votes'][v['b']]})" for k, v in h2h.items()))
    print(f"[analizza] {out_dir / 'risultati.md'} · {out_dir / 'ab_tests_row.json'} (winner: {row['winner'] or 'nessuno'})")
    return 0


def cmd_binom(args: argparse.Namespace) -> int:
    k, n = args.k, args.n
    p = binom_two_sided(max(k, n - k), n)
    t = win_threshold(n, args.alpha)
    print(f"{k}/{n} = {100 * k / n:.1f} % · p a due code {p:.4f} · soglia {t}/{n} · "
          f"{'vince il braccio con ' + str(max(k, n - k)) if p <= args.alpha and k != n - k else 'pari'}")
    return 0


def cmd_soglie(args: argparse.Namespace) -> int:
    ns = args.n or [30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 200]
    print(f"| n | vince con almeno (α {args.alpha}) | con α {args.alpha / 2} (primo passo Holm su 2 coppie) | potenza se la preferenza vera è 65/35 | 70/30 |")
    print("|---|---|---|---|---|")
    for n in ns:
        t, t2 = win_threshold(n, args.alpha), win_threshold(n, args.alpha / 2)
        pw = lambda q: sum(binom_pmf(n, i, q) for i in range(t, n + 1)) if t else 0.0  # noqa: E731
        print(f"| {n} | {t} ({100 * t / n:.0f} %) | {t2} | {100 * pw(0.65):.0f} % | {100 * pw(0.70):.0f} % |")
    return 0


def cmd_pickfu(args: argparse.Namespace) -> int:
    if len(args.pair) != len(args.counts):
        print("ogni --pair vuole il suo --counts", file=sys.stderr)
        return 2
    ps = {}
    for (a, b), (ka, kb) in zip(args.pair, args.counts):
        ps[f"{a}|{b}"] = (a, b, ka, kb, binom_two_sided(max(ka, kb), ka + kb))
    adj = holm({k: v[4] for k, v in ps.items()}) if len(ps) > 1 else {k: v[4] for k, v in ps.items()}
    for k, (a, b, ka, kb, p) in ps.items():
        n = ka + kb
        top = a if ka > kb else b
        esito = f"vince {top}" if ka != kb and adj[k] <= args.alpha else "pari"
        print(f"{a} vs {b}: {ka}–{kb} (n {n}) · soglia {win_threshold(n, args.alpha)}/{n} · p {p:.4f} · "
              f"p Holm {adj[k]:.4f} · {esito}")
    return 0


def cmd_selftest(_: argparse.Namespace) -> int:
    assert win_threshold(100) == 61 and win_threshold(50) == 33 and win_threshold(200) == 115, "soglie"
    assert win_threshold(100, 0.025) == 62, "soglia Holm"
    assert abs(binom_two_sided(61, 100) - 0.0352) < 1e-3
    assert abs(fisher_two_sided(3, 1, 1, 3) - 0.4857) < 1e-3
    h = holm({"x": 0.01, "y": 0.04})
    assert abs(h["x"] - 0.02) < 1e-9 and abs(h["y"] - 0.04) < 1e-9
    lo, hi = wilson(10, 100)
    assert 0.05 < lo < 0.06 and 0.17 < hi < 0.18
    # dati simulati: A batte ab1 al 70 %, C pari con ab1, A vs C 60/40
    rng = random.Random(11)
    cfg = {"study_id": "sim", "arms": [{"id": "ab1", "role": "control"}, {"id": "A", "role": "candidate"}, {"id": "C", "role": "candidate"}],
           "pairs": [["A", "ab1"], ["C", "ab1"], ["A", "C"]], "primary_pairs": [["A", "ab1"], ["C", "ab1"]],
           "analysis": {"promise_codes": {"codes": {"T2": "", "T1": "", "V2": "", "X": ""},
                                          "per_arm": {"ab1": {"giusta": ["T2"], "parziale": ["T1"]}, "A": {"giusta": ["T2"], "parziale": ["T1"]},
                                                      "C": {"giusta": ["V2"], "parziale": []}}},
                        "audience_codes": {"codes": {"F": "", "P": "", "X": ""}, "rules": {"giusta": ["F"], "parziale": ["P"]}}},
           "log": {"channel": "sim", "video_id": "SIM", "variable": "pacchetto"}}
    cfg = json.loads(json.dumps(cfg))
    for k, v in {"alpha": 0.05, "primary_correction": "holm", "min_total_s": 25, "exclude_knows_show": True,
                 "chance": 1 / 9, "exposure_window_ms": [2500, 3700]}.items():
        cfg["analysis"].setdefault(k, v)
    pref = {"A|ab1": 0.70, "C|ab1": 0.50, "A|C": 0.60}
    recs = []
    for i in range(110):
        arm = rng.choice(["ab1", "A", "C"])
        h2h = []
        for j, (x, y) in enumerate(cfg["pairs"]):
            left, right = (x, y) if rng.random() < 0.5 else (y, x)
            ch = x if rng.random() < pref[f"{x}|{y}"] else y
            h2h.append({"pair": f"{x}|{y}", "left": left, "right": right, "choice": ch, "position": j, "rt_ms": 2000})
        slot = rng.randrange(9)
        chose = rng.random() < {"ab1": 0.15, "A": 0.30, "C": 0.25}[arm]
        recs.append({"study_id": "sim", "build": "b1", "preview": False, "pid": f"P{i}", "arm": arm, "theme": rng.choice(["dark", "light"]),
                     "feed_on": True, "imc": {"pass": i % 37 != 0},
                     "feed": {"slot": slot, "exposure_ms": 3005, "hidden_during_exposure": i % 50 == 0,
                              "choice_slot": slot if chose else (slot + 1) % 9, "chose_candidate": chose},
                     "promise": {"promise": "perché il codice non bastava" if arm != "C" else "perché ha venduto",
                                 "audience": "founder", "exposure_ms": 3003, "hidden_during_exposure": False},
                     "h2h": h2h, "profile": {"freq": "settimana", "knows_show": "si" if i == 5 else "no"},
                     "total_ms": 20000 if i == 7 else 80000, "t_end": f"2026-10-2{i % 3}T10:00:00Z"})
    recs.append(dict(recs[3]))  # duplicato
    valid, reasons, warnings = apply_exclusions(recs, cfg)
    assert reasons["duplicato (stesso ID Prolific)"] == 1 and reasons["conosceva già il podcast"] == 1, reasons
    assert reasons["controllo di attenzione sbagliato"] == 3, reasons
    assert any(k.startswith("troppo veloce") for k in reasons), reasons
    h = analyse_h2h(valid, cfg)
    assert h["A|ab1"]["esito"] == "vince A", h["A|ab1"]
    assert h["A|ab1"]["n"] == len(valid)
    f = analyse_feed(valid, cfg)
    assert f["excluded"], "esposizioni non valide escluse"
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        sheet, keyf = coding_sheet(valid, cfg, tdp)
        with sheet.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert "arm" not in rows[0] and len(rows) == 2 * len(valid)
        with (tdp / "coded.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["riga", "tipo", "testo", "codice"])
            for r in rows:
                code = ("F" if r["tipo"] == "pubblico" else ("T2" if "codice" in r["testo"] else "V2"))
                w.writerow([r["riga"], r["tipo"], r["testo"], code])
        c = analyse_coding(tdp / "coded.csv", keyf, cfg)
        assert c["A"]["promessa"]["quota_giusta"] == 1.0 and c["C"]["promessa"]["quota_giusta"] == 1.0
        row = write_outputs(cfg, valid, reasons, warnings, h, f, c, {}, len(recs), tdp, "£0", "simulazione")
        assert row["kind"] == "pretest" and row["winner"] in ("A",), row["winner"]
        assert (tdp / "risultati.md").read_text(encoding="utf-8").count("vince A") >= 1
    print(f"[analizza] selftest ok · simulati {len(recs)} · validi {len(valid)} · "
          f"A vs ab1 {h['A|ab1']['votes']} · C vs ab1 {h['C|ab1']['votes']} ({h['C|ab1']['esito']}) · "
          f"A vs C {h['A|C']['votes']} ({h['A|C']['esito']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="analisi completa")
    r.add_argument("--config", required=True)
    r.add_argument("--csv", nargs="*", help="CSV scaricati dal Google Sheet delle risposte")
    r.add_argument("--json", nargs="*", help="JSON delle anteprime (prove)")
    r.add_argument("--coding", help="foglio di codifica compilato")
    r.add_argument("--new-coding-sheet", action="store_true", help="rigenera il foglio di codifica")
    r.add_argument("--cost", help="costo effettivo del panel, es. «£43»")
    r.add_argument("--panel", help="prolific | pickfu")
    r.add_argument("--out", help="cartella dei risultati (default: <cartella config>/risultati)")
    r.set_defaults(fn=cmd_report)
    b = sub.add_parser("binom", help="test binomiale esatto a due code")
    b.add_argument("k", type=int)
    b.add_argument("n", type=int)
    b.add_argument("--alpha", type=float, default=0.05)
    b.set_defaults(fn=cmd_binom)
    s = sub.add_parser("soglie", help="tabella delle soglie")
    s.add_argument("n", type=int, nargs="*")
    s.add_argument("--alpha", type=float, default=0.05)
    s.set_defaults(fn=cmd_soglie)
    p = sub.add_parser("pickfu", help="conteggi di PickFu (testa a testa o coppie da un Ranked)")
    p.add_argument("--pair", nargs=2, action="append", required=True, metavar=("X", "Y"))
    p.add_argument("--counts", nargs=2, type=int, action="append", required=True, metavar=("KX", "KY"))
    p.add_argument("--alpha", type=float, default=0.05)
    p.set_defaults(fn=cmd_pickfu)
    t = sub.add_parser("selftest", help="prova con dati simulati")
    t.set_defaults(fn=cmd_selftest)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
