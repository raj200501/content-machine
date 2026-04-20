"""Local-first TTS helpers."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from app.config import Settings
from app.utils import command_exists, ensure_directory, ffprobe_duration, run_command


def estimate_duration_seconds(text: str, words_per_minute: int = 165) -> float:
    words = max(len(text.split()), 1)
    return max((words / words_per_minute) * 60.0, 6.0)


def _piper(text: str, output_path: Path, settings: Settings) -> bool:
    if not settings.piper_model_path or not command_exists("piper"):
        return False
    process = subprocess.run(
        ["piper", "--model", settings.piper_model_path, "--output_file", str(output_path)],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    return process.returncode == 0 and output_path.exists()


def _macos_say(text: str, output_path: Path, settings: Settings) -> bool:
    if platform.system() != "Darwin" or not command_exists("say"):
        return False
    interim = output_path.with_suffix(".aiff")
    try:
        run_command(["say", "-v", settings.macos_say_voice, "-r", "185", "-o", str(interim), text])
        run_command(
            [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(interim),
                "-ar",
                "24000",
                "-ac",
                "1",
                str(output_path),
            ]
        )
        return output_path.exists()
    finally:
        if interim.exists():
            interim.unlink()


def _espeak(text: str, output_path: Path, settings: Settings) -> bool:
    binary = "espeak-ng" if command_exists("espeak-ng") else "espeak" if command_exists("espeak") else ""
    if not binary:
        return False
    run_command([binary, "-w", str(output_path), "-s", "172", "-v", settings.linux_tts_voice, text])
    return output_path.exists()


def _gtts(text: str, output_path: Path, settings: Settings) -> bool:
    if not settings.enable_gtts_fallback:
        return False
    try:  # pragma: no cover - optional dependency.
        from gtts import gTTS
    except Exception:
        return False
    interim = output_path.with_suffix(".mp3")
    try:
        gTTS(text=text, lang="en").save(str(interim))
        run_command(
            [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(interim),
                "-ar",
                "24000",
                "-ac",
                "1",
                str(output_path),
            ]
        )
        return output_path.exists()
    finally:
        if interim.exists():
            interim.unlink()


def _silent_fallback(text: str, output_path: Path, settings: Settings) -> bool:
    duration = f"{estimate_duration_seconds(text):.2f}"
    run_command(
        [
            settings.ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            duration,
            str(output_path),
        ]
    )
    return output_path.exists()


def synthesize_audio(text: str, output_dir: Path, stem: str, settings: Settings) -> tuple[Path, float, str]:
    """Create a WAV voiceover with local-first engines."""

    ensure_directory(output_dir)
    output_path = output_dir / f"{stem}.wav"

    engines = [
        ("piper", _piper),
        ("say", _macos_say),
        ("espeak", _espeak),
        ("gtts", _gtts),
        ("silent", _silent_fallback),
    ]

    for name, engine in engines:
        if engine(text, output_path, settings):
            return output_path, ffprobe_duration(settings.ffprobe_binary, output_path), name

    raise RuntimeError("no TTS engine available")
