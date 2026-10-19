import QtQuick

// ClockPanel: big pixel clock, date, and three segmented load meters.
Item {
    id: root
    property var sys: ({})
    property bool h24: true
    property date now: new Date()

    Timer { interval: 1000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.now = new Date() }

    PixelText {
        id: time
        anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: Theme.px(2) }
        height: parent.height * 0.46
        text: Qt.formatTime(root.now, root.h24 ? "HH:mm" : "h:mm")
        font.pixelSize: Theme.px(110)
        fontSizeMode: Text.Fit
        pixelSize: Theme.px(3)
    }
    Text {
        id: date
        anchors { horizontalCenter: parent.horizontalCenter; top: time.bottom; topMargin: -Theme.px(4) }
        text: Qt.formatDate(root.now, "ddd dd MMM yyyy").toUpperCase() + "  ·  " + Qt.formatTime(root.now, "ss")
        font.family: Theme.labelFont; font.pixelSize: Theme.px(11)
        color: Theme.dusty
    }
    Column {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: Theme.px(16) }
        spacing: Theme.px(7)
        Repeater {
            model: [
                { k: "CPU", v: root.sys.cpu_pct },
                { k: "GPU", v: root.sys.gpu_pct },
                { k: "RAM", v: root.sys.mem_total ? root.sys.mem_used / root.sys.mem_total * 100 : undefined }
            ]
            Row {
                id: meter
                readonly property real val: modelData.v || 0
                readonly property bool known: modelData.v !== undefined && modelData.v !== null
                spacing: Theme.px(8)
                Text {
                    width: Theme.px(30); text: modelData.k
                    font.family: Theme.labelFont; font.pixelSize: Theme.px(10); color: Theme.muted
                }
                Row {
                    id: seg
                    readonly property int n: 20
                    spacing: Theme.px(2)
                    anchors.verticalCenter: parent.verticalCenter
                    Repeater {
                        model: seg.n
                        Rectangle {
                            width: Theme.px(7); height: Theme.px(8)
                            readonly property bool lit: index < Math.round(meter.val / 100 * seg.n)
                            color: lit ? (index > 15 ? Theme.pale : Theme.rose) : Theme.dim
                            opacity: lit ? 1 : 0.45
                        }
                    }
                }
                Text {
                    text: meter.known ? Math.round(meter.val) + "%" : "n/a"
                    font.family: Theme.monoFont; font.pixelSize: Theme.px(11); color: Theme.dusty
                }
            }
        }
    }
}
