# B30 / B31: ion bit-bang capture, investigation and validation plan
<!-- v0.2 -->

Owner decision (2026-10-02): fix the ion sniffer firmware now, not in Phase 5, so that the
core embedded software works. This is an exception to plan rule D-06. Phase-1 runs 1–3
(`loopback_dut/runs/2026-10-02_run1..3`) are the **before** evidence.

## 1. What the rig measured (fw 1.3, 100 kHz unless noted)

| Item | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| B30 slips (whole run, LB-13 excluded) | 7 | 9 | 13 |
| … of which in the 200-read burst LB-12 | 7 | ~10 | ~10 |
| B31: LB-13 at 400 kHz, phases captured | 0/5 | 0/5 | 0/5 |

**B30 signature, the same for every slip in all three runs:**
- one SCL rising edge is lost exactly at the boundary between the address byte's ACK and the
  first data bit;
- the address is always correct;
- the data is shifted left by one bit (`06` → `0C`; `06 A0` → `0C 41` through the master ACK);
- it happens after a START (pointer write) and after a repeated START (read).

That boundary is where the DUT's I2C slave **clock-stretches** to service its address
interrupt. A random sampler stall would land anywhere in a transaction, not always at the
same bit. So there are two candidate causes:

- **H1, sampler stall:** something on the probe runs for longer than an SCL high time, exactly
  there.
- **H2, narrow pulse:** the SCL high pulse that follows the stretch release is shorter than one
  sampler iteration.

The three runs cannot tell H1 from H2. fw 1.4 is built to tell them apart.

## 1.1 First fw 1.4 hardware result (2026-10-05): commands lost while capturing

With fw 1.4 flashed, HELLO and START worked from a fresh reset, but every later command
(STOP, PING, STATUS_REQ) came back as ERROR 2 / 0xFF (bad CRC) or not at all, so the probe
could not be stopped. Bench test on `/dev/cu.usbmodem1203`:

| Probe state | Command bytes sent | Result |
|---|---|---|
| capturing | back to back | ERROR 2 / 0xFF, or nothing |
| capturing | one byte every 2 ms or 5 ms | HELLO / STATUS, correct |
| stopped | back to back | HELLO, correct |

STATUS showed `upkeep_deferred 0`, so the deferral was **not** the cause (the first diagnosis,
recorded in CLAUDE.md v1.11, was wrong). The 1-byte USART RDR is read only in the upkeep slot,
every 64 loop iterations. While capturing, 64 iterations of the fw 1.4 loop (with the diag code)
take longer than one byte time (87 µs at 115200), so back-to-back bytes overrun.

**Implication (fw 1.4 loop, with diag):** while capturing on an idle bus, one loop iteration takes
**more than ~1.36 µs** (87 µs / 64), i.e. the sampler runs below ~0.73 MS/s. This is a lower
bound. The decode path inside a transaction is slower still, and fw 1.3 (no diag) was only a
little faster, since its commands still got through. A 400 kHz SCL high of ~1.25 µs is shorter
than one iteration, which already explains B31 and supports H2 for B30. `max_gap` from the
fw 1.5 diag will give the exact number.

**fw 1.5 fix:** host RX is received by DMA1 CH2 in circular mode into a 256-byte buffer, with
no interrupts and no hot-path cost. The upkeep slot reads from that buffer, so no loop speed
and no deferral (≤ 20 ms; the buffer holds 22 ms) can lose a command byte. A compile-time check
keeps the buffer larger than the longest deferral. Everything else is as in fw 1.4.

## 1.2 fw 1.5 on the rig (2026-10-05): the diag and the deferral break capture; B30 is a sampler stall

Full runs: `loopback_dut/runs/2026-10-05_*` and `2026-10-05_NOTES.md`.

