from datetime import datetime, timezone
from pathlib import Path

from app.db import Database
from app.planning.taxonomy import scaled_daily_buckets
from app.publishing.insights import _values, category_weights


def test_insight_values_parse_both_shapes() -> None:
    payload = {"data": [{"name": "reach", "values": [{"value": 120}]}, {"name": "shares", "total_value": {"value": 7}}]}
    assert _values(payload) == {"reach": 120.0, "shares": 7.0}


def test_weights_reward_sends_and_saves_but_stay_bounded(tmp_path: Path) -> None:
    db = Database(tmp_path / "db.sqlite")
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        db.upsert_post_insights({"instagram_media_id": f"a{i}", "category": "openings_job_alert", "fetched_at": now,
                                 "reach": 1000, "shares": 60, "saved": 40, "likes": 50, "raw_json": "{}"})
        db.upsert_post_insights({"instagram_media_id": f"b{i}", "category": "interview_prep", "fetched_at": now,
                                 "reach": 1000, "shares": 2, "saved": 5, "likes": 20, "raw_json": "{}"})
    weights = category_weights(db)
    assert weights["openings_job_alert"] > 1 > weights["interview_prep"]
    assert 0.6 <= weights["interview_prep"] and weights["openings_job_alert"] <= 1.6
    boosted = scaled_daily_buckets(5, weights)
    assert sum(boosted.values()) == 5
    assert boosted["openings_job_alert"] >= scaled_daily_buckets(5)["openings_job_alert"]


def test_no_weights_without_enough_data(tmp_path: Path) -> None:
    db = Database(tmp_path / "db.sqlite")
    db.init_db()
    assert category_weights(db) == {}


def test_generated_share_starts_even_and_has_bounds(tmp_path: Path) -> None:
    from app.publishing.insights import generated_share, hook_examples

    db = Database(tmp_path / "db.sqlite")
    db.init_db()
    assert generated_share(db) == 0.5
    assert hook_examples(db) == ([], [])
