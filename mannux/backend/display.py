import os
import json
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional
from .logger import log

HYPR_DIR = os.path.expanduser("~/.config/hypr")
LUA_MONITORS_PATH = os.path.join(HYPR_DIR, "modules", "monitors.lua")
LUA_MONITORS_BAK = os.path.join(HYPR_DIR, "modules", "monitors.lua.mannux.bak")
LEGACY_MONITORS_PATH = os.path.join(HYPR_DIR, "monitors.conf")
LEGACY_MONITORS_BAK = os.path.join(HYPR_DIR, "monitors.conf.mannux.bak")

TRANSFORM_OPTIONS = [
    ("Normal (0°)", 0),
    ("90° (Portrait)", 1),
    ("180° (Inverted)", 2),
    ("270° (Portrait Flipped)", 3),
    ("Flipped (0°)", 4),
    ("Flipped (90°)", 5),
    ("Flipped (180°)", 6),
    ("Flipped (270°)", 7),
]

SCALE_PRESETS = [
    ("100% (1.0x)", 1.0),
    ("125% (1.25x)", 1.25),
    ("150% (1.5x)", 1.5),
    ("175% (1.75x)", 1.75),
    ("200% (2.0x)", 2.0),
    ("Custom...", -1.0),
]

BITDEPTH_OPTIONS = [
    ("8-bit (Standard Color)", 8),
    ("10-bit (Deep Color / HDR)", 10),
]

VRR_OPTIONS = [
    ("Off (Fixed Refresh Rate)", 0),
    ("Always On (Desktop & Windows)", 1),
    ("Fullscreen Only (Games)", 2),
    ("Content-Aware / Smart VRR (Games & Video)", 3),
]

@dataclass
class MonitorInfo:
    id: int
    name: str
    description: str
    make: str
    model: str
    width: int
    height: int
    refresh_rate: float
    x: int
    y: int
    scale: float
    transform: int
    focused: bool
    dpms_status: bool
    vrr: int = 0
    bitdepth: int = 8
    disabled: bool = False
    mirror_of: str = "none"
    bound_workspaces: List[int] = field(default_factory=list)
    available_modes: List[str] = field(default_factory=list)

    @property
    def aspect_ratio(self) -> str:
        def gcd(a, b):
            while b:
                a, b = b, a % b
            return a
        if self.width <= 0 or self.height <= 0:
            return ""
        d = gcd(self.width, self.height)
        w_ratio, h_ratio = self.width // d, self.height // d
        if (w_ratio, h_ratio) in [(8, 5), (16, 10)]:
            return "16:10"
        if (w_ratio, h_ratio) in [(16, 9)]:
            return "16:9"
        if (w_ratio, h_ratio) in [(4, 3)]:
            return "4:3"
        if (w_ratio, h_ratio) in [(21, 9), (64, 27)]:
            return "21:9"
        if (w_ratio, h_ratio) in [(32, 9)]:
            return "32:9"
        return f"{w_ratio}:{h_ratio}"

    @property
    def resolution_str(self) -> str:
        ratio = f" ({self.aspect_ratio})" if self.aspect_ratio else ""
        return f"{self.width} × {self.height}{ratio}"

    @property
    def mode_str(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh_rate:.2f}Hz"

    def get_resolutions_and_rates(self) -> Dict[Tuple[int, int], List[float]]:
        res_map: Dict[Tuple[int, int], List[float]] = {}
        for mode in self.available_modes:
            try:
                parts = mode.replace("Hz", "").split("@")
                if len(parts) == 2:
                    dim = parts[0].split("x")
                    w, h = int(dim[0]), int(dim[1])
                    rate = float(parts[1])
                    if (w, h) not in res_map:
                        res_map[(w, h)] = []
                    if rate not in res_map[(w, h)]:
                        res_map[(w, h)].append(rate)
            except Exception:
                pass

        curr = (self.width, self.height)
        if curr not in res_map:
            res_map[curr] = [self.refresh_rate]
        elif self.refresh_rate not in res_map[curr]:
            res_map[curr].append(self.refresh_rate)

        for k in res_map:
            res_map[k].sort(reverse=True)
        return res_map

