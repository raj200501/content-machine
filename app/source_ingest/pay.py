"""Extract a posted pay range from a job listing.

Pay is one of the most saved and shared details in job content, and many US
postings now include it for pay-transparency laws. Only ranges actually present
in the posting are used; nothing is estimated.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

SYMBOLS = {"USD": "$", "CAD": "CA$", "GBP": "£", "EUR": "€", "AUD": "A$"}

AMOUNT = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d{1,2})?)\s*([kK])?"
RANGE_PATTERN = re.compile(
    r"(?P<cur>US\$|CA\$|\$|£|€)\s?" + AMOUNT + r"\s*(?:USD|CAD)?\s*(?:-|–|—|to)\s*(?:US\$|CA\$|\$|£|€)?\s?" + AMOUNT,
)
UNIT_PATTERNS = [
    ("hour", re.compile(r"\b(hour|hourly|hr|/h)\b", re.I)),
    ("month", re.compile(r"\b(month|monthly|mo)\b", re.I)),
    ("year", re.compile(r"\b(year|yearly|annual|annually|salary|yr)\b", re.I)),
]


@dataclass(slots=True)
class PayRange:
    low: float
    high: float
    unit: str  # hour | month | year
    currency: str = "USD"

    @property
    def display(self) -> str:
        symbol = SYMBOLS.get(self.currency, self.currency + " ")
        suffix = {"hour": "/hr", "month": "/mo", "year": "/yr"}[self.unit]
        return f"{_short(self.low, self.unit, symbol)}–{_short(self.high, self.unit, symbol)}{suffix}" if self.high > self.low else f"{_short(self.low, self.unit, symbol)}{suffix}"

    @property
    def spoken(self) -> str:
        unit_word = {"hour": "an hour", "month": "a month", "year": "a year"}[self.unit]
        currency_word = {"USD": "dollars", "CAD": "Canadian dollars", "GBP": "pounds", "EUR": "euros", "AUD": "Australian dollars"}.get(self.currency, self.currency)
        if self.unit == "year" and self.low >= 1000:
            low, high = round(self.low / 1000), round(self.high / 1000)
            amount = f"{low} to {high} thousand" if high > low else f"{low} thousand"
        else:
            low, high = _plain(self.low), _plain(self.high)
            amount = f"{low} to {high}" if self.high > self.low else low
        return f"{amount} {currency_word} {unit_word}"


def _plain(value: float) -> str:
    return f"{int(round(value)):,}" if value >= 100 or value == int(value) else f"{value:.2f}"


def _short(value: float, unit: str, symbol: str) -> str:
    if unit == "year" and value >= 1000:
        return f"{symbol}{value / 1000:.0f}K"
    if value == int(value):
        return f"{symbol}{int(value):,}"
    return f"{symbol}{value:.2f}"


def _unit_words(context: str) -> str | None:
    for unit, pattern in UNIT_PATTERNS:
        if pattern.search(context):
            return unit
    return None


def _unit_for(high: float, context: str) -> str | None:
    unit = _unit_words(context)
    if unit:
        return unit
    # Fall back to magnitude, which is unambiguous for intern and new-grad pay.
    if 10 <= high <= 300:
        return "hour"
    if 1500 <= high <= 25000:
        return "month"
    if 30000 <= high <= 900000:
        return "year"
    return None


def _plausible(pay: PayRange) -> bool:
    limits = {"hour": (8, 400), "month": (800, 40000), "year": (15000, 900000)}[pay.unit]
    return limits[0] <= pay.low <= pay.high <= limits[1] and pay.high <= pay.low * 3.5


def _number(raw: str, kilo: str | None) -> float:
    value = float(raw.replace(",", ""))
    return value * 1000 if kilo else value


def from_text(text: str) -> PayRange | None:
    if not text:
        return None
    plain = BeautifulSoup(html.unescape(text), "html.parser").get_text(" ")
    plain = re.sub(r"\s+", " ", plain)
    for match in RANGE_PATTERN.finditer(plain):
        low = _number(match.group(2), match.group(3))
        high = _number(match.group(4), match.group(5) or match.group(3))
        if high < low:
            low, high = high, low
        context = plain[max(match.start() - 80, 0) : match.end() + 80]
        unit = _unit_words(plain[match.end() : match.end() + 50]) or _unit_for(high, context)
        if not unit:
            continue
        currency = {"£": "GBP", "€": "EUR", "CA$": "CAD"}.get(match.group("cur"), "USD")
        pay = PayRange(low, high, unit, currency)
        if _plausible(pay):
            return pay
    return None


def from_greenhouse(job: dict) -> PayRange | None:
    for item in job.get("pay_input_ranges") or []:
        try:
            low = float(item.get("min_cents") or 0) / 100
            high = float(item.get("max_cents") or 0) / 100
        except (TypeError, ValueError):
            continue
        if high <= 0:
            continue
        label = f"{item.get('title', '')} {BeautifulSoup(html.unescape(item.get('blurb') or ''), 'html.parser').get_text(' ')}"
        unit = _unit_for(high, label)
        if not unit:
            continue
        pay = PayRange(min(low or high, high), high, unit, str(item.get("currency_type") or "USD").upper())
        if _plausible(pay):
            return pay
    return from_text(job.get("content") or "")


LEVER_INTERVALS = {"per-hour-wage": "hour", "per-month-salary": "month", "per-year-salary": "year"}


def from_lever(job: dict) -> PayRange | None:
    salary = job.get("salaryRange") or {}
    unit = LEVER_INTERVALS.get(str(salary.get("interval", "")))
    try:
        low, high = float(salary.get("min") or 0), float(salary.get("max") or 0)
    except (TypeError, ValueError):
        low = high = 0
    if unit and high > 0:
        pay = PayRange(min(low or high, high), high, unit, str(salary.get("currency") or "USD").upper())
        if _plausible(pay):
            return pay
    text = " ".join(str(job.get(key) or "") for key in ("salaryDescriptionPlain", "additionalPlain", "descriptionPlain"))
    return from_text(text)
