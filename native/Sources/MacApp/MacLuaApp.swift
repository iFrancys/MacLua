import SwiftUI

struct MacLuaApp: App {
    var body: some Scene {
        WindowGroup {
            AppShellView()
                .environment(AppStore.shared)
                .environment(AppearanceSettings.shared)
                .frame(minWidth: 980, minHeight: 640)
        }
        .windowStyle(.hiddenTitleBar)
        .windowToolbarStyle(.unifiedCompact)
    }
}
