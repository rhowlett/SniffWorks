#!/usr/bin/env python3
# [v0.3]
"""
loopback_dut/tests/test_loopback_harness.py - P1-T5, tier T1 (no hardware).

Keeps the instrument honest: a harness bug must never look like a clean bill
of health for the tool.
  1. A perfect synthetic capture of the dry-run expected.json -> zero failures
     (ledger ignored).
  2. Five deliberate mutations are each caught, in the right case only:
     dropped transaction, truncated payload (B10-like), flipped PEC column,
     reordered pair, extra spurious transaction.
  3. Ledger semantics: the perfect capture WITH the ledger turns every xfail
     into xpass (stale-ledger detection); injecting exactly the known symptoms
     (B8, B9, B10 on ad2, B13) gives xfail and an exact ledger; the B10
     truncation on the ion path is an unexplained failure.
  4. Requirement gating: no PEC results -> LB-07/LB-08 not_exercisable.
Isolated: imports only loopback_dut/host.
"""
import copy
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LB, "host"))

import loopback_run  # noqa: E402
from loopback_compare import compare, read_capture, report_md  # noqa: E402
from lbsynth import rows_for, write_csv  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def dry_run_expected() -> dict:
    import json
    out = os.path.join(tempfile.mkdtemp(), "expected.json")
    rc = loopback_run.main(["--dry-run", "--out", out])
    assert rc == 0
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def run(expected, rows, path="ion", ignore_ledger=True):
    tmp = os.path.join(tempfile.mkdtemp(), "cap.csv")
    write_csv(tmp, rows)
    return compare(expected, read_capture(tmp), path, ignore_ledger=ignore_ledger)


def verdicts(res):
    return {cid: r.verdict for cid, r in res["cases"].items()}


def kinds(res, cid):
    return {f.kind for f in res["cases"][cid].failures}


def row_index(rows, case_rows, cid, k=0):
    return case_rows[cid][k]


def index_rows(expected, rows):
    """case id -> list of row indices (rows_for emits in case order)."""
    m, i = {}, 0
    for c in expected["cases"]:
        n = sum(len(it["phases"]) for it in c["iterations"])
        m[c["id"]] = list(range(i, i + n))
        i += n
    assert i == len(rows)
    return m


