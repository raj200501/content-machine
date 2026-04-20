"""Relevance, freshness, and lightweight entity extraction."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

EARLY_CAREER_KEYWORDS = {
    "intern",
    "internship",
    "new grad",
    "new-grad",
    "graduate",
    "campus",
    "student",
    "entry level",
    "entry-level",
    "associate",
    "recruiter",
    "resume",
    "technical interview",
    "behavioral interview",
    "return offer",
    "portfolio",
    "oa",
    "online assessment",
}
NEGATIVE_KEYWORDS = {"senior", "staff", "principal", "director", "vp"}
ROLE_PATTERNS = {
    "software_engineering": r"software|backend|frontend|full[- ]stack|mobile|developer",
    "data": r"data|analytics|business intelligence",
    "ml_ai": r"machine learning|ml|ai|research engineer|data science",
    "pm": r"product manager|product management|program manager",
    "design": r"designer|ux|ui",
    "internship": r"\bintern(ship)?\b",
    "new_grad": r"new grad|graduate|campus hire|entry[- ]level|university",
}
COMPANY_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9&.+-]+(?:\s+[A-Z][A-Za-z0-9&.+-]+){0,2})\b")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


def freshness_score(published_at: str | None) -> float:
    dt = parse_datetime(published_at)
    if dt is None:
        return 35.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_hours = max((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 0)
    if age_hours <= 24:
        return 100.0
    if age_hours <= 72:
        return 85.0
    if age_hours <= 168:
        return 70.0
    if age_hours <= 336:
        return 55.0
    return 30.0


def score_relevance(title: str, text: str) -> float:
    corpus = f"{title} {text}".lower()
    score = 0.0
    for keyword in EARLY_CAREER_KEYWORDS:
        if keyword in corpus:
            score += 8.0 if keyword in title.lower() else 4.0
    for keyword in NEGATIVE_KEYWORDS:
        if keyword in corpus:
            score -= 6.0
    if "software engineer" in corpus or "swe" in corpus:
        score += 8.0
    if "new grad" in corpus or "intern" in corpus:
        score += 12.0
    return max(score, 0.0)


def extract_roles(text: str) -> list[str]:
    corpus = text.lower()
    roles = [name for name, pattern in ROLE_PATTERNS.items() if re.search(pattern, corpus)]
    return sorted(set(roles))


def extract_entities(text: str) -> list[str]:
    entities = []
    for match in COMPANY_PATTERN.findall(text):
        if match.lower() in {"software engineer", "new grad", "career services"}:
            continue
        entities.append(match.strip())
    return sorted(set(entities))[:8]


def infer_company(title: str, text: str) -> str:
    entities = extract_entities(f"{title}. {text[:250]}")
    return entities[0] if entities else ""
