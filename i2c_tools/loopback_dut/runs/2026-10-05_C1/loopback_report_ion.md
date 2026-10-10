# Loopback report (ion capture path)

- **Generated:** 2026-10-05T10:10:50-06:00
- **Expected:** `loopback_dut/runs/2026-10-05_C1/expected.json` (mode hardware, pattern loopback_v1 sha256 4fc68f7999eb…, generated 2026-10-05T10:10:37.084-06:00)
- **Capture:** `loopback_dut/runs/2026-10-05_C1/ion_capture.csv`: 432 rows, 2 outside the run; PEC results present; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 9 · fail 1 · xfail 5 · xpass 0 · not exercisable 0
- **Ledger exact:** NO (unexplained failure or unexpected pass)

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | expect_pass | **fail** | 2/2 | address_nak_mismatch, data_mismatch |
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
| LB-12 | B30, B32 | xfail | **xfail** | 396/400 | address_nak_mismatch, data_mismatch, flag_mismatch, phase_extra, phase_missing |
| LB-14 | B32 | expect_pass | **pass** | 2/2 |  |
| LB-15 | B32 | expect_pass | **pass** | 8/8 |  |
| LB-13 | B31, B32 | xfail | **xfail** | 0/5 | phase_missing, scl_missing |

## LB-01: fail
- `data_mismatch`: iter 0 phase 0 (capture line 2): expected 1 B [02], captured 1 B [04], first difference at byte 0
- `address_nak_mismatch`: iter 0 phase 0 (capture line 2): NAK shown on an ACKed write

## LB-04: xfail
- `decode_mismatch`: iter 0 phase 0 (line 7): Decode '', expected to contain 'LB simple write = 0x20'

## LB-06: xfail
- `nak_on_normal_end_of_read`: iter 0 phase 1 (capture line 10): normal end-of-read master NAK exported as NAK

## LB-07: xfail
- `pec_invalid`: iter 0 phase 1 (capture line 12): PEC column ✗ PEC, bus PEC 0x6E is correct

## LB-12: xfail
- `data_mismatch`: iter 5 phase 1 (capture line 32): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `phase_extra`: capture line 58: W 0x00 [(none)] not emitted
- `phase_missing`: iter 18 phase 1: Sr R 0x6B [06 A0] not captured
- `data_mismatch`: iter 25 phase 1 (capture line 72): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 42 phase 0 (capture line 105): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 42 phase 0 (capture line 105): NAK shown on an ACKed write
- `data_mismatch`: iter 66 phase 1 (capture line 154): expected 2 B [06 A0], captured 0 B [(none)], first difference at byte 0
- `data_mismatch`: iter 92 phase 1 (capture line 206): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 93 phase 1 (capture line 208): expected 2 B [06 A0], captured 1 B [06], first difference at byte 1
- `flag_mismatch`: iter 93 phase 1 (capture line 208): stop -, expected P
- `phase_extra`: capture line 209: W 0x00 [(none)] not emitted
- `data_mismatch`: iter 117 phase 1 (capture line 257): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 124 phase 1 (capture line 271): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 130 phase 0 (capture line 282): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 130 phase 0 (capture line 282): NAK shown on an ACKed write
- `data_mismatch`: iter 138 phase 1 (capture line 299): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 144 phase 0 (capture line 310): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 144 phase 0 (capture line 310): NAK shown on an ACKed write
- `data_mismatch`: iter 153 phase 0 (capture line 328): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 153 phase 0 (capture line 328): NAK shown on an ACKed write
- `data_mismatch`: iter 158 phase 0 (capture line 338): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 158 phase 0 (capture line 338): NAK shown on an ACKed write
- `data_mismatch`: iter 175 phase 1 (capture line 373): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 176 phase 0 (capture line 374): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 176 phase 0 (capture line 374): NAK shown on an ACKed write
- … 6 more

## LB-13: xfail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `phase_missing`: iter 0 phase 2: S W 0x6B [10 34 12] not captured
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 4: Sr R 0x6B [02 A0 03 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)
