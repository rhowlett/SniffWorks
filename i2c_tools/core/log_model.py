"""
log_model.py  [v0.1]
QAbstractTableModel for I2C transaction log.
Supports filter by address, direction, search string, capture-all mode.
Supports CSV and JSON export.
"""

import csv
import json
import datetime
from typing import List, Optional, Set, Tuple
from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, Qt, Signal, QSortFilterProxyModel
)
from PySide6.QtGui import QColor, QFont

from core.i2c_controller import I2CTransaction, I2CDirection
from core.decode_schema import StreamDecoder


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------
# [XREF: csv-format] Capture CSV v2 — the column set and its
# serialization are normative; see documents/CSV_FORMAT.md and
# tools/validate_capture_csv.py before changing anything here.
# v2 = v1 + trailing "SCL (Hz)"; new columns only ever go at the end.
COLUMNS = [
    ("Time",        "timestamp_str"),
    ("#",           "seq"),
    ("Addr",        "addr_str"),
    ("Dir",         "dir_str"),
    ("Len",         "length"),
    ("Data (hex)",  "data_hex"),
    ("Int",         "data_int"),
    ("ASCII",       "data_ascii"),
    ("Decode",      "decode"),
    ("NAK",         "nak_str"),
    ("Start",       "start_str"),
    ("Stop",        "stop_str"),
    ("PEC",         "pec_str"),
    ("SCL (Hz)",    "scl_hz_str"),
]

COL_IDX = {name: i for i, (name, _) in enumerate(COLUMNS)}

# Table header text where it differs from the CSV column name (the table
# shows SCL in kHz; the file stores integer Hz).
_DISPLAY_HEADER = {"SCL (Hz)": "SCL"}


def format_scl_hz(hz) -> str:
    """Table text for a measured SCL: '100.0 kHz', '' when unknown."""
    if not hz:
        return ""
    return f"{hz / 1000.0:.1f} kHz"


class LogEntry:
    """Wraps a transaction with a sequence number and computed display fields."""

    def __init__(self, seq: int, txn: I2CTransaction):
        self.seq = seq
        self.txn = txn

    # Display helpers
    @property
    def data_ascii(self) -> str:
        return "".join(chr(b) if 32 <= b < 127 else "." for b in self.txn.data)

    @property
    def data_int(self) -> str:
        """Big-endian unsigned integer value of the data bytes."""
        if not self.txn.data:
            return ""
        return str(int.from_bytes(self.txn.data, byteorder="big", signed=False))

    @property
    def nak_str(self) -> str:
        return "NAK" if self.txn.nak else ""

    @property
    def start_str(self) -> str:
        return {1: "S", 2: "Sr"}.get(self.txn.start, "")

    @property
    def stop_str(self) -> str:
        return "P" if self.txn.stop else ""

    def decode(self, schema) -> str:
        """
        Return the cached stream-decoded text for this entry. Stream decoding is
        sequence-dependent (a read inherits the register from a preceding pointer
        write), so the model computes and caches it when the entry is added or
        when the schema changes; this just returns the cached value.
        """
        return getattr(self, "_decode_text", "")

    def get_col(self, col: int, schema=None):
        name, attr = COLUMNS[col]
        if attr == "seq":
            return str(self.seq)
        if attr == "data_ascii":
            return self.data_ascii
        if attr == "data_int":
            return self.data_int
        if attr == "decode":
            return self.decode(schema)
        if attr == "nak_str":
            return self.nak_str
        if attr == "start_str":
            return self.start_str
        if attr == "stop_str":
            return self.stop_str
        return str(getattr(self.txn, attr, ""))


# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------
class TransactionLogModel(QAbstractTableModel):

    row_added = Signal(int)   # emitted with row index when a row is appended

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[LogEntry] = []
        self._seq = 0
        self._schema = None   # active DecodeSchema (or None)
        self._stream = None    # StreamDecoder over the active schema

        # --- Display options (view-only; do NOT affect CSV export) ---
        # [XREF: addr-crc-display]
        self._addr_8bit = False   # False = 7-bit Addr + separate Dir; True = 8-bit byte (R/W folded in)
        self._show_crc = True     # colour the PEC/CRC value green/red; the view also hides the column when off

        # --- Filter state ---
        self.filter_addresses: Set[int] = set()   # empty = show all
        self.filter_direction: Optional[str] = None  # None, "R", "W"
        self.filter_search: str = ""
        # Search scope: None = the classic time/addr/hex/ASCII haystack;
        # a column index = match only that column's displayed text
        # (including the live Decode text). [XREF: search-scope]
        self.filter_search_col: "int | None" = None
        self.capture_all: bool = True
        self.include_addresses: Set[int] = set()   # if non-empty, ONLY these
        self.exclude_addresses: Set[int] = set()   # always hidden

        self._visible: List[int] = []  # indices into _entries that pass filter

    def set_schema(self, schema):
        """Set the active DecodeSchema and re-decode all entries (in order)."""
        self._schema = schema
        self._redecode_all()
        if self._visible:
            top = self.index(0, COL_IDX["Decode"])
            bot = self.index(len(self._visible) - 1, COL_IDX["Decode"])
            self.dataChanged.emit(top, bot)

    # --- Display options (view-only) ---------------------------------- [XREF: addr-crc-display]
    def set_addr_8bit(self, enabled: bool):
        """Show addresses as the 8-bit first byte (R/W folded into bit 0) instead
        of the 7-bit address + separate direction. Display only; export unchanged."""
        enabled = bool(enabled)
        if enabled != self._addr_8bit:
            self._addr_8bit = enabled
            self._emit_cols_changed([COL_IDX["Addr"], COL_IDX["Dir"]])

    def set_show_crc(self, enabled: bool):
        """Colour the CRC/PEC cell (green valid / red invalid). Display only."""
        enabled = bool(enabled)
        if enabled != self._show_crc:
            self._show_crc = enabled
            self._emit_cols_changed([COL_IDX["PEC"]])

    def _emit_cols_changed(self, cols):
        if not self._visible:
            return
        last = len(self._visible) - 1
        for c in cols:
            self.dataChanged.emit(
                self.index(0, c), self.index(last, c),
                [Qt.DisplayRole, Qt.ForegroundRole, Qt.ToolTipRole],
            )

    def _decode_entry(self, entry):
        """Stream-decode one entry, updating the StreamDecoder's register state."""
        if self._stream is None:
            entry._decode_text = ""
            return
        txn = entry.txn
        res = self._stream.feed(
            txn.address, txn.dir_str, txn.data,
            had_stop=bool(txn.stop),
            repeated_start=(txn.start == 2),
        )
        entry._decode_text = res.text

    def _redecode_all(self):
        """Rebuild the StreamDecoder and recompute every entry's decode text."""
        self._stream = StreamDecoder(self._schema) if self._schema is not None else None
        for entry in self._entries:
            self._decode_entry(entry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_transaction(self, txn: I2CTransaction):
        """Append a transaction to the log (thread-safe call from main thread)."""
        self._seq += 1
        entry = LogEntry(self._seq, txn)
        raw_idx = len(self._entries)
        self._entries.append(entry)
        # Decode in arrival order so reads inherit the register from prior writes.
        self._decode_entry(entry)

        # A search needs whole-capture context (matches expand across a NAK-bounded
        # frame to pull in the paired read/write), so recompute visibility rather
        # than deciding this one row in isolation. Without a search, the per-row
        # address/direction filter is exact, so keep the fast incremental insert.
        if self.filter_search:
            self.beginResetModel()
            self._visible = self._compute_visible()
            self.endResetModel()
            if self._visible and self._visible[-1] == raw_idx:
                self.row_added.emit(len(self._visible) - 1)
            return

        if self._passes_filter(entry):
            vis_row = len(self._visible)
            self.beginInsertRows(QModelIndex(), vis_row, vis_row)
            self._visible.append(raw_idx)
            self.endInsertRows()
            self.row_added.emit(vis_row)

    def clear(self):
        self.beginResetModel()
        self._entries.clear()
        self._visible.clear()
        self._seq = 0
        if self._schema is not None:
            self._stream = StreamDecoder(self._schema)
        self.endResetModel()

    def reapply_filter(self):
        self.beginResetModel()
        self._visible = self._compute_visible()
        self.endResetModel()

    def entry_at_row(self, row: int) -> Optional[LogEntry]:
        if 0 <= row < len(self._visible):
            return self._entries[self._visible[row]]
        return None

    # ------------------------------------------------------------------
    # Filter logic
    # ------------------------------------------------------------------
    def _addr_ok(self, entry: LogEntry) -> bool:
        """Address include/exclude test (exclude always wins)."""
        addr = entry.txn.address
        if addr in self.exclude_addresses:
            return False
        if self.include_addresses and addr not in self.include_addresses:
            return False
        return True

    def _dir_ok(self, entry: LogEntry) -> bool:
        d = entry.txn.direction
        if self.filter_direction == "R" and d != I2CDirection.READ:
            return False
        if self.filter_direction == "W" and d != I2CDirection.WRITE:
            return False
        return True

    def _search_hit(self, entry: LogEntry) -> bool:
        """True if the search needle appears in the search scope: the classic
        time/addr/hex/ASCII haystack (scope None) or one column's displayed
        text. The scope only changes what is MATCHED - frame-aware visibility
        (everything between the bounding NAKs of a matched frame is shown)
        is computed the same way in _compute_visible either way."""
        needle = self.filter_search.lower()
        if self.filter_search_col is not None:
            return needle in str(
                entry.get_col(self.filter_search_col, self._schema)).lower()
        haystack = " ".join([
            entry.txn.timestamp_str,
            entry.txn.addr_str,
            entry.txn.data_hex,
            entry.data_ascii,
        ]).lower()
        return needle in haystack

    def _passes_filter(self, entry: LogEntry) -> bool:
        """Per-row test used by the fast incremental insert when NO search is
        active. (With a search active, visibility is frame-aware and computed by
        _compute_visible.)"""
        if not (self._addr_ok(entry) and self._dir_ok(entry)):
            return False
        if self.filter_search and not self._search_hit(entry):
            return False
        return True

    def _compute_visible(self) -> List[int]:
        """
        Compute the visible raw-index list under the current filters.

        Without a search term this is a plain per-row test (address + direction).

        With a search term, matching is *frame-aware*: transactions are grouped
        into frames delimited by NAKs (a captured subcommand is a write of the
        register/pointer followed by the read of its response, and the read ends
        with the controller's NAK). A frame is "seeded" when it contains a row
        that passes the address AND direction filters AND matches the search;
        every row of a seeded frame is then shown (still subject to the address
        filter), regardless of direction. So searching the data of a WRITE
        reveals the paired READ in the same frame, and vice versa — the whole
        exchange from the last NAK to the next NAK.
        """
        entries = self._entries
        if not self.filter_search:
            return [i for i, e in enumerate(entries)
                    if self._addr_ok(e) and self._dir_ok(e)]

        # Assign each row to a frame; a NAK terminates the current frame.
        frame_of = [0] * len(entries)
        fid = 0
        for i, e in enumerate(entries):
            frame_of[i] = fid
            if e.txn.nak:
                fid += 1

        # Seed frames from rows that pass address + direction + search.
        seeded = set()
        for i, e in enumerate(entries):
            if self._addr_ok(e) and self._dir_ok(e) and self._search_hit(e):
                seeded.add(frame_of[i])

        # Show every row of a seeded frame that still passes the address filter.
        return [i for i, e in enumerate(entries)
                if frame_of[i] in seeded and self._addr_ok(e)]

    # ------------------------------------------------------------------
    # QAbstractTableModel interface
    # ------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._visible)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            name = COLUMNS[section][0]
            return _DISPLAY_HEADER.get(name, name)
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        entry = self.entry_at_row(index.row())
        if entry is None:
            return None

        if role == Qt.DisplayRole:
            col = index.column()
            # [XREF: addr-crc-display] 8-bit address view folds R/W into the byte
            if self._addr_8bit and col == COL_IDX["Addr"]:
                rw = 1 if entry.txn.direction == I2CDirection.READ else 0
                return f"0x{((entry.txn.address << 1) | rw):02X}"
            if self._addr_8bit and col == COL_IDX["Dir"]:
                return "R (bit0)" if entry.txn.direction == I2CDirection.READ else "W (bit0)"
            if col == COL_IDX["PEC"] and not self._show_crc:
                return ""
            if col == COL_IDX["SCL (Hz)"]:
                return format_scl_hz(entry.txn.scl_hz)
            return entry.get_col(col, self._schema)

        if role == Qt.ForegroundRole:
            from ui import theme
            # [XREF: addr-crc-display] the CRC/PEC value is green when valid, red
            # when invalid; this overrides the row's direction colour for that cell.
            if (self._show_crc and index.column() == COL_IDX["PEC"]
                    and entry.txn.pec_valid is not None):
                if entry.txn.pec_valid:
                    return theme.get_color("status_active", "#2ECC71")
                return theme.get_color("status_error", "#E74C3C")
            if entry.txn.nak:
                return theme.get_color("data_nak", "#E74C3C")
            if entry.txn.direction == I2CDirection.READ:
                return theme.get_color("data_read", "#27AE60")
            return theme.get_color("data_write", "#2980B9")

        if role == Qt.BackgroundRole:
            from ui import theme
            if entry.txn.pec_valid is False:
                return theme.get_color("data_pec_fail_bg", "#4A0000")
            return None

        if role == Qt.FontRole:
            col_name = COLUMNS[index.column()][0]
            if col_name in ("Data (hex)", "ASCII", "Int", "Decode"):
                f = QFont("Courier New", 9)
                return f

        if role == Qt.ToolTipRole:
            txn = entry.txn
            rw = 1 if txn.direction == I2CDirection.READ else 0
            addr8 = (txn.address << 1) | rw
            lines = [
                f"Seq: {entry.seq}",
                f"Time: {txn.timestamp_str}",
                f"Address: {txn.addr_str} (7-bit) / 0x{addr8:02X} (8-bit, R/W in bit 0)",
                f"Direction: {'READ' if txn.direction == I2CDirection.READ else 'WRITE'}",
                f"Data ({txn.length} bytes): {txn.data_hex}",
                f"NAK: {txn.nak}",
            ]
            if txn.pec_valid is not None:
                lines.append(f"CRC/PEC: {'VALID' if txn.pec_valid else 'INVALID'}")
            if txn.scl_hz:
                lines.append(f"SCL: {txn.scl_hz} Hz (measured by the probe)")
            return "\n".join(lines)

        return None

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_csv(self, filepath: str) -> Tuple[bool, str]:
        """Export visible rows to CSV. Returns (ok, error)."""
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([col for col, _ in COLUMNS])
                for raw_idx in self._visible:
                    entry = self._entries[raw_idx]
                    writer.writerow([entry.get_col(c, self._schema) for c in range(len(COLUMNS))])
            return True, ""
        except Exception as e:
            return False, str(e)

    def export_json(self, filepath: str) -> Tuple[bool, str]:
        """Export visible rows to JSON. Returns (ok, error)."""
        try:
            rows = []
            for raw_idx in self._visible:
                entry = self._entries[raw_idx]
                txn = entry.txn
                rows.append({
                    "seq": entry.seq,
                    "timestamp": txn.timestamp_str,
                    "address_hex": txn.addr_str,
                    "address_dec": txn.address,
                    "direction": txn.dir_str,
                    "data_hex": txn.data_hex,
                    "data_int": entry.data_int,
                    "data_bytes": list(txn.data),
                    "data_ascii": entry.data_ascii,
                    "decode": entry.decode(self._schema),
                    "length": txn.length,
                    "nak": txn.nak,
                    "start": txn.start,
                    "stop": txn.stop,
                    "pec_valid": txn.pec_valid,
                    "scl_hz": txn.scl_hz,
                })
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({"exported": datetime.datetime.now().isoformat(), "transactions": rows}, f, indent=2)
            return True, ""
        except Exception as e:
            return False, str(e)

    @property
    def total_count(self) -> int:
        return len(self._entries)

    @property
    def visible_count(self) -> int:
        return len(self._visible)

    def decoded_count(self) -> int:
        """Number of entries that produced a non-empty decode under the current
        schema. Uses the cached stream-decode text, so it reflects the same
        result shown in the Decode column."""
        return sum(1 for e in self._entries if getattr(e, "_decode_text", ""))


