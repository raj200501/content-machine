"""Public job board ingestion."""

from __future__ import annotations

import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import SourceDefinition, SourceItemCandidate
from app.source_ingest.dedupe import duplicate_hash
from app.source_ingest.pay import PayRange, from_greenhouse, from_lever
from app.source_ingest.source_ranker import extract_entities, extract_roles, freshness_score, score_relevance

LOG = logging.getLogger(__name__)

DEFAULT_FILTERS = ["intern", "internship", "new grad", "graduate", "early career", "university"]

# Role families this account covers. A posting must match one of these to be
# used, which keeps accounting / audit / sales internships out of tech reels.
TECH_ROLE_PATTERN = re.compile(
    r"\b(software|engineer(?:ing)?|developer|swe|sde|backend|back-end|frontend|front-end|full[- ]?stack|"
    r"data|machine learning|ml|ai|research|scientist|security|infrastructure|platform|mobile|ios|android|"
    r"product manag\w*|apm|product design\w*|designer|ux|site reliability|sre|devops|cloud|systems|quant\w*|"
    r"analytics|hardware|firmware|robotics)\b",
    re.IGNORECASE,
)
SENIORITY_PATTERN = re.compile(r"\b(senior|staff|principal|lead|manager|director|head of|sr\.?)\b", re.IGNORECASE)
NON_TECH_PATTERN = re.compile(
    r"\b(audit|accounting|accountant|tax|legal|counsel|sales|marketing|recruit\w*|talent|payroll|controllership|"
    r"high school|financial analyst|account development)\b",
    re.IGNORECASE,
)


def _filter_pattern(term: str) -> re.Pattern[str]:
    # Word-boundary match so "intern" does not match "internal" / "international".
    escaped = re.escape(term.strip().lower()).replace(r"\ ", r"[\s-]+")
    return re.compile(rf"\b{escaped}(s|ship|ships)?\b", re.IGNORECASE)


def _wanted(title: str, filters: list[str]) -> bool:
    if not any(_filter_pattern(term).search(title) for term in (filters or DEFAULT_FILTERS)):
        return False
    if SENIORITY_PATTERN.search(title) or NON_TECH_PATTERN.search(title):
        return False
    return bool(TECH_ROLE_PATTERN.search(title))


def _company_name(source: SourceDefinition) -> str:
    company = str(source.metadata.get("company", "")).strip()
    if company:
        return company
    return source.name.split("-")[0].replace("_", " ").title()


def _clean_location(location: str) -> str:
    location = re.sub(r"\s+", " ", location or "").strip(" ;,")
    if not location:
        return ""
    parts = [part.strip() for part in re.split(r"[;|]", location) if part.strip()]
    if len(parts) > 2:
        return f"{parts[0]} and {len(parts) - 1} more locations"
    return " or ".join(parts)


def _build_candidate(
    source: SourceDefinition,
    url: str,
    title: str,
    text: str,
    published_at: str | None,
    location: str = "",
    pay: PayRange | None = None,
    hosted_url: str = "",
) -> SourceItemCandidate | None:
    if pay:
        text = f"{text} Pay range: {pay.display}."
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
        metadata={
            "board_type": source.board_type,
            "board": source.name,
            "company": _company_name(source),
            "location": _clean_location(location),
            "job_title": title.strip(),
            "pay": pay.display if pay else "",
            "pay_spoken": pay.spoken if pay else "",
            # Greenhouse's own page for the posting: it shows the pay range even when
            # the company's careers site (the main URL) leaves it out.
            "hosted_url": hosted_url,
        },
    )


def _greenhouse_pay(source: SourceDefinition, job: dict, settings: Settings) -> PayRange | None:
    """Fetch one posting's detail with pay transparency data (only for wanted roles)."""

    job_id = job.get("id")
    if not job_id:
        return None
    try:
        response = requests.get(
            f"{source.url.rstrip('/')}/{job_id}",
            params={"pay_transparency": "true"},
            timeout=min(settings.request_timeout_seconds, 12),
            headers={"User-Agent": settings.user_agent},
        )
        response.raise_for_status()
        return from_greenhouse(response.json())
    except Exception as exc:
        LOG.debug("pay lookup failed for %s %s: %s", source.name, job_id, exc)
        return None


def _greenhouse(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    response = requests.get(source.url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent})
    response.raise_for_status()
    payload = response.json()
    items: list[SourceItemCandidate] = []
    limit = min(source.max_items, settings.max_source_items_per_ingest)
    # Filter first, then cap: large boards list hundreds of roles and the
    # early-career ones are rarely in the first page.
    for job in payload.get("jobs", []):
        title = (job.get("title") or "").strip()
        if not _wanted(title, source.filters):
            continue
        url = job.get("absolute_url") or source.url
        location = (job.get("location") or {}).get("name", "")
        text = f"{title}. {_company_name(source)}. {location}. Public Greenhouse listing."
        pay = _greenhouse_pay(source, job, settings)
        token = re.search(r"/boards/([^/]+)/", source.url)
        hosted = (
            f"https://job-boards.greenhouse.io/{token.group(1)}/jobs/{job.get('id')}"
            if token and job.get("id") and "greenhouse.io" not in url
            else ""
        )
        candidate = _build_candidate(
            source, url, title, text, job.get("first_published") or job.get("updated_at"), location, pay, hosted
        )
        if candidate:
            items.append(candidate)
        if len(items) >= limit:
            break
    return items


def _lever(source: SourceDefinition, settings: Settings) -> list[SourceItemCandidate]:
    response = requests.get(source.url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent})
    response.raise_for_status()
    items: list[SourceItemCandidate] = []
    limit = min(source.max_items, settings.max_source_items_per_ingest)
    for job in response.json():
        title = (job.get("text") or "").strip()
        if not _wanted(title, source.filters):
            continue
        location = (job.get("categories") or {}).get("location", "")
        url = job.get("hostedUrl") or source.url
        text = f"{title}. {_company_name(source)}. {location}. Public Lever listing."
        created = job.get("createdAt")
        if isinstance(created, (int, float)):
            created = datetime.utcfromtimestamp(created / 1000).isoformat()
        try:
            pay = from_lever(job)
        except Exception:  # pragma: no cover - defensive: never drop a posting over pay parsing
            pay = None
        candidate = _build_candidate(source, url, title, text, created, location, pay)
        if candidate:
            items.append(candidate)
        if len(items) >= limit:
            break
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
