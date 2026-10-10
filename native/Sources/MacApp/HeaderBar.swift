import SwiftUI

enum LibraryFilter: String, CaseIterable, Identifiable {
    case all = "all"
    case installed = "installed"
    case updates = "updates"
    case notInstalled = "notInstalled"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all: return "Tutti i giochi"
        case .installed: return "Installati"
        case .updates: return "Aggiornamenti"
        case .notInstalled: return "Da scaricare"
        }
    }
}

struct HeaderBarView: View {
    @Binding var currentFilter: LibraryFilter
    @Binding var selectedTab: AppTab
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            // Saluto e stato sintetico
            VStack(alignment: .leading, spacing: 3) {
                Text(tabTitle)
                    .font(.system(size: 19, weight: .bold))
                    .foregroundStyle(appearance.theme.primaryText)

                HStack(spacing: 8) {
                    Text("\(store.games.count) giochi gestiti")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(appearance.theme.secondaryText)

                    Text("·")
                        .foregroundStyle(appearance.theme.tertiaryText)

                    if store.areLicensesHealthy {
                        HStack(spacing: 4) {
                            Circle().fill(Color.green).frame(width: 6, height: 6)
                            Text("Licenze sincronizzate")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(Color.green.opacity(0.9))
                        }
                    } else {
                        HStack(spacing: 4) {
                            Circle().fill(Color.orange).frame(width: 6, height: 6)
                            Text("Licenze non allineate")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(Color.orange)
                        }
                    }
                }
            }

            Spacer()

            // Filtri pills (visibili in Home e Libreria)
            if selectedTab == .home || selectedTab == .library {
                HStack(spacing: 4) {
                    ForEach(LibraryFilter.allCases) { filter in
                        let isSelected = currentFilter == filter
                        Button {
                            currentFilter = filter
                        } label: {
                            Text(filter.label)
                                .font(.system(size: 12, weight: isSelected ? .semibold : .medium))
                                .foregroundStyle(isSelected ? appearance.theme.primaryText : appearance.theme.secondaryText)
                                .padding(.horizontal, 11)
                                .padding(.vertical, 6)
                                .background(
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(isSelected ? appearance.accentColor.opacity(0.2) : Color.clear)
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(isSelected ? appearance.accentColor.opacity(0.5) : Color.white.opacity(0.06), lineWidth: 1)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(3)
                .background(Color.black.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }

            // Pulsanti di azione rapida
            HStack(spacing: 8) {
                Button {
                    Task {
                        await store.reloadLibrary()
                    }
                } label: {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(appearance.theme.secondaryText)
                        .frame(width: 30, height: 30)
                        .background(Color.white.opacity(0.06))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .help("Ricarica libreria")

                SteamButtonView(
                    title: "Aggiungi",
                    icon: "plus",
                    variant: .accent
                ) {
                    selectedTab = .add
                }
            }
        }
        .padding(.horizontal, CGFloat(appearance.density.padding))
        .padding(.vertical, 12)
        .background(appearance.theme.secondaryBg.opacity(0.4))
        .overlay(
            Rectangle()
                .fill(appearance.theme.cardBorder)
                .frame(height: 1),
            alignment: .bottom
        )
    }

    private var tabTitle: String {
        switch selectedTab {
        case .home: return "Panoramica"
        case .library: return "La tua Libreria"
        case .collections: return "Collezioni Community"
        case .plugin: return "Integrazione Steam"
        case .depots: return "Ispettore Depot"
        case .add: return "Aggiungi un Gioco"
        case .downloads: return "Download e Aggiornamenti"
        case .settings: return "Impostazioni"
        }
    }
}
