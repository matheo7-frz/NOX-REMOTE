// Accueil NOX REMOTE 2 - fait par math_0235
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Controls.Material

import org.streetpea.chiaking

Rectangle {
    id: home
    signal showConsoleList()

    gradient: Gradient {
        GradientStop { position: 0.0; color: "#0b1530" }
        GradientStop { position: 0.55; color: "#060b1c" }
        GradientStop { position: 1.0; color: "#020409" }
    }

    // ---------- Recherche de la console ----------
    function findHost(wantPs5) {
        var hosts = Chiaki.hosts;
        var best = -1, bestScore = 0;
        for (var i = 0; i < hosts.length; i++) {
            var h = hosts[i];
            if (!h.display || !!h.ps5 !== wantPs5)
                continue;
            var score = 0;
            if (h.discovered && h.registered) score = 4;       // sur le Wi-Fi + associée
            else if (h.registered || h.duid) score = 3;        // associée (PSN / manuelle)
            else if (h.discovered) score = 2;                  // trouvée mais pas encore associée
            else score = 1;
            if (score > bestScore) { best = i; bestScore = score; }
        }
        return best;
    }

    function statusText(wantPs5) {
        var i = findHost(wantPs5);
        if (i < 0)
            return qsTr("Aucune console trouvée");
        var h = Chiaki.hosts[i];
        if (h.discovered && !h.registered)
            return qsTr("Trouvée - clique pour l'associer");
        if (h.state === "standby")
            return qsTr("En veille - elle va s'allumer");
        if (h.state === "ready")
            return qsTr("Allumée - prête");
        return h.registered || h.duid ? qsTr("Associée") : qsTr("Pas encore associée");
    }

    function connectConsole(wantPs5) {
        var i = findHost(wantPs5);
        if (i < 0) {
            infoLabel.text = wantPs5
                ? qsTr("Aucune PS5 trouvée. Allume ta PS5 sur le même Wi-Fi, ou ajoute-la dans « Consoles ».")
                : qsTr("Aucune PS4 trouvée. Allume ta PS4 sur le même Wi-Fi, ou ajoute-la dans « Consoles ».");
            return;
        }
        var h = Chiaki.hosts[i];
        infoLabel.text = qsTr("Connexion à %1...").arg(Chiaki.settings.streamerMode ? (wantPs5 ? "PS5" : "PS4") : h.name);
        if (h.discovered)
            Chiaki.connectToHost(i, h.name);
        else
            Chiaki.connectToHost(i);
    }

    Keys.onLeftPressed: ps5Tile.forceActiveFocus()
    Keys.onRightPressed: ps4Tile.forceActiveFocus()
    Keys.onMenuPressed: root.showSettingsDialog()
    Keys.onEscapePressed: root.showConfirmDialog(qsTr("Quitter"), qsTr("Tu veux vraiment quitter NOX REMOTE ?"), () => Qt.quit())

    // ---------- Barre du haut ----------
    RowLayout {
        id: topBar
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            topMargin: 18
            leftMargin: 28
            rightMargin: 22
        }
        height: 64
        spacing: 14

        Image {
            Layout.preferredWidth: 52
            Layout.preferredHeight: 52
            source: "qrc:/icons/noxremote-logo.png"
            sourceSize: Qt.size(104, 104)
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }
        Label {
            text: "NOX REMOTE"
            font.pixelSize: 26
            font.bold: true
            font.letterSpacing: 3
            color: "white"
        }

        Item { Layout.fillWidth: true }

        component TopButton: Button {
            Layout.preferredHeight: 56
            flat: true
            focusPolicy: Qt.NoFocus
            font.pixelSize: 16
            Material.foreground: "white"
            Material.roundedScale: Material.FullScale
        }

        TopButton {
            text: qsTr("Consoles")
            onClicked: home.showConsoleList()
        }
        TopButton {
            text: qsTr("Manette")
            onClicked: root.showControllerMappingDialog()
        }
        TopButton {
            text: Chiaki.settings.psnAuthToken ? qsTr("Compte PSN ✓") : qsTr("Connexion PSN")
            onClicked: {
                if (Chiaki.settings.psnAuthToken)
                    Chiaki.refreshPsnToken();
                else
                    root.showPSNTokenDialog(false);
            }
        }
        TopButton {
            icon.source: "qrc:/icons/settings-20px.svg"
            icon.width: 34
            icon.height: 34
            Layout.preferredWidth: 64
            onClicked: root.showSettingsDialog()
        }
    }

    // ---------- Titre + tuiles ----------
    ColumnLayout {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: 10
        spacing: 34

        Label {
            Layout.alignment: Qt.AlignHCenter
            text: qsTr("Quelle console veux-tu connecter ?")
            font.pixelSize: 34
            font.weight: Font.Light
            color: "white"
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 40

            component ConsoleTile: Button {
                id: tile
                property bool ps5: true
                property Item page: null
                Layout.preferredWidth: !page ? 300 : Math.min(page.width * 0.32, 420)
                Layout.preferredHeight: !page ? 300 : Math.min(page.height * 0.48, 380)
                flat: true
                focusPolicy: Qt.StrongFocus
                Keys.onReturnPressed: clicked()
                onClicked: if (page) page.connectConsole(ps5)

                background: Rectangle {
                    radius: 22
                    color: tile.down ? "#22335f" : (tile.hovered || tile.activeFocus ? "#1a2a52" : "#111c38")
                    border.width: tile.hovered || tile.activeFocus ? 3 : 1
                    border.color: tile.hovered || tile.activeFocus ? "#ffffff" : "#2c3c66"
                    scale: tile.hovered || tile.activeFocus ? 1.03 : 1.0
                    Behavior on scale { NumberAnimation { duration: 120 } }
                    Behavior on color { ColorAnimation { duration: 120 } }
                }

                contentItem: ColumnLayout {
                    spacing: 10
                    Image {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillHeight: true
                        Layout.preferredWidth: tile.width * 0.55
                        Layout.topMargin: 20
                        fillMode: Image.PreserveAspectFit
                        source: "image://svg/console-ps" + (tile.ps5 ? "5" : "4") + "#light_on"
                        sourceSize: Qt.size(width, height)
                    }
                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: tile.ps5 ? "PS5" : "PS4"
                        font.pixelSize: 40
                        font.bold: true
                        color: "white"
                    }
                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.bottomMargin: 18
                        text: { Chiaki.hosts; return tile.page ? tile.page.statusText(tile.ps5) : ""; }
                        font.pixelSize: 15
                        color: "#9fb0d8"
                    }
                }
            }

            ConsoleTile { id: ps5Tile; ps5: true; page: home }
            ConsoleTile { id: ps4Tile; ps5: false; page: home }
        }

        Label {
            id: infoLabel
            Layout.alignment: Qt.AlignHCenter
            Layout.maximumWidth: home.width * 0.8
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            text: qsTr("Branche ta manette au PC, puis choisis ta console.")
            font.pixelSize: 16
            color: "#c8d3f0"
        }
    }

    Label {
        anchors {
            bottom: parent.bottom
            horizontalCenter: parent.horizontalCenter
            bottomMargin: 16
        }
        text: "NOX REMOTE 2 · fait par math_0235"
        font.pixelSize: 13
        color: "#5d6c94"
    }

    Component.onCompleted: ps5Tile.forceActiveFocus()
}
