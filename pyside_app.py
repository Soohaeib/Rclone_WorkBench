"""PySide6 reconstruction of the GTK workbench defined in workbench.glade."""

import os
import sys

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from engine import RcloneEngine
from src import config_manager, rules_engine, workbench_blueprint


WORKBENCH_QSS = """
QMainWindow, QWidget {
    background: #181825;
    color: #cdd6f4;
}
QToolButton, QPushButton {
    border: 0;
    border-radius: 999px;
    padding: 4px 10px;
}
QToolButton:hover, QPushButton:hover { background: #313244; }
QPushButton#btn_sync { background: #2ecc71; color: #ffffff; }
QPushButton#btn_sync:hover { background: #27ae60; }
QPushButton#btn_stop { background: #c0392b; color: #ffffff; }
QPushButton#btn_stop:hover { background: #e74c3c; }
QPushButton#btn_apply { background: #3584e4; color: #ffffff; }
QComboBox, QLineEdit {
    background: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px;
    color: #cdd6f4;
}
QScrollArea { border: 0; background: transparent; }
QPlainTextEdit {
    background: #11111b;
    border: 1px solid #313244;
    padding: 8px;
    color: #cdd6f4;
}
QCheckBox { padding: 4px 2px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 8px;
    border: 1px solid #6c7086; background: #1e1e2e;
}
QCheckBox::indicator:checked { background: #3584e4; border-color: #89b4fa; }
QTabBar::tab { padding: 7px 14px; }
QTabBar::tab:selected { color: #89b4fa; }
.chip { border-radius: 999px; padding: 4px 10px; margin: 2px; }
.canvas-card { margin-bottom: 6px; padding: 10px; border-bottom: 1px solid #45475a; }
.log-header-btn { padding: 2px 6px; min-height: 24px; min-width: 28px; margin: 0; }
"""


class EngineEvents(QObject):
    log_line = Signal(object, str)
    state_changed = Signal(object, str)


