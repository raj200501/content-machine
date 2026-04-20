"""All-in-one daily workflow."""

from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.db import Database
from app.workflows.plan_day import run_plan_day
from app.workflows.publish_batch import run_publish_batch
from app.workflows.refresh_sources import run_refresh_sources
from app.workflows.render_batch import run_render_batch


def run_daily(db: Database, settings: Settings) -> dict[str, dict]:
    refresh = run_refresh_sources(db, settings)
    plan = run_plan_day(db, settings)
    render = run_render_batch(db, settings, count=settings.batch_render_size)
    publish = run_publish_batch(
        db,
        settings,
        now=datetime.now(settings.tzinfo),
        ignore_schedule=settings.dry_run,
        limit=settings.posts_per_day if settings.dry_run else 5,
    )
    return {"refresh": refresh, "plan": plan, "render": render, "publish": publish}
