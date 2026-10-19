# SniffWorks probe firmware
<!-- v0.1 -->

One source tree for every SniffWorks probe (root CLAUDE.md SW-04). Nothing is built from here yet; the working C031 I²C firmware still lives in `i2c_tools/embedded/` until it is migrated.

```
firmware/
  common/                  shared code: framing, capability handshake, timestamp, ring buffers, sync input
  targets/<mcu>-<board>/   one folder per board: NUCLEO POCs now, production boards later
  docs/build_and_flash.md  how to build and flash every target
  docs/change_log.md       firmware change history
```

## Naming

- **Target folder:** `<mcu>-<board>`, lower case, e.g. `stm32c031c6-nucleo`, `stm32h723zg-nucleo`. Production boards use the same pattern with their board name and revision (naming still open, root CLAUDE.md).
- **Build configuration:** the interface set compiled into a target, e.g. a C0 built for `gpio`, `i2c`, or `i2c+gpio`. Configuration names are still an open question.

Emulator and stimulus boards are not probes: they live in `system_emulation_testing/firmware/` with the same naming and are excluded from normal use.
