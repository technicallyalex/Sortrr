import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: review
    required property var backend
    required property var host
    property var s: backend.state
    spacing: 10
    onVisibleChanged: if (!visible) hover.dismiss()
    component Card: Rectangle { color: Theme.surface; radius: 12; border.color: review.host.line }
    component SmallLabel: Label { color: review.host.muted; font.pixelSize: 12; font.weight: Font.DemiBold }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        ActionButton {
            text: "All files (" + s.total + ")"; subtle: true; selected: !s.reviewOnly && !s.readyOnly && !s.rejectedOnly
            onClicked: review.backend.setReviewView("all")
        }
        ActionButton {
            text: "Needs review (" + s.unresolved + ")"; subtle: true; selected: s.reviewOnly
            onClicked: review.backend.setReviewView("review")
        }
        ActionButton {
            text: "Ready (" + s.ready + ")"; subtle: true; selected: s.readyOnly
            onClicked: review.backend.setReviewView("ready")
        }
        ActionButton {
            text: "Rejected (" + s.rejected + ")"; subtle: true; selected: s.rejectedOnly
            visible: s.rejected > 0 || s.rejectedOnly
            onClicked: review.backend.setReviewView("rejected")
        }
        Item { Layout.fillWidth: true }
        ActionButton {
            objectName: "reviewQueueButton"
            text: "Review unmatched (" + s.visibleUnresolved + ")"
            visible: s.visibleUnresolved > 0
            primary: true
            enabled: !s.busy
            onClicked: review.backend.openWizard(-1)
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Field {
            id: searchField
            Layout.fillWidth: true
            placeholderText: "Search file names or titles"
            Accessible.name: placeholderText
            onTextEdited: review.backend.setQuery(text)
        }
        ActionButton {
            id: filterToggle
            checkable: true
            text: checked ? "Hide filters" : (review.hasFilters ? "Filters active" : "Filters and sort")
        }
        ActionButton {
            text: "Clear filters"; visible: review.hasFilters
            onClicked: {
                searchField.clear()
                review.backend.resetFilters()
            }
        }
        ActionButton {
            text: "Check runtimes"
            enabled: !s.busy && (s.selected ? s.selectedMatched > 0 : s.visibleMatched > 0)
            onClicked: review.backend.checkRuntimes()
            ToolTip.visible: hovered
            ToolTip.text: s.selected ? "Compare the runtime of selected identified files." : "Compare the runtime of all identified files shown."
        }
    }
    readonly property bool hasFilters: !!s.query || s.filter !== "All media" || s.runtimeFilter !== "Any length"
    RowLayout {
        Layout.fillWidth: true
        visible: filterToggle.checked
        SmallLabel { text: "Media type" }
        SelectBox {
            Accessible.name: "Media type"
            model: ["All media", "Movies", "TV shows"]
            currentIndex: review.host.indexOfOption(model, s.filter)
            onActivated: review.backend.setMediaFilter(currentText)
            Layout.preferredWidth: 115
        }
        SmallLabel { text: "Runtime" }
        SelectBox {
            Accessible.name: "Runtime filter"
            model: ["Any length", "Matches", "Differs", "Unknown", "Unchecked"]
            currentIndex: review.host.indexOfOption(model, s.runtimeFilter)
            onActivated: review.backend.setRuntimeFilter(currentText)
            Layout.preferredWidth: 115
        }
        SmallLabel { text: "Sort by" }
        SelectBox {
            Accessible.name: "Sort by"
            model: ["Source name", "Title", "Type", "Year", "Season", "Episode", "Status"]
            currentIndex: review.host.indexOfOption(model, s.sortBy)
            onActivated: review.backend.setSort(currentText, s.descending)
            Layout.preferredWidth: 132
        }
        ActionButton { text: s.descending ? "Descending" : "Ascending"; onClicked: review.backend.setSort(s.sortBy, !s.descending) }
        Item { Layout.fillWidth: true }
    }
    RowLayout {
        Layout.fillWidth: true
        visible: s.selected > 0
        SmallLabel { text: s.selected + " selected" }
        Item { Layout.fillWidth: true }
        ActionButton { text: "Re-identify"; enabled: !s.busy && s.selectedReidentifiable > 0; onClicked: review.backend.reidentifySelected() }
        ActionButton { text: "Rename in place"; enabled: !s.busy && s.selectedMatched > 0; onClicked: review.backend.prepare("rename") }
        ActionButton {
            text: "Skip selected"; enabled: !s.busy && s.selectedSkippable > 0
            onClicked: review.backend.skipSelected()
            ToolTip.visible: hovered
            ToolTip.text: "Remember these skips. Re-identify a file to include it again."
        }
        ActionButton { text: "Deselect"; subtle: true; onClicked: review.backend.selectVisible(false) }
    }
    Card {
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 145; clip: true
        ColumnLayout {
            anchors.fill: parent; spacing: 0
            RowLayout {
                Layout.fillWidth: true; Layout.leftMargin: 10; Layout.rightMargin: 13
                ChoiceCheck { checked: s.visible > 0 && s.selected === s.visible; enabled: s.visible > 0; onToggled: review.backend.selectVisible(checked); Accessible.name: "Select all visible files" }
                SmallLabel { text: "FILES"; Layout.fillWidth: true }
                SmallLabel { text: s.selected ? s.selected + " selected" : s.visible + " shown" }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: review.host.line }
            ListView {
                id: library
                objectName: "libraryList"
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; reuseItems: true
                model: review.backend.mediaModel
                ScrollBar.vertical: ScrollBar {}
                delegate: Item {
                    id: itemRow
                    required property int uid
                    required property string mediaTitle
                    required property string fileName
                    required property string filePath
                    required property string mediaKind
                    required property string releaseYear
                    required property string episodeText
                    required property string statusText
                    required property string statusTone
                    required property string thumbnail
                    required property bool isSelected
                    required property bool isRemembered
                    required property string runtimeStatus
                    required property string runtimeLabel
                    property bool pooled: false
                    width: library.width - 12; height: 74
                    Component.onCompleted: review.backend.requestThumbnail(uid)
                    onUidChanged: if (!pooled) review.backend.requestThumbnail(uid)
                    ListView.onPooled: { pooled = true; if (hover.uid === uid) hover.dismiss() }
                    ListView.onReused: { pooled = false; review.backend.requestThumbnail(uid) }
                    Timer { interval: 1000; repeat: true; running: !itemRow.pooled && !itemRow.thumbnail && !s.mutating; onTriggered: review.backend.requestThumbnail(itemRow.uid) }
                    Rectangle { anchors.fill: parent; color: itemRow.isSelected ? Theme.accentSoft : (rowHover.hovered ? Theme.field : Theme.surface) }
                    HoverHandler { id: rowHover }
                    TapHandler { onDoubleTapped: review.backend.openWizard(itemRow.uid) }
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6; spacing: 10
                        ChoiceCheck { checked: itemRow.isSelected; onToggled: review.backend.select(itemRow.uid, checked); Accessible.name: "Select " + itemRow.fileName }
                        Rectangle {
                            id: thumb
                            Layout.preferredWidth: 89; Layout.preferredHeight: 50; radius: 6; color: Theme.raised; clip: true
                            Label { anchors.centerIn: parent; text: itemRow.mediaKind === "TV" ? "TV" : "FILM"; font.pixelSize: 10; color: review.host.muted; visible: image.status !== Image.Ready }
                            Image { id: image; anchors.fill: parent; source: itemRow.thumbnail; asynchronous: true; fillMode: Image.PreserveAspectCrop }
                            MouseArea {
                                anchors.fill: parent; acceptedButtons: Qt.NoButton; hoverEnabled: true
                                onEntered: function() { scrub(mouseX) }
                                onPositionChanged: function(event) { scrub(event.x) }
                                onExited: if (hover.uid === itemRow.uid) hover.dismiss()
                                function scrub(x) {
                                    if (!itemRow.thumbnail || s.mutating) return
                                    let step = Math.round(20 * Math.max(0, Math.min(1, x / width)))
                                    if (hover.visible && hover.uid === itemRow.uid && hover.step === step) return
                                    let pt = thumb.mapToItem(review.host.contentItem, 0, 0)
                                    hover.x = Math.min(review.host.width - hover.width - 12, pt.x)
                                    hover.y = pt.y >= hover.height + 10 ? pt.y - hover.height - 6 : pt.y + thumb.height + 6
                                    if (hover.uid !== itemRow.uid) { hover.frame = itemRow.thumbnail; hover.caption = "Move across the thumbnail to scrub" }
                                    hover.uid = itemRow.uid; hover.step = step; hover.token++; hover.visible = true; hoverTimer.restart()
                                }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 3
                            Label { text: itemRow.mediaTitle; textFormat: Text.PlainText; color: review.host.ink; font.pixelSize: 15; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                            Label {
                                text: itemRow.fileName; textFormat: Text.PlainText
                                color: review.host.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideMiddle
                                HoverHandler { id: nameHover }
                                ToolTip.visible: nameHover.hovered && truncated
                                ToolTip.text: itemRow.fileName
                            }
                        }
                        Label {
                            Layout.preferredWidth: 87; text: [itemRow.episodeText || itemRow.mediaKind, itemRow.releaseYear].filter(x => x).join(" / ")
                            color: review.host.muted; font.pixelSize: 11; elide: Text.ElideRight
                        }
                        ColumnLayout {
                            Layout.preferredWidth: 130; Layout.maximumWidth: 160; spacing: 3
                            Rectangle {
                                Layout.fillWidth: true; height: 23; radius: 6
                                color: itemRow.statusTone === "good" ? Theme.successSoft : itemRow.statusTone === "done" ? Theme.accentSoft : itemRow.statusTone === "review" ? Theme.warningSoft : Theme.raised
                                Label { anchors.fill: parent; anchors.leftMargin: 7; anchors.rightMargin: 7; text: itemRow.statusText; textFormat: Text.PlainText; verticalAlignment: Text.AlignVCenter; font.pixelSize: 11; color: review.host.ink; elide: Text.ElideRight }
                                HoverHandler { id: statusHover }
                                ToolTip.visible: statusHover.hovered; ToolTip.text: itemRow.statusText + (itemRow.isRemembered ? " (saved match)" : "")
                            }
                            Label {
                                Layout.fillWidth: true; text: itemRow.runtimeStatus === "Unchecked" ? (itemRow.isRemembered ? "Saved match" : "Length unchecked") : "Length: " + itemRow.runtimeStatus.toLowerCase()
                                color: itemRow.runtimeStatus === "Differs" ? Theme.warning : itemRow.runtimeStatus === "Matches" ? Theme.success : review.host.muted
                                font.pixelSize: 11
                                HoverHandler { id: runtimeHover }
                                ToolTip.visible: runtimeHover.hovered; ToolTip.text: itemRow.runtimeLabel
                            }
                        }
                        ActionButton {
                            text: itemRow.statusText === "Rejected" ? "View reject"
                                  : itemRow.statusTone === "good" || itemRow.statusTone === "done" ? "View match" : "Review"
                            Layout.preferredWidth: 102
                            enabled: !s.busy && itemRow.statusText !== "Sent to Recycle Bin" && itemRow.statusText !== "Moved to reject folder"
                            Accessible.name: text + " for " + itemRow.fileName
                            onClicked: review.backend.openWizard(itemRow.uid)
                        }
                        ActionButton {
                            text: "⋯"; padding: 3; Layout.preferredWidth: 36; enabled: !s.busy
                            Accessible.name: "Actions for " + itemRow.fileName
                            onClicked: rowMenu.open()
                            Menu {
                                id: rowMenu; y: parent.height
                                MenuItem { text: "Open file folder"; enabled: itemRow.statusText !== "Sent to Recycle Bin"; onTriggered: review.backend.openLocation(itemRow.uid) }
                            }
                        }
                    }
                    Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: Theme.line }
                }
                Column {
                    anchors.centerIn: parent; spacing: 7; visible: library.count === 0
                    Label { anchors.horizontalCenter: parent.horizontalCenter; text: s.busy ? "Looking for media..." : s.total ? "No files in this view" : "No media files found"; color: review.host.ink; font.pixelSize: 18; font.weight: Font.DemiBold }
                    Label { anchors.horizontalCenter: parent.horizontalCenter; text: s.busy ? "Files appear as the scan runs." : s.total ? "Try another tab or clear the filters." : "Check the source folder and scan again."; color: review.host.muted; font.pixelSize: 12 }
                }
            }
        }
    }
    Rectangle {
        id: hover
        parent: review.host.contentItem
        z: 20; visible: false; width: 300; height: 192; color: Theme.media; radius: 9
        property int uid: -1
        property int token: 0
        property int step: 0
        property string frame: ""
        property string caption: ""
        function dismiss() { visible = false; uid = -1; token++; hoverTimer.stop() }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 7; spacing: 3
            Image { source: hover.frame; asynchronous: true; Layout.fillHeight: true; Layout.fillWidth: true; fillMode: Image.PreserveAspectFit }
            Label { text: hover.caption; color: Theme.mediaForeground; font.pixelSize: 11; Layout.alignment: Qt.AlignHCenter }
        }
    }
    Timer { id: hoverTimer; interval: 150; onTriggered: if (hover.visible) review.backend.requestHover(hover.uid, hover.step / 20, hover.token) }

    Connections {
        target: review.backend
        function onProgressResumed() { searchField.text = review.backend.state.query }
        function onHoverReady(uid, token, url, caption) {
            if (hover.visible && uid === hover.uid && token === hover.token) {
                hover.frame = url
                hover.caption = caption
            }
        }
    }
}
