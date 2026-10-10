"""
tests/test_ion_master.py — Phase 4a host side: master command encoding,
IonMasterLink against a firmware-emulating fake port, and the
record/replay-compare logic. No hardware or Qt needed (pure Python).

Run:
    python3 tests/test_ion_master.py
"""
import os
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import ion_protocol as proto  # noqa: E402
from core.ion_master import (IonMasterLink, open_master, classify,  # noqa: E402
                             RESULT_ACK, RESULT_NAK, RESULT_TIMEOUT,
                             RESULT_LINK_TIMEOUT)
from core.i2c_controller import I2CDirection, smbus_crc8  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def make_frame(ftype, payload):
    body = bytes([ftype, len(payload) & 0xFF, len(payload) >> 8]) + payload
    return bytes([proto.SYNC_DEV2HOST]) + body + bytes([proto.crc8(body)])


def make_txn_frame(t_us, addr, flags, data):
    return make_frame(proto.FRAME_TXN,
                      t_us.to_bytes(4, "little")
                      + bytes([addr, flags, len(data)]) + data)


HELLO_MASTER = make_frame(proto.FRAME_HELLO, b"NC0S" + bytes([1, 1, 0, 3]))
HELLO_SNIFFER = make_frame(proto.FRAME_HELLO, b"NC0S" + bytes([1, 1, 0, 1]))
STATUS_OK = make_frame(proto.FRAME_STATUS,
                       bytes([1, 1, 0, 3, 0]) + b"\x00" * 16)


def test_encoders():
    print("command encoders")
    f = proto.encode_i2c_write(0x08, b"\x3E")
    check(f[:3] == bytes([0xA5, 0x10, 0x02]) and f[3:5] == b"\x08\x3E",
          "I2C_WRITE layout [A5 10 len addr data]")
    body = f[1:-1]
    check(proto.crc8(body) == f[-1], "I2C_WRITE crc over cmd..payload")

    f = proto.encode_i2c_write_read(0x08, b"\x3E", 36)
    check(f[1] == 0x11 and f[2] == 4 and f[3:7] == bytes([0x08, 1, 0x3E, 36]),
          "WRITE_READ payload: addr, wlen, wdata, rlen")
    f = proto.encode_i2c_read(0x6B, 2)
    check(f[1] == 0x12 and f[3:5] == bytes([0x6B, 2]), "READ payload")
    f = proto.encode_set_bus_speed(1)
    check(f[1] == 0x13 and f[3] == 1, "SET_BUS_SPEED payload")
    try:
        proto.encode_i2c_write(0x08, bytes(65))
        check(False, "oversize write rejected")
    except ValueError:
        check(True, "oversize write rejected")


class MasterFakePort:
    """Emulates the master firmware: parses host commands with the same
    var-length framing and answers with scripted TXN frames per address."""

    def __init__(self, hello=HELLO_MASTER):
        self.rx = bytearray(hello)          # HELLO queued on PING
        self.tx = bytearray()
        self.closed = False
        self.hello = hello
        self.responses: dict[int, bytes] = {}   # addr -> read payload
        self.nak_addrs: set = set()
        self.timeout_addrs: set = set()
        self._t = 1000

    def read(self, n):
        out = bytes(self.rx[:n])
        del self.rx[:len(out)]
        return out

    def write(self, data):
        self.tx.extend(data)
        d = bytes(data)
        if d[0] != proto.SYNC_HOST2DEV:
            return len(data)
        cmd = d[1]
        if cmd == proto.CMD_PING:
            self.rx.extend(self.hello)
        elif cmd == proto.CMD_SET_BUS_SPEED:
            self.rx.extend(STATUS_OK)
        elif cmd in (proto.CMD_I2C_WRITE, proto.CMD_I2C_WRITE_READ,
                     proto.CMD_I2C_READ):
            self._exec(cmd, d[3:-1])
        return len(data)

    def _txn(self, addr, flags, data=b""):
        self._t += 500
        self.rx.extend(make_txn_frame(self._t, addr, flags, data))

    def _exec(self, cmd, payload):
        addr = payload[0] & 0x7F
        if addr in self.timeout_addrs:
            self._txn(addr, proto.FLAG_TIMEOUT | proto.FLAG_STOP)
            return
        naked = addr in self.nak_addrs
        if cmd == proto.CMD_I2C_WRITE:
            f = proto.FLAG_STOP | (proto.FLAG_NAK if naked else 0)
            self._txn(addr, f, payload[1:])
        elif cmd == proto.CMD_I2C_READ:
            rlen = payload[1]
            resp = self.responses.get(addr, bytes(rlen))[:rlen]
            f = proto.FLAG_DIR_READ | proto.FLAG_STOP
            self._txn(addr, f, resp)
        else:                                   # WRITE_READ
            wlen = payload[1]
            wdata = payload[2:2 + wlen]
            rlen = payload[2 + wlen]
            if naked:
                self._txn(addr, proto.FLAG_NAK | proto.FLAG_STOP, wdata)
                return
            self._txn(addr, 0, wdata)           # write phase, no stop
            resp = self.responses.get(addr, bytes(rlen))[:rlen]
            self._txn(addr, proto.FLAG_DIR_READ | proto.FLAG_RESTART
                      | proto.FLAG_STOP | proto.FLAG_NAK, resp)

    def close(self):
        self.closed = True


