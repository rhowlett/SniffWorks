"""
ui.dialogs
Thin, consistent wrappers around the message boxes and file dialogs that the
panels previously called ad hoc. Centralizing these keeps wording, button
conventions, and JSON filters consistent across both apps.
"""

from ui.dialogs.message import warn, error, info, confirm
from ui.dialogs.file_dialogs import open_json, save_json, open_csv
from ui.dialogs.capture_results import CaptureResultsDialog

__all__ = ["warn", "error", "info", "confirm", "open_json", "save_json",
           "open_csv", "CaptureResultsDialog"]
