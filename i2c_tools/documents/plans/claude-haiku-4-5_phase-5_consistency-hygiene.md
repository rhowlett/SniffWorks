# Phase 5 — Consistency and hygiene
Model: claude-haiku-4-5 · Prereq: Phases 1–4 · Est. scope: mechanical sweeps

Fixes C1, C5, C6, C7, C8. All mechanical. After EVERY deletion, run the
full suite — a "dead" file that is still imported will show up there.

## Task 1 — C1: one version source (verified)
`version.py` says 1.2.1; `ui/common/app_info.py` `VERSION = "1.0.0"`; the
bootstrap fallback is another "1.0.0". Make `app_info` import
`PROJECT_VERSION` from `version.py` and delete the other literals. Also
fix `version.py`'s own docstring, which still says "Set to major 1.0".
Verify: every app reports the same string via
`QApplication.applicationVersion()`.

## Task 2 — C5: delete deprecated shims
Live code still imports them: `core/ion_backend.py` → `core.nucleo_protocol`;
`ui/widgets/__init__.py` → `help_panel`, `exit_panel`; tests →
`nucleo_backend`. Switch each import to the real module, then delete all 7
shim files. Suite must stay green.

## Task 3 — C6: remove dead code and leftovers
Candidates listed in the review: `ui/main_window.py`, `ui/rw_panel.py`,
`ui/decode_panel.py`, `ui/theme.new.py`, `ui/theme.org.py`,
`ui/widgets/registers_view.org.py`, unused `export_json`,
`filter_addresses`, `capture_all`, `load_decoder_file`, the 1.1 MB
`long_data_bq76905.json`, `i2c_capture/bq76905.json` (a v2 decoder sitting
in the captures folder), and duplicated `dwfconstants.py` / CMSIS headers.
**Before deleting each**, grep the tree for references. `ui/main_window.py`
contains the only AD2 master read/write/scan UI (M8): do NOT delete it in
this phase — move it to `reference_samples/` (or `archive/`) and note in
the changelog that the scope decision is still open.
Make the dwf loader prefer the INSTALLED SDK copy over the bundled one.

## Task 4 — C7: repo hygiene
Add a `.gitignore` covering `__pycache__/`, `*.pyc`, `.DS_Store`,
`embedded/**/build/`, `.venv/`. Remove those artifacts from the tree.
Rename `idel_normal_opperation.csv` → `idle_normal_operation.csv` (update
any reference). Extend `tools/check_tree.py` to track `.csv` and IDE
project files so the manifest stops omitting them, then regenerate.

## Task 5 — C8: theme tokens
Replace the hard-coded `#2ECC71` in `ui/sniffer_window.py` and the
hard-coded "Courier New" in `core/log_model.py` with theme tokens. Note:
`core/log_model.py` importing `ui.theme` is a layering violation (R3) —
out of scope here, but do not make it worse; if a token lookup is needed,
keep it where the import already exists.

## Acceptance
All test files under `tests/` plus `tests/smoke_test.py` (8 passes), and
`python3 tools/check_tree.py` clean after regeneration.

## Deliverable
PATCH bump, changelog listing every deleted/moved/renamed file, manifest
regenerated, one zip.
