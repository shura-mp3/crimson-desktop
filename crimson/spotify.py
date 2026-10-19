"""Crimson Spotify — Spicetify integration manager (`crimsonctl spotify ...`).

  inspect    read-only report of Spotify / Spicetify / project state  → spicetify/docs/INSPECTION.md
  install    back up, install the Crimson theme + app + Full App Display, apply (idempotent)
  enable     same as install (re-enables after `disable`)
  disable    switch Spotify back to your previous theme/extensions, keep Spicetify
  update     copy changed project theme/app files and re-apply only if something changed
  restore    restore the Spicetify configuration from the backup (and stock Spotify if it was stock)
  status     short state summary
  doctor     inspect + status + problem hints
  verify     compare the live state with the expected integration state (exit 1 on mismatch)

Rules followed: nothing privileged without asking; Spotify is never reinstalled, downgraded or
switched to another package format; no remote scripts are executed (Spicetify comes from its
official GitHub release tarball, checksum-verified when GitHub publishes a digest).
"""

from __future__ import annotations

import configparser
import datetime as dt
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

from . import client, config, paths

PROJ = paths.PROJECT_DIR
SRC_THEME = PROJ / "spicetify" / "theme" / "Crimson"
SRC_APP = PROJ / "spicetify" / "apps" / "crimson"
INSPECTION = PROJ / "spicetify" / "docs" / "INSPECTION.md"
BACKUPS = PROJ / "backups" / "spicetify"
STATE = paths.STATE_DIR / "spotify-integration.json"
THEME = "Crimson"
APP = "crimson"
EXTENSIONS = ["fullAppDisplay.js"]  # built into Spicetify (spicetify/cli, LGPL-2.1)
MARKER = ".crimson-desktop"         # marks theme/app folders this project owns
HOME = Path.home()
XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
XDG_STATE = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local" / "state")
FLATPAK_ID = "com.spotify.Client"
FLATPAK_TAIL = "app/com.spotify.Client/x86_64/stable/active/files/extra/share/spotify"
CANDIDATES = [  # same list Spicetify itself searches (src/utils/config.go, linuxApp)
    "/opt/spotify", "/opt/spotify/spotify-client", "/usr/share/spotify", "/usr/libexec/spotify",
    "/usr/share/spotify-client", f"/var/lib/flatpak/{FLATPAK_TAIL}", f"{HOME}/.local/share/flatpak/{FLATPAK_TAIL}",
    f"{HOME}/.local/share/spotify-launcher/install/usr/share/spotify",
]

TTY = sys.stdout.isatty()
P, D, M, R, G, Z, B = (("\033[38;2;242;183;197m", "\033[38;2;213;139;159m", "\033[38;2;168;139;152m",
                        "\033[38;2;224;108;132m", "\033[38;2;150;190;140m", "\033[0m", "\033[1m") if TTY else ("",) * 7)


def say(m): print(f"{D}◢◤{Z} {m}")
def ok(m): print(f"  {G}✔{Z} {m}")
def warn(m): print(f"  {D}!{Z} {m}")
def bad(m): print(f"  {R}✘{Z} {m}")
def hdr(m): print(f"\n{B}{P}── {m} {'─' * max(2, 58 - len(m))}{Z}")


