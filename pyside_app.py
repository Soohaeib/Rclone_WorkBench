"""Modern PySide6 Workbench dashboard for :class:`engine.RcloneEngine`."""

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
    QSplitter,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from engine import RcloneEngine
from src import config_manager, rules_engine, workbench_blueprint


DASHBOARD_QSS = """
QMainWindow, QWidget {
    background: #181825;
    color: #cdd6f4;
    font-size: 13px;
}
QFrame#card {
    background: #252538;
    border: 1px solid #313244;
    border-radius: 8px;
}
QLabel#eyebrow {
    color: #a6adc8;
    font-size: 11px;
    font-weight: 600;
}
QLabel#cardTitle {
    color: #f5e0e0;
    font-size: 15px;
    font-weight: 700;
}
QLabel#statusPill {
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 700;
}
QComboBox, QLineEdit {
    background: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 7px 8px;
    color: #cdd6f4;
}
QComboBox:focus, QLineEdit:focus {
    border-color: #89b4fa;
}
QPushButton {
    border: 0;
    border-radius: 6px;
    padding: 9px 12px;
    font-weight: 700;
}
QPushButton#syncButton {
    background: #3b82f6;
    color: white;
    font-size: 15px;
    padding: 12px;
}
QPushButton#syncButton:hover { background: #60a5fa; }
QPushButton#syncButton:disabled { background: #45475a; color: #7f849c; }
QPushButton#stopButton { background: #ef4444; color: white; }
QPushButton#stopButton:hover { background: #f87171; }
QPushButton#stopButton:disabled { background: #45475a; color: #7f849c; }
QPushButton#utilityButton {
    background: #313244;
    color: #cdd6f4;
    padding: 6px 10px;
}
QPlainTextEdit#telemetry {
    background: #11111b;
    border: 1px solid #313244;
    border-radius: 8px;
    color: #a6e3a1;
    selection-background-color: #45475a;
    padding: 8px;
}
QScrollArea { border: 0; background: transparent; }
QScrollArea QWidget { background: transparent; }
QCheckBox { spacing: 8px; padding: 4px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #585b70; background: #1e1e2e;
}
QCheckBox::indicator:checked { background: #3b82f6; border-color: #89b4fa; }
QLabel#statValue {
    color: #89b4fa;
    font-size: 14px;
    font-weight: 700;
}
QSplitter::handle { background: #313244; width: 6px; }
QStatusBar { background: #1e1e2e; color: #a6adc8; }
"""


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


def card(title, content_layout):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 14)
    layout.setSpacing(9)
    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    layout.addWidget(heading)
    layout.addLayout(content_layout)
    return frame


