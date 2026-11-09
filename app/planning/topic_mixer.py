"""Daily topic planning with rotation and diversity constraints."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import cycle

from app.models import PlannedTopic
from app.planning.taxonomy import EVERGREEN_ANGLES, HOOK_STYLES, scaled_daily_buckets
from app.source_ingest.source_ranker import infer_company
from app.utils import json_loads, slugify


def _select_hook(category: str, hook_counts: Counter[str]) -> str:
    choices = sorted(HOOK_STYLES[category], key=lambda item: (hook_counts[item], item))
    hook = choices[0]
    hook_counts[hook] += 1
    return hook


def _company_repeated(company: str, company_counts: Counter[str]) -> bool:
    return bool(company) and company_counts[company.lower()] >= 2


def item_company(item: dict) -> str:
    """Best-effort company name: job boards know it exactly, news needs inference."""

    metadata = json_loads(item.get("metadata_json"), default={}) or {}
    if metadata.get("company"):
        return str(metadata["company"])
    return infer_company(item["title"], item["summary"]) or ""


def _job_groups(source_items: list[dict], company_counts: Counter[str] | None = None) -> list[list[dict]]:
    """Group real job-board postings into reels of three different companies.

    News headlines are not postings, so they are never used for job alerts.
    """

    company_counts = company_counts or Counter()
    jobs = [item for item in source_items if item["source_type"] == "job_board"]
    # Fresh postings first, then companies we have featured least recently.
    jobs.sort(
        key=lambda item: (
            # Most followers are undergrads; PhD-only roles go last.
            bool(re.search(r"\bph\.?d\b", item["title"], re.I)),
            # Postings from the last two weeks first (freshness_score >= 55)...
            item["freshness_score"] < 55,
            # ...then the ones that list pay, which make far more useful reels.
            not (json_loads(item.get("metadata_json"), default={}) or {}).get("pay"),
            -item["freshness_score"],
            company_counts[item_company(item).lower()],
            -item["relevance_score"],
        )
    )
    by_company: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for item in jobs:
        company = item_company(item).lower()
        if company not in by_company:
            order.append(company)
        by_company[company].append(item)

    groups: list[list[dict]] = []
    while True:
        available = [company for company in order if by_company[company]]
        if len(available) < 3:
            break
        group = [by_company[company].pop(0) for company in available[:3]]
        # Rotate so the next reel starts with different companies.
        order = order[3:] + order[:3]
        groups.append(group)
        if len(groups) >= 6:
            break
    return groups


ROUNDUP_WEEKDAY = 6  # Sunday: a save-worthy carousel of the week's best roles
ROUNDUP_SIZE = 8


def _roundup_items(source_items: list[dict], exclude_ids: set[int]) -> list[dict]:
    jobs = [item for item in source_items if item["source_type"] == "job_board"]
    jobs.sort(
        key=lambda item: (
            item["id"] in exclude_ids,  # prefer roles not already in today's reels
            bool(re.search(r"\bph\.?d\b", item["title"], re.I)),
            not (json_loads(item.get("metadata_json"), default={}) or {}).get("pay"),
            -item["freshness_score"],
        )
    )
    picked: list[dict] = []
    seen: set[str] = set()
    for item in jobs:
        company = item_company(item).lower()
        if company in seen:
            continue
        seen.add(company)
        picked.append(item)
        if len(picked) >= ROUNDUP_SIZE:
            break
    return picked


def _with_weekly_roundup(run_date: date, topics: list[PlannedTopic], source_items: list[dict]) -> list[PlannedTopic]:
    if run_date.weekday() != ROUNDUP_WEEKDAY or len(topics) < 3:
        return topics
    used = {item_id for topic in topics if topic.category == "openings_job_alert" for item_id in topic.source_item_ids}
    items = _roundup_items(source_items, used)
    if len(items) < 5:
        return topics
    target = next((i for i, t in enumerate(topics) if t.category == "application_strategy"), None)
    if target is None:
        target = next((i for i, t in enumerate(topics) if t.category != "openings_job_alert"), None)
    if target is None:
        return topics
    old = topics[target]
    topics[target] = PlannedTopic(
        day=old.day,
        slot_index=old.slot_index,
        scheduled_at=old.scheduled_at,
        category="jobs_roundup",
        hook_style="weekly roundup",
        title="Weekly roundup: " + ", ".join(item_company(item) for item in items[:3]),
        angle="Carousel of open early-career roles from different companies.",
        company=item_company(items[0]),
        source_item_ids=[item["id"] for item in items],
        freshness_score=sum(item["freshness_score"] for item in items) / len(items),
        metadata={"kind": "roundup", "items": [item_company(item) for item in items]},
    )
    return topics


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
    category_multipliers: dict[str, float] | None = None,
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

    source_items = open_postings(source_items, recent_scripts, run_date)
    source_items = sorted(source_items, key=lambda item: (item["freshness_score"], item["relevance_score"]), reverse=True)
    grouped_jobs = _job_groups(source_items, company_counts)
    return _build_topics(run_date, schedule_slots, source_items, grouped_jobs, company_counts, hook_counts, recent_topics, category_multipliers)


def open_postings(source_items: list[dict], recent_scripts: list[dict], run_date: date) -> list[dict]:
    """Drop postings featured in the last two weeks, and ones no longer on their board."""

    recent_urls = {
        str(item.get("source_url") or "")
        for script in recent_scripts
        if str(script.get("created_at", ""))[:10] >= (run_date - timedelta(days=14)).isoformat()
        for item in (json_loads(script.get("evidence_json"), default=[]) or [])
        if item.get("source_url")
    }
    # Job postings must still be listed on the board (seen in the last 3 days).
    still_listed_since = (run_date - timedelta(days=3)).isoformat()
    return [
        item for item in source_items
        if not (
            item["source_type"] == "job_board"
            and (
                str(item.get("source_url") or "") in recent_urls
                or (bool(item.get("fetched_at")) and str(item["fetched_at"])[:10] < still_listed_since)
            )
        )
    ]


def _build_topics(run_date, schedule_slots, source_items, grouped_jobs, company_counts, hook_counts, recent_topics, category_multipliers):
    themed = _items_by_theme(source_items)
    evergreen_cursors = {name: cycle(values) for name, values in EVERGREEN_ANGLES.items()}

    topics: list[PlannedTopic] = []
    slot_index = 0

    for category, quota in scaled_daily_buckets(len(schedule_slots), category_multipliers).items():
        for _ in range(quota):
            if slot_index >= len(schedule_slots):
                return _with_weekly_roundup(run_date, topics, source_items)
            hook_style = _select_hook(category, hook_counts)
            company = ""
            source_item_ids: list[int] = []
            title = hook_style
            angle = ""
            freshness_score = 40.0
            metadata: dict[str, object] = {"kind": "evergreen"}

            if category == "openings_job_alert" and grouped_jobs:
                chosen = grouped_jobs.pop(0)
                for item in chosen:
                    company_counts[item_company(item).lower()] += 1
                if chosen:
                    companies = [item_company(item) or item["title"].split(" ")[0] for item in chosen]
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
                    company_name = item_company(item)
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

    return _with_weekly_roundup(run_date, topics, source_items)[: len(schedule_slots)]
