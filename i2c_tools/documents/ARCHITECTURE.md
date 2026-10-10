# AD2 I2C Tool — Shared Architecture & Extensibility Guide

> **Status:** Target architecture. This document is the *contract* every app and
> every refactor prompt in this series conforms to. When code and this document
> disagree, fix whichever is wrong and note it here.
>
> **Adopted:** 2026-07-01 (prompt P02). Entry-point (§1) and layer-map (§2) tables
> were verified against the source tree on this date and found accurate.
> **Not yet conformant:** the `bq76905_gateway_tool.py` app does **not** yet
> satisfy the §5/§7 conformance checklist — it still ships its own theme, hex
> parser, decoder, and log widget. Prompts **P07 → P08 → P09** bring it into
> conformance; check its boxes only after P09.

---

## 1. What this project is

A family of **standalone PySide6 desktop apps** that share one GUI/toolkit layer.
Each app runs on its own (`python3 <entry>.py`), but any app may hand a file
(capture CSV, decoder JSON) to another. The apps must **not duplicate** UI,
theming, hex parsing, decode logic, or the transaction-log table — they compose
those from the shared layer.

Supported platforms: **macOS**, **Ubuntu 22.04+**, optionally **Windows 10+**.

### Entry points (apps)

| Entry point                 | Window class          | Purpose |
|-----------------------------|-----------------------|---------|
| `sniffer_ad2.py`            | `SnifferWindow`       | AD2 passive I2C/SMBus sniffer + logger (Device/Sniffer/Preferences tabs) |
| `decoder_editor.py`         | `DecoderEditorWindow` | Create/edit decoder JSON files |
| `i2c_replay.py`             | `ReplayWindow`        | Replay a capture CSV against a decoder (no hardware) |
| `bq76905_gateway_tool.py`   | `BQ76905GatewayTool`  | USB-to-I2C gateway (NUCLEO) for the BQ76905EVM |

Every entry point is a **thin `main()`**: it calls `build_application(...)`,
constructs its window, `show()`s it, and enters the event loop. No business
logic lives in the entry point.

---

## 2. Layer map (the shared toolkit)

```
core/                      # No Qt widgets. Pure logic + models.
  device_manager.py        #   DWF device enumerate/open/close, self-test
  dwf_loader.py            #   locate + load the WaveForms SDK
  i2c_controller.py        #   I2CController, I2CTransaction, I2CDirection, smbus_crc8
  log_model.py             #   TransactionLogModel (QAbstractTableModel) + COLUMNS/COL_IDX
  spy_worker.py            #   background sniffer thread
  decode_schema.py         #   DecodeSchema, DecodeRule, BitField, StreamDecoder  <-- SINGLE SOURCE

ui/
  common/
    app_bootstrap.py       #   build_application(): QApplication + HiDPI + metadata + initial theme
    hexutil.py             #   parse_hex_bytes / parse_addr_7bit / parse_register_byte / HexParseError
    capture.py             #   load CSV -> transactions / decode a capture with a schema
    app_info.py            #   project/app metadata + User Guide loader (Help tab)
  theme.py                 #   SINGLE SOURCE for all colors/QSS. apply_theme/get_color/active_palette
  dialogs/                 #   warn/error/info/confirm, open_json/save_json/open_csv, CaptureResultsDialog
  widgets/                 #   HexLineEdit, ThemePicker, DecodeEditor; framing kit:
                           #     AppWindow, Sidebar, Section, make_tab_body, FilePickerRow,
                           #     HelpPanel, ExitPanel
  <app panels>.py          #   DevicePanel, SnifferPanel, LogPanel (RWPanel/DecodePanel/PreferencesPanel present but unused)
  sniffer_window.py        #   SnifferWindow (composes the panels on the AppWindow shell)
  replay_window.py         #   ReplayWindow
  decoder_editor_window.py #   DecoderEditorWindow

schema/decoder.schema.json #   JSON Schema describing the decoder-file format
documents/                 #   user guides + this file
```

**Golden rule:** an app may *compose* and *read* from the shared layer, but the
shared layer must never import from an app. Dependencies point **downward**
(app → ui → core), never sideways or up.

> **Current-tree deviations (updated 2026-07-01 after P03/P04).**
> - `ui/theme.org.py` — **removed** in P03 (was byte-identical to `ui/theme.py`).
> - `schema/decode_schema.py` — **removed** in P04; its improved subcommand
>   read-back (data-returning subcommands read back from the subcommand register
>   0x3E, not a fixed 0x40 buffer) was merged into `core/decode_schema.py`, now
>   the sole decoder. (`schema/decoder.schema.json` stays — it is the JSON Schema
>   for decoder files.)
> - `ui/theme.new.py` — **still present, pending a decision.** It is a divergent
>   redesign holding unique content not in `ui/theme.py`: an `_IONTRA` brand-token
>   set and an `iontra_pricing_tool` theme (and it is missing `dark_claude`).
>   Nothing imports it. Resolve by either merging its unique tokens into
>   `ui/theme.py` or deleting it; do not leave a second theme module long-term.

---

## 3. The extension points (how to reuse, not replicate)

