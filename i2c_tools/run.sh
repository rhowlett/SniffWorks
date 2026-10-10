#!/usr/bin/env bash
# run.sh — launch an ion_i2c_tool app inside the project venv.
# Usage: ./run.sh sniffer_ion.py [args...]      (default: sniffer_ion.py)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    echo "error: .venv not found — run ./install.sh first" >&2
    exit 1
fi
source "$SCRIPT_DIR/.venv/bin/activate"

APP="${1:-sniffer_ion.py}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ ! -f "$SCRIPT_DIR/$APP" ]]; then
    echo "error: $APP not found in $SCRIPT_DIR" >&2
    exit 1
fi
exec python3 "$SCRIPT_DIR/$APP" "$@"
