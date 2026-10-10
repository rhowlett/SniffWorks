# Loopback DUT — Setup Guide (NUCLEO-H533RE)
<!-- v0.9 -->

**Purpose:** get the I2C loopback rig wired, configured in STM32CubeMX, and verified from the
command line, so the DUT firmware, the host script and the sniffer captures all start from the
same known state.

**Status of this document:** pre-firmware. Sections 4–5 are what the owner does in CubeMX now;
section 6 is what you run to prove the bench is ready. Values marked *(datasheet)* come from the
cited ST document; values marked *(to measure)* have not been measured on this rig yet.

Sources used:

| Doc | ID | Used for |
|---|---|---|
| STM32H533xx datasheet | DS14539 Rev 3 | I2C count (§3.35, Table 8), pinout, AF table (Table 15) |
| NUCLEO-H533RE user manual | UM3121 Rev 6 | Arduino/morpho pinout (Table 16), VCP (§12.4), LD2/B1, HSE/MCO (§11.2) |
| MB1814 schematic | MB1814-H533RE-C02 | cross-check of connector nets |

---

## 1. What the rig is

The **loopback DUT** is a standalone instrument. It generates known I2C traffic between its own
peripherals and tells the PC exactly what it put on the bus. The devices under test are the
**sniffers**, which only listen.

```
             USB (ST-LINK V3EC VCP)                USB (ST-LINK VCP)       USB
   PC ─────────────────────────┐          PC ──────────────┐       PC ─────┐
   loopback_dut/host/          │          sniffer_ion.py   │       sniffer_ad2.py
   loopback_run.py             │                           │               │
                    ┌──────────┴──────────┐     ┌──────────┴───────┐  ┌────┴────┐
                    │  NUCLEO-H533RE (DUT)│     │ NUCLEO-C031C6    │  │  AD2    │
                    │  I2C1  master  0x08 │     │ sniffer fw       │  │ DIO0/1  │
                    │  I2C2  slave   0x6B │     │ (under test)     │  │ (under  │
                    │  I2C3  slave   0x55 │     │                  │  │  test)  │
                    └───┬──────┬──────────┘     └───┬──────┬───────┘  └─┬────┬──┘
                        │SCL   │SDA                 │SCL   │SDA         │SCL │SDA
   ═════════════════════╪══════╪════════════════════╪══════╪════════════╪════╪═════ SCL bus
   ═════════════════════════════════════════════════════════════════════════════════ SDA bus
                        4.7 kΩ to 3V3 on each line (one pair only), common GND
```

**Isolation rule:** nothing under `loopback_dut/` imports from `core/`, `ui/` or the sniffer
firmware, and nothing in the sniffer tools imports from `loopback_dut/`. The two sides meet
only in files: the DUT writes `expected.json`, the sniffer writes its CSV, and
`loopback_dut/host/loopback_compare.py` reads both.

### Address plan (owner decision, 2026-09-30)

| Peripheral | Role | 7-bit address | Mirrors |
|---|---|---|---|
| I2C1 | **master** (drives every case) | own address 0x08 | BQ76905 / BQ76922 address |
| I2C2 | slave responder | **0x6B** | BQ25731 |
| I2C3 | slave responder | **0x55** | — |

**0x08 is the address-NAK test case** (owner decision, 2026-09-30). I2C1 is the only master
and a master cannot ACK its own address, so every access to 0x08 must be NAKed. That makes it a
deterministic NAK case (LB-05) that also sits on the BQ76905/BQ76922 address, which checks that
the sniffer does not decode a NAKed phase as register data.

### Rig configuration file: every address is adjustable

The addresses above are **defaults, not constants**. One file, `loopback_dut/config/rig.toml`,
holds the rig parameters. **Both** the DUT PC software (`loopback_run.py`) and the validation
script (`loopback_compare.py`) read it, so a field-observed edge case (an odd address, a
different speed, a responder that should NAK) can be set up by editing one file, with no
firmware rebuild:

```toml
# loopback_dut/config/rig.toml — shared by loopback_run.py and loopback_compare.py
[master]                     # I2C1
own_address = 0x08
scl_hz      = 100_000        # default; each pattern case may override

[[responder]]                # I2C2
peripheral  = "I2C2"
address     = 0x6B
enabled     = true

[[responder]]                # I2C3
peripheral  = "I2C3"
address     = 0x55
enabled     = true

[nak]
addresses   = [0x08]         # accesses to these must be NAKed; compare checks it
```

At the start of every run the PC pushes the responder addresses to the DUT, which reprograms
I2C2/I2C3 `OAR1`. The CubeMX addresses (§4.5, §4.6) are only the power-up defaults. The config
used is copied into `expected.json`, so a report always records which addresses it was made
with.

