# workbench_ui.py
import gi
import os
import subprocess
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from src import config_manager, rules_engine, log_formatter, smart_automations
import src.workbench_blueprint as blueprint

class LiveOutputPanel:
    """Manages profile logs with side tabs and utility controls."""
    def __init__(self, remotes):
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.notebook = Gtk.Notebook()
        self.notebook.set_tab_pos(Gtk.PositionType.LEFT)
        self.container.pack_start(self.notebook, True, True, 0)

        self.change_callback = None
        self.tabs = {}
        
        for profile in remotes:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            vbox.set_border_width(8)
            
            # --- The Action Header ---
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            status_lbl = Gtk.Label(label="● IDLE", xalign=0)
            header_box.pack_start(status_lbl, True, True, 0)
            
            # Button: Find Log File
            btn_open = Gtk.Button(tooltip_text="Open Log Directory")
            btn_open.add(Gtk.Image.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON))
            btn_open.connect("clicked", lambda _, p=profile: self.on_open_log_dir(p))
            header_box.pack_end(btn_open, False, False, 0)

            # Button: Delete Log File
            btn_del = Gtk.Button(tooltip_text="Delete Physical Log File")
            btn_del.add(Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON))
            btn_del.connect("clicked", lambda _, p=profile: self.on_delete_log(p))
            header_box.pack_end(btn_del, False, False, 0)

            # Button: Clear Interface
            btn_clear = Gtk.Button(tooltip_text="Clear Display")
            btn_clear.add(Gtk.Image.new_from_icon_name("edit-clear-symbolic", Gtk.IconSize.BUTTON))
            btn_clear.connect("clicked", lambda _, p=profile: self.tabs[p]['buffer'].set_text(""))
            header_box.pack_end(btn_clear, False, False, 0)
            
            vbox.pack_start(header_box, False, False, 0)

            # --- The Log View ---
            tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            tv.set_monospace(True)
            sw = Gtk.ScrolledWindow()
            sw.set_shadow_type(Gtk.ShadowType.IN)
            sw.add(tv)
            vbox.pack_start(sw, True, True, 0)

            label = Gtk.Label(label=profile.upper())
            self.notebook.append_page(vbox, label)
            
            self.tabs[profile] = {
                'vbox': vbox, 'status': status_lbl, 'buffer': tv.get_buffer(), 'sw': sw
            }
            log_formatter.start_live_feed(profile, lambda a, p=profile: GLib.idle_add(self.update_logs, p, a))

        self.notebook.connect("switch-page", self._on_tab_switched)

    def _on_tab_switched(self, notebook, page, page_num):
        if self.change_callback:
            label_text = notebook.get_tab_label(page).get_text().lower()
            self.change_callback(label_text)

    def on_open_log_dir(self, profile):
        if not os.path.exists(blueprint.LOG_DIR): os.makedirs(blueprint.LOG_DIR)
        subprocess.Popen(['xdg-open', blueprint.LOG_DIR])

    def on_delete_log(self, profile):
        log_path = os.path.join(blueprint.LOG_DIR, f"{profile}_sync.jsonl")
        if os.path.exists(log_path):
            try: os.remove(log_path)
            except OSError: pass
        self.tabs[profile]['buffer'].set_text("[SYSTEM] Log file deleted.\n")

    def update_logs(self, profile, actions):
        tab = self.tabs.get(profile)
        if not tab: return False
        for key, data in actions:
            if key == "log":
                tab['buffer'].insert(tab['buffer'].get_end_iter(), str(data))
                adj = tab['sw'].get_vadjustment()
                adj.set_value(adj.get_upper() - adj.get_page_size())
            elif key == "stats":
                msg = data.get("msg", "Syncing...") if isinstance(data, dict) else str(data)
                tab['status'].set_text(f"● {msg}")
        return False

    def focus_profile(self, profile):
        if profile in self.tabs:
            page_num = self.notebook.page_num(self.tabs[profile]['vbox'])
            self.notebook.set_current_page(page_num)

