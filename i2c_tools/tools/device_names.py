#!/usr/bin/env python3
"""
tools/device_names.py  [v0.1]
List, discover and name USB instruments from the command line; the same
per-user names the GUI apps show (core/device_names.py,
~/.ion_i2c_tool/device_names.json).

  python tools/device_names.py list
  python tools/device_names.py discover            # snapshot, plug in, name it
  python tools/device_names.py name /dev/cu.usbmodem1203 "C031 sniffer"
  python tools/device_names.py name 066BFF544884654867102556 "C031 sniffer"
  python tools/device_names.py forget "C031 sniffer"

Every tool that takes --port accepts a name instead of a port path
(tools/ion_capture.py, tools/record_on_trigger.py, loopback_dut/host/loopback_run.py).
Exit status: 0 ok, 1 error / nothing found.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import device_names as dn  # noqa: E402


def _row(d, names):
    name = names.name_for(d.key) or "(unnamed)"
    return f"  {name:22s} {d.port:34s} {d.serial or '(no serial)':26s} {d.vid_pid}  {d.description}"


def cmd_list(args, names) -> int:
    devs = dn.scan_usb()
    print(f"Connected USB devices ({len(devs)}), names from {names.path}:")
    for d in devs:
        print(_row(d, names))
    connected = {d.key for d in devs}
    absent = [(k, v) for k, v in names.entries().items() if k not in connected]
    if absent:
        print("Named, not connected:")
        for k, v in absent:
            print(f"  {v.get('name', ''):22s} last seen {v.get('last_port', '?'):26s} {k}")
    return 0


def _find(target, devs, names):
    key = names.key_for_name(target) or dn.device_key(target)
    for d in devs:
        if d.port == target or d.key == key:
            return d
    return None


def _ask_name(d, names) -> int:
    current = names.name_for(d.key)
    try:
        name = input(f"Name for {d.description} on {d.port} (serial {d.serial or 'none'})"
                     f"{' [' + current + ']' if current else ''}: ").strip() or current
    except EOFError:
        name = ""
    if not name:
        print("not named")
        return 1
    try:
        names.set_name(d, name)
        names.save()
    except dn.NameError_ as e:
        print(f"error: {e}")
        return 1
    print(f"saved: {d.port} is '{name}'")
    return 0


def cmd_discover(args, names) -> int:
    tracker = dn.DiscoveryTracker(dn.scan_usb())
    print(f"Snapshot: {len(tracker.baseline)} USB device(s) connected.")
    print("Plug in the device to name now (unplug and re-plug it if it is already in). "
          f"Waiting up to {args.timeout:g} s, Ctrl-C to cancel…")
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < args.timeout:
            new = tracker.poll(dn.scan_usb())
            if new:
                for d in new:
                    print("New device:" + _row(d, names)[1:])
                    if not d.has_serial:
                        print("  warning: no USB serial number; the name is tied to this USB socket")
                return _ask_name(new[0], names)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\ncancelled")
        return 1
    print("No new USB device appeared. Check the cable (charge-only cables show nothing).")
    return 1


def cmd_name(args, names) -> int:
    devs = dn.scan_usb()
    d = _find(args.target, devs, names)
    if d is None:
        print(f"error: no connected device is '{args.target}' (use a port path, serial "
              f"number or existing name; see 'list')")
        return 1
    try:
        names.set_name(d, args.name)
        names.save()
    except dn.NameError_ as e:
        print(f"error: {e}")
        return 1
    print(f"saved: {d.port} is '{args.name}'")
    return 0


def cmd_forget(args, names) -> int:
    key = names.key_for_name(args.target) or dn.device_key(args.target)
    if not names.name_for(key):
        d = _find(args.target, dn.scan_usb(), names)
        key = d.key if d else key
    if not names.name_for(key):
        print(f"error: '{args.target}' has no name")
        return 1
    old = names.name_for(key)
    names.forget(key)
    names.save()
    print(f"forgot '{old}'")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="connected USB devices and their names")
    p = sub.add_parser("discover", help="snapshot, plug a device in, name it")
    p.add_argument("--timeout", type=float, default=60.0)
    p = sub.add_parser("name", help="name a connected device")
    p.add_argument("target", help="port path, serial number, or current name")
    p.add_argument("name")
    p = sub.add_parser("forget", help="remove a device's name")
    p.add_argument("target", help="name, serial number, or port path")
    args = ap.parse_args(argv)
    names = dn.DeviceNames()
    return {"list": cmd_list, "discover": cmd_discover, "name": cmd_name,
            "forget": cmd_forget}[args.cmd](args, names)


if __name__ == "__main__":
    sys.exit(main())
