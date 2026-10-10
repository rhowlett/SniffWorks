"""
ui/common/settings_store.py
[XREF: settings] Persistent user settings shared by every app in the tool
family (theme selection, serial link parameters). One QSettings file for the
whole suite — a theme chosen in the sniffer is the theme the decoder editor
starts with.

Deliberately tiny: typed get/set over QSettings plus one subscriber that
persists theme selections. Apps read values at build time and write them on
change; there is no live sync between running apps (last writer wins), which
matches how the tools are used.

Test injection: set_store(SettingsStore(path)) points the module at an INI
file in a temp directory so tests never touch the real user settings.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings

# One file for the whole suite, independent of per-app applicationName.
_ORG = "Digilent AD2 Utils"
_SUITE = "ion_i2c_tool"

# Keys
KEY_THEME = "appearance/theme"          # named theme or "file:<path>"
KEY_BAUD = "serial/baud"                # int
KEY_LAST_PORT = "serial/last_port"      # str device name
KEY_DECODERS = "files/decoders"         # newline-joined decoder paths


class SettingsStore:
    def __init__(self, path: str | None = None):
        if path:
            self._qs = QSettings(path, QSettings.Format.IniFormat)
        else:
            self._qs = QSettings(_ORG, _SUITE)

    def get_str(self, key: str, default: str = "") -> str:
        v = self._qs.value(key, default)
        return str(v) if v is not None else default

    def get_int(self, key: str, default: int) -> int:
        try:
            return int(self._qs.value(key, default))
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value) -> None:
        self._qs.setValue(key, value)
        self._qs.sync()


_store: SettingsStore | None = None


def store() -> SettingsStore:
    global _store
    if _store is None:
        import os
        # Test isolation / portable override: point settings at a file.
        _store = SettingsStore(os.environ.get("ION_TOOL_SETTINGS"))
    return _store


def set_store(s: SettingsStore) -> None:
    """Replace the module store (tests point this at a temp INI file)."""
    global _store
    _store = s


# ---------------------------------------------------------------------------
# Theme persistence
# ---------------------------------------------------------------------------
_theme_hooked = False


def _persist_theme(selection: str) -> None:
    store().set(KEY_THEME, selection)


def hook_theme_persistence() -> None:
    """Persist every applied theme selection. Idempotent; called by
    build_application after the startup theme is applied so the initial
    apply itself is what gets recorded going forward."""
    global _theme_hooked
    if _theme_hooked:
        return
    from ui import theme
    theme.signals.changed.connect(_persist_theme)
    _theme_hooked = True


def saved_theme() -> str:
    return store().get_str(KEY_THEME, "")
