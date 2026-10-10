"""
theme.py — Single source of truth for all GUI colors and theming.

Every color in the application is derived from a named token in one of the
palettes below. Widgets are styled through the global QSS template; code that
needs QColor objects (e.g. the log table model) reads the active palette via
get_color() / active_palette().

Semantic token groups
----------------------
Surfaces : bg_primary, bg_secondary, bg_tertiary, bg_selected, border_primary
Text     : text_primary, text_muted, text_inverse, heading
Accent   : accent_primary
Actions  : action_connect / action_disconnect / action_read / action_write /
           action_write_read / action_scan / action_apply  (+ action_text)
Status   : status_idle, status_active, status_error, status_warning
Data     : data_read, data_write, data_nak, data_pec_fail_bg  (log table cells)
Save     : save_dirty_bg / save_dirty_hover / save_dirty_text
Heading  : section_heading_color / _size / _weight
"""
from __future__ import annotations
import logging
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtGui import QColor

log = logging.getLogger(__name__)

VALID_THEMES = {"system", "light", "dark",
                "engineering_dark", "iontra_dark", "iontra_light",
                "dark_claude"}

# Human-readable labels + ordering for the Preferences tab.
THEME_CHOICES = [
    ("system",           "System (follows OS, defaults to dark)"),
    ("light",            "Light"),
    ("dark",             "Dark"),
    ("engineering_dark", "Engineering Dark"),
    ("iontra_dark",      "Iontra Dark"),
    ("iontra_light",     "Iontra Light"),
    ("dark_claude",      "Dark Claude"),
]

# ---------------------------------------------------------------------------
# Shared sizing tokens — apply to ALL themes. Change these in ONE place to
# resize every text box, dropdown, and spin box across the whole app.
# ---------------------------------------------------------------------------
_SHARED_TOKENS: dict[str, str] = {
    "input_min_height": "28",
    "input_v_padding":  "4",
}

