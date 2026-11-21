# SniffWorks
<!-- version: 1.3 -->

SniffWorks is a family of bus sniffers built on one shared framework: I²C, GPIO, SPI, UART, CAN, USB PD and Ethernet. Each protocol has a standalone app, and a master multi-sniffer app shows several buses and several hardware sniffers at once on one timeline. The goal is debugging a system with many communication schemes: the user knows the expected cross-bus sequence (e.g. an I²C write raises a GPIO, which starts an SPI or UART transfer), and a missing, late or out-of-order event shows where to start looking. The software must stay highly configurable so new hardware and tools can be added.

This file holds the cross-project decisions. Each sub-project has its own CLAUDE.md for its detail, and Claude Code loads this file together with it.

| Sub-project | Folder | CLAUDE.md | Status |
|---|---|---|---|
| I²C sniffer (ion_i2c_tool 1.6.0) | `i2c_tools/` | `i2c_tools/CLAUDE.md` | Phase 1 closed; its plan is frozen for the restructure (SW-08) |
| GPIO sniffer | `protocols/gpio/` | `protocols/gpio/CLAUDE.md` | Requirements draft, no code (SW-05) |
| Probe firmware | `firmware/` | — | Tree and naming only; C031 code still in `i2c_tools/embedded/` (SW-04) |
| System emulation testing | `system_emulation_testing/` | — | Tree only; excluded from normal use (SW-13) |
| SPI, UART, CAN, USB PD, Ethernet | not created | — | Planned |

## Findings
- The shared venv `$SHARED_VENV` = `~/Documents/GitHub/.venv` (Python 3.12.13, PySide6 6.11.1) gives the same test exit codes as the old per-project i2c_tools venv (i2c_tools/change_log.md 2026-10-19, commit ae8a627).
- i2c_tools already separates protocol-independent pieces (theme, window shell, dialogs, settings, hex helpers, log table) from I²C-specific ones (`I2CTransaction`, decode schema, probe protocols); see `i2c_tools/documents/ARCHITECTURE.md`. That split is the starting point for the framework.

