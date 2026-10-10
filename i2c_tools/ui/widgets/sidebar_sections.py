"""
ui/widgets/sidebar_sections.py  [v0.1]
[XREF: ui-sidebar] Reusable sidebar Sections shared by sniffer_ad2 and i2c_replay
so both apps present the same controls the same way (project extensibility rule).

  - CaptureStatsSection : configurable stat labels (Captured / Visible / Total / …)
  - TableDataSection    : Clear Log + Export CSV + Auto-scroll
  - LoadDecoderSection  : validated decoder-JSON picker           [XREF: file-picker]
  - LoadCaptureSection  : validated capture-CSV picker            [XREF: file-picker]
  - EditorSection       : Launch the standalone Decoder Editor    [XREF: edit-decoder]

Validators live here (they need core.decode_schema / the CSV column contract);
the widgets themselves stay thin.
"""
import csv
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QLabel, QPushButton, QCheckBox,
                               QListWidget, QListWidgetItem)
from PySide6.QtCore import Signal
from ui.widgets.buttons import icon_button, uniform_width

from ui.widgets.section import Section
from ui.widgets.file_picker import FilePickerRow
from ui import dialogs
from core.decode_schema import DecodeSchema
from core.log_model import COLUMNS


# --- validators -----------------------------------------------------------
def validate_decoder(path: str) -> Tuple[bool, str]:
    try:
        schema = DecodeSchema.load(path)
        return True, f"valid decoder ({len(schema)} rules)"
    except Exception as e:
        return False, str(e)


_REQUIRED_CAPTURE_COLS = {"Addr", "Dir", "Data (hex)"}


def validate_capture(path: str) -> Tuple[bool, str]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            cols = set(reader.fieldnames or [])
            missing = _REQUIRED_CAPTURE_COLS - cols
            if missing:
                return False, f"missing columns: {', '.join(sorted(missing))}"
            rows = sum(1 for _ in reader)
        return True, f"valid capture ({rows} rows)"
    except Exception as e:
        return False, str(e)


# --- sections --------------------------------------------------------------
class CaptureStatsSection(Section):
    """A Capture Stats block with configurable numeric fields."""

    def __init__(self, fields: List[Tuple[str, str]], title: str = "Capture Stats",
                 parent=None):
        super().__init__(title, parent)
        self._labels = {}
        for key, prefix in fields:
            lbl = QLabel(f"{prefix}: 0")
            self._labels[key] = (lbl, prefix)
            self.add_widget(lbl)

    def set_value(self, key: str, value) -> None:
        if key in self._labels:
            lbl, prefix = self._labels[key]
            lbl.setText(f"{prefix}: {value}")


class TableDataSection(Section):
    """Clear Log + Export CSV, Auto-scroll, and optional-column toggles
    (Int / ASCII interpretations of the data bytes). [XREF: int-ascii-cols]"""

    clear_requested = Signal()
    export_requested = Signal()
    auto_scroll_changed = Signal(bool)
    show_int_changed = Signal(bool)
    show_ascii_changed = Signal(bool)

    def __init__(self, title: str = "Table Data", parent=None):
        super().__init__(title, parent)
        clear_btn = icon_button("Clear Log", "clear")
        clear_btn.clicked.connect(self.clear_requested)
        export_btn = icon_button("Export CSV", "export")
        export_btn.clicked.connect(self.export_requested)
        uniform_width([clear_btn, export_btn], 110)   # [XREF: ui-buttons]
        self.add_row(clear_btn, export_btn)

        self._auto = QCheckBox("Auto-scroll")
        self._auto.setChecked(True)
        self._auto.stateChanged.connect(lambda s: self.auto_scroll_changed.emit(bool(s)))
        self.add_widget(self._auto)

        self._show_int = QCheckBox("Show Int column")
        self._show_int.stateChanged.connect(
            lambda s: self.show_int_changed.emit(bool(s)))
        self._show_ascii = QCheckBox("Show ASCII column")
        self._show_ascii.stateChanged.connect(
            lambda s: self.show_ascii_changed.emit(bool(s)))
        self.add_widget(self._show_int)
        self.add_widget(self._show_ascii)


