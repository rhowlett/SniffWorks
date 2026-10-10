# Loopback report (ion capture path)

- **Generated:** 2026-10-02T12:31:39-06:00
- **Expected:** `loopback_dut/runs/2026-10-02_run1/expected.json` (mode hardware, pattern loopback_v1 sha256 e44471dad980…, generated 2026-10-02T11:47:35.736-06:00)
- **Capture:** `loopback_dut/runs/2026-10-02_run1/ion_capture.csv`: 430 rows, 0 outside the run; PEC results ABSENT; Decode present
- **Expected phases:** 434 · ledger re-applied from pattern `loopback_v1`
- **Verdicts:** pass 8 · fail 1 · xfail 4 · xpass 0 · not exercisable 2
- **Ledger exact:** NO (unexplained failure or unexpected pass)

| Case | Review IDs | Status | Verdict | Matched | Detail |
|---|---|---|---|---|---|
| LB-01 | B32 | expect_pass | **pass** | 2/2 |  |
| LB-02 | - | expect_pass | **pass** | 2/2 |  |
| LB-03 | - | expect_pass | **pass** | 1/1 |  |
| LB-04 | B8 | xfail | **xfail** | 1/1 | decode_mismatch |
| LB-05 | - | expect_pass | **pass** | 1/1 |  |
| LB-06 | B13, B32 | xfail | **xfail** | 2/2 | nak_on_normal_end_of_read |
| LB-07 | B9, B32 | xfail | **not_exercisable** | 2/2 | requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC') |
| LB-08 | B9 | expect_pass | **not_exercisable** | 1/1 | requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC') |
| LB-09 | B10, B32 | expect_pass | **pass** | 3/3 |  |
| LB-10 | B10, B32 | expect_pass | **pass** | 2/2 |  |
| LB-11 | B10, B32 | expect_pass | **pass** | 2/2 |  |
| LB-12 | B30, B32 | xfail | **xfail** | 400/400 | address_nak_mismatch, data_mismatch |
| LB-13 | B31, B32 | xfail | **xfail** | 0/5 | phase_extra, phase_missing, scl_missing |
| LB-14 | B32 | expect_pass | **pass** | 2/2 |  |
| LB-15 | B32 | expect_pass | **fail** | 8/8 | data_mismatch |

## LB-04: xfail
- `decode_mismatch`: iter 0 phase 0 (line 7): Decode '', expected to contain 'LB simple write = 0x20'

## LB-06: xfail
- `nak_on_normal_end_of_read`: iter 0 phase 1 (capture line 10): normal end-of-read master NAK exported as NAK

## LB-07: not_exercisable
- note: requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC')

## LB-08: not_exercisable
- note: requires pec_validation_on: capture has no PEC results (enable 'Validate SMBus PEC')

## LB-12: xfail
- `data_mismatch`: iter 19 phase 0 (capture line 59): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 19 phase 0 (capture line 59): NAK shown on an ACKed write
- `data_mismatch`: iter 49 phase 0 (capture line 119): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 49 phase 0 (capture line 119): NAK shown on an ACKed write
- `data_mismatch`: iter 51 phase 1 (capture line 124): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 95 phase 1 (capture line 212): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0
- `data_mismatch`: iter 102 phase 0 (capture line 225): expected 1 B [06], captured 1 B [0C], first difference at byte 0
- `address_nak_mismatch`: iter 102 phase 0 (capture line 225): NAK shown on an ACKed write
- `data_mismatch`: iter 118 phase 1 (capture line 258): expected 2 B [06 A0], captured 2 B [0C 41], first difference at byte 0

## LB-13: xfail
- `phase_extra`: capture line 421: W 0x05 [(none)] not emitted
- `phase_missing`: iter 0 phase 0: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 1: Sr R 0x6B [02 A0] not captured
- `phase_missing`: iter 0 phase 2: S W 0x6B [10 34 12] not captured
- `phase_missing`: iter 0 phase 3: S W 0x6B [02] not captured
- `phase_missing`: iter 0 phase 4: Sr R 0x6B [02 A0 03 A0] not captured
- `scl_missing`: no SCL (Hz) values on this case's rows (probe fw >= 1.3?)

## LB-15: fail
- `data_mismatch`: iter 0 phase 3 (capture line 427): expected 2 B [02 B0], captured 2 B [04 61], first difference at byte 0
