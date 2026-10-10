import Foundation

// MARK: - Progresso Download

struct LineProgress: Sendable, Equatable {
    let mb: Double
    let totalMB: Double

    var fraction: Double? {
        totalMB > 0 ? min(1, mb / totalMB) : nil
    }
}

func parseProgress(_ line: String) -> LineProgress? {
    guard let data = line.trimmingCharacters(in: .whitespaces).data(using: .utf8),
          let obj = try? JSONDecoder().decode([String: Double].self, from: data),
          let mb = obj["mb"] else { return nil }
    return LineProgress(mb: mb, totalMB: obj["total"] ?? 0)
}

// MARK: - Modelli Collezioni Community (LuaTools inspired)

struct CollectionItem: Codable, Sendable, Identifiable, Equatable {
    let id: String
    let title: String
    let cover: String
    let appCount: Int
    let author: String
    var apps: [Int]?

    enum CodingKeys: String, CodingKey {
        case id, title, cover, appCount, author, apps
    }
}

struct CollectionsResponse: Codable, Sendable, Equatable {
    let collections: [CollectionItem]
    let cached: Bool
    let stale: Bool
}

struct CollectionAddResult: Codable, Sendable, Equatable {
    let ok: Bool
    let collection: String
    let enqueued: [Int]
}

// MARK: - Modelli Steam Hook & Vault

struct SteamHookTab: Codable, Sendable, Identifiable, Equatable {
    let title: String
    let url: String
    let id: String
}

struct SteamHookStatus: Codable, Sendable, Equatable {
    let markerPresent: Bool
    let cdpAvailable: Bool
    let tabsCount: Int
    let tabs: [SteamHookTab]?

    enum CodingKeys: String, CodingKey {
        case markerPresent = "marker_present"
        case cdpAvailable = "cdp_available"
        case tabsCount = "tabs_count"
        case tabs
    }
}

struct VaultSnapshotItem: Codable, Sendable, Identifiable, Equatable {
    let appid: Int
    let timestamp: Int
    let hash: String
    let bytes: Int
    let note: String?

    var id: String { "\(appid)_\(timestamp)_\(hash)" }

    var formattedDate: String {
        let sec = timestamp > 10_000_000_000 ? TimeInterval(timestamp) / 1000.0 : TimeInterval(timestamp)
        let date = Date(timeIntervalSince1970: sec)
        let df = DateFormatter()
        df.dateStyle = .short
        df.timeStyle = .short
        return df.string(from: date)
    }
}

struct VaultListResponse: Codable, Sendable, Equatable {
    let snapshots: [VaultSnapshotItem]
}

// MARK: - Modelli Depots & Builds Inspector (stile LuaTools)

struct DepotItem: Codable, Sendable, Identifiable, Equatable {
    let depotId: Int
    let name: String
    let os: String
    let gid: String
    let size: Int
    let sizeStr: String
    let hasKey: Bool
    let hasManifest: Bool
    let isDlc: Bool

    var id: Int { depotId }

    enum CodingKeys: String, CodingKey {
        case depotId = "depot_id"
        case name, os, gid, size
        case sizeStr = "size_str"
        case hasKey = "has_key"
        case hasManifest = "has_manifest"
        case isDlc = "is_dlc"
    }
}

struct GameDepotsResponse: Codable, Sendable, Identifiable, Equatable {
    let appid: Int
    let name: String
    let depotsCount: Int
    let depots: [DepotItem]

    var id: Int { appid }

    enum CodingKeys: String, CodingKey {
        case appid, name
        case depotsCount = "depots_count"
        case depots
    }
}

// MARK: - Risoluzione Eseguibile Nativo / Script

