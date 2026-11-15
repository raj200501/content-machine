"""Weekly report committed to the repo as REPORT.md, so progress is visible without logging in anywhere."""

from __future__ import annotations

import json
from datetime import datetime

from app.config import Settings
from app.db import Database
from app.publishing.insights import category_weights, hook_examples


def build_weekly_report(db: Database, settings: Settings, followers: int | None) -> str:
    now = datetime.now(settings.tzinfo)
    posts = db.recent_published_posts(days=7)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.hook, i.category, i.views, i.reach, i.saved, i.shares, i.likes, i.comments, i.skip_rate,
                   json_extract(s.metadata_json, '$.idea_source') AS idea_source
            FROM post_insights i JOIN scripts s ON s.id = i.script_id
            WHERE datetime(s.scheduled_at) >= datetime('now', '-8 day')
            ORDER BY i.views DESC
            """
        ).fetchall()
    lines = [
        f"# @careerstacked weekly report ({now:%b %d, %Y})",
        "",
        "Written automatically by the posting workflow every Monday.",
        "",
        f"- Followers: **{followers if followers is not None else 'unknown'}**",
        f"- Reels and posts published in the last 7 days: **{len(posts)}**",
        f"- Views on last week's posts so far: **{int(sum(r[2] or 0 for r in rows))}**",
        "",
        "## Top posts this week",
        "",
        "| Hook | Type | Views | Saves | Shares | Skip rate |",
        "|---|---|---|---|---|---|",
    ]
    for hook, category, views, _reach, saved, shares, _likes, _comments, skip, source in rows[:8]:
        origin = " (new idea)" if source else ""
        skip_text = f"{skip:.0f}%" if skip is not None else "-"
        lines.append(f"| {hook}{origin} | {category} | {int(views or 0)} | {int(saved or 0)} | {int(shares or 0)} | {skip_text} |")
    winners, losers = hook_examples(db)
    weights = category_weights(db)
    lines += ["", "## What the system is learning", ""]
    if weights:
        ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)
        lines.append("Posting mix for next week (more of what works): " + ", ".join(f"{k} x{v:.2f}" for k, v in ranked))
    else:
        lines.append("Not enough data yet to change the posting mix.")
    if winners:
        lines += ["", "Hooks the idea engine is told to learn from:"] + [f"- {row['hook']}" for row in winners[:5]]
    if losers:
        lines += ["", "Hooks it is told to avoid:"] + [f"- {row['hook']}" for row in losers[:3]]
    try:
        from app.publishing.insights import format_weights
        from app.publishing.trends import top_outperformers, trend_format_weights

        own = format_weights(db)
        if own:
            lines += ["", "Format weights from this account's results: " + ", ".join(f"{k} x{v:.2f}" for k, v in sorted(own.items(), key=lambda kv: -kv[1]))]
        trend = trend_format_weights(db)
        if trend:
            lines += ["", "Format weights from what's working for other accounts: " + ", ".join(f"{k} x{v:.2f}" for k, v in sorted(trend.items(), key=lambda kv: -kv[1]))]
        from app.planning.experiments import summary

        tests = summary(db)
        if tests:
            lines += ["", "## Style A/B tests (higher score wins more often)", ""] + [f"- {line}" for line in tests]
        winners = top_outperformers(db, limit=6)
        if winners:
            lines += ["", "## Working for other accounts in the niche (2x+ their usual engagement)", ""]
            for row in winners:
                first = (row["caption"] or "").split("\n")[0][:90]
                lines.append(f"- @{row['username']}: \"{first}\" ({row['ratio']:.1f}x, topics: {row['topics'] or 'other'})")
    except Exception:
        pass
    lines += ["", "<!-- " + json.dumps({"generated_at": now.isoformat()}) + " -->", ""]
    return "\n".join(lines)
