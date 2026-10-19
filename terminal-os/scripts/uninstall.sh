#!/usr/bin/env bash
# uninstall.sh [--yes] [--purge] — remove Crimson Terminal OS. Turns auto-start off first and restores
# Konsole's previous default profile. Keeps settings + backups unless --purge.
. "$(dirname "${BASH_SOURCE[0]}")/tos-lib.sh" "$@"
PURGE=0
for a in "$@"; do [ "$a" = --purge ] && PURGE=1; done

hdr "uninstall Crimson Terminal OS"
confirm "Remove Crimson Terminal OS (commands, Konsole profiles it installed, venv)?" n || die "cancelled"
if grep -qx 'DefaultProfile=Crimson OS.profile' "$KONSOLERC" 2>/dev/null; then
    sh "$TOS/bin/crimson-autostart" off || die "couldn't turn auto-start off — stopping before removing anything"
fi
bash "$TOS/scripts/konsole-theme.sh" remove --yes

for n in crimson crimson-os; do
    l="$BIN_DIR/$n"
    if [ -L "$l" ] && [ "$(readlink -f "$l")" = "$TOS/bin/crimson" ]; then rm -f "$l" && ok "removed $l"; fi
done
for n in crimson-konsole crimson-autostart; do
    f="$BIN_DIR/$n"
    [ -e "$f" ] || continue
    if is_ours "$f" || cmp -s "$f" "$TOS/bin/$n"; then rm -f "$f" && forget "$f" && ok "removed $f"; else warn "kept $f (modified)"; fi
done
rm -rf "$VENV" && ok "removed venv"
rm -f "$FLAG" "$TOS_STATE/terminal-os.failures" "$TOS_STATE/terminal-os.prev-default-profile" "$TOS_STATE/terminal-os.command"
if [ "$PURGE" = 1 ]; then
    rm -f "$CONFIG_HOME/crimson-desktop/terminal-os.toml" "$CONFIG_HOME/crimson-desktop/terminal-os-bookmarks.json" \
          "$CONFIG_HOME/crimson-desktop/terminal-os-commands.toml" "$TOS_STATE/terminal-os.log"* "$INSTALLED"
    ok "settings, bookmarks, custom commands and log removed (backups kept in ${TOS_BACKUPS/#$HOME/~})"
else
    say "kept your settings in ${CONFIG_HOME/#$HOME/~}/crimson-desktop/terminal-os*  (use --purge to delete)"
fi
say "Crimson Terminal OS removed. Crimson Desktop itself is untouched."
