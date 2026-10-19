"""MUSIC — Spotify controls, synced lyrics and the real CAVA spectrum, all via crimson-core."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Static

from ..widgets.chrome import progress, time_pair
from ..widgets.glyphs import (CRIMSON, DUSTY, LINE, MUTED, PALE, ROSE, TEXT, UNICODE, album_art, big_text, fit_big,
                              placeholder_art, spectrum)
from .base import ModuleScreen


class MusicScreen(ModuleScreen):
    MODULE = "music"
    HINTS = "space play  n/p skip  ←/→ seek  +/- offset  0 reset  b big  v viz  r reload"
    FAST = True
    SPECTRUM = True
    # defaults exist before on_mount: the app's timer may tick a screen as soon as it is composed
    _art_key = None
    _art = None
    _viz_mode = "bars"
    _last_line = None
    BINDINGS = [
        Binding("space", "core('play_pause')", "play/pause", show=False),
        Binding("n", "core('next')", "next", show=False),
        Binding("p", "core('prev')", "previous", show=False),
        Binding("right", "seek(5000)", "seek +5s", show=False),
        Binding("left", "seek(-5000)", "seek -5s", show=False),
        Binding("plus,equals_sign", "offset(100)", "offset +", show=False),
        Binding("minus", "offset(-100)", "offset -", show=False),
        Binding("0", "offset_reset", "offset reset", show=False),
        Binding("b", "toggle_big", "big lyrics", show=False),
        Binding("v", "cycle_viz", "visualizer", show=False),
        Binding("r", "core('reload_lyrics')", "reload lyrics", show=False),
    ]

    def compose_body(self) -> ComposeResult:
        with Horizontal(id="music-top"):
            yield Static(id="now", classes="panel")
            yield Static(id="lyrics", classes="panel")
        yield Static(id="viz", classes="panel")

    DEFAULT_CSS = """
    #music-top { height: 1fr; }
    #now { width: 44; height: 1fr; }
    #lyrics { width: 1fr; height: 1fr; content-align: center middle; text-align: center; }
    #viz { height: 9; }
    MusicScreen.narrow #now { display: none; }
    MusicScreen.short #viz { height: 5; }
    """

    def on_mount(self) -> None:
        self.query_one("#now").border_title = "01 // NOW PLAYING"
        self.query_one("#lyrics").border_title = "02 // LYRICS.SYS"
        self.query_one("#viz").border_title = "03 // SPECTRUM"
        self.render_all()

    def layout_for(self, width: int, height: int) -> None:
        self.set_class(width < 90, "narrow")
        self.set_class(height < 28, "short")

    # -------------------------------------------------------------- actions
    def action_core(self, name: str) -> None:
        self.app.core.command(name)

    def action_seek(self, ms: int) -> None:
        self.app.core.command("seek_rel", ms=ms)

    def action_offset(self, delta: int) -> None:
        self.app.core.command("offset", delta=delta)

    def action_offset_reset(self) -> None:
        self.app.core.command("offset", reset=True)

    def action_toggle_big(self) -> None:
        s = self.app.settings
        s.big_lyrics = not s.big_lyrics
        self.app.save_settings()
        self._render_lyrics(force=True)

    def action_cycle_viz(self) -> None:
        self._viz_mode = {"bars": "mirror", "mirror": "off", "off": "bars"}[self._viz_mode]
        self.app.core.want_spectrum(self._viz_mode != "off")
        self._render_viz()

    # -------------------------------------------------------------- render
    def render_all(self) -> None:
        self._render_now()
        self._render_lyrics(force=True)
        self._render_viz()

    def tick(self, fast: bool) -> None:
        self._render_lyrics()
        self._render_viz()
        if not fast:
            self._render_now()

    def on_core(self, kind: str) -> None:
        if kind in ("player", "art", "status"):
            self._render_now()
        if kind in ("lyrics", "player", "status"):
            self._render_lyrics(force=True)

    def _render_now(self) -> None:
        core = self.app.core
        box = self.query_one("#now")
        w = max(20, box.content_size.width)
        t = Text()
        art_w, art_h = min(w, 40), min(w, 40) // 2
        key = (core.art_path, art_w)
        if key != self._art_key:  # render artwork once per track/size
            self._art_key = key
            self._art = album_art(core.art_path, art_w, art_h)
        t.append_text(self._art or placeholder_art(art_w, art_h))
        t.append("\n\n")
        if not core.connected:
            t.append("CRIMSON-CORE OFFLINE\n", style=f"bold {ROSE}")
            t.append("crimsonctl start", style=MUTED)
        elif not core.player.get("available"):
            t.append("AWAITING SIGNAL\n", style=f"bold {DUSTY}")
            t.append("open Spotify and press play", style=MUTED)
        else:
            tr, p = core.track, core.player
            t.append(f"{tr.get('title', '—')}\n", style=f"bold {PALE}")
            t.append(f"{tr.get('artist', '')}\n", style=f"bold {DUSTY}")
            t.append(f"{tr.get('album', '')}\n\n", style=MUTED)
            pos, length = core.position_ms(), tr.get("length_ms") or 0
            t.append_text(progress(pos, length, w - 2))
            t.append(f"\n{'▶ PLAYING' if p.get('playing') else '❚❚ PAUSED'}   {time_pair(pos, length)}\n", style=DUSTY)
            ly = core.lyrics
            t.append(f"\nlyrics  {ly.get('status', '—')} · {(ly.get('source') or '—')[:22]}\n", style=MUTED)
            t.append(f"offset  {ly.get('offset_ms', 0):+d} ms", style=MUTED)
        box.update(t)

    def _render_lyrics(self, force: bool = False) -> None:
        core = self.app.core
        li, wi = core.lyric_index()
        box = self.query_one("#lyrics")
        key = (li, wi, core.lyrics.get("track_id"), core.lyrics.get("status"), self.app.settings.big_lyrics,
               tuple(box.content_size), core.connected, core.player.get("available"), core.lyrics.get("offset_ms"))
        if key == self._last_line and not force:
            return
        self._last_line = key
        w, h = max(20, box.content_size.width), max(5, box.content_size.height)
        ly = core.lyrics
        status = ly.get("status")
        t = Text(justify="center")

        def message(title: str, sub: str = "") -> Text:
            m = Text(justify="center")
            m.append("\n" * max(0, h // 2 - 4))
            m.append_text(big_text(title, DUSTY) if fit_big(title, w) else Text(title, style=f"bold {PALE}"))
            if sub:
                m.append(f"\n\n{sub}", style=MUTED)
            return m

        if not core.connected:
            t = message("OFFLINE", "crimson-core isn't running — start it with: crimsonctl start")
        elif not core.player.get("available"):
            t = message("NO SIGNAL", "Spotify isn't running")
        elif status == "loading":
            t = message("SEARCHING", "local .lrc → cache → lrclib.net")
        elif status == "instrumental":
            t = message("INSTRUMENTAL", core.track.get("artist", ""))
        elif status == "ad":
            t = message("AD")
        elif status == "error":
            t = message("UNREACHABLE", f"{(ly.get('error') or 'network error')[:70]}"
                        + (f" · retrying in {ly['retry_in']}s" if ly.get("retry_in") else " · press r to retry"))
        elif status == "plain":
            text = (ly.get("plain") or "").splitlines()
            t = Text("unsynced lyrics (no timestamps — shown without highlighting)\n\n", style=MUTED, justify="center")
            for line in text[: max(1, h - 3)]:
                t.append(line + "\n", style=TEXT)
        elif status != "synced" or not ly.get("lines"):
            t = message("NO LYRICS", "no synced lyrics found · add an .lrc to ~/.config/crimson-desktop/lyrics/")
        else:
            t = self._synced(ly["lines"], li, wi, w, h)
        box.border_subtitle = (f"{'word' if ly.get('has_words') else 'line'} sync · offset {ly.get('offset_ms', 0):+d}ms"
                               if status == "synced" else "")
        box.update(t)

    def _synced(self, lines: list[dict], li: int, wi: int, w: int, h: int) -> Text:
        big = self.app.settings.big_lyrics
        cur = lines[li] if li >= 0 else None
        cur_text = (cur.get("text") or "♪") if cur else "· · ·"
        out = Text(justify="center")
        cur_block = Text(justify="center")
        if big and cur and UNICODE:
            word = cur["w"][max(0, wi)][1].strip() if cur.get("w") else cur_text
            if fit_big(word, w):
                cur_block.append_text(big_text(word, PALE))
                if cur.get("w"):
                    cur_block.append("\n")
                    cur_block.append_text(self._karaoke(cur, wi))
            else:
                big = False
        if not (big and cur and UNICODE and cur_block.plain):
            cur_block = self._karaoke(cur, wi) if cur and cur.get("w") else Text(cur_text, style=f"bold {PALE}", justify="center")
        cur_rows = cur_block.plain.count("\n") + 1
        above = max(0, (h - cur_rows) // 2)
        below = max(0, h - cur_rows - above)
        for k in range(above, 0, -1):
            j = li - k
            txt = (lines[j].get("text") or "♪") if 0 <= j < len(lines) else ""
            out.append(txt[:w] + "\n", style=MUTED if k == 1 else LINE)
        out.append_text(cur_block)
        for k in range(1, below + 1):
            j = li + k
            txt = (lines[j].get("text") or "♪") if 0 <= j < len(lines) else ""
            out.append("\n" + txt[:w], style=DUSTY if k == 1 else MUTED if k <= 3 else LINE)
        return out

    @staticmethod
    def _karaoke(line: dict, wi: int) -> Text:
        t = Text(justify="center")
        for i, wd in enumerate(line["w"]):
            t.append(wd[1], style=f"bold {PALE}" if i <= wi else "#8f5f6f")
        return t

    def _render_viz(self) -> None:
        box = self.query_one("#viz")
        core = self.app.core
        w, h = max(10, box.content_size.width), max(2, box.content_size.height)
        if self._viz_mode == "off" or not self.app.settings.show_visualizer:
            box.update(Text("visualizer off (v to cycle)", style=MUTED, justify="center"))
            box.border_subtitle = ""
            return
        box.update(spectrum(core.spectrum, w, h, mirror=self._viz_mode == "mirror"))
        src = core.ui.get("audio_source") or "system"
        err = core.ui.get("audio_error")
        box.border_subtitle = (f"CAVA · {'ALL SYSTEM AUDIO' if src == 'system' else 'SPOTIFY ONLY' if src == 'spotify' else src.rsplit('/', 1)[-1][:24]}"
                               f" · {self._viz_mode}" + (f" · {err[:40]}" if err else "")
                               + ("" if core.spectrum else " · waiting for audio"))
