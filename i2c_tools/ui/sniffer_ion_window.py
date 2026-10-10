"""
ui/sniffer_ion_window.py  [v0.2]
Main window for the NUCLEO-C031C6 I2C sniffer (sniffer_nucleoC0.py) — the
same GUI as the AD2 sniffer with the WaveForms backend replaced by the serial
link to the Nucleo firmware (core.ion_backend).

Tabs: Device (port, probe info, serial baud, log - laid out like the AD2
Device tab) | Sniffer (controls+stats sidebar, log table) | Preferences
(themes) | Help | Exit.

Reused wholesale from the shared kits: LogPanel (filters/export — item 7),
SnifferPanel with its Capture Stats (item 6), TableDataSection,
LoadDecoderSection, self-managed EditorSection, PreferencesTab/HelpTab/ExitTab,
ConfirmingCloseMixin/notify via AppWindow. New shared pieces (item 2):
SerialDevicePanel (which owns the SerialPrefsSection since 2026-10-05).
"""
from __future__ import annotations

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QLabel

from ui.widgets import AppWindow, Sidebar, make_tab_body
from ui.widgets.registers_tabs_host import RegisterTabsHost
from ui.widgets.sidebar_sections import (
    TableDataSection, LoadDecoderSection, EditorSection,
)
from ui.widgets.serial_device_panel import SerialDevicePanel
from ui.tabs import PreferencesTab, HelpTab, ExitTab
from ui.sniffer_panel import SnifferPanel
from ui.log_panel import LogPanel
from ui import theme

from core.ion_backend import IonWorker, list_serial_ports
from ui.common import settings_store

APP_TITLE = "Ion I2C Sniffer"
APP_ID = "sniffer_ion"          # key for the per-user last-used device

SNIFFER_DESC = ("Passive mode: the Nucleo listens on SCL/SDA without driving "
                "the bus.\nWiring: SCL → D8 (PA9), SDA → D2 (PA10), GND → GND.")


