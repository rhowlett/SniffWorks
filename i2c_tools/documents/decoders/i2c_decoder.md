To help you accurately map out and name these patterns inside your I2C JSON schema, you need a list of I2C Bus Transaction Types (or Transfer Sequences).
In I2C, transactions are defined by the arrangement of START (S), REPEATED START (Sr), and STOP (P) conditions, combined with the direction of the Read/Write (R/W) bit.

Here is a list of the industry-standard names and structural breakdowns you can use for your schema keys:
## 1. Simple Data Transactions
These are the foundational single-direction sequences.

* Simple Write / Master Write
* Structure: [START] -> [Address + W] -> [Data Byte(s)] -> [STOP]
   * Use Case: Sending a one-off command byte, resetting a chip, or setting a configuration pointer without reading back.
* Simple Read / Master Read
* Structure: [START] -> [Address + R] -> [Data Byte(s) from Client] -> [STOP]
   * Use Case: Continuous reading from an streaming device (like a FIFO buffer or sequential ADC) where you do not need to specify an internal register index first.

## 2. Combined & Indexed Transactions
These use a Repeated START (Sr) to pivot direction without letting go of the bus hardware.

* Combined Write-Read / Indexed Register Read (This is how the raw trasaction look in the file)
* Structure: [START] -> [Address + W] -> [Register Index] -> [Repeated START] -> [Address + R] -> [Data Byte(s) from Client] -> [STOP]
   * Use Case: Reading a specific internal memory offset or configuration register.
* Combined Write-Write / Indexed Register Write
* Structure: [START] -> [Address + W] -> [Register Index] -> [Data Byte(s) to Write] -> [STOP]
   * Use Case: Standard method to write specific configuration parameters to a targeted chip register. (Note: This technically doesn't use a Repeated START because the direction doesn't change, but it is architecturally categorized alongside Indexed Reads).
* Split Transaction / Non-Combined Access
* Structure: [START] -> [Address + W] -> [Register Index] -> [STOP] || [START] -> [Address + R] -> [Data] -> [STOP]
   * Use Case: Multi-master environments or legacy operating systems (like older Linux I2C subsystems) that cannot support atomic Repeated START sequences and must drop the bus line between steps.

## 3. Advanced / Global Transactions
These are specialized sequences defined by the formal NXP/Philips I2C specification.

* General Call
* Structure: [START] -> [0x00 + W] -> [Command Byte] -> [STOP]
   * Use Case: Broadcasting a software reset or a mass configuration to all client devices on the bus simultaneously.
* Start Byte Sequence
* Structure: [START] -> [0x01] -> [Repeated START] -> [Normal I2C Frame...]
   * Use Case: Used to wake up slow, polling-based microcontrollers acting as I2C clients without forcing them to constantly process fast bus data.
* Device ID Read
* Structure: [START] -> [0xF8 + W] -> [Target Address] -> [Repeated START] -> [0xF9 + R] -> [3 Bytes Manufacturer/Part ID] -> [STOP]
   * Use Case: Querying a standard hardware signature block to auto-detect what model of chip is wired to the bus.
* High-Speed Master Code Phase
* Structure: [START] -> [0x00001XXX Master Code] -> [No ACK] -> [Repeated START] -> [High-Speed Data Loop...]
   * Use Case: Initiating a 3.4 Mbps high-speed mode transfer.

------------------------------
## Example JSON Schema Structure
If you are designing the property keys for your schema, organizing them by transaction flow or direction ensures clean validation rules:

``` json
{
  "type": "object",
  "properties": {
    "transaction_type": {
      "type": "string",
      "enum": [
        "simple_write",
        "simple_read",
        "indexed_read",
        "indexed_write",
        "split_transaction",
        "general_call",
        "device_id_query"
      ]
    }
  }
}
```

# Decoder JSON Schema

To cover all of these transaction types robustly, you can use JSON Schema's oneOf or allOf with if-then conditional logic. This architecture ensures that when a specific transaction_type is chosen, the schema strictly enforces the exact payload parameters required for that specific hardware sequence (like requiring a register_address only for indexed types).
Here is a comprehensive JSON Schema (Draft 7/2020-12 compatible) that models and enforces all the I2C transaction types discussed:

