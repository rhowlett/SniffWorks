"""
i2c_controller.py  [v0.1]
Wraps all DWF Digital I2C functions:
  - Configuration (pins, rate, pull-up, clock-stretch)
  - Master read / write / write-read
  - Spy (passive sniffer) mode via FDwfDigitalI2cSpyStart / SpyStatus
  - SMBus PEC (CRC-8) calculation
"""

import ctypes
import time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from enum import IntEnum


# ---------------------------------------------------------------------------
# SMBus CRC-8 (polynomial 0x07)
# ---------------------------------------------------------------------------
def smbus_crc8(data: bytes) -> int:
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class I2CDirection(IntEnum):
    WRITE = 0
    READ = 1


@dataclass
class I2CTransaction:
    """Represents one captured or issued I2C transaction."""
    timestamp: float          # time.time()
    address: int              # 7-bit address
    direction: I2CDirection
    data: bytes
    nak: bool = False         # NAK received
    start: int = 1            # 1=START, 2=RESTART
    stop: bool = True
    pec_valid: Optional[bool] = None   # None = not checked
    raw_frame: bytes = field(default_factory=bytes)  # raw spy bytes
    scl_hz: Optional[int] = None   # measured SCL of this phase, Hz (ion probe
    #                                fw >= 1.3, bit-bang mode); None = unknown

    @property
    def timestamp_str(self) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S.%f")[:-3]

    @property
    def addr_str(self) -> str:
        return f"0x{self.address:02X}"

    @property
    def data_hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def dir_str(self) -> str:
        return "R" if self.direction == I2CDirection.READ else "W"

    @property
    def pec_str(self) -> str:
        if self.pec_valid is None:
            return ""
        return "✓ PEC" if self.pec_valid else "✗ PEC"

    @property
    def length(self) -> int:
        return len(self.data)

    @property
    def scl_hz_str(self) -> str:
        """Capture CSV v2 'SCL (Hz)' cell: integer Hz, empty when unknown."""
        return str(int(self.scl_hz)) if self.scl_hz else ""


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
class I2CController:
    """
    Wraps the DWF Digital I2C API for master read/write and passive sniffer.
    """

    MAX_BYTES = 256   # max buffer for a single transfer

    # Negative iNak codes returned by FDwfDigitalI2cSpyStatus
    _NAK_ERROR_CODES = {
        -1:  "Invalid start (unexpected SDA falling edge while SCL high)",
        -2:  "Invalid restart (between bits or ACK cycle)",
        -3:  "Invalid stop (between bits or ACK cycle)",
        -10: "Device buffer overflow (warning) — capture lagging",
        -11: "Device buffer overflow (error) — samples lost",
    }

    def __init__(self, dwf, device_handle: ctypes.c_int):
        self._dwf = dwf
        self._hdwf = device_handle

        # Current config (defaults)
        self._scl_pin: int = 0
        self._sda_pin: int = 1
        self._alert_pin: int = -1       # -1 = not used
        self._rate_hz: float = 100_000  # 100 kHz
        self._stretch: bool = True
        self._spy_running: bool = False

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def configure(
        self,
        scl_pin: int,
        sda_pin: int,
        alert_pin: int,
        rate_hz: float,
        clock_stretch: bool = True,
    ):
        """Apply pin assignments and rate to the DWF I2C engine.

        rate_hz == 0 means "Auto": the DWF I2C engine has no auto-detect for the
        master clock, so we apply a safe 100 kHz default to the hardware while
        recording the configured rate as 0 (Auto) for display purposes.
        """
        self._scl_pin = scl_pin
        self._sda_pin = sda_pin
        self._alert_pin = alert_pin
        self._rate_hz = rate_hz
        self._stretch = clock_stretch

        effective_rate = rate_hz if rate_hz and rate_hz > 0 else 100_000

        self._dwf.FDwfDigitalI2cStretchSet(self._hdwf, ctypes.c_int(1 if clock_stretch else 0))
        self._dwf.FDwfDigitalI2cRateSet(self._hdwf, ctypes.c_double(effective_rate))
        self._dwf.FDwfDigitalI2cSclSet(self._hdwf, ctypes.c_int(scl_pin))
        self._dwf.FDwfDigitalI2cSdaSet(self._hdwf, ctypes.c_int(sda_pin))

    def clear_bus(self) -> Tuple[bool, str]:
        """
        Run FDwfDigitalI2cClear to resolve bus lockup.
        Returns (ok, error_message).
        """
        nak = ctypes.c_int(0)
        ret = self._dwf.FDwfDigitalI2cClear(self._hdwf, ctypes.byref(nak))
        if ret == 0:
            return False, self._last_error()
        if nak.value == 0:
            return False, "Bus error: SDA still LOW after clear (no pull-ups?)"
        return True, ""

    # ------------------------------------------------------------------
    # Master write
    # ------------------------------------------------------------------
    def write(self, address7: int, data: bytes, add_pec: bool = False) -> Tuple[bool, str, I2CTransaction]:
        """
        Write bytes to a 7-bit I2C address.
        Returns (success, error, transaction).
        """
        payload = bytearray(data)
        if add_pec:
            addr_byte = (address7 << 1) & 0xFE
            payload.append(smbus_crc8(bytes([addr_byte]) + bytes(data)))

        buf = (ctypes.c_ubyte * len(payload))(*payload)
        nak = ctypes.c_int(0)
        ts = time.time()

        ret = self._dwf.FDwfDigitalI2cWrite(
            self._hdwf,
            ctypes.c_int(address7 << 1),
            buf,
            ctypes.c_int(len(payload)),
            ctypes.byref(nak),
        )

        ok = (ret != 0) and (nak.value == 0)
        err = "" if ok else (f"NAK at byte {nak.value}" if nak.value else self._last_error())

        txn = I2CTransaction(
            timestamp=ts,
            address=address7,
            direction=I2CDirection.WRITE,
            data=bytes(payload),
            nak=not ok,
        )
        return ok, err, txn

    # ------------------------------------------------------------------
    # Master read
    # ------------------------------------------------------------------
    def read(self, address7: int, count: int, check_pec: bool = False) -> Tuple[bool, str, I2CTransaction]:
        """
        Read `count` bytes from a 7-bit I2C address.
        Returns (success, error, transaction).
        """
        buf = (ctypes.c_ubyte * count)()
        nak = ctypes.c_int(0)
        ts = time.time()

        ret = self._dwf.FDwfDigitalI2cRead(
            self._hdwf,
            ctypes.c_int((address7 << 1) | 1),
            buf,
            ctypes.c_int(count),
            ctypes.byref(nak),
        )

        raw = bytes(buf)
        ok = (ret != 0) and (nak.value == 0)
        err = "" if ok else (f"NAK at byte {nak.value}" if nak.value else self._last_error())

        pec_valid = None
        if check_pec and ok and count >= 1:
            payload = raw[:-1]
            received_pec = raw[-1]
            addr_byte = (address7 << 1) | 1
            expected_pec = smbus_crc8(bytes([addr_byte]) + payload)
            pec_valid = (received_pec == expected_pec)

        txn = I2CTransaction(
            timestamp=ts,
            address=address7,
            direction=I2CDirection.READ,
            data=raw,
            nak=not ok,
            pec_valid=pec_valid,
        )
        return ok, err, txn

    # ------------------------------------------------------------------
    # Write-then-read (register read)
    # ------------------------------------------------------------------
    def write_read(
        self,
        address7: int,
        write_data: bytes,
        read_count: int,
        check_pec: bool = False,
    ) -> Tuple[bool, str, List[I2CTransaction]]:
        """
        Write bytes then repeated-start read.
        Returns (success, error, [write_txn, read_txn]).
        """
        tx_buf = (ctypes.c_ubyte * len(write_data))(*write_data)
        rx_buf = (ctypes.c_ubyte * read_count)()
        nak = ctypes.c_int(0)
        ts = time.time()

        ret = self._dwf.FDwfDigitalI2cWriteRead(
            self._hdwf,
            ctypes.c_int(address7 << 1),
            tx_buf,
            ctypes.c_int(len(write_data)),
            rx_buf,
            ctypes.c_int(read_count),
            ctypes.byref(nak),
        )

        raw_rx = bytes(rx_buf)
        ok = (ret != 0) and (nak.value == 0)
        err = "" if ok else (f"NAK at byte {nak.value}" if nak.value else self._last_error())

        pec_valid = None
        if check_pec and ok and read_count >= 1:
            payload = raw_rx[:-1]
            received_pec = raw_rx[-1]
            addr_byte = (address7 << 1) | 1
            expected_pec = smbus_crc8(bytes([addr_byte]) + payload)
            pec_valid = (received_pec == expected_pec)

        write_txn = I2CTransaction(
            timestamp=ts,
            address=address7,
            direction=I2CDirection.WRITE,
            data=write_data,
            nak=not ok,
            stop=False,
        )
        read_txn = I2CTransaction(
            timestamp=ts,
            address=address7,
            direction=I2CDirection.READ,
            data=raw_rx,
            nak=not ok,
            start=2,
            pec_valid=pec_valid,
        )
        return ok, err, [write_txn, read_txn]

    # ------------------------------------------------------------------
    # Spy (passive sniffer)
    # ------------------------------------------------------------------
    def spy_start(self) -> Tuple[bool, str]:
        """Start passive I2C sniffing."""
        ret = self._dwf.FDwfDigitalI2cSpyStart(self._hdwf)
        if ret == 0:
            return False, self._last_error()
        self._spy_running = True
        return True, ""

    def spy_stop(self):
        """Stop passive sniffing (close the I2C engine)."""
        self._spy_running = False
        # The spy is stopped when a new operation starts or device closes

    def spy_poll(self, check_pec: bool = False) -> Tuple[bool, Optional[I2CTransaction], str]:
        """
        Poll for a captured I2C transaction.
        Returns (has_data, transaction_or_None, error).

        DWF spy status (per Digilent Digital_I2c_Spy.py sample):
          fStart: 0=no start, 1=START, 2=RESTART
          fStop : 0=no stop, 1=STOP
          rgData[0] = address byte (7-bit addr<<1 | R/W bit) WHEN fStart != 0
                      otherwise rgData[] are continuation data bytes
          cData : MUST be reset to buffer size before EACH call; on return it
                  holds the actual number of bytes captured.
          iNak  : NAK index + 1 (positive). Negative = protocol/buffer error:
                    -1  invalid start
                    -2  invalid restart
                    -3  invalid stop
                    -10 device buffer overflow warning
                    -11 device buffer overflow error
        """
        max_buf = self.MAX_BYTES
        start = ctypes.c_int(0)
        stop = ctypes.c_int(0)
        count = ctypes.c_int(max_buf)   # reset to buffer size BEFORE each call
        buf = (ctypes.c_ubyte * max_buf)()
        nak = ctypes.c_int(0)

        ret = self._dwf.FDwfDigitalI2cSpyStatus(
            self._hdwf,
            ctypes.byref(start),
            ctypes.byref(stop),
            buf,
            ctypes.byref(count),
            ctypes.byref(nak),
        )

        if ret == 0:
            return False, None, self._last_error()

        # Decode the negative error codes the SDK can report in iNak
        if nak.value < 0:
            return False, None, self._NAK_ERROR_CODES.get(
                nak.value, f"Spy protocol error ({nak.value})"
            )

        # A meaningful transaction frame begins with a START (fStart != 0),
        # where rgData[0] is the address byte. Without a start there is either
        # no new data, or mid-stream continuation bytes we fold into nothing here.
        if start.value == 0 or count.value == 0:
            return False, None, ""

        raw = bytes(buf[:count.value])
        addr_byte = raw[0]
        address7 = addr_byte >> 1
        direction = I2CDirection.READ if (addr_byte & 1) else I2CDirection.WRITE
        data_bytes = raw[1:] if count.value > 1 else b""

        # PEC check (last byte of data_bytes is the PEC when SMBus PEC enabled)
        pec_valid = None
        if check_pec and len(data_bytes) >= 1:
            payload = data_bytes[:-1]
            received_pec = data_bytes[-1]
            expected_pec = smbus_crc8(bytes([addr_byte]) + payload)
            pec_valid = (received_pec == expected_pec)

        txn = I2CTransaction(
            timestamp=time.time(),
            address=address7,
            direction=direction,
            data=data_bytes,
            nak=nak.value > 0,
            start=start.value,
            stop=bool(stop.value),
            pec_valid=pec_valid,
            raw_frame=raw,
        )
        return True, txn, ""

    # ------------------------------------------------------------------
    # Address scan
    # ------------------------------------------------------------------
    def scan_addresses(self, progress_cb=None) -> List[int]:
        """
        Scan all 7-bit addresses (0x03..0x77).
        Returns list of responding addresses.
        progress_cb(addr) called each step if provided.
        """
        found = []
        for addr in range(0x03, 0x78):
            if progress_cb:
                progress_cb(addr)
            buf = (ctypes.c_ubyte * 1)()
            nak = ctypes.c_int(0)
            self._dwf.FDwfDigitalI2cRead(
                self._hdwf,
                ctypes.c_int((addr << 1) | 1),
                buf,
                ctypes.c_int(1),
                ctypes.byref(nak),
            )
            if nak.value == 0:
                found.append(addr)
            time.sleep(0.001)
        return found

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _last_error(self) -> str:
        buf = ctypes.create_string_buffer(512)
        self._dwf.FDwfGetLastErrorMsg(buf)
        return buf.value.decode("ascii", errors="replace")

    @property
    def scl_pin(self) -> int:
        return self._scl_pin

    @property
    def sda_pin(self) -> int:
        return self._sda_pin

    @property
    def alert_pin(self) -> int:
        return self._alert_pin

    @property
    def rate_hz(self) -> float:
        return self._rate_hz

    @property
    def spy_running(self) -> bool:
        return self._spy_running
