"""Workbench page and controls for the Qt front end."""

import os

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QScrollArea, QToolButton, QVBoxLayout, QWidget

from src import config_manager, rules_engine, workbench_blueprint


class DropPathEdit(QLineEdit):
    path_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drop a local directory here")

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("text/uri-list"):
            event.acceptProposedAction()
        else:
            event.ignore()

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


class WorkbenchPage(QWidget):
    profile_changed = Signal(str)
    path_changed = Signal(str)
    sync_requested = Signal()
    stop_requested = Signal()
    trash_requested = Signal()
    apply_requested = Signal()
    environment_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._automation_checks = {}
        self._switching_profile = False
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self._profiles())
        self.profile_combo.currentTextChanged.connect(self.profile_changed)
        self.path_entry = DropPathEdit()
        self.path_entry.path_dropped.connect(self.path_changed)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(16)
        controls = QHBoxLayout()
        controls.setSpacing(12)
        toggle_smart = QToolButton(text="☰  Smart Automations", checkable=True, checked=True)
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
        preview = QPlainTextEdit(readOnly=True)
        preview.setFont(QFont("monospace", 10))
        preview.setMinimumHeight(100)
        preview_toggle.toggled.connect(preview.setVisible)
        layout.addWidget(preview_toggle)
        layout.addWidget(preview)
        self.preview_view = preview

        footer = QHBoxLayout()
        footer.setSpacing(12)
        undo = QToolButton(text="Undo")
        undo.clicked.connect(lambda: self.profile_changed.emit(self.profile_combo.currentText()))
        reset = QToolButton(text="Reset")
        reset.clicked.connect(self.reset_requested)
        apply_button = QPushButton("Apply")
        apply_button.setObjectName("btn_apply")
        apply_button.clicked.connect(self.apply_requested)
        footer.addWidget(undo)
        footer.addWidget(reset)
        footer.addWidget(self.status_label, 1)
        footer.addWidget(apply_button)
        layout.addLayout(footer)

    @staticmethod
    def _profiles():
        cfg = config_manager.load_config()
        return sorted(set(cfg.get("local_paths", {})) | set(cfg.get("remote_configs", {})))

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
        self.refresh_automations(values)

    def refresh_automations(self, values):
        for item_id, toggle in self._automation_checks.items():
            toggle.blockSignals(True)
            toggle.setChecked(bool(values.get(item_id, False)))
            toggle.blockSignals(False)

    def set_profile(self, profile, path, values):
        self._switching_profile = True
        self.path_entry.setText(path)
        self.refresh_automations(values)
        self._switching_profile = False

    def reset_requested(self):
        cfg = config_manager.load_config(force_reload=True)
        self.refresh_automations(cfg.get("remote_configs", {}).get(self.profile_combo.currentText(), {}))

    def _browse_path(self):
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Select Local Directory", self.path_entry.text())
        if path:
            self.path_entry.setText(path)
            self.path_changed.emit(path)

    def set_status(self, text):
        self.status_label.setText(text)