---

## 2. Bill of materials

| Qty | Item | Notes |
|---|---|---|
| 1 | NUCLEO-H533RE (MB1814) | the DUT; ST-LINK V3EC on board, USB-C |
| 1 | NUCLEO-C031C6 | sniffer under test (existing `sniffer_nucleoC0_fw`) |
| 1 | Digilent Analog Discovery 2 | sniffer under test (`sniffer_ad2.py`), needs WaveForms installed |
| 2 | 4.7 kΩ resistor, ¼ W | SCL and SDA pull-ups to 3V3; **one pair on the whole bus** |
| 1 | small breadboard | holds the shared SCL/SDA/GND rails |
| ~12 | male–male / male–female jumpers | short (< 15 cm) keeps rise time sane at 400 kHz |
| 3 | USB cables | USB-C for H533, micro-USB for C031, USB for AD2 |

---

## 3. Wiring

### 3.1 DUT board — NUCLEO-H533RE

All three peripherals go to the **same** two bus nets. Pin, AF and connector values are
*(datasheet)*: DS14539 Table 15 (all six pins are **AF4**), UM3121 Table 16.

| Net | Signal | MCU pin | LQFP64 pin | Nucleo connector | AF |
|---|---|---|---|---|---|
| SCL | I2C1_SCL | PB6 | 58 | **D15** — CN5 pin 10 | AF4 |
| SDA | I2C1_SDA | PB7 | 59 | **D14** — CN5 pin 9 | AF4 |
| SCL | I2C2_SCL | PB10 | 29 | **D6** — CN9 pin 7 | AF4 |
| SDA | I2C2_SDA | PB12 | 33 | **morpho CN10 pin 16** (not on Arduino header) | AF4 |
| SCL | I2C3_SCL | PA8 | 41 | **D7** — CN9 pin 8 | AF4 |
| SDA | I2C3_SDA | PC9 | 40 | **D10** — CN5 pin 3 | AF4 |
| ALERT | GPIO out, open-drain | PB4 | — | **D5** — CN9 pin 6 | — (Phase 11; wire, unused) |
| SYNC | GPIO out, push-pull | PB5 | — | **D4** — CN9 pin 5 | — (scope trigger, pulses at case start) |
| 3V3 | pull-up supply | — | — | CN6 pin 4 (3V3) | — |
| GND | ground | — | — | CN6 pin 6 (GND) | — |

Pin notes:
- PA8 is free: the ST-LINK 8 MHz MCO goes to PF0/PH0 (OSC_IN), not to PA8 (UM3121 §11.2). The
  `T_MCO/PA8` label in the schematic is on the ST-LINK MCU's own PA8.
- PB12 is an `FT_h` pin, not `FT_f`, so the bus is **not Fm+ (1 MHz, 20 mA)** capable through
  I2C2. 100 kHz and 400 kHz are fine.
- Keep clear of: PA5 (LD2 user LED), PC13 (B1 user button), PA2/PA3 (VCP, see below),
  PA13/PA14 (SWD).

### 3.2 Sniffer — NUCLEO-C031C6 (existing firmware, unchanged pins)

From `embedded/sniffer_nucleoC0_fw/Core/Inc/sniffer_config.h` and
`documents/User_Guide_sniffer_ion.md`:

| Net | MCU pin | Nucleo connector |
|---|---|---|
| SCL | PA9 | **D8** — CN5 pin 1 |
| SDA | PA10 | **D2** — CN9 pin 3 |
| GND | — | any GND |

### 3.3 Sniffer — Analog Discovery 2

| Net | AD2 pin | Notes |
|---|---|---|
| SCL | DIO 0 | default in `core/i2c_controller.py` (`_scl_pin = 0`) |
| SDA | DIO 1 | default (`_sda_pin = 1`) |
| GND | any ↓ (GND) | |

### 3.4 Pull-ups and power

- **One** 4.7 kΩ from SCL to 3V3 and **one** from SDA to 3V3, taken from the H533 CN6 pin 4.
  Do not enable internal pull-ups on any board (they would add in parallel and are weak and
  imprecise anyway).
- **Tie every GND together**: H533, C031 and AD2.
- Each board is powered from its own USB. Do not connect the 3V3 rails of different boards.
- Rise-time sanity *(to measure)*: with 4.7 kΩ and roughly 50–100 pF of jumpers plus three
  inputs, t_r ≈ 0.85·R·C ≈ 200–400 ns. 400 kHz Fast-mode allows 300 ns. If the rise time at
  400 kHz is over 300 ns, drop to 2.2 kΩ and record it here.

---

