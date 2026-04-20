#!/usr/bin/env bash
set -euo pipefail

if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is already installed: $(command -v ffmpeg)"
  exit 0
fi

OS="$(uname -s)"
case "$OS" in
  Darwin)
    echo "Installing ffmpeg with Homebrew..."
    if ! command -v brew >/dev/null 2>&1; then
      echo "Homebrew is required on macOS. Install it first: https://brew.sh"
      exit 1
    fi
    brew install ffmpeg
    ;;
  Linux)
    if command -v apt-get >/dev/null 2>&1; then
      echo "Installing ffmpeg with apt..."
      sudo apt-get update
      sudo apt-get install -y ffmpeg
    elif command -v dnf >/dev/null 2>&1; then
      echo "Installing ffmpeg with dnf..."
      sudo dnf install -y ffmpeg
    elif command -v pacman >/dev/null 2>&1; then
      echo "Installing ffmpeg with pacman..."
      sudo pacman -Sy --noconfirm ffmpeg
    else
      echo "Unsupported Linux package manager. Install ffmpeg manually."
      exit 1
    fi
    ;;
  *)
    echo "Unsupported OS: $OS"
    exit 1
    ;;
esac

echo "ffmpeg installation finished."
