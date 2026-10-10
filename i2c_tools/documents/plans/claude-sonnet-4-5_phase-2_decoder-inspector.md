# Phase 2 — Decoder Inspector (new feature)
Model: claude-sonnet-4-5 · Prereq: Phase 1 · Est. scope: 1 generator, 1 dialog, 1 CLI, tests

Give the user a way to see what is inside a decoder JSON and **what to
expect in a replay** before hunting a capture. Modeled on the IP5385
sanity-check package (`ip5385_decoder.md`), which proved valuable as a
hand-written artifact; this phase makes it a generated, always-current
in-app view.

## Where it lives
- **Replay window**: a `View Decoder` button in the Load Decoder sidebar
  section, next to the existing Edit Decoder action
  (`ui/widgets/sidebar_sections.py`). Enabled when at least one decoder is
  loaded. If several are loaded, the button opens the inspector on the
  decoder currently selected in the Decoders list.
- Same button on both sniffer windows (the section is shared, so this is
  free — verify it does not break their layouts).
- **CLI**: `tools/decoder_report.py DECODER.json [--out report.md]` emits
  the identical Markdown. Keep the generator UI-free so both callers share
  it.

## Generator — `core/decoder_report.py` (new, UI-free)
`build_report(schema_or_path) -> str` producing Markdown with these
sections, in this order:

1. **Header** — device name, description verbatim (this is where decoder
   provenance and board assumptions live), 7-bit address plus the 8-bit
   W/R pair, file byte order, schema version, rule count, display-group
   count.
2. **Rules table** — one row per rule: Reg (hex), Type, register width,
   data bytes, Format, Byte order, Signed, Unit, Function, Access, Group,
   Name. Sort by register then type so read/write pairs sit together.
3. **Bit fields** — per `format: bits` rule, one line per field:
   `[hi:lo] **Name** (mode)` plus enum names or the field function/unit.
   Reserved (unnamed) spans listed explicitly as `reserved` so a user can
   see coverage gaps.
4. **Field rules** — per rule carrying `fields`, a table of
   offset/size/byte order/signed/function/unit/name.
5. **Subcommands** — code (hex), name, data bytes, and whether it carries
   fields; state the protocol registers in use (`subcommand_reg`,
   buffer at `subcommand_reg+2`, checksum/length) when any exist.
6. **What to expect in replay** — THE POINT OF THE FEATURE. For each read
   rule, the exact wire pattern that produces it, written as the CSV rows
   a capture would contain, e.g.:
   ```
   Wpc_cur (0x13, 1 byte)
     W 0x75  13          (pointer write)
     R 0x75  <1 byte>    -> "Wpc_cur = <X*10> mA"
   ```
   For subcommands, show the 0x3E/0x3F write, the echo poll, and the
   buffer read. State plainly which rules will NEVER appear unless the
   host uses a particular access pattern (e.g. word reads vs byte reads).
7. **Sanity checklist** — generated warnings, not prose: rules whose
   description contains "verify" (unconfirmed provenance); bit rules with
   empty or partial coverage; registers with a read rule but no write rule
   where access is R/W (and vice versa); multi-byte rules on a device
   whose description says single-byte only; duplicate (address, register,
   type) keys; groups referenced but not declared. Reuse the checks in
   `tools/validate_capture_csv.py`'s style — fail-visible, one line each.

## Dialog — `ui/dialogs/decoder_inspector.py` (new)
- Read-only, non-modal, themed (no hard-coded colors — use theme tokens),
  resizable, remembers size in settings.
- Renders the Markdown in a `QTextBrowser`; a monospace section for the
  replay-expectation block.
- Buttons: **Copy**, **Save as Markdown…** (default filename
  `<device>_decoder.md`), **Close**.
- Poppable is NOT required (it is a dialog, not a tab).

## Explicit non-goals
- No editing from this view (that is the editor's job).
- Do not generate a synthetic replay CSV in this phase; the report only
  describes expected traffic. (A `--emit-csv` mode is a later idea.)

## Acceptance
- `python3 tools/decoder_report.py i2c_decoders/bq76922_decoder.json`
  produces a report whose subcommand section lists DASTATUS5 with its 14
  fields and whose checklist flags the `verify vs SLUUCG7` rules.
- Same for bq25731 (48 rules, fields rules present) and bq76905.
- New `tests/test_decoder_report.py`: report contains the device name and
  address for each shipped decoder; the replay section for a known rule
  contains both the pointer-write and read lines; the checklist flags a
  deliberately broken decoder (duplicate key, undeclared group).
- New `tests/test_decoder_inspector.py` (offscreen): the dialog opens from
  the replay window with a decoder loaded, renders non-empty text, and
  closes cleanly.
- Smoke test still 8 passes.

## Deliverable
MINOR bump (→ 1.3.0), changelog, `documents/User_Guide_i2c_replay.md`
gains a "View Decoder" subsection, manifest regenerated, one zip.
