import os
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
    SCALE_PRESETS,
    BITDEPTH_OPTIONS,
    VRR_OPTIONS,
    CM_PRESETS
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
        # 1. Connected Displays Header & Selector
        # -------------------------------------------------------------
        self.header_group = Adw.PreferencesGroup()
        self.header_group.set_title("Connected Displays")
        self.header_group.set_description("Manage screen resolution, scaling, orientation, color profiles, and VRR")
        self.add(self.header_group)

        self.selector_row = Adw.ComboRow()
        self.selector_row.set_title("Active Display")
        self.selector_row.set_subtitle("Select which monitor to configure")
        self.selector_row.connect("notify::selected", self._on_monitor_selected)
        self.header_group.add(self.selector_row)

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
        # 2. Display Properties
        # -------------------------------------------------------------
        self.props_group = Adw.PreferencesGroup()
        self.props_group.set_title("Display Properties")
        self.add(self.props_group)

        # Enable/Disable switch
        self.enable_switch = Adw.SwitchRow()
        self.enable_switch.set_title("Enable Display")
        self.enable_switch.set_subtitle("Turn screen output on or off")
        self.enable_switch.set_icon_name("display-brightness-symbolic")
        self.enable_switch.connect("notify::active", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.enable_switch)

        # Mirroring row
        self.mirror_combo = Adw.ComboRow()
        self.mirror_combo.set_title("Mirror Display")
        self.mirror_combo.set_subtitle("Clone output from another display")
        self.mirror_combo.connect("notify::selected", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.mirror_combo)

        # Resolution dropdown
        self.res_combo = Adw.ComboRow()
        self.res_combo.set_title("Resolution")
        self.res_combo.set_subtitle("Screen dimensions and aspect ratio")
        self.res_combo.connect("notify::selected", self._on_resolution_selected)
        self.props_group.add(self.res_combo)

        # Refresh Rate dropdown
        self.rate_combo = Adw.ComboRow()
        self.rate_combo.set_title("Refresh Rate")
        self.rate_combo.set_subtitle("Display refresh frequency in Hertz (Hz)")
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

        # Color Depth / Bit Depth
        bitdepth_model = Gtk.StringList.new([b[0] for b in BITDEPTH_OPTIONS])
        self.bitdepth_combo = Adw.ComboRow()
        self.bitdepth_combo.set_title("Color Depth")
        self.bitdepth_combo.set_subtitle("Pixel color bit depth")
        self.bitdepth_combo.set_model(bitdepth_model)
        self.bitdepth_combo.connect("notify::selected", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.bitdepth_combo)

        # Advanced VRR
        vrr_model = Gtk.StringList.new([v[0] for v in VRR_OPTIONS])
        self.vrr_combo = Adw.ComboRow()
        self.vrr_combo.set_title("Variable Refresh Rate (VRR / FreeSync)")
        self.vrr_combo.set_subtitle("Adaptive sync frame delivery mode")
        self.vrr_combo.set_model(vrr_model)
        self.vrr_combo.connect("notify::selected", lambda w, p: self._on_setting_changed())
        self.props_group.add(self.vrr_combo)

        # -------------------------------------------------------------
        # 3. Color Management & HDR
        # -------------------------------------------------------------
        self.cm_group = Adw.PreferencesGroup()
        self.cm_group.set_title("Color Management & HDR")
        self.cm_group.set_description("Configure color profiles, wide gamut, and HDR tone mapping")
        self.add(self.cm_group)

        # Color profile preset
        cm_model = Gtk.StringList.new([c[0] for c in CM_PRESETS])
        self.cm_combo = Adw.ComboRow()
        self.cm_combo.set_title("Color Profile (Color Space)")
        self.cm_combo.set_subtitle("Color management gamut preset")
        self.cm_combo.set_model(cm_model)
        self.cm_combo.connect("notify::selected", self._on_cm_selected)
        self.cm_group.add(self.cm_combo)

        # Custom ICC Profile Row
        self.icc_row = Adw.ActionRow()
        self.icc_row.set_title("ICC Color Calibration File")
        self.icc_row.set_subtitle("No ICC file selected (Standard primaries)")
        self.icc_row.set_visible(False)

        icc_btn = Gtk.Button(label="Select Profile...")
        icc_btn.set_icon_name("document-open-symbolic")
        icc_btn.set_valign(Gtk.Align.CENTER)
        icc_btn.connect("clicked", self._on_select_icc_clicked)
        self.icc_row.add_suffix(icc_btn)
        self.cm_group.add(self.icc_row)

        # SDR Brightness in HDR mode
        self.sdr_bright_spin = Adw.SpinRow.new_with_range(0.5, 3.0, 0.05)
        self.sdr_bright_spin.set_title("SDR Content Brightness (HDR)")
        self.sdr_bright_spin.set_subtitle("Multiplier for standard dynamic range content under HDR")
        self.sdr_bright_spin.connect("notify::value", lambda w, p: self._on_setting_changed())
        self.cm_group.add(self.sdr_bright_spin)

        # SDR Saturation in HDR mode
        self.sdr_sat_spin = Adw.SpinRow.new_with_range(0.5, 2.0, 0.05)
        self.sdr_sat_spin.set_title("SDR Content Saturation (HDR)")
        self.sdr_sat_spin.set_subtitle("Color vibrancy multiplier for SDR content")
        self.sdr_sat_spin.connect("notify::value", lambda w, p: self._on_setting_changed())
        self.cm_group.add(self.sdr_sat_spin)

        # -------------------------------------------------------------
        # 4. Apply Action Row
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
        # 5. Advanced & Code Preview
        # -------------------------------------------------------------
        self.advanced_group = Adw.PreferencesGroup()
        self.advanced_group.set_title("Configuration Preview")
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
            self.cm_group.set_sensitive(False)
            self.actions_group.set_sensitive(False)
            return

        self.props_group.set_sensitive(True)
        self.cm_group.set_sensitive(True)
        self.actions_group.set_sensitive(True)

        self._updating_ui = True
        titles = []
        for m in self.monitors:
            focus_str = " (Focused)" if m.focused else ""
            desc = m.description or m.name
            titles.append(f"{m.name}: {desc}{focus_str}")

        model = Gtk.StringList.new(titles)
        self.selector_row.set_model(model)
        self.selector_row.set_visible(len(self.monitors) > 1)

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

        make_model = f"{mon.make} {mon.model}".strip() or mon.description or mon.name
        self.summary_row.set_title(f"{mon.name} — {make_model}")
        self.summary_row.set_subtitle(f"Active Mode: {mon.resolution_str} @ {mon.refresh_rate:.2f}Hz (Scale {mon.scale:.2f}x)")

        self.enable_switch.set_active(not mon.disabled)
        self.enable_switch.set_sensitive(len(self.monitors) > 1)

        # Mirroring
        mirror_choices = ["None (Independent Display)"]
        curr_mirror_idx = 0
        for m in self.monitors:
            if m.name != mon.name:
                mirror_choices.append(f"Mirror {m.name}")
                if mon.mirror_of == m.name:
                    curr_mirror_idx = len(mirror_choices) - 1

        mirror_model = Gtk.StringList.new(mirror_choices)
        self.mirror_combo.set_model(mirror_model)
        self.mirror_combo.set_selected(curr_mirror_idx)
        self.mirror_combo.set_visible(len(self.monitors) > 1)

        # Resolutions and Rates
        res_map = mon.get_resolutions_and_rates()
        sorted_resolutions = sorted(res_map.keys(), key=lambda r: (r[0] * r[1], r[0]), reverse=True)

        res_labels = []
        curr_res_idx = 0
        for idx, (w, h) in enumerate(sorted_resolutions):
            temp_mon = MonitorInfo(
                id=mon.id, name=mon.name, description="", make="", model="",
                width=w, height=h, refresh_rate=60, x=0, y=0, scale=1, transform=0,
                focused=False, dpms_status=True, vrr=0
            )
            res_labels.append(temp_mon.resolution_str)
            if w == mon.width and h == mon.height:
                curr_res_idx = idx

        res_model = Gtk.StringList.new(res_labels)
        self.res_combo.set_model(res_model)
        self.res_combo.set_selected(curr_res_idx)

        selected_res = sorted_resolutions[curr_res_idx] if sorted_resolutions else (mon.width, mon.height)
        self._populate_rates_for_res(selected_res, res_map, mon.refresh_rate)

        # Scale
        scale_idx = len(SCALE_PRESETS) - 1
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

        # Bit Depth
        bd_idx = 0
        for idx, (_, val) in enumerate(BITDEPTH_OPTIONS):
            if val == mon.bitdepth:
                bd_idx = idx
                break
        self.bitdepth_combo.set_selected(bd_idx)

        # VRR
        vrr_idx = 0
        for idx, (_, val) in enumerate(VRR_OPTIONS):
            if val == mon.vrr:
                vrr_idx = idx
                break
        self.vrr_combo.set_selected(vrr_idx)

        # Color Management
        cm_idx = 0
        if mon.icc_profile:
            cm_idx = len(CM_PRESETS) - 1 # Custom ICC
        else:
            for idx, (_, val) in enumerate(CM_PRESETS[:-1]):
                if val == mon.cm:
                    cm_idx = idx
                    break
        self.cm_combo.set_selected(cm_idx)
        self.icc_row.set_visible(cm_idx == len(CM_PRESETS) - 1)
        if mon.icc_profile:
            self.icc_row.set_subtitle(mon.icc_profile)

        self.sdr_bright_spin.set_value(mon.sdr_brightness)
        self.sdr_sat_spin.set_value(mon.sdr_saturation)

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

    def _on_cm_selected(self, combo, param):
        if self._updating_ui:
            return
        idx = combo.get_selected()
        is_icc = (idx == len(CM_PRESETS) - 1)
        self.icc_row.set_visible(is_icc)
        self._on_setting_changed()

    def _on_select_icc_clicked(self, widget):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Select ICC/ICM Color Profile")
        filter_icc = Gtk.FileFilter()
        filter_icc.set_name("Color Profiles (*.icc, *.icm)")
        filter_icc.add_pattern("*.icc")
        filter_icc.add_pattern("*.icm")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_icc)
        dialog.set_filters(filters)

        def on_open_finish(d, result):
            try:
                gfile = d.open_finish(result)
                if gfile:
                    path = gfile.get_path()
                    mon = self._get_current_monitor()
                    if mon and path:
                        mon.icc_profile = path
                        self.icc_row.set_subtitle(path)
                        self._update_preview()
            except Exception as e:
                log.warning(f"File dialog cancelled or error: {e}")

        dialog.open(self.get_root(), None, on_open_finish)

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

        mon.disabled = not self.enable_switch.get_active()

        # Mirroring
        mirror_idx = self.mirror_combo.get_selected()
        if mirror_idx <= 0:
            mon.mirror_of = "none"
        else:
            other_mons = [m.name for m in self.monitors if m.name != mon.name]
            if mirror_idx - 1 < len(other_mons):
                mon.mirror_of = other_mons[mirror_idx - 1]

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

        bd_idx = self.bitdepth_combo.get_selected()
        if 0 <= bd_idx < len(BITDEPTH_OPTIONS):
            mon.bitdepth = BITDEPTH_OPTIONS[bd_idx][1]

        vrr_idx = self.vrr_combo.get_selected()
        if 0 <= vrr_idx < len(VRR_OPTIONS):
            mon.vrr = VRR_OPTIONS[vrr_idx][1]

        cm_idx = self.cm_combo.get_selected()
        if cm_idx == len(CM_PRESETS) - 1: # Custom ICC
            pass
        elif 0 <= cm_idx < len(CM_PRESETS) - 1:
            mon.cm = CM_PRESETS[cm_idx][1]
            mon.icc_profile = ""

        mon.sdr_brightness = float(self.sdr_bright_spin.get_value())
        mon.sdr_saturation = float(self.sdr_sat_spin.get_value())

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

        success = self.display_mgr.apply_all(self.monitors)
        if not success:
            if self.toast_callback:
                self.toast_callback("Failed to apply monitor settings via Hyprland IPC")
            return

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
                    self.toast_callback("Display settings saved and applied successfully!")
                self._load_monitor_to_ui(self.monitors[self.current_monitor_idx])
                self._update_preview()
            else:
                log.info("Display settings reverted by user or timeout.")
                self._revert_settings()

        root = self.get_root()
        self._revert_dialog.choose(root, None, on_dialog_response)

        self._revert_timer_id = GLib.timeout_add_seconds(1, self._countdown_tick)

    def _countdown_tick(self) -> bool:
        self._revert_seconds_left -= 1
        if self._revert_seconds_left <= 0:
            self._stop_revert_timer()
            if self._revert_dialog:
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
