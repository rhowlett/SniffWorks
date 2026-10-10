"""
ui.widgets.decode_editor
A self-contained decode-schema editor: rule editor, rules table, live Test
field, and New/Load/Save/Save-As file operations. Embedded by both the main
tool's Decode tab and the standalone decoder editor.

Function Type selector [Decimal | Hex | Bit Field] drives the form:
  - Decimal  : float math (X*0.001, X/16); shown as number + unit.
  - Hex      : integer/logic/shift math (X<<2, X&0xF0); shown as 0xNN.
  - Bit Field: no scalar function; the value's bits are sliced into named fields.
               Each field is an inclusive [high..low] range with one name per
               possible value (a field of N bits needs 2**N names).

Two layouts via the `layout` flag: "form" (compact, used by the Decode tab so
main.py is unchanged) and "sections" (grouped, used by the standalone editor).

Signals:
    schema_changed(DecodeSchema)
    path_changed(str)
"""

from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QSpinBox, QRadioButton,
    QButtonGroup, QFrame, QStackedWidget,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from core.decode_schema import (
    DecodeSchema, DecodeRule, BitField, evaluate_function, DecodeError,
)
from ui.common.hexutil import HexParseError
from ui.widgets.hex_line_edit import HexLineEdit
from ui import dialogs

FUNC_HELP_DEC = "Decimal: float math on X, e.g.  X*0.001+0.25  ·  X/16  ·  X*0.1"
FUNC_HELP_HEX = "Hex: integer/logic/shift on X, e.g.  X<<2  ·  X & 0xF0  ·  (X>>4)&0x0F   (shown as 0xNN)"
FUNC_HELP_BITS = "Bit Field: slice the value into named fields. Each field needs one name per value (N bits -> 2^N names)."

FMT_LABELS = [("Decimal", "dec"), ("Hex", "hex"), ("Bit Field", "bits")]