enum Locator {
    static func isSafeAuxiliaryBinary(_ candidate: URL) -> Bool {
        // PROTEZIONE RIGIDA CONTRO FORK BOMB / AUTO-INVOCAZIONE RICORSIVA:
        // Su filesystem APFS case-insensitive, MacLua e maclua puntano allo stesso file.
        // Se il candidato coincide (anche per maiuscole/minuscole) con l'eseguibile GUI corrente,
        // lo rifiutiamo categoricamente.
        if let currentExec = Bundle.main.executableURL {
            let p1 = candidate.standardizedFileURL.path
            let p2 = currentExec.standardizedFileURL.path
            if p1.caseInsensitiveCompare(p2) == .orderedSame {
                return false
            }
        }
        return FileManager.default.isExecutableFile(atPath: candidate.path)
    }

    static func nativeBinaryURL() -> URL? {
        if let root = ProcessInfo.processInfo.environment["MACLUA_ROOT"] {
            for name in ["maclua-cli", "maclua"] {
                let candidate = URL(fileURLWithPath: root).appending(path: name)
                if isSafeAuxiliaryBinary(candidate) { return candidate }
            }
        }
        // Cerca prima il binario ausiliario dedicato "maclua-cli" (non collidente con MacLua)
        if let bin = Bundle.main.url(forAuxiliaryExecutable: "maclua-cli"), isSafeAuxiliaryBinary(bin) {
            return bin
        }
        if let macosCLI = Bundle.main.executableURL?.deletingLastPathComponent().appending(path: "maclua-cli"),
           isSafeAuxiliaryBinary(macosCLI) {
            return macosCLI
        }
        let helpersCLI = Bundle.main.bundleURL.appending(path: "Contents/Helpers/maclua-cli")
        if isSafeAuxiliaryBinary(helpersCLI) {
            return helpersCLI
        }
        let helpers = Bundle.main.bundleURL.appending(path: "Contents/Helpers/maclua")
        if isSafeAuxiliaryBinary(helpers) {
            return helpers
        }
        var dir = Bundle.main.bundleURL
        for _ in 0..<5 {
            dir = dir.deletingLastPathComponent()
            let candidateCli = dir.appending(path: "rust/target/release/maclua-cli")
            if isSafeAuxiliaryBinary(candidateCli) { return candidateCli }
            let candidate = dir.appending(path: "rust/target/release/maclua")
            if isSafeAuxiliaryBinary(candidate) { return candidate }
            let direct = dir.appending(path: "maclua")
            if isSafeAuxiliaryBinary(direct) { return direct }
        }
        let devPath = URL(fileURLWithPath: "/Users/ciccioomazz/Desktop/MacLua/rust/target/release/maclua")
        if isSafeAuxiliaryBinary(devPath) { return devPath }
        return nil
    }

    static func scriptURL() -> URL {
        var candidates: [URL] = []
        if let root = ProcessInfo.processInfo.environment["MACLUA_ROOT"] {
            candidates.append(URL(fileURLWithPath: root).appending(path: "maclua.py"))
        }
        if let res = Bundle.main.resourceURL {
            candidates.append(res.appending(path: "backend/maclua.py"))
            candidates.append(res.appending(path: "maclua.py"))
        }
        var dir = Bundle.main.bundleURL
        for _ in 0..<5 {
            dir = dir.deletingLastPathComponent()
            candidates.append(dir.appending(path: "maclua.py"))
        }
        candidates.append(FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Desktop/MacLua/maclua.py"))
        for c in candidates where FileManager.default.isReadableFile(atPath: c.path) {
            return c
        }
        return candidates[0]
    }
}

// MARK: - Bridge Nativo verso maclua

struct MacLuaBridge: Sendable {
    let pythonURL: URL
    let scriptURL: URL
    let nativeBinaryURL: URL?
    var timeout: TimeInterval = 180

