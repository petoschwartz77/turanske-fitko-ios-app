#!/usr/bin/env python3
"""Upgrade the v9.26 NFC bridge to the v9.27 transport.

The theme/alternate-icon code from v9.26 remains untouched.
NFC now posts to WordPress admin-ajax instead of fetching the Universal Link URL itself.
If JavaScript transport fails, native Swift retries the same AJAX endpoint with cookies copied
from the currently logged-in WKWebView.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "TuranskeFitkoApp" / "ContentView.swift"
APP = ROOT / "TuranskeFitkoApp" / "TuranskeFitkoApp.swift"


def replace_once_regex(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Could not patch {label}; expected one match, got {count}.")
    return updated


def patch_content() -> None:
    swift = CONTENT.read_text(encoding="utf-8")

    replacement = r'''window.TFMANFC926 = {
            version: 927,
            process: async (rawURL) => {
                const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
                const timeout = setTimeout(() => { try { controller?.abort(); } catch (_) {} }, 12000);
                try {
                    const sourceURL = new URL(String(rawURL || ''), location.href);
                    const parts = sourceURL.pathname.split('/').filter(Boolean);
                    const token = parts.length ? String(parts[parts.length - 1] || '') : '';
                    const mode = parts.indexOf('out') >= 0 ? 'out' : 'in';
                    if (!token) throw new Error('NFC token missing');

                    const body = new URLSearchParams({
                        action: 'tfma927_nfc_process',
                        token: token,
                        mode: mode,
                        tfma_v: '9.27'
                    }).toString();

                    const response = await fetch('/wp-admin/admin-ajax.php', {
                        method: 'POST',
                        credentials: 'include',
                        cache: 'no-store',
                        redirect: 'follow',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'Accept': 'application/json',
                            'X-TFMA-Native-NFC': 'ios-9.27'
                        },
                        body,
                        signal: controller ? controller.signal : undefined
                    });
                    const text = await response.text();
                    const payload = cleanJSON(text);
                    if (!payload || !payload.title || !payload.state) {
                        post({event:'nfcResult', ok:false, code:'BAD_JSON', http:response.status, rawURL:String(rawURL || ''), message:'Server nepotvrdil výsledok NFC.'});
                        return;
                    }
                    post({event:'nfcResult', ok:true, http:response.status, rawURL:String(rawURL || ''), payload:payload});
                } catch (error) {
                    const code = error && error.name === 'AbortError' ? 'TIMEOUT' : 'NETWORK';
                    post({event:'nfcResult', ok:false, code:code, rawURL:String(rawURL || ''), message:String(error && error.message || 'NFC request failed')});
                } finally {
                    clearTimeout(timeout);
                }
            }
        };
    })();'''

    pattern = r"window\.TFMANFC926 = \{.*?\n        \};\n    \}\)\(\);"
    swift = replace_once_regex(swift, pattern, replacement, "WKWebView NFC AJAX transport")

    if "tfma927_nfc_process" not in swift or "ios-9.27" not in swift:
        raise RuntimeError("v9.27 JavaScript transport validation failed.")
    CONTENT.write_text(swift, encoding="utf-8")


def patch_app() -> None:
    swift = APP.read_text(encoding="utf-8")

    receive_replacement = r'''    static func receive(_ body: [String: Any]) {
        DispatchQueue.main.async {
            guard (body["event"] as? String) == "nfcResult" else { return }
            if body["ok"] as? Bool == true,
               let payload = body["payload"] as? [String: Any] {
                showPayload(payload)
                return
            }

            let rawURL = body["rawURL"] as? String ?? ""
            if !rawURL.isEmpty {
                nativeCookieFallback(rawURL: rawURL)
                return
            }

            showFinalTransportError(code: body["code"] as? String ?? "UNKNOWN")
        }
    }

    private static func showPayload(_ payload: [String: Any]) {
        let state = (payload["state"] as? String) ?? "info"
        let title = (payload["title"] as? String) ?? "NFC potvrdené"
        let message = (payload["message"] as? String) ?? "Server potvrdil NFC akciu."
        TFMNFCStatusRailV926.shared.showResult(state: state, title: title, message: message)
    }

    private static func showFinalTransportError(code: String) {
        let message: String
        switch code {
        case "TIMEOUT": message = "Server neodpovedal včas. Skús tag priložiť ešte raz."
        case "BAD_JSON": message = "Server vrátil nečitateľné potvrdenie. Skús tag priložiť ešte raz."
        case "NO_SESSION": message = "Prihlásenie appky sa nepodarilo overiť. Otvor appku a skús NFC znova."
        default: message = "Server sa nepodarilo overiť. Skús tag priložiť ešte raz."
        }
        TFMNFCStatusRailV926.shared.showResult(state: "error", title: "NFC bez potvrdenia", message: message)
    }

    private static func nativeCookieFallback(rawURL: String) {
        guard let webView = TFMWebViewRegistryV926.shared.webView,
              let parsed = parseTokenAndMode(rawURL: rawURL) else {
            showFinalTransportError(code: "NETWORK")
            return
        }

        webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { cookies in
            let tfCookies = cookies.filter { cookie in
                let domain = cookie.domain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
                return domain == "turanskefitko.sk" || domain.hasSuffix(".turanskefitko.sk")
            }

            var request = URLRequest(url: URL(string: "https://turanskefitko.sk/wp-admin/admin-ajax.php")!)
            request.httpMethod = "POST"
            request.timeoutInterval = 12
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.setValue("application/x-www-form-urlencoded; charset=UTF-8", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.setValue("ios-native-fallback-9.27", forHTTPHeaderField: "X-TFMA-Native-NFC")
            request.setValue("TFMiOSApp TFMNativeApp TuranskeFitko/9.27", forHTTPHeaderField: "User-Agent")

            if !tfCookies.isEmpty,
               let cookieHeader = HTTPCookie.requestHeaderFields(with: tfCookies)["Cookie"] {
                request.setValue(cookieHeader, forHTTPHeaderField: "Cookie")
            }

            var components = URLComponents()
            components.queryItems = [
                URLQueryItem(name: "action", value: "tfma927_nfc_process"),
                URLQueryItem(name: "token", value: parsed.token),
                URLQueryItem(name: "mode", value: parsed.mode),
                URLQueryItem(name: "tfma_v", value: "9.27"),
            ]
            request.httpBody = components.percentEncodedQuery?.data(using: .utf8)

            URLSession.shared.dataTask(with: request) { data, response, error in
                DispatchQueue.main.async {
                    guard error == nil,
                          let http = response as? HTTPURLResponse,
                          (200...299).contains(http.statusCode),
                          let data,
                          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                          object["state"] != nil,
                          object["title"] != nil else {
                        showFinalTransportError(code: error is URLError && (error as? URLError)?.code == .timedOut ? "TIMEOUT" : "NETWORK")
                        return
                    }
                    showPayload(object)
                }
            }.resume()
        }
    }

    private static func parseTokenAndMode(rawURL: String) -> (token: String, mode: String)? {
        guard let url = URL(string: rawURL) else { return nil }
        let parts = url.path.split(separator: "/").map(String.init)
        guard parts.count == 3 || parts.count == 4 else { return nil }
        guard parts[0] == "tfm-app", parts[1] == "nfc" else { return nil }
        let mode: String
        let token: String
        if parts.count == 4 {
            mode = parts[2] == "out" ? "out" : "in"
            token = parts[3]
        } else {
            mode = "in"
            token = parts[2]
        }
        guard (24...128).contains(token.count) else { return nil }
        return (token, mode)
    }

'''

    pattern = r"    static func receive\(_ body: \[String: Any\]\) \{.*?\n    \}\n\n    private static func validatedNFCURL"
    swift = replace_once_regex(
        swift,
        pattern,
        receive_replacement + "    private static func validatedNFCURL",
        "native NFC result + cookie fallback",
    )

    if "nativeCookieFallback" not in swift or "tfma927_nfc_process" not in swift or "9.27" not in swift:
        raise RuntimeError("v9.27 native fallback validation failed.")
    APP.write_text(swift, encoding="utf-8")


def main() -> None:
    patch_content()
    patch_app()
    print("Prepared v9.27 NFC admin-ajax transport")
    print("Prepared v9.27 native WKWebView-cookie fallback")
    print("Theme-linked Original/Ružová iskra icons remain unchanged from v9.26")


if __name__ == "__main__":
    main()
