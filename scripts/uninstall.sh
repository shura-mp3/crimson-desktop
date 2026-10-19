#!/usr/bin/env bash
# Crimson Desktop — remove what install.sh added (services, ~/.local/bin links, fonts).
# Theme changes are undone separately with restore-theme.sh. Packages are never removed
# automatically: the ones install.sh added are listed so you can decide.
set -u
. "$(dirname "$0")/lib.sh"
LOG="$STATE_DIR/install-manifest.txt"

ask "stop and remove the Crimson services, command links and fonts?" n || exit 0
systemctl --user disable --now crimson-dashboard.service crimson-core.service >/dev/null 2>&1
if [ -f "$LOG" ]; then
    while read -r kind path; do
        case "$kind" in
            link|unit) [ -L "$path" ] || [ -f "$path" ] && rm -f -- "$path" && ok "removed ${path/#$HOME/~}" ;;
            dir) [[ "$path" == "$HOME/.local/share/fonts/crimson-desktop" ]] && rm -rf -- "$path" && ok "removed ${path/#$HOME/~}" ;;
        esac
    done <"$LOG"
fi
systemctl --user daemon-reload
have fc-cache && fc-cache -f >/dev/null 2>&1
PKGS=$(awk '$1=="pkg"{print $2}' "$LOG" 2>/dev/null | xargs)
[ -n "$PKGS" ] && warn "packages installed by install.sh (kept): $PKGS — remove with: sudo dnf remove $PKGS"
echo "  config, cache and backups are kept: ${CONF_DIR/#$HOME/~}, ~/.cache/crimson-desktop, $BACKUP_ROOT"
