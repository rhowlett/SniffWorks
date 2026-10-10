# Phase 01 Review — I2C Loopback DUT + capture verification harness
<!-- v0.1 -->
**For:** senior designer · **Session dates:** 2026-09-30 → 2026-10-05 · **Reviewer verdict:** ☐ accept ☐ accept with fixes ☐ rework

## 1. Scope

Build a measuring instrument: a deterministic I2C traffic source plus a harness that judges each
sniffer's capture against what was emitted, and arm an xfail ledger for B8–B13. Per D-06, no
review item was to be fixed in this phase.

**Deviation, owner-authorised:**
- per-transaction SCL measurement + CSV v2 (2026-09-30);
- fixing the C031 sniffer firmware for B30/B31 (2026-10-02, "so the core embedded SW works").

B30 was fixed; B31 is open. See §5 criterion 7 and §8.

## 2. Task outcomes

| Task | Review IDs | Status | Evidence |
|---|---|---|---|
| P1-T0 bootstrap: questions, baseline, CLAUDE.md | — | **Done** | §2 questions answered by the owner (CLAUDE.md Decisions); baseline §4.1 |
| P1-T1 pattern + rig config | B8–B13 armed | **Done** | `loopback_v1.json` (15 cases, 437 dry-run / 434 hw phases), schema-valid; `test_pattern_schema` passes |
| P1-T2 DUT firmware (H533) | — | **Done** | bench check §6.1; clean build byte-identical §4.3 |
| P1-T3 host driver | B12 evidence | **Partial** | `loopback_run.py` works on hardware (all runs). **B12 desync evidence not produced**: isolation forbids `IonMasterLink` (§7.3) |
| P1-T4 comparison harness | — | **Done** | per-case verdicts on 17 archived runs; reports §6.2/§6.3 |
| P1-T5 harness self-test | — | **Done** | `test_loopback_harness.py` passes: perfect capture, 6 mutations, ledger semantics, gating, B30 regression guard (§4.1) |
| P1-T6 bench docs | — | **Done** | `embedded/docs/build_and_flash.md` (new), `documents/loopback_dut_bringup.md` (new), `loopback_dut/docs/setup_guide.md` v0.9 |
| P1-T7 close | — | **Done** | this review, `HANDOFF_PHASE_01.md`, change-log entries, zip |
| (exception) C031 SCL measurement, CSV v2 | M1 overlap | **Done** | SCL 98.8–99.6 kHz at 100 kHz on hardware; test_csv_format |
| (exception) **B30** ion bit slip under burst | B30 (new) | **Done** | before: fw 1.3 run 3 re-judged → LB-01 + LB-12 **fail** (§6.4); after: fw 1.6 G1/G2/H1/H2 → LB-12 400/400, ledger EXACT (§6.2) |
| (exception) **B31** ion 400 kHz | B31 (new) | **Not addressed — hardware limit** | §7.1 |

## 3. Files changed

The full per-file table with versions is in `change_log.md`: the entries dated 2026-09-30 to
2026-10-05 (cont. 6) and "Phase 1 close". Summary:

| Area | Files | Why |
|---|---|---|
| Loopback DUT (new, isolated) | `loopback_dut/**` (config, schema, patterns, firmware/App, host, tests, docs, runs) | P1-T1…T5 |
| C031 sniffer firmware | `embedded/sniffer_nucleoC0_fw/Core/{Inc,Src}/*` (fw 1.3 → 1.6), `build/`, `build_variants/`; `embedded/tests/host/*` | SCL measurement (exception); B30 fix (exception) |
| Sniffer host | `core/ion_protocol.py`, `core/ion_backend.py`, `core/i2c_controller.py`, `core/log_model.py`, `ui/log_panel.py`, `ui/common/capture.py`, `tools/validate_capture_csv.py`, `tools/ion_capture.py` (new) | CSV v2 / SCL column; headless capture tool |
| GUI harmonization | `ui/widgets/{connection_section,buttons}.py` (new), `ui/device_panel.py`, `ui/widgets/{serial_device_panel,serial_prefs_section,sidebar_sections,theme_picker}.py`, `ui/tabs/exit_tab.py`, `ui/sniffer_*window.py`, `ui/main_window.py`, `ui/sniffer_panel.py` | owner request 2026-10-05 |
| Fixture / docs | `i2c_decoders/loopback_dut_decoder.json`, `i2c_capture/loopback_dut_replay_check.csv`, `documents/*` guides, `embedded/docs/*`, `documents/phases/*` | rig decoder; documentation |
| Tests | `tests/test_ion_protocol.py`, `test_csv_format.py`, `test_neware_doc_conformance.py` (path fix), `test_loopback_dut_decoder.py`, `test_ion_capture.py` (new) | |