## 4. STM32CubeMX configuration — NUCLEO-H533RE

Written against **STM32CubeMX 6.18.0** with **STM32Cube FW_H5 V1.7.0** (the versions in
`loopback_dut/firmware/firmware.ioc`). Every value below is set explicitly so the generated code
matches what the DUT firmware expects.

The project already exists at **`loopback_dut/firmware/firmware.ioc`**, project name
`firmware`. CubeMX will not rename a saved project, and the name is fine: it matches the folder
layout. Open that `.ioc`; do not create a new project.

### 4.0 Install the H5 firmware package first

**Status 2026-09-30: done.** FW_H5 V1.7.0 is installed, the project is regenerated, and
`make` in `loopback_dut/firmware/` builds with 0 warnings (text 23 020 B, bss 2 044 B). The
generated `OwnAddress1` values are 16 / 214 / 170 as §4.11 expects. The CubeMX BSP demo
`printf` (USER CODE BSP block) was removed because it no longer compiles without the BSP COM
port. Optionally untick *NUCLEO-H533RE → Bsp_Common_DEMO* so CubeMX stops generating demo
code. Debug still claims PA15/PB3 (JTAG/trace); that is harmless because neither pin is used.

Original instructions, kept for a rebuild from scratch:

The first generate (2026-09-30) produced only `Core/`: no `Drivers/`, `Makefile`, startup file
or linker script. That is because `~/STM32Cube/Repository/` contains no `STM32Cube_FW_H5_*`
folder. Fix:

1. CubeMX → **Help → Manage embedded software packages** → STM32H5 → tick **1.7.0** →
   **Install** (accept the licence).
2. Confirm: `ls ~/STM32Cube/Repository | grep H5` → `STM32Cube_FW_H5_V1.7.0`.
3. Make the corrections in §4.2, §4.3 and §4.8 below, then **Generate Code** again.

### 4.1 New project

1. **File → New Project → Board Selector** → `NUCLEO-H533RE`.
2. "Initialize all peripherals with their default mode?" → **No**. The defaults enable
   peripherals that collide with the pins in §3.1.
3. "Enable TrustZone?" → **No**.

### 4.2 System core

| Item | Setting |
|---|---|
| RCC → HSE | Crystal/Ceramic Resonator (X3, 24 MHz, board default) |
| SYS → Debug | Serial Wire |
| SYS → Timebase source | SysTick |
| ICACHE | Enabled, **1-way (direct mapped)**. Already set in `firmware.ioc`. In CubeMX 6.18 it is listed under *System Core → ICACHE*. |
| DCACHE1 | **Leave disabled.** On the H533 it caches external memories only (DS14539 §3.2.2), and this design has none. |
| SYS → Debug (*Trace and Debug → DEBUG*) | **Serial Wire.** The current `.ioc` also claims PA15 (JTDI) and PB3 (JTDO/SWO), which means a JTAG mode is selected. Serial Wire frees both; the Nucleo ST-LINK uses SWD. |
| GPIO PA5 | GPIO_Output, label `LD2` |
| GPIO PC13 | GPIO_Input, label `B1` |
| GPIO PB4 | GPIO_Output, **Open Drain**, no pull, output level **High**, label `DUT_ALERT` |
| GPIO PB5 | GPIO_Output, Push Pull, no pull, output level **Low**, label `DUT_SYNC` |

### 4.3 Clock configuration tab

| Item | Setting | Why |
|---|---|---|
| **HSE input frequency** | **24 MHz** (type it in the HSE box on the left of the Clock tab) | X3 on this board is 24 MHz (UM3121 §11.2: "24 MHz, 6 pF, and 20 ppm"). The current `.ioc` and `stm32h5xx_hal_conf.h` say **25 MHz**, the MX default, which would make SYSCLK really 240 MHz and put every PLL-derived clock, including the UART baud rate, 4 % off. |
| PLL1 source | HSE | |
| PLL1 M / N / P | **6 / 125 / 2** → 4 MHz ref, 500 MHz VCO, 250 MHz P | the current 2 / 40 / 2 assumes 25 MHz. Easiest: type 250 in the HCLK box and let MX solve, then confirm the values. |
| SYSCLK | 250 MHz (PLL1P) | max for H533 |
| HCLK / APB1 / APB2 / APB3 | 250 MHz | |
| **I2C1, I2C2, I2C3 kernel clock** | **64 MHz, fixed.** As generated (2026-09-30): **PLL3R** from HSE, 24 MHz ÷ M3 × N16 ÷ R2 = 64.000 MHz. HSI 64 MHz is an acceptable alternative. | a fixed, known clock lets the firmware compute `TIMINGR` for any SCL the PC asks for. PLL3R is crystal-derived (20 ppm), which is more accurate than HSI, so it is the preferred choice. It was only wrong while HSE was set to 25 MHz. |
| USART2 kernel clock | PCLK1 (default) | |

