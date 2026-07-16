import SwiftUI
import WebKit
import UIKit
import AudioToolbox

struct ContentView: View {
    var body: some View {
        TFMWebView()
            .ignoresSafeArea(.all, edges: .all)
    }
}

struct TFMWebView: UIViewRepresentable {
    private let appURL = URL(string: "https://turanskefitko.sk/?tfm_mobile_app=1&native=ios&tfma_v=6.28")!

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.allowsInlineMediaPlayback = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = true

        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "tfmaNative")
        contentController.addUserScript(
            WKUserScript(
                source: Self.leoProteinAnimationScript,
                injectionTime: .atDocumentEnd,
                forMainFrameOnly: true
            )
        )
        configuration.userContentController = contentController

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.customUserAgent = "TFMiOSApp TFMNativeApp TuranskeFitko/6.28"
        webView.scrollView.bounces = true
        webView.load(URLRequest(url: appURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30))
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) {
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "tfmaNative")
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "tfmaNative" else { return }

            let event: String
            if let body = message.body as? String {
                event = body
            } else if let body = message.body as? [String: Any], let value = body["event"] as? String {
                event = value
            } else {
                return
            }

            DispatchQueue.main.async {
                switch event {
                case "proteinTap":
                    let generator = UIImpactFeedbackGenerator(style: .light)
                    generator.prepare()
                    generator.impactOccurred(intensity: 0.65)
                case "proteinPop":
                    let generator = UIImpactFeedbackGenerator(style: .medium)
                    generator.prepare()
                    generator.impactOccurred(intensity: 0.78)
                case "proteinShake":
                    let generator = UIImpactFeedbackGenerator(style: .rigid)
                    generator.prepare()
                    generator.impactOccurred(intensity: 0.82)
                case "proteinDrink":
                    let generator = UIImpactFeedbackGenerator(style: .soft)
                    generator.prepare()
                    generator.impactOccurred(intensity: 0.58)
                case "proteinPower":
                    let generator = UIImpactFeedbackGenerator(style: .heavy)
                    generator.prepare()
                    generator.impactOccurred(intensity: 0.9)
                case "proteinReward":
                    let generator = UINotificationFeedbackGenerator()
                    generator.prepare()
                    generator.notificationOccurred(.success)
                    AudioServicesPlaySystemSound(1104)
                default:
                    break
                }
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }

            let allowedHost = "turanskefitko.sk"
            let host = url.host?.lowercased() ?? ""
            if host == allowedHost || host.hasSuffix(".\(allowedHost)") || url.scheme == "about" {
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

    private static let leoProteinAnimationScript = #"""
    (() => {
        if (window.TFMALeoFX && window.TFMALeoFX.version >= 1) return;

        const native = (event) => {
            try {
                window.webkit?.messageHandlers?.tfmaNative?.postMessage({ event });
            } catch (_) {}
        };

        const normalize = (value) => String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();

        const style = document.createElement("style");
        style.id = "tfma-leo-protein-fx-style";
        style.textContent = `
            #tfma-lpf-root {
                --lpf-lime: #c8ff00;
                --lpf-lime-soft: rgba(200, 255, 0, .24);
                --lpf-cyan: #61e9ff;
                --lpf-purple: #dd83ff;
                position: fixed;
                inset: 0;
                z-index: 2147483000;
                display: grid;
                place-items: center;
                overflow: hidden;
                pointer-events: none;
                opacity: 0;
                visibility: hidden;
                transition: opacity .18s ease, visibility .18s ease;
                font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            #tfma-lpf-root.is-visible {
                opacity: 1;
                visibility: visible;
            }
            #tfma-lpf-root::before {
                content: "";
                position: absolute;
                inset: 0;
                background:
                    radial-gradient(circle at 50% 43%, rgba(200,255,0,.18), transparent 28%),
                    linear-gradient(180deg, rgba(0,0,0,.30), rgba(0,0,0,.84));
                backdrop-filter: blur(8px) saturate(1.1);
                -webkit-backdrop-filter: blur(8px) saturate(1.1);
            }
            .tfma-lpf-halo {
                position: absolute;
                width: min(82vw, 580px);
                aspect-ratio: 1;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(200,255,0,.24) 0, rgba(200,255,0,.08) 38%, transparent 69%);
                filter: blur(10px);
                transform: scale(.72);
                opacity: .25;
                transition: transform .5s cubic-bezier(.2,.8,.2,1), opacity .35s ease;
            }
            #tfma-lpf-root[data-stage="power"] .tfma-lpf-halo,
            #tfma-lpf-root[data-stage="reward"] .tfma-lpf-halo {
                transform: scale(1.18);
                opacity: .95;
            }
            .tfma-lpf-particles {
                position: absolute;
                inset: 0;
            }
            .tfma-lpf-particle {
                position: absolute;
                left: var(--x);
                top: var(--y);
                width: var(--s);
                height: var(--s);
                border-radius: 50%;
                background: var(--lpf-lime);
                box-shadow: 0 0 12px var(--lpf-lime), 0 0 25px rgba(200,255,0,.5);
                opacity: 0;
            }
            #tfma-lpf-root[data-stage="shake"] .tfma-lpf-particle,
            #tfma-lpf-root[data-stage="drink"] .tfma-lpf-particle,
            #tfma-lpf-root[data-stage="power"] .tfma-lpf-particle,
            #tfma-lpf-root[data-stage="reward"] .tfma-lpf-particle {
                animation: tfma-lpf-float var(--d) ease-out var(--delay) forwards;
            }
            .tfma-lpf-stage {
                position: relative;
                z-index: 2;
                width: min(94vw, 680px);
                height: min(78vh, 760px);
                display: grid;
                place-items: center;
            }
            .tfma-lpf-character-wrap {
                position: relative;
                display: grid;
                place-items: center;
                transform-origin: 50% 82%;
                will-change: transform, filter;
            }
            .tfma-lpf-character {
                display: block;
                max-width: min(76vw, 470px);
                max-height: 57vh;
                object-fit: contain;
                border-radius: 30px;
                filter: drop-shadow(0 28px 25px rgba(0,0,0,.58));
                transform-origin: 50% 78%;
                will-change: transform, filter;
                user-select: none;
                -webkit-user-drag: none;
            }
            .tfma-lpf-fallback {
                font-size: min(46vw, 270px);
                line-height: 1;
                filter: drop-shadow(0 24px 22px rgba(0,0,0,.55));
                transform-origin: 50% 78%;
            }
            .tfma-lpf-shaker {
                position: absolute;
                left: 50%;
                top: 55%;
                width: clamp(66px, 17vw, 105px);
                height: clamp(122px, 30vw, 188px);
                border-radius: 18px 18px 25px 25px;
                background:
                    linear-gradient(90deg, rgba(255,255,255,.12), transparent 28%, rgba(255,255,255,.08) 70%, transparent),
                    linear-gradient(180deg, #242424, #080808 72%, #1b1b1b);
                border: 2px solid rgba(255,255,255,.16);
                box-shadow: 0 22px 35px rgba(0,0,0,.55), 0 0 0 1px rgba(200,255,0,.12) inset;
                transform: translate(-50%, 78vh) rotate(-10deg) scale(.72);
                opacity: 0;
                transform-origin: 50% 78%;
                will-change: transform, opacity;
            }
            .tfma-lpf-shaker::before {
                content: "";
                position: absolute;
                left: -5%;
                right: -5%;
                top: -10%;
                height: 18%;
                border-radius: 12px 12px 7px 7px;
                background: linear-gradient(180deg, #d9ff2e, #91bd00);
                border: 2px solid rgba(0,0,0,.45);
                box-shadow: 0 5px 12px rgba(0,0,0,.35);
            }
            .tfma-lpf-shaker strong,
            .tfma-lpf-shaker small {
                position: absolute;
                left: 50%;
                transform: translateX(-50%);
                text-align: center;
                color: var(--lpf-lime);
                text-shadow: 0 0 12px rgba(200,255,0,.4);
            }
            .tfma-lpf-shaker strong {
                top: 29%;
                font-size: clamp(27px, 7vw, 42px);
                letter-spacing: -3px;
                font-weight: 950;
            }
            .tfma-lpf-shaker small {
                top: 56%;
                font-size: clamp(7px, 2.2vw, 12px);
                line-height: 1.05;
                font-weight: 900;
                letter-spacing: .8px;
            }
            .tfma-lpf-caption {
                position: absolute;
                top: max(6vh, env(safe-area-inset-top));
                left: 50%;
                transform: translate(-50%, -16px);
                width: min(88vw, 520px);
                padding: 12px 18px;
                border: 1px solid rgba(200,255,0,.28);
                border-radius: 999px;
                background: rgba(6,8,5,.74);
                box-shadow: 0 13px 40px rgba(0,0,0,.34), 0 0 25px rgba(200,255,0,.06) inset;
                color: white;
                text-align: center;
                font-size: clamp(12px, 3.3vw, 17px);
                font-weight: 800;
                letter-spacing: .2px;
                opacity: 0;
                transition: opacity .2s ease, transform .3s ease;
            }
            #tfma-lpf-root.is-visible .tfma-lpf-caption {
                opacity: 1;
                transform: translate(-50%, 0);
            }
            .tfma-lpf-caption b { color: var(--lpf-lime); }
            .tfma-lpf-rewards {
                position: absolute;
                left: 50%;
                bottom: max(5vh, calc(env(safe-area-inset-bottom) + 8px));
                transform: translate(-50%, 38px) scale(.92);
                width: min(88vw, 440px);
                padding: 14px;
                border-radius: 26px;
                background: linear-gradient(180deg, rgba(18,22,15,.96), rgba(5,6,5,.97));
                border: 1px solid rgba(200,255,0,.52);
                box-shadow: 0 24px 70px rgba(0,0,0,.62), 0 0 34px rgba(200,255,0,.16), 0 0 0 1px rgba(255,255,255,.04) inset;
                opacity: 0;
                transition: opacity .22s ease, transform .5s cubic-bezier(.18,.89,.32,1.28);
            }
            #tfma-lpf-root[data-stage="reward"] .tfma-lpf-rewards {
                opacity: 1;
                transform: translate(-50%, 0) scale(1);
            }
            .tfma-lpf-rewards h3 {
                margin: 2px 0 12px;
                text-align: center;
                color: var(--lpf-lime);
                font-size: clamp(17px, 4.7vw, 24px);
                font-weight: 950;
                letter-spacing: .4px;
            }
            .tfma-lpf-reward-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 9px;
            }
            .tfma-lpf-reward {
                min-width: 0;
                padding: 12px 7px 10px;
                border-radius: 17px;
                background: rgba(255,255,255,.045);
                border: 1px solid rgba(255,255,255,.09);
                text-align: center;
            }
            .tfma-lpf-reward strong {
                display: block;
                color: var(--reward-color);
                font-size: clamp(20px, 6vw, 31px);
                line-height: 1;
                font-weight: 950;
                text-shadow: 0 0 18px color-mix(in srgb, var(--reward-color), transparent 55%);
            }
            .tfma-lpf-reward span {
                display: block;
                margin-top: 6px;
                color: rgba(255,255,255,.82);
                font-size: clamp(9px, 2.6vw, 12px);
                font-weight: 850;
                letter-spacing: .35px;
                text-transform: uppercase;
                white-space: nowrap;
            }
            #tfma-lpf-root[data-stage="look"] .tfma-lpf-character-wrap {
                animation: tfma-lpf-look .42s cubic-bezier(.2,.85,.25,1) both;
            }
            #tfma-lpf-root[data-stage="anticipate"] .tfma-lpf-character-wrap {
                animation: tfma-lpf-anticipate .42s ease-in-out both;
            }
            #tfma-lpf-root[data-stage="shaker"] .tfma-lpf-shaker {
                opacity: 1;
                transform: translate(-50%, -6%) rotate(-8deg) scale(1);
                transition: transform .46s cubic-bezier(.2,1.25,.3,1), opacity .12s ease;
            }
            #tfma-lpf-root[data-stage="shake"] .tfma-lpf-shaker {
                opacity: 1;
                animation: tfma-lpf-shake .58s ease-in-out both;
            }
            #tfma-lpf-root[data-stage="shake"] .tfma-lpf-character-wrap {
                animation: tfma-lpf-body-shake .58s ease-in-out both;
            }
            #tfma-lpf-root[data-stage="drink"] .tfma-lpf-character-wrap {
                animation: tfma-lpf-drink-body .68s cubic-bezier(.2,.75,.25,1) both;
            }
            #tfma-lpf-root[data-stage="drink"] .tfma-lpf-shaker {
                opacity: 1;
                animation: tfma-lpf-drink-shaker .68s cubic-bezier(.2,.75,.25,1) both;
            }
            #tfma-lpf-root[data-stage="power"] .tfma-lpf-character-wrap {
                animation: tfma-lpf-power .52s cubic-bezier(.18,.89,.32,1.28) both;
            }
            #tfma-lpf-root[data-stage="power"] .tfma-lpf-shaker,
            #tfma-lpf-root[data-stage="reward"] .tfma-lpf-shaker {
                opacity: 0;
                transform: translate(65vw, 35vh) rotate(38deg) scale(.65);
                transition: transform .45s ease-in, opacity .25s ease;
            }
            #tfma-lpf-root[data-stage="reward"] .tfma-lpf-character-wrap {
                transform: translateY(-7vh) scale(1.03);
                filter: drop-shadow(0 0 25px rgba(200,255,0,.28));
                transition: transform .45s ease, filter .45s ease;
            }
            @keyframes tfma-lpf-look {
                0% { transform: translateY(12px) scale(.94); opacity: .4; }
                55% { transform: translateY(-7px) scale(1.035); opacity: 1; }
                100% { transform: translateY(0) scale(1); opacity: 1; }
            }
            @keyframes tfma-lpf-anticipate {
                0%,100% { transform: rotate(0) scale(1); }
                38% { transform: rotate(-2.2deg) scale(1.035); }
                70% { transform: rotate(1.6deg) scale(1.02); }
            }
            @keyframes tfma-lpf-shake {
                0% { transform: translate(-50%,-6%) rotate(-8deg); }
                17% { transform: translate(-60%,-18%) rotate(-23deg); }
                34% { transform: translate(-40%,-4%) rotate(17deg); }
                51% { transform: translate(-59%,-17%) rotate(-20deg); }
                68% { transform: translate(-42%,-2%) rotate(15deg); }
                84% { transform: translate(-54%,-10%) rotate(-12deg); }
                100% { transform: translate(-50%,-6%) rotate(-7deg); }
            }
            @keyframes tfma-lpf-body-shake {
                0%,100% { transform: rotate(0) translateX(0); }
                25% { transform: rotate(-1.8deg) translateX(-4px); }
                50% { transform: rotate(1.7deg) translateX(4px); }
                75% { transform: rotate(-1.2deg) translateX(-2px); }
            }
            @keyframes tfma-lpf-drink-body {
                0% { transform: rotate(0) translateY(0); }
                42% { transform: rotate(-4deg) translateY(8px) scale(1.015); }
                78% { transform: rotate(-5deg) translateY(8px) scale(1.018); }
                100% { transform: rotate(-1deg) translateY(1px); }
            }
            @keyframes tfma-lpf-drink-shaker {
                0% { transform: translate(-50%,-6%) rotate(-7deg); }
                38% { transform: translate(-18%,-50%) rotate(-66deg) scale(.96); }
                78% { transform: translate(-18%,-50%) rotate(-70deg) scale(.96); }
                100% { transform: translate(-47%,-9%) rotate(-11deg); }
            }
            @keyframes tfma-lpf-power {
                0% { transform: scale(.96) translateY(7px); filter: brightness(1); }
                45% { transform: scale(1.11) translateY(-13px); filter: brightness(1.22) saturate(1.18); }
                72% { transform: scale(1.035) translateY(-3px); filter: brightness(1.08); }
                100% { transform: scale(1.06) translateY(-6px); filter: brightness(1.12); }
            }
            @keyframes tfma-lpf-float {
                0% { opacity: 0; transform: translate(0,0) scale(.4); }
                18% { opacity: 1; }
                100% { opacity: 0; transform: translate(var(--dx), var(--dy)) scale(1.25); }
            }
            @media (prefers-reduced-motion: reduce) {
                #tfma-lpf-root *, #tfma-lpf-root *::before, #tfma-lpf-root *::after {
                    animation-duration: .01ms !important;
                    animation-iteration-count: 1 !important;
                    transition-duration: .01ms !important;
                }
            }
        `;
        document.head.appendChild(style);

        const root = document.createElement("div");
        root.id = "tfma-lpf-root";
        root.setAttribute("aria-hidden", "true");
        root.innerHTML = `
            <div class="tfma-lpf-halo"></div>
            <div class="tfma-lpf-particles"></div>
            <div class="tfma-lpf-stage">
                <div class="tfma-lpf-caption">🥤 <b>PROTEÍNOVÁ ODMENA</b> · sila rastie</div>
                <div class="tfma-lpf-character-wrap"></div>
                <div class="tfma-lpf-shaker"><strong>TF</strong><small>TURANSKÉ<br>FITKO</small></div>
                <div class="tfma-lpf-rewards">
                    <h3>SKVELÁ VOĽBA!</h3>
                    <div class="tfma-lpf-reward-grid">
                        <div class="tfma-lpf-reward" style="--reward-color: var(--lpf-lime)"><strong>+15</strong><span>Sýtosť</span></div>
                        <div class="tfma-lpf-reward" style="--reward-color: var(--lpf-cyan)"><strong>+5</strong><span>Energia</span></div>
                        <div class="tfma-lpf-reward" style="--reward-color: var(--lpf-purple)"><strong>+3</strong><span>XP</span></div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(root);

        const particleHost = root.querySelector(".tfma-lpf-particles");
        for (let index = 0; index < 28; index += 1) {
            const particle = document.createElement("i");
            particle.className = "tfma-lpf-particle";
            const angle = Math.random() * Math.PI * 2;
            const distance = 90 + Math.random() * 230;
            particle.style.setProperty("--x", `${42 + Math.random() * 16}%`);
            particle.style.setProperty("--y", `${38 + Math.random() * 23}%`);
            particle.style.setProperty("--s", `${2 + Math.random() * 5}px`);
            particle.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
            particle.style.setProperty("--dy", `${Math.sin(angle) * distance - 45}px`);
            particle.style.setProperty("--d", `${.72 + Math.random() * .8}s`);
            particle.style.setProperty("--delay", `${Math.random() * .24}s`);
            particleHost.appendChild(particle);
        }

        const visible = (element) => {
            if (!element) return false;
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return rect.width > 80 && rect.height > 80 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > .05;
        };

        const findCharacterSource = () => {
            const selectors = [
                "[data-leo-character] img",
                "[data-character='leo'] img",
                "[data-character='lea'] img",
                ".tfma-leo-character img",
                ".tfma-leo-scene img",
                ".leo-life img",
                "[class*='leo-life'] img",
                "img[alt*='Leo' i]",
                "img[alt*='Lea' i]",
                "img[src*='leo' i]",
                "img[src*='lea' i]"
            ];
            for (const selector of selectors) {
                const candidates = Array.from(document.querySelectorAll(selector));
                const candidate = candidates.find(visible);
                if (candidate?.currentSrc || candidate?.src) return candidate.currentSrc || candidate.src;
            }

            const backgroundCandidates = Array.from(document.querySelectorAll("[class*='leo'], [id*='leo'], [class*='lea'], [id*='lea']")).slice(0, 80);
            for (const candidate of backgroundCandidates) {
                if (!visible(candidate)) continue;
                const background = getComputedStyle(candidate).backgroundImage || "";
                const match = background.match(/url\(["']?(.*?)["']?\)/i);
                if (match?.[1]) return match[1];
            }
            return "";
        };

        const characterWrap = root.querySelector(".tfma-lpf-character-wrap");
        const setCharacter = () => {
            characterWrap.replaceChildren();
            const source = findCharacterSource();
            if (source) {
                const image = new Image();
                image.className = "tfma-lpf-character";
                image.alt = "Leo Life";
                image.decoding = "async";
                image.src = source;
                characterWrap.appendChild(image);
            } else {
                const fallback = document.createElement("div");
                fallback.className = "tfma-lpf-fallback";
                fallback.textContent = "🦁";
                characterWrap.appendChild(fallback);
            }
        };

        const tone = (frequency, start, duration, gain = .025) => {
            try {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (!AudioContext) return;
                window.__tfmaLeoAudio = window.__tfmaLeoAudio || new AudioContext();
                const context = window.__tfmaLeoAudio;
                const oscillator = context.createOscillator();
                const volume = context.createGain();
                oscillator.type = "sine";
                oscillator.frequency.setValueAtTime(frequency, context.currentTime + start);
                volume.gain.setValueAtTime(.0001, context.currentTime + start);
                volume.gain.exponentialRampToValueAtTime(gain, context.currentTime + start + .02);
                volume.gain.exponentialRampToValueAtTime(.0001, context.currentTime + start + duration);
                oscillator.connect(volume);
                volume.connect(context.destination);
                oscillator.start(context.currentTime + start);
                oscillator.stop(context.currentTime + start + duration + .03);
            } catch (_) {}
        };

        const rewardSound = () => {
            tone(523.25, 0, .13, .022);
            tone(659.25, .10, .16, .024);
            tone(783.99, .22, .23, .026);
        };

        let running = false;
        let timers = [];
        const schedule = (callback, delay) => {
            const timer = window.setTimeout(callback, delay);
            timers.push(timer);
        };
        const clearTimers = () => {
            timers.forEach(window.clearTimeout);
            timers = [];
        };
        const stage = (name) => root.dataset.stage = name;

        const playProtein = (options = {}) => {
            if (running) return false;
            running = true;
            clearTimers();
            setCharacter();
            root.classList.add("is-visible");
            stage("look");
            native("proteinTap");

            schedule(() => stage("anticipate"), 220);
            schedule(() => {
                stage("shaker");
                native("proteinPop");
            }, 500);
            schedule(() => {
                stage("shake");
                native("proteinShake");
            }, 820);
            schedule(() => native("proteinShake"), 1060);
            schedule(() => {
                stage("drink");
                native("proteinDrink");
            }, 1340);
            schedule(() => {
                stage("power");
                native("proteinPower");
            }, 2020);
            schedule(() => {
                stage("reward");
                native("proteinReward");
                rewardSound();
                try {
                    document.dispatchEvent(new CustomEvent("tfma:leo-protein-animation-reward", { detail: options }));
                } catch (_) {}
            }, 2320);
            schedule(() => {
                root.classList.remove("is-visible");
                stage("idle");
                running = false;
            }, 3500);
            return true;
        };

        const isProteinAction = (button) => {
            if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") return false;
            const action = normalize([
                button.dataset?.action,
                button.dataset?.leoAction,
                button.dataset?.tfmaAction,
                button.id,
                button.className,
                button.getAttribute("name"),
                button.getAttribute("value")
            ].join(" "));
            if (action.includes("feed_protein") || action.includes("protein_feed") || action.includes("leo_protein")) return true;

            const text = normalize(button.textContent);
            const proteinText = text.includes("dat protein") || text === "protein" || text === "proteinovy napoj" || text.includes("protein");
            if (!proteinText) return false;

            return Boolean(button.closest("[data-leo-life], #leo-life, .leo-life, [class*='leo-life'], [id*='leo-life'], [data-section*='leo']"));
        };

        document.addEventListener("click", (event) => {
            const button = event.target?.closest?.("button, a, [role='button'], [data-action]");
            if (!isProteinAction(button)) return;
            window.setTimeout(() => playProtein({ source: "button", action: "feed_protein" }), 35);
        }, true);

        document.addEventListener("tfma:leo-action-success", (event) => {
            const action = normalize(event?.detail?.action);
            if (action === "feed_protein" || action === "protein") {
                playProtein({ source: "action-success", ...(event.detail || {}) });
            }
        });

        window.TFMALeoFX = Object.freeze({
            version: 1,
            playProtein,
            isRunning: () => running
        });
        document.documentElement.classList.add("tfma-native-leo-fx-ready");
        document.dispatchEvent(new CustomEvent("tfma:native-leo-fx-ready"));
    })();
    """#
}
