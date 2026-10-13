"""yt-new — crea la cartella di lavoro di un episodio/video e il suo project.json.

Uso:
  yt-new --channel esempio --slug ospite-paolo --src ~/Downloads/registrazione.mp4 \\
         --glossary "Acme Robotics,Paolo Bianchi" --kind podcast
  yt-new --channel <slug> --slug ai-pm --src cam.mov mic.wav --roles camera,mic --main A
  yt-new … --workdir ~/youtube-studio/work/_test/ingest/ep1      # percorso esplicito

Crea <studio_dir>/work/<channel>/<YYYY-MM-DD>-<slug>/ (default ~/youtube-studio) con le sottocartelle standard
(src, analysis, edit, deliver, thumbs, shorts, qa, logs), mette in src/ un SYMLINK a ogni
sorgente (gli originali non vengono mai copiati, modificati o cancellati) e scrive
project.json (design §8.1) con hash veloce (testa+coda 64 MB + dimensione) di ogni sorgente.

Ruoli: master | camera | mic | other. Senza --roles: il primo sorgente con video è
'master', gli altri video 'camera', i file solo audio 'mic'.
Rifiuta di sovrascrivere un project.json esistente senza --force (che conserva 'created').
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import string
from pathlib import Path

import ytcore
from frames import media_label, probe_summary
from ytcore import emit, fail, log

ROLES = ("master", "camera", "mic", "other")
KINDS = ("podcast", "talking-head", "other")
HASH_LIMIT = 64 * 1024 * 1024


def _keys(n: int) -> list[str]:
    letters = string.ascii_uppercase
    return [letters[i] if i < 26 else letters[i // 26 - 1] + letters[i % 26] for i in range(n)]


def _split_list(text: str | None) -> list[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def _parse_speakers(text: str | None) -> dict:
    speakers = {}
    for item in _split_list(text):
        if "=" not in item:
            raise ValueError(f"--speakers: atteso S0=Nome, trovato '{item}'")
        k, v = item.split("=", 1)
        speakers[k.strip()] = v.strip()
    return speakers


def _link_name(src_dir: Path, key: str, path: Path, used: set[str]) -> str:
    """Nome del symlink in src/: basename originale, prefisso con la chiave se collide."""
    name = path.name
    if name in used:
        name = f"{key}-{name}"
    target = src_dir / name
    # Un file regolare in src/ non è nostro: mai toccarlo, usa un altro nome.
    if target.exists() and not target.is_symlink():
        name = f"{key}-{name}"
    used.add(name)
    return name


def _profile_kind(channel: str) -> str:
    """Tipo di video di default dal profilo canale (chiave facoltativa `video_kind`), altrimenti 'other'."""
    try:
        k = ytcore.load_channel(channel).get("video_kind")
    except Exception:  # noqa: BLE001 — profilo assente o illeggibile: nessun default dal profilo
        k = None
    return k if k in KINDS else "other"


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-new", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", required=True, help="slug del profilo canale (<slug>.md nei channels_dirs)")
    ap.add_argument("--slug", required=True, help="nome breve del video (diventa <data>-<slug>)")
    ap.add_argument("--src", nargs="+", action="extend", required=True, metavar="FILE",
                    help="uno o più sorgenti (master, camere, tracce mic)")
    ap.add_argument("--roles", help="ruoli nell'ordine dei --src, separati da virgola (master,camera,mic,other)")
    ap.add_argument("--main", help="chiave del sorgente principale (default: il primo 'master', altrimenti A)")
    ap.add_argument("--date", help="data YYYY-MM-DD (default: oggi)")
    ap.add_argument("--kind", choices=KINDS, help="podcast | talking-head | other (default: video_kind del profilo canale, altrimenti other)")
    ap.add_argument("--title", default="", help="titolo di lavoro")
    ap.add_argument("--glossary", help="termini extra per la trascrizione, separati da virgola")
    ap.add_argument("--speakers", help="mappa iniziale S0=Nome,S1=Nome")
    ap.add_argument("--workdir", help="percorso esplicito della cartella di lavoro")
    ap.add_argument("--force", action="store_true", help="riscrive project.json e i symlink esistenti")
    args = ap.parse_args()

    try:
        warnings: list[str] = []
        date = args.date or ytcore.today()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            fail(f"--date non valida: {date} (atteso YYYY-MM-DD)")
        dt.date.fromisoformat(date)
        slug = ytcore.slugify(args.slug)
        channel = args.channel.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", channel):
            fail(f"--channel non valido: '{channel}' (minuscole, cifre, - o _)")

        # Profilo canale: utile ma non obbligatorio (lo controlla yt-doctor --channel).
        try:
            ytcore.load_channel(channel)
        except FileNotFoundError as exc:
            warnings.append(str(exc))
        except Exception as exc:  # YAML rotto: segnalalo e prosegui
            warnings.append(f"profilo canale '{channel}' illeggibile: {exc}")

        wd = Path(args.workdir).expanduser().resolve() if args.workdir else ytcore.workdir_path(channel, slug, date)
        pj = wd / "project.json"
        previous = None
        if pj.exists():
            if not args.force:
                fail(f"Esiste già {pj}. Usa --force per riscriverlo (gli originali non vengono toccati).",
                     workdir=str(wd))
            previous = ytcore.load_project(wd)

        # Sorgenti: esistenza, probe, ruoli.
        paths = [Path(p).expanduser().resolve() for p in args.src]
        for p in paths:
            if not p.is_file():
                fail(f"Sorgente non trovato o non è un file: {p}")
            if wd in p.parents:
                fail(f"Il sorgente sta dentro la cartella di lavoro: {p}")
        if len(set(paths)) != len(paths):
            fail("Lo stesso sorgente è indicato due volte in --src")
        roles = _split_list(args.roles)
        if roles and len(roles) != len(paths):
            fail(f"--roles ha {len(roles)} voci ma --src ha {len(paths)} file")
        for r in roles:
            if r not in ROLES:
                fail(f"Ruolo non valido: {r} (ammessi: {', '.join(ROLES)})")

        keys = _keys(len(paths))
        summaries = {}
        for key, p in zip(keys, paths):
            try:
                summaries[key] = probe_summary(p)
            except Exception as exc:
                fail(f"ffprobe non riesce a leggere {p}: {exc}")
            if not summaries[key].get("video") and not summaries[key].get("audio"):
                fail(f"Nessuno stream audio/video in {p}")
        if not roles:
            master_given = False
            for key in keys:
                has_video = bool(summaries[key].get("video"))
                if has_video and not master_given:
                    roles.append("master")
                    master_given = True
                else:
                    roles.append("camera" if has_video else "mic")
        main_key = args.main or next((k for k, r in zip(keys, roles) if r == "master"), keys[0])
        if main_key not in keys:
            fail(f"--main {main_key} non esiste (chiavi: {', '.join(keys)})")

        # Cartelle + symlink (mai copie). Con --force si sostituiscono solo i symlink.
        for sub in ytcore.WORK_SUBDIRS:
            (wd / sub).mkdir(parents=True, exist_ok=True)
        src_dir = wd / "src"
        used: set[str] = set()
        sources = {}
        for key, p, role in zip(keys, paths, roles):
            name = _link_name(src_dir, key, p, used)
            link = src_dir / name
            if link.is_symlink():
                if Path(os.readlink(link)) != p:
                    if not args.force:
                        fail(f"{link} punta già a {os.readlink(link)} (usa --force)")
                    link.unlink()  # rimuove solo il symlink, mai il file puntato
            if not link.is_symlink():
                link.symlink_to(p)
            st = p.stat()
            log(f"· {key} [{role}] {p.name}: hash veloce…")
            sources[key] = {
                "path": str(p),
                "link": f"src/{name}",
                "role": role,
                "sha256_fast": ytcore.sha256_file(p, limit_bytes=HASH_LIMIT),
                "size": st.st_size,
                "mtime": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "duration": round(summaries[key]["duration"], 3),
                "media": media_label(summaries[key]),
            }

        now = dt.datetime.now().isoformat(timespec="seconds")
        prev = previous or {}
        # Con --force i campi non ripassati restano quelli di prima; stato e gate si
        # azzerano solo se i sorgenti sono cambiati (hash diverso).
        same_sources = bool(prev) and {k: (s["path"], s["sha256_fast"]) for k, s in sources.items()} == \
            {k: (s.get("path"), s.get("sha256_fast")) for k, s in (prev.get("sources") or {}).items()}
        kind = args.kind or prev.get("kind") or _profile_kind(channel)
        project = {
            "version": 1,
            "channel": channel,
            "slug": slug,
            "date": date,
            "title_working": args.title if args.title else prev.get("title_working", ""),
            "kind": kind,
            "main_source": main_key,
            "sources": sources,
            "glossary_extra": _split_list(args.glossary) if args.glossary is not None else prev.get("glossary_extra", []),
            "speakers": _parse_speakers(args.speakers) if args.speakers is not None else prev.get("speakers", {}),
            "gates": prev.get("gates", {"G1": "pending", "G2": "pending"}) if same_sources else {"G1": "pending", "G2": "pending"},
            "status": prev.get("status", "new") if same_sources else "new",
            "created": prev.get("created", now),
            "updated": now,
        }
        ytcore.save_project(wd, project)
        log(f"✓ cartella di lavoro: {wd}")
        emit(True, workdir=str(wd), project=project,
             outputs={"project_json": str(pj), "src": [str(src_dir / Path(s["link"]).name) for s in sources.values()]},
             next=f"yt-ingest {wd}", warnings=warnings)
    except SystemExit:
        raise
    except Exception as exc:
        log(f"✗ {exc}")
        fail(str(exc))


if __name__ == "__main__":
    main()
