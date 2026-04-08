import os, signal, threading, time, datetime, configparser, gi

gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk, AppIndicator3, Notify, GLib

from src import workbench_blueprint, config_manager, workbench_ui, rclone_runner, log_formatter

Notify.init("RClone Tray")

def send_notification(title, message, is_error=False):
    n = Notify.Notification.new(title, message, "dialog-error" if is_error else "emblem-synchronizing")
    n.show()

class SyncThread(threading.Thread):
    """Background thread to handle Rclone execution without blocking the GTK UI."""
    def __init__(self, profile, path, app):
        super().__init__(daemon=True)
        self.profile = profile
        self.path = path
        self.app = app
        self.req = False
        self.run_state = False
        self.err = False
        self.last = "Never"
        self.proc = None

    def trigger_sync(self):
        if not self.run_state:
            self.req = True

    def run(self):
        while True:
            if self.req:
                self.req, self.run_state, self.err = False, True, False
                GLib.idle_add(self.app.update_menu)
                
                if getattr(self.app, 'workbench', None) and hasattr(self.app.workbench, 'set_status'):
                    self.app.workbench.set_status(self.profile, True)
                
                global_cfg = config_manager.load_config()
                
                # Dynamically evaluate the state
                from src import rules_engine
                lookup = rules_engine.get_item_lookup()
                prof_cfg = global_cfg.get('remote_configs', {}).get(self.profile, {})
                active_keys = [k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v)]
                fk, fv, _ = rules_engine.evaluate_state(active_keys, lookup)
                
                run_state = prof_cfg.copy()
                run_state.update(fv)
                for k in fk:
                    if k not in run_state: run_state[k] = True
                
                # Execute Python hooks (e.g. inject dynamic timestamps)
                from src import smart_logic_hooks as hooks
                for k in fk:
                    base_k = k.split('__uid_')[0] if '__uid_' in k else k
                    if base_k in lookup and getattr(lookup[base_k], 'python_hook', None):
                        hook_func = getattr(hooks, lookup[base_k].python_hook, None)
                        if hook_func:
                            run_state = hook_func(self.profile, self.path, f'{self.profile}:', run_state)
                
                args = ['bisync', self.path, f'{self.profile}:']
                args.extend(config_manager.build_base_args(self.profile, global_cfg, run_state))
                
                res = rclone_runner.run_sync_session(self.profile, args)
                self.proc = res.get("process")
                self.last = datetime.datetime.now().strftime("%H:%M")
                
                if res.get("success"): 
                    send_notification("Complete", f"{self.profile.upper()} :: Bisync Complete!")
                    if getattr(self.app, 'workbench', None) and hasattr(self.app.workbench, 'post_sync_cleanup'):
                        self.app.workbench.post_sync_cleanup(self.profile)
                else: 
                    self.err = True
                    send_notification("Failed", f"{self.profile.upper()} :: Error Encountered!", True)
                
                self.run_state, self.proc = False, None
                
                if getattr(self.app, 'workbench', None) and hasattr(self.app.workbench, 'set_status'):
                    self.app.workbench.set_status(self.profile, False)
                
                GLib.idle_add(self.app.update_menu)
            else: 
                time.sleep(1)

