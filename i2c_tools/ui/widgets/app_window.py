"""
ui/widgets/app_window.py
[XREF: app-shell] The common window frame for the apps: a top-positioned
QTabWidget (self.tabs) plus a status bar, matching i2c_replay and decoder_editor.
Opt-in — an app may subclass this or embed a QTabWidget directly; nothing forces
adoption.
"""
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from ui import theme

NOTIFY_MSECS = 4000     # one standard status-message timeout for all apps


class StatusBarNotifier:
    """Mixin for QMainWindow subclasses: one consistent status-bar message
    call. notify("...") shows for NOTIFY_MSECS; sticky=True stays until
    replaced."""

    def notify(self, message: str, sticky: bool = False) -> None:
        self.statusBar().showMessage(message, 0 if sticky else NOTIFY_MSECS)


class ConfirmingCloseMixin:
    """Mixin for QMainWindow subclasses: one closeEvent for every app.

    Override points (all optional):
      close_guard()   -> str | None  message for a Yes/No confirm, or None
      confirm_close() -> bool        replace the whole confirmation (e.g. a
                                     Save/Discard/Cancel flow)
      on_close()                     teardown after the close is accepted
    The Exit tab and the window close button share this one code path.
    """

    def close_guard(self):
        return None

    def confirm_close(self) -> bool:
        message = self.close_guard()
        if message is None:
            return True
        from ui import dialogs
        return dialogs.confirm(self, f"Exit {self.windowTitle()}", message)

    def on_close(self) -> None:
        pass

    def closeEvent(self, event):  # noqa: N802 (Qt naming)
        if not self.confirm_close():
            event.ignore()
            return
        self.on_close()
        event.accept()


class AppWindow(ConfirmingCloseMixin, StatusBarNotifier, QMainWindow):
    """Base frame: top tabs + status bar. Add tabs with add_tab()."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready")
        # Opt the main content tabs in to theme-file tab settings
        # (document mode, draw base, position, shape).
        theme.register_tab_widget(self.tabs)
        # [XREF: tab-popout] framework-standard pop-out on every app's tabs
        from ui.widgets.tab_popout import TabPopoutController
        self.popout = TabPopoutController(self.tabs, self)

    # Tabs that must stay docked: connection control and the exit surface.
    NON_POPPABLE_TITLES = ("Device", "Exit")

    def add_tab(self, widget: QWidget, title: str,
                poppable: bool = None) -> int:
        """Add a tab. poppable: None = by title rule (Device/Exit stay
        docked), or force with True/False. [XREF: tab-popout]"""
        if poppable is None:
            poppable = title not in self.NON_POPPABLE_TITLES
        widget.setProperty("poppable", bool(poppable))
        return self.tabs.addTab(widget, title)

    def closeEvent(self, event):  # noqa: N802
        super().closeEvent(event)          # ConfirmingCloseMixin guard first
        if event.isAccepted():
            # Re-dock floats so teardown flows through normal tab lifecycle
            self.popout.dock_all()         # [XREF: tab-popout]
