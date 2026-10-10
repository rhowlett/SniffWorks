"""
ui/widgets/section.py
[XREF: ui-section] A titled sidebar block: a QGroupBox with a vertical layout and
helpers to add horizontal "rows" of widgets (the line-1 / line-2 layout pattern
the app sidebars use). Consistent margins/spacing so stacked sections look
uniform across apps.
"""
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QWidget


class Section(QGroupBox):
    """A titled block for use inside a Sidebar."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(8, 8, 8, 8)
        self._v.setSpacing(6)

    def add_row(self, *widgets: QWidget, stretch_last: bool = False) -> QHBoxLayout:
        """
        Add one horizontal row of widgets and return its layout.

        By default a trailing stretch is added so the widgets align left (e.g.
        `[Clear Log] [Export CSV]`). Pass stretch_last=True to instead let the
        LAST widget expand to fill the row (e.g. a status label).
        """
        row = QHBoxLayout()
        row.setSpacing(6)
        n = len(widgets)
        for i, w in enumerate(widgets):
            factor = 1 if (stretch_last and i == n - 1) else 0
            row.addWidget(w, factor)
        if not stretch_last:
            row.addStretch(1)
        self._v.addLayout(row)
        return row

    def add_widget(self, w: QWidget) -> None:
        self._v.addWidget(w)

    def add_layout(self, layout) -> None:
        self._v.addLayout(layout)
