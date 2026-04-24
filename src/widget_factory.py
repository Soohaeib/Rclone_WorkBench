import gi, uuid
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
from urllib.parse import unquote

THEME = {
    "critical": "#c0392b", # Red: Destructive / Abort
    "decision": "#e67e22", # Orange: Logic altercations
    "safety": "#27ae60", # Green: Safety nets
    "operational": "#2980b9", # Blue: Standard behaviors
    "heuristic": "#8e44ad", # Purple: Advanced Metadata
    "system": "#7f8c8d", # Grey: Paths & Plumbing
}

def create_inventory_chip(item, item_id, equip_callback, disabled_keys=None):
    if disabled_keys is None: disabled_keys = {}
    is_disabled = item_id in disabled_keys
    
    hex_color = THEME.get(getattr(item, 'severity', 'system'), "#ffffff")
    markup = f"<span foreground='{hex_color}'><b>{item.label}</b></span>"
    if is_disabled: markup = f"<span foreground='grey' strikethrough='true'>{item.label}</span>"

    lbl = Gtk.Label(); lbl.set_markup(markup)
    btn = Gtk.Button(); btn.add(lbl); btn.get_style_context().add_class("chip")
    
    if is_disabled:
        locker_name = disabled_keys.get(item_id, "current configuration")
        btn.set_tooltip_markup(f"<span color='orange'>[🔒︎] Locked by {locker_name}</span>")
        btn.set_sensitive(False)
    elif item.desc: 
        btn.set_tooltip_markup(item.desc)
        
    if not is_disabled: btn.connect("clicked", lambda _: equip_callback(item_id))
    return btn

def apply_locks(row, item_type, lock_state):
    """Dynamically grays out widgets and assigns tooltips based on Macro (String) or Micro (Dict) locks."""
    is_locked = bool(lock_state)
    
    if hasattr(row, 'drop_btn'):
        row.drop_btn.set_visible(not is_locked)
        row.drop_btn.set_sensitive(not is_locked)

    if isinstance(lock_state, str): 
        if hasattr(row, 'input_widget') and row.input_widget: 
            row.input_widget.set_sensitive(False)
            row.input_widget.set_tooltip_text(f"[🔒︎] Locked by {lock_state}")
        return

    if item_type == 'multi' and hasattr(row, 'checkboxes'):
        if hasattr(row, 'input_widget') and row.input_widget: 
            row.input_widget.set_sensitive(True)
            
        micro_locks = lock_state if isinstance(lock_state, dict) else {}
            
        for opt, chk in row.checkboxes.items():
            if opt in micro_locks:
                chk.set_sensitive(False)
                chk.set_tooltip_text(f"[🔒︎] Locked by {micro_locks[opt]}")
            else:
                chk.set_sensitive(True)
                chk.set_tooltip_text("")
    else:
        if hasattr(row, 'input_widget') and row.input_widget:
            row.input_widget.set_sensitive(not is_locked)
            row.input_widget.set_tooltip_text("")

