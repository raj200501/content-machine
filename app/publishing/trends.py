"""Trend radar: what is working for other accounts in this niche right now.

Uses Instagram's own Business Discovery API (free, same token): for each
public business/creator account in the niche it reads the latest posts with
like and comment counts. A post that beats its own account's median
engagement by 2x or more is an "outperformer". Outperformers are sorted
into topics, and those topics tilt which of our formats get made.

It learns the idea, never copies the video: copying another creator's reel
would also be treated by Instagram as unoriginal and cut the account's reach.
"""

from __future__ import annotations

import logging
import re
import statistics
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.db import Database

LOG = logging.getLogger(__name__)

# Public accounts in the CS career niche (personal accounts are skipped automatically,
# since Business Discovery only sees business and creator accounts).
WATCHLIST = [
    "zero2sudo", "sajjaadkhader", "allenvert", "arjay_the_dev", "conniecodes", "wonsulting",
    "salarytransparentstreet", "neetcode", "simplify.jobs", "joinhandshake", "levels.fyi",
    "thecodingsloth", "codewithvincent", "techwithtim", "jomakaze", "careerswithmeg",
]

TOPICS = {
    "job_list": r"\b(hiring|internships?|new grad|openings?|apply|applications? (are )?open|still open|roles?|deadline)\b",
    "pay": r"(\$\d|\bsalary|\bpay(s|ing)?\b|\bcomp(ensation)?\b|\b\d{2,3}k\b|per hour|/hr|\boffer\b)",
    "resume": r"\b(resume|cv|bullet|portfolio|github profile)\b",
    "interview": r"\b(interview|leetcode|behavioral|system design|coding round|recruiter call|oa\b|online assessment)",
    "search_hack": r"\b(linkedin|trick|hack|filter|search|nobody talks about|secret|website)\b",
    "market": r"\b(market|layoffs?|ai (is|will)|unemploy|hiring freeze|economy|cs degree)\b",
}
TOPIC_FORMATS = {
    "job_list": ["job_alert", "countdown", "spotlight"],
    "pay": ["countdown", "pay_tiers", "job_alert"],
    "resume": ["redline"],
    "interview": ["chat"],
    "search_hack": ["hack"],
    "market": ["pay_tiers", "countdown"],
}


def topics_of(caption: str) -> list[str]:
    text = (caption or "").lower()
    return [name for name, pattern in TOPICS.items() if re.search(pattern, text)]


def _ensure_table(db: Database) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trend_posts (
                permalink TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                caption TEXT NOT NULL,
                likes INTEGER NOT NULL,
                comments INTEGER NOT NULL,
                followers INTEGER NOT NULL,
                ratio REAL NOT NULL,
                topics TEXT NOT NULL,
                media_type TEXT,
                posted_at TEXT,
                fetched_at TEXT NOT NULL
            )
            """
        )


def collect_trends(db: Database, settings: Settings) -> dict:
    """Read the watchlist's recent posts and store each one's performance vs its account."""

    from app.publishing.instagram_meta import InstagramMetaPublisher

    _ensure_table(db)
    stats = {"accounts": 0, "posts": 0, "outperformers": 0, "skipped": []}
    if settings.dry_run or not settings.instagram_access_token:
        return stats
    publisher = InstagramMetaPublisher(settings)
    try:
        token, user_id = publisher.publish_credentials()
    except Exception as exc:
        stats["skipped"].append(f"credentials: {str(exc)[:120]}")
        return stats
    now = datetime.now(timezone.utc).isoformat()
    for username in WATCHLIST:
        fields = (
            f"business_discovery.username({username})"
            "{followers_count,media.limit(30){caption,like_count,comments_count,media_type,media_product_type,timestamp,permalink}}"
        )
        try:
            payload = publisher._request("GET", user_id, params={"fields": fields, "access_token": token})
        except Exception as exc:  # personal account, renamed, or not allowed
            stats["skipped"].append(f"{username}: {str(exc)[:80]}")
            continue
        found = payload.get("business_discovery") or {}
        followers = int(found.get("followers_count") or 0)
        media = (found.get("media") or {}).get("data") or []
        if not followers or not media:
            stats["skipped"].append(f"{username}: no public posts")
            continue
        stats["accounts"] += 1
        scores = [((m.get("like_count") or 0) + 3 * (m.get("comments_count") or 0)) for m in media]
        median = statistics.median(scores) or 1
        with db.connect() as conn:
            for post, score in zip(media, scores):
                ratio = score / median
                caption = (post.get("caption") or "")[:600]
                topics = topics_of(caption)
                conn.execute(
                    """
                    INSERT INTO trend_posts(permalink, username, caption, likes, comments, followers, ratio, topics, media_type, posted_at, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(permalink) DO UPDATE SET likes = excluded.likes, comments = excluded.comments,
                        followers = excluded.followers, ratio = excluded.ratio, topics = excluded.topics, fetched_at = excluded.fetched_at
                    """,
                    (
                        post.get("permalink") or f"{username}:{post.get('timestamp')}",
                        username, caption, int(post.get("like_count") or 0), int(post.get("comments_count") or 0),
                        followers, ratio, ",".join(topics), post.get("media_product_type") or post.get("media_type"),
                        post.get("timestamp"), now,
                    ),
                )
                stats["posts"] += 1
                stats["outperformers"] += int(ratio >= 2)
    return stats


def trend_format_weights(db: Database, days: int = 30) -> dict[str, float]:
    """Format -> weight (0.75-1.5) from which topics are outperforming in the niche."""

    _ensure_table(db)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT topics FROM trend_posts WHERE ratio >= 2 AND (posted_at IS NULL OR posted_at >= ?)", (since,)
        ).fetchall()
    counts: dict[str, int] = {}
    for (topics,) in rows:
        for topic in filter(None, (topics or "").split(",")):
            counts[topic] = counts.get(topic, 0) + 1
    if sum(counts.values()) < 5:
        return {}
    total = sum(counts.values())
    weights: dict[str, float] = {}
    for topic, count in counts.items():
        share = count / total
        for fmt in TOPIC_FORMATS.get(topic, []):
            weights[fmt] = max(weights.get(fmt, 0.0), share)
    top = max(weights.values()) or 1
    return {fmt: round(0.75 + 0.75 * value / top, 3) for fmt, value in weights.items()}


def top_outperformers(db: Database, limit: int = 8, days: int = 14) -> list[dict]:
    _ensure_table(db)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT username, caption, likes, comments, ratio, topics, permalink FROM trend_posts
               WHERE ratio >= 2 AND (posted_at IS NULL OR posted_at >= ?) ORDER BY ratio DESC LIMIT ?""",
            (since, limit),
        ).fetchall()
    keys = ["username", "caption", "likes", "comments", "ratio", "topics", "permalink"]
    return [dict(zip(keys, row)) for row in rows]
