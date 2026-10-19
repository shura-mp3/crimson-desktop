import QtQuick

// AudioSpectrum: real CAVA bars (0..1) with falling peak caps. Scene-graph rectangles only (GPU-cheap).
Item {
    id: root
    property var values: []
    property var peaks: []
    property bool active: true
    readonly property int n: Math.max(1, values.length || 48)
    readonly property real bw: width / n

    // faint horizontal guide lines
    Repeater {
        model: 6
        Rectangle {
            width: root.width; height: 1
            y: root.height - (index + 1) * root.height / 6
            color: Theme.line; opacity: 0.25
        }
    }
    Repeater {
        model: root.n
        Item {
            x: index * root.bw
            width: root.bw; height: root.height
            readonly property real v: root.values[index] || 0
            Rectangle {
                anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter }
                width: Math.max(1, root.bw * 0.62)
                height: Math.max(Theme.px(2), v * root.height * 0.94)
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.rgba(0.95, 0.72, 0.77, 0.95) }
                    GradientStop { position: 0.35; color: Theme.rose }
                    GradientStop { position: 1; color: Qt.rgba(0.55, 0.14, 0.27, 0.55) }
                }
            }
            Rectangle {
                visible: (root.peaks[index] || 0) > 0.02
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.max(1, root.bw * 0.62); height: Theme.px(2)
                y: root.height - (root.peaks[index] || 0) * root.height * 0.94 - Theme.px(4)
                color: Theme.pale
            }
        }
    }
    Text {
        anchors.centerIn: parent
        visible: !root.active
        text: "AUDIO VISUALISER OFF  //  INSTALL CAVA"
        font.family: Theme.labelFont; font.pixelSize: Theme.px(10)
        color: Theme.dim
    }
}
