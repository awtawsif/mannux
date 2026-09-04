import pytest
from mannux.backend.display import (
    MonitorInfo,
    DisplayManager,
    TRANSFORM_OPTIONS,
    SCALE_PRESETS,
    BITDEPTH_OPTIONS,
    VRR_OPTIONS,
    CM_PRESETS
)

@pytest.fixture
def sample_monitor():
    return MonitorInfo(
        id=0,
        name="eDP-1",
        description="Built-in Display",
        make="BOE",
        model="0x0A31",
        width=1920,
        height=1200,
        refresh_rate=60.0,
        x=0,
        y=0,
        scale=1.25,
        transform=0,
        focused=True,
        dpms_status=True,
        vrr=0,
        bitdepth=8,
        cm="srgb",
        icc_profile="",
        sdr_brightness=1.0,
        sdr_saturation=1.0,
        disabled=False,
        available_modes=[
            "1920x1200@60.00Hz",
            "1920x1200@48.00Hz",
            "1680x1050@60.00Hz",
            "1280x800@60.00Hz"
        ]
    )

def test_monitor_aspect_ratio(sample_monitor):
    assert sample_monitor.aspect_ratio == "16:10"
    assert "1920 × 1200 (16:10)" in sample_monitor.resolution_str
    assert sample_monitor.mode_str == "1920x1200@60.00Hz"

def test_resolutions_and_rates_parser(sample_monitor):
    res_map = sample_monitor.get_resolutions_and_rates()
    assert (1920, 1200) in res_map
    assert 60.0 in res_map[(1920, 1200)]
    assert 48.0 in res_map[(1920, 1200)]
    assert (1680, 1050) in res_map
    assert (1280, 800) in res_map

def test_build_lua_command(sample_monitor):
    dm = DisplayManager()
    cmd = dm.build_lua_command(sample_monitor)
    assert "hl.monitor({" in cmd
    assert "output = 'eDP-1'" in cmd
    assert "mode = '1920x1200@60.00'" in cmd
    assert "position = '0x0'" in cmd
    assert "scale = 1.25" in cmd
    assert "transform = 0" in cmd
    assert "bitdepth = 8" in cmd
    assert "vrr = 0" in cmd
    assert "cm = 'srgb'" in cmd
    assert "sdrbrightness = 1.00" in cmd
    assert "sdrsaturation = 1.00" in cmd

def test_build_legacy_command(sample_monitor):
    dm = DisplayManager()
    cmd = dm.build_legacy_command(sample_monitor)
    assert "monitor = eDP-1, 1920x1200@60.00, 0x0, 1.25, transform, 0, bitdepth, 8, vrr, 0, cm, srgb, sdrbrightness, 1.00, sdrsaturation, 1.00" in cmd

def test_disabled_monitor(sample_monitor):
    sample_monitor.disabled = True
    dm = DisplayManager()
    lua_cmd = dm.build_lua_command(sample_monitor)
    legacy_cmd = dm.build_legacy_command(sample_monitor)

    assert "mode = 'disable'" in lua_cmd
    assert "monitor = eDP-1, disable" in legacy_cmd

def test_mirror_monitor(sample_monitor):
    sample_monitor.mirror_of = "HDMI-A-1"
    dm = DisplayManager()
    lua_cmd = dm.build_lua_command(sample_monitor)
    legacy_cmd = dm.build_legacy_command(sample_monitor)

    assert "mirror = 'HDMI-A-1'" in lua_cmd
    assert "mirror, HDMI-A-1" in legacy_cmd

def test_color_management_and_icc(sample_monitor):
    sample_monitor.cm = "dcip3"
    sample_monitor.sdr_brightness = 1.25
    sample_monitor.sdr_saturation = 1.10
    dm = DisplayManager()
    lua_cmd = dm.build_lua_command(sample_monitor)
    legacy_cmd = dm.build_legacy_command(sample_monitor)

    assert "cm = 'dcip3'" in lua_cmd
    assert "sdrbrightness = 1.25" in lua_cmd
    assert "sdrsaturation = 1.10" in lua_cmd
    assert "cm, dcip3" in legacy_cmd

    # Test custom ICC profile overrides cm
    sample_monitor.icc_profile = "/home/user/.local/share/icc/display.icc"
    lua_icc_cmd = dm.build_lua_command(sample_monitor)
    legacy_icc_cmd = dm.build_legacy_command(sample_monitor)

    assert "icc = '/home/user/.local/share/icc/display.icc'" in lua_icc_cmd
    assert "icc, /home/user/.local/share/icc/display.icc" in legacy_icc_cmd

def test_advanced_vrr_and_bitdepth(sample_monitor):
    sample_monitor.vrr = 3 # Content-Aware Smart VRR
    sample_monitor.bitdepth = 10 # 10-bit Deep Color
    dm = DisplayManager()
    lua_cmd = dm.build_lua_command(sample_monitor)
    legacy_cmd = dm.build_legacy_command(sample_monitor)

    assert "bitdepth = 10" in lua_cmd
    assert "vrr = 3" in lua_cmd
    assert "bitdepth, 10, vrr, 3" in legacy_cmd

def test_generate_configs(sample_monitor):
    dm = DisplayManager()
    lua_cfg = dm.generate_lua_config([sample_monitor])
    legacy_cfg = dm.generate_legacy_config([sample_monitor])

    assert "Generated automatically by Mannux Settings" in lua_cfg
    assert "hl.monitor({" in lua_cfg
    assert "Generated automatically by Mannux Settings" in legacy_cfg
    assert "monitor = eDP-1" in legacy_cfg
