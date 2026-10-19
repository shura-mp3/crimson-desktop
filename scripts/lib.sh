# shellcheck shell=bash
# Shared helpers for Crimson Desktop scripts. Source, don't execute.

set -o pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/crimson-desktop"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/crimson-desktop"
BACKUP_ROOT="$PROJECT/backups"
PY="${CRIMSON_PYTHON:-python3}"
[ -f "$CONF_DIR/env" ] && . "$CONF_DIR/env" && PY="${CRIMSON_PYTHON:-python3}"

c_p=$'\e[38;2;242;183;197m'; c_d=$'\e[38;2;213;139;159m'; c_m=$'\e[38;2;168;139;152m'
c_r=$'\e[38;2;224;108;132m'; c_g=$'\e[38;2;150;190;140m'; c_0=$'\e[0m'; c_b=$'\e[1m'
[ -t 1 ] || { c_p=; c_d=; c_m=; c_r=; c_g=; c_0=; c_b=; }

say()  { printf '%s◢◤%s %s\n' "$c_d" "$c_0" "$*"; }
ok()   { printf '  %s✔%s %s\n' "$c_g" "$c_0" "$*"; }
warn() { printf '  %s!%s %s\n' "$c_d" "$c_0" "$*" >&2; }
err()  { printf '  %s✘%s %s\n' "$c_r" "$c_0" "$*" >&2; }
die()  { err "$*"; exit 1; }
hdr()  { printf '\n%s%s── %s %s%s\n' "$c_b" "$c_p" "$*" "$(printf '─%.0s' $(seq 1 $((60 - ${#1}))))" "$c_0"; }

# ask "question" [default y|n]  -> returns 0 for yes. CRIMSON_YES=1 answers the default... never for sudo.
ask() {
    local q="$1" def="${2:-n}" ans hint="[y/N]"
    [ "$def" = y ] && hint="[Y/n]"
    if [ ! -t 0 ]; then [ "$def" = y ]; return; fi
    read -r -p "  ${c_p}?${c_0} $q $hint " ans
    ans="${ans:-$def}"
    [[ "$ans" =~ ^[Yy] ]]
}

have() { command -v "$1" >/dev/null 2>&1; }

KWRITE="$(command -v kwriteconfig6 || command -v kwriteconfig5 || true)"
KREAD="$(command -v kreadconfig6 || command -v kreadconfig5 || true)"

# kw FILE "Group[/Sub...]" KEY VALUE    (groups separated by /)
kw() {
    local file="$1" groups="$2" key="$3" val="$4" args=()
    [ -n "$KWRITE" ] || { warn "kwriteconfig6 missing; skipped $file $groups $key"; return 1; }
    IFS='/' read -r -a gs <<<"$groups"
    for g in "${gs[@]}"; do args+=(--group "$g"); done
    "$KWRITE" --file "$file" "${args[@]}" --key "$key" "$val" && log_action "kwrite $file [$groups] $key=$val"
}
kr() {
    local file="$1" groups="$2" key="$3" def="${4:-}" args=()
    [ -n "$KREAD" ] || { echo "$def"; return; }
    IFS='/' read -r -a gs <<<"$groups"
    for g in "${gs[@]}"; do args+=(--group "$g"); done
    "$KREAD" --file "$file" "${args[@]}" --key "$key" --default "$def"
}

# qdbus_call SERVICE PATH INTERFACE.METHOD [ARGS...]   (qdbus6 / qdbus-qt6 / qdbus, else gdbus)
qdbus_call() {
    local q svc="$1" obj="$2" meth="$3"; shift 3
    for q in qdbus6 qdbus-qt6 qdbus; do
        if have "$q"; then "$q" "$svc" "$obj" "$meth" "$@"; return; fi
    done
    gdbus call --session --dest "$svc" --object-path "$obj" --method "$meth" "$@"
}

plasma_eval() {  # run a Plasma desktop scripting snippet
    qdbus_call org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$1"
}

kwin_reconfigure() {
    qdbus_call org.kde.KWin /KWin org.kde.KWin.reconfigure >/dev/null 2>&1 || true
}

# ------------------------------------------------------------------ backups / manifest
CURRENT_BACKUP=""
log_action() { [ -n "$CURRENT_BACKUP" ] && printf '%s  %s\n' "$(date '+%F %T')" "$*" >>"$CURRENT_BACKUP/actions.log"; return 0; }

# Files (relative to $HOME) the theme may touch. Directories are archived whole.
THEME_PATHS=(
    .config/kdeglobals .config/kwinrc .config/kwinrulesrc .config/breezerc .config/plasmarc
    .config/plasma-org.kde.plasma.desktop-appletsrc .config/plasmashellrc .config/kscreenlockerrc
    .config/kcminputrc .config/kglobalshortcutsrc .config/ksplashrc
    .config/kitty .config/cava/crimson .config/fastfetch/crimson.jsonc
    .local/share/color-schemes/CrimsonNight.colors
    .local/share/applications/crimson-dashboard-toggle.desktop
    .local/share/applications/crimson-lyrics.desktop
    .local/share/applications/crimson-profile-cycle.desktop
    .local/share/applications/crimson-offset-plus.desktop
    .local/share/applications/crimson-offset-minus.desktop
)

make_backup() {  # make_backup <label>  -> sets CURRENT_BACKUP
    local ts label="${1:-theme}" existing=() absent=() p
    ts="$(date +%Y%m%d-%H%M%S)"
    CURRENT_BACKUP="$BACKUP_ROOT/$ts-$label"
    mkdir -p "$CURRENT_BACKUP"
    for p in "${THEME_PATHS[@]}"; do
        if [ -e "$HOME/$p" ]; then existing+=("$p"); else absent+=("$p"); fi
    done
    if [ ${#existing[@]} -gt 0 ]; then
        tar --xattrs --acls -cpzf "$CURRENT_BACKUP/files.tar.gz" -C "$HOME" "${existing[@]}" 2>/dev/null ||
            tar -cpzf "$CURRENT_BACKUP/files.tar.gz" -C "$HOME" "${existing[@]}" ||
            die "backup failed — nothing was changed"
    fi
    # previous Plasma look, so rollback can re-apply it properly (not just restore files)
    "$PY" - "$CURRENT_BACKUP/manifest.json" "$ts" "$label" \
        "$(kr kdeglobals General ColorScheme BreezeDark)" \
        "$(kr kdeglobals Icons Theme breeze-dark)" \
        "$(kr kcminputrc Mouse cursorTheme breeze_cursors)" \
        "$(kr plasmarc Theme name default)" \
        "$(kr kdeglobals General AccentColor '')" \
        "${#existing[@]}" "${existing[@]}" "${absent[@]}" <<'PYEOF'
import json, sys
out, ts, label, scheme, icons, cursor, plasma, accent, n = sys.argv[1:10]
rest = sys.argv[10:]
n = int(n)
json.dump({
    "created": ts, "label": label, "home": __import__("os").path.expanduser("~"),
    "previous": {"color_scheme": scheme, "icon_theme": icons, "cursor_theme": cursor,
                 "plasma_theme": plasma, "accent_color": accent},
    "existed": rest[:n], "absent": rest[n:],
    "note": "files.tar.gz holds the 'existed' paths; 'absent' paths did not exist and are removed on restore.",
}, open(out, "w"), indent=2)
PYEOF
    log_action "backup created ($label): ${#existing[@]} existing paths archived"
    ok "backup: ${CURRENT_BACKUP/#$HOME/~}"
}
