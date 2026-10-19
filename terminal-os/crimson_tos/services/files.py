"""Safe file operations and previews for the FILES module.

* Delete = move to the freedesktop.org Trash (the same Trash Dolphin uses), never rm -r.
* Copy/move refuse to overwrite; names are validated (no '/', no '.'/'..').
* Previews never execute anything and strip terminal control sequences from file contents.
* Opening uses xdg-open / kde-open with an argument list (no shell).
"""

from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import re
import shutil
import stat
import subprocess
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

CTRL = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b[@-_]|[\x00-\x08\x0b-\x1f\x7f-\x9f]")
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".json", ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash", ".zsh", ".fish",
            ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".java", ".kt", ".lua", ".rb", ".php", ".html", ".css", ".qml", ".xml",
            ".yaml", ".yml", ".csv", ".log", ".lrc", ".desktop", ".service", ".colorscheme", ".profile", ".gitignore"}
MAX_PREVIEW = 64 * 1024


class FileOpError(Exception):
    pass


@dataclass
class Entry:
    path: Path
    name: str
    is_dir: bool
    is_link: bool
    size: int
    mtime: float
    mode: int
    error: str = ""

    @property
    def hidden(self) -> bool:
        return self.name.startswith(".")


def list_dir(path: Path, show_hidden: bool = False, sort: str = "name") -> list[Entry]:
    entries = []
    try:
        it = list(os.scandir(path))
    except PermissionError as e:
        raise FileOpError(f"permission denied: {path}") from e
    except FileNotFoundError as e:
        raise FileOpError(f"no such directory: {path}") from e
    for d in it:
        if not show_hidden and d.name.startswith("."):
            continue
        try:
            st = d.stat(follow_symlinks=True)
            entries.append(Entry(Path(d.path), d.name, stat.S_ISDIR(st.st_mode), d.is_symlink(), st.st_size, st.st_mtime, st.st_mode))
        except OSError as e:  # broken symlink, permission...
            entries.append(Entry(Path(d.path), d.name, False, True, 0, 0, 0, error=e.strerror or "unreadable"))
    keys = {
        "name": lambda e: (not e.is_dir, e.name.lower()),
        "size": lambda e: (not e.is_dir, -e.size),
        "modified": lambda e: (not e.is_dir, -e.mtime),
        "type": lambda e: (not e.is_dir, e.path.suffix.lower(), e.name.lower()),
    }
    return sorted(entries, key=keys.get(sort, keys["name"]))


def valid_name(name: str) -> str:
    name = name.strip()
    if not name or name in (".", "..") or "/" in name or "\x00" in name:
        raise FileOpError(f"invalid name: {name!r}")
    return name


def make_dir(parent: Path, name: str) -> Path:
    target = parent / valid_name(name)
    if target.exists():
        raise FileOpError(f"{target.name} already exists")
    target.mkdir()
    return target


def make_file(parent: Path, name: str) -> Path:
    target = parent / valid_name(name)
    try:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)  # never truncates an existing file
    except FileExistsError as e:
        raise FileOpError(f"{target.name} already exists") from e
    os.close(fd)
    return target


def rename(src: Path, new_name: str) -> Path:
    target = src.with_name(valid_name(new_name))
    if target.exists():
        raise FileOpError(f"{target.name} already exists")
    src.rename(target)
    return target


def copy(src: Path, dest_dir: Path) -> Path:
    target = dest_dir / src.name
    if target.exists():
        raise FileOpError(f"{target} already exists — not overwriting")
    if src.is_dir() and dest_dir.resolve().is_relative_to(src.resolve()):
        raise FileOpError("can't copy a folder into itself")
    if src.is_dir():
        shutil.copytree(src, target, symlinks=True)
    else:
        shutil.copy2(src, target, follow_symlinks=False)
    return target


def move(src: Path, dest_dir: Path) -> Path:
    target = dest_dir / src.name
    if target.exists():
        raise FileOpError(f"{target} already exists — not overwriting")
    if src.is_dir() and dest_dir.resolve().is_relative_to(src.resolve()):
        raise FileOpError("can't move a folder into itself")
    return Path(shutil.move(str(src), str(target)))


