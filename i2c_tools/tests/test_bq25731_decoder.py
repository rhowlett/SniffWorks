"""
tests/test_bq25731_decoder.py — the full BQ25731 decoder (SLUSE66A,
10 mOhm RSR/RAC) pinned to datasheet-derived vectors so future edits can't
silently break scalings.

Vector provenance (all from the datasheet):
  * ChargeVoltage resets: 4S = 0x41A0 -> 16800 mV, 5S = 0x5208 -> 21000 mV
  * ChargeCurrent EC-table code 0x1000 -> 4096 mA at 10 mOhm
  * IIN_DPM reset 0x4100 -> 3250 mA at 10 mOhm (code 65 x 50 mA)
  * OTGVoltage reset 0x09C4 -> 5000 mV
  * VINDPM fixed 3200 mV offset at code 0
  * Bit positions spot-checked: STAT_AC=15, Fault ACOV=7 (ChargerStatus),
    EN_LWPWR=15, CHRG_INHIBIT=0, WDTMR_ADJ=[14:13] (ChargeOption0)

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_bq25731_decoder.py
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

DECODER = os.path.join(ROOT, "i2c_decoders", "bq25731_decoder.json")
FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def le(word):
    return bytes([word & 0xFF, word >> 8])


def make_txn(direction, data, start=1, stop=True, nak=False):
    from core.i2c_controller import I2CTransaction, I2CDirection
    return I2CTransaction(
        timestamp=time.time(), address=0x6B,
        direction=I2CDirection.READ if direction == "R" else I2CDirection.WRITE,
        data=bytes(data), start=start, stop=stop, nak=nak)


def test_load_and_vectors():
    print("engine load + datasheet vectors")
    import jsonschema
    d = json.load(open(DECODER))
    jsonschema.validate(d, json.load(
        open(os.path.join(ROOT, "schema", "decoder.schema.json"))))
    from core.decode_schema import DecodeSchema
    sch = DecodeSchema.load(DECODER)
    check(len(sch) == 48, f"48 rules loaded ({len(sch)})")
    check(len(sch.display_groups) == 5, "5 display groups")

    def val(reg, word):
        rule = sch.find_read(0x6B, reg)
        return sch.extract_value(rule, le(word))

    check(val(0x04, 0x41A0) == 16800, "ChargeVoltage 0x41A0 -> 16800 mV (4S)")
    check(val(0x04, 0x5208) == 21000, "ChargeVoltage 0x5208 -> 21000 mV (5S)")
    check(val(0x02, 0x1000) == 4096, "ChargeCurrent 0x1000 -> 4096 mA @10mOhm")
    check(val(0x02, 0xE000) == 0, "ChargeCurrent reserved bits masked out")
    check(val(0x24, 0x4100) == 3250, "IIN_DPM reset 0x4100 -> 3250 mA")
    check(val(0x06, 0x09C4) == 5000, "OTGVoltage reset 0x09C4 -> 5000 mV")
    check(val(0x0A, 0x0000) == 3200, "VINDPM code 0 -> 3200 mV offset")
    check(val(0x08, 0x3C00) == 3000, "OTGCurrent reset 0x3C00 -> 3000 mA")
    check(val(0x0E, 0x2000) == 1600, "IIN_HOST 0x2000 -> 1600 mA @10mOhm")

    # byte-alias rules for one-byte-at-a-time hosts
    # byte-alias rules (single-byte reads at the odd/high registers)
    a = sch.find_read(0x6B, 0x27)
    check(a is not None and sch.extract_value(a, b"\x7d") == 12000,
          "VBUS byte alias 0x7D -> 12000 mV")
    a = sch.find_read(0x6B, 0x2D)
    check(sch.extract_value(a, b"\xbe") == 15040,
          "VSYS byte alias 0xBE -> 15040 mV")
    a = sch.find_read(0x6B, 0x25)
    check(sch.extract_value(a, b"\x41") == 3250,
          "IIN_DPM byte alias 0x41 -> 3250 mA")
    # a truncated word read must not fabricate offset-1 channel values
    adc = sch.find_read(0x6B, 0x2C)
    txt = sch._render_fields(adc, b"\x55")
    check("VSYS = \u2014" in txt and "8320" in txt,
          "1-byte read: VBAT decodes, VSYS honestly absent")

    # write rules mirror the read scaling
    wr = sch.find_write(0x6B, 0x02)
    check(wr is not None and sch.extract_value(wr, le(0x0800)) == 2048,
          "ChargeCurrent (set) write rule scales identically")


def test_bit_positions():
    print("bit-field positions vs datasheet")
    from core.decode_schema import DecodeSchema
    sch = DecodeSchema.load(DECODER)

    def field_at(reg, bit):
        rule = sch.find_read(0x6B, reg)
        for bf in rule.bit_fields:
            if bf.low <= bit <= bf.high:
                if bf.mode == "enum" and bf.names:
                    return bf.names[-1].split("=")[0]
                return getattr(bf, "description", "")
        return None

    check(field_at(0x20, 15) == "STAT_AC", "ChargerStatus[15] = STAT_AC")
    check(field_at(0x20, 7) == "Fault ACOV", "ChargerStatus[7] = Fault ACOV")
    check(field_at(0x20, 9) is None, "ChargerStatus[9] reserved (gray)")
    check(field_at(0x22, 15) is None, "ProchotStatus[15] reserved")
    check(field_at(0x22, 14) == "EN_PROCHOT_EXT",
          "ProchotStatus[14] = EN_PROCHOT_EXT (wrapped name rejoined)")
    check(field_at(0x22, 7) == "STAT_VINDPM",
          "ProchotStatus[7] = STAT_VINDPM (low byte)")
    check(field_at(0x00, 15) == "EN_LWPWR", "ChargeOption0[15] = EN_LWPWR")
    check(field_at(0x00, 0) == "CHRG_INHIBIT", "ChargeOption0[0]")
    check(field_at(0x00, 13) == "WDTMR_ADJ" and
          field_at(0x00, 14) == "WDTMR_ADJ",
          "WDTMR_ADJ spans [14:13] (multi-bit raw)")
    total = sum(len(sch.find_read(0x6B, r).bit_fields)
                for r in (0x00, 0x20, 0x22, 0x30, 0x32, 0x34, 0x36, 0x38,
                          0x3A, 0x3C, 0x3E))
    check(total == 133, f"133 named bit fields across 11 registers ({total})")


def test_pointer_styles():
    print("pointer persistence: restart AND stop-separated register reads")
    from core.decode_schema import DecodeSchema, StreamDecoder
    sch = DecodeSchema.load(DECODER)
    sd = StreamDecoder(sch)

    # stop-separated (this user's host): W [reg] P ... S R [data] P
    sd.feed(0x6B, "W", b"\x2e", had_stop=True)
    r = sd.feed(0x6B, "R", b"\x40\xd6", had_stop=True)
    check("Manufacturer ID = 0x40" in (r.text or ""),
          "stop-separated pointer read decodes")

    # restart style (BQ76905-host pattern) still pairs
    sd.feed(0x6B, "W", b"\x26", had_stop=False)
    r = sd.feed(0x6B, "R", b"\x00\x9d", had_stop=True, repeated_start=True)
    check("VBUS = 15072 mV" in (r.text or ""),
          "restart-style read still decodes (VBUS from user capture bytes)")

    # read-back after an indexed write decodes against that register
    sd.feed(0x6B, "W", b"\x20\x00\x80", had_stop=True)
    r = sd.feed(0x6B, "R", b"\x00\x80", had_stop=True)
    check("ChargerStatus" in (r.text or ""),
          "plain read after indexed write decodes (pointer left at reg)")

    # pointer is consumed: a second plain read has no context
    r = sd.feed(0x6B, "R", b"\x00\x80", had_stop=True)
    check("ChargerStatus" not in (r.text or ""),
          "pointer consumed by the read (no stale re-decode)")


def test_registers_view(app):
    print("Registers view: ADC channel rows + live decode")
    from core.decode_schema import DecodeSchema
    from ui.widgets.registers_view import RegisterCache, RegistersView
    from core.log_model import TransactionLogModel
    from PySide6.QtWidgets import QTableWidget

    sch = DecodeSchema.load(DECODER)
    cache = RegisterCache()
    cache.attach(sch)
    view = RegistersView(sch, 0x6B, "BQ25731", cache)
    view.show(); app.processEvents()

    # ADC pane: 4 fields-rules expand to 8 channel rows
    names = []
    for t in view.findChildren(QTableWidget):
        for row in range(t.rowCount()):
            item = t.item(row, 0)
            if item:
                names.append(item.text().split(" ", 1)[-1])
    for ch in ("PSYS", "VBUS", "IDCHG", "ICHG", "CMPIN", "IIN",
               "VBAT", "VSYS"):
        check(ch in names, f"ADC channel row present: {ch}")

    model = TransactionLogModel()
    model.set_schema(sch)
    # SMBus word read of ADCIBAT: IDCHG=0x02 (512 mA), ICHG=0x10 (1024 mA)
    model.add_transaction(make_txn("W", [0x28], stop=False))
    model.add_transaction(make_txn("R", [0x02, 0x10], start=2, nak=True))
    app.processEvents()
    rule = sch.find_read(0x6B, 0x28)
    cells = dict((f.name, c) for f, c in view._scalar_cells[rule.key()][1])
    check(cells["IDCHG"].text() == "512", "IDCHG cell = 512 mA (0x02*256)")
    check(cells["ICHG"].text() == "1024", "ICHG cell = 1024 mA (0x10*64)")

    # ChargerStatus 0x8040: STAT_AC (15) and Fault ACOV... 0x8040 -> bit 6?
    # use 0x8080: STAT_AC + Fault ACOV
    model.add_transaction(make_txn("W", [0x20], stop=False))
    model.add_transaction(make_txn("R", [0x80, 0x80], start=2, nak=True))
    app.processEvents()
    from ui import theme
    red = theme.get_color("status_error").name()
    green = theme.get_color("status_active").name()
    bs = sch.find_read(0x6B, 0x20)
    _r, hex_items, bit_cells = view._bit_rows[bs.key()]
    by_bit = {bit: item for item, bit in bit_cells}
    check(hex_items[0].text() == "0x8080", "ChargerStatus hex 0x8080")
    check(by_bit[15].background().color().name() == green and
          by_bit[15].text() == "STAT_AC", "STAT_AC set -> green (v1.1)")
    check(by_bit[7].background().color().name() == green and
          by_bit[7].text() == "Fault ACOV", "Fault ACOV set -> green")
    check(by_bit[14].background().color().name() == red,
          "ICO_DONE=0 -> red (v1.1: zero = red)")

    # multi-bit field: value paints the RGB background. ChargeOption0's
    # WDTMR_ADJ is [14:13]; write 0x6000 -> field value 3 -> #000003, which
    # is invisible on the dark bg -> complement #FFFFFC, black text.
    model.add_transaction(make_txn("W", [0x00], stop=False))
    model.add_transaction(make_txn("R", [0x00, 0x60], start=2, nak=True))
    app.processEvents()
    co0 = sch.find_read(0x6B, 0x00)
    _r2, _h2, cells2 = view._bit_rows[co0.key()]
    bb = {bit: item for item, bit in cells2}
    c = bb[13].background().color()
    check(c.name().upper() == "#FFFFFC",
          f"multi-bit value 3 -> #000003 complements to #FFFFFC ({c.name()})")
    check(bb[13].foreground().color().name() == "#000000",
          "light cell gets black text")
    check(bb[14].background().color() == bb[13].background().color(),
          "all cells of the field share the field color")
    # a bright multi-bit value used directly (no complement): value 0x39
    # in a 6-bit field -> still small -> complements; use PROCHOT-style?
    # keep coverage simple: zero multi-bit field is red
    model.add_transaction(make_txn("W", [0x00], stop=False))
    model.add_transaction(make_txn("R", [0x00, 0x00], start=2, nak=True))
    app.processEvents()
    check(bb[13].background().color().name() == red,
          "multi-bit field value 0 -> red")
    view.deleteLater()


def test_replay_window_registers(app):
    print("replay window: Registers tab from a loaded capture (user CSV)")
    import shutil
    from ui.replay_window import ReplayWindow
    from ui import theme

    cap = "/mnt/user-data/uploads/POC_i2c_sys_bq25731_smoke_v0_4.csv"
    if not os.path.isfile(cap):
        print("  SKIP  capture not present in this environment")
        return
    win = ReplayWindow()
    win.show(); app.processEvents()
    win._load_decoder_section.add_decoder(DECODER)
    win._load_capture_section.picker.set_path(cap)
    app.processEvents()

    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    check("BQ25731" in labels, f"BQ25731 Registers tab present ({labels})")
    view = win.tabs.widget(labels.index("BQ25731"))

    from core.decode_schema import DecodeSchema
    sch = view._schema
    green = theme.get_color("status_active").name()
    red = theme.get_color("status_error").name()
    bs = sch.find_read(0x6B, 0x20)
    _r, hex_items, cells = view._bit_rows[bs.key()]
    by_bit = {bit: item for item, bit in cells}
    check(hex_items[0].text() == "0x8200",
          f"ChargerStatus populated from the capture ({hex_items[0].text()})")
    check(by_bit[15].background().color().name() == green,
          "STAT_AC=1 -> GREEN in the replay window")
    check(by_bit[14].background().color().name() == red,
          "ICO_DONE=0 -> red")
    # VBUS scalar row carries the adapter voltage from the capture
    adc = sch.find_read(0x6B, 0x26)
    cells26 = dict((f.name, c) for f, c in view._scalar_cells[adc.key()][1])
    check(cells26["VBUS"].text() == "15072",
          "VBUS = 15072 mV in the Registers pane")
    win._log.clear_log() if hasattr(win._log, "clear_log") else None
    win.close(); app.processEvents()


def test_replay_scrub(app):
    print("replay scrub: device tab tracks the selected log row")
    from ui.replay_window import ReplayWindow
    from ui import theme
    from ui.widgets.registers_view import NO_VALUE

    cap = "/mnt/user-data/uploads/POC_i2c_sys_bq25731_smoke_v0_4.csv"
    if not os.path.isfile(cap):
        print("  SKIP  capture not present in this environment")
        return
    win = ReplayWindow()
    win.show(); app.processEvents()
    win._load_decoder_section.add_decoder(DECODER)
    win._load_capture_section.picker.set_path(cap)
    app.processEvents()
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    view = win.tabs.widget(labels.index("BQ25731"))
    sch = view._schema
    mfr = sch.find_read(0x6B, 0x2E)
    bs = sch.find_read(0x6B, 0x20)
    mfr_cell = view._scalar_cells[mfr.key()][1][0][1]
    _r, bs_hex, bs_cells = view._bit_rows[bs.key()]
    by_bit = {bit: item for item, bit in bs_cells}
    green = theme.get_color("status_active").name()
    gray = theme.get_color("bg_tertiary").name()

    entries = win._log.model._entries
    # user's example: the row BEFORE any successful read (the sweep /
    # pointer write at ~19:52:47.458) -> nothing set yet
    first_read = next(i for i, e in enumerate(entries)
                      if e.txn.address == 0x6B and e.txn.data and
                      e.txn.direction.name == "READ")
    win._on_log_row_selected(first_read - 1)
    app.processEvents()
    check(mfr_cell.text() == NO_VALUE,
          "row before first read: Manufacturer ID unset (\u2014)")
    check(bs_hex[0].text() == NO_VALUE and
          by_bit[15].background().color().name() == gray,
          "row before first read: ChargerStatus neutral")

    # the row of the ID read itself (~19:52:47.479): IDs present; and by
    # the ChargerStatus read a few rows later, its bit fields are colored
    win._on_log_row_selected(first_read)
    app.processEvents()
    check(mfr_cell.text() == "0x40",
          "at the ID-read row: Manufacturer ID = 0x40")
    cs_read = next(i for i, e in enumerate(entries)
                   if i > first_read and e.txn.address == 0x6B and
                   e.txn.direction.name == "READ" and
                   len(e.txn.data) == 2 and entries[i-1].txn.data
                   and entries[i-1].txn.data[0] == 0x20)
    win._on_log_row_selected(cs_read)
    app.processEvents()
    check(bs_hex[0].text() == "0x8200" and
          by_bit[15].background().color().name() == green,
          "at the status-read row: ChargerStatus 0x8200, STAT_AC green")

    # scrub BACK: state must rewind, not stick
    win._on_log_row_selected(first_read - 1)
    app.processEvents()
    check(mfr_cell.text() == NO_VALUE and bs_hex[0].text() == NO_VALUE,
          "scrubbing back rewinds the state")

    # selection cleared (-1): full-capture state returns
    win._on_log_row_selected(-1)
    app.processEvents()
    check(mfr_cell.text() == "0x40" and bs_hex[0].text() == "0x8200",
          "selection cleared: full-capture state restored")

    # the actual table wiring: selecting a view row emits the entry index
    got = []
    win._log.row_selected.connect(got.append)
    win._log._table.selectRow(first_read)
    app.processEvents()
    check(bool(got) and got[-1] == first_read,
          f"table selection emits the source entry index ({got[-1:]})")
    win.close(); app.processEvents()


def main():
    from ui.common import build_application
    app = build_application(app_name="bq25731-tests", initial_theme="default")
    test_load_and_vectors()
    test_bit_positions()
    test_pointer_styles()
    test_registers_view(app)
    test_replay_window_registers(app)
    test_replay_scrub(app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
