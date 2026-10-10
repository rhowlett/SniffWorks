# Loopback DUT — Line Protocol and Register Map
<!-- v0.2 -->

Normative for `loopback_dut/firmware/App` (DUT firmware 0.1, protocol 1) and the host software
in `loopback_dut/host/`. Parser and formatter: `App/Src/dut_proto.c`; register map:
`App/Src/dut_regmap.c`; TIMINGR: `App/Src/dut_timing.c`. All three are unit-tested on the host
(`loopback_dut/tests/host`, `make test`).

This protocol is **unrelated** to the sniffer probe protocol (`embedded/docs/PROTOCOL.md`).
The DUT is an isolated instrument.

---

## 1. Transport

- NUCLEO-H533RE ST-LINK V3EC virtual COM port = USART2 (PA2/PA3), **115200 8-N-1**, no flow
  control.
- ASCII lines ending in `\n`; `\r` is ignored. Maximum 600 characters per host line.
- **DUT → host:** every line ends with ` *CC`, where `CC` is the CRC-8/SMBUS (poly 0x07, init 0)
  of every character before ` *`, in upper-case hex. A host must drop a line whose CRC fails.
- **Host → DUT:** the ` *CC` suffix is **optional**. When present it is verified, and a mismatch
  gives `ERR - 2 CRC`. This lets a person type commands in a terminal.
- On reset the DUT sends one `HELLO` line.

## 2. Host → DUT commands

Keywords are case-insensitive. Addresses and bytes are hex (1–2 digits, optional `0x`).
Counts, speeds and times are decimal. `<id>` is the responder: `1` = I2C2 (R1), `2` = I2C3 (R2).

| Command | Effect | Reply |
|---|---|---|
| `PING` | — | `HELLO …` |
| `STATUS` | — | `STATUS …` |
| `RESET` | responders back to power-up defaults (address, enabled, PEC off, stretch off, pointer 0, subcommand 0); counters cleared; speed back to the default | `OK RESET` |
| `SET SPEED <hz> [<rise_ns> <fall_ns>]` | recompute TIMINGR for I2C1 (master) and apply it to I2C2/3 too (their SDADEL/SCLDEL); rise/fall default 300/30 | `OK SPEED hz=… pred=… timingr=… presc=… scll=… sclh=… sdadel=… scldel=… rise=… fall=…` or `ERR - 3 SPEED infeasible` |
| `SET ADDR <id> <addr7>` | change the responder's own address (must differ from the other responder) | `OK ADDR <id> <aa>` |
| `SET EN <id> <0\|1>` | 0 = the responder stops matching, so its address NAKs | `OK EN <id> <v>` |
| `SET PEC <id> <n>` | after `n` read bytes the responder sends the SMBus PEC byte (0 = off) | `OK PEC <id> <n>` |
| `SET STRETCH <id> <byte_index> <us>` | hold SCL low `us` µs before byte `byte_index` of each phase (0 = right after the address); `us` 0 = off; max 10 000 | `OK STRETCH <id> <i> <us>` |
| `RUN <seq> W <aa> <b0> [b1 …]` | START, write, STOP | `PH` lines + `END` |
| `RUN <seq> R <aa> <n>` | START, read n, STOP | |
| `RUN <seq> WR <aa> <n> <b0> [b1 …]` | START, write, **repeated START**, read n, STOP | |
| `RUN <seq> WPR <aa> <n> <b0> [b1 …]` | START, write, STOP; START, read n, STOP | |

`RUN` options (trailing, any order): `rep=<1..1000>` repeats the operation back to back (each
iteration is reported); `gap=<us>` waits between iterations.

Limits: at most 128 bytes per phase (`LB_MAX_XFER`); `<seq>` is 0 to 2³²−1 and is echoed
unchanged so the host can detect a lost or reordered reply.

## 3. DUT → host lines

| Line | Meaning |
|---|---|
| `HELLO LBDUT proto=1 fw=<maj>.<min> kernel=64000000` | identity (fw 0.2 from 2026-10-02); `kernel` = I2C kernel clock in Hz |
| `PH <seq> <iter> <idx> <S\|SR> <aa> <W\|R> <A\|NA\|ND\|ER> <P\|-> <n> [hex …]` | one bus phase as the **master** saw it: start type, 7-bit address, direction, acknowledge result, whether a STOP ended it, byte count, bytes |
| `END <seq> <iter> <OK\|NAK\|ERR> t=<us> dur=<us>` | iteration finished; `t` = DUT µs timestamp (TIM2, 32-bit) at the start |
| `OK …` | a `SET` or `RESET` succeeded |
| `STATUS proto=… fw=… hz=… pred=… r1=<aa>:<en> r2=<aa>:<en> pec=<n1>,<n2> stretch=<us>@<i>,<us>@<i> r1w=… r1r=… r2w=… r2r=… rerr=…,… merr=… uart_ovr=…` | configuration and counters |
| `ERR <seq\|-> <code> <text>` | codes: 1 SYNTAX, 2 CRC, 3 ARG, 4 LONG |

Acknowledge field of `PH`:

- `A`: every byte acknowledged. On a read, the master's NAK after the final byte is normal and
  still reads `A`.
