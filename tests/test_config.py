from pathlib import Path

from app.config import Settings
from app.db import Database


def test_settings_ensure_directories(tmp_path: Path) -> None:
    settings = Settings(
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "output" / "state.db",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="",
        turso_auth_token="",
    )
    settings.ensure_directories()

    assert settings.output_dir.exists()
    assert settings.assets_dir.exists()
    assert settings.database_path.parent.exists()
    assert settings.database_runtime_path.parent.exists()
    assert settings.media_staging_dir.exists()


def test_database_backend_selection_and_fallback(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "output" / "state.db",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="libsql://content-machine-example.turso.io",
        turso_auth_token="token",
    )

    assert settings.use_turso is True
    assert settings.database_backend == "turso"
    assert settings.database_runtime_path != settings.database_path
    assert settings.database_runtime_path.name == "state_turso_replica.db"

    monkeypatch.setattr("app.db.libsql", None)
    db = Database(settings.database_path, settings=settings)

    try:
        db.init_db()
    except RuntimeError as exc:
        assert "libsql" in str(exc)
    else:
        raise AssertionError("Expected Turso connection to require libsql when backend is enabled")


def test_content_topic_upsert_preserves_referenced_scripts(tmp_path: Path) -> None:
    settings = Settings(
        output_dir=tmp_path / "output",
        assets_dir=tmp_path / "assets",
        database_path=tmp_path / "output" / "state.db",
        media_staging_dir=tmp_path / "output" / "published" / "staged",
        turso_database_url="",
        turso_auth_token="",
    )
    settings.ensure_directories()
    db = Database(settings.database_path, settings=settings)
    db.init_db()

    topic_id = db.insert_content_topic(
        {
            "day": "2026-04-19",
            "slot_index": 0,
            "scheduled_at": "2026-04-19T08:00:00-04:00",
            "category": "openings_job_alert",
            "hook_style": "list",
            "title": "Three internships to check today",
            "angle": "openings",
            "company": "Datadog",
            "source_item_ids": [1, 2],
            "freshness_score": 92.0,
            "metadata": {"seed": True},
        }
    )

    db.insert_script(
        {
            "topic_id": topic_id,
            "script_date": "2026-04-19",
            "scheduled_at": "2026-04-19T08:00:00-04:00",
            "hook": "Three internships worth checking today.",
            "beats": ["Datadog", "Cloudflare", "Apply early"],
            "cta": "Follow for more.",
            "full_script": "Three internships worth checking today. Datadog. Cloudflare. Apply early.",
            "caption": "Caption",
            "hashtags": "#internship",
            "source_notes": "notes",
            "compliance_notes": "notes",
            "fact_status": "passed",
            "evidence": [],
            "metadata": {"seed": True},
            "status": "planned",
        }
    )

    updated_topic_id = db.insert_content_topic(
        {
            "day": "2026-04-19",
            "slot_index": 0,
            "scheduled_at": "2026-04-19T08:05:00-04:00",
            "category": "openings_job_alert",
            "hook_style": "myth_bust",
            "title": "Updated internship alert",
            "angle": "openings",
            "company": "Cloudflare",
            "source_item_ids": [2, 3],
            "freshness_score": 95.0,
            "metadata": {"updated": True},
        }
    )

    assert updated_topic_id == topic_id
    script_rows = db.scripts_for_day("2026-04-19")
    assert len(script_rows) == 1
