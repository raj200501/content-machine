"""Publish queue worker."""

from __future__ import annotations

import logging

from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.publishing.instagram_meta import InstagramMetaPublisher
from app.utils import json_loads
from app.publishing.post_history import script_hash, too_similar


def publish_due_jobs(
    db: Database,
    settings: Settings,
    *,
    now: datetime | None = None,
    ignore_schedule: bool = False,
    limit: int = 20,
) -> dict[str, int]:
    publisher = InstagramMetaPublisher(settings)
    run_now = now or datetime.now(settings.tzinfo)
    due_jobs = db.due_publish_jobs(run_now.isoformat(), limit=limit, ignore_schedule=ignore_schedule)
    recent_posts = db.recent_published_posts(30)
    stats = {"published": 0, "blocked_duplicates": 0, "failed": 0, "missing_media": 0}

    for job in due_jobs:
        current_attempts = int(job.get("attempts", 0)) + 1
        if too_similar(job["full_script"], recent_posts):
            db.update_publish_job(
                job["id"],
                status="blocked_duplicate",
                attempts=current_attempts,
                last_error="duplicate-prevention block",
            )
            stats["blocked_duplicates"] += 1
            continue

        db.update_publish_job(job["id"], status="publishing", attempts=current_attempts)
        try:
            render_path = Path(job["output_path"])
            if not render_path.exists():
                db.fail_render_job(
                    job["render_job_id"],
                    "Rendered media is not present on this runner.",
                    {"reason": "ephemeral_runner"},
                )
                db.update_publish_job(
                    job["id"],
                    status="planned",
                    render_job_id=None,
                    attempts=current_attempts,
                    last_error="Rendered media is not present on this runner; queued for rerender.",
                )
                db.update_script_status(job["script_id"], "planned")
                stats["failed"] += 1
                stats["missing_media"] += 1
                continue
            render_meta = json_loads(job.get("render_metadata_json"), default={}) or {}
            nested = render_meta.get("metadata") if isinstance(render_meta.get("metadata"), dict) else {}
            render_meta = {**render_meta, **nested}
            thumb_offset = render_meta.get("thumb_offset_ms") or nested.get("thumb_offset_ms")
            if render_meta.get("format") == "carousel":
                result = publisher.publish_carousel(
                    [Path(path) for path in render_meta.get("slides", [])],
                    job["caption"],
                    f"{job['script_id']}-{job['hook']}",
                )
            else:
                result = publisher.publish_reel(
                    render_path,
                    job["caption"],
                    f"{job['script_id']}-{job['hook']}",
                    thumb_offset_ms=int(thumb_offset) if thumb_offset else None,
                    category=job.get("category"),
                )
            db.update_publish_job(
                job["id"],
                status="published",
                media_url=result.get("media_url"),
                instagram_creation_id=result.get("creation_id"),
                instagram_media_id=result.get("instagram_media_id"),
                last_error="",
            )
            digest = script_hash(job["full_script"])
            db.insert_published_post(
                publish_job_id=job["id"],
                script_id=job["script_id"],
                instagram_media_id=result["instagram_media_id"],
                caption=job["caption"],
                hook=job["hook"],
                script_hash=digest,
                metadata=result,
            )
            recent_posts.insert(0, {"caption": job["caption"], "hook": job["hook"]})
            stats["published"] += 1
        except Exception as exc:
            # Meta error messages never include the access token (see MetaAPIError).
            logging.getLogger(__name__).warning(
                "Publish failed for job %s (attempt %s): %s", job["id"], current_attempts, exc
            )
            status = "failed" if current_attempts >= 5 else "ready"
            db.update_publish_job(job["id"], status=status, last_error=str(exc), attempts=current_attempts)
            stats["failed"] += 1

    return stats
