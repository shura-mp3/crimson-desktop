#!/usr/bin/env bash
# update.sh [--yes] — pull the latest Crimson Desktop (fast-forward only), refresh the venv,
# the wrapper commands and the Konsole files Crimson installed. Your settings are kept.
. "$(dirname "${BASH_SOURCE[0]}")/tos-lib.sh" "$@"

hdr "source"
if git -C "$PROJECT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [ -n "$(git -C "$PROJECT" status --porcelain --untracked-files=no)" ]; then
        warn "you have local changes in $PROJECT — skipping git pull (commit or stash them first)"
    elif confirm "git pull (fast-forward only) in ${PROJECT/#$HOME/~}?" y; then
        git -C "$PROJECT" pull --ff-only || warn "git pull failed — continuing with the current files"
    fi
else
    warn "not a git checkout — skipping pull"
fi

hdr "python packages"
[ -x "$VENV/bin/python" ] || die "no venv yet — run install.sh first"
"$VENV/bin/python" -m pip install --disable-pip-version-check -q --upgrade -r "$TOS/requirements.txt" \
    && ok "venv packages up to date" || warn "pip upgrade failed (offline?) — keeping current packages"

hdr "commands + Konsole files"
install_wrappers
if [ -e "$KONSOLE_DIR/Crimson OS.profile" ] || [ -e "$KONSOLE_DIR/Crimson.colorscheme" ]; then
    bash "$TOS/scripts/konsole-theme.sh" apply --yes
fi
"$TOS/bin/crimson" --version && ok "update complete"
