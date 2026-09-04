import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk
from mannux.backend.config import ConfigManager
from mannux.backend.power import PowerManager
from mannux.backend.hypridle import HypridleSync
from mannux.pages.power_screen import PowerScreenPage
from mannux.pages.display import DisplaysPage
from mannux.pages.placeholder import PlaceholderPage
from mannux.pages.about import AboutPage

class MainWindow(Adw.PreferencesWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Mannux Settings")
        self.set_default_size(880, 720)
        self.set_search_enabled(True)

        self.config_mgr = ConfigManager.get_instance()
        self.power_mgr = PowerManager.get_instance()
        self.hypridle_sync = HypridleSync(self.power_mgr)

        self._init_pages()
        self._init_shortcuts()

    def show_toast(self, message: str):
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.add_toast(toast)

    def _init_pages(self):
        # 1. Power & Screen Settings
        self.power_page = PowerScreenPage(
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr,
            hypridle_sync=self.hypridle_sync,
            toast_callback=self.show_toast
        )
        self.add(self.power_page)

        # 2. Displays & Monitors Module
        self.display_page = DisplaysPage(
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr,
            toast_callback=self.show_toast
        )
        self.add(self.display_page)

        # 3. Appearance (Placeholder)
        self.appearance_page = PlaceholderPage(
            tag="appearance",
            title="Appearance",
            icon_name="preferences-desktop-theme-symbolic",
            description="Hyprland borders, blur, gaps, animations, and GTK theme settings.",
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr
        )
        self.add(self.appearance_page)

        # 4. Keybindings (Placeholder)
        self.keybindings_page = PlaceholderPage(
            tag="keybindings",
            title="Keybindings",
            icon_name="input-keyboard-symbolic",
            description="Hyprland hotkey bindings viewer and custom keybind manager.",
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr
        )
        self.add(self.keybindings_page)

        # 5. About
        self.about_page = AboutPage(
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr
        )
        self.add(self.about_page)

        self.set_visible_page_name("power")

    def _init_shortcuts(self):
        # Action map
        action_group = Gio.SimpleActionGroup.new()

        # Quit
        quit_act = Gio.SimpleAction.new("quit", None)
        quit_act.connect("activate", lambda a, p: self.close())
        action_group.add_action(quit_act)

        # Reload
        reload_act = Gio.SimpleAction.new("reload", None)
        reload_act.connect("activate", lambda a, p: self._on_reload_shortcut())
        action_group.add_action(reload_act)

        self.insert_action_group("win", action_group)

        # Shortcut Controller
        controller = Gtk.ShortcutController.new()
        controller.set_scope(Gtk.ShortcutScope.LOCAL)

        # Ctrl+Q
        trigger_q = Gtk.ShortcutTrigger.parse_string("<Primary>q")
        action_q = Gtk.NamedAction.new("win.quit")
        controller.add_shortcut(Gtk.Shortcut.new(trigger_q, action_q))

        # Ctrl+R
        trigger_r = Gtk.ShortcutTrigger.parse_string("<Primary>r")
        action_r = Gtk.NamedAction.new("win.reload")
        controller.add_shortcut(Gtk.Shortcut.new(trigger_r, action_r))

        self.add_controller(controller)

    def _on_reload_shortcut(self):
        success = self.hypridle_sync.sync_and_reload(self.config_mgr.config)
        self.power_page._update_daemon_status()
        self.show_toast("Reloaded configuration and hypridle daemon!" if success else "Failed to reload hypridle")
