import json
from pathlib import Path

from app.models import PlannedTopic, SourceDefinition
from app.planning.topic_mixer import _job_groups
from app.source_ingest.jobs_ingest import _wanted
from app.writing.script_writer import build_script, clean_headline, spoken_job_title


def _job(item_id: int, company: str, title: str, location: str = "San Francisco, CA") -> dict:
    return {
        "id": item_id,
        "source_type": "job_board",
        "title": title,
        "summary": title,
        "source_url": f"https://example.com/{item_id}",
        "freshness_score": 80.0,
        "relevance_score": 40.0,
        "metadata_json": json.dumps({"company": company, "location": location, "job_title": title}),
    }


def test_job_filter_matches_words_not_substrings() -> None:
    filters = ["intern", "new grad", "university graduate"]
    assert _wanted("Software Engineer Intern (Summer 2027)", filters)
    assert _wanted("Data Science Internship 2027", filters)
    assert _wanted("Backend Software Engineer - University Graduate 2027", filters)
    assert not _wanted("Senior Manager, Internal Comms", filters)
    assert not _wanted("Staff Experience Designer, International", filters)
    assert not _wanted("Accounting Intern", filters)
    assert not _wanted("Internal Audit Analytics Intern", filters)


def test_spoken_job_titles_are_clean() -> None:
    assert spoken_job_title("[Summer 2027] Software Engineer Intern") == ("Software Engineer Intern", "")
    assert spoken_job_title("PhD Intern, Software Engineer - Graphics (2027)") == (
        "Software Engineer Intern",
        "for PhD students",
    )
    assert spoken_job_title("Backend Software Engineer - University Graduate 2027")[0] == "new grad Backend Software Engineer"
    assert clean_headline("Google opens 2027 internship applications - EdTech Hub") == "Google opens 2027 internship applications"


def test_job_groups_use_three_different_companies() -> None:
    items = [
        _job(1, "Stripe", "Software Engineer Intern"),
        _job(2, "Stripe", "Data Science Intern"),
        _job(3, "Figma", "Data Engineer Intern"),
        _job(4, "Lyft", "Data Engineer Intern"),
        _job(5, "Zoox", "Software Engineer Intern"),
        {**_job(6, "News", "Company opens internships"), "source_type": "news_query"},
    ]
    groups = _job_groups(items)
    assert groups
    for group in groups:
        companies = [json.loads(item["metadata_json"])["company"] for item in group]
        assert len(set(companies)) == 3
        assert all(item["source_type"] == "job_board" for item in group)


def test_job_alert_script_names_company_role_and_city() -> None:
    topic = PlannedTopic(
        day="2026-11-07",
        slot_index=0,
        scheduled_at="2026-11-07T08:00:00-05:00",
        category="openings_job_alert",
        hook_style="3 roles to apply to today",
        title="",
        angle="",
        company="Stripe",
        source_item_ids=[1, 3, 4],
        freshness_score=80,
    )
    items = [
        _job(1, "Stripe", "Software Engineer Intern (Summer 2027)"),
        _job(3, "Figma", "Data Engineer Intern (2027)", "New York, NY"),
        _job(4, "Lyft", "Data Engineer Intern", "Toronto, Canada"),
    ]
    package = build_script(topic, items)
    assert "Stripe is hiring a Software Engineer Intern in San Francisco." in package.full_script
    assert "Figma is hiring a Data Engineer Intern in New York." in package.full_script
    assert "#stripe" in package.caption.hashtags
    assert "has a public posting" not in package.full_script
    assert 40 <= len(package.full_script.split()) <= 80


def test_evergreen_scripts_rotate_and_skip_recent_hooks() -> None:
    def topic(day: str) -> PlannedTopic:
        return PlannedTopic(day, 2, f"{day}T15:00:00-05:00", "resume_portfolio", "x", "", "", "", [], 40)

    first = build_script(topic("2026-11-07"), [])
    second = build_script(topic("2026-11-07"), [], recent_hooks={first.hook})
    assert first.hook != second.hook
    assert len(first.beats) == 3


def test_source_definitions_carry_company_names() -> None:
    payload = json.loads(Path("app/source_ingest/source_definitions.json").read_text())
    boards = [SourceDefinition.from_dict(item) for item in payload["sources"] if item["source_type"] == "job_board"]
    assert len(boards) >= 10
    assert all(board.metadata.get("company") for board in boards)
