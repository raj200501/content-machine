"""Turn rendered reels into small review files: a contact sheet per reel and a
540p copy, plus downsized carousel slides. Used by the preview workflow so a
reviewer can look at frames without downloading full-size videos.

Usage: python scripts/preview_sheets.py output/rendered output/previews
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TIMES = [0.03, 0.6, 1.5, 3, 5, 7, 9, 12, 15, 18, 21, 24, 27, 30]


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def sheet(video: Path, out: Path) -> None:
    length = duration(video)
    frames = out / f"{video.stem}_frames"
    frames.mkdir(parents=True, exist_ok=True)
    times = [t for t in TIMES if t < length - 0.1] + [max(length - 0.3, 0)]
    for index, t in enumerate(times):
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t}", "-i", str(video), "-frames:v", "1",
             "-vf", "scale=360:-1", str(frames / f"f_{index:02d}.png")],
            check=False,
        )
    columns = 8 if len(times) > 8 else len(times)
    rows = (len(times) + columns - 1) // columns
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(frames / "f_%02d.png"),
         "-filter_complex", f"tile={columns}x{rows}:color=black", "-frames:v", "1", str(out / f"{video.stem}_sheet.png")],
        check=False,
    )
    for png in frames.glob("*.png"):
        png.unlink()
    frames.rmdir()
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf", "scale=540:-2", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "96k", str(out / f"{video.stem}_540.mp4")],
        check=False,
    )


def slides(folder: Path, out: Path) -> None:
    from PIL import Image

    for image in sorted(folder.glob("*.jpg")):
        with Image.open(image) as img:
            img.thumbnail((540, 675))
            img.save(out / f"{folder.name}_{image.stem}.jpg", quality=80)


def main(rendered: str, target: str) -> None:
    source, out = Path(rendered), Path(target)
    out.mkdir(parents=True, exist_ok=True)
    for video in sorted(source.rglob("*.mp4")):
        sheet(video, out)
    for manifest in sorted(source.rglob("carousel.json")):
        slides(manifest.parent, out)
    print(f"Wrote previews to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
