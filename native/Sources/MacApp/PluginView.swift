import SwiftUI

struct PluginView: View {
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState private var status: SteamHookStatus?
    @UIState private var isLoading = false
    @UIState private var isInjecting = false
    @UIState private var isAgentActive = false
    @UIState private var message: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 10) {
                        Image(systemName: "puzzlepiece.extension.fill")
                            .font(.system(size: 24))
                            .foregroundStyle(appearance.accentColor)

                        Text("Plugin Steam & Integrazione In-Client")
                            .font(.system(size: 22, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)
                    }

                    Text("Aggiungi e scarica giochi direttamente dall'interfaccia di Steam. Tutti i DLC sono inclusi automaticamente.")
                        .font(.system(size: 13))
                        .foregroundStyle(appearance.theme.secondaryText)
                }

                if let message {
                    HStack {
                        Image(systemName: "info.circle.fill")
                            .foregroundStyle(appearance.accentColor)
                        Text(message)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(appearance.theme.primaryText)
                        Spacer()
                        Button("✕") { self.message = nil }
                            .buttonStyle(.plain)
                            .foregroundStyle(appearance.theme.secondaryText)
                    }
                    .padding(12)
                    .background(Color.white.opacity(0.06))
                    .cornerRadius(8)
                }

                // Status Card principale (stile LuaTools PluginView)
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        Text("Stato Connessione e Servizi")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)

                        Spacer()

                        Button {
                            Task { await refresh() }
                        } label: {
                            Label("Aggiorna", systemImage: "arrow.clockwise")
                                .font(.system(size: 12))
                        }
                        .buttonStyle(.bordered)
                    }

                    VStack(spacing: 12) {
                        statusRow(
                            title: "CEF Remote Debugging (Porta 8080)",
                            subtitle: status?.cdpAvailable == true ? "Attivo e connesso a Steam Helper" : "In attesa di Steam con flag attivo",
                            isActive: status?.cdpAvailable == true,
                            systemIcon: "network"
                        )

                        Divider().background(Color.white.opacity(0.1))

                        statusRow(
                            title: "Bridge Locale MacLua (Porta 6767)",
                            subtitle: "Server HTTP locale con token di sicurezza",
                            isActive: true,
                            systemIcon: "bolt.horizontal.fill"
                        )

                        Divider().background(Color.white.opacity(0.1))

                        statusRow(
                            title: "Marker CEF (.cef-enable-remote-debugging)",
                            subtitle: status?.markerPresent == true ? "Configurato correttamente nella cartella Steam" : "Non presente, premi Abilita per crearlo",
                            isActive: status?.markerPresent == true,
                            systemIcon: "checkmark.seal.fill"
                        )

                        Divider().background(Color.white.opacity(0.1))

                        statusRow(
                            title: "Demone di Avvio Automatico (LaunchAgent)",
                            subtitle: isAgentActive ? "Attivo: il bridge si avvia automaticamente al login" : "Disattivato (avvio manuale tramite MacLua)",
                            isActive: isAgentActive,
                            systemIcon: "gearshape.arrow.triangle.2.circlepath"
                        )
                    }
                }
                .padding(18)
                .background(appearance.theme.cardBg)
                .cornerRadius(12)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.08), lineWidth: 1))

                // Pulsanti di Azione Rapida
                HStack(spacing: 12) {
                    Button {
                        Task { await injectNow() }
                    } label: {
                        HStack {
                            Image(systemName: "bolt.fill")
                            Text("Inietta Ora nei Tab Aperti")
                        }
                        .font(.system(size: 13, weight: .bold))
                        .padding(.vertical, 8)
                        .padding(.horizontal, 14)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(appearance.accentColor)
                    .disabled(isInjecting || status?.cdpAvailable != true)

                    if status?.markerPresent != true {
                        Button {
                            Task { await enableHook() }
                        } label: {
                            Text("Abilita Integrazione Steam")
                                .font(.system(size: 13, weight: .semibold))
                                .padding(.vertical, 8)
                                .padding(.horizontal, 14)
                        }
                        .buttonStyle(.bordered)
                    } else {
                        Button {
                            Task { await disableHook() }
                        } label: {
                            Text("Disabilita Integrazione")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(Color.red)
                                .padding(.vertical, 8)
                                .padding(.horizontal, 14)
                        }
                        .buttonStyle(.bordered)
                    }

                    Button {
                        Task { await restartSteam() }
                    } label: {
                        HStack {
                            Image(systemName: "arrow.triangle.2.circlepath")
                            Text("Riavvia Steam")
                        }
                        .font(.system(size: 13, weight: .semibold))
                        .padding(.vertical, 8)
                        .padding(.horizontal, 14)
                    }
                    .buttonStyle(.bordered)
                }

                // Tab Aperti nel Client Steam (Ispettore in tempo reale)
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        Text("Tab Rilevati in Steam (\(status?.tabsCount ?? 0))")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(appearance.theme.primaryText)

                        Spacer()
                    }

                    if let tabs = status?.tabs, !tabs.isEmpty {
                        VStack(spacing: 8) {
                            ForEach(tabs) { tab in
                                HStack {
                                    Image(systemName: "safari.fill")
                                        .foregroundStyle(appearance.accentColor)
                                        .font(.system(size: 14))

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(tab.title.isEmpty ? "Tab Steam" : tab.title)
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundStyle(appearance.theme.primaryText)

                                        Text(tab.url)
                                            .font(.system(size: 11))
                                            .foregroundStyle(appearance.theme.secondaryText)
                                            .lineLimit(1)
                                    }

                                    Spacer()

                                    Text("Connesso")
                                        .font(.system(size: 10, weight: .bold))
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 3)
                                        .background(Color.green.opacity(0.15))
                                        .foregroundStyle(Color.green)
                                        .cornerRadius(4)
                                }
                                .padding(10)
                                .background(Color.white.opacity(0.03))
                                .cornerRadius(8)
                            }
                        }
                    } else {
                        Text("Nessun tab con interfaccia web trovato. Assicurati che Steam sia avviato.")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                            .padding(.vertical, 8)
                    }
                }
                .padding(18)
                .background(appearance.theme.cardBg)
                .cornerRadius(12)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.08), lineWidth: 1))

                // Come Funziona
                VStack(alignment: .leading, spacing: 10) {
                    Text("Come funziona l'integrazione:")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("• Steam CEF Debugging: MacLua comunica con il browser interno di Steam tramite porta locale 8080.")
                        Text("• Pulsante Sticky e Barra Fluttuante: Su ogni pagina del negozio Steam compare il pulsante «+ Aggiungi con MacLua (Tutti i DLC inclusi)» e la barra rapida «⚡ MacLua» in alto a destra.")
                        Text("• Zero esposizione DLC separati: Ogni volta che aggiungi un gioco, tutti i DLC attuali e futuri sono configurati e scaricati automaticamente.")
                    }
                    .font(.system(size: 12))
                    .foregroundStyle(appearance.theme.secondaryText)
                }
                .padding(16)
                .background(Color.white.opacity(0.02))
                .cornerRadius(10)
            }
            .padding(24)
        }
        .task {
            await refresh()
        }
    }

    @ViewBuilder
    private func statusRow(title: String, subtitle: String, isActive: Bool, systemIcon: String) -> some View {
        HStack(spacing: 14) {
            Image(systemName: systemIcon)
                .font(.system(size: 16))
                .foregroundStyle(isActive ? Color.green : Color.gray)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(appearance.theme.primaryText)
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundStyle(appearance.theme.secondaryText)
            }

            Spacer()

            Circle()
                .fill(isActive ? Color.green : Color.gray.opacity(0.4))
                .frame(width: 10, height: 10)
        }
    }

    private func refresh() async {
        isLoading = true
        MacLuaBridge.live.ensureBridgeRunning()
        isAgentActive = MacLuaBridge.live.isBridgeAgentInstalled()
        do {
            status = try await Task.detached {
                try MacLuaBridge.live.steamHookStatus()
            }.value
        } catch {
            message = "Errore lettura stato hook: \(error.localizedDescription)"
        }
        isLoading = false
    }

    private func injectNow() async {
        isInjecting = true
        do {
            try await Task.detached {
                try MacLuaBridge.live.injectSteamTabs()
            }.value
            message = "Iniezione completata con successo! Controlla il client Steam."
            await refresh()
        } catch {
            message = "Errore iniezione: \(error.localizedDescription)"
        }
        isInjecting = false
    }

    private func enableHook() async {
        do {
            try await Task.detached {
                try MacLuaBridge.live.enableSteamHook()
            }.value
            message = "Integrazione Steam abilitata. Riavvia Steam per applicare."
            await refresh()
        } catch {
            message = "Errore abilitazione: \(error.localizedDescription)"
        }
    }

    private func disableHook() async {
        do {
            try await Task.detached {
                try MacLuaBridge.live.disableSteamHook()
            }.value
            message = "Integrazione Steam disabilitata e file di hook rimossi."
            await refresh()
        } catch {
            message = "Errore disabilitazione: \(error.localizedDescription)"
        }
    }

    private func restartSteam() async {
        message = "Riavvio di Steam in corso..."
        await SteamControl.restartSteam()
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        await refresh()
    }
}