**Not in the phase file list:**
- all firmware and GUI files: the owner-directed exceptions above;
- `tests/test_neware_doc_conformance.py`: path fix, owner-approved, overlaps C9.

## 4. Verification performed

### 4.1 Test suites (2026-10-05, `.venv` Python 3.12.13)

    project: 19 pass, 0 fail                       (tests/test_*.py)
    smoke_test.py: 8/9 checks passed               (bq76905_gateway_tool missing — Phase 10)
    test_pattern_schema.py / test_host_model.py / test_loopback_harness.py: ALL TESTS PASSED
    loopback_dut/tests/host: === 40 checks, 0 failures ===  ALL LOOPBACK DUT HOST TESTS PASSED
    embedded/tests/host: === 86 checks / 92 checks / 22 checks, 0 failures ===  ALL HOST TESTS PASSED

Baseline at the start of the phase: 16/17 + neware path failure → fixed → 17/17; smoke 8/9.

### 4.2 Decoders

    OK i2c_decoders/{bq25731,bq76905,bq76922,loopback_dut,neware,smbus1v1,smbus1v1_host_notify,
       smbus3v3_ara,smbus3v3_arp,smbus3v3_host_notify}_decoder.json   (10/10 vs schema/decoder.schema.json)

### 4.3 Firmware builds from a clean tree (copies without `build/`, 2026-10-05)

    sniffer_nucleoC0_fw:  0 warnings;   5796  4  9892  15692  3d4c  build/sniffer_nucleoC0_fw.elf
                          cmp → identical to the tracked build/sniffer_nucleoC0_fw.bin
    loopback_dut/firmware: rc=0, 0 warnings; 39324  112  5064  44500  add4  build/firmware.elf
                          cmp → identical to loopback_dut/firmware/build/firmware.bin
    STM32_Programmer_CLI 2.23.0 -l st-link → NUCLEO-H533RE SN 003200273234511437333934,
                                              NUCLEO-C031C6 SN 066BFF544884654867102556

### 4.4 Rig status at close

`tools/ion_capture.py --status-only` → `probe: fw 1.6, mode bit-bang`.

## 5. Global passing criteria (master plan §5.2) and phase criteria (§5)

| # | Criterion | Met? | Note |
|---|---|---|---|
| 1 | No regressions | **Yes** | 19/19 (17 at baseline + 2 new), smoke 8/9 unchanged |
| 2 | Task criteria met with evidence | **Mostly** | P1-T3 B12 evidence missing (§7.3) |
| 3 | Every closed ID has a before/after test | **Yes (B30)** | harness self-test injects B30 → LB-12 fail; real runs before (§6.4) / after (§6.2) |
| 4 | smoke_test 9/9 | **No** | 8/9; `bq76905_gateway_tool` missing, Phase 10 (pre-existing) |
| 5 | All decoders validate | **Yes** | §4.2 (round trip is Phase 4 onward) |
| 6 | Round trip byte-stable | n/a | Phase 4 onward |
| 7 | Tags bumped, change log, docs synced, tree zipped | **Yes** | line-2 tag rule used (see §9 Q4); zip `ion_i2c_tool_phase01_v1.6.0.zip` |
| 8 | xfail ledger exact | **ion: Yes; AD2: No (1 xpass)** | AD2 run 3 LB-01 xpass = B32 intermittency (§7.2) |
| P5-3 | Full run on both paths with reports | **Yes** | ion §6.2 (fw 1.6), AD2 §6.3 (run 3) |
| P5-4 | Ledger has B8, B9, B10, B13 with matching reasons | **Yes** | handoff §4 |
| P5-5 | Both images build from a clean tree by documented commands | **Yes** | §4.3; `build_and_flash.md` §3 |
| P5-6 | Bench docs complete | **Yes** | P1-T6 files |
| P5-7 | **No review item fixed; no tool behaviour change** | **No, by owner direction** | changed: C031 SCL + CSV v2; C031 fw 1.4–1.6 (B30 fixed); GUI harmonization. Each was owner-directed and logged |
| P5-8 | Unexercisable cases listed with remediation | **Yes** | B10 not reproduced (§7.4); LB-13 ion (§7.1) |

