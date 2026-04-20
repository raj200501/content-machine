"""Publication schedule helpers."""

from __future__ import annotations

from datetime import date

from app.config import Settings
from app.scheduler import build_publication_slots


def day_schedule(run_date: date, settings: Settings) -> list[str]:
    return [slot.isoformat() for slot in build_publication_slots(run_date, settings)]
