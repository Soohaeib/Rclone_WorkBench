import gi, os, subprocess
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from src import config_manager, rules_engine, log_formatter, smart_engine, widget_factory
from src.workbench_blueprint import LOG_DIR, TRASH_LOCAL_NAME, CONFIG_SCHEMA, SMART_SCHEMA

class LiveOutputPanel:
    def __init__(self, remotes):
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.container.get_style_context().add_class("live-output-tab")
        self.notebook = Gtk.Notebook(); self.notebook.get_style_context().add_class("live-output-notebook")
        self.notebook.set_tab_pos(Gtk.PositionType.LEFT); self.container.pack_start(self.notebook, True, True, 0)
        self.change_callback, self.tabs = None, {}
        
        for p in remotes:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); vbox.set_border_width(8)
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            status = Gtk.Label(label="● IDLE", xalign=0); status.get_style_context().add_class("status-line")
            header.pack_start(status, True, True, 0)
            
            def _btn(icon, tip, cb): b = Gtk.Button(tooltip_text=tip); b.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON)); b.connect("clicked", cb); return b
            header.pack_end(_btn("view-refresh-symbolic", "Reload Log", lambda _, x=p: self.reload_log(x)), False, False, 0)
            header.pack_end(_btn("folder-open-symbolic", "Open Log Dir", lambda _, x=p: os.makedirs(LOG_DIR, exist_ok=True) or subprocess.Popen(['xdg-open', LOG_DIR])), False, False, 0)
            header.pack_end(_btn("user-trash-symbolic", "Delete Log", lambda _, x=p: (os.remove(log) if os.path.exists(log := os.path.join(LOG_DIR, f"{x}_sync.jsonl")) else None) or self.tabs[x]['buffer'].set_text("[SYSTEM] Log deleted.\n")), False, False, 0)
            header.pack_end(_btn("edit-clear-symbolic", "Clear Display", lambda _, x=p: self.tabs[x]["buffer"].set_text("")), False, False, 0)
            
            vbox.pack_start(header, False, False, 0)
            tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            tv.set_monospace(True); tv.get_style_context().add_class("log-view")
            sw = Gtk.ScrolledWindow(); sw.set_shadow_type(Gtk.ShadowType.IN); sw.add(tv); vbox.pack_start(sw, True, True, 0)
            self.notebook.append_page(vbox, Gtk.Label(label=p.upper()))
            
            self.tabs[p] = {'vbox': vbox, 'status': status, 'buffer': tv.get_buffer(), 'tv': tv, 'sw': sw}
            log_formatter.start_live_feed(p, lambda a, x=p: GLib.idle_add(self.update_logs, x, a))
            
        self.notebook.connect("switch-page", lambda n, _, __: self.change_callback(n.get_tab_label(n.get_nth_page(n.get_current_page())).get_text().lower()) if self.change_callback else None)

    def focus_profile(self, profile):
        if profile in self.tabs and (pn := self.notebook.page_num(self.tabs[profile]['vbox'])) != -1: self.notebook.set_current_page(pn)

    def reload_log(self, profile):
        if not (tab := self.tabs.get(profile)): return
        tab['buffer'].set_text("")
        if os.path.exists(path := os.path.join(LOG_DIR, f"{profile}_sync.jsonl")):
            try: GLib.idle_add(self.update_logs, profile, [a for line in open(path, "r", encoding="utf-8") for a in log_formatter.format_line(line)])
            except: pass

    def set_status(self, profile, is_running):
        if tab := self.tabs.get(profile): GLib.idle_add(tab['status'].set_text, "● Syncing..." if is_running else "● Idle / Finished")

    def update_logs(self, profile, actions):
        if not (tab := self.tabs.get(profile)): return False
        scroll = False
        for k, d in actions:
            if k == "log": tab['buffer'].insert(tab['buffer'].get_end_iter(), str(d)); scroll = True
            elif k == "stats": tab['status'].set_text(f"● {d.get('msg') or f'Transferred: {d.get('bytes',0)} | Speed: {d.get('speed',0)}/s' if isinstance(d, dict) else str(d) or 'Syncing...'}")
        if scroll: tab['tv'].scroll_to_mark(tab['buffer'].create_mark(None, tab['buffer'].get_end_iter(), False), 0.05, True, 0, 1)
        return False

