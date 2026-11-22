// Accueil NOX REMOTE 2 - fait par math_0235
import QtQuick
import QtCore
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

    Settings {
        id: livePrefs
        category: "noxremote"
        property bool liveMode: false
    }

    // Réglages stables pour OBS / TikTok Live Studio / Discord
    function applyLiveMode(on) {
        livePrefs.liveMode = on;
        Chiaki.settings.streamerMode = on;          // cache IP / identifiants à l'écran
        if (!on)
            return;
        Chiaki.settings.showStreamStats = false;    // pas de stats par-dessus l'image
        Chiaki.settings.hideCursor = true;          // pas de curseur dans le live
        Chiaki.settings.vSyncEnabled = true;        // image sans déchirure
        Chiaki.settings.windowType = 0;             // fenêtre de taille fixe = capture stable
        Chiaki.settings.resolutionLocalPS5 = 4;     // 1080p
        Chiaki.settings.fpsLocalPS5 = 60;
        Chiaki.settings.resolutionRemotePS5 = 4;
        Chiaki.settings.fpsRemotePS5 = 60;
        Chiaki.settings.codecLocalPS5 = 1;          // H265 sans HDR (le HDR rend l'image délavée dans OBS)
        Chiaki.settings.codecRemotePS5 = 1;
        Chiaki.settings.fpsLocalPS4 = 60;
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
                ? qsTr("Aucune PS5 trouvée. Allume ta PS5 sur le même réseau, ou ajoute-la avec « Gérer mes consoles » en bas à droite.")
                : qsTr("Aucune PS4 trouvée. Allume ta PS4 sur le même réseau, ou ajoute-la avec « Gérer mes consoles » en bas à droite.");
            return;
        }
        var h = Chiaki.hosts[i];
        infoLabel.text = qsTr("Connexion à %1...").arg(Chiaki.settings.streamerMode ? (wantPs5 ? "PS5" : "PS4") : h.name);
        if (h.discovered)
            Chiaki.connectToHost(i, h.name);
        else
            Chiaki.connectToHost(i);
    }

    // Même fond d'écran que l'écran de chargement
    Image {
        id: homeWallpaper
        smooth: true
        mipmap: true
        anchors.fill: parent
        source: "qrc:/icons/noxremote-loading.jpg"
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        visible: status === Image.Ready
    }
    Rectangle {
        anchors.fill: parent
        visible: homeWallpaper.visible
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#cc000000" }
            GradientStop { position: 0.25; color: "#55000000" }
            GradientStop { position: 0.75; color: "#55000000" }
            GradientStop { position: 1.0; color: "#dd000000" }
        }
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

        Rectangle {
            visible: livePrefs.liveMode
            Layout.preferredHeight: 34
            Layout.preferredWidth: liveBadge.implicitWidth + 28
            radius: 17
            color: "#e0203c"
            Label {
                id: liveBadge
                anchors.centerIn: parent
                text: "● MODE LIVE"
                font.pixelSize: 14
                font.bold: true
                color: "white"
            }
            SequentialAnimation on opacity {
                running: livePrefs.liveMode
                loops: Animation.Infinite
                NumberAnimation { to: 0.65; duration: 900; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
            }
        }

        TopButton {
            text: livePrefs.liveMode ? qsTr("Live : ON") : qsTr("Mode Live")
            onClicked: home.applyLiveMode(!livePrefs.liveMode)
        }
        TopButton {
            text: qsTr("Guide Live")
            onClicked: liveGuide.open()
        }
        TopButton {
            text: qsTr("Captures")
            onClicked: Chiaki.window.openCaptureFolder()
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
                    color: tile.down ? "#cc22335f" : (tile.hovered || tile.activeFocus ? "#b31a2a52" : "#8c0b1228")
                    border.width: tile.hovered || tile.activeFocus ? 3 : 1
                    border.color: tile.hovered || tile.activeFocus ? "#ffffff" : "#66ffffff"
                    scale: tile.hovered || tile.activeFocus ? 1.03 : 1.0
                    Behavior on scale { NumberAnimation { duration: 120 } }
                    Behavior on color { ColorAnimation { duration: 120 } }
                }

                contentItem: Item {
                    Label {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: -14
                        text: tile.ps5 ? "PS5" : "PS4"
                        font.pixelSize: Math.max(56, tile.height * 0.28)
                        font.weight: Font.Black
                        font.letterSpacing: 6
                        color: "white"
                        opacity: tile.hovered || tile.activeFocus ? 1.0 : 0.9
                    }
                    RowLayout {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 22
                        spacing: 8
                        Rectangle {
                            width: 10; height: 10; radius: 5
                            color: { Chiaki.hosts; var t = tile.page ? tile.page.statusText(tile.ps5) : "";
                                     return t.indexOf("Allumée") === 0 ? "#2ee66b" : (t.indexOf("En veille") === 0 ? "#f5a623" : (t.indexOf("Aucune") === 0 ? "#e0203c" : "#5aa0ff")); }
                        }
                        Label {
                            text: { Chiaki.hosts; return tile.page ? tile.page.statusText(tile.ps5) : ""; }
                            font.pixelSize: 15
                            color: "#9fb0d8"
                        }
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

    Button {
        anchors { bottom: parent.bottom; right: parent.right; rightMargin: 22; bottomMargin: 8 }
        flat: true
        focusPolicy: Qt.NoFocus
        text: qsTr("Gérer mes consoles")
        font.pixelSize: 13
        Material.foreground: "#7d8bb3"
        onClicked: home.showConsoleList()
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

    Popup {
        id: liveGuide
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.86, 980)
        height: Math.min(parent.height * 0.86, 720)
        modal: true
        focus: true
        padding: 28
        background: Rectangle { radius: 20; color: "#0d1733"; border.color: "#2c3c66"; border.width: 1 }
        onClosed: ps5Tile.forceActiveFocus()

        ColumnLayout {
            anchors.fill: parent
            spacing: 14
            RowLayout {
                Layout.fillWidth: true
                Label { text: qsTr("Guide Live - sans coupure"); font.pixelSize: 26; font.bold: true; color: "white"; Layout.fillWidth: true }
                Button { text: "✕"; flat: true; Material.foreground: "white"; onClicked: liveGuide.close() }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                Label {
                    width: liveGuide.availableWidth - 20
                    wrapMode: Text.WordWrap
                    textFormat: Text.RichText
                    color: "#dbe4ff"
                    font.pixelSize: 16
                    text: qsTr("<h3>Avant de lancer le live</h3>"
                        + "<ul><li>Clique sur <b>Mode Live</b> en haut : 1080p 60 i/s, pas de HDR, image sans déchirure, IP cachée, pas de curseur.</li>"
                        + "<li>Branche le PC <b>et</b> la PS5 en <b>câble Ethernet</b> si possible : c'est ce qui évite le plus les coupures.</li>"
                        + "<li>Ferme les téléchargements (Steam, mises à jour PS5...) pendant le live.</li>"
                        + "<li>Ne change pas la taille de la fenêtre NOX REMOTE 2 pendant le live.</li></ul>"
                        + "<h3>OBS</h3>"
                        + "<ul><li>Source <b>Capture de fenêtre</b> → fenêtre <b>[NOX-REMOTE-2.exe] NOX REMOTE 2</b>.</li>"
                        + "<li>Méthode de capture : <b>Windows 10 (1903 et plus)</b>. Correspondance : <b>même exécutable</b>.</li>"
                        + "<li>Son : source <b>Capture audio d'application</b> → NOX-REMOTE-2.exe.</li></ul>"
                        + "<h3>TikTok Live Studio</h3>"
                        + "<ul><li>Ajouter une source → <b>Fenêtre</b> → <b>NOX REMOTE 2</b>.</li>"
                        + "<li>Son : ajoute l'audio de l'application / audio du PC.</li></ul>"
                        + "<h3>Discord</h3>"
                        + "<ul><li>Partager ton écran → onglet <b>Applications</b> → <b>NOX REMOTE 2</b>, son activé.</li></ul>"
                        + "<h3>Pendant le jeu</h3>"
                        + "<ul><li><b>F4</b> ou <b>F10</b> : ouvrir / fermer la barre du bas (son, luminosité, micro, capture). Un clic sur l'image la ferme aussi.</li>"
                        + "<li><b>F12</b>, le bouton <b>Capture</b> ou <b>Create + clic du pavé tactile</b> sur la manette : capture d'écran dans Images → <b>Nox Remote Capture</b>.</li>"
                        + "<li><b>Micro</b> : choisis le micro de la manette ou celui du PC dans la barre du bas (pris en compte à la prochaine activation du micro).</li></ul>"
                        + "<h3>Si ça coupe quand même</h3>"
                        + "<ul><li>Réglages ⚙️ → baisse le <b>débit (bitrate)</b> ou passe en <b>720p</b>.</li>"
                        + "<li>Si l'écran est noir dans OBS : change la méthode de capture, ou lance OBS en même temps que NOX REMOTE 2 (pas en administrateur).</li></ul>")
                }
            }
        }
    }

    Component.onCompleted: ps5Tile.forceActiveFocus()
}
