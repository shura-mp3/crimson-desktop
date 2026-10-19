import QtQuick

// Low-resolution metaball "blob" (the reference's big pink shape). Each ball's size is driven by
// a frequency band (bass / mid / high) so the shape swells with the music; dithered edges.
Item {
    id: root
    property real bass: 0
    property real mid: 0
    property real high: 0
    property real energy: 0
    property bool running: Theme.animateDecor
    readonly property real cell: Theme.px(10)
    readonly property int cols: Math.max(1, Math.floor(width / cell))
    readonly property int rows: Math.max(1, Math.floor(height / cell))
    property real phase: 0

    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            var C = root.cols, R = root.rows, cs = root.cell, ph = root.phase
            var m = Math.min(C, R)
            var bands = [root.bass, root.mid, root.high, root.bass, root.mid]
            var balls = []
            for (var b = 0; b < 5; b++) {
                var sp = 0.45 + b * 0.17
                balls.push({
                    x: C * (0.5 + 0.30 * Math.sin(ph * sp + b * 1.7)),
                    y: R * (0.5 + 0.28 * Math.cos(ph * (sp * 0.8) + b * 2.3)),
                    r: m * (0.11 + 0.06 * (b % 3)) * (0.85 + bands[b] * 0.75)
                })
            }
            var solid = [], edge = [], core = []
            for (var y = 0; y < R; y++) {
                for (var x = 0; x < C; x++) {
                    var f = 0
                    for (var k = 0; k < 5; k++) {
                        var dx = x - balls[k].x, dy = y - balls[k].y
                        f += balls[k].r * balls[k].r / (dx * dx + dy * dy + 0.5)
                    }
                    if (f > 2.4) core.push(x, y)
                    else if (f > 1.0) solid.push(x, y)
                    else if (f > 0.78 && ((x + y) & 1) === 0) edge.push(x, y)
                }
            }
            var g = cs - 1
            ctx.fillStyle = "rgba(213,139,159,0.30)"
            for (var i = 0; i < edge.length; i += 2) ctx.fillRect(edge[i] * cs, edge[i + 1] * cs, g, g)
            ctx.fillStyle = "rgba(213,139,159,0.55)"
            for (i = 0; i < solid.length; i += 2) ctx.fillRect(solid[i] * cs, solid[i + 1] * cs, g, g)
            ctx.fillStyle = "rgba(242,183,197,0.68)"
            for (i = 0; i < core.length; i += 2) ctx.fillRect(core[i] * cs, core[i + 1] * cs, g, g)
        }
    }
    Timer {
        running: root.running
        repeat: true
        interval: Math.max(Theme.frameMs, 33)
        onTriggered: {
            root.phase += (interval / 1000) * (0.25 + root.energy * 1.1)
            canvas.requestPaint()
        }
    }
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
}
