import gi
import os
import platform
import subprocess
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
from .base import BasePage

class AboutPage(BasePage):
    tag = "about"
    title = "About System"
    icon_name = "help-about-symbolic"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_ui()

    def _get_hyprland_version(self) -> str:
        try:
            res = subprocess.run(["hyprctl", "version"], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                if "Hyprland" in line or "Tag" in line or "version" in line.lower():
                    return line.strip()
            return "Hyprland (detected)"
        except Exception:
            return "Hyprland"

    def _get_distro_name(self) -> str:
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return "Arch Linux"

    def _build_ui(self):
        # App Info Group
        app_group = Adw.PreferencesGroup()
        self.add(app_group)

        app_status = Adw.StatusPage()
        app_status.set_icon_name("preferences-system-symbolic")
        app_status.set_title("Mannux Settings")
        app_status.set_description("Modern GTK4/Libadwaita Control Center for Arch Linux & Hyprland")
        app_group.add(app_status)

        # System Details Group
        sys_group = Adw.PreferencesGroup()
        sys_group.set_title("System Information")
        self.add(sys_group)

        # Distro
        distro_row = Adw.ActionRow()
        distro_row.set_title("Operating System")
        distro_row.set_subtitle(self._get_distro_name())
        distro_row.set_icon_name("software-update-available-symbolic")
        sys_group.add(distro_row)

        # Compositor
        wm_row = Adw.ActionRow()
        wm_row.set_title("Window Manager")
        wm_row.set_subtitle(self._get_hyprland_version())
        wm_row.set_icon_name("preferences-desktop-display-symbolic")
        sys_group.add(wm_row)

        # Kernel
        kernel_row = Adw.ActionRow()
        kernel_row.set_title("Linux Kernel")
        kernel_row.set_subtitle(platform.release())
        kernel_row.set_icon_name("dialog-information-symbolic")
        sys_group.add(kernel_row)

        # Toolkit
        gtk_row = Adw.ActionRow()
        gtk_row.set_title("GUI Toolkit")
        gtk_row.set_subtitle(f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()} + Libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}")
        gtk_row.set_icon_name("applications-graphics-symbolic")
        sys_group.add(gtk_row)
