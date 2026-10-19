"""Command registry for the COMMANDS module and the `/` palette.

Sources (only things that actually exist on this system are listed):
  * built-in navigation / app actions
  * Crimson Desktop actions via `crimsonctl` (profiles, dashboard, services, lyrics)
  * installed applications from freedesktop .desktop entries (launched with `gio launch` or
    `kioclient exec`, never by passing the Exec= line to a shell)
  * your own commands from ~/.config/crimson-desktop/terminal-os-commands.toml (argument arrays)

There is deliberately no "run arbitrary text" or sudo command: privileged work stays in a shell.
"""

from __future__ import annotations

import configparser
import os
import shlex
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from crimson import paths

CUSTOM_FILE = paths.CONFIG_DIR / "terminal-os-commands.toml"
CRIMSONCTL = str(paths.PROJECT_DIR / "bin" / "crimsonctl")


@dataclass
class Command:
    id: str
    title: str
    category: str
    help: str = ""
    argv: list[str] = field(default_factory=list)   # external program (no shell)
    action: str = ""                                  # internal action, e.g. "goto:music", "shell", "quit"
    desktop_file: str = ""
    confirm: bool = False
    keywords: str = ""

    @property
    def haystack(self) -> str:
        return f"{self.title} {self.category} {self.keywords} {self.help}".lower()


def score(query: str, cmd: Command) -> float:
    """Fuzzy score: substring hits rank highest, then in-order subsequence matches (0 = no match)."""
    q = query.lower().strip()
    if not q:
        return 1.0
    title, hay = cmd.title.lower(), cmd.haystack
    if title.startswith(q):
        return 100 - len(title) / 100
    if q in title:
        return 80 - title.index(q) / 10
    if q in hay:
        return 50
    pos, gaps = 0, 0
    for ch in q:
        found = hay.find(ch, pos)
        if found < 0:
            return 0.0
        gaps += found - pos
        pos = found + 1
    return max(1.0, 30 - gaps / 4)


def search(query: str, cmds: list[Command], limit: int = 200) -> list[Command]:
    scored = [(score(query, c), c) for c in cmds]
    return [c for s, c in sorted((x for x in scored if x[0] > 0), key=lambda x: (-x[0], x[1].title))][:limit]


# ------------------------------------------------------------------ built-ins
def builtin_commands() -> list[Command]:
    nav = [("home", "Home dashboard"), ("music", "Music — Spotify & lyrics"), ("monitor", "System monitor"),
           ("files", "File manager"), ("commands", "Command palette & apps"), ("theme", "Theme & settings")]
    cmds = [Command(f"goto-{m}", f"Open {t}", "Crimson OS", action=f"goto:{m}", keywords=m) for m, t in nav]
    cmds += [
        Command("shell", "Open shell", "Crimson OS", "drop into your normal shell; type `exit` to come back",
                action="shell", keywords="terminal bash zsh fish prompt"),
        Command("help", "Keyboard shortcuts", "Crimson OS", action="help", keywords="help keys"),
        Command("quit", "Exit Crimson Terminal OS", "Crimson OS", "leave to the normal shell", action="quit", keywords="exit close"),
        Command("play-pause", "Play / pause", "Music", argv=[], action="core:play_pause", keywords="spotify"),
        Command("next", "Next track", "Music", action="core:next", keywords="skip spotify"),
        Command("prev", "Previous track", "Music", action="core:prev", keywords="back spotify"),
        Command("reload-lyrics", "Re-fetch lyrics for this track", "Music", action="core:reload_lyrics", keywords="lrclib"),
    ]
    if Path(CRIMSONCTL).exists():
        ctl = [CRIMSONCTL]
        cmds += [
            Command("profile-crimson", "Desktop profile: Crimson Music", "Crimson Desktop", argv=ctl + ["profile", "crimson"], keywords="profile"),
            Command("profile-minimal", "Desktop profile: Minimal Dark", "Crimson Desktop", argv=ctl + ["profile", "minimal"], keywords="profile"),
            Command("profile-performance", "Desktop profile: Performance (gaming)", "Crimson Desktop", argv=ctl + ["profile", "performance"], keywords="profile gaming"),
            Command("dash-toggle", "Show / hide the music dashboard", "Crimson Desktop", argv=ctl + ["toggle"], keywords="dashboard"),
            Command("services-restart", "Restart Crimson services", "Crimson Desktop", "crimson-core + dashboard", argv=ctl + ["restart"],
                    confirm=True, keywords="restart core"),
            Command("kitty-lyrics", "Open lyrics in Kitty", "Crimson Desktop", argv=ctl + ["lyrics"], keywords="lyrics kitty"),
            Command("spotify-status", "Crimson Spotify status (opens in shell)", "Crimson Desktop", argv=ctl + ["spotify", "status"], action="foreground",
                    keywords="spicetify"),
        ]
    return cmds


