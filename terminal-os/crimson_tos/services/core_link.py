"""Async client for crimson-core (the existing Crimson Desktop backend).

Reuses the core's unix-socket JSON protocol: player / lyrics / art / ui / toast / spec messages,
and commands (play_pause, next, prev, seek_rel, offset, reload_lyrics, ui). Spotify itself is
reached through the core's MPRIS watcher, so there is exactly one Spotify backend on the system.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Callable

from crimson import client as core_client
from crimson import lrc, paths


class CoreLink:
    def __init__(self, on_update: Callable[[str], None], start_core: bool = True):
        self.on_update = on_update
        self.start_core = start_core
        self.connected = False
        self.player: dict = {}
        self.lyrics: dict = {"status": "none", "lines": []}
        self.ui: dict = {}
        self.art_path = ""
        self.spectrum: list[float] = []
        self.toast = ""
        self._writer: asyncio.StreamWriter | None = None
        self._topics: set[str] = set()
        self._task: asyncio.Task | None = None
        self._tried_start = False

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._writer:
            self._writer.close()

    async def _run(self) -> None:
        delay = 1.0
        while True:
            try:
                reader, self._writer = await asyncio.open_unix_connection(str(paths.SOCKET_PATH))
            except OSError:
                if self.start_core and not self._tried_start:
                    self._tried_start = True
                    await asyncio.get_running_loop().run_in_executor(None, core_client.start_core)
                    await asyncio.sleep(1.0)
                    continue
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15)
                continue
            delay = 1.0
            self.connected = True
            self._send({"cmd": "sub", "topics": sorted(self._topics)})
            self.on_update("status")
            try:
                while line := await reader.readline():
                    try:
                        self._handle(json.loads(line))
                    except (ValueError, KeyError):
                        continue
            except (ConnectionError, OSError):
                pass
            self.connected = False
            self.player = {}
            self._writer = None
            self.on_update("status")
            await asyncio.sleep(1.0)

    def _handle(self, m: dict) -> None:
        t = m.pop("t", None)
        if t == "player":
            m["_recv_mono"] = time.monotonic()
            self.player = m
        elif t == "lyrics":
            self.lyrics = m
        elif t == "ui":
            self.ui = m
        elif t == "art":
            self.art_path = m.get("path") or ""
        elif t == "spec":
            self.spectrum = [b / 255 for b in m.get("b", [])]
        elif t == "toast":
            self.toast = m.get("text", "")
        else:
            return
        self.on_update(t)

    # ---------------------------------------------------------------- api
    def _send(self, msg: dict) -> None:
        if self._writer is not None:
            try:
                self._writer.write((json.dumps(msg) + "\n").encode())
            except (ConnectionError, RuntimeError):
                pass

    def command(self, name: str, **args) -> None:
        self._send({"cmd": name, **args})

    def want_spectrum(self, on: bool) -> None:
        """CAVA in the core only runs while a client subscribes AND music plays: subscribe only while visible."""
        changed = ("spec" in self._topics) != on
        if on:
            self._topics.add("spec")
        else:
            self._topics.discard("spec")
            self.spectrum = []
        if changed:
            self._send({"cmd": "sub", "topics": sorted(self._topics)})

    # ---------------------------------------------------------------- derived
    @property
    def track(self) -> dict:
        return self.player.get("track") or {}

    def position_ms(self) -> float:
        p = self.player
        if not p:
            return 0.0
        pos = float(p.get("pos_ms", 0.0))
        if p.get("playing"):
            pos += (time.monotonic() - p.get("mono", time.monotonic())) * 1000
        length = self.track.get("length_ms") or 0
        return min(pos, length) if length else pos

    def lyric_index(self) -> tuple[int, int]:
        """(line index, word index) at the current position, honouring the shared offsets."""
        lines = self.lyrics.get("lines") or []
        if not lines:
            return -1, -1
        t = int(self.position_ms() + self.lyrics.get("offset_ms", 0))
        i = lrc.line_index(lines, t)
        if i < 0 or not lines[i].get("w"):
            return i, -1
        return i, sum(1 for w in lines[i]["w"] if t >= w[0]) - 1

    @property
    def performance(self) -> str:
        return self.ui.get("effective_performance") or "balanced"
