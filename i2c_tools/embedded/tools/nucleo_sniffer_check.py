#!/usr/bin/env python3
"""
nucleo_sniffer_check.py
Terminal sanity check for the NUCLEO-C031C6 I2C sniffer firmware.
Self-contained (only needs pyserial) - implements the wire protocol from
embedded/docs/PROTOCOL.md.

    pip install pyserial

Usage:
    python3 nucleo_sniffer_check.py                 # auto-detect port
    python3 nucleo_sniffer_check.py /dev/ttyACM0    # explicit port
    python3 nucleo_sniffer_check.py --baud 921600
    python3 nucleo_sniffer_check.py --seconds 10    # capture then auto-stop

Sequence: PING -> expect HELLO -> START -> stream TXN/STATUS frames until
Ctrl+C (or --seconds elapses) -> STOP -> final STATUS summary.
Exit code 0 = device answered and behaved; 1 = problem found.
"""

import argparse
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is required:  pip install pyserial")

# ---------------------------------------------------------------------------
# Protocol constants (PROTOCOL.md / frame_protocol.h)
# ---------------------------------------------------------------------------
SYNC_DEV2HOST = 0xAA
SYNC_HOST2DEV = 0xA5

FRAME_TXN, FRAME_STATUS, FRAME_ERROR, FRAME_HELLO = 0x01, 0x02, 0x03, 0x04
CMD_START, CMD_STOP, CMD_STATUS_REQ, CMD_PING, CMD_RESET_COUNTS = 1, 2, 3, 4, 5

FLAG_DIR_READ, FLAG_NAK, FLAG_RESTART, FLAG_STOP, FLAG_OVERFLOW = 1, 2, 4, 8, 16

HELLO_MAGIC = b"NC0S"
MODE_NAMES = {1: "bit-bang", 2: "slave-monitor"}
ERR_NAMES = {1: "UART ring overflow (frames lost)",
             2: "bad host command",
             3: "bus/decoder error"}