class SnifferIonWindow(RegisterTabsHost, AppWindow):  # AppWindow includes ConfirmingCloseMixin
    _txn_ready = Signal(object)   # cross-thread transaction delivery

    def __init__(self, parent=None):
        super().__init__(APP_TITLE, parent)
        self.resize(1250, 780)

        self._current_theme = theme.active_theme_name() or "default"
        self._worker: IonWorker | None = None
        self._connected_port = None
        self._captured = 0
        self._errors = 0

        self._build_tabs()
        self._build_status_bar()
        self._connect_signals()
        self._txn_ready.connect(self._handle_transaction)

        # Enumerate ports shortly after show (mirrors the AD2 DWF pattern)
        QTimer.singleShot(100, self._refresh_ports)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_tabs(self):
        # --- Device tab ---
        self._device_panel = SerialDevicePanel()
        self.add_tab(self._device_panel, "Device")

        # --- Sniffer tab = [sidebar of sections | log table] ---
        self._sniffer_panel = SnifferPanel(description=SNIFFER_DESC,
                                           show_bus_clock=True)
        self._table_data = TableDataSection()
        self._load_decoder = LoadDecoderSection()
        self._editor_section = EditorSection(               # [XREF: edit-decoder]
            path_provider=lambda: self._load_decoder.selected_path())

        sidebar = Sidebar(max_width=400)
        sidebar.add_section(self._sniffer_panel)       # controls + Capture Stats
        sidebar.add_section(self._table_data)          # [XREF: table-data]
        sidebar.add_section(self._load_decoder)        # [XREF: file-picker]
        sidebar.add_section(self._editor_section)      # [XREF: edit-decoder]
        sidebar.add_stretch()

        self._log_panel = LogPanel(show_toolbar=False)
        self.add_tab(make_tab_body(sidebar, self._log_panel), "Sniffer")

        # --- Preferences tab (themes; the serial baud is on the Device tab) ---
        self._preferences = PreferencesTab(self._current_theme)
        self.add_tab(self._preferences, "Preferences")

        # --- Help + Exit tabs ---
        self._help = HelpTab.for_app("sniffer_ion")   # [XREF: help-tab]
        self.add_tab(self._help, "Help")
        self._exit_panel = ExitTab(APP_TITLE)              # [XREF: exit-tab]
        self.add_tab(self._exit_panel, "Exit")

    def _build_status_bar(self):
        sb = self.statusBar()
        self._status_port = QLabel("No device")
        self._status_fw = QLabel("")
        self._status_bus = QLabel("")
        self._status_spy = QLabel("")
        # same order as the AD2 window: backend/firmware, device, bus, spy
        for w in [self._status_fw, self._status_port, self._status_bus,
                  self._status_spy]:
            sb.addPermanentWidget(QLabel(" | "))
            sb.addPermanentWidget(w)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        dp = self._device_panel
        dp.refresh_requested.connect(self._refresh_ports)
        dp.names_changed.connect(self._refresh_ports)   # [XREF: device-names]
        dp.connect_requested.connect(self._on_connect)
        dp.disconnect_requested.connect(self._on_disconnect)

        sp = self._sniffer_panel
        sp.start_requested.connect(self._on_spy_start)
        sp.stop_requested.connect(self._on_spy_stop)
        sp.pec_changed.connect(self._on_pec_changed)

        # Table Data section drives the (toolbar-less) log panel. [XREF: table-data]
        self._table_data.clear_requested.connect(self._log_panel.clear_log)
        self._table_data.export_requested.connect(self._log_panel.export_csv_dialog)
        self._table_data.auto_scroll_changed.connect(self._log_panel.set_auto_scroll)
        self._table_data.show_int_changed.connect(self._log_panel.set_int_visible)
        self._table_data.show_ascii_changed.connect(self._log_panel.set_ascii_visible)

        # Decoders set -> merged schema live-decodes the log. [XREF: decoder-manager]
        self._load_decoder.decoders_changed.connect(self._on_decoders_changed)
        if self._load_decoder.is_valid():   # persisted set restored pre-wiring
            self._on_decoders_changed()

        # Preferences: apply theme on request (repaints via theme.signals)
        self._preferences.theme_apply_requested.connect(self._on_theme_apply)

        # Exit tab -> the same clean-close path as the window close button.
        self._exit_panel.exit_requested.connect(self.close)  # [XREF: exit-tab]

    # ------------------------------------------------------------------
    # Device / connection
    # ------------------------------------------------------------------
    def _refresh_ports(self):
        try:
            ports = list_serial_ports()
        except Exception as e:
            self._device_panel.append_info(f"Port enumeration failed: {e}")
            ports = []
        preferred = settings_store.store().get_str(
            settings_store.KEY_LAST_PORT) or None    # [XREF: settings]
        from core.device_names import DeviceNames   # [XREF: device-names]
        last_key = DeviceNames().last_used(APP_ID)  # by USB serial, not port
        self._device_panel.populate_ports(ports, preferred=preferred,
                                          preferred_key=last_key)
        stlinks = sum(1 for p in ports if p.get("is_stlink"))
        self._device_panel.append_info(
            f"Found {len(ports)} serial port(s), {stlinks} ST-LINK.")

    def _on_connect(self, port_device: str):
        """Connection = start the worker on Start Sniffing; here we only
        validate the selection, remember it, and arm the Sniffer tab (the
        firmware streams nothing until CMD_START, so a persistent idle
        connection adds no value over connect-on-start)."""
        self._connected_port = port_device
        settings_store.store().set(settings_store.KEY_LAST_PORT, port_device)
        from core.device_names import DeviceNames   # [XREF: device-names]
        key = self._device_panel.selected_key()
        names = DeviceNames()
        if key:
            names.set_last_used(APP_ID, key)
            try:
                names.save()
            except OSError:
                pass                                # naming is a convenience
        name = names.name_for(key) if key else ""
        shown = f"{name} ({port_device})" if name else port_device
        baud = self._device_panel.current_baud()
        self._device_panel.set_connected(True, f"{port_device} @ {baud}")
        self._device_panel.append_info(
            f"Selected {port_device} @ {baud} baud — press Start Sniffing "
            f"on the Sniffer tab.")
        self._status_port.setText(shown)
        self._sniffer_panel.set_device_ready(True)
        self.notify(f"Ready: {port_device}")

    def _on_disconnect(self):
        self._stop_spy()
        self._connected_port = None
        self._device_panel.set_connected(False)
        self._device_panel.append_info("Disconnected.")
        self._status_port.setText("No device")
        self._status_fw.setText("")
        self._status_bus.setText("")
        self._sniffer_panel.set_device_ready(False)

    # ------------------------------------------------------------------
    # Sniffing
    # ------------------------------------------------------------------
    def _on_spy_start(self):
        if not self._connected_port:
            self.notify("Select a port on the Device tab first.")
            self._sniffer_panel.set_device_ready(False)
            return
        self._captured = 0
        self._errors = 0
        self._worker = IonWorker(
            self._connected_port,
            baud=self._device_panel.current_baud(),
            check_pec=self._sniffer_panel.pec_enabled,
            parent=self,
        )
        w = self._worker
        w.transaction_captured.connect(self._on_worker_transaction)
        w.error_occurred.connect(self._on_worker_error)
        w.stats_updated.connect(self._on_worker_stats)
        w.device_status.connect(self._on_device_status)
        w.connected.connect(self._on_worker_connected)
        w.disconnected.connect(self._on_worker_disconnected)
        w.start()
        self._sniffer_panel.set_bus_hz(0)   # firmware re-measures per capture
        self._status_spy.setText("● Sniffing")
        self._status_spy.setStyleSheet(
            f"color:{theme.get_color('status_active').name()};")

    def _on_spy_stop(self):
        self._stop_spy()

    def _stop_spy(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        self._worker = None
        self._status_spy.setText("")
        self._status_spy.setStyleSheet("")

    # -- worker signal handlers (worker thread -> queued to main thread) --
    def _on_worker_connected(self, hello: dict):
        fw = hello.get("fw", "?")
        mode = hello.get("mode", "?")
        self._status_fw.setText(f"fw {fw} ({mode})")
        self._device_panel.set_probe_info(hello)
        self._device_panel.append_info(
            f"HELLO: firmware {fw}, mode {mode}. Capturing.")

    def _on_worker_disconnected(self):
        # Worker ended (stop or error) — reflect idle state if user didn't stop
        self._status_spy.setText("")
        self._status_spy.setStyleSheet("")

    def _on_worker_transaction(self, txn):
        self._txn_ready.emit(txn)

    def _handle_transaction(self, txn):
        """Main thread: add to log model (same path as the AD2 sniffer)."""
        self._log_panel.model.add_transaction(txn)
        self._captured += 1
        self._update_stats()

    def _on_worker_error(self, msg: str):
        self._errors += 1
        self.notify(f"Sniffer: {msg}")
        self._device_panel.append_info(f"⚠ {msg}")
        self._update_stats()

    def _on_worker_stats(self, captured: int, errors: int):
        # device-side counters (authoritative for captured/errors totals)
        self._captured = max(self._captured, captured)
        self._errors = max(self._errors, errors)
        self._update_stats()

    def _on_device_status(self, status: dict):
        bus_hz = status.get("bus_hz", 0)
        dropped = status.get("dropped", 0)
        self._sniffer_panel.set_bus_hz(bus_hz)
        text = (f"bus ≈ {SnifferPanel.format_bus_hz(bus_hz)}"
                if bus_hz else "")
        if dropped:
            text += f"  dropped {dropped}"
        self._status_bus.setText(text)

    def _update_stats(self):
        self._sniffer_panel.update_stats(
            self._captured, self._errors,
            self._log_panel.model.visible_count,
            self._log_panel.model.total_count)

    def _on_pec_changed(self, enabled: bool):
        if self._worker:
            self._worker.set_check_pec(enabled)

    # ------------------------------------------------------------------
    # Preferences / decoder
    # ------------------------------------------------------------------
    def _on_theme_apply(self, theme_name: str):
        self._current_theme = theme_name
        theme.apply_theme(theme_name)
        self.notify(f"Theme applied: {theme_name}")

    def _on_decoders_changed(self):
        # [XREF: decoder-manager] apply the merged schema (all loaded devices)
        schema = self._load_decoder.merged_schema()
        self._rebuild_register_tabs(schema, self._load_decoder.manager)  # cache attaches BEFORE decode:
        self._log_panel.apply_schema(schema)             # re-decode replays history
        self.notify(self._load_decoder.manager.summary())


    # ------------------------------------------------------------------
    # [XREF: exit-tab] ConfirmingCloseMixin: confirm unexported rows, teardown
    # ------------------------------------------------------------------
    def close_guard(self):
        rows = self._log_panel.model.total_count
        if rows > 0:
            return (f"{rows} captured transaction(s) are in the log and have "
                    f"not been exported.\n\nExit and discard them?")
        return None

    def on_close(self):
        self._stop_spy()
        self._editor_section.close_editor()
