"""
tests/test_settings_store.py — persistence of theme / serial settings
(the TODO deferred to Phase 3).

Uses a temp INI file via settings_store.set_store so the real user settings
are never touched.

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_settings_store.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import sys  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui.common import settings_store as ss  # noqa: E402

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def main():
    tmp = tempfile.TemporaryDirectory()
    ini = str(Path(tmp.name) / "settings.ini")
    ss.set_store(ss.SettingsStore(ini))

    from ui.common import build_application
    app = build_application(app_name="settings-tests", initial_theme="default")
    from ui import theme

    print("store basics")
    st = ss.store()
    check(st.get_str(ss.KEY_LAST_PORT, "x") == "x", "missing str -> default")
    check(st.get_int(ss.KEY_BAUD, 115200) == 115200, "missing int -> default")
    st.set(ss.KEY_LAST_PORT, "/dev/ttyACM0")
    st.set(ss.KEY_BAUD, 230400)
    check(st.get_str(ss.KEY_LAST_PORT) == "/dev/ttyACM0", "str round-trip")
    check(st.get_int(ss.KEY_BAUD, 0) == 230400, "int round-trip")
    # values survive a fresh store on the same file (real persistence)
    st2 = ss.SettingsStore(ini)
    check(st2.get_int(ss.KEY_BAUD, 0) == 230400, "persists across instances")

    print("theme persistence")
    theme.apply_theme("light")
    check(ss.saved_theme() == "light", "named apply persisted")
    theme.apply_theme("dark")
    check(ss.saved_theme() == "dark", "subsequent apply overwrites")
    # missing-file selection: bootstrap restore must not wipe the fallback
    theme.apply_theme("default")
    saved_before = ss.saved_theme()
    theme.apply_theme_file("/nonexistent/gone.qt_theme.json")
    check(theme.active_palette()["bg_primary"] == "#101216",
          "missing file theme leaves current theme intact")
    check(ss.saved_theme() == saved_before,
          "failed apply is not persisted")

    print("serial prefs section")
    from ui.widgets.serial_prefs_section import SerialPrefsSection
    ss.store().set(ss.KEY_BAUD, 460800)
    sec = SerialPrefsSection()
    check(sec.current_baud() == 460800, "restores persisted baud")
    sec.set_baud(921600)
    check(ss.store().get_int(ss.KEY_BAUD, 0) == 921600,
          "baud change persisted")
    sec.deleteLater()

    print("device panel preferred port")
    from ui.widgets.serial_device_panel import SerialDevicePanel
    panel = SerialDevicePanel()
    ports = [{"device": "/dev/ttyUSB9", "description": "other", "is_stlink": False},
             {"device": "/dev/ttyACM0", "description": "STLink VCP", "is_stlink": True}]
    panel.populate_ports(ports, preferred="/dev/ttyUSB9")
    check(panel.selected_port() == "/dev/ttyUSB9",
          "preferred port preselected over ST-LINK sort order")
    panel.deleteLater()

    # restore untouched defaults for anything running after us
    ss.store().set(ss.KEY_BAUD, 115200)
    theme.apply_theme("default")

    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
