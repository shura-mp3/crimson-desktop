"""Modal dialogs: confirmation, text prompt, help overlay."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from ..widgets.glyphs import DUSTY, MUTED, PALE, TEXT


class Confirm(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "cancel"), Binding("y", "ok", "yes", show=False), Binding("n", "cancel", "no", show=False)]

    def __init__(self, title: str, body: str = "", ok_label: str = "OK", danger: bool = True):
        super().__init__()
        self._title, self._body, self._ok, self._danger = title, body, ok_label, danger

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = "CONFIRM"
            yield Static(Text(self._title, style=f"bold {PALE}"))
            if self._body:
                yield Static(Text(self._body, style=MUTED))
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button(self._ok, id="ok", variant="error" if self._danger else "primary")

    def on_mount(self) -> None:
        self.query_one("#cancel").focus()  # safe default

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "ok")

    def action_ok(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class Prompt(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "cancel")]

    def __init__(self, title: str, value: str = "", placeholder: str = ""):
        super().__init__()
        self._title, self._value, self._ph = title, value, placeholder

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog") as v:
            v.border_title = self._title.upper()
            yield Input(value=self._value, placeholder=self._ph, id="prompt-input")
            yield Static(Text("enter to confirm · esc to cancel", style=MUTED))

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


HELP = [
    ("GLOBAL", [("1 … 6", "Home · Music · Monitor · Files · Commands · Theme"),
                ("alt+1…6  F1…F6", "same, also while typing in a text field"), ("/", "command palette (fuzzy search)"),
                ("?", "this help"), ("tab / shift+tab", "move between panels"), ("esc", "back / close dialog"),
                ("ctrl+s", "open a shell (type `exit` to come back)"), ("ctrl+q  ctrl+c", "exit to the normal shell")]),
    ("MUSIC", [("space", "play / pause"), ("n / p", "next / previous"), ("← / →", "seek ∓5 s"),
               ("+ / -   0", "lyric offset ±100 ms (shared with dashboard) · reset"), ("b", "big pixel lyrics"),
               ("v", "visualizer: bars → mirrored → off"), ("r", "re-fetch lyrics")]),
    ("MONITOR", [("← / →", "switch tabs"), ("f", "filter processes"), ("s", "cycle sort (CPU/RAM/name/PID)"),
                 ("k", "terminate selected process (your own, non-critical, asks first)")]),
    ("FILES", [("enter", "open folder / file"), ("backspace", "parent folder"), ("~", "home"), (".", "hidden files"),
               ("s", "sort"), ("f", "filter"), ("b", "bookmarks · B add bookmark"), ("c / x  then  v", "copy / cut … paste here"),
               ("r", "rename"), ("n / N", "new folder / new file"), ("d", "move to Trash (asks first)"),
               ("o", "open with default app"), ("O", "open containing folder in Dolphin")]),
    ("COMMANDS", [("type", "fuzzy search apps & actions"), ("enter", "run"), ("↑ / ↓", "select")]),
]


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape,question_mark,q", "close", "close")]

    def compose(self) -> ComposeResult:
        t = Text()
        for section, rows in HELP:
            t.append(f"{section}\n", style=f"bold {PALE}")
            for k, d in rows:
                t.append(f"  {k:<18}", style=f"bold {DUSTY}")
                t.append(f"{d}\n", style=TEXT)
            t.append("\n")
        t.append("Auto-start bypass: CRIMSON_NO_AUTOSTART=1 konsole  ·  disable: crimson-autostart off", style=MUTED)
        with VerticalScroll(classes="dialog") as v:
            v.border_title = "KEYBOARD"
            yield Static(t)

    def action_close(self) -> None:
        self.dismiss(None)
