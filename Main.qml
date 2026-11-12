import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material

ApplicationWindow {
    id: window
    width: 1120; height: 780; minimumWidth: 760; minimumHeight: 580
    visible: true; title: "GPUCluster • Distributed AI Engine"
    color: "#0B1020"
    Material.theme: Material.Dark
    Material.accent: "#40D7B2"
    property int page: 0
    property bool drawerOpen: false
    property string localIP: "Not connected"
    property string statusText: "Ready to configure"
    property int progressValue: 0
    property var peerItems: []
    property var modelItems: []
    property string logText: ""
    property var navItems: ["Dashboard", "Devices", "Models", "Diagnostics", "Advanced", "Logs"]
    property var navIcons: ["⌂", "◈", "◎", "◷", "⚙", "≡"]
    property var fields: [
        {key:"peer",label:"Worker Tailscale IPv4"}, {key:"wsl_distro",label:"WSL distribution"},
        {key:"iperf_port",label:"iperf3 port"}, {key:"rpc_port",label:"RPC port"},
        {key:"api_port",label:"API port"}, {key:"llama_dir",label:"llama.cpp binaries directory"},
        {key:"model",label:"GGUF model path in WSL"}, {key:"context",label:"Context tokens"},
        {key:"gpu_layers",label:"GPU layers"}, {key:"tensor_split",label:"Tensor split (optional)"}
    ]
    Connections {
        target: bridge
        function onLogReceived(text) { window.logText += text + "\n\n" }
        function onStatusReceived(text,progress) { window.statusText=text; if(progress>=0) window.progressValue=progress }
        function onIpReceived(ip) { window.localIP=ip }
        function onPeersReceived(items) { window.peerItems=items }
        function onModelsReceived(items) { window.modelItems=items }
        function onErrorReceived(message) { errorDialog.message=message; errorDialog.open() }
    }
    Dialog {
        id: errorDialog; title: "Action required"; modal: true; anchors.centerIn: parent
        width: Math.min(490,window.width-50); standardButtons: Dialog.Ok
        property string message: ""
        Label { width: parent.width; wrapMode: Text.WordWrap; text: errorDialog.message; color: "#FCA5A5" }
    }
    Rectangle {
        id: sidebar; x: 0; y: 0; height: parent.height
        width: window.drawerOpen ? 232 : 0; clip: true; color: "#172033"; z: 3
        Behavior on width { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 16; spacing: 12
            Label { text: "GPUCLUSTER"; font.bold: true; font.pixelSize: 18; color: "#E2E8F0"; Layout.topMargin: 15 }
            Rectangle { height: 1; color: "#334155"; Layout.fillWidth: true }
            Repeater {
                model: window.navItems
                delegate: Rectangle {
                    required property int index
                    required property string modelData
                    Layout.fillWidth: true; height: 47; radius: 13
                    color: window.page===index ? "#254457" : (navMouse.containsMouse ? "#243149" : "transparent")
                    RowLayout { anchors.fill: parent; anchors.leftMargin: 13; spacing: 14
                        Label { text: window.navIcons[index]; font.pixelSize: 22; color: "#6EE7B7" }
                        Label { text: modelData; font.pixelSize: 14; color: "#E2E8F0" }
                    }
                    MouseArea { id: navMouse; anchors.fill: parent; hoverEnabled: true; onClicked: { window.page=index; window.drawerOpen=false } }
                }
            }
            Item { Layout.fillHeight: true }
            Label { text: "v4.0 • Qt Quick"; color: "#64748B"; font.pixelSize: 11 }
        }
    }
    Rectangle {
        x: sidebar.width; y: 0; width: parent.width-sidebar.width; height: 74; color: "#11192B"
        Behavior on x { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        RowLayout { anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 22; spacing: 16
            RoundButton { text: window.drawerOpen ? "❮" : "❯"; font.pixelSize: 19; onClicked: window.drawerOpen=!window.drawerOpen; implicitWidth: 44; implicitHeight: 44 }
            ColumnLayout { spacing: 0; Label { text: "GPUCluster"; font.bold: true; font.pixelSize: 22; color: "#F8FAFC" }
                Label { text: window.navItems[window.page] + "  /  Distributed AI Engine"; color: "#94A3B8"; font.pixelSize: 11 }
            }
            Item { Layout.fillWidth: true }
            Rectangle { width: 9; height: 9; radius: 5; color: window.localIP==="Not connected"?"#F59E0B":"#34D399" }
            Label { text: window.localIP; color: "#CBD5E1"; font.pixelSize: 12 }
        }
    }
    ScrollView {
        id: scroll; x: sidebar.width; y: 74; width: parent.width-sidebar.width; height: parent.height-74
        clip: true; ScrollBar.vertical.policy: ScrollBar.AsNeeded
        Behavior on x { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        ColumnLayout {
            width: Math.max(0,scroll.availableWidth-48); x: 24; spacing: 18
            Item { height: 12 }
            ColumnLayout { visible: window.page===0; spacing: 18; Layout.fillWidth: true
                Label { text: "Choose this device's role"; color: "#F8FAFC"; font.pixelSize: 22; font.bold: true }
                Label { text: "One-click setup for your distributed LLM cluster"; color: "#94A3B8"; font.pixelSize: 13 }
                RowLayout { Layout.fillWidth: true; spacing: 22
                    Repeater { model: ["host","worker"]
                        delegate: ColumnLayout { required property string modelData; Layout.fillWidth: true; spacing: 8
                            Rectangle { Layout.alignment: Qt.AlignHCenter; width: 116; height: 116; radius: 58
                                color: bridge.role===modelData ? "#176657" : "#253B60"
                                border.color: bridge.role===modelData ? "#6EE7B7" : "#5673A4"; border.width: 2
                                Text { anchors.centerIn: parent; text: modelData==="host"?"⌘":"◈"; color: "#D1FAE5"; font.pixelSize: 49 }
                                MouseArea { anchors.fill: parent; onClicked: bridge.chooseRole(modelData) }
                            }
                            Label { Layout.alignment: Qt.AlignHCenter; text: modelData.toUpperCase(); color: "#F8FAFC"; font.bold: true; font.pixelSize: 16 }
                            Label { Layout.alignment: Qt.AlignHCenter; text: modelData==="host"?"Run model and API":"Share remote GPU"; color: "#94A3B8"; font.pixelSize: 12 }
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; implicitHeight: setupContent.implicitHeight+34; radius: 20; color: "#172238"
                    ColumnLayout { id: setupContent; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 17; spacing: 13
                        Label { text: "Setup progress"; color: "#F8FAFC"; font.bold: true; font.pixelSize: 16 }
                        Label { text: window.statusText; color: "#CBD5E1"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        ProgressBar { from:0; to:100; value:window.progressValue; Layout.fillWidth:true }
                        Button { text: bridge.busy?"Working…":"Set up "+bridge.role.toUpperCase()+" device"; enabled:!bridge.busy; onClicked: confirmSetup.open() }
                        Label { text: "Windows administrator access, Tailscale sign-in and a restart may be required."; wrapMode: Text.Wrap; color: "#94A3B8"; Layout.fillWidth: true; font.pixelSize: 12 }
                    }
                }
                Rectangle { Layout.fillWidth: true; implicitHeight: quickContent.implicitHeight+32; radius:20; color:"#172238"
                    ColumnLayout { id:quickContent; anchors.left:parent.left; anchors.right:parent.right; anchors.top:parent.top; anchors.margins:16; spacing:10
                        Label { text:"Quick actions"; font.pixelSize:16; font.bold:true; color:"#F8FAFC" }
                        RowLayout { Layout.fillWidth:true
                            Button { text:"My Tailscale IP"; enabled:!bridge.busy; onClicked:bridge.refreshIP() }
                            Button { text:"Discover peers"; enabled:!bridge.busy; onClicked:bridge.discover() }
                            Button { text:"Find models"; enabled:!bridge.busy; onClicked:bridge.refreshModels() }
                        }
                    }
                }
            }
            ColumnLayout { visible: window.page===1; Layout.fillWidth:true; spacing:12
                Label { text:"Tailnet devices"; font.pixelSize:22; color:"#F8FAFC"; font.bold:true }
                Label { text:"Both PCs must join the same tailnet. Select the worker on your host."; color:"#94A3B8"; wrapMode:Text.Wrap; Layout.fillWidth:true }
                Button { text:"Refresh devices"; enabled:!bridge.busy; onClicked:bridge.discover() }
                Repeater { model: window.peerItems
                    delegate: Rectangle { required property var modelData; Layout.fillWidth:true; height:68; radius:15; color:"#172238"
                        RowLayout { anchors.fill:parent; anchors.margins:12
                            Rectangle { width:10; height:10; radius:5; color:modelData.online?"#34D399":"#64748B" }
                            ColumnLayout { Layout.fillWidth:true; spacing:2
                                Label { text:modelData.name; color:"#F8FAFC"; font.bold:true }
                                Label { text:modelData.ip+(modelData.online?" • Online":" • Offline"); color:"#94A3B8"; font.pixelSize:12 }
                            }
                            Button { text:"Use as worker"; enabled:modelData.online; onClicked: { bridge.selectPeer(modelData.ip); window.statusText="Selected worker: "+modelData.ip } }
                        }
                    }
                }
                Label { visible:window.peerItems.length===0; text:"No devices listed yet. Sign in to Tailscale and press Refresh devices."; color:"#94A3B8"; wrapMode:Text.Wrap }
            }
            ColumnLayout { visible:window.page===2; Layout.fillWidth:true; spacing:12
                Label { text:"Installed GGUF models"; color:"#F8FAFC"; font.pixelSize:22; font.bold:true }
                Label { text:"Models are scanned on this host. Ollama blobs may appear under SHA-256 names."; color:"#94A3B8"; wrapMode:Text.Wrap; Layout.fillWidth:true }
                Button { text:"Refresh installed models"; enabled:!bridge.busy; onClicked:bridge.refreshModels() }
                ComboBox { id:modelCombo; Layout.fillWidth:true; model:window.modelItems; textRole:"name"; enabled:window.modelItems.length>0
                    onActivated: function(index) { bridge.selectModel(window.modelItems[index].path) }
                }
                Label { text:"Selected model path: "+bridge.getOption("model"); color:"#94A3B8"; wrapMode:Text.WrapAnywhere; Layout.fillWidth:true }
                Button { text:"Start model server"; enabled:!bridge.busy && bridge.role==="host"; onClicked:confirmLaunch.open() }
            }
            ColumnLayout { visible:window.page===3; Layout.fillWidth:true; spacing:12
                Label { text:"Diagnostics & runtime"; color:"#F8FAFC"; font.pixelSize:22; font.bold:true }
                Label { text:"Run checks or start the service. Inspect Logs for command output."; color:"#94A3B8"; wrapMode:Text.Wrap; Layout.fillWidth:true }
                Button { text:"Check WSL / Tailscale / NVIDIA"; enabled:!bridge.busy; onClicked:bridge.diagnostics() }
                Button { text:"Check local model API"; enabled:!bridge.busy; onClicked:bridge.checkAPI() }
                Button { text:"Start llama.cpp service"; enabled:!bridge.busy; onClicked:confirmLaunch.open() }
                Label { text:"Worker RPC is not encrypted by itself. Never expose its port on a public router."; color:"#FBBF24"; wrapMode:Text.Wrap; Layout.fillWidth:true }
            }
            ColumnLayout { visible:window.page===4; Layout.fillWidth:true; spacing:13
                Label { text:"Advanced settings"; color:"#F8FAFC"; font.pixelSize:22; font.bold:true }
                Label { text:"These settings are optional. Changes are saved when you finish editing a field."; color:"#94A3B8"; wrapMode:Text.Wrap; Layout.fillWidth:true }
                Repeater { model:window.fields
                    delegate: ColumnLayout { required property var modelData; Layout.fillWidth:true; spacing:4
                        Label { text:modelData.label; color:"#CBD5E1"; font.pixelSize:12 }
                        TextField { Layout.fillWidth:true; text:bridge.getOption(modelData.key); selectByMouse:true
                            onEditingFinished:bridge.setOption(modelData.key,text)
                        }
                        Label { visible:modelData.key==="iperf_port" || modelData.key==="rpc_port";
                            text:modelData.key==="iperf_port" ? "?  iperf3 measures network throughput (default TCP 5201)." : "?  RPC provides remote GPU access (default TCP 50052). Restrict it to Tailscale."
                            color:"#94A3B8"; font.pixelSize:11; wrapMode:Text.Wrap; Layout.fillWidth:true }
                    }
                }
                Button { text:"Save settings"; onClicked:bridge.save() }
            }
            ColumnLayout { visible:window.page===5; Layout.fillWidth:true; spacing:10
                Label { text:"Activity logs"; color:"#F8FAFC"; font.pixelSize:22; font.bold:true }
                Rectangle { Layout.fillWidth:true; height:440; radius:15; color:"#111827"; clip:true
                    ScrollView { anchors.fill:parent; anchors.margins:12; ScrollBar.vertical.policy:ScrollBar.AsNeeded
                        TextArea { text:window.logText; readOnly:true; wrapMode:TextEdit.Wrap; color:"#D1D5DB"; font.family:"Consolas"; font.pixelSize:12; selectByMouse:true }
                    }
                }
                Button { text:"Clear log view"; onClicked:window.logText="" }
            }
            Item { height: 25 }
        }
    }
    Dialog { id:confirmSetup; title:"Confirm setup"; modal:true; anchors.centerIn:parent; width:Math.min(490,window.width-50)
        standardButtons:Dialog.Yes|Dialog.No
        Label { width:parent.width; wrapMode:Text.WordWrap; color:"#CBD5E1"; text:"Install or configure WSL2, Ubuntu, CUDA Toolkit, llama.cpp and Tailscale on this PC? This changes system settings and may require a restart." }
        onAccepted:bridge.setup()
    }
    Dialog { id:confirmLaunch; title:"Start service"; modal:true; anchors.centerIn:parent; width:Math.min(450,window.width-50)
        standardButtons:Dialog.Yes|Dialog.No
        Label { width:parent.width; wrapMode:Text.WordWrap; color:"#CBD5E1"; text:"Start llama.cpp using the current settings? Ensure the worker is trusted and connected over Tailscale." }
        onAccepted:bridge.launch()
    }
}
