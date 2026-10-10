# AD2 Sniffer — User Guide

`sniffer_ad2.py` is the application for passively sniffing and logging I2C / SMBus
traffic with a Digilent Analog Discovery 2 (AD2). It requires the Digilent
WaveForms SDK (`libdwf`) to be installed. The application opens without hardware,
but bus operations are unavailable until a device is connected.

This app is a **sniffer/logger only** — it never drives the bus, and it has no
master read/write function.

---

## Launch

```bash
# Using the generated launcher (created by install.sh)
./run.sh sniffer_ad2.py

# Or manually with the virtual environment active
source .venv/bin/activate
python sniffer_ad2.py
```

---

## Window Layout

The window uses **tabs across the top** — Device, Sniffer, Preferences — matching
the Replay and Decoder Editor apps. The Sniffer tab is laid out as a left
**sidebar of sections** beside the transaction-log table.

```
┌───────────────────────────────────────────────────────────────────────────┐
│  [ Device ] [ Sniffer ] [ Preferences ]        <- tabs at the top           │
├──────────────────────────────┬────────────────────────────────────────────┤
│  Sidebar (Sniffer tab)        │   Transaction Log                          │
│  ┌─────────────────────────┐  │   [filter bar: Search | Dir | Addr]        │
│  │ I2C Sniffer (Passive)   │  │   [table: Time # Addr Dir Len Data         │
│  │ Capture Stats           │  │    Int ASCII Decode NAK Start Stop PEC]    │
│  │ Table Data              │  │                                            │
│  │ Load Decoder File       │  │                                            │
│  │ Editor                  │  │                                            │
│  └─────────────────────────┘  │                                            │
└──────────────────────────────┴────────────────────────────────────────────┘
│ DWF version  |  device status  |  rate  |  pins  |  spy status             │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Status Bar

| Item | Description |
|---|---|
| DWF version | Library version loaded at startup, or "DWF not found" |
| Device status | "No device" or "✓ Device name" after connecting |
| Rate | Active I2C clock rate (e.g. `100 kHz`) |
| Pins | Active SCL/SDA pin assignment (e.g. `SCL=DIO0 SDA=DIO1`) |
| Spy status | "● Sniffing" (green) when the sniffer is running |

---

## Device Tab

Handles hardware connection, pin assignment, and I2C bus configuration. Complete
it before sniffing.

### Device Selection

**Refresh** — enumerates connected WaveForms-compatible devices. The dropdown
lists each device with index, model name, and serial number. Devices in use by
another application are marked `(in use)`.

**Connect** — opens the selected device and prepares the I2C engine. The default
configuration (SCL=DIO0, SDA=DIO1, 100 kHz, clock stretch on) is applied
automatically on connect.

**Disconnect** — closes the device. An active sniffer session is stopped first.

**Name devices…** — gives a USB instrument a name that every app shows (shared by
sniffer_ion, sniffer_ad2, the AD2 tool and the command-line tools; stored per user
in `~/.ion_i2c_tool/device_names.json`):
1. Press **Name devices…**, then **Start**. The app takes a snapshot of the
   connected USB devices.
2. Plug the device in. If it is already plugged in, unplug it and plug it back.
   Within half a second it reports the new device: description, port, serial
   number, VID:PID.
3. Type a name (e.g. `C031 sniffer`, `H533 DUT`, `Bench AD2`) and press
   **Save name**.

The lower table lists every connected USB device. Edit a **Name** cell to name
one you can already identify, or clear the cell to forget the name. Names must
be unique (case-insensitive).

**What names change:**
- Named devices are listed first, as `<name> — <port> …`.
- The device you last connected is **pre-selected by its serial number**, so it
  is found even when its port name changes.
- Devices are identified by USB serial number. One without a serial number is
  tied to the USB socket and flagged in the dialog.
- Command line: `python tools/device_names.py list | discover | name | forget`.
  Every `--port` option accepts a name, e.g.
  `tools/ion_capture.py --port "C031 sniffer"` or
  `loopback_dut/host/loopback_run.py --port "H533 DUT"`.

### DIO Pin Assignment

**SCL pin** — DIO pin for the I2C clock line (default DIO 0).
**SDA pin** — DIO pin for the I2C data line (default DIO 1).
**ALERT pin** — optional SMBus ALERT line; enable the checkbox and select a DIO.

> **Clock-stretch pin conflict:** With clock stretch enabled, the AD2 uses DIO 0–9
> internally for state logic. Keep SCL on DIO 0 and SDA on DIO 1; place other DIOs
> at 10 or higher. To use DIO 2–9 for other purposes, disable clock stretch first.

### I2C Rate / Options

**Rate** — I2C clock frequency; enter Hz directly or click a preset.

| Preset | Rate |
|---|---|
| Auto | 0 Hz (engine selects) |
| 100 kHz | Standard mode |
| 125 kHz | — |
| 250 kHz | — |
| 400 kHz | Fast mode |
| 1 MHz | Fast-mode Plus |

**Clock stretch** — recommended on; the AD2 waits for the slave to release SCL.

### Actions

**Apply Config** — pushes pins, rate, and clock-stretch to hardware. Applied
automatically on connect; call it manually after changing a setting.

**Clear Bus** — sends the I2C bus-clear sequence to release a stuck SDA line.

**Scan Addresses** — probes 0x03–0x77 for ACKs. A progress dialog runs; results
are written to the Device Info log.

**Self-Test** — reads DWF version, die temperature, and USB supply voltage into
the Device Info pane.

### Device Info / Log

A scrolling text log of connection events, config changes, scan results, and
self-test output. Informational only; not saved on close.

---

## Sniffer Tab

The Sniffer tab controls passive listening and hosts the log-table controls in
its sidebar. In passive (spy) mode the AD2 only observes — it never drives SCL or
SDA — so it can sit in parallel with an existing bus.

### I2C Sniffer (Passive)

**▶ Start Sniffing** — activates the spy (enabled once a device is connected and
configured). The status bar shows "● Sniffing" in green.

**■ Stop Sniffing** — deactivates the spy; captured rows remain.

**Validate SMBus PEC (CRC-8)** — when checked, each frame's last byte is validated
as an SMBus CRC-8 over `[8-bit address, data bytes…]`. Failures are flagged with a
red PEC cell.

**SCL: n/a** — beside the Idle/Sniffing indicator. The ion sniffer shows the
measured SCL clock there; the AD2 I2C spy reports bytes only, so this sniffer
shows *n/a* (the two apps share one layout).

### Capture Stats

| Label | Description |
|---|---|
| Captured | Total transactions received since Start |
| Spy errors | Hardware-level protocol errors (lost sync, overflow) |
| Visible (filtered) | Rows currently shown after filters |
| Total in log | All rows regardless of filters |

### Table Data

**Clear Log** — removes all rows (does not stop an active sniffer).
**Export CSV** — saves the visible (filtered) rows as CSV. The format is
interchangeable with the Replay app and the Decoder Editor's "Test Against
Capture."
**Auto-scroll** — when checked, the log scrolls to the newest row on each arrival.

### Load Decoder File

Pick a decoder JSON to populate the **Decode** column live. The status line shows
*none*, *name ✓ valid decoder (N rules)* (green), or *name ✗ error* (red).
Selecting a decoder re-decodes the rows already captured.

### Editor

**Launch** — opens the standalone Decoder Editor, pre-loaded with the decoder file
selected above (if any). If the editor is already open, it is brought to the front.

### Wiring for Spy Mode

```
AD2 DIO 0  ──┬──── SCL (tap, do not drive)
             └──── SCL bus line (has pull-up, driven by the existing master)
