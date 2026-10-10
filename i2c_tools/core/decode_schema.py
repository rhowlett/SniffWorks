"""
decode_schema.py
Human-readable decode schema for I2C transaction data.

A schema maps (address, direction) -> {unit, function}. When a transaction
matches, its data bytes are converted to a number and the function expression
is evaluated to produce a human-readable value, formatted as:

    "<function_value> <unit>"

Function expression operands
----------------------------
  X : the data interpreted as an integer from its HEX bytes (big-endian)
  D : the data interpreted as a decimal integer (same numeric value as X;
      provided so expressions read naturally) — supports + - * /
  B : the data interpreted for binary/bitwise operations — supports
      & | ^ ~ << >> and grouping

Examples
--------
  X*0.001+0.25      -> scale raw counts to volts with offset
  D/16              -> decimal divide
  (B>>4)&0x0F       -> extract a nibble
  B&0x80            -> test a flag bit

Only a safe subset of Python is permitted (numbers, the names X/D/B, the
operators above, parentheses, and the abs/min/max/round builtins). Anything
else raises a DecodeError.
"""
from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Tuple


class DecodeError(Exception):
    pass


# ---------------------------------------------------------------------------
# Safe expression evaluator
# ---------------------------------------------------------------------------
# Allowed binary operators
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Invert: operator.invert,
}
_FUNCS = {"abs": abs, "min": min, "max": max, "round": round}

# Operators that require integer operands (bitwise)
_BITWISE = {ast.BitAnd, ast.BitOr, ast.BitXor, ast.LShift, ast.RShift, ast.Invert}


def _eval_node(node, env: Dict[str, int]):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, env)

    # Numeric literal
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise DecodeError(f"Unsupported constant: {node.value!r}")

    # Variable name: X, D, or B
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise DecodeError(f"Unknown name '{node.id}' (only X, D, B allowed)")

    # Binary op
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise DecodeError(f"Operator {op_type.__name__} not permitted")
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        if op_type in _BITWISE:
            if not (float(left).is_integer() and float(right).is_integer()):
                raise DecodeError("Bitwise operators require integer operands (use B)")
            left, right = int(left), int(right)
        try:
            return _BIN_OPS[op_type](left, right)
        except ZeroDivisionError:
            raise DecodeError("Division by zero")

    # Unary op
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise DecodeError(f"Unary operator {op_type.__name__} not permitted")
        val = _eval_node(node.operand, env)
        if op_type is ast.Invert and not float(val).is_integer():
            raise DecodeError("Bitwise NOT requires an integer operand (use B)")
        return _UNARY_OPS[op_type](int(val) if op_type is ast.Invert else val)

    # Function call: abs/min/max/round only
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise DecodeError("Only abs, min, max, round calls are permitted")
        args = [_eval_node(a, env) for a in node.args]
        return _FUNCS[node.func.id](*args)

    raise DecodeError(f"Unsupported expression element: {type(node).__name__}")


def evaluate_function(expr: str, data: bytes,
                      byte_order: str = "be", signed: bool = False) -> float:
    """
    Evaluate a decode function expression against raw data bytes.

    byte_order : "be" (big-endian, default) or "le" (little-endian). Many I2C
                 register devices (e.g. BQ76905) place the low byte at the lower
                 register address, so the on-the-wire order is little-endian.
    signed     : if True, interpret the assembled integer as two's-complement.

    The expression operates on X = the assembled integer value. The rule's
    `format` decides how the result is presented:
      - Decimal : use float math (* / + -), e.g. "X*0.001", "X/16".
      - Hex     : use integer/logic/shift math (<< >> & | ^ ~ + -), shown 0xNN.
      - Bit Field: the function is usually just "X" (the raw value); the bits are
                   then sliced into named fields by the rule's bit_fields.
    (X, D and B all resolve to the same assembled value and remain accepted for
    backward compatibility; D/B exist only as aliases now.)
    """
    if not expr or not expr.strip():
        raise DecodeError("Empty function")

    order = "little" if str(byte_order).lower() in ("le", "little") else "big"
    int_val = int.from_bytes(data, byteorder=order, signed=signed) if data else 0
    # B (bitwise) always sees the unsigned form so masks/shifts behave predictably.
    uint_val = int.from_bytes(data, byteorder=order, signed=False) if data else 0
    env = {"X": int_val, "D": int_val, "B": uint_val}

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise DecodeError(f"Syntax error: {e.msg}")

    return _eval_node(tree, env)