class RCloneWorkbenchApp:
    def __init__(self):
        print("Initializing RClone Workbench Tray App...")
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        self.icon_name = "network-server"
        self.threads = {}
        self.workbench = None

        # Load standard rclone config to discover remotes
        self.rc = configparser.ConfigParser()
        if not os.path.exists(workbench_blueprint.RCLONE_CONF_PATH):
            send_notification("Error", "rclone.conf not found. Ensure rclone is configured.", True)
            return

        self.rc.read(workbench_blueprint.RCLONE_CONF_PATH)
        remotes = self.rc.sections()
        
        if not remotes:
            send_notification("Error", "No remotes found in rclone.conf.", True)
            return

        # Setup the AppIndicator (System Tray)
        self.ind = AppIndicator3.Indicator.new(
            "rclone_workbench_manager",
            self.icon_name,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        # Load profile configurations and start sync threads
        cfg = config_manager.load_config()
        for remote in remotes:
            saved_path = cfg.get('local_paths', {}).get(remote)
            local_path = saved_path if saved_path else f"/mnt/DataDrive/{remote}"
            
            # Ensure the config_manager populates default schema tools if it's a new remote
            config_manager.ensure_profile_exists(remote)
            
            thread = SyncThread(remote, local_path, self)
            self.threads[remote] = thread
            thread.start()

        # Build initial menu
        self.update_menu()

    def update_menu(self):
        """Rebuilds the tray menu dynamically based on thread states."""
        menu = Gtk.Menu()
        
        for profile, thread in self.threads.items():
            status_icon = "🔴" if thread.err else ("🔵" if thread.run_state else ("⚪" if thread.last == "Never" else "🟢"))
            item = Gtk.MenuItem(label=f"{status_icon} {profile.upper():<12}")
            submenu = Gtk.Menu()
            
            # Sync Action
            sync_item = Gtk.MenuItem(label="Sync Now")
            sync_item.set_sensitive(not thread.run_state)
            sync_item.connect('activate', lambda _, p=profile: self.threads[p].trigger_sync())
            submenu.append(sync_item)
            
            # Kill Action
            kill_item = Gtk.MenuItem(label="Kill Process")
            kill_item.set_sensitive(thread.run_state)
            kill_item.connect('activate', lambda _, p=profile: rclone_runner.kill_process(self.threads[p].proc))
            submenu.append(kill_item)
            
            # Live Output (Connects to Workbench UI)
            out_item = Gtk.MenuItem(label="Live Output")
            out_item.connect('activate', lambda _, p=profile: self.show_live_output(p))
            submenu.append(out_item)
            
            submenu.append(Gtk.SeparatorMenuItem())
            
            # Status Display
            status_text = "⚠️ ERR" if thread.err else ("Syncing" if thread.run_state else "Ready")
            info = Gtk.MenuItem(label=f"Status: {status_text:<10} | Last: {thread.last}")
            info.set_sensitive(False)
            submenu.append(info)
            
            item.set_submenu(submenu)
            menu.append(item)
            
        menu.append(Gtk.SeparatorMenuItem())
        
        # Workbench Action
        item_config = Gtk.MenuItem(label="Inventory Workbench")
        item_config.get_style_context().add_class("menu-action")
        item_config.connect('activate', lambda _: self.open_workbench())
        menu.append(item_config)
        
        # Quit Action
        item_quit = Gtk.MenuItem(label="Quit Application")
        item_quit.get_style_context().add_class("menu-action")
        item_quit.connect('activate', self.on_quit)
        menu.append(item_quit)
        
        menu.show_all()
        self.ind.set_menu(menu)

    def open_workbench(self):
        """Spawns or brings the GTK Workbench to the foreground."""
        if not self.workbench:
            profile_list = list(self.threads.keys())
            self.workbench = workbench_ui.InventoryWorkbench(profile_list)
        
        # Ensure the UI jumps to the Inventory page if opened from the general tray button
        if hasattr(self.workbench, 'focus_workbench'):
            self.workbench.focus_workbench()
            
        self.workbench.show_all()
        self.workbench.present()
        return self.workbench

    def show_live_output(self, profile):
        """Opens the workbench and instructs it to jump to the Live Output tab."""
        wb = self.open_workbench()
        if hasattr(wb, 'focus_profile'):
            wb.focus_profile(profile)

    def on_quit(self, _):
        """Cleanup handler before exiting GTK loop."""
        for thread in self.threads.values():
            if thread.proc:
                rclone_runner.kill_process(thread.proc)
        
        if self.workbench:
            for profile in self.threads.keys():
                log_formatter.stop_live_feed(profile)
                
        Gtk.main_quit()

if __name__ == "__main__":
    app = RCloneWorkbenchApp()
    Gtk.main()