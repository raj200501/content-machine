"""Local-first TTS helpers."""

from __future__ import annotations

import logging
import platform
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

from app.config import Settings
from app.utils import command_exists, ensure_directory, ffprobe_duration, run_command

LOG = logging.getLogger(__name__)
LINE_PAUSE_SECONDS = 0.28


def estimate_duration_seconds(text: str, words_per_minute: int = 165) -> float:
    words = max(len(text.split()), 1)
    return max((words / words_per_minute) * 60.0, 6.0)


def resolve_piper_model(settings: Settings) -> Path | None:
    """Explicit PIPER_MODEL_PATH wins; otherwise use any voice in assets/voices."""

    if settings.piper_model_path:
        path = Path(settings.piper_model_path).expanduser()
        return path if path.exists() else None
    voices_dir = settings.assets_dir / "voices"
    preferred = voices_dir / f"{settings.piper_voice}.onnx" if settings.piper_voice else None
    if preferred and preferred.exists():
        return preferred
    matches = sorted(voices_dir.glob("*.onnx"))
    return matches[0] if matches else None


@lru_cache(maxsize=2)
def _load_piper_voice(model_path: str):
    from piper import PiperVoice  # optional dependency

    return PiperVoice.load(model_path)


def _piper(text: str, output_path: Path, settings: Settings) -> bool:
    model_path = resolve_piper_model(settings)
    if model_path is None:
        return False
    try:
        from piper import SynthesisConfig

        voice = _load_piper_voice(str(model_path))
        config = SynthesisConfig(length_scale=settings.piper_length_scale)
        with wave.open(str(output_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=config)
        return output_path.exists() and output_path.stat().st_size > 1000
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - depends on local model files.
        LOG.warning("piper python synthesis failed: %s", exc)
    if not command_exists("piper"):
        return False
    process = subprocess.run(
        ["piper", "--model", str(model_path), "--output_file", str(output_path)],
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


def _silent_fallback(text: str, output_path: Path, settings: Settings, min_seconds: float = 6.0) -> bool:
    words = max(len(text.split()), 1)
    duration = f"{max(words / 165 * 60.0, min_seconds):.2f}"
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


ENGINES = [
    ("piper", _piper),
    ("say", _macos_say),
    ("espeak", _espeak),
    ("gtts", _gtts),
    ("silent", _silent_fallback),
]


def synthesize_audio(text: str, output_dir: Path, stem: str, settings: Settings) -> tuple[Path, float, str]:
    """Create a WAV voiceover with local-first engines."""

    ensure_directory(output_dir)
    output_path = output_dir / f"{stem}.wav"

    for name, engine in ENGINES:
        try:
            if engine(text, output_path, settings):
                return output_path, ffprobe_duration(settings.ffprobe_binary, output_path), name
        except Exception as exc:
            LOG.warning("TTS engine %s failed: %s", name, exc)

    raise RuntimeError("no TTS engine available")


def synthesize_lines(lines: list[str], output_dir: Path, stem: str, settings: Settings) -> tuple[Path, float, str, list[float]]:
    """Voice each line separately so visuals can be cut exactly on line boundaries.

    Returns (voiceover path, total seconds, engine name, seconds per line). Each
    line's slot includes the short pause that follows it.
    """

    ensure_directory(output_dir)
    engine_used = ""
    normalized: list[Path] = []
    durations: list[float] = []
    for index, line in enumerate(lines):
        raw = output_dir / f"{stem}_line{index:02d}_raw.wav"
        engine_name = ""
        for name, engine in ENGINES:
            if engine_used == "silent" and name != "silent":
                continue
            try:
                ok = engine(line, raw, settings, min_seconds=1.6) if name == "silent" else engine(line, raw, settings)
            except Exception as exc:
                LOG.warning("TTS engine %s failed: %s", name, exc)
                ok = False
            if ok:
                engine_name = name
                break
        if not engine_name:
            raise RuntimeError("no TTS engine available")
        engine_used = engine_used or engine_name
        padded = output_dir / f"{stem}_line{index:02d}.wav"
        run_command(
            [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(raw),
                "-af",
                f"apad=pad_dur={LINE_PAUSE_SECONDS}",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(padded),
            ]
        )
        raw.unlink(missing_ok=True)
        normalized.append(padded)
        durations.append(ffprobe_duration(settings.ffprobe_binary, padded))

    output_path = output_dir / f"{stem}.wav"
    list_path = output_dir / f"{stem}_lines.txt"
    list_path.write_text("".join(f"file '{path.resolve()}'\n" for path in normalized), encoding="utf-8")
    run_command(
        [
            settings.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(output_path),
        ]
    )
    return output_path, ffprobe_duration(settings.ffprobe_binary, output_path), engine_used, durations
