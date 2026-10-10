# Phase 4 — Transaction Record & Replay (PLAN — refine after Phase 3)

Status: **planned**. Written while Phase 1 (embedded sniffer) is complete and
verified on hardware; to be refined once Phase 3 (sniffer_nucleoC0.py) exists,
because the host-side pieces will reuse Phase 3's `nucleo_protocol` module.

## Goal

1. **Record** a window of sniffed traffic bounded by a trigger transaction
   (e.g. BQ76905 subcommand read: `W 0x08 [3E]` + `rS R 0x08 [36 bytes]`),
   start on first occurrence, stop on the next.
2. **Replay** the recorded master-side traffic from the Nucleo (reflashed as
   an I2C master) against a device under test.
3. **Compare** replayed read responses byte-for-byte against the recording,
   with a mask for legitimately-dynamic bytes (voltages, counters, CRC/PEC).

## Firmware: third build variant `SNIFF_MODE_MASTER`

* Same project tree, same pins (PA9/PA10 = I2C1 AF6), same UART/DMA transport,
  same TXN frame for results. Selected via `#define` / `make EXTRA_DEFS=...`,
  exactly like the slave-monitor variant.
* This is the only variant that configures a real I2C clock: TIMINGR gets
  100 kHz and 400 kHz constants (manual switch, per project preference).
* Estimated ~200–250 lines of new C (polled LL master, shaped like
  `sniffer_slave_monitor.c`).

## Protocol extension (reserve in Phase 3, implement in Phase 4)

Current host→device commands are fixed 4 bytes. Master mode needs a
variable-length form:

```
[0xA5][cmd][len][payload ...][crc8]     crc8 over cmd..payload
```

New commands (reserved now):

| cmd  | Name            | Payload                                   | Reply |
|------|-----------------|-------------------------------------------|-------|
| 0x10 | I2C_WRITE       | addr7, data[]                             | TXN   |
| 0x11 | I2C_WRITE_READ  | addr7, wlen, wdata[], rlen                | TXN×2 |
| 0x12 | I2C_READ        | addr7, rlen                               | TXN   |
| 0x13 | SET_BUS_SPEED   | 0=100 kHz, 1=400 kHz                      | STATUS|

Replies reuse the existing TXN frame — a master-issued transaction and a
sniffed one are the same record shape. Reserving these now avoids a
`FRAME_PROTOCOL_VERSION` bump later.

## Host scripts (thin wrappers over Phase 3's protocol module)

1. `record_on_trigger.py` — sanity-check script + a predicate over decoded
   TXNs (match addr/dir/payload prefix, e.g. `0x08 W [3E]`). Starts a
   recording on first match, stops on next. Output: JSON-lines, one txn per
   line (`t_us, addr, dir, data, flags`) — greppable, diffable.
2. `replay_compare.py` — reads the JSON-lines file; issues each write
   verbatim; for reads, issues a read of the recorded length and diffs the
   response. Options:
   * `--timing preserve|flat` — honor recorded `t_us` gaps or run flat-out
   * `--mask FILE` — byte ranges to ignore per rule (seed from
     `i2c_decoders/bq76905_decoder.json`: its 42 rules identify which
     registers are dynamic measurements vs static config)
   * Report: per-txn PASS/MISMATCH with hex diff + NAK behavior differences.

## Prerequisites from Phase 3

* `core/nucleo_protocol.py` with framing/CRC shared by GUI and scripts
  (tests in `tests/`).
* PROTOCOL.md updated with the reserved command table above.

## Effort estimate (post-Phase 3)

1–2 focused days: firmware master variant + protocol extension (the careful
part: C, PROTOCOL.md, and Python move together) + two host scripts + host
tests for the new frames.
