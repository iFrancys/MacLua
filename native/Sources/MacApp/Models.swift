import Foundation

// MARK: - Modelli Dati Backend

struct Versions: Codable, Sendable, Equatable {
    let installed: [String: String]
    let live: [String: String]
    let available: Bool
}

struct StatusApp: Codable, Sendable, Identifiable, Equatable {
    let appid: Int
    let managed: Bool
    let appinfoDepots: Int
    let hasAppmanifest: Bool
    let versions: Versions?
    var id: Int { appid }

    enum CodingKeys: String, CodingKey {
        case appid, managed, versions
        case appinfoDepots = "appinfo_depots"
        case hasAppmanifest = "has_appmanifest"
    }

    enum State: String, Sendable, Equatable, CaseIterable {
        case notInstalled
        case updateAvailable
        case installed

        var label: String {
            switch self {
            case .notInstalled: return "Da installare"
            case .updateAvailable: return "Aggiornamento disponibile"
            case .installed: return "Installato"
            }
        }
        
        var shortLabel: String {
            switch self {
            case .notInstalled: return "Da scaricare"
            case .updateAvailable: return "Aggiorna"
            case .installed: return "Pronto"
            }
        }
    }

    var state: State {
        if !hasAppmanifest { return .notInstalled }
        if versions?.available == true { return .updateAvailable }
        return .installed
    }
}

struct StatusAll: Codable, Sendable, Equatable {
    struct Missing: Codable, Sendable, Equatable {
        let appids: [Int]
        let depots: [Int]
    }
    let apps: [Int]
    let depots: Int
    let ok: Bool
    let missing: Missing
    let error: String?
}

struct VerifyOut: Codable, Sendable, Equatable {
    let appid: Int
    let bad: [String]
}

struct SearchHit: Codable, Sendable, Identifiable, Equatable {
    let appid: Int
    let name: String
    var isDLC: Bool? = false
    var parentAppId: Int? = nil
    var parentName: String? = nil
    var id: Int { appid }
}

struct DoctorCheck: Codable, Sendable, Identifiable, Equatable {
    let name: String
    let ok: Bool
    let detail: String
    var id: String { name }
}

struct DoctorOut: Codable, Sendable, Equatable {
    let ok: Bool
    let checks: [DoctorCheck]
}

struct ConfigOut: Codable, Sendable, Equatable {
    let hasKey: Bool
    let source: String?

    enum CodingKeys: String, CodingKey {
        case hasKey = "has_key"
        case source
    }
}

struct EnsureOut: Codable, Sendable, Equatable {
    struct AppDepotDiff: Codable, Sendable, Equatable {
        let appids: [Int]
        let depots: [Int]
    }
    let apps: [Int]
    let staged: [String]
    let keys: Int
    let added: AppDepotDiff
    let removed: AppDepotDiff
}

struct BackendErrorPayload: Codable, Sendable {
    let error: String
}
