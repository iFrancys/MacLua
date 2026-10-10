import SwiftUI

struct HomeView: View {
    @Binding var selectedTab: AppTab
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState var verifyResult: VerifyOut? = nil
    @UIState var isVerifying = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: CGFloat(appearance.density.spacing)) {
                if store.games.isEmpty && !store.isLoading {
                    emptyLibraryCard
                } else if let game = store.selectedGame {
                    if appearance.showLargeHero {
                        heroCard(for: game)
                    }

                    // 3 Card sotto la hero (ispirate allo screenshot di riferimento)
                    HStack(alignment: .top, spacing: CGFloat(appearance.density.spacing)) {
                        downloadsCard
                        updatesCard
                        licensesCard
                    }

                    // Galleria orizzontale giochi gestiti
                    managedGamesRow
                }
            }
            .padding(CGFloat(appearance.density.padding))
        }
    }

    // MARK: - Hero Card (Ispirata a "Ori and the Blind Forest" nello screenshot)

    @ViewBuilder
    private func heroCard(for game: GameItem) -> some View {
        let isDownloading = Downloader.shared.isRunning(appid: game.appid)
        let downloadItem = Downloader.shared.currentItem(for: game.appid)

        ZStack(alignment: .bottomLeading) {
            // Sfondo artwork cinematografico
            AsyncArtwork(urls: Art.hero(game.appid), cornerRadius: CGFloat(appearance.cornerRadius))
                .frame(height: 320)
                .overlay(
                    LinearGradient(
                        colors: [
                            Color.black.opacity(0.1),
                            Color.black.opacity(0.4),
                            Color.black.opacity(0.92)
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )

            // Contenuto testuale ed azioni sopra l'immagine
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    StatusBadge(state: game.state, isDownloading: isDownloading)

                    Text("App \(game.appid)")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.6))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Color.black.opacity(0.4))
                        .clipShape(Capsule())
                }

                Text(game.name)
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(.white)
                    .lineLimit(1)

                if let desc = game.shortDescription, !desc.isEmpty {
                    Text(desc)
                        .font(.system(size: 12.5, weight: .regular))
                        .foregroundStyle(.white.opacity(0.8))
                        .lineLimit(2)
                        .frame(maxWidth: 700, alignment: .leading)
                }

                // Barra di download se in corso
                if isDownloading, let dl = downloadItem {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(dl.statusText)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(appearance.accentColor)

                            Spacer()

                            if dl.totalMB > 0 {
                                Text("\(Int(dl.fraction * 100))%")
                                    .font(.system(size: 12, weight: .bold))
                                    .foregroundStyle(appearance.accentColor)
                            }
                        }

                        ProgressView(value: dl.fraction)
                            .progressViewStyle(.linear)
                            .tint(appearance.accentColor)
                    }
                    .frame(maxWidth: 500)
                    .padding(.vertical, 4)
                }

                // Azioni
                HStack(spacing: 12) {
                    if isDownloading {
                        SteamButtonView(title: "Annulla download", icon: "xmark.circle", variant: .destructive) {
                            store.cancelDownload(appid: game.appid)
                        }
                    } else {
                        switch game.state {
                        case .installed:
                            SteamButtonView(title: "Gioca con Steam", icon: "play.fill", variant: .primaryGreen) {
                                SteamControl.launchGame(appid: game.appid)
                            }
                        case .updateAvailable:
                            SteamButtonView(title: "Aggiorna gioco", icon: "arrow.triangle.2.circlepath", variant: .primaryGreen) {
                                store.startDownload(appid: game.appid)
                            }
                        case .notInstalled:
                            SteamButtonView(title: "Installa gioco", icon: "arrow.down.to.line", variant: .primaryGreen) {
                                store.startDownload(appid: game.appid)
                            }
                        }
                    }

                    SteamButtonView(
                        title: isVerifying ? "Verifica in corso..." : "Verifica integrità",
                        icon: "checkmark.shield",
                        variant: .secondary,
                        isLoading: isVerifying
                    ) {
                        verifyGame(game.appid)
                    }

                    SteamButtonView(title: "Dettagli Steam", icon: "arrow.up.right.square", variant: .secondary) {
                        SteamControl.openGamePage(appid: game.appid)
                    }
                }
                .padding(.top, 4)

                // Risultato verifica se presente
                if let v = verifyResult, v.appid == game.appid {
                    HStack(spacing: 6) {
                        Image(systemName: v.bad.isEmpty ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(v.bad.isEmpty ? Color.green : Color.orange)

                        Text(v.bad.isEmpty ? "Tutti i file sono integri e conformi al manifest." : "\(v.bad.count) file richiedono aggiornamento.")
                            .font(.system(size: 12))
                            .foregroundStyle(.white.opacity(0.9))
                    }
                    .padding(.top, 2)
                }
            }
            .padding(24)
        }
        .clipShape(RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius)))
        .overlay(
            RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius))
                .stroke(Color.white.opacity(0.12), lineWidth: 1)
        )
    }

    // MARK: - 3 Card di Stato

    private var downloadsCard: some View {
        SteamCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Image(systemName: "arrow.down.circle.fill")
                        .foregroundStyle(appearance.accentColor)
                    Text("Download in corso")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                }

                if let aid = Downloader.shared.activeAppId,
                   let item = Downloader.shared.currentItem(for: aid) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(item.title)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(appearance.theme.primaryText)
                            .lineLimit(1)

                        ProgressView(value: item.fraction)
                            .tint(appearance.accentColor)

                        HStack {
                            Text(item.statusText)
                                .font(.system(size: 11))
                                .foregroundStyle(appearance.theme.secondaryText)
                            Spacer()
                            Button("Annulla") {
                                Downloader.shared.cancel(appid: aid)
                            }
                            .font(.system(size: 11, weight: .bold))
                            .buttonStyle(.plain)
                            .foregroundStyle(.red)
                        }
                    }
                } else {
                    VStack(spacing: 6) {
                        Text("Nessun download attivo")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                        Text("Tutti i giochi sono pronti o in attesa")
                            .font(.system(size: 11))
                            .foregroundStyle(appearance.theme.tertiaryText)
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 110)
        }
    }

    private var updatesCard: some View {
        let updates = store.games.filter { $0.state == .updateAvailable }

        return SteamCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .foregroundStyle(Color.orange)
                    Text("Aggiornamenti")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                    Text("\(updates.count)")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(appearance.theme.secondaryText)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.white.opacity(0.08))
                        .clipShape(Capsule())
                }

                if updates.isEmpty {
                    VStack(spacing: 6) {
                        Text("Tutti i manifest aggiornati")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                        Text("Nessun delta da scaricare")
                            .font(.system(size: 11))
                            .foregroundStyle(appearance.theme.tertiaryText)
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
                } else {
                    VStack(spacing: 8) {
                        ForEach(updates.prefix(2)) { g in
                            HStack {
                                Text(g.name)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(appearance.theme.primaryText)
                                    .lineLimit(1)
                                Spacer()
                                Button("Aggiorna") {
                                    store.startDownload(appid: g.appid)
                                }
                                .font(.system(size: 11, weight: .semibold))
                                .buttonStyle(.plain)
                                .foregroundStyle(appearance.accentColor)
                            }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 110)
        }
    }

    private var licensesCard: some View {
        SteamCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Image(systemName: store.areLicensesHealthy ? "checkmark.shield.fill" : "exclamationmark.shield.fill")
                        .foregroundStyle(store.areLicensesHealthy ? Color.green : Color.orange)
                    Text("Stato Licenze")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                }

                if store.areLicensesHealthy {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Tutte le licenze allineate")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(Color.green.opacity(0.9))
                        Text("Depot e pacchetti registrati in Steam.")
                            .font(.system(size: 11))
                            .foregroundStyle(appearance.theme.tertiaryText)
                    }
                    .padding(.vertical, 4)
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(store.missingLicenseAppIds.count) licenze da risincronizzare")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(Color.orange)

                        Button {
                            Task {
                                await store.repairLicenses()
                            }
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "wrench.and.screwdriver.fill")
                                Text("Ripara e Riavvia Steam")
                            }
                            .font(.system(size: 11, weight: .bold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(Color.orange.opacity(0.2))
                            .foregroundStyle(Color.orange)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 110)
        }
    }

    // MARK: - Riga Giochi Gestiti

    private var managedGamesRow: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Tutti i giochi in gestione")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(appearance.theme.primaryText)
                Spacer()
                Button("Vedi in griglia") {
                    selectedTab = .library
                }
                .font(.system(size: 12, weight: .semibold))
                .buttonStyle(.plain)
                .foregroundStyle(appearance.accentColor)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(store.games) { g in
                        gameQuickCard(for: g)
                    }
                }
            }
        }
        .padding(.top, 8)
    }

    private func gameQuickCard(for game: GameItem) -> some View {
        let isSelected = store.selectedAppId == game.appid

        return Button {
            store.selectedAppId = game.appid
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                AsyncArtwork(urls: Art.capsule(game.appid), cornerRadius: 8)
                    .frame(width: 170, height: 95)

                Text(game.name)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(appearance.theme.primaryText)
                    .lineLimit(1)
                    .frame(width: 170, alignment: .leading)

                HStack {
                    Text(game.state.shortLabel)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(statusColor(game.state))
                    Spacer()
                }
                .frame(width: 170)
            }
            .padding(8)
            .background(isSelected ? appearance.accentColor.opacity(0.15) : appearance.theme.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isSelected ? appearance.accentColor : appearance.theme.cardBorder, lineWidth: 1.5)
            )
        }
        .buttonStyle(.plain)
    }

    private func statusColor(_ state: StatusApp.State) -> Color {
        switch state {
        case .installed: return Color.green
        case .updateAvailable: return Color.orange
        case .notInstalled: return Color.blue
        }
    }

    private var emptyLibraryCard: some View {
        SteamCard {
            VStack(spacing: 14) {
                Image(systemName: "square.grid.2x2.badge.plus")
                    .font(.system(size: 40))
                    .foregroundStyle(appearance.theme.tertiaryText)

                Text("La tua libreria è vuota")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(appearance.theme.primaryText)

                Text("Aggiungi il tuo primo gioco dalla scheda Aggiungi. Il file lua e i manifest verranno importati automaticamente.")
                    .font(.system(size: 13))
                    .foregroundStyle(appearance.theme.secondaryText)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 400)

                SteamButtonView(title: "Aggiungi un Gioco", icon: "plus", variant: .accent) {
                    selectedTab = .add
                }
            }
            .frame(maxWidth: .infinity)
            .padding(40)
        }
    }

    private func verifyGame(_ appid: Int) {
        isVerifying = true
        Task {
            if let out = try? await store.verifyGame(appid: appid) {
                verifyResult = out
            }
            isVerifying = false
        }
    }
}
