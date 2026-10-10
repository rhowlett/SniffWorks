"""
ui.widgets.hex_line_edit
A QLineEdit specialized for hex input, with helpers to read parsed values.
Used for address, register, and data-byte fields.
"""

from PySide6.QtWidgets import QLineEdit
from typing import Optional

from ui.common.hexutil import (
    parse_hex_bytes, parse_addr_7bit, parse_register_byte, HexParseError,
)


class HexLineEdit(QLineEdit):
    """
    A line edit for hex entry. Provides typed accessors that raise
    HexParseError on invalid content, so callers get one consistent error type.
    """

    def __init__(self, text: str = "", placeholder: str = "", parent=None):
        super().__init__(text, parent)
        if placeholder:
            self.setPlaceholderText(placeholder)

    def bytes_value(self) -> bytes:
        """Parse the field as a sequence of hex bytes."""
        return parse_hex_bytes(self.text())

    def addr_value(self) -> int:
        """Parse the field as a 7-bit I2C address (0x00-0x7F)."""
        return parse_addr_7bit(self.text())

    def register_value(self) -> Optional[int]:
        """Parse the field as an optional register byte (blank -> None)."""
        return parse_register_byte(self.text())
