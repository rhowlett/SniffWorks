# Run 1 — 2026-10-02 11:47
<!-- v0.1 -->
- DUT fw 0.1 (before the NA/ND fix), 15 cases, 434 phases, every case emit_status ok.
- ion (C031 fw 1.3): 8 pass, xfail LB-04 (B8) + LB-06 (B13), LB-07/08 not exercisable
  (Validate SMBus PEC was off), FAIL LB-12 (7/400 phases bit-shifted left by one bit),
  LB-15 (1 phase bit-shifted), LB-13 (400 kHz: 0/5 captured). Measured SCL 98.9-99.4 kHz at 100 kHz.
- ad2: INVALID run - AD2 wires were not connected correctly (owner, 2026-10-02); one
  garbage row (0x00 W, 255 x 00, no STOP).
