import Foundation

struct AppMeta: Codable, Sendable {
    let name: String
    let shortDescription: String?
    var type: String? = "game"
    var isDLC: Bool = false
    var parentAppId: Int? = nil
    var parentName: String? = nil
}

@MainActor
final class Catalog {
    static let shared = Catalog()

    private var cache: [Int: AppMeta] = [:]
    private let cacheURL: URL

    init() {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Library/Caches/MacLua")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        cacheURL = dir.appending(path: "names.json")
        loadDiskCache()
    }

    private func loadDiskCache() {
        guard let data = try? Data(contentsOf: cacheURL),
              let disk = try? JSONDecoder().decode([String: AppMeta].self, from: data) else {
            return
        }
        for (k, v) in disk {
            if let id = Int(k) {
                cache[id] = v
            }
        }
    }

    private func saveDiskCache() {
        var strMap: [String: AppMeta] = [:]
        for (k, v) in cache {
            strMap[String(k)] = v
        }
        if let data = try? JSONEncoder().encode(strMap) {
            try? data.write(to: cacheURL, options: .atomic)
        }
    }

    func name(_ appid: Int) -> String? {
        cache[appid]?.name
    }

    func shortDescription(_ appid: Int) -> String? {
        cache[appid]?.shortDescription
    }

    func metaOrFetch(_ appid: Int) async -> AppMeta {
        if let m = cache[appid] { return m }
        if let m = await Self.fetchMeta(appid) {
            cache[appid] = m
            saveDiskCache()
            return m
        }
        let fallback = AppMeta(name: "App \(appid)", shortDescription: nil)
        cache[appid] = fallback
        return fallback
    }

    func resolve(_ appids: [Int]) async -> [Int: String] {
        let missing = Set(appids).filter { cache[$0] == nil }
        if !missing.isEmpty {
            await withTaskGroup(of: (Int, AppMeta?).self) { group in
                for aid in missing {
                    group.addTask {
                        let meta = await Self.fetchMeta(aid)
                        return (aid, meta)
                    }
                }
                for await (aid, meta) in group {
                    if let meta {
                        cache[aid] = meta
                    }
                }
            }
            saveDiskCache()
        }
        return appids.reduce(into: [:]) { acc, id in
            acc[id] = cache[id]?.name ?? "App \(id)"
        }
    }

    nonisolated static func fetchMeta(_ appid: Int) async -> AppMeta? {
        guard let url = URL(string: "https://store.steampowered.com/api/appdetails?appids=\(appid)&filters=basic") else {
            return nil
        }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return parseMeta(data, appid: appid)
        } catch {
            return nil
        }
    }

    nonisolated static func parseMeta(_ data: Data, appid: Int) -> AppMeta? {
        struct Resp: Decodable {
            let data: Payload?
            struct Payload: Decodable {
                let name: String?
                let short_description: String?
                let type: String?
                let fullgame: FullGame?
                struct FullGame: Decodable {
                    let appid: String?
                    let name: String?
                }
            }
        }
        guard let root = try? JSONDecoder().decode([String: Resp].self, from: data),
              let payload = root[String(appid)]?.data,
              let name = payload.name else {
            return nil
        }
        let isDlc = payload.type == "dlc" || payload.fullgame != nil
        let parentId = Int(payload.fullgame?.appid ?? "")
        let parentName = payload.fullgame?.name
        return AppMeta(name: name, shortDescription: payload.short_description,
                       type: payload.type, isDLC: isDlc, parentAppId: parentId, parentName: parentName)
    }

    nonisolated static func parseName(_ data: Data, appid: Int) -> String? {
        parseMeta(data, appid: appid)?.name
    }
}

// MARK: - Artwork Steam

enum Art {
    private static let cdn = "https://cdn.akamai.steamstatic.com/steam/apps"

    static func hero(_ appid: Int) -> [URL] {
        [url(appid, "library_hero.jpg"), url(appid, "capsule_616x353.jpg"), url(appid, "header.jpg")]
            .compactMap { $0 }
    }

    static func tile(_ appid: Int) -> [URL] {
        [url(appid, "header.jpg"), url(appid, "capsule_616x353.jpg")]
            .compactMap { $0 }
    }

    static func capsule(_ appid: Int) -> [URL] {
        [url(appid, "capsule_616x353.jpg"), url(appid, "header.jpg")]
            .compactMap { $0 }
    }

    static func poster(_ appid: Int) -> [URL] {
        [url(appid, "library_600x900.jpg"), url(appid, "header.jpg")]
            .compactMap { $0 }
    }

    private static func url(_ appid: Int, _ name: String) -> URL? {
        URL(string: "\(cdn)/\(appid)/\(name)")
    }
}
