#!/usr/bin/env python3
# [v0.4]
"""
loopback_dut/tests/test_pattern_schema.py - tier T1 (no hardware).

Pins P1-T1: the loopback pattern schema is itself valid, loopback_v1.json
validates, every case carries review_ids, the xfail ledger holds B8/B9/B10/B13,
declared phase counts match the steps, and each conditional rule in the schema
really rejects the document it targets (review lesson B1: an `if` without
`required` passes vacuously). Also cross-checks config/rig.toml against the
firmware defaults in firmware/App/Inc/loopback_config.h.

Isolated: imports nothing from the sniffer tools (core/, ui/).
Run:  python loopback_dut/tests/test_pattern_schema.py
"""
import copy
import json
import os
import re
import sys
import tomllib

import jsonschema

HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.dirname(HERE)
SCHEMA = os.path.join(LB, "schema", "loopback_pattern.schema.json")
PATTERN = os.path.join(LB, "patterns", "loopback_v1.json")
RIG = os.path.join(LB, "config", "rig.toml")
FW_CFG = os.path.join(LB, "firmware", "App", "Inc", "loopback_config.h")

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


PHASES = {"write": 1, "read": 1, "write_read": 2, "write_stop_read": 2}


def load():
    with open(SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    with open(PATTERN, encoding="utf-8") as f:
        pattern = json.load(f)
    return schema, pattern


def is_valid(validator, doc):
    return not list(validator.iter_errors(doc))


def test_schema_and_pattern(schema, pattern, v):
    print("schema + golden pattern")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        ok = True
    except jsonschema.SchemaError as e:
        ok = False
        print("   ", e.message)
    check(ok, "schema is a valid draft 2020-12 schema")
    errs = list(v.iter_errors(pattern))
    for e in errs[:5]:
        print("    ", list(e.absolute_path), e.message)
    check(not errs, "loopback_v1.json validates against the schema")

    cases = pattern["cases"]
    ids = [c["id"] for c in cases]
    check(sorted(ids) == [f"LB-{i:02d}" for i in range(1, 16)] and len(set(ids)) == 15,
          "cases LB-01..LB-15 present, each once")
    check(ids[-1] == "LB-13", "LB-13 (400 kHz, B31 knock-on) runs last")
    check(all("review_ids" in c for c in cases), "every case carries review_ids")

    for c in cases:
        n = sum(PHASES[s["op"]] for s in c["steps"])
        check(c["expect"]["phases_per_iteration"] == n,
              f"{c['id']}: phases_per_iteration {c['expect']['phases_per_iteration']} == steps ({n})")


def test_xfail_ledger(pattern):
    print("xfail ledger")
    ledger = {}
    for c in pattern["cases"]:
        statuses = [c["status"]] + list(c.get("path_status", {}).values())
        if "xfail" in statuses:
            for rid in c["review_ids"]:
                ledger.setdefault(rid, []).append(c["id"])
            check(len(c.get("xfail_reason", "")) >= 10 and
                  any(r in c["xfail_reason"] for r in c["review_ids"]),
                  f"{c['id']}: xfail_reason names its review ID")
    for rid, case in (("B8", "LB-04"), ("B9", "LB-07"), ("B10", "LB-09"), ("B13", "LB-06"),
                      ("B31", "LB-13"), ("B32", "LB-01")):
        check(case in ledger.get(rid, []), f"ledger: {rid} armed by {case}")
    check("B30" not in ledger, "ledger: B30 closed (fixed in C031 fw 1.6), armed by no case")

    def eff(c, path):
        status = c.get("path_status", {}).get(path, c["status"])
        if status != "xfail":
            return None
        return set(c.get("path_xfail_symptoms", {}).get(path, c.get("xfail_symptoms", [])))
    C = {c["id"]: c for c in pattern["cases"]}
    want = {("LB-04", "ion"): {"decode_mismatch"}, ("LB-04", "ad2"): {"decode_mismatch"},
            ("LB-06", "ion"): {"nak_on_normal_end_of_read"},
            ("LB-06", "ad2"): {"nak_on_normal_end_of_read", "phase_missing", "phase_extra"},
            ("LB-07", "ion"): {"pec_invalid"},
            ("LB-07", "ad2"): {"pec_invalid", "phase_missing", "phase_extra"},
            ("LB-09", "ion"): None, ("LB-09", "ad2"): {"data_mismatch", "phase_missing", "phase_extra"},
            ("LB-01", "ion"): None, ("LB-01", "ad2"): {"phase_missing", "phase_extra"},
            ("LB-15", "ion"): None, ("LB-14", "ion"): None,
            ("LB-12", "ion"): None, ("LB-12", "ad2"): {"phase_missing", "phase_extra"}}
    for (cid, path), w in want.items():
        check(eff(C[cid], path) == w, f"{cid} on {path}: excused symptoms {eff(C[cid], path)}")
    for c in pattern["cases"]:
        for path, syms in c.get("path_xfail_symptoms", {}).items():
            check(set(syms) <= set(c.get("xfail_symptoms", [])),
                  f"{c['id']}: path_xfail_symptoms.{path} is a subset of xfail_symptoms")
    lb09 = next(c for c in pattern["cases"] if c["id"] == "LB-09")
    check(lb09.get("path_status") == {"ad2": "xfail", "ion": "expect_pass"},
          "B10 is AD2-only: LB-09 xfail on ad2, expect_pass on ion")


def test_b1_conditionals(pattern, v):
    """Each mutation must be REJECTED; each allowed variant ACCEPTED."""
    print("B1 lesson: conditional rules are not vacuous")
    # mutate a case that carries no ledger fields of its own
    base = next(c for c in pattern["cases"] if c["status"] == "expect_pass"
                and "path_status" not in c and not c["review_ids"])

    def doc_with(case):
        d = copy.deepcopy(pattern)
        d["cases"] = [case]
        return d

    def mutated(fn):
        c = copy.deepcopy(base)
        fn(c)
        return doc_with(c)

    rejects = {
        "xfail without xfail_reason":
            lambda c: c.update(status="xfail", review_ids=["B8"], xfail_symptoms=["decode_mismatch"]),
        "xfail without xfail_symptoms":
            lambda c: c.update(status="xfail", review_ids=["B8"], xfail_reason="observed: decode empty"),
        "unknown symptom kind":
            lambda c: c.update(status="xfail", review_ids=["B8"], xfail_reason="observed: decode empty",
                               xfail_symptoms=["looks_wrong"]),
        "path_status.ad2 xfail without reason":
            lambda c: c.update(path_status={"ad2": "xfail"}, xfail_symptoms=["data_mismatch"]),
        "path_status.ad2 xfail without symptoms":
            lambda c: c.update(path_status={"ad2": "xfail"}, xfail_reason="observed: truncated"),
        "path_status.ion xfail without reason":
            lambda c: c.update(path_status={"ion": "xfail"}),
        "xfail with no review_ids":
            lambda c: c.update(status="xfail", xfail_reason="some observed failure",
                               xfail_symptoms=["data_mismatch"]),
        "not_exercisable without reason":
            lambda c: c.update(status="not_exercisable"),
        "missing status":
            lambda c: c.pop("status"),
        "write step without data":
            lambda c: c.update(steps=[{"target": "R1", "op": "write"}]),
        "write_read without read_len":
            lambda c: c.update(steps=[{"target": "R1", "op": "write_read", "data": [1]}]),
        "read step with data":
            lambda c: c.update(steps=[{"target": "R1", "op": "read", "read_len": 2, "data": [1]}]),
        "write step with read_len":
            lambda c: c.update(steps=[{"target": "R1", "op": "write", "data": [1], "read_len": 2}]),
        "step with both target and address":
            lambda c: c.update(steps=[{"target": "R1", "address": 0x6B, "op": "read", "read_len": 1}]),
        "step with neither target nor address":
            lambda c: c.update(steps=[{"op": "read", "read_len": 1}]),
        "PEC read with read_len 1 (no room for data + PEC)":
            lambda c: c.update(steps=[{"target": "R1", "op": "read", "read_len": 1, "pec": True}]),
        "unknown target":
            lambda c: c.update(steps=[{"target": "R3", "op": "read", "read_len": 1}]),
        "speed above 400 kHz":
            lambda c: c.update(speed_hz=1000000),
        "unknown case key":
            lambda c: c.update(bogus=1),
    }
    for name, fn in rejects.items():
        check(not is_valid(v, mutated(fn)), f"rejects: {name}")

    accepts = {
        "literal address in place of target":
            lambda c: c.update(steps=[{"address": 0x2A, "op": "read", "read_len": 2}]),
        "path_status expect_pass without reason":
            lambda c: c.update(path_status={"ion": "expect_pass"}),
        "xfail with reason, symptoms and review id":
            lambda c: c.update(status="xfail", review_ids=["B8"], xfail_reason="observed: decode empty",
                               xfail_symptoms=["decode_mismatch"]),
        "PEC write (host appends PEC byte)":
            lambda c: c.update(steps=[{"target": "R1", "op": "write", "data": [1, 2], "pec": True}]),
    }
    for name, fn in accepts.items():
        check(is_valid(v, mutated(fn)), f"accepts: {name}")


def test_rig_config():
    print("rig.toml")
    with open(RIG, "rb") as f:
        rig = tomllib.load(f)
    resp = rig["responder"]
    check([r["name"] for r in resp] == ["R1", "R2"], "responders R1, R2")
    addrs = [r["address"] for r in resp]
    check(len(set(addrs)) == 2, "responder addresses unique")
    check(all(0 <= a <= 0x7F for a in addrs + rig["nak"]["addresses"]), "7-bit addresses")
    check(not set(addrs) & set(rig["nak"]["addresses"]), "NAK target is not a responder address")
    check(rig["nak"]["addresses"][0] == rig["master"]["own_address"] == 0x08,
          "owner plan: 0x08 is the master's own address and the NAK target")

    with open(FW_CFG, encoding="utf-8") as f:
        hdr = f.read()

    def fw(name):
        m = re.search(rf"#define\s+{name}\s+(0x[0-9A-Fa-f]+|\d+)U", hdr)
        return int(m.group(1), 0) if m else None

    check(fw("LB_R1_ADDR") == resp[0]["address"] and fw("LB_R2_ADDR") == resp[1]["address"],
          "rig.toml addresses == firmware power-up defaults")
    check(fw("LB_R1_WORD_BASE") == resp[0]["word_base"] and
          fw("LB_R2_WORD_BASE") == resp[1]["word_base"],
          "rig.toml word_base == firmware LB_R*_WORD_BASE (host model depends on it)")
    check(fw("LB_DEFAULT_SCL_HZ") == rig["rig"]["default_scl_hz"], "default SCL matches firmware")


def main():
    schema, pattern = load()
    v = jsonschema.Draft202012Validator(schema)
    test_schema_and_pattern(schema, pattern, v)
    test_xfail_ledger(pattern)
    test_b1_conditionals(pattern, v)
    test_rig_config()
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
