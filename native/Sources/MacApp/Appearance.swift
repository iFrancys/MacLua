import SwiftUI

enum AppThemePreset: String, CaseIterable, Identifiable, Codable {
    case night = "night"
    case slate = "slate"
    case oled = "oled"
    case light = "light"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .night: return "Notte Steam"
        case .slate: return "Ardesia"
        case .oled: return "Nero OLED"
        case .light: return "Chiaro"
        }
    }

    var isDark: Bool {
        self != .light
    }

    var primaryBg: Color {
        switch self {
        case .night: return Color(red: 0.05, green: 0.08, blue: 0.12)
        case .slate: return Color(red: 0.08, green: 0.09, blue: 0.12)
        case .oled: return Color(red: 0.02, green: 0.02, blue: 0.02)
        case .light: return Color(red: 0.95, green: 0.96, blue: 0.98)
        }
    }

    var secondaryBg: Color {
        switch self {
        case .night: return Color(red: 0.09, green: 0.14, blue: 0.20)
        case .slate: return Color(red: 0.12, green: 0.14, blue: 0.18)
        case .oled: return Color(red: 0.06, green: 0.06, blue: 0.07)
        case .light: return Color(red: 0.89, green: 0.91, blue: 0.94)
        }
    }

    var cardBg: Color {
        switch self {
        case .night: return Color(red: 0.08, green: 0.12, blue: 0.17).opacity(0.85)
        case .slate: return Color(red: 0.11, green: 0.13, blue: 0.17).opacity(0.85)
        case .oled: return Color(red: 0.08, green: 0.08, blue: 0.09).opacity(0.9)
        case .light: return Color.white.opacity(0.92)
        }
    }

    var cardBorder: Color {
        switch self {
        case .night: return Color.white.opacity(0.08)
        case .slate: return Color.white.opacity(0.07)
        case .oled: return Color.white.opacity(0.06)
        case .light: return Color.black.opacity(0.08)
        }
    }

    var primaryText: Color {
        isDark ? Color.white.opacity(0.95) : Color(red: 0.10, green: 0.12, blue: 0.16)
    }

    var secondaryText: Color {
        isDark ? Color.white.opacity(0.65) : Color(red: 0.35, green: 0.40, blue: 0.48)
    }

    var tertiaryText: Color {
        isDark ? Color.white.opacity(0.40) : Color(red: 0.55, green: 0.60, blue: 0.68)
    }
}

enum BackgroundStyle: String, CaseIterable, Identifiable, Codable {
    case gradient = "gradient"
    case solid = "solid"
    case glass = "glass"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .gradient: return "Gradiente fluido"
        case .solid: return "Tinta unita"
        case .glass: return "Vetro sfocato"
        }
    }
}

enum DensityLevel: String, CaseIterable, Identifiable, Codable {
    case comfortable = "comfortable"
    case compact = "compact"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .comfortable: return "Comoda"
        case .compact: return "Compatta"
        }
    }

    var padding: CGFloat {
        self == .comfortable ? 18 : 10
    }

    var spacing: CGFloat {
        self == .comfortable ? 16 : 8
    }
}

enum TextScale: String, CaseIterable, Identifiable, Codable {
    case small = "small"
    case medium = "medium"
    case large = "large"
    case extraLarge = "extraLarge"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .small: return "Compatto"
        case .medium: return "Predefinito"
        case .large: return "Grande"
        case .extraLarge: return "Molto grande"
        }
    }

    var scaleFactor: CGFloat {
        switch self {
        case .small: return 0.90
        case .medium: return 1.00
        case .large: return 1.15
        case .extraLarge: return 1.30
        }
    }

    var dynamicTypeSize: DynamicTypeSize {
        switch self {
        case .small: return .small
        case .medium: return .medium
        case .large: return .large
        case .extraLarge: return .xLarge
        }
    }
}

enum AccentPreset: String, CaseIterable, Identifiable {
    case blue = "blue"
    case cyan = "cyan"
    case emerald = "emerald"
    case orange = "orange"
    case coral = "coral"
    case purple = "purple"
    case gold = "gold"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .blue: return "Blu Steam"
        case .cyan: return "Ciano"
        case .emerald: return "Smeraldo"
        case .orange: return "Ambra"
        case .coral: return "Corallo"
        case .purple: return "Viola"
        case .gold: return "Oro"
        }
    }

    var color: Color {
        switch self {
        case .blue: return Color(red: 0.22, green: 0.65, blue: 0.98)
        case .cyan: return Color(red: 0.00, green: 0.85, blue: 0.92)
        case .emerald: return Color(red: 0.20, green: 0.82, blue: 0.48)
        case .orange: return Color(red: 1.00, green: 0.55, blue: 0.15)
        case .coral: return Color(red: 0.98, green: 0.35, blue: 0.45)
        case .purple: return Color(red: 0.68, green: 0.42, blue: 0.95)
        case .gold: return Color(red: 0.98, green: 0.78, blue: 0.20)
        }
    }
}