# ---------------------------------------------------------------------------
# Palettes. Every palette defines the FULL semantic token set so the QSS
# template and the model resolve cleanly for any theme.
# ---------------------------------------------------------------------------
_PALETTES: dict[str, dict] = {
    "light": {
        "bg_primary": "#FFFFFF", "bg_secondary": "#F0F0F0", "bg_tertiary": "#E4E4E4",
        "bg_selected": "#0057B7", "border_primary": "#C8C8C8",
        "text_primary": "#1A1A1A", "text_muted": "#6B6B6B", "text_inverse": "#FFFFFF",
        "accent_primary": "#0057B7",
        "action_connect": "#1E7E34", "action_disconnect": "#C0392B",
        "action_read": "#1E7E34", "action_write": "#2563B7",
        "action_write_read": "#7D3C98", "action_scan": "#C87410",
        "action_apply": "#0057B7", "action_text": "#FFFFFF",
        "status_idle": "#6B6B6B", "status_active": "#1E7E34",
        "status_error": "#C0392B", "status_warning": "#B9770E",
        "data_read": "#1E7E34", "data_write": "#2563B7",
        "data_nak": "#C0392B", "data_pec_fail_bg": "#F8D7DA",
        "save_dirty_bg": "#1E7E34", "save_dirty_hover": "#218838", "save_dirty_text": "#FFFFFF",
        "section_heading_color": "#1A1A1A", "section_heading_size": "13", "section_heading_weight": "600",
    },
    "dark": {
        "bg_primary": "#1E1E1E", "bg_secondary": "#252526", "bg_tertiary": "#2D2D30",
        "bg_selected": "#0057B7", "border_primary": "#3C3C3C",
        "text_primary": "#D4D4D4", "text_muted": "#9D9D9D", "text_inverse": "#FFFFFF",
        "accent_primary": "#0057B7",
        "action_connect": "#2EA043", "action_disconnect": "#E74C3C",
        "action_read": "#2EA043", "action_write": "#2980B9",
        "action_write_read": "#8E44AD", "action_scan": "#E67E22",
        "action_apply": "#0057B7", "action_text": "#FFFFFF",
        "status_idle": "#9D9D9D", "status_active": "#2ECC71",
        "status_error": "#E74C3C", "status_warning": "#F39C12",
        "data_read": "#2ECC71", "data_write": "#3FA0DC",
        "data_nak": "#E74C3C", "data_pec_fail_bg": "#4A0000",
        "save_dirty_bg": "#2EA043", "save_dirty_hover": "#3FB950", "save_dirty_text": "#0D1117",
        "section_heading_color": "#E6E6E6", "section_heading_size": "13", "section_heading_weight": "600",
    },
    "engineering_dark": {
        "bg_primary": "#1A1D23", "bg_secondary": "#1E2128", "bg_tertiary": "#262A33",
        "bg_selected": "#89B4FA", "border_primary": "#313244",
        "text_primary": "#CDD6F4", "text_muted": "#9399B2", "text_inverse": "#1A1D23",
        "accent_primary": "#89B4FA",
        "action_connect": "#40A02B", "action_disconnect": "#E64553",
        "action_read": "#40A02B", "action_write": "#1E66F5",
        "action_write_read": "#8839EF", "action_scan": "#FE640B",
        "action_apply": "#89B4FA", "action_text": "#11111B",
        "status_idle": "#9399B2", "status_active": "#40A02B",
        "status_error": "#E64553", "status_warning": "#DF8E1D",
        "data_read": "#A6E3A1", "data_write": "#89B4FA",
        "data_nak": "#F38BA8", "data_pec_fail_bg": "#45161D",
        "save_dirty_bg": "#40A02B", "save_dirty_hover": "#4CB535", "save_dirty_text": "#11111B",
        "section_heading_color": "#CDD6F4", "section_heading_size": "13", "section_heading_weight": "600",
    },
    "iontra_dark": {
        "bg_primary": "#0D1117", "bg_secondary": "#161B22", "bg_tertiary": "#1C232C",
        "bg_selected": "#238636", "border_primary": "#30363D",
        "text_primary": "#E6EDF3", "text_muted": "#8B949E", "text_inverse": "#FFFFFF",
        "accent_primary": "#00D4FF",
        "action_connect": "#238636", "action_disconnect": "#DA3633",
        "action_read": "#238636", "action_write": "#1F6FEB",
        "action_write_read": "#8957E5", "action_scan": "#DB6D28",
        "action_apply": "#00D4FF", "action_text": "#0D1117",
        "status_idle": "#8B949E", "status_active": "#3FB950",
        "status_error": "#DA3633", "status_warning": "#D29922",
        "data_read": "#3FB950", "data_write": "#58A6FF",
        "data_nak": "#F85149", "data_pec_fail_bg": "#3D1416",
        "save_dirty_bg": "#00D4A0", "save_dirty_hover": "#00E8B0", "save_dirty_text": "#0D1117",
        "section_heading_color": "#E6EDF3", "section_heading_size": "13", "section_heading_weight": "600",
    },
    "iontra_light": {
        "bg_primary": "#FFFFFF", "bg_secondary": "#F6F8FA", "bg_tertiary": "#EAEEF2",
        "bg_selected": "#218BFF", "border_primary": "#D0D7DE",
        "text_primary": "#24292F", "text_muted": "#656D76", "text_inverse": "#FFFFFF",
        "accent_primary": "#007CA3",
        "action_connect": "#0A7A2A", "action_disconnect": "#CF222E",
        "action_read": "#0A7A2A", "action_write": "#0969DA",
        "action_write_read": "#8250DF", "action_scan": "#BC4C00",
        "action_apply": "#007CA3", "action_text": "#FFFFFF",
        "status_idle": "#656D76", "status_active": "#0A7A2A",
        "status_error": "#CF222E", "status_warning": "#9A6700",
        "data_read": "#0A7A2A", "data_write": "#0969DA",
        "data_nak": "#CF222E", "data_pec_fail_bg": "#FFEBE9",
        "save_dirty_bg": "#0A7A2A", "save_dirty_hover": "#0C8F31", "save_dirty_text": "#FFFFFF",
        "section_heading_color": "#24292F", "section_heading_size": "13", "section_heading_weight": "600",
    },
    # -----------------------------------------------------------------------
    # dark_claude — warm, low-glare dark theme inspired by Claude's palette
    # (terracotta/clay accent on a near-black warm grey).
    # -----------------------------------------------------------------------
    "dark_claude": {
        "bg_primary": "#262624", "bg_secondary": "#2F2E2B", "bg_tertiary": "#3A3936",
        "bg_selected": "#C96442", "border_primary": "#46453F",
        "text_primary": "#F5F4EE", "text_muted": "#A8A49A", "text_inverse": "#1F1E1C",
        "accent_primary": "#C96442",
        "action_connect": "#5C8A4A", "action_disconnect": "#C0563E",
        "action_read": "#5C8A4A", "action_write": "#4A7DA8",
        "action_write_read": "#9A6BB0", "action_scan": "#C9874A",
        "action_apply": "#C96442", "action_text": "#1F1E1C",
        "status_idle": "#A8A49A", "status_active": "#7FB069",
        "status_error": "#D9785E", "status_warning": "#E0A458",
        "data_read": "#7FB069", "data_write": "#6FA8D0",
        "data_nak": "#D9785E", "data_pec_fail_bg": "#3F2420",
        "save_dirty_bg": "#5C8A4A", "save_dirty_hover": "#6B9E57", "save_dirty_text": "#1F1E1C",
        "section_heading_color": "#F5F4EE", "section_heading_size": "13", "section_heading_weight": "600",
    },
}

