"""
core/decoder_manager.py  [v0.1]
[XREF: decoder-manager] Manages a SET of loaded decoder JSON files and merges
them into one DecodeSchema for the live log.

Why this works without touching the decode engine: DecodeSchema rules are
keyed by (i2c_address, register, transaction_type), and the StreamDecoder
routes every transaction by its address — so a single schema already decodes
traffic from any number of client devices at once. This class only adds the
management layer: load several files (e.g. bq76905_decoder.json @0x08 and
bq25731_decoder.json @0x6B), merge their rules, report per-file metadata for
the UI list, and rebuild the merged schema when files are added/removed.

Merge policy: files are merged in load order; if two files define the same
(address, register, type) key, the later file wins and the collision is
counted (surfaced to the UI so silent shadowing is visible).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from core.decode_schema import DecodeSchema


@dataclass
class DecoderEntry:
    path: str
    device: str                 # from JSON "device", or filename stem
    rule_count: int
    addresses: set = field(default_factory=set)   # 7-bit addresses covered
    # optional per-address display names from the file-level "address_names"
    # map, e.g. {"0x6B": "R1"} (keys may be "0x6B" or "107") - used to title
    # one Registers tab per address (B33)
    address_names: dict = field(default_factory=dict)

    @property
    def addresses_str(self) -> str:
        return ", ".join(f"0x{a:02X}" for a in sorted(self.addresses))

    def label(self) -> str:
        """One-line UI label: 'BQ76905 @0x08 — 42 rules (file.json)'."""
        at = f" @{self.addresses_str}" if self.addresses else ""
        return f"{self.device}{at} — {self.rule_count} rules ({Path(self.path).name})"


class DecoderSetManager:
    """Ordered set of decoder files; merged_schema() rebuilds on demand."""

    def __init__(self):
        self._entries: list[DecoderEntry] = []
        self._schemas: dict[str, DecodeSchema] = {}   # path -> parsed schema
        self.last_conflicts = 0     # colliding rule keys in the last merge

    # ------------------------------------------------------------------
    def add(self, path: str) -> tuple[bool, str]:
        """Load (or reload) a decoder file. Returns (ok, message)."""
        p = str(Path(path))
        try:
            schema = DecodeSchema.load(p)
        except Exception as e:
            return False, str(e)

        device = Path(p).stem
        names: dict = {}
        try:
            meta = json.loads(Path(p).read_text(encoding="utf-8"))
            device = str(meta.get("device") or device)
            for k, v in (meta.get("address_names") or {}).items():
                try:
                    names[int(str(k), 0)] = str(v)
                except ValueError:
                    pass                     # ignore a malformed key
        except Exception:
            pass

        entry = DecoderEntry(
            path=p, device=device, rule_count=len(schema),
            addresses={r.address for r in schema.rules()},
            address_names=names)

        existing = self._index_of(p)
        if existing >= 0:
            self._entries[existing] = entry         # reload in place
        else:
            self._entries.append(entry)
        self._schemas[p] = schema
        return True, f"{entry.device}: {entry.rule_count} rules"

    def remove(self, path: str) -> bool:
        i = self._index_of(str(Path(path)))
        if i < 0:
            return False
        self._schemas.pop(self._entries[i].path, None)
        del self._entries[i]
        return True

    def move(self, path: str, delta: int) -> bool:
        """Move a decoder up (-1) or down (+1) in load order. Order matters:
        on key collisions the LATER file wins. Returns True if moved."""
        i = self._index_of(str(Path(path)))
        j = i + delta
        if i < 0 or j < 0 or j >= len(self._entries):
            return False
        self._entries[i], self._entries[j] = self._entries[j], self._entries[i]
        return True

    def clear(self):
        self._entries.clear()
        self._schemas.clear()

    # ------------------------------------------------------------------
    def entries(self) -> list[DecoderEntry]:
        return list(self._entries)

    def schema_for(self, path: str):
        """The parsed schema of ONE loaded file (not the merged set), so a
        per-device view shows only that file's rules and display groups."""
        return self._schemas.get(str(Path(path)))

    def paths(self) -> list[str]:
        return [e.path for e in self._entries]

    def __len__(self):
        return len(self._entries)

    def _index_of(self, path: str) -> int:
        for i, e in enumerate(self._entries):
            if e.path == path:
                return i
        return -1

    # ------------------------------------------------------------------
    def merged_schema(self, multiline_bits: bool = True) -> DecodeSchema:
        """One DecodeSchema containing every loaded file's rules (load order;
        later files win key collisions — count in self.last_conflicts)."""
        merged = DecodeSchema()
        merged.multiline_bits = multiline_bits
        seen = set()
        conflicts = 0
        group_names = set()
        for entry in self._entries:
            schema = self._schemas.get(entry.path)
            if schema is None:
                continue
            # v4 layout survives the merge: union of display_groups in load
            # order (first occurrence of a name wins). [XREF: registers-tab]
            for g in getattr(schema, "display_groups", []):
                if g["name"] not in group_names:
                    group_names.add(g["name"])
                    merged.display_groups.append(dict(g))
            for rule in schema.rules():
                key = rule.key()
                if key in seen:
                    conflicts += 1
                seen.add(key)
                merged.add_rule(rule)
        self.last_conflicts = conflicts
        return merged

    def summary(self) -> str:
        """Status line for the UI: devices + total rules (+ conflicts)."""
        if not self._entries:
            return "No decoders loaded"
        devices = ", ".join(e.device for e in self._entries)
        total = sum(e.rule_count for e in self._entries)
        text = f"{len(self._entries)} decoder(s): {devices} — {total} rules"
        if self.last_conflicts:
            text += f" ({self.last_conflicts} overridden by load order)"
        return text
