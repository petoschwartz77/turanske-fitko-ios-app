#!/usr/bin/env python3
"""Patch the clean SwiftUI/WKWebView wrapper with two isolated v9.26 features.

1) Theme-linked alternate icon: plugin/original -> primary icon, editorial/Ružová iskra -> AppIconPink.
2) NFC Universal Link -> same logged-in WKWebView fetch -> server JSON -> native non-blocking rail.

The WordPress plugin remains authoritative for membership, staff/owner roles and 10-entry logic.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "TuranskeFitkoApp" / "ContentView.swift"
APP = ROOT / "TuranskeFitkoApp" / "TuranskeFitkoApp.swift"
PROJECT = ROOT / "TuranskeFitkoApp.xcodeproj" / "project.pbxproj"
ENTITLEMENTS = ROOT / "TuranskeFitkoApp" / "TuranskeFitkoApp.entitlements"


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Could not patch {label}; expected 1 match, got {count}.")
    return text.replace(old, new, 1)


def patch_content_view() -> None:
    swift = CONTENT.read_text(encoding="utf-8")

    native_helpers = r'''
final class TFMWebViewRegistryV926 {
    static let shared = TFMWebViewRegistryV926()
    weak var webView: WKWebView?
    private init() {}
}

enum TFMNativeThemeIconV926 {
    static let pinkIconName = "AppIconPink"

    static func apply(theme rawTheme: String) {
        let theme = rawTheme.lowercased()
        let target: String? = (theme == "editorial" || theme == "pink" || theme == "rose") ? pinkIconName : nil
        UserDefaults.standard.set(theme, forKey: "tfma926.theme")

        DispatchQueue.main.async {
            let app = UIApplication.shared
            guard app.supportsAlternateIcons else {
                print("[TF Theme 9.26] Alternate icons are not supported by this build")
                return
            }
            if app.alternateIconName == target { return }
            app.setAlternateIconName(target) { error in
                if let error {
                    print("[TF Theme 9.26] Icon change failed: \(error.localizedDescription)")
                } else {
                    print("[TF Theme 9.26] Icon changed to \(target ?? "primary")")
                }
            }
        }
    }
}

'''
    if "enum TFMNativeThemeIconV926" not in swift:
        swift = once(swift, "struct ContentView: View {", native_helpers + "struct ContentView: View {", "native theme helpers")

    if 'name: "tfmaNativeNFC"' not in swift:
        swift = once(
            swift,
            '        contentController.add(context.coordinator, name: "tfmaNative")\n',
            '        contentController.add(context.coordinator, name: "tfmaNative")\n        contentController.add(context.coordinator, name: "tfmaNativeNFC")\n',
            "NFC message handler",
        )

    if "source: Self.nfcBridgeScript" not in swift:
        leo_block = '''        contentController.addUserScript(\n            WKUserScript(\n                source: Self.leoProteinAnimationScript,\n                injectionTime: .atDocumentEnd,\n                forMainFrameOnly: true\n            )\n        )\n'''
        bridge_block = leo_block + '''        contentController.addUserScript(\n            WKUserScript(\n                source: Self.nfcBridgeScript,\n                injectionTime: .atDocumentStart,\n                forMainFrameOnly: true\n            )\n        )\n'''
        swift = once(swift, leo_block, bridge_block, "NFC user script")

    if "TFMWebViewRegistryV926.shared.webView = webView" not in swift:
        swift = once(
            swift,
            '        webView.scrollView.bounces = true\n',
            '        webView.scrollView.bounces = true\n        TFMWebViewRegistryV926.shared.webView = webView\n',
            "webview registry",
        )

    if 'removeScriptMessageHandler(forName: "tfmaNativeNFC")' not in swift:
        swift = once(
            swift,
            '        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "tfmaNative")\n',
            '        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "tfmaNative")\n        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "tfmaNativeNFC")\n        if TFMWebViewRegistryV926.shared.webView === uiView { TFMWebViewRegistryV926.shared.webView = nil }\n',
            "NFC handler cleanup",
        )

    message_anchor = '            guard message.name == "tfmaNative" else { return }\n\n'
    if "TFMNFCBridgeV926.receive" not in swift:
        routing = '''            if message.name == "tfmaNativeNFC" {\n                if let body = message.body as? [String: Any] {\n                    TFMNFCBridgeV926.receive(body)\n                }\n                return\n            }\n            guard message.name == "tfmaNative" else { return }\n\n            if let body = message.body as? [String: Any],\n               let event = body["event"] as? String,\n               event == "themeChanged" {\n                TFMNativeThemeIconV926.apply(theme: body["theme"] as? String ?? "plugin")\n                return\n            }\n\n'''
        swift = once(swift, message_anchor, routing, "native bridge routing")

    if "didFinish navigation" not in swift:
        policy_anchor = '        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {\n'
        did_finish = '''        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {\n            webView.evaluateJavaScript("localStorage.getItem('tfma85_theme') || 'plugin'") { value, _ in\n                if let theme = value as? String { TFMNativeThemeIconV926.apply(theme: theme) }\n            }\n        }\n\n'''
        swift = once(swift, policy_anchor, did_finish + policy_anchor, "theme sync after navigation")

    if "private static let nfcBridgeScript" not in swift:
        marker = '    private static let leoProteinAnimationScript = #"""\n'
        nfc_script = r'''    private static let nfcBridgeScript = #"""
    (() => {
        if (window.TFMANFC926) return;
        const post = (payload) => {
            try { window.webkit?.messageHandlers?.tfmaNativeNFC?.postMessage(payload); } catch (_) {}
        };
        const cleanJSON = (text) => {
            const raw = String(text || '').replace(/^\uFEFF/, '').trim();
            if (!raw) return null;
            try { return JSON.parse(raw); } catch (_) {}
            const start = raw.indexOf('{');
            const end = raw.lastIndexOf('}');
            if (start >= 0 && end > start) {
                try { return JSON.parse(raw.slice(start, end + 1)); } catch (_) {}
            }
            return null;
        };
        window.TFMANFC926 = {
            version: 926,
            process: async (rawURL) => {
                const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
                const timeout = setTimeout(() => { try { controller?.abort(); } catch (_) {} }, 12000);
                try {
                    const url = new URL(String(rawURL || ''), location.href);
                    url.searchParams.set('tfma_nfc_app', '1');
                    url.searchParams.set('native', 'ios');
                    url.searchParams.set('tfma_native_json', '1');
                    url.searchParams.set('tfma_v', '9.26');
                    url.searchParams.set('tfma_nocache', String(Date.now()));
                    const response = await fetch(url.toString(), {
                        method: 'GET',
                        credentials: 'include',
                        cache: 'no-store',
                        redirect: 'follow',
                        headers: {
                            'Accept': 'application/json',
                            'X-TFMA-Native-NFC': 'ios-9.26'
                        },
                        signal: controller ? controller.signal : undefined
                    });
                    const text = await response.text();
                    const payload = cleanJSON(text);
                    if (!payload || !payload.title || !payload.state) {
                        post({event:'nfcResult', ok:false, code:'BAD_JSON', http:response.status, message:'Server nepotvrdil výsledok NFC.'});
                        return;
                    }
                    post({event:'nfcResult', ok:true, http:response.status, payload:payload});
                } catch (error) {
                    const code = error && error.name === 'AbortError' ? 'TIMEOUT' : 'NETWORK';
                    post({event:'nfcResult', ok:false, code:code, message:String(error && error.message || 'NFC request failed')});
                } finally {
                    clearTimeout(timeout);
                }
            }
        };
    })();
    """#

'''
        swift = once(swift, marker, nfc_script + marker, "NFC bridge script constant")

    required = [
        "enum TFMNativeThemeIconV926",
        "TFMWebViewRegistryV926.shared.webView = webView",
        'name: "tfmaNativeNFC"',
        "TFMNFCBridgeV926.receive",
        "window.TFMANFC926",
        "tfma_native_json",
        "themeChanged",
        "AppIconPink",
    ]
    missing = [item for item in required if item not in swift]
    if missing:
        raise RuntimeError(f"ContentView v9.26 validation failed: {missing}")

    CONTENT.write_text(swift, encoding="utf-8")


