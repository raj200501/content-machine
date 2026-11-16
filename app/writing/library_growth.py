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
import random
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


FIELDS = {
    "redline": ("hook", "weak", "strong", "why"),
    "chat": ("hook", "question", "bad", "good", "why"),
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
# Wall-clock budget for one growth run (time.monotonic() deadline). Growth runs inside
# the posting job, so it must never run long enough to delay or time out a post.
DEADLINE: list[float | None] = [None]
# Models that timed out or ran out of quota during this growth run: skip them for
# the rest of the run instead of waiting on them again.
BENCHED: set[str] = set()
GROWTH_BUDGET_SECONDS = 420


def _time_left() -> float:
    if DEADLINE[0] is None:
        return 120.0
    left = DEADLINE[0] - time.monotonic()
    if left < 25:
        raise RuntimeError("time budget used up")
    return min(120.0, left - 5)
# Used only if Google's model list can't be read. Google retires models over time,
# so the list below is a fallback; normally the live list decides.
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"]
_MODEL_CACHE: dict[str, list[str]] = {}
GEMINI_HOST = "https://generativelanguage.googleapis.com/v1beta"
SKIP_MODEL_WORDS = ("image", "tts", "audio", "live", "embedding", "vision", "robotics", "computer-use", "native", "learnlm", "gemma", "aqa")


def _model_rank(name: str) -> tuple:
    version = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    unstable = any(word in name for word in ("preview", "exp", "experimental"))
    return (
        unstable,  # stable first
        "lite" in name,  # full flash before lite
        "latest" in name,  # pinned versions before moving aliases
        -(float(version.group(1)) if version else 0.0),  # newest version first
        name,
    )


def available_models(settings: Settings) -> list[str]:
    """Flash models this key can call right now, best first (cached per run)."""

    key = settings.llm_api_key
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    names: list[str] = []
    try:
        response = requests.get(f"{GEMINI_HOST}/models", params={"key": key, "pageSize": 200}, timeout=30)
        if response.status_code < 400:
            for model in response.json().get("models", []):
                name = str(model.get("name", "")).removeprefix("models/")
                methods = model.get("supportedGenerationMethods") or []
                if "generateContent" in methods and "flash" in name and not any(word in name for word in SKIP_MODEL_WORDS):
                    names.append(name)
        LOG.info("Model list -> HTTP %s, %d usable flash models", response.status_code, len(names))
    except requests.RequestException as exc:
        LOG.info("Model list failed: %s", type(exc).__name__)
    names = sorted(set(names), key=_model_rank)[:6] or list(FALLBACK_MODELS)
    _MODEL_CACHE[key] = names
    return names


def _vertex_express(settings: Settings, messages: list[dict], max_tokens: int) -> str:
    """Google keys: Gemini API (AI Studio) first, then Vertex AI express mode."""

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
    live = available_models(settings)
    preferred = [settings.llm_model] if settings.llm_model in live or not live else []
    models = preferred + [m for m in live if m not in preferred]
    last_error = ""
    hosts = [
        f"{GEMINI_HOST}/models/{{model}}:generateContent",
        "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent",
    ]
    for host in hosts:
        host_name = host.split("/")[2]
        for model in models:
            if model in BENCHED:
                continue
            for attempt in range(2):
                try:
                    response = requests.post(host.format(model=model), params={"key": settings.llm_api_key}, json=body, timeout=_time_left())
                except requests.RequestException as exc:
                    last_error = f"{model}: {type(exc).__name__}"
                    LOG.info("Model call %s on %s failed: %s", model, host_name, type(exc).__name__)
                    if isinstance(exc, requests.Timeout):
                        BENCHED.add(model)
                    response = None
                    break
                LOG.info("Model call %s on %s -> HTTP %s", model, host_name, response.status_code)
                if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                    _time_left()
                    time.sleep(8)  # overloaded or rate-limited: one patient retry
                    continue
                break
            if response is None:
                continue
            if response.status_code == 404 or response.status_code == 429 or response.status_code >= 500:
                last_error = f"{model}: HTTP {response.status_code}"
                if response.status_code in (404, 429):
                    BENCHED.add(model)  # missing, or out of quota for now
                continue
            if response.status_code >= 400:
                last_error = f"{host_name} HTTP {response.status_code}: {response.text[:300]}"
                break  # key not valid for this host: try the next host
            candidate = (response.json().get("candidates") or [{}])[0]
            parts = (candidate.get("content") or {}).get("parts") or []
            text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
            if text.strip():
                LAST_MODEL[0] = f"{model} via {host_name}"
                return text
            last_error = f"{model}: empty reply ({candidate.get('finishReason')})"
        if host_name == "generativelanguage.googleapis.com" and last_error.startswith("gemini") and "HTTP 4" not in last_error:
            # The key works on the Gemini API but models were busy; Vertex won't help.
            break
    raise RuntimeError(f"Google model call failed ({last_error})")


def _chat(settings: Settings, messages: list[dict], max_tokens: int = 3000) -> str:
    key = settings.llm_api_key
    if key.startswith(("AQ.", "AIza")) or "googleapis.com" in settings.llm_base_url:
        return _vertex_express(settings, messages, max_tokens)
    response = requests.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": settings.llm_model, "messages": messages, "temperature": 0.8, "max_tokens": max_tokens},
        timeout=_time_left(),
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
    DEADLINE[0] = time.monotonic() + GROWTH_BUDGET_SECONDS
    BENCHED.clear()
    try:
        return _grow(db, settings, per_kind, every_days)
    finally:
        DEADLINE[0] = None
        BENCHED.clear()


def _grow(db: Database, settings: Settings, per_kind: int, every_days: int) -> dict:
    stats = {"generated": 0, "kept": 0, "rejected": []}
    if not (settings.llm_api_key and settings.llm_base_url):
        stats["skipped"] = "no LLM_API_KEY configured"
        return stats
    _ensure_table(db)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=every_days)).isoformat()
    with db.connect() as conn:
        fresh = {row[0] for row in conn.execute("SELECT DISTINCT kind FROM generated_items WHERE created_at > ?", (cutoff,))}
    due = [kind for kind in ("redline", "chat") if kind not in fresh]
    if not due:
        stats["skipped"] = "grew recently"
        return stats
    try:
        from app.publishing.trends import top_outperformers

        trending = [row["caption"].split("\n")[0][:140] for row in top_outperformers(db, limit=12, days=30)]
    except Exception:
        trending = []
    rng = random.Random(datetime.now(timezone.utc).strftime("%Y-%W"))
    for kind, library in (("redline", REDLINES), ("chat", CHATS)):
        if kind not in due:
            continue
        existing = [item["hook"] for item in library] + [item["hook"] for _key, item in generated_items(db, kind)]
        examples = rng.sample(library, min(6, len(library)))
        try:
            drafts = _draft(settings, kind, examples, trending, existing, per_kind + 6)
        except Exception as exc:
            stats["rejected"].append(f"{kind}: call failed {str(exc)[:120]}")
            continue
        candidates = _passing(kind, drafts, existing, stats)
        if not candidates:
            continue
        try:
            graded = _grade(settings, kind, examples, candidates)
        except Exception as exc:
            stats["rejected"].append(f"{kind}: grading failed {str(exc)[:120]}")
            continue
        stats.setdefault("grades", {})[kind] = [grade for grade, _fix in graded]
        stats.setdefault("notes", []).extend(
            f"{kind} {grade:.0f}: {item['hook']} | {item.get('good') or item.get('strong')} | fix: {fix}"
            for item, (grade, fix) in zip(candidates, graded)
        )
        kept = [(item, grade) for item, (grade, _fix) in zip(candidates, graded) if grade >= 8]
        # One rewrite pass for the near misses, using the editor's own notes.
        near = [(item, fix) for item, (grade, fix) in zip(candidates, graded) if 6 <= grade < 8 and fix]
        if near:
            try:
                revised = _passing(kind, _revise(settings, kind, near), existing + [i["hook"] for i, _g in kept], stats)
                if revised:
                    regraded = _grade(settings, kind, examples, revised)
                    stats["grades"][kind + "_revised"] = [grade for grade, _fix in regraded]
                    kept += [(item, grade) for item, (grade, _fix) in zip(revised, regraded) if grade >= 8]
            except Exception as exc:
                stats["rejected"].append(f"{kind}: revise failed {str(exc)[:120]}")
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


