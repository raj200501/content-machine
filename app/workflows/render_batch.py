"""Render planned scripts to MP4 reels."""

from __future__ import annotations

from datetime import date, datetime

from app.config import Settings
from app.db import Database
from app.media.quality_check import validate_render
from app.media.video_provider import render_with_fallback


def run_render_batch(
    db: Database,
    settings: Settings,
    *,
    count: int | None = None,
    run_date: date | None = None,
) -> dict[str, int]:
    target_date = run_date or datetime.now(settings.tzinfo).date()
    scripts = db.list_renderable_scripts(day=target_date.isoformat(), limit=count or settings.batch_render_size)
    stats = {"renders_succeeded": 0, "provider_failures": 0, "fallback_renders_used": 0}
    recent_scripts = db.recent_scripts(30)

    for script_row in scripts:
        render_job_id = db.create_render_job(script_row["id"], "pending")
        try:
            output_root = settings.rendered_dir / target_date.isoformat()
            artifact = render_with_fallback(settings, script_row, output_root)
            report = validate_render(settings, script_row, artifact, recent_scripts)
            if not report.passed:
                raise ValueError("; ".join(report.issues))

            db.insert_media_asset(
                script_row["id"],
                "video",
                str(artifact.video_path),
                artifact.provider,
                artifact.metadata,
            )
            db.complete_render_job(
                render_job_id,
                {
                    "provider": artifact.provider,
                    "output_path": str(artifact.video_path),
                    "audio_path": str(artifact.audio_path),
                    "subtitle_path": str(artifact.subtitle_path),
                    "duration_seconds": artifact.duration_seconds,
                    "fallback_used": artifact.fallback_used,
                    "metadata": artifact.metadata,
                },
            )
            db.mark_publish_job_ready(script_row["id"], render_job_id)
            db.update_script_status(script_row["id"], "rendered")
            if artifact.fallback_used:
                stats["fallback_renders_used"] += 1
            if artifact.metadata.get("provider_error"):
                stats["provider_failures"] += 1
            stats["renders_succeeded"] += 1
        except Exception as exc:
            db.fail_render_job(render_job_id, str(exc))
            db.update_script_status(script_row["id"], "render_failed")

    db.set_metric(target_date.isoformat(), "renders_succeeded", stats["renders_succeeded"])
    db.set_metric(target_date.isoformat(), "provider_failures", stats["provider_failures"])
    db.set_metric(target_date.isoformat(), "fallback_renders_used", stats["fallback_renders_used"])
    return stats
