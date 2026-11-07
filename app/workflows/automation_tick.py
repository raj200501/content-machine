"""GitHub-friendly periodic automation tick."""

from __future__ import annotations

from datetime import datetime, time

from app.config import Settings
from app.db import Database
from app.workflows.plan_day import run_plan_day
from app.workflows.publish_batch import run_publish_batch
from app.workflows.refresh_sources import run_refresh_sources
from app.workflows.render_batch import run_render_batch


def _metric_map(db: Database, metric_date: str) -> dict[str, float]:
    return {row["metric_name"]: float(row["metric_value"]) for row in db.metrics_for_day(metric_date)}


def _time_reached(now: datetime, target: time) -> bool:
    return now.timetz().replace(tzinfo=None) >= target


def run_automation_tick(db: Database, settings: Settings, *, now: datetime | None = None) -> dict[str, dict]:
    current = now or datetime.now(settings.tzinfo)
    metric_date = current.date().isoformat()
    metrics = _metric_map(db, metric_date)
    results: dict[str, dict] = {}

    if "sources_ingested" not in metrics and _time_reached(current, time(0, 15)):
        results["refresh"] = run_refresh_sources(db, settings)
        metrics = _metric_map(db, metric_date)

    if db.count_scripts_for_day(metric_date) < settings.posts_per_day and _time_reached(current, time(0, 45)):
        results["plan"] = run_plan_day(db, settings, run_date=current.date())
        metrics = _metric_map(db, metric_date)

    render_due_only = settings.publish_ready and not settings.dry_run
    publish_now = settings.publish_now_count if render_due_only else 0
    if publish_now > 0:
        # Manual "post now": render the next reels regardless of slot, then publish
        # them immediately. Later slots keep their schedule.
        results["render_now"] = run_render_batch(db, settings, count=publish_now, run_date=current.date())
        results["publish_now"] = run_publish_batch(
            db,
            settings,
            now=current,
            ignore_schedule=True,
            limit=publish_now,
        )
        if results["publish_now"].get("missing_media", 0) > 0:
            # A reel left "ready" by an earlier runner has no file here; it was
            # re-queued, so render it on this runner and try once more.
            results["render_now_retry"] = run_render_batch(db, settings, count=publish_now, run_date=current.date())
            results["publish_now_retry"] = run_publish_batch(
                db,
                settings,
                now=current,
                ignore_schedule=True,
                limit=publish_now,
            )
        return results

    if render_due_only:
        results["render_due"] = run_render_batch(
            db,
            settings,
            count=settings.batch_render_size,
            run_date=current.date(),
            scheduled_before=current.isoformat(),
        )
    elif metrics.get("renders_succeeded", 0) < settings.posts_per_day and _time_reached(current, time(1, 0)):
        results["render"] = run_render_batch(db, settings, count=settings.batch_render_size, run_date=current.date())

    if settings.dry_run or settings.publish_ready:
        publish = run_publish_batch(
            db,
            settings,
            now=current,
            ignore_schedule=settings.dry_run,
            limit=settings.posts_per_day,
        )
        results["publish"] = publish
        if publish.get("missing_media", 0) > 0:
            results["render_missing"] = run_render_batch(
                db,
                settings,
                count=settings.batch_render_size,
                run_date=current.date(),
                scheduled_before=current.isoformat(),
            )
            results["publish_retry"] = run_publish_batch(
                db,
                settings,
                now=current,
                ignore_schedule=settings.dry_run,
                limit=settings.posts_per_day,
            )
    else:
        results["publish"] = {"published": 0, "blocked_duplicates": 0, "failed": 0, "missing_media": 0, "skipped": 1}

    return results
