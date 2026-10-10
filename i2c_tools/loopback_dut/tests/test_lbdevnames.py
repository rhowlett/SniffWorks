#!/usr/bin/env python3
# [v0.1]
"""
loopback_dut/tests/test_lbdevnames.py - tier T1 (no hardware): the isolated
device-name reader (host/lbdevnames.py) resolves --port names exactly as the
sniffer tools' core/device_names.py does, from the same per-user file.

The store file is written here BY HAND in the documented format
(core/device_names.py docstring), not with core/, so the isolation rule holds.
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "host"))

import lbdevnames as ld  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def main():
    print("lbdevnames")
    path = os.path.join(tempfile.mkdtemp(), "device_names.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "devices": {
            "sn:003200273234511437333934": {"name": "H533 DUT"},
            "sn:210321AC1ED9": {"name": "Bench AD2"}}, "last_used": {}}, f)
    os.environ["ION_TOOL_DEVICE_NAMES"] = path
    ports = [NS(device="/dev/cu.usbmodem1403", vid=0x0483, serial_number="003200273234511437333934"),
             NS(device="/dev/cu.usbmodem1203", vid=0x0483, serial_number="066BFF544884654867102556"),
             NS(device="/dev/cu.Bluetooth-Incoming-Port", vid=None, serial_number=None)]
    check(ld.load_names() == {"sn:003200273234511437333934": "H533 DUT",
                              "sn:210321AC1ED9": "Bench AD2"}, "reads the per-user file (env override)")
    check(ld.resolve_port("H533 DUT", ports) == "/dev/cu.usbmodem1403", "name -> port")
    check(ld.resolve_port("h533 dut", ports) == "/dev/cu.usbmodem1403", "name, any case")
    check(ld.resolve_port("003200273234511437333934", ports) == "/dev/cu.usbmodem1403", "serial -> port")
    check(ld.resolve_port("/dev/cu.usbmodem1203", ports) == "/dev/cu.usbmodem1203", "path passes through")
    check(ld._norm("SN:210321ac1ed9") == "210321AC1ED9", "serial normalized like core ('SN:' dropped)")
    try:
        ld.resolve_port("Bench AD2", ports)      # named, but not plugged in
        check(False, "a named device that is not connected raises")
    except LookupError as e:
        check("H533 DUT [/dev/cu.usbmodem1403]" in str(e) and "Name devices" in str(e),
              "not connected: error lists connected devices and how to name one")
    os.environ["ION_TOOL_DEVICE_NAMES"] = os.path.join(tempfile.mkdtemp(), "missing.json")
    check(ld.load_names() == {}, "missing file -> no names, no crash")
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
