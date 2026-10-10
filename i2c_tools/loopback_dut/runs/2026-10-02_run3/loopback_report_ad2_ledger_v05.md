# Loopback report (ad2 capture path)

- **Generated:** 2026-10-05T12:17:48-06:00
- **Expected:** `loopback_dut/runs/2026-10-02_run3/expected.json` (mode hardware, pattern loopback_v1 sha256 4fc68f7999eb…, generated 2026-10-02T12:37:06.720-06:00)
- **Capture:** `loopback_dut/runs/2026-10-02_run3/ad2_capture.csv`: 434 rows, 0 outside the run; PEC results present; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 4 · fail 0 · xfail 10 · xpass 1 · not exercisable 0
- **Ledger exact:** NO (unexplained failure or unexpected pass)

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | xfail | **xpass** | 2/2 |  |
| LB-02 | - | expect_pass | **pass** | 2/2 |  |
| LB-03 | - | expect_pass | **pass** | 1/1 |  |
| LB-04 | B8 | xfail | **xfail** | 1/1 | decode_mismatch |
| LB-05 | - | expect_pass | **pass** | 1/1 |  |
| LB-06 | B13, B32 | xfail | **xfail** | 1/2 | nak_on_normal_end_of_read, phase_extra, phase_missing |
| LB-07 | B9, B32 | xfail | **xfail** | 1/2 | pec_invalid, phase_extra, phase_missing |
| LB-08 | B9 | expect_pass | **pass** | 1/1 |  |
| LB-09 | B10, B32 | xfail | **xfail** | 2/3 | phase_extra, phase_missing |
| LB-10 | B10, B32 | xfail | **xfail** | 1/2 | phase_extra, phase_missing |
| LB-11 | B10, B32 | xfail | **xfail** | 1/2 | phase_extra, phase_missing |
| LB-12 | B32 | xfail | **xfail** | 252/400 | phase_extra, phase_missing |
| LB-14 | B32 | xfail | **xfail** | 1/2 | phase_extra, phase_missing |
| LB-15 | B32 | xfail | **xfail** | 5/8 | phase_extra, phase_missing |
| LB-13 | B31, B32 | xfail | **xfail** | 3/5 | phase_extra, phase_missing |

## LB-04: xfail
- `decode_mismatch`: iter 0 phase 0 (line 7): Decode '', expected to contain 'LB simple write = 0x20'

## LB-06: xfail
- `phase_extra`: capture line 9: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `nak_on_normal_end_of_read`: iter 0 phase 1 (capture line 10): normal end-of-read master NAK exported as NAK

## LB-07: xfail
- `phase_extra`: capture line 11: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [08] not captured
- `pec_invalid`: iter 0 phase 1 (capture line 12): PEC column ✗ PEC, bus PEC 0x6E is correct

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
- `phase_extra`: capture line 33: W 0x00 [00] not emitted
- `phase_missing`: iter 6 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 35: W 0x00 [00] not emitted
- `phase_missing`: iter 7 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 37: W 0x00 [00] not emitted
- `phase_missing`: iter 8 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 39: W 0x00 [00] not emitted
- `phase_missing`: iter 9 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 45: W 0x00 [00] not emitted
- `phase_missing`: iter 12 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 47: W 0x00 [00] not emitted
- `phase_missing`: iter 13 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 49: W 0x00 [00] not emitted
- `phase_missing`: iter 14 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 51: W 0x00 [00] not emitted
- `phase_missing`: iter 15 phase 0: S W 0x6B [06] not captured
- `phase_extra`: capture line 53: W 0x00 [00] not emitted
- … 271 more

## LB-14: xfail
- `phase_extra`: capture line 421: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured

## LB-15: xfail
- `phase_extra`: capture line 423: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_extra`: capture line 425: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 2: S W 0x55 [02] not captured
- `phase_extra`: capture line 428: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 5: S W 0x6B [04] not captured

## LB-13: xfail
- `phase_extra`: capture line 431: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_extra`: capture line 434: W 0x00 [00] not emitted
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured
