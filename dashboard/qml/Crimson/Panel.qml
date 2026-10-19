import QtQuick

// A dashboard tile: frosted wallpaper (pre-blurred image, zero runtime cost), translucent
// burgundy fill, hairline border with corner brackets, header label and optional moving accent.
Item {
    id: panel
    property string title: ""
    property string index: ""
    property string blurSource: ""      // pre-blurred wallpaper, aligned to the screen
    property real originX: x            // panel position on screen (for wallpaper alignment)
    property real originY: y
    property real screenW: 1920
    property real screenH: 1080
    property bool strong: false
    property bool showHeader: true
    property alias status: statusLabel.text
    property real headerH: showHeader ? Theme.px(22) : 0
    default property alias content: body.data
    property alias body: body

    clip: true

    Image {
        visible: panel.blurSource !== ""
        source: panel.blurSource
        x: -panel.originX; y: -panel.originY
        width: panel.screenW; height: panel.screenH
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        smooth: true
    }
    Rectangle { anchors.fill: parent; color: panel.strong ? Theme.panelFillStrong : Theme.panelFill }

    // subtle inner top gradient
    Rectangle {
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: parent.height * 0.35
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(0.95, 0.55, 0.65, 0.05) }
            GradientStop { position: 1; color: "transparent" }
        }
    }

    Rectangle { anchors.fill: parent; color: "transparent"; border.color: Qt.rgba(0.55, 0.2, 0.32, 0.55); border.width: 1 }

    // corner brackets
    Repeater {
        model: 4
        Item {
            readonly property bool r: index % 2 === 1
            readonly property bool b: index > 1
            width: Theme.px(12); height: width
            x: r ? panel.width - width : 0
            y: b ? panel.height - height : 0
            Rectangle { width: parent.width; height: 1; y: b ? parent.height - 1 : 0; color: Theme.dusty; opacity: 0.85 }
            Rectangle { width: 1; height: parent.height; x: r ? parent.width - 1 : 0; color: Theme.dusty; opacity: 0.85 }
        }
    }

    // moving accent along the top edge (high performance profile only)
    Rectangle {
        visible: Theme.borderAnim && Theme.visibleUi
        height: 1; width: panel.width * 0.18
        y: 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 0.5; color: Theme.pale }
            GradientStop { position: 1; color: "transparent" }
        }
        NumberAnimation on x {
            running: Theme.borderAnim && Theme.visibleUi
            from: -panel.width * 0.2; to: panel.width; duration: 6000 + panel.width * 2; loops: Animation.Infinite
        }
    }

    // header
    Item {
        id: header
        visible: panel.showHeader
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: panel.headerH
        Text {
            anchors { left: parent.left; leftMargin: Theme.px(14); verticalCenter: parent.verticalCenter }
            text: (panel.index ? panel.index + " // " : "") + panel.title
            font.family: Theme.labelFont; font.pixelSize: Theme.px(10)
            color: Theme.muted
        }
        Text {
            id: statusLabel
            anchors { right: squares.left; rightMargin: Theme.px(8); verticalCenter: parent.verticalCenter }
            width: Math.min(implicitWidth, panel.width * 0.4)
            elide: Text.ElideLeft
            horizontalAlignment: Text.AlignRight
            font.family: Theme.labelFont; font.pixelSize: Theme.px(9)
            color: Theme.dim
        }
        Row {
            id: squares
            anchors { right: parent.right; rightMargin: Theme.px(14); verticalCenter: parent.verticalCenter }
            spacing: Theme.px(3)
            Repeater {
                model: 3
                Rectangle {
                    width: Theme.px(4); height: width
                    color: index === 0 ? Theme.dusty : Theme.dim
                }
            }
        }
        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: Theme.px(10); rightMargin: Theme.px(10) }
            height: 1; color: Theme.line; opacity: 0.6
        }
    }

    Item {
        id: body
        anchors { fill: parent; topMargin: panel.headerH }
    }
}
