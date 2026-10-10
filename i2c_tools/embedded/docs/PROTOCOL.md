# NUCLEO-C031C6 I2C Sniffer — Serial Protocol Specification

Protocol version: **1**
Transport: USART2 through the on-board ST-LINK Virtual COM port.
Default: **115200 baud, 8N1, no flow control** (`HOST_UART_BAUD` in
`Core/Inc/sniffer_config.h`).

All multi-byte integers are **little-endian**.
All CRCs are **SMBus CRC-8**: polynomial `0x07`, initial value `0x00`,
no reflection, no final XOR — identical to `core/i2c_controller.py::smbus_crc8`
in the host application.

---

## 1. Device → Host frames

```
+------+------+--------+--------+=============+------+
| 0xAA | type | len_lo | len_hi | payload ... | crc8 |
+------+------+--------+--------+=============+------+
```

* `len` = payload length in bytes.
* `crc8` is computed over `type`, `len_lo`, `len_hi`, and the payload.
* Resynchronization: scan for `0xAA`, attempt a parse, discard on bad CRC and
  resume scanning from the next byte.

### 1.1 TXN — captured I2C transaction (`type = 0x01`)

| Offset | Size | Field   | Meaning                                          |
|-------:|-----:|---------|--------------------------------------------------|
| 0      | 4    | `t_us`  | Timestamp of the START condition, microseconds. Free-running 32-bit counter, wraps every ~71.6 min. |
| 4      | 1    | `addr7` | 7-bit slave address                              |
| 5      | 1    | `flags` | See below                                        |
| 6      | 1    | `dlen`  | Number of data bytes following                   |
| 7      | n    | `data`  | Captured payload (`dlen` bytes, max `TXN_MAX_DATA` = 64) |
| 7 + n  | 4    | `scl_hz`| fw ≥ 1.3: measured SCL frequency of **this phase** in Hz, `0` = not measured. Absent in older firmware; hosts size `data` by `dlen` and treat a missing field as unknown. See §1.1.1. |

`flags` bits:

| Bit | Name       | Meaning                                                  |
|----:|------------|----------------------------------------------------------|
| 0   | `DIR_READ` | 1 = read transaction, 0 = write                          |
| 1   | `NAK`      | Final ACK cell was a NAK (address NAK, or the normal master NAK ending a read) |
| 2   | `RESTART`  | Opened by a repeated START                               |
| 3   | `STOP`     | Closed by a STOP (0 = closed by a repeated START)        |
| 4   | `OVERFLOW` | Payload exceeded `TXN_MAX_DATA`; `data` holds the first 64 bytes |
| 5   | `TIMEOUT`  | Master mode only: transfer exceeded the 25 ms firmware budget |
| 6   | `FRAMING`  | fw ≥ 1.2, bit-bang mode: the phase closed off a bit boundary (an SCL edge was lost or a glitch added one), so its address/data bytes are bit-slipped and must not be trusted. Older hosts ignore the bit. |

#### 1.1.1 SCL measurement (`scl_hz`, fw ≥ 1.3)

Bit-bang mode measures every address phase on its own; the accumulator
resets at each START and repeated START.

* Every SCL rise-to-rise interval inside the phase is a candidate period,
  timestamped with the 1 MHz TIM3 counter (1 µs resolution).
* A period is **accepted** when it is no longer than 1.5 × the shortest
  period seen in the phase. That excludes clock-stretched bits (a slave
  holding SCL low mid-byte or at the ACK) and inter-byte gaps, which only
  ever lengthen a period.
* `scl_hz = round(1e6 × accepted_count / sum_of_accepted_µs)`. Averaging
  resolves well below the 1 µs tick: a 400 kHz bus (2.5 µs periods) reads
  as alternating 2 µs / 3 µs samples whose mean is 2.5 µs.
* Fewer than `I2C_DEC_SCL_MIN_PERIODS` (default 4, `sniffer_config.h`)
  accepted periods → `0`. Every well-formed phase has at least 8.
* The division is done at frame-encode time in the main loop, never in the
  sampler (the repeated-START path is timing-critical; the M0+ has no
  hardware divider).
* Slave-monitor mode: `0` (the I2C1 peripheral owns PA9, so edges cannot be
  timed). Master mode: `0` (the host already knows the speed it set).

Accuracy, host simulation with 1 µs timestamps (`embedded/tests/host`,
`test_scl_hz_*`): 100 kHz within 0.5 %, 400 kHz within 2 % (measured
402 985 Hz), a 200 µs mid-byte stretch excluded. **Not yet measured on
hardware** — the loopback DUT (Phase 1, case LB-13/LB-14) provides that.

Transaction model: **one frame per address phase**, matching the Python
`I2CTransaction` dataclass. A register read (`write reg-pointer, repeated
START, read data`) therefore produces **two** TXN frames:

1. write, `STOP=0`, `RESTART=0`
2. read, `RESTART=1`, `STOP=1`, `NAK=1` (master NAK terminating the read)

