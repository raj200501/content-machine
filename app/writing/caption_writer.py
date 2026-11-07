"""Caption and hashtag generation."""

from __future__ import annotations

import re

from app.models import CaptionPackage, PlannedTopic
from app.utils import json_loads

BASE_HASHTAGS = [
    "techinternship",
    "newgradjobs",
    "softwareengineer",
    "csstudent",
    "internshipsearch",
    "jobsearchtips",
    "techcareers",
]

CATEGORY_HASHTAGS = {
    "openings_job_alert": ["internships", "hiring"],
    "application_strategy": ["jobsearch", "careeradvice"],
    "interview_prep": ["codinginterview", "leetcode"],
    "resume_portfolio": ["resumetips", "portfolio"],
    "market_context": ["techjobs", "careeradvice"],
    "motivational_community": ["studentlife", "careeradvice"],
}


def _metadata(item: dict) -> dict:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return json_loads(item.get("metadata_json"), default={}) or {}


def _hashtag(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def build_caption(
    topic: PlannedTopic,
    hook: str,
    beats: list[str],
    evidence_items: list[dict],
    cta: str,
) -> CaptionPackage:
    jobs = [item for item in evidence_items if item.get("source_type") == "job_board"]
    companies = [str(_metadata(item).get("company", "")) for item in jobs]
    source_lines = [f"- {item.get('title', 'Source')} :: {item.get('source_url', '')}" for item in evidence_items]
    compliance = "Original synthesized script from public sources. No raw URLs in spoken copy. Verify live details before posting."

    if topic.category == "openings_job_alert" and jobs:
        lines = [re.sub(r"\b[Tt]hree\b", "3", hook), ""]
        for item in jobs[:3]:
            metadata = _metadata(item)
            location = metadata.get("location") or ""
            title = metadata.get("job_title") or item.get("title", "")
            lines.append(f"• {metadata.get('company', '')}: {title}" + (f" ({location})" if location else ""))
        lines += [
            "",
            "Find each one by searching the exact title on the company's careers page. "
            "Postings change fast, so check that the role is still open.",
            "",
            cta,
        ]
    else:
        lines = [hook, "", *[f"• {beat}" for beat in beats[:4]], "", cta]

    caption_body = "\n".join(lines).strip()
    tags = BASE_HASHTAGS + CATEGORY_HASHTAGS.get(topic.category, []) + [_hashtag(name) for name in companies if name][:3]
    hashtags: list[str] = []
    for tag in tags:
        if tag and f"#{tag}" not in hashtags:
            hashtags.append(f"#{tag}")
    return CaptionPackage(
        caption=caption_body,
        hashtags=hashtags[:12],
        cta=cta,
        source_notes="\n".join(source_lines) if source_lines else "- Evergreen guidance written for early-career tech job seekers.",
        compliance_notes=compliance,
    )
