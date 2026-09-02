import os
import glob
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class PowerStatus:
    has_battery: bool
    on_ac: bool
    ac_name: Optional[str]
    battery_name: Optional[str]
    battery_percentage: Optional[int]
    battery_state: Optional[str]

class PowerManager:
    def __init__(self):
        self._ac_name = self._find_ac_supply()
        self._battery_name = self._find_battery()

    def _find_ac_supply(self) -> Optional[str]:
        # Look for AC, ADP, ADP1, ACAD, etc.
        for path in glob.glob("/sys/class/power_supply/*"):
            name = os.path.basename(path)
            type_file = os.path.join(path, "type")
            if os.path.exists(type_file):
                try:
                    with open(type_file, "r") as f:
                        if f.read().strip().lower() == "mains":
                            return name
                except OSError:
                    pass
            # Fallback by name pattern
            if name.startswith(("ADP", "AC", "ACAD")):
                return name
        return None

    def _find_battery(self) -> Optional[str]:
        for path in glob.glob("/sys/class/power_supply/*"):
            name = os.path.basename(path)
            type_file = os.path.join(path, "type")
            if os.path.exists(type_file):
                try:
                    with open(type_file, "r") as f:
                        if f.read().strip().lower() == "battery":
                            return name
                except OSError:
                    pass
            if name.startswith(("BAT", "battery")):
                return name
        return None

    def get_status(self) -> PowerStatus:
        # Refresh device names if not found earlier
        if not self._ac_name:
            self._ac_name = self._find_ac_supply()
        if not self._battery_name:
            self._battery_name = self._find_battery()

        on_ac = True
        if self._ac_name:
            online_path = f"/sys/class/power_supply/{self._ac_name}/online"
            if os.path.exists(online_path):
                try:
                    with open(online_path, "r") as f:
                        on_ac = (f.read().strip() == "1")
                except OSError:
                    on_ac = True

        has_battery = bool(self._battery_name)
        bat_pct = None
        bat_state = None

        if has_battery:
            cap_path = f"/sys/class/power_supply/{self._battery_name}/capacity"
            status_path = f"/sys/class/power_supply/{self._battery_name}/status"
            if os.path.exists(cap_path):
                try:
                    with open(cap_path, "r") as f:
                        bat_pct = int(f.read().strip())
                except (OSError, ValueError):
                    pass
            if os.path.exists(status_path):
                try:
                    with open(status_path, "r") as f:
                        bat_state = f.read().strip()
                except OSError:
                    pass

        return PowerStatus(
            has_battery=has_battery,
            on_ac=on_ac,
            ac_name=self._ac_name,
            battery_name=self._battery_name,
            battery_percentage=bat_pct,
            battery_state=bat_state,
        )
