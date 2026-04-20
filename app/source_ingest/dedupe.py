"""Deduplication helpers."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.utils import hash_text, normalize_whitespace


def normalize_title(title: str) -> str:
    value = normalize_whitespace(title).lower()
    value = re.sub(r"[^a-z0-9\s]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def duplicate_hash(title: str, text: str) -> str:
    return hash_text(normalize_title(title), text[:1200])


def highly_similar(left: str, right: str, threshold: float = 0.88) -> bool:
    return SequenceMatcher(None, normalize_title(left), normalize_title(right)).ratio() >= threshold
