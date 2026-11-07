"""Deterministic local script generation."""

from __future__ import annotations

import re
from datetime import date
from itertools import cycle

from app.models import CaptionPackage, PlannedTopic, ScriptPackage
from app.utils import json_loads
from app.writing.caption_writer import build_caption
from app.writing.prompt_templates import CATEGORY_SUBS, JOB_ALERT_CTAS, JOB_ALERT_TIPS, SCRIPT_CTAS
from app.writing.script_packs import pick_pack

CTA_CYCLE = cycle(SCRIPT_CTAS)
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
    if re.match(r"^\s*washington,?\s*d\.?\s?c\.?", location, re.I):
        return "Washington, D.C."
    first = re.split(r"\s+or\s+|\s+and\s+\d+\s+more|•|;|/", location)[0]
    first = re.sub(r"\b(Hybrid|Remote|In-Office)\s*-\s*", "", first, flags=re.I)
    first = re.sub(r"\s+-\s+.*$", "", first.split(",")[0]).strip()
    if first.lower() in {"in-office", "hybrid", "remote", ""}:
        return ""
    return first


def _posted_days(item: dict, day: str) -> int | None:
    published = str(item.get("published_at") or "")[:10]
    try:
        return max((date.fromisoformat(day) - date.fromisoformat(published)).days, 0)
    except ValueError:
        return None


def _job_details(item: dict, day: str) -> dict:
    metadata = _metadata(item)
    company = _company(item) or "One company"
    title, audience = spoken_job_title(metadata.get("job_title") or item.get("title", ""))
    location = spoken_location(metadata.get("location", ""))
    if location and title.lower().endswith(", " + location.lower()):
        title = title[: -(len(location) + 2)]
    role = title[:1].upper() + title[1:]
    if audience:
        role = f"{role} ({audience.replace('for ', '').replace(' students', '')})"
    return {
        "company": company,
        "title": title,
        "role": role,
        "audience": audience,
        "location": location,
        "pay": str(metadata.get("pay") or ""),
        "pay_spoken": str(metadata.get("pay_spoken") or ""),
        "posted_days": _posted_days(item, day),
    }


def _job_line(details: dict) -> str:
    where = f" in {details['location']}" if details["location"] else ""
    who = f", {details['audience']}" if details["audience"] else ""
    line = f"{details['company']}: {details['title']}{where}{who}"
    line = line if line.endswith(".") else line + "."
    if details["pay"]:
        # Written compactly for the screen; the voice layer says "47 to 58 dollars an hour".
        line += f" The posting lists {details['pay']}."
    return line


def _audience_word(jobs: list[dict]) -> tuple[str, str]:
    titles = " ".join(job["title"].lower() for job in jobs)
    if "intern" in titles and "new grad" not in titles:
        return "interns", "internships"
    if "new grad" in titles and "intern" not in titles:
        return "new grads", "new grad roles"
    return "students and new grads", "early-career roles"


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _job_alert(topic: PlannedTopic, evidence_items: list[dict], day_ordinal: int) -> tuple[str, list[str], list[dict]]:
    jobs = [_job_details(item, topic.day) for item in evidence_items[:3]]
    companies = [job["company"] for job in jobs]
    audience, roles = _audience_word(jobs)
    names = _join_names(companies)
    paid = [job for job in jobs if job["pay"]]
    fresh = all(job["posted_days"] is not None and job["posted_days"] <= 7 for job in jobs)
    options = [
        f"{names} are hiring {audience} right now.",
        f"Apply to these {roles} at {names} this week.",
    ]
    if fresh:
        options.append(f"{names} just posted new {roles}.")
    if paid:
        top = paid[0]
        role_word = "internship" if "intern" in top["title"].lower() else "role"
        top_pay = top["pay"].split("–")[-1]
        if "–" in top["pay"] and not top_pay.startswith(("$", "£", "€")):
            top_pay = top["pay"][0] + top_pay
        options.append(f"This {top['company']} {role_word} lists up to {top_pay}.")
    hook = options[(day_ordinal + topic.slot_index) % len(options)]
    beats = [_job_line(job) for job in jobs]
    beats.append(JOB_ALERT_TIPS[(day_ordinal + topic.slot_index) % len(JOB_ALERT_TIPS)])
    sub = {"interns": "Internships", "new grads": "New grad roles"}.get(audience, "Students & new grads")
    if paid:
        sub += "  ·  pay listed"
    scenes = [{"kind": "hook", "companies": companies, "sub": sub}]
    for job in jobs:
        scenes.append(
            {
                "kind": "job",
                "company": job["company"],
                "role": job["role"],
                "location": job["location"],
                "pay": job["pay"],
                "posted_days": job["posted_days"],
            }
        )
    scenes.append({"kind": "point", "label": "DO THIS TONIGHT"})
    return hook, beats, scenes


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
    scenes: list[dict] = []
    if topic.category == "openings_job_alert" and evidence_items:
        hook, beats, scenes = _job_alert(topic, evidence_items, day_ordinal)
        cta = JOB_ALERT_CTAS[(day_ordinal + topic.slot_index) % len(JOB_ALERT_CTAS)]
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

    if not scenes:
        scenes = [{"kind": "hook", "sub": CATEGORY_SUBS.get(topic.category, "")}]
        scenes += [{"kind": "point"} for _ in beats[:4]]
    scenes = scenes[: 1 + len(beats[:4])] + [{"kind": "cta"}]
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
        metadata={"word_count": len(full_script.split()), "scenes": scenes},
    )