def test_master_link():
    print("IonMasterLink")
    port = MasterFakePort()
    port.responses[0x08] = bytes(range(36))
    link = IonMasterLink(port)
    check(link.handshake() and link.is_master_firmware(),
          "handshake identifies master firmware")

    txn = link.write(0x08, b"\x3E")
    check(txn.result == RESULT_ACK and txn.data == b"\x3E"
          and txn.direction == I2CDirection.WRITE, "write ACK round-trip")

    w, r = link.write_read(0x08, b"\x3E", 36)
    check(w.result == RESULT_ACK and not w.stop, "write phase (no stop)")
    check(r is not None and r.start == 2 and r.data == bytes(range(36)),
          "read phase: restart + 36 bytes")

    port.nak_addrs.add(0x55)
    txn = link.write(0x55, b"\x00")
    check(txn.result == RESULT_NAK, "NAK classified")
    w, r = link.write_read(0x55, b"\x00", 4)
    check(w.result == RESULT_NAK and r is None,
          "write_read: failed write skips the read")

    port.timeout_addrs.add(0x77)
    txn = link.write(0x77, b"\x00")
    check(txn.result == RESULT_TIMEOUT, "bus TIMEOUT flag classified")

    st = link.set_bus_speed(400)
    check(st is not None and st["mode"] == "master", "SET_BUS_SPEED acked")

    pec = link.write_with_pec(0x08, b"\x00\x12")
    expect = smbus_crc8(bytes([0x10]) + b"\x00\x12")
    check(pec.data == b"\x00\x12" + bytes([expect]), "PEC byte appended")

    check(classify(None) == RESULT_LINK_TIMEOUT, "None classifies LINK_TIMEOUT")


def test_open_master_guards():
    print("open_master guards")
    try:
        open_master("X", serial_factory=lambda n, b: MasterFakePort(HELLO_SNIFFER))
        check(False, "sniffer firmware rejected")
    except RuntimeError as e:
        check("bit-bang" in str(e) and "MASTER" in str(e),
              "sniffer firmware rejected with actionable message")

    class DeadPort(MasterFakePort):
        def write(self, data):
            return len(data)                    # never answers
    IonMasterLink.HANDSHAKE_TIMEOUT_S = 0.2
    try:
        open_master("X", serial_factory=lambda n, b: DeadPort(b""))
        check(False, "silent port rejected")
    except RuntimeError as e:
        check("no HELLO" in str(e), "silent port rejected (no HELLO)")
    IonMasterLink.HANDSHAKE_TIMEOUT_S = 2.0


def test_replay_compare_logic():
    print("replay_compare pairing + diff + mask")
    sys.path.insert(0, str(Path(ROOT) / "tools"))
    import replay_compare as rc

    rows = [
        {"t_us": 1000, "addr": 8, "dir": "W", "data": b"\x3E",
         "nak": False, "restart": False, "stop": False},
        {"t_us": 2000, "addr": 8, "dir": "R", "data": b"\x01\x02",
         "nak": True, "restart": True, "stop": True},
        {"t_us": 3000, "addr": 8, "dir": "W", "data": b"\x10\x20",
         "nak": False, "restart": False, "stop": True},
        {"t_us": 4000, "addr": 0x6B, "dir": "R", "data": b"\xAA",
         "nak": True, "restart": False, "stop": True},
    ]
    units = list(rc.pair_transactions(rows))
    check([u[0] for u in units] == ["wr", "w", "r"],
          "write+restart-read paired; plain W and R stand alone")

    diff = rc.hex_diff(b"\x01\x02\x03", b"\x01\xFF\x03", {2})
    check(diff == "01 02>FF [03]", "hex diff: match, mismatch, masked")

    with _tf.TemporaryDirectory() as d:
        p = Path(d) / "cap.jsonl"
        p.write_text("\n".join(json.dumps(
            {**r, "data": r["data"].hex().upper()}) for r in rows))
        loaded = rc.load_capture(str(p))
        check(len(loaded) == 4 and loaded[0]["data"] == b"\x3E",
              "capture JSONL round-trip")


def test_record_trigger_logic():
    print("record_on_trigger predicate")
    sys.path.insert(0, str(Path(ROOT) / "tools"))
    import record_on_trigger as rot

    trig = rot.parse_trigger("0x08:W:3E")
    check(trig == (8, False, b"\x3E"), "trigger spec parsed")

    def rec(addr, dir_read, data):
        return proto.TxnRecord(t_us=0, address=addr, dir_read=dir_read,
                               nak=False, restart=False, stop=True,
                               overflow=False, timeout=False, data=data)
    check(rot.matches(rec(0x08, False, b"\x3E"), trig), "exact match")
    check(rot.matches(rec(0x08, False, b"\x3E\x00\x01"), trig),
          "prefix match")
    check(not rot.matches(rec(0x08, True, b"\x3E"), trig), "direction gates")
    check(not rot.matches(rec(0x09, False, b"\x3E"), trig), "address gates")
    trig2 = rot.parse_trigger("0x6B:R")
    check(rot.matches(rec(0x6B, True, b"anything"), trig2),
          "no-prefix trigger matches any data")


def main():
    test_encoders()
    test_master_link()
    test_open_master_guards()
    test_replay_compare_logic()
    test_record_trigger_logic()
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
