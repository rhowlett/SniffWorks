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
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtGui import QColor

log = logging.getLogger(__name__)


class _ThemeSignals(QObject):
    """Qt signals for the module-level theme API.

    changed(selection) fires after any theme is applied (named or file-based;
    selection is the value apply_theme() accepts). Widgets that render from
    the active palette outside of QSS — the log-table model colors, the Help
    tab's HTML guide — subscribe here instead of every window re-wiring the
    repaints by hand.
    """
    changed = Signal(str)


signals = _ThemeSignals()

VALID_THEMES = {"system", "light", "dark", "default"}

# Human-readable labels + ordering for the Preferences tab. Specialty themes
# (Iontra, Engineering, Claude, ...) live as ui/themes/*.qt_theme.json files
# and appear in the picker's "Theme Files" group instead.
THEME_CHOICES = [
    ("default", "Default (Modern Dark)"),
    ("system",  "System (follows OS)"),
    ("light",   "Light"),
    ("dark",    "Dark"),
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
    # -----------------------------------------------------------------------
    # default — modern dark: deep neutral slate surfaces with an indigo
    # accent; muted-but-saturated action colors (contemporary dev-tool look).
    # -----------------------------------------------------------------------
    "default": {
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
        "save_dirty_bg": "#2EA36B", "save_dirty_hover": "#35B879", "save_dirty_text": "#FFFFFF",
        "section_heading_color": "#E2E4EA", "section_heading_size": "13", "section_heading_weight": "600",
    },
}