1. **Both fw 1.4 additions collapse 100 kHz decoding on their own.** With SNIFF_DIAG on (runs A1,
   B1) or SNIFF_DEFER_UPKEEP on (D1, D2), every row decodes as address 0x00 with no data, and
   ion scores pass 0. With both off (C1, C2) the result is back to fw 1.3 level. fw 1.0 on the
   same wiring decodes correctly, so this is not the rig. The polled loop had almost no timing
   margin, and each addition pushed it past the edge. The diag therefore measured a different
   loop from the one under test, and §3/§4 below (decide from the diag numbers) are
   **superseded**.
2. **Flash prefetch + instruction cache were never enabled** (1 wait state at 48 MHz). Enabling
   them (`SNIFF_FLASH_ACCEL`, fw 1.5 default) cut LB-12 slip lines from 25/25 (C) to 1/6 (F).
   fw 1.3 had 9/14/21.
3. **The STATUS frame is not the stall.** At 10 Hz vs off, the slip count is unchanged.
4. **The bus is clean (AD2 logic analyser, 2 × 1200 START-triggered windows):**
   - SCL high ≥ 4.92 µs and SCL low ≥ 5.12 µs;
   - no stretch anywhere in the address byte;
   - SDA setup ≥ 2 µs, and SDA never moves while SCL is high.

   **H2 is refuted at 100 kHz.**
5. **B30 = H1.** The C031 misses the full 4.9 µs high of the address-ACK clock (clock 9), so
   every data byte arrives shifted left one bit with the ACK as its LSB. The stall source is not
   yet located: it is not STATUS and not the deferrable upkeep.

**fw 1.5 defaults:** DIAG 0, DEFER 0, FLASH_ACCEL 1. Result: ion pass 10 / xfail 5, ledger
exact in both F runs. B30 is reduced about 4× but not gone. B31 (400 kHz) is unchanged at 0/5.

## 1.3 Next step: locate the stall with trace pins (needs two jumpers)

`build_variants/fw15_trace/` is `SNIFF_TRACE=2`:

| C031 pin | Header | Function |
|---|---|---|
| PA0 | A0 | Toggles once per capture-loop iteration |
| PA1 | A1 | High while the upkeep slot or a frame flush runs |

Jumper **A0 → AD2 DIO2** and **A1 → AD2 DIO3**. Then a START-triggered AD2 capture shows:

- the real loop period;
- every gap longer than the SCL high, aligned with SCL/SDA;
- whether the gap coincides with BUSY.

That locates B30's stall directly, and the same trace sizes the loop for the B31 decision (§5).
Level 2 adds ~4 cycles per iteration. Level 1 (BUSY only) adds none and needs only the A1 jumper.

## 1.4 Trace result (2026-10-05): the decode pass itself is the stall

Details are in `loopback_dut/runs/2026-10-05_NOTES.md`. In summary:
- the idle loop takes 1.3 µs;
- a pass that decodes an edge takes 3.1–3.6 µs (fall / SDA change) or 5.2–5.8 µs (SCL rise),
  up to 8.2 µs;
- the 100 kHz SCL high is 4.9 µs;
- BUSY (upkeep / flush) is not involved.

So B30 and B31 have one root cause: decoding runs in the same polled loop that samples.
Tightening the loop gains too little: timestamp-on-edge gave 0.9 µs idle but no better edge
passes.

**Owner decision needed:** decouple sampling from decoding (§5, revised):

1. **EXTI edge interrupt → RAM edge ring.** PA9/PA10 on EXTI4_15. The ISR stores (IDR, TIM3
   count), about 30 instructions or ~1 µs, and preempts everything else. The existing host-tested
   decoder runs in the main loop on ring entries. This gives up the "zero interrupts" rule. It is
   comfortable at 100 kHz, and at 400 kHz it is limited by ISR time vs the shortest edge spacing.
2. **Timer-paced DMA oversampling of GPIOA->IDR into a circular buffer.** No CPU in the sampling
   path, exact time base, best for 400 kHz. It needs the C0 to allow DMA reads of GPIO (check
   RM0490 / bench test), and the CPU must still scan 1–4 MS/s.
