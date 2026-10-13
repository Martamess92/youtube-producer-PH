"""yt-db — manutenzione del database <studio_dir>/data/yt.db (shim verso ytdb.py; default ~/youtube-studio).

Uso: yt-db status | init | purge [--days 30] | query "SELECT …" | add TABELLA '{json}'
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytdb  # noqa: E402

if __name__ == "__main__":
    sys.argv[0] = "yt-db"
    ytdb.main()
