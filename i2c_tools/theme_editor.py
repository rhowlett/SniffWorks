#!/usr/bin/env python3
"""
theme_editor.py
Visual theme editor for the ion_i2c_tool applications.
(Renamed and refactored from pyside6_theme_playground.py, which was a
standalone proof of concept; this version is built on the project's ui/
infrastructure for extensibility.)

What it shares with the main applications - by construction, not by copy:
  * QApplication bootstrap ......... ui.common.build_application
  * Window frame (tabs + status) ... ui.widgets.AppWindow
  * Titled blocks .................. ui.widgets.Section
  * Open/save/message dialogs ...... ui.dialogs
  * Config load/normalize/defaults . ui.theme_config_loader
  * QSS generation & live apply .... ui.theme.apply_theme_config /
                                     ui.theme.qss_from_theme_config
  * Palette presets ................ every named app theme (ui.theme)

Because Apply routes through ui.theme.apply_theme_config, the preview here
renders with the *exact* QSS the main tool will use for the saved file.

Files are saved as ui/themes/<name>.qt_theme.json (the Preferences tab's
default discovery location) and validate against schema/qt_theme.schema.json.
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from typing import Any

# Allow running as `python3 theme_editor.py` from anywhere
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QAction, QCloseEvent, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox,
    QDateEdit, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QSplitter, QStyleFactory, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QTimeEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ui.common import build_application
from ui.widgets import AppWindow, Section
from ui.tabs import ExitTab
from ui import dialogs
from ui import theme
from ui.theme_config_loader import (
    DEFAULT_PALETTE, DEFAULT_SETTINGS, KNOWN_PALETTE_TOKENS,
    THEME_FILE_SUFFIX, THEME_FILE_TYPE, THEME_FILE_VERSION,
    ThemeConfigError, load_theme_config, normalize_theme_config,
    sanitize_hex_color, themes_dir,
)

APP_NAME = "Theme Editor"
APP_VERSION = "1.0.0"

SYSTEM_STYLE_SENTINEL = "System Default"


def default_config() -> dict:
    return {
        "file_type": THEME_FILE_TYPE,
        "file_version": THEME_FILE_VERSION,
        "preset_name": "default",
        "settings": dict(DEFAULT_SETTINGS),
        "palette": dict(theme.named_theme_palettes().get(
            "default", DEFAULT_PALETTE)),
    }


def config_for_save(config: dict) -> dict:
    """Canonical on-disk form: normalized + a generated_qss snapshot that is
    byte-identical to what the main tool will render for this file."""
    saved = normalize_theme_config(config)
    saved["app_version"] = APP_VERSION
    saved["generated_qss"] = theme.qss_from_theme_config(saved)
    return saved


def normalized_json(config: dict) -> str:
    return json.dumps(config_for_save(config), indent=2, sort_keys=True)


class ThemeEditorWindow(AppWindow):
    """Two tabs: Config (controls) and Preview (representative widgets)."""

    def __init__(self):
        super().__init__(f"{APP_NAME} {APP_VERSION}")
        self.resize(1220, 820)

        self._loading_controls = False
        self._current_file_path: Path | None = None
        self._saved_json = ""
        self._applied_config = normalize_theme_config(default_config())
        self._system_style_name = QApplication.instance().style().objectName()
        self._presets = theme.named_theme_palettes()

        self._palette_edits: dict[str, QLineEdit] = {}
        self._palette_swatches: dict[str, QLabel] = {}

        self._build_tabs()
        self._build_menu()
        self._load_config_into_controls(self._applied_config)
        self._apply_config(self._applied_config)
        self._mark_saved()

    # ------------------------------------------------------------------
    # Frame
    # ------------------------------------------------------------------
    def _build_tabs(self) -> None:
        self.add_tab(self._build_config_tab(), "Config")

        self.preview_tab = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_tab)
        self.preview_layout.setContentsMargins(8, 8, 8, 8)
        self.preview_layout.setSpacing(8)
        self.add_tab(self.preview_tab, "Preview")

        # Shared Exit tab (Close Application button uses action_disconnect
        # via btnDisconnect); closeEvent handles unsaved-changes confirm.
        self._exit_tab = ExitTab(APP_NAME)
        self._exit_tab.exit_requested.connect(self.close)
        self.add_tab(self._exit_tab, "Exit")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        for label, slot in (("Apply", self._on_apply), ("Save", self._on_save),
                            ("Load", self._on_load)):
            act = QAction(label, self)
            act.triggered.connect(slot)
            file_menu.addAction(act)
        file_menu.addSeparator()
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

    # ------------------------------------------------------------------
    # Config tab
    # ------------------------------------------------------------------
    def _build_config_tab(self) -> QWidget:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        top_bar = QHBoxLayout()
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("btnApply")
        self.apply_button.clicked.connect(self._on_apply)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self._on_load)

        top_bar.addWidget(self.apply_button)
        top_bar.addWidget(self.save_button)
        top_bar.addWidget(self.load_button)
        top_bar.addStretch(1)
        outer.addLayout(top_bar)

        splitter = QSplitter()
        splitter.addWidget(self._build_settings_panel())
        splitter.addWidget(self._build_palette_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)
        return root

    def _build_settings_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        settings_box = Section("Application / Tab Settings")
        form = QFormLayout()

        self.qt_style_combo = QComboBox()
        self.qt_style_combo.addItem(SYSTEM_STYLE_SENTINEL, SYSTEM_STYLE_SENTINEL)
        for style_name in QStyleFactory.keys():
            self.qt_style_combo.addItem(style_name, style_name)

        self.preset_combo = QComboBox()
        for preset_name in self._presets:
            self.preset_combo.addItem(preset_name, preset_name)

        self.document_mode_check = QCheckBox("Document mode")
        self.draw_base_check = QCheckBox("Draw tab-bar base")
        self.pane_border_check = QCheckBox("Draw tab pane border")

        self.tab_qss_mode_combo = QComboBox()
        self.tab_qss_mode_combo.addItems(["Styled QSS", "Native / Unicode Finder"])
        self.tab_pane_top_offset_spin = self._spin(-10, 10)
        self.selected_tab_margin_bottom_spin = self._spin(-10, 10)
        self.tab_position_combo = QComboBox()
        self.tab_position_combo.addItems(["North", "South", "West", "East"])
        self.tab_shape_combo = QComboBox()
        self.tab_shape_combo.addItems(["Rounded", "Triangular"])
        self.button_layout_combo = QComboBox()
        self.button_layout_combo.addItems(["Mixed", "Fixed Width", "Expanding"])
        self.group_box_title_combo = QComboBox()
        self.group_box_title_combo.addItems(["On Border", "Above Border"])

        self.font_family_edit = QLineEdit()
        self.font_family_edit.setPlaceholderText("Blank = Qt default")
        self.base_font_spin = self._spin(7, 18)
        self.radius_spin = self._spin(0, 20)
        self.input_height_spin = self._spin(18, 48)
        self.input_padding_spin = self._spin(0, 14)
        self.fixed_button_width_spin = self._spin(70, 260)
        self.tab_padding_v_spin = self._spin(0, 20)
        self.tab_padding_h_spin = self._spin(2, 32)
        self.table_row_height_spin = self._spin(18, 48)
        self.section_heading_size_spin = self._spin(8, 24)
        self.section_heading_weight_spin = self._spin(100, 900, step=50)

        form.addRow("Qt style:", self.qt_style_combo)
        form.addRow("Preset:", self.preset_combo)
        form.addRow("Tabs:", self.document_mode_check)
        form.addRow("", self.draw_base_check)
        form.addRow("", self.pane_border_check)
        form.addRow("Tab QSS mode:", self.tab_qss_mode_combo)
        form.addRow("Pane top offset:", self.tab_pane_top_offset_spin)
        form.addRow("Selected tab overlap:", self.selected_tab_margin_bottom_spin)
        form.addRow("Tab position:", self.tab_position_combo)
        form.addRow("Tab shape:", self.tab_shape_combo)
        form.addRow("Button layout:", self.button_layout_combo)
        form.addRow("Section title:", self.group_box_title_combo)
        form.addRow("Font family:", self.font_family_edit)
        form.addRow("Base font size:", self.base_font_spin)
        form.addRow("Control radius:", self.radius_spin)
        form.addRow("Input height:", self.input_height_spin)
        form.addRow("Input V padding:", self.input_padding_spin)
        form.addRow("Fixed button width:", self.fixed_button_width_spin)
        form.addRow("Tab V padding:", self.tab_padding_v_spin)
        form.addRow("Tab H padding:", self.tab_padding_h_spin)
        form.addRow("Table row height:", self.table_row_height_spin)
        form.addRow("Heading size:", self.section_heading_size_spin)
        form.addRow("Heading weight:", self.section_heading_weight_spin)

        settings_box.add_layout(form)
        layout.addWidget(settings_box)

        note = QLabel("Apply updates the live preview using the SAME QSS "
                      "generator the main tool uses (ui.theme). Save writes "
                      f"a *{THEME_FILE_SUFFIX} file into ui/themes/ where the "
                      "Preferences tab lists it.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

        self._connect_dirty_signals([
            self.qt_style_combo, self.preset_combo, self.document_mode_check,
            self.draw_base_check, self.pane_border_check,
            self.tab_qss_mode_combo, self.tab_pane_top_offset_spin,
            self.selected_tab_margin_bottom_spin, self.tab_position_combo,
            self.tab_shape_combo, self.button_layout_combo,
            self.group_box_title_combo, self.font_family_edit,
            self.base_font_spin, self.radius_spin, self.input_height_spin,
            self.input_padding_spin, self.fixed_button_width_spin,
            self.tab_padding_v_spin, self.tab_padding_h_spin,
            self.table_row_height_spin, self.section_heading_size_spin,
            self.section_heading_weight_spin,
        ])
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)

        scroll.setWidget(body)
        return scroll

    def _build_palette_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        colors_box = Section("Semantic Color Tokens")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        for index, token in enumerate(KNOWN_PALETTE_TOKENS):
            row, col = index // 2, (index % 2) * 4

            label = QLabel(token)
            edit = QLineEdit()
            edit.setMaxLength(7)
            edit.setPlaceholderText("#RRGGBB")
            edit.textChanged.connect(self._mark_dirty)
            edit.textChanged.connect(
                lambda value, name=token: self._update_color_swatch(name, value))

            swatch = QLabel()
            swatch.setFixedSize(34, 22)
            swatch.setToolTip(token)

            pick = QPushButton("Pick")
            pick.clicked.connect(
                lambda checked=False, name=token: self._pick_color(name))

            self._palette_edits[token] = edit
            self._palette_swatches[token] = swatch

            grid.addWidget(label, row, col)
            grid.addWidget(edit, row, col + 1)
            grid.addWidget(swatch, row, col + 2)
            grid.addWidget(pick, row, col + 3)

        colors_box.add_layout(grid)
        layout.addWidget(colors_box)

        hint = QLabel("Semantic tokens shared with ui/theme.py. Named action "
                      "buttons (btnConnect, btnRead, ...) and saveDirty "
                      "styling are shown on the Preview tab.")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

        scroll.setWidget(body)
        return scroll

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _spin(self, minimum: int, maximum: int, step: int = 1) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        return spin

    def _connect_dirty_signals(self, widgets: list[QWidget]) -> None:
        for w in widgets:
            if isinstance(w, QComboBox):
                w.currentTextChanged.connect(self._mark_dirty)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self._mark_dirty)
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self._mark_dirty)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self._mark_dirty)

    def _update_color_swatch(self, token: str, value: str) -> None:
        swatch = self._palette_swatches.get(token)
        if swatch is None:
            return
        color_text = sanitize_hex_color(value, "")
        if not color_text:
            swatch.setText("?")
            swatch.setAlignment(Qt.AlignCenter)
            swatch.setStyleSheet(
                "QLabel\n"
                "{\n"
                "    background-color: transparent;\n"
                "    border: 1px dashed #888888;\n"
                "    border-radius: 3px;\n"
                "}"
            )
            return
        swatch.setText("")
        swatch.setStyleSheet(
            "QLabel\n"
            "{\n"
            f"    background-color: {color_text};\n"
            "    border: 1px solid #888888;\n"
            "    border-radius: 3px;\n"
            "}"
        )

    def _pick_color(self, token: str) -> None:
        edit = self._palette_edits[token]
        current = sanitize_hex_color(edit.text(), "")
        initial = QColor(current) if current else QColor("#FFFFFF")
        color = QColorDialog.getColor(initial, self, f"Pick color for {token}")
        if color.isValid():
            edit.setText(color.name().upper())
        elif current:
            edit.setText(current)

    def _on_preset_changed(self) -> None:
        if self._loading_controls:
            return
        preset_name = self.preset_combo.currentData()
        preset = self._presets.get(preset_name)
        if not preset:
            return
        for token, value in preset.items():
            if token in self._palette_edits:
                self._palette_edits[token].setText(value)
        self._mark_dirty()

    # ------------------------------------------------------------------
    # Controls <-> config
    # ------------------------------------------------------------------
    def _config_from_controls(self) -> dict:
        cfg = normalize_theme_config(default_config())
        settings, palette = cfg["settings"], cfg["palette"]

        cfg["preset_name"] = self.preset_combo.currentData() or "custom"

        qt_style = self.qt_style_combo.currentData() or SYSTEM_STYLE_SENTINEL
        settings["qt_style"] = "" if qt_style == SYSTEM_STYLE_SENTINEL else qt_style
        settings["document_mode"] = self.document_mode_check.isChecked()
        settings["tab_draw_base"] = self.draw_base_check.isChecked()
        settings["pane_border"] = self.pane_border_check.isChecked()
        settings["tab_qss_mode"] = self.tab_qss_mode_combo.currentText()
        settings["tab_pane_top_offset"] = self.tab_pane_top_offset_spin.value()
        settings["selected_tab_margin_bottom"] = \
            self.selected_tab_margin_bottom_spin.value()
        settings["tab_position"] = self.tab_position_combo.currentText()
        settings["tab_shape"] = self.tab_shape_combo.currentText()
        settings["button_layout"] = self.button_layout_combo.currentText()
        settings["group_box_title_mode"] = self.group_box_title_combo.currentText()
        settings["font_family"] = self.font_family_edit.text().strip()
        settings["base_font_size"] = self.base_font_spin.value()
        settings["control_radius"] = self.radius_spin.value()
        settings["input_min_height"] = self.input_height_spin.value()
        settings["input_v_padding"] = self.input_padding_spin.value()
        settings["button_fixed_width"] = self.fixed_button_width_spin.value()
        settings["tab_padding_v"] = self.tab_padding_v_spin.value()
        settings["tab_padding_h"] = self.tab_padding_h_spin.value()
        settings["table_row_height"] = self.table_row_height_spin.value()
        settings["section_heading_size"] = self.section_heading_size_spin.value()
        settings["section_heading_weight"] = self.section_heading_weight_spin.value()

        for token in KNOWN_PALETTE_TOKENS:
            palette[token] = sanitize_hex_color(
                self._palette_edits[token].text(), DEFAULT_PALETTE[token])
        return cfg

    def _load_config_into_controls(self, config: dict) -> None:
        self._loading_controls = True
        cfg = normalize_theme_config(config)
        settings, palette = cfg["settings"], cfg["palette"]

        style_value = settings.get("qt_style") or SYSTEM_STYLE_SENTINEL
        self._set_combo_by_data(self.qt_style_combo, style_value)
        self._set_combo_by_data(self.preset_combo,
                                cfg.get("preset_name", "default"))

        self.document_mode_check.setChecked(settings["document_mode"])
        self.draw_base_check.setChecked(settings["tab_draw_base"])
        self.pane_border_check.setChecked(settings["pane_border"])
        self._set_combo_by_text(self.tab_qss_mode_combo, settings["tab_qss_mode"])
        self.tab_pane_top_offset_spin.setValue(settings["tab_pane_top_offset"])
        self.selected_tab_margin_bottom_spin.setValue(
            settings["selected_tab_margin_bottom"])
        self._set_combo_by_text(self.tab_position_combo, settings["tab_position"])
        self._set_combo_by_text(self.tab_shape_combo, settings["tab_shape"])
        self._set_combo_by_text(self.button_layout_combo, settings["button_layout"])
        self._set_combo_by_text(self.group_box_title_combo,
                                settings["group_box_title_mode"])
        self.font_family_edit.setText(settings["font_family"])
        self.base_font_spin.setValue(settings["base_font_size"])
        self.radius_spin.setValue(settings["control_radius"])
        self.input_height_spin.setValue(settings["input_min_height"])
        self.input_padding_spin.setValue(settings["input_v_padding"])
        self.fixed_button_width_spin.setValue(settings["button_fixed_width"])
        self.tab_padding_v_spin.setValue(settings["tab_padding_v"])
        self.tab_padding_h_spin.setValue(settings["tab_padding_h"])
        self.table_row_height_spin.setValue(settings["table_row_height"])
        self.section_heading_size_spin.setValue(settings["section_heading_size"])
        self.section_heading_weight_spin.setValue(
            settings["section_heading_weight"])

        for token in KNOWN_PALETTE_TOKENS:
            self._palette_edits[token].setText(palette[token])
        self._loading_controls = False

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_combo_by_text(combo: QComboBox, text: str) -> None:
        index = combo.findText(str(text))
        if index >= 0:
            combo.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # Apply / dirty tracking
    # ------------------------------------------------------------------
    def _apply_config(self, config: dict) -> None:
        cfg = normalize_theme_config(config)

        # "System Default" style: restore the platform style ourselves, then
        # let apply_theme_config skip its (empty) qt_style.
        if not cfg["settings"].get("qt_style"):
            app = QApplication.instance()
            if app is not None:
                app.setStyle(self._system_style_name)

        # One code path with the main tool: same QSS, same tab settings
        # (AppWindow registered self.tabs with the theme registry).
        theme.apply_theme_config(cfg)

        self._applied_config = cfg
        self._rebuild_preview_tab()
        self.notify("Theme applied.")

    def _mark_dirty(self) -> None:
        if self._loading_controls:
            return
        dirty = normalized_json(self._config_from_controls()) != self._saved_json
        theme.set_save_dirty(self.save_button, dirty)

    def _mark_saved(self) -> None:
        self._saved_json = normalized_json(self._config_from_controls())
        theme.set_save_dirty(self.save_button, False)

    # ------------------------------------------------------------------
    # Preview tab (representative widgets, passive)
    # ------------------------------------------------------------------
    def _rebuild_preview_tab(self) -> None:
        self._clear_layout(self.preview_layout)

        heading = theme.make_section_heading("Theme Preview")
        note = QLabel("Passive preview of common controls, including the "
                      "named action buttons and log-table styling the main "
                      "tool relies on.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        self.preview_layout.addWidget(heading)
        self.preview_layout.addWidget(note)

        splitter = QSplitter()
        splitter.addWidget(self._scroll_panel(
            self._build_button_preview(),
            self._build_input_preview(),
            self._build_selection_preview()))
        splitter.addWidget(self._scroll_panel(
            self._build_table_preview(),
            self._build_list_tree_preview(),
            self._build_text_preview(),
            self._build_nested_tabs_preview()))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.preview_layout.addWidget(splitter, 1)

    @staticmethod
    def _scroll_panel(*sections: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        for s in sections:
            layout.addWidget(s)
        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _build_button_preview(self) -> Section:
        section = Section("Buttons")
        settings = self._applied_config["settings"]
        mode = settings.get("button_layout", "Mixed")
        fixed_width = int(settings.get("button_fixed_width", 130))

        rows = [
            [("Connect", "btnConnect"), ("Disconnect", "btnDisconnect")],
            [("Read", "btnRead"), ("Write", "btnWrite"),
             ("Write Read", "btnWriteRead")],
            [("Scan", "btnScan"), ("Apply", "btnApply")],
        ]
        for row_spec in rows:
            buttons = [self._preview_button(t, o, mode, fixed_width)
                       for t, o in row_spec]
            self._add_button_row(section, buttons, mode)

        dirty_save = self._preview_button("Save Dirty", "", mode, fixed_width)
        theme.set_save_dirty(dirty_save, True)
        disabled = self._preview_button("Disabled", "", mode, fixed_width)
        disabled.setEnabled(False)
        self._add_button_row(section, [dirty_save, disabled], mode)
        return section

    def _preview_button(self, text: str, object_name: str,
                        mode: str, fixed_width: int) -> QPushButton:
        button = QPushButton(text)
        if object_name:
            button.setObjectName(object_name)
        if mode == "Fixed Width":
            button.setFixedWidth(fixed_width)
        elif mode == "Expanding":
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        elif text in {"Connect", "Disconnect", "Save Dirty"}:
            button.setFixedWidth(fixed_width)
        return button

    @staticmethod
    def _add_button_row(section: Section, buttons, mode: str) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        for b in buttons:
            row.addWidget(b, 1 if mode == "Expanding" else 0)
        if mode != "Expanding":
            row.addStretch(1)
        section.add_layout(row)

    def _build_input_preview(self) -> Section:
        section = Section("Inputs")
        form = QFormLayout()
        combo = QComboBox()
        combo.addItems(["100 kHz", "400 kHz", "1 MHz"])
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setValue(42)
        dspin = QDoubleSpinBox()
        dspin.setRange(0.0, 10.0)
        dspin.setDecimals(3)
        dspin.setValue(3.300)
        form.addRow("Line edit:", QLineEdit("0x2D"))
        form.addRow("Combo box:", combo)
        form.addRow("Spin box:", spin)
        form.addRow("Double spin:", dspin)
        form.addRow("Date edit:", QDateEdit(QDate.currentDate()))
        form.addRow("Time edit:", QTimeEdit(QTime.currentTime()))
        section.add_layout(form)
        return section

    def _build_selection_preview(self) -> Section:
        section = Section("Selections")
        cb1 = QCheckBox("Unchecked checkbox")
        cb2 = QCheckBox("Checked checkbox")
        cb2.setChecked(True)
        cb3 = QCheckBox("Partially checked checkbox")
        cb3.setTristate(True)
        cb3.setCheckState(Qt.PartiallyChecked)
        rb1 = QRadioButton("Radio option A")
        rb2 = QRadioButton("Radio option B")
        rb2.setChecked(True)
        group = QButtonGroup(section)
        group.addButton(rb1)
        group.addButton(rb2)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(65)
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(72)
        for w in (cb1, cb2, cb3, rb1, rb2, QLabel("Slider:"), slider,
                  QLabel("Progress:"), progress):
            section.add_widget(w)
        return section

    def _build_table_preview(self) -> Section:
        section = Section("Tables")
        table = QTableWidget(4, 5)
        table.setHorizontalHeaderLabels(
            ["Address", "Register", "Direction", "Value", "Status"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        rows = [
            ["0x08", "0x3E", "Write", "0x02", "ACK"],
            ["0x08", "0x14", "Read", "0x5A", "ACK"],
            ["0x08", "0x80", "Write Read", "0xFF", "NAK"],
            ["0x77", "--", "Scan", "--", "Idle"],
        ]
        row_height = int(self._applied_config["settings"]["table_row_height"])
        for r, values in enumerate(rows):
            table.setRowHeight(r, row_height)
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        section.add_widget(table)
        return section

    def _build_list_tree_preview(self) -> Section:
        section = Section("Lists / Trees")
        list_widget = QListWidget()
        list_widget.addItems(["Device", "Sniffer", "Preferences", "Logs"])
        list_widget.setCurrentRow(1)
        tree = QTreeWidget()
        tree.setHeaderLabels(["Node", "Value"])
        root = QTreeWidgetItem(["Project", "Active"])
        root.addChild(QTreeWidgetItem(
            ["Theme", self._applied_config.get("preset_name", "custom")]))
        root.addChild(QTreeWidgetItem(["Status", "Preview only"]))
        tree.addTopLevelItem(root)
        tree.expandAll()
        section.add_widget(list_widget)
        section.add_widget(tree)
        return section

    def _build_text_preview(self) -> Section:
        section = Section("Text")
        muted = QLabel("Muted helper text")
        muted.setObjectName("mutedLabel")
        warning = QLabel("Warning / note label")
        warning.setObjectName("noteLabel")
        ok = QLabel("Status OK label")
        ok.setObjectName("statusOk")
        err = QLabel("Status error label")
        err.setObjectName("statusError")
        text_edit = QTextEdit()
        text_edit.setPlainText("QTextEdit preview\nMultiline rich text area")
        text_edit.setFixedHeight(80)
        plain = QPlainTextEdit()
        plain.setPlainText("QPlainTextEdit preview\nLog style text area")
        plain.setFixedHeight(80)
        plain.setFont(QFont("monospace"))
        for w in (QLabel("Primary label text"), muted, warning, ok, err,
                  text_edit, plain):
            section.add_widget(w)
        return section

    def _build_nested_tabs_preview(self) -> Section:
        section = Section("Nested Tabs / Frames")
        settings = self._applied_config["settings"]
        tabs = QTabWidget()
        tabs.setObjectName("nestedTabs")
        tabs.setDocumentMode(bool(settings["document_mode"]))
        tabs.tabBar().setDrawBase(bool(settings["tab_draw_base"]))
        for name in ["First", "Second", "Third"]:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.addWidget(QLabel(f"Nested tab page: {name}"))
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            page_layout.addWidget(line)
            page_layout.addWidget(QLabel("Frame and page background preview."))
            page_layout.addStretch(1)
            tabs.addTab(page, name)
        section.add_widget(tabs)
        return section

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_apply(self) -> None:
        self._apply_config(self._config_from_controls())
        self._mark_dirty()

    def _on_save(self) -> None:
        cfg = config_for_save(self._config_from_controls())
        suggested = (self._current_file_path.name if self._current_file_path
                     else f"{cfg['preset_name'] or 'custom'}{THEME_FILE_SUFFIX}")
        themes_dir().mkdir(parents=True, exist_ok=True)
        path = dialogs.save_json(self, "Save Theme", suggested,
                                 str(themes_dir()))
        if not path:
            return
        if not path.endswith(THEME_FILE_SUFFIX):
            root = path[:-5] if path.endswith(".json") else path
            path = root + THEME_FILE_SUFFIX
        try:
            Path(path).write_text(json.dumps(cfg, indent=2, sort_keys=True)
                                  + "\n", encoding="utf-8")
        except OSError as e:
            dialogs.error(self, "Save Failed", str(e))
            return
        self._current_file_path = Path(path)
        self._mark_saved()
        self.notify(f"Saved {path}")

    def _on_load(self) -> None:
        path = dialogs.open_json(self, "Load Theme", str(themes_dir()))
        if not path:
            return
        try:
            cfg = load_theme_config(path)
        except ThemeConfigError as e:
            dialogs.error(self, "Load Failed", str(e))
            return
        self._current_file_path = Path(path)
        self._load_config_into_controls(cfg)
        self._apply_config(cfg)
        self._mark_saved()
        self.notify(f"Loaded {path}")

    # ConfirmingCloseMixin (via AppWindow) handles closeEvent; the Exit tab
    # and window close button share this guard.
    def close_guard(self):
        dirty = normalized_json(self._config_from_controls()) != self._saved_json
        return "The theme has unsaved changes. Exit anyway?" if dirty else None


def main():
    app = build_application(
        app_name=APP_NAME,
        version=APP_VERSION,
        org="Digilent AD2 Utils",
        initial_theme="dark",
    )
    window = ThemeEditorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
