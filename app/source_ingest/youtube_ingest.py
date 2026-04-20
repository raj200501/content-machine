"""Public YouTube feed and transcript ingestion."""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime

import feedparser

from app.config import Settings
from app.models import SourceDefinition, SourceItemCandidate
from app.source_ingest.dedupe import duplicate_hash
from app.source_ingest.source_ranker import extract_entities, extract_roles, freshness_score, score_relevance

LOG = logging.getLogger(__name__)

try:  # pragma: no cover - optional API availability depends on environment and network.
    from youtube_transcript_api import YouTubeTranscriptApi
except Exception:  # pragma: no cover
    YouTubeTranscriptApi = None


def _video_id(link: str) -> str:
    parsed = urllib.parse.urlparse(link)
    query = urllib.parse.parse_qs(parsed.query)
    return query.get("v", [""])[0]


def _transcript_text(video_id: str) -> str:
    if not video_id or YouTubeTranscriptApi is None:
        return ""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
    except Exception:
        return ""
    return " ".join(segment.get("text", "") for segment in transcript)


def ingest_youtube(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    feed_url = source.url
    if source.channel_id and "youtube.com/feeds/videos.xml" not in feed_url:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={source.channel_id}"
    parsed = feedparser.parse(feed_url)
    items: list[SourceItemCandidate] = []

    for entry in parsed.entries[: min(source.max_items, settings.max_source_items_per_ingest)]:
        title = entry.get("title", "")
        link = entry.get("link", "")
        if not title or not link:
            continue
        transcript = ""
        if settings.enable_youtube_transcripts:
            transcript = _transcript_text(_video_id(link))
        text = transcript or entry.get("summary", "")
        relevance = score_relevance(title, text)
        if relevance < 8:
            continue
        combined = f"{title}. {text}"
        published = entry.get("published")
        items.append(
            SourceItemCandidate(
                source_type=source.source_type,
                source_url=link,
                title=title,
                published_at=published,
                fetched_at=datetime.utcnow().isoformat(),
                text_content=text[:4000],
                summary=text[:500],
                extracted_entities=extract_entities(combined),
                extracted_roles=extract_roles(combined),
                freshness_score=freshness_score(published),
                relevance_score=relevance,
                duplicate_hash=duplicate_hash(title, text),
                metadata={"feed": source.name, "video_id": _video_id(link)},
            )
        )
    return items
