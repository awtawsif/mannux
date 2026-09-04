import os
import json
import glob
import shutil
import subprocess
from typing import Optional, List, Tuple
from .config import HyprlandPowerConfig
from .logger import log

HYPR_DIR = os.path.expanduser("~/.config/hypr")
LUA_MODULES_DIR = os.path.join(HYPR_DIR, "modules")
LUA_POWER_PATH = os.path.join(LUA_MODULES_DIR, "power.lua")
LUA_POWER_BAK = os.path.join(LUA_MODULES_DIR, "power.lua.mannux.bak")
LEGACY_POWER_PATH = os.path.join(HYPR_DIR, "power.conf")
LEGACY_POWER_BAK = os.path.join(HYPR_DIR, "power.conf.mannux.bak")
HYPRLAND_LUA_PATH = os.path.join(HYPR_DIR, "hyprland.lua")
HYPRLAND_CONF_PATH = os.path.join(HYPR_DIR, "hyprland.conf")

LID_ACTIONS: List[Tuple[str, str]] = [
    ("Ignore / System Default", "ignore"),
    ("Suspend System", "suspend"),
    ("Lock Screen", "lock"),
    ("Turn Off Screen (DPMS)", "dpms_off"),
]

def get_lid_command(action: str) -> Optional[str]:
    if action == "suspend":
        return "systemctl suspend"
    elif action == "lock":
        return "loginctl lock-session"
    elif action == "dpms_off":
        return "hyprctl dispatch dpms off"
    return None

