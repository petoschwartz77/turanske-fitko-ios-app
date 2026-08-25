import SwiftUI
import UIKit
import WebKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        let rootView = ContentView().preferredColorScheme(.dark)
        let controller = UIHostingController(rootView: rootView)
        controller.view.backgroundColor = .black
        window.rootViewController = controller
        self.window = window
        window.makeKeyAndVisible()

        // No UIScene lifecycle on purpose. Universal Links are handled centrally by AppDelegate,
        // which avoids losing the NFC activity during SwiftUI scene creation / cold launch.
        if let url = launchOptions?[.url] as? URL {
            DispatchQueue.main.async {
                NFCDeepLinkRouter.handle(url, source: "launchOptionsURL")
            }
        }

        if let activityDictionary = launchOptions?[.userActivityDictionary] as? [AnyHashable: Any] {
            for value in activityDictionary.values {
                guard let activity = value as? NSUserActivity,
                      activity.activityType == NSUserActivityTypeBrowsingWeb,
                      let url = activity.webpageURL else { continue }
                DispatchQueue.main.async {
                    NFCDeepLinkRouter.handle(url, source: "launchOptionsUserActivity")
                }
                break
            }
        }

        return true
    }

    func application(
        _ application: UIApplication,
        continue userActivity: NSUserActivity,
        restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
    ) -> Bool {
        guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
              let url = userActivity.webpageURL else {
            return false
        }
        return NFCDeepLinkRouter.handle(url, source: "continueUserActivity")
    }

    func application(
        _ app: UIApplication,
        open url: URL,
        options: [UIApplication.OpenURLOptionsKey: Any] = [:]
    ) -> Bool {
        return NFCDeepLinkRouter.handle(url, source: "openURL")
    }
}

enum NFCDeepLinkRouter {
    private static let allowedHost = "turanskefitko.sk"
    private static var pendingURL: URL?
    private static var webViewRetryWorkItem: DispatchWorkItem?
    private static var requestTimeoutWorkItem: DispatchWorkItem?
    private static var lastFingerprint = ""
    private static var lastHandledAt: TimeInterval = 0
    private static var activeRequestID = UUID()

    @discardableResult
    static func handle(_ incomingURL: URL, source: String) -> Bool {
        guard let targetURL = normalizedNFCURL(from: incomingURL) else {
            print("[TF NFC 9.21] Ignored non-NFC URL from \(source): \(incomingURL.absoluteString)")
            return false
        }

        DispatchQueue.main.async {
            let fingerprint = canonicalFingerprint(for: incomingURL)
            let now = Date().timeIntervalSince1970
            if fingerprint == lastFingerprint, now - lastHandledAt < 1.25 {
                print("[TF NFC 9.21] Ignored duplicate delivery from \(source)")
                return
            }
            lastFingerprint = fingerprint
            lastHandledAt = now

            let requestID = UUID()
            activeRequestID = requestID
            pendingURL = targetURL
            webViewRetryWorkItem?.cancel()
            requestTimeoutWorkItem?.cancel()
            webViewRetryWorkItem = nil
            requestTimeoutWorkItem = nil

            NFCNativeModal.shared.showLoading()
            armGlobalTimeout(for: requestID)
            processPendingURL(requestID: requestID, attempt: 0)
            print("[TF NFC 9.21] Accepted NFC Universal Link from \(source): \(incomingURL.path)")
        }
        return true
    }

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