_QSS_TEMPLATE = """
QMainWindow, QWidget {{ background-color: {bg_primary}; color: {text_primary}; {font_line} }}

QGroupBox {{
    border: 1px solid {border_primary};
    border-radius: {control_radius}px;
    margin-top: {group_box_margin_top}px;
    padding-top: {group_box_padding_top}px;
    font-weight: bold;
    color: {accent_primary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

{tab_qss_block}

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
    border-radius: {input_radius}px;
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
    border-radius: {control_radius}px;
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
    border-radius: {input_radius}px;
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
_active_name: str = "default"
_active_palette: dict = _PALETTES["default"]
_active_config: dict | None = None      # normalized theme-file config, if any
_active_file_path: str | None = None

# Selection strings for theme files carry this prefix (e.g. from ThemePicker):
FILE_THEME_PREFIX = "file:"

# Defaults that reproduce the original hard-coded template values, so the
# named themes render exactly as before the theme-file feature was added.
_LEGACY_TOKENS: dict[str, str] = {
    "font_line": "",
    "control_radius": "4",
    "input_radius": "3",
    "group_box_margin_top": "8",
    "group_box_padding_top": "0",
}

_LEGACY_TAB_QSS = """QTabWidget::pane { border: 1px solid %(border_primary)s; }
QTabBar::tab {
    background: %(bg_secondary)s;
    color: %(text_primary)s;
    padding: 6px 12px;
    border: 1px solid %(border_primary)s;
}
QTabBar::tab:selected {
    background: %(bg_tertiary)s;
    color: %(accent_primary)s;
}"""


def _resolve(theme_name: str) -> str:
    if theme_name == "system":
        return "default"   # OS detection could refine this; dark by default
    if theme_name not in VALID_THEMES:
        return "default"
    return theme_name


def apply_theme(theme_name: str) -> None:
    """
    Apply a theme to the running QApplication.

    Accepts either a named built-in theme ("default", "light", "dark") or a
    theme-file selection of the form "file:<path to *.qt_theme.json>" as
    emitted by the Preferences theme picker. Named-theme behaviour is
    unchanged from before theme-file support existed.
    """
    global _active_name, _active_palette, _active_config, _active_file_path
    app = QApplication.instance()
    if not app:
        return

    if isinstance(theme_name, str) and theme_name.startswith(FILE_THEME_PREFIX):
        apply_theme_file(theme_name[len(FILE_THEME_PREFIX):])
        return

    if theme_name not in VALID_THEMES:
        log.warning("Unknown theme '%s' - falling back to 'default'", theme_name)
        theme_name = "default"
    resolved = _resolve(theme_name)
    palette = _PALETTES.get(resolved, _PALETTES["default"])
    merged = {**_SHARED_TOKENS, **_LEGACY_TOKENS, **palette}
    merged["tab_qss_block"] = _LEGACY_TAB_QSS % palette
    app.setStyleSheet(_QSS_TEMPLATE.format(**merged))
    _active_name = theme_name
    _active_palette = palette
    _active_config = None
    _active_file_path = None
    _reset_tab_widgets_to_defaults()
    log.info("theme: %s applied", theme_name)
    signals.changed.emit(theme_name)


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


# ===========================================================================
# Theme-file support (*.qt_theme.json) - apply_qt_theme_prompt.md
# `palette` + `settings` are the source of truth; QSS is regenerated from the
# project's own template above so every widget stays consistent with the
# named themes. `generated_qss` in the file is reference-only.
# ===========================================================================
import weakref as _weakref

from ui.theme_config_loader import (               # noqa: E402
    load_theme_config, normalize_theme_config, ThemeConfigError,
)

# Weak registry of project-owned QTabWidgets that opt in to non-QSS tab
# settings (document mode, draw base, position, shape). AppWindow registers
# its main tab widget; custom layouts (e.g. side navigation) stay out.
_tab_widget_refs: list = []


def register_tab_widget(tabs) -> None:
    """Opt a normal content QTabWidget in to theme-file tab settings."""
    _tab_widget_refs.append(_weakref.ref(tabs))
    if _active_config is not None:
        _apply_tab_settings_one(tabs, _active_config["settings"])


def _live_tab_widgets():
    alive = []
    for ref in list(_tab_widget_refs):
        w = ref()
        if w is None:
            _tab_widget_refs.remove(ref)
        else:
            alive.append(w)
    return alive


def _tab_position_from_name(name: str):
    from PySide6.QtWidgets import QTabWidget
    return {
        "North": QTabWidget.TabPosition.North,
        "South": QTabWidget.TabPosition.South,
        "West":  QTabWidget.TabPosition.West,
        "East":  QTabWidget.TabPosition.East,
    }.get(name, QTabWidget.TabPosition.North)


def _tab_shape_from_name(name: str):
    from PySide6.QtWidgets import QTabWidget
    return {
        "Rounded":    QTabWidget.TabShape.Rounded,
        "Triangular": QTabWidget.TabShape.Triangular,
    }.get(name, QTabWidget.TabShape.Rounded)


def _apply_tab_settings_one(tabs, settings: dict) -> None:
    tabs.setDocumentMode(bool(settings.get("document_mode", False)))
    bar = tabs.tabBar()
    if bar is not None:
        bar.setDrawBase(bool(settings.get("tab_draw_base", True)))
    tabs.setTabPosition(_tab_position_from_name(str(settings.get("tab_position", "North"))))
    tabs.setTabShape(_tab_shape_from_name(str(settings.get("tab_shape", "Rounded"))))


def _apply_tab_settings_all(settings: dict) -> None:
    for tabs in _live_tab_widgets():
        _apply_tab_settings_one(tabs, settings)


def _reset_tab_widgets_to_defaults() -> None:
    """Named themes use Qt defaults (the pre-theme-file appearance)."""
    defaults = {"document_mode": False, "tab_draw_base": True,
                "tab_position": "North", "tab_shape": "Rounded"}
    _apply_tab_settings_all(defaults)


def _build_tab_qss_from_settings(settings: dict, tokens: dict) -> str:
    """Styled tab QSS driven by theme-file settings (Allman braces)."""
    if str(settings.get("tab_qss_mode", "Styled QSS")) == "Native / Unicode Finder":
        # Native mode: no QTabWidget/QTabBar QSS at all so the platform
        # style (e.g. macOS "Finder" look) renders the tabs.
        return ""
    pane_border_width = 1 if settings.get("pane_border", True) else 0
    pane_top = int(settings.get("tab_pane_top_offset", -1))
    sel_margin = int(settings.get("selected_tab_margin_bottom", 0))
    return f"""QTabWidget::pane
{{
    border: {pane_border_width}px solid {tokens['border_primary']};
    top: {pane_top}px;
}}

QTabBar::tab
{{
    background-color: {tokens['bg_secondary']};
    color: {tokens['text_primary']};
    padding: {tokens['tab_padding_v']}px {tokens['tab_padding_h']}px;
    border: 1px solid {tokens['border_primary']};
    border-top-left-radius: {tokens['control_radius']}px;
    border-top-right-radius: {tokens['control_radius']}px;
    min-width: 70px;
}}

