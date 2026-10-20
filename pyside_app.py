"""Minimal PySide6 front end for :class:`engine.RcloneEngine`."""

import os
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from engine import RcloneEngine
from src import config_manager


class EngineEvents(QObject):
    """Delivers worker callbacks through Qt's queued signal mechanism."""

    log_line = Signal(object, str)
    state_changed = Signal(object, str)


class DropPathEdit(QLineEdit):
    path_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drop a local directory here")

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("text/uri-list"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = os.path.realpath(os.path.abspath(url.toLocalFile()))
            if os.path.isdir(path):
                self.setText(path)
                self.path_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()


class MainWindow(QMainWindow):
    STATE_BADGES = {
        "starting": "🔵",
        "running": "🔵",
        "stopping": "🟡",
        "cancelled": "🟡",
        "completed": "🟢",
        "idle": "🟢",
        "failed": "🔴",
        "blocked": "🔴",
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rclone Workbench")
        self.resize(760, 480)
        self._engines = {}
        self._current_state = "idle"
        self._switching_profile = False

        self.events = EngineEvents()
        self.events.log_line.connect(self._append_engine_log)
        self.events.state_changed.connect(self._update_engine_state)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self._configured_profiles())
        self.profile_combo.currentTextChanged.connect(self._switch_profile)
        self.local_path_edit = DropPathEdit()
        self.local_path_edit.path_dropped.connect(self._save_local_path)
        self.remote_path_label = QLabel()

        self.start_button = QPushButton("Sync now")
        self.start_button.clicked.connect(self._start_sync)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_engine)

        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(10000)
        self.clear_logs_button = QPushButton("Clear Logs")
        self.clear_logs_button.clicked.connect(self.log_view.clear)
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)

        form = QFormLayout()
        form.addRow("Profile", self.profile_combo)
        form.addRow("Local path", self.local_path_edit)
        form.addRow("Remote path", self.remote_path_label)

        log_controls = QVBoxLayout()
        log_controls.addWidget(self.clear_logs_button)
        log_controls.addWidget(self.auto_scroll)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addLayout(log_controls)
        layout.addWidget(self.log_view, 1)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.tray = self._create_tray()
        if self.profile_combo.count():
            self._switch_profile(self.profile_combo.currentText())
        else:
            self._set_controls_for_state("idle")

    @staticmethod
    def _configured_profiles():
        cfg = config_manager.load_config()
        profiles = set(cfg.get("local_paths", {}))
        profiles.update(cfg.get("remote_configs", {}))
        return sorted(profiles)

    def _profile_config(self, profile):
        cfg = config_manager.load_config()
        return cfg, cfg.get("remote_configs", {}).get(profile, {})

    def _switch_profile(self, profile):
        if not profile or self._switching_profile:
            return
        self._switching_profile = True
        try:
            cfg, profile_cfg = self._profile_config(profile)
            local_path = cfg.get("local_paths", {}).get(profile, os.getcwd())
            self.local_path_edit.setText(local_path)
            self.remote_path_label.setText(str(profile_cfg.get("remote_path", "")))
            if profile not in self._engines:
                self._engines[profile] = RcloneEngine(
                    profile,
                    local_path,
                    state_callback=self._engine_state_callback,
                    log_callback=self._engine_log_callback,
                ).start()
            self._current_state = self._engine_state(self._engines[profile])
            self.log_view.clear()
            self._set_controls_for_state(self._current_state)
            self._update_tray(self._current_state)
        finally:
            self._switching_profile = False

    def _engine_state(self, engine):
        if engine.run_state:
            return "running"
        if engine.err:
            return "blocked" if engine.last == "Blocked" else "failed"
        if engine.cancelled:
            return "cancelled"
        return "idle"

    def _current_engine(self):
        return self._engines.get(self.profile_combo.currentText())

    def _save_local_path(self, path):
        profile = self.profile_combo.currentText()
        if not profile:
            return
        cfg = config_manager.load_config(force_reload=True)
        cfg.setdefault("local_paths", {})[profile] = path
        config_manager.save_config(cfg)
        engine = self._current_engine()
        if engine and not engine.run_state:
            engine.local_path = path

    def _start_sync(self):
        engine = self._current_engine()
        if engine:
            engine.trigger_sync()

    def _stop_engine(self):
        engine = self._current_engine()
        if engine and engine.run_state:
            self._update_engine_state(engine, "stopping")
            engine.stop_process(force=bool(engine.kill_clicks))
            engine.kill_clicks += 1

    def _create_tray(self):
        tray = QSystemTrayIcon(QIcon.fromTheme("network-server"), self)
        tray_menu = QMenu(self)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.showNormal)
        sync_action = QAction("Sync now", self)
        sync_action.triggered.connect(self._start_sync)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(show_action)
        tray_menu.addAction(sync_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        tray.setContextMenu(tray_menu)
        tray.activated.connect(
            lambda reason: self.showNormal()
            if reason == QSystemTrayIcon.Trigger else None
        )
        tray.show()
        return tray

    def _engine_state_callback(self, engine, state):
        self.events.state_changed.emit(engine, state)

    def _engine_log_callback(self, engine, line):
        self.events.log_line.emit(engine, line.rstrip("\n"))

    def _append_engine_log(self, engine, line):
        if engine is not self._current_engine():
            return
        scrollbar = self.log_view.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        self.log_view.appendPlainText(line)
        if self.auto_scroll.isChecked() and at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _update_engine_state(self, engine, state):
        if engine is not self._current_engine():
            return
        self._current_state = state
        self._set_controls_for_state(state)
        self._update_tray(state)

    def _set_controls_for_state(self, state):
        running = state in {"starting", "running", "stopping"}
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(state in {"starting", "running"})
        badge = self.STATE_BADGES.get(state, "🟢")
        self.statusBar().showMessage(f"{badge} {state.capitalize()}")

    def _update_tray(self, state):
        profile = self.profile_combo.currentText() or "No profile"
        badge = self.STATE_BADGES.get(state, "🟢")
        self.tray.setToolTip(f"{badge} {profile}: {state.capitalize()}")

    def closeEvent(self, event: QCloseEvent):
        for engine in self._engines.values():
            engine.stop(force=True)
        self.tray.hide()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
