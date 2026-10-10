# Loopback report (ion capture path)

- **Generated:** 2026-10-05T12:17:48-06:00
- **Expected:** `loopback_dut/runs/2026-10-05_H1/expected.json` (mode hardware, pattern loopback_v1 sha256 4fc68f7999eb…, generated 2026-10-05T11:31:58.458-06:00)
- **Capture:** `loopback_dut/runs/2026-10-05_H1/ion_capture.csv`: 429 rows, 0 outside the run; PEC results present; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 11 · fail 0 · xfail 4 · xpass 0 · not exercisable 0
- **Ledger exact:** YES

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | expect_pass | **pass** | 2/2 |  |
| LB-02 | - | expect_pass | **pass** | 2/2 |  |
| LB-03 | - | expect_pass | **pass** | 1/1 |  |
| LB-04 | B8 | xfail | **xfail** | 1/1 | decode_mismatch |
| LB-05 | - | expect_pass | **pass** | 1/1 |  |
| LB-06 | B13, B32 | xfail | **xfail** | 2/2 | nak_on_normal_end_of_read |
| LB-07 | B9, B32 | xfail | **xfail** | 2/2 | pec_invalid |
| LB-08 | B9 | expect_pass | **pass** | 1/1 |  |
| LB-09 | B10, B32 | expect_pass | **pass** | 3/3 |  |
| LB-10 | B10, B32 | expect_pass | **pass** | 2/2 |  |
| LB-11 | B10, B32 | expect_pass | **pass** | 2/2 |  |
| LB-12 | B32 | expect_pass | **pass** | 400/400 |  |
| LB-14 | B32 | expect_pass | **pass** | 2/2 |  |
| LB-15 | B32 | expect_pass | **pass** | 8/8 |  |
| LB-13 | B31, B32 | xfail | **xfail** | 0/5 | phase_missing, scl_missing |

## LB-04: xfail
- `decode_mismatch`: iter 0 phase 0 (line 7): Decode '', expected to contain 'LB simple write = 0x20'

## LB-06: xfail
- `nak_on_normal_end_of_read`: iter 0 phase 1 (capture line 10): normal end-of-read master NAK exported as NAK

## LB-07: xfail
- `pec_invalid`: iter 0 phase 1 (capture line 12): PEC column ✗ PEC, bus PEC 0x6E is correct

## LB-13: xfail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `phase_missing`: iter 0 phase 2: S W 0x6B [10 34 12] not captured
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 4: Sr R 0x6B [02 A0 03 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)