Mapping to `I2CTransaction`: `start = 2 if RESTART else 1`, `stop = bool(STOP)`,
`direction = READ if DIR_READ else WRITE`, `nak = bool(NAK)`. PEC validation
remains host-side (raw bytes are all present in `data`).

### 1.2 STATUS (`type = 0x02`), sent at 1 Hz while capturing and on request

| Offset | Size | Field       | Meaning                                    |
|-------:|-----:|-------------|--------------------------------------------|
| 0      | 1    | `proto_ver` | Protocol version (1)                       |
| 1      | 1    | `fw_major`  | Firmware major version                     |
| 2      | 1    | `fw_minor`  | Firmware minor version                     |
| 3      | 1    | `mode`      | 1 = bit-bang, 2 = slave-monitor            |
| 4      | 1    | `state`     | 0 = idle, 1 = capturing                    |
| 5      | 4    | `captured`  | Transactions captured since START/reset    |
| 9      | 4    | `errors`    | Decoder/bus errors; fw ≥ 1.6 also counts edges lost to a full edge ring |
| 13     | 4    | `dropped`   | TXN frames dropped (UART ring overflow)    |
| 17     | 4    | `bus_hz`    | Bus clock in Hz (0 = unknown). fw ≥ 1.3: the `scl_hz` of the **most recent** measured phase, so it follows speed changes. (fw ≤ 1.2: 1e6 / shortest SCL period since capture start, a sticky minimum.) No configuration is needed for 100 kHz vs 400 kHz. |

#### 1.2.1 Sampler diagnostics (fw ≥ 1.4, bit-bang mode, `SNIFF_DIAG = 1`)

Off by default from fw 1.5 (the instrumentation itself broke 100 kHz capture on hardware; see
`embedded/docs/B30_B31_investigation.md` §1.2), so STATUS is normally 21 bytes.
When present, STATUS is **45** bytes. Bytes 0–20 are unchanged, so hosts that read 21 bytes
ignore the rest. Ticks are probe SYSCLK cycles (48 MHz, 20.83 ns). `0xFFFF` in a "narrowest"
field means none was seen. Everything is measured **only while a transaction is open** and
is reset by START and RESET_COUNTS.

| Offset | Size | Field | Meaning |
|-------:|-----:|-------|---------|
| 21 | 1 | `diag_ver` | 1 |
| 22 | 1 | — | 0 |
| 23 | 2 | `max_gap` | longest gap between two consecutive line samples |
| 25 | 2 | `min_high` | narrowest SCL high pulse (SCL-rise sample → SCL-fall sample) |
| 27 | 2 | `min_low` | narrowest SCL low pulse |
| 29 | 4 | `gaps_2us` | number of sample gaps longer than 2 µs |
| 33 | 4 | `framing` | phases flagged FRAMING (a lost or extra SCL edge) |
| 37 | 2 | `frm_max_gap` | worst sample gap inside any FRAMING phase |
| 39 | 2 | `frm_min_high` | narrowest SCL high inside any FRAMING phase |
| 41 | 4 | `deferred` | upkeep slots held off because a transaction was open (`SNIFF_DEFER_UPKEEP`) |

How to read it: if FRAMING phases show a `frm_max_gap` longer than half an SCL period, the
**sampler stalled** at that moment. If the gap is short but `frm_min_high` is below one loop
iteration (about 1 µs), the **SCL pulse was narrower than the sampler** can see. A stretch
longer than the 1.365 ms TIM14 wrap aliases the low width. Host decoding:
`core/ion_protocol.py::decode_status()["diag"]`; printed by `tools/ion_capture.py`.

### 1.3 ERROR (`type = 0x03`)

| Offset | Size | Field    |
|-------:|-----:|----------|
| 0      | 1    | `code`   |
| 1      | 1    | `detail` |

Codes: `0x01` UART ring overflow (frames lost), `0x02` bad host command,
`0x03` bus/decoder error.

### 1.4 HELLO (`type = 0x04`), sent at boot and in reply to PING

| Offset | Size | Field       |
|-------:|-----:|-------------|
| 0      | 4    | Magic `"NC0S"` (`4E 43 30 53`) |
| 4      | 1    | `proto_ver` |
| 5      | 1    | `fw_major`  |
| 6      | 1    | `fw_minor`  |
| 7      | 1    | `mode`      |

The host auto-detects the sniffer by sending PING to candidate serial ports
and looking for the magic.

---

## 2. Host → Device commands

```
+------+-----+-----+------+
| 0xA5 | cmd | arg | crc8 |
+------+-----+-----+------+
```

`crc8` over `cmd` and `arg`. Unknown commands and bad CRCs elicit an ERROR
frame; the parser resynchronizes automatically.

Hosts may send commands back to back at any time, including while capturing:
from fw 1.5 the probe receives them by circular DMA (256 bytes). fw 1.4 lost
back-to-back command bytes while capturing (RX overrun), so a fw 1.4 host had
to space bytes about 2 ms apart or press RESET to stop a capture.