def crc8(data: bytes) -> int:
    """SMBus CRC-8: poly 0x07, init 0x00 (same as firmware/host app)."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def command(cmd: int, arg: int = 0) -> bytes:
    body = bytes([cmd, arg])
    return bytes([SYNC_HOST2DEV]) + body + bytes([crc8(body)])


# ---------------------------------------------------------------------------
# Frame parser (byte stream -> (type, payload) tuples, resync on bad CRC)
# ---------------------------------------------------------------------------
class FrameParser:
    def __init__(self):
        self._buf = bytearray()
        self.bad_crc = 0

    def feed(self, data: bytes):
        """Yield (type, payload) for each complete, CRC-valid frame."""
        self._buf.extend(data)
        while True:
            # hunt for sync
            i = self._buf.find(bytes([SYNC_DEV2HOST]))
            if i < 0:
                self._buf.clear()
                return
            if i > 0:
                del self._buf[:i]
            if len(self._buf) < 5:
                return                                  # need header
            ftype = self._buf[1]
            plen = self._buf[2] | (self._buf[3] << 8)
            total = 5 + plen
            # Plausibility gate before trusting the header: known type and a
            # realistic length (largest real frame is TXN: 7 + 64 bytes).
            # Prevents locking onto a stray 0xAA in garbage and stalling.
            if ftype not in (FRAME_TXN, FRAME_STATUS, FRAME_ERROR, FRAME_HELLO) \
               or plen > 128:
                del self._buf[0]
                continue
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
# Frame decoders / printers
# ---------------------------------------------------------------------------
def u32(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off + 4], "little")


def decode_hello(p: bytes):
    if len(p) < 8 or p[:4] != HELLO_MAGIC:
        return None
    return {"proto": p[4], "fw": f"{p[5]}.{p[6]}",
            "mode": MODE_NAMES.get(p[7], f"?{p[7]}")}


def decode_status(p: bytes):
    if len(p) < 21:
        return None
    return {"proto": p[0], "fw": f"{p[1]}.{p[2]}",
            "mode": MODE_NAMES.get(p[3], f"?{p[3]}"),
            "state": "CAPTURING" if p[4] else "idle",
            "captured": u32(p, 5), "errors": u32(p, 9),
            "dropped": u32(p, 13), "bus_hz": u32(p, 17)}


def print_txn(p: bytes, n: int):
    if len(p) < 7:
        print(f"  [txn {n}] short frame!")
        return
    t_us, addr, flags, dlen = u32(p, 0), p[4], p[5], p[6]
    data = p[7:7 + dlen]
    parts = [
        f"{t_us / 1e6:12.6f}s",
        f"0x{addr:02X}",
        "R" if flags & FLAG_DIR_READ else "W",
        "rS" if flags & FLAG_RESTART else "S ",
        "P" if flags & FLAG_STOP else "-",
        "NAK" if flags & FLAG_NAK else "ack",
        f"[{dlen:2d}]",
        " ".join(f"{b:02X}" for b in data) or "(no data)",
    ]
    if flags & FLAG_OVERFLOW:
        parts.append("**OVERFLOW**")
    print(f"  txn {n:5d}  " + "  ".join(parts))


# ---------------------------------------------------------------------------
# Port handling
# ---------------------------------------------------------------------------
def candidate_ports():
    """ST-LINK VCP first, then anything that looks like a USB serial port."""
    stlink, other = [], []
    for p in list_ports.comports():
        desc = f"{p.description} {p.manufacturer or ''}".lower()
        name = p.device
        if "stlink" in desc or "st-link" in desc or (p.vid == 0x0483):
            stlink.append(name)
        elif "usbmodem" in name or "ttyacm" in name.lower() or "usbserial" in name:
            other.append(name)
    return stlink + other


def open_and_hello(port: str, baud: int, verbose=True):
    """Open a port, send PING, wait briefly for HELLO. Returns (ser, hello)."""
    ser = serial.Serial(port, baud, timeout=0.2)
    parser = FrameParser()
    # board may also have sent its boot HELLO already; just PING it
    ser.reset_input_buffer()
    ser.write(command(CMD_PING))
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        data = ser.read(64)
        for ftype, payload in parser.feed(data):
            if ftype == FRAME_HELLO:
                h = decode_hello(payload)
                if h:
                    return ser, h
    ser.close()
    if verbose:
        print(f"  no HELLO from {port}")
    return None, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="NUCLEO-C031C6 sniffer sanity check")
    ap.add_argument("port", nargs="?", help="serial port (default: auto-detect)")
    ap.add_argument("--baud", type=int, default=115200,
                    help="must match HOST_UART_BAUD in the firmware (default 115200)")
    ap.add_argument("--seconds", type=float, default=0,
                    help="capture duration; 0 = until Ctrl+C (default)")
    args = ap.parse_args()

    # ---- 1. find the board -------------------------------------------------
    ports = [args.port] if args.port else candidate_ports()
    if not ports:
        sys.exit("No candidate serial ports found. Is the Nucleo plugged in?")

    ser = hello = None
    print("Probing for sniffer...")
    for port in ports:
        print(f"  trying {port} @ {args.baud}")
        try:
            ser, hello = open_and_hello(port, args.baud)
        except (serial.SerialException, OSError) as e:
            print(f"  {port}: {e}")
            continue
        if ser:
            break
    if not ser:
        sys.exit("FAIL: no device answered PING with a valid HELLO.\n"
                 "Check: board flashed? correct --baud? port not held open by "
                 "another program (CubeIDE serial console, screen, etc.)?")

    print(f"\nPASS: HELLO from {ser.port} — fw {hello['fw']}, protocol "
          f"{hello['proto']}, mode: {hello['mode']}")

    parser = FrameParser()
    txn_n = 0
    last_status = None
    rc = 0

    try:
        # ---- 2. start capture ---------------------------------------------
        ser.write(command(CMD_START))
        stop_at = time.monotonic() + args.seconds if args.seconds > 0 else None
        print("Capture started (LD4 solid). Generate I2C traffic now. "
              + ("Ctrl+C to stop.\n" if not stop_at else
                 f"Stopping in {args.seconds:g}s.\n"))

        # ---- 3. stream ------------------------------------------------------
        while stop_at is None or time.monotonic() < stop_at:
            data = ser.read(256)
            if not data:
                continue
            for ftype, payload in parser.feed(data):
                if ftype == FRAME_TXN:
                    txn_n += 1
                    print_txn(payload, txn_n)
                elif ftype == FRAME_STATUS:
                    st = decode_status(payload)
                    last_status = st
                    if st:
                        hz = f"{st['bus_hz'] / 1000:.0f} kHz" if st["bus_hz"] else "n/a"
                        print(f"  -- status: {st['state']}, captured={st['captured']}, "
                              f"errors={st['errors']}, dropped={st['dropped']}, "
                              f"bus≈{hz}")
                elif ftype == FRAME_ERROR:
                    code = payload[0] if payload else 0
                    print(f"  !! ERROR frame: "
                          f"{ERR_NAMES.get(code, f'code {code}')}")
                elif ftype == FRAME_HELLO:
                    pass          # board reset mid-capture would show this
    except KeyboardInterrupt:
        print("\n(Ctrl+C)")

    # ---- 4. stop + final status --------------------------------------------
    ser.write(command(CMD_STOP))
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        for ftype, payload in parser.feed(ser.read(64)):
            if ftype == FRAME_STATUS:
                last_status = decode_status(payload)
                deadline = 0
    ser.close()

    print("\n=== Summary ===")
    print(f"TXN frames printed : {txn_n}")
    print(f"CRC errors on link : {parser.bad_crc}")
    if last_status:
        print(f"Device counters    : captured={last_status['captured']}, "
              f"errors={last_status['errors']}, dropped={last_status['dropped']}")
        if last_status["bus_hz"]:
            print(f"Measured bus clock : ~{last_status['bus_hz'] / 1000:.0f} kHz")
        if last_status["dropped"]:
            print("NOTE: frames were dropped — consider rebuilding with "
                  "-DHOST_UART_BAUD=921600 and rerunning with --baud 921600.")
    if parser.bad_crc:
        rc = 1
        print("FAIL: CRC errors seen on the serial link.")
    else:
        print("Sanity check OK.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
