import json

from app.config import Settings
from app.writing import idea_engine
from app.writing.idea_engine import draft_tip_packs, validate


def test_rules_reject_stats_money_and_repeats() -> None:
    lines = ["Say the edge cases out loud before you write any code.", "Then walk one tiny example by hand, slowly and clearly.", "Interviewers grade the thinking they can hear, not silence."]
    assert validate("interview_prep", "Do this before you write a single line.", lines, []) is None
    assert validate("interview_prep", "80% of candidates fail this question.", lines, [])
    assert validate("interview_prep", "Do this before you write a single line.", lines[:2], [])
    assert validate("interview_prep", "Never start coding the second they stop talking.", lines, ["Never start coding the second they stop talking."])
    assert validate("interview_prep", "Do this before you write a single line.", [lines[0], "Earn $50 an hour fast with this trick here.", lines[2]], [])


def test_engine_returns_valid_drafts_and_skips_bad_ones(monkeypatch) -> None:
    reply = {
        "reels": [
            {"category": "interview_prep", "hook": "Say this the second you get stuck", "lines": [
                "Let me talk through a smaller version of this first.",
                "It buys you time and shows the interviewer how you think.",
                "Silence reads as stuck. Narration reads as problem solving."]},
            {"category": "resume_portfolio", "hook": "90% of resumes fail this test", "lines": ["a b c d e f", "a b c d e f", "a b c d e f"]},
        ]
    }
    calls = []

    def fake_call(base, model, prompt, api_key=""):
        calls.append((base, model))
        return json.dumps(reply)

    monkeypatch.setattr(idea_engine, "_call", fake_call)
    settings = Settings(llm_base_url="http://llm.test/v1", llm_model="some-model", idea_engine=True)
    drafts = draft_tip_packs(["interview_prep", "resume_portfolio"], settings, winners=[{"hook": "x", "score": 1.0}])
    assert list(drafts) == ["interview_prep"]
    assert drafts["interview_prep"].hook.endswith(".")
    assert calls == [("http://llm.test/v1", "some-model")]


def test_engine_is_off_without_a_model(tmp_path) -> None:
    assert draft_tip_packs(["interview_prep"], Settings(llm_dir=tmp_path, llm_base_url="")) == {}
