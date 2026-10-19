"""crimsonctl - control the Crimson Desktop.

  crimsonctl start | stop | restart | status       dashboard + backend services
  crimsonctl show | hide | toggle                   dashboard visibility (instant, no restart)
  crimsonctl profile crimson|minimal|performance|next [--notify]
  crimsonctl perf low|balanced|high                 animation/performance level
  crimsonctl offset +100 | -100 | reset             lyric timing for the current track
  crimsonctl lyrics                                 open the Kitty lyrics view
  crimsonctl reload-lyrics                          re-fetch lyrics for the current track
  crimsonctl play-pause | next | prev
  crimsonctl doctor                                 check dependencies & environment
  crimsonctl monitors                               show detected monitors
  crimsonctl logs [-f]                              service logs
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from . import client, config, paths

UNITS = ["crimson-core.service", "crimson-dashboard.service"]
PROFILE_ORDER = ["crimson", "minimal", "performance"]
PROFILE_LABEL = {"crimson": "Crimson Music", "minimal": "Minimal Dark", "performance": "Performance"}

C = {"p": "\033[38;2;242;183;197m", "d": "\033[38;2;213;139;159m", "m": "\033[38;2;168;139;152m",
     "r": "\033[38;2;224;108;132m", "g": "\033[38;2;150;190;140m", "0": "\033[0m", "b": "\033[1m"}
if not sys.stdout.isatty():
    C = {k: "" for k in C}


def say(msg: str) -> None:
    print(f"{C['d']}◢◤{C['0']} {msg}")


def systemctl(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=check)


def unit_installed(unit: str) -> bool:
    return systemctl("cat", unit).returncode == 0


def notify(title: str, body: str = "") -> None:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "Crimson Desktop", "-i", "preferences-desktop-theme", title, body],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ui_cmd(**kw) -> bool:
    """Send a ui change to the core; if it isn't running, persist it for the next start."""
    r = client.request({"cmd": "ui", **kw})
    if r is None:
        st = config.JsonState(paths.UI_STATE_FILE)
        for k, v in kw.items():
            if k == "visible" and v == "toggle":
                v = not st.data.get("visible", True)
            st.data[k] = v
        st.save()
    return r is not None


