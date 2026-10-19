"""System metrics with psutil + sysfs. Every reading may be None: missing sensors are reported as
unavailable, never invented. Sampling only happens while a visible screen asks for it."""

from __future__ import annotations

import getpass
import os
import platform
import shutil
import socket
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import psutil

HIST = 90  # samples kept for graphs
PSEUDO_FS = {"tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs", "cgroup", "cgroup2", "efivarfs",
             "fuse.portal", "fuse.gvfsd-fuse", "autofs", "ramfs", "tracefs", "debugfs", "securityfs", "devpts"}
CRITICAL_PROCS = {"systemd", "init", "kwin_wayland", "kwin_x11", "plasmashell", "Xwayland", "pipewire", "wireplumber",
                  "pipewire-pulse", "sddm", "dbus-daemon", "dbus-broker", "kded6", "kded5", "ksmserver", "polkitd",
                  "NetworkManager", "systemd-logind", "Xorg", "gnome-shell"}


def _read(p: str | Path) -> str | None:
    try:
        return Path(p).read_text().strip()
    except OSError:
        return None


@dataclass
class GPU:
    vendor: str = "unknown"
    name: str = ""
    util: float | None = None
    vram_used: int | None = None   # bytes
    vram_total: int | None = None
    temp: float | None = None
    power_w: float | None = None
    clock_mhz: float | None = None
    source: str = ""


@dataclass
class Snapshot:
    cpu: float = 0.0
    per_core: list[float] = field(default_factory=list)
    freq_mhz: float | None = None
    cpu_temp: float | None = None
    mem_used: int = 0
    mem_total: int = 0
    mem_avail: int = 0
    swap_used: int = 0
    swap_total: int = 0
    net_up: float = 0.0     # bytes/s
    net_down: float = 0.0
    gpu: GPU = field(default_factory=GPU)
    time: float = 0.0


