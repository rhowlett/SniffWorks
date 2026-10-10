#!/usr/bin/env python3
# [v0.2]
"""
loopback_dut/tests/test_host_model.py - tier T1 (no hardware) for P1-T3.

  * The Python DUT model reproduces the SAME literal vectors that the C
    firmware test (tests/host/test_dut_regmap.c) pins, so the two
    independent implementations of PROTOCOL.md §4 agree.
  * Line sealing matches the PROTOCOL.md §6 vectors.
  * DutLink against a fake DUT (driven by the model, speaking the real line
    format): handshake, RUN parsing, a desync (late reply with an old seq)
    raises DesyncError naming the in-flight seq, a corrupted line is rejected.
  * loopback_run --dry-run writes a schema-valid expected.json, and a
    hardware-mode run against the fake DUT matches the dry run phase for phase
    (emit_status "ok", no model_mismatch).
"""
import io
import json
import os
import sys
import tempfile

import jsonschema

HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LB, "host"))

import loopback_run  # noqa: E402
from dut_link import DesyncError, DutLink, LinkError  # noqa: E402
from lbcommon import DutModel, RegMap, crc8, load_rig, seal, unseal  # noqa: E402

FAILURES = []
RIG = os.path.join(LB, "config", "rig.toml")


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


# ------------------------------------------------------------ fake DUT
class FakeDut:
    """Speaks the DUT line protocol, answering from DutModel."""

    def __init__(self, rig, late_reply_seq=None, corrupt_next=False):
        self.model = DutModel(rig)
        self.rig = rig
        self.out = io.BytesIO()
        self.rx = b""
        self.pending = []
        self.late_reply_seq = late_reply_seq
        self.corrupt_next = corrupt_next
        self.id_to_addr = {r.id: r.address for r in rig.responders}

    def _emit(self, body):
        line = seal(body)
        if self.corrupt_next:
            line = line.replace(" ", "  ", 1)
            self.corrupt_next = False
        self.pending.append((line + "\n").encode())

    def write(self, b):
        self.rx += b
        while b"\n" in self.rx:
            raw, self.rx = self.rx.split(b"\n", 1)
            body = unseal(raw.decode())
            self._handle(body if body is not None else raw.decode())

    def readline(self):
        return self.pending.pop(0) if self.pending else b""

    def _handle(self, line):
        t = line.split()
        if t[0] == "PING":
            self._emit("HELLO LBDUT proto=1 fw=0.1 kernel=64000000")
        elif t[0] == "RESET":
            self._emit("OK RESET")
        elif t[0] == "SET":
            if t[1] == "SPEED":
                self._emit(f"OK SPEED hz={t[2]} pred={t[2]} timingr=00000000")
            elif t[1] == "PEC":
                self.model.pec_after[self.id_to_addr[int(t[2])]] = int(t[3])
                self._emit(f"OK PEC {t[2]} {t[3]}")
            else:
                self._emit(f"OK {t[1]} {' '.join(t[2:])}")
        elif t[0] == "RUN":
            seq, op, addr = int(t[1]), t[2], int(t[3], 16)
            rest = [x for x in t[4:] if "=" not in x]
            rep = next((int(x[4:]) for x in t if x.startswith("rep=")), 1)
            opname = {"W": "write", "R": "read", "WR": "write_read", "WPR": "write_stop_read"}[op]
            step = {"address": addr, "op": opname}
            if op == "W":
                step["data"] = [int(x, 16) for x in rest]
            elif op == "R":
                step["read_len"] = int(rest[0])
            else:
                step["read_len"] = int(rest[0]); step["data"] = [int(x, 16) for x in rest[1:]]
            if self.late_reply_seq is not None and seq == self.late_reply_seq + 1:
                self._emit(f"END {self.late_reply_seq} 0 OK t=1 dur=1")   # stale reply
            for it in range(rep):
                phases = self.model.step(step)
                for i, p in enumerate(phases):
                    n = 0 if p.ack == "NA" else len(p.data)
                    hx = "".join(f" {b:02X}" for b in (p.data if n else []))
                    self._emit(f"PH {seq} {it} {i} {'SR' if p.start == 'Sr' else 'S'} {p.address:02X} "
                               f"{p.dir} {p.ack} {'P' if p.stop else '-'} {n}{hx}")
                res = "NAK" if any(p.ack == "NA" for p in phases) else "OK"
                self._emit(f"END {seq} {it} {res} t={1000 + it} dur=100")