3. **Document 100 kHz only and accept ~0.1–0.5 % B30 slips.** Fallback.

## 1.5 fw 1.6: edge interrupt (owner chose option 1, 2026-10-05) — B30 fixed, B31 not reachable

**Design:**
- EXTI4_15 fires on both edges of PA9 (SCL) and PA10 (SDA). It is the firmware's only
  interrupt.
- The ISR clears the pending flags, reads IDR and TIM3, and pushes (16-bit µs, lines) into a
  1024-entry RAM ring (`Core/Inc/edge_ring.h`), but only when the lines changed.
- The main loop pops one edge per pass into the unchanged, host-tested decoder. It extends the
  time to 32 bits against a base that is re-anchored while the ring is empty.
- Upkeep and frame flushes can no longer cost samples.
- The TX ring drops from 6 KB to 4 KB to make room.
- The polled loop is kept as `SNIFF_EDGE_IRQ=0` (`build_variants/fw16_polled`).

**Hardware (runs G1, G2 trace build; H1, H2 default):**
- 0 FRAMING phases in all four runs;
- LB-12 400/400 exact every time (1600 burst phases; fw 1.3 had 9–21 slip lines per run);
- ion pass 10, LB-12 xpass, SCL 98.9 kHz;
- **B30 is fixed.**

**400 kHz (B31), measured with the trace build (PA0 high during the ISR):**
- The ISR takes 0.58 µs with no push and 1.37 µs with a push (1.23 µs from RAM, so the time is
  in the EXTI/TIM3 accesses, not instruction fetch).
- Entry latency is ≥ 0.33 µs and up to 0.9 µs when an ISR is already running.
- Edges arrive about every 0.8 µs, and 1160–1261 of ~2000 edges arrived during a running ISR.
- tHD;STA (~0.6 µs) is shorter than the ISR's sampling delay, so every START is missed. LB-13
  gives 0 rows and 5 errors, and no longer leaves garbage that corrupts later cases.

**400 kHz is not reachable with an edge ISR on a 48 MHz M0+.** It needs option 2 (timer-paced
DMA oversampling) or the AD2. Until then B31 stays open, documented in the user guide.

## 2. What fw 1.4 changes (`embedded/sniffer_nucleoC0_fw`, fw 1.4/1.5, project 1.5.0)

| Switch (`sniffer_config.h`) | Default | Effect |
|---|---|---|
| `SNIFF_DIAG` | 1 | TIM14 at 48 MHz measures sample gaps and SCL pulse widths while a transaction is open, and per FRAMING phase; reported in STATUS (PROTOCOL.md §1.2.1) |
| `SNIFF_DEFER_UPKEEP` | 1 | No UART pump, command poll or 1 Hz STATUS while a transaction is open (forced after 20 ms) |
| (always) | — | Table-driven CRC-8: the frame encode is ~8× shorter, so a START arriving during a frame flush is less likely to be missed |

**Images:**
- `build/sniffer_nucleoC0_fw.bin`: fw 1.5, diag on, defer on (default).
- `build_variants/fw15_diag_nodefer/sniffer_nucleoC0_fw.bin`: fw 1.5, diag on, defer off. This is the
  A/B variant, to isolate the deferral.

Host side: `tools/ion_capture.py` (headless capture with count/filters + STATUS/diag print)
and `core/ion_protocol.py` (diag decode).

**Not validated on hardware yet.** Host tests only: decoder 86, frame 92 (CRC table == bit-wise
for all 256 inputs; STATUS diag layout); `tests/test_ion_capture.py`.

## 3. Validation procedure (superseded 2026-10-05 by §1.2/§1.3; kept for the record)

Close sniffer_ion first: `ion_capture.py` needs the C031 port. Run from the project root with
`.venv` active. DUT = `/dev/cu.usbmodem1403`, C031 = `/dev/cu.usbmodem1203` (2026-10-05; port
names change with the USB location, so check the serial numbers with `ls /dev/cu.usbmodem*`).

