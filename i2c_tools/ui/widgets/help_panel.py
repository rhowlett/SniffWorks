"""DEPRECATED — moved to ui/tabs/help_tab.py. This shim keeps old imports
working; new code should use `from ui.tabs import HelpTab`."""
from ui.common import app_info
from ui.tabs.help_tab import HelpTab


class HelpPanel(HelpTab):
    """Old app_key-based constructor, preserved for compatibility."""

    def __init__(self, app_key: str, parent=None):
        info = app_info.APPS[app_key]
        super().__init__(app_info.guide_path(app_key), info.title,
                         info.blurb, parent=parent)
