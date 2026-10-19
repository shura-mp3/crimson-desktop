#!/usr/bin/env bash
# install.sh [--yes] [--no-autostart] — install Crimson Terminal OS for the current user.
#   * user-level only: no sudo, no system packages, no `sudo pip` — Python deps go into terminal-os/.venv
#   * links the `crimson` command into ~/.local/bin (or `crimson-os` if another `crimson` already exists)
#   * installs the Crimson Konsole colour scheme + profiles (existing files are never overwritten)
#   * asks before turning on Konsole auto-start (reversible: crimson-autostart off)
. "$(dirname "${BASH_SOURCE[0]}")/tos-lib.sh" "$@"

NO_AUTO=0
for a in "$@"; do [ "$a" = --no-autostart ] && NO_AUTO=1; done

hdr "1/5 python"
PYBIN="${CRIMSON_TOS_BASE_PYTHON:-python3}"
have "$PYBIN" || die "python3 not found. On Nobara/Fedora install it with:  sudo dnf install python3   (then re-run this)"
"$PYBIN" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10+ needed (found $("$PYBIN" -V 2>&1))"
"$PYBIN" -c 'import venv, ensurepip' 2>/dev/null || die "python venv support missing. Install it with:  sudo dnf install python3   (Debian/Ubuntu: sudo apt install python3-venv)"
ok "$("$PYBIN" -V 2>&1)"

hdr "2/5 virtual environment"
if [ ! -x "$VENV/bin/python" ]; then
    "$PYBIN" -m venv "$VENV" || die "couldn't create $VENV"
    ok "created ${VENV/#$HOME/~}"
else
    ok "reusing ${VENV/#$HOME/~}"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip >/dev/null 2>&1 || true
if "$VENV/bin/python" -m pip install --disable-pip-version-check -q -r "$TOS/requirements.txt"; then
    ok "textual, rich, psutil, pillow installed (inside the venv only)"
else
    "$VENV/bin/python" -c 'import textual, rich, psutil' 2>/dev/null ||
        die "pip couldn't install the requirements (no network?). Re-run when online."
    warn "pip failed (offline?) — keeping the packages already in the venv"
fi

hdr "3/5 commands"
NAME="$(launcher_name)"
mkdir -p "$BIN_DIR"
if [ "$NAME" != crimson ]; then
    warn "another 'crimson' command already exists ($(command -v crimson)) — leaving it alone, installing as 'crimson-os'"
fi
if [ -e "$BIN_DIR/$NAME" ] && [ ! -L "$BIN_DIR/$NAME" ]; then
    die "$BIN_DIR/$NAME exists and isn't ours — not touching it"
fi
ln -sfn "$TOS/bin/crimson" "$BIN_DIR/$NAME" && ok "$NAME → ${TOS/#$HOME/~}/bin/crimson"
install_wrappers
mkdir -p "$TOS_STATE" && echo "$NAME" > "$TOS_STATE/terminal-os.command"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not on your PATH yet — log out and back in (Fedora/Nobara add it automatically once it exists)" ;;
esac

hdr "4/5 Konsole theme"
if confirm "Install the Crimson Konsole colour scheme and profiles? (your existing profiles are untouched)" y; then
    fa=(); [ "$FORCE" = 1 ] && fa=(--force)
    bash "$TOS/scripts/konsole-theme.sh" apply --yes "${fa[@]+"${fa[@]}"}"
else
    warn "skipped — later: bash ${TOS/#$HOME/~}/scripts/konsole-theme.sh apply"
fi

hdr "5/5 auto-start in Konsole"
if [ "$NO_AUTO" = 1 ]; then
    warn "skipped (--no-autostart) — later: crimson-autostart on"
elif [ ! -f "$KONSOLE_DIR/Crimson OS.profile" ]; then
    warn "skipped — the Crimson OS Konsole profile isn't installed"
elif confirm "Open Crimson OS automatically in every new Konsole window? (quit it = your normal shell; undo: crimson-autostart off)" y; then
    sh "$TOS/bin/crimson-autostart" on
else
    warn "skipped — later: crimson-autostart on"
fi

hdr "check"
"$TOS/bin/crimson" --doctor || warn "doctor reported problems (see above)"
say "installed. Start it with:  $NAME     ·     help: $NAME --help"