class HyprlandPowerSync:
    _instance = None

    def __init__(self):
        self._is_lua: Optional[bool] = None

    @classmethod
    def get_instance(cls) -> 'HyprlandPowerSync':
        if cls._instance is None:
            cls._instance = HyprlandPowerSync()
        return cls._instance

    def is_hyprland_active(self) -> bool:
        return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))

    def is_lua_mode(self) -> bool:
        if self._is_lua is not None:
            return self._is_lua
        try:
            res = subprocess.run(["hyprctl", "eval", "return 1"], capture_output=True, text=True)
            self._is_lua = (res.returncode == 0 and "ok" in res.stdout.lower())
        except Exception:
            self._is_lua = False
        return self._is_lua

    def has_lid_switch(self) -> bool:
        if os.path.exists("/proc/acpi/button/lid"):
            try:
                entries = os.listdir("/proc/acpi/button/lid")
                if entries:
                    return True
            except OSError:
                pass
        try:
            res = subprocess.run(["hyprctl", "devices", "-j"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                for sw in data.get("switches", []):
                    if "lid" in sw.get("name", "").lower():
                        return True
        except Exception:
            pass
        return False

    def generate_lua_config(self, cfg: HyprlandPowerConfig) -> str:
        mouse = "true" if cfg.mouse_move_enables_dpms else "false"
        key = "true" if cfg.key_press_enables_dpms else "false"
        lines = [
            "-- ====================================================================",
            "-- Generated automatically by Mannux Settings",
            "-- https://github.com/awtawsif/mannux",
            "-- ====================================================================",
            "",
            "hl.config({",
            "    misc = {",
            f"        mouse_move_enables_dpms = {mouse},",
            f"        key_press_enables_dpms = {key},",
            "    },",
            "})",
            ""
        ]

        lid_cmd = get_lid_command(cfg.lid_switch_action)
        if lid_cmd:
            lines.append("-- Laptop Lid Switch Bindings")
            lines.append(f'hl.bind("switch:on:Lid Switch", hl.dsp.exec_cmd([[{lid_cmd}]]), {{ locked = true }})')
            if cfg.lid_switch_action == "dpms_off":
                lines.append('hl.bind("switch:off:Lid Switch", hl.dsp.exec_cmd([[hyprctl dispatch dpms on]]), { locked = true })')
            lines.append("")

        return "\n".join(lines)

    def generate_legacy_config(self, cfg: HyprlandPowerConfig) -> str:
        mouse = "true" if cfg.mouse_move_enables_dpms else "false"
        key = "true" if cfg.key_press_enables_dpms else "false"
        lines = [
            "# ====================================================================",
            "# Generated automatically by Mannux Settings",
            "# https://github.com/awtawsif/mannux",
            "# ====================================================================",
            "",
            "misc {",
            f"    mouse_move_enables_dpms = {mouse}",
            f"    key_press_enables_dpms = {key}",
            "}",
            ""
        ]

        lid_cmd = get_lid_command(cfg.lid_switch_action)
        if lid_cmd:
            lines.append("# Laptop Lid Switch Bindings")
            lines.append(f"bindl = , switch:on:Lid Switch, exec, {lid_cmd}")
            if cfg.lid_switch_action == "dpms_off":
                lines.append("bindl = , switch:off:Lid Switch, exec, hyprctl dispatch dpms on")
            lines.append("")

        return "\n".join(lines)

    def apply_live(self, cfg: HyprlandPowerConfig) -> bool:
        if not self.is_hyprland_active():
            log.debug("Hyprland is not active; skipping live application.")
            return False

        mouse = "true" if cfg.mouse_move_enables_dpms else "false"
        key = "true" if cfg.key_press_enables_dpms else "false"
        lid_cmd = get_lid_command(cfg.lid_switch_action)

        if self.is_lua_mode():
            # Apply misc settings
            lua_code = f"hl.config({{ misc = {{ mouse_move_enables_dpms = {mouse}, key_press_enables_dpms = {key} }} }})"
            subprocess.run(["hyprctl", "eval", lua_code], capture_output=True)

            # Unbind previous lid switch binding
            subprocess.run(["hyprctl", "eval", 'pcall(hl.unbind, "switch:on:Lid Switch")'], capture_output=True)
            subprocess.run(["hyprctl", "eval", 'pcall(hl.unbind, "switch:off:Lid Switch")'], capture_output=True)

            # Bind if configured
            if lid_cmd:
                bind_on = f'hl.bind("switch:on:Lid Switch", hl.dsp.exec_cmd([[{lid_cmd}]]), {{ locked = true }})'
                subprocess.run(["hyprctl", "eval", bind_on], capture_output=True)
                if cfg.lid_switch_action == "dpms_off":
                    bind_off = 'hl.bind("switch:off:Lid Switch", hl.dsp.exec_cmd([[hyprctl dispatch dpms on]]), {{ locked = true }})'
                    subprocess.run(["hyprctl", "eval", bind_off], capture_output=True)
            return True
        else:
            # Legacy parser
            subprocess.run(["hyprctl", "keyword", "misc:mouse_move_enables_dpms", mouse], capture_output=True)
            subprocess.run(["hyprctl", "keyword", "misc:key_press_enables_dpms", key], capture_output=True)
            if lid_cmd:
                subprocess.run(["hyprctl", "keyword", "bindl", f", switch:on:Lid Switch, exec, {lid_cmd}"], capture_output=True)
                if cfg.lid_switch_action == "dpms_off":
                    subprocess.run(["hyprctl", "keyword", "bindl", ", switch:off:Lid Switch, exec, hyprctl dispatch dpms on"], capture_output=True)
            return True

    def save_config(self, cfg: HyprlandPowerConfig) -> bool:
        saved_any = False
        try:
            # 1. Lua configuration
            if self.is_lua_mode() or os.path.exists(HYPRLAND_LUA_PATH) or os.path.exists(LUA_MODULES_DIR):
                os.makedirs(LUA_MODULES_DIR, exist_ok=True)
                if os.path.exists(LUA_POWER_PATH) and not os.path.exists(LUA_POWER_BAK):
                    shutil.copy2(LUA_POWER_PATH, LUA_POWER_BAK)
                content = self.generate_lua_config(cfg)
                with open(LUA_POWER_PATH, "w") as f:
                    f.write(content)
                log.info(f"Saved Lua power configuration to {LUA_POWER_PATH}")
                self._ensure_lua_included()
                saved_any = True

            # 2. Legacy configuration
            if not self.is_lua_mode() or os.path.exists(HYPRLAND_CONF_PATH) or os.path.exists(LEGACY_POWER_PATH):
                os.makedirs(HYPR_DIR, exist_ok=True)
                if os.path.exists(LEGACY_POWER_PATH) and not os.path.exists(LEGACY_POWER_BAK):
                    shutil.copy2(LEGACY_POWER_PATH, LEGACY_POWER_BAK)
                content = self.generate_legacy_config(cfg)
                with open(LEGACY_POWER_PATH, "w") as f:
                    f.write(content)
                log.info(f"Saved legacy power configuration to {LEGACY_POWER_PATH}")
                self._ensure_legacy_included()
                saved_any = True

            return saved_any
        except Exception as e:
            log.error(f"Failed to save hyprland power configuration: {e}")
            return False

    def _ensure_lua_included(self):
        if not os.path.exists(HYPRLAND_LUA_PATH):
            return
        try:
            with open(HYPRLAND_LUA_PATH, "r") as f:
                content = f.read()
            if "modules/power" not in content:
                with open(HYPRLAND_LUA_PATH, "a") as f:
                    f.write('\npcall(require, "modules/power")\n')
                log.info(f"Appended pcall(require, 'modules/power') to {HYPRLAND_LUA_PATH}")
        except Exception as e:
            log.warning(f"Could not update {HYPRLAND_LUA_PATH}: {e}")

    def _ensure_legacy_included(self):
        if not os.path.exists(HYPRLAND_CONF_PATH):
            return
        try:
            with open(HYPRLAND_CONF_PATH, "r") as f:
                content = f.read()
            if "power.conf" not in content:
                with open(HYPRLAND_CONF_PATH, "a") as f:
                    f.write("\nsource = ~/.config/hypr/power.conf\n")
                log.info(f"Appended source power.conf to {HYPRLAND_CONF_PATH}")
        except Exception as e:
            log.warning(f"Could not update {HYPRLAND_CONF_PATH}: {e}")

    def sync_and_apply(self, cfg: HyprlandPowerConfig) -> bool:
        saved = self.save_config(cfg)
        applied = self.apply_live(cfg)
        return saved or applied
