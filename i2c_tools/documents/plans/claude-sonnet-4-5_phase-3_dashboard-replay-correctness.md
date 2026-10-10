# Phase 3 — Dashboard and replay correctness
Model: claude-sonnet-4-5 · Prereq: Phase 1 · Est. scope: 5 fixes + tests

Fixes B11, B12, B13, B14, B19. These are wrong-output bugs in code paths
the user exercises constantly (Registers tabs, replay scrub, CSV export).

## Task 1 — B14: register tabs collide on shared addresses (M, verified)
`ui/widgets/registers_tabs_host.py` builds each device view from the
MERGED schema filtered by `min(entry.addresses)`. bq76905 and bq76922 both
live at 0x08, so each tab shows the other's rules, and `display_groups`
merge globally by name.

Fix: build each `RegistersView` from **its own entry's schema**, not the
merged one. Namespace display groups per device internally (the group's
display label stays as authored). The cache must still be fed by the
single merged `StreamDecoder` — so key cache entries by
(decoder identity, address, register), not address alone.
Test: load both 0x08 decoders, assert the bq76905 tab contains no
bq76922-only rule name and vice versa.

## Task 2 — B13: writes never update the dashboard (M)
The cache key includes `transaction_type`, so a write to an R/W register
(bq25731 has 17 write rules) never refreshes the read row the user is
watching. Fix: key by (address, register) — or explicitly link each read
rule to its write counterpart — so a `(set)` write updates the displayed
value. Preserve direction information if the view wants to show "last
written vs last read"; do not lose the distinction, just stop it from
splitting the cache.
Test: feed a write of ChargeCurrent, assert the dashboard row updates.

## Task 3 — B12: bit matrix truncates at 2 bytes (M)
Bit rules with `data_bytes >= 3` lose bits 16 and up. Generate one matrix
row per byte for N bytes (the existing 2-byte high/low pair is the N=2
case of the same rule). Test with a synthetic 4-byte bits rule: all 32
bits addressable and colored.

## Task 4 — B11: inconsistent number formatting (M)
Dashboard uses `.4g` (so 12345.6 renders `1.235e+04`); the log uses `.4f`
stripped. Add ONE formatter (put it in `core/decode_schema.py` next to the
render path, or a small `core/value_format.py`) and call it from both
`ui/widgets/registers_view.py` and the log. Rule: integers render without
a decimal point; non-integers render with up to 4 decimals, trailing
zeros stripped; never scientific notation below 1e9.
Test: 12345.6 renders "12345.6" in both surfaces.

## Task 5 — B19: CSV export writes only filtered rows (H)
Re-importing a filtered export drops pointer writes, so decode pairing
breaks — the user silently gets a capture that cannot replay.
Fix: default the export to ALL rows; offer filtered export as an explicit
choice (checkbox in the save dialog, or a second menu action labeled
"Export visible rows…"). Warn in the UI copy that a filtered export may
not replay correctly.
Time precision: the capture spec (`documents/CSV_FORMAT.md`) defines
`HH:MM:SS.mmm` for v1. Do NOT change the format in this phase — that is
Phase 4's schema-versioned change. Note the limitation in the export
dialog instead.
Test: export with an address filter active, reload, assert row count
equals the unfiltered total and that a pointer/read pair still decodes.

## Acceptance
```bash
QT_QPA_PLATFORM=offscreen python3 tests/test_registers_tab.py
QT_QPA_PLATFORM=offscreen python3 tests/test_bq25731_decoder.py   # scrub tests
QT_QPA_PLATFORM=offscreen python3 tests/test_bq76922_decoder.py
QT_QPA_PLATFORM=offscreen python3 tests/test_csv_format.py
QT_QPA_PLATFORM=offscreen python3 tests/test_table_ui_updates.py
QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py
```
Plus new cases for each of the five tasks above.

## Deliverable
MINOR bump if the export behavior change is user-visible (it is) — go to
the next MINOR, changelog, manifest, one zip.
