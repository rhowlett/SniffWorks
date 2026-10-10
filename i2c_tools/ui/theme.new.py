"""
theme.py - Theme application, section headings, and save-state button styling.

Applies the active theme from app_state.local_config.theme before the main
window is shown. Supports the themes defined in SpecGen_GUI_Theme.md and
provides helpers for the named specgen_section_heading style and the
dirty (unsaved-changes) Save button styling.
"""
from __future__ import annotations
import logging
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

log = logging.getLogger(__name__)

VALID_THEMES = {
    "system",
    "light",
    "dark",
    "engineering_dark",
    "iontra_dark",
    "iontra_light",
    "iontra_pricing_tool",
}

# ---------------------------------------------------------------------------
# Shared sizing tokens - apply to ALL themes. Change these in ONE place to
# resize every text box, dropdown, and spin box across the whole app.
#   input_min_height : minimum widget height in px (gives text vertical room)
#   input_v_padding  : top/bottom padding in px (keeps descenders from clipping)
# These are merged into every palette at apply_theme() time.
# ---------------------------------------------------------------------------
_SHARED_TOKENS: dict[str, str] = {
    "input_min_height": "28",
    "input_v_padding":  "4",
}

# ---------------------------------------------------------------------------
# Iontra brand color tokens.
# Source: Iontra Brand Color Guide.
# ---------------------------------------------------------------------------
_IONTRA: dict[str, str] = {
    # Primary brand colors
    "core_navy": "#002F6C",
    "core_navy_950": "#001634",
    "core_navy_900": "#002B62",
    "core_navy_700": "#004DB1",
    "core_yellow": "#FFC600",
    "core_yellow_50": "#FFF4CF",

    # Secondary brand colors
    "secondary_teal": "#00BCE1",
    "secondary_teal_700": "#00788F",
    "secondary_seafoam": "#49C5B1",

    # Accent colors
    "accent_green": "#007A33",
    "accent_green_hover": "#008537",
    "accent_red": "#D14124",

    # Neutrals
    "neutral_white": "#FFFFFF",
    "neutral_warm_50": "#FDFDF5",
    "neutral_warm_100": "#F7F6E9",
    "neutral_warm_200": "#F1F0DA",
    "neutral_warm_300": "#ECEACB",
    "neutral_warm_400": "#E6E4BC",
    "neutral_gray_300": "#D2D2CC",
    "neutral_gray_500": "#A8A8A3",
    "neutral_gray_700": "#535350",
    "neutral_gray_900": "#282827",
    "neutral_black": "#211E16",
}

# Per-theme palette subset needed for QSS. Extend with full palettes from
# SpecGen_GUI_Theme.md as needed. Each entry includes save-dirty and
# section-heading tokens. Extra logical tokens are safe: QSS ignores any
# palette keys it does not reference today, but they remain available to
# future widgets/templates.
_PALETTES: dict[str, dict] = {
    "light": {
        "bg_primary": "#FFFFFF", "text_primary": "#1A1A1A",
        "bg_secondary": "#F0F0F0", "bg_selected": "#0057B7",
        "text_inverse": "#FFFFFF", "border_primary": "#C8C8C8",
        "accent_primary": "#0057B7",
        "save_dirty_bg": "#1E7E34", "save_dirty_hover": "#218838",
        "save_dirty_text": "#FFFFFF",
        "section_heading_color": "#1A1A1A",
        "section_heading_size": "13", "section_heading_weight": "600",
    },
    "dark": {
        "bg_primary": "#1E1E1E", "text_primary": "#D4D4D4",
        "bg_secondary": "#252526", "bg_selected": "#0057B7",
        "text_inverse": "#FFFFFF", "border_primary": "#3C3C3C",
        "accent_primary": "#0057B7",
        "save_dirty_bg": "#2EA043", "save_dirty_hover": "#3FB950",
        "save_dirty_text": "#0D1117",
        "section_heading_color": "#E6E6E6",
        "section_heading_size": "13", "section_heading_weight": "600",
    },
    "engineering_dark": {
        "bg_primary": "#1A1D23", "text_primary": "#CDD6F4",
        "bg_secondary": "#1E2128", "bg_selected": "#89B4FA",
        "text_inverse": "#1A1D23", "border_primary": "#313244",
        "accent_primary": "#89B4FA",
        "save_dirty_bg": "#40A02B", "save_dirty_hover": "#4CB535",
        "save_dirty_text": "#11111B",
        "section_heading_color": "#CDD6F4",
        "section_heading_size": "13", "section_heading_weight": "600",
    },
    "iontra_dark": {
        # Dark Iontra UI: navy-first, with core yellow used for selection and
        # headings. This replaces the previous GitHub-like dark colors that did
        # not map to the Iontra brand palette.
        "bg_primary": _IONTRA["core_navy_950"],
        "text_primary": _IONTRA["neutral_warm_50"],
        "bg_secondary": _IONTRA["core_navy_900"],
        "bg_selected": _IONTRA["core_yellow"],
        "text_inverse": _IONTRA["core_navy"],
        "border_primary": _IONTRA["core_navy_700"],
        "accent_primary": _IONTRA["core_yellow"],
        "save_dirty_bg": _IONTRA["accent_green"],
        "save_dirty_hover": _IONTRA["accent_green_hover"],
        "save_dirty_text": _IONTRA["neutral_white"],
        "section_heading_color": _IONTRA["core_yellow"],
        "section_heading_size": "13", "section_heading_weight": "600",
    },
    "iontra_light": {
        # Light Iontra UI: warm neutral surfaces with navy text/action color.
        # This replaces non-brand blues and GitHub neutrals with Iontra guide
        # colors and avoids weak yellow-on-white default UI pairings.
        "bg_primary": _IONTRA["neutral_warm_50"],
        "text_primary": _IONTRA["core_navy"],
        "bg_secondary": _IONTRA["neutral_warm_100"],
        "bg_selected": _IONTRA["core_navy"],
        "text_inverse": _IONTRA["neutral_white"],
        "border_primary": _IONTRA["neutral_gray_300"],
        "accent_primary": _IONTRA["core_navy"],
        "save_dirty_bg": _IONTRA["accent_green"],
        "save_dirty_hover": _IONTRA["accent_green_hover"],
        "save_dirty_text": _IONTRA["neutral_white"],
        "section_heading_color": _IONTRA["core_navy"],
        "section_heading_size": "13", "section_heading_weight": "600",
    },
    "iontra_pricing_tool": {
        # Pricing Tool Setup theme.
        # The CSS-oriented logical names below are intentionally preserved so
        # the pricing/quote UI can map its stylesheet variables directly into
        # the PySide theme roles.
        "app_bg": _IONTRA["neutral_warm_50"],
        "card_bg": _IONTRA["neutral_white"],
        "card_border": _IONTRA["neutral_gray_300"],
        "text": _IONTRA["neutral_black"],
        "muted": _IONTRA["neutral_gray_700"],
        "heading": _IONTRA["core_navy"],
        "link": _IONTRA["core_navy_700"],
        "code_bg": _IONTRA["neutral_warm_100"],
        "code_border": _IONTRA["neutral_gray_300"],
        "inline_code_bg": _IONTRA["neutral_warm_200"],
        "quote_bg": _IONTRA["neutral_warm_100"],
        "quote_border": _IONTRA["core_yellow"],
        "table_border": _IONTRA["neutral_gray_300"],
        "table_header_bg": _IONTRA["neutral_warm_300"],
        "selection_bg": _IONTRA["core_navy"],
        "selection_text": _IONTRA["neutral_white"],

        # Existing QSS token mapping.
        "bg_primary": _IONTRA["neutral_warm_50"],       # app_bg
        "text_primary": _IONTRA["neutral_black"],      # text
        "bg_secondary": _IONTRA["neutral_white"],      # card_bg
        "bg_selected": _IONTRA["core_navy"],           # selection_bg
        "text_inverse": _IONTRA["neutral_white"],      # selection_text
        "border_primary": _IONTRA["neutral_gray_300"], # card_border
        "accent_primary": _IONTRA["core_navy_700"],    # link/action
        "save_dirty_bg": _IONTRA["accent_green"],
        "save_dirty_hover": _IONTRA["accent_green_hover"],
        "save_dirty_text": _IONTRA["neutral_white"],
        "section_heading_color": _IONTRA["core_navy"], # heading
        "section_heading_size": "13", "section_heading_weight": "600",
    },
}

