#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${MEDIA_PUBLIC_HOST:-127.0.0.1}"
PORT="${MEDIA_PUBLIC_PORT:-8787}"
ROOT="${MEDIA_STAGING_DIR:-output/published/staged}"

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <command> [args...]" >&2
  exit 2
fi

cd "$ROOT_DIR"

if [ -f .env ]; then
  env_public_url="$(awk -F= '/^PUBLIC_MEDIA_BASE_URL=/{print substr($0, index($0, "=") + 1)}' .env | tail -n 1)"
  env_staging_dir="$(awk -F= '/^MEDIA_STAGING_DIR=/{print substr($0, index($0, "=") + 1)}' .env | tail -n 1)"
  if [ -z "${PUBLIC_MEDIA_BASE_URL:-}" ] && [ -n "$env_public_url" ]; then
    export PUBLIC_MEDIA_BASE_URL="$env_public_url"
  fi
  if [ "${ROOT}" = "output/published/staged" ] && [ -n "$env_staging_dir" ]; then
    ROOT="$env_staging_dir"
  fi
fi

if [ -n "${PUBLIC_MEDIA_BASE_URL:-}" ]; then
  exec "$@"
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  cat >&2 <<EOF
cloudflared is not installed.

Install it for free, then rerun this command:
  brew install cloudflared

No Cloudflare account, R2 subscription, bucket, or API key is required for this local tunnel path.
EOF
  exit 1
fi

mkdir -p "${ROOT}/reels" "$ROOT_DIR/output/logs"

server_log="$(mktemp)"
tunnel_log="$(mktemp)"
server_pid=""
tunnel_pid=""

cleanup() {
  if [ -n "$tunnel_pid" ]; then
    kill "$tunnel_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$server_pid" ]; then
    kill "$server_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$server_log" "$tunnel_log"
}
trap cleanup EXIT INT TERM

python3 -m http.server "$PORT" --bind "$HOST" --directory "$ROOT" >"$server_log" 2>&1 &
server_pid=$!

cloudflared tunnel --url "http://${HOST}:${PORT}" >"$tunnel_log" 2>&1 &
tunnel_pid=$!

public_url=""
for _ in $(seq 1 60); do
  public_url="$(grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$tunnel_log" | grep -v '^https://api\.trycloudflare\.com$' | head -n 1 || true)"
  if [ -n "$public_url" ]; then
    break
  fi
  if ! kill -0 "$tunnel_pid" >/dev/null 2>&1; then
    echo "cloudflared exited before a public URL was ready:" >&2
    cat "$tunnel_log" >&2
    exit 1
  fi
  sleep 1
done

if [ -z "$public_url" ]; then
  echo "Timed out waiting for cloudflared to provide a public media URL." >&2
  cat "$tunnel_log" >&2
  exit 1
fi

export PUBLIC_MEDIA_BASE_URL="$public_url"
echo "Using temporary public media URL: $PUBLIC_MEDIA_BASE_URL"
"$@"
