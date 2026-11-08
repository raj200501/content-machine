from datetime import datetime

from app.config import Settings
from app.workflows import automation_tick


def test_publish_now_renders_and_publishes_immediately(monkeypatch, tmp_path) -> None:
    settings = Settings(
        dry_run=False,
        instagram_access_token="token",
        public_media_base_url="https://media.example.com",
        publish_now_count=1,
        posts_per_day=5,
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        turso_database_url="",
        turso_auth_token="",
    )
    calls = []

    class FakeDB:
        def metrics_for_day(self, _day):
            return [{"metric_name": "sources_ingested", "metric_value": 1}]

        def count_scripts_for_day(self, _day):
            return 5

        def expire_stale(self, _cutoff):
            return {"scripts": 0, "publish_jobs": 0}

    monkeypatch.setattr(
        automation_tick,
        "run_render_batch",
        lambda db, s, **kw: calls.append(("render", kw)) or {"renders_succeeded": 1},
    )
    monkeypatch.setattr(
        automation_tick,
        "run_publish_batch",
        lambda db, s, **kw: calls.append(("publish", kw)) or {"published": 1},
    )
    now = datetime(2026, 11, 7, 4, 0, tzinfo=settings.tzinfo)
    results = automation_tick.run_automation_tick(FakeDB(), settings, now=now)

    assert results["publish_now"] == {"published": 1}
    render_kwargs = calls[0][1]
    assert "scheduled_before" not in render_kwargs  # not limited to due slots
    assert render_kwargs["count"] == 1
    assert calls[1][1]["ignore_schedule"] is True and calls[1][1]["limit"] == 1
