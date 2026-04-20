"""Scheduling helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.config import Settings


def build_publication_slots(run_date: date, settings: Settings) -> list[datetime]:
    """Return evenly spaced publication datetimes for a day."""

    start = datetime.combine(run_date, time(settings.publication_start_hour, 0), tzinfo=settings.tzinfo)
    end = datetime.combine(run_date, time(settings.publication_end_hour, 0), tzinfo=settings.tzinfo)
    if settings.posts_per_day == 1:
        return [start]
    total_seconds = (end - start).total_seconds()
    step = total_seconds / (settings.posts_per_day - 1)
    return [start + timedelta(seconds=round(step * index)) for index in range(settings.posts_per_day)]
