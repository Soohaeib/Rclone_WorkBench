"""Visual Qt shell for the Workbench inventory and command preview."""

import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.shared import config_manager
from src.qt.qt_ui_inventory import InventoryPanel


class DropPathEdit(QLineEdit):
    path_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Local path...")
        self.setCursor(Qt.PointingHandCursor)

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
            if os.path.isfile(path):
                path = os.path.dirname(path)
            if os.path.isdir(path):
                self.setText(path)
                self.path_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()


class AnimatedSection(QWidget):
    def __init__(self, content, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)
        self._content = content
        self.setMaximumHeight(0)
        self._animation = QPropertyAnimation(self, b"maximumHeight", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)

    def set_expanded(self, expanded):
        self._content.adjustSize()
        height = max(self._content.sizeHint().height(), 1)
        self._animation.stop()
        self._animation.setStartValue(self.maximumHeight())
        self._animation.setEndValue(height if expanded else 0)
        self._animation.start()


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
        self.profile_combo = QComboBox()
        self.profile_combo.setCursor(Qt.PointingHandCursor)
        self.profile_combo.addItems(self._profiles())
        self.profile_combo.currentTextChanged.connect(self.profile_changed)

        self.path_entry = DropPathEdit()
        self.path_entry.path_dropped.connect(self.path_changed)
        self.path_entry.textChanged.connect(self._path_edited)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.inventory_panel = InventoryPanel(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(16)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        smart_toggle = QToolButton()
        smart_toggle.setIcon(QIcon.fromTheme("sidebar-show-symbolic"))
        smart_toggle.setCursor(Qt.PointingHandCursor)
        smart_toggle.setToolTip("Toggle Smart Presets")
        smart_toggle.setCheckable(True)
        smart_toggle.setChecked(True)
        smart_section = AnimatedSection(self.inventory_panel.smart_scroll)
        smart_toggle.toggled.connect(smart_section.set_expanded)
        controls.addWidget(smart_toggle)
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

        preview_toggle = QToolButton()
        preview_toggle.setIcon(QIcon.fromTheme("utilities-terminal-symbolic"))
        preview_toggle.setCursor(Qt.PointingHandCursor)
        preview_toggle.setToolTip("Toggle Command Preview")
        preview_toggle.setCheckable(True)
        preview_toggle.setChecked(True)
        preview_section = AnimatedSection(self.inventory_panel_preview())
        preview_toggle.toggled.connect(preview_section.set_expanded)
        layout.addWidget(preview_toggle)
        layout.addWidget(preview_section)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        undo = self._icon_button("edit-undo-symbolic", "Undo Unsaved Changes")
        undo.clicked.connect(self._reload_profile)
        reset = self._icon_button("view-refresh-symbolic", "Reset Options")
        reset.clicked.connect(self.inventory_panel.reset)
        apply_button = self._icon_button("document-save-symbolic", "Apply to Profile", QPushButton)
        apply_button.setObjectName("btn_apply")
        apply_button.clicked.connect(self.inventory_panel.save_config)
        apply_button.clicked.connect(self.apply_requested)
        footer.addWidget(undo)
        footer.addWidget(reset)
        footer.addWidget(self.status_label, 1)
        footer.addWidget(apply_button)
        layout.addLayout(footer)

        smart_section.set_expanded(True)
        preview_section.set_expanded(True)

    @staticmethod
    def _icon_button(icon_name, tooltip, cls=QToolButton):
        button = cls()
        button.setIcon(QIcon.fromTheme(icon_name))
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        return button

    @staticmethod
    def _profiles():
        cfg = config_manager.load_config()
        return sorted(set(cfg.get("local_paths", {})) | set(cfg.get("remote_configs", {})))

    def inventory_panel_preview(self):
        preview = QPlainTextEdit(readOnly=True)
        preview.setFont(QFont("monospace", 10))
        preview.setMinimumHeight(100)
        self.inventory_panel.attach_preview(preview)
        return preview

    def _path_edited(self, path):
        self.inventory_panel.path = path
        self.inventory_panel.update_preview()

    def _reload_profile(self):
        self.set_profile(
            self.profile_combo.currentText(),
            self.path_entry.text(),
            config_manager.load_config(force_reload=True)
            .get("remote_configs", {})
            .get(self.profile_combo.currentText(), {}),
        )

    def _browse_path(self):
        from PySide6.QtWidgets import QFileDialog

        path = QFileDialog.getExistingDirectory(
            self, "Select Local Directory", self.path_entry.text()
        )
        if path:
            self.path_entry.setText(path)
            self.path_changed.emit(path)

    def set_profile(self, profile, path, values):
        self.path_entry.setText(path)
        self.inventory_panel.set_profile(profile, path, values)

    def set_status(self, text):
        self.status_label.setText(text)

    def set_locked(self, locked):
        self.profile_combo.setEnabled(not locked)
        self.path_entry.setEnabled(not locked)
        self.inventory_panel.set_locked(locked)