class Metrics:
    def __init__(self):
        self.static = self._static()
        self.hist = {k: deque(maxlen=HIST) for k in ("cpu", "mem", "gpu", "up", "down")}
        self.last = Snapshot()
        self._net_prev: tuple[float, int, int] | None = None
        self._nv_cache: tuple[float, GPU] = (0.0, GPU())
        self._gpu_dev = self._find_amd_or_intel()
        psutil.cpu_percent(percpu=True)  # prime the counters

    # ------------------------------------------------------------ static facts
    @staticmethod
    def _static() -> dict:
        osname = platform.system()
        for line in (_read("/etc/os-release") or "").splitlines():
            if line.startswith("PRETTY_NAME="):
                osname = line.split("=", 1)[1].strip('"')
        cpu = platform.processor() or ""
        for line in (_read("/proc/cpuinfo") or "").splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
        for junk in ("(R)", "(TM)", " CPU", " Processor", "with Radeon Graphics"):
            cpu = cpu.replace(junk, "")
        boot = psutil.boot_time()
        return {
            "os": osname, "kernel": platform.release(), "host": socket.gethostname().split(".")[0],
            "user": getpass.getuser(),
            "cpu": " ".join(cpu.split()).split(" @")[0], "cores": psutil.cpu_count(logical=False) or 0,
            "threads": psutil.cpu_count() or 0, "boot": boot,
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "?"), "session": os.environ.get("XDG_SESSION_TYPE", "?"),
            "shell": Path(os.environ.get("SHELL", "?")).name,
            "battery": psutil.sensors_battery() is not None if hasattr(psutil, "sensors_battery") else False,
        }

    @staticmethod
    def _find_amd_or_intel() -> tuple[str, Path] | None:
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
            dev = card / "device"
            vendor = _read(dev / "vendor")
            if vendor == "0x1002" and (dev / "gpu_busy_percent").exists():
                return "amd", dev
            if vendor == "0x8086":
                return "intel", card
        return None

    def uptime(self) -> float:
        return time.time() - self.static["boot"]

    # ------------------------------------------------------------ sampling
    def _temps(self) -> float | None:
        try:
            temps = psutil.sensors_temperatures()
        except (AttributeError, OSError):
            return None
        for key in ("k10temp", "coretemp", "zenpower", "cpu_thermal", "acpitz"):
            for t in temps.get(key, []):
                if t.current:
                    return float(t.current)
        return None

    def _gpu(self) -> GPU:
        if self._gpu_dev and self._gpu_dev[0] == "amd":
            dev = self._gpu_dev[1]
            g = GPU(vendor="AMD", source="sysfs (amdgpu)")
            g.name = _read(dev / "product_name") or "AMD Radeon"
            b = _read(dev / "gpu_busy_percent")
            g.util = float(b) if b and b.isdigit() else None
            u, t = _read(dev / "mem_info_vram_used"), _read(dev / "mem_info_vram_total")
            g.vram_used = int(u) if u and u.isdigit() else None
            g.vram_total = int(t) if t and t.isdigit() else None
            for hw in (dev / "hwmon").glob("hwmon*"):
                temp = _read(hw / "temp1_input")
                g.temp = int(temp) / 1000 if temp and temp.lstrip("-").isdigit() else None
                pw = _read(hw / "power1_average") or _read(hw / "power1_input")
                g.power_w = int(pw) / 1e6 if pw and pw.isdigit() else None
                clk = _read(hw / "freq1_input")
                g.clock_mhz = int(clk) / 1e6 if clk and clk.isdigit() else None
            return g
        if shutil.which("nvidia-smi"):
            ts, cached = self._nv_cache
            if time.monotonic() - ts < 3:
                return cached
            g = GPU(vendor="NVIDIA", source="nvidia-smi")
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.gr",
                                      "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3).stdout
                vals = [v.strip() for v in out.splitlines()[0].split(",")]
                num = lambda v: float(v) if v.replace(".", "", 1).isdigit() else None  # noqa: E731
                g.name, g.util = vals[0], num(vals[1])
                g.vram_used = int(num(vals[2]) * 2**20) if num(vals[2]) is not None else None
                g.vram_total = int(num(vals[3]) * 2**20) if num(vals[3]) is not None else None
                g.temp, g.power_w, g.clock_mhz = num(vals[4]), num(vals[5]), num(vals[6])
            except (OSError, IndexError, ValueError, subprocess.TimeoutExpired):
                pass
            self._nv_cache = (time.monotonic(), g)
            return g
        if self._gpu_dev and self._gpu_dev[0] == "intel":
            card = self._gpu_dev[1]
            g = GPU(vendor="Intel", name="Intel Graphics", source="sysfs (i915/xe): clocks only")
            cur = _read(card / "gt_cur_freq_mhz")
            g.clock_mhz = float(cur) if cur and cur.isdigit() else None
            return g
        return GPU()

    def sample(self, want_gpu: bool = True) -> Snapshot:
        s = Snapshot(time=time.time())
        s.per_core = psutil.cpu_percent(percpu=True)
        s.cpu = sum(s.per_core) / max(1, len(s.per_core))
        try:
            f = psutil.cpu_freq()
            s.freq_mhz = f.current if f else None
        except (OSError, FileNotFoundError, AttributeError):
            s.freq_mhz = None
        s.cpu_temp = self._temps()
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        s.mem_used, s.mem_total, s.mem_avail = vm.total - vm.available, vm.total, vm.available
        s.swap_used, s.swap_total = sw.used, sw.total
        io = psutil.net_io_counters()
        now = time.monotonic()
        if self._net_prev:
            dt = max(1e-3, now - self._net_prev[0])
            s.net_up = max(0, io.bytes_sent - self._net_prev[1]) / dt
            s.net_down = max(0, io.bytes_recv - self._net_prev[2]) / dt
        self._net_prev = (now, io.bytes_sent, io.bytes_recv)
        s.gpu = self._gpu() if want_gpu else self.last.gpu
        self.hist["cpu"].append(s.cpu)
        self.hist["mem"].append(100 * s.mem_used / max(1, s.mem_total))
        self.hist["gpu"].append(s.gpu.util or 0.0)
        self.hist["up"].append(s.net_up)
        self.hist["down"].append(s.net_down)
        self.last = s
        return s

    # ------------------------------------------------------------ on-demand tables
    @staticmethod
    def disks() -> list[dict]:
        out, seen = [], set()
        for p in psutil.disk_partitions(all=False):
            if p.fstype in PSEUDO_FS or p.mountpoint.startswith(("/snap", "/var/lib/flatpak/", "/run/")) or p.device in seen:
                continue
            seen.add(p.device)
            try:
                u = psutil.disk_usage(p.mountpoint)
            except (PermissionError, OSError):
                continue
            out.append({"mount": p.mountpoint, "device": p.device, "fs": p.fstype, "total": u.total,
                        "used": u.used, "free": u.free, "pct": u.percent})
        return out

    @staticmethod
    def interfaces() -> list[dict]:
        stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
        out = []
        for name, st in stats.items():
            if name == "lo" or name.startswith(("veth", "docker", "br-", "virbr")):
                continue
            ipv4 = next((a.address for a in addrs.get(name, []) if a.family == socket.AF_INET), "")
            kind = "wifi" if Path(f"/sys/class/net/{name}/wireless").exists() else \
                   "ethernet" if Path(f"/sys/class/net/{name}/device").exists() else "virtual"
            out.append({"name": name, "up": st.isup, "speed": st.speed, "ip": ipv4, "kind": kind})
        out.sort(key=lambda d: (not d["up"], not d["ip"], d["kind"] == "virtual"))
        return out

    @staticmethod
    def processes(limit: int = 200) -> list[dict]:
        procs = []
        for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "status"]):
            info = p.info
            mem = info["memory_info"].rss if info.get("memory_info") else 0
            procs.append({"pid": info["pid"], "name": info.get("name") or "?", "user": info.get("username") or "?",
                          "cpu": info.get("cpu_percent") or 0.0, "mem": mem, "status": info.get("status") or ""})
        return procs[:5000]


def can_terminate(proc: dict) -> tuple[bool, str]:
    """Only your own, non-critical processes may be terminated (and the UI still asks first)."""
    if proc["name"] in CRITICAL_PROCS:
        return False, f"{proc['name']} is a critical desktop/system process"
    if proc["pid"] in (0, 1, os.getpid(), os.getppid()):
        return False, "refusing to terminate this process"
    import getpass
    if proc["user"] in ("", "?"):
        return False, "can't tell who owns it"
    if proc["user"] != getpass.getuser() and os.geteuid() != 0:
        return False, f"owned by {proc['user']} — not yours"
    return True, ""


def human_bytes(n: float | None, rate: bool = False) -> str:
    if n is None:
        return "n/a"
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024 or unit == "T":
            s = f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
            return s + ("/s" if rate else "")
        n /= 1024
    return str(n)


def human_duration(sec: float) -> str:
    sec = int(sec)
    d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    return (f"{d}d " if d else "") + (f"{h}h " if h or d else "") + f"{m}m"
