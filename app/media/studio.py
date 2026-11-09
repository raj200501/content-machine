"""Studio renderer: the reel formats in app/writing/formats.py, drawn as motion graphics.

What changed from the slideshow look, and why (research, Nov 2026):
- Frame one shows the payoff (the pay, the bad bullet, the question), and the
  voice starts at 0s. Skip rate is decided in the first 3 seconds.
- Every scene moves: pops, bars that grow, typing, a camera that scrolls the
  real posting to its pay. No scene is a still card with text on it.
- Big word-synced captions in the band above Instagram's own caption area.
- Visuals that are not "majority text": logos, numbers, bars, tier boards, a
  resume being redlined, a chat, a link being edited.
"""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from app.config import Settings
from app.media.voice import TimedLine, TimedWord, synthesize_timed_lines
from app.models import RenderArtifact
from app.utils import ensure_directory, hash_text, slugify

LOG = logging.getLogger(__name__)

W, H = 1080, 1920
CX = 520  # visual center, nudged left of Instagram's right-side buttons
MARGIN = 72
YELLOW = (255, 216, 77)
WHITE = (255, 255, 255)
MUTED = (178, 172, 208)
ACCENT = (139, 92, 246)
RED = (239, 68, 68)
GREEN = (34, 197, 94)
INK = (20, 18, 32)
CAPTION_Y = 1370
TRANSITION = 0.16


# ------------------------------------------------------------------ text --


def font(size: int, weight: int = 800) -> ImageFont.FreeTypeFont:
    from app.media.reel_renderer import font as base_font

    return base_font(size, weight)


@lru_cache(maxsize=16)
def mono(size: int) -> ImageFont.FreeTypeFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return font(size, 600)


def wrap(text: str, face, max_width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if face.getlength(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def wrap_chars(text: str, face, max_width: int) -> list[str]:
    """Wrap without spaces (URLs), breaking at any character."""

    lines, current = [], ""
    for char in text:
        if face.getlength(current + char) > max_width and current:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def wrap_words_then_chars(text: str, face, max_width: int) -> list[str]:
    """Wrap at spaces where possible; break long tokens (URLs) anywhere.
    Keeps every character (including spaces) so highlight offsets still line up."""

    if " " not in text:
        return wrap_chars(text, face, max_width)
    lines, current = [], ""
    for token in re.findall(r"\S+\s*", text):
        if face.getlength(current + token.rstrip()) <= max_width or not current:
            if face.getlength(token.rstrip()) > max_width and not current:
                parts = wrap_chars(token, face, max_width)
                lines.extend(parts[:-1])
                current = parts[-1]
            else:
                current += token
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


def fit_font(text: str, max_width: int, start: int, minimum: int, weight: int = 900):
    size = start
    while size > minimum and font(size, weight).getlength(text) > max_width:
        size -= 4
    return font(size, weight)


def draw_center(draw, y: float, text: str, face, fill, stroke: int = 0, cx: float = CX) -> None:
    width = face.getlength(text)
    draw.text((cx - width / 2, y), text, font=face, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))


def block_center(draw, top: float, text: str, face, fill, max_width: int, gap: int = 10, stroke: int = 0) -> float:
    ascent, descent = face.getmetrics()
    y = top
    for line in wrap(text, face, max_width):
        draw_center(draw, y, line, face, fill, stroke)
        y += ascent + descent + gap
    return y


# --------------------------------------------------------------- easing --


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def ease_out(value: float) -> float:
    value = clamp(value)
    return 1 - (1 - value) ** 3


def ease_in_out(value: float) -> float:
    value = clamp(value)
    return 3 * value**2 - 2 * value**3


def back_out(value: float) -> float:
    """Overshoot then settle: the 'pop'."""

    value = clamp(value)
    c = 1.70158
    return 1 + (c + 1) * (value - 1) ** 3 + c * (value - 1) ** 2


def progress(u: float, start: float, duration: float) -> float:
    return clamp((u - start) / duration) if duration > 0 else (1.0 if u >= start else 0.0)


def paste_scaled(frame: Image.Image, image: Image.Image, center: tuple[float, float], scale: float = 1.0, alpha: float = 1.0) -> None:
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.BILINEAR)
    if alpha < 0.999:
        image = image.copy()
        image.putalpha(image.getchannel("A").point(lambda a: int(a * alpha)))
    x, y = int(center[0] - image.width / 2), int(center[1] - image.height / 2)
    frame.alpha_composite(image, (max(x, 0), max(y, 0)), (max(-x, 0), max(-y, 0)))


