import QtQuick

// WallpaperManager (runtime side): the dashboard paints its monitor's wallpaper itself, so tiles
// can show a perfectly aligned pre-blurred copy ("frosted glass") without compositor blur.
// Grain + scanlines add the grungy texture; grain jitters slightly (balanced/high only).
Item {
    id: root
    property string source: ""
    property string grainSource: ""
    property string scanSource: ""

    Rectangle { anchors.fill: parent; color: Theme.bg }
    Image {
        anchors.fill: parent
        source: root.source
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        smooth: true
    }
    // vignette + darkening so tiles stay legible over any wallpaper
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0.04, 0.02, 0.03, 0.45) }
            GradientStop { position: 0.5; color: Qt.rgba(0.04, 0.02, 0.03, 0.15) }
            GradientStop { position: 1.0; color: Qt.rgba(0.04, 0.02, 0.03, 0.5) }
        }
    }
    Image {
        id: grain
        visible: Theme.grain && root.grainSource !== ""
        x: -Theme.px(64); y: -Theme.px(64)
        width: parent.width + Theme.px(128); height: parent.height + Theme.px(128)
        source: root.grainSource
        fillMode: Image.Tile
        opacity: 0.09
        smooth: false
        Timer {
            running: Theme.grain && Theme.animateDecor
            interval: 110; repeat: true
            onTriggered: { grain.x = -Math.random() * Theme.px(64); grain.y = -Math.random() * Theme.px(64) }
        }
    }
    Image {
        anchors.fill: parent
        visible: root.scanSource !== ""
        source: root.scanSource
        fillMode: Image.Tile
        opacity: 0.18
        smooth: false
    }
}
