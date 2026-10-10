"""
ui.common.app_bootstrap
Shared QApplication construction so every entry point (the main tool and the
standalone decoder editor) configures high-DPI, metadata, and the initial
theme identically.
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui import theme
from ui.common import settings_store


def build_application(app_name: str,
                     version: str = None,
                     org: str = "Digilent AD2 Utils",
                     initial_theme: str = "default",
                     restore_theme: bool = True) -> QApplication:
    """
    Create (or reuse) the QApplication with consistent settings and apply the
    startup theme. Returns the QApplication instance.

    Theme startup order [XREF: settings]:
      1. apply initial_theme (the app's built-in default), then
      2. if restore_theme and a persisted selection exists, apply it on top —
         a persisted "file:<path>" whose file has gone missing is logged and
         leaves step 1's theme intact (apply_theme_file keeps current).
    Every subsequent apply is persisted via settings_store.
    """
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(app_name)
    if version is None:
        try:
            from version import PROJECT_VERSION
            version = PROJECT_VERSION
        except ImportError:          # running outside the project root
            version = "1.0.0"
    app.setApplicationVersion(version)
    app.setOrganizationName(org)

    theme.apply_theme(initial_theme)
    if restore_theme:
        saved = settings_store.saved_theme()
        if saved and saved != initial_theme:
            theme.apply_theme(saved)
    settings_store.hook_theme_persistence()
    return app