_QSS_TEMPLATE = """
QMainWindow, QWidget {{ background-color: {bg_primary}; color: {text_primary}; }}
QListWidget {{ background-color: {bg_secondary}; }}
QListWidget::item:selected {{ background-color: {bg_selected}; color: {text_inverse}; }}

/* ---- Global input sizing -------------------------------------------------
   One rule sizes every text box, dropdown, and spin box across all themes.
   min-height (not a fixed height) plus vertical padding gives the font's
   ascenders and descenders room so text is never clipped, while still letting
   a widget grow if a larger font is used. Adjust {input_min_height} and
   {input_v_padding} in the palette to change this globally. */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
QDateTimeEdit, QPlainTextEdit, QAbstractSpinBox {{
    min-height: {input_min_height}px;
    padding-top: {input_v_padding}px;
    padding-bottom: {input_v_padding}px;
    padding-left: 4px;
    padding-right: 4px;
}}
QComboBox QAbstractItemView::item {{
    min-height: {input_min_height}px;
}}
QComboBox::drop-down {{
    min-height: {input_min_height}px;
}}

QLabel#specgenSectionHeading {{
    font-size: {section_heading_size}pt;
    font-weight: {section_heading_weight};
    color: {section_heading_color};
    margin-top: 8px;
    margin-bottom: 4px;
}}

QPushButton[saveDirty="true"] {{
    background-color: {save_dirty_bg};
    color: {save_dirty_text};
    font-weight: 600;
    border-radius: 3px;
    padding: 4px 12px;
}}
QPushButton[saveDirty="true"]:hover {{
    background-color: {save_dirty_hover};
}}
"""


def _resolve(theme_name: str) -> str:
    if theme_name == "system":
        return "dark"   # OS detection could refine this; default to dark
    if theme_name not in VALID_THEMES:
        return "dark"
    return theme_name


def apply_theme(theme_name: str) -> None:
    """Apply the named theme to the running QApplication."""
    app = QApplication.instance()
    if not app:
        return
    if theme_name not in VALID_THEMES:
        log.warning("Unknown theme '%s' - falling back to 'dark'", theme_name)
        theme_name = "dark"
    resolved = _resolve(theme_name)
    palette = _PALETTES.get(resolved, _PALETTES["dark"])
    # Merge shared sizing tokens (input heights/padding) into the palette so
    # the QSS template can reference them. Shared tokens apply to all themes.
    merged = {**_SHARED_TOKENS, **palette}
    app.setStyleSheet(_QSS_TEMPLATE.format(**merged))
    log.info("theme: %s applied", theme_name)


def make_section_heading(text: str) -> QLabel:
    """Create a QLabel styled as a specgen_section_heading."""
    label = QLabel(text)
    label.setObjectName("specgenSectionHeading")
    return label


def set_save_dirty(button: QPushButton, dirty: bool) -> None:
    """Toggle the dirty (unsaved-changes) green styling on a Save button."""
    button.setProperty("saveDirty", bool(dirty))
    style = button.style()
    if style:
        style.unpolish(button)
        style.polish(button)
