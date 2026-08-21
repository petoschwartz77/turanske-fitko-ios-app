#!/usr/bin/env python3
"""Expand AppIcon.appiconset for iPhone + iPad from the generated 1024px source."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONSET = ROOT / "TuranskeFitkoApp" / "Assets.xcassets" / "AppIcon.appiconset"
SOURCE = ICONSET / "AppIcon-1024.png"


def run_sips(size: int, output: Path) -> None:
    subprocess.run(
        ["sips", "-z", str(size), str(size), str(SOURCE), "--out", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def icon_name(size: int) -> str:
    return f"AppIcon-{size}.png"


def main() -> None:
    if not SOURCE.is_file() or SOURCE.stat().st_size == 0:
        raise RuntimeError("AppIcon-1024.png must exist before generating device icons.")

    required_pixel_sizes = [20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180]
    for size in required_pixel_sizes:
        output = ICONSET / icon_name(size)
        if size == 120 and output.is_file() and output.stat().st_size > 0:
            continue
        if size == 180 and output.is_file() and output.stat().st_size > 0:
            continue
        run_sips(size, output)

    images = [
        # iPhone notification / settings / spotlight / app icons.
        {"filename": icon_name(40), "idiom": "iphone", "size": "20x20", "scale": "2x"},
        {"filename": icon_name(60), "idiom": "iphone", "size": "20x20", "scale": "3x"},
        {"filename": icon_name(58), "idiom": "iphone", "size": "29x29", "scale": "2x"},
        {"filename": icon_name(87), "idiom": "iphone", "size": "29x29", "scale": "3x"},
        {"filename": icon_name(80), "idiom": "iphone", "size": "40x40", "scale": "2x"},
        {"filename": icon_name(120), "idiom": "iphone", "size": "40x40", "scale": "3x"},
        {"filename": icon_name(120), "idiom": "iphone", "size": "60x60", "scale": "2x"},
        {"filename": icon_name(180), "idiom": "iphone", "size": "60x60", "scale": "3x"},
        # iPad notification / settings / spotlight / app icons.
        {"filename": icon_name(20), "idiom": "ipad", "size": "20x20", "scale": "1x"},
        {"filename": icon_name(40), "idiom": "ipad", "size": "20x20", "scale": "2x"},
        {"filename": icon_name(29), "idiom": "ipad", "size": "29x29", "scale": "1x"},
        {"filename": icon_name(58), "idiom": "ipad", "size": "29x29", "scale": "2x"},
        {"filename": icon_name(40), "idiom": "ipad", "size": "40x40", "scale": "1x"},
        {"filename": icon_name(80), "idiom": "ipad", "size": "40x40", "scale": "2x"},
        {"filename": icon_name(76), "idiom": "ipad", "size": "76x76", "scale": "1x"},
        {"filename": icon_name(152), "idiom": "ipad", "size": "76x76", "scale": "2x"},
        {"filename": icon_name(167), "idiom": "ipad", "size": "83.5x83.5", "scale": "2x"},
        # App Store icon.
        {"filename": SOURCE.name, "idiom": "ios-marketing", "size": "1024x1024", "scale": "1x"},
    ]

    contents = {"images": images, "info": {"author": "xcode", "version": 1}}
    (ICONSET / "Contents.json").write_text(
        json.dumps(contents, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    must_exist = [SOURCE, ICONSET / icon_name(152), ICONSET / icon_name(167)]
    for icon in must_exist:
        if not icon.is_file() or icon.stat().st_size == 0:
            raise RuntimeError(f"Missing required icon: {icon}")

    print("Generated complete iPhone + iPad AppIcon set.")


if __name__ == "__main__":
    main()