@Observable @MainActor
final class AppearanceSettings {
    static let shared = AppearanceSettings()

    // MARK: - Proprietà con persistenza UserDefaults

    var theme: AppThemePreset {
        didSet { UserDefaults.standard.set(theme.rawValue, forKey: "app_theme") }
    }

    var bgStyle: BackgroundStyle {
        didSet { UserDefaults.standard.set(bgStyle.rawValue, forKey: "app_bg_style") }
    }

    var density: DensityLevel {
        didSet { UserDefaults.standard.set(density.rawValue, forKey: "app_density") }
    }

    var textScale: TextScale {
        didSet { UserDefaults.standard.set(textScale.rawValue, forKey: "app_text_scale") }
    }

    var accentHex: String {
        didSet { UserDefaults.standard.set(accentHex, forKey: "app_accent_hex") }
    }

    var isSidebarExpanded: Bool {
        didSet { UserDefaults.standard.set(isSidebarExpanded, forKey: "app_sidebar_expanded") }
    }

    var showLargeHero: Bool {
        didSet { UserDefaults.standard.set(showLargeHero, forKey: "app_show_hero") }
    }

    var gridCardWidth: Double {
        didSet { UserDefaults.standard.set(gridCardWidth, forKey: "app_grid_width") }
    }

    var cornerRadius: Double {
        didSet { UserDefaults.standard.set(cornerRadius, forKey: "app_corner_radius") }
    }

    var reduceMotion: Bool {
        didSet { UserDefaults.standard.set(reduceMotion, forKey: "app_reduce_motion") }
    }

    var restartSteamOnAdd: Bool {
        didSet { UserDefaults.standard.set(restartSteamOnAdd, forKey: "app_restart_steam_on_add") }
    }

    // MARK: - Sfondo Personalizzato (Immagini e GIF Animate)

    var customBgType: CustomBackgroundType {
        didSet {
            UserDefaults.standard.set(customBgType.rawValue, forKey: "app_custom_bg_type")
            syncToSettingsFile()
        }
    }

    var customBgPath: String? {
        didSet {
            UserDefaults.standard.set(customBgPath, forKey: "app_custom_bg_path")
            syncToSettingsFile()
        }
    }

    var customBgColorHex: String {
        didSet {
            UserDefaults.standard.set(customBgColorHex, forKey: "app_custom_bg_color")
            syncToSettingsFile()
        }
    }

    var bgBlurRadius: Double {
        didSet {
            UserDefaults.standard.set(bgBlurRadius, forKey: "app_bg_blur")
            syncToSettingsFile()
        }
    }

    var bgDimming: Double {
        didSet {
            UserDefaults.standard.set(bgDimming, forKey: "app_bg_dim")
            syncToSettingsFile()
        }
    }

    var bgFitMode: BackgroundFitMode {
        didSet {
            UserDefaults.standard.set(bgFitMode.rawValue, forKey: "app_bg_fit")
            syncToSettingsFile()
        }
    }

    var pauseGifOnInactive: Bool {
        didSet {
            UserDefaults.standard.set(pauseGifOnInactive, forKey: "app_pause_gif_inactive")
            syncToSettingsFile()
        }
    }

    init() {
        let def = UserDefaults.standard

        let themeStr = def.string(forKey: "app_theme") ?? AppThemePreset.night.rawValue
        self.theme = AppThemePreset(rawValue: themeStr) ?? .night

        let bgStr = def.string(forKey: "app_bg_style") ?? BackgroundStyle.gradient.rawValue
        self.bgStyle = BackgroundStyle(rawValue: bgStr) ?? .gradient

        let denStr = def.string(forKey: "app_density") ?? DensityLevel.comfortable.rawValue
        self.density = DensityLevel(rawValue: denStr) ?? .comfortable

        let tsStr = def.string(forKey: "app_text_scale") ?? TextScale.medium.rawValue
        self.textScale = TextScale(rawValue: tsStr) ?? .medium

        self.accentHex = def.string(forKey: "app_accent_hex") ?? "#38B6FF"
        self.isSidebarExpanded = def.object(forKey: "app_sidebar_expanded") == nil ? true : def.bool(forKey: "app_sidebar_expanded")
        self.showLargeHero = def.object(forKey: "app_show_hero") == nil ? true : def.bool(forKey: "app_show_hero")
        self.gridCardWidth = def.object(forKey: "app_grid_width") == nil ? 180.0 : def.double(forKey: "app_grid_width")
        self.cornerRadius = def.object(forKey: "app_corner_radius") == nil ? 12.0 : def.double(forKey: "app_corner_radius")
        self.reduceMotion = def.bool(forKey: "app_reduce_motion")
        // Default on per richiesta utente
        self.restartSteamOnAdd = def.object(forKey: "app_restart_steam_on_add") == nil ? true : def.bool(forKey: "app_restart_steam_on_add")

        let bgTypeStr = def.string(forKey: "app_custom_bg_type") ?? CustomBackgroundType.none.rawValue
        self.customBgType = CustomBackgroundType(rawValue: bgTypeStr) ?? .none
        self.customBgPath = def.string(forKey: "app_custom_bg_path")
        self.customBgColorHex = def.string(forKey: "app_custom_bg_color") ?? "#0d141e"
        self.bgBlurRadius = def.object(forKey: "app_bg_blur") == nil ? 15.0 : def.double(forKey: "app_bg_blur")
        self.bgDimming = def.object(forKey: "app_bg_dim") == nil ? 0.35 : def.double(forKey: "app_bg_dim")
        let fitStr = def.string(forKey: "app_bg_fit") ?? BackgroundFitMode.fill.rawValue
        self.bgFitMode = BackgroundFitMode(rawValue: fitStr) ?? .fill
        self.pauseGifOnInactive = def.object(forKey: "app_pause_gif_inactive") == nil ? true : def.bool(forKey: "app_pause_gif_inactive")
    }

