import pytest
from mannux.backend.config import AppConfig
from mannux.backend.power import PowerManager, PowerStatus
from mannux.backend.hypridle import HypridleSync

class MockPowerManager:
    def __init__(self, has_battery=True, on_ac=False, ac_name="ADP1"):
        self._status = PowerStatus(
            has_battery=has_battery,
            on_ac=on_ac,
            ac_name=ac_name,
            battery_name="BAT0" if has_battery else None,
            battery_percentage=80 if has_battery else None,
            battery_state="Discharging" if has_battery else None
        )

    def get_status(self):
        return self._status

def test_generate_config_standard():
    mock_power = MockPowerManager(has_battery=True, on_ac=False, ac_name="ADP1")
    sync = HypridleSync(power_mgr=mock_power)
    cfg = AppConfig()

    content = sync.generate_config(cfg)
    assert "general {" in content
    assert "lock_cmd = pidof hyprlock || hyprlock" in content
    assert "listener {" in content
    assert "brightnessctl -s set 10%" in content
    assert "loginctl lock-session" in content
    assert "hyprctl dispatch dpms off" in content
    assert "systemctl suspend" in content

def test_generate_config_inhibited():
    mock_power = MockPowerManager(has_battery=True, on_ac=False)
    sync = HypridleSync(power_mgr=mock_power)
    cfg = AppConfig()
    cfg.general.inhibit_idle = True

    content = sync.generate_config(cfg)
    assert "general {" in content
    assert "IDLE INHIBITION ACTIVE" in content
    assert "listener {" not in content

def test_generate_config_desktop_mode():
    mock_power = MockPowerManager(has_battery=False, on_ac=True)
    sync = HypridleSync(power_mgr=mock_power)
    cfg = AppConfig()

    content = sync.generate_config(cfg)
    assert "general {" in content
    # Desktop mode should not contain cat /sys/class/power_supply condition
    assert "/sys/class/power_supply" not in content
    assert "hyprctl dispatch dpms off" in content

def test_listener_ordering():
    mock_power = MockPowerManager(has_battery=False, on_ac=True)
    sync = HypridleSync(power_mgr=mock_power)
    cfg = AppConfig()
    cfg.ac.dim_enabled = True
    cfg.ac.dim_timeout = 100
    cfg.ac.dpms_enabled = True
    cfg.ac.dpms_timeout = 500
    cfg.ac.lock_enabled = True
    cfg.ac.lock_timeout = 300
    cfg.ac.suspend_enabled = True
    cfg.ac.suspend_timeout = 1000

    content = sync.generate_config(cfg)
    pos_dim = content.find("timeout = 100")
    pos_lock = content.find("timeout = 300")
    pos_dpms = content.find("timeout = 500")
    pos_susp = content.find("timeout = 1000")

    assert pos_dim < pos_lock < pos_dpms < pos_susp
