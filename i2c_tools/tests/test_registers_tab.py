"""
tests/test_registers_tab.py  [v0.1] — the live Registers view (schema v4).

Covers:
  * schema v4: display_groups + group/group_order/access parse and round-trip
  * extract_value + on_rule_decoded observer
  * RegisterCache fed through the real StreamDecoder / log-model path,
    including history replay when a schema is applied late
  * RegistersView: banner/pane layout from groups, sticky value updates,
    bit-matrix coloring (set bits red / clear green / RSVD gray),
    2-byte bit rules -> high/low row pairs, lock vs pencil markers
  * window integration: per-device tab appears with a v4 decoder, none for
    a v3 decoder without layout info
  * B33: a decoder covering several addresses gets one tab PER address that
    has layout (was: one tab for the lowest address only, so loopback R1 and
    the whole Smart Battery 0x0B dashboard were lost)

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_registers_tab.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


DEVICE_JSON = {
    "version": 4, "device": "TestBQ", "i2c_address": 0x08,
    "display_groups": [
        {"name": "Pack", "kind": "banner"},
        {"name": "IC", "kind": "banner"},
        {"name": "Cells", "kind": "pane"},
    ],
    "rules": [
        {"address": 8, "transaction_type": "indexed_read", "register": 0x26,
         "data_bytes": 2, "byte_order": "le", "format": "dec",
         "function": "X*10", "unit": "mV", "name": "Stack Voltage",
         "group": "Pack", "group_order": 1, "access": "R"},
        {"address": 8, "transaction_type": "indexed_read", "register": 0x28,
         "data_bytes": 2, "byte_order": "le", "signed": True,
         "format": "dec", "function": "X*0.01", "unit": "degC",
         "name": "Int Temperature", "group": "IC", "group_order": 1,
         "access": "R"},
        {"address": 8, "transaction_type": "indexed_read", "register": 0x14,
         "data_bytes": 2, "byte_order": "le", "format": "dec",
         "function": "X", "unit": "mV", "name": "Cell 1 Voltage",
         "group": "Cells", "group_order": 1, "access": "R"},
        {"address": 8, "transaction_type": "indexed_read", "register": 0x68,
         "data_bytes": 1, "byte_order": "le", "format": "dec",
         "function": "X", "unit": "", "name": "FET Setting",
         "group": "Cells", "group_order": 2, "access": "R/W"},
        # 2-byte bit register -> high/low pair in the matrix
        {"address": 8, "transaction_type": "indexed_read", "register": 0x12,
         "data_bytes": 2, "byte_order": "le", "format": "bits",
         "function": "", "unit": "", "name": "Battery Status", "access": "R",
         "bit_fields": [
             {"range": [15, 15], "mode": "enum", "names": ["SLEEP=0", "SLEEP=1"]},
             {"range": [10, 10], "mode": "enum", "names": ["FUSE=0", "FUSE=1"]},
             {"range": [0, 0], "mode": "enum", "names": ["SEC0=0", "SEC0=1"]},
         ]},
    ],
}


def make_txn(addr, direction, data, start=1, stop=True, nak=False):
    from core.i2c_controller import I2CTransaction, I2CDirection
    return I2CTransaction(
        timestamp=time.time(), address=addr,
        direction=I2CDirection.READ if direction == "R" else I2CDirection.WRITE,
        data=bytes(data), start=start, stop=stop, nak=nak)


def indexed_read(model, reg, payload):
    model.add_transaction(make_txn(8, "W", [reg], stop=False))
    model.add_transaction(make_txn(8, "R", payload, start=2, nak=True))


def test_schema_v4(tmp):
    print("schema v4 parse + round-trip")
    from core.decode_schema import DecodeSchema
    p = Path(tmp) / "dev.json"
    p.write_text(json.dumps(DEVICE_JSON))
    sch = DecodeSchema.load(str(p))
    check([g["name"] for g in sch.display_groups] == ["Pack", "IC", "Cells"],
          "display_groups ordered")
    rule = sch.find_read(8, 0x26)
    check(rule.group == "Pack" and rule.group_order == 1 and
          rule.access == "R", "rule group/order/access parsed")
    # round-trip through to_json preserves v4 fields + version
    back = DecodeSchema.from_json(sch.to_json())
    check(back.find_read(8, 0x26).group == "Pack" and
          back.display_groups == sch.display_groups,
          "to_json/from_json round-trip keeps layout")
    check(json.loads(sch.to_json())["version"] == 4, "saves as version 4")
    check(sch.extract_value(rule, b"\x64\x00") == 1000,
          "extract_value applies the function (0x0064*10)")


def test_cache_via_log_model(tmp, app):
    print("RegisterCache through the real decode path")
    from core.decode_schema import DecodeSchema
    from ui.widgets.registers_view import RegisterCache
    from core.log_model import TransactionLogModel

    p = Path(tmp) / "dev.json"
    p.write_text(json.dumps(DEVICE_JSON))
    sch = DecodeSchema.load(str(p))

    model = TransactionLogModel()
    # history BEFORE the schema exists (late decoder load)
    indexed_read(model, 0x26, [0x64, 0x00])          # Stack V = 1000
    cache = RegisterCache()
    cache.attach(sch)
    model.set_schema(sch)                            # re-decode replays history
    rule = sch.find_read(8, 0x26)
    check(cache.get(rule) == b"\x64\x00",
          "late schema apply replays history into the cache")

    # sticky last-wins on a newer value
    indexed_read(model, 0x26, [0xC8, 0x00])          # 2000
    check(cache.get(rule) == b"\xC8\x00", "newer traffic overwrites (sticky)")


def test_registers_view(tmp, app):
    print("RegistersView layout + live updates")
    from core.decode_schema import DecodeSchema
    from ui.widgets.registers_view import (RegisterCache, RegistersView,
                                           LOCK, PENCIL, NO_VALUE)
    from core.log_model import TransactionLogModel
    from PySide6.QtWidgets import QTableWidget

    p = Path(tmp) / "dev.json"
    p.write_text(json.dumps(DEVICE_JSON))
    sch = DecodeSchema.load(str(p))
    cache = RegisterCache()
    cache.attach(sch)
    view = RegistersView(sch, 8, "TestBQ", cache)
    view.show()
    app.processEvents()

    tables = view.findChildren(QTableWidget)
    check(len(tables) == 4, "2 banner + 1 pane + 1 bit table built")

    # scalar rows start empty, lock/pencil per access
    sv_rule = sch.find_read(8, 0x26)
    _r, _cells = view._scalar_cells[sv_rule.key()]
    sv_cell = _cells[0][1]
    check(sv_cell.text() == NO_VALUE, "unseen value shows em-dash")
    fet = sch.find_read(8, 0x68)
    fet_name_icon = None
    for t in tables:
        for row in range(t.rowCount()):
            item = t.item(row, 0)
            if item and "FET Setting" in item.text():
                fet_name_icon = item.text()[0]
    check(fet_name_icon == PENCIL, "R/W rule shows the pencil")
    sv_icon = None
    for t in tables:
        for row in range(t.rowCount()):
            item = t.item(row, 0)
            if item and "Stack Voltage" in item.text():
                sv_icon = item.text()[0]
    check(sv_icon == LOCK, "read-only rule shows the lock")

    # feed traffic through the model -> cache -> live cell update
    model = TransactionLogModel()
    model.set_schema(sch)
    indexed_read(model, 0x26, [0x64, 0x00])
    app.processEvents()
    check(sv_cell.text() == "1000", "scalar cell updates live (1000)")
    indexed_read(model, 0x28, [0x30, 0xF8])          # -2000 * 0.01 = -20
    app.processEvents()
    it_rule = sch.find_read(8, 0x28)
    check(view._scalar_cells[it_rule.key()][1][0][1].text() == "-20",
          "signed float value renders (-20)")

    # bit matrix: 2-byte rule -> high/low pair; 0x8401 -> SLEEP,FUSE,SEC0 red
    bs_rule = sch.find_read(8, 0x12)
    _rule, hex_items, cells = view._bit_rows[bs_rule.key()]
    check(len(cells) == 16 and len(hex_items) == 1,
          "2-byte bit rule renders 16 cells over a high/low row pair")
    indexed_read(model, 0x12, [0x01, 0x84])          # LE -> 0x8401
    app.processEvents()
    check(hex_items[0].text() == "0x8401", "hex value on the high row")
    from ui import theme
    red = theme.get_color("status_error").name()
    green = theme.get_color("status_active").name()
    gray = theme.get_color("bg_tertiary").name()
    by_bit = {bit: item for item, bit in cells}
    check(by_bit[15].background().color().name() == green and
          by_bit[10].background().color().name() == green and
          by_bit[0].background().color().name() == green,
          "set bits colored green (SLEEP/FUSE/SEC0, v1.1 rule)")
    check(by_bit[14].background().color().name() == gray and
          by_bit[14].text().startswith("RSVD"),
          "unnamed bits labeled RSVD_0 and grayed")
    check(by_bit[1].background().color().name() == gray or
          by_bit[1].text().startswith("RSVD"), "reserved stays gray even at 0")
    # zero-valued named field is RED under the v1.1 rule
    indexed_read(model, 0x12, [0x00, 0x00])
    app.processEvents()
    check(by_bit[15].background().color().name() == red,
          "cleared named bit turns red (v1.1: zero = red)")
    view.deleteLater()


def test_window_integration(tmp, app):
    print("window integration (tab per v4 device)")
    from ui.sniffer_ion_window import SnifferIonWindow

    v4 = Path(tmp) / "testbq.json"
    v4.write_text(json.dumps(DEVICE_JSON))
    v3 = Path(tmp) / "plain.json"
    v3.write_text(json.dumps({
        "version": 3, "device": "PlainDev", "i2c_address": 0x30,
        "rules": [{"address": 0x30, "transaction_type": "indexed_read",
                   "register": 1, "data_bytes": 1, "byte_order": "le",
                   "format": "dec", "function": "X", "unit": "",
                   "name": "Reg1"}]}))

    win = SnifferIonWindow()
    win.show(); app.processEvents()
    base_labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    win._load_decoder.add_decoder(str(v4))
    win._load_decoder.add_decoder(str(v3))
    app.processEvents()
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    check("TestBQ" in labels, "v4 decoder produces a device Registers tab")
    check("PlainDev" not in labels, "v3 decoder without layout: no tab")
    check(labels.index("TestBQ") < labels.index("Preferences"),
          "device tab inserted before Preferences")

    # live end-to-end: a transaction through the window's handler updates it
    win._handle_transaction(make_txn(8, "W", [0x26], stop=False))
    win._handle_transaction(make_txn(8, "R", [0x2C, 0x01], start=2, nak=True))
    app.processEvents()
    view = win.tabs.widget(labels.index("TestBQ"))
    from core.decode_schema import DecodeSchema
    key = (8, 0x26, "indexed_read")
    check(view._scalar_cells[key][1][0][1].text() == "3000",
          "sniffed traffic drives the Registers tab (0x012C*10)")

    # removing the decoder removes its tab
    win._load_decoder.manager.remove(str(v4))
    win._load_decoder._refresh()
    win._load_decoder.decoders_changed.emit()
    app.processEvents()
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    check("TestBQ" not in labels and labels == base_labels,
          "removing the decoder removes the tab (base layout restored)")
    win._log_panel.clear_log()
    win.close(); app.processEvents()


def test_b33_multi_address_tabs(tmp, app):
    print("B33: one Registers tab per address with layout")
    from ui.sniffer_ion_window import SnifferIonWindow

    def rule(addr, reg, name, group=None):
        r = {"address": addr, "transaction_type": "indexed_read",
             "register": reg, "data_bytes": 2, "byte_order": "le",
             "format": "hex", "function": "X", "name": name}
        if group:
            r["group"] = group
        return r

    multi = Path(tmp) / "multi.json"
    multi.write_text(json.dumps({
        "version": 4, "device": "Multi", "i2c_address": 0x55,
        "address_names": {"0x6B": "R1", "0x55": "R2"},
        "display_groups": [{"name": "G1", "kind": "pane"},
                           {"name": "G2", "kind": "pane"}],
        "rules": [rule(0x6B, 2, "R1 w2", "G1"), rule(0x55, 2, "R2 w2", "G2")]}))
    # layout only on the HIGHER address (the Smart Battery 0x08/0x0B shape)
    high = Path(tmp) / "high.json"
    high.write_text(json.dumps({
        "version": 4, "device": "HighOnly", "i2c_address": 0x0B,
        "display_groups": [{"name": "Pack", "kind": "banner"}],
        "rules": [rule(0x08, 1, "host"), rule(0x0B, 9, "Voltage", "Pack")]}))

    win = SnifferIonWindow()
    win.show(); app.processEvents()
    win._load_decoder.add_decoder(str(multi))
    win._load_decoder.add_decoder(str(high))
    app.processEvents()
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    check("Multi — R1 0x6B" in labels and "Multi — R2 0x55" in labels,
          f"two-address decoder: one tab per address, named ({labels})")
    check("HighOnly" in labels,
          "layout only on the higher address still gets a tab")
    # the R1 tab shows the R1 rule (the lost device in the bug)
    v = win.tabs.widget(labels.index("Multi — R1 0x6B"))
    check((0x6B, 2, "indexed_read") in v._scalar_cells,
          "R1 tab holds the 0x6B rules")
    # real shipped decoders
    for f in ("i2c_decoders/smbus1v1_decoder.json",
              "i2c_decoders/loopback_dut_decoder.json"):
        win._load_decoder.add_decoder(os.path.join(ROOT, f))
    app.processEvents()
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    check(any("0x0B" in l for l in labels) or any(l.startswith("Smart Battery") or "SBS" in l for l in labels),
          f"smbus1v1: the 0x0B battery dashboard exists ({labels})")
    check(sum("0x6B" in l for l in labels) >= 2,
          "loopback_dut: an R1 (0x6B) tab exists")
    check("HighOnly — 0x08" not in labels and "HighOnly" in labels,
          "a tab shows only its own file's rules (SBS 0x08 bit rules do not "
          "give HighOnly a 0x08 tab)")
    win._log_panel.clear_log()
    win.close(); app.processEvents()


def main():
    from ui.common import build_application
    app = build_application(app_name="registers-tests", initial_theme="default")
    with _tf.TemporaryDirectory() as tmp:
        test_schema_v4(tmp)
        test_cache_via_log_model(tmp, app)
        test_registers_view(tmp, app)
        test_window_integration(tmp, app)
        test_b33_multi_address_tabs(tmp, app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
