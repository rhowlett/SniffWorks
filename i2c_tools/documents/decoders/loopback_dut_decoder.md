# Loopback DUT — I2C decoder

Synthetic register map served by the loopback DUT (NUCLEO-H533RE) responders; source: loopback_dut/docs/PROTOCOL.md §4 (DUT fw 0.2, protocol 1). Multi-address file: R1 = I2C2 at 0x6B (word base 0xA000), R2 = I2C3 at 0x55 (word base 0xB000); rules carry their own address and the Registers tab shows one tab per responder (address_names). Word region: word(p) = base + p, little-endian, so a read shows the responder base in the high byte (A0 = R1, B0 = R2; a wrong base means a mis-routed phase) and the pointer echo in the low byte (must equal the register). Writes are acknowledged and counted but NOT stored, so read values never change; the 'writes (last value)' panes show what the host last wrote. R1 has the TI BQ769x-style subcommand block at 0x3E..0x61 (echo, checksum and length are checked by the engine; a mismatch is flagged with a warning sign). Addresses are rig.toml defaults; if rig.toml changes them, this file must change too. Test fixture for the loopback harness, not a real device. 0x6B also belongs to bq25731_decoder.json: load only one of the two (same-address cross-talk is review B19). Layout v2 (2026-10-05): per-responder panes, word fields, write and block panes.

- **Address:** 0x6B (8-bit W 0xD6 / R 0xD7)
- **File byte order:** le
- **Schema version:** 4  ·  **Rules:** 12
- **Note:** Registers are 16-bit little-endian words (PROTOCOL.md §4).

## Rules

| Reg | Type | W | Data | Fmt | BO | Sgn | Unit | Function | Name |
|-----|------|---|------|-----|----|----|------|----------|------|
| 0x00 | indexed_read | 1 | 2 | hex | le |  |  | X | R1 word 0x00 |
| 0x02 | indexed_read | 1 | 2 | hex | le |  |  | X | R1 word 0x02 |
| 0x04 | indexed_read | 1 | 2 | hex | le |  |  | X | R1 word 0x04 |
| 0x06 | indexed_read | 1 | 2 | hex | le |  |  | X | R1 word 0x06 |
| 0x08 | indexed_read | 1 | 2 | hex | le |  |  | X | R1 word 0x08 |
| 0x0A | indexed_write | 1 | 1 | hex | le |  |  | X | R1 word 0x0A (set) |
| 0x10 | indexed_write | 1 | 2 | hex | le |  |  | X | R1 word 0x10 (set) |
| — | simple_write | 1 | 1 | hex | be |  |  | X | LB simple write |
| sub 0x01 | subcommand | 1 | 32 | hex | be |  |  | X | LB block 0x0001 |
| 0x02 | indexed_read | 1 | 2 | hex | le |  |  | X | R2 word 0x02 |
| 0x10 | indexed_read | 1 | 2 | hex | le |  |  | X | R2 word 0x10 |
| 0x10 | indexed_write | 1 | 1 | hex | le |  |  | X | R2 word 0x10 (set) |

### Fields — R1 word 0x00
- off 0 +2B **word** hex le X 
- off 1 +1B **base** hex be X 
- off 0 +1B **pointer** hex be X 

### Fields — R1 word 0x02
- off 0 +2B **word** hex le X 
- off 1 +1B **base** hex be X 
- off 0 +1B **pointer** hex be X 

### Fields — R1 word 0x04
- off 0 +2B **word** hex le X 
- off 1 +1B **base** hex be X 
- off 0 +1B **pointer** hex be X 

### Fields — R1 word 0x06
- off 0 +2B **word** hex le X 
- off 1 +1B **base** hex be X 
- off 0 +1B **pointer** hex be X 

### Fields — R1 word 0x08
- off 0 +2B **word** hex le X 
- off 1 +1B **base** hex be X 
- off 0 +1B **pointer** hex be X 

