"""
ui/decoder_editor_launcher.py
Open or focus the standalone Decoder Editor (`decoder_editor.py` /
`DecoderEditorWindow`) as an independent window from within another AD2 app
(the main sniffer or the replay tool).

[XREF: edit-decoder] Hosts keep a single editor instance: pass the returned
window back in as `existing` on the next call so a second click focuses the
already-open editor instead of spawning another.
"""
from typing import Optional


def _is_alive(win) -> bool:
    """True if `win` is a live Qt window (its underlying C++ object exists)."""
    if win is None:
        return False
    try:
        win.objectName()  # raises RuntimeError if the C++ object was deleted
        return True
    except RuntimeError:
        return False


def open_or_focus_decoder_editor(existing, open_path: Optional[str] = None):
    """
    Return a shown, raised DecoderEditorWindow. Reuses `existing` when it is
    still alive (preserving whatever the user had loaded/edited); otherwise
    creates a new one, opening `open_path` if given.
    """
    # Imported lazily so this module stays cheap to import and cycle-free.
    from ui.decoder_editor_window import DecoderEditorWindow

    win = existing if _is_alive(existing) else DecoderEditorWindow(open_path=open_path)
    win.show()
    win.raise_()
    win.activateWindow()
    return win
