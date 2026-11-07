import QtQuick
import QtQuick.Controls.Basic
import "."

CheckBox {
    id: control
    implicitHeight: 34
    spacing: 9
    padding: 6
    font.pixelSize: 13
    indicator: Rectangle {
        implicitWidth: 18; implicitHeight: 18
        x: control.leftPadding; y: (control.height - height) / 2
        radius: 5
        color: !control.enabled ? Theme.raised : control.checked ? Theme.accent : Theme.surface
        border.color: control.visualFocus ? Theme.focus : control.checked ? Theme.accent : Theme.quiet
        border.width: control.visualFocus ? 2 : 1
        Label {
            anchors.centerIn: parent
            visible: control.checked
            text: "✓"; color: Theme.accentForeground; font.pixelSize: 13; font.bold: true
        }
    }
}
