import SwiftUI
import Foundation

@main
struct TuranskeFitkoApp: App {
    @UIApplicationDelegateAdaptor(TFMAppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
                .onAppear {
                    Task { @MainActor in
                        ThemeIconSynchronizer.shared.start()
                    }
                }
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    guard let url = activity.webpageURL else { return }
                    _ = UniversalLinkRouter.handle(url)
                }
                .onOpenURL { url in
                    _ = UniversalLinkRouter.handle(url)
                }
        }
    }
}
