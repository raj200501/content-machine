"""The "link in bio" page: every open role the account tracks, with pay and apply links.

Published to GitHub Pages by the workflow, so reels can say "the link is in my
bio" and actually deliver. Rebuilt on each run from the postings that are still
listed on their job boards.
"""

from __future__ import annotations

import html
from datetime import datetime

from app.insight.job_stats import JobRecord, market, records

LEVEL_LABEL = {"intern": "Internships", "new_grad": "New grad", "other": "Other early-career", "phd": "PhD"}


def _row(job: JobRecord) -> str:
    pay = html.escape(job.pay_headline() if job.pay else "")
    if job.pay and job.pay.high > job.pay.low:
        from app.source_ingest.pay import SYMBOLS

        symbol = SYMBOLS.get(job.pay.currency, "$")
        low = f"{symbol}{job.pay.low / 1000:.0f}K" if job.pay.unit == "year" else f"{symbol}{job.pay.low:,.0f}"
        pay = html.escape(f"{low}–{job.pay_headline()}")
    age = job.days_old
    fresh = "new" if age is not None and age <= 7 else ""
    return (
        f'<li class="{fresh}"><a href="{html.escape(job.url)}" rel="nofollow noopener" target="_blank">'
        f'<span class="co">{html.escape(job.company)}</span>'
        f'<span class="role">{html.escape(job.title)}</span>'
        f'<span class="meta">{html.escape(job.location)}{" · posted " + str(age) + "d ago" if age is not None else ""}</span>'
        f'<span class="pay">{pay or "pay not listed"}</span></a></li>'
    )


def build_jobs_page(source_items: list[dict], handle: str, now: datetime) -> str:
    jobs = [job for job in records(source_items) if job.level != "phd"]
    stats = market(jobs)
    sections = []
    for level in ("intern", "new_grad", "other"):
        group = [job for job in jobs if job.level == level]
        if not group:
            continue
        group.sort(key=lambda job: (-job.top_pay, job.days_old if job.days_old is not None else 999))
        sections.append(f"<h2>{LEVEL_LABEL[level]} <small>{len(group)} open</small></h2><ul>" + "".join(_row(j) for j in group) + "</ul>")
    medians = []
    if stats.intern_median:
        medians.append(f"Median intern pay we track: <b>${stats.intern_median:.0f}/hr</b> ({len(stats.intern_hourly)} roles)")
    if stats.new_grad_median:
        medians.append(f"Median new grad pay: <b>${stats.new_grad_median / 1000:.0f}K/yr</b> ({len(stats.new_grad_annual)} roles)")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(handle)}: open tech internships and new grad roles</title>
<meta name="description" content="Open software engineering internships and new grad roles with pay, updated daily.">
<style>
:root{{--bg:#0d0b1a;--card:#17142b;--ink:#f4f2ff;--mute:#a59fc9;--accent:#8b5cf6;--pay:#ffd84d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}}
main{{max-width:720px;margin:0 auto;padding:24px 16px 64px}}h1{{font-size:26px;margin:8px 0 4px}}
p.sub{{color:var(--mute);margin:0 0 12px}}.stats{{color:var(--mute);font-size:14px;margin-bottom:16px}}
h2{{font-size:18px;margin:28px 0 10px}}h2 small{{color:var(--mute);font-weight:500}}
ul{{list-style:none;margin:0;padding:0;display:grid;gap:8px}}
li a{{display:grid;grid-template-columns:1fr auto;gap:2px 12px;padding:12px 14px;background:var(--card);border-radius:12px;color:inherit;text-decoration:none}}
li a:hover{{outline:2px solid var(--accent)}}.co{{font-weight:700}}.role{{grid-column:1;color:var(--ink)}}
.meta{{grid-column:1;color:var(--mute);font-size:13px}}.pay{{grid-row:1/4;grid-column:2;align-self:center;font-weight:800;color:var(--pay);text-align:right;font-size:15px}}
li.new .co::after{{content:"NEW";margin-left:8px;font-size:11px;background:var(--accent);padding:2px 6px;border-radius:6px;vertical-align:middle}}
footer{{color:var(--mute);font-size:13px;margin-top:32px}}
</style></head><body><main>
<h1>Open tech roles for students</h1>
<p class="sub">From {html.escape(handle)}. Real postings from company job boards, sorted by pay. Updated {now:%b %d, %Y %I:%M %p} ET.</p>
<div class="stats">{" · ".join(medians)}</div>
{"".join(sections) or "<p>No open roles right now. Check back tomorrow.</p>"}
<footer>Pay is the range the company lists in the posting. Always confirm details on the posting before applying.</footer>
</main></body></html>
"""
