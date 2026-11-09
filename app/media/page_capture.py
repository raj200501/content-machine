"""Capture the real job posting page so job reels show the actual listing.

A headless browser opens each posting at phone width, hides cookie banners,
finds where the title and the pay line sit on the page, and saves a tall
screenshot. The renderer then scrolls and zooms through it like a screen
recording and highlights the pay as the voice says it.

Anything that goes wrong returns None and the reel falls back to the card.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger(__name__)

CSS_WIDTH = 432
SCALE = 2.5  # 432 css px * 2.5 = 1080 px, the reel width
MAX_CSS_HEIGHT = 6000
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
HIDE_OVERLAYS = """
#onetrust-banner-sdk, #onetrust-consent-sdk, .onetrust-pc-dark-filter, #truste-consent-track,
#CybotCookiebotDialog, [id*="cookie-banner"], [class*="cookie-banner"], [class*="CookieBanner"],
[id*="cookie-consent"], [class*="cookie-consent"], [aria-label*="cookie" i], .osano-cm-window,
#hs-eu-cookie-confirmation, [class*="consent-banner"] { display: none !important; }
html, body { overflow: visible !important; }
"""

FIND_JS = """
(needles) => {
  const out = {height: Math.min(document.documentElement.scrollHeight, 20000), title: null, pay: null};
  const rect = (el) => { const r = el.getBoundingClientRect(); return [r.x, r.y + window.scrollY, r.width, r.height]; };
  const heading = document.querySelector('h1') || document.querySelector('.posting-headline h2') || document.querySelector('h2');
  if (heading) out.title = rect(heading);
  if (needles.length) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const payRe = /[$£€]\s?\d[\d,.]*\s*[kK]?(?:\s*(?:-|–|—|to)\s*[$£€]?\s?\d[\d,.]*\s*[kK]?)?(?:\s*(?:USD|CAD|GBP|EUR))?(?:\s*(?:per hour|per year|per month|\/hr|\/hour|\/yr|\/year|hourly|annually))?/;
    let node;
    while ((node = walker.nextNode())) {
      const text = node.textContent || '';
      const hit = needles.find((n) => text.includes(n));
      if (!hit) continue;
      // Highlight just the pay amount, not the whole paragraph.
      let start = text.indexOf(hit);
      const dollar = text.lastIndexOf('$', start + 1);
      if (dollar >= 0 && start - dollar <= 2) start = dollar;
      const m = payRe.exec(text.slice(start));
      const end = start + (m ? m[0].length : hit.length);
      const range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, Math.min(end, text.length));
      const rects = Array.from(range.getClientRects()).filter((r) => r.width > 0);
      if (rects.length) {
        out.pay_rects = rects.map((q) => [q.x, q.y + window.scrollY, q.width, q.height]);
        const left = Math.min(...rects.map((q) => q.left));
        const top = Math.min(...rects.map((q) => q.top));
        const right = Math.max(...rects.map((q) => q.right));
        const bottom = Math.max(...rects.map((q) => q.bottom));
        out.pay = [left, top + window.scrollY, right - left, bottom - top];
        break;
      }
    }
  }
  return out;
}
"""


@dataclass(slots=True)
class PageCapture:
    image_path: Path
    height: int  # image px
    title: tuple[float, float, float, float] | None  # x, y, w, h in image px
    pay: tuple[float, float, float, float] | None  # union of the pay text
    pay_rects: list[tuple[float, float, float, float]] | None = None  # one box per line


def pay_needles(pay: str) -> list[str]:
    """'$120K–$140K/yr' -> ['$120,000', '$120K', '$120k', '120,000', ...] to locate the pay text."""

    needles: list[str] = []
    for raw, kilo in re.findall(r"[$£€]?(\d[\d,]*(?:\.\d+)?)([Kk])?", pay or "")[:1]:
        number = float(raw.replace(",", "")) * (1000 if kilo else 1)
        whole = int(round(number))
        variants = {f"{whole:,}", f"{number:,.2f}", str(whole)}
        if kilo or whole >= 1000:
            variants |= {f"{whole // 1000}K", f"{whole // 1000}k"}
        for value in variants:
            needles += [f"${value}", f"$ {value}", f"£{value}", f"€{value}"]
        needles += [f"{whole:,}"]
    return [needle for needle in needles if len(needle) >= 3]


def capture_pages(jobs: list[dict], out_dir: Path, timeout_ms: int = 30000) -> dict[int, PageCapture]:
    """Capture each job's posting page. Keys are indexes into ``jobs``."""

    targets = [(i, job) for i, job in enumerate(jobs) if str(job.get("url", "")).startswith("http")]
    if not targets:
        return {}
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - optional dependency
        LOG.warning("Playwright not installed; job reels use cards (%s)", exc)
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, PageCapture] = {}
    launch: dict = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    if os.environ.get("CHROME_PATH"):
        launch["executable_path"] = os.environ["CHROME_PATH"]
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context(
                viewport={"width": CSS_WIDTH, "height": 860},
                device_scale_factor=SCALE,
                user_agent=MOBILE_UA,
                locale="en-US",
                is_mobile=True,
                has_touch=True,
            )
            for index, job in targets:
                try:
                    results[index] = _capture_one(context, job, out_dir / f"page_{index}.png", timeout_ms)
                except Exception as exc:
                    LOG.warning("Could not capture %s: %s", job.get("url"), str(exc)[:200])
            browser.close()
    except Exception as exc:
        LOG.warning("Browser capture unavailable: %s", str(exc)[:200])
    return {key: value for key, value in results.items() if value is not None}


def _capture_one(context, job: dict, path: Path, timeout_ms: int) -> PageCapture | None:
    page = context.new_page()
    try:
        page.goto(job["url"], wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.add_style_tag(content=HIDE_OVERLAYS)
        page.wait_for_timeout(600)
        found = page.evaluate(FIND_JS, pay_needles(job.get("pay", "")))
        title = found.get("title")
        if not title:
            return None  # not a job page (error page, bot wall, redirect)
        text = page.inner_text("body")[:4000].lower()
        if any(flag in text for flag in ("verify you are human", "access denied", "page not found", "no longer accepting")):
            return None
        css_height = min(int(found.get("height") or 2000), MAX_CSS_HEIGHT)
        pay = found.get("pay")
        if pay and pay[1] > MAX_CSS_HEIGHT - 400:
            pay = None
        page.screenshot(path=str(path), clip={"x": 0, "y": 0, "width": CSS_WIDTH, "height": css_height}, full_page=True)
        scale = lambda box: tuple(float(v) * SCALE for v in box) if box else None  # noqa: E731
        pay_rects = [scale(box) for box in (found.get("pay_rects") or [])] if pay else None
        capture = PageCapture(path, int(css_height * SCALE), scale(title), scale(pay), pay_rects)
        path.with_suffix(".json").write_text(
            json.dumps({"title": capture.title, "pay": capture.pay, "pay_rects": pay_rects, "height": capture.height})
        )
        return capture
    finally:
        page.close()
