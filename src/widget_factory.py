import gi, uuid
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

def create_inventory_chip(item, key, equip_callback):
    lbl = Gtk.Label(); lbl.set_markup(f"<span foreground='{item.color}'><b>{item.label}</b></span>")
    btn = Gtk.Button(); btn.add(lbl); btn.get_style_context().add_class("chip")
    
    # NEW: Tooltips from Blueprint
    if item.desc: btn.set_tooltip_markup(item.desc)
        
    btn.connect("clicked", lambda _: equip_callback(key))
    return btn

def create_canvas_row(item, base_key, row_key, val, is_locked, cb_change, cb_unequip, cb_split):
    row = Gtk.ListBoxRow(); row.key = row_key; row.set_activatable(False); row.set_selectable(False)
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5); card.get_style_context().add_class("canvas-card")
    
    lbl = Gtk.Label(label=f"<span foreground='{item.color}'><b>{item.label}</b></span>", use_markup=True, xalign=0)
    if item.desc: lbl.set_tooltip_markup(item.desc)
        
    top = Gtk.Box(spacing=10); top.pack_start(lbl, True, True, 0)
    
    t = getattr(item, 'type', None)
    drop = Gtk.Button(label="✕"); drop.connect("clicked", lambda _: cb_unequip(row)); top.pack_end(drop, False, False, 0); row.drop_btn = drop
    card.pack_start(top, False, False, 0); row.input_widget = None
    
    limit = getattr(item, 'clone_limit', 0)
    if limit != 0 and '.' not in row_key and t in ['text', 'entry']:
        split_btn = Gtk.Button(label="➕")
        split_btn.set_tooltip_text("Split into an additional unblocked entry")
        split_btn.connect("clicked", lambda _: cb_split(f"{base_key}.{uuid.uuid4().hex[:6]}", limit, base_key))
        top.pack_end(split_btn, False, False, 0); row.split_btn = split_btn
     
    if t == 'entry':
        w = Gtk.Entry(text=str(val or "")); w.connect("changed", lambda _: cb_change())
        row.input_widget = w; card.pack_start(w, False, False, 0)
    elif t == 'multi':
        w = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE); w.set_max_children_per_line(3); row.checkboxes = {}
        active_vals = [v.strip() for v in str(val or "").split(',')] if val else []
        for opt in getattr(item, 'options', []):
            chk = Gtk.CheckButton(label=opt); chk.set_active(opt in active_vals); chk.connect("toggled", lambda _: cb_change())
            w.add(chk); row.checkboxes[opt] = chk
        row.input_widget = w; card.pack_start(w, False, False, 0)
    elif t == 'combo':
        w = Gtk.ComboBoxText(); opts = getattr(item, 'options', [])
        for opt in opts: w.append_text(opt)
        if str(val) in opts: w.set_active(opts.index(str(val)))
        w.connect("changed", lambda _: cb_change()); row.input_widget = w; card.pack_start(w, False, False, 0)
    elif t == 'text':
        tv = Gtk.TextView(); tv.get_buffer().set_text(str(val or "")); tv.set_left_margin(4)
        tv.get_buffer().connect("changed", lambda *args: cb_change()); row.input_widget = tv
        sw = Gtk.ScrolledWindow(); sw.set_min_content_height(80); sw.add(tv); card.pack_start(sw, False, False, 0)
    elif t in ['number', 'count']: 
        min_val = getattr(item, 'validation', {}).get('min', 0)
        max_val = getattr(item, 'validation', {}).get('max', 1000000)
        # FIX: Avoid "0 is falsy" bug. Explicitly check for None or empty string.
        start_val = val if val not in [None, ""] else min_val 
        adj = Gtk.Adjustment(value=int(start_val), lower=min_val, upper=max_val, step_increment=1)
        w = Gtk.SpinButton(adjustment=adj, numeric=True); w.connect("value-changed", lambda _: cb_change())
        row.input_widget = w; card.pack_start(w, False, False, 0)
        
    row.add(card)
    
    if is_locked:
        if row.input_widget: row.input_widget.set_sensitive(False)
        row.drop_btn.set_visible(False)
        
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
        av = [v.strip() for v in str(val or "").split(',')] if val else []
        for opt, chk in row.checkboxes.items(): chk.set_active(opt in av)
    elif t == 'combo' and hasattr(row, 'input_widget'):
        if str(val) in (opts := getattr(item, 'options', [])): row.input_widget.set_active(opts.index(str(val)))
    elif t == 'text' and hasattr(row, 'input_widget'): row.input_widget.get_buffer().set_text(str(val or ""))
    elif t in ['number', 'count'] and hasattr(row, 'input_widget'): row.input_widget.set_value(int(val or 0))