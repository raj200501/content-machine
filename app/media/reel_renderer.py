"""Frame-by-frame Reels renderer.

Design goals, from what keeps people watching short-form video:
- The first frame already shows the whole hook (no fade from black), so the
  preview and the first second both stop the scroll.
- Word-by-word captions synced to the voice, readable with the sound off.
- Something moves on every frame: drifting background, cards that slide in,
  words lighting up as they are spoken, story-style progress segments.
- Real information is the visual: job cards show company, role, location, pay
  and how fresh the posting is.
- Everything stays inside Instagram's safe zone (top header, right-side
  buttons, bottom caption area).

Frames are drawn with Pillow and piped straight into ffmpeg.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import Settings
from app.media.music_bed import generate_music_bed
from app.media.voice import TimedLine, TimedVoiceover, TimedWord, synthesize_timed_lines
from app.models import RenderArtifact
from app.utils import ensure_directory, hash_text, json_loads, run_command, slugify

LOG = logging.getLogger(__name__)

W, H = 1080, 1920
LEFT = 84
RIGHT = 996  # upper area; the caption band stays clear of the right-side buttons
CAPTION_RIGHT = 936

PALETTE = {
    "bg_top": (17, 12, 33),
    "bg_bottom": (6, 5, 12),
    "blob_a": (124, 58, 237),
    "blob_b": (37, 99, 235),
    "accent": (139, 92, 246),
    "accent_dark": (91, 33, 182),
    "highlight": (253, 224, 71),
    "text": (250, 250, 255),
    "dim": (150, 144, 182),
    "dim_hook": (186, 181, 212),
    "muted": (167, 163, 189),
    "card": (255, 255, 255),
    "card_text": (17, 14, 30),
    "card_muted": (82, 82, 100),
    "green": (22, 163, 74),
    "green_bg": (220, 252, 231),
    "chip_bg": (241, 238, 252),
}

KICKERS = {
    "openings_job_alert": "JOB DROP",
    "application_strategy": "APPLICATION TIP",
    "interview_prep": "INTERVIEW PREP",
    "resume_portfolio": "RESUME FIX",
    "market_context": "HIRING NEWS",
    "motivational_community": "REAL TALK",
}


# ---------------------------------------------------------------- fonts ----


def _font_path() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Montserrat-Variable.ttf"


@lru_cache(maxsize=64)
def font(size: int, weight: int = 800) -> ImageFont.FreeTypeFont:
    path = _font_path()
    try:
        face = ImageFont.truetype(str(path), size=size)
        try:
            face.set_variation_by_axes([weight])
        except Exception:
            pass
        return face
    except OSError:  # pragma: no cover - bundled font missing
        for fallback in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
            if Path(fallback).exists():
                return ImageFont.truetype(fallback, size=size)
        return ImageFont.load_default()


# ---------------------------------------------------------------- scenes ---


@dataclass(slots=True)
class Scene:
    kind: str  # hook | job | point | cta
    line: TimedLine
    data: dict = field(default_factory=dict)
    layer: Image.Image | None = None  # static RGBA overlay drawn once
    card: Image.Image | None = None  # job card (slides in)
    card_xy: tuple[int, int] = (0, 0)
    text_box: tuple[int, int, int, int] = (LEFT, 600, RIGHT, 1200)
    big_text: bool = True
    layout: list = field(default_factory=list)  # [(word_index, x, y)] for big text
    text_font: ImageFont.FreeTypeFont | None = None
    chunks: list = field(default_factory=list)  # caption chunks for card scenes


def plan_scenes(script_row: dict, lines: list[TimedLine]) -> list[Scene]:
    """Attach visual roles to each voiced line, using metadata.scenes if present."""

    metadata = json_loads(script_row.get("metadata_json"), default={}) or {}
    planned = metadata.get("scenes") or []
    scenes: list[Scene] = []
    for index, line in enumerate(lines):
        data = dict(planned[index]) if index < len(planned) and isinstance(planned[index], dict) else {}
        kind = data.get("kind")
        if not kind:
            kind = "hook" if index == 0 else "cta" if index == len(lines) - 1 else "point"
        scenes.append(Scene(kind=kind, line=line, data=data))
    points = [scene for scene in scenes if scene.kind == "point"]
    for number, scene in enumerate(points, start=1):
        scene.data.setdefault("number", number)
        scene.data.setdefault("total", len(points))
    jobs = [scene for scene in scenes if scene.kind == "job"]
    for number, scene in enumerate(jobs, start=1):
        scene.data.setdefault("number", number)
        scene.data.setdefault("total", len(jobs))
    return scenes


# ------------------------------------------------------------ drawing -----


def _gradient(width: int, height: int, top, bottom) -> Image.Image:
    column = Image.new("RGB", (1, height))
    for y in range(height):
        mix = y / max(height - 1, 1)
        column.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * mix) for i in range(3)))
    return column.resize((width, height))


def build_background(seed: int) -> Image.Image:
    """A large background canvas; each frame crops a slowly drifting window."""

    big_w, big_h = W + 240, H + 240
    base = _gradient(big_w, big_h, PALETTE["bg_top"], PALETTE["bg_bottom"])
    small = Image.new("RGB", (big_w // 8, big_h // 8), (0, 0, 0))
    draw = ImageDraw.Draw(small)
    sx, sy = small.size
    offset = (seed % 7) / 7
    draw.ellipse([sx * (0.55 - offset * 0.3), sy * 0.02, sx * (1.25 - offset * 0.3), sy * 0.42], fill=PALETTE["blob_a"])
    draw.ellipse([sx * (-0.35 + offset * 0.2), sy * 0.55, sx * (0.45 + offset * 0.2), sy * 1.0], fill=PALETTE["blob_b"])
    glow = small.filter(ImageFilter.GaussianBlur(radius=22)).resize((big_w, big_h), Image.BILINEAR)
    canvas = Image.blend(base, glow, 0.32)
    # Faint dot grid for texture.
    grid = ImageDraw.Draw(canvas)
    for gy in range(40, big_h, 64):
        for gx in range(40, big_w, 64):
            grid.point((gx, gy), fill=(48, 42, 72))
    return canvas


def _rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width: int = 0) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _pill(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, face, fill, text_fill, pad_x: int = 26, pad_y: int = 14) -> tuple[int, int]:
    width = int(face.getlength(text))
    ascent, descent = face.getmetrics()
    height = ascent + descent
    box = (x, y, x + width + pad_x * 2, y + height + pad_y * 2)
    _rounded(draw, box, radius=(height + pad_y * 2) // 2, fill=fill)
    draw.text((x + pad_x, y + pad_y), text, font=face, fill=text_fill)
    return box[2], box[3]


def _icon_pin(draw, x, y, size, color) -> None:
    r = size * 0.36
    cx, cy = x + size / 2, y + size * 0.38
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    draw.polygon([(cx - r * 0.78, cy + r * 0.5), (cx + r * 0.78, cy + r * 0.5), (cx, y + size * 0.98)], fill=color)
    hole = r * 0.42
    draw.ellipse([cx - hole, cy - hole, cx + hole, cy + hole], fill=PALETTE["card"])


def _icon_clock(draw, x, y, size, color) -> None:
    draw.ellipse([x + 2, y + 2, x + size - 2, y + size - 2], outline=color, width=max(size // 9, 3))
    cx, cy = x + size / 2, y + size / 2
    draw.line([(cx, cy), (cx, y + size * 0.24)], fill=color, width=max(size // 10, 3))
    draw.line([(cx, cy), (x + size * 0.72, cy)], fill=color, width=max(size // 10, 3))


def _icon_plane(draw, x, y, size, color) -> None:
    pts = [(x, y + size * 0.45), (x + size, y), (x + size * 0.62, y + size), (x + size * 0.45, y + size * 0.58)]
    draw.polygon(pts, fill=color)
    draw.line([(x + size * 0.45, y + size * 0.58), (x + size, y)], fill=PALETTE["accent_dark"], width=4)


def wrap_words(words: list[str], face, max_width: int) -> list[list[int]]:
    space = face.getlength(" ")
    lines: list[list[int]] = []
    current: list[int] = []
    width = 0.0
    for index, word in enumerate(words):
        w = face.getlength(word)
        if current and width + space + w > max_width:
            lines.append(current)
            current, width = [index], w
        else:
            width = w if not current else width + space + w
            current.append(index)
    if current:
        lines.append(current)
    return lines


def layout_big_text(words: list[str], box, start_size: int = 92, min_size: int = 58, max_lines: int = 5):
    x0, y0, x1, y1 = box
    size = start_size
    while True:
        face = font(size, 800)
        rows = wrap_words(words, face, x1 - x0)
        line_h = int(size * 1.22)
        if (len(rows) <= max_lines and len(rows) * line_h <= (y1 - y0)) or size <= min_size:
            break
        size -= 4
    total_h = len(rows) * line_h
    top = y0 + ((y1 - y0) - total_h) // 2
    space = face.getlength(" ")
    placed = []
    for row_index, row in enumerate(rows):
        row_w = sum(face.getlength(words[i]) for i in row) + space * (len(row) - 1)
        x = x0 + ((x1 - x0) - row_w) / 2
        y = top + row_index * line_h
        for i in row:
            placed.append((i, int(x), int(y)))
            x += face.getlength(words[i]) + space
    return face, placed


def caption_chunks(words: list[TimedWord], max_words: int = 4, max_chars: int = 22) -> list[list[int]]:
    chunks: list[list[int]] = []
    current: list[int] = []
    chars = 0
    for index, word in enumerate(words):
        if current and (len(current) >= max_words or chars + len(word.text) > max_chars):
            chunks.append(current)
            current, chars = [], 0
        current.append(index)
        chars += len(word.text) + 1
        if word.text[-1:] in ",.;:!?":
            chunks.append(current)
            current, chars = [], 0
    if current:
        chunks.append(current)
    return chunks


def _ease_out(value: float) -> float:
    value = min(max(value, 0.0), 1.0)
    return 1 - (1 - value) ** 3


# ------------------------------------------------------ scene layers ------


def _kicker_text(script_row: dict) -> str:
    label = KICKERS.get(script_row.get("category") or "", "CAREER TIP")
    try:
        day = date.fromisoformat(str(script_row.get("script_date", ""))[:10])
        return f"{label}  ·  {day.strftime('%b').upper()} {day.day}"
    except ValueError:
        return label


def _job_card(data: dict) -> Image.Image:
    card_w = RIGHT - LEFT
    company = str(data.get("company") or "").strip() or "Hiring now"
    role = str(data.get("role") or "").strip()
    location = str(data.get("location") or "").strip()
    pay = str(data.get("pay") or "").strip()
    posted = data.get("posted_days")
    number, total = data.get("number", 1), data.get("total", 1)

    company_face = font(108 if len(company) <= 11 else 88, 800)
    role_face = font(58, 700)
    info_face = font(46, 600)
    chip_face = font(32, 800)
    role_rows = wrap_words(role.split(), role_face, card_w - 120)[:3] if role else []

    height = 70 + 56 + 30 + 124 + len(role_rows) * 72 + 40 + 4
    info_rows = [("pin", location)] if location else []
    if pay:
        info_rows.append(("pay", pay))
    if posted is not None and int(posted) <= 21:  # an old date reads as stale; skip it
        info_rows.append(("clock", "Posted today" if int(posted) <= 0 else f"Posted {int(posted)}d ago"))
    height += 26 + len(info_rows) * 82 + 46

    card = Image.new("RGBA", (card_w, height), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (card_w, height), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([10, 18, card_w - 10, height - 2], radius=44, fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    card.alpha_composite(shadow)
    draw = ImageDraw.Draw(card)
    _rounded(draw, (0, 0, card_w, height - 20), radius=44, fill=PALETTE["card"])

    y = 54
    end_x, _ = _pill(draw, 60, y, f"{number} OF {total}", chip_face, PALETTE["accent"], (255, 255, 255), pad_x=20, pad_y=10)
    if posted is not None and int(posted) <= 7:
        _pill(draw, end_x + 14, y, "NEW", chip_face, PALETTE["green_bg"], PALETTE["green"], pad_x=20, pad_y=10)
    y += 56 + 40
    draw.text((60, y), company, font=company_face, fill=PALETTE["card_text"])
    y += 124
    for row in role_rows:
        draw.text((60, y), " ".join(role.split()[i] for i in row), font=role_face, fill=PALETTE["card_muted"])
        y += 72
    y += 30
    draw.line([(60, y), (card_w - 60, y)], fill=(232, 229, 244), width=4)
    y += 40
    for kind, text in info_rows:
        if kind == "pin":
            _icon_pin(draw, 60, y + 2, 46, PALETTE["accent"])
            draw.text((128, y), text, font=info_face, fill=PALETTE["card_text"])
        elif kind == "pay":
            _rounded(draw, (54, y - 8, 60 + 14 + int(font(48, 800).getlength(text)) + 18, y + 64), 18, PALETTE["green_bg"])
            draw.text((70, y - 2), text, font=font(48, 800), fill=PALETTE["green"])
        else:
            _icon_clock(draw, 60, y + 2, 46, PALETTE["card_muted"])
            draw.text((128, y), text, font=info_face, fill=PALETTE["card_muted"])
        y += 82
    return card


def prepare_scene(scene: Scene, script_row: dict, settings: Settings) -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    words = [word.text for word in scene.line.words]
    handle = settings.brand_handle or "@careerstacked"

    if scene.kind == "hook":
        _pill(draw, LEFT, 330, _kicker_text(script_row), font(34, 800), PALETTE["accent"], (255, 255, 255))
        companies = [str(name) for name in scene.data.get("companies", []) if name][:3]
        text_box = (LEFT, 470, RIGHT, 1180 if companies else 1300)
        scene.text_font, scene.layout = layout_big_text(words, text_box, start_size=100)
        if companies:
            face = font(40, 800)
            widths = [int(face.getlength(name)) + 52 for name in companies]
            total_w = sum(widths) + 18 * (len(widths) - 1)
            x = LEFT + ((RIGHT - LEFT) - total_w) // 2
            for name, width in zip(companies, widths):
                _pill(draw, x, 1230, name, face, (255, 255, 255), PALETTE["card_text"])
                x += width + 18
        sub = scene.data.get("sub")
        if sub:
            face = font(38, 600)
            draw.text((LEFT + ((RIGHT - LEFT) - face.getlength(sub)) / 2, 1340), sub, font=face, fill=PALETTE["muted"])
    elif scene.kind == "job":
        scene.card = _job_card(scene.data)
        scene.card_xy = (LEFT, 360)
        scene.big_text = False
        scene.chunks = caption_chunks(scene.line.words)
        card_bottom = 360 + scene.card.size[1]
        scene.text_box = (LEFT, max(card_bottom + 40, 1150), CAPTION_RIGHT, 1440)
    elif scene.kind == "cta":
        scene.text_font, scene.layout = layout_big_text(words, (LEFT, 520, RIGHT, 1080), start_size=92)
        face = font(42, 800)
        _icon_plane(draw, LEFT + 150, 1176, 58, PALETTE["highlight"])
        _pill(draw, LEFT + 230, 1160, "Send to a friend", face, (255, 255, 255), PALETTE["card_text"])
        handle_face = font(40, 700)
        label = f"Follow {handle} for daily drops"
        draw.text((LEFT + ((RIGHT - LEFT) - handle_face.getlength(label)) / 2, 1300), label, font=handle_face, fill=PALETTE["muted"])
    else:  # point
        number = scene.data.get("number", 1)
        total = scene.data.get("total", 1)
        label = scene.data.get("label") or (f"STEP {number} OF {total}" if total > 1 else "THE FIX")
        _pill(draw, LEFT, 330, label, font(34, 800), (255, 255, 255), PALETTE["card_text"])
        scene.text_font, scene.layout = layout_big_text(words, (LEFT, 460, RIGHT, 1380), start_size=88)
    scene.layer = layer


# ------------------------------------------------------------- frames -----


def _draw_progress(draw: ImageDraw.ImageDraw, scenes: list[Scene], t: float) -> None:
    count = len(scenes)
    gap = 12
    width = (RIGHT - LEFT - gap * (count - 1)) / count
    y = 232
    for index, scene in enumerate(scenes):
        x = LEFT + index * (width + gap)
        _rounded(draw, (x, y, x + width, y + 8), 4, (70, 64, 92))
        if t >= scene.line.end:
            fill = 1.0
        elif t <= scene.line.start:
            fill = 0.0
        else:
            fill = (t - scene.line.start) / max(scene.line.end - scene.line.start, 0.01)
        if fill > 0:
            _rounded(draw, (x, y, x + max(width * fill, 8), y + 8), 4, PALETTE["text"])


def _active_index(words: list[TimedWord], t: float) -> int:
    active = -1
    for index, word in enumerate(words):
        if t >= word.start:
            active = index
    return active


def _draw_big_text(draw: ImageDraw.ImageDraw, scene: Scene, t: float) -> None:
    words = scene.line.words
    face = scene.text_font
    if face is None:
        return
    active = _active_index(words, t)
    if t >= scene.line.speech_end:
        active = len(words)  # everything lit once the line is spoken
    ascent, descent = face.getmetrics()
    for index, x, y in scene.layout:
        text = words[index].text
        if index == active and index < len(words):
            progress = _ease_out((t - words[index].start) / 0.09)
            pad = 10
            w = face.getlength(text)
            grow = 0.86 + 0.14 * progress
            cx, cy = x + w / 2, y + (ascent + descent) / 2 + 4
            hw, hh = (w / 2 + pad) * grow, ((ascent + descent) / 2 + 4) * grow
            _rounded(draw, (cx - hw, cy - hh, cx + hw, cy + hh), 16, PALETTE["accent"])
            draw.text((x, y), text, font=face, fill=PALETTE["text"])
        elif index < active or active >= len(words):
            draw.text((x, y), text, font=face, fill=PALETTE["text"])
        else:
            # Unspoken words stay readable so the first frame already shows the hook.
            draw.text((x, y), text, font=face, fill=PALETTE["dim_hook"] if scene.kind == "hook" else PALETTE["dim"])


def _draw_caption_chunk(draw: ImageDraw.ImageDraw, scene: Scene, t: float) -> None:
    words = scene.line.words
    if not words or not scene.chunks:
        return
    active = max(_active_index(words, t), 0)
    chunk = next((c for c in scene.chunks if active in c), scene.chunks[-1])
    face = font(66, 800)
    x0, y0, x1, y1 = scene.text_box
    texts = [words[i].text for i in chunk]
    rows = wrap_words(texts, face, x1 - x0)
    line_h = 84
    top = y0 + ((y1 - y0) - len(rows) * line_h) // 2
    space = face.getlength(" ")
    for row_index, row in enumerate(rows):
        row_w = sum(face.getlength(texts[i]) for i in row) + space * (len(row) - 1)
        x = x0 + ((x1 - x0) - row_w) / 2
        y = top + row_index * line_h
        for i in row:
            word_index = chunk[i]
            color = PALETTE["highlight"] if word_index == active else PALETTE["text"] if word_index < active else (205, 202, 222)
            draw.text((x, y), texts[i], font=face, fill=color, stroke_width=5, stroke_fill=(10, 8, 20))
            x += face.getlength(texts[i]) + space


def render_frame(background: Image.Image, scenes: list[Scene], scene: Scene, t: float) -> Image.Image:
    dx = 120 + 90 * math.sin(2 * math.pi * t / 15.0)
    dy = 120 + 90 * math.cos(2 * math.pi * t / 19.0)
    frame = background.crop((int(dx), int(dy), int(dx) + W, int(dy) + H)).convert("RGBA")
    if scene.layer is not None:
        frame.alpha_composite(scene.layer)
    if scene.card is not None:
        progress = _ease_out((t - scene.line.start) / 0.32)
        x, y = scene.card_xy
        offset = int((1 - progress) * 90)
        if progress >= 1:
            frame.alpha_composite(scene.card, (x, y))
        else:
            faded = scene.card.copy()
            alpha = faded.getchannel("A").point(lambda value: int(value * progress))
            faded.putalpha(alpha)
            frame.alpha_composite(faded, (x, y + offset))
    draw = ImageDraw.Draw(frame)
    _draw_progress(draw, scenes, t)
    if scene.big_text:
        _draw_big_text(draw, scene, t)
    else:
        _draw_caption_chunk(draw, scene, t)
    return frame.convert("RGB")


# ------------------------------------------------------------- audio ------


def mix_audio(settings: Settings, voice: TimedVoiceover, work_dir: Path, seed: int) -> Path:
    mixed = work_dir / "mix.m4a"
    inputs = ["-i", str(voice.path)]
    if settings.music_bed:
        bed = generate_music_bed(work_dir / "music_bed.wav", voice.duration + 0.5, seed=seed)
        inputs += ["-i", str(bed)]
        graph = (
            "[0:a]aresample=44100,pan=stereo|c0=c0|c1=c0,asplit=2[v1][v2];"
            f"[1:a]volume={settings.music_bed_volume_db}dB[m];"
            "[m][v2]sidechaincompress=threshold=0.03:ratio=5:attack=15:release=350[md];"
            "[v1][md]amix=inputs=2:duration=first:normalize=0,"
            "loudnorm=I=-14:TP=-1.5:LRA=11[out]"
        )
    else:
        graph = "[0:a]aresample=44100,pan=stereo|c0=c0|c1=c0,loudnorm=I=-14:TP=-1.5:LRA=11[out]"
    run_command(
        [settings.ffmpeg_binary, "-y", *inputs, "-filter_complex", graph, "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(mixed)]
    )
    return mixed


def write_word_srt(lines: list[TimedLine], path: Path) -> Path:
    def stamp(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    blocks = []
    counter = 1
    for line in lines:
        for chunk in caption_chunks(line.words):
            start = line.words[chunk[0]].start
            end = line.words[chunk[-1]].end
            text = " ".join(line.words[i].text for i in chunk)
            blocks.append(f"{counter}\n{stamp(start)} --> {stamp(end)}\n{text}\n")
            counter += 1
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


# ------------------------------------------------------------- entry ------


def render_reel(settings: Settings, script_row: dict, output_root: Path) -> RenderArtifact:
    script_text = script_row["full_script"]
    slug = slugify(f"{script_row['id']}-{hash_text(script_text)[:10]}")
    work_dir = ensure_directory(output_root / slug)
    final_path = output_root / f"{slug}.mp4"
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    seed = int(hash_text(script_text)[:8], 16)

    voice = synthesize_timed_lines(lines, work_dir, "voiceover", settings)
    scenes = plan_scenes(script_row, voice.lines)
    for scene in scenes:
        prepare_scene(scene, script_row, settings)
    background = build_background(seed)
    audio = mix_audio(settings, voice, work_dir, seed)
    subtitles = write_word_srt(voice.lines, work_dir / "captions.srt")

    fps = settings.render_fps
    total_frames = int(math.ceil(voice.duration * fps))
    command = [
        settings.ffmpeg_binary,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-i",
        str(audio),
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-c:a",
        "copy",
        "-shortest",
        "-movflags",
        "+faststart",
        str(final_path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    scene_index = 0
    try:
        for frame_number in range(total_frames):
            t = frame_number / fps
            while scene_index < len(scenes) - 1 and t >= scenes[scene_index].line.end:
                scene_index += 1
            frame = render_frame(background, scenes, scenes[scene_index], t)
            assert process.stdin is not None
            process.stdin.write(frame.tobytes())
    finally:
        if process.stdin:
            process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", "ignore") if process.stderr else ""
        code = process.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg encode failed: {stderr[-800:]}")

    hook_end = scenes[0].line.speech_end if scenes else 1.0
    return RenderArtifact(
        script_id=script_row["id"],
        provider="local_reel",
        video_path=final_path,
        audio_path=voice.path,
        subtitle_path=subtitles,
        duration_seconds=voice.duration,
        metadata={
            "tts_engine": voice.engine,
            "work_dir": str(work_dir),
            "thumb_offset_ms": int(max(hook_end - 0.05, 0.2) * 1000),
            "scenes": [scene.kind for scene in scenes],
        },
        fallback_used=True,
    )


# ----------------------------------------------------------- carousel -----

SLIDE_W, SLIDE_H = 1080, 1350  # 4:5, the tallest feed format


def _slide_base(seed: int) -> Image.Image:
    background = build_background(seed)
    return background.crop((120, 300, 120 + SLIDE_W, 300 + SLIDE_H)).convert("RGBA")


def _centered(draw: ImageDraw.ImageDraw, y: int, text: str, face, fill) -> None:
    draw.text(((SLIDE_W - face.getlength(text)) / 2, y), text, font=face, fill=fill)


def _slide_footer(draw: ImageDraw.ImageDraw, index: int, total: int, handle: str) -> None:
    face = font(30, 700)
    draw.text((LEFT, SLIDE_H - 96), handle, font=face, fill=PALETTE["muted"])
    label = f"{index}/{total}"
    draw.text((SLIDE_W - LEFT - face.getlength(label), SLIDE_H - 96), label, font=face, fill=PALETTE["muted"])


def render_carousel(settings: Settings, script_row: dict, output_root: Path) -> RenderArtifact:
    metadata = json_loads(script_row.get("metadata_json"), default={}) or {}
    scenes = [scene for scene in metadata.get("scenes", []) if isinstance(scene, dict)]
    jobs = [scene for scene in scenes if scene.get("kind") == "job"][:8]
    cover = next((scene for scene in scenes if scene.get("kind") == "roundup_cover"), {})
    handle = settings.brand_handle or "@careerstacked"
    slug = slugify(f"{script_row['id']}-{hash_text(script_row['full_script'])[:10]}")
    work_dir = ensure_directory(output_root / slug)
    seed = int(hash_text(script_row["full_script"])[:8], 16)
    total = len(jobs) + 2
    paths: list[Path] = []

    # Cover slide.
    slide = _slide_base(seed)
    draw = ImageDraw.Draw(slide)
    _pill(draw, LEFT, 120, _kicker_text({**script_row, "category": "openings_job_alert"}).replace("JOB DROP", "SAVE THIS"), font(34, 800), PALETTE["accent"], (255, 255, 255))
    title = f"{len(jobs)} tech {cover.get('roles', 'roles')} open right now"
    face, placed = layout_big_text(title.split(), (LEFT, 260, RIGHT, 760), start_size=112, min_size=70, max_lines=4)
    words = title.split()
    for index, x, y in placed:
        color = PALETTE["highlight"] if index == 0 else PALETTE["text"]
        draw.text((x, y), words[index], font=face, fill=color)
    chip_face = font(36, 800)
    x, y = LEFT, 820
    for name in cover.get("companies", [])[:8]:
        width = int(chip_face.getlength(name)) + 52
        if x + width > RIGHT:
            x, y = LEFT, y + 84
        if y > 1080:
            break
        _pill(draw, x, y, name, chip_face, (255, 255, 255), PALETTE["card_text"])
        x += width + 16
    _centered(draw, 1160, "Swipe for pay, location and role  →", font(38, 700), PALETTE["muted"])
    _slide_footer(draw, 1, total, handle)
    paths.append(work_dir / "slide_01.jpg")
    slide.convert("RGB").save(paths[-1], "JPEG", quality=92)

    # One job per slide.
    for number, job in enumerate(jobs, start=1):
        slide = _slide_base(seed + number)
        draw = ImageDraw.Draw(slide)
        card = _job_card({**job, "number": number, "total": len(jobs)})
        y = max((SLIDE_H - card.size[1]) // 2 - 40, 120)
        slide.alpha_composite(card, (LEFT, y))
        tip = "Search this exact title on their careers page"
        _centered(draw, min(y + card.size[1] + 30, SLIDE_H - 200), tip, font(34, 700), PALETTE["muted"])
        _slide_footer(draw, number + 1, total, handle)
        paths.append(work_dir / f"slide_{number + 1:02d}.jpg")
        slide.convert("RGB").save(paths[-1], "JPEG", quality=92)

    # Closing slide.
    slide = _slide_base(seed + 99)
    draw = ImageDraw.Draw(slide)
    lines = ["Save this for later.", "Send it to a friend", "who's applying."]
    for row, text in enumerate(lines):
        _centered(draw, 360 + row * 120, text, font(84, 800), PALETTE["text"] if row else PALETTE["highlight"])
    _icon_plane(draw, SLIDE_W // 2 - 260, 790, 58, PALETTE["highlight"])
    _pill(draw, SLIDE_W // 2 - 180, 774, "New roles every day", font(42, 800), (255, 255, 255), PALETTE["card_text"])
    _centered(draw, 920, f"Follow {handle}", font(44, 700), PALETTE["muted"])
    _slide_footer(draw, total, total, handle)
    paths.append(work_dir / f"slide_{total:02d}.jpg")
    slide.convert("RGB").save(paths[-1], "JPEG", quality=92)

    manifest = work_dir / "carousel.json"
    manifest.write_text(json.dumps({"slides": [str(path) for path in paths]}), encoding="utf-8")
    return RenderArtifact(
        script_id=script_row["id"],
        provider="local_carousel",
        video_path=manifest,
        audio_path=manifest,
        subtitle_path=manifest,
        duration_seconds=0.0,
        metadata={"format": "carousel", "slides": [str(path) for path in paths], "work_dir": str(work_dir)},
        fallback_used=True,
    )
