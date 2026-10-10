# Handoff — Phase 01: I2C Loopback DUT + capture verification harness
<!-- v0.1 -->
**Session ended:** 2026-10-05 · **Next phase:** 02 — Repo foundations, conventions, test harness · **Tree version:** PROJECT_VERSION 1.6.0

## 1. What this phase was supposed to do

Build a deterministic I2C traffic source (the "loopback DUT") and a harness that compares each
sniffer's capture against exactly what was emitted, case by case. It arms an xfail ledger for
the capture-path review items B8–B13 so that Phase 5 can prove its fixes. No review item was
to be fixed (D-06).

Two owner-approved exceptions changed tool behaviour and are recorded in §5:
- C031 per-transaction SCL measurement + CSV v2;
- the C031 firmware fixes for B30.

## 2. What actually exists now

**The rig** (owner's bench; full detail in `documents/loopback_dut_bringup.md`):

| Board | Role | Firmware | ST-LINK serial |
|---|---|---|---|
| NUCLEO-H533RE | DUT. I2C1 = master (own address 0x08, the address-NAK case); I2C2 = responder 0x6B; I2C3 = responder 0x55 | DUT fw 0.2 | `0032002732…` |
| NUCLEO-C031C6 | ion sniffer under test | sniffer fw 1.6 (bit-bang, edge interrupt) | `066BFF5448…` |
| Analog Discovery 2 | AD2 sniffer under test | — | SCL DIO0, SDA DIO1 |
| Bus | one 4.7 kΩ pull-up pair to the H533 3V3, all GNDs common | | |

Optional trace jumpers are still fitted: C031 A0 → AD2 DIO2, A1 → AD2 DIO3. They are harmless
with the default image. Ports seen on 2026-10-05 were C031 `/dev/cu.usbmodem1203` and H533
`/dev/cu.usbmodem1403`; these names change with the USB socket.

**New files** (path → purpose):
- `loopback_dut/` (**isolated**: no imports from `core/`, `ui/` or sniffer firmware, and nothing
  imports it):
  - `config/rig.toml`: the one place for addresses, speed and ports;
  - `schema/loopback_pattern.schema.json`, `schema/expected.schema.json`;
  - `patterns/loopback_v1.json`: 15 cases plus **the xfail ledger** (description v0.5);
  - `firmware/`: the CubeMX H533 project. Hand-written code is in `App/`; build entry is
    `GNUmakefile`;
  - `host/`: `loopback_run.py` (drives the DUT, writes `expected.json`), `loopback_compare.py`
    (alignment + verdicts + report), `dut_link.py`, `lbcommon.py`, `lbsynth.py`;
  - `tests/`: `test_pattern_schema.py`, `test_host_model.py`, `test_loopback_harness.py` (T1),
    `test_loopback_capture.py` (T2; exit 77 = loud skip), `tests/host/` (C unit tests of the
    DUT model);
  - `docs/PROTOCOL.md` (DUT line protocol), `docs/setup_guide.md` (v0.9: CubeMX, wiring,
    bench checks);
  - `runs/`: archived evidence runs, 2026-10-02 run1–3 and 2026-10-05 A1…H2, plus
    `2026-10-05_NOTES.md`.
- **Sniffer side:**
  - `i2c_decoders/loopback_dut_decoder.json`: the decoder fixture for the rig;
  - `i2c_capture/loopback_dut_replay_check.csv`;
  - `tools/ion_capture.py`: headless C031 capture with filters, writing the GUI's CSV v2;
  - `embedded/sniffer_nucleoC0_fw/Core/Inc/edge_ring.h`;
  - `embedded/tests/host/test_edge_ring.c`.
- **UI:**
  - `ui/widgets/connection_section.py`: shared Device group;
  - `ui/widgets/buttons.py`: compact icon buttons.
- **Docs:**
  - `embedded/docs/build_and_flash.md`: both images (was missing);
  - `documents/loopback_dut_bringup.md`;
  - `embedded/docs/B30_B31_investigation.md`;
  - `documents/phases/` (this file and the review).
- **Project:** `CLAUDE.md` at the project root (v1.18). It is the working agreement; read it.

**Location deviations from the plan.** These follow from the isolation decision:
- `tools/loopback_run.py` is `loopback_dut/host/loopback_run.py`;
- `core/loopback_compare.py` is `loopback_dut/host/loopback_compare.py`;
- `embedded/loopback_dut_fw` is `loopback_dut/firmware`;
- the pattern and schemas live under `loopback_dut/`.

Nothing was renamed, moved or deleted. The change log is still `change_log.md` at the
project root; Phase 2 moves it.

**Firmware state.** C031 sniffer fw 1.6:
- host commands are received by circular DMA (fw 1.5);
- flash prefetch + I-cache are on;
- bit-bang sampling uses an EXTI edge interrupt into a RAM edge ring (fw 1.6);
- `embedded/sniffer_nucleoC0_fw/build/` (tracked) is byte-identical to a clean-tree build;
- variants are in `build_variants/fw16_trace`, `fw16_polled`.

## 3. Test state (verbatim)

Baseline at session start (2026-09-30, change_log "session bootstrap"):

    16/17 tests/test_*.py passed; the failure was test_neware_doc_conformance.py
    (FileNotFoundError: …/tests/Smart_Battery_Registers.txt) → path fix (owner-approved) → 17/17.
    smoke_test.py 8/9 (missing bq76905_gateway_tool, Phase 10). Skips: 2 in test_bq25731_decoder.py,
    1 in test_csv_format.py (captures not present).

At session end (2026-10-05, `.venv` Python 3.12.13):

    project: 19 pass, 0 fail          (tests/test_*.py; 2 new files this phase)
    smoke_test.py: 8/9 checks passed  (unchanged: bq76905_gateway_tool → Phase 10)
    loopback_dut T1: test_pattern_schema / test_host_model / test_loopback_harness → ALL TESTS PASSED
    loopback_dut/tests/host: === 40 checks, 0 failures === ALL LOOPBACK DUT HOST TESTS PASSED
    embedded/tests/host: 86 / 92 / 22 checks, 0 failures, ALL HOST TESTS PASSED
    i2c_decoders/*.json: 10/10 validate against schema/decoder.schema.json
    ion capture, fw 1.6 (runs 2026-10-05_G1/G2/H1/H2, ledger v0.5):
        ion: pass 11 fail 0 xfail 4 xpass 0 not_exercisable 0  ledger EXACT

**Known skips:**
- `test_csv_format.py` skips `POC_i2c_sys_bq25731_smoke_v0.4.csv` because it looks under
  `/mnt/user-data/uploads/`, although the file is in `i2c_capture/` (C9, Phase 2);
- `test_bq25731_decoder.py` skips 2 cases (captures not present);
- `test_loopback_capture.py` exits 77 (SKIPPED, never a pass) when no rig artefacts are given.

## 4. The xfail ledger

From `loopback_dut/patterns/loopback_v1.json` v0.5:

| Case | Review ID | Why it fails | Which phase flips it |
|---|---|---|---|
| LB-04 (both) | B8 | a 1-byte simple write decodes to nothing (no "LB simple write" Decode text) | 5 |
| LB-07 (both) | B9 | PEC on a Sr read is computed over the wrong bytes: bus PEC 0x6E is correct, the app shows ✗ PEC (proven on both, run 3) | 5 |
| LB-09/10/11 (AD2) | B10 | spy-segment truncation; **not reproduced** ≤ 80 B at 100 kHz (runs 2–3). The cases stay xfail on AD2 because B32 hides them | 5 |
| LB-06 (both) | B13 | normal end-of-read master NAK exported as NAK | 5 |
| LB-13 (ion) | B31 | the C031 (48 MHz M0+) cannot capture 400 kHz: every START is missed, no rows | faster probe MCU (owner: H723ZG/H743ZI2), not a numbered phase yet |
| LB-01, 06, 07, 09–15 (AD2) | B32 | a write phase that ends in Sr is exported as `0x00 W [00]` (~75 % per phase; intermittent) | 5 (AD2 host code) |

**Closed this phase: B30** (ion bit slip under burst). Fixed by fw 1.6 and closed in the ledger
on 2026-10-05; LB-12 ion is now expect_pass and a slip there is a regression (harness
self-test guards it).

## 5. Decisions made this session

| ID | Decision | Why | Evidence |
|---|---|---|---|
| P1-D1 | The DUT is one NUCLEO-H533RE (three I2C peripherals), fully isolated from the sniffer code | removes the C031's one-I2C limit; prevents contamination | DS14539 Table 8; isolation grep |
| P1-D2 | Address plan: master 0x08 (NAK case), responders 0x6B / 0x55; all adjustable in `config/rig.toml` | a lone master cannot ACK itself; field cases reproducible | LB-05 NA on hardware |
| P1-D3 | C031 per-transaction SCL measurement + capture CSV v2 `SCL (Hz)` (owner-directed exception to D-06 / M1) | the harness checks speed per case | SCL 98.8–99.6 kHz measured at 100 kHz |
| P1-D4 | Symptom-based, per-path xfail ledger; edit-distance alignment; loud T2 skip | an unexplained failure or stale ledger can never pass silently | test_loopback_harness, 6 mutations |
| P1-D5 | Fix the ion firmware (B30/B31) now (owner, exception to D-06) | the core embedded SW must work | runs 1–3 before; G/H runs after |
| P1-D6 | fw 1.5: host RX by circular DMA; fw 1.6: bit-bang sampling by EXTI edge interrupt + edge ring (owner chose option 1) | polled decode took 3–6 µs per edge vs a 4.9 µs SCL high | trace-pin measurement, `2026-10-05_NOTES.md` |
| P1-D7 | B31 left open; probe to move to a faster MCU | ISR 0.6–1.4 µs vs 400 kHz edges ~0.8 µs apart | trace at 400 kHz |
| P1-D8 | sniffer_ion / sniffer_ad2 harmonized: shared ConnectionSection, compact equal-width icon buttons, baud on the Device tab | owner request | offscreen renders; test_ion_protocol guard |

All are also in `CLAUDE.md` → Decisions.

## 6. Gotchas the next session must know

- **Python.** Always use `.venv` (Python 3.12.13). macOS `python3` is 3.9 and breaks
  PEP 604 code.
- **Shell.** There is no `timeout` command. zsh aborts on unmatched globs; use
  `2>/dev/null`.
- **Tracked firmware build.** `embedded/sniffer_nucleoC0_fw/build/` is **tracked** and is the
  shipped image. Phase 2's C8 ("strip firmware build/ from deliverables") must keep a shipped
  .bin somewhere (e.g. a release folder), or the rig loses its flashable image.
- **Firmware variants.** Build them with `make BUILD_DIR=<scratch> EXTRA_DEFS=…`, never into
  `build/`.
- **C031 capture path is fragile.** Never add code to it without a full loopback run before
  and after. In the polled loop, ~10–20 cycles per pass collapsed 100 kHz decoding. In
  edge-IRQ mode the ISR is the critical path.
- **Ports.** Rig port names change with the USB socket; identify boards by ST-LINK serial
  (`STM32_Programmer_CLI -l st-link`).
- **One program per serial port.** Close `sniffer_ion.py` before running
  `tools/ion_capture.py`.
- **DUT link.** The DUT needs LF line endings (`miniterm --eol LF`). After flashing, the first
  command may be dropped (DutLink retries). The C031 may need a RESET press after a
  drag-and-drop flash.
- **Ledger.** `expected.json` freezes the ledger at run time; re-judge old runs with
  `loopback_compare.py --pattern`. A new ledger key must be added to `LEDGER_KEYS` /
  `loopback_run.py`.
- **Captures.** Tick Validate SMBus PEC before Start, and clear all filters before exporting a
  loopback capture (B14).
- **Version tags.** The master plan says "line-1 tag", but the tree uses line 2 (after
  shebang/docstring opener). This session followed line 2. Phase 2's tag baseline must pick
  one rule.
- **Button style.** Never full-width bars. Use `ui/widgets/buttons.py` and check with an
  offscreen render of both sniffer windows.

## 7. Open questions carried forward

| Question | Blocks | Who answers |
|---|---|---|
| Intermittent-symptom ledger (signature kinds such as `sr_write_zeroed`, excused when present, never xpass when absent)? Only B32 needs it now: AD2 run 3 has one xpass (LB-01) | an exact AD2 ledger on every run | owner |
| Which faster probe MCU (NUCLEO-H723ZG or H743ZI2) and when; is B31 its own phase? | B31 | owner |
| Is `i2c_decoders/smbus1v1_decoder.json` the renamed `SBDS1v1_decoder.json`? (assumed yes) | nothing | owner |
| Plan's B12 desync evidence: the DUT driver does not use `IonMasterLink` (isolation), so B12 needs another test | Phase 5 B12 | Phase 5 session |

## 8. Start-here checklist for the next session

1. Read `00_MASTER_PLAN.md`, `PHASE_02_*.md`, this handoff, `CLAUDE.md` (project root only),
   and `documents/phases/REVIEW_PHASE_01.md` §7.
2. Unzip `ion_i2c_tool_phase01_v1.6.0.zip` (or use the working tree). Run the suite. There is
   no `tools/run_tests.sh` yet; Phase 2 creates it. Until then:
   ```bash
   source .venv/bin/activate
   for t in tests/test_*.py; do QT_QPA_PLATFORM=offscreen python $t >/dev/null 2>&1 && echo "ok $t" || echo "FAIL $t"; done
   python tests/smoke_test.py | tail -1
   for t in loopback_dut/tests/test_pattern_schema.py loopback_dut/tests/test_host_model.py loopback_dut/tests/test_loopback_harness.py; do python $t | tail -1; done
   make -C embedded/tests/host test | tail -1
   ```
   Confirm: 19 ok, `8/9 checks passed`, 3 × `ALL TESTS PASSED`, `ALL HOST TESTS PASSED`. If not,
   stop.
3. Phase 2 first step: when restructuring (C3/C8), keep `loopback_dut/` self-contained, and
   keep a tracked, flashable C031 image and the DUT image.
