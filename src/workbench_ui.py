import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib #type: ignore
from typing import Callable
import os, subprocess, uuid, shlex
from src import config_manager, rules_engine, log_formatter, smart_automations
from src.workbench_blueprint import LOG_DIR, TRASH_LOCAL_NAME, CONFIG_SCHEMA, SMART_SCHEMA

class LiveOutputPanel:
    def __init__(self, remotes):
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.container.get_style_context().add_class("live-output-tab")
        self.notebook = Gtk.Notebook(); self.notebook.get_style_context().add_class("live-output-notebook")
        self.notebook.set_tab_pos(Gtk.PositionType.LEFT); self.container.pack_start(self.notebook, True, True, 0)
        self.change_callback: Callable | None = None; self.tabs = {}
        for profile in remotes:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); vbox.set_border_width(8)
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            status = Gtk.Label(label="● IDLE", xalign=0); status.get_style_context().add_class("status-line")
            header.pack_start(status, True, True, 0)
            def _btn(icon, tip, cb):
                b = Gtk.Button(tooltip_text=tip); b.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON)); b.connect("clicked", cb); return b
            header.pack_end(_btn("view-refresh-symbolic", "Reload Log History", lambda _, p=profile: self.reload_log(p)), False, False, 0)
            header.pack_end(_btn("folder-open-symbolic", "Open Log Directory", lambda _, p=profile: self.on_open_log_dir(p)), False, False, 0)
            header.pack_end(_btn("user-trash-symbolic", "Delete Physical Log File", lambda _, p=profile: self.on_delete_log(p)), False, False, 0)
            header.pack_end(_btn("edit-clear-symbolic", "Clear Display", lambda _, p=profile: self.tabs[p]["buffer"].set_text("")), False, False, 0)
            vbox.pack_start(header, False, False, 0)
            tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            tv.set_monospace(True); tv.get_style_context().add_class("log-view")
            sw = Gtk.ScrolledWindow(); sw.set_shadow_type(Gtk.ShadowType.IN); sw.add(tv); vbox.pack_start(sw, True, True, 0)
            label = Gtk.Label(label=profile.upper()); self.notebook.append_page(vbox, label)
            self.tabs[profile] = {'vbox': vbox, 'status': status, 'buffer': tv.get_buffer(), 'tv': tv, 'sw': sw}
            log_formatter.start_live_feed(profile, lambda a, p=profile: GLib.idle_add(self.update_logs, p, a))
        self.notebook.connect("switch-page", self._on_tab_switched)

    def _on_tab_switched(self, notebook, page, page_num):
        if self.change_callback: self.change_callback(notebook.get_tab_label(page).get_text().lower())

    def focus_profile(self, profile):
        if profile in self.tabs:
            pn = self.notebook.page_num(self.tabs[profile]['vbox'])
            if pn != -1: self.notebook.set_current_page(pn)

    def on_open_log_dir(self, profile):
        if not os.path.exists(LOG_DIR): os.makedirs(LOG_DIR)
        try: subprocess.Popen(['xdg-open', LOG_DIR])
        except Exception: pass

    def on_delete_log(self, profile):
        p = os.path.join(LOG_DIR, f"{profile}_sync.jsonl")
        if os.path.exists(p):
            try: os.remove(p)
            except OSError: pass
        self.tabs[profile]['buffer'].set_text("[SYSTEM] Log file deleted.\n")

    def reload_log(self, profile):
        tab = self.tabs.get(profile)
        if not tab: return
        tab['buffer'].set_text("")
        path = os.path.join(LOG_DIR, f"{profile}_sync.jsonl")
        if os.path.exists(path):
            actions = []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f: actions.extend(log_formatter.format_line(line))
            except Exception: pass
            GLib.idle_add(self.update_logs, profile, actions)

    def set_status(self, profile, is_running):
        tab = self.tabs.get(profile)
        if not tab: return
        GLib.idle_add(tab['status'].set_text, "● Syncing..." if is_running else "● Idle / Finished")

    def update_logs(self, profile, actions):
        tab = self.tabs.get(profile)
        if not tab: return False
        scroll = False
        for key, data in actions:
            if key == "log":
                end = tab['buffer'].get_end_iter(); tab['buffer'].insert(end, str(data)); scroll = True
            elif key == "stats":
                if isinstance(data, dict):
                    msg = data.get("msg")
                    if not msg and "bytes" in data: msg = f"Transferred: {data.get('bytes',0)} | Speed: {data.get('speed',0)}/s"
                else: msg = str(data)
                tab['status'].set_text(f"● {msg or 'Syncing...'}")
        if scroll:
            m = tab['buffer'].create_mark(None, tab['buffer'].get_end_iter(), False)
            tab['tv'].scroll_to_mark(m, 0.05, True, 0, 1)
        return False

