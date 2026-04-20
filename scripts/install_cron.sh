#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing virtualenv Python at $PYTHON_BIN. Run scripts/bootstrap.sh first."
  exit 1
fi

CRON_BLOCK=$(cat <<EOF
# content-machine schedule
15 0 * * * cd "$ROOT_DIR" && "$PYTHON_BIN" -m app.cli refresh-sources >> "$ROOT_DIR/output/logs/cron_refresh.log" 2>&1
45 0 * * * cd "$ROOT_DIR" && "$PYTHON_BIN" -m app.cli plan-day >> "$ROOT_DIR/output/logs/cron_plan.log" 2>&1
0 1 * * * cd "$ROOT_DIR" && "$PYTHON_BIN" -m app.cli render-batch --count 20 >> "$ROOT_DIR/output/logs/cron_render.log" 2>&1
*/10 8-22 * * * cd "$ROOT_DIR" && "$PYTHON_BIN" -m app.cli publish-ready >> "$ROOT_DIR/output/logs/cron_publish.log" 2>&1
EOF
)

TMP_FILE="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'content-machine\|cron_refresh.log\|cron_plan.log\|cron_render.log\|cron_publish.log' > "$TMP_FILE" || true
printf "%s\n" "$CRON_BLOCK" >> "$TMP_FILE"
crontab "$TMP_FILE"
rm -f "$TMP_FILE"

echo "Installed content-machine cron entries."