### 4.4 I2C1 — master (Connectivity → I2C1 → Mode: I2C)

| Parameter | Value |
|---|---|
| Pins | PB6 = I2C1_SCL, PB7 = I2C1_SDA (move them there if MX picked PB8/PB9) |
| I2C Speed Mode | Standard Mode |
| I2C Speed Frequency | 100 kHz (the host changes it at run time) |
| Rise / fall time | 300 ns / 30 ns *(estimate, update after measuring)* |
| Analog filter | Enabled |
| Digital filter | 0 |
| Primary address length | 7-bit |
| **Primary slave address** | **0x08** (see check below) |
| Dual address / General call | Disabled / Disabled |
| Clock no-stretch mode | Disabled (i.e. stretching allowed) |
| NVIC | I2C1 event interrupt ✔, I2C1 error interrupt ✔ |

### 4.5 I2C2 — slave 0x6B

| Parameter | Value |
|---|---|
| Pins | **PB10 = I2C2_SCL, PB12 = I2C2_SDA** (MX may default SDA to PB3 or PF0 — change it) |
| Speed settings | same as I2C1 (only used for filter/timing; a slave follows the master's clock) |
| Analog filter / Digital filter | Enabled / 0 |
| Primary address length | 7-bit |
| **Primary slave address** | **0x6B** |
| Dual address / General call | Disabled / Disabled |
| **Clock no-stretch mode** | **Disabled** — stretching is required for case LB-14 |
| NVIC | I2C2 event ✔, I2C2 error ✔ |

### 4.6 I2C3 — slave 0x55

| Parameter | Value |
|---|---|
| Pins | **PA8 = I2C3_SCL, PC9 = I2C3_SDA** |
| Primary slave address | **0x55** |
| Everything else | same as I2C2 |
| NVIC | I2C3 event ✔, I2C3 error ✔ |

### 4.7 GPIO settings for the six I2C pins (System Core → GPIO → I2C tab)

| Setting | Value |
|---|---|
| Mode | Alternate Function **Open Drain** |
| Pull-up/Pull-down | **No pull-up and no pull-down** (external 4.7 kΩ) |
| Maximum output speed | Very High |

### 4.8 USART2 — host link over the ST-LINK VCP

The owner confirmed (2026-09-30) that the VCP is USART2 on PA2/PA3, which is the UM3121 §12.4
factory configuration.

The current `.ioc` gets PA2/PA3 through the **BSP** (*Middleware/BSP → NUCLEO-H533RE → VCP =
true*), not as a USART2 peripheral: there is no USART2 in the IP list, and no `usart.c` was
generated. The BSP COM driver is a blocking `printf` port with no receive interrupt, and the DUT
needs interrupt-driven receive for host commands. Change it:

1. *Middleware → NUCLEO-H533RE (BSP)* → untick **VCP** (keep the rest of BSP_COMMON if you like
   the LED/button helpers).
2. *Connectivity → USART2* → Mode **Asynchronous**, with the settings below.

| Parameter | Value |
|---|---|
| Mode | Asynchronous |
| Pins | PA2 = USART2_TX, PA3 = USART2_RX (AF7) |
| Baud / format | 115200, 8-N-1, no flow control |
| NVIC | USART2 global interrupt ✔ |

### 4.9 Timer for µs timestamps

| Parameter | Value |
|---|---|
| TIM2 | Clock source: Internal clock |
| Prescaler | 249 (250 MHz / 250 = 1 MHz → 1 µs tick) |
| Counter period | 0xFFFFFFFF (32-bit, free running) |
| NVIC | not needed |

### 4.10 Project Manager tab

| Item | Setting |
|---|---|
| Project name | `firmware` (fixed once saved; fine as is) |
| Project location | `…/ion_i2c_tool/loopback_dut/` (the project folder is `loopback_dut/firmware/`) |
| Toolchain / IDE | **Makefile** (confirmed in `firmware.ioc`: `TargetToolchain=Makefile`) |
| Code generator → STM32Cube MCU packages | "Copy only the necessary library files" |
| Code generator → Generated files | ✔ "Generate peripheral initialization as a pair of .c/.h files per peripheral" |
| Code generator → ✔ "Keep User Code when re-generating" | on |
| Advanced settings → driver | **HAL** for I2C1/2/3 and USART2 (the slave sequential/listen callbacks are HAL) |

### 4.11 After "Generate Code": check the generated addresses

HAL stores the 7-bit address **shifted left by one** in `OwnAddress1`. MX takes the 7-bit value
you type and writes the shifted value. Confirm in the generated `i2c.c` (or `main.c`):

```bash
grep -n "OwnAddress1" <project>/Core/Src/*.c
```

Expected:

```
hi2c1.Init.OwnAddress1 = 16;     # 0x10 = 0x08 << 1
hi2c2.Init.OwnAddress1 = 214;    # 0xD6 = 0x6B << 1
hi2c3.Init.OwnAddress1 = 170;    # 0xAA = 0x55 << 1
```

If you see 8 / 107 / 85, MX treated your entry as already shifted. Re-enter the addresses so the
generated values are the shifted ones.

---

## 5. SCL frequency: DUT sets it, C031 sniffer reports it

- **DUT side:** the PC script sends a "set speed" command. The DUT recomputes I2C1 `TIMINGR`
  from the fixed 64 MHz HSI kernel clock (§4.3) and uses it for every following case. The
  requested value is written into `expected.json` for each case.
- **Sniffer side (C031): implemented 2026-09-30, firmware 1.3, project 1.4.0.** Bit-bang mode
  measures each transaction's SCL (the mean of the un-stretched rise-to-rise periods; clock
  stretch is excluded) and sends it in every TXN frame (`embedded/docs/PROTOCOL.md` §1.1.1).
  The sniffer and replay tables show it in an **SCL** column (kHz), and the capture CSV
  carries it as `SCL (Hz)` (capture CSV v2, `documents/CSV_FORMAT.md`). The comparison
  harness checks the measured value against the value the DUT set for each case.
