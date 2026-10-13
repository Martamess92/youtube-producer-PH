# _paths.sh — risoluzione dei percorsi del plugin (sorgente comune di _run, install.sh, session-hint.sh).
# Va incluso con `. _paths.sh` dopo aver impostato YT_HOME (= …/scripts/yt). Bash 3.2 (macOS); processi esterni
# solo sed (id della data dir) e shasum (impronta). Stessa logica di lib/config.py (resolve_data_dir): se cambi qui,
# cambia anche lì.

# yt_data_dir → data dir del plugin; riga vuota = checkout di sviluppo con layout storico (scripts/yt/.venv).
# Ordine: YT_DATA → CLAUDE_PLUGIN_DATA (solo «youtube-…», non «youtube-inline») → cache dei plugin → scripts/yt/.venv →
# predefinita (~/.claude/plugins/data/youtube-youtube-producer).
yt_data_dir() {
  if [ -n "${YT_DATA:-}" ]; then
    case "$YT_DATA" in "~"|"~/"*) printf '%s%s\n' "$HOME" "${YT_DATA#\~}" ;; *) printf '%s\n' "$YT_DATA" ;; esac
    return 0
  fi
  if [ -n "${CLAUDE_PLUGIN_DATA:-}" ]; then
    # solo la data dir di questo plugin; non «youtube-inline» (--plugin-dir): i comandi lanciati dal tool Bash non
    # vedono CLAUDE_PLUGIN_DATA e userebbero un'altra cartella
    local cpd="${CLAUDE_PLUGIN_DATA%/}"
    case "${cpd##*/}" in youtube-inline) ;; youtube-*) printf '%s\n' "$cpd"; return 0 ;; esac
  fi
  case "$YT_HOME" in
    */plugins/cache/*/scripts/yt)
      local rest after base mkt plugin ver extra
      rest="${YT_HOME%/scripts/yt}"            # …/plugins/cache/<marketplace>/<plugin>/<versione>
      after="${rest#*/plugins/cache/}"          # <marketplace>/<plugin>/<versione>
      base="${rest%%/plugins/cache/*}/plugins"
      IFS=/ read -r mkt plugin ver extra <<EOF
$after
EOF
      if [ -n "$mkt" ] && [ -n "$plugin" ] && [ -n "$ver" ] && [ -z "$extra" ]; then
        printf '%s/data/%s\n' "$base" "$(printf '%s@%s' "$plugin" "$mkt" | LC_ALL=C sed 's/[^A-Za-z0-9_-]/-/g')"
        return 0
      fi
      ;;
  esac
  if [ -x "$YT_HOME/.venv/bin/python" ]; then
    printf '\n'
    return 0
  fi
  printf '%s/plugins/data/youtube-youtube-producer\n' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
}

# File che determinano il setup (stessa lista di lib/config.py FINGERPRINT_FILES).
YT_FINGERPRINT_FILES="install.sh pyproject.toml uv.lock node/package-lock.json remotion/package-lock.json swift/thumbvision.swift"

# yt_fingerprint → sha256 dell'elenco «<sha256>  <file>» (file mancante = «-»), identico a config.setup_fingerprint().
yt_fingerprint() {
  local f line
  for f in $YT_FINGERPRINT_FILES; do
    if [ -f "$YT_HOME/$f" ]; then
      line="$(shasum -a 256 "$YT_HOME/$f")"
      printf '%s  %s\n' "${line%% *}" "$f"
    else
      printf '%s  %s\n' "-" "$f"
    fi
  done | shasum -a 256 | sed 's/ .*//'
}
