import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import Database
from app.workflows.automation_tick import _hold_reason

NY = ZoneInfo("America/New_York")


def _db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite")
    db.init_db()
    return db


def test_no_posting_overnight_or_too_soon(tmp_path: Path) -> None:
    db = _db(tmp_path)
    settings = Settings()
    assert "outside posting hours" in _hold_reason(db, settings, datetime(2026, 11, 8, 3, 50, tzinfo=NY))
    assert _hold_reason(db, settings, datetime(2026, 11, 8, 14, 54, tzinfo=NY)) is None
    with db.connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO published_posts(publish_job_id, script_id, instagram_media_id, published_at, caption, hook, script_hash, metadata_json)"
            " VALUES (1, 1, 'ig_1', ?, '', '', 'h', '{}')",
            ((datetime(2026, 11, 8, 14, 0, tzinfo=NY)).astimezone(timezone.utc).isoformat(),),
        )
    assert "minutes ago" in _hold_reason(db, settings, datetime(2026, 11, 8, 15, 0, tzinfo=NY))
    assert _hold_reason(db, settings, datetime(2026, 11, 8, 16, 0, tzinfo=NY)) is None


def test_gate_script_runs_when_state_missing_and_sleeps_at_night(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("needs_work", Path(__file__).parents[1] / "scripts" / "needs_work.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    day = datetime(2026, 11, 8, 15, 13, tzinfo=NY)
    assert module.decide(tmp_path / "missing.db", day)[0] is True
    assert module.decide(tmp_path / "missing.db", datetime(2026, 11, 8, 3, 0, tzinfo=NY))[0] is False
    db = _db(tmp_path)
    run, reason = module.decide(tmp_path / "db.sqlite", day)
    assert run is True and "planning" in reason
