"""Scene image generation for fallback reels.

Every scene is one spoken line rendered as a large, readable card. The card
text *is* the caption, and the renderer cuts scenes exactly on voice line
boundaries, so no separate burned-in subtitles are needed.

Layout respects Instagram's Reels safe zone: nothing important in the bottom
~380px (caption / buttons) or the right ~140px (like / share rail).
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import Settings
from app.utils import ensure_directory, first_existing_file

WIDTH, HEIGHT = 1080, 1920
SAFE_LEFT, SAFE_RIGHT = 96, 940
TEXT_TOP, TEXT_BOTTOM = 420, 1380

# (background top, background bottom, accent, accent text)
PALETTES = [
    ("#0B1021", "#1B2A6B", "#FACC15", "#111111"),
    ("#0A1512", "#0F5C4E", "#34D399", "#04130E"),
    ("#140B1F", "#4C1D95", "#F472B6", "#1A0612"),
    ("#0F172A", "#1E3A8A", "#38BDF8", "#06121D"),
    ("#1A0E05", "#7C2D12", "#FB923C", "#1A0A02"),
]

CATEGORY_LABELS = {
    "openings_job_alert": "JOB ALERT",
    "application_strategy": "APPLICATION TIP",
    "interview_prep": "INTERVIEW PREP",
    "resume_portfolio": "RESUME TIP",
    "market_context": "MARKET UPDATE",
    "motivational_community": "KEEP GOING",
}

FONT_CANDIDATES_BOLD = [
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/Library/Fonts/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
]
FONT_CANDIDATES_REGULAR = [
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
]


@lru_cache(maxsize=64)
def _load_font(path: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(path, size=size)
    try:
        axes = font.get_variation_axes()
    except Exception:
        axes = []
    if axes:
        try:
            font.set_variation_by_axes([weight])
        except Exception:
            pass
    return font


def _font(settings: Settings, size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    fonts_dir = settings.assets_dir / "fonts"
    asset_fonts = sorted(fonts_dir.glob("*.ttf")) + sorted(fonts_dir.glob("*.otf"))
    bundled = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Montserrat-Variable.ttf"
    candidates = asset_fonts + [bundled] + (FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR)
    path = first_existing_file(candidates)
    if path:
        return _load_font(str(path), size, 800 if bold else 500)
    return ImageFont.load_default()


def _hex(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _gradient(width: int, height: int, start: str, end: str) -> Image.Image:
    start_rgb, end_rgb = _hex(start), _hex(end)
    column = Image.new("RGB", (1, height))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        column.putpixel((0, y), tuple(int(start_rgb[i] + (end_rgb[i] - start_rgb[i]) * ratio) for i in range(3)))
    return column.resize((width, height))


def _background(palette: tuple[str, str, str, str], seed: int) -> Image.Image:
    top, bottom, accent, _ = palette
    image = _gradient(WIDTH, HEIGHT, top, bottom).convert("RGBA")
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    accent_rgb = _hex(accent)
    for orb in range(3):
        radius = 340 + orb * 120
        cx = int(WIDTH * (0.15 + 0.35 * orb) + math.sin(seed * 1.7 + orb) * 120)
        cy = int(HEIGHT * (0.18 + 0.3 * orb) + math.cos(seed * 1.3 + orb) * 160)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*accent_rgb, 34))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    image = Image.alpha_composite(image, glow)
    # Faint dot grid for texture.
    grid = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    for y in range(40, HEIGHT, 72):
        for x in range(40, WIDTH, 72):
            grid_draw.ellipse((x, y, x + 3, y + 3), fill=(255, 255, 255, 16))
    return Image.alpha_composite(image, grid)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_text(draw: ImageDraw.ImageDraw, text: str, settings: Settings, max_width: int, max_height: int, start: int, minimum: int = 52):
    size = start
    while size >= minimum:
        font = _font(settings, size, bold=True)
        lines = _wrap(draw, text, font, max_width)
        line_height = int(size * 1.22)
        if len(lines) * line_height <= max_height and all(draw.textlength(line, font=font) <= max_width for line in lines):
            return font, lines, line_height
        size -= 4
    font = _font(settings, minimum, bold=True)
    return font, _wrap(draw, text, font, max_width), int(minimum * 1.22)


def _upper_first(value: str) -> str:
    return value[:1].upper() + value[1:]


def _split_job_line(text: str) -> tuple[str, str, str] | None:
    """'First, Stripe is hiring a ML Intern in San Francisco.' -> ('Stripe', 'ML Intern', 'San Francisco')."""

    match = re.match(r"^(?:First,|Next,|And|Also,)?\s*(.+?) is hiring an? (.+?)(?: in ([^,]+?))?(?:, (for .+?))?\.$", text)
    if not match:
        return None
    company, role, location, audience = match.groups()
    detail = " · ".join(part for part in [location or "", _upper_first((audience or "").replace("for ", ""))] if part)
    role = role.strip()
    role = role[:1].upper() + role[1:]
    role = re.sub(r"^New grad\b", "New Grad", role)
    return company.strip(), role, detail


def _pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill, text_fill) -> int:
    x, y = xy
    width = int(draw.textlength(text, font=font)) + 56
    height = font.size + 30
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height // 2, fill=fill)
    draw.text((x + 28, y + height / 2), text, font=font, fill=text_fill, anchor="lm")
    return width


def build_scene_image(
    scene_text: str,
    output_path: Path,
    scene_index: int,
    settings: Settings,
    prompt_hint: str = "",
    total_scenes: int = 0,
    category: str = "",
    palette_index: int | None = None,
) -> Path:
    """Create a polished 1080x1920 scene card for one spoken line."""

    ensure_directory(output_path.parent)
    palette = PALETTES[(palette_index if palette_index is not None else scene_index) % len(PALETTES)]
    _, _, accent, accent_text = palette
    total_scenes = total_scenes or scene_index + 1
    is_hook = scene_index == 0
    is_cta = total_scenes > 1 and scene_index == total_scenes - 1

    provider_path = output_path.with_name(output_path.stem + "_provider.png")
    if prompt_hint and maybe_provider_background(prompt_hint, provider_path, settings):
        base = Image.open(provider_path).convert("RGBA").resize((WIDTH, HEIGHT))
        shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 150))
        image = Image.alpha_composite(base, shade)
    else:
        image = _background(palette, palette_index or 0)

    image = image.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    label = CATEGORY_LABELS.get(category, "CAREER TIP")
    _pill(draw, (SAFE_LEFT, 170), label, _font(settings, 34, bold=True), accent, accent_text)

    # Progress bar: one segment per scene, filled up to the current one.
    bar_y, gap = 280, 12
    segment = (SAFE_RIGHT - SAFE_LEFT - gap * (total_scenes - 1)) / max(total_scenes, 1)
    for index in range(total_scenes):
        x0 = SAFE_LEFT + index * (segment + gap)
        fill = accent if index <= scene_index else (255, 255, 255, 60)
        draw.rounded_rectangle((x0, bar_y, x0 + segment, bar_y + 10), radius=5, fill=fill)

    max_width = SAFE_RIGHT - SAFE_LEFT
    job = None if (is_hook or is_cta) else _split_job_line(scene_text)

    if job:
        company, role, detail = job
        company_font, company_lines, company_lh = _fit_text(draw, company, settings, max_width, 260, 132, 80)
        role_font, role_lines, role_lh = _fit_text(draw, role, settings, max_width, 420, 84, 54)
        detail_font = _font(settings, 46)
        block = len(company_lines) * company_lh + 40 + len(role_lines) * role_lh + (90 if detail else 0)
        y = TEXT_TOP + max((TEXT_BOTTOM - TEXT_TOP - block) // 2, 0)
        draw.text((SAFE_LEFT, y - 70), "NOW HIRING", font=_font(settings, 38, bold=True), fill=accent)
        for line in company_lines:
            draw.text((SAFE_LEFT, y), line, font=company_font, fill=accent)
            y += company_lh
        y += 40
        for line in role_lines:
            draw.text((SAFE_LEFT, y), line, font=role_font, fill="white")
            y += role_lh
        if detail:
            y += 30
            dot = 22
            draw.ellipse((SAFE_LEFT, y + 20, SAFE_LEFT + dot, y + 20 + dot), fill=accent)
            draw.text((SAFE_LEFT + dot + 22, y), detail, font=detail_font, fill=(225, 230, 240))
    else:
        start_size = 104 if is_hook else 84
        font, lines, line_height = _fit_text(draw, scene_text, settings, max_width, TEXT_BOTTOM - TEXT_TOP, start_size)
        block = len(lines) * line_height
        y = TEXT_TOP + max((TEXT_BOTTOM - TEXT_TOP - block) // 2, 0)
        if is_hook:
            # Accent bar to the left of the hook.
            draw.rounded_rectangle((SAFE_LEFT - 40, y + 8, SAFE_LEFT - 24, y + block - 18), radius=8, fill=accent)
        for line in lines:
            # Soft shadow for legibility over any background.
            draw.text((SAFE_LEFT + 4, y + 5), line, font=font, fill=(0, 0, 0, 120))
            draw.text((SAFE_LEFT, y), line, font=font, fill=accent if is_hook else "white")
            y += line_height
        if is_cta:
            y += 50
            _pill(draw, (SAFE_LEFT, y), "SAVE  •  SHARE  •  FOLLOW", _font(settings, 36, bold=True), accent, accent_text)

    handle = (settings.brand_handle or "").strip()
    if handle:
        draw.text((SAFE_LEFT, 1450), handle, font=_font(settings, 38, bold=True), fill=(255, 255, 255, 190))

    image.save(output_path)
    return output_path


def maybe_provider_background(prompt: str, output_path: Path, settings: Settings) -> Path | None:
    if not settings.hf_token or not settings.enable_video_provider:
        return None
    try:
        from app.media.hf_provider import HFProvider

        provider = HFProvider(settings)
        provider.generate_image(prompt, output_path)
        return output_path if output_path.exists() else None
    except Exception:
        return None
