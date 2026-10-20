"""PySide6 entry point for the Rclone Workbench."""

import os
import sys

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QMainWindow, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from engine import RcloneEngine
from src import config_manager
from src.qt_live_output import LiveOutputPage
from src.qt_tray import TrayController
from src.qt_workbench_ui import WorkbenchPage


def load_stylesheet():
    stylesheet_path = os.path.join(os.path.dirname(__file__), "src", "style.qss")
    with open(stylesheet_path, encoding="utf-8") as stylesheet:
        return stylesheet.read()


class EngineEvents(QObject):
    log_line = Signal(object, str)
    state_changed = Signal(object, str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RClone Workbench")
        self.resize(1200, 800)
        self._engines = {}

        self.events = EngineEvents()
        self.events.log_line.connect(self._append_log)
        self.events.state_changed.connect(self._state_changed)

        self.workbench = WorkbenchPage()
        self.workbench.profile_changed.connect(self._switch_profile)
        self.workbench.path_changed.connect(self._save_path)
        self.workbench.apply_requested.connect(self._save_profile)
        self.workbench.sync_requested.connect(self._start_sync)
        self.workbench.stop_requested.connect(self._stop_sync)
        self.workbench.trash_requested.connect(self._open_trash)
        self.workbench.environment_requested.connect(self._show_environment_info)

        self.live_output = LiveOutputPage()
        self.main_stack = QStackedWidget()
        self.main_stack.addWidget(self.workbench)
        self.main_stack.addWidget(self.live_output)
        self._stack_buttons = []

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self.main_stack, 1)
        shell = QWidget()
        shell.setLayout(root)
        self.setCentralWidget(shell)

        self.tray = TrayController(
            self,
            self._engines,
            lambda: self.workbench.profile_combo.currentText(),
            self._open_workbench,
            self._show_live_output,
            self._stop_engine,
        )
        if self.workbench.profile_combo.count():
            self._switch_profile(self.workbench.profile_combo.currentText())

    def _build_header(self):
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 6)
        layout.setSpacing(0)
        layout.addLayout(self._build_left_bar(), 1)
        layout.addLayout(self._build_switcher(), 1)
        layout.addLayout(self._build_command_bar(), 1)
        return header

    def _build_left_bar(self):
        layout = QHBoxLayout()
        layout.setSpacing(6)
        info = QToolButton(text="ⓘ")
        info.setToolTip("Operating Environment Info")
        info.clicked.connect(self._show_environment_info)
        update = QToolButton(text="Update")
        update.setToolTip("Update Rclone System-Wide")
        gui = QToolButton(text="Web GUI")
        gui.setToolTip("Launch official Rclone Web Configurator")
        layout.addWidget(info)
        layout.addWidget(update)
        layout.addWidget(gui)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return layout

    def _build_switcher(self):
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        for label, index in (("Workbench", 0), ("Live Outputs", 1)):
            button = QToolButton(text=label, checkable=True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _=False, target=index: self._select_page(target))
            layout.addWidget(button)
            self._stack_buttons.append(button)
        return layout

    def _select_page(self, index):
        self.main_stack.setCurrentIndex(index)
        for position, button in enumerate(self._stack_buttons):
            button.setChecked(position == index)

    def _build_command_bar(self):
        layout = QHBoxLayout()
        layout.setSpacing(6)
        self.btn_sync = QPushButton("▶")
        self.btn_sync.setObjectName("btn_sync")
        self.btn_sync.setToolTip("Start Active Profile Sync Session")
        self.btn_sync.clicked.connect(self._start_sync)
        self.btn_stop = QPushButton("■")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setToolTip("Stop Active Sync Session")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_sync)
        self.btn_trash = QToolButton(text="♻")
        self.btn_trash.setObjectName("btn_trash")
        self.btn_trash.setEnabled(False)
        self.btn_trash.clicked.connect(self._open_trash)
        layout.addWidget(self.btn_sync)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_trash)
        layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return layout

    def _switch_profile(self, profile):
        if not profile:
            return
        cfg = config_manager.load_config()
        path = cfg.get("local_paths", {}).get(profile, os.getcwd())
        self.workbench.set_profile(profile, path, cfg.get("remote_configs", {}).get(profile, {}))
        if profile not in self._engines:
            self._engines[profile] = RcloneEngine(
                profile, path, self._engine_state_callback, self._engine_log_callback
            ).start()
        self.live_output.set_profile(profile)
        self._update_controls(self._engine_state(self._engines[profile]))
        self.tray.refresh()

    def _current_engine(self):
        return self._engines.get(self.workbench.profile_combo.currentText())

    @staticmethod
    def _engine_state(engine):
        if engine.run_state:
            return "running"
        if engine.err:
            return "blocked" if engine.last == "Blocked" else "failed"
        if engine.cancelled:
            return "cancelled"
        return "idle"

    def _engine_state_callback(self, engine, state):
        self.events.state_changed.emit(engine, state)

    def _engine_log_callback(self, engine, line):
        self.events.log_line.emit(engine, line.rstrip("\n"))

    def _state_changed(self, engine, state):
        if engine is self._current_engine():
            self._update_controls(state)

    def _append_log(self, engine, line):
        self.live_output.append_log(engine, self._current_engine(), line)

    def _update_controls(self, state):
        running = state in {"starting", "running"}
        self.btn_sync.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.workbench.set_status(state.capitalize())
        self.tray.refresh()

    def _save_path(self, path):
        profile = self.workbench.profile_combo.currentText()
        cfg = config_manager.load_config(force_reload=True)
        cfg.setdefault("local_paths", {})[profile] = path
        config_manager.save_config(cfg)
        if engine := self._current_engine():
            engine.local_path = path

    def _save_profile(self):
        self._save_path(self.workbench.path_entry.text())

    def _start_sync(self):
        if engine := self._current_engine():
            engine.trigger_sync()

    def _stop_sync(self):
        self._stop_engine(self._current_engine())

    def _stop_engine(self, engine):
        if engine and engine.run_state:
            engine.stop_process(force=bool(engine.kill_clicks))
            engine.kill_clicks += 1
            self.tray.refresh()

    def _open_trash(self):
        cfg = config_manager.load_config()
        profile = self.workbench.profile_combo.currentText()
        values = cfg.get("remote_configs", {}).get(profile, {})
        backup = values.get("--backup-dir1")
        if not backup:
            return
        path = backup if os.path.isabs(str(backup)) else os.path.join(self.workbench.path_entry.text(), str(backup))
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _show_environment_info(self):
        if engine := self._current_engine():
            bounds = engine.hardware_bounds()
            self.statusBar().showMessage(
                f"Available RAM: {bounds.get('mem_gb', 0):.2f} GB | Cores: {os.cpu_count() or 2}",
                5000,
            )

    def _open_workbench(self):
        self._select_page(0)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _show_live_output(self, profile):
        index = self.workbench.profile_combo.findText(profile)
        if index >= 0:
            self.workbench.profile_combo.setCurrentIndex(index)
        self._select_page(1)

    def closeEvent(self, event: QCloseEvent):
        for engine in self._engines.values():
            engine.stop(force=True)
        self.tray.hide()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet())
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
