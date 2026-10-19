#!/usr/bin/env bash
# Crimson Desktop — apply the desktop theme (KDE Plasma, user-level only, no sudo).
#
# Always creates a timestamped backup first (backups/<ts>-theme/: files.tar.gz, manifest.json,
# actions.log). Undo with scripts/restore-theme.sh.
#
# usage: apply-theme.sh [--wallpaper-dir DIR] [--left FILE] [--right FILE]
#                       [--no-wallpaper] [--no-icons] [--no-fonts] [--no-kitty] [--no-decor]
#                       [--panel] [--yes]
set -u
. "$(dirname "$0")/lib.sh"

WALL_DIR="$HOME/Downloads/home/jan/Downloads/pack 1/"
LEFT_PICK="" RIGHT_PICK=""
DO_WALL=1 DO_ICONS=1 DO_FONTS=1 DO_KITTY=1 DO_DECOR=1 DO_PANEL=0 YES=0
while [ $# -gt 0 ]; do
    case "$1" in
        --wallpaper-dir) WALL_DIR="$2"; shift ;;
        --left) LEFT_PICK="$2"; shift ;;
        --right) RIGHT_PICK="$2"; shift ;;
        --no-wallpaper) DO_WALL=0 ;;
        --no-icons) DO_ICONS=0 ;;
        --no-fonts) DO_FONTS=0 ;;
        --no-kitty) DO_KITTY=0 ;;
        --no-decor) DO_DECOR=0 ;;
        --panel) DO_PANEL=1 ;;
        --yes|-y) YES=1 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) die "unknown option $1" ;;
    esac
    shift
done

hdr "preflight"
[ -n "$KWRITE" ] || die "kwriteconfig6 not found (part of KDE Frameworks) — is this KDE Plasma?"
have plasma-apply-colorscheme || die "plasma-apply-colorscheme not found — is this KDE Plasma?"
pgrep -x plasmashell >/dev/null || warn "plasmashell isn't running; wallpaper/panel steps will be skipped"
echo "  plasma: $(plasmashell --version 2>/dev/null || echo '?')"
echo "  will apply: colour scheme, accent, Plasma style, window decoration + crimson shadows, blur,"
echo "              $( [ $DO_WALL = 1 ] && echo 'wallpapers (both monitors) + lock screen, ')$( [ $DO_ICONS = 1 ] && echo 'icons, ')$( [ $DO_FONTS = 1 ] && echo 'fonts, ')$( [ $DO_KITTY = 1 ] && echo 'kitty, ')cava/fastfetch presets,"
echo "              KWin fallback rule for the dashboard, global shortcuts$( [ $DO_PANEL = 1 ] && echo ', panel widgets')"
[ $YES = 1 ] || ask "continue (a backup is made first)?" y || exit 0

hdr "backup"
make_backup theme
cp -f "$CURRENT_BACKUP/manifest.json" "$STATE_DIR/last-theme-backup.json" 2>/dev/null || { mkdir -p "$STATE_DIR"; cp -f "$CURRENT_BACKUP/manifest.json" "$STATE_DIR/last-theme-backup.json"; }
echo "$CURRENT_BACKUP" >"$STATE_DIR/last-theme-backup"
# the first backup since the last restore is the true pre-Crimson desktop: restore defaults to it
if [ ! -f "$STATE_DIR/original-theme-backup" ] || [ ! -d "$(cat "$STATE_DIR/original-theme-backup")" ]; then
    echo "$CURRENT_BACKUP" >"$STATE_DIR/original-theme-backup"
    ok "marked as your original desktop backup"
fi

hdr "monitors"
"$PY" "$PROJECT/scripts/detect-monitors.py" --write | sed 's/^/  /'
log_action "wrote $CONF_DIR/monitors.json"

