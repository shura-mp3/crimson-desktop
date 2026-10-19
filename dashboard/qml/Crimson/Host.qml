import QtQuick

// Window content shared by the layer-shell and plain-window hosts.
Item {
    id: host
    property var backend
    property var assets: ({})
    property string layoutName: "full"
    property real margin: 0                      // minimal card: gap to the screen edges

    HostBindings { backend: host.backend }
    Binding {
        target: Theme; property: "s"
        value: host.layoutName === "minimal"
               ? Math.max(0.7, (host.height - host.margin) / 170)
               : Math.max(0.55, host.height > host.width ? Math.min(host.width / 1080, host.height / 1920)
                                                         : Math.min(host.width / 1920, host.height / 1080))
    }
    Loader {
        id: content
        anchors { fill: parent; leftMargin: host.margin; topMargin: host.margin }
        anchors.rightMargin: host.layoutName === "minimal" ? host.margin : 0
        anchors.bottomMargin: host.layoutName === "minimal" ? host.margin : 0
        sourceComponent: host.layoutName === "minimal" ? mini : full
        opacity: Theme.visibleUi ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 250 } }
    }
    Component { id: full; Dashboard { backend: host.backend; assets: host.assets } }
    Component { id: mini; MiniCard { backend: host.backend; assets: host.assets } }

    function interactiveRects() {
        if (!content.item || !Theme.visibleUi) return []
        var r = content.item.interactiveRects()
        for (var i = 0; i < r.length; i++) { r[i].x += content.x; r[i].y += content.y }
        return r
    }
}
