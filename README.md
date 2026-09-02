# Mannux Settings

A modern GTK4 + Libadwaita settings application for Arch Linux running Hyprland.

![Mannux Settings Icon](data/icons/hicolor/scalable/apps/com.mannux.Settings.svg)

## Features

- **Screen & Power Management**:
  - Independent profiles for **On Battery** and **Plugged In (AC)**.
  - Screen Dimming timeout and dim brightness control (`brightnessctl`).
  - Screen Turn Off (DPMS) timeout (`hyprctl dispatch dpms off/on`).
  - Automatic Session Lock (`hyprlock` integration).
  - Automatic Suspend (`systemctl suspend`).
  - Real-time battery status and power source detection via sysfs.
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

### Option 1: Download Precompiled Release Binary
Download the latest `mannux-linux-x86_64.tar.gz` or standalone executable `mannux-x86_64` from [GitHub Releases](https://github.com/awtawsif/mannux/releases).

Extract and install:
```bash
tar -xvf mannux-linux-x86_64.tar.gz
cd mannux-linux-x86_64
./install.sh
```

### Option 2: Quick Launch (Development from Source)
```bash
./run.sh
```

### Option 3: Install from Source
```bash
./install.sh
```
This adds the `mannux` binary to `~/.local/bin/mannux` and registers the desktop application for app launchers (`rofi`, `wofi`, `fuzzel`, etc.).

### Option 4: Pip / Editable Install
```bash
pip install -e .
```

## Creating a Release

The repository includes a GitHub Actions workflow that automatically compiles a standalone binary and publishes a GitHub Release when a version tag is pushed:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Requirements
- Python 3.10+ (if running from source)
- `python-gobject` (PyGObject)
- `gtk4` & `libadwaita`
- `hypridle` (for idle management)
- `hyprlock` (optional, for screen locking)
- `brightnessctl` (optional, for screen dimming)
