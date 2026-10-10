#!/usr/bin/env python3
# [v0.2]
"""
loopback_dut/host/lbsynth.py - synthesise the capture CSV (v2) that a PERFECT
sniffer would export for an expected.json, optionally with the symptoms of
known review items injected. Used by tests/test_loopback_harness.py (P1-T5) to
keep the comparison harness honest; not used on real runs.

Symptoms (per path, applied only where the item applies):
  "B8"  : 1-byte simple-write rows lose their Decode text
  "B9"  : PEC-bearing read rows of a combined transaction show ✗ PEC
  "B10" : (ad2) reads longer than 16 bytes are truncated to 16
  "B13" : normal end-of-read rows export NAK
  "B30" : (ion) every 40th phase of LB-12 is shifted left one bit (lost SCL edge)
  "B31" : (ion) cases above 100 kHz capture nothing but one garbage row, no STOP
  "B32" : (ad2) write phases closed by a repeated START export as 0x00 W [00]
"""
from __future__ import annotations

import csv
import datetime as _dt

HEADER = ["Time", "#", "Addr", "Dir", "Len", "Data (hex)", "Int", "ASCII", "Decode",
          "NAK", "Start", "Stop", "PEC", "SCL (Hz)"]
PEC_OK, PEC_BAD = "✓ PEC", "✗ PEC"


def rows_for(expected: dict, path: str = "ion", symptoms: set[str] | None = None,
             decoder: bool = True) -> list[list[str]]:
    symptoms = symptoms or set()
    out, seq = [], 0
    for c in expected["cases"]:
        if "B31" in symptoms and path == "ion" and c["speed_hz"] > 100000:
            seq += 1
            out.append(["00:00:00.000", str(seq), "0x00", "W", "0", "", "", "", "", "", "S", "", "", ""])
            continue
        n_in_case = 0
        dec = c.get("expect", {}).get("decode")
        trunc = c.get("expect", {}).get("truncate_to", {}).get(path)
        for it in c["iterations"]:
            t0 = it["t_host"]
            for i, p in enumerate(it["phases"]):
                seq += 1
                n_in_case += 1
                data = list(p["data"])
                addr = p["address"]
                if ("B30" in symptoms and path == "ion" and c["id"] == "LB-12"
                        and n_in_case % 40 == 7 and data):
                    data = [((b << 1) | ((data[k + 1] >> 7) if k + 1 < len(data) else 1)) & 0xFF
                            for k, b in enumerate(data)]
                if "B32" in symptoms and path == "ad2" and p["dir"] == "W" and not p["stop"]:
                    addr, data = 0x00, [0x00]
                if trunc is not None:
                    data = data[:trunc]
                if "B10" in symptoms and path == "ad2" and p["dir"] == "R" and len(data) > 16:
                    data = data[:16]
                nak = p["ack"] == "NA" or ("B13" in symptoms and p["dir"] == "R" and p["ack"] == "A")
                pec = ""
                if p.get("pec"):
                    pec = PEC_BAD if ("B9" in symptoms and p["start"] == "Sr") else PEC_OK
                # With the loopback decoder loaded almost every data row decodes;
                # the case's own `expect.decode` text goes on its phase.
                decode = ""
                if addr != p["address"]:
                    pass                                   # B32 row: undecodable
                elif dec and dec["phase"] == i:
                    if not ("B8" in symptoms and len(data) == 1 and p["dir"] == "W"):
                        decode = dec["contains"]
                elif decoder and data and not (p["dir"] == "W" and len(data) == 1):
                    decode = f"synthetic decode 0x{p['address']:02X}"
                ts = _dt.datetime.fromtimestamp(t0 + i * 1e-4).strftime("%H:%M:%S.%f")[:-3]
                out.append([ts, str(seq), f"0x{addr:02X}", p["dir"], str(len(data)),
                            " ".join(f"{b:02X}" for b in data),
                            str(int.from_bytes(bytes(data), "big")) if data else "",
                            "".join(chr(b) if 32 <= b < 127 else "." for b in data), decode,
                            "NAK" if nak else "", p["start"], "P" if p["stop"] else "", pec,
                            str(c["speed_hz"]) if path == "ion" and p["ack"] != "NA" else ""])
    return out


def write_csv(path_out: str, rows: list[list[str]]) -> None:
    with open(path_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
