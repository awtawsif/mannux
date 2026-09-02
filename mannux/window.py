import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio
from mannux.backend.config import ConfigManager
from mannux.backend.power import PowerManager
from mannux.backend.hypridle import HypridleSync
from mannux.pages.power_screen import PowerScreenPage
from mannux.pages.placeholder import PlaceholderPage
from mannux.pages.about import AboutPage

class MainWindow(Adw.PreferencesWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Mannux Settings")
        self.set_default_size(860, 680)
        self.set_search_enabled(True)

        self.config_mgr = ConfigManager.get_instance()
        self.power_mgr = PowerManager()
        self.hypridle_sync = HypridleSync(self.power_mgr)

        self._init_pages()

    def show_toast(self, message: str):
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.add_toast(toast)

    def _init_pages(self):
        # 1. Power & Screen Settings (Primary active module)
        self.power_page = PowerScreenPage(
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr,
            hypridle_sync=self.hypridle_sync,
            toast_callback=self.show_toast
        )
        self.add(self.power_page)

        # 2. Displays (Future module placeholder)
        self.display_page = PlaceholderPage(
            tag="displays",
            title="Displays",
            icon_name="video-display-symbolic",
            description="Display resolution, scaling, and multi-monitor layout settings will be available here.",
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr
        )
        self.add(self.display_page)

        # 3. Appearance (Future module placeholder)
        self.appearance_page = PlaceholderPage(
            tag="appearance",
            title="Appearance",
            icon_name="preferences-desktop-theme-symbolic",
            description="Hyprland borders, blur, gaps, animations, and GTK theme settings will be available here.",
            config_mgr=self.config_mgr,
            power_mgr=self.power_mgr
        )
        self.add(self.appearance_page)

        # 4. Keybindings (Future module placeholder)
        self.keybindings_page = PlaceholderPage(
            tag="keybindings",
            title="Keybindings",
            icon_name="input-keyboard-symbolic",
            description="Hyprland keybind viewer and hotkey customizer will be available here.",
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

        # Set default visible page
        self.set_visible_page_name("power")
