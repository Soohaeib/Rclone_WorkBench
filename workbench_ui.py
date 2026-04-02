import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import workbench_blueprint as blueprint
import rules_engine
import config_manager

class InventoryWorkbench(Gtk.Window):
    def __init__(self, profiles):
        super().__init__(title="Rclone Workbench")
        self.set_default_size(1000, 700)
        
        # Data State
        self.profiles = profiles
        self.active_profile = profiles[0] if profiles else None
        self.global_cfg = config_manager.load_config()
        
        # Build combined schema lookup for the Rules Engine
        self.items_lookup = rules_engine.get_full_lookup()
        
        self._build_ui()

    def _build_ui(self):
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(main_box)

        # 1. Sidebar: Profile Selection
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=200)
        sidebar.get_style_context().add_class("sidebar")
        
        profile_list = Gtk.ListBox()
        profile_list.connect("row-selected", self.on_profile_changed)
        for p in self.profiles:
            label = Gtk.Label(label=p, margin=15, xalign=0)
            row = Gtk.ListBoxRow()
            row.add(label)
            profile_list.add(row)
        
        sidebar.pack_start(profile_list, True, True, 0)
        main_box.pack_start(sidebar, False, False, 0)

        # 2. Right Side: The Inventory Canvas
        self.canvas = Gtk.ScrolledWindow()
        self.flowbox = Gtk.FlowBox(valign=Gtk.Align.START, max_children_per_line=3, selection_mode=Gtk.SelectionMode.NONE)
        self.canvas.add(self.flowbox)
        main_box.pack_start(self.canvas, True, True, 0)

        self.refresh_canvas()

    def on_profile_changed(self, listbox, row):
        if row:
            self.active_profile = row.get_child().get_label()
            self.refresh_canvas()

    def refresh_canvas(self):
        """Clears and rebuilds the card inventory for the active profile."""
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)

        # Get saved state for this profile
        profile_state = self.global_cfg.get('remote_configs', {}).get(self.active_profile, {})
        active_keys = [k for k, v in profile_state.items() if v is True]

        # Process through Rules Engine to handle dependencies/conflicts
        final_keys, forced, locked = rules_engine.evaluate_canvas(active_keys)

        # Render Smart Presets (Procedures)
        for card in blueprint.SMART_SCHEMA.get("Smart Automations", []):
            self.flowbox.add(self._create_card(card, final_keys, forced, locked))

        # Render Tool Categories
        for category, cards in blueprint.CONFIG_SCHEMA.items():
            for card in cards:
                self.flowbox.add(self._create_card(card, final_keys, forced, locked))
        
        self.show_all()

    def _create_card(self, info, active_keys, forced, locked):
        """Creates a UI card based on the Blueprint schema."""
        frame = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=10)
        
        lbl = Gtk.Label(label=f"<b>{info['label']}</b>", use_markup=True, xalign=0)
        box.pack_start(lbl, False, False, 5)
        
        desc = Gtk.Label(label=info.get('desc', ''), wrap=True, xalign=0)
        desc.set_opacity(0.7)
        box.pack_start(desc, False, False, 5)

        # Toggle switch for the tool/procedure
        switch = Gtk.Switch(active=(info['key'] in active_keys or info['key'] in forced))
        switch.set_sensitive(info['key'] not in locked)
        switch.connect("state-set", self.on_toggle, info['key'])
        
        box.pack_end(switch, False, False, 0)
        frame.add(box)
        return frame

    def on_toggle(self, switch, state, key):
        # Update config and re-evaluate rules
        # Logic for saving and re-running rules goes here
        return False