#!/usr/bin/env python3
"""
sniffer_ion.py — Ion I2C Sniffer (STM32C0 probe: NUCLEO-C031C6 today, standalone ion board when available).

Passive I2C/SMBus sniffer GUI: the NUCLEO-C031C6 board runs the
sniffer_nucleoC0_fw firmware and streams decoded transactions over its
ST-LINK virtual COM port; this app logs, filters, decodes (decoder JSON),
and exports them — the same interface as the AD2 sniffer it replaces.

Usage:
    python3 sniffer_ion.py
"""
import sys

from ui.common import build_application
from ui.sniffer_ion_window import SnifferIonWindow


def main():
    app = build_application(
        app_name="Nucleo I2C Sniffer",
        org="Digilent AD2 Utils",
        initial_theme="default",
    )
    window = SnifferIonWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
