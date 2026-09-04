import copy
from typing import List, Tuple, Dict, Optional
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango
from .base import BasePage
from mannux.backend.config import ConfigManager
from mannux.backend.power import PowerManager
from mannux.backend.display import (
    DisplayManager,
    MonitorInfo,
    TRANSFORM_OPTIONS,
    SCALE_PRESETS
)
from mannux.backend.logger import log

class DisplaysPage(BasePage):
    tag = "displays"
    title = "Displays"
    icon_name = "video-display-symbolic"

    def __init__(self, config_mgr: ConfigManager, power_mgr: PowerManager, display_mgr: Optional[DisplayManager] = None, toast_callback=None, **kwargs):
        super().__init__(config_mgr, power_mgr, **kwargs)
        self.display_mgr = display_mgr or DisplayManager.get_instance()
        self.toast_callback = toast_callback

        self.monitors: List[MonitorInfo] = []
        self._active_applied_snapshot: List[MonitorInfo] = []
        self.current_monitor_idx: int = 0
        self._updating_ui: bool = False
        self._revert_timer_id: Optional[int] = None
        self._revert_seconds_left: int = 15
        self._revert_dialog: Optional[Adw.AlertDialog] = None

        self._build_ui()
        self.refresh_monitors()

    def _build_ui(self):
        # -------------------------------------------------------------
        # 1. Monitor Header & Multi-Monitor Switcher
        # -------------------------------------------------------------
        self.header_group = Adw.PreferencesGroup()
        self.header_group.set_title("Connected Displays")
        self.header_group.set_description("Manage screen resolution, fractional scaling, and orientation")
        self.add(self.header_group)

        # Multi-monitor selector row
        self.selector_row = Adw.ComboRow()
        self.selector_row.set_title("Active Display")
        self.selector_row.set_subtitle("Select which monitor to configure")
        self.selector_row.connect("notify::selected", self._on_monitor_selected)
        self.header_group.add(self.selector_row)

        # Display Summary Card
        self.summary_row = Adw.ActionRow()
        self.summary_row.set_title("Detecting display...")
        self.summary_row.set_subtitle("Querying Hyprland IPC...")
        self.summary_row.set_icon_name("video-display-symbolic")

        refresh_btn = Gtk.Button(label="Detect Displays")
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.add_css_class("flat")
        refresh_btn.connect("clicked", lambda b: self.refresh_monitors())
        self.summary_row.add_suffix(refresh_btn)
        self.header_group.add(self.summary_row)

        # -------------------------------------------------------------
        # 2. Display Configuration Properties
        # -------------------------------------------------------------
        self.props_group = Adw.PreferencesGroup()
        self.props_group.set_title("Display Settings")
        self.add(self.props_group)

        # Enable/Disable switch
        self.enable_switch = Adw.SwitchRow()
        self.enable_switch.set_title("Enable Display")
        self.enable_switch.set_subtitle("Turn screen output on or off")
        self.enable_switch.set_icon_name("display-brightness-symbolic")
        self.enable_switch.connect("notify::active", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.enable_switch)

        # Resolution dropdown
        self.res_combo = Adw.ComboRow()
        self.res_combo.set_title("Resolution")
        self.res_combo.set_subtitle("Screen dimensions and aspect ratio")
        self.res_combo.connect("notify::selected", self._on_resolution_selected)
        self.props_group.add(self.res_combo)

        # Refresh Rate dropdown
        self.rate_combo = Adw.ComboRow()
        self.rate_combo.set_title("Refresh Rate")
        self.rate_combo.set_subtitle("Display frame rate in Hertz (Hz)")
        self.rate_combo.connect("notify::selected", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.rate_combo)

        # Scale dropdown
        scale_model = Gtk.StringList.new([c[0] for c in SCALE_PRESETS])
        self.scale_combo = Adw.ComboRow()
        self.scale_combo.set_title("Display Scaling")
        self.scale_combo.set_subtitle("Scale user interface elements")
        self.scale_combo.set_model(scale_model)
        self.scale_combo.connect("notify::selected", self._on_scale_combo_selected)
        self.props_group.add(self.scale_combo)

        # Custom Scale Spin
        self.scale_spin = Adw.SpinRow.new_with_range(0.5, 4.0, 0.05)
        self.scale_spin.set_title("Custom Scale Factor")
        self.scale_spin.set_subtitle("Exact fractional scaling multiplier (e.g. 1.25)")
        self.scale_spin.set_visible(False)
        self.scale_spin.connect("notify::value", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.scale_spin)

        # Orientation dropdown
        transform_model = Gtk.StringList.new([t[0] for t in TRANSFORM_OPTIONS])
        self.transform_combo = Adw.ComboRow()
        self.transform_combo.set_title("Orientation")
        self.transform_combo.set_subtitle("Rotate screen orientation")
        self.transform_combo.set_model(transform_model)
        self.transform_combo.connect("notify::selected", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.transform_combo)

        # Adaptive Sync (VRR)
        self.vrr_switch = Adw.SwitchRow()
        self.vrr_switch.set_title("Variable Refresh Rate (VRR / FreeSync)")
        self.vrr_switch.set_subtitle("Dynamically match monitor refresh rate to GPU frames")
        self.vrr_switch.connect("notify::active", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.vrr_switch)

        # -------------------------------------------------------------
        # 3. Apply Action Row
        # -------------------------------------------------------------
        self.actions_group = Adw.PreferencesGroup()
        self.add(self.actions_group)

        apply_row = Adw.ActionRow()
        apply_row.set_title("Apply Display Settings")
        apply_row.set_subtitle("Test settings with a 15-second automatic rollback timer")

        self.apply_btn = Gtk.Button(label="Apply Changes")
        self.apply_btn.set_valign(Gtk.Align.CENTER)
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", self._on_apply_clicked)
        apply_row.add_suffix(self.apply_btn)
        self.actions_group.add(apply_row)

        # -------------------------------------------------------------
        # 4. Advanced & Code Preview
        # -------------------------------------------------------------
        self.advanced_group = Adw.PreferencesGroup()
        self.advanced_group.set_title("Configuration")
        self.add(self.advanced_group)

        self.preview_expander = Adw.ExpanderRow()
        self.preview_expander.set_title("View Monitor Configuration")
        self.preview_expander.set_subtitle("Inspect generated Hyprland monitor syntax")
        self.preview_expander.set_icon_name("text-x-generic-symbolic")

        preview_scroller = Gtk.ScrolledWindow()
        preview_scroller.set_min_content_height(140)
        preview_scroller.set_max_content_height(260)
        preview_scroller.set_margin_top(6)
        preview_scroller.set_margin_bottom(6)
        preview_scroller.set_margin_start(12)
        preview_scroller.set_margin_end(12)

        self.preview_buffer = Gtk.TextBuffer()
        self.preview_view = Gtk.TextView.new_with_buffer(self.preview_buffer)
        self.preview_view.set_editable(False)
        self.preview_view.set_cursor_visible(False)
        self.preview_view.set_monospace(True)
        self.preview_view.add_css_class("card")
        preview_scroller.set_child(self.preview_view)

        self.preview_expander.add_row(preview_scroller)
        self.advanced_group.add(self.preview_expander)

    def refresh_monitors(self):
        self.monitors = self.display_mgr.get_monitors()
        self._active_applied_snapshot = copy.deepcopy(self.monitors)

        if not self.monitors:
            self.summary_row.set_title("No Monitors Detected")
            self.summary_row.set_subtitle("Ensure Hyprland is active")
            self.props_group.set_sensitive(False)
            self.actions_group.set_sensitive(False)
            return

        self.props_group.set_sensitive(True)
        self.actions_group.set_sensitive(True)

        # Populate selector row
        self._updating_ui = True
        titles = []
        for m in self.monitors:
            focus_str = " (Focused)" if m.focused else ""
            desc = m.description or m.name
            titles.append(f"{m.name}: {desc}{focus_str}")

        model = Gtk.StringList.new(titles)
        self.selector_row.set_model(model)
        self.selector_row.set_visible(len(self.monitors) > 1)

        # Default to focused or first monitor
        focused_idx = 0
        for i, m in enumerate(self.monitors):
            if m.focused:
                focused_idx = i
                break
        self.current_monitor_idx = focused_idx
        self.selector_row.set_selected(focused_idx)

        self._load_monitor_to_ui(self.monitors[focused_idx])
        self._updating_ui = False
        self._update_preview()

    def _get_current_monitor(self) -> Optional[MonitorInfo]:
        if 0 <= self.current_monitor_idx < len(self.monitors):
            return self.monitors[self.current_monitor_idx]
        return None

    def _load_monitor_to_ui(self, mon: MonitorInfo):
        self._updating_ui = True

        # Summary Row
        make_model = f"{mon.make} {mon.model}".strip() or mon.description or mon.name
        self.summary_row.set_title(f"{mon.name} — {make_model}")
        self.summary_row.set_subtitle(f"Active Mode: {mon.resolution_str} @ {mon.refresh_rate:.2f}Hz (Scale {mon.scale:.2f}x)")

        # Enable switch
        self.enable_switch.set_active(not mon.disabled)
        self.enable_switch.set_sensitive(len(self.monitors) > 1)

        # Resolutions and Rates
        res_map = mon.get_resolutions_and_rates()
        sorted_resolutions = sorted(res_map.keys(), key=lambda r: (r[0] * r[1], r[0]), reverse=True)

        res_labels = []
        curr_res_idx = 0
        for idx, (w, h) in enumerate(sorted_resolutions):
            temp_mon = MonitorInfo(
                id=mon.id, name=mon.name, description="", make="", model="",
                width=w, height=h, refresh_rate=60, x=0, y=0, scale=1, transform=0,
                focused=False, dpms_status=True, vrr=False
            )
            res_labels.append(temp_mon.resolution_str)
            if w == mon.width and h == mon.height:
                curr_res_idx = idx

        res_model = Gtk.StringList.new(res_labels)
        self.res_combo.set_model(res_model)
        self.res_combo.set_selected(curr_res_idx)

        # Populate Rates for selected resolution
        selected_res = sorted_resolutions[curr_res_idx] if sorted_resolutions else (mon.width, mon.height)
        self._populate_rates_for_res(selected_res, res_map, mon.refresh_rate)

        # Scale
        scale_idx = len(SCALE_PRESETS) - 1 # Custom by default
        for idx, (_, val) in enumerate(SCALE_PRESETS[:-1]):
            if abs(val - mon.scale) < 0.01:
                scale_idx = idx
                break
        self.scale_combo.set_selected(scale_idx)
        self.scale_spin.set_value(mon.scale)
        self.scale_spin.set_visible(scale_idx == len(SCALE_PRESETS) - 1)

        # Transform
        t_idx = 0
        for idx, (_, val) in enumerate(TRANSFORM_OPTIONS):
            if val == mon.transform:
                t_idx = idx
                break
        self.transform_combo.set_selected(t_idx)

        # VRR
        self.vrr_switch.set_active(mon.vrr)

        self._updating_ui = False

    def _populate_rates_for_res(self, res: Tuple[int, int], res_map: Dict[Tuple[int, int], List[float]], current_rate: float):
        rates = res_map.get(res, [current_rate])
        rate_labels = [f"{r:.2f} Hz" for r in rates]
        rate_model = Gtk.StringList.new(rate_labels)
        self.rate_combo.set_model(rate_model)

        curr_rate_idx = 0
        for idx, r in enumerate(rates):
            if abs(r - current_rate) < 0.1:
                curr_rate_idx = idx
                break
        self.rate_combo.set_selected(curr_rate_idx)

    def _on_monitor_selected(self, combo, param):
        if self._updating_ui:
            return
        idx = combo.get_selected()
        if 0 <= idx < len(self.monitors):
            self.current_monitor_idx = idx
            self._load_monitor_to_ui(self.monitors[idx])
            self._update_preview()

    def _on_resolution_selected(self, combo, param):
        if self._updating_ui:
            return
        mon = self._get_current_monitor()
        if not mon:
            return

        res_map = mon.get_resolutions_and_rates()
        sorted_resolutions = sorted(res_map.keys(), key=lambda r: (r[0] * r[1], r[0]), reverse=True)
        idx = combo.get_selected()
        if 0 <= idx < len(sorted_resolutions):
            sel_res = sorted_resolutions[idx]
            self._populate_rates_for_res(sel_res, res_map, mon.refresh_rate)
            self._on_setting_changed()

    def _on_scale_combo_selected(self, combo, param):
        if self._updating_ui:
            return
        idx = combo.get_selected()
        is_custom = (idx == len(SCALE_PRESETS) - 1)
        self.scale_spin.set_visible(is_custom)
        if not is_custom:
            preset_val = SCALE_PRESETS[idx][1]
            self.scale_spin.set_value(preset_val)
        self._on_setting_changed()

    def _on_setting_changed(self):
        if self._updating_ui:
            return
        mon = self._get_current_monitor()
        if not mon:
            return

        # Update monitor object in memory
        mon.disabled = not self.enable_switch.get_active()

        res_map = mon.get_resolutions_and_rates()
        sorted_resolutions = sorted(res_map.keys(), key=lambda r: (r[0] * r[1], r[0]), reverse=True)
        res_idx = self.res_combo.get_selected()
        if 0 <= res_idx < len(sorted_resolutions):
            w, h = sorted_resolutions[res_idx]
            mon.width = w
            mon.height = h

        rates = res_map.get((mon.width, mon.height), [mon.refresh_rate])
        rate_idx = self.rate_combo.get_selected()
        if 0 <= rate_idx < len(rates):
            mon.refresh_rate = rates[rate_idx]

        scale_idx = self.scale_combo.get_selected()
        if scale_idx == len(SCALE_PRESETS) - 1:
            mon.scale = float(self.scale_spin.get_value())
        else:
            mon.scale = SCALE_PRESETS[scale_idx][1]

        t_idx = self.transform_combo.get_selected()
        if 0 <= t_idx < len(TRANSFORM_OPTIONS):
            mon.transform = TRANSFORM_OPTIONS[t_idx][1]

        mon.vrr = self.vrr_switch.get_active()

        self._update_preview()

    def _update_preview(self):
        if self.display_mgr.is_lua_mode():
            content = self.display_mgr.generate_lua_config(self.monitors)
        else:
            content = self.display_mgr.generate_legacy_config(self.monitors)
        self.preview_buffer.set_text(content)

    def _on_apply_clicked(self, widget):
        mon = self._get_current_monitor()
        if not mon:
            return

        # Apply live settings
        success = self.display_mgr.apply_all(self.monitors)
        if not success:
            if self.toast_callback:
                self.toast_callback("Failed to apply monitor settings via Hyprland IPC")
            return

        # Start 15s Safety Revert Countdown Dialog
        self._start_revert_countdown()

    def _start_revert_countdown(self):
        self._stop_revert_timer()
        self._revert_seconds_left = 15

        self._revert_dialog = Adw.AlertDialog.new(
            "Keep These Display Settings?",
            f"Reverting to previous settings in {self._revert_seconds_left} seconds..."
        )
        self._revert_dialog.add_response("revert", "Revert Now")
        self._revert_dialog.add_response("keep", "Keep Changes")
        self._revert_dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        self._revert_dialog.set_response_appearance("revert", Adw.ResponseAppearance.DESTRUCTIVE)
        self._revert_dialog.set_default_response("keep")
        self._revert_dialog.set_close_response("revert")

        def on_dialog_response(d, result):
            self._stop_revert_timer()
            try:
                resp = d.choose_finish(result)
            except Exception as e:
                log.error(f"Error reading dialog response: {e}")
                resp = "revert"

            if resp == "keep":
                log.info("Display settings confirmed by user. Saving configuration permanently...")
                self.display_mgr.save_config(self.monitors)
                self._active_applied_snapshot = copy.deepcopy(self.monitors)
                if self.toast_callback:
                    self.toast_callback("Display settings saved successfully!")
                self._load_monitor_to_ui(self.monitors[self.current_monitor_idx])
                self._update_preview()
            else:
                log.info("Display settings reverted by user or timeout.")
                self._revert_settings()

        root = self.get_root()
        self._revert_dialog.choose(root, None, on_dialog_response)

        # Start 1-second interval timer
        self._revert_timer_id = GLib.timeout_add_seconds(1, self._countdown_tick)

    def _countdown_tick(self) -> bool:
        self._revert_seconds_left -= 1
        if self._revert_seconds_left <= 0:
            self._stop_revert_timer()
            if self._revert_dialog:
                # Force closing triggers choose_finish with close_response ("revert")
                self._revert_dialog.force_close()
            else:
                self._revert_settings()
            return False

        if self._revert_dialog:
            self._revert_dialog.set_body(f"Reverting to previous settings in {self._revert_seconds_left} seconds...")
        return True

    def _stop_revert_timer(self):
        if self._revert_timer_id:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None

    def _revert_settings(self):
        self._stop_revert_timer()
        log.info("Reverting display settings to baseline snapshot")
        self.monitors = copy.deepcopy(self._active_applied_snapshot)
        self.display_mgr.apply_all(self.monitors)
        self._load_monitor_to_ui(self.monitors[self.current_monitor_idx])
        self._update_preview()
        if self.toast_callback:
            self.toast_callback("Display settings reverted.")
