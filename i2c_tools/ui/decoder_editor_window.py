"""
ui.decoder_editor_window
Main window for the standalone decoder editor. Reuses the shared DecodeEditor
and ThemePicker widgets and the same theme system as the main tool, so the two
apps look and behave consistently.
"""

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTabWidget, QMessageBox,
)
from PySide6.QtCore import Qt

from ui import theme
from ui.widgets.decode_editor import DecodeEditor
from ui.widgets.display_groups_editor import DisplayGroupsEditor
from ui.tabs import PreferencesTab, HelpTab, ExitTab
from ui.widgets import ConfirmingCloseMixin, StatusBarNotifier


class DecoderEditorWindow(ConfirmingCloseMixin, StatusBarNotifier, QMainWindow):
    """A focused, standalone window for editing decoder JSON files."""

    def __init__(self, open_path: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AD2 Decoder Editor")
        self.resize(720, 760)
        self._current_theme = theme.active_theme_name() or "default"
        self._dirty = False          # [XREF: exit-tab] unsaved-edit tracking
        self._build_ui()
        if open_path and os.path.isfile(open_path):
            self._editor.load_path(open_path)
        self._dirty = False          # a freshly loaded / empty schema is clean

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.setObjectName("mainTabs")
        root.addWidget(tabs)
        self.tabs = tabs
        # [XREF: tab-popout] same pop-out standard as the AppWindow apps
        from ui.widgets.tab_popout import TabPopoutController
        self.popout = TabPopoutController(tabs, self)

        # --- Editor tab ---
        self._editor = DecodeEditor(show_file_ops=True, layout="sections")
        self._editor.path_changed.connect(self._on_path_changed)
        self._editor.schema_changed.connect(self._on_schema_changed)  # [XREF: exit-tab]
        tabs.addTab(self._wrap_scroll(self._editor), "Decoder")

        # --- Display Groups tab (Registers-view layout, schema v4) ---
        # [XREF: registers-tab] edits the SAME DecodeSchema the Decoder tab
        # holds (schema_provider), so Save persists groups too.
        self._groups_tab = DisplayGroupsEditor(
            schema_provider=lambda: self._editor.schema)
        self._groups_tab.changed.connect(self._on_groups_changed)
        # schema replaced (New/Load) or rules edited -> rebuild the table
        # (group usage counts) and keep the rule form's dropdown current
        self._editor.schema_changed.connect(
            lambda *_: self._groups_tab.refresh())
        tabs.addTab(self._groups_tab, "Display Groups")

        # --- Preferences (theme) tab ---
        self._theme_picker = PreferencesTab(self._current_theme)
        self._theme_picker.theme_apply_requested.connect(self._on_theme_apply)
        tabs.addTab(self._theme_picker, "Preferences")

        # --- Help + Exit tabs ---
        self._help = HelpTab.for_app("decoder_editor")  # [XREF: help-tab]
        tabs.addTab(self._help, "Help")
        self._exit_panel = ExitTab("AD2 Decoder Editor")    # [XREF: exit-tab]
        self._exit_panel.exit_requested.connect(self.close)
        self._exit_panel.setProperty("poppable", False)     # [XREF: tab-popout]
        tabs.addTab(self._exit_panel, "Exit")

        self.statusBar().showMessage("Ready")

    def _wrap_scroll(self, widget) -> QWidget:
        # Editor is tall; wrap in a plain container so the tab can size it.
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)
        return holder

    def _on_theme_apply(self, name: str):
        self._current_theme = name
        theme.apply_theme(name)
        self.notify(f"Theme applied: {name}")

    def _on_schema_changed(self, *_):
        # [XREF: exit-tab] any edit marks the document dirty
        self._dirty = True

    def _on_groups_changed(self):
        # [XREF: registers-tab] group edits dirty the document and feed the
        # rule form's Group dropdown
        self._dirty = True
        self._editor.refresh_group_choices()

    def _on_path_changed(self, path: str):
        # load/save put us back in sync with a file
        self._dirty = False
        if path:
            self.setWindowTitle(f"AD2 Decoder Editor — {os.path.basename(path)}")
            self.notify(path)
        else:
            self.setWindowTitle("AD2 Decoder Editor")

    def closeEvent(self, event):  # noqa: N802
        super().closeEvent(event)          # confirm_close guard first
        if event.isAccepted():
            self.popout.dock_all()         # [XREF: tab-popout]

    # [XREF: exit-tab] ConfirmingCloseMixin: Save / Discard / Cancel flow
    # (richer than the default Yes/No guard, so confirm_close is overridden).
    def confirm_close(self) -> bool:
        if not self._dirty:
            return True
        resp = QMessageBox.question(
            self, "Unsaved Changes",
            "The decoder has unsaved changes.\n\nSave before exiting?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if resp == QMessageBox.Cancel:
            return False
        if resp == QMessageBox.Save:
            self._editor.save()          # emits path_changed -> clears _dirty
            if self._dirty:              # save-as dismissed or failed
                return False
        return True
