"""
ui/theme_config_loader.py
Loading, validation, and normalization of *.qt_theme.json files produced by
the theme editor (theme_editor.py, formerly pyside6_theme_playground.py).

Design rules (apply_qt_theme_prompt.md):
  * `palette` and `settings` are the source of truth; `generated_qss` is kept
    only as a reference/fallback and is never required.
  * Unknown/missing/invalid fields fall back to safe defaults - a theme file
    can never crash the app.
  * This module is pure Python (no Qt imports) so it is unit-testable
    headlessly; ui/theme.py turns normalized configs into QSS.

The canonical file schema lives in schema/qt_theme.schema.json.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

THEME_FILE_TYPE = "pyside6-theme-playground"
THEME_FILE_VERSION = 1
THEME_FILE_SUFFIX = ".qt_theme.json"

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# ---------------------------------------------------------------------------
# Known semantic palette tokens (superset shared with ui/theme.py palettes).
# Defaults are the app's 'default' theme so a sparse file still looks coherent.
# ---------------------------------------------------------------------------
DEFAULT_PALETTE: dict[str, str] = {
    "bg_primary": "#101216", "bg_secondary": "#171A20", "bg_tertiary": "#1F232B",
    "bg_selected": "#5E6AD2", "border_primary": "#2A2F3A",
    "text_primary": "#E2E4EA", "text_muted": "#8A8F9E", "text_inverse": "#FFFFFF",
    "accent_primary": "#5E6AD2",
    "action_connect": "#2EA36B", "action_disconnect": "#E5484D",
    "action_read": "#2EA36B", "action_write": "#3E8FDD",
    "action_write_read": "#8E6BE8", "action_scan": "#D98E32",
    "action_apply": "#5E6AD2", "action_text": "#FFFFFF",
    "status_idle": "#8A8F9E", "status_active": "#3DD68C",
    "status_error": "#E5484D", "status_warning": "#E2B93B",
    "data_read": "#3DD68C", "data_write": "#66A9E0",
    "data_nak": "#F27276", "data_pec_fail_bg": "#3A1D20",
    "save_dirty_bg": "#2EA36B", "save_dirty_hover": "#35B879",
    "save_dirty_text": "#FFFFFF",
    "section_heading_color": "#E2E4EA",
}

KNOWN_PALETTE_TOKENS = tuple(DEFAULT_PALETTE.keys())

# ---------------------------------------------------------------------------
# Known settings: name -> (default, type). Booleans/ints/strings are coerced;
# anything un-coercible falls back to the default.
# Enumerated settings additionally validate against allowed values.
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS: dict[str, Any] = {
    "qt_style": "Fusion",
    "document_mode": False,
    "tab_draw_base": True,
    "pane_border": True,
    "tab_qss_mode": "Styled QSS",
    "tab_pane_top_offset": -1,
    "selected_tab_margin_bottom": 0,
    "tab_position": "North",
    "tab_shape": "Rounded",
    "button_layout": "Mixed",
    "group_box_title_mode": "On Border",
    "font_family": "",
    "base_font_size": 10,
    "control_radius": 4,
    "input_min_height": 28,
    "input_v_padding": 4,
    "button_fixed_width": 130,
    "tab_padding_v": 6,
    "tab_padding_h": 12,
    "table_row_height": 26,
    "section_heading_size": 13,
    "section_heading_weight": 600,
}

SETTING_ENUMS: dict[str, tuple[str, ...]] = {
    "tab_qss_mode": ("Styled QSS", "Native / Unicode Finder"),
    "tab_position": ("North", "South", "West", "East"),
    "tab_shape": ("Rounded", "Triangular"),
    "group_box_title_mode": ("On Border", "Above Border"),
}

# sanity clamps for numeric settings: name -> (lo, hi)
SETTING_RANGES: dict[str, tuple[int, int]] = {
    "tab_pane_top_offset": (-20, 20),
    "selected_tab_margin_bottom": (-10, 10),
    "base_font_size": (6, 24),
    "control_radius": (0, 20),
    "input_min_height": (16, 64),
    "input_v_padding": (0, 16),
    "button_fixed_width": (40, 400),
    "tab_padding_v": (0, 24),
    "tab_padding_h": (0, 48),
    "table_row_height": (14, 64),
    "section_heading_size": (8, 32),
    "section_heading_weight": (100, 900),
}


class ThemeConfigError(Exception):
    """Raised when a theme file cannot be read or parsed at all.
    (Field-level problems never raise - they fall back to defaults.)"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_theme_config(path: str | Path) -> dict:
    """
    Read and normalize a *.qt_theme.json file.
    Raises ThemeConfigError on unreadable/unparsable files; any field-level
    problem is repaired with defaults (and logged).
    """
    p = Path(path)
    try:
        raw_text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ThemeConfigError(f"Cannot read theme file '{p}': {e}") from e
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ThemeConfigError(f"Theme file '{p}' is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ThemeConfigError(f"Theme file '{p}' must contain a JSON object")
    cfg = normalize_theme_config(raw)
    cfg["source_path"] = str(p)
    if not cfg.get("preset_name"):
        cfg["preset_name"] = _name_from_path(p)
    return cfg


def normalize_theme_config(raw: dict) -> dict:
    """
    Return a canonical config dict:
        {file_type, file_version, preset_name, settings, palette,
         generated_qss?}
    Every settings key and palette token is present and type-valid.
    """
    if not isinstance(raw, dict):
        raw = {}

    ftype = raw.get("file_type")
    if ftype != THEME_FILE_TYPE:
        log.warning("theme file_type is %r (expected %r) - loading anyway",
                    ftype, THEME_FILE_TYPE)
    fver = raw.get("file_version")
    if fver not in (None, THEME_FILE_VERSION):
        log.warning("theme file_version %r newer than supported %d - "
                    "unknown fields will be ignored", fver, THEME_FILE_VERSION)

    cfg: dict[str, Any] = {
        "file_type": THEME_FILE_TYPE,
        "file_version": THEME_FILE_VERSION,
        "preset_name": str(raw.get("preset_name") or "").strip(),
        "settings": _normalize_settings(raw.get("settings")),
        "palette": _normalize_palette(raw.get("palette")),
    }
    gen = raw.get("generated_qss")
    if isinstance(gen, str) and gen.strip():
        cfg["generated_qss"] = gen          # reference only, never required
    return cfg


def default_theme_config() -> dict:
    """A complete, valid config using all defaults."""
    return {
        "file_type": THEME_FILE_TYPE,
        "file_version": THEME_FILE_VERSION,
        "preset_name": "default",
        "settings": dict(DEFAULT_SETTINGS),
        "palette": dict(DEFAULT_PALETTE),
    }


def sanitize_hex_color(value: Any, fallback: str) -> str:
    """'#RRGGBB' (case-normalized) or the fallback."""
    if isinstance(value, str) and _HEX_COLOR_RE.match(value.strip()):
        return value.strip().upper()
    return fallback


# ---------------------------------------------------------------------------
# Theme file discovery (ui/themes/ is the project's default location)
# ---------------------------------------------------------------------------
def themes_dir() -> Path:
    """Default directory for saved themes: <app root>/ui/themes."""
    return Path(__file__).resolve().parent / "themes"


def discover_theme_files(directory: str | Path | None = None) -> list[Path]:
    """Sorted list of *.qt_theme.json files in the given (or default) dir."""
    d = Path(directory) if directory else themes_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir()
                  if p.is_file() and p.name.endswith(THEME_FILE_SUFFIX))


