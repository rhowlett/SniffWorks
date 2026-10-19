# SniffWorks system emulation testing
<!-- v0.1 -->

Boards and host scripts that **generate** known bus traffic so the sniffers can be checked against ground truth. They emulate the system under test, for example an I²C master that raises a GPIO and then talks on a second I²C bus. This folder is excluded from normal SniffWorks use (root CLAUDE.md SW-13).

```
system_emulation_testing/
  firmware/
    common/                shared emulator code
    <mcu>-<board>/         one folder per emulator board, e.g. stm32h723zg-nucleo
    <other>/               anything that is not board firmware
```

Planned content:
- **NUCLEO-H723 test tool** for quick test creation, with emulators for the simpler hardware first, then the more complex devices (root SW-06).
- **I²C loopback DUT**: `i2c_tools/loopback_dut/` (NUCLEO-H533RE) moves here during the restructure, probably as `firmware/stm32h533re-nucleo/` plus its host scripts. Its isolation rule (never imports sniffer code; meets the sniffers only through files) carries over.
