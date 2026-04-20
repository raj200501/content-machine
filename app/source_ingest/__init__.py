"""Source ingestion helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.models import SourceDefinition


def load_source_definitions(path: Path) -> list[SourceDefinition]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        SourceDefinition.from_dict(source)
        for source in payload.get("sources", [])
        if source.get("enabled", True)
    ]
