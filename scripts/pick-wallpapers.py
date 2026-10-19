#!/usr/bin/env python3
"""Rank the wallpapers in a folder for the Crimson theme and produce per-monitor derivatives.

    pick-wallpapers.py --dir "/home/rune/Downloads/home/jan/Downloads/pack 1"
    pick-wallpapers.py --dir DIR --left FILE --right FILE      # override the automatic choice

Originals are only ever READ. Derivatives (colour-graded, cropped to each monitor, plus a
pre-blurred copy for the dashboard's frosted tiles) go to <project>/wallpapers/generated/.
A contact sheet of the top candidates is written so you can review the choice.
Needs Pillow (python3-pillow).
"""

import argparse
import colorsys
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat
except ImportError:
    sys.exit("Pillow is required: sudo dnf install python3-pillow")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "crimson-desktop"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PALETTE_RAMP = [(11, 8, 13), (35, 11, 23), (90, 22, 45), (141, 36, 69), (213, 139, 159), (242, 183, 197)]


def analyse(path: Path) -> dict | None:
    try:
        with Image.open(path) as im:
            if getattr(im, "is_animated", False):
                return None
            w, h = im.size
            if w * h > 120_000_000:
                return None
            im.draft("RGB", (320, 180))
            small = ImageOps.exif_transpose(im).convert("RGB").resize((160, 90))
    except Exception as e:  # noqa: BLE001 - unreadable / unsupported file
        print(f"  skip {path.name}: {e}", file=sys.stderr)
        return None
    px = list(small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata())
    n = len(px)
    red = foreign = 0
    lum = sat = 0.0
    for r, g, b in px:
        hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        lum += 0.2126 * r / 255 + 0.7152 * g / 255 + 0.0722 * b / 255
        sat += ss
        if ss > 0.18 and vv > 0.08 and (hh < 0.06 or hh > 0.86):
            red += 1
        elif ss > 0.35 and vv > 0.25:
            foreign += 1
    edges = ImageStat.Stat(small.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0] / 255
    return {"path": str(path), "name": path.name, "w": w, "h": h, "lum": lum / n, "sat": sat / n,
            "red": red / n, "foreign": foreign / n, "busy": edges}


def score(a: dict, tw: int, th: int) -> float:
    dark = max(0.0, 1 - abs(a["lum"] - 0.17) / 0.35)
    res = min(1.0, a["w"] / max(1, tw)) * min(1.0, a["h"] / max(1, th))
    aspect = 1 - min(1.0, abs((a["w"] / a["h"]) - (tw / th)) / (tw / th))
    calm = 1 - min(1.0, a["busy"] * 4)
    return 0.38 * a["red"] + 0.25 * dark + 0.2 * res + 0.1 * aspect + 0.07 * calm - 0.35 * a["foreign"]


def cover(im: Image.Image, w: int, h: int) -> Image.Image:
    return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.5))


def grade(im: Image.Image, amount: float, darken: float) -> Image.Image:
    """Blend toward a crimson gradient map (keeps the image's tones, unifies its colours)."""
    gray = ImageOps.grayscale(im)
    lut = []
    for c in range(3):
        for i in range(256):
            t = i / 255 * (len(PALETTE_RAMP) - 1)
            k = min(int(t), len(PALETTE_RAMP) - 2)
            f = t - k
            lut.append(int(PALETTE_RAMP[k][c] * (1 - f) + PALETTE_RAMP[k + 1][c] * f))
    mapped = Image.merge("RGB", [gray.point(lut[c * 256:(c + 1) * 256]) for c in range(3)])
    out = Image.blend(im.convert("RGB"), mapped, amount)
    if darken:
        out = Image.blend(out, Image.new("RGB", out.size, (11, 8, 13)), darken)
    return out


