import QtQuick
import QtQuick.Controls.Basic
import "."

RadioButton {
    id: control
    property bool alignIndicatorTop: false
    implicitHeight: 34
    spacing: 9
    padding: 6
    font.pixelSize: 13
    indicator: Rectangle {
        implicitWidth: 18; implicitHeight: 18
        x: control.padding
        y: control.alignIndicatorTop ? control.topPadding + 1 : (control.height - height) / 2
        radius: 9
        color: control.enabled ? Theme.surface : Theme.raised
        border.color: control.checked || control.visualFocus ? Theme.focus : Theme.quiet
        border.width: control.checked || control.visualFocus ? 2 : 1
        Rectangle {
            anchors.centerIn: parent
            visible: control.checked
            width: 8; height: 8; radius: 4
            color: control.enabled ? Theme.focus : Theme.quiet
        }
    }
}
