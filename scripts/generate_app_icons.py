#!/usr/bin/env python3
"""Generate Turanské Fitko iOS app icons using only the Python standard library."""

from __future__ import annotations

import json
import math
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICONSET = ROOT / "TuranskeFitkoApp" / "Assets.xcassets" / "AppIcon.appiconset"
SOURCE_BMP = ICONSET / "AppIcon-source.bmp"
ICON_1024 = ICONSET / "AppIcon-1024.png"
ICON_180 = ICONSET / "AppIcon-180.png"
ICON_120 = ICONSET / "AppIcon-120.png"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    t = clamp((value - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def rectangle_distance(
    x: float,
    y: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
) -> float:
    dx = max(left - x, 0.0, x - right)
    dy = max(top - y, 0.0, y - bottom)
    outside = math.hypot(dx, dy)
    if outside > 0.0:
        return outside
    return -min(x - left, right - x, y - top, bottom - y)


def ellipse_distance(
    x: float,
    y: float,
    center_x: float,
    center_y: float,
    radius_x: float,
    radius_y: float,
) -> float:
    normalized = math.hypot(
        (x - center_x) / radius_x,
        (y - center_y) / radius_y,
    )
    return (normalized - 1.0) * min(radius_x, radius_y)


def generate_rgb(width: int = 1024, height: int = 1024) -> bytes:
    logo_rectangles = (
        (270.0, 315.0, 525.0, 410.0),
        (370.0, 385.0, 470.0, 690.0),
        (500.0, 335.0, 600.0, 700.0),
        (500.0, 335.0, 760.0, 430.0),
        (500.0, 500.0, 700.0, 585.0),
    )
    paw_ellipses = (
        (512.0, 790.0, 66.0, 48.0),
        (438.0, 735.0, 27.0, 34.0),
        (488.0, 715.0, 29.0, 38.0),
        (544.0, 715.0, 29.0, 38.0),
        (594.0, 735.0, 27.0, 34.0),
    )
    particles = (
        (220.0, 260.0, 5.0),
        (790.0, 280.0, 4.0),
        (190.0, 700.0, 4.0),
        (820.0, 650.0, 5.0),
        (280.0, 790.0, 3.0),
        (740.0, 780.0, 3.0),
        (145.0, 470.0, 3.0),
        (875.0, 470.0, 3.0),
        (320.0, 195.0, 2.0),
        (690.0, 190.0, 2.0),
    )

    pixels = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            dx = (x - 512.0) / 720.0
            dy = (y - 485.0) / 720.0
            radius = math.hypot(dx, dy)
            vignette = clamp(1.0 - radius)

            glow_x = (x - 512.0) / 430.0
            glow_y = (y - 560.0) / 500.0
            center_glow = math.exp(
                -(glow_x * glow_x + glow_y * glow_y) * 2.4
            )

            warm_x = (x - 480.0) / 600.0
            warm_y = (y - 250.0) / 500.0
            warm_glow = math.exp(
                -(warm_x * warm_x + warm_y * warm_y) * 3.2
            )

            red = 3.0 + 8.0 * vignette + 3.0 * warm_glow
            green = (
                4.0
                + 12.0 * vignette
                + 16.0 * center_glow
                + 3.0 * warm_glow
            )
            blue = 4.0 + 6.0 * vignette + warm_glow

            circle_radius = math.hypot(x - 512.0, y - 510.0)
            ring_distance = abs(circle_radius - 365.0) - 12.0
            ring_alpha = 1.0 - smoothstep(0.0, 3.0, ring_distance)
            ring_glow = (
                math.exp(
                    -(max(0.0, ring_distance) ** 2) / (2.0 * 24.0**2)
                )
                * 0.45
            )
            red += 155.0 * ring_alpha + 35.0 * ring_glow
            green += 220.0 * ring_alpha + 70.0 * ring_glow
            blue += 5.0 * ring_glow

            if circle_radius < 345.0:
                inner_shadow = (
                    1.0 - smoothstep(305.0, 345.0, circle_radius)
                ) * 0.13
                red *= 1.0 - inner_shadow
                green *= 1.0 - inner_shadow
                blue *= 1.0 - inner_shadow

            logo_distance = min(
                rectangle_distance(x, y, *rectangle)
                for rectangle in logo_rectangles
            )
            logo_alpha = 1.0 - smoothstep(-1.2, 1.2, logo_distance)
            logo_glow = (
                math.exp(
                    -(max(0.0, logo_distance) ** 2) / (2.0 * 30.0**2)
                )
                * 0.75
            )

            vertical_gradient = clamp(1.0 - (y - 300.0) / 460.0)
            highlight = math.exp(-(((x + y - 770.0) / 90.0) ** 2)) * 0.45
            logo_red = 150.0 + 80.0 * vertical_gradient + 40.0 * highlight
            logo_green = 195.0 + 55.0 * vertical_gradient + 45.0 * highlight
            logo_blue = 20.0 * vertical_gradient + 20.0 * highlight

            shadow_distance = min(
                rectangle_distance(x - 10.0, y - 14.0, *rectangle)
                for rectangle in logo_rectangles
            )
            shadow_alpha = (
                (1.0 - smoothstep(-1.0, 2.0, shadow_distance))
                * (1.0 - logo_alpha)
                * 0.45
            )
            red = red * (1.0 - shadow_alpha) + 35.0 * shadow_alpha
            green = green * (1.0 - shadow_alpha) + 50.0 * shadow_alpha
            blue *= 1.0 - shadow_alpha

            red += 35.0 * logo_glow
            green += 105.0 * logo_glow

            red = red * (1.0 - logo_alpha) + logo_red * logo_alpha
            green = green * (1.0 - logo_alpha) + logo_green * logo_alpha
            blue = blue * (1.0 - logo_alpha) + logo_blue * logo_alpha

            paw_distance = min(
                ellipse_distance(x, y, *ellipse)
                for ellipse in paw_ellipses
            )
            paw_alpha = 1.0 - smoothstep(-1.2, 1.2, paw_distance)
            paw_glow = (
                math.exp(
                    -(max(0.0, paw_distance) ** 2) / (2.0 * 18.0**2)
                )
                * 0.35
            )
            red += 25.0 * paw_glow
            green += 75.0 * paw_glow
            red = red * (1.0 - paw_alpha) + 175.0 * paw_alpha
            green = green * (1.0 - paw_alpha) + 235.0 * paw_alpha
            blue = blue * (1.0 - paw_alpha) + 5.0 * paw_alpha

            for particle_x, particle_y, particle_radius in particles:
                particle_distance = (
                    math.hypot(x - particle_x, y - particle_y)
                    - particle_radius
                )
                particle_alpha = 1.0 - smoothstep(
                    -1.0,
                    1.5,
                    particle_distance,
                )
                if particle_alpha > 0.0:
                    red = red * (1.0 - particle_alpha) + 190.0 * particle_alpha
                    green = green * (1.0 - particle_alpha) + 250.0 * particle_alpha
                    blue = blue * (1.0 - particle_alpha) + 5.0 * particle_alpha

            edge = max(
                abs((x - 512.0) / 512.0),
                abs((y - 512.0) / 512.0),
            )
            edge_shadow = smoothstep(0.72, 1.03, edge) * 0.55
            red *= 1.0 - edge_shadow
            green *= 1.0 - edge_shadow
            blue *= 1.0 - edge_shadow

            offset = (y * width + x) * 3
            pixels[offset] = int(clamp(red, 0.0, 255.0))
            pixels[offset + 1] = int(clamp(green, 0.0, 255.0))
            pixels[offset + 2] = int(clamp(blue, 0.0, 255.0))

    return bytes(pixels)


def write_bmp(path: Path, width: int, height: int, rgb: bytes) -> None:
    row_size = (width * 3 + 3) & ~3
    pixel_size = row_size * height
    file_size = 14 + 40 + pixel_size

    with path.open("wb") as output:
        output.write(b"BM")
        output.write(struct.pack("<IHHI", file_size, 0, 0, 54))
        output.write(
            struct.pack(
                "<IIIHHIIIIII",
                40,
                width,
                height,
                1,
                24,
                0,
                pixel_size,
                2835,
                2835,
                0,
                0,
            )
        )

        padding = b"\0" * (row_size - width * 3)
        for y in range(height - 1, -1, -1):
            start = y * width * 3
            row = rgb[start : start + width * 3]
            bgr = bytearray(len(row))
            bgr[0::3] = row[2::3]
            bgr[1::3] = row[1::3]
            bgr[2::3] = row[0::3]
            output.write(bgr)
            output.write(padding)


def run_sips(*arguments: str) -> None:
    subprocess.run(
        ["sips", *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main() -> None:
    ICONSET.mkdir(parents=True, exist_ok=True)
    rgb = generate_rgb()
    write_bmp(SOURCE_BMP, 1024, 1024, rgb)

    run_sips(
        "-s",
        "format",
        "png",
        str(SOURCE_BMP),
        "--out",
        str(ICON_1024),
    )
    run_sips(
        "-z",
        "180",
        "180",
        str(ICON_1024),
        "--out",
        str(ICON_180),
    )
    run_sips(
        "-z",
        "120",
        "120",
        str(ICON_1024),
        "--out",
        str(ICON_120),
    )
    SOURCE_BMP.unlink(missing_ok=True)

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
        "info": {
            "author": "xcode",
            "version": 1,
        },
    }
    (ICONSET / "Contents.json").write_text(
        json.dumps(contents, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for icon in (ICON_120, ICON_180, ICON_1024):
        if not icon.is_file() or icon.stat().st_size == 0:
            raise RuntimeError(f"Icon generation failed: {icon}")
        print(f"Generated {icon.relative_to(ROOT)} ({icon.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
