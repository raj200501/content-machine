"""Reel formats that win in this niche, built from real data.

Each builder returns the voice lines and one scene spec per line, so the studio
renderer knows exactly what to show while each line is spoken. Formats come
from research on what gets views and sends for CS-career content:

- job_alert    one real role, the pay on frame one, the proof, how it compares
               to every role we track (original analysis), who it's for, a tip
- countdown    "5 internships still hiring, #1 pays $X": best saved for last
- pay_tiers    S/A/B/C tier board of intern pay at companies hiring now
- redline      a weak resume bullet rewritten live, and why it works
- chat         an interview question, the answer most people give, the one that works
- hack         a real search trick, shown by editing the link

The account's commentary (market comparison, eligibility, tips) is what makes
job reels original rather than reposted listings.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from app.insight.job_stats import JobRecord, Market
from app.writing.libraries import CHATS, HACKS, REDLINES, ROLE_TIPS, role_family

STUDIO_FORMATS = {"job_alert", "countdown", "pay_tiers", "redline", "chat", "hack"}

HASHTAGS = {
    "job": ["#swe", "#internships", "#csmajor", "#techjobs", "#newgrad"],
    "resume": ["#resumetips", "#csmajor", "#internships", "#techcareers"],
    "interview": ["#codinginterview", "#interviewtips", "#csmajor", "#swe"],
    "search": ["#jobsearch", "#internships", "#csmajor", "#techjobs"],
}

CTA_SEND = [
    "Send this to a friend who's applying.",
    "Send this to the friend who's still looking.",
    "Send this to someone applying this month.",
]


@dataclass
class FormatScript:
    format: str
    variant: str
    lines: list[str]
    scenes: list[dict]
    caption: str
    hashtags: list[str]
    jobs: list[JobRecord] = field(default_factory=list)

    @property
    def hook(self) -> str:
        return self.lines[0]

    @property
    def hook_id(self) -> str:
        return f"fmt:{self.format}:{self.variant}"


# ------------------------------------------------------------- job helpers --


def short_role(job: JobRecord) -> str:
    """'Master's Machine Learning Engineer, Intern' -> 'ML intern'."""

    title = job.title.lower()
    family = role_family(job.title)
    base = {
        "ml": "ML",
        "data": "data",
        "security": "security",
        "mobile": "mobile",
        "frontend": "frontend",
        "infra": "infrastructure",
        "hardware": "hardware",
    }.get(family, "software")
    if "product design" in title or "designer" in title:
        base = "design"
    elif "product manag" in title:
        base = "product"
    if job.level == "intern":
        return f"{base} intern"
    if job.level == "new_grad":
        return f"new grad {base} engineer" if base not in {"design", "product"} else f"new grad {base}"
    return f"{base} role"


def eligibility(job: JobRecord) -> str:
    title = job.title
    parts = []
    season = re.search(r"(summer|fall|winter|spring)\s*(20\d\d)", title, re.I)
    year = re.search(r"\b(20\d\d)\b", title)
    if season:
        parts.append(f"{season.group(1).title()} {season.group(2)}")
    elif job.level == "new_grad" and year:
        parts.append(f"{year.group(1)} grads")
    if re.search(r"master", title, re.I):
        parts.append("master's students")
    elif re.search(r"ph\.?d", title, re.I):
        parts.append("PhD students")
    elif re.search(r"undergrad|bachelor", title, re.I):
        parts.append("undergrads")
    return ", ".join(parts)


def screen_location(location: str) -> str:
    loc = re.sub(r",?\s*(United States|USA|US)$", "", location or "").strip()
    loc = loc.split(";")[0].split("|")[0].strip()
    return re.sub(r"\s*,\s*", ", ", loc)


def spoken_location(location: str) -> str:
    """City only for the voice ("San Mateo"), since state codes read badly aloud."""

    loc = screen_location(location)
    if not loc:
        return ""
    if loc.lower().startswith("remote"):
        return "remote"
    city = loc.split(",")[0].strip()
    return {"NYC": "New York", "SF": "San Francisco"}.get(city, city)


