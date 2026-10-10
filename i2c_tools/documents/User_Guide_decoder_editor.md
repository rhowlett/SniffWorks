# AD2 Decoder Editor — User Guide

`decoder_editor.py` is a standalone application for creating and editing decoder JSON files. A decoder maps I2C register addresses to human-readable names, units, and expressions, so the main tool and the replay app can annotate raw bus traffic with meaningful values. No hardware is required.

---

## Launch

```bash
# Open with a blank decoder
python decoder_editor.py

# Open an existing decoder file immediately
python decoder_editor.py path/to/decoder.json
```

---

## Window Layout

The window has two tabs: **Decoder** (the editor) and **Preferences** (theme selection). The title bar shows the current file name once a file is loaded or saved. The status bar at the bottom shows the last action and current file path.

### Decoder Tab

The Decoder tab is divided into four sections arranged top-to-bottom:

```
┌─────────────────────────────┬────────────────┬───────────┐
│  Rule                       │  Data          │  Save     │
│  (Address, Dir, Reg, Name,  │  (Byte order,  │  (Add/    │
│   Function Type, Unit)      │   Signed,      │   Update, │
│                             │   # Bytes)     │   Clear)  │
├─────────────────────────────┴────────────────┴───────────┤
│  Function / Bit Fields  (swaps based on Function Type)   │
├────────────────────────────────────────────────────────── ┤
│  Test  [ Test ]  [ hex input ]  Result:                  │
├──────────────────────────────────────────────────────────┤
│  Schema Rules  (table of all rules in current decoder)   │
├────────────────────────────────────────────────────────── ┤
│  [ Remove Selected ]  [ Clear All ]   path label   file ops │
└──────────────────────────────────────────────────────────┘
```

---

## Rule Fields

Every decode rule is defined by the fields in the **Rule** and **Data** groups.

### Rule Group

**Address (Hex)** — the 7-bit I2C device address in hex (e.g. `0x08`). This must match the address as it appears in the capture (`0x08`, not the 8-bit shifted form `0x10`).

**Direction** — which bus phase this rule applies to:
- `R` — the data phase of a read (most common for register reads)
- `W` — the data bytes of a write
- `*` — match either direction (use sparingly; two separate rules are usually clearer)

**Register (Hex)** — the register index byte in hex (e.g. `0x14`). Leave blank for register-less (simple) transactions.

**Name** — a human-readable label shown in the Decode column, e.g. `Cell 1 Voltage`. Displayed as `Name = value unit`.

**Function Type** — controls how the data bytes are interpreted and displayed. Three options:

| Type | Description | Output |
|---|---|---|
| **Decimal** | Float arithmetic on the assembled integer `X` | `2800 mV` |
| **Hex** | Integer / bitwise / shift arithmetic on `X` | `0x0028` |
| **Bit Field** | Splits the value into named sub-fields | `[SLEEP=1 \| FET_EN=0 \| …]` |

**Unit** — the string appended to the result (e.g. `mV`, `degC`, `ADC codes`). Not used for Bit Field rules.

### Data Group

**Byte Order** — how multi-byte data values are assembled into the integer `X`:
- **Big Endian** — most-significant byte first (network order, default)
- **Little Endian** — least-significant byte first (common for many I2C sensors, including the BQ76905)

**2's Complement** — when checked, the assembled integer is treated as a signed two's-complement value. Use this for signed measurements such as temperature, current, or voltage difference.

**# Data Bytes** — how many bytes from the data phase to use. `0` (shown as `any`) accepts any length. Set this to the register's actual width (e.g. `2` for a 16-bit register) so the decoder trims correctly and formats the hex output width properly.

---

## Function Expressions

For **Decimal** and **Hex** function types, you write a math expression in the **Function** field. The operand `X` is the assembled integer value from the data bytes.

### Decimal Examples

```
X * 0.001           # raw counts → volts (e.g. 2800 → 2.8 V)
X * 0.1             # tenths of a degree → °C
X / 16              # fixed-point divide
X * 0.001 + 0.25    # scale with offset
```

Decimal output is rendered as a number stripped of trailing zeros, followed by the unit.

