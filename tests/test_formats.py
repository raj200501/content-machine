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
    assert index not in {"0", "1"} and fresh


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


def test_trend_topics_and_weights(tmp_path: Path) -> None:
    from app.db import Database
    from app.publishing.trends import _ensure_table, topics_of, trend_format_weights

    assert "pay" in topics_of("Stripe pays interns $58/hr") and "job_list" in topics_of("Stripe is hiring interns")
    assert topics_of("Never say this in a behavioral interview") == ["interview"]
    db = Database(tmp_path / "db.sqlite")
    db.init_db()
    _ensure_table(db)
    with db.connect() as conn:
        for i in range(6):
            conn.execute(
                "INSERT INTO trend_posts VALUES (?, 'x', 'c', 1, 1, 100, 3.0, ?, 'REELS', NULL, 'now')",
                (f"p{i}", "resume" if i < 4 else "interview"),
            )
    weights = trend_format_weights(db)
    assert weights["redline"] > weights["chat"] >= 0.75


def test_spotlight_and_daily_variety() -> None:
    from app.models import PlannedTopic

    items = ITEMS + [_item(40, "Stripe", "Software Engineer Intern", "$50–$56/hr"), _item(41, "Stripe", "Data Science Intern", "$45–$52/hr")]
    planner = DayPlanner(items, [f"fmt:{f}:{i}" for i in range(20) for f in ("redline", "chat", "hack")], date(2026, 11, 10))
    topics = [PlannedTopic("2026-11-10", i, "x", c, "", "", "", "", [], 0) for i, c in enumerate(["resume_portfolio", "interview_prep"])]
    built = [planner.build(t) for t in topics]
    assert built[0].format == "spotlight" and built[0].lines[0].startswith("Stripe has 3")
    assert built[1].format != "spotlight" or built[1].jobs[0].company != "Stripe"


def test_library_growth_checks_and_uses_generated_items(tmp_path: Path, monkeypatch) -> None:
    import app.writing.library_growth as growth
    from app.db import Database
    from app.models import PlannedTopic

    good = {"hook": "Your projects section is hiding your best work.", "weak": "Built various projects.",
            "strong": "Built a budget app in Swift with 1,200 downloads and a 4.8 rating.", "why": "Downloads and ratings are proof anyone can check."}
    bad = {"hook": "Google wants this on your resume.", "weak": "Did stuff.", "strong": "Improved things a lot.", "why": "Because it is better."}
    calls = []

    def fake_chat(settings, messages, max_tokens=3000):
        calls.append(messages[-1]["content"][:20])
        if "grade these" in messages[-1]["content"]:
            return '[{"grade": 9, "fix": ""}]'
        return json.dumps([good, bad])

    monkeypatch.setattr(growth, "_chat", fake_chat)
    db = Database(tmp_path / "db.sqlite")
    db.init_db()
    settings = Settings(llm_api_key="k", llm_base_url="https://llm.test/v1")
    stats = growth.grow_libraries(db, settings)
    assert stats["kept"] >= 1 and any("banned" in r or "no number" in r for r in stats["rejected"])
    redlines_before = len(growth.generated_items(db, "redline"))
    growth.grow_libraries(db, settings)  # chats are still due; redlines grew this week
    assert len(growth.generated_items(db, "redline")) == redlines_before
    items = growth.generated_items(db, "redline")
    assert items and items[0][0].startswith("g")
    planner = DayPlanner(ITEMS, [f"fmt:redline:{i}" for i in range(20)], date(2026, 11, 10))
    planner.add_generated("redline", items)
    script = planner.build(PlannedTopic("2026-11-10", 0, "x", "resume_portfolio", "", "", "", "", [], 0))
    assert script.format == "redline" and script.hook_id == f"fmt:redline:{items[0][0]}"
    assert growth.grow_libraries(db, Settings(llm_api_key="", llm_base_url=""))["skipped"].startswith("no LLM")


def test_style_experiments_pick_known_values_and_land_in_metadata() -> None:
    from app.models import PlannedTopic
    from app.planning.experiments import DIMENSIONS, choose_variant

    variant = choose_variant(None, random.Random(1))
    assert set(variant) == set(DIMENSIONS) and all(variant[k] in DIMENSIONS[k] for k in DIMENSIONS)
    planner = DayPlanner(ITEMS, [], date(2026, 11, 10))
    topic = PlannedTopic("2026-11-10", 0, "x", "openings_job_alert", "", "", "", "", [], 0)
    script = planner.build(topic)
    package = to_package(topic, script, [])
    assert package.metadata["variant"] == script.variant_settings
    assert len(script.lines) == len(script.scenes)