def patch_app() -> None:
    swift = APP.read_text(encoding="utf-8")
    if "TFMNFCBridgeV926" in swift:
        return

    swift = once(swift, "import SwiftUI\n", "import SwiftUI\nimport UIKit\nimport WebKit\n", "app imports")

    old_body = '''        WindowGroup {\n            ContentView()\n                .preferredColorScheme(.dark)\n        }\n'''
    new_body = '''        WindowGroup {\n            ContentView()\n                .preferredColorScheme(.dark)\n                .onOpenURL { url in\n                    TFMNFCBridgeV926.handle(url, source: "openURL")\n                }\n                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in\n                    guard let url = activity.webpageURL else { return }\n                    TFMNFCBridgeV926.handle(url, source: "universalLink")\n                }\n        }\n'''
    swift = once(swift, old_body, new_body, "SwiftUI universal link hooks")

    bridge = r'''

enum TFMNFCBridgeV926 {
    private static var pendingURL: URL?
    private static var retryWorkItem: DispatchWorkItem?
    private static var lastFingerprint = ""
    private static var lastHandledAt: TimeInterval = 0

    static func handle(_ incomingURL: URL, source: String) {
        DispatchQueue.main.async {
            guard let target = validatedNFCURL(incomingURL) else {
                print("[TF NFC 9.26] Ignored URL from \(source): \(incomingURL.absoluteString)")
                return
            }

            let fingerprint = target.host! + target.path
            let now = Date().timeIntervalSince1970
            if fingerprint == lastFingerprint && now - lastHandledAt < 1.5 { return }
            lastFingerprint = fingerprint
            lastHandledAt = now

            pendingURL = target
            retryWorkItem?.cancel()
            retryWorkItem = nil
            TFMNFCStatusRailV926.shared.showLoading()
            dispatchPending(attempt: 0)
        }
    }

    static func receive(_ body: [String: Any]) {
        DispatchQueue.main.async {
            guard (body["event"] as? String) == "nfcResult" else { return }
            if body["ok"] as? Bool == true,
               let payload = body["payload"] as? [String: Any] {
                let state = (payload["state"] as? String) ?? "info"
                let title = (payload["title"] as? String) ?? "NFC potvrdené"
                let message = (payload["message"] as? String) ?? "Server potvrdil NFC akciu."
                TFMNFCStatusRailV926.shared.showResult(state: state, title: title, message: message)
            } else {
                let code = (body["code"] as? String) ?? "UNKNOWN"
                let message: String
                switch code {
                case "TIMEOUT": message = "Server neodpovedal včas. Skús tag priložiť ešte raz."
                case "BAD_JSON": message = "Server vrátil nečitateľné potvrdenie. Skús tag priložiť ešte raz."
                default: message = "Server sa nepodarilo overiť. Skús tag priložiť ešte raz."
                }
                TFMNFCStatusRailV926.shared.showResult(state: "error", title: "NFC bez potvrdenia", message: message)
            }
        }
    }

    private static func validatedNFCURL(_ incomingURL: URL) -> URL? {
        guard incomingURL.scheme?.lowercased() == "https" else { return nil }
        let host = (incomingURL.host ?? "").lowercased().replacingOccurrences(of: "www.", with: "")
        guard host == "turanskefitko.sk" else { return nil }
        let parts = incomingURL.path.split(separator: "/").map(String.init)
        guard parts.count == 3 || parts.count == 4 else { return nil }
        guard parts[0] == "tfm-app", parts[1] == "nfc" else { return nil }
        let token: String
        if parts.count == 4 {
            guard parts[2] == "in" || parts[2] == "out" else { return nil }
            token = parts[3]
        } else {
            token = parts[2]
        }
        guard (24...128).contains(token.count) else { return nil }
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
        guard token.unicodeScalars.allSatisfy({ allowed.contains($0) }) else { return nil }
        return incomingURL
    }

    private static func dispatchPending(attempt: Int) {
        guard let target = pendingURL else { return }
        guard attempt < 80 else {
            pendingURL = nil
            TFMNFCStatusRailV926.shared.showResult(
                state: "error",
                title: "NFC bez potvrdenia",
                message: "Appka sa nestihla pripraviť. Skús tag priložiť ešte raz."
            )
            return
        }
        guard let webView = TFMWebViewRegistryV926.shared.webView else {
            scheduleRetry(attempt + 1)
            return
        }

        webView.evaluateJavaScript("typeof window.TFMANFC926 === 'object' && typeof window.TFMANFC926.process === 'function'") { ready, error in
            DispatchQueue.main.async {
                if error != nil || (ready as? Bool) != true {
                    scheduleRetry(attempt + 1)
                    return
                }

                pendingURL = nil
                let literal = javascriptString(target.absoluteString)
                webView.evaluateJavaScript("window.TFMANFC926.process(\(literal));") { _, jsError in
                    if let jsError {
                        print("[TF NFC 9.26] JS dispatch error: \(jsError.localizedDescription)")
                        TFMNFCStatusRailV926.shared.showResult(
                            state: "error",
                            title: "NFC bez potvrdenia",
                            message: "Overenie sa nepodarilo spustiť. Skús tag priložiť ešte raz."
                        )
                    }
                }
            }
        }
    }

    private static func scheduleRetry(_ attempt: Int) {
        retryWorkItem?.cancel()
        let item = DispatchWorkItem { dispatchPending(attempt: attempt) }
        retryWorkItem = item
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.10, execute: item)
    }

    private static func javascriptString(_ value: String) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: [value]),
              let json = String(data: data, encoding: .utf8),
              json.count >= 2 else { return "''" }
        return "(\(json))[0]"
    }
}

final class TFMNFCStatusRailV926 {
    static let shared = TFMNFCStatusRailV926()

    private weak var rail: UIVisualEffectView?
    private weak var iconView: UIImageView?
    private weak var kickerLabel: UILabel?
    private weak var titleLabel: UILabel?
    private weak var messageLabel: UILabel?
    private weak var progress: UIProgressView?
    private var dismissWork: DispatchWorkItem?

    private init() {}

    func showLoading() {
        DispatchQueue.main.async {
            self.cancelDismiss()
            guard self.ensureRail() else { return }
            self.kickerLabel?.text = "NFC • TURANSKÉ FITKO"
            self.titleLabel?.text = "NFC načítané"
            self.messageLabel?.text = "Overujem vstup so serverom…"
            self.iconView?.image = UIImage(systemName: "wave.3.right.circle.fill")
            self.applyAccent(error: false)
            self.progress?.progress = 0.18
            self.present()
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        }
    }

    func showResult(state: String, title: String, message: String) {
        DispatchQueue.main.async {
            self.cancelDismiss()
            guard self.ensureRail() else { return }
            let normalized = state.lowercased()
            let isError = normalized == "error" || normalized == "login"
            self.kickerLabel?.text = "NFC • TURANSKÉ FITKO"
            self.titleLabel?.text = title
            self.messageLabel?.text = message
            self.iconView?.image = UIImage(systemName: isError ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
            self.applyAccent(error: isError)
            self.progress?.progress = 1.0
            self.present()

            let feedback = UINotificationFeedbackGenerator()
            feedback.notificationOccurred(isError ? .warning : .success)

            self.progress?.setProgress(0, animated: true)
            let work = DispatchWorkItem { [weak self] in self?.hide() }
            self.dismissWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 4.2, execute: work)
        }
    }

    private func currentAccent() -> UIColor {
        if UIApplication.shared.alternateIconName == TFMNativeThemeIconV926.pinkIconName {
            return UIColor(red: 1.0, green: 0.31, blue: 0.58, alpha: 1.0)
        }
        return UIColor(red: 0.78, green: 1.0, blue: 0.0, alpha: 1.0)
    }

    private func applyAccent(error: Bool) {
        let accent = error ? UIColor(red: 1.0, green: 0.63, blue: 0.30, alpha: 1.0) : currentAccent()
        rail?.layer.borderColor = accent.withAlphaComponent(0.50).cgColor
        kickerLabel?.textColor = accent
        iconView?.tintColor = accent
        progress?.progressTintColor = accent
    }

    private func ensureRail() -> Bool {
        if rail != nil { return true }
        guard let window = keyWindow() else { return false }

        let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterialDark))
        blur.translatesAutoresizingMaskIntoConstraints = false
        blur.layer.cornerRadius = 24
        blur.layer.cornerCurve = .continuous
        blur.layer.borderWidth = 1
        blur.clipsToBounds = true
        blur.isUserInteractionEnabled = false

        let icon = UIImageView()
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.contentMode = .scaleAspectFit

        let kicker = UILabel()
        kicker.font = .systemFont(ofSize: 10, weight: .heavy)
        kicker.numberOfLines = 1

        let title = UILabel()
        title.textColor = .white
        title.font = .systemFont(ofSize: 17, weight: .bold)
        title.numberOfLines = 1
        title.adjustsFontSizeToFitWidth = true
        title.minimumScaleFactor = 0.78

        let message = UILabel()
        message.textColor = UIColor.white.withAlphaComponent(0.68)
        message.font = .systemFont(ofSize: 12, weight: .semibold)
        message.numberOfLines = 2

        let text = UIStackView(arrangedSubviews: [kicker, title, message])
        text.axis = .vertical
        text.spacing = 2

        let row = UIStackView(arrangedSubviews: [icon, text])
        row.translatesAutoresizingMaskIntoConstraints = false
        row.axis = .horizontal
        row.alignment = .center
        row.spacing = 13

        let bar = UIProgressView(progressViewStyle: .bar)
        bar.translatesAutoresizingMaskIntoConstraints = false
        bar.trackTintColor = UIColor.white.withAlphaComponent(0.08)

        blur.contentView.addSubview(row)
        blur.contentView.addSubview(bar)
        window.addSubview(blur)

        NSLayoutConstraint.activate([
            blur.leadingAnchor.constraint(equalTo: window.leadingAnchor, constant: 14),
            blur.trailingAnchor.constraint(equalTo: window.trailingAnchor, constant: -14),
            blur.topAnchor.constraint(equalTo: window.safeAreaLayoutGuide.topAnchor, constant: 8),
            blur.heightAnchor.constraint(greaterThanOrEqualToConstant: 88),
            row.leadingAnchor.constraint(equalTo: blur.contentView.leadingAnchor, constant: 15),
            row.trailingAnchor.constraint(equalTo: blur.contentView.trailingAnchor, constant: -15),
            row.topAnchor.constraint(equalTo: blur.contentView.topAnchor, constant: 12),
            row.bottomAnchor.constraint(equalTo: bar.topAnchor, constant: -10),
            icon.widthAnchor.constraint(equalToConstant: 42),
            icon.heightAnchor.constraint(equalToConstant: 42),
            bar.leadingAnchor.constraint(equalTo: blur.contentView.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: blur.contentView.trailingAnchor),
            bar.bottomAnchor.constraint(equalTo: blur.contentView.bottomAnchor),
            bar.heightAnchor.constraint(equalToConstant: 3),
        ])

        blur.alpha = 0
        blur.transform = CGAffineTransform(translationX: 0, y: -120)
        rail = blur
        iconView = icon
        kickerLabel = kicker
        titleLabel = title
        messageLabel = message
        progress = bar
        return true
    }

    private func present() {
        guard let rail else { return }
        UIView.animate(withDuration: 0.26, delay: 0, options: [.curveEaseOut, .beginFromCurrentState]) {
            rail.alpha = 1
            rail.transform = .identity
        }
    }

    private func hide() {
        guard let rail else { return }
        UIView.animate(withDuration: 0.22, delay: 0, options: [.curveEaseIn, .beginFromCurrentState]) {
            rail.alpha = 0
            rail.transform = CGAffineTransform(translationX: 0, y: -120)
        }
    }

    private func cancelDismiss() {
        dismissWork?.cancel()
        dismissWork = nil
    }

    private func keyWindow() -> UIWindow? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .sorted { ($0.isKeyWindow ? 1 : 0) > ($1.isKeyWindow ? 1 : 0) }
            .first
    }
}
'''

    swift += bridge
    required = ["TFMNFCBridgeV926", "onContinueUserActivity", "TFMNFCStatusRailV926", "window.TFMANFC926"]
    missing = [item for item in required if item not in swift]
    if missing:
        raise RuntimeError(f"App v9.26 validation failed: {missing}")
    APP.write_text(swift, encoding="utf-8")


