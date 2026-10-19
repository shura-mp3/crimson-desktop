pragma Singleton
import QtQuick

// ThemeManager: palette, fonts, scale and performance knobs shared by every module.
QtObject {
    // palette (tuned to the reference: dried-blood reds, dusty rose highlights)
    readonly property color bg: "#0B080D"
    readonly property color burgundy: "#230B17"
    readonly property color crimson: "#8D2445"
    readonly property color rose: "#C0485F"
    readonly property color dusty: "#D58B9F"
    readonly property color pale: "#F2B7C5"
    readonly property color muted: "#A88B98"
    readonly property color dim: "#5C3E4C"
    readonly property color line: "#6A2A40"
    readonly property color panelFill: Qt.rgba(0.10, 0.035, 0.065, 0.62)
    readonly property color panelFillStrong: Qt.rgba(0.07, 0.025, 0.045, 0.82)

    // fonts (bundled, OFL)
    readonly property string pixelFont: "Jersey 10"     // huge lyric / headline type
    readonly property string pixelAlt: "Jersey 15"
    readonly property string labelFont: "Silkscreen"    // tiny caps labels
    readonly property string termFont: "VT323"          // terminal blocks
    readonly property string monoFont: "Space Mono"     // readable numbers

    // geometry
    property real s: 1.0                 // UI scale (1.0 == 1920x1080 logical)
    function px(v) { return Math.max(1, Math.round(v * s)) }

    // performance (driven by crimson-core "ui" messages)
    property int fps: 30
    property bool decor: true            // decorative animations (circuit, rain, blob)
    property bool glow: true
    property bool grain: true
    property bool borderAnim: false
    property bool visibleUi: true
    property bool playing: false
    property string lyricStyle: "crisp"  // crisp | retro (see PixelText.qml)

    // decorative animations only run while visible + music playing
    readonly property bool animateDecor: visibleUi && decor && playing
    readonly property int frameMs: Math.round(1000 / Math.max(1, fps))
}
