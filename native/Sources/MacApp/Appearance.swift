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

struct AppearanceConfig: Codable, Equatable {
    var theme: AppThemePreset = .night
    var bgStyle: BackgroundStyle = .gradient
    var density: DensityLevel = .comfortable
    var textScale: TextScale = .medium
    var accentHex: String = "#38B6FF"
    var isSidebarExpanded: Bool = true
    var showLargeHero: Bool = true
    var gridCardWidth: Double = 180.0
    var cornerRadius: Double = 12.0
    var reduceMotion: Bool = false
    var restartSteamOnAdd: Bool = true
    var customBgType: CustomBackgroundType = .none
    var customBgPath: String? = nil
    var customBgColorHex: String = "#0d141e"
    var bgBlurRadius: Double = 15.0
    var bgDimming: Double = 0.35
    var bgFitMode: BackgroundFitMode = .fill
    var pauseGifOnInactive: Bool = true
}

@Observable @MainActor
final class AppearanceSettings {
    static let shared = AppearanceSettings()

    var config: AppearanceConfig {
        didSet {
            saveConfig()
        }
    }

    private func saveConfig() {
        if let data = try? JSONEncoder().encode(config) {
            UserDefaults.standard.set(data, forKey: "maclua_appearance_config")
        }
        syncToSettingsFile()
    }

    var theme: AppThemePreset {
        get { config.theme }
        set { config.theme = newValue }
    }

    var bgStyle: BackgroundStyle {
        get { config.bgStyle }
        set { config.bgStyle = newValue }
    }

    var density: DensityLevel {
        get { config.density }
        set { config.density = newValue }
    }

    var textScale: TextScale {
        get { config.textScale }
        set { config.textScale = newValue }
    }

    var accentHex: String {
        get { config.accentHex }
        set { config.accentHex = newValue }
    }

    var isSidebarExpanded: Bool {
        get { config.isSidebarExpanded }
        set { config.isSidebarExpanded = newValue }
    }

    var showLargeHero: Bool {
        get { config.showLargeHero }
        set { config.showLargeHero = newValue }
    }

    var gridCardWidth: Double {
        get { config.gridCardWidth }
        set { config.gridCardWidth = newValue }
    }

    var cornerRadius: Double {
        get { config.cornerRadius }
        set { config.cornerRadius = newValue }
    }

    var reduceMotion: Bool {
        get { config.reduceMotion }
        set { config.reduceMotion = newValue }
    }

    var restartSteamOnAdd: Bool {
        get { config.restartSteamOnAdd }
        set { config.restartSteamOnAdd = newValue }
    }

    var customBgType: CustomBackgroundType {
        get { config.customBgType }
        set { config.customBgType = newValue }
    }

    var customBgPath: String? {
        get { config.customBgPath }
        set { config.customBgPath = newValue }
    }

    var customBgColorHex: String {
        get { config.customBgColorHex }
        set { config.customBgColorHex = newValue }
    }

    var bgBlurRadius: Double {
        get { config.bgBlurRadius }
        set { config.bgBlurRadius = newValue }
    }

    var bgDimming: Double {
        get { config.bgDimming }
        set { config.bgDimming = newValue }
    }

    var bgFitMode: BackgroundFitMode {
        get { config.bgFitMode }
        set { config.bgFitMode = newValue }
    }

    var pauseGifOnInactive: Bool {
        get { config.pauseGifOnInactive }
        set { config.pauseGifOnInactive = newValue }
    }

    init() {
        let def = UserDefaults.standard
        if let data = def.data(forKey: "maclua_appearance_config"),
           let saved = try? JSONDecoder().decode(AppearanceConfig.self, from: data) {
            self.config = saved
        } else {
            var c = AppearanceConfig()
            if let themeStr = def.string(forKey: "app_theme"), let t = AppThemePreset(rawValue: themeStr) {
                c.theme = t
            }
            if let bgStr = def.string(forKey: "app_bg_style"), let b = BackgroundStyle(rawValue: bgStr) {
                c.bgStyle = b
            }
            if let denStr = def.string(forKey: "app_density"), let d = DensityLevel(rawValue: denStr) {
                c.density = d
            }
            if let tsStr = def.string(forKey: "app_text_scale"), let ts = TextScale(rawValue: tsStr) {
                c.textScale = ts
            }
            if let acc = def.string(forKey: "app_accent_hex") {
                c.accentHex = acc
            }
            if def.object(forKey: "app_sidebar_expanded") != nil {
                c.isSidebarExpanded = def.bool(forKey: "app_sidebar_expanded")
            }
            if def.object(forKey: "app_show_hero") != nil {
                c.showLargeHero = def.bool(forKey: "app_show_hero")
            }
            if def.object(forKey: "app_grid_width") != nil {
                c.gridCardWidth = def.double(forKey: "app_grid_width")
            }
            if def.object(forKey: "app_corner_radius") != nil {
                c.cornerRadius = def.double(forKey: "app_corner_radius")
            }
            c.reduceMotion = def.bool(forKey: "app_reduce_motion")
            if def.object(forKey: "app_restart_steam_on_add") != nil {
                c.restartSteamOnAdd = def.bool(forKey: "app_restart_steam_on_add")
            }
            if let bgTypeStr = def.string(forKey: "app_custom_bg_type"), let bt = CustomBackgroundType(rawValue: bgTypeStr) {
                c.customBgType = bt
            }
            c.customBgPath = def.string(forKey: "app_custom_bg_path")
            if let col = def.string(forKey: "app_custom_bg_color") {
                c.customBgColorHex = col
            }
            if def.object(forKey: "app_bg_blur") != nil {
                c.bgBlurRadius = def.double(forKey: "app_bg_blur")
            }
            if def.object(forKey: "app_bg_dim") != nil {
                c.bgDimming = def.double(forKey: "app_bg_dim")
            }
            if let fitStr = def.string(forKey: "app_bg_fit"), let f = BackgroundFitMode(rawValue: fitStr) {
                c.bgFitMode = f
            }
            if def.object(forKey: "app_pause_gif_inactive") != nil {
                c.pauseGifOnInactive = def.bool(forKey: "app_pause_gif_inactive")
            }
            self.config = c
            if let data = try? JSONEncoder().encode(c) {
                def.set(data, forKey: "maclua_appearance_config")
            }
        }
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
