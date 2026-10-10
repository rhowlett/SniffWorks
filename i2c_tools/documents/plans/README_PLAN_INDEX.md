# Remediation program — index and sequencing

Source: `20260921_fix_list.md` (external review, 2026-09-21) plus a new
feature request: an in-app **Decoder Inspector** on the Replay tab, modeled
on the IP5385 decoder sanity-check package.

Each phase file is a self-contained work order for a single execution
model. Files are named `claude-<model>_phase-N_<topic>.md`. Execute phases
in order: later phases assume earlier ones landed.

| Phase | Model | Topic | Why this model |
|---|---|---|---|
| 1 | claude-sonnet-4-5 | Decoder schema + persistence integrity (B1, B2, B3, B21, M2) | Reasoning about JSON-Schema conditionals and round-trip semantics; everything downstream depends on it |
| 2 | claude-sonnet-4-5 | **Decoder Inspector** (new feature) | New UI + generator design; the headline deliverable |
| 3 | claude-sonnet-4-5 | Dashboard + replay correctness (B11, B12, B13, B14, B19) | Cross-module reasoning about cache keys and schema scoping |
| 4 | claude-haiku-4-5 | Capture CSV schema completion (M1 remainder) | Mechanical: spec exists, add JSON schema + legacy reader |
| 5 | claude-haiku-4-5 | Consistency and hygiene (C1, C5, C6, C7, C8) | Mechanical sweeps, deletions, renames |
| 6 | claude-sonnet-4-5 | Decoder editor fidelity (B4, B5, M4, M6) | Highest-risk data-loss work; large UI surface |
| 7 | claude-sonnet-4-5 | Engine and transport (B6, B7, B8, B9, B10, B15, B20, M7) | Protocol reasoning; several items need hardware to confirm |

Deferred, not scheduled (decide scope first, they are product questions
rather than defects): M3 hand-tool board ID, M5 user dashboard layout,
M8 orphaned features, C2 first-line version tags, C3 tree restructure,
C4 product-name sweep, R1–R8 refactors. R9 test gaps are absorbed into
the phases that create the relevant surface.

## Status corrections to the review (verified 2026-09-21 on v1.2.1)

Re-verified each claim against the current tree rather than trusting the
review. Results a later executor must not re-litigate:

- **M1 partially DONE.** `documents/CSV_FORMAT.md` (normative v1 spec) and
  `tools/validate_capture_csv.py` now exist; both real captures validate
  strict-clean and `tests/test_csv_format.py` pins the round trip. What
  remains is Phase 4: a machine-readable `schema/capture.schema.json`, a
  version marker line, the legacy 11-column (EVM_*) reader, and wiring the
  validator into the sidebar's `validate_capture`.
- **B1 CONFIRMED.** A plain `indexed_read` rule with no `format` key fails
  validation with "bit_fields is required".
- **B2 CONFIRMED and worse than stated.** `to_json()` drops `device`,
  `description`, `i2c_address`, `i2c_address_hex`, and `byte_order_note`.
- **B3 CONFIRMED.** bq76922 "PF Alert D" loses its empty `bit_fields`.
- **B14 CONFIRMED.** `registers_tabs_host.py` still filters by
  `min(entry.addresses)`; bq76905 and bq76922 both at 0x08 collide.
- **C1 CONFIRMED.** `version.py` is 1.2.1 while `app_info.VERSION` is
  "1.0.0" and the bootstrap fallback is "1.0.0".
- Items the review raised that this program treats as ALREADY CORRECT: the
  replay Registers tabs exist and scrub with the selected row (v1.1.0),
  and PROJECT_VERSION is a single source consumed by `build_application`.

## Standing rules for every phase

1. Restore the tree from the delivered zip; run `python3 tools/check_tree.py`
   FIRST and stop if it reports drift.
2. One change at a time, with a test that fails before and passes after.
3. Never weaken a test to make it pass. If a fix is not achievable, say so
   in the phase report and leave the test failing with a skip reason.
4. Append a dated section to `change_log.md`; update affected docs to
   current behavior only (no history in them).
5. Bump `version.py` per its own rules: MAJOR for format/protocol/schema
   breaks, MINOR for features, PATCH for fixes.
6. Regenerate the manifest (`python3 tools/check_tree.py --regen`), run the
   full suite plus `tests/smoke_test.py`, and deliver ONE zip of the whole
   tree.
7. Do not touch files outside the phase's declared scope.