``` json
{
  "$schema": "https://json-schema.org",
  "title": "I2CBusTransaction",
  "description": "Defines and validates payload requirements for standard I2C bus transaction types.",
  "type": "object",
  "required": ["client_address", "transaction_type"],
  "properties": {
    "client_address": {
      "type": "integer",
      "description": "7-bit or 10-bit hardware address of the target client device.",
      "minimum": 0,
      "maximum": 1023
    },
    "transaction_type": {
      "type": "string",
      "enum": [
        "simple_write",
        "simple_read",
        "indexed_write",
        "indexed_read",
        "split_transaction",
        "general_call",
        "device_id_query"
      ]
    },
    "register_address": {
      "type": "integer",
      "description": "The internal register pointer/offset index on the client device.",
      "minimum": 0
    },
    "register_address_width_bytes": {
      "type": "integer",
      "description": "The byte width of the register address (e.g., 1 byte for 0x00, 2 bytes for 0x0000).",
      "enum":,
      "default": 1
    },
    "write_data": {
      "type": "array",
      "description": "An array of byte values to be written to the bus.",
      "items": {
        "type": "integer",
        "minimum": 0,
        "maximum": 255
      }
    },
    "read_length": {
      "type": "integer",
      "description": "The expected number of bytes to read from the client device.",
      "minimum": 1
    }
  },

  "allOf": [
    {
      "comment": "Rule 1: Simple Write requires a write payload, forbids read parameters.",
      "if": { "properties": { "transaction_type": { "const": "simple_write" } } },
      "then": {
        "required": ["write_data"],
        "properties": {
          "register_address": false,
          "read_length": false
        }
      }
    },
    {
      "comment": "Rule 2: Simple Read requires a read length, forbids write payloads and registers.",
      "if": { "properties": { "transaction_type": { "const": "simple_read" } } },
      "then": {
        "required": ["read_length"],
        "properties": {
          "register_address": false,
          "write_data": false
        }
      }
    },
    {
      "comment": "Rule 3: Indexed Write requires a register index AND data to write. Forbids read parameters.",
      "if": { "properties": { "transaction_type": { "const": "indexed_write" } } },
      "then": {
        "required": ["register_address", "write_data"],
        "properties": {
          "read_length": false
        }
      }
    },
    {
      "comment": "Rule 4: Indexed Read (Combined Write-Read) requires a register index AND a read length. Forbids data arrays.",
      "if": { "properties": { "transaction_type": { "const": "indexed_read" } } },
      "then": {
        "required": ["register_address", "read_length"],
        "properties": {
          "write_data": false
        }
      }
    },
    {
      "comment": "Rule 5: Split Transaction acts like an indexed read structurally, but signals driver to drop the bus.",
      "if": { "properties": { "transaction_type": { "const": "split_transaction" } } },
      "then": {
        "required": ["register_address", "read_length"],
        "properties": {
          "write_data": false
        }
      }
    },
    {
      "comment": "Rule 6: General Call forces target address to 0x00 global broadcast and requires broadcast data.",
      "if": { "properties": { "transaction_type": { "const": "general_call" } } },
      "then": {
        "required": ["write_data"],
        "properties": {
          "client_address": { "const": 0 },
          "register_address": false,
          "read_length": false
        }
      }
    },
    {
      "comment": "Rule 7: Device ID Query strictly reads the hardware signature block back. No write arrays allowed.",
      "if": { "properties": { "transaction_type": { "const": "device_id_query" } } },
      "then": {
        "properties": {
          "register_address": false,
          "write_data": false,
          "read_length": { "const": 3 }
        }
      }
    }
  ]
}
```

## Why This Design Works Well for I2C Tools:

   1. Prevents Fragmented Payloads: Setting fields to false inside the conditional then block (or utilizing not: { "required": [...] } depending on your engine preference) explicitly forces clean payloads. An API parser won't receive a confusing payload containing both write_data and read_length when a user executes a simple_read.
   2. Strict Hardware Enforcement: For general_call, the schema dynamically forces client_address to be exactly 0, matching the I2C physical layer specification block.
   3. Byte Width Tracking: Inclusion of register_address_width_bytes accommodates complex devices (like EEPROMs or modern smart sensors) which require 16-bit (2 byte) or 32-bit (4 byte) register indices before reading data.
