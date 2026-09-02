import sys
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib
from mannux.window import MainWindow
from mannux.cli import create_parser, handle_cli_commands

class MannuxApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.mannux.Settings",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()

def main(args=None):
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    ret = handle_cli_commands(parsed_args)
    if ret is not None:
        return ret

    app = MannuxApp()
    return app.run([])
