import os
import json
from dataclasses import dataclass, asdict, field
from typing import Callable, List, Optional
from .logger import log

CONFIG_DIR = os.path.expanduser("~/.config/mannux")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

@dataclass
class PowerProfileConfig:
    dim_enabled: bool = True
    dim_timeout: int = 150         # seconds
    dim_brightness: int = 10       # percentage (1-100)
    dpms_enabled: bool = True
    dpms_timeout: int = 330        # seconds
    lock_enabled: bool = True
    lock_timeout: int = 300        # seconds
    suspend_enabled: bool = True
    suspend_timeout: int = 1800    # seconds

@dataclass
class GeneralConfig:
    lock_cmd: str = "pidof hyprlock || hyprlock"
    before_sleep_cmd: str = "loginctl lock-session"
    after_sleep_cmd: str = "hyprctl dispatch dpms on"
    inhibit_idle: bool = False
    auto_sync_hypridle: bool = True

@dataclass
class AppConfig:
    version: int = 1
    general: GeneralConfig = field(default_factory=GeneralConfig)
    battery: PowerProfileConfig = field(default_factory=lambda: PowerProfileConfig(
        dim_enabled=True,
        dim_timeout=150,
        dim_brightness=10,
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
        dim_brightness=20,
        dpms_enabled=True,
        dpms_timeout=900,
        lock_enabled=False,
        lock_timeout=600,
        suspend_enabled=False,
        suspend_timeout=3600
    ))

class ConfigManager:
    _instance = None

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
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
                log.error(f"Error in config listener callback: {e}")

    def reset_to_defaults(self):
        log.info("Resetting configuration to factory defaults")
        self._config = AppConfig()
        self.save()

    def load(self):
        if not os.path.exists(self.config_path):
            log.info(f"No existing config found at {self.config_path}, creating default")
            self.save()
            return

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)

            gen_data = data.get("general", {})
            bat_data = data.get("battery", {})
            ac_data = data.get("ac", {})

            self._config = AppConfig(
                version=data.get("version", 1),
                general=GeneralConfig(**{k: v for k, v in gen_data.items() if k in GeneralConfig.__annotations__}),
                battery=PowerProfileConfig(**{k: v for k, v in bat_data.items() if k in PowerProfileConfig.__annotations__}),
                ac=PowerProfileConfig(**{k: v for k, v in ac_data.items() if k in PowerProfileConfig.__annotations__}),
            )
            log.debug(f"Configuration loaded from {self.config_path}")
        except Exception as e:
            log.warning(f"Failed to parse config at {self.config_path}: {e}. Falling back to defaults.")
            self._config = AppConfig()

    def save(self):
        config_dir = os.path.dirname(self.config_path)
        os.makedirs(config_dir, exist_ok=True)
        try:
            with open(self.config_path, "w") as f:
                json.dump(asdict(self._config), f, indent=2)
            log.debug(f"Configuration saved to {self.config_path}")
            self._notify()
        except Exception as e:
            log.error(f"Failed to save config to {self.config_path}: {e}")
