import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."
Rectangle {
    id: panel
    property var backend
    property var w: backend.wizard
    property var p: backend.playback
    readonly property var outputs: backend.audioOutputs
    readonly property string trackLabels: JSON.stringify(p.tracks || [])
    readonly property bool silent: !!p.muted || p.volume === 0
    color: Theme.field; radius: 12; border.color: Theme.line
    function clock(ms) { let s=Math.floor((ms || 0)/1000); return Math.floor(s/3600)+":"+String(Math.floor(s/60)%60).padStart(2,"0")+":"+String(s%60).padStart(2,"0") }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 8
        RowLayout { Layout.fillWidth: true
            Label { text: "SOURCE VIDEO"; color: Theme.quiet; font.pixelSize: 10; font.letterSpacing: 1.6; font.bold: true }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 112; color: Theme.media; radius: 9; clip: true
            Image { anchors.fill: parent; source: panel.w.frame || ""; fillMode: Image.PreserveAspectFit; asynchronous: true; visible: !panel.p.frameReady }
            VideoOutput { id: video; objectName: "videoOutput"; anchors.fill: parent; fillMode: VideoOutput.PreserveAspectFit; visible: !!panel.p.frameReady; Component.onCompleted: panel.backend.attachVideoSink(video.videoSink) }
            Label { anchors.centerIn: parent; text: "Press Play to preview this file"; color: Theme.mediaText; visible: !panel.w.frame && !panel.p.frameReady; font.pixelSize: 12 }
            MouseArea { anchors.fill: parent; onClicked: panel.backend.playPause() }
        }
        RowLayout { Layout.fillWidth: true; spacing: 10
            ActionButton { objectName: "playButton"; text: panel.p.playing ? "Pause" : "Play"; primary: true; implicitWidth: 72; implicitHeight: 34; onClicked: panel.backend.playPause() }
            PreviewSlider { id: seek; objectName: "seekSlider"; Accessible.name: "Playback position"; Layout.fillWidth: true; from: 0; to: panel.p.duration || 1; value: panel.p.position || 0; enabled: !!panel.p.seekable; onMoved: panel.backend.seek(Math.round(value)) }
            Label { text: panel.clock(panel.p.position)+" / "+panel.clock(panel.p.duration); color: Theme.quiet; font.pixelSize: 10; font.family: "Consolas" }
        }
        RowLayout { Layout.fillWidth: true
            SelectBox { objectName: "audioTracks"; Accessible.name: "Audio track"; Layout.fillWidth: true; implicitHeight: 32; model: JSON.parse(panel.trackLabels); currentIndex: panel.p.activeTrack === undefined ? -1 : panel.p.activeTrack; enabled: count>0; displayText: count ? currentText : "No audio track"; onActivated: panel.backend.setAudioTrack(currentIndex) }
            ActionButton {
                objectName: "audioOutputButton"
                text: "Output"; implicitHeight: 32; padding: 7
                Accessible.name: "Choose playback device"
                ToolTip.visible: hovered && !outputMenu.visible
                ToolTip.text: panel.outputs.current || "Choose a playback device"
                onClicked: outputMenu.open()
                Menu {
                    id: outputMenu
                    objectName: "audioOutputMenu"
                    width: Math.min(370, panel.width)
                    y: parent.height
                    Instantiator {
                        model: panel.outputs.names || []
                        delegate: MenuItem {
                            required property string modelData
                            required property int index
                            objectName: "audioOutputOption" + index
                            text: modelData
                            checkable: true; checked: index === panel.outputs.selected
                            onTriggered: panel.backend.setAudioOutputDevice(index)
                        }
                        onObjectAdded: function(index, item) { outputMenu.insertItem(index, item) }
                        onObjectRemoved: function(index, item) { outputMenu.removeItem(item) }
                    }
                }
            }
            ActionButton {
                objectName: "muteButton"
                text: panel.silent ? "Unmute" : "Mute"
                subtle: true; implicitWidth: 72; padding: 7; implicitHeight: 32
                onClicked: panel.backend.setMuted(!panel.silent)
            }
            PreviewSlider { Accessible.name: "Volume"; Layout.preferredWidth: 80; from: 0; to: 1; value: panel.p.volume === undefined ? 0.7 : panel.p.volume; onMoved: panel.backend.setVolume(value) }
        }
        Label {
            visible: (panel.p.tracks || []).length > 0 && !panel.outputs.current
            text: "Windows has no playback device available."
            color: Theme.danger; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Label { visible: !!panel.p.error; text: panel.p.error || ""; color: Theme.danger; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }
}
