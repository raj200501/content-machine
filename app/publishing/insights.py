"""Close the loop: read each Reel's performance and steer the daily mix.

Instagram's top ranking signals are watch time, likes per reach and sends per
reach (Mosseri, Jan 2025). This pulls reach, shares, saves, likes and skip rate
for recent posts and turns them into gentle category weights for planning.

Reading insights needs the ``instagram_manage_insights`` permission on the
token. Without it, collection is skipped and the default mix is used.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import Settings
from app.db import Database
from app.publishing.instagram_meta import InstagramMetaPublisher, MetaAPIError
from app.utils import json_dumps

LOG = logging.getLogger(__name__)

FULL_METRICS = "reach,views,saved,shares,likes,comments,ig_reels_avg_watch_time,reels_skip_rate"
CORE_METRICS = "reach,saved,shares,likes,comments"


def _values(payload: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in payload.get("data", []):
        name = item.get("name")
        points = item.get("values") or []
        value = points[0].get("value") if points else item.get("total_value", {}).get("value")
        if isinstance(value, (int, float)):
            values[name] = float(value)
    return values


def collect_insights(db: Database, settings: Settings, days: int = 14) -> dict[str, int]:
    stats = {"posts": 0, "updated": 0, "skipped": 0}
    posts = db.posts_for_insights(days)
    stats["posts"] = len(posts)
    if not posts or settings.dry_run or not settings.instagram_access_token:
        return stats
    publisher = InstagramMetaPublisher(settings)
    try:
        token, _ = publisher.publish_credentials()
    except Exception as exc:
        LOG.warning("Insights skipped: %s", exc)
        return stats
    metrics = FULL_METRICS
    for post in posts:
        media_id = post["instagram_media_id"]
        try:
            payload = publisher._request("GET", f"{media_id}/insights", params={"metric": metrics, "access_token": token})
        except MetaAPIError as exc:
            message = str(exc)
            if "permission" in message.lower() or " 10:" in message or " 200:" in message:
                LOG.warning("Insights need the instagram_manage_insights permission; skipping (%s)", message)
                stats["skipped"] = len(posts)
                return stats
            if metrics == FULL_METRICS:
                metrics = CORE_METRICS  # a newer metric is not available on this API version
                try:
                    payload = publisher._request("GET", f"{media_id}/insights", params={"metric": metrics, "access_token": token})
                except Exception as retry_exc:
                    LOG.warning("Insights failed for %s: %s", media_id, retry_exc)
                    stats["skipped"] += 1
                    continue
            else:
                LOG.warning("Insights failed for %s: %s", media_id, message)
                stats["skipped"] += 1
                continue
        except Exception as exc:
            LOG.warning("Insights failed for %s: %s", media_id, exc)
            stats["skipped"] += 1
            continue
        values = _values(payload)
        db.upsert_post_insights(
            {
                "instagram_media_id": media_id,
                "script_id": post.get("script_id"),
                "category": post.get("category"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "reach": values.get("reach", 0),
                "views": values.get("views", 0),
                "saved": values.get("saved", 0),
                "shares": values.get("shares", 0),
                "likes": values.get("likes", 0),
                "comments": values.get("comments", 0),
                "avg_watch_ms": values.get("ig_reels_avg_watch_time", 0),
                "skip_rate": values.get("reels_skip_rate"),
                "raw_json": json_dumps(values),
            }
        )
        stats["updated"] += 1
    return stats


def category_weights(db: Database, min_posts: int = 3) -> dict[str, float]:
    """Multipliers (0.6 to 1.6) for categories with enough data.

    Score = sends per reach x3 + saves per reach x2 + likes per reach, relative
    to the account average. Bounded so no format is ever dropped completely:
    the account keeps exploring.
    """

    rows = [row for row in db.category_performance() if (row.get("posts") or 0) >= min_posts and (row.get("reach") or 0) > 0]
    if len(rows) < 2:
        return {}
    scores = {}
    for row in rows:
        reach = float(row["reach"])
        scores[row["category"]] = (3 * float(row["shares"] or 0) + 2 * float(row["saved"] or 0) + float(row["likes"] or 0)) / reach
    average = sum(scores.values()) / len(scores)
    if average <= 0:
        return {}
    return {category: max(0.6, min(1.6, score / average)) for category, score in scores.items()}


def hook_weights(db: Database, min_posts: int = 2) -> dict[str, float]:
    """Multipliers (0.5 to 1.8) per hook template, from how its reels performed."""

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT json_extract(s.metadata_json, '$.hook_id') AS hook_id,
                   COUNT(*) AS posts, SUM(i.reach) AS reach, SUM(i.shares) AS shares,
                   SUM(i.saved) AS saved, SUM(i.likes) AS likes, AVG(i.skip_rate) AS skip_rate
            FROM post_insights i JOIN scripts s ON s.id = i.script_id
            GROUP BY hook_id
            """
        ).fetchall()
    scores: dict[str, float] = {}
    for hook_id, posts, reach, shares, saved, likes, skip_rate in rows:
        if not hook_id or (posts or 0) < min_posts or not reach:
            continue
        engagement = (3 * (shares or 0) + 2 * (saved or 0) + (likes or 0)) / reach
        held = 1 - (skip_rate or 90) / 100  # share of viewers who stayed past 3 seconds
        scores[hook_id] = engagement + held
    if len(scores) < 2:
        return {}
    average = sum(scores.values()) / len(scores)
    if average <= 0:
        return {}
    return {hook_id: max(0.5, min(1.8, score / average)) for hook_id, score in scores.items()}
