"""Freshness helpers for planning."""

from __future__ import annotations


def freshness_label(score: float) -> str:
    if score >= 85:
        return "breaking"
    if score >= 65:
        return "fresh"
    if score >= 45:
        return "recent"
    return "evergreen"
