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
import time
from datetime import datetime, timedelta, timezone

import requests

from app.config import Settings
from app.db import Database
from app.writing.libraries import CHATS, REDLINES

LOG = logging.getLogger(__name__)

BANNED = re.compile(
    r"studies show|research shows|statistic|guarantee|you will get (hired|the job)|#|https?://|"
    r"\b\d+\s*(%|percent) of (recruiters|students|companies|people|applicants|hiring managers|candidates|resumes)\b|"
    r"\b(google|meta|amazon|apple|microsoft|netflix|openai|nvidia|stripe|facebook|tesla)\b",
    re.I,
)
# Money and percentages read as claims everywhere except inside an example resume
# bullet ("cut load time 40%", "saved $2K a month"), where they are the point.
CLAIMS = re.compile(r"%|\$\d|percent", re.I)

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


GRADER = """You are a harsh editor for an Instagram account that gives CS students career tips.
Give each item ONE overall grade from 1 to 10. Most drafts are a 5 to 7. Be stingy:
- A tip students have heard a hundred times ("quantify your impact", "show don't tell") is 5 or below
  unless the example itself is unusually sharp.
- A hook that is a label ("How to handle feedback", "Your approach to X") instead of a line that
  makes a student stop scrolling is 6 or below.
- Anything wrong, outdated, risky to say in a real interview, or that sounds like a robot is 3 or below.
- 8 means as good as the calibration examples. 9 or 10 is rare.
Numbers inside resume bullets are example figures; that is fine."""

WEAK_EXAMPLE = {
    "redline": {
        "hook": "How to improve your resume bullets.",
        "weak": "Worked on a web app.",
        "strong": "Developed a web application using modern technologies, improving efficiency by 30%.",
        "why": "Quantify your impact.",
    },
    "chat": {
        "hook": "How to answer the weakness question.",
        "question": "What is your greatest weakness?",
        "bad": "I'm a perfectionist.",
        "good": "I sometimes take on too much, but I'm learning to prioritize and delegate tasks better.",
        "why": "Show self-awareness.",
    },
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
        "redline": {"hook": (4, 13), "weak": (2, 16), "strong": (8, 24), "why": (4, 18)},
        "chat": {"hook": (4, 13), "question": (3, 18), "bad": (1, 20), "good": (8, 38), "why": (4, 18)},
    }[kind]
    for key, (low, high) in limits.items():
        value = str(item.get(key) or "").strip()
        if not value:
            return f"missing {key}"
        if not low <= _words(value) <= high:
            return f"{key} length ({_words(value)} words)"
        if BANNED.search(value):
            return f"banned content in {key}"
        if CLAIMS.search(value) and not (kind == "redline" and key in ("weak", "strong")):
            return f"money or percent claim in {key}"
        if re.search(r"[\[\]{}<>`*_]|\bX\b|\bY\b|\.\.\.", value):
            return f"placeholder or markup in {key}"
    if kind == "redline" and not re.search(r"\d", item["strong"]):
        return "rewrite has no number"
    for hook in existing_hooks:
        if _similar(item["hook"], hook):
            return "repeat of an existing hook"
    return None


LAST_MODEL = [""]
VERTEX_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash-001", "gemini-2.5-flash-lite"]


