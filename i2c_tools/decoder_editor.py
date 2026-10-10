#!/usr/bin/env python3
"""
decoder_editor.py — standalone Decoder Editor.

Create and edit decoder JSON files (register maps: names, units, formulas,
bit fields) used by the sniffers and the replay tool to annotate raw I2C
traffic. No hardware required. The same window opens in-process from the
sniffer/replay "Editor" sections; this entry point runs it on its own.

Usage:
    python3 decoder_editor.py                        # empty editor
    python3 decoder_editor.py path/to/decoder.json   # open a decoder
"""
import sys

from ui.common import build_application
from ui.decoder_editor_window import DecoderEditorWindow


def main():
    app = build_application(
        app_name="AD2 Decoder Editor",
        org="Digilent AD2 Utils",
        initial_theme="default",
    )
    open_path = sys.argv[1] if len(sys.argv) > 1 else None
    window = DecoderEditorWindow(open_path=open_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
