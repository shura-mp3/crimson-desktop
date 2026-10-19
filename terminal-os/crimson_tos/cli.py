"""`crimson` command-line entry point."""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import __version__


def doctor() -> int:
    from crimson import client, paths

    from .services import konsole, settings as settings_svc
    from .services.metrics import Metrics

    tty = sys.stdout.isatty()
    c = lambda code, s: f"\033[{code}m{s}\033[0m" if tty else s  # noqa: E731
    ok = lambda b: c("38;2;150;190;140", "✔") if b else c("38;2;224;108;132", "✘")  # noqa: E731
    warn = c("38;2;213;139;159", "!")
    bad = 0

    def row(state, name, detail=""):
        print(f"  {state} {name:24} {c('38;2;168;139;152', detail)}")

    print(c("1", "Crimson Terminal OS doctor"))
    row(ok(sys.version_info >= (3, 10)), "python", sys.version.split()[0] + "  " + sys.executable)
    for mod in ("textual", "rich", "psutil"):
        try:
            __import__(mod)
            from importlib.metadata import PackageNotFoundError, version
            try:
                v = version(mod)
            except PackageNotFoundError:
                v = ""
            row(ok(True), mod, v)
        except ImportError as e:
            row(ok(False), mod, str(e))
            bad += 1
    try:
        import PIL
        row(ok(True), "pillow (album art)", PIL.__version__)
    except ImportError:
        row(warn, "pillow (album art)", "missing — artwork falls back to a pattern")
    term, colorterm = os.environ.get("TERM", "?"), os.environ.get("COLORTERM", "")
    row(ok(colorterm in ("truecolor", "24bit")) if colorterm else warn, "terminal colours", f"TERM={term} COLORTERM={colorterm or '(unset)'}")
    enc = (sys.stdout.encoding or "?").lower()
    row(ok("utf" in enc) if "utf" in enc else warn, "unicode", enc + ("" if "utf" in enc else " — ASCII fallback glyphs"))
    cols, lines = shutil.get_terminal_size((0, 0))
    row(ok(cols >= 80 and lines >= 24) if cols else warn, "terminal size", f"{cols}×{lines} (best ≥ 120×34; works down to 60×20)")
    st = konsole.status()
    row(ok(st["konsole"] not in ("not installed",)), "konsole", st["konsole"])
    row(ok(True), "konsole default profile", st["default_profile"])
    row(ok(st["crimson_profile"]) if st["crimson_profile"] else warn, "Crimson OS profile", "installed" if st["crimson_profile"] else "not installed (crimson-terminal-os install)")
    row(ok(True), "auto-start", "ON" if st["autostart"] else "off" + (" (flag file)" if st["autostart_flag_disabled"] else ""))
    r = client.request({"cmd": "status"}, timeout=2)
    row(ok(bool(r)) if r else warn, "crimson-core", "reachable — music/lyrics/visualizer live" if r else f"not running ({paths.SOCKET_PATH}) — start: crimsonctl start")
    _, problems = settings_svc.load()
    row(ok(not problems) if not problems else warn, "settings", "; ".join(problems) or str(settings_svc.SETTINGS_FILE))
    m = Metrics()
    s = m.sample()
    row(ok(True), "cpu", f"{m.static['cpu']} · temp {'n/a' if s.cpu_temp is None else f'{s.cpu_temp:.0f}°C'}")
    row(ok(s.gpu.vendor != "unknown") if s.gpu.vendor != "unknown" else warn, "gpu metrics", f"{s.gpu.vendor} via {s.gpu.source}" if s.gpu.source else "none available")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="crimson", description="Crimson Terminal OS — cyberpunk command center for Konsole.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="keys:  1-6 modules · / palette · ? help · Ctrl+S shell · Ctrl+Q quit to your shell\n"
               "auto-start:  crimson-autostart on|off|status · bypass once: CRIMSON_NO_AUTOSTART=1 konsole\n"
               "docs:  docs/TERMINAL-OS.md (in the Crimson Desktop folder)")
    ap.add_argument("--version", action="version", version=f"Crimson Terminal OS {__version__}")
    ap.add_argument("--doctor", action="store_true", help="check dependencies, terminal and integration, then exit")
    ap.add_argument("--no-animation", action="store_true", help="skip the startup animation")
    ap.add_argument("--safe-mode", action="store_true", help="don't connect to / start crimson-core (no music features)")
    ap.add_argument("--module", choices=["home", "music", "monitor", "files", "commands", "theme"], help="start in this module")
    ap.add_argument("--from-konsole", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.doctor:
        return doctor()
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print("crimson: needs an interactive terminal", file=sys.stderr)
        return 2
    try:
        from .app import CrimsonApp
    except ImportError as e:  # broken/missing venv: say so plainly instead of a traceback wall
        _log(f"import failed: {e!r}")
        print(f"crimson: can't start — {e}. Repair with: bash terminal-os/scripts/install.sh", file=sys.stderr)
        return 3
    app = CrimsonApp(animation=not args.no_animation, safe_mode=args.safe_mode, module=args.module)
    app.run()
    exc = getattr(app, "_exception", None)
    if exc is not None or app.return_code:
        import traceback
        detail = "".join(traceback.format_exception(exc)) if exc is not None else ""
        _log(f"exited with code {app.return_code}{' (from Konsole)' if args.from_konsole else ''}\n{detail}")
    return app.return_code or 0


def _log(message: str) -> None:
    """Append to ~/.local/state/crimson-desktop/terminal-os.log (kept under ~256 KB)."""
    import datetime as dt
    from pathlib import Path

    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "crimson-desktop"
    log = state / "terminal-os.log"
    try:
        state.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > 256_000:
            log.replace(log.with_suffix(".log.1"))
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%F %T} v{__version__} {message.rstrip()}\n")
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
