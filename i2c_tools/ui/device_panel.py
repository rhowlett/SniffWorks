"""
device_panel.py  [v0.3]
Panel for device connection, DIO pin assignment, I2C rate, and self-test.
The Device group is the shared ConnectionSection (harmonized with the ion
sniffer's Device tab, 2026-10-05).
"""

from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QCheckBox, QTextEdit, QSizePolicy, QFrame,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from ui import theme
from ui.widgets.connection_section import ConnectionSection
from ui.widgets.buttons import icon_button, button_row


class DevicePanel(QWidget):
    """
    Emits:
      connect_requested(device_index)
      disconnect_requested()
      apply_config_requested(scl, sda, alert, rate_hz, clock_stretch)
      clear_bus_requested()
      scan_requested()
      self_test_requested()
    """

    connect_requested = Signal(int)
    disconnect_requested = Signal()
    apply_config_requested = Signal(int, int, int, float, bool)
    clear_bus_requested = Signal()
    scan_requested = Signal()
    self_test_requested = Signal()
    refresh_requested = Signal()
    names_changed = Signal()            # [XREF: device-names]

    DIO_PINS = [str(i) for i in range(16)]  # DIO 0-15

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ---- Device selection (shared with the ion Device tab) ----
        self._conn = ConnectionSection("Device:")
        self._conn.refresh_requested.connect(self.refresh_requested)
        self._conn.connect_clicked.connect(self._on_connect)
        self._conn.disconnect_requested.connect(self.disconnect_requested)
        self._conn.names_changed.connect(self.names_changed)
        root.addWidget(self._conn)

        # ---- DIO Pin Assignment ----
        pin_box = QGroupBox("DIO Pin Assignment")
        pin_form = QFormLayout(pin_box)
        pin_form.setLabelAlignment(Qt.AlignRight)

        self._scl_combo = QComboBox()
        self._scl_combo.addItems(self.DIO_PINS)
        self._scl_combo.setCurrentIndex(0)
        pin_form.addRow("SCL pin (DIO #):", self._scl_combo)

        self._sda_combo = QComboBox()
        self._sda_combo.addItems(self.DIO_PINS)
        self._sda_combo.setCurrentIndex(1)
        pin_form.addRow("SDA pin (DIO #):", self._sda_combo)

        alert_row = QHBoxLayout()
        self._alert_enable = QCheckBox("Enable")
        self._alert_enable.stateChanged.connect(self._on_alert_toggle)
        self._alert_combo = QComboBox()
        self._alert_combo.addItems(self.DIO_PINS)
        self._alert_combo.setCurrentIndex(2)
        self._alert_combo.setEnabled(False)
        for c in (self._scl_combo, self._sda_combo, self._alert_combo):
            c.setFixedWidth(120)
        alert_row.addWidget(self._alert_enable)
        alert_row.addWidget(self._alert_combo)
        alert_row.addStretch(1)
        pin_form.addRow("ALERT pin (DIO #):", alert_row)

        note = QLabel(
            "⚠ With clock-stretch enabled, I2C uses DIO 0–9\n"
            "for internal ROM logic. Keep SDA/SCL in DIO 0–1\n"
            "and other DIOs ≥10, or disable clock-stretch."
        )
        note.setObjectName("noteLabel")
        note.setWordWrap(True)
        pin_form.addRow(note)
        root.addWidget(pin_box)

        # ---- I2C Rate ----
        rate_box = QGroupBox("I2C Rate / Options")
        rate_lay = QFormLayout(rate_box)
        rate_lay.setLabelAlignment(Qt.AlignRight)

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0, 5_000_000)
        self._rate_spin.setValue(100_000)
        self._rate_spin.setSingleStep(25_000)
        self._rate_spin.setDecimals(0)
        self._rate_spin.setSuffix(" Hz")
        self._rate_spin.setSpecialValueText("Auto")   # shown when value == 0

        # Presets: one left-aligned row of equal-width buttons. "Auto" maps
        # to 0 Hz (special value) meaning let the engine use its default rate.
        presets = [
            ("Auto", 0), ("100 kHz", 100_000), ("125 kHz", 125_000),
            ("250 kHz", 250_000), ("400 kHz", 400_000), ("1 MHz", 1_000_000),
        ]
        preset_btns = []
        for label, hz in presets:
            btn = icon_button(label)
            btn.clicked.connect(lambda _, h=hz: self._rate_spin.setValue(h))
            preset_btns.append(btn)
        rate_presets = button_row(*preset_btns, min_width=80)
        self._rate_spin.setMaximumWidth(220)

        rate_lay.addRow("Rate:", self._rate_spin)
        rate_lay.addRow("Presets:", rate_presets)

        self._stretch_chk = QCheckBox("Clock stretch (recommended)")
        self._stretch_chk.setChecked(True)
        rate_lay.addRow(self._stretch_chk)
        root.addWidget(rate_box)

        # ---- Apply / Actions: one compact row of equal-width buttons ----
        action_box = QGroupBox("Actions")
        action_lay = QVBoxLayout(action_box)

        self._apply_btn = icon_button("Apply Config", "apply", "btnApply")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply)
        self._clear_btn = icon_button("Clear Bus", "clear_bus")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self.clear_bus_requested)
        self._scan_btn = icon_button("Scan Addresses", "scan")
        self._scan_btn.setEnabled(False)
        self._scan_btn.clicked.connect(self.scan_requested)
        self._test_btn = icon_button("Self-Test", "self_test")
        self._test_btn.setEnabled(False)
        self._test_btn.clicked.connect(self.self_test_requested)
        action_lay.addLayout(button_row(self._apply_btn, self._clear_btn,
                                        self._scan_btn, self._test_btn))
        root.addWidget(action_box)

        # ---- Info / Log ----
        info_box = QGroupBox("Device Info / Log")
        info_lay = QVBoxLayout(info_box)
        self._info_text = QTextEdit()
        self._info_text.setReadOnly(True)
        self._info_text.setFont(QFont("Courier New", 9))
        self._info_text.setMaximumHeight(160)
        info_lay.addWidget(self._info_text)
        root.addWidget(info_box)

        root.addStretch()

    # ------------------------------------------------------------------
    # Slots / internal
    # ------------------------------------------------------------------
    def _on_connect(self, idx):
        if idx is None:
            idx = -1
        self.connect_requested.emit(idx)

    def _on_apply(self):
        scl = int(self._scl_combo.currentText())
        sda = int(self._sda_combo.currentText())
        alert = int(self._alert_combo.currentText()) if self._alert_enable.isChecked() else -1
        rate = self._rate_spin.value()
        stretch = self._stretch_chk.isChecked()
        self.apply_config_requested.emit(scl, sda, alert, rate, stretch)

    def _on_alert_toggle(self, state):
        self._alert_combo.setEnabled(bool(state))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def populate_devices(self, devices: list, preferred_serial: str = None):
        """devices: DeviceInfo list from the DWF enumeration. A device with a
        per-user name is listed as '<name> — [i] AD2  S/N:…'; preferred_serial
        (the last-used device) is pre-selected when present."""
        from core.device_names import DeviceNames, normalize_serial
        names = DeviceNames()
        items, select = [], None
        self._serials = {}
        for d in devices:
            serial = (d.serial or "").replace("SN:", "")
            label = f"[{d.index}] {d.name}  S/N:{serial}"
            if d.is_open:
                label += " (in use)"
            name = names.name_for(normalize_serial(d.serial)) if d.serial else ""
            items.append((f"{name} — {label}" if name else label, d.index))
            self._serials[d.index] = normalize_serial(d.serial)
            if preferred_serial and normalize_serial(d.serial) == normalize_serial(preferred_serial):
                select = d.index
        self._conn.set_items(items, select=select, empty_text="(no devices found)")

    def serial_for_index(self, index: int) -> str:
        return getattr(self, "_serials", {}).get(index, "")

    def set_connected(self, connected: bool, device_info: str = ""):
        self._conn.set_connected(connected)
        self._apply_btn.setEnabled(connected)
        self._clear_btn.setEnabled(connected)
        self._scan_btn.setEnabled(connected)
        self._test_btn.setEnabled(connected)

    def append_info(self, text: str):
        self._info_text.append(text)

    def clear_info(self):
        self._info_text.clear()

    # Getters for external access
    @property
    def scl_pin(self) -> int:
        return int(self._scl_combo.currentText())

    @property
    def sda_pin(self) -> int:
        return int(self._sda_combo.currentText())