_QSS_TEMPLATE = """
QMainWindow, QWidget {{ background-color: {bg_primary}; color: {text_primary}; }}

QGroupBox {{
    border: 1px solid {border_primary};
    border-radius: 4px;
    margin-top: 8px;
    font-weight: bold;
    color: {accent_primary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

QTabWidget::pane {{ border: 1px solid {border_primary}; }}
QTabBar::tab {{
    background: {bg_secondary};
    color: {text_primary};
    padding: 6px 12px;
    border: 1px solid {border_primary};
}}
QTabBar::tab:selected {{
    background: {bg_tertiary};
    color: {accent_primary};
}}

QListWidget {{ background-color: {bg_secondary}; }}
QListWidget::item:selected {{ background-color: {bg_selected}; color: {text_inverse}; }}

QTableView {{
    background-color: {bg_secondary};
    alternate-background-color: {bg_primary};
    color: {text_primary};
    gridline-color: {border_primary};
    selection-background-color: {bg_tertiary};
}}
QHeaderView::section {{
    background-color: {bg_tertiary};
    color: {accent_primary};
    border: 1px solid {border_primary};
    padding: 3px;
    font-weight: bold;
}}
QTableWidget {{
    background-color: {bg_secondary};
    color: {text_primary};
    gridline-color: {border_primary};
}}

/* ---- Global input sizing ---------------------------------------------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
QDateTimeEdit, QPlainTextEdit, QAbstractSpinBox {{
    background-color: {bg_tertiary};
    color: {text_primary};
    border: 1px solid {border_primary};
    border-radius: 3px;
    min-height: {input_min_height}px;
    padding-top: {input_v_padding}px;
    padding-bottom: {input_v_padding}px;
    padding-left: 4px;
    padding-right: 4px;
}}
QComboBox QAbstractItemView {{
    background: {bg_tertiary};
    color: {text_primary};
    selection-background-color: {bg_selected};
    selection-color: {text_inverse};
}}
QComboBox QAbstractItemView::item {{ min-height: {input_min_height}px; }}
QComboBox::drop-down {{ border: none; min-height: {input_min_height}px; }}

QTextEdit {{
    background-color: {bg_secondary};
    color: {text_primary};
    border: 1px solid {border_primary};
}}

QPushButton {{
    background-color: {bg_tertiary};
    color: {text_primary};
    border: 1px solid {border_primary};
    border-radius: 4px;
    padding: 5px 10px;
}}
QPushButton:hover {{ background-color: {bg_selected}; color: {text_inverse}; }}
QPushButton:disabled {{ color: {text_muted}; border-color: {border_primary}; }}

/* ---- Named action buttons (set via objectName) ------------------------ */
QPushButton#btnConnect    {{ background-color: {action_connect};     color: {action_text}; font-weight: bold; }}
QPushButton#btnDisconnect {{ background-color: {action_disconnect};  color: {action_text}; }}
QPushButton#btnRead       {{ background-color: {action_read};        color: {action_text}; font-weight: bold; }}
QPushButton#btnWrite      {{ background-color: {action_write};       color: {action_text}; font-weight: bold; }}
QPushButton#btnWriteRead  {{ background-color: {action_write_read};  color: {action_text}; font-weight: bold; }}
QPushButton#btnScan       {{ background-color: {action_scan};        color: {action_text}; font-weight: bold; }}
QPushButton#btnApply      {{ font-weight: bold; }}
QPushButton#btnSpyStart   {{ background-color: {action_connect};     color: {action_text}; font-weight: bold; font-size: 13px; padding: 6px; }}
QPushButton#btnSpyStop    {{ background-color: {action_disconnect};  color: {action_text}; font-weight: bold; font-size: 13px; padding: 6px; }}

QLabel#specgenSectionHeading {{
    font-size: {section_heading_size}pt;
    font-weight: {section_heading_weight};
    color: {section_heading_color};
    margin-top: 8px;
    margin-bottom: 4px;
}}

QLabel#noteLabel {{ color: {status_warning}; font-size: 10px; }}
QLabel#mutedLabel {{ color: {text_muted}; }}
/* [XREF: file-picker] validated file-status line colors */
QLabel#statusOk {{ color: {status_active}; }}
QLabel#statusError {{ color: {status_error}; }}

QPushButton[saveDirty="true"] {{
    background-color: {save_dirty_bg};
    color: {save_dirty_text};
    font-weight: 600;
    border-radius: 3px;
    padding: 4px 12px;
}}
QPushButton[saveDirty="true"]:hover {{ background-color: {save_dirty_hover}; }}

QStatusBar {{ background-color: {bg_tertiary}; color: {text_primary}; }}
QSplitter::handle {{ background: {border_primary}; }}
QScrollBar:vertical {{ background: {bg_primary}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {border_primary}; border-radius: 4px; min-height: 20px; }}
QCheckBox {{ color: {text_primary}; spacing: 5px; }}
QRadioButton {{ color: {text_primary}; spacing: 6px; }}
QProgressDialog {{ background-color: {bg_primary}; color: {text_primary}; }}
"""