1. Flash `build/sniffer_nucleoC0_fw.bin` onto **NOD_C031C6**. Then:
   `python tools/ion_capture.py --port /dev/cu.usbmodem1203 --seconds 2 --status-only` must
   print `fw 1.5` and a "sampler diag" block. If it reports no HELLO, press the C031's black
   RESET button (B2) once and repeat. The owner saw the probe stuck after a flash once.
   Also check that commands work while capturing: run the same command twice in a row. Both
   runs must stop cleanly, i.e. the second one must not find the probe still capturing.
2. **Run A** (fw 1.5 default). In one terminal:
   ```bash
   python tools/ion_capture.py --port /dev/cu.usbmodem1203 --seconds 25 --pec \
          --decoder i2c_decoders/loopback_dut_decoder.json --out loopback_dut/runs/ion_capture.csv
   ```
   Within 2 s, in a second terminal:
   ```bash
   python loopback_dut/host/loopback_run.py --port /dev/cu.usbmodem1403 \
          --out loopback_dut/runs/expected.json --transcript loopback_dut/runs/transcript.txt
   ```
   Then run `python loopback_dut/tests/test_loopback_capture.py` (the ion path only; it
   reports the AD2 path as SKIPPED). Keep the STATUS/diag print.
3. **Run B** (A/B): flash `build_variants/fw15_diag_nodefer/…bin` and repeat step 2.
4. Repeat A at least twice. B30 is intermittent (~2 % per burst phase), so a single clean run
   proves little.

## 4. How to decide

| Observation | Conclusion | Next step |
|---|---|---|
| A: slips = 0 over ≥ 3 runs, B: slips > 0 | **H1**: a stall from upkeep/STATUS; fixed by the deferral | Keep `SNIFF_DEFER_UPKEEP=1`; set LB-12/LB-15 to expect_pass; B30 Done |
| FRAMING phases with `frm_max_gap` ≥ ~4 µs | **H1**: a stall, but not (only) upkeep | Find the stalling branch (frame flush at a STOP→START boundary?); move the work out of the open-transaction window |
| FRAMING phases with small gap but `frm_min_high` < ~1 µs | **H2**: SCL high narrower than the loop | Polling cannot fix this: go to §5 hardware capture |
| `max_gap` itself > ~1.25 µs | the loop is too slow for 400 kHz (B31) | §5 |

The global `min_high` at 100 kHz should be about 4–5 µs. A much smaller value supports H2 even
without a FRAMING hit.

## 5. B31 (400 kHz) options, to be chosen from the §1.3 trace

At 400 kHz, tHIGH can be as short as 0.6 µs, which is 29 cycles at 48 MHz. The current loop
reads IDR, compares, decodes on change and runs upkeep. The diag `max_gap` will show its real
iteration time. The options:

1. **Two-stage capture:** a minimal sampling loop, run from RAM, appends (IDR, timestamp) to an
   edge ring at about 8–10 cycles per sample. The existing decoder consumes the ring when the
   bus is idle. The decoder is unchanged and stays host-tested. Risk: a sustained 400 kHz burst
   must fit in the ring (~800 edges per 30-byte transaction).
2. **Timer-paced DMA oversampling:** TIM → DMA copies GPIOA->IDR (byte access) into a circular
   buffer at a fixed rate (≥ 3.3 MS/s for 400 kHz), and the CPU scans the buffer. Sample
   timestamps are exact (index × period), and stalls cannot lose edges. Risk: DMA and AHB
   bandwidth on the C031, and the CPU scan rate.
3. **Document** bit-bang capture as 100 kHz-only and point 400 kHz users at slave-monitor mode.
   Fallback only.

Recommendation: decide after the fw 1.4 diag numbers. Option 1 if `max_gap` shows the loop
itself is fast enough and the stalls come from elsewhere; option 2 if H2 is confirmed, because
oversampling also catches narrow pulses.
