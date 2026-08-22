import Foundation
import UIKit
import WebKit

@MainActor
final class ThemeIconSynchronizer {
    static let shared = ThemeIconSynchronizer()

    private var timer: Timer?
    private var lastObservedTheme: String?
    private var lastAttemptedTheme: String?
    private var isApplying = false

    private init() {}

    func start() {
        guard timer == nil else { return }
        syncNow()
        let timer = Timer.scheduledTimer(withTimeInterval: 0.75, repeats: true) { _ in
            Task { @MainActor in
                ThemeIconSynchronizer.shared.syncNow()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    func syncNow() {
        guard !isApplying, let webView = findWebView() else { return }

        let script = #"""
        (() => {
          try {
            const htmlTheme = document.documentElement?.getAttribute('data-tfma85-theme');
            const bodyTheme = document.body?.getAttribute('data-tfma85-theme');
            const storedTheme = localStorage.getItem('tfma85_theme');
            return String(htmlTheme || bodyTheme || storedTheme || 'plugin').toLowerCase();
          } catch (_) {
            return 'plugin';
          }
        })();
        """#

        webView.evaluateJavaScript(script) { result, _ in
            Task { @MainActor in
                guard let theme = result as? String else { return }
                ThemeIconSynchronizer.shared.observe(theme: theme)
            }
        }
    }

    private func observe(theme rawTheme: String) {
        let theme = rawTheme.lowercased()
        guard theme == "plugin" || theme == "editorial" else { return }

        if lastObservedTheme != theme {
            lastObservedTheme = theme
            lastAttemptedTheme = nil
        }

        guard UIApplication.shared.supportsAlternateIcons else { return }
        let desiredIconName: String? = theme == "editorial" ? "PinkIcon" : nil

        if UIApplication.shared.alternateIconName == desiredIconName {
            lastAttemptedTheme = theme
            return
        }

        // One icon-change request per actual theme change. If the system/user
        // rejects the switch, do not spam the same request on every timer tick.
        guard lastAttemptedTheme != theme else { return }
        lastAttemptedTheme = theme
        isApplying = true

        UIApplication.shared.setAlternateIconName(desiredIconName) { _ in
            Task { @MainActor in
                ThemeIconSynchronizer.shared.isApplying = false
            }
        }
    }

    private func findWebView() -> WKWebView? {
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

    private func findWebView(in view: UIView) -> WKWebView? {
        if let webView = view as? WKWebView { return webView }
        for subview in view.subviews {
            if let webView = findWebView(in: subview) { return webView }
        }
        return nil
    }
}
