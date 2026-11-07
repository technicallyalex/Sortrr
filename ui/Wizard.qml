import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: wizard
    objectName: "reviewWizard"
    required property var backend
    readonly property var w: backend.wizard
    property int formUid: -1
    property bool showSearch: false
    readonly property string candidateLabels: JSON.stringify((w.candidates || []).map(candidate =>
        candidate.title + (candidate.year ? " (" + candidate.year + ")" : "") + " · " + candidate.provider))
    readonly property bool manualMode: !!w.manualMode
    readonly property var manualPreview: manualMode && w.open && !w.complete
        ? backend.manualEntryPreview(w.uid, titleField.text, yearField.text, kindBox.currentText, seasonBox.value, episodeBox.value)
        : ({})
    readonly property bool hasCandidate: w.chosen >= 0 && w.chosen < (w.candidates || []).length
    readonly property color ink: Theme.ink
    readonly property color muted: Theme.muted
    readonly property color accent: Theme.accentInk

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(1180, parent.width - 32)
    height: Math.min(760, parent.height - 32)
    modal: true
    visible: !!w.open
    closePolicy: Popup.NoAutoClose
    padding: 18
    background: Rectangle { color: Theme.canvas; radius: 18; border.color: Theme.line }

    function syncForm() {
        if (!w.open || w.complete) {
            formUid = -1
            return
        }
        if (formUid === w.uid)
            return
        formUid = w.uid
        showSearch = typeof w.searchOpen === "boolean" ? w.searchOpen : !(w.candidates || []).length
        titleField.text = w.query || ""
        yearField.text = w.year || ""
        kindBox.currentIndex = w.kind === "TV" ? 1 : 0
        seasonBox.value = w.season === undefined ? 1 : w.season
        episodeBox.value = w.episode || 1
    }
    ListModel { id: timelineModel }
    function syncTimeline() {
        const frames = w.timeline || []
        if (timelineModel.count !== frames.length) {
            timelineModel.clear()
            for (const frame of frames)
                timelineModel.append({frameUrl: frame.url, stamp: frame.time})
            return
        }
        for (let i = 0; i < frames.length; i++) {
            const current = timelineModel.get(i)
            if (current.frameUrl !== frames[i].url)
                timelineModel.setProperty(i, "frameUrl", frames[i].url)
            if (current.stamp !== frames[i].time)
                timelineModel.setProperty(i, "stamp", frames[i].time)
        }
    }
    onWChanged: {
        syncForm()
        syncTimeline()
    }

    function capture() {
        if (w.open && !w.complete)
            backend.updateWizard(titleField.text, yearField.text, kindBox.currentText, seasonBox.value, episodeBox.value)
    }
    function search() {
        capture()
        backend.searchWizard()
    }

    contentItem: ColumnLayout {
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: wizard.w.complete ? "Review complete" : "Review file"
                color: wizard.ink; font.pixelSize: 27; font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Label {
                visible: !!wizard.w.queue && !wizard.w.complete
                text: "File " + (wizard.w.index + 1) + " of " + wizard.w.count
                color: wizard.accent; font.weight: Font.DemiBold
            }
            ActionButton {
                visible: !wizard.w.complete
                text: "Copy path"; subtle: true; implicitHeight: 32
                onClicked: wizard.backend.copyWizardPath()
            }
        }

        ColumnLayout {
            visible: !wizard.w.complete
            Layout.fillWidth: true
            spacing: 3
            ScrollView {
                id: pathScroll
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(65, sourcePath.implicitHeight)
                clip: true
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                TextArea {
                    id: sourcePath
                    objectName: "wizardPath"
                    text: wizard.w.path || ""
                    textFormat: TextEdit.PlainText
                    wrapMode: TextEdit.WrapAnywhere
                    readOnly: true; selectByMouse: true
                    Accessible.name: "Full file path"
                    padding: 0; background: null; color: wizard.ink
                    font.pixelSize: 13
                }
            }
            Label {
                objectName: "wizardFileMetadata"
                Layout.fillWidth: true
                text: [wizard.w.deferred ? "Skipped this pass" : wizard.w.fileStatus]
                      .concat(wizard.w.metadata || []).filter(value => !!value).join("  ·  ")
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                maximumLineCount: 2; elide: Text.ElideRight
                color: wizard.muted; font.pixelSize: 12
                HoverHandler { id: metadataHover }
                ToolTip.visible: metadataHover.hovered && truncated
                ToolTip.text: text
            }
        }

        Rectangle {
            visible: !wizard.w.complete
            Layout.fillWidth: true; Layout.fillHeight: true
            color: Theme.surface; radius: 12; border.color: Theme.line
            RowLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 14
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 550
                    spacing: 6
                    Player {
                        backend: wizard.backend
                        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 200
                    }
                    Label {
                        Layout.fillWidth: true
                        text: wizard.w.previewMessage || (wizard.w.timelineLoading ? "Loading timeline thumbnails…" : "Timeline · Select a thumbnail to jump to that point")
                        textFormat: Text.PlainText; color: wizard.muted; font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: thumbnails.count > 0
                        spacing: 4
                        Repeater {
                            id: thumbnails
                            model: timelineModel
                            delegate: Button {
                                id: thumb
                                required property int index
                                required property string frameUrl
                                required property string stamp
                                objectName: "wizardThumb" + index
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1; Layout.preferredHeight: 72
                                enabled: !!frameUrl
                                hoverEnabled: true; padding: 3
                                Accessible.name: "Jump to " + stamp
                                onClicked: wizard.backend.previewWizardFrame(index)
                                background: Rectangle {
                                    radius: 6; color: thumb.hovered ? Theme.accentSoft : Theme.raised
                                    border.color: thumb.activeFocus || wizard.w.previewIndex === thumb.index ? Theme.focus : Theme.line
                                }
                                contentItem: ColumnLayout {
                                    spacing: 2
                                    Image {
                                        Layout.fillWidth: true; Layout.fillHeight: true
                                        source: thumb.frameUrl; asynchronous: true
                                        fillMode: Image.PreserveAspectCrop
                                        clip: true
                                    }
                                    Label {
                                        Layout.alignment: Qt.AlignHCenter
                                        text: thumb.stamp; color: wizard.muted; font.pixelSize: 11
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: Theme.line }

                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 440
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: wizard.manualMode ? "Manual entry" : "Database match"
                            Layout.fillWidth: true; color: wizard.ink
                            font.pixelSize: 17; font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        ActionButton {
                            text: wizard.showSearch ? "Hide search" : "Search instead"
                            subtle: true; implicitHeight: 32
                            visible: !wizard.manualMode && !wizard.w.unsupported; enabled: !wizard.w.busy
                            onClicked: {
                                wizard.showSearch = !wizard.showSearch
                                if (wizard.showSearch)
                                    titleField.forceActiveFocus()
                            }
                        }
                        ActionButton {
                            objectName: "manualModeButton"
                            text: wizard.manualMode ? "Back to database" : "Create manual entry"
                            implicitHeight: 32
                            visible: !wizard.w.unsupported && !wizard.w.rejected
                            enabled: !wizard.w.busy
                            onClicked: {
                                const entering = !wizard.manualMode
                                wizard.capture()
                                wizard.backend.setWizardManualMode(entering)
                                if (!entering && !wizard.hasCandidate)
                                    wizard.showSearch = true
                                titleField.forceActiveFocus()
                            }
                        }
                    }
                    ScrollView {
                        visible: !wizard.manualMode && wizard.hasCandidate
                        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 110
                        clip: true; contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ColumnLayout {
                            width: parent.width
                            spacing: 7
                            RowLayout {
                                Layout.fillWidth: true; spacing: 10
                                Rectangle {
                                    Layout.preferredWidth: 70; Layout.preferredHeight: 105
                                    Layout.alignment: Qt.AlignTop
                                    radius: 6; color: Theme.raised; clip: true
                                    Image {
                                        id: poster
                                        objectName: "entryPoster"
                                        anchors.fill: parent
                                        source: wizard.w.poster || ""
                                        fillMode: Image.PreserveAspectFit; asynchronous: true
                                    }
                                    Label {
                                        anchors.centerIn: parent
                                        visible: poster.status !== Image.Ready
                                        text: wizard.w.detailLoading ? "Loading…" : "No poster"
                                        color: wizard.muted; font.pixelSize: 10
                                    }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                                    spacing: 4
                                    Label {
                                        text: (wizard.w.details || {}).title || ""
                                        textFormat: Text.PlainText; color: wizard.ink
                                        font.pixelSize: 17; font.weight: Font.DemiBold
                                        Layout.fillWidth: true; wrapMode: Text.Wrap
                                    }
                                    Label {
                                        visible: !!text; text: wizard.w.runtime || ""
                                        objectName: "wizardRuntime"; textFormat: Text.PlainText
                                        Layout.fillWidth: true; wrapMode: Text.Wrap
                                        color: wizard.accent; font.pixelSize: 12
                                    }
                                    TextArea {
                                        objectName: "entryDetailsText"
                                        Layout.fillWidth: true
                                        text: (wizard.w.details || {}).info ? wizard.w.details.info.split("\n").slice(1).join("\n") : ""
                                        textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true
                                        wrapMode: TextEdit.Wrap; color: wizard.muted
                                        font.pixelSize: 12; padding: 0; background: null
                                    }
                                    ActionButton {
                                        text: "Open database entry"; subtle: true; implicitHeight: 28
                                        visible: !!(wizard.w.details || {}).url
                                        onClicked: wizard.backend.openUrl(wizard.w.details.url)
                                    }
                                }
                            }
                        }
                    }
                    Label {
                        visible: !wizard.manualMode && !wizard.hasCandidate && !wizard.w.unsupported
                        text: "No suggested match. Search by title or create a manual entry."
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        color: wizard.muted; font.pixelSize: 13
                    }
                    SelectBox {
                        objectName: "wizardResults"
                        visible: !wizard.manualMode && count > 1; Layout.fillWidth: true
                        Accessible.name: "Database search results"
                        model: JSON.parse(wizard.candidateLabels)
                        currentIndex: wizard.w.chosen === undefined ? -1 : wizard.w.chosen
                        enabled: !wizard.w.busy
                        onActivated: function(index) {
                            wizard.capture()
                            wizard.backend.chooseCandidate(index)
                        }
                    }
                    ColumnLayout {
                        visible: (wizard.manualMode || wizard.showSearch) && !wizard.w.unsupported
                        Layout.fillWidth: true; spacing: 6
                        Label {
                            visible: wizard.manualMode
                            text: "Use the movie title or series title. Year is optional."
                            Layout.fillWidth: true; wrapMode: Text.Wrap
                            color: wizard.muted; font.pixelSize: 12
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Field {
                                id: titleField
                                objectName: "wizardTitle"
                                Layout.fillWidth: true
                                placeholderText: "Movie or show title"; Accessible.name: wizard.manualMode ? "Entry title" : "Search title"
                                enabled: !wizard.w.busy; onAccepted: if (!wizard.manualMode) wizard.search()
                            }
                            ActionButton {
                                objectName: "searchMatchButton"
                                visible: !wizard.manualMode
                                text: wizard.w.busy ? "Searching…" : "Search"
                                enabled: !wizard.w.busy && !!titleField.text.trim()
                                onClicked: wizard.search()
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            SelectBox {
                                id: kindBox
                                objectName: "wizardKind"
                                model: ["Movie", "TV"]; Accessible.name: "Media type"
                                Layout.preferredWidth: 118; enabled: !wizard.w.busy
                                onActivated: wizard.capture()
                            }
                            Field {
                                id: yearField
                                objectName: "wizardYear"
                                placeholderText: "Year"; Accessible.name: "Release year (optional)"
                                Layout.preferredWidth: 70; enabled: !wizard.w.busy
                                onAccepted: wizard.search()
                            }
                            Item { Layout.fillWidth: true }
                        }
                        RowLayout {
                            visible: kindBox.currentIndex === 1
                            Label { text: "Season"; color: wizard.muted }
                            SpinBox {
                                id: seasonBox
                                objectName: "wizardSeason"
                                from: 0; to: 99; value: 1; editable: true; enabled: !wizard.w.busy
                                Accessible.name: "Season number"; onValueModified: wizard.capture()
                            }
                            Label { text: "Episode"; color: wizard.muted }
                            SpinBox {
                                id: episodeBox
                                objectName: "wizardEpisode"
                                from: 1; to: 999; value: 1; editable: true; enabled: !wizard.w.busy
                                Accessible.name: "Episode number"; onValueModified: wizard.capture()
                            }
                        }
                    }
                    ColumnLayout {
                        visible: wizard.manualMode
                        Layout.fillWidth: true
                        spacing: 4
                        Label {
                            text: "Planned path"; color: wizard.ink
                            font.pixelSize: 13; font.weight: Font.DemiBold
                        }
                        Label {
                            objectName: "manualPathPreview"
                            text: wizard.manualPreview.path || wizard.manualPreview.error || ""
                            Layout.fillWidth: true
                            textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere
                            maximumLineCount: 4; elide: Text.ElideMiddle
                            color: wizard.muted; font.pixelSize: 12
                            HoverHandler { id: manualPathHover }
                            ToolTip.visible: manualPathHover.hovered && truncated
                            ToolTip.text: text
                        }
                    }
                    Label {
                        visible: !!text
                        text: wizard.w.message || ""; textFormat: Text.PlainText
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                        color: wizard.muted; font.pixelSize: 12
                    }
                    Item { visible: wizard.manualMode || !wizard.hasCandidate; Layout.fillHeight: true }
                }
            }
        }

        Item {
            visible: !!wizard.w.complete
            Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout {
                anchors.centerIn: parent
                Label { text: wizard.w.resolved + " of " + wizard.w.count + " files matched"; color: wizard.ink; font.pixelSize: 22; font.weight: Font.DemiBold }
                Label {
                    visible: (wizard.w.rejectedCount || 0) > 0
                    text: wizard.w.rejectedCount + " marked as rejected. Handle them in Organize."
                    color: wizard.muted; font.pixelSize: 13
                }
                Label {
                    visible: wizard.w.count > wizard.w.resolved + (wizard.w.rejectedCount || 0)
                    text: "Other unmatched files remain in Needs review."
                    color: wizard.muted; font.pixelSize: 13
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            ActionButton {
                objectName: "wizardBackButton"
                text: "Back"; visible: !!wizard.w.queue
                enabled: !wizard.w.busy && wizard.w.index > 0
                onClicked: { wizard.capture(); wizard.backend.wizardMove(-1) }
            }
            ActionButton {
                objectName: "wizardNextButton"
                text: "Next"; visible: !!wizard.w.queue && !wizard.w.complete
                enabled: !wizard.w.busy && wizard.w.index + 1 < wizard.w.count
                onClicked: { wizard.capture(); wizard.backend.wizardMove(1) }
                ToolTip.visible: hovered; ToolTip.text: "Browse without changing the match."
            }
            ActionButton {
                text: "Database settings"; subtle: true
                visible: !wizard.w.complete; enabled: !wizard.w.busy
                onClicked: wizard.backend.requestDatabase()
            }
            Item { Layout.fillWidth: true }
            ActionButton {
                objectName: "saveReviewButton"
                text: "Save and close"; visible: !wizard.w.complete
                enabled: !wizard.w.busy
                onClicked: { wizard.capture(); wizard.backend.saveReviewAndClose(wizard.showSearch) }
            }
            ActionButton {
                text: "Close"; subtle: true; visible: !wizard.w.complete
                onClicked: wizard.backend.closeWizard()
            }
            ActionButton {
                objectName: "wizardSkipButton"
                text: "Skip"; visible: !!wizard.w.queue && !wizard.w.complete
                enabled: !wizard.w.busy
                onClicked: { wizard.capture(); wizard.backend.skipWizard() }
                ToolTip.visible: hovered; ToolTip.text: "Leave unmatched and advance for this review."
            }
            ActionButton {
                objectName: "wizardRejectButton"
                text: wizard.w.rejected ? "Unmark reject" : "Reject"
                visible: !wizard.w.complete
                enabled: !wizard.w.busy
                onClicked: { wizard.capture(); wizard.backend.toggleWizardReject() }
                ToolTip.visible: hovered
                ToolTip.text: wizard.w.rejected ? "Return this file to review." : "Mark for handling in Organize."
            }
            ActionButton {
                objectName: "acceptWizardButton"
                text: wizard.w.complete ? "Back to files" : wizard.manualMode ? "Save manual entry" : "Assign match"
                primary: true
                enabled: !wizard.w.busy && (wizard.w.complete || (!wizard.w.unsupported && !wizard.w.rejected
                    && (wizard.manualMode ? !!wizard.manualPreview.path : wizard.hasCandidate)))
                onClicked: {
                    if (wizard.w.complete)
                        wizard.backend.closeWizard()
                    else {
                        wizard.capture()
                        wizard.backend.acceptWizard()
                    }
                }
            }
        }
    }
}