        var items = components.queryItems ?? []
        let reserved = Set([
            "tfma_nfc_app",
            "tfma_native_handoff",
            "tfma_native_json",
            "native",
            "tfma_nocache"
        ])
        items.removeAll { reserved.contains($0.name) }
        items.append(URLQueryItem(name: "tfma_nfc_app", value: "1"))
        items.append(URLQueryItem(name: "tfma_native_handoff", value: "1"))
        items.append(URLQueryItem(name: "tfma_native_json", value: "1"))
        items.append(URLQueryItem(name: "native", value: "ios"))
        items.append(URLQueryItem(
            name: "tfma_nocache",
            value: String(Int(Date().timeIntervalSince1970 * 1000))
        ))
        components.queryItems = items
        return components.url
    }

    private static func canonicalFingerprint(for url: URL) -> String {
        let rawHost = (url.host ?? "").lowercased()
        let host = rawHost.hasPrefix("www.") ? String(rawHost.dropFirst(4)) : rawHost
        return "\(host)|\(url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))"
    }

    private static func processPendingURL(requestID: UUID, attempt: Int) {
        guard requestID == activeRequestID, let targetURL = pendingURL else { return }

        guard let webView = locateWebView() else {
            guard attempt < 100 else {
                fail(
                    requestID: requestID,
                    title: "NFC sa nepodarilo spracovať",
                    message: "Appka sa otvorila, ale vnútorné prihlásené okno nebolo pripravené. Prilož tag ešte raz."
                )
                return
            }
            let item = DispatchWorkItem {
                processPendingURL(requestID: requestID, attempt: attempt + 1)
            }
            webViewRetryWorkItem = item
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.10, execute: item)
            return
        }

        pendingURL = nil
        webViewRetryWorkItem?.cancel()
        webViewRetryWorkItem = nil
        performNativeJSONRequest(targetURL, in: webView, requestID: requestID, attempt: 0)
    }

    /// Executes the NFC request inside the *already authenticated* WKWebView JavaScript context.
    /// This is intentionally different from navigating WKWebView: the visible Home screen never
    /// moves, WordPress receives the exact login cookies, and the native app receives only JSON.
    private static func performNativeJSONRequest(
        _ targetURL: URL,
        in webView: WKWebView,
        requestID: UUID,
        attempt: Int
    ) {
        guard requestID == activeRequestID else { return }

        let script = #"""
        const target = String(nfcURL || '');
        let theme = '';
        try { theme = String(localStorage.getItem('tfma85_theme') || ''); } catch (_) {}

        try {
            const response = await fetch(target, {
                method: 'GET',
                credentials: 'include',
                cache: 'no-store',
                redirect: 'follow',
                headers: {
                    'Accept': 'application/json',
                    'X-TFMA-Native-NFC': 'ios-9.21'
                }
            });
            const text = await response.text();
            return JSON.stringify({
                transportOK: response.ok,
                http: response.status,
                finalURL: String(response.url || ''),
                contentType: String(response.headers.get('content-type') || ''),
                theme,
                body: text
            });
        } catch (error) {
            return JSON.stringify({
                transportOK: false,
                http: 0,
                finalURL: '',
                contentType: '',
                theme,
                body: '',
                jsError: String(error && error.message ? error.message : error)
            });
        }
        """#

        if #available(iOS 15.0, *) {
            webView.callAsyncJavaScript(
                script,
                arguments: ["nfcURL": targetURL.absoluteString],
                in: nil,
                contentWorld: .page
            ) { result in
                DispatchQueue.main.async {
                    guard requestID == activeRequestID else { return }
                    switch result {
                    case .success(let value):
                        if let raw = value as? String, consumeTransportJSON(raw, requestID: requestID) {
                            return
                        }
                        retryOrFail(targetURL, webView: webView, requestID: requestID, attempt: attempt, reason: "Neplatná odpoveď WebView")
                    case .failure(let error):
                        retryOrFail(targetURL, webView: webView, requestID: requestID, attempt: attempt, reason: error.localizedDescription)
                    }
                }
            }
        } else {
            fail(
                requestID: requestID,
                title: "NFC vyžaduje novší iOS",
                message: "Aktualizuj iPhone na iOS 15 alebo novší."
            )
        }
    }

    private static func retryOrFail(
        _ targetURL: URL,
        webView: WKWebView,
        requestID: UUID,
        attempt: Int,
        reason: String
    ) {
        guard requestID == activeRequestID else { return }
        if attempt < 5 {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                performNativeJSONRequest(targetURL, in: webView, requestID: requestID, attempt: attempt + 1)
            }
            return
        }
        fail(
            requestID: requestID,
            title: "NFC bez potvrdenia",
            message: "Server sa nepodarilo overiť. Skús tag priložiť ešte raz. (\(reason))"
        )
    }

    @discardableResult
    private static func consumeTransportJSON(_ raw: String, requestID: UUID) -> Bool {
        guard let rawData = raw.data(using: .utf8),
              let transport = try? JSONSerialization.jsonObject(with: rawData) as? [String: Any] else {
            return false
        }

        let theme = (transport["theme"] as? String ?? "").lowercased()
        NFCNativeModal.shared.setTheme(theme)

        let finalURL = transport["finalURL"] as? String ?? ""
        let body = transport["body"] as? String ?? ""
        let jsError = transport["jsError"] as? String ?? ""

        guard jsError.isEmpty else { return false }

        guard let bodyData = body.data(using: .utf8),
              let payload = try? JSONSerialization.jsonObject(with: bodyData) as? [String: Any] else {
            if finalURL.contains("/tfm-app/") && !finalURL.contains("/tfm-app/nfc/") {
                fail(
                    requestID: requestID,
                    title: "Prihlásenie je potrebné",
                    message: "Prihlás sa do Turanské Fitko App a potom prilož NFC tag znova."
                )
                return true
            }
            return false
        }

        let ok = payload["ok"] as? Bool ?? false
        let state = (payload["state"] as? String ?? "error").lowercased()
        let title = payload["title"] as? String ?? "NFC výsledok"
        let message = payload["message"] as? String ?? ""
        let seconds = max(2, min(8, payload["return_seconds"] as? Int ?? 4))

        guard ok else {
            fail(
                requestID: requestID,
                title: title.isEmpty ? "NFC bez potvrdenia" : title,
                message: message.isEmpty ? "Server neposlal platný výsledok." : message
            )
            return true
        }

        requestTimeoutWorkItem?.cancel()
        requestTimeoutWorkItem = nil
        activeRequestID = UUID()
        pendingURL = nil

        NFCNativeModal.shared.showResult(
            state: state,
            title: title,
            message: message,
            seconds: seconds
        )
        print("[TF NFC 9.21] Server confirmed state=\(state), title=\(title)")
        return true
    }

    private static func armGlobalTimeout(for requestID: UUID) {
        let item = DispatchWorkItem {
            guard requestID == activeRequestID else { return }
            fail(
                requestID: requestID,
                title: "NFC bez potvrdenia",
                message: "Spracovanie trvalo príliš dlho. Prilož tag ešte raz."
            )
        }
        requestTimeoutWorkItem = item
        DispatchQueue.main.asyncAfter(deadline: .now() + 12.0, execute: item)
    }

    private static func fail(requestID: UUID, title: String, message: String) {
        guard requestID == activeRequestID else { return }
        requestTimeoutWorkItem?.cancel()
        webViewRetryWorkItem?.cancel()
        requestTimeoutWorkItem = nil
        webViewRetryWorkItem = nil
        pendingURL = nil
        activeRequestID = UUID()
        NFCNativeModal.shared.showResult(state: "error", title: title, message: message, seconds: 4)
        print("[TF NFC 9.21] Failure: \(title) – \(message)")
    }

    private static func locateWebView() -> WKWebView? {
        guard let appDelegate = UIApplication.shared.delegate as? AppDelegate,
              let window = appDelegate.window else {
            return nil
        }
        return findWebView(in: window)
    }

    private static func findWebView(in view: UIView) -> WKWebView? {
        if let webView = view as? WKWebView { return webView }
        for subview in view.subviews {
            if let webView = findWebView(in: subview) { return webView }
        }
        return nil
    }
}

final class NFCNativeModal {
    static let shared = NFCNativeModal()

    private weak var backdrop: UIVisualEffectView?
    private weak var card: UIView?
    private weak var iconView: UIImageView?
    private weak var spinner: UIActivityIndicatorView?
    private weak var kickerLabel: UILabel?
    private weak var titleLabel: UILabel?
    private weak var messageLabel: UILabel?
    private weak var countdownLabel: UILabel?
    private weak var countdownCaption: UILabel?

    private var countdownTimer: Timer?
    private var dismissWorkItem: DispatchWorkItem?
    private var accent = UIColor.white

    private init() {}

    func setTheme(_ rawTheme: String) {
        let theme = rawTheme.lowercased()
        if theme == "editorial" || theme == "pink" || theme == "rose" {
            accent = UIColor(red: 1.0, green: 0.31, blue: 0.58, alpha: 1.0)
        } else {
            accent = UIColor(red: 0.78, green: 1.0, blue: 0.0, alpha: 1.0)
        }
        applyAccent()
    }

    func showLoading() {
        DispatchQueue.main.async {
            self.dismissWorkItem?.cancel()
            self.countdownTimer?.invalidate()
            self.countdownTimer = nil

            guard self.ensureModal() else { return }
            self.kickerLabel?.text = "NFC • TURANSKÉ FITKO"
            self.titleLabel?.text = "Spracúvam NFC…"
            self.messageLabel?.text = "Overujem tvoj vstup so serverom."
            self.iconView?.image = UIImage(systemName: "wave.3.right.circle.fill")
            self.iconView?.isHidden = false
            self.countdownLabel?.isHidden = true
            self.countdownCaption?.isHidden = true
            self.spinner?.isHidden = false
            self.spinner?.startAnimating()
            self.presentIfNeeded()
        }
    }

    func showResult(state: String, title: String, message: String, seconds: Int) {
        DispatchQueue.main.async {
            self.dismissWorkItem?.cancel()
            self.countdownTimer?.invalidate()
            self.countdownTimer = nil

            guard self.ensureModal() else { return }
            self.spinner?.stopAnimating()
            self.spinner?.isHidden = true
            self.countdownLabel?.isHidden = false
            self.countdownCaption?.isHidden = false
            self.kickerLabel?.text = "NFC • TURANSKÉ FITKO"
            self.titleLabel?.text = title
            self.messageLabel?.text = message

            let normalized = state.lowercased()
            if normalized == "error" || normalized == "login" {
                self.iconView?.image = UIImage(systemName: "exclamationmark.circle.fill")
                UINotificationFeedbackGenerator().notificationOccurred(.error)
            } else if normalized == "info" || normalized == "duplicate" {
                self.iconView?.image = UIImage(systemName: "checkmark.shield.fill")
                UINotificationFeedbackGenerator().notificationOccurred(.success)
            } else {
                self.iconView?.image = UIImage(systemName: "checkmark.circle.fill")
                UINotificationFeedbackGenerator().notificationOccurred(.success)
            }
            self.iconView?.isHidden = false

            self.presentIfNeeded()
            self.startCountdown(seconds: seconds)
        }
    }

    private func startCountdown(seconds: Int) {
        var remaining = max(1, seconds)
        countdownLabel?.text = String(remaining)
        countdownCaption?.text = "Návrat do appky"

        countdownTimer?.invalidate()
        countdownTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] timer in
            guard let self = self else {
                timer.invalidate()
                return
            }
            remaining -= 1
            if remaining <= 0 {
                timer.invalidate()
                self.countdownTimer = nil
                self.dismiss()
            } else {
                self.countdownLabel?.text = String(remaining)
            }
        }
    }

    private func ensureModal() -> Bool {
        if backdrop != nil, card != nil { return true }
        guard let window = activeWindow() else { return false }

        let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterialDark))
        blur.translatesAutoresizingMaskIntoConstraints = false
        blur.alpha = 0
        blur.isUserInteractionEnabled = true

        let dim = UIView()
        dim.translatesAutoresizingMaskIntoConstraints = false
        dim.backgroundColor = UIColor.black.withAlphaComponent(0.42)
        blur.contentView.addSubview(dim)

        let card = UIView()
        card.translatesAutoresizingMaskIntoConstraints = false
        card.backgroundColor = UIColor(red: 0.055, green: 0.045, blue: 0.052, alpha: 0.96)
        card.layer.cornerRadius = 30
        card.layer.cornerCurve = .continuous
        card.layer.borderWidth = 1
        card.layer.borderColor = UIColor.white.withAlphaComponent(0.12).cgColor
        card.layer.shadowColor = UIColor.black.cgColor
        card.layer.shadowOpacity = 0.45
        card.layer.shadowRadius = 34
        card.layer.shadowOffset = CGSize(width: 0, height: 18)

        let icon = UIImageView()
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.contentMode = .scaleAspectFit

        let spinner = UIActivityIndicatorView(style: .medium)
        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.color = .white

        let kicker = UILabel()
        kicker.translatesAutoresizingMaskIntoConstraints = false
        kicker.textAlignment = .center
        kicker.font = .systemFont(ofSize: 10, weight: .heavy)
        kicker.textColor = UIColor.white.withAlphaComponent(0.58)
        kicker.numberOfLines = 1

        let title = UILabel()
        title.translatesAutoresizingMaskIntoConstraints = false
        title.textAlignment = .center
        title.font = .systemFont(ofSize: 28, weight: .black)
        title.textColor = .white
        title.numberOfLines = 3
        title.adjustsFontSizeToFitWidth = true
        title.minimumScaleFactor = 0.76

        let message = UILabel()
        message.translatesAutoresizingMaskIntoConstraints = false
        message.textAlignment = .center
        message.font = .systemFont(ofSize: 14, weight: .medium)
        message.textColor = UIColor.white.withAlphaComponent(0.67)
        message.numberOfLines = 5

        let countdown = UILabel()
        countdown.translatesAutoresizingMaskIntoConstraints = false
        countdown.textAlignment = .center
        countdown.font = .monospacedDigitSystemFont(ofSize: 28, weight: .black)
        countdown.textColor = .white
        countdown.backgroundColor = UIColor.white.withAlphaComponent(0.06)
        countdown.layer.cornerRadius = 28
        countdown.layer.cornerCurve = .continuous
        countdown.clipsToBounds = true

        let countdownCaption = UILabel()
        countdownCaption.translatesAutoresizingMaskIntoConstraints = false
        countdownCaption.textAlignment = .center
        countdownCaption.font = .systemFont(ofSize: 10, weight: .bold)
        countdownCaption.textColor = UIColor.white.withAlphaComponent(0.48)
        countdownCaption.text = "Návrat do appky"

        card.addSubview(icon)
        card.addSubview(spinner)
        card.addSubview(kicker)
        card.addSubview(title)
        card.addSubview(message)
        card.addSubview(countdown)
        card.addSubview(countdownCaption)
        blur.contentView.addSubview(card)
        window.addSubview(blur)

        NSLayoutConstraint.activate([
            blur.leadingAnchor.constraint(equalTo: window.leadingAnchor),
            blur.trailingAnchor.constraint(equalTo: window.trailingAnchor),
            blur.topAnchor.constraint(equalTo: window.topAnchor),
            blur.bottomAnchor.constraint(equalTo: window.bottomAnchor),

            dim.leadingAnchor.constraint(equalTo: blur.contentView.leadingAnchor),
            dim.trailingAnchor.constraint(equalTo: blur.contentView.trailingAnchor),
            dim.topAnchor.constraint(equalTo: blur.contentView.topAnchor),
            dim.bottomAnchor.constraint(equalTo: blur.contentView.bottomAnchor),

            card.leadingAnchor.constraint(greaterThanOrEqualTo: blur.contentView.leadingAnchor, constant: 22),
            card.trailingAnchor.constraint(lessThanOrEqualTo: blur.contentView.trailingAnchor, constant: -22),
            card.centerXAnchor.constraint(equalTo: blur.contentView.centerXAnchor),
            card.centerYAnchor.constraint(equalTo: blur.contentView.centerYAnchor),
            card.widthAnchor.constraint(lessThanOrEqualToConstant: 390),

            icon.topAnchor.constraint(equalTo: card.topAnchor, constant: 24),
            icon.centerXAnchor.constraint(equalTo: card.centerXAnchor),
            icon.widthAnchor.constraint(equalToConstant: 64),
            icon.heightAnchor.constraint(equalToConstant: 64),

            spinner.centerXAnchor.constraint(equalTo: icon.centerXAnchor),
            spinner.centerYAnchor.constraint(equalTo: icon.centerYAnchor),

            kicker.topAnchor.constraint(equalTo: icon.bottomAnchor, constant: 14),
            kicker.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 18),
            kicker.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -18),

            title.topAnchor.constraint(equalTo: kicker.bottomAnchor, constant: 8),
            title.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 20),
            title.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -20),

            message.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 9),
            message.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 22),
            message.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -22),

            countdown.topAnchor.constraint(equalTo: message.bottomAnchor, constant: 20),
            countdown.centerXAnchor.constraint(equalTo: card.centerXAnchor),
            countdown.widthAnchor.constraint(equalToConstant: 56),
            countdown.heightAnchor.constraint(equalToConstant: 56),

            countdownCaption.topAnchor.constraint(equalTo: countdown.bottomAnchor, constant: 7),
            countdownCaption.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 18),
            countdownCaption.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -18),
            countdownCaption.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -22)
        ])

        self.backdrop = blur
        self.card = card
        self.iconView = icon
        self.spinner = spinner
        self.kickerLabel = kicker
        self.titleLabel = title
        self.messageLabel = message
        self.countdownLabel = countdown
        self.countdownCaption = countdownCaption
        applyAccent()
        return true
    }

    private func applyAccent() {
        DispatchQueue.main.async {
            self.iconView?.tintColor = self.accent
            self.kickerLabel?.textColor = self.accent.withAlphaComponent(0.90)
            self.card?.layer.borderColor = self.accent.withAlphaComponent(0.35).cgColor
            self.countdownLabel?.layer.borderWidth = 1
            self.countdownLabel?.layer.borderColor = self.accent.withAlphaComponent(0.34).cgColor
            self.countdownLabel?.textColor = self.accent
        }
    }

    private func presentIfNeeded() {
        guard let backdrop = backdrop else { return }
        if backdrop.superview == nil, let window = activeWindow() {
            window.addSubview(backdrop)
        }
        if backdrop.alpha < 1 {
            backdrop.transform = CGAffineTransform(scaleX: 1.015, y: 1.015)
            UIView.animate(withDuration: 0.18) {
                backdrop.alpha = 1
                backdrop.transform = .identity
            }
        }
    }

    private func dismiss() {
        countdownTimer?.invalidate()
        countdownTimer = nil
        guard let backdrop = backdrop else { return }
        UIView.animate(withDuration: 0.20, animations: {
            backdrop.alpha = 0
            backdrop.transform = CGAffineTransform(scaleX: 0.985, y: 0.985)
        }, completion: { [weak self] _ in
            backdrop.removeFromSuperview()
            self?.backdrop = nil
            self?.card = nil
            self?.iconView = nil
            self?.spinner = nil
            self?.kickerLabel = nil
            self?.titleLabel = nil
            self?.messageLabel = nil
            self?.countdownLabel = nil
            self?.countdownCaption = nil
        })
    }

    private func activeWindow() -> UIWindow? {
        if let appDelegate = UIApplication.shared.delegate as? AppDelegate,
           let window = appDelegate.window {
            return window
        }
        return UIApplication.shared.windows.first(where: { $0.isKeyWindow })
    }
}
