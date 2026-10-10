"""
ui/replay_window.py  [v1.1]
ui.replay_window
Standalone CSV replay window. Loads a sniffer capture CSV and a decoder JSON, then
replays the captured transactions into the SAME transaction-log table used by the
sniffer app, with the Decode column populated by the decoder.

Layout mirrors sniffer_ad2 (P6.6): top tabs on the shared AppWindow frame, and a
Replay tab laid out as [sidebar of sections | log table]. Loading a valid capture
(or selecting a decoder) replays automatically — there is no separate Replay
button. [XREF: app-shell]
"""

import os

from ui import theme
from ui.log_panel import LogPanel
from ui.widgets import AppWindow, Sidebar, make_tab_body
from ui.widgets.registers_tabs_host import RegisterTabsHost
from ui.tabs import PreferencesTab, HelpTab, ExitTab
from ui.widgets.sidebar_sections import (
    CaptureStatsSection, TableDataSection, LoadCaptureSection,
    LoadDecoderSection, EditorSection,
)
from ui import dialogs
from ui.common import load_transactions
from core.decode_schema import DecodeSchema


class ReplayWindow(RegisterTabsHost, AppWindow):  # AppWindow includes ConfirmingCloseMixin
    def __init__(self, csv_path: str = None, decoder_path: str = None, parent=None):
        super().__init__("AD2 I2C Replay", parent)
        self.resize(1100, 720)
        self._current_theme = theme.active_theme_name() or "default"
        self._csv_path = None
        self._decoder_path = None
        self._build_ui()

        if decoder_path and os.path.isfile(decoder_path):
            self._load_decoder_section.picker.set_path(decoder_path)
        if csv_path and os.path.isfile(csv_path):
            self._load_capture_section.picker.set_path(csv_path)

    # ------------------------------------------------------------------
    def _build_ui(self):
        # --- Replay tab = [sidebar | log table] ---
        self._log = LogPanel(show_toolbar=False)
        self._log.enable_multiline_rows(True)

        self._stats = CaptureStatsSection(
            fields=[("rows", "Rows"), ("visible", "Visible (filtered)"),
                    ("total", "Total in log"), ("decoded", "Decoded")],
        )
        self._load_capture_section = LoadCaptureSection()   # [XREF: file-picker]
        self._load_decoder_section = LoadDecoderSection()   # [XREF: file-picker]
        self._editor_section = EditorSection(               # [XREF: edit-decoder]
            path_provider=lambda: self._load_decoder_section.selected_path())
        self._table_data = TableDataSection()               # [XREF: table-data]

        sidebar = Sidebar(max_width=380)
        sidebar.add_section(self._stats)
        sidebar.add_section(self._load_capture_section)
        sidebar.add_section(self._load_decoder_section)
        sidebar.add_section(self._editor_section)
        sidebar.add_section(self._table_data)
        sidebar.add_stretch()

        self.add_tab(make_tab_body(sidebar, self._log), "Replay")

        # --- Preferences tab ---
        self._theme_picker = PreferencesTab(self._current_theme)
        self.add_tab(self._theme_picker, "Preferences")

        # --- Help + Exit tabs ---
        self._help = HelpTab.for_app("i2c_replay")      # [XREF: help-tab]
        self.add_tab(self._help, "Help")
        self._exit_panel = ExitTab("AD2 I2C Replay")    # [XREF: exit-tab]
        self.add_tab(self._exit_panel, "Exit")

        # wiring
        self._load_capture_section.capture_selected.connect(self._on_capture_selected)
        # [XREF: decoder-manager] merged schema decodes all loaded devices
        self._load_decoder_section.decoders_changed.connect(self._on_decoders_changed)
        if self._load_decoder_section.is_valid():   # persisted set restored
            self._on_decoders_changed()
        # [XREF: replay-scrub] selecting a log row replays register state
        # up to that transaction in the device tabs; clearing the selection
        # returns to full-capture state.
        self._log.row_selected.connect(self._on_log_row_selected)
        self._table_data.clear_requested.connect(self._log.clear_log)
        self._table_data.export_requested.connect(self._log.export_csv_dialog)
        self._table_data.auto_scroll_changed.connect(self._log.set_auto_scroll)
        self._table_data.show_int_changed.connect(self._log.set_int_visible)
        self._table_data.show_ascii_changed.connect(self._log.set_ascii_visible)
        self._theme_picker.theme_apply_requested.connect(self._on_theme_apply)
        self._exit_panel.exit_requested.connect(self.close)   # [XREF: exit-tab]

    # ------------------------------------------------------------------
    def _on_theme_apply(self, name: str):
        self._current_theme = name
        theme.apply_theme(name)
        self.notify(f"Theme applied: {name}")

    # [XREF: exit-tab] ConfirmingCloseMixin: nothing unsaved (file-derived);
    # close the child decoder-editor window if the Editor section opened one.
    def on_close(self):
        self._editor_section.close_editor()

    # ------------------------------------------------------------------
    def _on_log_row_selected(self, entry_index: int):
        # [XREF: replay-scrub]
        self._replay_registers_to(self._log.model._entries, entry_index)

    def _on_capture_selected(self, path: str):
        if not self._load_capture_section.is_valid():
            self.notify("Capture file did not validate.")
            return
        self._csv_path = path
        self._run_replay()

    def _on_decoders_changed(self):
        # [XREF: decoder-manager] merged schema (replay renders bit fields
        # one per line, so multiline_bits is set on the merged schema)
        schema = self._load_decoder_section.merged_schema(multiline_bits=True)
        self._decoder_path = self._load_decoder_section.selected_path()
        # [XREF: registers-tab] tabs first so the cache sees the re-decode
        # of every loaded capture row (that replay IS the data source here)
        self._rebuild_register_tabs(schema, self._load_decoder_section.manager)
        self._log.model.set_schema(schema)   # re-decodes rows already loaded
        self._log.resize_rows_to_contents()
        self._update_stats()
        self.notify(self._load_decoder_section.manager.summary())

    def _run_replay(self):
        """(Re)populate the table from the loaded capture. Called automatically on
        capture load; the active decoder (if any) decodes as rows are added."""
        if not self._csv_path:
            return
        try:
            txns = load_transactions(self._csv_path)
        except Exception as e:
            dialogs.error(self, "Replay Error", str(e))
            return
        self._log.model.clear()
        for t in txns:
            self._log.model.add_transaction(t)
        self._log.resize_rows_to_contents()
        self._update_stats(rows=len(txns))
        self.notify(
            f"Replayed {len(txns)} transactions "
            f"({self._log.model.decoded_count()} decoded)")

    def _update_stats(self, rows: int = None):
        m = self._log.model
        if rows is not None:
            self._stats.set_value("rows", rows)
        self._stats.set_value("visible", m.visible_count)
        self._stats.set_value("total", m.total_count)
        self._stats.set_value("decoded", m.decoded_count())
