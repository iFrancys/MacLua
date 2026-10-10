import SwiftUI

struct DepotsView: View {
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState private var selectedAppId: Int?
    @UIState private var depotsResponse: GameDepotsResponse?
    @UIState private var isLoading = false
    @UIState private var osFilter: String = "all"
    @UIState private var searchCustomAppId: String = ""

    var body: some View {
        VStack(spacing: 0) {
            // Header e Selettore Gioco
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 10) {
                    Image(systemName: "shippingbox.fill")
                        .font(.system(size: 22))
                        .foregroundStyle(appearance.accentColor)

                    Text("Ispettore Depot & Build")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)

                    Spacer()

                    if isLoading {
                        ProgressView()
                            .controlSize(.small)
                    }
                }

                Text("Analisi approfondita dei depot Steam, manifest GID, architetture e chiavi di decrittazione (stile LuaTools).")
                    .font(.system(size: 13))
                    .foregroundStyle(appearance.theme.secondaryText)

                // Barra selezione gioco e filtri
                HStack(spacing: 12) {
                    // Picker giochi dalla libreria
                    Menu {
                        ForEach(store.games) { g in
                            Button(g.name) {
                                selectedAppId = g.appid
                                Task { await loadDepots(for: g.appid) }
                            }
                        }
                    } label: {
                        HStack {
                            Image(systemName: "gamecontroller.fill")
                            Text(currentSelectedGameName)
                                .lineLimit(1)
                            Spacer()
                            Image(systemName: "chevron.up.chevron.down")
                                .font(.system(size: 10))
                        }
                        .frame(minWidth: 220)
                    }
                    .menuStyle(.borderedButton)

                    // Campo di ricerca personalizzato per AppID
                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass")
                            .foregroundStyle(appearance.theme.secondaryText)
                        TextField("Cerca altro AppID...", text: $searchCustomAppId)
                            .textFieldStyle(.plain)
                            .onSubmit {
                                if let aid = Int(searchCustomAppId.trimmingCharacters(in: .whitespaces)) {
                                    selectedAppId = aid
                                    Task { await loadDepots(for: aid) }
                                }
                            }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.white.opacity(0.06))
                    .cornerRadius(8)
                    .frame(width: 180)

                    Spacer()

