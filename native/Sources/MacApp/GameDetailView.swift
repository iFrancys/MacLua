import SwiftUI

struct GameDetailView: View {
    let game: GameItem
    let onBack: () -> Void

    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState var isVerifying = false
    @UIState var verifyResult: VerifyOut? = nil
    @UIState var showDeleteConfirm = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Top bar con torna indietro
                HStack {
                    Button(action: onBack) {
                        HStack(spacing: 6) {
                            Image(systemName: "chevron.left")
                            Text("Torna alla libreria")
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(appearance.accentColor)
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    Button {
                        showDeleteConfirm = true
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: "trash")
                            Text("Rimuovi gioco")
                        }
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Color.red.opacity(0.85))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.red.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                }

                // Hero Artwork & Info
                ZStack(alignment: .bottomLeading) {
                    AsyncArtwork(urls: Art.hero(game.appid), cornerRadius: 12)
                        .frame(height: 280)
                        .overlay(
                            LinearGradient(
                                colors: [Color.black.opacity(0.1), Color.black.opacity(0.85)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )

                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            StatusBadge(state: game.state, isDownloading: Downloader.shared.isRunning(appid: game.appid))
                            Text("Steam AppID: \(game.appid)")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.7))
                        }

                        Text(game.name)
                            .font(.system(size: 26, weight: .bold))
                            .foregroundStyle(.white)

                        if let desc = game.shortDescription {
                            Text(desc)
                                .font(.system(size: 13))
                                .foregroundStyle(.white.opacity(0.85))
                                .lineLimit(3)
                        }
                    }
                    .padding(24)
                }
                .clipShape(RoundedRectangle(cornerRadius: 12))

                // Azioni Principali
                SteamCard {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Gestione & Azioni")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)

                        let isDownloading = Downloader.shared.isRunning(appid: game.appid)
                        let dl = Downloader.shared.currentItem(for: game.appid)

                        if isDownloading, let dl {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text("Download in corso...")
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundStyle(appearance.accentColor)
                                    Spacer()
                                    Text("\(Int(dl.fraction * 100))%")
                                        .font(.system(size: 13, weight: .bold))
                                        .foregroundStyle(appearance.accentColor)
                                }

                                ProgressView(value: dl.fraction)
                                    .tint(appearance.accentColor)

                                HStack {
                                    Text(dl.statusText)
                                        .font(.system(size: 12))
                                        .foregroundStyle(appearance.theme.secondaryText)
                                    Spacer()
                                    SteamButtonView(title: "Annulla", icon: "xmark", variant: .destructive) {
                                        store.cancelDownload(appid: game.appid)
                                    }
                                }
                            }
                        } else {
                            HStack(spacing: 12) {
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

                                SteamButtonView(
                                    title: isVerifying ? "Verifica in corso..." : "Verifica integrità file",
                                    icon: "checkmark.shield",
                                    variant: .secondary,
                                    isLoading: isVerifying
                                ) {
                                    runVerify()
                                }

                                SteamButtonView(title: "Apri dialogo Installa Steam", icon: "steam", variant: .secondary) {
                                    SteamControl.openInstall(appid: game.appid)
                                }

                                SteamButtonView(title: "Pagina Store", icon: "arrow.up.right.square", variant: .secondary) {
                                    SteamControl.openGamePage(appid: game.appid)
                                }
                            }
                        }

                        if let v = verifyResult {
                            Divider().background(appearance.theme.cardBorder)

                            VStack(alignment: .leading, spacing: 6) {
                                HStack(spacing: 8) {
                                    Image(systemName: v.bad.isEmpty ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                        .foregroundStyle(v.bad.isEmpty ? Color.green : Color.orange)

                                    Text(v.bad.isEmpty ? "Integrità verificata con successo: nessun file mancante o corrotto." : "\(v.bad.count) file richiedono riscaricamento:")
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundStyle(appearance.theme.primaryText)
                                }

                                if !v.bad.isEmpty {
                                    ForEach(v.bad.prefix(6), id: \.self) { path in
                                        Text("• \(path)")
                                            .font(.system(size: 11, design: .monospaced))
                                            .foregroundStyle(appearance.theme.secondaryText)
                                    }
                                }
                            }
                        }
                    }
                }

                // Dettagli Tecnici Puliti
                SteamCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Dati del Manifest")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)

                        Grid(alignment: .leading, horizontalSpacing: 20, verticalSpacing: 8) {
                            GridRow {
                                Text("AppID Steam:")
                                    .foregroundStyle(appearance.theme.secondaryText)
                                Text("\(game.appid)")
                                    .foregroundStyle(appearance.theme.primaryText)
                            }

                            GridRow {
                                Text("Depot configurati:")
                                    .foregroundStyle(appearance.theme.secondaryText)
                                Text("\(game.status?.appinfoDepots ?? 0) depot registrati")
                                    .foregroundStyle(appearance.theme.primaryText)
                            }

                            GridRow {
                                Text("AppManifest locale:")
                                    .foregroundStyle(appearance.theme.secondaryText)
                                Text(game.status?.hasAppmanifest == true ? "Presente in Steam/steamapps" : "Non presente (scarica per crearlo)")
                                    .foregroundStyle(game.status?.hasAppmanifest == true ? Color.green : appearance.theme.secondaryText)
                            }

                            if let versions = game.status?.versions {
                                GridRow {
                                    Text("Versione manifest installata:")
                                        .foregroundStyle(appearance.theme.secondaryText)
                                    Text(versions.installed.values.first ?? "Nessuna")
                                        .font(.system(size: 12, design: .monospaced))
                                        .foregroundStyle(appearance.theme.primaryText)
                                }

                                GridRow {
                                    Text("Versione manifest pubblica:")
                                        .foregroundStyle(appearance.theme.secondaryText)
                                    Text(versions.live.values.first ?? "Nessuna")
                                        .font(.system(size: 12, design: .monospaced))
                                        .foregroundStyle(appearance.theme.primaryText)
                                }
                            }
                        }
                        .font(.system(size: 13))
                    }
                }
            }
            .padding(CGFloat(appearance.density.padding))
        }
        .confirmationDialog(
            "Vuoi davvero rimuovere \(game.name)?",
            isPresented: $showDeleteConfirm,
            titleVisibility: .visible
        ) {
            Button("Rimuovi dalla gestione", role: .destructive) {
                Task {
                    try? await store.removeGame(appid: game.appid)
                    onBack()
                }
            }
            Button("Annulla", role: .cancel) {}
        } message: {
            Text("Verranno rimossi i file lua e le chiavi depot associate a questo gioco. I file di gioco già scaricati in steamapps non verranno cancellati.")
        }
    }

    private func runVerify() {
        isVerifying = true
        Task {
            if let out = try? await store.verifyGame(appid: game.appid) {
                verifyResult = out
            }
            isVerifying = false
        }
    }
}
