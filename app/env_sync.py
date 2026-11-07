"""Helpers for keeping local .env files aligned with .env.example."""

from __future__ import annotations

import re
from pathlib import Path


ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _env_entries(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if not path.exists():
        return entries
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE_RE.match(raw_line.strip())
        if match:
            entries.append((match.group(1), match.group(2)))
    return entries


def append_missing_env_values(env_path: Path, example_path: Path) -> tuple[str, ...]:
    """Append keys from example_path that are absent in env_path.

    Existing values are never overwritten and are not returned.
    """

    example_entries = _env_entries(example_path)
    existing_keys = {key for key, _value in _env_entries(env_path)}
    missing = [(key, value) for key, value in example_entries if key not in existing_keys]
    if not missing:
        return ()

    env_path.parent.mkdir(parents=True, exist_ok=True)
    separator = "\n" if env_path.exists() and env_path.stat().st_size else ""
    with env_path.open("a", encoding="utf-8") as env_file:
        env_file.write(separator)
        env_file.write("# Added from .env.example by content-machine sync-env.\n")
        for key, value in missing:
            env_file.write(f"{key}={value}\n")
    return tuple(key for key, _value in missing)


def set_env_values(env_path: Path, values: dict[str, str]) -> None:
    """Set or replace KEY=value lines in env_path, keeping every other line as-is."""

    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        match = ENV_LINE_RE.match(line.strip())
        if match and match.group(1) in remaining:
            key = match.group(1)
            updated.append(f"{key}={remaining.pop(key)}")
        else:
            updated.append(line)
    for key, value in remaining.items():
        updated.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
