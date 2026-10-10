# Loopback DUT rig — bring-up, capture, and report
<!-- v0.2 -->

This guide takes you from a box of parts to a judged loopback report for both sniffers. Each
step ends with a concrete **Expected** result. Do not move on until you see it.

Values marked **(measured on this unit)** come from the owner's rig on 2026-10-02 / 2026-10-05.
Your ports, sizes and timings may differ.

| Need detail on… | See |
|---|---|
| building and flashing either board | `embedded/docs/build_and_flash.md` |
| regenerating the DUT CubeMX project, pin rationale, DUT line protocol | `loopback_dut/docs/setup_guide.md` (§4) and `loopback_dut/docs/PROTOCOL.md` |
| the test cases and the xfail ledger | `loopback_dut/patterns/loopback_v1.json` |

---

## 1. What you are building

A **NUCLEO-H533RE** runs the loopback DUT firmware. Its I2C1 is the bus **master**, and its
I2C2 (address **0x6B**) and I2C3 (**0x55**) are **responders** with a synthetic register map.
Address **0x08** is never acknowledged (the address-NAK case). The PC tells the DUT what to
put on the bus and records exactly what happened (`expected.json`).

Two **sniffers under test** listen on the same two wires:
- **ion:** a **NUCLEO-C031C6** with `sniffer_nucleoC0_fw`, used from `sniffer_ion.py` or
  `tools/ion_capture.py`;
- **AD2:** an **Analog Discovery 2**, used from `sniffer_ad2.py`.

The harness compares each sniffer's CSV export against `expected.json` and writes a report.

The DUT and the sniffer tools are kept apart on purpose: they share only files, never code.

---

## 2. Parts

| Qty | Item |
|---|---|
| 1 | NUCLEO-H533RE (USB-C cable) |
| 1 | NUCLEO-C031C6 (micro-USB cable) |
| 1 | Digilent Analog Discovery 2 (USB cable, WaveForms installed) |
| 2 | 4.7 kΩ resistors |
| 1 | small breadboard + ~12 short jumpers (< 15 cm) |

---

## 3. Wiring

The bus has three nets: **SCL**, **SDA** and **GND**. Build two breadboard rails (SCL, SDA) and
a common GND rail.

| Board | SCL | SDA | GND |
|---|---|---|---|
| H533 I2C1 (master) | **D15** (PB6, CN5-10) | **D14** (PB7, CN5-9) | CN6-6 |
| H533 I2C2 (0x6B) | **D6** (PB10, CN9-7) | **morpho CN10 pin 16** (PB12), *not* on the Arduino header | — |
| H533 I2C3 (0x55) | **D7** (PA8, CN9-8) | **D10** (PC9, CN5-3) | — |
| C031 sniffer | **D8** (PA9) | **D2** (PA10) | any GND |
| AD2 | **DIO 0** | **DIO 1** | ⏚ |

- **Pull-ups:** exactly **one** 4.7 kΩ from SCL to 3V3 and **one** from SDA to 3V3. Take the
  3V3 from the **H533 CN6 pin 4**. Use no other pull-ups anywhere.
- **Ground:** tie **every** GND together (H533, C031, AD2).
- **Power:** each board powers from its own USB. Never join the boards' 3V3 rails.
- **Optional trace jumpers** (firmware investigations only): C031 **A0 → AD2 DIO2** and
  **A1 → AD2 DIO3**. They are harmless with the default firmware.

**Check (multimeter, all boards powered):** SCL to GND and SDA to GND both read
**3.3 V ± 0.1 V**. If a line is near 0 V, a board is holding it low (§8).

Both first-attempt failures on this rig were wiring: the H533 GND was not connected, and PB12
was jumpered to CN10 pin **10** instead of pin **16** **(measured on this unit)**.

---

## 4. Firmware: which board gets which image

| Board | Image | Flash |
|---|---|---|
| H533 | `loopback_dut/firmware/build/firmware.bin` (DUT fw **0.2**) | `cp … /Volumes/NOD_H533RE/` |
| C031 | `embedded/sniffer_nucleoC0_fw/build/sniffer_nucleoC0_fw.bin` (sniffer fw **1.6**, bit-bang, edge interrupt) | `cp … /Volumes/NOD_C031C6/` |

How to build either image: `embedded/docs/build_and_flash.md` §3.

**Wrong variant check:** `tools/ion_capture.py --status-only` must print `fw 1.6, mode bit-bang`.
`slave-mon` or `master` mode, or a fw below 1.6, is the wrong image for this rig.

