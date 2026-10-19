import QtQuick
import QtQuick.Window
import org.kde.layershell 1.0 as LayerShell
import Crimson

// wlr-layer-shell host (layer-shell-qt, part of KDE Plasma). The surface lives on the BOTTOM
// layer: above the Plasma desktop/wallpaper, below every normal window, never takes keyboard
// focus, respects panels (exclusion zone 0) and is pinned to the chosen output by the host app.
Window {
    id: win
    visible: false
    color: "transparent"
    title: "Crimson Dashboard"
    signal maskInvalidated()

    readonly property bool minimal: hostLayout === "minimal"
    LayerShell.Window.scope: "crimson-dashboard"
    LayerShell.Window.layer: LayerShell.Window.LayerBottom
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: 0
    LayerShell.Window.anchors: minimal
        ? (LayerShell.Window.AnchorBottom | LayerShell.Window.AnchorRight)
        : (LayerShell.Window.AnchorTop | LayerShell.Window.AnchorBottom | LayerShell.Window.AnchorLeft | LayerShell.Window.AnchorRight)

    Host {
        id: host
        anchors.fill: parent
        backend: hostBackend; assets: hostAssets; layoutName: hostLayout
        margin: win.minimal ? Theme.px(18) : 0
    }
    function interactiveRects() { return host.interactiveRects() }
    onWidthChanged: maskTimer.restart()
    onHeightChanged: maskTimer.restart()
    Connections { target: Theme; function onVisibleUiChanged() { maskTimer.restart() } }
    Timer { id: maskTimer; interval: 300; onTriggered: win.maskInvalidated() }
}
