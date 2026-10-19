import QtQuick
import QtQuick.Effects

// Big chunky pixel typography: a pixel font rendered into a low-resolution layer and scaled up
// with nearest-neighbour filtering (the look of the reference's lyric words), plus soft glow.
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
    property alias elide: label.elide
    property alias textFormat: label.textFormat
    property alias lineHeight: label.lineHeight
    property alias contentWidth: label.contentWidth
    property alias contentHeight: label.contentHeight
    property real pixelSize: 3          // size of one "pixel" block, in logical px
    property bool pixelate: Theme.pixelate
    property bool glow: Theme.glow
    property color glowColor: Theme.rose

    implicitWidth: label.implicitWidth
    implicitHeight: label.implicitHeight

    // glow: a blurred, crimson-tinted copy underneath the crisp pixel text
    MultiEffect {
        visible: root.glow && Theme.visibleUi
        source: holder
        anchors.fill: holder
        // the source is a layer texture: auto-padding would stretch it, so glow stays inside the item
        autoPaddingEnabled: false
        blurEnabled: true
        blur: 1.0
        blurMax: 40
        colorization: 1.0
        colorizationColor: root.glowColor
        blurMultiplier: 0.6
        brightness: 0.05
        opacity: 0.8
    }

    Item {
        id: holder
        anchors.fill: parent
        layer.enabled: root.pixelate && root.width > 0 && root.height > 0
        layer.smooth: false
        layer.mipmap: false
        layer.textureSize: Qt.size(Math.max(1, Math.round(root.width / root.pixelSize)),
                                   Math.max(1, Math.round(root.height / root.pixelSize)))
        Text {
            id: label
            anchors.fill: parent
            // keep glyphs off the layer edge so the glow blur doesn't smear edge pixels
            anchors.leftMargin: root.pixelSize * 8; anchors.rightMargin: root.pixelSize * 8
            font.family: Theme.pixelFont
            color: Theme.pale
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            minimumPixelSize: 8
            renderType: Text.QtRendering
        }
    }

}
