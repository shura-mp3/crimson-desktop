"""THEME — Crimson OS settings, Konsole theme/autostart and desktop profiles."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Select, Static, Switch

from ..services import konsole
from ..services.settings import MODULES, Settings
from ..widgets.chrome import kv
from ..widgets.glyphs import DUSTY, MUTED, PALE, ROSE
from .base import ModuleScreen
from .dialogs import Confirm

TOGGLES = [("startup_animation", "Startup animation"), ("compact", "Compact mode"), ("clock_24h", "24-hour clock"),
           ("show_visualizer", "Show visualizers"), ("big_lyrics", "Big pixel lyrics"), ("show_hidden_files", "Show hidden files")]


class ThemeScreen(ModuleScreen):
    MODULE = "theme"
    HINTS = "tab move  enter/space change"
    DEFAULT_CSS = """
    ThemeScreen VerticalScroll { padding: 0 1; }
    ThemeScreen .panel { height: auto; }
    ThemeScreen Select { width: 44; }
    .settings-grid { grid-size: 2; grid-columns: 28 1fr; grid-rows: 3; height: auto; grid-gutter: 0 1; }
    .settings-grid Label { padding: 1 0 0 1; color: #D58B9F; }
    .btn-row { height: auto; margin: 1 0 0 0; }
    .btn-row Button { margin-right: 1; }
    #konsole-status, #profile-status { height: auto; padding: 0 1; }
    """

    def compose_body(self) -> ComposeResult:
        s = self.app.settings
        with VerticalScroll():
            with Vertical(classes="panel", id="p-settings"):
                with Grid(classes="settings-grid"):
                    yield Label("Performance")
                    yield Select([(v.upper() if v != "auto" else "AUTO (follow desktop)", v) for v in Settings.CHOICES["performance"]],
                                 value=s.performance, allow_blank=False, id="sel-performance")
                    yield Label("Start in module")
                    yield Select([(m.upper(), m) for m in MODULES], value=s.default_module, allow_blank=False, id="sel-default_module")
                    yield Label("Focus accent")
                    yield Select([(a.upper(), a) for a in Settings.CHOICES["accent"]], value=s.accent, allow_blank=False, id="sel-accent")
                    for key, label in TOGGLES:
                        yield Label(label)
                        yield Switch(value=getattr(s, key), id=f"sw-{key}")
            with Vertical(classes="panel", id="p-konsole"):
                yield Static(id="konsole-status")
                with Horizontal(classes="btn-row"):
                    yield Button("Apply Crimson Konsole theme", id="btn-theme", variant="primary")
                    yield Button("Enable auto-start", id="btn-auto-on")
                    yield Button("Disable auto-start", id="btn-auto-off")
            with Vertical(classes="panel", id="p-profiles"):
                yield Static(id="profile-status")
                with Horizontal(classes="btn-row"):
                    yield Button("Crimson Music", id="prof-crimson")
                    yield Button("Minimal Dark", id="prof-minimal")
                    yield Button("Performance", id="prof-performance")

    def on_mount(self) -> None:
        self.query_one("#p-settings").border_title = "01 // CRIMSON OS SETTINGS"
        self.query_one("#p-konsole").border_title = "02 // KONSOLE"
        self.query_one("#p-profiles").border_title = "03 // DESKTOP PROFILE (Crimson Desktop)"
        self._ready = True
        self.refresh_status()

    def refresh_status(self) -> None:
        st = konsole.status()
        rows = [("konsole", st["konsole"]), ("default", st["default_profile"]),
                ("crimson", ("profile ✓" if st["crimson_profile"] else "profile ✗") + ("  scheme ✓" if st["crimson_scheme"] else "  scheme ✗")),
                ("autostart", Text("ON — new Konsole windows open Crimson OS", style=PALE) if st["autostart"]
                 else Text("OFF" + (" (disabled by flag file)" if st["autostart_flag_disabled"] else ""), style=MUTED)),
                ("shell", st["shell"])]
        t = kv(rows, 10)
        t.append("\n\nAuto-start only affects Konsole windows using the 'Crimson OS' profile — never SSH, scripts or other terminals.\n"
                 "Bypass once: CRIMSON_NO_AUTOSTART=1 konsole   ·   disable without Python: crimson-autostart off", style=MUTED)
        self.query_one("#konsole-status", Static).update(t)
        core = self.app.core
        prof = core.ui.get("profile") or "?"
        pt = kv([("profile", Text(prof, style=PALE)), ("desktop", core.performance),
                 ("crimson os", f"{self.app.performance} " + ("(following desktop)" if self.app.settings.performance == "auto" else "(overridden here)"))], 12)
        if not core.connected:
            pt.append("\ncrimson-core is offline — profile switching still works through crimsonctl", style=ROSE)
        self.query_one("#profile-status", Static).update(pt)

    def on_core(self, kind: str) -> None:
        if kind in ("ui", "status"):
            self.refresh_status()

    # -------------------------------------------------------------- settings
    def on_select_changed(self, event: Select.Changed) -> None:
        if not getattr(self, "_ready", False) or event.value is Select.BLANK:
            return
        key = event.select.id.removeprefix("sel-")
        setattr(self.app.settings, key, event.value)
        self.app.save_settings()
        self.app.apply_settings()
        self.refresh_status()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if not getattr(self, "_ready", False):
            return
        setattr(self.app.settings, event.switch.id.removeprefix("sw-"), event.value)
        self.app.save_settings()
        self.app.apply_settings()

    # -------------------------------------------------------------- konsole & profiles
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-theme":
            self._script("konsole-theme.sh", "apply", "Crimson Konsole profile + colour scheme installed (backup made)")
        elif bid == "btn-auto-on":
            self.app.push_screen(Confirm("Open Crimson OS in every new Konsole window?",
                                         "Sets the 'Crimson OS' profile as Konsole's default. Your previous default is backed up. "
                                         "Exiting Crimson OS always leaves you in your normal shell.", "Enable", danger=False),
                                 lambda ok: ok and self._script("autostart.sh", "on", "auto-start enabled"))
        elif bid == "btn-auto-off":
            self._script("autostart.sh", "off", "auto-start disabled — Konsole's previous default profile restored")
        elif bid.startswith("prof-"):
            name = bid.removeprefix("prof-")
            from ..services.commands import CRIMSONCTL, run_argv
            try:
                run_argv([CRIMSONCTL, "profile", name])
                self.notify(f"switching desktop profile to {name}…")
            except FileNotFoundError as e:
                self.notify(str(e), severity="error")

    def _script(self, name: str, arg: str, success: str) -> None:
        rc, out = konsole.run_script(name, arg)
        if rc == 0:
            self.notify(success)
        else:
            self.notify(f"{name} {arg} failed: {out[-200:]}", severity="error", timeout=8)
        self.refresh_status()
