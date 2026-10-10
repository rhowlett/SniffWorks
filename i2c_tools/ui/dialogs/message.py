"""
ui.dialogs.message  [v0.1]
Consistent message-box helpers.
"""

from PySide6.QtWidgets import QMessageBox, QWidget
from typing import Optional


def warn(parent: Optional[QWidget], title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def error(parent: Optional[QWidget], title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def info(parent: Optional[QWidget], title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def confirm(parent: Optional[QWidget], title: str, text: str) -> bool:
    """OK/Cancel confirmation (owner, 2026-10-05: OK/Cancel, not Yes/No, in
    every app). Returns True only if the user chose OK. Used by every app's
    exit guard (ConfirmingCloseMixin) and other confirm-before-acting prompts."""
    return QMessageBox.question(
        parent, title, text,
        QMessageBox.Ok | QMessageBox.Cancel,
        QMessageBox.Ok,
    ) == QMessageBox.Ok
