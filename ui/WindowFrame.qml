import QtQuick
import QtQuick.Window
import "."
import Sortrr.Native 1.0

Item {
    id: frame
    required property var targetWindow
    anchors.fill: parent
    z: 100
    readonly property int edgeWidth: 5
    readonly property int cornerWidth: 10
    readonly property bool resizable: targetWindow.visibility !== Window.Maximized
        && targetWindow.visibility !== Window.FullScreen

    property real tabWidth: 132
    property real tabHeight: 26
    WindowShape {
        targetWindow: frame.targetWindow
    }
    Canvas {
        id: outline
        antialiasing: true
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            let ctx = getContext("2d")
            let w = width - .5, h = height - .5, r = 8
            ctx.clearRect(0, 0, width, height)
            ctx.beginPath()
            ctx.moveTo(r, .5)
            ctx.lineTo(w - r, .5)
            ctx.quadraticCurveTo(w, .5, w, r)
            ctx.lineTo(w, h - r)
            ctx.quadraticCurveTo(w, h, w - r, h)
            ctx.lineTo(r, h)
            ctx.quadraticCurveTo(.5, h, .5, h - r)
            ctx.lineTo(.5, r)
            ctx.quadraticCurveTo(.5, .5, r, .5)
            ctx.closePath()
            ctx.strokeStyle = Theme.line
            ctx.lineWidth = 1
            ctx.stroke()
        }
        Connections {
            target: Theme
            function onDarkChanged() { outline.requestPaint() }
        }
    }
    onTabWidthChanged: outline.requestPaint()
    Repeater {
        model: [
            { edges: Qt.LeftEdge, cursor: Qt.SizeHorCursor },
            { edges: Qt.RightEdge, cursor: Qt.SizeHorCursor },
            { edges: Qt.TopEdge, cursor: Qt.SizeVerCursor },
            { edges: Qt.BottomEdge, cursor: Qt.SizeVerCursor },
            { edges: Qt.TopEdge | Qt.LeftEdge, cursor: Qt.SizeFDiagCursor },
            { edges: Qt.BottomEdge | Qt.RightEdge, cursor: Qt.SizeFDiagCursor },
            { edges: Qt.TopEdge | Qt.RightEdge, cursor: Qt.SizeBDiagCursor },
            { edges: Qt.BottomEdge | Qt.LeftEdge, cursor: Qt.SizeBDiagCursor }
        ]
        delegate: MouseArea {
            required property var modelData
            readonly property bool leftEdge: !!(modelData.edges & Qt.LeftEdge)
            readonly property bool rightEdge: !!(modelData.edges & Qt.RightEdge)
            readonly property bool topEdge: !!(modelData.edges & Qt.TopEdge)
            readonly property bool bottomEdge: !!(modelData.edges & Qt.BottomEdge)
            width: leftEdge || rightEdge ? (topEdge || bottomEdge ? frame.cornerWidth : frame.edgeWidth)
                : frame.width - 2 * frame.cornerWidth
            height: topEdge || bottomEdge ? (leftEdge || rightEdge ? frame.cornerWidth : frame.edgeWidth)
                : frame.height - 2 * frame.cornerWidth
            x: leftEdge ? 0 : rightEdge ? frame.width - width : frame.cornerWidth
            y: topEdge ? 0 : bottomEdge ? frame.height - height : frame.cornerWidth
            enabled: frame.resizable
            acceptedButtons: Qt.LeftButton
            cursorShape: modelData.cursor
            onPressed: frame.targetWindow.startSystemResize(modelData.edges)
        }
    }
}
