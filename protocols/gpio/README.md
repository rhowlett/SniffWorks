# SniffWorks — GPIO sniffer
<!-- v0.1 -->

Captures digital-line edges with device timestamps so they can be shown on the SniffWorks timeline next to I²C and the other buses. A GPIO edge is often the event that links two buses, for example an I²C write that raises an interrupt line, which then starts the next transfer.

Status: **requirements draft**, no code yet. See `documents/requirements.md`.

## Layout

```
protocols/gpio/
  CLAUDE.md              working agreement for this sub-project
  README.md              this file
  core/                  GPIO event type, decoding, no UI imports
  ui/                    GPIO panels for the master and standalone apps
  schema/                GPIO capture/config schemas
  tests/                 host-side tests
  tools/                 dev and maintenance scripts
  documents/
    requirements.md      what the GPIO sniffer must do
    change_log.md        per-change history
    user_guides/         user guide (later)
```

Probe firmware is built from the repo-wide tree, not from here:

```
firmware/common/                       shared framing, timestamp, ring buffer, sync
firmware/targets/stm32c031c6-nucleo/   C0 POC: GPIO alone or combined with I²C
firmware/targets/stm32h723zg-nucleo/   H7 POC: multi-interface
system_emulation_testing/firmware/     stimulus and emulator boards (not for normal use)
```