## Decisions
- SW-01 One master multi-sniffer app; each standalone protocol app is a configuration of it (one protocol, simpler layout) behind a thin entry point, so there is one codebase, not N+1 apps (owner, 2026-10-19).
- SW-02 Software is split by protocol: each protocol package owns its events, decoder, decoder schema, CSV columns and UI panels. Hardware sniffers are backends that declare which interfaces they capture; production hardware will be dedicated designs, and NUCLEO eval boards are the POC platforms because they are validated hardware (owner, 2026-10-19).
- SW-03 Multiple sniffers share a time base through a sync line, built as an accessory. The app names which device is the sync master, because a setup may contain only low-level devices. The number of drops is limited by drive strength, since each device adds load and RC delay (owner, 2026-10-19).
- SW-04 Firmware is one source tree: a common folder for shared functions, then targets per board (NUCLEO POC and production boards, several MCUs, staying in the STM32 family), then build configurations that pick the interface set, e.g. a C0 board built for UART, SPI, GPIO or I²C or a combination. No forks (owner, 2026-10-19).
- SW-05 GPIO is the next protocol, because it gives an interrupt-like event to trigger on. The first cross-bus test: an I2C1 event triggers a GPIO, then watch for an I2C2 event (owner, 2026-10-19).
- SW-06 A test tool for quick test creation, based on the NUCLEO-H723 plus system emulators for the simpler hardware devices; it moves to the more complex devices once the simple ones work (owner, 2026-10-19; see Open Questions for the scope).
- SW-07 Captures use a new multi-stream CSV format covering all protocols and devices in one file (owner, 2026-10-19).
- SW-08 The i2c_tools phase plan (`i2c_tools/plan_n_exe/00_MASTER_PLAN.md`) is frozen; restructure SniffWorks first (owner, 2026-10-19).
- SW-09 All projects share one Python venv beside the repos, `$SHARED_VENV` (exported by advanced_engineering `env/.zshenv`), whose manifest, lock and sync script are in advanced_engineering `tools/venv/`; scripts fall back to a local `.venv` when it is unset (owner, commit ae8a627).
- SW-10 The master app's debugging aid is checking expected cross-bus behaviour against what was captured: if the expected event does not appear, that is where to start debugging (owner, 2026-10-19).
- SW-11 The AD2 is not part of SniffWorks: it was the first POC because libraries existed, and the owner keeps a separate copy of the current tool that works with the AD2 as a backup. The hardware loop is NUCLEO POC → dedicated hardware designed from it → next NUCLEO POC (owner, 2026-10-19).
- SW-12 Hardware specs must let the app's discovery identify each connected device correctly; a NUCLEO does not give enough information for that today. Dedicated hardware replaces the ST-LINK interface with a lower-cost USB bridge; candidates MaxLinear XR21V1410 and Silicon Labs CP2102N, FTDI less likely (owner, 2026-10-19).
- SW-13 Emulator and loopback boards live apart from the sniffers because normal use excludes them: `system_emulation_testing/firmware/[common|<mcu>-<board>|<other>]`; i2c_tools' `loopback_dut/` moves there (owner, 2026-10-19).
- SW-14 Repo layout (owner chose, 2026-10-19): `protocols/<bus>/` for each protocol's host code, `firmware/common/` + `firmware/targets/<mcu>-<board>/` + `firmware/docs/`, `system_emulation_testing/`; `i2c_tools/` stays until migrated. GPIO is the first sub-project created this way.
- SW-15 Exception to SW-08 (owner, 2026-11-20): i2c_tools test hygiene done before the restructure: C9 test paths, R9 single runner (`i2c_tools/conftest.py`, `python -m pytest`), a test exit-crash fix, smoke TODO for the gateway, and repo CI (`.github/workflows/ci.yml`, Ubuntu + macOS); detail in i2c_tools/CLAUDE.md v1.25 and i2c_tools/change_log.md 2026-11-20.
## Tradeoffs
- Freezing the i2c_tools plan delays its open fixes (B31 400 kHz, Phases 2-13) until after the restructure (rationale not recorded).

## Gotchas
- ~~`i2c_tools/install.sh` deletes and recreates `$VENV_DIR` when `bin/python` is missing, even when it is the shared venv; a broken `$SHARED_VENV` would be wiped. Fix pending (session 2026-10-19).~~ fixed v1.1: install.sh [v0.1] never deletes or pip-installs into the shared venv (i2c_tools/change_log.md 2026-10-19 cont.).
- ~~`i2c_tools/install.sh` runs `pip install --upgrade pip` and `pip install -r requirements.txt` (loose `>=` pins) into the shared venv, bypassing `shared_venv.lock.txt`, so one project's install can upgrade packages for every project. Fix pending.~~ fixed v1.1: with `$SHARED_VENV` set it runs advanced_engineering `sync_venv.sh` (lock-constrained) instead.
- Project install scripts must never create, delete or pip-install into `$SHARED_VENV` themselves; only advanced_engineering `tools/venv/sync_venv.sh` changes it, and a new project's requirements.txt goes into `shared_venv_projects.txt` (pattern: i2c_tools/install.sh [v0.1]).
- ~~Commit 7799b55 added i2c_tools before the root `.gitignore` existed (62d5fcd): 257 `__pycache__/` and firmware `build/` files and 11 `.DS_Store` are tracked. Untrack with `git rm -r --cached`, but keep the two flashable images (`embedded/sniffer_nucleoC0_fw/build/sniffer_nucleoC0_fw.bin`, `loopback_dut/firmware/build/firmware.bin`).~~ fixed v1.2: untracked in 80600a1; root `.gitignore` rule `**/build/*` keeps only the two .bin images.
- The root `.gitignore` ignores every `*.csv`; capture fixtures and multi-stream CSV test data must be un-ignored explicitly (as `i2c_tools/.gitignore` does).
- Claude Code loads every CLAUDE.md from the working folder up to the repo root, so a sub-project CLAUDE.md must not tell Claude to ignore this one.
- CI runs only i2c_tools today; each new sub-project (protocols/gpio first) needs its own job in `.github/workflows/ci.yml` when it gets tests, or its tests never run on GitHub.

