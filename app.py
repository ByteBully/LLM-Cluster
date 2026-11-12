
"""GPUCluster v4 — English Qt Quick/QML desktop UI."""

import ctypes
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, Property, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from backend import Engine, admin


def elevate_without_console():
    """Restart the application as administrator without a console window."""
    if os.name != "nt":
        return False

    executable = Path(sys.executable)

    if executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.is_file():
            executable = pythonw

    script = Path(__file__).resolve()

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(executable),
        subprocess.list2cmdline([str(script), *sys.argv[1:]]),
        str(script.parent),
        1,
    )

    return result > 32


class Bridge(QObject):
    logReceived = Signal(str)
    statusReceived = Signal(str, int)
    ipReceived = Signal(str)
    peersReceived = Signal("QVariantList")
    modelsReceived = Signal("QVariantList")
    errorReceived = Signal(str)
    roleChanged = Signal()
    busyChanged = Signal()

    def __init__(self):
        super().__init__()
        self.core = Engine(self._emit)
        self._role = self.core.vars["role"].get()
        self._busy = False

    @Property(str, notify=roleChanged)
    def role(self):
        return self._role

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    def _emit(self, kind, value):
        if kind == "log":
            self.logReceived.emit(str(value))
        elif kind == "status":
            progress = value.get("progress")
            self.statusReceived.emit(
                str(value.get("message", "")),
                int(progress) if progress is not None else -1,
            )
        elif kind == "ip":
            self.ipReceived.emit(str(value))
        elif kind == "peers":
            self.peersReceived.emit(value)
        elif kind == "models":
            self.modelsReceived.emit(value)

    def _run(self, fn):
        if self._busy:
            return

        self._busy = True
        self.busyChanged.emit()

        def work():
            try:
                fn()
            except Exception as exc:
                self.logReceived.emit(
                    "ERROR: " + str(exc) + "\n" + traceback.format_exc()
                )
                self.errorReceived.emit(str(exc))
            finally:
                self._busy = False
                self.busyChanged.emit()

        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def chooseRole(self, role):
        if role not in ("host", "worker"):
            return

        self._role = role
        self.core.vars["role"].set(role)
        self.core.save()
        self.roleChanged.emit()

        self.statusReceived.emit(
            f"Selected {role.upper()}. Press Set up device to continue.",
            0,
        )

    @Slot()
    def setup(self):
        if not admin():
            self.errorReceived.emit(
                "Run as Windows administrator to configure WSL2."
            )
            return

        self._run(lambda: self.core.setup(self._role))

    @Slot()
    def discover(self):
        self._run(self.core.peers)

    @Slot()
    def refreshIP(self):
        self._run(self.core.tailscale_ip)

    @Slot()
    def refreshModels(self):
        self._run(self.core.scan_models)

    @Slot(str)
    def selectPeer(self, ip):
        self.core.vars["peer"].set(ip)
        self.core.save()

    @Slot(str)
    def selectModel(self, path):
        self.core.vars["model"].set(path)
        self.core.save()

    @Slot()
    def launch(self):
        self._run(self.core.launch)

    @Slot()
    def diagnostics(self):
        self._run(self.core.diagnostics)

    @Slot()
    def checkAPI(self):
        self._run(self.core.check_api)

    @Slot(str, str)
    def setOption(self, key, value):
        if key in self.core.vars:
            self.core.vars[key].set(value)
            self.core.save()

    @Slot(str, result=str)
    def getOption(self, key):
        if key in self.core.vars:
            return self.core.vars[key].get()
        return ""

    @Slot()
    def save(self):
        self.core.save()
        self.logReceived.emit("Settings saved.")


def main():
    if os.name == "nt" and not admin():
        if elevate_without_console():
            return 0

        print(
            "Administrator elevation was declined.",
            file=sys.stderr,
        )
        return 1

    app = QGuiApplication(sys.argv)
    app.setApplicationName("GPUCluster")

    bridge = Bridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)

    qml_file = Path(__file__).resolve().parent / "Main.qml"

    if not qml_file.is_file():
        print(f"Missing QML file: {qml_file}", file=sys.stderr)
        return 1

    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
