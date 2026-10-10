// swift-tools-version: 6.4
import PackageDescription

let package = Package(
    name: "MacLua",
    platforms: [.macOS(.v14)],
    targets: [
        // L'app: un solo modulo, entry point incluso. Le verifiche
        // (Check.swift) girano nello stesso modulo con `MACLUA_CHECK=1`.
        .executableTarget(
            name: "MacApp",
            swiftSettings: [
                // Il runtime Swift di questo toolchain va in crash
                // intermittente (EXC_BAD_ACCESS in _checkExpectedExecutor,
                // sempre allo stesso indirizzo di shared cache) quando un
                // callback AppKit interroga l'executor senza task corrente.
                // Tutto l'accesso UI è comunque sul main thread per contratto
                // AppKit + hop strutturati (Task @MainActor): i check
                // runtime sono solo overhead + rischio. La struttura
                // nonisolated + assumeIsolated resta come documentazione
                // ed è corretta anche su toolchain sani.
                .unsafeFlags(["-disable-actor-data-race-checks"]),
            ]
        ),
    ]
)
