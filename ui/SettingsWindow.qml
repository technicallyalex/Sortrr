import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import "."

ApplicationWindow {
    id: settings
    objectName: "settingsWindow"
    title: "Sortrr Settings"
    flags: Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint
    modality: Qt.WindowModal
    width: 590
    height: Math.min(760, Screen.height - 100)
    minimumWidth: 530
    minimumHeight: Math.min(580, Screen.height - 100)
    color: "transparent"
    font.family: "Segoe UI"

    required property var backend
    readonly property var watch: backend.watchInfo
    readonly property var cache: backend.cacheInfo
    readonly property var update: backend.updateState
    readonly property bool updating: update.status === "checking" || update.status === "downloading" || update.status === "installing"
    signal installUpdateRequested()
    required property bool connected
    signal darkModeRequested(bool enabled)
    signal databaseRequested()
    signal clearCacheRequested()

    onClosing: function(event) {
        if (settings.updating) event.accepted = false
    }
    onVisibleChanged: if (visible) backend.refreshCacheInfo()
    Shortcut { sequence: "Escape"; enabled: !settings.updating; onActivated: settings.close() }

    component SettingCard: Rectangle {
        Layout.fillWidth: true
        color: Theme.surface
        border.color: Theme.line
        radius: 13
    }
    component SettingTitle: Label {
        Layout.fillWidth: true
        color: Theme.ink
        font.pixelSize: 15
        font.weight: Font.DemiBold
    }
    component SettingDetail: Label {
        Layout.fillWidth: true
        color: Theme.muted
        font.pixelSize: 13
        wrapMode: Text.Wrap
    }

    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.top: parent.top; anchors.topMargin: 34
        color: Theme.canvas
        radius: 8
        z: -1
    }

    ColumnLayout {
        id: content
        anchors.fill: parent
        spacing: 0
        TitleBar {
            id: settingsChrome
            objectName: "settingsTitleBar"
            Layout.fillWidth: true
            implicitHeight: 98
            targetWindow: settings
            allowMinimize: false
            allowMaximize: false
            closeEnabled: !settings.updating
            headerContent: RowLayout {
                anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24
                spacing: 13
                Image {
                    source: "assets/sortrr.png"
                    Layout.preferredWidth: 42; Layout.preferredHeight: 42
                    fillMode: Image.PreserveAspectFit
                }
                Label {
                    Layout.fillWidth: true
                    text: "Settings"; color: Theme.ink
                    font.pixelSize: 26; font.weight: Font.DemiBold
                }
            }
        }

        ScrollView {
            id: settingsScroll
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                width: settingsScroll.availableWidth - 40
                x: 20; y: 20
                spacing: 12

            SettingCard {
                implicitHeight: appearanceRow.implicitHeight + 32
                RowLayout {
                    id: appearanceRow
                    anchors.fill: parent; anchors.margins: 16; spacing: 16
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        SettingTitle { text: "Appearance" }
                        SettingDetail { text: "Follow Windows or choose a theme." }
                    }
                    SelectBox {
                        objectName: "appearanceOption"
                        Accessible.name: "Appearance"
                        Layout.preferredWidth: 180
                        model: ["Use system setting", "Light", "Dark"]
                        currentIndex: ["system", "light", "dark"].indexOf(settings.backend.appearance)
                        enabled: !settings.backend.state.busy
                        onActivated: settings.backend.setAppearance(["system", "light", "dark"][currentIndex])
                    }
                }
            }

            SettingCard {
                objectName: "watchFoldersCard"
                implicitHeight: watchContent.implicitHeight + 32
                ColumnLayout {
                    id: watchContent
                    anchors.fill: parent; anchors.margins: 16
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        SettingTitle { text: "Watch folders"; Layout.fillWidth: true }
                        ActionButton {
                            objectName: "addWatchFolderButton"
                            text: "Add folder"
                            enabled: !settings.backend.state.busy
                            onClicked: settings.backend.addWatchFolder()
                        }
                    }
                    SettingDetail {
                        text: "Automatically identify new or changed media in these folders and their subfolders. Files must be unchanged for 60 seconds before scanning."
                    }
                    ChoiceCheck {
                        objectName: "backgroundModeOption"
                        Layout.fillWidth: true
                        text: "Keep running in the system tray when I close Sortrr"
                        checked: settings.watch.background
                        enabled: settings.watch.trayAvailable
                        onToggled: settings.backend.setWatchOption("background", checked)
                    }
                    SettingDetail {
                        text: settings.watch.trayAvailable
                            ? "Open, pause, review files, check for updates, or quit from the tray icon."
                            : "The system tray is unavailable. Sortrr will stay visible."
                        font.pixelSize: 12
                    }
                    ChoiceCheck {
                        objectName: "watchNotificationsOption"
                        text: "Notify me when new files are ready to review"
                        checked: settings.watch.notifications
                        onToggled: settings.backend.setWatchOption("notifications", checked)
                    }
                    SettingDetail {
                        visible: !settings.watch.background && settings.watch.notifications
                        text: "Notifications appear in Sortrr. Enable tray mode for Windows notifications while the window is closed."
                        font.pixelSize: 12
                    }
                    Repeater {
                        model: settings.watch.folders
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: folderContent.implicitHeight + 20
                            color: Theme.field; radius: 8; border.color: Theme.line
                            ColumnLayout {
                                id: folderContent
                                anchors.fill: parent; anchors.margins: 10; spacing: 6
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.path; textFormat: Text.PlainText
                                    wrapMode: Text.WrapAnywhere; color: Theme.ink; font.pixelSize: 12
                                }
                                SettingDetail {
                                    text: (!modelData.enabled || settings.watch.paused ? "Paused" : modelData.status)
                                          + (modelData.pending ? " | " + modelData.pending + " to review" : "")
                                    textFormat: Text.PlainText
                                    font.pixelSize: 12
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    ChoiceCheck {
                                        text: "Watch"; checked: modelData.enabled
                                        onToggled: settings.backend.enableWatchFolder(modelData.path, checked)
                                    }
                                    Item { Layout.fillWidth: true }
                                    ActionButton {
                                        text: "Review"
                                        enabled: !settings.watch.busy && !settings.backend.state.busy
                                        onClicked: {
                                            settings.close()
                                            settings.backend.reviewWatchFolder(modelData.path)
                                        }
                                    }
                                    ActionButton {
                                        text: "Remove"; subtle: true
                                        onClicked: settings.backend.removeWatchFolder(modelData.path)
                                    }
                                }
                            }
                        }
                    }
                    SettingDetail {
                        visible: !settings.watch.folders.length
                        text: "No watch folders yet. Add a folder to begin."
                    }
                    RowLayout {
                        ActionButton {
                            objectName: "checkWatchFoldersButton"
                            text: settings.watch.busy ? "Checking..." : "Check now"
                            enabled: !settings.watch.busy && !settings.backend.state.busy
                            onClicked: settings.backend.checkWatchFolders()
                        }
                        ActionButton {
                            text: settings.watch.paused ? "Resume all" : "Pause all"
                            onClicked: settings.backend.setWatchOption("paused", !settings.watch.paused)
                        }
                    }
                    SettingDetail {
                        visible: !!settings.watch.message
                        text: settings.watch.message
                        color: Theme.warning
                    }
                    SettingDetail {
                        text: "Identification only. Review matches and use Organize to copy, move, or rename files."
                        font.pixelSize: 12
                    }
                }
            }

            SettingCard {
                implicitHeight: databaseRow.implicitHeight + 32
                RowLayout {
                    id: databaseRow
                    anchors.fill: parent; anchors.margins: 16; spacing: 16
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 5
                        SettingTitle { text: "TMDb connection" }
                        SettingDetail { text: "Look up movie and show titles, posters, and details." }
                        Label {
                            text: settings.connected ? "Access token saved" : "Access token needed"
                            color: settings.connected ? Theme.success : Theme.warning
                            font.pixelSize: 12; font.weight: Font.DemiBold
                            padding: 5; leftPadding: 8; rightPadding: 8
                            background: Rectangle {
                                radius: 6
                                color: settings.connected ? Theme.successSoft : Theme.warningSoft
                            }
                        }
                    }
                    ActionButton {
                        objectName: "settingsDatabaseButton"
                        enabled: !settings.backend.state.busy
                        text: settings.connected ? "Manage token" : "Connect TMDb"
                        onClicked: {
                            settings.close()
                            settings.databaseRequested()
                        }
                    }
                }
            }

            SettingCard {
                implicitHeight: updateContent.implicitHeight + 32
                ColumnLayout {
                    id: updateContent
                    anchors.fill: parent; anchors.margins: 16; spacing: 9
                    RowLayout {
                        Layout.fillWidth: true; spacing: 12
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            SettingTitle { text: "App updates" }
                            SettingDetail { text: "Installed version " + settings.update.current }
                        }
                        ActionButton {
                            objectName: "checkUpdatesButton"
                            text: settings.update.status === "checking" ? "CheckingÃ¢â‚¬Â¦" : "Check for updates"
                            enabled: !settings.backend.state.busy && !settings.updating
                            onClicked: settings.backend.checkForUpdates()
                        }
                    }
                    SettingDetail {
                        objectName: "updateStatusText"
                        text: settings.update.message
                        color: settings.update.status === "error" ? Theme.warning : Theme.muted
                    }
                    ProgressBar {
                        objectName: "updateDownloadProgress"
                        Layout.fillWidth: true
                        visible: settings.update.status === "downloading"
                        from: 0; to: 1; value: settings.update.progress
                    }
                    SettingDetail {
                        visible: !!settings.update.available && settings.update.canInstall
                        text: "Sortrr will save your review progress, install the update, and restart."
                    }
                    SettingDetail {
                        visible: !!settings.update.available && !settings.update.canInstall
                        text: "Open the packaged Windows app to install updates automatically."
                    }
                    ActionButton {
                        objectName: "installUpdateButton"
                        text: "Install update and restart"
                        visible: !!settings.update.available && settings.update.canInstall
                        enabled: !settings.backend.state.busy && !settings.updating
                        primary: true
                        onClicked: settings.installUpdateRequested()
                    }
                }
            }

            SettingCard {
                implicitHeight: cacheContent.implicitHeight + 32
                ColumnLayout {
                    id: cacheContent
                    anchors.fill: parent; anchors.margins: 16; spacing: 9
                    RowLayout {
                        Layout.fillWidth: true
                        SettingTitle { text: "Cache storage" }
                        Label {
                            objectName: "cacheSizeText"
                            text: settings.cache.measuring ? "CalculatingÃ¢â‚¬Â¦" : settings.cache.size
                            color: Theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold
                        }
                        ActionButton {
                            objectName: "refreshCacheButton"
                            text: "Refresh"; subtle: true
                            enabled: !settings.backend.state.busy && !settings.cache.measuring
                            onClicked: settings.backend.refreshCacheInfo()
                        }
                    }
                    SettingDetail { text: "Thumbnails, posters, and database responses." }
                    SettingDetail {
                        objectName: "cacheDirectoryText"
                        text: settings.cache.directory
                        textFormat: Text.PlainText
                        wrapMode: Text.WrapAnywhere
                        font.pixelSize: 12
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        ActionButton {
                            objectName: "changeCacheDirectoryButton"
                            text: settings.cache.moving ? "Moving cache..." : "Change folder"
                            enabled: !settings.backend.state.busy
                            onClicked: settings.backend.chooseCacheDirectory()
                        }
                        ActionButton {
                            objectName: "settingsCacheButton"
                            enabled: !settings.backend.state.busy
                            text: "Clear cache"
                            onClicked: {
                                settings.close()
                                settings.clearCacheRequested()
                            }
                        }
                    }
                    SettingDetail {
                        visible: !!settings.cache.message
                        text: settings.cache.message
                        color: settings.cache.message.startsWith("Could not") ? Theme.warning : Theme.muted
                    }
                    SettingDetail {
                        text: "Changing folders moves cached files. Saved matches, settings, and change history stay in app data."
                        font.pixelSize: 12
                    }
                    SettingDetail {
                        text: "Clear cache also resets saved matches and review progress. You can review this before confirming."
                        font.pixelSize: 12
                    }
                }
            }
                Item { Layout.preferredHeight: 20 }
            }
        }

        Rectangle {
            Layout.fillWidth: true; implicitHeight: 64
            color: Theme.surface
            Rectangle { width: parent.width; height: 1; color: Theme.line }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24
                Item { Layout.fillWidth: true }
                ActionButton {
                    objectName: "settingsDoneButton"
                    text: "Done"; primary: true; Layout.preferredWidth: 88; enabled: !settings.updating
                    onClicked: settings.close()
                }
            }
        }
    }
    WindowFrame { targetWindow: settings; tabWidth: settingsChrome.tabWidth }

}
