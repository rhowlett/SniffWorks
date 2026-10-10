"""
ui/tabs/preferences_tab.py
[XREF: prefs-tab] The shared Preferences tab body: the ThemePicker inside a
scroll area (the picker grew with the Theme Files group), with room for
app-specific preference sections to be added below in later phases (e.g. the
serial-port / baud settings planned for the Nucleo sniffer).
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ui.widgets.theme_picker import ThemePicker


class PreferencesTab(QWidget):
    """Emits theme_apply_requested(value); value is a named theme or
    'file:<path>' (see ui.widgets.theme_picker)."""

    theme_apply_requested = Signal(str)

    def __init__(self, current_theme: str = "default", parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(6, 6, 6, 6)
        self._body_layout.setSpacing(8)

        self._picker = ThemePicker(current_theme, parent=body)
        self._picker.theme_apply_requested.connect(self.theme_apply_requested)
        self._body_layout.addWidget(self._picker)

        scroll.setWidget(body)
        root.addWidget(scroll)

    # ------------------------------------------------------------------
    def set_current(self, theme_name: str):
        self._picker.set_current(theme_name)

    def refresh_theme_files(self):
        self._picker.refresh_theme_files()

    def add_section(self, widget: QWidget):
        """Append an app-specific preferences section below the theme picker."""
        self._body_layout.addWidget(widget)
