#!/usr/bin/env python3
# [v0.1]
"""
check_dashboard.py - preview and lint the Registers-tab (dashboard) layout of
a decoder JSON, standalone (no tool repo needed).

The AD2 / ion I2C tool builds ONE dashboard tab per I2C address that has
layout info (a rule with `group`, or any `format: "bits"` rule - read OR
write; the tool's bit matrix takes both), titled
'<device>' when there is one such address, else '<device> — <name> 0xNN' with
<name> from the optional file-level "address_names" map ({"0x6B": "R1"}).
A tab shows `display_groups` (banner strip, then panes) filtered to that
address's grouped rules, plus a bit matrix of ALL its `bits` rules. A
`fields` rule shows one row per field; a field name that repeats across rules
in one group is shown as '<rule name> · <field name>'.

Usage:
    python3 check_dashboard.py <part>_decoder.json [--strict]

Prints the predicted tabs and their rows, then findings:
  FAIL  a display group named by a rule is not declared in display_groups
  WARN  multi-address file with no address_names entry for a laid-out address
  WARN  an address has rules but nothing on the dashboard (no tab)
  WARN  a declared display group is used by no rule
  WARN  a read rule and a write rule for the same register share one group
        (two rows for one register: put writes in a '... (last value)' pane)
  WARN  more than 2 banner groups, or a banner group with more than 6 rows
  INFO  read rules left off the dashboard (count per address)
Exit status: 1 on FAIL (or on WARN with --strict), else 0.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict


def _addr(rule, file_addr):
    a = rule.get("address", file_addr)
    return int(a) if a is not None else None


def _names(meta) -> dict:
    out = {}
    for k, v in (meta.get("address_names") or {}).items():
        try:
            out[int(str(k), 0)] = str(v)
        except ValueError:
            pass
    return out


def main(argv) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path, strict = argv[0], "--strict" in argv
    d = json.load(open(path, encoding="utf-8"))
    rules = d.get("rules", [])
    file_addr = d.get("i2c_address")
    device = d.get("device") or path
    groups = d.get("display_groups") or []
    declared = {g["name"]: g.get("kind", "pane") for g in groups}
    names = _names(d)
    fails, warns, infos = [], [], []

    by_addr = defaultdict(list)
    for r in rules:
        by_addr[_addr(r, file_addr)].append(r)

    def laid_out(rs):
        return any(r.get("group") or (r.get("format") == "bits"
                                      and r.get("bit_fields")) for r in rs)

    tabs = sorted(a for a, rs in by_addr.items() if a is not None and laid_out(rs))
    used = set()
    for r in rules:
        g = r.get("group")
        if g:
            used.add(g)
            if g not in declared:
                fails.append(f"rule {r.get('name')!r} uses group {g!r}, not declared in display_groups")
    for g in declared:
        if g not in used:
            warns.append(f"display group {g!r} is declared but no rule uses it")
    banners = [g for g, k in declared.items() if k == "banner"]
    if len(banners) > 2:
        warns.append(f"{len(banners)} banner groups (1-2 recommended)")

    print(f"{device}: {len(rules)} rules, addresses "
          + ", ".join(f"0x{a:02X}" for a in sorted(a for a in by_addr if a is not None)))
    for a in tabs:
        title = device if len(tabs) == 1 else \
            f"{device} — {names.get(a, '') + ' ' if names.get(a) else ''}0x{a:02X}"
        if len(tabs) > 1 and a not in names:
            warns.append(f"multi-address file: add address_names entry for 0x{a:02X} (tab title is a bare address)")
        print(f"\n  TAB  {title}")
        rs = by_addr[a]
        for g in groups:
            members = sorted((r for r in rs if r.get("group") == g["name"]
                              and r.get("format") != "bits"),
                             key=lambda r: (r.get("group_order", 0), r.get("name", "")))
            if not members:
                continue
            fcount = Counter(f.get("name") for r in members for f in (r.get("fields") or []))
            rows = []
            for r in members:
                if r.get("fields"):
                    for f in r["fields"]:
                        n = f.get("name")
                        rows.append(f"{r.get('name')} · {n}" if fcount[n] > 1 else n)
                else:
                    rows.append(r.get("name") or "(unnamed)")
            print(f"    [{g.get('kind', 'pane')}] {g['name']}: {len(rows)} rows")
            for row in rows:
                print(f"        {row}")
            if g.get("kind") == "banner" and len(rows) > 6:
                warns.append(f"banner {g['name']!r} on 0x{a:02X} has {len(rows)} rows (keep banners to headline values)")
            # read + write of one register in the same group
            regs = defaultdict(set)
            for r in members:
                if r.get("register") is not None:
                    regs[r["register"]].add("read" if "read" in r.get("transaction_type", "") else "write")
            for reg, kinds in regs.items():
                if kinds == {"read", "write"}:
                    warns.append(f"group {g['name']!r}: register 0x{reg:02X} has both a read and a write row")
        bits = [r for r in rs if r.get("format") == "bits" and r.get("bit_fields")]
        if bits:
            nw = sum(1 for r in bits if "write" in r.get("transaction_type", ""))
            print(f"    [bit matrix] {len(bits)} bit-field rules ({nw} of them writes)")
        off = [r for r in rs if "read" in r.get("transaction_type", "")
               and not r.get("group") and r.get("format") != "bits"]
        if off:
            infos.append(f"0x{a:02X}: {len(off)} read rule(s) not on the dashboard")
    for a, rs in sorted((a, rs) for a, rs in by_addr.items() if a is not None):
        if a not in tabs:
            warns.append(f"0x{a:02X} has {len(rs)} rule(s) but nothing on the dashboard (no tab)")

    print()
    for m in fails:
        print(f"  FAIL  {m}")
    for m in warns:
        print(f"  WARN  {m}")
    for m in infos:
        print(f"  INFO  {m}")
    if not (fails or warns):
        print("  OK    dashboard layout has no findings")
    return 1 if fails or (strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
