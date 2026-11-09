"""Cheap pre-check for scheduled runs (standard library only).

Reads the restored state DB and decides whether this run has anything to do,
so hourly runs that find nothing due finish in seconds instead of installing
ffmpeg, Python packages and voice models. Mirrors the rules in
app/workflows/automation_tick.py. If anything goes wrong it says "run".

Usage: python scripts/needs_work.py output/content_machine.db
Writes run=true|false to $GITHUB_OUTPUT when set.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

POSTS_PER_DAY = int(os.environ.get("POSTS_PER_DAY", "5"))
TZ = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))
START, END = time(7, 30), time(23, 30)
GAP = timedelta(minutes=int(os.environ.get("MIN_PUBLISH_GAP_MINUTES", "100")))
STALE = timedelta(hours=int(os.environ.get("STALE_AFTER_HOURS", "12")))


def emit(run: bool, reason: str) -> None:
    line = f"run={'true' if run else 'false'}"
    print(f"{line}  ({reason})")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def decide(db_path: Path, now: datetime) -> tuple[bool, str]:
    local = now.astimezone(TZ)
    if not START <= local.time().replace(tzinfo=None) <= END:
        return False, f"night ({local:%H:%M})"
    if not db_path.exists():
        return True, "no saved state yet"
    conn = sqlite3.connect(db_path)
    today = local.date().isoformat()
    planned = conn.execute("SELECT COUNT(*) FROM scripts WHERE script_date = ?", (today,)).fetchone()[0]
    if planned < POSTS_PER_DAY:
        return True, "today needs planning"
    collected = conn.execute(
        "SELECT 1 FROM daily_metrics WHERE metric_date = ? AND metric_name = 'insights_collected'", (today,)
    ).fetchone()
    if not collected:
        return True, "insights not collected today"
    last = conn.execute(
        "SELECT published_at FROM published_posts WHERE instagram_media_id NOT LIKE 'dryrun%' "
        "ORDER BY published_at DESC LIMIT 1"
    ).fetchone()
    if last and (when := parse(last[0])) and now - when < GAP:
        return False, f"last post {int((now - when).total_seconds() // 60)} min ago"
    candidates = conn.execute(
        "SELECT scheduled_at FROM scripts WHERE script_date = ? AND status IN ('planned', 'render_failed') "
        "UNION ALL SELECT scheduled_at FROM publish_jobs WHERE status = 'ready'",
        (today,),
    ).fetchall()
    for (scheduled_at,) in candidates:
        when = parse(scheduled_at)
        if when and now - STALE <= when <= now:
            return True, f"post due (slot {when.astimezone(TZ):%H:%M})"
    return False, "nothing due"


def plan_needed(db_path: Path, now: datetime) -> bool:
    """True when today's reels are not planned yet (the run that plans needs the idea model)."""

    if not db_path.exists():
        return True
    today = now.astimezone(TZ).date().isoformat()
    with sqlite3.connect(db_path) as conn:
        planned = conn.execute("SELECT COUNT(*) FROM scripts WHERE script_date = ?", (today,)).fetchone()[0]
    return planned < POSTS_PER_DAY


def main() -> None:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "output/content_machine.db")
    now = datetime.now(timezone.utc)
    try:
        run, reason = decide(db_path, now)
    except Exception as exc:  # fail open: a full run is always safe
        run, reason = True, f"check failed: {exc}"
    emit(run, reason)
    try:
        plan = plan_needed(db_path, now)
    except Exception:
        plan = True
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"plan={'true' if plan else 'false'}\n")
    print(f"plan={'true' if plan else 'false'}")


if __name__ == "__main__":
    main()
