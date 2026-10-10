"""
ui/widgets/sidebar.py
[XREF: ui-sidebar] A vertical column of Sections (the app sidebar) plus a helper
to compose a tab body = [sidebar | main content]. Used so every app's tabs share
the same side-column-of-sections layout.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from ui.widgets.section import Section


class Sidebar(QWidget):
    """A fixed-max-width vertical column that stacks Sections with uniform
    spacing. Call add_stretch() after the last section so sections stack at the
    top rather than expanding to fill."""

    DEFAULT_MAX_WIDTH = 340

    def __init__(self, max_width: int = DEFAULT_MAX_WIDTH, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(max_width)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(6, 6, 6, 6)
        self._v.setSpacing(8)

    def add_section(self, section: Section) -> Section:
        self._v.addWidget(section)
        return section

    def add_widget(self, w: QWidget) -> QWidget:
        self._v.addWidget(w)
        return w

    def add_stretch(self) -> None:
        self._v.addStretch(1)


def make_tab_body(sidebar: QWidget, main: QWidget,
                  sidebar_side: str = "left") -> QWidget:
    """
    Compose a tab body: the sidebar beside a main content widget (which gets the
    stretch). Returned widget is what you pass to QTabWidget.addTab().
    """
    body = QWidget()
    lay = QHBoxLayout(body)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    if sidebar_side == "right":
        lay.addWidget(main, 1)
        lay.addWidget(sidebar, 0)
    else:
        lay.addWidget(sidebar, 0)
        lay.addWidget(main, 1)
    return body