def ask(q: str, default: bool = False, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return default
    a = input(f"  {P}?{Z} {q} {'[Y/n]' if default else '[y/N]'} ").strip().lower()
    return default if not a else a.startswith("y")


def run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree_hash(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(x for x in d.rglob("*") if x.is_file() and x.name != MARKER):
        h.update(str(f.relative_to(d)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


# ════════════════════════════════════════════════════════════════════ detection
def prefs_version(prefs: Path) -> str:
    """Spotify version as Spicetify reads it (prefs key app.last-launched-version). Reads only that key."""
    try:
        for line in prefs.read_text(errors="replace").splitlines():
            if line.startswith("app.last-launched-version="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def apps_state(app_dir: Path) -> str:
    """Spicetify's own classification (src/status/spotify): stock / applied / mixed / invalid."""
    apps = app_dir / "Apps"
    try:
        entries = list(apps.iterdir())
    except OSError:
        return "unreadable"
    spa = sum(1 for e in entries if e.is_file() and e.name.endswith(".spa"))
    dirs = sum(1 for e in entries if e.is_dir())
    return "mixed" if spa and dirs else "stock" if spa else "applied" if dirs else "invalid"


def writable_tree(app_dir: Path) -> bool:
    apps = app_dir / "Apps"
    if not (os.access(app_dir, os.W_OK) and os.access(apps, os.W_OK)):
        return False
    return all(os.access(p, os.W_OK) for p in apps.iterdir())


def detect_spotify() -> list[dict]:
    found: dict[str, dict] = {}

    def add(path: str, method: str, prefs: Path, version: str = "", extra: str = ""):
        p = Path(path)
        if not ((p / "Apps").is_dir() and (p / "spotify").exists()):
            return
        key = str(p.resolve())
        if key in found:
            return
        st = p.stat()
        found[key] = {
            "method": method, "path": str(p), "prefs": str(prefs) if prefs.exists() else "",
            "prefs_expected": str(prefs), "version": version or prefs_version(prefs),
            "owner": "you" if st.st_uid == os.getuid() else ("root" if st.st_uid == 0 else str(st.st_uid)),
            "writable": writable_tree(p), "state": apps_state(p), "extra": extra,
        }

    flatpak_prefs = HOME / ".var" / "app" / FLATPAK_ID / "config" / "spotify" / "prefs"
    native_prefs = XDG_CONFIG / "spotify" / "prefs"
    if shutil.which("flatpak"):
        rc, out = run(["flatpak", "list", "--app", "--columns=application,version,installation"])
        for line in out.splitlines() if rc == 0 else []:
            cols = line.split("\t")
            if cols and cols[0] == FLATPAK_ID:
                inst = cols[2] if len(cols) > 2 else "system"
                base = f"{HOME}/.local/share/flatpak" if inst == "user" else "/var/lib/flatpak"
                add(f"{base}/{FLATPAK_TAIL}", f"flatpak-{inst}", flatpak_prefs, cols[1] if len(cols) > 1 else "")
    if shutil.which("rpm"):
        rc, out = run(["rpm", "-qa", "--qf", "%{NAME} %{VERSION}-%{RELEASE}\n"])
        for line in out.splitlines() if rc == 0 else []:
            name, _, ver = line.partition(" ")
            if "spotify" in name.lower() and not name.startswith("lpf-"):
                rc2, files = run(["rpm", "-ql", name])
                for f in files.splitlines():
                    if f.endswith("/Apps"):
                        add(str(Path(f).parent), "rpm", native_prefs, extra=f"package {name} {ver}")
    if shutil.which("snap"):
        rc, out = run(["snap", "list", "spotify"])
        if rc == 0:
            found["snap"] = {"method": "snap", "path": "/snap/spotify/current/usr/share/spotify", "prefs": "",
                             "prefs_expected": "", "version": "", "owner": "root", "writable": False,
                             "state": "read-only", "extra": "snap packages are read-only: not supported by Spicetify"}
    for c in CANDIDATES:
        add(c, "other", flatpak_prefs if "flatpak" in c else native_prefs)
    return list(found.values())


def running_spotify() -> list[str]:
    rc, out = run(["pgrep", "-a", "-f", "spotify"])
    procs = []
    for line in out.splitlines() if rc == 0 else []:
        if "crimson" in line or "pgrep" in line:
            continue
        procs.append(re.sub(r"(--[a-z-]*token[^ ]*|--uri=\S+)", "<redacted>", line)[:160])
    return procs


def spicetify_bin() -> str | None:
    return shutil.which("spicetify") or next(
        (str(p) for p in (HOME / ".spicetify" / "spicetify", HOME / ".local" / "bin" / "spicetify") if p.exists()), None)


def spicetify_paths() -> dict:
    cfg_dir = XDG_CONFIG / "spicetify"
    return {
        "config_dir": cfg_dir,
        "config_file": cfg_dir / "config-xpui.ini",
        "backup_dirs": [XDG_STATE / "spicetify" / "Backup", cfg_dir / "Backup"],  # new / older versions
    }


def read_ini(path: Path) -> configparser.ConfigParser | None:
    if not path.exists():
        return None
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read(path)
    except configparser.Error:
        return None
    return cp


def detect_spicetify() -> dict:
    sp = spicetify_paths()
    exe = spicetify_bin()
    info = {"binary": exe, "version": "", "config_file": str(sp["config_file"]), "config": {},
            "themes": [], "extensions_dir": [], "custom_apps_dir": [], "backup": "none", "backup_dir": ""}
    if exe:
        rc, out = run([exe, "-v"])
        info["version"] = out.splitlines()[-1].strip() if rc == 0 and out else "unknown"
    ini = read_ini(sp["config_file"])
    if ini:
        info["config"] = {s: dict(ini[s]) for s in ini.sections()}
    for sub, k in (("Themes", "themes"), ("Extensions", "extensions_dir"), ("CustomApps", "custom_apps_dir")):
        d = sp["config_dir"] / sub
        if d.is_dir():
            info[k] = sorted(x.name for x in d.iterdir())
    for bd in sp["backup_dirs"]:
        if bd.is_dir() and any(x.suffix == ".spa" for x in bd.iterdir()):
            info["backup"], info["backup_dir"] = "present", str(bd)
            break
    return info


def setting(info: dict, section: str, key: str, default: str = "") -> str:
    return info.get("config", {}).get(section, {}).get(key, default)


# ════════════════════════════════════════════════════════════════════ inspect
def inspect(write: bool = True) -> dict:
    hdr("inspection (read-only)")
    osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', Path("/etc/os-release").read_text(), re.M)) if Path("/etc/os-release").exists() else {}
    report = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "os": osr.get("PRETTY_NAME", platform.platform()),
        "kernel": platform.release(),
        "session": f"{os.environ.get('XDG_SESSION_TYPE', '?')} / {os.environ.get('XDG_CURRENT_DESKTOP', '?')}",
        "spotify": detect_spotify(),
        "spotify_running": running_spotify(),
        "spicetify": detect_spicetify(),
        "project_git": run(["git", "-C", str(PROJ), "status", "--short", "--branch"])[1],
        "core": None,
    }
    r = client.request({"cmd": "status"}, timeout=2)
    if r:
        report["core"] = {"bridge": r.get("bridge"), "lyrics": r.get("lyrics_status"), "player": r["player"].get("player")}
    sp = report["spicetify"]

    print(f"  os           {report['os']}  ({report['session']})")
    if not report["spotify"]:
        bad("no Spotify installation found (looked at Flatpak, RPM, snap and Spicetify's standard paths)")
    for s in report["spotify"]:
        print(f"  spotify      {B}{s['method']}{Z} {s['version'] or '(version unknown — launch Spotify once)'}  {M}{s['path']}{Z}")
        print(f"               state={s['state']} owner={s['owner']} writable={'yes' if s['writable'] else 'NO'} "
              f"prefs={'found' if s['prefs'] else 'missing'}{('  ' + s['extra']) if s['extra'] else ''}")
    print(f"  running      {len(report['spotify_running'])} spotify process(es)")
    print(f"  spicetify    {sp['binary'] or 'not installed'} {sp['version']}")
    if sp["config"]:
        st = sp["config"].get("Setting", {})
        ao = sp["config"].get("AdditionalOptions", {})
        print(f"               theme={st.get('current_theme') or '—'} scheme={st.get('color_scheme') or '—'} "
              f"extensions={ao.get('extensions') or '—'} apps={ao.get('custom_apps') or '—'}")
        print(f"               spotify_path={st.get('spotify_path') or '(auto)'} prefs_path={st.get('prefs_path') or '(auto)'}")
    print(f"               user themes={', '.join(sp['themes']) or '—'}  Spotify-file backup={sp['backup']}")
    print(f"  core bridge  {report['core']['bridge'] if report['core'] else 'crimson-core not running'}")
    dirty = [l for l in report["project_git"].splitlines()[1:] if l.strip()]
    print(f"  project git  {report['project_git'].splitlines()[0] if report['project_git'] else '?'}"
          f"{f'  ({len(dirty)} uncommitted change(s) — left untouched)' if dirty else ''}")

    if write:
        INSPECTION.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Crimson Spotify — inspection report", "", f"Generated {report['time']} by `crimsonctl spotify inspect` (read-only).", "",
                 "| item | value |", "|---|---|", f"| OS | {report['os']} |", f"| kernel | {report['kernel']} |", f"| session | {report['session']} |"]
        for s in report["spotify"]:
            lines.append(f"| Spotify ({s['method']}) | {s['version'] or 'unknown'} · `{s['path']}` · state {s['state']} · owner {s['owner']} · "
                         f"writable {s['writable']} · prefs `{s['prefs'] or 'missing'}` {s['extra']} |")
        if not report["spotify"]:
            lines.append("| Spotify | **not found** |")
        lines += [f"| Spotify running | {len(report['spotify_running'])} process(es) |",
                  f"| Spicetify | {sp['binary'] or 'not installed'} {sp['version']} |",
                  f"| Spicetify config | `{sp['config_file']}` {'(exists)' if sp['config'] else '(none)'} |",
                  f"| Spicetify settings | theme `{setting(sp, 'Setting', 'current_theme') or '—'}`, scheme `{setting(sp, 'Setting', 'color_scheme') or '—'}`, "
                  f"extensions `{setting(sp, 'AdditionalOptions', 'extensions') or '—'}`, apps `{setting(sp, 'AdditionalOptions', 'custom_apps') or '—'}` |",
                  f"| User themes | {', '.join(sp['themes']) or '—'} |",
                  f"| Spicetify backup of Spotify files | {sp['backup']} {sp['backup_dir']} |",
                  f"| crimson-core bridge | {report['core']['bridge'] if report['core'] else 'core not running'} |",
                  "", "Project git status:", "", "```", report["project_git"], "```", "",
                  "No credentials, tokens or Spotify account data were read; only `app.last-launched-version` is read from Spotify's prefs."]
        INSPECTION.write_text("\n".join(lines) + "\n")
        ok(f"report written to {INSPECTION.relative_to(PROJ)}")
    return report


# ════════════════════════════════════════════════════════════════════ install helpers
def choose_target(installs: list[dict], target: str | None) -> dict:
    usable = [s for s in installs if s["method"] != "snap"]
    if target:
        pick = [s for s in usable if s["method"] == target or s["path"].rstrip("/") == target.rstrip("/")]
        if not pick:
            sys.exit(f"--target {target!r} doesn't match a detected installation: " + ", ".join(s["method"] for s in usable))
        return pick[0]
    if not usable:
        sys.exit("No supported Spotify installation found. Install Spotify (Flatpak or RPM), launch it once, then retry.")
    if len(usable) > 1:
        print("\nSeveral Spotify installations were found; I won't guess which one you use:")
        for s in usable:
            print(f"   --target {s['method']:16} {s['path']}")
        sys.exit("Re-run with --target <one of the above>.")
    return usable[0]


def latest_spicetify() -> tuple[str, str | None]:
    """(version, sha256 digest or None) of the latest official release via the GitHub API."""
    req = urllib.request.Request("https://api.github.com/repos/spicetify/cli/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "crimson-desktop"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rel = json.load(r)
    ver = rel["tag_name"].lstrip("v")
    asset = next((a for a in rel.get("assets", []) if a["name"] == f"spicetify-{ver}-linux-{arch()}.tar.gz"), None)
    digest = (asset or {}).get("digest") or None
    return ver, digest.split(":", 1)[1] if digest and digest.startswith("sha256:") else None


def arch() -> str:
    return {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())


def install_spicetify(assume_yes: bool) -> str:
    """Download the official release tarball into ~/.spicetify (no install script is executed)."""
    dest = HOME / ".spicetify"
    if dest.exists() and any(dest.iterdir()):
        sys.exit(f"{dest} exists but no working spicetify binary was found there — inspect it manually first.")
    try:
        ver, digest = latest_spicetify()
    except Exception as e:  # noqa: BLE001 - offline, rate-limited, proxy...
        sys.exit(f"Spicetify isn't installed and GitHub couldn't be reached to find the latest release ({e}).\n"
                 f"Check your connection and retry, or download spicetify-<version>-linux-{arch()}.tar.gz yourself from\n"
                 f"https://github.com/spicetify/cli/releases, extract it into ~/.spicetify, then re-run this command.\n"
                 f"Nothing was changed.")
    url = f"https://github.com/spicetify/cli/releases/download/v{ver}/spicetify-{ver}-linux-{arch()}.tar.gz"
    say(f"Spicetify is not installed. Official release: v{ver}")
    print(f"    {M}{url}{Z}\n    checksum: {'sha256 ' + digest if digest else 'GitHub published no digest for this asset'}")
    if not ask("download and install it to ~/.spicetify (user-level, no sudo)?", True, assume_yes):
        sys.exit("Spicetify is required; stopping.")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "crimson-desktop"}), timeout=60) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"download failed ({e}); nothing was changed")
    got = hashlib.sha256(data).hexdigest()
    if digest and got != digest:
        sys.exit(f"checksum mismatch (expected {digest}, got {got}) — not installing")
    if not digest:
        warn(f"no published digest to compare; downloaded file sha256 = {got} (recorded in the manifest)")
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(dest, filter="data")
    exe = dest / "spicetify"
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    link = HOME / ".local" / "bin" / "spicetify"
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(exe)
    ok(f"spicetify v{ver} installed to {dest} (linked as {link})")
    return json.dumps({"version": ver, "url": url, "sha256": got, "verified": bool(digest)})


