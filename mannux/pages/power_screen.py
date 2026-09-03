import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango
from .base import BasePage
from mannux.backend.config import ConfigManager, PowerProfileConfig
from mannux.backend.power import PowerManager, PowerStatus
from mannux.backend.hypridle import HypridleSync, DaemonStatus
from mannux.backend.logger import log

TIMEOUT_PRESETS = [
    ("30 seconds", 30),
    ("1 minute", 60),
    ("2 minutes", 120),
    ("2.5 minutes (150s)", 150),
    ("3 minutes", 180),
    ("5 minutes", 300),
    ("5.5 minutes (330s)", 330),
    ("10 minutes", 600),
    ("15 minutes", 900),
    ("30 minutes", 1800),
    ("45 minutes", 2700),
    ("1 hour", 3600),
    ("2 hours", 7200),
    ("3 hours", 10800),
    ("Custom...", -1),
]

def find_timeout_index(seconds: int) -> int:
    for i, (_, s) in enumerate(TIMEOUT_PRESETS[:-1]):
        if s == seconds:
            return i
    return len(TIMEOUT_PRESETS) - 1 # Custom

class PowerScreenPage(BasePage):
    tag = "power"
    title = "Power & Screen"
    icon_name = "battery-symbolic"

    def __init__(self, config_mgr: ConfigManager, power_mgr: PowerManager, hypridle_sync: HypridleSync, toast_callback=None, **kwargs):
        super().__init__(config_mgr, power_mgr, **kwargs)
        self.hypridle_sync = hypridle_sync
        self.toast_callback = toast_callback
        self._updating_ui = False

        self._build_ui()
        self._load_from_config()

        # Listen to power status changes via PowerManager
        self.power_mgr.add_listener(self._on_power_status_changed)

        # Periodic refresh for daemon status & battery fallback
        GLib.timeout_add_seconds(3, self._periodic_refresh)

    def _build_ui(self):
        # -------------------------------------------------------------
        # 1. System Status & Quick Controls
        # -------------------------------------------------------------
        self.status_group = Adw.PreferencesGroup()
        self.status_group.set_title("System Status & Controls")
        self.add(self.status_group)

        # Power Source Row
        self.status_row = Adw.ActionRow()
        self.status_row.set_title("Detecting power source...")
        self.status_row.set_subtitle("Connecting to UPower...")
        self.status_row.set_icon_name("battery-charging-symbolic")
        self.status_group.add(self.status_row)

        # Hypridle Daemon Row
        self.daemon_row = Adw.ActionRow()
        self.daemon_row.set_title("Idle Daemon (hypridle)")
        self.daemon_row.set_subtitle("Checking status...")
        self.daemon_row.set_icon_name("system-run-symbolic")

        self.restart_daemon_btn = Gtk.Button(label="Restart")
        self.restart_daemon_btn.set_icon_name("view-refresh-symbolic")
        self.restart_daemon_btn.set_valign(Gtk.Align.CENTER)
        self.restart_daemon_btn.add_css_class("flat")
        self.restart_daemon_btn.connect("clicked", self._on_restart_daemon_clicked)
        self.daemon_row.add_suffix(self.restart_daemon_btn)
        self.status_group.add(self.daemon_row)

        # Keep Screen Awake / Inhibit Switch
        self.inhibit_row = Adw.SwitchRow()
        self.inhibit_row.set_title("Keep Screen Awake (Inhibit Idle)")
        self.inhibit_row.set_subtitle("Bypass timeouts for presentation or media viewing")
        self.inhibit_row.set_icon_name("media-playback-start-symbolic")
        self.inhibit_row.connect("notify::active", self._on_inhibit_toggled)
        self.status_group.add(self.inhibit_row)

        # -------------------------------------------------------------
        # 2. Segmented Profile Switcher (Battery vs AC)
        # -------------------------------------------------------------
        self.profiles_group = Adw.PreferencesGroup()
        self.profiles_group.set_title("Power Profiles")
        self.profiles_group.set_description("Configure independent idle behaviors based on power source")
        self.add(self.profiles_group)

        # Switcher & Stack
        self.profile_stack = Adw.ViewStack()

        self.bat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.bat_widgets = self._create_profile_controls("battery", self.bat_box)
        self.profile_stack.add_titled_with_icon(self.bat_box, "battery", "On Battery", "battery-symbolic")

        self.ac_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.ac_widgets = self._create_profile_controls("ac", self.ac_box)
        self.profile_stack.add_titled_with_icon(self.ac_box, "ac", "Plugged In (AC)", "ac-adapter-symbolic")

        self.profile_switcher = Adw.ViewSwitcher()
        self.profile_switcher.set_stack(self.profile_stack)
        self.profile_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        self.profile_switcher.set_halign(Gtk.Align.CENTER)
        self.profile_switcher.set_margin_bottom(12)

        self.profiles_group.add(self.profile_switcher)
        self.profiles_group.add(self.profile_stack)

        # -------------------------------------------------------------
        # 3. Advanced Settings (Expandable at Bottom)
        # -------------------------------------------------------------
        self.advanced_group = Adw.PreferencesGroup()
        self.advanced_group.set_title("Advanced")
        self.advanced_group.set_description("Expert settings, session commands, daemon flags, and maintenance")
        self.add(self.advanced_group)

        self.advanced_expander = Adw.ExpanderRow()
        self.advanced_expander.set_title("Advanced Settings")
        self.advanced_expander.set_subtitle("Session commands, daemon options, backup restore, and config preview")
        self.advanced_expander.set_icon_name("preferences-other-symbolic")
        self.advanced_expander.set_expanded(False)
        self.advanced_group.add(self.advanced_expander)

        # --- A. Custom Session Commands ---
        self.lock_cmd_row = Adw.EntryRow()
        self.lock_cmd_row.set_title("Lock Command")
        self.lock_cmd_row.connect("changed", lambda w: self._save_to_config())
        self.advanced_expander.add_row(self.lock_cmd_row)

        self.before_sleep_cmd_row = Adw.EntryRow()
        self.before_sleep_cmd_row.set_title("Before Sleep Command")
        self.before_sleep_cmd_row.connect("changed", lambda w: self._save_to_config())
        self.advanced_expander.add_row(self.before_sleep_cmd_row)

        self.after_sleep_cmd_row = Adw.EntryRow()
        self.after_sleep_cmd_row.set_title("After Sleep Command")
        self.after_sleep_cmd_row.connect("changed", lambda w: self._save_to_config())
        self.advanced_expander.add_row(self.after_sleep_cmd_row)

        # --- B. Hypridle Daemon Options ---
        self.auto_sync_row = Adw.SwitchRow()
        self.auto_sync_row.set_title("Automatic Sync & Reload")
        self.auto_sync_row.set_subtitle("Instantly write ~/.config/hypr/hypridle.conf on change")
        self.auto_sync_row.connect("notify::active", lambda w, p: self._save_to_config())
        self.advanced_expander.add_row(self.auto_sync_row)

        self.ignore_dbus_row = Adw.SwitchRow()
        self.ignore_dbus_row.set_title("Ignore D-Bus Inhibitors")
        self.ignore_dbus_row.set_subtitle("Ignore applications requesting idle inhibition via D-Bus")
        self.ignore_dbus_row.connect("notify::active", lambda w, p: self._save_to_config())
        self.advanced_expander.add_row(self.ignore_dbus_row)

        self.ignore_systemd_row = Adw.SwitchRow()
        self.ignore_systemd_row.set_title("Ignore Systemd Inhibitors")
        self.ignore_systemd_row.set_subtitle("Ignore system-level systemd-inhibit requests")
        self.ignore_systemd_row.connect("notify::active", lambda w, p: self._save_to_config())
        self.advanced_expander.add_row(self.ignore_systemd_row)

        # Force sync action row
        apply_row = Adw.ActionRow()
        apply_row.set_title("Force Apply & Restart Daemon")
        apply_row.set_subtitle("Manually regenerate hypridle.conf and restart background process")
        apply_btn = Gtk.Button(label="Apply Now")
        apply_btn.set_valign(Gtk.Align.CENTER)
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_clicked)
        apply_row.add_suffix(apply_btn)
        self.advanced_expander.add_row(apply_row)

        # --- C. Maintenance Tools ---
        self.restore_row = Adw.ActionRow()
        self.restore_row.set_title("Restore Original Config")
        self.restore_row.set_subtitle("Restore ~/.config/hypr/hypridle.conf.mannux.bak")
        self.restore_btn = Gtk.Button(label="Restore Backup")
        self.restore_btn.set_valign(Gtk.Align.CENTER)
        self.restore_btn.connect("clicked", self._on_restore_clicked)
        self.restore_row.add_suffix(self.restore_btn)
        self.advanced_expander.add_row(self.restore_row)

        # --- D. Live Config Preview ---
        self.preview_expander = Adw.ExpanderRow()
        self.preview_expander.set_title("Preview Generated hypridle.conf")
        self.preview_expander.set_subtitle("View live hypridle configuration syntax")
        self.preview_expander.set_icon_name("text-x-generic-symbolic")

        preview_scroller = Gtk.ScrolledWindow()
        preview_scroller.set_min_content_height(180)
        preview_scroller.set_max_content_height(320)
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
        self.advanced_expander.add_row(self.preview_expander)

        # --- E. Reset to Defaults ---
        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset Settings to Defaults")
        reset_row.set_subtitle("Restore all factory recommended configurations")
        reset_btn = Gtk.Button(label="Reset Defaults")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.add_css_class("destructive-action")
        reset_btn.connect("clicked", self._on_reset_clicked)
        reset_row.add_suffix(reset_btn)
        self.advanced_expander.add_row(reset_row)

        # Initial updates
        self._update_power_ui(self.power_mgr.get_status())
        self._update_daemon_status()
        self._update_backup_status()
        self._update_preview()

    def _create_profile_controls(self, name: str, container: Gtk.Box) -> dict:
        w = {}
        group = Adw.PreferencesGroup()
        container.append(group)

        # 1. Dim Screen
        w["dim_switch"] = Adw.SwitchRow()
        w["dim_switch"].set_title("Dim Screen")
        w["dim_switch"].set_subtitle("Reduce display backlight when idle")
        w["dim_switch"].set_icon_name("display-brightness-symbolic")
        w["dim_switch"].connect("notify::active", lambda s, p: self._on_control_changed())
        group.add(w["dim_switch"])

        # Preset combo
        dim_model = Gtk.StringList.new([c[0] for c in TIMEOUT_PRESETS])
        w["dim_combo"] = Adw.ComboRow()
        w["dim_combo"].set_title("Dim Delay")
        w["dim_combo"].set_model(dim_model)
        w["dim_combo"].connect("notify::selected", lambda s, p: self._on_combo_changed(w["dim_combo"], w["dim_spin"]))
        group.add(w["dim_combo"])

        # Custom Spin
        w["dim_spin"] = Adw.SpinRow.new_with_range(10, 86400, 10)
        w["dim_spin"].set_title("Custom Dim Delay (seconds)")
        w["dim_spin"].set_visible(False)
        w["dim_spin"].connect("notify::value", lambda s, p: self._on_control_changed())
        group.add(w["dim_spin"])

        # Dim Brightness Spin / Level
        w["dim_brightness"] = Adw.SpinRow.new_with_range(1, 100, 5)
        w["dim_brightness"].set_title("Dimmed Brightness Level (%)")
        w["dim_brightness"].set_subtitle("Target screen brightness percentage when dimmed")
        w["dim_brightness"].connect("notify::value", lambda s, p: self._on_control_changed())
        group.add(w["dim_brightness"])

        # 2. Turn Off Screen (DPMS)
        w["dpms_switch"] = Adw.SwitchRow()
        w["dpms_switch"].set_title("Turn Off Screen (DPMS)")
        w["dpms_switch"].set_subtitle("Put monitors into standby mode")
        w["dpms_switch"].set_icon_name("video-display-symbolic")
        w["dpms_switch"].connect("notify::active", lambda s, p: self._on_control_changed())
        group.add(w["dpms_switch"])

        dpms_model = Gtk.StringList.new([c[0] for c in TIMEOUT_PRESETS])
        w["dpms_combo"] = Adw.ComboRow()
        w["dpms_combo"].set_title("Turn Off Screen Delay")
        w["dpms_combo"].set_model(dpms_model)
        w["dpms_combo"].connect("notify::selected", lambda s, p: self._on_combo_changed(w["dpms_combo"], w["dpms_spin"]))
        group.add(w["dpms_combo"])

        w["dpms_spin"] = Adw.SpinRow.new_with_range(10, 86400, 10)
        w["dpms_spin"].set_title("Custom Screen Off Delay (seconds)")
        w["dpms_spin"].set_visible(False)
        w["dpms_spin"].connect("notify::value", lambda s, p: self._on_control_changed())
        group.add(w["dpms_spin"])

        # 3. Lock Session
        w["lock_switch"] = Adw.SwitchRow()
        w["lock_switch"].set_title("Lock Session")
        w["lock_switch"].set_subtitle("Secure screen with hyprlock")
        w["lock_switch"].set_icon_name("system-lock-screen-symbolic")
        w["lock_switch"].connect("notify::active", lambda s, p: self._on_control_changed())
        group.add(w["lock_switch"])

        lock_model = Gtk.StringList.new([c[0] for c in TIMEOUT_PRESETS])
        w["lock_combo"] = Adw.ComboRow()
        w["lock_combo"].set_title("Lock Session Delay")
        w["lock_combo"].set_model(lock_model)
        w["lock_combo"].connect("notify::selected", lambda s, p: self._on_combo_changed(w["lock_combo"], w["lock_spin"]))
        group.add(w["lock_combo"])

        w["lock_spin"] = Adw.SpinRow.new_with_range(10, 86400, 10)
        w["lock_spin"].set_title("Custom Lock Delay (seconds)")
        w["lock_spin"].set_visible(False)
        w["lock_spin"].connect("notify::value", lambda s, p: self._on_control_changed())
        group.add(w["lock_spin"])

        # 4. Suspend System
        w["suspend_switch"] = Adw.SwitchRow()
        w["suspend_switch"].set_title("Suspend System")
        w["suspend_switch"].set_subtitle("Enter low-power sleep mode")
        w["suspend_switch"].set_icon_name("system-shutdown-symbolic")
        w["suspend_switch"].connect("notify::active", lambda s, p: self._on_control_changed())
        group.add(w["suspend_switch"])

        suspend_model = Gtk.StringList.new([c[0] for c in TIMEOUT_PRESETS])
        w["suspend_combo"] = Adw.ComboRow()
        w["suspend_combo"].set_title("Suspend Delay")
        w["suspend_combo"].set_model(suspend_model)
        w["suspend_combo"].connect("notify::selected", lambda s, p: self._on_combo_changed(w["suspend_combo"], w["suspend_spin"]))
        group.add(w["suspend_combo"])

        w["suspend_spin"] = Adw.SpinRow.new_with_range(10, 86400, 10)
        w["suspend_spin"].set_title("Custom Suspend Delay (seconds)")
        w["suspend_spin"].set_visible(False)
        w["suspend_spin"].connect("notify::value", lambda s, p: self._on_control_changed())
        group.add(w["suspend_spin"])

        return w

    def _on_combo_changed(self, combo: Adw.ComboRow, spin: Adw.SpinRow):
        idx = combo.get_selected()
        is_custom = (idx == len(TIMEOUT_PRESETS) - 1)
        spin.set_visible(is_custom)
        if not is_custom:
            spin.set_value(TIMEOUT_PRESETS[idx][1])
        self._on_control_changed()

    def _on_power_status_changed(self, status: PowerStatus):
        GLib.idle_add(self._update_power_ui, status)

    def _periodic_refresh(self) -> bool:
        self._update_power_ui(self.power_mgr.get_status())
        self._update_daemon_status()
        self._update_backup_status()
        return True

    def _update_backup_status(self):
        has_bak = self.hypridle_sync.has_backup()
        self.restore_btn.set_sensitive(has_bak)
        if has_bak:
            self.restore_row.set_subtitle("Backup found at ~/.config/hypr/hypridle.conf.mannux.bak")
        else:
            self.restore_row.set_subtitle("No backup found")

    def _update_power_ui(self, status: PowerStatus):
        if not status.has_battery:
            self.status_row.set_title("Desktop System (AC Power)")
            self.status_row.set_subtitle("No battery detected — using Plugged In profile")
            self.status_row.set_icon_name("computer-symbolic")
            self.profile_stack.set_visible_child_name("ac")
            self.profile_switcher.set_visible(False)
        else:
            self.profile_switcher.set_visible(True)
            if status.on_ac:
                bat_str = f" ({status.battery_percentage}%)" if status.battery_percentage is not None else ""
                state_str = f" - {status.battery_state}" if status.battery_state else ""
                self.status_row.set_title(f"Plugged In (AC Power){bat_str}")
                self.status_row.set_subtitle(f"Currently active: Plugged In profile{state_str}")
                icon = "battery-charging-symbolic" if status.battery_state == "Charging" else "ac-adapter-symbolic"
                self.status_row.set_icon_name(icon)
            else:
                pct = status.battery_percentage if status.battery_percentage is not None else 0
                self.status_row.set_title(f"On Battery ({pct}%)")
                self.status_row.set_subtitle(f"Currently active: Battery profile ({status.battery_state or 'Discharging'})")
                if pct > 70:
                    icon = "battery-good-symbolic"
                elif pct > 30:
                    icon = "battery-medium-symbolic"
                else:
                    icon = "battery-caution-symbolic"
                self.status_row.set_icon_name(icon)

    def _update_daemon_status(self):
        st: DaemonStatus = self.hypridle_sync.get_daemon_status()
        if not st.is_installed:
            self.daemon_row.set_title("Idle Daemon: Missing")
            self.daemon_row.set_subtitle("hypridle is not installed (pacman -S hypridle)")
            self.daemon_row.set_icon_name("dialog-warning-symbolic")
            self.restart_daemon_btn.set_sensitive(False)
        elif st.is_running:
            self.daemon_row.set_title("Idle Daemon: Running 🟢")
            self.daemon_row.set_subtitle(st.description)
            self.daemon_row.set_icon_name("emblem-ok-symbolic")
            self.restart_daemon_btn.set_sensitive(True)
            self.restart_daemon_btn.set_label("Restart")
        else:
            self.daemon_row.set_title("Idle Daemon: Stopped 🔴")
            self.daemon_row.set_subtitle("Daemon is inactive — click Start to activate")
            self.daemon_row.set_icon_name("process-stop-symbolic")
            self.restart_daemon_btn.set_sensitive(True)
            self.restart_daemon_btn.set_label("Start")

    def _update_preview(self):
        content = self.hypridle_sync.generate_config(self.config_mgr.config)
        self.preview_buffer.set_text(content)

    def _load_from_config(self):
        self._updating_ui = True
        cfg = self.config_mgr.config

        self.inhibit_row.set_active(cfg.general.inhibit_idle)
        self.lock_cmd_row.set_text(cfg.general.lock_cmd)
        self.before_sleep_cmd_row.set_text(cfg.general.before_sleep_cmd)
        self.after_sleep_cmd_row.set_text(cfg.general.after_sleep_cmd)
        self.auto_sync_row.set_active(cfg.general.auto_sync_hypridle)
        self.ignore_dbus_row.set_active(cfg.general.ignore_dbus_inhibit)
        self.ignore_systemd_row.set_active(cfg.general.ignore_systemd_inhibit)

        self._load_profile_widgets(cfg.battery, self.bat_widgets)
        self._load_profile_widgets(cfg.ac, self.ac_widgets)

        self._updating_ui = False
        self._update_preview()

    def _load_profile_widgets(self, prof: PowerProfileConfig, w: dict):
        w["dim_switch"].set_active(prof.dim_enabled)
        dim_idx = find_timeout_index(prof.dim_timeout)
        w["dim_combo"].set_selected(dim_idx)
        w["dim_spin"].set_value(prof.dim_timeout)
        w["dim_spin"].set_visible(dim_idx == len(TIMEOUT_PRESETS) - 1)
        w["dim_brightness"].set_value(prof.dim_brightness)

        w["dpms_switch"].set_active(prof.dpms_enabled)
        dpms_idx = find_timeout_index(prof.dpms_timeout)
        w["dpms_combo"].set_selected(dpms_idx)
        w["dpms_spin"].set_value(prof.dpms_timeout)
        w["dpms_spin"].set_visible(dpms_idx == len(TIMEOUT_PRESETS) - 1)

        w["lock_switch"].set_active(prof.lock_enabled)
        lock_idx = find_timeout_index(prof.lock_timeout)
        w["lock_combo"].set_selected(lock_idx)
        w["lock_spin"].set_value(prof.lock_timeout)
        w["lock_spin"].set_visible(lock_idx == len(TIMEOUT_PRESETS) - 1)

        w["suspend_switch"].set_active(prof.suspend_enabled)
        susp_idx = find_timeout_index(prof.suspend_timeout)
        w["suspend_combo"].set_selected(susp_idx)
        w["suspend_spin"].set_value(prof.suspend_timeout)
        w["suspend_spin"].set_visible(susp_idx == len(TIMEOUT_PRESETS) - 1)

    def _save_to_config(self):
        if self._updating_ui:
            return

        cfg = self.config_mgr.config
        cfg.general.inhibit_idle = self.inhibit_row.get_active()
        cfg.general.lock_cmd = self.lock_cmd_row.get_text() or "pidof hyprlock || hyprlock"
        cfg.general.before_sleep_cmd = self.before_sleep_cmd_row.get_text() or "loginctl lock-session"
        cfg.general.after_sleep_cmd = self.after_sleep_cmd_row.get_text() or "hyprctl dispatch dpms on"
        cfg.general.auto_sync_hypridle = self.auto_sync_row.get_active()
        cfg.general.ignore_dbus_inhibit = self.ignore_dbus_row.get_active()
        cfg.general.ignore_systemd_inhibit = self.ignore_systemd_row.get_active()

        self._save_profile_widgets(cfg.battery, self.bat_widgets)
        self._save_profile_widgets(cfg.ac, self.ac_widgets)

        self.config_mgr.save()
        self._update_preview()

        if cfg.general.auto_sync_hypridle:
            self.hypridle_sync.sync_and_reload(cfg)

    def _save_profile_widgets(self, prof: PowerProfileConfig, w: dict):
        prof.dim_enabled = w["dim_switch"].get_active()
        prof.dim_brightness = int(w["dim_brightness"].get_value())
        dim_idx = w["dim_combo"].get_selected()
        prof.dim_timeout = int(w["dim_spin"].get_value()) if dim_idx == len(TIMEOUT_PRESETS) - 1 else TIMEOUT_PRESETS[dim_idx][1]

        prof.dpms_enabled = w["dpms_switch"].get_active()
        dpms_idx = w["dpms_combo"].get_selected()
        prof.dpms_timeout = int(w["dpms_spin"].get_value()) if dpms_idx == len(TIMEOUT_PRESETS) - 1 else TIMEOUT_PRESETS[dpms_idx][1]

        prof.lock_enabled = w["lock_switch"].get_active()
        lock_idx = w["lock_combo"].get_selected()
        prof.lock_timeout = int(w["lock_spin"].get_value()) if lock_idx == len(TIMEOUT_PRESETS) - 1 else TIMEOUT_PRESETS[lock_idx][1]

        prof.suspend_enabled = w["suspend_switch"].get_active()
        susp_idx = w["suspend_combo"].get_selected()
        prof.suspend_timeout = int(w["suspend_spin"].get_value()) if susp_idx == len(TIMEOUT_PRESETS) - 1 else TIMEOUT_PRESETS[susp_idx][1]

    def _on_control_changed(self):
        self._save_to_config()

    def _on_inhibit_toggled(self, widget, param):
        self._save_to_config()
        if self.toast_callback:
            msg = "Keep Awake Active (Idle Inhibited)" if self.inhibit_row.get_active() else "Idle Timeouts Restored"
            self.toast_callback(msg)

    def _on_restart_daemon_clicked(self, widget):
        success = self.hypridle_sync.restart_daemon()
        self._update_daemon_status()
        if self.toast_callback:
            self.toast_callback("Hypridle daemon restarted!" if success else "Failed to restart hypridle")

    def _on_apply_clicked(self, widget):
        self._save_to_config()
        success = self.hypridle_sync.sync_and_reload(self.config_mgr.config)
        self._update_daemon_status()
        if self.toast_callback:
            self.toast_callback("Configuration synchronized & daemon reloaded!" if success else "Failed to reload hypridle")

    def _on_restore_clicked(self, widget):
        dialog = Adw.AlertDialog.new(
            "Restore Original Backup Config?",
            "This will replace your current ~/.config/hypr/hypridle.conf with the original backup created on first run and restart hypridle."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("restore", "Restore Backup")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(d, resp):
            if resp == "restore":
                success = self.hypridle_sync.restore_backup()
                self._update_daemon_status()
                if self.toast_callback:
                    self.toast_callback("Original backup restored and daemon restarted!" if success else "Failed to restore backup")

        root = self.get_root()
        dialog.choose(root, None, on_response)

    def _on_reset_clicked(self, widget):
        dialog = Adw.AlertDialog.new(
            "Reset Settings to Defaults?",
            "This will restore all power timeouts, dimming preferences, screen lock settings, and advanced options to factory defaults."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset Settings")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(d, resp):
            if resp == "reset":
                self.config_mgr.reset_to_defaults()
                self._load_from_config()
                self.hypridle_sync.sync_and_reload(self.config_mgr.config)
                if self.toast_callback:
                    self.toast_callback("Settings reset to factory defaults!")

        root = self.get_root()
        dialog.choose(root, None, on_response)
