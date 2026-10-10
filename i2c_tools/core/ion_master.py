"""
core/ion_master.py
[XREF: ion-master] Host driver for the SNIFF_MODE_MASTER firmware variant:
issue I2C transactions on the target bus and get the result back as the same
I2CTransaction records the sniffer produces — so the log/decode/export stack
handles replayed and programmed traffic without knowing the difference.

Synchronous by design: replay/compare and step sequences are inherently
serial (send, wait for the TXN reply, decide, repeat), so a blocking
send-and-wait API on the caller's thread is the honest shape. GUI apps run
it inside a worker thread exactly like IonWorker.

Result classification per transaction (RESULT_*): ACK, NAK, TIMEOUT
(firmware transfer budget exceeded — TXN_FLAG_TIMEOUT), or LINK_TIMEOUT
(the probe itself did not reply — unplugged, wrong port/baud, or wrong
firmware variant).
"""
from __future__ import annotations

import time

from core.i2c_controller import I2CTransaction, I2CDirection, smbus_crc8
from core import ion_protocol as proto

RESULT_ACK = "ACK"
RESULT_NAK = "NAK"
RESULT_TIMEOUT = "TIMEOUT"           # bus-level (firmware reported)
RESULT_LINK_TIMEOUT = "LINK_TIMEOUT"  # probe never answered


def classify(txn: I2CTransaction | None) -> str:
    if txn is None:
        return RESULT_LINK_TIMEOUT
    if getattr(txn, "timeout", False):
        return RESULT_TIMEOUT
    return RESULT_NAK if txn.nak else RESULT_ACK


class IonMasterLink:
    """Drives the master firmware over a serial-like object (duck-typed
    read/write/close — the same contract as IonLink, same FakePort tests).

    Every bus phase the firmware reports arrives as an I2CTransaction with
    an extra ``timeout`` attribute; ``result`` (RESULT_*) is stamped on too.
    """

    REPLY_TIMEOUT_S = 1.0            # generous vs the 25 ms firmware budget
    HANDSHAKE_TIMEOUT_S = 2.0

    def __init__(self, port):
        self._port = port
        self._parser = proto.FrameParser()
        self._tsmap = proto.TimestampMapper()
        self._pending: list[I2CTransaction] = []
        self.hello: dict | None = None
        self.last_status: dict | None = None
        self.on_error = None            # optional: device ERROR frames

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    def handshake(self) -> bool:
        """PING → HELLO. Also verifies the firmware is the master variant."""
        self._port.write(proto.CMD_PING_BYTES)
        deadline = time.monotonic() + self.HANDSHAKE_TIMEOUT_S
        while time.monotonic() < deadline:
            self._pump()
            if self.hello is not None:
                return True
            time.sleep(0.005)
        return False

    def is_master_firmware(self) -> bool:
        return bool(self.hello) and self.hello.get("mode") == "master"

    def set_bus_speed(self, khz: int) -> dict | None:
        """khz: 100 or 400. Returns the STATUS ack (None on link timeout)."""
        self._port.write(proto.encode_set_bus_speed(0 if khz == 100 else 1))
        return self._wait_status()

    # ------------------------------------------------------------------
    # Transactions (blocking send-and-wait)
    # ------------------------------------------------------------------
    def write(self, addr7: int, data: bytes) -> I2CTransaction | None:
        self._port.write(proto.encode_i2c_write(addr7, data))
        phases = self._wait_txns(1)
        return phases[0] if phases else None

    def read(self, addr7: int, rlen: int) -> I2CTransaction | None:
        self._port.write(proto.encode_i2c_read(addr7, rlen))
        phases = self._wait_txns(1)
        return phases[0] if phases else None

    def write_read(self, addr7: int, wdata: bytes,
                   rlen: int) -> tuple[I2CTransaction | None,
                                       I2CTransaction | None]:
        """Pointer write + repeated-start read. Returns (write_phase,
        read_phase); read_phase is None if the write phase failed (the
        firmware skips the read) or the link timed out."""
        self._port.write(proto.encode_i2c_write_read(addr7, wdata, rlen))
        phases = self._wait_txns(1)
        if not phases:
            return None, None
        wtxn = phases[0]
        if wtxn.result != RESULT_ACK:
            return wtxn, None
        phases = self._wait_txns(1)
        return wtxn, (phases[0] if phases else None)

    def write_with_pec(self, addr7: int, data: bytes) -> I2CTransaction | None:
        """SMBus write with the PEC byte appended (addr_byte + data)."""
        pec = smbus_crc8(bytes([(addr7 << 1) | 0]) + bytes(data))
        return self.write(addr7, bytes(data) + bytes([pec]))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _pump(self):
        data = self._port.read(4096)
        if not data:
            return
        for ftype, payload in self._parser.feed(data):
            if ftype == proto.FRAME_TXN:
                txn = self._map_txn(payload)
                if txn is not None:
                    self._pending.append(txn)
            elif ftype == proto.FRAME_STATUS:
                self.last_status = proto.decode_status(payload)
            elif ftype == proto.FRAME_HELLO:
                self.hello = proto.decode_hello(payload)
            elif ftype == proto.FRAME_ERROR:
                err = proto.decode_error(payload)
                if self.on_error:
                    self.on_error(err["text"])

    def _wait_txns(self, n: int) -> list[I2CTransaction]:
        deadline = time.monotonic() + self.REPLY_TIMEOUT_S
        while len(self._pending) < n and time.monotonic() < deadline:
            self._pump()
            if len(self._pending) < n:
                time.sleep(0.001)
        out, self._pending = self._pending[:n], self._pending[n:]
        return out

    def _wait_status(self) -> dict | None:
        self.last_status = None
        deadline = time.monotonic() + self.REPLY_TIMEOUT_S
        while self.last_status is None and time.monotonic() < deadline:
            self._pump()
            time.sleep(0.001)
        return self.last_status

    def _map_txn(self, payload: bytes) -> I2CTransaction | None:
        rec = proto.decode_txn(payload)
        if rec is None:
            return None
        txn = I2CTransaction(
            timestamp=self._tsmap.to_wall(rec.t_us, time.time()),
            address=rec.address,
            direction=(I2CDirection.READ if rec.dir_read
                       else I2CDirection.WRITE),
            data=rec.data,
            nak=rec.nak,
            start=2 if rec.restart else 1,
            stop=rec.stop,
            raw_frame=payload,
        )
        txn.timeout = rec.timeout
        txn.result = classify(txn)
        return txn


def open_master(port_name: str, baud: int = 115200,
                serial_factory=None) -> IonMasterLink:
    """Open a serial port and handshake with the master firmware.
    Raises RuntimeError with a bench-actionable message on failure."""
    if serial_factory is None:
        import serial
        port = serial.Serial(port_name, baudrate=baud, timeout=0)
    else:
        port = serial_factory(port_name, baud)
    link = IonMasterLink(port)
    if not link.handshake():
        port.close()
        raise RuntimeError(
            f"no HELLO from {port_name} @ {baud} — is the probe connected "
            f"and flashed?")
    if not link.is_master_firmware():
        mode = (link.hello or {}).get("mode", "?")
        port.close()
        raise RuntimeError(
            f"probe on {port_name} runs the '{mode}' firmware — flash the "
            f"SNIFF_MODE_MASTER variant for replay/programming.")
    return link
