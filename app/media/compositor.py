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


def create_scene_clip(ffmpeg_binary: str, image_path: Path, duration: float, output_path: Path) -> Path:
    ensure_directory(output_path.parent)
    fade_out = max(duration - 0.20, 0.01)
    frames = max(int(duration * 30), 1)
    vf = (
        "scale=1200:-2,"
        f"zoompan=z='min(zoom+0.0008,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30,"
        "format=yuv420p,"
        "fade=t=in:st=0:d=0.20,"
        f"fade=t=out:st={fade_out:.2f}:d=0.20"
    )
    run_command(
        [
            ffmpeg_binary,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            f"{duration:.2f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
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
    ensure_directory(output_path.parent)
    if music_path and music_path.exists():
        run_command(
            [
                ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(voice_path),
                "-i",
                str(music_path),
                "-filter_complex",
                "[2:a]volume=0.08[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
        )
    else:
        run_command(
            [
                ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(voice_path),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
        )
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
            str(video_path),
            "-vf",
            subtitle_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-c:a",
            "copy",
            str(output_path),
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