def translucent(frame: Image.Image, box, fill, radius: int = 24, outline=None, width: int = 0) -> None:
    """Rounded rectangle with real alpha blending (ImageDraw on RGBA overwrites alpha)."""

    x0, y0, x1, y1 = (int(v) for v in box)
    overlay = Image.new("RGBA", (x1 - x0 + 1, y1 - y0 + 1), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle([0, 0, x1 - x0, y1 - y0], radius=radius, fill=fill, outline=outline, width=width)
    frame.alpha_composite(overlay, (x0, y0))


def layer() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def text_tile(text: str, face, fill, pad: tuple[int, int] = (0, 0), bg=None, radius: int = 24, stroke: int = 0) -> Image.Image:
    box = face.getbbox(text, stroke_width=stroke)
    width, height = box[2] - box[0] + pad[0] * 2, box[3] - box[1] + pad[1] * 2
    tile = Image.new("RGBA", (max(width, 1), max(height, 1)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    if bg:
        draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=bg)
    draw.text((pad[0] - box[0], pad[1] - box[1]), text, font=face, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
    return tile


# ------------------------------------------------------------ background --


@lru_cache(maxsize=4)
def _background_strip(seed: int) -> Image.Image:
    import random

    rng = random.Random(seed)
    strip = Image.new("RGB", (W, H + 600), (12, 9, 26))
    draw = ImageDraw.Draw(strip)
    for y in range(0, H + 600, 6):
        mix = y / (H + 600)
        draw.rectangle([0, y, W, y + 6], fill=(int(16 - 8 * mix), int(11 - 6 * mix), int(36 - 20 * mix)))
    glow = Image.new("RGB", strip.size, (0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for _ in range(5):
        x, y, r = rng.randint(-100, W + 100), rng.randint(0, H + 600), rng.randint(260, 520)
        color = rng.choice([(110, 52, 230), (40, 90, 230), (180, 60, 200)])
        gdraw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    strip = ImageChops.add(strip, ImageChops.multiply(glow, Image.new("RGB", glow.size, (110, 110, 110))))
    grid = ImageDraw.Draw(strip)
    for x in range(0, W, 90):
        grid.line([(x, 0), (x, H + 600)], fill=(30, 26, 52), width=1)
    for y in range(0, H + 600, 90):
        grid.line([(0, y), (W, y)], fill=(30, 26, 52), width=1)
    return strip


def background(seed: int, t: float) -> Image.Image:
    strip = _background_strip(seed)
    offset = int(300 + 260 * math.sin(t / 6.0))
    return strip.crop((0, offset, W, offset + H)).convert("RGBA")


# --------------------------------------------------------------- shots ----


@dataclass
class Shot:
    spec: dict
    line: TimedLine
    index: int
    assets: dict = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return str(self.spec.get("kind", "statement"))

    @property
    def stage(self) -> str:
        return str(self.spec.get("stage", ""))


NO_CAPTION_STAGES = {"weak", "strong", "question", "bad", "good", "edit"}


def wants_captions(shot: Shot) -> bool:
    if shot.kind in {"redline", "chat", "hack"} and shot.stage in NO_CAPTION_STAGES:
        return False
    return True


# ---------------------------------------------------------------- icons ---


def icon_pin(draw, x, y, size, color) -> None:
    r = size * 0.32
    draw.ellipse([x - r, y - r - size * 0.12, x + r, y + r - size * 0.12], fill=color)
    draw.polygon([(x - r * 0.8, y), (x + r * 0.8, y), (x, y + size * 0.45)], fill=color)
    draw.ellipse([x - r * 0.4, y - r * 0.4 - size * 0.12, x + r * 0.4, y + r * 0.4 - size * 0.12], fill=(20, 18, 40))


def icon_check(draw, x, y, size, color, bg) -> None:
    draw.ellipse([x - size / 2, y - size / 2, x + size / 2, y + size / 2], fill=bg)
    draw.line([(x - size * 0.22, y), (x - size * 0.05, y + size * 0.18), (x + size * 0.25, y - size * 0.2)], fill=color, width=max(4, size // 9))


def icon_cross(draw, x, y, size, color, bg) -> None:
    draw.ellipse([x - size / 2, y - size / 2, x + size / 2, y + size / 2], fill=bg)
    d = size * 0.2
    draw.line([(x - d, y - d), (x + d, y + d)], fill=color, width=max(4, size // 9))
    draw.line([(x - d, y + d), (x + d, y - d)], fill=color, width=max(4, size // 9))


def icon_plane(draw, x, y, size, color) -> None:
    draw.polygon([(x - size / 2, y), (x + size / 2, y - size / 2), (x + size * 0.1, y + size / 2), (x - size * 0.05, y + size * 0.1)], fill=color)


def icon_bulb(draw, x, y, size, color) -> None:
    draw.ellipse([x - size * 0.35, y - size * 0.45, x + size * 0.35, y + size * 0.25], fill=color)
    draw.rectangle([x - size * 0.16, y + size * 0.2, x + size * 0.16, y + size * 0.42], fill=color)


def icon_calendar(draw, x, y, size, color) -> None:
    draw.rounded_rectangle([x - size * 0.4, y - size * 0.32, x + size * 0.4, y + size * 0.4], radius=6, outline=color, width=6)
    draw.rectangle([x - size * 0.4, y - size * 0.32, x + size * 0.4, y - size * 0.1], fill=color)


def icon_cap(draw, x, y, size, color) -> None:
    draw.polygon([(x - size * 0.5, y - size * 0.05), (x, y - size * 0.3), (x + size * 0.5, y - size * 0.05), (x, y + size * 0.2)], fill=color)
    draw.rectangle([x - size * 0.25, y + size * 0.02, x + size * 0.25, y + size * 0.3], fill=color)


def icon_cash(draw, x, y, size, color) -> None:
    draw.rounded_rectangle([x - size * 0.45, y - size * 0.28, x + size * 0.45, y + size * 0.28], radius=8, outline=color, width=6)
    draw.ellipse([x - size * 0.13, y - size * 0.13, x + size * 0.13, y + size * 0.13], outline=color, width=5)


# -------------------------------------------------------------- captions --


def caption_chunks(words: list[TimedWord], max_words: int = 3, max_chars: int = 18) -> list[list[int]]:
    chunks, current, length = [], [], 0
    for index, word in enumerate(words):
        if current and (len(current) >= max_words or length + len(word.text) > max_chars):
            chunks.append(current)
            current, length = [], 0
        current.append(index)
        length += len(word.text) + 1
        if word.text.endswith((".", "?", "!", ":")) and current:
            chunks.append(current)
            current, length = [], 0
    if current:
        chunks.append(current)
    return chunks


def draw_captions(frame: Image.Image, shot: Shot, t: float) -> None:
    words = shot.line.words
    if not words:
        return
    chunks = shot.assets.setdefault("chunks", caption_chunks(words))
    current = None
    for chunk in chunks:
        if words[chunk[0]].start - 0.05 <= t:
            current = chunk
    if current is None:
        current = chunks[0]
    if t > shot.line.speech_end + 0.25:
        return
    face = font(78, 900)
    texts = [words[i].text for i in current]
    space = face.getlength(" ")
    widths = [face.getlength(text) for text in texts]
    total = sum(widths) + space * (len(texts) - 1)
    scale = min(1.0, 900 / max(total, 1))
    if scale < 1:
        face = font(int(78 * scale), 900)
        widths = [face.getlength(text) for text in texts]
        space = face.getlength(" ")
        total = sum(widths) + space * (len(texts) - 1)
    draw = ImageDraw.Draw(frame)
    x = CX - total / 2
    appear = progress(t, words[current[0]].start - 0.05, 0.12)
    y = CAPTION_Y + (1 - ease_out(appear)) * 18
    for index, text, width in zip(current, texts, widths):
        active = words[index].start <= t
        color = YELLOW if active and index == max(i for i in current if words[i].start <= t) else WHITE
        draw.text((x, y), text, font=face, fill=color, stroke_width=9, stroke_fill=(0, 0, 0))
        x += width + space


# ----------------------------------------------------------- page assets --


def page_assets(capture, url: str) -> dict:
    """A captured posting with browser chrome, plus a blurred backdrop version."""

    from app.media.reel_renderer import BROWSER_HEADER, _with_browser_chrome

    raw = Image.open(capture.image_path).convert("RGB")
    page = _with_browser_chrome(raw, capture.url or url)
    shift = lambda box: (box[0], box[1] + BROWSER_HEADER, box[2], box[3]) if box else None  # noqa: E731
    title = shift(capture.title)
    pay = shift(capture.pay)
    rects = [shift(box) for box in capture.pay_rects] if capture.pay_rects else ([pay] if pay else [])
    top = page.crop((0, 0, W, min(page.height, H))).resize((W // 4, min(page.height, H) // 4))
    blurred = top.filter(ImageFilter.GaussianBlur(10)).resize((W, min(page.height, H)))
    if blurred.height < H:
        canvas = Image.new("RGB", (W, H), (12, 9, 26))
        canvas.paste(blurred, (0, 0))
        blurred = canvas
    dark = Image.blend(blurred, Image.new("RGB", blurred.size, (16, 10, 38)), 0.88).convert("RGBA")
    return {"page": page, "title": title, "pay": pay, "rects": rects, "backdrop": dark}


# ---------------------------------------------------------------- scenes --


def scene_alert_hook(frame: Image.Image, shot: Shot, u: float) -> None:
    spec = shot.spec
    overlay, draw = layer()
    pulse = 0.5 + 0.5 * math.sin(u * 7)
    badge_face = font(40, 900)
    label = spec.get("badge", "STILL OPEN")
    width = badge_face.getlength(label) + 110
    draw.rounded_rectangle([CX - width / 2, 214, CX + width / 2, 290], radius=38, fill=RED)
    draw.ellipse([CX - width / 2 + 30, 238, CX - width / 2 + 58, 266], fill=(255, 255, 255, int(150 + 105 * pulse)))
    draw.text((CX - width / 2 + 76, 228), label, font=badge_face, fill=WHITE)
    frame.alpha_composite(overlay)
    logo = shot.assets.get("logo")
    if logo is not None:
        paste_scaled(frame, logo, (CX, 450), 0.9 + 0.1 * back_out(progress(u, 0, 0.35)))
    draw = ImageDraw.Draw(frame)
    block_center(draw, 590, spec.get("company", ""), fit_font(spec.get("company", ""), 900, 100, 60), WHITE, 920)
    sub = " · ".join(x for x in [spec.get("role", ""), spec.get("location", "")] if x)
    draw_center(draw, 716, sub, fit_font(sub, 900, 48, 32, 700), MUTED)
    draw_center(draw, 812, "up to", font(54, 800), MUTED)
    pay = spec.get("pay", "")
    face = fit_font(pay, 940, 230, 120)
    tile = text_tile(pay, face, YELLOW, stroke=4)
    drift = 0.03 * clamp(u / 4)
    paste_scaled(frame, tile, (CX, 1010), 1.12 - 0.12 * ease_out(progress(u, 0, 0.3)) + drift)


def scene_proof(frame: Image.Image, shot: Shot, u: float) -> None:
    page = shot.assets.get("page")
    if page is None:
        _proof_card(frame, shot, u)
        return
    title, pay, rects = shot.assets.get("title"), shot.assets.get("pay"), shot.assets.get("rects") or []
    start_y = max((title[1] - 380) if title else 0, 0)
    target_y = (pay[1] - 760) if pay else start_y + 900
    max_y = max(page.height - H, 0)
    start_y, target_y = min(start_y, max_y), clamp(target_y, 0, max_y)
    move = ease_in_out(progress(u, 0.35, 0.8))
    y = int(start_y + (target_y - start_y) * move)
    zoom = 1.0 + 0.035 * clamp(u / 3)
    view = page.crop((0, y, W, y + int(H / zoom))).resize((W, H)).convert("RGBA")
    if pay and u >= 1.15:
        sweep = ease_out(progress(u, 1.15, 0.35))
        total = sum(box[2] for box in rects) or 1
        done = 0.0
        for px, py, pw, ph in rects:
            share = clamp((sweep * total - done) / max(pw, 1))
            done += pw
            if share <= 0:
                continue
            left, top = (px - 8) * zoom, (py - y - 4) * zoom
            box = [int(max(left, 0)), int(max(top, 0)), int(min(left + (pw + 16) * zoom * share, W)), int(min(top + (ph + 8) * zoom, H))]
            if box[2] > box[0] and box[3] > box[1]:
                region = view.crop(box).convert("RGB")
                view.paste(ImageChops.multiply(region, Image.new("RGB", region.size, (255, 222, 70))).convert("RGBA"), box[:2])
    frame.alpha_composite(view)
    band, draw = layer()
    draw.rectangle([0, 0, W, 150], fill=(10, 8, 22, 210))
    frame.alpha_composite(band)
    chip = text_tile("THE REAL POSTING", font(36, 900), INK, pad=(26, 14), bg=YELLOW)
    paste_scaled(frame, chip, (CX, 210 + chip.height / 2), back_out(progress(u, 0, 0.3)))


def _proof_card(frame: Image.Image, shot: Shot, u: float) -> None:
    spec = shot.spec
    card, draw = layer()
    top = 420
    draw.rounded_rectangle([MARGIN, top, W - MARGIN - 40, top + 760], radius=40, fill=WHITE)
    draw.text((MARGIN + 50, top + 50), spec.get("company", ""), font=font(64, 900), fill=INK)
    y = top + 150
    for line in wrap(spec.get("title", ""), font(46, 700), 780)[:3]:
        draw.text((MARGIN + 50, y), line, font=font(46, 700), fill=(60, 60, 80))
        y += 62
    draw.text((MARGIN + 50, y + 20), spec.get("location", ""), font=font(40, 600), fill=(110, 110, 130))
    pay = spec.get("pay_range") or spec.get("pay", "")
    face = font(70, 900)
    sweep = ease_out(progress(u, 0.6, 0.35))
    pay_y = y + 120
    width = face.getlength(pay)
    draw.rectangle([MARGIN + 40, pay_y - 6, MARGIN + 60 + width * sweep, pay_y + 90], fill=(255, 226, 80))
    draw.text((MARGIN + 50, pay_y), pay, font=face, fill=INK)
    draw.text((MARGIN + 50, top + 680), "From the company's job posting", font=font(34, 600), fill=(120, 120, 140))
    frame.alpha_composite(card)


def scene_market(frame: Image.Image, shot: Shot, u: float) -> None:
    spec = shot.spec
    draw = ImageDraw.Draw(frame)
    draw_center(draw, 250, "How it compares", font(72, 900), WHITE)
    pool = "intern roles" if spec.get("level") == "intern" else "new grad roles"
    draw_center(draw, 345, f"vs. {spec.get('count', 0)} {pool} I track", font(44, 700), MUTED)
    median = float(spec.get("median") or 0)
    pct = float(spec.get("pct") or 0)
    value = median * (1 + pct / 100)
    unit = "/hr" if spec.get("level") == "intern" else "/yr"

    def money(v: float) -> str:
        return f"${v / 1000:.0f}K{unit}" if unit == "/yr" else f"${v:.0f}{unit}"

    biggest = max(value, median, 1)
    rows = [("This role", value, YELLOW, spec.get("pay_range") or money(value)), ("Median", median, (120, 116, 150), money(median))]
    grow = ease_out(progress(u, 0.1, 0.7))
    for index, (label, amount, color, text) in enumerate(rows):
        y = 500 + index * 250
        draw.text((MARGIN, y), label, font=font(46, 800), fill=WHITE)
        value_face = font(46, 900)
        draw.text((W - MARGIN - 40 - value_face.getlength(text), y), text, font=value_face, fill=color)
        length = (W - 2 * MARGIN - 40) * (amount / biggest) * grow
        draw.rounded_rectangle([MARGIN, y + 72, MARGIN + max(length, 30), y + 152], radius=40, fill=color)
    badge = f"{'+' if pct >= 0 else '−'}{abs(round(pct))}%"
    tile = text_tile(badge, font(170, 900), GREEN if pct >= 0 else (251, 146, 60), stroke=3)
    paste_scaled(frame, tile, (CX, 1130), back_out(progress(u, 0.65, 0.35)))


def scene_facts(frame: Image.Image, shot: Shot, u: float) -> None:
    spec = shot.spec
    rows = []
    if spec.get("who"):
        rows.append((icon_cap, str(spec["who"]).capitalize()))
    if spec.get("location"):
        rows.append((icon_pin, spec["location"]))
    days = spec.get("posted_days")
    if days is not None:
        rows.append((icon_calendar, "Posted today" if days == 0 else f"Posted {days} day{'s' if days != 1 else ''} ago"))
    if spec.get("pay_range") or spec.get("pay"):
        rows.append((icon_cash, spec.get("pay_range") or spec.get("pay")))
    draw = ImageDraw.Draw(frame)
    draw_center(draw, 250, spec.get("company", ""), fit_font(spec.get("company", ""), 900, 80, 50), WHITE)
    draw_center(draw, 352, spec.get("role", ""), font(46, 700), MUTED)
    for index, (icon, text) in enumerate(rows):
        appear = back_out(progress(u, 0.1 + index * 0.28, 0.3))
        if appear <= 0.01:
            continue
        tile = Image.new("RGBA", (900, 150), (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(tile)
        tdraw.rounded_rectangle([0, 0, 899, 149], radius=32, fill=(255, 255, 255, 30), outline=(255, 255, 255, 60), width=2)
        icon(tdraw, 80, 75, 70, YELLOW)
        face = fit_font(text, 720, 52, 34, 800)
        tdraw.text((150, 75 - face.getmetrics()[0] / 2 - 6), text, font=face, fill=WHITE)
        paste_scaled(frame, tile, (CX, 540 + index * 180), 0.85 + 0.15 * appear, alpha=clamp(appear))


def scene_tip(frame: Image.Image, shot: Shot, u: float) -> None:
    text = shot.spec.get("text", "")
    overlay, draw = layer()
    draw.rounded_rectangle([MARGIN, 330, W - MARGIN - 40, 1180], radius=48, fill=(255, 255, 255, 245))
    icon_bulb(draw, CX, 470, 120, YELLOW)
    draw_center(draw, 560, "TIP", font(48, 900), ACCENT)
    face = fit_font(text, 10_000, 66, 66, 800)
    y = 650
    for line in wrap(text, face, 780)[:6]:
        draw_center(draw, y, line, face, INK)
        y += 84
    frame.alpha_composite(overlay)


def scene_cta(frame: Image.Image, shot: Shot, u: float) -> None:
    draw = ImageDraw.Draw(frame)
    pop = back_out(progress(u, 0, 0.3))
    tile = text_tile("Apply link", font(110, 900), WHITE, stroke=2)
    paste_scaled(frame, tile, (CX, 470), 0.9 + 0.1 * pop)
    tile = text_tile("in my bio", font(110, 900), YELLOW, stroke=2)
    paste_scaled(frame, tile, (CX, 600), 0.9 + 0.1 * pop)
    pill = Image.new("RGBA", (620, 120), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(pill)
    pdraw.rounded_rectangle([0, 0, 619, 119], radius=60, fill=(255, 255, 255))
    pdraw.ellipse([22, 18, 106, 102], fill=ACCENT)
    pdraw.text((128, 32), "@careerstacked", font=font(48, 800), fill=INK)
    paste_scaled(frame, pill, (CX, 800), back_out(progress(u, 0.25, 0.3)))
    send = progress(u, 0.6, 0.3)
    if send > 0:
        tile = Image.new("RGBA", (820, 110), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(tile)
        sdraw.rounded_rectangle([0, 0, 819, 109], radius=55, fill=(139, 92, 246, 235))
        icon_plane(sdraw, 70, 55, 54, WHITE)
        sdraw.text((120, 28), "Send to a friend who's applying", font=font(42, 800), fill=WHITE)
        paste_scaled(frame, tile, (CX, 990), back_out(send))
    arrow = ease_out(progress(u, 0.3, 0.4))
    if arrow > 0:
        bob = 14 * math.sin(u * 6)
        x0, y0 = CX - 140, 1120 + bob
        x1, y1 = x0 - 230 * arrow, y0 + 200 * arrow
        draw.line([(x0, y0), (x1, y1)], fill=YELLOW, width=16)
        if arrow > 0.6:
            draw.polygon([(x1 - 22, y1 + 18), (x1 + 38, y1 + 8), (x1 + 2, y1 - 46)], fill=YELLOW)
        draw.text((x0 + 20, y0 - 10), "tap the name", font=font(36, 800), fill=YELLOW)


def scene_countdown_intro(frame: Image.Image, shot: Shot, u: float) -> None:
    spec = shot.spec
    big = text_tile(str(spec.get("n", 5)), font(460, 900), YELLOW, stroke=4)
    paste_scaled(frame, big, (CX, 470), 1.1 - 0.1 * ease_out(progress(u, 0, 0.3)))
    draw = ImageDraw.Draw(frame)
    block_center(draw, 760, f"{spec.get('level', 'internships')} still hiring", font(76, 900), WHITE, 900)
    teaser = text_tile(f"#1 pays {spec.get('top', '')}", font(70, 900), INK, pad=(34, 20), bg=YELLOW)
    paste_scaled(frame, teaser, (CX, 1010), back_out(progress(u, 0.35, 0.3)))
    tiles = shot.assets.get("mystery", [])
    for index, tile in enumerate(tiles):
        appear = back_out(progress(u, 0.6 + index * 0.08, 0.25))
        paste_scaled(frame, tile, (CX - 2 * 170 + index * 170, 1200), appear)


def scene_countdown_item(frame: Image.Image, shot: Shot, u: float) -> None:
    spec = shot.spec
    rank = int(spec.get("rank", 1))
    rank_tile = text_tile(f"#{rank}", font(250, 900), YELLOW if rank == 1 else ACCENT, stroke=4)
    paste_scaled(frame, rank_tile, (300, 380), 1.15 - 0.15 * ease_out(progress(u, 0, 0.25)))
    logo = shot.assets.get("logo")
    if logo is not None:
        paste_scaled(frame, logo, (720, 380), back_out(progress(u, 0.05, 0.3)))
    draw = ImageDraw.Draw(frame)
    draw_center(draw, 580, spec.get("company", ""), fit_font(spec.get("company", ""), 920, 96, 56), WHITE)
    draw_center(draw, 700, spec.get("role", ""), font(46, 700), MUTED)
    pay = spec.get("pay", "")
    tile = text_tile(pay, fit_font(pay, 920, 180, 110), YELLOW, stroke=3)
    paste_scaled(frame, tile, (CX, 880), 1.08 - 0.08 * ease_out(progress(u, 0.1, 0.25)))
    fill = float(spec.get("top_pay_value") or 0) / max(float(spec.get("max_pay") or 1), 1)
    grow = ease_out(progress(u, 0.15, 0.6))
    translucent(frame, [MARGIN, 1060, W - MARGIN - 40, 1110], (255, 255, 255, 40), radius=25)
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle([MARGIN, 1060, MARGIN + (W - 2 * MARGIN - 40) * fill * grow, 1110], radius=25, fill=YELLOW if rank == 1 else ACCENT)
    n = int(spec.get("n", 5))
    for index in range(n):
        x = CX - (n - 1) * 30 + index * 60
        filled = (n - index) >= rank
        draw.ellipse([x - 14, 1170, x + 14, 1198], fill=YELLOW if filled else (80, 76, 110))


TIER_COLORS = {"S": (255, 127, 127), "A": (255, 191, 127), "B": (255, 223, 127), "C": (191, 255, 127)}


def scene_tier_board(frame: Image.Image, shot: Shot, u: float) -> None:
    spec = shot.spec
    stage = int(spec.get("stage", 0))
    rows = spec.get("rows", [])[:4]
    draw = ImageDraw.Draw(frame)
    draw_center(draw, 190, "Intern pay tiers", font(76, 900), WHITE, stroke=2)
    draw_center(draw, 290, "companies hiring right now", font(42, 700), MUTED)
    logos = shot.assets.get("logos", {})
    row_h = 230
    for row_index, row in enumerate(rows):
        y = 370 + row_index * (row_h + 18)
        tier = row["tier"]
        lit = row_index + 1 <= stage
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle([MARGIN, y, MARGIN + 190, y + row_h], radius=26, fill=TIER_COLORS.get(tier, (200, 200, 200)))
        letter = font(130, 900)
        draw.text((MARGIN + 95 - letter.getlength(tier) / 2, y + 36), tier, font=letter, fill=INK)
        translucent(frame, [MARGIN + 206, y, W - MARGIN - 40, y + row_h], (255, 255, 255, 34 if lit else 18), radius=26)
        for index, member in enumerate(row["members"][:3]):
            if lit:
                fresh = row_index + 1 == stage
                appear = back_out(progress(u, 0.1 + index * 0.18, 0.28)) if fresh else 1.0
                alpha = 1.0
            else:
                appear, alpha = 1.0, 0.18  # ghosted preview of what's coming
            x = MARGIN + 320 + index * 225
            logo = logos.get(member["company"])
            if logo is not None:
                paste_scaled(frame, logo, (x, y + 82), 0.95 * appear, alpha=alpha)
            if appear > 0.6:
                name = member["company"]
                name_tile = text_tile(name, fit_font(name, 215, 36, 24, 800), WHITE)
                pay_tile = text_tile(member["pay"], font(32, 900), YELLOW)
                paste_scaled(frame, name_tile, (x, y + 168), alpha=alpha)
                paste_scaled(frame, pay_tile, (x, y + 206), alpha=alpha)


def _headline(frame: Image.Image, text: str, u: float, top: int = 230) -> int:
    draw = ImageDraw.Draw(frame)
    face = fit_font(text, 10_000, 86, 86)
    y = top
    for line in wrap(text, face, 900)[:3]:
        draw_center(draw, y, line, face, WHITE, stroke=3)
        y += 104
    return y


def _resume_card(spec: dict, stage: str, u: float) -> Image.Image:
    card = Image.new("RGBA", (920, 760), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([0, 0, 919, 759], radius=30, fill=(252, 251, 247))
    draw.rounded_rectangle([50, 46, 470, 86], radius=10, fill=(60, 60, 75))
    draw.rounded_rectangle([50, 104, 680, 126], radius=8, fill=(200, 200, 210))
    draw.text((50, 160), "EXPERIENCE", font=font(30, 900), fill=(90, 90, 110))
    draw.line([(50, 202), (870, 202)], fill=(210, 210, 220), width=3)
    draw.text((50, 222), "Software Engineering Intern", font=font(34, 800), fill=(40, 40, 55))
    draw.text((640, 226), "Summer 2026", font=font(28, 600), fill=(120, 120, 135))
    face = font(44, 600)
    weak_lines = wrap(spec.get("weak", ""), face, 760)
    y = 300
    weak_top = y
    for line in weak_lines:
        draw.text((90, y), line, font=face, fill=(40, 40, 55) if stage in {"hook", "weak"} else (150, 150, 160))
        y += 60
    draw.ellipse([58, weak_top + 18, 74, weak_top + 34], fill=(40, 40, 55))
    weak_bottom = y
    if stage == "weak":
        draw.rounded_rectangle([78, weak_top - 10, 880, weak_bottom + 6], radius=14, outline=RED, width=6)
    if stage in {"strong", "why", "cta"}:
        strike = ease_out(progress(u, 0, 0.35)) if stage == "strong" else 1.0
        for index, line in enumerate(weak_lines):
            ly = weak_top + index * 60 + 28
            draw.line([(90, ly), (90 + face.getlength(line) * strike, ly)], fill=RED, width=5)
        strong = spec.get("strong", "")
        reveal = len(strong) if stage != "strong" else int(len(strong) * clamp((u - 0.35) / 1.6))
        typed = strong[:reveal]
        sy = weak_bottom + 40
        sface = font(46, 800)
        for line in wrap(typed, sface, 740):
            if stage in {"why", "cta"}:
                x = 110
                for word in line.split():
                    width = sface.getlength(word)
                    if re.search(r"\d", word) or word == strong.split()[0]:
                        draw.rectangle([x - 4, sy + 2, x + width + 4, sy + 58], fill=(255, 226, 80))
                    x += width + sface.getlength(" ")
            draw.text((110, sy), line, font=sface, fill=(21, 128, 61))
            sy += 64
        if typed:
            icon_check(draw, 70, weak_bottom + 66, 44, WHITE, GREEN)
    return card


def scene_redline(frame: Image.Image, shot: Shot, u: float) -> None:
    spec, stage = shot.spec, shot.stage
    labels = {"weak": ("BEFORE", RED), "strong": ("AFTER", GREEN), "why": ("WHY IT WORKS", ACCENT), "cta": ("SAVE THIS", ACCENT)}
    if stage == "hook":
        bottom = _headline(frame, shot.line.text, u)
        top = max(bottom + 30, 560)
    else:
        label, color = labels.get(stage, ("", ACCENT))
        tile = text_tile(label, font(48, 900), WHITE, pad=(34, 18), bg=color)
        paste_scaled(frame, tile, (CX, 300), back_out(progress(u, 0, 0.3)))
        top = 420
    card = _resume_card(spec, stage, u)
    paste_scaled(frame, card, (CX, top + card.height / 2), 0.96 + 0.04 * ease_out(progress(u, 0, 0.3)))


def _bubble(text: str, side: str, tone: str, max_width: int = 760) -> Image.Image:
    face = font(44, 700)
    lines = wrap(text, face, max_width - 70)
    ascent, descent = face.getmetrics()
    height = len(lines) * (ascent + descent + 6) + 60
    width = int(max(face.getlength(line) for line in lines) + 70) if lines else 200
    fill = {"them": (233, 233, 235), "bad": (254, 215, 215), "good": (10, 132, 255)}[tone]
    ink = WHITE if tone == "good" else INK
    tile = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=40, fill=fill)
    y = 30
    for line in lines:
        draw.text((35, y), line, font=face, fill=ink)
        y += ascent + descent + 6
    return tile


def scene_chat(frame: Image.Image, shot: Shot, u: float) -> None:
    spec, stage = shot.spec, shot.stage
    order = ["hook", "question", "bad", "good", "why", "cta"]
    position = order.index(stage) if stage in order else 0
    draw = ImageDraw.Draw(frame)
    if stage == "hook":
        bottom = _headline(frame, shot.line.text, u)
        y = max(bottom + 40, 600)
    else:
        draw.ellipse([MARGIN, 190, MARGIN + 90, 280], fill=(120, 116, 150))
        draw.text((MARGIN + 30, 205), "?", font=font(56, 900), fill=WHITE)
        draw.text((MARGIN + 110, 200), "Interviewer", font=font(44, 800), fill=WHITE)
        draw.text((MARGIN + 110, 252), "live round", font=font(30, 600), fill=MUTED)
        y = 340
    bubbles = [("question", spec.get("question", ""), "left", "them")]
    if spec.get("bad", "").strip(". "):
        bubbles.append(("bad", spec.get("bad", ""), "right", "bad"))
    else:
        bubbles.append(("bad", "...", "right", "bad"))
    bubbles.append(("good", spec.get("good", ""), "right", "good"))
    for key, text, side, tone in bubbles:
        index = order.index(key)
        if position < index and not (stage == "hook" and key == "question"):
            continue
        current = position == index or (stage == "hook" and key == "question")
        typing = current and u < 0.35 and stage != "hook"
        if typing:
            dots = Image.new("RGBA", (170, 90), (0, 0, 0, 0))
            ddraw = ImageDraw.Draw(dots)
            ddraw.rounded_rectangle([0, 0, 169, 89], radius=45, fill=(233, 233, 235) if side == "left" else (10, 132, 255))
            for d in range(3):
                bounce = 8 * math.sin(u * 14 + d)
                ddraw.ellipse([32 + d * 40, 34 - bounce, 56 + d * 40, 58 - bounce], fill=(140, 140, 150) if side == "left" else WHITE)
            x = MARGIN + 85 if side == "left" else W - MARGIN - 40 - 85
            paste_scaled(frame, dots, (x, y + 45))
            y += 120
            continue
        bubble = _bubble(text, side, tone)
        pop = back_out(progress(u, 0.35 if current and stage != "hook" else 0, 0.25)) if current else 1.0
        x = MARGIN + bubble.width / 2 if side == "left" else W - MARGIN - 40 - bubble.width / 2
        paste_scaled(frame, bubble, (x, y + bubble.height / 2), 0.9 + 0.1 * pop, alpha=clamp(pop * 1.2))
        if tone in {"bad", "good"} and pop > 0.5:
            badge_draw = ImageDraw.Draw(frame)
            bx = x - bubble.width / 2 - 10
            by = y + 20
            if tone == "bad":
                icon_cross(badge_draw, bx, by, 64, WHITE, RED)
            else:
                icon_check(badge_draw, bx, by, 64, WHITE, GREEN)
        y += bubble.height + 34
    if stage in {"why", "cta"}:
        label = "SAVE THIS" if stage == "cta" else "WHY IT WORKS"
        tile = text_tile(label, font(42, 900), INK, pad=(30, 16), bg=YELLOW)
        paste_scaled(frame, tile, (CX, min(y + 50, 1260)), back_out(progress(u, 0, 0.3)))


def scene_hack(frame: Image.Image, shot: Shot, u: float) -> None:
    spec, stage = shot.spec, shot.stage
    order = ["hook", "before", "edit", "explain", "why", "cta"]
    position = order.index(stage) if stage in order else 0
    before, after = spec.get("before", ""), spec.get("after", "")
    if stage == "hook":
        bottom = _headline(frame, shot.line.text, u)
        top = max(bottom + 40, 620)
    else:
        top = 330
        draw = ImageDraw.Draw(frame)
        draw_center(draw, 220, spec.get("site", ""), font(44, 800), MUTED)
    face = mono(40)
    appended = after.startswith(before)
    if position < 2:
        shown, highlight_from = before, len(before)
    else:
        typed = 1.0 if position > 2 else clamp((u - 0.15) / 1.3)
        if appended:
            suffix = after[len(before):]
            shown = before + suffix[: int(len(suffix) * typed)]
            highlight_from = len(before)
        else:
            shown = after[: int(len(after) * typed)] if position == 2 else after
            highlight_from = 0
    lines = wrap_words_then_chars(shown or " ", face, 800)
    ascent, descent = face.getmetrics()
    box_height = len(lines) * (ascent + descent + 8) + 70
    overlay, draw = layer()
    draw.rounded_rectangle([MARGIN, top, W - MARGIN - 40, top + box_height], radius=34, fill=(245, 245, 248))
    count = 0
    y = top + 35
    cursor = None
    for line in lines:
        x = MARGIN + 50
        for char in line:
            width = face.getlength(char)
            if count >= highlight_from and position >= 2:
                draw.rectangle([x, y - 2, x + width, y + ascent + descent], fill=(255, 226, 80))
            draw.text((x, y), char, font=face, fill=INK)
            x += width
            count += 1
        cursor = (x, y)
        y += ascent + descent + 8
    if cursor and position == 2 and int(u * 3) % 2 == 0:
        draw.rectangle([cursor[0] + 2, cursor[1], cursor[0] + 6, cursor[1] + ascent + descent], fill=(10, 132, 255))
    frame.alpha_composite(overlay)
    if position >= 3:
        results = [("Software Engineer Intern", "Posted 14 minutes ago"), ("New Grad Software Engineer", "Posted 38 minutes ago"), ("Backend Engineer, Early Career", "Posted 52 minutes ago")]
        if "fromage" in after:
            results = [(r, "Posted today") for r, _ in results]
        elif "f_E" in after:
            results = [(r, label) for (r, _), label in zip(results, ["Internship", "Entry level", "Entry level"])]
        elif not appended:
            results = [(r, "Company job board") for r, _ in results]
        for index, (role, meta) in enumerate(results):
            appear = back_out(progress(u, 0.1 + index * 0.15, 0.3)) if position == 3 else 1.0
            card = Image.new("RGBA", (880, 150), (0, 0, 0, 0))
            cdraw = ImageDraw.Draw(card)
            cdraw.rounded_rectangle([0, 0, 879, 149], radius=26, fill=(255, 255, 255, 235))
            cdraw.rounded_rectangle([28, 34, 110, 116], radius=18, fill=(200, 196, 220))
            cdraw.text((140, 30), role, font=font(40, 800), fill=INK)
            cdraw.text((140, 86), meta, font=font(32, 700), fill=(22, 163, 74))
            paste_scaled(frame, card, (CX, top + box_height + 110 + index * 170), 0.9 + 0.1 * appear, alpha=clamp(appear))


DRAWERS = {
    "alert_hook": scene_alert_hook,
    "proof": scene_proof,
    "market_bar": scene_market,
    "facts": scene_facts,
    "tip": scene_tip,
    "cta": scene_cta,
    "countdown_intro": scene_countdown_intro,
    "countdown_item": scene_countdown_item,
    "tier_board": scene_tier_board,
    "redline": scene_redline,
    "chat": scene_chat,
    "hack": scene_hack,
}


def draw_shot(shot: Shot, t: float, seed: int) -> Image.Image:
    frame = background(seed, t)
    u = t - shot.line.start
    DRAWERS.get(shot.kind, scene_tip)(frame, shot, u)
    if wants_captions(shot):
        draw_captions(frame, shot, t)
    draw = ImageDraw.Draw(frame)
    handle = font(30, 800)
    draw.text((MARGIN, 112), "@careerstacked", font=handle, fill=(255, 255, 255, 150))
    return frame


def compose(shots: list[Shot], index: int, t: float, seed: int) -> Image.Image:
    shot = shots[index]
    frame = draw_shot(shot, t, seed)
    since = t - shot.line.start
    if index > 0 and since < TRANSITION:
        # Quick push-in from the previous shot.
        previous = draw_shot(shots[index - 1], shot.line.start - 0.001, seed)
        k = ease_out(since / TRANSITION)
        offset = int(W * 0.35 * (1 - k))
        canvas = previous.copy()
        canvas = Image.blend(canvas, Image.new("RGBA", canvas.size, (0, 0, 0, 255)), 0.25 * k)
        canvas.alpha_composite(frame, (offset, 0), (0, 0))
        frame = canvas
    if index == 0 and t < 0.3:
        # Punch-in on the very first frames, so the cover frame is already full.
        zoom = 1 + 0.06 * (1 - t / 0.3)
        cw, ch = int(W / zoom), int(H / zoom)
        frame = frame.crop(((W - cw) // 2, (H - ch) // 2, (W - cw) // 2 + cw, (H - ch) // 2 + ch)).resize((W, H))
    return frame


# ------------------------------------------------------------ assets/audio --


def prepare_assets(shots: list[Shot], settings: Settings, work_dir: Path) -> None:
    from app.media.logos import logo as company_logo

    cache = settings.assets_dir / "logos"
    jobs: dict[str, dict] = {}
    for shot in shots:
        url = shot.spec.get("url")
        if url and shot.kind in {"proof", "alert_hook", "cta"}:
            jobs.setdefault(url, {"url": url, "alt_url": shot.spec.get("alt_url", ""), "pay": shot.spec.get("pay_range") or shot.spec.get("pay", "")})
    captures = {}
    if jobs and settings.capture_postings:
        try:
            from app.media.page_capture import capture_pages

            ordered = list(jobs.values())
            found = capture_pages(ordered, work_dir / "pages")
            for index, job in enumerate(ordered):
                if found.get(index) is not None:
                    captures[job["url"]] = page_assets(found[index], job["url"])
        except Exception as exc:
            LOG.warning("Page capture unavailable: %s", str(exc)[:200])
    for shot in shots:
        spec = shot.spec
        url = spec.get("url", "")
        if url in captures:
            assets = captures[url]
            if shot.kind == "proof":
                shot.assets.update(assets)
            elif shot.kind in {"alert_hook", "cta"}:
                shot.assets["backdrop"] = assets["backdrop"]
        if shot.kind in {"alert_hook", "countdown_item"} and spec.get("company"):
            size = 210 if shot.kind == "alert_hook" else 230
            shot.assets["logo"] = company_logo(spec["company"], url, size, cache)
        if shot.kind == "countdown_intro":
            tiles = []
            for _company in spec.get("companies", [])[:5]:
                tile = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
                tdraw = ImageDraw.Draw(tile)
                tdraw.rounded_rectangle([0, 0, 139, 139], radius=28, fill=(60, 54, 96))
                tdraw.text((48, 22), "?", font=font(80, 900), fill=WHITE)
                tiles.append(tile)
            shot.assets["mystery"] = tiles
        if shot.kind == "tier_board":
            logos = {}
            for row in spec.get("rows", []):
                for member in row.get("members", []):
                    logos[member["company"]] = company_logo(member["company"], member.get("url", ""), 120, cache)
            shot.assets["logos"] = logos


def sound_events(shots: list[Shot]) -> list[tuple[float, str]]:
    events: list[tuple[float, str]] = []
    for shot in shots:
        start = shot.line.start
        if shot.index > 0:
            events.append((start, "whoosh"))
        if shot.kind in {"alert_hook", "countdown_item", "market_bar"}:
            events.append((start + (0.65 if shot.kind == "market_bar" else 0.05), "pop"))
        if shot.kind == "proof":
            events.append((start + 1.15, "pop"))
        if shot.kind == "chat" and shot.stage in {"question", "bad", "good"}:
            events.append((start + 0.35, "pop"))
        if shot.kind == "tier_board" and int(shot.spec.get("stage", 0)) > 0:
            for index, _member in enumerate(shot.spec["rows"][int(shot.spec["stage"]) - 1]["members"][:3]):
                events.append((start + 0.1 + index * 0.18, "pop"))
        if shot.kind == "hack" and shot.stage == "edit":
            for step in range(10):
                events.append((start + 0.15 + step * 0.13, "click"))
        if shot.kind == "redline" and shot.stage == "strong":
            events.append((start + 0.05, "whoosh"))
    return events


# ----------------------------------------------------------------- render --


def render_studio(settings: Settings, script_row: dict, output_root: Path) -> RenderArtifact:
    from app.media.reel_renderer import mix_audio, write_word_srt
    from app.media.sfx import render_sfx_track

    from app.utils import json_loads

    meta = json_loads(script_row.get("metadata_json"), default={}) or {}
    script_text = script_row["full_script"]
    slug = slugify(f"{script_row['id']}-{hash_text(script_text)[:10]}")
    work_dir = ensure_directory(output_root / slug)
    final_path = output_root / f"{slug}.mp4"
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    seed = int(hash_text(script_text)[:8], 16) % 1000
    voice = synthesize_timed_lines(lines, work_dir, "voiceover", settings)
    specs = list(meta.get("scenes") or [])
    shots = []
    for index, line in enumerate(voice.lines):
        spec = specs[index] if index < len(specs) else (specs[-1] if specs else {"kind": "tip", "text": line.text})
        shots.append(Shot(dict(spec), line, index))
    prepare_assets(shots, settings, work_dir)
    sfx = render_sfx_track(sound_events(shots), voice.duration, work_dir / "sfx.wav", seed=seed) if settings.sound_effects else None
    audio = mix_audio(settings, voice, work_dir, seed, sfx)
    subtitles = write_word_srt(voice.lines, work_dir / "captions.srt")

    fps = settings.render_fps
    total = int(math.ceil(voice.duration * fps))
    command = [
        settings.ffmpeg_binary, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
        "-i", "-", "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "19", "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "copy", "-shortest",
        "-movflags", "+faststart", str(final_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    index = 0
    try:
        for number in range(total):
            t = number / fps
            while index < len(shots) - 1 and t >= shots[index].line.end:
                index += 1
            frame = compose(shots, index, t, seed).convert("RGB")
            assert process.stdin is not None
            process.stdin.write(frame.tobytes())
    finally:
        if process.stdin:
            process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", "ignore") if process.stderr else ""
        code = process.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg encode failed: {stderr[-800:]}")
    return RenderArtifact(
        script_id=script_row["id"],
        provider="studio",
        video_path=final_path,
        audio_path=voice.path,
        subtitle_path=subtitles,
        duration_seconds=voice.duration,
        metadata={
            "tts_engine": voice.engine,
            "work_dir": str(work_dir),
            "thumb_offset_ms": 300,
            "scenes": [shot.kind for shot in shots],
            "style": f"studio:{meta.get('format', '')}",
        },
        fallback_used=False,
    )
