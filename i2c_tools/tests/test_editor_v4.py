"""
tests/test_editor_v4.py — Decoder Editor support for schema v4:
rule-level Group / Order / Access fields on the form, the Group column in
the rules table, and the new Display Groups tab (add/remove/reorder/rename/
kind, dirty tracking, rule-dropdown sync, save round-trip).

Run:
    QT_QPA_PLATFORM=offscreen python3 tests/test_editor_v4.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile as _tf
os.environ.setdefault("ION_TOOL_SETTINGS",
                      _tf.NamedTemporaryFile(suffix=".ini", delete=False).name)

import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILURES = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILURES.append(msg)


def test_rule_form_fields(app, tmp):
    print("rule form: Group / Order / Access")
    from ui.widgets.decode_editor import DecodeEditor

    ed = DecodeEditor(show_file_ops=True, layout="sections")
    ed.schema.display_groups.append({"name": "Pack", "kind": "banner"})
    ed.refresh_group_choices()
    check(ed._group_combo.count() == 2 and ed._group_combo.itemText(1) == "Pack",
          "Group dropdown offers schema groups (+ blank)")

    # author a rule with display fields via the form
    ed._addr_edit.setText("0x08")
    ed._reg_edit.setText("0x26")
    ed._name_edit.setText("Stack Voltage")
    ed._unit_edit.setText("mV")
    ed._func_edit.setText("X*10")
    ed._group_combo.setCurrentText("Pack")
    ed._group_order_spin.setValue(2)
    ed._access_combo.setCurrentText("R/W")
    ed._on_add_rule()
    rule = ed.schema.find_read(8, 0x26)
    check(rule is not None and rule.group == "Pack"
          and rule.group_order == 2 and rule.access == "R/W",
          "Add / Update Rule collects group/order/access")

    # rules table shows the group
    grp_col = ed._table.item(0, ed.C_GROUP)
    check(grp_col is not None and grp_col.text() == "Pack (2)",
          "rules table Group column populated")

    # row click populates the three fields back
    ed._clear_fields()
    check(ed._group_combo.currentText() == "" and
          ed._group_order_spin.value() == 0 and
          ed._access_combo.currentText() == "", "Clear resets display fields")
    ed._on_row_clicked(0, 0)
    check(ed._group_combo.currentText() == "Pack" and
          ed._group_order_spin.value() == 2 and
          ed._access_combo.currentText() == "R/W",
          "row click restores group/order/access")

    # save -> reload keeps everything (v4 round-trip through the editor)
    path = str(Path(tmp) / "ed.json")
    ed._current_path = path
    ed.save()
    data = json.loads(Path(path).read_text())
    check(data["version"] == 4 and data["rules"][0]["group"] == "Pack"
          and data["rules"][0]["access"] == "R/W"
          and data["display_groups"] == [{"name": "Pack", "kind": "banner"}],
          "editor save writes v4 layout fields")
    ed2 = DecodeEditor(show_file_ops=True, layout="sections")
    ed2.load_path(path)
    check(ed2._group_combo.count() == 2,
          "load refreshes the Group dropdown from the file")
    ed.deleteLater(); ed2.deleteLater()


def test_groups_tab(app, tmp):
    print("Display Groups tab")
    from ui.decoder_editor_window import DecoderEditorWindow

    win = DecoderEditorWindow()
    win.show(); app.processEvents()
    labels = [win.centralWidget().findChild(type(win._groups_tab).__mro__[0])]
    tabs = win.centralWidget().layout().itemAt(0).widget()
    names = [tabs.tabText(i) for i in range(tabs.count())]
    check(names == ["Decoder", "Display Groups", "Preferences", "Help", "Exit"],
          f"tab order {names}")

    gt = win._groups_tab
    # add two groups
    gt._name_edit.setText("Pack")
    gt._kind_combo.setCurrentText("banner")
    gt._on_add()
    gt._name_edit.setText("Cells")
    gt._kind_combo.setCurrentText("pane")
    gt._on_add()
    schema = win._editor.schema
    check([g["name"] for g in schema.display_groups] == ["Pack", "Cells"],
          "Add Group appends to the live schema")
    check(win._dirty, "group edit marks the document dirty")
    check(win._editor._group_combo.count() == 3,
          "rule form dropdown synced with new groups")

    # duplicate rejected
    gt._name_edit.setText("Pack")
    gt._on_add()
    check(len(schema.display_groups) == 2, "duplicate name rejected")

    # reorder
    gt._table.selectRow(1)
    gt._on_move(-1)
    check([g["name"] for g in schema.display_groups] == ["Cells", "Pack"],
          "reorder mutates schema order")

    # rename follows through to rules that use the group
    win._editor._addr_edit.setText("0x08")
    win._editor._reg_edit.setText("0x14")
    win._editor._name_edit.setText("Cell 1")
    win._editor._func_edit.setText("X")
    win._editor._group_combo.setCurrentText("Cells")
    win._editor._on_add_rule()
    app.processEvents()
    gt._table.item(0, 0).setText("Cell Measurements")
    app.processEvents()
    rule = schema.find_read(8, 0x14)
    check(schema.display_groups[0]["name"] == "Cell Measurements"
          and rule.group == "Cell Measurements",
          "rename cascades into rules using the group")
    check(gt._table.item(0, 2).text() == "1", "Rules usage count shown")

    # kind change + remove
    gt._table.cellWidget(0, 1).setCurrentText("banner")
    check(schema.display_groups[0]["kind"] == "banner", "kind edit applied")
    gt._table.selectRow(1)
    gt._on_remove()
    check(len(schema.display_groups) == 1, "Remove deletes the group")

    # New schema resets the tab
    win._editor.new_schema()
    app.processEvents()
    check(gt._table.rowCount() == 0, "New schema clears the groups table")
    win._dirty = False
    win.close(); app.processEvents()


def main():
    from ui.common import build_application
    app = build_application(app_name="editor-v4-tests", initial_theme="default")
    with _tf.TemporaryDirectory() as tmp:
        test_rule_form_fields(app, tmp)
        test_groups_tab(app, tmp)
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
