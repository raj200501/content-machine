#!/usr/bin/env bash
# Download a free Piper TTS voice (MIT-licensed models from rhasspy/piper-voices)
# into assets/voices so reels get a natural voiceover instead of silence.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE="${1:-${PIPER_VOICE:-en_US-lessac-medium}}"
DEST="$ROOT_DIR/assets/voices"
mkdir -p "$DEST"

if [ -s "$DEST/$VOICE.onnx" ] && [ -s "$DEST/$VOICE.onnx.json" ]; then
  echo "Voice $VOICE already installed."
  exit 0
fi

# en_US-lessac-medium -> en/en_US/lessac/medium/
lang_region="${VOICE%%-*}"
rest="${VOICE#*-}"
speaker="${rest%-*}"
quality="${rest##*-}"
lang="${lang_region%%_*}"
base="https://huggingface.co/rhasspy/piper-voices/resolve/main/${lang}/${lang_region}/${speaker}/${quality}"

for file in "$VOICE.onnx" "$VOICE.onnx.json"; do
  curl -fsSL --retry 3 -o "$DEST/$file.tmp" "$base/$file"
  mv "$DEST/$file.tmp" "$DEST/$file"
done
echo "Installed voice $VOICE into $DEST"