---

## 5. First contact (no bus traffic yet)

From the project root, with `source .venv/bin/activate`:

```bash
ls /dev/cu.usbmodem* 2>/dev/null                      # two ports: H533 and C031
python -m serial.tools.list_ports -v                   # match ports to boards by SER=
```

On this rig **(measured on this unit, 2026-10-05)**:

| Board | Port | ST-LINK serial |
|---|---|---|
| C031 | `/dev/cu.usbmodem1203` | `066BFF54…` |
| H533 | `/dev/cu.usbmodem1403` | `00320027…` |

The port names change if you use another USB socket. Name the boards once (sniffer app
**Name devices…**, or `python tools/device_names.py discover`), and every command
below accepts the name instead of the port, e.g. `--port "H533 DUT"` and
`--port "C031 sniffer"`. Names are per user, in `~/.ion_i2c_tool/device_names.json`.

1. **C031:**
   `python tools/ion_capture.py --port <C031 port> --seconds 1 --status-only`
   **Expected:** `probe: fw 1.6, mode bit-bang` and `STATUS: fw 1.6 …`. If not, press the
   C031 RESET button and retry.
2. **H533:**
   `python -m serial.tools.miniterm <H533 port> 115200 --eol LF`, then type `PING`.
   **Expected:** `HELLO LBDUT proto=1 fw=0.2 kernel=64000000 *AD`. Exit with Ctrl-].
3. **Bus check from the DUT:** in the same miniterm, type `RUN 1 WR 6B 2 02`.
   **Expected:**
   ```
   PH 1 0 0 S 6B W A - 1 02 *12
   PH 1 0 1 SR 6B R A P 2 02 A0 *CB
   END 1 0 OK …
   ```
   R1 answered (`A`) and returned word 0xA002, little-endian `02 A0`. More exact expected lines
   (LB-03 / LB-05 / LB-09) are in `loopback_dut/docs/setup_guide.md` §9.4.
4. **Self-checks, no hardware needed:**
   ```bash
   python loopback_dut/tests/test_pattern_schema.py
   python loopback_dut/tests/test_host_model.py
   python loopback_dut/tests/test_loopback_harness.py
   ```
   **Expected:** each ends with `ALL TESTS PASSED`.

---

## 6. A full run

A run takes about 4 s on the DUT: 15 cases, 434 bus phases, LB-13 (400 kHz) last. Make a run
folder first, e.g. `D=loopback_dut/runs/$(date +%F)_myrun; mkdir -p $D`.

### 6.1 ion sniffer, headless (recommended)

```bash
python tools/ion_capture.py --port <C031 port> --seconds 15 --pec \
       --decoder i2c_decoders/loopback_dut_decoder.json --out $D/ion_capture.csv &
sleep 2
python loopback_dut/host/loopback_run.py --port <H533 port> \
       --out $D/expected.json --transcript $D/transcript.txt
wait
python loopback_dut/tests/test_loopback_capture.py $D
```

**Expected:**
- `loopback_run` prints 15 lines `LB-xx ok … 100000 Hz (pred 100075)`, with LB-13 at
  `400000 Hz (pred 401204)`.
- `ion_capture` prints `kept ~429 of ~429 transactions; FRAMING-flagged 0`.
- The capture test prints `ion: pass 11 fail 0 xfail 4 xpass 0 not_exercisable 0  ledger EXACT`
  **(measured on this unit, fw 1.6, runs 2026-10-05_G1/G2/H1/H2 re-judged)**, and reports the
  AD2 path as `SKIPPED` (there is no AD2 capture in this folder).

### 6.2 Both sniffers from the GUIs

1. **ion GUI:** close any `ion_capture.py`, then run `./run.sh sniffer_ion.py`.
   - **Device** tab → *Refresh* → pick the C031 port → *Connect*.
   - **Sniffer** tab:
     - Decoders → *Add…* `i2c_decoders/loopback_dut_decoder.json`, and load **no other
       decoder on 0x6B**;
     - tick **Validate SMBus PEC** before starting;
     - clear all filters;
     - press **▶ Start Sniffing**.
2. **AD2 GUI:** `./run.sh sniffer_ad2.py`.
   - **Device** tab → *Refresh* → pick the AD2 → *Connect*. SCL = DIO 0, SDA = DIO 1.
   - Apply the same decoder, PEC and filter settings as for the ion GUI, then start.
   - Close the WaveForms app first: only one program can own the AD2.
