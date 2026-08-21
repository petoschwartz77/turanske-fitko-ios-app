import UIKit
import WebKit

/// Routes verified Turanske Fitko Universal Links into the existing WKWebView.
/// NFC tags keep a normal HTTPS URL; iOS decides whether to open the app or Safari.
enum UniversalLinkRouter {
    private static let allowedHost = "turanskefitko.sk"
    private static let allowedPathPrefix = "/tfm-app/"
    private static var pendingURL: URL?

    @discardableResult
    static func handle(_ url: URL) -> Bool {
        guard isAllowed(url) else { return false }
        pendingURL = url
        routePending(retries: 8)
        return true
    }

    static func resumePending() {
        routePending(retries: 8)
    }

    private static func isAllowed(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https" else { return false }
        let host = url.host?.lowercased() ?? ""
        guard host == allowedHost || host == "www.\(allowedHost)" else { return false }
        return url.path.hasPrefix(allowedPathPrefix)
    }

    private static func routePending(retries: Int) {
        DispatchQueue.main.async {
            guard let url = pendingURL else { return }

            if let webView = findWebView() {
                pendingURL = nil
                webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))
                return
            }

            guard retries > 0 else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.20) {
                routePending(retries: retries - 1)
            }
        }
    }

    private static func findWebView() -> WKWebView? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        for scene in scenes {
            for window in scene.windows where !window.isHidden {
                if let webView = findWebView(in: window) {
                    return webView
                }
            }
        }
        return nil
    }

    private static func findWebView(in view: UIView) -> WKWebView? {
        if let webView = view as? WKWebView { return webView }
        for subview in view.subviews {
            if let webView = findWebView(in: subview) { return webView }
        }
        return nil
    }
}

final class TFMAppDelegate: NSObject, UIApplicationDelegate {
    func applicationDidBecomeActive(_ application: UIApplication) {
        UniversalLinkRouter.resumePending()
    }
}