def patch_project() -> None:
    project = PROJECT.read_text(encoding="utf-8")
    if "ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES = AppIconPink;" not in project:
        project = project.replace(
            "ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon; CODE_SIGN_STYLE = Automatic;",
            "ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES = AppIconPink; ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon; CODE_SIGN_ENTITLEMENTS = TuranskeFitkoApp/TuranskeFitkoApp.entitlements; CODE_SIGN_STYLE = Automatic;",
        )
        if project.count("ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES = AppIconPink;") != 2:
            raise RuntimeError("Could not add alternate icon + entitlements to both target build configurations.")

    if "A000015 /* TuranskeFitkoApp.entitlements */" not in project:
        project = once(
            project,
            '\t\tA000014 /* Info.plist */ = {isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; };\n',
            '\t\tA000014 /* Info.plist */ = {isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; };\n\t\tA000015 /* TuranskeFitkoApp.entitlements */ = {isa = PBXFileReference; lastKnownFileType = text.plist.entitlements; path = TuranskeFitkoApp.entitlements; sourceTree = "<group>"; };\n',
            "entitlements file reference",
        )
        project = once(
            project,
            '\t\tA000031 /* TuranskeFitkoApp */ = {isa = PBXGroup; children = (A000011 /* TuranskeFitkoApp.swift */, A000012 /* ContentView.swift */, A000013 /* Assets.xcassets */, A000014 /* Info.plist */); path = TuranskeFitkoApp; sourceTree = "<group>"; };\n',
            '\t\tA000031 /* TuranskeFitkoApp */ = {isa = PBXGroup; children = (A000011 /* TuranskeFitkoApp.swift */, A000012 /* ContentView.swift */, A000013 /* Assets.xcassets */, A000014 /* Info.plist */, A000015 /* TuranskeFitkoApp.entitlements */); path = TuranskeFitkoApp; sourceTree = "<group>"; };\n',
            "entitlements project group",
        )

    PROJECT.write_text(project, encoding="utf-8")

    ENTITLEMENTS.write_text('''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n    <key>com.apple.developer.associated-domains</key>\n    <array>\n        <string>applinks:turanskefitko.sk</string>\n    </array>\n</dict>\n</plist>\n''', encoding="utf-8")


def main() -> None:
    patch_content_view()
    patch_app()
    patch_project()
    print("Prepared v9.26 theme-linked alternate icon bridge")
    print("Prepared v9.26 NFC Universal Link -> WebView JSON -> native status rail")
    print("Prepared Associated Domains entitlement: applinks:turanskefitko.sk")


if __name__ == "__main__":
    main()