- Simulated accuracy (1 µs timestamps): ±0.5 % at 100 kHz, ±2 % at 400 kHz. **Not yet
  measured on hardware**; LB-13 (400 kHz) and LB-14 (stretch) are the hardware checks.
- **Reflash the C031** with the rebuilt `embedded/sniffer_nucleoC0_fw/build/sniffer_nucleoC0_fw.bin`
  (fw 1.3). HELLO / the status bar should then report firmware `1.3`.
- **Range:** 10 kHz – 400 kHz supported. 1 MHz (Fm+) is out of scope on this rig, because
  PB12 is not an Fm+ pin and 4.7 kΩ pull-ups are too slow for it.

---

## 6. Command-line checks — run these before the first session with hardware

Run from the project root:

```bash
cd ~/Documents/GitHub/advanced_engineering/tools/scripts/ion_i2c_tool
```

Each check lists the **expected result**. Paste the output back to me if anything differs.

### 6.1 Python environment (needed for the baseline test run)

The tests must run inside the project `.venv`. macOS `/usr/bin/python3` is 3.9 and cannot run
parts of the suite (see §7). The `.venv` already exists on this Mac (Python 3.12.13); it just
has to be activated.

```bash
source .venv/bin/activate                          # (only if .venv is missing: ./install.sh)
.venv/bin/python --version                         # expect: Python 3.12.x (or 3.10+)
.venv/bin/python -c "import PySide6, serial, jsonschema; print('PySide6', PySide6.__version__, '| pyserial', serial.__version__, '| jsonschema ok')"
```

Expected: a Python version of 3.10 or later, and one line naming PySide6 6.6+, pyserial 3.5+
and jsonschema.

> Note: `install.sh` also rewrites `run.sh` (identical content) and copies `dwfconstants.py`
> from WaveForms into the project if it finds it.

### 6.2 Embedded toolchain

**Measured on the owner's Mac, 2026-09-30:** Python 3.12.13 (`.venv`), `arm-none-eabi-gcc`
15.2.Rel1 (Build arm-15.86), GNU Make 3.81, STM32CubeProgrammer v2.22.0,
STM32Cube_FW_C0 V1.4.0 and V1.4.1. **FW_H5 not yet installed** (§4.0).

```bash
arm-none-eabi-gcc --version | head -1              # expect: Arm GNU Toolchain 13.x or newer (this Mac: 15.2.Rel1)
make --version | head -1                            # expect: GNU Make 3.81+
cmake --version 2>/dev/null | head -1 || echo "cmake: not installed (only needed if MX generates CMake)"
ls ~/STM32Cube/Repository | grep -E "STM32Cube_FW_(C0|H5)"
```

Expected: the last command lists both a `STM32Cube_FW_C0_V1.4.x` and a
`STM32Cube_FW_H5_V1.x.x` folder. The H5 folder appears after CubeMX downloads the H5 package
the first time you generate code.

### 6.3 Flash tool

```bash
CLI=$(ls /Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI \
         /Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/*cubeprogrammer*/tools/bin/STM32_Programmer_CLI 2>/dev/null | head -1)
echo "CLI=${CLI:-NOT FOUND}"
[ -n "$CLI" ] && "$CLI" --version | head -3
```

