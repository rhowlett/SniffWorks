"""
tests/test_nucleo_protocol.py — wire protocol + serial backend for the  [v0.4]
NUCLEO-C031C6 sniffer (Phase 3), no hardware required.

Covers:
  * crc8 vectors and command frames against the bytes in PROTOCOL.md
  * FrameParser: chunked feeding, garbage resync, CRC rejection,
    boot HELLO byte sequence from the spec
  * TXN decode: flags, restart/stop mapping, overflow, fw 1.3 trailing scl_hz
  * TimestampMapper: anchoring + 32-bit wrap
  * IonLink against a scripted fake port: handshake, transaction mapping
    (incl. PEC), status, device errors
  * IonWorker end-to-end with the fake port via serial_factory injection

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_nucleo_protocol.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import sys  # noqa: E402
import time  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import nucleo_protocol as proto  # noqa: E402
from core.i2c_controller import I2CDirection, smbus_crc8  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


# ---------------------------------------------------------------------------
# Frame construction helpers (host-side encoders mirroring the firmware)
# ---------------------------------------------------------------------------
def make_frame(ftype: int, payload: bytes) -> bytes:
    body = bytes([ftype, len(payload) & 0xFF, len(payload) >> 8]) + payload
    return bytes([proto.SYNC_DEV2HOST]) + body + bytes([proto.crc8(body)])


def make_txn(t_us: int, addr: int, flags: int, data: bytes) -> bytes:
    payload = (t_us.to_bytes(4, "little") + bytes([addr, flags, len(data)])
               + data)
    return make_frame(proto.FRAME_TXN, payload)


def make_status(captured=0, errors=0, dropped=0, bus_hz=0, capturing=1):
    payload = (bytes([1, 1, 0, 1, capturing])
               + captured.to_bytes(4, "little") + errors.to_bytes(4, "little")
               + dropped.to_bytes(4, "little") + bus_hz.to_bytes(4, "little"))
    return make_frame(proto.FRAME_STATUS, payload)


# Build the real boot HELLO from the spec: magic NC0S, proto 1, fw 1.0, mode 1
HELLO_BYTES = make_frame(proto.FRAME_HELLO, b"NC0S" + bytes([1, 1, 0, 1]))


def test_crc_and_commands():
    print("crc8 + commands")
    check(proto.crc8(b"") == 0x00, "crc8('') == 0")
    check(proto.crc8(bytes([0x01, 0x00])) == 0x15, "crc8(01 00) == 0x15")
    check(proto.CMD_START_BYTES == bytes([0xA5, 0x01, 0x00, 0x15]),
          "START frame bytes A5 01 00 15")
    check(proto.CMD_STOP_BYTES == bytes([0xA5, 0x02, 0x00, 0x2A]),
          "STOP frame bytes A5 02 00 2A")
    check(proto.CMD_PING_BYTES == bytes([0xA5, 0x04, 0x00, 0x54]),
          "PING frame bytes A5 04 00 54")
    check(proto.crc8 is not None and proto.crc8(b"123456789") == 0xF4,
          "crc8 check value 0xF4 for '123456789'")
    # spec's documented boot HELLO: AA 04 08 00 4E 43 30 53 01 01 00 01 BB
    check(HELLO_BYTES.hex(" ").upper() == "AA 04 08 00 4E 43 30 53 01 01 00 01 BB",
          "boot HELLO matches PROTOCOL.md byte-for-byte")


def test_frame_parser():
    print("FrameParser")
    fp = proto.FrameParser()
    txn = make_txn(1000, 0x08, proto.FLAG_STOP, b"\x3E")
    stream = b"\x00garbage\xAA\x00junk" + HELLO_BYTES + txn + make_status(5)

    # feed in 1..7-byte chunks — must produce exactly 3 frames in order
    got = []
    for size in (1, 2, 3, 5, 7):
        fp2 = proto.FrameParser()
        frames = []
        for i in range(0, len(stream), size):
            frames.extend(fp2.feed(stream[i:i + size]))
        got.append([t for t, _ in frames])
    check(all(g == [proto.FRAME_HELLO, proto.FRAME_TXN, proto.FRAME_STATUS]
              for g in got), "chunked feeding yields 3 frames in order")

    # corrupt CRC -> frame dropped, later frames still parse
    bad = bytearray(txn)
    bad[-1] ^= 0xFF
    fp3 = proto.FrameParser()
    frames = list(fp3.feed(bytes(bad) + HELLO_BYTES))
    check([t for t, _ in frames] == [proto.FRAME_HELLO],
          "bad CRC dropped, resyncs to next frame")
    check(fp3.bad_crc >= 1, "bad_crc counted")

    # stray 0xAA with implausible header must not stall the stream
    fp4 = proto.FrameParser()
    frames = list(fp4.feed(bytes([0xAA, 0xEE, 0xFF, 0xFF]) + txn))
    check([t for t, _ in frames] == [proto.FRAME_TXN],
          "implausible header skipped (no stall)")


def test_txn_decode():
    print("TXN decode")
    flags = proto.FLAG_DIR_READ | proto.FLAG_NAK | proto.FLAG_RESTART
    payload = (123456).to_bytes(4, "little") + bytes([0x08, flags, 3]) + b"\x01\x02\x03"
    rec = proto.decode_txn(payload)
    check(rec.t_us == 123456 and rec.address == 0x08, "t_us + address")
    check(rec.dir_read and rec.nak and rec.restart and not rec.stop,
          "flags decoded")
    check(rec.data == b"\x01\x02\x03", "data bytes")
    check(proto.decode_txn(b"\x00\x00") is None, "short frame rejected")
    check(not rec.framing, "framing clear when bit 6 unset")
    slipped = (0).to_bytes(4, "little") + bytes(
        [0x21, proto.FLAG_RESTART | proto.FLAG_STOP | proto.FLAG_FRAMING, 2]
    ) + b"\x00\x03"
    check(proto.decode_txn(slipped).framing, "fw 1.2 FRAMING flag decoded")

    # fw 1.3: u32 scl_hz trails the data; absent (older fw) or 0 -> None
    check(rec.scl_hz is None, "no trailing field (fw <= 1.2) -> scl_hz None")
    with_scl = payload + (400000).to_bytes(4, "little")
    r13 = proto.decode_txn(with_scl)
    check(r13.scl_hz == 400000 and r13.data == b"\x01\x02\x03",
          "trailing u32 scl_hz decoded; data still sized by dlen")
    zero = payload + (0).to_bytes(4, "little")
    check(proto.decode_txn(zero).scl_hz is None, "scl_hz 0 (not measured) -> None")
    empty = (5).to_bytes(4, "little") + bytes([0x08, proto.FLAG_NAK | proto.FLAG_STOP, 0]) \
        + (99876).to_bytes(4, "little")
    r0 = proto.decode_txn(empty)
    check(r0.data == b"" and r0.scl_hz == 99876, "0-byte phase: scl_hz at offset 7")
    short = payload + b"\x40\x0D"
    check(proto.decode_txn(short).scl_hz is None, "truncated trailing field ignored")

    # fw 1.4 STATUS diag block (PROTOCOL.md 1.2.1)
    base = bytes([1, 1, 4, 1, 1]) + (5).to_bytes(4, "little") + (2).to_bytes(4, "little") \
        + (0).to_bytes(4, "little") + (99000).to_bytes(4, "little")
    st = proto.decode_status(base)
    check(st["fw"] == "1.4" and "diag" not in st, "21-byte STATUS: no diag key")
    diag = bytes([1, 0]) + (0x00F0).to_bytes(2, "little") + (48).to_bytes(2, "little") \
        + (0xFFFF).to_bytes(2, "little") + (7).to_bytes(4, "little") + (3).to_bytes(4, "little") \
        + (0x0BB8).to_bytes(2, "little") + (24).to_bytes(2, "little") + (9).to_bytes(4, "little")
    st = proto.decode_status(base + diag)
    d = st.get("diag", {})
    check(d.get("max_gap_us") == 5.0 and d.get("min_scl_high_us") == 1.0
          and d.get("min_scl_low_us") is None, "diag: ticks -> us, 0xFFFF -> None")
    check(d.get("gaps_over_2us") == 7 and d.get("framing_phases") == 3
          and d.get("framing_max_gap_us") == 62.5 and d.get("framing_min_scl_high_us") == 0.5
          and d.get("upkeep_deferred") == 9, "diag: counters and framing-phase stats")
    check(st["bus_hz"] == 99000, "classic fields unchanged with diag present")


def test_timestamp_mapper():
    print("TimestampMapper")
    tm = proto.TimestampMapper()
    w0 = tm.to_wall(1_000_000, 100.0)
    check(w0 == 100.0, "first sample anchors to wall time")
    w1 = tm.to_wall(1_500_000, 105.0)
    check(abs(w1 - 100.5) < 1e-9, "delta follows device clock, not host")
    # wrap: near top of 32-bit range, then a small value
    tm2 = proto.TimestampMapper()
    tm2.to_wall(proto.T_US_WRAP - 1000, 0.0)
    w = tm2.to_wall(500, 999.0)
    check(abs(w - (1500 / 1e6)) < 1e-6, "32-bit wrap handled monotonically")


# ---------------------------------------------------------------------------
# Fake serial port: scripted RX, records TX
# ---------------------------------------------------------------------------
class FakePort:
    def __init__(self):
        self.rx = bytearray()       # bytes the device "sends" to the host
        self.tx = bytearray()       # bytes the host wrote
        self.closed = False
        self.timeout = 0
        self.auto = {}              # command byte -> bytes to queue on write

    def queue(self, data: bytes):
        self.rx.extend(data)

    def read(self, n: int) -> bytes:
        out = bytes(self.rx[:n])
        del self.rx[:len(out)]
        return out

    def write(self, data: bytes):
        self.tx.extend(data)
        if len(data) >= 2 and data[0] == proto.SYNC_HOST2DEV:
            resp = self.auto.get(data[1])
            if resp:
                self.rx.extend(resp)
        return len(data)

    def close(self):
        self.closed = True


def test_nucleo_link():
    print("IonLink (fake port)")
    from core.ion_backend import IonLink

    port = FakePort()
    port.auto[proto.CMD_PING] = HELLO_BYTES
    link = IonLink(port, check_pec=False)
    txns, errs, stats = [], [], []
    link.on_transaction = txns.append
    link.on_error = errs.append
    link.on_status = stats.append

    check(link.handshake(), "handshake gets HELLO")
    check(link.hello == {"proto": 1, "fw": "1.0", "mode": "bit-bang"},
          "HELLO decoded")

    link.start_capture()
    check(bytes(port.tx).endswith(proto.CMD_START_BYTES), "START sent")

    # write phase then restart-read phase (the BQ76905 trigger shape)
    port.queue(make_txn(1000, 0x08, proto.FLAG_STOP * 0, b"\x3E"))
    port.queue(make_txn(2000, 0x08,
                        proto.FLAG_DIR_READ | proto.FLAG_RESTART |
                        proto.FLAG_NAK | proto.FLAG_STOP,
                        b"\x02\x00\x76\x05"))
    link.pump()
    check(len(txns) == 2, "two transactions relayed")
    w, r = txns
    check(w.address == 0x08 and w.direction == I2CDirection.WRITE
          and w.data == b"\x3E" and w.start == 1 and not w.stop,
          "write phase mapped (start=1, no stop)")
    check(r.direction == I2CDirection.READ and r.start == 2 and r.stop
          and r.nak, "restart-read phase mapped (start=2, stop, NAK)")
    check(abs((r.timestamp - w.timestamp) - 0.001) < 1e-6,
          "timestamps preserve the device 1 ms gap")
    check(w.scl_hz is None, "fw <= 1.2 frame -> I2CTransaction.scl_hz None")

    # fw 1.3 frame: scl_hz flows through to the transaction
    port.queue(make_frame(proto.FRAME_TXN, (2500).to_bytes(4, "little")
                          + bytes([0x6B, proto.FLAG_STOP, 1]) + b"\x3E"
                          + (100123).to_bytes(4, "little")))
    link.pump()
    check(txns[-1].scl_hz == 100123 and txns[-1].data == b"\x3E",
          "fw 1.3 scl_hz relayed to I2CTransaction")

    # PEC: valid then corrupted
    link.check_pec = True
    addr_byte = (0x08 << 1) | 1
    data = b"\x11\x22"
    good = data + bytes([smbus_crc8(bytes([addr_byte]) + data)])
    port.queue(make_txn(3000, 0x08,
                        proto.FLAG_DIR_READ | proto.FLAG_STOP, good))
    bad = data + bytes([smbus_crc8(bytes([addr_byte]) + data) ^ 0xFF])
    port.queue(make_txn(4000, 0x08,
                        proto.FLAG_DIR_READ | proto.FLAG_STOP, bad))
    link.pump()
    check(txns[-2].pec_valid is True, "PEC valid detected")
    check(txns[-1].pec_valid is False, "PEC failure detected")

    # status + device error
    port.queue(make_status(captured=99, errors=1, dropped=0, bus_hz=100000))
    port.queue(make_frame(proto.FRAME_ERROR, bytes([1, 0])))
    link.pump()
    check(stats and stats[-1]["captured"] == 99 and
          stats[-1]["bus_hz"] == 100000, "STATUS decoded to callback")
    check(errs and "overflow" in errs[-1], "device ERROR relayed as text")


def test_nucleo_worker(app):
    print("IonWorker (QThread, fake port)")
    from core.ion_backend import IonWorker

    port = FakePort()
    port.auto[proto.CMD_PING] = HELLO_BYTES
    port.auto[proto.CMD_START] = (
        make_txn(1000, 0x40, proto.FLAG_STOP, b"\xAB") +
        make_txn(2000, 0x40, proto.FLAG_DIR_READ | proto.FLAG_STOP, b"\xCD"))

    worker = IonWorker("FAKE", 115200,
                          serial_factory=lambda name, baud: port)
    got_txn, got_conn, got_disc = [], [], []
    worker.transaction_captured.connect(got_txn.append)
    worker.connected.connect(got_conn.append)
    worker.disconnected.connect(lambda: got_disc.append(1))

    worker.start()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and len(got_txn) < 2:
        app.processEvents()
        time.sleep(0.01)
    worker.stop()
    worker.wait(3000)
    app.processEvents()

    check(got_conn and got_conn[0].get("fw") == "1.0",
          "connected(hello) emitted")
    check(len(got_txn) == 2 and got_txn[0].address == 0x40,
          "transactions delivered via Qt signals")
    check(bytes(port.tx).count(proto.CMD_STOP_BYTES) >= 1,
          "STOP sent on shutdown")
    check(port.closed, "port closed on shutdown")
    check(got_disc == [1], "disconnected emitted")

    # failed handshake path
    quiet = FakePort()
    errors = []
    w2 = IonWorker("FAKE", 115200,
                      serial_factory=lambda name, baud: quiet)
    w2.HANDSHAKE = 0  # not used; IonLink owns the timeout
    w2.error_occurred.connect(errors.append)
    from core import nucleo_backend
    nucleo_backend.IonLink.HANDSHAKE_TIMEOUT_S = 0.2   # speed up test
    w2.start(); w2.wait(4000); app.processEvents()
    nucleo_backend.IonLink.HANDSHAKE_TIMEOUT_S = 2.0
    check(errors and "no HELLO" in errors[0], "silent port reports no HELLO")


def test_window_integration(app):
    print("SnifferIonWindow (offscreen, fake port)")
    from ui.sniffer_ion_window import SnifferIonWindow
    from core import nucleo_backend

    win = SnifferIonWindow()
    win.show()
    app.processEvents()
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    check(labels == ["Device", "Sniffer", "Preferences", "Help", "Exit"],
          f"tab layout {labels}")
    check(win._device_panel.current_baud() == 115200,
          "baud default 115200 on the Device tab")
    from ui.widgets.serial_prefs_section import SerialPrefsSection
    check(not win._preferences.findChildren(SerialPrefsSection),
          "Serial baud no longer duplicated in Preferences")
    from ui.widgets.connection_section import ConnectionSection
    check(len(win._device_panel.findChildren(ConnectionSection)) == 1,
          "Device tab uses the shared ConnectionSection (same as the AD2)")
    conn = win._device_panel.findChildren(ConnectionSection)[0]
    widths = {b.width() for b in (conn._refresh_btn, conn._connect_btn,
                                  conn._disconnect_btn)}
    check(len(widths) == 1 and max(widths) < 300 and
          all(not b.icon().isNull() for b in (conn._refresh_btn, conn._connect_btn,
                                              conn._disconnect_btn)),
          f"Refresh/Connect/Disconnect: compact, equal width, with icons ({widths})")

    # simulate: pick a fake port, connect, start sniffing with injected serial
    port = FakePort()
    port.auto[proto.CMD_PING] = HELLO_BYTES
    port.auto[proto.CMD_START] = (
        make_txn(1000, 0x08, 0, b"\x3E") +
        make_txn(2000, 0x08, proto.FLAG_DIR_READ | proto.FLAG_RESTART |
                 proto.FLAG_STOP, b"\x02\x00") +
        make_status(captured=2, bus_hz=47619))

    win._device_panel.populate_ports(
        [{"device": "FAKE0", "description": "test", "is_stlink": True}])
    win._on_connect("FAKE0")
    check(win._sniffer_panel._start_btn.isEnabled(),
          "connect arms Start Sniffing")
    sp = win._sniffer_panel
    win.tabs.setCurrentIndex(1)
    app.processEvents()
    start_g, stop_g = sp._start_btn.geometry(), sp._stop_btn.geometry()
    check(start_g.y() == stop_g.y() and start_g.x() < stop_g.x(),
          "Start/Stop Sniffing share one row")
    check(start_g.width() == stop_g.width(),
          f"Start/Stop equal width ({start_g.width()} vs {stop_g.width()})")
    check(sp._bus_clock_lbl.isVisible() and
          sp._bus_clock_lbl.text() == "SCL: —",
          "SCL clock readout shown, unmeasured before capture")
    check(sp._bus_clock_lbl.geometry().y() == sp._spy_status.geometry().y()
          and sp._bus_clock_lbl.x() > sp._spy_status.x(),
          "SCL readout sits beside the Idle/Sniffing indicator")

    orig_factory = nucleo_backend.IonWorker._default_factory
    nucleo_backend.IonWorker._default_factory = staticmethod(
        lambda name, baud: port)
    try:
        win._on_spy_start()
        deadline = time.monotonic() + 3.0
        while (time.monotonic() < deadline
               and win._log_panel.model.total_count < 2):
            app.processEvents()
            time.sleep(0.01)
        win._on_spy_stop()
        app.processEvents()
    finally:
        nucleo_backend.IonWorker._default_factory = orig_factory

    check(win._log_panel.model.total_count == 2,
          "transactions landed in the log model")
    check(sp._bus_clock_lbl.text() == "SCL: 47.6 kHz",
          f"STATUS bus_hz shown next to indicator "
          f"({sp._bus_clock_lbl.text()!r})")
    check(win._device_panel._fw_lbl.text() == proto.decode_hello(HELLO_BYTES[4:-1])["fw"],
          f"Probe group shows the HELLO firmware ({win._device_panel._fw_lbl.text()!r})")
    # close guard: rows present -> guard message
    check(win.close_guard() is not None, "close guard warns on unexported rows")
    win._log_panel.clear_log()
    check(win.close_guard() is None, "close guard clear after log cleared")
    win.close()
    app.processEvents()


def main():
    from ui.common import build_application
    app = build_application(app_name="nucleo-proto-tests",
                            initial_theme="default")
    test_crc_and_commands()
    test_frame_parser()
    test_txn_decode()
    test_timestamp_mapper()
    test_nucleo_link()
    test_nucleo_worker(app)
    test_window_integration(app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
