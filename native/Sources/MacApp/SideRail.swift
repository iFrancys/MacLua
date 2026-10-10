import SwiftUI

enum AppTab: String, CaseIterable, Identifiable {
    case home = "home"
    case library = "library"
    case collections = "collections"
    case plugin = "plugin"
    case depots = "depots"
    case add = "add"
    case downloads = "downloads"
    case settings = "settings"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .home: return "Home"
        case .library: return "Libreria"
        case .collections: return "Collezioni"
        case .plugin: return "Plugin Steam"
        case .depots: return "Depot & Build"
        case .add: return "Aggiungi"
        case .downloads: return "Download"
        case .settings: return "Impostazioni"
        }
    }

    var icon: String {
        switch self {
        case .home: return "house.fill"
        case .library: return "square.grid.2x2.fill"
        case .collections: return "square.stack.3d.up.fill"
        case .plugin: return "puzzlepiece.extension.fill"
        case .depots: return "shippingbox.fill"
        case .add: return "plus.circle.fill"
        case .downloads: return "arrow.down.circle.fill"
        case .settings: return "gearshape.fill"
        }
    }
}

struct SideRailView: View {
    @Binding var selectedTab: AppTab
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    var body: some View {
        VStack(spacing: 0) {
            // Header rail con pulsante collassa/espandi
            HStack {
                if appearance.isSidebarExpanded {
                    Text("MacLua")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                }

                Button {
                    if !appearance.reduceMotion {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                            appearance.isSidebarExpanded.toggle()
                        }
                    } else {
                        appearance.isSidebarExpanded.toggle()
                    }
                } label: {
                    Image(systemName: appearance.isSidebarExpanded ? "chevron.left" : "chevron.right")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(appearance.theme.secondaryText)
                        .frame(width: 28, height: 28)
                        .background(Color.white.opacity(0.05))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .help(appearance.isSidebarExpanded ? "Comprimi barra" : "Espandi barra")
            }
            .padding(.horizontal, appearance.isSidebarExpanded ? 16 : 10)
            .padding(.top, 14)
            .padding(.bottom, 20)

            // Voci di navigazione
            VStack(spacing: 6) {
                railButton(for: .home)
                railButton(for: .library, badge: store.games.isEmpty ? nil : "\(store.games.count)")
                railButton(for: .collections)
                railButton(for: .plugin)
                railButton(for: .depots)
                railButton(for: .add)
                railButton(for: .downloads, badge: Downloader.shared.isAnyRunning ? "●" : nil)
            }
            .padding(.horizontal, appearance.isSidebarExpanded ? 12 : 8)

            Spacer()

            // Licenze status badge in basso
            if appearance.isSidebarExpanded {
                HStack(spacing: 8) {
                    Circle()
                        .fill(store.areLicensesHealthy ? Color.green : Color.orange)
                        .frame(width: 8, height: 8)

                    Text(store.areLicensesHealthy ? "Licenze OK" : "Licenze da riparare")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(store.areLicensesHealthy ? appearance.theme.secondaryText : Color.orange)

                    Spacer()
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(store.areLicensesHealthy ? Color.clear : Color.orange.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .padding(.horizontal, 12)
                .padding(.bottom, 6)
            }

            // Impostazioni in fondo
            VStack(spacing: 6) {
                railButton(for: .settings)
            }
            .padding(.horizontal, appearance.isSidebarExpanded ? 12 : 8)
            .padding(.bottom, 16)
        }
        .frame(width: appearance.isSidebarExpanded ? 210 : 64)
        .background(appearance.theme.cardBg.opacity(0.7))
        .overlay(
            Rectangle()
                .fill(appearance.theme.cardBorder)
                .frame(width: 1),
            alignment: .trailing
        )
    }

    private func railButton(for tab: AppTab, badge: String? = nil) -> some View {
        let isSelected = selectedTab == tab

        return Button {
            selectedTab = tab
        } label: {
            HStack(spacing: 12) {
                Image(systemName: tab.icon)
                    .font(.system(size: 15, weight: isSelected ? .bold : .medium))
                    .foregroundStyle(isSelected ? appearance.accentColor : appearance.theme.secondaryText)
                    .frame(width: 24, height: 24)

                if appearance.isSidebarExpanded {
                    Text(tab.label)
                        .font(.system(size: 13, weight: isSelected ? .semibold : .regular))
                        .foregroundStyle(isSelected ? appearance.theme.primaryText : appearance.theme.secondaryText)
                        .lineLimit(1)
                        .truncationMode(.tail)

                    Spacer()

                    if let badge {
                        Text(badge)
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(isSelected ? Color.white : appearance.theme.secondaryText)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(isSelected ? appearance.accentColor : Color.white.opacity(0.12))
                            .clipShape(Capsule())
                            .fixedSize()
                    }
                }
            }
            .padding(.horizontal, appearance.isSidebarExpanded ? 12 : 10)
            .padding(.vertical, 9)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected ? appearance.accentColor.opacity(0.15) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isSelected ? appearance.accentColor.opacity(0.4) : Color.clear, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(tab.label)
    }
}
