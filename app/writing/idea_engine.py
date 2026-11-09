"""Daily idea engine: drafts fresh tip reels with a free model, steered by results.

Runs inside GitHub Actions with GitHub Models (free, rate-limited, no API key:
the workflow's own token with `models: read`). Each day it gets:

- which hooks on this account earned reach, saves and shares, and which flopped
- hooks used recently (so it never repeats itself)
- today's career and tech-hiring headlines (for timely angles)

and returns one tip script per requested category. Every draft is checked
against hard rules (length, no invented stats, no money figures, no
near-duplicates); anything that fails falls back to the hand-written packs, so
a model outage never stops posting.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import requests

from app.config import Settings
from app.writing.script_packs import SCRIPT_PACKS

LOG = logging.getLogger(__name__)

ENDPOINT = "https://models.github.ai/inference/chat/completions"

CATEGORY_BRIEFS = {
    "interview_prep": "coding, behavioral and recruiter interviews for internships and new grad roles",
    "resume_portfolio": "resumes, GitHub, portfolios and projects that get interviews",
    "application_strategy": "finding roles, applying, referrals, networking, follow-ups and offers",
    "market_context": "what is happening in early-career tech hiring and what students should do about it",
    "motivational_community": "staying consistent through rejections without burning out, with one concrete action",
}

SYSTEM = """You write scripts for @careerstacked, an Instagram account for computer science students
hunting internships and new grad jobs. Each reel is about 20 seconds: a hook line, then three short
lines that deliver the payoff, read aloud by a voiceover and typed on screen.

What wins on this account:
- Hook in under 10 words. Name a specific mistake, a surprising rule, or a promise of a script
  the viewer can steal. Make the viewer feel "that's me".
- Payoff lines are concrete and usable today: exact words to say, a bullet to rewrite,
  a step to take. No filler, no "in today's competitive market".
- Plain spoken English, like a sharp senior friend. Second person.

Hard rules (a draft that breaks one is thrown away):
- Hook: 4 to 12 words. Each payoff line: 6 to 22 words. Exactly three payoff lines.
- No percentages, no dollar amounts, no statistics, no "studies show". Do not invent facts.
- Do not name real companies or people. No hashtags, no emojis.
- Never promise results ("guaranteed", "you will get hired").
- Every idea must be new: do not reuse or reword the hooks listed as already used."""


@dataclass
class DraftPack:
    category: str
    hook: str
    beats: list[str]
    model: str


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _similar(a: str, b: str) -> bool:
    left, right = set(_words(a)), set(_words(b))
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= 0.55


BANNED = re.compile(
    r"%|\$|£|€|percent|studies|study shows|research shows|statistic|guarantee|#|https?://|"
    r"\b(google|meta|amazon|apple|microsoft|netflix|openai|nvidia|stripe)\b",
    re.I,
)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def validate(category: str, hook: str, beats: list[str], used_hooks: list[str]) -> str | None:
    """Return why a draft is rejected, or None when it is usable."""

    if len(beats) != 3:
        return "needs exactly three payoff lines"
    if not 4 <= len(hook.split()) <= 12:
        return "hook length"
    for line in [hook, *beats]:
        if BANNED.search(line) or EMOJI.search(line):
            return f"banned content: {line[:40]}"
    for beat in beats:
        if not 6 <= len(beat.split()) <= 22:
            return "payoff line length"
    for other in used_hooks:
        if _similar(hook, other):
            return f"too close to an earlier hook: {other[:40]}"
    if category not in CATEGORY_BRIEFS:
        return "unknown category"
    return None


def _tidy(line: str) -> str:
    line = re.sub(r"\s+", " ", str(line or "")).strip().strip('"').strip()
    line = line.replace("—", ", ").replace("–", "-")
    if line and line[-1] not in ".?!":
        line += "."
    return line


def _parse(content: str) -> list[dict]:
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    drafts = data.get("reels") if isinstance(data, dict) else None
    return drafts if isinstance(drafts, list) else []


def _prompt(categories: list[str], winners: list[dict], losers: list[dict], used_hooks: list[str], headlines: list[str]) -> str:
    examples = []
    for category in categories[:2]:
        pack = (SCRIPT_PACKS.get(category) or [None])[0]
        if pack:
            examples.append({"category": category, "hook": pack["hook"], "lines": pack["beats"]})
    parts = [
        "Write one new reel for each of these categories:",
        *[f"- {category}: {CATEGORY_BRIEFS.get(category, category)}" for category in categories],
        "",
        "Format example (style only, do not reuse):",
        json.dumps({"reels": examples}, indent=1),
    ]
    if winners:
        parts += ["", "Hooks that performed best on this account (learn what they have in common):"]
        parts += [f"- {row['hook']} (score {row['score']:.2f})" for row in winners]
    if losers:
        parts += ["", "Hooks that performed worst (avoid their pattern):"]
        parts += [f"- {row['hook']} (score {row['score']:.2f})" for row in losers]
    if headlines:
        parts += ["", "Today's hiring headlines, for a timely angle if one fits (never quote numbers from them):"]
        parts += [f"- {headline}" for headline in headlines[:8]]
    parts += ["", "Already used, do not repeat or reword:"]
    parts += [f"- {hook}" for hook in used_hooks[:60]]
    parts += [
        "",
        'Reply with JSON only: {"reels": [{"category": "...", "hook": "...", "lines": ["...", "...", "..."]}]}',
    ]
    return "\n".join(parts)


def _call(model: str, prompt: str, settings: Settings) -> str:
    response = requests.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 1200,
        },
        timeout=60,
    )
    kind = response.headers.get("content-type", "")
    if response.status_code >= 400 or "json" not in kind:
        raise RuntimeError(f"HTTP {response.status_code} {kind} {response.text[:240]!r}")
    return response.json()["choices"][0]["message"]["content"]


def draft_tip_packs(
    categories: list[str],
    settings: Settings,
    winners: list[dict] | None = None,
    losers: list[dict] | None = None,
    used_hooks: list[str] | None = None,
    headlines: list[str] | None = None,
) -> dict[str, DraftPack]:
    """One request per day: a fresh reel per category, validated. Empty on any failure."""

    wanted = [category for category in dict.fromkeys(categories) if category in CATEGORY_BRIEFS]
    if not wanted or not settings.idea_engine or not settings.github_token:
        return {}
    used = list(used_hooks or [])
    used += [str(pack["hook"]) for packs in SCRIPT_PACKS.values() for pack in packs]
    prompt = _prompt(wanted, winners or [], losers or [], used, headlines or [])
    for model in [m.strip() for m in settings.idea_models.split(",") if m.strip()]:
        try:
            content = _call(model, prompt, settings)
        except Exception as exc:  # rate limit, outage, model retired
            LOG.warning("Idea engine: %s unavailable (%s)", model, str(exc)[:160])
            continue
        result: dict[str, DraftPack] = {}
        for draft in _parse(content):
            category = str(draft.get("category", "")).strip()
            hook = _tidy(draft.get("hook", ""))
            beats = [_tidy(line) for line in (draft.get("lines") or []) if str(line).strip()]
            reason = validate(category, hook, beats, used)
            if reason or category in result or category not in wanted:
                LOG.info("Idea engine rejected a draft (%s): %s", reason or "duplicate category", hook[:60])
                continue
            used.append(hook)
            result[category] = DraftPack(category, hook, beats, model)
        if result:
            LOG.info("Idea engine drafted %d reels with %s", len(result), model)
            return result
    return {}
