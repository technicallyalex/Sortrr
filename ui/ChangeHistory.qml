import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: history
    objectName: "changeHistoryDialog"
    required property var backend
    required property bool busy
    required property string resultText
    property var runs: backend.changeHistory
    property var selectedRun: null
    property var changes: []
    property var checks: ({})
    property var matches: []
    readonly property bool searching: searchField.text.trim().length > 0
    readonly property var checkedIds: Object.keys(checks).filter(id => checks[id])

    title: "Change history"
    modal: true
    width: Math.min(1020, parent.width - 48)
    height: Math.min(680, parent.height - 48)
    padding: 20
    anchors.centerIn: parent
    onAboutToShow: backend.loadChangeHistory()
    onRunsChanged: {
        let current = selectedRun ? runs.find(run => run.id === selectedRun.id) : null
        selectRun(current || (runs.length ? runs[0] : null))
        if (searchField) refreshSearch()
    }
    function refreshSearch() {
        matches = backend.searchFileHistory(searchField.text)
        if (matchList) matchList.positionViewAtBeginning()
    }
    Timer { id: searchDelay; interval: 120; onTriggered: history.refreshSearch() }

    function selectRun(run) {
        selectedRun = run
        changes = run ? backend.fileChanges(run.id) : []
        checks = ({})
        if (changeList) changeList.positionViewAtBeginning()
    }

    background: Rectangle { color: Theme.surface; radius: 14; border.color: Theme.line }
    header: Label {
        text: history.title; color: Theme.ink
        font.pixelSize: 22; font.weight: Font.DemiBold; padding: 20; bottomPadding: 0
    }

    component Detail: Label {
        color: Theme.muted
        font.pixelSize: 13
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
    }

    component PathLabel: Label {
        Layout.fillWidth: true
        color: Theme.ink; font.pixelSize: 12
        textFormat: Text.PlainText
        elide: Text.ElideMiddle
        HoverHandler { id: hover }
        ToolTip.visible: hover.hovered && truncated
        ToolTip.text: text
    }

    contentItem: ColumnLayout {
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Field {
                id: searchField
                objectName: "changeHistorySearch"
                Layout.fillWidth: true
                placeholderText: "Search every operation by file name or path"
                Accessible.name: "Search change history"
                onTextChanged: searchDelay.restart()
                onAccepted: history.refreshSearch()
            }
            ActionButton {
                text: "Clear search"
                visible: history.searching
                onClicked: { searchField.clear(); searchField.forceActiveFocus() }
            }
        }
        Detail {
            Layout.fillWidth: true
            text: history.searching ? "Matches across all operations (" + history.matches.length + ")"
                : "Browse past operations or search for a file by any recorded name."
        }

        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            visible: history.searching
            color: Theme.field; border.color: Theme.line; radius: 10
            ListView {
                id: matchList
                anchors.fill: parent; anchors.margins: 6
                clip: true; spacing: 5; model: history.matches
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    id: match
                    required property var modelData
                    width: ListView.view.width - 10
                    height: matchRow.implicitHeight + 20
                    radius: 7; color: Theme.surface
                    RowLayout {
                        id: matchRow
                        anchors.fill: parent; anchors.margins: 10; spacing: 12
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 3
                            PathLabel {
                                text: match.modelData.name
                                font.pixelSize: 14; font.weight: Font.DemiBold
                            }
                            PathLabel { text: "Original  " + match.modelData.original }
                            PathLabel { text: "Latest recorded path  " + match.modelData.current }
                            Detail {
                                Layout.fillWidth: true
                                text: (match.modelData.status || ((match.modelData.copy ? "Copy  ·  " : "")
                                    + match.modelData.count + (match.modelData.count === 1 ? " recorded change" : " recorded changes")))
                                    + "  ·  " + match.modelData.date
                                color: match.modelData.status === "Reverted" ? Theme.success : Theme.muted
                                font.pixelSize: 12
                            }
                        }
                        ActionButton {
                            objectName: "restoreOriginalButton"
                            text: "Restore original"
                            Accessible.name: "Restore original for " + match.modelData.name
                            visible: match.modelData.canRestore
                            enabled: !history.busy
                            onClicked: history.backend.prepareOriginalRestore(match.modelData.id)
                        }
                    }
                }
            }
            Detail {
                anchors.fill: parent; anchors.margins: 12
                visible: !history.matches.length && !searchDelay.running
                text: history.busy ? "Loading history…" : "No recorded paths match your search."
            }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            visible: !history.searching
            Rectangle {
                Layout.preferredWidth: 228; Layout.fillHeight: true
                color: Theme.field; border.color: Theme.line; radius: 10
                ListView {
                    anchors.fill: parent; anchors.margins: 6
                    clip: true; spacing: 4; model: history.runs
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Button {
                        id: runButton
                        required property var modelData
                        width: ListView.view.width - 10
                        padding: 9
                        hoverEnabled: true
                        Accessible.name: modelData.label + ", " + modelData.date
                        readonly property bool current: !!history.selectedRun && history.selectedRun.id === modelData.id
                        onClicked: history.selectRun(modelData)
                        background: Rectangle {
                            radius: 7
                            color: runButton.current ? Theme.accentSoft : runButton.hovered ? Theme.raised : "transparent"
                            border.width: runButton.visualFocus ? 2 : 0
                            border.color: Theme.focus
                        }
                        contentItem: ColumnLayout {
                            spacing: 3
                            Label {
                                Layout.fillWidth: true
                                text: runButton.modelData.label; textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                color: runButton.current ? Theme.accentInk : Theme.ink
                                font.pixelSize: 13; font.weight: Font.DemiBold
                            }
                            Detail { Layout.fillWidth: true; text: runButton.modelData.date; font.pixelSize: 12 }
                            Detail {
                                Layout.fillWidth: true; font.pixelSize: 12
                                text: runButton.modelData.error
                                    || (runButton.modelData.count + (runButton.modelData.count === 1 ? " change" : " changes")
                                    + (runButton.modelData.reverted ? " · " + runButton.modelData.reverted + " reverted" : ""))
                            }
                        }
                    }
                }
                Detail {
                    anchors.fill: parent; anchors.margins: 12
                    visible: !history.runs.length
                    text: history.busy ? "Loading operations…" : "No recorded operations"
                }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: Theme.field; border.color: Theme.line; radius: 10
                ListView {
                    id: changeList
                    anchors.fill: parent; anchors.margins: 6
                    clip: true; spacing: 4; model: history.changes
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Rectangle {
                        id: changeRow
                        required property var modelData
                        width: ListView.view.width - 10
                        height: row.implicitHeight + 18
                        radius: 7
                        color: history.checks[modelData.id] ? Theme.accentSoft : Theme.surface
                        RowLayout {
                            id: row
                            anchors.fill: parent; anchors.margins: 9
                            spacing: 8
                            ChoiceCheck {
                                objectName: "revertCheck_" + changeRow.modelData.id
                                Layout.alignment: Qt.AlignTop
                                visible: changeRow.modelData.reversible
                                enabled: !history.busy
                                checked: !!history.checks[changeRow.modelData.id]
                                Accessible.name: "Select " + changeRow.modelData.source
                                onToggled: {
                                    let updated = Object.assign({}, history.checks)
                                    updated[changeRow.modelData.id] = checked
                                    history.checks = updated
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 3
                                Label {
                                    Layout.fillWidth: true
                                    text: changeRow.modelData.label + (changeRow.modelData.status ? " · " + changeRow.modelData.status : "")
                                    textFormat: Text.PlainText; wrapMode: Text.Wrap
                                    color: changeRow.modelData.status === "Reverted" ? Theme.success : Theme.ink
                                    font.pixelSize: 13; font.weight: Font.DemiBold
                                }
                                PathLabel { text: "Original  " + changeRow.modelData.source }
                                PathLabel {
                                    visible: changeRow.modelData.mode !== "rmdir" && changeRow.modelData.mode !== "recycle"
                                    text: "Destination  " + changeRow.modelData.target
                                }
                            }
                        }
                    }
                }
                Detail {
                    anchors.fill: parent; anchors.margins: 12
                    visible: !history.changes.length
                    text: (history.selectedRun && history.selectedRun.error) ||
                          "Recorded copies, moves, renames, cleanup, and rejected files will appear here."
                }
            }
        }
        Detail { Layout.fillWidth: true; visible: !!history.resultText; text: history.resultText }
        RowLayout {
            Layout.fillWidth: true
            ActionButton { text: "Close"; onClicked: history.close() }
            Item { Layout.fillWidth: true }
            ActionButton {
                objectName: "revertRunButton"
                visible: !history.searching
                text: "Revert operation"
                enabled: !history.busy && !!(history.selectedRun && history.selectedRun.remaining)
                onClicked: history.backend.prepareFileRevert(history.selectedRun.id, [])
            }
            ActionButton {
                objectName: "revertSelectedButton"
                visible: !history.searching
                text: history.checkedIds.length ? "Revert selected (" + history.checkedIds.length + ")" : "Revert selected"
                primary: true
                enabled: !history.busy && history.checkedIds.length > 0
                onClicked: history.backend.prepareFileRevert(history.selectedRun.id, history.checkedIds)
            }
        }
    }
}
