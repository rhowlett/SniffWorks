"""
ui/widgets/file_picker.py
[XREF: file-picker] A reusable "select a file" row:

    <label>                    [Open]
    <status>   — one of:  "none" (muted) | "<name>  ✓ <msg>" (green)
                          | "<name>  ✗ <msg>" (red)

Validation is injected (open_fn + validator) so the widget stays UI-only and has
no core/schema dependency. Colors come from theme tokens via objectName
(statusOk / statusError / mutedLabel), so the row themes correctly.
"""
import os
from typing import Callable, Optional, Tuple

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal


class FilePickerRow(QWidget):
    """Emits file_selected(path) after a pick has been validated."""

    file_selected = Signal(str)

    def __init__(self, label: str,
                 open_fn: Callable[[QWidget], Optional[str]],
                 validator: Callable[[str], Tuple[bool, str]],
                 parent=None):
        super().__init__(parent)
        self._open_fn = open_fn
        self._validator = validator
        self._path: Optional[str] = None
        self._valid = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QLabel(label))
        row.addStretch(1)
        self._open_btn = QPushButton("Open")
        self._open_btn.clicked.connect(self._on_open)
        row.addWidget(self._open_btn)
        v.addLayout(row)

        self._status = QLabel("none")
        self._status.setObjectName("mutedLabel")
        self._status.setWordWrap(True)
        v.addWidget(self._status)

    # ------------------------------------------------------------------
    def _on_open(self):
        path = self._open_fn(self)
        if path:
            self.set_path(path)

    def set_path(self, path: str) -> None:
        """Select `path` programmatically, run the validator, update status, and
        emit file_selected."""
        self._path = path
        try:
            ok, msg = self._validator(path)
        except Exception as e:   # a broken validator must not crash the UI
            ok, msg = False, str(e)
        self._valid = bool(ok)

        name = os.path.basename(path)
        mark = "✓" if ok else "✗"
        self._status.setObjectName("statusOk" if ok else "statusError")
        self._status.setText(f"{name}  {mark} {msg}".rstrip() if msg
                             else f"{name}  {mark}")
        self._restyle(self._status)
        self.file_selected.emit(path)

    def clear(self) -> None:
        self._path = None
        self._valid = False
        self._status.setObjectName("mutedLabel")
        self._status.setText("none")
        self._restyle(self._status)

    @staticmethod
    def _restyle(w: QWidget) -> None:
        # Re-polish so a changed objectName picks up its QSS color immediately.
        w.style().unpolish(w)
        w.style().polish(w)

    # ------------------------------------------------------------------
    def path(self) -> Optional[str]:
        return self._path

    def is_valid(self) -> bool:
        return self._valid
