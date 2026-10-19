import QtQuick

// LyricsPanel: the focal point.
//   line mode - current line huge (auto-fit), previous line above and next lines below, dimmed;
//               sung words brighten when the LRC has word timestamps (karaoke).
//   word mode - the reference look: one enormous word at a time, the full line underneath.
//               Only offered when real word timestamps exist; we never invent word timings.
Item {
    id: root
    property var lyrics: ({})
    property var player: ({})
    property real position: 0
    property string displayMode: "auto"      // auto | line | word
    property real energy: 0
    signal command(string name, var args)

    readonly property var lines: lyrics.lines || []
    readonly property string status: lyrics.status || "none"
    readonly property bool hasWords: !!lyrics.has_words
    readonly property bool wordMode: hasWords && (displayMode === "word" || (displayMode === "auto" && userWordMode))
    property bool userWordMode: true
    readonly property real t: position + (lyrics.offset_ms || 0)
    readonly property int idx: lineIndex(t)
    readonly property var cur: idx >= 0 && idx < lines.length ? lines[idx] : null
    readonly property int wordIdx: wordIndex(cur, t)
    readonly property var track: player.track || ({})

    function lineIndex(tm) {
        var lo = 0, hi = lines.length - 1, ans = -1
        while (lo <= hi) {
            var mid = (lo + hi) >> 1
            if (lines[mid].t <= tm) { ans = mid; lo = mid + 1 } else hi = mid - 1
        }
        return ans
    }
    function wordIndex(line, tm) {
        if (!line || !line.w) return -1
        var n = -1
        for (var i = 0; i < line.w.length; i++) if (line.w[i][0] <= tm) n = i
        return n
    }
    function lineText(i) {
        if (i < 0 || i >= lines.length) return ""
        return lines[i].text || "♪"
    }
    function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
    function karaoke(line, wi) {
        if (!line || !line.w) return esc(line ? (line.text || "♪") : "")
        var out = ""
        for (var i = 0; i < line.w.length; i++) {
            var col = i <= wi ? Theme.pale : Qt.darker(Theme.dusty, 1.35)
            out += "<font color='" + col + "'>" + esc(line.w[i][1]) + "</font>"
        }
        return out
    }

    // ---------------- fallback / status screens ----------------
    readonly property string fallbackTitle: {
        if (!player.available) return "AWAITING SIGNAL"
        switch (status) {
        case "loading": return "SEARCHING"
        case "ad": return "ADVERTISEMENT"
        case "instrumental": return "INSTRUMENTAL"
        case "synced": return ""
        default: return (track.title || "NO LYRICS").toUpperCase()
        }
    }
    readonly property string fallbackSub: {
        if (!player.available) return "SPOTIFY IS NOT RUNNING  //  OPEN IT AND PRESS PLAY"
        switch (status) {
        case "loading": return "LOCAL .LRC  →  CACHE  →  LRCLIB.NET"
        case "plain": return "UNSYNCED LYRICS ONLY  //  READ THEM IN crimson-lyrics"
        case "none": return "NO SYNCED LYRICS FOUND  //  " + (track.artist || "").toUpperCase()
        case "error": return "LYRICS SERVICE UNREACHABLE  //  " + (root.lyrics.error || "").toUpperCase().slice(0, 70)
                             + (root.lyrics.retry_in ? "  //  RETRY IN " + root.lyrics.retry_in + "S" : "  //  CRIMSONCTL RELOAD-LYRICS")
        case "instrumental": return (track.artist || "").toUpperCase()
        default: return ""
        }
    }

    Item {
        id: fallback
        anchors.fill: parent
        visible: root.fallbackTitle !== ""
        PixelText {
            id: fbTitle
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; verticalCenterOffset: -Theme.px(14) }
            anchors.margins: Theme.px(30)
            height: parent.height * 0.5
            text: root.fallbackTitle + (root.status === "loading" ? dots.text : "")
            font.pixelSize: Theme.px(150)
            fontSizeMode: Text.Fit
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            pixelSize: Theme.px(3)
            color: root.player.available ? Theme.pale : Theme.dusty
            opacity: 0.92
        }
        Text {
            id: dots
            visible: false
            property int n: 0
            text: ".".repeat(n)
            Timer { running: root.status === "loading" && Theme.visibleUi; interval: 350; repeat: true; onTriggered: dots.n = (dots.n + 1) % 4 }
        }
        Text {
            anchors { top: fbTitle.bottom; horizontalCenter: parent.horizontalCenter; topMargin: Theme.px(6) }
            text: root.fallbackSub
            font.family: Theme.labelFont; font.pixelSize: Theme.px(12)
            color: Theme.muted
        }
    }

    // ---------------- synced: line mode ----------------
    Item {
        id: lineView
        anchors.fill: parent
        anchors.margins: Theme.px(24)
        visible: root.fallbackTitle === "" && !root.wordMode

        Text {
            id: prevLine
            anchors { left: parent.left; right: parent.right; bottom: current.top; bottomMargin: Theme.px(4) }
            horizontalAlignment: Text.AlignHCenter
            text: root.lineText(root.idx - 1)
            font.family: Theme.pixelFont; font.pixelSize: Theme.px(30)
            color: Theme.muted; opacity: 0.45
            elide: Text.ElideRight
        }
        PixelText {
            id: current
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; verticalCenterOffset: -Theme.px(10) }
            height: parent.height * 0.52
            textFormat: root.cur && root.cur.w ? Text.StyledText : Text.PlainText
            text: root.idx < 0 ? (root.track.title || "") : (root.cur && root.cur.w ? root.karaoke(root.cur, root.wordIdx) : root.lineText(root.idx))
            font.pixelSize: Theme.px(120)
            fontSizeMode: Text.Fit
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            lineHeight: 0.9
            pixelSize: Theme.px(2.5)
            color: root.idx < 0 ? Theme.dusty : Theme.pale
            transform: Translate { id: curShift; y: 0 }
        }
        Column {
            anchors { left: parent.left; right: parent.right; top: current.bottom; topMargin: Theme.px(6) }
            spacing: Theme.px(2)
            Repeater {
                model: 2
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.lineText(root.idx + 1 + index)
                    font.family: Theme.pixelFont; font.pixelSize: Theme.px(index === 0 ? 34 : 26)
                    color: index === 0 ? Theme.dusty : Theme.muted
                    opacity: index === 0 ? 0.8 : 0.4
                    elide: Text.ElideRight
                }
            }
        }

        // line change transition: settle from below + fade in
        SequentialAnimation {
            id: lineAnim
            ParallelAnimation {
                NumberAnimation { target: curShift; property: "y"; from: Theme.px(26); to: 0; duration: 260; easing.type: Easing.OutCubic }
                NumberAnimation { target: current; property: "opacity"; from: 0.25; to: 1; duration: 260; easing.type: Easing.OutQuad }
            }
        }
    }
    onIdxChanged: if (Theme.visibleUi) lineAnim.restart()

    // ---------------- synced: word mode (reference style) ----------------
    Item {
        id: wordView
        anchors.fill: parent
        anchors.margins: Theme.px(24)
        visible: root.fallbackTitle === "" && root.wordMode

        PixelText {
            id: bigWord
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; verticalCenterOffset: -Theme.px(18) }
            height: parent.height * 0.62
            text: {
                if (!root.cur || !root.cur.w) return root.idx < 0 ? "♪" : root.lineText(root.idx).toUpperCase()
                var w = root.cur.w[Math.max(0, root.wordIdx)][1].trim()
                return w.toUpperCase()
            }
            font.pixelSize: Theme.px(260)
            fontSizeMode: Text.Fit
            pixelSize: Theme.px(4)
            color: Theme.pale
            scale: 1.0
        }
        Text {
            anchors { left: parent.left; right: parent.right; top: bigWord.bottom; topMargin: Theme.px(4) }
            horizontalAlignment: Text.AlignHCenter
            textFormat: Text.StyledText
            text: root.cur && root.cur.w ? root.karaoke(root.cur, root.wordIdx) : ""
            color: Theme.dusty
            font.family: Theme.pixelFont; font.pixelSize: Theme.px(30)
            wrapMode: Text.WordWrap; maximumLineCount: 2
        }
        Text {
            anchors { left: parent.left; right: parent.right; bottom: bigWord.top }
            horizontalAlignment: Text.AlignHCenter
            text: root.lineText(root.idx - 1)
            font.family: Theme.pixelFont; font.pixelSize: Theme.px(24)
            color: Theme.muted; opacity: 0.4
            elide: Text.ElideRight
        }
        SequentialAnimation {
            id: wordPop
            NumberAnimation { target: bigWord; property: "scale"; from: 1.07; to: 1.0; duration: 160; easing.type: Easing.OutQuad }
        }
    }
    onWordIdxChanged: if (wordMode && Theme.visibleUi) wordPop.restart()

    // offset hint + mode badge
    Text {
        anchors { right: parent.right; bottom: parent.bottom; margins: Theme.px(10) }
        visible: root.status === "synced"
        text: (root.hasWords ? (root.wordMode ? "WORD SYNC" : "LINE + KARAOKE") : "LINE SYNC") + "  ·  "
              + (root.lyrics.source || "").toUpperCase() + "  ·  " + ((root.lyrics.offset_ms || 0) >= 0 ? "+" : "")
              + (root.lyrics.offset_ms || 0) + "MS"
        font.family: Theme.labelFont; font.pixelSize: Theme.px(9)
        color: Theme.dim
    }

    // wheel = nudge timing offset (saved per track); click = toggle word/line mode
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: (m) => {
            if (m.button === Qt.MiddleButton) root.command("offset", { reset: true })
            else root.userWordMode = !root.userWordMode
        }
        onWheel: (w) => root.command("offset", { delta: w.angleDelta.y > 0 ? 50 : -50 })
    }
}
