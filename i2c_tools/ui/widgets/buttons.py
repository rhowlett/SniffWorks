"""
ui/widgets/buttons.py  [v0.2]
[XREF: ui-buttons] One button style for the sniffer apps (owner, 2026-10-05):
compact buttons of a uniform width, left-aligned, each with an icon - never
bars that stretch across the window.

    icon_button("Refresh", "refresh")     -> QPushButton with the Qt icon
    button_row(b1, b2, b3)                -> left-aligned row, equal widths
    uniform_width([b1, b2], min_width)    -> equal widths without a row

Icons come from the active Qt style's standard set (no image files), so they
follow the platform and work in every theme.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QPushButton, QSizePolicy, QStyle,
)

# role -> standard pixmap
_ICONS = {
    "refresh":    QStyle.StandardPixmap.SP_BrowserReload,
    "connect":    QStyle.StandardPixmap.SP_DialogApplyButton,
    "disconnect": QStyle.StandardPixmap.SP_DialogCancelButton,
    "apply":      QStyle.StandardPixmap.SP_DialogApplyButton,
    "clear_bus":  QStyle.StandardPixmap.SP_DialogResetButton,
    "scan":       QStyle.StandardPixmap.SP_FileDialogContentsView,
    "self_test":  QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "clear":      QStyle.StandardPixmap.SP_DialogDiscardButton,
    "export":     QStyle.StandardPixmap.SP_DialogSaveButton,
    "add":        QStyle.StandardPixmap.SP_DialogOpenButton,
    "remove":     QStyle.StandardPixmap.SP_TrashIcon,
    "launch":     QStyle.StandardPixmap.SP_DesktopIcon,
    "browse":     QStyle.StandardPixmap.SP_DirOpenIcon,
    "editor":     QStyle.StandardPixmap.SP_DesktopIcon,
    "close":      QStyle.StandardPixmap.SP_DialogCloseButton,
    "devices":    QStyle.StandardPixmap.SP_DriveNetIcon,
}

DEFAULT_MIN_WIDTH = 120     # px; the common width of a uniform button row


def std_icon(role: str):
    style = QApplication.style()
    return style.standardIcon(_ICONS[role]) if style and role in _ICONS else None


def icon_button(text: str, role: str | None = None,
                object_name: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    if role:
        ico = std_icon(role)
        if ico is not None:
            btn.setIcon(ico)
    if object_name:
        btn.setObjectName(object_name)
    return btn


def uniform_width(buttons, min_width: int = DEFAULT_MIN_WIDTH) -> int:
    """Give every button the same width: the widest size hint or min_width."""
    w = max([min_width] + [b.sizeHint().width() for b in buttons])
    for b in buttons:
        b.setMinimumWidth(w)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return w


def button_row(*buttons, min_width: int = DEFAULT_MIN_WIDTH,
               uniform: bool = True) -> QHBoxLayout:
    """A left-aligned row of (by default) equal-width buttons."""
    row = QHBoxLayout()
    row.setSpacing(6)
    if uniform:
        uniform_width(buttons, min_width)
    for b in buttons:
        row.addWidget(b)
    row.addStretch(1)
    return row
