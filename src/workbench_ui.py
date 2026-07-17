import gi, os, subprocess, signal
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from urllib.parse import unquote

from src import config_manager, rclone_runner, smart_engine, widget_factory
from src.workbench_blueprint import TRASH_LOCAL_NAME, RCLONE_CONF_PATH
from src import ui_live_output, ui_inventory

class InventoryWorkbench:
    def __init__(self, app):
        self.app = app
        self.remotes = list(app.threads.keys())
        self.global_cfg = config_manager.load_config()
        
        self.is_dirty = False
        self._is_syncing_profile = False
        
        self.builder = Gtk.Builder()
        self.builder.add_from_file(os.path.join(os.path.dirname(__file__), "workbench.glade"))
        self.window = self.builder.get_object("main_window")
        self.main_stack = self.builder.get_object("main_stack")
        self.profile_combo = self.builder.get_object("profile_combo")
        self.path_entry = self.builder.get_object("path_entry")
        self.status_label = self.builder.get_object("status_label")
        
        # ==============================================================================
        # --- GLOBAL COMMAND CENTER ---
        self.btn_sync = self.builder.get_object("btn_sync")
        self.btn_stop = self.builder.get_object("btn_stop")
        self.btn_trash = self.builder.get_object("btn_trash")
        self.btn_info = self.builder.get_object("btn_info")
        
        self.btn_sync.connect("clicked", lambda _: self.app.threads[self.profile_combo.get_active_text()].trigger_sync() if self.profile_combo.get_active_text() else None)
        self.btn_stop.connect("clicked", self.stop_current_sync)
        self.btn_trash.connect("clicked", self.open_local_trash)

        # Build Real-Time Info Popover (Global Operating Environment Only)
        self.info_popover = Gtk.Popover.new(self.btn_info)
        self.info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.info_box.set_margin_start(16); self.info_box.set_margin_end(16)
        self.info_box.set_margin_top(16); self.info_box.set_margin_bottom(16)
        
        def _add_info_row(icon_name, default_text):
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            lbl = Gtk.Label(label=default_text, xalign=0)
            hbox.pack_start(img, False, False, 0)
            hbox.pack_start(lbl, True, True, 0)
            self.info_box.pack_start(hbox, False, False, 0)
            return lbl

        self.lbl_ram = _add_info_row("drive-harddisk-symbolic", "Available RAM: ...")
        self.lbl_cpu = _add_info_row("applications-system-symbolic", "Logical Cores: ...")
        self.lbl_load = _add_info_row("utilities-system-monitor-symbolic", "System Load: ...")
        
        self.info_box.show_all()
        self.info_popover.add(self.info_box)
        self.btn_info.set_popover(self.info_popover)
        # ==============================================================================

        # Rclone Web Portal Button
        self.btn_rclone_gui = self.builder.get_object("btn_rclone_gui")
        if self.btn_rclone_gui:
            self.btn_rclone_gui.set_name("btn_rclone_gui")
            self.btn_rclone_gui.set_image(Gtk.Image.new_from_icon_name("web-browser-symbolic", Gtk.IconSize.BUTTON))
            self.btn_rclone_gui.set_always_show_image(True)
            self.btn_rclone_gui.connect("clicked", self.toggle_rclone_gui)
        self.gui_process = None
        # ==============================================================================
        
        self.btn_rclone_update = self.builder.get_object("btn_rclone_update")
        if self.btn_rclone_update:
            self.btn_rclone_update.set_name("btn_rclone_update")
            self.btn_rclone_update.connect("clicked", self.update_rclone_system)
            self._check_rclone_status()

        self.path_entry.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.path_entry.drag_dest_add_uri_targets()
        
        def _on_path_drop(wid, ctx, x, y, data, info, time):
            if uris := data.get_uris():
                path = unquote(uris[0].replace("file://", "").strip('\r\n'))
                if os.path.isfile(path): path = os.path.dirname(path) 
                wid.set_text(path)
                ctx.finish(True, False, time)
                wid.stop_emission_by_name("drag-data-received")
                return True
            return False
            
        self.path_entry.connect("drag-data-received", _on_path_drop)

        self._setup_minimal_css()
        self.window.connect("delete-event", lambda *_: self.window.hide() or True)
        
        self.builder.get_object("btn_toggle_smart").connect('clicked', lambda _: self.builder.get_object("smart_revealer").set_reveal_child(not self.builder.get_object("smart_revealer").get_reveal_child()))
        self.builder.get_object("btn_toggle_preview").connect('clicked', lambda _: self.builder.get_object("preview_revealer").set_reveal_child(not self.builder.get_object("preview_revealer").get_reveal_child()))
        
        def on_reset_clicked(btn):
            menu = Gtk.Menu()
            def create_menu_item_with_icon(icon_name, text):
                item = Gtk.MenuItem()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
                lbl = Gtk.Label(label=text, xalign=0)
                box.pack_start(icon, False, False, 0)
                box.pack_start(lbl, True, True, 0)
                box.show_all()
                item.add(box)
                return item
                
            i_default = create_menu_item_with_icon("view-refresh-symbolic", "Reset to Stable Defaults")
            i_default.connect("activate", lambda _: self.inventory_panel.reset_to_factory_defaults(None))
            menu.append(i_default)
            
            i_last = create_menu_item_with_icon("document-revert-symbolic", "Revert to Last Saved State")
            i_last.connect("activate", lambda _: setattr(self, 'global_cfg', config_manager.load_config(force_reload=True)) or self.inventory_panel.load_data())
            menu.append(i_last)
            
            menu.show_all()
            menu.popup_at_widget(btn, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

        self.builder.get_object("btn_reset").connect("clicked", on_reset_clicked)
        if undo_btn := self.builder.get_object("btn_undo"):
            undo_btn.connect("clicked", lambda _: setattr(self, 'global_cfg', config_manager.load_config(force_reload=True)) or self.inventory_panel.load_data())
            
        def _browse(_):
            d = Gtk.FileChooserDialog(title="Select Local Directory", parent=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER)
            d.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
            if d.run() == Gtk.ResponseType.OK: 
                self.path_entry.set_text(d.get_filename())
                self.inventory_panel.check_dirty()
            d.destroy()
            
        self.builder.get_object("btn_browse").connect("clicked", _browse)

        # ==============================================================================
        # --- INITIALIZE SUB-COMPONENTS ---
        self.output_panel = ui_live_output.LiveOutputPanel(self.remotes)
        self.output_panel.change_callback = self.sync_ui_to_log_tab
        self.builder.get_object("live_output_hook").pack_start(self.output_panel.container, True, True, 0)

        self.inventory_panel = ui_inventory.InventoryPanel(self, self.builder)
        
        # Wire up combo and entry after panels are created
        self.profile_combo.connect("changed", self.on_profile_changed)
        self.path_entry.connect("changed", lambda _: self.inventory_panel.check_dirty())

        for r in self.remotes: 
            self.profile_combo.append_text(r)
        if self.remotes:
            self.profile_combo.set_active(0)

        GLib.timeout_add(2000, self.realtime_overdrive_poll)

    def reload_profile_if_active(self, profile, new_cfg):
        """Passes reload triggers down to the active inventory panel."""
        self.inventory_panel.reload_profile_if_active(profile, new_cfg)

    # --- PROCESS KILL & TRASH FUNCTIONS ---
    def stop_current_sync(self, btn):
        if (p := self.profile_combo.get_active_text()) and p in self.app.threads:
            t = self.app.threads[p]
            # First click = Graceful SIGINT. Second click = Forceful SIGKILL.
            rclone_runner.kill_process(t.proc, force=(t.kill_clicks > 0))
            t.kill_clicks += 1
            
            # Update the UI button tooltip to warn the user that the next click is forceful
            if t.run_state:
                self.btn_stop.set_tooltip_text("Force Stop Session" if t.kill_clicks == 1 else "Terminating...")

    def open_local_trash(self, btn):
        if hasattr(self, 'current_trash_path') and os.path.exists(self.current_trash_path):
            subprocess.Popen(['xdg-open', self.current_trash_path])

    # --- SYSTEM UPDATE & HEALTH MODULE ---
    def _check_rclone_status(self):
        import threading, subprocess, os, configparser
        def _runner():
            try:
                res_ver = subprocess.run(['rclone', 'version'], capture_output=True, text=True)
                if res_ver.returncode != 0:
                    GLib.idle_add(self._set_system_state, "MISSING", None)
                    return
            except FileNotFoundError:
                GLib.idle_add(self._set_system_state, "MISSING", None)
                return
            
            rc = configparser.ConfigParser()
            if not os.path.exists(RCLONE_CONF_PATH) or not rc.read(RCLONE_CONF_PATH) or not rc.sections():
                GLib.idle_add(self._set_system_state, "NO_CONFIG", None)
                return

            GLib.idle_add(self._set_system_state, "OK", None)
            
        threading.Thread(target=_runner, daemon=True).start()

    def _set_system_state(self, state, data):
        if not hasattr(self, 'state_css'):
            self.state_css = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.state_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        self.btn_sync.set_sensitive(state == "OK" and not getattr(self, 'is_dirty', False))
        self.btn_trash.set_sensitive(state == "OK")
        self.main_stack.set_sensitive(state == "OK")
        self.profile_combo.set_sensitive(state == "OK")
        self.path_entry.set_sensitive(state == "OK")
        self.btn_rclone_gui.set_sensitive(state in ["OK", "NO_CONFIG"])
        
        self.rclone_needs_install = (state == "MISSING")
        
        if state == "MISSING":
            # RECOLORED: Red background for missing Rclone install mode action button
            self.state_css.load_from_data(b"#btn_rclone_update { background-image: none; background-color: #c0392b; border-color: #a93226; color: white; } #btn_rclone_update:hover { background-color: #e74c3c; }")
            self.btn_rclone_update.set_tooltip_text("Rclone Not Found! Click to Install.")
            self.status_label.set_markup("<span foreground='#e74c3c'><b>Rclone is not installed!</b></span>")
            self.btn_rclone_update.set_sensitive(True)
        elif state == "NO_CONFIG":
            # Config Missing: Orange status text and Web GUI button
            self.state_css.load_from_data(b"#btn_rclone_gui { background-image: none; background-color: #e67e22; border-color: #d35400; color: white; } #btn_rclone_gui:hover { background-color: #f39c12; }")
            self.btn_rclone_update.set_tooltip_text("Check and Update Rclone")
            self.btn_rclone_gui.set_tooltip_text("No remotes configured. Click to open Web GUI.")
            self.status_label.set_markup("<span foreground='#e67e22'><b>Please configure a remote to begin.</b></span>")
            self.btn_rclone_update.set_sensitive(True)
        else:
            self.state_css.load_from_data(b"")
            self.btn_rclone_update.set_tooltip_text("Check and Update Rclone")
            self.btn_rclone_update.set_sensitive(True)

    def update_rclone_system(self, btn):
        import threading, subprocess
        is_install = getattr(self, 'rclone_needs_install', False)
        cmd = ['pkexec', 'bash', '-c', 'curl https://rclone.org/install.sh | bash'] if is_install else ['pkexec', 'rclone', 'selfupdate']
        
        def _updater():
            try:
                GLib.idle_add(btn.set_sensitive, False)
                if is_install:
                    GLib.idle_add(btn.set_tooltip_text, "Installing Rclone...")
                else:
                    GLib.idle_add(btn.set_tooltip_text, "Updating Rclone...")
                
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    if is_install:
                        subprocess.Popen(['notify-send', 'Rclone Installed', 'Successfully installed Rclone!', '-i', 'software-update-available-symbolic'])
                    else:
                        out = (res.stdout + res.stderr).lower()
                        if "up to date" in out or "already up to date" in out:
                            subprocess.Popen(['notify-send', 'Rclone', 'Rclone is already up to date.', '-i', 'dialog-information'])
                        else:
                            subprocess.Popen(['notify-send', 'Rclone Updated', 'Successfully updated to the latest version!', '-i', 'software-update-available-symbolic'])
                    GLib.idle_add(self._check_rclone_status)
                else:
                    if "dismissed" not in res.stderr.lower() and "polkit" not in res.stderr.lower():
                        subprocess.Popen(['notify-send', 'Error', res.stderr.strip() or 'An unknown error occurred.', '-i', 'dialog-error'])
            except Exception as e:
                subprocess.Popen(['notify-send', 'Error', str(e), '-i', 'dialog-error'])
            finally:
                GLib.idle_add(btn.set_sensitive, True)
                GLib.idle_add(btn.set_tooltip_text, "Rclone Not Found! Click to Install." if is_install else "Check and Update Rclone")
                
        threading.Thread(target=_updater, daemon=True).start()

    # --- DYNAMIC CONFIGURATION PORTAL MODE ---
    def toggle_rclone_gui(self, btn):
        if not self.gui_process:
            try:
                subprocess.Popen(['notify-send', 'Rclone Web Portal', 'You can safely manage configs here.\n\nNOTE: Do NOT use the portal to update Rclone. Use the dedicated update button instead.', '-i', 'dialog-warning'])
                
                self.gui_process = subprocess.Popen(
                    ["rclone", "gui"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid
                )
                
                # Toggle visual state with a custom CSS provider to enforce red background while keeping circular shape
                self.btn_rclone_gui.set_tooltip_text("Close Rclone Web Configuration Portal")
                if not hasattr(self, 'red_btn_css'):
                    self.red_btn_css = Gtk.CssProvider()
                    self.red_btn_css.load_from_data(b"button { background-image: none; background-color: #c0392b; border-color: #a93226; color: white; } button:hover { background-color: #e74c3c; border-color: #c0392b; }")
                self.btn_rclone_gui.get_style_context().add_provider(self.red_btn_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                
                self.btn_sync.set_sensitive(False)
                self.btn_stop.set_sensitive(False)
                self.btn_trash.set_sensitive(False)
                self.btn_info.set_sensitive(False)
                self.profile_combo.set_sensitive(False)
                self.path_entry.set_sensitive(False)
                self.main_stack.set_sensitive(False)
                self.builder.get_object("btn_reset").set_sensitive(False)
                if undo := self.builder.get_object("btn_undo"): undo.set_sensitive(False)
                
            except Exception as e:
                self.status_label.set_markup(f"<span foreground='#e74c3c'><b>Failed to start Web GUI: {e}</b></span>")
        else:
            try:
                os.killpg(os.getpgid(self.gui_process.pid), signal.SIGTERM)
            except: pass
            self.gui_process = None
            
            # Return portal button back to its initial textless entry state
            self.btn_rclone_gui.set_tooltip_text("Launch official Rclone Web Configurator")
            if hasattr(self, 'red_btn_css'):
                self.btn_rclone_gui.get_style_context().remove_provider(self.red_btn_css)
            
            self._check_rclone_status() # Let the state machine unlock the UI safely
            self.btn_info.set_sensitive(True)
            self.builder.get_object("btn_reset").set_sensitive(True)
            if undo := self.builder.get_object("btn_undo"): undo.set_sensitive(True)
            
            self.app.rc.read(RCLONE_CONF_PATH)
            valid_remotes = self.app.rc.sections()
            config_manager.prune_orphaned_remotes(valid_remotes)
            
            self.profile_combo.remove_all()
            for r in valid_remotes:
                config_manager.ensure_profile_exists(r)
                if r not in self.app.threads:
                    from app import SyncThread
                    self.global_cfg = config_manager.load_config(force_reload=True)
                    t = SyncThread(r, self.global_cfg.get('local_paths', {}).get(r, f"/mnt/DataDrive/{r}"), self.app)
                    self.app.threads[r] = t
                    t.start()
                self.profile_combo.append_text(r)
                
            self.app.update_menu()
            
            if valid_remotes:
                self.profile_combo.set_active(0)
                
            self.global_cfg = config_manager.load_config(force_reload=True)
            self.inventory_panel.load_data()

    def focus_profile(self, profile): 
        self.main_stack.set_visible_child_name("page1")
        self.output_panel.focus_profile(profile)
        
    def focus_workbench(self): 
        self.main_stack.set_visible_child_name("page0")
    
    def set_status(self, profile, is_running): 
        self.output_panel.set_status(profile, is_running)
        if self.profile_combo.get_active_text() == profile:
            self.btn_sync.set_sensitive(not is_running)
            self.btn_stop.set_sensitive(is_running)
            self.btn_rclone_gui.set_sensitive(not is_running)
            self.btn_stop.set_tooltip_text("Stop Active Sync Session")
    
    def show_all(self): self.window.show_all()
    def present(self): self.window.present()
    
    def _setup_minimal_css(self):
        p = Gtk.CssProvider(); p.load_from_data(b".chip { border-radius: 999px; padding: 4px 10px; margin: 2px; } .canvas-card { margin-bottom: 6px; padding: 10px; border-bottom: 1px solid alpha(gray, 0.2); } .log-header-btn { padding: 2px 6px; min-height: 24px; min-width: 28px; margin: 0; }")
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def on_profile_changed(self, combo):
        if self._is_syncing_profile: return
        if profile := combo.get_active_text(): 
            self._is_syncing_profile = True
            self.inventory_panel.load_data()
            self.output_panel.focus_profile(profile)
            
            is_running = self.app.threads[profile].run_state
            self.btn_sync.set_sensitive(not is_running)
            self.btn_stop.set_sensitive(is_running)
            self._is_syncing_profile = False

    def sync_ui_to_log_tab(self, profile_name):
        if self._is_syncing_profile: return
        self._is_syncing_profile = True
        for i, row in enumerate(self.profile_combo.get_model()):
            if row[0].lower() == profile_name.lower(): 
                self.profile_combo.set_active(i)
                self.inventory_panel.load_data()
                break
        self._is_syncing_profile = False

    # --- REAL-TIME SYSTEM POLLER & UI UPDATER ---
    def realtime_overdrive_poll(self):
        bounds = smart_engine.get_hardware_bounds()
        p = self.profile_combo.get_active_text()
        
        # --- Update Native Popover Hardware UI (Global OS Info) ---
        import os
        cores = os.cpu_count() or 2
        try: load = os.getloadavg()[0] # 1-minute system load average
        except: load = 0.0
        
        self.lbl_ram.set_label(f"Available RAM: {bounds['mem_gb']:.2f} GB")
        self.lbl_cpu.set_label(f"Logical Cores: {cores}")
        self.lbl_load.set_label(f"System Load (1m): {load:.2f}")
        # ----------------------------------------------------------
        
        if p and p in self.app.threads:
            # Dynamic Trash Button State Evaluator
            cfg = config_manager.load_config()
            p_cfg = cfg.get('remote_configs', {}).get(p, {})
            l_path = self.path_entry.get_text() 
            t_name = p_cfg.get('--backup-dir1', TRASH_LOCAL_NAME)
            self.current_trash_path = t_name if os.path.isabs(t_name) else os.path.join(l_path, t_name)
            
            trash_exists = os.path.exists(self.current_trash_path)
            self.btn_trash.set_sensitive(trash_exists)
            self.btn_trash.set_tooltip_text("Open Local Trash" if trash_exists else "Local Trash (Unavailable)")

        # Dynamic Overdrive Widget Enforcement (Delegated to inventory panel fields)
        if self.inventory_panel.smart_toggles.get("preset_overdrive_sync", Gtk.Switch()).get_active():
            changed = False
            for row in self.inventory_panel.can_list.get_children():
                if row.key in ['--checkers', '--transfers'] and hasattr(row, 'input_widget'):
                    adj = row.input_widget.get_adjustment()
                    new_max = bounds[row.key]
                    
                    if adj.get_upper() != new_max:
                        widget_factory.update_spin_bounds(row, new_max)
                        if adj.get_value() > new_max:
                            adj.set_value(new_max)
                        changed = True

            if changed:
                self.inventory_panel.check_dirty()
                
        return True