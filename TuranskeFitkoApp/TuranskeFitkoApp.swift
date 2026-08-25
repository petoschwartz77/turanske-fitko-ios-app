import SwiftUI
import UIKit
import WebKit

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        continue userActivity: NSUserActivity,
        restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
    ) -> Bool {
        guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
              let url = userActivity.webpageURL else {
            return false
        }
        NFCDeepLinkRouter.handle(url, source: "appDelegateUserActivity")
        return true
    }

    func application(
        _ app: UIApplication,
        open url: URL,
        options: [UIApplication.OpenURLOptionsKey: Any] = [:]
    ) -> Bool {
        NFCDeepLinkRouter.handle(url, source: "appDelegateOpenURL")
        return true
    }
}

@main
struct TuranskeFitkoApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
                .onOpenURL { url in
                    NFCDeepLinkRouter.handle(url, source: "swiftUIOpenURL")
                }
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    guard let url = activity.webpageURL else { return }
                    NFCDeepLinkRouter.handle(url, source: "swiftUIUniversalLink")
                }
        }
    }
}

/// Native handoff for the NFC Universal Link.
///
/// The app is a SwiftUI + WKWebView wrapper. iOS can launch the native shell for a verified
/// Universal Link without automatically navigating the existing WKWebView. We therefore catch
/// the URL through both SwiftUI and UIApplicationDelegate, show an immediate native confirmation,
/// then force the same logged-in WKWebView to the NFC endpoint. The server renders the final
/// result modal (success, duplicate, unlinked membership, owner info, etc.).
enum NFCDeepLinkRouter {
    private static let allowedHost = "turanskefitko.sk"
    private static var pendingURL: URL?
    private static var retryWorkItem: DispatchWorkItem?
    private static var lastFingerprint = ""
    private static var lastHandledAt: TimeInterval = 0

    static func handle(_ incomingURL: URL, source: String) {
        DispatchQueue.main.async {
            guard let targetURL = normalizedNFCURL(from: incomingURL) else {
                print("[TF NFC] Ignored non-NFC URL from \(source): \(incomingURL.absoluteString)")
                return
            }

            let fingerprint = canonicalFingerprint(for: incomingURL)
            let now = Date().timeIntervalSince1970
            if fingerprint == lastFingerprint, now - lastHandledAt < 1.0 {
                print("[TF NFC] Ignored duplicate delivery from \(source)")
                return
            }
            lastFingerprint = fingerprint
            lastHandledAt = now

            NFCNativeOverlay.shared.show(
                title: "NFC načítané",
                message: "Spracúvam vstup…",
                state: .loading
            )

            pendingURL = targetURL
            retryWorkItem?.cancel()
            retryWorkItem = nil
            openPendingURL(attempt: 0)
        }
    }

    /// Native validation is deliberately broad. The server is the source of truth for token
    /// validity. Rejecting token shape in the native shell can silently drop a perfectly valid
    /// NFC tag after a future server-side token format change.
    private static func normalizedNFCURL(from incomingURL: URL) -> URL? {
        guard incomingURL.scheme?.lowercased() == "https" else { return nil }

        let rawHost = (incomingURL.host ?? "").lowercased()
        let host = rawHost.hasPrefix("www.") ? String(rawHost.dropFirst(4)) : rawHost
        guard host == allowedHost else { return nil }

        let path = incomingURL.path.lowercased()
        guard path.hasPrefix("/tfm-app/nfc/") else { return nil }

        guard var components = URLComponents(url: incomingURL, resolvingAgainstBaseURL: false) else {
            return nil
        }
        var queryItems = components.queryItems ?? []
        let reserved = Set(["tfma_nfc_app", "native", "tfma_native_handoff", "tfma_nocache"])
        queryItems.removeAll { reserved.contains($0.name) }
        queryItems.append(URLQueryItem(name: "tfma_nfc_app", value: "1"))
        queryItems.append(URLQueryItem(name: "native", value: "ios"))
        queryItems.append(URLQueryItem(name: "tfma_native_handoff", value: "1"))
        queryItems.append(URLQueryItem(
            name: "tfma_nocache",
            value: String(Int(Date().timeIntervalSince1970 * 1000))
        ))
        components.queryItems = queryItems
        return components.url
    }

