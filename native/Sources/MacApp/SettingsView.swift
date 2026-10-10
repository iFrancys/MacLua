import SwiftUI

struct SettingsView: View {
    @Environment(AppStore.self) private var store
    @Environment(AppearanceSettings.self) private var appearance

    @UIState var apiKeyInput = ""
    @UIState var isSavingKey = false
    @UIState var isClearingKey = false
    @UIState var isRepairingLicenses = false
    @UIState var showAdvancedDiagnostics = false

    // State per nuove feature LuaTools (Steam Hook, Sfondo, DoH, Vault)
    @UIState var hookStatus: SteamHookStatus? = nil
    @UIState var isTogglingHook = false
    @UIState var isRestartingSteam = false
    @UIState var dnsMode: String = "auto"
    @UIState var vaultSnapshots: [VaultSnapshotItem] = []
    @UIState var isLoadingVault = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                // Header
                VStack(alignment: .leading, spacing: 4) {
                    Text("Impostazioni")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Text("Personalizza l'interfaccia grafica e gestisci le integrazioni con Steam.")
                        .font(.system(size: 13))
                        .foregroundStyle(appearance.theme.secondaryText)
                }

                // MARK: - 1. Sorgente & Account
                sourceSection

                // MARK: - 2. Integrazione Steam Client & Hook CEF
                steamSection

                // MARK: - 3. Personalizzazione Aspetto & Sfondi GIF
                appearanceCustomizationSection

                // MARK: - 4. Rete, Resilienza DNS & Lua Vault (LuaTools)
                networkAndVaultSection

