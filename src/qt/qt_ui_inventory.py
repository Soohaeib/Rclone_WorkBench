"""Inventory controller for the Qt Workbench shell."""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QScrollArea, QVBoxLayout, QWidget

from src.shared import config_manager, rules_engine, smart_engine, workbench_blueprint
from src.qt import qt_widget_factory as widget_factory


class InventoryPanel(QWidget):
    preview_changed = Signal(str)
    dirty_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating_rules = False
        self._locked = False
        self.profile = ""
        self.path = ""
        self.values = {}
        self.items_lookup = rules_engine.get_item_lookup()
        self.smart_keys = rules_engine.get_smart_keys()
        self.smart_toggles = {}

        self.smart_body = QWidget()
        smart_layout = QVBoxLayout(self.smart_body)
        smart_layout.setContentsMargins(10, 10, 10, 10)
        for item in workbench_blueprint.SMART_SCHEMA.get("Smart Automations", []):
            toggle = QCheckBox(item.label)
            toggle.setToolTip(item.desc or item.label)
            toggle.setCursor(Qt.PointingHandCursor)
            toggle.toggled.connect(
                lambda checked, item_id=item.id: self._automation_toggled(item_id, checked)
            )
            self.smart_toggles[item.id] = toggle
            smart_layout.addWidget(toggle)
        smart_layout.addStretch()

        self.smart_scroll = QScrollArea()
        self.smart_scroll.setWidgetResizable(True)
        self.smart_scroll.setMaximumHeight(180)
        self.smart_scroll.setWidget(self.smart_body)

        self.preview_view = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.smart_scroll)

    def attach_preview(self, preview_view):
        self.preview_view = preview_view
        self.update_preview()

    def _automation_toggled(self, item_id, checked):
        if self._updating_rules or not self.profile:
            return
        self.values[item_id] = checked
        if item_id == "preset_safe_trash" and checked and os.path.isdir(self.path):
            os.makedirs(os.path.join(self.path, workbench_blueprint.TRASH_LOCAL_NAME), exist_ok=True)
        self._evaluate_and_refresh()

    def _active_keys(self):
        return [
            key for key, value in self.values.items()
            if value is True or isinstance(value, (int, float)) or bool(value)
        ]

    def _evaluate_and_refresh(self):
        final_keys, final_values, locks, disabled = rules_engine.evaluate_state(
            self._active_keys(), self.values, self.items_lookup
        )
        self.values.update(final_values)
        for item in workbench_blueprint.SMART_SCHEMA.get("Smart Automations", []):
            self.values[item.id] = item.id in final_keys
        self._updating_rules = True
        for item_id, toggle in self.smart_toggles.items():
            toggle.setChecked(bool(self.values.get(item_id, False)))
            toggle.setEnabled(
                not self._locked and item_id not in disabled
            )
        self._updating_rules = False
        self.update_preview()
        self.dirty_changed.emit(True)

    def set_profile(self, profile, path, values):
        self.profile = profile
        self.path = path
        self.values = dict(values or {})
        self._updating_rules = True
        for item_id, toggle in self.smart_toggles.items():
            toggle.setChecked(bool(self.values.get(item_id, False)))
        self._updating_rules = False
        self.update_preview()

    def set_locked(self, locked):
        self._locked = locked
        for toggle in self.smart_toggles.values():
            toggle.setEnabled(not locked)

    def reset(self):
        cfg = config_manager.load_config(force_reload=True)
        self.values = dict(cfg.get("remote_configs", {}).get(self.profile, {}))
        self.set_profile(self.profile, self.path, self.values)

    def save_config(self):
        if not self.profile:
            return
        cfg = config_manager.load_config(force_reload=True)
        cfg.setdefault("remote_configs", {})[self.profile] = dict(self.values)
        cfg.setdefault("local_paths", {})[self.profile] = self.path
        config_manager.save_config(cfg)
        self.dirty_changed.emit(False)

    def update_preview(self):
        if self.preview_view is None:
            return
        profile = self.profile or "[PROFILE]"
        local_path = self.path or "[LOCAL_PATH]"
        active_keys = self._active_keys()
        _, enforced, _, _ = rules_engine.evaluate_state(
            active_keys, self.values, self.items_lookup
        )
        state = {**self.values, **enforced}
        args = config_manager.build_base_args(profile, {"remote_configs": {profile: state}}, state)
        command = ["rclone", "bisync", local_path, f"{profile}:"]
        command.extend(args)
        rendered = " ".join(
            f'"{value}"' if " " in str(value) else str(value) for value in command
        )
        self.preview_view.setPlainText(rendered)
        self.preview_changed.emit(rendered)
