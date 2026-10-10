"""
sniffer_panel.py  [v0.1]
Controls for the passive I2C spy/sniffer mode.
"""

from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QFrame, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QFont

from ui import theme


class _EqualWidthRow(QWidget):
    """Lays two buttons side by side at exactly the same width.

    A QHBoxLayout with equal stretch hands an odd leftover pixel to one
    widget, so the pair can differ by 1 px; this row splits its width
    itself (any spare pixel goes to the right-hand gap, not a button).
    """

    SPACING = 6

    def __init__(self, left: QWidget, right: QWidget, parent=None):
        super().__init__(parent)
        self._pair = (left, right)
        for w in self._pair:
            w.setParent(self)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def _cell_hint(self) -> QSize:
        hints = [w.sizeHint() for w in self._pair]
        return QSize(max(h.width() for h in hints),
                     max(h.height() for h in hints))

    def sizeHint(self) -> QSize:
        c = self._cell_hint()
        return QSize(2 * c.width() + self.SPACING, c.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = (self.width() - self.SPACING) // 2
        h = self.height()
        left, right = self._pair
        left.setGeometry(0, 0, w, h)
        right.setGeometry(w + self.SPACING, 0, w, h)


class SnifferPanel(QWidget):
    """
    Controls: Start/Stop sniffing, PEC check, stats display.
    Emits: start_requested, stop_requested, pec_changed(bool)
    """

    start_requested = Signal()
    stop_requested = Signal()
    pec_changed = Signal(bool)

    DEFAULT_DESC = ("Passive mode: listens on SCL/SDA without driving the bus.\n"
                    "Connect AD2 DIO pins in parallel with your I2C bus.")

    def __init__(self, parent=None, description: str = None,
                 show_bus_clock: bool = True, bus_clock_available: bool = True):
        super().__init__(parent)
        self._description = description or self.DEFAULT_DESC
        # Both sniffers show the SCL readout (harmonized 2026-10-05); a probe
        # that cannot measure SCL (the AD2 spy) shows "n/a" with a tooltip.
        self._show_bus_clock = show_bus_clock
        self._bus_clock_available = bus_clock_available
        self._build_ui()
        self._running = False

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ---- Sniffer controls ----
        spy_box = QGroupBox("I2C Sniffer (Passive)")
        spy_lay = QVBoxLayout(spy_box)

        desc = QLabel(self._description)
        desc.setWordWrap(True)
        desc.setObjectName("mutedLabel")
        spy_lay.addWidget(desc)

        # Start / Stop share one row at equal width
        self._start_btn = QPushButton("▶  Start Sniffing")
        self._start_btn.setObjectName("btnSpyStart")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_start)

        self._stop_btn = QPushButton("■  Stop Sniffing")
        self._stop_btn.setObjectName("btnSpyStop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)

        spy_lay.addWidget(_EqualWidthRow(self._start_btn, self._stop_btn))

        self._pec_chk = QCheckBox("Validate SMBus PEC (CRC-8)")
        self._pec_chk.stateChanged.connect(lambda s: self.pec_changed.emit(bool(s)))
        spy_lay.addWidget(self._pec_chk)

        # Status indicator, with the measured SCL clock beside it
        self._spy_status = QLabel("● Idle")
        self._set_status("status_idle", "● Idle")
        self._bus_clock_lbl = QLabel()
        self._bus_clock_lbl.setObjectName("mutedLabel")
        self._bus_clock_lbl.setToolTip(
            "SCL clock of the last transaction, measured by the probe "
            "(mean un-stretched SCL period; firmware >= 1.3)."
            if self._bus_clock_available else
            "This probe does not measure the SCL clock (the AD2 I2C spy "
            "reports bytes only).")
        self._bus_clock_lbl.setVisible(self._show_bus_clock)
        self.set_bus_hz(0)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        status_row.addWidget(self._spy_status)
        status_row.addWidget(self._bus_clock_lbl)
        status_row.addStretch(1)
        spy_lay.addLayout(status_row)

        root.addWidget(spy_box)

        # ---- Stats ----
        stats_box = QGroupBox("Capture Stats")
        stats_lay = QVBoxLayout(stats_box)

        self._captured_lbl = QLabel("Captured: 0")
        self._errors_lbl = QLabel("Spy errors: 0")
        self._visible_lbl = QLabel("Visible (filtered): 0")
        self._total_lbl = QLabel("Total in log: 0")

        for lbl in [self._captured_lbl, self._errors_lbl, self._visible_lbl, self._total_lbl]:
            lbl.setFont(QFont("Courier New", 9))
            stats_lay.addWidget(lbl)

        root.addWidget(stats_box)
        # No trailing stretch: this panel sits at the top of the Sniffer tab
        # sidebar with more Sections below it; the Sidebar owns the bottom stretch.

    # ------------------------------------------------------------------
    def _on_start(self):
        self._running = True
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._set_status("status_active", "● Sniffing")
        self.start_requested.emit()

    def _on_stop(self):
        self._running = False
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._set_status("status_idle", "● Idle")
        self.stop_requested.emit()

    def _set_status(self, token: str, text: str):
        self._spy_status.setText(text)
        c = theme.get_color(token).name()
        self._spy_status.setStyleSheet(f"color:{c}; font-weight:bold;")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def set_device_ready(self, ready: bool):
        self._start_btn.setEnabled(ready and not self._running)
        if not ready:
            self._stop_btn.setEnabled(False)
            self._set_status("status_error", "● No device")

    def set_bus_hz(self, hz: int):
        """Show the probe-measured SCL clock; 0 / None = not measured yet."""
        if not self._bus_clock_available:
            self._bus_clock_lbl.setText("SCL: n/a")
            return
        self._bus_clock_lbl.setText(f"SCL: {self.format_bus_hz(hz)}")

    @staticmethod
    def format_bus_hz(hz: int) -> str:
        if not hz:
            return "—"
        if hz < 1000:
            return f"{hz} Hz"
        return f"{hz / 1000:.1f} kHz"

    def update_stats(self, captured: int, errors: int, visible: int, total: int):
        self._captured_lbl.setText(f"Captured: {captured}")
        self._errors_lbl.setText(f"Spy errors: {errors}")
        self._visible_lbl.setText(f"Visible (filtered): {visible}")
        self._total_lbl.setText(f"Total in log: {total}")

    @property
    def pec_enabled(self) -> bool:
        return self._pec_chk.isChecked()

    @property
    def is_running(self) -> bool:
        return self._running
