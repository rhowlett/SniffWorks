"""
ui/widgets/tab_popout.py
[XREF: tab-popout] Framework-standard tab pop-out: any tab in an app's main
QTabWidget can be floated into its own top-level window (right-click the tab
→ "Pop out", or double-click it) and re-docks at its original position when
the floating window is closed. Applied to every app via AppWindow and
attached explicitly by the non-AppWindow shells (decoder editor, theme
editor), so the behavior is identical everywhere.

Rules:
  * A tab is poppable unless its widget property "poppable" is False.
    AppWindow marks "Device" and "Exit" tabs non-poppable — connection
    control and the exit surface stay docked by design.
  * Floating preserves the widget and all its signal wiring (Qt connections
    are object-to-object), so live views (LogPanel, RegistersView) keep
    updating while floated, and the application stylesheet keeps theming
    them.
  * Closing the host window re-docks every float first, so teardown flows
    through the normal tab lifecycle and no orphan windows survive.

Host integration points:
  controller = TabPopoutController(tab_widget, host_window)
  controller.dock_all()                     # host close / bulk operations
  controller.floating_titles(prop=...)      # e.g. Registers-tab rebuilds
  controller.pop_out_by_title(title)        # re-float after a rebuild
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QEvent, Signal
from PySide6.QtWidgets import QTabWidget, QWidget, QMenu, QMainWindow


class TabPopoutController(QObject):
    """Owns the pop-out/re-dock lifecycle for one QTabWidget."""

    popped_out = Signal(str)      # tab title
    docked = Signal(str)          # tab title

    def __init__(self, tabs: QTabWidget, host: QMainWindow):
        super().__init__(host)
        self._tabs = tabs
        self._host = host
        # floating widget -> (original_index, title)
        self._floating: dict[QWidget, tuple[int, str]] = {}
        self._docking = False     # re-entrancy guard during dock()

        bar = tabs.tabBar()
        bar.setContextMenuPolicy(Qt.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._on_context_menu)
        bar.tabBarDoubleClicked.connect(self._on_double_click)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def is_poppable(widget: QWidget) -> bool:
        return widget is not None and widget.property("poppable") is not False

    def floating_widgets(self) -> list[QWidget]:
        return list(self._floating.keys())

    def floating_titles(self, prop: str = None) -> list[str]:
        """Titles of floating tabs, optionally only those whose widget has
        the given truthy property (e.g. 'registersTab')."""
        return [title for w, (_i, title) in self._floating.items()
                if prop is None or w.property(prop)]

    def is_floating(self, widget: QWidget) -> bool:
        return widget in self._floating

    # ------------------------------------------------------------------
    # Pop out
    # ------------------------------------------------------------------
    def pop_out(self, index: int) -> bool:
        widget = self._tabs.widget(index)
        if widget is None or not self.is_poppable(widget):
            return False
        title = self._tabs.tabText(index)
        size = widget.size()
        self._tabs.removeTab(index)

        widget.setParent(None)
        widget.setWindowFlag(Qt.Window, True)
        widget.setWindowTitle(f"{self._host.windowTitle()} — {title}")
        if size.isValid() and size.width() > 100:
            widget.resize(size)
        widget.installEventFilter(self)
        self._floating[widget] = (index, title)
        widget.show()
        widget.raise_()
        self.popped_out.emit(title)
        return True

    def pop_out_by_title(self, title: str) -> bool:
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == title:
                return self.pop_out(i)
        return False

    # ------------------------------------------------------------------
    # Dock back
    # ------------------------------------------------------------------
    def dock(self, widget: QWidget) -> bool:
        info = self._floating.pop(widget, None)
        if info is None:
            return False
        index, title = info
        self._docking = True
        try:
            widget.removeEventFilter(self)
            widget.hide()
            widget.setWindowFlag(Qt.Window, False)
            index = min(index, self._tabs.count())
            self._tabs.insertTab(index, widget, title)
            self._tabs.setCurrentIndex(index)
        finally:
            self._docking = False
        self.docked.emit(title)
        return True

    def dock_all(self, prop: str = None) -> None:
        """Re-dock every float (or only those with a truthy property).
        Docked in ascending original index so positions restore exactly."""
        targets = [w for w in self._floating
                   if prop is None or w.property(prop)]
        for w in sorted(targets, key=lambda w: self._floating[w][0]):
            self.dock(w)

    # ------------------------------------------------------------------
    # UI triggers
    # ------------------------------------------------------------------
    def _on_context_menu(self, pos):
        bar = self._tabs.tabBar()
        index = bar.tabAt(pos)
        if index < 0:
            return
        widget = self._tabs.widget(index)
        menu = QMenu(bar)
        act = menu.addAction(f"Pop out \u201C{self._tabs.tabText(index)}\u201D")
        act.setEnabled(self.is_poppable(widget))
        if menu.exec(bar.mapToGlobal(pos)) is act and act.isEnabled():
            self.pop_out(index)

    def _on_double_click(self, index: int):
        if index >= 0:
            self.pop_out(index)

    # ------------------------------------------------------------------
    # Float window close -> dock instead of destroy
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Close and obj in self._floating
                and not self._docking):
            event.ignore()
            self.dock(obj)
            return True
        return super().eventFilter(obj, event)
