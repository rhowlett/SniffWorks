# Phase 1 — I2C Loopback DUT + Capture Verification Harness

**Read first:** `00_MASTER_PLAN.md` (§3 session protocol, §5 test policy, §6 ground rules).
This is the **first session**, so there is no previous handoff; there is no `CLAUDE.md` yet
and you will create it.

---

## 1. Why this phase exists

Every capture-path bug in the review (B8–B13) is a claim about what the tool *should* have
recorded. Today there is no way to prove any of them, because the only reference is the
tool's own output. This phase builds a **deterministic traffic source** and a harness that
compares a sniffer capture against exactly what was emitted, case by case.

The output is a measuring instrument, not a fix. **Do not fix any review item in this
phase** (master plan D-06). When the rig exposes a bug, record it as an expected failure
with its review ID. Phase 5 flips those to passing — that is the proof the fixes worked.

---

## 2. Open questions — resolve before coding

Ask the project owner. Do not guess; the hardware topology changes the firmware design.

1. **Board count.** The design below assumes: probe A = sniffer under test (AD2 or Nucleo in
   sniff mode), probe B = Nucleo running the existing `SNIFF_MODE_MASTER` firmware as the
   pattern *driver*, board C = new Nucleo running the **DUT responder** firmware (I2C slave).
   Is a third board available, or must the driver and responder share one board?
2. **Slave capability.** Confirm against RM0490 / the STM32C031C6 datasheet how many I2C
   peripherals the board exposes and whether a hardware I2C **slave** with clock stretching
   is available on pins that do not collide with `SNIFF_SCL_PIN` (PA9) / `SNIFF_SDA_PIN`
   (PA10). If only one peripheral exists, driver and responder cannot share a board and
   question 1 is answered for you. **Report what you find before designing around it.**
3. **Bus electricals.** Pull-up values and supply for the rig (the responder board, the
   driver board and the sniffer share SCL/SDA/GND). State the intended value and confirm.
4. **Address plan.** Proposed: responder ACKs `0x08` (mirrors the BQ76905/BQ76922 address so
   the shipped decoders apply) and `0x6B` (mirrors BQ25731); `0x55` is left unclaimed to
   generate deliberate address-NAK cases. Confirm or amend.
5. **Speeds.** Proposed cases at 100 kHz and 400 kHz. Confirm 400 kHz is in scope for the
   sniffer firmware's bit-bang decoder.

Record the answers as decisions in `CLAUDE.md` and in the change-log entry.

---

## 3. Architecture to build

```
   ┌─────────────────┐        ┌──────────────────────┐
   │ Host (Python)   │        │  Probe B: Nucleo     │
   │ tools/loopback_ │ USB    │  SNIFF_MODE_MASTER   │   drives the bus
   │   run.py        ├───────►│  (existing firmware) ├───┐
   │ core.ion_master │        └──────────────────────┘   │
   └────────┬────────┘                                   │  SCL/SDA/GND
            │ writes expected.json                       │
            │                                   ┌────────┴─────────┐
            │                                   │  Board C: DUT    │
            │                                   │  responder fw    │  ACKs, serves a
            │                                   │  (NEW, I2C slave)│  synthetic reg map
            │                                   └────────┬─────────┘
            │                                            │
            │  captured.csv          ┌───────────────────┴──────┐
            └────────────────────────┤ Probe A: sniffer under   │
              tests/test_loopback_   │ test (AD2 or ion probe)  │
              capture.py compares    └──────────────────────────┘
```

The host knows **exactly** what it asked probe B to emit, so `expected.json` is ground truth
independent of the sniffer path being tested. That is the whole point: never compare the
tool against itself.

---

## 4. Tasks

Work in order. Each task lists files and passing criteria. Bump the line-1 version tag of
every file you touch (create at `v0.1` if absent) — including the firmware C files.

### P1-T0 — Session bootstrap
- Create `CLAUDE.md` at the project root using the **project-context-update** skill
  (six sections: Findings, Decisions, Tradeoffs, Gotchas, Current State, Open Questions;
  version tag on line 2; revision-history line).
- Seed it with: the program decisions D-01…D-06 from the master plan, the answers to §2,
  and the baseline test result you measure in the next step.
- Run every `tests/test_*.py` and `tests/smoke_test.py` with `QT_QPA_PLATFORM=offscreen`.
  **Expected baseline:** all 16 `test_*.py` pass; `smoke_test.py` reports 8/9 (missing
  `bq76905_gateway_tool`); two tests inside `test_bq25731_decoder.py` silently skip because
  they look for a capture under `/mnt/user-data/uploads/`. Record the actual result. If it
  differs from this, stop and report before continuing.

**Passing:** `CLAUDE.md` exists and is populated; baseline recorded verbatim in the handoff.

---

### P1-T1 — Pattern format and golden pattern v1

