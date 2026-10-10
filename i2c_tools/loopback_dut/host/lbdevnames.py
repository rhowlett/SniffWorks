#!/usr/bin/env python3
# [v0.1]
"""
loopback_dut/host/lbdevnames.py - resolve a device NAME to a serial port for
the loopback DUT tools ("--port 'H533 DUT'", or a name in rig.toml
[ports] dut).

Isolated: imports nothing from the sniffer tools (core/, ui/). It reads the
same per-user file the sniffer tools write (~/.ion_i2c_tool/device_names.json,
override ION_TOOL_DEVICE_NAMES) - sharing through a file is exactly what the
isolation rule allows. Names are created with the sniffer apps' "Name
devices…" button or tools/device_names.py; this reader never writes.

Identity: the USB serial number, normalized like core/device_names.py
(strip, drop a leading "SN:", upper-case) -> key "sn:<SERIAL>".
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STORE_ENV = "ION_TOOL_DEVICE_NAMES"
DEFAULT_PATH = Path.home() / ".ion_i2c_tool" / "device_names.json"


def _norm(serial) -> str:
    s = (serial or "").strip()
    if s.upper().startswith("SN:"):
        s = s[3:].strip()
    return s.upper()


def load_names(path=None) -> dict:
    """{key: name} from the per-user file; {} if missing or unreadable."""
    p = Path(path or os.environ.get(STORE_ENV) or DEFAULT_PATH)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {k: v.get("name", "") for k, v in (data.get("devices") or {}).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def resolve_port(arg: str, comports=None, names: dict | None = None) -> str:
    """Port path for `arg` (a port path, a USB serial number, or a device
    name). Raises LookupError listing what is connected."""
    if comports is None:
        from serial.tools import list_ports
        comports = list_ports.comports()
    ports = [p for p in comports if getattr(p, "vid", None) is not None]
    if arg in {p.device for p in ports} or arg.startswith("/dev/") or arg.upper().startswith("COM"):
        return arg
    names = load_names() if names is None else names
    want = arg.strip().casefold()
    key = next((k for k, n in names.items() if n.strip().casefold() == want), None) \
        or f"sn:{_norm(arg)}"
    for p in ports:
        if f"sn:{_norm(p.serial_number)}" == key:
            return p.device
    seen = ", ".join(f"{names.get('sn:' + _norm(p.serial_number), '') or '(unnamed)'} [{p.device}]"
                     for p in ports) or "none"
    raise LookupError(f"no connected device matches '{arg}'. Connected: {seen}. "
                      f"Name the DUT with the sniffer apps' 'Name devices…' button or "
                      f"python tools/device_names.py discover")
