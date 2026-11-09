""""Typing in a notes app" format for tip reels.

Looks like a phone screen recording: the hook is the note's title (fully
visible on the first frame), then each point is typed out in sync with the
voice, with a blinking cursor, keyboard key presses and soft key clicks. One
continuous shot, no slide changes.

The look is a generic notes app (no product names or logos).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageDraw

from app.media.reel_renderer import font
from app.media.voice import TimedLine, TimedWord

W, H = 1080, 1920
PAPER = (251, 251, 248)
INK = (28, 28, 30)
GREY = (142, 142, 147)
ACCENT = (224, 164, 0)
MARKER = (255, 226, 102)
KEYBOARD_BG = (209, 211, 217)
KEY = (255, 255, 255)
KEY_DOWN = (170, 174, 184)
KEYBOARD_TOP = 1270
TEXT_LEFT, TEXT_RIGHT = 72, 1008
VIEW_TOP, VIEW_BOTTOM = 330, KEYBOARD_TOP - 40

ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]


@dataclass(slots=True)
class PlacedWord:
    word: TimedWord
    x: int
    y: int  # in document coordinates
    size: int
    weight: int
    color: tuple[int, int, int]
    marker: bool


def _status_bar(draw: ImageDraw.ImageDraw, clock: str) -> None:
    draw.text((84, 52), clock, font=font(42, 700), fill=INK)
    # signal bars
    for i in range(4):
        h = 12 + i * 7
        draw.rounded_rectangle([820 + i * 15, 92 - h, 830 + i * 15, 92], radius=2, fill=INK)
    # wifi (three arcs)
    for r in (30, 20, 10):
        draw.arc([895 - r, 92 - r, 895 + r, 92 + r], start=225, end=315, fill=INK, width=6)
    # battery
    draw.rounded_rectangle([940, 64, 1000, 94], radius=8, outline=INK, width=3)
    draw.rounded_rectangle([946, 70, 984, 88], radius=4, fill=INK)
    draw.rectangle([1002, 74, 1007, 84], fill=INK)


def _nav_bar(draw: ImageDraw.ImageDraw) -> None:
    face = font(46, 600)
    draw.line([(92, 186), (76, 204), (92, 222)], fill=ACCENT, width=7, joint="curve")
    draw.text((110, 178), "Notes", font=face, fill=ACCENT)
    # share icon
    draw.rounded_rectangle([858, 190, 898, 236], radius=6, outline=ACCENT, width=5)
    draw.rectangle([870, 182, 886, 196], fill=PAPER)
    draw.line([(878, 168), (878, 214)], fill=ACCENT, width=5)
    draw.line([(864, 182), (878, 168), (892, 182)], fill=ACCENT, width=5)
    # more icon
    draw.ellipse([930, 180, 990, 240], outline=ACCENT, width=5)
    for dx in (-14, 0, 14):
        draw.ellipse([960 + dx - 4, 206, 960 + dx + 4, 214], fill=ACCENT)


def _keyboard(pressed: str | None) -> Image.Image:
    board = Image.new("RGB", (W, H - KEYBOARD_TOP), KEYBOARD_BG)
    draw = ImageDraw.Draw(board)
    # suggestion strip
    draw.line([(360, 30), (360, 90)], fill=(170, 172, 180), width=2)
    draw.line([(720, 30), (720, 90)], fill=(170, 172, 180), width=2)
    key_face = font(46, 500)
    key_w, key_h, gap = 92, 128, 14
    top = 130
    for row_index, row in enumerate(ROWS):
        total = len(row) * key_w + (len(row) - 1) * gap
        x = (W - total) // 2
        y = top + row_index * (key_h + 26)
        for letter in row:
            down = pressed == letter
            draw.rounded_rectangle([x, y, x + key_w, y + key_h], radius=14, fill=KEY_DOWN if down else KEY)
            draw.text((x + key_w / 2 - key_face.getlength(letter) / 2, y + 34), letter, font=key_face, fill=INK)
            x += key_w + gap
    y = top + 3 * (key_h + 26)
    draw.rounded_rectangle([20, y, 230, y + key_h], radius=14, fill=(171, 176, 188))
    draw.text((70, y + 38), "123", font=font(40, 500), fill=INK)
    draw.rounded_rectangle([250, y, 830, y + key_h], radius=14, fill=KEY_DOWN if pressed == " " else KEY)
    draw.text((470, y + 38), "space", font=font(40, 500), fill=INK)
    draw.rounded_rectangle([850, y, 1060, y + key_h], radius=14, fill=(171, 176, 188))
    draw.text((892, y + 38), "return", font=font(40, 500), fill=INK)
    return board


def _layout(title_line: TimedLine, body: list[TimedLine]) -> tuple[list[PlacedWord], list[PlacedWord], int]:
    title_words: list[PlacedWord] = []
    face = font(70, 800)
    space = face.getlength(" ")
    x, y = TEXT_LEFT, 0
    for word in title_line.words:
        width = face.getlength(word.text)
        if x > TEXT_LEFT and x + width > TEXT_RIGHT:
            x, y = TEXT_LEFT, y + 88
        title_words.append(PlacedWord(word, int(x), y, 70, 800, INK, False))
        x += width + space
    y += 88 + 44

    body_words: list[PlacedWord] = []
    for index, line in enumerate(body):
        last = index == len(body) - 1
        size, weight = (54, 700) if last else (54, 500)
        color = ACCENT if last else INK
        face = font(size, weight)
        space = face.getlength(" ")
        indent = TEXT_LEFT if last else TEXT_LEFT + 52
        x = indent
        if not last:
            body_words.append(PlacedWord(TimedWord("•", line.start, line.start), TEXT_LEFT + 6, y, size, 800, ACCENT, False))
        for word in line.words:
            width = face.getlength(word.text)
            if x > indent and x + width > TEXT_RIGHT:
                x, y = indent, y + 74
            marker = bool(re.search(r"[$£€]|\d", word.text))
            body_words.append(PlacedWord(word, int(x), y, size, weight, color, marker))
            x += width + space
        y += 74 + 34
    return title_words, body_words, y


def _typed(word: TimedWord, t: float) -> str:
    if t >= word.end or word.end <= word.start:
        return word.text if t >= word.start else ""
    if t < word.start:
        return ""
    share = (t - word.start) / (word.end - word.start)
    return word.text[: max(1, math.ceil(len(word.text) * min(share * 1.4, 1.0)))]


def typing_events(body_words: list[PlacedWord]) -> list[tuple[float, str]]:
    events: list[tuple[float, str]] = []
    for placed in body_words:
        word = placed.word
        if word.text == "•":
            continue
        count = max(len(word.text), 1)
        span = max((word.end - word.start) / 1.4, 0.05)
        for i in range(count):
            if i % 2 == 0:  # a click every other character keeps it subtle
                events.append((word.start + span * i / count, "click"))
        if placed.marker:
            events.append((word.end, "pop"))
    return events


class NotesScene:
    def __init__(self, lines: list[TimedLine], when: datetime | None = None) -> None:
        self.lines = lines
        when = when or datetime.now()
        self.clock = when.strftime("%-I:%M")
        self.date_line = when.strftime("%B %-d, %Y at %-I:%M %p")
        self.title, self.body, self.doc_height = _layout(lines[0], lines[1:])
        self.base = Image.new("RGB", (W, H), PAPER)
        draw = ImageDraw.Draw(self.base)
        _status_bar(draw, self.clock)
        _nav_bar(draw)
        face = font(34, 500)
        draw.text(((W - face.getlength(self.date_line)) / 2, 268), self.date_line, font=face, fill=GREY)
        self.keyboards = {key: _keyboard(key) for key in [None, " ", *"".join(ROWS)]}
        # Header (status bar, nav, date) is repainted over scrolled text.
        self.header = self.base.crop((0, 0, W, VIEW_TOP - 18))

    def events(self) -> list[tuple[float, str]]:
        return typing_events(self.body)

    def frame(self, t: float, total: float) -> Image.Image:
        frame = self.base.copy()
        draw = ImageDraw.Draw(frame)
        # Where is the cursor?
        cursor_word = None
        for placed in self.body:
            if placed.word.text != "•" and t >= placed.word.start:
                cursor_word = placed
        cursor_y = cursor_word.y if cursor_word else 0
        # Keep the line being typed in the upper-middle of the note, scrolling smoothly.
        scroll = max(0, cursor_y - (VIEW_BOTTOM - VIEW_TOP - 320))
        top = VIEW_TOP - scroll

        for placed in self.title:  # the hook is fully visible from frame one
            y = top + placed.y
            if VIEW_TOP - 100 < y < VIEW_BOTTOM:
                draw.text((placed.x, y), placed.word.text, font=font(placed.size, placed.weight), fill=placed.color)

        pressed = None
        cursor_xy = None
        for placed in self.body:
            text = placed.word.text if placed.word.text == "•" else _typed(placed.word, t)
            if placed.word.text == "•" and t < placed.word.start:
                continue
            if not text:
                continue
            y = top + placed.y
            face = font(placed.size, placed.weight)
            if not (VIEW_TOP - 100 < y < VIEW_BOTTOM):
                continue
            if placed.marker and text == placed.word.text:
                width = face.getlength(text)
                draw.rounded_rectangle([placed.x - 6, y + 6, placed.x + width + 6, y + placed.size + 14], radius=8, fill=MARKER)
            draw.text((placed.x, y), text, font=face, fill=placed.color)
            if placed is cursor_word or (cursor_word is not None and placed.word is cursor_word.word):
                cursor_xy = (placed.x + face.getlength(text) + 4, y)
                if text != placed.word.text:
                    letter = text[-1].lower()
                    pressed = letter if letter in "".join(ROWS) else None
                elif t - placed.word.end < 0.08:
                    pressed = " "

        if cursor_xy is None:
            last_title = self.title[-1] if self.title else None
            if last_title:
                cursor_xy = (last_title.x + font(70, 800).getlength(last_title.word.text) + 6, top + last_title.y)
        if cursor_xy and (t * 2) % 2 < 1.3:
            x, y = cursor_xy
            draw.rounded_rectangle([x, y + 4, x + 5, y + 66], radius=2, fill=ACCENT)

        frame.paste(self.header, (0, 0))
        if scroll > 0:
            draw.line([(0, VIEW_TOP - 18), (W, VIEW_TOP - 18)], fill=(228, 228, 232), width=2)
        frame.paste(self.keyboards.get(pressed, self.keyboards[None]), (0, KEYBOARD_TOP))
        # Very slow push-in over the whole clip, like a phone held closer.
        zoom = 1.0 + 0.035 * min(t / max(total, 1), 1)
        if zoom > 1.001:
            big = frame.resize((int(W * zoom), int(H * zoom)), Image.BILINEAR)
            left = (big.size[0] - W) // 2
            frame = big.crop((left, 0, left + W, H))
        return frame
