#!/usr/bin/env python3
"""Prepare the native iOS wrapper for the current Turanské Fitko App release."""

from __future__ import annotations

import argparse
import plistlib
import re
from pathlib import Path


def replace_exactly_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not update {label}; expected exactly one match, found {count}.")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-version", default="6.44")
    parser.add_argument("--marketing-version", default="1.0")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    content_view = root / "TuranskeFitkoApp" / "ContentView.swift"
    info_plist = root / "TuranskeFitkoApp" / "Info.plist"

    production_url = (
        "https://turanskefitko.sk/"
        f"?tfm_mobile_app=1&native=ios&tfma_v={args.web_version}"
    )

    swift = content_view.read_text(encoding="utf-8")
    swift = replace_exactly_once(
        swift,
        r'private let appURL = URL\(string: "[^"]+"\)!',
        f'private let appURL = URL(string: "{production_url}")!',
        "production app URL",
    )
    swift = replace_exactly_once(
        swift,
        r'webView\.customUserAgent = "TFMiOSApp TFMNativeApp TuranskeFitko/[^"]+"',
        f'webView.customUserAgent = "TFMiOSApp TFMNativeApp TuranskeFitko/{args.web_version}"',
        "native user agent version",
    )

    if "dev.turanskefitko.sk" in swift:
        raise RuntimeError("Development URL is still present in ContentView.swift.")
    if production_url not in swift:
        raise RuntimeError("Production URL validation failed.")

    content_view.write_text(swift, encoding="utf-8")

    with info_plist.open("rb") as handle:
        plist = plistlib.load(handle)

    plist["CFBundleDisplayName"] = "Turanské Fitko App"
    plist["CFBundleExecutable"] = "$(EXECUTABLE_NAME)"
    plist["CFBundlePackageType"] = "APPL"
    plist["CFBundleIconName"] = "AppIcon"
    plist["CFBundleIdentifier"] = "sk.turanskefitko.app"
    plist["CFBundleShortVersionString"] = args.marketing_version

    with info_plist.open("wb") as handle:
        plistlib.dump(plist, handle, fmt=plistlib.FMT_XML, sort_keys=False)

    print(f"Prepared production URL: {production_url}")
    print(f"Prepared display name: {plist['CFBundleDisplayName']}")
    print(f"Prepared marketing version: {plist['CFBundleShortVersionString']}")


if __name__ == "__main__":
    main()
