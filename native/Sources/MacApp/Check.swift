import Foundation

// Harness di verifica su richiesta (`MACLUA_CHECK=1`)

nonisolated(unsafe) private var passed = 0
nonisolated(unsafe) private var failed: [String] = []

private func expect(_ condition: Bool, _ label: String,
                    file: StaticString = #file, line: UInt = #line) {
    if condition { passed += 1 } else { failed.append("\(label) [\(file):\(line)]") }
}

private func expectEqual<T: Equatable>(_ got: T?, _ want: T?, _ label: String,
                                       file: StaticString = #file, line: UInt = #line) {
    if got == want { passed += 1 } else {
        failed.append("\(label): atteso \(String(describing: want)), ottenuto \(String(describing: got)) [\(file):\(line)]")
    }
}

private func expectThrows<T>(_ label: String, _ body: () throws -> T) {
    do {
        _ = try body()
        failed.append("\(label): attesa eccezione, nessun throw")
    } catch { passed += 1 }
}

/// Stub eseguibile che stampa `output` su stdout ed esce con `code`.
private func stubBridge(output: String, code: Int32 = 0) throws -> MacLuaBridge {
    let dir = FileManager.default.temporaryDirectory
    let sh = dir.appending(path: "stub-\(Int.random(in: 0..<1_000_000)).sh")
    let script = "#!/bin/sh\nprintf '%s' '\(output)'\nexit \(code)\n"
    try script.write(to: sh, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755],
                                         ofItemAtPath: sh.path)
    return MacLuaBridge(pythonURL: sh, scriptURL: dir.appending(path: "x"))
}

// MARK: - Bridge & Decoding

func testStatusDecoding() throws {
    let b = try stubBridge(output: """
    {"apps": [1332010], "depots": 2, "ok": true, "missing": {"appids": [], "depots": []}, "error": null}
    """)
    let st = try b.status()
    expectEqual(st.apps, [1332010], "status.apps")
    expect(st.ok, "status.ok")
}