# ---------------------------------------------------------------- wallpapers
if [ $DO_WALL = 1 ]; then
    hdr "wallpapers"
    LEFT_IMG="$PROJECT/wallpapers/crimson-fallback.jpg"; RIGHT_IMG="$LEFT_IMG"; LOCK_IMG="$LEFT_IMG"
    if [ -d "$WALL_DIR" ] && "$PY" -c 'import PIL' 2>/dev/null; then
        args=(--dir "$WALL_DIR")
        [ -n "$LEFT_PICK" ] && args+=(--left "$LEFT_PICK")
        [ -n "$RIGHT_PICK" ] && args+=(--right "$RIGHT_PICK")
        if "$PY" "$PROJECT/scripts/pick-wallpapers.py" "${args[@]}" | sed 's/^/  /'; then
            G="$PROJECT/wallpapers/generated"
            LEFT_IMG="$G/left.jpg"; RIGHT_IMG="$G/right.jpg"; LOCK_IMG="$G/lockscreen.jpg"
            log_action "generated wallpaper derivatives in $G (originals untouched)"
            ok "review the ranking: ${G/#$HOME/~}/candidates.jpg  (override with --left/--right FILE)"
        else
            warn "wallpaper picker failed — using the bundled crimson fallback"
        fi
    else
        [ -d "$WALL_DIR" ] || warn "wallpaper folder not found: $WALL_DIR"
        "$PY" -c 'import PIL' 2>/dev/null || warn "python3-pillow missing — can't analyse wallpapers"
        warn "using the bundled procedural crimson wallpaper"
    fi
    if pgrep -x plasmashell >/dev/null; then
        JS=$(cat <<EOF
var L = "file://$LEFT_IMG", R = "file://$RIGHT_IMG";
var ds = desktops().filter(function (d) { return d.screen >= 0; });
var gs = ds.map(function (d) { return screenGeometry(d.screen); });
var horiz = Math.max.apply(null, gs.map(function (g) { return g.x; })) !== Math.min.apply(null, gs.map(function (g) { return g.x; }));
var key = function (g) { return horiz ? g.x : g.y; };
var maxk = Math.max.apply(null, gs.map(key));
for (var i = 0; i < ds.length; i++) {
    var d = ds[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", (ds.length > 1 && key(gs[i]) === maxk) ? R : L);
    d.writeConfig("FillMode", 2);
}
print(ds.length + " desktop(s) updated");
EOF
)
        plasma_eval "$JS" >/dev/null && ok "wallpapers set (right = dashboard monitor, left = productivity)" &&
            log_action "plasma wallpapers: left=$LEFT_IMG right=$RIGHT_IMG"
    fi
    kw kscreenlockerrc Greeter WallpaperPlugin org.kde.image
    kw kscreenlockerrc "Greeter/Wallpaper/org.kde.image/General" Image "file://$LOCK_IMG"
    ok "lock screen wallpaper"
fi

# ---------------------------------------------------------------- colours
hdr "colours & plasma style"
mkdir -p "$HOME/.local/share/color-schemes"
cp -f "$PROJECT/themes/kde/CrimsonNight.colors" "$HOME/.local/share/color-schemes/" && log_action "installed CrimsonNight.colors"
plasma-apply-colorscheme --accent-color "#8D2445" CrimsonNight >/dev/null 2>&1 ||
    plasma-apply-colorscheme CrimsonNight >/dev/null && log_action "plasma-apply-colorscheme CrimsonNight (accent #8D2445)"
ok "colour scheme: Crimson Night (accent #8D2445)"
if have plasma-apply-desktoptheme; then
    # the default Breeze Plasma style follows the colour scheme (Breeze Dark has fixed colours)
    plasma-apply-desktoptheme default >/dev/null 2>&1 && log_action "plasma-apply-desktoptheme default" && ok "Plasma style: Breeze (follows Crimson Night)"
fi

# ---------------------------------------------------------------- icons & fonts
if [ $DO_ICONS = 1 ]; then
    if [ -d /usr/share/icons/Papirus-Dark ] || [ -d "$HOME/.local/share/icons/Papirus-Dark" ]; then
        if [ -x /usr/libexec/plasma-changeicons ]; then /usr/libexec/plasma-changeicons Papirus-Dark >/dev/null 2>&1
        else kw kdeglobals Icons Theme Papirus-Dark; fi
        log_action "icon theme Papirus-Dark"; ok "icons: Papirus-Dark"
    else
        warn "Papirus-Dark not installed — keeping your icon theme (dnf install papirus-icon-theme)"
    fi
fi
if [ $DO_FONTS = 1 ] && have fc-list; then
    UI="Noto Sans"; fc-list : family | grep -qx "Inter" && UI="Inter"
    MONO=""; fc-list : family | grep -q "JetBrains Mono" && MONO="JetBrains Mono"
    f() { echo "$1,$2,-1,5,${3:-400},0,0,0,0,0,0,0,0,0,0,1"; }
    kw kdeglobals General font "$(f "$UI" 10)"
    kw kdeglobals General menuFont "$(f "$UI" 10)"
    kw kdeglobals General toolBarFont "$(f "$UI" 9)"
    kw kdeglobals General smallestReadableFont "$(f "$UI" 8)"
    kw kdeglobals WM activeFont "$(f "$UI" 10 600)"
    [ -n "$MONO" ] && kw kdeglobals General fixed "$(f "$MONO" 10)"
    ok "fonts: $UI (UI)${MONO:+, $MONO (fixed)} — pixel fonts are used only for decorative text"
fi

# ---------------------------------------------------------------- window decoration / effects
if [ $DO_DECOR = 1 ]; then
    hdr "windows & effects"
    kw kwinrc org.kde.kdecoration2 library org.kde.breeze
    kw kwinrc org.kde.kdecoration2 theme Breeze
    kw kwinrc org.kde.kdecoration2 BorderSize Tiny
    kw kwinrc org.kde.kdecoration2 BorderSizeAuto false
    kw breezerc Common OutlineIntensity OutlineMedium
    kw breezerc Common ShadowColor "60,8,24"
    kw breezerc Common ShadowSize ShadowLarge
    kw breezerc Common ShadowStrength 200
    kw breezerc Windeco DrawBorderOnMaximizedWindows false
    kw breezerc Windeco DrawTitleBarSeparator true
    kw breezerc Windeco TitleAlignment AlignLeft
    kw kwinrc Plugins blurEnabled true
    kw kwinrc Effect-blur BlurStrength 9
    kw kwinrc Effect-blur NoiseStrength 3
    kw kwinrc Plugins translucencyEnabled true
    kw kwinrc Effect-translucency MoveResize 88
    kw kdeglobals KDE AnimationDurationFactor 0.7
    ok "Breeze decoration (tiny borders, crimson-tinted shadows), blur for kitty, snappier animations"
fi

# ---------------------------------------------------------------- KWin rule (dashboard window-mode fallback)
hdr "dashboard window rule"
RULE="8d244560-c71b-4a1e-9f2b-0b080dc7a110"
GEO=$("$PY" - "$CONF_DIR/monitors.json" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1]))
o = next((o for o in m.get("outputs", []) if o["name"] == m.get("right")), None)
print(f"{o['x']},{o['y']} {o['logical_width']},{o['logical_height']}" if o else "0,0 1920,1080")
PYEOF
)
POS="${GEO% *}"; SIZE="${GEO#* }"
kw kwinrulesrc "$RULE" Description "Crimson Dashboard (only used when layer-shell is unavailable)"
kw kwinrulesrc "$RULE" wmclass crimson-dashboard
kw kwinrulesrc "$RULE" wmclassmatch 1
kw kwinrulesrc "$RULE" wmclasscomplete false
for kv in "position=$POS" "size=$SIZE" below=true skiptaskbar=true skippager=true skipswitcher=true noborder=true acceptfocus=false; do
    k="${kv%%=*}"; v="${kv#*=}"
    kw kwinrulesrc "$RULE" "$k" "$v"
    kw kwinrulesrc "$RULE" "${k}rule" 2
