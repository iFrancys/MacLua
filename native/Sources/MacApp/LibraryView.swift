import SwiftUI

struct LibraryView: View {
    @Binding var currentFilter: LibraryFilter
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState var searchText = ""
    @UIState var inspectingGame: GameItem? = nil

    var body: some View {
        Group {
            if let game = inspectingGame {
                GameDetailView(game: game) {
                    inspectingGame = nil
                }
            } else {
                mainLibraryContent
            }
        }
    }

    private var mainLibraryContent: some View {
        VStack(spacing: 0) {
            // Barra di ricerca locale
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(appearance.theme.secondaryText)

                TextField("Filtra per nome o AppID...", text: $searchText)
                    .textFieldStyle(.plain)
                    .foregroundStyle(appearance.theme.primaryText)

                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(appearance.theme.secondaryText)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(appearance.theme.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(appearance.theme.cardBorder, lineWidth: 1)
            )
            .padding(.horizontal, CGFloat(appearance.density.padding))
            .padding(.top, 14)
            .padding(.bottom, 8)

            ScrollView {
                if filteredGames.isEmpty {
                    emptyFilterView
                } else {
                    let colWidth = CGFloat(appearance.gridCardWidth)
                    let columns = [GridItem(.adaptive(minimum: colWidth, maximum: colWidth + 50), spacing: 14)]

                    LazyVGrid(columns: columns, spacing: 14) {
                        ForEach(filteredGames) { game in
                            gameGridCard(for: game)
                        }
                    }
                    .padding(CGFloat(appearance.density.padding))
                }
            }
        }
    }

    private var filteredGames: [GameItem] {
        store.games.filter { g in
            let matchesFilter: Bool
            switch currentFilter {
            case .all:
                matchesFilter = true
            case .installed:
                matchesFilter = g.state == .installed
            case .updates:
                matchesFilter = g.state == .updateAvailable
            case .notInstalled:
                matchesFilter = g.state == .notInstalled
            }

            guard matchesFilter else { return false }

            if searchText.isEmpty { return true }
            return g.name.localizedCaseInsensitiveContains(searchText) || String(g.appid).contains(searchText)
        }
    }

    private func gameGridCard(for game: GameItem) -> some View {
        let isDownloading = Downloader.shared.isRunning(appid: game.appid)

        return Button {
            inspectingGame = game
            store.selectedAppId = game.appid
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                ZStack(alignment: .topTrailing) {
                    AsyncArtwork(urls: Art.poster(game.appid), cornerRadius: 8)
                        .aspectRatio(600.0 / 900.0, contentMode: .fill)

                    StatusBadge(state: game.state, isDownloading: isDownloading)
                        .padding(8)
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(game.name)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                        .lineLimit(1)

                    Text("App \(game.appid)")
                        .font(.system(size: 11))
                        .foregroundStyle(appearance.theme.tertiaryText)
                }
                .padding(.horizontal, 4)
                .padding(.bottom, 4)
            }
            .padding(7)
            .background(appearance.theme.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius)))
            .overlay(
                RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius))
                    .stroke(appearance.theme.cardBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button("Mostra dettagli") {
                inspectingGame = game
            }
            Button(game.state == .installed ? "Gioca con Steam" : "Scarica") {
                if game.state == .installed {
                    SteamControl.openInstall(appid: game.appid)
                } else {
                    store.startDownload(appid: game.appid)
                }
            }
            Button("Verifica integrità file") {
                inspectingGame = game
            }
            Button("Pagina Steam") {
                SteamControl.openGamePage(appid: game.appid)
            }
            Divider()
            Button("Rimuovi dalla libreria", role: .destructive) {
                Task {
                    try? await store.removeGame(appid: game.appid)
                }
            }
        }
    }

    private var emptyFilterView: some View {
        VStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 32))
                .foregroundStyle(appearance.theme.tertiaryText)

            Text("Nessun gioco trovato")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(appearance.theme.primaryText)

            Text(searchText.isEmpty
                 ? "Non ci sono giochi che corrispondono al filtro selezionato."
                 : "Nessun risultato per \"\(searchText)\".")
                .font(.system(size: 13))
                .foregroundStyle(appearance.theme.secondaryText)
        }
        .frame(maxWidth: .infinity, minHeight: 250)
    }
}