## Current State
- `i2c_tools/` (plan frozen, SW-08); `protocols/gpio/` created with CLAUDE.md, README, requirements draft (GPIO-R01..R11, owner vs proposed marked) and change log; `firmware/` and `system_emulation_testing/` hold READMEs, docs and empty folders. No new code yet.
- install.sh shared-venv fix done and tested in a scratch harness (not yet run end to end against the real shared venv).
- Build/cache files untracked (80600a1). Not yet done: migrate code out of i2c_tools.
- CI added (SW-15): i2c_tools `python -m pytest` = 26 passed, 1 skipped (exit 77), 1 xfailed (`neware_decoder.json` not committed; owner to commit it).
- Next: owner review of the GPIO requirements; settle the event model, wire protocol and multi-stream CSV (Open Questions); then the first GPIO code.

## Open Questions
- ~~Repo layout for the restructure.~~ Mostly resolved v1.1 (SW-14). Still open: where the shared framework, the hardware backends and the app entry points go (proposal: `framework/`, `backends/<hw>/`, `apps/`).
- Firmware naming: ~~target folders~~ resolved v1.1 as `<mcu>-<board>` (SW-13, SW-14). Still open: production board names/revisions, and build-configuration names (proposal: by interface set, `i2c`, `gpio`, `i2c+gpio`).
- Common event model and wire protocol (Claude proposal): every event carries device ID, channel, protocol, kind and a device-clock timestamp, and every firmware speaks one framed protocol with a capability handshake and a sync-event frame. Confirm before the framework is written.
- Sync line spec (SW-03): maximum drops, buffered star vs multidrop, pulse rate, how a sync master is chosen and how a device with no sync input is shown.
- Multi-stream CSV schema (SW-07): common columns, how protocol-specific fields are stored, file metadata (devices, clock offsets, sync master), and the import path for i2c_tools CSV v1/v2.
- ~~Scope of the SW-06 test tool~~ resolved v1.1: it lives in `system_emulation_testing/` with the loopback DUT, excluded from normal use (SW-13). Still open: does the loopback DUT's isolation rule (never imports sniffer code) apply to the whole folder?
- Link bandwidth: several busy buses can exceed a full-speed USB link, so how much filtering or triggering runs on the device?
- Device identification (SW-12): what must a probe report so discovery names it (board type, target, build configuration, firmware version, serial)? In the USB descriptors (bridge product/serial strings), in a firmware HELLO, or both? Blocks the hardware spec and the discovery code.
- USB bridge choice (SW-12): XR21V1410 vs CP2102N vs FTDI on throughput, cost, custom USB descriptors and driver support on macOS/Linux/Windows. Check against the datasheets before choosing.

## Revision History
- v1.0 (2026-10-19): Created; overview and sub-project table, decisions SW-01..SW-10 from the owner's answers, shared-venv and repo-hygiene gotchas, open questions for the restructure.
- v1.1 (2026-10-19): owner answers: AD2 out of SniffWorks (SW-11), device-identification and USB-bridge direction (SW-12), system_emulation_testing (SW-13), repo layout (SW-14); install.sh gotchas fixed and struck, shared-venv rule; GPIO, firmware and emulation folders in the sub-project table; layout, naming and SW-06 questions partly resolved; two new open questions; state rewritten.
- v1.2 (2026-10-19): tracked build/cache gotcha fixed (80600a1); state updated.
- v1.3 (2026-11-20): SW-15 test-hygiene exception to SW-08 and repo CI; CI-per-sub-project gotcha; state updated.