def _job_scene(job: JobRecord, kind: str, **extra) -> dict:
    return {
        "kind": kind,
        "company": job.company,
        "title": job.title,
        "role": short_role(job),
        "pay": job.pay_headline(),
        "pay_range": (job.metadata.get("pay") or ""),
        "location": screen_location(job.location),
        "url": job.url,
        "alt_url": job.alt_url,
        "posted_days": job.days_old,
        **extra,
    }


def _caption_for_jobs(jobs: list[JobRecord], lead: str, closer: str) -> str:
    lines = [lead, ""]
    for job in jobs:
        bits = [job.company, job.title]
        if job.location:
            bits.append(screen_location(job.location))
        line = " · ".join(b for b in bits if b)
        if job.pay:
            line += f" · {job.metadata.get('pay') or job.pay_headline()} (listed)"
        lines.append("• " + line)
    lines += ["", "Pay is the range listed on each posting. Apply links for every role are in the link in my bio.", "", closer]
    return "\n".join(lines)


def _pct_phrase(pct: float, count: int, level: str) -> str | None:
    pool = "intern roles" if level == "intern" else "new grad roles"
    if pct >= 8:
        return f"That range sits {round(pct)}% above the median of the {count} {pool} I track."
    if pct <= -8:
        return f"That range sits {round(-pct)}% below the median of the {count} {pool} I track."
    return f"That range is right around the median of the {count} {pool} I track."


# ----------------------------------------------------------------- formats --


def job_alert(job: JobRecord, market: Market, rng: random.Random) -> FormatScript:
    role = short_role(job)
    pay = job.pay_headline()
    fresh = job.days_old is not None and job.days_old <= 3
    variants = [
        ("pays", f"{job.company} is paying {role}s up to {pay}, and it's still open."),
        ("just_posted" if fresh else "open_now", f"{job.company} just posted a {role} role that pays up to {pay}." if fresh else f"This {role} role at {job.company} pays up to {pay}. Still open."),
    ]
    variant, hook = variants[rng.randrange(len(variants))]
    lines = [hook]
    scenes = [_job_scene(job, "alert_hook", badge="JUST POSTED" if fresh else "STILL OPEN")]
    lines.append(rng.choice(["That's straight from their job posting.", "Here's the posting, pay range and all."]))
    scenes.append(_job_scene(job, "proof"))
    compared = market.compare(job)
    if compared:
        pct, count = compared
        phrase = _pct_phrase(pct, count, job.level)
        if phrase:
            median = market.intern_median if job.level == "intern" else market.new_grad_median
            lines.append(phrase)
            scenes.append(_job_scene(job, "market_bar", pct=round(pct), median=median, count=count, level=job.level))
    who = eligibility(job)
    where = spoken_location(job.location)
    if who and where:
        sentence = f"It's for {who}, based in {where}."
    elif who:
        sentence = f"It's for {who}."
    elif where:
        sentence = f"It's based in {where}."
    else:
        sentence = ""
    if sentence:
        lines.append(sentence)
        scenes.append(_job_scene(job, "facts", who=who))
    tip = ROLE_TIPS[role_family(job.title)]
    lines.append(f"Tip: {tip[0].lower() + tip[1:]}")
    scenes.append({"kind": "tip", "text": tip, "company": job.company})
    lines.append(f"The apply link is in my bio. {rng.choice(CTA_SEND)}")
    scenes.append(_job_scene(job, "cta"))
    caption = _caption_for_jobs(
        [job],
        f"{job.company} {job.title}: up to {pay} (listed on the posting)",
        "Which company should I check next?",
    )
    return FormatScript("job_alert", variant, lines, scenes, caption, HASHTAGS["job"][:4], [job])


