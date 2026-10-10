#!/usr/bin/env python3
"""
tools/ion_capture.py  [v0.2]
Headless capture from the ion probe (NUCLEO-C031C6 sniffer firmware, bit-bang
mode) to a capture CSV v2 file, identical to the sniffer_ion GUI's Export CSV
(same TransactionLogModel, so the loopback harness and the replay tool read
it unchanged).

Stops at the first of: --seconds elapsed, --count transactions kept (after the
filters), or Ctrl-C. Then stops the probe, asks for a final STATUS and prints
it, including the fw >= 1.4 sampler diagnostics (PROTOCOL.md 1.2.1).

Filters (all optional, combined with AND):
  --addr 0x6B,0x55      keep only these 7-bit addresses
  --exclude-addr 0x08   drop these addresses
  --dir R|W             keep only reads or writes
  --nak only|none       keep only NAKed phases / only non-NAKed phases
  --min-len N --max-len N   data byte count bounds

Examples:
  python tools/ion_capture.py --seconds 30 --out loopback_dut/runs/ion_capture.csv \\
         --pec --decoder i2c_decoders/loopback_dut_decoder.json
  python tools/ion_capture.py --count 100 --addr 0x6B --dir R --out reads.csv
  python tools/ion_capture.py --port /dev/cu.usbmodem11203 --seconds 5 --status-only
  python tools/ion_capture.py --port "C031 sniffer" --seconds 5 --status-only

--port takes a port path, a USB serial number, or a device name given with
tools/device_names.py (or the apps' "Name devices…" button).

Exit status: 0 capture written; 1 no probe / link error; 2 nothing matched.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ---------------------------------------------------------------- filters
def _addr_list(text: str) -> set[int]:
    out = set()
    for t in text.split(","):
        t = t.strip()
        if t:
            v = int(t, 0)
            if not 0 <= v <= 0x7F:
                raise argparse.ArgumentTypeError(f"{t}: not a 7-bit address")
            out.add(v)
    return out


@dataclass
class TxnFilter:
    addrs: Optional[set[int]] = None
    exclude: set[int] = field(default_factory=set)
    direction: Optional[str] = None          # "R" | "W"
    nak: Optional[str] = None                # "only" | "none"
    min_len: Optional[int] = None
    max_len: Optional[int] = None

    def __call__(self, t) -> bool:
        if self.addrs is not None and t.address not in self.addrs:
            return False
        if t.address in self.exclude:
            return False
        if self.direction and t.dir_str != self.direction:
            return False
        if self.nak == "only" and not t.nak:
            return False
        if self.nak == "none" and t.nak:
            return False
        if self.min_len is not None and len(t.data) < self.min_len:
            return False
        if self.max_len is not None and len(t.data) > self.max_len:
            return False
        return True


# ---------------------------------------------------------------- capture
@dataclass
class CaptureResult:
    kept: list = field(default_factory=list)
    seen: int = 0
    framing: int = 0
    device_errors: list = field(default_factory=list)
    hello: Optional[dict] = None
    status: Optional[dict] = None
    stopped_by: str = ""


def run_capture(port, seconds: Optional[float], count: Optional[int],
                keep: Callable = lambda t: True, check_pec: bool = False,
                status_only: bool = False, log=print,
                clock=time.monotonic, sleep=time.sleep) -> CaptureResult:
    """Drive one capture over a serial-like `port` (write/read)."""
    from core.ion_backend import IonLink

    res = CaptureResult()
    link = IonLink(port, check_pec=check_pec)

    def on_txn(t):
        res.seen += 1
        if status_only:
            return
        if count is not None and len(res.kept) >= count:
            return
        if keep(t):
            res.kept.append(t)

    def on_err(msg):
        if msg.startswith("framing error"):
            res.framing += 1
        else:
            res.device_errors.append(msg)

    link.on_transaction = on_txn
    link.on_error = on_err
    if not link.handshake():
        raise RuntimeError("no HELLO from the probe (wrong port, or not the sniffer firmware?)")
    res.hello = link.hello
    log(f"probe: fw {link.hello['fw']}, mode {link.hello['mode']}")
    link.start_capture()
    t0 = clock()
    try:
        while True:
            if link.pump() == 0:
                sleep(0.005)
            if count is not None and len(res.kept) >= count:
                res.stopped_by = f"count {count}"
                break
            if seconds is not None and clock() - t0 >= seconds:
                res.stopped_by = f"{seconds:g} s"
                break
    except KeyboardInterrupt:
        res.stopped_by = "Ctrl-C"
    # let frames already queued on the probe drain before STOP (the probe
    # only flushes its ring while capturing)
    t1 = clock()
    while clock() - t1 < 0.3:
        if link.pump() == 0:
            sleep(0.005)
    link.stop_capture()
    link.request_status()
    t2 = clock()
    while clock() - t2 < 0.5:
        if link.pump() == 0:
            sleep(0.005)
    res.status = link.last_status
    return res


def export_csv(txns, out: str, decoders: list[str]) -> tuple[bool, str]:
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication(["ion_capture"])  # noqa: F841
    from core.log_model import TransactionLogModel
    m = TransactionLogModel()
    if decoders:
        from core.decoder_manager import DecoderSetManager
        mgr = DecoderSetManager()
        for d in decoders:
            ok, msg = mgr.add(d)
            if not ok:
                return False, f"decoder {d}: {msg}"
        m.set_schema(mgr.merged_schema(multiline_bits=False))
    for t in txns:
        m.add_transaction(t)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    return m.export_csv(out)


def format_status(st: Optional[dict]) -> str:
    if not st:
        return "STATUS: none received"
    lines = [f"STATUS: fw {st['fw']} mode {st['mode']} captured {st['captured']} "
             f"errors {st['errors']} dropped {st['dropped']} bus {st['bus_hz']} Hz"]
    d = st.get("diag")
    if d:
        lines.append("  sampler diag (fw >= 1.4, transaction open):")
        lines.append(f"    longest sample gap   {d['max_gap_us']} us   gaps > 2 us: {d['gaps_over_2us']}")
        lines.append(f"    narrowest SCL high   {d['min_scl_high_us']} us   low: {d['min_scl_low_us']} us")
        lines.append(f"    FRAMING phases       {d['framing_phases']}   worst gap {d['framing_max_gap_us']} us, "
                     f"narrowest high {d['framing_min_scl_high_us']} us")
        lines.append(f"    upkeep deferred      {d['upkeep_deferred']}")
    return "\n".join(lines)


def find_probe(baud: int, log=print) -> Optional[str]:
    """First serial port that answers HELLO as the sniffer (ST-LINK first)."""
    import serial
    from core.ion_backend import IonLink, list_serial_ports
    for p in list_serial_ports():
        try:
            with serial.Serial(p["device"], baud, timeout=0.05) as s:
                link = IonLink(s)
                if link.handshake():
                    named = f"'{p['name']}' " if p.get("name") else ""
                    log(f"found probe {named}on {p['device']} ({p['description']})")
                    return p["device"]
        except Exception:      # noqa: BLE001 - busy / not a probe: keep looking
            continue
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--port", help="probe serial port, USB serial number or device "
                                   "name (default: auto-detect)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", help="capture CSV v2 to write (required unless --status-only)")
    ap.add_argument("--seconds", type=float, help="stop after this long")
    ap.add_argument("--count", type=int, help="stop after this many KEPT transactions")
    ap.add_argument("--addr", type=_addr_list)
    ap.add_argument("--exclude-addr", type=_addr_list, default=set())
    ap.add_argument("--dir", choices=["R", "W"])
    ap.add_argument("--nak", choices=["only", "none"])
    ap.add_argument("--min-len", type=int)
    ap.add_argument("--max-len", type=int)
    ap.add_argument("--pec", action="store_true", help="validate SMBus PEC (GUI checkbox)")
    ap.add_argument("--decoder", action="append", default=[],
                    help="decoder JSON for the Decode column (repeatable)")
    ap.add_argument("--status-only", action="store_true",
                    help="capture for --seconds and print STATUS/diag; write no CSV")
    a = ap.parse_args(argv)
    if a.seconds is None and a.count is None:
        ap.error("give --seconds and/or --count")
    if not a.status_only and not a.out:
        ap.error("--out is required (or use --status-only)")

    import serial
    if a.port:
        from core.device_names import resolve_port
        try:
            port_name = resolve_port(a.port)
        except LookupError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    else:
        port_name = find_probe(a.baud)
    if not port_name:
        print("no ion probe found (close sniffer_ion first: one program per port)", file=sys.stderr)
        return 1
    keep = TxnFilter(addrs=a.addr, exclude=a.exclude_addr, direction=a.dir, nak=a.nak,
                     min_len=a.min_len, max_len=a.max_len)
    try:
        with serial.Serial(port_name, a.baud, timeout=0.05) as s:
            res = run_capture(s, a.seconds, a.count, keep, a.pec, a.status_only)
    except (RuntimeError, serial.SerialException) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"stopped by {res.stopped_by}: kept {len(res.kept)} of {res.seen} transactions; "
          f"FRAMING-flagged {res.framing}; device errors {len(res.device_errors)}")
    for e in res.device_errors[:10]:
        print(f"  device: {e}")
    print(format_status(res.status))
    if a.status_only:
        return 0
    ok, msg = export_csv(res.kept, a.out, a.decoder)
    if not ok:
        print(f"export failed: {msg}", file=sys.stderr)
        return 1
    print(f"wrote {a.out} ({len(res.kept)} rows)")
    return 0 if res.kept else 2


if __name__ == "__main__":
    sys.exit(main())
