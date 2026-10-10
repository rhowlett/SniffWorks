# BQ76905 Gateway Tool — User Guide

**NUCLEO-C031C6 + BQ76905EVM I²C Gateway**  
Revision 1.0

---

## Contents

1. [Overview](#1-overview)
2. [Hardware Setup](#2-hardware-setup)
3. [Firmware Setup — STM32CubeIDE](#3-firmware-setup--stm32cubeide)
4. [Flashing the NUCLEO](#4-flashing-the-nucleo)
5. [Serial Terminal — macOS](#5-serial-terminal--macos)
6. [Serial Terminal — Ubuntu 22+](#6-serial-terminal--ubuntu-22)
7. [Gateway Commands — Reference](#7-gateway-commands--reference)
8. [First Use — Sanity Checks](#8-first-use--sanity-checks)
9. [Reading Registers](#9-reading-registers)
10. [Subcommands](#10-subcommands)
11. [Building a Sequence](#11-building-a-sequence)
12. [Python GUI](#12-python-gui)
13. [Troubleshooting](#13-troubleshooting)

---

## 1  Overview

This project turns a NUCLEO-C031C6 into a USB-to-I²C gateway, allowing a PC to communicate directly with a BQ76905 battery monitor EVM using simple ASCII commands over a serial terminal or the provided Python GUI.

```
  ┌──────────────┐  USB/VCP    ┌─────────────────┐  I²C      ┌────────────────┐
  │   PC / Mac   │◄───────────►│ NUCLEO-C031C6   │◄─────────►│  BQ76905EVM    │
  │              │  115200 baud│ STM32C031C6T6   │  400 kHz  │  J4 connector  │
  │  Terminal or │             │                 │           │  addr 0x08     │
  │  Python GUI  │             │ PA9=SCL PA10=SDA│           │                │
  └──────────────┘             └─────────────────┘           └────────────────┘
```

**What the firmware does:** it sits in a loop waiting for ASCII commands on the serial port, executes the requested I²C transaction, and sends back the result. No BQ76905 knowledge is baked into the firmware — all decoding happens in the Python GUI using the `bq76905_decoder.json` file.

---

## 2  Hardware Setup

### Wiring — NUCLEO to BQ76905EVM J4

J4 is the 4-pin right-angle header on the BQ76905EVM labelled **External I2C Connection**.

| NUCLEO-C031C6 | Wire | BQ76905EVM J4 |
|---------------|------|----------------|
| CN5 Pin 1 — D8 / PA9 | Blue | Pin 3 — SCL |
| CN6 Pin 3 — D2 / PA10 | Green | Pin 2 — SDA |
| Any GND | Black | Pin 1 — GND |
| — | — | Pin 4 — NC (leave open) |

> PA9 is **Arduino D8** on the right-side header CN5.  
> PA10 is **Arduino D2** on the left-side header CN6.

### BQ76905EVM Jumper Settings

| Jumper | Setting | Purpose |
|--------|---------|---------|
| J1 | **Install** | SCL pull-up to REGOUT |
| J5 | **Install** | SDA pull-up to REGOUT |
| J2 | **Remove** | Disconnect on-board MCU from SCL |
| J6 | **Remove** | Disconnect on-board MCU from SDA |

> ⚠️ J2 and J6 must be removed. If left in, the on-board MSP430 will fight for the bus.

---

## 3  Firmware Setup — STM32CubeIDE

### 3.1  What you need

- STM32CubeIDE ≥ 1.14 — free from [st.com](https://www.st.com/en/development-tools/stm32cubeide.html)
- The project zip: `Test_STM32C031_BQ76905.zip` (the original CubeIDE project)
- The update zip: `BQ76905_gateway_update.zip` (our files to overwrite)

### 3.2  Open the project in CubeIDE

1. Unzip `Test_STM32C031_BQ76905.zip` to a convenient location.
2. In STM32CubeIDE: **File → Open Projects from File System…**
3. Click **Directory…**, select the `Test_STM32C031_BQ76905` folder → **Finish**.
4. The project appears in the Project Explorer.

### 3.3  Overwrite the modified files

Unzip `BQ76905_gateway_update.zip` and copy the files into your project, preserving folder structure. The update contains:

```
BQ76905_NUCLEO_Setup_Guide.md              ← documentation (parent folder)
Test_STM32C031_BQ76905/
  .cproject                                ← fixes build config (CMSIS exclusions + -Os)
  Core/Src/main.c                          ← gateway application
  Core/Src/stm32c0xx_it.c                  ← adds USART2 receive interrupt handler
```

> `stm32c0xx_hal_msp.c` is **not modified** — the CubeMX-generated I²C MSP for PA9/PA10 is already correct.

### 3.4  Select the Release configuration

In CubeIDE:

**Project → Build Configurations → Set Active → Release**

> Use Release rather than Debug. The STM32C031C6 has 32 KB flash and the full HAL stack at -O0 (Debug) is too large. Release uses -Os and produces a ~21 KB binary with room to spare.

### 3.5  Build

**Project → Clean Project**, then **Project → Build All** (or **Ctrl+B** / **⌘+B**).

Expected console output:
```
arm-none-eabi-size  Test_STM32C031_BQ76905.elf
   text    data     bss     dec     hex filename
  20964     100    3340   24404    5f54 Test_STM32C031_BQ76905.elf
Build Finished. 0 errors, 0 warnings.
```

If you see errors about CMSIS headers or FLASH overflow, make sure the `.cproject` from the update zip was copied correctly and do a Clean + Build again.

### 3.6  Locate the binary

The built binary is in the CubeIDE workspace, **not** in your source folder. Find it with:

```bash
find ~/STM32CubeIDE -name "*.elf" 2>/dev/null
```

Typical path:
```
~/STM32CubeIDE/workspace_2.1.1/Test_STM32C031_BQ76905/Release/Test_STM32C031_BQ76905.elf
```

---

## 4  Flashing the NUCLEO

### Method A — Drag and drop (recommended, no extra tools)

The NUCLEO-C031C6 appears as a USB drive when plugged in (named `NOD_C031C6` on macOS).

1. Connect the NUCLEO via micro-USB.
2. Open Finder (macOS) or Files (Ubuntu) — the drive appears automatically.
3. Drag the `.elf` file onto the drive.
4. The orange LED on the NUCLEO flickers for a second.
5. The board reboots and starts running the firmware.

> **macOS note:** You will see *"Disk Not Ejected Properly"* — this is normal. The NUCLEO reboots mid-mount, macOS complains. The flash was successful.

### Method B — Run from CubeIDE

**Run → Run** (green ▶ button, **Ctrl+F11**). If you see a popup about ST-Link Server:

1. **Run → Run Configurations…**
2. Click the **Debugger** tab
3. Change **Debug probe** from `ST-Link Server` to `ST-LINK (OpenOCD)`
4. Click **Apply → Run**

### Confirming the flash worked

After flashing, the **green LED** on the NUCLEO should be on solid. If it blinks rapidly, the firmware crashed — try reflashing.

---

## 5  Serial Terminal — macOS

### Find the port

```bash
ls /dev/cu.usbmodem*
```

The NUCLEO will be the `usbmodem` entry. If there are multiple, unplug the board, run the command, replug, run again — the new entry is yours.

### Connect

```bash
screen /dev/cu.usbmodemXXXX 115200
```

Replace `usbmodemXXXX` with your actual port name.

### Verify

Press the black **RESET** button on the NUCLEO. You should immediately see:

```
BQ76905GW v1.0
```

Type `VER` and press Enter to get the same response on demand.

### Exit screen

```
Ctrl+A  then  K  then  Y
```

Or just close the Terminal window. The NUCLEO keeps running regardless.

---

## 6  Serial Terminal — Ubuntu 22+

### Port permissions (one-time setup)

```bash
sudo usermod -aG dialout $USER
```

Log out and back in for this to take effect.

### Find the port

```bash
ls /dev/ttyACM*
```

The NUCLEO will appear as `/dev/ttyACM0` (or `ttyACM1` if other devices are connected).

### Connect with screen

```bash
screen /dev/ttyACM0 115200
```

### Or connect with minicom

```bash
sudo apt install minicom    # if not installed
minicom -b 115200 -D /dev/ttyACM0
```

In minicom, turn off hardware flow control: **Ctrl+A → O → Serial port setup → F** (toggle Hardware Flow Control to No) → Save.

### Verify

Press the NUCLEO **RESET** button. Expected:

```
BQ76905GW v1.0
```

### Exit screen

```
Ctrl+A  then  K  then  Y
```

---

## 7  Gateway Commands — Reference

All commands are ASCII, terminated by Enter (CR or LF). Responses end with `\r\n`.

All numbers are **hexadecimal** except the byte count in `READREG` and `RAWREAD`, which is **decimal**.

| Command | Format | Example | Response |
|---------|--------|---------|----------|
| Version | `VER` | `VER` | `BQ76905GW v1.0` |
| I²C scan | `SCAN` | `SCAN` | `OK 08` |
| Read register | `READREG <addr> <reg> <n>` | `READREG 08 14 2` | `OK 3E 0F` |
| Write register | `WRITEREG <addr> <reg> [data…]` | `WRITEREG 08 3E 22 00` | `OK` |
| Raw read | `RAWREAD <addr> <n>` | `RAWREAD 08 4` | `OK A5 FF 00 01` |
| Raw write | `RAWWRITE <addr> [data…]` | `RAWWRITE 08 3E` | `OK` |
| Set I²C speed | `SPEED <100\|400>` | `SPEED 100` | `OK` |

**Error responses:**

| Response | Meaning |
|----------|---------|
| `ERR NACK` | Device did not acknowledge — wrong address, device missing, or bus fault |
| `ERR TIMEOUT` | No response within 1 second — check wiring and pull-ups |
| `ERR BUSY` | I²C bus is busy |
| `ERR PARAM` | Unrecognised command or bad argument |

---

## 8  First Use — Sanity Checks

Do these in order after connecting to the serial terminal.

### Step 1 — Confirm firmware is running

```
VER
```

Expected:
```
BQ76905GW v1.0
```

If nothing appears, press the RESET button on the NUCLEO. If still nothing, reflash.

### Step 2 — Confirm I²C wiring

```
SCAN
```

Expected with EVM powered and wired:
```
OK 08
```

`08` is the BQ76905 7-bit I²C address. If the response is `OK` with no address, the bus is working but the device is not responding — check wiring, check EVM power (REGOUT should be ~3.3 V), and verify J1/J5 jumpers are installed.

### Step 3 — Read the device number (subcommand)

Write the `DEVICE_NUMBER` subcommand code (`0x0001`, little-endian) to register `0x3E`, then read 2 bytes from register `0x40`:

```
WRITEREG 08 3E 01 00
READREG 08 40 2
```

Expected response:
```
OK
OK 05 00
```

`0x0005` = BQ76905 device number. This confirms two-way register communication is working correctly.

### Step 4 — Read a cell voltage

```
READREG 08 14 2
```

Returns 2 bytes, little-endian signed, in millivolts. If cells are connected and balanced you'll see something like `OK 88 13` (0x1388 = 5000 mV). With cell simulator shunts but no real cells the reading will be near zero — that is normal.

---

## 9  Reading Registers

### Key register addresses

| Register | Name | Bytes | Format | Unit |
|----------|------|-------|--------|------|
| `0x14` | Cell 1 Voltage | 2 | LE signed | mV |
| `0x16` | Cell 2 Voltage | 2 | LE signed | mV |
| `0x18` | Cell 3 Voltage | 2 | LE signed | mV |
| `0x1A` | Cell 4 Voltage | 2 | LE signed | mV |
| `0x1C` | Cell 5 Voltage | 2 | LE signed | mV |
| `0x26` | Stack Voltage | 2 | LE unsigned | mV |
| `0x3A` | Current (CC2) | 2 | LE signed | mA (1 mΩ sense) |
| `0x02` | Safety Alert A | 1 | bits | fault flags |
| `0x12` | Battery Status | 2 | bits | mode / FET state |

### Reading all cell voltages

```
READREG 08 14 2
READREG 08 16 2
READREG 08 18 2
READREG 08 1A 2
READREG 08 1C 2
```

### Decoding the response

The BQ76905 returns values little-endian. For `OK 3E 0F`:
- Low byte = `0x3E`, high byte = `0x0F`
- Value = `0x0F3E` = 3902 decimal = **3902 mV**

For a signed value (current): if the high bit of the high byte is set, the value is negative.

### Reading the Safety Alert register

```
READREG 08 02 1
```

| Bit | Flag |
|-----|------|
| 7 | SSC — short circuit in charge |
| 6 | SSD — short circuit in discharge |
| 5 | OCC — overcurrent in charge |
| 4 | OCD1 — overcurrent in discharge |
| 3 | COV — cell overvoltage |
| 2 | CUV — cell undervoltage |
| 1 | OLVF — internal voltage fault |
| 0 | HWDF — hardware fault |

A response of `OK 00` means no faults. `OK 08` means bit 3 is set — cell overvoltage alert.

---

## 10  Subcommands

The BQ76905 has a two-step subcommand interface: write a 2-byte command code (little-endian) to register `0x3E`, then optionally read the response from register `0x40`.

**Pattern for write-only subcommands:**
```
WRITEREG 08 3E <lo> <hi>
```

**Pattern for read subcommands:**
```
WRITEREG 08 3E <lo> <hi>
READREG 08 40 <n>
```

### Common subcommands

| Subcommand | Code | Type | Example |
|------------|------|------|---------|
| DEVICE_NUMBER | `0x0001` | Read 2B | Verify device |
| HW_VERSION | `0x0003` | Read 2B | Hardware revision |
| RESET_PASSQ | `0x0005` | Write | Reset accumulated charge |
| FET_ENABLE | `0x0022` | Write | Enable CHG and DSG FETs |
| SET_CFGUPDATE | `0x0090` | Write | Enter configuration mode |
| EXIT_CFGUPDATE | `0x0092` | Write | Exit configuration mode |
| CB_ACTIVE_CELLS | `0x0053` | Read/Write 1B | Cell balancing mask |
| RESET | `0x0012` | Write | Full device reset |
| SHUTDOWN | `0x0010` | Write | Enter shutdown mode |

### Example — Enable FETs

```
WRITEREG 08 3E 22 00
```

The BQ76905 enables the CHG and DSG FET drivers. No response data — just `OK`.

### Example — Read hardware version

```
WRITEREG 08 3E 03 00
READREG 08 40 2
```

Response example: `OK 00 00` (version bytes).

### Example — Enter and exit config update mode

Some configuration registers can only be written while in `CONFIG_UPDATE` mode:

```
WRITEREG 08 3E 90 00
```
*(make your configuration register writes here)*
```
WRITEREG 08 3E 92 00
```

---

## 11  Building a Sequence

A sequence is a series of gateway commands run one after another, typically replaying an EVM capture or performing a structured readout. There are two ways to build and run one.

### Method A — Shell script

Write the commands to a script and pipe them to `screen` or use a serial send tool.

The simplest approach on macOS/Linux: use a heredoc with a small delay between commands.

```bash
#!/bin/bash
PORT=/dev/cu.usbmodemXXXX   # replace with your port

send() {
    echo -e "$1\r" > $PORT
    sleep 0.1
}

# Open port
stty -f $PORT 115200 cs8 -cstopb -parenb

# Sanity checks
send "VER"
send "SCAN"

# Read all cell voltages
send "READREG 08 14 2"
send "READREG 08 16 2"
send "READREG 08 18 2"
send "READREG 08 1A 2"
send "READREG 08 1C 2"

# Read stack and current
send "READREG 08 26 2"
send "READREG 08 3A 2"

# Read status
send "READREG 08 02 1"
send "READREG 08 12 2"
```

Run with:
```bash
chmod +x readout.sh
./readout.sh
```

### Method B — Python GUI sequence player

The Python GUI can load a CSV capture file from the BQ76905 EVM software and replay it against the real hardware. This is useful for verifying that a known-good sequence from the EVM tool produces the same results through the gateway.

**CSV format** (same columns as an EVM long capture):

```
Time,#,Addr,Dir,Len,Data (hex),ASCII,NAK,Start,Stop,PEC
00:00:00.000,1,0x08,W,1,3E,>,,,S,,
00:00:00.010,2,0x08,W,2,01 00,..,,S,P,
00:00:00.020,3,0x08,W,1,40,@,,S,,
00:00:00.030,4,0x08,R,2,05 00,..,,Sr,P,
```

The sequence player reads the CSV and:
- Converts **Write-then-Read (no stop + repeated start)** pairs → `READREG`
- Converts **Write with stop** → `WRITEREG`
- Sends each command with a configurable delay between them (default 50 ms)

**To run a sequence in the GUI:**
1. Launch `python3 bq76905_gateway_tool.py`
2. Connect to the NUCLEO COM port
3. In the **Sequence Capture** panel, click **Load CSV…** and select your capture file
4. Adjust the delay slider if needed (longer for slower devices)
5. Click **▶ Run**
6. When complete, click **💾 Export CSV** to save the results

### Building your own sequence CSV

You can write a sequence CSV by hand. The minimal required columns are `Addr`, `Dir`, `Len`, `Data (hex)`, `Start`, and `Stop`. The rules:

- A **write row** with `Stop=P` becomes `WRITEREG` (write data to register)
- A **write row** with no stop, followed by a **read row** with `Start=Sr` (repeated start) becomes `READREG`
- A **read row** with `Start=S` (fresh start) becomes `RAWREAD`

**Minimal sequence to read Device Number:**

```
Time,#,Addr,Dir,Len,Data (hex),ASCII,NAK,Start,Stop,PEC
00:00:00.000,1,0x08,W,3,3E 01 00,>..,,S,P,
00:00:00.010,2,0x08,W,1,40,@,,S,,
00:00:00.020,3,0x08,R,2,,,,,Sr,P,
```

**Minimal sequence to read all 5 cell voltages:**

```
Time,#,Addr,Dir,Len,Data (hex),ASCII,NAK,Start,Stop,PEC
00:00:00.000,1,0x08,W,1,14,.,S,,
00:00:00.010,2,0x08,R,2,,,Sr,P,
00:00:00.020,3,0x08,W,1,16,.,S,,
00:00:00.030,4,0x08,R,2,,,Sr,P,
00:00:00.040,5,0x08,W,1,18,.,S,,
00:00:00.050,6,0x08,R,2,,,Sr,P,
00:00:00.060,7,0x08,W,1,1A,.,S,,
00:00:00.070,8,0x08,R,2,,,Sr,P,
00:00:00.080,9,0x08,W,1,1C,.,S,,
00:00:00.090,10,0x08,R,2,,,Sr,P,
```

---

## 12  Python GUI

### Installation

```bash
# macOS / Ubuntu
python3 -m venv venv
source venv/bin/activate
pip install PySide6 pyserial
```

### Launch

Place `bq76905_decoder.json` in the same folder as `bq76905_gateway_tool.py` — it auto-loads on startup.

```bash
python3 bq76905_gateway_tool.py
```

### Layout

```
┌─ Connection bar ─────────────────────────────────────────────────────┐
│ Port [/dev/cu.usbmodemXXXX ▾]  [Connect]  Decoder [41 rules]  400kHz│
└──────────────────────────────────────────────────────────────────────┘
┌─ Decoder tree ──────┬─ Transaction log (last 20) ───────────────────┐
│ ▸ Readings (25)     │ # Time    Dir Addr Reg  Len Data      Decoded  │
│   Cell 1 Voltage    │ live updates, newest at top                    │
│   Cell 2 Voltage    ├────────────────────────────────────────────────┤
│   …                 │ Manual Command                                 │
│ ▸ Subcommands (16)  │ Addr [08] Reg [14] Len [2]                    │
│   FET_ENABLE        │ [◀ Read]  [▶ Write]  [⇄ Subcommand]  [Scan]  │
│   RESET             ├────────────────────────────────────────────────┤
│   …                 │ Sequence Capture                               │
│                     │ [Load CSV…]  [▶ Run]  [■ Stop]  Delay [50ms] │
└─────────────────────┴────────────────────────────────────────────────┘
```

### Basic workflow

1. Select port → **Connect** → status bar shows `● Connected` and firmware version
2. Click any register in the Decoder tree — fields auto-populate
3. Click **◀ Read** — result appears in the transaction log with decoded value
4. For subcommands, click the subcommand name → **⇄ Subcommand** — the GUI handles the two-step write/read automatically

---

## 13  Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| No banner after RESET | Firmware not flashed or wrong baud rate | Reflash; confirm terminal at 115200 |
| `SCAN` returns `OK` with no addresses | EVM unpowered or wiring fault | Check REGOUT = 3.3 V; verify J4 wiring |
| `ERR NACK` on every command | Bus conflict or J2/J6 still installed | Remove J2 and J6 shunts |
| `ERR TIMEOUT` | Missing pull-ups | Confirm J1 and J5 shunts installed |
| Cell voltages read zero | No cells connected, cell simulator only | Normal — simulator shunts give ~0 V |
| macOS "Disk not ejected" after drag-and-drop | NUCLEO rebooted mid-mount | Normal — flash succeeded |
| CubeIDE flash popup about ST-Link Server | Wrong debug probe selected | Change to ST-LINK (OpenOCD) in Run Configurations |
| Build fails — FLASH overflow | Debug config at -O0 | Use Release config, or confirm `.cproject` update was applied |
| Python: `No module named PySide6` | venv not activated | `source venv/bin/activate` then `pip install PySide6 pyserial` |

---

*BQ76905 is a product of Texas Instruments. For development and evaluation use only.*
