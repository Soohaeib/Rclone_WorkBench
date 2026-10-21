"""PySide6 widget factory for inventory chips and configuration rows."""

import os
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


THEME = {
    "critical": "#c0392b",
    "decision": "#e67e22",
    "safety": "#27ae60",
    "operational": "#2980b9",
    "heuristic": "#8e44ad",
    "system": "#7f8c8d",
}


class CanvasRow(QWidget):
    changed = Signal()

    def __init__(self, item, base_key, row_key, value, parent=None):
        super().__init__(parent)
        self.key = row_key
        self.item = item
        self.base_key = base_key
        self.checkboxes = {}
        self.drop_btn = QPushButton()
        self.drop_btn.setIcon(QIcon.fromTheme("list-remove-symbolic"))
        self.split_btn = None
        self.input_widget = None
        self._build(value)

    def _build(self, value):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        header = QHBoxLayout()
        label = QLabel(self.item.label)
        label.setStyleSheet(
            f"color: {THEME.get(getattr(self.item, 'severity', 'system'), '#fff')};"
            " font-weight: bold;"
        )
        if self.item.desc:
            label.setToolTip(self.item.desc)
        header.addWidget(label, 1)
        header.addWidget(self.drop_btn)
        layout.addLayout(header)

        item_type = getattr(self.item, "type", None)
        if item_type == "entry":
            self.input_widget = QLineEdit(str(value or ""))
            self.input_widget.textChanged.connect(self.changed)
        elif item_type == "multi":
            container = QWidget()
            flow = QHBoxLayout(container)
            flow.setContentsMargins(0, 0, 0, 0)
            active = {part.strip() for part in str(value or "").split(",")}
            for option in getattr(self.item, "options", []):
                checkbox = QCheckBox(option)
                checkbox.setChecked(option in active)
                checkbox.toggled.connect(self.changed)
                self.checkboxes[option] = checkbox
                flow.addWidget(checkbox)
            self.input_widget = container
        elif item_type == "combo":
            self.input_widget = QComboBox()
            self.input_widget.addItems(getattr(self.item, "options", []))
            if str(value) in getattr(self.item, "options", []):
                self.input_widget.setCurrentText(str(value))
            self.input_widget.currentTextChanged.connect(self.changed)
        elif item_type == "text":
            self.input_widget = QTextEdit(str(value or ""))
            self.input_widget.textChanged.connect(self.changed)
        elif item_type in {"number", "count"}:
            validation = getattr(self.item, "validation", {})
            self.input_widget = QSpinBox()
            self.input_widget.setRange(
                int(validation.get("min", 0)), int(validation.get("max", 1000000))
            )
            self.input_widget.setValue(int(value or validation.get("min", 0)))
            self.input_widget.valueChanged.connect(self.changed)
        if self.input_widget is not None:
            layout.addWidget(self.input_widget)
        self.setProperty("class", "canvas-card")


def create_inventory_chip(item, item_id, equip_callback, disabled_keys=None):
    disabled_keys = disabled_keys or {}
    button = QPushButton(item.label)
    button.setProperty("class", "chip")
    color = THEME.get(getattr(item, "severity", "system"), "#ffffff")
    button.setStyleSheet(f"color: {color};")
    if item_id in disabled_keys:
        button.setEnabled(False)
        button.setToolTip(f"Locked by {disabled_keys[item_id]}")
    else:
        button.setToolTip(item.desc or item.label)
        button.clicked.connect(lambda: equip_callback(item_id))
    return button


def create_canvas_row(item, base_key, row_key, value, lock_state, cb_change, cb_unequip, cb_split):
    row = CanvasRow(item, base_key, row_key, value)
    row.drop_btn.clicked.connect(lambda: cb_unequip(row))
    row.changed.connect(cb_change)
    if getattr(item, "clone_limit", 0) and "." not in row_key:
        row.split_btn = QPushButton()
        row.split_btn.setIcon(QIcon.fromTheme("list-add-symbolic"))
        row.split_btn.setToolTip("Split into an additional unblocked entry")
        row.split_btn.clicked.connect(
            lambda: cb_split(f"{base_key}.{uuid.uuid4().hex[:6]}", item.clone_limit, base_key)
        )
        row.layout().itemAt(0).layout().addWidget(row.split_btn)
    apply_locks(row, getattr(item, "type", None), lock_state)
    return row


def apply_locks(row, item_type, lock_state):
    locked = bool(lock_state)
    row.drop_btn.setVisible(not locked)
    if isinstance(lock_state, str):
        row.input_widget.setEnabled(False)
        row.input_widget.setToolTip(f"Locked by {lock_state}")
        return
    if item_type == "multi":
        for option, checkbox in row.checkboxes.items():
            owner = lock_state.get(option) if isinstance(lock_state, dict) else None
            checkbox.setEnabled(not owner)
            checkbox.setToolTip(f"Locked by {owner}" if owner else "")
    elif row.input_widget is not None:
        row.input_widget.setEnabled(not locked)


def extract_value(row, item_type):
    if item_type == "check" or row.input_widget is None:
        return True
    if item_type == "entry":
        return row.input_widget.text()
    if item_type == "multi":
        return ",".join(k for k, value in row.checkboxes.items() if value.isChecked())
    if item_type == "combo":
        return row.input_widget.currentText()
    if item_type == "text":
        return row.input_widget.toPlainText()
    if item_type in {"number", "count"}:
        return row.input_widget.value()
    return None


def inject_value(row, item, value):
    item_type = getattr(item, "type", None)
    widget = row.input_widget
    if widget is None:
        return
    if item_type == "entry":
        widget.setText(str(value or ""))
    elif item_type == "multi":
        active = {part.strip() for part in str(value or "").split(",")}
        for option, checkbox in row.checkboxes.items():
            checkbox.setChecked(option in active)
    elif item_type == "combo":
        widget.setCurrentText(str(value or ""))
    elif item_type == "text":
        widget.setPlainText(str(value or ""))
    elif item_type in {"number", "count"}:
        widget.setValue(int(value or 0))