func testSearchDecoding() throws {
    let b = try stubBridge(output: #"[{"appid": 1332010, "name": "Stray"}]"#)
    let hits = try b.search("stray")
    expectEqual(hits.count, 1, "search.count")
    expectEqual(hits.first?.appid, 1332010, "search.appid")
}

func testVerifyDecoding() throws {
    let b = try stubBridge(output: #"{"appid": 1332010, "bad": []}"#)
    expect(try b.verify(1332010).bad.isEmpty, "verify.bad vuoto")
}

func testDoctorDecoding() throws {
    let b = try stubBridge(output: """
    {"ok": true, "checks": [{"name": "python", "ok": true, "detail": "3.9"}]}
    """)
    let d = try b.doctor()
    expect(d.ok, "doctor.ok")
    expectEqual(d.checks.first?.name, "python", "doctor.nome")
}

func testBackendErrorPayloadThrowsBackendError() throws {
    let b = try stubBridge(output: #"{"error": "serve una chiave API"}"#, code: 2)
    do {
        _ = try b.decode(StatusAll.self, args: ["status"])
        failed.append("backend error payload non ha sollevato eccezione")
    } catch let BridgeError.backend(msg) {
        expectEqual(msg, "serve una chiave API", "messaggio errore backend")
    } catch {
        failed.append("atteso BridgeError.backend ma ricevuto \(error)")
    }
}

func testNonZeroExitWithEmptyOutputThrows() throws {
    let b = try stubBridge(output: "", code: 3)
    expectThrows("exit != 0 con output vuoto solleva") {
        _ = try b.run(["test"])
    }
}

func testBadJSONThrows() throws {
    let b = try stubBridge(output: "not json at all")
    expectThrows("output non JSON solleva") {
        _ = try b.decode(StatusAll.self, args: ["test"])
    }
}

func testPrettyJSONAccepted() throws {
    let b = try stubBridge(output: """
    {
      "apps": [1],
      "depots": 1,
      "ok": true,
      "missing": {"appids": [], "depots": []},
      "error": null
    }
    """)
    expectEqual(try b.status().apps, [1], "pretty json accettato")
}

// MARK: - Purezza & Funzioni Ausiliarie

func testSteamURL() {
    expectEqual(steamInstallURL(appid: 1671210), "steam://install/1671210", "steam url")
}

func testProgressLineParsing() {
    let p = parseProgress(#"{"mb": 12.5, "total": 100, "pct": 12}"#)
    expectEqual(p?.mb, 12.5, "progress.mb")
    expectEqual(p?.totalMB, 100, "progress.total")
    expectEqual(p?.fraction, 0.125, "progress.frazione")
    expect(parseProgress("  12.5 MB") == nil, "progress: ignora riga umana")
    expect(parseProgress("not json") == nil, "progress: ignora spazzatura")
    expect(parseProgress(#"{"mb": 5}"#)?.fraction == nil, "progress: totale assente")
}

func testStateDerivation() throws {
    let b = try stubBridge(output: #"""
    {"appid": 10, "managed": true, "appinfo_depots": 1, "has_appmanifest": true,
     "versions": {"installed": {"11": "9001"}, "live": {"11": "9002"}, "available": true}}
    """#)
    let app = try b.appStatus(10)
    expectEqual(app.state, .updateAvailable, "stato.update")
    expectEqual(app.state.label, "Aggiornamento disponibile", "stato.label")
}

func testNotInstalledWhenNoManifest() throws {
    let b = try stubBridge(output: #"""
    {"appid": 10, "managed": true, "appinfo_depots": 1, "has_appmanifest": false,
     "versions": null}
    """#)
    expectEqual(try b.appStatus(10).state, .notInstalled, "stato.notInstalled")
}

// MARK: - Catalogo

func testStoreNameParsing() {
    let json = #"{"1332010":{"success":true,"data":{"type":"game","name":"Stray","short_description":"Gatto randagio"}}}"#
    expectEqual(Catalog.parseName(Data(json.utf8), appid: 1332010), "Stray", "nome store")
    let meta = Catalog.parseMeta(Data(json.utf8), appid: 1332010)
    expectEqual(meta?.name, "Stray", "meta.name")
    expectEqual(meta?.shortDescription, "Gatto randagio", "meta.shortDescription")
    expect(Catalog.parseName(Data("null".utf8), appid: 1332010) == nil, "nome: null")
    expect(Catalog.parseName(Data("{}".utf8), appid: 1332010) == nil, "nome: assente")
}

func testArtworkURLs() {
    expectEqual(Art.hero(1671210).first?.absoluteString,
                "https://cdn.akamai.steamstatic.com/steam/apps/1671210/library_hero.jpg",
                "art.hero primo")
    expectEqual(Art.tile(1671210).count, 2, "art.tile fallback")
    expectEqual(Art.tile(1671210).last?.absoluteString,
                "https://cdn.akamai.steamstatic.com/steam/apps/1671210/capsule_616x353.jpg",
                "art.tile ultimo")
}

func testLocatorHonoursEnvironment() throws {
    let dir = FileManager.default.temporaryDirectory
        .appending(path: "maclua-root-\(Int.random(in: 0..<1_000_000))")
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let script = dir.appending(path: "maclua.py")
    try "print(1)".write(to: script, atomically: true, encoding: .utf8)
    setenv("MACLUA_ROOT", dir.path, 1)
    defer { unsetenv("MACLUA_ROOT") }
    expectEqual(Locator.scriptURL(), script, "locator rispetta MACLUA_ROOT")
}

func testBackendIsReachable() throws {
    expect(FileManager.default.isReadableFile(atPath: MacLuaBridge.live.scriptURL.path),
           "maclua.py trovato")
    expect(FileManager.default.isExecutableFile(atPath: MacLuaBridge.live.pythonURL.path),
           "python3 trovato")
}

func testCollectionsDecoding() throws {
    let b = try stubBridge(output: """
    {"collections": [{"id": "sonic", "title": "Sonic Pack", "cover": "https://img.jpg", "appCount": 5, "author": "User", "apps": [123, 456]}], "cached": false, "stale": false}
    """)
    let resp = try b.collectionsList()
    expectEqual(resp.collections.count, 1, "collections.count")
    expectEqual(resp.collections.first?.title, "Sonic Pack", "collections.title")
    expectEqual(resp.collections.first?.apps?.count, 2, "collections.apps.count")
}

func testSteamHookStatusDecoding() throws {
    let b = try stubBridge(output: """
    {"marker_present": true, "cdp_available": true, "tabs_count": 4, "tabs": []}
    """)
    let st = try b.steamHookStatus()
    expect(st.markerPresent, "hook.markerPresent")
    expect(st.cdpAvailable, "hook.cdpAvailable")
    expectEqual(st.tabsCount, 4, "hook.tabsCount")
}

func testVaultDecoding() throws {
    let b = try stubBridge(output: """
    {"snapshots": [{"appid": 322170, "timestamp": 1728551234000, "hash": "abc12345", "bytes": 80, "note": "v1"}]}
    """)
    let resp = try b.vaultList()
    expectEqual(resp.snapshots.count, 1, "vault.count")
    expectEqual(resp.snapshots.first?.appid, 322170, "vault.appid")
}

func testBackgroundModels() {
    let types = CustomBackgroundType.allCases
    expect(types.contains(.gif), "bg.gif supportato")
    expect(types.contains(.image), "bg.image supportato")
    expect(types.contains(.none), "bg.none supportato")

    let fit = BackgroundFitMode.allCases
    expect(fit.contains(.fill), "bg.fit.fill supportato")
    expect(fit.contains(.fit), "bg.fit.fit supportato")
}

// MARK: - Esecuzione Check

func testDepotsDecoding() throws {
    let b = try stubBridge(output: """
    {
      "appid": 322170,
      "name": "Geometry Dash",
      "depots_count": 1,
      "depots": [
        {
          "depot_id": 322172,
          "name": "Geometry Dash Mac",
          "os": "macos",
          "gid": "8780295549609362522",
          "size": 334510594,
          "size_str": "334.5 MB",
          "has_key": true,
          "has_manifest": true,
          "is_dlc": false
        }
      ]
    }
    """)
    let res = try b.depots(appid: 322170)
    expectEqual(res.appid, 322170, "depots.appid")
    expectEqual(res.depots.count, 1, "depots.count")
    expectEqual(res.depots.first?.depotId, 322172, "depots.first.id")
    expectEqual(res.depots.first?.hasKey, true, "depots.first.hasKey")
}

func runChecks() -> Int32 {
    let checks: [(String, () throws -> Void)] = [
        ("bridge: status", testStatusDecoding),
        ("bridge: search", testSearchDecoding),
        ("bridge: verify", testVerifyDecoding),
        ("bridge: doctor", testDoctorDecoding),
        ("bridge: payload errore backend", testBackendErrorPayloadThrowsBackendError),
        ("bridge: exit != 0 con output vuoto", testNonZeroExitWithEmptyOutputThrows),
        ("bridge: JSON non valido", testBadJSONThrows),
        ("bridge: JSON multi-riga", testPrettyJSONAccepted),
        ("bridge: collezioni community", testCollectionsDecoding),
        ("bridge: stato hook steam", testSteamHookStatusDecoding),
        ("bridge: vault backup", testVaultDecoding),
        ("bridge: ispettore depot", testDepotsDecoding),
        ("motore sfondo: tipi e modalita", testBackgroundModels),
        ("puro: steam url", testSteamURL),
        ("puro: riga progresso", testProgressLineParsing),
        ("modello: stato derivato", testStateDerivation),
        ("modello: senza manifest", testNotInstalledWhenNoManifest),
        ("catalogo: nome e meta dallo store", testStoreNameParsing),
        ("catalogo: url artwork", testArtworkURLs),
        ("seam: MACLUA_ROOT", testLocatorHonoursEnvironment),
        ("seam: backend raggiungibile", testBackendIsReachable),
    ]

    var crashed = 0
    for (name, check) in checks {
        do {
            try check()
            print("  ok   \(name)")
        } catch {
            crashed += 1
            failed.append("\(name): eccezione \(error)")
            print("  ERR  \(name): \(error)")
        }
    }
    let total = failed.count + crashed
    print("\nMacAppCheck — \(passed) verifiche superate, \(total) fallite\n")
    for f in failed { print("  x \(f)") }
    return total == 0 ? 0 : 1
}
