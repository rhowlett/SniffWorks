"""
ui/widgets/serial_device_panel.py  [v0.3]
[XREF: device-tab] The ion sniffer's Device tab, laid out like the AD2
DevicePanel (harmonized 2026-10-05):

    Device            shared ConnectionSection (port + Refresh, Connect /
                      Disconnect, ● status)
    Probe             what the probe reported in HELLO: firmware, mode,
                      protocol, and the fixed wiring
    Serial            link baud rate (moved here from Preferences)
    Device Info / Log same fixed-height monospace log as the AD2 tab

Same host surface as before (populate_ports / selected_port / set_connected /
append_info / clear_info, signals refresh_requested / connect_requested(str) /
disconnect_requested), plus set_probe_info(), current_baud(), names_changed,
and device names [XREF: device-names]: a named port is listed as
"<name> — <port> — <description>" and can be pre-selected by its USB serial
key (populate_ports(preferred_key=...)), so it survives a port rename.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLabel, QTextEdit,
)

from ui.widgets.connection_section import ConnectionSection
from ui.widgets.serial_prefs_section import SerialPrefsSection

WIRING_TEXT = "SCL → D8 (PA9), SDA → D2 (PA10), GND → GND"


class SerialDevicePanel(QWidget):
    """Signals:
        refresh_requested()
        connect_requested(str port_device)
        disconnect_requested()
    """

    refresh_requested = Signal()
    connect_requested = Signal(str)
    disconnect_requested = Signal()
    names_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        self._conn = ConnectionSection("Port:")
        self._conn.refresh_requested.connect(self.refresh_requested)
        self._conn.connect_clicked.connect(self._on_connect_clicked)
        self._conn.disconnect_requested.connect(self.disconnect_requested)
        self._conn.names_changed.connect(self.names_changed)
        root.addWidget(self._conn)

        probe = QGroupBox("Probe")
        form = QFormLayout(probe)
        form.setLabelAlignment(Qt.AlignRight)
        self._fw_lbl = QLabel()
        self._mode_lbl = QLabel()
        self._proto_lbl = QLabel()
        form.addRow("Firmware:", self._fw_lbl)
        form.addRow("Mode:", self._mode_lbl)
        form.addRow("Protocol:", self._proto_lbl)
        form.addRow("Wiring:", QLabel(WIRING_TEXT))
        note = QLabel("Firmware, mode and protocol are read from the probe's "
                      "HELLO when sniffing starts.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        form.addRow(note)
        root.addWidget(probe)
        self.set_probe_info(None)

        self._serial = SerialPrefsSection()
        root.addWidget(self._serial)

        info_box = QGroupBox("Device Info / Log")
        info_lay = QVBoxLayout(info_box)
        self._info = QTextEdit()
        self._info.setReadOnly(True)
        self._info.setFont(QFont("Courier New", 9))
        self._info.setMaximumHeight(160)
        info_lay.addWidget(self._info)
        root.addWidget(info_box)

        root.addStretch()

    # ------------------------------------------------------------------
    def populate_ports(self, ports: list[dict], preferred: str = None,
                       preferred_key: str = None):
        """ports: [{device, description, is_stlink, serial, key, name}] (see
        ion_backend.list_serial_ports). preferred_key (the last-used device's
        USB serial key) wins; else preferred (a port path); otherwise the
        current selection is kept if still listed. A port without a "name"
        is looked up in the per-user device names by its serial."""
        from core.device_names import DeviceNames, device_key
        names = DeviceNames()
        items = []
        self._port_keys = {}
        for p in ports:
            key = p.get("key") or (device_key(p["serial"]) if p.get("serial") else "")
            name = p.get("name") or (names.name_for(key) if key else "")
            self._port_keys[p["device"]] = key
            hint = p.get("hint") or ("ST-LINK" if p.get("is_stlink") else "")
            tag = f"  [{hint}]" if hint else ""
            text = f"{p['device']} — {p.get('description', '')}{tag}"
            items.append((f"{name} — {text}" if name else text, p["device"]))
        select = preferred
        if preferred_key:
            select = next((d for d, k in self._port_keys.items() if k == preferred_key),
                          preferred)
        self._conn.set_items(items, select=select,
                             empty_text="(no serial ports found)")

    def selected_key(self) -> str:
        """USB serial key of the selected port ("" if unknown)."""
        return getattr(self, "_port_keys", {}).get(self.selected_port() or "", "")

    def selected_port(self):
        return self._conn.current_data()

    def current_baud(self) -> int:
        return self._serial.current_baud()

    @property
    def serial_section(self) -> SerialPrefsSection:
        return self._serial

    def set_connected(self, connected: bool, info: str = ""):
        self._connected = connected
        self._conn.set_connected(connected, info)
        self._serial.setEnabled(not connected)   # baud applies on the next Connect
        if not connected:
            self.set_probe_info(None)

    def set_probe_info(self, hello: dict | None):
        """Show the HELLO fields; None = not read yet."""
        dash = "— (read on Start Sniffing)"
        self._fw_lbl.setText(str(hello.get("fw", "?")) if hello else dash)
        self._mode_lbl.setText(str(hello.get("mode", "?")) if hello else dash)
        self._proto_lbl.setText(str(hello.get("proto", "?")) if hello else dash)

    def append_info(self, text: str):
        self._info.append(text)

    def clear_info(self):
        self._info.clear()

    # ------------------------------------------------------------------
    def _on_connect_clicked(self, port):
        if port:
            self.connect_requested.emit(port)
        else:
            self.append_info("No port selected — click Refresh and pick the "
                             "ST-LINK COM port.")
