import AppKit

enum SteamControl {
    static let steamBundleId = "com.valvesoftware.steam"

    static var isSteamRunning: Bool {
        !NSRunningApplication.runningApplications(withBundleIdentifier: steamBundleId).isEmpty
    }

    @MainActor
    static func openInstall(appid: Int) {
        if let url = URL(string: "steam://install/\(appid)") {
            NSWorkspace.shared.open(url)
        }
    }

    @MainActor
    static func launchGame(appid: Int) {
        if let url = URL(string: "steam://run/\(appid)") {
            NSWorkspace.shared.open(url)
        }
    }

    @MainActor
    static func openGamePage(appid: Int) {
        if let url = URL(string: "steam://nav/games/details/\(appid)") {
            NSWorkspace.shared.open(url)
        }
    }

    @MainActor
    static func restartSteam() async {
        let apps = NSRunningApplication.runningApplications(withBundleIdentifier: steamBundleId)
        if !apps.isEmpty {
            for app in apps {
                app.terminate()
            }

            // Attende la chiusura graduale per 3 secondi
            let deadline = Date().addingTimeInterval(3.0)
            while Date() < deadline {
                if NSRunningApplication.runningApplications(withBundleIdentifier: steamBundleId).isEmpty {
                    break
                }
                try? await Task.sleep(nanoseconds: 200_000_000)
            }

            // Forza la chiusura se ancora aperto
            for app in NSRunningApplication.runningApplications(withBundleIdentifier: steamBundleId) {
                app.forceTerminate()
            }
            try? await Task.sleep(nanoseconds: 300_000_000)
        }

        // Riapre Steam assicurando il flag di debug CEF
        if let steamAppURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: steamBundleId) {
            let conf = NSWorkspace.OpenConfiguration()
            conf.arguments = ["-cef-enable-debugging"]
            _ = try? await NSWorkspace.shared.openApplication(at: steamAppURL, configuration: conf)
        } else {
            let pOpen = Process()
            pOpen.executableURL = URL(fileURLWithPath: "/usr/bin/open")
            pOpen.arguments = ["-a", "Steam", "--args", "-cef-enable-debugging"]
            try? pOpen.run()
        }
    }
}

func steamInstallURL(appid: Int) -> String {
    "steam://install/\(appid)"
}
