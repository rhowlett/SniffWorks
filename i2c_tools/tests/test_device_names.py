#!/usr/bin/env python3
# [v0.1]
"""
tests/test_device_names.py — USB device discovery and naming (core/device_names.py)
and its GUI/CLI integration, no hardware needed (fake port lists).

Covers:
  * identity: serial normalization ("SN:" prefix from the Digilent library),
    no-serial fallback key, non-USB ports skipped
  * the per-user store: round trip through the file, unique names, forget,
    last-used per app, env-var path override
  * discovery: snapshot -> new device reported; unplug + replug of an
    already-connected board is detected; nothing new -> nothing reported
  * resolve_port: by name, by serial, by path; helpful error otherwise
  * GUI: the shared Device group has a "Name devices…" button; the ion port
    list and the AD2 device list show names and pre-select the last-used
    device by serial; the naming dialog finds a newly plugged device and saves
    its name

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_device_names.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
_TMP = _tf.mkdtemp()
os.environ["ION_TOOL_DEVICE_NAMES"] = os.path.join(_TMP, "device_names.json")
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import json  # noqa: E402
import sys  # noqa: E402
from types import SimpleNamespace as NS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import device_names as dn  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def port(device, vid, pid, sn, desc, loc="0-1.2", mfr=""):
    return NS(device=device, vid=vid, pid=pid, serial_number=sn, location=loc,
              description=desc, manufacturer=mfr)


C031 = port("/dev/cu.usbmodem1203", 0x0483, 0x374B, "066BFF544884654867102556", "STM32 STLink")
H533 = port("/dev/cu.usbmodem1403", 0x0483, 0x374E, "003200273234511437333934", "STLINK-V3", "0-1.4")
AD2 = port("/dev/cu.usbserial-210321AC1ED9", 0x0403, 0x6014, "210321AC1ED9", "Digilent USB Device", "0-1.3")
BT = port("/dev/cu.Bluetooth-Incoming-Port", None, None, None, "n/a")
NOSN = port("/dev/cu.usbserial-X", 0x1A86, 0x7523, None, "CH340", "0-1.5")


def scan(*ports):
    return dn.scan_usb(lambda: list(ports))


def test_identity():
    print("identity")
    check(dn.normalize_serial("SN:210321AC1ED9") == "210321AC1ED9"
          and dn.normalize_serial(" 210321ac1ed9 ") == "210321AC1ED9",
          "Digilent 'SN:' prefix and case/whitespace normalized")
    devs = scan(C031, BT, AD2, NOSN)
    check([d.port for d in devs] == ["/dev/cu.usbmodem1203", "/dev/cu.usbserial-210321AC1ED9",
                                     "/dev/cu.usbserial-X"], "non-USB (Bluetooth) port skipped")
    ad2 = [d for d in devs if d.vid == 0x0403][0]
    check(ad2.key == dn.device_key("SN:210321AC1ED9"),
          "AD2 seen by pyserial and by DWF ('SN:…') has ONE key")
    nosn = [d for d in devs if d.vid == 0x1A86][0]
    check(nosn.key == "loc:1A86:7523:0-1.5" and not nosn.has_serial,
          "no serial number -> vid:pid:location key")


def test_store():
    print("store")
    path = os.path.join(_TMP, "store_test.json")
    s = dn.DeviceNames(path)
    c031, h533 = scan(C031)[0], scan(H533)[0]
    s.set_name(c031, "C031 sniffer")
    s.set_name(h533, "H533 DUT")
    s.set_last_used("sniffer_ion", c031.key)
    s.save()
    t = dn.DeviceNames(path)
    check(t.name_for(c031.key) == "C031 sniffer" and t.name_for("066bff544884654867102556") == "C031 sniffer",
          "names survive a save/reload; lookup by key or raw serial")
    check(t.last_used("sniffer_ion") == c031.key, "last-used per app survives")
    try:
        t.set_name(h533, "c031 SNIFFER")
        check(False, "duplicate name (case-insensitive) rejected")
    except dn.NameError_:
        check(True, "duplicate name (case-insensitive) rejected")
    try:
        t.set_name(h533, "   ")
        check(False, "empty name rejected")
    except dn.NameError_:
        check(True, "empty name rejected")
    t.set_name(c031, "C031 probe")        # renaming the same device is fine
    check(t.key_for_name("c031 probe") == c031.key, "rename + case-insensitive lookup")
    t.forget(c031.key)
    check(t.name_for(c031.key) == "" and t.last_used("sniffer_ion") is None,
          "forget removes the name and its last-used entries")
    check(dn.DeviceNames().path == dn.Path(os.environ["ION_TOOL_DEVICE_NAMES"]),
          "ION_TOOL_DEVICE_NAMES overrides the per-user path")
    bad = os.path.join(_TMP, "corrupt.json")
    open(bad, "w").write("{not json")
    check(dn.DeviceNames(bad).entries() == {}, "a corrupt file loads as empty, no crash")


def test_discovery():
    print("discovery")
    tr = dn.DiscoveryTracker(scan(C031, AD2))
    check(tr.poll(scan(C031, AD2)) == [], "nothing plugged in -> nothing new")
    new = tr.poll(scan(C031, AD2, H533))
    check([d.port for d in new] == ["/dev/cu.usbmodem1403"], "new board after the snapshot is reported")
    tr = dn.DiscoveryTracker(scan(C031, AD2))
    tr.poll(scan(AD2))                                   # C031 unplugged
    new = tr.poll(scan(C031, AD2))                       # ... and plugged back
    check([d.port for d in new] == ["/dev/cu.usbmodem1203"],
          "unplug + replug of an already-connected board is detected")


def test_resolve():
    print("resolve_port")
    s = dn.DeviceNames(os.path.join(_TMP, "resolve.json"))
    s.set_name(scan(C031)[0], "C031 sniffer")
    devs = scan(C031, H533, AD2)
    check(dn.resolve_port("C031 sniffer", devs, s) == "/dev/cu.usbmodem1203", "by name")
    check(dn.resolve_port("c031 SNIFFER", devs, s) == "/dev/cu.usbmodem1203", "by name, any case")
    check(dn.resolve_port("003200273234511437333934", devs, s) == "/dev/cu.usbmodem1403", "by serial")
    check(dn.resolve_port("/dev/cu.whatever", devs, s) == "/dev/cu.whatever", "a path passes through")
    try:
        dn.resolve_port("H533 DUT", devs, s)
        check(False, "unknown name raises")
    except LookupError as e:
        check("C031 sniffer [/dev/cu.usbmodem1203]" in str(e) and "device_names.py discover" in str(e),
              "unknown name: error lists connected devices and how to name them")


def test_gui(app):
    print("GUI integration")
    from PySide6.QtWidgets import QPushButton
    store = dn.DeviceNames()
    c031 = scan(C031)[0]
    store.set_name(c031, "C031 sniffer")
    store.set_last_used("sniffer_ion", c031.key)
    store.save()

    from ui.widgets.serial_device_panel import SerialDevicePanel
    from ui.widgets.connection_section import ConnectionSection
    panel = SerialDevicePanel()
    conn = panel.findChildren(ConnectionSection)[0]
    btns = [b.text() for b in conn.findChildren(QPushButton)]
    check("Name devices…" in btns, f"Device group has a 'Name devices…' button ({btns})")
    ports = [{"device": "/dev/cu.usbmodem1403", "description": "STLINK-V3", "is_stlink": True,
              "serial": "003200273234511437333934"},
             {"device": "/dev/cu.usbmodem1203", "description": "STM32 STLink", "is_stlink": True,
              "serial": "066BFF544884654867102556"}]
    panel.populate_ports(ports, preferred_key=store.last_used("sniffer_ion"))
    check(panel.selected_port() == "/dev/cu.usbmodem1203",
          "ion: last-used device pre-selected by serial (port name irrelevant)")
    check(conn._combo.currentText().startswith("C031 sniffer — /dev/cu.usbmodem1203"),
          f"ion: selector shows the name first ({conn._combo.currentText()!r})")

    from ui.device_panel import DevicePanel
    ad2 = scan(AD2)[0]
    store.set_name(ad2, "Bench AD2")
    store.save()
    dp = DevicePanel()
    dp.populate_devices([NS(index=0, name="Analog Discovery 2", serial="SN:210321AC1ED9", is_open=False)])
    txt = dp._conn._combo.currentText()
    check(txt.startswith("Bench AD2 — ") and "S/N:210321AC1ED9" in txt,
          f"AD2: device list shows the name ({txt!r})")

    # the naming dialog: discover a newly plugged board and name it
    from ui.dialogs.device_names_dialog import DeviceNamesDialog
    plugged = [C031, AD2]
    dlg = DeviceNamesDialog(scanner=lambda: scan(*plugged), store=dn.DeviceNames())
    dlg.start_discovery()
    plugged.append(H533)
    dlg.poll_once()
    check([d.port for d in dlg.found_devices()] == ["/dev/cu.usbmodem1403"],
          "dialog: the newly plugged H533 is found")
    ok = dlg.save_found_name("H533 DUT")
    again = dn.DeviceNames()
    check(ok and again.name_for("003200273234511437333934") == "H533 DUT",
          "dialog: the name is saved to the per-user file")
    # naming an already-connected, unnamed device directly in the table
    rows = dlg.table_rows()
    check(any(r["port"] == "/dev/cu.usbmodem1403" and r["name"] == "H533 DUT" for r in rows)
          and any(r["port"] == AD2.device and r["name"] == "Bench AD2" for r in rows),
          "dialog table lists connected devices with their names")
    ok, msg = dlg.set_row_name(AD2.device, "C031 sniffer")
    check(not ok and "already" in msg, "dialog: a duplicate name is refused with a message")
    dlg.close()


def main():
    test_identity()
    test_store()
    test_discovery()
    test_resolve()
    from ui.common import build_application
    app = build_application(app_name="device-names-tests", initial_theme="default")
    test_gui(app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
