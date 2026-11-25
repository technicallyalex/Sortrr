import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
import "."

Item {
    id: bar
    required property var targetWindow
    property alias headerContent: headerSlot.data
    property bool allowMinimize: true
    property bool allowMaximize: true
    property bool closeEnabled: true
    readonly property bool maximized: targetWindow.visibility === Window.Maximized
    property int tabHeight: 40
    readonly property int tabWidth: windowButtons.width + 40
    implicitHeight: 116

    onTabWidthChanged: headerSurface.requestPaint()
    Canvas {
        id: headerSurface
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            let ctx = getContext("2d")
            let w = width, t = bar.tabHeight, x = w - bar.tabWidth
            ctx.clearRect(0, 0, width, height)
            ctx.beginPath()
            ctx.moveTo(8, t)
            ctx.lineTo(x - 18, t)
            ctx.bezierCurveTo(x - 4, t, x - 8, 0, x + 10, 0)
            ctx.lineTo(w - 8, 0)
            ctx.quadraticCurveTo(w, 0, w, 8)
            ctx.lineTo(w, height)
            ctx.lineTo(0, height)
            ctx.lineTo(0, t + 8)
            ctx.quadraticCurveTo(0, t, 8, t)
            ctx.closePath()
            ctx.fillStyle = Theme.surface
            ctx.fill()
        }
        Connections {
            target: Theme
            function onDarkChanged() { headerSurface.requestPaint() }
        }
    }

    function toggleMaximized() {
        if (!allowMaximize) return
        if (maximized) targetWindow.showNormal()
        else targetWindow.showMaximized()
    }

    Item {
        objectName: "titleBarDragArea"
        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.right: parent.right
        DragHandler {
            target: null
            acceptedButtons: Qt.LeftButton
            onActiveChanged: if (active) bar.targetWindow.startSystemMove()
        }
        TapHandler {
            acceptedButtons: Qt.LeftButton
            onDoubleTapped: bar.toggleMaximized()
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.RightButton
            onClicked: function(mouse) { windowMenu.popup(mouse.x, mouse.y) }
        }

    }

    Item {
        id: headerSlot
        anchors.left: parent.left; anchors.bottom: parent.bottom
        anchors.top: parent.top; anchors.topMargin: bar.tabHeight
        anchors.right: parent.right
    }

    component WindowButton: Button {
        id: control
        required property string windowAction
        implicitWidth: 46
        implicitHeight: 30
        hoverEnabled: true
        padding: 0
        Accessible.name: text
        background: Rectangle {
            radius: 6
            color: control.hovered || control.down
                ? control.windowAction === "close" ? (control.down ? "#ad2939" : "#c43c4b") : Theme.raised
                : "transparent"
            border.width: control.visualFocus ? 2 : 0
            border.color: Theme.focus
        }
        contentItem: Item {
            Canvas {
                id: glyph
                width: 12; height: 12; anchors.centerIn: parent
                opacity: control.enabled ? 1 : .4
                onPaint: {
                    let ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.strokeStyle = control.hovered && control.windowAction === "close" ? "#ffffff" : Theme.ink
                    ctx.lineWidth = 1.2
                    ctx.beginPath()
                    if (control.windowAction === "minimize") {
                        ctx.moveTo(1, 8); ctx.lineTo(11, 8)
                    } else if (control.windowAction === "close") {
                        ctx.moveTo(2, 2); ctx.lineTo(10, 10)
                        ctx.moveTo(10, 2); ctx.lineTo(2, 10)
                    } else if (bar.maximized) {
                        ctx.moveTo(4, 3); ctx.lineTo(4, 1.5); ctx.lineTo(10.5, 1.5)
                        ctx.lineTo(10.5, 8); ctx.lineTo(9, 8)
                        ctx.rect(1.5, 4, 6.5, 6.5)
                    } else {
                        ctx.rect(1.5, 1.5, 9, 9)
                    }
                    ctx.stroke()
                }
                Connections {
                    target: control
                    function onHoveredChanged() { glyph.requestPaint() }
                }
                Connections {
                    target: bar
                    function onMaximizedChanged() { glyph.requestPaint() }
                }
                Connections {
                    target: Theme
                    function onDarkChanged() { glyph.requestPaint() }
                }
            }
        }
        ToolTip.visible: hovered
        ToolTip.text: text
        ToolTip.delay: 700
    }

    Row {
        id: windowButtons
        anchors.right: parent.right; anchors.rightMargin: 8
        anchors.top: parent.top; anchors.topMargin: 5
        height: 30
        spacing: 2
        WindowButton {
            objectName: "windowMinimizeButton"
            windowAction: "minimize"; text: "Minimize"
            visible: bar.allowMinimize
            onClicked: bar.targetWindow.showMinimized()
        }
        WindowButton {
            objectName: "windowMaximizeButton"
            windowAction: "maximize"; text: bar.maximized ? "Restore" : "Maximize"
            visible: bar.allowMaximize
            onClicked: bar.toggleMaximized()
        }
        WindowButton {
            objectName: "windowCloseButton"
            windowAction: "close"; text: "Close"
            enabled: bar.closeEnabled
            onClicked: bar.targetWindow.close()
        }
    }

    Menu {
        id: windowMenu
        MenuItem { text: "Restore"; enabled: bar.maximized; onTriggered: bar.targetWindow.showNormal() }
        MenuItem { text: "Minimize"; visible: bar.allowMinimize; onTriggered: bar.targetWindow.showMinimized() }
        MenuItem { text: "Maximize"; enabled: bar.allowMaximize && !bar.maximized; onTriggered: bar.targetWindow.showMaximized() }
        MenuSeparator {}
        MenuItem { text: "Close"; enabled: bar.closeEnabled; onTriggered: bar.targetWindow.close() }
    }
    Shortcut {
        sequence: "Alt+Space"
        enabled: bar.targetWindow.active
        onActivated: windowMenu.popup(12, bar.height)
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }
}
