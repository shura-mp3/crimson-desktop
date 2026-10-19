#!/usr/bin/env python3
"""Generate bundled textures: film grain, scanlines and a procedural marbled-crimson fallback
wallpaper (domain-warped noise, like the reference's red fluid background).

    python3 scripts/generate-assets.py [--width 3840 --height 2160]
Needs numpy + Pillow. Outputs are committed, so this only needs re-running to regenerate.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent


def fbm(h, w, rng, octaves=6, base=3):
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = base * 2 ** o
        small = rng.random((cells + 1, int(cells * w / h) + 1)).astype(np.float32)
        up = np.asarray(Image.fromarray(small).resize((w, h), Image.BICUBIC), np.float32)
        out += up * amp
        total += amp
        amp *= 0.5
    return out / total


def sample(img, y, x):
    h, w = img.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = x - x0, y - y0
    a = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    b = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def marble(w, h, seed=7):
    rng = np.random.default_rng(seed)
    sh, sw = h // 2, w // 2  # compute at half resolution, upscale (the pattern is smooth)
    n1, n2, n3 = (fbm(sh, sw, rng) for _ in range(3))
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    k = sh * 0.22
    qx = sample(n1, yy, xx) - 0.5
    qy = sample(n2, yy, xx) - 0.5
    rx = sample(n2, yy + k * qy, xx + k * qx) - 0.5
    ry = sample(n3, yy + k * qy, xx + k * qx) - 0.5
    f = sample(n1, yy + k * 1.6 * ry, xx + k * 1.6 * rx)
    f = (f - f.min()) / (f.max() - f.min())
    # thin bright veins where the warped field crosses iso-lines
    veins = np.abs(np.sin(f * 38.0)) ** 0.35
    veins = 1 - veins
    stops = np.array([0.0, 0.25, 0.5, 0.72, 0.88, 1.0])
    cols = np.array([[18, 6, 11], [52, 12, 24], [104, 22, 44], [146, 40, 66], [190, 92, 112], [236, 170, 186]], np.float32)
    rgb = np.stack([np.interp(f, stops, cols[:, c]) for c in range(3)], -1)
    vein_col = np.array([242, 183, 197], np.float32)
    rgb = rgb * (1 - veins[..., None] * 0.55) + vein_col * veins[..., None] * 0.55
    # darken overall so widgets stay readable; vignette
    vy, vx = np.mgrid[-1:1:complex(sh), -1:1:complex(sw)]
    vig = 1 - 0.45 * np.clip(np.sqrt(vx ** 2 + vy ** 2) - 0.25, 0, 1)
    rgb *= (0.72 * vig)[..., None]
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((w, h), Image.LANCZOS)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=3840)
    ap.add_argument("--height", type=int, default=2160)
    a = ap.parse_args()
    assets = ROOT / "dashboard" / "assets"
    walls = ROOT / "wallpapers"
    assets.mkdir(parents=True, exist_ok=True)
    walls.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(1)
    g = (rng.random((256, 256)) * 255).astype(np.uint8)
    grain = Image.merge("RGBA", [Image.fromarray(g)] * 3 + [Image.fromarray((rng.random((256, 256)) * 255).astype(np.uint8))])
    grain.save(assets / "grain.png", optimize=True)

    scan = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    for x in range(4):
        scan.putpixel((x, 3), (0, 0, 0, 140))
    scan.save(assets / "scanlines.png")

    wall = marble(a.width, a.height)
    wall.save(walls / "crimson-fallback.jpg", quality=92, optimize=True)
    blur = wall.resize((a.width // 4, a.height // 4), Image.LANCZOS).filter(ImageFilter.GaussianBlur(10))
    blur = Image.blend(blur, Image.new("RGB", blur.size, (20, 7, 13)), 0.25)
    blur.resize((a.width // 2, a.height // 2), Image.BICUBIC).save(walls / "crimson-fallback-blur.jpg", quality=88)
    print("assets written to", assets, "and", walls)


if __name__ == "__main__":
    main()
