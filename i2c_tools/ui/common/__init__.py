"""
ui.common
Non-widget helpers shared across the AD2 I2C Tool and the standalone
decoder editor: hex parsing and JSON file I/O.
"""

from ui.common.hexutil import (
    parse_hex_bytes,
    parse_hex_int,
    parse_addr_7bit,
    parse_register_byte,
    HexParseError,
)
from ui.common.app_bootstrap import build_application
from ui.common.capture import decode_capture, load_capture_rows, CaptureRow, load_transactions

__all__ = [
    "parse_hex_bytes",
    "parse_hex_int",
    "parse_addr_7bit",
    "parse_register_byte",
    "HexParseError",
    "build_application",
    "decode_capture",
    "load_capture_rows",
    "load_transactions",
    "CaptureRow",
]
