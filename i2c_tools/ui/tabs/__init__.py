"""
ui.tabs
The tab bodies every app shares: Preferences (theme selection), Help (About +
rendered User Guide), and Exit. Windows add these to their QTabWidget so all
apps present the same trailing tabs with one implementation.

    from ui.tabs import PreferencesTab, HelpTab, ExitTab
"""
from ui.tabs.preferences_tab import PreferencesTab
from ui.tabs.help_tab import HelpTab
from ui.tabs.exit_tab import ExitTab

__all__ = ["PreferencesTab", "HelpTab", "ExitTab"]
