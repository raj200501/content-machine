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
TOP_CSS = 1800  # css px of the page top kept when the pay is further down
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

FIND_JS = r"""
(needles) => {
  const out = {height: Math.min(document.documentElement.scrollHeight, 20000), title: null, pay: null};
  const rect = (el) => { const r = el.getBoundingClientRect(); return [r.x, r.y + window.scrollY, r.width, r.height]; };
  const heading = document.querySelector('h1') || document.querySelector('.posting-headline h2') || document.querySelector('h2');
  if (heading) out.title = rect(heading);
  if (!needles.length) return out;
  // Flatten visible text so a pay range split across tags ("$120,000" "-" "$140,000 USD")
  // is matched as one span of text.
  const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement && !skip.has(n.parentElement.tagName) && n.parentElement.getClientRects().length
      ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
  });
  const nodes = [];
  let flat = '';
  let node;
  while ((node = walker.nextNode())) {
    nodes.push([node, flat.length]);
    flat += node.textContent || '';
  }
  const payRe = /[$£€]\s?\d[\d,.]*\s*[kK]?(?:\s*(?:-|–|—|to)\s*[$£€]?\s?\d[\d,.]*\s*[kK]?)?(?:\s*(?:USD|CAD|GBP|EUR))?(?:\s*(?:per hour|per year|per month|\/hr|\/hour|\/yr|\/year|hourly|annually))?/y;
  for (const needle of needles) {
    let at = flat.indexOf(needle);
    while (at >= 0) {
      let start = at;
      const dollar = flat.lastIndexOf('$', start + 1);
      if (dollar >= 0 && start - dollar <= 2) start = dollar;
      payRe.lastIndex = start;
      const m = payRe.exec(flat);
      const end = start + (m ? m[0].replace(/\s+$/, '').length : needle.length);
      const rects = [];
      for (const [textNode, offset] of nodes) {
        const length = (textNode.textContent || '').length;
        const a = Math.max(start, offset), b = Math.min(end, offset + length);
        if (a >= b) continue;
        const range = document.createRange();
        range.setStart(textNode, a - offset);
        range.setEnd(textNode, b - offset);
        for (const q of range.getClientRects()) if (q.width > 1 && q.height > 1) rects.push(q);
      }
      if (rects.length) {
        out.pay_rects = rects.map((q) => [q.x, q.y + window.scrollY, q.width, q.height]);
        const left = Math.min(...rects.map((q) => q.left));
        const top = Math.min(...rects.map((q) => q.top));
        const right = Math.max(...rects.map((q) => q.right));
        const bottom = Math.max(...rects.map((q) => q.bottom));
        out.pay = [left, top + window.scrollY, right - left, bottom - top];
        return out;
      }
      at = flat.indexOf(needle, at + 1);
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


def _find_pay_in_frames(page, needles: list[str], found: dict) -> None:
    """Many careers sites embed the Greenhouse posting in an iframe; look for the pay there."""

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            sub = frame.evaluate(FIND_JS, needles)
            if not sub.get("pay"):
                continue
            box = frame.frame_element().bounding_box()
            if not box:
                continue
            scroll_y = page.evaluate("window.scrollY")
            dx, dy = box["x"], box["y"] + scroll_y
            move = lambda r: [r[0] + dx, r[1] + dy, r[2], r[3]]  # noqa: E731
            found["pay"] = move(sub["pay"])
            found["pay_rects"] = [move(r) for r in sub.get("pay_rects") or []]
            return
        except Exception as exc:  # detached or blocked frame
            LOG.debug("Frame search failed: %s", str(exc)[:120])


def _stitch(parts: list[Path], out: Path) -> None:
    from PIL import Image

    images = [Image.open(part).convert("RGB") for part in parts]
    canvas = Image.new("RGB", (max(i.size[0] for i in images), sum(i.size[1] for i in images)), (255, 255, 255))
    y = 0
    for image in images:
        canvas.paste(image, (0, y))
        y += image.size[1]
    canvas.save(out)


def merge_line_rects(rects: list) -> list[tuple[float, float, float, float]]:
    """Join boxes that sit on the same text line (one per tag) into one box per line."""

    lines: list[list[float]] = []
    for x, y, w, h in sorted((tuple(r) for r in rects), key=lambda r: (round(r[1]), r[0])):
        for line in lines:
            if abs(line[1] - y) < 4 and abs(line[3] - h) < 6:
                right = max(line[0] + line[2], x + w)
                line[0] = min(line[0], x)
                line[2] = right - line[0]
                break
        else:
            lines.append([x, y, w, h])
    return [tuple(line) for line in lines]


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
        needles = pay_needles(job.get("pay", ""))
        found = page.evaluate(FIND_JS, needles)
        if needles and not found.get("pay"):
            _find_pay_in_frames(page, needles, found)
        title = found.get("title")
        text = page.inner_text("body")[:4000].lower()
        flags = ("verify you are human", "access denied", "page not found", "no longer accepting")
        if not title or any(flag in text for flag in flags):
            # Not a usable job page (error page, bot wall, closed role): the reel uses a card.
            reason = "no title" if not title else next(flag for flag in flags if flag in text)
            path.with_suffix(".json").write_text(json.dumps({"url": job.get("url"), "skipped": reason}))
            LOG.info("Skipping capture of %s: %s", job.get("url"), reason)
            return None
        page_height = int(found.get("height") or 2000)
        pay = found.get("pay")
        rects = merge_line_rects(found.get("pay_rects") or []) if pay else []
        shift = 0.0
        if pay and pay[1] > TOP_CSS + 600:
            # Pay sits deep in the posting: keep the top of the page, then jump to a
            # window around the pay (reads like a fast scroll) instead of a 15k px image.
            start = max(int(pay[1]) - 1100, TOP_CSS)
            end = min(start + 2200, page_height)
            top_shot = path.with_name(path.stem + "_top.png")
            low_shot = path.with_name(path.stem + "_pay.png")
            page.screenshot(path=str(top_shot), clip={"x": 0, "y": 0, "width": CSS_WIDTH, "height": TOP_CSS}, full_page=True)
            page.screenshot(path=str(low_shot), clip={"x": 0, "y": start, "width": CSS_WIDTH, "height": end - start}, full_page=True)
            _stitch([top_shot, low_shot], path)
            css_height = TOP_CSS + (end - start)
            shift = start - TOP_CSS
        else:
            css_height = min(page_height, MAX_CSS_HEIGHT)
            if pay and pay[1] > MAX_CSS_HEIGHT - 400:
                pay, rects = None, []
            page.screenshot(path=str(path), clip={"x": 0, "y": 0, "width": CSS_WIDTH, "height": css_height}, full_page=True)
        moved = lambda box: (box[0], box[1] - shift, box[2], box[3]) if box else None  # noqa: E731
        scale = lambda box: tuple(float(v) * SCALE for v in box) if box else None  # noqa: E731
        pay_rects = [scale(moved(box)) for box in rects] if pay else None
        capture = PageCapture(path, int(css_height * SCALE), scale(title), scale(moved(pay)), pay_rects)
        path.with_suffix(".json").write_text(
            json.dumps({"url": job.get("url"), "title": capture.title, "pay": capture.pay, "pay_rects": pay_rects, "height": capture.height})
        )
        return capture
    finally:
        page.close()
