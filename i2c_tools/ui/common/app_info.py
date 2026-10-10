"""
ui/common/app_info.py
[XREF: help-tab] Single source for project/app metadata shown in the Help tab, and
a loader that resolves + reads the matching documents/User_Guide*.md.
"""
from dataclasses import dataclass
from pathlib import Path

PROJECT = "AD2 I2C / SMBus Tool"
VERSION = "1.0.0"
UPDATED = "2026-07-02"
DESCRIPTION = (
    "A family of standalone PySide6 tools for sniffing, replaying, and decoding "
    "I2C / SMBus traffic captured with a Digilent Analog Discovery 2."
)

# documents/ lives at the project root (this file is ui/common/app_info.py).
_DOCS_DIR = Path(__file__).resolve().parents[2] / "documents"


@dataclass(frozen=True)
class AppInfo:
    title: str
    guide: str      # filename under documents/
    blurb: str


APPS = {
    "sniffer_ad2": AppInfo(
        title="AD2 Sniffer",
        guide="User_Guide_sniffer_ad2.md",
        blurb="Passive I2C/SMBus sniffer + logger (Device / Sniffer / Preferences).",
    ),
    "i2c_replay": AppInfo(
        title="AD2 I2C Replay",
        guide="User_Guide_i2c_replay.md",
        blurb="Replay a capture CSV against a decoder JSON — no hardware needed.",
    ),
    "sniffer_ion": AppInfo(
        title="Ion I2C Sniffer",
        guide="User_Guide_sniffer_ion.md",
        blurb="Passive I2C/SMBus sniffer using an STM32C0 probe over serial "
              "(Device / Sniffer / Preferences).",
    ),
    "decoder_editor": AppInfo(
        title="AD2 Decoder Editor",
        guide="User_Guide_decoder_editor.md",
        blurb="Create and edit decoder JSON files.",
    ),
}


def guide_path(app_key: str) -> Path:
    return _DOCS_DIR / APPS[app_key].guide


def read_guide(app_key: str) -> str:
    """Return the User Guide markdown, or a short fallback note if unavailable."""
    path = guide_path(app_key)
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return (f"# {APPS[app_key].title}\n\n"
                f"_User guide not found at_ `documents/{APPS[app_key].guide}`.\n\n"
                f"> {e}\n")