# ---------------------------------------------------------------------------
# Schema entry + container
# ---------------------------------------------------------------------------
@dataclass
class BitField:
    """
    One named field within a bit-field decode, covering an inclusive bit range
    [high..low]. The field's `mode` decides how its raw value is rendered:

      - "enum"  : `names` enumerates every value (a field of N bits needs 2**N
                  names); names[value] is shown. (Default.)
      - "scale" : the value is fed through `function` (e.g. "X*122.1") and shown
                  with `unit`; `special` maps specific raw values to a label that
                  overrides the scaled output (e.g. {0: "PWM disabled"}).
      - "raw"   : the integer value is shown as-is (optionally with `unit`).

    `description` holds the datasheet text for the field (shown on hover/expand).
    """
    high: int
    low: int
    names: list = None              # for mode="enum"
    mode: str = "enum"              # "enum" | "scale" | "raw"
    function: str = "X"             # for mode="scale"
    unit: str = ""                  # for mode="scale"/"raw"
    special: dict = None            # for mode="scale": {raw_value: label}
    name: str = ""                  # field name (used by scale/raw)
    description: str = ""           # datasheet field description

    @property
    def width(self) -> int:
        return self.high - self.low + 1

    @property
    def expected_names(self) -> int:
        return 1 << self.width

    def value_of(self, raw: int) -> int:
        mask = ((1 << self.width) - 1) << self.low
        return (raw & mask) >> self.low

    def label(self, raw: int) -> str:
        v = self.value_of(raw)
        if self.mode == "scale":
            # Special-case override (e.g. 0 -> "PWM disabled").
            if self.special and v in self.special:
                lab = self.special[v]
                return f"{self.name}: {lab}" if self.name else lab
            try:
                val = evaluate_function(self.function or "X",
                                        v.to_bytes(8, "big"), byte_order="be",
                                        signed=False)
            except DecodeError:
                val = v
            if isinstance(val, float):
                txt = f"{val:.4f}".rstrip("0").rstrip(".")
            else:
                txt = str(val)
            body = f"{txt} {self.unit}".strip()
            return f"{self.name}={body}" if self.name else body
        if self.mode == "raw":
            body = f"{v} {self.unit}".strip()
            return f"{self.name}={body}" if self.name else body
        # enum (default)
        nm = self.names or []
        if 0 <= v < len(nm) and nm[v] != "":
            return nm[v]
        return f"[{self.high}:{self.low}]={v}"


@dataclass
class DataField:
    """
    One sub-field within a structured payload, addressed by BYTE offset (not bit
    range). Models the TRM's subcommand tables, which lay out a response as
    several independent values at fixed offsets, each with its own size, byte
    order, signedness and units (e.g. FW_VERSION = Device Number + FW Version +
    Build; PASSQ = PASSQLSB + PASSQMSB + PASSTIME).

    fmt controls rendering of the field's assembled value:
      - "dec"  : function result, decimal (default; function default "X")
      - "hex"  : function result as 0xNN, zero-padded to the field width
      - "raw"  : the integer value as-is
      - "ascii": the raw bytes as printable ASCII
      - "bits" : slice `bit_fields` out of the value (single-line)
    """
    name: str
    offset: int                 # byte offset within the payload buffer
    size: int                   # field width in bytes
    byte_order: str = "be"      # "be" | "le"
    signed: bool = False
    fmt: str = "dec"            # "dec" | "hex" | "raw" | "ascii" | "bits"
    function: str = "X"
    unit: str = ""
    bit_fields: Optional[list] = None
    description: str = ""


@dataclass
class DecodeRule:
    address: int               # 7-bit I2C device address
    transaction_type: str      # "indexed_read", "indexed_write", "subcommand", ...
    unit: str                  # e.g. "mV", "mm"
    function: str              # value expression (used for dec/hex; ignored for bits)
    register: Optional[int] = None  # register index; required for indexed_*/split
    register_width_bytes: int = 1   # 1/2/4 byte register index on the wire
    byte_order: str = "be"     # "be" or "le" for multi-byte value assembly
    signed: bool = False       # interpret value as two's-complement
    data_bytes: Optional[int] = None  # expected # of DATA bytes; None = any
    fmt: str = "dec"           # output format: "dec", "hex", or "bits"
    bit_fields: Optional[list] = None  # for fmt="bits": list[BitField]
    fields: Optional[list] = None      # structured payload: list[DataField] (offset-addressed)
    name: str = ""             # human label
    description: str = ""      # datasheet description (shown in replay/editor)
    # Subcommand support (transaction_type == "subcommand"):
    subcommand: Optional[int] = None       # 16-bit subcommand code (e.g. 0x0005)
    subcommand_reg: Optional[int] = None   # register the code is written to; sourced from the decoder JSON (e.g. 0x3E on BQ76905)
    access: str = ""                       # "R", "W", "R/W" — informational
    # Registers-tab layout (schema v4): scalar rules with a group appear in
    # the live Registers view; group_order sorts within the group.
    group: str = ""                        # display group name ("" = not shown)
    group_order: int = 0                   # order within the group

    @property
    def direction(self) -> str:
        """Direction derived from transaction type ('R' or 'W')."""
        if self.transaction_type in ("indexed_read", "simple_read",
                                     "split_transaction", "device_id_query"):
            return "R"
        if self.transaction_type == "subcommand":
            # subcommands are initiated by a write; data-returning ones also read
            return "W"
        return "W"

    def key(self):
        if self.transaction_type == "subcommand":
            return (self.address, self.subcommand, "subcommand")
        return (self.address, self.register, self.transaction_type)


