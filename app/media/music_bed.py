"""A soft, royalty-free music bed generated in code.

Warm chord pads with a light plucked arpeggio, mixed well under the voice. It is
synthesized from sine partials, so there is nothing to license and no risk of a
copyright claim. The progression and tempo vary with a seed so consecutive
reels do not sound identical.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 44100

# Chord progressions as semitone offsets from A2 (110 Hz). Each is a loop of 4.
PROGRESSIONS = [
    [[0, 7, 12, 15, 19], [-4, 3, 8, 12, 15], [3, 10, 15, 19, 22], [-2, 5, 10, 14, 17]],  # Am9 Fmaj7 Cmaj7 G
    [[5, 12, 17, 21, 24], [0, 7, 12, 15, 19], [3, 10, 15, 19, 22], [-2, 5, 10, 14, 17]],  # Dm9 Am7 C G
    [[-4, 3, 8, 12, 15], [3, 10, 15, 19, 22], [-2, 5, 10, 14, 17], [0, 7, 12, 15, 19]],  # F C G Am
]


def _freq(semitones: float) -> float:
    return 110.0 * (2.0 ** (semitones / 12.0))


def _envelope(length: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(length, dtype=np.float32)
    a = min(int(attack * RATE), length // 2)
    r = min(int(release * RATE), length // 2)
    if a:
        env[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32) ** 2
    if r:
        env[-r:] = np.linspace(1.0, 0.0, r, dtype=np.float32) ** 2
    return env


def _pad(chord: list[int], seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    out = np.zeros((n, 2), dtype=np.float32)
    for index, note in enumerate(chord):
        f = _freq(note)
        level = 0.16 if index == 0 else 0.1
        for detune, pan in ((0.997, 0.3), (1.003, 0.7)):
            tone = np.sin(2 * np.pi * f * detune * t) + 0.18 * np.sin(2 * np.pi * 2 * f * detune * t)
            tone *= 1.0 + 0.08 * np.sin(2 * np.pi * 0.23 * t + index)  # slow shimmer
            out[:, 0] += level * tone * (1 - pan)
            out[:, 1] += level * tone * pan
    return out * _envelope(n, attack=1.0, release=1.3)[:, None]


def _pluck(semitones: float, seconds: float) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    f = _freq(semitones + 12)
    tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t) + 0.08 * np.sin(2 * np.pi * 3 * f * t)
    decay = np.exp(-t * 6.5).astype(np.float32)
    attack = np.minimum(t / 0.004, 1.0)
    return (tone * decay * attack).astype(np.float32)


def _kick(seconds: float = 0.3) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    sweep = 45 + 85 * np.exp(-t * 28)
    phase = 2 * np.pi * np.cumsum(sweep) / RATE
    return (np.sin(phase) * np.exp(-t * 9)).astype(np.float32)


def _snare(rng: np.random.Generator, seconds: float = 0.18) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    noise = rng.standard_normal(n).astype(np.float32)
    noise = noise - np.concatenate([[0], noise[:-1]]) * 0.6  # tilt toward the top end
    body = 0.5 * np.sin(2 * np.pi * 185 * t)
    return ((0.55 * noise + body) * np.exp(-t * 22)).astype(np.float32)


def _hat(rng: np.random.Generator, seconds: float = 0.05) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    noise = rng.standard_normal(n).astype(np.float32)
    noise = noise - np.concatenate([[0], noise[:-1]])  # crude high-pass
    return (noise * np.exp(-t * 70)).astype(np.float32)


def _drums(total: int, beat: float, rng: np.random.Generator) -> np.ndarray:
    """A light pop/lo-fi groove: kick on 1 and 3, snare on 2 and 4, eighth hats."""

    out = np.zeros((total, 2), dtype=np.float32)
    kick, snare, hat = _kick(), _snare(rng), _hat(rng)

    def place(sample: np.ndarray, at: float, level: float, pan: float = 0.5) -> None:
        start = int(at * RATE)
        if start >= total:
            return
        stop = min(start + sample.size, total)
        out[start:stop, 0] += sample[: stop - start] * level * (1 - pan) * 2
        out[start:stop, 1] += sample[: stop - start] * level * pan * 2

    steps = int(total / RATE / (beat / 2)) + 1
    for step in range(steps):
        at = step * beat / 2
        in_bar = step % 8
        if in_bar in (0, 4) or (in_bar == 7 and rng.random() < 0.3):
            place(kick, at, 0.55)
        if in_bar in (2, 6):
            place(snare, at, 0.22, 0.48)
        place(hat, at + (0.012 if step % 2 else 0.0), 0.06 if step % 2 else 0.09, 0.62)
    return out


def generate_music_bed(output_path: Path, duration: float, seed: int = 0) -> Path:
    """Write a stereo WAV of the requested length."""

    rng = np.random.default_rng(seed)
    progression = PROGRESSIONS[seed % len(PROGRESSIONS)]
    bpm = float(rng.choice([120, 124, 128]))  # >120 BPM tends to hold viewers better
    beat = 60.0 / bpm
    chord_seconds = beat * 8  # two bars per chord
    total = int((duration + 1.5) * RATE)
    mix = np.zeros((total, 2), dtype=np.float32)

    position = 0
    chord_index = 0
    overlap = int(1.2 * RATE)
    while position < total:
        chord = progression[chord_index % len(progression)]
        pad = _pad(chord, chord_seconds + 1.2)
        end = min(position + pad.shape[0], total)
        mix[position:end] += pad[: end - position]
        # Light eighth-note arpeggio over the chord.
        pattern = [chord[1], chord[2], chord[3], chord[2], chord[4], chord[3], chord[2], chord[1]]
        for step in range(16):
            onset = position + int(step * beat / 2 * RATE)
            if onset >= total:
                break
            note = pattern[step % len(pattern)]
            pluck = _pluck(note, beat * 1.5) * (0.07 if step % 2 == 0 else 0.045)
            pan = 0.35 + 0.3 * ((step * 3) % 5) / 4
            stop = min(onset + pluck.size, total)
            mix[onset:stop, 0] += pluck[: stop - onset] * (1 - pan)
            mix[onset:stop, 1] += pluck[: stop - onset] * pan
        position += pad.shape[0] - overlap
        chord_index += 1

    # Gentle low-pass (smooth roll-off above ~1.8 kHz) to keep it warm and out
    # of the voice's way. Done in the frequency domain so it is fast.
    spectrum = np.fft.rfft(mix, axis=0)
    freqs = np.fft.rfftfreq(mix.shape[0], d=1.0 / RATE)
    rolloff = 1.0 / (1.0 + (freqs / 1800.0) ** 4)
    mix = np.fft.irfft(spectrum * rolloff[:, None], n=mix.shape[0], axis=0).astype(np.float32)
    # A beat under the pads gives the reel forward motion (drums start after the hook's first second).
    drums = _drums(total, beat, rng)
    drums[: int(0.9 * RATE)] *= np.linspace(0.0, 1.0, int(0.9 * RATE), dtype=np.float32)[:, None]
    peak_pads = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak_pads + drums * 0.9

    mix = mix[: int(duration * RATE)]
    fade = min(int(1.0 * RATE), mix.shape[0])
    if fade:
        mix[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
        mix[: int(0.25 * RATE)] *= np.linspace(0.0, 1.0, int(0.25 * RATE), dtype=np.float32)[:, None]
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix * (0.8 / peak)

    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    with wave.open(str(output_path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())
    return output_path
