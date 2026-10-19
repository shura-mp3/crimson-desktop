"""Crimson Terminal OS — application shell: modules, navigation, palette, shell access, ticking."""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import partial
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.css.query import NoMatches
from textual.theme import Theme

from .screens.commands import CommandsScreen
from .screens.dialogs import Confirm, Help
from .screens.files import FilesScreen
from .screens.home import HomeScreen
from .screens.monitor import MonitorScreen
from .screens.music import MusicScreen
from .screens.splash import SplashScreen
from .screens.theme import ThemeScreen
from .services import commands as cmdsvc
from .services import settings as settings_svc
from .services.core_link import CoreLink
from .services.metrics import Metrics

FRAME = {"low": 0.5, "balanced": 0.1, "high": 1 / 30}  # fast-tick interval (visualizers, lyrics)

CRIMSON_THEME = Theme(
    name="crimson", dark=True,
    primary="#8D2445", secondary="#D58B9F", accent="#C0485F",
    foreground="#F4E8ED", background="#0B080D", surface="#120B12", panel="#190D16",
    success="#8FA88B", warning="#D6A57A", error="#E06C84", boost="#230B17",
)


class CrimsonCommands(Provider):
    """Feeds Textual's command palette (opened with `/`) from the shared command registry."""

    async def search(self, query: str) -> Hits:
        app = self.app
        matcher = self.matcher(query)
        for cmd in cmdsvc.search(query, app.all_commands(), limit=40):
            label = f"{cmd.title}  ·  {cmd.category}"
            yield Hit(max(matcher.match(label), 0.01), matcher.highlight(label), partial(app.execute_command, cmd), help=cmd.help)

    async def discover(self) -> Hits:
        for cmd in self.app.all_commands()[:25]:
            yield Hit(1.0, f"{cmd.title}  ·  {cmd.category}", partial(self.app.execute_command, cmd), help=cmd.help)


