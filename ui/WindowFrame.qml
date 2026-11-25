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
        tabWidth: frame.tabWidth
        tabHeight: frame.tabHeight
    }
    Canvas {
        id: outline
        antialiasing: true
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            let ctx = getContext("2d")
            let w = width - .5, h = height - .5, t = frame.tabHeight + .5
            let x = width - frame.tabWidth
            ctx.clearRect(0, 0, width, height)
            ctx.beginPath()
            ctx.moveTo(8, t)
            ctx.lineTo(x - 18, t)
            ctx.bezierCurveTo(x - 4, t, x - 8, .5, x + 10, .5)
            ctx.lineTo(w - 8, .5)
            ctx.quadraticCurveTo(w, .5, w, 8)
            ctx.lineTo(w, h - 8)
            ctx.quadraticCurveTo(w, h, w - 8, h)
            ctx.lineTo(8, h)
            ctx.quadraticCurveTo(.5, h, .5, h - 8)
            ctx.lineTo(.5, t + 8)
            ctx.quadraticCurveTo(.5, t, 8, t)
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
    MouseArea {
        x: frame.width - frame.tabWidth + 10
        y: 0; width: frame.tabWidth - 20; height: frame.edgeWidth
        enabled: frame.resizable
        cursorShape: Qt.SizeVerCursor
        onPressed: frame.targetWindow.startSystemResize(Qt.TopEdge)
    }
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
            width: modelData.edges === Qt.TopEdge ? frame.width - frame.tabWidth - 24
                : leftEdge || rightEdge ? (topEdge || bottomEdge ? frame.cornerWidth : frame.edgeWidth)
                : frame.width - 2 * frame.cornerWidth
            height: topEdge || bottomEdge ? (leftEdge || rightEdge ? frame.cornerWidth : frame.edgeWidth)
                : frame.height - 2 * frame.cornerWidth - (leftEdge ? frame.tabHeight : 0)
            x: leftEdge ? 0 : rightEdge ? frame.width - width : frame.cornerWidth
            y: topEdge ? (rightEdge ? 0 : frame.tabHeight)
                : bottomEdge ? frame.height - height
                : frame.cornerWidth + (leftEdge ? frame.tabHeight : 0)
            enabled: frame.resizable
            acceptedButtons: Qt.LeftButton
            cursorShape: modelData.cursor
            onPressed: frame.targetWindow.startSystemResize(modelData.edges)
        }
    }
}
