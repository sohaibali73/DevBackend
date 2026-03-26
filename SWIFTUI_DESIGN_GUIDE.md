# Analyst by Potomac — SwiftUI Design Guide

> **Matching Design System for iOS, iPadOS, macOS, watchOS & visionOS**
>
> This guide translates the Next.js web frontend into native SwiftUI equivalents for every Apple platform.

---

## Table of Contents

1. [Design Tokens](#1-design-tokens)
2. [Typography](#2-typography)
3. [Color System](#3-color-system)
4. [Dark & Light Mode](#4-dark--light-mode)
5. [Theme Styles](#5-theme-styles)
6. [Spacing & Layout](#6-spacing--layout)
7. [Component Library](#7-component-library)
8. [Navigation & Sidebar](#8-navigation--sidebar)
9. [Login & Register Screens](#9-login--register-screens)
10. [Dashboard](#10-dashboard)
11. [Chat Interface](#11-chat-interface)
12. [AFL Generator](#12-afl-generator)
13. [Knowledge Base](#13-knowledge-base)
14. [Settings](#14-settings)
15. [Platform Adaptations](#15-platform-adaptations)
16. [Animations & Transitions](#16-animations--transitions)
17. [Accessibility](#17-accessibility)
18. [Complete App Architecture](#18-complete-app-architecture)

---

## 1. Design Tokens

### Brand Colors

```swift
import SwiftUI

// MARK: - Potomac Brand Colors
enum PotomacColors {
    // Primary accent
    static let accent = Color(hex: "FEC00F")        // Potomac Yellow
    static let accentLight = Color(hex: "FCD34D")
    static let accentDim = Color(hex: "FEC00F").opacity(0.08)
    static let accentGlow = Color(hex: "FEC00F").opacity(0.3)
    
    // Semantic colors
    static let blue = Color(hex: "60A5FA")
    static let purple = Color(hex: "A78BFA")
    static let green = Color(hex: "34D399")
    static let orange = Color(hex: "FB923C")
    static let pink = Color(hex: "F472B6")
    static let cyan = Color(hex: "22D3EE")
    static let rose = Color(hex: "EC4899")
    
    // Status colors
    static let success = Color(hex: "22C55E")
    static let warning = Color(hex: "FCD34D")
    static let error = Color(hex: "EF4444")
    static let info = Color(hex: "60A5FA")
}
```

### Color Extension

```swift
extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default: (a, r, g, b) = (1, 1, 1, 0)
        }
        self.init(.sRGB, red: Double(r) / 255, green: Double(g) / 255, blue: Double(b) / 255, opacity: Double(a) / 255)
    }
}
```

### Theme Environment

```swift
// MARK: - Theme Environment
enum ThemeMode: String, CaseIterable {
    case light, dark, system
}

enum ThemeStyle: String, CaseIterable, Identifiable {
    case `default`, midnight, ocean, forest, sunset, rose
    
    var id: String { rawValue }
    
    var displayName: String {
        rawValue.capitalized
    }
    
    var icon: String {
        switch self {
        case .default: return "bolt.fill"
        case .midnight: return "moon.fill"
        case .ocean: return "water.waves"
        case .forest: return "leaf.fill"
        case .sunset: return "sunset.fill"
        case .rose: return "flower.fill"
        }
    }
    
    var accentColor: Color {
        switch self {
        case .default: return PotomacColors.accent
        case .midnight: return Color(hex: "818CF8")
        case .ocean: return PotomacColors.cyan
        case .forest: return PotomacColors.green
        case .sunset: return PotomacColors.orange
        case .rose: return PotomacColors.pink
        }
    }
}

// Theme-aware color provider
struct ThemeColors {
    let isDark: Bool
    let style: ThemeStyle
    
    var accent: Color { style.accentColor }
    var accentDim: Color { style.accentColor.opacity(0.08) }
    var background: Color { isDark ? Color(hex: "080809") : Color(hex: "F5F5F6") }
    var card: Color { isDark ? Color(hex: "0D0D10") : .white }
    var cardHover: Color { isDark ? Color(hex: "121216") : Color(hex: "F9F9FA") }
    var raised: Color { isDark ? Color(hex: "111115") : Color(hex: "FAFAFA") }
    var border: Color { isDark ? Color.white.opacity(0.06) : Color.black.opacity(0.07) }
    var borderHover: Color { style.accentColor.opacity(0.4) }
    var text: Color { isDark ? Color(hex: "EFEFEF") : Color(hex: "0A0A0B") }
    var textMuted: Color { isDark ? Color(hex: "606068") : Color(hex: "808088") }
    var textDim: Color { isDark ? Color(hex: "2E2E36") : Color(hex: "D8D8DC") }
    var shadow: Color { isDark ? .black.opacity(0.4) : .black.opacity(0.06) }
}

@Observable
class ThemeManager {
    var mode: ThemeMode = .system
    var style: ThemeStyle = .default
    
    var isDark: Bool {
        switch mode {
        case .light: return false
        case .dark: return true
        case .system:
            #if os(iOS)
            return UITraitCollection.current.userInterfaceStyle == .dark
            #else
            return NSApp?.effectiveAppearance.name == .darkAqua
            #endif
        }
    }
    
    var colors: ThemeColors {
        ThemeColors(isDark: isDark, style: style)
    }
}

struct ThemeKey: EnvironmentKey {
    static let defaultValue = ThemeManager()
}

extension EnvironmentValues {
    var theme: ThemeManager {
        get { self[ThemeKey.self] }
        set { self[ThemeKey.self] = newValue }
    }
}
```

---

## 2. Typography

### Font Families

The web uses three Google Fonts:
- **Syne** — Headings, buttons, labels (display/brand font)
- **DM Mono** — Eyebrow labels, code, metadata (monospace)
- **Instrument Sans** — Body text (sans-serif)

```swift
import SwiftUI

// MARK: - Typography
enum PotomacFont {
    // Syne equivalent → SF Pro Display (closest native match)
    // For exact Syne, load via .otf in bundle
    static func syne(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        // If Syne.otf is bundled:
        // Font.custom("Syne-\(weightName(weight))", size: size)
        // Otherwise use SF Pro Display:
        .system(size: size, weight: weight, design: .default)
    }
    
    // DM Mono equivalent → SF Mono
    static func mono(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
    
    // Instrument Sans equivalent → SF Pro
    static func body(size: CGFloat = 14, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .default)
    }
    
    // Letter spacing helper
    static func letterSpacing(_ value: CGFloat) -> some ViewModifier {
        LetterSpacingModifier(value: value)
    }
}

struct LetterSpacingModifier: ViewModifier {
    let value: CGFloat
    func body(content: Content) -> some View {
        content.kerning(value)
    }
}

// MARK: - Typography Styles
extension View {
    func eyebrowLabel() -> some View {
        self
            .font(PotomacFont.mono(size: 9, weight: .medium))
            .kerning(0.18)
            .textCase(.uppercase)
    }
    
    func heading1(mobile: Bool = false) -> some View {
        self
            .font(PotomacFont.syne(size: mobile ? 36 : 52, weight: .bold))
            .tracking(-0.03)
    }
    
    func heading2(mobile: Bool = false) -> some View {
        self
            .font(PotomacFont.syne(size: mobile ? 26 : 34, weight: .bold))
            .tracking(-0.025)
    }
    
    func heading3(mobile: Bool = false) -> some View {
        self
            .font(PotomacFont.syne(size: mobile ? 18 : 20, weight: .bold))
            .tracking(-0.02)
    }
    
    func bodyText() -> some View {
        self
            .font(PotomacFont.body(size: 14))
            .lineSpacing(4)
    }
    
    func monoLabel(size: CGFloat = 9) -> some View {
        self
            .font(PotomacFont.mono(size: size, weight: .regular))
            .kerning(0.05)
    }
    
    func navLabel(mobile: Bool = false) -> some View {
        self
            .font(PotomacFont.syne(size: mobile ? 15 : 13, weight: .bold))
            .kerning(0.5)
            .textCase(.uppercase)
    }
    
    func sectionTitle() -> some View {
        self
            .font(PotomacFont.syne(size: 13, weight: .bold))
            .tracking(-0.01)
    }
}
```

---

## 3. Color System

### Accent Color Picker

```swift
struct AccentColorPicker: View {
    @Binding var selectedColor: Color
    
    let accentColors: [(Color, String)] = [
        (PotomacColors.accent, "Potomac Yellow"),
        (PotomacColors.blue, "Blue"),
        (PotomacColors.green, "Green"),
        (PotomacColors.purple, "Purple"),
        (PotomacColors.orange, "Orange"),
        (PotomacColors.pink, "Pink"),
    ]
    
    var body: some View {
        HStack(spacing: 12) {
            ForEach(accentColors, id: \.1) { color, name in
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        selectedColor = color
                    }
                } label: {
                    ZStack {
                        RoundedRectangle(cornerRadius: 14)
                            .fill(color)
                            .frame(width: 48, height: 48)
                            .overlay(
                                RoundedRectangle(cornerRadius: 14)
                                    .strokeBorder(
                                        selectedColor == color ? Color.primary : .clear,
                                        lineWidth: 3
                                    )
                            )
                        
                        if selectedColor == color {
                            Image(systemName: "checkmark")
                                .font(.system(size: 18, weight: .bold))
                                .foregroundStyle(.black)
                        }
                    }
                    .scaleEffect(selectedColor == color ? 1.1 : 1.0)
                    .shadow(color: selectedColor == color ? color.opacity(0.4) : .clear, radius: 8)
                }
                .buttonStyle(.plain)
            }
        }
    }
}
```

---

## 4. Dark & Light Mode

### System-Aware Background

```swift
struct ThemedBackground: View {
    @Environment(\.theme) var theme
    
    var body: some View {
        let colors = theme.colors
        
        ZStack {
            colors.background
                .ignoresSafeArea()
            
            // Radial gradient overlay (matches web)
            RadialGradient(
                colors: [
                    colors.accent.opacity(0.04),
                    .clear
                ],
                center: .init(x: 0.6, y: -0.1),
                startRadius: 0,
                endRadius: 500
            )
            .ignoresSafeArea()
        }
    }
}
```

### Top Accent Bar

```swift
struct AccentTopBar: View {
    @Environment(\.theme) var theme
    
    var body: some View {
        LinearGradient(
            colors: [.clear, theme.colors.accent.opacity(0.5), theme.colors.accent.opacity(0.12), .clear],
            startPoint: .leading,
            endPoint: .trailing
        )
        .frame(height: 1)
        .opacity(0.5)
    }
}
```

---

## 5. Theme Styles

### Theme Style Picker

```swift
struct ThemeStylePicker: View {
    @Binding var selectedStyle: ThemeStyle
    @Environment(\.theme) var theme
    @Environment(\.horizontalSizeClass) var sizeClass
    
    let columns = [
        GridItem(.flexible()),
        GridItem(.flexible()),
        GridItem(.flexible()),
    ]
    
    var body: some View {
        LazyVGrid(columns: sizeClass == .compact ? [GridItem(.flexible()), GridItem(.flexible())] : columns, spacing: 12) {
            ForEach(ThemeStyle.allCases) { style in
                ThemeStyleCard(
                    style: style,
                    isSelected: selectedStyle == style,
                    colors: theme.colors
                ) {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        selectedStyle = style
                    }
                }
            }
        }
    }
}

struct ThemeStyleCard: View {
    let style: ThemeStyle
    let isSelected: Bool
    let colors: ThemeColors
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 10) {
                // Icon
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(style.accentColor.opacity(0.15))
                        .frame(width: 44, height: 44)
                    
                    Image(systemName: style.icon)
                        .font(.system(size: 20, weight: .medium))
                        .foregroundStyle(style.accentColor)
                }
                
                Text(style.displayName)
                    .font(PotomacFont.syne(size: 12, weight: .bold))
                    .foregroundStyle(isSelected ? colors.text : colors.textMuted)
                
                Text(styleDescription(style))
                    .font(PotomacFont.mono(size: 9))
                    .foregroundStyle(colors.textMuted)
            }
            .frame(maxWidth: .infinity)
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(colors.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .strokeBorder(
                                isSelected ? style.accentColor : colors.border,
                                lineWidth: isSelected ? 2 : 1
                            )
                    )
            )
            .shadow(
                color: isSelected ? style.accentColor.opacity(0.2) : colors.shadow,
                radius: isSelected ? 6 : 4,
                y: 2
            )
        }
        .buttonStyle(.plain)
    }
    
    func styleDescription(_ style: ThemeStyle) -> String {
        switch style {
        case .default: return "Classic Potomac yellow"
        case .midnight: return "Deep purple elegance"
        case .ocean: return "Calm teal waters"
        case .forest: return "Natural green vibes"
        case .sunset: return "Warm orange glow"
        case .rose: return "Soft pink elegance"
        }
    }
}
```

### Theme Mode Picker

```swift
struct ThemeModePicker: View {
    @Binding var selectedMode: ThemeMode
    @Environment(\.theme) var theme
    
    var body: some View {
        HStack(spacing: 16) {
            ForEach(ThemeMode.allCases, id: \.self) { mode in
                ThemeModeCard(
                    mode: mode,
                    isSelected: selectedMode == mode,
                    colors: theme.colors
                ) {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        selectedMode = mode
                    }
                }
            }
        }
    }
}

struct ThemeModeCard: View {
    let mode: ThemeMode
    let isSelected: Bool
    let colors: ThemeColors
    let onTap: () -> Void
    
    var modeColor: Color {
        switch mode {
        case .light: return PotomacColors.orange
        case .dark: return PotomacColors.purple
        case .system: return PotomacColors.blue
        }
    }
    
    var modeIcon: String {
        switch mode {
        case .light: return "sun.max.fill"
        case .dark: return "moon.fill"
        case .system: return "display"
        }
    }
    
    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 14)
                        .fill(
                            LinearGradient(
                                colors: [modeColor.opacity(0.2), modeColor.opacity(0.08)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 52, height: 52)
                    
                    Image(systemName: modeIcon)
                        .font(.system(size: 24, weight: .medium))
                        .foregroundStyle(modeColor)
                }
                
                Text(mode.rawValue.capitalized)
                    .font(PotomacFont.syne(size: 14, weight: .bold))
                    .foregroundStyle(isSelected ? colors.text : colors.textMuted)
                
                Text(modeDescription(mode))
                    .font(PotomacFont.mono(size: 10))
                    .foregroundStyle(colors.textMuted)
                
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(modeColor)
                        .font(.system(size: 20))
                }
            }
            .frame(maxWidth: .infinity)
            .padding(28)
            .background(
                RoundedRectangle(cornerRadius: 20)
                    .fill(colors.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: 20)
                            .strokeBorder(
                                isSelected ? modeColor : colors.border,
                                lineWidth: isSelected ? 2 : 1
                            )
                    )
            )
            .shadow(
                color: isSelected ? modeColor.opacity(0.25) : colors.shadow,
                radius: isSelected ? 8 : 4,
                y: 2
            )
        }
        .buttonStyle(.plain)
    }
    
    func modeDescription(_ mode: ThemeMode) -> String {
        switch mode {
        case .light: return "Clean, bright interface"
        case .dark: return "Easy on the eyes"
        case .system: return "Match your OS"
        }
    }
}
```

---

## 6. Spacing & Layout

### Grid System

```swift
// MARK: - Layout Constants
enum PotomacLayout {
    static let pagePadding: CGFloat = 52
    static let pagePaddingMobile: CGFloat = 20
    static let cardPadding: CGFloat = 28
    static let sectionGap: CGFloat = 52
    static let cardGap: CGFloat = 16
    static let sidebarWidth: CGFloat = 256
    static let sidebarCollapsedWidth: CGFloat = 80
    static let maxContentWidth: CGFloat = 1360
}

// Responsive page container
struct PotomacPage<Content: View>: View {
    @Environment(\.horizontalSizeClass) var sizeClass
    @Environment(\.theme) var theme
    let content: Content
    
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }
    
    var isMobile: Bool { sizeClass == .compact }
    
    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                AccentTopBar()
                
                content
                    .frame(maxWidth: PotomacLayout.maxContentWidth)
                    .padding(.horizontal, isMobile ? PotomacLayout.pagePaddingMobile : PotomacLayout.pagePadding)
                    .padding(.vertical, isMobile ? 40 : 56)
            }
        }
        .background(ThemedBackground())
    }
}
```

### Section Header

```swift
struct SectionHeader: View {
    @Environment(\.theme) var theme
    let label: String
    var action: String? = nil
    var onAction: (() -> Void)? = nil
    
    var body: some View {
        HStack(spacing: 16) {
            // Accent bar
            LinearGradient(
                colors: [theme.colors.accent, theme.colors.accent.opacity(0.2)],
                startPoint: .top,
                endPoint: .bottom
            )
            .frame(width: 3, height: 16)
            .clipShape(Capsule())
            
            Text(label)
                .eyebrowLabel()
                .foregroundStyle(theme.colors.textMuted)
            
            Rectangle()
                .fill(theme.colors.border)
                .frame(height: 1)
            
            if let action = action {
                Button(action: { onAction?() }) {
                    Text(action)
                        .font(PotomacFont.mono(size: 9))
                        .kerning(0.12)
                        .textCase(.uppercase)
                        .foregroundStyle(theme.colors.accent.opacity(0.7))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.bottom, 18)
    }
}
```

---

## 7. Component Library

### Card Component

```swift
struct PotomacCard<Content: View>: View {
    @Environment(\.theme) var theme
    var accentColor: Color? = nil
    let content: Content
    
    init(accentColor: Color? = nil, @ViewBuilder content: () -> Content) {
        self.accentColor = accentColor
        self.content = content()
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            content
        }
        .padding(PotomacLayout.cardPadding)
        .background(
            RoundedRectangle(cornerRadius: 20)
                .fill(theme.colors.card)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .strokeBorder(theme.colors.border, lineWidth: 1)
                )
        )
        .shadow(color: theme.colors.shadow, radius: 4, y: 2)
        .overlay(alignment: .top) {
            if let accent = accentColor {
                LinearGradient(
                    colors: [accent, accent.opacity(0.1)],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(height: 1.5)
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .padding(.horizontal, 1)
            }
        }
    }
}
```

### Styled Button

```swift
struct PotomacButton: View {
    @Environment(\.theme) var theme
    let title: String
    var icon: String? = nil
    var style: ButtonStyle = .primary
    var isLoading: Bool = false
    let action: () -> Void
    
    enum ButtonStyle {
        case primary, secondary, destructive
    }
    
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if isLoading {
                    ProgressView()
                        .tint(style == .primary ? .black : theme.colors.accent)
                } else if let icon = icon {
                    Image(systemName: icon)
                        .font(.system(size: 15, weight: .bold))
                }
                
                Text(title)
                    .font(PotomacFont.syne(size: 12, weight: .bold))
                    .kerning(0.08)
                    .textCase(.uppercase)
            }
            .padding(.horizontal, 32)
            .padding(.vertical, 15)
            .background(backgroundView)
            .foregroundStyle(foregroundColor)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .shadow(color: shadowColor, radius: 8, y: 4)
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
    }
    
    @ViewBuilder
    var backgroundView: some View {
        switch style {
        case .primary:
            LinearGradient(
                colors: [theme.colors.accent, theme.colors.accent],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        case .secondary:
            theme.colors.card
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(theme.colors.border, lineWidth: 1)
                )
        case .destructive:
            Color.clear
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(PotomacColors.error.opacity(0.4), lineWidth: 1)
                )
        }
    }
    
    var foregroundColor: Color {
        switch style {
        case .primary: return .black
        case .secondary: return theme.colors.text
        case .destructive: return PotomacColors.error
        }
    }
    
    var shadowColor: Color {
        switch style {
        case .primary: return theme.colors.accent.opacity(0.35)
        case .secondary, .destructive: return .clear
        }
    }
}
```

### Text Field

```swift
struct PotomacTextField: View {
    @Environment(\.theme) var theme
    let label: String
    @Binding var text: String
    var placeholder: String = ""
    var isSecure: Bool = false
    var showToggle: Bool = false
    
    @State private var isRevealed = false
    @FocusState private var isFocused: Bool
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(label)
                .eyebrowLabel()
                .foregroundStyle(theme.colors.textMuted)
            
            HStack {
                Group {
                    if isSecure && !isRevealed {
                        SecureField(placeholder, text: $text)
                    } else {
                        TextField(placeholder, text: $text)
                    }
                }
                .font(PotomacFont.body(size: 14))
                .foregroundStyle(theme.colors.text)
                .focused($isFocused)
                
                if showToggle && isSecure {
                    Button {
                        isRevealed.toggle()
                    } label: {
                        Image(systemName: isRevealed ? "eye.slash" : "eye")
                            .foregroundStyle(theme.colors.textMuted)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .frame(height: 46)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(theme.colors.raised)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .strokeBorder(
                                isFocused ? theme.colors.accent : theme.colors.border,
                                lineWidth: 1
                            )
                    )
            )
            .shadow(color: theme.colors.shadow, radius: 4, y: 2)
        }
    }
}
```

### Toggle Switch

```swift
struct PotomacToggle: View {
    @Environment(\.theme) var theme
    let label: String
    var description: String? = nil
    var color: Color? = nil
    @Binding var isOn: Bool
    
    var body: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(PotomacFont.syne(size: 13, weight: .bold))
                    .tracking(-0.01)
                    .foregroundStyle(theme.colors.text)
                
                if let desc = description {
                    Text(desc)
                        .font(PotomacFont.body(size: 12))
                        .foregroundStyle(theme.colors.textMuted)
                        .lineSpacing(2)
                }
            }
            
            Spacer()
            
            Toggle("", isOn: $isOn)
                .toggleStyle(PotomacToggleStyle(accentColor: color ?? theme.colors.accent))
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 22)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(theme.colors.card)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .strokeBorder(theme.colors.border, lineWidth: 1)
                )
        )
        .shadow(color: theme.colors.shadow, radius: 4, y: 2)
    }
}

struct PotomacToggleStyle: ToggleStyle {
    let accentColor: Color
    
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            RoundedRectangle(cornerRadius: 13)
                .fill(configuration.isOn ? accentColor : Color.gray.opacity(0.3))
                .frame(width: 48, height: 26)
                .overlay(
                    Circle()
                        .fill(.white)
                        .frame(width: 20, height: 20)
                        .shadow(radius: 1)
                        .offset(x: configuration.isOn ? 11 : -11)
                )
                .shadow(color: configuration.isOn ? accentColor.opacity(0.3) : .clear, radius: 4)
        }
        .buttonStyle(.plain)
        .animation(.spring(response: 0.2, dampingFraction: 0.7), value: configuration.isOn)
    }
}
```

### Badge / Chip

```swift
struct PotomacBadge: View {
    @Environment(\.theme) var theme
    let text: String
    var color: Color? = nil
    var isOutlined: Bool = false
    
    var body: some View {
        let badgeColor = color ?? theme.colors.accent
        
        Text(text)
            .font(PotomacFont.mono(size: 9, weight: .bold))
            .kerning(0.1)
            .textCase(.uppercase)
            .foregroundStyle(isOutlined ? badgeColor : .black)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(
                Capsule()
                    .fill(isOutlined ? badgeColor.opacity(0.1) : badgeColor)
                    .overlay(
                        Capsule()
                            .strokeBorder(badgeColor, lineWidth: isOutlined ? 1 : 0)
                    )
            )
    }
}
```

### Sparkline Chart

```swift
struct Sparkline: View {
    let values: [Double]
    let color: Color
    
    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let min = values.min() ?? 0
            let max = values.max() ?? 1
            let range = max - min
            
            Path { path in
                for (i, v) in values.enumerated() {
                    let x = CGFloat(i) / CGFloat(values.count - 1) * w
                    let y = h - CGFloat((v - min) / range) * h * 0.8 - h * 0.1
                    if i == 0 { path.move(to: CGPoint(x: x, y: y)) }
                    else { path.addLine(to: CGPoint(x: x, y: y)) }
                }
            }
            .stroke(color, lineWidth: 1.5)
            .clipShape(RoundedRectangle(cornerRadius: 4))
        }
        .frame(width: 80, height: 28)
    }
}
```

### Loading Shimmer

```swift
struct ShimmerText: View {
    let text: String
    @State private var phase: CGFloat = 0
    
    var body: some View {
        Text(text)
            .font(PotomacFont.syne(size: 12, weight: .bold))
            .foregroundStyle(
                LinearGradient(
                    colors: [.secondary, .primary, .secondary],
                    startPoint: UnitPoint(x: phase - 0.3, y: 0.5),
                    endPoint: UnitPoint(x: phase + 0.3, y: 0.5)
                )
            )
            .onAppear {
                withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                    phase = 1.6
                }
            }
    }
}
```

---

## 8. Navigation & Sidebar

### Sidebar (macOS / iPad)

```swift
struct PotomacSidebar: View {
    @Environment(\.theme) var theme
    @Binding var selectedTab: AppTab
    @Binding var isCollapsed: Bool
    var user: User?
    
    var body: some View {
        VStack(spacing: 0) {
            // Logo section
            LogoSection(isCollapsed: isCollapsed, colors: theme.colors)
                .frame(height: 88)
                .overlay(alignment: .bottom) {
                    Divider()
                        .overlay(theme.colors.border)
                }
            
            // Navigation items
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(AppTab.mainTabs) { tab in
                        SidebarItem(
                            tab: tab,
                            isSelected: selectedTab == tab,
                            isCollapsed: isCollapsed,
                            colors: theme.colors
                        ) {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                                selectedTab = tab
                            }
                        }
                    }
                }
                .padding(.horizontal, isCollapsed ? 8 : 16)
                .padding(.vertical, 24)
            }
            
            Spacer()
            
            // User section
            UserSection(user: user, isCollapsed: isCollapsed, colors: theme.colors)
                .padding(.horizontal, isCollapsed ? 8 : 16)
                .padding(.vertical, 24)
                .overlay(alignment: .top) {
                    Divider()
                        .overlay(theme.colors.border)
                }
        }
        .frame(width: isCollapsed ? PotomacLayout.sidebarCollapsedWidth : PotomacLayout.sidebarWidth)
        .background(
            LinearGradient(
                colors: [
                    theme.colors.card,
                    theme.colors.background
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .overlay(alignment: .trailing) {
            Divider()
                .overlay(theme.colors.border)
        }
    }
}

struct SidebarItem: View {
    let tab: AppTab
    let isSelected: Bool
    let isCollapsed: Bool
    let colors: ThemeColors
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack(spacing: 16) {
                // Icon container
                ZStack {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected ? .white.opacity(0.2) : colors.accent.opacity(0.1))
                        .frame(width: 36, height: 36)
                    
                    Image(systemName: tab.icon)
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(isSelected ? .white : PotomacColors.blue)
                }
                
                if !isCollapsed {
                    Text(tab.title)
                        .navLabel()
                        .foregroundStyle(isSelected ? .white : colors.textMuted)
                    
                    Spacer()
                    
                    if let badge = tab.badge {
                        PotomacBadge(text: badge)
                    }
                }
            }
            .padding(.horizontal, isCollapsed ? 8 : 16)
            .frame(height: 52)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(
                        isSelected
                        ? LinearGradient(
                            colors: [PotomacColors.blue, PotomacColors.purple],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                        : LinearGradient(
                            colors: [.clear, .clear],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .shadow(
                        color: isSelected ? PotomacColors.blue.opacity(0.35) : .clear,
                        radius: 8, y: 4
                    )
            )
        }
        .buttonStyle(.plain)
    }
}

enum AppTab: String, CaseIterable, Identifiable {
    case dashboard, afl, chat, knowledge, reverseEngineer, settings
    
    var id: String { rawValue }
    
    var title: String {
        switch self {
        case .dashboard: return "DASHBOARD"
        case .afl: return "AFL GENERATOR"
        case .chat: return "CHAT"
        case .knowledge: return "KNOWLEDGE BASE"
        case .reverseEngineer: return "REVERSE ENGINEER"
        case .settings: return "SETTINGS"
        }
    }
    
    var icon: String {
        switch self {
        case .dashboard: return "square.grid.2x2"
        case .afl: return "chevron.left.forwardslash.chevron.right"
        case .chat: return "message"
        case .knowledge: return "cylinder.split.1x2"
        case .reverseEngineer: return "bolt"
        case .settings: return "gear"
        }
    }
    
    var badge: String? { nil }
    
    static var mainTabs: [AppTab] {
        [.dashboard, .afl, .chat, .knowledge, .reverseEngineer, .settings]
    }
}
```

### Tab Bar (iPhone)

```swift
struct PotomacTabBar: View {
    @Environment(\.theme) var theme
    @Binding var selectedTab: AppTab
    
    var body: some View {
        HStack(spacing: 0) {
            ForEach(AppTab.mainTabs) { tab in
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        selectedTab = tab
                    }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: selectedTab == tab ? tab.icon + ".fill" : tab.icon)
                            .font(.system(size: 20, weight: .medium))
                            .foregroundStyle(selectedTab == tab ? theme.colors.accent : theme.colors.textMuted)
                        
                        Text(tabShortTitle(tab))
                            .font(PotomacFont.mono(size: 8, weight: .bold))
                            .kerning(0.08)
                            .textCase(.uppercase)
                            .foregroundStyle(selectedTab == tab ? theme.colors.accent : theme.colors.textMuted)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .padding(.top, 8)
        .padding(.bottom, 24) // Safe area
        .background(
            theme.colors.card
                .overlay(alignment: .top) {
                    Divider()
                        .overlay(theme.colors.border)
                }
                .shadow(color: theme.colors.shadow, radius: 8, y: -2)
        )
    }
    
    func tabShortTitle(_ tab: AppTab) -> String {
        switch tab {
        case .dashboard: return "Home"
        case .afl: return "AFL"
        case .chat: return "Chat"
        case .knowledge: return "KB"
        case .reverseEngineer: return "RE"
        case .settings: return "Settings"
        }
    }
}
```

### Logo Section

```swift
struct LogoSection: View {
    let isCollapsed: Bool
    let colors: ThemeColors
    
    var body: some View {
        HStack(spacing: 12) {
            // Logo
            Image("PotomacIcon")
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 44, height: 44)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .strokeBorder(colors.border, lineWidth: 1)
                )
                .shadow(color: colors.accent.opacity(0.15), radius: 8)
            
            if !isCollapsed {
                VStack(alignment: .leading, spacing: 4) {
                    Text("ANALYST")
                        .font(PotomacFont.syne(size: 20, weight: .heavy))
                        .kerning(2)
                        .foregroundStyle(colors.text)
                    
                    // Developer Beta badge
                    HStack(spacing: 5) {
                        Circle()
                            .fill(PotomacColors.warning)
                            .frame(width: 5, height: 5)
                        
                        Text("DEVELOPER BETA")
                            .font(PotomacFont.mono(size: 8, weight: .bold))
                            .kerning(0.14)
                            .textCase(.uppercase)
                            .foregroundStyle(PotomacColors.warning)
                    }
                    .padding(.horizontal, 7)
                    .padding(.vertical, 2)
                    .background(
                        Capsule()
                            .fill(PotomacColors.warning.opacity(0.1))
                            .overlay(
                                Capsule()
                                    .strokeBorder(PotomacColors.warning.opacity(0.3), lineWidth: 1)
                            )
                    )
                }
            }
            
            Spacer()
            
            // Collapse toggle
            if !isCollapsed {
                Button {
                    // Toggle collapse
                } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 20, weight: .medium))
                        .foregroundStyle(colors.textMuted)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 20)
    }
}
```

---

## 9. Login & Register Screens

### Login Screen

```swift
struct LoginView: View {
    @Environment(\.theme) var theme
    @Environment(\.horizontalSizeClass) var sizeClass
    @State private var email = ""
    @State private var password = ""
    @State private var showPassword = false
    @State private var isLoading = false
    @State private var error: String?
    
    var isMobile: Bool { sizeClass == .compact }
    
    var body: some View {
        if isMobile {
            mobileLayout
        } else {
            desktopLayout
        }
    }
    
    // MARK: - Desktop (split view)
    var desktopLayout: some View {
        HStack(spacing: 0) {
            brandingPanel
                .frame(maxWidth: .infinity)
            
            Divider()
                .overlay(theme.colors.border)
            
            formPanel
                .frame(width: 520)
        }
        .ignoresSafeArea()
    }
    
    // MARK: - Mobile (stacked)
    var mobileLayout: some View {
        VStack(spacing: 0) {
            // Mini branding
            VStack(spacing: 16) {
                Image("PotomacIcon")
                    .resizable()
                    .frame(width: 60, height: 60)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                
                Text("ANALYST")
                    .font(PotomacFont.syne(size: 28, weight: .heavy))
                    .kerning(1.5)
                    .foregroundStyle(theme.colors.text)
                
                Text("BY POTOMAC")
                    .font(PotomacFont.syne(size: 14, weight: .bold))
                    .kerning(0.14)
                    .textCase(.uppercase)
                    .foregroundStyle(theme.colors.accent)
            }
            .padding(.top, 48)
            .padding(.bottom, 36)
            
            formPanel
        }
    }
    
    // MARK: - Branding Panel
    var brandingPanel: some View {
        ZStack {
            // Background
            LinearGradient(
                colors: [
                    theme.colors.background,
                    Color(hex: "0D1117"),
                    theme.colors.background
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            
            // Grid lines
            VStack(spacing: 0) {
                ForEach(0..<20, id: \.self) { _ in
                    HStack(spacing: 0) {
                        ForEach(0..<20, id: \.self) { _ in
                            Rectangle()
                                .fill(theme.colors.accent.opacity(0.04))
                                .frame(width: 40, height: 40)
                                .border(theme.colors.accent.opacity(0.04), width: 0.5)
                        }
                    }
                }
            }
            
            // Content
            VStack(spacing: 36) {
                Spacer()
                
                // Logo
                ZStack {
                    RoundedRectangle(cornerRadius: 28)
                        .fill(
                            LinearGradient(
                                colors: [
                                    theme.colors.accent.opacity(0.1),
                                    PotomacColors.purple.opacity(0.08)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 110, height: 110)
                        .overlay(
                            RoundedRectangle(cornerRadius: 28)
                                .strokeBorder(theme.colors.accent.opacity(0.2), lineWidth: 1)
                        )
                        .shadow(color: theme.colors.accent.opacity(0.15), radius: 8)
                    
                    Image("PotomacIcon")
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 70, height: 70)
                }
                
                Text("ANALYST")
                    .font(PotomacFont.syne(size: 52, weight: .heavy))
                    .kerning(-0.03)
                    .foregroundStyle(theme.colors.text)
                
                Text("BY POTOMAC")
                    .font(PotomacFont.syne(size: 17, weight: .bold))
                    .kerning(0.14)
                    .textCase(.uppercase)
                    .foregroundStyle(theme.colors.accent)
                
                // Tagline
                VStack(spacing: 0) {
                    LinearGradient(
                        colors: [.clear, theme.colors.accent, .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(height: 2)
                    
                    Text("BREAK THE\nSTATUS QUO")
                        .font(PotomacFont.syne(size: 30, weight: .heavy))
                        .kerning(0.14)
                        .textCase(.uppercase)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(theme.colors.accent)
                        .padding(.vertical, 32)
                        .padding(.horizontal, 44)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(theme.colors.accent.opacity(0.08))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .strokeBorder(theme.colors.accent.opacity(0.25), lineWidth: 1)
                                )
                        )
                    
                    LinearGradient(
                        colors: [.clear, theme.colors.accent, .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(height: 2)
                }
                
                Spacer()
            }
        }
    }
    
    // MARK: - Form Panel
    var formPanel: some View {
        VStack(spacing: 0) {
            Spacer()
            
            VStack(alignment: .leading, spacing: 0) {
                // Header
                HStack(spacing: 16) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(
                                LinearGradient(
                                    colors: [
                                        theme.colors.accent.opacity(0.15),
                                        PotomacColors.purple.opacity(0.12)
                                    ],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 40, height: 40)
                        
                        Image(systemName: "sparkles")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundStyle(PotomacColors.blue)
                    }
                    
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Welcome Back")
                            .font(PotomacFont.syne(size: 30, weight: .heavy))
                            .kerning(0.08)
                            .foregroundStyle(theme.colors.text)
                        
                        Text("Sign in to continue to your dashboard")
                            .font(PotomacFont.body(size: 14))
                            .foregroundStyle(theme.colors.textMuted)
                    }
                }
                .padding(.bottom, 28)
                
                // Error
                if let error = error {
                    HStack(spacing: 12) {
                        Image(systemName: "exclamationmark.circle.fill")
                            .foregroundStyle(PotomacColors.error)
                        Text(error)
                            .font(PotomacFont.body(size: 13))
                            .foregroundStyle(PotomacColors.error)
                    }
                    .padding(16)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(PotomacColors.error.opacity(0.08))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .strokeBorder(PotomacColors.error.opacity(0.3), lineWidth: 1)
                            )
                    )
                    .padding(.bottom, 28)
                }
                
                // Fields
                PotomacTextField(
                    label: "EMAIL ADDRESS",
                    text: $email,
                    placeholder: "you@example.com"
                )
                .padding(.bottom, 24)
                
                PotomacTextField(
                    label: "PASSWORD",
                    text: $password,
                    placeholder: "Enter your password",
                    isSecure: true,
                    showToggle: true
                )
                .padding(.bottom, 8)
                
                HStack {
                    Spacer()
                    Button("Forgot password?") {
                        // Navigate to forgot password
                    }
                    .font(PotomacFont.body(size: 12, weight: .semibold))
                    .foregroundStyle(theme.colors.accent)
                    .buttonStyle(.plain)
                }
                .padding(.bottom, 28)
                
                // Sign In button
                PotomacButton(
                    title: "Sign In",
                    icon: "arrow.right",
                    isLoading: isLoading
                ) {
                    Task { await signIn() }
                }
                .frame(maxWidth: .infinity)
                .padding(.bottom, 36)
                
                // Divider
                HStack(spacing: 16) {
                    Rectangle().fill(theme.colors.border).frame(height: 1)
                    Text("OR")
                        .font(PotomacFont.mono(size: 12))
                        .kerning(0.1)
                        .foregroundStyle(theme.colors.textMuted)
                    Rectangle().fill(theme.colors.border).frame(height: 1)
                }
                .padding(.bottom, 36)
                
                // Sign Up link
                VStack(spacing: 8) {
                    Text("Don't have an account?")
                        .font(PotomacFont.body(size: 14))
                        .foregroundStyle(theme.colors.textMuted)
                    
                    NavigationLink {
                        RegisterView()
                    } label: {
                        HStack(spacing: 8) {
                            Text("Create one")
                                .font(PotomacFont.syne(size: 13, weight: .bold))
                                .kerning(0.06)
                                .textCase(.uppercase)
                            Image(systemName: "chevron.right")
                                .font(.system(size: 14))
                        }
                        .foregroundStyle(theme.colors.accent)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(theme.colors.accent.opacity(0.08))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .strokeBorder(theme.colors.accent.opacity(0.3), lineWidth: 1)
                                )
                        )
                    }
                    .buttonStyle(.plain)
                }
                .frame(maxWidth: .infinity)
            }
            .padding(.horizontal, isMobile ? 28 : 64)
            .padding(.vertical, isMobile ? 36 : 72)
            .frame(maxWidth: 380)
            
            Spacer()
            
            // Copyright
            Text("© 2026 Potomac Fund Management. All rights reserved.")
                .font(PotomacFont.body(size: 12))
                .foregroundStyle(theme.colors.textMuted)
                .padding(.bottom, 24)
        }
        .background(theme.colors.card)
    }
    
    func signIn() async {
        isLoading = true
        error = nil
        // API call
        isLoading = false
    }
}
```

---

## 10. Dashboard

### Dashboard View

```swift
struct DashboardView: View {
    @Environment(\.theme) var theme
    @Environment(\.horizontalSizeClass) var sizeClass
    @State private var recentChats: [Conversation] = []
    @State private var stats = DashboardStats()
    
    var isMobile: Bool { sizeClass == .compact }
    
    var body: some View {
        PotomacPage {
            VStack(spacing: 0) {
                // Hero section
                heroSection
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Quick actions
                quickActions
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Recent conversations
                if !recentChats.isEmpty {
                    recentSection
                        .padding(.bottom, PotomacLayout.sectionGap)
                }
                
                // Feature cards
                featureSection
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Bottom grid
                bottomGrid
            }
        }
        .task { await loadData() }
    }
    
    var heroSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Eyebrow
            HStack(spacing: 10) {
                Circle()
                    .fill(theme.colors.accent)
                    .frame(width: 5, height: 5)
                
                Text("Trading Platform · Live")
                    .font(PotomacFont.mono(size: 9.5, weight: .medium))
                    .kerning(0.14)
                    .textCase(.uppercase)
                    .foregroundStyle(theme.colors.accent)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 5)
            .background(
                Capsule()
                    .fill(theme.colors.accent.opacity(0.07))
                    .overlay(
                        Capsule()
                            .strokeBorder(theme.colors.accent.opacity(0.2), lineWidth: 1)
                    )
            )
            .padding(.bottom, 24)
            
            // Title
            (Text("Good \(greeting), ")
                .font(PotomacFont.syne(size: isMobile ? 36 : 58, weight: .heavy))
                .tracking(-0.03)
                .foregroundStyle(theme.colors.text)
             + Text(userName)
                .font(PotomacFont.syne(size: isMobile ? 36 : 58, weight: .heavy))
                .tracking(-0.03)
                .foregroundStyle(theme.colors.accent)
            )
            
            Text("Your edge starts here.")
                .font(PotomacFont.syne(size: isMobile ? 20 : 28, weight: .regular))
                .tracking(-0.01)
                .foregroundStyle(theme.colors.textMuted)
                .padding(.top, 6)
            
            Text("AI-powered AFL generation, strategy analysis, and intelligent trading tools — purpose-built for systematic traders.")
                .font(PotomacFont.body(size: 14))
                .foregroundStyle(theme.colors.textMuted)
                .lineSpacing(6)
                .padding(.top, 20)
                .padding(.bottom, 36)
            
            // CTA buttons
            HStack(spacing: 12) {
                PotomacButton(title: "Generate AFL", icon: "sparkles") {
                    // Navigate to AFL
                }
                
                PotomacButton(title: "Open Chat", icon: "message", style: .secondary) {
                    // Navigate to Chat
                }
            }
        }
    }
    
    var quickActions: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                QuickActionButton(title: "New Chat", icon: "plus", color: PotomacColors.purple)
                QuickActionButton(title: "Generate AFL", icon: "chevron.left.forwardslash.chevron.right", color: PotomacColors.blue)
                QuickActionButton(title: "Upload Doc", icon: "doc.text", color: PotomacColors.green)
                QuickActionButton(title: "Backtest", icon: "chart.bar", color: PotomacColors.orange)
            }
        }
    }
    
    var recentSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionHeader(label: "RECENT CONVERSATIONS", action: "View All →")
            
            PotomacCard {
                ForEach(Array(recentChats.enumerated()), id: \.element.id) { idx, chat in
                    RecentChatRow(chat: chat, colors: theme.colors)
                    if idx < recentChats.count - 1 {
                        Divider()
                            .overlay(theme.colors.border)
                    }
                }
            }
        }
    }
    
    var featureSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionHeader(label: "PLATFORM TOOLS")
            
            LazyVGrid(
                columns: isMobile ? [GridItem(.flexible())] : [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())],
                spacing: 16
            ) {
                FeatureCard(
                    icon: "chevron.left.forwardslash.chevron.right",
                    title: "AFL Generator",
                    description: "Generate AmiBroker Formula Language code from plain-language descriptions.",
                    color: PotomacColors.blue,
                    sparkData: [3, 7, 5, 11, 8, 14, 10, 16, 12, 18],
                    colors: theme.colors
                )
                
                FeatureCard(
                    icon: "message",
                    title: "AI Chat",
                    description: "Discuss trading strategies and get contextual, intelligent assistance.",
                    color: PotomacColors.purple,
                    sparkData: [5, 4, 8, 6, 12, 9, 14, 11, 16, 13],
                    colors: theme.colors
                )
                
                FeatureCard(
                    icon: "cylinder.split.1x2",
                    title: "Knowledge Base",
                    description: "Upload and semantically search your trading documents and archives.",
                    color: PotomacColors.green,
                    sparkData: [2, 5, 3, 8, 6, 11, 7, 13, 9, 15],
                    colors: theme.colors
                )
                
                FeatureCard(
                    icon: "chart.line.uptrend.xyaxis",
                    title: "Backtest Analysis",
                    description: "Decode backtest reports with AI-powered performance breakdowns.",
                    color: PotomacColors.orange,
                    sparkData: [8, 6, 10, 7, 13, 9, 15, 11, 17, 14],
                    colors: theme.colors
                )
                
                FeatureCard(
                    icon: "bolt",
                    title: "Reverse Engineer",
                    description: "Convert strategy logic and descriptions directly into working AFL code.",
                    color: theme.colors.accent,
                    sparkData: [4, 8, 5, 10, 6, 14, 8, 16, 10, 18],
                    colors: theme.colors
                )
            }
        }
    }
    
    var bottomGrid: some View {
        LazyVGrid(columns: isMobile ? [GridItem(.flexible())] : [GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
            // Platform Guide
            PotomacCard(accentColor: theme.colors.accent) {
                HStack(spacing: 10) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .foregroundStyle(theme.colors.accent)
                    Text("Platform Guide")
                        .sectionTitle()
                        .foregroundStyle(theme.colors.text)
                }
                .padding(.bottom, 22)
                
                VStack(spacing: 0) {
                    GuideTip(number: "01", strong: "AFL Generator", text: " — describe any strategy in plain language.")
                    GuideTip(number: "02", strong: "AI Chat", text: " — refine logic and ask trading questions.")
                    GuideTip(number: "03", strong: "Knowledge Base", text: " — upload docs for context-aware responses.")
                    GuideTip(number: "04", strong: "Backtest Analysis", text: " — extract insights from your results.")
                    GuideTip(number: "05", strong: "Reverse Engineer", text: " — convert ideas directly to AFL code.")
                }
            }
            
            // Activity
            PotomacCard(accentColor: PotomacColors.green) {
                HStack(spacing: 10) {
                    Image(systemName: "chart.bar")
                        .foregroundStyle(PotomacColors.green)
                    Text("Activity")
                        .sectionTitle()
                        .foregroundStyle(theme.colors.text)
                }
                .padding(.bottom, 22)
                
                StatRow(label: "Total Conversations", value: "\(stats.conversations)")
                StatRow(label: "Documents Indexed", value: "\(stats.documents)")
                StatRow(label: "Platform Status", value: "Online", valueColor: PotomacColors.green)
                StatRow(label: "AI Engine", value: "Active", valueColor: theme.colors.accent)
            }
        }
    }
    
    var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        return h < 12 ? "morning" : h < 17 ? "afternoon" : "evening"
    }
    
    var userName: String { "Trader" } // Replace with actual user name
    
    func loadData() async {
        // Load conversations and stats
    }
}

struct FeatureCard: View {
    let icon: String
    let title: String
    let description: String
    let color: Color
    let sparkData: [Double]
    let colors: ThemeColors
    
    @State private var isHovered = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                // Icon
                ZStack {
                    RoundedRectangle(cornerRadius: 14)
                        .fill(
                            LinearGradient(
                                colors: [color.opacity(0.2), color.opacity(0.08)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 52, height: 52)
                        .overlay(
                            RoundedRectangle(cornerRadius: 14)
                                .strokeBorder(color.opacity(0.3), lineWidth: 1)
                        )
                        .shadow(color: color.opacity(0.2), radius: 8)
                    
                    Image(systemName: icon)
                        .font(.system(size: 22, weight: .medium))
                        .foregroundStyle(color)
                }
                
                Spacer()
                
                Sparkline(values: sparkData, color: color)
                    .padding(6)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(.white.opacity(0.02))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .strokeBorder(.white.opacity(0.05), lineWidth: 1)
                            )
                    )
            }
            .padding(.bottom, 24)
            
            Text(title)
                .font(PotomacFont.syne(size: 16, weight: .heavy))
                .tracking(-0.02)
                .foregroundStyle(colors.text)
                .padding(.bottom, 10)
            
            Text(description)
                .font(PotomacFont.body(size: 13))
                .foregroundStyle(colors.textMuted)
                .lineSpacing(4)
                .padding(.bottom, 22)
            
            // Launch button
            HStack(spacing: 8) {
                Text("Launch")
                    .font(PotomacFont.mono(size: 10, weight: .semibold))
                    .kerning(0.12)
                    .textCase(.uppercase)
                
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [color, color.opacity(0.5)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 16, height: 16)
                    .overlay(
                        Image(systemName: "arrow.up.right")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.black)
                    )
                    .shadow(color: color.opacity(0.4), radius: 4)
            }
            .foregroundStyle(color)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(color.opacity(0.08))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .strokeBorder(color.opacity(0.4), lineWidth: 1)
                    )
            )
        }
        .padding(PotomacLayout.cardPadding)
        .background(
            RoundedRectangle(cornerRadius: 20)
                .fill(colors.card)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .strokeBorder(isHovered ? colors.accent.opacity(0.4) : colors.border, lineWidth: 1)
                )
        )
        .shadow(
            color: isHovered ? colors.accent.opacity(0.2) : colors.shadow,
            radius: isHovered ? 8 : 4,
            y: 2
        )
        .onHover { hovering in
            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                isHovered = hovering
            }
        }
    }
}
```

---

## 11. Chat Interface

### Chat View (iOS)

```swift
struct ChatView: View {
    @Environment(\.theme) var theme
    @Environment(\.horizontalSizeClass) var sizeClass
    @State private var messages: [ChatMessage] = []
    @State private var inputText = ""
    @State private var isStreaming = false
    @State private var selectedModel = "claude-sonnet-4-6"
    
    var body: some View {
        VStack(spacing: 0) {
            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 24) {
                        ForEach(messages) { message in
                            MessageBubble(message: message, colors: theme.colors, logo: "PotomacIcon")
                                .id(message.id)
                        }
                        
                        if isStreaming {
                            HStack(spacing: 8) {
                                Image("PotomacIcon")
                                    .resizable()
                                    .frame(width: 18, height: 18)
                                    .clipShape(RoundedRectangle(cornerRadius: 4))
                                ShimmerText(text: "Thinking...")
                            }
                            .id("streaming")
                        }
                    }
                    .padding(.horizontal, isMobile ? 16 : 28)
                    .padding(.vertical, isMobile ? 24 : 40)
                }
                .onChange(of: messages.count) { _ in
                    withAnimation {
                        proxy.scrollTo("streaming", anchor: .bottom)
                    }
                }
            }
            
            Divider()
                .overlay(theme.colors.border)
            
            // Input bar
            inputBar
        }
        .background(ThemedBackground())
    }
    
    var inputBar: some View {
        VStack(spacing: 0) {
            // Accent line
            LinearGradient(
                colors: [.clear, PotomacColors.blue.opacity(0.35), PotomacColors.blue.opacity(0.12), .clear],
                startPoint: .leading,
                endPoint: .trailing
            )
            .frame(height: 1)
            .padding(.bottom, 12)
            
            HStack(spacing: 12) {
                // Attachment button
                Button {
                    // Open file picker
                } label: {
                    Image(systemName: "paperclip")
                        .font(.system(size: 20))
                        .foregroundStyle(theme.colors.textMuted)
                }
                .buttonStyle(.plain)
                
                // Text field
                TextField("Type a message...", text: $inputText, axis: .vertical)
                    .font(PotomacFont.body(size: 14))
                    .foregroundStyle(theme.colors.text)
                    .lineLimit(1...5)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(theme.colors.raised)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .strokeBorder(theme.colors.border, lineWidth: 1)
                            )
                    )
                
                // Send button
                Button {
                    sendMessage()
                } label: {
                    Image(systemName: isStreaming ? "stop.circle.fill" : "arrow.up.circle.fill")
                        .font(.system(size: 28))
                        .foregroundStyle(inputText.isEmpty && !isStreaming ? theme.colors.textMuted : PotomacColors.blue)
                }
                .buttonStyle(.plain)
                .disabled(inputText.isEmpty && !isStreaming)
            }
            .padding(.horizontal, isMobile ? 14 : 24)
            .padding(.vertical, 14)
            .background(
                theme.colors.background
                    .overlay(alignment: .top) {
                        Divider()
                            .overlay(theme.colors.border)
                    }
            )
        }
    }
    
    var isMobile: Bool { sizeClass == .compact }
    
    func sendMessage() {
        let text = inputText
        inputText = ""
        // Send via API
    }
}

struct MessageBubble: View {
    let message: ChatMessage
    let colors: ThemeColors
    let logo: String
    
    var body: some View {
        if message.role == "user" {
            userBubble
        } else {
            assistantBubble
        }
    }
    
    var userBubble: some View {
        HStack {
            Spacer()
            VStack(alignment: .trailing, spacing: 5) {
                Text(message.content)
                    .font(PotomacFont.body(size: 14))
                    .foregroundStyle(colors.text)
                    .padding(12)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(colors.accent.opacity(0.07))
                            .overlay(
                                RoundedRectangle(cornerRadius: 16)
                                    .strokeBorder(colors.accent.opacity(0.18), lineWidth: 1)
                            )
                    )
            }
            .frame(maxWidth: 320, alignment: .trailing)
        }
    }
    
    var assistantBubble: some View {
        HStack(alignment: .top, spacing: 12) {
            // Avatar
            Image(logo)
                .resizable()
                .frame(width: 18, height: 18)
                .clipShape(RoundedRectangle(cornerRadius: 5))
                .padding(7)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(PotomacColors.blue.opacity(0.08))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .strokeBorder(PotomacColors.blue.opacity(0.2), lineWidth: 1)
                        )
                )
            
            VStack(alignment: .leading, spacing: 6) {
                Text("Yang")
                    .font(PotomacFont.syne(size: 12, weight: .bold))
                    .tracking(-0.01)
                    .foregroundStyle(colors.text)
                
                Text(message.content)
                    .font(PotomacFont.body(size: 14))
                    .foregroundStyle(colors.text)
                    .lineSpacing(6)
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(colors.accent.opacity(0.03))
                            .overlay(
                                RoundedRectangle(cornerRadius: 16)
                                    .strokeBorder(colors.border, lineWidth: 1)
                            )
                    )
                
                // Action buttons
                HStack(spacing: 4) {
                    ActionButton(icon: "doc.on.doc", tip: "Copy")
                    ActionButton(icon: "hand.thumbsup", tip: "Helpful")
                    ActionButton(icon: "hand.thumbsdown", tip: "Not helpful")
                }
            }
            
            Spacer()
        }
    }
}
```

---

## 12. AFL Generator

### AFL Generator View

```swift
struct AFLGeneratorView: View {
    @Environment(\.theme) var theme
    @Environment(\.horizontalSizeClass) var sizeClass
    @State private var prompt = ""
    @State private var strategyType: StrategyType = .standalone
    @State private var generatedCode = ""
    @State private var isGenerating = false
    @State private var qualityScore: Double = 0
    
    var isMobile: Bool { sizeClass == .compact }
    
    var body: some View {
        PotomacPage {
            VStack(alignment: .leading, spacing: 0) {
                // Hero
                HStack(spacing: 10) {
                    Circle()
                        .fill(PotomacColors.blue)
                        .frame(width: 5, height: 5)
                    Text("Code Generation · Ready")
                        .font(PotomacFont.mono(size: 9.5, weight: .medium))
                        .kerning(0.14)
                        .textCase(.uppercase)
                        .foregroundStyle(PotomacColors.blue)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 5)
                .background(
                    Capsule()
                        .fill(PotomacColors.blue.opacity(0.07))
                        .overlay(Capsule().strokeBorder(PotomacColors.blue.opacity(0.2), lineWidth: 1))
                )
                .padding(.bottom, 24)
                
                Text("AFL Generator")
                    .font(PotomacFont.syne(size: isMobile ? 36 : 52, weight: .heavy))
                    .tracking(-0.03)
                    .foregroundStyle(PotomacColors.blue)
                    .padding(.bottom, 8)
                
                Text("Describe your trading strategy in plain language. The AI generates production-ready AmiBroker AFL code.")
                    .font(PotomacFont.body(size: 14))
                    .foregroundStyle(theme.colors.textMuted)
                    .lineSpacing(6)
                    .padding(.bottom, 40)
                
                // Strategy type picker
                HStack(spacing: 12) {
                    StrategyTypeButton(type: .standalone, isSelected: strategyType == .standalone, colors: theme.colors) {
                        strategyType = .standalone
                    }
                    StrategyTypeButton(type: .composite, isSelected: strategyType == .composite, colors: theme.colors) {
                        strategyType = .composite
                    }
                }
                .padding(.bottom, 20)
                
                // Prompt input
                PotomacCard(accentColor: PotomacColors.blue) {
                    SectionHeader(label: "STRATEGY DESCRIPTION")
                    
                    TextEditor(text: $prompt)
                        .font(PotomacFont.body(size: 14))
                        .foregroundStyle(theme.colors.text)
                        .frame(minHeight: 120)
                        .scrollContentBackground(.hidden)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(theme.colors.raised)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .strokeBorder(theme.colors.border, lineWidth: 1)
                                )
                        )
                    
                    HStack {
                        Text("\(prompt.count) / 1000 characters")
                            .font(PotomacFont.mono(size: 10))
                            .foregroundStyle(theme.colors.textMuted)
                        
                        Spacer()
                        
                        PotomacButton(title: "Generate", icon: "sparkles", isLoading: isGenerating) {
                            Task { await generate() }
                        }
                    }
                    .padding(.top, 16)
                }
                .padding(.bottom, 24)
                
                // Generated code
                if !generatedCode.isEmpty {
                    PotomacCard(accentColor: PotomacColors.green) {
                        SectionHeader(label: "GENERATED AFL CODE")
                        
                        // Quality score
                        HStack {
                            Text("Quality Score")
                                .font(PotomacFont.mono(size: 10))
                                .foregroundStyle(theme.colors.textMuted)
                            
                            Spacer()
                            
                            Text("\(Int(qualityScore))/100")
                                .font(PotomacFont.syne(size: 24, weight: .heavy))
                                .foregroundStyle(qualityScore >= 80 ? PotomacColors.green : qualityScore >= 60 ? PotomacColors.orange : PotomacColors.error)
                        }
                        .padding(.bottom, 16)
                        
                        // Code display
                        ScrollView(.horizontal, showsIndicators: false) {
                            Text(generatedCode)
                                .font(PotomacFont.mono(size: 12))
                                .foregroundStyle(theme.colors.text)
                                .padding(16)
                        }
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(theme.colors.raised)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .strokeBorder(theme.colors.border, lineWidth: 1)
                                )
                        )
                        
                        HStack(spacing: 12) {
                            PotomacButton(title: "Copy", icon: "doc.on.doc", style: .secondary) {
                                UIPasteboard.general.string = generatedCode
                            }
                            PotomacButton(title: "Optimize", icon: "arrow.triangle.2.circlepath", style: .secondary) {
                                // Optimize
                            }
                            PotomacButton(title: "Debug", icon: "ladybug", style: .secondary) {
                                // Debug
                            }
                        }
                        .padding(.top, 16)
                    }
                }
            }
        }
    }
    
    func generate() async {
        isGenerating = true
        // API call
        isGenerating = false
    }
}

enum StrategyType: String, CaseIterable {
    case standalone, composite
}

struct StrategyTypeButton: View {
    let type: StrategyType
    let isSelected: Bool
    let colors: ThemeColors
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Text(type.rawValue.capitalized)
                .font(PotomacFont.syne(size: 12, weight: .bold))
                .kerning(0.06)
                .textCase(.uppercase)
                .foregroundStyle(isSelected ? .black : colors.text)
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected ? colors.accent : colors.card)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .strokeBorder(isSelected ? colors.accent : colors.border, lineWidth: 1)
                        )
                )
                .shadow(color: isSelected ? colors.accent.opacity(0.3) : .clear, radius: 4)
        }
        .buttonStyle(.plain)
    }
}
```

---

## 13. Knowledge Base

### Knowledge Base View

```swift
struct KnowledgeBaseView: View {
    @Environment(\.theme) var theme
    @Environment(\.horizontalSizeClass) var sizeClass
    @State private var documents: [KBDoc] = []
    @State private var searchText = ""
    @State private var isUploading = false
    @State private var stats = KBStats()
    
    var isMobile: Bool { sizeClass == .compact }
    
    var body: some View {
        PotomacPage {
            VStack(alignment: .leading, spacing: 0) {
                // Hero
                heroSection
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Stats
                statsSection
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Search
                searchSection
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Upload section
                uploadSection
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Documents grid
                documentsSection
            }
        }
        .task { await loadData() }
    }
    
    var heroSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Circle()
                    .fill(PotomacColors.green)
                    .frame(width: 5, height: 5)
                Text("Knowledge Base · Indexed")
                    .font(PotomacFont.mono(size: 9.5, weight: .medium))
                    .kerning(0.14)
                    .textCase(.uppercase)
                    .foregroundStyle(PotomacColors.green)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 5)
            .background(
                Capsule()
                    .fill(PotomacColors.green.opacity(0.07))
                    .overlay(Capsule().strokeBorder(PotomacColors.green.opacity(0.2), lineWidth: 1))
            )
            .padding(.bottom, 24)
            
            Text("Knowledge Base")
                .font(PotomacFont.syne(size: isMobile ? 36 : 52, weight: .heavy))
                .tracking(-0.03)
                .foregroundStyle(PotomacColors.green)
                .padding(.bottom, 8)
            
            Text("Upload and semantically search your trading documents, strategy archives, and research materials.")
                .font(PotomacFont.body(size: 14))
                .foregroundStyle(theme.colors.textMuted)
                .lineSpacing(6)
        }
    }
    
    var statsSection: some View {
        HStack(spacing: 16) {
            StatCard(label: "Documents", value: "\(stats.totalDocs)", color: PotomacColors.green, sparkData: [2, 5, 3, 8, 6, 11, 7, 13, 9, 15])
            StatCard(label: "Chunks", value: "\(stats.totalChunks)", color: PotomacColors.blue, sparkData: [4, 7, 5, 10, 8, 13, 9, 15, 11, 17])
            StatCard(label: "Size", value: String(format: "%.1f MB", stats.totalSizeMB), color: PotomacColors.purple, sparkData: [1, 3, 2, 5, 4, 7, 6, 9, 8, 11])
        }
    }
    
    var searchSection: some View {
        PotomacCard(accentColor: PotomacColors.blue) {
            SectionHeader(label: "SEARCH KNOWLEDGE BASE")
            
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(theme.colors.textMuted)
                TextField("Search documents...", text: $searchText)
                    .font(PotomacFont.body(size: 14))
                    .foregroundStyle(theme.colors.text)
            }
            .padding(.horizontal, 16)
            .frame(height: 46)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(theme.colors.raised)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .strokeBorder(theme.colors.border, lineWidth: 1)
                    )
            )
        }
    }
    
    var uploadSection: some View {
        PotomacCard(accentColor: PotomacColors.green) {
            SectionHeader(label: "UPLOAD DOCUMENT")
            
            // Drop zone
            ZStack {
                RoundedRectangle(cornerRadius: 16)
                    .fill(PotomacColors.green.opacity(0.06))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .strokeBorder(
                                style: StrokeStyle(lineWidth: 2, dash: [8])
                            )
                            .foregroundStyle(PotomacColors.green.opacity(0.4))
                    )
                    .frame(height: 120)
                
                VStack(spacing: 8) {
                    Image(systemName: "arrow.up.doc")
                        .font(.system(size: 28))
                        .foregroundStyle(PotomacColors.green)
                    
                    Text("Drop files here or tap to browse")
                        .font(PotomacFont.body(size: 13))
                        .foregroundStyle(theme.colors.textMuted)
                    
                    Text("PDF, DOCX, TXT, CSV • Max 10 MB")
                        .font(PotomacFont.mono(size: 10))
                        .foregroundStyle(theme.colors.textDim)
                }
            }
        }
    }
    
    var documentsSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionHeader(label: "DOCUMENTS")
            
            LazyVGrid(
                columns: isMobile ? [GridItem(.flexible())] : [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())],
                spacing: 16
            ) {
                ForEach(documents) { doc in
                    DocumentCard(doc: doc, colors: theme.colors)
                }
            }
        }
    }
    
    func loadData() async {
        // Load documents and stats
    }
}
```

---

## 14. Settings

### Settings View

```swift
struct SettingsView: View {
    @Environment(\.theme) var theme
    @Environment(\.horizontalSizeClass) var sizeClass
    @State private var activeSection: SettingsSection = .profile
    @State private var profile = UserProfile()
    @State private var apiKeys = APIKeys()
    @State private var saved = false
    
    var isMobile: Bool { sizeClass == .compact }
    
    var body: some View {
        PotomacPage {
            VStack(alignment: .leading, spacing: 0) {
                // Hero
                heroSection
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Section tabs
                sectionTabs
                    .padding(.bottom, PotomacLayout.sectionGap)
                
                // Content
                sectionContent
                
                // Save button
                if activeSection != .about {
                    HStack {
                        Spacer()
                        PotomacButton(
                            title: saved ? "Saved!" : "Save Changes",
                            icon: saved ? "checkmark" : "square.and.arrow.down"
                        ) {
                            Task { await save() }
                        }
                    }
                    .padding(.top, 32)
                }
            }
        }
    }
    
    var heroSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Circle()
                    .fill(PotomacColors.accent)
                    .frame(width: 5, height: 5)
                Text("Configuration · Active")
                    .font(PotomacFont.mono(size: 9.5, weight: .medium))
                    .kerning(0.14)
                    .textCase(.uppercase)
                    .foregroundStyle(PotomacColors.accent)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 5)
            .background(
                Capsule()
                    .fill(PotomacColors.accent.opacity(0.07))
                    .overlay(Capsule().strokeBorder(PotomacColors.accent.opacity(0.2), lineWidth: 1))
            )
            .padding(.bottom, 24)
            
            Text("Settings")
                .font(PotomacFont.syne(size: isMobile ? 36 : 52, weight: .heavy))
                .tracking(-0.03)
                .foregroundStyle(PotomacColors.accent)
            
            Text("Manage your account, appearance, and preferences.")
                .font(PotomacFont.syne(size: isMobile ? 18 : 24, weight: .regular))
                .tracking(-0.01)
                .foregroundStyle(theme.colors.textMuted)
                .padding(.top, 6)
        }
    }
    
    var sectionTabs: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(SettingsSection.allCases) { section in
                    SettingsTabButton(
                        section: section,
                        isSelected: activeSection == section,
                        colors: theme.colors,
                        isMobile: isMobile
                    ) {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                            activeSection = section
                        }
                    }
                }
            }
        }
        .overlay(alignment: .bottom) {
            Divider()
                .overlay(theme.colors.border)
        }
    }
    
    @ViewBuilder
    var sectionContent: some View {
        switch activeSection {
        case .profile:
            ProfileSection(profile: $profile, colors: theme.colors, isMobile: isMobile)
        case .apiKeys:
            APIKeysSection(apiKeys: $apiKeys, colors: theme.colors)
        case .appearance:
            AppearanceSection(colors: theme.colors, isMobile: isMobile)
        case .notifications:
            NotificationsSection(colors: theme.colors)
        case .security:
            SecuritySection(colors: theme.colors)
        case .about:
            AboutSection(colors: theme.colors, isMobile: isMobile)
        }
    }
    
    func save() async {
        saved = true
        try? await Task.sleep(for: .seconds(2))
        saved = false
    }
}

enum SettingsSection: String, CaseIterable, Identifiable {
    case profile, apiKeys, appearance, notifications, security, about
    
    var id: String { rawValue }
    
    var label: String {
        switch self {
        case .profile: return "PROFILE"
        case .apiKeys: return "API KEYS"
        case .appearance: return "APPEARANCE"
        case .notifications: return "NOTIFICATIONS"
        case .security: return "SECURITY"
        case .about: return "ABOUT"
        }
    }
    
    var icon: String {
        switch self {
        case .profile: return "person"
        case .apiKeys: return "key"
        case .appearance: return "paintbrush"
        case .notifications: return "bell"
        case .security: return "shield"
        case .about: return "info.circle"
        }
    }
    
    var color: Color {
        switch self {
        case .profile: return PotomacColors.purple
        case .apiKeys: return PotomacColors.accent
        case .appearance: return PotomacColors.blue
        case .notifications: return PotomacColors.green
        case .security: return PotomacColors.orange
        case .about: return PotomacColors.pink
        }
    }
}
```

---

## 15. Platform Adaptations

### iPhone

```swift
// iPhone-specific adaptations:
// - Tab bar instead of sidebar
// - Single-column layouts
// - Sheet-based navigation for detail views
// - 20px page padding
// - Smaller typography (36px headings vs 52px)
// - Bottom sheet for settings sections
// - Full-screen modal for chat

struct iPhoneAppView: View {
    @State private var selectedTab: AppTab = .dashboard
    
    var body: some View {
        VStack(spacing: 0) {
            switch selectedTab {
            case .dashboard: DashboardView()
            case .afl: AFLGeneratorView()
            case .chat: ChatView()
            case .knowledge: KnowledgeBaseView()
            case .reverseEngineer: ReverseEngineerView()
            case .settings: SettingsView()
            }
            
            PotomacTabBar(selectedTab: $selectedTab)
        }
    }
}
```

### iPad

```swift
// iPad-specific adaptations:
// - Collapsible sidebar (auto-collapse at 768-1024px)
// - Two-column layouts where appropriate
// - 52px page padding
// - Full typography
// - NavigationSplitView

struct iPadAppView: View {
    @State private var selectedTab: AppTab = .dashboard
    @State private var sidebarCollapsed = false
    
    var body: some View {
        NavigationSplitView {
            PotomacSidebar(
                selectedTab: $selectedTab,
                isCollapsed: $sidebarCollapsed,
                user: nil
            )
        } detail: {
            switch selectedTab {
            case .dashboard: DashboardView()
            case .afl: AFLGeneratorView()
            case .chat: ChatView()
            case .knowledge: KnowledgeBaseView()
            case .reverseEngineer: ReverseEngineerView()
            case .settings: SettingsView()
            }
        }
    }
}
```

### macOS

```swift
// macOS-specific adaptations:
// - Persistent sidebar (never auto-collapses)
// - Window controls integration
// - Keyboard shortcuts
// - Menu bar integration
// - Multi-window support
// - 52px page padding
// - Full typography

struct MacAppView: View {
    @State private var selectedTab: AppTab = .dashboard
    
    var body: some View {
        NavigationSplitView {
            PotomacSidebar(
                selectedTab: $selectedTab,
                isCollapsed: .constant(false),
                user: nil
            )
            .navigationSplitViewColumnWidth(min: 256, ideal: 256, max: 256)
        } detail: {
            switch selectedTab {
            case .dashboard: DashboardView()
            case .afl: AFLGeneratorView()
            case .chat: ChatView()
            case .knowledge: KnowledgeBaseView()
            case .reverseEngineer: ReverseEngineerView()
            case .settings: SettingsView()
            }
        }
        .navigationSplitViewStyle(.balanced)
    }
}
```

### watchOS

```swift
// watchOS-specific adaptations:
// - Complications for quick stats
// - Digital Crown for scrolling
// - Simplified chat (voice-first)
// - Glanceable dashboard
// - Notification actions

struct WatchDashboardView: View {
    @Environment(\.theme) var theme
    
    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                // Status indicator
                HStack {
                    Circle()
                        .fill(PotomacColors.green)
                        .frame(width: 6, height: 6)
                    Text("Online")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                
                // Quick stats
                StatCard(label: "Chats", value: "12", color: PotomacColors.purple)
                StatCard(label: "Docs", value: "8", color: PotomacColors.green)
                
                // Quick actions
                NavigationLink {
                    WatchChatView()
                } label: {
                    Label("Chat", systemImage: "message")
                }
                
                NavigationLink {
                    WatchAFLView()
                } label: {
                    Label("AFL", systemImage: "chevron.left.forwardslash.chevron.right")
                }
            }
            .padding()
        }
        .navigationTitle("Analyst")
    }
}

struct WatchChatView: View {
    @State private var isListening = false
    
    var body: some View {
        VStack {
            if isListening {
                Image(systemName: "waveform")
                    .font(.system(size: 40))
                    .foregroundStyle(PotomacColors.accent)
                    .symbolEffect(.variableColor.iterative)
                
                Text("Listening...")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Button {
                    isListening = true
                } label: {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 30))
                }
                .buttonStyle(.plain)
            }
        }
        .navigationTitle("Chat")
    }
}
```

### visionOS

```swift
// visionOS-specific adaptations:
// - 3D card layouts
// - Hover effects with gaze
// - Immersive spaces for data visualization
// - Window-based UI with volumetric elements

struct VisionOSDashboardView: View {
    @Environment(\.theme) var theme
    
    var body: some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 300))], spacing: 24) {
                ForEach(AppTab.mainTabs) { tab in
                    VisionOSCard(tab: tab, colors: theme.colors)
                }
            }
            .padding(40)
        }
        .background(.ultraThinMaterial)
    }
}

struct VisionOSCard: View {
    let tab: AppTab
    let colors: ThemeColors
    
    var body: some View {
        NavigationLink {
            // Destination view
        } label: {
            VStack(spacing: 16) {
                Image(systemName: tab.icon)
                    .font(.system(size: 40))
                    .foregroundStyle(colors.accent)
                
                Text(tab.title)
                    .font(PotomacFont.syne(size: 18, weight: .bold))
                    .foregroundStyle(colors.text)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 200)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 24))
            .shadow(color: colors.shadow, radius: 8)
        }
        .buttonStyle(.plain)
        .hoverEffect(.lift)
    }
}
```

---

## 16. Animations & Transitions

### Entrance Animations

```swift
// Staggered fade-up (matches web's .da0 through .da5)
struct StaggeredFadeIn: ViewModifier {
    let index: Int
    
    func body(content: Content) -> some View {
        content
            .opacity(0)
            .offset(y: 22)
            .onAppear {
                withAnimation(
                    .spring(response: 0.6, dampingFraction: 0.8, blendDuration: 0)
                    .delay(Double(index) * 0.08)
                ) {
                    // Animation applied via state
                }
            }
    }
}

// Card hover lift
struct CardHoverModifier: ViewModifier {
    @State private var isHovered = false
    
    func body(content: Content) -> some View {
        content
            .scaleEffect(isHovered ? 1.02 : 1.0)
            .shadow(
                color: isHovered ? .black.opacity(0.15) : .black.opacity(0.05),
                radius: isHovered ? 12 : 4,
                y: isHovered ? 8 : 2
            )
            .onHover { hovering in
                withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                    isHovered = hovering
                }
            }
    }
}

// Pulse animation for status dots
struct PulseModifier: ViewModifier {
    @State private var isPulsing = false
    
    func body(content: Content) -> some View {
        content
            .scaleEffect(isPulsing ? 0.6 : 1.0)
            .opacity(isPulsing ? 0.3 : 1.0)
            .onAppear {
                withAnimation(
                    .easeInOut(duration: 2.4)
                    .repeatForever(autoreverses: true)
                ) {
                    isPulsing = true
                }
            }
    }
}
```

---

## 17. Accessibility

### VoiceOver Support

```swift
// All interactive elements should have:
// - .accessibilityLabel
// - .accessibilityHint
// - .accessibilityValue (for toggles, sliders)
// - .accessibilityAction for custom gestures

struct AccessibleButton: View {
    let title: String
    let hint: String
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Text(title)
        }
        .accessibilityLabel(title)
        .accessibilityHint(hint)
    }
}

// Dynamic Type support
// Use .font(.body) or .font(.headline) for system fonts
// Custom fonts should scale with Dynamic Type:
extension Font {
    static func scaledCustom(_ name: String, size: CGFloat) -> Font {
        let metrics = UIFontMetrics(forTextStyle: .body)
        let descriptor = UIFontDescriptor(fontAttributes: [.family: name])
        let uiFont = UIFont(descriptor: descriptor, size: size)
        let scaledFont = metrics.scaledFont(for: uiFont)
        return Font(scaledFont)
    }
}

// Reduce Motion support
@Environment(\.accessibilityReduceMotion) var reduceMotion

// High Contrast support
@Environment(\.accessibilityDifferentiateWithoutColor) var differentiateWithoutColor
```

---

## 18. Complete App Architecture

```swift
import SwiftUI

@main
struct AnalystApp: App {
    @State private var theme = ThemeManager()
    @State private var auth = AuthManager()
    
    var body: some Scene {
        WindowGroup {
            Group {
                if auth.isAuthenticated {
                    #if os(iOS)
                    if UIDevice.current.userInterfaceIdiom == .pad {
                        iPadAppView()
                    } else {
                        iPhoneAppView()
                    }
                    #elseif os(macOS)
                    MacAppView()
                    #elseif os(watchOS)
                    WatchDashboardView()
                    #elseif os(visionOS)
                    VisionOSDashboardView()
                    #endif
                } else {
                    LoginView()
                }
            }
            .environment(\.theme, theme)
            .environment(auth)
            .preferredColorScheme(theme.mode == .system ? nil : (theme.mode == .dark ? .dark : .light))
            .tint(theme.colors.accent)
        }
        #if os(macOS)
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified(showsTitle: true))
        #endif
        
        #if os(macOS || visionOS)
        Settings {
            SettingsView()
                .environment(\.theme, theme)
        }
        #endif
    }
}
```

---

## Quick Reference: Component → SwiftUI Mapping

| Web Component | SwiftUI Equivalent |
|---|---|
| `<div>` with styles | `VStack` / `HStack` / `ZStack` |
| `className="bg-card"` | `RoundedRectangle().fill(colors.card)` |
| `border: 1px solid var(--border)` | `.strokeBorder(colors.border, lineWidth: 1)` |
| `border-radius: 20px` | `RoundedRectangle(cornerRadius: 20)` |
| `box-shadow` | `.shadow(color:radius:y:)` |
| `display: flex` | `HStack` / `VStack` |
| `grid-template-columns` | `LazyVGrid(columns:)` |
| `position: absolute` | `.overlay(alignment:)` or `ZStack` |
| `overflow: hidden` | `.clipped()` |
| `transition` / `animation` | `.animation(_:value:)` |
| `hover` | `.onHover { }` |
| `@media (max-width: 768px)` | `@Environment(\.horizontalSizeClass)` |
| `color-scheme: dark` | `.preferredColorScheme(.dark)` |
| `font-family: Syne` | `Font.custom("Syne", size:)` or `.system(.display)` |
| `text-transform: uppercase` | `.textCase(.uppercase)` |
| `letter-spacing` | `.kerning()` |
| `opacity` | `.opacity()` |
| `background: linear-gradient` | `LinearGradient(colors:startPoint:endPoint:)` |
| `radial-gradient` | `RadialGradient(colors:center:startRadius:endRadius:)` |
| `Tailwind responsive grid` | `GridItem(.adaptive(minimum:))` |
| CSS variables (`var(--accent)`) | `@Environment(\.theme) var theme` |

---

**Last Updated:** March 2026
**Design System Version:** RC 2.0
**Platforms:** iOS 17+, iPadOS 17+, macOS 14+, watchOS 10+, visionOS 1+