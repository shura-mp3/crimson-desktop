import QtQuick

// TrackMetadata + SpotifyController: album art, title/artist/album, progress, transport controls.
Item {
    id: root
    property var player: ({})
    property string artPath: ""
    property var lyrics: ({})
    property real position: 0
    property var spectrum: []
    signal command(string name, var args)

    readonly property var track: player.track || ({})
    readonly property real length: track.length_ms || 0
    readonly property bool online: !!player.available
    readonly property var controlRects: [artBox, controls, progress]

    function fmt(ms) {
        var s = Math.max(0, Math.floor(ms / 1000))
        return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2)
    }

    // ---------------- album art (crossfading pair) ----------------
    Item {
        id: artBox
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: Theme.px(14) }
        width: height
        property bool useA: true
        property string shown: ""

        function update() {
            var src = root.artPath ? "file://" + root.artPath : ""
            if (src === shown) return
            shown = src
            if (useA) { artB.source = src } else { artA.source = src }
            useA = !useA
        }
        Connections { target: root; function onArtPathChanged() { artBox.update() } }
        Component.onCompleted: update()

        Rectangle { anchors.fill: parent; color: Theme.burgundy; border.color: Theme.line; border.width: 1 }
        // placeholder: dither pattern + label
        Grid {
            anchors.centerIn: parent
            visible: artBox.shown === ""
            columns: 8; spacing: Theme.px(4)
            Repeater {
                model: 64
                Rectangle {
                    width: Theme.px(6); height: width
                    color: ((index + Math.floor(index / 8)) % 2) ? Theme.crimson : "transparent"
                    opacity: 0.5
                }
            }
        }
        Image {
            id: artA
            anchors.fill: parent; anchors.margins: 1
            fillMode: Image.PreserveAspectCrop; asynchronous: true; smooth: true
            opacity: artBox.useA && status === Image.Ready ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }
        }
        Image {
            id: artB
            anchors.fill: parent; anchors.margins: 1
            fillMode: Image.PreserveAspectCrop; asynchronous: true; smooth: true
            opacity: !artBox.useA && status === Image.Ready ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }
        }
        // scanline tint over the art keeps it inside the palette
        Rectangle { anchors.fill: parent; color: Theme.crimson; opacity: 0.12 }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.command("raise", {})
        }
    }

    // ---------------- metadata ----------------
    Column {
        id: meta
        anchors { left: artBox.right; leftMargin: Theme.px(18); right: parent.right; rightMargin: Theme.px(16); top: artBox.top }
        spacing: Theme.px(2)

        Text {
            text: root.online ? (root.player.playing ? "▶ NOW PLAYING" : "❚❚ PAUSED") + "  //  " + (root.player.player || "spotify").toUpperCase()
                              : "◇ NO SIGNAL  //  SPOTIFY OFFLINE"
            font.family: Theme.labelFont; font.pixelSize: Theme.px(10)
            color: root.player.playing ? Theme.dusty : Theme.muted
        }
        Text {
            width: parent.width
            text: root.track.title || (root.online ? "—" : "AWAITING SIGNAL")
            font.family: Theme.pixelFont; font.pixelSize: Theme.px(46)
            color: Theme.pale
            elide: Text.ElideRight
            lineHeight: 0.85
        }
        Text {
            width: parent.width
            text: root.track.artist || ""
            font.family: Theme.monoFont; font.pixelSize: Theme.px(16); font.bold: true
            color: Theme.dusty
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: root.track.album || ""
            font.family: Theme.monoFont; font.pixelSize: Theme.px(13)
            color: Theme.muted
            elide: Text.ElideRight
        }
    }

    // ---------------- progress ----------------
    Item {
        id: progress
        anchors { left: meta.left; right: meta.right; bottom: controls.top; bottomMargin: Theme.px(10) }
        height: Theme.px(26)
        readonly property real frac: root.length > 0 ? Math.min(1, root.position / root.length) : 0

        Text {
            anchors { left: parent.left; top: parent.top }
            text: root.fmt(root.position)
            font.family: Theme.monoFont; font.pixelSize: Theme.px(11); color: Theme.dusty
        }
        Text {
            anchors { right: parent.right; top: parent.top }
            text: root.fmt(root.length)
            font.family: Theme.monoFont; font.pixelSize: Theme.px(11); color: Theme.muted
        }
        Item {
            id: bar
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: Theme.px(8)
            // tick track
            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.px(3)
                Repeater {
                    model: Math.max(1, Math.floor(bar.width / Theme.px(6)))
                    Rectangle {
                        width: Theme.px(3); height: Theme.px(6)
                        color: (index / Math.max(1, Math.floor(bar.width / Theme.px(6)))) < progress.frac ? Theme.rose : Theme.dim
                        opacity: (index / Math.max(1, Math.floor(bar.width / Theme.px(6)))) < progress.frac ? 1 : 0.5
                    }
                }
            }
            Rectangle {
                x: progress.frac * bar.width - width / 2
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.px(4); height: Theme.px(12)
                color: Theme.pale
                visible: root.length > 0
            }
        }
        MouseArea {
            anchors.fill: bar
            anchors.margins: -Theme.px(6)
            enabled: root.length > 0
            cursorShape: Qt.PointingHandCursor
            onClicked: (m) => root.command("seek", { ms: Math.round(m.x / width * root.length) })
        }
    }

    // ---------------- transport ----------------
    Row {
        id: controls
        anchors { left: meta.left; bottom: artBox.bottom }
        spacing: Theme.px(8)
        Repeater {
            model: [
                { glyph: "◀◀", cmd: "prev" },
                { glyph: root.player.playing ? "❚❚" : "▶", cmd: "play_pause" },
                { glyph: "▶▶", cmd: "next" }
            ]
            Rectangle {
                width: Theme.px(index === 1 ? 64 : 48); height: Theme.px(34)
                color: ma.containsMouse ? Theme.crimson : Qt.rgba(0.55, 0.14, 0.27, 0.25)
                border.color: index === 1 ? Theme.dusty : Theme.line
                border.width: 1
                Text {
                    anchors.centerIn: parent
                    text: modelData.glyph
                    font.pixelSize: Theme.px(index === 1 ? 16 : 13)
                    color: Theme.pale
                }
                MouseArea {
                    id: ma
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.command(modelData.cmd, {})
                }
            }
        }
    }

    // ---------------- mini spectrum + lyric source info ----------------
    Row {
        anchors { right: meta.right; bottom: artBox.bottom }
        height: Theme.px(34)
        spacing: Theme.px(2)
        Repeater {
            model: 18
            Rectangle {
                anchors.bottom: parent.bottom
                width: Theme.px(4)
                height: Math.max(Theme.px(2), (root.spectrum[index * 2] || 0) * parent.height)
                color: Theme.dusty
                opacity: 0.4 + 0.6 * (root.spectrum[index * 2] || 0)
            }
        }
    }
}
