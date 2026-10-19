# shellcheck shell=bash
# shellcheck disable=SC2034  # variables are used by the scripts that source this file
# Shared helpers for the Crimson Terminal OS scripts. Source, don't execute.
# Builds on the Crimson Desktop helpers (say/ok/warn/err/die/hdr/ask/have).

TOS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../../scripts/lib.sh
. "$TOS/../scripts/lib.sh"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
TOS_STATE="${XDG_STATE_HOME:-$HOME/.local/state}/crimson-desktop"
KONSOLE_DIR="$DATA_HOME/konsole"
KONSOLERC="$CONFIG_HOME/konsolerc"
BIN_DIR="$HOME/.local/bin"
VENV="$TOS/.venv"
TOS_BACKUPS="$TOS_STATE/backups/terminal-os"
INSTALLED="$TOS_STATE/terminal-os.installed"   # "<sha256>  <path>" of every file we wrote
FLAG="$CONFIG_HOME/crimson-desktop/terminal-os.autostart-disabled"

YES=0
FORCE=0
ARGS=()
for a in "$@"; do
    case "$a" in
        --yes|-y) YES=1 ;;
        --force) FORCE=1 ;;
        *) ARGS+=("$a") ;;
    esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

# confirm "question" [default] — --yes answers yes without prompting
confirm() {
    [ "$YES" = 1 ] && return 0
    ask "$@"
}

sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# The name `crimson` unless something else already owns it on PATH, then `crimson-os`.
launcher_name() {
    local p
    p="$(command -v crimson 2>/dev/null || true)"
    if [ -z "$p" ] || [ "$(readlink -f "$p")" = "$TOS/bin/crimson" ]; then echo crimson; else echo crimson-os; fi
}

recorded_sha() { [ -f "$INSTALLED" ] && awk -v p="$1" '{ s = $1; $1 = ""; sub(/^ +/, ""); if ($0 == p) h = s } END { print h }' "$INSTALLED"; }
record() {  # record PATH  — remember what we wrote so later runs know the file is ours
    mkdir -p "$TOS_STATE"
    local tmp="$INSTALLED.tmp"
    { [ -f "$INSTALLED" ] && awk -v p="$1" '{ l = $0; $1 = ""; sub(/^ +/, ""); if ($0 != p) print l }' "$INSTALLED"; printf '%s  %s\n' "$(sha "$1")" "$1"; } > "$tmp"
    mv "$tmp" "$INSTALLED"
}
forget() {
    [ -f "$INSTALLED" ] || return 0
    awk -v p="$1" '{ l = $0; $1 = ""; sub(/^ +/, ""); if ($0 != p) print l }' "$INSTALLED" > "$INSTALLED.tmp" && mv "$INSTALLED.tmp" "$INSTALLED"
}
# is_ours PATH — true when PATH is byte-identical to what we last wrote there
is_ours() { local r; r="$(recorded_sha "$1")"; [ -n "$r" ] && [ "$r" = "$(sha "$1")" ]; }

# ---------------------------------------------------------------- backups (manifest.tsv)
# new_backup LABEL PATH... — copies each existing PATH, notes absent ones. Sets BACKUP_DIR.
new_backup() {
    local label="$1" p i=0; shift
    BACKUP_DIR="$TOS_BACKUPS/$(date +%Y%m%d-%H%M%S)-$label"
    while [ -e "$BACKUP_DIR" ]; do i=$((i + 1)); BACKUP_DIR="${BACKUP_DIR%.*}.$i"; done
    mkdir -p "$BACKUP_DIR/files" || die "can't create $BACKUP_DIR — nothing was changed"
    : > "$BACKUP_DIR/manifest.tsv"
    for p in "$@"; do
        i=$((i + 1))
        if [ -e "$p" ]; then
            cp -p "$p" "$BACKUP_DIR/files/$i" || die "backup of $p failed — nothing was changed"
            printf '%s\texisted\t%s\n' "$p" "$i" >> "$BACKUP_DIR/manifest.tsv"
        else
            printf '%s\tabsent\t-\n' "$p" >> "$BACKUP_DIR/manifest.tsv"
        fi
    done
    printf 'Crimson Terminal OS backup "%s" made %s\nRestore: bash %s/scripts/restore.sh %s\n' \
        "$label" "$(date '+%F %T')" "$TOS" "$BACKUP_DIR" > "$BACKUP_DIR/README"
    ok "backup: ${BACKUP_DIR/#$HOME/~}"
}

# install_file SRC DEST — never clobbers a file we didn't write (unless --force, and then after a backup)
install_file() {
    local src="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    if [ -e "$dest" ]; then
        if cmp -s "$src" "$dest"; then record "$dest"; ok "up to date: ${dest/#$HOME/~}"; return 0; fi
        if ! is_ours "$dest" && [ "$FORCE" != 1 ]; then
            warn "kept your existing ${dest/#$HOME/~} (not written by Crimson, or edited since). Use --force to replace it (a backup is made first)."
            return 0
        fi
    fi
    cp "$src" "$dest" && record "$dest" && ok "installed ${dest/#$HOME/~}"
}

install_wrappers() {
    mkdir -p "$BIN_DIR"
    local f
    # copies, not links: they must keep working (and keep `crimson-autostart off` working) if the project moves
    for f in crimson-konsole crimson-autostart; do
        install_file "$TOS/bin/$f" "$BIN_DIR/$f" && chmod +x "$BIN_DIR/$f"
    done
}