                // MARK: - 5. Stato Sistema Semplificato
                systemHealthSection
            }
            .padding(CGFloat(appearance.density.padding))
        }
        .onAppear {
            Task {
                await store.checkApiKey()
                await store.loadDoctor()
                loadHookStatus()
                loadVault()
            }
        }
    }

    // MARK: - Sezione Sorgente

    private var sourceSection: some View {
        SteamCard {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Image(systemName: "key.fill")
                        .foregroundStyle(appearance.accentColor)
                    Text("Sorgente Lua & Chiave API")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                    if store.hasApiKey {
                        HStack(spacing: 5) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(Color.green)
                            Text("Configurata")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(Color.green)
                        }
                    } else {
                        Text("Non configurata")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(Color.orange)
                    }
                }

                Text("La chiave API permette al tool di interrogare la sorgente e prelevare i file .lua e i relativi manifest in automatico. Viene salvata su file con permessi 0600 protetti.")
                    .font(.system(size: 12))
                    .foregroundStyle(appearance.theme.secondaryText)

                HStack(spacing: 10) {
                    SecureField(store.hasApiKey ? "•••••••••••••••••••• (Inserisci nuova per sostituire)" : "Incolla qui la chiave API...", text: $apiKeyInput)
                        .textFieldStyle(.plain)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.black.opacity(0.2))
                        .clipShape(RoundedRectangle(cornerRadius: 8))

                    SteamButtonView(
                        title: "Salva",
                        icon: "square.and.arrow.down",
                        variant: .accent,
                        isLoading: isSavingKey
                    ) {
                        saveKey()
                    }
                    .disabled(apiKeyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    if store.hasApiKey {
                        SteamButtonView(
                            title: "Rimuovi",
                            icon: "trash",
                            variant: .destructive,
                            isLoading: isClearingKey
                        ) {
                            clearKey()
                        }
                    }
                }
            }
        }
    }

    // MARK: - Sezione Steam

    private var steamSection: some View {
        @Bindable var appSettings = appearance

        return SteamCard {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Image(systemName: "gamecontroller.fill")
                        .foregroundStyle(appearance.accentColor)
                    Text("Integrazione con Steam")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                }

                // Sottosezione Integrazione CEF Client Steam (LuaTools-style)
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Integrazione Client Steam (In-Client UI)")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(appearance.theme.primaryText)
                            Text("Inietta i pulsanti MacLua direttamente nelle pagine dello Store e della Libreria di Steam.")
                                .font(.system(size: 12))
                                .foregroundStyle(appearance.theme.secondaryText)
                        }
                        Spacer()

                        let isHooked = hookStatus?.markerPresent == true && hookStatus?.cdpAvailable == true
                        HStack(spacing: 5) {
                            Circle()
                                .fill(isHooked ? Color.green : Color.orange)
                                .frame(width: 8, height: 8)
                            Text(isHooked ? "Attivo (CEF connesso)" : "Non attivo")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(isHooked ? Color.green : Color.orange)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(isHooked ? Color.green.opacity(0.12) : Color.orange.opacity(0.12))
                        .clipShape(Capsule())
                    }

                    HStack(spacing: 10) {
                        let isHooked = hookStatus?.markerPresent == true
                        SteamButtonView(
                            title: isHooked ? "Disabilita Hook (Ripristina originale)" : "Abilita Hook Steam",
                            icon: isHooked ? "xmark.circle" : "bolt.circle.fill",
                            variant: isHooked ? .secondary : .accent,
                            isLoading: isTogglingHook
                        ) {
                            toggleHook(enable: !isHooked)
                        }

                        SteamButtonView(
                            title: isRestartingSteam ? "Riavvio in corso..." : "Riavvia Steam",
                            icon: "arrow.clockwise",
                            variant: .secondary,
                            isLoading: isRestartingSteam
                        ) {
                            restartSteam()
                        }
                    }
                }

                Divider().background(appearance.theme.cardBorder)

                // Opzione Riavvia Steam su add (Attiva di default)
                Toggle(isOn: $appSettings.restartSteamOnAdd) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Riavvia Steam automaticamente dopo l'aggiunta di un gioco")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(appearance.theme.primaryText)
                        Text("Attiva di default. Chiude e riapre il client Steam per registrare le licenze senza doverlo riavviare manualmente.")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                    }
                }
                .toggleStyle(.checkbox)

                Divider().background(appearance.theme.cardBorder)

                // LaunchAgent toggle
                Toggle(isOn: Binding(
                    get: { store.isAgentEnabled },
                    set: { enabled in
                        Task { await store.toggleAgent(enabled: enabled) }
                    }
                )) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Riapplica licenze e manifest all'avvio del Mac (LaunchAgent)")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(appearance.theme.primaryText)
                        Text("Previene la perdita delle licenze quando il client Steam si aggiorna in automatico.")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                    }
                }
                .toggleStyle(.checkbox)

                Divider().background(appearance.theme.cardBorder)

                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Sincronizzazione manuale licenze")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(appearance.theme.primaryText)
                        Text("Riapplica packageinfo.vdf, risincronizza tutti i manifest e riavvia Steam.")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                    }
                    Spacer()
                    SteamButtonView(
                        title: isRepairingLicenses ? "Riparazione..." : "Ripara licenze ora",
                        icon: "wrench.and.screwdriver",
                        variant: .primaryGreen,
                        isLoading: isRepairingLicenses
                    ) {
                        repairLicenses()
                    }
                }
            }
        }
    }

    // MARK: - Sezione Personalizzazione Aspetto

    private var appearanceCustomizationSection: some View {
        @Bindable var appSettings = appearance

        return SteamCard {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Image(systemName: "paintpalette.fill")
                        .foregroundStyle(appearance.accentColor)
                    Text("Personalizzazione Interfaccia")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                    Button("Ripristina predefiniti") {
                        appearance.resetToDefaults()
                    }
                    .font(.system(size: 12))
                    .buttonStyle(.plain)
                    .foregroundStyle(appearance.accentColor)
                }

                // 1. Tema di sfondo
                VStack(alignment: .leading, spacing: 8) {
                    Text("Palette e Tema Sfondo")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(appearance.theme.primaryText)

                    Picker("", selection: $appSettings.theme) {
                        ForEach(AppThemePreset.allCases) { t in
                            Text(t.label).tag(t)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                // 2. Stile di resa sfondo
                VStack(alignment: .leading, spacing: 8) {
                    Text("Effetto Sfondo")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(appearance.theme.primaryText)

                    Picker("", selection: $appSettings.bgStyle) {
                        ForEach(BackgroundStyle.allCases) { b in
                            Text(b.label).tag(b)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                // Sfondo Personalizzato (Immagini e GIF Animate - Richiesta Utente)
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Sfondo Personalizzato (Immagini o GIF Animate)")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(appearance.theme.primaryText)
                            Text("Importa una foto o una GIF animata per personalizzare l'aspetto dell'app.")
                                .font(.system(size: 12))
                                .foregroundStyle(appearance.theme.secondaryText)
                        }
                        Spacer()

                        if appearance.customBgType != .none {
                            Text(appearance.customBgType.label)
                                .font(.system(size: 11, weight: .bold))
                                .foregroundStyle(appearance.accentColor)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(appearance.accentColor.opacity(0.15))
                                .clipShape(Capsule())
                        }
                    }

                    // Selettore e anteprima
                    HStack(spacing: 12) {
                        if appearance.customBgType != .none, let path = appearance.customBgPath {
                            ZStack {
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(appearance.theme.secondaryBg)
                                    .frame(width: 70, height: 45)

                                if appearance.customBgType == .gif {
                                    Image(systemName: "film.fill")
                                        .font(.system(size: 18))
                                        .foregroundStyle(appearance.accentColor)
                                } else if let nsImg = NSImage(contentsOfFile: path) {
                                    Image(nsImage: nsImg)
                                        .resizable()
                                        .aspectRatio(contentMode: .fill)
                                        .frame(width: 70, height: 45)
                                        .clipped()
                                        .clipShape(RoundedRectangle(cornerRadius: 8))
                                }
                            }
                        }

                        SteamButtonView(
                            title: appearance.customBgType == .none ? "Scegli Sfondo (Immagine o GIF...)" : "Cambia Sfondo...",
                            icon: "photo.on.rectangle.angled",
                            variant: .accent
                        ) {
                            appearance.selectCustomBackground()
                        }

                        if appearance.customBgType != .none {
                            SteamButtonView(
                                title: "Rimuovi Sfondo",
                                icon: "trash",
                                variant: .destructive
                            ) {
                                appearance.removeCustomBackground()
                            }
                        }
                    }

                    if appearance.customBgType != .none {
                        // Slider Regolazioni Sfondo
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text("Sfocatura sfondo (Blur):")
                                    .font(.system(size: 12))
                                    .foregroundStyle(appearance.theme.secondaryText)
                                Slider(value: $appSettings.bgBlurRadius, in: 0...30, step: 1)
                                Text("\(Int(appearance.bgBlurRadius)) px")
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(appearance.theme.primaryText)
                                    .frame(width: 45)
                            }

                            HStack {
                                Text("Oscuramento (Dimming):")
                                    .font(.system(size: 12))
                                    .foregroundStyle(appearance.theme.secondaryText)
                                Slider(value: $appSettings.bgDimming, in: 0.0...0.85, step: 0.05)
                                Text("\(Int(appearance.bgDimming * 100))%")
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(appearance.theme.primaryText)
                                    .frame(width: 45)
                            }

                            HStack {
                                Text("Adattamento:")
                                    .font(.system(size: 12))
                                    .foregroundStyle(appearance.theme.secondaryText)
                                Picker("", selection: $appSettings.bgFitMode) {
                                    ForEach(BackgroundFitMode.allCases) { f in
                                        Text(f.label).tag(f)
                                    }
                                }
                                .pickerStyle(.segmented)
                                .frame(width: 200)
                            }

                            Toggle("Pausa automatica GIF quando non in primo piano o in Risparmio Energetico", isOn: $appSettings.pauseGifOnInactive)
                                .toggleStyle(.checkbox)
                                .font(.system(size: 12))
                                .foregroundStyle(appearance.theme.primaryText)
                        }
                        .padding(.top, 4)
                    }
                }

                Divider().background(appearance.theme.cardBorder)

                // 3. Colore Accento
                VStack(alignment: .leading, spacing: 8) {
                    Text("Colore di Accento")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(appearance.theme.primaryText)

                    HStack(spacing: 12) {
                        ForEach(AccentPreset.allCases) { preset in
                            Button {
                                appearance.setAccentPreset(preset)
                            } label: {
                                Circle()
                                    .fill(preset.color)
                                    .frame(width: 24, height: 24)
                                    .overlay(
                                        Circle()
                                            .stroke(Color.white, lineWidth: appearance.accentHex == preset.color.toHex() ? 2.5 : 0)
                                    )
                                    .shadow(radius: 2)
                            }
                            .buttonStyle(.plain)
                            .help(preset.label)
                        }

                        Spacer()

                        ColorPicker("Colore personalizzato", selection: Binding(
                            get: { appearance.accentColor },
                            set: { col in
                                if let hex = col.toHex() {
                                    appearance.accentHex = hex
                                }
                            }
                        ))
                        .labelsHidden()
                    }
                }

                Divider().background(appearance.theme.cardBorder)

                // 4. Barra laterale & Layout
                HStack(spacing: 24) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Barra Laterale")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(appearance.theme.primaryText)

                        Picker("", selection: $appSettings.isSidebarExpanded) {
                            Text("Espansa").tag(true)
                            Text("Compatta (Icone)").tag(false)
                        }
                        .pickerStyle(.segmented)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Densità")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(appearance.theme.primaryText)

                        Picker("", selection: $appSettings.density) {
                            ForEach(DensityLevel.allCases) { d in
                                Text(d.label).tag(d)
                            }
                        }
                        .pickerStyle(.segmented)
                    }
                }

                // 5. Hero Banner & Animazioni
                HStack(spacing: 24) {
                    Toggle("Mostra copertina grande in Home (Hero)", isOn: $appSettings.showLargeHero)
                        .toggleStyle(.checkbox)
                        .font(.system(size: 13))
                        .foregroundStyle(appearance.theme.primaryText)

                    Toggle("Riduci animazioni ed effetti", isOn: $appSettings.reduceMotion)
                        .toggleStyle(.checkbox)
                        .font(.system(size: 13))
                        .foregroundStyle(appearance.theme.primaryText)
                }

                // 6. Slider Raggio Angoli & Larghezza Copertine
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        Text("Raggio angoli card:")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                        Slider(value: $appSettings.cornerRadius, in: 4...20, step: 1)
                        Text("\(Int(appearance.cornerRadius)) px")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(appearance.theme.primaryText)
                            .frame(width: 45)
                    }

                    HStack {
                        Text("Dimensione copertine libreria:")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                        Slider(value: $appSettings.gridCardWidth, in: 140...250, step: 10)
                        Text("\(Int(appearance.gridCardWidth)) px")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(appearance.theme.primaryText)
                            .frame(width: 45)
                    }
                }

                // 7. Dimensione Testo
                VStack(alignment: .leading, spacing: 6) {
                    Text("Dimensione Testo")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(appearance.theme.primaryText)

                    Picker("", selection: $appSettings.textScale) {
                        ForEach(TextScale.allCases) { s in
                            Text(s.label).tag(s)
                        }
                    }
                    .pickerStyle(.segmented)
                }
            }
        }
    }

    // MARK: - Sezione Rete, Resilienza DNS & Lua Vault (LuaTools)

    private var networkAndVaultSection: some View {
        SteamCard {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Image(systemName: "network.badge.shield.half.filled")
                        .foregroundStyle(appearance.accentColor)
                    Text("Rete, Resilienza DNS & Lua Vault (LuaTools)")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()
                }

                // 1. Resilienza DNS (DoH)
                VStack(alignment: .leading, spacing: 6) {
                    Text("Risoluzione DNS-over-HTTPS (DoH)")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Text("Previene blocchi CDN e problemi di risoluzione Steam usando DoH cifrato (Cloudflare / Google).")
                        .font(.system(size: 12))
                        .foregroundStyle(appearance.theme.secondaryText)

                    Picker("", selection: $dnsMode) {
                        Text("Automatico (Fallback)").tag("auto")
                        Text("Sempre attivo (DoH)").tag("always")
                        Text("Disattivato (Solo OS)").tag("never")
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: dnsMode) { _, newVal in
                        syncDnsMode(newVal)
                    }
                }

                Divider().background(appearance.theme.cardBorder)

                // 2. Lua Vault
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Lua Vault (Backup e Versioning Configurazioni)")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(appearance.theme.primaryText)
                            Text("Ogni configurazione .lua viene archiviata con SHA-256 e timestamp per permettere il ripristino.")
                                .font(.system(size: 12))
                                .foregroundStyle(appearance.theme.secondaryText)
                        }
                        Spacer()
                        SteamButtonView(
                            title: "Aggiorna",
                            icon: "arrow.clockwise",
                            variant: .secondary,
                            isLoading: isLoadingVault
                        ) {
                            loadVault()
                        }
                    }

                    if vaultSnapshots.isEmpty {
                        Text("Nessun backup memorizzato nel Vault. Vengono creati automaticamente prima di ogni modifica.")
                            .font(.system(size: 12))
                            .foregroundStyle(appearance.theme.secondaryText)
                            .padding(.vertical, 4)
                    } else {
                        VStack(spacing: 6) {
                            ForEach(vaultSnapshots.prefix(5)) { snap in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("AppID \(snap.appid) • \(snap.formattedDate)")
                                            .font(.system(size: 12, weight: .medium))
                                            .foregroundStyle(appearance.theme.primaryText)
                                        Text("Hash: \(snap.hash) • \(snap.bytes) byte • \(snap.note ?? "Snapshot automatico")")
                                            .font(.system(size: 11))
                                            .foregroundStyle(appearance.theme.secondaryText)
                                    }
                                    Spacer()
                                    SteamButtonView(
                                        title: "Ripristina",
                                        icon: "arrow.uturn.backward",
                                        variant: .secondary
                                    ) {
                                        restoreSnapshot(snap)
                                    }
                                }
                                .padding(8)
                                .background(appearance.theme.cardBg)
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Sezione Stato Sistema Semplificato

    private var systemHealthSection: some View {
        SteamCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: "stethoscope")
                        .foregroundStyle(appearance.accentColor)
                    Text("Stato del Sistema")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(appearance.theme.primaryText)
                    Spacer()

                    let allOk = store.doctorChecks.allSatisfy { $0.ok }
                    HStack(spacing: 6) {
                        Image(systemName: allOk ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(allOk ? Color.green : Color.orange)
                        Text(allOk ? "Tutti i componenti pronti" : "Verifiche richieste")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(allOk ? Color.green : Color.orange)
                    }
                }

                Text("L'ambiente locale (Python, cartelle Steam e librerie crittografiche) è monitorato automaticamente per garantire il corretto funzionamento di download e licenze.")
                    .font(.system(size: 12))
                    .foregroundStyle(appearance.theme.secondaryText)

                // Dettagli tecnici collassati di default
                DisclosureGroup("Dettagli tecnici di diagnostica", isExpanded: $showAdvancedDiagnostics) {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(store.doctorChecks) { check in
                            HStack {
                                Text(check.name)
                                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                                    .foregroundStyle(appearance.theme.primaryText)
                                Spacer()
                                Text(check.detail)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(appearance.theme.secondaryText)
                                    .lineLimit(1)
                                Image(systemName: check.ok ? "checkmark" : "xmark")
                                    .foregroundStyle(check.ok ? Color.green : Color.red)
                                    .font(.system(size: 11, weight: .bold))
                            }
                        }
                    }
                    .padding(.top, 8)
                }
                .font(.system(size: 12))
                .foregroundStyle(appearance.accentColor)
            }
        }
    }

    // MARK: - Azioni

    private func saveKey() {
        let k = apiKeyInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !k.isEmpty else { return }

        isSavingKey = true
        Task {
            do {
                try await store.saveApiKey(k)
                apiKeyInput = ""
                isSavingKey = false
            } catch {
                isSavingKey = false
                store.errorMessage = "Errore salvataggio chiave: \(error.localizedDescription)"
            }
        }
    }

    private func clearKey() {
        isClearingKey = true
        Task {
            do {
                try await store.clearApiKey()
                isClearingKey = false
            } catch {
                isClearingKey = false
                store.errorMessage = "Errore rimozione chiave: \(error.localizedDescription)"
            }
        }
    }

    private func repairLicenses() {
        isRepairingLicenses = true
        Task {
            await store.repairLicenses()
            isRepairingLicenses = false
        }
    }

    private func loadHookStatus() {
        Task {
            if let st = try? MacLuaBridge.live.steamHookStatus() {
                await MainActor.run { self.hookStatus = st }
            }
        }
    }

    private func toggleHook(enable: Bool) {
        isTogglingHook = true
        Task {
            do {
                if enable {
                    try MacLuaBridge.live.enableSteamHook()
                } else {
                    try MacLuaBridge.live.disableSteamHook()
                }
                loadHookStatus()
                await MainActor.run { self.isTogglingHook = false }
            } catch {
                await MainActor.run {
                    self.isTogglingHook = false
                    self.store.errorMessage = "Errore hook Steam: \(error.localizedDescription)"
                }
            }
        }
    }

    private func restartSteam() {
        isRestartingSteam = true
        Task {
            await SteamControl.restartSteam()
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            loadHookStatus()
            await MainActor.run { self.isRestartingSteam = false }
        }
    }

    private func loadVault() {
        isLoadingVault = true
        Task {
            if let res = try? MacLuaBridge.live.vaultList() {
                await MainActor.run {
                    self.vaultSnapshots = res.snapshots
                    self.isLoadingVault = false
                }
            } else {
                await MainActor.run { self.isLoadingVault = false }
            }
        }
    }

    private func restoreSnapshot(_ snap: VaultSnapshotItem) {
        Task {
            do {
                try MacLuaBridge.live.vaultRestore(appid: snap.appid, timestamp: snap.timestamp)
                await MainActor.run {
                    self.store.toastMessage = "Snapshot \(snap.formattedDate) per AppID \(snap.appid) ripristinato!"
                }
                await store.reloadLibrary()
            } catch {
                await MainActor.run {
                    self.store.errorMessage = "Errore ripristino snapshot: \(error.localizedDescription)"
                }
            }
        }
    }

    private func syncDnsMode(_ mode: String) {
        let settingsFile = FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Library/Application Support/MacLua/settings.json")
        var dict: [String: Any] = [:]
        if let data = try? Data(contentsOf: settingsFile),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            dict = json
        }
        dict["dns_mode"] = mode
        if let out = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted]) {
            try? out.write(to: settingsFile)
        }
    }
}
