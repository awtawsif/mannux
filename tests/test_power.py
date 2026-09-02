import pytest
from mannux.backend.power import PowerManager, PowerStatus

def test_power_manager_status():
    mgr = PowerManager()
    status = mgr.get_status()
    assert isinstance(status, PowerStatus)
    assert isinstance(status.has_battery, bool)
    assert isinstance(status.on_ac, bool)

def test_power_manager_listener():
    mgr = PowerManager()
    received = []
    def on_power(st):
        received.append(st)

    mgr.add_listener(on_power)
    mgr._notify(mgr.get_status())
    assert len(received) == 1

    mgr.remove_listener(on_power)
    mgr._notify(mgr.get_status())
    assert len(received) == 1
