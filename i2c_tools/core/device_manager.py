"""
device_manager.py
Handles enumeration, open, close, and health-check of the Analog Discovery 2.
"""

import ctypes
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class DeviceInfo:
    index: int
    name: str
    serial: str
    is_open: bool


class DeviceManager:
    """Wraps DWF device open/close/enum calls."""

    HDWF_NONE = 0

    def __init__(self, dwf, constants):
        self._dwf = dwf
        self._c = constants
        self._hdwf = ctypes.c_int(self.HDWF_NONE)

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------
    def enumerate_devices(self) -> List[DeviceInfo]:
        """Return list of connected WaveForms devices."""
        count = ctypes.c_int(0)
        self._dwf.FDwfEnum(self._c.enumfilterAll, ctypes.byref(count))

        devices = []
        for i in range(count.value):
            name_buf = ctypes.create_string_buffer(32)
            serial_buf = ctypes.create_string_buffer(16)
            is_open = ctypes.c_int(0)

            self._dwf.FDwfEnumDeviceName(ctypes.c_int(i), name_buf)
            self._dwf.FDwfEnumSN(ctypes.c_int(i), serial_buf)
            self._dwf.FDwfEnumDeviceIsOpened(ctypes.c_int(i), ctypes.byref(is_open))

            devices.append(DeviceInfo(
                index=i,
                name=name_buf.value.decode("ascii", errors="replace").strip("\x00"),
                serial=serial_buf.value.decode("ascii", errors="replace").strip("\x00"),
                is_open=bool(is_open.value),
            ))
        return devices

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------
    def open(self, device_index: int = -1) -> bool:
        """
        Open device by index (-1 = first available).
        Returns True on success.
        """
        self._dwf.FDwfDeviceOpen(ctypes.c_int(device_index), ctypes.byref(self._hdwf))
        return self._hdwf.value != self.HDWF_NONE

    def close(self):
        """Close current device."""
        if self._hdwf.value != self.HDWF_NONE:
            self._dwf.FDwfDeviceClose(self._hdwf)
            self._hdwf = ctypes.c_int(self.HDWF_NONE)

    def close_all(self):
        self._dwf.FDwfDeviceCloseAll()
        self._hdwf = ctypes.c_int(self.HDWF_NONE)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._hdwf.value != self.HDWF_NONE

    @property
    def handle(self) -> ctypes.c_int:
        return self._hdwf

    # ------------------------------------------------------------------
    # Error / diagnostics
    # ------------------------------------------------------------------
    def last_error(self) -> str:
        buf = ctypes.create_string_buffer(512)
        self._dwf.FDwfGetLastErrorMsg(buf)
        return buf.value.decode("ascii", errors="replace")

    def device_temperature(self) -> Optional[float]:
        """Read on-board temperature (°C). Returns None on error."""
        if not self.is_open:
            return None
        temp = ctypes.c_double(0.0)
        ret = self._dwf.FDwfAnalogIOChannelNodeGet(
            self._hdwf, ctypes.c_int(0), ctypes.c_int(0), ctypes.byref(temp)
        )
        if ret == 0:
            return None
        return round(temp.value, 2)

    def supply_voltage(self) -> Optional[float]:
        """Read USB supply voltage (V). Returns None on error."""
        if not self.is_open:
            return None
        self._dwf.FDwfAnalogIOStatus(self._hdwf)
        voltage = ctypes.c_double(0.0)
        ret = self._dwf.FDwfAnalogIOChannelNodeStatus(
            self._hdwf, ctypes.c_int(0), ctypes.c_int(0), ctypes.byref(voltage)
        )
        if ret == 0:
            return None
        return round(voltage.value, 3)

    def run_self_test(self) -> dict:
        """
        Run a basic connectivity check on the open device.
        Returns dict with keys: passed, version, temperature, supply, error.
        """
        result = {"passed": False, "version": "", "temperature": None, "supply": None, "error": ""}

        if not self.is_open:
            result["error"] = "Device not open"
            return result

        # DWF version
        buf = ctypes.create_string_buffer(16)
        self._dwf.FDwfGetVersion(buf)
        result["version"] = buf.value.decode("ascii", errors="replace")

        # Temperature
        result["temperature"] = self.device_temperature()

        # Supply voltage
        result["supply"] = self.supply_voltage()

        result["passed"] = True
        return result
