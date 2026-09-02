import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Tuple, Optional
from .config import AppConfig
from .power import PowerManager
from .logger import log

HYPRIDLE_CONF_DIR = os.path.expanduser("~/.config/hypr")
HYPRIDLE_CONF_PATH = os.path.join(HYPRIDLE_CONF_DIR, "hypridle.conf")
HYPRIDLE_BACKUP_PATH = os.path.join(HYPRIDLE_CONF_DIR, "hypridle.conf.mannux.bak")

@dataclass
class DaemonStatus:
    is_installed: bool
    is_running: bool
    is_systemd: bool
    pid: Optional[int]
    description: str

class HypridleSync:
    def __init__(self, power_mgr: Optional[PowerManager] = None):
        self.power_mgr = power_mgr or PowerManager.get_instance()

    def get_daemon_status(self) -> DaemonStatus:
        # 1. Check if binary is installed
        res = subprocess.run(["which", "hypridle"], capture_output=True, text=True)
        if res.returncode != 0 or not res.stdout.strip():
            return DaemonStatus(
                is_installed=False,
                is_running=False,
                is_systemd=False,
                pid=None,
                description="hypridle is not installed on system"
            )

        # 2. Check systemd user service
        res = subprocess.run(["systemctl", "--user", "is-active", "hypridle"], capture_output=True, text=True)
        if res.returncode == 0 and "active" in res.stdout:
            # Get PID if possible
            pid_res = subprocess.run(["systemctl", "--user", "show", "--property=MainPID", "--value", "hypridle"], capture_output=True, text=True)
            pid = int(pid_res.stdout.strip()) if pid_res.stdout.strip().isdigit() else None
            return DaemonStatus(
                is_installed=True,
                is_running=True,
                is_systemd=True,
                pid=pid,
                description=f"Running via systemd service (PID {pid or 'active'})"
            )

        # 3. Check standalone process
        pid_res = subprocess.run(["pidof", "hypridle"], capture_output=True, text=True)
        if pid_res.returncode == 0 and pid_res.stdout.strip():
            pids = pid_res.stdout.strip().split()
            main_pid = int(pids[0]) if pids else None
            return DaemonStatus(
                is_installed=True,
                is_running=True,
                is_systemd=False,
                pid=main_pid,
                description=f"Running as standalone process (PID {main_pid})"
            )

        return DaemonStatus(
            is_installed=True,
            is_running=False,
            is_systemd=False,
            pid=None,
            description="hypridle is installed but currently stopped"
        )

    def backup_if_needed(self):
        if os.path.exists(HYPRIDLE_CONF_PATH) and not os.path.exists(HYPRIDLE_BACKUP_PATH):
            try:
                shutil.copy2(HYPRIDLE_CONF_PATH, HYPRIDLE_BACKUP_PATH)
                log.info(f"Backed up existing hypridle.conf to {HYPRIDLE_BACKUP_PATH}")
            except OSError as e:
                log.error(f"Failed to backup hypridle.conf: {e}")

    def generate_config(self, config: AppConfig) -> str:
        power_status = self.power_mgr.get_status()
        ac_name = power_status.ac_name or "ADP1"
        has_battery = power_status.has_battery

        lines = [
            "# ====================================================================",
            "# Generated automatically by Mannux Settings",
            "# https://github.com/awtawsif/mannux",
            "# ====================================================================",
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
            lines.append("# ====================================================================")
            lines.append("# IDLE INHIBITION ACTIVE (Presentation / Awake Mode)")
            lines.append("# All timeout listeners are bypassed.")
            lines.append("# ====================================================================")
            return "\n".join(lines) + "\n"

        # List of (timeout, listener_type, on_timeout_cmd, on_resume_cmd)
        listeners: List[Tuple[int, str, str, str]] = []

        if has_battery:
            ac_cond = f'[ "$(cat /sys/class/power_supply/{ac_name}/online 2>/dev/null)" = 1 ]'
            bat_cond = f'[ "$(cat /sys/class/power_supply/{ac_name}/online 2>/dev/null)" = 0 ]'

            # Battery profile
            bat = config.battery
            if bat.dim_enabled and bat.dim_timeout > 0:
                dim_val = f"{bat.dim_brightness}%" if bat.dim_brightness > 0 else "1"
                listeners.append((
                    bat.dim_timeout,
                    f"Battery: Dim Screen to {dim_val}",
                    f"{bat_cond} && brightnessctl -s set {dim_val}",
                    f"{bat_cond} && brightnessctl -r"
                ))
            if bat.lock_enabled and bat.lock_timeout > 0:
                listeners.append((
                    bat.lock_timeout,
                    "Battery: Lock Session",
                    f"{bat_cond} && loginctl lock-session",
                    ""
                ))
            if bat.dpms_enabled and bat.dpms_timeout > 0:
                listeners.append((
                    bat.dpms_timeout,
                    "Battery: Turn Off Displays (DPMS)",
                    f"{bat_cond} && hyprctl dispatch dpms off",
                    f"{bat_cond} && hyprctl dispatch dpms on"
                ))
            if bat.suspend_enabled and bat.suspend_timeout > 0:
                listeners.append((
                    bat.suspend_timeout,
                    "Battery: System Suspend",
                    f"{bat_cond} && systemctl suspend",
                    ""
                ))

            # AC profile
            ac = config.ac
            if ac.dim_enabled and ac.dim_timeout > 0:
                dim_val = f"{ac.dim_brightness}%" if ac.dim_brightness > 0 else "1"
                listeners.append((
                    ac.dim_timeout,
                    f"AC: Dim Screen to {dim_val}",
                    f"{ac_cond} && brightnessctl -s set {dim_val}",
                    f"{ac_cond} && brightnessctl -r"
                ))
            if ac.lock_enabled and ac.lock_timeout > 0:
                listeners.append((
                    ac.lock_timeout,
                    "AC: Lock Session",
                    f"{ac_cond} && loginctl lock-session",
                    ""
                ))
            if ac.dpms_enabled and ac.dpms_timeout > 0:
                listeners.append((
                    ac.dpms_timeout,
                    "AC: Turn Off Displays (DPMS)",
                    f"{ac_cond} && hyprctl dispatch dpms off",
                    f"{ac_cond} && hyprctl dispatch dpms on"
                ))
            if ac.suspend_enabled and ac.suspend_timeout > 0:
                listeners.append((
                    ac.suspend_timeout,
                    "AC: System Suspend",
                    f"{ac_cond} && systemctl suspend",
                    ""
                ))
        else:
            # Desktop mode (no battery detected)
            ac = config.ac
            if ac.dim_enabled and ac.dim_timeout > 0:
                dim_val = f"{ac.dim_brightness}%" if ac.dim_brightness > 0 else "1"
                listeners.append((
                    ac.dim_timeout,
                    f"Dim Screen to {dim_val}",
                    f"brightnessctl -s set {dim_val}",
                    "brightnessctl -r"
                ))
            if ac.lock_enabled and ac.lock_timeout > 0:
                listeners.append((
                    ac.lock_timeout,
                    "Lock Session",
                    "loginctl lock-session",
                    ""
                ))
            if ac.dpms_enabled and ac.dpms_timeout > 0:
                listeners.append((
                    ac.dpms_timeout,
                    "Turn Off Displays (DPMS)",
                    "hyprctl dispatch dpms off",
                    "hyprctl dispatch dpms on"
                ))
            if ac.suspend_enabled and ac.suspend_timeout > 0:
                listeners.append((
                    ac.suspend_timeout,
                    "System Suspend",
                    "systemctl suspend",
                    ""
                ))

        # Sort listeners by timeout ascending
        listeners.sort(key=lambda x: x[0])

        for timeout, desc, on_timeout, on_resume in listeners:
            lines.append(f"# {desc} (after {timeout}s)")
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
            log.info(f"Successfully generated and wrote {HYPRIDLE_CONF_PATH}")
            return True
        except Exception as e:
            log.error(f"Failed to write hypridle.conf: {e}")
            return False

    def restart_daemon(self) -> bool:
        status = self.get_daemon_status()
        if not status.is_installed:
            log.warning("Cannot restart hypridle: binary not installed")
            return False

        if status.is_systemd:
            log.info("Restarting hypridle via systemd user service...")
            res = subprocess.run(["systemctl", "--user", "restart", "hypridle"], capture_output=True)
            return res.returncode == 0
        else:
            log.info("Restarting standalone hypridle process...")
            subprocess.run(["killall", "hypridle"], capture_output=True)
            try:
                subprocess.Popen(
                    ["hypridle"],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception as e:
                log.error(f"Failed to spawn hypridle process: {e}")
                return False

    def start_daemon(self) -> bool:
        return self.restart_daemon()

    def stop_daemon(self) -> bool:
        status = self.get_daemon_status()
        if status.is_systemd:
            res = subprocess.run(["systemctl", "--user", "stop", "hypridle"], capture_output=True)
            return res.returncode == 0
        else:
            res = subprocess.run(["killall", "hypridle"], capture_output=True)
            return res.returncode == 0

    def sync_and_reload(self, config: AppConfig) -> bool:
        if self.write_config(config):
            self.restart_daemon()
            return True
        return False
