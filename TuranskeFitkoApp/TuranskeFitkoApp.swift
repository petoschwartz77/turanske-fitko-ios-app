import SwiftUI
import UIKit
import WebKit

@main
struct TuranskeFitkoApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
                .onOpenURL { url in
                    NFCDeepLinkRouter.handle(url, source: "openURL")
                }
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    guard let url = activity.webpageURL else { return }
                    NFCDeepLinkRouter.handle(url, source: "universalLink")
                }
        }
    }
}

/// Native handoff for NFC Universal Links.
///
/// The app is a direct SwiftUI + WKWebView wrapper, not a Capacitor shell. iOS therefore
/// launches the app for a verified Universal Link but will not automatically navigate the
/// already-running WKWebView to that URL. This router validates the NFC URL and loads it
/// directly in the existing WebView so the WordPress NFC endpoint can render the result popup.
private enum NFCDeepLinkRouter {
    private static let allowedHost = "turanskefitko.sk"
    private static var pendingURL: URL?
    private static var retryWorkItem: DispatchWorkItem?
    private static var lastFingerprint = ""
    private static var lastHandledAt: TimeInterval = 0

    static func handle(_ incomingURL: URL, source: String) {
        DispatchQueue.main.async {
            guard let targetURL = normalizedNFCURL(from: incomingURL) else {
                print("[TF NFC] Ignored external URL from \(source): \(incomingURL.absoluteString)")
                return
            }

            let fingerprint = canonicalFingerprint(for: incomingURL)
            let now = Date().timeIntervalSince1970
            if fingerprint == lastFingerprint, now - lastHandledAt < 1.5 {
                print("[TF NFC] Ignored duplicate Universal Link delivery")
                return
            }
            lastFingerprint = fingerprint
            lastHandledAt = now

            pendingURL = targetURL
            retryWorkItem?.cancel()
            retryWorkItem = nil
            openPendingURL(attempt: 0)
        }
    }

    private static func normalizedNFCURL(from incomingURL: URL) -> URL? {
        guard incomingURL.scheme?.lowercased() == "https" else { return nil }

        let host = (incomingURL.host ?? "")
            .lowercased()
            .replacingOccurrences(of: "www.", with: "")
        guard host == allowedHost else { return nil }

        let parts = incomingURL.path.split(separator: "/").map(String.init)
        guard parts.count == 3 || parts.count == 4 else { return nil }
        guard parts[0] == "tfm-app", parts[1] == "nfc" else { return nil }

        let token: String
        if parts.count == 4 {
            guard parts[2] == "in" || parts[2] == "out" else { return nil }
            token = parts[3]
        } else {
            // Backward-compatible legacy NFC check-in URL: /tfm-app/nfc/{token}/
            token = parts[2]
        }

        guard (24...128).contains(token.count) else { return nil }
        let allowedTokenCharacters = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
        guard token.unicodeScalars.allSatisfy({ allowedTokenCharacters.contains($0) }) else { return nil }

        guard var components = URLComponents(url: incomingURL, resolvingAgainstBaseURL: false) else { return nil }
        var queryItems = components.queryItems ?? []
        queryItems.removeAll { item in
            ["tfma_nfc_app", "native", "tfma_native_handoff", "tfma_nocache"].contains(item.name)
        }
        queryItems.append(URLQueryItem(name: "tfma_nfc_app", value: "1"))
        queryItems.append(URLQueryItem(name: "native", value: "ios"))
        queryItems.append(URLQueryItem(name: "tfma_native_handoff", value: "1"))
        queryItems.append(URLQueryItem(name: "tfma_nocache", value: String(Int(Date().timeIntervalSince1970 * 1000))))
        components.queryItems = queryItems
        return components.url
    }

    private static func canonicalFingerprint(for url: URL) -> String {
        let host = (url.host ?? "").lowercased().replacingOccurrences(of: "www.", with: "")
        return "\(host)\(url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))"
    }

    private static func openPendingURL(attempt: Int) {
        guard let targetURL = pendingURL else { return }

        if let webView = locateWebView() {
            pendingURL = nil
            retryWorkItem?.cancel()
            retryWorkItem = nil

            webView.stopLoading()
            let request = URLRequest(
                url: targetURL,
                cachePolicy: .reloadIgnoringLocalCacheData,
                timeoutInterval: 30
            )
            webView.load(request)
            print("[TF NFC] Navigated WKWebView to NFC endpoint: \(targetURL.path)")
            return
        }

        // Cold launch: SwiftUI may deliver the Universal Link before WKWebView exists.
        // Retry for up to ~6 seconds instead of losing the NFC event.
        guard attempt < 60 else {
            print("[TF NFC] Could not locate WKWebView after cold launch")
            return
        }

        let workItem = DispatchWorkItem {
            openPendingURL(attempt: attempt + 1)
        }
        retryWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.10, execute: workItem)
    }

    private static func locateWebView() -> WKWebView? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let windows = scenes.flatMap(\.windows)
        let orderedWindows = windows.sorted { lhs, rhs in
            if lhs.isKeyWindow != rhs.isKeyWindow { return lhs.isKeyWindow }
            return lhs.windowLevel.rawValue > rhs.windowLevel.rawValue
        }

        for window in orderedWindows {
            if let webView = findWebView(in: window) {
                return webView
            }
        }
        return nil
    }

    private static func findWebView(in view: UIView) -> WKWebView? {
        if let webView = view as? WKWebView {
            return webView
        }
        for subview in view.subviews {
            if let webView = findWebView(in: subview) {
                return webView
            }
        }
        return nil
    }
}
