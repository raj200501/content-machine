"""Company logos for reels: the site's own icon via Google's favicon service.

Free, no key. Falls back to a lettered badge if nothing usable comes back.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw

LOG = logging.getLogger(__name__)

DOMAINS = {
    "stripe": "stripe.com", "databricks": "databricks.com", "robinhood": "robinhood.com", "figma": "figma.com",
    "coinbase": "coinbase.com", "pinterest": "pinterest.com", "lyft": "lyft.com", "roblox": "roblox.com",
    "scale ai": "scale.com", "scaleai": "scale.com", "verkada": "verkada.com", "affirm": "affirm.com",
    "mongodb": "mongodb.com", "samsara": "samsara.com", "duolingo": "duolingo.com", "datadog": "datadoghq.com",
    "cloudflare": "cloudflare.com", "palantir": "palantir.com", "spotify": "spotify.com", "zoox": "zoox.com",
    "openai": "openai.com", "anthropic": "anthropic.com", "ramp": "ramp.com", "notion": "notion.so",
    "airbnb": "airbnb.com", "dropbox": "dropbox.com", "reddit": "reddit.com", "discord": "discord.com",
    "instacart": "instacart.com", "plaid": "plaid.com", "brex": "brex.com", "doordash": "doordash.com",
    "anduril": "anduril.com", "nuro": "nuro.ai", "waymo": "waymo.com", "asana": "asana.com", "gusto": "gusto.com",
    "twilio": "twilio.com", "okta": "okta.com", "gitlab": "gitlab.com", "elastic": "elastic.co",
    "linear": "linear.app", "replit": "replit.com", "vercel": "vercel.com", "retool": "retool.com",
}
JOB_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "smartrecruiters.com")


def domain_for(company: str, url: str = "") -> str:
    key = company.strip().lower()
    if key in DOMAINS:
        return DOMAINS[key]
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host and not any(host.endswith(job_host) for job_host in JOB_HOSTS):
        parts = host.split(".")
        return ".".join(parts[-2:])
    slug = re.sub(r"[^a-z0-9]", "", key)
    return f"{slug}.com" if slug else ""


def _badge(company: str, size: int) -> Image.Image:
    from app.media.reel_renderer import font

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=(139, 92, 246))
    letter = (company.strip()[:1] or "?").upper()
    face = font(int(size * 0.55), 900)
    box = draw.textbbox((0, 0), letter, font=face)
    draw.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), letter, font=face, fill=(255, 255, 255))
    return image


@lru_cache(maxsize=128)
def _fetch(domain: str, cache_dir: str) -> bytes | None:
    if not domain:
        return None
    path = Path(cache_dir) / f"{domain}.png"
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    try:
        response = requests.get(
            "https://www.google.com/s2/favicons", params={"domain": domain, "sz": 256}, timeout=10
        )
        if response.status_code != 200 or not response.content:
            return None
        image = Image.open(BytesIO(response.content))
        if image.size[0] < 64:  # the service's generic globe is tiny; use the badge instead
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return response.content
    except Exception as exc:  # offline, blocked, bad image
        LOG.info("Logo fetch failed for %s: %s", domain, str(exc)[:120])
        return None


def logo(company: str, url: str, size: int, cache_dir: Path) -> Image.Image:
    """Square RGBA logo on a white rounded tile (or a lettered badge)."""

    data = _fetch(domain_for(company, url), str(cache_dir))
    if not data:
        return _badge(company, size)
    icon = Image.open(BytesIO(data)).convert("RGBA")
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=(255, 255, 255))
    inner = int(size * 0.72)
    icon = icon.resize((inner, inner), Image.LANCZOS)
    tile.alpha_composite(icon, ((size - inner) // 2, (size - inner) // 2))
    return tile
