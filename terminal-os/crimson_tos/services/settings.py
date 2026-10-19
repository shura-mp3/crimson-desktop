"""Terminal OS settings: ~/.config/crimson-desktop/terminal-os.toml (validated, written atomically).

The desktop-wide performance level (Crimson Music / Minimal Dark / Performance profiles, GameMode)
comes from crimson-core; `performance = "auto"` follows it, anything else overrides it.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from crimson import paths

SETTINGS_FILE = paths.CONFIG_DIR / "terminal-os.toml"
MODULES = ("home", "music", "monitor", "files", "commands", "theme")


@dataclass
class Settings:
    performance: str = "auto"          # auto | low | balanced | high
    startup_animation: bool = True
    default_module: str = "home"
    compact: bool = False
    clock_24h: bool = True
    show_visualizer: bool = True
    big_lyrics: bool = False
    show_hidden_files: bool = False
    confirm_quit: bool = False
    accent: str = "crimson"            # crimson | rose | dusty

    CHOICES = {
        "performance": ("auto", "low", "balanced", "high"),
        "default_module": MODULES,
        "accent": ("crimson", "rose", "dusty"),
    }

    def validate(self) -> list[str]:
        """Fix invalid values in place; return human-readable problems."""
        problems = []
        defaults = Settings()
        for f in fields(self):
            val = getattr(self, f.name)
            default = getattr(defaults, f.name)
            if not isinstance(val, type(default)):
                problems.append(f"{f.name}: expected {type(default).__name__}, got {val!r}")
                setattr(self, f.name, default)
            elif f.name in self.CHOICES and val not in self.CHOICES[f.name]:
                problems.append(f"{f.name}: {val!r} not one of {', '.join(self.CHOICES[f.name])}")
                setattr(self, f.name, default)
        return problems


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def load(path: Path = SETTINGS_FILE) -> tuple[Settings, list[str]]:
    s = Settings()
    problems: list[str] = []
    if path.exists():
        try:
            data = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as e:
            return s, [f"{path} unreadable ({e}); using defaults"]
        known = {f.name for f in fields(Settings)}
        for k, v in data.items():
            if k in known:
                setattr(s, k, v)
            else:
                problems.append(f"unknown setting {k!r} ignored")
        problems += s.validate()
    return s, problems


def save(s: Settings, path: Path = SETTINGS_FILE) -> None:
    s.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "# Crimson Terminal OS settings (edit here or in the THEME module)\n"
    body += "".join(f"{k} = {_toml_value(v)}\n" for k, v in asdict(s).items())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body)
    tmp.replace(path)
