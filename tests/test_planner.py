from collections import Counter
from datetime import date
from pathlib import Path

from app.config import Settings
from app.planning.calendar import day_schedule
from app.planning.taxonomy import scaled_daily_buckets
from app.planning.topic_mixer import build_daily_topics


def _item(item_id: int, title: str, source_type: str = "job_board", freshness: float = 90.0) -> dict:
    return {
        "id": item_id,
        "source_type": source_type,
        "title": title,
        "summary": f"{title} summary for early-career tech candidates.",
        "freshness_score": freshness,
        "relevance_score": 90.0,
        "metadata_json": "{}",
    }


def test_daily_topic_mix_respects_quota(tmp_path: Path) -> None:
    settings = Settings(
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="",
        turso_auth_token="",
        posts_per_day=20,
    )
    settings.ensure_directories()
    schedule = day_schedule(date(2026, 4, 19), settings)
    source_items = []
    for index in range(1, 19):
        source_items.append(_item(index, f"Company{index} Software Engineer Intern"))
    source_items.extend(
        [
            _item(101, "Internship recruiting timelines are moving earlier", "rss"),
            _item(102, "Resume mistakes students make for internships", "rss"),
            _item(103, "Behavioral interview tips for CS students", "rss"),
            _item(104, "New-grad market context for software engineers", "rss"),
        ]
    )

    topics = build_daily_topics(date(2026, 4, 19), schedule, source_items, recent_scripts=[])
    counts = Counter(topic.category for topic in topics)

    assert len(topics) == 20
    assert counts["openings_job_alert"] == 6
    # 2026-04-19 is a Sunday: the weekly carousel roundup takes one application slot.
    assert counts["jobs_roundup"] == 1
    assert counts["application_strategy"] == 3
    assert counts["interview_prep"] == 4
    assert counts["resume_portfolio"] == 3
    assert counts["market_context"] == 2
    assert counts["motivational_community"] == 1


def test_scaled_daily_buckets_for_five_posts() -> None:
    quotas = scaled_daily_buckets(5)

    assert sum(quotas.values()) == 5
    assert quotas["openings_job_alert"] == 2
    assert quotas["application_strategy"] == 1
    assert quotas["interview_prep"] == 1
    assert quotas["resume_portfolio"] == 1
    assert quotas["market_context"] == 0
    assert quotas["motivational_community"] == 0