                    // Filtro OS (Tutti / macOS / Contenuto)
                    Picker("Filtro OS", selection: $osFilter) {
                        Text("Tutti").tag("all")
                        Text("macOS").tag("macos")
                        Text("Contenuto / Dati").tag("content")
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 220)
                }
            }
            .padding(20)
            .background(appearance.theme.cardBg)
            .overlay(Divider(), alignment: .bottom)

            // Contenuto principale
            ScrollView {
                VStack(spacing: 16) {
                    if let resp = depotsResponse {
                        // Summary Stats Bar
                        HStack(spacing: 20) {
                            statBadge(
                                title: "Depot Totali",
                                value: "\(resp.depotsCount)",
                                icon: "shippingbox.fill",
                                color: appearance.accentColor
                            )

                            statBadge(
                                title: "Depot macOS",
                                value: "\(resp.depots.filter { isMacOsDepot($0) }.count)",
                                icon: "apple.logo",
                                color: Color.green
                            )

                            statBadge(
                                title: "Chiavi Sbloccate",
                                value: "\(resp.depots.filter { $0.hasKey }.count)/\(resp.depotsCount)",
                                icon: "key.fill",
                                color: Color.orange
                            )

                            statBadge(
                                title: "Manifest Staged",
                                value: "\(resp.depots.filter { $0.hasManifest }.count)/\(resp.depotsCount)",
                                icon: "doc.fill",
                                color: Color.blue
                            )
                        }
                        .padding(.top, 14)

                        // Lista dei Depot
                        VStack(spacing: 8) {
                            ForEach(filteredDepots(resp.depots)) { d in
                                depotRow(d)
                            }
                        }
                    } else if !store.games.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "shippingbox")
                                .font(.system(size: 36))
                                .foregroundStyle(appearance.theme.secondaryText)
                            Text("Seleziona un gioco per visualizzare la struttura dei depot")
                                .font(.system(size: 13))
                                .foregroundStyle(appearance.theme.secondaryText)
                        }
                        .frame(maxWidth: .infinity, minHeight: 280)
                    } else {
                        VStack(spacing: 12) {
                            Image(systemName: "tray")
                                .font(.system(size: 36))
                                .foregroundStyle(appearance.theme.secondaryText)
                            Text("Nessun gioco presente in libreria. Aggiungi un gioco per ispezionarne i depot.")
                                .font(.system(size: 13))
                                .foregroundStyle(appearance.theme.secondaryText)
                        }
                        .frame(maxWidth: .infinity, minHeight: 280)
                    }
                }
                .padding(20)
            }
        }
        .task {
            if selectedAppId == nil, let first = store.games.first {
                selectedAppId = first.appid
                await loadDepots(for: first.appid)
            }
        }
    }

    private var currentSelectedGameName: String {
        guard let aid = selectedAppId else { return "Seleziona gioco..." }
        return store.games.first { $0.appid == aid }?.name ?? "Gioco \(aid)"
    }

    private func isMacOsDepot(_ d: DepotItem) -> Bool {
        let os = d.os.lowercased()
        return os == "macos" || os == "osx" || os == "mac" || os == "macosx"
    }

    private func filteredDepots(_ depots: [DepotItem]) -> [DepotItem] {
        switch osFilter {
        case "macos":
            return depots.filter { isMacOsDepot($0) }
        case "content":
            return depots.filter { !isMacOsDepot($0) && $0.os != "windows" }
        default:
            return depots
        }
    }

    @ViewBuilder
    private func statBadge(title: String, value: String, icon: String, color: Color) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(color)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 11))
                    .foregroundStyle(appearance.theme.secondaryText)
                Text(value)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(appearance.theme.primaryText)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color.white.opacity(0.04))
        .cornerRadius(8)
    }

    @ViewBuilder
    private func depotRow(_ d: DepotItem) -> some View {
        HStack(spacing: 14) {
            // Icona e ID Depot
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text("Depot \(d.depotId)")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)

                    if d.isDlc {
                        Text("DLC INTEGRATO")
                            .font(.system(size: 9, weight: .bold))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.purple.opacity(0.2))
                            .foregroundStyle(Color.purple)
                            .cornerRadius(4)
                    }

                    osBadge(d.os)
                }

                Text(d.name)
                    .font(.system(size: 11))
                    .foregroundStyle(appearance.theme.secondaryText)
                    .lineLimit(1)
            }

            Spacer()

            // Manifest GID
            VStack(alignment: .trailing, spacing: 2) {
                HStack(spacing: 4) {
                    Text("GID:")
                        .font(.system(size: 10))
                        .foregroundStyle(appearance.theme.secondaryText)
                    Text(d.gid)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(appearance.theme.primaryText)
                }

                Text(d.sizeStr)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(appearance.theme.secondaryText)
            }

            // Indicatori Chiave e Manifest
            HStack(spacing: 8) {
                if d.hasKey {
                    Label("Chiave OK", systemImage: "key.fill")
                        .font(.system(size: 10, weight: .bold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.green.opacity(0.15))
                        .foregroundStyle(Color.green)
                        .cornerRadius(6)
                } else {
                    Label("Senza Chiave", systemImage: "lock.fill")
                        .font(.system(size: 10, weight: .semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.orange.opacity(0.15))
                        .foregroundStyle(Color.orange)
                        .cornerRadius(6)
                }

                if d.hasManifest {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 8, height: 8)
                        .help("Manifest salvato in locale")
                } else {
                    Circle()
                        .fill(Color.gray.opacity(0.5))
                        .frame(width: 8, height: 8)
                        .help("Manifest non presente sul disco")
                }
            }
            .frame(width: 140, alignment: .trailing)
        }
        .padding(12)
        .background(appearance.theme.cardBg)
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.white.opacity(0.05), lineWidth: 1))
    }

    @ViewBuilder
    private func osBadge(_ osStr: String) -> some View {
        let os = osStr.lowercased()
        if os == "macos" || os == "osx" || os == "mac" {
            Text("macOS")
                .font(.system(size: 9, weight: .bold))
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.green.opacity(0.2))
                .foregroundStyle(Color.green)
                .cornerRadius(4)
        } else if os == "windows" {
            Text("Windows")
                .font(.system(size: 9, weight: .bold))
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.orange.opacity(0.2))
                .foregroundStyle(Color.orange)
                .cornerRadius(4)
        } else {
            Text(osStr.isEmpty ? "Dati" : osStr)
                .font(.system(size: 9, weight: .bold))
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.gray.opacity(0.2))
                .foregroundStyle(Color.gray)
                .cornerRadius(4)
        }
    }

    private func loadDepots(for appid: Int) async {
        isLoading = true
        do {
            depotsResponse = try await Task.detached {
                try MacLuaBridge.live.depots(appid: appid)
            }.value
        } catch {
            print("Errore caricamento depot: \(error)")
        }
        isLoading = false
    }
}
