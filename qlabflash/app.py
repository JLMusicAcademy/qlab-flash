"""Application entry point: show the connect dialog, then the main window."""

from __future__ import annotations

import argparse
import os
import sys

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.qlab-flash.json")


def _resource(rel_path: str) -> str:
    """Locate a bundled data file, whether running from source or a frozen app.

    PyInstaller unpacks data files under ``sys._MEIPASS``; from source they sit
    next to the package.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base, rel_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="QLab Flash — bulk mic mute/unmute editor for QLab + X32.")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH,
                        help="Path to a JSON config file "
                             f"(default: {DEFAULT_CONFIG_PATH}).")
    parser.add_argument("--demo", action="store_true",
                        help="Start in demo mode against a simulated QLab.")
    # parse_known_args so macOS-injected args (e.g. -psn_…) don't crash launch.
    args, _ = parser.parse_known_args(argv)

    # Import Qt lazily so non-GUI tooling (and tests) don't require PySide6.
    from PySide6.QtGui import QColor, QIcon, QPalette
    from PySide6.QtWidgets import QApplication, QDialog

    from .config import Config
    from .gui.connect_dialog import ConnectDialog
    from .gui.main_window import MainWindow

    config = Config.load(args.config)

    app = QApplication(sys.argv)
    app.setApplicationName("QLab Flash")
    app.setApplicationDisplayName("QLab Flash")

    # Force a consistent light theme. The mic grid relies on dark-on-light
    # checkboxes and faint grid lines; macOS Dark Mode renders those nearly
    # invisible, so we pin the Fusion style with an explicit light palette.
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#ECECEC"))
    pal.setColor(QPalette.WindowText, QColor("#1A1A1A"))
    pal.setColor(QPalette.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.AlternateBase, QColor("#F3F5F8"))
    pal.setColor(QPalette.Text, QColor("#1A1A1A"))
    pal.setColor(QPalette.Button, QColor("#E6E6E6"))
    pal.setColor(QPalette.ButtonText, QColor("#1A1A1A"))
    pal.setColor(QPalette.Highlight, QColor("#2C6BBF"))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor("#FFFFE6"))
    pal.setColor(QPalette.ToolTipText, QColor("#1A1A1A"))
    pal.setColor(QPalette.PlaceholderText, QColor("#8A8A8A"))
    app.setPalette(pal)

    icon_path = _resource(os.path.join("assets", "icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    dialog = ConnectDialog(config)
    if args.demo:
        dialog.demo_check.setChecked(True)
        dialog._discover()
    if dialog.exec() != QDialog.Accepted or dialog.client is None:
        return 0

    try:
        config.save(args.config)
    except OSError:
        pass  # not fatal if we can't persist preferences

    window = MainWindow(dialog.client, dialog.workspace_id,
                        dialog.workspace_name, config, mock=dialog.mock,
                        config_path=args.config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
