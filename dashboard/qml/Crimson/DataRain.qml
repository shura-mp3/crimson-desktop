import QtQuick

// Column of drifting hex glyphs (the reference's left strip). Fall speed and glyph churn follow
// the music's overall energy; frozen when nothing plays.
Item {
    id: root
    property real energy: 0
    property bool running: Theme.animateDecor
    readonly property real cw: Theme.px(15)
    readonly property real ch: Theme.px(17)
    readonly property int cols: Math.max(1, Math.floor(width / cw))
    readonly property int rows: Math.max(1, Math.floor(height / ch))
    property var glyphs: []
    property var bright: []
    property var heads: []
    property var speeds: []
    readonly property string alphabet: "0123456789ABCDEF0101<>/\\:+*"

    function g() { return alphabet.charAt(Math.floor(Math.random() * alphabet.length)) }
    function init() {
        var n = cols * rows
        glyphs = []; bright = []; heads = []; speeds = []
        for (var i = 0; i < n; i++) { glyphs.push(g()); bright.push(0) }
        for (var c = 0; c < cols; c++) { heads.push(Math.random() * rows); speeds.push(0.25 + Math.random() * 0.6) }
        canvas.requestPaint()
    }
    onColsChanged: init()
    onRowsChanged: init()
    Component.onCompleted: init()

    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.font = Math.round(root.ch * 1.05) + "px 'VT323'"
            ctx.textBaseline = "top"
            for (var c = 0; c < root.cols; c++) {
                for (var r = 0; r < root.rows; r++) {
                    var i = r * root.cols + c
                    var b = root.bright[i] || 0
                    var a = 0.2 + b * 0.8
                    ctx.fillStyle = b > 0.85 ? "rgba(255,222,230," + a + ")" : "rgba(213,139,159," + a + ")"
                    ctx.fillText(root.glyphs[i] || "0", c * root.cw + Theme.px(3), r * root.ch)
                }
            }
        }
    }
    Timer {
        running: root.running && root.glyphs.length > 0
        repeat: true
        interval: Math.max(Theme.frameMs, 50)
        onTriggered: {
            var e = root.energy
            for (var c = 0; c < root.cols; c++) {
                root.heads[c] += root.speeds[c] * (0.35 + e * 1.8)
                if (root.heads[c] >= root.rows) { root.heads[c] = 0; root.speeds[c] = 0.25 + Math.random() * 0.6 }
                var hr = Math.floor(root.heads[c])
                var idx = hr * root.cols + c
                root.bright[idx] = 1
                root.glyphs[idx] = root.g()
            }
            for (var i = 0; i < root.bright.length; i++) {
                root.bright[i] *= 0.86
                if (Math.random() < 0.004 + e * 0.02) root.glyphs[i] = root.g()
            }
            canvas.requestPaint()
        }
    }
}
