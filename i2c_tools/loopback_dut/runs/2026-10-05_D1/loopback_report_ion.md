# Loopback report (ion capture path)

- **Generated:** 2026-10-05T10:11:38-06:00
- **Expected:** `loopback_dut/runs/2026-10-05_D1/expected.json` (mode hardware, pattern loopback_v1 sha256 4fc68f7999eb…, generated 2026-10-05T10:11:25.466-06:00)
- **Capture:** `loopback_dut/runs/2026-10-05_D1/ion_capture.csv`: 564 rows, 563 outside the run; PEC results present; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 0 · fail 13 · xfail 2 · xpass 0 · not exercisable 0
- **Ledger exact:** NO (unexplained failure or unexpected pass)

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | expect_pass | **fail** | 0/2 | phase_missing, scl_missing |
| LB-02 | - | expect_pass | **fail** | 0/2 | phase_missing, scl_missing |
| LB-03 | - | expect_pass | **fail** | 0/1 | phase_missing, scl_missing |
| LB-04 | B8 | xfail | **fail** | 0/1 | phase_missing |
| LB-05 | - | expect_pass | **fail** | 0/1 | phase_missing |
| LB-06 | B13, B32 | xfail | **fail** | 0/2 | phase_missing |
| LB-07 | B9, B32 | xfail | **fail** | 0/2 | phase_missing |
| LB-08 | B9 | expect_pass | **fail** | 0/1 | phase_missing |
| LB-09 | B10, B32 | expect_pass | **fail** | 0/3 | phase_missing, scl_missing |
| LB-10 | B10, B32 | expect_pass | **fail** | 0/2 | phase_missing |
| LB-11 | B10, B32 | expect_pass | **fail** | 0/2 | phase_missing |
| LB-12 | B30, B32 | xfail | **xfail** | 1/400 | phase_missing |
| LB-14 | B32 | expect_pass | **fail** | 0/2 | phase_missing, scl_missing |
| LB-15 | B32 | expect_pass | **fail** | 0/8 | phase_missing, scl_missing |
| LB-13 | B31, B32 | xfail | **xfail** | 0/5 | phase_missing, scl_missing |

## LB-01: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)

## LB-02: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [04] not captured
- `phase_missing`: iter 0 phase 1: S R 0x6B [04 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)

## LB-03: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [10 34 12] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)

## LB-04: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [20] not captured

## LB-05: fail
- `phase_missing`: iter 0 phase 0: S W 0x08 [(none)] not captured

## LB-06: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0 03 A0] not captured

## LB-07: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [08] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [08 A0 6E] not captured

## LB-08: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [0A 5A 51] not captured

## LB-09: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [3E 01 00] not captured
- `phase_missing`: iter 0 phase 1: S W 0x6B [3E] not captured
- `phase_missing`: iter 0 phase 2: Sr R 0x6B [01 00 41 40 43 42 45 44 47 46 49 48] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)

## LB-10: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [00] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [00 A0 01 A0 02 A0 03 A0 04 A0 05 A0] not captured

## LB-11: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [00] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [00 A0 01 A0 02 A0 03 A0 04 A0 05 A0] not captured

## LB-12: xfail
- `phase_missing`: iter 0 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 1 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 1 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 2 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 2 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 3 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 3 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 4 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 4 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 5 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 5 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 6 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 6 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 7 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 7 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 8 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 8 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 9 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 9 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 10 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 10 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 11 phase 0: S W 0x6B [06] not captured
- `phase_missing`: iter 11 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 12 phase 0: S W 0x6B [06] not captured
- … 374 more

## LB-14: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0 03 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)

## LB-15: fail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `phase_missing`: iter 0 phase 2: S W 0x55 [02] not captured
- `phase_missing`: iter 0 phase 3: Sr R 0x55 [02 B0] not captured
- `phase_missing`: iter 0 phase 4: S W 0x55 [10 01] not captured
- `phase_missing`: iter 0 phase 5: S W 0x6B [04] not captured
- `phase_missing`: iter 0 phase 6: Sr R 0x6B [04 A0] not captured
- `phase_missing`: iter 0 phase 7: S R 0x55 [10 B0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)

## LB-13: xfail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `phase_missing`: iter 0 phase 2: S W 0x6B [10 34 12] not captured
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 4: Sr R 0x6B [02 A0 03 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)