    static let live: MacLuaBridge = {
        let python = ["/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
            .map { URL(fileURLWithPath: $0) }
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
            ?? URL(fileURLWithPath: "/usr/bin/python3")
        return MacLuaBridge(
            pythonURL: python,
            scriptURL: Locator.scriptURL(),
            nativeBinaryURL: Locator.nativeBinaryURL()
        )
    }()

    init(pythonURL: URL, scriptURL: URL, nativeBinaryURL: URL? = nil, timeout: TimeInterval = 180) {
        self.pythonURL = pythonURL
        self.scriptURL = scriptURL
        self.nativeBinaryURL = nativeBinaryURL
        self.timeout = timeout
    }

    @discardableResult
    func run(_ args: [String], stdinInput: String? = nil) throws -> Data {
        let proc = Process()
        if let native = nativeBinaryURL {
            proc.executableURL = native
            proc.arguments = ["--json"] + args
        } else {
            proc.executableURL = pythonURL
            proc.arguments = [scriptURL.path, "--json"] + args
        }

        let outPipe = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = errPipe

        let inPipe = Pipe()
        if stdinInput != nil {
            proc.standardInput = inPipe
        }

        // Lettura concorrente per evitare deadlock se l'output supera la dimensione del buffer di pipe
        let group = DispatchGroup()
        nonisolated(unsafe) var outData = Data()
        nonisolated(unsafe) var errData = Data()

        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            outData = outPipe.fileHandleForReading.readDataToEndOfFile()
            group.leave()
        }

        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            errData = errPipe.fileHandleForReading.readDataToEndOfFile()
            group.leave()
        }

        try proc.run()

        if let stdinInput, let data = stdinInput.data(using: .utf8) {
            inPipe.fileHandleForWriting.write(data)
            try? inPipe.fileHandleForWriting.close()
        }

        let deadline = Date().addingTimeInterval(timeout)
        while proc.isRunning {
            if Date() > deadline {
                proc.terminate()
                throw BridgeError.timeout(args)
            }
            Thread.sleep(forTimeInterval: 0.05)
        }

        group.wait()

        // Controlla se stdout contiene un errore incapsulato dal backend
        if let backendErr = try? JSONDecoder().decode(BackendErrorPayload.self, from: outData),
           !backendErr.error.isEmpty {
            throw BridgeError.backend(backendErr.error)
        }

        if proc.terminationStatus != 0 && outData.isEmpty {
            let detail = String(data: errData, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            throw BridgeError.exit(code: proc.terminationStatus, args: args, detail: detail)
        }

        guard !outData.isEmpty else {
            throw BridgeError.emptyOutput(args)
        }

        return outData
    }

    func decode<T: Decodable>(_ type: T.Type, args: [String], stdinInput: String? = nil) throws -> T {
        let data = try run(args, stdinInput: stdinInput)
        let decoder = JSONDecoder()

        if let s = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
           let full = s.data(using: .utf8),
           let obj = try? decoder.decode(type, from: full) {
            return obj
        }

        let lines = data.split(separator: UInt8(ascii: "\n"))
        if let last = lines.last, let obj = try? decoder.decode(type, from: Data(last)) {
            return obj
        }

        throw BridgeError.badJSON(args)
    }

    // MARK: - Chiamate tipizzate

    func status() throws -> StatusAll {
        try decode(StatusAll.self, args: ["status"])
    }

    func appStatus(_ appid: Int) throws -> StatusApp {
        try decode(StatusApp.self, args: ["status", String(appid)])
    }

    func search(_ name: String) throws -> [SearchHit] {
        try decode([SearchHit].self, args: ["search", name])
    }

    func doctor() throws -> DoctorOut {
        try decode(DoctorOut.self, args: ["doctor"])
    }

    func verify(_ appid: Int) throws -> VerifyOut {
        try decode(VerifyOut.self, args: ["verify", String(appid)])
    }

    func config() throws -> ConfigOut {
        try decode(ConfigOut.self, args: ["config", "show"])
    }

    func setKey(_ key: String) throws {
        _ = try decode(ConfigOut.self, args: ["config", "set-key", "-"], stdinInput: key + "\n")
    }

    func clearKey() throws {
        _ = try decode(ConfigOut.self, args: ["config", "clear-key"])
    }

