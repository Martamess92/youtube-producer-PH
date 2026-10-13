"""Credenziali condivise del toolkit: OAuth in sola lettura per canale + API key.

Segreti fuori dal repo: <studio_dir>/secrets/ (default ~/youtube-studio/secrets, chmod 700).
- client_secret.json      → OAuth client "Desktop app" scaricato da Google Cloud
- token-<channel>.json    → refresh token per canale (slug del profilo: proprio, personale o cliente)
- api_key                 → chiave Data API v3 (solo ricerca pubblica)
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

try:  # stessa cartella di ytcore (<studio_dir>/secrets, configurabile; YT_SECRETS vince)
    import ytcore as _ytcore
    SECRETS = _ytcore.SECRETS
except ImportError:
    SECRETS = Path(os.environ.get("YT_SECRETS", Path.home() / "youtube-studio" / "secrets"))
CLIENT_SECRET = SECRETS / "client_secret.json"

# Solo scope di lettura. Mai youtube, youtube.upload o youtube.force-ssl.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def token_path(channel: str) -> Path:
    return SECRETS / f"token-{channel}.json"


def _lock_down(path: Path) -> None:
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def load_credentials(channel: str):
    """Credenziali OAuth del canale, rinnovate se scadute. Errore chiaro se manca il token."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = token_path(channel)
    if not path.exists():
        raise SystemExit(
            f"Nessun token per il canale '{channel}'. Esegui: yt-auth --channel {channel}"
        )
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            path.write_text(creds.to_json())
            _lock_down(path)
        else:
            raise SystemExit(
                f"Token del canale '{channel}' non valido. Ripeti: yt-auth --channel {channel}"
            )
    return creds


def save_credentials(channel: str, creds, channel_meta: dict) -> Path:
    SECRETS.mkdir(parents=True, exist_ok=True)
    SECRETS.chmod(stat.S_IRWXU)
    data = json.loads(creds.to_json())
    data["_channel"] = channel_meta
    path = token_path(channel)
    path.write_text(json.dumps(data, indent=2))
    _lock_down(path)
    return path


def api_key() -> str | None:
    env = os.environ.get("YT_API_KEY")
    if env:
        return env.strip()
    path = SECRETS / "api_key"
    return path.read_text().strip() if path.exists() else None