# Currently active resolved palette (set by apply_theme).
_active_name: str = "dark"
_active_palette: dict = _PALETTES["dark"]


def _resolve(theme_name: str) -> str:
    if theme_name == "system":
        return "dark"   # OS detection could refine this; default to dark
    if theme_name not in VALID_THEMES:
        return "dark"
    return theme_name


def apply_theme(theme_name: str) -> None:
    """Apply the named theme to the running QApplication."""
    global _active_name, _active_palette
    app = QApplication.instance()
    if not app:
        return
    if theme_name not in VALID_THEMES:
        log.warning("Unknown theme '%s' - falling back to 'dark'", theme_name)
        theme_name = "dark"
    resolved = _resolve(theme_name)
    palette = _PALETTES.get(resolved, _PALETTES["dark"])
    merged = {**_SHARED_TOKENS, **palette}
    app.setStyleSheet(_QSS_TEMPLATE.format(**merged))
    _active_name = theme_name
    _active_palette = palette
    log.info("theme: %s applied", theme_name)


def active_palette() -> dict:
    """Return the currently active resolved palette dict."""
    return _active_palette


def active_theme_name() -> str:
    return _active_name


def get_color(token: str, default: str = "#000000") -> QColor:
    """Return a QColor for a named token in the active palette."""
    return QColor(_active_palette.get(token, default))


def make_section_heading(text: str) -> QLabel:
    """Create a QLabel styled as a specgen_section_heading."""
    label = QLabel(text)
    label.setObjectName("specgenSectionHeading")
    return label


def set_save_dirty(button: QPushButton, dirty: bool) -> None:
    """Toggle the dirty (unsaved-changes) styling on a Save button."""
    button.setProperty("saveDirty", bool(dirty))
    style = button.style()
    if style:
        style.unpolish(button)
        style.polish(button)