# ------------------------------------------------------------------ desktop entries
def _data_dirs() -> list[Path]:
    home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    dirs = [home] + [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
    dirs += [home / "flatpak" / "exports" / "share", Path("/var/lib/flatpak/exports/share")]
    return list(dict.fromkeys(dirs))


def desktop_entries() -> list[Command]:
    desktops = set((os.environ.get("XDG_CURRENT_DESKTOP") or "").lower().split(":"))
    seen: dict[str, Command] = {}
    for d in _data_dirs():
        appdir = d / "applications"
        if not appdir.is_dir():
            continue
        for f in sorted(appdir.rglob("*.desktop")):
            app_id = str(f.relative_to(appdir)).replace("/", "-")
            if app_id in seen:
                continue  # earlier dirs take precedence (user overrides)
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            cp.optionxform = str
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if e.get("Type") != "Application" or e.get("NoDisplay") == "true" or e.get("Hidden") == "true":
                seen[app_id] = None  # a hidden user override hides the system entry too
                continue
            only = {x.lower() for x in e.get("OnlyShowIn", "").split(";") if x}
            notin = {x.lower() for x in e.get("NotShowIn", "").split(";") if x}
            if (only and not only & desktops) or (notin & desktops):
                continue
            tryexec = e.get("TryExec")
            if tryexec and not shutil.which(tryexec) and not Path(tryexec).exists():
                continue
            seen[app_id] = Command(
                id="app:" + app_id, title=e.get("Name", app_id), category="Applications",
                help=e.get("Comment", "") or e.get("GenericName", ""), desktop_file=str(f),
                keywords=" ".join(filter(None, [e.get("GenericName", ""), e.get("Keywords", "").replace(";", " "),
                                                e.get("Categories", "").replace(";", " ")])))
    return [c for c in seen.values() if c]


def launch_desktop(path: str) -> None:
    for tool in (["gio", "launch", path], ["kioclient", "exec", path], ["kioclient5", "exec", path]):
        if shutil.which(tool[0]):
            subprocess.Popen(tool, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return
    # last resort: parse Exec= ourselves (field codes dropped), still without a shell
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    argv = [a for a in shlex.split(cp["Desktop Entry"]["Exec"]) if not (len(a) == 2 and a.startswith("%"))]
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


# ------------------------------------------------------------------ custom commands
EXAMPLE_CUSTOM = '''# Crimson Terminal OS — custom commands. Each entry is an argument array (no shell).
# [[command]]
# title = "Open Projects in Dolphin"
# argv = ["dolphin", "~/Projects"]       # "~" is expanded in arguments
# category = "My commands"              # optional
# help = "file manager on my projects"  # optional
# confirm = false                       # ask before running
'''


def custom_commands(path: Path = CUSTOM_FILE) -> tuple[list[Command], list[str]]:
    if not path.exists():
        return [], []
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        return [], [f"{path.name}: {e}"]
    out, problems = [], []
    for i, c in enumerate(data.get("command", [])):
        argv = c.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            problems.append(f"command #{i + 1}: 'argv' must be a non-empty list of strings")
            continue
        if argv[0] in ("sudo", "pkexec", "doas", "su", "run0"):
            problems.append(f"command #{i + 1}: privileged commands are not allowed in the palette — use the shell")
            continue
        out.append(Command(f"custom:{i}", str(c.get("title", " ".join(argv))), str(c.get("category", "My commands")),
                           str(c.get("help", "")), argv=[os.path.expanduser(a) for a in argv], confirm=bool(c.get("confirm", False))))
    return out, problems


def run_argv(argv: list[str]) -> None:
    if not shutil.which(argv[0]) and not Path(argv[0]).exists():
        raise FileNotFoundError(f"{argv[0]} not found")
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
