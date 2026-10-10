"""
tests/test_common_refactor.py  [v0.1] — the shared-behavior refactor:
  1. theme.signals.changed fires for named and file themes
  2. HelpTab re-renders itself on theme change (no window wiring)
  3. LogPanel repaints its model on theme change
  4. StatusBarNotifier.notify uses the standard timeout
  5. ConfirmingCloseMixin: guard / confirm / on_close flow
  6. EditorSection: self-managed launch + close_editor

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_common_refactor.py
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
from ui import theme  # noqa: E402
from ui.tabs import HelpTab, ExitTab  # noqa: E402
from ui.widgets import AppWindow  # noqa: E402
from ui.widgets import sidebar_sections  # noqa: E402
from ui.log_panel import LogPanel  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def test_theme_signal(app):
    print("theme.signals.changed")
    got = []
    theme.signals.changed.connect(got.append)
    theme.apply_theme("light")
    check(got and got[-1] == "light", "named apply emits selection")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sig.qt_theme.json"
        p.write_text(json.dumps({"palette": {"bg_primary": "#0A0B0C"}}))
        n_before = len(got)
        theme.apply_theme(theme.FILE_THEME_PREFIX + str(p))
        check(len(got) == n_before + 1, "file apply emits exactly once")
        check(got[-1] == theme.FILE_THEME_PREFIX + str(p),
              "file apply emits the file: selection")
    theme.apply_theme("default")
    theme.signals.changed.disconnect(got.append)


def test_help_tab_auto_refresh(app):
    print("HelpTab auto-refresh")
    with tempfile.TemporaryDirectory() as d:
        md = Path(d) / "guide.md"
        md.write_text("# Guide\n\nHello **world**.\n")
        tab = HelpTab(md, "Test App", "blurb")
        theme.apply_theme("light")
        light_html = tab._browser.toHtml()
        theme.apply_theme("dark")
        dark_html = tab._browser.toHtml()
        check(light_html != dark_html,
              "guide re-renders on theme change without window wiring")
        tab.deleteLater()
    theme.apply_theme("default")


def test_log_panel_auto_repaint(app):
    print("LogPanel auto-repaint")
    panel = LogPanel(show_toolbar=False)
    hits = []
    panel.model.layoutChanged.connect(lambda *a: hits.append(1))
    theme.apply_theme("light")
    check(len(hits) >= 1, "model.layoutChanged emitted on theme change")
    panel.deleteLater()
    theme.apply_theme("default")


def test_notify(app):
    print("StatusBarNotifier.notify")
    win = AppWindow("Notify Test")
    win.notify("hello")
    check(win.statusBar().currentMessage() == "hello", "notify shows message")
    win.notify("stay", sticky=True)
    check(win.statusBar().currentMessage() == "stay", "sticky notify shows")
    win.deleteLater()


def test_confirming_close(app):
    print("ConfirmingCloseMixin")
    closed = []

    class GuardedWindow(AppWindow):
        def __init__(self, guard_msg):
            super().__init__("Guard Test")
            self._guard_msg = guard_msg
        def close_guard(self):
            return self._guard_msg
        def on_close(self):
            closed.append(True)

    # no guard -> closes, on_close runs
    w = GuardedWindow(None)
    w.show(); w.close()
    check(closed == [True], "no guard: close accepted + on_close ran")

    # guard + user declines (patch dialogs.confirm)
    from ui import dialogs
    orig = dialogs.confirm
    dialogs.confirm = lambda *a, **k: False
    w2 = GuardedWindow("really?")
    w2.show(); w2.close()
    check(w2.isVisible(), "guard declined: window stays open")
    dialogs.confirm = lambda *a, **k: True
    w2.close()
    check(not w2.isVisible(), "guard accepted: window closes")
    dialogs.confirm = orig
    w2.deleteLater()

    # the shared confirm dialog offers OK / Cancel (not Yes / No) in every app
    from PySide6.QtWidgets import QMessageBox
    seen = {}
    orig_q = QMessageBox.question
    def fake_q(parent, title, text, buttons=None, default=None):
        seen["buttons"], seen["default"] = buttons, default
        return QMessageBox.Cancel
    QMessageBox.question = staticmethod(fake_q)
    try:
        ok = dialogs.confirm(None, "Exit", "really?")
    finally:
        QMessageBox.question = orig_q
    check(seen.get("buttons") == (QMessageBox.Ok | QMessageBox.Cancel)
          and seen.get("default") == QMessageBox.Ok and ok is False,
          "confirm dialog: OK/Cancel buttons, OK default, Cancel -> False")

    # ExitTab drives the same path
    closed.clear()
    w3 = GuardedWindow(None)
    tab = ExitTab("Guard Test")
    tab.exit_requested.connect(w3.close)
    w3.show()
    tab.exit_requested.emit()
    check(closed == [True], "Exit tab uses the same close path")
    w3.deleteLater(); tab.deleteLater()


def test_editor_section(app):
    print("EditorSection self-managed")
    launches = []

    class FakeEditor:
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True

    def fake_open_or_focus(existing, open_path=None):
        launches.append(open_path)
        return existing or FakeEditor()

    import ui.decoder_editor_launcher as launcher
    orig = launcher.open_or_focus_decoder_editor
    launcher.open_or_focus_decoder_editor = fake_open_or_focus
    try:
        sec = sidebar_sections.EditorSection(
            path_provider=lambda: "/tmp/dec.json")
        emitted = []
        sec.launch_requested.connect(lambda: emitted.append(1))
        sec._on_launch()
        check(launches == ["/tmp/dec.json"],
              "launch uses path_provider automatically")
        check(emitted == [1], "launch_requested still emitted")
        first = sec._editor_win
        sec.launch()
        check(sec._editor_win is first, "second launch focuses same window")
        sec.close_editor()
        check(first.closed and sec._editor_win is None,
              "close_editor closes and clears the child window")

        # opt-out mode: signal only
        launches.clear()
        sec2 = sidebar_sections.EditorSection(self_managed=False)
        sec2._on_launch()
        check(launches == [], "self_managed=False does not launch")
        sec2.deleteLater()
        sec.deleteLater()
    finally:
        launcher.open_or_focus_decoder_editor = orig


def main():
    app = build_application(app_name="refactor-tests", initial_theme="default")
    test_theme_signal(app)
    test_help_tab_auto_refresh(app)
    test_log_panel_auto_repaint(app)
    test_notify(app)
    test_confirming_close(app)
    test_editor_section(app)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