def trash_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Trash"


def trash(path: Path) -> Path:
    """Move to the freedesktop.org home Trash (restorable from Dolphin's Trash)."""
    td = trash_dir()
    files, info = td / "files", td / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    if os.stat(path, follow_symlinks=False).st_dev != os.stat(files).st_dev:
        # cross-device: let the desktop's own trash implementation handle it
        for tool in (["gio", "trash", "--"], ["kioclient", "move"]):
            if shutil.which(tool[0]):
                args = tool + [str(path)] + (["trash:/"] if tool[0] == "kioclient" else [])
                if subprocess.run(args, capture_output=True).returncode == 0:
                    return path
        raise FileOpError("file is on another drive and no trash tool (gio/kioclient) worked — not deleting")
    base = path.name
    name, n = base, 1
    while (files / name).exists() or (info / f"{name}.trashinfo").exists():
        n += 1
        name = f"{base}.{n}"
    tinfo = info / f"{name}.trashinfo"
    with open(tinfo, "x") as f:
        f.write(f"[Trash Info]\nPath={urllib.parse.quote(str(path.absolute()))}\n"
                f"DeletionDate={dt.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
    try:
        os.rename(path, files / name)
    except OSError:
        tinfo.unlink(missing_ok=True)
        raise
    return files / name


def open_external(path: Path) -> bool:
    for tool in ("kde-open", "kde-open5", "xdg-open"):
        exe = shutil.which(tool)
        if exe:
            subprocess.Popen([exe, str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return True
    raise FileOpError("no opener found (xdg-open / kde-open)")


def sanitize(text: str) -> str:
    return CTRL.sub("", text.replace("\t", "    "))


def describe(e: Entry) -> list[tuple[str, str]]:
    mt = dt.datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d %H:%M") if e.mtime else "?"
    kind = "folder" if e.is_dir else (mimetypes.guess_type(e.name)[0] or "file")
    rows = [("name", e.name), ("type", kind + (" (link)" if e.is_link else "")), ("modified", mt),
            ("mode", stat.filemode(e.mode) if e.mode else "?")]
    if not e.is_dir:
        rows.insert(2, ("size", f"{e.size:,} bytes"))
    if e.error:
        rows.append(("error", e.error))
    return rows


def preview(e: Entry) -> tuple[str, str]:
    """Return (kind, content) where kind is one of dir / text / code / markdown / json / image / binary / error."""
    if e.error:
        return "error", e.error
    if e.is_dir:
        try:
            items = list_dir(e.path)
        except FileOpError as err:
            return "error", str(err)
        lines = [("▸ " if i.is_dir else "  ") + i.name for i in items[:200]]
        return "dir", f"{len(items)} item(s)\n\n" + "\n".join(lines)
    mime = mimetypes.guess_type(e.name)[0] or ""
    if mime.startswith("image/"):
        return "image", image_info(e.path)
    try:
        with open(e.path, "rb") as f:
            raw = f.read(MAX_PREVIEW)
    except OSError as err:
        return "error", err.strerror or str(err)
    if b"\x00" in raw[:8192]:
        return "binary", f"binary file ({mime or 'unknown type'}) — no preview"
    text = sanitize(raw.decode("utf-8", errors="replace"))
    ext = e.path.suffix.lower()
    if ext == ".json":
        try:
            return "json", json.dumps(json.loads(text), indent=2)[:MAX_PREVIEW]
        except ValueError:
            return "code", text
    if ext == ".md":
        return "markdown", text
    if ext in TEXT_EXT or mime.startswith("text/") or not mime:
        return ("code" if ext in TEXT_EXT and ext not in (".txt", ".log", ".csv") else "text"), text
    return "binary", f"{mime} — no text preview"


def image_info(path: Path) -> str:
    try:
        from PIL import Image  # optional
        with Image.open(path) as im:
            return f"image {im.format} {im.width}×{im.height} {im.mode}"
    except Exception:  # noqa: BLE001 - Pillow missing or unreadable image
        try:
            return f"image, {path.stat().st_size:,} bytes"
        except OSError:
            return "image"
