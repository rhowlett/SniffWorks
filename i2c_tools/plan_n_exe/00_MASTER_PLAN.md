# ion_i2c_tool — Remediation & Launcher Program: Master Plan

**Audience:** Claude Code (one phase per session) and the senior designer reviewing each phase.
**Source of findings:** `ion_i2c_tool_review.md` (10 missing pieces, 28 bugs, 12 consistency
issues, 9 refactors). Every task in every phase carries the review ID it closes.

**Read this file first in every session**, then the phase document for the phase you are
executing, then the handoff document from the previous phase.

---

## 1. Program decisions (already made — do not re-litigate)

| ID | Decision | Rationale |
|---|---|---|
| D-01 | The master launcher starts each app as a **subprocess**, not in-process. | Crash isolation: `i2c_controller` drives DWF through ctypes; a segfault must not take down every window. |
| D-02 | **Sniffer apps may run in multiple instances** (practical cap = number of available probe/COM ports). All other apps are **single-instance**: a second launch focuses the existing window. | One sniffer per probe is a real workflow; two decoder editors on the same file is not. |
| D-03 | Hardware is available for verification: **AD2 + Nucleo probes**. A dedicated **I2C loopback DUT** is built first (Phase 1) so every capture-path fix has a deterministic ground truth. | "Measured beats documented beats assumed." |
| D-04 | Tree restructure (C3), the missing gateway app (M3), master mode + ALERT (M9), and Windows support (M10) are each **their own phase**, not folded into other work. | Each is a scope decision with its own risk profile. |
| D-05 | Loopback cases that fail because of a *known, not-yet-fixed* review item are recorded as **expected failures (xfail) in a ledger**, not deleted or skipped. Later phases flip them to expected-pass. | The suite doubles as the proof that each fix worked. |
| D-06 | No review item is fixed outside its assigned phase. If you spot something new, **record it** in the phase review document; do not fix it. | Keeps phases reviewable and context bounded. |

Open decisions that a phase must close are listed in that phase's document under
**Open questions — resolve before coding**. Do not guess; ask the project owner.

---

## 2. Phase order

Ordering rule: build the measuring instrument, then the workbench, then fix in review-priority
order (data loss → capture correctness → schemas → UI), then extensibility, then scope items.

| Phase | Title | Closes | Depends on | Size |
|---|---|---|---|---|
| **1** | I2C Loopback DUT + capture verification harness | (new capability); arms xfail ledger for B8–B13 | — | Large |
| **2** | Repo foundations, conventions, test harness | C2, C3, C6, C7, C8, C9, R9 (runner) | 1 | Medium |
| **3** | Master launcher | (new capability); C4 (naming registry), M3 groundwork | 2 | Medium |
| **4** | Decoder editor & decoder-schema data loss | B1, B2, B3, B4, B5, B6, B7, M2, M5 | 2 | Large |
| **5** | Capture-path correctness | B8, B9, B10, B11, B12, B13 | 1, 2 | Large |
| **6** | CSV capture schema & I/O | M1, B14, B15, B16, B17 | 4, 5 | Medium |
| **7** | Dashboard (Registers view) | B18, B19, B20, B21, B22, B23, M6, M7 | 4 | Medium |
| **8** | Decode-engine extensibility | M8, R4, R5, R6 | 4, 5 | Large |
| **9** | Architecture refactor | R1, R2, R3, R7, R8 | 3, 5, 8 | Large |
| **10** | Gateway app: resolve or remove | M3 | 2, 3 | Small |
| **11** | Master mode + ALERT | M9 | 1, 5, 9 | Medium |
| **12** | Windows support | M10 | 2, 3 | Medium |
| **13** | Hand-tool board support | M4 | 1, 5, 9 | Medium |

A phase marked **Large** is expected to need a split. See §4.

---

## 3. Standard session protocol (every phase, no exceptions)

### 3.1 Start of session

1. Read, in order: this file → `PHASE_NN_*.md` → `HANDOFF_PHASE_<NN-1>.md` → `CLAUDE.md`.
2. Invoke the **project-conventions** skill and keep it active for the whole session.
   Invoke **project-structures** when creating folders, and **project-context-update**
   when writing `CLAUDE.md`.
3. Unzip / open the current project tree. Run the full test suite **before** changing
   anything and record the baseline result in the handoff document. If the baseline
   does not match what the previous handoff claimed, stop and report.
