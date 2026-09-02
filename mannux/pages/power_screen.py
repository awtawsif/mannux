import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
from .base import BasePage
from mannux.backend.config import ConfigManager, PowerProfileConfig
from mannux.backend.power import PowerManager
from mannux.backend.hypridle import HypridleSync

# Helper for timeouts (label, seconds)
DIM_TIMEOUT_CHOICES = [
    ("30 seconds", 30),
    ("1 minute", 60),
    ("2 minutes", 120),
    ("2.5 minutes (150s)", 150),
    ("3 minutes", 180),
    ("5 minutes", 300),
    ("10 minutes", 600),
    ("15 minutes", 900),
]

DPMS_TIMEOUT_CHOICES = [
    ("1 minute", 60),
    ("2 minutes", 120),
    ("3 minutes", 180),
    ("5.5 minutes (330s)", 330),
    ("10 minutes", 600),
    ("15 minutes", 900),
    ("30 minutes", 1800),
    ("1 hour", 3600),
]

LOCK_TIMEOUT_CHOICES = [
    ("1 minute", 60),
    ("2 minutes", 120),
    ("3 minutes", 180),
    ("5 minutes", 300),
    ("10 minutes", 600),
    ("15 minutes", 900),
    ("30 minutes", 1800),
]

SUSPEND_TIMEOUT_CHOICES = [
    ("10 minutes", 600),
    ("15 minutes", 900),
    ("30 minutes", 1800),
    ("45 minutes", 2700),
    ("1 hour", 3600),
    ("2 hours", 7200),
    ("3 hours", 10800),
]

