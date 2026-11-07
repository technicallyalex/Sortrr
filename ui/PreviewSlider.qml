import QtQuick
import QtQuick.Controls.Basic
import "."

Slider {
    id: control
    implicitHeight: 28
    leftPadding: 5; rightPadding: 5
    background: Rectangle {
        x: control.leftPadding
        y: (control.height - height) / 2
        width: control.availableWidth
        height: 4
        radius: 2
        color: Theme.line
        Rectangle {
            width: parent.width * control.visualPosition
            height: parent.height
            radius: 2
            color: control.enabled ? Theme.focus : Theme.quiet
        }
    }
    handle: Rectangle {
        width: 15; height: 15; radius: 8
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2
        color: control.pressed ? Theme.accentSoft : Theme.surface
        border.width: control.visualFocus ? 3 : 2
        border.color: control.enabled ? Theme.focus : Theme.quiet
    }
}
