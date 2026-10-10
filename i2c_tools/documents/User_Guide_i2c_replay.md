# AD2 I2C Replay — User Guide

`i2c_replay.py` is a standalone application for validating decoder JSON files
against real captured I2C traffic, without hardware connected. It replays a
sniffer CSV capture (format: documents/CSV_FORMAT.md) through the stream decoder and displays the results in the
same transaction-log table used by the sniffer app.

---

## Launch

```bash
# From the project folder with the virtual environment active
python i2c_replay.py

# With files pre-loaded on startup
python i2c_replay.py path/to/capture.csv path/to/decoder.json
```

---

## Window Layout

The window has two tabs across the top — **Replay** and **Preferences**. The
Replay tab is laid out as a left **sidebar of sections** beside the
transaction-log table, matching the sniffer app.

```
[ Replay ] [ Preferences ]                     <- tabs at the top
┌──────────────────────────────┬────────────────────────────────────────────┐
│  Sidebar (Replay tab)         │   Transaction Log Table                    │
│  ┌─────────────────────────┐  │   (same columns as the sniffer:            │
│  │ Capture Stats           │  │    Time, #, Addr, Dir, Len, Data, …)       │
│  │ Load Capture File       │  │    Decode column populated when a          │
│  │ Load Decoder File       │  │    decoder is loaded                       │
│  │ Editor                  │  │                                            │
│  │ Table Data              │  │                                            │
│  └─────────────────────────┘  │                                            │
└──────────────────────────────┴────────────────────────────────────────────┘
```

Replay happens **automatically** when a valid capture (or decoder) is loaded —
there is no separate Replay button.

---

## Sidebar Sections

### Capture Stats

Live counts for the loaded capture: **Rows** (transactions loaded), **Visible
(filtered)**, **Total in log**, and **Decoded** (rows the decoder produced text
for).

### Load Capture File

Click **Open** and select a `.csv` capture previously exported from the sniffer
(or the AD2 WaveForms Logic Analyzer). The status line shows *none*, *name ✓ valid
capture (N rows)* (green), or *name ✗ error* (red). The expected columns are:

| Column | Content |
|---|---|
| `Time` | HH:MM:SS.mmm timestamp |
| `#` | Transaction sequence number |
| `Addr` | 7-bit address in hex (e.g. `0x08`) |
| `Dir` | `R` or `W` |
| `Len` | Byte count |
| `Data (hex)` | Space-separated hex bytes |
| `NAK` | `NAK` if not acknowledged |
| `Start` | `S` (Start) or `Sr` (Repeated Start) |
| `Stop` | `P` if a Stop ended the frame |
| `PEC` | SMBus CRC-8 result (if validated) |

Selecting a valid capture **replays it immediately**: the table is cleared and
repopulated with one row per transaction, decoded against the active decoder (if
one is loaded).

### Load Decoder File

Click **Open** and select a `.json` decoder (see the Decoder Editor guide to
create one). The status line shows *name ✓ valid decoder (N rules)* or an error.
Selecting a decoder loads it and **re-decodes the rows already in the table** — no
extra step needed. If a capture is loaded first, load the decoder afterward and the
Decode column fills in.

### Editor

**Launch** — opens the standalone Decoder Editor, pre-loaded with the decoder file
selected above (if any), or brings it to the front if already open. After editing
and saving, re-select the file in **Load Decoder File** to pick up the changes
(this re-decodes the table).

### Table Data

**Clear Log** — empties the table without unloading the capture or decoder.
**Export CSV** — saves the visible (filtered) rows, including the Decode column,
to a CSV file (same format the sniffer produces).
**Auto-scroll** — present for consistency with the sniffer; it has no effect here
because the table is populated in a single batch.

---

## Transaction Log Table

### Columns

