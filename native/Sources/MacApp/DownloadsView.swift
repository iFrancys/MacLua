import SwiftUI

struct DownloadsView: View {
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Sezione Download Attivi
                VStack(alignment: .leading, spacing: 12) {
                    Text("Attività Recenti & Download")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)

                    let activeDownloads = Downloader.shared.downloads.values.sorted { $0.appid < $1.appid }

                    if activeDownloads.isEmpty {
                        SteamCard {
                            HStack(spacing: 12) {
                                Image(systemName: "arrow.down.circle")
                                    .font(.system(size: 24))
                                    .foregroundStyle(appearance.theme.tertiaryText)

                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Nessun download in corso")
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundStyle(appearance.theme.primaryText)
                                    Text("I download e gli aggiornamenti avviati appariranno qui con il progresso in tempo reale.")
                                        .font(.system(size: 12))
                                        .foregroundStyle(appearance.theme.secondaryText)
                                }
                                Spacer()
                            }
                            .padding(8)
                        }
                    } else {
                        ForEach(activeDownloads) { item in
                            downloadItemRow(for: item)
                        }
                    }
                }

                // Sezione Aggiornamenti Disponibili
                let updates = store.games.filter { $0.state == .updateAvailable }
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text("Aggiornamenti Disponibili (\(updates.count))")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)
                        Spacer()

                        if !updates.isEmpty {
                            SteamButtonView(title: "Aggiorna tutti", icon: "arrow.down.circle.fill", variant: .primaryGreen) {
                                for g in updates {
                                    store.startDownload(appid: g.appid)
                                }
                            }
                        }
                    }

                    if updates.isEmpty {
                        SteamCard {
                            HStack(spacing: 12) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 22))
                                    .foregroundStyle(Color.green)

                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Tutti i giochi sono aggiornati")
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundStyle(appearance.theme.primaryText)
                                    Text("I manifest installati corrispondono alle ultime build pubblicate da Steam.")
                                        .font(.system(size: 12))
                                        .foregroundStyle(appearance.theme.secondaryText)
                                }
                                Spacer()
                            }
                            .padding(8)
                        }
                    } else {
                        ForEach(updates) { game in
                            updateGameRow(for: game)
                        }
                    }
                }
            }
            .padding(CGFloat(appearance.density.padding))
        }
    }

    private func downloadItemRow(for item: DownloadItem) -> some View {
        SteamCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    AsyncArtwork(urls: Art.tile(item.appid), cornerRadius: 6)
                        .frame(width: 80, height: 40)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.title)
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)

                        Text(item.statusText)
                            .font(.system(size: 12))
                            .foregroundStyle(item.error != nil ? Color.red : appearance.accentColor)
                    }

                    Spacer()

                    if Downloader.shared.isRunning(appid: item.appid) {
                        SteamButtonView(title: "Annulla", icon: "xmark", variant: .destructive) {
                            Downloader.shared.cancel(appid: item.appid)
                        }
                    } else if item.isCompleted {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(Color.green)
                            .font(.system(size: 20))
                    }
                }

                if Downloader.shared.isRunning(appid: item.appid) {
                    ProgressView(value: item.fraction)
                        .tint(appearance.accentColor)
                }
            }
        }
    }

    private func updateGameRow(for game: GameItem) -> some View {
        SteamCard {
            HStack(spacing: 14) {
                AsyncArtwork(urls: Art.tile(game.appid), cornerRadius: 6)
                    .frame(width: 100, height: 48)

                VStack(alignment: .leading, spacing: 3) {
                    Text(game.name)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)

                    Text("Nuova build disponibile sui CDN Steam.")
                        .font(.system(size: 12))
                        .foregroundStyle(appearance.theme.secondaryText)
                }

                Spacer()

                SteamButtonView(title: "Scarica Aggiornamento", icon: "arrow.triangle.2.circlepath", variant: .primaryGreen) {
                    store.startDownload(appid: game.appid)
                }
            }
        }
    }
}
