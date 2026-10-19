"""crimson-lyrics: synchronized Spotify lyrics in the terminal (made for Kitty, works in any truecolor terminal).

Uses the same crimson-core backend as the dashboard. If the core service isn't running it is
started; if that's impossible, an embedded core runs inside this process.

Keys:  space play/pause   n/p next/prev   ←/→ seek 5s   +/- offset ±100ms   0 reset offset
       r reload lyrics    b big text (kitty ≥0.40)   c compact   j/k scroll   ? help   q quit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import sys
import termios
import textwrap
import time
import tty
import unicodedata

from . import client, config, lrc, paths

# palette (truecolor)
BG = (11, 8, 13)
CRIMSON = (141, 36, 69)
ROSE = (192, 72, 95)
DUSTY = (213, 139, 159)
PALE = (242, 183, 197)
MUTED = (168, 139, 152)
DIM = (92, 62, 76)
FAINT = (60, 38, 50)

ESC = "\x1b"


def fg(c):
    return f"{ESC}[38;2;{c[0]};{c[1]};{c[2]}m"


def bgc(c):
    return f"{ESC}[48;2;{c[0]};{c[1]};{c[2]}m"


RST = f"{ESC}[0m"
BOLD = f"{ESC}[1m"


def width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 0 if unicodedata.combining(ch) else 1 for ch in s)


def clip(s: str, w: int) -> str:
    if width(s) <= w:
        return s
    out, acc = "", 0
    for ch in s:
        cw = width(ch)
        if acc + cw > w - 1:
            break
        out += ch
        acc += cw
    return out + "…"


def center(s: str, w: int, visible: int | None = None) -> str:
    v = width(s) if visible is None else visible
    return " " * max(0, (w - v) // 2) + s


def fmt_time(ms: float) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


class LyricsTUI:
    def __init__(self, args):
        self.args = args
        self.player: dict = {}
        self.lyrics: dict = {"status": "none", "lines": []}
        self.toast: tuple[str, float] | None = None
        self.big = args.big
        self.compact = args.compact
        self.help = False
        self.scroll = 0
        self.prev_frame: list[str] = []
        self.dirty = True
        self.writer: asyncio.StreamWriter | None = None
        self.local_core = None
        self.connected = False
        self.cols, self.rows = shutil.get_terminal_size((80, 24))

    # ------------------------------------------------------------ connection
    async def connect(self) -> None:
        for attempt in range(2):
            try:
                reader, self.writer = await asyncio.open_unix_connection(str(paths.SOCKET_PATH))
                self.connected = True
                self._send({"cmd": "sub", "topics": []})
                asyncio.create_task(self._read(reader))
                return
            except (FileNotFoundError, ConnectionRefusedError):
                if attempt == 0 and not self.args.embedded:
                    await asyncio.get_running_loop().run_in_executor(None, client.start_core)
                    for _ in range(20):
                        await asyncio.sleep(0.15)
                        if paths.SOCKET_PATH.exists():
                            break
        # embedded fallback
        from .core import Core
        self.local_core = Core(config.load())
        await self.local_core.start(serve=False)
        self._local_client = self.local_core.add_local_client(self._on_msg)
        self.connected = True

    async def _read(self, reader) -> None:
        try:
            while line := await reader.readline():
                try:
                    self._on_msg(json.loads(line))
                except ValueError:
                    pass
        finally:
            self.connected = False
            self.player = {}
            self.dirty = True
            await asyncio.sleep(2)
            asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        while not self.connected:
            try:
                reader, self.writer = await asyncio.open_unix_connection(str(paths.SOCKET_PATH))
                self.connected = True
                self._send({"cmd": "sub", "topics": []})
                asyncio.create_task(self._read(reader))
            except (FileNotFoundError, ConnectionRefusedError):
                await asyncio.sleep(2)

    def _send(self, msg: dict) -> None:
        if self.local_core:
            asyncio.ensure_future(self.local_core.command(self._local_client, msg))
        elif self.writer:
            self.writer.write((json.dumps(msg) + "\n").encode())

    def _on_msg(self, m: dict) -> None:
        t = m.get("t")
        if t == "player":
            if m.get("track", {}).get("id") != self.player.get("track", {}).get("id"):
                self.scroll = 0
            m["_recv"] = time.monotonic()
            self.player = m
        elif t == "lyrics":
            self.lyrics = m
        elif t == "toast":
            self.toast = (m["text"], time.monotonic() + 2.5)
        self.dirty = True

    # ------------------------------------------------------------ timing
    def position(self) -> float:
        p = self.player
        if not p:
            return 0.0
        pos = p.get("pos_ms", 0.0)
        if p.get("playing"):
            pos += (time.monotonic() - p.get("mono", time.monotonic())) * 1000
        length = p.get("track", {}).get("length_ms") or 0
        return min(pos, length) if length else pos

    # ------------------------------------------------------------ rendering
    def frame(self) -> list[str]:
        W, H = self.cols, self.rows
        rows: list[str] = []
        p = self.player
        tr = p.get("track", {}) if p else {}
        pos = self.position()
        length = tr.get("length_ms") or 0

        if not self.compact:
            state = ("▶ PLAYING" if p.get("playing") else "❚❚ PAUSED") if p.get("available") else "◇ OFFLINE"
            left = f"{bgc(CRIMSON)}{fg(PALE)}{BOLD} ◢◤ CRIMSON//LYRICS {RST}"
            right_txt = f"{state}  {fmt_time(pos)} / {fmt_time(length)} "
            gap = W - 20 - width(right_txt)
            rows.append(left + fg(FAINT) + "░" * max(0, gap) + RST + fg(DUSTY) + right_txt + RST)
            if tr.get("title"):
                info = f" {tr['title']}"
                sub = f"  {tr.get('artist', '')}" + (f" · {tr['album']}" if tr.get("album") else "")
                rows.append(fg(PALE) + BOLD + clip(info, W) + RST + fg(MUTED) + clip(sub, max(0, W - width(info))) + RST)
            else:
                rows.append(fg(MUTED) + " no track" + RST)
            bar_w = max(10, W - 2)
            filled = int(bar_w * (pos / length)) if length else 0
            rows.append(" " + fg(ROSE) + "━" * filled + fg(PALE) + ("╸" if filled < bar_w else "") +
                        fg(FAINT) + "─" * max(0, bar_w - filled - 1) + RST)
            rows.append("")

        body_h = H - len(rows) - 2
        rows += self.body(W, body_h, pos)
        while len(rows) < H - 1:
            rows.append("")
        rows = rows[:H - 1]
        rows.append(self.footer(W))
        if self.help:
            rows = self.overlay_help(rows, W, H)
        return rows

    def body(self, W: int, H: int, pos: float) -> list[str]:
        st = self.lyrics.get("status")
        p = self.player
        if not self.connected:
            return self.message(W, H, "◇ CONNECTING TO CRIMSON-CORE ◇", "")
        if not p.get("available"):
            return self.message(W, H, "◇ AWAITING SIGNAL ◇", "Spotify isn't running — open it and press play")
        if st == "loading":
            return self.message(W, H, "▒▒ SEARCHING LYRICS ▒▒", "local .lrc → cache → lrclib.net")
        if st == "ad":
            return self.message(W, H, "▣ ADVERTISEMENT ▣", "")
        if st == "instrumental":
            return self.message(W, H, "♪ INSTRUMENTAL ♪", "")
        if st == "error":
            ly = self.lyrics
            sub = (ly.get("error") or "network error")[:60] + ("  ·  retrying in %ss" % ly["retry_in"] if ly.get("retry_in") else "  ·  press r to retry")
            return self.message(W, H, "✕ LYRICS SERVICE UNREACHABLE", sub)
        if st == "plain":
            return self.plain(W, H)
        if st != "synced" or not self.lyrics.get("lines"):
            return self.message(W, H, "NO SYNCED LYRICS FOUND",
                                f"add an .lrc file to {paths.USER_LYRICS_DIR}".replace(os.path.expanduser("~"), "~"))
        return self.synced(W, H, pos)

    def message(self, W, H, title, sub) -> list[str]:
        out = [""] * max(0, H // 2 - 1)
        out.append(center(fg(PALE) + BOLD + title + RST, W, width(title)))
        if sub:
            out.append(center(fg(MUTED) + clip(sub, W - 4) + RST, W, min(width(sub), W - 4)))
        return out

    def plain(self, W, H) -> list[str]:
        text = (self.lyrics.get("plain") or "").splitlines()
        out = [center(fg(MUTED) + "— unsynced lyrics · j/k to scroll —" + RST, W, 35), ""]
        self.scroll = max(0, min(self.scroll, max(0, len(text) - (H - 2))))
        for line in text[self.scroll:self.scroll + H - 2]:
            out.append(center(fg(DUSTY) + clip(line, W - 4) + RST, W, min(width(line), W - 4)))
        return out

    def synced(self, W, H, pos) -> list[str]:
        lines = self.lyrics["lines"]
        t = pos + self.lyrics.get("offset_ms", 0)
        idx = lrc.line_index(lines, int(t))
        maxw = W - 8
        cur_rows: list[str] = []
        if idx >= 0:
            ln = lines[idx]
            text = ln["text"] or "♪"
            if self.big:
                # kitty text-sizing protocol: draw at 2x scale (occupies two rows)
                txt = clip(text, max(4, maxw // 2))
                pad = " " * max(0, (W - width(txt) * 2) // 2)
                cur_rows = [pad + fg(PALE) + BOLD + f"{ESC}]66;s=2;{txt}{ESC}\\" + RST, "\x00"]
            elif ln.get("w") and text != "♪":
                cur_rows = self.karaoke(ln, t, W, maxw)
            else:
                for wl in textwrap.wrap(text, maxw) or [text]:
                    cur_rows.append(center(fg(PALE) + BOLD + wl + RST, W, width(wl)))
        else:
            cur_rows = [center(fg(DIM) + "· · ·" + RST, W, 5)]

        above = (H - len(cur_rows)) // 2
        below = H - len(cur_rows) - above
        out: list[str] = []
        for k in range(above, 0, -1):
            j = idx - k
            if j < 0:
                out.append("")
                continue
            col = MUTED if k == 1 else DIM if k <= 3 else FAINT
            text = clip(lines[j]["text"] or "♪", maxw)
            out.append(center(fg(col) + text + RST, W, width(text)))
        out += cur_rows
        for k in range(1, below + 1):
            j = idx + k
            if j >= len(lines):
                out.append("")
                continue
            col = DUSTY if k == 1 else MUTED if k <= 3 else DIM
            text = clip(lines[j]["text"] or "♪", maxw)
            out.append(center(fg(col) + text + RST, W, width(text)))
        return out

    def karaoke(self, ln, t, W, maxw) -> list[str]:
        rows, cur, cur_w = [], "", 0
        for w in ln["w"]:
            word = w[1]
            sung = t >= w[0]
            active = sung and (len(w) < 3 or t < w[2])
            col = (fg(PALE) + BOLD) if sung else fg(DUSTY)
            if active:
                col = f"{ESC}[4m" + fg(PALE) + BOLD
            ww = width(word)
            if cur_w + ww > maxw and cur:
                rows.append((cur, cur_w))
                cur, cur_w = "", 0
            cur += col + word + RST
            cur_w += ww
        if cur:
            rows.append((cur, cur_w))
        return [center(r, W, vw) for r, vw in rows]

    def footer(self, W) -> str:
        if self.toast and time.monotonic() < self.toast[1]:
            msg = self.toast[0]
            return center(bgc(CRIMSON) + fg(PALE) + BOLD + f" {msg} " + RST, W, width(msg) + 2)
        ly = self.lyrics
        src = ly.get("source") or "—"
        info = f" {ly.get('status', '')} · {src} · offset {ly.get('offset_ms', 0):+d}ms "
        keys = " ␣ play  n/p skip  ←→ seek  +/- offset  b big  ? help  q quit "
        if width(info) + width(keys) > W:
            keys = " ? help  q quit "
        gap = W - width(info) - width(keys)
        return fg(MUTED) + clip(info, W) + fg(FAINT) + " " * max(0, gap) + fg(DIM) + keys + RST

    def overlay_help(self, rows, W, H) -> list[str]:
        lines = [
            "CRIMSON//LYRICS — KEYS", "",
            "space   play / pause", "n / p   next / previous track", "← / →   seek -5s / +5s",
            "+ / -   lyric offset ±100 ms (saved per track)", "0       reset offset",
            "r       re-fetch lyrics (ignores cache)", "b       big text (kitty text sizing)",
            "c       compact mode", "j / k   scroll unsynced lyrics", "q       quit",
        ]
        bw = max(width(l) for l in lines) + 6
        top = max(0, (H - len(lines) - 2) // 2)
        left = max(0, (W - bw) // 2)
        for i, l in enumerate(["┌" + "─" * (bw - 2) + "┐"] + [f"│  {l}{' ' * (bw - 4 - width(l))}│" for l in lines]
                              + ["└" + "─" * (bw - 2) + "┘"]):
            if top + i < len(rows):
                rows[top + i] = " " * left + bgc(BG) + fg(PALE if i == 1 else DUSTY) + l + RST
        return rows

    def render(self) -> None:
        self.cols, self.rows = shutil.get_terminal_size((80, 24))
        frame = self.frame()
        out = []
        full = len(frame) != len(self.prev_frame)
        for i, line in enumerate(frame):
            if line == "\x00":
                continue  # second row of a 2x-scaled line
            if full or self.prev_frame[i] != line:
                out.append(f"{ESC}[{i + 1};1H{ESC}[2K{line}")
        if out:
            sys.stdout.write(f"{ESC}[?2026h" + "".join(out) + f"{ESC}[?2026l")  # synchronized update
            sys.stdout.flush()
        self.prev_frame = frame

    # ------------------------------------------------------------ input
    def on_key(self, s: str) -> bool:
        keymap = {
            " ": {"cmd": "play_pause"}, "n": {"cmd": "next"}, "p": {"cmd": "prev"},
            f"{ESC}[C": {"cmd": "seek_rel", "ms": 5000}, f"{ESC}[D": {"cmd": "seek_rel", "ms": -5000},
            "+": {"cmd": "offset", "delta": 100}, "=": {"cmd": "offset", "delta": 100},
            "-": {"cmd": "offset", "delta": -100}, "0": {"cmd": "offset", "reset": True},
            "r": {"cmd": "reload_lyrics"},
        }
        if s in ("q", ESC, "\x03"):
            if self.help and s == ESC:
                self.help = False
                return True
            return False
        if s in keymap:
            self._send(keymap[s])
        elif s == "b":
            self.big = not self.big
            self.prev_frame = []
        elif s == "c":
            self.compact = not self.compact
        elif s == "?":
            self.help = not self.help
        elif s in ("j", f"{ESC}[B"):
            self.scroll += 1
        elif s in ("k", f"{ESC}[A"):
            self.scroll = max(0, self.scroll - 1)
        self.dirty = True
        return True

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        quit_ev = asyncio.Event()
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        sys.stdout.write(f"{ESC}[?1049h{ESC}[?25l{ESC}[2J{bgc(BG)}")
        sys.stdout.flush()
        tty.setcbreak(fd)

        def on_stdin():
            data = os.read(fd, 256).decode(errors="ignore")
            i = 0
            while i < len(data):
                # split the chunk into keys: CSI sequences (ESC [ ... final byte) or single chars
                if data[i] == ESC and i + 2 < len(data) + 1 and data[i + 1:i + 2] == "[":
                    j = i + 2
                    while j < len(data) and not ("@" <= data[j] <= "~"):
                        j += 1
                    key, i = data[i:j + 1], j + 1
                else:
                    key, i = data[i], i + 1
                if not self.on_key(key):
                    quit_ev.set()
                    return

        loop.add_reader(fd, on_stdin)
        loop.add_signal_handler(signal.SIGWINCH, lambda: setattr(self, "prev_frame", []))
        loop.add_signal_handler(signal.SIGTERM, quit_ev.set)
        try:
            self.render()
            await self.connect()
            last_key = None
            while not quit_ev.is_set():
                # re-render only when something visible changed (line/word index, second, message)
                pos = self.position()
                key = (int(pos // 1000), self._line_key(pos), self.cols, self.rows,
                       bool(self.toast and time.monotonic() < self.toast[1]))
                if self.dirty or key != last_key:
                    self.render()
                    self.dirty, last_key = False, key
                try:
                    await asyncio.wait_for(quit_ev.wait(), 0.05)
                except asyncio.TimeoutError:
                    pass
        finally:
            loop.remove_reader(fd)
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            sys.stdout.write(f"{RST}{ESC}[2J{ESC}[?25h{ESC}[?1049l")
            sys.stdout.flush()

    def _line_key(self, pos):
        lines = self.lyrics.get("lines") or []
        if not lines:
            return None
        t = int(pos + self.lyrics.get("offset_ms", 0))
        i = lrc.line_index(lines, t)
        if i < 0 or not lines[i].get("w"):
            return i
        return i, sum(1 for w in lines[i]["w"] if t >= w[0])


def main() -> None:
    ap = argparse.ArgumentParser(prog="crimson-lyrics", description="Synchronized Spotify lyrics for Kitty")
    ap.add_argument("--big", action="store_true", help="2x current line (kitty ≥ 0.40 text sizing protocol)")
    ap.add_argument("--compact", action="store_true", help="hide the header")
    ap.add_argument("--embedded", action="store_true", help="don't use the crimson-core service")
    args = ap.parse_args()
    if not sys.stdin.isatty():
        sys.exit("crimson-lyrics needs an interactive terminal")
    try:
        asyncio.run(LyricsTUI(args).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
