"""
ui/dialogs/device_names_dialog.py  [v0.1]
[XREF: device-names] "Name devices" dialog, shared by every app with a USB
device (opened from the shared ConnectionSection's "Name devices…" button).

  1. Discover a new device
     Start -> the dialog takes a snapshot of the connected USB devices and
     asks you to plug the board in (unplug it first if it is already in; the
     snapshot follows unplugs, so a replug is detected). It polls every
     0.5 s for up to 60 s; when a new serial number appears it shows the
     device and asks for a name.
  2. Connected USB devices
     Every connected USB device with its port, serial, VID:PID and name.
     Edit the Name cell to name or rename any of them (for boards you can
     identify by their port or serial); clear it to forget the name.

Names go to the per-user file (core/device_names.py) and are shared by all
apps. The scanner and store are injectable for tests.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from core import device_names as dn
from ui.widgets.buttons import icon_button, button_row

POLL_MS = 500
TIMEOUT_S = 60


class DeviceNamesDialog(QDialog):
    COLS = ["Name", "Port", "Serial number", "VID:PID", "Description"]

    def __init__(self, parent=None, scanner: Optional[Callable[[], list]] = None,
                 store: Optional[dn.DeviceNames] = None):
        super().__init__(parent)
        self.setWindowTitle("Name USB devices")
        self.resize(900, 560)
        self._scan = scanner or dn.scan_usb
        self._store = store or dn.DeviceNames()
        self._tracker: Optional[dn.DiscoveryTracker] = None
        self._found: list = []
        self._elapsed_ms = 0
        self._loading = False
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._on_tick)
        self._build_ui()
        self.refresh_table()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        disc = QGroupBox("1. Discover a new device")
        dl = QVBoxLayout(disc)
        self._step = QLabel("Press Start, then plug in the device you want to name. "
                            "If it is already plugged in, unplug it first.")
        self._step.setWordWrap(True)
        dl.addWidget(self._step)
        self._start_btn = icon_button("Start", "scan")
        self._start_btn.clicked.connect(self.start_discovery)
        self._stop_btn = icon_button("Stop", "disconnect")
        self._stop_btn.clicked.connect(self.stop_discovery)
        self._stop_btn.setEnabled(False)
        dl.addLayout(button_row(self._start_btn, self._stop_btn))
        self._found_lbl = QLabel("")
        self._found_lbl.setWordWrap(True)
        dl.addWidget(self._found_lbl)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. C031 sniffer, H533 DUT, Bench AD2")
        self._name_edit.setMinimumWidth(280)
        self._name_edit.setMaximumWidth(360)
        self._name_edit.returnPressed.connect(lambda: self.save_found_name(self._name_edit.text()))
        name_row.addWidget(self._name_edit)
        self._save_btn = icon_button("Save name", "export")
        self._save_btn.clicked.connect(lambda: self.save_found_name(self._name_edit.text()))
        name_row.addWidget(self._save_btn)
        name_row.addStretch(1)
        dl.addLayout(name_row)
        self._set_found_visible(False)
        root.addWidget(disc)

        tbl = QGroupBox("2. Connected USB devices — edit a Name cell to name or rename; clear it to forget")
        tl = QVBoxLayout(tbl)
        self._table = QTableWidget(0, len(self.COLS))
        self._table.setHorizontalHeaderLabels(self.COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.itemChanged.connect(self._on_item_changed)
        tl.addWidget(self._table)
        self._msg = QLabel("")
        self._msg.setObjectName("mutedLabel")
        self._msg.setWordWrap(True)
        tl.addWidget(self._msg)
        refresh = icon_button("Refresh", "refresh")
        refresh.clicked.connect(self.refresh_table)
        close = icon_button("Close", "close")
        close.clicked.connect(self.accept)
        tl.addLayout(button_row(refresh, close))
        root.addWidget(tbl, 1)

    def _set_found_visible(self, on: bool):
        for w in (self._name_edit, self._save_btn):
            w.setVisible(on)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def start_discovery(self):
        self._tracker = dn.DiscoveryTracker(self._scan())
        self._found = []
        self._elapsed_ms = 0
        self._set_found_visible(False)
        self._found_lbl.setText("")
        self._step.setText(f"Snapshot taken ({len(self._tracker.baseline)} USB device(s) connected). "
                           f"Plug in the device now (unplug and re-plug it if it was already in). "
                           f"Waiting up to {TIMEOUT_S} s…")
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._timer.start()

    def stop_discovery(self, text: str = "Stopped. Press Start to try again."):
        self._timer.stop()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._step.setText(text)

    def _on_tick(self):
        self._elapsed_ms += POLL_MS
        self.poll_once()
        if not self._found and self._elapsed_ms >= TIMEOUT_S * 1000:
            self.stop_discovery("No new USB device appeared within "
                                f"{TIMEOUT_S} s. Check the cable (charge-only cables show "
                                "nothing) and press Start to try again.")

    def poll_once(self) -> None:
        if self._tracker is None:
            return
        new = self._tracker.poll(self._scan())
        if not new:
            return
        self._found = new
        self._timer.stop()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        d = new[0]
        current = self._store.name_for(d.key)
        more = f" (and {len(new) - 1} more — name them in the table below)" if len(new) > 1 else ""
        warn = ("" if d.has_serial else
                " ⚠ This device has no USB serial number; the name is tied to the USB "
                "socket it is plugged into.")
        self._step.setText("New device found:")
        self._found_lbl.setText(
            f"<b>{d.description or 'USB device'}</b> on {d.port or '(no port)'} — serial "
            f"{d.serial or '(none)'}, VID:PID {d.vid_pid}{more}."
            + (f" Currently named <b>{current}</b>." if current else " Not named yet.") + warn)
        self._set_found_visible(True)
        self._name_edit.setText(current)
        self._name_edit.setFocus()
        self.refresh_table()

    def found_devices(self) -> list:
        return list(self._found)

    def save_found_name(self, name: str) -> bool:
        if not self._found:
            return False
        ok, msg = self._apply_name(self._found[0], name)
        self._step.setText(msg)
        if ok:
            self._set_found_visible(False)
            self.refresh_table()
        return ok

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------
    def refresh_table(self):
        self._devices = self._scan()
        self._loading = True
        self._table.setRowCount(len(self._devices))
        for row, d in enumerate(self._devices):
            desc = d.description
            if d.manufacturer and not desc.lower().startswith(d.manufacturer.lower()):
                desc = f"{d.manufacturer} {desc}".strip()
            vals = [self._store.name_for(d.key), d.port, d.serial or "(none)", d.vid_pid, desc]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if col != 0:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, it)
        self._loading = False

    def table_rows(self) -> list[dict]:
        return [{"name": self._table.item(r, 0).text(), "port": self._table.item(r, 1).text(),
                 "serial": self._table.item(r, 2).text()} for r in range(self._table.rowCount())]

    def _on_item_changed(self, item):
        if self._loading or item.column() != 0:
            return
        d = self._devices[item.row()]
        ok, msg = self._apply_name(d, item.text())
        self._msg.setText(msg)
        if not ok:
            self.refresh_table()

    def set_row_name(self, port: str, name: str) -> tuple[bool, str]:
        for d in self._devices:
            if d.port == port:
                ok, msg = self._apply_name(d, name)
                self.refresh_table()
                return ok, msg
        return False, f"{port} is not connected"

    def _apply_name(self, d, name: str) -> tuple[bool, str]:
        name = (name or "").strip()
        try:
            if name:
                self._store.set_name(d, name)
                msg = f"Saved: {d.port or d.serial} is now '{name}'."
            else:
                self._store.forget(d.key)
                msg = f"Forgot the name of {d.port or d.serial}."
            self._store.save()
            return True, msg
        except dn.NameError_ as e:
            return False, str(e)
        except OSError as e:
            return False, f"Could not save {self._store.path}: {e}"

    def closeEvent(self, event):  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)