class DecodeSchema:
    """
    Collection of decode rules keyed by (i2c_address, register, transaction_type).

    Transaction types follow the standard I2C taxonomy:
      - indexed_read   : S -> Addr+W -> Reg -> Sr -> Addr+R -> Data -> P
                         (Combined Write-Read; the dominant register-read shape).
                         The register comes from the write phase, data from the
                         read phase; ONE rule decodes the pair.
      - indexed_write  : S -> Addr+W -> Reg -> Data -> P
      - simple_read    : S -> Addr+R -> Data -> P            (no register)
      - simple_write   : S -> Addr+W -> Data -> P            (no register)
      - split_transaction, general_call, device_id_query     (see schema)

    Rules are looked up by (address, register, transaction_type). For indexed
    reads/writes the register is the index byte; for simple/general/device-id
    types the register is None.

    The helper `name_value_unit()` renders "Name = value unit" for output.
    """

    SCHEMA_VERSION = 4

    READ_TYPES = ("indexed_read", "simple_read", "split_transaction", "device_id_query")
    WRITE_TYPES = ("indexed_write", "simple_write", "general_call")

    def __init__(self):
        self._rules: Dict[Tuple[int, Optional[int], str], DecodeRule] = {}
        # When True, bit-field decodes render one field per line:
        #   "Name:\nBit.15 [SSA=0]\nBit.14 [SSB=0]..."  (used by the replay table)
        self.multiline_bits = False
        # Ordered Registers-tab layout (schema v4):
        #   [{"name": str, "kind": "banner"|"pane"}, ...]
        self.display_groups: list = []
        # Optional observer called from _render on every successful rule
        # match: on_rule_decoded(rule, full_value_bytes). Used by the
        # Registers tab's last-seen cache. [XREF: registers-tab]
        self.on_rule_decoded = None

    # --- rule management ---
    def add_rule(self, rule: DecodeRule):
        self._rules[rule.key()] = rule

    def remove_rule(self, address: int, transaction_type: str,
                    register: Optional[int] = None):
        self._rules.pop((address, register, transaction_type), None)

    def clear(self):
        self._rules.clear()

    def rules(self):
        return list(self._rules.values())

    def __len__(self):
        return len(self._rules)

    # --- lookup ---
    def find(self, address: int, transaction_type: str,
             register: Optional[int] = None) -> Optional[DecodeRule]:
        """Exact lookup by (address, register, transaction_type)."""
        return self._rules.get((address, register, transaction_type))

    def find_read(self, address: int, register: Optional[int]) -> Optional[DecodeRule]:
        """Find a read-side rule for a register, trying indexed then simple."""
        if register is not None:
            r = self._rules.get((address, register, "indexed_read"))
            if r:
                return r
            r = self._rules.get((address, register, "split_transaction"))
            if r:
                return r
        return self._rules.get((address, None, "simple_read"))

    def find_write(self, address: int, register: Optional[int]) -> Optional[DecodeRule]:
        """Find a write-side rule for a register, trying indexed then simple."""
        if register is not None:
            r = self._rules.get((address, register, "indexed_write"))
            if r:
                return r
        return self._rules.get((address, None, "simple_write"))

    def find_subcommand(self, address: int, code: int) -> Optional[DecodeRule]:
        """Find a subcommand rule by its 16-bit code."""
        return self._rules.get((address, code, "subcommand"))

    def decode_subcommand(self, address: int, code: int, data: bytes = b"",
                          block_framed: bool = False) -> str:
        """
        Decode a subcommand. `data` is the transfer-buffer payload for
        data-returning subcommands (empty for command-only subcommands).

        block_framed=True means `data` is a raw read that STARTED at the
        subcommand register (0x3E), so it is wrapped in the device's block
        framing: [echo_lo, echo_hi][32-byte transfer buffer 0x40-0x5F]
        [checksum 0x60][length 0x61]. The echo is stripped and, when the whole
        0x3E..0x61 frame was captured, the checksum/length are verified per the
        TRM; a mismatch is flagged in the output.
        """
        rule = self.find_subcommand(address, code)
        if rule is None:
            return ""
        if not data:
            return rule.name or f"Subcommand 0x{code:04X}"

        payload, note = (self._unwrap_subcommand_block(code, data)
                         if block_framed else (data, ""))

        has_spec = (rule.fields
                    or (rule.fmt == "bits" and rule.bit_fields)
                    or (rule.function or "").strip())
        if not has_spec:
            seg = payload[:rule.data_bytes] if rule.data_bytes else payload
            hexs = " ".join(f"{b:02X}" for b in seg)
            base = rule.name or f"Subcommand 0x{code:04X}"
            return f"{base} = {hexs}{note}"
        return self._render(rule, payload) + note

    @staticmethod
    def _unwrap_subcommand_block(code: int, data: bytes):
        """
        Strip the block framing from a subcommand read that started at the
        subcommand register. Returns (buffer_payload, note).

        Layout of a full read (0x3E..0x61, >=36 bytes):
            [0]     0x3E  subcommand echo, low byte
            [1]     0x3F  subcommand echo, high byte
            [2..33] 0x40..0x5F  32-byte transfer buffer
            [34]    0x60  checksum
            [35]    0x61  length  (= buffer-data length + 4)
        Per the TRM the checksum is the bitwise-NOT of the 8-bit sum of the two
        subcommand bytes plus the buffer bytes used; length counts 0x3E, 0x3F,
        0x60, 0x61 and the buffer data.
        """
        if len(data) < 2:
            return data, ""
        echo = data[0] | (data[1] << 8)
        if len(data) >= 36:
            chksum = data[34]
            length = data[35]
            n = max(0, min(length - 4, 32))          # declared buffer-data length
            calc = (~(sum(data[0:2]) + sum(data[2:2 + n]))) & 0xFF
            flags = []
            if echo != code:
                flags.append(f"echo 0x{echo:04X}≠0x{code:04X}")
            if calc != chksum:
                flags.append(f"chk 0x{calc:02X}≠0x{chksum:02X}")
            note = "" if not flags else "  ⚠ " + ", ".join(flags)
            return data[2:2 + n], note
        # Partial read (no trailing checksum/length captured): just drop the echo
        # and let the rule/field slicing bound the data.
        return data[2:], ""

    def decode_indexed_read(self, address: int, register: int, data: bytes) -> str:
        """Decode the data phase of an indexed read (register already known)."""
        rule = self.find_read(address, register)
        if rule is None:
            return ""
        return self._render(rule, data)

    def decode_indexed_write(self, address: int, register: int, data: bytes) -> str:
        """Decode the data bytes of an indexed write (register + value)."""
        rule = self.find_write(address, register)
        if rule is None:
            return ""
        return self._render(rule, data)

    def decode_simple(self, address: int, is_read: bool, data: bytes) -> str:
        """Decode a simple (register-less) read or write."""
        ttype = "simple_read" if is_read else "simple_write"
        rule = self._rules.get((address, None, ttype))
        if rule is None:
            return ""
        return self._render(rule, data)

    def extract_value(self, rule: "DecodeRule", value_bytes: bytes):
        """Engineering value for a rule's payload (Registers tab): applies
        the data_bytes trim and the rule function; bits/hex rules yield the
        raw assembled integer. Raises DecodeError on a bad expression."""
        if rule.data_bytes is not None and rule.data_bytes > 0:
            value_bytes = value_bytes[:rule.data_bytes]
        expr = rule.function.strip() if rule.function else ""
        if (rule.fmt or "").lower() in ("bits", "hex") and not expr:
            expr = "X"
        return evaluate_function(expr or "X", value_bytes,
                                 byte_order=rule.byte_order,
                                 signed=rule.signed)

    def _render(self, rule: "DecodeRule", value_bytes: bytes) -> str:
        """Apply a rule's trim + function + format -> 'Name = value unit'."""
        if self.on_rule_decoded is not None:
            try:
                self.on_rule_decoded(rule, bytes(value_bytes))
            except Exception:
                pass  # a cache/UI observer must never break decoding
        # Structured (offset-addressed) payloads render field-by-field. Dispatch
        # BEFORE any data_bytes slicing, since each field's offset indexes the
        # full payload buffer, not a front-truncated copy.
        if rule.fields:
            return self._render_fields(rule, value_bytes)
        if rule.data_bytes is not None and rule.data_bytes > 0:
            value_bytes = value_bytes[:rule.data_bytes]
        fmt = (rule.fmt or "dec").lower()
        # Bit-field rules decode the raw assembled value directly; a function is
        # optional (default "X" = raw value). dec/hex always use the function.
        expr = rule.function.strip() if rule.function else ""
        if fmt == "bits" and not expr:
            expr = "X"
        try:
            value = evaluate_function(
                expr or rule.function,
                value_bytes,
                byte_order=rule.byte_order, signed=rule.signed,
            )
        except DecodeError as e:
            return f"<err: {e}>"

        if fmt == "hex":
            ival = int(value)
            # width from declared data_bytes (2 hex digits per byte), min 2.
            width = (rule.data_bytes * 2) if rule.data_bytes else max(2, len(value_bytes) * 2)
            if ival < 0:
                text = f"-0x{-ival:0{width}X}"
            else:
                text = f"0x{ival:0{width}X}"
        elif fmt == "bits":
            ival = int(value)
            if self.multiline_bits:
                # One field per line, high bit first, with a name header.
                return self._format_bits_multiline(ival, rule.bit_fields, rule.name)
            text = self._format_bits(ival, rule.bit_fields)
        else:  # "dec"
            if isinstance(value, float):
                text = f"{value:.4f}".rstrip("0").rstrip(".")
            else:
                text = str(value)

        value_unit = f"{text} {rule.unit}".strip()
        if rule.name:
            return f"{rule.name} = {value_unit}"
        return value_unit

    def _render_fields(self, rule: "DecodeRule", payload: bytes) -> str:
        """
        Render a structured payload (rule.fields) as several offset-addressed
        values. In multi-line mode (Replay) each field is its own line under a
        name header; otherwise they are joined on one line.

            FW_VERSION:                    FW_VERSION: Device Number = 0x7605 |
            Device Number = 0x7605    vs.  FW Version = 0x0000 | Build Number = 0x0002
            FW Version = 0x0000
            Build Number = 0x0002
        """
        parts = [self._render_field(f, payload) for f in (rule.fields or [])]
        if self.multiline_bits:
            header = f"{rule.name}:" if rule.name else "Fields:"
            return "\n".join([header] + parts)
        body = " | ".join(parts)
        return f"{rule.name}: {body}" if rule.name else body

    def _render_field(self, field: "DataField", payload: bytes) -> str:
        """
        Render one DataField: slice payload[offset:offset+size], assemble per the
        field's byte order/signedness, and format per fmt -> 'name = value unit'.
        """
        size = max(1, int(field.size))
        off = max(0, int(field.offset))
        seg = payload[off:off + size]
        fmt = (field.fmt or "dec").lower()
        name = field.name or ""
        if len(seg) < size:
            # The payload doesn't cover this field (e.g. a 1-byte read of a
            # word register): say so rather than fabricating a value from
            # missing bytes (a VSYS "2880 mV" from an absent byte + offset
            # is worse than no answer).
            return f"{name} = — (byte not read)" if name else "—"

        if fmt == "ascii":
            text = "".join(chr(b) if 32 <= b < 127 else "." for b in seg)
            text = f'"{text}"'
        else:
            expr = (field.function or "X").strip() or "X"
            try:
                value = evaluate_function(
                    expr, seg, byte_order=field.byte_order, signed=field.signed,
                )
            except DecodeError as e:
                body = f"<err: {e}>"
                return f"{name} = {body}" if name else body
            if fmt == "hex":
                ival = int(value)
                width = size * 2
                text = (f"-0x{-ival:0{width}X}" if ival < 0
                        else f"0x{ival:0{width}X}")
            elif fmt == "raw":
                text = str(int(value))
            elif fmt == "bits":
                text = self._format_bits(int(value), field.bit_fields)
            else:  # "dec"
                if isinstance(value, float):
                    text = f"{value:.4f}".rstrip("0").rstrip(".")
                else:
                    text = str(value)

        body = f"{text} {field.unit}".strip()
        return f"{name} = {body}" if name else body

    @staticmethod
    def _format_bits_multiline(value: int, bit_fields: Optional[list],
                               name: str) -> str:
        """
        Render bit fields as a multi-line block, one field per line, high bit
        first:
            Name:
            Bit.15 [SSA=0]
            Bit.14 [SSB=0]
            ...
        Multi-bit fields show their range, e.g. "Bit.2:1 [Rest select]".
        """
        header = f"{name}:" if name else "Bit fields:"
        if not bit_fields:
            return f"{header}\n0b{value:b}"
        fields = sorted(bit_fields, key=lambda f: f.high, reverse=True)
        lines = [header]
        for f in fields:
            pos = f"Bit.{f.high}" if f.high == f.low else f"Bit.{f.high}:{f.low}"
            lines.append(f"{pos} [{f.label(value)}]")
        return "\n".join(lines)

    @staticmethod
    def _format_bits(value: int, bit_fields: Optional[list]) -> str:
        """
        Render named bit fields from an integer. Each BitField covers an
        inclusive [high..low] range and enumerates names for every value of that
        range; the name for the field's current value is shown. Output groups the
        fields high-to-low, e.g. "[CC select | Enable]". Falls back to a binary
        string when no fields are defined.
        """
        if not bit_fields:
            return f"0b{value:b}"
        fields = sorted(bit_fields, key=lambda f: f.high, reverse=True)
        parts = [f.label(value) for f in fields]
        return "[" + " | ".join(parts) + "]"

    # --- persistence ---
    def to_json(self) -> str:
        rules_out = []
        for r in self._rules.values():
            d = {
                "address": r.address,
                "transaction_type": r.transaction_type,
                "register": r.register,
                "register_width_bytes": r.register_width_bytes,
                "unit": r.unit,
                "function": r.function,
                "byte_order": r.byte_order,
                "signed": r.signed,
                "data_bytes": r.data_bytes,
                "format": r.fmt,
                "name": r.name,
            }
            if r.description:
                d["description"] = r.description
            if r.transaction_type == "subcommand":
                d["subcommand"] = r.subcommand
                d["subcommand_reg"] = r.subcommand_reg
            if r.access:
                d["access"] = r.access
            if r.group:
                d["group"] = r.group
                d["group_order"] = r.group_order
            if r.fmt == "bits" and r.bit_fields:
                d["bit_fields"] = self._bit_fields_to_json(r.bit_fields)
            if r.fields:
                d["fields"] = [self._data_field_to_json(f) for f in r.fields]
            rules_out.append(d)
        payload = {"version": self.SCHEMA_VERSION, "rules": rules_out}
        if self.display_groups:
            payload["display_groups"] = self.display_groups
        return json.dumps(payload, indent=2)

    @staticmethod
    def _bit_fields_to_json(bit_fields: list) -> list:
        """Serialize a list[BitField] to the JSON 'bit_fields' form."""
        out = []
        for bf in bit_fields:
            f = {"range": [bf.high, bf.low], "mode": bf.mode}
            if bf.name:
                f["name"] = bf.name
            if bf.mode == "enum":
                f["names"] = list(bf.names or [])
            elif bf.mode == "scale":
                f["function"] = bf.function
                if bf.unit:
                    f["unit"] = bf.unit
                if bf.special:
                    f["special"] = {str(k): v for k, v in bf.special.items()}
            elif bf.mode == "raw" and bf.unit:
                f["unit"] = bf.unit
            if bf.description:
                f["description"] = bf.description
            out.append(f)
        return out

    @classmethod
    def _data_field_to_json(cls, field: "DataField") -> dict:
        """Serialize one DataField to the JSON 'fields' entry form."""
        d = {
            "name": field.name,
            "offset": field.offset,
            "size": field.size,
            "byte_order": field.byte_order,
            "signed": field.signed,
            "format": field.fmt,
        }
        if (field.function or "X") != "X":
            d["function"] = field.function
        if field.unit:
            d["unit"] = field.unit
        if field.description:
            d["description"] = field.description
        if field.fmt == "bits" and field.bit_fields:
            d["bit_fields"] = cls._bit_fields_to_json(field.bit_fields)
        return d

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @staticmethod
    def _parse_bit_fields(raw_list) -> list:
        """Parse the JSON 'bit_fields' list form into list[BitField]."""
        out = []
        for bf in raw_list:
            rng = bf.get("range", [0, 0])
            hi, lo = int(rng[0]), int(rng[1])
            if hi < lo:
                hi, lo = lo, hi
            mode = str(bf.get("mode", "enum"))
            special = bf.get("special")
            if special:
                special = {int(k): v for k, v in special.items()}
            names = None
            if mode == "enum":
                names = list(bf.get("names", []))
                expected = 1 << (hi - lo + 1)
                if len(names) < expected:
                    names += [f"[{hi}:{lo}]={v}" for v in range(len(names), expected)]
            out.append(BitField(
                high=hi, low=lo, names=names, mode=mode,
                function=str(bf.get("function", "X")),
                unit=str(bf.get("unit", "")),
                special=special,
                name=str(bf.get("name", "")),
                description=str(bf.get("description", "")),
            ))
        return out

    @classmethod
    def _parse_fields(cls, raw_list) -> list:
        """Parse the JSON 'fields' list form into list[DataField]."""
        out = []
        for f in raw_list:
            nested = f.get("bit_fields")
            out.append(DataField(
                name=str(f.get("name", "")),
                offset=int(f.get("offset", 0)),
                size=int(f.get("size", 1)),
                byte_order=str(f.get("byte_order", "be")),
                signed=bool(f.get("signed", False)),
                fmt=str(f.get("format", f.get("fmt", "dec"))),
                function=str(f.get("function", "X")),
                unit=str(f.get("unit", "")),
                bit_fields=(cls._parse_bit_fields(nested) if nested else None),
                description=str(f.get("description", "")),
            ))
        return out

    @classmethod
    def from_json(cls, text: str) -> "DecodeSchema":
        schema = cls()
        data = json.loads(text)
        # v4: ordered Registers-tab groups. Tolerant of v3 files (absent).
        for g in data.get("display_groups", []) or []:
            if isinstance(g, dict) and g.get("name"):
                kind = g.get("kind", "pane")
                schema.display_groups.append(
                    {"name": str(g["name"]),
                     "kind": kind if kind in ("banner", "pane") else "pane"})
        for r in data.get("rules", []):
            reg = r.get("register", None)
            reg = int(reg) if reg is not None else None
            db = r.get("data_bytes", None)

            ttype = r.get("transaction_type")
            if not ttype:
                # Migrate v1/v2 rules (which used 'direction' + register) to the
                # transaction-type model.
                direction = str(r.get("direction", "R")).upper()
                if direction == "W":
                    ttype = "indexed_write" if reg is not None else "simple_write"
                else:
                    ttype = "indexed_read" if reg is not None else "simple_read"

            # Parse bit_fields (new list form) or migrate legacy bitfields dict.
            bit_fields = None
            if r.get("bit_fields"):
                bit_fields = cls._parse_bit_fields(r["bit_fields"])
            elif r.get("bitfields"):
                # Legacy {bit_or_range: name} flag map -> 2-name fields ["NAME=0","NAME=1"]
                bit_fields = []
                for k, nm in r["bitfields"].items():
                    ks = str(k)
                    if ":" in ks:
                        hi, lo = (int(x) for x in ks.split(":"))
                    else:
                        hi = lo = int(ks)
                    width = hi - lo + 1
                    names = [f"{nm}={v}" for v in range(1 << width)]
                    bit_fields.append(BitField(high=hi, low=lo, names=names))

            # Parse structured fields (offset-addressed payloads, e.g. the
            # BQ76905 FW_VERSION / PASSQ subcommand tables).
            fields = cls._parse_fields(r["fields"]) if r.get("fields") else None

            sc = r.get("subcommand")
            schema.add_rule(DecodeRule(
                address=int(r["address"]),
                transaction_type=str(ttype),
                unit=str(r.get("unit", "")),
                function=str(r.get("function", "")),
                register=reg,
                register_width_bytes=int(r.get("register_width_bytes", 1)),
                byte_order=str(r.get("byte_order", "be")),
                signed=bool(r.get("signed", False)),
                data_bytes=(int(db) if db is not None else None),
                fmt=str(r.get("format", r.get("fmt", "dec"))),
                bit_fields=bit_fields,
                fields=fields,
                name=str(r.get("name", "")),
                description=str(r.get("description", "")),
                subcommand=(int(sc) if sc is not None else None),
                subcommand_reg=(int(r["subcommand_reg"]) if r.get("subcommand_reg") is not None else None),
                access=str(r.get("access", "")),
                group=str(r.get("group", "")),
                group_order=int(r.get("group_order", 0)),
            ))
        return schema

    @classmethod
    def load(cls, filepath: str) -> "DecodeSchema":
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())


