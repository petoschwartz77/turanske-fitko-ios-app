import SwiftUI
import WebKit

struct ContentView: View {
    var body: some View {
        TFMWebView()
            .ignoresSafeArea(.all, edges: .all)
    }
}

struct TFMWebView: UIViewRepresentable {
    private let appURL = URL(string: "https://turanskefitko.sk/?tfm_mobile_app=1&native=ios&tfma_v=4.73")!

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.allowsInlineMediaPlayback = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.customUserAgent = "TFMiOSApp TFMNativeApp TuranskeFitko/1.0"
        webView.scrollView.bounces = true
        webView.load(URLRequest(url: appURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }

            let allowedHost = "turanskefitko.sk"
            if url.host == allowedHost || url.scheme == "about" {
                decisionHandler(.allow)
                return
            }

            if ["tel", "mailto", "sms", "whatsapp"].contains(url.scheme?.lowercased() ?? "") {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }

            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        }
    }
}
