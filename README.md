# Mannux Settings

A modern, fast GTK4 + Libadwaita settings application and CLI for Arch Linux running Hyprland.

![Mannux Settings Icon](data/icons/hicolor/scalable/apps/com.mannux.Settings.svg)

## Features

- **Screen & Power Management**:
  - **Dual Power Profiles**: Separate, customizable timeouts for **On Battery** and **Plugged In (AC Power)**.
  - **Segmented Profile Switcher**: Interactive switcher with real-time active power state indicator.
  - **Screen Dimming**: Configurable timeout (presets + custom seconds) and exact brightness percentage control.
  - **Screen Off (DPMS)**: Display power management timeout (`hyprctl dispatch dpms off/on`).
  - **Automatic Session Lock**: Configurable idle lock delay (`hyprlock` integration).
  - **System Suspend**: Auto-suspend timeout (`systemctl suspend`).
  - **Keep Screen Awake (Inhibit Idle)**: Quick toggle for presentation/media viewing mode.
  - **Live System Detection**: Zero-latency UPower D-Bus event listening with sysfs fallback.
- **Hypridle Integration & Daemon Supervision**:
  - Live status badge showing daemon health (🟢 Running with PID/systemd, 🔴 Stopped, ⚠️ Missing).
  - One-click Start / Restart button.
  - Automatic synchronization and backup of `~/.config/hypr/hypridle.conf`.
  - Live syntax-highlighted code preview drawer for `hypridle.conf`.
- **Scriptable Headless CLI (Waybar / Hotkeys)**:
  - `mannux --inhibit-toggle` to toggle presentation mode without launching the GUI.
  - `mannux --status [--json]` for integration with status bars (Waybar, Eww, AGS).
  - `mannux --sync` for headless config regeneration and daemon reload.
- **Keyboard Shortcuts**:
  - `Ctrl + Q`: Quit application
  - `Ctrl + R`: Reload configuration and restart hypridle daemon

---

## Installation & Running

### Option 1: Download Precompiled Release Binary
Download the latest `mannux-linux-x86_64.tar.gz` or standalone executable `mannux-x86_64` from [GitHub Releases](https://github.com/awtawsif/mannux/releases).

Extract and install:
```bash
tar -xvf mannux-linux-x86_64.tar.gz
cd mannux-linux-x86_64
./install.sh
```

### Option 2: Run from Source
```bash
./run.sh
```

### Option 3: Install Locally from Source
```bash
./install.sh
```
This adds the `mannux` binary to `~/.local/bin/mannux` and registers the desktop application for app launchers (`rofi`, `wofi`, `fuzzel`, etc.).

---

## CLI & Waybar Integration

### Waybar Module Example (`config.jsonc`)
```jsonc
"custom/idle_inhibit": {
    "format": "{}",
    "return-type": "json",
    "exec": "mannux --status --json | jq -c '{text: (if .inhibit_idle then \" \" else \" \" end), tooltip: (if .inhibit_idle then \"Keep Awake: ON\" else \"Keep Awake: OFF\" end), class: (if .inhibit_idle then \"active\" else \"inactive\" end)}'",
    "on-click": "mannux --inhibit-toggle",
    "interval": 5
}
```

### Hyprland Keybind Example (`hyprland.conf`)
```ini
# Toggle Keep Awake mode
bind = $mainMod SHIFT, I, exec, mannux --inhibit-toggle
# Open Mannux Settings
bind = $mainMod, S, exec, mannux
```

---

## Development & Testing

Run unit and integration tests:
```bash
pytest -v
```

Release a new version:
```bash
git tag v0.2.0
git push origin v0.2.0
```

---

## Requirements
- Python 3.10+
- `python-gobject` (PyGObject)
- `gtk4` & `libadwaita`
- `hypridle` (idle management)
- `hyprlock` (screen locking)
- `brightnessctl` (screen dimming)
