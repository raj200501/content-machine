#!/usr/bin/env bash
# Download the free Kokoro-82M voice model (Apache-2.0) used for reel voiceovers.
# ~350 MB the first time; GitHub Actions caches it after that.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT_DIR/assets/voices"
BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
mkdir -p "$DEST"

for file in kokoro-v1.0.onnx voices-v1.0.bin; do
  if [ -s "$DEST/$file" ]; then
    echo "$file already installed."
    continue
  fi
  curl -fsSL --retry 3 -o "$DEST/$file.tmp" "$BASE/$file"
  mv "$DEST/$file.tmp" "$DEST/$file"
  echo "Installed $file"
done
