#!/usr/bin/env python3
"""Generate primary and alternate iOS app icons from the live TF plugin assets."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "TuranskeFitkoApp" / "Assets.xcassets"
PRIMARY_SET = ASSETS / "AppIcon.appiconset"
PINK_SET = ASSETS / "PinkIcon.appiconset"

PRIMARY_URL = (
    "https://turanskefitko.sk/wp-content/plugins/"
    "turanske-fitko-manager-mobile-app-mode/assets/native-icon/primary-1024.jpg?v=810"
)
PINK_URL = (
    "https://turanskefitko.sk/wp-content/plugins/"
    "turanske-fitko-manager-mobile-app-mode/assets/native-icon/pink-1024.jpg?v=810"
)

# Complete legacy iPhone + iPad icon matrix. The primary set also gets the
# 1024x1024 App Store marketing icon. Alternate icons do not need marketing art.
DEVICE_SLOTS = [
    ("iphone", "20x20", "2x", 40),
    ("iphone", "20x20", "3x", 60),
    ("iphone", "29x29", "2x", 58),
    ("iphone", "29x29", "3x", 87),
    ("iphone", "40x40", "2x", 80),
    ("iphone", "40x40", "3x", 120),
    ("iphone", "60x60", "2x", 120),
    ("iphone", "60x60", "3x", 180),
    ("ipad", "20x20", "1x", 20),
    ("ipad", "20x20", "2x", 40),
    ("ipad", "29x29", "1x", 29),
    ("ipad", "29x29", "2x", 58),
    ("ipad", "40x40", "1x", 40),
    ("ipad", "40x40", "2x", 80),
    ("ipad", "76x76", "1x", 76),
    ("ipad", "76x76", "2x", 152),
    ("ipad", "83.5x83.5", "2x", 167),
]


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def fetch(url: str, destination: Path) -> None:
    run(
        "curl",
        "-fL",
        "--retry",
        "4",
        "--retry-delay",
        "2",
        "--connect-timeout",
        "20",
        "--max-time",
        "90",
        "-A",
        "TuranskeFitko-iOS-Codemagic/1.1",
        "-o",
        str(destination),
        url,
    )
    if not destination.is_file() or destination.stat().st_size < 20_000:
        raise RuntimeError(f"Downloaded icon source is missing or suspiciously small: {destination}")


def image_dimensions(path: Path) -> tuple[int, int]:
    output = subprocess.check_output(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        text=True,
    )
    width = height = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":", 1)[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":", 1)[1].strip())
    if width is None or height is None:
        raise RuntimeError(f"Could not read image dimensions for {path}")
    return width, height


def prepare_source(url: str, destination: Path) -> None:
    fetch(url, destination)
    width, height = image_dimensions(destination)
    if width != height or width < 1024:
        raise RuntimeError(
            f"App icon source must be square and at least 1024px; got {width}x{height}: {url}"
        )


def png_resize(source: Path, destination: Path, pixels: int) -> None:
    run(
        "sips",
        "-s",
        "format",
        "png",
        "-z",
        str(pixels),
        str(pixels),
        str(source),
        "--out",
        str(destination),
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"Failed to generate icon: {destination}")


def reset_iconset(iconset: Path) -> None:
    iconset.mkdir(parents=True, exist_ok=True)
    for child in iconset.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def build_iconset(iconset: Path, source: Path, prefix: str, include_marketing: bool) -> None:
    reset_iconset(iconset)
    images: list[dict[str, str]] = []

    for index, (idiom, size, scale, pixels) in enumerate(DEVICE_SLOTS, start=1):
        safe_size = size.replace(".", "_")
        filename = f"{prefix}-{idiom}-{safe_size}-{scale}-{pixels}.png"
        png_resize(source, iconset / filename, pixels)
        images.append(
            {
                "filename": filename,
                "idiom": idiom,
                "scale": scale,
                "size": size,
            }
        )

    if include_marketing:
        filename = f"{prefix}-marketing-1024.png"
        png_resize(source, iconset / filename, 1024)
        images.append(
            {
                "filename": filename,
                "idiom": "ios-marketing",
                "scale": "1x",
                "size": "1024x1024",
            }
        )

    payload = {"images": images, "info": {"author": "xcode", "version": 1}}
    (iconset / "Contents.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tfm-app-icons-") as temp:
        temp_dir = Path(temp)
        primary_source = temp_dir / "primary-1024.jpg"
        pink_source = temp_dir / "pink-1024.jpg"

        prepare_source(PRIMARY_URL, primary_source)
        prepare_source(PINK_URL, pink_source)

        build_iconset(PRIMARY_SET, primary_source, "AppIcon", include_marketing=True)
        build_iconset(PINK_SET, pink_source, "PinkIcon", include_marketing=False)

    print(f"Primary icon generated from: {PRIMARY_URL}")
    print(f"Pink alternate icon generated from: {PINK_URL}")
    print("Generated full iPhone+iPad icon matrices for AppIcon and PinkIcon.")


if __name__ == "__main__":
    main()
