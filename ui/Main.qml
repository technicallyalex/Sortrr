import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import "."

ApplicationWindow {
    id: window
    visible: true
    width: 1240; height: 820
    minimumWidth: 1000; minimumHeight: 670
    title: "Sortrr"
    color: Theme.canvas
    font.family: "Segoe UI"
    palette.window: Theme.surface
    palette.windowText: Theme.ink
    palette.base: Theme.surface
    palette.alternateBase: Theme.canvas
    palette.text: Theme.ink
    palette.button: Theme.surface
    palette.buttonText: Theme.ink
    palette.dark: Theme.muted
    palette.mid: Theme.quiet
    palette.light: Theme.line
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.accentForeground
    palette.toolTipBase: Theme.raised
    palette.toolTipText: Theme.ink

    property var s: controller.state
    property int step: 0
    property string scannedSource: ""
    readonly property bool hasScanned: !!scannedSource && scannedSource === s.source
    property string scope: "all"
    property string rejectMode: "leave"
    readonly property int rejectCount: rejectMode === "leave" ? 0 : s.rejected
    readonly property int planCount: scopeCount + rejectCount
    readonly property int scopeCount: scope === "none" ? 0 : scope === "selected" ? s.selectedReady : scope === "visible" ? s.visibleReady : s.ready
    property var operation: ({})
    property var cleanupChecks: ({})
    property color ink: Theme.ink
    property color muted: Theme.muted
    property color accent: Theme.accent
    property color line: Theme.line

    function indexOfOption(list, value) {
        for (let i = 0; i < list.length; i++) if ((list[i].value || list[i]) === value) return i
        return -1
    }
    onSChanged: if (!s.rejected && scope === "none") scope = "all"
    function openOrganize() {
        notice.close()
        scope = s.selectedReady > 0 ? "selected" : (s.visibleReady > 0 && s.visibleReady < s.ready ? "visible" : "all")
        step = 2
    }
    function captureOrganizePaths() {
        if (!s.inPlace && destinationField.text.trim() !== s.destination)
            controller.setPath("destination", destinationField.text.trim())
        if (window.rejectMode === "folder" && rejectFolderField.text.trim() !== s.rejectFolder)
            controller.setPath("reject", rejectFolderField.text.trim())
    }
    function beginScan() {
        controller.setPath("source", sourceField.text.trim())
        controller.scan()
    }
    function showNotice(message) {
        noticeText.text = message
        notice.open()
        noticeTimer.restart()
    }
    onClosing: function(event) {
        if (s.busy) {
            event.accepted = false
            showNotice("Wait for the current operation to finish.")
            return
        }
        controller.shutdown()
    }

    component Card: Rectangle { color: Theme.surface; radius: 15; border.color: window.line }
    component SectionTitle: Label { color: window.ink; font.pixelSize: 18; font.weight: Font.DemiBold }
    component SmallLabel: Label { color: window.muted; font.pixelSize: 12; font.weight: Font.DemiBold }
    component Description: Label { color: window.muted; font.pixelSize: 13; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
    component ScopeOption: ChoiceRadio {
        id: option
        required property string detail
        Layout.fillWidth: true
        implicitHeight: Math.max(34, implicitContentHeight + topPadding + bottomPadding)
        topPadding: 2; bottomPadding: 2
        Accessible.description: detail
        contentItem: ColumnLayout {
            spacing: 2
            Label {
                Layout.fillWidth: true
                text: option.text; textFormat: Text.PlainText
                color: option.enabled ? window.ink : Theme.disabled
                font.pixelSize: 13; font.weight: Font.DemiBold
                wrapMode: Text.Wrap
            }
            Description { text: option.detail; font.pixelSize: 12 }
        }
        leftPadding: padding + indicator.width + spacing
        alignIndicatorTop: true
    }
    component Sheet: Dialog {
        id: sheet
        background: Rectangle { color: Theme.surface; radius: 14; border.color: window.line }
        header: Label {
            text: sheet.title; textFormat: Text.PlainText; color: window.ink
            font.pixelSize: 20; font.weight: Font.DemiBold; padding: 20; bottomPadding: 4
        }
    }
    component StepButton: Button {
        id: tab
        property int page: 0
        readonly property bool current: window.step === page
        implicitHeight: 44
        hoverEnabled: true
        Accessible.name: (page + 1) + ". " + text
        background: Rectangle {
            radius: 10
            color: tab.current ? Theme.accentSoft : tab.hovered ? Theme.raised : "transparent"
            border.width: tab.visualFocus ? 2 : 0
            border.color: Theme.focus
        }
        contentItem: RowLayout {
            spacing: 8
            Item { Layout.fillWidth: true }
            Rectangle {
                width: 24; height: 24; radius: 7
                color: tab.current ? Theme.accent : Theme.raised
                Label {
                    anchors.centerIn: parent
                    text: "0" + (tab.page + 1)
                    color: tab.current ? Theme.accentForeground : Theme.quiet
                    font.pixelSize: 10; font.weight: Font.DemiBold
                }
            }
            Label {
                text: tab.text
                color: !tab.enabled ? Theme.disabled : tab.current ? Theme.accentInk : Theme.ink
                font.pixelSize: 13; font.weight: tab.current ? Font.DemiBold : Font.Medium
            }
            Item { Layout.fillWidth: true }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 76; color: Theme.surface
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24; spacing: 12
                RowLayout {
                    spacing: 10
                    Image { source: "assets/sortrr.png"; Layout.preferredWidth: 36; Layout.preferredHeight: 36; fillMode: Image.PreserveAspectFit }
                    Label { text: "Sortrr"; color: window.ink; font.pixelSize: 25; font.weight: Font.DemiBold }
                }
                Item { Layout.fillWidth: true }
                StepButton { text: "Source"; page: 0; Layout.preferredWidth: 122; enabled: !s.busy || current; onClicked: window.step = 0 }
                StepButton { text: "Review files"; page: 1; Layout.preferredWidth: 150; enabled: window.hasScanned && (!s.busy || current); onClicked: window.step = 1 }
                StepButton { text: "Organize"; page: 2; Layout.preferredWidth: 136; enabled: !s.busy || current; onClicked: if (!current) window.openOrganize() }
                Item { Layout.fillWidth: true }
                ActionButton {
                    objectName: "settingsButton"
                    text: "Settings"; enabled: !s.busy
                    onClicked: {
                        settings.x = window.x + Math.round((window.width - settings.width) / 2)
                        settings.y = window.y + Math.round((window.height - settings.height) / 2)
                        settings.show()
                        settings.requestActivate()
                    }
                }
            }
            Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: window.line }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: 24; spacing: 14
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Label {
                        text: ["Choose your source", "Review identified files", "Plan your library"][window.step]
                        color: window.ink; font.pixelSize: 32; font.weight: Font.DemiBold
                    }
                    Description {
                        visible: window.step !== 0
                        text: [
                            "",
                            "Check matches, resolve uncertain files, and choose what to organize.",
                            "Choose where the files go and preview their final paths before starting."
                        ][window.step]
                    }
                }
                ActionButton {
                    objectName: "resumeReviewButton"
                    text: "Resume saved progress"
                    visible: window.step === 1 && s.savedSource === s.source && !!s.savedSource
                    enabled: !s.busy
                    onClicked: controller.resumeProgress()
                }
                ActionButton { text: "Scan again"; visible: window.step === 1; enabled: !s.busy && !!s.source; onClicked: controller.scan() }
                ActionButton {
                    objectName: "changeHistoryButton"
                    text: "Change history"; visible: window.step === 2; enabled: !s.busy
                    onClicked: changeHistory.open()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                visible: window.step === 2 && !!s.lastSort && !s.busy
                implicitHeight: resultText.implicitHeight + 24
                radius: 9; color: Theme.successSoft
                Description {
                    id: resultText
                    anchors.fill: parent; anchors.margins: 12
                    text: s.lastSort; color: window.ink
                }
            }
            StackLayout {
                currentIndex: window.step
                Layout.fillWidth: true; Layout.fillHeight: true

                ColumnLayout {
                    spacing: 14
                    Card {
                        Layout.fillWidth: true
                        implicitHeight: sourceOptions.implicitHeight + 36
                        ColumnLayout {
                            id: sourceOptions
                            anchors.fill: parent; anchors.margins: 18; spacing: 10
                            SectionTitle { text: "Media folder" }
                            Description { text: "Sortrr scans this folder and its subfolders. Your files stay in place during the scan." }
                            RowLayout {
                                Layout.fillWidth: true
                                Field {
                                    id: sourceField
                                    objectName: "sourceField"
                                    Layout.fillWidth: true
                                    text: s.source
                                    placeholderText: "Path to your movies or TV episodes"
                                    Accessible.name: "Source folder"
                                    onEditingFinished: if (text.trim() !== s.source) controller.setPath("source", text.trim())
                                    onAccepted: window.beginScan()
                                }
                                ActionButton { text: "Browse"; onClicked: controller.pickFolder("source") }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Item { Layout.fillWidth: true }
                                ActionButton {
                                    objectName: "scanButton"
                                    text: "Scan files"; primary: true
                                    enabled: !s.busy && !!sourceField.text.trim(); onClicked: window.beginScan()
                                }
                            }
                        }
                    }
                    Card {
                        Layout.fillWidth: true
                        implicitHeight: connectionContent.implicitHeight + 32
                        RowLayout {
                            id: connectionContent
                            anchors.fill: parent; anchors.margins: 16; spacing: 16
                            ColumnLayout {
                                Layout.fillWidth: true
                                SectionTitle { text: s.connected ? "TMDb token saved" : "Connect TMDb for movies" }
                                Description {
                                    text: s.connected ? "Sortrr uses TMDb for movies and TVmaze for episode identification."
                                                      : "Movie identification requires a TMDb token. TV episode scans can use TVmaze right away."
                                }
                            }
                            ActionButton { text: s.connected ? "Manage connection" : "Connect TMDb"; onClicked: controller.requestDatabase() }
                        }
                    }
                    Card {
                        visible: !!s.savedSource
                        Layout.fillWidth: true
                        implicitHeight: savedContent.implicitHeight + 32
                        RowLayout {
                            id: savedContent
                            anchors.fill: parent; anchors.margins: 16; spacing: 16
                            ColumnLayout {
                                Layout.fillWidth: true
                                SectionTitle { text: s.savedStage === "organize" ? "Saved organize plan" : "Saved review progress" }
                                Description { text: s.savedSource; maximumLineCount: 2; elide: Text.ElideMiddle }
                            }
                            ActionButton {
                                objectName: "resumeSourceButton"
                                text: "Resume"; enabled: !s.busy
                                onClicked: controller.resumeProgress()
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }

                ReviewPane { backend: controller; host: window }

                ScrollView {
                    id: organizeScroll
                    clip: true
                    contentWidth: availableWidth
                    rightPadding: 12
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical: ScrollBar {
                        anchors.top: organizeScroll.top
                        anchors.bottom: organizeScroll.bottom
                        anchors.right: organizeScroll.right
                        active: organizeScroll.contentHeight > organizeScroll.availableHeight
                    }
                    RowLayout {
                        width: organizeScroll.availableWidth
                        spacing: 14
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                            Layout.preferredWidth: 570; spacing: 12
                            Card {
                                Layout.fillWidth: true
                                implicitHeight: outputOptions.implicitHeight + 32
                                ColumnLayout {
                                    id: outputOptions
                                    anchors.fill: parent; anchors.margins: 16; spacing: 8
                                    SectionTitle { text: "1. Destination" }
                                    RowLayout {
                                        ButtonGroup { id: modeGroup }
                                        ChoiceRadio {
                                            text: "Copy to a library folder"; checked: !s.inPlace; ButtonGroup.group: modeGroup
                                            enabled: !s.busy; onClicked: controller.setAutomatic(false, s.autoRename, s.autoCleanup)
                                        }
                                        ChoiceRadio {
                                            objectName: "moveOption"
                                            text: "Move within the source folder"; checked: s.inPlace; ButtonGroup.group: modeGroup
                                            enabled: !s.busy; onClicked: controller.setAutomatic(true, s.autoRename, s.autoCleanup)
                                        }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        visible: !s.inPlace
                                        Field {
                                            id: destinationField
                                            objectName: "destinationField"
                                            text: s.destination; Layout.fillWidth: true; enabled: !s.busy
                                            placeholderText: "Path to the media server library"
                                            Accessible.name: "Library destination"
                                            onEditingFinished: if (text.trim() !== s.destination) controller.setPath("destination", text.trim())
                                        }
                                        ActionButton { text: "Browse"; enabled: !s.busy; onClicked: controller.pickFolder("destination") }
                                    }
                                    Description {
                                        text: s.inPlace ? "Files move into Movies or TV Shows under " + (s.source || "the source folder") + "."
                                                        : "Sortrr creates Movies and TV Shows subfolders here and keeps the original media files."
                                    }
                                }
                            }
                            Card {
                                Layout.fillWidth: true
                                implicitHeight: layoutOptions.implicitHeight + 32
                                ColumnLayout {
                                    id: layoutOptions
                                    anchors.fill: parent; anchors.margins: 16; spacing: 8
                                    SectionTitle { text: "2. Folder and file names" }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        SmallLabel { text: "Media server" }
                                        SelectBox {
                                            model: s.preset === "Custom" ? controller.presets.concat(["Custom"]) : controller.presets
                                            currentIndex: window.indexOfOption(model, s.preset)
                                            onActivated: controller.setPreset(currentText)
                                            Accessible.name: "Media server preset"
                                            enabled: !s.busy; Layout.preferredWidth: 210
                                        }
                                        ActionButton { objectName: "customizeButton"; text: "Customize"; Accessible.name: "Customize folder layout"; enabled: !s.busy; onClicked: layouts.open() }
                                    }
                                    ChoiceCheck {
                                        text: "Rename media to match"; checked: s.autoRename; enabled: !s.busy
                                        onToggled: controller.setAutomatic(s.inPlace, checked, s.autoCleanup)
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: controller.layoutExamples(s.movieLayout, s.showLayout, s.idStyle, s.autoRename).join("\n")
                                        textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere
                                        font.pixelSize: 12; color: window.muted
                                    }
                                }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                            Layout.preferredWidth: 390; spacing: 12
                            Card {
                                Layout.fillWidth: true
                                implicitHeight: scopeOptions.implicitHeight + 32
                                ColumnLayout {
                                    id: scopeOptions
                                    anchors.fill: parent; anchors.margins: 16; spacing: 8
                                    SectionTitle { text: "3. Files to organize" }
                                    ButtonGroup { id: scopeGroup }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 6
                                        ScopeOption {
                                            objectName: "allReadyOption"
                                            text: "All ready files (" + s.ready + ")"
                                            detail: "Includes ready matches hidden by Review filters."
                                            ButtonGroup.group: scopeGroup
                                            checked: window.scope === "all"; enabled: !s.busy
                                            onClicked: window.scope = "all"
                                        }
                                        ScopeOption {
                                            objectName: "visibleReadyOption"
                                            text: "Ready files in current view (" + s.visibleReady + ")"
                                            detail: "Includes ready matches shown by your Review filters."
                                            ButtonGroup.group: scopeGroup
                                            checked: window.scope === "visible"; enabled: !s.busy && s.visibleReady > 0
                                            onClicked: window.scope = "visible"
                                        }
                                        ScopeOption {
                                            objectName: "selectedReadyOption"
                                            text: "Checked ready files (" + s.selectedReady + ")"
                                            detail: "Includes only checked files shown in Review."
                                            ButtonGroup.group: scopeGroup
                                            checked: window.scope === "selected"; enabled: !s.busy && s.selectedReady > 0
                                            onClicked: window.scope = "selected"
                                        }
                                        ScopeOption {
                                            objectName: "rejectOnlyOption"
                                            text: "Rejected files only"
                                            detail: "Uses the action below for rejects and leaves out ready files."
                                            ButtonGroup.group: scopeGroup
                                            visible: s.rejected > 0; enabled: !s.busy
                                            checked: window.scope === "none"; onClicked: window.scope = "none"
                                        }
                                    }
                                    Description {
                                        visible: s.unresolved > 0
                                        text: s.unresolved === 1 ? "1 file still needs a match in Review."
                                                                 : s.unresolved + " files still need a match in Review."
                                    }
                                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: window.line }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 0
                                        ChoiceCheck {
                                            objectName: "autoCleanupOption"
                                            text: "Clean up source folders after sorting"
                                            checked: s.autoCleanup; enabled: !s.busy
                                            onToggled: controller.setAutomatic(s.inPlace, s.autoRename, checked)
                                        }
                                        Description {
                                            Layout.leftMargin: 6
                                            font.pixelSize: 12
                                            text: "Archives system junk and checksums from successfully sorted folders. Also removes eligible empty folders."
                                        }
                                    }
                                }
                            }
                            Card {
                                visible: s.rejected > 0
                                Layout.fillWidth: true
                                implicitHeight: rejectOptions.implicitHeight + 32
                                ColumnLayout {
                                    id: rejectOptions
                                    anchors.fill: parent; anchors.margins: 16; spacing: 8
                                    SectionTitle { text: "Rejected files (" + s.rejected + ")" }
                                    SelectBox {
                                        objectName: "rejectModeBox"
                                        Accessible.name: "What to do with rejected files"
                                        Layout.fillWidth: true
                                        model: s.canRecycle ? [ "Leave in place", "Move to folder", "Send to Recycle Bin" ]
                                                            : [ "Leave in place", "Move to folder" ]
                                        currentIndex: ["leave", "folder", "recycle"].indexOf(window.rejectMode)
                                        enabled: !s.busy
                                        onActivated: function(index) { window.rejectMode = ["leave", "folder", "recycle"][index] }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        visible: window.rejectMode === "folder"
                                        Field {
                                            id: rejectFolderField
                                            objectName: "rejectFolderField"
                                            Layout.fillWidth: true; text: s.rejectFolder
                                            placeholderText: "Reject folder"
                                            Accessible.name: "Destination for rejected files"
                                            enabled: !s.busy
                                            onEditingFinished: if (text.trim() !== s.rejectFolder) controller.setPath("reject", text.trim())
                                        }
                                        ActionButton { text: "Browse"; enabled: !s.busy; onClicked: controller.pickFolder("reject") }
                                    }
                                    Description {
                                        text: window.rejectMode === "recycle" ? "Restore recycled files from the Windows Recycle Bin."
                                            : window.rejectMode === "folder" ? "Move rejected files while keeping their names and subfolders."
                                            : "Choose where rejected files go. You can review the list before applying."
                                    }
                                }
                            }
                            Card {
                                Layout.fillWidth: true
                                implicitHeight: toolsContent.implicitHeight + 32
                                ColumnLayout {
                                    id: toolsContent
                                    anchors.fill: parent; anchors.margins: 16; spacing: 8
                                    SectionTitle { text: "File tools" }
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 12
                                        ColumnLayout {
                                            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 5
                                            ActionButton {
                                                objectName: "cleanupButton"; text: "Review source cleanup"
                                                enabled: !s.busy && !!s.source
                                                onClicked: controller.prepare("cleanup")
                                            }
                                            Description { text: "Choose extra files to archive."; font.pixelSize: 12 }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 5
                                            ActionButton {
                                                objectName: "undoButton"; text: "Undo last operation"
                                                enabled: !s.busy; onClicked: controller.prepare("undo")
                                            }
                                            Description { text: "Reverse the last move, copy, rename, or cleanup."; font.pixelSize: 12 }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true; implicitHeight: 66; color: Theme.surface
            Rectangle { width: parent.width; height: 1; color: window.line }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24; spacing: 10
                BusyIndicator { running: s.busy; visible: running; Layout.preferredWidth: 25; Layout.preferredHeight: 25 }
                Label {
                    text: window.step === 2 && s.lastSort === s.status ? "" : s.status; textFormat: Text.PlainText; color: window.muted
                    Layout.fillWidth: true; elide: Text.ElideRight
                    HoverHandler { id: statusHover }
                    ToolTip.visible: statusHover.hovered && truncated
                    ToolTip.text: text
                }
                ActionButton {
                    objectName: "saveProgressButton"
                    text: "Save progress"
                    visible: window.step > 0 && window.hasScanned
                    enabled: !s.busy && s.total > 0
                    onClicked: {
                        if (window.step === 2)
                            window.captureOrganizePaths()
                        controller.saveProgress(window.step === 2 ? "organize" : "review", window.scope, window.rejectMode)
                    }
                }
                ActionButton {
                    objectName: "continueButton"
                    text: "Continue to organize"; primary: true; visible: window.step === 1
                    enabled: !s.busy && (s.ready > 0 || s.rejected > 0); onClicked: window.openOrganize()
                }
                ActionButton {
                    text: "Back to review"; visible: window.step === 2 && window.hasScanned
                    enabled: !s.busy; onClicked: window.step = 1
                }
                ActionButton {
                    objectName: "previewPlanButton"
                    text: window.planCount > 0 ? "Preview " + window.planCount + (window.planCount === 1 ? " file" : " files") : "Preview plan"
                    primary: true; visible: window.step === 2
                    enabled: !s.busy && window.planCount > 0
                        && (!window.scopeCount || s.inPlace || !!destinationField.text.trim())
                        && (!window.rejectCount || window.rejectMode !== "folder" || !!rejectFolderField.text.trim())
                    onClicked: {
                        window.captureOrganizePaths()
                        controller.prepareSort(window.scope, window.rejectMode)
                    }
                }
            }
        }
    }


    Wizard { backend: controller }

    Sheet {
        id: layouts
        objectName: "layoutsDialog"
        parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(590, parent.width - 40); modal: true; padding: 20
        title: "Customize folder layout"
        standardButtons: Dialog.Close
        contentItem: ColumnLayout {
            spacing: 10
            Description { text: "Adjust the structure and database tags for the selected library. Changes apply to the plan immediately." }
            GridLayout {
                columns: 2; columnSpacing: 16; rowSpacing: 5; Layout.fillWidth: true
                SmallLabel { text: "Movies" }
                SelectBox { model: controller.movieLayouts; textRole: "label"; valueRole: "value"; currentIndex: window.indexOfOption(model,s.movieLayout); Layout.fillWidth: true; onActivated: controller.setLayouts(currentValue,s.showLayout,s.idStyle) }
                SmallLabel { text: "TV shows" }
                SelectBox { model: controller.showLayouts; textRole: "label"; valueRole: "value"; currentIndex: window.indexOfOption(model,s.showLayout); Layout.fillWidth: true; onActivated: controller.setLayouts(s.movieLayout,currentValue,s.idStyle) }
                SmallLabel { text: "Database IDs" }
                SelectBox { model: controller.idStyles; textRole: "label"; valueRole: "value"; currentIndex: window.indexOfOption(model,s.idStyle); Layout.fillWidth: true; onActivated: controller.setLayouts(s.movieLayout,s.showLayout,currentValue) }
            }
            SmallLabel { text: "Example paths" }
            Label {
                text: controller.layoutExamples(s.movieLayout,s.showLayout,s.idStyle,s.autoRename).join("\n")
                color: window.ink; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere; font.pixelSize: 12
            }
            RowLayout {
                Label { text: "Naming guides"; color: window.muted; Layout.fillWidth: true }
                Repeater { model: ["Plex","Jellyfin","Emby"]; ActionButton { required property string modelData; text: modelData; onClicked: controller.openGuide(modelData) } }
            }
        }
    }
    SettingsWindow {
        id: settings
        transientParent: window
        connected: s.connected
        onDatabaseRequested: controller.requestDatabase()
        onClearCacheRequested: controller.prepare("clear")
        onDarkModeRequested: function(enabled) { controller.setDarkMode(enabled) }
    }
    Sheet {
        id: database
        objectName: "databaseDialog"
        parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(530, parent.width - 40); modal: true; padding: 20
        title: "TMDb connection"
        onOpened: token.text = ""
        contentItem: ColumnLayout {
            spacing: 10
            Label { text: s.connected ? "A token is saved. Enter a new one to replace it." : "Connect TMDb once to identify movies. TV lookup is also available through TVmaze."; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: window.muted }
            Field { id: token; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "TMDb API Read Access Token"; onAccepted: if (text.trim()) { controller.saveToken(text); database.close() } }
            RowLayout {
                Layout.fillWidth: true
                ActionButton { text: "Open TMDb API settings"; onClicked: controller.openUrl("https://www.themoviedb.org/settings/api") }
                Item { Layout.fillWidth: true }
                ActionButton { text: "Close"; onClicked: database.close() }
                ActionButton { text: "Save token"; primary: true; enabled: !!token.text.trim(); onClicked: { controller.saveToken(token.text); database.close() } }
            }
        }
    }
    ChangeHistory {
        id: changeHistory
        parent: Overlay.overlay
        backend: controller
        busy: s.busy
        resultText: /^(Reverted |Restored |Restore stopped)/.test(s.status) ? s.status : ""
    }
    Sheet {
        id: confirmation
        objectName: "confirmDialog"
        parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(690, parent.width - 40); modal: true; padding: 20
        title: operation.title || ""
        onClosed: controller.cancelPlan()
        onOpened: removeEmpty.checked = false
        contentItem: ColumnLayout {
            spacing: 9
            Description { text: operation.text || "" }
            SmallLabel {
                visible: operation.action === "sort"
                text: "Source file and planned destination"
            }
            ListView {
                id: confirmationRows
                Layout.fillWidth: true; Layout.preferredHeight: Math.min(325, count * 57)
                visible: count > 0; clip: true; model: operation.rows || []
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    id: confirmRow
                    required property var modelData
                    required property int index
                    width: confirmationRows.width - 12; height: 57
                    color: index % 2 ? Theme.surface : Theme.field; radius: 5
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 6
                        ChoiceCheck {
                            visible: operation.action === "cleanup"
                            checked: !!cleanupChecks[confirmRow.modelData.path]
                            Accessible.name: "Archive " + confirmRow.modelData.label
                            onToggled: {
                                let checks = Object.assign({}, cleanupChecks)
                                checks[confirmRow.modelData.path] = checked
                                cleanupChecks = checks
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Label { text: confirmRow.modelData.label; textFormat: Text.PlainText; elide: Text.ElideMiddle; Layout.fillWidth: true; color: window.ink; font.weight: Font.DemiBold }
                            Label {
                                text: confirmRow.modelData.detail; textFormat: Text.PlainText
                                elide: Text.ElideMiddle; Layout.fillWidth: true; color: window.muted; font.pixelSize: 12
                                HoverHandler { id: pathHover }
                                ToolTip.visible: pathHover.hovered && truncated
                                ToolTip.text: text
                            }
                        }
                    }
                }
            }
            ChoiceCheck { id: removeEmpty; text: "Also remove empty source folders"; visible: !!operation.canRemoveEmpty }
            Label { visible: removeEmpty.visible && removeEmpty.checked; Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Only folders that are empty after the selected files are archived will be removed."; color: window.muted }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "Save progress"; visible: operation.action === "sort"
                    onClicked: if (controller.saveProgress("organize", window.scope, window.rejectMode)) confirmation.close()
                }
                ActionButton { text: "Cancel"; onClicked: confirmation.close() }
                ActionButton {
                    objectName: "applyPlanButton"
                    text: operation.action === "cleanup" && removeEmpty.checked && !Object.keys(cleanupChecks).some(p => cleanupChecks[p]) ? "Remove empty folders" : (operation.button || "Continue"); primary: true
                    enabled: operation.action !== "cleanup" || removeEmpty.checked || Object.keys(cleanupChecks).some(p => cleanupChecks[p])
                    onClicked: {
                        controller.confirm(operation.action, Object.keys(cleanupChecks).filter(p => cleanupChecks[p]), removeEmpty.checked)
                        confirmation.close()
                    }
                }
            }
        }
    }
    Popup {
        id: notice
        parent: Overlay.overlay; x: parent.width - width - 20; y: parent.height - height - 70
        width: Math.min(430, parent.width - 40); padding: 13; closePolicy: Popup.NoAutoClose
        background: Rectangle { radius: 9; color: Theme.media }
        contentItem: Label { id: noticeText; wrapMode: Text.Wrap; color: Theme.mediaForeground; font.pixelSize: 13 }
    }
    Timer { id: noticeTimer; interval: 4400; onTriggered: notice.close() }
    Connections {
        target: controller
        function onToast(message) { window.showNotice(message) }
        function onScanStarted() {
            notice.close()
            controller.setReviewView("all")
            window.scannedSource = s.source
            window.step = 1
        }
        function onProgressResumed(stage, scope, rejectMode) {
            window.scannedSource = s.source
            window.scope = scope
            window.rejectMode = rejectMode
            window.step = stage === "organize" ? 2 : 1
        }
        function onDialogRequested(data) {
            if (data.kind === "database") { database.open(); return }
            operation = data
            let checks = {}
            for (const row of data.rows || []) if (row.path) checks[row.path] = !!row.checked
            cleanupChecks = checks
            confirmation.open()
        }
    }
}
