import QtQuick

// Pushes crimson-core "ui" state into the Theme singleton (performance profile, visibility, ...).
QtObject {
    property var backend
    readonly property var ui: backend ? backend.ui : ({})
    readonly property var perf: ui.perf || ({})
    property list<QtObject> bindings: [
        Binding { target: Theme; property: "fps"; value: perf.fps || 30 },
        Binding { target: Theme; property: "decor"; value: perf.decor !== false },
        Binding { target: Theme; property: "glow"; value: perf.glow !== false },
        Binding { target: Theme; property: "grain"; value: perf.grain !== false },
        Binding { target: Theme; property: "borderAnim"; value: !!perf.border_anim },
        Binding { target: Theme; property: "visibleUi"; value: ui.visible !== false },
        Binding { target: Theme; property: "playing"; value: !!(backend && backend.player.playing) },
        Binding { target: Theme; property: "lyricStyle"; value: (ui.ui_cfg && ui.ui_cfg.lyrics_style === "retro") ? "retro" : "crisp" }
    ]
}
