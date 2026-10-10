"""
ui.dialogs.capture_results
A dialog that displays the result of decoding a capture file against the current
schema: each row's #, Dir, applied Register, raw data, and decoded text. Useful
for verifying a decoder against real sniffed data.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QCheckBox,
)
from PySide6.QtCore import Qt
from typing import List

from ui.common.capture import CaptureRow


class CaptureResultsDialog(QDialog):
    HEADERS = ["#", "Dir", "Register", "Data (hex)", "Decoded"]

    def __init__(self, rows: List[CaptureRow], source_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture Decode Results")
        self.resize(720, 560)
        self._rows = rows
        self._build_ui(source_name)
        self._populate(only_decoded=True)

    def _build_ui(self, source_name: str):
        root = QVBoxLayout(self)

        total = len(self._rows)
        decoded = sum(1 for r in self._rows if r.decoded)
        info = QLabel(
            f"{source_name}  —  {total} rows, {decoded} decoded "
            f"({total - decoded} without a matching rule)."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self._only_decoded = QCheckBox("Show only rows with a decode result")
        self._only_decoded.setChecked(True)
        self._only_decoded.toggled.connect(self._populate)
        root.addWidget(self._only_decoded)

        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self._table)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        root.addLayout(btns)

    def _populate(self, only_decoded: bool = True):
        only = self._only_decoded.isChecked()
        self._table.setRowCount(0)
        for r in self._rows:
            if only and not r.decoded:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            reg = "" if r.register is None else f"0x{r.register:02X}"
            self._table.setItem(row, 0, QTableWidgetItem(r.seq))
            self._table.setItem(row, 1, QTableWidgetItem(r.direction))
            self._table.setItem(row, 2, QTableWidgetItem(reg))
            self._table.setItem(row, 3, QTableWidgetItem(r.raw_data_hex))
            self._table.setItem(row, 4, QTableWidgetItem(r.decoded))
