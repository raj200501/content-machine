"""Natural free voiceover with word timings.

Kokoro-82M (Apache-2.0, runs locally on CPU through ONNX) is used when its model
files are present; it sounds far more natural than Piper. Each script line is
voiced separately so scene cuts land exactly on line boundaries, and word start
and end times are estimated inside each line from phoneme counts, which is
accurate enough for word-by-word captions.

If Kokoro is missing, the older engine chain in ``audio_tts`` is used and word
timings fall back to character weights.
"""

from __future__ import annotations

import logging
import re
import wave
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import Settings
from app.utils import ensure_directory

LOG = logging.getLogger(__name__)
# The phonemizer warns on harmless word-count mismatches for every line.
logging.getLogger("phonemizer").setLevel(logging.ERROR)

SAMPLE_RATE = 24000
SILENCE_THRESHOLD = 0.012
LEAD_IN_SECONDS = 0.04


@dataclass(slots=True)
class TimedWord:
    text: str
    start: float
    end: float


@dataclass(slots=True)
class TimedLine:
    text: str
    start: float  # when this line's slot begins (seconds from reel start)
    end: float  # when the next line's slot begins (includes the pause)
    speech_end: float  # when the voice stops speaking this line
    words: list[TimedWord] = field(default_factory=list)


@dataclass(slots=True)
class TimedVoiceover:
    path: Path
    duration: float
    engine: str
    lines: list[TimedLine]


def kokoro_paths(settings: Settings) -> tuple[Path, Path]:
    voices_dir = settings.assets_dir / "voices"
    model = Path(settings.kokoro_model_path) if settings.kokoro_model_path else voices_dir / "kokoro-v1.0.onnx"
    voices = Path(settings.kokoro_voices_path) if settings.kokoro_voices_path else voices_dir / "voices-v1.0.bin"
    return model.expanduser(), voices.expanduser()


def kokoro_available(settings: Settings) -> bool:
    model, voices = kokoro_paths(settings)
    if not (model.exists() and voices.exists()):
        return False
    try:
        import kokoro_onnx  # noqa: F401
    except Exception:
        return False
    return True


@lru_cache(maxsize=1)
def _load_kokoro(model_path: str, voices_path: str):
    from kokoro_onnx import Kokoro

    return Kokoro(model_path, voices_path)


_CURRENCY_WORDS = {"$": "dollars", "£": "pounds", "€": "euros"}
_UNIT_WORDS = {"/hr": " an hour", "/mo": " a month", "/yr": " a year"}
_MONEY_RANGE = re.compile(
    r"([$£€])(\d[\d,]*(?:\.\d+)?)([kK])?\s*(?:–|-|to)\s*[$£€]?(\d[\d,]*(?:\.\d+)?)([kK])?(/hr|/mo|/yr)?"
)
_MONEY_SINGLE = re.compile(r"([$£€])(\d[\d,]*(?:\.\d+)?)([kK])?(/hr|/mo|/yr)?")


def _amount(value: str) -> str:
    whole, _, cents = value.partition(".")
    return whole if not cents or int(cents) == 0 else f"{whole} dollars and {int(cents)} cents"


def _say_money(text: str) -> str:
    """'$47–$58/hr' -> '47 to 58 dollars an hour' (TTS reads '$47' as 'dollar 47')."""

    def ranged(match: re.Match) -> str:
        thousand = " thousand" if (match.group(3) or match.group(5)) else ""
        unit = _UNIT_WORDS.get(match.group(6) or "", "")
        return f"{match.group(2)} to {match.group(4)}{thousand} {_CURRENCY_WORDS[match.group(1)]}{unit}"

    def single(match: re.Match) -> str:
        thousand = " thousand" if match.group(3) else ""
        unit = _UNIT_WORDS.get(match.group(4) or "", "")
        amount = match.group(2)
        if "." in amount and not thousand and match.group(1) == "$":
            return f"{_amount(amount)}{unit}"
        return f"{amount}{thousand} {_CURRENCY_WORDS[match.group(1)]}{unit}"

    return _MONEY_SINGLE.sub(single, _MONEY_RANGE.sub(ranged, text))


