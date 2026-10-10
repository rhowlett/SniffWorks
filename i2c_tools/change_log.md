# ion_i2c_tool — Change Log

Chronological (oldest first); new update notes are appended at the end.
Consolidated from the per-update *_NOTES.md files on 2026-07-09.

---

# 2026-07-08 — Phase 2 — Theme File System (+ theme consolidation, shared tabs, common-behavior refactor)

## Phase 2 — Theme File System: Delivery Notes

### Update (theme consolidation)
Named themes are now just: **Default (Modern Dark)** — new indigo-on-slate
palette and the startup theme for every app — plus System, Light, Dark.
Iontra Dark/Light, Engineering Dark, and Dark Claude were converted to
ui/themes/*.qt_theme.json files (exact palettes preserved; verified by test)
and removed from ui/theme.py. They appear in the picker's "Theme Files" group.
Entry points and window fallbacks now start on "default". Last-used-theme
persistence deferred to Phase 3 as agreed.

### Update 2 (shared tabs package)
New ui/tabs/ package: PreferencesTab (ThemePicker in a scroll area, with
add_section() for app-specific settings later), HelpTab (help FILE passed as a
field; HelpTab.for_app() convenience for registered apps), ExitTab (Close
Application button colored action_disconnect via btnDisconnect). All four
windows migrated; theme_editor.py now has Config/Preview/Exit tabs and no Exit
button. Old locations (ui/widgets/help_panel.py, exit_panel.py,
ui/preferences_panel.py) are one-line deprecation shims.

### Update 3 (common-behavior refactor: items 1, 3, 4, 5)
- **theme.signals.changed(selection)** fires after any theme apply (named or
  file, exactly once). HelpTab and LogPanel now subscribe and refresh
  themselves, so the four windows' _on_theme_apply handlers shrank to
  set-name + apply + notify — the repaint side effects can no longer be
  forgotten by a new window.
- **AppWindow.notify(msg, sticky=False)** (StatusBarNotifier mixin): one
  standard 4 s status-bar message everywhere; DecoderEditorWindow and
  MainWindow gained the mixin too. All scattered showMessage timeouts unified.
- **ConfirmingCloseMixin** (included in AppWindow): one closeEvent for all
  five windows. Override close_guard() for a Yes/No message (sniffer's
  unexported-rows warning, theme editor's unsaved-changes), confirm_close()
  for richer flows (decoder editor's Save/Discard/Cancel), on_close() for
  teardown (spy stop, device close, child-editor close). Exit tab and window
  close button share this path by construction.
- **EditorSection** is now self-managed: it owns the open-or-focus decoder
  editor window and takes a path_provider for auto-loading the selected
  decoder. Sniffer/replay dropped their _on_edit_decoder handlers and window
  refs; replay's on_close() just calls editor_section.close_editor().
  self_managed=False keeps the old signal-only behavior available.
- New tests: tests/test_common_refactor.py (16 checks).

### Drop-in file list (unzip over your project root)
    ui/theme.py                        MODIFIED  file-theme API + parameterized QSS template
    ui/theme_config_loader.py          NEW       load/normalize/discover *.qt_theme.json (pure Python)
    ui/widgets/theme_picker.py         MODIFIED  named themes + Theme Files list + Custom browse + editor launch
    ui/widgets/app_window.py           MODIFIED  registers its QTabWidget for theme-file tab settings
    theme_editor.py                    NEW       playground renamed & refactored onto ui/ (root of project)
    schema/qt_theme.schema.json        NEW       draft-07 schema for theme files
    ui/themes/clay.qt_theme.json       NEW       sample (radius 8, above-border titles)
    ui/themes/solarized_light.qt_theme.json  NEW sample (new palette)
    ui/themes/iontra_dark.qt_theme.json      NEW converted from named theme
    ui/themes/iontra_light.qt_theme.json     NEW converted from named theme
    ui/themes/engineering_dark.qt_theme.json NEW converted from named theme
    ui/themes/dark_claude.qt_theme.json      NEW converted from named theme
    sniffer_ad2.py / i2c_replay.py           MODIFIED  initial_theme="default"
    ui/common/app_bootstrap.py               MODIFIED  default initial theme
    ui/main_window.py ui/sniffer_window.py   MODIFIED  fallback theme "default"
    ui/replay_window.py ui/decoder_editor_window.py  MODIFIED  same
    tests/test_theme_files.py          NEW       58 checks, offscreen
    tests/test_common_refactor.py      NEW       16 checks, offscreen
    ui/log_panel.py                    MODIFIED  self-repaints on theme change
    ui/widgets/sidebar_sections.py     MODIFIED  self-managed EditorSection
    docs/PHASE4_REPLAY_PLAN.md         NEW       record/replay plan (refine after Phase 3)

theme.apply_theme() accepts named themes or "file:<path>" selections
from the picker; window signal handlers are unchanged.

### Design in one paragraph
palette+settings in the JSON are the source of truth; ui/theme.py regenerates
QSS from its own (now parameterized) template, so file themes and named themes
render through one pipeline and future widgets stay consistent. Named themes
are pinned to their original values (radii 4/3, original tab QSS) — verified
by test. Non-QSS tab settings (document mode, draw base, position, shape)
reach QTabWidgets through a weak registry that AppWindow joins automatically;
applying a named theme resets them. The editor launches as a separate process
from Preferences because it restyles its QApplication globally.

### Manual visual checks (recommended on macOS)
1. `python3 sniffer_ad2.py` → Preferences: named radios + "Theme Files" group
   listing clay + solarized light; apply each; apply a named theme again and
   confirm it looks exactly as before this change.
2. Click "Open Theme Editor" → editor opens as its own app. Change control
   radius / colors → Apply → Preview tab. Save into ui/themes/ → back in the
   sniffer, "Refresh List" → new theme appears → Apply.
3. In the editor, Tab position South + document mode → Apply → editor's own
   tabs move (same registry the main tool uses).

### Tests
    QT_QPA_PLATFORM=offscreen python3 tests/test_theme_files.py   # 58/58
    QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py         # 10/11*
*the one failure is the pre-existing missing bq76905_gateway_tool module
 (not in the uploaded zip), unrelated to this change.

### TODOs / accepted limitations
- Last-used theme is not persisted across app restarts (no settings store in
  the project yet). Windows still start with their built-in default theme.
- `button_layout` / `button_fixed_width` / `table_row_height` affect the
  editor preview only; the main tool's layouts manage their own button sizing.
- Editor "System Default" style restores the platform style and saves
  qt_style as "" (meaning: don't override).

---

# 2026-07-09 — Phase 3 — sniffer_nucleoC0 / Ion Sniffer (+ settings persistence)

## Phase 3 — sniffer_nucleoC0.py: Delivery Notes

### Drop-in file list (unzip over your project root)
    sniffer_nucleoC0.py                    NEW   entry point
    core/nucleo_protocol.py                NEW   framing/CRC/commands/decoders (pure Python)
    core/nucleo_backend.py                 NEW   NucleoLink + NucleoWorker (QThread, pyserial)
    ui/sniffer_nucleo_window.py            NEW   the app window
    ui/widgets/serial_device_panel.py      NEW   shared serial Device tab (item 2)
    ui/widgets/serial_prefs_section.py     NEW   baud rate in Preferences
    ui/sniffer_panel.py                    MODIFIED  description parameterized (item 6 flag pattern)
    ui/common/app_info.py                  MODIFIED  sniffer_nucleoC0 registered
    documents/User_Guide_sniffer_nucleoC0.md  NEW  Help-tab guide (wiring, baud, troubleshooting)
    tests/test_nucleo_protocol.py          NEW   43 checks, no hardware needed
    tests/smoke_test.py                    MODIFIED  nucleo window added
    ui/common/settings_store.py            NEW   persistent settings (QSettings)
    ui/common/app_bootstrap.py             MODIFIED  theme restore + persistence
    tests/test_settings_store.py           NEW   13 checks
    tests/*                                MODIFIED  settings isolated to temp INI
    docs/PROTOCOL.md (embedded repo)       MODIFIED  Phase 4 commands 0x10-0x13 reserved

Requires: pyserial (pip install pyserial). No WaveForms SDK anywhere in the
new app — sniffer_ad2.py remains in the tree untouched but is no longer the
product path.

### Architecture
- core/nucleo_protocol.py is pure Python: crc8, command builders (byte-exact
  vs PROTOCOL.md, incl. the documented boot HELLO AA 04 08 00 4E 43 30 53 01
  01 00 01 BB), FrameParser (garbage-resync, chunk-safe), TXN/STATUS/HELLO/
  ERROR decoders, TimestampMapper (anchors the device us clock to wall time,
  handles the 32-bit wrap at ~71.6 min). Phase 4 commands 0x10-0x13 declared.
- core/nucleo_backend.py: NucleoLink drives the protocol against any
  serial-like object (fully tested with a fake port); NucleoWorker is the
  QThread wrapper with the AD2 SpyWorker's exact signal surface
  (transaction_captured/error_occurred/stats_updated) plus device_status
  (bus_hz, dropped) and connected/disconnected. PEC checked host-side exactly
  as the AD2 spy path did (SMBus CRC-8 over addr_byte + payload).
- One TXN frame = one address phase; restart -> I2CTransaction.start=2, so
  the log table renders S/rS/P identically to the AD2 sniffer.
- Serial session opens on Start Sniffing (the firmware is silent until
  CMD_START, so an idle connection adds nothing); Connect on the Device tab
  validates the port choice and arms the Sniffer tab.

### Deferred items landed here
- Item 2: SerialDevicePanel is the shared Device tab for serial tools.
- Item 6: SnifferPanel (controls + Capture Stats) reused wholesale; its
  AD2-specific description became a constructor parameter.
- Item 7: LogPanel (filter bar/export) reused wholesale — nothing to extract.

### Manual test with hardware (macOS)
1. pip install pyserial; flash sniffer_nucleoC0_fw; wire SCL->D8, SDA->D2, GND.
2. python3 sniffer_nucleoC0.py -> Device tab -> Refresh: the ST-LINK port is
   flagged and sorted first -> Connect.
3. Sniffer tab -> Start Sniffing. Status bar shows "fw 1.0 (bit-bang)" and
   the measured bus kHz; transactions stream into the log.
4. Load i2c_decoders/bq76905_decoder.json -> live decode; Export CSV ->
   feed it to i2c_replay.py to confirm the shared CSV contract.
5. Preferences -> Serial to change baud (rebuild firmware to match).

### Update: settings persistence (the TODO deferred to this phase) — DONE
ui/common/settings_store.py: one QSettings file for the whole suite
(theme chosen in any app is the startup theme for all).
- Theme: every apply is persisted via theme.signals.changed;
  build_application applies the app default first, then the saved selection,
  so a persisted "file:<path>" whose file went missing degrades to the
  default instead of an unstyled app (tested).
- Serial: baud (Preferences -> Serial) and last-used port (preselected on the
  Device tab, beating the ST-LINK sort) persist across runs.
- Test isolation: ION_TOOL_SETTINGS env var points the store at a file;
  every test suite sets it to a temp INI so running tests never touches your
  real settings. tests/test_settings_store.py: 13 checks.

### Remaining
- Phase 4 (record/replay) per docs/PHASE4_REPLAY_PLAN.md — protocol constants
  and PROTOCOL.md reserved commands are already in place.

---

# 2026-07-09 — Decoder Manager — multi-decoder support (+ reorder)

## Decoder Manager Update — Delivery Notes

### Answer to "is it missing?"
Half. The decode ENGINE already supported multiple devices: DecodeSchema
rules are keyed by (i2c_address, register, transaction_type) and the
StreamDecoder routes every transaction by its address. What was missing was
the MANAGEMENT layer — the UI loaded exactly one file and set_schema()
replaced rather than merged. This update adds that layer.

### Drop-in file list (unzip over your project root)
    core/decoder_manager.py            NEW   DecoderSetManager (merge + metadata)
    ui/widgets/sidebar_sections.py     MODIFIED  LoadDecoderSection -> "Decoders"
                                                 list with Add.../Remove
    ui/log_panel.py                    MODIFIED  apply_schema(schema)
    ui/sniffer_window.py               MODIFIED  merged-schema flow
    ui/sniffer_nucleo_window.py        MODIFIED  merged-schema flow
    ui/replay_window.py                MODIFIED  merged-schema flow (multiline bits kept)
    ui/common/settings_store.py        MODIFIED  KEY_DECODERS
    tests/test_decoder_manager.py      NEW   38 checks (incl. reorder)

### Behavior
- The sidebar section is now "Decoders": a list of loaded decoder JSONs
  ("BQ76905 @0x08 — 42 rules (bq76905_decoder.json)") with Add... and
  Remove buttons. Every add/remove rebuilds ONE merged schema and re-decodes
  the whole log, so traffic from e.g. a BQ76905 @0x08 and a BQ25731 @0x6B
  decodes side by side in the same table.
- Merge policy: load order; if two files define the same
  (address, register, type) key the later file wins and the status line says
  "N overridden by load order" so shadowing is never silent. Re-adding a file
  reloads it in place (edit in the Decoder Editor -> Add again to refresh).
- Editor -> Launch opens the Decoder Editor on the SELECTED decoder in the
  list (falls back to the most recently added).
- The loaded set persists across runs (settings store); missing files are
  skipped silently on restore.
- Compatibility: decoder_selected(str) still fires per successful add;
  path()/is_valid() still work (path() = selected entry).
- Reorder: ▲/▼ buttons move the selected decoder in load order
  (tooltip explains: on collisions the LOWER entry wins). Selection follows
  the moved entry; the merged schema and the log re-decode on every move,
  and the new order persists.

All suites pass (28 new checks incl. a two-device decode through the real
log model); 4-app smoke test unchanged.

---

# 2026-07-09 — Phase 4a — Master transport, ion rename, CLI replay tools

## Phase 4a — Master Transport, Ion Rename, CLI Replay Tools

### Firmware (embedded zip)
- BOARD select [XREF: board-select]: BOARD_NUCLEO_C031C6 (default) /
  BOARD_ION_C0 (standalone board, pins provisional). Build:
  make EXTRA_DEFS='-DBOARD=BOARD_ION_C0'
- SNIFF_MODE_MASTER: active I2C master on the same PA9/PA10 pins (LL, polled,
  hardware-verified TIMINGR 100k/400k @48 MHz from your BQ76905 project).
  Commands 0x10-0x13 implemented (variable-length form); each bus phase
  replies as a standard TXN frame; new TXN flag bit 5 = TIMEOUT (25 ms
  budget). SET_BUS_SPEED acked with STATUS. START/STOP rejected in master
  mode; HELLO mode byte = 3.
  Build: make EXTRA_DEFS='-DSNIFF_MODE=SNIFF_MODE_MASTER'
- All four build combos compile 0-warning: bitbang, slave-mon, master,
  master+ION. Host C tests: 111 checks, 0 failures (var-length parser,
  max/oversize payload, CRC reject, TIMEOUT flag).

### Host (tool zip)
- RENAME nucleo -> ion (role name for the probe family): core/ion_protocol.py,
  core/ion_backend.py (IonLink/IonWorker), ui/sniffer_ion_window.py,
  sniffer_ion.py, User_Guide_sniffer_ion.md, app_info key "sniffer_ion".
  Old paths remain as one-line deprecation shims (incl. sniffer_nucleoC0.py).
- Port hints: ST-LINK (Nucleo) plus generic USB-UART bridges
  (FTDI/CP210x/CH340/PL2303) flagged and sorted first for the future ion
  board; HELLO remains the definitive identity check.
- core/ion_master.py: IonMasterLink (blocking send-and-wait; write / read /
  write_read / write_with_pec / set_bus_speed), result classification
  ACK / NAK / TIMEOUT / LINK_TIMEOUT; open_master() verifies the firmware
  variant and fails with bench-actionable messages.
- tools/record_on_trigger.py: sniffer-firmware capture bounded by a trigger
  (ADDR:DIR[:HEXPREFIX], e.g. 0x08:W:3E) -> JSON-lines.
- tools/replay_compare.py: master-firmware replay of a recording;
  write+restart-read pairs replay as one write_read (repeated start
  preserved); --timing preserve|flat, --mask (per-register ignored byte
  indices), --bus-khz; per-unit PASS/MISMATCH with hex diff; exit code
  reflects the result.
- tests/test_ion_master.py: 29 checks incl. a firmware-emulating fake port.
- CROSS-VALIDATED: python encoders piped through the actual firmware C
  parser - byte-identical agreement (6/6 incl. noise resync + 64B max).

### Bench bring-up order (your side)
1. Flash the master variant; run: python3 tools/replay_compare.py --help
2. Sniff a window: flash sniffer variant, tools/record_on_trigger.py
   --trigger 0x08:W:3E --out cap.jsonl (your BQ76905 subcommand poll)
3. Reflash master, replay: tools/replay_compare.py cap.jsonl
   --mask mask.json (mask the measurement bytes)

Next: 4b (Exerciser app shell: Device tab with HELLO-probe finder + Replay
tab wrapping this compare logic).

---

# 2026-07-09 — Table / Filter update — scoped search, multiline bit fields, Int/ASCII columns

## Table / Filter Update — Delivery Notes

### 1. Column-scoped search [XREF: search-scope]
The Filters bar's search box gained an "in:" scope dropdown: "All columns"
(the previous time/addr/hex/ASCII behavior, still the default) or any single
column — including **Decode**, so you can search decoded rule names/values.
The frame-aware behavior is untouched by design and covered by a test: a hit
anywhere still reveals the entire exchange between the bounding NAKs
(start/stop context), whichever scope is active. Reset restores All columns.

### 2. Multiline bit fields + wrapped rows [XREF: row-wrap]
merged_schema() now defaults to multiline bit fields everywhere (the replay
window already had it; the sniffer windows regressed to single-line when the
decoder-manager flow was introduced — fixed at the source, and the legacy
single-file loader gets it too). The table wraps content instead of eliding
with "...", and each row is sized to its content as it arrives (26 -> 57 px
for a real BQ76905 safety register in the test).

### 3. Int / ASCII columns [XREF: int-ascii-cols]
Both interpretation columns are hidden by default; the Table Data section
gained "Show Int column" / "Show ASCII column" checkboxes (all three apps).

Tests: tests/test_table_ui_updates.py (20 checks, incl. the shipped BQ76905
decoder rendering multiline and scoped-search frame-context preservation).
Full regression: 10 suites + 4-app smoke all pass.

### Packaging change
From now on: ONE zip (ion_i2c_tool_full.zip) containing the complete
current state of the project — ion_i2c_tool/ with the apps at the root
and the firmware + protocol docs in embedded/. Unpack anywhere.

---

# 2026-07-09 — Launcher / install fixes + tree integrity

- run.sh: python3 (was python), venv-missing and app-missing guards with
  clean errors, argument-shift bug fixed (app name was passed to itself),
  defaults to sniffer_ion.py. install.sh's embedded run.sh generator emits
  the same fixed script so re-installs keep it; venv verification and
  summary use python3 / sniffer_ion.py.
- requirements.txt created (PySide6, pyserial, jsonschema) — pyserial is
  required by the ion sniffer and tools/; older venvs need one re-install.
- MANIFEST.sha256 + tools/check_tree.py ship in every delivery: verifies
  the working copy against the delivered file hashes and names stale/missing
  files (catches mixed-revision trees from partial unpacks / Finder folder
  replacement / git checkouts). Manifest tracks .py/.json/.md/.c/.h/.s/.ld/
  Makefile/.sh/.txt.
- Repository layout: parent renamed ion_i2c_tool; embedded/ (firmware +
  protocol docs) moved inside it; single-zip delivery (ion_i2c_tool_full.zip)
  with __MACOSX/. _* litter excluded.

---

# 2026-07-09 — Notes consolidation

Per-update *_NOTES.md files merged into this change_log.md (this file);
future update notes are appended here instead of new files.

---

# 2026-07-09 — decoder_editor.py entry point added

The standalone entry point was missing from the tree (absent from the
original project upload, like bq76905_gateway_tool.py) even though the docs
reference it; the editor window itself (ui/decoder_editor_window.py) was
always present and maintained. Added decoder_editor.py following the sibling
entry-point pattern, honoring the documented optional decoder-path argument
(python3 decoder_editor.py path/to/decoder.json).

---

# 2026-07-09 — Registers tab (Tab 1) + decoder schema v4

Live BQStudio-style Registers view in both sniffer apps, built entirely from
the decoder JSON (no decoder with layout info -> no tab). Replaces the first
slice of the retired bq76905_gateway_tool.

## Schema v4 (decoder JSON)
- File level: "display_groups": ordered [{name, kind: "banner"|"pane"}].
  Banner groups render as the headline strip (dividers between); pane groups
  render as side-by-side Name/Value/Units tables.
- Rule level: "group" + "group_order" place scalar rules (no group = not
  shown in the top zone); "access" ("R"/"W"/"R/W") now saved for ALL rules
  and drives the lock/pencil marker (and future Phase 4 write controls).
- format="bits" rules always join the Bit Registers matrix; 2-byte bit rules
  render as an inferred high/low row pair with the hex value on the high row.
- v3 files still load (no groups -> no tab); schema/decoder.schema.json
  updated; both shipped decoders validate.

## Live view (ui/widgets/registers_view.py)
- Passive last-seen-from-traffic: RegisterCache attaches to the merged
  schema's new on_rule_decoded observer, so it sees exactly what the log
  decodes — including replayed history when a decoder is loaded late.
  Values are sticky; unseen rows show "—". No staleness display by design.
- Bit matrix colors from the active theme: bit=1 red (status_error),
  bit=0 green (status_active), reserved gray (bg_tertiary) — RSVD_*-named
  fields gray out as reserved. Repaints on theme change.
- DecodeSchema additions: extract_value(rule, bytes) (engineering value for
  display) and the exception-safe on_rule_decoded hook in _render.
- DecoderSetManager.merged_schema now carries display_groups through the
  merge (first occurrence of a group name wins).

## Integration
- Both sniffer windows rebuild one tab per loaded decoder (tab title =
  device name) whenever the decoder set changes, inserted before
  Preferences; removing the decoder removes its tab.
- i2c_decoders/bq76905_decoder.json -> v4 with an authored grouping
  (Pack/IC banners; Cell Measurements / Current & Charge / Device Info
  panes; 17 rules) — REVIEW the grouping and adjust freely.

## Deferred (next update)
- Decoder Editor UI fields for group / group_order / access (the schema
  round-trips them today; the editor just can't edit them yet).
- Phase 4: polling + send/update buttons on this same tab, gated by access.

tests/test_registers_tab.py: 25 checks incl. window-level end-to-end
(sniffed traffic lighting the tab). Full regression green.

---

# 2026-07-09 — Decoder Editor: schema v4 support (closes the deferred item)

The editor can now author everything the Registers tab consumes.

## Rule form (Decoder tab)
- New DISPLAY (Registers tab) section: Group (editable dropdown fed from the
  schema's display_groups), Order (spinbox), Access ("", R, W, R/W).
  Collected on Add / Update Rule, restored on row click, reset by Clear;
  present in both editor layouts (standalone sections + embedded form).
- Rules table gained a Group column ("Pack (2)" = group + order).

## New "Display Groups" tab
- Manages the file-level display_groups list: Add (name + banner/pane kind),
  Remove, reorder (order here IS the on-screen order), in-place rename
  (cascades into every rule using the group), kind change via per-row combo,
  and a live per-group rule-usage count. Duplicate names rejected.
- Edits mutate the same live DecodeSchema the Decoder tab holds, so Save
  persists them; every change marks the document dirty and refreshes the
  rule form's Group dropdown. New/Load resets the tab.

Verified against the shipped v4 bq76905 decoder (5 groups / 3-3-5-3-3 rule
counts render in the tab). tests/test_editor_v4.py: 19 checks. Full
regression + 4-app smoke green.

Note: fixed in passing — a code-insertion mishap briefly detached the
@property decorator from DecodeEditor.schema; restored, with the groups tab
using a provider lambda.

---

# 2026-07-09 — Framework standard: tab pop-out (all applications)

Any main tab can be floated into its own top-level window and re-docked.
Standard across all four apps: the AppWindow apps (both sniffers, replay,
theme editor) get it from the base class; the decoder editor attaches the
same controller to its local tabs.

## Behavior
- Pop out: right-click the tab -> "Pop out", or double-click it. The tab
  leaves the bar and becomes its own window titled "<App> — <Tab>".
- Re-dock: close the floating window; the tab returns to its ORIGINAL
  position (nothing is destroyed). Closing the app first re-docks every
  float, so no orphan windows survive and teardown flows through the normal
  tab lifecycle.
- Exclusions: Device and Exit tabs never pop (AppWindow title rule; explicit
  poppable=False property available for any widget). Everything else pops,
  including per-device Registers tabs — the bench use case: float a device's
  Registers window next to the live Sniffer tab.
- Floated views stay fully live: signal wiring survives reparenting, the
  app-level stylesheet keeps theming them, and RegisterCache/LogPanel
  updates continue. Theme changes restyle floats automatically.
- Registers rebuilds are float-aware: if a device tab is floating when the
  decoder set changes, the rebuilt (fresh) view is re-floated; removing the
  decoder retires the floated tab entirely.

## Implementation
- ui/widgets/tab_popout.py: TabPopoutController (context menu, double-click,
  eventFilter close->dock, dock_all, floating_titles/pop_out_by_title for
  hosts that rebuild tabs).
- AppWindow: self.popout on every app; add_tab gained an optional poppable
  parameter (None = title rule); closeEvent sweeps floats after the
  confirm-close guard accepts.
- Both sniffer windows' _rebuild_register_tabs remember/re-float device tabs.

tests/test_tab_popout.py: 22 checks incl. live updates while floated and
rebuild-while-floated. Full regression (13 suites) + 4-app smoke green.

Not included (possible follow-ups): floated-state/geometry persistence
across runs; drag-tab-off-the-bar to detach.

---

# 2026-07-09 — BQ25731 decoder: full register map (schema v4)

i2c_decoders/bq25731_decoder.json regenerated from the SLUSE66A Rev A
datasheet (user-supplied PDF): the 8-rule starter template is replaced by
the complete map — 30 rules, 133 named bit fields.

- Extraction: register tables pulled structurally with pdfplumber (the
  layout-text route proved too fragile for wrapped field names); all 38
  per-byte field tables verified for full 8-bit coverage before generation.
- Sense resistors: ALL current scalings fixed for 10 mOhm RSR and RAC per
  the user's board (ChargeCurrent LSB 64 mA, OTG/IIN LSBs 50 mA, ADC ICHG
  64 mA / IDCHG 256 mA / IIN 50 mA). Halve mA for a 5 mOhm build — noted in
  the file description. PSYS/CMPIN assume ADC_FULLSCALE=1b (POR default).
- Numeric registers encode their bit placement in the function (e.g.
  ChargeCurrent ((X>>6)&127)*64) so reserved bits can't corrupt readings;
  read + "(set)" write rule pairs for every R/W register.
- ADC word registers (VBUS/PSYS, IBAT, IIN/CMPIN, VSYS/VBAT) are fields
  rules — and RegistersView now renders one pane row per DataField
  [XREF: registers-fields], so all 8 ADC channels appear individually
  (benefits the BQ76905 PASSQ row too). VBAT/VSYS carry the 2880 mV offset
  (1S-4S; 5S note in description).
- 11 bit registers (ChargeOption0-4, ProchotOption0/1, ChargerStatus,
  ProchotStatus, ADCOption, Vmin Active Protection) with high/low row pairs
  in the Registers tab; reserved bits gray automatically.
- v4 layout: banners "Charge Settings" + "Input"; panes "ADC Measurements",
  "OTG", "Device Info".
- tests/test_bq25731_decoder.py: 37 checks pinned to datasheet vectors
  (ChargeVoltage resets 0x41A0/0x5208, IIN_DPM reset 0x4100 -> 3250 mA,
  OTGVoltage reset -> 5000 mV, EC-table ChargeCurrent code, bit positions
  incl. a wrapped-name rejoin) so scaling edits can't slip through silently.

---

# 2026-07-09 — Field-capture fix: restart-phase corruption + BQ25731 write rules

User capture (POC_i2c_sys_with_bq25731_testX.csv) showed zero decodes after
the bus sweep found the part. Two causes, both fixed.

## 1. Firmware: sampling stall corrupted every repeated-START phase
The capture's restart phases decoded at 0x5C/0x5D (dir sometimes W) instead
of 0x6B — yet ACKed, so the wire was fine and the sniffer was misdecoding.
Root cause: the bit-bang hot loop encoded + enqueued the UART frame INLINE
when a phase completed; that stall swallowed the repeated-START setup and
the first address bits of the immediately-following phase (a register
read's Sr gap is only microseconds). StreamDecoder then had no same-address
read to pair with the pointer write -> no decodes.

Fix [XREF: deferred-emit]: completed transactions are now queued (8-deep
ring, ~80 B struct copy, sub-microsecond) and encoded to UART only while
the bus is idle (>=20 us quiet, not mid-transaction) or under ring
pressure; capture-stop drains the ring. Reproduced and pinned in
tests/host/test_i2c_decoder.c: continuous sampling decodes the
write+Sr+read pattern cleanly, and a post-phase sampling stall at any gap
size corrupts the restart phase (46 checks). All three firmware variants
build 0-warning. REFLASH the sniffer firmware to pick this up.

## 2. Decoder: no write rules for the bit-config registers
The capture's clean config writes ([00 0A 67] etc.) matched nothing —
bit registers only had read rules. Added 11 "(set)" hex write rules
(ChargeOption0-4, ProchotOption0/1, ChargerStatus, ProchotStatus,
ADCOption, Vmin Active Protection) -> 41 rules. Replaying the user's exact
CSV now decodes the three config writes; a post-fix traffic simulation
shows IDs, status bit fields, and ADC channels all decoding.

Caveat noted: the POC host reads registers one byte at a time; a 1-byte
read decodes against the word rule with the high byte absent (fields
render as 0 / VBUS-style offset-1 channels show no value). Reading full
16-bit words is recommended and matches the datasheet's word-oriented map.

---

# 2026-07-09 — Smoke capture v0.3 review: VSYS/VBUS missing — three causes

Capture POC_i2c_sys_bq25731_smoke_v0_3.csv reviewed. The decoder JSON was
not the blocker; three stacked causes, two fixed here, one is a host change.

1. OLD FIRMWARE STILL FLASHED. The capture shows the identical restart
   corruption signature as the previous one (Sr phases at 0x5C/0x5D,
   byte-identical misdecodes for the same host sequence) — the deferred-emit
   fix is not running on the board. Firmware version bumped to 1.1 so the
   flashed build is verifiable: after reflashing, the app status bar must
   say "fw 1.1". If it says 1.0, the reflash didn't take.

2. THE HOST NEVER READS VBUS/VSYS. Zero 2-byte word reads and zero reads of
   the odd registers in 1663 rows: the host polls single bytes at 0x26
   (=PSYS), 0x2C (=VBAT), 0x2A (=CMPIN) and the status low bytes. VBUS is
   register 0x27 and VSYS is 0x2D — those bytes never cross the bus, so no
   firmware or decoder can show them. Host fix: read 16-bit words at the
   even base (recommended, matches the datasheet map) or read 0x27/0x2D
   explicitly.

3. Decoder additions for byte-at-a-time hosts: 7 single-byte alias rules
   (0x21/0x23 status high as hex, 0x25 IIN_DPM, 0x27 VBUS, 0x29 ICHG,
   0x2B IIN, 0x2D VSYS) -> 48 rules. Log decode only; word reads at the
   even base drive the Registers tab.

Also fixed while proving this out: a truncated fields payload (1-byte read
of a word register) used to FABRICATE offset-1 values from missing bytes
("VSYS = 2880 mV" from 0*64+2880) — now renders "VSYS = — (byte not read)".
New vectors in tests/test_bq25731_decoder.py (48-rule count, three alias
conversions, honest-absence check).

---

# 2026-07-09 — Smoke v0.4: stop-separated register reads now decode

Capture POC_i2c_sys_bq25731_smoke_v0_4.csv confirmed fw 1.1 is running
(restart corruption gone, correct data on the wire) and the host now reads
16-bit words. Remaining blocker was in the DECODE ENGINE, not the decoder
JSON: the host uses stop-separated register reads (W [reg] P, then S R),
while StreamDecoder only paired pointer->read across a repeated START.

Fix (core/decode_schema.py, StreamDecoder): the register pointer now
persists across STOP, matching real register-map devices —
- a single-byte write is a pointer set whether or not it ended in STOP;
- an indexed write leaves the pointer at its register, so a read-back
  verify decodes;
- the pointer is consumed by the read (no stale re-decodes).
Both host styles are covered by regression checks (restart/BQ76905 style
and stop-separated/BQ25731 style, using the user's actual capture bytes).

Replaying the v0.4 capture: 569 of 1231 rows decode (previously 4) —
Manufacturer/Device ID, ChargerStatus/ProchotStatus with full bit fields,
ChargeOption0/1 read-backs and (set) writes, and the asked-for values:
VBUS = 15072 mV, VSYS/VBAT = 2880 mV (offset floor, converter idle),
IIN/CMPIN = 0.

Polish: multi-bit raw bit fields now render named ("WDTMR_ADJ=3" instead
of a bare "3") — 15 fields in the BQ25731 JSON gained names; the bit-matrix
label lookup prefers the field name.

---

# 2026-07-09 — Bit-matrix coloring rule v1.1 (registers_view [v1.1])

New field-value coloring in the Registers tab's Bit Registers matrix,
replacing the BQStudio-style bit-high-red / bit-low-green scheme:

- A bit field with value != 0 colors GREEN; value == 0 colors RED.
- Fields WIDER than one bit take their cell background directly from the
  value as 24-bit RGB (all cells of the field share it). If that color sits
  too close to the widget background to be visible, its complement is used;
  text switches black/white by cell luminance. Zero-valued wide fields are
  red like any other zero.
- Reserved cells stay gray; cells with no observed value are now NEUTRAL
  gray with normal text (previously green, which under the new semantics
  would have falsely read as "set").
- Legend updated: Set (≠0) green | Zero red | RSVD gray. Colors remain
  theme-token based and repaint on theme change.

Note: small multi-bit values map to near-black RGB and will usually render
as the near-white complement on dark themes — that is the literal
value-as-RGB rule working as specified; if a scaled mapping (e.g. hue
rotation across the field's range) reads better on the bench, it is a
one-function change in RegistersView._field_color.

Tests updated to the new rule (registers tab + BQ25731 suites) plus new
vectors: field-shared color, #000003 -> #FFFFFC complement, luminance text,
zero-wide-field red. Full regression + smoke green.

---

# 2026-07-09 — Registers tabs in the replay window (+ shared host mixin)

Report: "running i2c_replay, no bit fields > 0 are green." Root cause:
ReplayWindow never had the Registers tabs — they were only wired into the
two sniffer windows, so replay showed no v1.1 coloring at all (anything
red-looking there was a stale tree; run tools/check_tree.py to confirm a
sync).

- ui/widgets/registers_tabs_host.py [v1.0]: the per-device tab rebuild
  (layout gate, float-aware teardown/re-float, insert before Preferences,
  cache attach) extracted into a RegisterTabsHost mixin — the three copies
  of this logic in the windows are now one.
- ReplayWindow uses it: loading a capture + decoders populates the device
  tabs from the capture rows (the cache rides the model re-decode), with
  the v1.1 coloring. This is the natural offline bench for the tabs.
- End-to-end test with the user's actual v0.4 CSV in the replay window:
  BQ25731 tab appears, ChargerStatus = 0x8200 from the capture,
  STAT_AC=1 GREEN, ICO_DONE=0 red, VBUS = 15072 mV in the ADC pane.
- Fixed during the refactor: an import splice broke the multi-name
  ui.widgets import in ALL THREE windows (replay caught by the new test;
  the sniffers slipped past a too-narrow grep check and were caught by the
  full regression before delivery). All 12 suites + smoke re-run green
  after the fix.

Reminder on v1.1 semantics: zero-valued fields are RED by design — an idle
charger legitimately shows a mostly-red matrix; only fields with non-zero
values go green (or value-RGB when wider than one bit).

---

# 2026-07-09 — PROJECT VERSION 1.0.0

Project major set to 1.0 (project conventions). Single source of truth:
version.py -> PROJECT_VERSION = "1.0.0"; build_application defaults to it,
so every app reports it via QApplication.applicationVersion, and the
hardcoded per-app version strings are gone.

v1.0.0 comprises: the four applications + theme editor on the shared
AppWindow/theme/settings framework; decoder schema v4 (display groups,
rule group/order/access, fields, bit fields) with BQ76905 and full BQ25731
(48 rules) decoders; live per-device Registers tabs (v1.1 field-value
coloring) in both sniffers and the replay window; framework-wide tab
pop-out; probe firmware 1.1 (bit-bang deferred-emit fix, master transport);
stream decode supporting restart and stop-separated register reads;
MANIFEST.sha256 + check_tree.py delivery verification; 12 test suites +
4-app/4-theme smoke + host-C firmware tests.

Component versions intentionally separate: probe firmware (1.1, HELLO/status
bar), decoder JSON format (schema version 4), per-file [vX.Y] module tags.
Bump rules recorded in version.py.

---

# 2026-07-09 — v1.1.0: replay scrub — device tabs track the selected row

Selecting a row in the replay data table now replays register state UP TO
that transaction (inclusive) into the device Registers tabs — a true
replay. Per the user's example on smoke v0.4: the row before the first
read shows no values set; the ID-read row (~19:52:47.479) shows
Manufacturer ID 0x40 / Device ID 0xD6; by the ChargerStatus read the bit
matrix shows 0x8200 with STAT_AC green. Scrubbing backward rewinds;
clearing the selection restores full-capture state.

- ui/log_panel.py [v1.1]: row_selected(int) signal — SOURCE entry index
  via the model's visible-row mapping, so active filters don't skew the
  scrub position; -1 on selection clear.
- ui/widgets/registers_tabs_host.py [v1.1]: _replay_registers_to(entries,
  row) — clears the cache and re-feeds transactions [0..row] through a
  fresh StreamDecoder over the merged schema (same decode path as the
  log; ~ms for thousands of rows).
- ui/widgets/registers_view.py [v1.2]: RegisterCache.cleared signal;
  views reset every cell to the unseen state on clear.
- ui/replay_window.py [v1.1]: wires selection -> scrub.

Clarified from the report: the replay DATA TABLE keeps its direction
coloring (red = read rows, blue = write rows) by design; the v1.1
field-value coloring lives in the per-device Registers tabs, which now
follow the selected row.

PROJECT_VERSION 1.0.0 -> 1.1.0 (feature, per version.py bump rules).
Six new scrub checks in tests/test_bq25731_decoder.py incl. real table
selection emitting the correct source index; 12 suites + smoke green.

---

# 2026-07-09 — v1.2.0: BQ76922 decoder (full direct-command map) + BQ769x2 subcommand flow

New i2c_decoders/bq76922_decoder.json: 74 rules, 154 named bit fields, for
the TI BQ76922 3s-5s monitor/protector (BQ769x2 family, I2C 0x08).

## Sources and provenance (recorded per rule in its description)
The BQ76922 DATASHEET does not contain the register map — it defers to the
Technical Reference Manual (SLUUCG7, April 2024). The TRM was fetched from
TI and provided verbatim: all six Safety Alert/Status A/B/C bit tables,
every 16-bit measurement command with units (cells 0x14-0x1C in mV; Stack/
PACK/LD 0x34/0x36/0x38 in userV, default 10 mV; CC2 0x3A in userA;
temperatures 0x68-0x72 raw 0.1 K -> decoded to degC), the full subcommand
protocol (0x3E/0x3F + buffer 0x40-0x5F + checksum 0x60 / length 0x61),
DASTATUS1/2/5/6 byte maps (DASTATUS5/6 modeled as per-field rules),
Manufacturing Status bits, and the FET test/control subcommand set.
Registers whose chapter-12 tables were beyond fetch reach (Battery Status,
Alarm Status/Raw/Enable, Control Status, PF A-D, FET Status upper bits) use
the BQ769x2 family-standard layout — cross-validated against the project's
BQStudio reference screenshot and the TRM's own Permanent-Fail list — and
are marked "family standard; verify vs SLUUCG7 §12.2" in their
descriptions. Data-memory (RAM/OTP settings) traffic appears as
subcommand+buffer transfers and is intentionally not individually named.

## Engine: BQ769x2 subcommand read-back flow [XREF: subcmd-buffer]
StreamDecoder now routes a read pointed at the TRANSFER BUFFER (subcommand
reg + 2, i.e. 0x40) to the pending subcommand as an unframed payload — the
TRM's efficient read flow — and the pending subcommand persists across the
0x3E echo poll (it is replaced by the next subcommand write), matching
device behavior. Reads starting at 0x3E keep the existing block-framed
decode with checksum/length verification.

## Layout (v4)
Banners: Pack Measurements (Stack/PACK/LD/CC2), IC Measurements (Int Temp).
Panes: Cell Voltages (1-5), Temperatures (CFETOFF/DFETOFF/ALERT/TS1/TS2),
Device Info (DEVICE_NUMBER/FW_VERSION/HW_VERSION). 21 bit registers in the
matrix incl. 16-bit pairs (Battery Status, Alarm set, Control Status).

tests/test_bq76922_decoder.py: 27 checks — TRM vectors (0.1 K conversion,
signed cells/CC2, Safety table positions incl. Alert-C PTOS vs Status-C
PTO/HWDF distinction), stream decode of direct reads + RESET subcommand +
DASTATUS5 fields through the 0x40 buffer path, and the Registers view
rendering (Battery Status 0x8000 -> SLEEP green). Full regression green.
PROJECT_VERSION 1.1.0 -> 1.2.0.

---

# 2026-07-09 — v1.2.1: capture CSV format specified + validator

Question answered: there was NO schema for the replay/capture CSV — the
format existed only implicitly in core/log_model.py (writer) and
ui/common/capture.py (reader). Now normative:

- documents/CSV_FORMAT.md — capture CSV v1: exact header, per-column
  format and semantics, canonical vs informational split (canonical:
  Time, Addr, Dir, Data, NAK, Start, Stop, PEC — authoritative on load;
  informational: #, Len, Int, ASCII, Decode — regenerated), the traps
  (Addr always 7-bit, Int always big-endian by convention, positional
  pointer/read pairing, zero-length probe rows), a minimal external-
  producer example, and the versioning rule (header row is the version
  signature).
- tools/validate_capture_csv.py [v1.0]: header + per-row canonical
  validation; --strict cross-checks #, Len, Int as the sniffers produce
  them. Both real smoke captures validate strict-clean (v0_4: 1231 rows,
  v0_3: 1663 rows); a fresh model export round-trips; corrupted rows are
  rejected.
- core/log_model.py: [XREF: csv-format] marker at COLUMNS so the writer,
  the spec, and the validator reference each other; replay user guide now
  points at the spec.
- tests/test_csv_format.py: 5 checks (export->strict-validate, real
  capture, corruption rejection, loader round-trip incl. PEC restore).

PATCH bump (documentation + auxiliary tooling; no runtime behavior
change). PROJECT_VERSION 1.2.0 -> 1.2.1.

---

# 2026-09-21 — Remediation program plan (documents/plans/)

External review (20260921_fix_list.md) triaged into seven sequenced work
orders under documents/plans/, each named for the model intended to
execute it. No code changed in this entry.

Claims were re-verified against v1.2.1 rather than taken on trust:
B1 (schema `if` without `required` rejects format-less rules), B2 (to_json
drops device/description/i2c_address/i2c_address_hex/byte_order_note —
worse than reported), B3 (empty bit_fields dropped), B14 (registers tabs
still filter by min(addresses); 0x08 collision real), and C1 (version.py
1.2.1 vs app_info 1.0.0) all reproduce. M1 is PARTIALLY DONE by the
2026-07-09 CSV_FORMAT.md + validator work; only the machine-readable
schema, version marker, legacy 11-column reader and sidebar wiring remain
(Phase 4).

New feature scheduled in Phase 2: a Decoder Inspector ("View Decoder" on
the Replay tab plus a CLI), generating the decoder's rule/bit-field/
subcommand inventory, an explicit "what to expect in replay" section
showing the wire pattern per rule, and a generated sanity checklist. It
productizes the hand-written IP5385 sanity-check package.

Deferred pending scope decisions (product questions, not defects): M3, M5,
M8, C2, C3, C4, R1-R8.

---

# 2026-09-28 — v1.3.0: probe fw 1.2 (repeated-START bit-slip fix) + Sniffer controls

## Bug: first SCL edge after every repeated START lost (fw 1.1)

Field capture i2c_capture/"working test 1.csv" (Neware polling a pack at
7-bit 0x10, SBS ChargingCurrent 0x14): 334 of 338 Read Word phases logged as
`Sr W 0x21 [00 03|05]`, no NAK, instead of `Sr R 0x10 [00 01|02] NAK`.
Reported bytes = (real << 1 | next bit): address bit 7 was never sampled.

Root cause: at the Sr, finish_txn() copied the record (txn -> out) and
main.c then struct-copied ~76 bytes into its ring. The copy compiled to
newlib-nano's byte-wise memcpy-stub, stalling the sampler ~20 us. The bus
ran at ~47 kHz (derived from device timestamps: S->Sr share a millisecond in
199/338 pairs => ~0.41 ms for ~19.5 bits), so the stall covered SCL
low->high of address bit 7; SDA was already low, so the IDR-change gate
never saw it. fw 1.1's deferred-emit moved the UART encode out of this
path but not the copy. Reproduced exactly on the host decoder (stall of
0.75-1.6 bit periods). Not related: the pack at 0x10 is a Neware channel
setting (decimal 16 entered for 8-bit 0x16), not a probe error.

Fix (FW_VERSION 1.1 -> 1.2):
- i2c_bitbang_decoder [XREF: zero-copy-ring]: records are assembled in
  place in a decoder-owned ring (I2C_DEC_RING_DEPTH = 8 in
  sniffer_config.h); closing one only advances an index. New API
  i2c_dec_peek / i2c_dec_pop / i2c_dec_pending; `txn` / `out` removed;
  new event I2C_DEC_EVT_DROPPED when the ring is full. memcpy is no longer
  linked into the image at all. RAM: 10 record slots -> 8.
- Framing check: bit_count must be exactly 1 at a STOP / Sr (the setup SCL
  rise). Anything else sets the new i2c_txn_t.framing and TXN flag bit 6
  FRAMING (PROTOCOL.md updated; older hosts ignore it).
- Missed-START detection: SCL falling with no open transaction raises
  I2C_DEC_EVT_BUS_ERROR once per lost transaction (was never emitted).
- main.c: IDR masked to SCL|SDA (UART TX / LED toggles no longer count as
  bus activity); frames flush only between transactions - the old ring-
  pressure path could encode mid-transaction, reintroducing the stall.
  Framing-flagged frames and missed STARTs count in STATUS `errors`.
- Host: ion_protocol FLAG_FRAMING + TxnRecord.framing (default False);
  ion_backend reports "framing error at 0x.." per flagged phase.

Tests: embedded/tests/host — decoder 67 checks (new: exact
working-test-1 signature under a stall + framing flag on every corrupted
restart for stalls 0..60 samples, zero-copy ring FIFO/drop, missed START),
frame_protocol 71 checks (FRAMING bit). Firmware builds warning-free in
all three SNIFF_MODEs. NOT yet verified on hardware: reflash and repeat
the Neware capture.

## Sniffer tab — I2C Sniffer (Passive) section

- Start Sniffing / Stop Sniffing share one row at exactly equal width
  (ui/sniffer_panel.py _EqualWidthRow; a QHBoxLayout left a 1 px
  difference). Shared panel: the AD2 sniffers get the same row.
- New "SCL: 47.6 kHz" readout beside the Idle/Sniffing indicator, fed by
  STATUS bus_hz (SnifferPanel(show_bus_clock=True) + set_bus_hz(); hidden
  in the AD2 sniffers, which have no measurement). Reset to "—" on Start.
  The status-bar "bus ≈" now uses the same 0.1 kHz format.
- tests/test_ion_protocol.py: FRAMING decode, button row geometry, clock
  readout placement and STATUS-driven value.
- User_Guide_sniffer_ion.md: controls, SCL readout, framing-error
  troubleshooting row.

## Tooling

- tools/check_tree.py: `.venv` added to EXCLUDE_PARTS (a local venv put
  864 site-packages files into the regenerated manifest). Manifest
  regenerated.

MINOR bump (features + backward-compatible protocol flag).
PROJECT_VERSION 1.2.1 -> 1.3.0.

---

# 2026-09-30 — Program Phase 1 (loopback DUT) — session bootstrap

| File | Version | Change |
|---|---|---|
| CLAUDE.md | 1.0 (new) | Project working agreement: program decisions D-01..D-06, Phase 1 owner answers, H533 findings, baseline |
| loopback_dut/docs/setup_guide.md | v0.3 (new) | Rig topology, wiring, CubeMX settings for NUCLEO-H533RE, bash verification checks, shared `config/rig.toml` |
| tests/test_neware_doc_conformance.py | v1.1 | Reads its inputs from their real locations: `documents/decoders/Smart Battery Registers.txt`, `i2c_decoders/neware_decoder.json`, `i2c_decoders/smbus1v1_decoder.json` (was `tests/…`) |
| documents/decoders/neware_decoder.md | — | References updated to the real paths of the Neware reference and the SBDS decoder |
| documents/decoders/sbds1v1_decoder.md | — | Reference updated to the real path of the Neware reference |
| plan_n_exe/00_MASTER_PLAN.md | — | §5.2 criterion 5: "All three decoders" → all `i2c_decoders/*.json` (nine as of today) |

Why: Phase 1 bootstrap (P1-T0). The owner decided that the loopback DUT is a standalone,
isolated NUCLEO-H533RE (I2C1 master with own address 0x08, I2C2 slave 0x6B, I2C3 slave 0x55;
0x08 is the address-NAK case; all addresses adjustable through one shared config), and that
decoder JSON and the Neware reference stay where they are.

Evidence: baseline in `.venv` (Python 3.12.13) on the working tree including uncommitted
changes. Before the test fix, 16/17 `tests/test_*.py` passed; the only failure was
`test_neware_doc_conformance.py` with `FileNotFoundError: …/tests/Smart_Battery_Registers.txt`.
After the fix, 17/17 passed (neware: `OK: 0 failure(s)`, also when run from `/tmp`).
`smoke_test.py` is 8/9 (missing `bq76905_gateway_tool`, Phase 10). Skips: 2 in
`test_bq25731_decoder.py` and 1 in `test_csv_format.py` (captures not present). The path fix is
an owner-approved exception to D-06 (it overlaps review item C9). No tool behaviour changed.

---

# 2026-09-30 — Per-transaction SCL measurement (probe fw 1.3) + capture CSV v2

| File | Version | Change |
|---|---|---|
| embedded/sniffer_nucleoC0_fw/Core/Inc/sniffer_config.h | v0.1 | FW 1.2 → **1.3**; new guarded `I2C_DEC_SCL_MIN_PERIODS` (default 4) |
| embedded/sniffer_nucleoC0_fw/Core/Inc/i2c_bitbang_decoder.h | v0.1 | `i2c_txn_t` gains raw `scl_sum_us`/`scl_cnt`; per-phase accumulator state; `i2c_scl_hz()` / `i2c_txn_scl_hz()` helpers |
| embedded/sniffer_nucleoC0_fw/Core/Src/i2c_bitbang_decoder.c | v0.1 | Per-phase SCL measurement: mean of rise-to-rise periods ≤ 1.5× the phase minimum, reset at START/Sr; `i2c_dec_bus_hz()` = last measured phase (was a sticky shortest period) |
| embedded/sniffer_nucleoC0_fw/Core/Inc/frame_protocol.h | v0.1 | `FRAME_MAX_ENCODED` +4 |
| embedded/sniffer_nucleoC0_fw/Core/Src/frame_protocol.c | v0.1 | TXN frame appends `u32 scl_hz` after the data |
| embedded/sniffer_nucleoC0_fw/Core/Src/sniffer_slave_monitor.c | v0.1 | Clears the new fields (slave-monitor: not measurable) |
| embedded/sniffer_nucleoC0_fw/Core/Src/i2c_master.c | v0.1 | Clears the new fields (master: not measured) |
| embedded/sniffer_nucleoC0_fw/build/* | — | Rebuilt, default BITBANG, fw 1.3 |
| embedded/tests/host/waveform_gen.h / .c | v0.1 | `wg_init_ns()` (sub-µs sampler, 1 µs timestamp floor), `wg_stretch_next_byte()`; original timestamps unchanged |
| embedded/tests/host/test_i2c_decoder.c | v0.1 | 4 new SCL tests + exact-value check on the old estimate test |
| embedded/tests/host/test_frame_protocol.c | v0.1 | TXN length/offset of `scl_hz`, 0-byte and max-size frames |
| core/ion_protocol.py | v0.1 | `TxnRecord.scl_hz`; `decode_txn` reads the trailing field when present |
| core/i2c_controller.py | v0.1 | `I2CTransaction.scl_hz` (+ `scl_hz_str`) |
| core/ion_backend.py | v0.1 | Relays `scl_hz` into `I2CTransaction` |
| core/log_model.py | v0.1 | Column `SCL (Hz)` (appended; table header "SCL", cells in kHz, tooltip exact Hz); JSON export `scl_hz` |
| ui/log_panel.py | v1.2 | Default width for the new column |
| ui/common/capture.py | v0.1 | Loader reads `SCL (Hz)` (v2) and still loads v1 |
| tools/validate_capture_csv.py | v1.1 | Accepts v1 and v2 headers; validates the SCL cell |
| tests/test_ion_protocol.py | v0.1 | Trailing-field decode cases; link relays `scl_hz` |
| tests/test_csv_format.py | v0.1 | v2 header, SCL round trip, load→re-export identical, v1 compatibility, bad SCL rejected |
| version.py | v1.1 | PROJECT_VERSION 1.3.0 → **1.4.0** |
| embedded/docs/PROTOCOL.md | — | TXN `scl_hz` field, §1.1.1 measurement method and accuracy, STATUS `bus_hz` semantics, UART cost 17 + dlen |
| documents/CSV_FORMAT.md | — | Capture CSV **v2** (trailing `SCL (Hz)`), versioning table |
| documents/User_Guide_sniffer_ion.md, User_Guide_i2c_replay.md | — | SCL column and readout; troubleshooting rows |
| loopback_dut/docs/setup_guide.md | v0.4 | §5 updated: C031 SCL measurement implemented |

Why: the owner directed that the loopback DUT's PC software sets the SCL frequency and that
the C031 sniffer detects and reports it, with a per-transaction `scl_hz` CSV column that the
replay app displays. That lets the Phase 1 harness check speed case by case. This is an
owner-directed exception to Phase 1's "no tool behaviour change" and to D-06 (the CSV change
overlaps M1, Phase 6).

Design notes: the old estimate (1e6 / shortest period since capture start, 1 µs resolution)
stayed stuck after a speed step down and quantised 400 kHz to 333 or 500 kHz. The division is
kept out of the sampler: the decoder stores a raw sum and count, and Hz is computed in
`frame_encode_txn` (main loop) and `i2c_dec_bus_hz` (1 Hz STATUS). Disassembly of the BITBANG
image shows `__udivsi3` called only from those two functions, and `i2c_dec_sample` makes no
calls at all. The TXN frame costs 4 more bytes (UART 13 + dlen → 17 + dlen). Old hosts ignore
the field; new hosts treat its absence as unknown.

Evidence:
- Firmware host tests before → after: decoder 67 → 86 checks, frame_protocol 71 → 80, 0
  failures. Simulated 400 kHz reads 402 985 Hz (+0.75 %).
- Builds (arm-none-eabi-gcc 15.2), 0 warnings, before → after: BITBANG text 4540 → 4880 /
  bss 8500 → 8588; SLAVE_MON 4076 → 4436 / 7908 → 7916; MASTER 4668 → 5040 / 7900 → 7908.
- Python: 17/17 `tests/test_*.py`; `smoke_test.py` 8/9, unchanged.
- The replay window, driven offscreen with a v2 CSV, shows header "SCL" and cells
  `400.3 kHz` / `399.9 kHz` / blank.
- 13 of the 15 shipped `i2c_capture/*.csv` validate. The two `EVM_*` files use a pre-existing
  11-column legacy layout (no Int/Decode) that v1 already rejected (M1, Phase 6).
- **Not yet measured on hardware.**

---

# 2026-09-30 — Phase 1 P1-T1 (pattern + rig config) and P1-T2 (loopback DUT firmware)

| File | Version | Change |
|---|---|---|
| loopback_dut/config/rig.toml | v0.1 (new) | Shared rig parameters: responders R1 (I2C2 0x6B) / R2 (I2C3 0x55), NAK target 0x08, speed, rise/fall, compare tolerances, DUT port |
| loopback_dut/schema/loopback_pattern.schema.json | v0.1 (new) | Pattern schema; every conditional `if` carries `required` (B1 lesson); per-path status (ion/ad2) |
| loopback_dut/patterns/loopback_v1.json | v0.1 (new) | Golden pattern LB-01..LB-15; xfail ledger B8 (LB-04), B9 (LB-07), B10 (LB-09, AD2 only), B13 (LB-06) |
| loopback_dut/tests/test_pattern_schema.py | v0.1 (new) | T1: schema valid, pattern valid, ledger, phase counts, 16 reject / 4 accept mutations, rig.toml ↔ firmware defaults |
| loopback_dut/firmware/App/Inc/loopback_config.h | v0.1 (new) | Guarded DUT defaults (kernel clock, speed, rise/fall, addresses, limits) |
| loopback_dut/firmware/App/{Inc,Src}/dut_regmap.* | v0.1 (new) | Synthetic register map (word region + BQ769x subcommand block) and SMBus CRC-8 |
| loopback_dut/firmware/App/{Inc,Src}/dut_timing.* | v0.1 (new) | TIMINGR calculator for any SCL 8 kHz–400 kHz from the 64 MHz kernel clock |
| loopback_dut/firmware/App/{Inc,Src}/dut_proto.* | v0.1 (new) | PC↔DUT line protocol parser + CRC line sealing |
| loopback_dut/firmware/App/{Inc,Src}/dut_app.* | v0.1 (new) | Hardware glue: I2C1 master (HAL Seq IT), I2C2/I2C3 listen-mode responders with PEC and byte-boundary stretch, USART2 line I/O, SYNC pulse, LD2 heartbeat, ALERT wired only |
| loopback_dut/firmware/GNUmakefile | v0.1 (new) | Build entry point; includes the CubeMX Makefile and adds App/ (survives regeneration) |
| loopback_dut/firmware/Core/Src/main.c | USER CODE tag v0.1 | Hooks `dut_app_init()` / `dut_app_poll()` in USER CODE regions; CubeMX BSP demo printf removed. Tag lives in the USER CODE Includes region (generated-file policy) |
| loopback_dut/tests/host/{Makefile,test_dut_regmap.c,test_dut_timing.c,test_dut_proto.c} | v0.1 (new) | T1 host tests for the three pure modules |
| loopback_dut/docs/PROTOCOL.md | v0.1 (new) | Normative DUT line protocol, register map, behaviour notes, example session with real CRCs |
| loopback_dut/docs/setup_guide.md | v0.6 | §4.0 H5 project done, §4.3 PLL3R accepted, §9 build/flash/first bench check with exact expected lines |

Why: PHASE_01 tasks P1-T1 and P1-T2, following the owner decisions of 2026-09-30:
- the DUT is a standalone NUCLEO-H533RE (I2C1 master, I2C2 slave 0x6B, I2C3 slave 0x55),
  isolated from the sniffer tools;
- 0x08 is the address-NAK case;
- addresses come from one config file shared by the DUT PC software and the validation script.

Design notes:
- **I2C1 own address.** Matching for I2C1's own address (0x08) is disabled at start-up, so the
  master can never ACK or stretch itself, and 0x08 NAKs deterministically.
- **Clock stretch** is at byte boundaries: the HAL clears ADDR / loads TXDR only after the
  callback returns (checked in `stm32h5xx_hal_i2c.c` `I2C_ITAddrCplt`). A hardware slave cannot
  stretch mid-byte, so LB-14 is defined at a byte boundary.
- **Deviations from PHASE_01:**
  - the pattern/schema/config live under `loopback_dut/`, not `tests/patterns` / `schema/`, and
    DUT firmware is `loopback_dut/firmware`, not `embedded/loopback_dut_fw` (isolation decision);
  - `tools/loopback_run.py` will be `loopback_dut/host/loopback_run.py` (T3);
  - the driver does not use `core.ion_master`, so there is no B12 desync evidence from it.

Evidence:
- DUT host tests: regmap 18, timing 301, proto 40 checks, 0 failures.
- The timing model puts CubeMX's generated 100 kHz TIMINGR values (0x40703444 / 0x30803E58)
  at 99 453 / 99 763 Hz. Computed 100 kHz = 0x20B56464 (predicted 100 075 Hz); 400 kHz =
  0x10C81429 (401 204 Hz).
- `test_pattern_schema.py` passes 56 checks. Re-introducing the B1 mistake (dropping `required`
  from the path_status `if`) makes the golden pattern fail with 22 errors, so the checks are
  sensitive.
- The firmware protocol CRC matches an independent Python CRC on the PROTOCOL.md vectors (HELLO
  `*BF`, PH `*CB`).
- DUT firmware builds with 0 warnings (text 39 316 B, data 112 B, bss 5 064 B). Callbacks link
  as strong symbols over the HAL weak defaults.
- Project suite unchanged: 17/17 `tests/test_*.py`, smoke 8/9, sniffer host tests 86 + 80.
- Isolation: no `core`/`ui` imports and no sniffer firmware headers under `loopback_dut/`;
  nothing in the tools references `loopback_dut`.
- **Not yet run on hardware** (flash + setup_guide §9.4 are the P1-T2 bench criteria).

---

# 2026-09-30 — Loopback DUT decoder (sniffer-side fixture) + C031 fw 1.3 confirmed on the rig

| File | Version | Change |
|---|---|---|
| i2c_decoders/loopback_dut_decoder.json | (new; decoder format version 4) | 12 rules for the DUT register map (PROTOCOL.md §4): R1 0x6B words 0x00–0x08 (LE hex), writes 0x0A/0x10, `simple_write` for LB-04 (no indexed rule at 0x20), subcommand 0x0001 block; R2 0x55 word 0x02/0x10, write 0x10 |
| documents/decoders/loopback_dut_decoder.md | (new) | Register table (skill `decoder_to_markdown.py`) + provenance / defects |
| i2c_capture/loopback_dut_replay_check.csv | (new) | Synthetic capture CSV v2, 20 rows, real DUT values; expected decode in the Decode column |
| tests/test_loopback_dut_decoder.py | v0.1 (new) | Vectors LB-01/02/03/07/09/15, replay-check comparison, expected failures B8 (LB-04) and **B29** |
| loopback_dut/patterns/loopback_v1.json | (desc v0.1) | LB-04 expected text corrected to the engine's `Name = value` form: "LB simple write = 0x20" |
| plan_n_exe/00_MASTER_PLAN.md | — | §5.2 criterion 5 count: ten decoders |

Why: the owner approved `i2c_decoders/loopback_dut_decoder.json` (the default decoder location),
so LB-04/B8 is exercisable. The owner also confirmed that the C031 Nucleo now runs sniffer fw
1.3.

New finding **B29** (engine): `DecodeSchema` renders a truncated payload as a value (a 2-byte rule
on 1 byte → `0x0002`) instead of absent. The test records it as an expected failure.

Tool defects (not fixed):
- the skill's `make_replay_check.py` puts multi-address rules on the file-level address;
- its `validate_decoder.py` tool-load step fails for every decoder, because `DecodeSchema` keeps
  no `device` attribute (B2 area).

Evidence:
- The decoder validates (repo schema 0 errors; skill schema, constraint and lint OK).
- All ten decoders validate.
- `test_loopback_dut_decoder.py`: all pass, including 20/20 replay rows (B8 row as xfail).
- Project suite 18/18, smoke 8/9.

---

# 2026-09-30 — Phase 1 P1-T3 (host driver), P1-T4 (comparison harness), P1-T5 (harness self-test)

| File | Version | Change |
|---|---|---|
| loopback_dut/host/lbcommon.py | v0.1 (new) | CRC-8 line sealing, rig.toml loader + target resolution, independent Python DUT model (register map, PEC, ACK/NAK) |
| loopback_dut/host/dut_link.py | v0.1 (new) | PC side of the DUT line protocol; CRC check on every line; seq-matched RUN replies raise `DesyncError` |
| loopback_dut/host/loopback_run.py | v0.1 (new) | Pattern driver: pushes rig config, per-case speed/PEC/stretch, emits cases (DUT `rep=` for bursts), writes expected.json; `--dry-run` from the model; hardware runs are cross-checked against the model (`model_mismatch`); desync aborts with exit 2 naming the case |
| loopback_dut/host/loopback_compare.py | v0.1 (new) | Harness: own CSV v1/v2 reader, edit-distance alignment (no equal-count assumption), per-case checks (data, S/Sr/P, address NAK, end-of-read NAK, PEC, decode, SCL), ledger verdicts pass/fail/xfail/xpass/not_exercisable, loopback_report.md |
| loopback_dut/host/lbsynth.py | v0.1 (new) | Perfect-capture synthesiser with optional B8/B9/B10/B13 symptoms (self-test only) |
| loopback_dut/schema/expected.schema.json | v0.1 (new) | expected.json schema (B1: `required` in every `if`) |
| loopback_dut/schema/loopback_pattern.schema.json | v0.2 | `xfail_symptoms` (machine-readable failure kinds) required with every xfail |
| loopback_dut/patterns/loopback_v1.json | (desc v0.3) | `xfail_symptoms` on LB-04/06/07/09; **LB-10 and LB-11 are now AD2-only xfail B10** |
| loopback_dut/tests/test_pattern_schema.py | v0.2 | Symptom rules (+3 reject, 1 accept) and ledger symptom check (63 checks) |
| loopback_dut/tests/test_host_model.py | v0.1 (new) | T1: model == C firmware vectors, PROTOCOL.md CRC vectors, DutLink vs fake DUT (desync, bad CRC), dry-run schema-valid, fake-hardware == dry-run for all 15 cases |
| loopback_dut/tests/test_loopback_harness.py | v0.1 (new) | T1 (P1-T5): perfect capture → 0 failures; 6 mutations caught in the right case; ledger xfail/xpass/unlisted-kind semantics; requirement gating; report format |
| loopback_dut/tests/test_loopback_capture.py | v0.1 (new) | T2: compares rig captures in loopback_dut/runs/, writes reports; exit 77 = loud SKIP (never a pass) |
| loopback_dut/runs/README.md | v0.1 (new) | What goes in runs/ |
| loopback_dut/docs/setup_guide.md | v0.7 | §10 full run with both sniffers, compare, how to read verdicts |

Why: PHASE_01 tasks P1-T3, T4 and T5.

Ledger correction found by the self-test: B10 ("spy_poll discards continuation segments")
truncates **any** AD2 read that spans a segment boundary, so LB-10 (64 B) and LB-11 (80 B)
would fail on the AD2 path too. PHASE_01 listed LB-10 as expect_pass. Both are now
`path_status {ad2: xfail, ion: expect_pass}`. If the AD2 captures them whole, the harness reports
`xpass`, which locates B10's real segment boundary.

Deviations: the driver lives at `loopback_dut/host/loopback_run.py`, not `tools/loopback_run.py`,
and the harness at `loopback_dut/host/loopback_compare.py`, not `core/loopback_compare.py`
(isolation). The desync guard is on the DUT's own link, not on `IonMasterLink`, so there is no B12
evidence from this driver.

Evidence:
- Dry run: 15 cases, 437 phases, `expected.json` schema-valid (0 errors). LB-07 PEC 0x6E
  independently verified over D6 08 D7 08 A0.
- test_host_model 22/22.
- test_loopback_harness all pass:
  - perfect capture 15/15 pass on both paths;
  - dropped / truncated / PEC-flipped / reordered / spurious / 1-of-400-burst mutations each
    detected in their case only;
  - with the known symptoms, ion gives xfail 3 and ad2 gives xfail 6, ledger exact;
  - the same truncation on ion is fail.
- test_pattern_schema 63 checks.
- DUT host tests 18 + 301 + 40.
- Project 18/18, smoke 8/9.
- Isolation: no `core`/`ui` imports in `loopback_dut/`.
- **Not yet run on hardware** (setup_guide §9-10).

---

# 2026-10-02 — First DUT bench contact: handshake retry, NA/ND fix

| File | Version | Change |
|---|---|---|
| loopback_dut/host/dut_link.py | v0.2 | `handshake()` flushes and retries PING up to 3×. A bad CRC is counted and retried; a persistently corrupted link raises; RUN replies are never retried |
| loopback_dut/tests/test_host_model.py | v0.2 | Tests for the retry contract (1 corrupted HELLO recovers; persistent corruption raises after 3; bad CRC during RUN raises) |
| loopback_dut/firmware/App/Src/dut_app.c | v0.2 | Address-vs-data NAK: the H5 HAL Seq transmit preloads TXDR before START (`stm32h5xx_hal_i2c.c` "Preload TX register"), so ≤ 1 byte consumed now reports `NA`. Before this fix every address NAK read `ND` |

Evidence (bench, measured on this rig):
- H533 at `/dev/cu.usbmodem11403` (STLINK-V3, VID:PID 0483:374E), C031 at
  `/dev/cu.usbmodem11203` (STLink 0483:374B), AD2 at `/dev/cu.usbserial-210321AC1ED9`
  (0403:6014).
- The first PING after flashing timed out; the next ones answered
  `HELLO LBDUT proto=1 fw=0.1 kernel=64000000 *BF` (matches PROTOCOL.md), and `STATUS` showed
  `uart_ovr=1`.
- First bus traffic: RUN 1–5 (LB-01/03/05/09 commands) were all NAKed, including 0x6B, with
  `STATUS r1w=0 r1r=0`. Responder R1 never saw its address, while the lines were pulled up
  (NAK, not bus error/timeout). Suspected wiring between I2C1 (PB6/PB7) and I2C2/I2C3; owner to
  check. Rebuilt firmware (0 warnings) not yet reflashed.

## 2026-10-02 (cont.) — P1-T2 bench check passes after the wiring fixes

Owner fixes: the H533 GND was not connected, and I2C2 SDA (PB12, CN10-16) was jumpered to
CN10-10 rather than the bus SDA. With both corrected, the setup_guide §9.4 commands gave
(DUT fw 0.1, before the NA fix was reflashed; measured on this rig):

```
PH 1 0 0 S 6B W A - 1 02 *12
PH 1 0 1 SR 6B R A P 2 02 A0 *CB                       LB-01  (matches guide)
PH 2 0 0 S 6B W A P 3 10 34 12 *48                     LB-03  (matches)
PH 3 0 0 S 08 W ND P 1 00 *9E                          LB-05  NAK ok; label ND = the v0.1 bug, v0.2 reports NA
PH 4 0 0 S 6B W A P 3 3E 01 00 *84                     LB-09 subcommand write (matches)
PH 5 0 1 SR 6B R A P 36 01 00 41 40 … 5F 5E 0E 24 *DB  LB-09 36-byte block (matches, checksum 0E, length 36)
PH 6 0 1 SR 55 R A P 2 02 B0 *00                       R2 (I2C3) answers with base 0xB000
STATUS … r1w=4 r1r=2 r2w=1 r2r=1 rerr=0,0 merr=0 uart_ovr=0
```

Every reply line, including its CRC, matches the expected line pre-computed in setup_guide §9.4.
Durations: 1-byte write + 2-byte read 5.95 ms end to end; 36-byte block 18.1 ms (UART report
included).

---

# 2026-10-02 — First full loopback runs (both sniffers); DUT fw 0.2 identity

| File | Version | Change |
|---|---|---|
| loopback_dut/firmware/App/Inc/loopback_config.h | v0.2 | `LB_FW_MINOR` 1 → 2: the NA/ND fix shipped as fw 0.2 (it had been flashed still reporting 0.1) |
| loopback_dut/docs/setup_guide.md | v0.8 | §9.3 expected HELLO for fw 0.2 (`*AD`) |
| loopback_dut/docs/PROTOCOL.md | v0.2 | HELLO fw field generic; §6 kept as the fw 0.1 CRC vector |
| loopback_dut/runs/2026-10-02_run1/, _run2/ | — | Archived run artefacts + NOTES.md (evidence) |

Evidence (measured on this rig, DUT `/dev/cu.usbmodem11403`):

Both runs: the DUT emitted all 15 cases (434 phases) with every case `emit_status ok`, so the
DUT matched the host model phase for phase. Run 1's AD2 capture is invalid (owner: AD2 wires
not connected correctly).

ion path (C031 fw 1.3), run 1 / run 2:
- pass on both runs: LB-01/02/03/05/09/10/11;
- LB-15: fail (1 bit slip) / pass;
- xfail exactly as recorded on both runs: LB-04 (B8), LB-06 (B13);
- not exercisable on both runs: LB-07/08 (PEC column empty: Validate SMBus PEC not active in the
  export);
- LB-12: fail on both. 7 / ~10 of 400 phases bit-shifted left by one bit (`06`→`0C`,
  `06 A0`→`0C 41`), plus 1 phase lost in run 2;
- LB-13 (400 kHz): fail on both, 0/5 captured;
- LB-14: pass / fail. In run 2 its first phase was recorded as Sr, because the LB-13 garbage left
  the decoder mid-transaction (knock-on, not a stretch problem);
- measured SCL 98.8–99.6 kHz at 100 kHz set (TIMINGR model predicted 100 075 Hz).

ad2 path, run 2 (434 rows):
- write phases that end in a repeated START are exported as `0x00 W [00]` in 162 of 212;
  stop-terminated writes are always right;
- the 36-, 64- and 80-byte reads were captured complete: B10 was not reproduced at ≤ 80 bytes at
  100 kHz;
- PEC column empty;
- SCL column empty (as designed).

Proposed new review IDs (owner to confirm): **B30** ion bit-bang decoder slips one SCL edge
under back-to-back traffic at 100 kHz (~2 % of burst phases); **B31** ion bit-bang capture fails
at 400 kHz and leaves the decoder mid-transaction (knock-on into the next case); **B32** AD2
spy exports Sr-terminated write phases as `0x00 W [00]` (~76 %), probably in the same
`spy_poll` start/segment handling as B10.

---

# 2026-10-02 — Ledger update from the bench runs: B30, B31, B32 (owner-approved)

| File | Version | Change |
|---|---|---|
| loopback_dut/schema/loopback_pattern.schema.json | v0.3 | `path_xfail_symptoms` {ion, ad2}: on a path only those kinds are excused; IDs may run out of numeric order |
| loopback_dut/patterns/loopback_v1.json | (desc v0.4) | Ledger: B32 (AD2) on LB-01/06/07/09/10/11/12/13/14/15; B30 (ion) on LB-12; B31 (ion) on LB-13; per-path symptoms; **LB-13 runs last**; LB-15 stays expect_pass on ion (B30 is intermittent) |
| loopback_dut/host/loopback_compare.py | v0.2 | Uses per-path symptoms; `apply_ledger()` / `--pattern` re-judge an archived run against the current ledger |
| loopback_dut/host/loopback_run.py | v0.2 | **Bug fix:** `path_xfail_symptoms` was not copied into expected.json, so per-path narrowing would have been lost on fresh runs (caught by the self-test) |
| loopback_dut/host/lbsynth.py | v0.2 | Symptom injectors B30 (bit shift), B31 (400 kHz garbage), B32 (Sr write → 0x00 W [00]) |
| loopback_dut/tests/test_loopback_capture.py | v0.2 | Optional run-directory argument; judges with the current ledger |
| loopback_dut/tests/test_pattern_schema.py | v0.3 | Run order (LB-13 last), effective per-path symptoms, path ⊆ union; mutation base = a ledger-free case |
| loopback_dut/tests/test_loopback_harness.py | v0.2 | ion with B8/B9/B13/B30/B31 and ad2 with B8/B9/B13/B32 (± B10) give an exact ledger; a B32 symptom on ion is not excused; LB-14 unaffected with LB-13 last |
| loopback_dut/tests/test_host_model.py | v0.3 | Guard: every `LEDGER_KEYS` field reaches expected.json |

New review items (owner-confirmed 2026-10-02):
- **B30**: the ion bit-bang decoder misses one SCL edge under back-to-back 100 kHz traffic
  (~2 % of LB-12 phases).
- **B31**: ion bit-bang capture fails at 400 kHz and leaves the decoder mid-transaction.
- **B32**: the AD2 spy exports Sr-terminated writes as `0x00 W [00]` (162/212).

Evidence: the archived runs re-judged with the new ledger:
- run 2 ad2: **ledger exact** (pass 3, xfail 10);
- run 2 ion: one fail, LB-14, the B31 knock-on from the old run order. The reorder prevents it
  from now on;
- run 1 ion: one fail, LB-15, an intermittent B30 slip, left expect_pass on purpose;
- run 1 ad2: invalid (wiring).

All loopback T1 suites pass; project 18/18; smoke 8/9; DUT host tests pass.

---

# 2026-10-02 — Run 3 (B9 proven) + ion firmware 1.4 (B30/B31 diagnostics and mitigations) + tools/ion_capture.py

| File | Version | Change |
|---|---|---|
| embedded/sniffer_nucleoC0_fw/Core/Inc/sniffer_config.h | v0.2 | FW 1.3 → **1.4**; `SNIFF_DIAG` (default 1), `SNIFF_DEFER_UPKEEP` (default 1), `UPKEEP_MAX_DEFER_US` 20 ms |
| embedded/sniffer_nucleoC0_fw/Core/Inc/frame_protocol.h | v0.2 | `status_info_t` diag fields; `STATUS_DIAG_PAYLOAD_LEN` 45; `frame_crc8_table` |
| embedded/sniffer_nucleoC0_fw/Core/Src/frame_protocol.c | v0.2 | Table-driven CRC-8 (identical results, ~8× faster); STATUS appends the 24-byte diag block when `diag_valid` |
| embedded/sniffer_nucleoC0_fw/Core/Src/main.c | v0.1 (tag added) | TIM14 (48 MHz) hot-path instrumentation: sample gaps, SCL high/low widths, per-FRAMING-phase worst gap and narrowest high; upkeep/STATUS deferred while a transaction is open |
| embedded/sniffer_nucleoC0_fw/build/* | — | Rebuilt fw 1.4 default (diag + defer) |
| embedded/sniffer_nucleoC0_fw/build_variants/fw14_diag_nodefer/ | (new) | A/B image: diag on, defer off |
| embedded/tests/host/test_frame_protocol.c | v0.2 | CRC table == bit-wise for all 256 inputs + long/continued messages; STATUS diag layout |
| core/ion_protocol.py | v0.2 | `decode_status()["diag"]` (ticks → µs, 0xFFFF → None) |
| tests/test_ion_protocol.py | v0.2 | diag decode cases |
| tools/ion_capture.py | v0.1 (new) | Headless capture: `--seconds`/`--count`, filters `--addr --exclude-addr --dir --nak --min-len --max-len`, `--pec`, `--decoder` (repeatable), `--status-only`; CSV v2 via TransactionLogModel; prints STATUS + diag |
| tests/test_ion_capture.py | v0.1 (new) | Fake probe: count + filters, PEC, FRAMING count, diag print, CSV v2 strict, Decode filled |
| embedded/docs/PROTOCOL.md | — | §1.2.1 STATUS diag block and how to read it |
| embedded/docs/B30_B31_investigation.md | v0.1 (new) | Evidence, hypotheses H1/H2, validation procedure, decision table, B31 options |
| loopback_dut/runs/2026-10-02_run3/ | — | Archived run 3 + NOTES.md |
| version.py | v1.2 | PROJECT_VERSION 1.4.0 → **1.5.0** |

Why:
- **Run 3** (PEC validation on in both apps) proves **B9** on both sniffers. On LB-07 the bus PEC
  0x6E is correct (independently computed over D6 08 D7 08 A0), yet both show ✗ PEC. LB-08's
  write PEC shows ✓ on both.
- **Ledger:** B30 (ion) and B32 (AD2) are intermittent per phase. B32 hit 162/212 and 159/212
  Sr-terminated writes in runs 2/3. B30 hit LB-15 in run 1 and LB-01 in run 3. That produces
  one random fail or xpass per run, so the intermittent-symptom ledger proposal is pending owner
  approval.
- **Owner decision (2026-10-02):** fix the ion embedded software now rather than in Phase 5, so
  the core firmware works. This is an exception to D-06.
- **Analysis of all slips in runs 1–3:** every B30 slip is the same lost SCL rise at the
  address-ACK / first-data-bit boundary (address intact, data shifted left one bit). That is
  where the DUT slave stretches, so either a sampler stall (H1) or a too-narrow SCL pulse (H2)
  at the stretch release.
- **fw 1.4** measures exactly that and adds two low-risk mitigations behind switches, so the
  next session can A/B them (procedure in `embedded/docs/B30_B31_investigation.md` §3).

Evidence (host only; **not validated on hardware**):
- all 4 variants build, 0 warnings: BITBANG text 5772 / bss 8636; SLAVE_MON 4608; MASTER 5212;
  BITBANG with diag + defer off 5080;
- disassembly: `i2c_dec_sample` makes no calls; division only in `i2c_dec_bus_hz` /
  `frame_encode_txn`;
- firmware host tests 86 + 92;
- project 19/19, smoke 8/9;
- loopback suites pass.

## 2026-10-05 — fw 1.5: host commands received by DMA (fw 1.4 lost them while capturing)
| File | Version | Change |
|---|---|---|
| embedded/sniffer_nucleoC0_fw/Core/Src/uart_stream.c | v0.1 (tag added) | USART2 RX now goes through DMA1 CH2, circular, into a 256-byte buffer; `uart_stream_read_byte()` follows the DMA write position. No interrupts, no hot-path cost |
| embedded/sniffer_nucleoC0_fw/Core/Inc/uart_stream.h | v0.1 (tag added) | API comments: RX is DMA-driven |
| embedded/sniffer_nucleoC0_fw/Core/Inc/sniffer_config.h | v0.3 | `UART_RX_DMA_SIZE` 256; `#error` if the buffer holds less than `UPKEEP_MAX_DEFER_US`; `FW_VERSION_MINOR` 4 → **5** |
| embedded/sniffer_nucleoC0_fw/build/* | — | Rebuilt fw 1.5 default (diag + defer) |
| embedded/sniffer_nucleoC0_fw/build_variants/fw15_diag_nodefer/ | (renamed from fw14_diag_nodefer) | A/B image rebuilt from fw 1.5: diag on, defer off |
| embedded/docs/B30_B31_investigation.md | v0.2 | §1.1 fw 1.4 hardware result + loop-rate implication; fw 1.5 images, new ports, reset step in §3 |
| embedded/docs/PROTOCOL.md | — | Commands may be sent back to back at any time from fw 1.5; the fw 1.4 caveat |

Why: fw 1.4 on the rig (owner-flashed 2026-10-05) answered HELLO and START from a fresh reset,
but then lost every command. ERROR 2 / 0xFF (bad CRC) or no reply, so a capture could not be
stopped. A bench test isolated the cause:

| Probe state | Command bytes | Result |
|---|---|---|
| capturing | back to back | lost |
| capturing | 2 ms or 5 ms apart | correct replies |
| stopped | back to back | correct replies |

STATUS showed `upkeep_deferred 0`, so the upkeep deferral was not involved (that first diagnosis,
in CLAUDE.md v1.11, was wrong). The 1-byte RDR was polled every 64 loop iterations. With the
diag code, 64 capturing iterations take longer than one byte time (87 µs), so bytes overran.

This also gives a measured lower bound for B30/B31: more than ~1.36 µs per capturing loop
iteration, which is longer than a 400 kHz SCL high. The planned "defer only after a recent edge"
change was dropped, because with RX by DMA a deferral can only delay a command (by ≤ 20 ms),
never lose it.

Evidence (host + build; fw 1.5 **not yet on hardware**):
- all 4 images build, 0 warnings: BITBANG text 5952 / bss 8892; BITBANG defer-off 5864;
  SLAVE_MON 4788; MASTER 5392;
- disassembly: division only in `frame_encode_txn` and `i2c_dec_bus_hz`;
- firmware host tests 86 + 92 pass.

## 2026-10-05 (cont.) — fw 1.5 on hardware: diag/deferral off by default, flash prefetch + cache on, trace pins
| File | Version | Change |
|---|---|---|
| embedded/sniffer_nucleoC0_fw/Core/Src/main.c | v0.2 | Flash prefetch + instruction cache enabled (`SNIFF_FLASH_ACCEL`); STATUS period from `STATUS_PERIOD_US`; optional trace pins PA0 (loop toggle) / PA1 (upkeep/flush busy) under `SNIFF_TRACE` |
| embedded/sniffer_nucleoC0_fw/Core/Inc/sniffer_config.h | v0.3 | Defaults now `SNIFF_DIAG 0`, `SNIFF_DEFER_UPKEEP 0`; new `SNIFF_FLASH_ACCEL 1`, `STATUS_PERIOD_US`, `SNIFF_TRACE 0` |
| embedded/sniffer_nucleoC0_fw/build/* | — | fw 1.5 default rebuilt (text 5280 / bss 8852); **flashed on the rig C031** |
| embedded/sniffer_nucleoC0_fw/build_variants/fw15_trace/ | (new) | `SNIFF_TRACE=2` image for the AD2 timing trace |
| embedded/sniffer_nucleoC0_fw/build_variants/fw15_diag_nodefer/ | (removed) | Diag images measure a broken loop (see Why) |
| embedded/docs/B30_B31_investigation.md | v0.2 | §1.2 hardware results; §1.3 trace procedure; §3/§4 marked superseded |
| embedded/docs/PROTOCOL.md | — | §1.2.1: diag block off by default from fw 1.5 |
| loopback_dut/runs/2026-10-05_{A1,B1,C1,C2,D1,D2,E1,E2,F1,F2}/, 2026-10-05_NOTES.md | — | Archived runs + summary |

Why: on the rig (I flashed each image by copying it to NOD_C031C6), the fw 1.4 additions turned
out harmful. SNIFF_DIAG on (A1, B1) or SNIFF_DEFER_UPKEEP on (D1, D2) each collapsed 100 kHz
decoding: every row read address 0x00 with no data, and ion passed 0 cases. With both off it was
back to fw 1.3 level, and fw 1.0 decoded the same wiring correctly. The polled loop had almost no
margin.

Flash prefetch + instruction cache had never been enabled. Turning them on cut LB-12 slips from
25/25 to 1/6 lines (fw 1.3: 9/14/21). The F runs (fw 1.5 default) give ion pass 10 / xfail 5,
ledger EXACT.

A STATUS-rate A/B (10 Hz vs off) showed no change, so STATUS is not the stall. AD2
logic-analyser timing during LB-12 shows a clean bus:
- SCL high ≥ 4.92 µs, low ≥ 5.12 µs;
- no stretch in the address byte;
- SDA setup ≥ 2 µs.

So B30 is a C031 sampler stall that misses the address-ACK clock (H1), and H2 is refuted at
100 kHz. B31 is unchanged (LB-13 0/5).

Evidence:
- all modes build, 0 warnings: default 5280; trace 5308; SLAVE_MON 4808; MASTER 5412;
  diag+defer 5972;
- division only in `frame_encode_txn` and `i2c_dec_bus_hz`;
- host tests 86 + 92 pass;
- runs and AD2 numbers in `loopback_dut/runs/2026-10-05_NOTES.md`.

## 2026-10-05 (cont. 2) — B30 root cause measured with trace pins
| File | Version | Change |
|---|---|---|
| embedded/docs/B30_B31_investigation.md | v0.2 | §1.4 trace result and the architecture options for the owner |
| loopback_dut/runs/2026-10-05_NOTES.md | v0.1 | Trace-pin measurement section |

Why: with C031 A0/A1 jumpered to AD2 DIO2/DIO3 (owner) and `fw15_trace`:
- the idle capture loop takes 1.3 µs per pass;
- every pass that decodes an edge takes 3.1–5.8 µs (up to 8.2 µs), against a 4.9 µs SCL high;
- whole clock highs were seen with no sample at all;
- upkeep / flush (BUSY) is not involved.

So B30 and B31 share one cause: decoding runs in the sampling loop. A timestamp-on-edge tweak
was tried, did not help (FRAMING 37 → 61) and was reverted; no source change is kept from this
step. The rig C031 is back on the fw 1.5 default (`build/`, text 5280).

## 2026-10-05 (cont. 3) — fw 1.6: bit-bang sampling by edge interrupt (B30 fixed)
| File | Version | Change |
|---|---|---|
| embedded/sniffer_nucleoC0_fw/Core/Inc/edge_ring.h | v0.1 (new) | SPSC edge ring (16-bit µs + lines), 16→32-bit time extension with idle re-anchor; pure C |
| embedded/sniffer_nucleoC0_fw/Core/Src/main.c | v0.3 | EXTI4_15 ISR on PA9/PA10 both edges → edge ring; main loop decodes one edge per pass; EXTI on at START, off at STOP; ring overflow counted in `errors`; trace level 2 shows the ISR on PA0; `#error` if DIAG/DEFER are combined with edge mode |
| embedded/sniffer_nucleoC0_fw/Core/Inc/sniffer_config.h | v0.4 | `SNIFF_EDGE_IRQ 1`, `EDGE_RING_SIZE 1024`; TX ring 4096 in edge mode; `FW_VERSION_MINOR` 5 → **6** |
| embedded/tests/host/test_edge_ring.c | v0.1 (new) | 22 checks: FIFO/wrap/overflow, time extension across TIM3 wraps, idle re-anchor + read-clock-first rule, waveform → ring → decoder identical to direct feed |
| embedded/tests/host/Makefile | v0.1 (tag added) | Builds and runs test_edge_ring |
| embedded/sniffer_nucleoC0_fw/build/* | — | fw 1.6 default (text 5796 / bss 9892); **flashed on the rig C031** |
| embedded/sniffer_nucleoC0_fw/build_variants/fw16_trace/, fw16_polled/ | (new) | Trace image; fw 1.5-equivalent polled image. `fw15_trace/` removed |
| embedded/docs/B30_B31_investigation.md | v0.2 | §1.5 fw 1.6 results and the 400 kHz limit |
| embedded/docs/PROTOCOL.md | — | STATUS `errors` also counts edge-ring overflows |
| documents/User_Guide_sniffer_ion.md | — | Troubleshooting row: 400 kHz not captured (B31), use the AD2 |
| loopback_dut/runs/2026-10-05_{G1,G2,H1,H2}/, 2026-10-05_NOTES.md | — | Evidence |

Why: the owner chose option 1 (edge interrupt). The trace had shown that a polled decode pass
(3–6 µs) could swallow a whole 4.9 µs SCL high.

Result on the rig, four full runs:
- 0 FRAMING;
- LB-12 400/400 exact every time (fw 1.3: 9–21 slip lines per run), so **B30 is fixed**;
- all other 100 kHz cases unchanged (pass 10).

At 400 kHz the ISR (0.58 / 1.37 µs, entry latency up to 0.9 µs) cannot keep up with edges every
~0.8 µs and misses every START. A RAM-resident ISR was only 10 % faster and was dropped. So B31
remains open: it needs DMA oversampling or the AD2.

Evidence:
- 5 images build, 0 warnings: default 5796 / bss 9892 (≈ 850 B RAM spare); trace 5828;
  polled 5280; SLAVE_MON 4808; MASTER 5412;
- `#error` fires for edge mode + DIAG;
- division only in `frame_encode_txn` / `i2c_dec_bus_hz`;
- host tests 86 + 92 + 22 pass.

## 2026-10-05 (cont. 4) — Ledger: B30 closed (owner-approved)
| File | Version | Change |
|---|---|---|
| loopback_dut/patterns/loopback_v1.json | description v0.5 | LB-12: `review_ids` [B32]; ion `path_status` expect_pass; ion symptoms removed; reason notes B30 fixed in fw 1.6. LB-15 note: a slip is now a regression |
| loopback_dut/tests/test_pattern_schema.py | v0.4 | B30 armed by no case; LB-12 effective symptoms (ion none, ad2 B32) |
| loopback_dut/tests/test_loopback_harness.py | v0.3 | ion bug set without B30; LB-12 must pass; injecting B30 on LB-12 must fail (regression guard) |

Why: owner approved closing B30 after four fw 1.6 runs with LB-12 400/400 exact. Re-judged
with the new ledger, runs G1, G2, H1 and H2 are each ion pass 11 / xfail 4 / ledger EXACT.
Results:
- DUT T1 suites pass;
- project 19/19, smoke 8/9 (the known baseline);
- firmware host tests 86 + 92 + 22 pass.

B31 stays open: the owner plans to move the probe to a faster MCU (NUCLEO-H723ZG or
H743ZI2).

## 2026-10-05 (cont. 5) — sniffer_ion / sniffer_ad2 tabs harmonized (owner request)
| File | Version | Change |
|---|---|---|
| ui/widgets/connection_section.py | v0.1 (new) | Shared "Device" group for both apps: selector + Refresh, full-width Connect / Disconnect, ● status in theme colors; selector and Refresh locked while connected |
| ui/device_panel.py | v0.1 (tag added) | AD2 Device group replaced by ConnectionSection; public API unchanged |
| ui/widgets/serial_device_panel.py | v0.2 | ion Device tab in the AD2 layout: ConnectionSection, **Probe** group (firmware / mode / protocol from HELLO, wiring), **Serial** baud (moved from Preferences, locked while connected), fixed-height **Device Info / Log** |
| ui/widgets/serial_prefs_section.py | v0.1 (tag added) | Docstring: lives on the Device tab now |
| ui/sniffer_ion_window.py | v0.1 (tag added) | Baud from the Device tab; Probe group filled on HELLO; Preferences = themes only; status bar ordered like the AD2 (firmware, port, bus, spy) |
| ui/sniffer_panel.py | v0.1 (tag added) | SCL readout shown by default; `bus_clock_available=False` shows "SCL: n/a" with an explaining tooltip; ion tooltip describes the fw ≥ 1.3 measurement |
| ui/sniffer_window.py, ui/main_window.py | v0.1 (tag added) | AD2 sniffer panels show "SCL: n/a" |
| tests/test_ion_protocol.py | v0.3 | Baud on the Device tab, not in Preferences; shared ConnectionSection present; Probe group shows the HELLO firmware |
| documents/User_Guide_sniffer_ion.md, documents/User_Guide_sniffer_ad2.md | — | Device-tab layout, baud location, SCL n/a |

Why: owner request to make the two sniffer apps look alike. Both now have:
- the same tab set;
- an identical Device group, then device-specific groups, then the same Device Info / Log;
- an identical Sniffer sidebar, including the SCL readout;
- Preferences with themes only;
- matching status-bar order.

Before/after renders were checked offscreen. Result: project 19/19, smoke 8/9 (baseline), DUT T1
suites pass.

## 2026-10-05 (cont. 6) — Compact, uniform icon buttons in both sniffers (owner request)
| File | Version | Change |
|---|---|---|
| ui/widgets/buttons.py | v0.1 (new) | `icon_button` (Qt standard icons by role), `uniform_width`, `button_row` (left-aligned, equal widths) |
| ui/widgets/connection_section.py | v0.2 | Selector on its own row; `[Refresh] [Connect] [Disconnect]` compact, equal width, with icons (the prior ion layout) |
| ui/device_panel.py | v0.2 | AD2: rate presets in one compact row; Actions (Apply Config, Clear Bus, Scan Addresses, Self-Test) in one compact icon row; DIO selectors 120 px, rate box ≤ 220 px |
| ui/widgets/theme_picker.py | v0.1 (tag added) | Browse / Refresh List / Open Theme Editor / Apply Theme: compact icon buttons |
| ui/widgets/sidebar_sections.py | v0.1 (tag added) | Clear Log / Export CSV, Add / Remove, Launch: icons, equal widths |
| ui/tabs/exit_tab.py | v0.1 (tag added) | Close Application: icon, compact |
| tests/test_ion_protocol.py | v0.4 | Guard: Refresh/Connect/Disconnect equal width, < 300 px, icons present |

Why: the owner did not want buttons spanning the window. Every button in both sniffers is now
compact, equal-width within its group, left-aligned and with an icon. The icons come from the Qt
style's standard set, so no image files are needed. The shared widgets give i2c_replay and the
editors the same style.

Result: project 19/19, smoke 8/9 (baseline). Checked with offscreen renders of all tabs of both
apps.

## 2026-10-05 — Phase 1 close (P1-T6 bench docs, P1-T7 handoff + review), PROJECT_VERSION 1.6.0
| File | Version | Change |
|---|---|---|
| embedded/docs/build_and_flash.md | v0.1 (new) | Both firmware images: toolchain (measured versions), build/variant/test commands with expected output, drag-and-drop and CLI flashing by ST-LINK serial, power-up ritual, troubleshooting |
| documents/loopback_dut_bringup.md | v0.1 (new) | Rig from parts to report: wiring, pull-ups, which image per board, first contact, headless + GUI runs, reading the report, current ledger, troubleshooting |
| loopback_dut/docs/setup_guide.md | v0.9 | §6.3 CubeProgrammer CLI path fixed (`Contents/Resources/bin`, not `Contents/MacOs/bin`) |
| documents/phases/HANDOFF_PHASE_01.md | v0.1 (new) | Cold-start handoff for Phase 2 |
| documents/phases/REVIEW_PHASE_01.md | v0.1 (new) | Senior-designer review: task outcomes, §5.2 criteria, both loopback reports, remediation §7 (B31, B32 intermittency, B12 evidence, B10, smoke, tag rule), new findings |
| loopback_dut/runs/2026-10-05_H1/loopback_report_ion_ledger_v05.md, 2026-10-02_run3/loopback_report_ad2_ledger_v05.md | — | Evidence reports re-judged with ledger v0.5 |
| version.py | v1.3 | PROJECT_VERSION 1.5.0 → **1.6.0** (fw 1.5/1.6, B30 fixed, GUI harmonization, Phase 1 closed) |

Why: PHASE_01 P1-T6 and P1-T7 (master plan §3.3).

Evidence:
- **Clean-tree builds** of both images (copies without `build/`): 0 warnings, byte-identical
  to the tracked images (`cmp`).
  - C031 `5796 4 9892`;
  - DUT `39324 112 5064`;
  - `STM32_Programmer_CLI` 2.23.0 lists both boards by serial number.
- **Decoders:** 10/10 validate against the schema.
- **Tests:** project 19/19, smoke 8/9 (baseline), DUT T1 + host 40, firmware host 86 + 92 + 22.
- **Loopback reports** (cited in REVIEW §6):
  - ion fw 1.6 (H1): `pass 11 · xfail 4 · Ledger exact: YES`;
  - AD2 run 3: `pass 4 · xfail 10 · xpass 1` (B32 intermittency, REVIEW §7.2).
- **Deliverable:** `~/Downloads/ion_i2c_tool_phase01_v1.6.0.zip` (tree without `.venv`,
  `__pycache__`, `.DS_Store`).

## 2026-10-05 (post-Phase 1) — Confirm dialogs use OK / Cancel in every app (owner request)
| File | Version | Change |
|---|---|---|
| ui/dialogs/message.py | v0.1 (tag added) | `confirm()` shows **OK / Cancel** (OK default) instead of Yes / No; returns True only on OK |
| tests/test_common_refactor.py | v0.1 (tag added) | Guard: confirm offers OK|Cancel, OK default, Cancel → False |

Why: owner request; the change is made in the one shared helper. Every app's exit guard
(`ConfirmingCloseMixin` → `dialogs.confirm`) and the decode editor's "Clear All" prompt change
the same way. The decoder editor's unsaved-changes prompt keeps its Save / Discard / Cancel
choice.

Evidence:
- offscreen check: the exit prompts of sniffer_ion and sniffer_ad2 both show OK|Cancel with OK
  as default, and Cancel keeps the window open;
- project 19/19, smoke 8/9 (baseline).

## 2026-10-05 (Phase 1b, owner-directed) — Decoder dashboard: B33 fixed, loopback decoder layout v2, skill update drafts
| File | Version | Change |
|---|---|---|
| ui/widgets/registers_tabs_host.py | v1.2 | **B33:** one Registers tab per (decoder, address) with layout, not one for the lowest address; titles `<device> — <name> 0xNN` from `address_names`; each tab shows its own file's rules and groups (not the merged set) |
| core/decoder_manager.py | v0.1 (tag added) | `DecoderEntry.address_names` read from the file-level `address_names` map; `schema_for(path)` |
| ui/widgets/registers_view.py | v1.3 | A field name repeated across rules in one table is shown as `<rule> · <field>` |
| i2c_decoders/loopback_dut_decoder.json | layout v2 | `device` "Loopback DUT"; `address_names` R1/R2; word reads as fields word / base / pointer; panes R1 reads, R1 block 0x3E (4 buffer bytes), R1 writes (last value), R2 reads, R2 writes (last value); description explains that values are constant by design |
| i2c_decoders/smbus1v1_decoder.json | — | `address_names` Host 0x08 / Charger 0x09 / Battery 0x0B (5 added lines; generator not in the tree) |
| i2c_capture/loopback_dut_replay_check.csv | — | Decode column for the 7 word reads and the block, updated to layout v2 (hand-derived from PROTOCOL.md §4) |
| documents/decoders/loopback_dut_decoder.md | — | Regenerated with the skill's decoder_to_markdown.py; provenance: dashboard, constant values, editor-save metadata loss; changelog |
| tests/test_registers_tab.py | v0.1 (tag added) | `test_b33_multi_address_tabs`: per-address named tabs, layout only on a higher address, R1 rules on the R1 tab, real smbus1v1 and loopback files, no cross-decoder rows |
| tests/test_loopback_dut_decoder.py | v0.2 | Vectors for layout v2; B29 probe moved to an inline plain-hex rule; block fields pinned |
| tests/test_ion_capture.py | v0.2 | Decode pin for layout v2 |
| .gitignore | v0.1 (new, project level) | Un-ignores the replay fixture and `loopback_dut/runs/**/*.csv` (the repo-wide `*.csv` rule had kept all 20 rig captures and the fixture out of git) |
| plan_n_exe/skill_updates/datasheet-i2c-decoder/ | (new) | Skill drafts for claude.ai: `CHANGES.md` (exact find/replace for SKILL.md and schema-guide.md), `references/dashboard-design.md`, `scripts/check_dashboard.py` |

Why: the owner saw the loopback decoder's dashboard show only R2 with constant values, and
asked for a descriptive dashboard plus skill guidance. Owner decisions: one tab per address;
do it now, before Phase 2 (an exception to D-06); deliver the skill changes as drafts for
upload.

Root cause (B33, new): `_rebuild_register_tabs` used `min(entry.addresses)`.
- The loopback decoder lost R1 (0x6B).
- `smbus1v1_decoder.json` got no tab at all, because its 36 grouped rules are at 0x0B.

Also fixed: tabs used the merged schema, so two decoders on one address showed each other's
rules.

Constant values are by design: the DUT stores no writes and reads are base + pointer.

Evidence:
- **B33 before:** `test_b33_multi_address_tabs` fails. Tabs were
  `['Device','Sniffer','Multi','Preferences','Help','Exit']`, with no "HighOnly" tab, then an
  exception (kept in the scratch log).
- **B33 after:** passes. Tabs are `Multi — R2 0x55`, `Multi — R1 0x6B`, `HighOnly`, and
  `Smart Battery (SBDS v1.1) — Host 0x08 / Charger 0x09 / Battery 0x0B`.
- **Dashboard render:** the ion window replaying rig run 2026-10-05_H1 (429 transactions) shows
  `Loopback DUT — R1 0x6B` with rows such as `R1 word 0x02 · base = 0xA0`, the block pane and
  the last-written pane, and the R2 tab with base 0xB0.
- **Checks:** 10/10 decoders schema-valid; replay CSV valid (20 rows); project 19/19; smoke 8/9;
  DUT T1 pass; ion run H1 still `pass 11 · xfail 4 · ledger EXACT`.

Found, not fixed (Phase 4, review B2 area): `DecodeSchema.save()` keeps only `version`,
`rules` and `display_groups`. It drops `device`, `description`, `address_names`,
`i2c_address*`, `byte_order` and `byte_order_note`, so saving a decoder in the editor loses
its tab names and its Int-column byte order.

Skill finding: `references/schema-guide.md` §7 says a `bits` write rule stays out of the
bit matrix, but the tool includes every `bits` rule. This is corrected in the draft.

## 2026-10-05 — USB device discovery and naming across all USB apps (owner request)
| File | Version | Change |
|---|---|---|
| core/device_names.py | v0.1 (new) | USB scan (pyserial; ST-LINK VCPs and FTDI incl. the AD2), identity = normalized USB serial (`SN:` prefix dropped, so DWF and pyserial agree; no-serial fallback vid:pid:location), per-user store `~/.ion_i2c_tool/device_names.json` (env `ION_TOOL_DEVICE_NAMES`), unique case-insensitive names, last-used device per app, `DiscoveryTracker` (snapshot; unplug + replug detected), `resolve_port(name / serial / path)` |
| ui/dialogs/device_names_dialog.py | v0.1 (new) | "Name USB devices": 1) Start → snapshot → plug in → new serial found → name it; 2) table of all connected devices, edit Name to name / rename, clear to forget |
| ui/widgets/connection_section.py | v0.3 | **Name devices…** button in the shared Device group (every app); `names_changed` signal |
| ui/widgets/buttons.py | v0.2 | `devices` icon role |
| ui/widgets/serial_device_panel.py | v0.3 | Named ports listed `<name> — <port> …`; pre-select by USB serial key; `selected_key()`; `names_changed` |
| ui/device_panel.py | v0.3 | AD2 list shows names; pre-select by serial; `serial_for_index()`; `names_changed` |
| ui/sniffer_ion_window.py, ui/sniffer_window.py, ui/main_window.py | v0.2 | Refresh on `names_changed`; last-used device per app (`sniffer_ion`, `sniffer_ad2`, `ad2_tool`) saved on Connect and pre-selected on Refresh; status bar shows the name |
| core/ion_backend.py | v0.2 | `list_serial_ports()` adds `serial`, `key`, `name`; named ports sort first |
| tools/device_names.py | v0.1 (new) | CLI: `list`, `discover`, `name <port/serial/name> <name>`, `forget` |
| tools/ion_capture.py | v0.2 | `--port` accepts a device name or USB serial; auto-detect prints the name |
| tools/record_on_trigger.py | v0.1 (tag added) | `--port` accepts a device name or USB serial |
| loopback_dut/host/lbdevnames.py | v0.1 (new) | Isolated reader of the same per-user file (no core/ imports); `resolve_port` |
| loopback_dut/host/loopback_run.py | v0.3 | `--port` (and rig.toml `[ports] dut`) may be a device name |
| tests/test_device_names.py | v0.1 (new) | 29 checks: identity, store, discovery incl. replug, resolve, GUI button/labels/pre-select, dialog discover + save + duplicate refusal |
| loopback_dut/tests/test_lbdevnames.py | v0.1 (new) | Isolated reader resolves names like core (file written by hand in the documented format) |
| documents/User_Guide_sniffer_ion.md, User_Guide_sniffer_ad2.md, loopback_dut_bringup.md (v0.2) | — | How to name devices; `--port <name>` |

Why: the owner wants every USB-connected app to discover a device by snapshot-then-plug-in,
name it, and also name any already-connected unnamed device. Owner decisions:
- names are stored per user and shared by all apps;
- GUI, CLI and the loopback runner all use them;
- the last-used named device is pre-selected.

Evidence:
- **Rig check** (real devices, scratch name file):
  - `tools/device_names.py list` shows C031 / H533 / AD2 with their serials;
  - `name` by serial and by port works; a duplicate name (different case) is refused;
  - `ion_capture.py --port "C031 sniffer"` connects (fw 1.6);
  - `loopback_run.py --port "H533 DUT" --cases LB-01` runs.
- **Renders:** the dialog finds a "newly plugged" AD2 and offers it for naming; the ion Device
  tab lists `C031 sniffer — /dev/cu.usbmodem1203 …` first, with the Name devices… button.
- **Tests:** project 20/20 (19 + test_device_names), smoke 8/9 (baseline), loopback T1 + lbdevnames
  pass. The tests use an isolated name file, and the real `~/.ion_i2c_tool` was not created.