Expected: a path, then `STM32CubeProgrammer version: 2.x`. If it is NOT FOUND, run the
installer that is sitting in `/Applications` (`SetupSTM32CubeProgrammer-2.23.0.app`), or rely on
drag-and-drop flashing to the `NOD_H533RE` mass-storage volume.

### 6.4 USB: all three instruments enumerate

Plug in all three boards, then:

```bash
.venv/bin/python -m serial.tools.list_ports -v
ls /dev/cu.usbmodem* 2>/dev/null
system_profiler SPUSBDataType 2>/dev/null | grep -E -A6 "STLINK|ST-LINK|Digilent|Analog Discovery" | grep -E "STLINK|ST-LINK|Digilent|Discovery|Product ID|Serial Number"
```

Expected:
- **Two** `/dev/cu.usbmodem…` ports: one for the H533 (ST-LINK **V3**, VID 0483, PID typically
  `3754`) and one for the C031 (ST-LINK **V2-1**, VID 0483, PID `374B`).
- One Digilent device (VID `1443`). The AD2 is not a serial port, so it does not appear in the
  first list.
- **Write down which `usbmodem` serial number is which board.** Every later command names the
  port explicitly.

*(The PIDs are the usual ST-LINK values, not measured on these units. Record what you see.)*

### 6.5 Mass-storage volumes (drag-and-drop flashing path)

```bash
ls /Volumes | grep -E "NOD_|NUCLEO"
```

Expected: `NOD_H533RE` and `NOD_C031C6` (exact names *to confirm*).

### 6.6 AD2 / WaveForms

```bash
ls /Library/Frameworks/dwf.framework/dwf && echo "DWF framework OK"
ls dwfconstants.py && echo "dwfconstants.py present in project"
```

Expected: both lines print OK. Close the WaveForms GUI before running `sniffer_ad2.py`, because
only one program can own the AD2 at a time.

### 6.7 C031 sniffer firmware builds from a clean tree (dry run; changes nothing)

```bash
make -C embedded/sniffer_nucleoC0_fw -n | tail -5
```

Expected: no `No rule to make target` errors. If `build/` is already up to date (as on this Mac,
2026-09-30), the only line printed is `arm-none-eabi-size build/sniffer_nucleoC0_fw.elf`.
Otherwise you see `arm-none-eabi-gcc` / `objcopy` lines. A real build comes later in the session.

### 6.8 Bus idle levels (multimeter, all boards powered, no firmware running traffic)

| Probe point | Expected |
|---|---|
| SCL to GND | 3.3 V ± 0.1 V |
| SDA to GND | 3.3 V ± 0.1 V |

If either line reads near 0 V, one board is holding the line low: unplug the boards one at a
time until it rises. A pin left in push-pull output mode is the usual cause.

---

## 7. Known environment issues (found 2026-09-30)

| Issue | Evidence | Resolution |
|---|---|---|
| `.venv` exists (Python 3.12.13) but was not activated, so tests ran on macOS Python 3.9.6 | `python3 --version` → 3.9.6; `test_ion_master.py` fails with `TypeError: unsupported operand type(s) for \|: 'type' and 'NoneType'` (PEP 604 syntax needs 3.10+) | `source .venv/bin/activate` (§6.1) |
| `jsonschema` not installed | `test_bq25731_decoder.py`, `test_bq76922_decoder.py`: `ModuleNotFoundError: No module named 'jsonschema'` | installed by `install.sh` from `requirements.txt` |
| `test_neware_doc_conformance.py` looked in `tests/` for its inputs | `FileNotFoundError` for `tests/Smart_Battery_Registers.txt` | **Fixed 2026-09-30** (test v1.1): reads `documents/decoders/Smart Battery Registers.txt`, `i2c_decoders/neware_decoder.json` and `i2c_decoders/smbus1v1_decoder.json`; 0 failures |
| 17 `test_*.py` files, not 16 as the plan expects | `ls tests/test_*.py` | record in the baseline; `test_neware_doc_conformance.py` is the extra one |

---

## 8. Open points for the owner

| # | Question | Blocks |
|---|---|---|
| A | ~~0x08 handling~~ **Closed:** 0x08 is the address-NAK case; all addresses configurable via `config/rig.toml` (owner, 2026-09-30) | — |
| B | ~~CubeMX project path and toolchain~~ **Closed:** `loopback_dut/firmware/`, Makefile | — |
| C | ~~VCP solder bridges~~ **Closed:** USART2 on PA2/PA3 (owner, 2026-09-30) | — |
| E | Regenerate after installing FW_H5 1.7.0 and making the §4.2/§4.3/§4.8 fixes | DUT firmware task P1-T2 |
| D | ~~Missing Neware reference~~ **Closed:** it is `documents/decoders/Smart Battery Registers.txt`; the test was repointed (owner, 2026-09-30) | — |

