"""Deterministic local script generation."""

from __future__ import annotations

import re
from datetime import date
from itertools import cycle

from app.models import CaptionPackage, PlannedTopic, ScriptPackage
from app.utils import json_loads
from app.writing.caption_writer import build_caption
from app.writing.prompt_templates import JOB_ALERT_HOOKS, JOB_ALERT_TIPS, SCRIPT_CTAS
from app.writing.script_packs import pick_pack

CTA_CYCLE = cycle(SCRIPT_CTAS)
ORDINALS = ["First,", "Next,", "And"]
COUNT_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}


def _metadata(item: dict) -> dict:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return json_loads(item.get("metadata_json"), default={}) or {}


def clean_headline(title: str) -> str:
    """Drop the trailing ' - Publisher' that Google News appends to every title."""

    cleaned = re.sub(r"\s+[-–|]\s+[^-–|]{2,80}$", "", title or "").strip()
    return cleaned or (title or "").strip()


def _company(item: dict) -> str:
    metadata = _metadata(item)
    if metadata.get("company"):
        return str(metadata["company"])
    if item.get("company"):
        return str(item["company"])
    return ""


def spoken_job_title(title: str) -> tuple[str, str]:
    """Return a speakable title plus an audience note.

    'PhD Intern, Software Engineer - Graphics (2027)' -> ('Software Engineer Intern', 'for PhD students')
    """

    raw = title or ""
    audience = ""
    if re.search(r"\bph\.?d\b", raw, re.I):
        audience = "for PhD students"
    elif re.search(r"\bmaster'?s\b", raw, re.I):
        audience = "for master's students"
    new_grad = bool(re.search(r"\b(new grad|university grad\w*|graduate)\b", raw, re.I)) and not re.search(r"\bintern", raw, re.I)

    spoken = re.sub(r"[\[(][^\])]*[\])]", " ", raw)
    spoken = re.sub(r"^\s*\d{4}\s*[-–:]\s*", "", spoken)
    spoken = re.sub(r"\s+[-–]\s+.*$", "", spoken)
    spoken = re.sub(r"\b(19|20)\d{2}\b", " ", spoken)
    spoken = re.sub(r"\b(ph\.?d|master'?s|new grad|university grad\w*)\b", " ", spoken, flags=re.I)
    spoken = re.sub(r"\b(Summer|Fall|Spring|Winter)\b", " ", spoken, flags=re.I)
    spoken = re.sub(r"\s+", " ", spoken).strip(" ,-–")
    # "Intern, Software Engineer" -> "Software Engineer Intern"
    match = re.match(r"^(intern(?:ship)?)\s*,\s*(.+)$", spoken, re.I)
    if match:
        spoken = f"{match.group(2)} {match.group(1)}"
    # "Machine Learning Engineer, Intern" -> "Machine Learning Engineer Intern"
    spoken = re.sub(r",\s*(intern(?:ship)?)\b", r" \1", spoken, flags=re.I)
    spoken = re.sub(r"\binternship\b", "Intern", spoken, flags=re.I)
    spoken = re.sub(r"\s*,\s*", ", ", spoken)
    spoken = re.sub(r"\s+", " ", spoken).strip(" ,-–")
    if new_grad and spoken:
        spoken = f"new grad {spoken}"
    return (spoken or raw.strip()), audience


def spoken_location(location: str) -> str:
    if not location:
        return ""
    first = re.split(r"\s+or\s+|\s+and\s+\d+\s+more|•|;|/", location)[0]
    first = re.sub(r"\b(Hybrid|Remote|In-Office)\s*-\s*", "", first, flags=re.I)
    first = re.sub(r"\s+-\s+.*$", "", first.split(",")[0]).strip()
    if first.lower() in {"in-office", "hybrid", "remote", ""}:
        return ""
    return first


def _job_line(index: int, item: dict) -> str:
    metadata = _metadata(item)
    company = _company(item) or "One company"
    title, audience = spoken_job_title(metadata.get("job_title") or item.get("title", ""))
    location = spoken_location(metadata.get("location", ""))
    lead = ORDINALS[index] if index < len(ORDINALS) else "Also,"
    if location and title.lower().endswith(", " + location.lower()):
        title = title[: -(len(location) + 2)]
    where = f" in {location}" if location else ""
    who = f", {audience}" if audience else ""
    article = "an" if title[:1].lower() in "aeiou" else "a"
    return f"{lead} {company} is hiring {article} {title}{where}{who}."


def _job_alert(topic: PlannedTopic, evidence_items: list[dict], day_ordinal: int) -> tuple[str, list[str]]:
    jobs = evidence_items[:3]
    hook = JOB_ALERT_HOOKS[(day_ordinal + topic.slot_index) % len(JOB_ALERT_HOOKS)].format(
        count=COUNT_WORDS.get(len(jobs) or 3, "These"),
        count_lower=COUNT_WORDS.get(len(jobs) or 3, "these").lower(),
    )
    beats = [_job_line(index, item) for index, item in enumerate(jobs)]
    beats.append(JOB_ALERT_TIPS[(day_ordinal + topic.slot_index) % len(JOB_ALERT_TIPS)])
    return hook, beats


def _market_from_headline(topic: PlannedTopic, evidence_items: list[dict]) -> tuple[str, list[str]] | None:
    if not evidence_items:
        return None
    headline = clean_headline(evidence_items[0].get("title", ""))
    words = headline.split()
    if not headline or len(words) < 4 or len(words) > 18:
        return None
    return (
        "Hiring news students should know.",
        [
            f"Headline: {headline}" + ("" if headline[-1] in ".?!" else "."),
            "News like this shows where early-career hiring is actually moving.",
            "Use it to widen your search, and check the company's own careers page for live roles.",
        ],
    )


def build_script(
    topic: PlannedTopic,
    evidence_items: list[dict],
    recent_hooks: set[str] | None = None,
) -> ScriptPackage:
    cta = next(CTA_CYCLE)
    try:
        day_ordinal = date.fromisoformat(topic.day).toordinal()
    except ValueError:
        day_ordinal = 0

    hook = ""
    beats: list[str] = []
    if topic.category == "openings_job_alert" and evidence_items:
        hook, beats = _job_alert(topic, evidence_items, day_ordinal)
    elif topic.category == "market_context":
        sourced = _market_from_headline(topic, evidence_items)
        if sourced:
            hook, beats = sourced

    if not beats:
        category = topic.category if topic.category != "openings_job_alert" else "application_strategy"
        pack = pick_pack(category, day_ordinal, topic.slot_index, recent_hooks)
        if pack:
            hook = str(pack["hook"])
            beats = list(pack["beats"])  # type: ignore[arg-type]
        else:
            hook = topic.hook_style[:1].upper() + topic.hook_style[1:] + "."
            beats = [topic.angle or "Pick one small, concrete step and do it today."]

    full_script = "\n".join([hook, *beats[:4], cta])
    caption: CaptionPackage = build_caption(topic, hook, beats, evidence_items, cta)
    evidence = [
        {
            "title": item.get("title", ""),
            "source_url": item.get("source_url", ""),
            "summary": item.get("summary", ""),
            "company": _company(item),
        }
        for item in evidence_items
    ]
    return ScriptPackage(
        topic=topic,
        hook=hook,
        beats=beats[:4],
        cta=cta,
        full_script=full_script,
        caption=caption,
        evidence=evidence,
        metadata={"word_count": len(full_script.split())},
    )