4. Restate the phase's scope and the open questions. If an open question is unresolved,
   ask the project owner before writing code.

### 3.2 During the session

- Work task by task in the order given. Each task states its review IDs, its files, and
  its passing criteria.
- **Every file you touch**: bump its line-1 version tag (`# vX.Y` / `/* vX.Y */`),
  minor +1, creating the tag at `v0.1` if absent.
- **Edit verification is non-negotiable.** After each batch: `grep -c` that each new
  symbol is defined exactly once, that references resolve, that structural balance holds,
  and that new code is actually called. Show the verification output.
- Never claim an edit is applied without reading it back from disk.
- If a fix requires touching a file outside the phase's file list, say so explicitly in
  the review document with the reason.
- Update `CLAUDE.md` at every milestone, decision, finding, or gotcha (the
  **project-context-check** skill defines the triggers).

### 3.3 End of session — four deliverables, always

1. **The zipped project tree** — full, current, versions bumped, change log updated.
2. **`documents/change_log.md` entry** — files, versions, what changed, why, with evidence
   (test output, capture, measurement) for every decision closed.
3. **`HANDOFF_PHASE_NN.md`** — the context summary that lets a fresh session start the next
   phase cold. Use `TEMPLATES.md` → Handoff template. It must be self-contained: assume the
   next session has read nothing but the master plan and the next phase document.
4. **`REVIEW_PHASE_NN.md`** — the senior-designer review document. Use `TEMPLATES.md` →
   Phase review template. It must state, per task: what was done, what evidence proves it,
   **what was not addressed and why**, and — critically — **ready-to-paste Claude Code
   instructions to close each unaddressed item**. A phase is not finished until an item is
   either fixed with evidence or has remediation instructions written for it.

Put the handoff and review documents in `documents/phases/`.

---

## 4. Context budgeting and splitting

Target: no session should exceed roughly **60% of the model's context window** before it
starts writing its end-of-session documents, because those documents are the part that must
not be rushed.

**Split a phase when any of these is true:**

- more than ~8 tasks, or ~15 files to modify;
- more than ~1,500 lines of new or rewritten code;
- a task requires reading a file larger than ~1,000 lines in full (e.g. `decode_schema.py`
  at 1,045 lines, `decode_editor.py` at 847);
- you have consumed ~60% of context and more than a third of the tasks remain.

**How to split, mid-session:**

1. Stop at the nearest task boundary — never mid-task, never with an unverified edit.
2. Write `PHASE_NN-B_<title>.md` in the same format as the phase document you are executing,
   containing only the remaining tasks, with any new context they need folded in.
3. Write the handoff and review documents for the work actually completed (`NN-A`).
4. Deliver the zip. The next session starts on `NN-B`.

The **project-splitter** skill packages a clean handoff if the split is awkward.

---

## 5. Test policy and global passing criteria

### 5.1 Structure

- Tests live in `tests/`. Phase 2 converts the current standalone scripts to **pytest**
  and adds `tools/run_tests.sh` as the single entry point. Until then, run every
  `tests/test_*.py` and `tests/smoke_test.py` individually with
  `QT_QPA_PLATFORM=offscreen`.
- Every test is one of three tiers, and every new test declares its tier:
  - **T1 headless** — no hardware, runs in CI and in every session. The default.
  - **T2 loopback** — needs the Phase 1 DUT rig. Skipped automatically when the rig is
    absent, but a skip is **reported loudly** in the summary line, never silent.
  - **T3 bench** — manual procedure with a written checklist and expected values.
- A skip must never be counted as a pass. Phase 2 makes the runner fail if a T1 test skips.

### 5.2 Passing criteria that apply to every phase

A phase passes only when all of the following hold:

1. **No regressions.** Every test that passed at the session baseline still passes.
2. **Each task's own passing criteria are met**, with the evidence pasted into the review
   document (test output, capture excerpt, or measurement — not prose).
3. **Every review ID claimed closed has a test that fails before the fix and passes after.**
   Show both runs. An ID with no such test is not closed; it is "changed, unverified".
4. **`tests/smoke_test.py` reports 9/9** — or the missing entry has been formally removed
   in Phase 10 with the doc and guide removed in the same pass.
5. **All `i2c_decoders/*.json` validate** (ten files as of 2026-09-30, incl. the loopback DUT fixture) against `schema/decoder.schema.json`,
   before *and* after a load→save round trip through `DecodeSchema`.
