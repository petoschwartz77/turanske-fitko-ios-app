#!/usr/bin/env python3
"""Prepare the native iOS wrapper for Turanské Fitko App v9.23."""

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
    parser.add_argument("--web-version", default="9.23")
    parser.add_argument("--marketing-version", default="1.0")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    content_view = root / "TuranskeFitkoApp" / "ContentView.swift"
    app_delegate = root / "TuranskeFitkoApp" / "TuranskeFitkoApp.swift"
    info_plist = root / "TuranskeFitkoApp" / "Info.plist"

    production_url = (
        "https://turanskefitko.sk/"
        f"?tfm_mobile_app=1&native=ios&tfma_v={args.web_version}"
    )

    content = content_view.read_text(encoding="utf-8")
    content = replace_exactly_once(
        content,
        r'private let appURL = URL\(string: "[^"]+"\)!',
        f'private let appURL = URL(string: "{production_url}")!',
        "production app URL",
    )
    content = replace_exactly_once(
        content,
        r'webView\.customUserAgent = "TFMiOSApp TFMNativeApp TuranskeFitko/[^"]+"',
        f'webView.customUserAgent = "TFMiOSApp TFMNativeApp TuranskeFitko/{args.web_version}"',
        "native user agent version",
    )
    if "dev.turanskefitko.sk" in content:
        raise RuntimeError("Development URL is still present in ContentView.swift.")
    if production_url not in content:
        raise RuntimeError("Production URL validation failed.")
    content_view.write_text(content, encoding="utf-8")

    swift = app_delegate.read_text(encoding="utf-8")

    # Xcode 26 exposes the completion-handler overload with the second argument label `in:`.
    # The previous source used the async overload label (`contentWorld:`) together with a
    # trailing closure, which fails with "extra trailing closure passed in call".
    old_call = '''            webView.callAsyncJavaScript(\n                script,\n                arguments: ["nfcURL": targetURL.absoluteString],\n                in: nil,\n                contentWorld: .page\n            ) { result in'''
    new_call = '''            webView.callAsyncJavaScript(\n                script,\n                arguments: ["nfcURL": targetURL.absoluteString],\n                in: nil,\n                in: .page,\n                completionHandler: { result in'''
    if old_call in swift:
        swift = swift.replace(old_call, new_call, 1)
        call_pos = swift.index('            webView.callAsyncJavaScript(')
        old_close = '            }\n        } else {'
        close_pos = swift.index(old_close, call_pos)
        swift = swift[:close_pos] + '            })\n        } else {' + swift[close_pos + len(old_close):]
    elif 'completionHandler: { result in' not in swift:
        raise RuntimeError("Could not patch WKWebView callAsyncJavaScript for Xcode 26.")

    # The physical NFC tag reaches WordPress first. WordPress stores a short-lived one-use
    # ticket and launches the app through turanskefitko://nfc?ticket=.... This means the scan
    # survives even when iOS Universal Link delivery is inconsistent.
    scheme_anchor = '        guard incomingURL.scheme?.lowercased() == "https" else { return nil }\n'
    scheme_block = '''        let incomingScheme = incomingURL.scheme?.lowercased() ?? ""\n        if incomingScheme == "turanskefitko" {\n            guard (incomingURL.host ?? "").lowercased() == "nfc",\n                  let components = URLComponents(url: incomingURL, resolvingAgainstBaseURL: false),\n                  let rawTicket = components.queryItems?.first(where: { $0.name == "ticket" })?.value else {\n                return nil\n            }\n            let ticket = rawTicket.lowercased()\n            let hex = CharacterSet(charactersIn: "0123456789abcdef")\n            guard (32...128).contains(ticket.count),\n                  ticket.unicodeScalars.allSatisfy({ hex.contains($0) }) else {\n                return nil\n            }\n            guard var claim = URLComponents(string: "https://turanskefitko.sk/tfm-app/nfc/claim/\\(ticket)/") else {\n                return nil\n            }\n            claim.queryItems = [\n                URLQueryItem(name: "tfma_nfc_app", value: "1"),\n                URLQueryItem(name: "tfma_native_handoff", value: "1"),\n                URLQueryItem(name: "tfma_native_json", value: "1"),\n                URLQueryItem(name: "native", value: "ios"),\n                URLQueryItem(name: "tfma_nocache", value: String(Int(Date().timeIntervalSince1970 * 1000)))\n            ]\n            return claim.url\n        }\n        guard incomingScheme == "https" else { return nil }\n'''
    if 'incomingScheme == "turanskefitko"' not in swift:
        if swift.count(scheme_anchor) != 1:
            raise RuntimeError("Could not inject custom NFC scheme handler.")
        swift = swift.replace(scheme_anchor, scheme_block, 1)

    # Compact non-blocking NFC receipt rail. It gives immediate feedback without covering Home.
    # No AudioToolbox dependency: haptics are enough and avoid SDK/import compatibility issues.
    rail_class = r'''final class NFCNativeModal {
    static let shared = NFCNativeModal()

    private weak var rail: UIVisualEffectView?
    private weak var iconView: UIImageView?
    private weak var kickerLabel: UILabel?
    private weak var titleLabel: UILabel?
    private weak var messageLabel: UILabel?
    private weak var progressView: UIProgressView?
    private var dismissWorkItem: DispatchWorkItem?
    private var progressTimer: Timer?
    private var accent = UIColor(red: 0.78, green: 1.0, blue: 0.0, alpha: 1.0)

    private init() {}

    func setTheme(_ rawTheme: String) {
        let theme = rawTheme.lowercased()
        if theme.contains("pink") || theme.contains("rose") || theme.contains("editorial") {
            accent = UIColor(red: 1.0, green: 0.31, blue: 0.58, alpha: 1.0)
        } else {
            accent = UIColor(red: 0.78, green: 1.0, blue: 0.0, alpha: 1.0)
        }
        applyAccent()
    }

    func showLoading() {
        DispatchQueue.main.async {
            self.cancelTimers()
            guard self.ensureRail() else { return }
            self.kickerLabel?.text = "NFC • TURANSKÉ FITKO"
            self.titleLabel?.text = "NFC načítané"
            self.messageLabel?.text = "Overujem vstup so serverom…"
            self.iconView?.image = UIImage(systemName: "wave.3.right.circle.fill")
            self.iconView?.tintColor = self.accent
            self.progressView?.progressTintColor = self.accent
            self.progressView?.progress = 0.18
            self.present()
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        }
    }

    func showResult(state: String, title: String, message: String, seconds: Int) {
        DispatchQueue.main.async {
            self.cancelTimers()
            guard self.ensureRail() else { return }

            let normalized = state.lowercased()
            let isError = normalized == "error" || normalized == "login"
            let resultAccent = isError
                ? UIColor(red: 1.0, green: 0.64, blue: 0.32, alpha: 1.0)
                : self.accent

            self.kickerLabel?.text = "NFC • TURANSKÉ FITKO"
            self.titleLabel?.text = title
            self.messageLabel?.text = message
            self.iconView?.image = UIImage(systemName: isError ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
            self.iconView?.tintColor = resultAccent
            self.progressView?.progressTintColor = resultAccent
            self.progressView?.progress = 1.0
            self.present()

            let feedback = UINotificationFeedbackGenerator()
            feedback.prepare()
            feedback.notificationOccurred(isError ? .error : .success)

            let duration = max(3, min(9, seconds))
            let started = Date().timeIntervalSince1970
            self.progressTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] timer in
                guard let self = self else { timer.invalidate(); return }
                let elapsed = Date().timeIntervalSince1970 - started
                let remaining = max(0, 1 - Float(elapsed / Double(duration)))
                self.progressView?.setProgress(remaining, animated: false)
                if remaining <= 0 { timer.invalidate() }
            }

            let item = DispatchWorkItem { [weak self] in self?.hide() }
            self.dismissWorkItem = item
            DispatchQueue.main.asyncAfter(deadline: .now() + Double(duration), execute: item)
        }
    }

    private func ensureRail() -> Bool {
        if rail != nil { applyAccent(); return true }
        guard let appDelegate = UIApplication.shared.delegate as? AppDelegate,
              let window = appDelegate.window else { return false }

        let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterialDark))
        blur.translatesAutoresizingMaskIntoConstraints = false
        blur.layer.cornerRadius = 22
        blur.layer.cornerCurve = .continuous
        blur.layer.borderWidth = 1
        blur.layer.borderColor = accent.withAlphaComponent(0.42).cgColor
        blur.clipsToBounds = true
        blur.isUserInteractionEnabled = false

        let icon = UIImageView()
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.contentMode = .scaleAspectFit
        icon.tintColor = accent

        let kicker = UILabel()
        kicker.textColor = accent
        kicker.font = .systemFont(ofSize: 9, weight: .heavy)
        kicker.numberOfLines = 1

        let title = UILabel()
        title.textColor = .white
        title.font = .systemFont(ofSize: 16, weight: .bold)
        title.numberOfLines = 1
        title.adjustsFontSizeToFitWidth = true
        title.minimumScaleFactor = 0.76

        let message = UILabel()
        message.textColor = UIColor.white.withAlphaComponent(0.62)
        message.font = .systemFont(ofSize: 11, weight: .semibold)
        message.numberOfLines = 1
        message.lineBreakMode = .byTruncatingTail

        let text = UIStackView(arrangedSubviews: [kicker, title, message])
        text.translatesAutoresizingMaskIntoConstraints = false
        text.axis = .vertical
        text.spacing = 2

        let row = UIStackView(arrangedSubviews: [icon, text])
        row.translatesAutoresizingMaskIntoConstraints = false
        row.axis = .horizontal
        row.alignment = .center
        row.spacing = 12

        let progress = UIProgressView(progressViewStyle: .bar)
        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.trackTintColor = UIColor.white.withAlphaComponent(0.06)
        progress.progressTintColor = accent
        progress.progress = 0

        blur.contentView.addSubview(row)
        blur.contentView.addSubview(progress)
        window.addSubview(blur)

        NSLayoutConstraint.activate([
            blur.leadingAnchor.constraint(equalTo: window.leadingAnchor, constant: 14),
            blur.trailingAnchor.constraint(equalTo: window.trailingAnchor, constant: -14),
            blur.topAnchor.constraint(equalTo: window.safeAreaLayoutGuide.topAnchor, constant: 8),
            blur.heightAnchor.constraint(greaterThanOrEqualToConstant: 78),

            row.leadingAnchor.constraint(equalTo: blur.contentView.leadingAnchor, constant: 14),
            row.trailingAnchor.constraint(equalTo: blur.contentView.trailingAnchor, constant: -14),
            row.topAnchor.constraint(equalTo: blur.contentView.topAnchor, constant: 11),
            row.bottomAnchor.constraint(equalTo: progress.topAnchor, constant: -8),

            icon.widthAnchor.constraint(equalToConstant: 38),
            icon.heightAnchor.constraint(equalToConstant: 38),

            progress.leadingAnchor.constraint(equalTo: blur.contentView.leadingAnchor),
            progress.trailingAnchor.constraint(equalTo: blur.contentView.trailingAnchor),
            progress.bottomAnchor.constraint(equalTo: blur.contentView.bottomAnchor),
            progress.heightAnchor.constraint(equalToConstant: 3),
        ])

        blur.alpha = 0
        blur.transform = CGAffineTransform(translationX: 0, y: -110)
        rail = blur
        iconView = icon
        kickerLabel = kicker
        titleLabel = title
        messageLabel = message
        progressView = progress
        applyAccent()
        return true
    }

    private func applyAccent() {
        rail?.layer.borderColor = accent.withAlphaComponent(0.42).cgColor
        kickerLabel?.textColor = accent
        iconView?.tintColor = accent
        progressView?.progressTintColor = accent
    }

    private func present() {
        guard let rail = rail else { return }
        if rail.superview == nil,
           let appDelegate = UIApplication.shared.delegate as? AppDelegate,
           let window = appDelegate.window {
            window.addSubview(rail)
        }
        UIView.animate(withDuration: 0.28, delay: 0, options: [.curveEaseOut, .beginFromCurrentState]) {
            rail.alpha = 1
            rail.transform = .identity
        }
    }

    private func hide() {
        guard let rail = rail else { return }
        UIView.animate(withDuration: 0.24, delay: 0, options: [.curveEaseIn, .beginFromCurrentState]) {
            rail.alpha = 0
            rail.transform = CGAffineTransform(translationX: 0, y: -110)
        }
    }

    private func cancelTimers() {
        dismissWorkItem?.cancel()
        dismissWorkItem = nil
        progressTimer?.invalidate()
        progressTimer = nil
    }
}
'''

    swift, class_count = re.subn(r'final class NFCNativeModal \{.*\Z', rail_class, swift, count=1, flags=re.S)
    if class_count != 1:
        raise RuntimeError(f"Could not replace NFCNativeModal; found {class_count} matches.")

    if 'incomingScheme == "turanskefitko"' not in swift:
        raise RuntimeError("Custom NFC scheme injection validation failed.")
    if 'NFC načítané' not in swift or 'translationX: 0, y: -110' not in swift:
        raise RuntimeError("NFC receipt rail validation failed.")
    if 'completionHandler: { result in' not in swift or 'in: .page' not in swift:
        raise RuntimeError("Xcode 26 WebKit compatibility validation failed.")

    app_delegate.write_text(swift, encoding="utf-8")

    with info_plist.open("rb") as handle:
        plist = plistlib.load(handle)

    plist["CFBundleDisplayName"] = "Turanské Fitko App"
    plist["CFBundleExecutable"] = "$(EXECUTABLE_NAME)"
    plist["CFBundlePackageType"] = "APPL"
    plist["CFBundleIconName"] = "AppIcon"
    plist["CFBundleIdentifier"] = "sk.turanskefitko.app"
    plist["CFBundleShortVersionString"] = args.marketing_version
    plist["ITSAppUsesNonExemptEncryption"] = False
    plist["CFBundleURLTypes"] = [
        {
            "CFBundleURLName": "sk.turanskefitko.nfc",
            "CFBundleURLSchemes": ["turanskefitko"],
        }
    ]

    with info_plist.open("wb") as handle:
        plistlib.dump(plist, handle, fmt=plistlib.FMT_XML, sort_keys=False)

    print(f"Prepared production URL: {production_url}")
    print("Prepared NFC transport: server gateway -> turanskefitko:// one-use ticket")
    print("Prepared NFC feedback: non-blocking top receipt rail")
    print("Prepared Xcode 26 WebKit compatibility")
    print(f"Prepared display name: {plist['CFBundleDisplayName']}")
    print(f"Prepared marketing version: {plist['CFBundleShortVersionString']}")


if __name__ == "__main__":
    main()