class InventoryWorkbench:
    def __init__(self, profiles):# --- Schema Linter Execution ---
        # Fails fast in the terminal if the blueprint has typos or missing dependencies
        rules_engine.validate_blueprint()
        
        self.remotes = profiles
        self.global_cfg = config_manager.load_config()
        self.items_lookup = rules_engine.get_item_lookup()
        self.smart_keys = rules_engine.get_smart_keys()
        
        self.is_dirty = False
        self._updating_rules = False
        self.smart_toggles = {}

        # 1. Load XML
        self.builder = Gtk.Builder()
        glade_path = os.path.join(os.path.dirname(__file__), "workbench.glade")
        self.builder.add_from_file(glade_path)

        self.window = self.builder.get_object("main_window")
        self.main_stack = self.builder.get_object("main_stack")
        self.profile_combo = self.builder.get_object("profile_combo")
        self.path_entry = self.builder.get_object("path_entry")
        
        self.smart_container = self.builder.get_object("smart_container")
        self.inventory_container = self.builder.get_object("inventory_container")
        self.can_list = self.builder.get_object("canvas_list")
        
        self.smart_revealer = self.builder.get_object("smart_revealer")
        self.preview_revealer = self.builder.get_object("preview_revealer")
        self.preview_view = self.builder.get_object("preview_view")
        
        self.search_entry = self.builder.get_object("search_entry")
        self.category_combo = self.builder.get_object("category_combo")
        self.status_label = self.builder.get_object("status_label")

        self._setup_minimal_css()
        self.setup_smart_presets()

        # 2. Connect Signals
        self.window.connect("delete-event", self.on_hide)
        self.profile_combo.connect("changed", self.on_profile_changed)
        self.path_entry.connect("changed", self.check_dirty)
        self.search_entry.connect("search-changed", lambda _: self.refresh_inventory())
        self.category_combo.connect("changed", lambda _: self.refresh_inventory())
        
        self.builder.get_object("btn_toggle_smart").connect('clicked', lambda _: self.smart_revealer.set_reveal_child(not self.smart_revealer.get_reveal_child()))
        self.builder.get_object("btn_toggle_preview").connect('clicked', lambda _: self.preview_revealer.set_reveal_child(not self.preview_revealer.get_reveal_child()))
        self.builder.get_object("btn_reset").connect("clicked", self.on_reset_clicked)
        self.builder.get_object("btn_apply").connect("clicked", self.save_config)
        self.builder.get_object("btn_browse").connect("clicked", self.on_browse)

        live_output_hook = self.builder.get_object("live_output_hook")
        self.output_panel = LiveOutputPanel(self.remotes)
        self.output_panel.change_callback = self.sync_ui_to_log_tab
        live_output_hook.pack_start(self.output_panel.container, True, True, 0)
        
        self.category_combo.append_text("All Categories")
        for cat in blueprint.CONFIG_SCHEMA.keys(): self.category_combo.append_text(cat)
        self.category_combo.set_active(0)

        for r in self.remotes: self.profile_combo.append_text(r)
        self.profile_combo.set_active(0)

    def _setup_minimal_css(self):
        css = b".chip { border-radius: 999px; padding: 4px 10px; margin: 2px; } .canvas-card { margin-bottom: 6px; padding: 10px; border-bottom: 1px solid alpha(gray, 0.2); }"
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # --- API ---
    def show_all(self): self.window.show_all()
    def present(self): self.window.present()
    def on_hide(self, *args):
        self.window.hide()
        return True

    # --- Initializers ---
    def setup_smart_presets(self):
        """Builds Smart Presets once and dynamically generates CSS for toggle handles."""
        dynamic_css = ""
        for i in blueprint.SMART_SCHEMA.get("Smart Automations", []):
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            hbox.set_tooltip_text(i.get('desc', ''))
            hbox.set_margin_start(8); hbox.set_margin_end(8)

            color = i.get('color', '#3498db')
            lbl = Gtk.Label(xalign=0)
            lbl.set_markup(f"<span foreground='{color}'><b>{i['label']}</b></span>")
            hbox.pack_start(lbl, True, True, 0)

            switch = Gtk.Switch()
            switch.set_valign(Gtk.Align.CENTER)
            
            # Create a unique CSS name to style just this switch's background
            css_name = f"smart_switch_{i['key']}"
            switch.set_name(css_name)
            dynamic_css += f"#{css_name}:checked {{ background-image: none; background-color: {color}; }}\n"
            
            switch.connect('notify::active', self.on_smart_preset_toggled, i['key'])
            
            self.smart_toggles[i['key']] = switch
            hbox.pack_end(switch, False, False, 0)
            self.smart_container.pack_start(hbox, False, False, 0)

        # Apply the colored toggle CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(dynamic_css.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # --- Interlinking & Environment Scanning Logic ---
    def on_profile_changed(self, combo):
        profile = combo.get_active_text()
        if not profile: return
        self.load_data()
        self.output_panel.focus_profile(profile)

    def sync_ui_to_log_tab(self, profile_name):
        self.profile_combo.handler_block_by_func(self.on_profile_changed)
        model = self.profile_combo.get_model()
        for i, row in enumerate(model):
            if row[0].lower() == profile_name.lower():
                self.profile_combo.set_active(i)
                break
        self.load_data()
        self.profile_combo.handler_unblock_by_func(self.on_profile_changed)

    def on_browse(self, btn):
        dialog = Gtk.FileChooserDialog(title="Select Local Directory", parent=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.path_entry.set_text(dialog.get_filename())
            self.check_dirty()
        dialog.destroy()

    # --- State Management & Validation ---
    def check_dirty(self, *args):
        if self._updating_rules: return
        profile = self.profile_combo.get_active_text()
        if not profile: return

        saved_path = self.global_cfg.get('local_paths', {}).get(profile, "")
        current_path = self.path_entry.get_text()
        saved_remote_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {})
        
        current_remote_cfg = {}
        for row in self.can_list.get_children():
            current_remote_cfg[row.key] = self.get_row_value(row)
        for key, switch in self.smart_toggles.items():
            if switch.get_active(): current_remote_cfg[key] = True

        path_changed = saved_path != current_path
        config_changed = False
        all_keys = set(saved_remote_cfg.keys()) | set(current_remote_cfg.keys())
        for k in all_keys:
            if (saved_remote_cfg.get(k) or False) != (current_remote_cfg.get(k) or False):
                config_changed = True
                break

        self.is_dirty = path_changed or config_changed
        if self.is_dirty:
            self.status_label.set_markup("<span foreground='#e67e22'><b>[✗] Unsaved Changes</b></span>")
        else:
            self.status_label.set_markup("<span foreground='#2ecc71'><b>[✓] Synced to Disk</b></span>")
        
        self.update_preview()

    def on_reset_clicked(self, btn):
        self.global_cfg = config_manager.load_config()
        self.load_data()

    # --- Rules Engine Logic Triggers ---
    def _gather_live_keys(self):
        current_keys = [r.key for r in self.can_list.get_children()]
        for k, btn in self.smart_toggles.items():
            if btn.get_active() and k not in current_keys:
                current_keys.append(k)
        return current_keys

    def equip_logic(self, key):
        keys = self._gather_live_keys()
        if key not in keys: keys.append(key)
        fk, fv, lk = rules_engine.evaluate_state(keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk)
        self.check_dirty()

    def unequip_logic(self, row):
        keys = [k for k in self._gather_live_keys() if k != row.key]
        fk, fv, lk = rules_engine.evaluate_state(keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk)
        self.check_dirty()

    def on_smart_preset_toggled(self, switch, pspec, key):
        if self._updating_rules: return

        # Creation Hook: Inject local folder immediately when Trash Protect is toggled ON
        if key == "preset_safe_trash" and switch.get_active():
            local_path = self.path_entry.get_text()
            if local_path and os.path.exists(local_path):
                try: os.makedirs(os.path.join(local_path, blueprint.TRASH_LOCAL_NAME), exist_ok=True)
                except Exception: pass

        keys = self._gather_live_keys()
        fk, fv, lk = rules_engine.evaluate_state(keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk)
        self.check_dirty()

    # --- Core State Application ---
    def _apply_new_state(self, target_keys, forced_values, locked_keys):
        self._updating_rules = True
        display_keys = {k for k in target_keys if k not in self.smart_keys and k in self.items_lookup}
        current_rows = {r.key: r for r in self.can_list.get_children()}
        
        for k, r in list(current_rows.items()):
            if k not in display_keys:
                self.can_list.remove(r)
                del current_rows[k]
                
        for k in display_keys:
            if k not in current_rows:
                val = forced_values.get(k, self.items_lookup[k].get('default'))
                new_row = self.create_canvas_card(k, val, is_locked=(k in locked_keys))
                self.can_list.add(new_row)
                current_rows[k] = new_row
                
        for k, r in current_rows.items():
            if k in forced_values: self.set_row_value(r, forced_values[k])
            
            is_locked = (k in locked_keys)
            r.set_sensitive(not is_locked)
            card_box = r.get_child()
            drop_btn = card_box.get_children()[0].get_children()[-1]
            if is_locked: drop_btn.hide()
            elif str(self.items_lookup[k].get('default_equipped')) != "0": drop_btn.show()

        for k, btn in self.smart_toggles.items():
            if btn.get_active() != (k in target_keys):
                btn.set_active(k in target_keys)

        self._updating_rules = False
        self.refresh_inventory()

    def refresh_inventory(self):
        """Rebuilds the middle Inventory column based on active filters."""
        for c in self.inventory_container.get_children(): 
            self.inventory_container.remove(c)

        search = self.search_entry.get_text().lower()
        active_cat = self.category_combo.get_active_text()
        excluded = {r.key for r in self.can_list.get_children()}

        for cat, items in blueprint.CONFIG_SCHEMA.items():
            if active_cat != "All Categories" and cat != active_cat: continue
            available = [i for i in items if i['key'] not in excluded and str(i.get('default_equipped')) != "0" 
                         and (not search or search in f"{i.get('label','')} {i.get('key','')} {i.get('desc','')}".lower())]
            if not available: continue
            
            grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            lbl = Gtk.Label(xalign=0); lbl.set_markup(f"<span color='#888' size='small'><b>{cat.upper()}</b></span>")
            grp.pack_start(lbl, False, False, 0)
            
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
            for i in available: flow.add(self.create_chip(i['key']))
            grp.pack_start(flow, False, False, 0)
            self.inventory_container.pack_start(grp, False, False, 0)
            
        self.window.show_all()

    def update_preview(self):
        profile = self.profile_combo.get_active_text()
        live_state = {r.key: self.get_row_value(r) for r in self.can_list.get_children()}
        live_state.update({k: btn.get_active() for k, btn in self.smart_toggles.items()})
        try:
            args = config_manager.build_base_args(profile, self.global_cfg, live_state)
            cmd = f"rclone {' '.join(args)} {self.path_entry.get_text() or '[PATH]'} {profile}:"
            self.preview_view.get_buffer().set_text(cmd)
        except: self.preview_view.get_buffer().set_text("Preview Error")

    def load_data(self):
        """Loads memory state, scans environment, and injects into UI."""
        profile = self.profile_combo.get_active_text()
        if not profile: return

        self._updating_rules = True
        
        local_path = self.global_cfg.get('local_paths', {}).get(profile, "")
        self.path_entry.set_text(local_path)
        prof_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {})
        
        # Pull active keys
        active_keys = [k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v)]
        
        # Scanner Auto-Apply check: If safe master resync is recommended, activate it
        heuristics = smart_automations.scan_environment(local_path, profile)
        for rec in heuristics:
            item = self.items_lookup.get(rec)
            if item and item.get("auto_apply"):
                if rec not in active_keys:
                    active_keys.append(rec)
        
        fk, merged, lk = rules_engine.evaluate_state(active_keys, self.items_lookup)
        
        for k in fk:
            if k not in merged and k in prof_cfg: merged[k] = prof_cfg[k]
                
        self._apply_new_state(fk, merged, lk)
        
        self._updating_rules = False 
        self.check_dirty()

    def save_config(self, btn):
        profile = self.profile_combo.get_active_text()
        if not profile: return

        new_remote_cfg = {}
        for row in self.can_list.get_children():
            new_remote_cfg[row.key] = self.get_row_value(row)
        for k, switch in self.smart_toggles.items():
            if switch.get_active(): new_remote_cfg[k] = True

        self.global_cfg.setdefault('remote_configs', {})[profile] = new_remote_cfg
        self.global_cfg.setdefault('local_paths', {})[profile] = self.path_entry.get_text()
        
        config_manager.save_config(self.global_cfg)
        self.check_dirty()

    # --- Widget Generators ---
    def create_chip(self, key):
        i = self.items_lookup[key]
        color = i.get('color', '#ecf0f1') # Default color if none specified
        lbl = Gtk.Label()
        lbl.set_markup(f"<span foreground='{color}'><b>{i['label']}</b></span>")
        
        btn = Gtk.Button()
        btn.add(lbl)
        btn.get_style_context().add_class("chip")
        btn.connect("clicked", lambda _: self.equip_logic(key))
        return btn

    def create_canvas_card(self, key, val=None, is_locked=False):
        i = self.items_lookup.get(key)
        color = i.get('color', '#ecf0f1')
        
        row = Gtk.ListBoxRow(); row.key = key
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        card.get_style_context().add_class("canvas-card")
        
        top = Gtk.Box(spacing=10)
        # Card header text styled dynamically 
        top.pack_start(Gtk.Label(label=f"<span foreground='{color}'><b>{i['label']}</b></span>", use_markup=True, xalign=0), True, True, 0)
        drop = Gtk.Button(label="✕")
        drop.connect("clicked", lambda _: self.unequip_logic(row))
        top.pack_end(drop, False, False, 0)
        card.pack_start(top, False, False, 0)
        
        row.input_widget = None
        if i.get('type') == 'entry':
            row.input_widget = Gtk.Entry(text=str(val or ""))
            row.input_widget.connect("changed", self.check_dirty)
            card.pack_start(row.input_widget, False, False, 0)
        elif i.get('type') == 'combo':
            row.input_widget = Gtk.ComboBoxText()
            opts = i.get('options', [])
            for opt in opts: row.input_widget.append_text(opt)
            if val in opts: row.input_widget.set_active(opts.index(val))
            row.input_widget.connect("changed", self.check_dirty)
            card.pack_start(row.input_widget, False, False, 0)
            
        row.add(card)
        return row

    def get_row_value(self, row):
        i = self.items_lookup[row.key]
        if i.get('type') == 'check' or not i.get('type'): return True
        if not hasattr(row, 'input_widget') or not row.input_widget: return None
        if i['type'] == 'entry': return row.input_widget.get_text()
        if i['type'] == 'combo': return row.input_widget.get_active_text()
        return None

    def set_row_value(self, row, val):
        i = self.items_lookup[row.key]
        if i.get('type') == 'entry': row.input_widget.set_text(str(val))
        elif i.get('type') == 'combo':
            opts = i.get('options', [])
            if str(val) in opts: row.input_widget.set_active(opts.index(str(val)))
    
    def post_sync_cleanup(self, profile):
        """Called by app.py upon successful 'exit 0' to scrub one_time presets."""
        # Ensure we only affect the currently visible profile if it matches
        is_active_profile = (self.profile_combo.get_active_text() == profile)
        
        prof_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {})
        changed = False
        
        # Strip one-time smart keys
        for i in blueprint.SMART_SCHEMA.get("Smart Automations", []):
            if i.get("lifecycle") == "one_time" and prof_cfg.get(i['key']):
                prof_cfg[i['key']] = False
                changed = True
                
        if changed:
            # Re-evaluate logic without the one_time preset to automatically drop dependencies (like resync)
            active_keys = [k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v)]
            fk, merged, lk = rules_engine.evaluate_state(active_keys, self.items_lookup)
            
            # Save the clean state
            self.global_cfg['remote_configs'][profile] = merged
            config_manager.save_config(self.global_cfg)
            
            # If the user is currently looking at this profile, redraw the UI
            if is_active_profile:
                GLib.idle_add(self.load_data)