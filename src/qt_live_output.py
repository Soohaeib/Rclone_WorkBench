"""Live Outputs page for the Qt workbench."""

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget

from src import workbench_blueprint


class LiveOutputPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(10000)
        self.log_view.setFont(QFont("monospace", 10))
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        toolbar.addWidget(QLabel("Live Output"))
        toolbar.addStretch()
        toolbar.addWidget(self.auto_scroll)
        toolbar.addWidget(self._button("Clear", self.log_view.clear))
        toolbar.addWidget(self._button("Reload", self.reload_current))
        toolbar.addWidget(self._button("Delete", self.delete_current))
        toolbar.addWidget(self._button("Open Dir", self.open_log_directory))
        layout.addLayout(toolbar)
        layout.addWidget(self.log_view, 1)
        self.profile = ""

    def _button(self, text, callback):
        button = QToolButton(text=text)
        button.setObjectName("log-header-btn")
        button.clicked.connect(callback)
        return button

    def set_profile(self, profile):
        self.profile = profile
        self.reload_current()

    def append_log(self, engine, current_engine, line):
        if engine is not current_engine:
            return
        scrollbar = self.log_view.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        self.log_view.appendPlainText(line)
        if self.auto_scroll.isChecked() and at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def reload_current(self):
        self.log_view.clear()
        path = os.path.join(workbench_blueprint.LOG_DIR, f"{self.profile}_sync.jsonl")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as log_file:
                self.log_view.setPlainText(log_file.read())

    def delete_current(self):
        path = os.path.join(workbench_blueprint.LOG_DIR, f"{self.profile}_sync.jsonl")
        if os.path.isfile(path):
            os.remove(path)
        self.log_view.setPlainText("[SYSTEM] Log deleted.")

    @staticmethod
    def open_log_directory():
        os.makedirs(workbench_blueprint.LOG_DIR, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(workbench_blueprint.LOG_DIR))
