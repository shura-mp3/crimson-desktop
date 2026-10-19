"""Terminal graphics helpers: a 5-row pixel block font, bar meters, spectrum and half-block album art.
All render to Rich Text; an ASCII fallback is used when the terminal isn't UTF-8."""

from __future__ import annotations

import locale
import os
import sys

from rich.text import Text

UNICODE = (sys.stdout.encoding or locale.getpreferredencoding() or "").lower().replace("-", "").startswith("utf") \
    and os.environ.get("CRIMSON_ASCII") != "1"

PALE, DUSTY, ROSE, CRIMSON, LINE, MUTED, TEXT = "#F2B7C5", "#D58B9F", "#C0485F", "#8D2445", "#482033", "#A88B98", "#F4E8ED"

# 5-row pixel font (3-5 columns per glyph). '#' = filled pixel.
FONT = {
    "A": [" ## ", "#  #", "####", "#  #", "#  #"], "B": ["### ", "#  #", "### ", "#  #", "### "],
    "C": [" ###", "#   ", "#   ", "#   ", " ###"], "D": ["### ", "#  #", "#  #", "#  #", "### "],
    "E": ["####", "#   ", "### ", "#   ", "####"], "F": ["####", "#   ", "### ", "#   ", "#   "],
    "G": [" ###", "#   ", "# ##", "#  #", " ###"], "H": ["#  #", "#  #", "####", "#  #", "#  #"],
    "I": ["###", " # ", " # ", " # ", "###"], "J": ["  ##", "   #", "   #", "#  #", " ## "],
    "K": ["#  #", "# # ", "##  ", "# # ", "#  #"], "L": ["#   ", "#   ", "#   ", "#   ", "####"],
    "M": ["#   #", "## ##", "# # #", "#   #", "#   #"], "N": ["#  #", "## #", "# ##", "#  #", "#  #"],
    "O": [" ## ", "#  #", "#  #", "#  #", " ## "], "P": ["### ", "#  #", "### ", "#   ", "#   "],
    "Q": [" ## ", "#  #", "#  #", "# ##", " ###"], "R": ["### ", "#  #", "### ", "# # ", "#  #"],
    "S": [" ###", "#   ", " ## ", "   #", "### "], "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#  #", "#  #", "#  #", "#  #", " ## "], "V": ["#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "# # #", "## ##", "#   #"], "X": ["#  #", "#  #", " ## ", "#  #", "#  #"],
    "Y": ["#   #", " # # ", "  #  ", "  #  ", "  #  "], "Z": ["####", "   #", " ## ", "#   ", "####"],
    "0": [" ## ", "#  #", "#  #", "#  #", " ## "], "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["### ", "   #", " ## ", "#   ", "####"], "3": ["### ", "   #", " ## ", "   #", "### "],
    "4": ["#  #", "#  #", "####", "   #", "   #"], "5": ["####", "#   ", "### ", "   #", "### "],
    "6": [" ## ", "#   ", "### ", "#  #", " ## "], "7": ["####", "   #", "  # ", " #  ", " #  "],
    "8": [" ## ", "#  #", " ## ", "#  #", " ## "], "9": [" ## ", "#  #", " ###", "   #", " ## "],
    ":": [" ", "#", " ", "#", " "], ".": [" ", " ", " ", " ", "#"], ",": [" ", " ", " ", "#", "#"],
    "!": ["#", "#", "#", " ", "#"], "?": ["### ", "   #", " ## ", "    ", " #  "], "'": ["#", "#", " ", " ", " "],
    "-": ["   ", "   ", "###", "   ", "   "], "/": ["   #", "  # ", " #  ", "#   ", "    "], " ": ["  ", "  ", "  ", "  ", "  "],
    "&": [" #  ", "# # ", " # #", "# # ", " # #"], "(": [" #", "# ", "# ", "# ", " #"], ")": ["# ", " #", " #", " #", "# "],
}


def big_width(text: str) -> int:
    return sum(len(FONT.get(ch, FONT["?"])[0]) + 1 for ch in text.upper()) - 1 if text else 0


def big_text(text: str, color: str = PALE, shadow: str | None = None) -> Text:
    """Render text in the pixel font (5 rows). Unknown characters render as '?'."""
    text = text.upper()
    rows = ["", "", "", "", ""]
    for i, ch in enumerate(text):
        g = FONT.get(ch, FONT["?"])
        for r in range(5):
            rows[r] += g[r] + (" " if i < len(text) - 1 else "")
    out = Text()
    full = "█" if UNICODE else "#"
    for r, row in enumerate(rows):
        for c, px in enumerate(row):
            if px == "#":
                out.append(full, style=color)
            elif shadow and UNICODE and r > 0 and c > 0 and rows[r - 1][c - 1:c] == "#":
                out.append("░", style=shadow)  # soft drop shadow
            else:
                out.append(" ")
        if r < 4:
            out.append("\n")
    return out