---

## 9. DUT firmware: build, flash, first bench check (P1-T2 evidence)

### 9.1 Build

```bash
cd ~/Documents/GitHub/advanced_engineering/tools/scripts/ion_i2c_tool/loopback_dut/firmware
make -j8            # uses GNUmakefile -> includes the CubeMX Makefile + App/
```

Expected: no warnings, and a size line close to
`39316  112  5064  44492  adcc  build/firmware.elf` (2026-09-30). Outputs are
`build/firmware.elf/.hex/.bin`. **Always run `make` in this folder, never `make -f Makefile`**:
the CubeMX Makefile alone does not know about `App/` and fails to link.

Host unit tests (no hardware):

```bash
make -C ../tests/host test                                   # expect: ALL LOOPBACK DUT HOST TESTS PASSED
../../.venv/bin/python ../tests/test_pattern_schema.py       # expect: ALL TESTS PASSED
```

### 9.2 Flash

Use either method:

```bash
# (a) CubeProgrammer CLI over the on-board ST-LINK V3 (SWD); not on PATH on this Mac,
#     so use the $CLI path found in §6.3
"$CLI" -c port=SWD -w build/firmware.bin 0x08000000 -v -rst
# (b) drag and drop: copy build/firmware.bin onto the NOD_H533RE volume
cp build/firmware.bin /Volumes/NOD_H533RE/
```

Expected: (a) ends with `File download complete` and `Download verified successfully`; with
(b) the volume disappears and remounts. **LD2 then blinks at 1 Hz** (toggles every 500 ms).

### 9.3 First contact, bus not needed

Use miniterm from the project `.venv` with **LF** line endings. The DUT ignores CR and needs LF,
which `screen` does not send.

```bash
../../.venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodemXXXX 115200 --eol LF
```

Press the black RESET button (B2), then type `PING` and `STATUS`. Expected:

```
HELLO LBDUT proto=1 fw=0.2 kernel=64000000 *AD
```

(DUT fw 0.1 answered `…fw=0.1… *BF`.)

and a `STATUS … hz=100000 pred=100075 r1=6B:1 r2=55:1 …` line.

### 9.4 Bus checks: LB-01, LB-03, LB-05, LB-09 (the P1-T2 passing criteria)

With the bus wired and pulled up (§3), type each command and compare the reply exactly
(the CRC suffixes are computed values, so they must match as well):

| Command | Expected reply lines |
|---|---|
| `RUN 1 WR 6B 2 02` (LB-01) | `PH 1 0 0 S 6B W A - 1 02 *12`<br>`PH 1 0 1 SR 6B R A P 2 02 A0 *CB`<br>`END 1 0 OK t=… dur=… *…` |
| `RUN 2 W 6B 10 34 12` (LB-03) | `PH 2 0 0 S 6B W A P 3 10 34 12 *48` then `END 2 0 OK …` |
| `RUN 3 W 08 00` (LB-05) | `PH 3 0 0 S 08 W NA P 0 *FD` then `END 3 0 NAK …` |
| `RUN 4 W 6B 3E 01 00` then `RUN 5 WR 6B 36 3E` (LB-09) | `PH 4 0 0 S 6B W A P 3 3E 01 00 *84`, `END 4 …`, then `PH 5 0 0 S 6B W A - 1 3E *76` and the 36-byte read below |

LB-09 read line (echo 01 00, buffer (0x40+i) XOR 0x01, checksum 0E, length 24h = 36):

```
PH 5 0 1 SR 6B R A P 36 01 00 41 40 43 42 45 44 47 46 49 48 4B 4A 4D 4C 4F 4E 51 50 53 52 55 54 57 56 59 58 5B 5A 5D 5C 5F 5E 0E 24 *DB
```

Paste the actual output into `REVIEW_PHASE_01.md` §4 as evidence.

If a reply differs:

| Symptom | Likely cause |
|---|---|
| No HELLO, LD2 dark | not flashed / wrong port / board not reset |
| `ERR - 1 SYNTAX` on everything | terminal sends CR only (use `--eol LF`) |
| `NA` from 6B / 55 | responder pin not wired to the bus (I2C2 SDA is **PB12 on morpho CN10-16**, not the Arduino header) |
| `ER` or no `END` | bus stuck low / no pull-ups: measure SCL/SDA idle = 3.3 V (§6.8) |
| read bytes all `FF` | SDA not reaching the master (PB7 / D14) |