def vignette(im: Image.Image, strength: float = 0.35) -> Image.Image:
    w, h = im.size
    mask = Image.new("L", (w // 8, h // 8), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((-w // 40, -h // 40, w // 8 + w // 40, h // 8 + h // 40), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(w // 60)).resize((w, h), Image.BICUBIC)
    dark = Image.new("RGB", (w, h), (8, 5, 8))
    return Image.composite(im, Image.blend(im, dark, strength), mask)


def contact_sheet(ranked: list[tuple[float, dict]], dest: Path) -> None:
    top = ranked[:12]
    tw, th, pad = 320, 180, 10
    cols = 4
    rows = (len(top) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + 40 + pad) + pad), (11, 8, 13))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(str(ROOT / "fonts" / "SpaceMono-Regular.ttf"), 12)
    except OSError:
        font = ImageFont.load_default()
    for i, (s, a) in enumerate(top):
        x, y = pad + (i % cols) * (tw + pad), pad + (i // cols) * (th + 40 + pad)
        with Image.open(a["path"]) as im:
            im.draft("RGB", (tw * 2, th * 2))
            sheet.paste(cover(ImageOps.exif_transpose(im).convert("RGB"), tw, th), (x, y))
        d.text((x, y + th + 4), f"#{i + 1}  {a['name'][:34]}", fill=(242, 183, 197), font=font)
        d.text((x, y + th + 20), f"score {s:.2f}  red {a['red']:.0%}  {a['w']}x{a['h']}", fill=(168, 139, 152), font=font)
    sheet.save(dest, quality=88)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--monitors", default=str(CONFIG_DIR / "monitors.json"))
    ap.add_argument("--left", help="force this file for the left monitor")
    ap.add_argument("--right", help="force this file for the right monitor")
    ap.add_argument("--out", default=str(ROOT / "wallpapers" / "generated"))
    ap.add_argument("--dry-run", action="store_true", help="rank only, write nothing")
    a = ap.parse_args()

    src = Path(a.dir).expanduser()
    if not src.is_dir():
        sys.exit(f"wallpaper directory not found: {src}")
    mons = {}
    try:
        mons = json.loads(Path(a.monitors).read_text())
    except (OSError, ValueError):
        pass
    by_name = {o["name"]: o for o in mons.get("outputs", [])}
    left = by_name.get(mons.get("left")) or {"name": "left", "width": 2560, "height": 1440}
    right = by_name.get(mons.get("right")) or {"name": "right", "width": 2560, "height": 1440}

    files = sorted(p for p in src.rglob("*") if p.suffix.lower() in EXTS and p.is_file())
    print(f"scanning {len(files)} images in {src} ...")
    infos = [i for i in (analyse(p) for p in files) if i]
    if not infos:
        sys.exit("no usable images found")
    rank_r = sorted(((score(i, right["width"], right["height"]), i) for i in infos), key=lambda x: -x[0])
    rank_l = sorted(((score(i, left["width"], left["height"]), i) for i in infos), key=lambda x: -x[0])

    pick_r = next((i for _, i in rank_r if a.right and Path(i["path"]).resolve() == Path(a.right).expanduser().resolve()), rank_r[0][1])
    if a.left:
        pick_l = next((i for _, i in rank_l if Path(i["path"]).resolve() == Path(a.left).expanduser().resolve()), rank_l[0][1])
    else:
        # a different image for the left monitor when a good one exists
        pick_l = next((i for s, i in rank_l if i["path"] != pick_r["path"] and s > rank_l[0][0] * 0.8), rank_l[0][1])

    print("\nrank  score  red   dark  res          file")
    for k, (s, i) in enumerate(rank_r[:15], 1):
        mark = " ◀ right" if i is pick_r else (" ◀ left" if i is pick_l else "")
        print(f"{k:>3}  {s:5.2f}  {i['red']:4.0%}  {i['lum']:4.2f}  {i['w']}x{i['h']:<6} {i['name']}{mark}")
    if a.dry_run:
        return

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    contact_sheet(rank_r, out / "candidates.jpg")

    def load(info):
        with Image.open(info["path"]) as im:
            return ImageOps.exif_transpose(im).convert("RGB")

    rw, rh = right["width"] or 2560, right["height"] or 1440
    lw, lh = left["width"] or 2560, left["height"] or 1440
    r_img = vignette(grade(cover(load(pick_r), rw, rh), 0.30, 0.12))
    r_img.save(out / "right.jpg", quality=93)
    blur = r_img.resize((max(1, rw // 4), max(1, rh // 4)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(10))
    blur = Image.blend(blur, Image.new("RGB", blur.size, (20, 7, 13)), 0.25)
    blur.resize((max(1, rw // 2), max(1, rh // 2)), Image.BICUBIC).save(out / "right-blur.jpg", quality=88)
    l_img = vignette(grade(cover(load(pick_l), lw, lh), 0.18, 0.05), 0.25)
    l_img.save(out / "left.jpg", quality=93)
    lock = Image.blend(l_img.filter(ImageFilter.GaussianBlur(6)), Image.new("RGB", l_img.size, (11, 8, 13)), 0.35)
    lock.save(out / "lockscreen.jpg", quality=90)

    state = {
        "source_dir": str(src),
        "left": {"output": left["name"], "source": pick_l["path"], "image": str(out / "left.jpg")},
        "right": {"output": right["name"], "source": pick_r["path"], "image": str(out / "right.jpg"),
                  "blur": str(out / "right-blur.jpg")},
        "lockscreen": str(out / "lockscreen.jpg"),
        "by_output": {right["name"]: {"image": str(out / "right.jpg"), "blur": str(out / "right-blur.jpg")}},
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "wallpapers.json").write_text(json.dumps(state, indent=2))
    print(f"\nright monitor ({right['name']}): {pick_r['name']}\nleft monitor  ({left['name']}): {pick_l['name']}")
    print(f"derivatives + contact sheet: {out}\nstate: {CONFIG_DIR / 'wallpapers.json'}")


if __name__ == "__main__":
    main()
