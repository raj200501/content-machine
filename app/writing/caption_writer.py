"""Caption and hashtag generation."""

from __future__ import annotations

import re

from app.models import CaptionPackage, PlannedTopic
from app.utils import json_loads

# Instagram now caps posts at a handful of hashtags and ranks mostly on content,
# captions and on-screen text, so a few specific tags beat a long list.
MAX_HASHTAGS = 5

CATEGORY_HASHTAGS = {
    "openings_job_alert": ["techinternships", "softwareengineering", "csstudents", "internships", "newgrad"],
    "application_strategy": ["internshipsearch", "csstudents", "jobsearchtips", "techcareers", "newgrad"],
    "interview_prep": ["codinginterview", "csstudents", "leetcode", "techinterview", "softwareengineering"],
    "resume_portfolio": ["resumetips", "csstudents", "techresume", "internshipsearch", "newgrad"],
    "market_context": ["techjobs", "csstudents", "techcareers", "newgrad", "internships"],
    "motivational_community": ["csstudents", "techcareers", "internshipsearch", "newgrad", "studentlife"],
}

# One keyword-rich first line per category (Instagram search reads captions).
CATEGORY_LEADS = {
    "application_strategy": "Internship application tip",
    "interview_prep": "Coding interview tip",
    "resume_portfolio": "Resume tip for CS students",
    "market_context": "Tech hiring update",
    "motivational_community": "For CS students recruiting right now",
}

QUESTIONS = {
    "openings_job_alert": [
        "Which one are you applying to?",
        "Which company should we cover next?",
        "Applied to any of these yet?",
    ],
    "application_strategy": ["What's your reply rate looking like this season?", "What's the hardest part of applying for you?"],
    "interview_prep": ["What interview question threw you off the most?", "What topic should the next tip cover?"],
    "resume_portfolio": ["What's one bullet on your resume you're unsure about?", "Want a part two on projects?"],
    "market_context": ["Seeing the same thing in your search?"],
    "motivational_community": ["How many applications are you at so far?"],
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
    questions = QUESTIONS.get(topic.category, ["What should the next one cover?"])
    question = questions[topic.slot_index % len(questions)]

    if topic.category == "openings_job_alert" and jobs:
        names = [name for name in companies if name]
        lead = "Tech internships and new grad roles open now"
        if names:
            lead += " at " + (", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0])
        lines = [lead, ""]
        for item in jobs[:3]:
            metadata = _metadata(item)
            parts = [metadata.get("job_title") or item.get("title", "")]
            if metadata.get("location"):
                parts.append(str(metadata["location"]))
            if metadata.get("pay"):
                parts.append(f"{metadata['pay']} (listed)")
            lines.append(f"• {metadata.get('company', '')}: " + " · ".join(parts))
        lines += [
            "",
            "How to apply: search the exact title on each company's careers page. Postings close fast, so check it's still open.",
            "",
            question,
            "",
            "Send this to a friend who's applying. New roles every day at @careerstacked.",
        ]
    else:
        lead = CATEGORY_LEADS.get(topic.category, "Career tip for CS students")
        lines = [f"{lead}: {hook}", "", *[f"• {beat}" for beat in beats[:4]], "", question, "", cta]

    caption_body = "\n".join(lines).strip()
    tags = list(CATEGORY_HASHTAGS.get(topic.category, CATEGORY_HASHTAGS["application_strategy"]))
    hashtags: list[str] = []
    for tag in tags:
        tag = _hashtag(tag)
        if tag and f"#{tag}" not in hashtags:
            hashtags.append(f"#{tag}")
    return CaptionPackage(
        caption=caption_body,
        hashtags=hashtags[:MAX_HASHTAGS],
        cta=cta,
        source_notes="\n".join(source_lines) if source_lines else "- Evergreen guidance written for early-career tech job seekers.",
        compliance_notes=compliance,
    )
