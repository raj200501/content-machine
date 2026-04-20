from app.writing.fact_guard import guard_script


def test_fact_guard_softens_unsupported_dates_and_numbers() -> None:
    evidence = [
        {
            "title": "Recruiting timelines are moving earlier",
            "summary": "Recruiting timelines are moving earlier and students should prep sooner.",
            "text_content": "Recruiting timelines are moving earlier and students should prep resumes sooner.",
            "source_url": "https://example.com/article",
        }
    ]
    script = "\n".join(
        [
            "Recruiting timelines are moving earlier this year.",
            "Apply by May 10 because this closes in 3 days.",
        ]
    )

    guarded = guard_script(script, evidence)

    assert guarded.passed is False
    assert "May 10" not in guarded.script_text
    assert "3 days" not in guarded.script_text
    assert guarded.claims[0].evidence
