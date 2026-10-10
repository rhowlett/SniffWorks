#!/usr/bin/env python3
# [v0.2]
"""
loopback_dut/tests/test_loopback_capture.py - P1-T4, tier T2 (needs the rig).

Compares real sniffer captures against a HARDWARE expected.json:
  loopback_dut/runs/expected.json      loopback_run.py --port ... (mode hardware)
  loopback_dut/runs/ion_capture.csv    exported by sniffer_ion (C031, fw >= 1.3)
  loopback_dut/runs/ad2_capture.csv    exported by sniffer_ad2
or, with a directory argument, the same three files in that directory (e.g. an
archived run: runs/2026-10-02_run2). Verdicts use the CURRENT ledger in
patterns/loopback_v1.json.
and writes loopback_dut/runs/loopback_report_<path>.md for each path present.

Exit codes: 0 = every present path has an exact ledger; 1 = a ledger is not
exact; 77 = SKIPPED (rig artefacts absent). A skip is NOT a pass: it prints a
banner and returns 77 so a runner can report it (master plan §5.1).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LB, "host"))
from loopback_compare import apply_ledger, compare, read_capture, report_md  # noqa: E402

RUNS = os.path.join(LB, "runs")
SKIP = 77


def main():
    runs = sys.argv[1] if len(sys.argv) > 1 else RUNS
    exp_path = os.path.join(runs, "expected.json")
    caps = {p: os.path.join(runs, f"{p}_capture.csv") for p in ("ion", "ad2")}
    present = {p: c for p, c in caps.items() if os.path.isfile(c)}
    if not os.path.isfile(exp_path) or not present:
        print("=" * 72)
        print("SKIPPED (tier T2): no rig artefacts in loopback_dut/runs/ - this is NOT a pass.")
        print("  need expected.json + ion_capture.csv and/or ad2_capture.csv (setup_guide §9-10)")
        print("=" * 72)
        return SKIP
    with open(exp_path, encoding="utf-8") as f:
        expected = json.load(f)
    if expected.get("mode") != "hardware":
        print("WARNING: expected.json is a DRY RUN; compare a hardware run for evidence")
    # judge with the CURRENT ledger (the pattern may have been updated since the run)
    with open(os.path.join(LB, "patterns", "loopback_v1.json"), encoding="utf-8") as f:
        expected = apply_ledger(expected, json.load(f))
    if expected.get("aborted"):
        print(f"WARNING: the DUT run aborted: {expected['aborted']}")
    ok = True
    for path, cap in present.items():
        res = compare(expected, read_capture(cap), path)
        out = os.path.join(runs, f"loopback_report_{path}.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(report_md(res, expected, exp_path, cap))
        c = res["counts"]
        print(f"{path}: pass {c['pass']} fail {c['fail']} xfail {c['xfail']} xpass {c['xpass']} "
              f"not_exercisable {c['not_exercisable']}  ledger "
              f"{'EXACT' if res['ledger_exact'] else 'NOT EXACT'}  -> {out}")
        ok &= res["ledger_exact"]
    for p in set(caps) - set(present):
        print(f"SKIPPED path {p}: {caps[p]} absent - NOT a pass")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
