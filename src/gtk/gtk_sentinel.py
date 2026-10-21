#!/usr/bin/env python3
import configparser
import datetime
import os
import signal
import subprocess

os.environ["NO_AT_BRIDGE"] = "1"

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
gi.require_version("Notify", "0.7")
from gi.repository import AyatanaAppIndicator3 as AppIndicator3, Gtk, Notify, GLib

from src.shared.rclone_engine import RcloneEngine
from src.shared import config_manager, workbench_blueprint, log_formatter
from src.gtk import gtk_workbench_ui


Notify.init("Rclone Sentinel")


def notify(title, message, err=False):
    Notify.Notification.new(
        title, message, "dialog-error" if err else "emblem-synchronizing"
    ).show()


class RcloneSentinelApp:
    def __init__(self):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.threads, self.workbench = {}, None
        self.rc = configparser.ConfigParser()
        if os.path.exists(workbench_blueprint.RCLONE_CONF_PATH):
            self.rc.read(workbench_blueprint.RCLONE_CONF_PATH)

        self.ind = AppIndicator3.Indicator.new(
            "rclone_tray", "network-server",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        valid_remotes = self.rc.sections()
        config_manager.prune_orphaned_remotes(valid_remotes)
        cfg = config_manager.load_config()
        for profile in valid_remotes:
            config_manager.ensure_profile_exists(profile)
            engine = RcloneEngine(
                profile,
                cfg.get("local_paths", {}).get(profile, f"/mnt/DataDrive/{profile}"),
                self._on_engine_state,
                self._on_engine_log,
            )
            self.threads[profile] = engine.start()
        self.update_menu()

    def _on_engine_state(self, engine, state):
        def update():
            if state == "blocked":
                notify(
                    f"Sync Blocked: {engine.profile}",
                    engine.last_error or "Bisync safety audit blocked this run.",
                    True,
                )
            if self.workbench:
                self.workbench.set_status(engine.profile, engine.run_state)
                if state == "completed":
                    self.workbench.reload_profile_if_active(
                        engine.profile, config_manager.load_config(force_reload=True)
                    )
            self.update_menu()
            return False
        GLib.idle_add(update)

    def _on_engine_log(self, engine, line):
        # LiveOutputPanel already tails the persisted JSONL file; this callback
        # remains available to alternate front ends and integrations.
        return None

    @staticmethod
    def _relative_time(value):
        if not value or value == "Never" or value == "Blocked":
            return value or "Never"
        try:
            clean = value.split(".")[0].split("+")[0].split("Z")[0]
            seconds = (datetime.datetime.now() -
                       datetime.datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")).total_seconds()
            if seconds < 60: return "Just now"
            if seconds < 3600: return f"{int(seconds // 60)} mins ago"
            if seconds < 86400: return f"{int(seconds // 3600)} hours ago"
            if seconds < 172800: return "Yesterday"
            return f"{int(seconds // 86400)} days ago"
        except ValueError:
            return "Unknown"

    def update_menu(self):
        menu = Gtk.Menu()

        def create_icon_item(icon_name, text):
            item = Gtk.MenuItem()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.pack_start(
                Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU),
                False,
                False,
                0,
            )
            row.pack_start(Gtk.Label(label=text, xalign=0), True, True, 0)
            row.show_all()
            item.add(row)
            return item

        for profile, engine in self.threads.items():
            icon = (
                "🔵" if engine.run_state
                else "🔴" if engine.err
                else "🟡" if engine.cancelled
                else "⚪" if engine.last == "Never"
                else "🟢"
            )
            item = Gtk.MenuItem(label=f"{icon} {profile:<12}")
            submenu = Gtk.Menu()
            stop_label = "Destroy Process" if engine.kill_clicks else "Abandon Process"
            sync = Gtk.MenuItem(label="Sync Now")
            sync.connect("activate", lambda _, e=engine: e.trigger_sync())
            sync.set_sensitive(not engine.run_state)
            submenu.append(sync)
            stop = Gtk.MenuItem(label=stop_label)
            stop.connect("activate", lambda _, e=engine: self._stop_engine(e))
            stop.set_sensitive(engine.run_state)
            submenu.append(stop)
            live = Gtk.MenuItem(label="Live Output")
            live.connect("activate", lambda _, p=profile: self.show_live_output(p))
            submenu.append(live)
            submenu.append(Gtk.SeparatorMenuItem())

            cfg = config_manager.load_config()
            profile_cfg = cfg.get("remote_configs", {}).get(profile, {})
            local_path = cfg.get("local_paths", {}).get(profile, "")
            trash_name = profile_cfg.get("--backup-dir1", workbench_blueprint.TRASH_LOCAL_NAME)
            trash_path = trash_name if os.path.isabs(trash_name) else os.path.join(local_path, trash_name)
            trash = create_icon_item("user-trash-symbolic", "Open Local Trash")
            trash.set_sensitive(os.path.exists(trash_path))
            trash.connect("activate", lambda _, path=trash_path: subprocess.Popen(["xdg-open", path]))
            submenu.append(trash)
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
            status_item = create_icon_item(status_icon, f"Status: {status}")
            status_item.set_sensitive(False)
            submenu.append(status_item)
            last = create_icon_item(
                "document-open-recent-symbolic",
                f"Last Run: {self._relative_time(engine.last)}",
            )
            last.set_sensitive(False)
            submenu.append(last)
            item.set_submenu(submenu)
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        workbench = Gtk.MenuItem(label="Inventory Workbench")
        workbench.connect("activate", lambda _: self.open_workbench())
        menu.append(workbench)
        quit_item = Gtk.MenuItem(label="Quit Application")
        quit_item.connect("activate", self.on_quit)
        menu.append(quit_item)
        menu.show_all()
        self.ind.set_menu(menu)

    def _stop_engine(self, engine):
        engine.stop_process(force=bool(engine.kill_clicks))
        engine.kill_clicks += 1
        self.update_menu()

    def open_workbench(self):
        if not self.workbench:
            self.workbench = gtk_workbench_ui.InventoryWorkbench(self)
        self.workbench.focus_workbench()
        self.workbench.show_all()
        self.workbench.present()
        return self.workbench

    def show_live_output(self, profile):
        self.open_workbench().focus_profile(profile)

    def on_quit(self, _):
        for engine in self.threads.values():
            engine.stop(force=True)
        if self.workbench:
            for profile in self.threads:
                log_formatter.stop_live_feed(profile)
        Gtk.main_quit()


def main():
    RcloneSentinelApp()
    Gtk.main()


if __name__ == "__main__":
    main()