done
kw kwinrulesrc "$RULE" fsplevel 4
kw kwinrulesrc "$RULE" fsplevelrule 2
RULES="$(kr kwinrulesrc General rules '')"
case ",$RULES," in *",$RULE,"*) ;; *) RULES="${RULES:+$RULES,}$RULE" ;; esac
kw kwinrulesrc General rules "$RULES"
kw kwinrulesrc General count "$(awk -F, '{print NF}' <<<"$RULES")"
kwin_reconfigure
ok "rule pins a fallback dashboard window to $POS ($SIZE), below others, unfocusable"

# ---------------------------------------------------------------- kitty / cava / fastfetch
if [ $DO_KITTY = 1 ]; then
    hdr "terminal"
    K="$HOME/.config/kitty"
    mkdir -p "$K"
    cp -f "$PROJECT/themes/kitty/crimson.conf" "$K/crimson.conf"
    [ -f "$K/crimson-profile.conf" ] || cp "$PROJECT/themes/kitty/crimson-profile.conf" "$K/crimson-profile.conf"
    if [ ! -f "$K/kitty.conf" ]; then
        printf '# kitty.conf — created by Crimson Desktop. Put personal settings above the include.\n\ninclude crimson.conf\n' >"$K/kitty.conf"
        log_action "created $K/kitty.conf"
    elif ! grep -qx 'include crimson.conf' "$K/kitty.conf"; then
        printf '\n# Crimson Desktop theme (remove this line to disable)\ninclude crimson.conf\n' >>"$K/kitty.conf"
        log_action "appended 'include crimson.conf' to $K/kitty.conf"
    fi
    pgrep -x kitty >/dev/null && pkill -USR1 -x kitty
    ok "kitty theme (your kitty.conf is kept; one include line added)"
