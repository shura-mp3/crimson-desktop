#!/usr/bin/env bash
# Crimson Desktop — restore the desktop exactly as it was before apply-theme.sh.
#
# usage: restore-theme.sh [BACKUP_DIR | --latest | --list] [--keep-dashboard] [--yes]
#   default: your ORIGINAL desktop (the first backup taken since the last restore),
#   --latest: the most recent backup (undo only the last apply-theme run)
#
# Idempotent: running it twice restores the same files again. It only touches the paths listed
# in the backup's manifest — never anything else. Packages installed by install.sh are NOT
# removed (see docs/ROLLBACK.md); use scripts/uninstall.sh to remove the dashboard itself.
set -u
. "$(dirname "$0")/lib.sh"

TARGET="" KEEP_DASH=0 YES=0 LATEST=0
while [ $# -gt 0 ]; do
    case "$1" in
        --list) ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | sed "s|$BACKUP_ROOT/||; s|/$||"; exit 0 ;;
        --keep-dashboard) KEEP_DASH=1 ;;
        --latest) LATEST=1 ;;
        --yes|-y) YES=1 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) TARGET="$1" ;;
    esac
    shift
done
if [ -z "$TARGET" ] && [ $LATEST = 0 ] && [ -f "$STATE_DIR/original-theme-backup" ]; then
    TARGET="$(cat "$STATE_DIR/original-theme-backup")"
    [ -d "$TARGET" ] || TARGET=""
fi
[ -z "$TARGET" ] && TARGET="$(ls -1d "$BACKUP_ROOT"/*-theme 2>/dev/null | sort | tail -1)"
[ -n "$TARGET" ] || die "no backups found in $BACKUP_ROOT"
[ -d "$TARGET" ] || TARGET="$BACKUP_ROOT/$TARGET"
[ -f "$TARGET/manifest.json" ] || die "not a Crimson backup: $TARGET"

hdr "restore"
"$PY" - "$TARGET/manifest.json" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"  backup   : {m['created']} ({m['label']})")
p = m["previous"]
print(f"  previous : colours={p['color_scheme']}  icons={p['icon_theme']}  plasma style={p['plasma_theme']}")
print(f"  restores : {len(m['existed'])} paths;  removes {len(m['absent'])} paths that did not exist before (if present)")
PYEOF
[ $YES = 1 ] || ask "restore this backup now?" y || exit 0

read_manifest() { "$PY" -c 'import json,sys; m=json.load(open(sys.argv[1])); [print(x) for x in m[sys.argv[2]]]' "$TARGET/manifest.json" "$1"; }
prev() { "$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["previous"][sys.argv[2]])' "$TARGET/manifest.json" "$1"; }

# 1. dashboard
if [ $KEEP_DASH = 0 ]; then
    systemctl --user disable --now crimson-dashboard.service >/dev/null 2>&1 && ok "dashboard stopped & disabled (re-enable: crimsonctl profile crimson)"
fi

# 2. stop plasmashell so it cannot rewrite its config while we restore
PLASMA_WAS_RUNNING=0
if pgrep -x plasmashell >/dev/null; then
    PLASMA_WAS_RUNNING=1
    if systemctl --user cat plasma-plasmashell.service >/dev/null 2>&1; then systemctl --user stop plasma-plasmashell.service
    else (have kquitapp6 && kquitapp6 plasmashell) || pkill -TERM -x plasmashell; fi
    for _ in $(seq 1 30); do pgrep -x plasmashell >/dev/null || break; sleep 0.2; done
    ok "plasmashell stopped"
fi

# 3. remove paths that did not exist before (only those listed in the manifest)
while IFS= read -r p; do
    [ -n "$p" ] || continue
    if [ -e "$HOME/$p" ]; then rm -rf -- "${HOME:?}/$p" && ok "removed ~/$p"; fi
done < <(read_manifest absent)

# 4. restore files (permissions and timestamps preserved)
if [ -f "$TARGET/files.tar.gz" ]; then
    # kitty dir: replace wholesale so files we added inside it disappear too
    while IFS= read -r p; do
        [ -d "$HOME/$p" ] && rm -rf -- "${HOME:?}/$p"
    done < <(read_manifest existed | grep -E '^\.config/kitty$')
    tar --xattrs --acls -xpzf "$TARGET/files.tar.gz" -C "$HOME" 2>/dev/null || tar -xpzf "$TARGET/files.tar.gz" -C "$HOME" ||
        die "extracting the backup failed"
    ok "restored $(read_manifest existed | wc -l) paths"
fi

# 5. re-apply the previous look so running apps update (file restore alone won't repaint them)
SCHEME="$(prev color_scheme)"
plasma-apply-colorscheme "$SCHEME" >/dev/null 2>&1 && ok "colour scheme: $SCHEME"
ACC="$(prev accent_color)"
# accent was unset before: drop the one apply-theme set (only touch the file if it's there)
[ -z "$ACC" ] && [ -n "$(kr kdeglobals General AccentColor '')" ] && have kwriteconfig6 &&
    kwriteconfig6 --file kdeglobals --group General --key AccentColor --delete
have plasma-apply-desktoptheme && plasma-apply-desktoptheme "$(prev plasma_theme)" >/dev/null 2>&1 && ok "Plasma style: $(prev plasma_theme)"
[ -x /usr/libexec/plasma-changeicons ] && /usr/libexec/plasma-changeicons "$(prev icon_theme)" >/dev/null 2>&1 && ok "icons: $(prev icon_theme)"
have plasma-apply-cursortheme && plasma-apply-cursortheme "$(prev cursor_theme)" >/dev/null 2>&1

# 6. bring the desktop back
if [ $PLASMA_WAS_RUNNING = 1 ]; then
    if systemctl --user cat plasma-plasmashell.service >/dev/null 2>&1; then systemctl --user start plasma-plasmashell.service
    else (have kstart && kstart plasmashell) || (setsid plasmashell >/dev/null 2>&1 &); fi
    ok "plasmashell restarted"
fi
kwin_reconfigure
pgrep -x kitty >/dev/null && pkill -USR1 -x kitty
# revert profile side effects (animation speed / blur saved by crimsonctl)
rm -f "$STATE_DIR/profile-saved.json"
# back to the original: the next apply-theme run takes a fresh "original" backup
[ "$TARGET" = "$(cat "$STATE_DIR/original-theme-backup" 2>/dev/null)" ] && rm -f "$STATE_DIR/original-theme-backup"

hdr "done"
echo "  restored from ${TARGET/#$HOME/~}"
echo "  not undone automatically: installed packages, the dashboard install itself (scripts/uninstall.sh)."