# ---------------------------------------------------------------- services
def start() -> None:
    if not all(unit_installed(u) for u in UNITS):
        say("services not installed - run scripts/install.sh first; starting processes directly")
        client.start_core()
        subprocess.Popen([str(paths.PROJECT_DIR / "bin" / "crimson-dashboard")], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    systemctl("start", *UNITS)
    say("started")


def stop() -> None:
    systemctl("stop", "crimson-dashboard.service", "crimson-core.service")
    say("stopped")


def restart() -> None:
    systemctl("restart", *UNITS)
    say("restarted")


def status() -> None:
    for u in UNITS:
        active = systemctl("is-active", u).stdout.strip() or "unknown"
        enabled = systemctl("is-enabled", u).stdout.strip() or "unknown"
        col = C["g"] if active == "active" else C["r"]
        print(f"  {u:28} {col}{active:9}{C['0']} ({enabled})")
    r = client.request({"cmd": "status"})
    if not r:
        print(f"  {C['m']}core not reachable at {paths.SOCKET_PATH}{C['0']}")
        return
    p = r["player"]
    t = p.get("track", {})
    ui = r["ui"]
    print(f"  player      {('%s (%s)' % (p['player'], p['status'])) if p.get('available') else 'not running'}")
    if t.get("title"):
        pos = int(r["position_ms"] // 1000)
        ln = int((t.get("length_ms") or 0) // 1000)
        print(f"  track       {C['p']}{t['title']}{C['0']} — {t.get('artist')}  [{pos // 60}:{pos % 60:02d}/{ln // 60}:{ln % 60:02d}]")
        print(f"  lyrics      {r['lyrics_status']}  ({r.get('lyrics_source') or '—'}), offset {r['offset_ms']:+d} ms")
    print(f"  profile     {PROFILE_LABEL.get(ui.get('profile'), ui.get('profile'))}  layout={ui.get('layout')}  "
          f"performance={ui.get('performance')} (effective {ui.get('effective_performance')})")
    print(f"  dashboard   {'visible' if ui.get('visible') else 'hidden'}   gamemode={'on' if ui.get('gamemode') else 'off'}"
          f"   clients={r['clients']}")
    print(f"  audio       {'running' if r['audio_running'] else 'idle'}  source={ui.get('audio_source')}"
          + (f"  {C['r']}error: {ui['audio_error']}{C['0']}" if ui.get("audio_error") else ""))


# ---------------------------------------------------------------- profiles
def _kwrite(file: str, group: list[str], key: str, value: str) -> None:
    tool = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if not tool:
        return
    args = [tool, "--file", file]
    for g in group:
        args += ["--group", g]
    subprocess.run(args + ["--key", key, value], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _kread(file: str, group: list[str], key: str, default: str = "") -> str:
    tool = shutil.which("kreadconfig6") or shutil.which("kreadconfig5")
    if not tool:
        return default
    args = [tool, "--file", file]
    for g in group:
        args += ["--group", g]
    r = subprocess.run(args + ["--key", key, "--default", default], capture_output=True, text=True)
    return r.stdout.strip() or default


def _kwin_reconfigure() -> None:
    for q in ("qdbus6", "qdbus-qt6", "qdbus"):
        if shutil.which(q):
            subprocess.run([q, "org.kde.KWin", "/KWin", "reconfigure"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    subprocess.run(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.KWin", "/KWin",
                    "org.kde.KWin.reconfigure"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _kitty_opacity(value: float) -> None:
    conf = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kitty" / "crimson-profile.conf"
    if not conf.parent.exists():
        return
    conf.write_text(f"# written by `crimsonctl profile`\nbackground_opacity {value}\n")
    # kitty re-reads its config on SIGUSR1 (running windows update live)
    r = subprocess.run(["pgrep", "-x", "kitty"], capture_output=True, text=True)
    for pid in r.stdout.split():
        try:
            os.kill(int(pid), signal.SIGUSR1)
        except (ProcessLookupError, PermissionError, ValueError):
            pass


def _desktop_effects(performance: bool) -> None:
    """Performance profile: instant animations + no blur. Previous values are saved and restored."""
    saved = config.JsonState(paths.STATE_DIR / "profile-saved.json")
    if performance:
        if "anim" not in saved.data:
            saved.data["anim"] = _kread("kdeglobals", ["KDE"], "AnimationDurationFactor", "1")
            saved.data["blur"] = _kread("kwinrc", ["Plugins"], "blurEnabled", "true")
            saved.save()
        _kwrite("kdeglobals", ["KDE"], "AnimationDurationFactor", "0")
        _kwrite("kwinrc", ["Plugins"], "blurEnabled", "false")
    elif "anim" in saved.data:
        _kwrite("kdeglobals", ["KDE"], "AnimationDurationFactor", saved.data.pop("anim"))
        _kwrite("kwinrc", ["Plugins"], "blurEnabled", saved.data.pop("blur", "true"))
        saved.save()
    _kwin_reconfigure()


def profile(name: str, do_notify: bool = False) -> None:
    cur = config.JsonState(paths.UI_STATE_FILE).data.get("profile", "crimson")
    if name == "next":
        name = PROFILE_ORDER[(PROFILE_ORDER.index(cur) + 1) % len(PROFILE_ORDER)] if cur in PROFILE_ORDER else "crimson"
    if name not in config.PROFILES:
        sys.exit(f"unknown profile {name!r}; choose from {', '.join(PROFILE_ORDER)}")
    spec = config.PROFILES[name]
    cfg = config.load()
    perf = spec["performance"] or cfg["dashboard"].get("performance", "balanced")
    prev_layout = config.JsonState(paths.UI_STATE_FILE).data.get("layout")
    ui_cmd(profile=name, layout=spec["layout"], performance=perf, visible=True)
    # the core may not be running: make sure ui.json reflects the choice either way
    st = config.JsonState(paths.UI_STATE_FILE)
    st.data.update(profile=name, layout=spec["layout"], performance=perf, visible=True)
    st.save()

    _kitty_opacity(1.0 if name == "performance" else 0.88)
    _desktop_effects(name == "performance")
    if unit_installed("crimson-dashboard.service"):
        if spec["dashboard"]:
            systemctl("enable", "crimson-dashboard.service")
            if prev_layout != spec["layout"]:
                systemctl("restart", "crimson-dashboard.service")
            else:
                systemctl("start", "crimson-dashboard.service")
        else:
            systemctl("disable", "--now", "crimson-dashboard.service")
    say(f"profile: {C['p']}{PROFILE_LABEL[name]}{C['0']}  (layout {spec['layout']}, performance {perf})")
    if do_notify:
        notify(f"Profile: {PROFILE_LABEL[name]}")


# ---------------------------------------------------------------- doctor
def doctor() -> None:
    ok = lambda b: f"{C['g']}✔{C['0']}" if b else f"{C['r']}✘{C['0']}"  # noqa: E731
    warn = f"{C['d']}!{C['0']}"

    def row(state, name, detail=""):
        print(f"  {state} {name:26} {C['m']}{detail}{C['0']}")

    print(f"{C['b']}environment{C['0']}")
    osr = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                osr[k] = v.strip('"')
    except OSError:
        pass
    row(ok(osr.get("ID") in ("nobara", "fedora") or "fedora" in osr.get("ID_LIKE", "")), "distribution", osr.get("PRETTY_NAME", "?"))
    row(ok(os.environ.get("XDG_SESSION_TYPE") == "wayland"), "wayland session", os.environ.get("XDG_SESSION_TYPE", "?"))
    row(ok("KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")), "KDE Plasma", os.environ.get("XDG_CURRENT_DESKTOP", "?"))
    if shutil.which("plasmashell"):
        v = subprocess.run(["plasmashell", "--version"], capture_output=True, text=True).stdout.strip()
        row(ok(True), "plasmashell", v)

    print(f"{C['b']}python{C['0']}")
    row(ok(True), "interpreter", sys.executable + " " + sys.version.split()[0])
    for mod in ("jeepney", "PySide6.QtQuick", "PySide6.QtNetwork", "PIL"):
        try:
            m = __import__(mod)
            row(ok(True), mod, getattr(m, "__version__", ""))
        except ImportError as e:
            row(ok(False) if mod != "PIL" else warn, mod, f"{e} (python3-pillow is only needed by the wallpaper picker)" if mod == "PIL" else str(e))
    try:
        from .dashboard import layer_shell_available
        avail, why = layer_shell_available()
        row(ok(avail) if avail else warn, "layer-shell (dashboard)", "available" if avail else why + " → window mode + KWin rule")
    except ImportError:
        pass

    print(f"{C['b']}tools{C['0']}")
    for tool, why in (("cava", "audio spectrum"), ("pw-dump", "Spotify-only audio capture"), ("kscreen-doctor", "monitor detection"),
                      ("kitty", "terminal"), ("fastfetch", "crimsonfetch"), ("playerctl", "optional, handy for debugging"),
                      ("gamemoded", "GameMode auto performance"), ("notify-send", "profile notifications")):
        path = shutil.which(tool)
        row(ok(bool(path)) if tool in ("cava", "kscreen-doctor", "kitty") else (ok(True) if path else warn), tool, path or f"missing — {why}")
    if shutil.which("cava"):
        v = subprocess.run(["cava", "-v"], capture_output=True, text=True)
        import re
        row(ok(True), "cava version", re.sub(r"\x1b\][^\x07]*\x07|\x1b\[[0-9;]*m", "", v.stdout or v.stderr).strip())

    print(f"{C['b']}runtime{C['0']}")
    r = client.request({"cmd": "status"})
    row(ok(bool(r)), "crimson-core", "reachable" if r else f"not reachable ({paths.SOCKET_PATH})")
    if r:
        p = r["player"]
        row(ok(p.get("available")) if p.get("available") else warn, "spotify (MPRIS)",
            f"{p.get('player')} {p.get('status')}" if p.get("available") else "not running / no MPRIS name")
        ui = r["ui"]
        row(ok(not ui.get("audio_error")) if ui.get("audio_available") else warn, "audio capture",
            ui.get("audio_error") or ("source " + str(ui.get("audio_source"))))
    cfg = config.load()
    try:
        import urllib.request
        from .lyrics import USER_AGENT
        req = urllib.request.Request(cfg["lyrics"]["lrclib_url"].rstrip("/") + "/api/search?q=test",
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            row(ok(resp.status == 200), "LRCLIB reachable", cfg["lyrics"]["lrclib_url"])
    except Exception as e:  # noqa: BLE001
        row(warn, "LRCLIB reachable", f"no ({e}) — local .lrc files still work")
    fonts = subprocess.run(["fc-list", ":family=Jersey 10"], capture_output=True, text=True).stdout.strip() if shutil.which("fc-list") else ""
    row(ok(True) if fonts else warn, "pixel fonts installed", "yes" if fonts else "not system-wide (the dashboard loads its bundled copies anyway)")
    for u in UNITS:
        row(ok(unit_installed(u)), u, systemctl("is-active", u).stdout.strip())


def logs(follow: bool) -> None:
    os.execvp("journalctl", ["journalctl", "--user", "-u", "crimson-core", "-u", "crimson-dashboard", "-n", "120", "--no-hostname"]
              + (["-f"] if follow else []))


def open_lyrics() -> None:
    lyr = str(paths.PROJECT_DIR / "bin" / "crimson-lyrics")
    if sys.stdin.isatty() and os.environ.get("TERM"):
        os.execv(lyr, [lyr])
    if shutil.which("kitty"):
        subprocess.Popen(["kitty", "--title", "crimson-lyrics", "--class", "crimson-lyrics", lyr], start_new_session=True)
    else:
        sys.exit("kitty not found; run crimson-lyrics inside a terminal")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    simple = {"play-pause": "play_pause", "next": "next", "prev": "prev", "reload-lyrics": "reload_lyrics"}
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        restart()
    elif cmd == "status":
        status()
    elif cmd in ("show", "hide", "toggle"):
        ui_cmd(visible={"show": True, "hide": False, "toggle": "toggle"}[cmd])
        say(f"dashboard {cmd}")
    elif cmd == "profile":
        if not rest:
            cur = config.JsonState(paths.UI_STATE_FILE).data.get("profile", "crimson")
            print(f"current: {PROFILE_LABEL.get(cur, cur)}   available: {', '.join(PROFILE_ORDER)}, next")
            return
        profile(rest[0], "--notify" in rest)
    elif cmd == "perf":
        if not rest or rest[0] not in config.PERFORMANCE:
            sys.exit("usage: crimsonctl perf low|balanced|high")
        ui_cmd(performance=rest[0])
        say(f"performance: {rest[0]}")
    elif cmd == "offset":
        if not rest:
            sys.exit("usage: crimsonctl offset +100|-100|reset")
        msg = {"cmd": "offset", "reset": True} if rest[0] == "reset" else {"cmd": "offset", "delta": int(rest[0])}
        r = client.request(msg)
        if not r or not r.get("ok"):
            sys.exit(f"could not change offset: {(r or {}).get('error', 'core not running')}")
        say(f"lyric offset for this track: {r['offset_ms']:+d} ms")
    elif cmd in simple:
        if not client.request({"cmd": simple[cmd]}):
            sys.exit("core not running")
    elif cmd == "lyrics":
        open_lyrics()
    elif cmd == "doctor":
        doctor()
    elif cmd == "monitors":
        os.execvp(sys.executable, [sys.executable, str(paths.PROJECT_DIR / "scripts" / "detect-monitors.py"), *rest])
    elif cmd == "logs":
        logs("-f" in rest)
    else:
        sys.exit(f"unknown command {cmd!r} (see crimsonctl help)")


if __name__ == "__main__":
    main()
