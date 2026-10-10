"""
ui/widgets/connection_section.py  [v0.3]
[XREF: device-tab] The "Device" group that opens every sniffer's Device tab,
shared by the AD2 DevicePanel and the ion SerialDevicePanel so both tabs look
and behave the same (owner request 2026-10-05: harmonize sniffer_ion and
sniffer_ad2):

    Device ─────────────────────────────────────────────────
    <label> [ selector ................................... ]
    [↻ Refresh] [✓ Connect] [✗ Disconnect] [Name devices…]  (compact, icons)
    ● Not connected

The selector holds (text, data) items; the host decides what data means (AD2
device index, serial port name). Status uses the theme's status colors.
"Name devices…" opens the shared USB discovery/naming dialog
(ui/dialogs/device_names_dialog.py) and then emits names_changed, so the
host re-lists its devices with their names. [XREF: device-names]
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel

from ui.widgets.section import Section
from ui.widgets.buttons import icon_button, button_row
from ui import theme


class ConnectionSection(Section):
    """Signals: refresh_requested(), connect_clicked(object data),
    disconnect_requested()."""

    refresh_requested = Signal()
    connect_clicked = Signal(object)
    disconnect_requested = Signal()
    names_changed = Signal()

    def __init__(self, selector_label: str = "Device:", placeholder: str = "(click Refresh)",
                 parent=None):
        super().__init__("Device", parent)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel(selector_label))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(150)
        self._combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._combo.addItem(placeholder, None)
        row.addWidget(self._combo, 1)
        self._v.addLayout(row)

        self._refresh_btn = icon_button("Refresh", "refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested)
        self._connect_btn = icon_button("Connect", "connect", "btnConnect")
        self._connect_btn.clicked.connect(
            lambda: self.connect_clicked.emit(self._combo.currentData()))
        self._disconnect_btn = icon_button("Disconnect", "disconnect",
                                           "btnDisconnect")
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self.disconnect_requested)
        self._names_btn = icon_button("Name devices…", "devices")
        self._names_btn.setToolTip("Discover a USB device by plugging it in, and give "
                                   "it a name all apps will show")
        self._names_btn.clicked.connect(self.open_names_dialog)
        self._v.addLayout(button_row(self._refresh_btn, self._connect_btn,
                                     self._disconnect_btn, self._names_btn))

        self._status = QLabel()
        self._v.addWidget(self._status)
        self.set_connected(False)

    # ------------------------------------------------------------------
    def set_items(self, items: list[tuple[str, object]], select=None,
                  empty_text: str = "(nothing found)"):
        """Replace the selector items. `select` (a data value) is selected
        when present; otherwise the previous selection is kept if listed."""
        keep = select if select is not None else self._combo.currentData()
        self._combo.clear()
        for text, data in items:
            self._combo.addItem(text, data)
        if not items:
            self._combo.addItem(empty_text, None)
        if keep is not None:
            idx = self._combo.findData(keep)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)

    def open_names_dialog(self):
        from ui.dialogs.device_names_dialog import DeviceNamesDialog
        DeviceNamesDialog(self).exec()
        self.names_changed.emit()

    def current_data(self):
        return self._combo.currentData()

    def set_connected(self, connected: bool, text: str = ""):
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._refresh_btn.setEnabled(not connected)
        self._combo.setEnabled(not connected)
        if connected:
            self._status.setText(f"● {text or 'Connected'}")
            token = "status_active"
        else:
            self._status.setText("● Not connected")
            token = "status_error"
        c = theme.get_color(token).name()
        self._status.setStyleSheet(f"color:{c}; font-weight:bold;")
