"""Hook templates for job-alert reels, chosen by evidence and by results.

Templates come from what works for career creators in this niche (salary
reveals, direct address, curiosity gaps, negative framing, specific numbers).
Every number in a hook comes from the posting itself, and a template is only
offered when its claim is true for the jobs in hand.

Choice = template prior x measured performance of that template on this
account (sends, saves and likes per reach, from the insights loop), with a
little randomness so new templates keep getting tested.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

FAANG = {"meta", "apple", "amazon", "netflix", "google", "alphabet", "microsoft"}


@dataclass(slots=True)
class Hook:
    id: str
    text: str
    prior: float


def _money(text: str) -> tuple[float, float, str] | None:
    """'$120K–$140K/yr' -> (120000, 140000, 'year')."""

    amounts = re.findall(r"[$£€](\d[\d,]*(?:\.\d+)?)([Kk])?", text or "")
    if not amounts:
        return None
    values = [float(a.replace(",", "")) * (1000 if k else 1) for a, k in amounts]
    unit = "hour" if "/hr" in text else "month" if "/mo" in text else "year"
    return min(values), max(values), unit


def annualized(pay: str) -> float:
    parsed = _money(pay)
    if not parsed:
        return 0.0
    _low, high, unit = parsed
    return high * {"hour": 2080, "month": 12, "year": 1}[unit]


def _top_amount(pay: str) -> str:
    parts = pay.split("–")
    top = parts[-1]
    if len(parts) > 1 and not top.startswith(("$", "£", "€")):
        top = pay[0] + top
    return top


def _role_noun(job: dict) -> str:
    title = job["title"].lower()
    if "intern" in title:
        return "interns"
    if "new grad" in title or "graduate" in title:
        return "new grads"
    return "early-career engineers"


def job_alert_candidates(jobs: list[dict], audience: str, roles: str) -> list[Hook]:
    names = [job["company"] for job in jobs]
    joined = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else (names[0] if names else "")
    hooks = [
        Hook("names_hiring", f"{joined} are hiring {audience} right now.", 0.6),
    ]
    if all(job.get("posted_days") is not None and job["posted_days"] <= 7 for job in jobs):
        hooks.append(Hook("names_just_posted", f"{joined} just posted new {roles}.", 0.75))

    paid = [job for job in jobs if job.get("pay")]
    if paid:
        top = max(paid, key=lambda job: annualized(job["pay"]))
        amount = _top_amount(top["pay"])
        noun = _role_noun(top)
        hooks.append(Hook("company_pays", f"{top['company']} pays {noun} up to {amount}.", 1.0))
        parsed = _money(top["pay"])
        if parsed and parsed[0] < parsed[1]:
            low = top["pay"].split("–")[0]
            hooks.append(Hook("posted_range", f"{top['company']} posted the pay: {low} to {amount}.", 0.85))
        if parsed and parsed[2] == "hour" and noun == "interns":
            hooks.append(Hook("as_an_intern", f"{amount.replace('/hr', '')} an hour. As an intern. At {top['company']}.", 1.0))
            if top["company"].lower() not in FAANG:
                hooks.append(Hook("not_faang", f"This internship pays {amount} and it isn't FAANG.", 0.95))
        what = re.sub(r"\s*(intern(ship)?|new grad)\b.*$", "", top["title"], flags=re.I).strip()
        if what and len(what.split()) <= 4 and noun == "interns":
            hooks.append(Hook("what_make", f"What does a {what} intern at {top['company']} make?", 0.9))
    if len(paid) == len(jobs) and len(jobs) >= 2:
        units = {(_money(job["pay"]) or (0, 0, ""))[2] for job in jobs}
        if len(units) == 1:
            # Every role's posted minimum is at least this, so "at least" is true.
            floor = min((_money(job["pay"]) or (0, 0, ""))[0] for job in jobs)
            unit = units.pop()
            suffix = {"hour": "/hr", "month": "/mo", "year": "/yr"}[unit]
            shown = f"${floor / 1000:.0f}K{suffix}" if unit == "year" else f"${floor:,.0f}{suffix}"
            hooks.append(Hook("n_paying_over", f"{len(jobs)} {roles} that pay at least {shown}, still open.", 0.8))
    years = sorted({y for job in jobs for y in re.findall(r"\b(20[2-3]\d)\b", job["title"])})
    if len(years) == 1:
        hooks.append(Hook("grad_year", f"Graduating in {years[0]}? Don't scroll past this.", 0.7))
    return hooks


def choose_hook(
    candidates: list[Hook],
    performance: dict[str, float] | None,
    recent_ids: list[str],
    seed: int,
) -> Hook:
    """Pick a hook: prior x measured performance, skipping the last two templates used."""

    rng = random.Random(seed)
    pool = [hook for hook in candidates if hook.id not in recent_ids[:2]] or candidates
    weights = []
    for hook in pool:
        weight = hook.prior * (performance or {}).get(hook.id, 1.0)
        weights.append(max(weight, 0.05) * rng.uniform(0.75, 1.25))  # keep exploring
    return pool[max(range(len(pool)), key=weights.__getitem__)]