6. **No silent data loss**: a load→save round trip of every shipped decoder is byte-stable
   apart from formatting (Phase 4 onward).
7. **Conventions hold**: every touched file's line-1 tag bumped, change-log entry written,
   affected docs updated in the same pass, full tree zipped.
8. **The xfail ledger is exact**: every expected failure is listed with its review ID, and
   there are no unexplained failures and no unexpected passes. An unexpected pass means the
   ledger is stale — investigate before celebrating.

### 5.3 Writing a test for a bug fix

For each bug ID, the test must assert the *behaviour*, not the implementation:

- name it `test_<review_id>_<short_description>` (e.g. `test_b09_pec_spans_combined_transaction`);
- include a one-line docstring quoting the review item;
- construct the smallest input that reproduces it (a synthetic `I2CTransaction` list, a
  4-line CSV, a 2-rule decoder) rather than depending on the large shipped files;
- assert the exact expected output, not merely "no exception".

---

## 6. Ground rules

- **Do not fix items outside the current phase** (D-06). Record them instead.
- **Do not delete a test to make a suite green.** Mark it xfail with its review ID.
- **Do not change file formats without updating both schemas and the round-trip tests.**
- **Authority ranking for conflicts:** measured bus capture > device datasheet/TRM by
  document number > this review > existing code comments > `documents/ARCHITECTURE.md`
  (which is already known to be partly aspirational).
- **The review document is written for a human who was not in the session.** No "as
  discussed", no references to conversation, no unexplained IDs.

---

## 7. Phase scope summaries

Full instructions live in each `PHASE_NN_*.md`. These summaries exist so a reviewer can
see the whole arc, and so a phase author knows what is deliberately *not* theirs.

### Phase 1 — I2C Loopback DUT + capture verification harness
Build a deterministic traffic source (Nucleo DUT responder + host-driven master) and a
harness that compares a sniffer capture against the known-emitted pattern, per case.
Arms the xfail ledger for B8, B9, B10, B13. Full document: `PHASE_01_loopback_dut.md`.

### Phase 2 — Repo foundations, conventions, test harness
Baseline line-1 version tags on every source file; move the change log to
`documents/change_log.md`; restructure the tree to the project-structures template (C3);
delete the 7 deprecated shims after repointing imports (C6); remove dead modules and stale
backups (C7); strip `__pycache__`, `.DS_Store`, firmware `build/` from deliverables and add
`.gitignore` (C8); regenerate `MANIFEST.sha256`; fix the two tests that point at
`/mnt/user-data/uploads/` (C9); theme-token the hard-coded colours (C10); convert tests to
pytest and add `tools/run_tests.sh` (R9 runner only — new test cases belong to their own
phases). **Not in scope:** any behaviour change.

### Phase 3 — Master launcher
New entry point (`ion_i2c_tool.py`) plus an app registry in `ui/common/app_info.py`
(module, class, entry script, single-instance flag). Subprocess launch per D-01; the
launcher tracks children, reaps exits, and shows live status per app. Sniffers may be
launched N times, bounded by available probes/COM ports; all other apps focus their existing
window instead of spawning (D-02) — which requires a single-instance mechanism (lock file or
a local socket) inside the child apps. The registry becomes the single source of truth for
"what apps exist", replacing the three separate lists in `smoke_test.py`,
`documents/ARCHITECTURE.md` §1, and the Help tab. **Not in scope:** fixing the apps
themselves; the gateway app (Phase 10).

### Phase 4 — Decoder editor & decoder-schema data loss (highest review priority)
B1 (schema `if` blocks need `required`), B2 (save drops top-level metadata), B3 (empty
`bit_fields` dropped → invalid file), B4 (Add/Update wipes `description`/`fields`; 13 bq25731
bit fields destroyed by comma parsing), B5 (subcommand rows unselectable/unremovable), B6
(`subcommand_reg` default mismatch), B7 (evaluator DoS + uncaught `TypeError`), M2 (validate
on load and save), M5 (editor reaches the whole schema: transaction type, subcommand, fields,
descriptions, register width). The **i2c-decoder-generator** skill is relevant when
regenerating or extending decoder content. **Not in scope:** decode-engine behaviour (Phase 8).