def find_closest_index(choices, val):
    for i, (_, s) in enumerate(choices):
        if s == val:
            return i
    # Find closest
    diffs = [abs(s - val) for _, s in choices]
    return diffs.index(min(diffs))

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

        # Timer to refresh power status periodically
        GLib.timeout_add_seconds(5, self._refresh_power_status)

    def _build_ui(self):
        # 1. Power Status & Inhibit Banner
        self.status_group = Adw.PreferencesGroup()
        self.status_group.set_title("System Power Status")
        self.add(self.status_group)

        self.status_row = Adw.ActionRow()
        self.status_row.set_title("Detecting power source...")
        self.status_row.set_subtitle("Checking sysfs power supply...")
        self.status_row.set_icon_name("battery-charging-symbolic")
        self.status_group.add(self.status_row)

        # Inhibit switch (Presentation Mode)
        self.inhibit_row = Adw.SwitchRow()
        self.inhibit_row.set_title("Keep Screen Awake (Inhibit Idle)")
        self.inhibit_row.set_subtitle("Temporarily disable screen dimming, lock, and suspend")
        self.inhibit_row.set_icon_name("media-playback-start-symbolic")
        self.inhibit_row.connect("notify::active", self._on_inhibit_toggled)
        self.status_group.add(self.inhibit_row)

        # 2. Battery Power Profile Group
        self.bat_group = Adw.PreferencesGroup()
        self.bat_group.set_title("On Battery Power")
        self.bat_group.set_description("Settings applied when your laptop is running on battery")
        self.add(self.bat_group)

        self.bat_widgets = self._create_profile_widgets("battery", self.bat_group)

        # 3. AC Power Profile Group
        self.ac_group = Adw.PreferencesGroup()
        self.ac_group.set_title("Plugged In (AC Power)")
        self.ac_group.set_description("Settings applied when connected to wall power or desktop")
        self.add(self.ac_group)

        self.ac_widgets = self._create_profile_widgets("ac", self.ac_group)

        # 4. General & Screen Locker Group
        self.gen_group = Adw.PreferencesGroup()
        self.gen_group.set_title("Screen Lock & Daemon Integration")
        self.gen_group.set_description("Hypridle and Hyprlock integration commands")
        self.add(self.gen_group)

        self.lock_cmd_row = Adw.EntryRow()
        self.lock_cmd_row.set_title("Lock Command")
        self.lock_cmd_row.connect("changed", self._on_lock_cmd_changed)
        self.gen_group.add(self.lock_cmd_row)

        self.auto_sync_row = Adw.SwitchRow()
        self.auto_sync_row.set_title("Automatic Sync to Hypridle")
        self.auto_sync_row.set_subtitle("Instantly write ~/.config/hypr/hypridle.conf and reload daemon on change")
        self.auto_sync_row.connect("notify::active", self._on_auto_sync_toggled)
        self.gen_group.add(self.auto_sync_row)

        # Apply button row
        apply_row = Adw.ActionRow()
        apply_row.set_title("Apply & Restart Hypridle")
        apply_row.set_subtitle("Manually generate hypridle.conf and restart the background daemon")
        apply_btn = Gtk.Button(label="Apply Now")
        apply_btn.set_valign(Gtk.Align.CENTER)
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_clicked)
        apply_row.add_suffix(apply_btn)
        self.gen_group.add(apply_row)

        self._refresh_power_status()

    def _create_profile_widgets(self, profile_name: str, group: Adw.PreferencesGroup) -> dict:
        w = {}

        # Dim Row
        w["dim_switch"] = Adw.SwitchRow()
        w["dim_switch"].set_title("Dim Screen")
        w["dim_switch"].set_subtitle("Reduce backlight brightness before locking")
        w["dim_switch"].set_icon_name("display-brightness-symbolic")
        w["dim_switch"].connect("notify::active", lambda s, p: self._on_setting_changed())
        group.add(w["dim_switch"])

        # Dim timeout combo
        dim_model = Gtk.StringList.new([c[0] for c in DIM_TIMEOUT_CHOICES])
        w["dim_combo"] = Adw.ComboRow()
        w["dim_combo"].set_title("Dim Delay")
        w["dim_combo"].set_model(dim_model)
        w["dim_combo"].connect("notify::selected", lambda s, p: self._on_setting_changed())
        group.add(w["dim_combo"])

        # Turn Off Screen (DPMS)
        w["dpms_switch"] = Adw.SwitchRow()
        w["dpms_switch"].set_title("Turn Off Screen (DPMS)")
        w["dpms_switch"].set_subtitle("Power down displays when inactive")
        w["dpms_switch"].set_icon_name("video-display-symbolic")
        w["dpms_switch"].connect("notify::active", lambda s, p: self._on_setting_changed())
        group.add(w["dpms_switch"])

        dpms_model = Gtk.StringList.new([c[0] for c in DPMS_TIMEOUT_CHOICES])
        w["dpms_combo"] = Adw.ComboRow()
        w["dpms_combo"].set_title("Turn Off Screen Delay")
        w["dpms_combo"].set_model(dpms_model)
        w["dpms_combo"].connect("notify::selected", lambda s, p: self._on_setting_changed())
        group.add(w["dpms_combo"])

        # Lock Screen
        w["lock_switch"] = Adw.SwitchRow()
        w["lock_switch"].set_title("Lock Screen")
        w["lock_switch"].set_subtitle("Lock the session with hyprlock")
        w["lock_switch"].set_icon_name("system-lock-screen-symbolic")
        w["lock_switch"].connect("notify::active", lambda s, p: self._on_setting_changed())
        group.add(w["lock_switch"])

        lock_model = Gtk.StringList.new([c[0] for c in LOCK_TIMEOUT_CHOICES])
        w["lock_combo"] = Adw.ComboRow()
        w["lock_combo"].set_title("Lock Screen Delay")
        w["lock_combo"].set_model(lock_model)
        w["lock_combo"].connect("notify::selected", lambda s, p: self._on_setting_changed())
        group.add(w["lock_combo"])

        # Suspend PC
        w["suspend_switch"] = Adw.SwitchRow()
        w["suspend_switch"].set_title("Automatic Suspend")
        w["suspend_switch"].set_subtitle("Put the system into low power sleep")
        w["suspend_switch"].set_icon_name("system-shutdown-symbolic")
        w["suspend_switch"].connect("notify::active", lambda s, p: self._on_setting_changed())
        group.add(w["suspend_switch"])

        suspend_model = Gtk.StringList.new([c[0] for c in SUSPEND_TIMEOUT_CHOICES])
        w["suspend_combo"] = Adw.ComboRow()
        w["suspend_combo"].set_title("Suspend Delay")
        w["suspend_combo"].set_model(suspend_model)
        w["suspend_combo"].connect("notify::selected", lambda s, p: self._on_setting_changed())
        group.add(w["suspend_combo"])

        return w

    def _refresh_power_status(self) -> bool:
        status = self.power_mgr.get_status()
        if not status.has_battery:
            self.status_row.set_title("Desktop Power (No Battery Detected)")
            self.status_row.set_subtitle("Using Plugged In (AC) configuration profile")
            self.status_row.set_icon_name("computer-symbolic")
            self.bat_group.set_visible(False)
        else:
            self.bat_group.set_visible(True)
            if status.on_ac:
                bat_str = f" ({status.battery_percentage}%)" if status.battery_percentage is not None else ""
                state_str = f" - {status.battery_state}" if status.battery_state else ""
                self.status_row.set_title(f"Plugged In (AC Power){bat_str}")
                self.status_row.set_subtitle(f"Currently active: AC profile{state_str}")
                self.status_row.set_icon_name("battery-charging-symbolic" if status.battery_state == "Charging" else "ac-adapter-symbolic")
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
        return True

    def _load_from_config(self):
        self._updating_ui = True
        cfg = self.config_mgr.config

        self.inhibit_row.set_active(cfg.general.inhibit_idle)
        self.lock_cmd_row.set_text(cfg.general.lock_cmd)
        self.auto_sync_row.set_active(cfg.general.auto_sync_hypridle)

        # Battery
        self.bat_widgets["dim_switch"].set_active(cfg.battery.dim_enabled)
        self.bat_widgets["dim_combo"].set_selected(find_closest_index(DIM_TIMEOUT_CHOICES, cfg.battery.dim_timeout))
        self.bat_widgets["dpms_switch"].set_active(cfg.battery.dpms_enabled)
        self.bat_widgets["dpms_combo"].set_selected(find_closest_index(DPMS_TIMEOUT_CHOICES, cfg.battery.dpms_timeout))
        self.bat_widgets["lock_switch"].set_active(cfg.battery.lock_enabled)
        self.bat_widgets["lock_combo"].set_selected(find_closest_index(LOCK_TIMEOUT_CHOICES, cfg.battery.lock_timeout))
        self.bat_widgets["suspend_switch"].set_active(cfg.battery.suspend_enabled)
        self.bat_widgets["suspend_combo"].set_selected(find_closest_index(SUSPEND_TIMEOUT_CHOICES, cfg.battery.suspend_timeout))

        # AC
        self.ac_widgets["dim_switch"].set_active(cfg.ac.dim_enabled)
        self.ac_widgets["dim_combo"].set_selected(find_closest_index(DIM_TIMEOUT_CHOICES, cfg.ac.dim_timeout))
        self.ac_widgets["dpms_switch"].set_active(cfg.ac.dpms_enabled)
        self.ac_widgets["dpms_combo"].set_selected(find_closest_index(DPMS_TIMEOUT_CHOICES, cfg.ac.dpms_timeout))
        self.ac_widgets["lock_switch"].set_active(cfg.ac.lock_enabled)
        self.ac_widgets["lock_combo"].set_selected(find_closest_index(LOCK_TIMEOUT_CHOICES, cfg.ac.lock_timeout))
        self.ac_widgets["suspend_switch"].set_active(cfg.ac.suspend_enabled)
        self.ac_widgets["suspend_combo"].set_selected(find_closest_index(SUSPEND_TIMEOUT_CHOICES, cfg.ac.suspend_timeout))

        self._updating_ui = False

    def _save_to_config(self):
        if self._updating_ui:
            return

        cfg = self.config_mgr.config
        cfg.general.inhibit_idle = self.inhibit_row.get_active()
        cfg.general.lock_cmd = self.lock_cmd_row.get_text() or "pidof hyprlock || hyprlock"
        cfg.general.auto_sync_hypridle = self.auto_sync_row.get_active()

        # Battery
        cfg.battery.dim_enabled = self.bat_widgets["dim_switch"].get_active()
        cfg.battery.dim_timeout = DIM_TIMEOUT_CHOICES[self.bat_widgets["dim_combo"].get_selected()][1]
        cfg.battery.dpms_enabled = self.bat_widgets["dpms_switch"].get_active()
        cfg.battery.dpms_timeout = DPMS_TIMEOUT_CHOICES[self.bat_widgets["dpms_combo"].get_selected()][1]
        cfg.battery.lock_enabled = self.bat_widgets["lock_switch"].get_active()
        cfg.battery.lock_timeout = LOCK_TIMEOUT_CHOICES[self.bat_widgets["lock_combo"].get_selected()][1]
        cfg.battery.suspend_enabled = self.bat_widgets["suspend_switch"].get_active()
        cfg.battery.suspend_timeout = SUSPEND_TIMEOUT_CHOICES[self.bat_widgets["suspend_combo"].get_selected()][1]

        # AC
        cfg.ac.dim_enabled = self.ac_widgets["dim_switch"].get_active()
        cfg.ac.dim_timeout = DIM_TIMEOUT_CHOICES[self.ac_widgets["dim_combo"].get_selected()][1]
        cfg.ac.dpms_enabled = self.ac_widgets["dpms_switch"].get_active()
        cfg.ac.dpms_timeout = DPMS_TIMEOUT_CHOICES[self.ac_widgets["dpms_combo"].get_selected()][1]
        cfg.ac.lock_enabled = self.ac_widgets["lock_switch"].get_active()
        cfg.ac.lock_timeout = LOCK_TIMEOUT_CHOICES[self.ac_widgets["lock_combo"].get_selected()][1]
        cfg.ac.suspend_enabled = self.ac_widgets["suspend_switch"].get_active()
        cfg.ac.suspend_timeout = SUSPEND_TIMEOUT_CHOICES[self.ac_widgets["suspend_combo"].get_selected()][1]

        self.config_mgr.save()

        if cfg.general.auto_sync_hypridle:
            self.hypridle_sync.sync_and_reload(cfg)

    def _on_setting_changed(self):
        self._save_to_config()

    def _on_inhibit_toggled(self, widget, param):
        self._save_to_config()
        if self.toast_callback:
            msg = "Keep Awake Enabled (Idle Inhibited)" if self.inhibit_row.get_active() else "Idle Timeouts Restored"
            self.toast_callback(msg)

    def _on_lock_cmd_changed(self, widget):
        self._save_to_config()

    def _on_auto_sync_toggled(self, widget, param):
        self._save_to_config()

    def _on_apply_clicked(self, widget):
        self._save_to_config()
        success = self.hypridle_sync.sync_and_reload(self.config_mgr.config)
        if self.toast_callback:
            if success:
                self.toast_callback("Hypridle configuration updated and reloaded!")
            else:
                self.toast_callback("Failed to reload hypridle daemon")
