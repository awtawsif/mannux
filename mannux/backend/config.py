import os
import json
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Callable, List

CONFIG_DIR = os.path.expanduser("~/.config/mannux")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

@dataclass
class PowerProfileConfig:
    dim_enabled: bool = True
    dim_timeout: int = 150         # 2.5 mins
    dim_brightness: int = 1        # level or percent
    dpms_enabled: bool = True
    dpms_timeout: int = 330        # 5.5 mins
    lock_enabled: bool = True
    lock_timeout: int = 300        # 5 mins
    suspend_enabled: bool = True
    suspend_timeout: int = 1800    # 30 mins

@dataclass
class GeneralConfig:
    lock_cmd: str = "pidof hyprlock || hyprlock"
    before_sleep_cmd: str = "loginctl lock-session"
    after_sleep_cmd: str = "hyprctl dispatch dpms on"
    inhibit_idle: bool = False
    auto_sync_hypridle: bool = True

@dataclass
class AppConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    battery: PowerProfileConfig = field(default_factory=lambda: PowerProfileConfig(
        dim_enabled=True,
        dim_timeout=150,
        dim_brightness=1,
        dpms_enabled=True,
        dpms_timeout=330,
        lock_enabled=True,
        lock_timeout=300,
        suspend_enabled=True,
        suspend_timeout=1800
    ))
    ac: PowerProfileConfig = field(default_factory=lambda: PowerProfileConfig(
        dim_enabled=False,
        dim_timeout=300,
        dim_brightness=10,
        dpms_enabled=True,
        dpms_timeout=900,
        lock_enabled=False,
        lock_timeout=600,
        suspend_enabled=False,
        suspend_timeout=3600
    ))

class ConfigManager:
    _instance = None

    def __init__(self):
        self._config = AppConfig()
        self._listeners: List[Callable[[AppConfig], None]] = []
        self.load()

    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = ConfigManager()
        return cls._instance

    @property
    def config(self) -> AppConfig:
        return self._config

    def add_listener(self, callback: Callable[[AppConfig], None]):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[AppConfig], None]):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self):
        for listener in self._listeners:
            try:
                listener(self._config)
            except Exception as e:
                print(f"[ConfigManager] Error in listener: {e}")

    def load(self):
        if not os.path.exists(CONFIG_PATH):
            self.save()
            return

        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)

            gen_data = data.get("general", {})
            bat_data = data.get("battery", {})
            ac_data = data.get("ac", {})

            self._config = AppConfig(
                general=GeneralConfig(**{k: v for k, v in gen_data.items() if k in GeneralConfig.__annotations__}),
                battery=PowerProfileConfig(**{k: v for k, v in bat_data.items() if k in PowerProfileConfig.__annotations__}),
                ac=PowerProfileConfig(**{k: v for k, v in ac_data.items() if k in PowerProfileConfig.__annotations__}),
            )
        except Exception as e:
            print(f"[ConfigManager] Failed to load config: {e}. Using defaults.")
            self._config = AppConfig()

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(asdict(self._config), f, indent=2)
            self._notify()
        except Exception as e:
            print(f"[ConfigManager] Failed to save config: {e}")
