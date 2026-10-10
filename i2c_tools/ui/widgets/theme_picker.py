"""
ui.widgets.theme_picker  [v0.1]
A reusable theme-selection widget, shared by the main tool's Preferences tab
and the standalone editors.

Offers three sources, applied via the single theme_apply_requested(str)
signal (handled by ui.theme.apply_theme, which dispatches on the value):

  * built-in named themes            -> emits the theme name ("dark", ...)
  * saved theme files                -> emits "file:<path>"
    (discovered in ui/themes/*.qt_theme.json, the project default location)
  * Custom Theme File... (browse)    -> emits "file:<chosen path>"

Also hosts the "Open Theme Editor" button that launches theme_editor.py as a
separate process (the editor restyles its own QApplication globally, so
running it in-process would clobber this app's theme).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QRadioButton, QButtonGroup,
    QPushButton, QLabel, QFileDialog,
)
from PySide6.QtCore import Signal
from ui.widgets.buttons import icon_button, button_row

from ui import theme
from ui.theme_config_loader import (
    discover_theme_files, theme_display_name, themes_dir, THEME_FILE_SUFFIX,
)


class ThemePicker(QWidget):
    """
    Emits theme_apply_requested(value) when Apply Theme is clicked.
    value is a named theme or "file:<path>" (see module docstring).
    """

    theme_apply_requested = Signal(str)

    def __init__(self, current_theme: str = "dark", parent=None):
        super().__init__(parent)
        self._radios: dict[str, QRadioButton] = {}     # value -> radio
        self._custom_path: str | None = None
        self._build_ui(current_theme)

    # ------------------------------------------------------------------
    def _build_ui(self, current_theme: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._group = QButtonGroup(self)

        # ---- built-in named themes ------------------------------------
        theme_box = QGroupBox("Theme")
        theme_lay = QVBoxLayout(theme_box)

        intro = QLabel("Select a color theme, then click Apply Theme.")
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        theme_lay.addWidget(intro)

        for name, label in theme.THEME_CHOICES:
            self._add_radio(theme_lay, name, label)
        root.addWidget(theme_box)

        # ---- saved theme files (ui/themes/*.qt_theme.json) -------------
        files_box = QGroupBox("Theme Files")
        files_lay = QVBoxLayout(files_box)

        hint = QLabel(f"Loaded from {themes_dir().name}/ "
                      f"(*{THEME_FILE_SUFFIX}). Create or edit these with "
                      "the Theme Editor below.")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        files_lay.addWidget(hint)

        self._files_lay = files_lay
        self._file_radio_values: list[str] = []
        self._populate_theme_files()

        # Custom theme file (anywhere on disk)
        self._custom_radio = QRadioButton("Custom Theme File...")
        self._group.addButton(self._custom_radio)
        files_lay.addWidget(self._custom_radio)

        self._custom_label = QLabel("(no file selected)")
        self._custom_label.setObjectName("mutedLabel")
        self._custom_label.setWordWrap(True)
        files_lay.addWidget(self._custom_label)

        # compact equal-width buttons with icons [XREF: ui-buttons]
        browse = icon_button("Browse...", "browse")
        browse.clicked.connect(self._on_browse_custom)
        refresh = icon_button("Refresh List", "refresh")
        refresh.clicked.connect(self.refresh_theme_files)
        files_lay.addLayout(button_row(browse, refresh, min_width=140))

        root.addWidget(files_box)

        # ---- editor launch ---------------------------------------------
        editor_box = QGroupBox("Theme Editor")
        editor_lay = QVBoxLayout(editor_box)
        editor_hint = QLabel("Design themes visually and save them into "
                             "ui/themes/ for the list above.")
        editor_hint.setObjectName("mutedLabel")
        editor_hint.setWordWrap(True)
        editor_lay.addWidget(editor_hint)

        self._editor_btn = icon_button("Open Theme Editor", "editor")
        self._editor_btn.clicked.connect(self._on_open_editor)
        editor_lay.addLayout(button_row(self._editor_btn, min_width=140))
        root.addWidget(editor_box)

        # ---- apply -------------------------------------------------------
        self._apply_btn = icon_button("Apply Theme", "apply", "btnApply")
        self._apply_btn.clicked.connect(self._on_apply)
        root.addLayout(button_row(self._apply_btn, min_width=140))

        root.addStretch()
        self.set_current(current_theme)

    # ------------------------------------------------------------------
    def _add_radio(self, layout, value: str, label: str) -> QRadioButton:
        rb = QRadioButton(label)
        rb.setProperty("themeName", value)
        self._group.addButton(rb)
        self._radios[value] = rb
        layout.addWidget(rb)
        return rb

    def _populate_theme_files(self):
        for path in discover_theme_files():
            value = theme.FILE_THEME_PREFIX + str(path)
            label = f"{theme_display_name(path)}  ({path.name})"
            self._add_radio(self._files_lay, value, label)
            self._file_radio_values.append(value)
        if not self._file_radio_values:
            none_lbl = QLabel("(none found)")
            none_lbl.setObjectName("mutedLabel")
            self._files_lay.addWidget(none_lbl)

    def refresh_theme_files(self):
        """Re-scan ui/themes/ (e.g. after saving from the editor)."""
        for value in self._file_radio_values:
            rb = self._radios.pop(value, None)
            if rb is not None:
                self._group.removeButton(rb)
                rb.setParent(None)
                rb.deleteLater()
        self._file_radio_values = []
        # remove a possible "(none found)" label
        for i in reversed(range(self._files_lay.count())):
            w = self._files_lay.itemAt(i).widget()
            if isinstance(w, QLabel) and w.text() == "(none found)":
                w.setParent(None)
                w.deleteLater()
        # re-insert just after the hint label (index 1..)
        insert_at = 1
        for path in discover_theme_files():
            value = theme.FILE_THEME_PREFIX + str(path)
            rb = QRadioButton(f"{theme_display_name(path)}  ({path.name})")
            rb.setProperty("themeName", value)
            self._group.addButton(rb)
            self._radios[value] = rb
            self._files_lay.insertWidget(insert_at, rb)
            insert_at += 1
            self._file_radio_values.append(value)

    # ------------------------------------------------------------------
    def _on_browse_custom(self):
        start_dir = str(themes_dir())
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Theme File", start_dir,
            f"Qt Theme Files (*{THEME_FILE_SUFFIX});;JSON Files (*.json)")
        if path:
            self._custom_path = path
            self._custom_label.setText(path)
            self._custom_radio.setChecked(True)

    def _on_open_editor(self):
        """Launch theme_editor.py as its own process (see module docstring)."""
        editor = Path(__file__).resolve().parents[2] / "theme_editor.py"
        if not editor.exists():
            self._custom_label.setText(f"theme_editor.py not found at {editor}")
            return
        subprocess.Popen([sys.executable, str(editor)],
                         cwd=str(editor.parent))

    def _on_apply(self):
        if self._custom_radio.isChecked():
            if self._custom_path:
                self.theme_apply_requested.emit(
                    theme.FILE_THEME_PREFIX + self._custom_path)
            return
        for value, rb in self._radios.items():
            if rb.isChecked():
                self.theme_apply_requested.emit(value)
                return

    # ------------------------------------------------------------------
    def set_current(self, theme_name: str):
        """Select the radio matching a name or 'file:<path>' selection."""
        rb = self._radios.get(theme_name)
        if rb:
            rb.setChecked(True)
            return
        if isinstance(theme_name, str) and \
           theme_name.startswith(theme.FILE_THEME_PREFIX):
            self._custom_path = theme_name[len(theme.FILE_THEME_PREFIX):]
            self._custom_label.setText(self._custom_path)
            self._custom_radio.setChecked(True)
            return
        fallback = self._radios.get("dark")
        if fallback:
            fallback.setChecked(True)
