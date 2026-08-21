#!/usr/bin/env python3
"""Fail fast on App Store release configuration issues before publishing."""

from __future__ import annotations

import argparse
import json
import plistlib
import shutil
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


def load_plist(path: Path) -> dict:
    with path.open("rb") as handle:
        return plistlib.load(handle)


def verify_source(root: Path, marketing_version: str) -> None:
    info_path = root / "TuranskeFitkoApp" / "Info.plist"
    entitlements_path = root / "TuranskeFitkoApp" / "TuranskeFitkoApp.entitlements"
    project_path = root / "TuranskeFitkoApp.xcodeproj" / "project.pbxproj"
    iconset = root / "TuranskeFitkoApp" / "Assets.xcassets" / "AppIcon.appiconset"
    icons_path = iconset / "Contents.json"

    info = load_plist(info_path)
    entitlements = load_plist(entitlements_path)
    project = project_path.read_text(encoding="utf-8")
    icons = json.loads(icons_path.read_text(encoding="utf-8"))

    assert info["CFBundleShortVersionString"] == marketing_version
    assert info["CFBundleIdentifier"] == BUNDLE_ID
    assert info["ITSAppUsesNonExemptEncryption"] is False
    assert set(info.get("UISupportedInterfaceOrientations~ipad", [])) == REQUIRED_IPAD_ORIENTATIONS

    assert project.count('TARGETED_DEVICE_FAMILY = "1,2";') >= 2
    assert project.count(f"MARKETING_VERSION = {marketing_version};") >= 2

    domains = entitlements.get("com.apple.developer.associated-domains", [])
    assert ASSOCIATED_DOMAIN in domains

    ipad_slots = {
        (item.get("size"), item.get("scale"), item.get("filename"))
        for item in icons.get("images", [])
        if item.get("idiom") == "ipad"
    }
    assert ("76x76", "2x", "AppIcon-152.png") in ipad_slots
    assert ("83.5x83.5", "2x", "AppIcon-167.png") in ipad_slots
    for filename in ("AppIcon-152.png", "AppIcon-167.png", "AppIcon-1024.png"):
        path = iconset / filename
        assert path.is_file() and path.stat().st_size > 0, f"Missing icon {filename}"

    print(
        "SOURCE PREFLIGHT OK: version, iPhone+iPad family, four iPad orientations, "
        "Associated Domains and iPad icons are valid."
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
        "SIGNED IPA PREFLIGHT OK: bundle/version, iPhone+iPad family, iPad orientations, "
        "signature and Associated Domains are valid."
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
