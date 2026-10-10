import AppKit

// Harness di verifica su richiesta: `MACLUA_CHECK=1 .build/debug/MacApp`
if ProcessInfo.processInfo.environment["MACLUA_CHECK"] != nil {
    exit(runChecks())
}

MacLuaApp.main()
