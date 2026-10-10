# datasheet-i2c-decoder — skill update (2026-10-05)
<!-- v0.1 -->

These are drafts for the claude.ai skill. The local synced copy would be overwritten by the next
sync, so apply them in claude.ai.

**Why:**
- the loopback DUT decoder's dashboard (Registers tab) was thin;
- multi-address decoders lost devices on the dashboard (review B33, fixed in tool 1.6.0);
- the skill gave almost no guidance on dashboard design;
- the schema guide stated a `bits`-write rule stays out of the bit matrix. The tool puts
  **every** `bits` rule there.

## Files

| Action | Path in the skill | Source here |
|---|---|---|
| **add** | `references/dashboard-design.md` | `references/dashboard-design.md` |
| **add** | `scripts/check_dashboard.py` | `scripts/check_dashboard.py` |
| **edit** | `SKILL.md` | blocks 1–4 below |
| **edit** | `references/schema-guide.md` | blocks 5–6 below |

---

## 1. SKILL.md — "What this skill produces": add a fifth deliverable line after item 4

**Find:**
```
   validates the decoder, not real readings. A sidecar
   `<part>_replay_check.expected.md` lists the expected decode per row.
```
**Replace with:**
```
   validates the decoder, not real readings. A sidecar
   `<part>_replay_check.expected.md` lists the expected decode per row.
5. **A dashboard preview** — the `scripts/check_dashboard.py` output (predicted Registers
   tabs and rows) pasted into the `.md`, with a decision recorded for every WARN.
```

## 2. SKILL.md — step 5: replace the layout bullet

**Find:**
```
- Layout: `display_groups` with 1–2 `banner` groups (headline numbers) and 2–4 `pane`
  groups. `group` on read rules only.
```
**Replace with:**
```
- Layout — design the dashboard on purpose (read `references/dashboard-design.md`):
  `display_groups` with 1–2 `banner` groups (headline numbers, ≤ 6 rows each) and 2–4
  `pane` groups by function. A **multi-address file must carry `address_names`**
  (`{"0x0B": "Battery", "0x09": "Charger"}`), because the tool builds one tab per address.
  Write rules go in their **own** `… (last value)` / `Setpoints written` pane, never in
  the same group as the matching read rule. Split packed words into `fields` so each part
  is a labelled row.
```

Also in step 5, **find:**
```
  write is genuinely opaque. Do **not** put `group` on a write rule — that, not the format, is what duplicates Registers-tab rows.
```
(the sentence may wrap differently) and **replace the second sentence with:**
```
  Do **not** put a write rule in the same group as its read rule — that is what
  duplicates Registers-tab rows; a separate "(last value)" pane for writes is correct
  and is how a write-dominated part shows its setpoints.
```

## 3. SKILL.md — step 6: add the dashboard check to the command block

**Find:**
```
python3 scripts/make_replay_check.py <part>_decoder.json -o <part>_replay_check.csv
```
**Replace with:**
```
python3 scripts/make_replay_check.py <part>_decoder.json -o <part>_replay_check.csv
python3 scripts/check_dashboard.py <part>_decoder.json
```
and **add after the `make_replay_check.py` paragraph:**
```
- `check_dashboard.py` predicts exactly what the tool's Registers tabs will show (one tab
  per address with layout; field rows; bit matrix). Fix every FAIL; for each WARN either
  fix it or record why in the `.md`. Paste the tab preview into the `.md`.
```

## 4. SKILL.md — "Recurring failure modes": add two items

**Add after item 9:**
```
10. A multi-address decoder without `address_names`, or with layout on only one address —
    on tool < 1.6.0 only the lowest address got a tab (B33); on any version bare-address
    tab titles are unreadable.
11. A dashboard of raw words: packed values not split into `fields`, writes not shown,
    status registers not in `bits`. Decodes fine, tells the user nothing.
```

---

## 5. references/schema-guide.md — §1 top-level fields table: add a row after `display_groups`

**Find:**
```
| `display_groups` | array | Optional v4 Registers-tab layout (section 7). |
```
**Replace with:**
```
| `display_groups` | array | Optional v4 Registers-tab layout (section 7). |
| `address_names` | object | Optional: per-address tab names for a multi-address file, e.g. `{"0x6B": "R1", "0x55": "R2"}`. Keys `"0x6B"` or `"107"`. Tool ≥ 1.6.0 titles each tab `<device> — <name> 0xNN`. |
```

## 6. references/schema-guide.md — §7: replace the two rules at the end

**Find:**
```
- **`group` on read rules only.** A grouped write rule duplicates every row.
- A `format: "bits"` **read** rule joins the bit matrix regardless of grouping; a `bits`
  **write** rule does not, which is why writes may safely use `bits` (section 9).
```
**Replace with:**
```
- **Never put a write rule in the same group as its read rule** — that gives two rows for
  one register. Writes belong in their own pane (`… (last value)`, `Setpoints written`).
- **Every** `format: "bits"` rule — read **or write** — joins its address's bit matrix,
  regardless of grouping (measured on tool 1.6.0; the earlier "writes do not" statement was
  wrong). A `bits` write rule therefore *does* appear on the dashboard — useful for status
  a host writes (e.g. SBS AlarmWarning to Host/Charger), noisy for a long list of commands.
- The tool builds **one tab per address** with layout (tool ≥ 1.6.0; before that only the
  lowest address, review B33). Name them with file-level `address_names`.
- Full design guidance and the checker: `references/dashboard-design.md`,
  `scripts/check_dashboard.py`.
```

---

## Verification done here (2026-10-05)

- **`check_dashboard.py` matches the tool** on the loopback DUT decoder (offscreen render of the
  ion window replaying rig run 2026-10-05_H1):
  - tabs: `Loopback DUT — R2 0x55`, `Loopback DUT — R1 0x6B`;
  - rows: `R1 word 0x02 · base = 0xA0`, etc.
- **All 10 shipped decoders run through the checker.** Its tab predictions match the tool,
  including Smart Battery `Host 0x08` / `Charger 0x09` / `Battery 0x0B`.
- **The round-trip limitation in `dashboard-design.md` §4 was measured:** after
  `DecodeSchema.save()` only `version`, `rules` and `display_groups` remain.
