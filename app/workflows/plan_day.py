"""Plan a full day of content and generate scripts."""

from __future__ import annotations

from datetime import date, datetime

from app.config import Settings
from app.db import Database
from app.planning.calendar import day_schedule
from app.planning.topic_mixer import build_daily_topics
from app.utils import json_loads
from app.publishing.insights import category_weights, hook_examples, hook_weights
from app.writing.idea_engine import CATEGORY_BRIEFS, draft_tip_packs
from app.writing.fact_guard import guard_script
from app.writing.script_writer import build_script


def run_plan_day(db: Database, settings: Settings, run_date: date | None = None) -> dict[str, int]:
    target_date = run_date or datetime.now(settings.tzinfo).date()
    if db.count_scripts_for_day(target_date.isoformat()) >= settings.posts_per_day:
        return {"scripts_generated": 0, "already_planned": settings.posts_per_day}

    source_items = db.recent_source_items(days=30, limit=600)
    recent_scripts = db.recent_scripts(days=30)
    slots = day_schedule(target_date, settings)
    multipliers = category_weights(db)
    topics = build_daily_topics(target_date, slots, source_items, recent_scripts, multipliers)

    recent_hooks = {script["hook"] for script in recent_scripts}
    # Research and feedback before drafting: which hook templates have earned
    # reach and shares on this account, and which were used most recently.
    hook_performance = hook_weights(db)
    recent_hook_ids = [
        (json_loads(script.get("metadata_json"), default={}) or {}).get("hook_id", "")
        for script in sorted(recent_scripts, key=lambda row: str(row.get("scheduled_at", "")), reverse=True)
    ]
    # Fresh ideas for today's tip slots, steered by what has worked on this account
    # and by today's hiring headlines. Falls back to the hand-written packs.
    winners, losers = hook_examples(db)
    headlines = [
        str(item.get("title", ""))
        for item in source_items
        if item.get("source_type") != "job_board" and item.get("title")
    ][:8]
    drafts = draft_tip_packs(
        [topic.category for topic in topics if topic.category in CATEGORY_BRIEFS],
        settings,
        winners=winners,
        losers=losers,
        used_hooks=sorted(recent_hooks),
        headlines=headlines,
    )
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
        package = build_script(
            topic, evidence_items, recent_hooks, hook_performance, recent_hook_ids, drafts.pop(topic.category, None)
        )
        recent_hooks.add(package.hook)
        recent_hook_ids.insert(0, package.metadata.get("hook_id", ""))
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