QUALITY_NOTES = {
    "redline": (
        "What makes the examples good: the weak bullet is one real students actually write; the strong "
        "bullet names a specific project, the tool, and a believable number; the hook calls out one "
        "specific mistake in plain words. Pick sharper, less obvious angles than 'quantify your impact'."
    ),
    "chat": (
        "What makes the examples good: the question is a real moment (recruiter call, technical round, "
        "offer call, career fair); the good answer is something a student can say word for word, with "
        "one concrete detail; the hook names the exact moment ('When they ask X, say this'). Skip "
        "generic advice like 'be confident' or 'research the company'."
    ),
}


def _draft(settings: Settings, kind: str, examples: list[dict], trending: list[str], existing: list[str], count: int) -> list:
    prompt = "\n".join(
        [
            f"Write {count} NEW items. {FORMAT_HELP[kind]}",
            "",
            "Examples of the quality bar (do not reuse):",
            json.dumps(examples, indent=1),
            "",
            QUALITY_NOTES[kind],
            "",
            "Posts that are getting unusual engagement in this niche right now (for topic ideas only):",
            *[f"- {caption}" for caption in trending],
            "",
            "Hooks already used (do not repeat or reword):",
            *[f"- {hook}" for hook in existing[:60]],
            "",
            "Plain text only: no markdown, no brackets, no placeholders. Reply with a JSON array of objects only.",
        ]
    )
    drafts = _json_block(_chat(settings, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]))
    return drafts if isinstance(drafts, list) else []


