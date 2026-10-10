# Phase 7 — Engine and transport correctness
Model: claude-sonnet-4-5 · Prereq: Phases 1–6 · Est. scope: protocol work; some items need hardware

Fixes B6, B7, B8, B9, B10, B15, B20 and M7. Several of these cannot be
fully confirmed without an AD2 or an Ion probe on a live bus. Where that
is the case, implement against the documented behavior, pin it with a
synthetic test, and say clearly in the report that hardware confirmation
is outstanding. Do not claim a hardware fix is verified from a unit test.

## Task 1 — B15: evaluator hardening (M, no hardware needed)
`**` and `<<` are unbounded (`X**X`, `1<<10**9` hang the app);
`min/max/round` with bad arguments raise `TypeError` that escapes
`_render`. Cap exponent and shift magnitudes (reject exponents > 64 and
shifts > 64 at parse time), and catch `TypeError`/`ValueError`/
`OverflowError`, converting them to `DecodeError`. Test with each hostile
expression; the app must stay responsive.

## Task 2 — B7: SMBus PEC across combined transactions (H)
PEC covers Addr+W, command, Addr+R, and data. The code computes it per
phase, so every SMBus read-word/read-block shows ✗ PEC. Move the
computation to the PAIRING layer (write phase + read phase together).
Coordinate with `core/i2c_controller.py` (`write_read`, `spy_poll`),
`core/ion_backend.py`, and whichever of `log_model`/`decode_schema` holds
the pairing. Synthetic test: a known-good SMBus read-word frame with a
correct PEC byte must validate; flipping one data bit must fail it.
Also unify the two CRC-8 implementations while you are here (C9's second
half) — one `crc8` helper.

## Task 3 — B8: AD2 spy drops continuation segments (H, hardware)
`spy_poll` discards segments with `fStart == 0`, truncating transactions
split across status calls (36-byte subcommand blocks are the common
victim) and losing stop-only status. Accumulate segments until Stop or
Restart, following Digilent's `Digital_I2c_Spy.py` pattern. Synthetic
test: feed a scripted sequence of segments through the accumulator and
assert one complete 36-byte transaction comes out.

## Task 4 — B6: dead simple-write path (M)
`_is_pointer_write` is true for every 1-byte write, so `simple_write`
rules never decode. Fix: prefer a `simple_write` rule when the address has
one AND there is no indexed rule for that byte; otherwise treat the byte
as a pointer. Careful: this interacts with the pointer persistence across
STOP that makes stop-separated register reads work — do not regress
`tests/test_decode_schema.py` or the bq25731 replay decode counts.

## Task 5 — B20: NAK semantics (M)
The master's NAK on the final read byte is normal I2C, but it renders as a
red error, and `_compute_visible`'s frame grouping depends on that
behavior. Distinguish address NAK, data NAK, and end-of-read NAK in the
transaction model, adjust the grouping logic in the same change, and keep
the capture CSV's `NAK` column semantics (spec: `documents/CSV_FORMAT.md`)
backward compatible — if you need finer detail in the file, that is a
capture-schema version bump, not a silent change.

## Task 6 — B9, B10: Ion transport (M, hardware)
- B9: the worker drain on stop exits at the first empty read
  (`timeout=0`), losing final frames. Loop until a deadline with a short
  sleep.
- B10: `IonMasterLink` desyncs after a timeout — late TXN frames stay in
  `_pending` and are attributed to the next command. Flush the parser and
  pending list before each send. A sequence tag is the better fix but
  requires protocol v2; if you do that, update
  `embedded/docs/PROTOCOL.md`, the firmware, and `core/ion_protocol.py`
  together, and keep v1 compatibility.

## Task 7 — M7: unimplemented transaction types (M)
`general_call`, `device_id_query`, and `split_transaction` are declared in
the schema but never produced; `register_width_bytes > 1` is ignored
because the register is always `data[0]`. Implement in
`StreamDecoder.feed`: address 0x00 → general call, 0x7C → device ID query,
and a multi-byte register index honoring the rule's width. If you cannot
implement one safely, REMOVE it from the schema rather than leaving a
declared-but-dead type.

## Acceptance
Every existing test file plus smoke (8 passes), the firmware host C tests
if you touched protocol (`embedded/tests/host`), and new synthetic tests
for B15, B7, B8, B6, B20, M7. Report hardware-unconfirmed items explicitly.

## Deliverable
MINOR bump (MAJOR if you change the frame protocol), changelog,
`embedded/docs/PROTOCOL.md` updated if touched, manifest, one zip.
