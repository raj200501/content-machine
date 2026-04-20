"""Fetch and extract public article bodies."""

from __future__ import annotations

import logging
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass

import requests
import trafilatura

from app.config import Settings
from app.utils import normalize_whitespace

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class ArticleContent:
    text: str
    summary: str


def robots_allows(url: str, settings: Settings) -> bool:
    parsed = urllib.parse.urlparse(url)
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    try:
        parser.set_url(robots_url)
        parser.read()
        return parser.can_fetch(settings.user_agent, url)
    except Exception:
        return True


def fetch_article(url: str, settings: Settings) -> ArticleContent:
    """Fetch and extract a public article while respecting robots.txt when possible."""

    if not robots_allows(url, settings):
        raise ValueError(f"robots.txt disallows fetch: {url}")

    response = requests.get(
        url,
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()

    extracted = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=False,
        url=url,
    )
    text = normalize_whitespace(extracted or "")
    if not text:
        text = normalize_whitespace(response.text[:4000])

    summary = ". ".join(text.split(". ")[:3]).strip()
    if not summary:
        summary = text[:280]
    return ArticleContent(text=text, summary=summary)
