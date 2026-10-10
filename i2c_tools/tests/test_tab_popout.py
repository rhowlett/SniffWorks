"""
tests/test_tab_popout.py — framework-standard tab pop-out.

Covers:
  * pop out via controller: tab leaves the bar, widget becomes a visible
    top-level window with a composed title
  * closing the float re-docks at the original index (not destroyed)
  * exclusions: Device and Exit tabs refuse to pop (AppWindow title rule
    and explicit property in the decoder editor)
  * a floated RegistersView keeps updating live from sniffed traffic
  * decoders_changed while a device tab is floated: the rebuilt tab is
    re-floated (fresh view, still live), removal docks nothing back
  * host window close sweeps floats back (no orphan top-levels)
  * decoder editor: Display Groups pops, Exit refuses
  * theme editor inherits pop-out via AppWindow (Config pops, Exit refuses)

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tab_popout.py
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
    "version": 4, "device": "PopBQ", "i2c_address": 0x08,
    "display_groups": [{"name": "Pack", "kind": "banner"}],
    "rules": [
        {"address": 8, "transaction_type": "indexed_read", "register": 0x26,
         "data_bytes": 2, "byte_order": "le", "format": "dec",
         "function": "X*10", "unit": "mV", "name": "Stack Voltage",
         "group": "Pack", "group_order": 1, "access": "R"},
    ],
}


def make_txn(addr, direction, data, start=1, stop=True, nak=False):
    from core.i2c_controller import I2CTransaction, I2CDirection
    return I2CTransaction(
        timestamp=time.time(), address=addr,
        direction=I2CDirection.READ if direction == "R" else I2CDirection.WRITE,
        data=bytes(data), start=start, stop=stop, nak=nak)


def test_basic_popout(app):
    print("basic pop out / re-dock (sniffer window)")
    from ui.sniffer_ion_window import SnifferIonWindow

    win = SnifferIonWindow()
    win.show(); app.processEvents()
    n0 = win.tabs.count()
    sniffer_ix = [win.tabs.tabText(i)
                  for i in range(n0)].index("Sniffer")
    widget = win.tabs.widget(sniffer_ix)

    check(win.popout.pop_out(sniffer_ix), "Sniffer tab pops out")
    app.processEvents()
    check(win.tabs.count() == n0 - 1, "tab removed from the bar")
    check(widget.isWindow() and widget.isVisible(),
          "widget is a visible top-level window")
    check(widget.windowTitle() == f"{win.windowTitle()} — Sniffer",
          "float title composed from app + tab")
    check(win.popout.floating_titles() == ["Sniffer"], "tracked as floating")

    widget.close()                     # user closes the float
    app.processEvents()
    check(win.tabs.count() == n0 and win.tabs.tabText(sniffer_ix) == "Sniffer",
          "close re-docks at the original index")
    check(not widget.isWindow(), "widget no longer top-level")
    check(win.popout.floating_titles() == [], "no floats tracked")

    # exclusions by title rule
    dev_ix = [win.tabs.tabText(i) for i in range(win.tabs.count())].index("Device")
    exit_ix = [win.tabs.tabText(i) for i in range(win.tabs.count())].index("Exit")
    check(not win.popout.pop_out(dev_ix), "Device tab refuses to pop")
    check(not win.popout.pop_out(exit_ix), "Exit tab refuses to pop")
    check(win.popout.pop_out_by_title("Preferences"),
          "Preferences pops (only Device/Exit excluded)")
    win.popout.dock_all()
    win._log_panel.clear_log()
    win.close(); app.processEvents()


def test_floating_registers_live(tmp, app):
    print("floated Registers tab stays live + survives rebuilds")
    from ui.sniffer_ion_window import SnifferIonWindow

    v4 = Path(tmp) / "popbq.json"
    v4.write_text(json.dumps(DEVICE_JSON))
    win = SnifferIonWindow()
    win.show(); app.processEvents()
    win._load_decoder.add_decoder(str(v4))
    app.processEvents()

    check(win.popout.pop_out_by_title("PopBQ"), "device Registers tab pops")
    app.processEvents()
    view = win.popout.floating_widgets()[0]

    # live update while floated
    win._handle_transaction(make_txn(8, "W", [0x26], stop=False))
    win._handle_transaction(make_txn(8, "R", [0x64, 0x00], start=2, nak=True))
    app.processEvents()
    key = (8, 0x26, "indexed_read")
    check(view._scalar_cells[key][1][0][1].text() == "1000",
          "floated view updates live from sniffed traffic")

    # rebuild while floated (re-add same decoder -> decoders_changed)
    win._load_decoder.add_decoder(str(v4))
    app.processEvents()
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    check("PopBQ" not in labels, "rebuilt device tab is floating, not docked")
    check(win.popout.floating_titles(prop="registersTab") == ["PopBQ"],
          "fresh view re-floated after rebuild")
    new_view = win.popout.floating_widgets()[0]
    check(new_view is not view, "rebuild produced a fresh view")
    win._handle_transaction(make_txn(8, "W", [0x26], stop=False))
    win._handle_transaction(make_txn(8, "R", [0xC8, 0x00], start=2, nak=True))
    app.processEvents()
    check(new_view._scalar_cells[key][1][0][1].text() == "2000",
          "re-floated view is live (2000)")

    # decoder removal: floated tab docks + disappears with its decoder
    win._load_decoder.manager.remove(str(v4))
    win._load_decoder._refresh()
    win._load_decoder.decoders_changed.emit()
    app.processEvents()
    check(win.popout.floating_titles() == [] and
          "PopBQ" not in [win.tabs.tabText(i) for i in range(win.tabs.count())],
          "removing the decoder retires the floated tab entirely")

    # host close sweeps floats
    win.popout.pop_out_by_title("Sniffer")
    app.processEvents()
    win._log_panel.clear_log()
    win.close(); app.processEvents()
    check(win.popout.floating_titles() == [],
          "window close re-docks all floats (no orphans)")


def test_editor_windows(app):
    print("decoder editor + theme editor")
    from ui.decoder_editor_window import DecoderEditorWindow
    win = DecoderEditorWindow()
    win.show(); app.processEvents()
    check(win.popout.pop_out_by_title("Display Groups"),
          "editor: Display Groups pops out")
    win.popout.dock_all()
    check(not win.popout.pop_out_by_title("Exit"),
          "editor: Exit refuses (explicit property)")
    win._dirty = False
    win.close(); app.processEvents()

    from theme_editor import ThemeEditorWindow
    tw = ThemeEditorWindow()
    tw.show(); app.processEvents()
    check(tw.popout.pop_out_by_title("Config"),
          "theme editor inherits pop-out via AppWindow")
    tw.popout.dock_all()
    check(not tw.popout.pop_out_by_title("Exit"),
          "theme editor: Exit refuses by title rule")
    if hasattr(tw, "close_guard"):
        pass
    tw.close(); app.processEvents()


def main():
    from ui.common import build_application
    app = build_application(app_name="popout-tests", initial_theme="default")
    with _tf.TemporaryDirectory() as tmp:
        test_basic_popout(app)
        test_floating_registers_live(tmp, app)
        test_editor_windows(app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
