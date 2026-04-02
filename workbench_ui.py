import gi
import os
import subprocess
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import config_manager
import rules_engine
import log_formatter
import workbench_blueprint as blueprint

class LiveOutputPanel:
    """Manages the nested profile logs with advanced UI controls."""
    def __init__(self, remotes):
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.notebook = Gtk.Notebook()
        self.notebook.set_tab_pos(Gtk.PositionType.LEFT)
        self.container.pack_start(self.notebook, True, True, 0)

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

            self.notebook.append_page(vbox, Gtk.Label(label=profile.upper()))
            
            self.tabs[profile] = {
                'vbox': vbox, 'status': status_lbl, 'buffer': tv.get_buffer(), 'sw': sw
            }
            log_formatter.start_live_feed(profile, lambda a, p=profile: GLib.idle_add(self.update_logs, p, a))

    def on_open_log_dir(self, profile):
        """Opens the system file manager to the logs directory."""
        subprocess.Popen(['xdg-open', blueprint.LOG_DIR])

    def on_delete_log(self, profile):
        """Deletes the log file and clears the buffer."""
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
            self.notebook.set_current_page(self.notebook.page_num(self.tabs[profile]['vbox']))


class InventoryWorkbench:
    def __init__(self, profiles):
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
        self.main_stack = self.builder.get_object("main_stack") # Now a Stack, not Notebook
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

        # 2. Connect Signals
        self.window.connect("delete-event", self.on_hide)
        self.profile_combo.connect("changed", self.on_profile_changed)
        self.path_entry.connect("changed", self.set_dirty)
        self.search_entry.connect("search-changed", lambda _: self.refresh_inventory())
        self.category_combo.connect("changed", lambda _: self.refresh_inventory())
        
        self.builder.get_object("btn_toggle_smart").connect('clicked', lambda _: self.smart_revealer.set_reveal_child(not self.smart_revealer.get_reveal_child()))
        self.builder.get_object("btn_toggle_preview").connect('clicked', lambda _: self.preview_revealer.set_reveal_child(not self.preview_revealer.get_reveal_child()))
        self.builder.get_object("btn_reset").connect("clicked", self.on_reset_clicked)
        self.builder.get_object("btn_apply").connect("clicked", self.save_config)
        self.builder.get_object("btn_browse").connect("clicked", self.on_browse)

        for r in self.remotes: self.profile_combo.append_text(r)
        self.profile_combo.set_active(0)
        
        self.category_combo.append_text("All Categories")
        for cat in blueprint.CONFIG_SCHEMA.keys(): self.category_combo.append_text(cat)
        self.category_combo.set_active(0)

        live_output_hook = self.builder.get_object("live_output_hook")
        self.output_panel = LiveOutputPanel(self.remotes)
        live_output_hook.pack_start(self.output_panel.container, True, True, 0)

        self.load_data()

    def _setup_minimal_css(self):
        css = b".chip { border-radius: 999px; padding: 4px 10px; margin: 2px; } .canvas-card { margin-bottom: 6px; padding: 10px; }"
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # --- API ---
    def show_all(self): self.window.show_all()
    def present(self): self.window.present()
    def on_hide(self, *args):
        self.window.hide()
        return True

    def focus_profile(self, profile):
        self.show_all()
        self.present()
        # Navigate the Stack to page1 (Live Outputs)
        self.main_stack.set_visible_child_name("page1")
        self.output_panel.focus_profile(profile)

    def set_status(self, profile, is_running):
        self.output_panel.tabs[profile]['status'].set_text("● SYNCING..." if is_running else "● IDLE")

    # --- Logic ---
    def set_dirty(self, *args):
        if self._updating_rules: return
        self.is_dirty = True
        self.status_label.set_markup("<span foreground='#e67e22'><b>[✗] Unsaved</b></span>")
        self.update_preview()

    def on_profile_changed(self, combo): self.load_data()
    
    def on_reset_clicked(self, btn):
        self.global_cfg = config_manager.load_config()
        self.load_data()
        self.set_dirty()

    def on_browse(self, btn):
        dialog = Gtk.FileChooserDialog(title="Select Local Directory", parent=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.path_entry.set_text(dialog.get_filename())
            self.set_dirty()
        dialog.destroy()

    def equip_logic(self, key):
        keys = [r.key for r in self.can_list.get_children()] + [key]
        fk, fv, lk = rules_engine.evaluate_state(keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk)
        self.set_dirty()

    def unequip_logic(self, row):
        keys = [r.key for r in self.can_list.get_children() if r.key != row.key]
        fk, fv, lk = rules_engine.evaluate_state(keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk)
        self.set_dirty()

    def on_smart_preset_toggled(self, btn, key):
        if self._updating_rules: return
        current_keys = [r.key for r in self.can_list.get_children() if r.key not in self.smart_keys]
        if btn.get_active(): current_keys.append(key)
        fk, fv, lk = rules_engine.evaluate_state(current_keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk)
        self.set_dirty()

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
            r.is_locked = is_locked
            r.set_sensitive(not is_locked) 
            
            card_box = r.get_child()
            drop_btn = card_box.get_children()[0].get_children()[-1]
            if is_locked: drop_btn.hide()
            elif str(self.items_lookup[k].get('default_equipped')) != "0": drop_btn.show()

        for k, btn in self.smart_toggles.items():
            btn.set_active(k in target_keys)

        self._updating_rules = False
        self.refresh_inventory()
        self.update_preview()

    def update_preview(self):
        profile = self.profile_combo.get_active_text()
        live_state = {r.key: self.get_row_value(r) for r in self.can_list.get_children()}
        live_state.update({k: btn.get_active() for k, btn in self.smart_toggles.items()})
        
        try:
            args = config_manager.build_base_args(profile, self.global_cfg, live_state)
            cmd_str = f"rclone {' '.join(args)} {self.path_entry.get_text() or '[LOCAL_PATH]'} {profile}:"
            self.preview_view.get_buffer().set_text(cmd_str)
            self.builder.get_object("btn_apply").set_sensitive(True)
        except Exception as e:
            self.preview_view.get_buffer().set_text(f"PREVIEW ERROR:\n{str(e)}")
            self.builder.get_object("btn_apply").set_sensitive(False)

    def refresh_inventory(self):
        for c in self.inventory_container.get_children(): self.inventory_container.remove(c)
        for c in self.smart_container.get_children(): self.smart_container.remove(c)

        search = self.search_entry.get_text().lower()
        active_cat = self.category_combo.get_active_text()
        excluded = {r.key for r in self.can_list.get_children()}

        for i in blueprint.SMART_SCHEMA.get("Smart Automations", []):
            self.smart_container.pack_start(self.create_smart_toggle(i), False, False, 0)

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

    def load_data(self):
        profile = self.profile_combo.get_active_text()
        if not profile: return
        
        self.path_entry.set_text(self.global_cfg.get('local_paths', {}).get(profile, ""))
        prof_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {})
        
        active_keys = [k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v)]
        fk, merged, lk = rules_engine.evaluate_state(active_keys, self.items_lookup)
        
        for k in fk:
            if k not in merged and k in prof_cfg: merged[k] = prof_cfg[k]
                
        self._apply_new_state(fk, merged, lk)
        self.is_dirty = False
        self.update_preview()

    def save_config(self, btn):
        profile = self.profile_combo.get_active_text()
        new_cfg = {r.key: self.get_row_value(r) for r in self.can_list.get_children()}
        new_cfg.update({k: btn.get_active() for k, btn in self.smart_toggles.items()})
        
        self.global_cfg.setdefault('remote_configs', {})[profile] = new_cfg
        self.global_cfg.setdefault('local_paths', {})[profile] = self.path_entry.get_text()
        config_manager.save_config(self.global_cfg)
        
        self.is_dirty = False
        self.status_label.set_markup("<span foreground='#2ecc71'><b>[✓] Applied</b></span>")
        GLib.timeout_add_seconds(3, lambda: self.status_label.set_label("") or False)

    # --- Widget Generators ---
    def create_smart_toggle(self, item):
        """Creates an isolated toggle button for Smart Presets with a symbolic icon."""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # Left side: Text
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.pack_start(Gtk.Label(label=f"<b>{item['label']}</b>", use_markup=True, xalign=0), False, False, 0)
        desc = Gtk.Label(label=item.get('desc', ''), xalign=0)
        desc.set_line_wrap(True); desc.set_opacity(0.7)
        vbox.pack_start(desc, False, False, 0)
        hbox.pack_start(vbox, True, True, 0)

        # Right side: Symbolic Toggle Button
        toggle = Gtk.ToggleButton()
        icon = Gtk.Image.new_from_icon_name("system-run-symbolic", Gtk.IconSize.BUTTON)
        toggle.add(icon)
        toggle.set_valign(Gtk.Align.CENTER) # Keeps the button small
        toggle.connect('toggled', self.on_smart_preset_toggled, item['key'])
        self.smart_toggles[item['key']] = toggle
        
        hbox.pack_end(toggle, False, False, 0)
        return hbox

    def create_chip(self, key):
        i = self.items_lookup[key]
        btn = Gtk.Button(label=i['label'])
        btn.get_style_context().add_class("chip")
        btn.connect("clicked", lambda _: self.equip_logic(key))
        btn.set_tooltip_text(i.get('desc', ""))
        return btn

    def create_canvas_card(self, key, current_val=None, is_locked=False):
        i = self.items_lookup.get(key)
        row = Gtk.ListBoxRow()
        row.key = key; row.is_locked = is_locked

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        card.get_style_context().add_class("canvas-card")

        top = Gtk.Box(spacing=10)
        top.pack_start(Gtk.Label(label=f"<b>{i['label']}</b>", use_markup=True, xalign=0), True, True, 0)
        
        drop_btn = Gtk.Button(label="✕")
        drop_btn.connect("clicked", lambda _: self.unequip_logic(row))
        top.pack_end(drop_btn, False, False, 0)
        card.pack_start(top, False, False, 0)

        row.input_widget = None
        if i.get('type') == 'entry':
            row.input_widget = Gtk.Entry(text=str(current_val or ""))
            row.input_widget.connect("changed", self.set_dirty)
            card.pack_start(row.input_widget, False, False, 0)
        elif i.get('type') == 'combo':
            row.input_widget = Gtk.ComboBoxText()
            opts = i.get('options', [])
            for opt in opts: row.input_widget.append_text(opt)
            if current_val in opts: row.input_widget.set_active(opts.index(current_val))
            row.input_widget.connect("changed", self.set_dirty)
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

    def set_row_value(self, row, value):
        i = self.items_lookup[row.key]
        if i.get('type') == 'entry': row.input_widget.set_text(str(value))
        elif i.get('type') == 'combo':
            opts = i.get('options', [])
            if str(value) in opts: row.input_widget.set_active(opts.index(str(value)))