"""Write a markdown report of the scripts, captions and renders in a (dry-run) DB."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "output/content_machine.db")
out_path = Path(sys.argv[2] if len(sys.argv) > 2 else "output/preview.md")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT s.id, s.scheduled_at, s.full_script, s.caption, s.hashtags, s.fact_status, s.metadata_json,
           t.category,
           (SELECT r.output_path FROM render_jobs r WHERE r.script_id = s.id AND r.status = 'completed' ORDER BY r.id DESC LIMIT 1) AS video,
           (SELECT r.error FROM render_jobs r WHERE r.script_id = s.id AND r.status = 'failed' ORDER BY r.id DESC LIMIT 1) AS error
    FROM scripts s JOIN content_topics t ON t.id = s.topic_id ORDER BY s.scheduled_at
    """
).fetchall()
lines = ["# Preview", ""]
for row in rows:
    meta = json.loads(row["metadata_json"] or "{}")
    lines += [
        f"## Script {row['id']} · {row['category']} · {row['scheduled_at']} · fact={row['fact_status']}",
        f"video: {row['video'] or 'NOT RENDERED'}" + (f" · error: {row['error']}" if row["error"] else ""),
        "",
        "```",
        row["full_script"],
        "```",
        "",
        "Scenes: " + json.dumps(meta.get("scenes", []))[:1500],
        "",
        "Caption:",
        "```",
        f"{row['caption']}\n\n{row['hashtags']}",
        "```",
        "",
    ]
items = conn.execute(
    "SELECT title, metadata_json, published_at FROM source_items WHERE source_type = 'job_board' ORDER BY id DESC LIMIT 400"
).fetchall()
paid = [(i["title"], json.loads(i["metadata_json"] or "{}")) for i in items]
with_pay = [(t, m) for t, m in paid if m.get("pay")]
lines += [f"## Job items: {len(paid)} · with pay: {len(with_pay)}", ""]
lines += [f"- {m.get('company')}: {t} · {m.get('location')} · {m.get('pay')}" for t, m in with_pay[:40]]
out_path.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {out_path} ({len(rows)} scripts, {len(with_pay)}/{len(paid)} jobs with pay)")
