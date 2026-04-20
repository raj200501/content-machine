"""Scene image generation for fallback reels."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.utils import ensure_directory, first_existing_file

PALETTES = [
    ("#0B1021", "#19376D", "#F8D14B"),
    ("#111827", "#0F766E", "#F97316"),
    ("#1F2937", "#2563EB", "#F43F5E"),
    ("#0F172A", "#334155", "#22C55E"),
]


def _font(settings: Settings, size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    asset_fonts = list((settings.assets_dir / "fonts").glob("*.ttf")) + list((settings.assets_dir / "fonts").glob("*.otf"))
    candidates = asset_fonts + [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    path = first_existing_file(candidates)
    if path:
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _gradient(width: int, height: int, start: str, end: str) -> Image.Image:
    image = Image.new("RGB", (width, height), start)
    draw = ImageDraw.Draw(image)
    start_rgb = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(start_rgb[i] + (end_rgb[i] - start_rgb[i]) * ratio) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def maybe_provider_background(prompt: str, output_path: Path, settings: Settings) -> Path | None:
    if not settings.hf_token:
        return None
    try:
        from app.media.hf_provider import HFProvider, ProviderFailure

        provider = HFProvider(settings)
        provider.generate_image(prompt, output_path)
        return output_path if output_path.exists() else None
    except Exception:
        return None


def build_scene_image(scene_text: str, output_path: Path, scene_index: int, settings: Settings, prompt_hint: str = "") -> Path:
    """Create a polished 1080x1920 text card scene."""

    ensure_directory(output_path.parent)
    provider_path = output_path.with_name(output_path.stem + "_provider.png")
    if prompt_hint and maybe_provider_background(prompt_hint, provider_path, settings):
        image = Image.open(provider_path).convert("RGB").resize((1080, 1920))
    else:
        start, end, accent = PALETTES[scene_index % len(PALETTES)]
        image = _gradient(1080, 1920, start, end)
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        for orb in range(4):
            radius = 220 + orb * 60
            x = 80 + orb * 190
            y = 280 + int(math.sin(scene_index + orb) * 120) + orb * 240
            draw_overlay.ellipse((x, y, x + radius, y + radius), fill=(255, 255, 255, 18))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((72, 92, 320, 142), radius=24, fill=accent)
        draw.text((106, 103), "CAREER REEL", font=_font(settings, 30, bold=True), fill="black")

    draw = ImageDraw.Draw(image)
    accent = PALETTES[scene_index % len(PALETTES)][2]
    draw.rounded_rectangle((72, 300, 1008, 1560), radius=46, fill=(8, 12, 24))
    draw.rounded_rectangle((72, 300, 1008, 1560), radius=46, outline=accent, width=6)
    wrapped = textwrap.fill(scene_text, width=18)
    draw.text((128, 420), wrapped, font=_font(settings, 74, bold=True), fill="white", spacing=18)
    draw.rounded_rectangle((128, 1460, 552, 1536), radius=28, fill=accent)
    draw.text((162, 1478), "save  |  share  |  apply", font=_font(settings, 28, bold=True), fill="black")
    draw.text((128, 1660), "content-machine", font=_font(settings, 28), fill=(220, 220, 220))
    image.save(output_path)
    return output_path
