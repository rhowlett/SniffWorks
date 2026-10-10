"""
ui.dialogs.file_dialogs
Consistent open/save dialogs. JSON is the common format across the tool, so
those filters live here in one place.
"""

from PySide6.QtWidgets import QFileDialog, QWidget
from typing import Optional

JSON_FILTER = "JSON files (*.json);;All files (*)"
CSV_FILTER = "CSV files (*.csv);;All files (*)"


def open_json(parent: Optional[QWidget], caption: str = "Open JSON",
              directory: str = "") -> Optional[str]:
    """Show an open dialog filtered to JSON. Returns the path or None."""
    path, _ = QFileDialog.getOpenFileName(parent, caption, directory, JSON_FILTER)
    return path or None


def save_json(parent: Optional[QWidget], caption: str = "Save JSON",
              suggested_name: str = "untitled.json",
              directory: str = "") -> Optional[str]:
    """Show a save dialog filtered to JSON. Returns the path or None."""
    start = f"{directory}/{suggested_name}" if directory else suggested_name
    path, _ = QFileDialog.getSaveFileName(parent, caption, start, JSON_FILTER)
    return path or None


def open_csv(parent: QWidget = None, caption: str = "Open Capture CSV",
             directory: str = "") -> "str | None":
    """Show an open dialog filtered to CSV. Returns the path or None."""
    path, _ = QFileDialog.getOpenFileName(parent, caption, directory, CSV_FILTER)
    return path or None
