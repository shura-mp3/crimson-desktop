"""Configuration: built-in defaults, deep-merged with ~/.config/crimson-desktop/config.toml.

The TOML file is only ever read. Values the user changes at runtime (timing offsets,
current profile/performance level) live in small JSON files under ~/.local/state.
"""

from __future__ import annotations

import copy
import json
import logging
import tomllib
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "spotify": {
        # MPRIS player names in priority order. "*" = fall back to any MPRIS player.
        "players": ["spotify"],
        # Seconds between Position re-reads while playing (drift / seek detection).
        "resync_interval": 1.5,
    },
    "lyrics": {
        # Global latency compensation in ms. Positive = lyrics appear EARLIER.
        "latency_ms": 0,
        "local_dirs": ["~/Music/Lyrics", "~/Music/lyrics", "~/.lyrics"],
        "lrclib": True,
        "lrclib_url": "https://lrclib.net",
        "duration_tolerance": 3,
        "negative_cache_hours": 24,
        # "auto" = word-by-word when the LRC has word timestamps, else line mode.
        # "line" = always line mode. "word" = single huge word (only with word timestamps).
        "display_mode": "auto",
    },
    "audio": {
        "enabled": True,
        # "system" = everything you hear (default sink monitor).
        # "spotify" = experimental: capture only Spotify's PipeWire stream.
        "source": "system",
        "bars": 48,
        "cava_binary": "cava",
    },
    "dashboard": {
        # "auto" = the right-most monitor, or a connector name such as "DP-2".
        "monitor": "auto",
        # "auto" tries layer-shell (sits under windows, never takes focus), else a KWin-ruled window.
        "mode": "auto",
        "layout": "full",
        "performance": "balanced",
        # When GameMode reports an active game: "low", "hide" or "ignore".
        "gamemode_action": "low",
        # Reduce effects automatically when the 1-minute load average exceeds cores * this.
        "load_threshold": 0.9,
    },
    "spicetify": {
        # loopback WebSocket that lets the Crimson Spicetify theme read playback/lyrics state
        "bridge": True,
        "bridge_port": 47811,
        "allowed_origins": ["https://xpui.app.spotify.com"],
    },
    "ui": {
        # "crisp": the pixel font drawn sharp at the screen's real resolution (default).
        # "retro": extra chunky nearest-neighbour blocks. (Replaces the old pixelate_lyrics key,
        # which is still accepted in config files but no longer changes the renderer.)
        "lyrics_style": "crisp",
        # neon glow behind the big lyric/clock text: 0 = off ... 1 = strong (off in the low profile)
        "lyrics_glow": 0.8,
        "pixelate_lyrics": False,
        "clock_24h": True,
        "username": "",
        "show_matrix": True,
        "show_circuit": True,
        "show_blob": True,
    },
}

PERFORMANCE = {
    "low": {"fps": 15, "cava_fps": 30, "decor": False, "glow": False, "grain": False, "border_anim": False},
    "balanced": {"fps": 30, "cava_fps": 45, "decor": True, "glow": True, "grain": True, "border_anim": False},
    "high": {"fps": 60, "cava_fps": 60, "decor": True, "glow": True, "grain": True, "border_anim": True},
}

PROFILES = {
    # profile -> (dashboard running?, layout, performance)
    "crimson": {"dashboard": True, "layout": "full", "performance": None},
    "minimal": {"dashboard": True, "layout": "minimal", "performance": "balanced"},
    "performance": {"dashboard": False, "layout": "minimal", "performance": "low"},
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: Path | None = None) -> dict[str, Any]:
    path = path or paths.CONFIG_FILE
    cfg = copy.deepcopy(DEFAULTS)
    if path.exists():
        try:
            with open(path, "rb") as f:
                cfg = _merge(cfg, tomllib.load(f))
        except (OSError, tomllib.TOMLDecodeError) as e:
            log.error("config %s unreadable (%s) - using defaults", path, e)
    return cfg


class JsonState:
    """A tiny JSON-backed dict, written atomically."""

    def __init__(self, path: Path, default: dict | None = None):
        self.path = path
        self.data: dict = dict(default or {})
        try:
            self.data.update(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        tmp.replace(self.path)
