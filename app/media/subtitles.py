"""Subtitle generation."""

from __future__ import annotations

from pathlib import Path

from app.utils import ensure_directory


def _timestamp(seconds: float) -> str:
    total_ms = int(max(seconds, 0) * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def _segments(script_text: str) -> list[str]:
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    segments: list[str] = []
    for line in lines:
        words = line.split()
        chunk_size = 4 if len(words) > 8 else len(words)
        for index in range(0, len(words), max(chunk_size, 1)):
            segments.append(" ".join(words[index : index + chunk_size]))
    return [segment for segment in segments if segment]


def write_srt(script_text: str, output_path: Path, duration_seconds: float) -> Path:
    ensure_directory(output_path.parent)
    segments = _segments(script_text)
    if not segments:
        segments = [" "]
    total_words = sum(max(len(segment.split()), 1) for segment in segments)
    cursor = 0.0
    rows = []
    for index, segment in enumerate(segments, start=1):
        allocation = duration_seconds * (max(len(segment.split()), 1) / total_words)
        rows.append(
            "\n".join(
                [
                    str(index),
                    f"{_timestamp(cursor)} --> {_timestamp(cursor + allocation)}",
                    segment,
                    "",
                ]
            )
        )
        cursor += allocation
    output_path.write_text("\n".join(rows).strip() + "\n", encoding="utf-8")
    return output_path