When building a **new application** or feature, reach for these in order. If a
need isn't met, extend the shared layer (and update this doc) rather than
copying code into the app.

1. **Startup** — always `from ui.common import build_application`. Never build a
   `QApplication` or set a stylesheet by hand. This guarantees identical HiDPI
   policy, metadata, and initial theme.

2. **Theming** — `from ui import theme`. Colors come from *named tokens* in
   `theme.py` (`get_color("status_error")`, `active_palette()[...]`). Never
   hardcode hex in an app or embed a private QSS block. To offer theme switching,
   drop in `ui.widgets.ThemePicker` (or `PreferencesPanel`) and connect its
   `theme_apply_requested(str)` signal to `theme.apply_theme`.
   *Adding a new theme = adding one palette dict + one `THEME_CHOICES` entry in
   `theme.py`; every app picks it up for free.*

3. **Hex I/O** — `from ui.common.hexutil import ...` or use `ui.widgets.HexLineEdit`.
   Never write another hex parser.

4. **Transaction log** — the table is `core.log_model.TransactionLogModel`
   wrapped by `ui.log_panel.LogPanel`. It handles columns, filtering, decode
   column, CSV/JSON export, and multi-line rows. New apps that show captured or
   replayed traffic embed `LogPanel`; they do not build their own `QTableWidget`.

5. **Decoding** — `core.decode_schema.DecodeSchema` (load/save/`from_json`) plus
   `StreamDecoder` for sequence-aware decode. `DecodeEditor` is the reusable
   editing widget. There is exactly **one** decode implementation. Do not add a
   second `Rule`/`DecoderEngine`.

6. **Dialogs** — `ui.dialogs` for message boxes and JSON/CSV file pickers so
   wording, buttons, and filters stay consistent.

7. **Hardware/transport** — `core.i2c_controller.I2CController` +
   `core.device_manager`. A different transport (e.g. a serial gateway) should
   present the **same** `I2CTransaction` objects to `TransactionLogModel`, so the
   log/decoder/export stack is reused unchanged.

8. **Application framing** `[XREF: app-shell]` — apps share one window frame and
   sidebar vocabulary from `ui.widgets`: `AppWindow` (top-tab shell + status bar),
   `Sidebar` + `Section` + `make_tab_body` for a tab laid out as
   `[sidebar of sections | main content]`, and `FilePickerRow` `[XREF: file-picker]`
   for a validated "select a file" control (label + Open + a status line that reads
   *none* / *name ✓ valid* (green) / *name ✗ error* (red), colored from theme
   tokens). `sniffer_ad2` and `i2c_replay` use this layout; new apps should too.
   Standardize the Preferences tab on `ui.widgets.ThemePicker`.

9. **Help & Exit tabs** — apps add a `HelpPanel(app_key)` [XREF: help-tab] tab that
   shows project/version/date from `ui.common.app_info` and renders the matching
   `documents/User_Guide*.md` (themed HTML: colored headings/code, bordered
   tables; call `refresh()` after a theme change), and an `ExitPanel(title)`
   [XREF: exit-tab] whose button calls `window.close()`. Unsaved-change
   confirmation lives in each window's `closeEvent`, so the Exit tab and the window
   close button share one path.

---

## 4. Recipe: add a new application

1. Create `my_tool.py` at the repo root:
   ```python
   from ui.common import build_application
   from ui.my_tool_window import MyToolWindow
   def main():
       app = build_application(app_name="My Tool", version="1.0.0",
                               org="Digilent AD2 Utils", initial_theme="dark")
       MyToolWindow().show()
       import sys; sys.exit(app.exec())
   if __name__ == "__main__":
       main()
   ```
2. Put the window in `ui/my_tool_window.py`. Compose it from existing panels
   (`LogPanel`, `ThemePicker`, `DecodeEditor`, …). Add a Preferences tab with a
   `ThemePicker` for theme parity.
3. Emit/consume `core.i2c_controller.I2CTransaction` so the shared log model,
   decoder, and export work with zero new code.
4. If you need a genuinely new capability, add it to `core/` or `ui/widgets/`
   (reusable), **not** inside the app, and document it in §3 above.
5. Add the app to the table in §1, to the smoke-test harness, and to `run.sh` /
   the Windows launcher.

**Definition of done for "extensible":** the new app contains only *composition
and wiring* — no copied theme, hex, decode, or table code.

---

## 5. Conformance checklist (per app)

- [ ] Starts via `build_application` (no manual `QApplication`/`setStyleSheet`).
- [ ] Uses `ui.theme` tokens only — zero hardcoded colors, no embedded QSS.
- [ ] Offers the same theme set through `ThemePicker`.
- [ ] Uses `ui.common.hexutil` / `HexLineEdit` for hex.
- [ ] Shows traffic through `LogPanel` / `TransactionLogModel`.
- [ ] Decodes through the single `core.decode_schema`.
- [ ] Uses `ui.dialogs` for message/file dialogs.
- [ ] No private-attribute access across module boundaries (`obj._x` from outside).
- [ ] Window uses minimum sizes + persisted geometry, not fixed pixel sizes.
