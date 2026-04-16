#usr/bin/env python3
import gi, os, signal, threading, time, datetime, configparser
gi.require_version('Gtk', '3.0'); gi.require_version('AppIndicator3', '0.1'); gi.require_version('Notify', '0.7')
from gi.repository import Gtk, GLib, AppIndicator3, Notify
from src import workbench_blueprint, config_manager, workbench_ui, rclone_runner, log_formatter, rules_engine, smart_engine

Notify.init("RClone Tray")
def notify(title, msg, err=False): Notify.Notification.new(title, msg, "dialog-error" if err else "emblem-synchronizing").show()

class SyncThread(threading.Thread):
    def __init__(self, profile, path, app):
        super().__init__(daemon=True)
        self.profile, self.path, self.app = profile, path, app
        self.req, self.run_state, self.err, self.last, self.proc = False, False, False, "Never", None

    def trigger_sync(self): self.req = True

    def run(self):
        while True:
            if not self.req: 
                time.sleep(1)
                continue
                
            self.req, self.run_state, self.err = False, True, False
            GLib.idle_add(self.app.update_menu)
            if self.app.workbench: 
                self.app.workbench.set_status(self.profile, True)
            
            # 1. Load configuration and lookup
            cfg = config_manager.load_config()
            lookup = rules_engine.get_item_lookup()
            live_state = cfg.get('remote_configs', {}).get(self.profile, {}).copy()
            local_path = cfg.get('local_paths', {}).get(self.profile, '')
            remote_path = live_state.get('remote_path', '')
            
            # 2. POWERING B: Run the Audit
            live_state = smart_engine.audit_resync_environment(
                self.profile, local_path, remote_path, live_state
            )
            
            # 3. TEST C RESOLUTION: Check for Blockers
            audit_errors = [v for k, v in live_state.items() if k.startswith('_AUDIT_ERROR')]
            
            if audit_errors:
                self.err = True
                self.run_state = False
                self.last = "Blocked"
                error_msg = audit_errors[0]
                GLib.idle_add(notify, f"Sync Blocked: {self.profile}", error_msg, True)
                GLib.idle_add(self.app.update_menu)
                if self.app.workbench: 
                    self.app.workbench.set_status(self.profile, False)
                continue # Abort the sync before rclone even starts

            # 4. Preparation side-effects (Dynamic Trash Bin timestamps)
            if hasattr(smart_engine, 'setup_trash_bins'):
                live_state = smart_engine.setup_trash_bins(self.profile, local_path, remote_path, live_state)
                
            # 5. Execution
            args = config_manager.build_base_args(self.profile, cfg, live_state)
            res = rclone_runner.run_sync_session(self.profile, args)

            # 6. Post-Sync Wrap-up & UI Reset
            self.run_state = False
            self.err = not res.get("success", False)
            self.last = datetime.datetime.now().strftime("%H:%M:%S")
            self.proc = None
            
            if self.app.workbench:
                self.app.workbench.set_status(self.profile, False)
                # Cleanup one-time flags (like --resync) after success
                if not self.err:
                    self.app.workbench.post_sync_cleanup(self.profile)
                    
                    # Save Filter Hash post-sync for Prerequisite 2
                    import hashlib
                    f_txt = "\n".join([v for k, v in live_state.items() if k.startswith('filter') and isinstance(v, str)])
                    if f_txt:
                        tracker = os.path.join(workbench_blueprint.APP_DIR, f"{self.profile}_filter_state.md5")
                        try:
                            with open(tracker, 'w') as f: f.write(hashlib.md5(f_txt.encode()).hexdigest())
                        except Exception: pass
            
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
        for p, t in self.threads.items():
            item = Gtk.MenuItem(label=f"{'🔴' if t.err else '🔵' if t.run_state else '⚪' if t.last == 'Never' else '🟢'} {p.upper():<12}")
            sub = Gtk.Menu()
            for lbl, cb, sens in [("Sync Now", lambda _, x=p: self.threads[x].trigger_sync(), not t.run_state),
                                  ("Kill Process", lambda _, x=p: rclone_runner.kill_process(self.threads[x].proc), t.run_state),
                                  ("Live Output", lambda _, x=p: self.show_live_output(x), True)]:
                mi = Gtk.MenuItem(label=lbl); mi.connect('activate', cb); mi.set_sensitive(sens); sub.append(mi)
            sub.append(Gtk.SeparatorMenuItem())
            i = Gtk.MenuItem(label=f"Status: {'⚠️ ERR' if t.err else 'Syncing' if t.run_state else 'Ready':<10} | Last: {t.last}")
            i.set_sensitive(False); sub.append(i); item.set_submenu(sub); m.append(item)
            
        m.append(Gtk.SeparatorMenuItem())
        for lbl, cb in [("Inventory Workbench", lambda _: self.open_workbench()), ("Quit Application", self.on_quit)]:
            mi = Gtk.MenuItem(label=lbl); mi.get_style_context().add_class("menu-action"); mi.connect('activate', cb); m.append(mi)
        m.show_all(); self.ind.set_menu(m)

    def open_workbench(self):
        if not self.workbench: self.workbench = workbench_ui.InventoryWorkbench(list(self.threads.keys()))
        if hasattr(self.workbench, 'focus_workbench'): self.workbench.focus_workbench()
        self.workbench.show_all(); self.workbench.present(); return self.workbench

    def show_live_output(self, profile):
        if hasattr(wb := self.open_workbench(), 'focus_profile'): wb.focus_profile(profile)

    def on_quit(self, _):
        [rclone_runner.kill_process(t.proc) for t in self.threads.values() if t.proc]
        if self.workbench: [log_formatter.stop_live_feed(p) for p in self.threads]
        Gtk.main_quit()

if __name__ == "__main__": RCloneWorkbenchApp(); Gtk.main()