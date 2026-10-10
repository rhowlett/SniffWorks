"""
core/device_names.py  [v0.1]
[XREF: device-names] Discovery and naming of USB-connected instruments, shared
by every app that talks to a USB device (sniffer_ion, sniffer_ad2, the AD2
tool, tools/ion_capture.py, tools/record_on_trigger.py, tools/device_names.py;
loopback_dut reads the same file with its own reader - isolation).

Identity is the USB **serial number**, normalized (whitespace stripped, a
leading "SN:" removed - the Digilent library reports the AD2 as
"SN:210321AC1ED9", pyserial as "210321AC1ED9" - upper-cased). A device with no
serial number falls back to vendor:product:USB-location, which is only as
stable as the socket it is plugged into.

Names are stored per user, shared by all apps on the machine (owner decision
2026-10-05), in ~/.ion_i2c_tool/device_names.json (override with the
ION_TOOL_DEVICE_NAMES environment variable, used by the tests):

    {"version": 1,
     "devices":   {"sn:066BFF544884654867102556": {"name": "C031 sniffer",
                    "serial": "...", "vid": 1155, "pid": 14155,
                    "description": "STM32 STLink", "manufacturer": "...",
                    "last_port": "/dev/cu.usbmodem1203", "named_on": "2026-10-05"}},
     "last_used": {"sniffer_ion": "sn:066B..."}}

No Qt here: the GUIs, the CLIs and the tests all use this module.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

STORE_ENV = "ION_TOOL_DEVICE_NAMES"
DEFAULT_PATH = Path.home() / ".ion_i2c_tool" / "device_names.json"


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
def normalize_serial(serial: Optional[str]) -> str:
    s = (serial or "").strip()
    if s.upper().startswith("SN:"):
        s = s[3:].strip()
    return s.upper()


def device_key(serial: Optional[str], vid: Optional[int] = None,
               pid: Optional[int] = None, location: Optional[str] = None) -> str:
    sn = normalize_serial(serial)
    if sn:
        return f"sn:{sn}"
    return f"loc:{(vid or 0):04X}:{(pid or 0):04X}:{location or '?'}"


@dataclass(frozen=True)
class UsbDevice:
    key: str
    serial: str
    vid: Optional[int]
    pid: Optional[int]
    port: str = ""                  # serial port path, "" if none
    location: str = ""
    description: str = ""
    manufacturer: str = ""

    @property
    def vid_pid(self) -> str:
        return f"{(self.vid or 0):04X}:{(self.pid or 0):04X}"

    @property
    def has_serial(self) -> bool:
        return self.key.startswith("sn:")


def _comports():
    from serial.tools import list_ports
    return list_ports.comports()


def scan_usb(comports: Callable[[], Iterable] = None) -> list[UsbDevice]:
    """Every USB device that exposes a serial port (ST-LINK VCPs, FTDI
    bridges - the AD2 included). Non-USB ports (Bluetooth, debug console:
    no vendor id) are skipped."""
    out = []
    for p in (comports or _comports)():
        if getattr(p, "vid", None) is None:
            continue
        out.append(UsbDevice(
            key=device_key(p.serial_number, p.vid, p.pid, getattr(p, "location", "")),
            serial=normalize_serial(p.serial_number),
            vid=p.vid, pid=p.pid, port=p.device or "",
            location=getattr(p, "location", "") or "",
            description=p.description or "",
            manufacturer=getattr(p, "manufacturer", "") or ""))
    out.sort(key=lambda d: d.port)
    return out


# ---------------------------------------------------------------------------
# Discovery: snapshot first, then report what appears
# ---------------------------------------------------------------------------
class DiscoveryTracker:
    """Start with a snapshot of the connected devices; every poll() returns
    the devices that were not in it. A device unplugged after the snapshot
    leaves the baseline, so unplugging and re-plugging a board that was
    already connected is still detected."""

    def __init__(self, initial: Iterable[UsbDevice]):
        self._baseline = {d.key for d in initial}

    @property
    def baseline(self) -> set:
        return set(self._baseline)

    def poll(self, current: Iterable[UsbDevice]) -> list[UsbDevice]:
        cur = {d.key: d for d in current}
        self._baseline &= set(cur)               # unplugged -> forget
        return [d for k, d in sorted(cur.items()) if k not in self._baseline]


# ---------------------------------------------------------------------------
# The per-user store
# ---------------------------------------------------------------------------
class NameError_(ValueError):
    """A name that is empty or already used by another device."""


class DeviceNames:
    def __init__(self, path: Optional[str | os.PathLike] = None):
        self.path = Path(path or os.environ.get(STORE_ENV) or DEFAULT_PATH)
        self._data = {"version": 1, "devices": {}, "last_used": {}}
        self.reload()

    # -- persistence ------------------------------------------------------
    def reload(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._data["devices"] = dict(data.get("devices") or {})
                self._data["last_used"] = dict(data.get("last_used") or {})
        except (OSError, ValueError):
            pass                                  # missing / unreadable = empty

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".device_names.", dir=str(self.path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.path)                # atomic on one filesystem

    # -- names --------------------------------------------------------------
    def entries(self) -> dict:
        return {k: dict(v) for k, v in self._data["devices"].items()}

    def name_for(self, key_or_serial: str) -> str:
        key = key_or_serial if ":" in key_or_serial and key_or_serial.split(":", 1)[0] in ("sn", "loc") \
            else device_key(key_or_serial)
        return (self._data["devices"].get(key) or {}).get("name", "")

    def key_for_name(self, name: str) -> Optional[str]:
        want = (name or "").strip().casefold()
        for k, v in self._data["devices"].items():
            if v.get("name", "").strip().casefold() == want:
                return k
        return None

    def set_name(self, dev: UsbDevice, name: str) -> None:
        name = (name or "").strip()
        if not name:
            raise NameError_("a device name cannot be empty")
        other = self.key_for_name(name)
        if other is not None and other != dev.key:
            raise NameError_(f"'{name}' is already the name of another device ({other})")
        entry = self._data["devices"].setdefault(dev.key, {})
        entry.update({"name": name, "serial": dev.serial, "vid": dev.vid, "pid": dev.pid,
                      "description": dev.description, "manufacturer": dev.manufacturer,
                      "last_port": dev.port})
        entry.setdefault("named_on", _dt.date.today().isoformat())

    def forget(self, key: str) -> None:
        self._data["devices"].pop(key, None)
        for app, k in list(self._data["last_used"].items()):
            if k == key:
                self._data["last_used"].pop(app)

    def note_port(self, dev: UsbDevice) -> None:
        """Remember where a named device was last seen (display only)."""
        e = self._data["devices"].get(dev.key)
        if e is not None and dev.port:
            e["last_port"] = dev.port

    # -- last used, per app (pre-select by serial, not by port name) -------
    def last_used(self, app: str) -> Optional[str]:
        return self._data["last_used"].get(app)

    def set_last_used(self, app: str, key: str) -> None:
        self._data["last_used"][app] = key

    # -- labels -------------------------------------------------------------
    def label(self, dev: UsbDevice) -> str:
        name = self.name_for(dev.key)
        base = f"{dev.port} — {dev.description}" if dev.port else dev.description
        return f"{name} — {base}" if name else base


# ---------------------------------------------------------------------------
# Resolution for command-line tools: "--port <name | serial | path>"
# ---------------------------------------------------------------------------
def resolve_port(arg: str, devices: Optional[list[UsbDevice]] = None,
                 names: Optional[DeviceNames] = None) -> str:
    """Return a serial port path for `arg`, which may be a device name, a USB
    serial number, or a port path. Raises LookupError with a helpful list."""
    devices = scan_usb() if devices is None else devices
    names = names or DeviceNames()
    if arg in {d.port for d in devices} or (arg.startswith("/dev/") or arg.upper().startswith("COM")):
        return arg
    key = names.key_for_name(arg) or device_key(arg)
    for d in devices:
        if d.key == key and d.port:
            return d.port
    named = sorted(v.get("name") for v in names.entries().values() if v.get("name"))
    connected = ", ".join(f"{names.name_for(d.key) or '(unnamed)'} [{d.port}]" for d in devices) or "none"
    raise LookupError(f"no connected device matches '{arg}'. Connected: {connected}. "
                      f"Known names: {', '.join(named) or 'none'}. "
                      f"Name devices with: python tools/device_names.py discover")