### Hex Examples

```
X                   # show the raw value as hex
(X >> 4) & 0x0F    # extract high nibble
X & 0x80            # isolate a flag bit
X << 2              # shift left
```

Hex output is shown as `0xNNNN` with width determined by `# Data Bytes`.

### Allowed Operators and Names

| Category | Allowed |
|---|---|
| Names | `X` (assembled value), `D` (alias for X), `B` (unsigned alias for bitwise) |
| Arithmetic | `+  -  *  /  //  %  **` |
| Bitwise | `&  \|  ^  ~  <<  >>` |
| Grouping | `( )` |
| Functions | `abs()  min()  max()  round()` |

Anything else (string literals, other function calls, comparison operators) is rejected for safety.

---

## Bit Field Rules

When **Function Type** is **Bit Field**, the data value's bits are sliced into named fields. This is used for status and control registers that pack multiple flags or multi-bit enumerations into one value.

### Adding a Field

Fill in the bit field entry row above the field table:

**High / Low** — the inclusive bit range. For a single bit, set both to the same value (e.g. High=7, Low=7). For a 3-bit field, e.g. High=2, Low=0.

**Mode** — how the field's extracted value is displayed:

| Mode | Use for | Spec format |
|---|---|---|
| `enum` | Named states (one name per possible value) | Comma-separated names, e.g. `Off, On` or `Sleep, Active, Error, Fault` |
| `scale` | Numeric values with a formula and unit | `function \| unit` or `function \| unit \| v=label,v=label` for special overrides |
| `raw` | Show the raw integer | Optional unit string |

**Field Name** — a label for the field (used by `scale` and `raw` modes, shown as `Name=value`). Optional for `enum` mode.

**Names / Function·Unit** — the spec string, format depends on mode (see table above).

Click **Add Field** to add the row to the field table. Click **Remove Field** to remove the selected row. Fields can be added in any order; the decoder sorts them high-bit-first when rendering.

### Enum Mode

A field spanning N bits needs exactly 2^N names, indexed by value. Examples:

| Bit width | Names needed | Example |
|---|---|---|
| 1 bit | 2 | `SLEEP=0, SLEEP=1` |
| 2 bits | 4 | `uninitialized, FULLACCESS, unused, SEALED` |
| 3 bits | 8 | `1.8V, 1.8V, 1.8V, 1.8V, 2.5V, 3.0V, 3.3V, 5V` |

### Scale Mode

The spec string has up to three pipe-separated parts: `function | unit | special`.

