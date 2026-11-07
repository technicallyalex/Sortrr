import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: control
    property bool primary: false
    property bool subtle: false
    property bool selected: false
    implicitHeight: 40
    implicitWidth: Math.max(40, label.implicitWidth + 28)
    hoverEnabled: true
    padding: 11
    font.family: "Segoe UI"
    font.pixelSize: 13
    font.weight: primary || selected ? Font.DemiBold : Font.Medium
    contentItem: Text {
        id: label
        text: control.text
        font: control.font
        color: !control.enabled ? Theme.disabled : control.primary ? Theme.accentForeground
                               : control.selected ? Theme.accentInk : Theme.ink
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 9
        color: !control.enabled ? Theme.raised
             : control.primary ? (control.down ? Theme.accentDown : control.hovered ? Theme.accentHover : Theme.accent)
             : control.selected || control.checked ? Theme.accentSoft
             : control.hovered || control.down ? Theme.raised
             : control.subtle ? "transparent" : Theme.surface
        border.width: control.visualFocus ? 2 : control.primary || control.subtle || control.selected ? 0 : 1
        border.color: control.visualFocus ? (control.primary ? Theme.accentForeground : Theme.focus) : Theme.line
        Behavior on color { enabled: !control.subtle; ColorAnimation { duration: 100 } }
    }
    ToolTip.visible: hovered && text.length > 0 && width < label.implicitWidth + 18
    ToolTip.text: text
}
