"""Workbench page and controls for the Qt front end."""

import os

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QScrollArea, QToolButton, QVBoxLayout, QWidget

from shared import config_manager, rules_engine, workbench_blueprint


class DropPathEdit(QLineEdit):
    path_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drop a local directory here")
        self.setCursor(Qt.PointingHandCursor)

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


class AnimatedSection(QWidget):
    def __init__(self, content, parent=None):
        super().__init__(parent)
        self._content = content
        self._expanded_height = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)
        self.setMaximumHeight(0)
        self._animation = QPropertyAnimation(self, b"maximumHeight", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)

    def set_expanded(self, expanded):
        self._content.adjustSize()
        self._expanded_height = max(self._content.sizeHint().height(), 1)
        self._animation.stop()
        self._animation.setStartValue(self.maximumHeight())
        self._animation.setEndValue(self._expanded_height if expanded else 0)
        self._animation.start()


class WorkbenchPage(QWidget):
    profile_changed = Signal(str)
    path_changed = Signal(str)
    sync_requested = Signal()
    stop_requested = Signal()
    trash_requested = Signal()
    apply_requested = Signal()
    environment_requested = Signal()
    preview_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._automation_checks = {}
        self._disabled_automations = set()
        self._switching_profile = False
        self.profile_combo = QComboBox()
        self.profile_combo.setCursor(Qt.PointingHandCursor)
        self.profile_combo.addItems(self._profiles())
        self.profile_combo.currentTextChanged.connect(self.profile_changed)
        self.path_entry = DropPathEdit()
        self.path_entry.path_dropped.connect(self.path_changed)
        self.path_entry.textChanged.connect(lambda: self.update_preview())
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(16)
        controls = QHBoxLayout()
        controls.setSpacing(12)
        toggle_smart = QToolButton(
            icon=QIcon.fromTheme("sidebar-show-symbolic"),
            checkable=True,
            checked=True,
        )
        toggle_smart.setCursor(Qt.PointingHandCursor)
        toggle_smart.setToolTip("Toggle Smart Presets")
        smart_scroll = self._build_automations()
        smart_section = AnimatedSection(smart_scroll)
        toggle_smart.toggled.connect(smart_section.set_expanded)
        controls.addWidget(toggle_smart)
        controls.addWidget(self.profile_combo, 1)
        controls.addWidget(self.path_entry, 2)
        browse = QToolButton()
        browse.setIcon(QIcon.fromTheme("folder-open-symbolic"))
        browse.setCursor(Qt.PointingHandCursor)
        browse.setToolTip("Browse Local Path")
        browse.clicked.connect(self._browse_path)
        controls.addWidget(browse)
        layout.addLayout(controls)
        layout.addWidget(smart_section)

        preview_toggle = QToolButton(
            icon=QIcon.fromTheme("utilities-terminal-symbolic"),
            checkable=True,
            checked=True,
        )
        preview_toggle.setCursor(Qt.PointingHandCursor)
        preview_toggle.setToolTip("Toggle Command Preview")
        preview = QPlainTextEdit(readOnly=True)
        preview.setFont(QFont("monospace", 10))
        preview.setMinimumHeight(100)
        preview_section = AnimatedSection(preview)
        preview_toggle.toggled.connect(preview_section.set_expanded)
        layout.addWidget(preview_toggle)
        layout.addWidget(preview_section)
        self.preview_view = preview
        smart_section.set_expanded(True)
        preview_section.set_expanded(True)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        undo = QToolButton()
        undo.setIcon(QIcon.fromTheme("edit-undo-symbolic"))
        undo.setCursor(Qt.PointingHandCursor)
        undo.setToolTip("Undo Unsaved Changes")
        undo.clicked.connect(lambda: self.profile_changed.emit(self.profile_combo.currentText()))
        reset = QToolButton()
        reset.setIcon(QIcon.fromTheme("view-refresh-symbolic"))
        reset.setCursor(Qt.PointingHandCursor)
        reset.setToolTip("Reset Options")
        reset.clicked.connect(self.reset_requested)
        apply_button = QPushButton()
        apply_button.setIcon(QIcon.fromTheme("document-save-symbolic"))
        apply_button.setCursor(Qt.PointingHandCursor)
        apply_button.setToolTip("Apply to Profile")
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
            toggle.setProperty("automation-id", item.id)
            toggle.setCursor(Qt.PointingHandCursor)
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
        final_keys, final_values, _, disabled = rules_engine.evaluate_state(
            active, values, rules_engine.get_item_lookup()
        )
        values.update({key: value for key, value in final_values.items() if not key.startswith("_")})
        for item in workbench_blueprint.SMART_SCHEMA.get("Smart Automations", []):
            values[item.id] = item.id in final_keys
        config_manager.save_config(cfg)
        self.refresh_automations(values, disabled)

    def refresh_automations(self, values, disabled=None):
        disabled = disabled or {}
        self._disabled_automations = set(disabled)
        for item_id, toggle in self._automation_checks.items():
            toggle.blockSignals(True)
            toggle.setChecked(bool(values.get(item_id, False)))
            toggle.setEnabled(item_id not in self._disabled_automations)
            toggle.blockSignals(False)

    def set_profile(self, profile, path, values):
        self._switching_profile = True
        self.path_entry.setText(path)
        self.refresh_automations(values)
        self._switching_profile = False
        self.update_preview()

    def reset_requested(self):
        cfg = config_manager.load_config(force_reload=True)
        self.refresh_automations(cfg.get("remote_configs", {}).get(self.profile_combo.currentText(), {}))
        self.update_preview()

    def _browse_path(self):
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Select Local Directory", self.path_entry.text())
        if path:
            self.path_entry.setText(path)
            self.path_changed.emit(path)
            self.update_preview()

    def set_status(self, text):
        self.status_label.setText(text)

    def set_locked(self, locked):
        self.profile_combo.setEnabled(not locked)
        self.path_entry.setEnabled(not locked)
        for toggle in self._automation_checks.values():
            toggle.setEnabled(not locked and toggle.property("automation-id") not in self._disabled_automations)

    def update_preview(self):
        profile = self.profile_combo.currentText()
        if not profile:
            self.preview_view.clear()
            return
        cfg = config_manager.load_config()
        values = cfg.get("remote_configs", {}).get(profile, {}).copy()
        flags = config_manager.build_base_args(profile, cfg, values)
        remote_path = values.get("remote_path", "")
        remote = f"{profile}:{remote_path}" if remote_path else f"{profile}:"
        command = ["rclone", "bisync", self.path_entry.text(), remote] + flags
        self.preview_view.setPlainText(" ".join(f'"{arg}"' if " " in str(arg) else str(arg) for arg in command))
        self.preview_changed.emit(self.preview_view.toPlainText())
