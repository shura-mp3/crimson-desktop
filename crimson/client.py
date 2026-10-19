"""Small synchronous helpers for talking to crimson-core (used by crimsonctl)."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time

from . import paths


def connect(start: bool = False, timeout: float = 4.0) -> socket.socket | None:
    deadline = time.monotonic() + timeout
    started = False
    while True:
        s = socket.socket(socket.AF_UNIX)
        try:
            s.connect(str(paths.SOCKET_PATH))
            return s
        except OSError:  # missing / refused / stale socket, path too long, ...
            s.close()
        if not start or time.monotonic() > deadline:
            return None
        if not started:
            start_core()
            started = True
        time.sleep(0.2)


def start_core() -> None:
    if shutil.which("systemctl"):
        r = subprocess.run(["systemctl", "--user", "start", "crimson-core.service"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return
    # no systemd unit installed: start detached
    import sys
    subprocess.Popen([sys.executable, "-m", "crimson.core"], cwd=str(paths.PROJECT_DIR),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def request(cmd: dict, start: bool = False, timeout: float = 4.0) -> dict | None:
    s = connect(start=start)
    if not s:
        return None
    s.settimeout(timeout)
    try:
        s.sendall((json.dumps({**cmd, "id": 1}) + "\n").encode())
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                return None
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = json.loads(line)
                if msg.get("t") == "reply" and msg.get("id") == 1:
                    return msg
    except (socket.timeout, OSError, ValueError):
        return None
    finally:
        s.close()
