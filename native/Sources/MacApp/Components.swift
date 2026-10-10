import SwiftUI

// MARK: - Proprietà di Stato Senza Macro SwiftUIMacros

@propertyWrapper
@Observable
final class UIState<Value>: @unchecked Sendable {
    var wrappedValue: Value
    init(wrappedValue: Value) {
        self.wrappedValue = wrappedValue
    }
    var projectedValue: Binding<Value> {
        Binding(
            get: { self.wrappedValue },
            set: { self.wrappedValue = $0 }
        )
    }
}

// MARK: - Immagine Gioco Asincrona con Fallback

struct AsyncArtwork: View {
    let urls: [URL]
    var cornerRadius: CGFloat = 8
    var contentMode: ContentMode = .fill

    @UIState var currentURLIndex = 0
    @UIState var imageLoaded = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius)
                .fill(Color.white.opacity(0.04))

            if currentURLIndex < urls.count {
                AsyncImage(url: urls[currentURLIndex]) { phase in
                    switch phase {
                    case .empty:
                        ProgressView()
                            .scaleEffect(0.6)
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: contentMode)
                            .transition(.opacity.animation(.easeInOut(duration: 0.25)))
                    case .failure:
                        Color.clear.onAppear {
                            // Prova il fallback successivo
                            if currentURLIndex + 1 < urls.count {
                                currentURLIndex += 1
                            }
                        }
                    @unknown default:
                        EmptyView()
                    }
                }
            } else {
                Image(systemName: "gamecontroller.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(.white.opacity(0.2))
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: cornerRadius)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }
}

// MARK: - Badge di Stato

struct StatusBadge: View {
    let state: StatusApp.State
    var isDownloading: Bool = false

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(badgeColor)
                .frame(width: 7, height: 7)

            Text(isDownloading ? "Download in corso" : state.label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(badgeColor)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(badgeColor.opacity(0.12))
        .clipShape(Capsule())
        .overlay(
            Capsule()
                .stroke(badgeColor.opacity(0.35), lineWidth: 1)
        )
    }

    private var badgeColor: Color {
        if isDownloading {
            return Color.blue
        }
        switch state {
        case .installed:
            return Color(red: 0.35, green: 0.85, blue: 0.45)
        case .updateAvailable:
            return Color(red: 1.0, green: 0.65, blue: 0.20)
        case .notInstalled:
            return Color(red: 0.35, green: 0.70, blue: 1.0)
        }
    }
}

// MARK: - Pulsante in Stile Steam

struct SteamButtonView: View {
    enum Variant {
        case primaryGreen
        case accent
        case secondary
        case destructive
    }

    let title: String
    var icon: String? = nil
    var variant: Variant = .secondary
    var isLoading: Bool = false
    let action: () -> Void

    @UIState var isHovered = false
    @Environment(AppearanceSettings.self) private var appearance

    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                if isLoading {
                    ProgressView()
                        .controlSize(.small)
                } else if let icon {
                    Image(systemName: icon)
                        .font(.system(size: 12, weight: .bold))
                }

                Text(title)
                    .font(.system(size: 13, weight: .semibold))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .foregroundStyle(textColor)
            .background(backgroundView)
            .clipShape(RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius * 0.7)))
            .overlay(borderView)
        }
        .buttonStyle(.plain)
        .onHover { h in
            if !appearance.reduceMotion {
                withAnimation(.easeInOut(duration: 0.15)) {
                    isHovered = h
                }
            } else {
                isHovered = h
            }
        }
    }

    @ViewBuilder
    private var backgroundView: some View {
        switch variant {
        case .primaryGreen:
            LinearGradient(
                colors: isHovered
                    ? [Color(red: 0.50, green: 0.78, blue: 0.18), Color(red: 0.38, green: 0.60, blue: 0.12)]
                    : [Color(red: 0.45, green: 0.70, blue: 0.15), Color(red: 0.32, green: 0.52, blue: 0.10)],
                startPoint: .top,
                endPoint: .bottom
            )
        case .accent:
            LinearGradient(
                colors: isHovered
                    ? [appearance.accentColor.opacity(0.95), appearance.accentColor.opacity(0.80)]
                    : [appearance.accentColor, appearance.accentColor.opacity(0.85)],
                startPoint: .top,
                endPoint: .bottom
            )
        case .secondary:
            Color.white.opacity(isHovered ? 0.12 : 0.06)
        case .destructive:
            Color.red.opacity(isHovered ? 0.25 : 0.15)
        }
    }

    private var borderView: some View {
        RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius * 0.7))
            .stroke(
                variant == .destructive
                    ? Color.red.opacity(0.4)
                    : (variant == .secondary ? Color.white.opacity(0.12) : Color.clear),
                lineWidth: 1
            )
    }

    private var textColor: Color {
        switch variant {
        case .primaryGreen, .accent:
            return .white
        case .secondary:
            return .white.opacity(0.9)
        case .destructive:
            return Color(red: 1.0, green: 0.4, blue: 0.4)
        }
    }
}

// MARK: - Card Contenitore Stile Steam

struct SteamCard<Content: View>: View {
    @Environment(AppearanceSettings.self) private var appearance
    var padding: CGFloat? = nil
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .padding(padding ?? CGFloat(appearance.density.padding))
            .background(appearance.theme.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius)))
            .overlay(
                RoundedRectangle(cornerRadius: CGFloat(appearance.cornerRadius))
                    .stroke(appearance.theme.cardBorder, lineWidth: 1)
            )
    }
}

// MARK: - Banner Notifica Toast

struct ToastOverlay: View {
    let message: String?
    let onDismiss: () -> Void

    var body: some View {
        if let message {
            VStack {
                Spacer()
                HStack(spacing: 12) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Color.green)
                        .font(.system(size: 16))

                    Text(message)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(.white)

                    Spacer(minLength: 12)

                    Button(action: onDismiss) {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(.white.opacity(0.6))
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(Color(red: 0.12, green: 0.16, blue: 0.22).opacity(0.95))
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.white.opacity(0.15), lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.4), radius: 12, y: 6)
                .padding(.horizontal, 32)
                .padding(.bottom, 24)
            }
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }
}
