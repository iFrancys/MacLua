import SwiftUI

struct CollectionsView: View {
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState private var collections: [CollectionItem] = []
    @UIState private var isLoading = false
    @UIState private var isCached = false
    @UIState private var searchText = ""
    @UIState private var selectedSort = "popular"
    @UIState private var addingSlug: String? = nil
    @UIState private var inspectingCollection: CollectionItem? = nil
    @UIState private var expandedDetails: [String: CollectionItem] = [:]
    @UIState private var errorMessage: String? = nil

    var filteredCollections: [CollectionItem] {
        if searchText.trimmingCharacters(in: .whitespaces).isEmpty {
            return collections
        }
        return collections.filter {
            $0.title.localizedCaseInsensitiveContains(searchText) ||
            $0.author.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header & Controlli
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                Text("Collezioni Community")
                                    .font(.system(size: 22, weight: .bold))
                                    .foregroundStyle(appearance.theme.primaryText)

                                if isCached {
                                    HStack(spacing: 4) {
                                        Image(systemName: "icloud.slash")
                                            .font(.system(size: 11))
                                        Text("Offline")
                                            .font(.system(size: 11, weight: .medium))
                                    }
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(Color.orange.opacity(0.18))
                                    .foregroundStyle(Color.orange)
                                    .clipShape(Capsule())
                                }
                            }

                            Text("Pacchetti e saghe curate da aggiungere con un clic. Tutti i DLC sono inclusi automaticamente.")
                                .font(.system(size: 13))
                                .foregroundStyle(appearance.theme.secondaryText)
                        }

                        Spacer()

