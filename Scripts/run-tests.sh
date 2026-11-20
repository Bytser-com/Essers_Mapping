#!/usr/bin/env bash
# Linux/macOS launcher for the shared Python test runner.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/run-tests.py" "$@"