QTabBar::tab:selected
{{
    background-color: {tokens['bg_tertiary']};
    color: {tokens['accent_primary']};
    font-weight: 600;
    margin-bottom: {sel_margin}px;
}}

QTabBar::tab:hover
{{
    background-color: {tokens['bg_selected']};
    color: {tokens['text_inverse']};
}}

QTabBar::tab:!selected
{{
    margin-top: 2px;
}}"""


def qss_from_theme_config(config: dict) -> str:
    """
    Build application QSS from a normalized theme-file config using the
    project's own template (single source of styling for all widgets).
    """
    cfg = normalize_theme_config(config)
    palette = cfg["palette"]
    settings = cfg["settings"]

    font_family = str(settings.get("font_family", "")).strip()
    font_line = f"font-size: {int(settings['base_font_size'])}pt;"
    if font_family:
        font_line += f" font-family: '{font_family}';"

    if settings.get("group_box_title_mode") == "Above Border":
        gb_margin, gb_padding = 22, 4
    else:
        gb_margin, gb_padding = 8, 0

    control_radius = int(settings["control_radius"])
    tokens: dict = {
        **_SHARED_TOKENS,
        **palette,
        "font_line": font_line,
        "control_radius": str(control_radius),
        "input_radius": str(max(control_radius - 1, 0)),
        "group_box_margin_top": str(gb_margin),
        "group_box_padding_top": str(gb_padding),
        "input_min_height": str(int(settings["input_min_height"])),
        "input_v_padding": str(int(settings["input_v_padding"])),
        "tab_padding_v": str(int(settings["tab_padding_v"])),
        "tab_padding_h": str(int(settings["tab_padding_h"])),
        "section_heading_size": str(int(settings["section_heading_size"])),
        "section_heading_weight": str(int(settings["section_heading_weight"])),
    }
    tokens["tab_qss_block"] = _build_tab_qss_from_settings(settings, tokens)
    return _QSS_TEMPLATE.format(**tokens)


def apply_theme_config(config: dict, _selection: str | None = None) -> None:
    """Apply a (raw or normalized) theme-file config to the QApplication.
    _selection (internal) lets apply_theme_file record the 'file:<path>'
    selection string before the changed signal fires."""
    global _active_name, _active_palette, _active_config
    app = QApplication.instance()
    if not app:
        return
    cfg = normalize_theme_config(config)

    style_name = str(cfg["settings"].get("qt_style", "")).strip()
    if style_name:
        from PySide6.QtWidgets import QStyleFactory
        available = {k.lower(): k for k in QStyleFactory.keys()}
        if style_name.lower() in available:
            app.setStyle(QStyleFactory.create(available[style_name.lower()]))
        else:
            log.warning("qt_style %r not available (have: %s)",
                        style_name, ", ".join(QStyleFactory.keys()))

    app.setStyleSheet(qss_from_theme_config(cfg))
    _apply_tab_settings_all(cfg["settings"])

    _active_config = cfg
    _active_palette = cfg["palette"]
    _active_name = _selection or cfg.get("preset_name") or "custom"
    log.info("theme: config '%s' applied", _active_name)
    signals.changed.emit(_active_name)


def apply_theme_file(path) -> None:
    """Load a *.qt_theme.json file and apply it. Falls back to the current
    theme (with a log message) if the file is unreadable."""
    global _active_file_path, _active_name
    try:
        cfg = load_theme_config(path)
    except ThemeConfigError as e:
        log.error("theme file rejected: %s", e)
        return
    _active_file_path = str(path)
    apply_theme_config(cfg, _selection=FILE_THEME_PREFIX + str(path))


def active_theme_file():
    """Path of the active theme file, or None if a named theme is active."""
    return _active_file_path


def named_theme_palettes() -> dict:
    """
    Read-only copies of the built-in theme palettes, keyed by theme name and
    filtered to the theme-file token set. Used by theme_editor.py so every
    named app theme automatically appears as an editor preset.
    """
    from ui.theme_config_loader import KNOWN_PALETTE_TOKENS
    out = {}
    for name, pal in _PALETTES.items():
        out[name] = {t: pal[t] for t in KNOWN_PALETTE_TOKENS if t in pal}
    return out
