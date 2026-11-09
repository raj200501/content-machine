"""Refresh public sources into normalized SQLite state."""

from __future__ import annotations

import logging
from dataclasses import asdict

from app.config import Settings
from app.db import Database
from app.source_ingest import load_source_definitions
from app.source_ingest.dedupe import normalize_title
from app.source_ingest.jobs_ingest import ingest_job_board
from app.source_ingest.rss_ingest import ingest_feed
from app.source_ingest.youtube_ingest import ingest_youtube

LOG = logging.getLogger(__name__)


def run_refresh_sources(db: Database, settings: Settings) -> dict[str, int]:
    definitions = load_source_definitions(settings.source_config_path)
    ingested = 0
    relevant = 0

    for source in definitions:
        source_id = db.upsert_source(source.name, source.source_type, asdict(source))
        try:
            if source.source_type in {"rss", "news_query"}:
                candidates = ingest_feed(source, settings)
            elif source.source_type == "job_board":
                candidates = ingest_job_board(source, settings)
            elif source.source_type == "youtube":
                candidates = ingest_youtube(source, settings)
            else:
                LOG.warning("Unsupported source type: %s", source.source_type)
                continue
        except Exception as exc:
            LOG.warning("Source refresh failed for %s: %s", source.name, exc)
            continue

        ingested += len(candidates)
        for candidate in candidates:
            payload = asdict(candidate)
            payload["normalized_title"] = normalize_title(candidate.title)
            if db.source_item_exists(candidate.source_url, payload["normalized_title"], candidate.duplicate_hash):
                # Still on the job board today: mark it as seen so it counts as open.
                db.touch_source_item(candidate.source_url, payload["fetched_at"])
                continue
            row_id = db.insert_source_item(source_id, payload)
            if row_id:
                relevant += 1

    metric_date = str(__import__("datetime").datetime.now(settings.tzinfo).date())
    db.set_metric(metric_date, "sources_ingested", ingested)
    db.set_metric(metric_date, "relevant_items_found", relevant)
    return {"sources_ingested": ingested, "relevant_items_found": relevant}
