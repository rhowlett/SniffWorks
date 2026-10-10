"""
tests/test_csv_format.py — capture CSV v2 spec conformance.  [v0.1]
[XREF: csv-format] Pins: a fresh model export is v2 and validates strict;
the user's real capture validates strict (skipped when absent); corrupted
rows are rejected; loader round-trip preserves canonical fields incl. the
v2 SCL column; v1 files (no SCL column) still validate and load.
"""
import os, subprocess, sys, tempfile, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ION_TOOL_SETTINGS",
                      tempfile.NamedTemporaryFile(suffix=".ini", delete=False).name)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
VALIDATOR = os.path.join(ROOT, "tools", "validate_capture_csv.py")
FAILURES = []

def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)

def run(*args):
    return subprocess.run([sys.executable, VALIDATOR, *args],
                          capture_output=True, text=True)

def main():
    from ui.common import build_application
    app = build_application(app_name="csvfmt-tests")
    from core.log_model import TransactionLogModel
    from core.i2c_controller import I2CTransaction, I2CDirection

    m = TransactionLogModel()
    for a, d, data, st, sp, nak, pec, scl in (
            (0x6B, "W", b"\x2e", 1, False, False, None, 400321),
            (0x6B, "R", b"\x40\x00", 2, True, True, True, 399876),
            (0x08, "W", b"", 1, True, True, False, None)):
        m.add_transaction(I2CTransaction(
            timestamp=time.time(), address=a,
            direction=I2CDirection.READ if d == "R" else I2CDirection.WRITE,
            data=data, start=st, stop=sp, nak=nak, pec_valid=pec,
            scl_hz=scl))
    out = tempfile.NamedTemporaryFile(suffix=".csv", delete=False).name
    ok, msg = m.export_csv(out)
    check(ok, f"export_csv succeeds ({msg})")
    r = run(out, "--strict")
    check(r.returncode == 0 and "VALID" in r.stdout,
          "fresh export validates strict")
    lines = open(out, encoding="utf-8").read().splitlines()
    check(lines[0].endswith(",PEC,SCL (Hz)"), "export header is v2 (trailing SCL (Hz))")
    check(lines[1].endswith(",400321") and lines[3].endswith(","),
          "SCL cell: integer Hz, empty when unknown")

    from core.log_model import COL_IDX
    from PySide6.QtCore import Qt
    col = COL_IDX["SCL (Hz)"]
    check(m.headerData(col, Qt.Horizontal) == "SCL", "table header reads SCL")
    check(m.data(m.index(0, col), Qt.DisplayRole) == "400.3 kHz"
          and m.data(m.index(2, col), Qt.DisplayRole) == "",
          "table shows kHz, blank when unknown")

    cap = "/mnt/user-data/uploads/POC_i2c_sys_bq25731_smoke_v0_4.csv"
    if os.path.isfile(cap):
        r = run(cap, "--strict")
        check(r.returncode == 0 and "1231 rows" in r.stdout,
              "real v0_4 capture: 1231 rows VALID (strict)")
    else:
        print("  SKIP  real capture not present")

    bad = out + ".bad.csv"
    txt = open(out, encoding="utf-8").read().replace("0x6B,R", "0x6B,X") \
                                            .replace("Sr", "QQ")
    open(bad, "w", encoding="utf-8").write(txt)
    r = run(bad)
    check(r.returncode == 1 and r.stdout.count("FAIL") >= 2,
          "corrupted Dir/Start rejected")

    from ui.common.capture import load_transactions
    txns = load_transactions(out)
    t = txns[1]
    check(t.address == 0x6B and t.start == 2 and t.stop and t.nak
          and t.pec_valid is True and t.data == b"\x40\x00",
          "loader round-trip preserves canonical fields incl. PEC")
    check(txns[0].scl_hz == 400321 and txns[1].scl_hz == 399876
          and txns[2].scl_hz is None, "loader round-trip preserves SCL (Hz)")

    # replay path: loaded rows re-exported are identical (SCL included)
    m2 = TransactionLogModel()
    for tx in txns:
        m2.add_transaction(tx)
    out2 = out + ".rt.csv"
    m2.export_csv(out2)
    strip = lambda p: [l.split(",", 1)[1] for l in open(p, encoding="utf-8").read().splitlines()]
    check(strip(out2) == strip(out), "load -> re-export is identical (apart from Time)")

    # v1 file (no SCL column) still validates and loads with scl_hz None
    v1 = out + ".v1.csv"
    open(v1, "w", encoding="utf-8").write(
        "Time,#,Addr,Dir,Len,Data (hex),Int,ASCII,Decode,NAK,Start,Stop,PEC\n"
        "19:52:47.479,,0x6B,W,,2E,,,,,S,,\n"
        "19:52:47.479,,0x6B,R,,40 00,,,,,Sr,P,\n")
    r = run(v1)
    check(r.returncode == 0 and "2 rows, VALID" in r.stdout, "v1 file validates")
    v1t = load_transactions(v1)
    check(len(v1t) == 2 and all(x.scl_hz is None for x in v1t),
          "v1 file loads with scl_hz None")

    # bad SCL cell rejected
    bad2 = out + ".badscl.csv"
    open(bad2, "w", encoding="utf-8").write(
        open(out, encoding="utf-8").read().replace(",400321", ",fast"))
    r = run(bad2)
    check(r.returncode == 1 and "SCL (Hz)" in r.stdout, "non-integer SCL rejected")
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0

if __name__ == "__main__":
    sys.exit(main())