def countdown(jobs: list[JobRecord], market: Market, rng: random.Random) -> FormatScript | None:
    # One level per list (hourly intern pay and yearly salaries don't rank together),
    # and one role per company.
    paid: list[JobRecord] = []
    for level in ("intern", "new_grad"):
        best: dict[str, JobRecord] = {}
        for job in jobs:
            if job.level == level and job.pay and job.usd:
                if job.company not in best or job.top_pay > best[job.company].top_pay:
                    best[job.company] = job
        if len(best) >= 4:
            paid = sorted(best.values(), key=lambda j: j.top_pay)
            break
    if len(paid) < 4:
        return None
    picks = paid[-5:]
    n = len(picks)
    top = picks[-1]
    level_word = "internships" if picks[0].level == "intern" else "new grad roles"
    floor = picks[0].pay_headline()
    hook = rng.choice(
        [
            f"{n} {level_word} still hiring right now. Number one pays {top.pay_headline()}.",
            f"{n} tech {level_word} paying up to {floor} or more, still open. Wait for number one.",
        ]
    )
    variant = "top_pay" if "Number one" in hook else "wait"
    lines = [hook]
    scenes = [{"kind": "countdown_intro", "n": n, "top": top.pay_headline(), "level": level_word,
               "companies": [j.company for j in picks]}]
    words = {5: "five", 4: "four", 3: "three", 2: "two", 1: "one"}
    for rank, job in zip(range(n, 0, -1), picks):
        if rank == 1:
            line = f"And number one: {job.company}, up to {job.pay_headline()} for {short_role(job)}s."
            compared = market.compare(job)
            if compared and compared[0] >= 25:
                line += f" That's {round(compared[0])}% above the median."
        else:
            line = f"Number {words[rank]}: {job.company}, up to {job.pay_headline()}."
        lines.append(line)
        scenes.append(_job_scene(job, "countdown_item", rank=rank, n=n, max_pay=top.top_pay, top_pay_value=job.top_pay))
    lines.append(f"Every apply link is in my bio. {rng.choice(['Save this before they close.', 'Save this, then send it to a friend.'])}")
    scenes.append({"kind": "cta", "company": top.company, "url": top.url, "alt_url": top.alt_url})
    caption = _caption_for_jobs(
        list(reversed(picks)),
        f"{n} tech {level_word} still hiring, ranked by listed pay. #1: {top.company} at up to {top.pay_headline()}",
        "Which one are you applying to?",
    )
    return FormatScript("countdown", variant, lines, scenes, caption, HASHTAGS["job"][:4], list(reversed(picks)))


TIERS = [("S", 60, None), ("A", 50, 60), ("B", 40, 50), ("C", 0, 40)]


def pay_tiers(jobs: list[JobRecord], rng: random.Random) -> FormatScript | None:
    interns = [j for j in jobs if j.level == "intern" and j.pay and j.usd]
    best: dict[str, JobRecord] = {}
    for job in interns:
        if job.company not in best or job.top_pay > best[job.company].top_pay:
            best[job.company] = job
    if len(best) < 5:
        return None
    rows = []
    for name, low, high in TIERS:
        members = sorted(
            [j for j in best.values() if j.top_pay >= low and (high is None or j.top_pay < high)],
            key=lambda j: -j.top_pay,
        )
        if members:
            rows.append((name, low, high, members[:5]))
    if len(rows) < 2:
        return None
    lines = [rng.choice(["I ranked intern pay at every company hiring right now.", "Intern pay tier list, from companies hiring right now."])]
    scenes = [{"kind": "tier_board", "stage": 0, "rows": [_tier_row(r) for r in rows]}]
    for index, (name, low, high, members) in enumerate(rows, start=1):
        names = [m.company for m in members[:3]]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
        band = f"over ${low} an hour" if high is None else (f"under ${high} an hour" if low == 0 else f"${low} to ${high} an hour")
        lines.append(f"{name} tier, {band}: {listed}.")
        scenes.append({"kind": "tier_board", "stage": index, "rows": [_tier_row(r) for r in rows]})
    lines.append("Pay is the top of each posted range. Every link is in my bio.")
    scenes.append({"kind": "tier_board", "stage": len(rows), "rows": [_tier_row(r) for r in rows], "final": True})
    all_jobs = [m for _n, _l, _h, members in rows for m in members]
    caption = _caption_for_jobs(all_jobs[:10], "Intern pay tier list from companies hiring right now (top of each listed range)", "Agree with the ranking?")
    return FormatScript("pay_tiers", "weekly", lines, scenes, caption, HASHTAGS["job"][:4], all_jobs)


