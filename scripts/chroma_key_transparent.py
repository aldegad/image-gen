#!/usr/bin/env python3
"""Convert image_gen chroma-key output into a clean transparent PNG.

Use this for generated images that were prompted with a solid #FF00FF magenta
or #00FF00 green background. It removes the key color, clears RGB for fully
transparent pixels, and optionally neutralizes semi-transparent chroma fringe.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


KEYS = {
    "magenta": {
        "target": (255, 0, 255),
        "min_primary": 170,
        "max_opposite": 115,
        "min_delta": 70,
    },
    "green": {
        "target": (0, 255, 0),
        "min_primary": 170,
        "max_opposite": 115,
        "min_delta": 70,
    },
}


def is_key_pixel(r: int, g: int, b: int, key: str, min_primary: int, max_opposite: int, min_delta: int) -> bool:
    if key == "magenta":
        return (
            r >= min_primary
            and b >= min_primary
            and g <= max_opposite
            and (r - g) >= min_delta
            and (b - g) >= min_delta
        )
    return (
        g >= min_primary
        and r <= max_opposite
        and b <= max_opposite
        and (g - r) >= min_delta
        and (g - b) >= min_delta
    )


def is_fringe_pixel(r: int, g: int, b: int, key: str, threshold: int) -> bool:
    if key == "magenta":
        return (r - g) > threshold and (b - g) > threshold
    return (g - r) > threshold and (g - b) > threshold


def neutralize_fringe(r: int, g: int, b: int, a: int, key: str) -> tuple[int, int, int, int]:
    if key == "magenta":
        neutral = g
    else:
        neutral = max(r, b)
    return (neutral, neutral, neutral, max(0, a // 3))


def write_white_check(image: Image.Image, path: Path) -> None:
    bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
    bg.alpha_composite(image)
    bg.convert("RGB").save(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove solid chroma background from generated images and write a clean RGBA PNG."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--key", choices=sorted(KEYS), default="magenta")
    parser.add_argument("--min-primary", type=int, default=None)
    parser.add_argument("--max-opposite", type=int, default=None)
    parser.add_argument("--min-delta", type=int, default=None)
    parser.add_argument("--fringe-threshold", type=int, default=4)
    parser.add_argument("--fringe-alpha-max", type=int, default=239)
    parser.add_argument("--no-fringe-cleanup", action="store_true")
    parser.add_argument("--white-check", type=Path, default=None)
    args = parser.parse_args()

    defaults = KEYS[args.key]
    min_primary = args.min_primary if args.min_primary is not None else defaults["min_primary"]
    max_opposite = args.max_opposite if args.max_opposite is not None else defaults["max_opposite"]
    min_delta = args.min_delta if args.min_delta is not None else defaults["min_delta"]

    image = Image.open(args.input).convert("RGBA")
    pixels = image.load()
    width, height = image.size
    keyed = 0
    fringe = 0
    cleaned_rgb = 0

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a and is_key_pixel(r, g, b, args.key, min_primary, max_opposite, min_delta):
                pixels[x, y] = (0, 0, 0, 0)
                keyed += 1
                continue

            if a == 0:
                if r or g or b:
                    pixels[x, y] = (0, 0, 0, 0)
                    cleaned_rgb += 1
                continue

            if (
                not args.no_fringe_cleanup
                and 0 < a <= args.fringe_alpha_max
                and is_fringe_pixel(r, g, b, args.key, args.fringe_threshold)
            ):
                pixels[x, y] = neutralize_fringe(r, g, b, a, args.key)
                fringe += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out)

    if args.white_check:
        args.white_check.parent.mkdir(parents=True, exist_ok=True)
        write_white_check(image, args.white_check)

    total = width * height
    alpha_zero = 0
    stale_rgb = 0
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                alpha_zero += 1
                if r or g or b:
                    stale_rgb += 1

    print(f"wrote={args.out}")
    print(f"mode=RGBA")
    print(f"size={width}x{height}")
    print(f"key={args.key}")
    print(f"keyed_pixels={keyed}")
    print(f"fringe_pixels={fringe}")
    print(f"cleaned_transparent_rgb_pixels={cleaned_rgb}")
    print(f"alpha_zero_pct={alpha_zero / total * 100:.2f}")
    print(f"stale_transparent_rgb_pixels={stale_rgb}")
    if stale_rgb:
        raise SystemExit("transparent pixels still contain non-zero RGB")


if __name__ == "__main__":
    main()