---

## 10. Full loopback run with both sniffers (P1-T3/T4 evidence)

Do this after §9 passes. The paths below are from the project root
(`…/ion_i2c_tool`), with `source .venv/bin/activate` done.

1. **No-hardware self-checks first:**
   ```bash
   python loopback_dut/tests/test_pattern_schema.py    # ALL TESTS PASSED
   python loopback_dut/tests/test_host_model.py        # ALL TESTS PASSED
   python loopback_dut/tests/test_loopback_harness.py  # ALL TESTS PASSED
   python loopback_dut/host/loopback_run.py --list     # 15 cases
   ```
2. **Sniffer 1 (ion / C031, fw 1.3):** `./run.sh sniffer_ion.py`. In the app:
   - load decoder `i2c_decoders/loopback_dut_decoder.json` and **no other decoder on 0x6B**
     (bq25731 shares it, review B19);
   - tick **Validate SMBus PEC** (LB-07/LB-08 need it);
   - clear every filter;
   - **Start Sniffing**.
3. **Sniffer 2 (AD2):** `./run.sh sniffer_ad2.py`, with SCL on DIO 0 and SDA on DIO 1. Make
   the same decoder, PEC and no-filter settings, then start the spy.
4. **Emit the pattern** (fill `[ports] dut` in `config/rig.toml` or pass `--port`):
   ```bash
   python loopback_dut/host/loopback_run.py --port /dev/cu.usbmodemXXXX \
          --out loopback_dut/runs/expected.json --transcript loopback_dut/runs/transcript.txt
   ```
   Expected: one line per case, `LB-xx ok … phases 100000 Hz (pred 100075)` (LB-13 at 400000,
   pred 401204). `model_mismatch` means the DUT did not do what the host model predicts: a DUT
   or wiring problem. Stop and check §9.4. `DESYNC in case LB-xx` (exit 2) means a reply arrived
   with the wrong sequence number. Keep the transcript; it is evidence.
5. **Stop both sniffers and export CSV** with all rows visible (Export writes only the visible
   rows, review B14) to `loopback_dut/runs/ion_capture.csv` and `loopback_dut/runs/ad2_capture.csv`.
6. **Compare:**
   ```bash
   python loopback_dut/tests/test_loopback_capture.py
   ```
   It writes `loopback_dut/runs/loopback_report_ion.md` and `…_ad2.md`. Read the verdict column:
   - `pass`: the sniffer captured exactly what the DUT emitted;
   - `xfail`: it failed in exactly the way the ledger records (B8/B9/B10/B13);
   - `fail`: an unexplained failure. That is a new finding: give it a review ID (B30…);
   - `xpass`: a recorded bug did not show. The ledger is stale, so investigate before
     celebrating;
   - `not_exercisable`: a required capture setting was missing (the decoder or PEC validation).
     Fix the setup and re-capture.

   The report's per-case sections list byte-level diffs. Paste both reports into
   `REVIEW_PHASE_01.md`.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-09-30 | First version: topology, wiring, CubeMX settings, command-line checks, environment findings |
| v0.2 | 2026-09-30 | Audited against the saved `firmware.ioc` (MX 6.18.0, FW_H5 1.7.0): HSE 25→24 MHz and PLL1 6/125/2; I2C kernel clock PLL3R→HSI; Debug→Serial Wire; USART2 as a peripheral in place of BSP VCP; ICACHE/DCACHE1 note; FW_H5 package missing (§4.0); project name/location/toolchain closed; `.venv` exists (activate only); measured tool versions recorded |
| v0.3 | 2026-09-30 | 0x08 is the address-NAK case; shared `config/rig.toml` for addresses and speed; open points A and D closed; Neware test fixed |
| v0.4 | 2026-09-30 | §5: C031 SCL measurement implemented (fw 1.3, CSV v2 `SCL (Hz)`), accuracy and reflash note |
| v0.5 | 2026-09-30 | §4.0 marked done (project generated and building); §4.3 I2C kernel clock PLL3R 64 MHz from HSE accepted (preferred over HSI) |
| v0.6 | 2026-09-30 | §9: DUT firmware build, flash, first contact and bus checks with exact expected lines (LB-01/03/05/09) |
| v0.7 | 2026-09-30 | §10: full loopback run with both sniffers, compare and how to read the verdicts |
| v0.8 | 2026-10-02 | §9.3 expected HELLO for DUT fw 0.2 |
| v0.9 | 2026-10-05 | §6.3 CLI path fixed (`Contents/Resources/bin`, CubeProgrammer 2.23.0 measured); build and flash for both images now also in `embedded/docs/build_and_flash.md` |
