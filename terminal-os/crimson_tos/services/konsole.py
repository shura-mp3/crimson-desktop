"""Read-only Konsole inspection + calls into the shell scripts that make the (reversible) changes.

The scripts (terminal-os/scripts/*.sh) are the single implementation of every Konsole change so
recovery works even if Python is broken; this module only reports state and invokes them.
"""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
from pathlib import Path

from crimson import paths

TOS_DIR = paths.PROJECT_DIR / "terminal-os"
SCRIPTS = TOS_DIR / "scripts"
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
KONSOLERC = CONFIG_HOME / "konsolerc"
PROFILE_DIR = DATA_HOME / "konsole"
CRIMSON_PROFILE = "Crimson OS.profile"
DISABLED_FLAG = paths.CONFIG_DIR / "terminal-os.autostart-disabled"


def _ini(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
    except configparser.Error:
        pass
    return cp


def status() -> dict:
    version = ""
    if shutil.which("konsole"):
        try:
            out = subprocess.run(["konsole", "--version"], capture_output=True, text=True, timeout=5).stdout
            version = out.strip().splitlines()[-1] if out.strip() else ""
        except (OSError, subprocess.TimeoutExpired):
            pass
    rc = _ini(KONSOLERC)
    default = rc.get("Desktop Entry", "DefaultProfile", fallback="") if rc.has_section("Desktop Entry") else ""
    profiles = sorted(p.name for p in PROFILE_DIR.glob("*.profile")) if PROFILE_DIR.is_dir() else []
    schemes = sorted(p.stem for p in PROFILE_DIR.glob("*.colorscheme")) if PROFILE_DIR.is_dir() else []
    return {
        "konsole": version or ("not installed" if not shutil.which("konsole") else "unknown version"),
        "default_profile": default or "(built-in default)",
        "profiles": profiles,
        "schemes": schemes,
        "crimson_profile": CRIMSON_PROFILE in profiles,
        "crimson_scheme": "Crimson" in schemes,
        "autostart": default == CRIMSON_PROFILE and not DISABLED_FLAG.exists(),
        "autostart_flag_disabled": DISABLED_FLAG.exists(),
        "shell": os.environ.get("SHELL", "?"),
        "in_konsole": bool(os.environ.get("KONSOLE_VERSION") or os.environ.get("KONSOLE_DBUS_SESSION")),
    }


def run_script(name: str, *args: str) -> tuple[int, str]:
    script = SCRIPTS / name
    try:
        r = subprocess.run(["bash", str(script), *args, "--yes"], capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
