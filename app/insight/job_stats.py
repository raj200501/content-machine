"""Turn ingested postings into clean records and market numbers.

This is the account's original analysis: every pay comparison in a reel
("about 30% above the median intern rate we track") is computed here from the
postings the bot has collected, never estimated.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime

from app.source_ingest.pay import SYMBOLS, PayRange
from app.utils import json_loads

SINGLE = re.compile(r"^(US\$|CA\$|\$|£|€)\s?([\d,.]+)\s*([kK])?\s*/\s*(hr|mo|yr)$")
RANGE = re.compile(r"^(US\$|CA\$|\$|£|€)\s?([\d,.]+)\s*([kK])?\s*[–-]\s*(?:US\$|CA\$|\$|£|€)?\s?([\d,.]+)\s*([kK])?\s*/\s*(hr|mo|yr)$")
UNITS = {"hr": "hour", "mo": "month", "yr": "year"}
CURRENCY = {"$": "USD", "US$": "USD", "CA$": "CAD", "£": "GBP", "€": "EUR"}


def from_display(display: str) -> PayRange | None:
    """Parse the stored display form ("$47–$58/hr", "$120K–$140K/yr", "$61.90/hr")."""

    text = (display or "").strip()
    match = RANGE.match(text)
    if match:
        cur, low, k1, high, k2, unit = match.groups()
        low_v = float(low.replace(",", "")) * (1000 if k1 else 1)
        high_v = float(high.replace(",", "")) * (1000 if (k2 or k1) else 1)
        return PayRange(low_v, high_v, UNITS[unit], CURRENCY.get(cur, "USD"))
    match = SINGLE.match(text)
    if match:
        cur, value, kilo, unit = match.groups()
        amount = float(value.replace(",", "")) * (1000 if kilo else 1)
        return PayRange(amount, amount, UNITS[unit], CURRENCY.get(cur, "USD"))
    return None


def level_of(title: str) -> str:
    lowered = title.lower()
    if re.search(r"\bph\.?d\b", lowered):
        return "phd"
    if re.search(r"intern|co-?op|apprentice", lowered):
        return "intern"
    if re.search(r"new grad|university grad|graduate|early career|entry|junior|associate|engineer i\b|level 1|\bl1\b|2026|2027", lowered):
        return "new_grad"
    return "other"


def hourly(pay: PayRange) -> float:
    mid = (pay.low + pay.high) / 2
    return {"hour": mid, "month": mid * 12 / 2080, "year": mid / 2080}[pay.unit]


def annual(pay: PayRange) -> float:
    mid = (pay.low + pay.high) / 2
    return {"hour": mid * 2080, "month": mid * 12, "year": mid}[pay.unit]


@dataclass
class JobRecord:
    item_id: int
    company: str
    title: str
    level: str
    location: str
    url: str
    alt_url: str
    pay: PayRange | None
    posted: date | None
    metadata: dict = field(default_factory=dict)

    @property
    def top_pay(self) -> float:
        """Upper end, in the unit that matters for the level (hourly for interns)."""

        if not self.pay:
            return 0.0
        top = PayRange(self.pay.high, self.pay.high, self.pay.unit, self.pay.currency)
        return hourly(top) if self.level == "intern" else annual(top)

    @property
    def usd(self) -> bool:
        return bool(self.pay) and self.pay.currency == "USD"

    @property
    def days_old(self) -> int | None:
        return (date.today() - self.posted).days if self.posted else None

    def pay_headline(self) -> str:
        """Big-number form for the screen: "$58/hr" or "$140K/yr" (top of the range)."""

        if not self.pay:
            return ""
        symbol = SYMBOLS.get(self.pay.currency, "$")
        if self.pay.unit == "year":
            return f"{symbol}{self.pay.high / 1000:.0f}K/yr"
        if self.pay.unit == "month":
            return f"{symbol}{self.pay.high:,.0f}/mo"
        value = self.pay.high
        return f"{symbol}{value:.0f}/hr" if value == int(value) else f"{symbol}{value:.2f}/hr"


def records(source_items: list[dict]) -> list[JobRecord]:
    out = []
    for item in source_items:
        if item.get("source_type") != "job_board":
            continue
        meta = json_loads(item.get("metadata_json"), default={}) or {}
        posted = None
        raw = item.get("published_at") or ""
        try:
            posted = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date() if raw else None
        except ValueError:
            posted = None
        title = str(meta.get("job_title") or item.get("title") or "")
        out.append(
            JobRecord(
                item_id=int(item.get("id") or 0),
                company=str(meta.get("company") or ""),
                title=title,
                level=level_of(title),
                location=str(meta.get("location") or ""),
                url=str(item.get("source_url") or ""),
                alt_url=str(meta.get("hosted_url") or ""),
                pay=from_display(str(meta.get("pay") or "")),
                posted=posted,
                metadata=meta,
            )
        )
    return out


@dataclass
class Market:
    intern_hourly: list[float]
    new_grad_annual: list[float]

    @property
    def intern_median(self) -> float | None:
        return statistics.median(self.intern_hourly) if len(self.intern_hourly) >= 8 else None

    @property
    def new_grad_median(self) -> float | None:
        return statistics.median(self.new_grad_annual) if len(self.new_grad_annual) >= 8 else None

    def compare(self, record: JobRecord) -> tuple[float, int] | None:
        """(percent above/below the median, how many roles that median is from) or None."""

        if not record.pay or not record.usd:
            return None
        if record.level == "intern" and self.intern_median:
            mid = hourly(record.pay)
            return (mid / self.intern_median - 1) * 100, len(self.intern_hourly)
        if record.level == "new_grad" and self.new_grad_median:
            mid = annual(record.pay)
            return (mid / self.new_grad_median - 1) * 100, len(self.new_grad_annual)
        return None


def market(all_records: list[JobRecord]) -> Market:
    intern = [hourly(r.pay) for r in all_records if r.pay and r.usd and r.level == "intern" and r.pay.unit != "year"]
    grad = [annual(r.pay) for r in all_records if r.pay and r.usd and r.level == "new_grad"]
    return Market(intern, grad)
