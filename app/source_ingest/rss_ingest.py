"""RSS and public feed ingestion."""

from __future__ import annotations

import logging
from datetime import datetime

import feedparser
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import SourceDefinition, SourceItemCandidate
from app.source_ingest.article_fetch import fetch_article
from app.source_ingest.dedupe import duplicate_hash
from app.source_ingest.source_ranker import (
    extract_entities,
    extract_roles,
    freshness_score,
    parse_datetime,
    score_relevance,
)
from app.utils import normalize_whitespace

LOG = logging.getLogger(__name__)


def _entry_published(entry: dict) -> str | None:
    value = entry.get("published") or entry.get("updated")
    dt = parse_datetime(value)
    return dt.isoformat() if isinstance(dt, datetime) else None


def ingest_feed(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    """Convert an RSS/Atom feed into normalized source items."""

    parsed = feedparser.parse(source.url)
    items: list[SourceItemCandidate] = []

    for entry in parsed.entries[: min(source.max_items, settings.max_source_items_per_ingest)]:
        link = entry.get("link")
        title = normalize_whitespace(entry.get("title", "Untitled"))
        if not link or not title:
            continue

        summary_html = entry.get("summary", "") or entry.get("description", "")
        summary = normalize_whitespace(BeautifulSoup(summary_html, "html.parser").get_text(" "))
        text_content = summary

        if source.fetch_article:
            try:
                article = fetch_article(link, settings)
                text_content = article.text or text_content
                summary = article.summary or summary
            except Exception as exc:  # pragma: no cover - network failures are expected in practice.
                LOG.debug("Article fetch failed for %s: %s", link, exc)

        relevance = score_relevance(title, text_content)
        if relevance < 8:
            continue

        published_at = _entry_published(entry)
        combined = f"{title}. {text_content}"
        items.append(
            SourceItemCandidate(
                source_type=source.source_type,
                source_url=link,
                title=title,
                published_at=published_at,
                fetched_at=datetime.utcnow().isoformat(),
                text_content=text_content,
                summary=summary[:500],
                extracted_entities=extract_entities(combined),
                extracted_roles=extract_roles(combined),
                freshness_score=freshness_score(published_at),
                relevance_score=relevance,
                duplicate_hash=duplicate_hash(title, text_content),
                metadata={"feed": source.name, "category": source.category},
            )
        )

    return items
