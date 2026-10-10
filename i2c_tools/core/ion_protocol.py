"""
core/ion_protocol.py  [v0.2]
Wire protocol for the NUCLEO-C031C6 I2C sniffer firmware (sniffer_nucleoC0_fw).
Pure Python (no Qt, no pyserial) so it is unit-testable headlessly and shared
by the GUI backend (core.ion_backend), the CLI sanity-check script, and the
Phase 4 record/replay tools.

Authoritative spec: embedded/docs/PROTOCOL.md (protocol version 1).

Device -> Host framing:
    [0xAA][type][len lo][len hi][payload ...][crc8]
        crc8 (SMBus, poly 0x07, init 0x00) over type..payload.

Host -> Device commands (fixed 4 bytes in protocol v1):
    [0xA5][cmd][arg][crc8]      crc8 over cmd+arg.

Commands 0x10..0x13 are RESERVED for the Phase 4 master/replay firmware and
use a variable-length form [0xA5][cmd][len][payload...][crc8]; they are
declared here so the constant space is fixed before that firmware exists.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants (must match Core/Inc/frame_protocol.h)
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = 1

SYNC_DEV2HOST = 0xAA
SYNC_HOST2DEV = 0xA5

FRAME_TXN = 0x01
FRAME_STATUS = 0x02
FRAME_ERROR = 0x03
FRAME_HELLO = 0x04
_KNOWN_FRAME_TYPES = (FRAME_TXN, FRAME_STATUS, FRAME_ERROR, FRAME_HELLO)

CMD_START = 0x01
CMD_STOP = 0x02
CMD_STATUS_REQ = 0x03
CMD_PING = 0x04
CMD_RESET_COUNTS = 0x05

# Reserved for Phase 4 (master/replay firmware) — variable-length form.
CMD_I2C_WRITE = 0x10        # payload: addr7, data[]
CMD_I2C_WRITE_READ = 0x11   # payload: addr7, wlen, wdata[], rlen
CMD_I2C_READ = 0x12         # payload: addr7, rlen
CMD_SET_BUS_SPEED = 0x13    # payload: 0=100 kHz, 1=400 kHz

TXN_MAX_DATA = 64
MAX_PAYLOAD = 128           # plausibility gate for the parser

# TXN flags byte
FLAG_DIR_READ = 0x01
FLAG_NAK = 0x02
FLAG_RESTART = 0x04
FLAG_STOP = 0x08
FLAG_OVERFLOW = 0x10
FLAG_TIMEOUT = 0x20   # master transfer timed out
FLAG_FRAMING = 0x40   # fw >= 1.2: phase bit-slipped (lost SCL edge)

HELLO_MAGIC = b"NC0S"
MODE_NAMES = {1: "bit-bang", 2: "slave-monitor", 3: "master"}
ERROR_NAMES = {1: "UART ring overflow (frames lost)",
               2: "bad host command",
               3: "bus/decoder error"}

T_US_WRAP = 1 << 32         # device timestamps are 32-bit microseconds


# ---------------------------------------------------------------------------
# CRC-8 (SMBus): poly 0x07, init 0x00 — same routine as the firmware
# ---------------------------------------------------------------------------
def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


# ---------------------------------------------------------------------------
# Host -> Device
# ---------------------------------------------------------------------------
def build_command(cmd: int, arg: int = 0) -> bytes:
    """Fixed 4-byte protocol-v1 command frame."""
    body = bytes([cmd & 0xFF, arg & 0xFF])
    return bytes([SYNC_HOST2DEV]) + body + bytes([crc8(body)])


def build_var_command(cmd: int, payload: bytes) -> bytes:
    """Variable-length master command: [A5][cmd][len][payload][crc8],
    crc8 over cmd..payload. Firmware caps payload at 72 bytes."""
    if len(payload) > 72:
        raise ValueError(f"payload too long ({len(payload)} > 72)")
    body = bytes([cmd & 0xFF, len(payload) & 0xFF]) + bytes(payload)
    return bytes([SYNC_HOST2DEV]) + body + bytes([crc8(body)])


def encode_i2c_write(addr7: int, data: bytes) -> bytes:
    if len(data) > TXN_MAX_DATA:
        raise ValueError("write data exceeds TXN_MAX_DATA")
    return build_var_command(CMD_I2C_WRITE, bytes([addr7 & 0x7F]) + bytes(data))


def encode_i2c_write_read(addr7: int, wdata: bytes, rlen: int) -> bytes:
    if len(wdata) > TXN_MAX_DATA or rlen > TXN_MAX_DATA:
        raise ValueError("transfer exceeds TXN_MAX_DATA")
    payload = (bytes([addr7 & 0x7F, len(wdata)]) + bytes(wdata)
               + bytes([rlen & 0xFF]))
    return build_var_command(CMD_I2C_WRITE_READ, payload)


def encode_i2c_read(addr7: int, rlen: int) -> bytes:
    if rlen > TXN_MAX_DATA:
        raise ValueError("read length exceeds TXN_MAX_DATA")
    return build_var_command(CMD_I2C_READ, bytes([addr7 & 0x7F, rlen & 0xFF]))


def encode_set_bus_speed(speed: int) -> bytes:
    """speed: 0 = 100 kHz, 1 = 400 kHz."""
    if speed not in (0, 1):
        raise ValueError("speed must be 0 (100 kHz) or 1 (400 kHz)")
    return build_var_command(CMD_SET_BUS_SPEED, bytes([speed]))


CMD_START_BYTES = build_command(CMD_START)          # A5 01 00 15
CMD_STOP_BYTES = build_command(CMD_STOP)            # A5 02 00 2A
CMD_STATUS_REQ_BYTES = build_command(CMD_STATUS_REQ)
CMD_PING_BYTES = build_command(CMD_PING)


# ---------------------------------------------------------------------------
# Device -> Host frame parser (byte stream -> (type, payload), CRC-resync)
# ---------------------------------------------------------------------------
class FrameParser:
    """Feed arbitrary chunks; iterate complete, CRC-valid frames.

    Resilient to garbage and split frames: hunts for 0xAA, gates the header on
    a known type and plausible length before trusting it (prevents locking
    onto a stray 0xAA and stalling), slides one byte on CRC failure.
    """

    def __init__(self):
        self._buf = bytearray()
        self.bad_crc = 0

    def feed(self, data: bytes):
        """Yield (frame_type, payload) for each complete valid frame."""
        self._buf.extend(data)
        while True:
            i = self._buf.find(bytes([SYNC_DEV2HOST]))
            if i < 0:
                self._buf.clear()
                return
            if i > 0:
                del self._buf[:i]
            if len(self._buf) < 5:
                return                                  # need full header
            ftype = self._buf[1]
            plen = self._buf[2] | (self._buf[3] << 8)
            if ftype not in _KNOWN_FRAME_TYPES or plen > MAX_PAYLOAD:
                del self._buf[0]                        # not a real header
                continue
            total = 5 + plen
            if len(self._buf) < total:
                return                                  # need more bytes
            body = bytes(self._buf[1:4 + plen])         # type+len+payload
            rx_crc = self._buf[4 + plen]
            if crc8(body) == rx_crc:
                payload = bytes(self._buf[4:4 + plen])
                del self._buf[:total]
                yield ftype, payload
            else:
                self.bad_crc += 1
                del self._buf[0]                        # slide and re-hunt


# ---------------------------------------------------------------------------
# Payload decoders
# ---------------------------------------------------------------------------
def _u32(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off + 4], "little")


@dataclass(frozen=True)
class TxnRecord:
    """One decoded TXN frame — one I2C address phase."""
    t_us: int           # device timestamp, us (32-bit, wraps ~71.6 min)
    address: int        # 7-bit
    dir_read: bool
    nak: bool
    restart: bool       # this phase began with a repeated START
    stop: bool          # this phase ended with a STOP
    overflow: bool      # decoder dropped data before this frame
    timeout: bool       # master-mode: transfer exceeded the firmware budget
    data: bytes
    framing: bool = False  # fw >= 1.2: bytes are bit-slipped, don't trust them
    scl_hz: int | None = None  # fw >= 1.3: measured SCL of this phase (Hz);
    #                            None = older firmware or not measured


def decode_txn(p: bytes) -> TxnRecord | None:
    if len(p) < 7:
        return None
    t_us, addr, flags, dlen = _u32(p, 0), p[4], p[5], p[6]
    # fw >= 1.3 appends u32 scl_hz after the data; older frames end at data.
    tail = 7 + dlen
    scl = _u32(p, tail) if len(p) >= tail + 4 else 0
    return TxnRecord(
        t_us=t_us,
        address=addr & 0x7F,
        dir_read=bool(flags & FLAG_DIR_READ),
        nak=bool(flags & FLAG_NAK),
        restart=bool(flags & FLAG_RESTART),
        stop=bool(flags & FLAG_STOP),
        overflow=bool(flags & FLAG_OVERFLOW),
        timeout=bool(flags & FLAG_TIMEOUT),
        data=p[7:7 + dlen],
        framing=bool(flags & FLAG_FRAMING),
        scl_hz=scl or None,
    )


def decode_hello(p: bytes) -> dict | None:
    if len(p) < 8 or p[:4] != HELLO_MAGIC:
        return None
    return {"proto": p[4], "fw": f"{p[5]}.{p[6]}",
            "mode": MODE_NAMES.get(p[7], f"?{p[7]}")}


DIAG_TICKS_PER_US = 48          # fw 1.4 diag ticks = probe SYSCLK cycles


def _u16(b: bytes, off: int) -> int:
    return b[off] | (b[off + 1] << 8)


def decode_status(p: bytes) -> dict | None:
    if len(p) < 21:
        return None
    st = {"proto": p[0], "fw": f"{p[1]}.{p[2]}",
          "mode": MODE_NAMES.get(p[3], f"?{p[3]}"),
          "capturing": bool(p[4]),
          "captured": _u32(p, 5), "errors": _u32(p, 9),
          "dropped": _u32(p, 13), "bus_hz": _u32(p, 17)}
    # fw >= 1.4: trailing sampler-diagnostics block (PROTOCOL.md 1.2.1)
    if len(p) >= 45 and p[21] == 1:
        def us(ticks):        # 0xFFFF = none seen
            return None if ticks == 0xFFFF else round(ticks / DIAG_TICKS_PER_US, 3)
        st["diag"] = {
            "max_gap_us": round(_u16(p, 23) / DIAG_TICKS_PER_US, 3),
            "min_scl_high_us": us(_u16(p, 25)),
            "min_scl_low_us": us(_u16(p, 27)),
            "gaps_over_2us": _u32(p, 29),
            "framing_phases": _u32(p, 33),
            "framing_max_gap_us": round(_u16(p, 37) / DIAG_TICKS_PER_US, 3),
            "framing_min_scl_high_us": us(_u16(p, 39)),
            "upkeep_deferred": _u32(p, 41),
        }
    return st


def decode_error(p: bytes) -> dict:
    code = p[0] if len(p) >= 1 else 0
    detail = p[1] if len(p) >= 2 else 0
    return {"code": code, "detail": detail,
            "text": ERROR_NAMES.get(code, f"unknown error {code}")}


# ---------------------------------------------------------------------------
# Device timestamp -> wall-clock mapping (handles 32-bit us wrap)
# ---------------------------------------------------------------------------
class TimestampMapper:
    """Anchor the device's microsecond counter to host wall time on the first
    sample, then extend past 32-bit wraps (~71.6 min) monotonically."""

    def __init__(self):
        self._anchor_wall: float | None = None
        self._anchor_us: int | None = None
        self._last_us: int | None = None
        self._wraps = 0

    def to_wall(self, t_us: int, now: float) -> float:
        if self._anchor_wall is None:
            self._anchor_wall = now
            self._anchor_us = t_us
            self._last_us = t_us
            return now
        if t_us < self._last_us and (self._last_us - t_us) > (T_US_WRAP // 2):
            self._wraps += 1
        self._last_us = t_us
        extended = t_us + self._wraps * T_US_WRAP
        return self._anchor_wall + (extended - self._anchor_us) / 1e6
