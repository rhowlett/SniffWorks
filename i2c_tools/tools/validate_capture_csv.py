#!/usr/bin/env python3
"""
tools/validate_capture_csv.py  [v1.1]
Validate a capture CSV against documents/CSV_FORMAT.md (capture CSV v2;
v1 files, which lack the trailing SCL column, are still accepted).
[XREF: csv-format]

Usage:
    python3 tools/validate_capture_csv.py CAPTURE.csv [--strict]

Default mode enforces what the loader requires (canonical columns);
--strict additionally cross-checks the informational columns (# monotonic,
Len == byte count, Int == big-endian value) as produced by the sniffers.

Exit status 0 = valid, 1 = errors found.
"""
import argparse
import csv
import re
import sys

HEADER_V1 = ["Time", "#", "Addr", "Dir", "Len", "Data (hex)", "Int", "ASCII",
             "Decode", "NAK", "Start", "Stop", "PEC"]
HEADER_V2 = HEADER_V1 + ["SCL (Hz)"]
HEADER = HEADER_V2                      # what current tools write
SCL_MAX_HZ = 10_000_000                 # sanity bound for a measured SCL
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}$")
HEXPAIRS_RE = re.compile(r"^[0-9A-Fa-f]{2}([ ,][0-9A-Fa-f]{2})*$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--strict", action="store_true",
                    help="also verify informational columns (#, Len, Int)")
    args = ap.parse_args()

    errors, rows = [], 0
    with open(args.csv_path, newline="", encoding="utf-8") as fh:
        rdr = csv.reader(fh)
        try:
            header = next(rdr)
        except StopIteration:
            print("FAIL empty file")
            return 1
        if header == HEADER_V2:
            cols = HEADER_V2
        elif header == HEADER_V1:
            cols = HEADER_V1
        else:
            cols = HEADER_V2
            errors.append(f"header mismatch:\n  got      {header}\n"
                          f"  expected {HEADER_V2}\n"
                          f"        or {HEADER_V1} (v1)")
        prev_seq = 0
        for n, row in enumerate(rdr, start=2):
            if not any(cell.strip() for cell in row):
                continue
            rows += 1
            if len(row) != len(cols):
                errors.append(f"line {n}: {len(row)} cells, expected "
                              f"{len(cols)}")
                continue
            r = dict(zip(cols, row))

            def err(msg):
                errors.append(f"line {n}: {msg}")

            if not TIME_RE.match(r["Time"].strip()):
                err(f"Time {r['Time']!r} not HH:MM:SS.mmm")
            addr = r["Addr"].strip()
            try:
                a = int(addr, 16)
                if not (0 <= a <= 0x7F):
                    err(f"Addr {addr} outside 7-bit range")
            except ValueError:
                err(f"Addr {addr!r} not hex")
            if r["Dir"].strip() not in ("W", "R"):
                err(f"Dir {r['Dir']!r} not W/R")
            data = r["Data (hex)"].strip()
            if data and not HEXPAIRS_RE.match(data):
                err(f"Data {data!r} not space-separated hex pairs")
            if r["NAK"].strip() not in ("", "NAK"):
                err(f"NAK {r['NAK']!r}")
            if r["Start"].strip().lower() not in ("", "s", "sr"):
                err(f"Start {r['Start']!r} not S/Sr/empty")
            if r["Stop"].strip() not in ("", "P"):
                err(f"Stop {r['Stop']!r} not P/empty")
            if r["PEC"].strip() not in ("", "\u2713 PEC", "\u2717 PEC"):
                err(f"PEC {r['PEC']!r} not '\u2713 PEC'/'\u2717 PEC'/empty")
            scl = r.get("SCL (Hz)", "").strip()
            if scl and not (scl.isdigit() and 0 < int(scl) <= SCL_MAX_HZ):
                err(f"SCL (Hz) {scl!r} not an integer 1..{SCL_MAX_HZ}")

            if args.strict:
                nbytes = len(data.replace(",", " ").split()) if data else 0
                if r["Len"].strip() and int(r["Len"]) != nbytes:
                    err(f"Len {r['Len']} != {nbytes} data bytes")
                if r["Int"].strip():
                    want = int.from_bytes(
                        bytes(int(t, 16) for t in
                              data.replace(",", " ").split()), "big")
                    if int(r["Int"]) != want:
                        err(f"Int {r['Int']} != big-endian value {want}")
                if r["#"].strip():
                    seq = int(r["#"])
                    if seq <= prev_seq:
                        err(f"# {seq} not increasing (prev {prev_seq})")
                    prev_seq = seq

    for e in errors[:40]:
        print("FAIL", e)
    if len(errors) > 40:
        print(f"... {len(errors) - 40} more")
    print(f"{args.csv_path}: {rows} rows, "
          f"{'VALID' if not errors else f'{len(errors)} errors'}"
          f"{' (strict)' if args.strict else ''}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