- `NA`: address NAK. `n` is 0 and no bytes follow. For `WR`, the read phase is not attempted.
- `ND`: a data byte was NAKed on a write. The count is approximate: HAL does not report exactly
  which byte was NAKed.
- `ER`: bus error or timeout. The master peripheral is reset.

A `PH` phase is ground truth for **what the master put on or took off the bus**. It is
independent of any sniffer. Read bytes are what the master actually received.

## 4. Register map (both responders)

The pointer is the first byte of each write phase. It persists across STOP. Reads start at the
pointer, and the pointer does **not** advance after a read, so every read is a pure function of
(pointer, subcommand).

**Word region** (pointer outside 0x3E–0x61):

    read byte k = byte (k & 1) of word(ptr + k/2), little-endian
    word(x)     = (base + x) & 0xFFFF      base: R1 0xA000, R2 0xB000

| Example | Bytes |
|---|---|
| R1, pointer 0x02, read 4 | `02 A0 03 A0` |
| R2, pointer 0x02, read 2 | `02 B0` |
| R1, pointer 0x00, read 80 | … ends `27 A0` |
| R1, pointer 0xFF, read 4 | `FF A0 00 A1` (no wrap) |

**Subcommand block** (pointer 0x3E–0x61, byte-addressed). This is the TI BQ769x layout that
`DecodeSchema._unwrap_subcommand_block` unwraps:

| Offset | Content |
|---|---|
| 0x3E, 0x3F | echo of the last subcommand written to 0x3E (little-endian) |
| 0x40–0x5F | `buf[i] = (0x40 + i) XOR (subcommand & 0xFF)` |
| 0x60 | checksum `~(lo + hi + sum(buf)) & 0xFF` (0x0E for subcommand 0x0001) |
| 0x61 | length = 36 |
| past 0x61 | 0xFF |

**Writes:** byte 0 sets the pointer. If the pointer is 0x3E, bytes 1–2 set the subcommand
(little-endian). All other data is acknowledged and counted, but not stored.

**PEC** (`SET PEC <id> <n>`): after `n` read bytes the responder sends CRC-8/SMBUS over the
whole transaction:

- Addr+W, every written byte, Addr+R and the data bytes, when the read follows a write with no
  STOP in between (repeated START);
- only Addr+R and the data for a stand-alone read.

For writes, the **host** appends the PEC byte to the data it sends. The responder does not
check it.

## 5. Behaviour notes

- **Address NAK target.** I2C1's own address (0x08 from CubeMX) is kept but its matching is
  disabled at start-up (`OAR1.OA1EN = 0`), so any access to 0x08 is NAKed. This is also what
  stops the master peripheral from answering its own address.
- **Clock stretch** happens at byte boundaries only. The responder ISR busy-waits before
  releasing ADDR or loading TXDR, and SCL is held low meanwhile. A hardware I2C slave cannot
  stretch mid-byte. UART receive can overrun during very long stretches, so the host must wait
  for `END` before sending the next command (counted in `uart_ovr`).
- **Speed.** `pred` is the TIMINGR model's prediction: t_SCL = (SCLL+1+SCLH+1)·t_PRESC +
  t_rise + t_fall + 2·t_AF + 6·t_I2CCLK. The model puts CubeMX's own 100 kHz values at
  99.45 / 99.76 kHz, and every speed from 10 to 400 kHz lands within 2 % of the target in
  simulation. The **measured** value is the sniffer's `SCL (Hz)` column. Supported range is
  about 8 kHz–400 kHz; 1 MHz is infeasible with a 300 ns rise and out of scope, because PB12
  is not an Fm+ pin.
- **SYNC** (PB5, D4) is high for the duration of each `RUN` iteration: use it as the scope
  trigger. **ALERT** (PB4, D5) is wired open-drain and held released (high). There is no
  command for it until Phase 11.
- **Heartbeat:** LD2 toggles every 500 ms while the main loop runs.

## 6. Example session

```
<- HELLO LBDUT proto=1 fw=0.1 kernel=64000000 *BF
-> SET SPEED 100000
<- OK SPEED hz=100000 pred=100075 timingr=20B56464 presc=2 scll=100 sclh=100 sdadel=5 scldel=11 rise=300 fall=30 *0D
-> RUN 1 WR 6B 2 02
<- PH 1 0 0 S 6B W A - 1 02 *12
<- PH 1 0 1 SR 6B R A P 2 02 A0 *CB
<- END 1 0 OK t=12345678 dur=412 *99
-> RUN 2 W 08 00
<- PH 2 0 0 S 08 W NA P 0 *2B
<- END 2 0 NAK t=12399001 dur=121 *89
```

(Each `*CC` is the real CRC-8/SMBUS of its line, usable as a test vector. The TIMINGR shown is the host-test value for 100 kHz at
rise 300 / fall 30. Timestamps are illustrative. Not yet captured on hardware.)

## Revision history

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-09-30 | First version (DUT fw 0.1, protocol 1) |
| v0.2 | 2026-10-02 | HELLO fw field generic (fw 0.2: address NAK reported NA); §6 example kept as the fw 0.1 CRC test vector |
