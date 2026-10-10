#!/usr/bin/env python3
# [v0.3]
"""
loopback_dut/host/loopback_run.py - P1-T3 pattern driver for the loopback DUT.

Reads a pattern (loopback_dut/patterns/*.json) and the rig config
(loopback_dut/config/rig.toml), emits every case on the NUCLEO-H533RE DUT,
and writes expected.json: for each case and iteration, the bus phases as the
DUT master saw them (address, direction, bytes, S/Sr/P, ACK/NAK), the host
timestamp and the DUT timestamp. That file is the ground truth the
comparison harness (loopback_compare.py) checks a sniffer capture against.
It never comes from the sniffer being tested.

  --dry-run   no hardware: the phases come from the Python DUT model
              (lbcommon.DutModel). Used to test the harness.
  hardware    the phases come from the DUT; each case is also cross-checked
              against the model, and a difference is reported as
              emit_status "model_mismatch" (a DUT/wiring problem, not a
              sniffer problem).

A reply carrying the wrong sequence number aborts the run (exit 2) and names
the case that desynced.

Usage:
  python loopback_dut/host/loopback_run.py --dry-run [--out runs/expected.json]
  python loopback_dut/host/loopback_run.py --port /dev/cu.usbmodemXXXX
  python loopback_dut/host/loopback_run.py --port "H533 DUT"   # a device name
  python loopback_dut/host/loopback_run.py --list

Isolated: imports nothing from the sniffer tools (core/, ui/).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from lbcommon import DutModel, Phase, Rig, crc8, load_rig  # noqa: E402

DEFAULT_PATTERN = os.path.join(LB, "patterns", "loopback_v1.json")
DEFAULT_RIG = os.path.join(LB, "config", "rig.toml")
DEFAULT_OUT = os.path.join(LB, "runs", "expected.json")
EXPECTED_FORMAT, EXPECTED_VERSION = "loopback_expected", 1

OPCODE = {"write": "W", "read": "R", "write_read": "WR", "write_stop_read": "WPR"}


def step_wire_bytes(step: dict, addr: int) -> list[int]:
    """Bytes the master writes for a step (host appends PEC on PEC writes)."""
    data = list(step.get("data", []))
    if step.get("pec") and step["op"] == "write":
        data.append(crc8(bytes([addr << 1] + data)))
    return data


def step_command(step: dict, addr: int) -> str:
    op = OPCODE[step["op"]]
    wb = " ".join(f"{b:02X}" for b in step_wire_bytes(step, addr))
    if step["op"] == "write":
        return f"W {addr:02X} {wb}"
    if step["op"] == "read":
        return f"R {addr:02X} {step['read_len']}"
    return f"{op} {addr:02X} {step['read_len']} {wb}"


def phases_equal(a: list[Phase], b: list[Phase]) -> bool:
    key = lambda p: (p.start, p.address, p.dir, p.ack, p.stop, list(p.data))
    return [key(p) for p in a] == [key(p) for p in b]


class Runner:
    def __init__(self, rig: Rig, link=None, log=print):
        self.rig, self.link, self.log = rig, link, log
        self.seq = 0
        self.model = DutModel(rig)

    # -------------------------------------------------------------- setup
    def configure_rig(self) -> None:
        if not self.link:
            return
        self.link.command("RESET")
        for r in self.rig.responders:
            self.link.command(f"SET ADDR {r.id} {r.address:02X}")
            self.link.command(f"SET EN {r.id} {1 if r.enabled else 0}")

    def _pec_mode(self, step: dict, addr: int, on: bool) -> None:
        if not step.get("pec") or step["op"] == "write":
            return
        r = self.rig.by_address(addr)
        if r is None:
            raise ValueError(f"PEC read needs a responder, {addr:#04x} is not one")
        n = (int(step["read_len"]) - 1) if on else 0
        self.model.pec_after[addr] = n
        if self.link:
            self.link.command(f"SET PEC {r.id} {n}")

    # ---------------------------------------------------------------- run
    def run_case(self, case: dict) -> dict:
        hz = int(case.get("speed_hz", self.rig.default_scl_hz))
        rep = int(case.get("repeat", 1))
        gap = int(case.get("gap_us", 0))
        # ledger + expectation fields travel with the bus data (loopback_compare
        # reads them from here); keep this list in step with
        # loopback_compare.LEDGER_KEYS
        out = {k: case[k] for k in ("id", "description", "review_ids", "status", "expect",
                                     "path_status", "xfail_reason", "xfail_symptoms",
                                     "path_xfail_symptoms", "requires", "stretch") if k in case}
        out.update(speed_hz=hz, speed_pred_hz=None, repeat=rep, emit_status="ok", iterations=[])

        stretch = case.get("stretch")
        if self.link:
            sp = self.link.set_speed(hz, self.rig.rise_ns, self.rig.fall_ns)
            out["speed_pred_hz"] = int(sp.get("pred", 0)) or None
            if stretch:
                rid = self.rig.by_name(stretch["responder"]).id
                self.link.command(f"SET STRETCH {rid} {stretch['byte_index']} {stretch['us']}")
        try:
            steps = case["steps"]
            if len(steps) == 1 and rep > 1:
                out["iterations"] = self._run_step_repeated(steps[0], rep, gap, out)
            else:
                for it in range(rep):
                    out["iterations"].append(self._run_iteration(steps, it, out))
                    if gap and self.link:
                        time.sleep(gap / 1e6)        # multi-step: host-paced gap
        finally:
            if self.link and stretch:
                rid = self.rig.by_name(stretch["responder"]).id
                self.link.command(f"SET STRETCH {rid} 0 0")
        return out

    def _model_phases(self, step: dict) -> list[Phase]:
        return self.model.step(step, host_pec=bool(step.get("pec")) and step["op"] == "write")

    def _run_iteration(self, steps: list[dict], it: int, out: dict) -> dict:
        phases, model, t0, t_dut, result = [], [], time.time(), None, "OK"
        for step in steps:
            addr = self.rig.resolve(step)
            self._pec_mode(step, addr, True)
            m = self._model_phases(step)
            model += m
            if self.link:
                self.seq += 1
                r = self.link.run(self.seq, step_command(step, addr))
                itr = r.iterations[0]
                t_dut = itr["t_dut_us"] if t_dut is None else t_dut
                result = itr["result"] if result == "OK" else result
                got = itr["phases"]
                for p, mp in zip(got, m):
                    p.pec = mp.pec
                phases += got
            else:
                phases += m
                result = "NAK" if any(p.ack == "NA" for p in m) and result == "OK" else result
            self._pec_mode(step, addr, False)
        if self.link and not phases_equal(phases, model):
            out["emit_status"] = "model_mismatch"
            out.setdefault("model_phases", []).append([p.to_json() for p in model])
        return {"iter": it, "t_host": t0, "t_dut_us": t_dut, "result": result,
                "phases": [p.to_json() for p in phases]}

    def _run_step_repeated(self, step: dict, rep: int, gap: int, out: dict) -> list[dict]:
        """Single-step case: the DUT repeats back to back (rep=), no host gaps."""
        addr = self.rig.resolve(step)
        self._pec_mode(step, addr, True)
        model_iters = [self._model_phases(step) for _ in range(rep)]
        iters = []
        if self.link:
            self.seq += 1
            r = self.link.run(self.seq, step_command(step, addr), rep=rep, gap_us=gap,
                              timeout_s=5.0 + rep * 0.05)
            for itr, m in zip(r.iterations, model_iters):
                for p, mp in zip(itr["phases"], m):
                    p.pec = mp.pec
                if not phases_equal(itr["phases"], m):
                    out["emit_status"] = "model_mismatch"
                iters.append({"iter": itr["iter"], "t_host": itr["t_host"],
                              "t_dut_us": itr["t_dut_us"], "result": itr["result"],
                              "phases": [p.to_json() for p in itr["phases"]]})
        else:
            t0 = time.time()
            for i, m in enumerate(model_iters):
                iters.append({"iter": i, "t_host": t0 + i * 1e-4, "t_dut_us": None,
                              "result": "NAK" if any(p.ack == "NA" for p in m) else "OK",
                              "phases": [p.to_json() for p in m]})
        self._pec_mode(step, addr, False)
        return iters


def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--rig", default=DEFAULT_RIG)
    ap.add_argument("--port", help="DUT serial port, USB serial number or device name "
                                   "(default: rig.toml [ports] dut, which may also be a name)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true", help="no hardware; phases from the model")
    ap.add_argument("--cases", help="comma-separated case IDs (default: all)")
    ap.add_argument("--list", action="store_true", help="list cases and exit")
    ap.add_argument("--transcript", help="write the raw line transcript here (hardware)")
    a = ap.parse_args(argv)

    rig = load_rig(a.rig)
    with open(a.pattern, encoding="utf-8") as f:
        pattern = json.load(f)
    cases = pattern["cases"]
    if a.cases:
        want = {c.strip() for c in a.cases.split(",")}
        cases = [c for c in cases if c["id"] in want]
        missing = want - {c["id"] for c in cases}
        if missing:
            print(f"unknown case(s): {sorted(missing)}", file=sys.stderr)
            return 1
    if a.list:
        for c in cases:
            print(f"{c['id']:6} {c['status']:12} {','.join(c['review_ids']) or '-':8} {c['description'][:70]}")
        return 0

    link, transcript = None, []
    if not a.dry_run:
        from dut_link import DutLink, open_serial
        port = a.port or rig.raw.get("ports", {}).get("dut", "")
        if not port:
            print("no DUT port: pass --port or set [ports] dut in rig.toml", file=sys.stderr)
            return 1
        from lbdevnames import resolve_port      # names are per-user, see lbdevnames
        try:
            port = resolve_port(port)
        except LookupError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        link = DutLink(open_serial(port), log=transcript.append)
        print(link.handshake())

    runner = Runner(rig, link)
    doc = {"format": EXPECTED_FORMAT, "version": EXPECTED_VERSION,
           "generated": _dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
           "mode": "dry_run" if a.dry_run else "hardware",
           "pattern": {"name": pattern["name"], "path": os.path.relpath(a.pattern, LB),
                       "sha256": sha256(a.pattern)},
           "rig": rig.raw, "dut": {"hello": link.hello if link else None,
                                   "port": (a.port or rig.raw.get("ports", {}).get("dut")) if link else None},
           "cases": []}
    rc = 0
    try:
        runner.configure_rig()
        for c in cases:
            res = runner.run_case(c)
            doc["cases"].append(res)
            nph = sum(len(i["phases"]) for i in res["iterations"])
            print(f"{res['id']:6} {res['emit_status']:15} {len(res['iterations']):4} iter "
                  f"{nph:5} phases  {res['speed_hz']} Hz"
                  + (f" (pred {res['speed_pred_hz']})" if res.get("speed_pred_hz") else ""))
            if res["emit_status"] != "ok":
                rc = 1
    except Exception as e:  # noqa: BLE001 - report which case broke, keep partial output
        from dut_link import DesyncError  # local: dry-run never imports serial
        failed = cases[len(doc["cases"])]["id"] if len(doc["cases"]) < len(cases) else "?"
        kind = "DESYNC" if isinstance(e, DesyncError) else "ERROR"
        print(f"{kind} in case {failed}: {e}", file=sys.stderr)
        doc["aborted"] = {"case": failed, "kind": kind.lower(), "error": str(e)}
        rc = 2 if kind == "DESYNC" else 1
    finally:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
        if a.transcript and transcript:
            with open(a.transcript, "w", encoding="utf-8") as f:
                f.write("\n".join(transcript) + "\n")
        print(f"wrote {a.out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
