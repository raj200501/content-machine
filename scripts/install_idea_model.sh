#!/usr/bin/env bash
# Downloads the free idea-engine model and llama.cpp's server into assets/llm
# (cached between runs by the workflow). No account or API key needed.
#   assets/llm/bin/llama-server   prebuilt llama.cpp release for Linux x64
#   assets/llm/model.gguf         Qwen3 4B Instruct (Apache-2.0), 4-bit, ~2.5 GB
set -euo pipefail

DIR="${LLM_DIR:-assets/llm}"
mkdir -p "$DIR"

if [ ! -x "$DIR/bin/llama-server" ]; then
  tmp=$(mktemp -d)
  # Prebuilt CPU build from the official llama.cpp releases.
  gh release download -R ggml-org/llama.cpp --pattern '*bin-ubuntu-x64.zip' -D "$tmp"
  unzip -q "$tmp"/*.zip -d "$tmp/unzipped"
  server=$(find "$tmp/unzipped" -type f -name llama-server | head -1)
  if [ -z "$server" ]; then echo "llama-server not found in the release zip" >&2; exit 1; fi
  rm -rf "$DIR/bin" && mkdir -p "$DIR/bin"
  cp -a "$(dirname "$server")"/. "$DIR/bin/"
  chmod +x "$DIR/bin/llama-server"
  rm -rf "$tmp"
fi

if [ ! -s "$DIR/model.gguf" ]; then
  for url in \
    "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf" \
    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"; do
    if curl -fsSL --retry 3 -o "$DIR/model.gguf.part" "$url"; then
      mv "$DIR/model.gguf.part" "$DIR/model.gguf"
      echo "Downloaded $url"
      break
    fi
  done
fi

ls -la "$DIR" "$DIR/bin" | head -20
LD_LIBRARY_PATH="$DIR/bin" "$DIR/bin/llama-server" --version 2>&1 | head -2 || true
