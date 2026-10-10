#!/usr/bin/env python3
"""
i2c_replay.py
Standalone application that replays a sniffer CSV capture against a decoder JSON,
displaying the result in the same transaction-log table the main app uses. Useful
for validating a decoder against real captured data without hardware.

Usage:
    python3 i2c_replay.py [capture.csv] [decoder.json]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.common import build_application
from ui.replay_window import ReplayWindow


def main():
    app = build_application(
        app_name="AD2 I2C Replay",
        org="Digilent AD2 Utils",
        initial_theme="default",
    )
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    decoder_path = sys.argv[2] if len(sys.argv) > 2 else None
    window = ReplayWindow(csv_path=csv_path, decoder_path=decoder_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
