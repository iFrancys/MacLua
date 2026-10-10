import SwiftUI

struct AppShellView: View {
    @UIState var selectedTab: AppTab = .home
    @UIState var libraryFilter: LibraryFilter = .all
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    var body: some View {
        ZStack {
            // Sfondo dinamico personalizzato (tema, immagine o GIF animata)
            DynamicBackgroundView()

            HStack(spacing: 0) {
                // Rail di navigazione laterale
                SideRailView(selectedTab: $selectedTab)

                // Area Principale
                VStack(spacing: 0) {
                    HeaderBarView(currentFilter: $libraryFilter, selectedTab: $selectedTab)

                    ZStack {
                        switch selectedTab {
                        case .home:
                            HomeView(selectedTab: $selectedTab)
                        case .library:
                            LibraryView(currentFilter: $libraryFilter)
                        case .collections:
                            CollectionsView()
                        case .plugin:
                            PluginView()
                        case .depots:
                            DepotsView()
                        case .add:
                            AddGameView(selectedTab: $selectedTab)
                        case .downloads:
                            DownloadsView()
                        case .settings:
                            SettingsView()
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }

            // Toast Notifiche Fluttuante
            ToastOverlay(message: store.toastMessage) {
                store.toastMessage = nil
            }
        }
        .dynamicTypeSize(appearance.textScale.dynamicTypeSize)
        .task {
            // Supporto hook verifica MACLUA_TAB
            if let tabStr = ProcessInfo.processInfo.environment["MACLUA_TAB"],
               let tabIdx = Int(tabStr) {
                switch tabIdx {
                case 1: selectedTab = .add
                case 2: selectedTab = .downloads
                case 3: selectedTab = .settings
                default: selectedTab = .home
                }
            }

            MacLuaBridge.live.ensureBridgeRunning()
            await store.reloadLibrary()
        }
    }
}

// MARK: - Helper NSVisualEffectView in SwiftUI

struct VisualEffectBlur: NSViewRepresentable {
    var material: NSVisualEffectView.Material = .headerView
    var blendingMode: NSVisualEffectView.BlendingMode = .withinWindow

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}
