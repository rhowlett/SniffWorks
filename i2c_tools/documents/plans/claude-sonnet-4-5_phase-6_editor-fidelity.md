# Phase 6 — Decoder editor fidelity
Model: claude-sonnet-4-5 · Prereq: Phases 1–5 · Est. scope: largest UI phase

Fixes B4, B5, M4, M6. This is the highest data-loss risk in the product:
opening a decoder in the editor and pressing Update can silently destroy
authored content. Phase 1's schema enforcement will now BLOCK such a save,
which converts silent corruption into a visible error — but the underlying
bugs still need fixing.

## Task 1 — B5 first (it is small and blocks testing the rest)
Selecting or removing a subcommand row does nothing: the row key is
derived from Dir+Reg (yielding `simple_write`) instead of `rule.key()`.
Fix: store `rule.key()` in each row's `Qt.UserRole` and use it for find,
select, and remove. Test: select and remove a bq76905 subcommand rule.

## Task 2 — B4: Add/Update rebuilds the rule from the form (H)
Consequences, all verified by the reviewer: `description`, `fields`,
`register_width_bytes`, subcommand data, and bit-field descriptions are
wiped; `_collect_bit_fields` drops enum fields whose names contain commas
(13 fields in bq25731); changing addr/reg/dir leaves the old rule behind
as a duplicate.

Fix:
- Edit a COPY of the selected rule (`dataclasses.replace`), applying only
  the fields the form actually owns. Never construct a fresh rule from
  form state alone.
- Treat an addr/reg/dir change as a MOVE: remove the old key, insert the
  new one, and refuse if the new key already exists.
- Replace the comma-joined enum-names string with a per-name table widget
  (one row per value) so commas inside names are safe.
- Surface parse errors in the dialog instead of dropping fields silently.
Test: load bq25731, select a rule with comma-containing enum names, press
Update without editing, save, and assert the file is byte-identical to the
original (modulo key order). That round-trip test is the acceptance bar
for this phase.

## Task 3 — M4: the editor cannot express half the schema (H)
Missing: transaction-type selector; create/edit/remove for subcommand
rules (17 in bq76905, 34 in bq76922); editors for `fields`,
`description`, `register_width_bytes`, `subcommand_reg`, and bit-field
`description`.
Add: a type selector that shows/hides the relevant inputs; subcommand code
and subcommand-register inputs; a multi-line description box; a structured
`fields` table (name/offset/size/byte order/signed/format/function/unit/
description); a description column in the bit-field table.
Keep the editor honest: every control must map to exactly one schema key,
and unknown keys on a loaded rule must survive an edit untouched.

## Task 4 — M6: saving does not refresh open windows
The user must re-add the file today. Emit `saved(path)` from the editor;
hosts (`ui/widgets/sidebar_sections.py`, `ui/decoder_editor_launcher.py`,
`decoder_editor_window.py`) call `manager.add(path)` to reload in place,
then rebuild register tabs. A `QFileSystemWatcher` is acceptable as an
alternative, but the signal is simpler and avoids double-reload races.
Test: with a replay window open, save from the editor and assert the
window's schema picked up a renamed rule.

## Acceptance
```bash
QT_QPA_PLATFORM=offscreen python3 tests/test_editor_v4.py
QT_QPA_PLATFORM=offscreen python3 tests/test_decoder_schema_conformance.py
QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py
```
New `tests/test_editor_roundtrip.py` is mandatory: load → select each rule
in turn → Update → save → compare to the original for all three shipped
decoders. This closes R9's "no editor round trip".

## Deliverable
MINOR bump, changelog, `documents/User_Guide_decoder_editor.md` updated to
current behavior, manifest, one zip.
