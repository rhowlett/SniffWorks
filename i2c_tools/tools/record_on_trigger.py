#!/usr/bin/env python3
"""
tools/record_on_trigger.py  [v0.1]
Record a window of sniffed I2C traffic bounded by a trigger transaction:
recording starts at the first transaction matching the trigger and stops at
its next occurrence (the trigger transactions themselves are included).

Requires a probe running the SNIFFER firmware (bit-bang variant).
Output: JSON-lines, one transaction per line — the input format for
replay_compare.py.

Examples:
    # BQ76905 subcommand poll: write 0x3E to addr 0x08 starts/stops the window
    python3 tools/record_on_trigger.py --port /dev/tty.usbmodem1103 \\
        --trigger 0x08:W:3E --out capture.jsonl

    # any read from 0x6B
    python3 tools/record_on_trigger.py --trigger 0x6B:R --out c.jsonl

Trigger spec:  ADDR:DIR[:HEXPREFIX]
    ADDR       7-bit address (0x.. or decimal)
    DIR        W or R
    HEXPREFIX  optional data prefix, hex bytes (no spaces): 3E, 1A2B, ...
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import ion_protocol as proto           # noqa: E402
from core.ion_backend import list_serial_ports   # noqa: E402


def parse_trigger(spec: str):
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise argparse.ArgumentTypeError("trigger must be ADDR:DIR[:HEXPREFIX]")
    addr = int(parts[0], 0)
    if parts[1].upper() not in ("W", "R"):
        raise argparse.ArgumentTypeError("DIR must be W or R")
    dir_read = parts[1].upper() == "R"
    prefix = bytes.fromhex(parts[2]) if len(parts) == 3 else b""
    return addr, dir_read, prefix


def matches(rec: "proto.TxnRecord", trig) -> bool:
    addr, dir_read, prefix = trig
    return (rec.address == addr and rec.dir_read == dir_read
            and rec.data[:len(prefix)] == prefix)


def rec_to_json(rec: "proto.TxnRecord") -> dict:
    return {"t_us": rec.t_us, "addr": rec.address,
            "dir": "R" if rec.dir_read else "W",
            "data": rec.data.hex().upper(),
            "nak": rec.nak, "restart": rec.restart, "stop": rec.stop}


def pick_port(explicit: str | None) -> str:
    if explicit:
        # a port path, a USB serial number, or a device name [XREF: device-names]
        from core.device_names import resolve_port
        try:
            return resolve_port(explicit)
        except LookupError as e:
            sys.exit(f"error: {e}")
    ports = list_serial_ports()
    for p in ports:
        if p["is_stlink"] or p["hint"]:
            print(f"auto-selected {p['device']} [{p['hint']}]")
            return p["device"]
    sys.exit("no probe-like serial port found — pass --port")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial port, USB serial number or device name "
                                   "(default: auto-detect probe)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--trigger", required=True, type=parse_trigger,
                    help="ADDR:DIR[:HEXPREFIX], e.g. 0x08:W:3E")
    ap.add_argument("--out", required=True, help="output .jsonl path")
    ap.add_argument("--max-seconds", type=float, default=300.0,
                    help="give up if the window doesn't close (default 300)")
    args = ap.parse_args()

    import serial
    port = serial.Serial(pick_port(args.port), baudrate=args.baud, timeout=0)
    parser = proto.FrameParser()

    port.write(proto.CMD_PING_BYTES)
    port.write(proto.CMD_START_BYTES)

    recording: list[dict] = []
    armed = False
    t_end = time.monotonic() + args.max_seconds
    print(f"waiting for trigger "
          f"{'R' if args.trigger[1] else 'W'}@0x{args.trigger[0]:02X} "
          f"[{args.trigger[2].hex().upper() or 'any'}] ...")
    try:
        while time.monotonic() < t_end:
            data = port.read(4096)
            if not data:
                time.sleep(0.002)
                continue
            for ftype, payload in parser.feed(data):
                if ftype != proto.FRAME_TXN:
                    continue
                rec = proto.decode_txn(payload)
                if rec is None:
                    continue
                hit = matches(rec, args.trigger)
                if not armed:
                    if hit:
                        armed = True
                        recording.append(rec_to_json(rec))
                        print("trigger #1 — recording")
                    continue
                recording.append(rec_to_json(rec))
                if hit and len(recording) > 1:
                    raise StopIteration      # window closed
        print("timed out waiting for the closing trigger", file=sys.stderr)
        return 2
    except StopIteration:
        pass
    except KeyboardInterrupt:
        print("\ninterrupted — writing what was captured", file=sys.stderr)
    finally:
        try:
            port.write(proto.CMD_STOP_BYTES)
            port.close()
        except Exception:
            pass

    Path(args.out).write_text(
        "\n".join(json.dumps(r) for r in recording) + "\n")
    print(f"wrote {len(recording)} transactions to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
