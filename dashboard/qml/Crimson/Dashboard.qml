import QtQuick

// Full "Crimson Music" layout. Panels are absolutely positioned children of this item so each
// tile can align its slice of the pre-blurred wallpaper with x/y directly.
//
// Landscape                                 Portrait (h > w)
// ┌──────────────┬───────────┬────────┐     NowPlaying / Lyrics / Spectrum+Circle /
// │ NOW PLAYING  │ CIRCUIT   │ CLOCK  │     Circuit+Clock / SysTerm+Blob
// ├──┬───────────┴─────┬─────┴────────┤
// │R │   LYRICS        │  SPECTRUM    │
// ├──┴──────────┬──────┼──────────────┤
// │ SYSTERM     │CIRCLE│  BLOB        │
// └─────────────┴──────┴──────────────┘
Item {
    id: root
    property var backend
    property var assets: ({})
    readonly property var player: backend ? backend.player : ({})
    readonly property var lyrics: backend ? backend.lyrics : ({})
    readonly property var ui: backend ? backend.ui : ({})
    readonly property var lv: backend ? backend.levels : ({})
    readonly property var uiCfg: ui.ui_cfg || ({})
    readonly property bool portrait: height > width * 1.05

    // ---------- playback clock (extrapolated locally from core anchors) ----------
    property real position: 0
    function updatePosition() {
        var p = player
        if (!p || p.pos_ms === undefined) { position = 0; return }
        var pos = p.pos_ms
        if (p.playing) pos += Date.now() - p.anchor_wall
        var len = (p.track && p.track.length_ms) || 0
        position = len > 0 ? Math.min(pos, len) : pos
    }
    Timer {
        // lyrics need ~25 Hz even in the low profile; stops entirely when hidden or paused
        interval: Math.min(40, Theme.frameMs)
        running: Theme.visibleUi && !!root.player.playing
        repeat: true
        onTriggered: root.updatePosition()
    }
    onPlayerChanged: updatePosition()

    // ---------- geometry ----------
    readonly property real m: Theme.px(16)
    readonly property real g: Theme.px(10)
    readonly property real aw: width - 2 * m
    readonly property real ah: height - 2 * m
    function rect(x0, y0, w0, h0) { return { x: m + x0, y: m + y0, w: w0, h: h0 } }

    readonly property real showRain: uiCfg.show_matrix === false ? 0 : 1
    readonly property var geo: portrait ? portraitLayout() : landscapeLayout()

    function landscapeLayout() {
        var hA = (ah - 2 * g) * 0.30, hB = (ah - 2 * g) * 0.43, hC = (ah - 2 * g) - hA - hB
        var yB = hA + g, yC = yB + hB + g
        var wA1 = (aw - 2 * g) * 0.43, wA2 = (aw - 2 * g) * 0.33, wA3 = (aw - 2 * g) - wA1 - wA2
        var wR = showRain ? (aw - 3 * g) * 0.09 : 0
        var gR = showRain ? g : 0
        var wS = (aw - 2 * g) * 0.27
        var wL = aw - wR - gR - wS - g
        var wC1 = (aw - 2 * g) * 0.36, wC2 = (aw - 2 * g) * 0.21, wC3 = (aw - 2 * g) - wC1 - wC2
        return {
            now: rect(0, 0, wA1, hA), circuit: rect(wA1 + g, 0, wA2, hA), clock: rect(wA1 + wA2 + 2 * g, 0, wA3, hA),
            rain: rect(0, yB, wR, hB), lyrics: rect(wR + gR, yB, wL, hB), spectrum: rect(wR + gR + wL + g, yB, wS, hB),
            term: rect(0, yC, wC1, hC), circle: rect(wC1 + g, yC, wC2, hC), blob: rect(wC1 + wC2 + 2 * g, yC, wC3, hC)
        }
    }
    function portraitLayout() {
        var hs = [0.17, 0.33, 0.16, 0.14, 0.20], y = 0, r = []
        var usable = ah - 4 * g
        for (var i = 0; i < hs.length; i++) { r.push([y, usable * hs[i]]); y += usable * hs[i] + g }
        var half = (aw - g) / 2
        return {
            now: rect(0, r[0][0], aw, r[0][1]), lyrics: rect(0, r[1][0], aw, r[1][1]),
            spectrum: rect(0, r[2][0], half, r[2][1]), circle: rect(half + g, r[2][0], half, r[2][1]),
            circuit: rect(0, r[3][0], half, r[3][1]), clock: rect(half + g, r[3][0], half, r[3][1]),
            term: rect(0, r[4][0], half, r[4][1]), blob: rect(half + g, r[4][0], half, r[4][1]),
            rain: rect(0, 0, 0, 0)
        }
    }

    // ---------- background ----------
    Backdrop {
        anchors.fill: parent
        source: root.assets.wallpaper || ""
        grainSource: root.assets.grain || ""
        scanSource: root.assets.scan || ""
    }

    component Tile: Panel {
        property var r: ({ x: 0, y: 0, w: 0, h: 0 })
        x: r.x; y: r.y; width: r.w; height: r.h
        visible: r.w > 1 && r.h > 1
        blurSource: root.assets.wallpaperBlur || ""
        screenW: root.width; screenH: root.height
    }

    Tile {
        id: nowTile
        r: root.geo.now; index: "01"; title: "NOW PLAYING"
        status: root.player.available ? (root.player.playing ? "LIVE" : "HOLD") : "OFFLINE"
        NowPlaying {
            id: nowPlaying
            anchors.fill: parent
            player: root.player
            artPath: root.backend ? root.backend.art : ""
            position: root.position
            spectrum: root.backend ? root.backend.spectrum : []
            onCommand: (name, args) => root.backend.command(name, args)
        }
    }
    Tile {
        r: root.geo.circuit; index: "02"; title: "SIGNAL TRACE"
        status: Theme.animateDecor ? "ROUTING" : "IDLE"
        Circuit {
            anchors.fill: parent; anchors.margins: Theme.px(6)
            visible: root.uiCfg.show_circuit !== false
            seed: (root.player.track && root.player.track.id) || "crimson"
            bass: root.lv.bass || 0; energy: root.lv.energy || 0
        }
    }
    Tile {
        r: root.geo.clock; index: "03"; title: "LOCAL TIME"
        ClockPanel { anchors.fill: parent; sys: root.backend ? root.backend.sys : ({}); h24: root.uiCfg.clock_24h !== false }
    }
    Tile {
        r: root.geo.rain; showHeader: false
        DataRain { anchors.fill: parent; anchors.margins: Theme.px(6); energy: root.lv.energy || 0 }
    }
    Tile {
        id: lyricsTile
        r: root.geo.lyrics; index: "04"; title: "LYRICS.SYS"; strong: true
        status: (root.lyrics.status || "").toUpperCase()
        LyricsPanel {
            id: lyricsPanel
            anchors.fill: parent
            lyrics: root.lyrics; player: root.player; position: root.position
            displayMode: root.ui.display_mode || "auto"
            energy: root.lv.energy || 0
            onCommand: (name, args) => root.backend.command(name, args)
        }
        Toast {
            id: toast
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: Theme.px(34) }
        }
    }
    Tile {
        r: root.geo.spectrum; index: "05"; title: "SPECTRUM"
        status: root.ui.audio_error ? "NO INPUT"
              : !root.ui.audio_source ? ""
              : "SRC " + (["system", "spotify"].indexOf(root.ui.audio_source) >= 0 ? root.ui.audio_source.toUpperCase() : "CUSTOM")
        SpectrumBars {
            anchors { fill: parent; margins: Theme.px(14) }
            values: root.backend ? root.backend.spectrum : []
            peaks: root.backend ? root.backend.peaks : []
            active: root.ui.audio_available !== false
        }
    }
    Tile {
        r: root.geo.term; index: "06"; title: "SYSTEM"
        SysTerm { anchors.fill: parent; sys: root.backend ? root.backend.sys : ({}); username: root.uiCfg.username || "" }
    }
    Tile {
        r: root.geo.circle; index: "07"; title: "WAVEFORM.RING"
        CircleViz { anchors.fill: parent; values: root.backend ? root.backend.spectrum : []; bass: root.lv.bass || 0 }
    }
    Tile {
        r: root.geo.blob; index: "08"; title: "RESONANCE"
        status: "B " + Math.round((root.lv.bass || 0) * 99) + " M " + Math.round((root.lv.mid || 0) * 99) + " H " + Math.round((root.lv.high || 0) * 99)
        PixelBlob {
            anchors.fill: parent; anchors.margins: Theme.px(4)
            visible: root.uiCfg.show_blob !== false
            bass: root.lv.bass || 0; mid: root.lv.mid || 0; high: root.lv.high || 0; energy: root.lv.energy || 0
        }
    }

    Connections {
        target: root.backend
        function onToast(text) { toast.show(text) }
    }

    // input region: only controls and the lyrics panel take clicks; the rest falls through
    function interactiveRects() {
        var out = []
        function add(item) {
            var p = item.mapToItem(root, 0, 0)
            out.push({ x: p.x, y: p.y, w: item.width, h: item.height })
        }
        var c = nowPlaying.controlRects
        for (var i = 0; i < c.length; i++) add(c[i])
        add(lyricsTile)
        return out
    }
}
