#!/usr/bin/env python3
"""Generate the iOS AppIcon set from the original approved Turanské Fitko v6.99 icon.

This is intentionally a recovery-only packaging script. It does not change app behavior.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONSET = ROOT / "TuranskeFitkoApp" / "Assets.xcassets" / "AppIcon.appiconset"
SOURCE = ICONSET / "AppIcon-original-v699.png"

SOURCE_URL = (
    "https://turanskefitko.sk/wp-content/plugins/"
    "turanske-fitko-manager-mobile-app-mode/assets/app-icon/"
    "turanske-fitko-app-icon-1024.png"
)
SOURCE_SHA256 = "fe78336b9275c1767a8358a15f68fe108de0fbb72f7db94a15dbe004a94bdd69"

ICON_SPECS = [
    # iPhone
    ("AppIcon-120.png", 120, "iphone", "60x60", "2x"),
    ("AppIcon-180.png", 180, "iphone", "60x60", "3x"),
    # iPad - kept only because the already approved App Store record requires it.
    ("AppIcon-iPad-20.png", 20, "ipad", "20x20", "1x"),
    ("AppIcon-iPad-40.png", 40, "ipad", "20x20", "2x"),
    ("AppIcon-iPad-29.png", 29, "ipad", "29x29", "1x"),
    ("AppIcon-iPad-58.png", 58, "ipad", "29x29", "2x"),
    ("AppIcon-iPad-40pt.png", 40, "ipad", "40x40", "1x"),
    ("AppIcon-iPad-80.png", 80, "ipad", "40x40", "2x"),
    ("AppIcon-iPad-76.png", 76, "ipad", "76x76", "1x"),
    ("AppIcon-iPad-152.png", 152, "ipad", "76x76", "2x"),
    ("AppIcon-iPad-167.png", 167, "ipad", "83.5x83.5", "2x"),
]


def download_source() -> None:
    ICONSET.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "TuranskeFitko-Recovery-Builder/1.2"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()

    digest = hashlib.sha256(payload).hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError(
            "The original approved v6.99 app icon changed or is unavailable. "
            f"Expected sha256 {SOURCE_SHA256}, got {digest}."
        )
    SOURCE.write_bytes(payload)


def resize(output: Path, pixels: int) -> None:
    subprocess.run(
        ["sips", "-z", str(pixels), str(pixels), str(SOURCE), "--out", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Failed to generate {output.name}")


def main() -> None:
    download_source()

    marketing = ICONSET / "AppIcon-1024.png"
    resize(marketing, 1024)

    images = []
    for filename, pixels, idiom, size, scale in ICON_SPECS:
        output = ICONSET / filename
        resize(output, pixels)
        images.append(
            {
                "filename": filename,
                "idiom": idiom,
                "size": size,
                "scale": scale,
            }
        )

    images.append(
        {
            "filename": marketing.name,
            "idiom": "ios-marketing",
            "size": "1024x1024",
            "scale": "1x",
        }
    )

    payload = {
        "images": images,
        "info": {"author": "xcode", "version": 1},
    }
    (ICONSET / "Contents.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Original v6.99 icon verified: {SOURCE_SHA256}")
    print("Prepared iPhone + App-Store-required iPad icon sizes from the exact same source")


if __name__ == "__main__":
    main()
