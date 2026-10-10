#!/usr/bin/env python3
# [v0.2]
"""
tests/test_loopback_dut_decoder.py - vectors for i2c_decoders/loopback_dut_decoder.json,
pinned to the loopback DUT register map (loopback_dut/docs/PROTOCOL.md §4):
R1 0x6B word(x) = 0xA000 + x, R2 0x55 word(x) = 0xB000 + x, little-endian;
R1 subcommand block at 0x3E. Feeds the tool's StreamDecoder exactly as a
sniffer capture would (one call per address phase).

LB-04 / review B8 is an EXPECTED FAILURE: with B8 present a 1-byte write is
taken as a pointer and decodes empty. The test asserts that symptom and FAILS
if it unexpectedly decodes, because that means the xfail ledger is stale
(master plan §5.2.8). B29 (new, Phase 1) is handled the same way: a truncated
payload renders a fabricated value instead of absent.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.decode_schema import DecodeSchema, StreamDecoder  # noqa: E402

DEC = os.path.join(ROOT, "i2c_decoders", "loopback_dut_decoder.json")
FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def new():
    return StreamDecoder(DecodeSchema.load(DEC))


def main():
    print("loopback_dut_decoder vectors")
    s = new()
    check(s.feed(0x6B, "W", b"\x02", had_stop=False).text == "",
          "LB-01 pointer write W [02]: no text yet")
    r = s.feed(0x6B, "R", b"\x02\xA0", had_stop=True, repeated_start=True)
    check(r.text == "R1 word 0x02: word = 0xA002 | base = 0xA0 | pointer = 0x02", f"LB-01 Sr R [02 A0] -> word, R1 base A0, pointer echo 02 (got {r.text!r})")

    s = new()
    s.feed(0x6B, "W", b"\x04", had_stop=True)
    r = s.feed(0x6B, "R", b"\x04\xA0", had_stop=True)
    check(r.text == "R1 word 0x04: word = 0xA004 | base = 0xA0 | pointer = 0x04", f"LB-02 stop-separated pointer (got {r.text!r})")

    s = new()
    r = s.feed(0x6B, "W", b"\x10\x34\x12", had_stop=True)
    check(r.text == "R1 word 0x10 (set) = 0x1234", f"LB-03 indexed write LE (got {r.text!r})")

    s = new()
    s.feed(0x55, "W", b"\x02", had_stop=False)
    r = s.feed(0x55, "R", b"\x02\xB0", had_stop=True, repeated_start=True)
    check(r.text == "R2 word 0x02: word = 0xB002 | base = 0xB0 | pointer = 0x02", f"LB-15 R2 has its own base B0 (got {r.text!r})")

    s = new()
    s.feed(0x6B, "W", b"\x08", had_stop=False)
    r = s.feed(0x6B, "R", b"\x08\xA0\x5C", had_stop=True, repeated_start=True)
    check(r.text == "R1 word 0x08: word = 0xA008 | base = 0xA0 | pointer = 0x08", f"LB-07 trailing PEC byte ignored (got {r.text!r})")

    # New finding B29 (Phase 1): a data_bytes=2 rule fed a 1-byte payload
    # renders a fabricated value (0x0002) instead of absent. Expected failure.
    # Probed with an inline plain-hex rule: B29 is an engine bug, and the
    # shipped fixture's word reads now use fields (layout v2, 2026-10-05).
    import json, tempfile
    probe = {"version": 4, "device": "B29 probe", "i2c_address": 0x6B,
             "byte_order": "le",
             "rules": [{"address": 0x6B, "transaction_type": "indexed_read",
                        "register": 2, "data_bytes": 2, "byte_order": "le",
                        "format": "hex", "function": "X", "name": "R1 word 0x02"}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(probe, tf)
    s = StreamDecoder(DecodeSchema.load(tf.name))
    s.feed(0x6B, "W", b"\x02", had_stop=False)
    r = s.feed(0x6B, "R", b"\x02", had_stop=True, repeated_start=True)
    if r.text in ("", "R1 word 0x02 = <absent>") or "absent" in r.text:
        check(False, "B29 appears FIXED (truncated read renders absent) - update the xfail ledger")
    else:
        check(r.text == "R1 word 0x02 = 0x0002",
              f"XFAIL(B29) truncated 1-byte read renders a fabricated 0x0002 (got {r.text!r})")

    # LB-09 subcommand block: write 0x0001 to 0x3E, then read 36 bytes from 0x3E
    lo = 0x01
    buf = bytes((0x40 + i) ^ lo for i in range(32))
    chk = (~(lo + 0 + sum(buf))) & 0xFF
    block = bytes([lo, 0x00]) + buf + bytes([chk, 36])
    check(chk == 0x0E, "block checksum for subcommand 0x0001 is 0x0E (PROTOCOL.md)")
    s = new()
    s.feed(0x6B, "W", b"\x3E\x01\x00", had_stop=True)
    s.feed(0x6B, "W", b"\x3E", had_stop=False)
    r = s.feed(0x6B, "R", block, had_stop=True, repeated_start=True)
    check(r.text == "LB block 0x0001: buf[0] = 0x41 | buf[1] = 0x40 | buf[30] = 0x5F | buf[31] = 0x5E",
          f"LB-09 block fields: buf[i] = (0x40+i) XOR 0x01 (got {r.text!r})")
    check("buf[0]" in r.text and "0x41" in r.text and "0x5E" in r.text and "⚠" not in r.text,
          f"LB-09 block unwraps, echo+checksum OK (got {r.text!r})")

    # LB-04 / B8 expected failure
    s = new()
    r = s.feed(0x6B, "W", b"\x20", had_stop=True)
    if r.text == "LB simple write = 0x20":
        check(False, "LB-04 decoded as a simple write: B8 appears FIXED - update the xfail ledger")
    else:
        check(r.text == "", f"XFAIL(B8) LB-04 W [20] P decodes empty, as the ledger records (got {r.text!r})")

    # Replay check: i2c_capture/loopback_dut_replay_check.csv carries the
    # expected decode (computed from PROTOCOL.md, not by the engine) in its
    # Decode column; the tool's capture decoder must reproduce every row.
    import csv
    from ui.common.capture import decode_capture
    cap = os.path.join(ROOT, "i2c_capture", "loopback_dut_replay_check.csv")
    with open(cap, newline="", encoding="utf-8") as f:
        want = [r["Decode"] for r in csv.DictReader(f)]
    got = decode_capture(cap, DecodeSchema.load(DEC))
    check(len(got) == len(want) == 20, "replay check: 20 rows")
    for i, (g, w) in enumerate(zip(got, want), start=1):
        if w == "LB simple write = 0x20":
            check(g.decoded == "", f"XFAIL(B8) replay row {i}: simple write decodes empty")
        elif w == "" and g.raw_data_hex.startswith("3E 01"):
            continue                    # subcommand announce: text informational
        else:
            check(g.decoded == w, f"replay row {i}: {w!r} (got {g.decoded!r})")

    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