class LoadDecoderSection(Section):
    """[XREF: decoder-manager] Multi-decoder picker: Add/Remove decoder JSON
    files; the loaded set decodes transactions from multiple client devices
    at once (rules are routed by I2C address).

    Signals:
        decoders_changed()      the loaded set changed; hosts pull
                                merged_schema() and re-apply to their model
        decoder_selected(str)   compatibility: emitted with each successfully
                                added path
    """

    decoders_changed = Signal()
    decoder_selected = Signal(str)

    def __init__(self, title: str = "Decoders", parent=None,
                 persist: bool = True):
        super().__init__(title, parent)
        from core.decoder_manager import DecoderSetManager
        self.manager = DecoderSetManager()
        self._persist = persist

        self._list = QListWidget()
        self._list.setMinimumHeight(64)
        self._list.setMaximumHeight(110)
        self.add_widget(self._list)

        add_btn = icon_button("Add…", "add")
        self._remove_btn = icon_button("Remove", "remove")
        uniform_width([add_btn, self._remove_btn], 90)   # [XREF: ui-buttons]
        self._up_btn = QPushButton("▲")      # move up in load order
        self._down_btn = QPushButton("▼")    # move down (later wins)
        for b in (self._up_btn, self._down_btn):
            b.setFixedWidth(34)
            b.setToolTip("Reorder: on rule collisions the LOWER decoder in "
                         "the list wins (later load order).")
        add_btn.clicked.connect(self._on_add)
        self._remove_btn.clicked.connect(self._on_remove)
        self._up_btn.clicked.connect(lambda: self._on_move(-1))
        self._down_btn.clicked.connect(lambda: self._on_move(+1))
        self._list.itemSelectionChanged.connect(self._update_buttons)
        self._update_buttons()
        self.add_row(add_btn, self._remove_btn, self._up_btn, self._down_btn)

        self._status = QLabel("No decoders loaded")
        self._status.setObjectName("mutedLabel")
        self._status.setWordWrap(True)
        self.add_widget(self._status)

        if persist:
            self._restore_persisted()

    # ------------------------------------------------------------------
    def _on_add(self):
        path = dialogs.open_json(self, "Add Decoder JSON")
        if path:
            self.add_decoder(path)

    def add_decoder(self, path: str) -> bool:
        """Load a decoder file into the set (public for hosts/tests)."""
        ok, msg = self.manager.add(path)
        if not ok:
            self._status.setText(f"Load failed: {msg}")
            self._set_status_kind("statusError")
            return False
        self._refresh()
        self.decoder_selected.emit(path)
        self.decoders_changed.emit()
        return True

    def _update_buttons(self):
        row = self._list.currentRow()
        has_sel = bool(self._list.selectedItems())
        self._remove_btn.setEnabled(has_sel)
        self._up_btn.setEnabled(has_sel and row > 0)
        self._down_btn.setEnabled(has_sel and 0 <= row < self._list.count() - 1)

    def _on_move(self, delta: int):
        items = self._list.selectedItems()
        if not items:
            return
        path = items[0].data(Qt.UserRole)
        if not self.manager.move(path, delta):
            return
        self._refresh()
        # keep the moved entry selected at its new position
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.UserRole) == path:
                self._list.setCurrentRow(i)
                break
        self.decoders_changed.emit()

    def _on_remove(self):
        items = self._list.selectedItems()
        if not items:
            return
        self.manager.remove(items[0].data(Qt.UserRole))
        self._refresh()
        self.decoders_changed.emit()

    def _refresh(self):
        self._list.clear()
        for entry in self.manager.entries():
            item = QListWidgetItem(entry.label())
            item.setToolTip(entry.path)
            item.setData(Qt.UserRole, entry.path)
            self._list.addItem(item)
        # refresh conflict count for the summary line
        self.manager.merged_schema()
        self._status.setText(self.manager.summary())
        self._set_status_kind("statusOk" if len(self.manager) else "mutedLabel")
        self._update_buttons()
        self._save_persisted()

    def _set_status_kind(self, object_name: str):
        self._status.setObjectName(object_name)
        style = self._status.style()
        if style:
            style.unpolish(self._status)
            style.polish(self._status)

    # ------------------------------------------------------------------
    def merged_schema(self, multiline_bits: bool = True):
        return self.manager.merged_schema(multiline_bits=multiline_bits)

    def selected_path(self):
        """Selected decoder's path (else the most recently added), e.g. for
        launching the Decoder Editor on it."""
        items = self._list.selectedItems()
        if items:
            return items[0].data(Qt.UserRole)
        paths = self.manager.paths()
        return paths[-1] if paths else None

    def path(self):
        """Compatibility: the single-decoder API returns selected_path()."""
        return self.selected_path()

    def is_valid(self) -> bool:
        return len(self.manager) > 0

    # ------------------------------------------------------------------
    # [XREF: settings] persist the loaded set across runs
    # ------------------------------------------------------------------
    def _save_persisted(self):
        if not self._persist:
            return
        from ui.common import settings_store
        settings_store.store().set(settings_store.KEY_DECODERS,
                                   "\n".join(self.manager.paths()))

    def _restore_persisted(self):
        from ui.common import settings_store
        from pathlib import Path as _P
        raw = settings_store.store().get_str(settings_store.KEY_DECODERS, "")
        restored = False
        for path in [p for p in raw.split("\n") if p]:
            if _P(path).is_file() and self.manager.add(path)[0]:
                restored = True
        if restored:
            self._refresh()
            self.decoders_changed.emit()