def _vertex_express(settings: Settings, messages: list[dict], max_tokens: int) -> str:
    """Google Cloud Vertex AI 'express mode' keys (they start with "AQ.")."""

    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    # Newer Gemini models "think" first and that counts against the output limit,
    # so leave plenty of room.
    body = {"contents": contents, "generationConfig": {"temperature": 0.8, "maxOutputTokens": max(max_tokens, 8192)}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    preferred = [settings.llm_model] if settings.llm_model else []
    last_error = ""
    # Same request shape works on both Google endpoints: AI Studio (Gemini API) first,
    # then Vertex AI express mode.
    hosts = [
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent",
    ]
    for host in hosts:
        for model in preferred + [m for m in VERTEX_MODELS if m not in preferred]:
            try:
                response = requests.post(host.format(model=model), params={"key": settings.llm_api_key}, json=body, timeout=90)
            except requests.RequestException as exc:
                last_error = f"{model}: {type(exc).__name__}"
                LOG.info("Model call to %s failed: %s", host.split('/')[2], last_error)
                continue
            LOG.info("Model call %s on %s -> HTTP %s", model, host.split('/')[2], response.status_code)
            if response.status_code == 404:
                last_error = f"{model} not found"
                continue
            if response.status_code == 429 or response.status_code >= 500:
                # Busy or rate-limited: wait a moment, then try the next model.
                last_error = f"{model}: HTTP {response.status_code}"
                time.sleep(3)
                continue
            if response.status_code >= 400:
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                break  # key not valid for this host: try the next host
            candidate = (response.json().get("candidates") or [{}])[0]
            parts = (candidate.get("content") or {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
            if text.strip():
                LAST_MODEL[0] = f"{model} via {host.split('/')[2]}"
                return text
            last_error = f"{model}: empty reply ({candidate.get('finishReason')})"
    raise RuntimeError(f"Google model call failed ({last_error})")


def _chat(settings: Settings, messages: list[dict], max_tokens: int = 3000) -> str:
    key = settings.llm_api_key
    if key.startswith(("AQ.", "AIza")) or "googleapis.com" in settings.llm_base_url:
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

    reply = _chat(settings, [{"role": "user", "content": "Reply with exactly: ok"}], max_tokens=64)
    return f"{reply.strip()[:40]} (model: {LAST_MODEL[0] or settings.llm_model})"


def _as_number(value) -> float:
    """A grade from whatever shape the grader used: 8, "8/10", {"grade": 8}, {"specific": 8, ...}."""

    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("grade", "score", "overall", "total", "rating", "final"):
            for name, inner in value.items():
                if name.lower() == key:
                    return _as_number(inner)
        numbers = [float(v) for v in value.values() if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 10]
        return sum(numbers) / len(numbers) if numbers else 0.0
    if isinstance(value, list):
        numbers = [_as_number(v) for v in value]
        return sum(numbers) / len(numbers) if numbers else 0.0
    match = re.search(r"\d+(\.\d+)?", str(value))
    return float(match.group(0)) if match else 0.0


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
                stats["rejected"].append(f"{kind}: {reason} | {json.dumps(item)[:220]}")
                continue
            candidates.append(item)
        if not candidates:
            continue
        # Second opinion: grade each candidate; keep only the strong ones.
        try:
            raw_grades = _chat(
                    settings,
                    [
                        {"role": "system", "content": GRADER},
                        {
                            "role": "user",
                            "content": "Calibration, already graded:\n"
                            + json.dumps([{**examples[0], "grade": 8}, {**examples[1], "grade": 8}, {**WEAK_EXAMPLE[kind], "grade": 4}], indent=1)
                            + "\n\nNow grade these. Reply with a JSON array of integers only, one per item, same order, like [6, 8, 5].\n"
                            + json.dumps(candidates, indent=1),
                        },
                    ],
                    max_tokens=200,
                )
            grades = _json_block(raw_grades)
            if isinstance(grades, dict):
                grades = next((v for v in grades.values() if isinstance(v, list)), None)
            stats.setdefault("grader_reply", {})[kind] = re.sub(r"\s+", " ", raw_grades)[:300]
        except Exception:
            grades = None
        if isinstance(grades, list):
            grades = [_as_number(grade) for grade in grades]
        if not isinstance(grades, list) or len(grades) != len(candidates):
            stats["rejected"].append(f"{kind}: grading failed, kept nothing")
            continue
        stats.setdefault("grades", {})[kind] = grades
        kept = [(item, grade) for item, grade in zip(candidates, grades) if grade >= 8]
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
