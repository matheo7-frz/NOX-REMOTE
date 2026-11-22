// Saisie de code en petites cases - NOX REMOTE 2 (fait par math_0235)
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

import org.streetpea.chiaking

FocusScope {
    id: codeRoot
    property int length: 4
    property alias text: input.text
    readonly property bool acceptableInput: input.text.length === length
    property bool hidden: Chiaki.settings.streamerMode
    property int boxSize: 58
    signal accepted()

    implicitWidth: boxes.implicitWidth
    implicitHeight: boxSize + 8

    function clear() { input.text = ""; }

    TextInput {
        id: input
        focus: true
        width: 0
        height: 0
        opacity: 0
        maximumLength: codeRoot.length
        inputMethodHints: Qt.ImhDigitsOnly
        validator: RegularExpressionValidator { regularExpression: /[0-9]*/ }
        Keys.onReturnPressed: if (codeRoot.acceptableInput) codeRoot.accepted()
        Keys.onEnterPressed: if (codeRoot.acceptableInput) codeRoot.accepted()
    }

    MouseArea {
        anchors.fill: parent
        onClicked: input.forceActiveFocus()
    }

    Row {
        id: boxes
        anchors.centerIn: parent
        spacing: codeRoot.length > 4 ? 8 : 12

        Repeater {
            model: codeRoot.length
            delegate: Rectangle {
                id: box
                required property int index
                readonly property bool filled: index < input.text.length
                readonly property bool current: input.activeFocus && index === Math.min(input.text.length, codeRoot.length - 1)
                // petit espace au milieu pour les codes à 8 chiffres
                width: codeRoot.boxSize * (codeRoot.length > 4 ? 0.8 : 1)
                height: codeRoot.boxSize
                radius: 10
                color: filled ? "#1c2c58" : "#0d1630"
                border.width: current ? 3 : 1
                border.color: current ? "#ffffff" : (filled ? "#5aa0ff" : "#2c3c66")
                scale: current ? 1.06 : 1.0
                Behavior on scale { NumberAnimation { duration: 110 } }
                Behavior on color { ColorAnimation { duration: 110 } }

                Text {
                    anchors.centerIn: parent
                    text: box.filled ? (codeRoot.hidden ? "●" : input.text.charAt(box.index)) : ""
                    color: "white"
                    font.pixelSize: codeRoot.boxSize * 0.5
                    font.bold: true
                }

                // curseur qui clignote dans la case active
                Rectangle {
                    visible: box.current && !box.filled
                    anchors.centerIn: parent
                    width: 3
                    height: parent.height * 0.45
                    radius: 1
                    color: "white"
                    SequentialAnimation on opacity {
                        running: visible
                        loops: Animation.Infinite
                        NumberAnimation { to: 0; duration: 450 }
                        NumberAnimation { to: 1; duration: 450 }
                    }
                }
            }
        }
    }

    Component.onCompleted: input.forceActiveFocus()
    onActiveFocusChanged: if (activeFocus) input.forceActiveFocus()
}
