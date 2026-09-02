import os
import glob
from dataclasses import dataclass
from typing import Optional, List, Callable
from .logger import log

try:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
    HAS_GIO = True
except Exception:
    HAS_GIO = False

@dataclass
class PowerStatus:
    has_battery: bool
    on_ac: bool
    ac_name: Optional[str]
    battery_name: Optional[str]
    battery_percentage: Optional[int]
    battery_state: Optional[str]

class PowerManager:
    _instance = None

    def __init__(self):
        self._ac_name = self._find_ac_supply()
        self._battery_name = self._find_battery()
        self._listeners: List[Callable[[PowerStatus], None]] = []
        self._upower_proxy = None

        if HAS_GIO:
            self._init_upower()

    @classmethod
    def get_instance(cls) -> 'PowerManager':
        if cls._instance is None:
            cls._instance = PowerManager()
        return cls._instance

    def _init_upower(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self._upower_proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.freedesktop.UPower",
                "/org/freedesktop/UPower",
                "org.freedesktop.UPower",
                None
            )
            if self._upower_proxy:
                self._upower_proxy.connect("g-properties-changed", self._on_upower_properties_changed)
                log.debug("UPower D-Bus listener initialized successfully")
        except Exception as e:
            log.debug(f"Could not connect to UPower D-Bus: {e}")
            self._upower_proxy = None

    def _on_upower_properties_changed(self, proxy, changed_properties, invalidated_properties):
        log.debug("UPower power state changed via D-Bus signal")
        status = self.get_status()
        self._notify(status)

    def add_listener(self, callback: Callable[[PowerStatus], None]):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[PowerStatus], None]):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, status: PowerStatus):
        for cb in self._listeners:
            try:
                cb(status)
            except Exception as e:
                log.error(f"Error in power status listener callback: {e}")

    def _find_ac_supply(self) -> Optional[str]:
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
        if not self._ac_name:
            self._ac_name = self._find_ac_supply()
        if not self._battery_name:
            self._battery_name = self._find_battery()

        on_ac = True

        # Check UPower first if available
        if self._upower_proxy:
            try:
                on_battery_prop = self._upower_proxy.get_cached_property("OnBattery")
                if on_battery_prop is not None:
                    on_ac = not on_battery_prop.get_boolean()
            except Exception as e:
                log.debug(f"UPower query failed: {e}, falling back to sysfs")
                on_ac = self._check_sysfs_ac()
        else:
            on_ac = self._check_sysfs_ac()

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

    def _check_sysfs_ac(self) -> bool:
        if self._ac_name:
            online_path = f"/sys/class/power_supply/{self._ac_name}/online"
            if os.path.exists(online_path):
                try:
                    with open(online_path, "r") as f:
                        return f.read().strip() == "1"
                except OSError:
                    pass
        return True