class LoadCaptureSection(Section):
    """Validated capture-CSV picker. Emits capture_selected(path)."""

    capture_selected = Signal(str)

    def __init__(self, title: str = "Load Capture File", parent=None):
        super().__init__(title, parent)
        self.picker = FilePickerRow(
            "Select CSV File",
            lambda p: dialogs.open_csv(p, "Select Capture CSV"),
            validate_capture,
        )
        self.picker.file_selected.connect(self.capture_selected)
        self.add_widget(self.picker)

    def path(self):
        return self.picker.path()

    def is_valid(self) -> bool:
        return self.picker.is_valid()


class EditorSection(Section):
    """Open Decoder Editor [Launch].

    Self-managed by default: the section owns the open-or-focus editor window
    itself (pass path_provider to auto-load the host's selected decoder JSON).
    Pass self_managed=False to only emit launch_requested() and wire your own
    handler. launch() is public so other triggers (e.g. the log panel's Edit
    Decoder button) can share the same editor window instance.
    """

    launch_requested = Signal()

    def __init__(self, title: str = "Editor", parent=None,
                 self_managed: bool = True, path_provider=None):
        super().__init__(title, parent)
        self._self_managed = self_managed
        self._path_provider = path_provider
        self._editor_win = None
        launch_btn = icon_button("Launch", "launch")
        uniform_width([launch_btn], 110)
        launch_btn.clicked.connect(self._on_launch)
        self.add_row(QLabel("Open Decoder Editor"), launch_btn)

    def _on_launch(self):
        self.launch_requested.emit()
        if self._self_managed:
            self.launch()

    def launch(self, open_path=None):
        """Open (or focus) the decoder editor, auto-loading a decoder path."""
        from ui.decoder_editor_launcher import open_or_focus_decoder_editor
        if open_path is None and self._path_provider is not None:
            open_path = self._path_provider()
        self._editor_win = open_or_focus_decoder_editor(
            self._editor_win, open_path=open_path)
        return self._editor_win

    def close_editor(self):
        """Close the child editor window if this section opened one."""
        if self._editor_win is not None:
            self._editor_win.close()
            self._editor_win = None


# COLUMNS is imported to anchor this module to the CSV contract; validate_capture
# checks a subset of these headers. Keep in sync if COLUMNS changes.
_CSV_HEADERS = [c for c, _ in COLUMNS]
