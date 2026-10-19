"""Persistent chrome: header (brand, module tabs, track, status, clock) and bottom key hints."""

from __future__ import annotations

import datetime as dt

from rich.text import Text
from textual.widget import Widget

from .glyphs import CRIMSON, DUSTY, LINE, MUTED, PALE, ROSE, TEXT, UNICODE, fmt_time

MODULES = [("1", "home", "HOME"), ("2", "music", "MUSIC"), ("3", "monitor", "MONITOR"),
           ("4", "files", "FILES"), ("5", "commands", "COMMANDS"), ("6", "theme", "THEME")]


class CrimsonHeader(Widget):
    def render(self) -> Text:
        app = self.app
        w = self.size.width
        core = app.core
        now = dt.datetime.now()
        clock = now.strftime("%H:%M:%S" if app.settings.clock_24h else "%I:%M:%S %p")
        date = now.strftime("%a %d %b").upper()

        left = Text()
        left.append(" ◢◤ " if UNICODE else " // ", style=f"bold {PALE} on {CRIMSON}")
        left.append("CRIMSON TERMINAL OS " if w >= 110 else "CRIMSON OS ", style=f"bold {PALE} on {CRIMSON}")
        left.append(" ")
        for key, mode, label in MODULES:
            active = app.current_mode == mode
            short = label if w >= 120 else label[:4] if w >= 80 else ""
            chip = f" {key}{(' ' + short) if short else ''} "
            left.append(chip, style=f"bold {TEXT} on {CRIMSON}" if active else f"{MUTED}")
        dot = "●" if UNICODE else "*"
        status = Text()
        if core.connected:
            p = core.player
            if p.get("available") and core.track.get("title") and w >= 140:
                t = core.track
                status.append("▶ " if p.get("playing") else "❚❚ ", style=DUSTY)
                status.append(f"{t['title'][:28]}", style=PALE)
                status.append(f" · {t.get('artist', '')[:20]}  ", style=MUTED)
            status.append(dot, style=DUSTY if p.get("available") else LINE)
            status.append(" spotify " if w >= 100 else " ", style=MUTED)
        status.append(dot, style=DUSTY if core.connected else ROSE)
        status.append(" core " if w >= 100 else " ", style=MUTED)
        perf = app.performance
        status.append(f"{perf.upper()[:3]} ", style=MUTED)
        status.append(f" {date} ", style=MUTED)
        status.append(f"{clock} ", style=f"bold {PALE}")

        line1 = Text()
        line1.append_text(left)
        pad = w - left.cell_len - status.cell_len
        line1.append(" " * max(1, pad))
        line1.append_text(status)
        line1.truncate(w)
        return line1


class StatusBar(Widget):
    hints: str = ""

    def render(self) -> Text:
        t = Text(" ")
        hints = getattr(self.app.screen, "HINTS", "") or ""
        common = "1-6 modules  / palette  ^S shell  ? help  ^Q quit"
        for part in (hints + ("   " if hints else "") + common).split("  "):
            part = part.strip()
            if not part:
                continue
            key, _, desc = part.partition(" ")
            t.append(f"{key}", style=f"bold {DUSTY}")
            t.append(f" {desc}   ", style=MUTED)
        t.truncate(self.size.width)
        return t


def kv(rows: list[tuple[str, str | Text]], key_width: int = 9) -> Text:
    out = Text()
    for i, (k, v) in enumerate(rows):
        out.append(f"{k:<{key_width}}", style=DUSTY)
        out.append_text(v if isinstance(v, Text) else Text(str(v), style=TEXT))
        if i < len(rows) - 1:
            out.append("\n")
    return out


def progress(pos: float, length: float, width: int) -> Text:
    width = max(10, width)
    frac = pos / length if length else 0
    filled = int(frac * width)
    t = Text()
    bar, head, rest = ("━", "╸", "─") if UNICODE else ("=", ">", "-")
    t.append(bar * filled, style=ROSE)
    if filled < width:
        t.append(head, style=PALE)
        t.append(rest * (width - filled - 1), style=LINE)
    return t


def time_pair(pos: float, length: float) -> str:
    return f"{fmt_time(pos)} / {fmt_time(length)}"
