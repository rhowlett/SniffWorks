"""
ui/widgets/registers_tabs_host.py  [v1.2]
[XREF: registers-tab] Shared host behavior for the per-device Registers
tabs: one tab per (loaded decoder, I2C address) that provides layout info
(schema v4; B33 - was one tab for the decoder's lowest address only),
rebuilt whenever the decoder set changes, float-aware, inserted before the
Preferences tab. Used by both sniffer windows and the replay window so the
three no longer carry duplicated rebuild logic.

Host requirements: self.tabs (QTabWidget), self.popout
(TabPopoutController). The cache attaches to the merged schema BEFORE the
host applies it to its log model, so the model's re-decode of existing rows
replays history into the tabs (which is exactly how a loaded capture file
populates them in the replay window).
"""
from __future__ import annotations


class RegisterTabsHost:
    """Mixin: call _rebuild_register_tabs(schema, manager) from the host's
    decoders-changed handler, before applying the schema to the log."""

    def _replay_registers_to(self, entries, row_index: int) -> None:
        """[XREF: replay-scrub] Rebuild register state from transactions
        [0 .. row_index] inclusive (row_index < 0 = full history), so the
        device tabs show the state AS OF the selected log row — a true
        replay scrub. Cheap: a few thousand feeds run in milliseconds."""
        cache = getattr(self, "_register_cache", None)
        schema = getattr(self, "_register_schema", None)
        if cache is None or schema is None:
            return
        from core.decode_schema import StreamDecoder
        cache.clear()
        stream = StreamDecoder(schema)     # decodes fire schema.on_rule_decoded
        upto = len(entries) if row_index < 0 else min(row_index + 1,
                                                      len(entries))
        for e in entries[:upto]:
            txn = e.txn
            stream.feed(txn.address, txn.dir_str, txn.data,
                        had_stop=bool(txn.stop),
                        repeated_start=(txn.start == 2))

    @staticmethod
    def _register_tab_title(entry, addr: int, n_tabs: int) -> str:
        """The device name alone when the decoder has one laid-out address
        (unchanged titles); otherwise '<device> — <name> 0xNN'."""
        if n_tabs <= 1:
            return entry.device
        name = entry.address_names.get(addr, "")
        return f"{entry.device} — {name + ' ' if name else ''}0x{addr:02X}"

    def _rebuild_register_tabs(self, schema, manager) -> None:
        from ui.widgets.registers_view import RegisterCache, RegistersView
        # [XREF: tab-popout] a floated device tab must survive the rebuild:
        # remember which were floating, dock them so the sweep sees them,
        # rebuild, then re-float the fresh replacements at the end.
        refloat = self.popout.floating_titles(prop="registersTab")
        self.popout.dock_all(prop="registersTab")
        for i in reversed(range(self.tabs.count())):
            if self.tabs.widget(i).property("registersTab"):
                w = self.tabs.widget(i)
                self.tabs.removeTab(i)
                w.deleteLater()

        self._register_cache = RegisterCache(self)
        self._register_cache.attach(schema)   # observes every decode
        self._register_schema = schema        # for replay scrub

        # insert before the trailing Preferences/Help/Exit trio
        insert_at = max(0, self.tabs.count() - 3)
        for entry in manager.entries():
            # each tab shows ITS file's rules and groups, not the merged set
            # (two decoders on one address no longer show each other's
            # rules); values still come from the merged-schema cache, which
            # is keyed by rule key
            own = getattr(manager, "schema_for", lambda _p: None)(entry.path)
            own = own if own is not None else schema
            # [B33] every address of the decoder that has layout info gets
            # its own tab (a multi-address decoder such as the loopback DUT
            # or the Smart Battery set lost all but its lowest address)
            laid_out = sorted(
                a for a in entry.addresses
                if any((r.group or r.fmt == "bits")
                       for r in own.rules() if r.address == a))
            for addr in laid_out:
                view = RegistersView(own, addr, entry.device,
                                     self._register_cache)
                view.setProperty("registersTab", True)
                view.setProperty("poppable", True)
                self.tabs.insertTab(insert_at, view,
                                    self._register_tab_title(entry, addr,
                                                             len(laid_out)))
                insert_at += 1
        for title in refloat:                 # [XREF: tab-popout]
            self.popout.pop_out_by_title(title)
