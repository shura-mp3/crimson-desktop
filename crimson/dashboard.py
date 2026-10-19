"""crimson-dashboard: the QML music dashboard for the right-hand monitor.

Display strategy on KDE Plasma (Wayland):
  layer  - wlr-layer-shell via layer-shell-qt (ships with Plasma). Bottom layer: drawn above the
           desktop, below all windows, never focused, pinned to one output. Preferred.
  window - an ordinary frameless window kept below others / off the task bar by a KWin rule.
           Fallback when the layer-shell QML module is unavailable (e.g. pip-installed PySide6
           built against a different Qt than the system's).
Only interactive areas (transport controls, progress bar, art, lyrics panel) accept input; the
rest of the surface is click-through via an input region.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import math
import os
import random
import sys
import time
from pathlib import Path

from . import client, config, paths

log = logging.getLogger("crimson.dashboard")
ASSETS = paths.PROJECT_DIR / "dashboard" / "assets"
QML_DIR = paths.PROJECT_DIR / "dashboard" / "qml"
FONTS_DIR = paths.PROJECT_DIR / "fonts"


def layer_shell_available() -> tuple[bool, str]:
    from PySide6.QtCore import QLibraryInfo
    if not os.environ.get("WAYLAND_DISPLAY"):
        return False, "not a Wayland session"
    plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "wayland-shell-integration"
    if not any("layer-shell" in p.name for p in plugins.glob("*")):
        return False, f"no layer-shell plugin in {plugins} (install layer-shell-qt)"
    qml = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath)) / "org" / "kde" / "layershell" / "qmldir"
    if not qml.exists():
        return False, f"layer-shell-qt QML module missing ({qml})"
    return True, "ok"


def wallpaper_assets(screen_name: str) -> dict:
    """Paths written by scripts/apply-theme (pick-wallpapers), with a bundled fallback."""
    state = config.JsonState(paths.WALLPAPER_STATE).data
    entry = state.get("right") or {}
    if screen_name and state.get("by_output", {}).get(screen_name):
        entry = state["by_output"][screen_name]
    img = entry.get("image")
    blur = entry.get("blur")
    if not (img and Path(img).exists()):
        img = str(paths.PROJECT_DIR / "wallpapers" / "crimson-fallback.jpg")
        blur = str(paths.PROJECT_DIR / "wallpapers" / "crimson-fallback-blur.jpg")
    url = lambda p: ("file://" + p) if p and Path(p).exists() else ""  # noqa: E731
    return {
        "wallpaper": url(img),
        "wallpaperBlur": url(blur),
        "grain": url(str(ASSETS / "grain.png")),
        "scan": url(str(ASSETS / "scanlines.png")),
    }


def make_backend_classes():
    from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
    from PySide6.QtNetwork import QLocalSocket

    class Backend(QObject):
        playerChanged = Signal()
        lyricsChanged = Signal()
        artChanged = Signal()
        uiChanged = Signal()
        sysChanged = Signal()
        spectrumChanged = Signal()
        connectedChanged = Signal()
        toast = Signal(str)

        def __init__(self, bars: int = 48):
            super().__init__()
            self._player: dict = {}
            self._lyrics: dict = {"status": "none", "lines": []}
            self._art = ""
            self._ui: dict = {"visible": True, "perf": config.PERFORMANCE["balanced"]}
            self._sys: dict = {}
            self._spec = [0.0] * bars
            self._peaks = [0.0] * bars
            self._levels = {"bass": 0.0, "mid": 0.0, "high": 0.0, "energy": 0.0}
            self._connected = False
            self._last_frame = 0.0
            self._decay = QTimer(self, interval=33, timeout=self._decay_step)

        # ---- QML-facing properties ----
        player = Property("QVariantMap", lambda s: s._player, notify=playerChanged)
        lyrics = Property("QVariantMap", lambda s: s._lyrics, notify=lyricsChanged)
        art = Property(str, lambda s: s._art, notify=artChanged)
        ui = Property("QVariantMap", lambda s: s._ui, notify=uiChanged)
        sys = Property("QVariantMap", lambda s: s._sys, notify=sysChanged)
        spectrum = Property("QVariantList", lambda s: s._spec, notify=spectrumChanged)
        peaks = Property("QVariantList", lambda s: s._peaks, notify=spectrumChanged)
        levels = Property("QVariantMap", lambda s: s._levels, notify=spectrumChanged)
        connected = Property(bool, lambda s: s._connected, notify=connectedChanged)

        @Slot(str, "QVariant")
        def command(self, name, args=None):
            msg = {"cmd": name}
            if isinstance(args, dict):
                msg.update(args)
            self.send(msg)

        def send(self, msg: dict) -> None:
            pass

        # ---- message handling ----
        def handle(self, m: dict) -> None:
            t = m.pop("t", None)
            if t == "player":
                # convert the core's monotonic anchor into wall-clock ms for QML's Date.now()
                m["anchor_wall"] = time.time() * 1000 - (time.monotonic() - m.get("mono", time.monotonic())) * 1000
                self._player = m
                self.playerChanged.emit()
            elif t == "lyrics":
                self._lyrics = m
                self.lyricsChanged.emit()
            elif t == "art":
                self._art = m.get("path") or ""
                self.artChanged.emit()
            elif t == "ui":
                self._ui = m
                self.uiChanged.emit()
            elif t == "sys":
                self._sys = m
                self.sysChanged.emit()
            elif t == "spec":
                self._frame([b / 255 for b in m.get("b", [])])
            elif t == "toast":
                self.toast.emit(m.get("text", ""))

        def _frame(self, vals: list[float]) -> None:
            if len(vals) != len(self._spec):
                self._spec = [0.0] * len(vals)
                self._peaks = [0.0] * len(vals)
            # fast attack, smooth release; falling peak caps
            self._spec = [max(v, o * 0.80) for v, o in zip(vals, self._spec)]
            self._peaks = [max(v, p - 0.012) for v, p in zip(self._spec, self._peaks)]
            n = len(self._spec)
            mean = lambda a: sum(a) / max(1, len(a))  # noqa: E731
            b, mid = max(1, n // 8), max(2, n * 5 // 12)
            self._levels = {
                "bass": min(1.0, mean(self._spec[:b]) * 1.1),
                "mid": min(1.0, mean(self._spec[b:mid]) * 1.4),
                "high": min(1.0, mean(self._spec[mid:]) * 2.2),
                "energy": min(1.0, mean(self._spec) * 1.6),
            }
            self._last_frame = time.monotonic()
            if not self._decay.isActive():
                self._decay.start()
            self.spectrumChanged.emit()

        def _decay_step(self) -> None:
            if time.monotonic() - self._last_frame < 0.12:
                return
            if max(self._spec + self._peaks, default=0) < 0.01:
                self._spec = [0.0] * len(self._spec)
                self._peaks = [0.0] * len(self._peaks)
                self._levels = {k: 0.0 for k in self._levels}
                self._decay.stop()
                self.spectrumChanged.emit()
                return
            self._spec = [v * 0.82 for v in self._spec]
            self._peaks = [max(0.0, p - 0.02) for p in self._peaks]
            self._levels = {k: v * 0.82 for k, v in self._levels.items()}
            self.spectrumChanged.emit()

    class SocketBackend(Backend):
        def __init__(self):
            super().__init__()
            self.sock = QLocalSocket(self)
            self.sock.connected.connect(self._on_connected)
            self.sock.disconnected.connect(self._on_disconnected)
            self.sock.readyRead.connect(self._on_ready)
            self.sock.errorOccurred.connect(lambda _e: self._on_disconnected())
            self._buf = b""
            self._tried_start = False
            self._retry = QTimer(self, interval=2000, timeout=self._connect)
            self._retry.start()
            self._connect()

        def _connect(self) -> None:
            if self.sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                return
            if not paths.SOCKET_PATH.exists() and not self._tried_start:
                self._tried_start = True
                log.info("crimson-core not running - starting it")
                client.start_core()
            self.sock.connectToServer(str(paths.SOCKET_PATH))

        def _on_connected(self) -> None:
            log.info("connected to crimson-core")
            self._connected = True
            self.connectedChanged.emit()
            self.send({"cmd": "sub", "topics": ["spec", "sys"]})

        def _on_disconnected(self) -> None:
            if self._connected:
                log.warning("lost crimson-core; reconnecting")
                self._connected = False
                self._player = {}
                self.connectedChanged.emit()
                self.playerChanged.emit()

        def _on_ready(self) -> None:
            self._buf += bytes(self.sock.readAll())
            *lines, self._buf = self._buf.split(b"\n")
            for line in lines:
                try:
                    self.handle(json.loads(line))
                except (ValueError, KeyError) as e:
                    log.debug("bad message: %s", e)

        def send(self, msg: dict) -> None:
            if self.sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
                self.sock.write((json.dumps(msg) + "\n").encode())

    class DemoBackend(Backend):
        """Synthetic data for previews / screenshots only (never used in normal operation)."""

        LRC = """[00:00.50]Can you hear the signal
