"""yt-reporting-setup — crea i job della YouTube Reporting API per un canale.

Perché subito: CTR e impressioni delle thumbnail esistono SOLO nei report "reach"
della Reporting API, e un job appena creato recupera al massimo 30 giorni di storico.
Ogni giorno senza job è storico perso.

Versioni dei report: per ogni tipo base (es. channel_basic) si chiede la versione _aN più
alta tra quelle che il canale offre (oggi channel_basic_a3). Le versioni precedenti restano
richieste solo dove indicato in KEEP_PREVIOUS e solo se il canale le offre ancora
(channel_basic_a2: continuità con lo storico già raccolto; yt-collect legge entrambe).
I job esistenti non vengono mai cancellati.

Uso:
  yt-reporting-setup --channel esempio            # crea i job mancanti
  yt-reporting-setup --channel esempio --dry-run  # mostra cosa creerebbe, senza creare nulla
  yt-reporting-setup --channel esempio --list     # job esistenti, tipi disponibili e piano per tipo base

Stampa un solo JSON di riepilogo su stdout (i messaggi vanno su stderr).
"""
from __future__ import annotations

import argparse
import re

import ytcore
from ytcore import log

# Tipi base da tenere sempre attivi (la versione _aN si sceglie a runtime: la più alta offerta).
WANTED_BASES = [
    "channel_reach_basic",          # impressioni + CTR thumbnail per video
    "channel_reach_combined",       # come sopra, per traffic source / device
    "channel_basic",                # views, watch time, iscritti per giorno e video
    "channel_traffic_source",       # da dove arrivano le visualizzazioni
    "channel_playback_location",
    "channel_demographics",
    "channel_subtitles",
]
# Versioni precedenti da richiedere ANCHE, se il canale le offre ancora.
KEEP_PREVIOUS = {"channel_basic": ["channel_basic_a2"]}
VERSION_RE = re.compile(r"^(?P<base>.+)_a(?P<n>\d+)$")


def plan_types(available: set[str] | list[str]) -> dict[str, dict]:
    """Per ogni tipo base: versione da richiedere (la più alta offerta), versioni precedenti da
    tenere, versioni offerte. {base: {"want": [...], "offered": [...], "chosen": str | None}}"""
    by_base: dict[str, list[tuple[int, str]]] = {}
    for t in available:
        m = VERSION_RE.match(t)
        if m:
            by_base.setdefault(m["base"], []).append((int(m["n"]), t))
    plan = {}
    for base in WANTED_BASES:
        offered = [t for _, t in sorted(by_base.get(base, []))]
        chosen = offered[-1] if offered else None
        want = [chosen] if chosen else []
        want += [t for t in KEEP_PREVIOUS.get(base, []) if t in offered and t not in want]
        plan[base] = {"chosen": chosen, "want": want, "offered": offered}
    return plan


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-reporting-setup", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", required=True, help="slug del canale (token in <studio_dir>/secrets/token-<slug>.json)")
    ap.add_argument("--list", action="store_true", help="elenca job esistenti, tipi disponibili e il piano per tipo base")
    ap.add_argument("--dry-run", action="store_true", help="mostra i job che verrebbero creati, senza crearli")
    args = ap.parse_args()

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from ytauth import load_credentials
    except ImportError as exc:
        ytcore.fail(f"dipendenze Google mancanti nel venv: {exc}")

    try:
        creds = load_credentials(args.channel)
    except SystemExit as exc:  # ytauth segnala token mancante/non valido con SystemExit(msg)
        ytcore.fail(str(exc), channel=args.channel)
    except Exception as exc:  # rinnovo del token fallito (RefreshError, rete…)
        ytcore.fail(f"credenziali del canale '{args.channel}' non utilizzabili: {exc}", channel=args.channel)

    try:
        rep = build("youtubereporting", "v1", credentials=creds, cache_discovery=False)
        types = {t["id"]: t.get("name", "") for t in rep.reportTypes().list().execute().get("reportTypes", [])}
        jobs = rep.jobs().list().execute().get("jobs", [])
    except HttpError as exc:
        ytcore.fail(f"Reporting API: {exc}", channel=args.channel)
    existing = {j["reportTypeId"]: j for j in jobs}
    plan = plan_types(set(types))
    wanted = [t for p in plan.values() for t in p["want"]]

    if args.list:
        ytcore.emit(True, channel=args.channel,
                    jobs=[{"id": j["id"], "type": j["reportTypeId"], "created": j.get("createTime")} for j in jobs],
                    available_types=sorted(types), plan=plan)
        return

    created, skipped, missing, would_create = [], [], [], []
    legacy = sorted(t for t in existing if t not in wanted and VERSION_RE.match(t)
                    and VERSION_RE.match(t)["base"] in plan)
    for base, p in plan.items():
        if not p["want"]:
            missing.append(base)
    for type_id in wanted:
        if type_id in existing:
            skipped.append(type_id)
        elif args.dry_run:
            would_create.append(type_id)
        else:
            try:
                job = rep.jobs().create(body={"reportTypeId": type_id,
                                              "name": f"youtube-producer {args.channel} {type_id}"}).execute()
            except HttpError as exc:
                ytcore.fail(f"creazione del job {type_id} fallita: {exc}", channel=args.channel,
                            created=created, already_present=skipped)
            created.append({"type": type_id, "job_id": job["id"]})

    warnings = []
    if missing:
        warnings.append(f"tipi base non offerti a questo canale: {', '.join(missing)}")
    if legacy:
        warnings.append(f"job di versioni precedenti ancora attivi (non toccati): {', '.join(legacy)}")
    if created:
        log("I primi report (con fino a 30 giorni di backfill) arrivano in 24-48 ore.")
    ytcore.emit(True, channel=args.channel, dry_run=args.dry_run, created=created, would_create=would_create,
                already_present=skipped, not_available_for_channel=missing, legacy_jobs=legacy,
                chosen={b: p["chosen"] for b, p in plan.items()},
                note="primi report (fino a 30 giorni di backfill) in 24-48 ore" if created else None,
                warnings=warnings)


if __name__ == "__main__":
    main()
