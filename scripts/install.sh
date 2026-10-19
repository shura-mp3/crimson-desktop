#!/usr/bin/env bash
# Crimson Desktop — installer (Nobara / Fedora, KDE Plasma on Wayland).
#
#  1. inspects the system (nothing is changed)
#  2. lists missing packages from the official Fedora/Nobara repos and asks before `sudo dnf install`
#  3. user-level install only: fonts, ~/.local/bin links, systemd --user units, default config
#
# It does NOT touch your theme — that is scripts/apply-theme.sh (which backs everything up first).
# No third-party repositories, no COPR, no curl|bash.
set -u
. "$(dirname "$0")/lib.sh"

INSTALL_LOG="$STATE_DIR/install-manifest.txt"
mkdir -p "$STATE_DIR" "$CONF_DIR"
record() { echo "$1" >>"$INSTALL_LOG"; }

hdr "1/5 system inspection"
. "${CRIMSON_OS_RELEASE:-/etc/os-release}" 2>/dev/null || true  # override only for tests
echo "  distribution : ${PRETTY_NAME:-unknown}"
case "${ID:-}:${ID_LIKE:-}" in
    nobara:*|fedora:*|*:*fedora*) ok "Fedora-family system" ;;
    *) warn "not Nobara/Fedora — package names below may not apply"; ask "continue anyway?" n || exit 1 ;;
esac
echo "  session      : ${XDG_SESSION_TYPE:-?} / ${XDG_CURRENT_DESKTOP:-?}"
[ "${XDG_SESSION_TYPE:-}" = wayland ] || warn "not a Wayland session (the dashboard still works, layer-shell won't)"
have plasmashell && echo "  plasma       : $(plasmashell --version 2>/dev/null)"
have kwin_wayland && echo "  kwin         : $(kwin_wayland --version 2>/dev/null | head -1)"
have kitty && echo "  kitty        : $(kitty --version 2>/dev/null)"
echo "  python       : $(command -v "$PY") $("$PY" -V 2>&1)"
if have spotify; then ok "spotify (native) found: $(command -v spotify)"
elif have flatpak && flatpak info com.spotify.Client >/dev/null 2>&1; then ok "spotify (flatpak) found — MPRIS works the same"
else warn "spotify not found in PATH (install it whenever you like; detection is automatic)"; fi
if have pactl; then echo "  audio server : $(pactl info 2>/dev/null | sed -n 's/^Server Name: //p')"; fi
have kscreen-doctor && { echo "  monitors     :"; "$PY" "$PROJECT/scripts/detect-monitors.py" | sed 's/^/    /'; }

hdr "2/5 packages"
# package -> why. All from the standard Fedora/Nobara repositories.
declare -A WANT=(
    [python3-pyside6]="Qt 6 / QML for the dashboard"
    [python3-jeepney]="D-Bus (Spotify MPRIS)"
    [python3-pillow]="wallpaper analysis"
    [layer-shell-qt]="layer-shell surfaces under KWin (usually already installed with Plasma)"
    [cava]="real audio spectrum (PipeWire)"
    [pipewire-utils]="pw-dump (optional Spotify-only capture)"
    [kitty]="terminal"
    [fastfetch]="system info (crimsonfetch)"
    [playerctl]="MPRIS debugging tool (optional)"
    [jetbrains-mono-fonts-all]="terminal / UI mono font"
    [rsms-inter-fonts]="UI font (optional)"
    [papirus-icon-theme]="dark icon theme (optional)"
    [libnotify]="notify-send for profile switching notices"
)
MISSING=()
for pkg in "${!WANT[@]}"; do
    if rpm -q "$pkg" >/dev/null 2>&1; then ok "$pkg"
    else MISSING+=("$pkg"); fi
