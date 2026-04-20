"""Deterministic local script generation."""

from __future__ import annotations

from itertools import cycle

from app.models import CaptionPackage, PlannedTopic, ScriptPackage
from app.writing.caption_writer import build_caption
from app.writing.prompt_templates import SCRIPT_CTAS

CTA_CYCLE = cycle(SCRIPT_CTAS)


def _company(item: dict) -> str:
    return item.get("company") or item.get("title", "").split(" ")[0]


def _job_alert_beats(evidence_items: list[dict]) -> list[str]:
    beats = []
    for item in evidence_items[:3]:
        beats.append(f"{_company(item)} has a public posting that looks worth checking.")
    beats.append("Match your resume keywords to the role family before you apply.")
    return beats[:4]


def _strategy_beats(topic: PlannedTopic, evidence_items: list[dict]) -> list[str]:
    if evidence_items:
        item = evidence_items[0]
        return [
            f"Students miss replies when every application sounds the same.",
            f"{item.get('summary', topic.angle)[:90].rstrip('.')}.",
            "Tighten your resume, recruiter note, and project story around one role family.",
            "That usually beats blasting another fifty cold applications.",
        ]
    return [
        "A generic resume makes every application feel lower signal.",
        topic.angle,
        "Batch similar roles together so your materials stay consistent.",
        "That keeps your follow-up cleaner too.",
    ]


def _interview_beats(topic: PlannedTopic, evidence_items: list[dict]) -> list[str]:
    source = evidence_items[0]["summary"] if evidence_items else topic.angle
    return [
        "Most students overpractice questions and underpractice explanations.",
        source[:95].rstrip(".") + ".",
        "Say your tradeoffs out loud, then end with what you'd improve next.",
        "That makes even imperfect answers sound more hireable.",
    ]


def _resume_beats(topic: PlannedTopic, evidence_items: list[dict]) -> list[str]:
    source = evidence_items[0]["summary"] if evidence_items else topic.angle
    return [
        "If your resume reads like coursework only, it will blur together.",
        source[:95].rstrip(".") + ".",
        "Lead with shipped work, measurable impact, and tools next to results.",
        "Then pin two repos that prove the story.",
    ]


def _market_beats(topic: PlannedTopic, evidence_items: list[dict]) -> list[str]:
    source = evidence_items[0]["summary"] if evidence_items else topic.angle
    return [
        "The market is mixed, not hopeless.",
        source[:100].rstrip(".") + ".",
        "Wider role coverage matters right now: SWE, data, ML, PM, and adjacent analyst roles.",
        "Treat this like a process problem, not a personal verdict.",
    ]


def _motivation_beats(topic: PlannedTopic) -> list[str]:
    return [
        "You do not need a perfect resume week to get momentum back.",
        topic.angle,
        "Pick one role family, one project bullet fix, and one follow-up today.",
        "Tiny consistency beats panic every time.",
    ]


def build_script(topic: PlannedTopic, evidence_items: list[dict]) -> ScriptPackage:
    cta = next(CTA_CYCLE)
    if topic.category == "openings_job_alert":
        hook = "Three early-career tech roles worth checking today."
        beats = _job_alert_beats(evidence_items)
    elif topic.category == "application_strategy":
        hook = topic.hook_style.capitalize() + "."
        beats = _strategy_beats(topic, evidence_items)
    elif topic.category == "interview_prep":
        hook = topic.hook_style.capitalize() + "."
        beats = _interview_beats(topic, evidence_items)
    elif topic.category == "resume_portfolio":
        hook = topic.hook_style.capitalize() + "."
        beats = _resume_beats(topic, evidence_items)
    elif topic.category == "market_context":
        hook = topic.hook_style.capitalize() + "."
        beats = _market_beats(topic, evidence_items)
    else:
        hook = topic.hook_style.capitalize() + "."
        beats = _motivation_beats(topic)

    full_script = "\n".join([hook, *beats[:4], cta])
    caption: CaptionPackage = build_caption(topic, beats, evidence_items, cta)
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
