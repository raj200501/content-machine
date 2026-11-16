"""Weekly library growth: new resume redlines and interview chats, written by a free
model, inspired by what is outperforming in the niche, checked twice before use.

Off unless an API key is configured (LLM_API_KEY secret). The default endpoint is
Google's Gemini API through its OpenAI-compatible URL, which has a free tier.
Search hacks are never generated: they must be factually exact, so they stay
hand-written.

Checks, in order:
1. Shape: exact fields, word counts, a metric in every rewritten bullet.
2. Rules: no real company names, no stats or money claims, no promises.
3. Not a repeat of any existing hook or item.
4. A second model call grades each item; only 8/10 or better is kept.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

import requests

from app.config import Settings
from app.db import Database
from app.writing.libraries import CHATS, REDLINES

LOG = logging.getLogger(__name__)

BANNED = re.compile(
    r"%(?! )|\$\d|percent|studies show|research shows|statistic|guarantee|you will get (hired|the job)|#|https?://|"
    r"\b(google|meta|amazon|apple|microsoft|netflix|openai|nvidia|stripe|facebook|tesla)\b",
    re.I,
)

SYSTEM = """You write short, specific career tips for @careerstacked, an Instagram account for CS
students hunting internships and new grad jobs. Viewers hate vague advice. Every item must be
something a student can copy today: an exact resume bullet, or exact words to say.
Never name real companies or people. No statistics, no salary numbers, no promises."""

FORMAT_HELP = {
    "redline": (
        'Resume bullet rewrites. Fields: "hook" (4-12 words, a scroll-stopping line), "weak" (the vague bullet '
        'most students write, 3-14 words), "strong" (the rewrite: action verb, what was built, a concrete number, '
        '8-22 words; numbers are example figures on an example resume), "why" (one plain reason, 5-16 words).'
    ),
    "chat": (
        'Interview moments. Fields: "hook" (4-12 words), "question" (what the interviewer or recruiter asks, '
        '3-16 words), "bad" (the answer most students give, 1-18 words), "good" (exact words that work, 8-35 '
        'words, first person), "why" (one plain reason, 5-16 words).'
    ),
}


def _words(text: str) -> int:
    return len(str(text or "").split())


def _similar(a: str, b: str) -> bool:
    left = set(re.findall(r"[a-z0-9']+", a.lower()))
    right = set(re.findall(r"[a-z0-9']+", b.lower()))
    return bool(left and right) and len(left & right) / len(left | right) >= 0.5


def check(kind: str, item: dict, existing_hooks: list[str]) -> str | None:
    """Why an item is rejected, or None if it passes the rule checks."""

    limits = {
        "redline": {"hook": (4, 12), "weak": (3, 14), "strong": (8, 22), "why": (5, 16)},
        "chat": {"hook": (4, 12), "question": (3, 16), "bad": (1, 18), "good": (8, 35), "why": (5, 16)},
    }[kind]
    for key, (low, high) in limits.items():
        value = str(item.get(key) or "").strip()
        if not value:
            return f"missing {key}"
        if not low <= _words(value) <= high:
            return f"{key} length"
        if BANNED.search(value):
            return f"banned content in {key}"
    if kind == "redline" and not re.search(r"\d", item["strong"]):
        return "rewrite has no number"
    for hook in existing_hooks:
        if _similar(item["hook"], hook):
            return "repeat of an existing hook"
    return None


VERTEX_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash-001", "gemini-2.5-flash-lite"]


def _vertex_express(settings: Settings, messages: list[dict], max_tokens: int) -> str:
    """Google Cloud Vertex AI 'express mode' keys (they start with "AQ.")."""

    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    body = {"contents": contents, "generationConfig": {"temperature": 0.8, "maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    preferred = [settings.llm_model] if settings.llm_model and "latest" not in settings.llm_model else []
    last_error = ""
    for model in preferred + VERTEX_MODELS:
        response = requests.post(
            f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent",
            params={"key": settings.llm_api_key},
            json=body,
            timeout=120,
        )
        if response.status_code == 404:
            last_error = f"{model} not found"
            continue
        if response.status_code >= 400:
            raise RuntimeError(f"Vertex HTTP {response.status_code}: {response.text[:200]}")
        parts = response.json()["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    raise RuntimeError(f"No Vertex model available ({last_error})")


def _chat(settings: Settings, messages: list[dict], max_tokens: int = 3000) -> str:
    key = settings.llm_api_key
    if key.startswith("AQ.") or "aiplatform.googleapis.com" in settings.llm_base_url:
        return _vertex_express(settings, messages, max_tokens)
    response = requests.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": settings.llm_model, "messages": messages, "temperature": 0.8, "max_tokens": max_tokens},
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    return response.json()["choices"][0]["message"]["content"]


def llm_check(settings: Settings) -> str:
    """One tiny request, to confirm the key works (prints no secrets)."""

    reply = _chat(settings, [{"role": "user", "content": "Reply with exactly: ok"}], max_tokens=10)
    return reply.strip()[:40]


def _json_block(text: str):
    match = re.search(r"[\[{].*[\]}]", text or "", re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _ensure_table(db: Database) -> None:
    with db.connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS generated_items (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   kind TEXT NOT NULL,
                   payload_json TEXT NOT NULL,
                   score REAL,
                   created_at TEXT NOT NULL,
                   active INTEGER NOT NULL DEFAULT 1
               )"""
        )