def _tier_row(row) -> dict:
    name, low, high, members = row
    def shown(job: JobRecord) -> str:
        # Monthly stipends are shown as their hourly equivalent so tiers compare like with like.
        return f"~${job.top_pay:.0f}/hr" if job.pay and job.pay.unit != "hour" else job.pay_headline()

    return {"tier": name, "members": [{"company": m.company, "pay": shown(m), "url": m.url} for m in members]}


def redline(index: int, rng: random.Random) -> FormatScript:
    item = REDLINES[index % len(REDLINES)]
    lines = [
        item["hook"],
        f"Most people write: {item['weak']}",
        f"Rewrite it like this: {item['strong']}",
        item["why"],
        f"Save this for your next resume pass. {rng.choice(CTA_SEND)}",
    ]
    base = {"weak": item["weak"], "strong": item["strong"], "why": item["why"]}
    scenes = [
        {"kind": "redline", "stage": "hook", **base},
        {"kind": "redline", "stage": "weak", **base},
        {"kind": "redline", "stage": "strong", **base},
        {"kind": "redline", "stage": "why", **base},
        {"kind": "redline", "stage": "cta", **base},
    ]
    caption = "\n".join(
        [
            f"Resume tip for CS students: {item['hook']}",
            "",
            f"❌ {item['weak']}",
            f"✅ {item['strong']}",
            "",
            item["why"],
            "",
            "What bullet should I fix next?",
        ]
    )
    return FormatScript("redline", str(index % len(REDLINES)), lines, scenes, caption, HASHTAGS["resume"][:4])


def chat(index: int, rng: random.Random) -> FormatScript:
    item = CHATS[index % len(CHATS)]
    bad_line = "Most people freeze." if item["bad"].strip(". ") == "" else f"Most people say: {item['bad']}"
    lines = [
        item["hook"],
        f"They ask: {item['question']}",
        bad_line,
        f"Instead, say: {item['good']}",
        item["why"],
        f"Save this before your next interview. {rng.choice(CTA_SEND)}",
    ]
    base = {"question": item["question"], "bad": item["bad"], "good": item["good"], "why": item["why"]}
    scenes = [{"kind": "chat", "stage": stage, **base} for stage in ("hook", "question", "bad", "good", "why", "cta")]
    caption = "\n".join(
        [
            f"Interview tip: {item['hook']}",
            "",
            f"Q: {item['question']}",
            f"❌ {item['bad'] if item['bad'].strip('. ') else '(silence)'}",
            f"✅ {item['good']}",
            "",
            item["why"],
            "",
            "Which interview question should I do next?",
        ]
    )
    return FormatScript("chat", str(index % len(CHATS)), lines, scenes, caption, HASHTAGS["interview"][:4])


def hack(index: int, rng: random.Random) -> FormatScript:
    item = HACKS[index % len(HACKS)]
    lines = [
        item["hook"],
        "Search the usual way first.",
        "Now add this to the end.",
        item["explain"],
        item["why"],
        f"Try it tonight. {rng.choice(CTA_SEND)}",
    ]
    base = {"site": item["site"], "before": item["before"], "after": item["after"]}
    scenes = [{"kind": "hack", "stage": stage, **base} for stage in ("hook", "before", "edit", "explain", "why", "cta")]
    caption = "\n".join(
        [
            f"Job search trick: {item['hook']}",
            "",
            f"Before: {item['before']}",
            f"After: {item['after']}",
            "",
            item["explain"],
            item["why"],
            "",
            "Got a search trick? Drop it below.",
        ]
    )
    return FormatScript("hack", str(index % len(HACKS)), lines, scenes, caption, HASHTAGS["search"][:4])
