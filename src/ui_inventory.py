import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from src import config_manager, rules_engine, smart_engine, widget_factory
from src.workbench_blueprint import TRASH_LOCAL_NAME, CONFIG_SCHEMA, SMART_SCHEMA

class InventoryPanel:
    def __init__(self, ctrl, builder):
        self.ctrl = ctrl
        self.builder = builder
        self.items_lookup = rules_engine.get_item_lookup()
        self.smart_keys = rules_engine.get_smart_keys()
        
        self._updating_rules = False
        self.smart_toggles = {}
        
        # Grab local containers from builder
        self.smart_container = self.builder.get_object("smart_container")
        self.inventory_container = self.builder.get_object("inventory_container")
        self.can_list = self.builder.get_object("canvas_list")
        self.preview_view = self.builder.get_object("preview_view")
        self.search_entry = self.builder.get_object("search_entry")
        self.category_combo = self.builder.get_object("category_combo")
        self.apply_btn = self.builder.get_object("btn_apply")
        
        # Wire up local signals
        self.search_entry.connect("search-changed", lambda _: self.refresh_inventory())
        self.category_combo.connect("changed", lambda _: self.refresh_inventory())
        self.apply_btn.connect("clicked", self.save_config)
        
        self.setup_smart_presets()
        
        self.category_combo.append_text("All Categories")
        for c in CONFIG_SCHEMA.keys():
            self.category_combo.append_text(c)
        self.category_combo.set_active(0)

    def setup_smart_presets(self):
        css = ""
        for i in SMART_SCHEMA.get("Smart Automations", []):
            h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            h.set_tooltip_text(i.desc)
            h.set_margin_start(8); h.set_margin_end(8)
            
            lbl = Gtk.Label(xalign=0)
            lbl.set_markup(f"<span foreground='{i.color}'><b>{i.label}</b></span>")
            h.pack_start(lbl, True, True, 0)
            
            sw = Gtk.Switch()
            sw.set_valign(Gtk.Align.CENTER)
            sw.set_name(n := f"smart_switch_{i.id}")
            css += f"#{n}:checked {{ background-image: none; background-color: {i.color}; }}\n"
            
            sw.connect('notify::active', self.on_smart_preset_toggled, i.id)
            self.smart_toggles[i.id] = sw
            h.pack_end(sw, False, False, 0)
            self.smart_container.pack_start(h, False, False, 0)
            
        p = Gtk.CssProvider()
        p.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _gather_live_keys(self):
        return [r.key for r in self.can_list.get_children()] + [k for k, b in self.smart_toggles.items() if b.get_active() and k not in [r.key for r in self.can_list.get_children()]]

    def _gather_raw_values(self):
        vals = {r.key: widget_factory.extract_value(r, getattr(self.items_lookup[r.key.split('.')[0] if '.' in r.key else r.key], 'type', 'check')) for r in self.can_list.get_children()}
        vals.update({k: True for k, b in self.smart_toggles.items() if b.get_active()})
        return vals

    def equip_logic(self, item_id):
        raw_keys = self._gather_live_keys()
        if item_id not in raw_keys: raw_keys.append(item_id)
        fk, fv, lk, dk = rules_engine.evaluate_state(raw_keys, self._gather_raw_values(), self.items_lookup)
        self._apply_new_state(fk, fv, lk, dk)
        self.check_dirty()

    def unequip_logic(self, row):
        fk, fv, lk, dk = rules_engine.evaluate_state([k for k in self._gather_live_keys() if k != row.key], self._gather_raw_values(), self.items_lookup)
        self._apply_new_state(fk, fv, lk, dk)
        self.check_dirty()

    def on_smart_preset_toggled(self, switch, pspec, item_id):
        if self._updating_rules: return
        if item_id == "preset_safe_trash" and switch.get_active() and (lp := self.ctrl.path_entry.get_text()) and os.path.exists(lp):
            try: os.makedirs(os.path.join(lp, TRASH_LOCAL_NAME), exist_ok=True)
            except: pass
            
        fk, fv, lk, dk = rules_engine.evaluate_state(self._gather_live_keys(), self._gather_raw_values(), self.items_lookup)
        self._apply_new_state(fk, fv, lk, dk)
        
        if item_id == "preset_overdrive_sync" and switch.get_active():
            bounds = smart_engine.get_hardware_bounds()
            for row in self.can_list.get_children():
                if row.key == '--checkers': widget_factory.inject_value(row, self.items_lookup['--checkers'], bounds["--checkers"])
                elif row.key == '--transfers': widget_factory.inject_value(row, self.items_lookup['--transfers'], bounds["--transfers"])
                
        self.check_dirty()

    def _apply_new_state(self, target_keys, values_dict, locked_keys, disabled_keys):
        self._updating_rules = True
        display_keys = {k for k in target_keys if k not in self.smart_keys and (k.split('.')[0] if '.' in k else k) in self.items_lookup}
        current_rows = {r.key: r for r in self.can_list.get_children()}
        
        for k in list(current_rows):
            if k not in display_keys: self.can_list.remove(current_rows.pop(k))
            
        def enforce_split(new_key, limit, base_k):
            current_clones = len([r for r in self.can_list.get_children() if r.key.split('.')[0] == base_k])
            if limit == -1 or current_clones < limit:
                self.equip_logic(new_key)
            else:
                self.ctrl.status_label.set_markup(f"<span foreground='#e74c3c'><b>Limit reached ({limit} max)</b></span>")

        for k in display_keys:
            base_k = k.split('.')[0] if '.' in k else k
            item = self.items_lookup[base_k]
            if k not in current_rows:
                lock_state = locked_keys.get(k, False)
                new_row = widget_factory.create_canvas_row(item, base_k, k, values_dict.get(k, getattr(item, 'default', "")), lock_state, self.check_dirty, self.unequip_logic, enforce_split)
                self.can_list.add(new_row); current_rows[k] = new_row
                
        for k, r in current_rows.items():
            if k in values_dict: widget_factory.inject_value(r, self.items_lookup[k.split('.')[0] if '.' in k else k], values_dict[k])
            lock_state = locked_keys.get(k, False)
            widget_factory.apply_locks(r, getattr(self.items_lookup[k.split('.')[0] if '.' in k else k], 'type', None), lock_state)
            if hasattr(r, 'split_btn'): r.split_btn.set_visible('.' not in k)

        for k, btn in self.smart_toggles.items():
            if btn.get_active() != (k in target_keys): btn.set_active(k in target_keys)
            
        self._updating_rules = False
        self.refresh_inventory(disabled_keys)

    def refresh_inventory(self, disabled_keys=None):
        if disabled_keys is None: disabled_keys = set()
        for c in self.inventory_container.get_children(): self.inventory_container.remove(c)
        
        search = self.search_entry.get_text().lower()
        cat_filter = self.category_combo.get_active_text()
        excluded = {r.key for r in self.can_list.get_children()}
        
        for cat, items in CONFIG_SCHEMA.items():
            if cat_filter != "All Categories" and cat != cat_filter: continue
            
            available = [i for i in items if i.flag not in excluded and not getattr(i, 'hidden', False) and str(i.default_equipped) != "0" and (not search or search in f"{i.label} {i.flag} {i.desc}".lower())]
            if available:
                grp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                lbl = Gtk.Label(xalign=0)
                lbl.set_markup(f"<span color='#888' size='small'><b>{cat.upper()}</b></span>")
                grp.pack_start(lbl, False, False, 0)
                
                flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
                for i in available:
                    flow.add(widget_factory.create_inventory_chip(i, i.flag, self.equip_logic, disabled_keys=disabled_keys))
                grp.pack_start(flow, False, False, 0)
                self.inventory_container.pack_start(grp, False, False, 0)
                
        self.ctrl.window.show_all()

    def check_dirty(self):
        if self._updating_rules or not (p := self.ctrl.profile_combo.get_active_text()): return
        s_cfg = self.ctrl.global_cfg.get('remote_configs', {}).get(p, {})
        c_cfg = self._gather_raw_values()
        
        self.ctrl.is_dirty = (self.ctrl.global_cfg.get('local_paths', {}).get(p, "") != self.ctrl.path_entry.get_text()) or any(
            (str(s_cfg.get(k)).strip() if s_cfg.get(k) not in [None, False] else "") != 
            (str(c_cfg.get(k)).strip() if c_cfg.get(k) not in [None, False] else "") for k in set(s_cfg) | set(c_cfg))
            
        self.ctrl.status_label.set_markup("<span foreground='#e67e22'><b>[✗] Unsaved Changes</b></span>" if self.ctrl.is_dirty else "<span foreground='#2ecc71'><b>[✓] Synced to Disk</b></span>")
        
        self.ctrl.btn_sync.set_sensitive(not self.ctrl.is_dirty and not self.ctrl.app.threads[p].run_state)
        self.update_preview()
        
    def update_preview(self):
        p = self.ctrl.profile_combo.get_active_text() or "[PROFILE]"
        lp = self.ctrl.path_entry.get_text() or "[LOCAL_PATH]"
        raw_vals = self._gather_raw_values()
        
        is_overdrive = raw_vals.get('preset_overdrive_sync', False)
        hw_bounds = smart_engine.get_hardware_bounds()
        
        for row in self.can_list.get_children():
            if row.key == '--checkers':
                widget_factory.update_spin_bounds(row, hw_bounds["--checkers"] if is_overdrive else 1000000)
            elif row.key == '--transfers':
                widget_factory.update_spin_bounds(row, hw_bounds["--transfers"] if is_overdrive else 1000000)
                
        active_keys = [k for k, v in raw_vals.items() if v is True or (isinstance(v, str) and v) or (type(v) in [int, float])]
        _, fv, _, _ = rules_engine.evaluate_state(active_keys, raw_vals, self.items_lookup)
        
        p_state = {**raw_vals, **fv}
        for k in active_keys:
            item = self.items_lookup.get(k.split('.')[0] if '.' in k else k)
            if item and (hk := getattr(item, 'python_hook', None)) and hasattr(smart_engine, hk):
                p_state = getattr(smart_engine, hk)(p, lp, f"{p}:", p_state)

        if errors := rules_engine.validate_state(p_state, self.items_lookup):
            self.preview_view.get_buffer().set_text("VALIDATION ERRORS:\n" + "\n".join([f"[X] {k}: {msg}" for k, msg in errors.items()]))
            self.preview_view.get_style_context().add_class("console-error")
            if hasattr(self, 'apply_btn'): self.apply_btn.set_sensitive(False)
            return
            
        try:
            self.preview_view.get_style_context().remove_class("console-error")
            args = [f'"{a}"' if ' ' in str(a) else str(a) for a in config_manager.build_base_args(p, self.ctrl.global_cfg, p_state)]
            self.preview_view.get_buffer().set_text(f"rclone bisync {'\"'+lp+'\"' if ' ' in lp else lp} {'\"'+p+':\"' if ' ' in p else p+':'} {' '.join(args)}")
            if hasattr(self, 'apply_btn'): self.apply_btn.set_sensitive(True)
        except Exception as e:
            import traceback
            self.preview_view.get_buffer().set_text(f"PREVIEW ERROR:\n{e}\n\nTraceback:\n{traceback.format_exc()}")
            if hasattr(self, 'apply_btn'): self.apply_btn.set_sensitive(False)

    def load_data(self):
        if not (p := self.ctrl.profile_combo.get_active_text()): return
        self._updating_rules = True
        lp = self.ctrl.global_cfg.get('local_paths', {}).get(p, "")
        self.ctrl.path_entry.set_text(lp)
        
        prof_cfg = self.ctrl.global_cfg.get('remote_configs', {}).get(p, {})
        
        active_keys = {k for k, v in prof_cfg.items() if v is True or (isinstance(v, str) and v) or (type(v) in [int, float])}
        active_keys.update(rec for rec in smart_engine.scan_environment(lp, p, prof_cfg) if getattr(self.items_lookup.get(rec, object), "auto_apply", False))
            
        fk, fv, lk, dk = rules_engine.evaluate_state(list(active_keys), prof_cfg, self.items_lookup)
        self._apply_new_state(fk, {**prof_cfg, **fv}, lk, dk)
        
        self._updating_rules = False
        self.ctrl.is_dirty = False
        self.ctrl.status_label.set_markup("<span foreground='#2ecc71'><b>[✓] Synced to Disk</b></span>")
        
        is_running = self.ctrl.app.threads[p].run_state
        self.ctrl.btn_sync.set_sensitive(not is_running)
        self.ctrl.btn_stop.set_sensitive(is_running)
        
        self.update_preview()
        
    def save_config(self, btn):
        if not (p := self.ctrl.profile_combo.get_active_text()): return
        new_cfg = {r.key: widget_factory.extract_value(r, getattr(self.items_lookup[r.key.split('.')[0] if '.' in r.key else r.key], 'type', 'check')) for r in self.can_list.get_children()}
        new_cfg.update({k: True for k, sw in self.smart_toggles.items() if sw.get_active()})
        self.ctrl.global_cfg.setdefault('remote_configs', {})[p] = new_cfg
        self.ctrl.global_cfg.setdefault('local_paths', {})[p] = self.ctrl.path_entry.get_text()
        config_manager.save_config(self.ctrl.global_cfg)
        self.check_dirty()

    def reload_profile_if_active(self, profile, new_cfg):
        self.ctrl.global_cfg = new_cfg
        if self.ctrl.profile_combo.get_active_text() == profile:
            self.load_data()

    def reset_to_factory_defaults(self, btn):
        if not (p := self.ctrl.profile_combo.get_active_text()): 
            return
        factory_defaults = {
            getattr(item, 'flag', ''): getattr(item, 'default', "") if item.type != 'check' else False 
            for cat in CONFIG_SCHEMA.values() for item in cat if getattr(item, 'flag', None)
        }
        self.ctrl.global_cfg.setdefault('remote_configs', {})[p] = factory_defaults
        self.load_data()