## 6. Evidence appendix

### 6.1 DUT bench check (P1-T2, 2026-10-02)

Matches `setup_guide.md` §9.4 byte for byte, CRCs included, e.g.
`PH 1 0 1 SR 6B R A P 2 02 A0 *CB` (LB-01). The LB-09 36-byte block has checksum `0E`, and R2
returns base 0xB000. The first attempt failed for two wiring reasons: H533 GND not connected,
and PB12 on CN10-10 instead of pin 16.

### 6.2 ion report — fw 1.6, run `2026-10-05_H1`, judged with ledger v0.5 (`loopback_report_ion_ledger_v05.md`)

    - Verdicts: pass 11 · fail 0 · xfail 4 · xpass 0 · not exercisable 0
    - Ledger exact: YES
    | Case | Review IDs | Status | Verdict | Matched | Detail |
    | LB-01 | B32 | expect_pass | pass | 2/2 |  |
    | LB-02 | - | expect_pass | pass | 2/2 |  |
    | LB-03 | - | expect_pass | pass | 1/1 |  |
    | LB-04 | B8 | xfail | xfail | 1/1 | decode_mismatch |
    | LB-05 | - | expect_pass | pass | 1/1 |  |
    | LB-06 | B13, B32 | xfail | xfail | 2/2 | nak_on_normal_end_of_read |
    | LB-07 | B9, B32 | xfail | xfail | 2/2 | pec_invalid |
    | LB-08 | B9 | expect_pass | pass | 1/1 |  |
    | LB-09 | B10, B32 | expect_pass | pass | 3/3 |  |
    | LB-10 | B10, B32 | expect_pass | pass | 2/2 |  |
    | LB-11 | B10, B32 | expect_pass | pass | 2/2 |  |
    | LB-12 | B32 | expect_pass | pass | 400/400 |  |
    | LB-14 | B32 | expect_pass | pass | 2/2 |  |
    | LB-15 | B32 | expect_pass | pass | 8/8 |  |
    | LB-13 | B31, B32 | xfail | xfail | 0/5 | phase_missing, scl_missing |

G1, G2 and H2 give the identical summary.

### 6.3 AD2 report — run `2026-10-02_run3` (PEC on), judged with ledger v0.5 (`loopback_report_ad2_ledger_v05.md`)

    - Verdicts: pass 4 · fail 0 · xfail 10 · xpass 1 · not exercisable 0
    - Ledger exact: NO (unexpected pass)
    | LB-01 | B32 | xfail | xpass | 2/2 |  |
    | LB-02 | - | expect_pass | pass | 2/2 |  |
    | LB-03 | - | expect_pass | pass | 1/1 |  |
    | LB-04 | B8 | xfail | xfail | 1/1 | decode_mismatch |
    | LB-05 | - | expect_pass | pass | 1/1 |  |
    | LB-06 | B13, B32 | xfail | xfail | 1/2 | nak_on_normal_end_of_read, phase_extra, phase_missing |
    | LB-07 | B9, B32 | xfail | xfail | 1/2 | pec_invalid, phase_extra, phase_missing |
    | LB-08 | B9 | expect_pass | pass | 1/1 |  |
    | LB-09 | B10, B32 | xfail | xfail | 2/3 | phase_extra, phase_missing |
    | LB-10 | B10, B32 | xfail | xfail | 1/2 | phase_extra, phase_missing |
    | LB-11 | B10, B32 | xfail | xfail | 1/2 | phase_extra, phase_missing |
    | LB-12 | B32 | xfail | xfail | 252/400 | phase_extra, phase_missing |
    | LB-14 | B32 | xfail | xfail | 1/2 | phase_extra, phase_missing |
    | LB-15 | B32 | xfail | xfail | 5/8 | phase_extra, phase_missing |
    | LB-13 | B31, B32 | xfail | xfail | 3/5 | phase_extra, phase_missing |

