#!/usr/bin/env bash
set -euo pipefail

ROOT="${MEDIA_STAGING_DIR:-output/published/staged}"
HOST="${MEDIA_PUBLIC_HOST:-127.0.0.1}"
PORT="${MEDIA_PUBLIC_PORT:-8787}"

mkdir -p "${ROOT}/reels"

if ! command -v cloudflared >/dev/null 2>&1; then
  cat >&2 <<EOF
cloudflared is not installed.

Install it for free, then rerun this script:
  brew install cloudflared

This script does not create a Cloudflare account, R2 subscription, bucket, or API key.
EOF
  exit 1
fi

python3 -m http.server "${PORT}" --bind "${HOST}" --directory "${ROOT}" &
server_pid=$!

cleanup() {
  kill "${server_pid}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cat <<EOF
Serving staged media from ${ROOT}

When cloudflared prints an https://*.trycloudflare.com URL, set:
  PUBLIC_MEDIA_BASE_URL=<that URL>

Keep this terminal open while running a live publish.
EOF

cloudflared tunnel --url "http://${HOST}:${PORT}"
