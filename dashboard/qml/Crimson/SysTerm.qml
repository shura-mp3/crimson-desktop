import QtQuick

// SystemMonitor rendered as a fake-but-truthful terminal (all values are live from /proc & /sys).
Item {
    id: root
    property var sys: ({})
    property string username: ""
    readonly property string user: username || sys.user || "rune"
    readonly property string host: (sys.host || "nobara").split(".")[0]

    function bar(pct, n) {
        if (pct === undefined || pct === null) return "[" + ".".repeat(n) + "]"
        var f = Math.round(Math.max(0, Math.min(100, pct)) / 100 * n)
        return "[" + "|".repeat(f) + " ".repeat(n - f) + "]"
    }
    function up(s) {
        if (!s) return "—"
        var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60)
        return (d ? d + "d " : "") + (h ? h + "h " : "") + m + "m"
    }
    function deg(t) { return t ? "  " + Math.round(t) + "°C" : "" }

    readonly property var logo: [
        "     /\\     ",
        "    /  \\    ",
        "   / /\\ \\   ",
        "  < <  > >  ",
        "   \\ \\/ /   ",
        "    \\  /    ",
        "     \\/     "
    ]
    readonly property var rows: [
        ["", root.user + "@" + root.host],
        ["os", sys.os || "—"],
        ["kernel", (sys.kernel || "—").split("-")[0]],
        ["wm", (sys.desktop || "KDE") + " · " + (sys.session || "wayland")],
        ["uptime", up(sys.uptime_s)],
        ["pkgs", sys.packages || "—"],
        ["cpu", bar(sys.cpu_pct, 10) + " " + Math.round(sys.cpu_pct || 0) + "%" + deg(sys.cpu_temp)],
        ["gpu", sys.gpu_pct !== undefined && sys.gpu_pct !== null ? bar(sys.gpu_pct, 10) + " " + sys.gpu_pct + "%" + deg(sys.gpu_temp) : (sys.gpu || "n/a")],
        ["memory", sys.mem_total ? bar(sys.mem_used / sys.mem_total * 100, 10) + " " + (sys.mem_used / 1024).toFixed(1) + "/" + (sys.mem_total / 1024).toFixed(1) + "G" : "—"]
    ]

    Column {
        anchors { fill: parent; margins: Theme.px(14) }
        spacing: Theme.px(2)
        Text {
            text: root.user + "@" + root.host + " ~ ❯ crimsonfetch"
            font.family: Theme.termFont; font.pixelSize: Theme.px(19)
            color: Theme.muted
        }
        Row {
            spacing: Theme.px(14)
            Column {
                topPadding: Theme.px(8)
                Repeater {
                    model: root.logo
                    Text { text: modelData; font.family: Theme.termFont; font.pixelSize: Theme.px(19); color: Theme.rose; lineHeight: 0.92 }
                }
            }
            Column {
                Repeater {
                    model: root.rows
                    Row {
                        Text {
                            width: Theme.px(72)
                            text: modelData[0]
                            font.family: Theme.termFont; font.pixelSize: Theme.px(19); color: Theme.dusty
                        }
                        Text {
                            text: modelData[1]
                            font.family: Theme.termFont; font.pixelSize: Theme.px(19)
                            color: modelData[0] === "" ? Theme.pale : Qt.rgba(0.9, 0.82, 0.86, 0.9)
                        }
                    }
                }
            }
        }
        Row {
            Text {
                text: root.user + "@" + root.host + " ~ ❯ "
                font.family: Theme.termFont; font.pixelSize: Theme.px(19)
                color: Theme.muted
            }
            Rectangle {
                width: Theme.px(9); height: Theme.px(17)
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.pale
                SequentialAnimation on opacity {
                    running: Theme.visibleUi
                    loops: Animation.Infinite
                    NumberAnimation { to: 0; duration: 1; }
                    PauseAnimation { duration: 530 }
                    NumberAnimation { to: 1; duration: 1 }
                    PauseAnimation { duration: 530 }
                }
            }
        }
    }
}