def spice(exe: str, *args: str, check: bool = True, interactive: bool = False) -> int:
    print(f"    {M}$ spicetify {' '.join(args)}{Z}")
    if interactive:
        rc = subprocess.run([exe, *args]).returncode
    else:
        r = subprocess.run([exe, *args], capture_output=True, text=True)
        rc = r.returncode
        out = (r.stdout + r.stderr).strip()
        if out:
            print("\n".join("      " + l for l in out.splitlines()[-12:]))
    if check and rc != 0:
        sys.exit(f"spicetify {' '.join(args)} failed (exit {rc}). Nothing else was changed after this step; "
                 f"run `crimsonctl spotify restore` if you want to undo the earlier steps.")
    return rc


def make_backup(sp: dict, spot: dict, label: str) -> Path:
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = BACKUPS / f"{ts}-{label}"
    bdir.mkdir(parents=True)
    cfg_dir = spicetify_paths()["config_dir"]
    existed, absent = [], []
    rels = ["config-xpui.ini", f"Themes/{THEME}", f"CustomApps/{APP}"]
    rels += [f"Themes/{t}" for t in sp["themes"] if t != THEME]
    rels += [f"Extensions/{e}" for e in sp["extensions_dir"]]
    rels += [f"CustomApps/{a}" for a in sp["custom_apps_dir"] if a != APP]
    for rel in dict.fromkeys(rels):
        (existed if (cfg_dir / rel).exists() else absent).append(rel)
    if existed:
        with tarfile.open(bdir / "spicetify-config.tar.gz", "w:gz") as tf:
            for rel in existed:
                tf.add(cfg_dir / rel, arcname=rel)
    manifest = {
        "created": ts, "label": label, "config_dir": str(cfg_dir),
        "existed": existed, "absent": absent,
        "previous": {
            "spicetify_installed": bool(sp["binary"]), "spicetify_version": sp["version"],
            "current_theme": setting(sp, "Setting", "current_theme"), "color_scheme": setting(sp, "Setting", "color_scheme"),
            "inject_css": setting(sp, "Setting", "inject_css", "1"), "replace_colors": setting(sp, "Setting", "replace_colors", "1"),
            "inject_theme_js": setting(sp, "Setting", "inject_theme_js", "1"),
            "extensions": setting(sp, "AdditionalOptions", "extensions"), "custom_apps": setting(sp, "AdditionalOptions", "custom_apps"),
            "spotify_state": spot["state"], "spotify_backup": sp["backup"],
        },
        "spotify": {k: spot[k] for k in ("method", "path", "version", "owner")},
        "note": "Spotify credentials/caches are never copied. Spicetify's own copy of Spotify's original files "
                "(its Backup folder) is managed by `spicetify backup/restore` and not duplicated here.",
    }
    (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    # verify the archive before anything changes
    if existed:
        with tarfile.open(bdir / "spicetify-config.tar.gz") as tf:
            names = tf.getnames()
        missing = [r for r in existed if r not in names]
        if missing:
            sys.exit(f"backup verification failed ({missing}) — nothing changed")
    ok(f"backup verified: {bdir.relative_to(PROJ)} ({len(existed)} path(s) archived)")
    return bdir


def install_files(cfg_dir: Path) -> bool:
    """Copy theme + app into Spicetify's folders. Returns True if anything changed."""
    changed = False
    for src, dst in ((SRC_THEME, cfg_dir / "Themes" / THEME), (SRC_APP, cfg_dir / "CustomApps" / APP)):
        if dst.exists() and not (dst / MARKER).exists():
            sys.exit(f"{dst} already exists and was not created by Crimson Desktop — not overwriting it. "
                     f"Rename or remove it yourself, then retry.")
        if dst.exists() and tree_hash(dst) == tree_hash(src):
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        (dst / MARKER).write_text("installed by Crimson Desktop (crimsonctl spotify); safe to remove with `crimsonctl spotify restore`\n")
        changed = True
        ok(f"installed {dst}")
    return changed


def load_state() -> dict:
    return config.JsonState(STATE).data


def save_state(**kw) -> None:
    st = config.JsonState(STATE)
    st.data.update(kw)
    st.save()


# ════════════════════════════════════════════════════════════════════ commands
def cmd_install(target: str | None, assume_yes: bool) -> None:
    report = inspect(write=True)
    spot = choose_target(report["spotify"], target)
    sp = report["spicetify"]
    hdr("compatibility")
    if not spot["prefs"]:
        sys.exit(f"Spotify's prefs file is missing ({spot['prefs_expected']}). Launch Spotify once, log in, close it, retry.")
    if spot["state"] in ("mixed", "invalid", "unreadable"):
        sys.exit(f"Spotify's Apps folder is in state '{spot['state']}'. Spicetify can't safely back it up. "
                 f"Fix: `spicetify restore` (if Spicetify was used before) or reinstall/update Spotify, then retry.")
    ok(f"target: {spot['method']} Spotify {spot['version']} at {spot['path']} (state {spot['state']})")

    installed_info = None
    exe = sp["binary"]
    if not exe:
        installed_info = install_spicetify(assume_yes)
        exe = spicetify_bin()
        sp = detect_spicetify()
    else:
        ok(f"spicetify {sp['version']} at {exe}")
        try:
            latest, _ = latest_spicetify()
            if latest != sp["version"]:
                warn(f"newer Spicetify available: v{latest} (you have {sp['version']}). Not upgrading automatically; "
                     f"run `spicetify upgrade` yourself if Spotify {spot['version']} isn't supported by your version.")
        except Exception:  # noqa: BLE001 - offline is fine
            pass

    chmod_record = None
    if not spot["writable"]:
        hdr("permissions — your approval needed")
        print(f"  Spicetify must modify Spotify's files in {spot['path']} (owned by {spot['owner']}).")
        print("  Spicetify's documented fix for system-wide Linux installs is:")
        print(f"    {P}sudo chmod a+wr {spot['path']}{Z}")
        print(f"    {P}sudo chmod a+wr -R {spot['path']}/Apps{Z}")
        print(f"  Risk: any local user account could then modify Spotify's UI files. "
              f"{'Flatpak/package updates reset these files; re-run `crimsonctl spotify install` after Spotify updates.' if spot['method'] != 'other' else ''}")
        print("  Alternative without sudo: a per-user Flatpak (flatpak install --user flathub com.spotify.Client) —"
              " switching package formats is your decision; I won't do it.")
        if not ask("run the two sudo chmod commands now?", False):
            sys.exit("Stopped before changing permissions. Nothing was modified.")
        modes = {p: oct(Path(p).stat().st_mode & 0o7777) for p in (spot["path"], f"{spot['path']}/Apps")}
        for c in (["sudo", "chmod", "a+wr", spot["path"]], ["sudo", "chmod", "a+wr", "-R", f"{spot['path']}/Apps"]):
            if subprocess.run(c).returncode != 0:
                sys.exit("chmod failed; nothing else was changed.")
        chmod_record = {"paths": modes, "applied": dt.datetime.now().isoformat(timespec="seconds")}
        ok("permissions updated (original modes recorded for restore)")

    hdr("backup")
    bdir = make_backup(sp, spot, "spicetify")
    st = load_state()
    if not st.get("original_backup") or not Path(st["original_backup"]).exists():
        save_state(original_backup=str(bdir))
        ok("marked as your original (pre-Crimson) Spotify configuration")
    added_ext = [e for e in EXTENSIONS if e not in setting(sp, "AdditionalOptions", "extensions").split("|")]
    save_state(last_backup=str(bdir), target=spot,
               added_extensions=sorted(set(st.get("added_extensions", [])) | set(added_ext)),
               spicetify_installed_by_us=st.get("spicetify_installed_by_us") or installed_info,
               chmod=st.get("chmod") or chmod_record)

    hdr("theme & app")
    cfg_dir = spicetify_paths()["config_dir"]
    if not spicetify_paths()["config_file"].exists():
        spice(exe, "config")  # first run: Spicetify generates config-xpui.ini
    install_files(cfg_dir)

    hdr("spicetify configuration")
    spice(exe, "config", "spotify_path", spot["path"], "prefs_path", spot["prefs"])
    spice(exe, "config", "current_theme", THEME, "color_scheme", "Crimson",
          "inject_css", "1", "replace_colors", "1", "inject_theme_js", "1")
    spice(exe, "config", "extensions", "|".join(EXTENSIONS), check=False)  # already-present = harmless warning
    spice(exe, "config", "custom_apps", APP, check=False)

    hdr("apply")
    if running_spotify() and not ask("Spicetify restarts Spotify to apply the theme (playback stops briefly). Continue?", True, assume_yes):
        sys.exit("Configured but not applied. Run `crimsonctl spotify install` again when convenient.")
    sp = detect_spicetify()
    if spot["state"] == "stock" or sp["backup"] != "present":
        spice(exe, "backup", "apply", interactive=True)
    else:
        spice(exe, "apply", interactive=True)
    save_state(applied=dt.datetime.now().isoformat(timespec="seconds"))
    cmd_verify(wait_bridge=20)


def cmd_disable() -> None:
    st = load_state()
    exe = spicetify_bin()
    if not exe or not st.get("last_backup"):
        sys.exit("Crimson Spotify isn't installed (no integration state found).")
    orig = json.loads((Path(st["original_backup"]) / "manifest.json").read_text())["previous"]
    say("disabling Crimson Spotify (Spicetify stays installed; theme files stay for `enable`)")
    spice(exe, "config", "current_theme", orig["current_theme"] or "", "color_scheme", orig["color_scheme"] or "",
          "inject_theme_js", orig["inject_theme_js"] or "1")
    spice(exe, "config", "custom_apps", f"{APP}-", check=False)
    for e in st.get("added_extensions", []):
        spice(exe, "config", "extensions", f"{e}-", check=False)
    spice(exe, "apply", interactive=True)
    save_state(disabled=dt.datetime.now().isoformat(timespec="seconds"))
    ok("disabled — re-enable with `crimsonctl spotify enable`")


def cmd_update(assume_yes: bool) -> None:
    exe = spicetify_bin()
    st = load_state()
    if not exe or not st.get("last_backup"):
        sys.exit("Crimson Spotify isn't installed yet: run `crimsonctl spotify install`.")
    sp = detect_spicetify()
    say(f"spicetify {sp['version']} (never upgraded automatically; use `spicetify upgrade` yourself if needed)")
    changed = install_files(spicetify_paths()["config_dir"])
    if not changed:
        ok("theme and app already up to date — nothing to apply")
        return
    if running_spotify() and not ask("apply now (restarts Spotify)?", True, assume_yes):
        return
    spice(exe, "apply", interactive=True)
    cmd_verify(wait_bridge=20)


def cmd_restore(latest: bool, assume_yes: bool, remove_spicetify: bool) -> None:
    st = load_state()
    key = "last_backup" if latest else "original_backup"
    if not st.get(key):
        say("No Crimson Spotify backup recorded — nothing to restore (already restored?).")
        return
    bdir = Path(st[key])
    man = json.loads((bdir / "manifest.json").read_text())
    prev = man["previous"]
    cfg_dir = Path(man["config_dir"])
    hdr("restore")
    print(f"  backup {bdir.relative_to(PROJ)}  (theme was '{prev['current_theme'] or 'none'}', Spotify was {prev['spotify_state']})")
    if not ask("restore it now?", True, assume_yes):
        return
    exe = spicetify_bin()
    was_stock = prev["spotify_state"] == "stock"
    # Order matters: `spicetify restore` needs the CURRENT config (it knows where Spotify is), while
    # re-applying a previous Spicetify setup needs the PREVIOUS config back first.
    if exe and was_stock:
        rc = spice(exe, "restore", check=False, interactive=True)  # back to unmodified Spotify files
        if rc != 0:
            sys.exit("`spicetify restore` failed — config left untouched so you can retry; see the message above.")
    # remove integration-owned paths that did not exist before
    for rel in man["absent"]:
        p = cfg_dir / rel
        if p.exists() and (p.is_file() or (p / MARKER).exists()):
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            ok(f"removed {p}")
    # put the previous configuration files back
    arc = bdir / "spicetify-config.tar.gz"
    if arc.exists():
        with tarfile.open(arc) as tf:
            tf.extractall(cfg_dir, filter="data")
        ok(f"restored {len(man['existed'])} Spicetify path(s)")
    if exe and not was_stock:
        spice(exe, "apply", check=False, interactive=True)  # your previous Spicetify setup
    # 4. things that can't be undone silently
    if st.get("chmod"):
        print("\n  Spotify folder permissions were widened during install. To return them to the original modes:")
        for p, mode in st["chmod"]["paths"].items():
            print(f"    {P}sudo chmod {mode[2:]} {p}{Z}" + ("   (and restore Apps/ files with: sudo chmod -R go-w " + p + ")" if p.endswith("/Apps") else ""))
        if ask("run these sudo commands now?", False):
            for p, mode in st["chmod"]["paths"].items():
                subprocess.run(["sudo", "chmod", mode[2:], p])
                if p.endswith("/Apps"):
                    subprocess.run(["sudo", "chmod", "-R", "go-w", p])
            st_obj = config.JsonState(STATE)
            st_obj.data.pop("chmod", None)
            st_obj.save()
    if st.get("spicetify_installed_by_us"):
        if remove_spicetify:
            shutil.rmtree(HOME / ".spicetify", ignore_errors=True)
            link = HOME / ".local" / "bin" / "spicetify"
            if link.is_symlink():
                link.unlink()
            ok("removed the Spicetify binary installed by Crimson Desktop (~/.spicetify)")
        else:
            warn("Spicetify itself (installed by Crimson Desktop in ~/.spicetify) was kept; add --remove-spicetify to remove it")
    if not latest:
        st_obj = config.JsonState(STATE)
        st_obj.data.pop("original_backup", None)
        st_obj.data.pop("applied", None)
        st_obj.save()
    ok("restore finished")


def expected_problems(wait_bridge: int = 0) -> list[str]:
    probs = []
    sp = detect_spicetify()
    if not sp["binary"]:
        return ["spicetify not installed"]
    if setting(sp, "Setting", "current_theme") != THEME:
        probs.append(f"current_theme is '{setting(sp, 'Setting', 'current_theme')}', expected {THEME}")
    if setting(sp, "Setting", "inject_theme_js") != "1":
        probs.append("inject_theme_js is off (the Crimson bridge/profile script won't load)")
    exts = setting(sp, "AdditionalOptions", "extensions").split("|")
    apps = setting(sp, "AdditionalOptions", "custom_apps").split("|")
    probs += [f"extension {e} not enabled" for e in EXTENSIONS if e not in exts]
    if APP not in apps:
        probs.append(f"custom app '{APP}' not enabled")
    cfg_dir = spicetify_paths()["config_dir"]
    for src, dst in ((SRC_THEME, cfg_dir / "Themes" / THEME), (SRC_APP, cfg_dir / "CustomApps" / APP)):
        if not dst.exists():
            probs.append(f"{dst} missing")
        elif tree_hash(dst) != tree_hash(src):
            probs.append(f"{dst} differs from the project copy (run `crimsonctl spotify update`)")
    spot_path = setting(sp, "Setting", "spotify_path")
    if spot_path:
        xpui = Path(spot_path) / "Apps" / "xpui"
        if apps_state(Path(spot_path)) != "applied":
            probs.append(f"Spotify is not patched (state {apps_state(Path(spot_path))}) — Spotify may have updated; re-run install")
        else:
            for rel in ("user.css", f"custom-apps/{APP}/index.js"):
                if not (xpui / rel).exists():
                    probs.append(f"{xpui / rel} missing — theme not applied")
            css = xpui / "user.css"
            if css.exists() and "Crimson Spotify" not in css.read_text(errors="replace"):
                probs.append("applied user.css is not the Crimson theme")
    # functional check: the theme script inside Spotify connected to crimson-core
    deadline = time.monotonic() + wait_bridge
    while True:
        r = client.request({"cmd": "status"}, timeout=2)
        br = (r or {}).get("bridge") or {}
        if br.get("connections"):
            break
        if time.monotonic() >= deadline:
            if not r:
                probs.append("crimson-core not running (`crimsonctl start`) — Spotify works, but the Crimson page has no data")
            elif not br.get("listening"):
                probs.append("crimson-core bridge not listening (port in use? see `crimsonctl logs`)")
            elif running_spotify():
                probs.append("Spotify is running but its Crimson script hasn't connected to the bridge"
                             + (f" (last refused origin: {br['last_rejected_origin']} — add it to [spicetify] allowed_origins)"
                                if br.get("last_rejected_origin") else ""))
            break
        time.sleep(1)
    return probs


def cmd_verify(wait_bridge: int = 0) -> int:
    hdr("verify")
    probs = expected_problems(wait_bridge)
    if probs:
        for p in probs:
            bad(p)
        return 1
    ok("Crimson theme, Crimson app and Full App Display configured, applied, and the Spotify ↔ crimson-core bridge is connected")
    return 0


def cmd_status() -> None:
    sp = detect_spicetify()
    st = load_state()
    print(f"  spicetify   {sp['binary'] or 'not installed'} {sp['version']}")
    print(f"  theme       {setting(sp, 'Setting', 'current_theme') or '—'} / {setting(sp, 'Setting', 'color_scheme') or '—'}")
    print(f"  extensions  {setting(sp, 'AdditionalOptions', 'extensions') or '—'}")
    print(f"  apps        {setting(sp, 'AdditionalOptions', 'custom_apps') or '—'}")
    sp_path = setting(sp, "Setting", "spotify_path")
    if sp_path:
        print(f"  spotify     {sp_path}  state={apps_state(Path(sp_path))}  version={prefs_version(Path(setting(sp, 'Setting', 'prefs_path') or '/nonexistent'))}")
    r = client.request({"cmd": "status"}, timeout=2)
    br = (r or {}).get("bridge")
    print(f"  bridge      {('ws://127.0.0.1:%d, %d Spotify connection(s)' % (br['port'], br['connections'])) if br else 'core not running'}")
    print(f"  backups     original={Path(st['original_backup']).name if st.get('original_backup') else '—'}  last={Path(st['last_backup']).name if st.get('last_backup') else '—'}")
    probs = expected_problems(0) if st.get("applied") else []
    print(f"  health      {'OK' if not probs else '; '.join(probs)}" if st.get("applied") else "  health      not installed")


def cmd_doctor() -> None:
    report = inspect(write=True)
    hdr("integration")
    cmd_status()
    hdr("hints")
    for s in report["spotify"]:
        if s["method"] == "snap":
            warn("snap Spotify is read-only and can't be themed; use the Flatpak or RPM build")
        if s["method"].startswith("flatpak") and not s["writable"]:
            warn("system Flatpak Spotify: Spicetify needs write access (install asks before the documented sudo chmod)")
        if not s["prefs"]:
            warn(f"launch Spotify once so its prefs file exists ({s['prefs_expected']})")
    sp = report["spicetify"]
    for bd in spicetify_paths()["backup_dirs"]:
        if bd.is_dir() and sp["backup"] == "present" and report["spotify"]:
            v = report["spotify"][0]["version"]
            ini_v = setting(sp, "Backup", "version")
            if ini_v and v and ini_v != v:
                warn(f"Spicetify's backup is for Spotify {ini_v} but Spotify is now {v} (Spotify updated). "
                     f"Run `crimsonctl spotify install` to back up the new version and re-apply.")
    print(f"\n  {M}After a Spotify update the theme disappears until re-applied — that is normal for Spicetify.{Z}")


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    yes = "--yes" in rest or "-y" in rest
    target = next((rest[i + 1] for i, a in enumerate(rest) if a == "--target" and i + 1 < len(rest)), None)
    if cmd == "inspect":
        inspect(write=True)
    elif cmd in ("install", "enable"):
        cmd_install(target, yes)
    elif cmd == "disable":
        cmd_disable()
    elif cmd == "update":
        cmd_update(yes)
    elif cmd == "restore":
        cmd_restore("--latest" in rest, yes, "--remove-spicetify" in rest)
    elif cmd == "status":
        cmd_status()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "verify":
        sys.exit(cmd_verify(wait_bridge=int(next((rest[i + 1] for i, a in enumerate(rest) if a == "--wait"), "0"))))
    else:
        sys.exit(f"unknown command {cmd!r}; see `crimsonctl spotify help`")
