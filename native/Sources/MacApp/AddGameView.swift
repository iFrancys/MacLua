import SwiftUI

struct AddGameView: View {
    @Binding var selectedTab: AppTab
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState var query = ""
    @UIState var hits: [SearchHit] = []
    @UIState var isSearching = false
    @UIState var addingAppId: Int? = nil
    @UIState var errorMessage: String? = nil
    @UIState var successMessage: String? = nil

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Avviso se la chiave API manca
                if !store.hasApiKey {
                    SteamCard {
                        HStack(spacing: 12) {
                            Image(systemName: "key.fill")
                                .font(.system(size: 20))
                                .foregroundStyle(Color.orange)

                            VStack(alignment: .leading, spacing: 3) {
                                Text("Chiave API sorgente non configurata")
                                    .font(.system(size: 14, weight: .bold))
                                    .foregroundStyle(appearance.theme.primaryText)
                                Text("Per scaricare automaticamente i file .lua e i manifest è necessario inserire la chiave API nelle Impostazioni.")
                                    .font(.system(size: 12))
                                    .foregroundStyle(appearance.theme.secondaryText)
                            }

                            Spacer()

                            SteamButtonView(title: "Configura ora", icon: "gearshape", variant: .accent) {
                                selectedTab = .settings
                            }
                        }
                    }
                }

                // Barra di ricerca principale
                SteamCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Cerca nel catalogo Steam")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)

                        HStack(spacing: 10) {
                            HStack {
                                Image(systemName: "magnifyingglass")
                                    .foregroundStyle(appearance.theme.secondaryText)

                                TextField("Es: Stray, Hollow Knight, 1332010...", text: $query)
                                    .textFieldStyle(.plain)
                                    .foregroundStyle(appearance.theme.primaryText)
                                    .onSubmit {
                                        performSearch()
                                    }

                                if !query.isEmpty {
                                    Button {
                                        query = ""
                                    } label: {
                                        Image(systemName: "xmark.circle.fill")
                                            .foregroundStyle(appearance.theme.secondaryText)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(Color.black.opacity(0.2))
                            .clipShape(RoundedRectangle(cornerRadius: 8))

                            SteamButtonView(
                                title: "Cerca",
                                icon: "magnifyingglass",
                                variant: .accent,
                                isLoading: isSearching
                            ) {
                                performSearch()
                            }
                        }

                        if appearance.restartSteamOnAdd {
                            HStack(spacing: 6) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(appearance.accentColor)
                                    .font(.system(size: 11))
                                Text("Steam verrà riavviato automaticamente dopo l'aggiunta per registrare la nuova licenza.")
                                    .font(.system(size: 11))
                                    .foregroundStyle(appearance.theme.secondaryText)
                            }
                        }
                    }
                }

                if let err = errorMessage {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.red)
                        Text(err)
                            .font(.system(size: 12))
                            .foregroundStyle(.red)
                    }
                    .padding(.horizontal, 8)
                }

                if let succ = successMessage {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                        Text(succ)
                            .font(.system(size: 12))
                            .foregroundStyle(.green)
                    }
                    .padding(.horizontal, 8)
                }

                // Risultati di ricerca
                if !hits.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Risultati trovati (\(hits.count))")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)

                        ForEach(hits) { hit in
                            searchHitRow(for: hit)
                        }
                    }
                }
            }
            .padding(CGFloat(appearance.density.padding))
        }
    }

    private func searchHitRow(for hit: SearchHit) -> some View {
        let isAlreadyAdded = store.games.contains { $0.appid == hit.appid }
        let isAddingThis = addingAppId == hit.appid

        return SteamCard(padding: 10) {
            HStack(spacing: 14) {
                AsyncArtwork(urls: Art.tile(hit.appid), cornerRadius: 6)
                    .frame(width: 120, height: 56)

                VStack(alignment: .leading, spacing: 3) {
                    Text(hit.name)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                        .lineLimit(1)

                    Text("Steam AppID: \(hit.appid)")
                        .font(.system(size: 12))
                        .foregroundStyle(appearance.theme.secondaryText)
                }

                Spacer()

                if isAlreadyAdded {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark")
                        Text("Già in libreria")
                    }
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Color.green)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.green.opacity(0.12))
                    .clipShape(Capsule())
                } else {
                    SteamButtonView(
                        title: isAddingThis ? "Importazione..." : "Aggiungi",
                        icon: "plus",
                        variant: .primaryGreen,
                        isLoading: isAddingThis
                    ) {
                        addGame(hit)
                    }
                }
            }
        }
    }

    private func performSearch() {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !isSearching else { return }

        isSearching = true
        errorMessage = nil
        successMessage = nil
        hits = []

        Task {
            do {
                let results = try await Task.detached {
                    try MacLuaBridge.live.search(q)
                }.value

                // Risolvi e filtra in modo che SOLO i giochi base compaiano (mai DLC singoli)
                var resolvedHits: [SearchHit] = []
                var seenAppIds = Set<Int>()

                for hit in results {
                    let meta = await Catalog.shared.metaOrFetch(hit.appid)
                    if meta.isDLC {
                        // Se è un DLC, risolvi automaticamente al gioco base genitore
                        if let parentId = meta.parentAppId, let parentName = meta.parentName {
                            if !seenAppIds.contains(parentId) {
                                seenAppIds.insert(parentId)
                                resolvedHits.append(SearchHit(appid: parentId, name: parentName))
                            }
                        }
                    } else if meta.type == "music" {
                        continue
                    } else {
                        if !seenAppIds.contains(hit.appid) {
                            seenAppIds.insert(hit.appid)
                            resolvedHits.append(hit)
                        }
                    }
                }

                hits = resolvedHits
                isSearching = false
                if hits.isEmpty {
                    errorMessage = "Nessun gioco trovato per \"\(q)\"."
                }
            } catch {
                isSearching = false
                errorMessage = error.localizedDescription
            }
        }
    }

    private func addGame(_ hit: SearchHit) {
        addingAppId = hit.appid
        errorMessage = nil
        successMessage = nil

        Task {
            do {
                try await store.addGame(appid: hit.appid, name: hit.name)
                store.startDownload(appid: hit.appid)
                addingAppId = nil
                successMessage = "“\(hit.name)” aggiunto! Download e preparazione per Steam avviati."
            } catch {
                addingAppId = nil
                errorMessage = "Impossibile aggiungere: \(error.localizedDescription)"
            }
        }
    }
}
