"""Publish due rendered posts."""

from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.db import Database
from app.publishing.publish_queue import publish_due_jobs


def run_publish_batch(
    db: Database,
    settings: Settings,
    *,
    now: datetime | None = None,
    ignore_schedule: bool = False,
    limit: int = 20,
) -> dict[str, int]:
    stats = publish_due_jobs(db, settings, now=now, ignore_schedule=ignore_schedule, limit=limit)
    metric_date = (now or datetime.now(settings.tzinfo)).date().isoformat()
    db.set_metric(metric_date, "posts_published", stats["published"])
    db.set_metric(metric_date, "duplicate_prevention_blocks", stats["blocked_duplicates"])
    return stats