AD2 DIO 1  ──┬──── SDA (tap, do not drive)
             └──── SDA bus line (has pull-up, driven by the existing master)
AD2 GND    ──────── GND of target board
```

Do not add a second master to the bus. The AD2 is passive; your host system must
remain the sole master.

---

## Transaction Log

The table (right of the Sniffer tab) captures every sniffed frame.

### Columns

| Column | Description |
|---|---|
| **Time** | Wall-clock timestamp at capture |
| **#** | Session sequence number |
| **Addr** | 7-bit device address in hex |
| **Dir** | `R` (read) or `W` (write) |
| **Len** | Number of data bytes |
| **Data (hex)** | Raw bytes in hex |
| **Int** | Big-endian unsigned integer of the data bytes |
| **ASCII** | Printable ASCII (`.` for non-printable) |
| **Decode** | Human-readable value from the loaded decoder |
| **NAK** | `NAK` if not acknowledged |
| **Start** | `S` (Start) or `Sr` (Repeated Start) |
| **Stop** | `P` if a Stop ended the frame |
| **PEC** | SMBus CRC-8 result (empty if PEC validation is off) |

### Color Coding

| Condition | Color |
|---|---|
| Read transaction | Green (`data_read`) |
| Write transaction | Blue (`data_write`) |
| NAK received | Red (`data_nak`) |
| PEC check failed | Dark red background (`data_pec_fail_bg`) |

With **Show CRC** on, the PEC/CRC value itself is colored green (valid) or red
(invalid) in addition to the row background on failure.

### Decode Column

The Decode column is blank until a decoder JSON is loaded from the **Load Decoder
File** section. Use the **Editor** section (or `decoder_editor.py`) to author or
modify decoder files.

### Filters

**Search** — live filter over hex data, address text, or ASCII.
**Dir** — All / Read only / Write only.
**Addr filter** — three modes from the dropdown:
- **Capture All** — capture/show all addresses (default)
- **Include Only** — capture only the listed addresses; other traffic is discarded
- **Exclude** — capture all but hide the listed addresses

Enter addresses as space-separated hex (`0x08 0x50 0x68`); **Apply** to commit,
**Reset** to clear.

### Display options

Two view-only checkboxes on the right of the filter bar change how the table is
presented. They affect display only — the CSV export always uses the canonical
7-bit form, so exported captures stay interchangeable with Replay and the editor.

**8-bit address** — off by default. The bus puts a 7-bit target address plus a
1-bit R/W flag on the wire. By default the **Addr** column shows the **7-bit**
address (e.g. `0x08`) and **Dir** shows `R`/`W` separately. Tick this to show the
**8-bit** first byte with R/W folded into bit 0 — the form TI's datasheet uses
(`0x10` write, `0x11` read for a 7-bit `0x08`). In this mode **Dir** reads
`W (bit0)` / `R (bit0)` to make clear the direction is the address's low bit.
The two are the same address: `0x10 >> 1 == 0x11 >> 1 == 0x08`.

**Show CRC** — on by default. Shows the **PEC/CRC** column and colors its value
**green** when the SMBus CRC-8 is valid and **red** when it is invalid. Untick to
hide the column. The BQ76905 ships with CRC disabled, so the column is usually
blank until CRC is enabled on the device and PEC validation is turned on (see the
Sniffer tab's *Validate SMBus PEC* control, which computes the value during live
capture).

---

## Preferences Tab

Select a color theme and click **Apply Theme**; the change is immediate.

| Theme | Description |
|---|---|
| System | Follows OS appearance, defaults to Dark |
| Light | Light backgrounds, dark text |
| Dark | VS Code-style dark (default) |
| Engineering Dark | Catppuccin-inspired, blue accent |
| Iontra Dark | GitHub-style deep dark, cyan accent |
| Iontra Light | GitHub-style light |
| Dark Claude | Warm near-black, terracotta accent |

---

## Help & Exit Tabs

**Help** — shows the project name, version, and last-updated date, then renders
this User Guide with the active theme (colored headings and code, bordered
tables). It re-renders when you change the theme in Preferences.

**Exit** — click **Close Application** to quit. If captured transactions are still
in the log, you're asked to confirm before they're discarded. The window's close
button uses the same confirmation.

---

## Troubleshooting

| Problem | Resolution |
|---|---|
| "DWF load error" on startup | Install Digilent WaveForms + Adept Runtime; restart. |
| Device dropdown shows "(no devices found)" | Click Refresh; ensure the AD2 is plugged in and not held by WaveForms IDE. |
| "Connect Failed" | Device open in another app; close WaveForms IDE and retry. |
| Bus stuck (SDA low) | Click **Clear Bus** on the Device tab. |
| No sniffer data | Verify SCL/SDA pin assignments match the wiring; confirm the bus has pull-ups and traffic. |
| Sniffer errors (`protocol error -1/-2/-3`) | The spy started mid-transaction; harmless and clears on the next full frame. |
| Buffer overflow warning | Bus rate exceeds capture bandwidth; lower the I2C clock or reduce activity. |
| PySide6 import fails on Ubuntu | Run `sudo apt install libgl1 libxkbcommon0` and relaunch. |
| Log fills up on long captures | Use the address Include/Exclude filter to capture only the device of interest. |
