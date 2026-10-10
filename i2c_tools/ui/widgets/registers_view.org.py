"""
ui/widgets/registers_view.py
[XREF: registers-tab] Live "Registers" view for one decoded device, built
entirely from its decoder JSON (schema v4): a banner strip of headline
measurements, grouped parameter panes, and a bit-register matrix.

Data source: passive last-seen-from-traffic. RegisterCache attaches to the
merged DecodeSchema's on_rule_decoded observer, so it sees every value the
log's StreamDecoder pairs and decodes — including the replay of existing
rows when a schema is (re)applied. Values are sticky: a row keeps its last
value until the next matching transaction updates it; rows never seen show
"—". (Active polling arrives with the Phase 4 master transport: same tab,
plus send/update controls gated by the rules' access flags.)

Layout comes from the decoder JSON:
  * file-level "display_groups": ordered [{name, kind: banner|pane}]
  * per-rule "group" + "group_order" place scalar rules; rules without a
    group don't appear in the top zone
  * every fmt="bits" rule appears in the Bit Registers matrix automatically;
    2-byte bit rules render as a high/low row pair (inferred, not authored)
  * access containing "W" shows the writable pencil, otherwise a lock
Cell colors: bit=1 red, bit=0 green, reserved gray (RSVD_*-named or
unnamed bits), taken from the active theme palette.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from ui import theme

LOCK, PENCIL = "\U0001F512", "\u270E"          # 🔒 / ✎
NO_VALUE = "\u2014"                             # —


def _is_writable(rule) -> bool:
    return "W" in (rule.access or "").upper()


def _is_reserved(name: str) -> bool:
    return (not name) or name.upper().startswith("RSVD")


# ---------------------------------------------------------------------------
class RegisterCache(QObject):
    """Last-seen raw payload per rule key. Attach to a schema:
        cache.attach(schema)     # sets schema.on_rule_decoded
    Emits value_changed(key) on every observation (sticky last-wins)."""

    value_changed = Signal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values: dict[tuple, bytes] = {}

    def attach(self, schema) -> None:
        schema.on_rule_decoded = self._on_rule_decoded

    def _on_rule_decoded(self, rule, value_bytes: bytes) -> None:
        key = rule.key()
        self._values[key] = value_bytes
        self.value_changed.emit(key)

    def get(self, rule):
        return self._values.get(rule.key())

    def clear(self):
        self._values.clear()


# ---------------------------------------------------------------------------
class RegistersView(QWidget):
    """The Registers tab body for one device (one address in the schema)."""

    def __init__(self, schema, address: int, device_name: str,
                 cache: RegisterCache, parent=None):
        super().__init__(parent)
        self._schema = schema
        self._address = address
        self._device = device_name
        self._cache = cache
        # rule.key() -> (rule, QTableWidgetItem value cell) for scalar rows
        self._scalar_cells: dict[tuple, tuple] = {}
        # rule.key() -> (rule, hex QTableWidgetItem, [(row, col, bit)] cells)
        self._bit_rows: dict[tuple, tuple] = {}
        self._build_ui()
        self._cache.value_changed.connect(self._on_value_changed)
        theme.signals.changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------
    def _device_rules(self):
        return [r for r in self._schema.rules() if r.address == self._address]

    def _grouped(self, kind: str):
        """[(group_name, [rules sorted by group_order])] in display order."""
        groups = [g for g in self._schema.display_groups if g["kind"] == kind]
        out = []
        for g in groups:
            rules = sorted((r for r in self._device_rules()
                            if r.group == g["name"] and r.fmt != "bits"),
                           key=lambda r: (r.group_order, r.name))
            if rules:
                out.append((g["name"], rules))
        return out

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ---- banner strip: headline groups with dividers ----------------
        banner_groups = self._grouped("banner")
        if banner_groups:
            strip = QHBoxLayout()
            strip.setSpacing(10)
            for i, (name, rules) in enumerate(banner_groups):
                if i:
                    div = QFrame()
                    div.setFrameShape(QFrame.VLine)
                    strip.addWidget(div)
                strip.addWidget(self._banner_group(name, rules))
            strip.addStretch(1)
            root.addLayout(strip)

        # ---- parameter panes --------------------------------------------
        pane_groups = self._grouped("pane")
        if pane_groups:
            panes = QHBoxLayout()
            panes.setSpacing(8)
            for name, rules in pane_groups:
                panes.addWidget(self._pane_group(name, rules), 1)
            root.addLayout(panes, 2)

        # ---- bit-register matrix ----------------------------------------
        bit_rules = [r for r in self._device_rules() if r.fmt == "bits"
                     and r.bit_fields]
        if bit_rules:
            head = QHBoxLayout()
            title = QLabel("Bit Registers")
            title.setObjectName("specgenSectionHeading")
            head.addWidget(title)
            head.addStretch(1)
            for text, tok, inv in (("Bit High", "status_error", True),
                                   ("Bit Low", "status_active", True),
                                   ("RSVD", "bg_tertiary", False)):
                lab = QLabel(f" {text} ")
                lab.setAutoFillBackground(True)
                lab.setProperty("legendToken", tok)
                lab.setProperty("legendInverse", inv)
                head.addWidget(lab)
                self._style_legend(lab)
            root.addLayout(head)
            root.addWidget(self._bit_table(bit_rules), 3)

        if not (banner_groups or pane_groups or bit_rules):
            note = QLabel(f"{self._device}: the decoder has no display "
                          f"groups or bit registers (schema v4 'group' / "
                          f"'display_groups' fields).")
            note.setObjectName("mutedLabel")
            note.setWordWrap(True)
            root.addWidget(note)
        root.addStretch(0)

    # ------------------------------------------------------------------
    def _make_param_table(self, rules) -> QTableWidget:
        t = QTableWidget(len(rules), 3)
        t.setHorizontalHeaderLabels(["Name", "Value", "Units"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, rule in enumerate(rules):
            icon = PENCIL if _is_writable(rule) else LOCK
            name = QTableWidgetItem(f"{icon} {rule.name}")
            name.setToolTip(rule.description or rule.name)
            value = QTableWidgetItem(NO_VALUE)
            value.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            unit = QTableWidgetItem(rule.unit or NO_VALUE)
            t.setItem(row, 0, name)
            t.setItem(row, 1, value)
            t.setItem(row, 2, unit)
            self._scalar_cells[rule.key()] = (rule, value)
            self._refresh_scalar(rule, value)
        t.resizeRowsToContents()
        return t

    def _banner_group(self, name: str, rules) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel(name)
        title.setObjectName("specgenSectionHeading")
        lay.addWidget(title)
        table = self._make_param_table(rules)
        table.setMaximumHeight(30 + 26 * len(rules))
        table.horizontalHeader().setVisible(False)
        lay.addWidget(table)
        return box

    def _pane_group(self, name: str, rules) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel(name)
        title.setObjectName("specgenSectionHeading")
        lay.addWidget(title)
        lay.addWidget(self._make_param_table(rules))
        return box

    # ------------------------------------------------------------------
    def _bit_table(self, bit_rules) -> QTableWidget:
        # rows: one per byte (2-byte rules -> high row + low row)
        specs = []          # (rule, byte_index 1=high/0=low or None for 1B)
        for rule in bit_rules:
            nbytes = rule.data_bytes or 1
            if nbytes >= 2:
                specs.append((rule, 1))
                specs.append((rule, 0))
            else:
                specs.append((rule, None))

        t = QTableWidget(len(specs), 10)
        t.setHorizontalHeaderLabels(
            ["Name", "Value"] + [f"Bit{b}" for b in range(7, -1, -1)])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        for row, (rule, byte_ix) in enumerate(specs):
            first_row_of_rule = (byte_ix in (None, 1))
            label = rule.name
            if byte_ix is not None:
                label += " (high)" if byte_ix == 1 else " (low)"
            icon = (PENCIL if _is_writable(rule) else LOCK) + " " \
                if first_row_of_rule else "    "
            name = QTableWidgetItem(icon + label)
            name.setToolTip(rule.description or rule.name)
            t.setItem(row, 0, name)
            hex_item = QTableWidgetItem(NO_VALUE if first_row_of_rule else "")
            hex_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(row, 1, hex_item)

            cells = []
            base = (byte_ix or 0) * 8
            for col, bit in enumerate(range(7, -1, -1)):
                item = QTableWidgetItem(self._bit_name(rule, base + bit))
                item.setTextAlignment(Qt.AlignCenter)
                t.setItem(row, col + 2, item)
                cells.append((item, base + bit))
            entry = self._bit_rows.setdefault(rule.key(), (rule, [], []))
            if first_row_of_rule:
                entry[1].append(hex_item)
            entry[2].extend(cells)
            self._refresh_bits(rule)
        t.resizeRowsToContents()
        return t

    def _bit_name(self, rule, bit: int) -> str:
        for bf in rule.bit_fields or []:
            if bf.low <= bit <= bf.high:
                if bf.mode == "enum" and bf.names:
                    # single-bit flag: strip "=1" style suffix for the label
                    base = bf.names[-1].split("=")[0]
                    return base if bf.high == bf.low else f"{base}[{bit - bf.low}]"
                return (getattr(bf, "description", "") or "").split()[0] \
                    if getattr(bf, "description", "") else f"b{bit}"
        return "RSVD_0"

    # ------------------------------------------------------------------
    # Live refresh
    # ------------------------------------------------------------------
    def _on_value_changed(self, key: tuple):
        if key in self._scalar_cells:
            rule, cell = self._scalar_cells[key]
            self._refresh_scalar(rule, cell)
        if key in self._bit_rows:
            self._refresh_bits(self._bit_rows[key][0])

    def _refresh_scalar(self, rule, cell):
        raw = self._cache.get(rule)
        if raw is None:
            cell.setText(NO_VALUE)
            return
        try:
            value = self._schema.extract_value(rule, raw)
        except Exception:
            cell.setText("<err>")
            return
        if (rule.fmt or "").lower() == "hex":
            cell.setText(f"0x{int(value):0{(rule.data_bytes or 1) * 2}X}")
        elif isinstance(value, float) and not value.is_integer():
            cell.setText(f"{value:.4g}")
        else:
            cell.setText(str(int(value)))

    def _refresh_bits(self, rule):
        entry = self._bit_rows.get(rule.key())
        if entry is None:
            return
        rule, hex_items, cells = entry
        raw = self._cache.get(rule)
        red = theme.get_color("status_error")
        green = theme.get_color("status_active")
        gray = theme.get_color("bg_tertiary")
        fg = theme.get_color("text_inverse")
        muted = theme.get_color("text_muted")

        value = None
        if raw is not None:
            try:
                value = int(self._schema.extract_value(rule, raw))
            except Exception:
                value = None
        nbytes = rule.data_bytes or 1
        for h in hex_items:
            h.setText(NO_VALUE if value is None
                      else f"0x{value:0{nbytes * 2}X}")
        for item, bit in cells:
            reserved = _is_reserved(item.text())
            if reserved:
                item.setBackground(gray)
                item.setForeground(muted)
            elif value is None:
                item.setBackground(green)      # no value yet: default 0 look
                item.setForeground(fg)
            else:
                item.setBackground(red if (value >> bit) & 1 else green)
                item.setForeground(fg)

    # ------------------------------------------------------------------
    def _style_legend(self, lab: QLabel):
        tok = lab.property("legendToken")
        color = theme.get_color(tok)
        fg = theme.get_color("text_inverse") if lab.property("legendInverse") \
            else theme.get_color("text_muted")
        lab.setStyleSheet(
            "QLabel\n{\n"
            f"    background-color: {color.name()};\n"
            f"    color: {fg.name()};\n"
            "    padding: 1px 6px;\n"
            "    border-radius: 3px;\n"
            "}")

    def _on_theme_changed(self, _selection: str):
        for rule, _hex, _cells in list(self._bit_rows.values()):
            self._refresh_bits(rule)
        for lab in self.findChildren(QLabel):
            if lab.property("legendToken"):
                self._style_legend(lab)
