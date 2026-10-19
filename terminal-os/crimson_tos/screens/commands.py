"""COMMANDS — fuzzy launcher for Crimson actions, desktop apps and your own commands."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from ..services import commands as cmdsvc
from ..widgets.glyphs import DUSTY, MUTED, PALE
from .base import ModuleScreen


class CommandsScreen(ModuleScreen):
    MODULE = "commands"
    HINTS = "type search  ↑/↓ select  enter run  esc clear"
    BINDINGS = [Binding("escape", "clear", "clear", show=False), Binding("down", "to_list", "list", show=False)]
    DEFAULT_CSS = """
    #cmd-box { height: 1fr; }
    #cmd-results { height: 1fr; max-height: 100%; }
    #cmd-help { height: 2; color: #A88B98; }
    """

    def compose_body(self) -> ComposeResult:
        with Vertical(id="cmd-box", classes="panel"):
            yield Input(placeholder="search apps and actions…  (try: spotify, profile, files, settings)", id="cmd-search")
            yield OptionList(id="cmd-results")
            yield Static(id="cmd-help")

    def on_mount(self) -> None:
        self.query_one("#cmd-box").border_title = "COMMAND PALETTE"
        self.refresh_results("")
        self.query_one("#cmd-search").focus()

    def on_screen_resume(self) -> None:
        super().on_screen_resume()
        self.query_one("#cmd-search").focus()

    def refresh_results(self, query: str) -> None:
        results = cmdsvc.search(query, self.app.all_commands())
        ol = self.query_one("#cmd-results", OptionList)
        ol.clear_options()
        self._results = results
        for c in results:
            label = Text()
            label.append(f"{c.title}", style=f"bold {PALE}")
            label.append(f"   {c.category}", style=DUSTY)
            if c.help:
                label.append(f"  — {c.help[:70]}", style=MUTED)
            ol.add_option(Option(label, id=c.id))
        if results:
            ol.highlighted = 0
        self.query_one("#cmd-box").border_subtitle = f"{len(results)} match(es)"
        probs = self.app.command_problems
        self.query_one("#cmd-help", Static).update(
            Text(("⚠ " + "; ".join(probs)) if probs else f"custom commands: {cmdsvc.CUSTOM_FILE}", style=MUTED))

    def on_input_changed(self, event: Input.Changed) -> None:
        self.refresh_results(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        ol = self.query_one("#cmd-results", OptionList)
        if self._results:
            idx = ol.highlighted or 0
            self.app.execute_command(self._results[idx])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        cmd = next((c for c in self._results if c.id == event.option.id), None)
        if cmd:
            self.app.execute_command(cmd)

    def action_to_list(self) -> None:
        self.query_one("#cmd-results").focus()

    def action_clear(self) -> None:
        """esc: clear the search; if already empty, move focus to the results so 1-6 work again."""
        inp = self.query_one("#cmd-search", Input)
        if inp.value:
            inp.value = ""
            inp.focus()
        else:
            self.query_one("#cmd-results").focus()
