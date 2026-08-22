#!/usr/bin/env python3
"""Fail fast on App Store release configuration issues before publishing."""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import tempfile
import zipfile
from pathlib import Path

REQUIRED_IPAD_ORIENTATIONS = {
    "UIInterfaceOrientationPortrait",
    "UIInterfaceOrientationPortraitUpsideDown",
    "UIInterfaceOrientationLandscapeLeft",
    "UIInterfaceOrientationLandscapeRight",
}
ASSOCIATED_DOMAIN = "applinks:turanskefitko.sk"
BUNDLE_ID = "sk.turanskefitko.app"
ALTERNATE_ICON = "PinkIcon"

REQUIRED_DEVICE_SLOTS = {
    ("iphone", "20x20", "2x"),
    ("iphone", "20x20", "3x"),
    ("iphone", "29x29", "2x"),
    ("iphone", "29x29", "3x"),
    ("iphone", "40x40", "2x"),
    ("iphone", "40x40", "3x"),
    ("iphone", "60x60", "2x"),
    ("iphone", "60x60", "3x"),
    ("ipad", "20x20", "1x"),
    ("ipad", "20x20", "2x"),
    ("ipad", "29x29", "1x"),
    ("ipad", "29x29", "2x"),
    ("ipad", "40x40", "1x"),
    ("ipad", "40x40", "2x"),
    ("ipad", "76x76", "1x"),
    ("ipad", "76x76", "2x"),
    ("ipad", "83.5x83.5", "2x"),
}


def load_plist(path: Path) -> dict:
    with path.open("rb") as handle:
        return plistlib.load(handle)


def load_iconset(path: Path) -> dict:
    return json.loads((path / "Contents.json").read_text(encoding="utf-8"))


def verify_iconset(path: Path, *, require_marketing: bool) -> None:
    assert path.is_dir(), f"Missing iconset: {path}"
    payload = load_iconset(path)
    images = payload.get("images", [])
    slots = {
        (item.get("idiom"), item.get("size"), item.get("scale"))
        for item in images
        if item.get("idiom") in {"iphone", "ipad"}
    }
    missing = REQUIRED_DEVICE_SLOTS - slots
    assert not missing, f"Missing device icon slots in {path.name}: {sorted(missing)}"

    filenames = [item.get("filename") for item in images if item.get("filename")]
    for filename in filenames:
        icon = path / filename
        assert icon.is_file() and icon.stat().st_size > 0, f"Missing generated icon: {icon}"

    marketing = [
        item for item in images
        if item.get("idiom") == "ios-marketing" and item.get("size") == "1024x1024"
    ]
    if require_marketing:
        assert len(marketing) == 1, f"Primary iconset must contain one 1024 marketing icon: {path}"


def verify_source(root: Path, marketing_version: str) -> None:
    info_path = root / "TuranskeFitkoApp" / "Info.plist"
    entitlements_path = root / "TuranskeFitkoApp" / "TuranskeFitkoApp.entitlements"
    project_path = root / "TuranskeFitkoApp.xcodeproj" / "project.pbxproj"
    primary_iconset = root / "TuranskeFitkoApp" / "Assets.xcassets" / "AppIcon.appiconset"
    pink_iconset = root / "TuranskeFitkoApp" / "Assets.xcassets" / "PinkIcon.appiconset"
    synchronizer_path = root / "TuranskeFitkoApp" / "ThemeIconSynchronizer.swift"

    info = load_plist(info_path)
    entitlements = load_plist(entitlements_path)
    project = project_path.read_text(encoding="utf-8")
    synchronizer = synchronizer_path.read_text(encoding="utf-8")

    assert info["CFBundleShortVersionString"] == marketing_version
    assert info["CFBundleIdentifier"] == BUNDLE_ID
    assert info["ITSAppUsesNonExemptEncryption"] is False
    assert set(info.get("UISupportedInterfaceOrientations~ipad", [])) == REQUIRED_IPAD_ORIENTATIONS

    assert project.count('TARGETED_DEVICE_FAMILY = "1,2";') >= 2
    assert project.count(f"MARKETING_VERSION = {marketing_version};") >= 2
    assert project.count("ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES = PinkIcon;") >= 2
    assert project.count("ASSETCATALOG_COMPILER_INCLUDE_ALL_APPICON_ASSETS = YES;") >= 2
    assert "ThemeIconSynchronizer.swift in Sources" in project

    domains = entitlements.get("com.apple.developer.associated-domains", [])
    assert ASSOCIATED_DOMAIN in domains

    assert "tfma85_theme" in synchronizer
    assert '"editorial" ? "PinkIcon"' in synchronizer
    assert "setAlternateIconName" in synchronizer

    verify_iconset(primary_iconset, require_marketing=True)
    verify_iconset(pink_iconset, require_marketing=False)

    print(
        "SOURCE PREFLIGHT OK: version, iPhone+iPad, iPad orientations, Associated Domains, "
        "final primary icon, PinkIcon alternate set and native theme synchronizer are valid."
    )


