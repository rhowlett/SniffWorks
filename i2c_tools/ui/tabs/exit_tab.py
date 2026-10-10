"""
ui/tabs/exit_tab.py  [v0.1]
[XREF: exit-tab] The shared Exit tab body: a note and a Close Application
button colored with the theme's action_disconnect token (via the
btnDisconnect object name). Emits exit_requested; the host window handles the
clean close (and any unsaved-changes confirmation) in its closeEvent, so the
tab and the window's close button share one code path.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal
from ui.widgets.buttons import icon_button, uniform_width

from ui.widgets.section import Section


class ExitTab(QWidget):
    exit_requested = Signal()

    def __init__(self, app_title: str, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        sec = Section("Exit")
        lead = QLabel(f"Close {app_title}.")
        lead.setWordWrap(True)
        sec.add_widget(lead)

        note = QLabel("You'll be asked to confirm if there are unsaved changes.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        sec.add_widget(note)

        btn = icon_button("Close Application", "close")   # [XREF: ui-buttons]
        uniform_width([btn], 140)
        # action_disconnect color from the active theme (named or file-based)
        btn.setObjectName("btnDisconnect")
        btn.clicked.connect(self.exit_requested)
        sec.add_row(btn)

        root.addWidget(sec)
        root.addStretch(1)
