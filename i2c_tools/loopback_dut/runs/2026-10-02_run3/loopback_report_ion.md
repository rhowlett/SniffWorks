# Loopback report (ion capture path)

- **Generated:** 2026-10-02T12:39:35-06:00
- **Expected:** `/Users/Richard.Howlett/Documents/GitHub/advanced_engineering/tools/scripts/ion_i2c_tool/loopback_dut/runs/expected.json` (mode hardware, pattern loopback_v1 sha256 4fc68f7999eb…, generated 2026-10-02T12:37:06.720-06:00)
- **Capture:** `/Users/Richard.Howlett/Documents/GitHub/advanced_engineering/tools/scripts/ion_i2c_tool/loopback_dut/runs/ion_capture.csv`: 431 rows, 3 outside the run; PEC results present; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 9 · fail 1 · xfail 5 · xpass 0 · not exercisable 0
- **Ledger exact:** NO (unexplained failure or unexpected pass)

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | expect_pass | **fail** | 2/2 | data_mismatch |
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
| LB-12 | B30, B32 | xfail | **xfail** | 397/400 | address_nak_mismatch, data_mismatch, flag_mismatch, phase_extra, phase_missing |
| LB-14 | B32 | expect_pass | **pass** | 2/2 |  |
| LB-15 | B32 | expect_pass | **pass** | 8/8 |  |
| LB-13 | B31, B32 | xfail | **xfail** | 0/5 | phase_missing, scl_missing |

## LB-01: fail
- `data_mismatch`: iter 0 phase 1 (capture line 3): expected 2 B [02 A0], captured 2 B [04 41], first difference at byte 0

## LB-04: xfail
- `decode_mismatch`: iter 0 phase 0 (line 7): Decode '', expected to contain 'LB simple write = 0x20'

## LB-06: xfail
- `nak_on_normal_end_of_read`: iter 0 phase 1 (capture line 10): normal end-of-read master NAK exported as NAK

## LB-07: xfail
- `pec_invalid`: iter 0 phase 1 (capture line 12): PEC column ✗ PEC, bus PEC 0x6E is correct

## LB-12: xfail
- `data_mismatch`: iter 1 phase 1 (capture line 24): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 61 phase 1 (capture line 144): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `phase_extra`: capture line 154: W 0x00 [(none)] not emitted
- `phase_missing`: iter 66 phase 1: Sr R 0x6B [06 A0] not captured
- `phase_missing`: iter 91 phase 0: S W 0x6B [06] not captured
- `flag_mismatch`: iter 91 phase 1 (capture line 203): start S, expected Sr
- `data_mismatch`: iter 97 phase 1 (capture line 215): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 116 phase 0 (capture line 252): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 116 phase 0 (capture line 252): NAK shown on an ACKed write
- `data_mismatch`: iter 120 phase 1 (capture line 261): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 135 phase 0 (capture line 290): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 135 phase 0 (capture line 290): NAK shown on an ACKed write
- `data_mismatch`: iter 141 phase 1 (capture line 303): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 154 phase 0 (capture line 328): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 154 phase 0 (capture line 328): NAK shown on an ACKed write
- `data_mismatch`: iter 158 phase 1 (capture line 337): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 179 phase 1 (capture line 379): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `phase_extra`: capture line 395: W 0x00 [(none)] not emitted
- `phase_missing`: iter 187 phase 1: Sr R 0x6B [06 A0] not captured
- `data_mismatch`: iter 191 phase 1 (capture line 403): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 196 phase 1 (capture line 413): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0

## LB-13: xfail
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `phase_missing`: iter 0 phase 2: S W 0x6B [10 34 12] not captured
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 4: Sr R 0x6B [02 A0 03 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)