done
INSTALLABLE=()
if [ ${#MISSING[@]} -gt 0 ]; then
    say "checking repository availability for: ${MISSING[*]}"
    for pkg in "${MISSING[@]}"; do
        if dnf -q info "$pkg" >/dev/null 2>&1; then INSTALLABLE+=("$pkg"); warn "$pkg missing — ${WANT[$pkg]}"
        else err "$pkg not available in your enabled repos — ${WANT[$pkg]}"; fi
    done
fi
if [ ${#INSTALLABLE[@]} -gt 0 ]; then
    echo
    echo "  proposed command (requires sudo):"
    echo "    ${c_p}sudo dnf install ${INSTALLABLE[*]}${c_0}"
    if ask "run it now?" n; then
        if sudo dnf install "${INSTALLABLE[@]}"; then
            for p in "${INSTALLABLE[@]}"; do record "pkg $p"; done
            ok "packages installed (rollback does not remove packages; see docs/ROLLBACK.md)"
        else
            warn "dnf failed — continuing; crimsonctl doctor will show what's missing"
        fi
    else
        warn "skipped — install later and re-run this script"
    fi
fi

# Python modules: prefer the distro's PySide6 (same Qt as Plasma => layer-shell works)
if ! "$PY" -c 'import PySide6.QtQuick, jeepney' 2>/dev/null; then
    warn "python3 can't import PySide6/jeepney"
    if ask "install them for your user with pip instead (PySide6 from PyPI; layer-shell mode will be unavailable)?" n; then
        "$PY" -m pip install --user PySide6-Essentials jeepney && record "pip PySide6-Essentials jeepney"
    fi
fi
echo "CRIMSON_PYTHON=$(command -v "$PY")" >"$CONF_DIR/env"

hdr "3/5 fonts"
FONT_DIR="$HOME/.local/share/fonts/crimson-desktop"
mkdir -p "$FONT_DIR"
cp -f "$PROJECT"/fonts/*.ttf "$FONT_DIR/"
record "dir $FONT_DIR"
have fc-cache && fc-cache -f "$FONT_DIR" >/dev/null 2>&1
ok "pixel fonts (Jersey 10/15, VT323, Silkscreen, Pixelify Sans, Space Mono — SIL OFL) → ${FONT_DIR/#$HOME/~}"

hdr "4/5 commands & config"
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
for f in crimsonctl crimson-lyrics crimson-core crimson-dashboard crimson-cava crimsonfetch; do
    ln -sf "$PROJECT/bin/$f" "$BIN/$f" && record "link $BIN/$f"
done
case ":$PATH:" in *":$BIN:"*) ok "commands linked into ~/.local/bin" ;;
    *) warn "~/.local/bin is not on your PATH — add it to your shell profile" ;; esac
if [ ! -f "$CONF_DIR/config.toml" ]; then
    cp "$PROJECT/config/config.toml" "$CONF_DIR/config.toml" && ok "config → ${CONF_DIR/#$HOME/~}/config.toml"
else
    ok "keeping existing ${CONF_DIR/#$HOME/~}/config.toml"
fi
mkdir -p "$CONF_DIR/lyrics"

hdr "5/5 systemd user services"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
for u in crimson-core.service crimson-dashboard.service; do
    sed "s|@PROJECT@|$PROJECT|g" "$PROJECT/systemd/$u" >"$UNIT_DIR/$u" && record "unit $UNIT_DIR/$u"
done
systemctl --user daemon-reload
systemctl --user enable crimson-core.service >/dev/null 2>&1 && ok "crimson-core enabled (starts with your Plasma session)"
if ask "enable and start the music dashboard now?" y; then
    systemctl --user enable --now crimson-core.service crimson-dashboard.service && ok "dashboard running"
else
    systemctl --user start crimson-core.service
fi
sort -u -o "$INSTALL_LOG" "$INSTALL_LOG"

hdr "done"
echo "  next steps:"
echo "    ${c_p}crimsonctl doctor${c_0}                 verify everything"
echo "    ${c_p}$PROJECT/scripts/apply-theme.sh${c_0}   apply the full desktop theme (backs up first)"
echo "    ${c_p}crimson-lyrics${c_0}                    lyrics in the terminal"
