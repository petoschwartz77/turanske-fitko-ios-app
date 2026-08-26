#!/usr/bin/env python3
"""Patch the iOS WKWebView wrapper with v9.24 native persistent authentication.

WordPress remains the source of truth for accounts and permissions. The native app stores only a
random, revocable device token in the iOS Keychain. If WebKit loses its cookies after an update,
the app exchanges that token for a one-time WordPress login ticket and recreates the normal web
session. Explicit logout, account switching and password-security events revoke/replace the token.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT_VIEW = ROOT / "TuranskeFitkoApp" / "ContentView.swift"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Could not patch {label}; expected one match, found {count}.")
    return text.replace(old, new, 1)


def main() -> None:
    swift = CONTENT_VIEW.read_text(encoding="utf-8")

    if "enum TFNativeAuth924" not in swift:
        swift = replace_once(
            swift,
            "import AudioToolbox\n",
            "import AudioToolbox\nimport Foundation\nimport Security\n",
            "native-auth imports",
        )

        native_auth = r'''
enum TFNativeAuth924 {
    private static let endpoint = URL(string: "https://turanskefitko.sk/wp-admin/admin-ajax.php")!
    private static let service = "sk.turanskefitko.app.native-auth"
    private static let account = "persistent-login"
    private static let explicitLogoutKey = "tfma924.explicit-logout"
    private static let nativeUserAgent = "TFMiOSApp TFMNativeApp TuranskeFitkoNative/9.24"

    private static var shouldEnroll = false
    private static var exportInFlight = false
    private static var restoreInFlight = false

    static let bridgeScript = #"""
    (() => {
        if (window.__TFMA924NativeAuthBridge) return;
        window.__TFMA924NativeAuthBridge = true;
        document.addEventListener('click', (event) => {
            try {
                const target = event.target && event.target.closest
                    ? event.target.closest('[data-tfma764-forget-email]')
                    : null;
                if (target) {
                    window.webkit?.messageHandlers?.tfmaNativeAuth?.postMessage({ event: 'switchAccount' });
                }
            } catch (_) {}
        }, true);
    })();
    """#

    static func loadInitialPage(in webView: WKWebView, fallback: URL) {
        precondition(Thread.isMainThread)

        if UserDefaults.standard.bool(forKey: explicitLogoutKey) {
            shouldEnroll = true
            load(fallback, in: webView)
            return
        }

        guard let token = loadToken(), !token.isEmpty else {
            shouldEnroll = true
            load(fallback, in: webView)
            return
        }

        guard !restoreInFlight else { return }
        restoreInFlight = true

        post(
            action: "tfma924_native_auth_restore",
            token: token,
            purpose: "restore"
        ) { data, response, error in
            DispatchQueue.main.async {
                restoreInFlight = false

                guard error == nil,
                      let http = response as? HTTPURLResponse,
                      (200...299).contains(http.statusCode),
                      let data,
                      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      object["success"] as? Bool == true,
                      let payload = object["data"] as? [String: Any],
                      let redirectString = payload["redirect"] as? String,
                      let redirect = URL(string: redirectString),
                      isFirstParty(redirect) else {
                    // The server may have revoked the token after password reset/security changes.
                    deleteToken()
                    shouldEnroll = true
                    load(fallback, in: webView)
                    return
                }

                shouldEnroll = false
                UserDefaults.standard.set(false, forKey: explicitLogoutKey)
                load(redirect, in: webView)
            }
        }
    }

    static func maybeEnroll(in webView: WKWebView) {
        precondition(Thread.isMainThread)
        guard !exportInFlight else { return }
        if loadToken() != nil && !shouldEnroll { return }

        exportInFlight = true
        let script = #"""
        (() => {
            const send = (payload) => {
                try { window.webkit?.messageHandlers?.tfmaNativeAuth?.postMessage(payload); } catch (_) {}
            };
            const body = new URLSearchParams({ action: 'tfma924_native_auth_export' }).toString();
            fetch('/wp-admin/admin-ajax.php', {
                method: 'POST',
                credentials: 'include',
                cache: 'no-store',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Accept': 'application/json',
                    'X-TFMA-Native-Auth': 'enroll-9.24'
                },
                body
            })
            .then((response) => response.json())
            .then((json) => send({
                event: 'enroll',
                success: !!json?.success,
                token: String(json?.data?.token || '')
            }))
            .catch(() => send({ event: 'enroll', success: false, token: '' }));
        })();
        """#

        webView.evaluateJavaScript(script) { _, error in
            if error != nil {
                DispatchQueue.main.async { exportInFlight = false }
            }
        }
    }

    static func handleBridgeMessage(_ body: Any) {
        guard let payload = body as? [String: Any],
              let event = payload["event"] as? String else { return }

        switch event {
        case "enroll":
            exportInFlight = false
            guard payload["success"] as? Bool == true,
                  let token = payload["token"] as? String,
                  token.count >= 40 else { return }
            if storeToken(token) {
                shouldEnroll = false
                UserDefaults.standard.set(false, forKey: explicitLogoutKey)
                print("[TF Auth 9.24] Native Keychain login enrolled")
            }

        case "switchAccount":
            clearForAccountSwitch()

        default:
            break
        }
    }

    static func inspectNavigation(_ url: URL) {
        guard isFirstParty(url) else { return }
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let items = components?.queryItems ?? []
        let values = Dictionary(uniqueKeysWithValues: items.map { ($0.name.lowercased(), ($0.value ?? "").lowercased()) })

        let explicitLogout = values["tfma61_logout"] == "1"
            || values["tfma_logout_complete"] == "1"
            || values["tfma_account_deleted"] == "1"
            || (values["action"] == "logout")

        if explicitLogout {
            markExplicitLogout()
        }
    }

    private static func clearForAccountSwitch() {
        let oldToken = loadToken()
        deleteToken()
        shouldEnroll = true
        UserDefaults.standard.set(false, forKey: explicitLogoutKey)
        if let oldToken { revoke(oldToken) }
        print("[TF Auth 9.24] Cleared native token for account switch")
    }

    private static func markExplicitLogout() {
        let oldToken = loadToken()
        deleteToken()
        shouldEnroll = true
        UserDefaults.standard.set(true, forKey: explicitLogoutKey)
        if let oldToken { revoke(oldToken) }
        print("[TF Auth 9.24] Explicit logout revoked native token")
    }

    private static func revoke(_ token: String) {
        post(
            action: "tfma924_native_auth_revoke",
            token: token,
            purpose: "revoke"
        ) { _, _, _ in }
    }

    private static func post(
        action: String,
        token: String?,
        purpose: String,
        completion: @escaping (Data?, URLResponse?, Error?) -> Void
    ) {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 15
        request.setValue("application/x-www-form-urlencoded; charset=UTF-8", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("\(purpose)-9.24", forHTTPHeaderField: "X-TFMA-Native-Auth")
        request.setValue(nativeUserAgent, forHTTPHeaderField: "User-Agent")

        var components = URLComponents()
        var items = [URLQueryItem(name: "action", value: action)]
        if let token { items.append(URLQueryItem(name: "token", value: token)) }
        components.queryItems = items
        request.httpBody = components.percentEncodedQuery?.data(using: .utf8)

        URLSession.shared.dataTask(with: request, completionHandler: completion).resume()
    }

    private static func load(_ url: URL, in webView: WKWebView) {
        webView.load(URLRequest(
            url: url,
            cachePolicy: .reloadIgnoringLocalCacheData,
            timeoutInterval: 30
        ))
    }

    private static func isFirstParty(_ url: URL) -> Bool {
        let host = (url.host ?? "").lowercased()
        return host == "turanskefitko.sk" || host.hasSuffix(".turanskefitko.sk")
    }

    private static func keychainQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    private static func loadToken() -> String? {
        var query = keychainQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let token = String(data: data, encoding: .utf8),
              !token.isEmpty else { return nil }
        return token
    }

    @discardableResult
    private static func storeToken(_ token: String) -> Bool {
        guard let data = token.data(using: .utf8) else { return false }
        deleteToken()
        var query = keychainQuery()
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(query as CFDictionary, nil) == errSecSuccess
    }

    private static func deleteToken() {
        SecItemDelete(keychainQuery() as CFDictionary)
    }
}

'''
        swift = replace_once(
            swift,
            "struct ContentView: View {",
            native_auth + "struct ContentView: View {",
            "TFNativeAuth924 manager",
        )

    if "configuration.websiteDataStore = .default()" not in swift:
        swift = replace_once(
            swift,
            "        let configuration = WKWebViewConfiguration()\n",
            "        let configuration = WKWebViewConfiguration()\n        configuration.websiteDataStore = .default()\n",
            "persistent WKWebsiteDataStore",
        )

    if 'name: "tfmaNativeAuth"' not in swift:
        swift = replace_once(
            swift,
            '        contentController.add(context.coordinator, name: "tfmaNative")\n',
            '        contentController.add(context.coordinator, name: "tfmaNative")\n        contentController.add(context.coordinator, name: "tfmaNativeAuth")\n',
            "native auth message handler",
        )

        user_script_anchor = '''        contentController.addUserScript(\n            WKUserScript(\n                source: Self.leoProteinAnimationScript,\n                injectionTime: .atDocumentEnd,\n                forMainFrameOnly: true\n            )\n        )\n'''
        user_script_replacement = user_script_anchor + '''        contentController.addUserScript(\n            WKUserScript(\n                source: TFNativeAuth924.bridgeScript,\n                injectionTime: .atDocumentEnd,\n                forMainFrameOnly: true\n            )\n        )\n'''
        swift = replace_once(
            swift,
            user_script_anchor,
            user_script_replacement,
            "native auth account-switch bridge",
        )

    old_load = "        webView.load(URLRequest(url: appURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))\n"
    if old_load in swift:
        swift = swift.replace(
            old_load,
            "        TFNativeAuth924.loadInitialPage(in: webView, fallback: appURL)\n",
            1,
        )
    elif "TFNativeAuth924.loadInitialPage" not in swift:
        raise RuntimeError("Could not replace initial WebView load with native restore flow.")

    if 'removeScriptMessageHandler(forName: "tfmaNativeAuth")' not in swift:
        swift = replace_once(
            swift,
            '        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "tfmaNative")\n',
            '        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "tfmaNative")\n        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "tfmaNativeAuth")\n',
            "native auth handler cleanup",
        )

    old_message_guard = '            guard message.name == "tfmaNative" else { return }\n\n'
    if old_message_guard in swift:
        swift = swift.replace(
            old_message_guard,
            '''            if message.name == "tfmaNativeAuth" {\n                TFNativeAuth924.handleBridgeMessage(message.body)\n                return\n            }\n            guard message.name == "tfmaNative" else { return }\n\n''',
            1,
        )
    elif "TFNativeAuth924.handleBridgeMessage" not in swift:
        raise RuntimeError("Could not patch script message routing for native auth.")

    if "func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!)" not in swift:
        anchor = "        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {\n"
        did_finish = '''        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {\n            TFNativeAuth924.maybeEnroll(in: webView)\n        }\n\n'''
        swift = replace_once(swift, anchor, did_finish + anchor, "native auth enrollment hook")

    first_party = '''            if host == allowedHost || host.hasSuffix(".\\(allowedHost)") || url.scheme == "about" {\n                decisionHandler(.allow)\n                return\n            }\n'''
    if "TFNativeAuth924.inspectNavigation(url)" not in swift:
        first_party_new = '''            if host == allowedHost || host.hasSuffix(".\\(allowedHost)") || url.scheme == "about" {\n                TFNativeAuth924.inspectNavigation(url)\n                decisionHandler(.allow)\n                return\n            }\n'''
        swift = replace_once(swift, first_party, first_party_new, "explicit logout detection")

    required = [
        "enum TFNativeAuth924",
        "configuration.websiteDataStore = .default()",
        'name: "tfmaNativeAuth"',
        "TFNativeAuth924.loadInitialPage",
        "TFNativeAuth924.maybeEnroll",
        "tfma924_native_auth_restore",
        "tfma924_native_auth_export",
        "kSecClassGenericPassword",
        "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly",
        "TFNativeAuth924.inspectNavigation(url)",
    ]
    missing = [needle for needle in required if needle not in swift]
    if missing:
        raise RuntimeError(f"Native auth validation failed; missing: {missing}")

    CONTENT_VIEW.write_text(swift, encoding="utf-8")
    print("Prepared native Keychain persistent login v9.24")
    print("Prepared explicit logout/account-switch token revocation")
    print("Prepared persistent WKWebsiteDataStore + WebView session recovery")


if __name__ == "__main__":
    main()
