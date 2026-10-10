"""
tests/test_theme_files.py — theme-file (*.qt_theme.json) support added in the
Preferences/theme-editor update.

Covers:
  * ui.theme_config_loader: load/normalize/validation/fallbacks, discovery
  * ui.theme: qss_from_theme_config, apply_theme_config, apply_theme_file,
    apply_theme("file:...") dispatch, named themes unaffected, tab-settings
    registry
  * ui.widgets.ThemePicker: lists ui/themes files, emits file: selections
  * shipped sample themes and schema consistency
  * theme_editor: config round-trip through config_for_save

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_theme_files.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui.common import build_application  # noqa: E402
from PySide6.QtWidgets import QTabWidget  # noqa: E402
from ui import theme  # noqa: E402
from ui import theme_config_loader as tcl  # noqa: E402
from ui.widgets import ThemePicker, AppWindow  # noqa: E402

FAILURES = []


def check(cond, msg):
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        FAILURES.append(msg)


# ---------------------------------------------------------------------------
# Loader (pure)
# ---------------------------------------------------------------------------
def test_loader_normalization():
    print("loader: normalization & fallbacks")
    cfg = tcl.normalize_theme_config({})
    check(set(cfg["palette"]) == set(tcl.KNOWN_PALETTE_TOKENS),
          "empty input yields full palette")
    check(cfg["settings"] == tcl.DEFAULT_SETTINGS,
          "empty input yields default settings")

    cfg = tcl.normalize_theme_config({
        "palette": {"bg_primary": "not-a-color", "accent_primary": "#ff00aa"},
        "settings": {"control_radius": "12", "tab_position": "Sideways",
                     "document_mode": "true", "base_font_size": 999},
    })
    check(cfg["palette"]["bg_primary"] == tcl.DEFAULT_PALETTE["bg_primary"],
          "invalid color falls back")
    check(cfg["palette"]["accent_primary"] == "#FF00AA",
          "valid color case-normalized")
    check(cfg["settings"]["control_radius"] == 12, "string int coerced")
    check(cfg["settings"]["tab_position"] == "North", "bad enum falls back")
    check(cfg["settings"]["document_mode"] is True, "string bool coerced")
    check(cfg["settings"]["base_font_size"] == 24, "out-of-range clamped")


def test_loader_files():
    print("loader: file handling")
    with tempfile.TemporaryDirectory() as d:
        good = Path(d) / "my_test.qt_theme.json"
        good.write_text(json.dumps({
            "file_type": tcl.THEME_FILE_TYPE, "file_version": 1,
            "preset_name": "unit test",
            "settings": {"control_radius": 9},
            "palette": {"accent_primary": "#123456"},
        }))
        cfg = tcl.load_theme_config(good)
        check(cfg["preset_name"] == "unit test", "preset_name read")
        check(cfg["settings"]["control_radius"] == 9, "setting read")
        check(cfg["palette"]["accent_primary"] == "#123456", "palette read")
        check(cfg["source_path"] == str(good), "source_path recorded")

        bad = Path(d) / "broken.qt_theme.json"
        bad.write_text("{ not json !")
        try:
            tcl.load_theme_config(bad)
            check(False, "broken JSON raises ThemeConfigError")
        except tcl.ThemeConfigError:
            check(True, "broken JSON raises ThemeConfigError")

        try:
            tcl.load_theme_config(Path(d) / "missing.qt_theme.json")
            check(False, "missing file raises ThemeConfigError")
        except tcl.ThemeConfigError:
            check(True, "missing file raises ThemeConfigError")

        found = tcl.discover_theme_files(d)
        check([p.name for p in found] == ["broken.qt_theme.json",
                                          "my_test.qt_theme.json"],
              "discovery finds only *.qt_theme.json, sorted")
        check(tcl.theme_display_name(good) == "unit test",
              "display name from preset_name")
        check(tcl.theme_display_name(bad) == "broken",
              "display name falls back to filename")


# ---------------------------------------------------------------------------
# theme module
# ---------------------------------------------------------------------------
def test_qss_generation():
    print("theme: qss_from_theme_config")
    cfg = tcl.default_theme_config()
    cfg["palette"]["bg_primary"] = "#101112"
    cfg["palette"]["accent_primary"] = "#A1B2C3"
    cfg["settings"]["control_radius"] = 11
    cfg["settings"]["base_font_size"] = 12
    cfg["settings"]["font_family"] = "Fira Sans"
    qss = theme.qss_from_theme_config(cfg)
    check("#101112" in qss, "palette bg color present")
    check("#A1B2C3" in qss, "palette accent color present")
    check("border-radius: 11px" in qss, "control radius applied")
    check("font-size: 12pt" in qss, "base font size applied")
    check("font-family: 'Fira Sans'" in qss, "font family applied")
    check("QPushButton#btnConnect" in qss, "object-name styling preserved")
    check('QPushButton[saveDirty="true"]' in qss, "saveDirty styling preserved")

    cfg["settings"]["tab_qss_mode"] = "Native / Unicode Finder"
    qss_native = theme.qss_from_theme_config(cfg)
    check("QTabBar::tab" not in qss_native, "native mode drops tab QSS")
    cfg["settings"]["tab_qss_mode"] = "Styled QSS"
    cfg["settings"]["tab_pane_top_offset"] = -3
    qss_styled = theme.qss_from_theme_config(cfg)
    check("top: -3px" in qss_styled, "pane top offset in styled tab QSS")


def test_apply_paths(app):
    print("theme: apply paths")
    # named themes still work (acceptance criterion 1)
    for name, _label in theme.THEME_CHOICES:
        theme.apply_theme(name)
        check(bool(theme.active_palette()), f"named theme '{name}' applies")
    check(theme.active_theme_file() is None,
          "no theme file active after named theme")
    named_qss = app.styleSheet()
    check("border-radius: 4px" in named_qss and "border-radius: 3px" in named_qss,
          "named themes keep original radii (4px/3px)")

    # config apply
    cfg = tcl.default_theme_config()
    cfg["palette"]["bg_primary"] = "#0B0C0D"
    theme.apply_theme_config(cfg)
    check("#0B0C0D" in app.styleSheet(), "apply_theme_config restyles app")
    check(theme.active_palette()["bg_primary"] == "#0B0C0D",
          "active_palette tracks config (log-model colors)")
    check(theme.get_color("bg_primary").name().upper() == "#0B0C0D",
          "get_color resolves from config palette")

    # file apply + "file:" dispatch through the unchanged apply_theme API
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "disp.qt_theme.json"
        p.write_text(json.dumps({"palette": {"bg_primary": "#0E0F10"},
                                 "preset_name": "disp"}))
        theme.apply_theme_file(p)
        check("#0E0F10" in app.styleSheet(), "apply_theme_file restyles app")
        check(theme.active_theme_file() == str(p), "active_theme_file set")

        theme.apply_theme("dark")
        theme.apply_theme(theme.FILE_THEME_PREFIX + str(p))
        check("#0E0F10" in app.styleSheet(),
              "apply_theme('file:...') dispatches to file loader")

        # unreadable file must not crash or wipe the current theme
        before = app.styleSheet()
        theme.apply_theme_file(Path(d) / "nope.qt_theme.json")
        check(app.styleSheet() == before, "missing file leaves theme intact")

    theme.apply_theme("dark")


def test_tab_settings_registry(app):
    print("theme: tab-settings registry")
    win = AppWindow("t")   # registers its QTabWidget
    cfg = tcl.default_theme_config()
    cfg["settings"]["tab_position"] = "South"
    cfg["settings"]["document_mode"] = True
    theme.apply_theme_config(cfg)
    check(win.tabs.tabPosition() == QTabWidget.TabPosition.South,
          "tab position pushed to registered tabs")
    check(win.tabs.documentMode() is True, "document mode pushed")

    # late registration picks up the active config
    late = QTabWidget()
    theme.register_tab_widget(late)
    check(late.tabPosition() == QTabWidget.TabPosition.South,
          "late-registered tabs receive active settings")

    # named theme resets to defaults
    theme.apply_theme("dark")
    check(win.tabs.tabPosition() == QTabWidget.TabPosition.North,
          "named theme resets tab position")
    check(win.tabs.documentMode() is False, "named theme resets document mode")
    win.deleteLater()


# ---------------------------------------------------------------------------
# ThemePicker
# ---------------------------------------------------------------------------
def test_theme_picker(app):
    print("widgets: ThemePicker")
    picker = ThemePicker("dark")
    emitted = []
    picker.theme_apply_requested.connect(emitted.append)

    # named selection emits the name
    picker.set_current("light")
    picker._on_apply()
    check(emitted and emitted[-1] == "light", "named theme emitted")

    # the shipped sample files appear as radios
    values = list(picker._radios.keys())
    file_values = [v for v in values if v.startswith(theme.FILE_THEME_PREFIX)]
    check(len(file_values) >= 6, "ui/themes files listed (samples + converted)")
    names = " ".join(file_values)
    check("clay.qt_theme.json" in names and
          "solarized_light.qt_theme.json" in names,
          "both sample files present")

    # selecting a file radio emits file:<path>
    picker.set_current(file_values[0])
    picker._on_apply()
    check(emitted[-1] == file_values[0], "file selection emits file:<path>")

    # custom path round-trip via set_current
    picker.set_current(theme.FILE_THEME_PREFIX + "/tmp/custom.qt_theme.json")
    picker._on_apply()
    check(emitted[-1] == theme.FILE_THEME_PREFIX + "/tmp/custom.qt_theme.json",
          "custom file selection emits file:<path>")
    picker.deleteLater()


# ---------------------------------------------------------------------------
# Shipped samples + editor round-trip
# ---------------------------------------------------------------------------
def test_samples_and_editor_roundtrip(app):
    print("samples & editor round-trip")
    themes_dir = Path(ROOT) / "ui" / "themes"
    samples = sorted(themes_dir.glob("*.qt_theme.json"))
    check(len(samples) >= 2, "two sample themes shipped in ui/themes/")

    import theme_editor
    for p in samples:
        cfg = tcl.load_theme_config(p)
        saved = theme_editor.config_for_save(cfg)
        check(saved["generated_qss"] == theme.qss_from_theme_config(cfg),
              f"{p.name}: generated_qss matches live generator")
        theme.apply_theme_file(p)
        check(cfg["palette"]["bg_primary"] in app.styleSheet(),
              f"{p.name}: applies to the app")
    theme.apply_theme("dark")

    # editor's save canonicalization is loader-stable (idempotent)
    cfg = tcl.default_theme_config()
    once = theme_editor.config_for_save(cfg)
    twice = theme_editor.config_for_save(tcl.normalize_theme_config(once))
    once.pop("app_version"), twice.pop("app_version")
    check(once == twice, "config_for_save is idempotent through normalize")


def main():
    app = build_application(app_name="theme-file-tests", initial_theme="dark")
    test_loader_normalization()
    test_loader_files()
    test_qss_generation()
    test_apply_paths(app)
    test_tab_settings_registry(app)
    test_theme_picker(app)
    test_samples_and_editor_roundtrip(app)

    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
