import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
from .base import BasePage

class PlaceholderPage(BasePage):
    def __init__(self, tag: str, title: str, icon_name: str, description: str, **kwargs):
        self.tag = tag
        self.title = title
        self.icon_name = icon_name
        super().__init__(**kwargs)

        group = Adw.PreferencesGroup()
        self.add(group)

        status_page = Adw.StatusPage()
        status_page.set_icon_name(icon_name)
        status_page.set_title(title)
        status_page.set_description(description)
        group.add(status_page)
