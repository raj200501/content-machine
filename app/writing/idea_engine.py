"""Daily idea engine: drafts fresh tip reels with a free model, steered by results.

The model runs inside the GitHub Actions runner itself: a small open model
(GGUF) served by llama.cpp's llama-server, both downloaded once and cached, so
there is no account, no API key and no bill. Any OpenAI-compatible endpoint can
be used instead by setting LLM_BASE_URL (and LLM_API_KEY / LLM_MODEL).

Each day it gets:

- which hooks on this account earned reach, saves and shares, and which flopped
- hooks used recently (so it never repeats itself)
- today's career and tech-hiring headlines (for timely angles)

and returns one tip script per requested category. Every draft is checked
against hard rules (length, no invented stats, no money figures, no
near-duplicates); anything that fails falls back to the hand-written packs, so
a model problem never stops posting.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import requests

from app.config import Settings
from app.writing.script_packs import SCRIPT_PACKS

LOG = logging.getLogger(__name__)


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
    line = re.sub(r"\s*[—–]\s*", ", ", line)
    line = line.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    line = re.sub(r"\s+([,.?!])", r"\1", line)
    if line and line[-1] not in ".?!" and not (line[-1] in "'\"" and line[-2:-1] in tuple(".?!")):
        line += "."
    return line


STRONG = re.compile(r"\b(this|these|say|stop|never|instead|steal|copy|exact|before|after|ask)\b", re.I)
GENERIC = re.compile(r"\b(journey|success|passion|embrace|silence|rest|mindset|believe|dream|grind|hustle|unlock)\b", re.I)


def score(hook: str, beats: list[str]) -> float:
    """Prefer short, specific hooks and payoffs the viewer can use word for word."""

    words = len(hook.split())
    value = 2.0 - abs(words - 8) * 0.15
    value += 0.6 if STRONG.search(hook) else 0
    value += sum(0.4 for beat in beats if "'" in beat or '"' in beat or ":" in beat)
    value += sum(0.2 for beat in beats if re.match(r"^(add|cut|ask|say|send|write|pick|use|open|list|swap|start|end|replace)\b", beat, re.I))
    value -= sum(0.8 for line in [hook, *beats] if GENERIC.search(line))
    return value


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
    for category, index in (("interview_prep", 3), ("resume_portfolio", 3), ("application_strategy", 3)):
        packs = SCRIPT_PACKS.get(category) or []
        if len(packs) > index:
            examples.append({"category": category, "hook": packs[index]["hook"], "lines": packs[index]["beats"]})
    parts = [
        "Write TWO different new reels for each of these categories (different angles):",
        *[f"- {category}: {CATEGORY_BRIEFS.get(category, category)}" for category in categories],
        "",
        "Examples of the voice and format (do not reuse them):",
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
    parts += [f"- {hook}" for hook in used_hooks[:45]]
    parts += [
        "",
        'Reply with JSON only: {"reels": [{"category": "...", "hook": "...", "lines": ["...", "...", "..."]}]}',
    ]
    return "\n".join(parts)


def _call(base_url: str, model: str, prompt: str, api_key: str = "") -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        },
        timeout=600,
    )
    kind = response.headers.get("content-type", "")
    if response.status_code >= 400 or "json" not in kind:
        raise RuntimeError(f"HTTP {response.status_code} {kind} {response.text[:240]!r}")
    return response.json()["choices"][0]["message"]["content"]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _local_server(llm_dir: Path):
    """Start llama-server on the cached model; yields its base URL (or None)."""

    binary, model = llm_dir / "bin" / "llama-server", llm_dir / "model.gguf"
    if not binary.exists() or not model.exists():
        yield None
        return
    port = _free_port()
    env = {**os.environ, "LD_LIBRARY_PATH": f"{binary.parent}:{os.environ.get('LD_LIBRARY_PATH', '')}"}
    process = subprocess.Popen(
        [str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(port), "-c", "6144",
         "-t", str(os.cpu_count() or 2)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    base = f"http://127.0.0.1:{port}/v1"
    try:
        deadline = time.time() + 240
        while time.time() < deadline:
            if process.poll() is not None:
                LOG.warning("llama-server exited: %s", (process.stderr.read() or b"")[-300:].decode(errors="ignore"))
                yield None
                return
            try:
                if requests.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            yield None
            return
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


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
    if not wanted or not settings.idea_engine:
        return {}
    used = list(used_hooks or [])
    used += [str(pack["hook"]) for packs in SCRIPT_PACKS.values() for pack in packs]
    prompt = _prompt(wanted, winners or [], losers or [], used, headlines or [])
    if settings.llm_base_url:
        return _drafts_from(settings.llm_base_url, settings.llm_model, prompt, wanted, used, settings.llm_api_key)
    with _local_server(Path(settings.llm_dir)) as base:
        if not base:
            LOG.info("Idea engine: no model available, using hand-written packs")
            return {}
        return _drafts_from(base, "local", prompt, wanted, used)


def _drafts_from(base: str, model: str, prompt: str, wanted: list[str], used: list[str], api_key: str = "") -> dict[str, DraftPack]:
    for attempt in range(2):
        started = time.time()
        try:
            content = _call(base, model, prompt, api_key)
        except Exception as exc:
            LOG.warning("Idea engine call failed: %s", str(exc)[:200])
            return {}
        options: dict[str, list[tuple[float, DraftPack]]] = {}
        for draft in _parse(content):
            category = str(draft.get("category", "")).strip()
            hook = _tidy(draft.get("hook", ""))
            beats = [_tidy(line) for line in (draft.get("lines") or []) if str(line).strip()]
            reason = validate(category, hook, beats, used) or (None if category in wanted else "not asked for")
            if reason:
                LOG.info("Idea engine rejected a draft (%s): %s", reason, hook[:60])
                continue
            options.setdefault(category, []).append((score(hook, beats), DraftPack(category, hook, beats, model)))
        result: dict[str, DraftPack] = {}
        for category, scored in options.items():
            best = max(scored, key=lambda item: item[0])[1]
            used.append(best.hook)
            result[category] = best
        LOG.info("Idea engine: %d/%d drafts passed in %.0fs", len(result), len(wanted), time.time() - started)
        if result:
            return result
    return {}
