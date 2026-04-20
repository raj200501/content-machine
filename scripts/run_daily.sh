#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing virtualenv Python at $PYTHON_BIN. Run scripts/bootstrap.sh first."
  exit 1
fi

cd "$ROOT_DIR"
"$PYTHON_BIN" -m app.cli daily-run