LB-01's only Sr-terminated write escaped B32 in this run (~75 % hit rate per phase). Run 2 was
exact under the then-ledger but had no PEC results.

### 6.4 B30 before / after

- **Before:** fw 1.3, run 3, re-judged with ledger v0.5 (B30 closed):
  - `ion: pass 9 fail 2 …`;
  - LB-01 `data_mismatch … expected 2 B [02 A0], captured 2 B [04 41]`;
  - LB-12 `fail 397/400 …`.

  fw 1.3 runs 1–3 had 9 / 14 / 21 LB-12 slip lines.
- **After:** fw 1.6, four runs (G1, G2, H1, H2): 0 FRAMING, LB-12 400/400 exact each time.
- **Root cause, measured:**
  - With AD2 logic-analyser timing and C031 trace pins (`loopback_dut/runs/2026-10-05_NOTES.md`),
    the bus is clean: SCL high ≥ 4.92 µs, no stretch.
  - The polled decode pass took 3.1–5.8 µs per edge.
  - Moving sampling into an EXTI edge interrupt removed the misses.

## 7. NOT ADDRESSED — remediation instructions

### 7.1 B31 — ion sniffer cannot capture 400 kHz

**What was expected:** LB-13 (5 phases at 400 kHz) captured.

**What happened instead:** every fw version captures 0/5. With fw 1.6 the trace shows:
- ISR 0.58 µs without a push, 1.37 µs with one (1.23 µs from RAM);
- entry latency up to 0.9 µs;
- edges ~0.8 µs apart;
- tHD;STA ~0.6 µs, shorter than the sampling delay, so every START is missed.

**Why it was not done:** it is a hardware limit of the 48 MHz Cortex-M0+. The owner decided to
move the probe to a faster MCU (NUCLEO-H723ZG or H743ZI2).

**Risk of leaving it:** users on 400 kHz buses see no rows. The user guide now says to use the
AD2 for 400 kHz.

**Instructions to close it:**
1. Once the new board is chosen, port `sniffer_nucleoC0_fw` to it. Keep `i2c_bitbang_decoder.c`,
   `edge_ring.h` and `frame_protocol.c` unchanged; they are host-tested.
2. Prefer timer-triggered DMA sampling of the GPIO IDR into a circular buffer at ≥ 4 MS/s, or a
   timer input-capture on both lines. Do not use a CPU poll loop.
3. Update `core/ion_backend.py` port detection for the new ST-LINK, and the user guide.

**Test to add:** the existing loopback run with LB-13 `path_status.ion` changed to
`expect_pass`, as `test_b31_ion_400k`. It must xfail on C031 fw 1.6 and pass on the new probe.

**Passing criteria:**
- LB-13 5/5 on ion;
- measured SCL within 2 % of 401 204 Hz;
- ledger exact.

**Estimated size:** large. **Suggested phase:** dedicated, "probe MCU migration".

### 7.2 B32 intermittency — the AD2 ledger cannot be exact on every run

**What was expected:** ledger exact on both paths.

**What happened instead:** B32 hits ~75 % of Sr-terminated writes, so a case with one such
write sometimes passes. The ledger then reports an xpass: run 3, LB-01, §6.3.

**Why it was not done:** it needs an owner decision on ledger semantics (handoff §7).

**Risk of leaving it:** a random "ledger NOT EXACT" on AD2 runs hides real regressions in
noise.

**Instructions to close it:**
1. In `loopback_dut/schema/loopback_pattern.schema.json`, allow `path_intermittent: {ad2: true}`
   on a case.
2. In `loopback_dut/host/loopback_compare.py`, give such a case `pass` instead of `xpass` when
   no symptom appears. Keep `fail` for unlisted kinds.
3. Set it on the B32 cases.

**Test to add:** `test_intermittent_xfail_no_xpass` in `loopback_dut/tests/test_loopback_harness.py`:
- the perfect AD2 capture gives `pass` on intermittent cases and the ledger stays exact;
- an unlisted symptom still gives `fail`.

**Passing criteria:** AD2 run 3 re-judged → ledger EXACT. Harness self-test still catches all
mutations.

**Estimated size:** small. **Suggested phase:** 5 (or earlier, if the owner approves).