Define the traffic pattern as data, not code, so new cases need no new Python.

- Create `schema/loopback_pattern.schema.json` — a JSON Schema for the pattern file.
  Apply the lesson from review item **B1**: every conditional `if` block must carry
  `required` naming the property it tests, or it passes vacuously on files that omit the key.
- Create `tests/patterns/loopback_v1.json`. Each case has: `id`, `description`, `address`,
  `op` (`write` | `read` | `write_read`), `data` / `read_len`, `speed_khz`, `pec` (bool),
  `expect` (the transaction phases the sniffer should record), `review_ids` (which review
  items this case exercises), and `status` (`expect_pass` | `xfail`).

**Cases that must be present** (these are the ones that pay for the rig):

| Case ID | What it emits | Exercises | Initial status |
|---|---|---|---|
| `LB-01` | 1-byte pointer write + repeated-start read, 2 bytes | baseline indexed_read pairing | expect_pass |
| `LB-02` | 1-byte pointer write + STOP, then plain read | stop-separated pointer style (BQ25731 host style) | expect_pass |
| `LB-03` | indexed write, register + 2 data bytes | indexed_write | expect_pass |
| `LB-04` | **single-byte write with STOP, no read follows** | **B8** — the unreachable simple-write branch | **xfail (B8)** |
| `LB-05` | write to the unclaimed address (address NAK) | NAK classification, scan behaviour | expect_pass |
| `LB-06` | read of 4 bytes ending in the master's final-byte NAK | **B13** — normal end-of-read NAK shown as an error | **xfail (B13)** |
| `LB-07` | SMBus read-word with PEC over the full combined transaction | **B9** — PEC computed over the wrong bytes | **xfail (B9)** |
| `LB-08` | SMBus write-byte with PEC | B9 (write side) | expect_pass or xfail per observation |
| `LB-09` | 36-byte block read starting at 0x3E (subcommand frame shape) | **B10** — spy continuation segments discarded | **xfail (B10)** |
| `LB-10` | 64-byte read (at `TXN_MAX_DATA`) | boundary, no truncation | expect_pass |
| `LB-11` | 80-byte read (**over** `TXN_MAX_DATA`) | documents the truncation limit; the flag must say so | expect_pass (flag asserted) |
| `LB-12` | burst of 200 back-to-back transactions | overflow/dropped flags, no silent loss | expect_pass |
| `LB-13` | the same pattern at 400 kHz | speed coverage | expect_pass |
| `LB-14` | responder clock-stretches ~200 µs mid-byte | stretch tolerance | expect_pass |
| `LB-15` | traffic interleaved across both responder addresses | multi-device routing | expect_pass |

Mark an `xfail` only with its review ID and a one-line reason. If a case you expected to
fail passes, that is a **finding** — record it; do not quietly change the ledger.

**Passing:** the pattern file validates against its schema; every case carries `review_ids`;
the four xfail cases above are present with their IDs.

---

### P1-T2 — DUT responder firmware

Create `embedded/loopback_dut_fw/` following the **project-structures** embedded template
(`Core/Inc`, `Core/Src`, `Core/Startup`, `Drivers`, `build`), reusing the existing project's
LL drivers and `Makefile` shape from `embedded/sniffer_nucleoC0_fw/`.

Behaviour:
- ACK the two configured 7-bit addresses (§2 Q4); NAK everything else.
- Serve a **synthetic register map**: register N returns a deterministic function of N
  (document the function — e.g. `value = 0xA000 + N`) so any byte-order or off-by-one error
  in the host is immediately visible in the decoded value.
- Support the block-read shape used by `LB-09`: echo at 0x3E/0x3F, 32-byte buffer at
  0x40–0x5F, checksum at 0x60, length at 0x61, matching the framing already implemented in
  `DecodeSchema._unwrap_subcommand_block`.
- A compile-time or command-selectable **clock-stretch injection** for `LB-14`.
- A GPIO output usable as an **ALERT assert** for Phase 11 (wire it, do not use it yet).
- Guarded configuration defines at the top of `Core/Inc/loopback_config.h`, each with a
  one-line comment saying when to change it.

**Passing:** builds with `make` to `.elf/.hex/.bin`; a host-side unit test of the register
map function exists (T1, no hardware); flashed board ACKs its addresses and returns the
documented values for at least `LB-01`, `LB-03`, `LB-09` (evidence: captured bytes pasted
into the review document).

---

### P1-T3 — Host pattern driver

Create `tools/loopback_run.py`:
- Opens probe B with `core.ion_master.open_master(...)` (it already raises a bench-actionable
  error when the firmware variant is wrong).
- Reads a pattern file, emits each case in order, and writes `expected.json`: for every case,
  the phases the bus actually carried (address, direction, bytes, start/restart/stop, the
  NAK the *master* observed) plus the host timestamp.