class InventoryWorkbench:
    def __init__(self, profiles):
        rules_engine.validate_blueprint()
        self.remotes, self.global_cfg = profiles, config_manager.load_config()
        self.items_lookup, self.smart_keys = rules_engine.get_item_lookup(), rules_engine.get_smart_keys()
        self.is_dirty, self._updating_rules, self.smart_toggles = False, False, {}
        
        self.builder = Gtk.Builder(); self.builder.add_from_file(os.path.join(os.path.dirname(__file__), "workbench.glade"))
        self.window = self.builder.get_object("main_window")
        self.main_stack, self.smart_container = self.builder.get_object("main_stack"), self.builder.get_object("smart_container")
        self.inventory_container, self.can_list = self.builder.get_object("inventory_container"), self.builder.get_object("canvas_list")
        self.preview_view, self.apply_btn = self.builder.get_object("preview_view"), self.builder.get_object("btn_apply")
        self.profile_combo, self.path_entry = self.builder.get_object("profile_combo"), self.builder.get_object("path_entry")
        self.search_entry, self.category_combo = self.builder.get_object("search_entry"), self.builder.get_object("category_combo")
        self.status_label = self.builder.get_object("status_label")
        
        self._setup_minimal_css(); self.setup_smart_presets()
        self.window.connect("delete-event", lambda *_: self.window.hide() or True)
        self.profile_combo.connect("changed", self.on_profile_changed)
        self.path_entry.connect("changed", lambda _: self.check_dirty())
        self.search_entry.connect("search-changed", lambda _: self.refresh_inventory())
        self.category_combo.connect("changed", lambda _: self.refresh_inventory())
        
        self.builder.get_object("btn_toggle_smart").connect('clicked', lambda _: self.builder.get_object("smart_revealer").set_reveal_child(not self.builder.get_object("smart_revealer").get_reveal_child()))
        self.builder.get_object("btn_toggle_preview").connect('clicked', lambda _: self.builder.get_object("preview_revealer").set_reveal_child(not self.builder.get_object("preview_revealer").get_reveal_child()))
        self.builder.get_object("btn_reset").connect("clicked", lambda _: setattr(self, 'global_cfg', config_manager.load_config()) or self.load_data())
        self.apply_btn.connect("clicked", self.save_config)
        
        def _browse(_):
            d = Gtk.FileChooserDialog(title="Select Local Directory", parent=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER)
            d.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
            if d.run() == Gtk.ResponseType.OK: self.path_entry.set_text(d.get_filename()); self.check_dirty()
            d.destroy()
        self.builder.get_object("btn_browse").connect("clicked", _browse)

        self.output_panel = LiveOutputPanel(self.remotes)
        self.output_panel.change_callback = self.sync_ui_to_log_tab
        self.builder.get_object("live_output_hook").pack_start(self.output_panel.container, True, True, 0)
        
        self.category_combo.append_text("All Categories")
        [self.category_combo.append_text(c) for c in CONFIG_SCHEMA.keys()]; self.category_combo.set_active(0)
        [self.profile_combo.append_text(r) for r in self.remotes]; self.profile_combo.set_active(0)

    def focus_profile(self, profile): self.main_stack.set_visible_child_name("page1"); self.output_panel.focus_profile(profile)
    def focus_workbench(self): self.main_stack.set_visible_child_name("page0")
    def show_all(self): self.window.show_all()
    def present(self): self.window.present()
    
    def _setup_minimal_css(self):
        p = Gtk.CssProvider(); p.load_from_data(b".chip { border-radius: 999px; padding: 4px 10px; margin: 2px; } .canvas-card { margin-bottom: 6px; padding: 10px; border-bottom: 1px solid alpha(gray, 0.2); }")
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def setup_smart_presets(self):
        css = ""
        for i in SMART_SCHEMA.get("Smart Automations", []):
            h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12); h.set_tooltip_text(i.desc); h.set_margin_start(8); h.set_margin_end(8)
            lbl = Gtk.Label(xalign=0); lbl.set_markup(f"<span foreground='{i.color}'><b>{i.label}</b></span>"); h.pack_start(lbl, True, True, 0)
            sw = Gtk.Switch(); sw.set_valign(Gtk.Align.CENTER); sw.set_name(n := f"smart_switch_{i.key}")
            css += f"#{n}:checked {{ background-image: none; background-color: {i.color}; }}\n"
            sw.connect('notify::active', self.on_smart_preset_toggled, i.key)
            self.smart_toggles[i.key] = sw; h.pack_end(sw, False, False, 0); self.smart_container.pack_start(h, False, False, 0)
        p = Gtk.CssProvider(); p.load_from_data(css.encode()); Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def on_profile_changed(self, combo):
        if profile := combo.get_active_text(): self.load_data(); self.output_panel.focus_profile(profile)

    def sync_ui_to_log_tab(self, profile_name):
        self.profile_combo.handler_block_by_func(self.on_profile_changed)
        for i, row in enumerate(self.profile_combo.get_model()):
            if row[0].lower() == profile_name.lower(): self.profile_combo.set_active(i); break
        self.load_data(); self.profile_combo.handler_unblock_by_func(self.on_profile_changed)

    def check_dirty(self):
        if self._updating_rules or not (p := self.profile_combo.get_active_text()): return
        s_cfg = self.global_cfg.get('remote_configs', {}).get(p, {})
        c_cfg = {r.key: widget_factory.extract_value(r, getattr(self.items_lookup[r.key.split('.')[0] if '.' in r.key else r.key], 'type', 'check')) for r in self.can_list.get_children()}
        c_cfg.update({k: True for k, s in self.smart_toggles.items() if s.get_active()})
        
        self.is_dirty = (self.global_cfg.get('local_paths', {}).get(p, "") != self.path_entry.get_text()) or any(
            (str(s_cfg.get(k)).strip() if s_cfg.get(k) not in [None, False] else "") != 
            (str(c_cfg.get(k)).strip() if c_cfg.get(k) not in [None, False] else "") for k in set(s_cfg) | set(c_cfg))
            
        self.status_label.set_markup("<span foreground='#e67e22'><b>[✗] Unsaved Changes</b></span>" if self.is_dirty else "<span foreground='#2ecc71'><b>[✓] Synced to Disk</b></span>")
        self.update_preview()

    def _gather_live_keys(self):
        return [r.key for r in self.can_list.get_children()] + [k for k, b in self.smart_toggles.items() if b.get_active() and k not in [r.key for r in self.can_list.get_children()]]

    def equip_logic(self, key):
        fk, fv, lk = rules_engine.evaluate_state(self._gather_live_keys() + [key] if key not in self._gather_live_keys() else self._gather_live_keys(), self.items_lookup)
        self._apply_new_state(fk, fv, lk); self.check_dirty()

    def unequip_logic(self, row):
        fk, fv, lk = rules_engine.evaluate_state([k for k in self._gather_live_keys() if k != row.key], self.items_lookup)
        self._apply_new_state(fk, fv, lk); self.check_dirty()

    def on_smart_preset_toggled(self, switch, pspec, key):
        if self._updating_rules: return
        if key == "preset_safe_trash" and switch.get_active() and (lp := self.path_entry.get_text()) and os.path.exists(lp):
            try: os.makedirs(os.path.join(lp, TRASH_LOCAL_NAME), exist_ok=True)
            except: pass
        fk, fv, lk = rules_engine.evaluate_state(self._gather_live_keys(), self.items_lookup)
        self._apply_new_state(fk, fv, lk); self.check_dirty()

    def _apply_new_state(self, target_keys, values_dict, locked_keys):
        self._updating_rules = True
        display_keys = {k for k in target_keys if k not in self.smart_keys and (k.split('.')[0] if '.' in k else k) in self.items_lookup}
        current_rows = {r.key: r for r in self.can_list.get_children()}
        
        for k in list(current_rows):
            if k not in display_keys: self.can_list.remove(current_rows.pop(k))
                
        for k in display_keys:
            base_k = k.split('.')[0] if '.' in k else k
            item = self.items_lookup[base_k]
            if k not in current_rows:
                # Delegate entirely to the Widget Factory
                new_row = widget_factory.create_canvas_row(item, base_k, k, values_dict.get(k, getattr(item, 'default', "")), k in locked_keys, self.check_dirty, self.unequip_logic, self.equip_logic)
                self.can_list.add(new_row); current_rows[k] = new_row
                
        for k, r in current_rows.items():
            if k in values_dict: widget_factory.inject_value(r, self.items_lookup[k.split('.')[0] if '.' in k else k], values_dict[k])
            if hasattr(r, 'input_widget') and r.input_widget: r.input_widget.set_sensitive(k not in locked_keys)
            if hasattr(r, 'drop_btn'): r.drop_btn.set_visible(k not in locked_keys)
            if hasattr(r, 'split_btn'): r.split_btn.set_visible('.' not in k)

        for k, btn in self.smart_toggles.items():
            if btn.get_active() != (k in target_keys): btn.set_active(k in target_keys)
            
        self._updating_rules = False; self.refresh_inventory()

    def refresh_inventory(self):
        [self.inventory_container.remove(c) for c in self.inventory_container.get_children()]
        search, cat_filter = self.search_entry.get_text().lower(), self.category_combo.get_active_text()
        excluded = {r.key for r in self.can_list.get_children()}
        
        for cat, items in CONFIG_SCHEMA.items():
            if cat_filter != "All Categories" and cat != cat_filter: continue
            if available := [i for i in items if i.key not in excluded and str(i.default_equipped) != "0" and (not search or search in f"{i.label} {i.key} {i.desc}".lower())]:
                grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                lbl = Gtk.Label(xalign=0); lbl.set_markup(f"<span color='#888' size='small'><b>{cat.upper()}</b></span>"); grp.pack_start(lbl, False, False, 0)
                flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
                # Delegate to factory
                [flow.add(widget_factory.create_inventory_chip(i, i.key, self.equip_logic)) for i in available]
                grp.pack_start(flow, False, False, 0); self.inventory_container.pack_start(grp, False, False, 0)
        self.window.show_all()

    def update_preview(self):
        p, lp = self.profile_combo.get_active_text() or "[PROFILE]", self.path_entry.get_text() or "[LOCAL_PATH]"
        live_state = {r.key: widget_factory.extract_value(r, getattr(self.items_lookup[r.key.split('.')[0] if '.' in r.key else r.key], 'type', 'check')) for r in self.can_list.get_children()}
        live_state.update({k: True for k, b in self.smart_toggles.items() if b.get_active()})
        
        active_keys = [k for k, v in live_state.items() if v is True or (isinstance(v, str) and v)]
        _, fv, _ = rules_engine.evaluate_state(active_keys, self.items_lookup)
        
        p_state = {**live_state, **fv}
        for k in active_keys:
            if (item := self.items_lookup.get(k.split('.')[0] if '.' in k else k)) and (hk := getattr(item, 'python_hook', None)) and hasattr(smart_engine, hk):
                p_state = getattr(smart_engine, hk)(p, lp, f"{p}:", p_state)

        if errors := rules_engine.validate_state(p_state, self.items_lookup):
            self.preview_view.get_buffer().set_text("VALIDATION ERRORS:\n" + "\n".join([f"× {k}: {msg}" for k, msg in errors.items()]))
            self.preview_view.get_style_context().add_class("console-error")
            if hasattr(self, 'apply_btn'): self.apply_btn.set_sensitive(False)
            return
            
        try:
            self.preview_view.get_style_context().remove_class("console-error")
            args = [f'"{a}"' if ' ' in str(a) else str(a) for a in config_manager.build_base_args(p, self.global_cfg, p_state)]
            self.preview_view.get_buffer().set_text(f"rclone bisync {'\"'+lp+'\"' if ' ' in lp else lp} {'\"'+p+':\"' if ' ' in p else p+':'} {' '.join(args)}")
            if hasattr(self, 'apply_btn'): self.apply_btn.set_sensitive(True)
        except Exception as e:
            import traceback; self.preview_view.get_buffer().set_text(f"PREVIEW ERROR:\n{e}\n\nTraceback:\n{traceback.format_exc()}")
            if hasattr(self, 'apply_btn'): self.apply_btn.set_sensitive(False)

    def load_data(self):
        if not (p := self.profile_combo.get_active_text()): return
        self._updating_rules, lp = True, self.global_cfg.get('local_paths', {}).get(p, "")
        self.path_entry.set_text(lp)
        
        prof_cfg = self.global_cfg.get('remote_configs', {}).get(p, {})
        active_keys = {k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v)}
        active_keys.update(rec for rec in smart_engine.scan_environment(lp, p) if getattr(self.items_lookup.get(rec, object), "auto_apply", False))
            
        fk, fv, lk = rules_engine.evaluate_state(active_keys, self.items_lookup)
        self._apply_new_state(fk, {**prof_cfg, **fv}, lk)
        
        self._updating_rules, self.is_dirty = False, False
        self.status_label.set_markup("<span foreground='#2ecc71'><b>[✓] Synced to Disk</b></span>")
        self.update_preview()

    def save_config(self, btn):
        if not (p := self.profile_combo.get_active_text()): return
        new_cfg = {r.key: widget_factory.extract_value(r, getattr(self.items_lookup[r.key.split('.')[0] if '.' in r.key else r.key], 'type', 'check')) for r in self.can_list.get_children()}
        new_cfg.update({k: True for k, sw in self.smart_toggles.items() if sw.get_active()})
        self.global_cfg.setdefault('remote_configs', {})[p] = new_cfg
        self.global_cfg.setdefault('local_paths', {})[p] = self.path_entry.get_text()
        config_manager.save_config(self.global_cfg); self.check_dirty()

    def post_sync_cleanup(self, profile):
        p_cfg = self.global_cfg.get('remote_configs', {}).get(profile, {})
        if any(p_cfg.pop(i.key, None) for i in SMART_SCHEMA.get("Smart Automations", []) if getattr(i, "lifecycle", "persistent") == "one_time" and p_cfg.get(i.key)):
            fk, merged, lk = rules_engine.evaluate_state([k for k, v in p_cfg.items() if v is True or (isinstance(v, str) and v)], self.items_lookup)
            self.global_cfg['remote_configs'][profile] = merged; config_manager.save_config(self.global_cfg)
            if self.profile_combo.get_active_text() == profile: self._apply_new_state(fk, merged, lk)