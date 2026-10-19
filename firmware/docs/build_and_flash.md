# Build and flash — SniffWorks probe firmware
<!-- v0.1 -->

**Status:** no target in `firmware/` builds yet. This file documents only proven procedures, so it is empty until the first target builds and flashes on the bench.

Until then, the proven procedure for the existing C031 I²C probe is `i2c_tools/embedded/docs/build_and_flash.md`. When the C031 code moves into `firmware/`, copy that procedure here, update it, and re-prove it.

Each target section must cover:
- the toolchain and its version (compiler, CubeMX/CubeIDE if used);
- the probe/adapter hardware;
- every supported build path (make, IDE, CubeProgrammer CLI, drag-and-drop to the ST-LINK volume);
- OS-specific quirks;
- the board's power-up and connection steps, with expected voltages.