- **Guard against review item B12** while using it: this driver is the first serious user of
  `IonMasterLink`, and a late reply after a link timeout is attributed to the next command.
  Do not fix B12 here; instead, make the driver detect the desync (sequence mismatch between
  the case it sent and the phases it got back), abort the run, and report which case desynced.
  That report is evidence for Phase 5.
- `--dry-run` produces `expected.json` from the pattern with no hardware, for harness testing.

**Passing:** `--dry-run` produces a schema-valid `expected.json` for `loopback_v1.json`;
with hardware, a full run completes and reports per-case emit status.

---

### P1-T4 — Comparison harness

Create `tests/test_loopback_capture.py` (tier **T2**) plus `core/loopback_compare.py` (pure
logic, no Qt, so it is unit-testable):
- Inputs: a captured CSV from the sniffer under test and `expected.json`.
- Aligns captured transactions to expected phases (align on address + direction + payload;
  allow bounded timestamp skew; never assume equal counts — a missing transaction is the
  most important failure mode).
- Per case, produces a verdict: `pass`, `fail` (with a byte-level diff), or `xfail` when the
  case is marked xfail and the observed failure matches the recorded reason.
- Emits `loopback_report.md`: a table of case ID, review IDs, verdict, and the diff for any
  failure — this file is the evidence you paste into the phase review.
- **The ledger is exact** (master plan §5.2.8): unexplained failures and unexpected passes
  both fail the suite.

Run it for **both** sniffer paths: AD2 (`sniffer_ad2`) and the ion probe (`sniffer_ion`), and
report both. They will differ — B10 is AD2-specific, B11 is ion-specific.

**Passing:** the harness produces a report for both capture paths; every non-xfail case
passes on at least one path, or is promoted to a new finding with a review ID you assign
(`B29`, `B30`, … — continue the review's numbering and describe each in the review document).

---

### P1-T5 — Harness self-test (no hardware)

Create `tests/test_loopback_harness.py` (tier **T1**):
- Synthesises a capture CSV from an `expected.json` (perfect capture) → every case passes.
- Then mutates it deliberately and asserts the harness catches each mutation:
  a dropped transaction, a truncated payload (simulating B10), a flipped PEC column,
  a reordered pair, an extra spurious transaction.

This is the test that keeps the instrument honest. Without it, a harness bug looks like a
clean bill of health for the tool.

**Passing:** all five mutations detected; perfect capture reports zero failures.

---

### P1-T6 — Bench documentation

- `embedded/docs/build_and_flash.md` — **mandatory** per the project conventions and
  currently missing from the project entirely. Write it for someone who has never seen the
  project: toolchain and versions, probe/adaptor hardware, every supported build path
  (make / STM32CubeIDE / CubeProgrammer CLI / drag-and-drop to the mass-storage volume),
  OS-specific quirks, and the power-up ritual. Cover both firmware images
  (`sniffer_nucleoC0_fw`, `loopback_dut_fw`).
- `documents/loopback_dut_bringup.md` — the rig: wiring diagram (which pins, which grounds),
  pull-up values, which board gets which firmware, how to run `tools/loopback_run.py`, how
  to capture with each sniffer, how to read `loopback_report.md`, and a troubleshooting list
  (no ACK, no HELLO, wrong firmware variant, bus stuck low).
- Mark every value you measured on *this* rig as measured-on-this-unit, not universal.

**Passing:** a person with the hardware and no prior knowledge can follow the document from
unpacking to a report; the reviewer confirms every step has a concrete expected result.

---

### P1-T7 — Close the session

Follow master plan §3.3. Deliver: the zipped tree, the change-log entry (with the loopback
report cited as evidence), `documents/phases/HANDOFF_PHASE_01.md`, and
`documents/phases/REVIEW_PHASE_01.md`.

The handoff must carry forward, at minimum: the resolved §2 answers, the exact rig topology,
the xfail ledger as it stands, any new review IDs you assigned, and the baseline test result.

---

## 5. Phase 1 passing criteria (the reviewer checks these)

1. All master-plan §5.2 global criteria hold.
2. `tests/test_loopback_harness.py` passes headless, including all five mutation cases.
3. A full loopback run exists for **both** the AD2 and ion capture paths, with
   `loopback_report.md` for each pasted into the review document.
4. The xfail ledger contains **at least** B8, B9, B10, B13 with case IDs, and each xfail
   reason matches the observed failure mode — not merely "fails".
5. Both firmware images build from a clean tree by the documented commands.
6. `embedded/docs/build_and_flash.md` and `documents/loopback_dut_bringup.md` exist and are
   complete enough that the reviewer could rebuild the rig from them alone.
7. **No review item was fixed.** If any tool behaviour changed, that is a defect in this
   phase; call it out.
8. Any case that could not be exercised (missing board, speed unsupported, stretch not
   reproducible) is listed in the review document with remediation instructions, not
   silently dropped from the pattern file.
