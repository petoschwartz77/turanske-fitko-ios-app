#!/usr/bin/env python3
"""Add the iPad icon variants required for universal iPhone+iPad App Store builds."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONSET = ROOT / "TuranskeFitkoApp" / "Assets.xcassets" / "AppIcon.appiconset"
SOURCE = ICONSET / "AppIcon-1024.png"
CONTENTS = ICONSET / "Contents.json"

IPAD_ICONS = [
    ("AppIcon-iPad-20.png", 20, "20x20", "1x"),
    ("AppIcon-iPad-40.png", 40, "20x20", "2x"),
    ("AppIcon-iPad-29.png", 29, "29x29", "1x"),
    ("AppIcon-iPad-58.png", 58, "29x29", "2x"),
    ("AppIcon-iPad-40pt.png", 40, "40x40", "1x"),
    ("AppIcon-iPad-80.png", 80, "40x40", "2x"),
    ("AppIcon-iPad-76.png", 76, "76x76", "1x"),
    ("AppIcon-iPad-152.png", 152, "76x76", "2x"),
    ("AppIcon-iPad-167.png", 167, "83.5x83.5", "2x"),
]


def resize(filename: str, pixels: int) -> None:
    output = ICONSET / filename
    subprocess.run(
        ["sips", "-z", str(pixels), str(pixels), str(SOURCE), "--out", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"Failed to generate {filename}")


def main() -> None:
    if not SOURCE.is_file():
        raise RuntimeError(f"Missing source icon: {SOURCE}")
    if not CONTENTS.is_file():
        raise RuntimeError(f"Missing asset catalog: {CONTENTS}")

    payload = json.loads(CONTENTS.read_text(encoding="utf-8"))
    images = [item for item in payload.get("images", []) if item.get("idiom") != "ipad"]

    for filename, pixels, size, scale in IPAD_ICONS:
        resize(filename, pixels)
        images.append(
            {
                "filename": filename,
                "idiom": "ipad",
                "size": size,
                "scale": scale,
            }
        )

    payload["images"] = images
    payload.setdefault("info", {"author": "xcode", "version": 1})
    CONTENTS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    required = [ICONSET / "AppIcon-iPad-152.png", ICONSET / "AppIcon-iPad-167.png"]
    for icon in required:
        if not icon.is_file() or icon.stat().st_size == 0:
            raise RuntimeError(f"Required iPad icon missing: {icon}")

    print("Prepared iPad App Store icons including 152x152 and 167x167")


if __name__ == "__main__":
    main()