    func addApp(_ appid: Int) throws {
        _ = try run(["add", "--appid", String(appid)])
    }

    func removeApp(_ appid: Int) throws {
        _ = try run(["remove", String(appid)])
    }

    func ensureLicenses() throws -> EnsureOut {
        try decode(EnsureOut.self, args: ["ensure"])
    }

    func isAgentInstalled() -> Bool {
        let plist = FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Library/LaunchAgents/com.maclua.ensure.plist")
        return FileManager.default.fileExists(atPath: plist.path)
    }

    func setAgent(enabled: Bool) throws {
        _ = try run(["agent", enabled ? "install" : "remove"])
    }

    // MARK: - Funzionalità LuaTools (Collezioni, Steam Hook, Vault)

    func collectionsList(sort: String = "popular") throws -> CollectionsResponse {
        try decode(CollectionsResponse.self, args: ["collections", "--sort", sort, "list"])
    }

    func collectionShow(slug: String) throws -> CollectionItem {
        try decode(CollectionItem.self, args: ["collections", "show", slug])
    }

    func collectionAdd(slug: String) throws -> CollectionAddResult {
        try decode(CollectionAddResult.self, args: ["collections", "add", slug])
    }

    func steamHookStatus() throws -> SteamHookStatus {
        try decode(SteamHookStatus.self, args: ["steam-hook", "status"])
    }

    func enableSteamHook() throws {
        _ = try run(["steam-hook", "enable"])
    }

    func disableSteamHook() throws {
        _ = try run(["steam-hook", "disable"])
    }

    func vaultList(appid: Int? = nil) throws -> VaultListResponse {
        var args = ["vault", "list"]
        if let appid {
            args.append(String(appid))
        }
        return try decode(VaultListResponse.self, args: args)
    }

    func vaultRestore(appid: Int, timestamp: Int) throws {
        _ = try run(["vault", "restore", String(appid), String(timestamp)])
    }

    func depots(appid: Int) throws -> GameDepotsResponse {
        try decode(GameDepotsResponse.self, args: ["depots", String(appid)])
    }

    func injectSteamTabs() throws {
        _ = try run(["steam-hook", "inject"])
    }

    func isBridgeAgentInstalled() -> Bool {
        let plist = FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Library/LaunchAgents/dev.maclua.bridge.plist")
        return FileManager.default.fileExists(atPath: plist.path)
    }

    func ensureBridgeRunning() {
        Task.detached {
            let u = URL(string: "http://127.0.0.1:6767/health")!
            var req = URLRequest(url: u)
            req.timeoutInterval = 1.0
            if (try? await URLSession.shared.data(for: req)) != nil {
                return
            }
            let proc = Process()
            if let native = self.nativeBinaryURL {
                proc.executableURL = native
                proc.arguments = ["bridge", "serve"]
            } else {
                proc.executableURL = self.pythonURL
                proc.arguments = [self.scriptURL.path, "bridge", "serve"]
            }
            try? proc.run()
        }
    }
}

// MARK: - Errori

enum BridgeError: Error, LocalizedError, Equatable {
    case timeout([String])
    case exit(code: Int32, args: [String], detail: String)
    case backend(String)
    case emptyOutput([String])
    case badJSON([String])

    var errorDescription: String? {
        switch self {
        case .timeout(let a):
            return "maclua non risponde (\(a.joined(separator: " ")))"
        case .backend(let msg):
            return msg
        case .exit(_, let a, let detail):
            let head = detail.split(separator: "\n").last.map(String.init) ?? detail
            return "\(a.joined(separator: " ")): \(head.isEmpty ? "errore del processo" : head)"
        case .emptyOutput(let a):
            return "Nessuna risposta da maclua (\(a.joined(separator: " ")))"
        case .badJSON(let a):
            return "Risposta non valida dal backend (\(a.joined(separator: " ")))"
        }
    }
}
