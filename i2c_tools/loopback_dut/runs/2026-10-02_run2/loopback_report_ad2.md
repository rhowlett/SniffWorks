# Loopback report (ad2 capture path)

- **Generated:** 2026-10-02T12:33:13-06:00
- **Expected:** `loopback_dut/runs/2026-10-02_run2/expected.json` (mode hardware, pattern loopback_v1 sha256 e44471dad980…, generated 2026-10-02T12:06:20.877-06:00)
- **Capture:** `loopback_dut/runs/2026-10-02_run2/ad2_capture.csv`: 434 rows, 1 outside the run; PEC results ABSENT; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 3 · fail 0 · xfail 10 · xpass 0 · not exercisable 2
- **Ledger exact:** YES

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | xfail | **xfail** | 1/2 | phase_missing |
| LB-02 | - | expect_pass | **pass** | 2/2 |  |
| LB-03 | - | expect_pass | **pass** | 1/1 |  |
| LB-04 | B8 | xfail | **xfail** | 1/1 | decode_mismatch |
| LB-05 | - | expect_pass | **pass** | 1/1 |  |
| LB-06 | B13, B32 | xfail | **xfail** | 1/2 | nak_on_normal_end_of_read, phase_extra, phase_missing |
| LB-07 | B9, B32 | xfail | **not_exercisable** | 1/2 | phase_extra, phase_missing |
| LB-08 | B9 | expect_pass | **not_exercisable** | 1/1 | requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC') |
| LB-09 | B10, B32 | xfail | **xfail** | 2/3 | phase_extra, phase_missing |
| LB-10 | B10, B32 | xfail | **xfail** | 1/2 | phase_extra, phase_missing |
| LB-11 | B10, B32 | xfail | **xfail** | 1/2 | phase_extra, phase_missing |
| LB-12 | B30, B32 | xfail | **xfail** | 250/400 | phase_extra, phase_missing |
| LB-13 | B31, B32 | xfail | **xfail** | 3/5 | phase_extra, phase_missing |
| LB-14 | B32 | xfail | **xfail** | 1/2 | phase_extra, phase_missing |
| LB-15 | B32 | xfail | **xfail** | 5/8 | phase_extra, phase_missing |

## LB-01: xfail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured

## LB-04: xfail
- `decode_mismatch`: iter 0 phase 0 (line 7): Decode '', expected to contain 'LB simple write = 0x20'

## LB-06: xfail
- `phase_extra`: capture line 9: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `nak_on_normal_end_of_read`: iter 0 phase 1 (capture line 10): normal end-of-read master NAK exported as NAK

## LB-07: not_exercisable
- note: requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC')
- `phase_extra`: capture line 11: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [08] not captured

## LB-08: not_exercisable
- note: requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC')

## LB-09: xfail
- `phase_extra`: capture line 15: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 1: S W 0x6B [3E] not captured

## LB-10: xfail
- `phase_extra`: capture line 17: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [00] not captured

## LB-11: xfail
- `phase_extra`: capture line 19: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [00] not captured

## LB-12: xfail
- `phase_extra`: capture line 21: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 23: W 0x00 [00] not emitted
- `phase_missing`: iter 1 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 25: W 0x00 [00] not emitted
- `phase_missing`: iter 2 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 27: W 0x00 [00] not emitted
- `phase_missing`: iter 3 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 29: W 0x00 [00] not emitted
- `phase_missing`: iter 4 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 31: W 0x00 [00] not emitted
- `phase_missing`: iter 5 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 37: W 0x00 [00] not emitted
- `phase_missing`: iter 8 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 39: W 0x00 [00] not emitted
- `phase_missing`: iter 9 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 41: W 0x00 [00] not emitted
- `phase_missing`: iter 10 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 47: W 0x00 [00] not emitted
- `phase_missing`: iter 13 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 49: W 0x00 [00] not emitted
- `phase_missing`: iter 14 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 51: W 0x00 [00] not emitted
- `phase_missing`: iter 15 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 53: W 0x00 [00] not emitted
- … 275 more

## LB-13: xfail
- `phase_extra`: capture line 421: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_extra`: capture line 424: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured

## LB-14: xfail
- `phase_extra`: capture line 426: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured

## LB-15: xfail
- `phase_extra`: capture line 428: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_extra`: capture line 430: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 2: S W 0x55 [02] not captured
- `phase_extra`: capture line 433: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 5: S W 0x6B [04] not captured
