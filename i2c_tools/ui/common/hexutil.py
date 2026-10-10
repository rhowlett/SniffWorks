"""
ui.common.hexutil
Hex parsing helpers consolidated from the panels that previously each rolled
their own (decode_panel, rw_panel, log_panel). Accepts forms like
"0x14 0x0E", "14 0e", "14,0e".
"""

from typing import Optional


class HexParseError(ValueError):
    """Raised when a hex string cannot be parsed."""


def _normalize(text: str) -> str:
    return text.replace(",", " ").replace("0x", " ").replace("0X", " ").strip()


def parse_hex_bytes(text: str) -> bytes:
    """
    Parse a whitespace/comma-separated hex byte string into bytes.
    Empty input yields b"". Raises HexParseError on any invalid token or a
    value outside 0x00-0xFF.
    """
    norm = _normalize(text)
    if not norm:
        return b""
    out = bytearray()
    for tok in norm.split():
        try:
            val = int(tok, 16)
        except ValueError:
            raise HexParseError(f"'{tok}' is not valid hex")
        if not 0 <= val <= 0xFF:
            raise HexParseError(f"byte '{tok}' is out of range 0x00-0xFF")
        out.append(val)
    return bytes(out)


def parse_hex_int(text: str) -> int:
    """
    Parse a single hex integer (with or without 0x). Raises HexParseError if
    the text is blank or not valid hex.
    """
    t = text.strip()
    if not t:
        raise HexParseError("empty value")
    try:
        return int(t, 16)
    except ValueError:
        raise HexParseError(f"'{text}' is not valid hex")


def parse_addr_7bit(text: str) -> int:
    """Parse a 7-bit I2C address (0x00-0x7F). Raises HexParseError if invalid."""
    val = parse_hex_int(text)
    if not 0 <= val <= 0x7F:
        raise HexParseError("address must be 0x00-0x7F")
    return val


def parse_register_byte(text: str) -> Optional[int]:
    """
    Parse an optional register byte. Blank -> None (register-agnostic).
    Otherwise must be 0x00-0xFF. Raises HexParseError if non-blank and invalid.
    """
    if not text.strip():
        return None
    val = parse_hex_int(text)
    if not 0 <= val <= 0xFF:
        raise HexParseError("register must be 0x00-0xFF")
    return val
