#!/usr/bin/env python3
# [v0.2]
"""
loopback_dut/host/dut_link.py - PC side of the loopback DUT line protocol
(loopback_dut/docs/PROTOCOL.md). Transport-agnostic: give it any object with
write(bytes) and readline() -> bytes (pyserial Serial, or a test fake).

Every DUT line is CRC-verified. RUN replies are matched on the echoed <seq>:
a PH/END line carrying any other seq means the link has DESYNCED (a late
reply from an earlier command), which raises DesyncError naming the command
that was in flight. That is the rig-side guard the Phase 1 plan asks for.

Isolated: imports nothing from the sniffer tools (core/, ui/).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from lbcommon import Phase, seal, unseal

BAUD = 115200


class LinkError(Exception):
    """Transport or protocol error (bad CRC, timeout, ERR reply)."""


class DesyncError(LinkError):
    def __init__(self, sent_seq: int, line: str):
        super().__init__(f"desync: waiting for seq {sent_seq}, got {line!r}")
        self.sent_seq, self.line = sent_seq, line


class WrongDevice(LinkError):
    pass


@dataclass
class RunResult:
    seq: int
    iterations: list[dict] = field(default_factory=list)   # per iteration


def open_serial(port: str, timeout: float = 0.2):
    import serial  # pyserial, from the project .venv
    return serial.Serial(port, BAUD, timeout=timeout)


class DutLink:
    def __init__(self, port, reply_timeout_s: float = 2.0, log=None):
        self.port = port
        self.reply_timeout_s = reply_timeout_s
        self.bad_crc = 0
        self.log = log            # optional callable(str) for a transcript
        self.hello: Optional[str] = None

    # ---------------------------------------------------------- transport
    def _send(self, line: str) -> None:
        if self.log:
            self.log(f"-> {line}")
        self.port.write((seal(line) + "\n").encode("ascii"))

    def _line(self, deadline: float) -> str:
        while time.monotonic() < deadline:
            raw = self.port.readline()
            if not raw:
                continue
            text = raw.decode("ascii", errors="replace")
            body = unseal(text)
            if self.log:
                self.log(f"<- {text.rstrip()}")
            if body is None:
                self.bad_crc += 1
                raise LinkError(f"bad CRC on DUT line {text.rstrip()!r}")
            return body
        raise LinkError("timeout waiting for DUT reply")

    def _reply(self, want: tuple[str, ...], timeout: Optional[float] = None) -> str:
        deadline = time.monotonic() + (timeout or self.reply_timeout_s)
        while True:
            body = self._line(deadline)
            head = body.split(" ", 1)[0]
            if head == "ERR":
                raise LinkError(body)
            if head in want:
                return body
            if head in ("PH", "END"):
                raise DesyncError(-1, body)
            # HELLO after an unexpected reset etc.: surface it
            raise LinkError(f"unexpected line {body!r} (wanted {want})")

    # ------------------------------------------------------------ commands
    def handshake(self, attempts: int = 3) -> str:
        """PING until HELLO. The ST-LINK V3 VCP can drop or corrupt the first
        command after the board (re)enumerates (seen 2026-10-02: first PING
        after flashing timed out, DUT counted uart_ovr=1), so retry."""
        last: Exception = LinkError("no attempt")
        for _ in range(attempts):
            flush = getattr(self.port, "reset_input_buffer", None)
            if flush:
                time.sleep(0.1)
                flush()
            try:
                self._send("PING")
                body = self._reply(("HELLO",), timeout=1.0)
            except WrongDevice:
                raise
            except LinkError as e:
                last = e
                continue
            if not body.startswith("HELLO LBDUT "):
                raise WrongDevice(f"not a loopback DUT: {body!r}")
            self.hello = body
            return body
        raise LinkError(f"no HELLO after {attempts} PINGs: {last}")

    def command(self, line: str) -> str:
        self._send(line)
        return self._reply(("OK", "STATUS"))

    def set_speed(self, hz: int, rise_ns: int, fall_ns: int) -> dict:
        body = self.command(f"SET SPEED {hz} {rise_ns} {fall_ns}")
        return dict(kv.split("=", 1) for kv in body.split()[2:] if "=" in kv)

    def run(self, seq: int, cmd: str, rep: int = 1, gap_us: int = 0,
            timeout_s: Optional[float] = None) -> RunResult:
        opts = (f" rep={rep}" if rep > 1 else "") + (f" gap={gap_us}" if gap_us else "")
        self._send(f"RUN {seq} {cmd}{opts}")
        res = RunResult(seq)
        cur: list[Phase] = []
        deadline = time.monotonic() + (timeout_s or self.reply_timeout_s + 0.01 * rep)
        while len(res.iterations) < rep:
            body = self._line(deadline)
            tok = body.split()
            if tok[0] == "ERR":
                raise LinkError(body)
            if tok[0] not in ("PH", "END"):
                raise LinkError(f"unexpected line during RUN {seq}: {body!r}")
            if int(tok[1]) != seq:
                raise DesyncError(seq, body)
            if tok[0] == "PH":
                # PH seq iter idx start addr dir ack stop n bytes...
                n = int(tok[9])
                cur.append(Phase(start="Sr" if tok[4] == "SR" else "S",
                                 address=int(tok[5], 16), dir=tok[6], ack=tok[7],
                                 stop=(tok[8] == "P"),
                                 data=[int(b, 16) for b in tok[10:10 + n]]))
                if len(tok) != 10 + n:
                    raise LinkError(f"PH byte count mismatch: {body!r}")
            else:
                kv = dict(t.split("=", 1) for t in tok[4:] if "=" in t)
                res.iterations.append({"iter": int(tok[2]), "result": tok[3],
                                       "t_dut_us": int(kv.get("t", 0)),
                                       "dur_us": int(kv.get("dur", 0)),
                                       "t_host": time.time(), "phases": cur})
                cur = []
        return res
