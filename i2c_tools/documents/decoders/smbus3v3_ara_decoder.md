# SMBus ARA — I2C decoder

SMBus Alert Response Address (SMBALERT#). Source: SMBus Specification v3.3 (12 May 2024, SMIF) App. A.2 (Figs 65-66), §6.2.2.6, Table 17. Controller performs a modified Receive Byte; the lowest-address alerting device wins arbitration and returns its 7-bit address in [7:1] ([0] don't-care), optionally followed by PEC. A write to 0x0C is invalid per A.2/Table 17 (App. D states the opposite polarity; A.2 governs).

- **Address:** 0x0C (8-bit W 0x18 / R 0x19)
- **File byte order:** be
- **Schema version:** 4  ·  **Rules:** 2
- **Note:** Single-byte response; PEC byte (if any) trails and is ignored.

## Rules

| Reg | Type | W | Data | Fmt | BO | Sgn | Unit | Function | Name |
|-----|------|---|------|-----|----|----|------|----------|------|
| — | simple_read | 1 | 1 | hex | be |  |  | X | Alert Response |
| — | simple_write | 1 | 0 | hex | be |  |  | X | INVALID: write to ARA |

### Fields — Alert Response
- off 0 +1B **Alerting Device** hex be X>>1 

## Coverage

- **ARP (0x61):** every command byte 0x00–0xFF decodes. General 0x01–0x04; directed Get UDID (odd) / Reset Device (even) for legal targets 0x08–0x77 except 0x0C and 0x61; reserved 0x00, 0x05–0x0F, 0xFE, 0xFF on both write and read; directed forms aimed at 0x0C, 0x61 and 0x78–0x7E labelled *reserved target*. Wrong-direction use of a directed code (e.g. a read at even code 0x20) is not decoded.
- **Host Notify (0x08):** every command byte 0x00–0xFF decodes; sender = cmd >> 1, X = bit 0 (both values). Senders outside 0x09–0x77 or at 0x0C/0x61 are labelled *reserved sender*.
- **ARA (0x0C):** any read response decodes; writes are flagged invalid.
- These decoders only match traffic **addressed to** 0x08, 0x0C or 0x61. Device addresses appear inside the command/data byte, not in the rule `address`. Traffic to any other address (e.g. a device's own register reads) needs that device's decoder.

## Assumptions and open items

- **Engine behaviour unverified** (no `ion_i2c_tool` tree in this session): (1) whether a trailing PEC byte beyond `data_bytes` still lets a rule fire — ARP Send Byte rules have `data_bytes: 0` and every real ARP packet carries PEC; (2) whether the block-read byte count is passed through as payload byte 0 (assumed yes, decoded as `Byte Count`); (3) whether `fields` on non-subcommand rules renders in preference to the top-level `hex`/`X` fallback. Load `smbus_arp_sequence_pec.csv` with all three decoders to settle all three in one pass.
- **Enumerated per command byte** because rules match exact command bytes. An engine register-mask match would collapse ARP and Host Notify to a handful of rules.
- Directed commands 0x10–0x1F (targets 0x08–0x0F, incl. Smart Battery 0x0B → 0x17) sit inside Table 10's reserved *general* range 0x05–0x1F; decoded as directed.
- Target/assigned address fields render the 7-bit address (`X>>1`); the Get UDID "bit 0 must be 1" rule is not checked.
- Out of scope: Host Notify status meanings (device-specific; SBS AlarmWarning needs the Smart Battery Data spec), PMBus ZONE READ/WRITE (0x28/0x37), Quick Command, bus timing/electrical.

## Document defects (SMBus 3.3, 12 May 2024)

1. **App. D vs A.2 / Table 17 — ARA direction inverted.** App. D says sending the ARA with R/W# = 1 is not permitted; A.2 and Table 17 say R/W# = 0 (write) is invalid. A.2/Table 17 govern.
2. **Table 8 has no SMBus 3.3 version code.** Highest defined is 0111b = 3.2. Decoder renders 1000b as reserved.
3. **§6.2.2.7 stale cross-reference.** Device Default Address "See Section 6.5.10" — ARP is §6.6.
4. **Table 17 cites "V 3.3, February 2024"** for the ARA-write row; the document is dated 12 May 2024.
5. **Table 10 range overlap.** "General 00h–1Fh" overlaps the directed encoding for targets 0x00–0x0F.

History: see `change_log.md`.