### 7.3 P1-T3 B12 desync evidence not produced

**What was expected:** the driver detects a request/response desync on `IonMasterLink` (B12).

**What happened instead:** the DUT driver uses its own link (`loopback_dut/host/dut_link.py`,
sequence-numbered and CRC-checked). DUT isolation forbids importing `core.ion_master`.

**Instructions to close it:** in Phase 5, add `tests/test_b12_ion_master_desync.py`:
- drive `core.ion_master.IonMasterLink` against a fake serial that drops one response;
- assert the next call raises or flags a desync instead of returning the stale reply.

It must fail before the B12 fix and pass after.

**Passing criteria:** the test passes and its fail-before is recorded. **Size:** small.
**Phase:** 5.

### 7.4 B10 not reproduced on hardware

**What was expected:** AD2 truncates long reads (LB-09/10/11).

**What happened instead:** runs 2 and 3 captured the 36, 64 and 80-byte reads complete at
100 kHz. The cases stay AD2-xfail only because B32 corrupts them.

**Instructions to close it:** in Phase 5, before fixing B10:
1. Add a pattern case reading 128–256 bytes at 400 kHz and at 100 kHz to find the real
   truncation boundary.
2. If it still cannot be reproduced, downgrade B10 to "not reproducible" with this evidence.

**Size:** small. **Phase:** 5.

### 7.5 smoke_test 8/9

`bq76905_gateway_tool` is missing (pre-existing). Close it in Phase 10 per the master plan:
restore the module, or remove the entry together with its doc and guide.

### 7.6 Version-tag position rule

The master plan says line-1 tags; the project-conventions skill and the existing files use
line 2. This phase followed line 2. Close it in Phase 2's tag baseline: pick one rule, update
the master plan or the files, and add a check to the runner.

## 8. New findings (not in the original review)

| New ID | Sev | Issue | Where found | Recommended fix | Files |
|---|---|---|---|---|---|
| B29 | Med | a `data_bytes: 2` rule fed a 1-byte payload renders a fabricated value (`R1 word 0x02 = 0x0002`) instead of absent | loopback decoder test | decode engine must render absent on short payloads (Phase 4) | `core/decode_schema.py` |
| B30 | High | ion bit slip under burst at 100 kHz (missed address-ACK clock) | runs 1–3 | **fixed** in fw 1.6 (owner exception) | sniffer fw |
| B31 | High | ion captures nothing at 400 kHz; fw ≤ 1.5 also left garbage that corrupted the next case | runs 1–3 | §7.1 | sniffer fw / new MCU |
| B32 | High | AD2 exports a Sr-terminated write as `0x00 W [00]` (~75 %) | runs 2–3 | Phase 5 (AD2 host code) | `core/i2c_controller.py` spy path |
| F-1 | Low | skill tool `make_replay_check.py` puts every rule of a multi-address decoder on the file-level address; `validate_decoder.py` tool-load fails for every shipped decoder | decoder work | fix in the skill, not this repo | skill scripts |
| F-2 | Low | capture CSV v2 has no overflow column, so the ion OVERFLOW flag on LB-11 (80 B > 64) is invisible to the harness | LB-11 | add a column in M1 (Phase 6) | `core/log_model.py`, CSV doc |
| F-3 | Low | `i2c_capture/EVM_*.csv` use an 11-column legacy layout that fails v1 and v2 validation | CSV v2 work | legacy reader (M1, Phase 6) | `ui/common/capture.py` |

All open items appear in §7 or are assigned to the phases named.

## 9. Questions for the senior designer

1. **Accept the owner-directed behaviour changes** (C031 SCL + CSV v2, fw 1.4–1.6, GUI
   harmonization) inside Phase 1? Recommendation: yes. Each one is logged with before/after
   evidence, and they are what made the instrument trustworthy on the ion path.
2. **Intermittent-symptom ledger** (§7.2): approve now or in Phase 5? Recommendation: now. It
   is small, and it makes every future AD2 run judgeable.
3. **B31 home:** a dedicated "probe MCU migration" phase once the H723ZG/H743ZI2 arrives?
   Recommendation: yes. Keep the C031 as the supported 100 kHz probe until then.
4. **Tag position:** confirm line 2 (recommendation: line 2, so shebangs and opening comments
   keep line 1).