def theme_display_name(path: str | Path) -> str:
    """
    Human label for a theme file: its preset_name if quickly readable,
    else a cleaned-up filename.
    """
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        name = str(raw.get("preset_name") or "").strip()
        if name:
            return name
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return _name_from_path(p)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _name_from_path(p: Path) -> str:
    name = p.name
    if name.endswith(THEME_FILE_SUFFIX):
        name = name[: -len(THEME_FILE_SUFFIX)]
    return name.replace("_", " ").strip() or "custom theme"


def _normalize_palette(raw: Any) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, str] = {}
    for token, default in DEFAULT_PALETTE.items():
        value = sanitize_hex_color(src.get(token), default)
        if token in src and value != str(src.get(token, "")).strip().upper():
            log.warning("palette token %r invalid (%r) - using %s",
                        token, src.get(token), value)
        out[token] = value
    return out


def _coerce(value: Any, default: Any):
    """Coerce value to type(default); return None if impossible."""
    if isinstance(default, bool):                    # before int: bool is int!
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        return None
    if isinstance(default, int):
        try:
            if isinstance(value, bool):
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
    if isinstance(default, str):
        return value if isinstance(value, str) else None
    return None


def _normalize_settings(raw: Any) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for key, default in DEFAULT_SETTINGS.items():
        value = _coerce(src.get(key, default), default)
        if value is None:
            log.warning("setting %r invalid (%r) - using default %r",
                        key, src.get(key), default)
            value = default
        if key in SETTING_ENUMS and value not in SETTING_ENUMS[key]:
            log.warning("setting %r value %r not in %s - using default %r",
                        key, value, SETTING_ENUMS[key], default)
            value = default
        if key in SETTING_RANGES and isinstance(value, int):
            lo, hi = SETTING_RANGES[key]
            value = max(lo, min(hi, value))
        out[key] = value
    return out
