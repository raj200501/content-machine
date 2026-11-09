"""Typer CLI entrypoints."""

from __future__ import annotations

import json

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.config import get_settings
from app.logging_utils import configure_logging
from app.scheduler import build_publication_slots
from app.setup_status import build_setup_report

app = typer.Typer(help="Automation CLI for daily internship/new-grad reel generation.")
console = Console()


def _ctx() -> tuple[Database, object]:
    from app.db import Database

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


@app.command("setup-status")
def setup_status(
    strict_live: bool = typer.Option(False, "--strict-live", help="Exit non-zero unless live publishing is ready."),
    strict_video: bool = typer.Option(
        False,
        "--strict-video",
        help="Exit non-zero unless provider video generation is ready.",
    ),
) -> None:
    settings = get_settings()
    report = build_setup_report(settings)
    table = Table(title="Content Machine setup status")
    table.add_column("Area")
    table.add_column("Item")
    table.add_column("Status")
    table.add_column("Details")
    for check in report.checks:
        table.add_row(check.category, check.name, check.status, check.detail)
    console.print(table)

    if report.ready_for_github_automation:
        console.print("GitHub automation has the required settings for live publishing.")
    elif report.ready_for_live_publish:
        console.print(
            "Live publishing is configured locally. GitHub-hosted automation still needs Turso state secrets."
        )
    else:
        console.print("Live publishing is not ready yet. Run with DRY_RUN=true until the missing keys are set.")

    if strict_live and not report.ready_for_live_publish:
        raise typer.Exit(1)
    if strict_video and not report.ready_for_provider_video:
        raise typer.Exit(1)


@app.command("sync-env")
def sync_env(
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Local env file to update."),
    example_file: Path = typer.Option(Path(".env.example"), "--example-file", help="Template env file."),
) -> None:
    from app.env_sync import append_missing_env_values

    added = append_missing_env_values(env_file, example_file)
    if added:
        console.print(f"Added {len(added)} missing env keys to {env_file}: {', '.join(added)}")
    else:
        console.print(f"{env_file} already has every key from {example_file}.")


@app.command("instagram-accounts")
def instagram_accounts() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.instagram_access_token:
        console.print("Set INSTAGRAM_ACCESS_TOKEN first, then rerun this command.")
        raise typer.Exit(1)

    from app.publishing.instagram_meta import InstagramMetaPublisher

    accounts = InstagramMetaPublisher(settings).connected_instagram_accounts()
    if not accounts:
        console.print("No connected Instagram Professional accounts were returned for this token.")
        raise typer.Exit(1)

    table = Table(title="Connected Instagram accounts")
    table.add_column("Page")
    table.add_column("Page ID")
    table.add_column("Instagram User ID")
    table.add_column("Username")
    table.add_column("Type")
    for account in accounts:
        table.add_row(
            account["page_name"],
            account["page_id"],
            account["instagram_ig_user_id"],
            account["username"],
            account["account_type"],
        )
    console.print(table)
    console.print("Use the Instagram User ID value for INSTAGRAM_IG_USER_ID.")


@app.command("exchange-token")
def exchange_token(
    write_env: bool = typer.Option(True, "--write-env/--no-write-env", help="Save results into .env"),
    env_path: Path = typer.Option(Path(".env"), "--env-path"),
) -> None:
    """Turn a short-lived Graph API Explorer token into a non-expiring Page token."""

    settings = get_settings()
    configure_logging(settings.log_level)
    from app.env_sync import set_env_values
    from app.publishing.instagram_meta import InstagramMetaPublisher

    result = InstagramMetaPublisher(settings).exchange_for_long_lived_token()
    if "page_token" not in result:
        console.print(
            "Got a long-lived user token, but no Facebook Page with a connected Instagram Professional account. "
            "Connect Instagram to a Page, then rerun."
        )
        raise typer.Exit(1)
    console.print(
        f"Connected: @{result.get('username', '')} via Page '{result.get('page_name', '')}'. "
        f"INSTAGRAM_IG_USER_ID={result['instagram_ig_user_id']}"
    )
    if write_env:
        set_env_values(
            env_path,
            {
                "INSTAGRAM_ACCESS_TOKEN": result["page_token"],
                "INSTAGRAM_IG_USER_ID": result["instagram_ig_user_id"],
            },
        )
        console.print(f"Saved the non-expiring Page token and IG user ID to {env_path} (values not printed).")
        console.print("Copy the same two values into your GitHub Actions secrets.")
    else:
        console.print("Re-run with --write-env to save the values; tokens are never printed.")


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
    # Read by scripts/health_issue.py to open or close the "posting is broken" issue.
    status_path = settings.output_dir / "last_tick.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(stats, default=str), encoding="utf-8")


@app.command("jobs-page")
def jobs_page(out: Path = typer.Option(Path("site/index.html"), help="Where to write the page")) -> None:
    """The link-in-bio page: every open role we track, with pay and apply links."""
    db, settings = _ctx()
    db.init_db()
    from datetime import datetime

    from app.planning.topic_mixer import open_postings
    from app.workflows.jobs_page import build_jobs_page

    now = datetime.now(settings.tzinfo)
    items = open_postings(db.recent_source_items(days=30, limit=1000), [], now.date())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_jobs_page(items, settings.brand_handle, now), encoding="utf-8")
    console.print(f"wrote {out}")


@app.command("weekly-report")
def weekly_report(out: Path = typer.Option(Path("REPORT.md"), help="Where to write the report")) -> None:
    db, settings = _ctx()
    db.init_db()
    from app.workflows.weekly_report import build_weekly_report

    followers = None
    if settings.instagram_access_token:
        try:
            from app.publishing.instagram_meta import InstagramMetaPublisher

            followers = InstagramMetaPublisher(settings).followers_count()
        except Exception as exc:  # the report must never fail the run
            console.print(f"followers unavailable: {str(exc)[:120]}")
    out.write_text(build_weekly_report(db, settings, followers), encoding="utf-8")
    console.print(f"wrote {out}")


@app.command("idea-check")
def idea_check() -> None:
    """Ask the idea engine for one reel per tip category and print what passes the rules."""
    _db, settings = _ctx()
    from app.writing.idea_engine import CATEGORY_BRIEFS, draft_tip_packs

    drafts = draft_tip_packs(list(CATEGORY_BRIEFS), settings)
    for category, draft in drafts.items():
        console.print(f"[bold]{category}[/bold] ({draft.model}): {draft.hook}")
        for beat in draft.beats:
            console.print(f"  - {beat}")
    console.print(f"{len(drafts)} drafts passed")


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
