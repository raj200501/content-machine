"""General utility helpers."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from collections.abc import Iterable
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return normalized or "item"


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True)


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def hash_text(*parts: str) -> str:
    joined = "||".join(normalize_whitespace(part) for part in parts if part)
    return md5(joined.encode("utf-8")).hexdigest()


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    LOG.debug("Running command: %s", " ".join(args))
    return subprocess.run(
        args,
        check=check,
        capture_output=capture_output,
        text=text,
        cwd=str(cwd) if cwd else None,
    )


def ffprobe_duration(ffprobe_binary: str, path: Path) -> float:
    result = run_command(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def first_existing_file(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None
