#!/usr/bin/env bash
# autostart.sh on|off|status — thin wrapper around bin/crimson-autostart (pure sh; works without Python).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
args=()
for a in "$@"; do [ "$a" = --yes ] || [ "$a" = -y ] || args+=("$a"); done
exec sh "$HERE/../bin/crimson-autostart" "${args[@]+"${args[@]}"}"
