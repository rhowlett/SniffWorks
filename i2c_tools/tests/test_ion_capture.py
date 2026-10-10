#!/usr/bin/env python3
# [v0.2]
"""
tests/test_ion_capture.py - tools/ion_capture.py without hardware: a fake
probe speaks the real frame protocol (HELLO, TXN with fw 1.3 scl_hz, STATUS
with the fw 1.4 diag block). Checks count + filters, PEC flag, framing count,
STATUS/diag reporting, and that the CSV is capture CSV v2 (validator strict)
with the Decode column filled by --decoder.
"""
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from core import ion_protocol as proto  # noqa: E402
from core.i2c_controller import smbus_crc8  # noqa: E402
import ion_capture  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def frame(ftype, payload):
    body = bytes([ftype, len(payload) & 0xFF, len(payload) >> 8]) + payload
    return bytes([proto.SYNC_DEV2HOST]) + body + bytes([proto.crc8(body)])


def txn(t_us, addr, flags, data, scl=100000):
    return frame(proto.FRAME_TXN, t_us.to_bytes(4, "little") + bytes([addr, flags, len(data)])
                 + data + scl.to_bytes(4, "little"))


class FakeProbe:
    def __init__(self, frames):
        self.frames, self.rx = frames, b""

    def write(self, b):
        if b == proto.CMD_PING_BYTES:
            self.rx += frame(proto.FRAME_HELLO, b"NC0S" + bytes([1, 1, 4, 1]))
        elif b == proto.CMD_START_BYTES:
            self.rx += b"".join(self.frames)
        elif b == proto.CMD_STATUS_REQ_BYTES:
            st = bytes([1, 1, 4, 1, 0]) + (8).to_bytes(4, "little") + (1).to_bytes(4, "little") \
                + (0).to_bytes(4, "little") + (99415).to_bytes(4, "little")
            diag = bytes([1, 0]) + (240).to_bytes(2, "little") + (96).to_bytes(2, "little") \
                + (192).to_bytes(2, "little") + (4).to_bytes(4, "little") + (1).to_bytes(4, "little") \
                + (3000).to_bytes(2, "little") + (24).to_bytes(2, "little") + (12).to_bytes(4, "little")
            self.rx += frame(proto.FRAME_STATUS, st + diag)

    def read(self, n):
        out, self.rx = self.rx[:n], self.rx[n:]
        return out


R, S, RS, NAK = proto.FLAG_DIR_READ, proto.FLAG_STOP, proto.FLAG_RESTART, proto.FLAG_NAK
addr_r = (0x6B << 1) | 1
pec_ok = bytes([0x08, 0xA0]) + bytes([smbus_crc8(bytes([addr_r, 0x08, 0xA0]))])
FRAMES = [
    txn(10, 0x6B, 0, b"\x02"),                       # W 6B [02]
    txn(20, 0x6B, R | RS | S | NAK, b"\x02\xA0"),    # Sr R 6B [02 A0]
    txn(30, 0x55, 0, b"\x02"),
    txn(40, 0x55, R | RS | S | NAK, b"\x02\xB0"),
    txn(50, 0x08, NAK | S, b""),                     # address NAK
    txn(60, 0x6B, R | S | NAK, pec_ok),              # read with a (per-phase) valid PEC
    txn(70, 0x6B, R | RS | S | NAK | proto.FLAG_FRAMING, b"\x0C\x41"),
    txn(80, 0x6B, R | RS | S | NAK, b"\x04\xA0"),
]


def cap(**kw):
    clock = iter(range(0, 10 ** 6))           # fake monotonic clock: 1 s per call
    return ion_capture.run_capture(FakeProbe(list(FRAMES)), log=lambda *_: None,
                                   clock=lambda: next(clock) * 0.001, sleep=lambda s: None, **kw)


def main():
    print("ion_capture")
    r = cap(seconds=5.0, count=None)
    check(r.seen == 8 and len(r.kept) == 8, f"no filter: all 8 kept ({r.seen} seen)")
    check(r.framing == 1, "FRAMING-flagged phase counted")
    check(r.hello["fw"] == "1.4", "HELLO fw 1.4")
    d = (r.status or {}).get("diag", {})
    check(d.get("max_gap_us") == 5.0 and d.get("framing_phases") == 1
          and d.get("framing_min_scl_high_us") == 0.5, "final STATUS carries the diag block")
    txt = ion_capture.format_status(r.status)
    check("longest sample gap   5.0 us" in txt and "narrowest SCL high   2.0 us" in txt,
          "status print shows the diag lines")

    f = ion_capture.TxnFilter(addrs={0x6B}, direction="R")
    r = cap(seconds=5.0, count=2, keep=f)
    check([t.data for t in r.kept] == [b"\x02\xA0", pec_ok], "--addr 0x6B --dir R --count 2: first two 6B reads")
    check(r.stopped_by == "count 2", "stopped by count")
    r = cap(seconds=5.0, count=None, keep=ion_capture.TxnFilter(nak="none"))
    check(all(not t.nak for t in r.kept) and [t.address for t in r.kept] == [0x6B, 0x55],
          "--nak none keeps the 2 ACK-ended writes (0x6B, 0x55)")
    r = cap(seconds=5.0, count=None, keep=ion_capture.TxnFilter(exclude={0x08}, min_len=2))
    check(len(r.kept) == 5 and all(len(t.data) >= 2 for t in r.kept), "--exclude-addr 0x08 --min-len 2")
    r = cap(seconds=5.0, count=None, check_pec=True)
    check(r.kept[5].pec_valid is True and r.kept[1].pec_valid is False, "--pec flags PEC per phase (GUI behaviour)")

    out = os.path.join(tempfile.mkdtemp(), "cap.csv")
    ok, msg = ion_capture.export_csv(r.kept, out, [os.path.join(ROOT, "i2c_decoders", "loopback_dut_decoder.json")])
    check(ok, f"export ({msg})")
    v = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "validate_capture_csv.py"), out, "--strict"],
                       capture_output=True, text=True)
    check(v.returncode == 0 and "8 rows, VALID" in v.stdout, f"CSV v2 validates strict ({v.stdout.strip()})")
    text = open(out, encoding="utf-8").read()
    check(text.splitlines()[0].endswith("SCL (Hz)") and ",100000" in text, "SCL (Hz) column filled")
    check("R1 word 0x02: word = 0xA002 | base = 0xA0 | pointer = 0x02" in text
          and "R2 word 0x02: word = 0xB002 | base = 0xB0 | pointer = 0x02" in text,
          "--decoder fills Decode (loopback decoder layout v2)")
    check("✓ PEC" in text, "PEC column exported")

    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