def fit_big(text: str, width: int) -> bool:
    return big_width(text) <= width


def meter(frac: float | None, width: int, label_color: str = ROSE) -> Text:
    """Segmented horizontal meter; None renders as an empty 'n/a' track."""
    width = max(4, width)
    t = Text()
    if frac is None:
        t.append(("·" if UNICODE else ".") * width, style=LINE)
        return t
    filled = round(max(0.0, min(1.0, frac)) * width)
    on, off = ("▰", "▱") if UNICODE else ("#", "-")
    for i in range(width):
        if i < filled:
            t.append(on, style=PALE if i >= width * 0.85 else label_color)
        else:
            t.append(off, style=LINE)
    return t


EIGHTHS = " ▁▂▃▄▅▆▇█"


def spectrum(values: list[float], width: int, height: int, mirror: bool = False) -> Text:
    """Multi-row spectrum bars (eighth-block resolution). mirror=True draws a symmetric, waveform-style shape."""
    if width <= 0 or height <= 0:
        return Text()
    n = len(values)
    if n == 0:
        values, n = [0.0] * 32, 32
    cols = [values[min(n - 1, int(i * n / width))] for i in range(width)]
    t = Text()
    if mirror:
        half = max(1, height // 2)
        rows_top = []
        for r in range(half):
            level_floor = (half - r - 1) / half
            line = Text()
            for v in cols:
                h = (v - level_floor) * half
                if UNICODE:
                    ch = "█" if h >= 1 else "▄" if h >= 0.5 else " "
                else:
                    ch = "#" if h >= 0.5 else " "
                line.append(ch, style=PALE if r == 0 else ROSE if r < half / 2 else CRIMSON)
            rows_top.append(line)
        for line in rows_top:
            t.append_text(line)
            t.append("\n")
        for i, line in enumerate(reversed(rows_top)):
            mirrored = Text(line.plain.replace("▄", "▀"), style=CRIMSON if i == 0 else LINE)
            t.append_text(mirrored)
            if i < len(rows_top) - 1:
                t.append("\n")
        return t
    for r in range(height):
        floor = (height - r - 1) / height
        for v in cols:
            h = (v - floor) * height
            if UNICODE:
                ch = EIGHTHS[8] if h >= 1 else EIGHTHS[max(0, int(h * 8))] if h > 0 else " "
            else:
                ch = "#" if h >= 0.5 else " "
            t.append(ch, style=PALE if r == 0 else ROSE if r < height * 0.5 else CRIMSON)
        if r < height - 1:
            t.append("\n")
    return t


def graph(values: list[float], width: int, height: int, vmax: float | None = None, color: str = ROSE) -> Text:
    """History graph on a FIXED scale (0..vmax), newest sample on the right. vmax=None → max(values)."""
    width, height = max(4, width), max(1, height)
    vals = list(values)[-width:]
    vals = [0.0] * (width - len(vals)) + vals
    top = vmax if vmax else (max(vals) or 1.0)
    t = Text()
    for r in range(height):
        floor = (height - r - 1) / height
        for v in vals:
            h = (min(v, top) / top - floor) * height
            if UNICODE:
                ch = EIGHTHS[8] if h >= 1 else EIGHTHS[max(0, int(h * 8))] if h > 0 else ("·" if r == height - 1 else " ")
            else:
                ch = "#" if h >= 0.5 else ("." if r == height - 1 else " ")
            t.append(ch, style=(PALE if r == 0 else color) if h > 0 else LINE)
        if r < height - 1:
            t.append("\n")
    return t


def album_art(path: str, width: int, height: int) -> Text | None:
    """Half-block (▀) rendering: 2 image pixels per character cell. Needs Pillow; None if unavailable."""
    if not path or not UNICODE:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB").resize((width, height * 2), Image.LANCZOS)
            px = im.load()
    except (OSError, ValueError):
        return None
    t = Text()
    for y in range(0, height * 2, 2):
        for x in range(width):
            top, bot = px[x, y], px[x, y + 1]
            # tint toward the palette so artwork sits inside the theme without losing detail
            tint = lambda c: tuple(int(c[i] * 0.88 + (141, 36, 69)[i] * 0.12) for i in range(3))  # noqa: E731
            a, b = tint(top), tint(bot)
            t.append("▀", style=f"#{a[0]:02x}{a[1]:02x}{a[2]:02x} on #{b[0]:02x}{b[1]:02x}{b[2]:02x}")
        if y < height * 2 - 2:
            t.append("\n")
    return t


def placeholder_art(width: int, height: int) -> Text:
    t = Text()
    for y in range(height):
        for x in range(width):
            on = (x // 2 + y) % 2 == 0 and abs(x - width / 2) + abs(y * 2 - height) < min(width, height * 2) / 2
            t.append(("▓" if UNICODE else "#") if on else " ", style=CRIMSON)
        if y < height - 1:
            t.append("\n")
    return t


def fmt_time(ms: float) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"
