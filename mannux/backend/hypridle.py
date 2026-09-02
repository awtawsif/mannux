import os
import shutil
import subprocess
from typing import List, Tuple
from .config import AppConfig, ConfigManager
from .power import PowerManager

HYPRIDLE_CONF_DIR = os.path.expanduser("~/.config/hypr")
HYPRIDLE_CONF_PATH = os.path.join(HYPRIDLE_CONF_DIR, "hypridle.conf")
HYPRIDLE_BACKUP_PATH = os.path.join(HYPRIDLE_CONF_DIR, "hypridle.conf.mannux.bak")

class HypridleSync:
    def __init__(self, power_mgr: PowerManager):
        self.power_mgr = power_mgr

    def backup_if_needed(self):
        if os.path.exists(HYPRIDLE_CONF_PATH) and not os.path.exists(HYPRIDLE_BACKUP_PATH):
            try:
                shutil.copy2(HYPRIDLE_CONF_PATH, HYPRIDLE_BACKUP_PATH)
                print(f"[HypridleSync] Backed up original config to {HYPRIDLE_BACKUP_PATH}")
            except OSError as e:
                print(f"[HypridleSync] Failed to backup hypridle.conf: {e}")

    def generate_config(self, config: AppConfig) -> str:
        power_status = self.power_mgr.get_status()
        ac_name = power_status.ac_name or "ADP1"
        has_battery = power_status.has_battery

        lines = [
            "# Generated automatically by Mannux Settings",
            "# https://github.com/awtawsif/mannux",
            "",
            "general {",
            f"    lock_cmd = {config.general.lock_cmd}",
            f"    before_sleep_cmd = {config.general.before_sleep_cmd}",
            f"    after_sleep_cmd = {config.general.after_sleep_cmd}",
            "    ignore_dbus_inhibit = false",
            "    ignore_systemd_inhibit = false",
            "}",
            ""
        ]

        if config.general.inhibit_idle:
            lines.append("# IDLE INHIBITION IS ACTIVE (Presentation Mode)")
            lines.append("# No timeout listeners configured.")
            return "\n".join(lines) + "\n"

        # List of (timeout, listener_type, on_timeout_cmd, on_resume_cmd)
        listeners: List[Tuple[int, str, str, str]] = []

        if has_battery:
            ac_cond = f'[ "$(cat /sys/class/power_supply/{ac_name}/online 2>/dev/null)" = 1 ]'
            bat_cond = f'[ "$(cat /sys/class/power_supply/{ac_name}/online 2>/dev/null)" = 0 ]'

            # Battery profile
            bat = config.battery
            if bat.dim_enabled and bat.dim_timeout > 0:
                listeners.append((
                    bat.dim_timeout,
                    "Battery Dim",
                    f"{bat_cond} && brightnessctl -s set {bat.dim_brightness}",
                    "brightnessctl -r"
                ))
            if bat.lock_enabled and bat.lock_timeout > 0:
                listeners.append((
                    bat.lock_timeout,
                    "Battery Lock",
                    f"{bat_cond} && loginctl lock-session",
                    ""
                ))
            if bat.dpms_enabled and bat.dpms_timeout > 0:
                listeners.append((
                    bat.dpms_timeout,
                    "Battery DPMS",
                    f"{bat_cond} && hyprctl dispatch dpms off",
                    "hyprctl dispatch dpms on"
                ))
            if bat.suspend_enabled and bat.suspend_timeout > 0:
                listeners.append((
                    bat.suspend_timeout,
                    "Battery Suspend",
                    f"{bat_cond} && systemctl suspend",
                    ""
                ))

            # AC profile
            ac = config.ac
            if ac.dim_enabled and ac.dim_timeout > 0:
                listeners.append((
                    ac.dim_timeout,
                    "AC Dim",
                    f"{ac_cond} && brightnessctl -s set {ac.dim_brightness}",
                    "brightnessctl -r"
                ))
            if ac.lock_enabled and ac.lock_timeout > 0:
                listeners.append((
                    ac.lock_timeout,
                    "AC Lock",
                    f"{ac_cond} && loginctl lock-session",
                    ""
                ))
            if ac.dpms_enabled and ac.dpms_timeout > 0:
                listeners.append((
                    ac.dpms_timeout,
                    "AC DPMS",
                    f"{ac_cond} && hyprctl dispatch dpms off",
                    "hyprctl dispatch dpms on"
                ))
            if ac.suspend_enabled and ac.suspend_timeout > 0:
                listeners.append((
                    ac.suspend_timeout,
                    "AC Suspend",
                    f"{ac_cond} && systemctl suspend",
                    ""
                ))
        else:
            # Desktop mode (no battery)
            ac = config.ac
            if ac.dim_enabled and ac.dim_timeout > 0:
                listeners.append((
                    ac.dim_timeout,
                    "Dim",
                    f"brightnessctl -s set {ac.dim_brightness}",
                    "brightnessctl -r"
                ))
            if ac.lock_enabled and ac.lock_timeout > 0:
                listeners.append((
                    ac.lock_timeout,
                    "Lock",
                    "loginctl lock-session",
                    ""
                ))
            if ac.dpms_enabled and ac.dpms_timeout > 0:
                listeners.append((
                    ac.dpms_timeout,
                    "DPMS Off",
                    "hyprctl dispatch dpms off",
                    "hyprctl dispatch dpms on"
                ))
            if ac.suspend_enabled and ac.suspend_timeout > 0:
                listeners.append((
                    ac.suspend_timeout,
                    "Suspend",
                    "systemctl suspend",
                    ""
                ))

        # Sort listeners by timeout ascending
        listeners.sort(key=lambda x: x[0])

        for timeout, desc, on_timeout, on_resume in listeners:
            lines.append(f"# {desc} ({timeout}s)")
            lines.append("listener {")
            lines.append(f"    timeout = {timeout}")
            lines.append(f"    on-timeout = {on_timeout}")
            if on_resume:
                lines.append(f"    on-resume = {on_resume}")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)

    def write_config(self, config: AppConfig) -> bool:
        try:
            os.makedirs(HYPRIDLE_CONF_DIR, exist_ok=True)
            self.backup_if_needed()
            content = self.generate_config(config)
            with open(HYPRIDLE_CONF_PATH, "w") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"[HypridleSync] Failed to write hypridle.conf: {e}")
            return False

    def reload_daemon(self) -> bool:
        # Check systemd user service first
        res = subprocess.run(["systemctl", "--user", "is-active", "hypridle"], capture_output=True, text=True)
        if res.returncode == 0 and "active" in res.stdout:
            subprocess.run(["systemctl", "--user", "restart", "hypridle"], capture_output=True)
            return True

        # Check if process is running
        pid_res = subprocess.run(["pidof", "hypridle"], capture_output=True, text=True)
        if pid_res.returncode == 0 and pid_res.stdout.strip():
            # Restart hypridle
            subprocess.run(["killall", "hypridle"], capture_output=True)
            subprocess.Popen(["hypridle"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True

        return False

    def sync_and_reload(self, config: AppConfig) -> bool:
        if self.write_config(config):
            self.reload_daemon()
            return True
        return False