def codesign_entitlements(app_path: Path, output: Path) -> dict:
    with output.open("wb") as handle:
        subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", str(app_path)],
            check=True,
            stdout=handle,
            stderr=subprocess.DEVNULL,
        )
    return load_plist(output)


def alternate_icons_from_info(info: dict) -> set[str]:
    names: set[str] = set()
    for key in ("CFBundleIcons", "CFBundleIcons~ipad"):
        block = info.get(key, {}) or {}
        alternates = block.get("CFBundleAlternateIcons", {}) or {}
        names.update(alternates.keys())
    return names


def verify_ipa(ipa_path: Path, marketing_version: str) -> None:
    assert ipa_path.is_file() and ipa_path.stat().st_size > 0
    with tempfile.TemporaryDirectory(prefix="tfm-ios-verify-") as temp:
        temp_dir = Path(temp)
        with zipfile.ZipFile(ipa_path) as archive:
            archive.extractall(temp_dir)

        apps = list((temp_dir / "Payload").glob("*.app"))
        assert len(apps) == 1, f"Expected one .app in Payload, found {len(apps)}"
        app_path = apps[0]
        info = load_plist(app_path / "Info.plist")

        assert info["CFBundleDisplayName"] == "Turanské Fitko App"
        assert info["CFBundleIdentifier"] == BUNDLE_ID
        assert info["CFBundleShortVersionString"] == marketing_version
        assert info["ITSAppUsesNonExemptEncryption"] is False
        assert set(info.get("UIDeviceFamily", [])) == {1, 2}
        assert set(info.get("UISupportedInterfaceOrientations~ipad", [])) == REQUIRED_IPAD_ORIENTATIONS
        assert (app_path / "Assets.car").is_file()

        alternates = alternate_icons_from_info(info)
        assert ALTERNATE_ICON in alternates, (
            f"Compiled Info.plist does not expose {ALTERNATE_ICON}; found alternate icons: {sorted(alternates)}"
        )

        primary_name = (info.get("CFBundleIcons", {}) or {}).get("CFBundlePrimaryIcon", {}).get("CFBundleIconName")
        if primary_name is not None:
            assert primary_name == "AppIcon", f"Unexpected primary icon name: {primary_name}"

        executable = info["CFBundleExecutable"]
        executable_path = app_path / executable
        assert executable_path.is_file()

        signed_entitlements = codesign_entitlements(app_path, temp_dir / "signed-entitlements.plist")
        assert ASSOCIATED_DOMAIN in signed_entitlements.get("com.apple.developer.associated-domains", [])
        assert signed_entitlements.get("application-identifier", "").endswith(f".{BUNDLE_ID}")

        result = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(app_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert result.returncode == 0, result.stdout

    print(
        "SIGNED IPA PREFLIGHT OK: bundle/version, iPhone+iPad, orientations, signature, "
        "Associated Domains and PinkIcon alternate app icon are valid."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("source", "ipa"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ipa")
    parser.add_argument("--marketing-version", required=True)
    args = parser.parse_args()

    if args.mode == "source":
        verify_source(Path(args.root).resolve(), args.marketing_version)
        return

    if not args.ipa:
        raise SystemExit("--ipa is required in ipa mode")
    verify_ipa(Path(args.ipa).resolve(), args.marketing_version)


if __name__ == "__main__":
    main()