[00:04.00]<00:04.00>You <00:04.60>could <00:05.20>be <00:05.80>everything <00:07.00>
[00:08.00]Come back to me
[00:11.00]Am I sinking or am I swimming
[00:15.00]Is it love or is it noise
[00:19.00]Or can I just be myself?
[00:24.00]Everything, everything
"""

        def __init__(self, start_ms: int = 5900, art: str = "", lyrics_status: str = "synced", display: str = "auto"):
            super().__init__()
            from . import lrc
            self.t0 = time.time() * 1000 - start_ms
            parsed = lrc.parse(self.LRC)
            self._lyrics = {"status": lyrics_status, "source": "demo", "lines": parsed["lines"] if lyrics_status == "synced" else [],
                            "has_words": parsed["has_words"], "offset_ms": 0, "lrc_offset": 0}
            self._art = art
            perf = config.PERFORMANCE["balanced"]
            self._ui = {"visible": True, "perf": perf, "effective_performance": "balanced", "audio_available": True,
                        "audio_source": "system", "display_mode": display, "ui_cfg": config.DEFAULTS["ui"], "demo": True}
            self._player = {"available": True, "player": "spotify", "status": "Playing", "playing": True,
                            "track": {"id": "demo", "title": "Everything You Are", "artist": "Crimson Test",
                                      "album": "Signal Lost", "length_ms": 30000, "art_url": ""},
                            "pos_ms": start_ms, "anchor_wall": time.time() * 1000}
            self._sys = {"user": "rune", "host": "nobara", "os": "Nobara Linux 42 (KDE Plasma)", "kernel": "6.16.4-201.nobara.fc42.x86_64",
                         "desktop": "KDE", "session": "wayland", "uptime_s": 11650, "packages": "2214 (rpm), 31 (flatpak)",
                         "cpu_pct": 23, "cpu_temp": 54, "gpu_pct": 41, "gpu_temp": 61, "gpu": "Radeon RX 7800 XT",
                         "mem_used": 9830, "mem_total": 31890, "cpu": "AMD Ryzen 7 7800X3D"}
            self._ph = 0.0
            self._timer = QTimer(self, interval=33, timeout=self._tick)
            self._timer.start()

        def _tick(self) -> None:
            self._ph += 0.033
            n = len(self._spec)
            beat = max(0.0, math.sin(self._ph * 7.5)) ** 6
            vals = []
            for i in range(n):
                f = i / n
                base = (1 - f) ** 1.4 * (0.55 + 0.45 * beat) + 0.25 * math.sin(self._ph * 3 + i * 0.5) ** 2 * (1 - f * 0.6)
                vals.append(max(0.0, min(1.0, base * (0.75 + random.random() * 0.25))))
            self._frame(vals)

        def send(self, msg: dict) -> None:
            log.info("demo command: %s", msg)

    return Backend, SocketBackend, DemoBackend


def pick_screen(app, want: str):
    screens = app.screens()
    for s in screens:
        g = s.geometry()
        log.info("screen %s %dx%d+%d+%d scale=%.2f", s.name(), g.width(), g.height(), g.x(), g.y(), s.devicePixelRatio())
    if want and want != "auto":
        for s in screens:
            if s.name() == want:
                return s
        log.warning("configured monitor %r not found; using the right-most screen", want)
    return max(screens, key=lambda s: (s.geometry().x(), s.geometry().y()))


def main() -> None:
    ap = argparse.ArgumentParser(description="Crimson music dashboard")
    ap.add_argument("--mode", choices=["auto", "layer", "window"])
    ap.add_argument("--layout", choices=["full", "minimal"])
    ap.add_argument("--monitor", help="connector name, e.g. DP-2 (default: config / right-most)")
    ap.add_argument("--demo", action="store_true", help="synthetic data, no crimson-core needed")
    ap.add_argument("--demo-state", default="synced", help="demo lyrics status: synced|none|loading|instrumental")
    ap.add_argument("--demo-pos", type=int, default=5900)
    ap.add_argument("--demo-display", default="auto", help="demo lyric display mode: auto|line|word")
    ap.add_argument("--demo-art", default="")
    ap.add_argument("--size", help="window size WxH (testing)")
    ap.add_argument("--screenshot", help="render, save PNG to this path and exit")
    ap.add_argument("--screenshot-delay", type=int, default=2500)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = config.load()
    paths.ensure_dirs()
    if not (args.demo or args.screenshot):
        lock = open(paths.RUNTIME_DIR / "dashboard.lock", "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit("crimson-dashboard is already running")

    ui_state = config.JsonState(paths.UI_STATE_FILE).data
    layout = args.layout or ui_state.get("layout") or cfg["dashboard"].get("layout", "full")
    mode = args.mode or cfg["dashboard"].get("mode", "auto")
    if args.screenshot or args.size:
        mode = "window"
    if mode in ("auto", "layer"):
        ok, why = layer_shell_available()
        if ok:
            mode = "layer"
        else:
            log.warning("layer-shell unavailable (%s); using a KWin-ruled window", why)
            mode = "window"
    if mode == "layer":
        os.environ["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"
    log.info("display mode: %s, layout: %s", mode, layout)

    from PySide6.QtCore import QRect, QTimer
    from PySide6.QtGui import QFontDatabase, QGuiApplication, QRegion
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow  # noqa: F401 - lets PySide type the root as QQuickWindow

    QGuiApplication.setDesktopFileName("crimson-dashboard")
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("crimson-dashboard")
    app.setQuitOnLastWindowClosed(False)
    for f in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))

    _, SocketBackend, DemoBackend = make_backend_classes()
    backend = DemoBackend(args.demo_pos, args.demo_art, args.demo_state, args.demo_display) if args.demo else SocketBackend()

    screen = pick_screen(app, args.monitor or cfg["dashboard"].get("monitor", "auto"))
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    ctx = engine.rootContext()
    ctx.setContextProperty("hostBackend", backend)
    ctx.setContextProperty("hostAssets", wallpaper_assets(screen.name()))
    ctx.setContextProperty("hostLayout", layout)
    engine.load(str(QML_DIR / ("LayerMain.qml" if mode == "layer" else "WindowMain.qml")))
    if not engine.rootObjects():
        if mode == "layer":
            log.error("layer-shell QML host failed to load; restarting in window mode")
            os.execv(sys.executable, [sys.executable, "-m", "crimson.dashboard", "--mode", "window", *sys.argv[1:]])
        sys.exit("failed to load the dashboard QML")
    win = engine.rootObjects()[0]

    # geometry
    g = screen.geometry()
    if args.size:
        w, h = (int(x) for x in args.size.lower().split("x"))
        win.resize(w, h)
    elif layout == "minimal":
        s = max(0.8, min(g.width() / 1920, g.height() / 1080))
        margin = 18 * s if mode == "layer" else 0
        win.resize(int(480 * s + 2 * margin), int(170 * s + 2 * margin))
    else:
        win.setScreen(screen)
        win.setGeometry(g)
    win.setScreen(screen)

    # input region: clicks only on interactive tiles, the rest falls through to the desktop
    def update_mask():
        rects = win.interactiveRects() or []
        region = QRegion()
        for r in rects:
            r = r.toVariant() if hasattr(r, "toVariant") else r
            region = region.united(QRect(int(r["x"]), int(r["y"]), int(r["w"]), int(r["h"])))
        win.setMask(region if not region.isEmpty() else QRegion(0, 0, 1, 1))

    if not args.screenshot:
        win.maskInvalidated.connect(update_mask)

    # hide/show without restarting (crimsonctl hide/show/toggle, GameMode "hide")
    def on_ui():
        visible = backend.ui.get("visible", True)
        if visible and not win.isVisible():
            win.show()
        elif not visible and win.isVisible():
            QTimer.singleShot(350, lambda: (not backend.ui.get("visible", True)) and win.hide())

    backend.uiChanged.connect(on_ui)

    # monitor hot-plug: restart (systemd brings us back) if the target screen changed
    def screens_changed(*_):
        new = pick_screen(app, args.monitor or cfg["dashboard"].get("monitor", "auto"))
        if new is not screen:
            log.info("monitor layout changed; restarting dashboard")
            app.exit(75)
    app.screenAdded.connect(screens_changed)
    app.screenRemoved.connect(screens_changed)

    win.show()
    if args.screenshot:
        def grab():
            try:
                img = win.grabWindow()
                img.save(args.screenshot)
                log.info("saved %s (%dx%d)", args.screenshot, img.width(), img.height())
            finally:
                app.exit(0)
        QTimer.singleShot(args.screenshot_delay, grab)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
