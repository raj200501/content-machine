"""FFmpeg composition helpers."""

from __future__ import annotations

import logging
import shutil
from functools import lru_cache
from pathlib import Path

from app.utils import ensure_directory, run_command

LOG = logging.getLogger(__name__)


def _escape_filter_value(value: str) -> str:
    escaped = str(value)
    for original, replacement in (
        ("\\", r"\\"),
        (":", r"\:"),
        (",", r"\,"),
        ("'", r"\'"),
        ("[", r"\["),
        ("]", r"\]"),
    ):
        escaped = escaped.replace(original, replacement)
    return escaped


@lru_cache(maxsize=8)
def _ffmpeg_has_filter(ffmpeg_binary: str, filter_name: str) -> bool:
    result = run_command(
        [ffmpeg_binary, "-hide_banner", "-h", f"filter={filter_name}"],
        check=False,
    )
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    return "Unknown filter" not in combined


def create_scene_clip(
    ffmpeg_binary: str,
    image_path: Path,
    duration: float,
    output_path: Path,
    fade_in: bool = True,
) -> Path:
    """Turn a still card into a clip with a slow push-in so the frame never feels static."""

    ensure_directory(output_path.parent)
    fps = 30
    frames = max(int(round(duration * fps)), 1)
    zoom_step = 0.05 / frames  # ~5% push-in over the scene, independent of its length
    filters = [
        "scale=2160:-2",  # upscale first so zoompan stays smooth instead of jittery
        f"zoompan=z='min(1+{zoom_step:.6f}*on,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s=1080x1920:fps={fps}",
        "format=yuv420p",
    ]
    if fade_in:
        filters.append("fade=t=in:st=0:d=0.25")
    run_command(
        [
            ffmpeg_binary,
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-i",
            str(image_path),
            "-frames:v",
            str(frames),
            "-vf",
            ",".join(filters),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    )
    return output_path


def concat_clips(ffmpeg_binary: str, clips: list[Path], output_path: Path) -> Path:
    ensure_directory(output_path.parent)
    list_path = output_path.with_suffix(".txt")
    list_path.write_text("".join(f"file '{clip.resolve()}'\n" for clip in clips), encoding="utf-8")
    run_command(
        [
            ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
    )
    return output_path


def mux_audio(ffmpeg_binary: str, video_path: Path, voice_path: Path, output_path: Path, music_path: Path | None = None) -> Path:
    """Mix voice (and optional looped music bed) under the video. Video length wins."""

    ensure_directory(output_path.parent)
    command = [ffmpeg_binary, "-y", "-i", str(video_path), "-i", str(voice_path)]
    if music_path and music_path.exists():
        command += ["-stream_loop", "-1", "-i", str(music_path)]
        audio_filter = (
            "[2:a]volume=0.07,afade=t=in:d=1[m];"
            "[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,apad[a]"
        )
    else:
        audio_filter = "[1:a]apad[a]"
    command += [
        "-filter_complex",
        audio_filter,
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    run_command(command)
    return output_path


def burn_subtitles(ffmpeg_binary: str, video_path: Path, subtitles_path: Path, output_path: Path) -> Path:
    ensure_directory(output_path.parent)
    if not _ffmpeg_has_filter(ffmpeg_binary, "subtitles"):
        LOG.warning("ffmpeg '%s' does not support the subtitles filter; using unburned video fallback", ffmpeg_binary)
        shutil.copyfile(video_path, output_path)
        return output_path

    style = "Fontsize=22,PrimaryColour=&Hffffff,OutlineColour=&H30000000,BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV=110"
    subtitle_filter = (
        f"subtitles=filename={_escape_filter_value(subtitles_path.name)}:"
        f"force_style={_escape_filter_value(style)}"
    )
    run_command(
        [
            ffmpeg_binary,
            "-y",
            "-i",
            str(video_path.resolve()),
            "-vf",
            subtitle_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-c:a",
            "copy",
            str(output_path.resolve()),
        ],
        cwd=subtitles_path.parent,
    )
    return output_path


def compose_with_background_video(
    ffmpeg_binary: str,
    background_video: Path,
    voice_path: Path,
    subtitles_path: Path,
    output_path: Path,
    duration: float,
    music_path: Path | None = None,
) -> Path:
    ensure_directory(output_path.parent)
    mixed_path = output_path.with_name(output_path.stem + "_mixed.mp4")
    if music_path and music_path.exists():
        run_command(
            [
                ffmpeg_binary,
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(background_video),
                "-i",
                str(voice_path),
                "-i",
                str(music_path),
                "-t",
                f"{duration:.2f}",
                "-filter_complex",
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=saturation=1.05:brightness=-0.03[v];"
                "[2:a]volume=0.08[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(mixed_path),
            ]
        )
    else:
        run_command(
            [
                ffmpeg_binary,
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(background_video),
                "-i",
                str(voice_path),
                "-t",
                f"{duration:.2f}",
                "-vf",
                "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=saturation=1.05:brightness=-0.03",
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(mixed_path),
            ]
        )
    return burn_subtitles(ffmpeg_binary, mixed_path, subtitles_path, output_path)
