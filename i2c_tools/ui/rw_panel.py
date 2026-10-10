"""
rw_panel.py
Panel for I2C master read, write, write-read, and address scan.
"""

from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QTextEdit,
    QCheckBox, QRadioButton, QButtonGroup, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QColor

from ui import theme
from ui.common.hexutil import parse_hex_bytes, parse_addr_7bit, HexParseError


class RWPanel(QWidget):
    """
    Emits:
      write_requested(address7, data_bytes, add_pec)
      read_requested(address7, count, check_pec)
      write_read_requested(address7, write_bytes, read_count, check_pec)
      scan_requested()
    """

    write_requested = Signal(int, bytes, bool)
    read_requested = Signal(int, int, bool)
    write_read_requested = Signal(int, bytes, int, bool)
    scan_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._enabled = False

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ---- Address ----
        addr_box = QGroupBox("Target Address")
        addr_lay = QFormLayout(addr_box)
        addr_lay.setLabelAlignment(Qt.AlignRight)

        self._addr_edit = QLineEdit("0x50")
        self._addr_edit.setMaximumWidth(80)
        self._addr_edit.setPlaceholderText("0x00–0x77")
        addr_lay.addRow("7-bit Address (hex):", self._addr_edit)

        self._pec_chk = QCheckBox("SMBus PEC (CRC-8)")
        addr_lay.addRow(self._pec_chk)
        root.addWidget(addr_box)

        # ---- Write ----
        write_box = QGroupBox("Write")
        write_lay = QVBoxLayout(write_box)

        self._write_edit = QLineEdit()
        self._write_edit.setPlaceholderText("Hex bytes e.g. 01 FF A0  or  0x01,0xFF")
        self._write_edit.setFont(QFont("Courier New", 10))
        write_lay.addWidget(self._write_edit)

        self._write_btn = QPushButton("Write →")
        self._write_btn.setObjectName("btnWrite")
        self._write_btn.clicked.connect(self._on_write)
        self._write_btn.setEnabled(False)
        write_lay.addWidget(self._write_btn)
        root.addWidget(write_box)

        # ---- Read ----
        read_box = QGroupBox("Read")
        read_lay = QFormLayout(read_box)
        read_lay.setLabelAlignment(Qt.AlignRight)

        self._read_count = QSpinBox()
        self._read_count.setRange(1, 255)
        self._read_count.setValue(1)
        read_lay.addRow("Byte count:", self._read_count)

        self._read_btn = QPushButton("← Read")
        self._read_btn.setObjectName("btnRead")
        self._read_btn.clicked.connect(self._on_read)
        self._read_btn.setEnabled(False)
        read_lay.addRow(self._read_btn)
        root.addWidget(read_box)

        # ---- Write-Read (register read) ----
        wr_box = QGroupBox("Write then Read (Register Read)")
        wr_lay = QVBoxLayout(wr_box)

        wr_form = QFormLayout()
        wr_form.setLabelAlignment(Qt.AlignRight)

        self._wr_write_edit = QLineEdit()
        self._wr_write_edit.setPlaceholderText("Register / cmd bytes hex e.g. 01")
        self._wr_write_edit.setFont(QFont("Courier New", 10))
        wr_form.addRow("Write bytes:", self._wr_write_edit)

        self._wr_read_count = QSpinBox()
        self._wr_read_count.setRange(1, 255)
        self._wr_read_count.setValue(2)
        wr_form.addRow("Read count:", self._wr_read_count)
        wr_lay.addLayout(wr_form)

        self._wr_btn = QPushButton("Write then Read")
        self._wr_btn.setObjectName("btnWriteRead")
        self._wr_btn.clicked.connect(self._on_write_read)
        self._wr_btn.setEnabled(False)
        wr_lay.addWidget(self._wr_btn)
        root.addWidget(wr_box)

        # ---- Address Scan ----
        scan_box = QGroupBox("Address Scan (0x03–0x77)")
        scan_lay = QVBoxLayout(scan_box)

        self._scan_btn = QPushButton("Scan I2C Bus")
        self._scan_btn.setObjectName("btnScan")
        self._scan_btn.clicked.connect(self.scan_requested)
        self._scan_btn.setEnabled(False)
        scan_lay.addWidget(self._scan_btn)

        self._scan_table = QTableWidget(0, 2)
        self._scan_table.setHorizontalHeaderLabels(["Address", "Hex"])
        self._scan_table.horizontalHeader().setStretchLastSection(True)
        self._scan_table.setMaximumHeight(120)
        self._scan_table.setEditTriggers(QTableWidget.NoEditTriggers)
        scan_lay.addWidget(self._scan_table)
        root.addWidget(scan_box)

        # ---- Result display ----
        res_box = QGroupBox("Last Result")
        res_lay = QVBoxLayout(res_box)
        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setFont(QFont("Courier New", 10))
        self._result_text.setMaximumHeight(100)
        res_lay.addWidget(self._result_text)
        root.addWidget(res_box)

        root.addStretch()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _parse_address(self) -> int:
        try:
            return parse_addr_7bit(self._addr_edit.text())
        except HexParseError:
            return -1

    def _parse_hex_bytes(self, text: str) -> bytes:
        """Parse space/comma-separated hex bytes (shared helper)."""
        return parse_hex_bytes(text)

    def _on_write(self):
        addr = self._parse_address()
        if addr < 0 or addr > 0x77:
            self._show_result("❌ Invalid address", error=True)
            return
        try:
            data = self._parse_hex_bytes(self._write_edit.text())
        except Exception:
            self._show_result("❌ Invalid hex bytes in write field", error=True)
            return
        self.write_requested.emit(addr, data, self._pec_chk.isChecked())

    def _on_read(self):
        addr = self._parse_address()
        if addr < 0 or addr > 0x77:
            self._show_result("❌ Invalid address", error=True)
            return
        self.read_requested.emit(addr, self._read_count.value(), self._pec_chk.isChecked())

    def _on_write_read(self):
        addr = self._parse_address()
        if addr < 0 or addr > 0x77:
            self._show_result("❌ Invalid address", error=True)
            return
        try:
            data = self._parse_hex_bytes(self._wr_write_edit.text())
        except Exception:
            self._show_result("❌ Invalid hex bytes in write field", error=True)
            return
        self.write_read_requested.emit(addr, data, self._wr_read_count.value(), self._pec_chk.isChecked())

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._write_btn.setEnabled(enabled)
        self._read_btn.setEnabled(enabled)
        self._wr_btn.setEnabled(enabled)
        self._scan_btn.setEnabled(enabled)

    def show_result(self, txn, ok: bool, error: str = ""):
        """Display result of a master operation."""
        from core.i2c_controller import I2CDirection
        if not ok:
            self._show_result(f"❌ Error: {error}", error=True)
            return

        lines = [
            f"{'✓ OK':6}  {txn.timestamp_str}",
            f"Addr:  {txn.addr_str}",
            f"Dir:   {'READ' if txn.direction == I2CDirection.READ else 'WRITE'}",
            f"Data:  {txn.data_hex}",
        ]
        if txn.pec_valid is not None:
            lines.append(f"PEC:   {'✓ valid' if txn.pec_valid else '✗ INVALID'}")
        self._result_text.setStyleSheet("")
        self._result_text.setText("\n".join(lines))

    def _show_result(self, text: str, error: bool = False):
        self._result_text.setText(text)
        err_color = theme.get_color("status_error").name()
        self._result_text.setStyleSheet(f"color:{err_color};" if error else "")

    def populate_scan_results(self, addresses: list):
        self._scan_table.setRowCount(0)
        for addr in addresses:
            row = self._scan_table.rowCount()
            self._scan_table.insertRow(row)
            self._scan_table.setItem(row, 0, QTableWidgetItem(str(addr)))
            self._scan_table.setItem(row, 1, QTableWidgetItem(f"0x{addr:02X}"))
