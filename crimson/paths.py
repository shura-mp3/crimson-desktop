"""XDG-aware filesystem locations used by every Crimson component."""

import os
from pathlib import Path

APP = "crimson-desktop"


def _xdg(env: str, fallback: str) -> Path:
    return Path(os.environ.get(env) or fallback).expanduser()


PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", "~/.config") / APP
CACHE_DIR = _xdg("XDG_CACHE_HOME", "~/.cache") / APP
STATE_DIR = _xdg("XDG_STATE_HOME", "~/.local/state") / APP
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{APP}-{os.getuid()}") / APP

CONFIG_FILE = CONFIG_DIR / "config.toml"
DEFAULT_CONFIG_FILE = PROJECT_DIR / "config" / "config.toml"
UI_STATE_FILE = STATE_DIR / "ui.json"
OFFSETS_FILE = STATE_DIR / "offsets.json"
WALLPAPER_STATE = CONFIG_DIR / "wallpapers.json"
MONITORS_FILE = CONFIG_DIR / "monitors.json"
SOCKET_PATH = RUNTIME_DIR / "core.sock"
LYRICS_CACHE = CACHE_DIR / "lyrics"
ART_CACHE = CACHE_DIR / "art"
USER_LYRICS_DIR = CONFIG_DIR / "lyrics"


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, CACHE_DIR, STATE_DIR, LYRICS_CACHE, ART_CACHE, USER_LYRICS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
