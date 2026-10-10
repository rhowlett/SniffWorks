# Build and flash — both firmware images
<!-- v0.1 -->

This project has two firmware images. Both build with GNU make and the Arm GNU toolchain, and
both flash through the ST-LINK built into each Nucleo board. You need no other probe.

| Image | Board | Source | Role |
|---|---|---|---|
| **ion sniffer** (`sniffer_nucleoC0_fw`) | NUCLEO-C031C6 | `embedded/sniffer_nucleoC0_fw/` | the passive I2C sniffer under test (`sniffer_ion.py`) |
| **loopback DUT** (`loopback_dut_fw`) | NUCLEO-H533RE | `loopback_dut/firmware/` | the I2C traffic generator / ground truth (`loopback_dut/host/loopback_run.py`) |

Values marked **(measured on this unit)** were measured on the owner's Mac and rig on
2026-10-05. Check them on yours. Everything else is from the source or the vendor docs.

---

## 1. Toolchain

| Tool | Version (measured on this unit) | Needed for | Check |
|---|---|---|---|
| Arm GNU Toolchain `arm-none-eabi-gcc` | 15.2.Rel1 (Build arm-15.86) | both builds | `arm-none-eabi-gcc --version \| head -1` |
| GNU make | 3.81 (macOS stock) | both builds | `make --version \| head -1` |
| STM32CubeProgrammer | 2.23.0 | CLI flashing (optional) | see §4.2 |
| STM32CubeMX | 6.18.0 | only to regenerate the DUT project | — |
| STM32CubeIDE | installed | optional IDE path (§3.4) | — |
| Python `.venv` | 3.12.13 | host tools and tests | `source .venv/bin/activate; python -V` |

Any Arm GNU toolchain from 13.x on should work. The firmware uses only C11 and the vendor
LL/HAL drivers, which are vendored in the tree, so you do not need a STM32Cube firmware package
to build. CubeMX needs the FW_H5 package only when you **regenerate** the DUT project
(`loopback_dut/docs/setup_guide.md` §4.0).

**macOS quirks:**
- **CubeProgrammer CLI path.** `STM32_Programmer_CLI` is not on `PATH`. Its path on this Mac
  is:
  `/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI`.
  A second copy ships inside STM32CubeIDE.app (`…/plugins/…cubeprogrammer.macosaarch64…/tools/bin/`).
- **Old guide path.** `loopback_dut/docs/setup_guide.md` §6.3 probed `Contents/MacOs/bin`,
  which does not exist; the correct folder is `Contents/Resources/bin`.
- **No `timeout` command.** macOS has none, so do not wrap commands in it.
- **zsh globs.** zsh aborts a command when a glob matches nothing (`ls /dev/cu.usbmodem*` with
  no board plugged in). Use `ls /dev/cu.usbmodem* 2>/dev/null`.

---

## 2. Hardware for flashing

| Board | On-board probe | USB | Mass-storage volume | VCP |
|---|---|---|---|---|
| NUCLEO-C031C6 | ST-LINK V2-1 | micro-USB | `NOD_C031C6` | USART2 PA2/PA3, 115200 8N1 |
| NUCLEO-H533RE | ST-LINK V3EC | USB-C | `NOD_H533RE` | USART2 PA2/PA3, 115200 8N1 |

Each board is powered from its own USB cable. You need no jumper changes from the factory
default.

ST-LINK serial numbers **(measured on this unit)**: H533 `003200273234511437333934`, C031
`066BFF544884654867102556`. Port names such as `/dev/cu.usbmodem1203` change when you plug into
another USB socket, so identify the boards by serial number (§5).

---

## 3. Build

Run every command from the project root (`…/ion_i2c_tool`) unless stated otherwise.

### 3.1 ion sniffer (C031)

```bash
make -C embedded/sniffer_nucleoC0_fw -j8
```

**Expected:** no warnings, then the size line, which should be **identical** to:

```
   text	   data	    bss	    dec	    hex	filename
   5796	      4	   9892	  15692	   3d4c	build/sniffer_nucleoC0_fw.elf
```

