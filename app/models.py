"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SourceDefinition:
    name: str
    source_type: str
    url: str = ""
    enabled: bool = True
    category: str = ""
    description: str = ""
    max_items: int = 20
    board_type: str = ""
    channel_id: str = ""
    fetch_article: bool = True
    tags: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceDefinition":
        reserved = {
            "name",
            "source_type",
            "url",
            "enabled",
            "category",
            "description",
            "max_items",
            "board_type",
            "channel_id",
            "fetch_article",
            "tags",
            "filters",
        }
        metadata = {key: value for key, value in payload.items() if key not in reserved}
        return cls(
            name=payload["name"],
            source_type=payload["source_type"],
            url=payload.get("url", ""),
            enabled=payload.get("enabled", True),
            category=payload.get("category", ""),
            description=payload.get("description", ""),
            max_items=int(payload.get("max_items", 20)),
            board_type=payload.get("board_type", ""),
            channel_id=payload.get("channel_id", ""),
            fetch_article=payload.get("fetch_article", True),
            tags=list(payload.get("tags", [])),
            filters=list(payload.get("filters", [])),
            metadata=metadata,
        )


@dataclass(slots=True)
class SourceItemCandidate:
    source_type: str
    source_url: str
    title: str
    published_at: str | None
    fetched_at: str
    text_content: str
    summary: str
    extracted_entities: list[str]
    extracted_roles: list[str]
    freshness_score: float
    relevance_score: float
    duplicate_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlannedTopic:
    day: str
    slot_index: int
    scheduled_at: str
    category: str
    hook_style: str
    title: str
    angle: str
    company: str
    source_item_ids: list[int]
    freshness_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CaptionPackage:
    caption: str
    hashtags: list[str]
    cta: str
    source_notes: str
    compliance_notes: str


@dataclass(slots=True)
class ScriptPackage:
    topic: PlannedTopic
    hook: str
    beats: list[str]
    cta: str
    full_script: str
    caption: CaptionPackage
    evidence: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RenderArtifact:
    script_id: int
    provider: str
    video_path: Path
    audio_path: Path
    subtitle_path: Path
    duration_seconds: float
    metadata: dict[str, Any]
    fallback_used: bool = False


@dataclass(slots=True)
class QualityReport:
    passed: bool
    issues: list[str]
