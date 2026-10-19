"""HOME — the main dashboard."""

from __future__ import annotations

import datetime as dt
import math

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ..services.metrics import human_bytes, human_duration
from ..widgets.chrome import kv, progress, time_pair
from ..widgets.glyphs import CRIMSON, DUSTY, LINE, MUTED, PALE, ROSE, TEXT, UNICODE, big_text, graph, meter, spectrum
from .base import ModuleScreen

LOGO = [
    "    ╱╲    ", "   ╱  ╲   ", "  ╱ ╱╲ ╲  ", " ◀ ◀  ▶ ▶ ", "  ╲ ╲╱ ╱  ", "   ╲  ╱   ", "    ╲╱    ",
] if UNICODE else ["    /\\    ", "   /  \\   ", "  / /\\ \\  ", " < <  > > ", "  \\ \\/ /  ", "   \\  /   ", "    \\/    "]

QUICK = [("goto:music", "♪  Music — Spotify & lyrics"), ("goto:files", "▤  Files"), ("goto:monitor", "▲  System monitor"),
         ("palette", "/  Command palette"), ("goto:theme", "◆  Theme & settings"), ("shell", "$  Open shell")]


class HomeScreen(ModuleScreen):
    MODULE = "home"
    HINTS = "enter run-action  tab next-panel"
    FAST = True
    SPECTRUM = True
    _phase = 0.0

    def compose_body(self) -> ComposeResult:
        with VerticalScroll():
            with Container(id="home-grid"):
                yield Static(id="identity", classes="panel")
                yield Static(id="clock", classes="panel")
                yield Static(id="music", classes="panel")
                with Container(id="hardware", classes="panel span-2"):
                    yield Static(id="hw-text")
                    yield Static(id="cpu-graph")
                with Container(id="quick", classes="panel"):
                    yield OptionList(*[Option(label, id=key) for key, label in QUICK], id="quick-list")
                yield Static(id="signal", classes="panel span-3")

    def on_mount(self) -> None:
        titles = {"identity": "01 // IDENTITY", "clock": "02 // LOCAL TIME", "music": "03 // NOW PLAYING",
                  "hardware": "04 // HARDWARE", "quick": "05 // QUICK ACTIONS", "signal": "06 // SIGNAL"}
        for wid, title in titles.items():
            self.query_one(f"#{wid}").border_title = title
        self._phase = 0.0
        self.tick(False)
        self.query_one("#quick-list").focus()

    def layout_for(self, width: int, height: int) -> None:
        grid = self.query_one("#home-grid")
        grid.set_class(width < 150 and width >= 96, "cols-2")
        grid.set_class(width < 96, "cols-1")

    # -------------------------------------------------------------- render
    def tick(self, fast: bool) -> None:
        app = self.app
        m = app.metrics
        if not fast:
            s = m.sample()
            st = m.static
            ident = Text()
            width = max(20, self.query_one("#identity").content_size.width)
            rows = [("user", f"{st['user']}@{st['host']}"), ("os", st["os"]), ("kernel", st["kernel"].split("-")[0]),
                    ("desktop", f"{st['desktop']} · {st['session']}"), ("shell", st["shell"]),
                    ("uptime", human_duration(m.uptime()))]
            if width >= 40:
                body = kv(rows).split("\n")
                for i in range(max(len(LOGO), len(body))):
                    ident.append(LOGO[i] if i < len(LOGO) else " " * len(LOGO[0]), style=ROSE)
                    ident.append("  ")
                    if i < len(body):
                        ident.append_text(body[i])
                    ident.append("\n")
            else:
                ident = kv(rows)
            self.query_one("#identity").update(ident)
            self._render_clock()
            self._render_hardware(s)
        self._render_music()
        self._render_signal(fast)

    def _render_clock(self) -> None:
        now = dt.datetime.now()
        hm = now.strftime("%H:%M" if self.app.settings.clock_24h else "%I:%M")
        w = self.query_one("#clock").content_size.width
        t = Text(justify="center")
        if w >= 22:
            t.append_text(big_text(hm, PALE))
        else:
            t.append(hm, style=f"bold {PALE}")
        t.append(f"\n\n{now.strftime('%A %d %B %Y').upper()}", style=DUSTY)
        t.append(f"\n:{now.strftime('%S')}  ·  up {human_duration(self.app.metrics.uptime())}", style=MUTED)
        self.query_one("#clock").update(t)

    def _render_hardware(self, s) -> None:
        m = self.app.metrics
        w = max(30, self.query_one("#hw-text").content_size.width)
        mw = max(8, min(30, w // 2 - 22))
        g = s.gpu
        disk = next(iter(m.disks()), None)
        lines = Text()

        def row(label, frac, value, extra=""):
            lines.append(f"{label:<5}", style=DUSTY)
            lines.append_text(meter(frac, mw))
            lines.append(f" {value:<14}", style=TEXT)
            lines.append(f"{extra}\n", style=MUTED)

        row("CPU", s.cpu / 100, f"{s.cpu:5.1f}%", f"{m.static['cpu'][:34]}"
            + (f" · {s.cpu_temp:.0f}°C" if s.cpu_temp is not None else "") + (f" · {s.freq_mhz / 1000:.2f} GHz" if s.freq_mhz else ""))
        if g.vendor != "unknown":
            row("GPU", (g.util / 100) if g.util is not None else None, f"{g.util:5.1f}%" if g.util is not None else "  n/a",
                f"{g.name[:30]}" + (f" · {g.temp:.0f}°C" if g.temp is not None else ""))
        else:
            row("GPU", None, "  n/a", "no GPU metrics available")
        row("RAM", s.mem_used / max(1, s.mem_total), f"{human_bytes(s.mem_used)}/{human_bytes(s.mem_total)}",
            f"swap {human_bytes(s.swap_used)}/{human_bytes(s.swap_total)}" if s.swap_total else "")
        if disk:
            row("DISK", disk["pct"] / 100, f"{disk['pct']:5.1f}%", f"{disk['mount']} · {human_bytes(disk['free'])} free")
        lines.append(f"{'NET':<5}", style=DUSTY)
        lines.append(f"↑ {human_bytes(s.net_up, True):<10} ↓ {human_bytes(s.net_down, True):<10}", style=TEXT)
        lines.append("cpu history (0-100%)", style=MUTED)
        self.query_one("#hw-text").update(lines)
        self.query_one("#cpu-graph", Static).update(graph(list(m.hist["cpu"]), w, 3, vmax=100))

    def _render_music(self) -> None:
        core = self.app.core
        box = self.query_one("#music")
        w = max(20, box.content_size.width)
        t = Text()
        if not core.connected:
            t.append("CRIMSON-CORE OFFLINE\n", style=f"bold {ROSE}")
            t.append("start it with:  crimsonctl start", style=MUTED)
        elif not core.player.get("available"):
            t.append("AWAITING SIGNAL\n", style=f"bold {DUSTY}")
            t.append("Spotify isn't running", style=MUTED)
        else:
            tr, p = core.track, core.player
            t.append(("▶ " if p.get("playing") else "❚❚ "), style=DUSTY)
            t.append(f"{tr.get('title', '—')}\n", style=f"bold {PALE}")
            t.append(f"{tr.get('artist', '')}\n", style=DUSTY)
            pos, length = core.position_ms(), tr.get("length_ms") or 0
            t.append_text(progress(pos, length, w - 14))
            t.append(f" {time_pair(pos, length)}\n", style=MUTED)
            li, _ = core.lyric_index()
            lines = core.lyrics.get("lines") or []
            if li >= 0:
                t.append(f"“{lines[li].get('text') or '♪'}”\n", style=f"italic {TEXT}")
            elif core.lyrics.get("status") not in ("synced",):
                t.append(f"lyrics: {core.lyrics.get('status', '—')}\n", style=MUTED)
            else:
                t.append("· · ·\n", style=MUTED)
            if self.app.settings.show_visualizer:
                t.append_text(spectrum(core.spectrum, w, 2))
        box.update(t)

    def _render_signal(self, fast: bool) -> None:
        """Decorative circuit pulse. Its brightness follows the REAL spectrum energy (zero when silent)."""
        box = self.query_one("#signal")
        w, h = max(10, box.content_size.width), max(3, min(14, box.content_size.height))
        energy = sum(self.app.core.spectrum) / len(self.app.core.spectrum) if self.app.core.spectrum else 0.0
        if self.app.performance != "low":
            self._phase += 0.15 + energy * 0.8
        t = Text()
        for y in range(h):
            for x in range(w):
                v = math.sin(x * 0.45 + self._phase + y * 0.9) * math.cos(y * 1.3 - self._phase * 0.5)
                if v > 0.82:
                    t.append("◆" if UNICODE else "*", style=PALE if energy > 0.25 else DUSTY)
                elif v > 0.55:
                    t.append("─" if (x + y) % 3 else "┼", style=ROSE if energy > 0.1 else CRIMSON)
                elif (x * 7 + y * 3) % 11 == 0:
                    t.append("·", style=LINE)
                else:
                    t.append(" ")
            if y < h - 1:
                t.append("\n")
        label = "audio-reactive · CAVA" if energy > 0 else "idle (no audio)"
        box.border_subtitle = label
        box.update(t)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.app.run_action_key(event.option.id)

    def on_core(self, kind: str) -> None:
        if kind in ("player", "lyrics", "status"):
            self._render_music()
