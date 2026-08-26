#!/usr/bin/env python3
"""Build the iOS AppIcon set from the exact Turanské Fitko icon approved on 23 Jul 2026."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICONSET = ROOT / "TuranskeFitkoApp" / "Assets.xcassets" / "AppIcon.appiconset"
SOURCE = ICONSET / "AppIcon-approved-source.png"
ICON_1024 = ICONSET / "AppIcon-1024.png"
ICON_180 = ICONSET / "AppIcon-180.png"
ICON_120 = ICONSET / "AppIcon-120.png"

APPROVED_URL = (
    "https://turanskefitko.sk/wp-content/plugins/"
    "turanske-fitko-manager-mobile-app-mode/assets/app-icon-approved.png?tfma_v=9.24"
)
APPROVED_SHA256 = "99d9771aff470a6ce92ab7b26888434d2f74f1f95e07393533414ff4f92a30bb"


def download_approved_icon() -> None:
    request = urllib.request.Request(
        APPROVED_URL,
        headers={"User-Agent": "TuranskeFitko-iOS-Builder/9.24"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()

    digest = hashlib.sha256(payload).hexdigest()
    if digest != APPROVED_SHA256:
        raise RuntimeError(
            "Approved app icon checksum mismatch. Refusing to build another icon. "
            f"Expected {APPROVED_SHA256}, got {digest}."
        )

    ICONSET.mkdir(parents=True, exist_ok=True)
    SOURCE.write_bytes(payload)
    print(f"Downloaded exact approved icon ({len(payload)} bytes, sha256={digest})")


def sips_resize(source: Path, output: Path, pixels: int) -> None:
    subprocess.run(
        ["sips", "-z", str(pixels), str(pixels), str(source), "--out", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Failed to generate {output.name}")


def main() -> None:
    download_approved_icon()

    # Always derive every iOS size from the same approved square source.
    sips_resize(SOURCE, ICON_1024, 1024)
    sips_resize(ICON_1024, ICON_180, 180)
    sips_resize(ICON_1024, ICON_120, 120)

    contents = {
        "images": [
            {
                "filename": ICON_120.name,
                "idiom": "iphone",
                "size": "60x60",
                "scale": "2x",
            },
            {
                "filename": ICON_180.name,
                "idiom": "iphone",
                "size": "60x60",
                "scale": "3x",
            },
            {
                "filename": ICON_1024.name,
                "idiom": "ios-marketing",
                "size": "1024x1024",
                "scale": "1x",
            },
        ],
        "info": {"author": "xcode", "version": 1},
    }
    (ICONSET / "Contents.json").write_text(
        json.dumps(contents, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for icon in (SOURCE, ICON_1024, ICON_180, ICON_120):
        if not icon.is_file() or icon.stat().st_size == 0:
            raise RuntimeError(f"Icon generation failed: {icon}")
        print(f"Prepared {icon.relative_to(ROOT)} ({icon.stat().st_size} bytes)")

    print("App icon source: exact user-approved Turanské Fitko icon, 23 Jul 2026")


if __name__ == "__main__":
    main()
