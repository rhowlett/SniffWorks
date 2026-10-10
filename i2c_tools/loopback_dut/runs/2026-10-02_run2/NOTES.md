# Run 2 — 2026-10-02 12:06
<!-- v0.1 -->
- DUT fw v0.2 build (NA fix confirmed: LB-05 ack NA; HELLO still says fw=0.1 because
  LB_FW_MINOR was not bumped). 15 cases, 434 phases, every case emit_status ok.
- ion (C031 fw 1.3), 431 rows: pass LB-01/02/03/05/09/10/11/15; xfail LB-04 (B8), LB-06 (B13);
  not exercisable LB-07/08 (PEC column empty); FAIL LB-12 (bit slips 06→0C / 06 A0→0C 41 in
  ~10 of 400 phases, 1 lost), LB-13 (400 kHz: 0/5, garbage rows 0x00 W / 0x0C R, no STOP),
  LB-14 (first phase recorded as Sr: decoder left mid-transaction by the LB-13 garbage).
  SCL 98.8–99.6 kHz measured at 100 kHz set (pred 100 075).
- ad2, 434 rows: write phases ending in a repeated START exported as `0x00 W [00]` in 162 of
  212 (stop-terminated writes always right); the 36/64/80-byte reads were captured COMPLETE
  (B10 not reproduced at <= 80 bytes, 100 kHz); PEC column empty; no SCL column values.
