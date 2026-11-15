"""Print today's plan and pipeline state from the saved database (stdlib only)."""

import json
import sqlite3
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

db = sys.argv[1] if len(sys.argv) > 1 else "output/content_machine.db"
day = sys.argv[2] if len(sys.argv) > 2 else datetime.now(ZoneInfo("America/New_York")).date().isoformat()
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
print("now", datetime.now(ZoneInfo("America/New_York")).isoformat())
for row in conn.execute(
    """SELECT s.id, s.status, s.script_date, s.scheduled_at, s.fact_status, t.category,
              substr(s.hook, 1, 70) AS hook, json_extract(s.metadata_json, '$.format') AS format
       FROM scripts s JOIN content_topics t ON t.id = s.topic_id WHERE s.script_date = ? ORDER BY s.scheduled_at""",
    (day,),
):
    print(dict(row))
    for job in conn.execute("SELECT id, status, substr(error, 1, 600) AS error, created_at FROM render_jobs WHERE script_id = ?", (row["id"],)):
        print("   render", dict(job))
    for job in conn.execute("SELECT id, status, scheduled_at, last_error, attempts FROM publish_jobs WHERE script_id = ?", (row["id"],)):
        print("   publish", dict(job))
print("last publishes:")
for row in conn.execute("SELECT * FROM published_posts ORDER BY id DESC LIMIT 6"):
    print("  ", {k: row[k] for k in row.keys() if k in ("id", "script_id", "published_at", "hook")})