fi
mkdir -p "$HOME/.config/cava" "$HOME/.config/fastfetch"
cp -f "$PROJECT/themes/cava/crimson" "$HOME/.config/cava/crimson"
cp -f "$PROJECT/themes/fastfetch/crimson.jsonc" "$HOME/.config/fastfetch/crimson.jsonc"
log_action "installed cava + fastfetch presets"
ok "crimson-cava / crimsonfetch presets (your default cava & fastfetch configs are untouched)"

# ---------------------------------------------------------------- shortcuts
hdr "global shortcuts"
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
for d in "$PROJECT"/applications/*.desktop; do
    sed "s|@PROJECT@|$PROJECT|g" "$d" >"$APPS/$(basename "$d")"
done
log_action "installed .desktop entries in $APPS"
declare -A SC=(
    [crimson-dashboard-toggle.desktop]="Meta+Alt+D"
    [crimson-lyrics.desktop]="Meta+Alt+L"
    [crimson-profile-cycle.desktop]="Meta+Alt+P"
    [crimson-offset-plus.desktop]="Meta+Alt+]"
    [crimson-offset-minus.desktop]="Meta+Alt+["
)
for d in "${!SC[@]}"; do kw kglobalshortcutsrc "services/$d" _launch "${SC[$d]}"; done
have update-desktop-database && update-desktop-database "$APPS" >/dev/null 2>&1
ok "Meta+Alt+D toggle dashboard · Meta+Alt+L kitty lyrics · Meta+Alt+P next profile · Meta+Alt+[ / ] lyric offset"
warn "shortcuts become active after your next login (check System Settings → Shortcuts for conflicts)"

# ---------------------------------------------------------------- optional panel widgets
if [ $DO_PANEL = 1 ] && pgrep -x plasmashell >/dev/null; then
    hdr "panel"
    JS=$(cat <<'EOF'
var ps = panels(), done = 0;
var minx = Math.min.apply(null, ps.map(function (p) { return screenGeometry(p.screen).x; }));
ps.forEach(function (p) {
    try { p.floating = true; } catch (e) {}
    if (screenGeometry(p.screen).x !== minx) return;
    ["org.kde.plasma.mediacontroller", "org.kde.plasma.systemmonitor.cpu", "org.kde.plasma.systemmonitor.memory"].forEach(function (w) {
        if (p.widgets(w).length === 0) { try { p.addWidget(w); done++; } catch (e) {} }
    });
});
print(done + " widget(s) added");
EOF
)
    plasma_eval "$JS" && log_action "panel: floating + media/cpu/memory widgets on the left monitor panel"
fi

# ---------------------------------------------------------------- profile
hdr "profile"
"$PROJECT/bin/crimsonctl" profile crimson
log_action "profile crimson"

hdr "done"
echo "  backup + log : ${CURRENT_BACKUP/#$HOME/~}"
echo "  undo         : ${c_p}$PROJECT/scripts/restore-theme.sh${c_0}"
echo "  notes        : some apps pick up fonts/colours after restart; shortcuts after re-login."