def main():
    exp = dry_run_expected()
    perfect = rows_for(exp, "ion")
    idx = index_rows(exp, perfect)

    print("1. perfect capture")
    res = run(exp, perfect)
    v = verdicts(res)
    check(all(x == "pass" for x in v.values()), f"perfect ion capture: all 15 pass ({res['counts']})")
    check(res["ledger_exact"] and res["outside_rows"] == 0, "no failures, nothing outside the run")
    res_ad2 = run(exp, rows_for(exp, "ad2"), path="ad2")
    check(all(x == "pass" for x in verdicts(res_ad2).values()), "perfect ad2 capture: all pass")

    print("2. mutations are detected, in the right case")
    # 2a dropped transaction (LB-03's only phase)
    rows = copy.deepcopy(perfect); del rows[idx["LB-03"][0]]
    r = run(exp, rows)
    check("phase_missing" in kinds(r, "LB-03") and r["cases"]["LB-03"].verdict == "fail",
          "dropped transaction -> LB-03 phase_missing")
    check(sum(1 for x in verdicts(r).values() if x != "pass") == 1, "  ...and no other case disturbed")
    # 2b truncated payload (LB-09 36-byte read cut to 16, B10-like)
    rows = copy.deepcopy(perfect); j = idx["LB-09"][2]
    b = rows[j][5].split()[:16]; rows[j][5] = " ".join(b); rows[j][4] = "16"
    r = run(exp, rows)
    check("data_mismatch" in kinds(r, "LB-09"), "truncated payload -> LB-09 data_mismatch")
    det = [f.detail for f in r["cases"]["LB-09"].failures if f.kind == "data_mismatch"]
    check(det and "expected 36 B" in det[0] and "captured 16 B" in det[0], "  ...byte-level diff names the lengths")
    # 2c flipped PEC column (LB-07 read row)
    rows = copy.deepcopy(perfect); j = idx["LB-07"][1]
    rows[j][12] = "✗ PEC"
    r = run(exp, rows)
    check(kinds(r, "LB-07") == {"pec_invalid"}, "flipped PEC -> LB-07 pec_invalid")
    # 2d reordered pair (LB-01 write/read swapped)
    rows = copy.deepcopy(perfect); a, bb = idx["LB-01"][0], idx["LB-01"][1]
    rows[a], rows[bb] = rows[bb], rows[a]
    r = run(exp, rows)
    check(r["cases"]["LB-01"].verdict == "fail", f"reordered pair -> LB-01 fails ({sorted(kinds(r, 'LB-01'))})")
    # 2e extra spurious transaction inside LB-05
    rows = copy.deepcopy(perfect); j = idx["LB-05"][0]
    rows.insert(j, list(rows[j])); rows[j][2] = "0x3C"; rows[j][9] = ""; rows[j][5] = "99"
    r = run(exp, rows)
    check("phase_extra" in kinds(r, "LB-05") or "phase_extra" in kinds(r, "LB-04"),
          "spurious transaction -> phase_extra next to LB-05")
    check(sum(1 for x in verdicts(r).values() if x != "pass") == 1, "  ...attributed to one case only")
    # 2f burst drop (LB-12: one of 400 phases missing)
    rows = copy.deepcopy(perfect); del rows[idx["LB-12"][123]]
    r = run(exp, rows)
    check(kinds(r, "LB-12") == {"phase_missing"}, "1 of 400 burst phases dropped -> LB-12 phase_missing")

    print("3. ledger semantics")
    r = run(exp, perfect, ignore_ledger=False)
    v = verdicts(r)
    check(v["LB-04"] == v["LB-06"] == v["LB-07"] == "xpass" and not r["ledger_exact"],
          "perfect capture with ledger: xfail cases become xpass, ledger NOT exact")
    check(v["LB-09"] == "pass", "LB-09 is expect_pass on the ion path")
    ION_BUGS, AD2_BUGS = {"B8", "B9", "B13", "B31"}, {"B8", "B9", "B13", "B32"}   # B30 fixed fw 1.6
    buggy = rows_for(exp, "ion", ION_BUGS)
    r = run(exp, buggy, ignore_ledger=False)
    v = verdicts(r)
    check(all(v[c] == "xfail" for c in ("LB-04", "LB-06", "LB-07", "LB-13")) and v["LB-12"] == "pass",
          f"ion + B8/B9/B13/B31 -> LB-04/06/07/13 xfail, LB-12 pass ({r['counts']})")
    check(r["ledger_exact"], "ion ledger exact with exactly the known symptoms")
    check(v["LB-14"] == "pass", "LB-13 runs last, so its B31 garbage cannot reach another case")
    r = run(exp, rows_for(exp, "ion", ION_BUGS | {"B30"}), ignore_ledger=False)
    check(r["cases"]["LB-12"].verdict == "fail" and not r["ledger_exact"],
          "B30 is closed: a bit slip on LB-12 (ion) is now a regression (fail)")
    buggy_ad2 = rows_for(exp, "ad2", AD2_BUGS)
    r = run(exp, buggy_ad2, path="ad2", ignore_ledger=False)
    v = verdicts(r)
    check(all(v[c] == "xfail" for c in ("LB-01", "LB-09", "LB-12", "LB-13", "LB-14", "LB-15"))
          and v["LB-02"] == v["LB-03"] == v["LB-05"] == "pass" and r["ledger_exact"],
          f"ad2 + B32 -> Sr-terminated cases xfail, stop-terminated pass, ledger exact ({r['counts']})")
    r = run(exp, rows_for(exp, "ad2", AD2_BUGS | {"B10"}), path="ad2", ignore_ledger=False)
    check(verdicts(r)["LB-09"] == "xfail" and r["ledger_exact"],
          "ad2 + B32 + B10 truncation -> still exact (data_mismatch excused on ad2 only)")
    # per-path narrowing: the AD2-only B32 symptoms must NOT excuse the ion path
    rows = rows_for(exp, "ion", ION_BUGS)
    j = idx["LB-06"][0]
    rows[j][2], rows[j][5] = "0x00", "00"
    r = run(exp, rows, ignore_ledger=False)
    check(verdicts(r)["LB-06"] == "fail", "B32-like symptom on the ion path is NOT excused (fail)")
    trunc_ion = rows_for(exp, "ion", ION_BUGS)
    j = idx["LB-09"][2]; trunc_ion[j][5] = " ".join(trunc_ion[j][5].split()[:16])
    r = run(exp, trunc_ion, ignore_ledger=False)
    check(verdicts(r)["LB-09"] == "fail" and not r["ledger_exact"],
          "the same truncation on the ion path is an unexplained failure")
    # an xfail case that fails in an UNLISTED way must be fail, not xfail
    rows = rows_for(exp, "ion", ION_BUGS)
    del rows[idx["LB-06"][1]]
    r = run(exp, rows, ignore_ledger=False)
    check(verdicts(r)["LB-06"] == "fail", "xfail case with an unlisted failure kind -> fail")

    print("4. requirement gating + report")
    rows = copy.deepcopy(perfect)
    for x in rows:
        x[12] = ""
    r = run(exp, rows, ignore_ledger=False)
    v = verdicts(r)
    check(v["LB-07"] == "not_exercisable" and v["LB-08"] == "not_exercisable",
          "no PEC results in the capture -> LB-07/LB-08 not_exercisable")
    md = report_md(run(exp, buggy, ignore_ledger=False), exp, "expected.json", "cap.csv")
    check("| LB-06 | B13, B32 | xfail | **xfail** |" in md and "Ledger exact:** YES" in md,
          "report table carries case, review ID, status, verdict")

    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
