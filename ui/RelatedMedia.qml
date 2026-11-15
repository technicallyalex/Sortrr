import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: panel
    objectName: "relatedMediaDialog"
    required property var backend
    required property bool busy
    readonly property var parents: backend.relatedParents
    title: "Related media"
    modal: true
    width: Math.min(900, parent.width - 48)
    height: Math.min(600, parent.height - 48)
    anchors.centerIn: parent
    padding: 20
    background: Rectangle { color: Theme.surface; border.color: Theme.line; radius: 14 }
    header: Label {
        text: panel.title; padding: 20; bottomPadding: 0
        color: Theme.ink; font.pixelSize: 22; font.weight: Font.DemiBold
    }
    contentItem: ColumnLayout {
        spacing: 12
        Label {
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted
            text: "Bonus videos travel with the movie or show you choose here. They keep their descriptive names in extras subfolders. Review the final paths in Organize before applying."
        }
        ListView {
            id: list
            Layout.fillWidth: true; Layout.fillHeight: true
            model: panel.backend.relatedMedia
            spacing: 8; clip: true
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                id: entry
                required property var modelData
                width: list.width - 14
                height: content.implicitHeight + 24
                radius: 10; color: Theme.field; border.color: Theme.line
                ColumnLayout {
                    id: content
                    anchors.fill: parent; anchors.margins: 12
                    spacing: 5
                    Label {
                        Layout.fillWidth: true; text: entry.modelData.name
                        textFormat: Text.PlainText; color: Theme.ink
                        font.weight: Font.DemiBold; elide: Text.ElideMiddle
                    }
                    Label {
                        Layout.fillWidth: true; text: entry.modelData.path
                        textFormat: Text.PlainText; color: Theme.muted
                        font.pixelSize: 12; wrapMode: Text.WrapAnywhere
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        SelectBox {
                            objectName: "relatedParentBox"
                            Layout.fillWidth: true
                            model: panel.parents
                            textRole: "title"
                            currentIndex: Math.max(0,panel.parents.findIndex(p => p.path === entry.modelData.owner))
                            Accessible.name: "Related movie or show for " + entry.modelData.name
                            enabled: !panel.busy
                            onActivated: function(index) {
                                panel.backend.assignRelatedMedia(entry.modelData.path,panel.parents[index].path,entry.modelData.category)
                            }
                        }
                        SelectBox {
                            objectName: "relatedTypeBox"
                            Layout.preferredWidth: 175
                            model: panel.backend.extraTypes
                            currentIndex: model.indexOf(entry.modelData.category)
                            Accessible.name: "Bonus type for " + entry.modelData.name
                            enabled: !panel.busy
                            onActivated: panel.backend.assignRelatedMedia(entry.modelData.path,entry.modelData.owner,currentText)
                        }
                    }
                    Label {
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        text: entry.modelData.owner ? entry.modelData.reason : "Unassigned. This file will stay in the source."
                        color: entry.modelData.owner ? Theme.muted : Theme.warning
                        font.pixelSize: 12
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Label {
                Layout.fillWidth: true; color: Theme.muted; wrapMode: Text.Wrap
                text: "Unrecognized videos remain in Review. Numbered TV specials use normal episode matching."
                font.pixelSize: 12
            }
            ActionButton { text: "Done"; primary: true; onClicked: panel.close() }
        }
    }
}