def create_canvas_row(item, base_key, row_key, val, lock_state, cb_change, cb_unequip, cb_split):
    row = Gtk.ListBoxRow(); row.key = row_key; row.set_activatable(False); row.set_selectable(False)
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5); card.get_style_context().add_class("canvas-card")
    
    hex_color = THEME.get(getattr(item, 'severity', 'system'), "#ffffff")
    lbl = Gtk.Label(label=f"<span foreground='{hex_color}'><b>{item.label}</b></span>", use_markup=True, xalign=0)
    if item.desc: lbl.set_tooltip_markup(item.desc)
        
    top = Gtk.Box(spacing=10); top.pack_start(lbl, True, True, 0)
    t = getattr(item, 'type', None)
    drop = Gtk.Button(label="✕"); drop.connect("clicked", lambda _: cb_unequip(row)); top.pack_end(drop, False, False, 0); row.drop_btn = drop
    
    card.pack_start(top, False, False, 0); row.input_widget = None
    
    limit = getattr(item, 'clone_limit', 0)
    if limit != 0 and '.' not in row_key and t in['text', 'entry']:
        split_btn = Gtk.Button(label="+")
        split_btn.set_tooltip_text("Split into an additional unblocked entry")
        split_btn.connect("clicked", lambda _: cb_split(f"{base_key}.{uuid.uuid4().hex[:6]}", limit, base_key))
        top.pack_end(split_btn, False, False, 0); row.split_btn = split_btn

    # --- DND Helper ---
    def _attach_dnd(w, is_text):
        # We drop DestDefaults.ALL to stop GTK from auto-handling the drop sequence natively
        w.drag_dest_set(Gtk.DestDefaults.MOTION | Gtk.DestDefaults.HIGHLIGHT,[], Gdk.DragAction.COPY)
        w.drag_dest_add_uri_targets()
        
        def _on_drag_drop(wid, ctx, x, y, time):
            if Gdk.Atom.intern("text/uri-list", False) in ctx.list_targets():
                # STOP the TextView base class from initiating its text/plain fallback!
                wid.stop_emission_by_name("drag-drop") 
                wid.drag_get_data(ctx, Gdk.Atom.intern("text/uri-list", False), time)
                return True
            return False
            
        def _on_drop_data(wid, ctx, x, y, data, info, time):
            if uris := data.get_uris():
                wid.stop_emission_by_name("drag-data-received") # Final safety block
                paths =[unquote(u.replace("file://", "").strip('\r\n')) for u in uris]
                if is_text:
                    buf = wid.get_buffer()
                    buf.insert_at_cursor("\n".join(paths) + "\n")
                else: 
                    wid.set_text(paths[0])
                ctx.finish(True, False, time)
                return True
            ctx.finish(False, False, time)
            return False
            
        w.connect("drag-drop", _on_drag_drop)
        w.connect("drag-data-received", _on_drop_data)
    # ------------------
     
    if t == 'entry':
        w = Gtk.Entry(text=str(val or "")); w.connect("changed", lambda _: cb_change())
        _attach_dnd(w, False)
        row.input_widget = w; card.pack_start(w, False, False, 0)
    elif t == 'multi':
        w = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE); w.set_max_children_per_line(3); row.checkboxes = {}
        active_vals =[v.strip() for v in str(val or "").split(',')] if val else[]
        for opt in getattr(item, 'options',[]):
            chk = Gtk.CheckButton(label=opt); chk.set_active(opt in active_vals); chk.connect("toggled", lambda _: cb_change())
            w.add(chk); row.checkboxes[opt] = chk
        row.input_widget = w; card.pack_start(w, False, False, 0)
    elif t == 'combo':
        w = Gtk.ComboBoxText(); opts = getattr(item, 'options',[])
        for opt in opts: w.append_text(opt)
        if str(val) in opts: w.set_active(opts.index(str(val)))
        w.connect("changed", lambda _: cb_change()); row.input_widget = w; card.pack_start(w, False, False, 0)
    elif t == 'text':
        tv = Gtk.TextView(); tv.get_buffer().set_text(str(val or "")); tv.set_left_margin(4)
        tv.get_buffer().connect("changed", lambda *args: cb_change()); row.input_widget = tv
        _attach_dnd(tv, True)
        sw = Gtk.ScrolledWindow(); sw.set_min_content_height(80); sw.add(tv); card.pack_start(sw, False, False, 0)
    elif t in ['number', 'count']: 
        min_val = getattr(item, 'validation', {}).get('min', 0)
        max_val = getattr(item, 'validation', {}).get('max', 1000000)
        start_val = val if val not in [None, ""] else min_val 
        adj = Gtk.Adjustment(value=int(start_val), lower=min_val, upper=max_val, step_increment=1)
        w = Gtk.SpinButton(adjustment=adj, numeric=True); w.connect("value-changed", lambda _: cb_change())
        row.input_widget = w; card.pack_start(w, False, False, 0)
        
    row.add(card)
    apply_locks(row, t, lock_state)
    return row

def extract_value(row, item_type):
    if item_type in ['check'] or not getattr(row, 'input_widget', None): return True
    if item_type == 'entry': return row.input_widget.get_text()
    if item_type == 'multi': return ",".join(opt for opt, chk in getattr(row, 'checkboxes', {}).items() if chk.get_active())
    if item_type == 'combo': return row.input_widget.get_active_text()
    if item_type == 'text': buf = row.input_widget.get_buffer(); return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
    if item_type in ['number', 'count']: return int(row.input_widget.get_value())
    return None

def inject_value(row, item, val):
    t = getattr(item, 'type', None)
    if t == 'entry' and hasattr(row, 'input_widget'): row.input_widget.set_text(str(val or ""))
    elif t == 'multi' and hasattr(row, 'checkboxes'):
        av =[v.strip() for v in str(val or "").split(',')] if val else[]
        for opt, chk in row.checkboxes.items(): chk.set_active(opt in av)
    elif t == 'combo' and hasattr(row, 'input_widget'):
        if str(val) in (opts := getattr(item, 'options',[])): row.input_widget.set_active(opts.index(str(val)))
    elif t == 'text' and hasattr(row, 'input_widget'): row.input_widget.get_buffer().set_text(str(val or ""))
    elif t in ['number', 'count'] and hasattr(row, 'input_widget'): row.input_widget.set_value(int(val or 0))