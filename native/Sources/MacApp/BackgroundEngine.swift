import SwiftUI
import AppKit
import ImageIO

// MARK: - Modalità e Tipi Sfondo

enum CustomBackgroundType: String, CaseIterable, Identifiable, Codable, Sendable {
    case none = "default"
    case color = "color"
    case image = "image"
    case gif = "gif"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .none: return "Predefinito (Tema)"
        case .color: return "Tinta unita"
        case .image: return "Immagine statica"
        case .gif: return "GIF Animata"
        }
    }
}

enum BackgroundFitMode: String, CaseIterable, Identifiable, Codable, Sendable {
    case fill = "fill"
    case fit = "fit"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .fill: return "Riempi (Ritaglia)"
        case .fit: return "Adatta (Intera)"
        }
    }
}

// MARK: - Gestore Cartella Sfondi

enum BackgroundStorage {
    static var backgroundsDirectory: URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appending(path: "MacLua/backgrounds", directoryHint: .isDirectory)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// Importa un file selezionato dall'utente, copiandolo nella sandbox protetta di MacLua
    static func importFile(from sourceURL: URL) throws -> (type: CustomBackgroundType, path: String) {
        let isSecured = sourceURL.startAccessingSecurityScopedResource()
        defer {
            if isSecured { sourceURL.stopAccessingSecurityScopedResource() }
        }

        let ext = sourceURL.pathExtension.lowercased()
        let isGif = ext == "gif"
        let isImage = ["png", "jpg", "jpeg", "webp", "heic"].contains(ext)

        guard isGif || isImage else {
            throw NSError(domain: "MacLuaBackground", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "Formato file non supportato. Seleziona una GIF, PNG, JPG o WEBP."
            ])
        }

        let targetDir = backgroundsDirectory
        let safeName = "custom_bg_\(Int(Date().timeIntervalSince1970)).\(ext)"
        let targetURL = targetDir.appending(path: safeName)

        // Rimuovi eventuali file con lo stesso nome
        if FileManager.default.fileExists(atPath: targetURL.path) {
            try? FileManager.default.removeItem(at: targetURL)
        }

        let data = try Data(contentsOf: sourceURL)
        try data.write(to: targetURL, options: .atomic)

        return (type: isGif ? .gif : .image, path: targetURL.path)
    }

    /// Rimuove un file sfondo precedente
    static func removeFile(atPath path: String) {
        if FileManager.default.fileExists(atPath: path) {
            try? FileManager.default.removeItem(atPath: path)
        }
    }
}

// MARK: - Vista AppKit per GIF Animate ad Alte Prestazioni

final class NonSizingImageView: NSImageView {
    override var intrinsicContentSize: NSSize {
        NSSize(width: NSView.noIntrinsicMetric, height: NSView.noIntrinsicMetric)
    }
}

struct AnimatedGIFView: NSViewRepresentable {
    let fileURL: URL
    let isPlaying: Bool
    let fitMode: BackgroundFitMode

    func makeNSView(context: Context) -> NonSizingImageView {
        let imageView = NonSizingImageView()
        imageView.animates = true
        imageView.canDrawSubviewsIntoLayer = true
        imageView.imageScaling = fitMode == .fill ? .scaleAxesIndependently : .scaleProportionallyUpOrDown
        if let image = NSImage(contentsOf: fileURL) {
            imageView.image = image
        }
        return imageView
    }

    func updateNSView(_ nsView: NonSizingImageView, context: Context) {
        nsView.imageScaling = fitMode == .fill ? .scaleAxesIndependently : .scaleProportionallyUpOrDown
        nsView.animates = isPlaying

        // Aggiorna l'immagine solo se il path è mutato
        if nsView.tag != fileURL.path.hashValue {
            nsView.tag = fileURL.path.hashValue
            nsView.image = NSImage(contentsOf: fileURL)
        }
    }
}

// MARK: - Layer di Sfondo Completo

struct DynamicBackgroundView: View {
    @Environment(AppearanceSettings.self) private var appearance
    @UIState private var isWindowActive = true
    @UIState private var isLowPowerMode = ProcessInfo.processInfo.isLowPowerModeEnabled

    var body: some View {
        ZStack {
            // Sfondo base per garantire contrasto
            appearance.theme.primaryBg

            switch appearance.customBgType {
            case .none:
                // Sfondo nativo (gradiente o tinta)
                defaultBackgroundLayer

            case .color:
                Color(hex: appearance.customBgColorHex) ?? appearance.theme.primaryBg

            case .image:
                if let path = appearance.customBgPath,
                   let nsImage = NSImage(contentsOfFile: path) {
                    GeometryReader { proxy in
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: appearance.bgFitMode == .fill ? .fill : .fit)
                            .frame(width: proxy.size.width, height: proxy.size.height)
                            .clipped()
                            .blur(radius: appearance.bgBlurRadius)
                    }
                    .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                } else {
                    defaultBackgroundLayer
                }

            case .gif:
                if let path = appearance.customBgPath,
                   FileManager.default.fileExists(atPath: path) {
                    GeometryReader { proxy in
                        let shouldAnimate = !appearance.pauseGifOnInactive || (isWindowActive && !isLowPowerMode)
                        AnimatedGIFView(
                            fileURL: URL(fileURLWithPath: path),
                            isPlaying: shouldAnimate,
                            fitMode: appearance.bgFitMode
                        )
                        .frame(width: proxy.size.width, height: proxy.size.height)
                        .clipped()
                        .blur(radius: appearance.bgBlurRadius)
                    }
                    .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                } else {
                    defaultBackgroundLayer
                }
            }

            // Overlay di oscuramento per garantire leggibilità del testo
            if appearance.customBgType != .none {
                Color.black.opacity(appearance.bgDimming)
            }
        }
        .ignoresSafeArea()
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            isWindowActive = true
            isLowPowerMode = ProcessInfo.processInfo.isLowPowerModeEnabled
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didResignActiveNotification)) { _ in
            isWindowActive = false
        }
    }

    @ViewBuilder
    private var defaultBackgroundLayer: some View {
        switch appearance.bgStyle {
        case .gradient:
            LinearGradient(
                colors: [
                    appearance.theme.secondaryBg,
                    appearance.theme.primaryBg
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        case .solid:
            appearance.theme.primaryBg
        case .glass:
            ZStack {
                appearance.theme.primaryBg
                VisualEffectBlur(material: .underWindowBackground, blendingMode: .behindWindow)
            }
        }
    }
}
