#!/usr/bin/env bash
# health.sh — check the Crimson Terminal OS install. The shell checks run even when Python is broken.
. "$(dirname "${BASH_SOURCE[0]}")/tos-lib.sh" "$@"
bad=0
chk() { if eval "$2"; then ok "$1"; else err "$1 — $3"; bad=$((bad + 1)); fi; }

hdr "install"
NAME="$(cat "$TOS_STATE/terminal-os.command" 2>/dev/null || echo crimson)"
chk "command '$NAME'" '[ -x "$BIN_DIR/$NAME" ]' "run scripts/install.sh"
chk "crimson-konsole wrapper" '[ -x "$BIN_DIR/crimson-konsole" ]' "run scripts/install.sh"
chk "crimson-autostart" '[ -x "$BIN_DIR/crimson-autostart" ]' "run scripts/install.sh"
chk "venv python" '[ -x "$VENV/bin/python" ]' "run scripts/install.sh"
chk "python packages" '"$VENV/bin/python" -c "import textual, rich, psutil" 2>/dev/null' "run scripts/update.sh"
chk "wrapper is valid sh" 'sh -n "$BIN_DIR/crimson-konsole" 2>/dev/null' "reinstall"

hdr "konsole"
if have konsole; then ok "$(konsole --version 2>/dev/null | tail -1)"; else warn "konsole not installed"; fi
bash "$TOS/scripts/konsole-theme.sh" status
sh "$TOS/bin/crimson-autostart" status | sed 's/^/  /'
[ -f "$TOS_STATE/terminal-os.log" ] && { say "last log lines ($TOS_STATE/terminal-os.log):"; tail -5 "$TOS_STATE/terminal-os.log" | sed 's/^/  /'; }

hdr "doctor"
if [ -x "$VENV/bin/python" ]; then "$TOS/bin/crimson" --doctor || bad=$((bad + 1)); else warn "skipped (no venv)"; fi
[ "$bad" = 0 ] && say "healthy" || { err "$bad problem(s)"; exit 1; }