def _spoken_form(text: str) -> str:
    """Small fixes so the voice reads screen text naturally."""

    value = _say_money(text)
    value = re.sub(r"\bSWE\b", "S W E", value)
    value = re.sub(r"\bML\b", "M L", value)
    value = re.sub(r"\bAI\b", "A I", value)
    value = re.sub(r"\bPM\b", "P M", value)
    value = re.sub(r"\bSRE\b", "S R E", value)
    value = re.sub(r"\bNYC\b", "New York City", value)
    value = value.replace("&", " and ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _trim(samples: np.ndarray) -> np.ndarray:
    loud = np.flatnonzero(np.abs(samples) > SILENCE_THRESHOLD)
    if loud.size == 0:
        return samples
    start = max(int(loud[0]) - int(LEAD_IN_SECONDS * SAMPLE_RATE), 0)
    end = min(int(loud[-1]) + int(0.06 * SAMPLE_RATE), samples.size)
    return samples[start:end]


def _word_weights(words: list[str], phonemize) -> list[float]:
    weights: list[float] = []
    for word in words:
        bare = re.sub(r"[^\w'$%-]", "", word)
        count = 0
        if phonemize is not None and bare:
            try:
                count = len(re.sub(r"\s", "", phonemize(bare)))
            except Exception:
                count = 0
        if count == 0:
            count = max(len(bare), 1)
        weight = float(count) + 1.5  # every word has some onset cost
        if re.search(r"[,;:]$", word):
            weight += 3.0  # the voice pauses briefly at clause marks
        elif re.search(r"[.!?]$", word):
            weight += 4.0
        weights.append(weight)
    return weights


def _time_words(text: str, start: float, speech_seconds: float, phonemize) -> list[TimedWord]:
    words = text.split()
    if not words:
        return []
    weights = _word_weights(words, phonemize)
    total = sum(weights) or 1.0
    cursor = start
    timed: list[TimedWord] = []
    for word, weight in zip(words, weights):
        span = speech_seconds * (weight / total)
        timed.append(TimedWord(word, cursor, cursor + span))
        cursor += span
    return timed


def _write_wav(path: Path, samples: np.ndarray) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").astype(np.float32) / 32767.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and data.size:
        positions = np.linspace(0, data.size - 1, int(data.size * SAMPLE_RATE / rate))
        data = np.interp(positions, np.arange(data.size), data).astype(np.float32)
    return data


def _pause_after(index: int, total: int, settings: Settings) -> float:
    if index == 0:
        return settings.voice_pause_after_hook
    if index == total - 1:
        return 0.55  # let the last line land before the loop
    return settings.voice_pause_between_lines


def _assemble(
    clips: list[np.ndarray],
    texts: list[str],
    output_path: Path,
    engine: str,
    settings: Settings,
    phonemize,
) -> TimedVoiceover:
    pieces: list[np.ndarray] = []
    lines: list[TimedLine] = []
    cursor = 0.0
    for index, (clip, text) in enumerate(zip(clips, texts)):
        speech = clip.size / SAMPLE_RATE
        pause = _pause_after(index, len(clips), settings)
        words = _time_words(text, cursor + LEAD_IN_SECONDS, max(speech - LEAD_IN_SECONDS - 0.04, 0.2), phonemize)
        lines.append(TimedLine(text=text, start=cursor, end=cursor + speech + pause, speech_end=cursor + speech, words=words))
        pieces.append(clip)
        pieces.append(np.zeros(int(pause * SAMPLE_RATE), dtype=np.float32))
        cursor += speech + pause
    audio = np.concatenate(pieces) if pieces else np.zeros(SAMPLE_RATE, dtype=np.float32)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio * (0.89 / peak)
    _write_wav(output_path, audio)
    return TimedVoiceover(path=output_path, duration=audio.size / SAMPLE_RATE, engine=engine, lines=lines)


def synthesize_timed_lines(lines: list[str], output_dir: Path, stem: str, settings: Settings) -> TimedVoiceover:
    """Voice each line and return the joined voiceover with line and word timings."""

    ensure_directory(output_dir)
    output_path = output_dir / f"{stem}.wav"
    texts = [line.strip() for line in lines if line.strip()]

    if settings.tts_engine == "silent":
        from app.media.audio_tts import _silent_fallback

        clips = []
        for index, text in enumerate(texts):
            raw = output_dir / f"{stem}_silent_{index:02d}.wav"
            _silent_fallback(text, raw, settings, min_seconds=1.6)
            clips.append(_read_wav(raw))
            raw.unlink(missing_ok=True)
        return _assemble(clips, texts, output_path, "silent", settings, None)

    if settings.tts_engine in {"auto", "kokoro"} and kokoro_available(settings):
        model, voices = kokoro_paths(settings)
        try:
            kokoro = _load_kokoro(str(model), str(voices))
            clips = []
            for text in texts:
                samples, rate = kokoro.create(
                    _spoken_form(text),
                    voice=settings.kokoro_voice,
                    speed=settings.kokoro_speed,
                    lang="en-us",
                )
                if rate != SAMPLE_RATE:
                    raise RuntimeError(f"unexpected Kokoro sample rate {rate}")
                clips.append(_trim(np.asarray(samples, dtype=np.float32)))
            tokenizer = getattr(kokoro, "tokenizer", None)
            phonemize = (lambda word: tokenizer.phonemize(word, "en-us")) if tokenizer is not None else None
            return _assemble(clips, texts, output_path, "kokoro", settings, phonemize)
        except Exception as exc:  # pragma: no cover - depends on model files.
            LOG.warning("Kokoro synthesis failed, falling back: %s", exc)
            if settings.tts_engine == "kokoro":
                raise

    # Fallback: the older local engine chain, one line at a time.
    from app.media.audio_tts import ENGINES

    clips = []
    engine_used = ""
    for index, text in enumerate(texts):
        raw = output_dir / f"{stem}_fallback_{index:02d}.wav"
        for name, engine in ENGINES:
            if engine_used == "silent" and name != "silent":
                continue
            try:
                ok = engine(text, raw, settings, min_seconds=1.6) if name == "silent" else engine(text, raw, settings)
            except Exception as exc:
                LOG.warning("TTS engine %s failed: %s", name, exc)
                ok = False
            if ok:
                engine_used = engine_used or name
                break
        else:
            raise RuntimeError("no TTS engine available")
        data = _read_wav(raw)
        raw.unlink(missing_ok=True)
        clips.append(_trim(data) if engine_used != "silent" else data)
    return _assemble(clips, texts, output_path, engine_used, settings, None)
