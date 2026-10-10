"""
tests/test_table_ui_updates.py — the three table/filter updates:
  1. Column-scoped search (All columns vs one column, incl. Decode) with the
     frame-aware "everything between the bounding NAKs" behavior preserved
  2. Multiline bit-field decode by default + wrapped rows sized to content
  3. Int / ASCII columns hidden by default, revealed by Table Data checkboxes

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_table_ui_updates.py
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


def make_txn(addr, direction, data, nak=False, start=1, stop=True):
    from core.i2c_controller import I2CTransaction, I2CDirection
    return I2CTransaction(
        timestamp=time.time(), address=addr,
        direction=I2CDirection.READ if direction == "R" else I2CDirection.WRITE,
        data=bytes(data), nak=nak, start=start, stop=stop)


def test_scoped_search(app):
    print("column-scoped search")
    from core.log_model import TransactionLogModel, COL_IDX

    m = TransactionLogModel()
    # frame 1: pointer write 0x3E + response read ending in NAK
    m.add_transaction(make_txn(0x08, "W", [0x3E], stop=False))
    m.add_transaction(make_txn(0x08, "R", [0x41, 0x42], nak=True, start=2))
    # frame 2: unrelated traffic, also contains byte 0x3E in DATA
    m.add_transaction(make_txn(0x6B, "W", [0x3E, 0x99], nak=True))

    # classic all-columns search finds 3E in both frames
    m.filter_search = "3e"
    m.filter_search_col = None
    m.reapply_filter()
    check(m.visible_count == 3, "All-columns search: both frames shown")

    # scope to Addr: "6b" matches only frame 2
    m.filter_search = "6b"
    m.filter_search_col = COL_IDX["Addr"]
    m.reapply_filter()
    check(m.visible_count == 1, "Addr-scoped search narrows to one frame")

    # frame-aware context preserved under a scoped search: matching the READ
    # row's ASCII ('AB') reveals its paired WRITE too (start/stop context)
    m.filter_search = "ab"
    m.filter_search_col = COL_IDX["ASCII"]
    m.reapply_filter()
    check(m.visible_count == 2,
          "scoped hit still reveals the whole NAK-bounded exchange")

    # Decode column scope: load a schema, search the decoded name
    with _tf.TemporaryDirectory() as d:
        dec = Path(d) / "d.json"
        dec.write_text(json.dumps({
            "version": 3, "device": "DevA", "i2c_address": 0x08,
            "rules": [{"address": 0x08, "transaction_type": "indexed_read",
                       "register": 0x3E, "data_bytes": 2, "byte_order": "le",
                       "signed": False, "format": "dec", "function": "X",
                       "unit": "", "name": "MagicValue"}]}))
        from core.decode_schema import DecodeSchema
        m.set_schema(DecodeSchema.load(str(dec)))
        m.filter_search = "magicvalue"
        m.filter_search_col = COL_IDX["Decode"]
        m.reapply_filter()
        check(m.visible_count == 2,
              "Decode-scoped search matches decoded text (+frame context)")

    m.filter_search = ""
    m.filter_search_col = None
    m.reapply_filter()
    check(m.visible_count == 3, "clearing search restores all rows")


def test_multiline_and_wrap(app):
    print("multiline bit fields + wrapped rows")
    from ui.widgets.sidebar_sections import LoadDecoderSection
    from ui.log_panel import LogPanel
    from PySide6.QtCore import Qt

    with _tf.TemporaryDirectory() as d:
        dec = Path(d) / "bits.json"
        dec.write_text(json.dumps({
            "version": 3, "device": "DevB", "i2c_address": 0x08,
            "rules": [{"address": 0x08, "transaction_type": "indexed_read",
                       "register": 0x02, "data_bytes": 1, "byte_order": "le",
                       "signed": False, "format": "bits", "function": "X",
                       "unit": "", "name": "SafetyStatus",
                       "bit_fields": [
                           {"range": [0, 0], "mode": "enum",
                            "names": ["OV=0", "OV=1"]},
                           {"range": [1, 1], "mode": "enum",
                            "names": ["UV=0", "UV=1"]},
                           {"range": [2, 2], "mode": "raw",
                            "description": "SCD"},
                       ]}]}))
        sec = LoadDecoderSection(persist=False)
        sec.add_decoder(str(dec))
        schema = sec.merged_schema()          # default now multiline
        check(schema.multiline_bits is True,
              "merged_schema defaults to multiline bit fields")

        panel = LogPanel(show_toolbar=False)
        panel.apply_schema(schema)
        panel.model.add_transaction(make_txn(0x08, "W", [0x02], stop=False))
        panel.model.add_transaction(make_txn(0x08, "R", [0x07], nak=True,
                                             start=2))
        decode_text = panel.model._entries[1].decode(schema)
        check("\n" in decode_text and "OV" in decode_text and "UV" in decode_text,
              "bit fields render one per line")

        # and with the real shipped decoder: a SafetyAlertA-style register
        real = Path(ROOT) / "i2c_decoders" / "bq76905_decoder.json"
        sec2 = LoadDecoderSection(persist=False)
        sec2.add_decoder(str(real))
        rschema = sec2.merged_schema()
        bits_rules = [r for r in rschema.rules()
                      if r.fmt == "bits" and r.bit_fields]
        check(bool(bits_rules), "shipped decoder has bit-field rules")
        r0 = bits_rules[0]
        rendered = rschema.decode_value_text(r0, 0xFF) \
            if hasattr(rschema, "decode_value_text") else \
            rschema._format_bits_multiline(0xFF, r0.bit_fields, r0.name)
        check(rendered.count("\n") >= 2,
              "real BQ76905 bit register renders multiline")
        sec2.deleteLater()

        check(panel._table.wordWrap() is True, "table wraps instead of eliding")
        check(panel._table.textElideMode() == Qt.ElideNone,
              "elide mode off (no ...)")
        # the multiline row is taller than the single-line write row
        h_write = panel._table.rowHeight(0)
        h_read = panel._table.rowHeight(1)
        check(h_read > h_write,
              f"row height follows decode content ({h_write} -> {h_read}px)")
        panel.deleteLater()
        sec.deleteLater()


def test_int_ascii_toggles(app):
    print("Int / ASCII column toggles")
    from ui.log_panel import LogPanel
    from ui.widgets.sidebar_sections import TableDataSection
    from core.log_model import COL_IDX

    panel = LogPanel(show_toolbar=False)
    check(panel._table.isColumnHidden(COL_IDX["Int"]) and
          panel._table.isColumnHidden(COL_IDX["ASCII"]),
          "Int and ASCII columns hidden by default")

    sec = TableDataSection()
    sec.show_int_changed.connect(panel.set_int_visible)
    sec.show_ascii_changed.connect(panel.set_ascii_visible)

    sec._show_int.setChecked(True)
    check(not panel._table.isColumnHidden(COL_IDX["Int"]),
          "checkbox reveals Int column")
    sec._show_ascii.setChecked(True)
    check(not panel._table.isColumnHidden(COL_IDX["ASCII"]),
          "checkbox reveals ASCII column")
    sec._show_int.setChecked(False)
    check(panel._table.isColumnHidden(COL_IDX["Int"]),
          "unchecking hides Int again")
    panel.deleteLater()
    sec.deleteLater()


def test_filter_bar_scope_ui(app):
    print("filter bar scope combo")
    from ui.log_panel import LogPanel
    from core.log_model import COL_IDX

    panel = LogPanel(show_toolbar=False)
    combo = panel._search_col_combo
    check(combo.itemText(0) == "All columns" and combo.currentData() is None,
          "default scope: All columns")
    idx = combo.findText("Decode")
    combo.setCurrentIndex(idx)
    panel._search_edit.setText("volt")
    panel._apply_filters()
    check(panel.model.filter_search_col == COL_IDX["Decode"]
          and panel.model.filter_search == "volt",
          "Apply pushes scope + needle to the model")
    panel._reset_filters()
    check(panel.model.filter_search_col is None
          and combo.currentIndex() == 0,
          "Reset restores All columns")
    panel.deleteLater()


def main():
    from ui.common import build_application
    app = build_application(app_name="table-ui-tests", initial_theme="default")
    test_scoped_search(app)
    test_multiline_and_wrap(app)
    test_int_ascii_toggles(app)
    test_filter_bar_scope_ui(app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