class DecodeEditor(QWidget):
    schema_changed = Signal(object)
    path_changed = Signal(str)

    DIR_OPTIONS = ["R", "W", "*"]
    MAX_DATA_BYTES = 64

    def __init__(self, show_file_ops: bool = True, layout: str = "form", parent=None):
        super().__init__(parent)
        self._schema = DecodeSchema()
        self._current_path = None
        self._show_file_ops = show_file_ops
        self._layout_mode = layout if layout in ("form", "sections") else "form"
        self._build_widgets()
        self._build_ui()
        self.refresh_group_choices()
        self._on_fmt_changed()

    # ------------------------------------------------------------------
    # Shared widget construction
    # ------------------------------------------------------------------
    def _build_widgets(self):
        # RULE
        self._addr_edit = HexLineEdit("0x08", "0x08"); self._addr_edit.setMaximumWidth(110)
        self._dir_combo = QComboBox(); self._dir_combo.addItems(self.DIR_OPTIONS); self._dir_combo.setMaximumWidth(90)
        self._reg_edit = HexLineEdit("", "0x14 (blank=any)"); self._reg_edit.setMaximumWidth(130)
        self._name_edit = QLineEdit(); self._name_edit.setPlaceholderText("e.g. Cell 1 Voltage")
        self._unit_edit = QLineEdit(); self._unit_edit.setPlaceholderText("mV, mm, °C"); self._unit_edit.setMaximumWidth(110)

        # Function Type
        self._fmt_combo = QComboBox()
        for label, _ in FMT_LABELS:
            self._fmt_combo.addItem(label)
        self._fmt_combo.setMaximumWidth(130)
        self._fmt_combo.currentIndexChanged.connect(self._on_fmt_changed)

        # Function expression (Decimal/Hex)
        self._func_edit = QLineEdit()
        self._func_edit.setPlaceholderText("X*0.001+0.25   |   X<<2   |   X & 0xF0")
        self._func_edit.setFont(QFont("Courier New", 10))

        self._func_help = QLabel(FUNC_HELP_DEC)
        self._func_help.setObjectName("mutedLabel"); self._func_help.setWordWrap(True)

        # DATA
        self._order_be = QRadioButton("Big Endian")
        self._order_le = QRadioButton("Little Endian")
        self._order_be.setChecked(True)
        self._order_group = QButtonGroup(self)
        self._order_group.addButton(self._order_be); self._order_group.addButton(self._order_le)
        self._signed_check = QCheckBox("2's Complement")
        self._nbytes_spin = QSpinBox(); self._nbytes_spin.setRange(0, self.MAX_DATA_BYTES)
        self._nbytes_spin.setSpecialValueText("any"); self._nbytes_spin.setValue(0); self._nbytes_spin.setMaximumWidth(90)

        # BIT FIELD editor
        self._bf_table = QTableWidget(0, 4)
        self._bf_table.setHorizontalHeaderLabels(["High", "Low", "Mode", "Names / Function·Unit"])
        self._bf_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._bf_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._bf_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._bf_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._bf_table.setMinimumHeight(120)
        self._bf_hi = QSpinBox(); self._bf_hi.setRange(0, 63); self._bf_hi.setMaximumWidth(70)
        self._bf_lo = QSpinBox(); self._bf_lo.setRange(0, 63); self._bf_lo.setMaximumWidth(70)
        self._bf_mode = QComboBox(); self._bf_mode.addItems(["enum", "scale", "raw"]); self._bf_mode.setMaximumWidth(80)
        self._bf_fieldname = QLineEdit(); self._bf_fieldname.setPlaceholderText("field name"); self._bf_fieldname.setMaximumWidth(130)
        self._bf_names = QLineEdit(); self._bf_names.setPlaceholderText("enum: Off, On   ·   scale: X*122.1 | us | 0=disabled")
        self._bf_add_btn = QPushButton("Add Field"); self._bf_add_btn.clicked.connect(self._on_bf_add)
        self._bf_del_btn = QPushButton("Remove Field"); self._bf_del_btn.clicked.connect(self._on_bf_remove)

        # DISPLAY (Registers tab, schema v4)  [XREF: registers-tab]
        self._group_combo = QComboBox()
        self._group_combo.setEditable(True)
        self._group_combo.setMinimumWidth(160)
        self._group_combo.lineEdit().setPlaceholderText("(not shown)")
        self._group_order_spin = QSpinBox()
        self._group_order_spin.setRange(0, 999)
        self._group_order_spin.setMaximumWidth(80)
        self._access_combo = QComboBox()
        self._access_combo.addItems(["", "R", "W", "R/W"])
        self._access_combo.setMaximumWidth(80)
        self._display_help = QLabel(
            "Registers tab: rules with a Group appear in that group of the "
            "live view (order sorts within it); Bit Field rules always join "
            "the bit matrix. Access W shows the writable pencil. Define "
            "groups on the Display Groups tab.")
        self._display_help.setObjectName("mutedLabel")
        self._display_help.setWordWrap(True)

        # TEST
        self._test_btn = QPushButton("Test"); self._test_btn.clicked.connect(self._on_test)
        self._test_input = HexLineEdit("", "test data hex e.g. 14 74 0E"); self._test_input.setFont(QFont("Courier New", 10))
        self._test_result = QLabel(""); self._test_result.setObjectName("mutedLabel")

        # SAVE
        self._add_btn = QPushButton("Add / Update Rule"); self._add_btn.setObjectName("btnApply")
        self._add_btn.clicked.connect(self._on_add_rule)
        self._clear_fields_btn = QPushButton("Clear"); self._clear_fields_btn.clicked.connect(self._clear_fields)

    # ------------------------------------------------------------------
    # Format helpers
    # ------------------------------------------------------------------
    def _fmt_value(self) -> str:
        return FMT_LABELS[self._fmt_combo.currentIndex()][1]

    def _set_fmt(self, fmt: str):
        for i, (_, v) in enumerate(FMT_LABELS):
            if v == fmt:
                self._fmt_combo.setCurrentIndex(i); return
        self._fmt_combo.setCurrentIndex(0)

    def _on_fmt_changed(self, *_):
        fmt = self._fmt_value()
        is_bits = (fmt == "bits")
        # Show function row for dec/hex, bit-field editor for bits.
        if hasattr(self, "_func_stack"):
            self._func_stack.setCurrentIndex(1 if is_bits else 0)
        self._func_help.setText(
            FUNC_HELP_BITS if is_bits else (FUNC_HELP_HEX if fmt == "hex" else FUNC_HELP_DEC)
        )
        # Unit is meaningless for bit fields.
        self._unit_edit.setEnabled(not is_bits)

    def _byte_order(self) -> str:
        return "le" if self._order_le.isChecked() else "be"

    def _set_byte_order(self, order):
        (self._order_le if str(order).lower() in ("le", "little") else self._order_be).setChecked(True)

    def _data_bytes(self):
        v = self._nbytes_spin.value()
        return None if v == 0 else v

    def _set_data_bytes(self, n):
        self._nbytes_spin.setValue(0 if not n else int(n))

    # ------------------------------------------------------------------
    # Bit-field editor table
    # ------------------------------------------------------------------
    def _on_bf_mode_changed(self, mode):
        if mode == "enum":
            self._bf_names.setPlaceholderText("enum: comma-separated names, e.g.  Off, On  (2^N names)")
            self._bf_fieldname.setEnabled(True)
        elif mode == "scale":
            self._bf_names.setPlaceholderText("scale: function | unit | special  e.g.  X*122.1 | us | 0=PWM disabled")
            self._bf_fieldname.setEnabled(True)
        else:  # raw
            self._bf_names.setPlaceholderText("raw: optional unit, e.g.  counts")
            self._bf_fieldname.setEnabled(True)

    def _parse_bf_spec(self, hi, lo, mode, fieldname, spec):
        """Build a BitField from the entry-row spec string for the given mode."""
        width = hi - lo + 1
        if mode == "enum":
            names = [n.strip() for n in spec.split(",") if n.strip() != ""]
            expected = 1 << width
            if len(names) != expected:
                return None, (f"A [{hi}:{lo}] enum field spans {width} bit(s) and needs "
                              f"exactly {expected} names. You gave {len(names)}.")
            return BitField(high=hi, low=lo, names=names, mode="enum", name=fieldname), None
        if mode == "scale":
            # "function | unit | special" where special is "v=label,v=label"
            parts = [p.strip() for p in spec.split("|")]
            func = parts[0] if parts and parts[0] else "X"
            unit = parts[1] if len(parts) > 1 else ""
            special = None
            if len(parts) > 2 and parts[2]:
                special = {}
                for kv in parts[2].split(","):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        try:
                            special[int(k.strip(), 0)] = v.strip()
                        except ValueError:
                            pass
            return BitField(high=hi, low=lo, mode="scale", function=func,
                            unit=unit, special=special, name=fieldname), None
        # raw
        return BitField(high=hi, low=lo, mode="raw", unit=spec.strip(), name=fieldname), None

    def _on_bf_add(self):
        hi, lo = self._bf_hi.value(), self._bf_lo.value()
        if hi < lo:
            hi, lo = lo, hi
        mode = self._bf_mode.currentText()
        bf, err = self._parse_bf_spec(hi, lo, mode, self._bf_fieldname.text().strip(),
                                      self._bf_names.text())
        if err:
            dialogs.warn(self, "Bit Field", err); return
        r = self._bf_table.rowCount()
        self._bf_table.insertRow(r)
        self._set_bf_row(r, bf)
        self._bf_names.clear(); self._bf_fieldname.clear()

    def _bf_spec_text(self, bf) -> str:
        if bf.mode == "enum":
            return ", ".join(bf.names or [])
        if bf.mode == "scale":
            sp = ""
            if bf.special:
                sp = " | " + ",".join(f"{k}={v}" for k, v in bf.special.items())
            return f"{bf.function} | {bf.unit}{sp}"
        return bf.unit  # raw

    def _set_bf_row(self, r, bf):
        self._bf_table.setItem(r, 0, QTableWidgetItem(str(bf.high)))
        self._bf_table.setItem(r, 1, QTableWidgetItem(str(bf.low)))
        mode_cell = QTableWidgetItem(bf.mode)
        # stash field name on the mode cell for round-trip
        mode_cell.setData(Qt.UserRole, bf.name or "")
        self._bf_table.setItem(r, 2, mode_cell)
        self._bf_table.setItem(r, 3, QTableWidgetItem(self._bf_spec_text(bf)))

    def _on_bf_remove(self):
        r = self._bf_table.currentRow()
        if r >= 0:
            self._bf_table.removeRow(r)

    def _collect_bit_fields(self):
        fields = []
        for r in range(self._bf_table.rowCount()):
            hi = int(self._bf_table.item(r, 0).text())
            lo = int(self._bf_table.item(r, 1).text())
            mode_cell = self._bf_table.item(r, 2)
            mode = mode_cell.text()
            fieldname = mode_cell.data(Qt.UserRole) or ""
            spec = self._bf_table.item(r, 3).text()
            bf, err = self._parse_bf_spec(hi, lo, mode, fieldname, spec)
            if bf is not None:
                fields.append(bf)
        return fields

    def _load_bit_fields(self, bit_fields):
        self._bf_table.setRowCount(0)
        for bf in (bit_fields or []):
            r = self._bf_table.rowCount()
            self._bf_table.insertRow(r)
            self._set_bf_row(r, bf)

    # ------------------------------------------------------------------
    # Top-level layout
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)
        if self._layout_mode == "sections":
            self._build_layout_b(root)
        else:
            root.addWidget(self._build_editor_form())
            root.addWidget(self._build_table_box())
            if self._show_file_ops:
                root.addWidget(self._build_file_box())
            root.addStretch()

    def _build_layout_b(self, root):
        """
        Tiled compact layout: a top strip of three side-by-side group boxes
        (Rule | Data | Save), then the Function/Bit-Field area and Test row,
        then the Schema Rules table filling all remaining space, then one
        compact bottom bar (table buttons + file ops).
        """
        # --- top strip: Rule | Data | Save ---
        strip = QHBoxLayout(); strip.setSpacing(6)
        strip.addWidget(self._build_rule_box(), 3)
        strip.addWidget(self._build_data_box(), 1)
        strip.addWidget(self._build_save_box(), 0)
        root.addLayout(strip)

        # --- function / bit-field area (swaps with Function Type) ---
        from PySide6.QtWidgets import QSizePolicy
        func_box = QGroupBox("Function / Bit Fields")
        fb = QVBoxLayout(func_box); fb.setContentsMargins(8, 4, 8, 4); fb.setSpacing(3)
        fb.addWidget(self._make_func_stack())
        fb.addWidget(self._func_help)
        func_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._func_box = func_box
        root.addWidget(func_box)

        # --- test row ---
        test_row = QHBoxLayout()
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._test_input, 1)
        test_row.addWidget(QLabel("Data :"))
        test_row.addWidget(self._test_result, 2)
        root.addLayout(test_row)

        # --- schema rules table (fills remaining space) ---
        root.addWidget(self._build_table_box(), 1)

        # --- compact bottom bar: table buttons (left) + file ops (right) ---
        if self._show_file_ops:
            root.addLayout(self._build_bottom_bar())

    def _build_rule_box(self) -> QGroupBox:
        box = QGroupBox("Rule")
        grid = QGridLayout(box); grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(8); grid.setVerticalSpacing(2)
        # row 0: captions / row 1: widgets  (Address, Direction, Register)
        grid.addWidget(QLabel("Address (Hex)"), 0, 0)
        grid.addWidget(QLabel("Direction"), 0, 1)
        grid.addWidget(QLabel("Register (Hex)"), 0, 2)
        grid.addWidget(self._addr_edit, 1, 0)
        grid.addWidget(self._dir_combo, 1, 1)
        grid.addWidget(self._reg_edit, 1, 2)
        # row 2: captions / row 3: widgets  (Name, Function Type, Unit)
        grid.addWidget(QLabel("Name"), 2, 0)
        grid.addWidget(QLabel("Function Type"), 2, 1)
        grid.addWidget(QLabel("Unit"), 2, 2)
        grid.addWidget(self._name_edit, 3, 0)
        grid.addWidget(self._fmt_combo, 3, 1)
        grid.addWidget(self._unit_edit, 3, 2)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        return box

    def _build_data_box(self) -> QGroupBox:
        box = QGroupBox("Data")
        grid = QGridLayout(box); grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(10); grid.setVerticalSpacing(2)
        grid.addWidget(QLabel("Byte Order"), 0, 0)
        grid.addWidget(self._order_be, 1, 0)
        grid.addWidget(self._order_le, 2, 0)
        grid.addWidget(QLabel("Signed"), 0, 1)
        grid.addWidget(self._signed_check, 1, 1)
        grid.addWidget(QLabel("# Data Bytes"), 0, 2, Qt.AlignRight)
        grid.addWidget(self._nbytes_spin, 1, 2, Qt.AlignRight)
        return box

    def _build_save_box(self) -> QGroupBox:
        box = QGroupBox("Save")
        v = QVBoxLayout(box); v.setContentsMargins(8, 6, 8, 6); v.setSpacing(4)
        v.addWidget(self._add_btn)
        v.addWidget(self._clear_fields_btn)
        v.addStretch()
        return box

    def _build_bottom_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(self._remove_btn)
        bar.addWidget(self._clear_btn)
        bar.addStretch()
        # file ops on the right
        self._path_lbl = QLabel("In-memory only")
        self._path_lbl.setObjectName("mutedLabel")
        bar.addWidget(self._path_lbl)
        sep = QFrame(); sep.setFrameShape(QFrame.VLine); sep.setFrameShadow(QFrame.Sunken)
        bar.addWidget(sep)
        self._new_btn = QPushButton("New"); self._new_btn.clicked.connect(self.new_schema); bar.addWidget(self._new_btn)
        self._load_btn = QPushButton("Load…"); self._load_btn.clicked.connect(self.load_dialog); bar.addWidget(self._load_btn)
        self._save_btn = QPushButton("Save"); self._save_btn.clicked.connect(self.save); bar.addWidget(self._save_btn)
        self._save_as_btn = QPushButton("Save As…"); self._save_as_btn.clicked.connect(self.save_as); bar.addWidget(self._save_as_btn)
        self._capture_btn = QPushButton("Test Against Capture (CSV)…")
        self._capture_btn.clicked.connect(self.test_against_capture); bar.addWidget(self._capture_btn)
        return bar

    def _make_func_stack(self) -> QStackedWidget:
        """Page 0: function line edit (dec/hex). Page 1: bit-field editor."""
        from PySide6.QtWidgets import QSizePolicy
        stack = QStackedWidget()

        page_func = QWidget()
        pf = QVBoxLayout(page_func); pf.setContentsMargins(0, 0, 0, 0)
        pf.addWidget(self._func_edit)
        pf.addStretch()
        page_func.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        stack.addWidget(page_func)

        page_bits = QWidget()
        pb = QVBoxLayout(page_bits); pb.setContentsMargins(0, 0, 0, 0); pb.setSpacing(4)
        entry = QHBoxLayout()
        entry.addWidget(QLabel("High")); entry.addWidget(self._bf_hi)
        entry.addWidget(QLabel("Low")); entry.addWidget(self._bf_lo)
        entry.addWidget(QLabel("Mode")); entry.addWidget(self._bf_mode)
        entry.addWidget(self._bf_fieldname)
        entry.addWidget(self._bf_names, 1)
        entry.addWidget(self._bf_add_btn); entry.addWidget(self._bf_del_btn)
        pb.addLayout(entry)
        pb.addWidget(self._bf_table)
        stack.addWidget(page_bits)

        # Size the stack to the CURRENT page only, so Decimal/Hex (just a line
        # edit) doesn't reserve the tall bit-field editor's height.
        page_bits.setMinimumHeight(190)

        def _fit(idx):
            # Function page is a single line edit -> compact; bit-field page ->
            # tall enough for the entry row + a few table rows. Setting the stack
            # height explicitly keeps the schema table large in Decimal/Hex mode.
            if idx == 0:
                self._func_stack.setMinimumHeight(36)
                self._func_stack.setMaximumHeight(48)
            else:
                self._func_stack.setMinimumHeight(190)
                self._func_stack.setMaximumHeight(240)
        self._func_stack = stack
        _fit(stack.currentIndex())
        stack.currentChanged.connect(_fit)
        return stack

    # ---- form layout (Decode tab) ----
    def _build_editor_form(self) -> QGroupBox:
        box = QGroupBox("Add / Update Rule")
        form = QFormLayout(box); form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Address (hex):", self._addr_edit)
        form.addRow("Direction:", self._dir_combo)
        form.addRow("Register (hex):", self._reg_edit)

        order_row = QHBoxLayout(); order_row.addWidget(self._order_be); order_row.addWidget(self._order_le); order_row.addStretch()
        oh = QWidget(); oh.setLayout(order_row); form.addRow("Byte order:", oh)
        form.addRow("", self._signed_check)
        form.addRow("# data bytes:", self._nbytes_spin)
        form.addRow("Name:", self._name_edit)
        form.addRow("Unit:", self._unit_edit)
        form.addRow("Function Type:", self._fmt_combo)
        form.addRow("Function:", self._make_func_stack())
        form.addRow(self._func_help)

        form.addRow("Display group:", self._group_combo)
        form.addRow("Group order:", self._group_order_spin)
        form.addRow("Access:", self._access_combo)

        btn_row = QHBoxLayout(); btn_row.addWidget(self._add_btn); btn_row.addWidget(self._test_btn)
        form.addRow(btn_row)
        form.addRow("Test data:", self._test_input)
        form.addRow("Result:", self._test_result)
        return box

    # ---- sections layout (standalone) ----
    def _section_label(self, text):
        lbl = QLabel(text); f = lbl.font(); f.setBold(True); lbl.setFont(f); return lbl

    def _hline(self):
        ln = QFrame(); ln.setFrameShape(QFrame.HLine); ln.setFrameShadow(QFrame.Sunken); return ln

    def _labeled(self, label, widget):
        cell = QWidget(); v = QVBoxLayout(cell); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
        cap = QLabel(label); cap.setObjectName("mutedLabel")
        v.addWidget(cap); v.addWidget(widget); return cell

    def _build_editor_sections(self) -> QGroupBox:
        box = QGroupBox("Add / Update Rule")
        outer = QVBoxLayout(box); outer.setSpacing(6)

        outer.addWidget(self._section_label("RULE:"))
        rule_row = QHBoxLayout()
        rule_row.addWidget(self._labeled("Address (Hex)", self._addr_edit))
        rule_row.addWidget(self._labeled("Direction", self._dir_combo))
        rule_row.addWidget(self._labeled("Register (Hex)", self._reg_edit))
        rule_row.addWidget(self._labeled("Name", self._name_edit), 1)
        rule_row.addWidget(self._labeled("Function Type", self._fmt_combo))
        rule_row.addWidget(self._labeled("Unit", self._unit_edit))
        outer.addLayout(rule_row)
        outer.addWidget(self._labeled("Function / Bit Fields", self._make_func_stack()))
        outer.addWidget(self._func_help)

        outer.addWidget(self._hline())
        outer.addWidget(self._section_label("DATA:"))
        data_row = QHBoxLayout()
        order_cell = QWidget(); ov = QVBoxLayout(order_cell); ov.setContentsMargins(0, 0, 0, 0); ov.setSpacing(2)
        ov.addWidget(QLabel("Byte Order")); ov.addWidget(self._order_be); ov.addWidget(self._order_le)
        data_row.addWidget(order_cell)
        signed_cell = QWidget(); sv = QVBoxLayout(signed_cell); sv.setContentsMargins(0, 0, 0, 0); sv.setSpacing(2)
        sv.addWidget(QLabel("Signed")); sv.addWidget(self._signed_check); sv.addStretch()
        data_row.addWidget(signed_cell)
        data_row.addStretch()
        data_row.addWidget(self._labeled("# of Data Bytes", self._nbytes_spin))
        outer.addLayout(data_row)

        outer.addWidget(self._hline())
        outer.addWidget(self._section_label("DISPLAY (Registers tab):"))
        disp_row = QHBoxLayout()
        disp_row.addWidget(self._labeled("Group", self._group_combo))
        disp_row.addWidget(self._labeled("Order", self._group_order_spin))
        disp_row.addWidget(self._labeled("Access", self._access_combo))
        disp_row.addStretch()
        outer.addLayout(disp_row)
        outer.addWidget(self._display_help)

        outer.addWidget(self._hline())
        outer.addWidget(self._section_label("TEST:"))
        test_row = QHBoxLayout()
        test_row.addWidget(self._test_btn); test_row.addWidget(self._test_input, 1)
        test_row.addWidget(QLabel("Data :")); test_row.addWidget(self._test_result, 1)
        outer.addLayout(test_row)

        outer.addWidget(self._hline())
        outer.addWidget(self._section_label("SAVE:"))
        save_row = QHBoxLayout(); save_row.addWidget(self._add_btn); save_row.addWidget(self._clear_fields_btn); save_row.addStretch()
        outer.addLayout(save_row)
        return box

    # ------------------------------------------------------------------
    # Rules table
    # ------------------------------------------------------------------
    TABLE_HEADERS = ["Address", "Direction", "Register", "Data(Bytes)",
                     "Type", "Name", "Function / Fields", "Unit", "Group"]
    (C_ADDR, C_DIR, C_REG, C_DBYTES, C_TYPE, C_NAME, C_FUNC, C_UNIT,
     C_GROUP) = range(9)

    def _build_table_box(self) -> QGroupBox:
        box = QGroupBox("Schema Rules")
        lay = QVBoxLayout(box)
        self._table = QTableWidget(0, len(self.TABLE_HEADERS))
        self._table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.cellClicked.connect(self._on_row_clicked)
        lay.addWidget(self._table)
        # Always create the row buttons so they exist; in the tiled sections
        # layout they are placed in the bottom bar instead of inside this box.
        self._remove_btn = QPushButton("Remove Selected"); self._remove_btn.setObjectName("btnDisconnect")
        self._remove_btn.clicked.connect(self._on_remove)
        self._clear_btn = QPushButton("Clear All"); self._clear_btn.clicked.connect(self._on_clear)
        if self._layout_mode != "sections":
            row_btns = QHBoxLayout()
            row_btns.addWidget(self._remove_btn)
            row_btns.addWidget(self._clear_btn); row_btns.addStretch()
            lay.addLayout(row_btns)
        return box

    def _build_file_box(self) -> QGroupBox:
        box = QGroupBox("Schema File (JSON)")
        lay = QVBoxLayout(box)
        self._path_lbl = QLabel("No file loaded — schema is in memory only.")
        self._path_lbl.setObjectName("mutedLabel"); self._path_lbl.setWordWrap(True)
        lay.addWidget(self._path_lbl)
        btns = QHBoxLayout()
        self._new_btn = QPushButton("New"); self._new_btn.clicked.connect(self.new_schema); btns.addWidget(self._new_btn)
        self._load_btn = QPushButton("Load…"); self._load_btn.clicked.connect(self.load_dialog); btns.addWidget(self._load_btn)
        self._save_btn = QPushButton("Save"); self._save_btn.clicked.connect(self.save); btns.addWidget(self._save_btn)
        self._save_as_btn = QPushButton("Save As…"); self._save_as_btn.clicked.connect(self.save_as); btns.addWidget(self._save_as_btn)
        lay.addLayout(btns)
        cap_row = QHBoxLayout()
        self._capture_btn = QPushButton("Test Against Capture (CSV)…")
        self._capture_btn.clicked.connect(self.test_against_capture)
        cap_row.addWidget(self._capture_btn); cap_row.addStretch()
        lay.addLayout(cap_row)
        return box

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fmt_label(self, fmt):
        for label, v in FMT_LABELS:
            if v == fmt:
                return label
        return fmt

    def _refresh_table(self):
        self._table.setRowCount(0)
        for rule in self._schema.rules():
            r = self._table.rowCount(); self._table.insertRow(r)
            reg_txt = "" if rule.register is None else f"0x{rule.register:02X}"
            db_txt = "" if rule.data_bytes is None else str(rule.data_bytes)
            if rule.fmt == "bits":
                func_txt = "; ".join(f"[{bf.high}:{bf.low}]" for bf in (rule.bit_fields or []))
            else:
                func_txt = rule.function
            self._table.setItem(r, self.C_ADDR, QTableWidgetItem(f"0x{rule.address:02X}"))
            self._table.setItem(r, self.C_DIR, QTableWidgetItem(rule.direction))
            self._table.setItem(r, self.C_REG, QTableWidgetItem(reg_txt))
            self._table.setItem(r, self.C_DBYTES, QTableWidgetItem(db_txt))
            self._table.setItem(r, self.C_TYPE, QTableWidgetItem(self._fmt_label(rule.fmt)))
            self._table.setItem(r, self.C_NAME, QTableWidgetItem(rule.name))
            self._table.setItem(r, self.C_FUNC, QTableWidgetItem(func_txt))
            self._table.setItem(r, self.C_UNIT, QTableWidgetItem(rule.unit))
            grp = rule.group + (f" ({rule.group_order})" if rule.group else "")
            self._table.setItem(r, self.C_GROUP, QTableWidgetItem(grp))

    def _emit_changed(self):
        self.schema_changed.emit(self._schema)

    def _set_path(self, path, label_text):
        self._current_path = path
        if self._show_file_ops:
            self._path_lbl.setText(label_text)
        self.path_changed.emit(path or "")

    def _clear_fields(self):
        self._addr_edit.setText("0x08"); self._reg_edit.setText(""); self._dir_combo.setCurrentIndex(0)
        self._set_byte_order("be"); self._signed_check.setChecked(False); self._set_data_bytes(None)
        self._name_edit.clear(); self._unit_edit.clear(); self._func_edit.clear()
        self._bf_table.setRowCount(0); self._set_fmt("dec")
        self._group_combo.setCurrentText(""); self._group_order_spin.setValue(0)
        self._access_combo.setCurrentText("")
        self._test_input.clear(); self._test_result.setText("")

    def _ttype_from_dir(self, direction, reg):
        if direction == "R":
            return "indexed_read" if reg is not None else "simple_read"
        return "indexed_write" if reg is not None else "simple_write"

    # ------------------------------------------------------------------
    # Rule editing
    # ------------------------------------------------------------------
    def _on_add_rule(self):
        try:
            addr = self._addr_edit.addr_value()
        except HexParseError as e:
            dialogs.warn(self, "Invalid", f"Address: {e}"); return
        try:
            reg = self._reg_edit.register_value()
        except HexParseError as e:
            dialogs.warn(self, "Invalid", f"Register: {e}"); return

        fmt = self._fmt_value()
        order = self._byte_order(); signed = self._signed_check.isChecked()
        bit_fields = None
        func = self._func_edit.text().strip()

        if fmt == "bits":
            bit_fields = self._collect_bit_fields()
            if not bit_fields:
                dialogs.warn(self, "Bit Field", "Add at least one bit field, or choose Decimal/Hex.")
                return
            func = ""  # value defaults to raw X
        else:
            if not func:
                dialogs.warn(self, "Invalid", "Function expression is required for Decimal/Hex.")
                return
            try:
                evaluate_function(func, bytes([0x01]), byte_order=order, signed=signed)
            except DecodeError as e:
                dialogs.warn(self, "Invalid Function", f"Function error:\n{e}"); return

        self._schema.add_rule(DecodeRule(
            address=addr,
            transaction_type=self._ttype_from_dir(self._dir_combo.currentText(), reg),
            unit=("" if fmt == "bits" else self._unit_edit.text().strip()),
            function=func,
            register=reg,
            byte_order=order,
            signed=signed,
            data_bytes=self._data_bytes(),
            fmt=fmt,
            bit_fields=bit_fields,
            name=self._name_edit.text().strip(),
            group=self._group_combo.currentText().strip(),
            group_order=self._group_order_spin.value(),
            access=self._access_combo.currentText().strip(),
        ))
        self._refresh_table(); self._emit_changed()

    def _on_test(self):
        try:
            data = self._test_input.bytes_value()
        except HexParseError as e:
            self._test_result.setText(f"Test data: {e}"); return
        order = self._byte_order(); signed = self._signed_check.isChecked()
        try:
            reg = self._reg_edit.register_value()
        except HexParseError:
            reg = None
        # Build a transient rule mirroring the current form and render it.
        fmt = self._fmt_value()
        func = self._func_edit.text().strip()
        bit_fields = self._collect_bit_fields() if fmt == "bits" else None
        if fmt != "bits" and not func:
            self._test_result.setText("Enter a function first."); return
        rule = DecodeRule(
            address=reg or 0,
            transaction_type="indexed_read",
            unit=("" if fmt == "bits" else self._unit_edit.text().strip()),
            function=func, register=reg, byte_order=order, signed=signed,
            data_bytes=self._data_bytes(), fmt=fmt, bit_fields=bit_fields,
            name=self._name_edit.text().strip(),
        )
        # Test data is the VALUE bytes directly (the register is implied by the
        # rule), matching how an indexed read's data phase is decoded.
        self._test_result.setText(self._schema._render(rule, data) or "(no result)")

    def _on_row_clicked(self, row, _col):
        addr_item = self._table.item(row, self.C_ADDR)
        reg_item = self._table.item(row, self.C_REG)
        dir_item = self._table.item(row, self.C_DIR)
        if not addr_item or not dir_item:
            return
        addr = int(addr_item.text(), 16)
        reg_txt = reg_item.text() if reg_item else ""
        reg = int(reg_txt, 16) if reg_txt else None
        ttype = self._ttype_from_dir(dir_item.text(), reg)
        rule = self._schema.find(addr, ttype, register=reg)
        if not rule:
            return
        self._addr_edit.setText(f"0x{rule.address:02X}")
        self._reg_edit.setText("" if rule.register is None else f"0x{rule.register:02X}")
        self._dir_combo.setCurrentText(rule.direction)
        self._set_byte_order(rule.byte_order)
        self._signed_check.setChecked(rule.signed)
        self._set_data_bytes(rule.data_bytes)
        self._name_edit.setText(rule.name)
        self._unit_edit.setText(rule.unit)
        self._group_combo.setCurrentText(rule.group or "")
        self._group_order_spin.setValue(rule.group_order or 0)
        self._access_combo.setCurrentText(rule.access or "")
        self._set_fmt(rule.fmt)
        if rule.fmt == "bits":
            # When loaded from the Schema Rules table, present bit fields sorted
            # low bit -> high bit.
            ordered = sorted(rule.bit_fields or [], key=lambda f: f.low)
            self._load_bit_fields(ordered)
            self._func_edit.clear()
        else:
            self._func_edit.setText(rule.function)
            self._bf_table.setRowCount(0)
        self._on_fmt_changed()

    def _on_remove(self):
        row = self._table.currentRow()
        if row < 0:
            return
        addr = int(self._table.item(row, self.C_ADDR).text(), 16)
        reg_txt = self._table.item(row, self.C_REG).text()
        reg = int(reg_txt, 16) if reg_txt else None
        ttype = self._ttype_from_dir(self._table.item(row, self.C_DIR).text(), reg)
        self._schema.remove_rule(addr, ttype, register=reg)
        self._refresh_table(); self._emit_changed()

    def _on_clear(self):
        if dialogs.confirm(self, "Clear All", "Remove all rules?"):
            self._schema.clear(); self._refresh_table(); self._emit_changed()

    # ------------------------------------------------------------------
    # File ops
    # ------------------------------------------------------------------
    def new_schema(self):
        self._schema = DecodeSchema()
        self._set_path(None, "No file loaded — schema is in memory only.")
        self._refresh_table(); self.refresh_group_choices()
        self._emit_changed()

    def load_dialog(self):
        path = dialogs.open_json(self, "Load Decode Schema")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            self._schema = DecodeSchema.load(path)
            self._set_path(path, f"Loaded: {path}")
            self._refresh_table(); self.refresh_group_choices()
            self._emit_changed()
        except Exception as e:
            dialogs.error(self, "Load Error", str(e))

    def save(self):
        if not self._current_path:
            self.save_as(); return
        try:
            self._schema.save(self._current_path)
            self._set_path(self._current_path, f"Saved: {self._current_path}")
        except Exception as e:
            dialogs.error(self, "Save Error", str(e))

    def save_as(self):
        path = dialogs.save_json(self, "Save Decode Schema", "decode_schema.json")
        if not path:
            return
        try:
            self._schema.save(path)
            self._set_path(path, f"Saved: {path}")
        except Exception as e:
            dialogs.error(self, "Save Error", str(e))

    def test_against_capture(self):
        from ui.common import decode_capture
        import os
        path = dialogs.open_csv(self, "Open Capture CSV")
        if not path:
            return
        try:
            rows = decode_capture(path, self._schema)
        except Exception as e:
            dialogs.error(self, "Capture Error", str(e)); return
        dlg = dialogs.CaptureResultsDialog(rows, os.path.basename(path), parent=self)
        dlg.exec()

    # ------------------------------------------------------------------
    def refresh_group_choices(self):
        """Rebuild the Group dropdown from the schema's display_groups,
        preserving whatever is typed. [XREF: registers-tab]"""
        current = self._group_combo.currentText()
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem("")
        for g in self._schema.display_groups:
            self._group_combo.addItem(g["name"])
        self._group_combo.setCurrentText(current)
        self._group_combo.blockSignals(False)

    @property
    def schema(self) -> DecodeSchema:
        return self._schema

    def set_schema(self, schema: DecodeSchema):
        self._schema = schema; self._refresh_table()
        self.refresh_group_choices(); self._emit_changed()

    @property
    def current_path(self):
        return self._current_path
