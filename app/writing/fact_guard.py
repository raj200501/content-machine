"""Lightweight evidence guard for generated scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass


STRICT_PATTERNS = [
    re.compile(r"\b\d{1,4}\b"),
    re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", re.I),
    re.compile(r"\bdeadline|closing date|apply by|hiring freeze\b", re.I),
]


@dataclass(slots=True)
class GuardedClaim:
    claim_text: str
    supported: bool
    evidence: list[dict]


@dataclass(slots=True)
class GuardedScript:
    script_text: str
    claims: list[GuardedClaim]
    passed: bool


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+-]+", value.lower())
        if token not in {"this", "that", "with", "from", "your", "have", "about", "there", "their"}
    }


def _needs_strict_support(claim: str) -> bool:
    return any(pattern.search(claim) for pattern in STRICT_PATTERNS)


def _supporting_evidence(claim: str, evidence_items: list[dict]) -> tuple[bool, list[dict]]:
    claim_tokens = _tokens(claim)
    matches: list[dict] = []
    for item in evidence_items:
        evidence_text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('text_content', '')[:400]}"
        overlap = claim_tokens & _tokens(evidence_text)
        if claim_tokens and len(overlap) / max(len(claim_tokens), 1) >= 0.22:
            matches.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("source_url", ""),
                    "overlap": sorted(overlap)[:10],
                }
            )
    supported = bool(matches) if _needs_strict_support(claim) else bool(matches) or len(claim_tokens) <= 5
    return supported, matches[:3]


def _soften(claim: str) -> str:
    softened = re.sub(r"\b\d{1,4}\b", "recent", claim)
    softened = re.sub(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}\b",
        "soon",
        softened,
        flags=re.I,
    )
    softened = re.sub(r"\bdeadline|apply by|closing date\b", "posted timing", softened, flags=re.I)
    softened = re.sub(r"\s+", " ", softened).strip()
    return softened


def guard_script(script_text: str, evidence_items: list[dict]) -> GuardedScript:
    claims: list[GuardedClaim] = []
    rewritten_lines: list[str] = []
    passed = True

    for raw_line in [line.strip() for line in script_text.splitlines() if line.strip()]:
        supported, evidence = _supporting_evidence(raw_line, evidence_items)
        claim_text = raw_line if supported else _soften(raw_line)
        claims.append(GuardedClaim(claim_text=claim_text, supported=supported, evidence=evidence))
        rewritten_lines.append(claim_text)
        if _needs_strict_support(raw_line) and not supported:
            passed = False

    return GuardedScript(script_text="\n".join(rewritten_lines), claims=claims, passed=passed)
