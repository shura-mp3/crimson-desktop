#!/usr/bin/env python3
"""Detect monitors on KDE Plasma (Wayland) with kscreen-doctor and decide which is LEFT / RIGHT.

    detect-monitors.py            print a table
    detect-monitors.py --write    also save ~/.config/crimson-desktop/monitors.json
    detect-monitors.py --json     print JSON

Left/right is decided from the actual layout positions, never from connector names.
Nothing here changes your display configuration.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "crimson-desktop"


def from_json(raw: str) -> list[dict]:
    data = json.loads(raw)
    outs = []
    for o in data.get("outputs", []):
        if not o.get("connected", True):
            continue
        mode = next((m for m in o.get("modes", []) if str(m.get("id")) == str(o.get("currentModeId"))), {})
        msize = mode.get("size") or o.get("size") or {}
        w, h = int(msize.get("width", 0)), int(msize.get("height", 0))
        scale = float(o.get("scale", 1.0) or 1.0)
        rot = int(o.get("rotation", 1) or 1)  # 1 none, 2 left(90), 4 inverted, 8 right(270)
        lw, lh = (h, w) if rot in (2, 8) else (w, h)
        outs.append({
            "name": o.get("name"),
            "enabled": bool(o.get("enabled", False)),
            "x": int((o.get("pos") or {}).get("x", 0)),
            "y": int((o.get("pos") or {}).get("y", 0)),
            "width": w, "height": h,
            "logical_width": round(lw / scale), "logical_height": round(lh / scale),
            "refresh": round(float(mode.get("refreshRate", 0) or 0), 2),
            "scale": scale,
            "rotation": rot,
            "primary": o.get("priority") == 1 or bool(o.get("primary")),
            "priority": o.get("priority"),
        })
    return outs


def from_text(raw: str) -> list[dict]:
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    outs = []
    for block in re.split(r"\n(?=Output:)", raw):
        m = re.match(r"Output:\s+\d+\s+(\S+)", block)
        if not m or " connected" not in block:
            continue
        geo = re.search(r"Geometry:\s*(-?\d+),(-?\d+)\s+(\d+)x(\d+)", block)
        scale = re.search(r"Scale:\s*([\d.]+)", block)
        cur = re.search(r"\d+:(\d+)x(\d+)@([\d.]+)\*", block)
        prio = re.search(r"priority\s+(\d+)", block)
        sc = float(scale.group(1)) if scale else 1.0
        outs.append({
            "name": m.group(1),
            "enabled": " enabled" in block.split("\n")[0],
            "x": int(geo.group(1)) if geo else 0, "y": int(geo.group(2)) if geo else 0,
            "width": int(cur.group(1)) if cur else 0, "height": int(cur.group(2)) if cur else 0,
            "logical_width": int(geo.group(3)) if geo else 0, "logical_height": int(geo.group(4)) if geo else 0,
            "refresh": float(cur.group(3)) if cur else 0.0,
            "scale": sc, "rotation": 1,
            "primary": bool(prio and prio.group(1) == "1") or "primary" in block.split("\n")[0],
            "priority": int(prio.group(1)) if prio else None,
        })
    return outs


def detect() -> dict:
    if not shutil.which("kscreen-doctor"):
        return {"error": "kscreen-doctor not found (it ships with Plasma's kscreen package)", "outputs": []}
    method = "kscreen-doctor -j"
    r = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True)
    outs = []
    if r.returncode == 0 and r.stdout.strip().startswith("{"):
        try:
            outs = from_json(r.stdout)
        except (ValueError, KeyError, TypeError):
            outs = []
    if not outs:
        method = "kscreen-doctor -o"
        r = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True)
        outs = from_text(r.stdout)
    enabled = [o for o in outs if o["enabled"]]
    res = {"detected_with": method, "outputs": outs, "left": None, "right": None, "arrangement": "single"}
    if len(enabled) >= 2:
        xs = sorted(enabled, key=lambda o: (o["x"], o["y"]))
        if xs[0]["x"] == xs[-1]["x"]:
            res["arrangement"] = "vertical (stacked)"
            ys = sorted(enabled, key=lambda o: o["y"])
            res["left"], res["right"] = ys[0]["name"], ys[-1]["name"]  # top = productivity, bottom = dashboard
        else:
            res["arrangement"] = "horizontal"
            res["left"], res["right"] = xs[0]["name"], xs[-1]["name"]
    elif enabled:
        res["left"] = res["right"] = enabled[0]["name"]
    return res


def main() -> None:
    res = detect()
    if "--json" in sys.argv:
        print(json.dumps(res, indent=2))
    else:
        if res.get("error"):
            sys.exit(res["error"])
        print(f"detected with: {res['detected_with']}   arrangement: {res['arrangement']}")
        print(f"{'connector':12} {'role':6} {'mode':18} {'logical':12} {'pos':12} {'scale':6} {'primary':8} enabled")
        for o in res["outputs"]:
            role = "LEFT" if o["name"] == res["left"] else "RIGHT" if o["name"] == res["right"] else ""
            if res["left"] == res["right"] == o["name"]:
                role = "ONLY"
            print(f"{o['name']:12} {role:6} {o['width']}x{o['height']}@{o['refresh']:<8} "
                  f"{o['logical_width']}x{o['logical_height']:<6} {str(o['x']) + ',' + str(o['y']):12} "
                  f"{o['scale']:<6} {'yes' if o['primary'] else 'no':8} {'yes' if o['enabled'] else 'no'}")
        if res["left"] and res["left"] != res["right"]:
            print(f"\nleft (productivity) = {res['left']}, right (music dashboard) = {res['right']}")
    if "--write" in sys.argv:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "monitors.json").write_text(json.dumps(res, indent=2))
        if "--json" not in sys.argv:
            print(f"saved {CONFIG_DIR / 'monitors.json'}")


if __name__ == "__main__":
    main()
