"""Duplicate-prevention helpers for publishing."""

from __future__ import annotations

from difflib import SequenceMatcher

from app.utils import hash_text, normalize_whitespace


def script_hash(script_text: str) -> str:
    return hash_text(normalize_whitespace(script_text))


def too_similar(script_text: str, recent_posts: list[dict], threshold: float = 0.87) -> bool:
    normalized = normalize_whitespace(script_text).lower()
    for post in recent_posts:
        other = normalize_whitespace(post.get("caption", "") + " " + post.get("hook", "")).lower()
        if SequenceMatcher(None, normalized, other).ratio() >= threshold:
            return True
    return False
