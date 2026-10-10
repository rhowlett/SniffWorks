"""
log_panel.py  [v1.2]
The main transaction log table + filter controls + export.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QTableView, QCheckBox, QSizePolicy, QFileDialog,
    QAbstractScrollArea, QHeaderView, QToolBar, QFrame,
    QSpinBox, QMessageBox,
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QFont, QAction

from core.log_model import TransactionLogModel, COLUMNS, COL_IDX
from ui import theme


class LogPanel(QWidget):
    """
    Full log table view with:
     - Filter bar (address, direction, search)
     - Address include/exclude lists
     - Auto-scroll toggle
     - Export CSV
     - Edit Decoder (opens the standalone Decoder Editor, via the host window)
     - Clear log
    """

    # [XREF: edit-decoder] emitted when the Edit Decoder button is clicked; the
    # host window (main or replay) opens/focuses the standalone Decoder Editor.
    edit_decoder_requested = Signal()

    # [XREF: replay-scrub] emitted with the SOURCE-model row index whenever
    # the selected row changes (-1 when the selection is cleared). Proxy
    # filtering is mapped back to source, so hosts can replay state "up to
    # this transaction" regardless of active filters.
    row_selected = Signal(int)

    def __init__(self, parent=None, show_toolbar: bool = True):
        super().__init__(parent)
        self._model = TransactionLogModel()
        self._auto_scroll = True
        self._show_toolbar = show_toolbar
        self._count_lbl = None       # only present when the toolbar is shown
        self._build_ui()
        self._connect_model()
        # Model-driven cell colors read the active palette; repaint on any
        # theme change so host windows don't have to wire this individually.
        theme.signals.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _selection: str):
        self._model.layoutChanged.emit()

    def _on_current_row_changed(self, current, _previous):
        # [XREF: replay-scrub]
        if not current.isValid():
            self.row_selected.emit(-1)
            return
        visible = self._model._visible
        row = current.row()
        self.row_selected.emit(visible[row] if 0 <= row < len(visible)
                               else -1)

    @property
    def model(self) -> TransactionLogModel:
        """The underlying transaction log model (for feeding/decoding)."""
        return self._model

    @property
    def table(self):
        """The underlying QTableView (for view-level configuration)."""
        return self._table

    def enable_multiline_rows(self, enabled: bool = True):
        """
        Allow cells to wrap and rows to grow to fit multi-line content (used by
        the replay app so multi-line bit-field decodes display fully). Row
        heights are computed on demand via resize_rows_to_contents() after a
        batch load rather than the always-on ResizeToContents mode, which is too
        expensive on large tables.
        """
        self._multiline = enabled
        self._table.setWordWrap(enabled)

    def resize_rows_to_contents(self):
        """Recompute row heights once (call after a batch load)."""
        if getattr(self, "_multiline", False):
            self._table.resizeRowsToContents()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ---- Toolbar row (optional; the sniffer/replay apps host these actions
        #      in their sidebar instead, via the public methods below) ----
        if self._show_toolbar:
            tb = QHBoxLayout()

            clear_btn = QPushButton("🗑 Clear Log")
            clear_btn.clicked.connect(self._on_clear)
            tb.addWidget(clear_btn)

            self._export_csv_btn = QPushButton("Export CSV")
            self._export_csv_btn.clicked.connect(self._on_export_csv)
            tb.addWidget(self._export_csv_btn)

            # [XREF: edit-decoder] the host window connects this to open the editor
            self._edit_decoder_btn = QPushButton("Edit Decoder")
            self._edit_decoder_btn.clicked.connect(self.edit_decoder_requested)
            tb.addWidget(self._edit_decoder_btn)

            tb.addStretch()

            self._auto_scroll_chk = QCheckBox("Auto-scroll")
            self._auto_scroll_chk.setChecked(True)
            self._auto_scroll_chk.stateChanged.connect(lambda s: setattr(self, "_auto_scroll", bool(s)))
            tb.addWidget(self._auto_scroll_chk)

            self._count_lbl = QLabel("0 rows")
            self._count_lbl.setObjectName("mutedLabel")
            tb.addWidget(self._count_lbl)
            root.addLayout(tb)

        # ---- Filter bar ----
        filt_box = QGroupBox("Filters")
        filt_lay = QHBoxLayout(filt_box)

        # Search
        filt_lay.addWidget(QLabel("Search:"))
        # [XREF: search-scope] where the search looks: the classic combined
        # haystack, or a single column (including live Decode text)
        self._search_col_combo = QComboBox()
        self._search_col_combo.addItem("All columns", None)
        for name, _attr in COLUMNS:
            self._search_col_combo.addItem(name, COL_IDX[name])
        self._search_col_combo.setToolTip(
            "Search scope. Either way, a hit reveals the whole exchange "
            "between the bounding NAKs (start/stop context preserved).")

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("hex data, address, ASCII…")
        self._search_edit.setMaximumWidth(180)
        # Filters commit on Apply/Reset (or Enter here), not on every keystroke:
        # live filtering thrashed the table (and, with multi-line decodes, left
        # rows sized for stale content until the next full resize).
        self._search_edit.returnPressed.connect(self._apply_filters)
        filt_lay.addWidget(self._search_edit)
        filt_lay.addWidget(QLabel("in:"))
        filt_lay.addWidget(self._search_col_combo)

        # Direction
        filt_lay.addWidget(QLabel("Dir:"))
        self._dir_combo = QComboBox()
        self._dir_combo.addItems(["All", "Read (R)", "Write (W)"])
        self._dir_combo.setMaximumWidth(100)
        filt_lay.addWidget(self._dir_combo)

        # Address filter
        filt_lay.addWidget(QLabel("Addr filter:"))
        self._addr_mode_combo = QComboBox()
        self._addr_mode_combo.addItems(["Capture All", "Include Only", "Exclude"])
        self._addr_mode_combo.setMaximumWidth(110)
        self._addr_mode_combo.currentIndexChanged.connect(self._on_addr_mode_changed)
        filt_lay.addWidget(self._addr_mode_combo)

        self._addr_list_edit = QLineEdit()
        self._addr_list_edit.setPlaceholderText("0x50 0x68  (space-separated)")
        self._addr_list_edit.setMaximumWidth(180)
        self._addr_list_edit.setEnabled(False)
        self._addr_list_edit.returnPressed.connect(self._apply_filters)
        filt_lay.addWidget(self._addr_list_edit)

        apply_filt_btn = QPushButton("Apply")
        apply_filt_btn.setMaximumWidth(55)
        apply_filt_btn.clicked.connect(self._apply_filters)
        filt_lay.addWidget(apply_filt_btn)

        reset_filt_btn = QPushButton("Reset")
        reset_filt_btn.setMaximumWidth(55)
        reset_filt_btn.clicked.connect(self._reset_filters)
        filt_lay.addWidget(reset_filt_btn)

        filt_lay.addStretch()

        # ---- Display options (view-only; shared by sniffer + replay) ----
        # [XREF: addr-crc-display]
        self._addr8_chk = QCheckBox("8-bit address")
        self._addr8_chk.setToolTip(
            "Show the 8-bit first byte with R/W folded into bit 0 "
            "(e.g. 7-bit 0x08 → write 0x10 / read 0x11)."
        )
        self._addr8_chk.toggled.connect(self._model.set_addr_8bit)
        filt_lay.addWidget(self._addr8_chk)

        self._crc_chk = QCheckBox("Show CRC")
        self._crc_chk.setChecked(True)
        self._crc_chk.setToolTip(
            "Show the CRC/PEC column and colour its value green (valid) / red (invalid)."
        )
        self._crc_chk.toggled.connect(self._on_show_crc_toggled)
        filt_lay.addWidget(self._crc_chk)

        root.addWidget(filt_box)

        # ---- Table view ----
        self._table = QTableView()
        self._table.setModel(self._model)
        # [XREF: replay-scrub] view row -> _entries index via the model's
        # visible-row mapping (filters collapse rows in the view).
        self._table.selectionModel().currentRowChanged.connect(
            self._on_current_row_changed)
        self._table.setFont(QFont("Courier New", 9))
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._table.setShowGrid(True)
        # Wrap long hex/decode content instead of eliding with "..."; row
        # heights follow the wrapped/multiline content. [XREF: row-wrap]
        self._table.setWordWrap(True)
        self._table.setTextElideMode(Qt.ElideNone)
        # Int / ASCII interpretation columns start hidden; the Table Data
        # section's checkboxes reveal them. [XREF: int-ascii-cols]
        self._table.setColumnHidden(COL_IDX["Int"], True)
        self._table.setColumnHidden(COL_IDX["ASCII"], True)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        # Set default column widths
        col_widths = [90, 45, 55, 35, 40, 180, 70, 90, 130, 40, 35, 35, 60, 75]
        for i, w in enumerate(col_widths):
            if i < self._model.columnCount():
                self._table.setColumnWidth(i, w)

        root.addWidget(self._table, 1)

    def _connect_model(self):
        self._model.row_added.connect(self._on_row_added)
        self._model.modelReset.connect(self._update_count)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_row_added(self, row: int):
        self._update_count()
        # [XREF: row-wrap] size the new row to its (possibly multiline) content
        self._table.resizeRowToContents(row)
        if self._auto_scroll:
            self._table.scrollToBottom()

    def _on_show_crc_toggled(self, checked: bool):
        # [XREF: addr-crc-display] colour via the model; hide the column when off
        self._model.set_show_crc(checked)
        self._table.setColumnHidden(COL_IDX["PEC"], not checked)

    def _update_count(self):
        if self._count_lbl is not None:
            self._count_lbl.setText(
                f"{self._model.visible_count} / {self._model.total_count} rows"
            )

    def _on_clear(self):
        self._model.clear()
        self._update_count()

    def _on_export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV files (*.csv)")
        if path:
            ok, err = self._model.export_csv(path)
            if not ok:
                QMessageBox.critical(self, "Export Error", err)
            else:
                QMessageBox.information(self, "Export OK", f"Saved {self._model.visible_count} rows to:\n{path}")

    # ------------------------------------------------------------------
    # Public actions — let a host (sidebar) drive the log without the toolbar.
    # [XREF: log-toolbar]
    # ------------------------------------------------------------------
    def clear_log(self):
        """Clear the log (same as the toolbar's Clear Log)."""
        self._on_clear()

    def export_csv_dialog(self):
        """Open the Export CSV dialog (same as the toolbar's Export CSV)."""
        self._on_export_csv()

    def set_auto_scroll(self, enabled: bool):
        """Enable/disable auto-scroll to the newest row."""
        self._auto_scroll = bool(enabled)
        if self._count_lbl is not None and hasattr(self, "_auto_scroll_chk"):
            self._auto_scroll_chk.setChecked(bool(enabled))

    def set_int_visible(self, visible: bool):
        self._table.setColumnHidden(COL_IDX["Int"], not visible)

    def set_ascii_visible(self, visible: bool):
        self._table.setColumnHidden(COL_IDX["ASCII"], not visible)

    def apply_schema(self, schema) -> None:
        """[XREF: decoder-manager] Apply a (possibly merged) DecodeSchema to
        the live model and re-decode everything already in the table."""
        self._model.set_schema(schema)
        self.resize_rows_to_contents()

    def load_decoder_file(self, path: str) -> "tuple[bool, str]":
        """Load a decoder JSON into the live model and re-decode. Returns (ok, msg)."""
        from core.decode_schema import DecodeSchema
        try:
            schema = DecodeSchema.load(path)
        except Exception as e:
            return False, str(e)
        schema.multiline_bits = True   # bit fields one per line in the row
        self._model.set_schema(schema)
        self.resize_rows_to_contents()
        return True, f"{len(schema)} rules"

    def _on_addr_mode_changed(self, idx: int):
        self._addr_list_edit.setEnabled(idx != 0)  # disabled for "Capture All"

    def _parse_addr_list(self) -> set:
        text = self._addr_list_edit.text()
        addrs = set()
        for tok in text.replace(",", " ").split():
            try:
                addrs.add(int(tok, 16))
            except ValueError:
                pass
        return addrs

    def _apply_filters(self):
        m = self._model

        # Direction
        dir_idx = self._dir_combo.currentIndex()
        m.filter_direction = {0: None, 1: "R", 2: "W"}.get(dir_idx)

        # Search
        m.filter_search = self._search_edit.text().strip()
        m.filter_search_col = self._search_col_combo.currentData()

        # Address mode
        mode = self._addr_mode_combo.currentIndex()
        addrs = self._parse_addr_list()
        if mode == 0:   # Capture All
            m.capture_all = True
            m.include_addresses = set()
            m.exclude_addresses = set()
        elif mode == 1:  # Include Only
            m.capture_all = False
            m.include_addresses = addrs
            m.exclude_addresses = set()
        else:           # Exclude
            m.capture_all = True
            m.include_addresses = set()
            m.exclude_addresses = addrs

        m.reapply_filter()
        self._update_count()
        # Filtering resets the model; with multi-line decodes, recompute row
        # heights now so the Decode cells aren't clipped to the default height.
        self.resize_rows_to_contents()

    def _reset_filters(self):
        self._search_edit.clear()
        self._search_col_combo.setCurrentIndex(0)   # All columns
        self._dir_combo.setCurrentIndex(0)
        self._addr_mode_combo.setCurrentIndex(0)
        self._addr_list_edit.clear()
        self._apply_filters()
