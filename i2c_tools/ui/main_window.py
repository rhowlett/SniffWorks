"""
main_window.py  [v0.2]
Main application window for the AD2 I2C Tool.
Coordinates: DevicePanel, SnifferPanel, RWPanel, LogPanel.
"""

import sys
import threading
import time
import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTabWidget, QStatusBar, QLabel,
    QMessageBox, QProgressDialog, QApplication,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QFont, QPalette, QColor

from ui.device_panel import DevicePanel
from ui.sniffer_panel import SnifferPanel
from ui.rw_panel import RWPanel
from ui.log_panel import LogPanel
from ui.tabs import PreferencesTab
from ui.widgets import ConfirmingCloseMixin, StatusBarNotifier
from ui.decoder_editor_launcher import open_or_focus_decoder_editor
from ui import theme

# These are imported lazily after DWF loads successfully
_dwf = None
_constants = None


class ScanWorker(QThread):
    finished = Signal(list)
    progress = Signal(int)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._ctrl = controller

    def run(self):
        results = self._ctrl.scan_addresses(progress_cb=lambda a: self.progress.emit(a))
        self.finished.emit(results)


class MainWindow(ConfirmingCloseMixin, StatusBarNotifier, QMainWindow):
    _txn_ready = Signal(object)   # cross-thread transaction delivery

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AD2 I2C / SMBus Tool")
        self.resize(1300, 820)

        self._device_mgr = None
        self._i2c_ctrl = None
        self._spy_worker = None
        self._spy_total_captured = 0
        self._spy_total_errors = 0
        self._current_theme = "default"
        self._decoder_editor_win = None   # [XREF: edit-decoder] lazily opened

        theme.apply_theme(self._current_theme)
        self._build_ui()
        self._build_status_bar()

        # Internal signal for cross-thread transaction delivery
        self._txn_ready.connect(self._handle_transaction)

        # Attempt to load DWF on startup (non-fatal)
        QTimer.singleShot(100, self._init_dwf)

    # ------------------------------------------------------------------
    # DWF init
    # ------------------------------------------------------------------
    def _init_dwf(self):
        global _dwf, _constants
        try:
            from core.dwf_loader import load_dwf, get_dwf_version
            _dwf, _constants, cpath = load_dwf()
            version = get_dwf_version(_dwf)
            self._device_panel.append_info(f"DWF library loaded OK — version {version}")
            self._device_panel.append_info(f"dwfconstants: {cpath}")
            self._status_dwf.setText(f"DWF {version}")

            from core.device_manager import DeviceManager
            self._device_mgr = DeviceManager(_dwf, _constants)
            self._refresh_devices()
        except Exception as e:
            self._device_panel.append_info(f"⚠ DWF load error: {e}")
            self._status_dwf.setText("DWF not found")
            QMessageBox.warning(
                self, "WaveForms SDK Not Found",
                f"{e}\n\nInstall WaveForms from:\nhttps://digilent.com/shop/software/digilent-waveforms/"
            )

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ---- Left sidebar tabs ----
        self._left_tabs = QTabWidget()
        # Wider dashboard so the device selector is not covered by Refresh and
        # the rate preset labels are fully readable. Minimum (not fixed) width
        # lets the splitter grow it further if the user drags.
        self._left_tabs.setMinimumWidth(400)
        self._left_tabs.setTabPosition(QTabWidget.West)

        self._device_panel = DevicePanel()
        self._sniffer_panel = SnifferPanel(bus_clock_available=False)
        self._rw_panel = RWPanel()
        self._preferences_panel = PreferencesTab(current_theme=self._current_theme)

        self._left_tabs.addTab(self._device_panel, "Device")
        self._left_tabs.addTab(self._sniffer_panel, "Sniffer")
        self._left_tabs.addTab(self._rw_panel, "Read/Write")
        self._left_tabs.addTab(self._preferences_panel, "Preferences")

        # ---- Right: Log panel ----
        self._log_panel = LogPanel()

        # ---- Splitter ----
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._left_tabs)
        splitter.addWidget(self._log_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 980])
        root.addWidget(splitter)

        self._connect_signals()

    def _build_status_bar(self):
        sb = self.statusBar()
        self._status_dwf = QLabel("DWF: loading…")
        self._status_device = QLabel("No device")
        self._status_rate = QLabel("")
        self._status_pins = QLabel("")
        self._status_spy = QLabel("")

        for w in [self._status_dwf, self._status_device, self._status_rate,
                  self._status_pins, self._status_spy]:
            sb.addPermanentWidget(QLabel(" | "))
            sb.addPermanentWidget(w)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        dp = self._device_panel
        dp.refresh_requested.connect(self._refresh_devices)
        dp.names_changed.connect(self._refresh_devices)   # [XREF: device-names]
        dp.connect_requested.connect(self._on_connect)
        dp.disconnect_requested.connect(self._on_disconnect)
        dp.apply_config_requested.connect(self._on_apply_config)
        dp.clear_bus_requested.connect(self._on_clear_bus)
        dp.scan_requested.connect(self._on_scan)
        dp.self_test_requested.connect(self._on_self_test)

        sp = self._sniffer_panel
        sp.start_requested.connect(self._on_spy_start)
        sp.stop_requested.connect(self._on_spy_stop)
        sp.pec_changed.connect(self._on_pec_changed)

        rw = self._rw_panel
        rw.write_requested.connect(self._on_write)
        rw.read_requested.connect(self._on_read)
        rw.write_read_requested.connect(self._on_write_read)
        rw.scan_requested.connect(self._on_scan)

        # Preferences: apply theme on request
        self._preferences_panel.theme_apply_requested.connect(self._on_theme_apply)

        # Decoder editing lives in the standalone Decoder Editor; the log
        # panel's Edit Decoder button opens or focuses it. [XREF: edit-decoder]
        self._log_panel.edit_decoder_requested.connect(self._on_edit_decoder)

    # ------------------------------------------------------------------
    # Preferences / Decoder editor
    # ------------------------------------------------------------------
    def _on_theme_apply(self, theme_name: str):
        self._current_theme = theme_name
        theme.apply_theme(theme_name)
        self.notify(f"Theme applied: {theme_name}")

    def _on_edit_decoder(self):
        # [XREF: edit-decoder] open the standalone editor, or focus it if already open
        self._decoder_editor_win = open_or_focus_decoder_editor(self._decoder_editor_win)

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------
    def _refresh_devices(self):
        if self._device_mgr is None:
            return
        devices = self._device_mgr.enumerate_devices()
        from core.device_names import DeviceNames   # [XREF: device-names]
        last = DeviceNames().last_used("ad2_tool") or ""
        self._device_panel.populate_devices(
            devices, preferred_serial=last[3:] if last.startswith("sn:") else None)
        self._device_panel.append_info(f"Found {len(devices)} device(s)")

    def _on_connect(self, device_index: int):
        if self._device_mgr is None:
            QMessageBox.warning(self, "Error", "DWF library not loaded.")
            return

        ok = self._device_mgr.open(device_index)
        if not ok:
            err = self._device_mgr.last_error()
            QMessageBox.critical(self, "Connect Failed", f"Could not open device:\n{err}")
            return

        # Enumerate to get device name for display
        devs = self._device_mgr.enumerate_devices()
        dev_name = devs[device_index].name if device_index < len(devs) and device_index >= 0 else "Device"
        from core.device_names import DeviceNames, device_key   # [XREF: device-names]
        serial = self._device_panel.serial_for_index(device_index)
        if serial:
            names = DeviceNames()
            names.set_last_used("ad2_tool", device_key(serial))
            try:
                names.save()
            except OSError:
                pass                                # naming is a convenience
            dev_name = names.name_for(serial) or dev_name

        self._device_panel.set_connected(True)
        self._sniffer_panel.set_device_ready(True)
        self._rw_panel.set_enabled(True)
        self._status_device.setText(f"✓ {dev_name}")

        # Create I2C controller
        from core.i2c_controller import I2CController
        self._i2c_ctrl = I2CController(_dwf, self._device_mgr.handle)
        self._device_panel.append_info(f"Connected to {dev_name}")

        # Auto-apply default config
        self._on_apply_config(
            self._device_panel.scl_pin,
            self._device_panel.sda_pin,
            -1,
            100_000,
            True,
        )

    def _on_disconnect(self):
        self._stop_spy()
        if self._device_mgr:
            self._device_mgr.close()
        self._i2c_ctrl = None
        self._device_panel.set_connected(False)
        self._sniffer_panel.set_device_ready(False)
        self._rw_panel.set_enabled(False)
        self._status_device.setText("No device")
        self._status_rate.setText("")
        self._status_pins.setText("")
        self._device_panel.append_info("Disconnected.")

    # ------------------------------------------------------------------
    # I2C Config
    # ------------------------------------------------------------------
    def _on_apply_config(self, scl: int, sda: int, alert: int, rate_hz: float, stretch: bool):
        if self._i2c_ctrl is None:
            return
        self._i2c_ctrl.configure(scl, sda, alert, rate_hz, stretch)
        rate_k = rate_hz / 1000
        self._status_rate.setText(f"{rate_k:.0f} kHz")
        self._status_pins.setText(f"SCL=DIO{scl} SDA=DIO{sda}")
        self._device_panel.append_info(
            f"Config: SCL=DIO{scl} SDA=DIO{sda} ALERT={'DIO'+str(alert) if alert >= 0 else 'N/A'} "
            f"Rate={rate_k:.0f}kHz Stretch={'Y' if stretch else 'N'}"
        )

    def _on_clear_bus(self):
        if self._i2c_ctrl is None:
            return
        ok, err = self._i2c_ctrl.clear_bus()
        if ok:
            self._device_panel.append_info("Bus cleared OK")
        else:
            self._device_panel.append_info(f"Bus clear: {err}")

    # ------------------------------------------------------------------
    # Self-test
    # ------------------------------------------------------------------
    def _on_self_test(self):
        if self._device_mgr is None:
            return
        result = self._device_mgr.run_self_test()
        lines = [
            f"=== Self-Test {datetime.datetime.now().strftime('%H:%M:%S')} ===",
            f"DWF version : {result.get('version', 'n/a')}",
            f"Temperature : {result.get('temperature', 'n/a')} °C",
            f"USB supply  : {result.get('supply', 'n/a')} V",
            f"Result      : {'PASS ✓' if result['passed'] else 'FAIL ✗'}",
        ]
        if result.get("error"):
            lines.append(f"Error       : {result['error']}")
        self._device_panel.append_info("\n".join(lines))

    # ------------------------------------------------------------------
    # Address scan
    # ------------------------------------------------------------------
    def _on_scan(self):
        if self._i2c_ctrl is None:
            QMessageBox.warning(self, "No Device", "Connect a device first.")
            return

        progress = QProgressDialog("Scanning I2C addresses…", "Cancel", 3, 120, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(3)
        progress.show()

        worker = ScanWorker(self._i2c_ctrl, self)

        def on_progress(addr):
            progress.setValue(addr)
            QApplication.processEvents()

        def on_done(addresses):
            progress.close()
            self._rw_panel.populate_scan_results(addresses)
            self._device_panel.append_info(
                f"Scan complete: {len(addresses)} device(s) found — "
                + (", ".join(f"0x{a:02X}" for a in addresses) or "none")
            )

        worker.progress.connect(on_progress)
        worker.finished.connect(on_done)
        worker.start()

    # ------------------------------------------------------------------
    # Spy / Sniffer
    # ------------------------------------------------------------------
    def _on_spy_start(self):
        if self._i2c_ctrl is None:
            QMessageBox.warning(self, "No Device", "Connect and configure first.")
            return

        ok, err = self._i2c_ctrl.spy_start()
        if not ok:
            QMessageBox.critical(self, "Spy Error", f"Could not start spy:\n{err}")
            return

        from core.spy_worker import SpyWorker
        self._spy_worker = SpyWorker(
            self._i2c_ctrl,
            check_pec=self._sniffer_panel.pec_enabled,
            parent=self,
        )
        self._spy_worker.transaction_captured.connect(self._on_spy_transaction)
        self._spy_worker.error_occurred.connect(self._on_spy_error)
        self._spy_worker.stats_updated.connect(self._on_spy_stats)
        self._spy_worker.start()

        self._status_spy.setText("● Sniffing")
        self._status_spy.setStyleSheet("color:#2ECC71;")
        self._spy_total_captured = 0
        self._spy_total_errors = 0

    def _on_spy_stop(self):
        self._stop_spy()

    def _stop_spy(self):
        if self._spy_worker and self._spy_worker.isRunning():
            self._spy_worker.stop()
            self._spy_worker.wait(2000)
            self._spy_worker = None
        if self._i2c_ctrl:
            self._i2c_ctrl.spy_stop()
        self._status_spy.setText("")
        self._status_spy.setStyleSheet("")

    def _on_spy_transaction(self, txn):
        """Called from SpyWorker thread — relay via Qt signal for thread safety."""
        self._txn_ready.emit(txn)

    def _handle_transaction(self, txn):
        """Main thread: add to log model."""
        self._log_panel.model.add_transaction(txn)
        self._spy_total_captured += 1
        self._update_spy_stats()

    def _on_spy_error(self, msg: str):
        self._spy_total_errors += 1
        self._status_bar_msg(f"Spy error: {msg}")
        self._update_spy_stats()

    def _on_spy_stats(self, captured: int, errors: int):
        self._spy_total_captured = captured
        self._spy_total_errors = errors
        self._update_spy_stats()

    def _update_spy_stats(self):
        self._sniffer_panel.update_stats(
            self._spy_total_captured,
            self._spy_total_errors,
            self._log_panel.model.visible_count,
            self._log_panel.model.total_count,
        )

    def _on_pec_changed(self, enabled: bool):
        if self._spy_worker:
            self._spy_worker.set_check_pec(enabled)

    # ------------------------------------------------------------------
    # Master Read / Write
    # ------------------------------------------------------------------
    def _on_write(self, addr: int, data: bytes, add_pec: bool):
        if not self._i2c_ctrl:
            return
        ok, err, txn = self._i2c_ctrl.write(addr, data, add_pec)
        self._log_panel.model.add_transaction(txn)
        self._rw_panel.show_result(txn, ok, err)
        if not ok:
            self._status_bar_msg(f"Write NAK: {err}")

    def _on_read(self, addr: int, count: int, check_pec: bool):
        if not self._i2c_ctrl:
            return
        ok, err, txn = self._i2c_ctrl.read(addr, count, check_pec)
        self._log_panel.model.add_transaction(txn)
        self._rw_panel.show_result(txn, ok, err)
        if not ok:
            self._status_bar_msg(f"Read NAK: {err}")

    def _on_write_read(self, addr: int, write_data: bytes, read_count: int, check_pec: bool):
        if not self._i2c_ctrl:
            return
        ok, err, txns = self._i2c_ctrl.write_read(addr, write_data, read_count, check_pec)
        for t in txns:
            self._log_panel.model.add_transaction(t)
        self._rw_panel.show_result(txns[-1], ok, err)
        if not ok:
            self._status_bar_msg(f"Write-Read NAK: {err}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _status_bar_msg(self, msg: str):
        self.notify(msg)


    # [XREF: exit-tab] ConfirmingCloseMixin: teardown only
    def on_close(self):
        self._stop_spy()
        if self._device_mgr:
            self._device_mgr.close_all()