                        SteamButtonView(
                            title: "Aggiorna",
                            icon: "arrow.clockwise",
                            variant: .secondary,
                            isLoading: isLoading
                        ) {
                            loadCollections()
                        }
                    }

                    // Barra di ricerca & Filtro
                    HStack(spacing: 12) {
                        HStack {
                            Image(systemName: "magnifyingglass")
                                .foregroundStyle(appearance.theme.tertiaryText)
                            TextField("Cerca collezione per nome o autore...", text: $searchText)
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
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .background(appearance.theme.cardBg)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(appearance.theme.cardBorder, lineWidth: 1)
                        )

                        Picker("Ordina", selection: $selectedSort) {
                            Text("Più popolari").tag("popular")
                            Text("Recenti").tag("recent")
                        }
                        .pickerStyle(.segmented)
                        .frame(width: 190)
                        .onChange(of: selectedSort) { _, _ in
                            loadCollections()
                        }
                    }
                    .padding(.top, 4)
                }

                if let err = errorMessage {
                    HStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(Color.red)
                        Text(err)
                            .font(.system(size: 12))
                            .foregroundStyle(Color.red)
                        Spacer()
                    }
                    .padding(10)
                    .background(Color.red.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }

                // Griglia Collezioni
                if isLoading && collections.isEmpty {
                    VStack(spacing: 14) {
                        ProgressView()
                        Text("Caricamento collezioni in corso...")
                            .font(.system(size: 13))
                            .foregroundStyle(appearance.theme.secondaryText)
                    }
                    .frame(maxWidth: .infinity, minHeight: 250)
                } else if filteredCollections.isEmpty {
                    VStack(spacing: 10) {
                        Image(systemName: "square.stack.3d.up.slash")
                            .font(.system(size: 36))
                            .foregroundStyle(appearance.theme.tertiaryText)
                        Text("Nessuna collezione trovata")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)
                        Text("Prova a modificare i filtri di ricerca.")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                    }
                    .frame(maxWidth: .infinity, minHeight: 250)
                } else {
                    LazyVGrid(
                        columns: [
                            GridItem(.adaptive(minimum: 280, maximum: 380), spacing: 14)
                        ],
                        spacing: 14
                    ) {
                        ForEach(filteredCollections) { item in
                            collectionCard(item)
                        }
                    }
                }
            }
            .padding(CGFloat(appearance.density.padding))
        }
        .task {
            if collections.isEmpty {
                loadCollections()
            }
        }
        .sheet(item: $inspectingCollection) { col in
            collectionDetailSheet(col)
        }
    }

    // MARK: - Card Singola Collezione

    private func collectionCard(_ item: CollectionItem) -> some View {
        SteamCard {
            VStack(alignment: .leading, spacing: 10) {
                // Copertina Collezione con badge conteggio
                ZStack(alignment: .bottomLeading) {
                    if let url = URL(string: item.cover), !item.cover.isEmpty {
                        AsyncImage(url: url) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            case .failure:
                                defaultCoverHeader
                            default:
                                Rectangle()
                                    .fill(appearance.theme.secondaryBg)
                                    .overlay(ProgressView().scaleEffect(0.7))
                            }
                        }
                        .frame(height: 125)
                        .clipped()
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    } else {
                        defaultCoverHeader
                    }

                    // Badge giochi
                    HStack(spacing: 5) {
                        Image(systemName: "square.stack.3d.up.fill")
                            .font(.system(size: 10))
                        Text(item.appCount > 0 ? "\(item.appCount) giochi" : "Multi-gioco")
                            .font(.system(size: 10, weight: .bold))
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.black.opacity(0.75))
                    .foregroundStyle(Color.white)
                    .clipShape(Capsule())
                    .padding(8)
                }

                // Titolo e Autore
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.title)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                        .lineLimit(1)

                    HStack(spacing: 6) {
                        Image(systemName: "person.circle")
                            .font(.system(size: 11))
                        Text(item.author)
                            .font(.system(size: 11))
                        Spacer()
                    }
                    .foregroundStyle(appearance.theme.secondaryText)
                }

                // Azioni
                HStack(spacing: 8) {
                    SteamButtonView(
                        title: "Dettagli",
                        icon: "info.circle",
                        variant: .secondary
                    ) {
                        openDetails(for: item)
                    }

                    Spacer()

                    let isAdding = addingSlug == item.id
                    SteamButtonView(
                        title: isAdding ? "Aggiunta..." : "Aggiungi Tutto",
                        icon: "plus.circle.fill",
                        variant: .accent,
                        isLoading: isAdding
                    ) {
                        addCollection(item)
                    }
                    .disabled(isAdding)
                }
            }
        }
    }

    private var defaultCoverHeader: some View {
        LinearGradient(
            colors: [appearance.accentColor.opacity(0.4), appearance.theme.secondaryBg],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .frame(height: 125)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            Image(systemName: "square.stack.3d.up.fill")
                .font(.system(size: 32))
                .foregroundStyle(Color.white.opacity(0.4))
        )
    }

    // MARK: - Modale Dettagli

    private func collectionDetailSheet(_ col: CollectionItem) -> some View {
        let details = expandedDetails[col.id] ?? col
        let appsList = details.apps ?? []

        return VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(details.title)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Text("Autore: \(details.author) • \(appsList.count) giochi nel pacchetto")
                        .font(.system(size: 12))
                        .foregroundStyle(appearance.theme.secondaryText)
                }
                Spacer()
                Button {
                    inspectingCollection = nil
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 18))
                        .foregroundStyle(appearance.theme.secondaryText)
                }
                .buttonStyle(.plain)
            }

            Divider().background(appearance.theme.cardBorder)

            Text("Giochi inclusi (Tutti i DLC verranno associati in automatico):")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(appearance.theme.primaryText)

            ScrollView {
                VStack(spacing: 8) {
                    if appsList.isEmpty {
                        Text("Caricamento elenco giochi in corso...")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                            .frame(maxWidth: .infinity, minHeight: 100)
                    } else {
                        ForEach(appsList, id: \.self) { appid in
                            HStack(spacing: 12) {
                                AsyncArtwork(urls: Art.tile(appid), cornerRadius: 4)
                                    .frame(width: 50, height: 26)

                                VStack(alignment: .leading, spacing: 1) {
                                    Text(Catalog.shared.name(appid) ?? "AppID \(appid)")
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundStyle(appearance.theme.primaryText)
                                    Text("AppID \(appid) • DLC inclusi")
                                        .font(.system(size: 11))
                                        .foregroundStyle(appearance.theme.secondaryText)
                                }

                                Spacer()

                                if store.games.contains(where: { $0.appid == appid }) {
                                    Text("Già in Libreria")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(Color.green)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.green.opacity(0.12))
                                        .clipShape(Capsule())
                                }
                            }
                            .padding(8)
                            .background(appearance.theme.cardBg)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                        }
                    }
                }
            }
            .frame(maxHeight: 300)

            HStack {
                Spacer()
                SteamButtonView(
                    title: "Aggiungi Tutti i Giochi",
                    icon: "plus.circle.fill",
                    variant: .accent
                ) {
                    inspectingCollection = nil
                    addCollection(details)
                }
            }
        }
        .padding(20)
        .frame(minWidth: 500, minHeight: 400)
        .background(appearance.theme.primaryBg)
    }

    // MARK: - Azioni

    private func loadCollections() {
        isLoading = true
        errorMessage = nil

        Task {
            do {
                let res = try MacLuaBridge.live.collectionsList(sort: selectedSort)
                await MainActor.run {
                    self.collections = res.collections
                    self.isCached = res.cached
                    self.isLoading = false
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Impossibile recuperare le collezioni: \(error.localizedDescription)"
                    self.isLoading = false
                }
            }
        }
    }

    private func openDetails(for item: CollectionItem) {
        inspectingCollection = item

        // Carica dettagli se non già in cache
        if expandedDetails[item.id] == nil {
            Task {
                if let detailed = try? MacLuaBridge.live.collectionShow(slug: item.id) {
                    await MainActor.run {
                        self.expandedDetails[item.id] = detailed
                    }
                }
            }
        }
    }

    private func addCollection(_ item: CollectionItem) {
        addingSlug = item.id

        Task {
            do {
                let res = try MacLuaBridge.live.collectionAdd(slug: item.id)
                await MainActor.run {
                    self.addingSlug = nil
                    self.store.toastMessage = "Collezione '\(item.title)' aggiunta: \(res.enqueued.count) giochi accodati!"
                }
                await store.reloadLibrary()
            } catch {
                await MainActor.run {
                    self.addingSlug = nil
                    self.errorMessage = "Errore durante l'aggiunta del pacchetto: \(error.localizedDescription)"
                }
            }
        }
    }
}
