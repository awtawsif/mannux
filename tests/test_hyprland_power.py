import pytest
from mannux.backend.config import HyprlandPowerConfig
from mannux.backend.hyprland_power import HyprlandPowerSync, get_lid_command, LID_ACTIONS

def test_get_lid_command():
    assert get_lid_command("suspend") == "systemctl suspend"
    assert get_lid_command("lock") == "loginctl lock-session"
    assert get_lid_command("dpms_off") == "hyprctl dispatch dpms off"
    assert get_lid_command("ignore") is None

def test_generate_lua_config_default():
    sync = HyprlandPowerSync()
    cfg = HyprlandPowerConfig(
        mouse_move_enables_dpms=False,
        key_press_enables_dpms=False,
        lid_switch_action="ignore"
    )
    lua = sync.generate_lua_config(cfg)
    assert "hl.config({" in lua
    assert "mouse_move_enables_dpms = false" in lua
    assert "key_press_enables_dpms = false" in lua
    assert "Lid Switch" not in lua

def test_generate_lua_config_with_lid_and_wake():
    sync = HyprlandPowerSync()
    cfg = HyprlandPowerConfig(
        mouse_move_enables_dpms=True,
        key_press_enables_dpms=True,
        lid_switch_action="suspend"
    )
    lua = sync.generate_lua_config(cfg)
    assert "mouse_move_enables_dpms = true" in lua
    assert "key_press_enables_dpms = true" in lua
    assert 'hl.bind("switch:on:Lid Switch", hl.dsp.exec_cmd([[systemctl suspend]]), { locked = true })' in lua

def test_generate_lua_config_with_dpms_off_lid():
    sync = HyprlandPowerSync()
    cfg = HyprlandPowerConfig(
        mouse_move_enables_dpms=True,
        key_press_enables_dpms=False,
        lid_switch_action="dpms_off"
    )
    lua = sync.generate_lua_config(cfg)
    assert 'hl.bind("switch:on:Lid Switch", hl.dsp.exec_cmd([[hyprctl dispatch dpms off]]), { locked = true })' in lua
    assert 'hl.bind("switch:off:Lid Switch", hl.dsp.exec_cmd([[hyprctl dispatch dpms on]]), { locked = true })' in lua

def test_generate_legacy_config():
    sync = HyprlandPowerSync()
    cfg = HyprlandPowerConfig(
        mouse_move_enables_dpms=True,
        key_press_enables_dpms=True,
        lid_switch_action="lock"
    )
    conf = sync.generate_legacy_config(cfg)
    assert "misc {" in conf
    assert "mouse_move_enables_dpms = true" in conf
    assert "key_press_enables_dpms = true" in conf
    assert "bindl = , switch:on:Lid Switch, exec, loginctl lock-session" in conf
