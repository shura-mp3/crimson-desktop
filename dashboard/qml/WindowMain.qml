import QtQuick
import QtQuick.Window
import Crimson

// Plain-window host. On KDE Wayland a KWin window rule (installed by apply-theme) keeps it on the
// right monitor, below other windows, borderless, out of the task bar and unfocusable.
// Also used for --demo / --screenshot runs.
Window {
    id: win
    visible: false
    color: "transparent"
    title: "Crimson Dashboard"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnBottomHint
    signal maskInvalidated()

    Host {
        id: host
        anchors.fill: parent
        backend: hostBackend; assets: hostAssets; layoutName: hostLayout
    }
    function interactiveRects() { return host.interactiveRects() }
    onWidthChanged: maskTimer.restart()
    onHeightChanged: maskTimer.restart()
    Connections { target: Theme; function onVisibleUiChanged() { maskTimer.restart() } }
    Timer { id: maskTimer; interval: 300; onTriggered: win.maskInvalidated() }
}
