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
    assert "Stripe: Software Engineer Intern in San Francisco." in package.full_script
    assert "Figma: Data Engineer Intern in New York." in package.full_script
    assert all(name in package.hook for name in ("Stripe", "Figma", "Lyft"))  # hook names the companies
    assert len(package.caption.hashtags) <= 3
    assert "Stripe" in package.caption.caption.splitlines()[0]  # keyword-rich first line
    assert "has a public posting" not in package.full_script
    assert 35 <= len(package.full_script.split()) <= 80
    scenes = package.metadata["scenes"]
    assert [scene["kind"] for scene in scenes] == ["hook", "job", "job", "job", "cta"]
    assert scenes[1]["company"] == "Stripe" and scenes[1]["location"] == "San Francisco"
    assert len(scenes) == len(package.full_script.splitlines())


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


def test_job_alert_speaks_posted_pay_and_guard_keeps_it() -> None:
    from app.writing.fact_guard import guard_script

    topic = PlannedTopic("2026-11-07", 1, "2026-11-07T11:30:00-05:00", "openings_job_alert", "x", "", "", "Stripe", [1, 2, 3], 80)
    items = [
        _job(1, "Stripe", "Machine Learning Engineer, Intern"),
        _job(2, "Figma", "Software Engineer Intern", "New York, NY"),
        _job(3, "Lyft", "Data Engineer Intern", "Toronto, Canada"),
    ]
    meta = json.loads(items[0]["metadata_json"])
    meta.update({"pay": "$47–$58/hr", "pay_spoken": "47 to 58 dollars an hour"})
    items[0]["metadata_json"] = json.dumps(meta)
    items[0]["text_content"] = items[0].get("text_content", "") + " Pay range: $47–$58/hr."
    package = build_script(topic, items)
    assert "in San Francisco, listed at $47–$58/hr." in package.full_script
    assert package.metadata["scenes"][1]["pay"] == "$47–$58/hr"
    assert "$47–$58/hr (listed)" in package.caption.caption
    guarded = guard_script(package.full_script, items)
    assert "$47–$58/hr" in guarded.script_text  # real, sourced numbers are not softened
    assert "recent" not in guarded.script_text.split("\n")[1]


def test_hooks_only_claim_what_the_postings_support() -> None:
    from app.writing.hooks import choose_hook, job_alert_candidates

    jobs = [
        {"company": "Samsara", "title": "Software Engineering Intern", "pay": "$61.90/hr", "posted_days": 1},
        {"company": "Google", "title": "Software Engineering Intern", "pay": "$52–$58/hr", "posted_days": 3},
    ]
    hooks = {hook.id: hook.text for hook in job_alert_candidates(jobs, "interns", "internships")}
    assert hooks["company_pays"] == "Samsara pays interns up to $61.90/hr."
    assert hooks["not_faang"] == "This internship pays $61.90/hr and it isn't FAANG."
    assert hooks["n_paying_over"] == "2 internships that pay at least $52/hr, still open."
    assert "grad_year" not in hooks  # no year in the titles
    google_top = [{"company": "Google", "title": "SWE Intern", "pay": "$70/hr", "posted_days": 1}]
    assert "not_faang" not in {h.id for h in job_alert_candidates(google_top, "interns", "internships")}
    picked = choose_hook(job_alert_candidates(jobs, "interns", "internships"), {"company_pays": 1.8}, ["as_an_intern"], seed=3)
    assert picked.id != "as_an_intern"
