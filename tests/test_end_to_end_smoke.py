from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.models import RenderArtifact
from app.workflows.automation_tick import run_automation_tick
from app.workflows.plan_day import run_plan_day
from app.workflows.publish_batch import run_publish_batch
from app.workflows.render_batch import run_render_batch


def _seed_source_items(db: Database, settings: Settings) -> None:
    source_id = db.upsert_source("seed", "job_board", {"name": "seed", "source_type": "job_board"})
    now = datetime.now(settings.tzinfo).isoformat()
    for index, company in enumerate(["Datadog", "Cloudflare", "Asana", "Figma", "Vercel", "Notion"], start=1):
        db.insert_source_item(
            source_id,
            {
                "source_type": "job_board",
                "source_url": f"https://example.com/{company.lower()}-{index}",
                "title": f"{company} Software Engineer Intern",
                "normalized_title": f"{company.lower()} software engineer intern",
                "published_at": now,
                "fetched_at": now,
                "text_content": f"{company} has a public internship posting for software engineering students.",
                "summary": f"{company} has a public internship posting for software engineering students.",
                "extracted_entities": [company],
                "extracted_roles": ["software_engineering", "internship"],
                "freshness_score": 95,
                "relevance_score": 95,
                "duplicate_hash": f"seed-{index}",
                "metadata": {"seed": True},
            },
        )


def test_end_to_end_smoke(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        dry_run=True,
        posts_per_day=3,
        batch_render_size=3,
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="",
        turso_auth_token="",
    )
    settings.ensure_directories()
    db = Database(settings.database_path, settings=settings)
    db.init_db()
    _seed_source_items(db, settings)

    def fake_render_with_fallback(local_settings, script_row, output_root):
        output_root.mkdir(parents=True, exist_ok=True)
        video = output_root / f"{script_row['id']}.mp4"
        audio = output_root / f"{script_row['id']}.wav"
        srt = output_root / f"{script_row['id']}.srt"
        video.write_bytes(b"video")
        audio.write_bytes(b"audio")
        srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nhello\n", encoding="utf-8")
        return RenderArtifact(
            script_id=script_row["id"],
            provider="local_fallback",
            video_path=video,
            audio_path=audio,
            subtitle_path=srt,
            duration_seconds=18.0,
            metadata={},
            fallback_used=True,
        )

    monkeypatch.setattr("app.workflows.render_batch.render_with_fallback", fake_render_with_fallback)

    planned = run_plan_day(db, settings)
    rendered = run_render_batch(db, settings, count=2)
    published = run_publish_batch(db, settings, ignore_schedule=True, limit=1)

    assert planned["scripts_generated"] == 3
    assert rendered["renders_succeeded"] == 2
    assert published["published"] == 1
    assert db.recent_published_posts(30)


def test_automation_tick_runs_due_steps(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        dry_run=True,
        posts_per_day=5,
        batch_render_size=5,
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "db.sqlite",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="",
        turso_auth_token="",
    )
    settings.ensure_directories()
    db = Database(settings.database_path, settings=settings)
    db.init_db()

    called = []

    monkeypatch.setattr(
        "app.workflows.automation_tick.run_refresh_sources",
        lambda *args, **kwargs: called.append("refresh") or {"sources_ingested": 1, "relevant_items_found": 1},
    )
    monkeypatch.setattr(
        "app.workflows.automation_tick.run_plan_day",
        lambda *args, **kwargs: called.append("plan") or {"scripts_generated": 5, "fact_guard_softened": 0},
    )
    monkeypatch.setattr(
        "app.workflows.automation_tick.run_render_batch",
        lambda *args, **kwargs: called.append("render") or {"renders_succeeded": 5, "provider_failures": 0, "fallback_renders_used": 5},
    )
    monkeypatch.setattr(
        "app.workflows.automation_tick.run_publish_batch",
        lambda *args, **kwargs: called.append("publish") or {"published": 0, "blocked_duplicates": 0, "failed": 0},
    )

    now = datetime(2026, 4, 19, 9, 0, tzinfo=settings.tzinfo)
    stats = run_automation_tick(db, settings, now=now)

    assert called == ["refresh", "plan", "render", "publish"]
    assert "publish" in stats
