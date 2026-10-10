# Ion I2C Sniffer — User Guide

**Supported probe boards:** NUCLEO-C031C6 (current default) and the planned
standalone STM32C0 "ion" board with a USB-UART bridge. The firmware, wire
protocol, and this app are identical for both; only the USB port
identification differs (ST-LINK vs a generic bridge — both are flagged in
the Device tab's port list, and the PING→HELLO handshake is the definitive
identity check).

Passive I2C / SMBus sniffer using an **STM32C0 probe** in place of the
Analog Discovery 2. The board runs the `sniffer_nucleoC0_fw` firmware and
streams decoded transactions over its ST-LINK virtual COM port; this app
logs, filters, live-decodes, and exports them.

## 1. Hardware setup

| Signal | Nucleo pin | MCU pin |
|--------|-----------|---------|
| SCL    | **D8** (CN5 pin 1)  | PA9  |
| SDA    | **D2** (CN9 pin 3)  | PA10 |
| GND    | any GND   | —    |

Connect SCL/SDA **in parallel** with the bus under test (the sniffer never
drives the bus). Plug the Nucleo's USB (ST-LINK) into the host — it provides
both power and the serial link.

Flash `sniffer_nucleoC0_fw` (bit-bang variant, the default build) via
CubeIDE or `st-flash`/CubeProgrammer with the produced `.hex`/`.bin`.

## 2. Connecting

1. **Device tab** → *Refresh*. The Nucleo appears as an **[ST-LINK]** port
   (VID 0x0483) and sorts to the top.
2. Select it and press **Connect**. This arms the app; the serial session
   itself opens when sniffing starts (the firmware is silent until then, so
   nothing is lost).
3. The baud rate is in the **Serial** group on the Device tab (default
   **115200**, which matches the firmware's `HOST_UART_BAUD`; change both
   together if you rebuild the firmware for a faster rate). It is locked
   while connected.
4. The **Probe** group fills in the firmware version, mode and protocol from
   the probe's HELLO when sniffing starts. The Device tab has the same layout
   as the AD2 sniffer's: a **Device** group (selector, Refresh, Connect /
   Disconnect, ● status), then the probe-specific groups, then
   **Device Info / Log**.
5. **Name your boards** once with **Name devices…** (below); after that the
   probe is found by name and pre-selected even when its port name changes.

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

## 3. Sniffing

* **Sniffer tab** → *Start Sniffing*. The app pings the board, receives its
  HELLO (firmware version + mode shown in the status bar), and starts the
  capture. Transactions appear live in the log table.
* One row per address phase; a repeated START shows as `rS` (start = 2),
  matching the AD2 sniffer's convention.
* **Validate SMBus PEC** treats the last data byte as an SMBus PEC and marks
  failures (row highlighted with the theme's `data_pec_fail_bg`).
* **Start Sniffing** and **Stop Sniffing** sit side by side. Next to the
  *Idle / Sniffing* indicator, **SCL:** shows the clock the probe measured
  on the most recent transaction (firmware ≥ 1.3; updated by the 1 Hz STATUS
  frame, reset to "—" at each Start). It follows speed changes on the bus.
* The log's **SCL** column shows the frequency measured for **each**
  transaction (kHz; exported to CSV as integer Hz in the `SCL (Hz)` column).
  Clock-stretched bits are excluded from the measurement. Blank = not
  measured (firmware ≤ 1.2, or slave-monitor / master firmware). The status bar repeats it together with
  a **dropped** count if the firmware's UART ring overflows.
* Firmware ≥ 1.2 flags any phase whose bits slipped because the probe lost a
  bus edge (TXN `FRAMING` flag): the app reports "framing error at 0x..",
  and the *Spy errors* count goes up. Don't trust that row's bytes.
* *Stop Sniffing* sends STOP and drains the final frames.

Timestamps come from the device's microsecond clock (anchored to wall time
at the first frame), so inter-transaction spacing is hardware-accurate even
when the host is busy.

## 4. Filtering / decoding / export

Identical to the AD2 sniffer:

* Filter bar above the table: address, direction, text search, include /
  exclude address lists, auto-scroll.
* **Load Decoder File** applies a decoder JSON (e.g.
  `i2c_decoders/bq76905_decoder.json`) for live decode of known registers.
* **Editor → Launch** opens the Decoder Editor on the loaded decoder.
* **Export CSV** writes the (filtered) log in the shared capture-CSV format
  used by `i2c_replay.py`.

## 5. Troubleshooting

| Symptom | Check |
|---------|-------|
| "no HELLO" on start | Firmware flashed? Correct port? Baud matches firmware? Board just reset (retry)? |
| No transactions | SCL on **D8** and SDA on **D2** (not D3), common ground, bus actually active. |
| `dropped > 0` in status bar | Bus traffic exceeds 115200 baud drain rate — raise `HOST_UART_BAUD` in the firmware **and** Device tab → Serial. |
| "framing error" messages | The probe missed an SCL edge. Firmware 1.1 did this on nearly every repeated START (Sr reads logged as e.g. `0x21 W [00 03]` instead of `0x10 R [00 01]`); reflash with firmware ≥ 1.2. If it persists, the bus is faster than the probe can sample. |
| Bus kHz looks low | Firmware ≥ 1.3 reports the mean un-stretched SCL period of each transaction (≈ ±0.5 % at 100 kHz, ±2 % at 400 kHz in simulation). Many adapters bit-bang well below their nominal rate; verify with a scope if it matters. Firmware ≤ 1.2 reported 1e6 / shortest period, 1 µs resolution. |
| Nothing captured on a 400 kHz bus | Known limitation (review B31). Firmware 1.6 samples every edge by interrupt and is reliable at 100 kHz. At 400 kHz the edges come faster than the C031 can record them: STARTs are missed, no rows appear and `errors` counts up. Use the AD2 sniffer for 400 kHz buses. |
| SCL column blank | Firmware ≤ 1.2 (reflash), slave-monitor or master firmware, or a phase with fewer than 4 clean clocks. |

## 6. Protocol

The wire protocol (framing, CRC-8, commands) is documented in the firmware
repository: `embedded/docs/PROTOCOL.md`. Host-side implementation:
`core/ion_protocol.py` (shared with the CLI sanity-check script and the
planned record/replay tooling).
