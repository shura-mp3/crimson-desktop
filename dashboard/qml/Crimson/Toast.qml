import QtQuick

// Short status notices from crimson-core (offset changes, GameMode, ...).
Rectangle {
    id: root
    property string text: ""
    function show(t) { text = t; anim.restart() }
    width: label.implicitWidth + Theme.px(28)
    height: Theme.px(30)
    color: Theme.crimson
    border.color: Theme.pale; border.width: 1
    opacity: 0
    visible: opacity > 0
    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        font.family: Theme.labelFont; font.pixelSize: Theme.px(12)
        color: Theme.pale
    }
    SequentialAnimation {
        id: anim
        NumberAnimation { target: root; property: "opacity"; to: 1; duration: 150 }
        PauseAnimation { duration: 1800 }
        NumberAnimation { target: root; property: "opacity"; to: 0; duration: 400 }
    }
}
