"""Content taxonomy and template hooks."""

from __future__ import annotations

from collections import OrderedDict

DAILY_BUCKETS = OrderedDict(
    [
        ("openings_job_alert", 6),
        ("application_strategy", 4),
        ("interview_prep", 4),
        ("resume_portfolio", 3),
        ("market_context", 2),
        ("motivational_community", 1),
    ]
)

HOOK_STYLES = {
    "openings_job_alert": [
        "3 roles to apply to today",
        "companies still hiring interns right now",
        "early-career tech openings worth checking",
        "new-grad roles that are actually live",
    ],
    "application_strategy": [
        "If you're a CS student doing this, stop",
        "This is why you're not hearing back",
        "Don't send this recruiter message",
        "Application batching that actually helps",
    ],
    "interview_prep": [
        "technical interview fix in 20 seconds",
        "behavioral answer mistake students keep making",
        "OA prep if you're short on time",
        "what recruiters notice in interview prep",
    ],
    "resume_portfolio": [
        "3 resume fixes before internship season",
        "what to do if you have no internships yet",
        "GitHub and portfolio fixes for students",
        "resume bullets that sound stronger fast",
    ],
    "market_context": [
        "new-grad market update in 20 seconds",
        "what this hiring shift means for students",
        "layoffs and hiring context, minus the panic",
    ],
    "motivational_community": [
        "you're not behind, but do this next",
        "job search momentum without burnout",
        "small move that makes this week better",
    ],
}

EVERGREEN_ANGLES = {
    "openings_job_alert": [
        "When live openings thin out, widen the company mix and keep checking public boards directly.",
        "Use today's search block to scan internships, new-grad roles, and adjacent analyst or PM listings.",
        "A thinner feed day is still useful if you review public boards with a tighter role-family filter.",
    ],
    "application_strategy": [
        "Tailor your resume keywords to the role family, not just the company logo.",
        "Batch similar roles together so your resume and recruiter message stay aligned.",
        "Apply earlier in the week and follow with a cleaner recruiter note, not a longer one.",
    ],
    "interview_prep": [
        "Practice one debugging story, one ambiguity story, and one teamwork story every week.",
        "OA prep improves faster when you drill timing, not just question volume.",
        "Use mock interviews to tighten explanations, not to memorize scripts.",
    ],
    "resume_portfolio": [
        "If you lack internships, lead with shipped projects, measurable outcomes, and clean READMEs.",
        "Move technical stack into project bullets so recruiters see tools next to impact.",
        "Pin two relevant repositories and remove stale coursework clutter.",
    ],
    "market_context": [
        "Hiring is uneven, so students need a wider role mix across SWE, data, ML, PM, and analyst lanes.",
        "When postings look thinner, shift part of your week to evergreen prep instead of doomscrolling.",
    ],
    "motivational_community": [
        "Momentum matters more than one perfect application sprint.",
        "You only need a stronger process this week, not a complete reinvention.",
    ],
}
