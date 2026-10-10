"""
ui/widgets/display_groups_editor.py
[XREF: registers-tab] "Display Groups" tab for the Decoder Editor: manages
the schema-v4 file-level `display_groups` list that lays out the live
Registers view — ordered groups, each rendered as either a headline
**banner** (top strip, dividers between) or a **pane** (side-by-side
Name/Value/Units table).

Edits mutate the DecodeEditor's live DecodeSchema in place (obtained via
schema_provider), so Save on the Decoder tab persists them; every change
emits changed() for dirty tracking and so the rule form's Group dropdown
can refresh.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)

KINDS = ["banner", "pane"]


class DisplayGroupsEditor(QWidget):
    """Signals: changed() — the schema's display_groups were modified."""

    changed = Signal()

    def __init__(self, schema_provider, parent=None):
        super().__init__(parent)
        self._provider = schema_provider
        self._loading = False
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    def _groups(self) -> list:
        return self._provider().display_groups

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        intro = QLabel(
            "Display groups define the live Registers-tab layout for this "
            "decoder (schema v4). Order here is the on-screen order: "
            "banner groups form the headline strip across the top "
            "(divider between each); pane groups are the side-by-side "
            "parameter tables below it. Assign rules to a group (and an "
            "order within it) on the Decoder tab; scalar rules without a "
            "group don't appear in the Registers view, and Bit Field rules "
            "always join the bit matrix.")
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Group Name", "Kind", "Rules"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.itemChanged.connect(self._on_name_edited)
        root.addWidget(self._table, 1)

        add_row = QHBoxLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Pack Measurements")
        self._kind_combo = QComboBox()
        self._kind_combo.addItems(KINDS)
        add_btn = QPushButton("Add Group")
        add_btn.setObjectName("btnApply")
        add_btn.clicked.connect(self._on_add)
        self._name_edit.returnPressed.connect(self._on_add)
        add_row.addWidget(QLabel("Name:"))
        add_row.addWidget(self._name_edit, 1)
        add_row.addWidget(QLabel("Kind:"))
        add_row.addWidget(self._kind_combo)
        add_row.addWidget(add_btn)
        root.addLayout(add_row)

        btn_row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove")
        self._up_btn = QPushButton("\u25B2")
        self._down_btn = QPushButton("\u25BC")
        for b in (self._up_btn, self._down_btn):
            b.setFixedWidth(34)
        self._remove_btn.clicked.connect(self._on_remove)
        self._up_btn.clicked.connect(lambda: self._on_move(-1))
        self._down_btn.clicked.connect(lambda: self._on_move(+1))
        self._table.itemSelectionChanged.connect(self._update_buttons)
        btn_row.addWidget(self._remove_btn)
        btn_row.addWidget(self._up_btn)
        btn_row.addWidget(self._down_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)
        self._update_buttons()

    # ------------------------------------------------------------------
    def refresh(self):
        """Rebuild the table from the (possibly replaced) schema."""
        self._loading = True
        groups = self._groups()
        # count rule usage per group for the Rules column
        counts = {}
        for r in self._provider().rules():
            if r.group:
                counts[r.group] = counts.get(r.group, 0) + 1
        self._table.setRowCount(0)
        for g in groups:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(g["name"]))
            combo = QComboBox()
            combo.addItems(KINDS)
            combo.setCurrentText(g.get("kind", "pane"))
            combo.currentTextChanged.connect(
                lambda kind, r=row: self._on_kind_changed(r, kind))
            self._table.setCellWidget(row, 1, combo)
            used = QTableWidgetItem(str(counts.get(g["name"], 0)))
            used.setFlags(used.flags() & ~Qt.ItemIsEditable)
            used.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 2, used)
        self._loading = False
        self._update_buttons()

    def _emit(self):
        if not self._loading:
            self.changed.emit()

    # ------------------------------------------------------------------
    def _on_add(self):
        name = self._name_edit.text().strip()
        if not name:
            return
        if any(g["name"] == name for g in self._groups()):
            self._name_edit.selectAll()
            return                              # names must be unique
        self._groups().append({"name": name,
                               "kind": self._kind_combo.currentText()})
        self._name_edit.clear()
        self.refresh()
        self._emit()

    def _on_remove(self):
        row = self._table.currentRow()
        groups = self._groups()
        if 0 <= row < len(groups):
            del groups[row]
            self.refresh()
            self._emit()

    def _on_move(self, delta: int):
        row = self._table.currentRow()
        groups = self._groups()
        j = row + delta
        if 0 <= row < len(groups) and 0 <= j < len(groups):
            groups[row], groups[j] = groups[j], groups[row]
            self.refresh()
            self._table.selectRow(j)
            self._emit()

    def _on_kind_changed(self, row: int, kind: str):
        groups = self._groups()
        if not self._loading and 0 <= row < len(groups):
            groups[row]["kind"] = kind
            self._emit()

    def _on_name_edited(self, item: QTableWidgetItem):
        if self._loading or item.column() != 0:
            return
        groups = self._groups()
        row = item.row()
        if 0 <= row < len(groups):
            new = item.text().strip()
            old = groups[row]["name"]
            if not new or new == old:
                self.refresh()
                return
            groups[row]["name"] = new
            # renaming follows through to the rules using the group
            for r in self._provider().rules():
                if r.group == old:
                    r.group = new
            self.refresh()
            self._emit()

    def _update_buttons(self):
        row = self._table.currentRow()
        n = self._table.rowCount()
        has = 0 <= row < n
        self._remove_btn.setEnabled(has)
        self._up_btn.setEnabled(has and row > 0)
        self._down_btn.setEnabled(has and row < n - 1)