The outputs are `embedded/sniffer_nucleoC0_fw/build/sniffer_nucleoC0_fw.{elf,hex,bin}`.

- **The `build/` folder is tracked in git** and holds the shipped default image. A clean-tree
  build reproduces it byte for byte (`cmp` showed no difference, 2026-10-05).
- **Build variants go to a scratch folder**, so the shipped image stays untouched:

```bash
make -C embedded/sniffer_nucleoC0_fw BUILD_DIR=/tmp/fw_variant EXTRA_DEFS='-DSNIFF_TRACE=2'
```

Firmware switches (`Core/Inc/sniffer_config.h`; the default is in **bold**):

| Switch | Values | Effect |
|---|---|---|
| `SNIFF_MODE` | **`SNIFF_MODE_BITBANG`**, `SNIFF_MODE_SLAVE_MON`, `SNIFF_MODE_MASTER` | sniffing method / master tool |
| `SNIFF_EDGE_IRQ` | **1**, 0 | fw 1.6 edge-interrupt sampling; 0 = the old polled loop |
| `SNIFF_FLASH_ACCEL` | **1**, 0 | flash prefetch + instruction cache |
| `SNIFF_TRACE` | **0**, 1, 2 | logic-analyser trace pins PA1 (busy) / PA0 (ISR or loop) |
| `SNIFF_DIAG`, `SNIFF_DEFER_UPKEEP` | **0** | fw 1.4 instrumentation; polled mode only (they broke 100 kHz capture) |
| `HOST_UART_BAUD` | **115200** | must match the app's Device tab → Serial |
| `STATUS_PERIOD_US` | **1000000** | unsolicited STATUS period while capturing |

Prebuilt variants (`embedded/sniffer_nucleoC0_fw/build_variants/`):

| Folder | Image |
|---|---|
| `fw16_trace/` | `SNIFF_TRACE=2` |
| `fw16_polled/` | the fw 1.5-equivalent polled loop (`SNIFF_EDGE_IRQ=0`) |

Host unit tests, no hardware needed (they compile the same C files on the Mac):

```bash
make -C embedded/tests/host test
```

**Expected:** `=== 86 checks, 0 failures ===`, `=== 92 checks, 0 failures ===`,
`=== 22 checks, 0 failures ===`, then `ALL HOST TESTS PASSED`.

### 3.2 loopback DUT (H533)

```bash
cd loopback_dut/firmware && make -j8 && cd -
```

**Expected:** no warnings. The last lines are the `objcopy` steps, and
`arm-none-eabi-size build/firmware.elf` prints
`39324  112  5064  44500  add4  build/firmware.elf` **(measured on this unit, DUT fw 0.2)**.
The outputs are `loopback_dut/firmware/build/firmware.{elf,hex,bin}`.

- **Use the plain `make`.** It picks up `GNUmakefile`, which includes the CubeMX `Makefile`
  and adds `App/`.
- **Never run `make -f Makefile`.** Without `App/` the link fails with
  `undefined reference to dut_app_init`.
- **Clean-tree check.** A build from a clean tree is byte-identical to the image in
  `build/` (2026-10-05).

Host unit tests:

```bash
make -C loopback_dut/tests/host test     # expect: ALL LOOPBACK DUT HOST TESTS PASSED
```

### 3.3 Regenerating the DUT project (only after a `.ioc` change)

Open `loopback_dut/firmware/firmware.ioc` in STM32CubeMX and click **Generate Code**. Hand-written
code lives only in `App/` and in the `USER CODE` regions of `Core/Src/main.c`, so it survives.
The settings and the checks to run after generating are in `loopback_dut/docs/setup_guide.md`
§4 and §4.11.

### 3.4 STM32CubeIDE (optional)

`embedded/sniffer_nucleoC0_fw/sniffer_nucleoC0_fw.launch` is a CubeIDE debug configuration. The
Makefile is written to match the CubeIDE project's sources, defines and flags. To debug in the
IDE, create a *Makefile project with existing code* on `embedded/sniffer_nucleoC0_fw/` and use
the launch file. The make build above remains the reference build.

