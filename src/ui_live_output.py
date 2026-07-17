import gi, os, subprocess, datetime
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from src import log_formatter
from src.workbench_blueprint import LOG_DIR

class LiveOutputPanel:
    def __init__(self, remotes):
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.container.get_style_context().add_class("live-output-tab")
        self.notebook = Gtk.Notebook(); self.notebook.get_style_context().add_class("live-output-notebook")
        self.notebook.set_tab_pos(Gtk.PositionType.LEFT); self.container.pack_start(self.notebook, True, True, 0)
        self.change_callback, self.tabs = None, {}
        
        for p in remotes:
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); vbox.set_border_width(8)
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            header.set_margin_bottom(6)
            
            stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            prog = Gtk.ProgressBar(); prog.set_show_text(False) # Turn off messy text overlay
            
            metrics_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            detail_lbl = Gtk.Label(xalign=0); detail_lbl.set_markup("<span size='small' color='gray'>Speed: 0 B/s | ETA: - | Checks: 0 | Deletes: 0</span>")
            progress_lbl = Gtk.Label(xalign=1); progress_lbl.set_markup("<span size='small' color='gray'>Finished</span>")
            
            metrics_box.pack_start(detail_lbl, True, True, 0)
            metrics_box.pack_end(progress_lbl, False, False, 0)
            
            stats_box.pack_start(prog, False, False, 0)
            stats_box.pack_start(metrics_box, False, False, 0)
            
            header.pack_start(stats_box, True, True, 0)
            
            def _btn(icon, tip, cb):
                b = Gtk.Button(tooltip_text=tip)
                b.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
                b.get_style_context().add_class("log-header-btn")
                b.connect("clicked", cb)
                return b
            
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            btn_box.set_valign(Gtk.Align.CENTER)
            
            # Stylized Active Task menu button with a Live badge counter
            transfer_btn = Gtk.MenuButton(tooltip_text="Active Transfers")
            transfer_btn.get_style_context().add_class("log-header-btn")
            t_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            t_icon = Gtk.Image.new_from_icon_name("view-list-symbolic", Gtk.IconSize.BUTTON)
            transfer_lbl = Gtk.Label(label="0")
            t_box.pack_start(t_icon, False, False, 0)
            t_box.pack_start(transfer_lbl, False, False, 0)
            t_box.show_all()
            transfer_btn.add(t_box)
            
            transfer_popover = Gtk.Popover.new(transfer_btn)
            transfer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            transfer_box.set_margin_start(8); transfer_box.set_margin_end(8); transfer_box.set_margin_top(8); transfer_box.set_margin_bottom(8)
            transfer_popover.add(transfer_box)
            transfer_btn.set_popover(transfer_popover)
            
            wrap_btn = Gtk.ToggleButton(tooltip_text="Toggle Line Wrap")
            wrap_btn.get_style_context().add_class("log-header-btn")
            wrap_btn.add(Gtk.Image.new_from_icon_name("format-text-wrap-symbolic", Gtk.IconSize.BUTTON))
            wrap_btn.set_active(True)
            wrap_btn.connect("toggled", lambda btn, x=p: self.toggle_wrap(x, btn))
            
            # Sorted contextually left-to-right (System State -> Render/Visual -> Operations -> External System)
            btn_box.pack_start(transfer_btn, False, False, 0)
            btn_box.pack_start(wrap_btn, False, False, 0)
            btn_box.pack_start(_btn("edit-clear-symbolic", "Clear Display", lambda _, x=p: self.tabs[x]["buffer"].set_text("")), False, False, 0)
            btn_box.pack_start(_btn("view-refresh-symbolic", "Reload Log", lambda _, x=p: self.reload_log(x)), False, False, 0)
            btn_box.pack_start(_btn("ymuse-delete-symbolic", "Delete Log", lambda _, x=p: (os.remove(log) if os.path.exists(log := os.path.join(LOG_DIR, f"{x}_sync.jsonl")) else None) or self.tabs[x]['buffer'].set_text("[SYSTEM] Log deleted.\n")), False, False, 0)
            btn_box.pack_start(_btn("folder-open-symbolic", "Open Log Dir", lambda _, x=p: os.makedirs(LOG_DIR, exist_ok=True) or subprocess.Popen(['xdg-open', LOG_DIR])), False, False, 0)
            
            header.pack_end(btn_box, False, False, 0)
            vbox.pack_start(header, False, False, 0)
            
            tv = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            tv.set_monospace(True); tv.get_style_context().add_class("log-view")
            tv.set_pixels_above_lines(2)
            tv.set_pixels_below_lines(2)
            tv.set_pixels_inside_wrap(1)
            buf = tv.get_buffer()
            buf.create_tag("DEBUG", foreground="#95a5a6")
            buf.create_tag("ERROR", foreground="#e74c3c", weight=700)
            buf.create_tag("WARNING", foreground="#e67e22")
            buf.create_tag("NOTICE", foreground="#3498db")
            buf.create_tag("INFO") 
            
            buf.create_tag("tag_DEBUG", foreground="#7f8c8d", weight=700)
            buf.create_tag("tag_ERROR", foreground="#c0392b", weight=700)
            buf.create_tag("tag_WARNING", foreground="#d35400", weight=700)
            buf.create_tag("tag_NOTICE", foreground="#2980b9", weight=700)
            buf.create_tag("tag_INFO", foreground="#27ae60", weight=700)
            
            buf.create_tag("divider", justification=Gtk.Justification.CENTER, foreground="#95a5a6", weight=700)
            
            tag_link = buf.create_tag("LINK", underline=Pango.Underline.SINGLE)
            
            for code, color in [("30", "gray"), ("31", "#e74c3c"), ("32", "#2ecc71"), ("33", "#f1c40f"), ("34", "#3498db"), ("35", "#9b59b6"), ("36", "#1abc9c"), ("37", "white"), ("90", "gray")]:
                buf.create_tag(f"ansi_{code}", foreground=color)
            
            def _on_click(view, event, b=buf):
                if event.type == Gdk.EventType.BUTTON_RELEASE and event.button == 1:
                    try:
                        x, y = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, int(event.x), int(event.y))
                        _, it = view.get_iter_at_position(x, y)
                        if it.has_tag(tag_link):
                            start, end = it.copy(), it.copy()
                            if not start.starts_tag(tag_link): start.backward_to_tag_toggle(tag_link)
                            if not end.ends_tag(tag_link): end.forward_to_tag_toggle(tag_link)
                            subprocess.Popen(['xdg-open', b.get_text(start, end, False)])
                            return True
                    except: pass
                return False
                
            def _on_hover(view, event):
                try:
                        x, y = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, int(event.x), int(event.y))
                        _, it = view.get_iter_at_position(x, y)
                        cursor = Gdk.Cursor.new(Gdk.CursorType.HAND2) if it.has_tag(tag_link) else Gdk.Cursor.new(Gdk.CursorType.XTERM)
                        view.get_window(Gtk.TextWindowType.TEXT).set_cursor(cursor)
                except: pass
                return False
                
            tv.connect("button-release-event", _on_click)
            tv.connect("motion-notify-event", _on_hover)
            tv.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
            
            sw = Gtk.ScrolledWindow(); sw.set_shadow_type(Gtk.ShadowType.IN); sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC); sw.add(tv); vbox.pack_start(sw, True, True, 0)
            self.notebook.append_page(vbox, Gtk.Label(label=p.upper()))
            
            # --- CRITICAL FIX: Create ONE persistent scroll mark to prevent rendering crashes ---
            scroll_mark = buf.create_mark("scroll_end", buf.get_end_iter(), False)
            
            self.tabs[p] = {'vbox': vbox, 'buffer': buf, 'tv': tv, 'sw': sw, 'scroll_mark': scroll_mark, 'prog': prog, 'detail_lbl': detail_lbl, 'progress_lbl': progress_lbl, 'transfer_lbl': transfer_lbl, 'transfer_box': transfer_box}
            log_formatter.start_live_feed(p, lambda a, x=p: GLib.idle_add(self.update_logs, x, a))
            
        self.notebook.connect("switch-page", lambda n, page, page_num: self.change_callback(n.get_tab_label(page).get_text()) if self.change_callback else None)

    def focus_profile(self, profile):
        if profile in self.tabs and (pn := self.notebook.page_num(self.tabs[profile]['vbox'])) != -1: self.notebook.set_current_page(pn)

    def reload_log(self, profile):
        if not (tab := self.tabs.get(profile)): return
        tab['buffer'].set_text("")
        if os.path.exists(path := os.path.join(LOG_DIR, f"{profile}_sync.jsonl")):
            try: GLib.idle_add(self.update_logs, profile,[a for line in open(path, "r", encoding="utf-8") for a in log_formatter.format_line(line)])
            except: pass

    def toggle_wrap(self, profile, btn):
        if tab := self.tabs.get(profile):
            tv = tab['tv']
            tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if btn.get_active() else Gtk.WrapMode.NONE)

    def set_status(self, profile, is_running):
        if tab := self.tabs.get(profile): 
            if not is_running:
                GLib.idle_add(tab['prog'].set_fraction, 0.0)
                GLib.idle_add(tab['progress_lbl'].set_markup, "<span size='small' color='gray'>Finished</span>")
                GLib.idle_add(tab['detail_lbl'].set_markup, "<span size='small' color='gray'>Speed: 0 B/s | ETA: -</span>")
                if 'transfer_lbl' in tab:
                    GLib.idle_add(tab['transfer_lbl'].set_label, "0")
                    GLib.idle_add(lambda: [tab['transfer_box'].remove(c) for c in tab['transfer_box'].get_children()] or False)
            else:
                GLib.idle_add(tab['progress_lbl'].set_markup, "<span size='small' color='gray'>Syncing...</span>")

    def update_logs(self, profile, actions):
        if not (tab := self.tabs.get(profile)): return False
        scroll = False
        buf = tab['buffer']
        for act in actions:
            k = act[0]
            if k == "log":
                if len(act) == 4:
                    prefix, msg, level = act[1], act[2], act[3]
                    if not buf.get_tag_table().lookup(level): level = "INFO"
                    buf.insert_with_tags_by_name(buf.get_end_iter(), prefix, f"tag_{level}")
                else:
                    msg = act[1]
                    level = act[2] if len(act) > 2 else "INFO"
                    if not buf.get_tag_table().lookup(level): level = "INFO" 
                
                import re
                ansi_re = re.compile(r'\x1B\[([0-9;]*)[mK]')
                text_parts = ansi_re.split(str(msg))
                
                current_ansi = None
                for i, part in enumerate(text_parts):
                    if i % 2 == 1:
                        if part in ["0", ""]: current_ansi = None
                        else:
                            for c in part.split(';'):
                                if c in ['30','31','32','33','34','35','36','37','90']:
                                    current_ansi = f"ansi_{c}"
                    else:
                        if part:
                            tags = [level]
                            if current_ansi: tags.append(current_ansi)
                            
                            url_parts = re.split(r'(https?://[^\s<>]+[^.,:;\"\s<>])', part)
                            for u in url_parts:
                                if u.startswith('http'):
                                    buf.insert_with_tags_by_name(buf.get_end_iter(), u, *(tags + ["LINK"]))
                                elif u:
                                    buf.insert_with_tags_by_name(buf.get_end_iter(), u, *tags)
                scroll = True
            elif k == "divider":
                ts = act[1]
                try:
                    dt = datetime.datetime.strptime(ts, "%Y-%m-%d %I:%M:%S %p")
                    now = datetime.datetime.now()
                    time_part = dt.strftime("%I:%M:%S %p")
                    if dt.date() == now.date():
                        ts_display = f"Today at {time_part}"
                    elif dt.date() == (now.date() - datetime.timedelta(days=1)):
                        ts_display = f"Yesterday at {time_part}"
                    else:
                        ts_display = dt.strftime("%b %d, %Y at %I:%M:%S %p")
                except:
                    ts_display = ts
                
                buf.insert_with_tags_by_name(buf.get_end_iter(), f"\n━━━━━━━━━━━ Session: {ts_display} ━━━━━━━━━━━\n\n", "divider")
                scroll = True
            elif k == "stats":
                d = act[1]
                def fmt_b(b):
                    for u in ['B','KB','MB','GB','TB']:
                        if b < 1024: return f"{b:.1f} {u}"
                        b /= 1024
                    return f"{b:.1f} PB"

                if "bytes" in d:
                    b_tot, b_done = d.get('totalBytes', 0), d.get('bytes', 0)
                    frac = b_done / b_tot if b_tot > 0 else 0.0
                    tab['prog'].set_fraction(frac)
                    tab['progress_lbl'].set_markup(f"<span size='small' color='gray'>{fmt_b(b_done)} / {fmt_b(b_tot)} ({int(frac*100)}%)</span>")
                    eta = d.get('eta')
                    tab['detail_lbl'].set_markup(f"<span size='small' color='gray'>Speed: {fmt_b(d.get('speed',0))}/s | ETA: {f'{eta}s' if eta is not None else '-'} | Checks: {d.get('checks',0)} | Deletes: {d.get('deletes',0)}</span>")
                    
                    trs = d.get('transferring', [])
                    tab['transfer_lbl'].set_text(str(len(trs)))
                    for c in tab['transfer_box'].get_children(): tab['transfer_box'].remove(c)
                    
                    for t in trs:
                        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                        tl = Gtk.Label(label=f"{t.get('name', '...')}", xalign=0, ellipsize=Pango.EllipsizeMode.START)
                        tl.set_max_width_chars(50)
                        tp = Gtk.ProgressBar(); tp.set_fraction(t.get('percentage', 0)/100.0); tp.set_show_text(True); tp.set_text(f"{t.get('percentage', 0)}%")
                        hb.pack_start(tl, True, True, 0); hb.pack_end(tp, False, False, 0)
                        tab['transfer_box'].pack_start(hb, False, False, 0)
                    tab['transfer_box'].show_all()
                else:
                    tab['progress_lbl'].set_markup(f"<span size='small' color='gray'>{d.get('msg', 'Syncing...')}</span>")
        if scroll: 
            # --- CRITICAL FIX: Move the single mark instead of creating thousands ---
            buf.move_mark(tab['scroll_mark'], buf.get_end_iter())
            tab['tv'].scroll_to_mark(tab['scroll_mark'], 0.0, False, 0.0, 1.0)
        return False