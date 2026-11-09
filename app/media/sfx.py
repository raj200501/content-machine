"""Generated sound effects (no samples, nothing to license).

Small, quiet effects make edited video feel produced rather than a slideshow:
a whoosh on every cut, a soft pop when something is highlighted, and light key
clicks while text is typed.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 44100


def _noise(seconds: float, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal(int(seconds * RATE)).astype(np.float32)


def _bandpass(signal: np.ndarray, low: float, high: float) -> np.ndarray:
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(signal.size, 1 / RATE)
    mask = ((freqs >= low) & (freqs <= high)).astype(np.float32)
    return np.fft.irfft(spectrum * mask, n=signal.size).astype(np.float32)


def whoosh(rng: np.random.Generator, seconds: float = 0.32) -> np.ndarray:
    n = int(seconds * RATE)
    out = np.zeros(n, dtype=np.float32)
    noise = _noise(seconds, rng)
    # Sweep a band upward through overlapping windows.
    steps = 8
    for i in range(steps):
        a, b = i * n // steps, (i + 2) * n // steps
        seg = noise[a:b]
        if seg.size < 64:
            continue
        low = 300 + 2500 * i / steps
        out[a:b] += _bandpass(seg, low, low * 2.2) * np.hanning(seg.size).astype(np.float32)
    env = np.sin(np.linspace(0, np.pi, n)).astype(np.float32) ** 1.5
    out *= env
    return out / (np.max(np.abs(out)) or 1) * 0.5


def pop(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(int(0.09 * RATE)) / RATE
    freq = 950 - 3500 * t
    tone = np.sin(2 * np.pi * np.cumsum(freq) / RATE).astype(np.float32)
    return tone * np.exp(-t * 45).astype(np.float32) * 0.45


def click(rng: np.random.Generator) -> np.ndarray:
    seconds = 0.018
    burst = _bandpass(_noise(seconds, rng), 1800 + rng.uniform(-300, 300), 7000)
    env = np.exp(-np.arange(burst.size) / RATE * 260).astype(np.float32)
    return burst * env * 0.28


SOUNDS = {"whoosh": whoosh, "pop": pop, "click": click}


def render_sfx_track(events: list[tuple[float, str]], duration: float, output_path: Path, seed: int = 0) -> Path:
    """Mix (time, sound) events into a mono WAV of the given duration."""

    rng = np.random.default_rng(seed)
    track = np.zeros(int((duration + 0.5) * RATE), dtype=np.float32)
    for start, name in events:
        sound = SOUNDS.get(name)
        if sound is None or start < 0:
            continue
        clip = sound(rng)
        begin = int(start * RATE)
        end = min(begin + clip.size, track.size)
        if begin < track.size:
            track[begin:end] += clip[: end - begin]
    track = track[: int(duration * RATE)]
    pcm = (np.clip(track, -1, 1) * 32767).astype("<i2")
    with wave.open(str(output_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())
    return output_path
