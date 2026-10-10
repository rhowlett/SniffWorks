#!/usr/bin/env python3
"""
tests/test_decode_schema.py — regression coverage for the single-source decoder
(core/decode_schema.py) against real captured data.

Usage:
    python3 tests/test_decode_schema.py          # standalone, prints PASS/FAIL
    pytest tests/test_decode_schema.py            # also works under pytest

No Qt / no hardware required: it parses the capture CSVs directly and drives
core.decode_schema.StreamDecoder, the same sequence-aware decoder the log model
and the replay app use.

Baseline captured 2026-07-01 (prompt P04) after merging the improved subcommand
read-back logic into core/. The long-capture decoded count rose to 612 after the
BQ76905 subcommand block-read fix: data-returning subcommands are read back as a
block frame ([code echo][32-byte transfer buffer][checksum][length]); the decoder
now strips the 2-byte echo, bounds the data by the frame length, verifies the
checksum, and renders offset-addressed fields. This corrects two classes of bug
the previous front-slicing logic had:
  * It sliced the value from the FRONT of the raw read, i.e. it reported the
    subcommand *echo* instead of the buffer data (e.g. HW_VERSION read back as
    0x0003 — the echo — instead of the real 0x0001).
  * FW_VERSION (0x0002) had no rule, so its six block reads (and their write
    rows) never decoded; they now do, which is the +12 versus the old 600.
test_subcommand_block_read below pins the field values and the clean checksum so
this cannot silently regress.
"""

import csv
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.decode_schema import DecodeSchema, StreamDecoder  # noqa: E402

DECODER = os.path.join(_ROOT, "i2c_decoders", "bq76905_decoder.json")
HANDSHAKE = os.path.join(_ROOT, "i2c_capture", "EVM_Handshake.csv")
LONG = os.path.join(_ROOT, "i2c_capture", "EVM_long_capture.csv")


def _parse_hex(text: str) -> bytes:
    text = (text or "").strip()
    if not text:
        return b""
    return bytes(int(t, 16) for t in text.replace(",", " ").split() if t)


def _decode_capture(csv_path: str):
    """Return list of (seq, addr, dir, data_hex, decoded_text) in capture order."""
    schema = DecodeSchema.load(DECODER)
    schema.multiline_bits = True  # matches the replay app
    stream = StreamDecoder(schema)
    out = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            addr_txt = (r.get("Addr") or "").strip()
            try:
                addr = int(addr_txt, 16)
            except ValueError:
                continue
            direction = (r.get("Dir") or "").strip().upper()
            data = _parse_hex(r.get("Data (hex)", ""))
            had_stop = (r.get("Stop") or "").strip().upper() == "P"
            rstart = (r.get("Start") or "").strip().lower() == "sr"
            res = stream.feed(addr, direction, data,
                              had_stop=had_stop, repeated_start=rstart)
            out.append(((r.get("#") or "").strip(), addr, direction,
                        data.hex(), res.text or ""))
    return out


def test_handshake_decodes_nothing():
    """Handshake capture is all 0x0B zero-length probes; decoder rules are 0x08."""
    rows = _decode_capture(HANDSHAKE)
    assert len(rows) == 23, f"expected 23 rows, got {len(rows)}"
    assert sum(1 for r in rows if r[4]) == 0


def test_long_capture_decoded_count():
    rows = _decode_capture(LONG)
    assert len(rows) == 2740, f"expected 2740 rows, got {len(rows)}"
    decoded = sum(1 for r in rows if r[4])
    assert decoded == 612, f"expected 612 decoded rows, got {decoded}"


def test_subcommand_readback():
    """Pins the same-register (0x3E) subcommand read-back pairing. Row #276 is a
    HW_VERSION result; it must report the real version from the transfer buffer
    (0x0001), NOT the 2-byte code echo (0x0003) the old front-slicing produced."""
    rows = {r[0]: r for r in _decode_capture(LONG)}
    assert rows["276"][4] == "HW_VERSION = 0x0001", rows["276"][4]
    assert rows["276"][4] == rows["1020"][4]     # same subcommand appears twice
    assert rows["291"][4].startswith("PASSQ:")   # multiline structured render
    assert rows["424"][4].startswith("CB_ACTIVE_CELLS")


def test_subcommand_block_read_fields():
    """The 36-byte block reads decode into offset-addressed fields with the
    correct byte order/scaling, and the frame checksum verifies clean (no ⚠)."""
    rows = {r[0]: r for r in _decode_capture(LONG)}

    fw = rows["231"][4]                          # FW_VERSION (0x0002)
    assert "⚠" not in fw, f"checksum flag on clean frame: {fw!r}"
    assert "Device Number = 0x7605" in fw
    assert "FW Version = 0x0000" in fw
    assert "Build Number = 0x0002" in fw

    pq = rows["291"][4]                           # PASSQ (0x0004)
    assert "⚠" not in pq
    assert "PASSQLSB = 1073741762.25 userA-s" in pq   # 0xFFFFFF09 * 0.25
    assert "PASSQMSB = -0.25 userA-s" in pq           # signed I4 == -1, * 0.25
    assert "PASSTIME = 9.75 s" in pq                  # 39 * 0.25 s

    pq2 = rows["1035"][4]                         # a second PASSQ with different data
    assert "PASSQLSB = 930.25 userA-s" in pq2         # 0x00000E89 * 0.25
    assert "PASSQMSB = 0 userA-s" in pq2


def test_subcommand_checksum_flag():
    """A corrupted checksum byte must surface a ⚠ note (the verification is real,
    not cosmetic)."""
    schema = DecodeSchema.load(DECODER)
    # Real FW_VERSION frame: echo 02 00 | buffer 76 05 00 00 00 02 (+26 zero) | chk 80 | len 0A
    good = bytes([0x02, 0x00, 0x76, 0x05, 0x00, 0x00, 0x00, 0x02]
                 + [0] * 26 + [0x80, 0x0A])
    assert len(good) == 36
    ok = schema.decode_subcommand(0x08, 0x0002, good, block_framed=True)
    assert "⚠" not in ok, ok
    bad = bytearray(good)
    bad[34] ^= 0xFF                               # corrupt the checksum byte
    flagged = schema.decode_subcommand(0x08, 0x0002, bytes(bad), block_framed=True)
    assert "⚠" in flagged and "chk" in flagged, flagged


def test_roundtrip_json():
    """Loading and re-serializing the decoder preserves rule count."""
    schema = DecodeSchema.load(DECODER)
    n = len(schema)
    reparsed = DecodeSchema.from_json(schema.to_json())
    assert len(reparsed) == n


def _run():
    tests = [
        ("handshake_decodes_nothing", test_handshake_decodes_nothing),
        ("long_capture_decoded_count", test_long_capture_decoded_count),
        ("subcommand_readback", test_subcommand_readback),
        ("subcommand_block_read_fields", test_subcommand_block_read_fields),
        ("subcommand_checksum_flag", test_subcommand_checksum_flag),
        ("roundtrip_json", test_roundtrip_json),
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:
            failures += 1
            print(f"  FAIL  {name}   -> {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run())
