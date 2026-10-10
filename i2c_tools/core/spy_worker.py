"""
spy_worker.py
QThread-based background worker that polls FDwfDigitalI2cSpyStatus
and emits captured transactions to the main thread.
"""

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import time

from core.i2c_controller import I2CController, I2CTransaction


class SpyWorker(QThread):
    """
    Runs in a background thread.
    Polls I2C spy status at ~1 ms intervals.
    Emits transaction_captured for each new transaction found.
    Emits error_occurred on DWF errors.
    Emits stats_updated periodically with (captured_count, error_count).
    """

    transaction_captured = Signal(object)   # I2CTransaction
    error_occurred = Signal(str)
    stats_updated = Signal(int, int)        # captured, errors

    POLL_INTERVAL_S = 0.001    # 1 ms polling

    def __init__(self, controller: I2CController, check_pec: bool = False, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._check_pec = check_pec
        self._stop_flag = False
        self._mutex = QMutex()
        self._captured = 0
        self._errors = 0
        self._last_err_msg = ""

    def stop(self):
        with QMutexLocker(self._mutex):
            self._stop_flag = True

    def set_check_pec(self, enabled: bool):
        self._check_pec = enabled

    def run(self):
        self._stop_flag = False
        self._captured = 0
        self._errors = 0
        self._last_err_msg = ""
        last_stats = time.monotonic()

        while True:
            with QMutexLocker(self._mutex):
                if self._stop_flag:
                    break

            try:
                has_data, txn, err = self._controller.spy_poll(self._check_pec)
            except Exception as e:
                self._errors += 1
                self.error_occurred.emit(f"Spy poll exception: {e}")
                time.sleep(0.1)
                continue

            if err:
                self._errors += 1
                # Overflow *warnings* are transient under heavy bus load — don't
                # hammer the UI or back off as hard as for real protocol errors.
                is_warning = "warning" in err.lower()
                if err != self._last_err_msg or not is_warning:
                    self.error_occurred.emit(err)
                    self._last_err_msg = err
                time.sleep(0.005 if is_warning else 0.05)
                continue

            if has_data and txn is not None:
                self._captured += 1
                self.transaction_captured.emit(txn)
            else:
                # Back off slightly when idle to reduce CPU
                time.sleep(self.POLL_INTERVAL_S)

            # Emit stats every second
            now = time.monotonic()
            if now - last_stats >= 1.0:
                self.stats_updated.emit(self._captured, self._errors)
                last_stats = now
