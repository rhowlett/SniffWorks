"""
ui/widgets/serial_prefs_section.py  [v0.1]
[XREF: device-tab] A "Serial" section: baud-rate selection for the Nucleo
link. Since 2026-10-05 it sits on the ion Device tab (SerialDevicePanel), not
in Preferences, next to the connection it configures.
The firmware default is 115200 (HOST_UART_BAUD in sniffer_config.h); other
rates require a matching firmware rebuild, so the section says so.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLabel

from ui.widgets.section import Section
from ui.common import settings_store

BAUD_RATES = [115200, 230400, 460800, 921600, 57600, 38400, 19200, 9600]
DEFAULT_BAUD = 115200


class SerialPrefsSection(Section):
    """Emits baud_changed(int). current_baud() reads the selection."""

    baud_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Serial", parent)

        note = QLabel("Baud rate for the Nucleo sniffer link. Must match the "
                      "firmware's HOST_UART_BAUD (default 115200) — change "
                      "both together. Takes effect on the next Connect.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        self.add_widget(note)

        self._baud_combo = QComboBox()
        for rate in sorted(set(BAUD_RATES)):
            self._baud_combo.addItem(f"{rate}", rate)
        saved = settings_store.store().get_int(
            settings_store.KEY_BAUD, DEFAULT_BAUD)   # [XREF: settings]
        idx = self._baud_combo.findData(saved)
        if idx < 0:
            idx = self._baud_combo.findData(DEFAULT_BAUD)
        if idx >= 0:
            self._baud_combo.setCurrentIndex(idx)
        self._baud_combo.currentIndexChanged.connect(self._on_baud_changed)
        self.add_row(QLabel("Baud rate:"), self._baud_combo)

    def _on_baud_changed(self, _i: int):
        baud = self.current_baud()
        settings_store.store().set(settings_store.KEY_BAUD, baud)
        self.baud_changed.emit(baud)

    def current_baud(self) -> int:
        return int(self._baud_combo.currentData() or DEFAULT_BAUD)

    def set_baud(self, baud: int):
        idx = self._baud_combo.findData(int(baud))
        if idx >= 0:
            self._baud_combo.setCurrentIndex(idx)
