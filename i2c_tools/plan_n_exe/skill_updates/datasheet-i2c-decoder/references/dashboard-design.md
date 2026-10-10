# Dashboard (Registers-tab) design

The tool shows a decoder in two places:

- the **Decode column**: one line per transaction;
- the **Registers tab**, or dashboard: the *last known value* of every register the decoder
  places on it.

The Decode column is satisfied by correct rules. The dashboard needs **layout decisions**,
and a decoder without them gives the user a thin or empty tab even when every rule decodes
correctly. Design the dashboard on purpose, then check it with `scripts/check_dashboard.py`.

## 1. What the tool builds (tool ≥ 1.6.0)

- **One tab per I2C address with layout info.** An address has layout info when it has a
  rule with `group`, or any `format: "bits"` rule (read or write). Addresses without layout
  get no tab.
- **Tab title:**
  - the file's `device` when only one address has a tab;
  - `<device> — <name> 0xNN` otherwise, where `<name>` comes from the file-level
    **`address_names`** map, e.g. `{"0x6B": "R1", "0x55": "R2"}` or
    `{"0x08": "Host", "0x09": "Charger", "0x0B": "Battery"}`. Keys may be `"0x6B"` or `"107"`.
- **Inside a tab:**
  - **banner** groups as a compact headline strip;
  - **pane** groups side by side;
  - a **bit matrix** of every `bits` rule of that address.

  Groups appear in `display_groups` order; rows in `group_order`, then `name`.
- **A `fields` rule is one row per field.** If the same field name appears on several rules
  in one group (e.g. `word`, `base`, `pointer` on every register), the row reads
  `<rule name> · <field name>`. Otherwise the field name stands alone.
- **Values are sticky:** a row shows the last value decoded since capture start (or, in
  replay, as of the selected row). `—` means "not seen yet".
- **Tool versions before 1.6.0** built a tab for the file's **lowest** address only (review
  B33). A multi-address decoder lost all its other devices there. Smart Battery had no tab at
  all, because its layout is at 0x0B.

## 2. Design rules

1. **Decide what a user needs at a glance; that is the banner.**
   - **Banners** hold 1–2 groups of headline values (pack voltage, current, SoC; charge
     voltage and current setpoints).
   - **Panes** hold 2–4 groups for the rest, grouped by function (Measurements, Status,
     Setpoints, Device info), not by register order.
   - Keep each banner to ≤ 6 rows.
2. **Every multi-address file gets `address_names`.** Use the roles from the document
   (Host / Charger / Battery, primary / secondary, or the board designator). A bare `0x6B`
   tab title is a defect.
3. **Writes are often the interesting data.** On a write-dominated part (chargers, a host
   reporting status) the dashboard must show what was **last written**:
   - put the write rules in their own pane named `<block> (last value)`, or
     `Setpoints written`;
   - **never put a write rule in the same group as its read rule.** That gives two rows for
     one register, which is the "duplicate rows" problem.
   - Group-less write rules are invisible on the dashboard.
4. **Show meaning, not just the raw word.**
   - Split packed words into `fields` (per-channel ADC words; base/pointer; high/low
     bytes with different meanings).
   - Give each field a `unit` and a `description`. The description is the row tooltip.
   - Use `bits` for status/control registers so they land in the bit matrix (set = red,
     zero = green, reserved = grey).
5. **Make correctness visible where the device allows it.** If a value has a known
   structure (an echo, a base ID, a checksum), show the parts as fields. A wrong value is
   then obvious: a mis-routed phase shows the wrong base. The decode engine has no
   comparisons, so do not try to compute ✓/✗ in a `function`.
6. **Subcommand / block reads:** put the decoded `fields` in a pane named after the block.
   The engine already checks the echo, checksum and length of a TI-style block and appends
   ⚠ on a mismatch.
7. **Do not group what the dashboard cannot show:**
   - a `simple_write` that only fires for a protocol case;
   - command-only subcommands (`data_bytes: 0`);
   - alias rules for byte-at-a-time hosts.

   Those stay decode-only.
8. **Static or synthetic devices:** if values never change by design (a test fixture), say
   so in the file `description`, so a user does not mistake a constant for a stuck capture.

## 3. Check it

```bash
python3 scripts/check_dashboard.py <part>_decoder.json
```

It prints the predicted tabs and rows, then its findings:

| Severity | Finding |
|---|---|
| **FAIL** | a group used but not declared |
| **WARN** | multi-address file without `address_names` |
| **WARN** | an address with rules but no tab |
| **WARN** | a declared group nobody uses |
| **WARN** | a read and a write of one register in one group |
| **WARN** | more than 2 banners, or a banner with more than 6 rows |
| **INFO** | read rules left off the dashboard |

Fix every FAIL. Decide on every WARN and record the decision in the `.md` assumptions list.

Example (loopback DUT fixture, layout v2):

```
  TAB  Loopback DUT — R1 0x6B
    [pane] R1 reads: 15 rows
        R1 word 0x00 · word
        R1 word 0x00 · base
        R1 word 0x00 · pointer
        …
    [pane] R1 block 0x3E: 4 rows
    [pane] R1 writes (last value): 2 rows
  OK    dashboard layout has no findings
```

## 4. Known tool limitation

`DecodeSchema.save()` (the decoder editor's save path) drops the file-level metadata:
`device`, `description`, `address_names`, `i2c_address*`, `byte_order` (which drives the
Int column) and `byte_order_note`. It keeps
`rules` and `display_groups` (review B2 area, tool Phase 4; measured 2026-10-05). Until that is fixed:
- deliver decoders as hand-edited or generated JSON;
- warn the user that saving a file in the editor drops the tab names.
