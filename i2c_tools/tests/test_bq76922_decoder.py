"""
tests/test_bq76922_decoder.py — the BQ76922 decoder (BQ769x2 family),
pinned to TRM-derived vectors (SLUUCG7 April 2024) so edits can't silently
break conversions.

Vector provenance:
  * Safety Alert/Status A/B/C bit maps: TRM Tables 5-1..5-6 (fetched text)
  * Voltage command addresses/units: TRM Table 4-1 (Cell1 0x14 mV,
    Stack 0x34 userV); temperatures: TRM Table 4-7, raw 0.1 K
  * DASTATUS5 byte map: TRM Table 4-5 (Battery Voltage Sum in cV at
    offset 8, CC1 at offset 22)
  * Subcommand protocol: 0x3E/0x3F + buffer/checksum/length, TRM §3.1
  * Battery Status / Alarm bit layout: BQ769x2 family (cross-checked
    against the project's BQStudio reference screenshot)

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_bq76922_decoder.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DECODER = os.path.join(ROOT, "i2c_decoders", "bq76922_decoder.json")
FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def le(word):
    return bytes([word & 0xFF, (word >> 8) & 0xFF])


def make_txn(direction, data, start=1, stop=True, nak=False):
    from core.i2c_controller import I2CTransaction, I2CDirection
    return I2CTransaction(
        timestamp=time.time(), address=0x08,
        direction=I2CDirection.READ if direction == "R" else I2CDirection.WRITE,
        data=bytes(data), start=start, stop=stop, nak=nak)


def test_load_and_vectors():
    print("engine load + TRM vectors")
    import jsonschema
    d = json.load(open(DECODER))
    jsonschema.validate(d, json.load(
        open(os.path.join(ROOT, "schema", "decoder.schema.json"))))
    from core.decode_schema import DecodeSchema
    sch = DecodeSchema.load(DECODER)
    check(len(sch) == 74, f"74 rules loaded ({len(sch)})")
    check(len(sch.display_groups) == 5, "5 display groups")

    def val(reg, payload):
        return sch.extract_value(sch.find_read(0x08, reg), payload)

    check(val(0x14, le(3712)) == 3712, "Cell 1 Voltage 3712 mV (1 mV LSB)")
    check(val(0x14, le(0xFFFF)) == -1, "cell voltage is signed")
    # Int Temperature: 0.1 K raw -> degC: 2981 -> 24.95 C
    v = val(0x68, le(2981))
    check(abs(v - 24.95) < 1e-9, f"Int Temperature 2981 raw -> 24.95 C ({v})")
    check(val(0x34, le(1850)) == 1850,
          "Stack Voltage raw userV (1850 = 18.50 V at default 10 mV)")
    # CC2 signed
    check(val(0x3A, le(0x8000)) == -32768, "CC2 Current signed")


def test_bit_positions():
    print("bit positions vs TRM tables")
    from core.decode_schema import DecodeSchema
    sch = DecodeSchema.load(DECODER)

    def field_at(reg, b):
        rule = sch.find_read(0x08, reg)
        for bf in rule.bit_fields:
            if bf.low <= b <= bf.high:
                if bf.mode == "enum" and bf.names:
                    return bf.names[-1].split("=")[0]
                return getattr(bf, "name", "") or ""
        return None

    # TRM Table 5-1/5-2 (fetched verbatim)
    check(field_at(0x02, 7) == "SCD" and field_at(0x02, 2) == "CUV" and
          field_at(0x02, 1) is None, "Safety Alert A: SCD[7]..CUV[2], 1:0 rsvd")
    # TRM Table 5-4
    check(field_at(0x05, 7) == "OTF" and field_at(0x05, 3) is None and
          field_at(0x05, 0) == "UTC", "Safety Status B: OTF[7], rsvd[3], UTC[0]")
    # TRM Table 5-6: Status C has PTO[2] and HWDF[1], not PTOS
    check(field_at(0x07, 2) == "PTO" and field_at(0x07, 1) == "HWDF",
          "Safety Status C: PTO[2], HWDF[1]")
    check(field_at(0x06, 3) == "PTOS", "Safety Alert C: PTOS[3]")
    # family layout, screenshot-cross-checked
    check(field_at(0x12, 15) == "SLEEP" and field_at(0x12, 0) == "CFGUPDATE",
          "Battery Status: SLEEP[15], CFGUPDATE[0]")
    check(field_at(0x12, 9) == "SEC" and field_at(0x12, 8) == "SEC",
          "Battery Status: SEC spans [9:8]")
    check(field_at(0x62, 15) == "SSBC" and field_at(0x62, 0) == "WAKE",
          "Alarm Status: SSBC[15], WAKE[0]")
    check(field_at(0x7F, 0) == "CHG_FET" and field_at(0x7F, 3) == "PDSG_FET",
          "FET Status bits 3:0 (TRM FET_CONTROL mapping)")


def test_stream_decode(app):
    print("stream decode: direct reads, subcommands, buffer")
    from core.decode_schema import DecodeSchema
    from core.log_model import TransactionLogModel
    sch = DecodeSchema.load(DECODER)
    m = TransactionLogModel(); m.set_schema(sch)

    def t(d, data, stop=True, start=1, nak=False):
        m.add_transaction(make_txn(d, data, start=start, stop=stop, nak=nak))
        return m._entries[-1].decode(sch) or ""

    t("W", [0x14], stop=False)
    r = t("R", le(3695), start=2, nak=True)
    check("Cell 1 Voltage = 3695 mV" in r, f"cell read decodes ({r!r})")

    t("W", [0x03], stop=False)
    r = t("R", [0x88], start=2, nak=True)
    check("SCD=1" in r and "COV=1" in r and "CUV=0" in r,
          "Safety Status A 0x88 -> SCD+COV set")

    # subcommand: write 0x0012 RESET to 0x3E
    r = t("W", [0x3E, 0x12, 0x00])
    check("RESET" in r, f"subcommand write decodes to RESET ({r!r})")

    # DASTATUS5 fields through the buffer read-back path
    t("W", [0x3E, 0x75, 0x00])
    payload = bytearray(32)
    payload[4:6] = le(4200)          # Max Cell Voltage
    payload[8:10] = le(1848)         # Battery Voltage Sum in cV
    payload[22:24] = le(1500)        # CC1 Current
    t("W", [0x40], stop=False)
    r = t("R", list(payload), start=2, nak=True)
    check("Max Cell Voltage = 4200 mV" in r and
          "Battery Voltage Sum = 18480 mV" in r and
          "CC1 Current = 1500 userA" in r,
          f"DASTATUS5 fields decode (cV*10, userA) ({r[:120]!r})")


def test_registers_view(app):
    print("Registers view renders from the decoder")
    from core.decode_schema import DecodeSchema
    from ui.widgets.registers_view import RegisterCache, RegistersView
    from core.log_model import TransactionLogModel
    from PySide6.QtWidgets import QTableWidget
    from ui import theme

    sch = DecodeSchema.load(DECODER)
    cache = RegisterCache(); cache.attach(sch)
    view = RegistersView(sch, 0x08, "BQ76922", cache)
    view.show(); app.processEvents()
    names = []
    for tw in view.findChildren(QTableWidget):
        for row in range(tw.rowCount()):
            item = tw.item(row, 0)
            if item:
                names.append(item.text().split(" ", 1)[-1])
    for want in ("Cell 1 Voltage", "Stack Voltage", "TS1 Temperature",
                 "DEVICE_NUMBER"):
        check(any(want in n for n in names), f"pane row present: {want}")

    m = TransactionLogModel(); m.set_schema(sch)
    m.add_transaction(make_txn("W", [0x12], stop=False))
    m.add_transaction(make_txn("R", [0x00, 0x80], start=2, nak=True))
    app.processEvents()
    bs = sch.find_read(0x08, 0x12)
    _r, hex_items, cells = view._bit_rows[bs.key()]
    by_bit = {b: item for item, b in cells}
    green = theme.get_color("status_active").name()
    check(hex_items[0].text() == "0x8000" and
          by_bit[15].background().color().name() == green and
          by_bit[15].text() == "SLEEP",
          "Battery Status 0x8000: SLEEP green in the matrix")
    view.deleteLater()


def main():
    from ui.common import build_application
    app = build_application(app_name="bq76922-tests", initial_theme="default")
    test_load_and_vectors()
    test_bit_positions()
    test_stream_decode(app)
    test_registers_view(app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
