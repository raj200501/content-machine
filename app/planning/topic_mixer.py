"""Daily topic planning with rotation and diversity constraints."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from itertools import cycle

from app.models import PlannedTopic
from app.planning.taxonomy import EVERGREEN_ANGLES, HOOK_STYLES, scaled_daily_buckets
from app.source_ingest.source_ranker import infer_company
from app.utils import chunked, json_loads, slugify


def _select_hook(category: str, hook_counts: Counter[str]) -> str:
    choices = sorted(HOOK_STYLES[category], key=lambda item: (hook_counts[item], item))
    hook = choices[0]
    hook_counts[hook] += 1
    return hook


def _company_repeated(company: str, company_counts: Counter[str]) -> bool:
    return bool(company) and company_counts[company.lower()] >= 2


def _job_groups(source_items: list[dict]) -> list[list[dict]]:
    jobs = [
        item
        for item in source_items
        if item["source_type"] == "job_board" or "internship" in (item["title"] + item["summary"]).lower()
    ]
    jobs.sort(key=lambda item: (item["freshness_score"], item["relevance_score"]), reverse=True)
    return chunked(jobs[:18], 3)


def _items_by_theme(source_items: list[dict]) -> dict[str, list[dict]]:
    themed = defaultdict(list)
    for item in source_items:
        text = f"{item['title']} {item['summary']}".lower()
        if any(term in text for term in ("resume", "portfolio", "github")):
            themed["resume_portfolio"].append(item)
        if any(term in text for term in ("interview", "oa", "assessment")):
            themed["interview_prep"].append(item)
        if any(term in text for term in ("recruit", "recruiter", "application", "timeline")):
            themed["application_strategy"].append(item)
        if any(term in text for term in ("layoff", "market", "hiring", "economy")):
            themed["market_context"].append(item)
    for values in themed.values():
        values.sort(key=lambda item: (item["freshness_score"], item["relevance_score"]), reverse=True)
    return themed


def build_daily_topics(
    run_date: date,
    schedule_slots: list[str],
    source_items: list[dict],
    recent_scripts: list[dict],
) -> list[PlannedTopic]:
    """Build 20 diversified daily content slots."""

    recent_topics = {slugify(script["hook"]) for script in recent_scripts}
    company_counts = Counter()
    hook_counts = Counter()
    for script in recent_scripts:
        hook_counts[script["hook"]] += 1
        evidence = json_loads(script.get("evidence_json"), default=[]) or []
        for item in evidence:
            company = item.get("company", "")
            if company:
                company_counts[company.lower()] += 1

    source_items = sorted(source_items, key=lambda item: (item["freshness_score"], item["relevance_score"]), reverse=True)
    grouped_jobs = _job_groups(source_items)
    themed = _items_by_theme(source_items)
    evergreen_cursors = {name: cycle(values) for name, values in EVERGREEN_ANGLES.items()}

    topics: list[PlannedTopic] = []
    slot_index = 0

    for category, quota in scaled_daily_buckets(len(schedule_slots)).items():
        for _ in range(quota):
            if slot_index >= len(schedule_slots):
                return topics
            hook_style = _select_hook(category, hook_counts)
            company = ""
            source_item_ids: list[int] = []
            title = hook_style
            angle = ""
            freshness_score = 40.0
            metadata: dict[str, object] = {"kind": "evergreen"}

            if category == "openings_job_alert" and grouped_jobs:
                group = grouped_jobs.pop(0)
                chosen = []
                for item in group:
                    company_name = infer_company(item["title"], item["summary"]) or ""
                    if _company_repeated(company_name, company_counts):
                        continue
                    chosen.append(item)
                    if company_name:
                        company_counts[company_name.lower()] += 1
                if chosen:
                    companies = [infer_company(item["title"], item["summary"]) or item["title"].split(" ")[0] for item in chosen]
                    title = " / ".join(companies[:3])
                    angle = "Three live-looking internship or new-grad roles worth reviewing today."
                    company = companies[0]
                    source_item_ids = [item["id"] for item in chosen]
                    freshness_score = sum(item["freshness_score"] for item in chosen) / len(chosen)
                    metadata = {"kind": "job_alert", "items": companies}
            else:
                pool = list(themed.get(category, []))
                while pool:
                    item = pool.pop(0)
                    themed[category] = pool
                    company_name = infer_company(item["title"], item["summary"]) or ""
                    if _company_repeated(company_name, company_counts):
                        continue
                    company = company_name
                    if company:
                        company_counts[company.lower()] += 1
                    source_item_ids = [item["id"]]
                    title = item["title"]
                    angle = item["summary"][:220]
                    freshness_score = item["freshness_score"]
                    metadata = {"kind": "sourced"}
                    break
                if not source_item_ids:
                    angle = next(evergreen_cursors[category])
                    title = hook_style

            topic_key = slugify(f"{category}-{title}-{angle}")[:80]
            if topic_key in recent_topics:
                angle = f"{angle} Focus on a slightly different example or framing today."
            topics.append(
                PlannedTopic(
                    day=run_date.isoformat(),
                    slot_index=slot_index,
                    scheduled_at=schedule_slots[slot_index],
                    category=category,
                    hook_style=hook_style,
                    title=title,
                    angle=angle,
                    company=company,
                    source_item_ids=source_item_ids,
                    freshness_score=freshness_score,
                    metadata=metadata,
                )
            )
            slot_index += 1

    return topics[: len(schedule_slots)]
