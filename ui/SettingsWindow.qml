import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import "."

ApplicationWindow {
    id: settings
    objectName: "settingsWindow"
    title: "Sortrr Settings"
    flags: Qt.Dialog | Qt.WindowCloseButtonHint
    modality: Qt.WindowModal
    width: 590
    height: content.implicitHeight
    minimumWidth: 530
    minimumHeight: content.implicitHeight
    color: Theme.canvas
    font.family: "Segoe UI"

    required property bool connected
    signal darkModeRequested(bool enabled)
    signal databaseRequested()
    signal clearCacheRequested()

    Shortcut { sequence: "Escape"; onActivated: settings.close() }

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

    ColumnLayout {
        id: content
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true; implicitHeight: 88
            color: Theme.surface
            RowLayout {
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
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }
        }

        ColumnLayout {
            Layout.fillWidth: true; Layout.margins: 20
            spacing: 12

            SettingCard {
                implicitHeight: appearanceRow.implicitHeight + 32
                RowLayout {
                    id: appearanceRow
                    anchors.fill: parent; anchors.margins: 16; spacing: 16
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        SettingTitle { text: "Appearance" }
                        SettingDetail { text: "Use dark mode throughout Sortrr." }
                    }
                    Switch {
                        id: themeSwitch
                        objectName: "darkModeOption"
                        Accessible.name: "Dark mode"
                        checked: Theme.dark
                        onToggled: settings.darkModeRequested(checked)
                        implicitWidth: implicitIndicatorWidth + leftPadding + rightPadding
                        implicitHeight: implicitIndicatorHeight + topPadding + bottomPadding
                        padding: 4
                        contentItem: Item {}
                        indicator: Rectangle {
                            implicitWidth: 46; implicitHeight: 26
                            x: themeSwitch.leftPadding; y: (themeSwitch.height - height) / 2
                            radius: height / 2
                            color: themeSwitch.checked ? Theme.accent : Theme.raised
                            border.color: themeSwitch.visualFocus ? Theme.focus : Theme.quiet
                            border.width: themeSwitch.visualFocus ? 2 : themeSwitch.checked ? 0 : 1
                            Rectangle {
                                width: 18; height: 18; radius: 9
                                anchors.verticalCenter: parent.verticalCenter
                                x: themeSwitch.checked ? parent.width - width - 4 : 4
                                color: themeSwitch.checked ? Theme.accentForeground : Theme.quiet
                            }
                        }
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
                        text: settings.connected ? "Manage token" : "Connect TMDb"
                        onClicked: {
                            settings.close()
                            settings.databaseRequested()
                        }
                    }
                }
            }

            SettingCard {
                implicitHeight: cacheRow.implicitHeight + 32
                RowLayout {
                    id: cacheRow
                    anchors.fill: parent; anchors.margins: 16; spacing: 16
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 4
                        SettingTitle { text: "Identification cache" }
                        SettingDetail { text: "Reset saved matches, lookup results, and review progress. Your media files stay in place." }
                    }
                    ActionButton {
                        objectName: "settingsCacheButton"
                        text: "Clear cache"
                        onClicked: {
                            settings.close()
                            settings.clearCacheRequested()
                        }
                    }
                }
            }
        }

        Item { Layout.fillHeight: true }

        Rectangle {
            Layout.fillWidth: true; implicitHeight: 64
            color: Theme.surface
            Rectangle { width: parent.width; height: 1; color: Theme.line }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24
                Item { Layout.fillWidth: true }
                ActionButton {
                    objectName: "settingsDoneButton"
                    text: "Done"; primary: true; Layout.preferredWidth: 88
                    onClicked: settings.close()
                }
            }
        }
    }
}
