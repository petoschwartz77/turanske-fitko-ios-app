#!/usr/bin/env python3
"""Generate Turanské Fitko primary + Ružová iskra iOS app icon sets.

The two 1024px sources already ship with the WordPress app plugin. The build verifies exact
SHA-256 hashes so a wrong or stale icon can never silently reach TestFlight.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "TuranskeFitkoApp" / "Assets.xcassets"

PRIMARY_SET = ASSETS / "AppIcon.appiconset"
PINK_SET = ASSETS / "AppIconPink.appiconset"

BASE_URL = (
    "https://turanskefitko.sk/wp-content/plugins/"
    "turanske-fitko-manager-mobile-app-mode/assets/native-icon/"
)
SOURCES = {
    "primary": {
        "url": BASE_URL + "primary-1024.jpg",
        "sha256": "fa7ac64da038befa7d59d9748cfca19879701e72b3c42f179205038cf0b3e84a",
        "set": PRIMARY_SET,
        "prefix": "AppIcon",
    },
    "pink": {
        "url": BASE_URL + "pink-1024.jpg",
        "sha256": "853b5499ccf67877aac6207e097d6fb7eab686e52c15d99231acd52d77b58f62",
        "set": PINK_SET,
        "prefix": "AppIconPink",
    },
}

ICON_SPECS = [
    (120, "iphone", "60x60", "2x"),
    (180, "iphone", "60x60", "3x"),
    (20, "ipad", "20x20", "1x"),
    (40, "ipad", "20x20", "2x"),
    (29, "ipad", "29x29", "1x"),
    (58, "ipad", "29x29", "2x"),
    (40, "ipad", "40x40", "1x"),
    (80, "ipad", "40x40", "2x"),
    (76, "ipad", "76x76", "1x"),
    (152, "ipad", "76x76", "2x"),
    (167, "ipad", "83.5x83.5", "2x"),
]


def download(url: str, expected_sha: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TuranskeFitko-iOS-Builder/9.26"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()

    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha:
        raise RuntimeError(
            f"Icon checksum mismatch for {destination.name}. "
            f"Expected {expected_sha}, got {digest}."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    print(f"Verified {destination.name}: {digest}")


def resize(source: Path, output: Path, pixels: int) -> None:
    subprocess.run(
        ["sips", "-s", "format", "png", "-z", str(pixels), str(pixels), str(source), "--out", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Failed to generate {output.name}")


def build_icon_set(name: str, spec: dict) -> None:
    iconset: Path = spec["set"]
    prefix: str = spec["prefix"]
    iconset.mkdir(parents=True, exist_ok=True)

    source = iconset / f"{prefix}-source.jpg"
    download(spec["url"], spec["sha256"], source)

    images = []
    used_names = set()
    for pixels, idiom, size, scale in ICON_SPECS:
        # 40px occurs twice for iPad (20@2x and 40@1x), so include size+scale in the filename.
        safe_size = size.replace(".", "_").replace("x", "x")
        filename = f"{prefix}-{idiom}-{safe_size}-{scale}-{pixels}.png"
        if filename not in used_names:
            resize(source, iconset / filename, pixels)
            used_names.add(filename)
        images.append({
            "filename": filename,
            "idiom": idiom,
            "size": size,
            "scale": scale,
        })

    marketing = f"{prefix}-1024.png"
    resize(source, iconset / marketing, 1024)
    images.append({
        "filename": marketing,
        "idiom": "ios-marketing",
        "size": "1024x1024",
        "scale": "1x",
    })

    (iconset / "Contents.json").write_text(
        json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Prepared {name} icon set at {iconset.relative_to(ROOT)}")


def main() -> None:
    for name, spec in SOURCES.items():
        build_icon_set(name, spec)

    print("Primary icon = Original theme")
    print("Alternate icon AppIconPink = Ružová iskra")


if __name__ == "__main__":
    main()
