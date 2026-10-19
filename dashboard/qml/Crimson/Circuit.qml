import QtQuick

// Generative PCB / maze traces (the reference's top-right panel). Drawn incrementally on a
// Canvas that is never cleared until the board is "full", so each frame costs a few lineTo()s.
// Seeded from the track id: every song grows its own circuit. Brightness pulses with bass.
Item {
    id: root
    property string seed: "crimson"
    property real bass: 0
    property real energy: 0
    property bool running: Theme.animateDecor

    readonly property real step: Theme.px(14)
    property var traces: []
    property var used: ({})
    property int steps: 0
    property int cols: Math.max(2, Math.floor(width / step))
    property int rows: Math.max(2, Math.floor(height / step))
    property int rngState: 1

    function hash(s) {
        var h = 2166136261
        for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
        return h >>> 0
    }
    function rnd() {                       // mulberry32
        var t = (rngState += 0x6D2B79F5)
        t = Math.imul(t ^ (t >>> 15), t | 1)
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
    function key(x, y) { return x + "," + y }
    function spawn() {
        for (var tries = 0; tries < 30; tries++) {
            var x = Math.floor(rnd() * cols), y = Math.floor(rnd() * rows)
            if (!used[key(x, y)]) {
                used[key(x, y)] = 1
                return { x: x, y: y, d: Math.floor(rnd() * 4), len: 0, pad: true }
            }
        }
        return null
    }
    function reset() {
        rngState = hash(seed) || 1
        used = ({}); traces = []; steps = 0
        for (var i = 0; i < 7; i++) { var t = spawn(); if (t) traces.push(t) }
        canvas.clearAll = true
        canvas.requestPaint()
    }
    onSeedChanged: reset()
    onWidthChanged: resetTimer.restart()
    onHeightChanged: resetTimer.restart()
    Timer { id: resetTimer; interval: 200; onTriggered: root.reset() }
    Component.onCompleted: reset()

    Canvas {
        id: canvas
        anchors.fill: parent
        opacity: 0.55 + Math.min(1, root.bass) * 0.45
        property bool clearAll: true
        property int pending: 1

        onPaint: {
            var ctx = getContext("2d")
            var s = root.step, o = s / 2
            if (clearAll) {
                ctx.clearRect(0, 0, width, height)
                clearAll = false
                // static mode: grow a complete board in one go
                if (!root.running) pending = Math.floor(root.cols * root.rows * 0.5)
            }
            ctx.lineWidth = Math.max(1, Theme.px(1.4))
            for (var p = 0; p < pending; p++) {
                for (var i = 0; i < root.traces.length; i++) {
                    var tr = root.traces[i]
                    if (tr.pad) {
                        ctx.fillStyle = "rgba(242,183,197,0.9)"
                        ctx.fillRect(tr.x * s + o - Theme.px(3), tr.y * s + o - Theme.px(3), Theme.px(6), Theme.px(6))
                        tr.pad = false
                    }
                    // maybe turn 90 degrees
                    if (tr.len > 1 && root.rnd() < 0.28) { tr.d = (tr.d + (root.rnd() < 0.5 ? 1 : 3)) % 4; tr.len = 0 }
                    var dx = [1, 0, -1, 0][tr.d], dy = [0, 1, 0, -1][tr.d]
                    var nx = tr.x + dx, ny = tr.y + dy
                    if (nx < 0 || ny < 0 || nx >= root.cols || ny >= root.rows || root.used[root.key(nx, ny)]) {
                        // dead end: terminate with a via, start a new trace
                        ctx.strokeStyle = "rgba(213,139,159,0.8)"
                        ctx.beginPath(); ctx.arc(tr.x * s + o, tr.y * s + o, Theme.px(2.5), 0, Math.PI * 2); ctx.stroke()
                        var t2 = root.spawn()
                        if (t2) root.traces[i] = t2
                        continue
                    }
                    root.used[root.key(nx, ny)] = 1
                    ctx.strokeStyle = "rgba(213,139,159,0.55)"
                    ctx.beginPath()
                    ctx.moveTo(tr.x * s + o, tr.y * s + o)
                    ctx.lineTo(nx * s + o, ny * s + o)
                    ctx.stroke()
                    tr.x = nx; tr.y = ny; tr.len++
                    root.steps++
                }
            }
            pending = 1
            if (root.steps > root.cols * root.rows * 0.62) {
                root.rngState = (root.rngState * 31 + 7) >>> 0
                root.used = ({}); root.traces = []; root.steps = 0
                for (var k = 0; k < 7; k++) { var t3 = root.spawn(); if (t3) root.traces.push(t3) }
                clearAll = true
            }
        }
    }
    Timer {
        // growth speed follows the music
        running: root.running
        repeat: true
        interval: Math.max(Theme.frameMs, 90 - root.energy * 60)
        onTriggered: canvas.requestPaint()
    }
}
