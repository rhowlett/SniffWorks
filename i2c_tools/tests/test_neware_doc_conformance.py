#!/usr/bin/env python3
# [v1.1]
"""
test_neware_doc_conformance.py — check i2c_decoders/neware_decoder.json and
i2c_decoders/smbus1v1_decoder.json (the SBDS v1.1 decoder, reported as "SBDS1v1")
against the Neware-supplied reference "documents/decoders/Smart Battery Registers.txt". Parses the file itself, so a
revised Neware file is re-checked automatically. Intentional deviations are asserted
by name, with the source that governs.  [XREF: neware-doc]
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DECODER_DIR = os.path.join(ROOT, "i2c_decoders")                 # all decoder JSON lives here
NEWARE_REF = os.path.join(ROOT, "documents", "decoders", "Smart Battery Registers.txt")
FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    if not ok:
        FAILS.append(label)


T = open(NEWARE_REF, encoding="utf-8").read()
ACC = {int(m.group(1), 16): m.group(2) for m in
       re.finditer(r"SBS_CMD_\w+\s*=\s*0x([0-9A-Fa-f]+)\s*#\s*(RW|RO|WO)", T)}
MAP = ast.literal_eval(re.search(r"SBS_REGISTER_MAP = (\{.*?\n\})", T, re.S).group(1))
ADDR = int(re.search(r"SBS_ADDRESS = (0x[0-9A-Fa-f]+)", T).group(1), 16)
BITS = {int(m.group(1)): m.group(2) for m in re.finditer(r"Bit\s+(\d+)\s+0x[0-9A-F]+\s+(\w+)", T)}
EC = {int(m.group(1), 16): m.group(2) for m in re.finditer(r"^0x([0-7]) (\S+)", T, re.M)}

check("parsed Neware file: 37 registers, 12 status bits, 8 error codes",
      (len(MAP), len(BITS), len(EC)), (37, 12, 8))
check("register map and access list cover the same codes", set(MAP), set(ACC))


def load(name, addr):
    d = json.load(open(os.path.join(DECODER_DIR, name)))
    rd = {r["register"]: r for r in d["rules"]
          if r["address"] == addr and r["transaction_type"] == "indexed_read"}
    wr = {r["register"]: r for r in d["rules"]
          if r["address"] == addr and r["transaction_type"] == "indexed_write"}
    return d, rd, wr


NW, NRD, NWR = load("neware_decoder.json", 0x10)
SB, SRD, SWR = load("smbus1v1_decoder.json", 0x0B)
size = lambda r: -1 if r.get("data_bytes") is None else r["data_bytes"]

# ---- address ----------------------------------------------------------------------
check("Neware file default address = SBDS 0x0B", ADDR, 0x0B)
check("SBDS1v1 decoder at 0x0B", SB["i2c_address"], ADDR)
check("DEVIATION neware decoder at 0x10 (capture channel config), not file default",
      NW["i2c_address"], 0x10)

# ---- every register: present, size, name --------------------------------------------
for lbl, rd in (("neware", NRD), ("SBDS1v1", SRD)):
    check(f"{lbl}: every Neware register decoded", sorted(set(MAP) - set(rd)), [])
    check(f"{lbl}: sizes match (word 2, block variable)",
          [hex(c) for c, (sz, _, _) in MAP.items() if size(rd[c]) != sz], [])
check("neware: names match the Neware file exactly",
      [hex(c) for c, (_, n, _) in MAP.items() if NRD[c]["name"] != n], [])
check("SBDS1v1: names match except 0x3C-0x3F (spec name OptionalMfgFunction4..1)",
      [hex(c) for c, (_, n, _) in MAP.items() if SRD[c]["name"] != n],
      ["0x3c", "0x3d", "0x3e", "0x3f"])

# ---- access ---------------------------------------------------------------------------
nacc = {c: "RW" if c in NWR else "RO" for c in MAP}
check("neware: access matches the Neware file for all 37 registers",
      [hex(c) for c in MAP if nacc[c] != ACC[c]], [])
sacc = {c: "RW" if c in SWR else "RO" for c in MAP}
check("DEVIATION SBDS1v1 0x14/0x15 read-only at battery (SBDS App A; writes go to 0x09)",
      [hex(c) for c in MAP if sacc[c] != ACC[c] and c in (0x14, 0x15)], ["0x14", "0x15"])
check("SBDS1v1 keeps battery->charger writes at 0x09",
      sorted(r["register"] for r in SB["rules"] if r["address"] == 0x09), [0x14, 0x15, 0x16])
check("DEVIATION SBDS1v1 0x3C-0x3F r/w (SBS 1.1 OptionalMfgFunction), Neware says RO",
      [hex(c) for c in MAP if sacc[c] != ACC[c] and c >= 0x3C], ["0x3c", "0x3d", "0x3e", "0x3f"])
check("SBDS1v1: no other access differences",
      [hex(c) for c in MAP if sacc[c] != ACC[c] and c not in (0x14, 0x15, 0x3C, 0x3D, 0x3E, 0x3F)], [])

# ---- units (Neware fixes CAPACITY_MODE = 0) --------------------------------------------
# SBDS §5.1.4 Note 1: CAPACITY_MODE changes only 0x01, 0x04, 0x0F, 0x10, 0x18.
UNIT = {"mAh": ("mAh", "mAh/10mWh"), "mA": ("mA", "mA"), "mV": ("mV", "mV"),
        "min": ("min", "min"), "%": ("%", "%"), "cycles": ("cycles", "cycles"),
        "0.1K": ("degC", "degC")}
for c, (_, n, u) in MAP.items():
    if u in UNIT:
        want_n, want_s = UNIT[u]
        if c == 0x04:
            want_s = "mA/10mW"                  # AtRate follows CAPACITY_MODE
        if c >= 0x3C:
            want_s = ""                         # raw manufacturer word in SBDS1v1
        check(f"0x{c:02X} {n}: unit {u} -> neware {want_n!r}, SBDS1v1 {want_s!r}",
              (NRD[c].get("unit", ""), SRD[c].get("unit", "")), (want_n, want_s))

# ---- BatteryStatus bits and error codes ---------------------------------------------------
for lbl, rd in (("neware", NRD), ("SBDS1v1", SRD)):
    bf = rd[0x16]["bit_fields"]
    single = {b["range"][0]: b["name"] for b in bf if b["range"][0] == b["range"][1]}
    check(f"{lbl}: BatteryStatus named bits match the Neware file",
          {k: v for k, v in BITS.items() if v != "Reserved"},
          {k: single[k] for k in BITS if BITS[k] != "Reserved"})
    check(f"{lbl}: reserved bits 13 and 10 left unnamed",
          [k for k, v in BITS.items() if v == "Reserved" and k in single], [])
    ec = next(b for b in bf if b["range"] == [3, 0])["names"]
    check(f"{lbl}: error codes 0x0-0x7 match", {k: ec[k] for k in EC}, EC)
    check(f"{lbl}: error codes 0x8-0xF reserved on a read", all(n.startswith("Reserved")
          for n in ec[8:16]), True)

print(f"\n{'OK' if not FAILS else 'FAILED'}: {len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