- `function` — expression on `X` (the field's extracted value), e.g. `X * 30.52`
- `unit` — unit string, e.g. `us`
- `special` — comma-separated `value=label` pairs that override the formula for specific values, e.g. `0=PWM disabled`

Full example: `X*30.52 | us | 0=PWM disabled`

---

## Testing a Rule

Before adding a rule, test it against sample data to confirm the expression and byte order are correct.

1. Fill in the rule fields (Address, Register, Function, Byte Order, etc.)
2. Type or paste sample hex bytes into the **test data** field (e.g. `F0 0A`)
3. Click **Test**

The result appears next to the button:

```
Cell 1 Voltage = 2800 mV
```

If the expression has a syntax error or the data is malformed, the error is shown in place of the result. Fix and re-test before clicking **Add / Update Rule**.

---

## Managing Rules

### Add / Update Rule

Click **Add / Update Rule** to save the current form into the in-memory schema. If a rule for the same (address, direction, register) already exists, it is replaced. The Schema Rules table refreshes immediately.

### Clear

Click **Clear** (next to Add / Update) to reset all form fields to their defaults without affecting the schema.

### Schema Rules Table

The table at the bottom shows all rules in the current schema:

| Column | Description |
|---|---|
| Address | 7-bit device address |
| Direction | R or W |
| Register | Register index, or blank for register-less |
| Data(Bytes) | Expected data byte count, or blank for any |
| Type | Decimal, Hex, or Bit Field |
| Name | Human label |
| Function / Fields | Expression or list of bit field ranges |
| Unit | Unit string |

**Click any row** to load that rule back into the form for editing. Modify the fields and click **Add / Update Rule** to save the changes.

**Remove Selected** — deletes the currently highlighted row from the schema.

**Clear All** — removes all rules after confirmation.

---

## File Operations

All file operations appear in the bottom bar of the Decoder tab.

### New

Clears the in-memory schema without saving. A confirmation prompt is not shown; unsaved changes are lost.

### Load…

Opens a file picker for a `.json` decoder file. The file is validated and loaded; the Schema Rules table repopulates. Any unsaved in-memory rules are replaced.

### Save

Saves to the currently open file. If no file is open (in-memory only), behaves like **Save As…**.

### Save As…

Opens a file picker and saves the schema to a new `.json` file. The title bar and status bar update to show the new path.

### Test Against Capture (CSV)…

Opens a file picker for a CSV sniffer capture and runs the current in-memory schema against it using the stream decoder. Results appear in a **Capture Decode Results** dialog:

- Summary line: total rows, how many decoded, how many had no matching rule
- **Show only rows with a decode result** checkbox (checked by default)
- Table with columns: `#`, `Dir`, `Register`, `Data (hex)`, `Decoded`

This is the fastest way to verify a decoder without launching the replay app.

---

## Decoder JSON Format

Decoder files follow the schema in `schema/decoder.schema.json`. Key top-level fields:

```json
{
  "version": 3,
  "device": "BQ76905",
  "description": "Optional description",
  "i2c_address": 8,
  "rules": [ ... ]
}
```

Each rule in the `rules` array:

```json
{
  "address": 8,
  "transaction_type": "indexed_read",
  "register": 20,
  "register_width_bytes": 1,
  "name": "Cell 1 Voltage",
  "unit": "mV",
  "function": "X",
  "byte_order": "le",
  "signed": true,
  "data_bytes": 2,
  "format": "dec"
}
```

### Transaction Types

| `transaction_type` | Description |
|---|---|
| `indexed_read` | Register pointer write → repeated-start → read data |
| `indexed_write` | Write where first byte is the register index |
| `simple_read` | Read with no preceding register pointer |
| `simple_write` | Write with no register byte (all bytes are data) |
| `subcommand` | BQ76905-style subcommand: write 16-bit code to a register, read response |
| `split_transaction` | Two-phase split across separate Start conditions |
| `general_call` | I2C broadcast (address 0x00) |
| `device_id_query` | I2C Device ID read (3 bytes) |

The editor's Direction dropdown maps to `indexed_read`/`indexed_write` when a register is present, and `simple_read`/`simple_write` when no register is set.

---

## Preferences Tab

Select a color theme and click **Apply Theme**. Available themes: System, Light, Dark, Engineering Dark, Iontra Dark, Iontra Light, Dark Claude.

---

## Help & Exit Tabs

**Help** — shows the project name, version, and last-updated date, then renders
this User Guide with the active theme (colored headings and code, bordered
tables). It re-renders when you change the theme in Preferences.

**Exit** — click **Close Application** to quit. If the decoder has unsaved edits,
you're prompted to **Save**, **Discard**, or **Cancel**. The window's close button
uses the same prompt.

---

## Troubleshooting

**"Add at least one bit field" warning**
The Function Type is set to Bit Field but no fields have been added to the table. Either add fields or switch the Function Type to Decimal or Hex.

**"Function error" on Test**
The expression contains a disallowed operator or name. Only `X`, `D`, `B`, arithmetic operators, bitwise operators, and `abs/min/max/round` are permitted.

**Enum field warning about wrong number of names**
A field spanning N bits requires exactly 2^N comma-separated names. Count the commas: a 2-bit field needs 4 names (3 commas).

**Rule not matching in replay or main tool**
- Confirm the address in the rule matches the capture exactly (7-bit format, e.g. `8` = `0x08`).
- Check that `register` matches the byte the device uses as an index (read from the datasheet, not the shifted 8-bit address).
- For Little Endian devices, verify Byte Order is set to Little Endian.
- For registers where data length varies, set `# Data Bytes` to the exact count or leave it at `any`.
