# Run 3 — 2026-10-02 12:37
<!-- v0.1 -->
- DUT fw 0.2 (HELLO fw=0.2), LB-13 run last, 15 cases / 434 phases, all emit_status ok.
- Validate SMBus PEC ON in both apps (ion 424 rows / ad2 432 rows carry a PEC result).
- **B9 proven on both paths:** LB-07 read-word, bus PEC 0x6E correct (independently computed over
  D6 08 D7 08 A0), both sniffers show ✗ PEC; LB-08 write-byte PEC ✓ on both (pass, as predicted).
- ion: pass 9, xfail 5 (B8 LB-04, B13 LB-06, B9 LB-07, B30 LB-12, B31 LB-13), fail 1: LB-01
  bit slip 02 A0 -> 04 41 (B30 hitting a single-transaction case; intermittent).
- ad2: pass 4, xfail 10, xpass 1: LB-01 (its single Sr-terminated write came through clean;
  B32 mangled 159/212 Sr writes this run vs 162/212 in run 2 -> ~75 % per phase, intermittent).