---

## 4. Flash

Use either method on either board.

### 4.1 Drag and drop (simplest)

```bash
cp embedded/sniffer_nucleoC0_fw/build/sniffer_nucleoC0_fw.bin /Volumes/NOD_C031C6/
cp loopback_dut/firmware/build/firmware.bin                  /Volumes/NOD_H533RE/
```

**Expected:**
- the volume disappears and remounts within ~8 s;
- no `FAIL.TXT` appears on the volume;
- the board then runs the new image.

### 4.2 CubeProgrammer CLI (SWD through the on-board ST-LINK)

```bash
CLI=/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI
"$CLI" -l st-link                          # lists both probes with board name + serial
"$CLI" -c port=SWD sn=066BFF544884654867102556 -w embedded/sniffer_nucleoC0_fw/build/sniffer_nucleoC0_fw.bin 0x08000000 -v -rst
"$CLI" -c port=SWD sn=003200273234511437333934 -w loopback_dut/firmware/build/firmware.bin 0x08000000 -v -rst
```

**Expected:**
- `-l` prints `Board Name : NUCLEO-H533RE` and `Board Name : NUCLEO-C031C6` with their serial
  numbers;
- each flash ends with `Download verified successfully`.

Use `sn=` whenever both boards are plugged in; otherwise the CLI picks the first probe.

---

## 5. Power-up ritual and first contact

1. **Plug in the boards** (any order) and find the serial ports:
   ```bash
   ls /dev/cu.usbmodem* 2>/dev/null
   .venv/bin/python -m serial.tools.list_ports -v      # shows the ST-LINK serial numbers
   ```
   **Expected:** two `usbmodem` ports. Match them to the boards by `SER=` (§2).
2. **ion sniffer:**
   ```bash
   python tools/ion_capture.py --port /dev/cu.usbmodemXXXX --seconds 1 --status-only
   ```
   **Expected:**
   - `probe: fw 1.6, mode bit-bang`;
   - a `STATUS: fw 1.6 …` line.

   **If it reports no HELLO:** press the C031's black **RESET** button (B2) once and retry.
   After a drag-and-drop flash the board sometimes needs this (owner, 2026-10-05). Another
   program holding the port has the same symptom: close `sniffer_ion.py` first.
3. **loopback DUT:** LD2 blinks at 1 Hz.
   ```bash
   .venv/bin/python -m serial.tools.miniterm /dev/cu.usbmodemYYYY 115200 --eol LF
   ```
   Type `PING`. **Expected:** `HELLO LBDUT proto=1 fw=0.2 kernel=64000000 *AD`. The DUT needs
   LF line endings; `screen` sends only CR and gets `ERR … SYNTAX`.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `make: arm-none-eabi-gcc: No such file or directory` | toolchain not on PATH: install the Arm GNU Toolchain and add its `bin/` |
| DUT link: `undefined reference to dut_app_init` | built with `make -f Makefile`; run plain `make` in `loopback_dut/firmware` |
| DUT link: `cannot find build/dut_*.o` | the GNUmakefile's explicit `DUT_OBJECTS` prerequisites were removed; restore them |
| `FAIL.TXT` on the `NOD_…` volume | wrong .bin for the board, or a truncated copy; copy again |
| C031: no HELLO after flashing | press RESET (B2); close any other program using the port |
| C031 fw 1.4 only: commands answered with `ERROR 2/0xFF`, capture cannot be stopped | known fw 1.4 defect (RX overrun); flash fw ≥ 1.5. To stop a stuck 1.4 probe, press RESET |
| CLI: `No ST-Link detected` | cable is charge-only, or another tool (CubeIDE debugger) owns the probe |
| Two probes, CLI flashed the wrong board | add `sn=<serial>` to `-c` |

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-10-05 | First version (P1-T6): both images, toolchain, build/variant/test commands with measured expected output, drag-and-drop and CLI flashing by serial number, power-up ritual, troubleshooting |