def test_model_vectors(rig):
    print("model == C firmware vectors")
    m = RegMap(0xA000)
    m.write(0, 0x02)
    check([m.read(k) for k in range(4)] == [0x02, 0xA0, 0x03, 0xA0], "R1 ptr 0x02 x4 = 02 A0 03 A0")
    m.write(0, 0xFF)
    check([m.read(k) for k in range(4)] == [0xFF, 0xA0, 0x00, 0xA1], "ptr 0xFF: no wrap")
    m.write(0, 0x00)
    check(m.read(78) == 0x27 and m.read(79) == 0xA0, "80-byte read ends 27 A0")
    m.write(0, 0x3E); m.write(1, 0x01); m.write(2, 0x00); m.write(0, 0x3E)
    blk = [m.read(k) for k in range(38)]
    check(blk[:4] == [0x01, 0x00, 0x41, 0x40] and blk[34] == 0x0E and blk[35] == 36
          and blk[36:] == [0xFF, 0xFF], "block: echo, buffer, checksum 0x0E, length 36, then FF")
    check(crc8(b"123456789") == 0xF4, "CRC-8/SMBUS check value")
    check(seal("HELLO LBDUT proto=1 fw=0.1 kernel=64000000").endswith(" *BF")
          and seal("PH 1 0 1 SR 6B R A P 2 02 A0").endswith(" *CB"), "PROTOCOL.md §6 CRC vectors")
    check(unseal("PING *ZZ") is None and unseal("PING") is None, "unseal rejects bad/missing CRC")

    dm = DutModel(rig)
    ph = dm.step({"target": "R1", "op": "write_read", "data": [2], "read_len": 2})
    check([(p.start, p.dir, p.ack, p.stop, p.data) for p in ph] ==
          [("S", "W", "A", False, [2]), ("Sr", "R", "A", True, [0x02, 0xA0])], "LB-01 phases")
    ph = dm.step({"target": "NAK", "op": "write", "data": [0]})
    check(ph[0].ack == "NA" and ph[0].data == [] and ph[0].stop, "LB-05: 0x08 NAKs, no data")
    dm.pec_after[0x6B] = 2
    ph = dm.step({"target": "R1", "op": "write_read", "data": [8], "read_len": 3, "pec": True})
    check(ph[1].data == [0x08, 0xA0, 0x6E] and ph[1].pec, "LB-07 PEC 0x6E over D6 08 D7 08 A0")
    dm.pec_after[0x6B] = 0
    ph = dm.step({"target": "R1", "op": "write", "data": [0x0A, 0x5A], "pec": True}, host_pec=True)
    check(ph[0].data == [0x0A, 0x5A, crc8(bytes([0xD6, 0x0A, 0x5A]))], "LB-08 host appends write PEC")
    ph = dm.step({"target": "R2", "op": "write_read", "data": [2], "read_len": 2})
    check(ph[1].data == [0x02, 0xB0], "R2 base 0xB000")


def test_link(rig):
    print("DutLink against a fake DUT")
    link = DutLink(FakeDut(rig))
    check(link.handshake().startswith("HELLO LBDUT"), "handshake")
    r = link.run(7, "WR 6B 2 02")
    ph = r.iterations[0]["phases"]
    check(len(ph) == 2 and ph[1].start == "Sr" and ph[1].data == [0x02, 0xA0] and ph[1].stop,
          "RUN WR parsed into two phases")
    r = link.run(8, "WR 6B 2 06", rep=5)
    check(len(r.iterations) == 5 and all(len(i["phases"]) == 2 for i in r.iterations), "rep=5: five iterations")
    link = DutLink(FakeDut(rig, late_reply_seq=10))
    link.handshake()
    try:
        link.run(11, "WR 6B 2 02")
        check(False, "late reply with an old seq must raise DesyncError")
    except DesyncError as e:
        check(e.sent_seq == 11 and "END 10" in e.line, f"desync detected: {e}")
    # one corrupted HELLO (VCP glitch after enumeration): rejected, counted, retried
    link = DutLink(FakeDut(rig, corrupt_next=True))
    check(link.handshake().startswith("HELLO LBDUT") and link.bad_crc == 1,
          "corrupted first HELLO rejected (bad CRC counted) and the retry succeeds")
    # a link that stays corrupted must fail, never be accepted
    class AlwaysCorrupt(FakeDut):
        def _emit(self, body):
            self.corrupt_next = True
            super()._emit(body)
    link = DutLink(AlwaysCorrupt(rig))
    try:
        link.handshake()
        check(False, "persistently corrupted link must raise")
    except LinkError as e:
        check(link.bad_crc == 3 and "no HELLO after 3" in str(e),
              f"persistent bad CRC -> LinkError after 3 PINGs ({e})")
    # RUN replies are never retried: a bad CRC mid-RUN raises
    fd = FakeDut(rig); link = DutLink(fd); link.handshake()
    fd.corrupt_next = True
    try:
        link.run(1, "WR 6B 2 02")
        check(False, "bad CRC during RUN must raise")
    except LinkError as e:
        check("bad CRC" in str(e), "bad CRC during RUN raises (no silent retry of bus traffic)")


def test_run_dry_and_fake(rig):
    print("loopback_run: dry run vs hardware mode on the fake DUT")
    tmp = tempfile.mkdtemp()
    out_dry = os.path.join(tmp, "dry.json")
    check(loopback_run.main(["--dry-run", "--out", out_dry]) == 0, "dry run exits 0")
    schema = json.load(open(os.path.join(LB, "schema", "expected.schema.json")))
    dry = json.load(open(out_dry))
    errs = list(jsonschema.Draft202012Validator(schema).iter_errors(dry))
    check(not errs, f"dry-run expected.json is schema-valid ({len(errs)} errors)")

    pattern = json.load(open(loopback_run.DEFAULT_PATTERN, encoding="utf-8"))
    runner = loopback_run.Runner(rig, DutLink(FakeDut(rig)))
    runner.link.handshake()
    runner.configure_rig()
    hw = [runner.run_case(c) for c in pattern["cases"]]
    same = all(h["emit_status"] == "ok" for h in hw)
    check(same, "hardware mode on the fake DUT: every case emit_status ok (no model_mismatch)")
    strip = lambda cs: [[it["phases"] for it in c["iterations"]] for c in cs]
    check(strip(hw) == strip(dry["cases"]), "fake-DUT phases == dry-run phases, all 15 cases")
    check(sum(len(c["iterations"]) for c in hw if c["id"] == "LB-12") == 200, "LB-12: 200 iterations via rep=")
    from loopback_compare import LEDGER_KEYS
    for c in pattern["cases"]:
        d = next(x for x in dry["cases"] if x["id"] == c["id"])
        lost = [k for k in LEDGER_KEYS if k in c and d.get(k) != c[k]]
        check(not lost, f"{c['id']}: every ledger field reaches expected.json (lost {lost})")


def main():
    rig = load_rig(RIG)
    test_model_vectors(rig)
    test_link(rig)
    test_run_dry_and_fake(rig)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
