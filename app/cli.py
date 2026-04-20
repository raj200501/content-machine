"""Typer CLI entrypoints."""

from __future__ import annotations

from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from app.config import get_settings
from app.db import Database
from app.logging_utils import configure_logging
from app.scheduler import build_publication_slots

app = typer.Typer(help="Automation CLI for daily internship/new-grad reel generation.")
console = Console()


def _ctx() -> tuple[Database, object]:
    settings = get_settings()
    configure_logging(settings.log_level)
    db = Database(settings.database_runtime_path, settings=settings)
    return db, settings


def _seed_smoke_items(db: Database, settings) -> None:
    source_id = db.upsert_source(
        "smoke-seed",
        "job_board",
        {"name": "smoke-seed", "source_type": "job_board", "url": "https://example.com/jobs"},
    )
    base_items = [
        {
            "source_type": "job_board",
            "source_url": "https://example.com/datadog-intern",
            "title": "Datadog Software Engineer Intern",
            "normalized_title": "datadog software engineer intern",
            "published_at": datetime.now(settings.tzinfo).isoformat(),
            "fetched_at": datetime.now(settings.tzinfo).isoformat(),
            "text_content": "Datadog has a public internship role for software engineering students.",
            "summary": "Public internship role for software engineering students.",
            "extracted_entities": ["Datadog"],
            "extracted_roles": ["software_engineering", "internship"],
            "freshness_score": 95,
            "relevance_score": 95,
            "duplicate_hash": "smoke1",
            "metadata": {"seed": True},
        },
        {
            "source_type": "job_board",
            "source_url": "https://example.com/cloudflare-new-grad",
            "title": "Cloudflare New Grad Software Engineer",
            "normalized_title": "cloudflare new grad software engineer",
            "published_at": datetime.now(settings.tzinfo).isoformat(),
            "fetched_at": datetime.now(settings.tzinfo).isoformat(),
            "text_content": "Cloudflare has a public new grad posting for software engineering.",
            "summary": "Public new grad posting for software engineering.",
            "extracted_entities": ["Cloudflare"],
            "extracted_roles": ["software_engineering", "new_grad"],
            "freshness_score": 92,
            "relevance_score": 94,
            "duplicate_hash": "smoke2",
            "metadata": {"seed": True},
        },
        {
            "source_type": "rss",
            "source_url": "https://example.com/recruiting-timeline",
            "title": "Internship recruiting timelines are moving earlier",
            "normalized_title": "internship recruiting timelines are moving earlier",
            "published_at": datetime.now(settings.tzinfo).isoformat(),
            "fetched_at": datetime.now(settings.tzinfo).isoformat(),
            "text_content": "Recruiting timelines keep moving earlier, so students should prep resumes and OA practice sooner.",
            "summary": "Recruiting timelines are moving earlier for students.",
            "extracted_entities": [],
            "extracted_roles": ["internship"],
            "freshness_score": 90,
            "relevance_score": 88,
            "duplicate_hash": "smoke3",
            "metadata": {"seed": True},
        },
    ]
    for item in base_items:
        if not db.source_item_exists(item["source_url"], item["normalized_title"], item["duplicate_hash"]):
            db.insert_source_item(source_id, item)


@app.command("init-db")
def init_db() -> None:
    db, settings = _ctx()
    db.init_db()
    console.print(f"Initialized {settings.database_backend} schema.")


@app.command("refresh-sources")
def refresh_sources() -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.refresh_sources import run_refresh_sources

    stats = run_refresh_sources(db, settings)
    console.print(stats)


@app.command("plan-day")
def plan_day() -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.plan_day import run_plan_day

    stats = run_plan_day(db, settings)
    console.print(stats)


@app.command("render-batch")
def render_batch(count: int = typer.Option(20, "--count", min=1)) -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.render_batch import run_render_batch

    stats = run_render_batch(db, settings, count=count)
    console.print(stats)


@app.command("publish-ready")
def publish_ready() -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.publish_batch import run_publish_batch

    stats = run_publish_batch(db, settings, ignore_schedule=settings.dry_run)
    console.print(stats)


@app.command("daily-run")
def daily_run() -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.daily_run import run_daily

    stats = run_daily(db, settings)
    console.print(stats)


@app.command("automation-tick")
def automation_tick() -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.automation_tick import run_automation_tick

    stats = run_automation_tick(db, settings)
    console.print(stats)


@app.command("metrics")
def metrics() -> None:
    db, settings = _ctx()
    db.init_db()
    today = datetime.now(settings.tzinfo).date().isoformat()
    rows = db.metrics_for_day(today)
    table = Table(title=f"Metrics for {today}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_column("Notes")
    for row in rows:
        table.add_row(row["metric_name"], str(row["metric_value"]), row.get("notes") or "")
    console.print(table)


@app.command("smoke-test")
def smoke_test() -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.plan_day import run_plan_day
    from app.workflows.publish_batch import run_publish_batch
    from app.workflows.render_batch import run_render_batch

    _seed_smoke_items(db, settings)
    planned = run_plan_day(db, settings)
    rendered = run_render_batch(db, settings, count=1)
    published = run_publish_batch(db, settings, ignore_schedule=True, limit=1)
    slots = build_publication_slots(datetime.now(settings.tzinfo).date(), settings)
    console.print(
        {
            "planned": planned,
            "rendered": rendered,
            "published": published,
            "sample_publish_slot": slots[0].isoformat(),
        }
    )


if __name__ == "__main__":
    app()
