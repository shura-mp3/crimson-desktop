#!/usr/bin/env bash
# konsole-theme.sh apply|remove|status [--yes] [--force]
#   apply   install the Crimson colour scheme + two profiles into ~/.local/share/konsole:
#             "Crimson"     plain shell, Crimson colours (pick it any time: Konsole ▸ New Tab ▸ Crimson)
#             "Crimson OS"  opens Crimson Terminal OS first (used by crimson-autostart)
#           Existing files are never overwritten unless Crimson wrote them (or --force, after a backup).
#           Konsole's default profile is NOT changed here — that's `crimson-autostart on`.
#   remove  turn auto-start off and delete the files above (only the ones still unmodified)
. "$(dirname "${BASH_SOURCE[0]}")/tos-lib.sh" "$@"

SCHEME="$KONSOLE_DIR/Crimson.colorscheme"
PLAIN="$KONSOLE_DIR/Crimson.profile"
TOSP="$KONSOLE_DIR/Crimson OS.profile"

apply() {
    hdr "Crimson Konsole theme"
    have konsole || warn "konsole isn't installed — files are installed anyway and apply once it is"
    new_backup konsole-theme "$SCHEME" "$PLAIN" "$TOSP"
    install_wrappers
    local tmp
    tmp="$(mktemp -d)"
    cp "$TOS/konsole/Crimson.profile.in" "$tmp/Crimson.profile"
    sed "s|@WRAPPER@|$BIN_DIR/crimson-konsole|" "$TOS/konsole/Crimson OS.profile.in" > "$tmp/Crimson OS.profile"
    install_file "$TOS/konsole/Crimson.colorscheme" "$SCHEME"
    install_file "$tmp/Crimson.profile" "$PLAIN"
    install_file "$tmp/Crimson OS.profile" "$TOSP"
    rm -rf "$tmp"
    say "done. In Konsole: Settings ▸ Manage Profiles shows 'Crimson' and 'Crimson OS'."
}

remove() {
    hdr "remove Crimson Konsole theme"
    if grep -qx 'DefaultProfile=Crimson OS.profile' "$KONSOLERC" 2>/dev/null; then
        sh "$TOS/bin/crimson-autostart" off || die "couldn't turn auto-start off — nothing removed"
    fi
    new_backup konsole-theme-remove "$SCHEME" "$PLAIN" "$TOSP"
    local f
    for f in "$SCHEME" "$PLAIN" "$TOSP"; do
        [ -e "$f" ] || continue
        if is_ours "$f" || [ "$FORCE" = 1 ]; then rm -f "$f" && forget "$f" && ok "removed ${f/#$HOME/~}"
        else warn "kept ${f/#$HOME/~} (edited since install; remove by hand or use --force)"; fi
    done
}

status() {
    local f
    for f in "$SCHEME" "$PLAIN" "$TOSP"; do
        if [ -e "$f" ]; then printf '  %-55s %s\n' "${f/#$HOME/~}" "$(is_ours "$f" && echo "installed" || echo "present (modified / not ours)")"
        else printf '  %-55s %s\n' "${f/#$HOME/~}" "missing"; fi
    done
}

case "${1:-status}" in
    apply) apply ;;
    remove|restore) remove ;;
    status) status ;;
    *) die "usage: konsole-theme.sh apply|remove|status [--yes] [--force]" ;;
esac
