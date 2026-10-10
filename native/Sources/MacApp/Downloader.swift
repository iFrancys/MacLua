import Foundation

/// Modello per rappresentare un download/update attivo
struct DownloadItem: Identifiable, Sendable {
    let appid: Int
    var title: String
    var mb: Double = 0
    var totalMB: Double = 0
    var fraction: Double = 0
    var statusText: String = "Inizializzazione..."
    var isCompleted: Bool = false
    var error: String?

    var id: Int { appid }
}

@Observable @MainActor
final class Downloader {
    static let shared = Downloader()

    private(set) var activeAppId: Int?
    private(set) var downloads: [Int: DownloadItem] = [:]
    private var processes: [Int: Process] = [:]

    var isAnyRunning: Bool {
        activeAppId != nil
    }

    func isRunning(appid: Int) -> Bool {
        activeAppId == appid
    }

    func currentItem(for appid: Int) -> DownloadItem? {
        downloads[appid]
    }

    func start(appid: Int, title: String, onCompletion: (@Sendable () -> Void)? = nil) {
        guard !isRunning(appid: appid) else { return }

        var item = DownloadItem(appid: appid, title: title)
        item.statusText = "Preparazione download..."
        downloads[appid] = item
        activeAppId = appid

        let bridge = MacLuaBridge.live
        let proc = Process()
        if let native = bridge.nativeBinaryURL {
            proc.executableURL = native
            proc.arguments = ["--json", "update", String(appid), "-j", "8"]
        } else {
            proc.executableURL = bridge.pythonURL
            proc.arguments = [bridge.scriptURL.path, "--json", "update", String(appid), "-j", "8"]
        }

        let pipe = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = errPipe

        do {
            try proc.run()
        } catch {
            item.statusText = "Errore di avvio"
            item.error = error.localizedDescription
            downloads[appid] = item
            activeAppId = nil
            return
        }

        processes[appid] = proc

        let fd = dup(pipe.fileHandleForReading.fileDescriptor)
        let pumpQueue = DispatchQueue(label: "dev.maclua.downloader.pump", qos: .utility)

        pumpQueue.async {
            let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: false)
            var rest = Data()
            while true {
                guard let chunk = try? handle.read(upToCount: 64 * 1024), !chunk.isEmpty else { break }
                rest.append(chunk)
                while let nl = rest.firstIndex(of: UInt8(ascii: "\n")) {
                    let lineData = rest[..<nl]
                    rest = rest[rest.index(after: nl)...]
                    if let line = String(data: lineData, encoding: .utf8),
                       let pr = parseProgress(line) {
                        Task { @MainActor in
                            if var cur = Downloader.shared.downloads[appid] {
                                cur.mb = pr.mb
                                let tot = pr.totalMB
                                if tot > 0 {
                                    cur.totalMB = tot
                                    let frac = pr.fraction ?? min(1.0, pr.mb / tot)
                                    cur.fraction = max(0.0, min(1.0, frac))
                                    cur.statusText = String(format: "%.1f MB / %.1f MB (%d%%)", pr.mb, tot, Int(cur.fraction * 100))
                                } else {
                                    cur.totalMB = 0
                                    cur.fraction = 0
                                    cur.statusText = String(format: "Scaricati %.1f MB...", pr.mb)
                                }
                                Downloader.shared.downloads[appid] = cur
                            }
                        }
                    }
                }
            }
            close(fd)
        }

        DispatchQueue.global(qos: .utility).async {
            proc.waitUntilExit()
            let exitCode = proc.terminationStatus
            let errOutput = String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""

            Task { @MainActor in
                self.processes.removeValue(forKey: appid)
                if self.activeAppId == appid {
                    self.activeAppId = nil
                }

                if var cur = self.downloads[appid] {
                    if exitCode == 0 {
                        cur.isCompleted = true
                        cur.fraction = 1.0
                        cur.statusText = "Pronto su Steam! Puoi avviarlo direttamente da Steam."
                        Task {
                            await SteamControl.restartSteam()
                        }
                    } else if exitCode == 15 || exitCode == 9 {
                        cur.statusText = "Download annullato"
                    } else {
                        cur.statusText = "Interrotto (errore \(exitCode))"
                        cur.error = errOutput.trimmingCharacters(in: .whitespacesAndNewlines)
                    }
                    self.downloads[appid] = cur
                }
                onCompletion?()
            }
        }
    }

    func cancel(appid: Int) {
        if let proc = processes[appid] {
            proc.terminate()
            processes.removeValue(forKey: appid)
        }
        if activeAppId == appid {
            activeAppId = nil
        }
        if var cur = downloads[appid] {
            cur.statusText = "Annullato dall'utente"
            downloads[appid] = cur
        }
    }
}
