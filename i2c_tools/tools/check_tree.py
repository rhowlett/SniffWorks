#!/usr/bin/env python3
"""
tools/check_tree.py
Verify this working copy against the MANIFEST.sha256 shipped in the same
delivery zip. Catches the mixed-revision trees that partial unpacks, macOS
Finder folder "merges", or git checkouts can produce (symptom: errors like
`module 'ui.theme' has no attribute 'signals'` because one file is current
and another is stale).

Usage (from the ion_i2c_tool root):
    python3 tools/check_tree.py            # verify
    python3 tools/check_tree.py --regen    # rebuild the manifest (packaging)

Exit code: 0 clean, 1 mismatches/missing, 2 no manifest.
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"

# Everything that ships; excludes caches, builds, and user-local artifacts.
INCLUDE_SUFFIXES = {".py", ".json", ".md", ".c", ".h", ".s", ".ld", ".sh", ".txt"}
INCLUDE_NAMES = {"Makefile"}
EXCLUDE_PARTS = {"__pycache__", "build", "__MACOSX", ".git", ".venv"}


def tracked_files():
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or p == MANIFEST:
            continue
        if any(part in EXCLUDE_PARTS for part in p.parts):
            continue
        if p.name.startswith("._"):
            continue
        if p.suffix in INCLUDE_SUFFIXES or p.name in INCLUDE_NAMES:
            yield p


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def regen() -> int:
    lines = [f"{sha256(p)}  {p.relative_to(ROOT).as_posix()}"
             for p in tracked_files()]
    MANIFEST.write_text("\n".join(lines) + "\n")
    print(f"wrote {MANIFEST.name}: {len(lines)} files")
    return 0


def verify() -> int:
    if not MANIFEST.exists():
        print("MANIFEST.sha256 not found — this copy predates the manifest "
              "or the file was dropped in a partial unpack.", file=sys.stderr)
        return 2
    expected = {}
    for line in MANIFEST.read_text().splitlines():
        digest, _, rel = line.partition("  ")
        if rel:
            expected[rel] = digest

    stale, missing = [], []
    for rel, digest in expected.items():
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
        elif sha256(p) != digest:
            stale.append(rel)
    extra = [p.relative_to(ROOT).as_posix() for p in tracked_files()
             if p.relative_to(ROOT).as_posix() not in expected]

    if not stale and not missing:
        print(f"OK — {len(expected)} files match the delivered manifest"
              + (f" ({len(extra)} local additions, fine)" if extra else ""))
        return 0
    if stale:
        print(f"STALE/MODIFIED ({len(stale)}) — differ from the delivery; "
              f"re-extract these from the zip:")
        for rel in stale:
            print(f"  {rel}")
    if missing:
        print(f"MISSING ({len(missing)}):")
        for rel in missing:
            print(f"  {rel}")
    if extra:
        print(f"(local additions not in the manifest: {len(extra)} — "
              f"expected for your own files)")
    print("\nFix: replace the WHOLE ion_i2c_tool folder from the latest zip "
          "(don't merge), or re-extract just the listed files. Then delete "
          "all __pycache__ directories.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true",
                    help="rebuild the manifest (used at packaging time)")
    args = ap.parse_args()
    return regen() if args.regen else verify()


if __name__ == "__main__":
    sys.exit(main())