class DisplayManager:
    _instance = None

    def __init__(self):
        self._is_lua: Optional[bool] = None

    @classmethod
    def get_instance(cls) -> 'DisplayManager':
        if cls._instance is None:
            cls._instance = DisplayManager()
        return cls._instance

    def is_lua_mode(self) -> bool:
        if self._is_lua is not None:
            return self._is_lua
        try:
            res = subprocess.run(["hyprctl", "eval", "return 1"], capture_output=True, text=True)
            self._is_lua = (res.returncode == 0 and "ok" in res.stdout.lower())
        except Exception:
            self._is_lua = False
        return self._is_lua

    def get_monitors(self) -> List[MonitorInfo]:
        try:
            res = subprocess.run(["hyprctl", "monitors", "all", "-j"], capture_output=True, text=True)
            if res.returncode != 0 or not res.stdout.strip():
                res = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True)
            data = json.loads(res.stdout)
            monitors = []
            for item in data:
                vrr_raw = item.get("vrr", False)
                if isinstance(vrr_raw, bool):
                    vrr_val = 1 if vrr_raw else 0
                elif isinstance(vrr_raw, (int, float)):
                    vrr_val = int(vrr_raw)
                else:
                    vrr_val = 0

                mon = MonitorInfo(
                    id=item.get("id", 0),
                    name=item.get("name", "Unknown"),
                    description=item.get("description", ""),
                    make=item.get("make", ""),
                    model=item.get("model", ""),
                    width=item.get("width", 1920),
                    height=item.get("height", 1080),
                    refresh_rate=float(item.get("refreshRate", 60.0)),
                    x=item.get("x", 0),
                    y=item.get("y", 0),
                    scale=float(item.get("scale", 1.0)),
                    transform=int(item.get("transform", 0)),
                    focused=bool(item.get("focused", False)),
                    dpms_status=bool(item.get("dpmsStatus", True)),
                    vrr=vrr_val,
                    bitdepth=int(item.get("currentFormat", "8").replace("XRGB", "").replace("8888", "8") == "10" and 10 or 8),
                    disabled=bool(item.get("disabled", False)),
                    mirror_of=item.get("mirrorOf", "none") or "none",
                    available_modes=item.get("availableModes", []),
                )
                monitors.append(mon)
            return monitors
        except Exception as e:
            log.error(f"Failed to query hyprctl monitors: {e}")
            return []

    def build_lua_command(self, mon: MonitorInfo) -> str:
        if mon.disabled:
            return f"hl.monitor({{ output = '{mon.name}', mode = 'disable' }})"
        if mon.mirror_of and mon.mirror_of != "none":
            return f"hl.monitor({{ output = '{mon.name}', mode = 'preferred', position = 'auto', scale = {mon.scale}, mirror = '{mon.mirror_of}' }})"
        mode_str = f"{mon.width}x{mon.height}@{mon.refresh_rate:.2f}"
        pos_str = f"{mon.x}x{mon.y}"
        return (
            f"hl.monitor({{"
            f" output = '{mon.name}',"
            f" mode = '{mode_str}',"
            f" position = '{pos_str}',"
            f" scale = {mon.scale},"
            f" transform = {mon.transform},"
            f" bitdepth = {mon.bitdepth},"
            f" vrr = {mon.vrr}"
            f" }})"
        )

    def build_legacy_command(self, mon: MonitorInfo) -> str:
        if mon.disabled:
            return f"monitor = {mon.name}, disable"
        if mon.mirror_of and mon.mirror_of != "none":
            return f"monitor = {mon.name}, preferred, auto, {mon.scale}, mirror, {mon.mirror_of}"
        mode_str = f"{mon.width}x{mon.height}@{mon.refresh_rate:.2f}"
        pos_str = f"{mon.x}x{mon.y}"
        return f"monitor = {mon.name}, {mode_str}, {pos_str}, {mon.scale}, transform, {mon.transform}, bitdepth, {mon.bitdepth}, vrr, {mon.vrr}"

    def apply_monitor(self, mon: MonitorInfo) -> bool:
        success = True
        if self.is_lua_mode():
            cmd = self.build_lua_command(mon)
            log.info(f"Applying monitor via Lua IPC: {cmd}")
            res = subprocess.run(["hyprctl", "eval", cmd], capture_output=True, text=True)
            if res.returncode != 0:
                success = False

            # Apply workspace bindings
            for ws in mon.bound_workspaces:
                ws_cmd = f"hl.workspace_rule({{ workspace = '{ws}', monitor = '{mon.name}' }})"
                subprocess.run(["hyprctl", "eval", ws_cmd], capture_output=True)
        else:
            cmd = self.build_legacy_command(mon).replace("monitor = ", "")
            log.info(f"Applying monitor via legacy keyword IPC: {cmd}")
            res = subprocess.run(["hyprctl", "keyword", "monitor", cmd], capture_output=True, text=True)
            if res.returncode != 0:
                success = False

            for ws in mon.bound_workspaces:
                ws_cmd = f"{ws}, monitor:{mon.name}"
                subprocess.run(["hyprctl", "keyword", "workspace", ws_cmd], capture_output=True)

        return success

    def apply_all(self, monitors: List[MonitorInfo]) -> bool:
        success = True
        for mon in monitors:
            if not self.apply_monitor(mon):
                success = False
        return success

    def generate_lua_config(self, monitors: List[MonitorInfo]) -> str:
        lines = [
            "-- ====================================================================",
            "-- Generated automatically by Mannux Settings",
            "-- https://github.com/awtawsif/mannux",
            "-- ====================================================================",
            "",
        ]
        for mon in monitors:
            lines.append(f"-- Monitor: {mon.name} ({mon.description})")
            lines.append(self.build_lua_command(mon))
            if mon.bound_workspaces:
                for ws in mon.bound_workspaces:
                    lines.append(f"hl.workspace_rule({{ workspace = '{ws}', monitor = '{mon.name}' }})")
            lines.append("")
        return "\n".join(lines)

    def generate_legacy_config(self, monitors: List[MonitorInfo]) -> str:
        lines = [
            "# ====================================================================",
            "# Generated automatically by Mannux Settings",
            "# https://github.com/awtawsif/mannux",
            "# ====================================================================",
            "",
        ]
        for mon in monitors:
            lines.append(f"# Monitor: {mon.name} ({mon.description})")
            lines.append(self.build_legacy_command(mon))
            if mon.bound_workspaces:
                for ws in mon.bound_workspaces:
                    lines.append(f"workspace = {ws}, monitor:{mon.name}")
            lines.append("")
        return "\n".join(lines)

    def save_config(self, monitors: List[MonitorInfo]) -> bool:
        saved_any = False
        try:
            lua_dir = os.path.dirname(LUA_MONITORS_PATH)
            if self.is_lua_mode() or os.path.exists(LUA_MONITORS_PATH) or os.path.exists(lua_dir):
                os.makedirs(lua_dir, exist_ok=True)
                if os.path.exists(LUA_MONITORS_PATH) and not os.path.exists(LUA_MONITORS_BAK):
                    shutil.copy2(LUA_MONITORS_PATH, LUA_MONITORS_BAK)
                content = self.generate_lua_config(monitors)
                with open(LUA_MONITORS_PATH, "w") as f:
                    f.write(content)
                log.info(f"Saved Lua monitor configuration to {LUA_MONITORS_PATH}")
                saved_any = True

            if not self.is_lua_mode() or os.path.exists(LEGACY_MONITORS_PATH) or os.path.exists(os.path.join(HYPR_DIR, "hyprland.conf")):
                os.makedirs(HYPR_DIR, exist_ok=True)
                if os.path.exists(LEGACY_MONITORS_PATH) and not os.path.exists(LEGACY_MONITORS_BAK):
                    shutil.copy2(LEGACY_MONITORS_PATH, LEGACY_MONITORS_BAK)
                content = self.generate_legacy_config(monitors)
                with open(LEGACY_MONITORS_PATH, "w") as f:
                    f.write(content)
                log.info(f"Saved legacy monitor configuration to {LEGACY_MONITORS_PATH}")
                saved_any = True

            return saved_any
        except Exception as e:
            log.error(f"Failed to save monitor configuration: {e}")
            return False
