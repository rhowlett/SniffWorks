#!/usr/bin/env python3
"""
tools/replay_compare.py
Replay a recorded transaction window (record_on_trigger.py JSON-lines)
against a device under test and compare its responses byte-for-byte.

Requires a probe running the MASTER firmware
(make EXTRA_DEFS='-DSNIFF_MODE=SNIFF_MODE_MASTER').

For each recorded WRITE: the same bytes are written verbatim.
For each recorded READ: a read of the recorded length is issued and the
response is diffed against the recording (a write immediately followed by a
restart-read is replayed as one write_read, preserving the repeated start).

Examples:
    python3 tools/replay_compare.py --port /dev/tty.usbmodem1103 \\
        capture.jsonl
    python3 tools/replay_compare.py capture.jsonl --timing preserve \\
        --mask mask.json --bus-khz 100

--timing preserve   honor the recorded inter-transaction gaps (t_us deltas)
--timing flat       run back-to-back (default)
--mask FILE         JSON: {"ADDR:HEXREG": [byte_index, ...], ...} — response
                    byte indices to ignore per pointer register (dynamic
                    measurements, counters, PEC). Example:
                    {"0x08:14": [0, 1], "0x08:3E": [4, 5, 6, 7]}
Exit code: 0 all match, 1 mismatches, 2 link/setup error.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ion_master import open_master, RESULT_ACK   # noqa: E402
from core.i2c_controller import I2CDirection          # noqa: E402


def load_capture(path: str) -> list[dict]:
    rows = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            r = json.loads(line)
            r["data"] = bytes.fromhex(r["data"])
            rows.append(r)
    return rows


def pair_transactions(rows: list[dict]):
    """Group a write followed by a restart-read into one write_read unit;
    everything else stands alone. Yields ('wr'|'w'|'r', rows...)."""
    i = 0
    while i < len(rows):
        cur = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        if (cur["dir"] == "W" and nxt is not None and nxt["dir"] == "R"
                and nxt.get("restart") and nxt["addr"] == cur["addr"]):
            yield "wr", cur, nxt
            i += 2
        elif cur["dir"] == "W":
            yield "w", cur, None
            i += 1
        else:
            yield "r", cur, None
            i += 1


def hex_diff(expected: bytes, actual: bytes, ignore: set) -> str:
    parts = []
    for i in range(max(len(expected), len(actual))):
        e = f"{expected[i]:02X}" if i < len(expected) else "--"
        a = f"{actual[i]:02X}" if i < len(actual) else "--"
        if i in ignore:
            parts.append(f"[{a}]")           # masked
        elif e == a:
            parts.append(a)
        else:
            parts.append(f"{e}>{a}")         # expected>actual
    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Replay a capture as I2C master and compare responses.",
        epilog=__doc__.split("Examples:")[1],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", help="JSON-lines file from record_on_trigger.py")
    ap.add_argument("--port", help="serial port (default: auto-detect probe)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timing", choices=["flat", "preserve"], default="flat")
    ap.add_argument("--mask", help="JSON mask file (see --help)")
    ap.add_argument("--bus-khz", type=int, choices=[100, 400], default=None,
                    help="set the probe's bus speed before replaying")
    args = ap.parse_args()

    rows = load_capture(args.capture)
    if not rows:
        print("empty capture", file=sys.stderr)
        return 2

    mask: dict[str, set] = {}
    if args.mask:
        raw = json.loads(Path(args.mask).read_text())
        mask = {k.upper(): set(v) for k, v in raw.items()}

    if not args.port:
        from core.ion_backend import list_serial_ports
        cand = [p for p in list_serial_ports() if p["is_stlink"] or p["hint"]]
        if not cand:
            print("no probe-like port found — pass --port", file=sys.stderr)
            return 2
        args.port = cand[0]["device"]
        print(f"auto-selected {args.port} [{cand[0]['hint']}]")

    try:
        link = open_master(args.port, args.baud)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"probe: fw {link.hello['fw']} ({link.hello['mode']})")
    if args.bus_khz:
        link.set_bus_speed(args.bus_khz)
        print(f"bus speed: {args.bus_khz} kHz")

    def mask_for(addr: int, reg: bytes) -> set:
        key = f"0X{addr:02X}:{reg.hex().upper()}"
        return mask.get(key, set())

    n_units = n_pass = n_mismatch = n_result = 0
    prev_t_us = None
    for kind, a, b in pair_transactions(rows):
        if args.timing == "preserve" and prev_t_us is not None:
            gap = (a["t_us"] - prev_t_us) / 1e6
            if 0 < gap < 10:
                time.sleep(gap)
        prev_t_us = (b or a)["t_us"]
        n_units += 1

        if kind == "w":
            txn = link.write(a["addr"], a["data"])
            ok = txn is not None and txn.result == RESULT_ACK
            want_nak = a.get("nak", False)
            if ok or (txn is not None and txn.nak and want_nak):
                n_pass += 1
                status = "PASS"
            else:
                n_result += 1
                status = f"RESULT {txn.result if txn else 'LINK_TIMEOUT'}"
            print(f"[{n_units:3}] W 0x{a['addr']:02X} "
                  f"[{a['data'].hex(' ').upper()}]  {status}")
            continue

        # read-bearing unit: 'r' or 'wr'
        if kind == "wr":
            reg = a["data"]
            wtxn, rtxn = link.write_read(a["addr"], reg, len(b["data"]))
            expected, label = b["data"], f"W[{reg.hex().upper()}] rS R"
            txn = rtxn
        else:
            reg = b""
            txn = link.read(a["addr"], len(a["data"]))
            expected, label = a["data"], "R"

        if txn is None or txn.result != RESULT_ACK:
            n_result += 1
            print(f"[{n_units:3}] {label} 0x{a['addr']:02X}  "
                  f"RESULT {txn.result if txn else 'LINK_TIMEOUT'}")
            continue
        ignore = mask_for(a["addr"], reg)
        live = [i for i in range(max(len(expected), len(txn.data)))
                if i not in ignore]
        match = (all(i < len(expected) and i < len(txn.data)
                     and expected[i] == txn.data[i] for i in live))
        if match:
            n_pass += 1
            print(f"[{n_units:3}] {label} 0x{a['addr']:02X} "
                  f"[{len(expected)}B]  PASS"
                  + (f"  ({len(ignore)} masked)" if ignore else ""))
        else:
            n_mismatch += 1
            print(f"[{n_units:3}] {label} 0x{a['addr']:02X}  MISMATCH")
            print(f"      {hex_diff(expected, txn.data, ignore)}")

    print(f"\n{n_units} unit(s): {n_pass} pass, {n_mismatch} mismatch, "
          f"{n_result} result-error")
    return 0 if (n_mismatch + n_result) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
