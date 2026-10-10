"""
decode_panel.py
Decode tab. Thin wrapper around the reusable DecodeEditor widget so the main
window keeps its existing DecodePanel API while all editing logic lives in
ui/widgets/decode_editor.py (shared with the standalone decoder editor).
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal

from ui.widgets.decode_editor import DecodeEditor


class DecodePanel(QWidget):
    """
    Emits schema_changed(DecodeSchema) whenever the in-memory schema changes
    so the log model can refresh its Decode column live.
    """

    schema_changed = Signal(object)   # DecodeSchema

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._editor = DecodeEditor(show_file_ops=True, parent=self)
        self._editor.schema_changed.connect(self.schema_changed)
        lay.addWidget(self._editor)

    # --- compatibility shims used by MainWindow / tests ---
    @property
    def schema(self):
        return self._editor.schema

    @property
    def _schema(self):
        return self._editor._schema

    @_schema.setter
    def _schema(self, value):
        self._editor._schema = value

    def _emit_changed(self):
        self._editor._emit_changed()

    def _refresh_table(self):
        self._editor._refresh_table()

    # expose editor sub-widgets for any existing test hooks
    def __getattr__(self, name):
        # Delegate unknown attribute access (e.g. _addr_edit, _table) to editor.
        editor = self.__dict__.get("_editor")
        if editor is not None and hasattr(editor, name):
            return getattr(editor, name)
        raise AttributeError(name)
