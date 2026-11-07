"""Plan a full day of content and generate scripts."""

from __future__ import annotations

from datetime import date, datetime

from app.config import Settings
from app.db import Database
from app.planning.calendar import day_schedule
from app.planning.topic_mixer import build_daily_topics
from app.writing.fact_guard import guard_script
from app.writing.script_writer import build_script


def run_plan_day(db: Database, settings: Settings, run_date: date | None = None) -> dict[str, int]:
    target_date = run_date or datetime.now(settings.tzinfo).date()
    if db.count_scripts_for_day(target_date.isoformat()) >= settings.posts_per_day:
        return {"scripts_generated": 0, "already_planned": settings.posts_per_day}

    source_items = db.recent_source_items(days=30, limit=600)
    recent_scripts = db.recent_scripts(days=30)
    slots = day_schedule(target_date, settings)
    topics = build_daily_topics(target_date, slots, source_items, recent_scripts)

    recent_hooks = {script["hook"] for script in recent_scripts}
    created = 0
    unsupported = 0
    for topic in topics:
        evidence_items = db.source_items_by_ids(topic.source_item_ids)
        topic_id = db.insert_content_topic(
            {
                "day": topic.day,
                "slot_index": topic.slot_index,
                "scheduled_at": topic.scheduled_at,
                "category": topic.category,
                "hook_style": topic.hook_style,
                "title": topic.title,
                "angle": topic.angle,
                "company": topic.company,
                "source_item_ids": topic.source_item_ids,
                "freshness_score": topic.freshness_score,
                "metadata": topic.metadata,
            }
        )
        package = build_script(topic, evidence_items, recent_hooks)
        recent_hooks.add(package.hook)
        guarded = guard_script(package.full_script, evidence_items)
        fact_status = "passed" if guarded.passed else "softened"
        if not guarded.passed:
            unsupported += 1

        script_id = db.insert_script(
            {
                "topic_id": topic_id,
                "script_date": topic.day,
                "scheduled_at": topic.scheduled_at,
                "hook": package.hook,
                "beats": package.beats,
                "cta": package.cta,
                "full_script": guarded.script_text,
                "caption": package.caption.caption,
                "hashtags": " ".join(package.caption.hashtags),
                "source_notes": package.caption.source_notes,
                "compliance_notes": package.caption.compliance_notes,
                "fact_status": fact_status,
                "evidence": package.evidence,
                "metadata": package.metadata,
                "status": "planned",
            }
        )
        for claim in guarded.claims:
            db.insert_claim(script_id, claim.claim_text, claim.evidence, claim.supported)
        db.create_publish_job(script_id, topic.scheduled_at, f"{package.caption.caption}\n\n{' '.join(package.caption.hashtags)}")
        created += 1

    db.set_metric(target_date.isoformat(), "scripts_generated", created)
    db.set_metric(target_date.isoformat(), "fact_guard_softened", unsupported)
    return {"scripts_generated": created, "fact_guard_softened": unsupported}
