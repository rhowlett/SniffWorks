#!/usr/bin/env python3
# [v0.1]
"""
loopback_dut/host/lbcommon.py - pure helpers shared by loopback_run.py and
loopback_compare.py: CRC-8 line sealing, rig.toml loading and target
resolution, and an INDEPENDENT Python model of the DUT (register map, PEC,
address ACK/NAK) used for --dry-run and to cross-check the hardware.

The model is written from loopback_dut/docs/PROTOCOL.md, not ported from the
C firmware, so the two implementations check each other (the literal vectors
in tests/test_host_model.py are the same ones test_dut_regmap.c pins).

Isolated: imports nothing from the sniffer tools (core/, ui/).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import Optional

# ------------------------------------------------------------------ CRC-8
def crc8(data: bytes, crc: int = 0) -> int:
    """CRC-8/SMBUS: poly 0x07, init 0, no reflection, no final XOR."""
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def seal(line: str) -> str:
    """Append ' *CC' (CRC of every character before it)."""
    return f"{line} *{crc8(line.encode('ascii')):02X}"


def unseal(line: str) -> Optional[str]:
    """Strip and verify ' *CC'. None if missing or wrong."""
    line = line.rstrip("\r\n")
    if len(line) < 4 or line[-4:-2] != " *":
        return None
    body, cc = line[:-4], line[-2:]
    try:
        return body if int(cc, 16) == crc8(body.encode("ascii")) else None
    except ValueError:
        return None


# ------------------------------------------------------------------ rig
@dataclass
class Responder:
    name: str
    id: int
    address: int
    enabled: bool
    word_base: int


@dataclass
class Rig:
    raw: dict
    responders: list[Responder]
    nak_addresses: list[int]
    default_scl_hz: int
    rise_ns: int
    fall_ns: int
    master_own_address: int

    def by_name(self, name: str) -> Responder:
        for r in self.responders:
            if r.name == name:
                return r
        raise KeyError(f"rig has no responder {name!r}")

    def by_address(self, addr: int) -> Optional[Responder]:
        for r in self.responders:
            if r.address == addr:
                return r
        return None

    def resolve(self, step: dict) -> int:
        """7-bit address of a pattern step (target name or literal address)."""
        if "address" in step:
            return int(step["address"])
        t = step["target"]
        if t == "NAK":
            return self.nak_addresses[0]
        return self.by_name(t).address


def load_rig(path: str) -> Rig:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    resp = [Responder(r["name"], int(r["id"]), int(r["address"]), bool(r["enabled"]),
                      int(r["word_base"])) for r in raw["responder"]]
    if len({r.address for r in resp}) != len(resp):
        raise ValueError("rig.toml: responder addresses must be unique")
    return Rig(raw=raw, responders=resp,
               nak_addresses=[int(a) for a in raw["nak"]["addresses"]],
               default_scl_hz=int(raw["rig"]["default_scl_hz"]),
               rise_ns=int(raw["rig"]["rise_ns"]), fall_ns=int(raw["rig"]["fall_ns"]),
               master_own_address=int(raw["master"]["own_address"]))


# ------------------------------------------------------------ DUT model
BLOCK_START, BLOCK_END, BLOCK_DATA = 0x3E, 0x61, 32


class RegMap:
    """PROTOCOL.md §4, from the prose."""

    def __init__(self, base: int):
        self.base, self.ptr, self.subcmd, self._sub_lo = base, 0, 0, 0

    def write(self, index: int, b: int) -> None:
        if index == 0:
            self.ptr = b
        elif self.ptr == BLOCK_START and index == 1:
            self._sub_lo = b
        elif self.ptr == BLOCK_START and index == 2:
            self.subcmd = self._sub_lo | (b << 8)

    def block(self) -> bytes:
        lo, hi = self.subcmd & 0xFF, self.subcmd >> 8
        buf = bytes(((0x40 + i) ^ lo) for i in range(BLOCK_DATA))
        chk = (~(lo + hi + sum(buf))) & 0xFF
        return bytes([lo, hi]) + buf + bytes([chk, BLOCK_DATA + 4])

    def read(self, k: int) -> int:
        if BLOCK_START <= self.ptr <= BLOCK_END:
            off = self.ptr - BLOCK_START + k
            blk = self.block()
            return blk[off] if off < len(blk) else 0xFF
        word = (self.base + self.ptr + k // 2) & 0xFFFF
        return (word >> 8) if (k & 1) else (word & 0xFF)


@dataclass
class Phase:
    start: str                  # "S" | "Sr"
    address: int
    dir: str                    # "W" | "R"
    ack: str                    # "A" | "NA" | "ND" | "ER"
    stop: bool
    data: list[int] = field(default_factory=list)
    pec: bool = False           # last data byte is an SMBus PEC

    def to_json(self) -> dict:
        return {"start": self.start, "address": self.address, "dir": self.dir,
                "ack": self.ack, "stop": self.stop, "data": list(self.data), "pec": self.pec}


class DutModel:
    """Bus-level model of the whole DUT (I2C1 master + two responders)."""

    def __init__(self, rig: Rig):
        self.rig = rig
        self.maps = {r.address: RegMap(r.word_base) for r in rig.responders}
        self.enabled = {r.address: r.enabled for r in rig.responders}
        self.pec_after: dict[int, int] = {r.address: 0 for r in rig.responders}

    def acks(self, addr: int) -> bool:
        return self.enabled.get(addr, False)      # master's own address never ACKs

    def _read(self, addr: int, n: int, crc: int) -> list[int]:
        m, pa, out = self.maps[addr], self.pec_after[addr], []
        for k in range(n):
            if pa and k == pa:
                b = crc
            else:
                b = m.read(k - 1 if (pa and k > pa) else k)
            crc = crc8(bytes([b]), crc)
            out.append(b)
        return out

    def step(self, step: dict, host_pec: bool = False) -> list[Phase]:
        """Phases one pattern step puts on the bus. `data` excludes host PEC."""
        a = self.rig.resolve(step)
        op = step["op"]
        wdata = list(step.get("data", []))
        if host_pec and op in ("write",):
            wdata.append(crc8(bytes([a << 1] + wdata)))
        n = int(step.get("read_len", 0))
        ok = self.acks(a)
        ph: list[Phase] = []
        read_pec = bool(step.get("pec")) and op != "write"

        def write_phase(stop: bool) -> tuple[Phase, int]:
            if not ok:
                return Phase("S", a, "W", "NA", True, []), 0
            m = self.maps[a]
            for i, b in enumerate(wdata):
                m.write(i, b)
            return Phase("S", a, "W", "A", stop, wdata), crc8(bytes([a << 1] + wdata))

        if op == "write":
            p, _ = write_phase(True)
            p.pec = host_pec and ok
            ph.append(p)
        elif op == "read":
            if not ok:
                ph.append(Phase("S", a, "R", "NA", True, []))
            else:
                ph.append(Phase("S", a, "R", "A", True,
                                self._read(a, n, crc8(bytes([(a << 1) | 1]))), read_pec))
        elif op == "write_read":
            p, crc = write_phase(False)
            ph.append(p)
            if ok:
                crc = crc8(bytes([(a << 1) | 1]), crc)
                ph.append(Phase("Sr", a, "R", "A", True, self._read(a, n, crc), read_pec))
        elif op == "write_stop_read":
            p, _ = write_phase(True)
            ph.append(p)
            if ok:
                ph.append(Phase("S", a, "R", "A", True,
                                self._read(a, n, crc8(bytes([(a << 1) | 1]))), read_pec))
        else:
            raise ValueError(f"unknown op {op!r}")
        return ph


def phases_per_step(op: str) -> int:
    return {"write": 1, "read": 1, "write_read": 2, "write_stop_read": 2}[op]
