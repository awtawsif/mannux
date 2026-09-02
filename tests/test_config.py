import os
import json
import tempfile
import pytest
from mannux.backend.config import ConfigManager, AppConfig, PowerProfileConfig

def test_config_defaults():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name
    try:
        os.remove(tmp_path)
        mgr = ConfigManager(config_path=tmp_path)
        assert mgr.config.version == 1
        assert mgr.config.general.inhibit_idle is False
        assert mgr.config.battery.dim_enabled is True
        assert mgr.config.battery.dim_timeout == 150
        assert mgr.config.battery.dim_brightness == 10
        assert os.path.exists(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_config_save_load():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name
    try:
        mgr = ConfigManager(config_path=tmp_path)
        mgr.config.battery.dim_timeout = 420
        mgr.config.general.inhibit_idle = True
        mgr.save()

        # Load fresh
        mgr2 = ConfigManager(config_path=tmp_path)
        assert mgr2.config.battery.dim_timeout == 420
        assert mgr2.config.general.inhibit_idle is True
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_config_listener():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name
    try:
        mgr = ConfigManager(config_path=tmp_path)
        called = []
        def listener(cfg):
            called.append(cfg.battery.dim_timeout)

        mgr.add_listener(listener)
        mgr.config.battery.dim_timeout = 999
        mgr.save()

        assert called == [999]

        mgr.remove_listener(listener)
        mgr.config.battery.dim_timeout = 111
        mgr.save()
        assert called == [999]
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_reset_defaults():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name
    try:
        mgr = ConfigManager(config_path=tmp_path)
        mgr.config.battery.dim_timeout = 9999
        mgr.config.general.inhibit_idle = True
        mgr.save()

        mgr.reset_to_defaults()
        assert mgr.config.battery.dim_timeout == 150
        assert mgr.config.general.inhibit_idle is False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
