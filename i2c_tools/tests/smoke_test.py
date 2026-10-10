#!/usr/bin/env python3
"""
tests/smoke_test.py — headless smoke test for every AD2 I2C Tool application.

Usage:
    QT_QPA_PLATFORM=offscreen python3 tests/smoke_test.py

What it does (no hardware, no WaveForms SDK, no serial port required):
  1. Builds the QApplication once via ui.common.build_application.
  2. Constructs, shows, pumps events for, and closes each app window:
     SnifferWindow, DecoderEditorWindow, ReplayWindow, BQ76905GatewayTool.
  3. Applies every theme in ui.theme.THEME_CHOICES and asserts the palette
     resolves to a non-empty dict.
  4. Prints PASS/FAIL per app and per theme; exits non-zero if anything failed.

This file does not modify any application code. It is the per-prompt regression
check for the refactor series (run it after every prompt).
"""

import os
# Force offscreen rendering before any Qt import so the harness needs no display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import sys
import importlib
import traceback

# Project root is the parent of this tests/ directory; put it on the path so the
# app modules import the same way they do when launched normally.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ui.common import build_application          # noqa: E402
from ui import theme                             # noqa: E402
from PySide6.QtWidgets import QMessageBox        # noqa: E402


# App windows to construct: (label, module, class name, kwargs).
APPS = [
    ("sniffer_ad2.py     → SnifferWindow",       "ui.sniffer_window",        "SnifferWindow",       {}),
    ("decoder_editor.py  → DecoderEditorWindow", "ui.decoder_editor_window", "DecoderEditorWindow", {}),
    ("i2c_replay.py      → ReplayWindow",        "ui.replay_window",         "ReplayWindow",        {}),
    ("sniffer_ion.py → SnifferIonWindow",       "ui.sniffer_ion_window", "SnifferIonWindow", {}),
    ("bq76905_gateway.py → BQ76905GatewayTool",  "bq76905_gateway_tool",     "BQ76905GatewayTool",  {}),
]


def _silence_dialogs():
    """Neutralize modal message boxes so nothing can block the headless run
    (e.g. the main window's non-fatal 'WaveForms not found' warning)."""
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.NoButton)
    QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.NoButton)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.NoButton)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)


def _pump(app, cycles: int = 5):
    for _ in range(cycles):
        app.processEvents()


def check_apps(app):
    results = []
    for label, module_name, class_name, kwargs in APPS:
        try:
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            win = cls(**kwargs)
            win.show()
            _pump(app)
            win.close()
            _pump(app)
            results.append((label, True, ""))
        except Exception:
            last = traceback.format_exc().strip().splitlines()[-1]
            results.append((label, False, last))
    return results


def check_themes():
    results = []
    for name, _human in theme.THEME_CHOICES:
        try:
            theme.apply_theme(name)
            palette = theme.active_palette()
            ok = bool(palette)
            results.append((name, ok, "" if ok else "empty palette"))
        except Exception as exc:
            results.append((name, False, str(exc)))
    return results


def main() -> int:
    app = build_application(app_name="AD2 Smoke Test", version="1.0.0",
                            org="Digilent AD2 Utils", initial_theme="dark")
    _silence_dialogs()

    app_results = check_apps(app)
    theme_results = check_themes()

    print("== App construction ==")
    for label, ok, msg in app_results:
        line = f"  {'PASS' if ok else 'FAIL'}  {label}"
        if not ok:
            line += f"   -> {msg}"
        print(line)

    print("== Themes ==")
    for name, ok, msg in theme_results:
        line = f"  {'PASS' if ok else 'FAIL'}  {name}"
        if not ok:
            line += f"   -> {msg}"
        print(line)

    failures = [r for r in app_results + theme_results if not r[1]]
    total = len(app_results) + len(theme_results)
    print(f"\n{total - len(failures)}/{total} checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
