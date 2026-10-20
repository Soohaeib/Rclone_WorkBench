"""Live Outputs page for the Qt workbench."""

import os

from PySide6.QtCore import QRegularExpression, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFont, QSyntaxHighlighter, QTextCharFormat, QIcon, QColor
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget

from src import workbench_blueprint


class LogHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        for pattern, color in (
            (r"\b\d+(?:\.\d+)?\b", "#f9e2af"),
            (r"\b\d+(?:\.\d+)?(?:\s?)(?:B/s|KB/s|MB/s|GB/s|%|checks?|deletes?)\b", "#a6e3a1"),
            (r"\b(INFO|NOTICE)\b", "#66d9ef"),
            (r"\bERROR\b.*$", "#ff6b6b"),
        ):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.rules.append((QRegularExpression(pattern), fmt))

    def highlightBlock(self, text):
        for expression, fmt in self.rules:
            match = expression.match(text)
            while match.hasMatch():
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
                match = expression.match(text, match.capturedEnd())


class LiveOutputPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(10000)
        self.log_view.setFont(QFont("monospace", 10))
        self.highlighter = LogHighlighter(self.log_view.document())
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        self.auto_scroll.setCursor(Qt.PointingHandCursor)

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
        button.setCursor(Qt.PointingHandCursor)
        icons = {"Clear": "edit-clear", "Reload": "view-refresh", "Delete": "edit-delete", "Open Dir": "folder-open"}
        if icons.get(text):
            button.setIcon(QIcon.fromTheme(icons[text]))
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
