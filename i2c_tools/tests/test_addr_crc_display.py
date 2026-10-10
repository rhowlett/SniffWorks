"""
tests/test_addr_crc_display.py — offscreen checks for the shared log table's
display toggles: 7-bit vs 8-bit address view, CRC/PEC green-red coloring, and the
PEC round-trip through the capture-CSV loader.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_addr_crc_display.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys, csv, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.common import build_application  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from core.log_model import TransactionLogModel, COLUMNS, COL_IDX  # noqa: E402
from core.i2c_controller import I2CTransaction, I2CDirection  # noqa: E402
from ui import theme  # noqa: E402
from ui.common import load_transactions  # noqa: E402


def _model():
    m = TransactionLogModel()
    m.add_transaction(I2CTransaction(timestamp=0, address=0x08, direction=I2CDirection.WRITE,
                                     data=b"\x14", nak=False, start=1, stop=True, pec_valid=None))
    m.add_transaction(I2CTransaction(timestamp=0, address=0x08, direction=I2CDirection.READ,
                                     data=b"\xf0\x0a", nak=False, start=2, stop=True, pec_valid=True))
    m.add_transaction(I2CTransaction(timestamp=0, address=0x08, direction=I2CDirection.READ,
                                     data=b"\xde\xad", nak=False, start=2, stop=True, pec_valid=False))
    return m


def _disp(m, r, c):
    return m.data(m.index(r, COL_IDX[c]), Qt.DisplayRole)


def _fg(m, r, c):
    return m.data(m.index(r, COL_IDX[c]), Qt.ForegroundRole)


def test_addr_7bit_default():
    m = _model()
    assert _disp(m, 0, "Addr") == "0x08" and _disp(m, 0, "Dir") == "W"
    assert _disp(m, 1, "Addr") == "0x08" and _disp(m, 1, "Dir") == "R"


def test_addr_8bit_folds_rw():
    m = _model()
    m.set_addr_8bit(True)
    assert _disp(m, 0, "Addr") == "0x10" and _disp(m, 0, "Dir") == "W (bit0)"  # write even
    assert _disp(m, 1, "Addr") == "0x11" and _disp(m, 1, "Dir") == "R (bit0)"  # read odd
    m.set_addr_8bit(False)
    assert _disp(m, 1, "Addr") == "0x08" and _disp(m, 1, "Dir") == "R"


def test_crc_coloring_and_blanking():
    m = _model()
    green = theme.get_color("status_active")
    red = theme.get_color("status_error")
    assert _fg(m, 1, "PEC") == green   # valid
    assert _fg(m, 2, "PEC") == red     # invalid
    # unchecked pec (row 0) shows no value and no override
    assert _disp(m, 0, "PEC") == ""
    # turning CRC display off blanks the value and drops the override
    m.set_show_crc(False)
    assert _disp(m, 2, "PEC") == "" and _fg(m, 2, "PEC") != red


def test_export_stays_7bit_even_in_8bit_view():
    m = _model()
    m.set_addr_8bit(True)   # display 8-bit...
    path = os.path.join(tempfile.mkdtemp(), "e.csv")
    ok, _ = m.export_csv(path)
    assert ok
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["Addr"] == "0x08" and rows[0]["Dir"] == "W"   # canonical, not 8-bit


def test_replay_restores_pec_valid():
    path = os.path.join(tempfile.mkdtemp(), "c.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([c for c, _ in COLUMNS])
        w.writerow(["00:00:00.000", "1", "0x08", "R", "2", "DE AD", "57005", "..",
                    "", "", "Sr", "P", "✗ PEC"])
        w.writerow(["00:00:00.001", "2", "0x08", "R", "2", "F0 0A", "61450", "..",
                    "", "", "Sr", "P", "✓ PEC"])
    txns = load_transactions(path)
    assert txns[0].pec_valid is False and txns[1].pec_valid is True


def _run():
    build_application(app_name="AddrCRC Test", version="1.0.0",
                      org="Digilent AD2 Utils", initial_theme="dark")
    tests = [
        ("addr_7bit_default", test_addr_7bit_default),
        ("addr_8bit_folds_rw", test_addr_8bit_folds_rw),
        ("crc_coloring_and_blanking", test_crc_coloring_and_blanking),
        ("export_stays_7bit", test_export_stays_7bit_even_in_8bit_view),
        ("replay_restores_pec_valid", test_replay_restores_pec_valid),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn(); print(f"  PASS  {name}"); passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            print(f"  ERROR {name}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
