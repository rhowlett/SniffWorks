"""
core/ion_backend.py  [v0.2]
Serial backend for the NUCLEO-C031C6 sniffer: turns the firmware's framed
UART stream into I2CTransaction objects with the same signal surface the AD2
SpyWorker exposed (transaction_captured / error_occurred / stats_updated), so
the GUI's log path is backend-agnostic.

Split in two for testability:
  * IonLink   — the protocol logic against any serial-like object
                   (duck-typed: read/write/close + .timeout). Pure logic,
                   fully tested with a fake port, no hardware needed.
  * IonWorker — a QThread that owns a real pyserial port and pumps
                   IonLink, relaying its callbacks as Qt signals.

I2CTransaction mapping (mirrors the AD2 spy path in i2c_controller):
  * one TXN frame = one address phase; restart flag -> start=2
  * PEC (optional): last data byte checked as SMBus PEC over
    [addr_byte + preceding data], exactly as spy_poll did.
  * timestamp: device microsecond clock anchored to wall time on the first
    frame (core.ion_protocol.TimestampMapper), so inter-transaction
    spacing is device-accurate.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

from core.i2c_controller import I2CTransaction, I2CDirection, smbus_crc8
from core import nucleo_protocol as proto

ST_LINK_VID = 0x0483        # STMicroelectronics (ST-LINK VCP) - Nucleo board
# Generic USB-UART bridge VIDs - candidates for the standalone ion board
# (final bridge part TBD). [XREF: board-select]
BRIDGE_VIDS = {0x0403: "FTDI", 0x10C4: "CP210x", 0x1A86: "CH340",
               0x067B: "PL2303"}


# ---------------------------------------------------------------------------
# Port discovery
# ---------------------------------------------------------------------------
def list_serial_ports() -> list[dict]:
    """Enumerate serial ports. Each entry: {device, description, is_stlink,
    hint, serial, key, name}. serial/key/name come from core.device_names
    (USB serial number identity; name = the per-user device name, "" if
    unnamed). ST-LINK virtual COM ports (the Nucleo's UART bridge) sort first."""
    from core.device_names import DeviceNames, device_key, normalize_serial
    names = DeviceNames()
    from serial.tools import list_ports
    ports = []
    for p in list_ports.comports():
        bridge = BRIDGE_VIDS.get(p.vid or 0)
        ports.append({
            "device": p.device,
            "description": p.description or "",
            "is_stlink": (p.vid == ST_LINK_VID),
            "hint": ("Nucleo (ST-LINK)" if p.vid == ST_LINK_VID
                     else f"USB-UART bridge ({bridge})" if bridge else ""),
            "serial": normalize_serial(p.serial_number),
            "key": (device_key(p.serial_number, p.vid, p.pid,
                               getattr(p, "location", "")) if p.vid is not None else ""),
        })
        ports[-1]["name"] = names.name_for(ports[-1]["key"]) if ports[-1]["key"] else ""
    # named devices first, then probable probes: ST-LINK (Nucleo), then known
    # bridges (ion)
    ports.sort(key=lambda e: (not e["name"], not e["is_stlink"], not e["hint"],
                              e["device"]))
    return ports


# ---------------------------------------------------------------------------
# Protocol driver (hardware-independent)
# ---------------------------------------------------------------------------
class IonLink:
    """Drives the sniffer protocol over a serial-like object.

    Callbacks (set any subset):
        on_transaction(I2CTransaction)
        on_status(dict)         decoded STATUS frame
        on_error(str)           device ERROR frames and link problems
        on_hello(dict)          decoded HELLO frame
    """

    HANDSHAKE_TIMEOUT_S = 2.0

    def __init__(self, port, check_pec: bool = False):
        self._port = port
        self._parser = proto.FrameParser()
        self._tsmap = proto.TimestampMapper()
        self.check_pec = check_pec
        self.hello: dict | None = None
        self.last_status: dict | None = None
        self.captured = 0           # host-side count of relayed transactions
        self.device_errors = 0
        self.on_transaction = None
        self.on_status = None
        self.on_error = None
        self.on_hello = None

    # -- session ---------------------------------------------------------
    def handshake(self) -> bool:
        """PING and wait for a HELLO. Returns True when the device answers."""
        self._port.write(proto.CMD_PING_BYTES)
        deadline = time.monotonic() + self.HANDSHAKE_TIMEOUT_S
        while time.monotonic() < deadline:
            self.pump()
            if self.hello is not None:
                return True
            time.sleep(0.01)
        return False

    def start_capture(self):
        self._port.write(proto.CMD_START_BYTES)

    def stop_capture(self):
        self._port.write(proto.CMD_STOP_BYTES)

    def request_status(self):
        self._port.write(proto.CMD_STATUS_REQ_BYTES)

    # -- pump ------------------------------------------------------------
    def pump(self) -> int:
        """Read whatever is available and dispatch frames. Returns the number
        of frames handled (0 when the port was quiet)."""
        try:
            data = self._port.read(4096)
        except Exception as e:                      # port vanished mid-read
            self._emit_error(f"serial read failed: {e}")
            raise
        if not data:
            return 0
        n = 0
        for ftype, payload in self._parser.feed(data):
            n += 1
            if ftype == proto.FRAME_TXN:
                self._handle_txn(payload)
            elif ftype == proto.FRAME_STATUS:
                self.last_status = proto.decode_status(payload)
                if self.last_status and self.on_status:
                    self.on_status(self.last_status)
            elif ftype == proto.FRAME_ERROR:
                err = proto.decode_error(payload)
                self.device_errors += 1
                self._emit_error(f"device: {err['text']} (detail={err['detail']})")
            elif ftype == proto.FRAME_HELLO:
                self.hello = proto.decode_hello(payload)
                if self.hello and self.on_hello:
                    self.on_hello(self.hello)
        return n

    # -- mapping ---------------------------------------------------------
    def _handle_txn(self, payload: bytes):
        rec = proto.decode_txn(payload)
        if rec is None:
            self._emit_error("short TXN frame")
            return
        if rec.overflow:
            self._emit_error("device decoder overflow — transactions dropped")
        if rec.framing:
            self._emit_error(
                f"framing error at 0x{rec.address:02X}: a bus edge was lost, "
                f"this phase's bytes are bit-slipped")

        addr_byte = (rec.address << 1) | (1 if rec.dir_read else 0)
        pec_valid = None
        if self.check_pec and len(rec.data) >= 1:
            payload_bytes = rec.data[:-1]
            expected = smbus_crc8(bytes([addr_byte]) + payload_bytes)
            pec_valid = (rec.data[-1] == expected)

        txn = I2CTransaction(
            timestamp=self._tsmap.to_wall(rec.t_us, time.time()),
            address=rec.address,
            direction=I2CDirection.READ if rec.dir_read else I2CDirection.WRITE,
            data=rec.data,
            nak=rec.nak,
            start=2 if rec.restart else 1,
            stop=rec.stop,
            pec_valid=pec_valid,
            raw_frame=payload,
            scl_hz=rec.scl_hz,
        )
        self.captured += 1
        if self.on_transaction:
            self.on_transaction(txn)

    def _emit_error(self, msg: str):
        if self.on_error:
            self.on_error(msg)


# ---------------------------------------------------------------------------
# Qt worker thread (owns the real serial port)
# ---------------------------------------------------------------------------
class IonWorker(QThread):
    """Background reader for the Nucleo sniffer.

    Signal-compatible with the AD2 SpyWorker plus device-status extras:
        transaction_captured(object)   I2CTransaction
        error_occurred(str)
        stats_updated(int, int)        captured, errors
        device_status(dict)            decoded STATUS (bus_hz, dropped, ...)
        connected(dict) / disconnected()
    """

    transaction_captured = Signal(object)
    error_occurred = Signal(str)
    stats_updated = Signal(int, int)
    device_status = Signal(dict)
    connected = Signal(dict)
    disconnected = Signal()

    STATUS_PERIOD_S = 1.0
    IDLE_SLEEP_S = 0.002

    def __init__(self, port_name: str, baud: int = 115200,
                 check_pec: bool = False, parent=None,
                 serial_factory=None):
        super().__init__(parent)
        self._port_name = port_name
        self._baud = baud
        self._check_pec = check_pec
        self._serial_factory = serial_factory or self._default_factory
        self._stop_flag = False
        self._mutex = QMutex()
        self._link: IonLink | None = None

    @staticmethod
    def _default_factory(port_name: str, baud: int):
        import serial
        return serial.Serial(port_name, baudrate=baud, timeout=0)

    def stop(self):
        with QMutexLocker(self._mutex):
            self._stop_flag = True

    def set_check_pec(self, enabled: bool):
        self._check_pec = enabled
        if self._link:
            self._link.check_pec = enabled

    def run(self):
        self._stop_flag = False
        try:
            port = self._serial_factory(self._port_name, self._baud)
        except Exception as e:
            self.error_occurred.emit(
                f"could not open {self._port_name} @ {self._baud}: {e}")
            return

        link = IonLink(port, check_pec=self._check_pec)
        self._link = link
        link.on_transaction = self.transaction_captured.emit
        link.on_error = self._on_link_error
        link.on_status = self._on_link_status

        try:
            if not link.handshake():
                self.error_occurred.emit(
                    f"no HELLO from {self._port_name} — is the sniffer "
                    f"firmware flashed and the baud rate correct?")
                return
            self.connected.emit(link.hello or {})
            link.start_capture()

            last_status = time.monotonic()
            while True:
                with QMutexLocker(self._mutex):
                    if self._stop_flag:
                        break
                try:
                    n = link.pump()
                except Exception:
                    break                               # read error already emitted
                now = time.monotonic()
                if now - last_status >= self.STATUS_PERIOD_S:
                    last_status = now
                    try:
                        link.request_status()
                    except Exception as e:
                        self.error_occurred.emit(f"serial write failed: {e}")
                        break
                if n == 0:
                    time.sleep(self.IDLE_SLEEP_S)

            try:
                link.stop_capture()
                # drain briefly so the final frames land in the log
                deadline = time.monotonic() + 0.2
                while time.monotonic() < deadline and link.pump():
                    pass
            except Exception:
                pass
        finally:
            self._link = None
            try:
                port.close()
            except Exception:
                pass
            self.disconnected.emit()

    # -- link callbacks (worker thread) -----------------------------------
    def _on_link_error(self, msg: str):
        self.error_occurred.emit(msg)
        if self._link:
            self.stats_updated.emit(self._link.captured, self._link.device_errors)

    def _on_link_status(self, status: dict):
        self.device_status.emit(status)
        self.stats_updated.emit(status.get("captured", 0),
                                status.get("errors", 0))
