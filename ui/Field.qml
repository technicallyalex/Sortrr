import QtQuick
import QtQuick.Controls.Basic
import "."

TextField {
    id: field
    implicitHeight: 40
    font.family: "Segoe UI"
    font.pixelSize: 13
    color: Theme.ink
    placeholderTextColor: Theme.quiet
    leftPadding: 12
    rightPadding: 12
    selectByMouse: true
    selectionColor: Theme.accentSoft
    selectedTextColor: Theme.accentInk
    background: Rectangle {
        radius: 9
        color: field.enabled ? Theme.field : Theme.raised
        border.width: field.activeFocus ? 2 : 1
        border.color: field.activeFocus ? Theme.focus : Theme.line
    }
}
