# SniffWorks GPIO sniffer
<!-- version: 1.0 -->

GPIO sub-project of SniffWorks. The root `../../CLAUDE.md` (decisions SW-xx) also applies; this file adds the GPIO detail. Requirements: `documents/requirements.md`; change log: `documents/change_log.md`. Firmware lives in the repo-wide `firmware/` tree (SW-04), not in this folder.

## Findings
- The I²C probe (NUCLEO-C031C6, fw 1.6) already timestamps bus edges by EXTI interrupt into a RAM ring (`i2c_tools/embedded/sniffer_nucleoC0_fw/Core/Inc/edge_ring.h`); that edge-capture path is the nearest existing code to a GPIO sniffer (i2c_tools/CLAUDE.md, Decisions, 2026-10-05).
- On the C031 the edge ISR costs 0.58-1.37 µs with up to 0.9 µs entry latency, so edges closer than ~1-2 µs are lost (i2c_tools/CLAUDE.md, Findings: 400 kHz trace); this bounds the shortest GPIO pulse a C031 target can resolve.

## Decisions
- G-01 GPIO is the second protocol after I²C, because it gives an interrupt-like event to trigger on (owner, 2026-10-19; root SW-05).
- G-02 First cross-bus test: an I2C1 event triggers a GPIO, then watch for an I2C2 event (owner, 2026-10-19; root SW-05).
- G-03 Code lives in the target layout: `protocols/gpio/` for host code, `firmware/targets/<mcu>-<board>/` for probe builds, `system_emulation_testing/` for emulators (owner, 2026-10-19; root SW-14).
- G-04 GPIO runs on NUCLEO POC hardware only; the AD2 is not a SniffWorks backend (owner, 2026-10-19; root SW-11).

## Tradeoffs

## Gotchas
- `.gitkeep` files hold the empty folders; delete each one when the folder gets real content.

## Current State
- Created 2026-10-19: folder skeleton, this file, README, requirements draft (v0.1) and change log. No code yet.
- Next: owner review of `documents/requirements.md` (items marked *proposed*), then the event model and multi-stream CSV columns with the root open questions.

## Open Questions
- Channel count, voltage range and input protection per target (C031 POC vs H723 POC). Blocks the firmware pin map.
- Shortest pulse and edge rate to support, and whether a glitch filter belongs in firmware or host. Blocks the C031 vs H723 choice for the first test.
- Which target runs the first I2C1 → GPIO → I2C2 test: one H723 capturing all three, or a C031 (I²C+GPIO build) plus a second probe on the sync line?
- GPIO event fields (edge time, level, channel, pulse width?) — decided with the root event-model question.

## Revision History
- v1.0 (2026-10-19): Created; decisions G-01..G-04, C031 edge-capture findings, open questions.
