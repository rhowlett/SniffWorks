"""
tests/test_decoder_manager.py — multi-decoder support ("decoders manager"):
several decoder JSONs loaded at once decode transactions from multiple
client devices in one log.

Covers:
  * DecoderSetManager: add/reload/remove, metadata, merge order + conflict
    counting, summary
  * merged schema decodes traffic from two different device addresses
    through the real log model
  * LoadDecoderSection UI: add/remove buttons, list, signals, persistence
    of the loaded set across a fresh section

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_decoder_manager.py
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


def write_decoder(dirpath, name, device, address, register, rule_name,
                  unit="mV"):
    path = Path(dirpath) / name
    path.write_text(json.dumps({
        "version": 3, "device": device, "i2c_address": address,
        "rules": [{
            "address": address, "transaction_type": "indexed_read",
            "register": register, "data_bytes": 2, "byte_order": "le",
            "signed": False, "format": "dec", "function": "X",
            "unit": unit, "name": rule_name,
        }],
    }))
    return str(path)


def make_txn(addr, direction, data, start=1, stop=True):
    from core.i2c_controller import I2CTransaction, I2CDirection
    return I2CTransaction(
        timestamp=time.time(), address=addr,
        direction=I2CDirection.READ if direction == "R" else I2CDirection.WRITE,
        data=bytes(data), start=start, stop=stop)


def test_manager(tmp):
    print("DecoderSetManager")
    from core.decoder_manager import DecoderSetManager
    a = write_decoder(tmp, "dev_a.json", "DevA", 0x08, 0x14, "Cell Voltage")
    b = write_decoder(tmp, "dev_b.json", "DevB", 0x6B, 0x20, "Charge Current",
                      unit="mA")

    mgr = DecoderSetManager()
    ok, msg = mgr.add(a)
    check(ok and "DevA" in msg, "add reports device + rules")
    mgr.add(b)
    check(len(mgr) == 2, "two decoders loaded")
    e0, e1 = mgr.entries()
    check(e0.device == "DevA" and e0.addresses == {0x08}, "metadata: DevA @0x08")
    check("0x6B" in e1.addresses_str, "metadata: DevB address rendered")

    merged = mgr.merged_schema()
    check(len(merged) == 2 and mgr.last_conflicts == 0,
          "merged schema holds both rules, no conflicts")
    check(merged.find_read(0x08, 0x14) is not None
          and merged.find_read(0x6B, 0x20) is not None,
          "rules from both devices route by address")

    # conflict: second file redefines DevA's key -> later file wins, counted
    a2 = write_decoder(tmp, "dev_a2.json", "DevA-alt", 0x08, 0x14, "Override")
    mgr.add(a2)
    merged = mgr.merged_schema()
    check(mgr.last_conflicts == 1, "key collision counted")
    check(merged.find_read(0x08, 0x14).name == "Override",
          "later file wins the collision")
    check("overridden" in mgr.summary(), "summary surfaces the override")

    # reload in place (same path) and remove
    mgr.add(a)                                   # reload, position kept
    check(len(mgr) == 3, "re-adding same path reloads, not duplicates")
    mgr.remove(a2)
    check(len(mgr) == 2 and mgr.merged_schema().find_read(0x08, 0x14).name
          == "Cell Voltage", "remove restores the shadowed rule")

    ok, msg = mgr.add(str(Path(tmp) / "missing.json"))
    check(not ok, "missing file rejected with message")

    # reorder: moving the shadowed file below the winner flips the collision
    mgr.add(a2)                                  # DevA-alt: Override (last -> wins)
    check(mgr.merged_schema().find_read(0x08, 0x14).name == "Override",
          "pre-move: later file wins")
    check(mgr.move(a2, -1), "move up succeeds")
    check(mgr.merged_schema().find_read(0x08, 0x14).name == "Override",
          "one step up (still below its collision partner): no flip yet")
    mgr.move(a2, -1)                             # now above dev_a
    check(mgr.merged_schema().find_read(0x08, 0x14).name == "Cell Voltage",
          "moving above the partner flips the collision winner")
    check(not mgr.move(mgr.paths()[0], -1), "move above top rejected")
    check(not mgr.move(mgr.paths()[-1], +1), "move below bottom rejected")
    mgr.remove(a2)


def test_merged_decode_in_log(tmp, app):
    print("merged decode through the log model")
    from ui.log_panel import LogPanel
    from core.decoder_manager import DecoderSetManager

    mgr = DecoderSetManager()
    mgr.add(write_decoder(tmp, "m_a.json", "DevA", 0x08, 0x14, "Cell Voltage"))
    mgr.add(write_decoder(tmp, "m_b.json", "DevB", 0x6B, 0x20,
                          "Charge Current", unit="mA"))

    panel = LogPanel(show_toolbar=False)
    panel.apply_schema(mgr.merged_schema())

    # indexed read from DevA: pointer write then restart read (0x1234 = 4660)
    panel.model.add_transaction(make_txn(0x08, "W", [0x14], stop=False))
    panel.model.add_transaction(make_txn(0x08, "R", [0x34, 0x12], start=2))
    # indexed read from DevB (0x0064 = 100)
    panel.model.add_transaction(make_txn(0x6B, "W", [0x20], stop=False))
    panel.model.add_transaction(make_txn(0x6B, "R", [0x64, 0x00], start=2))

    decodes = [e.decode(None) for e in panel.model._entries] \
        if hasattr(panel.model, "_entries") else []
    text = " | ".join(d for d in decodes if d)
    check("Cell Voltage" in text and "4660" in text,
          f"DevA decode present ({text!r})")
    check("Charge Current" in text and "100" in text,
          "DevB decode present in the same log")
    panel.deleteLater()


def test_section_ui(tmp, app):
    print("LoadDecoderSection UI")
    from ui.widgets.sidebar_sections import LoadDecoderSection
    from ui.common import settings_store as ss

    a = write_decoder(tmp, "ui_a.json", "DevA", 0x08, 0x14, "V")
    b = write_decoder(tmp, "ui_b.json", "DevB", 0x6B, 0x20, "I")

    sec = LoadDecoderSection()
    changed, selected = [], []
    sec.decoders_changed.connect(lambda: changed.append(1))
    sec.decoder_selected.connect(selected.append)

    check(not sec.is_valid(), "starts empty / invalid")
    check(sec.add_decoder(a), "add_decoder ok")
    sec.add_decoder(b)
    check(len(changed) == 2 and selected == [a, b],
          "both signals fired per add")
    check(sec._list.count() == 2, "list shows two entries")
    check("DevA" in sec._list.item(0).text() and
          "0x08" in sec._list.item(0).text(), "list label has device + addr")
    check(sec.is_valid() and sec.selected_path() == b,
          "selected_path defaults to last added")

    sec._list.setCurrentRow(0)
    check(sec.selected_path() == a, "selection drives selected_path")
    check(len(sec.merged_schema()) == 2, "merged_schema from section")

    # reorder buttons: select first row, move down, selection follows
    sec._list.setCurrentRow(0)
    check(sec._up_btn.isEnabled() is False and sec._down_btn.isEnabled(),
          "top row: only Down enabled")
    sec._on_move(+1)
    check(sec.manager.paths() == [b, a], "Down button reorders load order")
    check(sec.selected_path() == a and sec._list.currentRow() == 1,
          "moved entry stays selected at new position")
    check(sec._down_btn.isEnabled() is False and sec._up_btn.isEnabled(),
          "bottom row: only Up enabled")
    sec._on_move(-1)
    check(sec.manager.paths() == [a, b], "Up button restores order")
    check(len(changed) == 4, "each move emits decoders_changed")
    sec._list.setCurrentRow(0)

    # remove selected
    sec._on_remove()
    check(sec._list.count() == 1 and sec.manager.paths() == [b],
          "Remove drops the selected decoder")
    check(len(changed) == 5, "remove emits decoders_changed")
    check(not sec.add_decoder(str(Path(tmp) / "nope.json")),
          "bad file rejected, status shows error")

    # persistence: a fresh section restores the surviving set
    sec2 = LoadDecoderSection()
    check(sec2.manager.paths() == [b],
          "fresh section restores persisted decoder set")
    # a persisted path that no longer exists is silently skipped
    ss.store().set(ss.KEY_DECODERS, "\n".join([b, str(Path(tmp) / "gone.json")]))
    sec3 = LoadDecoderSection()
    check(sec3.manager.paths() == [b], "missing persisted file skipped")

    for s in (sec, sec2, sec3):
        s.deleteLater()
    ss.store().set(ss.KEY_DECODERS, "")


def main():
    from ui.common import build_application
    app = build_application(app_name="decoder-mgr-tests",
                            initial_theme="default")
    with _tf.TemporaryDirectory() as tmp:
        test_manager(tmp)
        test_merged_decode_in_log(tmp, app)
        test_section_ui(tmp, app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
