import QtQuick
import QtQuick.Effects

// Big pixel-style typography (lyrics, clock, status titles).
//
// style "crisp" (default): the pixel font (Jersey 10) is drawn as real vector glyphs at the
//   screen's physical resolution — sharp at any KDE scale factor (100/125/150/200 %) and while
//   animating, because nothing is rasterised and scaled afterwards. CurveRendering (Qt ≥ 6.7)
//   keeps the square pixel corners exact at huge sizes; older Qt uses distance-field text.
//   A neon glow (strength: [ui] lyrics_glow) is drawn BEHIND the glyphs, so it never softens them.
// style "retro": the old chunky look — the text is drawn into a low-resolution texture and
//   enlarged with nearest-neighbour. Each block is a whole number of device pixels and glyph
//   antialiasing is off, so blocks stay hard and even at any scale factor (see 'holder').
Item {
    id: root
    property alias text: label.text
    property alias color: label.color
    property alias font: label.font
    property alias horizontalAlignment: label.horizontalAlignment
    property alias verticalAlignment: label.verticalAlignment
    property alias wrapMode: label.wrapMode
    property alias fontSizeMode: label.fontSizeMode
    property alias maximumLineCount: label.maximumLineCount
    property alias minimumPixelSize: label.minimumPixelSize
    property alias elide: label.elide
    property alias textFormat: label.textFormat
    property alias lineHeight: label.lineHeight
    property alias contentWidth: label.contentWidth
    property alias contentHeight: label.contentHeight
    property real pixelSize: 3          // retro mode: size of one block, in logical px
    property string style: Theme.lyricStyle
    readonly property bool retro: style === "retro"
    property bool glow: Theme.glow
    property color glowColor: Theme.rose
    property bool shadow: true
    property color shadowColor: Theme.bg
    // padding so wide glyphs / the shadow never touch the item edge (no clipped first/last letter)
    property real sidePadding: Theme.px(10)

    implicitWidth: label.implicitWidth
    implicitHeight: label.implicitHeight

    // physical pixels per logical pixel on the screen this item is shown on
    readonly property real dpr: Screen.devicePixelRatio > 0 ? Screen.devicePixelRatio : 1
    // retro: whole device pixels per block (≥ 2)
    readonly property int blockDevice: Math.max(2, Math.round(pixelSize * dpr))

    // ---- neon glow BEHIND the text (the text itself stays crisp on top) ----
    // Two layers: a wide soft halo and a tight bright rim. Strength comes from [ui] lyrics_glow
    // (0 = off … 1 = strong); the low performance profile turns it off.
    property real glowStrength: Theme.lyricGlow
    readonly property bool glowOn: root.glow && root.glowStrength > 0 && Theme.visibleUi && label.text !== ""
    MultiEffect {
        visible: root.glowOn
        source: root.retro ? holder : label
        x: root.retro ? 0 : label.x; y: root.retro ? 0 : label.y
        width: root.retro ? root.width : label.width; height: root.retro ? root.height : label.height
        autoPaddingEnabled: true
        blurEnabled: true
        blur: 1.0
        blurMax: 48
        blurMultiplier: 0.7
        colorization: 1.0
        colorizationColor: root.glowColor
        brightness: 0.12
        opacity: Math.min(1, 1.15 * root.glowStrength)
    }
    MultiEffect {
        visible: root.glowOn
        source: root.retro ? holder : label
        x: root.retro ? 0 : label.x; y: root.retro ? 0 : label.y
        width: root.retro ? root.width : label.width; height: root.retro ? root.height : label.height
        autoPaddingEnabled: true
        blurEnabled: true
        blur: 0.8
        blurMax: 16
        colorization: 1.0
        colorizationColor: Qt.lighter(root.glowColor, 1.3)
        opacity: Math.min(1, 1.0 * root.glowStrength)
    }

    // ---- hard drop shadow: one crisp offset copy, improves contrast over any wallpaper ----
    Text {
        id: shadowCopy
        visible: root.shadow && !root.retro && label.text !== ""
        x: label.x + Math.max(1, Math.round(label.font.pixelSize * 0.035 * root.dpr)) / root.dpr
        y: label.y + Math.max(1, Math.round(label.font.pixelSize * 0.045 * root.dpr)) / root.dpr
        width: label.width; height: label.height
        text: label.textFormat === Text.StyledText ? label.text.replace(/<font color='[^']*'>/g, "<font>") : label.text
        textFormat: label.textFormat
        font: label.font
        color: root.shadowColor
        // the glow does the separating; the dark shadow fades out as the glow gets stronger
        opacity: root.glowOn ? Math.max(0, 0.85 - 1.1 * root.glowStrength) : 0.85
        horizontalAlignment: label.horizontalAlignment
        verticalAlignment: label.verticalAlignment
        wrapMode: label.wrapMode
        fontSizeMode: label.fontSizeMode
        maximumLineCount: label.maximumLineCount
        minimumPixelSize: label.minimumPixelSize
        lineHeight: label.lineHeight
        elide: label.elide
        renderType: label.renderType
    }

    // retro: 'holder' is a 1/B-size layer (B = block size in device pixels) holding the text scaled
    // down by B, then enlarged B× without smoothing. Its texture size is left to Qt (item size ×
    // device-pixel ratio), so it is correct at every KDE scale factor — setting layer.textureSize by
    // hand is what clipped the old version at 150 % and made it vanish at 200 %.
    // crisp: holder and inner are plain 1:1 containers (no layer, no scaling).
    Item {
        id: holder
        readonly property real b: root.retro ? root.blockDevice : 1
        width: root.width / b; height: root.height / b
        transformOrigin: Item.TopLeft
        scale: b
        layer.enabled: root.retro && root.width > 0 && root.height > 0
        layer.smooth: false
        layer.mipmap: false
        Item {
            id: inner
            width: root.width; height: root.height
            transformOrigin: Item.TopLeft
            scale: 1 / holder.b
            Text {
                id: label
                anchors.fill: parent
                anchors.leftMargin: root.sidePadding; anchors.rightMargin: root.sidePadding
                font.family: Theme.pixelFont
                color: Theme.pale
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                minimumPixelSize: 8
                antialiasing: !root.retro
                // Text.CurveRendering is undefined on Qt < 6.7 → falls back to distance-field text
                renderType: Text.CurveRendering !== undefined && !root.retro ? Text.CurveRendering : Text.QtRendering
            }
        }
    }
}
