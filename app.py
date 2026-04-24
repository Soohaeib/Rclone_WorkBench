#usr/bin/env python3
import os
os.environ["NO_AT_BRIDGE"] = "1" # Suppress GTK/Nemo DBus accessibility spam

import gi, signal, threading, time, datetime, configparser
gi.require_version('Gtk', '3.0'); gi.require_version('AppIndicator3', '0.1'); gi.require_version('Notify', '0.7')
from gi.repository import Gtk, GLib, AppIndicator3, Notify
from src import workbench_blueprint, config_manager, workbench_ui, rclone_runner, log_formatter, rules_engine, smart_engine

Notify.init("RClone Workbench")
def notify(title, msg, err=False): Notify.Notification.new(title, msg, "dialog-error" if err else "emblem-synchronizing").show()

class SyncThread(threading.Thread):
    def __init__(self, profile, path, app):
        super().__init__(daemon=True)
        self.profile, self.path, self.app = profile, path, app
        self.req, self.run_state, self.err, self.last, self.proc = False, False, False, "Never", None
        self.last = log_formatter.get_last_run_time(profile)
        self.kill_clicks = 0

    def trigger_sync(self): self.req = True

    def run(self):
        while True:
            if not self.req: 
                time.sleep(1)
                continue
                
            self.req, self.run_state, self.err = False, True, False
            self.kill_clicks = 0
            
            GLib.idle_add(self.app.update_menu)
            if self.app.workbench: 
                self.app.workbench.set_status(self.profile, True)
            
            cfg = config_manager.load_config()
            lookup = rules_engine.get_item_lookup()
            live_state = cfg.get('remote_configs', {}).get(self.profile, {}).copy()
            local_path = cfg.get('local_paths', {}).get(self.profile, '')
            remote_path = live_state.get('remote_path', '')
            
            live_state = smart_engine.audit_resync_environment(
                self.profile, local_path, remote_path, live_state
            )
            
            audit_errors =[v for k, v in live_state.items() if k.startswith('_AUDIT_ERROR')]
            
            if audit_errors:
                self.err = True
                self.run_state = False
                self.last = "Blocked"
                error_msg = audit_errors[0]
                GLib.idle_add(notify, f"Sync Blocked: {self.profile}", error_msg, True)
                GLib.idle_add(self.app.update_menu)
                if self.app.workbench: 
                    self.app.workbench.set_status(self.profile, False)
                continue 

            if '--backup-dir1' in live_state and hasattr(smart_engine, 'setup_trash_bins'):
                live_state = smart_engine.setup_trash_bins(self.profile, local_path, remote_path, live_state)
                
            flags = config_manager.build_base_args(self.profile, cfg, live_state)
            
            remote_full = f"{self.profile}:{remote_path}" if remote_path else f"{self.profile}:"
            args =["bisync", local_path, remote_full] + flags
            
            res = rclone_runner.run_sync_session(self.profile, args)

            self.run_state = False
            self.err = not res.get("success", False)
            self.last = datetime.datetime.now().isoformat()
            self.proc = None
            
            if self.app.workbench:
                self.app.workbench.set_status(self.profile, False)
                
            if not self.err:
                cfg = config_manager.load_config()
                p_cfg = cfg.setdefault('remote_configs', {}).setdefault(self.profile, {})
                
                import hashlib
                f_txt = "\n".join([v for k, v in live_state.items() if k.startswith('--filter') and isinstance(v, str)])
                if 'filter_hashes' not in cfg:
                    cfg['filter_hashes'] = {}
                if f_txt:
                    cfg['filter_hashes'][self.profile] = hashlib.md5(f_txt.encode()).hexdigest()
                else:
                    cfg['filter_hashes'].pop(self.profile, None)
                
                dropped = False
                for i in workbench_blueprint.SMART_SCHEMA.get("Smart Automations",[]):
                    if getattr(i, "lifecycle", "persistent") == "one_time" and p_cfg.get(i.id):
                        p_cfg.pop(i.id, None)
                        for k in getattr(i, "satisfy", {}).keys():
                            p_cfg.pop(k, None)
                        for k in getattr(i, "expects",[]):
                            p_cfg.pop(k, None)
                        dropped = True
                        
                if dropped:
                    active_keys =[k for k, v in p_cfg.items() if v is True or (isinstance(v, str) and v) or (type(v) in [int, float])]
                    _, merged, _, _ = rules_engine.evaluate_state(active_keys, p_cfg, rules_engine.get_item_lookup())
                    cfg['remote_configs'][self.profile] = merged
                    
                config_manager.save_config(cfg)
                
                if self.app.workbench:
                    GLib.idle_add(self.app.workbench.reload_profile_if_active, self.profile, cfg)
                    
            GLib.idle_add(self.app.update_menu)
            
