"""FILES — keyboard-driven file manager with safe operations and previews."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, OptionList, Static
from textual.widgets.option_list import Option

from ..services import files as fs
from ..services.metrics import human_bytes
from ..widgets.chrome import kv
from ..widgets.glyphs import DUSTY, MUTED, PALE, ROSE, TEXT
from .base import ModuleScreen
from .dialogs import Confirm, Prompt

BOOKMARKS_FILE = "terminal-os-bookmarks.json"
SORTS = ["name", "modified", "size", "type"]


class FilesScreen(ModuleScreen):
    MODULE = "files"
    HINTS = "enter open  ⌫ up  ~ home  . hidden  c/x/v copy/cut/paste  r rename  n/N new  d trash  b bookmarks"
    BINDINGS = [
        Binding("backspace", "up", "parent", show=False),
        Binding("tilde", "home", "home", show=False),
        Binding("full_stop", "toggle_hidden", "hidden", show=False),
        Binding("s", "cycle_sort", "sort", show=False),
        Binding("f", "filter", "filter", show=False),
        Binding("b", "bookmarks", "bookmarks", show=False),
        Binding("B", "add_bookmark", "add bookmark", show=False),
        Binding("c", "clip('copy')", "copy", show=False),
        Binding("x", "clip('move')", "cut", show=False),
        Binding("v", "paste", "paste", show=False),
        Binding("r", "rename", "rename", show=False),
        Binding("n", "new_dir", "new folder", show=False),
        Binding("N", "new_file", "new file", show=False),
        Binding("d,delete", "trash", "trash", show=False),
        Binding("o", "open_external", "open", show=False),
        Binding("O", "open_folder", "open folder", show=False),
        Binding("escape", "clear_filter", "clear filter", show=False),
    ]
    DEFAULT_CSS = """
    #files-main { height: 1fr; }
    #files-left { width: 3fr; }
    #files-right { width: 2fr; }
    #path-bar { height: 1; color: #F2B7C5; padding: 0 1; }
    #file-filter { display: none; }
    #file-filter.show { display: block; }
    #bookmarks { display: none; height: auto; max-height: 12; }
    #bookmarks.show { display: block; }
    #preview { height: 1fr; overflow-y: auto; }
    FilesScreen.narrow #files-right { display: none; }
    """

    def compose_body(self) -> ComposeResult:
        yield Static(id="path-bar")
        with Horizontal(id="files-main"):
            with Vertical(id="files-left", classes="panel"):
                yield Input(placeholder="filter…", id="file-filter")
                yield OptionList(id="bookmarks")
                yield DataTable(id="file-table", cursor_type="row")
            with Vertical(id="files-right", classes="panel"):
                yield Static(id="meta")
                yield Static(id="preview")

    def on_mount(self) -> None:
        self.cwd = Path.home()
        self.sort = 0
        self.filter = ""
        self.clip: tuple[str, Path] | None = None
        self.entries: list[fs.Entry] = []
        self.query_one("#files-left").border_title = "01 // BROWSER"
        self.query_one("#files-right").border_title = "02 // PREVIEW"
        t = self.query_one("#file-table", DataTable)
        t.add_columns("", "name", "size", "modified")
        self.load()
        t.focus()

    def layout_for(self, width: int, height: int) -> None:
        self.set_class(width < 90, "narrow")

    # -------------------------------------------------------------- listing
    def load(self, select: str | None = None) -> None:
        try:
            entries = fs.list_dir(self.cwd, self.app.settings.show_hidden_files, SORTS[self.sort])
        except fs.FileOpError as e:
            self.notify(str(e), severity="error")
            return
        if self.filter:
            entries = [e for e in entries if self.filter.lower() in e.name.lower()]
        self.entries = entries
        t = self.query_one("#file-table", DataTable)
        t.clear()
        for e in entries:
            icon = Text("▸" if e.is_dir else "·", style=DUSTY if e.is_dir else MUTED)
            name = Text(e.name + ("/" if e.is_dir else ""), style=f"bold {PALE}" if e.is_dir else (ROSE if e.error else TEXT))
            size = "" if e.is_dir else human_bytes(e.size)
            mod = dt.datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d %H:%M") if e.mtime else "?"
            t.add_row(icon, name, size, mod, key=e.name)
        if select:
            idx = next((i for i, e in enumerate(entries) if e.name == select), 0)
            t.move_cursor(row=idx)
        home = str(Path.home())
        shown = str(self.cwd).replace(home, "~", 1)
        bar = Text(f" {shown}", style=f"bold {PALE}")
        bar.append(f"   {len(entries)} items · sort {SORTS[self.sort]}"
                   + (" · hidden shown" if self.app.settings.show_hidden_files else "")
                   + (f" · filter '{self.filter}'" if self.filter else "")
                   + (f" · clipboard: {self.clip[0]} {self.clip[1].name}" if self.clip else ""), style=MUTED)
        self.query_one("#path-bar", Static).update(bar)
        self.show_preview()

    def current(self) -> fs.Entry | None:
        t = self.query_one("#file-table", DataTable)
        if not self.entries or t.cursor_row is None or t.cursor_row >= len(self.entries):
            return None
        return self.entries[t.cursor_row]

    def show_preview(self) -> None:
        e = self.current()
        meta, prev = self.query_one("#meta", Static), self.query_one("#preview", Static)
        if not e:
            meta.update(Text("empty folder", style=MUTED))
            prev.update("")
            return
        meta.update(kv(fs.describe(e), 10))
        kind, content = fs.preview(e)
        if kind in ("code", "json"):
            lexer = "json" if kind == "json" else Syntax.guess_lexer(str(e.path), code=content[:2000])
            prev.update(Syntax(content, lexer, theme="monokai", background_color="#190D16", line_numbers=False, word_wrap=True))
        elif kind == "markdown":
            prev.update(Markdown(content[:20000]))
        elif kind in ("binary", "image", "error"):
            prev.update(Text(f"\n{content}", style=ROSE if kind == "error" else MUTED))
        else:
            prev.update(Text(content, style=TEXT))

    def on_data_table_row_highlighted(self, event) -> None:
        if event.data_table.id == "file-table":
            self.show_preview()

    def on_data_table_row_selected(self, event) -> None:
        if event.data_table.id != "file-table":
            return
        e = self.current()
        if e and e.is_dir:
            self.cwd = e.path
            self.filter = ""
            self.load()
        elif e:
            self.action_open_external()

    # -------------------------------------------------------------- navigation
    def action_up(self) -> None:
        if self.focused and isinstance(self.focused, Input):
            return
        prev = self.cwd.name
        self.cwd = self.cwd.parent
        self.filter = ""
        self.load(select=prev)

    def action_home(self) -> None:
        self.cwd = Path.home()
        self.load()

    def action_toggle_hidden(self) -> None:
        s = self.app.settings
        s.show_hidden_files = not s.show_hidden_files
        self.app.save_settings()
        self.load(select=(self.current() or fs.Entry(Path("."), "", False, False, 0, 0, 0)).name)

    def action_cycle_sort(self) -> None:
        self.sort = (self.sort + 1) % len(SORTS)
        self.load()

    def action_filter(self) -> None:
        inp = self.query_one("#file-filter", Input)
        inp.add_class("show")
        inp.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "file-filter":
            self.filter = event.value
            self.load()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "file-filter":
            self.query_one("#file-table").focus()

    def action_clear_filter(self) -> None:
        inp = self.query_one("#file-filter", Input)
        bm = self.query_one("#bookmarks", OptionList)
        if bm.has_class("show"):
            bm.remove_class("show")
        elif inp.has_class("show") or self.filter:
            inp.value = ""
            inp.remove_class("show")
            self.filter = ""
            self.load()
        self.query_one("#file-table").focus()

    # -------------------------------------------------------------- bookmarks
    def _bookmarks(self) -> list[str]:
        from crimson import paths
        f = paths.CONFIG_DIR / BOOKMARKS_FILE
        try:
            saved = json.loads(f.read_text())
        except (OSError, ValueError):
            saved = []
        defaults = [str(Path.home() / d) for d in ("", "Downloads", "Documents", "Music", "Pictures", "Projects")]
        defaults.append(str(paths.PROJECT_DIR))
        return [p for p in dict.fromkeys(defaults + saved) if Path(p).is_dir()]

    def action_bookmarks(self) -> None:
        bm = self.query_one("#bookmarks", OptionList)
        bm.clear_options()
        home = str(Path.home())
        for p in self._bookmarks():
            bm.add_option(Option(p.replace(home, "~", 1) or "~", id=p))
        bm.add_class("show")
        bm.focus()

    def action_add_bookmark(self) -> None:
        from crimson import paths
        f = paths.CONFIG_DIR / BOOKMARKS_FILE
        try:
            saved = json.loads(f.read_text())
        except (OSError, ValueError):
            saved = []
        if str(self.cwd) not in saved:
            saved.append(str(self.cwd))
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(saved, indent=2))
        self.notify(f"bookmarked {self.cwd}")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "bookmarks":
            self.cwd = Path(event.option.id)
            event.option_list.remove_class("show")
            self.load()
            self.query_one("#file-table").focus()

    # -------------------------------------------------------------- operations
    def _guard(self, fn, *args):
        try:
            return fn(*args)
        except fs.FileOpError as e:
            self.notify(str(e), severity="error")
        except PermissionError:
            self.notify("permission denied", severity="error")
        except OSError as e:
            self.notify(e.strerror or str(e), severity="error")
        return None

    def action_clip(self, mode: str) -> None:
        e = self.current()
        if e:
            self.clip = (mode, e.path)
            self.notify(f"{'copied' if mode == 'copy' else 'cut'}: {e.name} — go to a folder and press v to paste")
            self.load(select=e.name)

    def action_paste(self) -> None:
        if not self.clip:
            self.notify("clipboard is empty (c = copy, x = cut)")
            return
        mode, src = self.clip
        result = self._guard(fs.copy if mode == "copy" else fs.move, src, self.cwd)
        if result:
            self.notify(f"{'copied' if mode == 'copy' else 'moved'} {src.name}")
            if mode == "move":
                self.clip = None
            self.load(select=result.name)

    def action_rename(self) -> None:
        e = self.current()
        if not e:
            return

        def done(name: str | None) -> None:
            if name and name != e.name:
                new = self._guard(fs.rename, e.path, name)
                if new:
                    self.load(select=new.name)

        self.app.push_screen(Prompt(f"rename {e.name}", e.name), done)

    def action_new_dir(self) -> None:
        def done(name: str | None) -> None:
            if name:
                new = self._guard(fs.make_dir, self.cwd, name)
                if new:
                    self.load(select=new.name)
        self.app.push_screen(Prompt("new folder", placeholder="folder name"), done)

    def action_new_file(self) -> None:
        def done(name: str | None) -> None:
            if name:
                new = self._guard(fs.make_file, self.cwd, name)
                if new:
                    self.load(select=new.name)
        self.app.push_screen(Prompt("new empty file", placeholder="file name"), done)

    def action_trash(self) -> None:
        e = self.current()
        if not e:
            return

        def done(ok: bool | None) -> None:
            if ok and self._guard(fs.trash, e.path):
                self.notify(f"moved {e.name} to Trash (restore it from Dolphin → Trash)")
                self.load()

        kind = "folder and everything in it" if e.is_dir else "file"
        self.app.push_screen(Confirm(f"Move {e.name} to Trash?", f"This {kind} goes to the desktop Trash and can be restored.",
                                     "Move to Trash"), done)

    def action_open_external(self) -> None:
        e = self.current()
        if e and self._guard(fs.open_external, e.path):
            self.notify(f"opening {e.name} with its default app…", timeout=2)

    def action_open_folder(self) -> None:
        self._guard(fs.open_external, self.cwd)