class MainWindow(QMainWindow):
    STATE_BADGES = {
        "starting": ("🔵", "Running", "#2563eb"),
        "running": ("🔵", "Running", "#2563eb"),
        "stopping": ("🟡", "Stopping", "#d97706"),
        "cancelled": ("🟡", "Cancelled", "#d97706"),
        "completed": ("🟢", "Completed", "#16a34a"),
        "idle": ("🟢", "Idle", "#16a34a"),
        "failed": ("🔴", "Error", "#dc2626"),
        "blocked": ("🔴", "Blocked", "#dc2626"),
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rclone Workbench Dashboard")
        self.resize(960, 620)
        self.setMinimumSize(820, 520)
        self._engines = {}
        self._current_state = "idle"
        self._switching_profile = False
        self._automation_checks = {}

        self.events = EngineEvents()
        self.events.log_line.connect(self._append_engine_log)
        self.events.state_changed.connect(self._update_engine_state)

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self._configured_profiles())
        self.profile_combo.currentTextChanged.connect(self._switch_profile)
        self.local_path_edit = DropPathEdit()
        self.local_path_edit.path_dropped.connect(self._save_local_path)
        self.remote_path_label = QLabel()
        self.remote_path_label.setWordWrap(True)

        self.start_button = QPushButton("SYNC NOW")
        self.start_button.setObjectName("syncButton")
        self.start_button.clicked.connect(self._start_sync)
        self.stop_button = QPushButton("Stop / Abort")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self._stop_engine)
        self.status_pill = QLabel()
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignCenter)

        self.cpu_value = QLabel("—")
        self.transfers_value = QLabel("—")
        self.memory_value = QLabel("—")
        for label in (self.cpu_value, self.transfers_value, self.memory_value):
            label.setObjectName("statValue")

        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setObjectName("telemetry")
        self.log_view.setMaximumBlockCount(10000)
        self.log_view.setFont(QFont("JetBrains Mono", 10))
        self.clear_logs_button = QPushButton("Clear")
        self.clear_logs_button.setObjectName("utilityButton")
        self.clear_logs_button.clicked.connect(self.log_view.clear)
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)

        left_panel = self._build_control_deck()
        right_panel = self._build_telemetry_panel()
        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 600])
        self.setCentralWidget(splitter)

        self.tray = self._create_tray()
        if self.profile_combo.count():
            self._switch_profile(self.profile_combo.currentText())
        else:
            self._set_controls_for_state("idle")

    def _build_control_deck(self):
        panel = QWidget()
        panel.setFixedWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 6, 12)
        layout.setSpacing(12)

        target_form = QFormLayout()
        target_form.setVerticalSpacing(8)
        target_form.addRow("Profile", self.profile_combo)
        target_form.addRow("Local directory", self.local_path_edit)
        target_form.addRow("Remote path", self.remote_path_label)
        layout.addWidget(card("Profile & Target Deck", target_form))

        mission = QVBoxLayout()
        mission.addWidget(self.status_pill)
        mission.addWidget(self.start_button)
        mission.addWidget(self.stop_button)
        layout.addWidget(card("Mission Control", mission))

        hardware = QFormLayout()
        hardware.setVerticalSpacing(8)
        hardware.addRow("CPU checker clamp", self.cpu_value)
        hardware.addRow("Transfer limit", self.transfers_value)
        hardware.addRow("Memory headroom", self.memory_value)
        layout.addWidget(card("Hardware & Environment Monitor", hardware))
        layout.addWidget(self._build_automation_card())
        quick_actions = QHBoxLayout()
        trash_button = QPushButton("Open Trash / Backups")
        trash_button.setObjectName("utilityButton")
        trash_button.clicked.connect(self._open_trash)
        log_button = QPushButton("View Session Log")
        log_button.setObjectName("utilityButton")
        log_button.clicked.connect(self._open_session_log)
        quick_actions.addWidget(trash_button)
        quick_actions.addWidget(log_button)
        layout.addWidget(card("Quick Actions", quick_actions))
        layout.addStretch(1)
        return panel

    def _build_automation_card(self):
        automation_layout = QVBoxLayout()
        automation_layout.setSpacing(2)
        automations = workbench_blueprint.SMART_SCHEMA.get("Smart Automations", [])
        if not automations:
            automation_layout.addWidget(QLabel("No smart automations configured."))
        else:
            for item in automations:
                toggle = QCheckBox(item.label)
                toggle.setToolTip(item.desc or item.label)
                toggle.toggled.connect(
                    lambda checked, item_id=item.id: self._automation_toggled(item_id, checked)
                )
                self._automation_checks[item.id] = toggle
                automation_layout.addWidget(toggle)

        content = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(190)
        body = QWidget()
        body.setLayout(automation_layout)
        scroll.setWidget(body)
        content.addWidget(scroll)
        return card("Automations & Flags", content)

    def _build_telemetry_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 12, 12, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("LIVE TELEMETRY")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.auto_scroll)
        header.addWidget(self.clear_logs_button)
        layout.addLayout(header)
        layout.addWidget(self.log_view, 1)
        return panel

    @staticmethod
    def _configured_profiles():
        cfg = config_manager.load_config()
        return sorted(set(cfg.get("local_paths", {})) | set(cfg.get("remote_configs", {})))

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
            self.remote_path_label.setText(str(profile_cfg.get("remote_path", "")) or "(default remote root)")
            if profile not in self._engines:
                self._engines[profile] = RcloneEngine(
                    profile, local_path,
                    state_callback=self._engine_state_callback,
                    log_callback=self._engine_log_callback,
                ).start()
            engine = self._engines[profile]
            self._current_state = self._engine_state(engine)
            self.log_view.clear()
            self._update_hardware_monitor(engine)
            self._refresh_automation_controls(profile_cfg)
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

    def _automation_toggled(self, item_id, checked):
        if self._switching_profile:
            return
        profile = self.profile_combo.currentText()
        if not profile:
            return
        cfg = config_manager.load_config(force_reload=True)
        profile_cfg = cfg.setdefault("remote_configs", {}).setdefault(profile, {})
        profile_cfg[item_id] = checked
        active_keys = [
            key for key, value in profile_cfg.items()
            if value is True or (isinstance(value, str) and value.strip())
            or (isinstance(value, (int, float)) and value != 0)
        ]
        final_keys, final_values, _, _ = rules_engine.evaluate_state(
            active_keys, profile_cfg, rules_engine.get_item_lookup()
        )
        for key, value in final_values.items():
            if key.startswith("_"):
                continue
            profile_cfg[key] = value
        for item in workbench_blueprint.SMART_SCHEMA.get("Smart Automations", []):
            profile_cfg[item.id] = item.id in final_keys
        config_manager.save_config(cfg)
        self._refresh_automation_controls(profile_cfg)

    def _refresh_automation_controls(self, profile_cfg):
        for item_id, toggle in self._automation_checks.items():
            toggle.blockSignals(True)
            toggle.setChecked(bool(profile_cfg.get(item_id, False)))
            toggle.blockSignals(False)

    def _open_trash(self):
        profile = self.profile_combo.currentText()
        if not profile:
            return
        cfg, profile_cfg = self._profile_config(profile)
        local_path = cfg.get("local_paths", {}).get(profile, "")
        backup = profile_cfg.get("--backup-dir1")
        if not backup:
            return
        path = backup if os.path.isabs(str(backup)) else os.path.join(local_path, str(backup))
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_session_log(self):
        profile = self.profile_combo.currentText()
        if not profile:
            return
        path = os.path.join(workbench_blueprint.LOG_DIR, f"{profile}_sync.jsonl")
        if os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

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

    def _update_hardware_monitor(self, engine):
        bounds = engine.hardware_bounds()
        self.cpu_value.setText(str(bounds.get("--checkers", "—")))
        self.transfers_value.setText(str(bounds.get("--transfers", "—")))
        self.memory_value.setText(
            f"{bounds.get('mem_gb', 0):.2f} GB"
            if isinstance(bounds.get("mem_gb"), (int, float)) else "—"
        )

    def _create_tray(self):
        tray = QSystemTrayIcon(QIcon.fromTheme("network-server"), self)
        tray_menu = QMenu(self)
        show_action = QAction("Show Dashboard", self)
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
        self._update_hardware_monitor(engine)
        self._update_tray(state)

    def _set_controls_for_state(self, state):
        running = state in {"starting", "running", "stopping"}
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(state in {"starting", "running"})
        emoji, text, color = self.STATE_BADGES.get(state, self.STATE_BADGES["idle"])
        self.status_pill.setText(f"{emoji}  {text}")
        self.status_pill.setStyleSheet(
            f"QLabel#statusPill {{ background: {color}; color: white; }}"
        )
        self.statusBar().showMessage(f"{emoji} {text}")

    def _update_tray(self, state):
        profile = self.profile_combo.currentText() or "No profile"
        emoji, text, _ = self.STATE_BADGES.get(state, self.STATE_BADGES["idle"])
        self.tray.setToolTip(f"{emoji} {profile}: {text}")

    def closeEvent(self, event: QCloseEvent):
        for engine in self._engines.values():
            engine.stop(force=True)
        self.tray.hide()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DASHBOARD_QSS)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
