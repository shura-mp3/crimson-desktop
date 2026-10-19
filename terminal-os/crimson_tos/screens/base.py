"""Base class for module screens: shared header/status bar + visibility-aware ticking."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from ..widgets.chrome import CrimsonHeader, StatusBar


class ModuleScreen(Screen):
    MODULE = ""
    HINTS = ""
    FAST = False       # wants the fast tick (visualizers); otherwise ~1 Hz
    SPECTRUM = False   # subscribe to the core's CAVA spectrum while visible

    def compose(self) -> ComposeResult:
        yield CrimsonHeader()
        yield from self.compose_body()
        yield StatusBar()

    def compose_body(self) -> ComposeResult:
        yield Static("")

    # called by the app ------------------------------------------------
    def tick(self, fast: bool) -> None:
        """fast=True on every frame tick, fast=False roughly once per second."""

    def on_core(self, kind: str) -> None:
        """crimson-core sent a message (player / lyrics / ui / art / spec / status / toast)."""

    def on_screen_resume(self) -> None:
        self.app.screen_changed(self)

    def refresh_chrome(self) -> None:
        for w in self.query(CrimsonHeader):
            w.refresh()
        for w in self.query(StatusBar):
            w.refresh()

    def on_resize(self, event) -> None:
        self.layout_for(self.size.width, self.size.height)

    def layout_for(self, width: int, height: int) -> None:
        """Override to adapt layout to the terminal size."""