    private static func canonicalFingerprint(for url: URL) -> String {
        let rawHost = (url.host ?? "").lowercased()
        let host = rawHost.hasPrefix("www.") ? String(rawHost.dropFirst(4)) : rawHost
        return "\(host)|\(url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))"
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
            print("[TF NFC] Forced WKWebView navigation to: \(targetURL.absoluteString)")
            verifyServerPopup(in: webView, attempt: 0)
            return
        }

        // Cold launch can deliver the Universal Link before SwiftUI has mounted WKWebView.
        guard attempt < 80 else {
            pendingURL = nil
            NFCNativeOverlay.shared.show(
                title: "NFC sa nepodarilo otvoriť",
                message: "Appka sa otvorila, ale vnútorné okno ešte nebolo pripravené. Prilož tag ešte raz.",
                state: .error
            )
            NFCNativeOverlay.shared.dismiss(after: 4.0)
            print("[TF NFC] WKWebView not found after cold-launch retry window")
            return
        }

        let workItem = DispatchWorkItem {
            openPendingURL(attempt: attempt + 1)
        }
        retryWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.10, execute: workItem)
    }

    /// The web result page contains #tfma811-title and body[data-state]. Polling it gives us a
    /// second confirmation path. If the web modal renders, the temporary native overlay disappears.
    /// If it never renders, the user still gets a visible error instead of a silent home screen.
    private static func verifyServerPopup(in webView: WKWebView, attempt: Int) {
        let script = #"""
        (() => {
          const title = document.querySelector('#tfma811-title');
          return JSON.stringify({
            title: title ? String(title.textContent || '').trim() : '',
            state: document.body ? String(document.body.getAttribute('data-state') || '') : '',
            path: String(location.pathname || '')
          });
        })();
        """#

        DispatchQueue.main.asyncAfter(deadline: .now() + (attempt == 0 ? 0.55 : 0.40)) {
            webView.evaluateJavaScript(script) { result, _ in
                DispatchQueue.main.async {
                    if let json = result as? String,
                       let data = json.data(using: .utf8),
                       let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        let title = (object["title"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                        let state = (object["state"] as? String ?? "").lowercased()
                        let path = (object["path"] as? String ?? "").lowercased()

                        if !title.isEmpty && path.hasPrefix("/tfm-app/nfc/") {
                            let overlayState: NFCNativeOverlay.State = (state == "error") ? .error : .success
                            NFCNativeOverlay.shared.show(
                                title: title,
                                message: "Potvrdené serverom",
                                state: overlayState
                            )
                            NFCNativeOverlay.shared.dismiss(after: 0.55)
                            print("[TF NFC] Server popup confirmed: \(title)")
                            return
                        }
                    }

                    if attempt < 18 {
                        verifyServerPopup(in: webView, attempt: attempt + 1)
                    } else {
                        NFCNativeOverlay.shared.show(
                            title: "NFC bez potvrdenia",
                            message: "Tag appku otvoril, ale server neposlal výsledok. Prilož tag ešte raz.",
                            state: .error
                        )
                        NFCNativeOverlay.shared.dismiss(after: 4.0)
                        print("[TF NFC] Server popup was not detected")
                    }
                }
            }
        }
    }

    private static func locateWebView() -> WKWebView? {
        let scenes = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .filter { $0.activationState != .unattached }

        let windows = scenes.flatMap(\.windows).sorted { lhs, rhs in
            if lhs.isKeyWindow != rhs.isKeyWindow { return lhs.isKeyWindow }
            return lhs.windowLevel.rawValue > rhs.windowLevel.rawValue
        }

        for window in windows {
            if let webView = findWebView(in: window) {
                return webView
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

final class NFCNativeOverlay {
    enum State {
        case loading
        case success
        case error
    }

    static let shared = NFCNativeOverlay()

    private weak var overlayView: UIVisualEffectView?
    private weak var titleLabel: UILabel?
    private weak var messageLabel: UILabel?
    private weak var symbolView: UIImageView?
    private var dismissWorkItem: DispatchWorkItem?

    private init() {}

    func show(title: String, message: String, state: State) {
        DispatchQueue.main.async {
            self.dismissWorkItem?.cancel()
            self.dismissWorkItem = nil

            let overlay = self.overlayView ?? self.makeOverlay()
            guard let overlay else { return }

            self.titleLabel?.text = title
            self.messageLabel?.text = message

            let symbolName: String
            switch state {
            case .loading: symbolName = "wave.3.right.circle.fill"
            case .success: symbolName = "checkmark.circle.fill"
            case .error: symbolName = "exclamationmark.circle.fill"
            }
            self.symbolView?.image = UIImage(systemName: symbolName)

            if overlay.alpha < 1 {
                overlay.alpha = 0
                UIView.animate(withDuration: 0.16) {
                    overlay.alpha = 1
                }
            }
        }
    }

    func dismiss(after delay: TimeInterval = 0) {
        DispatchQueue.main.async {
            self.dismissWorkItem?.cancel()
            let item = DispatchWorkItem { [weak self] in
                guard let self, let overlay = self.overlayView else { return }
                UIView.animate(withDuration: 0.18, animations: {
                    overlay.alpha = 0
                }, completion: { _ in
                    overlay.removeFromSuperview()
                })
            }
            self.dismissWorkItem = item
            DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: item)
        }
    }

    private func makeOverlay() -> UIVisualEffectView? {
        guard let window = activeWindow() else { return nil }

        let blur = UIBlurEffect(style: .systemUltraThinMaterialDark)
        let overlay = UIVisualEffectView(effect: blur)
        overlay.translatesAutoresizingMaskIntoConstraints = false
        overlay.layer.cornerRadius = 24
        overlay.layer.cornerCurve = .continuous
        overlay.clipsToBounds = true
        overlay.layer.borderWidth = 1
        overlay.layer.borderColor = UIColor.white.withAlphaComponent(0.16).cgColor
        overlay.isUserInteractionEnabled = false

        let symbol = UIImageView()
        symbol.translatesAutoresizingMaskIntoConstraints = false
        symbol.contentMode = .scaleAspectFit
        symbol.tintColor = .white

        let title = UILabel()
        title.translatesAutoresizingMaskIntoConstraints = false
        title.textColor = .white
        title.font = .systemFont(ofSize: 18, weight: .bold)
        title.numberOfLines = 2

        let message = UILabel()
        message.translatesAutoresizingMaskIntoConstraints = false
        message.textColor = UIColor.white.withAlphaComponent(0.68)
        message.font = .systemFont(ofSize: 12, weight: .semibold)
        message.numberOfLines = 2

        let textStack = UIStackView(arrangedSubviews: [title, message])
        textStack.translatesAutoresizingMaskIntoConstraints = false
        textStack.axis = .vertical
        textStack.spacing = 3

        let row = UIStackView(arrangedSubviews: [symbol, textStack])
        row.translatesAutoresizingMaskIntoConstraints = false
        row.axis = .horizontal
        row.alignment = .center
        row.spacing = 12

        overlay.contentView.addSubview(row)
        window.addSubview(overlay)

        NSLayoutConstraint.activate([
            overlay.leadingAnchor.constraint(equalTo: window.leadingAnchor, constant: 18),
            overlay.trailingAnchor.constraint(equalTo: window.trailingAnchor, constant: -18),
            overlay.topAnchor.constraint(equalTo: window.safeAreaLayoutGuide.topAnchor, constant: 14),
            overlay.heightAnchor.constraint(greaterThanOrEqualToConstant: 78),

            row.leadingAnchor.constraint(equalTo: overlay.contentView.leadingAnchor, constant: 16),
            row.trailingAnchor.constraint(equalTo: overlay.contentView.trailingAnchor, constant: -16),
            row.topAnchor.constraint(equalTo: overlay.contentView.topAnchor, constant: 13),
            row.bottomAnchor.constraint(equalTo: overlay.contentView.bottomAnchor, constant: -13),

            symbol.widthAnchor.constraint(equalToConstant: 38),
            symbol.heightAnchor.constraint(equalToConstant: 38),
        ])

        overlay.alpha = 0
        overlayView = overlay
        titleLabel = title
        messageLabel = message
        symbolView = symbol
        return overlay
    }

    private func activeWindow() -> UIWindow? {
        let scenes = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .filter { $0.activationState == .foregroundActive || $0.activationState == .foregroundInactive }
        for scene in scenes {
            if let key = scene.windows.first(where: { $0.isKeyWindow }) { return key }
            if let first = scene.windows.first { return first }
        }
        return nil
    }
}
