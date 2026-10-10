#!/usr/bin/env python3
"""
sniffer_ad2.py
Analog Discovery 2 passive I2C/SMBus sniffer + logger.
Entry point. (Renamed from main.py; read/write moved out of this app.)
"""

import sys
import os

# Ensure the app root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.common import build_application
from ui.sniffer_window import SnifferWindow


def main():
    app = build_application(
        app_name="AD2 Sniffer",
        org="Digilent AD2 Utils",
        initial_theme="default",
    )
    window = SnifferWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
