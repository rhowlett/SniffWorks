"""
ui.widgets
Reusable composite widgets shared across the apps: a validated hex line edit, a
theme picker, the self-contained decode-schema editor, and the framing kit
(application shell, sidebar sections, and a validated file-picker row).
"""

from ui.widgets.hex_line_edit import HexLineEdit
from ui.widgets.theme_picker import ThemePicker
from ui.widgets.decode_editor import DecodeEditor
from ui.widgets.section import Section
from ui.widgets.sidebar import Sidebar, make_tab_body
from ui.widgets.file_picker import FilePickerRow
from ui.widgets.app_window import (AppWindow, StatusBarNotifier,
                                   ConfirmingCloseMixin)
from ui.widgets.help_panel import HelpPanel
from ui.widgets.exit_panel import ExitPanel

__all__ = [
    "HexLineEdit", "ThemePicker", "DecodeEditor",
    "Section", "Sidebar", "make_tab_body", "FilePickerRow", "AppWindow",
    "StatusBarNotifier", "ConfirmingCloseMixin",
    "HelpPanel", "ExitPanel",
]
from ui.widgets.tab_popout import TabPopoutController  # noqa: F401,E402