3. **Emit the pattern:** run the same `loopback_run.py` command as in §6.1.
4. **Stop and export:** stop both sniffers. **Export CSV** to `$D/ion_capture.csv` and
   `$D/ad2_capture.csv`. Export writes only the visible rows, so clear the filters first.
5. **Judge:** `python loopback_dut/tests/test_loopback_capture.py $D`.

---

## 7. Reading the reports

The capture test writes `$D/loopback_report_ion.md` and `$D/loopback_report_ad2.md`. Each has
one row per case: ID, review IDs, ledger status, **verdict**, and phases matched.

| Verdict | Meaning | Action |
|---|---|---|
| `pass` | the sniffer captured exactly what the DUT emitted | none |
| `xfail` | it failed **exactly** as the ledger records (every symptom listed) | none; a known open review item |
| `fail` | an unexplained failure | new finding: read the case section's byte-level diff, then assign a review ID |
| `xpass` | a recorded bug did not show | the ledger may be stale; confirm over several runs, then update the ledger |
| `not_exercisable` | the capture lacks something the case needs (PEC results, Decode text) | fix the setup (§6.2: PEC ticked, decoder loaded) and capture again |

The header line `Ledger exact: YES` means every verdict was `pass` or `xfail`. Below the table,
each non-pass case lists its findings, e.g.
`data_mismatch: iter 0 phase 1 … expected 2 B [02 A0], captured 2 B [04 41]`.

The current ledger (2026-10-05):

| Item | Cases | Path |
|---|---|---|
| B8 | LB-04 | both |
| B9 | LB-07 | both |
| B10 | LB-09/10/11 | AD2 |
| B13 | LB-06 | both |
| B31 (400 kHz) | LB-13 | ion |
| B32 | most Sr-terminated cases | AD2 |

B30 was fixed in C031 fw 1.6. To re-judge an old run against today's ledger:
`python loopback_dut/host/loopback_compare.py --expected <dir>/expected.json --capture <dir>/ion_capture.csv --path ion --pattern loopback_dut/patterns/loopback_v1.json`.

---

## 8. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| **No ACK**: the DUT reports `NA` from 6B or 55 on every access | responder pin not on the bus, or GND missing | I2C2 SDA is **CN10 pin 16** (not pin 10, not the Arduino header); tie all GNDs; `STATUS` on the DUT shows `r1w=0` when R1 was never addressed |
| **No ACK** from 0x08 | expected: 0x08 always NAKs (LB-05) | none |
| **No HELLO** from the C031 | not flashed, port held by another program, or board needs a reset | close `sniffer_ion.py`; press RESET; re-flash (`build_and_flash.md` §4) |
| **No HELLO** from the DUT | terminal sends CR only, or wrong port | use `miniterm … --eol LF`; check the port's serial number |
| **Wrong firmware variant** on the C031 | `--status-only` shows `slave-mon`, `master`, or fw < 1.6 | flash `embedded/sniffer_nucleoC0_fw/build/sniffer_nucleoC0_fw.bin` |
| C031 fw 1.4 answers every command with `ERROR 2/0xFF` | known fw 1.4 defect | press RESET, flash fw ≥ 1.5 |
| **Bus stuck low** (SCL or SDA near 0 V, DUT `END … ER`) | a board drives the line, or there are no pull-ups | measure both lines idle (§3); unplug boards one at a time; check the two 4.7 kΩ |
| ion: every row `0x00 W`, no data | firmware built with `SNIFF_DIAG` or `SNIFF_DEFER_UPKEEP` (polled mode) | flash the default image |
| ion: nothing captured at 400 kHz (LB-13) | known limit B31 of the C031 (48 MHz M0+) | expected `xfail`; use the AD2 for 400 kHz buses |
| AD2: `0x00 W [00]` rows instead of pointer writes | known AD2 issue B32 | expected `xfail` |
| `not_exercisable` for LB-07/08 | PEC validation not ticked before Start | tick it, re-capture |
| `not_exercisable` for LB-04 | loopback decoder not loaded | load `i2c_decoders/loopback_dut_decoder.json` |
| `loopback_run` prints `model_mismatch` | the DUT did not do what the host model predicts (DUT or wiring) | redo §5 step 3 |
| `DESYNC in case LB-xx` (exit 2) | a DUT reply carried the wrong sequence number | re-run; keep the transcript as evidence |

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v0.2 | 2026-10-05 | Device names: `--port <name>` for all rig commands |
| v0.1 | 2026-10-05 | First version (P1-T6): rig, wiring, firmware per board, first contact, headless and GUI runs, report reading, current ledger, troubleshooting |
