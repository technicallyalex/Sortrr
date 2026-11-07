pragma Singleton
import QtQuick

QtObject {
    readonly property bool dark: controller.darkMode

    readonly property color canvas: dark ? "#111522" : "#f2f4f9"
    readonly property color surface: dark ? "#1a2031" : "#ffffff"
    readonly property color field: dark ? "#151a2a" : "#f8f9fd"
    readonly property color raised: dark ? "#252d43" : "#edf0f7"
    readonly property color ink: dark ? "#edf0ff" : "#171e33"
    readonly property color muted: dark ? "#b2bdd5" : "#505d76"
    readonly property color quiet: dark ? "#9daac6" : "#65738d"
    readonly property color line: dark ? "#343e57" : "#dbe2ef"
    readonly property color accent: dark ? "#515ad6" : "#424bcc"
    readonly property color accentHover: dark ? "#565fde" : "#373fb6"
    readonly property color accentDown: dark ? "#454dc1" : "#30369c"
    readonly property color accentSoft: dark ? "#2c3561" : "#e9ecff"
    readonly property color accentInk: dark ? "#c2c8ff" : "#30399f"
    readonly property color focus: dark ? "#aab4ff" : "#424bcc"
    readonly property color accentForeground: "#ffffff"
    readonly property color success: dark ? "#8be0b9" : "#147055"
    readonly property color successSoft: dark ? "#203a38" : "#e3f4ec"
    readonly property color warning: dark ? "#f4c783" : "#8a5518"
    readonly property color warningSoft: dark ? "#443428" : "#fff0d9"
    readonly property color danger: dark ? "#ffadb5" : "#a53d45"
    readonly property color media: dark ? "#0d1120" : "#101729"
    readonly property color mediaText: "#c4cde3"
    readonly property color mediaForeground: "#f5f7ff"
    readonly property color disabled: dark ? "#8d9bb8" : "#737f96"
}
