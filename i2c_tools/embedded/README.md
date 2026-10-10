# NUCLEO-C031C6 I2C Sniffer — Firmware

Passive I2C/SMBus sniffer firmware for the ST **NUCLEO-C031C6** board
(STM32C031C6, Cortex-M0+ @ 48 MHz, 32 KB flash / 12 KB RAM), replacing the
Analog Discovery 2 in the `ion_i2c_tool` application.

Built on **STM32 LL drivers only** — no HAL, no interrupts, no RTOS.
Flash footprint ≈ 4 KB.

```
embedded/
├── sniffer_nucleoC0_fw/      STM32CubeIDE project (also builds with make)
│   ├── .project / .cproject  Import into CubeIDE (no .ioc on purpose — see below)
│   ├── Core/Inc/sniffer_config.h   <-- ALL user options live here
│   ├── Core/{Inc,Src,Startup}/     firmware sources
│   ├── Drivers/                    LL driver + CMSIS subset (self-contained)
│   ├── STM32C031C6TX_FLASH.ld
│   └── Makefile
├── tests/host/               host-compiled unit tests (gcc, no hardware)
└── docs/PROTOCOL.md          serial wire protocol (host app contract)
```

---

## 1. Wiring

Per the official board manual (UM2953 Rev 2), on the Arduino headers:

| Signal | MCU pin | Arduino socket | Connector |
|--------|---------|----------------|-----------|
| SCL    | PA9     | **D8**         | CN5 pin 1 |
| SDA    | PA10    | **D2**         | CN9 pin 3 |
| GND    | —       | GND            | any       |

> Note: D3 is **PB3** on this board — if SCL was previously on D3, move it to
> D8. The board's silkscreened I2C pins (D14/D15) are PB9/PB8 and are *not*
> used by this firmware.

Tap the wires in parallel with the existing bus; the sniffer (in the default
bit-bang mode) never drives or loads the lines beyond a CMOS input.

USB: the same Micro-B cable that powers/flashes the board carries the
sniffer's serial stream (ST-LINK Virtual COM port).

---

## 2. Capture modes (`SNIFF_MODE` in `sniffer_config.h`)

| | `SNIFF_MODE_BITBANG` *(default)* | `SNIFF_MODE_SLAVE_MON` |
|---|---|---|
| Method | GPIO sampling, tight polling loop | I2C1 peripheral, slave match-all |
| Write data | ✔ captured | ✔ captured |
| Read data | ✔ captured | ✘ address + direction only |
| NAK visibility | ✔ true bus NAKs | partial (peripheral ACKs matched addresses) |
| Bus intrusion | none | mild (hardware ACK) |
| 100 kHz | ✔ guaranteed | ✔ |
| 400 kHz | best-effort (see PROTOCOL.md §3.1) | ✔ for writes |

Bus speed needs **no configuration** in bit-bang mode — the decoder is
edge-driven and the measured bus clock is reported in STATUS frames
(the "Auto" feature).

Switch modes without editing files:

```bash
make EXTRA_DEFS='-DSNIFF_MODE=SNIFF_MODE_SLAVE_MON'
```

Raise the UART baud (for heavy bus traffic):

```bash
make EXTRA_DEFS='-DHOST_UART_BAUD=921600'
```

---

## 3. Building

### Option A — STM32CubeIDE (matches your existing workflow)

1. *File ▸ Import… ▸ General ▸ Existing Projects into Workspace*.
2. Select `embedded/sniffer_nucleoC0_fw` (check "Copy projects into
   workspace" if you prefer isolation).
3. Build (hammer icon), then *Run ▸ Debug As ▸ STM32 C/C++ Application* —
   the included `sniffer_nucleoC0_fw.launch` is preconfigured for the
   on-board ST-LINK.

There is intentionally **no `.ioc` file**: the project is pure hand-written
LL code, and a CubeMX regeneration pass would overwrite it. Pin/clock changes
are made in `sniffer_config.h` and `main.c`, not in CubeMX.

### Option B — command line

```bash
cd embedded/sniffer_nucleoC0_fw
make              # -> build/sniffer_nucleoC0_fw.{elf,hex,bin}
```

Flash with any of:

```bash
# STM32CubeProgrammer CLI
STM32_Programmer_CLI -c port=SWD -w build/sniffer_nucleoC0_fw.hex -v -rst

# or simply copy the .bin to the NUCLEO mass-storage drive
cp build/sniffer_nucleoC0_fw.bin /media/$USER/NOD_C031C6/
```

---

## 4. Smoke test (before the Phase 3 GUI exists)

A ready-made terminal sanity check lives in `tools/`:

```bash
pip install pyserial
python3 tools/nucleo_sniffer_check.py                # auto-detects the ST-LINK VCP
python3 tools/nucleo_sniffer_check.py --seconds 10   # timed capture, auto-stop
python3 tools/nucleo_sniffer_check.py /dev/cu.usbmodemXXXX --baud 921600
```

It PINGs the board, verifies the HELLO handshake, starts a capture, and
pretty-prints every transaction live:

```
  txn     1      1.234567s  0x08  W  S   P  ack  [ 3]  3E 01 02
  txn     2      1.240000s  0x08  R  rS  P  NAK  [ 2]  69 77
  -- status: CAPTURING, captured=2, errors=0, dropped=0, bus≈100 kHz
```

Ctrl+C (or `--seconds`) stops the capture and prints a summary with the
device counters, link CRC errors, and the measured bus clock. Exit code 0
means the link and firmware behaved. On macOS the port looks like
`/dev/cu.usbmodem...`; close any other program holding the VCP first
(CubeIDE serial console, `screen`, etc.).

Manual bytes, if you'd rather poke it yourself: LD4 blinks at 2 Hz when
idle; boot HELLO is `AA 04 08 00 4E 43 30 53 01 01 00 01 BB`; START is
`A5 01 00 15`; STOP is `A5 02 00 2A` (CRCs are SMBus CRC-8).

## 5. Host-side unit tests

The decoder and protocol modules are pure C (no register access) and are
compiled and tested on the PC — the exact same files the firmware links:

```bash
cd embedded/tests/host
make test
```

100 checks cover: write/read/restart decoding, address NAK, quick command,
overflow clamping, back-to-back streams, bus-clock estimation, change-gated
sampling (mirroring the firmware's IDR gate), CRC-8 known-answer vectors,
frame round-trips, and command-parser resync. Tests run under
AddressSanitizer/UBSan.

---

## 6. Design notes

* **Zero interrupts.** Everything (capture, DMA pump, command parsing,
  status, LED) runs in one superloop so the sampler never suffers ISR
  jitter. UART TX is DMA-driven from a 6 KB ring buffer; overflow drops
  whole frames and reports the count in STATUS rather than corrupting the
  stream.
* **Transaction model** mirrors the Python `I2CTransaction` dataclass
  one-to-one (repeated START closes a record with `stop=0` and opens the
  next with `restart=1`), so the Phase 3 backend maps frames straight into
  the existing GUI pipeline.
* **PEC** stays host-side, same as the AD2 flow — the raw bytes are all in
  the TXN frame.