class RCloneWorkbenchApp:
    def __init__(self):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.threads, self.workbench, self.rc = {}, None, configparser.ConfigParser()
        
        if not os.path.exists(workbench_blueprint.RCLONE_CONF_PATH) or not self.rc.read(workbench_blueprint.RCLONE_CONF_PATH) or not self.rc.sections():
            notify("Error", "Valid rclone.conf not found or empty.", True); return

        self.ind = AppIndicator3.Indicator.new("rclone_tray", "network-server", AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        cfg = config_manager.load_config()
        for r in self.rc.sections():
            thread = SyncThread(r, cfg.get('local_paths', {}).get(r, f"/mnt/DataDrive/{r}"), self)
            config_manager.ensure_profile_exists(r); self.threads[r] = thread; thread.start()
        self.update_menu()

    def update_menu(self):
        m = Gtk.Menu()
        import subprocess # Safely import for the xdg-open calls
        
        # Helper to calculate relative time dynamically
        def format_relative(iso_str):
            if not iso_str or iso_str == "Never": return "Never"
            try:
                clean_iso = iso_str.split('.')[0].split('+')[0].split('Z')[0]
                dt = datetime.datetime.strptime(clean_iso, "%Y-%m-%dT%H:%M:%S")
                secs = (datetime.datetime.now() - dt).total_seconds()
                
                if secs < 60: return "Just now"
                if secs < 3600: return f"{int(secs//60)} mins ago"
                if secs < 86400: return f"{int(secs//3600)} hours ago"
                if secs < 172800: return "Yesterday"
                return f"{int(secs//86400)} days ago"
            except: 
                return "Unknown"

        # Helper to create a menu item with a native GTK symbolic icon
        def create_icon_item(icon_name, text):
            item = Gtk.MenuItem()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            lbl = Gtk.Label(label=text, xalign=0)
            box.pack_start(icon, False, False, 0)
            box.pack_start(lbl, True, True, 0)
            box.show_all() 
            item.add(box)
            return item

        # Load live config to resolve dynamic Trash paths per profile
        cfg = config_manager.load_config()

        for p, t in self.threads.items():
            state_icon = '🔴' if t.err else '🔵' if t.run_state else '⚪' if t.last == 'Never' else '🟢'
            item = Gtk.MenuItem(label=f"{state_icon} {p.upper():<12}")
            sub = Gtk.Menu()
            
            kill_lbl = "Destroy Process" if t.kill_clicks > 0 else "Abandon Process"
            
            def handle_kill(_, t_obj=t):
                rclone_runner.kill_process(t_obj.proc, force=(t_obj.kill_clicks > 0))
                t_obj.kill_clicks += 1
                self.update_menu()
            
            for lbl, cb, sens in[("Sync Now", lambda _, x=p: self.threads[x].trigger_sync(), not t.run_state),
                                  (kill_lbl, handle_kill, t.run_state),
                                  ("Live Output", lambda _, x=p: self.show_live_output(x), True)]:
                mi = Gtk.MenuItem(label=lbl); mi.connect('activate', cb); mi.set_sensitive(sens); sub.append(mi)
            sub.append(Gtk.SeparatorMenuItem())
            
            # --- DYNAMIC TRASH RESOLVER ---
            p_cfg = cfg.get('remote_configs', {}).get(p, {})
            l_path = cfg.get('local_paths', {}).get(p, "")
            t_name = p_cfg.get('--backup-dir1', workbench_blueprint.TRASH_LOCAL_NAME)
            trash_path = t_name if os.path.isabs(t_name) else os.path.join(l_path, t_name)
            
            i_trash = create_icon_item("user-trash-symbolic", "Open Local Trash")
            if os.path.exists(trash_path):
                i_trash.connect("activate", lambda _, path=trash_path: subprocess.Popen(['xdg-open', path]))
                i_trash.set_sensitive(True)
            else:
                i_trash.set_sensitive(False) # Gray it out if no trash exists!
            sub.append(i_trash)
            # ------------------------------
            
            if t.err:
                s_icon, s_text = "dialog-error-symbolic", "ERROR"
            elif t.run_state:
                s_icon, s_text = "view-refresh-symbolic", "Syncing..."
            else:
                s_icon, s_text = "media-playback-start-symbolic", "Ready"
                
            i_status = create_icon_item(s_icon, f"Status: {s_text}")
            i_status.set_sensitive(False)
            sub.append(i_status)
            
            i_last = create_icon_item("document-open-recent-symbolic", f"Last Run: {format_relative(t.last)}")
            i_last.set_sensitive(False)
            sub.append(i_last)
            
            item.set_submenu(sub); m.append(item)
            
        m.append(Gtk.SeparatorMenuItem())
        for lbl, cb in[("Inventory Workbench", lambda _: self.open_workbench()), ("Quit Application", self.on_quit)]:
            mi = Gtk.MenuItem(label=lbl); mi.get_style_context().add_class("menu-action"); mi.connect('activate', cb); m.append(mi)
        m.show_all(); self.ind.set_menu(m)

    def open_workbench(self):
        if not self.workbench: self.workbench = workbench_ui.InventoryWorkbench(list(self.threads.keys()))
        if hasattr(self.workbench, 'focus_workbench'): self.workbench.focus_workbench()
        self.workbench.show_all(); self.workbench.present(); return self.workbench

    def show_live_output(self, profile):
        if hasattr(wb := self.open_workbench(), 'focus_profile'): wb.focus_profile(profile)

    def on_quit(self, _):
        [rclone_runner.kill_process(t.proc, force=True) for t in self.threads.values() if t.proc]
        if self.workbench:[log_formatter.stop_live_feed(p) for p in self.threads]
        Gtk.main_quit()

if __name__ == "__main__": RCloneWorkbenchApp(); Gtk.main()