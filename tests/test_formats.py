import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from app.config import Settings
from app.insight.job_stats import from_display, level_of, market, records
from app.planning.format_planner import DayPlanner, pick_item, to_package
from app.writing import formats
from app.workflows.jobs_page import build_jobs_page


def _item(i, company, title, pay, days=2):
    return {
        "id": i, "source_type": "job_board", "title": title, "source_url": f"https://example.com/{i}",
        "published_at": (date.today() - timedelta(days=days)).isoformat(), "fetched_at": date.today().isoformat(),
        "freshness_score": 80, "relevance_score": 40, "summary": "", "text_content": "",
        "metadata_json": json.dumps({"company": company, "job_title": title, "pay": pay, "location": "San Mateo, CA, United States"}),
    }


ITEMS = [
    _item(1, "Stripe", "Master's Machine Learning Engineer, Intern", "$47–$58/hr"),
    _item(2, "Roblox", "Software Engineer Intern - Summer 2027", "$52–$60/hr", 1),
    _item(3, "Verkada", "Backend Software Engineer - University Graduate 2027", "$120K–$140K/yr"),
    _item(4, "Samsara", "Software Engineering Internship", "$61.90/hr"),
    _item(5, "Pinterest", "Machine Learning Internship 2027 (USA)", "$40–$55/hr"),
    _item(6, "Zoox", "Hardware Engineer Intern, Vehicle Systems [Summer 2027]", "$6,500–$8,500/mo"),
] + [_item(10 + i, f"Co{i}", "Software Engineer Intern", f"${30 + i * 3}/hr") for i in range(8)]


def test_pay_parsing_and_levels() -> None:
    assert from_display("$120K–$140K/yr").high == 140000
    assert from_display("$61.90/hr").low == 61.9
    assert level_of("Software Engineer Intern") == "intern"
    assert level_of("Backend Software Engineer - University Graduate 2027") == "new_grad"


def test_every_format_has_one_scene_per_line_and_no_invented_numbers() -> None:
    jobs = records(ITEMS)
    stats = market(jobs)
    rng = random.Random(1)
    built = [
        formats.job_alert(jobs[0], stats, rng),
        formats.countdown(jobs, stats, rng),
        formats.pay_tiers(jobs, rng),
        formats.redline(0, rng),
        formats.chat(0, rng),
        formats.hack(0, rng),
    ]
    for script in built:
        assert script is not None
        assert len(script.lines) == len(script.scenes)
        assert script.hook_id.startswith(f"fmt:{script.format}:")
    alert = built[0]
    assert "$58/hr" in alert.lines[0]
    assert any("median" in line for line in alert.lines)
    countdown = built[1]
    # One level per list, best last.
    assert all("/hr" in scene["pay"] for scene in countdown.scenes if scene["kind"] == "countdown_item")
    assert countdown.scenes[-2]["rank"] == 1


def test_planner_never_repeats_a_role_in_a_day_and_rotates_libraries() -> None:
    from app.models import PlannedTopic

    planner = DayPlanner(ITEMS, [], date(2026, 11, 10))
    topics = [
        PlannedTopic("2026-11-10", i, "x", category, "", "", "", "", [], 0)
        for i, category in enumerate(["openings_job_alert", "openings_job_alert", "resume_portfolio", "interview_prep", "application_strategy"])
    ]
    scripts = [planner.build(topic) for topic in topics]
    assert [s.format for s in scripts] == ["job_alert", "countdown", "redline", "chat", "hack"]
    urls = [job.url for s in scripts for job in s.jobs]
    assert len(urls) == len(set(urls))
    package = to_package(topics[0], scripts[0], [])
    assert package.metadata["format"] == "job_alert" and package.full_script.count("\n") == len(scripts[0].lines) - 1
    index, fresh = pick_item("hack", ["fmt:hack:0", "fmt:hack:1"], random.Random(0))
    assert index not in {0, 1} and fresh


def test_jobs_page_lists_roles_with_pay() -> None:
    page = build_jobs_page(ITEMS, "@careerstacked", datetime(2026, 11, 10, 8, 0))
    assert "Stripe" in page and "$47–$58/hr" in page and "https://example.com/1" in page


def test_studio_renders_a_short_reel(tmp_path: Path) -> None:
    from app.media.studio import render_studio

    settings = Settings(output_dir=tmp_path, assets_dir=tmp_path / "assets", tts_engine="silent", capture_postings=False,
                        render_fps=6, music_bed=False, sound_effects=False)
    script = formats.chat(0, random.Random(0))
    row = {"id": 1, "full_script": "\n".join(script.lines[:3]), "metadata_json": json.dumps({"format": "chat", "scenes": script.scenes[:3]})}
    artifact = render_studio(settings, row, tmp_path / "out")
    assert artifact.video_path.exists() and artifact.duration_seconds > 2
