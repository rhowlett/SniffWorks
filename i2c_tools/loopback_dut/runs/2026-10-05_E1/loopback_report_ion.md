# Loopback report (ion capture path)

- **Generated:** 2026-10-05T10:12:55-06:00
- **Expected:** `loopback_dut/runs/2026-10-05_E1/expected.json` (mode hardware, pattern loopback_v1 sha256 4fc68f7999eb…, generated 2026-10-05T10:12:42.103-06:00)
- **Capture:** `loopback_dut/runs/2026-10-05_E1/ion_capture.csv`: 433 rows, 4 outside the run; PEC results present; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 8 · fail 3 · xfail 4 · xpass 0 · not exercisable 0
- **Ledger exact:** NO (unexplained failure or unexpected pass)

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | expect_pass | **pass** | 2/2 |  |
| LB-02 | - | expect_pass | **pass** | 2/2 |  |
| LB-03 | - | expect_pass | **fail** | 1/1 | data_mismatch |
| LB-04 | B8 | xfail | **xfail** | 1/1 | decode_mismatch |
| LB-05 | - | expect_pass | **pass** | 1/1 |  |
| LB-06 | B13, B32 | xfail | **xfail** | 2/2 | nak_on_normal_end_of_read |
| LB-07 | B9, B32 | xfail | **fail** | 2/2 | data_mismatch, pec_invalid |
| LB-08 | B9 | expect_pass | **pass** | 1/1 |  |
| LB-09 | B10, B32 | expect_pass | **pass** | 3/3 |  |
| LB-10 | B10, B32 | expect_pass | **pass** | 2/2 |  |
| LB-11 | B10, B32 | expect_pass | **pass** | 2/2 |  |
| LB-12 | B30, B32 | xfail | **xfail** | 400/400 | address_nak_mismatch, data_mismatch |
| LB-14 | B32 | expect_pass | **fail** | 2/2 | data_mismatch |
| LB-15 | B32 | expect_pass | **pass** | 8/8 |  |
| LB-13 | B31, B32 | xfail | **xfail** | 0/5 | phase_missing, scl_missing |

## LB-03: fail
- `data_mismatch`: iter 0 phase 0 (capture line 6): expected 3 B [10 34 12], captured 3 B [20 68 24], first difference at byte 0

## LB-04: xfail
- `decode_mismatch`: iter 0 phase 0 (line 7): Decode '', expected to contain 'LB simple write = 0x20'

## LB-06: xfail
- `nak_on_normal_end_of_read`: iter 0 phase 1 (capture line 10): normal end-of-read master NAK exported as NAK

## LB-07: fail
- `data_mismatch`: iter 0 phase 1 (capture line 12): expected 3 B [08 A0 6E], captured 3 B [10 40 DD], first difference at byte 0
- `pec_invalid`: iter 0 phase 1 (capture line 12): PEC column ✗ PEC, bus PEC 0x6E is correct

## LB-12: xfail
- `data_mismatch`: iter 82 phase 0 (capture line 185): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 82 phase 0 (capture line 185): NAK shown on an ACKed write
- `data_mismatch`: iter 197 phase 1 (capture line 416): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0

## LB-14: fail
- `data_mismatch`: iter 0 phase 1 (capture line 422): expected 4 B [02 A0 03 A0], captured 4 B [04 40 06 41], first difference at byte 0

## LB-13: xfail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `phase_missing`: iter 0 phase 2: S W 0x6B [10 34 12] not captured
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 4: Sr R 0x6B [02 A0 03 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)
