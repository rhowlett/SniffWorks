# GPIO sniffer — requirements
<!-- v0.1 -->

**Status:** draft for owner review (2026-10-19). Each item says where it came from:
*owner* = stated by the owner; *proposed* = Claude's proposal, not yet accepted. Proposed items become requirements only when the owner accepts them.

## 1. Purpose

Capture edges on digital lines with device timestamps, so GPIO activity appears on the SniffWorks timeline with the other buses and can be checked against the expected cross-bus sequence (root SW-10).

## 2. Requirements

| ID | Requirement | Source |
|---|---|---|
| GPIO-R01 | The sniffer reports GPIO edges as interrupt-like events that other buses' events can be triggered on and compared with. | owner (SW-05) |
| GPIO-R02 | It supports the first cross-bus test: an I2C1 event triggers a GPIO, then an I2C2 event is expected. | owner (SW-05) |
| GPIO-R03 | It runs as a standalone GPIO app and inside the master multi-sniffer app, from one codebase. | owner (SW-01) |
| GPIO-R04 | A C0 target can be built for GPIO alone or GPIO combined with other interfaces (I²C, SPI, UART); the H723 target carries GPIO among many interfaces. | owner (SW-04) |
| GPIO-R05 | Timestamps come from the probe's own clock and share the SniffWorks sync line when more than one probe is used. | owner (SW-03) |
| GPIO-R06 | Captures are written to the SniffWorks multi-stream CSV. | owner (SW-07) |
| GPIO-R07 | Each event carries channel, edge (rise/fall), level after the edge, and the device timestamp. | proposed |
| GPIO-R08 | Per channel, the user can enable/disable it, name it (e.g. `PMIC_INT`), and choose rising, falling or both edges. | proposed |
| GPIO-R09 | The probe counts edges it could not record (ring overflow, edges closer than the ISR can handle) and reports the count, so a missing event is never mistaken for a missing signal. | proposed |
| GPIO-R10 | The app shows the minimum resolvable pulse width for the connected target, measured on the bench, not assumed. | proposed |
| GPIO-R11 | Expectation rules can name a GPIO event, e.g. "after I²C write 0x6B reg 0x12, PA3 rises within 500 µs". | proposed |

## 3. Open items

- Channel count, voltage range and input protection per target.
- Shortest pulse and maximum edge rate to support (the C031 edge ISR loses edges closer than ~1-2 µs; i2c_tools findings).
- Glitch filter: firmware, host, or none.
- Which target runs the first I2C1 → GPIO → I2C2 test.
- How the system-emulation board generates the test stimulus for GPIO-R02.