class DropPathEdit(QLineEdit):
    path_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drop a local directory here")

    def dragEnterEvent(self, event):
        event.acceptProposedAction() if event.mimeData().hasFormat("text/uri-list") else event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = os.path.realpath(os.path.abspath(url.toLocalFile()))
                if os.path.isdir(path):
                    self.setText(path)
                    self.path_dropped.emit(path)
                    event.acceptProposedAction()
                    return
        event.ignore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RClone Workbench")
        self.resize(1200, 800)
        self._engines = {}
        self._automation_checks = {}
        self._switching_profile = False

        self.events = EngineEvents()
        self.events.log_line.connect(self._append_log)
        self.events.state_changed.connect(self._state_changed)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self._profiles())
        self.profile_combo.currentTextChanged.connect(self._switch_profile)
        self.path_entry = DropPathEdit()
        self.path_entry.path_dropped.connect(self._save_path)
        self.status_label = QLabel()

        self.btn_info = QToolButton(text="ⓘ")
        self.btn_info.setToolTip("Operating Environment Info")
        self.btn_info.clicked.connect(self._show_environment_info)
        self.btn_rclone_update = QToolButton(text="Update")
        self.btn_rclone_update.setToolTip("Update Rclone System-Wide")
        self.btn_rclone_gui = QToolButton(text="Web GUI")
        self.btn_rclone_gui.setToolTip("Launch official Rclone Web Configurator")

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
        self.btn_trash.setToolTip("Local Trash (Unavailable)")
        self.btn_trash.setEnabled(False)
        self.btn_trash.clicked.connect(self._open_trash)

        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(10000)
        self.log_view.setFont(QFont("monospace", 10))
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)

        self.main_stack = QStackedWidget()
        self.stack_switcher = QHBoxLayout()
        self._add_stack_button("Workbench", 0)
        self._add_stack_button("Live Outputs", 1)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self.main_stack, 1)
        shell = QWidget()
        shell.setLayout(root)
        self.setCentralWidget(shell)

        self.main_stack.addWidget(self._build_workbench_page())
        self.main_stack.addWidget(self._build_live_page())
        self.tray = self._build_tray()
        if self.profile_combo.count():
            self._switch_profile(self.profile_combo.currentText())

    def _build_header(self):
        header = QFrame()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 6)
        layout.setSpacing(0)
        for column in (self._build_left_bar(), self._build_switcher(), self._build_command_bar()):
            layout.addLayout(column, 1)
        return header

    def _build_left_bar(self):
        layout = QHBoxLayout()
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.btn_info)
        layout.addWidget(self.btn_rclone_update)
        layout.addWidget(self.btn_rclone_gui)
        return layout

    def _build_switcher(self):
        holder = QHBoxLayout()
        holder.setAlignment(Qt.AlignCenter)
        for button in self._stack_buttons:
            holder.addWidget(button)
        return holder

    def _add_stack_button(self, label, index):
        if not hasattr(self, "_stack_buttons"):
            self._stack_buttons = []
        button = QToolButton(text=label, checkable=True)
        button.clicked.connect(lambda: self.main_stack.setCurrentIndex(index))
        self._stack_buttons.append(button)
        if index == 0:
            button.setChecked(True)

    def _build_command_bar(self):
        layout = QHBoxLayout()
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.btn_sync)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_trash)
        return layout

    def _build_workbench_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(16)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        toggle_smart = QToolButton(text="☰  Smart Automations", checkable=True, checked=True)
        toggle_smart.setToolTip("Toggle Smart Presets")
        smart_scroll = self._build_automations()
        toggle_smart.toggled.connect(smart_scroll.setVisible)
        controls.addWidget(toggle_smart)
        controls.addWidget(self.profile_combo, 1)
        controls.addWidget(self.path_entry, 2)
        browse = QToolButton(text="Browse")
        browse.clicked.connect(self._browse_path)
        controls.addWidget(browse)
        layout.addLayout(controls)
        layout.addWidget(smart_scroll)

        preview_toggle = QToolButton(text="☰  Live Command Preview", checkable=True, checked=True)
        preview_toggle.setToolTip("Toggle Live Preview")
        preview = QPlainTextEdit(readOnly=True)
        preview.setFont(QFont("monospace", 10))
        preview.setMinimumHeight(100)
        preview.setPlainText("")
        preview_toggle.toggled.connect(preview.setVisible)
        layout.addWidget(preview_toggle)
        layout.addWidget(preview)
        self.preview_view = preview

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.btn_undo = QToolButton(text="Undo")
        self.btn_undo.setToolTip("Undo Unsaved Changes")
        self.btn_undo.clicked.connect(lambda: self._switch_profile(self.profile_combo.currentText()))
        self.btn_reset = QToolButton(text="Reset")
        self.btn_reset.setToolTip("Reset Options")
        self.btn_reset.clicked.connect(self._reset_automations)
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setObjectName("btn_apply")
        self.btn_apply.setToolTip("Apply to Profile")
        self.btn_apply.clicked.connect(self._save_profile)
        footer.addWidget(self.btn_undo)
        footer.addWidget(self.btn_reset)
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.btn_apply)
        layout.addLayout(footer)
        return page

    def _build_automations(self):
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(2)
        for item in workbench_blueprint.SMART_SCHEMA.get("Smart Automations", []):
            toggle = QCheckBox(item.label)
            toggle.setToolTip(item.desc or item.label)
            toggle.toggled.connect(lambda checked, item_id=item.id: self._automation_toggled(item_id, checked))
            self._automation_checks[item.id] = toggle
            body_layout.addWidget(toggle)
        body_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setWidget(body)
        return scroll

    def _build_live_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        title = QLabel("Live Output")
        toolbar.addWidget(title)
        toolbar.addStretch()
        toolbar.addWidget(self.auto_scroll)
        clear = QToolButton(text="Clear")
        clear.setObjectName("log-header-btn")
        clear.clicked.connect(self.log_view.clear)
        toolbar.addWidget(clear)
        reload_button = QToolButton(text="Reload")
        reload_button.setObjectName("log-header-btn")
        reload_button.clicked.connect(self._reload_log)
        toolbar.addWidget(reload_button)
        delete_button = QToolButton(text="Delete")
        delete_button.setObjectName("log-header-btn")
        delete_button.clicked.connect(self._delete_log)
        toolbar.addWidget(delete_button)
        open_button = QToolButton(text="Open Dir")
        open_button.setObjectName("log-header-btn")
        open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(workbench_blueprint.LOG_DIR)))
        toolbar.addWidget(open_button)
        layout.addLayout(toolbar)
        layout.addWidget(self.log_view, 1)
        return page

    def _profiles(self):
        cfg = config_manager.load_config()
        return sorted(set(cfg.get("local_paths", {})) | set(cfg.get("remote_configs", {})))

    def _switch_profile(self, profile):
        if not profile or self._switching_profile:
            return
        self._switching_profile = True
        try:
            cfg = config_manager.load_config()
            path = cfg.get("local_paths", {}).get(profile, os.getcwd())
            self.path_entry.setText(path)
            if profile not in self._engines:
                self._engines[profile] = RcloneEngine(
                    profile, path, self._engine_state_callback, self._engine_log_callback
                ).start()
            self._refresh_automations(cfg.get("remote_configs", {}).get(profile, {}))
            self._update_controls(self._engine_state(self._engines[profile]))
            self._reload_log()
        finally:
            self._switching_profile = False

    def _current_engine(self):
        return self._engines.get(self.profile_combo.currentText())

    def _engine_state(self, engine):
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

    def _update_controls(self, state):
        running = state in {"starting", "running"}
        self.btn_sync.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.status_label.setText(state.capitalize())
        self._update_tray(state)

    def _append_log(self, engine, line):
        if engine is not self._current_engine():
            return
        scrollbar = self.log_view.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        self.log_view.appendPlainText(line)
        if self.auto_scroll.isChecked() and at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _automation_toggled(self, item_id, checked):
        if self._switching_profile:
            return
        profile = self.profile_combo.currentText()
        cfg = config_manager.load_config(force_reload=True)
        values = cfg.setdefault("remote_configs", {}).setdefault(profile, {})
        values[item_id] = checked
        active = [key for key, value in values.items() if value is True or (isinstance(value, str) and value)]
        final_keys, final_values, _, _ = rules_engine.evaluate_state(active, values, rules_engine.get_item_lookup())
        values.update({key: value for key, value in final_values.items() if not key.startswith("_")})
        for item in workbench_blueprint.SMART_SCHEMA.get("Smart Automations", []):
            values[item.id] = item.id in final_keys
        config_manager.save_config(cfg)
        self._refresh_automations(values)

    def _refresh_automations(self, values):
        for item_id, toggle in self._automation_checks.items():
            toggle.blockSignals(True)
            toggle.setChecked(bool(values.get(item_id, False)))
            toggle.blockSignals(False)

    def _save_path(self, path):
        profile = self.profile_combo.currentText()
        cfg = config_manager.load_config(force_reload=True)
        cfg.setdefault("local_paths", {})[profile] = path
        config_manager.save_config(cfg)
        if engine := self._current_engine():
            engine.local_path = path

    def _save_profile(self):
        self._save_path(self.path_entry.text())

    def _reset_automations(self):
        cfg = config_manager.load_config(force_reload=True)
        values = cfg.get("remote_configs", {}).get(self.profile_combo.currentText(), {})
        self._refresh_automations(values)

    def _browse_path(self):
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Select Local Directory", self.path_entry.text())
        if path:
            self.path_entry.setText(path)
            self._save_path(path)

    def _start_sync(self):
        if engine := self._current_engine():
            engine.trigger_sync()

    def _stop_sync(self):
        if engine := self._current_engine():
            engine.stop_process(force=bool(engine.kill_clicks))
            engine.kill_clicks += 1

    def _profile_backup_path(self):
        cfg = config_manager.load_config()
        profile = self.profile_combo.currentText()
        values = cfg.get("remote_configs", {}).get(profile, {})
        backup = values.get("--backup-dir1")
        if not backup:
            return ""
        return backup if os.path.isabs(str(backup)) else os.path.join(self.path_entry.text(), str(backup))

    def _open_trash(self):
        path = self._profile_backup_path()
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _show_environment_info(self):
        if engine := self._current_engine():
            bounds = engine.hardware_bounds()
            self.statusBar().showMessage(
                f"Available RAM: {bounds.get('mem_gb', 0):.2f} GB | Cores: {os.cpu_count() or 2}",
                5000,
            )

    def _reload_log(self):
        self.log_view.clear()
        path = os.path.join(workbench_blueprint.LOG_DIR, f"{self.profile_combo.currentText()}_sync.jsonl")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as log_file:
                self.log_view.setPlainText(log_file.read())

    def _delete_log(self):
        path = os.path.join(workbench_blueprint.LOG_DIR, f"{self.profile_combo.currentText()}_sync.jsonl")
        if os.path.isfile(path):
            os.remove(path)
        self.log_view.setPlainText("[SYSTEM] Log deleted.")

    def _build_tray(self):
        tray = QSystemTrayIcon(QIcon.fromTheme("network-server"), self)
        menu = QMenu(self)
        show = QAction("Show Workbench", self)
        show.triggered.connect(self.showNormal)
        sync = QAction("Sync Now", self)
        sync.triggered.connect(self._start_sync)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(show)
        menu.addAction(sync)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.show()
        return tray

    def _update_tray(self, state):
        self.tray.setToolTip(f"{self.profile_combo.currentText()}: {state.capitalize()}")

    def closeEvent(self, event: QCloseEvent):
        for engine in self._engines.values():
            engine.stop(force=True)
        self.tray.hide()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(WORKBENCH_QSS)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