### Fields — LB block 0x0001
- off 0 +1B **buf[0]** hex be X 
- off 1 +1B **buf[1]** hex be X 
- off 30 +1B **buf[30]** hex be X 
- off 31 +1B **buf[31]** hex be X 

### Fields — R2 word 0x02
- off 0 +2B **word** hex le X 
- off 1 +1B **base** hex be X 
- off 0 +1B **pointer** hex be X 

### Fields — R2 word 0x10
- off 0 +2B **word** hex le X 
- off 1 +1B **base** hex be X 
- off 0 +1B **pointer** hex be X 

## Provenance, assumptions and defects

- **Source:** `loopback_dut/docs/PROTOCOL.md` §4 (DUT firmware 0.2, protocol 1). This is a
  synthetic test fixture for the Phase 1 loopback harness, not a real device. Every value is
  defined by `loopback_dut/firmware/App/Src/dut_regmap.c` and pinned by
  `loopback_dut/tests/host/test_dut_regmap.c` and `tests/test_loopback_dut_decoder.py`.
- **Dashboard (Registers tab), layout v2 (2026-10-05).** `address_names` gives one tab per
  responder: "Loopback DUT — R1 0x6B" and "Loopback DUT — R2 0x55" (needs the B33 fix, tool
  ≥ 1.6.0). Each word read splits into **word**, **base** (high byte: A0 = R1, B0 = R2; any
  other value means the phase reached the wrong responder) and **pointer** (low byte: must
  equal the register). Writes appear in "writes (last value)" panes, and the 0x3E block shows
  buf[0], buf[1], buf[30] and buf[31]. The engine checks the block's echo, checksum and length
  and appends ⚠ on a mismatch.
- **Values never change on this rig, by design:** the DUT does not store writes, and reads
  are a pure function of the pointer.
- **Saving this file in the decoder editor drops `address_names`, `device` and
  `description`**: `DecodeSchema.save()` keeps no top-level metadata (review B2 area,
  Phase 4). Edit the JSON directly until then.
- **Addresses** are the `loopback_dut/config/rig.toml` defaults (R1 0x6B, R2 0x55). If
  rig.toml changes them, this file must change too.
- **0x6B is shared with `bq25731_decoder.json`.** Load only one of the two, because
  same-address decoders cross-contaminate (review B19).
- **No indexed rule at R1 0x20, on purpose.** The `simple_write` rule exists for pattern case
  LB-04. With review item **B8** open it decodes empty (expected failure).
- **Replay check:** `i2c_capture/loopback_dut_replay_check.csv` (capture CSV v2, 20 rows,
  values from the real DUT map). Its Decode column holds the independently computed expected
  text. The tool's `make_replay_check.py` output was not used, because that generator puts
  every rule of a multi-address decoder on the file-level address (R2 rows landed on 0x6B).
- **Engine defect found (new B29):** a `data_bytes: 2` rule fed a 1-byte payload renders a
  fabricated value (`R1 word 0x02 = 0x0002`) instead of absent. It is an expected failure in
  `tests/test_loopback_dut_decoder.py`.
- **Validator defect:** the skill's `validate_decoder.py` "tool load" step fails for **every**
  shipped decoder (`'DecodeSchema' object has no attribute 'device'`), because the tool's
  loader keeps no top-level metadata (B2 area). Schema and lint steps pass.

## Changelog

| Date | Change |
|---|---|
| 2026-09-30 | First version: 12 rules (R1 words 0x00–0x08, writes 0x0A/0x10, simple write, subcommand 0x0001 block; R2 word 0x02/0x10, write 0x10) |
| 2026-10-05 | Layout v2: `address_names` (R1/R2 tabs), word/base/pointer fields on every read, groups per responder for reads and last-written values, block pane with 4 buffer bytes; device renamed "Loopback DUT"; Decode text of reads changed accordingly (replay check and vectors updated) |