### Phase 5 — Capture-path correctness
B10 (AD2 `spy_poll` discards continuation segments — truncates the very block reads this
tool exists to decode), B9 (SMBus PEC computed over the wrong bytes for combined
transactions), B11 (IonWorker drain exits immediately, loses final frames), B12
(IonMasterLink desync after a link timeout), B13 (normal end-of-read NAK rendered as an
error — move frame grouping off NAKs at the same time), B8 (single-byte simple-write branch
unreachable). Every fix is proven against the Phase 1 rig: the matching xfail case flips to
pass. **Not in scope:** CSV format changes (Phase 6).

### Phase 6 — CSV capture schema & I/O
M1 (`schema/capture.schema.json` + a parsable versioned header line, with a v0 reader for
the two legacy layouts already in `i2c_capture/`), B14 (export all rows by default; filtered
export explicit and recorded in the header), B15 (ISO 8601 + microseconds, plus the raw
device µs counter), B16 (machine-readable PEC instead of ✓/✗ glyphs), B17 (report skipped
rows; validate on load). Round-trip test: capture → export → import → identical decode
output, run against a Phase 1 loopback capture.

### Phase 7 — Dashboard (Registers view)
B18 (cache key includes transaction type, so writes never update the row), B19 (two decoders
on one address cross-contaminate — bq76905 and bq76922 are both 0x08), B20 (bit matrix caps
at 2 bytes), B21 (`.4g` formatting produces `1.235e+04`), B22 (bit labels show the enum value
name, not the field name), B23 (multi-bit fields coloured as 24-bit RGB), M6 (user-level
dashboard layout separate from the device decoder, plus staleness indication), M7 (reload
decoders when the editor saves).

### Phase 8 — Decode-engine extensibility
M8 (`general_call`, `device_id_query`, `split_transaction` are declared but never produced;
`register_width_bytes` is parsed but ignored), R4 (the TI BQ769x subcommand protocol is
hard-coded in the generic engine — make it a data-driven `subcommand_protocol` block),
R5 (per-instance address override so two identical ICs need one decoder file), R6
(`on_rule_decoded` single-observer and `multiline_bits` shared mutable state).

### Phase 9 — Architecture refactor
R1 (`CaptureBackend` interface + one `BaseSnifferWindow`; the two sniffer windows duplicate
~60% of their logic, and that duplication already produced B24/B26/C10), R2 (move
`I2CTransaction` out of the ctypes AD2 module into `core/transaction.py` with real fields for
`timeout`/`result`/`overflow`), R3 (layering: `core/log_model` imports `ui.theme`; capture
I/O lives in `ui/common`; two divergent CSV row parsers), R7 (performance: per-transaction
rule scan, O(n²) filtered insert, per-row resize, unbounded log), R8 (private-member reach-through
and the hard-coded `count - 3` tab anchor). Also fixes B24, B25, B26, B28 in passing since
they live in the rewritten windows.

### Phase 10 — Gateway app: resolve or remove
M3: `bq76905_gateway_tool.py` is listed in `ARCHITECTURE.md` §1, has a 20 KB user guide, and
is asserted by `smoke_test.py` (the single failing check) — but neither the app nor its
firmware is in the tree. Decide with the owner: restore, rebuild against the shared toolkit,
or remove app + guide + test entry + ARCHITECTURE row in one pass. Either way
`smoke_test.py` must end at 9/9 or N/N.

### Phase 11 — Master mode + ALERT
M9: expose ion master mode in the GUI, gated on `is_master_firmware()`, reusing the Phase 9
backend abstraction; decide the fate of the orphaned AD2 read/write/scan UI; implement
SMBALERT# monitoring or remove the ALERT control that currently configures nothing.
Verified against the Phase 1 rig (the DUT can assert ALERT on demand).

### Phase 12 — Windows support
M10: `ARCHITECTURE.md` promises "optionally Windows 10+" while `dwf_loader` only tries the
macOS framework and `libdwf.so`, and `install.sh`/`run.sh` are bash-only. Add the `dwf.dll`
path, a Windows launcher, COM-port enumeration checks, and a documented install path — or
formally drop the claim.

### Phase 13 — Hand-tool board support
M4: the purpose-built hand tool is currently detected by guessing USB bridge VIDs. Add a
board-ID byte to HELLO (protocol v2, host + firmware + `PROTOCOL.md` in one pass) and a BSP
layer so a second board is a build target rather than a fork.