class CrimsonApp(App):
    TITLE = "Crimson Terminal OS"
    CSS_PATH = Path(__file__).parent / "styles" / "crimson.tcss"
    COMMANDS = {CrimsonCommands}
    COMMAND_PALETTE_BINDING = "slash"
    MODES = {"home": HomeScreen, "music": MusicScreen, "monitor": MonitorScreen,
             "files": FilesScreen, "commands": CommandsScreen, "theme": ThemeScreen}
    BINDINGS = [
        Binding("1", "goto('home')", "home", show=False),
        Binding("2", "goto('music')", "music", show=False),
        Binding("3", "goto('monitor')", "monitor", show=False),
        Binding("4", "goto('files')", "files", show=False),
        Binding("5", "goto('commands')", "commands", show=False),
        Binding("6", "goto('theme')", "theme", show=False),
        # work even while a text field has focus
        *[Binding(f"alt+{i},f{i}", f"goto('{m}')", m, show=False, priority=True)
          for i, m in enumerate(["home", "music", "monitor", "files", "commands", "theme"], 1)],
        Binding("question_mark", "help", "help", show=False),
        Binding("ctrl+s", "shell", "shell", show=False, priority=True),
        Binding("ctrl+q", "quit_to_shell", "quit", show=False, priority=True),
        Binding("ctrl+c", "quit_to_shell", "quit", show=False, priority=True),
    ]

    def __init__(self, animation: bool = True, safe_mode: bool = False, module: str | None = None):
        super().__init__()
        self.settings, self.settings_problems = settings_svc.load()
        self.safe_mode = safe_mode
        self.animation = animation and self.settings.startup_animation
        self.start_module = module or self.settings.default_module
        self.metrics = Metrics()
        self.core = CoreLink(self._on_core, start_core=not safe_mode)
        self._apps_cache: list[cmdsvc.Command] | None = None
        self.command_problems: list[str] = []
        self._fast = None
        self._slow = None

    # ------------------------------------------------------------------ lifecycle
    def on_mount(self) -> None:
        self.register_theme(CRIMSON_THEME)
        self.theme = "crimson"
        self.apply_settings()
        if not self.safe_mode:
            self.core.start()
        self.switch_mode(self.start_module)
        if self.animation and self.performance != "low":
            self.push_screen(SplashScreen(self.pop_screen))
        self._slow = self.set_interval(1.0, self._slow_tick)
        for p in self.settings_problems:
            self.notify(f"settings: {p}", severity="warning", timeout=6)

    async def on_unmount(self) -> None:
        await self.core.stop()

    # ------------------------------------------------------------------ settings / performance
    @property
    def performance(self) -> str:
        p = self.settings.performance
        return self.core.performance if p == "auto" else p

    def save_settings(self) -> None:
        settings_svc.save(self.settings)

    def apply_settings(self) -> None:
        for a in ("crimson", "rose", "dusty"):
            self.set_class(self.settings.accent == a, f"accent-{a}")
        self.set_class(self.settings.compact, "compact")
        self._restart_fast_tick()

    def _restart_fast_tick(self) -> None:
        if self._fast:
            self._fast.stop()
            self._fast = None
        screen = self.screen if self.screen_stack else None
        if screen is not None and getattr(screen, "FAST", False):
            self._fast = self.set_interval(FRAME.get(self.performance, 0.1), self._fast_tick)

    def screen_changed(self, screen) -> None:
        """A module became visible: re-target ticking and the spectrum subscription to it."""
        self.core.want_spectrum(bool(getattr(screen, "SPECTRUM", False)) and self.settings.show_visualizer)
        self._restart_fast_tick()
        screen.refresh_chrome()

    @staticmethod
    def _call(scr, name: str, *args) -> None:
        """Call a screen hook only once it is mounted; a screen mid-compose has no widgets to query yet."""
        fn = getattr(scr, name, None)
        if fn is None or not scr.is_mounted:
            return
        try:
            fn(*args)
        except NoMatches:
            pass  # widgets not composed yet (or being torn down) — the next tick catches up

    def _fast_tick(self) -> None:
        if self.screen_stack:
            self._call(self.screen, "tick", True)

    def _slow_tick(self) -> None:
        if not self.screen_stack:
            return
        scr = self.screen
        self._call(scr, "tick", False)
        self._call(scr, "refresh_chrome")

    def _on_core(self, kind: str) -> None:
        scr = self.screen if self.screen_stack else None
        if scr is None:
            return
        if kind == "ui":
            self._restart_fast_tick()
        if kind == "toast" and self.core.toast:
            self.notify(self.core.toast, timeout=3)
        if kind != "spec":
            self._call(scr, "on_core", kind)
        if kind in ("status", "player", "ui"):
            self._call(scr, "refresh_chrome")

    # ------------------------------------------------------------------ navigation
    def action_goto(self, module: str) -> None:
        if module in self.MODES and self.current_mode != module:
            self.switch_mode(module)

    def action_help(self) -> None:
        self.push_screen(Help())

    def action_quit_to_shell(self) -> None:
        if self.settings.confirm_quit:
            self.push_screen(Confirm("Exit Crimson Terminal OS?", "You'll land in your normal shell.", "Exit", danger=False),
                             lambda ok: ok and self.exit(0))
        else:
            self.exit(0)

    def action_shell(self) -> None:
        """Suspend the UI, run the user's shell, come back when it exits."""
        shell = os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"
        env = dict(os.environ, CRIMSON_TOS_SUBSHELL="1")
        try:
            with self.suspend():
                print("\033[38;2;213;139;159m◢◤ Crimson OS suspended — type `exit` (or Ctrl+D) to return.\033[0m")
                subprocess.run([shell], env=env)
        except Exception as e:  # noqa: BLE001 - SuspendNotSupported on some drivers
            self.notify(f"can't suspend here ({e}); use Ctrl+Q to exit to the shell", severity="warning")
        self.refresh()

    # ------------------------------------------------------------------ commands
    def all_commands(self) -> list[cmdsvc.Command]:
        if self._apps_cache is None:
            custom, problems = cmdsvc.custom_commands()
            self.command_problems = problems
            self._apps_cache = cmdsvc.builtin_commands() + custom + cmdsvc.desktop_entries()
        return self._apps_cache

    def run_action_key(self, key: str) -> None:
        if key == "palette":
            self.action_command_palette()
        elif key == "shell":
            self.action_shell()
        elif key.startswith("goto:"):
            self.action_goto(key.split(":", 1)[1])

    def execute_command(self, cmd: cmdsvc.Command) -> None:
        if cmd.confirm:
            self.push_screen(Confirm(f"Run: {cmd.title}?", cmd.help or " ".join(cmd.argv), "Run", danger=False),
                             lambda ok: ok and self._run(cmd))
        else:
            self._run(cmd)

    def _run(self, cmd: cmdsvc.Command) -> None:
        a = cmd.action
        try:
            if a.startswith("goto:"):
                self.action_goto(a.split(":", 1)[1])
            elif a == "shell":
                self.action_shell()
            elif a == "quit":
                self.action_quit_to_shell()
            elif a == "help":
                self.action_help()
            elif a.startswith("core:"):
                if not self.core.connected:
                    self.notify("crimson-core isn't running (crimsonctl start)", severity="warning")
                self.core.command(a.split(":", 1)[1])
            elif a == "foreground" and cmd.argv:   # show the command's output in the terminal, then come back
                with self.suspend():
                    subprocess.run(cmd.argv)
                    input("\n[press Enter to return to Crimson OS]")
            elif cmd.desktop_file:
                cmdsvc.launch_desktop(cmd.desktop_file)
                self.notify(f"launching {cmd.title}…", timeout=2)
            elif cmd.argv:
                cmdsvc.run_argv(cmd.argv)
                self.notify(f"{cmd.title}", timeout=2)
        except (OSError, FileNotFoundError) as e:
            self.notify(f"{cmd.title}: {e}", severity="error")
