"""Short startup animation (≈1 s; any key skips; disabled by setting, --no-animation or LOW performance)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

from ..widgets.glyphs import CRIMSON, DUSTY, LINE, MUTED, PALE, ROSE, UNICODE, big_text

STEPS = ["mounting crimson-core link", "sampling sensors", "indexing applications", "loading lyrics engine", "ready"]


class SplashScreen(Screen):
    def __init__(self, on_done, duration: float = 1.1):
        super().__init__()
        self._on_done = on_done
        self._frames = max(6, int(duration / 0.08))
        self._i = 0
        self._finished = False

    def compose(self) -> ComposeResult:
        yield Static(id="splash")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.08, self._step)
        self._step()

    def _step(self) -> None:
        self._i += 1
        p = min(1.0, self._i / self._frames)
        w = max(20, self.size.width - 4)
        logo = big_text("CRIMSON", PALE if p > 0.4 else DUSTY)
        rows = logo.split("\n")
        visible = max(1, int(len(rows) * min(1.0, p * 2)))
        t = Text(justify="center")
        bar_w = min(48, w)
        t.append(("◢" + "■" * 3 + "◣" if UNICODE else "[###]") + "\n\n", style=CRIMSON)
        for r in rows[:visible]:
            t.append_text(r)
            t.append("\n")
        t.append("\n" * (len(rows) - visible))
        t.append("T E R M I N A L   O S\n\n", style=f"bold {ROSE}")
        filled = int(bar_w * p)
        t.append(("━" if UNICODE else "=") * filled, style=ROSE)
        t.append(("─" if UNICODE else "-") * (bar_w - filled) + "\n", style=LINE)
        step = STEPS[min(len(STEPS) - 1, int(p * len(STEPS)))]
        t.append(f"{step}…" if p < 1 else "ready", style=MUTED)
        self.query_one("#splash", Static).update(t)
        if self._i >= self._frames:
            self.finish()

    def on_key(self, event) -> None:
        event.stop()
        self.finish()

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        self._on_done()
