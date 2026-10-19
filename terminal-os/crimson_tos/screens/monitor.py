"""MONITOR — real-time CPU / GPU / memory / storage / network / processes."""

from __future__ import annotations

import os
import signal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Static, TabbedContent, TabPane

from ..services.metrics import can_terminate, human_bytes
from ..widgets.chrome import kv
from ..widgets.glyphs import DUSTY, LINE, MUTED, PALE, ROSE, TEXT, graph, meter
from .base import ModuleScreen
from .dialogs import Confirm


class MonitorScreen(ModuleScreen):
    MODULE = "monitor"
    HINTS = "←/→ tabs  s sort  f filter  k terminate"
    BINDINGS = [
        Binding("s", "cycle_sort", "sort", show=False),
        Binding("f", "focus_filter", "filter", show=False),
        Binding("k", "terminate", "terminate", show=False),
    ]
    DEFAULT_CSS = """
    MonitorScreen TabPane { padding: 0 1; }
    #cpu-cores, #gpu-text, #mem-text, #net-text { height: auto; }
    .graph-label { color: #A88B98; height: 1; margin-top: 1; }
    .graph { height: 4; }
    #proc-filter { width: 40; margin: 0 0 1 0; }
    """
    SORTS = [("cpu", "CPU"), ("mem", "RAM"), ("name", "NAME"), ("pid", "PID")]
    _sort = 0
    _procs: list = []

    def compose_body(self) -> ComposeResult:
        with Vertical(classes="panel", id="mon-panel"):
            with TabbedContent(id="mon-tabs"):
                with TabPane("CPU", id="t-cpu"):
                    yield Static(id="cpu-head")
                    yield Static("utilisation history", classes="graph-label")
                    yield Static(id="cpu-hist", classes="graph")
                    yield Static(id="cpu-cores")
                with TabPane("GPU", id="t-gpu"):
                    yield Static(id="gpu-text")
                    yield Static("utilisation history", classes="graph-label")
                    yield Static(id="gpu-hist", classes="graph")
                with TabPane("MEMORY", id="t-mem"):
                    yield Static(id="mem-text")
                    yield Static("usage history", classes="graph-label")
                    yield Static(id="mem-hist", classes="graph")
                with TabPane("STORAGE", id="t-disk"):
                    yield DataTable(id="disk-table", cursor_type="row", zebra_stripes=False)
                with TabPane("NETWORK", id="t-net"):
                    yield Static(id="net-text")
                    yield Static("download", classes="graph-label")
                    yield Static(id="down-hist", classes="graph")
                    yield Static("upload", classes="graph-label")
                    yield Static(id="up-hist", classes="graph")
                with TabPane("PROCESSES", id="t-proc"):
                    with Vertical():
                        yield Input(placeholder="filter processes (name / user / pid)…", id="proc-filter")
                        yield DataTable(id="proc-table", cursor_type="row")

    def on_mount(self) -> None:
        self.query_one("#mon-panel").border_title = "SYSTEM MONITOR"
        self._sort = 0
        self._procs: list[dict] = []
        disk = self.query_one("#disk-table", DataTable)
        disk.add_columns("mount", "device", "fs", "size", "used", "free", "use")
        pt = self.query_one("#proc-table", DataTable)
        pt.add_columns("PID", "NAME", "USER", "CPU%", "RAM", "STATE")
        self.tick(False)

    @property
    def active_tab(self) -> str:
        return self.query_one("#mon-tabs", TabbedContent).active

    def on_tabbed_content_tab_activated(self, event) -> None:
        self.tick(False)

    def tick(self, fast: bool) -> None:
        if fast:
            return
        m = self.app.metrics
        tab = self.active_tab
        s = m.sample(want_gpu=tab in ("t-gpu", "t-cpu"))
        if tab == "t-cpu":
            head = kv([("model", m.static["cpu"]), ("cores", f"{m.static['cores']} cores / {m.static['threads']} threads"),
                       ("usage", f"{s.cpu:.1f}%"), ("freq", f"{s.freq_mhz / 1000:.2f} GHz" if s.freq_mhz else "n/a"),
                       ("temp", f"{s.cpu_temp:.0f}°C" if s.cpu_temp is not None else "n/a (no sensor exposed)")])
            self.query_one("#cpu-head", Static).update(head)
            self.query_one("#cpu-hist", Static).update(graph(list(m.hist["cpu"]), self.size.width - 6, 4, vmax=100))
            cores = Text()
            per_row = max(1, (self.size.width - 4) // 30)
            for i, v in enumerate(s.per_core):
                cores.append(f"cpu{i:<3}", style=DUSTY)
                cores.append_text(meter(v / 100, 14))
                cores.append(f" {v:5.1f}%   ", style=TEXT)
                if (i + 1) % per_row == 0:
                    cores.append("\n")
            self.query_one("#cpu-cores", Static).update(cores)
        elif tab == "t-gpu":
            g = s.gpu
            if g.vendor == "unknown":
                self.query_one("#gpu-text", Static).update(Text("No GPU metrics available on this system.\n"
                    "AMD: amdgpu sysfs · NVIDIA: nvidia-smi · Intel: clocks only (no utilisation without root tools).", style=MUTED))
            else:
                na = "n/a"
                self.query_one("#gpu-text", Static).update(kv([
                    ("gpu", f"{g.name} ({g.vendor})"), ("source", g.source),
                    ("usage", f"{g.util:.0f}%" if g.util is not None else na),
                    ("vram", f"{human_bytes(g.vram_used)} / {human_bytes(g.vram_total)}" if g.vram_total else na),
                    ("temp", f"{g.temp:.0f}°C" if g.temp is not None else na),
                    ("power", f"{g.power_w:.0f} W" if g.power_w is not None else na),
                    ("clock", f"{g.clock_mhz:.0f} MHz" if g.clock_mhz is not None else na)], 8))
            self.query_one("#gpu-hist", Static).update(graph(list(m.hist["gpu"]), self.size.width - 6, 4, vmax=100))
        elif tab == "t-mem":
            t = kv([("total", human_bytes(s.mem_total)), ("used", human_bytes(s.mem_used)),
                    ("avail", f"{human_bytes(s.mem_avail)}  (MemAvailable: what apps can still get)"),
                    ("swap", f"{human_bytes(s.swap_used)} / {human_bytes(s.swap_total)}" if s.swap_total else "none")])
            t.append("\n\n")
            t.append_text(meter(s.mem_used / max(1, s.mem_total), 40))
            t.append(f"  {100 * s.mem_used / max(1, s.mem_total):.1f}%", style=PALE)
            self.query_one("#mem-text", Static).update(t)
            self.query_one("#mem-hist", Static).update(graph(list(m.hist["mem"]), self.size.width - 6, 4, vmax=100))
        elif tab == "t-disk":
            table = self.query_one("#disk-table", DataTable)
            table.clear()
            for d in m.disks():
                bar = meter(d["pct"] / 100, 12)
                bar.append(f" {d['pct']:.0f}%", style=TEXT)
                table.add_row(d["mount"], d["device"], d["fs"], human_bytes(d["total"]), human_bytes(d["used"]),
                              human_bytes(d["free"]), bar)
        elif tab == "t-net":
            ifs = m.interfaces()
            t = Text()
            for i in ifs[:6]:
                t.append(f"{i['name']:<14}", style=f"bold {PALE}" if i["up"] and i["ip"] else MUTED)
                t.append(f"{i['kind']:<9}", style=DUSTY)
                t.append(f"{'up' if i['up'] else 'down':<6}", style=TEXT if i["up"] else ROSE)
                t.append(f"{i['ip'] or '—':<17}", style=TEXT)
                t.append(f"{(str(i['speed']) + ' Mb/s') if i['speed'] else ''}\n", style=MUTED)
            t.append(f"\n↓ {human_bytes(s.net_down, True)}    ↑ {human_bytes(s.net_up, True)}", style=PALE)
            self.query_one("#net-text", Static).update(t)
            self.query_one("#down-hist", Static).update(graph(list(m.hist["down"]), self.size.width - 6, 4, vmax=None))
            self.query_one("#up-hist", Static).update(graph(list(m.hist["up"]), self.size.width - 6, 4, vmax=None))
        elif tab == "t-proc":
            self._refresh_procs()

    # -------------------------------------------------------------- processes
    def _refresh_procs(self) -> None:
        self._procs = self.app.metrics.processes()
        q = self.query_one("#proc-filter", Input).value.lower().strip()
        procs = [p for p in self._procs if not q or q in p["name"].lower() or q in p["user"].lower() or q == str(p["pid"])]
        key = self.SORTS[self._sort][0]
        procs.sort(key=lambda p: p[key] if key in ("name", "pid") else -p[key])
        table = self.query_one("#proc-table", DataTable)
        cur = table.cursor_row
        table.clear()
        for p in procs[:300]:
            table.add_row(str(p["pid"]), p["name"][:32], p["user"][:12], f"{p['cpu']:.1f}", human_bytes(p["mem"]), p["status"],
                          key=str(p["pid"]))
        if procs:
            table.move_cursor(row=min(cur, len(procs) - 1))
        self.query_one("#t-proc").border_title = f"sorted by {self.SORTS[self._sort][1]}"

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "proc-filter":
            self._refresh_procs()

    def action_cycle_sort(self) -> None:
        self._sort = (self._sort + 1) % len(self.SORTS)
        self.notify(f"processes sorted by {self.SORTS[self._sort][1]}", timeout=1.5)
        if self.active_tab == "t-proc":
            self._refresh_procs()

    def action_focus_filter(self) -> None:
        self.query_one("#mon-tabs", TabbedContent).active = "t-proc"
        self.query_one("#proc-filter", Input).focus()

    def action_terminate(self) -> None:
        if self.active_tab != "t-proc":
            return
        table = self.query_one("#proc-table", DataTable)
        if table.row_count == 0:
            return
        pid = int(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
        proc = next((p for p in self._procs if p["pid"] == pid), None)
        if not proc:
            return
        ok, why = can_terminate(proc)
        if not ok:
            self.notify(f"won't terminate: {why}", severity="warning")
            return

        def done(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                os.kill(pid, signal.SIGTERM)
                self.notify(f"sent SIGTERM to {proc['name']} ({pid})")
            except ProcessLookupError:
                self.notify("process already exited")
            except PermissionError:
                self.notify("permission denied", severity="error")
            self._refresh_procs()

        self.app.push_screen(Confirm(f"Terminate {proc['name']} (PID {pid})?",
                                     "Sends SIGTERM (a polite request to exit). Unsaved work in it may be lost.",
                                     "Terminate"), done)
