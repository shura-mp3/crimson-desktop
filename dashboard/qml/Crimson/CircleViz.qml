import QtQuick

// CircularVisualizer: the spectrum mirrored around a ring (like the reference's circular CAVA),
// with an inner ring that breathes on bass energy.
Item {
    id: root
    property var values: []
    property real bass: 0
    readonly property int n: Math.max(1, values.length || 48)
    readonly property int total: n * 2
    readonly property real radius: Math.min(width, height) * 0.27
    readonly property real maxLen: Math.min(width, height) * 0.19

    // outer tick ring
    Repeater {
        model: 72
        Rectangle {
            x: root.width / 2 - width / 2
            y: root.height / 2 - root.radius - root.maxLen - Theme.px(10)
            width: 1; height: index % 6 === 0 ? Theme.px(6) : Theme.px(3)
            color: Theme.dim
            transformOrigin: Item.Center
            transform: Rotation {
                origin.x: 0.5; origin.y: root.radius + root.maxLen + Theme.px(10)
                angle: index * 5
            }
        }
    }
    // bars: left half = spectrum low->high clockwise, right half mirrored
    Repeater {
        model: root.total
        Rectangle {
            readonly property int bin: index < root.n ? index : root.total - 1 - index
            readonly property real v: root.values[bin] || 0
            x: root.width / 2 - width / 2
            y: root.height / 2 - root.radius - height
            width: Math.max(1, Theme.px(2.2))
            height: Theme.px(2) + v * root.maxLen
            radius: width / 2
            color: v > 0.55 ? Theme.pale : Qt.rgba(0.88, 0.80, 0.84, 0.85)
            antialiasing: true
            transform: Rotation {
                origin.x: width / 2; origin.y: height + root.radius
                angle: index * 360 / root.total
            }
        }
    }
    Rectangle {
        anchors.centerIn: parent
        width: root.radius * 2 - Theme.px(6); height: width
        radius: width / 2
        color: "transparent"
        border.color: Theme.pale; border.width: Theme.px(2)
        opacity: 0.85
        scale: 1 + root.bass * 0.06
    }
    Rectangle {
        anchors.centerIn: parent
        width: root.radius * 1.4; height: width
        radius: width / 2
        color: Theme.crimson
        opacity: 0.08 + root.bass * 0.25
    }
}