def generated_items(db: Database, kind: str) -> list[tuple[str, dict]]:
    """[(key, item)] for active generated items, key like 'g12'."""

    _ensure_table(db)
    with db.connect() as conn:
        rows = conn.execute("SELECT id, payload_json FROM generated_items WHERE kind = ? AND active = 1 ORDER BY id", (kind,)).fetchall()
    return [(f"g{row[0]}", json.loads(row[1])) for row in rows]


def grow_libraries(db: Database, settings: Settings, per_kind: int = 6, every_days: int = 7) -> dict:
    stats = {"generated": 0, "kept": 0, "rejected": []}
    if not (settings.llm_api_key and settings.llm_base_url):
        stats["skipped"] = "no LLM_API_KEY configured"
        return stats
    _ensure_table(db)
    with db.connect() as conn:
        last = conn.execute("SELECT MAX(created_at) FROM generated_items").fetchone()[0]
    if last and datetime.fromisoformat(last) > datetime.now(timezone.utc) - timedelta(days=every_days):
        stats["skipped"] = "grew recently"
        return stats
    try:
        from app.publishing.trends import top_outperformers

        trending = [row["caption"].split("\n")[0][:140] for row in top_outperformers(db, limit=12, days=30)]
    except Exception:
        trending = []
    for kind, examples in (("redline", REDLINES), ("chat", CHATS)):
        existing = [item["hook"] for item in examples] + [item["hook"] for _key, item in generated_items(db, kind)]
        prompt = "\n".join(
            [
                f"Write {per_kind + 4} NEW items. {FORMAT_HELP[kind]}",
                "",
                "Examples of the quality bar (do not reuse):",
                json.dumps(examples[:3], indent=1),
                "",
                "Posts that are getting unusual engagement in this niche right now (for topic ideas only):",
                *[f"- {caption}" for caption in trending],
                "",
                "Hooks already used (do not repeat or reword):",
                *[f"- {hook}" for hook in existing[:60]],
                "",
                "Reply with a JSON array of objects only.",
            ]
        )
        try:
            drafts = _json_block(_chat(settings, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]))
        except Exception as exc:
            stats["rejected"].append(f"{kind}: call failed {str(exc)[:120]}")
            continue
        candidates = []
        for draft in drafts if isinstance(drafts, list) else []:
            if not isinstance(draft, dict):
                continue
            item = {key: re.sub(r"\s+", " ", str(value)).strip() for key, value in draft.items() if isinstance(value, (str, int, float))}
            reason = check(kind, item, existing + [c["hook"] for c in candidates])
            stats["generated"] += 1
            if reason:
                stats["rejected"].append(f"{kind}: {reason}")
                continue
            candidates.append(item)
        if not candidates:
            continue
        # Second opinion: grade each candidate; keep only the strong ones.
        try:
            grades = _json_block(
                _chat(
                    settings,
                    [
                        {"role": "system", "content": "You are a strict editor for career advice aimed at CS students."},
                        {
                            "role": "user",
                            "content": "Grade each item 1-10 for: specific, correct, useful today, sounds like a real person, "
                            "and the hook matches the content. Reply with a JSON array of numbers only, same order.\n"
                            + json.dumps(candidates, indent=1),
                        },
                    ],
                    max_tokens=200,
                )
            )
        except Exception:
            grades = None
        if not isinstance(grades, list) or len(grades) != len(candidates):
            stats["rejected"].append(f"{kind}: grading failed, kept nothing")
            continue
        kept = [(item, float(grade)) for item, grade in zip(candidates, grades) if isinstance(grade, (int, float)) and grade >= 8]
        kept = sorted(kept, key=lambda pair: -pair[1])[:per_kind]
        now = datetime.now(timezone.utc).isoformat()
        with db.connect() as conn:
            for item, grade in kept:
                conn.execute(
                    "INSERT INTO generated_items(kind, payload_json, score, created_at) VALUES (?, ?, ?, ?)",
                    (kind, json.dumps(item), grade, now),
                )
        stats["kept"] += len(kept)
    return stats
