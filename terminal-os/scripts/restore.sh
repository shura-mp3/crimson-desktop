#!/usr/bin/env bash
# restore.sh [BACKUP_DIR | --list] [--yes] — put files back exactly as a Crimson Terminal OS backup recorded them.
#   Default: the newest backup. Files that existed are copied back; files that didn't exist are removed.
#   Running it twice gives the same result (idempotent). A safety backup of the current state is made first.
. "$(dirname "${BASH_SOURCE[0]}")/tos-lib.sh" "$@"

if [ "${1:-}" = --list ]; then
    ls -1 "$TOS_BACKUPS" 2>/dev/null || echo "(no backups in $TOS_BACKUPS)"
    exit 0
fi
SRC="${1:-$(find "$TOS_BACKUPS" -mindepth 1 -maxdepth 1 -type d ! -name '*-pre-restore*' 2>/dev/null | sort | tail -1)}"
# crimson-autostart's own backups are plain: konsolerc + manifest.tsv (stored name 'konsolerc')
[ -n "$SRC" ] && [ -f "$SRC/manifest.tsv" ] || die "no backup found (looked in $TOS_BACKUPS). List: restore.sh --list"

hdr "restore ${SRC/#$HOME/~}"
cut -f1,2 "$SRC/manifest.tsv" | sed 's/^/  /'
confirm "Restore these files to the state recorded in this backup?" n || die "cancelled — nothing changed"

mapfile -t paths < <(cut -f1 "$SRC/manifest.tsv")
new_backup pre-restore "${paths[@]}"
while IFS=$'\t' read -r path state stored; do
    case "$state" in
        existed)
            src="$SRC/files/$stored"; [ -f "$src" ] || src="$SRC/$stored"
            [ -f "$src" ] || { err "missing $stored in backup — skipped $path"; continue; }
            mkdir -p "$(dirname "$path")" && cp -p "$src" "$path" && ok "restored $path" ;;
        absent)
            if [ -e "$path" ]; then rm -f "$path" && ok "removed $path (didn't exist before)"; else ok "absent $path"; fi
            forget "$path" ;;
    esac
done < "$SRC/manifest.tsv"
say "restored. Close all Konsole windows so it re-reads its settings."