    var accentColor: Color {
        Color(hex: accentHex) ?? Color(red: 0.22, green: 0.65, blue: 0.98)
    }

    func setAccentPreset(_ preset: AccentPreset) {
        accentHex = preset.color.toHex() ?? "#38B6FF"
        syncToSettingsFile()
    }

    func selectCustomBackground() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.gif, .png, .jpeg, .webP]
        panel.prompt = "Imposta sfondo"
        panel.message = "Scegli un'immagine o una GIF animata per lo sfondo di MacLua"

        if panel.runModal() == .OK, let url = panel.url {
            do {
                let res = try BackgroundStorage.importFile(from: url)
                self.customBgPath = res.path
                self.customBgType = res.type
            } catch {
                print("Errore importazione sfondo: \(error)")
            }
        }
    }

    func removeCustomBackground() {
        if let path = customBgPath {
            BackgroundStorage.removeFile(atPath: path)
        }
        customBgPath = nil
        customBgType = .none
    }

    private func syncToSettingsFile() {
        let settingsDir = FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Library/Application Support/MacLua")
        let settingsFile = settingsDir.appending(path: "settings.json")

        var dict: [String: Any] = [:]
        if let data = try? Data(contentsOf: settingsFile),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            dict = json
        }

        dict["theme"] = theme.rawValue
        dict["accent_color"] = accentHex
        dict["background_mode"] = customBgType.rawValue
        dict["background_path"] = customBgPath ?? ""
        dict["background_blur"] = bgBlurRadius
        dict["background_dim"] = bgDimming
        dict["low_power_pause_gif"] = pauseGifOnInactive

        if let outData = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted, .sortedKeys]) {
            try? FileManager.default.createDirectory(at: settingsDir, withIntermediateDirectories: true)
            try? outData.write(to: settingsFile, options: .atomic)
        }
    }

    func resetToDefaults() {
        theme = .night
        bgStyle = .gradient
        density = .comfortable
        textScale = .medium
        accentHex = "#38B6FF"
        isSidebarExpanded = true
        showLargeHero = true
        gridCardWidth = 180.0
        cornerRadius = 12.0
        reduceMotion = false
        restartSteamOnAdd = true
        removeCustomBackground()
        bgBlurRadius = 15.0
        bgDimming = 0.35
        bgFitMode = .fill
        pauseGifOnInactive = true
    }
}

// MARK: - Color Hex Conversion

extension Color {
    init?(hex: String) {
        var hexSanitized = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        hexSanitized = hexSanitized.replacingOccurrences(of: "#", with: "")

        var rgb: UInt64 = 0
        guard Scanner(string: hexSanitized).scanHexInt64(&rgb) else { return nil }

        let r, g, b, a: Double
        if hexSanitized.count == 6 {
            r = Double((rgb & 0xFF0000) >> 16) / 255.0
            g = Double((rgb & 0x00FF00) >> 8) / 255.0
            b = Double(rgb & 0x0000FF) / 255.0
            a = 1.0
        } else if hexSanitized.count == 8 {
            r = Double((rgb & 0xFF000000) >> 24) / 255.0
            g = Double((rgb & 0x00FF0000) >> 16) / 255.0
            b = Double((rgb & 0x0000FF00) >> 8) / 255.0
            a = Double(rgb & 0x000000FF) / 255.0
        } else {
            return nil
        }
        self.init(.sRGB, red: r, green: g, blue: b, opacity: a)
    }

    func toHex() -> String? {
        guard let nsColor = NSColor(self).usingColorSpace(.sRGB) else { return nil }
        let r = Int(nsColor.redComponent * 255.0)
        let g = Int(nsColor.greenComponent * 255.0)
        let b = Int(nsColor.blueComponent * 255.0)
        return String(format: "#%02X%02X%02X", r, g, b)
    }
}
