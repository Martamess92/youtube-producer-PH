"""yt-auth — autorizza un canale YouTube in SOLA LETTURA e salva il token.

Uso:
  yt-auth --channel <slug>          # si apre il browser: scegli il canale del profilo <slug> (channels_dirs)
  yt-auth --channel <slug> --check

Per i canali Brand Account (es. il canale di un'azienda) Google chiede quale canale usare:
scegli quello giusto, lo script verifica e stampa il canale autorizzato.
"""
from __future__ import annotations

import argparse
import json
import sys

from ytauth import CLIENT_SECRET, SCOPES, load_credentials, save_credentials, token_path


def describe(creds) -> dict:
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise SystemExit("L'account autorizzato non ha un canale YouTube.")
    ch = items[0]
    return {
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "customUrl": ch["snippet"].get("customUrl"),
        "subscribers": ch.get("statistics", {}).get("subscriberCount"),
        "videos": ch.get("statistics", {}).get("videoCount"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-auth", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", required=True, help="slug del profilo canale (proprio, personale o cliente)")
    ap.add_argument("--check", action="store_true", help="verifica il token esistente senza riautorizzare")
    args = ap.parse_args()

    if args.check:
        creds = load_credentials(args.channel)
        print(json.dumps({"channel": args.channel, **describe(creds)}, indent=2, ensure_ascii=False))
        return

    if not CLIENT_SECRET.exists():
        sys.exit(
            f"Manca {CLIENT_SECRET}.\n"
            "Scarica il JSON del client OAuth 'Desktop app' da Google Cloud → API e servizi → "
            "Credenziali e salvalo con quel nome."
        )

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline", open_browser=True)
    meta = describe(creds)
    path = save_credentials(args.channel, creds, meta)
    print(f"Autorizzato in sola lettura: {meta['title']} ({meta['id']}) → {path}")
    print(f"Prossimo passo: yt-reporting-setup --channel {args.channel}")


if __name__ == "__main__":
    main()
