import QtQuick

// Minimal profile: a compact music card (art, track, current lyric line, mini spectrum).
Item {
    id: root
    property var backend
    property var assets: ({})
    readonly property var player: backend ? backend.player : ({})
    readonly property var lyrics: backend ? backend.lyrics : ({})
    readonly property var track: player.track || ({})
    property real position: 0

    Timer {
        interval: 50; repeat: true
        running: Theme.visibleUi && !!root.player.playing
        onTriggered: {
            var p = root.player, pos = p.pos_ms || 0
            if (p.playing) pos += Date.now() - p.anchor_wall
            root.position = pos
        }
    }

    readonly property var lines: lyrics.lines || []
    readonly property int idx: {
        var t = position + (lyrics.offset_ms || 0), lo = 0, hi = lines.length - 1, ans = -1
        while (lo <= hi) { var mid = (lo + hi) >> 1; if (lines[mid].t <= t) { ans = mid; lo = mid + 1 } else hi = mid - 1 }
        return ans
    }

    Rectangle { anchors.fill: parent; color: Qt.rgba(0.05, 0.018, 0.035, 0.9) }
    Panel {
        anchors.fill: parent
        showHeader: false
        strong: true

        Image {
            id: art
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: Theme.px(12) }
            width: height
            source: root.backend && root.backend.art ? "file://" + root.backend.art : ""
            fillMode: Image.PreserveAspectCrop; asynchronous: true
            Rectangle { anchors.fill: parent; color: "transparent"; border.color: Theme.line }
            MouseArea { anchors.fill: parent; onClicked: root.backend.command("raise", {}) }
        }
        Column {
            anchors { left: art.right; right: parent.right; top: parent.top; margins: Theme.px(12) }
            spacing: Theme.px(1)
            Text {
                width: parent.width; elide: Text.ElideRight
                text: root.player.available ? (root.track.title || "—") : "SPOTIFY OFFLINE"
                font.family: Theme.pixelFont; font.pixelSize: Theme.px(28); color: Theme.pale
            }
            Text {
                width: parent.width; elide: Text.ElideRight
                text: root.track.artist || ""
                font.family: Theme.monoFont; font.pixelSize: Theme.px(12); font.bold: true; color: Theme.dusty
            }
            Text {
                width: parent.width; elide: Text.ElideRight
                topPadding: Theme.px(6)
                text: root.idx >= 0 ? (root.lines[root.idx].text || "♪") : ""
                font.family: Theme.pixelFont; font.pixelSize: Theme.px(24); color: Theme.pale
                opacity: 0.9
            }
        }
        Row {
            anchors { right: parent.right; bottom: parent.bottom; margins: Theme.px(12) }
            height: Theme.px(22); spacing: Theme.px(2)
            Repeater {
                model: 16
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: Theme.px(3)
                    height: Math.max(Theme.px(2), ((root.backend ? root.backend.spectrum[index * 3] : 0) || 0) * parent.height)
                    color: Theme.dusty
                }
            }
        }
        Rectangle {
            anchors { left: art.right; leftMargin: Theme.px(12); bottom: parent.bottom; bottomMargin: Theme.px(14) }
            width: (parent.width - art.width - Theme.px(110)) * Math.min(1, root.position / Math.max(1, root.track.length_ms || 1))
            height: Theme.px(3); color: Theme.rose
        }
    }

    function interactiveRects() {
        return [{ x: 0, y: 0, w: width, h: height }]
    }
}