# ---------------------------------------------------------------------------
# Stream decoding: pair Combined Write-Read (Indexed Read) transactions
# ---------------------------------------------------------------------------
@dataclass
class StreamResult:
    """Result of feeding one physical transaction line to the StreamDecoder."""
    transaction_type: Optional[str]  # resolved type, or None if not classified
    register: Optional[int]          # register applied (or None)
    text: str                        # decoded "Name = value unit" or ""
    unpaired: bool = False           # True if this line couldn't be paired


class StreamDecoder:
    """
    Sequence-aware decoder that pairs the two physical lines of a Combined
    Write-Read (Indexed Register Read) into one logical decode, and decodes
    Indexed Writes inline.

    Per the I2C taxonomy:
      indexed_read : S -> Addr+W -> Reg -> Sr -> Addr+R -> Data -> P
                     Appears as two lines: a 1-byte WRITE with no Stop (the
                     register index), then a repeated-start READ (the data).
                     Both lines together are ONE indexed_read; the read line is
                     decoded against the register from the write line.
      indexed_write: S -> Addr+W -> Reg -> Data -> P
                     One line: first byte = register, rest = data.
      simple_read  : S -> Addr+R -> Data -> P            (register-less)
      simple_write : S -> Addr+W -> Data -> P            (register-less)

    feed() is called once per physical CSV/log line, in capture order. It returns
    a StreamResult describing how that line was classified and decoded. A pointer
    write (the W phase of an indexed read) returns text="" and stashes the
    register; the following read returns the decoded value. If a read arrives
    with no pending register and no simple_read rule, it is flagged unpaired.

    Subcommand protocol notes
    -------------------------
    Many devices (e.g. BQ76905) implement subcommands by writing a 16-bit LE
    code to a dedicated register (subcommand_reg, taken from the decoder JSON;
    e.g. 0x3E on BQ76905). A data-returning subcommand places its result in a
    32-byte transfer buffer (0x40..0x5F). The host reads it back by resetting the
    read pointer to the subcommand register and reading a block that begins with
    the 16-bit code echo (0x3E/0x3F), followed by the transfer buffer, then a
    checksum (0x60) and length (0x61). The read-back is therefore decoded with
    block_framed=True so the echo is stripped, the declared length bounds the
    data, and the checksum is verified. The decoder only stashes a pending
    subcommand when a known data-returning rule exists for that code, so unknown
    or command-only subcommands do not corrupt subsequent reads of that register.
    """

    def __init__(self, schema: DecodeSchema):
        self.schema = schema
        self._pending_reg: Dict[int, Optional[int]] = {}   # addr -> register awaiting a read
        self._pending_subcmd: Dict[int, Optional[int]] = {}  # addr -> subcommand code awaiting its read-back

    def reset(self):
        self._pending_reg.clear()
        self._pending_subcmd.clear()

    def _subcommand_reg(self, address: int) -> Optional[int]:
        """The register subcommand codes are written to for this address, taken
        from the address's subcommand rules in the decoder JSON. Returns None if
        the decoder defines no subcommand register for this address, in which
        case no subcommand pairing is attempted."""
        for rule in self.schema.rules():
            if (rule.transaction_type == "subcommand"
                    and rule.address == address
                    and rule.subcommand_reg is not None):
                return rule.subcommand_reg
        return None

    def _is_data_returning_subcommand(self, address: int, code: int) -> bool:
        """
        True when a known rule for this subcommand code has a data payload
        (data_bytes > 0 or bit_fields). Command-only subcommands (no data spec)
        do not need a read-back and must not poison the pending-subcommand state.
        """
        rule = self.schema.find_subcommand(address, code)
        if rule is None:
            return False
        has_data = (
            (rule.data_bytes is not None and rule.data_bytes > 0)
            or (rule.fmt == "bits" and rule.bit_fields)
            or bool(rule.fields)
            or bool((rule.function or "").strip())
        )
        return has_data

    @staticmethod
    def _is_pointer_write(data: bytes, had_stop: Optional[bool]) -> bool:
        """
        A register-pointer set: exactly one byte (the register index). Both
        forms are legal and observed in the field:
          * restart style: W [reg] (no Stop) -> Sr -> R ...   (BQ76905 host)
          * stop-separated: W [reg] P -> S -> R ...           (BQ25731 host)
        Register-map devices retain the pointer across STOP, so a single-byte
        write is a pointer set regardless of how the phase ended.
        """
        del had_stop  # retained for API compatibility; both forms qualify
        return len(data) == 1

    def feed(self, address: int, direction: str, data: bytes,
             had_stop: Optional[bool] = None,
             repeated_start: Optional[bool] = None) -> StreamResult:
        direction = (direction or "").upper()
        data = data or b""

        if direction == "W":
            if self._is_pointer_write(data, had_stop):
                # Register index for the indexed read that follows. Nothing to
                # decode yet; remember the register for the paired read.
                self._pending_reg[address] = data[0]
                return StreamResult(transaction_type="indexed_read",
                                    register=data[0], text="")
            if len(data) >= 2:
                # Indexed write: first byte = register, rest = data. The
                # device's pointer now sits at this register, so a following
                # plain read (read-back verify) decodes against it.
                reg = data[0]
                self._pending_reg[address] = reg
                # Subcommand write? The code is written to the subcommand reg
                # (subcommand_reg from the decoder JSON) as a 16-bit LE value.
                if reg == self._subcommand_reg(address) and len(data) >= 3:
                    code = data[1] | (data[2] << 8)
                    # Only track a pending read-back for known data-returning
                    # subcommands. Unknown or command-only subcommands produce
                    # no read-back, so stashing them would mis-decode the next
                    # ordinary read of the subcommand register.
                    if self._is_data_returning_subcommand(address, code):
                        self._pending_subcmd[address] = code
                    else:
                        self._pending_subcmd.pop(address, None)
                    text = self.schema.decode_subcommand(address, code, b"")
                    return StreamResult(transaction_type="subcommand",
                                        register=code, text=text)
                text = self.schema.decode_indexed_write(address, reg, data[1:])
                return StreamResult(transaction_type="indexed_write",
                                    register=reg, text=text)
            if len(data) == 1:
                # Single-byte write that ended with Stop: a simple 1-byte write.
                text = self.schema.decode_simple(address, is_read=False, data=data)
                return StreamResult(transaction_type="simple_write",
                                    register=None, text=text)
            # Zero-length write (e.g. address probe / ACK scan).
            return StreamResult(transaction_type="simple_write",
                                register=None, text="")

        if direction == "R":
            reg = self._pending_reg.pop(address, None)
            if reg is not None:
                # If a data-returning subcommand is pending and this read is from
                # the subcommand register (devices return data there, not a fixed
                # 0x40 buffer), decode it against the pending subcommand.
                pend = self._pending_subcmd.get(address)
                sub_reg = self._subcommand_reg(address)
                if pend is not None and sub_reg is not None:
                    # The pending subcommand persists until replaced by the
                    # next subcommand write (the device keeps its transfer
                    # buffer populated), so echo polls at 0x3E followed by a
                    # buffer read at 0x40 both decode. [XREF: subcmd-buffer]
                    if reg == sub_reg:
                        # Read starting at the subcommand register carries the
                        # block frame: [echo][buffer][checksum][length] (or a
                        # short echo poll). decode_subcommand strips/verifies.
                        text = self.schema.decode_subcommand(
                            address, pend, data, block_framed=True)
                        return StreamResult(transaction_type="subcommand",
                                            register=pend, text=text,
                                            unpaired=False)
                    if reg == sub_reg + 2:
                        # Read starting at the transfer buffer (0x40): raw
                        # payload, no frame (BQ769x2 TRM efficient flow).
                        text = self.schema.decode_subcommand(
                            address, pend, data, block_framed=False)
                        return StreamResult(transaction_type="subcommand",
                                            register=pend, text=text,
                                            unpaired=False)
                # Data phase of a correctly paired indexed read. It is "paired"
                # regardless of whether a decode rule exists for this register.
                text = self.schema.decode_indexed_read(address, reg, data)
                return StreamResult(transaction_type="indexed_read",
                                    register=reg, text=text, unpaired=False)
            # No pending register: try a simple_read rule.
            text = self.schema.decode_simple(address, is_read=True, data=data)
            if text:
                return StreamResult(transaction_type="simple_read",
                                    register=None, text=text)
            # A read with no register context and no simple_read rule: genuinely
            # unpaired (no preceding pointer write was seen).
            return StreamResult(transaction_type=None, register=None,
                                text="", unpaired=True)

        return StreamResult(transaction_type=None, register=None, text="")