class InventoryWorkbench:
    def __init__(self, profiles):
        rules_engine.validate_blueprint()
        self.remotes = profiles
        self.global_cfg = config_manager.load_config()
        self.items_lookup = rules_engine.get_item_lookup()
        self.smart_keys = rules_engine.get_smart_keys()
        self.is_dirty = False; self._updating_rules = False; self.smart_toggles = {}
        self.builder = Gtk.Builder(); self.builder.add_from_file(os.path.join(os.path.dirname(__file__), "workbench.glade"))
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
        self.apply_btn = self.builder.get_object("btn_apply")
        self.search_entry = self.builder.get_object("search_entry")
        self.category_combo = self.builder.get_object("category_combo")
        self.status_label = self.builder.get_object("status_label")
        self._setup_minimal_css(); self.setup_smart_presets()
        self.window.connect("delete-event", self.on_hide)
        self.profile_combo.connect("changed", self.on_profile_changed)
        self.path_entry.connect("changed", self.check_dirty)
        self.search_entry.connect("search-changed", lambda _: self.refresh_inventory())
        self.category_combo.connect("changed", lambda _: self.refresh_inventory())
        self.builder.get_object("btn_toggle_smart").connect('clicked', lambda _: self.smart_revealer.set_reveal_child(not self.smart_revealer.get_reveal_child()))
        self.builder.get_object("btn_toggle_preview").connect('clicked', lambda _: self.preview_revealer.set_reveal_child(not self.preview_revealer.get_reveal_child()))
        self.builder.get_object("btn_reset").connect("clicked", self.on_reset_clicked)
        self.apply_btn.connect("clicked", self.save_config)
        self.builder.get_object("btn_browse").connect("clicked", self.on_browse)
        live_output_hook = self.builder.get_object("live_output_hook")
        self.output_panel = LiveOutputPanel(self.remotes); self.output_panel.change_callback = self.sync_ui_to_log_tab
        live_output_hook.pack_start(self.output_panel.container, True, True, 0)
        self.category_combo.append_text("All Categories")
        for cat in CONFIG_SCHEMA.keys(): self.category_combo.append_text(cat)
        self.category_combo.set_active(0)
        for r in self.remotes: self.profile_combo.append_text(r)
        self.profile_combo.set_active(0)

    def focus_profile(self, profile):
        self.main_stack.set_visible_child_name("page1"); self.output_panel.focus_profile(profile)

    def focus_workbench(self):
        self.main_stack.set_visible_child_name("page0")

    def _setup_minimal_css(self):
        css = b".chip { border-radius: 999px; padding: 4px 10px; margin: 2px; } .canvas-card { margin-bottom: 6px; padding: 10px; border-bottom: 1px solid alpha(gray, 0.2); }"
        p = Gtk.CssProvider(); p.load_from_data(css); Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def show_all(self): self.window.show_all()
    def present(self): self.window.present()
    def on_hide(self, *a): self.window.hide(); return True

    def setup_smart_presets(self):
        css = ""
        for i in SMART_SCHEMA.get("Smart Automations", []):
            h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12); h.set_tooltip_text(i.desc); h.set_margin_start(8); h.set_margin_end(8)
            lbl = Gtk.Label(xalign=0); lbl.set_markup(f"<span foreground='{i.color}'><b>{i.label}</b></span>"); h.pack_start(lbl, True, True, 0)
            sw = Gtk.Switch(); sw.set_valign(Gtk.Align.CENTER)
            name = f"smart_switch_{i.key}"; sw.set_name(name); css += f"#{name}:checked {{ background-image: none; background-color: {i.color}; }}\n"
            sw.connect('notify::active', self.on_smart_preset_toggled, i.key)
            self.smart_toggles[i.key] = sw; h.pack_end(sw, False, False, 0); self.smart_container.pack_start(h, False, False, 0)
        p = Gtk.CssProvider(); p.load_from_data(css.encode()); Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def on_profile_changed(self, combo):
        profile = combo.get_active_text()
        if not profile: return
        self.load_data(); self.output_panel.focus_profile(profile)

    def sync_ui_to_log_tab(self, profile_name):
        self.profile_combo.handler_block_by_func(self.on_profile_changed)
        model = self.profile_combo.get_model()
        for i, row in enumerate(model):
            if row[0].lower() == profile_name.lower(): self.profile_combo.set_active(i); break
        self.load_data(); self.profile_combo.handler_unblock_by_func(self.on_profile_changed)

    def on_browse(self, btn):
        d = Gtk.FileChooserDialog(title="Select Local Directory", parent=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if d.run() == Gtk.ResponseType.OK: self.path_entry.set_text(d.get_filename()); self.check_dirty()
        d.destroy()

    def check_dirty(self, *a):
        if self._updating_rules: return
        profile = self.profile_combo.get_active_text()
        if not profile: return
        
        saved_path = self.global_cfg.get('local_paths', {}).get(profile, ""); current_path = self.path_entry.get_text()
        saved_remote_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {})
        current_remote_cfg = {row.key: self.get_row_value(row) for row in self.can_list.get_children()}
        for k, s in self.smart_toggles.items():
            if s.get_active(): current_remote_cfg[k] = True
            
        path_changed = saved_path != current_path
        config_changed = False
        all_keys = set(saved_remote_cfg.keys()) | set(current_remote_cfg.keys())
        
        # Safe string comparison prevents false positives from int/string differences
        for k in all_keys:
            s_val = saved_remote_cfg.get(k)
            c_val = current_remote_cfg.get(k)
            s_norm = str(s_val).strip() if s_val not in [None, False] else ""
            c_norm = str(c_val).strip() if c_val not in [None, False] else ""
            if s_norm != c_norm:
                config_changed = True
                break
                
        self.is_dirty = path_changed or config_changed
        self.status_label.set_markup("<span foreground='#e67e22'><b>[✗] Unsaved Changes</b></span>" if self.is_dirty else "<span foreground='#2ecc71'><b>[✓] Synced to Disk</b></span>")
        self.update_preview()

    def on_reset_clicked(self, btn): self.global_cfg = config_manager.load_config(); self.load_data()

    def _gather_live_keys(self):
        keys = [r.key for r in self.can_list.get_children()]
        for k, btn in self.smart_toggles.items():
            if btn.get_active() and k not in keys: keys.append(k)
        return keys

    def equip_logic(self, key):
        keys = self._gather_live_keys()
        if key not in keys: keys.append(key)
        fk, fv, lk = rules_engine.evaluate_state(keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk); self.check_dirty()

    def unequip_logic(self, row):
        keys = [k for k in self._gather_live_keys() if k != row.key]
        fk, fv, lk = rules_engine.evaluate_state(keys, self.items_lookup)
        self._apply_new_state(fk, fv, lk); self.check_dirty()

    def on_smart_preset_toggled(self, switch, pspec, key):
        if self._updating_rules: return
        if key == "preset_safe_trash" and switch.get_active():
            lp = self.path_entry.get_text()
            if lp and os.path.exists(lp):
                try: os.makedirs(os.path.join(lp, TRASH_LOCAL_NAME), exist_ok=True)
                except Exception: pass
        fk, fv, lk = rules_engine.evaluate_state(self._gather_live_keys(), self.items_lookup)
        self._apply_new_state(fk, fv, lk); self.check_dirty()

    def _apply_new_state(self, target_keys, values_dict, locked_keys):
        self._updating_rules = True
        display_keys = {k for k in target_keys if k not in self.smart_keys and (k.split('__uid_')[0] if '__uid_' in k else k) in self.items_lookup}
        current_rows = {r.key: r for r in self.can_list.get_children()}
        
        for k in list(current_rows):
            if k not in display_keys:
                self.can_list.remove(current_rows[k]); del current_rows[k]
                
        for k in display_keys:
            base_k = k.split('__uid_')[0] if '__uid_' in k else k
            item = self.items_lookup[base_k]
            if k not in current_rows:
                # Merge user values with schema defaults
                val = values_dict.get(k, getattr(item, 'default', ""))
                new_row = self.create_canvas_card(k, val, is_locked=(k in locked_keys))
                self.can_list.add(new_row); current_rows[k] = new_row
                
        for k, r in current_rows.items():
            if k in values_dict: self.set_row_value(r, values_dict[k])
            is_locked = (k in locked_keys)
            if hasattr(r, 'input_widget') and r.input_widget: r.input_widget.set_sensitive(not is_locked)
            if hasattr(r, 'drop_btn'): r.drop_btn.set_visible(not is_locked)
            
            # The Split Button remains visible even if the input is locked, allowing unblocked clones
            if hasattr(r, 'split_btn'):
                r.split_btn.set_visible('__uid_' not in k)

        for k, btn in self.smart_toggles.items():
            if btn.get_active() != (k in target_keys): btn.set_active(k in target_keys)
            
        self._updating_rules = False; self.refresh_inventory()

    def refresh_inventory(self):
        for c in self.inventory_container.get_children(): self.inventory_container.remove(c)
        search = self.search_entry.get_text().lower(); active_cat = self.category_combo.get_active_text()
        excluded = {r.key for r in self.can_list.get_children()}
        for cat, items in CONFIG_SCHEMA.items():
            if active_cat != "All Categories" and cat != active_cat: continue
            available = [i for i in items if i.key not in excluded and str(i.default_equipped) != "0" and (not search or search in f"{i.label} {i.key} {i.desc}".lower())]
            if not available: continue
            grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            lbl = Gtk.Label(xalign=0); lbl.set_markup(f"<span color='#888' size='small'><b>{cat.upper()}</b></span>"); grp.pack_start(lbl, False, False, 0)
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
            for i in available: flow.add(self.create_chip(i.key))
            grp.pack_start(flow, False, False, 0); self.inventory_container.pack_start(grp, False, False, 0)
        self.window.show_all()

    def update_preview(self):
        profile = self.profile_combo.get_active_text() or "[PROFILE]"
        local_path = self.path_entry.get_text() or "[LOCAL_PATH]"
        
        live_state = {r.key: self.get_row_value(r) for r in self.can_list.get_children()}
        for k, btn in self.smart_toggles.items():
            if btn.get_active(): live_state[k] = True
            
        active_keys = [k for k, v in live_state.items() if v is True or (isinstance(v, str) and v)]
        _, forced_values, _ = rules_engine.evaluate_state(active_keys, self.items_lookup)
        
        preview_state = live_state.copy(); preview_state.update(forced_values)

        errors = rules_engine.validate_state(preview_state, self.items_lookup)
        if errors:
            self.preview_view.get_buffer().set_text("VALIDATION ERRORS:\n" + "\n".join([f"× {k}: {msg}" for k, msg in errors.items()]))
            self.preview_view.get_style_context().add_class("console-error")
            if getattr(self, 'apply_btn', None): self.apply_btn.set_sensitive(False)
            return
            
        try:
            self.preview_view.get_style_context().remove_class("console-error")
            
            # Passed local_path here to render absolute paths for trash folders
            args = config_manager.build_base_args(profile, self.global_cfg, preview_state, local_path)
            
            import shlex
            safe_args = [shlex.quote(str(a)) for a in args]
            p1 = shlex.quote(local_path)
            p2 = shlex.quote(f"{profile}:")
            
            cmd_str = f"rclone bisync {p1} {p2} {' '.join(safe_args)}"
            
            self.preview_view.get_buffer().set_text(cmd_str)
            if getattr(self, 'apply_btn', None): self.apply_btn.set_sensitive(True)
        except Exception as e:
            import traceback
            err_msg = f"PREVIEW ERROR:\n{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            self.preview_view.get_buffer().set_text(err_msg)
            if getattr(self, 'apply_btn', None): self.apply_btn.set_sensitive(False)

    def load_data(self):
        profile = self.profile_combo.get_active_text()
        if not profile: return
        self._updating_rules = True
        
        local_path = self.global_cfg.get('local_paths', {}).get(profile, ""); self.path_entry.set_text(local_path)
        prof_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {})
        
        active_keys = {k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v)}
        
        heuristics = smart_automations.scan_environment(local_path, profile)
        for rec in heuristics:
            item = self.items_lookup.get(rec)
            if item and getattr(item, "auto_apply", False): active_keys.add(rec)
            
        fk, forced_vals, lk = rules_engine.evaluate_state(active_keys, self.items_lookup)
        
        merged_state = prof_cfg.copy()
        merged_state.update(forced_vals)
        
        self._apply_new_state(fk, merged_state, lk)
        self._updating_rules = False
        
        self.is_dirty = False
        self.status_label.set_markup("<span foreground='#2ecc71'><b>[✓] Synced to Disk</b></span>")
        
        # Added to immediately render preview on load
        self.update_preview()

    def save_config(self, btn):
        profile = self.profile_combo.get_active_text()
        if not profile: return
        new_remote_cfg = {row.key: self.get_row_value(row) for row in self.can_list.get_children()}
        for k, switch in self.smart_toggles.items():
            if switch.get_active(): new_remote_cfg[k] = True
        self.global_cfg.setdefault('remote_configs', {})[profile] = new_remote_cfg
        self.global_cfg.setdefault('local_paths', {})[profile] = self.path_entry.get_text()
        config_manager.save_config(self.global_cfg); self.check_dirty()

    def create_chip(self, key):
        i = self.items_lookup[key]; lbl = Gtk.Label(); lbl.set_markup(f"<span foreground='{i.color}'><b>{i.label}</b></span>")
        btn = Gtk.Button(); btn.add(lbl); btn.get_style_context().add_class("chip")
        # Standard behavior: clicking inventory equips base tool
        btn.connect("clicked", lambda _: self.equip_logic(key)); return btn

    def create_canvas_card(self, key, val=None, is_locked=False):
        base_key = key.split('__uid_')[0] if '__uid_' in key else key
        i = self.items_lookup[base_key]
        row = Gtk.ListBoxRow(); row.key = key; row.set_activatable(False); row.set_selectable(False)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5); card.get_style_context().add_class("canvas-card")
        top = Gtk.Box(spacing=10)
        top.pack_start(Gtk.Label(label=f"<span foreground='{i.color}'><b>{i.label}</b></span>", use_markup=True, xalign=0), True, True, 0)
        item_type = getattr(i, 'type', None)
            
        drop = Gtk.Button(label="✕"); drop.connect("clicked", lambda _: self.unequip_logic(row)); top.pack_end(drop, False, False, 0); row.drop_btn = drop
        card.pack_start(top, False, False, 0); row.input_widget = None
        
        # Split button exclusively attached to base component
        if item_type in ['text', 'stack'] and '__uid_' not in key:
            split_btn = Gtk.Button(label="+"); split_btn.set_tooltip_text("Split into an additional unblocked entry")
            def on_split(_):
                uid_key = f"{base_key}__uid_{uuid.uuid4().hex[:6]}"
                self.equip_logic(uid_key)
            split_btn.connect("clicked", on_split); top.pack_end(split_btn, False, False, 0); row.split_btn = split_btn
        
        if item_type == 'entry':
            row.input_widget = Gtk.Entry(text=str(val or "")); row.input_widget.connect("changed", self.check_dirty); card.pack_start(row.input_widget, False, False, 0)
        elif item_type == 'multi':
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE); flow.set_max_children_per_line(3); row.checkboxes = {}
            opts = getattr(i, 'options', []); active_vals = [v.strip() for v in str(val or "").split(',')] if val else []
            for opt in opts:
                chk = Gtk.CheckButton(label=opt)
                if opt in active_vals: chk.set_active(True)
                chk.connect("toggled", lambda _: self.check_dirty()); flow.add(chk); row.checkboxes[opt] = chk
            row.input_widget = flow; card.pack_start(flow, False, False, 0)
        elif item_type == 'combo':
            row.input_widget = Gtk.ComboBoxText(); opts = getattr(i, 'options', [])
            for opt in opts: row.input_widget.append_text(opt)
            if str(val) in opts: row.input_widget.set_active(opts.index(str(val)))
            row.input_widget.connect("changed", self.check_dirty); card.pack_start(row.input_widget, False, False, 0)
        elif item_type == 'text':
            tv = Gtk.TextView(); tv.get_buffer().set_text(str(val or "")); tv.set_left_margin(4)
            tv.get_buffer().connect("changed", lambda _: self.check_dirty()); row.input_widget = tv
            sw = Gtk.ScrolledWindow(); sw.set_min_content_height(80); sw.add(tv); card.pack_start(sw, False, False, 0)
        elif item_type == 'count':
            adj = Gtk.Adjustment(value=int(val or 0), lower=0, upper=5, step_increment=1); spin = Gtk.SpinButton(adjustment=adj, numeric=True)
            spin.connect("value-changed", lambda _: self.check_dirty()); row.input_widget = spin; card.pack_start(spin, False, False, 0)
        row.add(card); return row

    def get_row_value(self, row):
        base_key = row.key.split('__uid_')[0] if '__uid_' in row.key else row.key
        i = self.items_lookup[base_key]; t = getattr(i, 'type', 'check')
        if t in ['check'] or not getattr(row, 'input_widget', None): return True
        if t == 'entry': return row.input_widget.get_text()
        if t == 'multi':
            active = [opt for opt, chk in getattr(row, 'checkboxes', {}).items() if chk.get_active()]; return ",".join(active)
        if t == 'combo': return row.input_widget.get_active_text()
        if t == 'text':
            buf = row.input_widget.get_buffer(); return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        if t == 'count': return int(row.input_widget.get_value())
        return None

    def set_row_value(self, row, val):
        base_key = row.key.split('__uid_')[0] if '__uid_' in row.key else row.key
        i = self.items_lookup[base_key]; t = getattr(i, 'type', None)
        if t == 'entry' and hasattr(row, 'input_widget'): row.input_widget.set_text(str(val or ""))
        elif t == 'multi' and hasattr(row, 'checkboxes'):
            active_vals = [v.strip() for v in str(val or "").split(',')] if val else []
            for opt, chk in row.checkboxes.items(): chk.set_active(opt in active_vals)
        elif t == 'combo' and hasattr(row, 'input_widget'):
            opts = getattr(i, 'options', [])
            if str(val) in opts: row.input_widget.set_active(opts.index(str(val)))
        elif t == 'text' and hasattr(row, 'input_widget') and isinstance(row.input_widget, Gtk.TextView):
            row.input_widget.get_buffer().set_text(str(val or ""))
        elif t == 'count' and hasattr(row, 'input_widget') and isinstance(row.input_widget, Gtk.SpinButton):
            row.input_widget.set_value(int(val or 0))

    def post_sync_cleanup(self, profile):
        prof_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {}); changed = False
        for i in SMART_SCHEMA.get("Smart Automations", []):
            if getattr(i, "lifecycle", "persistent") == "one_time" and prof_cfg.get(i.key):
                prof_cfg[i.key] = False; changed = True
        if changed:
            active_keys = [k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v)]
            fk, merged, lk = rules_engine.evaluate_state(active_keys, self.items_lookup)
            self.global_cfg['remote_configs'][profile] = merged; config_manager.save_config(self.global_cfg)
            if self.profile_combo.get_active_text() == profile: self._apply_new_state(fk, merged, lk)