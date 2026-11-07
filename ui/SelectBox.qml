import QtQuick
import QtQuick.Controls.Basic
import "."

ComboBox {
    id: control
    implicitHeight: 38
    implicitWidth: 150
    padding: 10
    spacing: 5
    font.family: "Segoe UI"
    font.pixelSize: 13
    contentItem: Text {
        text: control.displayText
        font: control.font
        color: control.enabled ? Theme.ink : Theme.disabled
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Canvas {
        x: control.width - width - 10
        y: (control.height - height) / 2
        width: 14
        height: 14
        opacity: control.enabled ? 1 : 0.55
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = Theme.muted
            ctx.lineWidth = 1.5
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.beginPath()
            ctx.moveTo(3, 5)
            ctx.lineTo(7, 9)
            ctx.lineTo(11, 5)
            ctx.stroke()
        }
    }
    background: Rectangle {
        color: control.enabled ? Theme.surface : Theme.raised
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? Theme.focus : Theme.line
        radius: 9
    }
}
