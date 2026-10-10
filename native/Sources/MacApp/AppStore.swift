import SwiftUI

struct GameItem: Identifiable, Sendable, Equatable {
    let appid: Int
    var name: String
    var status: StatusApp?
    var shortDescription: String?

    var id: Int { appid }

    var state: StatusApp.State {
        status?.state ?? .notInstalled
    }
}

@Observable @MainActor
final class AppStore {
    static let shared = AppStore()

    // MARK: - Dati di Stato

    var games: [GameItem] = []
    var selectedAppId: Int?
    var isLoading = false
    var errorMessage: String?
    var toastMessage: String?

    // Stato Licenze
    var areLicensesHealthy = true
    var missingLicenseAppIds: [Int] = []
    var totalDepots: Int = 0

    // Configurazione & Sistema
    var hasApiKey = false
    var apiKeySource: String?
    var isAgentEnabled = false
    var doctorChecks: [DoctorCheck] = []
    var isDoctorLoaded = false

    // Statistiche
    var installedCount: Int {
        games.filter { $0.state == .installed }.count
    }

    var updatesCount: Int {
        games.filter { $0.state == .updateAvailable }.count
    }

    var notInstalledCount: Int {
        games.filter { $0.state == .notInstalled }.count
    }

    var selectedGame: GameItem? {
        guard let id = selectedAppId else { return games.first }
        return games.first { $0.appid == id } ?? games.first
    }

    init() {
        isAgentEnabled = MacLuaBridge.live.isAgentInstalled()
    }

    // MARK: - Ricarica Libreria

    func reloadLibrary() async {
        isLoading = true
        errorMessage = nil

        do {
            let statusAll = try await Task.detached {
                try MacLuaBridge.live.status()
            }.value
            areLicensesHealthy = statusAll.ok
            missingLicenseAppIds = statusAll.missing.appids
            totalDepots = statusAll.depots

            // Garantisce che solo i giochi base (e mai DLC singoli) siano presenti nella libreria
            var baseAppIds: [Int] = []
            for aid in statusAll.apps {
                let meta = await Catalog.shared.metaOrFetch(aid)
                if !meta.isDLC {
                    baseAppIds.append(aid)
                }
            }
            let appids = baseAppIds.sorted()
            let resolvedNames = await Catalog.shared.resolve(appids)

            // Caricamento in parallelo dello stato dettagliato per ciascuna app
            var detailedStatuses: [Int: StatusApp] = [:]
            await withTaskGroup(of: (Int, StatusApp?).self) { group in
                for aid in appids {
                    group.addTask {
                        let st = try? await Task.detached {
                            try MacLuaBridge.live.appStatus(aid)
                        }.value
                        return (aid, st)
                    }
                }
                for await (aid, st) in group {
                    if let st {
                        detailedStatuses[aid] = st
                    }
                }
            }

            var updatedGames: [GameItem] = []
            for aid in appids {
                let name = resolvedNames[aid] ?? "App \(aid)"
                let desc = Catalog.shared.shortDescription(aid)
                let st = detailedStatuses[aid]
                updatedGames.append(GameItem(appid: aid, name: name, status: st, shortDescription: desc))
            }

            self.games = updatedGames

            if selectedAppId == nil || !appids.contains(selectedAppId!) {
                selectedAppId = games.first?.appid
            }

            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }

        await checkApiKey()
    }

    // MARK: - Azioni Giochi

    func startDownload(appid: Int) {
        guard let game = games.first(where: { $0.appid == appid }) else { return }
        Downloader.shared.start(appid: appid, title: game.name) { [weak self] in
            Task { @MainActor in
                await self?.reloadLibrary()
            }
        }
    }

    func cancelDownload(appid: Int) {
        Downloader.shared.cancel(appid: appid)
    }

    func addGame(appid: Int, name: String? = nil) async throws {
        try await Task.detached {
            try MacLuaBridge.live.addApp(appid)
        }.value

        if let name {
            toastMessage = "“\(name)” aggiunto con successo."
        } else {
            toastMessage = "Gioco \(appid) aggiunto."
        }

        if AppearanceSettings.shared.restartSteamOnAdd {
            await SteamControl.restartSteam()
        }

        await reloadLibrary()
    }

    func removeGame(appid: Int) async throws {
        try await Task.detached {
            try MacLuaBridge.live.removeApp(appid)
        }.value
        toastMessage = "Gioco rimosso dalla gestione."
        await reloadLibrary()
    }

    func verifyGame(appid: Int) async throws -> VerifyOut {
        try await Task.detached {
            try MacLuaBridge.live.verify(appid)
        }.value
    }

    // MARK: - Licenze & Riparazione

    func repairLicenses() async {
        do {
            _ = try await Task.detached {
                try MacLuaBridge.live.ensureLicenses()
            }.value
            toastMessage = "Licenze e manifest riapplicati!"
            await SteamControl.restartSteam()
            await reloadLibrary()
        } catch {
            errorMessage = "Errore durante la riparazione licenze: \(error.localizedDescription)"
        }
    }

    // MARK: - Impostazioni

    func checkApiKey() async {
        if let conf = try? await Task.detached(operation: {
            try MacLuaBridge.live.config()
        }).value {
            hasApiKey = conf.hasKey
            apiKeySource = conf.source
        }
    }

    func saveApiKey(_ key: String) async throws {
        try await Task.detached {
            try MacLuaBridge.live.setKey(key)
        }.value
        hasApiKey = true
        toastMessage = "Chiave API salvata in sicurezza."
    }

    func clearApiKey() async throws {
        try await Task.detached {
            try MacLuaBridge.live.clearKey()
        }.value
        hasApiKey = false
        toastMessage = "Chiave API rimossa."
    }

    func toggleAgent(enabled: Bool) async {
        do {
            try await Task.detached {
                try MacLuaBridge.live.setAgent(enabled: enabled)
            }.value
            isAgentEnabled = enabled
            toastMessage = enabled ? "Avvio automatico al login attivato." : "Avvio al login disattivato."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadDoctor() async {
        do {
            let doc = try await Task.detached {
                try MacLuaBridge.live.doctor()
            }.value
            doctorChecks = doc.checks
            isDoctorLoaded = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
