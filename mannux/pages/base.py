import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
from mannux.backend.config import ConfigManager
from mannux.backend.power import PowerManager

class BasePage(Adw.PreferencesPage):
    tag: str = "base"
    title: str = "Base Page"
    icon_name: str = "application-x-executable-symbolic"

    def __init__(self, config_mgr: ConfigManager, power_mgr: PowerManager, **kwargs):
        super().__init__(**kwargs)
        self.set_title(self.title)
        self.set_icon_name(self.icon_name)
        self.set_name(self.tag)
        self.config_mgr = config_mgr
        self.power_mgr = power_mgr
