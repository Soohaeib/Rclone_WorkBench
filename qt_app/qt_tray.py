"""System tray controller matching the original GTK tray menu."""

import datetime
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from shared import config_manager, workbench_blueprint


class TrayController:
    def __init__(self, parent, engines, current_profile, open_workbench, show_live_output, stop_engine):
        self.parent = parent
        self.engines = engines
        self.current_profile = current_profile
        self.open_workbench = open_workbench
        self.show_live_output = show_live_output
        self.stop_engine = stop_engine
        self.tray = QSystemTrayIcon(QIcon.fromTheme("network-server"), parent)
        self.tray.activated.connect(self._activated)
        self.refresh()
        self.tray.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.parent.isVisible():
                self.parent.hide()
            else:
                self.parent.showNormal()
                self.parent.raise_()
                self.parent.activateWindow()

    @staticmethod
    def _relative(value):
        if not value or value == "Never":
            return "Never"
        try:
            clean = value.split(".")[0].split("+")[0].split("Z")[0]
            seconds = (datetime.datetime.now() - datetime.datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")).total_seconds()
            if seconds < 60: return "Just now"
            if seconds < 3600: return f"{int(seconds // 60)} mins ago"
            if seconds < 86400: return f"{int(seconds // 3600)} hours ago"
            if seconds < 172800: return "Yesterday"
            return f"{int(seconds // 86400)} days ago"
        except (TypeError, ValueError):
            return "Unknown"

    @staticmethod
    def _icon_action(icon_name, text, parent):
        action = QAction(QIcon.fromTheme(icon_name), text, parent)
        return action

    def refresh(self):
        menu = QMenu(self.parent)
        cfg = config_manager.load_config()
        for profile, engine in self.engines.items():
            icon = "🔵" if engine.run_state else "🔴" if engine.err else "🟡" if engine.cancelled else "⚪" if engine.last == "Never" else "🟢"
            action = QAction(f"{icon} {profile:<12}", menu)
            submenu = QMenu(menu)
            sync = QAction("Sync Now", submenu)
            sync.setEnabled(not engine.run_state)
            sync.triggered.connect(engine.trigger_sync)
            submenu.addAction(sync)
            stop = QAction("Destroy Process" if engine.kill_clicks else "Abandon Process", submenu)
            stop.setEnabled(engine.run_state)
            stop.triggered.connect(lambda _=False, selected=engine: self.stop_engine(selected))
            submenu.addAction(stop)
            live = QAction("Live Output", submenu)
            live.triggered.connect(lambda _=False, selected=profile: self.show_live_output(selected))
            submenu.addAction(live)
            submenu.addSeparator()
            values = cfg.get("remote_configs", {}).get(profile, {})
            path = cfg.get("local_paths", {}).get(profile, "")
            backup = values.get("--backup-dir1", workbench_blueprint.TRASH_LOCAL_NAME)
            trash = backup if os.path.isabs(str(backup)) else os.path.join(path, str(backup))
            trash_action = self._icon_action(
                "user-trash-symbolic", "Open Local Trash", submenu
            )
            trash_action.setEnabled(os.path.isdir(trash))
            trash_action.triggered.connect(lambda _=False, target=trash: QDesktopServices.openUrl(QUrl.fromLocalFile(target)))
            submenu.addAction(trash_action)
            if engine.run_state:
                status_icon, status = "view-refresh-symbolic", "Syncing..."
            elif engine.err:
                status_icon, status = "dialog-error-symbolic", "ERROR"
            elif engine.cancelled:
                status_icon, status = "process-stop-symbolic", "Cancelled"
            elif engine.last == "Never":
                status_icon, status = "media-playback-start-symbolic", "Never Run"
            else:
                status_icon, status = "emblem-synchronizing-symbolic", "Ready"
            status_action = self._icon_action(
                status_icon, f"Status: {status}", submenu
            )
            status_action.setEnabled(False)
            submenu.addAction(status_action)
            last = self._icon_action(
                "document-open-recent-symbolic",
                f"Last Run: {self._relative(engine.last)}",
                submenu,
            )
            last.setEnabled(False)
            submenu.addAction(last)
            action.setMenu(submenu)
            menu.addAction(action)
        menu.addSeparator()
        workbench = QAction("Inventory Workbench", menu)
        workbench.triggered.connect(self.open_workbench)
        menu.addAction(workbench)
        menu.addSeparator()
        quit_action = QAction("Quit Application", menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        profile = self.current_profile()
        engine = self.engines.get(profile)
        state = "Running" if engine and engine.run_state else "Ready"
        self.tray.setToolTip(f"{profile or 'Rclone Workbench'}: {state}")

    def hide(self):
        self.tray.hide()