| cmd  | Name           | arg | Reply            |
|------|----------------|-----|-------------------|
| 0x01 | START          | 0   | STATUS            |
| 0x02 | STOP           | 0   | STATUS            |
| 0x03 | STATUS_REQ     | 0   | STATUS            |
| 0x04 | PING           | 0   | HELLO             |
| 0x05 | RESET_COUNTS   | 0   | STATUS            |

---

### Master-mode commands (protocol v1, implemented in SNIFF_MODE_MASTER)

Commands `0x10`–`0x13` are served by the master firmware variant
(`make EXTRA_DEFS='-DSNIFF_MODE=SNIFF_MODE_MASTER'`). They use a
**variable-length** command form:

```
[0xA5][cmd][len][payload ...][crc8]      crc8 over cmd..payload
```

| cmd  | Name           | Payload                     | Reply    |
|------|----------------|-----------------------------|----------|
| 0x10 | I2C_WRITE      | addr7, data[]               | TXN      |
| 0x11 | I2C_WRITE_READ | addr7, wlen, wdata[], rlen  | TXN × 2  |
| 0x12 | I2C_READ       | addr7, rlen                 | TXN      |
| 0x13 | SET_BUS_SPEED  | 0 = 100 kHz, 1 = 400 kHz    | STATUS   |

Sniffer firmware variants reply `ERROR(code=2)` to these; the master
variant conversely rejects `START`/`STOP`. A host must check HELLO's mode
byte (3 = master) before sending them. Host-side implementation:
`core/ion_protocol.py` (encoders) + `core/ion_master.py` (IonMasterLink).

Replies: each executed transfer emits one TXN frame per bus phase
(WRITE_READ emits two: the write, then the read with `restart=1`);
`SET_BUS_SPEED` is acked with a STATUS frame. TXN `flags` gained bit 5
`TIMEOUT` (transfer exceeded the 25 ms firmware budget — bus stuck or no
pull-ups); `NAK` keeps its meaning. Payload caps: 64 data bytes per phase.

### Target boards

`BOARD=BOARD_NUCLEO_C031C6` (default) or `BOARD=BOARD_ION_C0` (standalone
STM32C0 + USB-UART bridge; pin map provisional until hardware lands). The
protocol is identical on both; hosts identify a probe by the PING→HELLO
handshake, not by USB VID.

## 3. Timing and bandwidth analysis

### 3.1 Capture engine (bit-bang mode)

Zero-interrupt superloop at 48 MHz. The hot path (read GPIOA IDR, compare
with previous, decode on change) executes in well under 1 µs per iteration;
UART/command upkeep runs every 64 iterations and stays off the critical path.

* **100 kHz standard mode** (your current target): SCL half-period is 5 µs —
  the loop samples each line state many times over. Verified design budget
  with large margin. This is the supported, guaranteed rate.
* **400 kHz fast mode**: SCL high time can be as short as 0.6 µs. The loop
  usually catches every edge, but a worst-case burst of upkeep work can
  straddle a short SCL-high window. Treat 400 kHz as best-effort in bit-bang
  mode; if you move the target bus to 400 kHz permanently, the slave-monitor
  mode (hardware-assisted) captures writes robustly at that speed, or ask for
  the RAM-executed/assembly-tightened sampler as a follow-up.

### 3.2 UART throughput at 115200 baud

A TXN frame costs `17 + dlen` bytes ≈ `(17 + dlen) × 87 µs` (fw ≥ 1.3; the
trailing `scl_hz` added 4 bytes — was `13 + dlen`).

| Bus load example (100 kHz bus)            | UART time  | Bus time | Verdict |
|-------------------------------------------|-----------|----------|---------|
| 3-byte write every 10 ms (typical polling)| 1.4 ms    | 10 ms    | OK      |
| Register read pair (1B write + 2B read)   | 2.5 ms    | ~0.9 ms  | Bursts only |
| Saturated back-to-back traffic            | > bus time| —        | Ring absorbs ~370 txns, then drops are **counted and reported** in STATUS `dropped` |

The 6 KB TX ring rides out realistic bursts (the BQ76905 captures in
`i2c_capture/` are far below saturation). For sustained heavy traffic build
with `-DHOST_UART_BAUD=921600` — the ST-LINK VCP handles it, and the GUI will
expose baud selection in its preferences (Phase 3).

### 3.3 Timestamps

TIM3 free-runs at 1 MHz (16-bit) and is software-extended to 32 bits in the
loop. Accuracy is limited only by loop sampling (µs-scale). The counter wraps
after 2³² µs ≈ 71.6 minutes; the host should handle wraparound by treating
timestamps as monotonic modulo 2³².

---

## 4. Keeping implementations in sync

Three artifacts define this protocol and must change together:

1. `Core/Inc/frame_protocol.h` + `frame_protocol.c` (firmware)
2. This document
3. The Python parser in the host app (Phase 3: `core/nucleo_protocol.py`)

Host tests: `embedded/tests/host/test_frame_protocol.c` pins the byte-exact
layout; the Python side gets mirror tests in `tests/` in Phase 3.
Bump `FRAME_PROTOCOL_VERSION` on any wire change.
