import sys
import json
import argparse
from typing import Optional
from mannux import __version__
from mannux.backend.config import ConfigManager
from mannux.backend.power import PowerManager
from mannux.backend.hypridle import HypridleSync
from mannux.backend.logger import setup_logger, log

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mannux",
        description="Modern GTK4/Libadwaita Settings App & CLI for Arch Linux (Hyprland)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose log output")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    # Headless Automation Flags
    group = parser.add_argument_group("Headless & Automation Options")
    group.add_argument("--inhibit-toggle", action="store_true", help="Toggle idle inhibition (Keep Awake / Presentation mode) and exit")
    group.add_argument("--inhibit-on", action="store_true", help="Enable idle inhibition and exit")
    group.add_argument("--inhibit-off", action="store_true", help="Disable idle inhibition and exit")
    group.add_argument("--sync", action="store_true", help="Regenerate hypridle.conf and reload daemon headlessly")
    group.add_argument("--status", action="store_true", help="Display current power, battery, and daemon status")
    group.add_argument("--json", action="store_true", help="Output status in machine-readable JSON format")
    return parser

def handle_cli_commands(args: argparse.Namespace) -> Optional[int]:
    setup_logger(verbose=args.verbose, debug=args.debug)
    config_mgr = ConfigManager.get_instance()
    power_mgr = PowerManager.get_instance()
    hypridle_sync = HypridleSync(power_mgr)

    if args.inhibit_toggle:
        curr = config_mgr.config.general.inhibit_idle
        new_val = not curr
        config_mgr.config.general.inhibit_idle = new_val
        config_mgr.save()
        hypridle_sync.sync_and_reload(config_mgr.config)
        state_str = "ON" if new_val else "OFF"
        if args.json:
            print(json.dumps({"inhibit_idle": new_val}))
        else:
            print(f"Keep Awake (Idle Inhibition): {state_str}")
        return 0

    if args.inhibit_on:
        config_mgr.config.general.inhibit_idle = True
        config_mgr.save()
        hypridle_sync.sync_and_reload(config_mgr.config)
        if args.json:
            print(json.dumps({"inhibit_idle": True}))
        else:
            print("Keep Awake (Idle Inhibition): ON")
        return 0

    if args.inhibit_off:
        config_mgr.config.general.inhibit_idle = False
        config_mgr.save()
        hypridle_sync.sync_and_reload(config_mgr.config)
        if args.json:
            print(json.dumps({"inhibit_idle": False}))
        else:
            print("Keep Awake (Idle Inhibition): OFF")
        return 0

    if args.sync:
        success = hypridle_sync.sync_and_reload(config_mgr.config)
        if args.json:
            print(json.dumps({"sync_success": success}))
        else:
            print("Hypridle configuration regenerated and daemon reloaded." if success else "Failed to reload hypridle.")
        return 0 if success else 1

    if args.status:
        power = power_mgr.get_status()
        daemon = hypridle_sync.get_daemon_status()
        inhibit = config_mgr.config.general.inhibit_idle

        data = {
            "power_source": "AC" if power.on_ac else "Battery",
            "battery_percentage": power.battery_percentage,
            "battery_state": power.battery_state,
            "has_battery": power.has_battery,
            "inhibit_idle": inhibit,
            "hypridle_installed": daemon.is_installed,
            "hypridle_running": daemon.is_running,
            "hypridle_pid": daemon.pid,
            "hypridle_description": daemon.description,
        }

        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print("=== Mannux Status ===")
            print(f"Power Source       : {data['power_source']}")
            if power.has_battery:
                print(f"Battery Level      : {power.battery_percentage}% ({power.battery_state})")
            print(f"Keep Awake Mode    : {'ACTIVE (Inhibited)' if inhibit else 'Disabled'}")
            print(f"Hypridle Daemon    : {daemon.description}")
        return 0

    return None
