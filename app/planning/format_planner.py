"""Turn the day's category slots into concrete reel formats with real material.

- Job slots: the first is a single-role alert (best-paying open role not shown in
  two weeks), the second a countdown of the top-paying open roles; on Saturdays
  the second is the intern pay tier list.
- Tip slots: resume -> redline, interview -> chat, application strategy ->
  search hack (falls back to chat/redline when every hack ran recently).
- Library items rotate least-recently-used, never within 3 weeks if avoidable.
- Format weights from insights tilt which tip formats appear.
"""

from __future__ import annotations

import random
from datetime import date

from app.insight.job_stats import JobRecord, Market, market, records
from app.models import CaptionPackage, PlannedTopic, ScriptPackage
from app.writing import formats
from app.writing.formats import FormatScript
from app.writing.libraries import CHATS, HACKS, REDLINES

TIP_FORMAT = {
    "resume_portfolio": "redline",
    "interview_prep": "chat",
    "application_strategy": "hack",
    "motivational_community": "chat",
}
LIBRARY_SIZE = {"redline": len(REDLINES), "chat": len(CHATS), "hack": len(HACKS)}


def _recent_uses(recent_hook_ids: list[str], fmt: str) -> dict[int, int]:
    """item index -> how many scripts ago it was last used (0 = most recent)."""

    uses: dict[int, int] = {}
    for age, hook_id in enumerate(recent_hook_ids):
        parts = (hook_id or "").split(":")
        if len(parts) == 3 and parts[0] == "fmt" and parts[1] == fmt and parts[2].isdigit():
            uses.setdefault(int(parts[2]), age)
    return uses


def pick_item(fmt: str, recent_hook_ids: list[str], rng: random.Random, performance: dict[str, float] | None = None) -> tuple[int, bool]:
    """(index, fresh) for a library format. fresh=False means everything ran recently.

    Among items not used recently, ones that earned more saves/shares/watch time
    on earlier runs are more likely to come back."""

    size = LIBRARY_SIZE[fmt]
    uses = _recent_uses(recent_hook_ids, fmt)
    unused = [index for index in range(size) if index not in uses]
    if unused:
        weights = [(performance or {}).get(f"fmt:{fmt}:{index}", 1.0) for index in unused]
        return rng.choices(unused, weights=weights, k=1)[0], True
    oldest = max(uses.items(), key=lambda item: item[1])[0]
    return oldest, uses[oldest] > 60  # 60 scripts ago is about 12 days at 5/day


class DayPlanner:
    def __init__(
        self,
        open_items: list[dict],
        recent_hook_ids: list[str],
        run_date: date,
        all_items: list[dict] | None = None,
        performance: dict[str, float] | None = None,
    ):
        self.performance = performance or {}
        self.jobs: list[JobRecord] = [job for job in records(open_items) if job.level in {"intern", "new_grad"}]
        # Market numbers come from every posting we have seen in 30 days, not just unused ones.
        self.market: Market = market([job for job in records(all_items or open_items) if job.level in {"intern", "new_grad"}])
        self.used_urls: set[str] = set()
        self.recent_hook_ids = list(recent_hook_ids)
        self.run_date = run_date
        self.rng = random.Random(run_date.toordinal())
        self.job_slot = 0

    def _available(self) -> list[JobRecord]:
        return [job for job in self.jobs if job.url not in self.used_urls]

    def _claim(self, script: FormatScript) -> FormatScript:
        self.used_urls.update(job.url for job in script.jobs)
        self.recent_hook_ids.insert(0, script.hook_id)
        return script

    def job_format(self) -> FormatScript | None:
        available = self._available()
        slot, self.job_slot = self.job_slot, self.job_slot + 1
        paid = [job for job in available if formats.rankable(job)]
        if slot % 2 == 1:
            if self.run_date.weekday() == 5:
                tiers = formats.pay_tiers(available, self.rng)
                if tiers:
                    return self._claim(tiers)
            counted = formats.countdown(available, self.market, self.rng)
            if counted:
                return self._claim(counted)
        if paid:
            # Freshest high-paying role first: score pay rank and freshness together.
            def score(job: JobRecord) -> float:
                age = job.days_old if job.days_old is not None else 30
                return job.top_pay / (max(self.market.intern_median or 40, 1) if job.level == "intern" else max(self.market.new_grad_median or 120000, 1)) - age / 30

            best = max(paid, key=score)
            return self._claim(formats.job_alert(best, self.market, self.rng))
        return None

    def tip_format(self, category: str) -> FormatScript | None:
        fmt = TIP_FORMAT.get(category)
        if category == "market_context":
            tiers = formats.pay_tiers(self._available(), self.rng)
            if tiers:
                return self._claim(tiers)
            fmt = "chat"
        if not fmt:
            return None
        index, fresh = pick_item(fmt, self.recent_hook_ids, self.rng, self.performance)
        if not fresh:
            for alternative in ("chat", "redline", "hack"):
                alt_index, alt_fresh = pick_item(alternative, self.recent_hook_ids, self.rng, self.performance)
                if alt_fresh:
                    fmt, index = alternative, alt_index
                    break
        builder = {"redline": formats.redline, "chat": formats.chat, "hack": formats.hack}[fmt]
        return self._claim(builder(index, self.rng))

    def build(self, topic: PlannedTopic) -> FormatScript | None:
        if topic.category == "openings_job_alert":
            return self.job_format()
        return self.tip_format(topic.category)


def to_package(topic: PlannedTopic, script: FormatScript, evidence_items: list[dict]) -> ScriptPackage:
    caption = CaptionPackage(
        caption=script.caption,
        hashtags=script.hashtags[:5],
        cta=script.lines[-1],
        source_notes="\n".join(f"- {job.company} {job.title} :: {job.url}" for job in script.jobs),
        compliance_notes="Pay figures are the ranges listed on each posting; market comparisons are computed from postings the bot tracks.",
    )
    evidence = [
        {"title": job.title, "source_url": job.url, "summary": job.metadata.get("pay", ""), "company": job.company}
        for job in script.jobs
    ] or [
        {"title": item.get("title", ""), "source_url": item.get("source_url", ""), "summary": item.get("summary", ""), "company": ""}
        for item in evidence_items
    ]
    return ScriptPackage(
        topic=topic,
        hook=script.hook,
        beats=script.lines[1:-1],
        cta=script.lines[-1],
        full_script="\n".join(script.lines),
        caption=caption,
        evidence=evidence,
        metadata={
            "format": script.format,
            "scenes": script.scenes,
            "hook_id": script.hook_id,
            "word_count": len(" ".join(script.lines).split()),
            "source_item_ids": [job.item_id for job in script.jobs],
        },
    )
