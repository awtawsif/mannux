# Mannux Settings

A modern GTK4 + Libadwaita settings application for Arch Linux running Hyprland.

![Mannux Settings Icon](data/icons/hicolor/scalable/apps/com.mannux.Settings.svg)

## Features

- **Screen & Power Management**:
  - Independent profiles for **On Battery** and **Plugged In (AC)**.
  - Screen Dimming timeout and dim brightness control.
  - Screen Turn Off (DPMS) timeout.
  - Automatic Session Lock (`hyprlock` integration).
  - Automatic Suspend (`systemctl suspend`).
  - Real-time battery status and power source detection.
  - **Keep Screen Awake (Inhibit Idle)**: Quick toggle for presentation/media viewing mode.
- **Hypridle Integration**:
  - Automatic generation and synchronization of `~/.config/hypr/hypridle.conf`.
  - Automatic backup of existing configuration on first launch.
  - Seamless live reloading/restarting of the `hypridle` daemon.
- **Modern Libadwaita UI**:
  - GNOME HIG compliant interface with native dark/light mode support.
  - Responsive sidebar navigation and search.
  - Modular architecture ready for additional modules (Displays, Appearance, Keybindings).

## Installation & Running

### Quick Launch (Development)
```bash
./run.sh
```

### Install to System (User Level)
```bash
./install.sh
```
This adds the `mannux` binary to `~/.local/bin/mannux` and registers the desktop application for app launchers (`rofi`, `wofi`, `fuzzel`, etc.).

### Pip / Editable Install
```bash
pip install -e .
```

## Requirements
- Python 3.10+
- `python-gobject` (PyGObject)
- `gtk4` & `libadwaita`
- `hypridle` (for idle management)
- `hyprlock` (optional, for screen locking)
- `brightnessctl` (optional, for screen dimming)
