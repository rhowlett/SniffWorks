"""
ui.common.capture  [v0.1]
Load a sniffer CSV capture (the same column layout the log exports) and run a
DecodeSchema over it with sequence-aware StreamDecoder, so a schema can be
verified against real sniffed data.
"""

import csv
from dataclasses import dataclass
from typing import List, Optional

from core.decode_schema import DecodeSchema, StreamDecoder


@dataclass
class CaptureRow:
    seq: str
    address: int
    direction: str          # "R" / "W"
    data: bytes
    had_stop: bool
    repeated_start: bool
    register: Optional[int]  # register applied during decode (filled in by decode)
    decoded: str             # decode text ("" if none)
    raw_data_hex: str


def _parse_hex(text: str) -> bytes:
    text = (text or "").strip()
    if not text:
        return b""
    return bytes(int(t, 16) for t in text.replace(",", " ").split() if t)


def load_capture_rows(path: str) -> List[dict]:
    """Read the CSV into raw dict rows (no decoding)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def decode_capture(path: str, schema: DecodeSchema) -> List[CaptureRow]:
    """
    Stream-decode an entire capture file with the given schema. Returns one
    CaptureRow per input row, in order, with the register applied and the decode
    text filled in. Rows for other addresses still advance/observe state but
    simply carry their own decode result (usually empty).
    """
    rows = load_capture_rows(path)
    stream = StreamDecoder(schema)
    out: List[CaptureRow] = []
    for r in rows:
        addr_txt = (r.get("Addr") or "").strip()
        try:
            address = int(addr_txt, 16)
        except ValueError:
            continue
        direction = (r.get("Dir") or "").strip().upper()
        data = _parse_hex(r.get("Data (hex)", ""))
        had_stop = (r.get("Stop") or "").strip().upper() == "P"
        rstart = (r.get("Start") or "").strip().lower() == "sr"
        res = stream.feed(address, direction, data,
                          had_stop=had_stop, repeated_start=rstart)
        out.append(CaptureRow(
            seq=(r.get("#") or "").strip(),
            address=address,
            direction=direction,
            data=data,
            had_stop=had_stop,
            repeated_start=rstart,
            register=res.register,
            decoded=res.text,
            raw_data_hex=(r.get("Data (hex)") or "").strip(),
        ))
    return out


def load_transactions(path: str):
    """
    Parse a sniffer CSV into a list of I2CTransaction objects (in capture order),
    preserving address, direction, data, NAK, start (1=S, 2=Sr), stop, PEC and
    (capture CSV v2) the measured SCL. Used by the replay app to feed the
    standard transaction log model. v1 files (no SCL column) load with
    scl_hz=None.
    """
    import time, datetime
    from core.i2c_controller import I2CTransaction, I2CDirection

    rows = load_capture_rows(path)
    txns = []
    for r in rows:
        addr_txt = (r.get("Addr") or "").strip()
        try:
            address = int(addr_txt, 16)
        except ValueError:
            continue
        direction = (r.get("Dir") or "").strip().upper()
        d = I2CDirection.READ if direction == "R" else I2CDirection.WRITE
        data = _parse_hex(r.get("Data (hex)", ""))
        start_txt = (r.get("Start") or "").strip().lower()
        start = 2 if start_txt == "sr" else (1 if start_txt == "s" else 0)
        stop = (r.get("Stop") or "").strip().upper() == "P"
        nak = (r.get("NAK") or "").strip().upper() == "NAK"

        # Restore CRC/PEC validity from the exported column ("✓ PEC" / "✗ PEC" /
        # blank) so the replay table can colour the CRC value. [XREF: addr-crc-display]
        pec_txt = (r.get("PEC") or "").strip()
        if "✓" in pec_txt:
            pec_valid = True
        elif "✗" in pec_txt:
            pec_valid = False
        else:
            pec_valid = None

        # Parse the HH:MM:SS.mmm time column into a timestamp (today's date).
        ts = time.time()
        tcol = (r.get("Time") or "").strip()
        if tcol:
            try:
                today = datetime.date.today()
                parsed = datetime.datetime.strptime(tcol, "%H:%M:%S.%f").time()
                ts = datetime.datetime.combine(today, parsed).timestamp()
            except ValueError:
                pass

        # Capture CSV v2: integer Hz; empty/absent/garbage -> unknown.
        scl_txt = (r.get("SCL (Hz)") or "").strip()
        scl_hz = int(scl_txt) if scl_txt.isdigit() and int(scl_txt) > 0 else None

        txns.append(I2CTransaction(
            timestamp=ts, address=address, direction=d, data=data,
            nak=nak, start=start, stop=stop, pec_valid=pec_valid,
            scl_hz=scl_hz,
        ))
    return txns