| Column | Description |
|---|---|
| **Time** | Timestamp from the CSV |
| **#** | Sequence number |
| **Addr** | 7-bit device address |
| **Dir** | `R` (read) or `W` (write) |
| **Len** | Number of data bytes |
| **Data (hex)** | Raw bytes in hex |
| **Int** | Big-endian unsigned integer of the data bytes |
| **ASCII** | Printable ASCII (`.` for non-printable) |
| **Decode** | Human-readable value from the decoder (e.g. `Cell 1 Voltage = 2800 mV`) |
| **NAK** | `NAK` if not acknowledged |
| **Start** | `S` or `Sr` (repeated start) |
| **Stop** | `P` if a Stop was present |
| **PEC** | SMBus CRC-8 result |
| **SCL** | SCL frequency measured by the capture probe for that transaction, in kHz (CSV column `SCL (Hz)`, capture CSV v2). Blank for v1 files and for captures from probes that do not measure it (AD2). Hover a row for the exact Hz. |

### Multi-line Decode Column

The replay app enables multi-line rows, so bit-field decodes expand vertically,
one field per line:

```
Battery Status:
Bit.15 [SLEEP=1]
Bit.14 [DEEPSLEEP=0]
Bit.13 [SA=0]
...
```

Row heights are recomputed after each load. If rows look truncated after resizing
the window, re-select the capture in **Load Capture File**.

### Filters

**Search** — live match over hex data, address, or ASCII.
**Dir** — Read only / Write only / all.
**Addr filter** — Capture All (default) / Include Only / Exclude, with a
space-separated hex address list. **Apply** to commit, **Reset** to clear.

### Display options

Two view-only checkboxes on the right of the filter bar (the same ones the sniffer
has) change how the table is presented; they don't alter the loaded capture.

**8-bit address** — off by default. Shows the **7-bit** address (`0x08`) with a
separate `R`/`W` **Dir** by default; tick it to show the **8-bit** first byte with
R/W folded into bit 0 (`0x10` write, `0x11` read), the form TI's datasheet uses.
In that mode **Dir** reads `W (bit0)` / `R (bit0)`.

**Show CRC** — on by default. Shows the **PEC/CRC** column and colors its value
green (valid) / red (invalid); untick to hide the column. Replay reads the CRC
result from the capture CSV's PEC column, so coloring appears when the original
capture was taken with PEC validation on.

---

## Preferences Tab

Select a color theme and click **Apply Theme**; the change is immediate.

| Theme | Description |
|---|---|
| System | Follows the OS setting, defaults to Dark |
| Light | Light backgrounds, dark text |
| Dark | VS Code-style dark (default) |
| Engineering Dark | Catppuccin-inspired dark, blue accent |
| Iontra Dark | GitHub-style deep dark |
| Iontra Light | GitHub-style light |
| Dark Claude | Warm near-black, terracotta accent |

---

## How the Decoder Works

The replay engine uses a **stream decoder** that processes transactions in order,
mirroring the bus:

- **Indexed read** — a single-byte write (the register index) with no Stop, then a
  read: one logical operation; the register sets context and the read data is
  decoded against it.
- **Indexed write** — a write of two or more bytes: first byte is the register,
  the rest are the value.
- **Subcommand** — a write to the subcommand register (typically `0x3E`) carrying a
  16-bit little-endian code; if it matches a data-returning subcommand rule, the
  following read of that register is decoded as the response.
- **Simple read / write** — register-less transactions.

Rows carrying only the register pointer (the `W` phase of a paired read) show empty
Decode text; the text appears on the paired `R` row.

---

## Help & Exit Tabs

**Help** — shows the project name, version, and last-updated date, then renders
this User Guide with the active theme (colored headings and code, bordered
tables). It re-renders when you change the theme in Preferences.

**Exit** — click **Close Application** to quit. Replay data is loaded from files,
so there is nothing unsaved and no save prompt appears; any Decoder Editor window
opened from the Editor section is closed too.

---

## Troubleshooting

**Decode column is empty for all rows**
- Confirm a decoder loaded (Load Decoder File status is green).
- Verify the device address in the decoder matches the CSV (e.g. `0x08` vs `0x10` —
  some tools show the 8-bit shifted address).

**Some registers decode but others don't**
- The register may have no rule in the decoder JSON.
- Subcommand responses only decode if the issuing write appears earlier in the CSV.
- Use the Decoder Editor to inspect and correct a rule's address/value.

**Capture loads but the table stays empty**
- Check the CSV has the required headers (`Addr`, `Dir`, `Data (hex)`).
- Rows with non-parseable address values are silently skipped.

**Timestamps show today's date**
- The parser combines the `HH:MM:SS.mmm` time with today's date; cosmetic only.
