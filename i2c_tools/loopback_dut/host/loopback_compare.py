#!/usr/bin/env python3
# [v0.2]
"""
loopback_dut/host/loopback_compare.py - P1-T4 comparison harness (pure logic,
no Qt, no sniffer imports).

Inputs : expected.json (loopback_run.py, ground truth from the DUT) and the
         capture CSV exported by the sniffer under test (capture CSV v1/v2,
         read by this module's own parser, not the sniffer's).
Output : per case a verdict and loopback_report.md.

Alignment: the capture is aligned to the flattened expected phases with a
global edit-distance alignment (match = same address, direction and bytes;
substitution = same address and direction, different bytes; gap = missing or
extra). Counts are never assumed equal: a missing transaction is the most
important failure mode. Captured rows before the first and after the last
aligned row are outside the run and ignored (counted in the report).

Verdicts (per capture path, from the case's path_status or status):
  pass            expect_pass, no failure
  fail            expect_pass with failures, OR xfail with a failure kind not
                  in xfail_symptoms  (unexplained -> suite fails)
  xfail           xfail, every failure kind is one of xfail_symptoms
  xpass           xfail but nothing failed -> the ledger is stale (suite fails)
  not_exercisable a `requires` capability is missing from the capture
                  (reported loudly; does not fail the suite)

CLI:
  python loopback_dut/host/loopback_compare.py --expected runs/expected.json \\
         --capture runs/ion_capture.csv --path ion --out runs/loopback_report_ion.md
Exit 0 when the ledger is exact (no fail, no xpass), else 1.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

PEC_OK, PEC_BAD = "✓ PEC", "✗ PEC"
SYMPTOMS = ("phase_missing", "phase_extra", "data_mismatch", "flag_mismatch",
            "address_nak_mismatch", "nak_on_normal_end_of_read", "pec_invalid",
            "decode_mismatch", "scl_mismatch", "scl_missing")


# --------------------------------------------------------------- capture
@dataclass
class Row:
    line: int
    time: str
    address: int
    dir: str
    data: list[int]
    nak: bool
    start: str          # "S" | "Sr" | ""
    stop: bool
    pec: str            # "", PEC_OK, PEC_BAD
    decode: str
    scl_hz: Optional[int]


def read_capture(path: str) -> list[Row]:
    rows: list[Row] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        missing = {"Addr", "Dir", "Data (hex)"} - set(rd.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: not a capture CSV (missing {sorted(missing)})")
        for n, r in enumerate(rd, start=2):
            try:
                addr = int((r.get("Addr") or "").strip(), 16)
            except ValueError:
                continue
            txt = (r.get("Data (hex)") or "").replace(",", " ").split()
            st = (r.get("Start") or "").strip()
            scl = (r.get("SCL (Hz)") or "").strip()
            rows.append(Row(line=n, time=(r.get("Time") or "").strip(), address=addr,
                            dir=(r.get("Dir") or "").strip().upper(),
                            data=[int(t, 16) for t in txt],
                            nak=(r.get("NAK") or "").strip().upper() == "NAK",
                            start="Sr" if st.lower() == "sr" else ("S" if st.lower() == "s" else ""),
                            stop=(r.get("Stop") or "").strip().upper() == "P",
                            pec=(r.get("PEC") or "").strip(),
                            decode=(r.get("Decode") or "").strip(),
                            scl_hz=int(scl) if scl.isdigit() else None))
    return rows


# -------------------------------------------------------------- expected
@dataclass
class Exp:
    case: str
    iter: int
    idx: int            # phase index within the iteration
    ph: dict            # expected.json phase (data possibly truncated per path)
    full_len: int       # untruncated byte count


def flatten(expected: dict, path: str) -> list[Exp]:
    out = []
    for c in expected["cases"]:
        trunc = c.get("expect", {}).get("truncate_to", {}).get(path)
        for it in c["iterations"]:
            for i, p in enumerate(it["phases"]):
                q = dict(p)
                if trunc is not None and len(q["data"]) > trunc:
                    q["data"] = q["data"][:trunc]
                out.append(Exp(c["id"], it["iter"], i, q, len(p["data"])))
    return out


# ------------------------------------------------------------- alignment
def _key(e: Exp):
    return (e.ph["address"], e.ph["dir"], tuple(e.ph["data"]))


def align(E: list[Exp], C: list[Row]) -> list[tuple[Optional[int], Optional[int]]]:
    """Global alignment. Returns (e_index | None, c_index | None) pairs."""
    n, m = len(E), len(C)
    INF = 10 ** 9
    ek = [_key(e) for e in E]
    ck = [(r.address, r.dir, tuple(r.data)) for r in C]
    # DP over rows; keep full back-pointer table (sizes are a few hundred)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    B = [[0] * (m + 1) for _ in range(n + 1)]     # 0 diag, 1 up (miss), 2 left (extra)
    for i in range(1, n + 1):
        D[i][0], B[i][0] = i, 1
    for j in range(1, m + 1):
        D[0][j], B[0][j] = 0, 2                    # leading capture rows are free
    for i in range(1, n + 1):
        Di, Dp, Bi = D[i], D[i - 1], B[i]
        e = ek[i - 1]
        for j in range(1, m + 1):
            c = ck[j - 1]
            if c == e:
                sub = 0
            elif c[0] == e[0] and c[1] == e[1]:
                sub = 1
            else:
                sub = INF
            best, b = Dp[j - 1] + sub, 0
            if Dp[j] + 1 < best:
                best, b = Dp[j] + 1, 1
            extra = 0 if i == n else 1                 # trailing capture rows are free
            if Di[j - 1] + extra < best:
                best, b = Di[j - 1] + extra, 2
            Di[j], Bi[j] = best, b
    pairs = []
    i, j = n, m
    while i > 0 or j > 0:
        b = B[i][j]
        if i > 0 and j > 0 and b == 0:
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif i > 0 and (j == 0 or b == 1):
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    pairs.reverse()
    return pairs


# ---------------------------------------------------------------- verdict
@dataclass
class Failure:
    kind: str
    detail: str


@dataclass
class CaseResult:
    id: str
    review_ids: list[str]
    status: str
    verdict: str = ""
    failures: list[Failure] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    phases: int = 0
    matched: int = 0


def _hex(b) -> str:
    return " ".join(f"{x:02X}" for x in b) or "(none)"


def _data_diff(exp: list[int], got: list[int]) -> str:
    k = next((i for i, (a, b) in enumerate(zip(exp, got)) if a != b), min(len(exp), len(got)))
    return (f"expected {len(exp)} B [{_hex(exp[:12])}{' …' if len(exp) > 12 else ''}], "
            f"captured {len(got)} B [{_hex(got[:12])}{' …' if len(got) > 12 else ''}], "
            f"first difference at byte {k}")


LEDGER_KEYS = ("review_ids", "status", "path_status", "xfail_reason", "xfail_symptoms",
               "path_xfail_symptoms", "requires", "expect")


def apply_ledger(expected: dict, pattern: dict) -> dict:
    """Re-judge an archived run against a newer ledger: copy the ledger fields
    of each case from `pattern` (by case id) over the copies frozen into
    expected.json. Bus data (iterations) is untouched."""
    pc = {c["id"]: c for c in pattern["cases"]}
    out = dict(expected)
    out["cases"] = []
    for c in expected["cases"]:
        c = dict(c)
        for k in LEDGER_KEYS:
            c.pop(k, None)
            if k in pc.get(c["id"], {}):
                c[k] = pc[c["id"]][k]
        out["cases"].append(c)
    out["ledger_from"] = pattern.get("name")
    return out


def compare(expected: dict, rows: list[Row], path: str, scl_tol_pct: Optional[float] = None,
            ignore_ledger: bool = False) -> dict:
    if path not in ("ion", "ad2"):
        raise ValueError("path must be 'ion' or 'ad2'")
    tol = scl_tol_pct if scl_tol_pct is not None else \
        float(expected.get("rig", {}).get("compare", {}).get("scl_tolerance_pct", 5))
    E, C = flatten(expected, path), rows
    pairs = align(E, C)

    cases = {c["id"]: c for c in expected["cases"]}
    res = {cid: CaseResult(cid, c.get("review_ids", []),
                           "expect_pass" if ignore_ledger else
                           c.get("path_status", {}).get(path, c["status"]))
           for cid, c in cases.items()}
    capture_has_pec = any(r.pec for r in C)
    capture_has_decode = any(r.decode for r in C)

    # span of the run inside the capture
    cj = [j for e, j in pairs if e is not None and j is not None]
    lo, hi = (min(cj), max(cj)) if cj else (0, -1)
    outside = sum(1 for e, j in pairs if e is None and j is not None and not (lo <= j <= hi))

    last_case = E[0].case if E else None
    matched_rows: dict[tuple, Row] = {}
    for k, (ei, cj_) in enumerate(pairs):
        if ei is not None:
            last_case = E[ei].case
        if ei is None:
            if lo <= cj_ <= hi:
                # attribute an extra row to the case of the next expected phase
                nxt = next((E[e].case for e, _ in pairs[k:] if e is not None), last_case)
                r = C[cj_]
                res[nxt].failures.append(Failure(
                    "phase_extra", f"capture line {r.line}: {r.dir} 0x{r.address:02X} [{_hex(r.data)}] not emitted"))
            continue
        e = E[ei]
        cr = res[e.case]
        cr.phases += 1
        p = e.ph
        if cj_ is None:
            cr.failures.append(Failure("phase_missing",
                f"iter {e.iter} phase {e.idx}: {p['start']} {p['dir']} 0x{p['address']:02X} "
                f"[{_hex(p['data'][:12])}] not captured"))
            continue
        r = C[cj_]
        cr.matched += 1
        matched_rows[(e.case, e.iter, e.idx)] = r
        where = f"iter {e.iter} phase {e.idx} (capture line {r.line})"
        if r.data != p["data"]:
            cr.failures.append(Failure("data_mismatch", f"{where}: {_data_diff(p['data'], r.data)}"))
        want_start = p["start"]
        if r.start and r.start != want_start:
            cr.failures.append(Failure("flag_mismatch", f"{where}: start {r.start}, expected {want_start}"))
        if r.stop != p["stop"]:
            cr.failures.append(Failure("flag_mismatch",
                f"{where}: stop {'P' if r.stop else '-'}, expected {'P' if p['stop'] else '-'}"))
        exp_expect = cases[e.case].get("expect", {})
        if p["ack"] == "NA":
            if not r.nak:
                cr.failures.append(Failure("address_nak_mismatch", f"{where}: address NAK not shown"))
        elif r.nak:
            if p["dir"] == "R" and p["ack"] == "A":
                if exp_expect.get("end_of_read_nak", "lenient") == "strict":
                    cr.failures.append(Failure("nak_on_normal_end_of_read",
                        f"{where}: normal end-of-read master NAK exported as NAK"))
            else:
                cr.failures.append(Failure("address_nak_mismatch", f"{where}: NAK shown on an ACKed write"))
        if p.get("pec") and exp_expect.get("pec") == "valid" and capture_has_pec:
            if r.pec != PEC_OK:
                cr.failures.append(Failure("pec_invalid",
                    f"{where}: PEC column {r.pec or '(empty)'}, bus PEC 0x{p['data'][-1]:02X} is correct"))

    # case-level checks
    for cid, c in cases.items():
        cr = res[cid]
        ex = c.get("expect", {})
        req = set(c.get("requires", []))
        if "pec_validation_on" in req and not capture_has_pec:
            cr.notes.append("requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC')")
            cr.verdict = "not_exercisable"
        if "loopback_decoder" in req and not capture_has_decode:
            cr.notes.append("requires loopback_decoder: capture Decode column is empty (load i2c_decoders/loopback_dut_decoder.json)")
            cr.verdict = "not_exercisable"
        if "decode" in ex and capture_has_decode:
            want = ex["decode"]
            for it in c["iterations"]:
                r = matched_rows.get((cid, it["iter"], want["phase"]))
                if r is not None and want["contains"] not in r.decode:
                    cr.failures.append(Failure("decode_mismatch",
                        f"iter {it['iter']} phase {want['phase']} (line {r.line}): Decode "
                        f"{r.decode!r}, expected to contain {want['contains']!r}"))
        if ex.get("scl_check"):
            hz = c["speed_hz"]
            vals = [(k, r) for k, r in matched_rows.items() if k[0] == cid and r.scl_hz]
            if path == "ion" and not vals:
                cr.failures.append(Failure("scl_missing", "no SCL (Hz) values on this case's rows (probe fw >= 1.3?)"))
            for k, r in vals:
                if abs(r.scl_hz - hz) * 100.0 > tol * hz:
                    cr.failures.append(Failure("scl_mismatch",
                        f"iter {k[1]} phase {k[2]} (line {r.line}): SCL {r.scl_hz} Hz vs set {hz} Hz (tol {tol:g} %)"))
        if c.get("emit_status") == "model_mismatch":
            cr.notes.append("DUT phases differed from the host model (see expected.json model_phases)")

        kinds = {f.kind for f in cr.failures}
        if cr.verdict == "not_exercisable":
            pass
        elif cr.status == "not_exercisable":
            cr.verdict = "not_exercisable"
        elif cr.status == "expect_pass":
            cr.verdict = "fail" if kinds else "pass"
        else:  # xfail: a per-path override narrows what is excused on this path
            allowed = set(c.get("path_xfail_symptoms", {}).get(path, c.get("xfail_symptoms", [])))
            cr.verdict = ("xpass" if not kinds else
                          "xfail" if kinds <= allowed else "fail")

    verdicts = [r.verdict for r in res.values()]
    return {"path": path, "cases": res, "outside_rows": outside, "captured_rows": len(C),
            "expected_phases": len(E), "ledger_exact": not any(v in ("fail", "xpass") for v in verdicts),
            "counts": {v: verdicts.count(v) for v in ("pass", "fail", "xfail", "xpass", "not_exercisable")},
            "capture_has_pec": capture_has_pec, "capture_has_decode": capture_has_decode}


# ----------------------------------------------------------------- report
def report_md(result: dict, expected: dict, expected_path: str, capture_path: str) -> str:
    cnt = result["counts"]
    L = [f"# Loopback report ({result['path']} capture path)", "",
         f"- **Generated:** {_dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
         f"- **Expected:** `{expected_path}` (mode {expected['mode']}, pattern {expected['pattern']['name']} "
         f"sha256 {expected['pattern']['sha256'][:12]}…, generated {expected['generated']})",
         f"- **Capture:** `{capture_path}`: {result['captured_rows']} rows, "
         f"{result['outside_rows']} outside the run; PEC results {'present' if result['capture_has_pec'] else 'ABSENT'}; "
         f"Decode {'present' if result['capture_has_decode'] else 'ABSENT'}",
         f"- **Expected phases:** {result['expected_phases']}"
         + (f" · ledger re-applied from pattern `{expected['ledger_from']}`" if expected.get("ledger_from") else ""),
         f"- **Verdicts:** pass {cnt['pass']} · fail {cnt['fail']} · xfail {cnt['xfail']} · "
         f"xpass {cnt['xpass']} · not exercisable {cnt['not_exercisable']}",
         f"- **Ledger exact:** {'YES' if result['ledger_exact'] else 'NO (unexplained failure or unexpected pass)'}",
         "", "| Case | Review IDs | Status | Verdict | Matched | Detail |", "|---|---|---|---|---|---|"]
    for cid, r in result["cases"].items():
        kinds = sorted({f.kind for f in r.failures})
        detail = ", ".join(kinds) or ("; ".join(r.notes) if r.notes else "")
        L.append(f"| {cid} | {', '.join(r.review_ids) or '-'} | {r.status} | **{r.verdict}** | "
                 f"{r.matched}/{r.phases} | {detail} |")
    for cid, r in result["cases"].items():
        if r.failures or r.notes:
            L += ["", f"## {cid}: {r.verdict}"]
            L += [f"- note: {n}" for n in r.notes]
            for f in r.failures[:25]:
                L.append(f"- `{f.kind}`: {f.detail}")
            if len(r.failures) > 25:
                L.append(f"- … {len(r.failures) - 25} more")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare a sniffer capture against expected.json")
    ap.add_argument("--expected", required=True)
    ap.add_argument("--capture", required=True)
    ap.add_argument("--path", required=True, choices=["ion", "ad2"])
    ap.add_argument("--out", help="write loopback_report.md here")
    ap.add_argument("--ignore-ledger", action="store_true",
                    help="treat every case as expect_pass (harness self-test)")
    ap.add_argument("--pattern", help="re-judge with the ledger from this pattern file "
                                      "(default: the ledger frozen in expected.json)")
    a = ap.parse_args(argv)
    with open(a.expected, encoding="utf-8") as f:
        expected = json.load(f)
    if a.pattern:
        with open(a.pattern, encoding="utf-8") as f:
            expected = apply_ledger(expected, json.load(f))
    result = compare(expected, read_capture(a.capture), a.path, ignore_ledger=a.ignore_ledger)
    md = report_md(result, expected, a.expected, a.capture)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"wrote {a.out}")
    c = result["counts"]
    print(f"{a.path}: pass {c['pass']} fail {c['fail']} xfail {c['xfail']} xpass {c['xpass']} "
          f"not_exercisable {c['not_exercisable']}  ledger {'EXACT' if result['ledger_exact'] else 'NOT EXACT'}")
    return 0 if result["ledger_exact"] else 1


if __name__ == "__main__":
    sys.exit(main())
