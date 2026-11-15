"""Always-on A/B tests of how reels look and sound, decided by results.

Every reel gets one value per dimension below. After insights come in, values
that earned lower skip rates and more saves/shares/likes per reach get picked
more often (a simple bandit: 25% of the time it still explores at random, so a
loser can come back if things change).
"""

from __future__ import annotations

import json
import random

from app.db import Database

DIMENSIONS: dict[str, list] = {
    "voice_speed": [1.0, 1.08],          # natural vs. a touch faster
    "caption_size": [78, 66],            # big vs. medium word-synced captions
    "music_db": [-24, -30],              # music bed level under the voice
    "job_tip": [True, False],            # job alerts: keep or drop the tip line
}
EXPLORE = 0.25


def _scores(db: Database) -> dict[str, dict[str, list[float]]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT json_extract(s.metadata_json, '$.variant') AS variant, i.reach, i.shares, i.saved, i.likes, i.skip_rate
            FROM post_insights i JOIN scripts s ON s.id = i.script_id
            WHERE json_extract(s.metadata_json, '$.variant') IS NOT NULL AND i.reach > 0
            """
        ).fetchall()
    out: dict[str, dict[str, list[float]]] = {}
    for variant_json, reach, shares, saved, likes, skip_rate in rows:
        try:
            variant = json.loads(variant_json)
        except (TypeError, ValueError):
            continue
        score = (3 * (shares or 0) + 2 * (saved or 0) + (likes or 0)) / reach + 1 - (skip_rate if skip_rate is not None else 90) / 100
        for dim, value in variant.items():
            out.setdefault(dim, {}).setdefault(json.dumps(value), []).append(score)
    return out


def choose_variant(db: Database | None, rng: random.Random) -> dict:
    scores = _scores(db) if db is not None else {}
    variant = {}
    for dim, values in DIMENSIONS.items():
        seen = scores.get(dim, {})
        if rng.random() < EXPLORE or any(len(seen.get(json.dumps(v), [])) < 3 for v in values):
            variant[dim] = rng.choice(values)
            continue
        means = {json.dumps(v): sum(seen[json.dumps(v)]) / len(seen[json.dumps(v)]) for v in values}
        best = max(values, key=lambda v: means[json.dumps(v)] + rng.random() * 0.02)
        variant[dim] = best
    return variant


def summary(db: Database) -> list[str]:
    """Human-readable lines for the weekly report."""

    lines = []
    for dim, values in _scores(db).items():
        parts = []
        for value, scores in sorted(values.items()):
            parts.append(f"{value}: {sum(scores) / len(scores):.2f} over {len(scores)} reels")
        lines.append(f"{dim} → " + "; ".join(parts))
    return lines