def _passing(kind: str, drafts: list, existing: list[str], stats: dict) -> list[dict]:
    candidates: list[dict] = []
    for draft in drafts:
        if not isinstance(draft, dict):
            continue
        fields = FIELDS[kind]
        item = {key: re.sub(r"\s+", " ", str(draft.get(key, ""))).strip() for key in fields}
        reason = check(kind, item, existing + [c["hook"] for c in candidates])
        stats["generated"] += 1
        if reason:
            stats["rejected"].append(f"{kind}: {reason} | {json.dumps(item)[:220]}")
            continue
        candidates.append(item)
    return candidates


def _grade(settings: Settings, kind: str, examples: list[dict], candidates: list[dict]) -> list[tuple[float, str]]:
    raw = _chat(
        settings,
        [
            {"role": "system", "content": GRADER},
            {
                "role": "user",
                "content": "Calibration, already graded:\n"
                + json.dumps([{**examples[0], "grade": 8}, {**examples[1], "grade": 8}, {**WEAK_EXAMPLE[kind], "grade": 4}], indent=1)
                + "\n\nNow grade these. Reply with a JSON array only, one object per item, same order: "
                '{"grade": <1-10>, "fix": "<the single change that would make it an 8 or better>"}\n'
                + json.dumps(candidates, indent=1),
            },
        ],
        max_tokens=1500,
    )
    parsed = _json_block(raw)
    if isinstance(parsed, dict):
        parsed = next((v for v in parsed.values() if isinstance(v, list)), None)
    if not isinstance(parsed, list) or len(parsed) != len(candidates):
        raise RuntimeError(f"unexpected grader reply: {re.sub(chr(10), ' ', str(raw))[:160]}")
    out = []
    for entry in parsed:
        fix = str(entry.get("fix", "")).strip() if isinstance(entry, dict) else ""
        out.append((_as_number(entry), fix))
    return out


def _revise(settings: Settings, kind: str, near: list[tuple[dict, str]]) -> list:
    prompt = "\n".join(
        [
            f"Rewrite each item, applying its editor note. Keep the same fields. {FORMAT_HELP[kind]}",
            QUALITY_NOTES[kind],
            "",
            json.dumps([{"item": item, "editor_note": fix} for item, fix in near], indent=1),
            "",
            "Plain text only. Reply with a JSON array of the rewritten items only, same order.",
        ]
    )
    revised = _json_block(_chat(settings, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]))
    return revised if isinstance(revised, list) else []
