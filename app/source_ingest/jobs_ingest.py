"""Public job board ingestion."""

from __future__ import annotations

import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import SourceDefinition, SourceItemCandidate
from app.source_ingest.dedupe import duplicate_hash
from app.source_ingest.source_ranker import extract_entities, extract_roles, freshness_score, score_relevance

LOG = logging.getLogger(__name__)

DEFAULT_FILTERS = ["intern", "internship", "new grad", "graduate", "early career", "university"]


def _wanted(title: str, filters: list[str]) -> bool:
    lowered = title.lower()
    return any(term.lower() in lowered for term in (filters or DEFAULT_FILTERS))


def _build_candidate(source: SourceDefinition, url: str, title: str, text: str, published_at: str | None) -> SourceItemCandidate | None:
    relevance = score_relevance(title, text)
    if relevance < 10:
        return None
    combined = f"{title}. {text}"
    return SourceItemCandidate(
        source_type=source.source_type,
        source_url=url,
        title=title,
        published_at=published_at,
        fetched_at=datetime.utcnow().isoformat(),
        text_content=text,
        summary=text[:500],
        extracted_entities=extract_entities(combined),
        extracted_roles=extract_roles(combined),
        freshness_score=freshness_score(published_at),
        relevance_score=relevance,
        duplicate_hash=duplicate_hash(title, text),
        metadata={"board_type": source.board_type, "board": source.name},
    )


def _greenhouse(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    response = requests.get(source.url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent})
    response.raise_for_status()
    payload = response.json()
    items: list[SourceItemCandidate] = []
    for job in payload.get("jobs", [])[: min(source.max_items, settings.max_source_items_per_ingest)]:
        title = job.get("title", "")
        if not _wanted(title, source.filters):
            continue
        url = job.get("absolute_url") or source.url
        location = job.get("location", {}).get("name", "")
        text = f"{title}. {location}. Public Greenhouse listing."
        candidate = _build_candidate(source, url, title, text, job.get("updated_at"))
        if candidate:
            items.append(candidate)
    return items


def _lever(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    response = requests.get(source.url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent})
    response.raise_for_status()
    items: list[SourceItemCandidate] = []
    for job in response.json()[: min(source.max_items, settings.max_source_items_per_ingest)]:
        title = job.get("text", "")
        if not _wanted(title, source.filters):
            continue
        location = (job.get("categories") or {}).get("location", "")
        url = job.get("hostedUrl") or source.url
        text = f"{title}. {location}. Public Lever listing."
        candidate = _build_candidate(source, url, title, text, job.get("createdAt"))
        if candidate:
            items.append(candidate)
    return items


def _generic_html(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    response = requests.get(source.url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items: list[SourceItemCandidate] = []
    for anchor in soup.find_all("a", href=True):
        title = " ".join(anchor.stripped_strings)
        if not title or not _wanted(title, source.filters):
            continue
        url = anchor["href"]
        if url.startswith("/"):
            url = source.url.rstrip("/") + url
        text = f"{title}. Public careers page listing."
        candidate = _build_candidate(source, url, title, text, None)
        if candidate:
            items.append(candidate)
        if len(items) >= min(source.max_items, settings.max_source_items_per_ingest):
            break
    return items


def ingest_job_board(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    if source.board_type == "greenhouse":
        return _greenhouse(source, settings)
    if source.board_type == "lever":
        return _lever(source, settings)
    return _generic_html(source, settings)
