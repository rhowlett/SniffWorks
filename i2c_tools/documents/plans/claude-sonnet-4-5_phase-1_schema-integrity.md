# Phase 1 — Decoder schema and persistence integrity
Model: claude-sonnet-4-5 · Prereq: none (first phase) · Est. scope: 5 fixes + tests

Fixes B1, B2, B3, B21, M2. Everything in later phases assumes a decoder
file can survive a load/save round trip and that the schema accepts every
shipped decoder. Do this first.

## Context you need
- Decoders live in `i2c_decoders/*.json` (bq25731, bq76905, bq76922).
- Schema: `schema/decoder.schema.json`. Format reference:
  `documents/i2c_decoder.md`.
- Engine: `core/decode_schema.py` (`DecodeSchema.load`, `.to_json`,
  `DecodeRule`, `StreamDecoder`).
- The editor (`ui/widgets/decode_editor.py`) saves through `to_json`, so
  B2/B3 are live data-loss paths, not theory.

## Task 1 — B1: schema conditionals lack `required` (H)
Reproduce first:
```python
r = {"address": 8, "transaction_type": "indexed_read", "register": 2,
     "data_bytes": 2, "byte_order": "le", "signed": False,
     "function": "X", "unit": "mV", "name": "T"}
# validating {"version":4,"rules":[r]} today raises "'bit_fields' is a required property"
```
Cause: each `if` block in the schema matches when the keyed property is
ABSENT, because the `if` has no `required`. Fix: inside every `if`, add
`"required": ["format"]` (or `["transaction_type"]` for the subcommand and
register conditionals) so the conditional only fires when the key exists.
Verify all three shipped decoders still validate AND the rule above now
validates. Add `tests/test_decoder_schema_conformance.py` that walks
`i2c_decoders/*.json` and validates each (this also covers R9's "no schema
check on every decoder").

## Task 2 — B2: `to_json()` drops file-level metadata (H)
Confirmed missing after round trip: `device`, `description`, `i2c_address`,
`i2c_address_hex`, `byte_order_note`. Consequence: saving from the editor
makes the Decoders list show a filename instead of the device name, and
the decoder loses its I2C address.

Fix: have `DecodeSchema.load` retain the parsed top-level dict (minus
`rules`) as `self.metadata`, and have `to_json` emit those keys first,
then its own known keys (known keys win, so edits are not overwritten by
stale metadata). Unknown/future keys must pass through untouched.

## Task 3 — B3: empty `bit_fields` dropped on save (M)
bq76922 "PF Alert D" (reg 0x10) has `"bit_fields": []`. After a save the
key vanishes and the file fails its own schema. Pick ONE:
- (preferred) `to_json` always emits `bit_fields` for `format: "bits"`
  rules, even when empty; OR
- set `minItems: 1` in the schema and give PF Alert D a real field.
If you choose the first, keep the schema permissive for empty lists. Test
both directions: round trip bq76922 and re-validate.

## Task 4 — B21: `subcommand_reg` default disagreement (L)
Schema documents a default of 62 (0x3E); `core/decode_schema.py` treats a
missing value as "this device has no subcommands". Make them agree — the
code behavior is the safer one (absence means absent), so REMOVE the
default from the schema and state the rule in `documents/i2c_decoder.md`.
Do not silently start defaulting to 0x3E: that would make non-TI decoders
route arbitrary reads into subcommand decoding.

## Task 5 — M2: enforce the schema at runtime (H)
Today the schema is used only by tests. Add `core/schema_validation.py`
with `validate_decoder_dict(d) -> list[str]` (empty list = valid) using
`jsonschema`, and call it:
- on load in `ui/widgets/sidebar_sections.py::validate_decoder` and in the
  decoder manager's add path: on errors, show them and REFUSE to add the
  decoder to the active set (a half-valid decoder silently mis-decodes,
  which is worse than not loading).
- on save in `ui/widgets/decode_editor.py`: block the save, list the
  errors, and keep the editor open.
Add `jsonschema` to `requirements.txt` (already a de-facto dependency).
Errors must be human-readable: `rule[12] "Charge Current": <message>`.

## Acceptance
```bash
python3 tools/check_tree.py                     # clean before you start
QT_QPA_PLATFORM=offscreen python3 tests/test_decoder_schema_conformance.py
QT_QPA_PLATFORM=offscreen python3 tests/test_decode_schema.py
QT_QPA_PLATFORM=offscreen python3 tests/test_editor_v4.py
QT_QPA_PLATFORM=offscreen python3 tests/test_bq25731_decoder.py
QT_QPA_PLATFORM=offscreen python3 tests/test_bq76922_decoder.py
QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py      # expect 8 passes
```
New test file must include: the B1 no-format rule validating; a full
load→to_json→load round trip of all three decoders asserting metadata
equality and rule-count equality; PF Alert D keeping `bit_fields`; an
invalid decoder being rejected by `validate_decoder_dict` with a message
naming the offending rule.

## Deliverable
PATCH bump (1.2.1 → 1.2.2), changelog section, manifest regenerated, one
zip. Report which of B1/B2/B3/B21/M2 landed and anything you could not do.
