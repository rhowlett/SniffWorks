"""
tests/test_framing_widgets.py — offscreen construction/behavior test for the
shared framing kit (P6.5): Section, Sidebar/make_tab_body, FilePickerRow, AppWindow.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_framing_widgets.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.common import build_application  # noqa: E402
from PySide6.QtWidgets import QPushButton, QTabWidget, QWidget  # noqa: E402
from ui.widgets import (  # noqa: E402
    Section, Sidebar, make_tab_body, FilePickerRow, AppWindow,
)


def test_section():
    s = Section("Table Data")
    assert s.title() == "Table Data"
    s.add_row(QPushButton("Clear Log"), QPushButton("Export CSV"))
    s.add_widget(QPushButton("x"))


def test_sidebar_and_tab_body():
    sb = Sidebar()
    sb.add_section(Section("A"))
    sb.add_section(Section("B"))
    sb.add_stretch()
    assert sb.maximumWidth() == Sidebar.DEFAULT_MAX_WIDTH
    main = QWidget()
    body = make_tab_body(sb, main)
    assert isinstance(body, QWidget)
    # both children present
    assert sb.parent() is body and main.parent() is body


def test_file_picker_transitions():
    picks = {"path": "/tmp/good.json"}

    def open_fn(_parent):
        return picks["path"]

    def validator(path):
        if path.endswith("good.json"):
            return True, "2 rules"
        return False, "parse error"

    fp = FilePickerRow("Select JSON File", open_fn, validator)
    # initial
    assert fp.path() is None and fp.is_valid() is False
    assert fp._status.objectName() == "mutedLabel"
    assert fp._status.text() == "none"
    # valid pick
    fp._on_open()
    assert fp.path() == "/tmp/good.json" and fp.is_valid() is True
    assert fp._status.objectName() == "statusOk"
    assert "good.json" in fp._status.text() and "✓" in fp._status.text()
    # invalid pick
    picks["path"] = "/tmp/bad.json"
    fp._on_open()
    assert fp.is_valid() is False
    assert fp._status.objectName() == "statusError"
    assert "✗" in fp._status.text()
    # clear
    fp.clear()
    assert fp.path() is None and fp._status.objectName() == "mutedLabel"


def test_app_window():
    w = AppWindow("Test")
    assert w.windowTitle() == "Test"
    assert w.tabs.tabPosition() == QTabWidget.North
    idx = w.add_tab(QWidget(), "One")
    assert idx == 0 and w.tabs.tabText(0) == "One"


def test_help_panel():
    from ui.widgets import HelpPanel
    hp = HelpPanel("i2c_replay")
    html = hp._browser.toHtml()
    assert len(html) > 1000 and "<table" in html.lower()
    hp.refresh()   # re-render (theme change) must not raise


def test_exit_panel():
    from ui.widgets import ExitPanel
    from PySide6.QtWidgets import QPushButton
    fired = {"n": 0}
    ep = ExitPanel("Test App")
    ep.exit_requested.connect(lambda: fired.__setitem__("n", fired["n"] + 1))
    btn = ep.findChild(QPushButton)
    assert btn is not None
    btn.click()
    assert fired["n"] == 1


def _run():
    build_application(app_name="Framing Test", version="1.0.0",
                      org="Digilent AD2 Utils", initial_theme="dark")
    tests = [
        ("section", test_section),
        ("sidebar_and_tab_body", test_sidebar_and_tab_body),
        ("file_picker_transitions", test_file_picker_transitions),
        ("app_window", test_app_window),
        ("help_panel", test_help_panel),
        ("exit_panel", test_exit_panel),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            print(f"  ERROR {name}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
