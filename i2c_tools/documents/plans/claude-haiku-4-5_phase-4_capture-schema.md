# Phase 4 — Capture CSV schema completion
Model: claude-haiku-4-5 · Prereq: Phases 1–3 · Est. scope: 1 schema, 1 reader, wiring

Completes M1. **Read `documents/CSV_FORMAT.md` first** — the normative v1
spec already exists and both real captures validate against it. This phase
makes it machine-readable and adds legacy support. Do not redesign the
format; implement what the spec says.

## Task 1 — `schema/capture.schema.json` (new)
Encode capture CSV v1: the 13-column header, per-column type and pattern
(Time `HH:MM:SS.mmm`, Addr `^0x[0-9A-Fa-f]{2}$` with a 0x00–0x7F range
note, Dir `W|R`, Data space-separated hex pairs, NAK `NAK|""`, Start
`S|Sr|""`, Stop `P|""`, PEC `✓ PEC|✗ PEC|""`). Model it as a schema for a
parsed row object (one object per row), since CSV itself is not JSON.
Mirror `schema/decoder.schema.json`'s `$id`/title conventions — and use
the CURRENT product name, not "ad2_i2c_tool" (see C4).

## Task 2 — version marker line
Add an optional first line `# ion_i2c_capture v1` written by the exporter
ABOVE the header row. The loader must accept files with or without it
(every existing capture lacks it). Update `documents/CSV_FORMAT.md` to
describe the marker and state that the header row remains the fallback
version signature.

## Task 3 — legacy v0 reader
Some captures (EVM_* files) have an 11-column header. Detect the column
count/names and map them onto the canonical fields; missing columns become
empty. Put this in the single parser in `ui/common/capture.py`. A v0 file
must load and replay; the validator should report it as "v0 (legacy)"
rather than failing.

## Task 4 — wire the validator in
`ui/widgets/sidebar_sections.py::validate_capture` should call the same
logic as `tools/validate_capture_csv.py` (extract the check into a shared
function; do not duplicate the rules) and show a row-numbered error list.

## Acceptance
```bash
python3 tools/validate_capture_csv.py <a POC_* capture> --strict   # VALID
python3 tools/validate_capture_csv.py <an EVM_* capture>           # v0, loads
QT_QPA_PLATFORM=offscreen python3 tests/test_csv_format.py
QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py
```
Extend `tests/test_csv_format.py`: marker line round trip; a v0 file loads
with correct address/direction/data; validator labels v0 vs v1.

## Do not
- Do not change the time format or column set in this phase.
- Do not touch decoder code.

## Deliverable
MINOR bump, changelog, manifest, one zip.
