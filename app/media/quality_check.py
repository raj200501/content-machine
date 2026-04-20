"""Renderable media quality checks."""

from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher

from app.config import Settings
from app.models import QualityReport, RenderArtifact
from app.utils import ffprobe_duration


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def validate_render(
    settings: Settings,
    script_row: dict,
    artifact: RenderArtifact,
    recent_scripts: list[dict],
) -> QualityReport:
    issues: list[str] = []
    if not artifact.video_path.exists():
        issues.append("rendered MP4 is missing")
    if not artifact.audio_path.exists():
        issues.append("audio file is missing")
    if not artifact.subtitle_path.exists():
        issues.append("subtitle file is missing")

    duration = artifact.duration_seconds or ffprobe_duration(settings.ffprobe_binary, artifact.video_path)
    if duration < 14 or duration > 31:
        issues.append(f"duration {duration:.1f}s is outside the 15-30 second target")

    if len(script_row["caption"]) > 2200:
        issues.append("caption is too long for Instagram")

    scheduled = datetime.fromisoformat(script_row["scheduled_at"])
    if not (settings.publication_start_hour <= scheduled.hour <= settings.publication_end_hour):
        issues.append("scheduled publish window is outside configured hours")

    if script_row.get("fact_status") == "failed":
        issues.append("fact_guard marked the script as unsupported")

    for recent in recent_scripts[:25]:
        if recent["id"] == script_row["id"]:
            continue
        if _similarity(recent["full_script"], script_row["full_script"]) >= 0.86:
            issues.append("script is too similar to a recent draft")
            break

    return QualityReport(passed=not issues, issues=issues)
